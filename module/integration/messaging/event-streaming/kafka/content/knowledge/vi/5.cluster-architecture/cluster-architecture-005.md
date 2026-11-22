# Data plane, control plane và các loại listener

Một cụm Apache Kafka vừa phải truyền dữ liệu sự kiện với thông lượng cao, vừa phải duy trì metadata để các broker và client biết dữ liệu nằm ở đâu. Hai nhóm trách nhiệm này thường được mô tả là **data plane** và **control plane**. Hiểu ranh giới giữa chúng giúp người vận hành phân tích luồng produce/fetch, sự cố broker, thay đổi leader và cấu hình mạng.

Listener là các endpoint mạng mà broker hoặc controller mở để nhận kết nối. Một cụm có thể cung cấp endpoint cho ứng dụng, endpoint cho giao tiếp giữa broker và endpoint riêng cho KRaft controller. Cấu hình listener đúng phải đồng thời bảo đảm tiến trình bind được địa chỉ, client nhận được địa chỉ quảng bá có thể truy cập và giao thức bảo mật phù hợp với từng loại kết nối.

Bài học này giải thích cách data plane và control plane phối hợp, vai trò của KRaft controller, cách client khám phá metadata, các loại listener thường gặp và cách tổ chức endpoint cho môi trường nội bộ, bên ngoài hoặc Docker.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt luồng dữ liệu produce/fetch với luồng quản lý metadata của cụm Kafka.
- Mô tả vai trò của broker, active controller và controller quorum trong KRaft.
- Giải thích vì sao controller không trực tiếp xử lý từng record produce hoặc fetch.
- Phân biệt listeners với advertised.listeners và mô tả quy trình metadata discovery.
- Nhận diện client listener, inter-broker listener và controller listener.
- Chọn endpoint và security protocol phù hợp cho mạng nội bộ, mạng ngoài và môi trường container.
- Chẩn đoán các lỗi kết nối thường gặp do quảng bá hostname hoặc port không thể truy cập.

## 1. Hai nhóm trách nhiệm trong một cụm Kafka

### Data plane: truyền và lưu record

Data plane là đường xử lý dữ liệu của Kafka. Các hoạt động tiêu biểu gồm:

- Producer gửi ProduceRequest đến broker đang làm leader của partition.
- Broker append record batch vào log partition.
- Follower replica fetch dữ liệu từ leader để nhân bản.
- Consumer gửi FetchRequest đến broker có bản sao phù hợp và đọc record theo offset.
- Client trao đổi dữ liệu và metadata qua các kết nối mạng đã được thiết lập.

Ví dụ, producer gửi một sự kiện OrderCreated vào topic orders.events. Sau khi xác định partition leader, producer gửi request đến broker đó. Broker kiểm tra request, append batch vào log cục bộ và phản hồi theo cấu hình xác nhận. Các follower replica tiếp tục fetch dữ liệu từ leader để duy trì bản sao.

### Control plane: quản lý trạng thái và metadata cụm

Control plane quản lý thông tin mô tả cụm Kafka, chẳng hạn:

- Broker và controller nào đang là thành viên cụm.
- Topic nào tồn tại và topic có những partition nào.
- Partition nào có leader, replica nào thuộc ISR.
- Cấu hình topic và các thay đổi metadata.
- Quá trình bầu hoặc chuyển leader khi trạng thái cụm thay đổi.
- Trạng thái metadata được lưu và đồng bộ trong KRaft quorum.

Trong kiến trúc KRaft, controller quorum dùng cơ chế đồng thuận Raft để duy trì metadata log. Một controller đang active xử lý các thay đổi metadata; các controller voter còn lại tham gia duy trì bản sao metadata và bầu active controller khi cần. Broker nhận metadata cập nhật để biết cách phục vụ request dữ liệu.

Có thể hình dung mối quan hệ như sau:

~~~mermaid
flowchart TB
    subgraph CP["Control plane - KRaft"]
      A["Admin / broker request"] --> C["Active controller"]
      C <--> Q["Controller quorum<br/>metadata log"]
      C --> M["Metadata cập nhật"]
    end
    subgraph DP["Data plane - Brokers"]
      P["Producer"] --> L["Partition leader"]
      L --> F["Follower replicas"]
      L --> U["Consumer"]
    end
    M --> L
    M --> F
    M --> P
    M --> U
~~~

Control plane và data plane là cách phân loại trách nhiệm, không nhất thiết là hai mạng vật lý hoàn toàn tách biệt. Chúng có thể dùng các endpoint và mạng khác nhau để giới hạn quyền truy cập, nhưng việc tách mạng cần được thiết kế và cấu hình rõ ràng.

## 2. Luồng produce/fetch và vai trò của broker

Broker là tiến trình Kafka phục vụ request từ client, lưu partition replica và tham gia giao tiếp nội bộ cụm. Trong một partition, leader là replica nhận ghi và thường phục vụ đọc; follower fetch dữ liệu từ leader để theo kịp log.

Luồng produce điển hình:

1. Producer kết nối đến một bootstrap broker.
2. Client lấy metadata của topic và xác định broker đang giữ leader của partition đích.
3. Producer gửi ProduceRequest đến broker leader.
4. Leader append record batch vào log partition.
5. Follower replica fetch dữ liệu từ leader theo cơ chế replication.
6. Leader phản hồi producer theo cấu hình acks và trạng thái ISR.

Luồng fetch điển hình:

1. Consumer kết nối bootstrap broker và lấy metadata.
2. Consumer xác định broker đang giữ leader của partition được gán.
3. Consumer gửi FetchRequest đến broker phù hợp.
4. Broker trả về các record có offset đáp ứng vị trí fetch.
5. Consumer xử lý record và commit offset theo chính sách ứng dụng.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Bootstrap broker
    participant L as Partition leader
    participant F as Follower
    participant C as Consumer

    P->>B: Kết nối bootstrap và yêu cầu metadata
    B-->>P: Metadata: partition leader
    P->>L: ProduceRequest
    L->>L: Append record batch
    F->>L: Fetch dữ liệu replication
    L-->>P: ProduceResponse theo acks
    C->>B: Kết nối bootstrap và yêu cầu metadata
    B-->>C: Metadata: partition leader
    C->>L: FetchRequest từ offset
    L-->>C: Record batch
~~~

Producer và consumer không cần gửi mọi record qua một broker trung tâm. Sau khi có metadata, client kết nối đến broker phù hợp với partition mà nó cần ghi hoặc đọc. Đây là một lý do Kafka có thể mở rộng tải theo partition và broker.

### Broker không đồng nghĩa với controller

Broker phục vụ dữ liệu và một số vai trò điều phối ở cấp dịch vụ. Ví dụ, consumer group coordinator quản lý membership, assignment và committed offset của một group; transaction coordinator quản lý trạng thái giao dịch producer. Những coordinator này là vai trò ở phía broker, không phải KRaft controller.

KRaft controller quản lý metadata cấp cụm. Nó không nhận từng record của ứng dụng để ghi vào partition và cũng không xử lý heartbeat của mọi consumer group thay cho group coordinator.

Sự phân biệt này giúp khoanh vùng sự cố. Ví dụ:

- Producer không ghi được vào partition leader có thể là vấn đề data path, leader hoặc kết nối client.
- Consumer group liên tục rebalance có thể liên quan đến membership, heartbeat, poll hoặc group coordinator.
- Không thể tạo topic hoặc metadata không được cập nhật có thể liên quan đến controller quorum hoặc control path.
- Controller mất quorum có thể làm các thay đổi metadata bị đình trệ, dù một số luồng produce/fetch đang hoạt động vẫn có thể tiếp tục trong giới hạn metadata hiện có.

## 3. KRaft controller và metadata propagation

Trong KRaft, controller quorum duy trì metadata của cụm bằng metadata log. Một controller giữ vai trò active controller để xử lý các thay đổi metadata; các voter còn lại tham gia đồng thuận và sao chép log. Khi active controller gặp sự cố, quorum bầu controller mới nếu còn đủ điều kiện đạt đa số.

Một số thay đổi do controller quản lý:

- Tạo hoặc xóa topic.
- Thêm partition và thay đổi metadata liên quan.
- Thay đổi replica assignment và trạng thái leader.
- Đăng ký broker, theo dõi broker mất kết nối.
- Cập nhật cấu hình và metadata quản trị theo API được hỗ trợ.

Khi metadata thay đổi, broker cần nhận trạng thái mới để phục vụ client đúng. Ví dụ, khi leader partition chuyển từ broker 1 sang broker 2, metadata cập nhật giúp client làm mới thông tin và gửi request tiếp theo đến broker 2.

Controller quorum không nằm trên đường truyền từng record của ứng dụng. Tuy nhiên, control plane vẫn quan trọng với hoạt động lâu dài: nếu quorum không thể tiến triển, các thay đổi metadata, thao tác quản trị và một số quá trình phục hồi có thể bị ảnh hưởng.

### Controller listener

Controller listener là endpoint dành cho giao tiếp giữa các controller và kết nối broker đến controller trong KRaft. Nó được khai báo bằng controller.listener.names. Với controller node, listener tương ứng phải được bind trong listeners; broker-only node tham chiếu tên controller listener để kết nối đến controller nhưng không cần bind endpoint controller đó như một listener client.

Controller listener nên nằm trên mạng quản trị hoặc mạng nội bộ đáng tin cậy. Không quảng bá endpoint controller cho ứng dụng producer/consumer. Client thông thường kết nối qua listener dành cho client.

Trong mô hình tách vai trò:

- Controller node chạy process.roles=controller và mở controller listener.
- Broker node chạy process.roles=broker, mở listener client và inter-broker; nó kết nối đến controller qua controller listener đã cấu hình.
- Combined node chạy cả vai trò broker và controller, nên cần bind các listener tương ứng với cả hai vai trò.

Cấu hình quorum và cách bootstrap controller phụ thuộc phiên bản Kafka cùng chế độ quorum được sử dụng. Hãy dùng cấu hình mẫu đúng phiên bản cụm thay vì sao chép nguyên một cấu hình quorum từ môi trường khác.

## 4. Listener là endpoint mạng của Kafka

Listener xác định địa chỉ và cổng mà một tiến trình Kafka bind để nhận kết nối. Mỗi listener có một tên và được ánh xạ sang security protocol.

Tên listener thường do người vận hành đặt, ví dụ:

- CLIENT: ứng dụng producer/consumer.
- INTERNAL: giao tiếp nội bộ giữa broker.
- EXTERNAL: client bên ngoài mạng nội bộ hoặc qua load balancer.
- CONTROLLER: giao tiếp KRaft controller.

Các tên trên là quy ước triển khai, không phải danh sách tên bắt buộc do Kafka cố định. Điều quan trọng là mọi node liên quan hiểu cùng tên listener và cấu hình đúng protocol.

### listeners và advertised.listeners khác nhau thế nào?

Hai thuộc tính này giải quyết hai vấn đề riêng:

| Thuộc tính | Chức năng | Ví dụ |
|---|---|---|
| listeners | Địa chỉ IP/hostname và port mà tiến trình bind để nhận kết nối | INTERNAL://0.0.0.0:9092 |
| advertised.listeners | Địa chỉ broker công bố trong metadata để client kết nối sau bootstrap | INTERNAL://kafka-1.kafka.svc:9092 |

0.0.0.0 có thể dùng làm địa chỉ bind để lắng nghe trên các interface IPv4 phù hợp, nhưng không phải địa chỉ mà client có thể dùng để kết nối. Địa chỉ quảng bá cần là hostname hoặc IP có thể phân giải và truy cập từ mạng của client.

Nếu advertised.listeners không được cấu hình, Kafka có thể dùng địa chỉ listener làm địa chỉ quảng bá theo quy tắc mặc định. Điều này có thể hoạt động trong một số môi trường đơn giản, nhưng dễ gây lỗi khi broker nằm trong container, NAT hoặc có nhiều mạng truy cập.

### Vì sao bootstrap thành công nhưng client vẫn lỗi?

Bootstrap broker chỉ là điểm vào ban đầu. Client kết nối tới một hoặc nhiều địa chỉ trong bootstrap.servers, lấy metadata, rồi kết nối trực tiếp đến broker được metadata chỉ định cho partition leader hoặc coordinator.

Vì vậy, việc mở được cổng bootstrap chưa đủ để chứng minh cụm có thể truy cập từ client. Nếu metadata quảng bá kafka-1.internal:9092 nhưng máy client không phân giải được hostname đó, client có thể bootstrap thành công rồi thất bại khi gửi hoặc fetch dữ liệu.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Seed as Bootstrap broker
    participant Leader as Broker leader

    App->>Seed: Kết nối bootstrap.servers
    Seed-->>App: Metadata + advertised endpoint
    App->>Leader: Kết nối broker leader theo metadata
    alt Endpoint truy cập được
      Leader-->>App: Produce / Fetch response
    else Endpoint không truy cập được
      App--xLeader: DNS / timeout / connection refused
    end
~~~

Khi chẩn đoán, hãy kiểm tra cả endpoint bootstrap và endpoint broker được trả về trong metadata từ chính mạng chạy ứng dụng.

## 5. Các loại listener thường dùng

### Client listener

Client listener nhận kết nối từ producer, consumer, AdminClient và các ứng dụng Kafka khác. Đây là endpoint được khai báo trong bootstrap.servers.

Một cụm có thể có nhiều client listener để phục vụ các nhóm mạng hoặc chính sách bảo mật khác nhau. Ví dụ, ứng dụng trong Kubernetes kết nối listener nội bộ; công cụ quản trị từ mạng VPN kết nối listener quản trị; đối tác bên ngoài kết nối endpoint được bảo vệ bằng TLS/SASL qua gateway hoặc load balancer phù hợp.

### Inter-broker listener

Inter-broker listener phục vụ giao tiếp giữa các broker, chẳng hạn replication fetch và các trao đổi nội bộ liên quan. Broker chọn listener này thông qua inter.broker.listener.name.

Các broker cần phân giải và kết nối được endpoint inter-broker mà nhau quảng bá. Nếu inter-broker listener quảng bá hostname chỉ tồn tại trong một mạng khác, replication có thể lỗi dù client bên ngoài vẫn kết nối được.

Không nên nhầm inter-broker listener với controller listener. Inter-broker phục vụ giao tiếp giữa broker; controller listener phục vụ giao tiếp KRaft controller và broker/controller.

### Controller listener

Controller listener phục vụ controller quorum và kết nối broker đến controller trong KRaft. Endpoint này nên được giới hạn trong mạng nội bộ quản trị và chỉ mở cho các node cần giao tiếp.

Ứng dụng thông thường không dùng controller listener làm bootstrap.servers. Nếu client kết nối nhầm endpoint này, request Kafka client thông thường không được phục vụ như trên client listener.

### Internal và external listener

Internal và external là cách phân tách endpoint theo vị trí mạng của client. Chúng thường được triển khai dưới dạng listener có tên riêng, mỗi listener có địa chỉ quảng bá và có thể có security protocol riêng.

Ví dụ:

- Internal listener quảng bá DNS chỉ phân giải được trong mạng container hoặc Kubernetes.
- External listener quảng bá hostname công khai hoặc hostname VPN có thể truy cập từ máy client bên ngoài.
- Hai listener có thể dùng port và chứng thư khác nhau, tùy chính sách bảo mật.

Không nên quảng bá địa chỉ nội bộ cho client bên ngoài hoặc quảng bá địa chỉ công khai cho broker nội bộ nếu đường định tuyến không phù hợp.

## 6. Ánh xạ listener với security protocol

Kafka hỗ trợ các security protocol thường gặp:

| Protocol | Mã hóa kết nối | Xác thực |
|---|---|---|
| PLAINTEXT | Không | Không |
| SSL | TLS | Có thể dùng TLS client authentication |
| SASL_PLAINTEXT | Không | SASL |
| SASL_SSL | TLS | SASL |

Tên listener được ánh xạ sang protocol bằng listener.security.protocol.map. Ví dụ:

~~~properties
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:SASL_SSL,CONTROLLER:SSL
~~~

Trong ví dụ này, kết nối nội bộ dùng PLAINTEXT, endpoint external dùng SASL over TLS và controller listener dùng TLS. Đây chỉ là minh họa cách ánh xạ; lựa chọn thực tế cần dựa trên mô hình đe dọa, PKI, cơ chế xác thực và yêu cầu vận hành.

Với listener dùng SASL hoặc TLS, các cấu hình bổ sung thường có tiền tố theo tên listener, chẳng hạn listener.name.external. Cần bảo đảm chứng thư TLS có SAN khớp hostname mà client thực sự kết nối. Nếu client kết nối qua DNS alias hoặc load balancer, chứng thư và cấu hình trust phải tương thích với endpoint đó.

Trong môi trường production, không nên để listener PLAINTEXT có thể truy cập từ mạng không tin cậy. Cũng không nên xem việc đổi port hoặc đổi tên listener là một biện pháp bảo mật; quyền truy cập cần được bảo vệ bằng mạng, TLS, authentication và authorization phù hợp.

## 7. Ví dụ cấu hình KRaft tách broker và controller

Ví dụ sau minh họa một broker node dùng listener nội bộ cho inter-broker, listener external cho client ngoài mạng và kết nối đến controller listener. Đây là cấu hình khái niệm; các thuộc tính quorum, TLS/SASL và storage phải được hoàn thiện theo phiên bản Kafka và topology thực tế.

### Broker node

~~~properties
process.roles=broker
node.id=101

listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9094
advertised.listeners=INTERNAL://kafka-1.kafka.svc:9092,EXTERNAL://broker-1.example.net:19094

listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:SASL_SSL,CONTROLLER:SSL

inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

Ở broker-only node, CONTROLLER xuất hiện trong protocol map và được tham chiếu bởi controller.listener.names, nhưng không được bind trong listeners của broker này. Broker sẽ kết nối đến endpoint controller do cấu hình quorum cung cấp.

### Controller node

~~~properties
process.roles=controller
node.id=1

listeners=CONTROLLER://0.0.0.0:9093
controller.listener.names=CONTROLLER
listener.security.protocol.map=CONTROLLER:SSL
~~~

Controller node bind controller listener để các controller trong quorum và broker kết nối. Cấu hình địa chỉ quorum, bảo mật TLS và thư mục metadata storage cần được bổ sung phù hợp với phiên bản và quy trình khởi tạo cụm.

### Nếu dùng combined broker/controller cho lab

Trong môi trường thực hành một node, một tiến trình có thể chạy cả hai vai trò. Khi đó nó cần bind listener cho client/broker và controller:

~~~properties
process.roles=broker,controller
node.id=1

listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9094,CONTROLLER://0.0.0.0:9093
advertised.listeners=INTERNAL://localhost:9092,EXTERNAL://localhost:9094

listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

Ví dụ lab dùng PLAINTEXT để dễ quan sát. Không dùng nguyên cấu hình này cho production. Cần bổ sung cấu hình quorum, storage và các thiết lập bảo mật phù hợp; listener external chỉ hợp lệ nếu hostname/port quảng bá thực sự truy cập được từ nơi chạy client.

## 8. Ví dụ nhiều mạng: Docker nội bộ và máy host

Một tình huống thường gặp là Kafka chạy trong Docker Compose. Các container ứng dụng có thể kết nối broker bằng DNS service name và port trong mạng Docker, còn công cụ chạy trên máy host cần kết nối qua port được publish.

Ví dụ về hai endpoint:

| Nơi chạy client | Endpoint cần quảng bá | Vì sao |
|---|---|---|
| Container cùng Docker network | kafka:9092 | Tên service được Docker DNS phân giải nội bộ |
| Máy host | localhost:19094 | Port 19094 được publish ra host |

Cấu hình broker có thể biểu diễn hai listener:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9094
advertised.listeners=INTERNAL://kafka:9092,EXTERNAL://localhost:19094
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
inter.broker.listener.name=INTERNAL
~~~

Docker Compose cần publish port external, ví dụ 19094:9094, và các container client phải cùng network với service kafka. Cấu hình đầy đủ còn cần KRaft role, node ID, quorum và storage. Với nhiều broker, mỗi broker phải quảng bá endpoint riêng có thể truy cập được từ client và từ các broker khác.

Nếu ứng dụng chạy trên máy khác, localhost sẽ trỏ về máy ứng dụng đó chứ không phải máy chạy Kafka. Khi ấy external listener phải quảng bá hostname hoặc IP của máy Kafka có thể định tuyến từ máy client. Không sao chép localhost vào metadata của một cụm mà client nằm trên nhiều máy.

## 9. Cách chọn listener cho từng luồng kết nối

| Luồng kết nối | Listener thường dùng | Lưu ý |
|---|---|---|
| Producer/consumer trong mạng ứng dụng | Client hoặc INTERNAL | Advertise DNS nội bộ có thể truy cập từ ứng dụng |
| Producer/consumer từ mạng ngoài | EXTERNAL | Dùng endpoint định tuyến được và bảo vệ TLS/SASL |
| Broker replication và giao tiếp broker nội bộ | Inter-broker | Các broker phải truy cập endpoint lẫn nhau |
| Broker đến KRaft controller | CONTROLLER | Giới hạn trong mạng quản trị |
| Controller đến controller | CONTROLLER | Phải đáp ứng yêu cầu quorum và bảo mật |

Không phải mọi cụm đều cần bốn listener khác nhau. Một lab nhỏ có thể dùng một client/inter-broker listener và một controller listener. Một cụm production có nhiều vùng mạng có thể cần listener nội bộ và external riêng. Hãy bắt đầu từ các luồng kết nối thực tế rồi mới quyết định số listener.

Một listener có thể phục vụ nhiều loại client nếu chính sách mạng và bảo mật cho phép. Tuy nhiên, tách endpoint giúp áp dụng protocol, firewall rule, DNS và quyền truy cập phù hợp hơn cho từng nhóm.

## 10. Các lỗi cấu hình thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Bootstrap thành công nhưng produce/fetch timeout | Broker quảng bá hostname hoặc port client không truy cập được | Lấy metadata và kiểm tra DNS/port của từng broker từ máy client |
| Container kết nối được nhưng máy host không kết nối được | Chỉ cấu hình endpoint nội bộ hoặc chưa publish external port | Kiểm tra listener external, port mapping và advertised endpoint |
| Máy host kết nối được nhưng container lỗi | Broker quảng bá localhost cho container hoặc thiếu DNS nội bộ | Dùng hostname service trong internal listener |
| Broker không replicate được partition | Inter-broker listener quảng bá địa chỉ sai hoặc firewall chặn | Kiểm tra DNS, port và protocol giữa các broker |
| Broker không kết nối controller | Sai tên controller listener, sai protocol map hoặc endpoint quorum | Kiểm tra controller.listener.names, quorum endpoint và log controller |
| TLS handshake thất bại | CA, truststore, keystore hoặc SAN hostname không khớp | Kiểm tra chứng thư và hostname client dùng để kết nối |
| SASL authentication failed | Cơ chế SASL hoặc credential không khớp listener | Kiểm tra cấu hình SASL theo listener và log xác thực |
| Không tạo được topic hoặc metadata thay đổi không tiến triển | Controller quorum không khỏe hoặc không đạt quorum | Kiểm tra trạng thái controller quorum và log controller |
| Client kết nối nhầm controller endpoint | Dùng sai bootstrap endpoint | Kiểm tra listener client trong bootstrap.servers |

Một quy trình chẩn đoán hiệu quả:

1. Xác định client chạy ở đâu: host, container, Kubernetes, VPN hay mạng bên ngoài.
2. Kiểm tra endpoint trong bootstrap.servers có phân giải DNS và mở TCP được không.
3. Lấy metadata để biết client nhận các broker hostname/port nào.
4. Kiểm tra từng advertised endpoint từ đúng môi trường chạy client.
5. Xác định request đang thất bại ở client listener, inter-broker path hay controller path.
6. Kiểm tra protocol map, TLS/SASL và quyền truy cập tương ứng.
7. Đối chiếu log broker/controller cùng thời điểm lỗi để xác định request hoặc kết nối bị từ chối.

Có thể dùng kcat -b <bootstrap-host>:<port> -L để xem metadata broker mà client nhận được. Công cụ này giúp phát hiện trường hợp bootstrap endpoint truy cập được nhưng metadata trả về hostname nội bộ hoặc địa chỉ không thể định tuyến. Hãy chạy lệnh từ đúng máy hoặc container đang gặp lỗi.

## 11. Nguyên tắc thiết kế cho production

- Xác định rõ từng luồng: client, inter-broker và broker/controller.
- Quảng bá hostname mà đúng nhóm client có thể phân giải và kết nối.
- Không quảng bá địa chỉ wildcard như 0.0.0.0.
- Dùng listener nội bộ riêng cho replication nếu topology yêu cầu.
- Giới hạn controller listener trong mạng quản trị, không mở cho ứng dụng.
- Ánh xạ protocol rõ ràng cho từng listener và dùng TLS/SASL theo chính sách.
- Đảm bảo SAN của chứng thư khớp hostname advertised.
- Đồng bộ DNS, firewall, load balancer và port mapping với metadata Kafka công bố.
- Kiểm tra metadata từ từng loại mạng client sau mỗi thay đổi listener.
- Thử nghiệm broker restart, leader movement và controller failover trong môi trường kiểm thử trước khi áp dụng production.

Khi thay đổi advertised.listeners, client có thể cần metadata refresh hoặc reconnect để nhận endpoint mới. Thay đổi endpoint không chỉ là sửa một dòng cấu hình: DNS, chứng thư, firewall, NAT, load balancer và mọi client đang chạy đều có thể bị ảnh hưởng. Lập kế hoạch chuyển đổi để tránh làm gián đoạn đồng thời toàn bộ kết nối.

## 12. Checklist kiểm tra listener và hai plane

- [ ] Đã xác định broker nào giữ leader của partition và luồng produce/fetch đi qua đâu.
- [ ] Đã phân biệt controller quorum với group coordinator và transaction coordinator.
- [ ] Controller quorum có đủ thành viên khỏe để duy trì đồng thuận.
- [ ] listeners bind đúng interface và port trên từng node.
- [ ] advertised.listeners trả về hostname/IP mà client thực sự truy cập được.
- [ ] bootstrap.servers trỏ đến client listener, không trỏ controller listener.
- [ ] inter.broker.listener.name nhất quán giữa các broker và dùng endpoint nội bộ phù hợp.
- [ ] controller.listener.names khớp với listener của controller quorum.
- [ ] listener.security.protocol.map khai báo đầy đủ protocol cho các listener được dùng.
- [ ] TLS/SASL, chứng thư, DNS và firewall được kiểm tra từ đúng mạng client.
- [ ] Đã kiểm thử metadata discovery, produce, fetch, replication và controller failover.

## Kết luận

Data plane truyền record giữa client, partition leader và replica; control plane duy trì metadata để cụm biết broker, partition, replica và leader đang ở trạng thái nào. Trong KRaft, controller quorum quản lý metadata log và điều phối các thay đổi cấp cụm, còn broker tiếp tục phục vụ dữ liệu và các coordinator như consumer group hoặc transaction coordinator.

Listener xác định endpoint mà từng luồng kết nối sử dụng. listeners là địa chỉ bind; advertised.listeners là địa chỉ broker công bố để client kết nối sau bootstrap. Cấu hình đúng cần bảo đảm DNS, port, routing và security protocol phù hợp từ mọi mạng tham gia. Khi hiểu rõ hai plane và từng listener, người vận hành có thể thiết kế topology mạng dễ kiểm soát và chẩn đoán sự cố Kafka chính xác hơn.

