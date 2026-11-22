# Request handler, network thread và quá trình xử lý yêu cầu

Mỗi khi ứng dụng Java/Spring gửi một yêu cầu tới Apache Kafka, broker phải tiếp nhận dữ liệu qua socket, giải mã giao thức, đưa yêu cầu tới luồng xử lý phù hợp, thực hiện thao tác trên log hoặc metadata rồi gửi phản hồi về client. Kafka chia công việc này thành các lớp mạng và xử lý request riêng để có thể phục vụ nhiều kết nối đồng thời mà không để một thao tác nghiệp vụ chiếm giữ luồng đọc/ghi socket.

Hiểu đường đi của request giúp bạn giải thích độ trễ, nhận diện điểm nghẽn giữa network thread và request handler, cấu hình broker hợp lý và chẩn đoán các lỗi timeout hoặc quá tải. Bài học đặt quá trình này trong kiến trúc cụm Kafka hiện đại sử dụng KRaft, đồng thời liên hệ với producer, consumer và Spring Kafka.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt nhiệm vụ của Acceptor, network processor, request channel và request handler.
- Mô tả vòng đời một request từ socket client tới khi broker trả response.
- Giải thích broker xử lý các loại request Produce, Fetch, Metadata, consumer group và Admin API ở mức tổng quan.
- Hiểu vì sao một số request phải chờ replication, dữ liệu hoặc điều kiện khác trước khi trả response.
- Phân biệt độ trễ do mạng, hàng đợi, xử lý cục bộ và chờ thành phần khác.
- Đọc các metric liên quan tới request queue, network processor và request handler.
- Biết cách cân nhắc num.network.threads, num.io.threads và các giới hạn request khi tối ưu broker.

## 2. Các thành phần tham gia xử lý request

Broker Kafka sử dụng mô hình xử lý bất đồng bộ. Các tên lớp dưới đây là những thành phần tiêu biểu trong triển khai Kafka; chi tiết nội bộ có thể thay đổi theo phiên bản, nhưng ranh giới trách nhiệm vẫn hữu ích để hiểu hệ thống.

| Thành phần | Nhiệm vụ | Công việc tiêu biểu |
|---|---|---|
| Acceptor | Chấp nhận kết nối TCP mới trên listener | Nhận socket và đăng ký kết nối cho network processor |
| Network processor | Đọc request và ghi response qua socket | Dùng cơ chế I/O không chặn, quản lý nhiều kết nối |
| RequestChannel | Chuyển request và response giữa lớp mạng với lớp xử lý | Hàng đợi request/response và thông tin processor sở hữu kết nối |
| Request handler | Xử lý API request ở phía broker | Kiểm tra request, gọi ReplicaManager, coordinator hoặc thành phần quản trị |
| API handler | Thực thi logic của từng Kafka API | Produce, Fetch, Metadata, JoinGroup, Heartbeat, Admin API... |

Trong mã nguồn Kafka, bạn có thể gặp các tên như SocketServer, Acceptor, Processor, RequestChannel, KafkaRequestHandler và KafkaApis. Đây là các tên hữu ích khi đọc log, stack trace hoặc mã nguồn của một phiên bản cụ thể.

### 2.1. Phân biệt network thread và request handler thread

**Network thread** chịu trách nhiệm cho phần giao tiếp mạng: nhận byte từ socket, ghép thành frame request, chuyển request vào hàng đợi xử lý, nhận response và ghi byte về socket. Network processor thường dùng Java NIO selector để theo dõi nhiều socket mà không cần một thread riêng cho mỗi kết nối.

**Request handler thread** lấy request đã được network layer tiếp nhận và thực hiện logic API. Ví dụ, handler kiểm tra request Produce, gọi thành phần quản lý replica để append record vào partition log hoặc xử lý Fetch từ partition. Một số thao tác có thể chờ đĩa, replication, quota hoặc điều kiện dữ liệu.

Hai nhóm thread có mục đích khác nhau. Nếu network thread phải thực hiện toàn bộ logic lưu trữ, một request chậm có thể ảnh hưởng việc đọc dữ liệu từ nhiều kết nối khác. Nếu request handler phải tự đọc và ghi socket, logic nghiệp vụ sẽ bị trộn với quản lý kết nối. Việc tách lớp giúp broker điều phối tải tốt hơn.

### 2.2. Bức tranh luồng xử lý

~~~mermaid
flowchart TB
    C["Kafka client<br/>Producer / Consumer / AdminClient"]
    S["TCP socket<br/>Listener của broker"]
    A["Acceptor"]
    N["Network processor<br/>Đọc và ghi socket"]
    Q["RequestChannel<br/>Request queue"]
    H["KafkaRequestHandler<br/>Request handler pool"]
    API["Kafka API logic<br/>KafkaApis"]
    R["ReplicaManager / GroupCoordinator /<br/>TransactionCoordinator / Metadata"]
    QR["Response queue"]
    W["Network processor<br/>Ghi response"]
    C2["Kafka client nhận response"]

    C --> S --> A --> N --> Q --> H --> API --> R
    R --> API --> QR --> W --> C2
~~~

Sơ đồ mô tả đường đi logic. Trong thực tế, một số xử lý hoàn tất ngay trong handler, một số xử lý hoàn tất qua callback sau khi điều kiện bất đồng bộ được đáp ứng. Response vẫn được gửi về đúng kết nối client thông qua processor quản lý kết nối đó.

## 3. Vòng đời của một request

Một request Kafka có header và phần nội dung theo giao thức Kafka. Header chứa thông tin như API key, API version, correlation ID và client ID. Correlation ID giúp client ghép response với request tương ứng khi có nhiều request đang chờ trên cùng kết nối.

Quá trình xử lý có thể chia thành các bước sau.

### Bước 1: Client mở kết nối tới broker

Producer, consumer hoặc AdminClient bắt đầu kết nối tới một địa chỉ bootstrap server. Sau khi lấy metadata, client có thể kết nối trực tiếp tới broker leader của partition cần truy cập.

Broker tiếp nhận kết nối qua listener phù hợp. Cấu hình listener và advertised listener phải bảo đảm địa chỉ broker mà client nhận được có thể phân giải DNS và truy cập từ mạng của client. Nếu bootstrap thành công nhưng advertised address không truy cập được, lỗi thường xuất hiện ở giai đoạn kết nối tới broker đích.

### Bước 2: Acceptor chấp nhận socket

Acceptor lắng nghe kết nối mới và chấp nhận socket. Nó đăng ký kết nối cho một network processor để processor quản lý các sự kiện đọc/ghi tiếp theo.

Acceptor không thực hiện logic Produce hoặc Fetch. Nhiệm vụ chính của nó là đưa kết nối mới vào hệ thống xử lý mạng.

### Bước 3: Network processor đọc dữ liệu

Network processor dùng selector để theo dõi nhiều socket. Khi socket có dữ liệu, processor đọc byte, xác định kích thước frame và thu thập đủ dữ liệu cho một request. Kích thước request phải nằm trong giới hạn giao thức và cấu hình broker.

Ở lớp kết nối, Kafka cũng thực hiện các bước cần thiết cho TLS hoặc SASL nếu listener được cấu hình bảo mật. Quá trình xác thực thường gắn với handshake hoặc trạng thái kết nối; việc kiểm tra quyền truy cập API được thực hiện theo loại thao tác và principal đã xác thực.

### Bước 4: Request được đưa vào RequestChannel

Sau khi request được giải mã ở mức giao thức, network processor tạo đối tượng request cùng metadata kết nối và đưa vào request queue của RequestChannel.

Thông tin về processor gốc được giữ lại để response sau này có thể quay về đúng kết nối. RequestChannel là ranh giới trao đổi giữa network layer và request handler pool.

Nếu request queue đầy, network layer có thể bị chặn khi cố gắng đưa thêm request vào hàng đợi. Đây là một cơ chế backpressure: broker hạn chế nhận thêm công việc khi lớp xử lý phía sau không theo kịp.

### Bước 5: Request handler lấy request và gọi API logic

Một request handler thread lấy request từ hàng đợi, xác định API tương ứng và chuyển tới phần xử lý thích hợp. Trước hoặc trong khi thực hiện thao tác, broker có thể:

- Kiểm tra phiên bản API và cấu trúc request.
- Kiểm tra principal, ACL và quyền thực hiện thao tác.
- Kiểm tra giới hạn kích thước, trạng thái broker và metadata partition.
- Áp dụng quota cho client hoặc user.
- Gọi ReplicaManager, GroupCoordinator, TransactionCoordinator hoặc thành phần quản trị tương ứng.
- Tạo lỗi giao thức phù hợp nếu request không hợp lệ hoặc broker không thể thực hiện.

Không phải mọi request đều cần truy cập đĩa. Metadata request có thể được phục vụ từ metadata cache. Produce và Fetch thường liên quan tới partition log. Request consumer group được chuyển tới logic coordinator tương ứng.

### Bước 6: Xử lý có thể hoàn tất ngay hoặc bất đồng bộ

Một số API trả kết quả nhanh sau khi kiểm tra trạng thái cục bộ. Một số API cần đợi điều kiện khác.

Ví dụ, với Produce request sử dụng acks=all, broker leader có thể append record vào log rồi chờ các replica trong ISR đáp ứng điều kiện xác nhận trước khi trả ACK. Nếu producer dùng acks=1, response có thể được trả sau khi leader xác nhận append cục bộ theo semantics của Kafka. Với acks=0, producer không chờ response từ broker.

Fetch request có thể phải chờ đủ dữ liệu hoặc chờ tới fetch.max.wait.ms khi consumer đặt fetch.min.bytes. Kafka có cơ chế delayed operation để xử lý các trường hợp cần chờ như vậy. Request handler không nhất thiết phải giữ một thread bận trong toàn bộ thời gian chờ; response có thể được hoàn tất sau thông qua callback hoặc cơ chế đánh thức tương ứng.

### Bước 7: Response được đưa về network layer

Khi kết quả sẵn sàng, broker tạo response chứa correlation ID và dữ liệu hoặc mã lỗi. Response được đưa vào hàng đợi phản hồi gắn với network processor quản lý kết nối ban đầu.

Network processor lấy response, mã hóa thành frame theo Kafka protocol và ghi dữ liệu về socket. Nếu socket chưa sẵn sàng ghi hết, phần còn lại được giữ để gửi khi có sự kiện writable.

### Bước 8: Client nhận và xử lý response

Client ghép response với request theo correlation ID. Tùy loại response, client có thể hoàn tất future, cập nhật metadata, retry, refresh group state hoặc báo lỗi cho ứng dụng.

Nếu client timeout hoặc kết nối bị ngắt trước khi nhận response, kết quả nghiệp vụ có thể chưa rõ. Ví dụ, broker có thể đã append record nhưng ACK không tới được producer. Vì vậy, retry cần được thiết kế cùng idempotent producer, transaction hoặc cơ chế chống xử lý trùng ở tầng nghiệp vụ.

## 4. Ví dụ xử lý các loại request phổ biến

Mỗi Kafka API đi qua cùng kiến trúc tiếp nhận mạng, nhưng phần xử lý nghiệp vụ khác nhau.

### 4.1. Produce request

Giả sử Order Service gửi OrderCreated tới topic orders.

1. Producer chọn partition dựa trên key hoặc partitioner.
2. Client dùng metadata để tìm broker leader của partition.
3. Producer gửi Produce request tới broker leader.
4. Network processor đọc request và chuyển vào RequestChannel.
5. Request handler kiểm tra quyền, topic, partition, cấu hình và điều kiện ghi.
6. ReplicaManager phối hợp append record vào partition log và replication theo cấu hình.
7. Khi điều kiện ACK được đáp ứng, broker tạo response cho producer.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant N as Network processor
    participant H as Request handler
    participant R as ReplicaManager
    participant F as Follower replica

    P->>N: Produce request
    N->>H: RequestChannel
    H->>R: Validate và append
    R->>F: Replicate record
    F-->>R: Replica fetch / bắt kịp log
    R-->>H: Điều kiện ACK được đáp ứng
    H-->>N: Produce response
    N-->>P: ACK hoặc lỗi
~~~

Nếu broker nhận request cho partition mà nó không còn là leader, client có thể nhận lỗi như NOT_LEADER_OR_FOLLOWER và làm mới metadata. Client sẽ retry tới leader mới theo chính sách retry và timeout.

Với acks=all, broker cần chờ điều kiện ISR tương ứng. Nếu ISR thấp hơn min.insync.replicas, broker có thể từ chối ghi để giữ mức an toàn đã cấu hình. Điều đó có thể khiến producer nhận lỗi khi cụm đang suy giảm.

### 4.2. Fetch request

Consumer gửi Fetch request để đọc record từ các partition được gán.

1. Consumer xác định broker phục vụ partition dựa trên metadata.
2. Network processor tiếp nhận request.
3. Request handler gọi logic fetch của broker và đọc dữ liệu phù hợp từ log.
4. Nếu dữ liệu đáp ứng điều kiện fetch, broker trả record và offset.
5. Nếu chưa đủ dữ liệu theo fetch.min.bytes, request có thể chờ đến khi có dữ liệu hoặc hết thời gian chờ được cấu hình.
6. Consumer xử lý record và commit offset theo chiến lược ứng dụng.

Fetch response không đồng nghĩa record đã được xử lý nghiệp vụ. Việc đọc record và việc commit offset là hai hoạt động riêng. Nếu ứng dụng xử lý thành công nhưng lỗi trước khi commit, record có thể được đọc lại.

### 4.3. Metadata request

Client cần biết broker, topic, partition và leader hiện tại. Metadata request thường được phục vụ từ metadata mà broker đang nắm giữ.

Khi metadata thay đổi, client có thể làm mới metadata theo chu kỳ hoặc sau các lỗi chỉ ra leader/partition đã thay đổi. Metadata request không cần controller xử lý từng lần như một thao tác ghi dữ liệu; broker có thể trả lời từ trạng thái metadata đã được cập nhật.

### 4.4. Consumer group request

Các request như JoinGroup, SyncGroup, Heartbeat và OffsetCommit được xử lý bởi broker đang giữ vai trò group coordinator cho consumer group tương ứng.

Group coordinator quản lý membership, generation, heartbeat, rebalance và commit offset. Đây là vai trò của broker, không phải controller leader của KRaft. Nếu coordinator thay đổi, consumer cần tìm coordinator mới và tham gia lại quy trình group theo giao thức.

### 4.5. Admin API và metadata control

AdminClient gửi các request quản trị như tạo topic, mô tả topic, thay đổi cấu hình hoặc reassignment partition. Tùy API và phiên bản Kafka, broker có thể xử lý cục bộ hoặc chuyển tiếp request tới controller đang có thẩm quyền.

Trong KRaft, controller quorum chịu trách nhiệm commit thay đổi metadata. Request handler phía broker là lớp tiếp nhận API từ client; controller là thành phần điều phối và lưu trạng thái metadata. Hai vai trò liên quan nhưng không đồng nhất.

## 5. Request handler và các cơ chế chờ bất đồng bộ

Một request handler không phải lúc nào cũng thực hiện toàn bộ công việc rồi trả response trong cùng một đoạn xử lý đồng bộ.

Kafka có các thao tác phải chờ điều kiện xảy ra sau thời điểm request được tiếp nhận. Ví dụ:

- Produce request chờ replica xác nhận theo mức acks.
- Fetch request chờ đủ dữ liệu hoặc hết thời gian chờ.
- Một số thao tác group hoặc transaction phải chờ trạng thái coordinator thay đổi.
- Request bị quota có thể cần trì hoãn response theo thời gian throttle.

Kafka sử dụng cơ chế delayed operation/purgatory và callback để theo dõi các điều kiện này. Khi điều kiện được đáp ứng hoặc hết thời gian, response được hoàn tất và đưa vào đường gửi về client.

Điểm cần nhớ là thời gian request tồn tại không nhất thiết bằng thời gian một request handler thread bị chiếm dụng. Nếu request chờ replication trong một khoảng thời gian, không nên kết luận toàn bộ thời gian đó đều là CPU time của request handler. Hãy phân tích các thành phần thời gian của request.

## 6. KRaft controller nằm ở đâu trong quá trình này?

Broker request handler phục vụ các API client và gọi các thành phần phù hợp. KRaft controller quorum duy trì metadata của cụm bằng metadata log và Raft.

Với Produce hoặc Fetch bình thường, request đi tới broker đang phục vụ partition; controller không đứng giữa đường đi của từng record. Khi có thay đổi metadata, chẳng hạn tạo topic, thay đổi assignment hoặc bầu partition leader mới, controller tham gia điều phối và commit trạng thái tương ứng.

Có thể phân biệt ba tầng:

| Tầng | Thành phần | Trách nhiệm |
|---|---|---|
| Network layer | Acceptor, network processor | Nhận và gửi dữ liệu qua socket |
| Broker request layer | RequestChannel, request handler, API logic | Xử lý Kafka protocol request và gọi logic broker |
| Cluster control plane | KRaft controller quorum | Quản lý metadata và điều phối thay đổi cụm |

Sự phân tầng này giúp khoanh vùng sự cố. Nếu client không thể mở TCP connection, hãy kiểm tra listener, DNS, firewall và network layer. Nếu kết nối hoạt động nhưng request queue tăng, hãy kiểm tra request handler và tài nguyên broker. Nếu broker trả lỗi leader hoặc metadata, cần kiểm tra trạng thái partition và controller.

## 7. Cấu hình thread và hàng đợi trên broker

Một số cấu hình broker ảnh hưởng trực tiếp đến khả năng tiếp nhận và xử lý request. Tên và giá trị mặc định có thể thay đổi theo phiên bản hoặc cách triển khai; hãy đối chiếu tài liệu đúng phiên bản Kafka.

| Cấu hình | Vai trò | Khi cân nhắc điều chỉnh |
|---|---|---|
| num.network.threads | Số thread phục vụ nhận request từ mạng và gửi response | Khi network processor bận do nhiều kết nối, TLS hoặc lưu lượng mạng |
| num.io.threads | Số thread xử lý request; công việc có thể bao gồm disk I/O | Khi request handler pool thường xuyên bận và tài nguyên CPU/đĩa còn khả năng đáp ứng |
| queued.max.requests | Giới hạn số request được xếp hàng trước khi network thread bị chặn | Khi cần kiểm soát lượng request tồn đọng và backpressure |
| socket.request.max.bytes | Giới hạn kích thước request mà broker chấp nhận | Khi cần kiểm soát request quá lớn và tương thích với payload thực tế |

Ví dụ cấu hình minh họa trong server.properties:

~~~properties
num.network.threads=4
num.io.threads=12
queued.max.requests=500
socket.request.max.bytes=104857600
~~~

Các giá trị trên chỉ minh họa cách khai báo. Không sao chép nguyên xi vào production nếu chưa đo tải, CPU, disk throughput, network và kích thước request thực tế.

### 7.1. Khi nào tăng network threads?

Cân nhắc tăng num.network.threads khi network processor thường xuyên bận, số lượng kết nối và request rate cao, hoặc chi phí TLS/network processing đáng kể. Kiểm tra metric network processor idle và CPU trước khi tăng.

Tăng quá nhiều thread có thể làm tăng context switching và tranh chấp CPU. Nếu điểm nghẽn thực tế nằm ở request handler hoặc đĩa, tăng network threads không giải quyết được vấn đề.

### 7.2. Khi nào tăng request handler threads?

Cân nhắc tăng num.io.threads khi request handler pool thường xuyên bận và còn dư CPU, disk I/O cùng các tài nguyên liên quan. Request handler có thể thực hiện công việc CPU, gọi thành phần broker và chờ một số thao tác I/O; vì vậy cần xem loại request đang chiếm thời gian.

Nếu đĩa đã bão hòa, tăng số handler có thể làm nhiều request cùng tranh chấp I/O và khiến latency tệ hơn. Trước khi tăng thread, cần kiểm tra storage latency, page cache, CPU, partition distribution và request mix.

### 7.3. Vì sao không nên chỉ tăng request queue?

Queue lớn có thể hấp thụ một đợt tải ngắn, nhưng không tăng tốc độ xử lý bền vững của broker. Nếu tốc độ request đến lớn hơn tốc độ handler xử lý trong thời gian dài, queue sẽ tiếp tục tăng và latency cũng tăng theo.

Giới hạn queue là một phần của backpressure. Hãy tìm nguyên nhân handler không theo kịp: CPU, đĩa, network, quota, replication, số partition, kích thước batch hoặc downstream. Tăng queue mà không xử lý nguyên nhân chỉ làm request chờ lâu hơn trước khi timeout.

## 8. Đọc metric để tìm điểm nghẽn

Khi một ứng dụng báo Kafka chậm, hãy tách thời gian request thành các phần thay vì chỉ nhìn tổng latency.

Các metric request thường được chia thành:

| Metric | Ý nghĩa khái quát | Dấu hiệu cần điều tra |
|---|---|---|
| RequestQueueTimeMs | Thời gian request nằm trong request queue trước khi được xử lý | Queue tăng có thể cho thấy handler không theo kịp |
| LocalTimeMs | Thời gian xử lý cục bộ phía broker | Tăng có thể liên quan CPU, disk hoặc logic broker |
| RemoteTimeMs | Thời gian chờ xử lý hoặc điều kiện ở thành phần từ xa | Tăng có thể liên quan replication hoặc phối hợp giữa node |
| ResponseQueueTimeMs | Thời gian response chờ network layer gửi đi | Tăng có thể cho thấy network processor hoặc socket bị nghẽn |
| ResponseSendTimeMs | Thời gian gửi response qua mạng | Tăng có thể liên quan băng thông, socket hoặc client đọc chậm |
| TotalTimeMs | Tổng thời gian request ở phía broker theo phép đo tương ứng | Dùng cùng các thành phần để tìm phần đóng góp lớn |

Tên metric, phạm vi đo và cách xuất metric có thể khác nhau theo phiên bản, request type và hệ thống giám sát. Hãy đối chiếu JMX hoặc metric exporter đang dùng với tài liệu phiên bản Kafka.

Các metric tổng quan đáng theo dõi:

- RequestQueueSize: số request đang chờ xử lý.
- RequestHandlerAvgIdlePercent: mức nhàn rỗi trung bình của request handler pool.
- NetworkProcessorAvgIdlePercent: mức nhàn rỗi trung bình của network processor.
- Request rate, request size, error rate và latency theo API key.
- Số connection, network bytes in/out và request throttling.
- Disk latency, CPU utilization, page cache và replication lag.

Một số cách diễn giải:

- Request queue time cao, request handler idle thấp: handler pool có thể đang quá tải.
- Network processor idle thấp, response send time cao: kiểm tra network, socket, TLS và tốc độ đọc của client.
- Local processing time cao: kiểm tra CPU, storage, số partition, request size và loại API.
- Remote wait tăng với Produce acks=all: kiểm tra ISR, follower lag và network replication.
- Broker request latency bình thường nhưng producer timeout: kiểm tra client network, DNS, advertised listener, timeout và việc client có đang kết nối đúng leader hay không.

Không nên kết luận từ một metric đơn lẻ. Hãy đối chiếu theo broker, listener, request type, partition và thời điểm phát sinh lỗi.

## 9. Các nguyên nhân làm request chậm hoặc thất bại

### 9.1. Request handler pool bị quá tải

Nhiều request đến đồng thời hoặc một số loại request cần nhiều CPU/đĩa có thể làm handler pool bận. Request queue tăng, RequestQueueTimeMs tăng và client bắt đầu timeout.

Hướng điều tra:

- Xem request rate và loại request đang tăng.
- Đối chiếu RequestHandlerAvgIdlePercent, request queue và CPU.
- Kiểm tra disk latency và số partition đang phục vụ.
- Xác định có một broker hoặc một partition leader bị nóng hay không.
- Kiểm tra client có gửi batch quá nhỏ hoặc quá nhiều request riêng lẻ không.

### 9.2. Network processor hoặc mạng bị nghẽn

Network thread có thể bận khi số kết nối, request rate, TLS overhead hoặc response lớn tăng cao. Đường mạng giữa client và broker cũng có thể có packet loss, retransmission, băng thông thấp hoặc latency cao.

Hướng điều tra:

- Kiểm tra NetworkProcessorAvgIdlePercent.
- Đo latency và throughput giữa client với từng broker.
- Kiểm tra listener, DNS, firewall, TLS và advertised listener.
- Theo dõi số connection và kích thước response.
- Kiểm tra client có đọc response chậm hoặc giữ quá nhiều kết nối không cần thiết.

### 9.3. Disk I/O hoặc page cache bị áp lực

Produce và Fetch đều có thể bị ảnh hưởng bởi storage. Broker ghi log, đọc segment và duy trì index; nếu disk latency cao hoặc page cache thiếu, request local processing có thể tăng.

Hướng điều tra:

- Theo dõi disk utilization, IOPS, throughput và latency.
- Kiểm tra dung lượng còn trống và log segment growth.
- Kiểm tra partition có phân bố lệch trên broker hay không.
- Đánh giá retention, compaction và workload đọc/ghi đồng thời.

### 9.4. Replication làm tăng thời gian ACK

Với acks=all, producer phải đợi điều kiện xác nhận từ ISR. Nếu follower chậm, network replication yếu hoặc broker follower bị quá tải, response Produce có thể chậm dù leader đã nhận record.

Hướng điều tra:

- Kiểm tra ISR và under-replicated partitions.
- Đối chiếu leader/follower network và disk.
- Kiểm tra rack hoặc vùng lỗi có latency cao.
- Xác nhận min.insync.replicas và replication factor có phù hợp mục tiêu hay không.

### 9.5. Quota hoặc request không hợp lệ

Broker có thể áp dụng quota theo user/client để bảo vệ cụm. Request bị throttle có thể chờ trước khi client được phép tiếp tục. Request sai API version, topic không tồn tại, thiếu quyền, partition không có leader hoặc payload vượt giới hạn cũng có thể trả lỗi.

Hướng điều tra:

- Đọc mã lỗi và response throttle time.
- Kiểm tra ACL, principal và quota.
- Kiểm tra topic/partition metadata và API version tương thích.
- Đối chiếu kích thước record/batch với giới hạn broker và client.

### 9.6. Client timeout nhưng broker đã xử lý request

Timeout chỉ cho biết client không nhận được response trong thời gian cho phép. Nó không chứng minh request chưa được thực hiện.

Ví dụ, broker có thể append record thành công rồi response bị mất do kết nối đứt. Producer retry có thể gửi lại cùng nghiệp vụ. Hãy sử dụng idempotent producer và thiết kế consumer idempotent để xử lý tình huống không rõ kết quả.

## 10. Tương tác với producer và consumer trong Java/Spring Kafka

Ứng dụng Spring Kafka không trực tiếp quản lý request handler thread của broker. Ứng dụng cấu hình client, gửi record hoặc fetch record; broker quyết định cách tiếp nhận và xử lý request.

Một số cấu hình client có ảnh hưởng tới tải broker:

- Producer batch.size và linger.ms giúp gom record thành batch, giảm số request nhỏ khi workload phù hợp.
- Producer compression.type giảm byte truyền qua mạng và dung lượng log, đổi lại có chi phí CPU nén/giải nén.
- Producer max.request.size giới hạn kích thước request phía client; broker cũng có giới hạn riêng.
- Producer request.timeout.ms xác định thời gian client chờ response cho request.
- Consumer fetch.min.bytes, fetch.max.wait.ms và max.partition.fetch.bytes ảnh hưởng cách consumer yêu cầu dữ liệu.
- Consumer max.poll.records giới hạn số record trả về mỗi lần poll ở tầng consumer API; nó không phải giới hạn kích thước một Kafka Fetch request.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
    producer:
      acks: all
      batch-size: 32768
      properties:
        linger.ms: 5
        compression.type: lz4
        enable.idempotence: true
        request.timeout.ms: 30000
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        fetch.min.bytes: 1
        fetch.max.wait.ms: 500
~~~

Các giá trị chỉ minh họa. Chúng cần được kiểm chứng với phiên bản Kafka client/Spring Kafka, kích thước record, latency mục tiêu và tải thực tế. Tăng linger.ms có thể cải thiện batching nhưng làm tăng thời gian chờ trước khi gửi. Tăng fetch.min.bytes có thể cải thiện hiệu quả batch khi lưu lượng lớn nhưng có thể tăng độ trễ khi lưu lượng thấp.

Không nên cố khắc phục broker quá tải chỉ bằng cách tăng timeout ở client. Timeout dài hơn có thể giảm lỗi quan sát được trong ngắn hạn nhưng không làm tăng năng lực xử lý và có thể khiến request tồn đọng lâu hơn.

## 11. Ví dụ chẩn đoán theo số liệu

Giả sử producer ghi sự kiện vào topic orders và đột nhiên latency tăng từ 20 ms lên 800 ms. Bạn thu thập được các tín hiệu sau:

| Tín hiệu | Trạng thái |
|---|---|
| RequestQueueTimeMs | Tăng mạnh trên broker 2 |
| RequestHandlerAvgIdlePercent | Gần 0 trên broker 2 |
| NetworkProcessorAvgIdlePercent | Vẫn cao |
| Disk latency | Cao trên broker 2 |
| ISR | Một số partition có follower lag |
| Producer request timeout | Tăng |

Nhận định hợp lý là network processor chưa phải điểm nghẽn chính. Request handler đang bận và disk latency cao trên broker 2; follower lag còn có thể kéo dài thời gian ACK cho những partition có leader hoặc replica liên quan.

Quy trình xử lý:

1. Xác định partition leader và replica đang nằm trên broker 2.
2. Kiểm tra disk utilization, I/O latency, dung lượng và workload compaction/retention.
3. Kiểm tra request rate, batch size và phân bố partition để tìm broker hoặc partition nóng.
4. Kiểm tra replication lag và network giữa leader/follower.
5. Sau khi xử lý nguyên nhân, theo dõi lại queue time, handler idle, disk latency và producer latency.
6. Chỉ cân nhắc tăng num.io.threads khi có bằng chứng handler concurrency là giới hạn và CPU/disk còn đủ khả năng.

Nếu thay vào đó NetworkProcessorAvgIdlePercent thấp, response send time cao và request queue time thấp, hướng điều tra nên tập trung vào network processor, socket, TLS hoặc tốc độ đọc response của client.

## 12. Nguyên tắc tối ưu request path

1. **Đo trước khi thay đổi thread.** Xác định thời gian nằm ở network, request queue, xử lý cục bộ hay chờ replication.
2. **Giữ request vừa phải.** Gom record theo batch hợp lý, tránh gửi quá nhiều request nhỏ hoặc payload khổng lồ.
3. **Phân bố partition và leader cân bằng.** Một broker quá nóng có thể làm request latency tăng dù tổng tài nguyên cụm còn dư.
4. **Bảo đảm storage và network đủ năng lực.** Request handler không thể bù cho ổ đĩa hoặc đường truyền đã bão hòa.
5. **Dùng quota có chủ đích.** Quota giúp một client không chiếm hết tài nguyên, nhưng cần theo dõi throttling và đặt ngưỡng phù hợp.
6. **Giữ request queue trong giới hạn.** Queue là vùng đệm và cơ chế backpressure, không phải năng lực xử lý bổ sung.
7. **Cấu hình client tương thích.** Batch, compression, timeout và fetch settings cần phù hợp với broker và SLA ứng dụng.
8. **Kiểm thử tình huống lỗi.** Mô phỏng broker chậm, follower lag, client đọc chậm, network gián đoạn và request timeout để kiểm tra hành vi retry.

## 13. Thực hành quan sát một broker

Khi có quyền truy cập môi trường Kafka, hãy chọn một broker và thực hiện các bước sau:

1. Xác định listener mà ứng dụng đang kết nối và kiểm tra advertised address có truy cập được từ môi trường client.
2. Gửi một lượng Produce/Fetch nhỏ có kiểm soát và quan sát request rate.
3. Theo dõi request queue size, RequestQueueTimeMs, RequestHandlerAvgIdlePercent và NetworkProcessorAvgIdlePercent.
4. So sánh LocalTimeMs, RemoteTimeMs và response timing theo từng request type.
5. Tăng tải dần trong môi trường thử nghiệm và ghi lại thời điểm queue bắt đầu tăng.
6. Dừng một follower thử nghiệm để quan sát ISR, replication và Produce latency với acks=all.
7. Khôi phục follower và xác nhận ISR cùng latency trở lại trạng thái bình thường.

Không thực hiện thử nghiệm gây lỗi broker trên cụm production nếu chưa có kế hoạch vận hành và phạm vi kiểm soát phù hợp. Mục đích của bài thực hành là liên kết metric với từng đoạn của request path.

## 14. Những nhầm lẫn thường gặp

- **Cho rằng network thread xử lý toàn bộ nghiệp vụ:** network processor quản lý socket và chuyển request/response; request handler thực hiện API logic.
- **Cho rằng mỗi client connection có một request handler thread riêng:** Kafka dùng network processor quản lý nhiều kết nối và request handler pool xử lý request theo hàng đợi.
- **Cho rằng tăng network threads luôn làm broker nhanh hơn:** nếu bottleneck là handler, disk hoặc replication, tăng network thread không giải quyết được.
- **Cho rằng request queue lớn hơn đồng nghĩa throughput cao hơn:** queue lớn chỉ cho phép giữ nhiều request chờ hơn; nó có thể làm latency và timeout tăng.
- **Cho rằng handler thread phải chờ đồng bộ cho mọi response:** một số request được hoàn tất bất đồng bộ sau khi replication, dữ liệu hoặc điều kiện khác sẵn sàng.
- **Cho rằng timeout nghĩa là record chưa được ghi:** broker có thể đã xử lý request nhưng response không tới client.
- **Cho rằng controller xử lý từng Produce request:** broker phục vụ Produce/Fetch bình thường; KRaft controller quản lý metadata và thay đổi trạng thái cụm.

## 15. Tự kiểm tra

**Câu 1.** Network processor và request handler khác nhau ở điểm nào?

**Đáp án:** Network processor đọc/ghi socket và chuyển request/response. Request handler xử lý logic Kafka API như Produce, Fetch, group hoặc Admin request.

**Câu 2.** RequestChannel dùng để làm gì?

**Đáp án:** Là kênh trao đổi request và response giữa network layer và request handler pool, đồng thời giữ thông tin để response quay về đúng processor/kết nối.

**Câu 3.** Vì sao request queue tăng có thể làm client timeout?

**Đáp án:** Request phải chờ lâu trước khi được handler xử lý. Nếu thời gian chờ cộng thời gian xử lý vượt timeout của client, client có thể timeout dù broker vẫn đang chạy.

**Câu 4.** Khi producer dùng acks=all, điều gì có thể kéo dài thời gian response?

**Đáp án:** Broker leader phải chờ các replica trong ISR đáp ứng điều kiện xác nhận. Follower lag hoặc network replication chậm có thể làm response trễ.

**Câu 5.** Nếu NetworkProcessorAvgIdlePercent cao nhưng RequestHandlerAvgIdlePercent gần 0, nên kiểm tra gì trước?

**Đáp án:** Request handler pool và các tài nguyên mà handler sử dụng, như CPU, disk I/O, request mix, partition distribution và replication. Network processor có vẻ chưa phải điểm nghẽn chính.

**Câu 6.** Có nên tăng queued.max.requests để chữa request handler quá tải không?

**Đáp án:** Không nên xem đó là cách chữa gốc. Queue lớn hơn có thể hấp thụ đợt tải ngắn nhưng không tăng tốc độ xử lý; cần tìm nguyên nhân handler không theo kịp.

**Câu 7.** Client timeout có chứng minh request chưa được broker thực hiện không?

**Đáp án:** Không. Broker có thể đã xử lý request nhưng response bị mất hoặc đến muộn. Ứng dụng cần retry an toàn và idempotency.

---

Khi điều tra độ trễ Kafka, hãy lần theo request từ socket, network processor, request queue, request handler tới thao tác broker và response. Việc xác định đúng đoạn đang chờ giúp bạn chọn đúng metric, điều chỉnh đúng cấu hình và tránh tăng thread hoặc timeout một cách thiếu căn cứ.

