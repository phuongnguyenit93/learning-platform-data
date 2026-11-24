# Lập kế hoạch dung lượng, độ sẵn sàng và nâng cấp sổ đăng ký

## Mục tiêu

Sau bài học này, bạn có thể:

- Ước lượng tải registry từ số lượng instance, heartbeat, lookup, metadata và tốc độ thay đổi topology.
- Chọn kiến trúc có độ sẵn sàng phù hợp với Eureka, Consul, ZooKeeper hoặc Kubernetes.
- Phân biệt mô hình peer replication của Eureka với quorum/consensus của Consul, ZooKeeper và etcd.
- Đặt SLO, RTO, RPO và kiểm tra khả năng phục hồi khi registry hoặc một failure domain bị mất.
- Lập kế hoạch backup, restore, rolling upgrade và tương thích giữa server, client, Spring Boot và Spring Cloud.
- Kiểm chứng dung lượng và quy trình nâng cấp bằng tải thử, canary và diễn tập sự cố.

## 1. Registry là hạ tầng quan trọng, nhưng mỗi loại có cách vận hành khác nhau

Service registry lưu hoặc cung cấp thông tin để consumer tìm instance của service. Tùy công nghệ, registry có thể lưu registration trong bộ nhớ, nhân bản giữa các peer, ghi vào log consensus hoặc dựa vào Kubernetes API.

Không thể dùng cùng một công thức triển khai cho mọi registry:

| Registry | Mô hình lưu trữ/đồng bộ chính | Thành phần ảnh hưởng trực tiếp đến availability |
| --- | --- | --- |
| Eureka | Registry chủ yếu ở bộ nhớ; server peer-replicate registration; client có cache cục bộ. | Các peer, heartbeat, peer replication, client cache và self-preservation. |
| Consul | Server dùng Raft để duy trì catalog và state; client agent có thể chạy trên node ứng dụng. | Quorum của server voting members, leader, disk I/O và network giữa server. |
| ZooKeeper | Ensemble dùng leader và quorum; registration thường được biểu diễn bằng ephemeral znode. | Majority của ensemble, transaction log, session và network giữa các thành viên. |
| Kubernetes | Service và endpoint được lưu qua Kubernetes API; control plane dùng etcd để lưu trạng thái cluster. | kube-apiserver, etcd quorum, controller và đường DNS/dataplane của cluster. |

Điều đầu tiên khi lập kế hoạch là xác định ứng dụng đang dùng cơ chế nào: gọi DNS của Kubernetes Service, truy vấn Kubernetes API qua Spring Cloud Kubernetes, hay dùng registry riêng như Eureka, Consul hoặc ZooKeeper. Một ứng dụng chỉ gọi Service DNS không có cùng tải discovery với ứng dụng liên tục gọi API để lấy danh sách endpoint.

## 2. Xác định workload trước khi chọn cấu hình máy chủ

Đừng bắt đầu bằng việc chọn CPU hoặc RAM theo một con số chung. Hãy lập workload model từ các thông tin có thể đo được:

- Số service được đăng ký trong từng môi trường và từng cluster.
- Số replica trung bình, cực đại và số instance tăng thêm trong rolling deployment.
- Tần suất heartbeat/renewal và số client thực hiện heartbeat.
- Số consumer, số lookup, chu kỳ refresh và cách client dùng watch, polling hoặc cache.
- Tốc độ tạo, xóa và thay đổi instance trong một khoảng thời gian.
- Số lượng key/value metadata và kích thước registration.
- Số namespace, service, Pod và EndpointSlice nếu dùng Kubernetes.
- Số agent, kết nối đồng thời, peer và vùng địa lý.
- Số lần reconnect đồng thời khi một node, AZ hoặc network path phục hồi.

Cần đo cả tải bình thường và tải đột biến. Một đợt deploy hàng trăm replica, một đợt autoscaling hoặc việc hàng nghìn client reconnect sau network partition có thể tạo burst lớn hơn nhiều so với mức trung bình.

### Công thức ước lượng ban đầu

Gọi:

- N là số instance đang đăng ký.
- T là chu kỳ heartbeat/renewal trung bình tính bằng giây.
- C là số consumer client.
- Q là số lần lookup trung bình mỗi consumer trong một giây.
- S là kích thước trung bình của dữ liệu một instance sau serialization.
- F là hệ số dự phòng cho burst và tăng trưởng.

Có thể ước lượng sơ bộ:

~~~~text
Heartbeat rate trung bình ≈ N / T

Lookup rate trung bình ≈ C × Q

Kích thước dữ liệu registration thô ≈ N × S

Tải kế hoạch ban đầu ≈ tải đo được × F
~~~~

Các công thức chỉ là mô hình đầu vào để benchmark. Chúng không dự đoán chính xác tải thực tế vì mỗi registry có cách batch, cache, replication, watch và xử lý request khác nhau. Hãy dùng log/metric của hệ thống hiện có để thay số giả định bằng số đo.

### Ví dụ tính tải

Giả sử một nền tảng có 2.400 instance và mỗi instance gửi heartbeat trung bình mỗi 30 giây:

~~~~text
Heartbeat rate ≈ 2.400 / 30 = 80 heartbeat/giây
~~~~

Nếu có 600 consumer và mỗi consumer thực hiện một lần lookup mỗi 30 giây:

~~~~text
Lookup rate ≈ 600 / 30 = 20 lookup/giây
~~~~

Nếu rolling deployment làm thêm 600 instance mới cùng đăng ký trong 2 phút, registration burst trung bình của riêng đợt rollout là:

~~~~text
600 / 120 = 5 registration/giây
~~~~

Các giá trị trên chưa tính retry, heartbeat trùng thời điểm, peer replication, client refresh, cache miss, health check hoặc reconnect storm. Khi benchmark cần tạo cả tải đều và burst, thay vì chỉ chạy một mức request/giây ổn định.

## 3. Ước lượng tài nguyên theo từng chiều

Registry không chỉ tiêu thụ CPU. Một hệ thống có nhiều registration nhỏ có thể bị giới hạn bởi network, connection count hoặc heap; một hệ thống ghi state bền vững có thể bị giới hạn bởi disk latency.

| Tài nguyên | Yếu tố gây tải | Dấu hiệu thiếu dung lượng |
| --- | --- | --- |
| CPU | Serialize/deserialize, xử lý request, TLS, lọc service, watch và replication. | CPU cao kéo dài, request latency tăng, leader election hoặc GC tăng. |
| Memory | Registry catalog, metadata, index, client cache, watch state và request buffer. | Heap/working set tăng liên tục, GC pause, OOM hoặc cache eviction. |
| Network | Heartbeat, lookup response, full/incremental registry fetch, peer replication, watch event. | RTT cao, retransmit, connection reset, network saturation. |
| Disk capacity | Snapshot, transaction/Raft log, audit và log vận hành. | Disk gần đầy, log retention không đủ, snapshot thất bại. |
| Disk I/O | Ghi Raft/transaction log, fsync, snapshot và restore. | Write latency cao, leader chậm, quorum mất ổn định. |
| Connections/file descriptors | Số client, peer, agent, HTTP pool và watch connection. | Connection refused, file descriptor exhausted, thread pool cạn. |
| Control-plane/API quota | LIST/WATCH, EndpointSlice update, API request và controller work queue. | API throttling, watch reconnect, endpoint cập nhật chậm. |

Đo footprint của một registration thực tế, bao gồm metadata và overhead của implementation. Không chỉ lấy kích thước JSON trước khi gửi làm dung lượng bộ nhớ. Index, object header, map, cache và replication có thể làm footprint thực lớn hơn nhiều.

### Metadata và số lượng instance

Metadata nên nhỏ và ổn định. Một registry chứa hàng chục nghìn instance, mỗi instance có metadata lớn, sẽ tốn memory và network đáng kể khi client cần đồng bộ catalog.

Nên:

- Chỉ đưa key mà consumer thực sự sử dụng vào metadata.
- Đặt giới hạn số key, độ dài value và tổng byte.
- Không dùng metadata để lưu cấu hình lớn, secret, danh sách người dùng hoặc trạng thái thay đổi liên tục.
- Dùng label/filter/namespace để giới hạn phạm vi discovery khi implementation hỗ trợ.
- Đo kích thước response thực tế sau serialization và mức sử dụng heap khi tải cao.

## 4. Benchmark và hệ số dự phòng

Không có một cấu hình CPU/RAM chung áp dụng cho mọi registry. Thông số phần cứng của Consul server, ZooKeeper server hoặc Kubernetes control plane phụ thuộc quy mô, loại workload, latency mạng và đặc tính lưu trữ.

Một quy trình benchmark thực tế:

1. Tạo catalog có số lượng service, instance và metadata gần với production.
2. Mô phỏng heartbeat/renewal theo chu kỳ thực tế.
3. Tạo lookup ở cả mức trung bình và burst; bao gồm cache hit, cache miss và response lớn.
4. Thực hiện rolling deployment và scale-out/scale-in để tạo churn.
5. Ngắt một node hoặc một network path để đo failover và reconnect.
6. Đo CPU, memory, GC, network, disk latency, open connections, queue depth và request latency.
7. Tăng tải cho tới khi latency/SLO hoặc giới hạn tài nguyên bắt đầu xấu đi.
8. Chọn điểm vận hành thấp hơn vùng bão hòa và dành headroom cho tăng trưởng, bảo trì và lỗi node.

Hệ số dự phòng F cần được chọn theo mức biến động workload, thời gian provisioning và khả năng scale. Ví dụ dùng 1,5 hoặc 2 lần tải dự báo có thể là giả định ban đầu cho một bài benchmark, nhưng không phải quy tắc cố định. Nếu một cụm phải chịu burst reconnect lớn hoặc mất cả một failure domain, cần benchmark kịch bản đó trực tiếp.

Không dùng CPU trung bình thấp làm bằng chứng registry còn dư tải. Với Consul/ZooKeeper, disk sync hoặc network giữa quorum members có thể giới hạn availability trước khi CPU đạt 100%. Với Eureka, server peer replication và client cache có thể che một phần lỗi trong ngắn hạn, nhưng dữ liệu giữa các peer có thể lệch khi mạng bị phân vùng.

## 5. Lập kế hoạch độ sẵn sàng bằng SLO, RTO và RPO

Trước khi chọn số node, cần định nghĩa hệ thống cần phục hồi như thế nào:

- **SLO availability:** tỷ lệ thời gian lookup/registration quan trọng có thể hoàn tất trong ngưỡng latency và error rate đã thống nhất.
- **RTO:** thời gian tối đa để khôi phục dịch vụ registry sau sự cố.
- **RPO:** lượng thay đổi registry có thể chấp nhận mất trong một tình huống phục hồi dữ liệu.
- **Failure domain:** phạm vi lỗi có thể xảy ra cùng lúc, ví dụ process, VM, node, rack, AZ, region hoặc toàn bộ cluster.
- **Degraded mode:** hành vi của provider/consumer khi registry không truy cập được.

Với registry lưu thông tin có thể tái tạo từ heartbeat và đăng ký lại, RPO có thể được xử lý khác với một registry lưu cấu hình hoặc dữ liệu điều phối bền vững. Không nên mặc định rằng mọi registration đều phải được backup giống database nghiệp vụ.

### Chọn failure domain

Nếu đặt tất cả server voting trong cùng một rack hoặc cùng một AZ, sự cố của failure domain đó có thể làm mất quorum dù số node trên sơ đồ có vẻ đủ. Hãy phân tán các thành viên theo topology thực tế và kiểm tra network latency giữa các vùng.

Cần cân bằng giữa:

- Khả năng chịu lỗi của node/AZ.
- Độ trễ giữa các thành viên quorum.
- Chi phí network và compute.
- Số thành viên cần phối hợp cho mỗi lần ghi.
- Quy trình thay thế node và phục hồi quorum.

## 6. Độ sẵn sàng với Eureka

Eureka dùng mô hình peer-aware server. Mỗi server lưu registry trong bộ nhớ, nhận heartbeat từ client và nhân bản registration tới các peer được cấu hình. Client cũng giữ cache registry để không phải truy vấn server cho mỗi request.

Trong production:

- Chạy nhiều Eureka Server peer-aware ở các failure domain độc lập.
- Cấu hình client có thể truy cập nhiều peer hoặc một load balancer được thiết kế phù hợp.
- Bảo đảm peer URLs, hostname, TLS và network path có thể truy cập hai chiều theo cấu hình.
- Theo dõi peer replication, renewal rate, eviction và self-preservation.
- Kiểm tra client vẫn sử dụng cache khi một peer tạm thời không truy cập được.

Eureka không dùng Raft quorum giống Consul hoặc ZooKeeper. Một peer có thể tiếp tục phục vụ với registry view riêng khi mất liên lạc với peer khác. Điều này giúp tăng khả năng phục vụ, nhưng các peer có thể tạm thời có góc nhìn khác nhau về registration.

Self-preservation là cơ chế bảo vệ registry khỏi xóa hàng loạt instance khi số heartbeat giảm bất thường. Trong một network partition, registry có thể giữ lại instance đã không còn phục vụ. Consumer phải có timeout, retry/failover và khả năng xử lý endpoint stale.

Ví dụ peer configuration minh họa:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal/eureka/,https://eureka-b.internal/eureka/,https://eureka-c.internal/eureka/
~~~~

Đây là danh sách URL ví dụ, không phải cấu hình hoàn chỉnh cho mọi topology. Hãy xác minh từng peer thực sự replicate và client có thể failover. Thêm peer mà không kiểm tra kết nối và replication không tạo ra HA thực tế.

Vì registry Eureka thường được tái tạo từ client registration và heartbeat, quy trình backup cần ưu tiên cấu hình server, peer topology, TLS/credential và khả năng client tự đăng ký lại. Nếu yêu cầu phục hồi dữ liệu đặc biệt, hãy xác minh hành vi của phiên bản và deployment cụ thể; không giả định có một snapshot database bền vững tương đương Consul Raft.

## 7. Độ sẵn sàng với Consul

Consul server dùng Raft để duy trì state nhất quán. Chỉ các server voting members tham gia peer set Raft; Consul client agents không làm tăng quorum server.

Với N server voting, quorum là:

~~~~text
quorum = floor(N / 2) + 1
failure tolerance = N - quorum
~~~~

Ví dụ:

| Server voting | Quorum | Số server có thể mất mà vẫn giữ quorum |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |

Consul thường khuyến nghị 3 hoặc 5 server voting cho production. Thêm nhiều server không làm throughput tăng tuyến tính; quorum lớn hơn làm tăng chi phí phối hợp và vận hành. Hãy phân tán server qua các failure domain nhưng vẫn giữ latency giữa chúng trong giới hạn phù hợp.

Các điểm cần theo dõi:

- Leader hiện tại và thời gian leader election.
- Raft commit/apply latency, log size và replication lag.
- Disk sync latency và dung lượng data directory.
- Số server voting/healthy và trạng thái quorum.
- Request latency, blocking query, catalog size và client agent health.

Khi mất quorum, Consul không thể tiếp tục commit các log entry mới. Đừng cố khắc phục bằng cách khởi động thêm server với data directory rỗng vào cluster đang có vấn đề; thao tác membership và recovery cần theo quy trình Consul chính thức.

## 8. Độ sẵn sàng với ZooKeeper

ZooKeeper dùng ensemble và cần majority để duy trì hoạt động. Với N server, quorum là:

~~~~text
quorum = floor(N / 2) + 1
failure tolerance = floor((N - 1) / 2)
~~~~

| Ensemble | Quorum | Số server có thể mất |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Trong production, 3 hoặc 5 server thường là điểm bắt đầu hợp lý. Thêm thành viên làm tăng chi phí replication và quản trị; không nên tăng số node chỉ vì muốn có thêm replica mà chưa tính quorum.

Các lưu ý quan trọng:

- Đặt các server trên máy/VM và failure domain độc lập.
- Dùng network ổn định với latency thấp giữa các thành viên.
- Dành thiết bị hoặc volume phù hợp cho transaction log; ZooKeeper cần ghi transaction log bền vững trước khi xác nhận cập nhật.
- Tránh swap; heap không được chiếm hết RAM vật lý vì hệ điều hành và page cache cũng cần bộ nhớ.
- Theo dõi outstanding requests, latency, fsync, leader state và số lượng watch/session.
- Cấu hình purge snapshot/transaction log theo retention policy; mặc định server không tự xóa toàn bộ file cũ.

Registration dạng ephemeral znode được xóa khi session hết hạn. Vì vậy, khi client reconnect sau session loss, ứng dụng cần tạo lại session và registration. Registry availability và service availability không giống nhau: ensemble có quorum nhưng provider vẫn có thể chưa đăng ký lại.

## 9. Độ sẵn sàng khi dùng Kubernetes discovery

Khi discovery dựa vào Kubernetes, registry view phụ thuộc vào Kubernetes API và trạng thái control plane. API server cung cấp API; etcd lưu trạng thái cluster. EndpointSlice và Service được controller cập nhật dựa trên Pod readiness và selector.

Nếu ứng dụng chỉ gọi ClusterIP Service qua DNS, request data plane có thể tiếp tục hoạt động trong một số tình huống control plane không sẵn sàng. Tuy nhiên, thao tác thay đổi Service, Pod hoặc EndpointSlice có thể bị trì hoãn khi API server/etcd gặp sự cố. Ứng dụng gọi Kubernetes API trực tiếp để refresh discovery sẽ chịu ảnh hưởng rõ hơn.

Với cluster tự quản lý bằng kubeadm, HA topology thường có hai hướng:

- **Stacked etcd:** etcd member chạy cùng control-plane node. Dễ triển khai hơn nhưng mất node làm mất cả một control-plane instance và etcd member.
- **External etcd:** etcd chạy trên host riêng. Tách failure domain tốt hơn nhưng cần thêm máy và vận hành riêng cho etcd.

Một cluster HA cần nhiều control-plane node và etcd member theo topology được hỗ trợ; cấu hình load balancer cho API server phải được kiểm tra độc lập. Không xem số lượng worker node là bằng chứng control plane đã có HA.

Khi dùng Spring Cloud Kubernetes DiscoveryClient, giới hạn namespace và label filter để giảm LIST/WATCH. Theo dõi API throttling, watch reconnect, EndpointSlice update latency và cache freshness. Nếu chỉ cần hostname Service, Kubernetes DNS thường giảm phụ thuộc vào việc mỗi ứng dụng gọi API server.

## 10. Thiết kế hành vi khi registry không sẵn sàng

Availability không chỉ là số node. Cần quyết định consumer và provider làm gì khi registry bị mất:

| Tình huống | Hành vi nên cân nhắc |
| --- | --- |
| Provider không đăng ký được lúc startup | Retry có backoff và jitter; báo trạng thái degraded; không tạo vòng lặp retry dồn dập. |
| Registry mất sau khi app đã chạy | Giữ last-known-good cache nếu thư viện hỗ trợ; timeout request nhanh và theo dõi cache age. |
| Lookup trả danh sách rỗng | Phân biệt service chưa tồn tại với lookup error; không tự thay empty thành cache cũ vô thời hạn. |
| Instance trong cache đã stale | Thử endpoint với timeout giới hạn, retry sang instance khác và cập nhật cache khi registry hồi phục. |
| Registry reconnect đồng loạt | Dùng backoff/jitter và giới hạn concurrency để tránh reconnect storm. |
| Provider shutdown | Deregister nếu có thể; readiness/draining trước khi process kết thúc. |

Không có chiến lược stale-cache phù hợp cho mọi service. Một consumer có thể chấp nhận dùng địa chỉ đã biết trong vài phút cho thao tác đọc không nhạy cảm; một consumer khác cần dữ liệu membership mới vì thao tác ghi hoặc bảo mật. Hãy xác định giới hạn tuổi cache, timeout và retry theo hợp đồng nghiệp vụ.

## 11. Backup, restore và disaster recovery

Backup phải phù hợp với loại dữ liệu registry lưu trữ.

| Registry | Dữ liệu cần bảo vệ | Lưu ý phục hồi |
| --- | --- | --- |
| Eureka | Cấu hình, peer topology, TLS/credential, deployment manifest và quy trình client re-registration. | Registry runtime chủ yếu ở memory; cần xác minh khả năng tái tạo từ heartbeat/client thay vì giả định có database snapshot. |
| Consul | Raft snapshot, cấu hình server/agent, ACL, TLS, encryption key và thông tin deployment. | Snapshot cần được lưu an toàn và restore thử vào cluster phục hồi phù hợp. |
| ZooKeeper | Snapshot, transaction log, dataDir, logDir, myid và cấu hình ensemble. | Giữ snapshot cùng transaction log cần thiết; kiểm tra phục hồi và đồng bộ server theo hướng dẫn. |
| Kubernetes | etcd snapshot, PKI/certificates, encryption configuration, manifests và thông tin control-plane. | etcd snapshot chứa state cluster nhạy cảm; mã hóa và giới hạn quyền truy cập. |

### Backup Consul

Consul cung cấp snapshot cho state của server cluster. Ví dụ thao tác:

~~~~bash
consul snapshot save registry-backup.snap
consul snapshot inspect registry-backup.snap
~~~~

Lưu snapshot ở nơi tách biệt với cluster và kiểm tra snapshot có thể đọc được. Restore là thao tác Raft cấp thấp, chủ yếu dành cho disaster recovery và có thể ảnh hưởng lớn đến state của cluster. Tài liệu Consul yêu cầu cluster phục hồi chạy cùng phiên bản Consul đã tạo snapshot. Hãy restore vào cluster mới/cô lập theo runbook của phiên bản, không coi restore là thao tác rollback nóng trên cluster đang hoạt động. Diễn tập trong môi trường riêng trước khi cần dùng trong production.

### Backup ZooKeeper

ZooKeeper lưu snapshot của data tree và transaction log. Cần hiểu quan hệ giữa snapshot mới nhất và các transaction log sau snapshot. Không xóa thủ công file đang cần cho recovery. Cấu hình autopurge/retention để tránh đầy disk nhưng vẫn giữ đủ file theo chính sách backup.

### Backup Kubernetes etcd

etcd snapshot chứa trạng thái Kubernetes cluster, bao gồm Secret và dữ liệu nhạy cảm khác. Mã hóa file backup, hạn chế quyền đọc, quản lý certificate/key và kiểm tra restore trên một control plane cô lập. Backup chưa được restore thử chưa phải bằng chứng rằng quy trình DR hoạt động.

### Kiểm thử restore

Một bài diễn tập tối thiểu nên xác nhận:

1. Snapshot được tạo từ cluster khỏe mạnh và có timestamp/index rõ ràng.
2. Snapshot được chuyển tới vùng lưu trữ tách biệt và có checksum.
3. Nhóm vận hành có đủ credential/certificate/config để dựng cluster phục hồi.
4. Restore thành công trong môi trường cô lập.
5. Service catalog, ACL, metadata, namespace và registration được xác minh.
6. Consumer có thể lookup và gọi instance sau khi provider đăng ký lại.
7. Đo thời gian thực tế để so với RTO/RPO.

## 12. Lập kế hoạch nâng cấp registry

Nâng cấp registry có thể ảnh hưởng đến protocol, dữ liệu bền vững, API, client library và cách Spring Cloud tích hợp. Hãy chia nâng cấp thành các bước có thể quan sát và dừng an toàn.

### Trước khi nâng cấp

- Xác định phiên bản hiện tại và phiên bản đích của server, agent và client library.
- Đọc release notes, deprecation, breaking changes và supported upgrade path.
- Kiểm tra ma trận tương thích giữa Spring Boot, Spring Cloud release train, Spring Cloud Netflix/Consul/Zookeeper/Kubernetes và registry server.
- Kiểm tra protocol compatibility, API version, serialization, metadata schema và authentication.
- Đo baseline: registration failure, lookup error/empty, latency, connection state, catalog size và quorum health.
- Tạo backup hoặc xác nhận cách tái tạo registry phù hợp với công nghệ.
- Diễn tập restore và rollback trong môi trường staging có tải gần production.
- Xác nhận client có thể tiếp tục hoạt động khi một node server được nâng cấp.

Không nâng cấp nhiều server voting cùng lúc. Với quorum-based registry, làm như vậy có thể khiến cluster mất majority. Không bắt đầu khi cluster đang mất node, leader không ổn định hoặc replication lag cao.

### Rolling upgrade

Một trình tự tổng quát:

~~~~mermaid
flowchart TD
    A[Kiểm tra phiên bản và release notes] --> B[Đo baseline và xác nhận cluster khỏe]
    B --> C[Backup hoặc xác nhận khả năng tái tạo]
    C --> D[Diễn tập upgrade và restore ở staging]
    D --> E[Upgrade một server/peer canary]
    E --> F{Node khỏe và đồng bộ?}
    F -- Không --> G[Stop rollout và điều tra/rollback theo runbook]
    F -- Có --> H[Upgrade từng server còn lại]
    H --> I[Upgrade client agents và ứng dụng theo đợt]
    I --> J[Kiểm thử register, lookup, heartbeat và failover]
    J --> K[Theo dõi SLO và đóng đợt nâng cấp]
~~~~

Đây là thứ tự khung. Thứ tự chi tiết phải theo hướng dẫn upgrade của sản phẩm và phiên bản đích.

### Consul

Quy trình Consul thông thường nâng từng server agent một, chờ server khỏe và rejoin cluster rồi mới chuyển sang server tiếp theo. Sau khi server cluster hoàn tất, mới rollout client agents và thành phần phụ thuộc như Envoy theo compatibility matrix.

Trước khi nâng cấp, tạo snapshot và xem hướng dẫn riêng cho từng major version. Một số bản có protocol compatibility hoặc quy trình hai pha cho thay đổi không tương thích ngược. Không suy luận rằng mọi phiên bản đều có thể nhảy thẳng tới bản mới nhất.

### ZooKeeper

ZooKeeper có quy tắc backward compatibility và rolling upgrade path theo release. Cần kiểm tra phiên bản nguồn, phiên bản đích, client compatibility và các tính năng mới mà client bắt đầu sử dụng. Tài liệu phát hành có thể khuyến nghị đi qua một nhánh trung gian trước khi lên nhánh mới.

Khi rolling upgrade ensemble, giữ quorum hoạt động, chỉ nâng một thành viên tại một thời điểm và chờ thành viên rejoin ổn định. Không bật tính năng mới yêu cầu phiên bản server mới trên toàn cluster trước khi tất cả thành viên và client liên quan tương thích.

### Eureka

Eureka server peer-aware có thể được nâng từng peer trong khi các peer khác tiếp tục phục vụ. Trước khi chuyển peer tiếp theo, kiểm tra peer replication, heartbeat, registry fetch và client error rate. Do registry view có thể tạm thời khác nhau giữa peer, cần kiểm tra client có thể truy cập peer còn khỏe và chịu được dữ liệu stale trong thời gian rollout.

Nâng cấp Spring Cloud Netflix client theo release train tương thích với Spring Boot. Không chỉ nâng server mà bỏ qua các thay đổi trong client transport, heartbeat, health check hoặc metadata handling.

### Kubernetes

Kubernetes control-plane upgrade cần theo version skew policy và hướng dẫn của phiên bản Kubernetes. Với kubeadm, nâng cấp control plane và node theo quy trình được hỗ trợ; backup etcd trước khi thay đổi. Đừng tự ý nâng kube-apiserver, kubelet, kubeadm và etcd theo thứ tự tùy ý. Kiểm tra API deprecated/removed và version của controller/operator quản lý EndpointSlice.

## 13. Kiểm chứng sau nâng cấp

Sau mỗi node hoặc mỗi đợt client upgrade, xác minh:

- Tất cả server members có version/build mong đợi.
- Quorum hoặc peer replication đang khỏe.
- Leader không bầu lại liên tục.
- Client kết nối được, đăng ký mới và heartbeat/renew thành công.
- Lookup trả đúng instance, metadata và endpoint.
- Registration/deregistration không tăng lỗi.
- Request latency và connection latency không vượt SLO.
- Không có tăng đột biến retry, reconnect, timeout hoặc stale cache.
- Backup/restore procedure vẫn phù hợp với phiên bản mới.
- Các dashboard, alert và runbook còn hoạt động.

Đừng đóng change chỉ vì process mới đã khởi động. Hãy xác minh hành vi end-to-end từ provider đến consumer.

## 14. Kế hoạch thay đổi và rollback

Một change plan nên ghi rõ:

| Hạng mục | Nội dung cần ghi |
| --- | --- |
| Phạm vi | Registry server, client agent, Spring Cloud dependency, control plane hoặc tất cả. |
| Mục tiêu | Phiên bản đích, lỗi cần khắc phục, tính năng cần dùng. |
| Tương thích | Supported upgrade path, protocol, API, client/server version skew. |
| Backup | Snapshot/config backup, nơi lưu, người có quyền restore và thời điểm tạo. |
| Thứ tự | Node canary, server còn lại, client agents, ứng dụng. |
| Gate | Quorum/peer health, registration error, lookup latency, catalog visibility. |
| Dừng rollout | Điều kiện vượt SLO, mất quorum, peer replication lỗi hoặc client incompatibility. |
| Rollback | Cách quay lại phiên bản trước; khi nào cần restore snapshot thay vì chỉ hạ binary. |
| Xác minh | Register, heartbeat, lookup, failover, restore test và dashboard. |

Rollback không phải lúc nào cũng là thay binary cũ trở lại. Nếu phiên bản mới đã thay đổi state hoặc protocol, cần làm theo hướng dẫn downgrade/restore cụ thể. Không restore snapshot cũ lên cluster đang hoạt động mà chưa xác định tác động của thao tác đó.

## 15. Checklist dung lượng và độ sẵn sàng

- [ ] Đã đếm instance, consumer, heartbeat, lookup, churn và metadata theo môi trường.
- [ ] Đã đo catalog size và response size thực tế.
- [ ] Đã benchmark tải đều, burst deployment, reconnect và node failure.
- [ ] Đã xác định CPU, memory, network, disk I/O, connections và file descriptors là các giới hạn riêng.
- [ ] Đã chọn headroom theo dữ liệu benchmark và tốc độ tăng trưởng.
- [ ] Đã xác định SLO, RTO, RPO và failure domains.
- [ ] Đã phân biệt peer replication của Eureka với quorum của Consul/ZooKeeper/etcd.
- [ ] Đã phân tán server voting/peer qua failure domain phù hợp.
- [ ] Đã xác định hành vi client khi registry unavailable và giới hạn tuổi cache.
- [ ] Đã có backup hoặc quy trình re-registration phù hợp với registry.
- [ ] Đã diễn tập restore và đo RTO thực tế.
- [ ] Đã kiểm tra version compatibility và supported upgrade path.
- [ ] Đã upgrade canary trước và giữ quorum trong suốt rolling upgrade.
- [ ] Đã kiểm chứng registration, heartbeat, lookup, failover và client compatibility sau nâng cấp.
- [ ] Đã cập nhật dashboard, alert và runbook.

## Ghi nhớ

- Capacity planning bắt đầu từ số instance, heartbeat, lookup, churn và kích thước metadata; không bắt đầu từ một cấu hình máy chủ mặc định.
- Benchmark phải có cả tải bình thường, burst deploy và reconnect storm.
- Eureka peer replication không có quorum Raft; Consul, ZooKeeper và etcd cần majority/quorum.
- Thêm server voting không luôn tăng throughput; quorum lớn hơn cũng tăng chi phí phối hợp.
- HA phải xét failure domain, network, disk I/O, backup và hành vi client khi registry unavailable.
- Backup cần phù hợp dữ liệu: Consul snapshot, ZooKeeper snapshot/log, Kubernetes etcd snapshot; Eureka thường cần bảo vệ cấu hình và khả năng client re-register.
- Rolling upgrade chỉ tiến từng bước khi node đã khỏe và đồng bộ; luôn theo supported upgrade path của phiên bản.
- Kiểm tra register, lookup, latency, failover và restore sau nâng cấp trước khi đóng change.

## Tài liệu tham khảo chính thức

- [Spring Cloud Netflix – Eureka Server and High Availability](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Peer-to-Peer Communication and Self-Preservation](https://github.com/Netflix/eureka/wiki/Understanding-Eureka-Peer-to-Peer-Communication)
- [Consul – Capacity Planning](https://developer.hashicorp.com/consul/docs/reference/architecture/capacity)
- [Consul – Reliability and Quorum](https://developer.hashicorp.com/consul/docs/concept/reliability)
- [Consul – Upgrading Consul](https://developer.hashicorp.com/consul/docs/upgrade)
- [Consul – General Upgrade Process](https://developer.hashicorp.com/consul/docs/upgrade/instructions/general)
- [Consul – Backup and Restore](https://developer.hashicorp.com/consul/docs/manage/disaster-recovery/backup-restore)
- [Apache ZooKeeper – Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache ZooKeeper – Releases and Upgrade Guidance](https://zookeeper.apache.org/releases/)
- [Kubernetes – Highly Available Topology](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/)
- [Kubernetes – Highly Available Cluster](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)
- [Kubernetes – Operating etcd Clusters](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)
