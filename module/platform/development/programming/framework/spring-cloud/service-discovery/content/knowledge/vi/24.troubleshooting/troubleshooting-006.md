# Instance đã tắt nhưng vẫn xuất hiện trong kết quả khám phá

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt registration còn tồn tại trong registry với dữ liệu cũ trong cache của consumer.
- Xác định nguyên nhân instance đã dừng nhưng vẫn được trả về qua Eureka, Consul, ZooKeeper hoặc Kubernetes.
- Hiểu thời điểm cleanup theo lease, health check, session timeout và Pod termination.
- Kiểm tra trạng thái ở registry gốc, client cache, LoadBalancer và DNS.
- Xử lý instance cũ mà không xóa nhầm một replica đang hoạt động.
- Thiết kế graceful shutdown, health check, timeout và giám sát để giảm thời gian stale discovery.

## 1. Một instance đã tắt không nhất thiết biến mất ngay khỏi discovery

Khi một process dừng, nhiều thành phần vẫn có thể giữ thông tin về instance đó:

1. **Process:** ứng dụng đã thoát hoặc container đã dừng.
2. **Provider registration:** bản ghi đăng ký của instance vẫn còn trong registry.
3. **Registry view:** registry server hoặc agent vẫn trả về bản ghi đó.
4. **Consumer cache:** DiscoveryClient hoặc thư viện discovery đã lưu danh sách instance cũ.
5. **Load balancer / DNS cache:** tầng định tuyến còn giữ endpoint hoặc địa chỉ đã phân giải trước đó.

Vì vậy, cần xác định chính xác tầng nào đang chứa dữ liệu cũ. Nếu registry đã xóa registration nhưng consumer vẫn trả instance, xóa lại bản ghi ở server không giải quyết được cache. Ngược lại, nếu registry gốc vẫn trả instance thì refresh consumer cache chỉ tải lại cùng một bản ghi.

### Phân biệt năm trạng thái

| Trạng thái | Ý nghĩa | Cách xác minh |
| --- | --- | --- |
| Process stopped | JVM/container không còn chạy. | Process table, container runtime, Pod/container status. |
| Endpoint unreachable | Địa chỉ/port không còn phục vụ kết nối. | Kết nối trực tiếp tới host và port, xem timeout/refused. |
| Registration stale | Registry vẫn lưu instance dù process đã dừng. | Truy vấn trực tiếp registry server/agent. |
| Health not passing | Instance còn registration nhưng health check đã báo lỗi. | Xem trạng thái và output của check. |
| Consumer cache stale | Registry gốc đã cập nhật nhưng consumer vẫn giữ endpoint cũ. | So sánh registry API với kết quả DiscoveryClient tại consumer. |

Không kết luận registration bị lỗi chỉ vì một request tới endpoint thất bại. Có thể process đã dừng nhưng lease chưa hết hạn; cũng có thể registry đã sạch nhưng consumer chưa refresh cache.

## 2. Các nguyên nhân thường gặp

### 2.1. Process dừng đột ngột, không deregister

Khi ứng dụng shutdown bình thường, framework thường có cơ hội gửi yêu cầu deregister. Nếu process bị kill cưỡng bức, máy ảo hoặc node mất điện, network bị partition, hoặc JVM bị crash, shutdown hook có thể không chạy. Registry phải chờ lease, TTL hoặc session timeout trước khi xóa registration.

### 2.2. Health check chưa đủ thời gian để đánh dấu lỗi

Health check thường chạy theo chu kỳ. Nếu check interval là 10 giây và yêu cầu nhiều lần thất bại liên tiếp, instance có thể vẫn ở trạng thái passing trong một khoảng thời gian sau khi process dừng.

Một số registry chỉ đánh dấu instance critical; chúng không tự xóa registration ngay khi check thất bại. Việc xóa có thể cần cấu hình cleanup riêng.

### 2.3. Registry bảo vệ dữ liệu khi mất kết nối diện rộng

Eureka có self-preservation. Khi số heartbeat thấp hơn ngưỡng dự kiến, server có thể ngừng eviction để tránh xóa hàng loạt instance chỉ vì network partition. Trong tình huống này, các instance đã chết vẫn có thể nằm trong registry.

### 2.4. Registry và consumer có cache riêng

Eureka có server response cache và client registry cache. Consul có agent-local state và catalog toàn cụm. ZooKeeper client có thể duy trì cache/watch. Spring Cloud LoadBalancer cũng có thể có cache riêng. Mỗi tầng có chu kỳ cập nhật khác nhau.

### 2.5. Bản ghi được tạo thủ công hoặc dùng sai loại registration

Một service có thể được đăng ký bằng file cấu hình agent, CLI, script hoặc một controller bên ngoài. Nếu process dừng nhưng registration là persistent/static, registry không có tín hiệu tự động để xóa nó.

Trong ZooKeeper, nếu dùng persistent znode thay vì ephemeral znode, node sẽ không tự biến mất khi session kết thúc.

### 2.6. Service ID hoặc instance ID bị trùng

Nếu nhiều process dùng cùng instance ID, một lần deregister từ process cũ có thể ảnh hưởng tới registration của process mới; hoặc một bản ghi cũ có thể bị nhầm là replica hiện tại. Hãy đối chiếu service ID, instance ID, host, port, node và thời điểm đăng ký.

## 3. Quy trình chẩn đoán: tìm tầng chứa bản ghi cũ

Luôn kiểm tra từ registry gốc ra consumer, theo thứ tự:

~~~~mermaid
flowchart TD
    A[Instance được cho là đã dừng] --> B[Kiểm tra process/container/Pod]
    B --> C[Thử kết nối trực tiếp tới endpoint]
    C --> D[Truy vấn registry gốc]
    D --> E{Registry còn trả instance?}
    E -- Có --> F[Kiểm tra lease, health check, session hoặc endpoint controller]
    E -- Không --> G[Kiểm tra DiscoveryClient cache]
    G --> H[Kiểm tra LoadBalancer / DNS / service mesh cache]
    F --> I[Cleanup đúng instance và xác minh propagation]
    H --> J[Refresh cache theo cơ chế hỗ trợ]
    I --> K[Consumer không còn chọn endpoint cũ]
    J --> K
~~~~

### Bước 1: xác minh instance thực sự đã dừng

Kiểm tra process, container hoặc Pod theo đúng runtime. Đối chiếu cả IP và port được registry công bố. Nếu có thể, gọi trực tiếp endpoint để phân biệt:

- **Connection refused:** host còn phản hồi nhưng không có process lắng nghe port.
- **Timeout:** có thể host/network không truy cập được hoặc firewall đang drop traffic.
- **HTTP response:** có thể IP đã được tái sử dụng bởi một process khác; xác minh danh tính service trước khi kết luận.

Đừng chỉ dựa vào tên host. IP có thể được tái sử dụng cho Pod mới hoặc máy mới.

### Bước 2: truy vấn registry gốc

Dùng giao diện/API/CLI trực tiếp của registry, tránh chỉ xem dashboard hoặc log từ consumer. Ghi lại service ID, instance ID, địa chỉ, port, trạng thái health và metadata.

### Bước 3: so sánh với kết quả từ consumer

Tại consumer, ghi lại kết quả DiscoveryClient.getInstances(serviceId) và thời điểm lần refresh gần nhất. Nếu registry đã xóa bản ghi nhưng consumer vẫn thấy, kiểm tra:

- Registry fetch interval.
- Client-side cache hoặc informer/watch.
- Spring Cloud LoadBalancer cache.
- Service mesh endpoint cache.
- DNS resolver và JVM DNS cache nếu dùng hostname/headless Service.

### Bước 4: chỉ cleanup sau khi xác minh danh tính

Trước khi xóa thủ công, xác nhận instance ID/Pod UID/host-port thực sự thuộc process đã dừng. Nếu instance mới đã tái sử dụng cùng địa chỉ hoặc ID, thao tác xóa có thể loại nhầm replica khỏe mạnh.

## 4. Eureka: lease expiration, self-preservation và cache

Eureka client gửi heartbeat để gia hạn lease. Theo cấu hình mặc định phổ biến của Spring Cloud Netflix, client renew khoảng 30 giây một lần và server chờ khoảng 90 giây kể từ heartbeat cuối trước khi có thể loại instance khỏi registry. Các giá trị này có thể thay đổi theo phiên bản và cấu hình hiệu lực. Hãy kiểm tra **eureka.instance.lease-renewal-interval-in-seconds** và **eureka.instance.lease-expiration-duration-in-seconds**.

Nếu ứng dụng shutdown bình thường, Eureka client gửi cancel/unregister. Khi process bị kill -9, crash hoặc mất kết nối trước khi gửi cancel, server phải đợi lease hết hạn. Sau đó eviction vẫn cần chạy và dữ liệu phải đi qua response cache và client fetch cycle. [Spring Cloud Netflix properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html) mô tả lease và chu kỳ fetch; tài liệu Netflix cũng giải thích cancel, renew và registry cache.

### Self-preservation có thể giữ instance đã chết

Eureka server bật self-preservation mặc định trong cấu hình hiện hành. Khi số heartbeat nhận được thấp hơn renewal threshold, server có thể ngừng expiration/eviction để bảo vệ registry khỏi một network partition diện rộng. Điều này có thể khiến client tiếp tục nhận endpoint của instance không còn tồn tại. Đây là hành vi bảo vệ có chủ đích, không nhất thiết là lỗi của eviction scheduler. [Netflix Eureka – Server Self Preservation](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode).

Khi thấy stale instance:

1. Kiểm tra renewal count và renewal threshold.
2. Xác nhận server có đang ở self-preservation mode hay không.
3. Kiểm tra network giữa client và Eureka server; heartbeat có thể mất dù process còn sống.
4. Kiểm tra instance có gửi cancel khi graceful shutdown hay không.
5. Kiểm tra lease expiration và eviction interval thực tế.
6. Kiểm tra peer replication nếu các Eureka server trả registry view khác nhau.

Không tắt self-preservation như phản xạ đầu tiên. Nếu nguyên nhân là network partition, tắt cơ chế này có thể làm registry xóa hàng loạt instance khỏe mạnh nhưng tạm thời không gửi heartbeat.

### Registry cache làm stale kéo dài thêm

Eureka có nhiều tầng cache:

- Server response cache cập nhật theo chu kỳ.
- Client fetch registry định kỳ, thường có mặc định 30 giây.
- Consumer có thể tiếp tục dùng cache cũ trong lúc fetch thất bại.
- LoadBalancer có thể có cache riêng phía trên Eureka client.

**eureka.client.filter-only-up-instances** mặc định là true trong config properties hiện hành, giúp lọc các instance không ở trạng thái UP. Tuy nhiên, nếu server vẫn giữ instance stale với status UP, bộ lọc này không thể biết process đã chết.

Ví dụ cấu hình client:

~~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
    filter-only-up-instances: true
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~~

Đây là các giá trị minh họa theo mặc định thường gặp, không phải khuyến nghị thay đổi tùy tiện. Giảm lease timeout có thể làm instance bị loại khi network hoặc GC pause tạm thời. Hãy căn chỉnh heartbeat, lease, eviction và cache theo SLO, sau khi kiểm thử failure mode.

### Kiểm tra

Có thể truy vấn Eureka REST API để xem trạng thái registration ở server:

~~~~bash
curl -H "Accept: application/json" \
  http://eureka-server:8761/eureka/apps/INVENTORY-SERVICE
~~~~

Đối chiếu instanceId, hostName, ipAddr, port, status và metadata. Nếu server đã không còn instance nhưng consumer vẫn trả về, tập trung vào client fetch cache và LoadBalancer cache. Nếu server còn trả status UP, kiểm tra lease/self-preservation và deregistration.

## 5. Consul: health check, critical duration và agent/catalog

Consul có sự khác biệt giữa service được đăng ký trên local agent và service catalog toàn cụm. Agent quản lý service/check local và đồng bộ thông tin lên catalog. Cơ chế anti-entropy định kỳ đối chiếu local agent state với catalog. Vì vậy, cần xác định bản ghi đang tồn tại ở agent nào và catalog nào. [Consul – Consistency](https://developer.hashicorp.com/consul/docs/concept/consistency).

### Critical không có nghĩa là đã bị xóa

Khi health check chuyển sang critical, service có thể vẫn còn trong catalog. Muốn Consul tự deregister service sau một khoảng critical, cấu hình check với **deregister_critical_service_after**. Consul chỉ tự xóa khi trạng thái critical kéo dài đủ thời gian đã cấu hình; chu kỳ reap có thể khiến thao tác xóa trễ thêm một khoảng. [Consul – Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check).

Ví dụ service definition:

~~~~yaml
service:
  name: inventory
  id: inventory-node-a-8080
  port: 8080
  checks:
    - name: inventory-http
      http: http://127.0.0.1:8080/actuator/health
      interval: 10s
      timeout: 2s
      deregister_critical_service_after: 5m
~~~~

5m chỉ là giá trị minh họa. Chọn thời gian dài hơn các gián đoạn có thể phục hồi bình thường nhưng đủ ngắn để không giữ endpoint chết quá lâu. Một check HTTP/TCP/TTL phải thực sự giám sát process hoặc khả năng phục vụ; check chỉ kiểm tra một cổng trung gian còn mở có thể không phát hiện ứng dụng đã hỏng.

Với TTL check, ứng dụng/agent phải cập nhật trạng thái trước khi TTL hết. Nếu không có update trong TTL, check chuyển sang critical. [Consul – TTL Checks](https://developer.hashicorp.com/consul/docs/register/health-check/vm).

### Đối chiếu agent và catalog

Dùng Health API để lấy instance cùng trạng thái check:

~~~~bash
curl -s "http://consul-agent:8500/v1/health/service/inventory"
~~~~

Chỉ lấy instance passing:

~~~~bash
curl -s "http://consul-agent:8500/v1/health/service/inventory?passing"
~~~~

Đối chiếu với catalog:

~~~~bash
curl -s "http://consul-agent:8500/v1/catalog/service/inventory"
~~~~

Nếu service có trong catalog nhưng check critical, đây là registration còn tồn tại nhưng không healthy. Nếu service chỉ còn ở local agent, kiểm tra cấu hình agent, file service definition và anti-entropy. Nếu đã bị xóa khỏi agent/catalog nhưng consumer vẫn thấy, kiểm tra cache hoặc query consistency mode của client.

Các service được đăng ký bằng CLI hoặc agent configuration có thể tồn tại qua lần restart agent nếu state/config vẫn được giữ. Không giả định rằng process nghiệp vụ dừng thì Consul agent sẽ tự xóa mọi service entry. [Consul – Services Register](https://developer.hashicorp.com/consul/commands/services/register).

### Deregister đúng nơi

Khi service được đăng ký thông qua local agent, ưu tiên deregister qua chính agent đó để agent cập nhật catalog:

~~~~bash
curl -X PUT \
  http://consul-agent:8500/v1/agent/service/deregister/inventory-node-a-8080
~~~~

Chỉ thực hiện sau khi xác nhận service ID không còn thuộc process đang hoạt động. Với Spring Cloud Consul, kiểm tra lifecycle deregistration và cấu hình health check; không xóa trực tiếp catalog entry nếu agent vẫn xem service là authoritative vì anti-entropy có thể đăng ký lại.

## 6. ZooKeeper: session và ephemeral znode

Spring Cloud Zookeeper thường dùng Curator để tạo registration node trong ZooKeeper. Nếu registration được tạo dưới dạng ephemeral znode, node tồn tại trong suốt session đã tạo nó. Khi session kết thúc hoặc hết hạn, ZooKeeper xóa ephemeral node. [ZooKeeper Programmer's Guide – Ephemeral Nodes](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html).

### Vì sao process chết mà znode vẫn còn?

Khi JVM crash hoặc máy mất mạng, client không thể gửi close session. ZooKeeper server phải đợi cho tới khi session timeout được thương lượng hết hạn. Mất TCP connection không đồng nghĩa session đã hết hạn: client có thể kết nối lại với session cũ trước timeout và tiếp tục giữ ephemeral znode.

Do đó, thời gian tồn tại stale có thể gần bằng session timeout, cộng với thời gian consumer nhận watch event và làm mới cache. Nếu session chưa hết hạn, việc node vẫn xuất hiện là hành vi đúng theo session semantics.

### Kiểm tra znode

Kết nối bằng ZooKeeper CLI:

~~~~bash
zkCli.sh -server zk-1:2181
~~~~

Liệt kê registration:

~~~~text
ls /services/inventory
~~~~

Kiểm tra metadata và stat của một instance:

~~~~text
get -s /services/inventory/inventory-node-a
~~~~

Xem **ephemeralOwner** trong stat:

- **ephemeralOwner khác 0:** node thuộc một session và sẽ bị xóa khi session kết thúc.
- **ephemeralOwner bằng 0:** node là persistent; nó không tự xóa theo session.

Nếu node vẫn tồn tại sau khi session đã hết hạn, kiểm tra node có phải persistent, có registration trùng path hoặc có một client/session khác đang sở hữu nó không. Không xóa node bằng tay trước khi xác minh ephemeralOwner và session liên quan.

### Phục hồi và cache

Sau khi session hết hạn, client phải tạo session mới và tạo lại registration. Watcher/cache phía consumer cần nhận sự kiện node deletion hoặc đồng bộ lại dữ liệu. Nếu consumer chỉ dựa vào local cache mà không xử lý reconnect/session state đúng cách, kết quả discovery có thể cũ dù znode đã bị xóa.

Không rút ngắn session timeout quá mức chỉ để xóa instance nhanh. Network jitter, GC pause hoặc server failover có thể làm session của instance khỏe mạnh hết hạn, dẫn tới xóa registration và tạo churn.

## 7. Kubernetes: Pod termination và EndpointSlice

Với Kubernetes, cần phân biệt Pod object, container process, Service và EndpointSlice. Khi Pod bị xóa, control plane đánh dấu Pod đang terminating và cập nhật endpoint state. Endpoint đại diện cho Pod terminating không bị xóa ngay lập tức khỏi EndpointSlice; trạng thái terminating được công bố để consumer/load balancer xử lý quá trình drain. Endpoint terminating có ready=false để tương thích ngược. [Kubernetes – Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/).

EndpointSlice có ba condition:

- **ready:** shortcut cho endpoint đang serving và chưa terminating, ngoại trừ trường hợp publishNotReadyAddresses.
- **serving:** endpoint có đang phục vụ hay không.
- **terminating:** endpoint đang trong quá trình kết thúc.

Service proxy thường bỏ qua endpoint terminating, nhưng trong một số tình huống tất cả endpoint đều terminating, proxy có thể tiếp tục chọn endpoint vừa serving vừa terminating để tránh mất toàn bộ traffic trong rolling update. [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

### Các nguyên nhân Kubernetes hay gặp

1. **Pod đang Terminating:** EndpointSlice vẫn giữ endpoint trong giai đoạn graceful shutdown.
2. **Container process đã chết nhưng Pod object còn:** controller chưa xóa Pod; readiness/container state cần được kiểm tra.
3. **Readiness probe thiếu hoặc sai:** Pod có thể được đánh dấu Ready dù ứng dụng không còn phục vụ đúng.
4. **publishNotReadyAddresses: true:** Kubernetes coi endpoint là ready ngay cả khi Pod chưa ready. Đây thường là chủ đích với Headless Service cho StatefulSet peer discovery.
5. **Service không có selector:** endpoint được quản lý bởi hệ thống bên ngoài; Kubernetes không tự sửa EndpointSlice cho Service đó.
6. **EndpointSlice do controller khác quản lý:** service mesh hoặc controller tùy chỉnh có thể giữ endpoint riêng.
7. **Cache DNS:** headless Service có thể trả Pod IP; resolver/client có thể còn giữ địa chỉ cũ trong TTL/cache.

### Kiểm tra Pod, Service và EndpointSlice

~~~~bash
kubectl get pods -n commerce -o wide
kubectl describe pod inventory-7c8f9d9c7b-abcd1 -n commerce
kubectl get service inventory -n commerce -o yaml
kubectl get endpointslice -n commerce \
  -l kubernetes.io/service-name=inventory -o yaml
~~~~

Đối chiếu các trường:

- Pod metadata.deletionTimestamp, status.phase, status.containerStatuses.
- Service spec.selector và spec.publishNotReadyAddresses.
- EndpointSlice addresses, targetRef, conditions.ready, conditions.serving, conditions.terminating.
- Label endpointslice.kubernetes.io/managed-by để biết controller nào quản lý slice.

Nếu Pod object đã bị xóa nhưng endpoint vẫn còn trong một EndpointSlice do controller tùy chỉnh quản lý, cần điều tra controller đó. Nếu EndpointSlice đã sạch nhưng ứng dụng vẫn thấy IP cũ, kiểm tra DNS cache, informer/watch hoặc LoadBalancer cache.

### ClusterIP và Headless Service khác nhau

Với ClusterIP Service, DNS trả về địa chỉ Service ổn định. Địa chỉ này vẫn có thể phân giải được khi không còn Pod backend. Điều đó không có nghĩa một Pod cũ vẫn còn trong discovery; hãy kiểm tra EndpointSlice để biết backend thực tế.

Với Headless Service (clusterIP: None), DNS có thể trả địa chỉ của từng Pod. Khi Pod bị xóa hoặc endpoint thay đổi, resolver hoặc client DNS cache có thể còn giữ IP cũ trong một khoảng thời gian. Cũng cần kiểm tra publishNotReadyAddresses, đặc biệt với StatefulSet peer discovery.

## 8. Consumer cache và LoadBalancer cache

Nếu registry gốc đã xóa instance nhưng consumer vẫn thấy nó, kiểm tra từng lớp cache theo thứ tự:

| Lớp | Dữ liệu có thể còn cũ | Cách kiểm tra |
| --- | --- | --- |
| Registry server response cache | Payload trả về vẫn chưa phản ánh thay đổi mới nhất. | So sánh API trực tiếp và thời điểm cache update. |
| DiscoveryClient | Danh sách instance lưu cục bộ. | Kiểm tra fetch interval, watch/reconnect và lần refresh cuối. |
| Spring Cloud LoadBalancer | Danh sách ServiceInstance đã cache. | Kiểm tra ServiceInstanceListSupplier, cache TTL và cấu hình của phiên bản. |
| Service mesh / proxy | Cluster endpoint từ control plane. | Kiểm tra endpoint/cluster dump và xDS update time. |
| DNS resolver | A/AAAA/SRV record hoặc Pod IP cũ. | Truy vấn DNS từ chính môi trường consumer và xem TTL. |
| JVM DNS cache | Kết quả resolve hostname còn được giữ trong JVM. | Kiểm tra DNS cache policy và resolver đang dùng. |

Không restart toàn bộ consumer ngay khi phát hiện stale instance. Trước hết, xác định cache nào đang giữ endpoint cũ và liệu cache có tự refresh được không. Restart hàng loạt có thể tạo tải lên registry và gây mất ổn định nếu registry đang phục hồi.

Với Eureka, config properties hiện hành ghi eureka.client.registry-fetch-interval-seconds mặc định là 30 giây; server response cache cũng có chu kỳ cập nhật riêng. Client chỉ biết thay đổi sau khi dữ liệu đi qua các chu kỳ này. Đừng dùng một con số cố định làm cam kết propagation cho mọi version/topology.

## 9. Graceful shutdown để tránh stale registration

Khi ứng dụng dừng bình thường, nên chủ động rút instance khỏi traffic và deregister trước khi process biến mất.

Trình tự gợi ý:

1. Chuyển readiness sang REFUSING_TRAFFIC hoặc trạng thái tương đương.
2. Ngừng nhận request mới và bắt đầu drain request đang chạy.
3. Gửi deregistration/cancel tới registry nếu kết nối còn hoạt động.
4. Chờ propagation đủ để consumer/load balancer cập nhật.
5. Đóng HTTP server, worker và các kết nối ứng dụng.
6. Kết thúc process trong termination grace period.

Với Spring Boot:

~~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~~

Trong Kubernetes, terminationGracePeriodSeconds cần đủ cho preStop hook, propagation và shutdown phase. Nếu thời gian quá ngắn, kubelet có thể gửi SIGKILL trước khi ứng dụng hoàn tất deregistration.

Graceful shutdown không bảo vệ được trường hợp mất điện, kill -9, node crash hoặc network partition. Lease, health check, session timeout và readiness vẫn cần được cấu hình hợp lý để xử lý các sự cố không graceful.

## 10. Cách xử lý theo từng registry

| Registry | Khi process dừng đột ngột | Hành động ưu tiên |
| --- | --- | --- |
| Eureka | Server chờ lease expiration; self-preservation có thể trì hoãn eviction. | Kiểm tra heartbeat, self-preservation, eviction, response cache và client fetch cache. |
| Consul | Health check chuyển critical; service có thể còn catalog nếu chưa cấu hình critical cleanup. | Kiểm tra local agent, health check, deregister_critical_service_after và anti-entropy. |
| ZooKeeper | Ephemeral znode tồn tại tới khi session kết thúc/hết hạn. | Kiểm tra session state, timeout và ephemeralOwner. |
| Kubernetes | Pod terminating và endpoint propagation diễn ra theo lifecycle/controller. | Kiểm tra Pod deletion timestamp, readiness, EndpointSlice conditions và selector. |
| DNS / Headless Service | DNS cache có thể còn giữ Pod IP cũ. | Kiểm tra record, TTL, resolver và JVM cache. |

Không áp dụng cùng một thao tác cleanup cho tất cả registry. Xóa thủ công ở một tầng có thể bị agent/controller khác tạo lại nếu nguồn authoritative vẫn còn bản ghi.

## 11. Quy trình xử lý sự cố end-to-end

Khi consumer tiếp tục gọi một instance đã dừng, thực hiện:

1. **Ghi nhận danh tính:** service ID, instance ID, host/IP, port, namespace, Pod UID hoặc ZooKeeper path.
2. **Xác minh process:** process/container/Pod còn chạy không; thời điểm dừng chính xác.
3. **Thử endpoint trực tiếp:** phân biệt connection refused, timeout và response từ một process mới.
4. **Truy vấn registry gốc:** kiểm tra raw record, health, lease/session và timestamp.
5. **Nếu registry còn record:** xử lý cleanup theo cơ chế registry; kiểm tra shutdown hook, check, lease, session hoặc controller.
6. **Nếu registry đã sạch:** truy vấn DiscoveryClient tại consumer; xác định cache nào còn endpoint cũ.
7. **Nếu LoadBalancer/DNS còn stale:** refresh cache theo cơ chế hỗ trợ hoặc đợi TTL; kiểm tra resolver và service mesh.
8. **Xác minh không còn traffic:** theo dõi request log/metrics của instance và consumer.
9. **Theo dõi tái diễn:** tìm process nào đăng ký lại ID cũ hoặc controller nào tạo lại endpoint.

### Điều kiện hoàn tất

- Registry gốc không còn trả instance đã dừng, hoặc trả trạng thái không được chọn theo policy.
- Consumer không còn chọn endpoint cũ sau thời gian propagation đã đo.
- LoadBalancer và DNS không còn trỏ tới địa chỉ cũ nếu chúng công bố endpoint trực tiếp.
- Không có registration mới được tạo lại từ agent/config/controller ngoài dự kiến.
- Các replica còn sống vẫn được giữ trong registry và tiếp tục nhận traffic.

## 12. Metrics và cảnh báo nên có

Theo dõi riêng:

- Thời gian từ lúc process dừng tới lúc registration bị xóa.
- Thời gian từ lúc registry xóa record tới lúc consumer ngừng trả instance.
- Số registration có heartbeat/renewal quá hạn.
- Số instance ở trạng thái critical, OUT_OF_SERVICE, terminating hoặc session LOST.
- Số lần deregistration thất bại và cleanup retry.
- Tuổi của cache discovery tại consumer.
- Tỷ lệ request tới endpoint trả connection refused hoặc timeout.
- Số endpoint trong EndpointSlice so với số Pod Ready.
- Số znode registration persistent bất thường nếu thiết kế yêu cầu ephemeral.

Một metric hữu ích là stale-selection rate: số request được gửi tới instance đã xác minh là không còn sống chia cho tổng request được định tuyến. Kết hợp metric này với timestamp deregistration và cache refresh để xác định thời gian hội tụ thực tế.

## 13. Kiểm thử tình huống stale instance

| Thí nghiệm | Điều cần quan sát |
| --- | --- |
| Graceful shutdown | Registry nhận deregistration; consumer ngừng chọn instance sau propagation. |
| SIGKILL / process crash | Registry cleanup diễn ra theo lease, check hoặc session timeout. |
| Mất network giữa provider và registry | Phân biệt process còn sống với heartbeat/session bị mất. |
| Eureka renewal giảm trên diện rộng | Self-preservation có bật và stale lease có bị giữ lại không. |
| Consul health check critical | Service có bị deregister sau critical duration hay vẫn nằm trong catalog. |
| ZooKeeper client disconnect lâu hơn session timeout | Ephemeral znode bị xóa và consumer nhận watch/update. |
| Pod Terminating với preStop | EndpointSlice đánh dấu terminating/ready false; request đang chạy được drain. |
| publishNotReadyAddresses bật | Endpoint có thể được công bố ready dù Pod chưa Ready. |
| Headless Service DNS cache | Resolver có còn trả Pod IP đã xóa không. |
| Consumer cache không refresh | Registry sạch nhưng DiscoveryClient/LoadBalancer còn trả instance cũ bao lâu. |

Ghi timestamp cho các mốc: process stopped, health failed, lease/session expired, registry record removed, client cache updated và last request to stale endpoint. Khi đó có thể tách thời gian cleanup của registry khỏi thời gian hội tụ của consumer.

## 14. Checklist phòng ngừa

- [ ] Instance ID duy nhất và ổn định trong một vòng đời process.
- [ ] Graceful shutdown chuyển readiness sang từ chối traffic trước khi deregister.
- [ ] Shutdown hook không bị bỏ qua trong container/process lifecycle.
- [ ] Lease/heartbeat phù hợp với network jitter và GC pause.
- [ ] Eureka self-preservation được giám sát; không tắt chỉ để ép eviction nhanh.
- [ ] Consul có health check thực sự kiểm tra process/service và cấu hình critical cleanup phù hợp.
- [ ] ZooKeeper registration dùng ephemeral znode nếu cần tự xóa theo session.
- [ ] Session timeout không quá dài hoặc quá ngắn so với failure model.
- [ ] Kubernetes có readiness probe phù hợp và termination grace period đủ dài.
- [ ] publishNotReadyAddresses chỉ bật khi có chủ đích.
- [ ] Service không selector có quy trình quản lý EndpointSlice bên ngoài.
- [ ] DiscoveryClient, LoadBalancer, service mesh và DNS cache có TTL/refresh được hiểu rõ.
- [ ] Có metric cho stale record, deregistration delay và stale selection.
- [ ] Runbook so sánh registry gốc với kết quả ở consumer trước khi xóa thủ công.
- [ ] Có kiểm thử cả graceful shutdown và abrupt failure.

## Ghi nhớ

- Process dừng không đồng nghĩa registry record bị xóa ngay.
- Phải phân biệt registry stale với consumer cache stale.
- Eureka có lease expiration và self-preservation; heartbeat bị mất diện rộng có thể khiến server giữ instance.
- Consul có thể giữ service ở trạng thái critical; chỉ deregister tự động khi cấu hình critical duration.
- ZooKeeper xóa ephemeral znode khi session kết thúc, không phải ngay khi TCP disconnect.
- Kubernetes giữ terminating endpoint trong EndpointSlice trong quá trình Pod shutdown; publishNotReadyAddresses có thể làm endpoint được xem là ready.
- ClusterIP DNS ổn định không chứng minh backend Pod còn tồn tại; hãy kiểm tra EndpointSlice.
- Dùng graceful shutdown để deregister sớm, nhưng vẫn cần lease/health/session cleanup cho crash và network partition.
- Chỉ xóa thủ công sau khi xác minh chính xác instance ID, Pod UID hoặc znode owner.
- Đo riêng thời gian cleanup ở registry và thời gian cache consumer hội tụ.

## Tài liệu tham khảo chính thức

- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix – Eureka Features](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Server Self Preservation](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Netflix Eureka – Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Consul – Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [Consul – Agent Check API](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [Consul – Service Registration and Deregistration](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul – Consistency and Anti-Entropy](https://developer.hashicorp.com/consul/docs/concept/consistency)
- [Apache ZooKeeper – Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Kubernetes – Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes – Service API and publishNotReadyAddresses](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/)
