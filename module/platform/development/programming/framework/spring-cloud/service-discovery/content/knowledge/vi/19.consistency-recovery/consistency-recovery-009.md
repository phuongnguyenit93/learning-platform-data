# Đặt tiêu chí phục hồi và kiểm chứng bằng thí nghiệm gây lỗi

Service discovery có thể trả về một danh sách instance hợp lệ về mặt cấu trúc nhưng đã cũ so với trạng thái thực tế. Một provider có thể đã dừng trong khi registry hoặc cache consumer vẫn giữ địa chỉ của nó; ngược lại, provider mới đã sẵn sàng nhưng consumer chưa nhìn thấy registration mới. Vì vậy, kiểm thử service discovery không nên chỉ xác nhận registry hoạt động hoặc endpoint trả về HTTP 200. Cần đo thời gian phát hiện lỗi, thời gian hội tụ của registry và consumer, mức độ stale data, khả năng phục hồi và tỷ lệ instance khỏe bị loại nhầm.

Thí nghiệm gây lỗi (fault injection) tạo ra các tình huống có kiểm soát như dừng provider, chặn kết nối tới registry, làm chậm health check hoặc khởi động lại một node. Quan sát kết quả giúp xác minh các tiêu chí phục hồi đã đặt có đạt được trong điều kiện thực tế hay không.

Bài viết xây dựng bộ tiêu chí đo lường, cách lập kế hoạch thí nghiệm, ma trận lỗi cho Eureka, Consul và ZooKeeper, phương pháp thu thập bằng chứng và cách chuyển kết quả thành quyết định vận hành.

## 1. Phục hồi trong service discovery cần đạt điều gì?

Một luồng discovery có nhiều trạng thái độc lập:

1. Provider process đang chạy hay đã dừng.
2. Endpoint nghiệp vụ có thực sự sẵn sàng nhận request hay không.
3. Registry đã ghi nhận trạng thái mới chưa.
4. Discovery client đã cập nhật danh sách local chưa.
5. LoadBalancer hoặc cache của consumer còn chọn instance cũ không.
6. Consumer có thể gọi thành công một instance khỏe khác hay không.

Một hệ thống phục hồi tốt phải đưa các lớp này trở lại trạng thái nhất quán trong giới hạn thời gian đã thống nhất. Registry hiển thị instance UP chưa đủ để chứng minh consumer gọi được; tương tự, registry xóa instance lỗi chưa bảo đảm mọi consumer đã ngừng sử dụng cache cũ.

~~~mermaid
flowchart LR
    P["Provider thực tế"]
    R["Registry / agent"]
    D["Discovery client cache"]
    L["LoadBalancer"]
    Q["Request của consumer"]
    P -->|"Register / health"| R
    R -->|"Fetch / watch / query"| D
    D --> L
    L --> Q
    Q --> P
~~~

Khi gây lỗi, cần quan sát cả provider, registry, cache consumer và kết quả request. Chỉ nhìn một thành phần sẽ không cho biết toàn bộ thời gian phục hồi.

## 2. Phân biệt phát hiện, hội tụ và khôi phục dịch vụ

Đặt các mốc thời gian:

- **t0:** thời điểm bắt đầu gây lỗi.
- **tdetect:** thời điểm hệ thống discovery đầu tiên nhận biết lỗi.
- **tregistry:** thời điểm registry phản ánh trạng thái mới.
- **tconsumer:** thời điểm consumer không còn chọn instance lỗi và đã nhìn thấy danh sách phù hợp.
- **trecovered:** thời điểm consumer gọi thành công một instance khỏe theo tiêu chí nghiệp vụ.

Từ đó có thể đo:

\[
T_{detect} = t_{detect} - t_0
\]

\[
T_{registry} = t_{registry} - t_0
\]

\[
T_{converge} = t_{consumer} - t_{registry}
\]

\[
T_{remove} = t_{consumer} - t_0
\]

\[
T_{restore} = t_{recovered} - t_0
\]

Các chỉ số này trả lời các câu hỏi khác nhau:

| Chỉ số | Câu hỏi |
|---|---|
| Detection time | Bao lâu registry hoặc health checker nhận biết instance lỗi? |
| Registry convergence | Bao lâu registry thể hiện trạng thái mới? |
| Consumer convergence | Bao lâu consumer ngừng chọn instance lỗi? |
| Removal time | Bao lâu địa chỉ lỗi biến mất khỏi luồng chọn instance? |
| Service restore time | Bao lâu request nghiệp vụ có thể thành công trở lại? |

Ví dụ, Consul agent phát hiện health check thất bại sau 15 giây, catalog cập nhật gần như ngay sau đó, nhưng consumer còn cache danh sách cũ thêm 20 giây. Khi đó detection time có thể tốt, nhưng removal time vẫn dài do cache. Nếu còn instance khỏe khác, request có thể phục hồi trước khi instance lỗi bị loại khỏi mọi cache; vì vậy phải đo cả request success và discovery state.

## 3. Đặt SLI và SLO có thể kiểm chứng

SLI là chỉ số đo được; SLO là mục tiêu chất lượng đã thống nhất. Không dùng một mục tiêu chung cho mọi service. API thanh toán, service nội bộ ít lưu lượng và môi trường phát triển có thể có yêu cầu khác nhau.

Một bộ SLI hữu ích:

| SLI | Cách đo | Ý nghĩa |
|---|---|---|
| Stale selection rate | Số request được gửi tới instance đã xác nhận lỗi / tổng request | Mức ảnh hưởng của stale registry |
| Healthy instance availability | Tỷ lệ thời gian instance khỏe vẫn có thể được chọn | Tránh loại nhầm instance tốt |
| Detection latency | tdetect - t0 | Tốc độ nhận biết lỗi |
| Registry update latency | tregistry - t0 | Thời gian registry phản ánh trạng thái mới |
| Consumer convergence latency | tconsumer - tregistry | Thời gian consumer áp dụng trạng thái registry mới |
| Removal latency | tconsumer - t0 | Tổng thời gian từ lúc gây lỗi đến khi consumer ngừng chọn instance lỗi |
| Service restore latency | trecovered - t0 | Thời gian request phục hồi |
| Registration recovery | Thời gian instance mới xuất hiện và được consumer sử dụng | Khả năng phục hồi sau restart/scale |
| Registry request error rate | Lỗi register, heartbeat, fetch, query hoặc watch | Sức khỏe control plane |
| False eviction rate | Tỷ lệ instance khỏe bị đánh dấu lỗi hoặc bị loại nhầm | Độ ổn định của cơ chế health |

Ví dụ SLO minh họa cho một service có ít nhất hai replica:

- Sau khi một replica bị dừng cưỡng bức, consumer ngừng chọn replica đó trong tối đa 60 giây ở p95.
- Request thành công trở lại trong tối đa 30 giây nếu vẫn còn replica khỏe và không có lỗi dependency khác.
- Tỷ lệ request tới instance đã xác nhận lỗi sau thời điểm hội tụ nhỏ hơn 0,1% trong cửa sổ đo.
- Không có instance khỏe nào bị loại nhầm trong thí nghiệm mất kết nối ngắn hơn ngưỡng chịu đựng đã định.
- Instance mới được consumer nhìn thấy trong tối đa 90 giây sau khi đạt readiness và đăng ký thành công.

Đây chỉ là số mẫu để minh họa cách viết SLO, không phải mặc định của Spring Cloud hoặc các registry. Hãy chọn giới hạn dựa trên lease/session timeout, health-check interval, fetch/watch behavior, cache TTL, latency mạng và yêu cầu nghiệp vụ.

### Đặt ngưỡng stale data

Stale data có thể được đo theo thời gian hoặc theo request:

- **Stale window:** khoảng từ khi provider thực sự lỗi tới khi consumer cuối cùng ngừng chọn nó.
- **Stale request count:** số request được gửi tới instance lỗi trong stale window.
- **Stale request ratio:** stale request chia cho tổng request trong cùng cửa sổ.

Nếu instance lỗi chỉ nhận một request mỗi phút, stale request count có thể thấp dù stale window dài. Nếu service có lưu lượng lớn, một stale window ngắn vẫn có thể tạo nhiều request lỗi. Vì vậy nên theo dõi cả thời gian và tỷ lệ request.

### Định nghĩa tiêu chí phục hồi cho instance mới

Không tính instance mới là phục hồi chỉ vì process đã khởi động hoặc znode/registry record đã xuất hiện. Chỉ đánh dấu phục hồi khi:

1. Provider vượt qua readiness check cần thiết.
2. Registry có registration với host, port và metadata đúng.
3. Discovery client mục tiêu đã nhìn thấy instance.
4. LoadBalancer có thể chọn instance.
5. Một request kiểm chứng an toàn tới instance trả kết quả hợp lệ.

## 4. Đặt giới hạn cho mất dữ liệu và trạng thái registry

Trong service discovery, registration động thường có thể được tái tạo từ các provider còn sống. Vì vậy, khái niệm RPO của registry không hoàn toàn giống RPO của cơ sở dữ liệu nghiệp vụ.

Thay vì chỉ hỏi “mất bao nhiêu dữ liệu”, nên xác định:

- Có bao nhiêu registration hợp lệ bị mất sau khi registry restart?
- Bao lâu provider còn sống đăng ký lại được?
- Có bao nhiêu registration cũ còn sót sau khi instance đã dừng?
- Metadata, service ID, instance ID và health state có được khôi phục đúng không?
- Consumer có nhìn thấy trạng thái nhất quán sau khi cache được làm mới không?

Với ephemeral registration, trạng thái có thể được dựng lại từ provider đang chạy và session mới. Với cấu hình tĩnh hoặc cấu hình registry do quản trị viên quản lý, cần kiểm tra khả năng lưu bền và khôi phục từ nguồn cấu hình. Không gộp registration động với dữ liệu cấu hình bền vững thành một chỉ số RPO duy nhất.

## 5. Chuẩn bị thí nghiệm gây lỗi

Một thí nghiệm tốt có giả thuyết, phạm vi, tiêu chí pass/fail và cách khôi phục rõ ràng.

### Xác định giả thuyết

Ví dụ:

“Nếu một provider bị dừng cưỡng bức, health/lease/session sẽ khiến instance bị loại khỏi lựa chọn của consumer trong tối đa 60 giây; consumer chuyển sang replica khỏe còn lại mà không vượt quá tỷ lệ lỗi request đã đặt.”

Giả thuyết phải nói rõ:

- Lỗi được tạo ở đâu và vào thời điểm nào.
- Thành phần nào dự kiến phát hiện lỗi.
- Consumer nào được dùng để đo.
- Trạng thái mong đợi ở registry và request path.
- Giới hạn thời gian và tỷ lệ lỗi.

### Chuẩn bị baseline

Trước khi gây lỗi:

1. Xác nhận mọi instance mục tiêu đang healthy.
2. Ghi lại service ID, instance ID, host, port, metadata và trạng thái registry.
3. Ghi số lượng instance mà từng consumer nhìn thấy.
4. Gửi request kiểm chứng ở tải thấp để xác nhận đường gọi bình thường.
5. Ghi baseline latency, error rate, registry QPS và health-check latency.
6. Đồng bộ thời gian giữa máy test, provider, registry và consumer.

Không thể tính chính xác stale window nếu đồng hồ giữa các thành phần lệch đáng kể. Dùng timestamp đồng bộ hoặc một bộ điều khiển thí nghiệm ghi mốc t0 duy nhất.

### Cô lập phạm vi

Chạy fault injection trong môi trường staging hoặc namespace dành riêng, với service ID và dữ liệu không ảnh hưởng workload khác. Xác định trước:

- Instance hoặc node nào được phép tác động.
- Tài nguyên nào tuyệt đối không được dừng.
- Ngưỡng tự dừng thí nghiệm.
- Người chịu trách nhiệm khôi phục.
- Cách xác nhận mọi fault rule đã được gỡ bỏ.

Không chạy đồng thời nhiều loại lỗi trong lần đo đầu tiên. Bắt đầu bằng một lỗi đơn, xác định nguyên nhân, rồi mới thử các lỗi kết hợp.

## 6. Ma trận thí nghiệm gây lỗi

Ma trận sau là bộ khung để chọn thí nghiệm. Mỗi hàng cần có expected result, timeout và bằng chứng cụ thể trước khi chạy.

| Thí nghiệm | Cách tạo lỗi | Điều cần quan sát |
|---|---|---|
| Provider crash | Dừng cưỡng bức một instance | Health/lease/session phát hiện, registry loại instance, consumer chuyển sang replica khác |
| Graceful shutdown | Dừng provider theo quy trình | Deregistration chủ động, drain request, không tạo stale window dài |
| Provider bị cô lập khỏi registry | Chặn lưu lượng provider-agent/registry nhưng giữ API còn chạy | Registration có hết hạn không, provider có tự đăng ký lại sau reconnect không |
| Consumer bị cô lập khỏi registry | Chặn consumer-registry nhưng giữ provider hoạt động | Cache cũ được dùng ra sao, request có tiếp tục được không, refresh sau reconnect |
| Registry node/agent restart | Khởi động lại một node hoặc agent trong staging | Quorum/leader, registration, reconnect, cache và thời gian hội tụ |
| Network latency/loss | Thêm delay hoặc packet loss có giới hạn | False eviction, retry burst, latency và session stability |
| Health endpoint lỗi | Trả 500 hoặc timeout từ health endpoint | Trạng thái instance thay đổi đúng ngưỡng và phục hồi sau khi endpoint khỏe |
| Rolling deployment | Thay instance theo batch | Có khoảng thời gian không còn instance khả dụng hay không |
| Duplicate instance ID | Khởi động hai provider cùng định danh trong test | Registry xử lý xung đột thế nào, instance nào bị ghi đè hoặc từ chối |
| Metadata sai | Đăng ký thiếu hoặc sai version/zone | Consumer filter có loại đúng instance và phát cảnh báo không |

## 7. Thí nghiệm theo đặc tính Eureka

Eureka Client thường gửi heartbeat/renewal, còn consumer fetch registry theo chu kỳ. Thí nghiệm nên kiểm tra cả eviction ở server lẫn độ trễ fetch/cache ở client.

### Provider dừng cưỡng bức

Quy trình:

1. Chạy tối thiểu hai instance cùng service ID.
2. Xác nhận cả hai đang UP trong Eureka và được consumer nhìn thấy.
3. Gửi request liên tục ở tải thấp, ghi nhận instance được chọn.
4. Dừng cưỡng bức một provider để không chạy deregistration graceful.
5. Ghi thời điểm lease không còn được renew và thời điểm Eureka loại instance.
6. Theo dõi registry fetch của consumer và thời điểm request ngừng tới instance đã dừng.
7. Xác minh request tiếp tục thành công qua instance còn lại.

Các cấu hình thường ảnh hưởng kết quả:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    registry-fetch-interval-seconds: 30
~~~

Các giá trị trên chỉ là ví dụ. Eureka Server có cơ chế self-preservation để tránh xóa hàng loạt instance khi tỷ lệ renewal giảm bất thường. Trong thí nghiệm, phải ghi lại trạng thái self-preservation và log eviction; không giả định lease expiration luôn dẫn đến xóa ngay trong mọi điều kiện.

### Consumer mất kết nối tới Eureka

Chặn kết nối từ một consumer tới Eureka nhưng giữ provider và các consumer khác hoạt động. Quan sát:

- Consumer tiếp tục dùng local registry cache hay từ chối request.
- Danh sách cache có stale khi provider bị dừng trong thời gian consumer mất kết nối không.
- Sau khi mạng phục hồi, consumer mất bao lâu để fetch snapshot mới.
- Retry có tạo burst khi nhiều client reconnect cùng lúc không.

Kết quả mong đợi phải được viết theo cấu hình client và chính sách request thực tế. Không giả định tất cả phiên bản Eureka client xử lý cache và lỗi kết nối giống hệt nhau.

## 8. Thí nghiệm theo đặc tính Consul

Consul thường sử dụng agent để nhận registration và chạy health check. Cần phân biệt lỗi của ứng dụng với lỗi agent và lỗi giao tiếp giữa agent với Consul server.

### Health check thất bại

1. Đăng ký provider có health check endpoint nhẹ.
2. Xác nhận agent đang báo check passing.
3. Làm endpoint trả lỗi hoặc không phản hồi.
4. Ghi thời điểm lần probe thất bại đầu tiên và thời điểm catalog chuyển trạng thái.
5. Truy vấn health API với điều kiện chỉ lấy instance passing.
6. Kiểm tra consumer có dùng query chỉ lấy instance passing hay vẫn nhận cả instance warning/critical.
7. Khôi phục endpoint và đo thời gian instance trở lại trạng thái passing.

Ví dụ kiểm tra catalog health:

~~~bash
curl "http://consul-agent:8500/v1/health/service/catalog-service?passing=true"
~~~

Trong môi trường bật ACL/TLS, cần dùng HTTPS và token phù hợp. Lệnh chỉ minh họa truy vấn; không nên dùng API không xác thực trong production.

### Agent mất kết nối tới server

Chặn đường giao tiếp giữa một Consul agent client và Consul server trong thời gian có kiểm soát, nhưng giữ HTTP API cục bộ nếu kịch bản yêu cầu. Theo dõi:

- Agent API còn phản hồi không.
- Local health check có tiếp tục chạy không.
- Catalog server nhìn thấy trạng thái nào.
- Agent đồng bộ lại bao lâu sau khi kết nối phục hồi.
- Consumer truy vấn agent khác có nhìn thấy trạng thái khác không.

Một agent cục bộ phản hồi không đồng nghĩa toàn cụm đã nhận trạng thái mới. Hãy so sánh kết quả từ agent bị tác động, agent khác và server/catalog theo đúng topology triển khai.

## 9. Thí nghiệm theo đặc tính ZooKeeper

ZooKeeper gắn ephemeral znode với session. Mất TCP connection tạm thời không nhất thiết xóa node; node bị xóa khi session hết hạn. Vì vậy, thí nghiệm phải phân biệt reconnect thành công với session expiration.

### Mất kết nối ngắn hơn session timeout

1. Đăng ký một service bằng ephemeral znode.
2. Ghi session state và ephemeral owner.
3. Chặn kết nối client tới ensemble trong khoảng ngắn hơn session timeout hiệu lực.
4. Quan sát znode vẫn tồn tại trong lúc session còn hiệu lực.
5. Khôi phục mạng và xác nhận client reconnect với session cũ nếu có thể.
6. Xác minh registration và watch được duy trì hoặc phục hồi đúng.

### Mất kết nối vượt session timeout

1. Tạo lại baseline với session khỏe.
2. Chặn kết nối client lâu hơn session timeout đã thương lượng.
3. Xác nhận server đánh dấu session expired.
4. Xác nhận ephemeral znode thuộc session bị xóa.
5. Khôi phục mạng.
6. Xác nhận client tạo session mới và đăng ký lại znode.
7. Đo thời gian consumer nhìn thấy instance trở lại.

Không lấy connection timeout làm mốc session expiration. Server thương lượng session timeout trong giới hạn cấu hình của ensemble; phải quan sát giá trị hiệu lực trước khi đặt thời lượng gây lỗi.

### Registry mất quorum

Trong môi trường staging có nhiều ZooKeeper server, dừng một node rồi kiểm tra client tiếp tục hoạt động khi quorum còn đủ. Sau đó có thể mô phỏng mất quorum trong môi trường cô lập để xác minh client báo lỗi, session/watch phục hồi và không tạo kết luận sai rằng mọi provider đã chết.

Không thực hiện thí nghiệm mất quorum trên ensemble đang phục vụ workload dùng chung. Mục tiêu là hiểu hành vi khi control plane không thể commit thay đổi, không phải gây gián đoạn hệ thống đang vận hành.

## 10. Công cụ fault injection

Chọn công cụ theo lớp lỗi muốn tạo:

| Công cụ/cách làm | Lỗi có thể mô phỏng | Phạm vi phù hợp |
|---|---|---|
| Docker Compose stop/kill/restart | Provider hoặc agent dừng | Local integration/staging |
| Toxiproxy | Delay, timeout, reset, bandwidth limit giữa hai endpoint | Kiểm thử client-registry hoặc consumer-provider |
| Linux network emulation (`tc netem`) | Delay, jitter, packet loss, corruption | Network namespace hoặc node thử nghiệm |
| Kubernetes pod delete/scale | Pod restart hoặc replica biến mất | Namespace staging |
| Chaos Mesh/Litmus | Network partition, pod failure, stress theo experiment | Kubernetes staging có kiểm soát |
| HTTP mock server | Health endpoint trả 500, chậm hoặc body lỗi | Test tự động của ứng dụng |

Ưu tiên proxy trung gian hoặc network namespace dành riêng để chỉ tác động kết nối mục tiêu. Khi dùng network emulation ở node, phải xác định đúng interface và rule cleanup; một rule áp vào interface dùng chung có thể ảnh hưởng nhiều workload ngoài thí nghiệm.

### Ví dụ dừng một provider trong Docker Compose

~~~bash
docker compose stop inventory-service
~~~

Lệnh này mô phỏng dừng có kiểm soát. Để kiểm tra crash không chạy shutdown hook, dùng cách dừng cưỡng bức trong môi trường thử nghiệm và ghi rõ đó là kịch bản khác. Sau mỗi lần gây lỗi, xác nhận trạng thái container và thời điểm dừng thực tế.

### Ví dụ kiểm tra endpoint từ Kubernetes

~~~bash
kubectl get pods -n discovery-staging
kubectl get endpointslices -n discovery-staging
kubectl describe pod <pod-name> -n discovery-staging
~~~

Các lệnh này thu thập trạng thái Pod và EndpointSlice. Khi test, so sánh chúng với dữ liệu Eureka/Consul/ZooKeeper và danh sách instance mà consumer nhìn thấy.

## 11. Đối chiếu trạng thái giữa các lớp

Trong mỗi thí nghiệm, thu thập bằng chứng từ ít nhất bốn góc nhìn:

| Góc nhìn | Bằng chứng |
|---|---|
| Provider | Process/container/pod state, readiness, health endpoint, log start/stop |
| Registry | Instance record, status, health check, lease/session, registration timestamp |
| Consumer | Danh sách DiscoveryClient, LoadBalancer selection, cache age, reconnect/fetch/watch log |
| Request path | Request count theo instance, success/error rate, latency, timeout |

Nếu registry đã loại instance nhưng consumer vẫn gọi nó, vấn đề nằm ở propagation hoặc cache phía consumer. Nếu registry còn giữ instance nhưng provider đã chết, cần xem detection/lease/session/health policy. Nếu registry và consumer đều thấy instance mới nhưng request thất bại, kiểm tra advertised host/port, network, TLS và readiness.

Không dùng riêng dashboard làm nguồn sự thật. Dashboard có thể refresh chậm hoặc hiển thị dữ liệu từ một cache khác. Ghi timestamp và instance ID để so sánh cùng một bản ghi qua các lớp.

## 12. Ghi nhận kết quả thí nghiệm

Mỗi lần chạy nên có một bản ghi thống nhất:

~~~yaml
experiment:
  id: provider-crash-001
  environment: discovery-staging
  service: inventory-service
  fault: abrupt-provider-stop
  target_instance: inventory-02
  started_at: "2026-11-24T10:00:00Z"
  expected:
    max_detection_seconds: 30
    max_consumer_removal_seconds: 60
    max_service_restore_seconds: 30
    max_false_evictions: 0
  observed:
    detection_seconds: 24
    consumer_removal_seconds: 47
    service_restore_seconds: 3
    stale_requests: 2
    false_evictions: 0
  result: PASS
~~~

Các con số trong YAML chỉ minh họa cách ghi kết quả, không phải kết quả đo thực tế hoặc SLO mặc định. Trong thí nghiệm thật, timestamp cần lấy từ log/metrics đã đồng bộ; không nhập số đo ước lượng để đánh dấu PASS.

Ghi thêm:

- Phiên bản Spring Boot, Spring Cloud và registry.
- Cấu hình lease/session/health/fetch/cache có hiệu lực.
- Số instance và consumer tại thời điểm chạy.
- Tải request nền.
- Fault rule chính xác và thời điểm cleanup.
- Link tới log, dashboard hoặc trace liên quan.
- Sai lệch so với giả thuyết và nguyên nhân đã xác nhận.

## 13. Tiêu chí PASS/FAIL

Một thí nghiệm chỉ PASS khi tất cả tiêu chí quan trọng đã được đo và nằm trong giới hạn đã đặt. Ví dụ:

| Tiêu chí | PASS khi | FAIL khi |
|---|---|---|
| Detection | Registry/agent nhận biết lỗi trong giới hạn | Lỗi không được phát hiện hoặc phát hiện quá trễ |
| Consumer convergence | Consumer ngừng chọn instance lỗi đúng hạn | Cache tiếp tục chọn instance lỗi quá thời hạn |
| Healthy availability | Instance khỏe vẫn được giữ lại | Instance khỏe bị loại nhầm vượt ngân sách |
| Service restore | Request chuyển sang instance khỏe đúng hạn | Request tiếp tục lỗi dù còn instance khỏe |
| Re-registration | Instance mới được đăng ký và chọn đúng hạn | Registration không trở lại hoặc metadata sai |
| Recovery stability | Không có vòng lặp register/evict liên tục sau phục hồi | Flapping hoặc retry storm tiếp diễn |
| Cleanup | Fault rule đã được gỡ và baseline được phục hồi | Còn rule gây lỗi hoặc tài nguyên thử nghiệm bị bỏ lại |

Nếu thiếu dữ liệu để tính một chỉ số, kết quả phải là **INCONCLUSIVE**, không tự đánh dấu PASS. Ví dụ, nếu không ghi được thời điểm provider thực sự chết, không thể tính detection latency chính xác.

## 14. Dừng thí nghiệm và khôi phục

Đặt điều kiện dừng trước khi chạy:

- Error rate vượt ngưỡng an toàn.
- Tỷ lệ instance healthy bị loại nhầm tăng bất thường.
- Registry mất quorum hoặc không phục vụ được các service ngoài phạm vi.
- Retry hoặc request queue tăng liên tục.
- Fault ảnh hưởng nhầm namespace, node hoặc service ID.
- Thời gian thí nghiệm vượt giới hạn.

Quy trình cleanup:

1. Gỡ proxy toxic, network rule hoặc chaos experiment.
2. Khôi phục provider/agent/node đã dừng.
3. Xác nhận registry quorum/leader và API hoạt động.
4. Xác nhận mọi instance mong đợi đã healthy và registration đúng.
5. Xác nhận consumer cache đã hội tụ và request thành công.
6. Kiểm tra không còn process, container hoặc fault rule thử nghiệm.
7. Lưu kết quả và ghi lại các sai lệch trước khi chạy thí nghiệm tiếp theo.

Khôi phục hạ tầng chưa đồng nghĩa discovery đã phục hồi. Chỉ kết thúc khi consumer thực sự có thể chọn instance khỏe và request kiểm chứng đạt tiêu chí.

## 15. Chuyển kết quả thành cải tiến

Nếu stale window vượt SLO, không nên chỉ giảm mọi interval. Trước hết xác định thời gian nằm ở bước nào:

- Detection chậm: xem health-check interval, timeout, lease/session expiration và khả năng probe.
- Registry update chậm: xem server load, self-preservation, agent sync, quorum hoặc catalog processing.
- Consumer update chậm: xem fetch interval, blocking query/watch, reconnect và local cache.
- Request restore chậm: xem LoadBalancer cache, retry, timeout, circuit breaker và số replica khỏe.
- False eviction: xem health endpoint quá nhạy, dependency check không phù hợp, JVM pause, network jitter và session timeout.
- Registration không trở lại: xem client reconnect, re-registration, duplicate ID, ACL, metadata và advertised address.

Mỗi thay đổi cấu hình cần có giả thuyết mới và chạy lại cùng thí nghiệm để so sánh trước/sau. Giữ lại baseline để tránh tối ưu một chỉ số bằng cách làm xấu chỉ số khác, chẳng hạn giảm stale window nhưng tăng false eviction.

## 16. Bộ thí nghiệm tối thiểu nên duy trì

Một bộ kiểm chứng định kỳ cho service discovery nên có:

1. Provider graceful shutdown và crash.
2. Provider mất kết nối tới registry/agent.
3. Consumer mất kết nối tới registry nhưng vẫn gọi provider.
4. Health endpoint timeout rồi phục hồi.
5. Registry node/agent restart.
6. Một đợt rolling deployment hoặc scale up/down.
7. Network latency/loss trong giới hạn đã định.
8. Session expiration và re-registration với ZooKeeper.
9. Eureka lease/eviction và consumer fetch convergence.
10. Consul health state, catalog query và agent reconnect.

Không phải môi trường nào cũng cần chạy toàn bộ thí nghiệm ở mọi lần deploy. Có thể phân tầng: test tự động trong pipeline cho lỗi đơn và contract; staging định kỳ cho network/registry failure; diễn tập vận hành theo lịch cho tình huống quorum hoặc mất nhiều node.

## 17. Nguyên tắc đặt tiêu chí phục hồi

- Đo riêng detection, registry convergence, consumer convergence và service restore.
- Đặt ngưỡng stale window, stale request ratio và false eviction.
- Chỉ tính instance mới phục hồi khi readiness, registration, discovery và request đều đạt.
- Phân biệt registration động có thể dựng lại với cấu hình registry cần lưu bền.
- Chạy từng fault đơn trước khi thử kết hợp nhiều lỗi.
- Thu thập bằng chứng từ provider, registry, consumer và request path.
- Điều chỉnh tiêu chí theo semantics của Eureka, Consul hoặc ZooKeeper.
- Ghi rõ phiên bản, cấu hình hiệu lực, thời gian và phạm vi thí nghiệm.
- Đánh dấu INCONCLUSIVE khi thiếu dữ liệu đo.
- Gỡ fault rule và xác minh toàn bộ luồng discovery trước khi kết thúc.

Một tiêu chí phục hồi có giá trị phải mô tả được người dùng dịch vụ sẽ thấy điều gì, trong bao lâu và bằng chứng nào xác nhận kết quả. Thí nghiệm gây lỗi biến các giả định về heartbeat, health check, cache, watch và session thành số đo thực tế. Khi đo từ provider tới registry, từ registry tới consumer và tới request cuối cùng, đội vận hành có thể xác định đúng nút thắt và cải thiện khả năng phục hồi mà không đánh đổi sự ổn định của instance khỏe.
