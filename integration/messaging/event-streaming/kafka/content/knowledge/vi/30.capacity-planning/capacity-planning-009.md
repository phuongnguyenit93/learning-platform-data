# Quản lý tenant, quota và phân bổ tài nguyên

Một Kafka cluster có thể phục vụ nhiều ứng dụng hoặc nhiều nhóm nghiệp vụ. Nếu mọi workload dùng chung broker mà không có quy tắc phân bổ, một tenant gửi dữ liệu đột biến hoặc consumer đọc quá nhanh có thể chiếm network, request handler, disk I/O và làm các tenant khác tăng latency. Đây là hiện tượng noisy neighbor.

Kafka cung cấp client quotas để giới hạn tốc độ produce, consume và tỷ lệ thời gian xử lý request. Tuy nhiên quota không tự tạo tenant, không thay thế ACL và cũng không đặt trước một phần CPU, RAM hay disk cho từng ứng dụng. Muốn chia sẻ cluster an toàn cần kết hợp identity, ACL, quota, naming policy, partition placement, capacity budget và monitoring.

## 1. Tenant trong Kafka là gì?

Apache Kafka không có một resource tenant độc lập tương tự database schema hoặc cloud account. Tenant thường là một ranh giới logic do platform team xây dựng quanh một workload, ứng dụng hoặc nhóm nghiệp vụ.

Một tenant nên có các thành phần nhận diện nhất quán:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Tenant ID | commerce-a | Định danh nhóm sử dụng cluster |
| Principal | User:commerce-a-orders | Identity được xác thực |
| Client ID | commerce-a-orders-producer | Nhận diện producer/consumer instance |
| Topic namespace | commerce-a.orders.events | Phân vùng tên topic |
| Consumer group | commerce-a.payments | Phân biệt tiến độ đọc |
| Quota profile | bronze, silver, gold | Chọn giới hạn throughput/request |
| Owner | Commerce platform | Chịu trách nhiệm workload và incident |

Ví dụ một tenant có thể sở hữu các topic commerce-a.orders.events, commerce-a.payments.events và group commerce-a.analytics. Việc đặt prefix chỉ giúp quản lý tên; nó không tự ngăn tenant khác truy cập. Phải dùng ACL và provisioning policy để thực thi ranh giới.

### Tenant không đồng nghĩa với một client ID

Một tenant thường có nhiều service account, producer và consumer. Nếu dùng một client ID chung cho tất cả workload, khó phân tích quota và không thể phân biệt producer bị nghẽn với consumer gây tải.

Nên đặt client ID theo workload/instance, ví dụ:

~~~text
commerce-a-orders-producer
commerce-a-payment-consumer-01
commerce-a-analytics-consumer-02
~~~

Principal phản ánh danh tính được xác thực; client ID giúp phân loại ứng dụng và quan sát. Client ID do client khai báo nên không nên xem nó là bằng chứng bảo mật hoặc ranh giới tenant duy nhất.

## 2. Các lớp kiểm soát tenant

Quản lý tenant cần nhiều lớp vì mỗi lớp giải quyết một vấn đề khác nhau:

~~~mermaid
flowchart TD
    A[Workload / Tenant] --> B[Authentication]
    B --> C[Principal]
    C --> D[ACL authorization]
    D --> E[Client quotas]
    E --> F[Broker and partition capacity]
    F --> G[Metrics, alerts and chargeback]
~~~

| Lớp | Câu hỏi | Cơ chế |
|---|---|---|
| Authentication | Workload là ai? | SASL/SCRAM, mTLS, OAuth, Kerberos |
| Authorization | Được truy cập resource nào? | ACL trên topic, group, cluster và resource khác |
| Quota | Được dùng throughput/request ở mức nào? | Producer byte rate, consumer byte rate, request percentage |
| Placement | Partition và leader nằm ở đâu? | Partition assignment, rack awareness, reassignment |
| Capacity | Cluster có đủ CPU, disk, network không? | Sizing, headroom, benchmark và scaling |
| Observability | Ai đang dùng tài nguyên và gây tải? | Client/broker metrics, trace, logs, dashboards |
| Governance | Ai sở hữu và được thay đổi gì? | Catalog, naming policy, approval và audit |

Quota không thay thế ACL. ACL không giới hạn throughput. Naming convention không tự tạo isolation. Cần thiết kế cả ba.

## 3. Kafka client quotas giới hạn những gì?

Kafka có các loại client quota phổ biến:

| Quota | Ý nghĩa | Đơn vị |
|---|---|---|
| producer_byte_rate | Giới hạn tốc độ dữ liệu client produce | bytes/second |
| consumer_byte_rate | Giới hạn tốc độ dữ liệu client fetch/consume | bytes/second |
| request_percentage | Giới hạn tỷ lệ thời gian request handler mà client được sử dụng | Phần trăm |

Producer quota bảo vệ broker khỏi một producer gửi dữ liệu quá nhanh. Consumer quota kiểm soát tốc độ dữ liệu fetch từ broker. Request percentage giúp hạn chế phần thời gian xử lý request mà một client được tiêu thụ.

Các quota này được thực thi bằng throttling. Client có thể nhận response chậm hơn và thấy throttle time tăng. Đây là cơ chế điều tiết lưu lượng, không phải một bộ lập lịch bảo đảm mỗi tenant luôn nhận được một mức throughput tối thiểu.

### Quota không phải hard resource reservation

Quota không đảm bảo:

- Một số core CPU cố định cho tenant.
- Một lượng RAM/heap hoặc page cache cố định.
- Một dung lượng disk riêng.
- Một số partition hoặc leader cố định.
- Một mức latency tuyệt đối trong mọi tình huống.
- Một băng thông tối thiểu khi cluster đã bão hòa vì workload khác hoặc lỗi hạ tầng.

Nếu cần isolation cứng về CPU, memory, disk, network hoặc compliance boundary, cân nhắc broker pool/cluster riêng, node pool riêng hoặc hạ tầng tách biệt. Shared cluster với ACL và quota phù hợp cho nhiều workload có mức tin cậy và yêu cầu isolation tương thích.

## 4. Quota được áp dụng theo user và client ID

Kafka cho phép cấu hình quota theo user, theo client ID hoặc theo cặp user/client ID. Cách chọn ảnh hưởng trực tiếp tới khả năng cô lập tenant.

| Scope | Ví dụ | Nhận xét |
|---|---|---|
| User | User:commerce-a-orders | Gắn với principal sau authentication |
| Client ID | commerce-a-orders-producer | Phân loại workload nhưng client có thể tự khai báo |
| User + client ID | User:commerce-a-orders và client ID orders-writer | Có thể áp dụng quota cụ thể cho workload của principal |
| Default user/client | Mọi identity chưa có quota cụ thể | Tạo baseline để tránh client không giới hạn |

Với ranh giới tenant bảo mật, quota theo user thường đáng tin cậy hơn quota chỉ theo client ID vì principal được tạo từ authentication. Client ID vẫn hữu ích để tách producer và consumer hoặc các workload khác nhau của cùng một service account.

Kafka áp dụng quota theo scope cụ thể nhất phù hợp với client. Một cấu hình cụ thể cho cặp user/client có thể ghi đè quota rộng hơn. Không giả định các quota ở nhiều scope luôn cộng dồn; kiểm tra cấu hình hiệu lực theo phiên bản và entity đang dùng.

### Client ID không phải danh tính bảo mật

Client có thể đặt client.id trong cấu hình. Một ứng dụng có thể khai báo client ID giống tenant khác nếu không có governance ở lớp provisioning. Vì vậy:

- Dùng principal riêng cho từng tenant/workload.
- Dùng ACL để giới hạn topic/group theo principal.
- Dùng client ID để phân tích quota và metric.
- Không dựa vào client ID đơn lẻ để quyết định quyền truy cập.

## 5. Thiết kế namespace cho tenant

Tên topic, group và principal nên có quy tắc dễ nhận diện và dễ áp dụng ACL:

~~~text
Principal:
  User:commerce-a-orders
  User:commerce-a-payments

Topics:
  commerce-a.orders.events
  commerce-a.payments.events
  commerce-a.orders.dlt

Consumer groups:
  commerce-a.payments
  commerce-a.analytics

Client IDs:
  commerce-a-orders-producer
  commerce-a-payments-consumer
~~~

Naming policy cần xác định:

- Prefix/suffix của tenant.
- Environment như dev, staging, prod.
- Owner và contact.
- Data classification.
- Retention và cleanup policy.
- Replication factor và min ISR.
- Schema compatibility policy.
- Consumer group và transactional ID namespace.
- Quota profile và giới hạn partition/topic.

Tên có prefix không tự tạo security boundary. ACL phải khớp principal và resource pattern; cần kiểm thử tenant A không thể đọc/ghi topic tenant B.

## 6. ACL và quota có trách nhiệm khác nhau

ACL trả lời principal được thực hiện operation nào trên resource. Quota điều tiết tốc độ sử dụng của client. Một tenant có thể có quyền WRITE vào topic nhưng vẫn bị throttle khi vượt quota.

| Tình huống | ACL | Quota |
|---|---|---|
| Tenant không được đọc topic | Deny READ | Không liên quan |
| Tenant được ghi nhưng gửi quá nhanh | Allow WRITE | Throttle producer |
| Consumer được đọc nhưng fetch quá nhiều | Allow READ | Throttle consumer |
| Client ID giả mạo tên tenant khác | ACL vẫn dựa trên principal/resource | Quota client ID có thể bị áp dụng theo tên client ID khai báo |
| Tenant tạo topic ngoài namespace | ACL/policy provisioning từ chối | Quota không thay thế kiểm soát tạo topic |

Ví dụ cấp quyền producer chỉ ghi topic của tenant:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:commerce-a-orders \
  --operation Write \
  --topic commerce-a.orders.events
~~~

Ví dụ cấp quyền consumer đọc topic và dùng group trong namespace tenant:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:commerce-a-payments \
  --operation Read \
  --topic commerce-a.orders.events

kafka-acls.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:commerce-a-payments \
  --operation Read \
  --group commerce-a.payments
~~~

Principal trong ACL phải là principal cuối cùng sau authentication/principal mapping. Không đưa prefix tenant vào ACL theo suy đoán nếu principal thực tế khác tên.

Không cấp quyền ALL để giải quyết quota throttle. Không giảm quota để sửa authorization error. Xác định đúng lớp trước khi thay đổi.

## 7. Cấu hình producer byte-rate quota

Ví dụ đặt giới hạn produce cho user tenant:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-name commerce-a-orders \
  --add-config 'producer_byte_rate=1048576'
~~~

Giá trị 1.048.576 bytes/second tương đương khoảng 1 MiB/s theo cách tính nhị phân. Đây là quota minh họa, không phải sizing khuyến nghị cho mọi tenant.

Nếu muốn giới hạn theo client ID:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type clients \
  --entity-name commerce-a-orders-producer \
  --add-config 'producer_byte_rate=1048576'
~~~

Producer quota có thể điều tiết tốc độ produce tại broker. Nó không giới hạn số record chính xác nếu record size khác nhau; cùng một record rate nhưng payload lớn hơn sẽ tiêu thụ byte quota nhanh hơn.

## 8. Cấu hình consumer byte-rate quota

Ví dụ giới hạn consumer fetch cho một user:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-name commerce-a-payments \
  --add-config 'consumer_byte_rate=2097152'
~~~

Giới hạn trên tương đương khoảng 2 MiB/s. Consumer có thể fetch chậm hơn khi vượt quota; lag có thể tăng nếu producer ingest cao hơn tốc độ consumer được phép đọc.

Nếu nhiều consumer cùng dùng một principal, quota user có thể áp dụng chung cho lưu lượng của principal đó theo cơ chế quota của broker. Nếu cần phân biệt workload, dùng service principal/client ID riêng và kiểm tra cách quota scope được resolve.

Consumer quota không phải quota theo consumer group. Kafka client quota thường dựa trên user/client ID; group ID không phải khóa quota mặc định. Nếu cần policy theo group, cần governance ở provisioning/application layer hoặc thiết kế identity riêng cho workload.

## 9. Cấu hình request percentage quota

Request percentage giới hạn tỷ lệ thời gian request handler mà client có thể sử dụng. Nó hữu ích khi một workload tạo nhiều request nhỏ hoặc tốn CPU dù byte rate không cao.

Ví dụ:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-name commerce-a-orders \
  --add-config 'request_percentage=25'
~~~

Giá trị 25 là ví dụ quota request percentage. Nó không có nghĩa tenant được bảo đảm 25% CPU của toàn cluster. Đây là giới hạn theo cơ chế request quota trên broker; tài nguyên CPU thực tế còn phụ thuộc request mix, partition placement, broker load và workload khác.

Request percentage có thể hữu ích với workload có nhiều metadata/admin request hoặc request processing nặng. Cần đo request handler utilization và throttle time trước khi điều chỉnh.

## 10. Quota mặc định và quota riêng

Default quota tạo baseline cho client chưa có cấu hình riêng. Ví dụ đặt producer quota mặc định cho user:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-default \
  --add-config 'producer_byte_rate=524288'
~~~

Có thể đặt default quota cho client ID:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type clients \
  --entity-default \
  --add-config 'consumer_byte_rate=1048576'
~~~

Giá trị default phải phù hợp với loại workload chung. Nếu quá thấp, service mới có thể bị throttle ngay khi onboarding. Nếu quá cao, default không còn bảo vệ cluster khỏi noisy neighbor.

Nên có:

- Default quota bảo vệ cluster.
- Quota riêng theo tenant tier.
- Quota cụ thể cho workload có đặc tính khác nhau.
- Quy trình exception có owner, expiry và review.

## 11. Xem quota đang áp dụng

Kiểm tra quota của user:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --describe \
  --entity-type users \
  --entity-name commerce-a-orders
~~~

Kiểm tra quota theo client ID:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --describe \
  --entity-type clients \
  --entity-name commerce-a-orders-producer
~~~

Kiểm tra default quota:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --describe \
  --entity-type users \
  --entity-default
~~~

Lưu output cùng tenant ID, principal, client ID, quota profile, người thay đổi và timestamp. Khi điều tra throttle, cần biết quota nào đang có hiệu lực chứ không chỉ đọc một file cấu hình cũ.

## 12. Thay đổi và gỡ quota

Quota động thường có thể được cập nhật mà không cần restart broker. Ví dụ đổi producer rate:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-name commerce-a-orders \
  --add-config 'producer_byte_rate=2097152'
~~~

Gỡ một quota riêng:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --command-config admin.properties \
  --alter \
  --entity-type users \
  --entity-name commerce-a-orders \
  --delete-config producer_byte_rate
~~~

Gỡ override có nghĩa client quay về quota ở scope rộng hơn nếu có, không nhất thiết trở thành không giới hạn. Luôn describe lại sau thay đổi để xác minh cấu hình hiệu lực.

Không xóa quota mặc định trong giờ cao điểm nếu chưa đánh giá tác động. Thay đổi từ quota riêng về default có thể làm workload bị throttle mạnh hơn hoặc nới lỏng hơn tùy cấu hình.

## 13. Quota được thực thi theo broker

Kafka quota được broker thực thi. Vì vậy, quota cấu hình không nên được hiểu như một bộ giới hạn cluster-wide duy nhất có một counter toàn cục. Lưu lượng của client có thể đi qua nhiều broker; tổng throughput quan sát được còn phụ thuộc số broker tham gia, partition leader placement và cách traffic phân bố.

Ví dụ một producer ghi vào nhiều partition có leader trên nhiều broker. Mỗi broker áp dụng quota theo cơ chế của mình. Nếu leader của một tenant tập trung trên một broker, broker đó có thể throttle workload sớm hơn các broker khác dù tổng cluster còn capacity.

Hệ quả:

- Không suy ra cluster-wide cap bằng cách chỉ đọc một broker.
- Quan sát throttle và traffic trên từng broker.
- Cân bằng leader/partition placement.
- Benchmark với topology tương tự production.
- Khi đặt quota, tính đến số broker mà client thực sự tương tác.

Đây cũng là lý do quota không thay thế capacity planning và load balancing.

## 14. Quota profile theo tier

Platform team có thể định nghĩa các tier để onboarding nhất quán. Các giá trị dưới đây chỉ là ví dụ chính sách; cần benchmark và đo capacity trước khi áp dụng.

| Tier | Producer quota | Consumer quota | Request quota | Mục đích |
|---|---:|---:|---:|---|
| Bronze | 512 KiB/s | 1 MiB/s | 10% | Workload nhỏ, không critical |
| Silver | 2 MiB/s | 4 MiB/s | 20% | Workload production thông thường |
| Gold | 8 MiB/s | 16 MiB/s | 40% | Workload có throughput lớn |
| Exception | Theo capacity review | Theo capacity review | Theo capacity review | Workload đặc biệt có owner và expiry |

Tier không phải cam kết SLA nếu cluster chưa có capacity headroom. Tổng quota được cấp có thể lớn hơn capacity thực tế nếu mọi tenant cùng đạt peak; cần oversubscription policy có kiểm soát và admission planning.

Một tenant có producer lớn và consumer analytics riêng có thể cần quota profile khác với service chỉ consume. Không áp dụng cùng quota một cách máy móc cho mọi client ID.

## 15. Tính capacity budget theo tenant

Capacity planning bắt đầu từ workload profile:

- Producer ingress bytes/s theo tenant.
- Consumer egress bytes/s và số consumer group đọc toàn bộ stream.
- Record size distribution.
- Compression ratio thực tế.
- Replication factor và partition/leader placement.
- Retention duration và cleanup policy.
- Peak multiplier, retry/replay burst và recovery traffic.

### Ước tính storage

Một ước tính sơ bộ:

~~~text
Raw retained bytes
  = ingress bytes/second
    × retention seconds

Approximate replicated storage
  = raw retained bytes
    × compression ratio
    × replication factor
~~~

Ví dụ tenant produce trung bình 1 MiB/s, retention 7 ngày, compression ratio đo được 0,5 và RF=3:

~~~text
Retention seconds = 7 × 24 × 60 × 60 = 604800
Raw bytes = 1 MiB/s × 604800 s = 590.6 GiB
Compressed bytes per replica ≈ 295.3 GiB
Three replicas ≈ 885.9 GiB
~~~

Con số này chưa gồm index/segment overhead, compaction, tombstone, temporary reassignment copies, burst traffic và free-space headroom. Hãy cộng reserve phù hợp theo storage platform và recovery objective; không dùng phép tính này làm sizing cuối cùng.

### Ước tính network

Network budget cần tính:

- Producer gửi dữ liệu tới partition leader.
- Leader gửi replication data tới follower.
- Consumer group fetch dữ liệu từ broker.
- Nhiều consumer group có thể đọc lại cùng stream.
- Reassignment, recovery và cross-rack/cross-zone traffic.

Một luồng có ba consumer group đọc toàn bộ topic có thể tạo egress xấp xỉ ba lần lượng dữ liệu mỗi group đọc, chưa tính protocol overhead và compression khác nhau. Replication factor cũng làm tăng inter-broker traffic.

### Ước tính partition và CPU

Partition count cần dựa trên throughput benchmark, parallelism yêu cầu, record key distribution và giới hạn vận hành. Kafka không cung cấp quota partition/topic per tenant như một client byte quota phổ biến; platform provisioning service cần áp dụng policy cho số topic, partition, RF và retention.

CPU budget phải xét request mix, compression, TLS/SASL, serialization, transaction, compaction và replication. Request percentage quota có thể giúp điều tiết request processing nhưng không phải reservation core.

## 16. Quota không giới hạn disk hoặc số partition

Client byte quota kiểm soát tốc độ produce/fetch, nhưng không trực tiếp giới hạn:

- Tổng dung lượng topic của tenant.
- Số topic tenant tạo.
- Số partition tenant sử dụng.
- Replication factor tenant yêu cầu.
- Retention duration.
- Kích thước message tối đa.
- Số consumer group hoặc transactional ID.

Những giới hạn này nên được quản lý qua provisioning workflow, policy-as-code, ACL và kiểm tra trước khi tạo topic.

Ví dụ một topic request nên được kiểm tra:

| Thuộc tính | Policy cần xét |
|---|---|
| Topic name | Đúng namespace tenant |
| Owner | Có service/team chịu trách nhiệm |
| Partition count | Phù hợp throughput và parallelism |
| Replication factor | Đáp ứng durability và rack placement |
| min.insync.replicas | Phù hợp acks và durability requirement |
| Retention | Có budget disk và data lifecycle |
| cleanup.policy | Delete/compact theo semantics |
| max.message.bytes | Phù hợp contract và broker capacity |
| ACL | Principal chỉ truy cập resource cần thiết |
| Quota profile | Được gán theo workload và tier |

## 17. Phân bổ tài nguyên và lựa chọn shared/dedicated cluster

Có ba mô hình thường gặp:

| Mô hình | Cách làm | Ưu điểm | Hạn chế |
|---|---|---|---|
| Shared cluster | Nhiều tenant dùng chung broker, ACL và quotas | Hiệu quả tài nguyên, vận hành tập trung | Noisy neighbor và blast radius lớn hơn |
| Broker pool/node pool tách workload | Phân workload theo cluster hoặc pool riêng | Giảm tranh chấp và dễ capacity planning | Tốn tài nguyên và vận hành phức tạp hơn |
| Dedicated cluster per tenant | Tenant có cluster riêng | Isolation mạnh, dễ đặt SLO riêng | Chi phí cao và nhiều cluster cần quản lý |

Chọn shared cluster khi tenant có trust level và workload phù hợp, có thể điều tiết bằng quota, ACL và governance. Chọn dedicated cluster khi cần isolation cứng, compliance boundary, workload rất lớn/khó dự đoán hoặc blast radius không thể chia sẻ.

Không dùng quota để thay thế isolation vật lý khi yêu cầu là tenant này không được ảnh hưởng tenant khác trong mọi tình huống.

## 18. Partition placement và leader balance

Quota được thực thi trên broker, nên placement ảnh hưởng cách quota và capacity biểu hiện. Nếu tất cả partition nóng của tenant cùng có leader trên một broker, broker đó có thể trở thành bottleneck.

Theo dõi:

- LeaderCount và partition count theo broker.
- BytesIn/BytesOut theo broker và topic.
- Request latency và throttle time.
- Disk utilization/latency theo log directory.
- Replica placement theo rack/failure domain.
- Consumer lag theo partition.

Reassignment có thể cân bằng leader/replica placement nhưng tạo network và disk traffic. Thực hiện trong change window, có throttle và theo dõi URP/ISR. Không reassignment đồng loạt chỉ để làm số partition trên broker bằng nhau nếu workload partition không đồng đều.

## 19. Quota throttling và metric cần quan sát

Khi quota bị vượt, broker có thể trì hoãn request và gửi throttle time trong response. Cần quan sát cả client và broker:

| Metric/dấu hiệu | Thành phần | Ý nghĩa |
|---|---|---|
| produce-throttle-time-avg/max | Producer client | Thời gian producer bị throttle |
| fetch-throttle-time-avg/max | Consumer client | Thời gian fetch bị throttle |
| Produce request throttle time | Broker | Throttle đối với produce request |
| Fetch request throttle time | Broker | Throttle đối với fetch request |
| BytesInPerSec / BytesOutPerSec | Broker | Throughput thực tế |
| RequestHandlerAvgIdlePercent | Broker | Mức rảnh của request handler |
| RequestQueueTimeMs | Broker | Request queue pressure |
| Consumer lag | Consumer group | Backlog có thể tăng khi consumer bị giới hạn |
| Producer bufferpool wait | Producer | Backpressure ở client |

Tên JMX metric cụ thể và exporter naming phụ thuộc Kafka/client version. Kiểm tra MBean thực tế và metric catalog trước khi viết alert.

### Phân biệt throttle do quota với broker saturation

| Quan sát | Khả năng |
|---|---|
| Throttle time tăng, broker còn idle, client throughput chạm quota | Quota đang hoạt động như thiết kế |
| Throttle time thấp nhưng request latency và queue time cao | Broker saturation hoặc dependency chậm |
| Consumer lag tăng, fetch throttle tăng | Consumer quota có thể giới hạn tốc độ đọc |
| Producer retry/error tăng nhưng throttle không tăng | Có thể là network, timeout, ISR hoặc broker error |
| Chỉ một broker throttle mạnh | Partition leader placement hoặc traffic skew |

Không tăng quota chỉ vì thấy throttle time. Trước tiên xác minh tenant có đang vượt allocation đã thống nhất hay quota được đặt quá thấp so với workload đã duyệt.

## 20. Onboarding tenant

Một quy trình onboarding nên tự động hóa các bước lặp lại:

1. Nhận tenant ID, owner, environment và use case.
2. Xác định principal/service account và authentication mechanism.
3. Cấp ACL giới hạn đúng topic/group namespace.
4. Tạo topic qua provisioning workflow, không cho client tự tạo ngoài policy.
5. Xác định partition, RF, min ISR, retention và cleanup policy.
6. Chọn quota profile theo producer/consumer workload.
7. Gán client ID convention.
8. Thiết lập dashboard/alerts và ownership labels.
9. Chạy smoke test: allowed access thành công, out-of-scope access bị từ chối.
10. Đo baseline và xác nhận capacity headroom trước khi tăng tải.

Provisioning record nên lưu tenant, principal, topic list, group list, quota scope/value, owner, ticket và thời điểm hết hạn của exception.

## 21. Điều chỉnh quota khi workload thay đổi

Quota cần được review khi:

- Tenant tăng throughput hoặc thêm consumer group.
- Thay đổi record size/compression.
- Tăng retention hoặc replication factor.
- Chuyển partition leader sang broker khác.
- Thêm batch replay/backfill.
- Chạy migration hoặc incident recovery.
- Thay đổi tier/SLO.

Quy trình thay đổi:

1. Đo baseline và workload forecast.
2. Kiểm tra headroom trên từng broker, không chỉ tổng cluster.
3. Tính ảnh hưởng tới disk/network/replication và các tenant khác.
4. Đề xuất quota mới và thời gian áp dụng.
5. Cập nhật bằng Admin API/CLI qua change control.
6. Đọc lại quota hiệu lực.
7. Theo dõi throttle, p99, lag, ISR và broker resources.
8. Rollback nếu guardrail bị vi phạm.

Quota exception nên có expiry. Nếu exception không có ngày review, các giới hạn tạm thời có thể trở thành cấu hình vĩnh viễn mà không được capacity planning.

## 22. Công bằng và noisy neighbor

Quota giúp hạn chế một tenant chiếm quá nhiều throughput, nhưng công bằng không tự động xảy ra. Nếu một tenant có nhiều principal/client ID và được cấp quota riêng cho từng identity, tổng allocation của tenant có thể lớn hơn dự kiến.

Các nguyên tắc:

- Gắn quota với principal tenant đáng tin cậy.
- Quản lý tổng quota của tenant qua inventory.
- Hạn chế số service account và client identity không cần thiết.
- Đặt default quota để workload mới không unlimited.
- Theo dõi tổng traffic theo tenant, không chỉ từng client.
- Phân bổ leader/partition để tránh broker nóng.
- Dự trữ capacity cho replication, recovery và control-plane.

Không cộng quota danh nghĩa thành capacity cluster mà không tính concurrency và per-broker enforcement. Nếu tổng quota được cấp vượt capacity bền vững, nhiều tenant có thể cùng bị throttle khi peak đồng thời.

## 23. Gỡ tenant và thu hồi tài nguyên

Khi tenant ngừng sử dụng:

1. Xác nhận owner và thời điểm ngừng.
2. Dừng producer/consumer/connector/Streams workload.
3. Export offsets, config hoặc dữ liệu cần giữ.
4. Xác minh retention/legal hold và backup.
5. Thu hồi ACL và credential theo quy trình.
6. Gỡ quota riêng, xác minh tenant quay về default hoặc không còn client.
7. Xóa topic chỉ khi có approval và recovery decision riêng.
8. Dọn dashboard, alert, catalog và ownership metadata.

Không xóa topic chỉ vì quota tenant đã được gỡ. Không xóa quota trước khi hiểu client còn hoạt động hay không; client có thể quay về default quota và gây tải ngoài dự kiến.

## 24. Bài thực hành: tạo hai tenant dùng chung cluster

Tạo lab có hai tenant commerce-a và commerce-b, mỗi tenant có principal, producer, consumer và topic namespace riêng.

1. Tạo principal/service account riêng cho mỗi tenant.
2. Tạo topic commerce-a.orders và commerce-b.orders.
3. Cấp ACL để tenant A chỉ ghi/đọc topic A, tenant B chỉ ghi/đọc topic B.
4. Cấu hình producer byte quota khác nhau cho hai user.
5. Cấu hình consumer byte quota và request percentage.
6. Đặt default quota cho user/client chưa có profile.
7. Tạo producer với client ID rõ ràng và gửi dữ liệu đồng thời.
8. Quan sát producer throttle time và broker BytesInPerSec.
9. Tạo consumer đọc liên tục, quan sát fetch throttle và consumer lag.
10. Thay quota trong lab và xác minh hiệu lực bằng describe.
11. Thử tenant A truy cập topic B; xác minh ACL từ chối dù quota còn dư.
12. Xóa quota override và xác minh cấu hình default được áp dụng.
13. So sánh traffic khi partition leader phân bố đều và khi một broker bị nóng.

Chỉ chạy load test, quota stress và thay đổi ACL trên cluster lab. Không dùng credential tenant thử nghiệm trên cluster production.

## 25. Checklist production

- Mỗi tenant có owner, principal và namespace rõ ràng.
- Authentication tạo principal ổn định; client ID chỉ dùng phân loại workload.
- ACL giới hạn topic/group/resource theo tenant.
- Quota được đặt theo user/client scope phù hợp.
- Có default quota cho workload chưa có profile riêng.
- Đã hiểu quota resolution và per-broker enforcement của Kafka version.
- Tổng quota allocation nằm trong capacity budget có headroom.
- Producer, consumer và request percentage được cân nhắc riêng.
- Có policy cho topic count, partition count, RF, retention và message size.
- Leader/replica placement không tạo broker hotspot.
- Theo dõi throttle time, bytes in/out, request queue, lag và ISR.
- Quota exception có owner, ticket và expiry.
- Thay đổi quota có readback, monitoring và rollback.
- Dùng dedicated cluster khi yêu cầu isolation vượt khả năng quota/ACL.
- Có quy trình onboarding, review và offboarding tenant.

## 26. Những nhầm lẫn thường gặp

- **Kafka có tenant object native:** tenant thường là mô hình logic do platform xây dựng từ principal, ACL, namespace và quota.
- **Quota thay thế ACL:** quota giới hạn tốc độ; ACL quyết định quyền truy cập resource.
- **Client ID là identity bảo mật:** client tự khai báo client ID; principal mới gắn với authentication.
- **Quota là giới hạn cluster-wide duy nhất:** quota được broker thực thi; tổng throughput còn phụ thuộc broker và partition placement.
- **Quota bảo đảm CPU tối thiểu:** request percentage là giới hạn sử dụng request handler, không phải CPU reservation.
- **Consumer quota được gắn trực tiếp với group ID:** client quota phổ biến dựa trên user/client ID; group ID không phải scope mặc định.
- **Quota giới hạn số topic/partition:** cần provisioning policy để kiểm soát các tài nguyên đó.
- **Throttle luôn là lỗi:** throttle có thể là hành vi bảo vệ cluster đúng theo allocation.
- **Tăng quota luôn giải quyết lag:** broker, partition skew, downstream và consumer processing có thể mới là bottleneck.
- **Gỡ quota nghĩa là client bị chặn:** client có thể quay về quota default hoặc scope rộng hơn.
- **Replication factor chỉ ảnh hưởng disk:** RF còn làm tăng replication network và follower I/O.
- **Shared cluster với quota tạo isolation cứng:** quota không tách CPU, RAM, disk và failure domain hoàn toàn.

Quản lý tenant trên Kafka là sự kết hợp giữa danh tính, quyền truy cập, quota và capacity governance. Principal xác định workload; ACL giới hạn resource; quota điều tiết throughput/request; provisioning policy quản lý topic, partition, retention và replication. Để tránh noisy neighbor, phải đo tải theo tenant và broker, giữ headroom cho peak/recovery, kiểm soát exception và chọn dedicated cluster khi cần isolation cứng.
