# Tắt tiến trình đột ngột và thời gian loại bỏ đăng ký

Khi một instance dừng đột ngột, service registry không nhất thiết biết ngay rằng instance đã biến mất. Provider có thể không còn chạy, nhưng registration vẫn tồn tại trong registry hoặc trong cache của consumer. Trong khoảng thời gian đó, consumer vẫn có thể chọn địa chỉ cũ và gặp lỗi kết nối.

**Thời gian loại bỏ đăng ký không phải một bộ đếm duy nhất.** Cần tách ít nhất bốn mốc: tiến trình dừng, registry phát hiện hoặc nhận yêu cầu deregister, dữ liệu registry được cập nhật, và consumer ngừng sử dụng địa chỉ cũ sau khi cache hoặc DNS được làm mới. Request đang chạy cũng cần thời gian drain riêng.

Bài này phân tích vòng đời đó trong Spring Cloud với Eureka, Consul và ZooKeeper; đồng thời trình bày cách shutdown có kiểm soát, cách đo thời gian stale registration và cách giảm lỗi khi process chết hoặc mạng bị phân vùng.

## 1. Phân biệt dừng tiến trình, deregister và ngừng gửi traffic

Một instance có thể trải qua các mốc sau:

1. **Tiến trình bắt đầu dừng:** nhận tín hiệu shutdown, crash hoặc mất máy.
2. **Ứng dụng ngừng nhận request mới:** readiness chuyển DOWN, server hoặc gateway bắt đầu drain traffic.
3. **Registration bị gỡ hoặc đánh dấu không khỏe:** provider gọi deregister, health check thất bại, lease hết hạn hoặc session ZooKeeper mất.
4. **Registry cập nhật catalog:** instance biến mất hoặc chuyển sang trạng thái không được chọn.
5. **Consumer cập nhật dữ liệu discovery:** client fetch lại registry, nhận watcher event hoặc truy vấn lại Consul.
6. **Load balancer hết dùng cache cũ:** danh sách instance trong bộ nhớ được thay mới.
7. **Request đang xử lý kết thúc:** các kết nối và request đã bắt đầu được drain hoặc timeout.

Vì vậy, “đã bị xóa khỏi registry” và “không còn consumer nào gọi vào instance” là hai điều khác nhau. Một consumer có thể vẫn giữ cache cũ sau khi server đã xóa registration. Ngược lại, health-aware consumer có thể ngừng chọn instance ngay khi trạng thái chuyển critical dù catalog vẫn giữ service record để theo dõi.

Cần phân biệt thêm ba tình huống:

| Tình huống | Provider có thể thực hiện deregister? | Cơ chế phát hiện chính |
|---|---|---|
| Graceful shutdown | Có, nếu shutdown hook và client còn hoạt động | Lời gọi deregister hoặc đóng session |
| Process crash / SIGKILL | Không | Heartbeat, lease, health check hoặc session timeout |
| Network partition | Thường không chắc chắn | Timeout và trạng thái kết nối; có thể bị nhầm với process crash |

Một process không phản hồi không nhất thiết đã chết. Nó có thể bị treo, mất mạng hoặc chỉ không truy cập được từ một vùng mạng. Registry cần một khoảng thời gian để phân biệt gián đoạn tạm thời với instance đã mất.

## 2. Graceful shutdown và abrupt shutdown

**Graceful shutdown** cho ứng dụng cơ hội dừng theo thứ tự. JVM nhận tín hiệu kết thúc phù hợp như SIGTERM, Spring đóng ApplicationContext, các lifecycle component thực hiện stop, discovery client có thể hủy registration, và HTTP server có thể drain request đang chạy.

**Abrupt shutdown** xảy ra khi process bị kill cưỡng bức, máy mất điện, container runtime dừng đột ngột hoặc JVM crash. Shutdown hook có thể không chạy; provider không gửi được deregistration. Registry phải dựa vào cơ chế phát hiện mất heartbeat, health check hoặc session expiration.

| Đặc điểm | Graceful shutdown | Abrupt shutdown |
|---|---|---|
| Có cơ hội chạy shutdown hook | Thường có | Không bảo đảm |
| Deregistration chủ động | Có thể thực hiện | Không |
| Request đang xử lý | Có thể drain đến hết timeout | Có thể bị ngắt ngay |
| Thời gian registry nhận biết | Thường ngắn nếu deregister thành công | Phụ thuộc heartbeat/check/session timeout |
| Rủi ro stale registration | Chủ yếu do cache và propagation | Do cả phát hiện lỗi lẫn cache |
| Cách giảm lỗi | Readiness, deregister, drain, stop | Health check, lease/session hợp lý, retry và loại instance lỗi |

SIGTERM chỉ là yêu cầu dừng có kiểm soát; nếu ứng dụng không hoàn tất trong thời gian grace period, runtime có thể gửi SIGKILL. SIGKILL không cho JVM cơ hội chạy shutdown hook. Do đó, không thể dựa hoàn toàn vào deregistration khi vận hành container hoặc máy chủ.

## 3. Một công thức để hiểu thời gian loại bỏ

Có thể mô hình hóa thời gian từ lúc instance thực sự ngừng phục vụ đến lúc consumer không còn chọn instance đó:

\[
T_{\text{stale}} \approx
T_{\text{detect}} +
T_{\text{registry}} +
T_{\text{propagation}} +
T_{\text{consumer-cache}}
\]

Trong đó:

- \(T_{\text{detect}}\): thời gian registry hoặc health checker phát hiện instance không còn hợp lệ.
- \(T_{\text{registry}}\): thời gian xử lý deregistration, eviction hoặc chuyển trạng thái.
- \(T_{\text{propagation}}\): thời gian dữ liệu mới đến các consumer.
- \(T_{\text{consumer-cache}}\): thời gian cache discovery hoặc load balancer còn giữ instance cũ.

Đây là mô hình ước lượng để tìm nguồn trễ, không phải cam kết SLA. Một số thành phần có thể chồng lấp; DNS cache, retry, connection pool và request đang chạy có thể làm quan sát thực tế khác đi.

Với graceful shutdown, thời gian phát hiện được thay bằng thời gian provider gửi deregistration thành công. Với abrupt shutdown, thời gian phát hiện thường là phần lớn độ trễ.

Cần đo riêng:

- Thời gian từ process stop đến lúc catalog thay đổi.
- Thời gian từ catalog thay đổi đến lúc consumer nhận danh sách mới.
- Thời gian từ lúc consumer nhận danh sách mới đến request cuối cùng đi vào instance cũ.
- Thời gian request đang chạy kết thúc hoặc thất bại.

Không cộng tất cả thành một con số nếu mục tiêu là tìm bottleneck. Registry có thể xóa instance rất nhanh trong khi consumer vẫn dùng cache cũ.

## 4. Eureka: heartbeat, lease expiration và eviction

Eureka Client đăng ký instance với Eureka Server và định kỳ gửi heartbeat để gia hạn lease. Một số giá trị mặc định thường gặp trong Eureka là:

| Cấu hình | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---:|---|
| eureka.instance.lease-renewal-interval-in-seconds | 30 giây | Chu kỳ client gửi heartbeat |
| eureka.instance.lease-expiration-duration-in-seconds | 90 giây | Thời gian lease không được gia hạn trước khi instance đủ điều kiện hết hạn |
| eureka.server.eviction-interval-timer-in-ms | 60000 ms | Chu kỳ server chạy tác vụ eviction |
| eureka.client.registry-fetch-interval-seconds | 30 giây | Chu kỳ client tải lại registry khi fetch được bật |

Các giá trị là mặc định phổ biến của Eureka; phiên bản Spring Cloud Netflix, cấu hình server/client và môi trường triển khai có thể thay đổi chúng. Hãy kiểm tra cấu hình thực tế thay vì xem đây là thời gian cố định cho mọi ứng dụng.

### Khi shutdown có kiểm soát

Khi Eureka Client còn hoạt động và shutdown đúng vòng đời, client có thể gửi yêu cầu cancel registration đến server. Server xóa instance khỏi registry mà không cần chờ lease expiration. Consumer vẫn có thể thấy instance cũ cho đến khi registry fetch và cache của load balancer được cập nhật.

### Khi process chết đột ngột

Không có heartbeat mới và cũng không có cancel registration. Server chỉ có thể coi lease đã hết hạn sau khoảng thời gian expiration. Tác vụ eviction chạy theo chu kỳ để loại các instance hết hạn. Vì vậy, độ trễ phát hiện có thể xấp xỉ lease expiration cộng thêm phần chờ eviction, rồi cộng propagation và cache phía consumer.

Eureka có cơ chế self-preservation. Khi số heartbeat giảm bất thường, server có thể tạm dừng eviction để tránh xóa hàng loạt instance do sự cố mạng diện rộng. Điều này bảo vệ registry khỏi false eviction nhưng cũng có thể làm instance đã chết còn xuất hiện lâu hơn. Không nên tắt self-preservation chỉ để làm dashboard xóa instance nhanh hơn nếu chưa đánh giá rủi ro của một network partition.

### Cấu hình liên quan

Ví dụ cấu hình client:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    registry-fetch-interval-seconds: 30
~~~

Ví dụ cấu hình server:

~~~yaml
eureka:
  server:
    eviction-interval-timer-in-ms: 60000
~~~

Đây là ví dụ thể hiện các mốc có thể cấu hình. Không giảm lease hoặc chu kỳ eviction quá thấp chỉ để rút ngắn thời gian phát hiện. Mạng chập chờn, CPU pause hoặc GC dài có thể khiến instance khỏe bị xem là mất. Chọn giá trị dựa trên độ trễ mạng, thời gian pause, tải hệ thống và mức chịu lỗi.

### Consumer còn cache instance cũ

Ngay cả khi Eureka Server đã xóa registration, consumer có thể chưa fetch registry mới. Spring Cloud LoadBalancer còn có thể cache danh sách ServiceInstance tùy cấu hình và phiên bản. Khi request tiếp tục đến địa chỉ đã chết, consumer cần timeout và chính sách retry phù hợp; retry chỉ nên tự động áp dụng cho thao tác có thể lặp an toàn.

## 5. Consul: health check và deregister critical service

Consul thường dùng health check để xác định service có đang passing hay không. Agent thực hiện HTTP, TCP, gRPC hoặc TTL check theo cấu hình. Khi check thất bại, trạng thái chuyển sang critical. Consumer có thể yêu cầu chỉ nhận instance passing, ví dụ qua Health API với tham số passing=1.

Có hai mốc cần phân biệt:

- **Không còn được chọn:** service chuyển critical và consumer chỉ truy vấn các instance passing.
- **Bị xóa registration:** service được deregister thủ công hoặc Consul tự deregister sau khi check critical liên tục đủ thời gian nếu đã cấu hình deregister_critical_service_after.

Ví dụ service registration:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 8080,
    "checks": [
      {
        "http": "http://10.20.1.15:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s",
        "DeregisterCriticalServiceAfter": "2m"
      }
    ]
  }
}
~~~

Trong ví dụ, agent kiểm tra mỗi 10 giây. Nếu check chuyển critical và duy trì liên tục đủ khoảng deregister đã cấu hình, Consul có thể tự gỡ service registration. Thời gian này không phải thời gian phát hiện đầu tiên; consumer dùng truy vấn passing=1 có thể ngừng nhận instance ngay khi trạng thái critical được ghi nhận.

deregister_critical_service_after là tùy chọn cấu hình cho check/service theo phiên bản Consul. Cần kiểm tra giới hạn duration, cú pháp và điều kiện áp dụng của phiên bản đang chạy. Nếu không cấu hình cơ chế này, trạng thái critical có thể tiếp tục tồn tại trong catalog cho đến khi được deregister hoặc xử lý bằng cơ chế cleanup khác.

### Khi Consul agent cũng chết

Nếu chỉ ứng dụng chết nhưng Consul agent còn sống, agent có thể tiếp tục chạy check và đánh dấu service critical. Nếu chính agent hoặc node bị mất, server phải phát hiện tình trạng node qua cơ chế membership/health của Consul. Thời gian phát hiện node không giống interval của HTTP check ứng dụng.

Với service registration gắn với agent, cần xác định ai chịu trách nhiệm đăng ký, check và deregister. Nếu ứng dụng đăng ký qua agent local, agent có thể giữ trạng thái local và đồng bộ với catalog; khi agent chết, việc dọn node/service phụ thuộc trạng thái node và cấu hình Consul. Không giả định deregister_critical_service_after thay thế mọi cơ chế phát hiện node mất.

### Theo dõi Consul

Có thể truy vấn service và health status qua HTTP API:

~~~bash
curl http://consul-server:8500/v1/health/service/inventory-service?passing=1
~~~

Kết quả chỉ gồm các instance đáp ứng điều kiện passing của truy vấn. Hãy so sánh Health API với Catalog API để phân biệt service còn registration nhưng critical với service đã bị xóa.

## 6. ZooKeeper: session timeout và ephemeral znode

ZooKeeper service discovery thường tạo ephemeral znode cho mỗi instance. Node này gắn với session tạo ra nó và tự bị xóa khi session kết thúc hoặc hết hạn.

### Khi shutdown có kiểm soát

Ứng dụng có thể chủ động xóa znode hoặc đóng ZooKeeper session. Khi server xử lý thao tác đó, ephemeral node được xóa và consumer nhận sự kiện thay đổi qua watcher/cache. Nếu ứng dụng dùng Curator Service Discovery hoặc Spring Cloud Zookeeper, cần hiểu lifecycle deregistration mà thư viện quản lý để tránh xóa node hai lần hoặc tự tạo registration thủ công trùng với auto-registration.

### Khi process chết hoặc mất mạng

Nếu JVM bị kill hoặc máy mất kết nối, ZooKeeper không thể biết ngay client đã chết. Session vẫn có thể tồn tại trong thời gian timeout. Client library có thể phát SUSPENDED khi mất kết nối; nếu session hết hạn, nó phát LOST. Khi session hết hạn, các ephemeral znode thuộc session cũ bị xóa.

Không có một giá trị timeout cố định áp dụng cho mọi cluster. Client yêu cầu session timeout; server thương lượng giá trị hợp lệ theo cấu hình min/max và tickTime của ensemble. Do đó, thời gian xóa ephemeral node phụ thuộc session timeout thực tế, thời điểm server phát hiện session hết hạn và thời gian consumer xử lý watcher/cache.

### Sau khi kết nối lại

Nếu client chỉ bị gián đoạn ngắn và session vẫn còn, nó có thể reconnect mà không cần tạo registration mới. Nếu session đã LOST, ephemeral node cũ đã bị xóa; ứng dụng phải tạo session mới và đăng ký lại node khi readiness cho phép. Consumer cũng cần xử lý cache cũ và watcher được đăng ký lại.

Không dùng persistent znode làm service registration mà không có cơ chế dọn dẹp. Persistent node không tự xóa khi session client kết thúc và có thể để lại địa chỉ instance cũ vô thời hạn.

## 7. So sánh thời gian phát hiện giữa các registry

| Registry | Graceful shutdown | Abrupt process stop | Điểm có thể kéo dài thời gian |
|---|---|---|---|
| Eureka | Client cancel registration; sau đó consumer cần refresh/cache expiry | Lease expiration rồi eviction | Self-preservation, eviction interval, registry fetch và LoadBalancer cache |
| Consul | Deregister service hoặc agent cập nhật catalog | Health check chuyển critical; có thể tự deregister sau duration đã cấu hình | Check interval/timeout, node health, deregister duration và consumer cache |
| ZooKeeper | Đóng session hoặc xóa ephemeral node | Session hết hạn mới xóa ephemeral node | Session timeout, reconnect, watcher propagation và consumer cache |

Không nên so sánh ba registry chỉ bằng một con số deregistration timeout. Eureka dựa trên heartbeat/lease và eviction; Consul dựa trên health check, catalog và tùy chọn critical deregistration; ZooKeeper dựa trên session và ephemeral node. Mỗi hệ thống có cách biểu diễn trạng thái và cơ chế cleanup riêng.

## 8. Thời gian registry xóa và thời gian consumer ngừng gọi

Một ví dụ minh họa với Eureka:

- Tại giây 0, inventory instance bị kill cưỡng bức.
- Server chưa nhận cancel registration.
- Lease còn hiệu lực trong một khoảng thời gian.
- Sau khi lease hết hạn, eviction task xử lý instance.
- Consumer tải registry mới theo chu kỳ.
- LoadBalancer cache được cập nhật hoặc hết TTL.
- Request mới không còn chọn instance cũ.

Giả sử cấu hình và cache khiến server xóa registration sau khoảng 90–150 giây, consumer refresh mỗi 30 giây và LoadBalancer cache còn hiệu lực thêm một khoảng thời gian, tổng thời gian consumer có thể tiếp tục thử instance cũ dài hơn thời gian registry xóa. Đây chỉ là ví dụ tính toán từ cấu hình giả định; self-preservation hoặc cache riêng có thể làm kết quả khác đáng kể.

Với Consul, một check chuyển critical có thể làm instance bị loại khỏi truy vấn passing=1 trước khi registration bị deregister. Với ZooKeeper, znode đã bị xóa nhưng consumer vẫn có thể giữ một danh sách instance cũ trong bộ nhớ đến khi watcher/cache cập nhật.

Do đó, cần đo cả **catalog removal time** và **last request to old instance time**. Hai metric này trả lời hai câu hỏi khác nhau.

## 9. Thiết kế graceful shutdown trong Spring Boot

Spring Boot hỗ trợ graceful shutdown cho embedded web server. Có thể bật trong cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Khi ApplicationContext đóng, server ngừng nhận kết nối mới theo khả năng của web server và chờ các request đang xử lý hoàn tất trong thời gian shutdown được cấp. Thời gian thực tế phụ thuộc server (Tomcat, Jetty, Reactor Netty), phiên bản Spring Boot và cấu hình lifecycle.

Graceful HTTP shutdown không tự bảo đảm mọi consumer đã cập nhật discovery. Cần phối hợp readiness và deregistration:

1. Đánh dấu instance không sẵn sàng nhận traffic mới.
2. Ngăn ingress/load balancer đưa request mới đến instance.
3. Thực hiện deregistration hoặc để discovery integration xử lý trong lifecycle shutdown.
4. Dành thời gian cho consumer refresh registry và cho request đang chạy drain.
5. Đóng HTTP server, executor, connection pool và các dependency theo thứ tự phù hợp.

Cấu hình auto-registration/deregistration khác nhau theo registry và phiên bản Spring Cloud. Với Eureka, kiểm tra hành vi shutdown của Eureka Client và thuộc tính liên quan như eureka.client.should-unregister-on-shutdown trong phiên bản đang dùng. Với Consul và ZooKeeper, kiểm tra service registry integration, auto-registration và thứ tự đóng client. Không giả định chỉ bật server.shutdown: graceful là đủ để xóa service khỏi registry.

Nếu ứng dụng tự quản lý readiness, hãy bảo đảm health endpoint và registry dùng cùng một trạng thái phục vụ. Nếu readiness DOWN nhưng registration vẫn tồn tại, consumer chỉ lọc passing/healthy mới tránh được instance đó; consumer không lọc health có thể vẫn gọi.

## 10. Orchestrator và thời gian termination

Container runtime và orchestrator có grace period riêng. Khi dừng container theo cách bình thường, runtime thường gửi SIGTERM trước và gửi SIGKILL sau khi hết thời gian chờ. Kubernetes dùng terminationGracePeriodSeconds; preStop hook chạy trong grace period đó, sau đó container nhận tín hiệu dừng theo cấu hình runtime.

Ví dụ Deployment:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory
          image: inventory-service:1.0
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

Ví dụ này chỉ minh họa một khoảng đệm trước khi process nhận tín hiệu dừng. sleep không tự deregister service và không bảo đảm endpoint đã biến mất khỏi mọi consumer. Trong thực tế, preStop có thể gọi endpoint nội bộ để đánh dấu readiness DOWN hoặc kích hoạt drain nếu ứng dụng cung cấp cơ chế đó. Lệnh phải phù hợp với image và không được vượt quá grace period.

Kubernetes loại Pod không ready khỏi các endpoint phù hợp, nhưng việc cập nhật EndpointSlice, kube-proxy, ingress, service mesh và discovery cache có độ trễ. Nếu đồng thời dùng Kubernetes Service và Spring Cloud registry, phải quyết định lớp nào chịu trách nhiệm chọn instance và drain traffic để tránh hai cơ chế cập nhật lệch nhau.

Thời gian termination grace phải đủ cho readiness/endpoint propagation, deregistration và discovery propagation nếu có, request đang xử lý hoàn tất, và đóng resource an toàn. Nếu tổng thời gian vượt grace period, runtime có thể kill process cưỡng bức và chuyển tình huống graceful thành abrupt.

## 11. Vì sao không nên giảm timeout quá thấp?

Giảm heartbeat interval, lease expiration, health check interval hoặc session timeout có thể làm phát hiện lỗi nhanh hơn, nhưng tăng nguy cơ false positive:

- GC pause hoặc CPU starvation làm heartbeat trễ.
- Network jitter khiến check timeout dù service vẫn khỏe.
- ZooKeeper leader election hoặc network partition tạm thời làm session gián đoạn.
- Consul agent bận hoặc dependency chậm khiến health check fail.
- Consumer refresh quá thường xuyên làm tăng tải registry và network.

Chọn timeout dựa trên độ trễ bình thường và các tình huống bất thường có thể chấp nhận. Có thể dùng nhiều tín hiệu: readiness nội bộ, health check từ agent, heartbeat/session và quan sát request thực tế. Không nên xóa instance chỉ vì một lần timeout ngắn nếu điều đó gây flapping liên tục.

## 12. Xử lý request trong khoảng stale registration

Ngay cả khi cấu hình registry tốt, vẫn có một khoảng thời gian consumer có thể chọn instance đã chết. Consumer cần xử lý tình huống này:

- Đặt connect timeout và response timeout phù hợp.
- Retry có giới hạn khi lỗi kết nối và có thể chọn instance khác.
- Chỉ retry tự động với thao tác idempotent hoặc có idempotency key.
- Dùng circuit breaker hoặc outlier detection nếu hệ thống cần ngăn liên tục chọn instance lỗi.
- Nếu danh sách instance rỗng, trả lỗi phụ thuộc dịch vụ có ý nghĩa thay vì loop vô hạn.
- Ghi log serviceId, instance address, lỗi kết nối và số lần retry.
- Không log token hoặc dữ liệu nhạy cảm.

Một lần connect refused có thể khiến LoadBalancer thử instance khác nếu retry integration được cấu hình. Tuy nhiên, không phải mọi lỗi HTTP đều nên retry: lỗi validation hoặc business rejection không trở thành thành công khi gửi lại request.

## 13. Đo thời gian deregistration trong môi trường lab

Có thể kiểm tra riêng từng mốc bằng một dịch vụ có endpoint trả về instance ID.

Ghi lại các timestamp:

| Mốc | Cách quan sát |
|---|---|
| T0 — process stop | Log shutdown hoặc thời điểm kill container |
| T1 — health failure/session loss | Log check status, Eureka lease/eviction hoặc Curator LOST |
| T2 — registry removal | Truy vấn Eureka/Consul/ZooKeeper và xác nhận record/node biến mất hoặc critical |
| T3 — consumer refresh | Log danh sách instance mà consumer nhận được |
| T4 — request cuối đến instance cũ | Log request tại provider hoặc client trace |

Tính các khoảng:

\[
T_{\text{detect}} = T_1 - T_0
\]

\[
T_{\text{registry}} = T_2 - T_1
\]

\[
T_{\text{consumer}} = T_3 - T_2
\]

\[
T_{\text{last-use}} = T_4 - T_0
\]

Với Consul, T2 nên ghi rõ “chuyển critical” hay “bị deregister”, vì hai mốc khác nhau. Với ZooKeeper, T2 là lúc ephemeral znode bị xóa; consumer có thể vẫn dùng cache cũ. Với Eureka, T2 là lúc instance không còn trong server registry, không phải lúc mọi consumer đã refresh xong.

Thực hiện hai bài test riêng:

1. **Graceful:** gửi SIGTERM hoặc chạy lệnh stop có grace period; xác nhận ứng dụng deregister, drain request và kết thúc.
2. **Abrupt:** kill cưỡng bức process trong môi trường lab; xác nhận registry phát hiện theo lease/check/session và đo thời gian consumer ngừng chọn.

Không thử nghiệm kill process hoặc làm mất mạng trên môi trường production. Thực hiện nhiều lần trong lab để thấy độ dao động thay vì kết luận từ một lần đo.

## 14. Checklist vận hành

Trước khi triển khai service discovery, xác nhận:

1. Ứng dụng có shutdown hook và deregistration khi nhận SIGTERM.
2. HTTP server có graceful shutdown và timeout phù hợp.
3. Readiness được hạ trước khi instance ngừng nhận request.
4. Registry có cơ chế phát hiện process chết hoặc node mất.
5. Eureka lease/eviction, Consul check/deregister, hoặc ZooKeeper session timeout được hiểu và cấu hình phù hợp.
6. Consumer cập nhật registry/cache và không dùng instance cũ vô thời hạn.
7. Retry, timeout và circuit breaker không tạo tác dụng phụ cho request ghi.
8. Orchestrator grace period đủ cho drain và shutdown.
9. Metrics tách catalog removal time khỏi last request to old instance.
10. Đã kiểm thử graceful stop, abrupt kill và network partition trong môi trường phù hợp.
11. Có cảnh báo khi registration tồn tại nhưng endpoint không thể truy cập.
12. Có quy trình phục hồi khi instance khởi động lại và đăng ký lại.

Điểm cần nhớ là: **graceful shutdown có thể deregister chủ động; abrupt shutdown buộc registry phát hiện instance mất qua heartbeat, health check hoặc session timeout; consumer còn cần refresh dữ liệu và hết cache cũ trước khi ngừng gửi request.** Vì thế, thời gian loại bỏ registration và thời gian traffic thực sự dừng phải được đo và thiết kế riêng.

