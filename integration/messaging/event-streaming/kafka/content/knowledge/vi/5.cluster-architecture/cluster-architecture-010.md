# Phân biệt lỗi client, lỗi broker và lỗi điều phối cụm

Khi một ứng dụng không gửi được record hoặc consumer không đọc được dữ liệu từ Apache Kafka, thông báo lỗi thường xuất hiện ở phía client. Tuy nhiên, nơi phát hiện lỗi không nhất thiết là nơi gây ra lỗi. Một producer có thể nhận timeout vì broker đang quá tải, vì partition chưa có leader hoặc vì controller quorum trong KRaft chưa thể hoàn tất một thay đổi metadata. Ngược lại, chỉ một ứng dụng có thể thất bại do serializer, cấu hình bảo mật hoặc logic xử lý của chính nó trong khi cụm Kafka vẫn hoạt động bình thường.

Để xử lý đúng, cần phân biệt ba lớp chính:

- **Lỗi client:** phát sinh trong ứng dụng, Kafka client library hoặc cấu hình kết nối của ứng dụng.
- **Lỗi broker:** phát sinh tại broker đang phục vụ request hoặc quản lý dữ liệu partition, replica và tài nguyên cục bộ.
- **Lỗi điều phối cụm:** phát sinh trong control plane, đặc biệt là controller và KRaft metadata quorum, nơi quản lý metadata, đăng ký broker, bầu controller và thay đổi trạng thái partition.

Ba lớp có thể liên quan với nhau. Một sự cố broker có thể dẫn đến thay đổi leader do controller điều phối; trong thời gian metadata cập nhật, client có thể nhận lỗi tạm thời. Vì vậy, không nên chỉ nhìn tên exception ở ứng dụng rồi kết luận ngay nguyên nhân.

## 1. Nhìn Kafka như hai mặt phẳng hoạt động

Để phân loại lỗi, trước tiên cần hiểu luồng request và vai trò của các thành phần trong cụm.

Kafka có thể được nhìn theo hai mặt phẳng:

- **Data plane:** producer gửi record đến partition leader; consumer fetch record từ broker; replica follower sao chép dữ liệu từ leader.
- **Control plane:** controller quản lý metadata cụm, broker registration, topic, partition assignment, leader election và các thay đổi cấu trúc.

Trong kiến trúc KRaft, controller duy trì metadata log bằng cơ chế Raft. Các controller tạo thành một quorum. Broker nhận metadata và thực hiện vai trò data plane; trong cấu hình combined, một node có thể đồng thời mang vai trò broker và controller.

~~~mermaid
flowchart TB
    subgraph Client["Ứng dụng và Kafka client"]
        P["Producer"]
        C["Consumer"]
        A["AdminClient"]
    end

    subgraph DataPlane["Data plane - Brokers"]
        B1["Broker 1<br/>Partition leader"]
        B2["Broker 2<br/>Replica follower"]
        B3["Broker 3<br/>Partition leader / follower"]
    end

    subgraph ControlPlane["Control plane - KRaft"]
        K1["Controller 1"]
        K2["Controller 2"]
        K3["Controller 3"]
        Q["Metadata quorum<br/>Raft log"]
        K1 --- Q
        K2 --- Q
        K3 --- Q
    end

    P --> B1
    C --> B1
    B1 --> B2
    A --> K1
    Q --> B1
    Q --> B2
    Q --> B3
~~~

Producer và consumer thường trao đổi trực tiếp với broker phục vụ partition. Chúng không cần gọi controller cho từng record. Tuy nhiên, khi topic được tạo, partition đổi leader, broker gia nhập hoặc metadata thay đổi, control plane phải phối hợp và phân phối trạng thái mới cho các broker.

Điều này giải thích vì sao mất quorum controller không nhất thiết làm dừng ngay mọi request produce/fetch đang hoạt động. Những partition vẫn có leader hợp lệ có thể tiếp tục phục vụ một số request data plane. Nhưng các thay đổi metadata và những leader election cần controller có thể bị đình trệ; partition không có leader mới có thể tiếp tục unavailable cho đến khi điều phối phục hồi.

## 2. Lỗi client: vấn đề nằm ở ứng dụng hoặc phía kết nối

Lỗi client thường ảnh hưởng đến một ứng dụng, một instance, một consumer group hoặc một luồng xử lý cụ thể. Các ứng dụng khác vẫn có thể sử dụng cùng cụm Kafka bình thường.

### 2.1. Lỗi serialize và deserialize

Producer phải chuyển key và value thành byte trước khi gửi. Consumer phải chuyển byte nhận được thành kiểu dữ liệu ứng dụng. Nếu serializer/deserializer không tương thích với dữ liệu, lỗi xuất hiện ở phía client.

Ví dụ thường gặp:

- Producer dùng JSON serializer nhưng cấu hình topic hoặc consumer mong đợi Avro.
- Một field bắt buộc bị thiếu hoặc có kiểu dữ liệu không hợp lệ.
- Schema thay đổi nhưng consumer chưa tương thích.
- Consumer cố parse một payload rỗng hoặc null như JSON object.
- Key serializer giữa các producer không thống nhất, làm thay đổi cả dữ liệu key và cách chọn partition.

Các lỗi có thể xuất hiện dưới dạng SerializationException, DeserializationException hoặc RecordDeserializationException tùy client và framework.

Cách xử lý:

1. Ghi lại topic, partition, offset và thông tin schema của record lỗi nếu có.
2. Kiểm tra serializer/deserializer và schema compatibility giữa producer, consumer.
3. Phân biệt record không hợp lệ với lỗi hạ tầng.
4. Với record không thể deserialize, đưa record vào dead-letter topic sau số lần xử lý phù hợp thay vì retry vô hạn.
5. Giữ nguyên raw bytes hoặc metadata cần thiết để có thể điều tra và phát lại.

Lỗi deserialize thường gắn với một record hoặc một schema cụ thể. Nếu tất cả consumer cùng lỗi trên mọi partition sau một lần triển khai, cần kiểm tra thay đổi phiên bản schema hoặc cấu hình chung của ứng dụng.

### 2.2. Cấu hình client và kết nối

Client có thể không kết nối được do:

- Sai bootstrap server hoặc sai port.
- DNS không phân giải được hostname broker.
- Địa chỉ advertised.listeners mà broker công bố không thể truy cập từ mạng của client.
- Firewall, network policy hoặc routing chặn kết nối.
- TLS truststore/keystore sai, chứng chỉ hết hạn hoặc hostname không khớp.
- SASL mechanism, username, password hoặc cấu hình JAAS không đúng.
- Client dùng phiên bản protocol hoặc cấu hình không tương thích với môi trường.

Một điểm dễ nhầm là client có thể kết nối thành công đến bootstrap broker nhưng thất bại khi kết nối đến broker leader thực tế. Bootstrap server chỉ giúp client lấy metadata ban đầu. Sau đó client kết nối đến địa chỉ broker được quảng bá trong metadata.

Vì vậy, khi chỉ một môi trường mạng gặp lỗi, hãy kiểm tra advertised.listeners và khả năng truy cập đến tất cả broker, không chỉ bootstrap address.

### 2.3. Authentication và authorization

Authentication xác minh danh tính client; authorization kiểm tra client có quyền thực hiện hành động hay không.

Ví dụ:

- SASL authentication thất bại do credential hoặc mechanism sai.
- TLS handshake thất bại do chứng chỉ hoặc trust chain.
- Client không có ACL để ghi vào topic.
- Consumer không có quyền đọc topic hoặc truy cập consumer group.
- AdminClient không có quyền tạo topic hoặc thay đổi cấu hình.

Các lỗi bảo mật thường có tính lặp lại cho đến khi credential, chứng chỉ hoặc ACL được sửa. Retry liên tục không giải quyết được lỗi cấu hình hoặc thiếu quyền.

Cần phân biệt nguồn lỗi: credential sai thường do client secret/configuration; ACL bị từ chối là quyết định authorization của broker dựa trên principal và policy hiện tại. Cả hai đều có thể xuất hiện thành exception trong ứng dụng.

### 2.4. Timeout và backpressure phía ứng dụng

Timeout là triệu chứng, không phải kết luận về nguyên nhân.

Một producer có thể timeout vì:

- Ứng dụng tạo record nhanh hơn khả năng gửi và buffer đầy.
- Broker phản hồi chậm hoặc không thể truy cập.
- Network bị mất gói hoặc độ trễ cao.
- Partition đang chuyển leader.
- Request timeout hoặc delivery timeout cấu hình quá thấp.
- Consumer xử lý chậm khiến lag tăng, nhưng producer vẫn gửi bình thường.

Cần phân biệt timeout của API gửi, request timeout đến broker và delivery timeout của producer. Khi timeout, ứng dụng có thể không biết chắc broker đã ghi record hay chưa. Nếu gửi lại mà không có cơ chế chống trùng, nghiệp vụ có thể bị xử lý hai lần.

Idempotent producer giúp hạn chế duplicate do retry của producer trong phạm vi session và protocol được Kafka hỗ trợ. Với side effect bên ngoài Kafka như ghi database, gọi REST hoặc gửi thanh toán, ứng dụng vẫn cần idempotency key, event ID hoặc transaction/outbox phù hợp.

### 2.5. Lỗi lập trình và xử lý consumer

Các lỗi chỉ xuất hiện trong một consumer có thể đến từ:

- NullPointerException hoặc lỗi logic nghiệp vụ.
- Database downstream không truy cập được.
- Consumer commit offset sai thời điểm.
- Xử lý bất đồng bộ làm mất kiểm soát thứ tự.
- Handler bị block quá lâu khiến poll interval vượt giới hạn.
- Retry vô hạn một record độc hại hoặc dữ liệu không hợp lệ.

Trong Spring Kafka, exception từ listener có thể được xử lý bởi error handler. Với lỗi dữ liệu không thể phục hồi, có thể dùng DefaultErrorHandler cùng DeadLetterPublishingRecoverer và backoff hữu hạn để chuyển record sang dead-letter topic. Với lỗi tạm thời của hệ thống downstream, retry có giới hạn và backoff tăng dần thường phù hợp hơn.

Không nên cấu hình mọi exception đều retry vô hạn. Điều đó có thể khiến một partition bị kẹt ở một record lỗi và làm consumer lag tăng liên tục.

## 3. Lỗi broker: vấn đề ở data plane hoặc tài nguyên broker

Broker lưu partition log, phục vụ produce/fetch, duy trì replica và quản lý tài nguyên cục bộ. Một broker lỗi có thể chỉ ảnh hưởng đến các partition có replica hoặc leader trên broker đó, nhưng cũng có thể lan rộng nếu broker giữ nhiều partition quan trọng hoặc cụm thiếu tài nguyên dự phòng.

### 3.1. Broker mất kết nối hoặc dừng hoạt động

Nguyên nhân có thể là:

- Tiến trình Kafka bị crash hoặc bị restart.
- Máy chủ mất điện hoặc hệ điều hành lỗi.
- Broker bị OOM hoặc CPU quá tải.
- Network giữa broker và các node khác bị gián đoạn.
- Disk đầy, disk lỗi hoặc log directory không thể ghi.
- JVM pause dài do garbage collection.

Hệ quả phụ thuộc replica assignment và trạng thái ISR:

- Nếu partition có replica còn hoạt động và đủ điều kiện, controller có thể điều phối bầu leader mới.
- Trong lúc leader election và metadata cập nhật, producer/consumer có thể gặp lỗi tạm thời.
- Nếu partition chỉ có một replica trên broker lỗi, partition đó có thể unavailable.
- Nếu replica không còn đủ điều kiện hoặc ISR bị thu hẹp, producer có thể không ghi được khi yêu cầu acks và min.insync.replicas không được đáp ứng.

Không nên kết luận toàn bộ cluster đã down chỉ vì một broker không phản hồi. Hãy xác định partition nào có leader hoặc replica trên broker đó, và partition nào thực sự ở trạng thái offline.

### 3.2. Leader và replica không đồng bộ

Mỗi partition có một leader và có thể có nhiều follower replica. Producer ghi vào leader; follower fetch dữ liệu từ leader để bắt kịp log.

Các trạng thái quan trọng:

- **ISR (In-Sync Replicas):** tập replica đang theo kịp leader theo tiêu chí Kafka.
- **Under-replicated partition:** partition có replica không theo kịp hoặc chưa đủ trạng thái đồng bộ mong muốn.
- **Offline partition:** partition hiện không có leader khả dụng.

Một số mã lỗi thường gặp:

| Mã lỗi hoặc exception | Ý nghĩa khái quát | Hướng kiểm tra |
|---|---|---|
| NOT_LEADER_OR_FOLLOWER | Broker nhận request không còn là leader/follower phù hợp cho request đó | Metadata client, leader hiện tại và quá trình chuyển leader |
| LEADER_NOT_AVAILABLE | Partition chưa có leader khả dụng | Replica, ISR, broker và controller |
| NOT_ENOUGH_REPLICAS | Số replica hiện có không đáp ứng điều kiện ghi | ISR và min.insync.replicas |
| NOT_ENOUGH_REPLICAS_AFTER_APPEND | Sau khi append, số replica đáp ứng yêu cầu vẫn không đủ | Trạng thái replication và kết quả ghi có thể chưa rõ với ứng dụng |
| REQUEST_TIMED_OUT | Request không hoàn thành trong thời hạn | Broker load, network, disk và timeout config |
| UNKNOWN_TOPIC_OR_PARTITION | Broker không nhận diện topic/partition trong metadata hiện tại | Tên topic, quyền, metadata propagation và topic creation |
| BROKER_NOT_AVAILABLE | Broker đích không khả dụng cho request | Broker process, network và advertised.listeners |

Tên exception ở client có thể bọc mã lỗi protocol. Hãy xem root cause và error code thực tế nếu framework cung cấp.

### 3.3. Disk, network và tài nguyên broker

Một broker vẫn có thể sống nhưng không phục vụ tốt nếu tài nguyên cạn kiệt.

| Dấu hiệu | Nguyên nhân có thể | Hướng chẩn đoán |
|---|---|---|
| Produce latency tăng | Disk flush chậm, CPU cao, network nghẽn, request queue dài | Broker metrics, disk latency, network và request handler |
| Fetch latency tăng | Broker quá tải, replica lag, network chậm | Fetch request latency, bytes in/out, replica fetcher |
| Under-replicated partitions tăng | Follower không theo kịp leader | Replication traffic, disk, network, broker load |
| Offline log directory | Disk lỗi hoặc mount không còn khả dụng | Log directory health, filesystem và broker logs |
| Request timeout diện rộng | Broker quá tải hoặc network partition | Request queue, processor idle, network và broker logs |
| Một broker liên tục restart | OOM, cấu hình JVM, disk hoặc lỗi hệ điều hành | Process logs, GC logs, kernel/system logs |

Không nên chỉ tăng timeout để che giấu broker quá tải. Timeout lớn hơn có thể làm request tồn đọng lâu hơn và che khuất thời điểm sự cố bắt đầu. Hãy xác định tài nguyên nào đang là nút thắt.

### 3.4. acks và min.insync.replicas khi broker gặp sự cố

Producer config acks xác định mức xác nhận ghi:

- acks=0: producer không chờ broker xác nhận.
- acks=1: chờ leader xác nhận append.
- acks=all: chờ các replica trong ISR đáp ứng điều kiện xác nhận theo cấu hình broker.

min.insync.replicas đặt ngưỡng ISR tối thiểu để một lần ghi với acks=all được chấp nhận. Nếu ISR giảm dưới ngưỡng này, broker từ chối ghi với lỗi liên quan đến NOT_ENOUGH_REPLICAS.

Ví dụ, replication factor là 3 và min.insync.replicas là 2. Nếu một broker mất kết nối và ISR còn 2 replica, producer có thể tiếp tục ghi với acks=all. Nếu ISR chỉ còn 1, broker từ chối ghi để bảo vệ mức độ bền vững đã cấu hình.

Cấu hình này là một đánh đổi giữa availability và durability. Không nên tùy tiện hạ min.insync.replicas hoặc chuyển acks xuống 1 chỉ để làm mất lỗi, vì có thể làm tăng nguy cơ mất dữ liệu khi leader gặp sự cố tiếp theo.

## 4. Lỗi điều phối cụm: controller và KRaft metadata quorum

Lỗi điều phối khác lỗi xử lý record tại broker. Nó ảnh hưởng đến việc cụm thống nhất metadata và quyết định broker nào đang giữ vai trò leader cho từng partition.

### 4.1. Vai trò của controller trong KRaft

Trong KRaft, các controller duy trì metadata log bằng Raft. Một controller được bầu làm active controller; các controller còn lại tham gia quorum để sao chép metadata log và có thể đảm nhận vai trò active khi cần.

Controller quản lý các thay đổi như:

- Đăng ký và theo dõi trạng thái broker.
- Tạo hoặc xóa topic.
- Tạo partition và thay đổi assignment.
- Bầu leader và xử lý thay đổi trạng thái partition.
- Cập nhật metadata để broker và client sử dụng.

Controller không nhận mọi record produce/fetch thay cho partition leader. Vì thế, cần phân biệt lỗi controller với lỗi broker đang trực tiếp phục vụ dữ liệu.

### 4.2. Mất quorum controller

Quorum cần đa số thành viên để tiếp tục tiến triển. Với ba controller, cần ít nhất hai thành viên hoạt động và giao tiếp được để có majority. Nếu chỉ còn một controller, quorum không thể commit metadata mới.

Khi mất quorum:

- Controller không thể tiếp tục commit metadata log một cách an toàn.
- Thay đổi cấu trúc như tạo topic, thay đổi partition assignment hoặc các thao tác điều phối có thể thất bại hoặc chờ.
- Nếu active controller mất và không còn quorum để bầu controller mới, control plane không thể phục hồi vai trò active.
- Một số partition đang có leader và metadata đã ổn định có thể tiếp tục phục vụ data plane.
- Partition cần leader election mới hoặc thay đổi metadata có thể tiếp tục unavailable cho đến khi quorum phục hồi.

Đây là lý do controller quorum cần số node lẻ phù hợp, phân bố failure domain hợp lý và có giám sát riêng. Chạy ba controller trên cùng một máy hoặc cùng một failure domain không tạo ra khả năng chịu lỗi thực tế như ba miền độc lập.

### 4.3. Controller election và metadata propagation

Khi active controller dừng hoặc mất kết nối, quorum có thể bầu controller mới nếu còn majority. Trong quá trình chuyển vai trò:

- Một số thao tác AdminClient có thể timeout hoặc nhận lỗi tạm thời.
- Broker có thể cần cập nhật metadata.
- Partition leader có thể thay đổi.
- Client có thể tạm thời dùng metadata cũ và gửi request đến broker không còn là leader.
- Các request có thể thành công trở lại sau khi metadata mới được phân phối và client refresh metadata.

Những lỗi như NOT_CONTROLLER hoặc lỗi metadata liên quan thường cần xem trong ngữ cảnh Admin API và trạng thái controller, không nên tự động quy thành broker lưu dữ liệu bị hỏng.

### 4.4. Broker registration và cluster identity

Khi broker khởi động, nó phải tham gia đúng cluster và đăng ký với controller. Một số lỗi khởi động hoặc gia nhập cụm có thể đến từ:

- Cluster ID không khớp.
- Node ID bị trùng hoặc cấu hình không đúng.
- Metadata directory đã format với cluster identity khác.
- Controller quorum không thể truy cập.
- Cấu hình listener hoặc security giữa broker và controller không tương thích.
- Broker bị fencing hoặc bị loại khỏi trạng thái cụm.

Với KRaft, metadata directory và cluster ID là phần quan trọng của danh tính cụm. Không nên tùy tiện xóa metadata directory hoặc chạy lại lệnh format để thử khắc phục một broker không gia nhập được. Cần đọc log khởi động, xác định trạng thái storage và đối chiếu cluster identity trước khi can thiệp.

## 5. Bảng phân biệt ba nhóm lỗi

| Tiêu chí | Lỗi client | Lỗi broker | Lỗi điều phối cụm |
|---|---|---|---|
| Phạm vi thường gặp | Một ứng dụng, instance hoặc consumer group | Một broker hoặc các partition liên quan | Metadata và nhiều broker/partition |
| Thành phần chính | Code, client config, serializer, network phía client | Broker process, partition log, replica, disk, network | Active controller, controller quorum, metadata log |
| Ví dụ | SerializationException, sai SASL config, ACL thiếu quyền, lỗi listener | Broker unavailable, leader unavailable, ISR giảm, disk đầy | Mất controller quorum, controller election, broker registration lỗi |
| Triệu chứng | Chỉ một client hoặc một loại record thất bại | Partition cụ thể unavailable hoặc latency tăng theo broker | Admin operation thất bại, metadata/leader transition bị đình trệ |
| Dữ liệu đã ghi chưa? | Có thể chưa gửi, đã ghi hoặc kết quả chưa rõ nếu timeout | Có thể đã append một phần hoặc chưa đáp ứng durability | Request có thể chờ hoặc thất bại do metadata chưa thể thay đổi |
| Hướng xử lý | Sửa code, schema, credential, network/config client | Khôi phục broker, disk, replica và ISR | Khôi phục majority controller, controller election và metadata propagation |

Bảng này mô tả phạm vi thường gặp. Một lỗi client có thể là hậu quả của broker hoặc controller; ngược lại, một cấu hình sai được triển khai đồng loạt có thể khiến mọi client cùng thất bại dù cụm vẫn khỏe.

## 6. Quy trình chẩn đoán theo thứ tự

Khi có sự cố, hãy bắt đầu từ phạm vi ảnh hưởng rồi mới đi sâu vào từng thành phần.

### Bước 1: Xác định lỗi xảy ra ở đâu và khi nào

Ghi nhận:

- Thời điểm bắt đầu và kết thúc.
- Ứng dụng, client ID, consumer group và topic liên quan.
- Partition, offset và broker được nhắc trong exception.
- Lỗi ảnh hưởng một record, một partition, một broker hay toàn bộ cụm.
- Các thay đổi gần đây: deploy ứng dụng, rotate certificate, đổi ACL, restart broker, tăng partition hoặc thay đổi cấu hình.

Nếu chỉ một consumer gặp SerializationException trên một offset, hãy bắt đầu từ dữ liệu và deserializer. Nếu nhiều producer/consumer cùng gặp lỗi trên nhiều topic trong cùng thời điểm, cần mở rộng kiểm tra sang broker, network và controller.

### Bước 2: Đọc root cause và khả năng retry

Không chỉ ghi lại dòng exception ngoài cùng. Hãy lấy nguyên nhân sâu nhất, error code Kafka nếu có, broker trả lời và trạng thái retryable.

Phân loại ban đầu:

- Lỗi dữ liệu/schema/configuration cố định: thường không retry cho đến khi sửa nguyên nhân.
- Lỗi leader/metadata tạm thời: client có thể refresh metadata và retry theo cơ chế của Kafka.
- Lỗi broker quá tải hoặc network chập chờn: retry có backoff và giới hạn.
- Lỗi authorization: sửa ACL hoặc credential, không retry vô hạn.
- Timeout không rõ kết quả: kiểm tra event ID và khả năng duplicate trước khi gửi lại bằng logic nghiệp vụ.

### Bước 3: Kiểm tra topic, leader, replica và ISR

Dùng lệnh mô tả topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --topic orders
~~~

Quan sát:

- Partition có leader hay không.
- Danh sách replicas và ISR.
- Partition nào under-replicated hoặc offline.
- Có nhiều partition cùng phụ thuộc vào một broker bị lỗi không.

Nếu một broker vừa restart, hãy theo dõi ISR có phục hồi hay không. Không ép leader election hoặc xóa dữ liệu replica khi chưa hiểu trạng thái bản sao.

### Bước 4: Kiểm tra controller quorum trong KRaft

Có thể xem trạng thái quorum bằng công cụ metadata quorum:

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server broker-1:9092 \
  describe \
  --status
~~~

Kiểm tra leader ID, epoch, số voter và trạng thái quorum theo phiên bản Kafka đang vận hành. Nếu lệnh không truy cập được, hãy kiểm tra broker endpoint, listener, bảo mật và log của các controller.

Trong môi trường production, cần kiểm tra riêng log controller và broker, vì lỗi controller không phải lúc nào cũng xuất hiện đầy đủ trong log của broker đang nhận request từ ứng dụng.

### Bước 5: Kiểm tra broker và hạ tầng

Kiểm tra:

- Tiến trình Kafka và restart count.
- CPU, heap, garbage collection và memory pressure.
- Disk utilization, latency, dung lượng trống và log directory.
- Network throughput, retransmission và kết nối giữa broker/controller.
- Request latency, request queue và network processor.
- Replica fetch lag, under-replicated partitions và offline partitions.

Các metric thường hữu ích gồm UnderReplicatedPartitions, OfflinePartitionsCount, IsrShrinksPerSec, request latency, request handler idle, network processor idle và disk/log directory health. Tên metric hoặc cách expose có thể khác theo phiên bản và cấu hình.

### Bước 6: Kiểm tra consumer group và downstream

Nếu producer vẫn ghi được nhưng ứng dụng không xử lý kịp, kiểm tra lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --group billing-service
~~~

Xác định lag tăng ở partition nào, consumer nào không có assignment, offset có tiến triển không và listener có bị kẹt ở một record lỗi hay không. Kiểm tra thêm database, HTTP service hoặc hệ thống downstream mà listener gọi đến.

### Bước 7: Xác nhận phục hồi bằng dữ liệu và hành vi ứng dụng

Sau khi sửa nguyên nhân:

- Produce một record kiểm thử có event ID xác định.
- Xác nhận broker trả kết quả và record xuất hiện trong partition dự kiến.
- Consume record bằng group phù hợp.
- Kiểm tra không có duplicate hoặc side effect lặp.
- Xác nhận ISR, offline partition, consumer lag và controller quorum đã ổn định.
- Theo dõi một khoảng thời gian đủ dài để chắc chắn lỗi không tái diễn.

## 7. Xử lý retry đúng cách trong Java và Spring Kafka

Retry chỉ có ích khi lỗi có khả năng tự phục hồi. Một chính sách tốt cần phân loại lỗi, backoff, giới hạn số lần thử và cơ chế chống trùng.

### 7.1. Producer: quan sát kết quả gửi

Với Spring Kafka 3.x, KafkaTemplate.send trả về CompletableFuture. Có thể ghi nhận kết quả gửi và phân loại exception:

~~~java
@Service
public class EventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public EventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate
            .send("orders", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Ghi event ID, topic, key và root cause.
                    // Chuyển lỗi đến chính sách retry phù hợp.
                    handlePublishFailure(event, exception);
                    return;
                }

                // Ghi nhận topic, partition và offset khi cần.
                handlePublishSuccess(event, result);
            });
    }

    private void handlePublishFailure(
            OrderCreated event,
            Throwable exception) {
        // Phân loại retriable/permanent và xử lý idempotent.
    }

    private void handlePublishSuccess(
            OrderCreated event,
            SendResult<String, OrderCreated> result) {
        // Ghi nhận metadata của record đã gửi.
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thực tế, cần bảo đảm event ID ổn định và không nuốt exception khiến caller tưởng rằng nghiệp vụ đã hoàn tất. Nếu việc publish là một phần của transaction nghiệp vụ, cân nhắc transactional outbox thay vì chỉ dựa vào callback.

### 7.2. Consumer: retry có giới hạn và dead-letter

Với lỗi tạm thời từ database hoặc dịch vụ downstream, có thể retry với backoff tăng dần. Với lỗi schema hoặc payload không hợp lệ, thường nên chuyển record sang dead-letter topic sau khi lưu đủ thông tin điều tra.

Spring Kafka cung cấp DefaultErrorHandler và DeadLetterPublishingRecoverer để xây dựng cơ chế này. Cấu hình cần xác định rõ:

- Exception nào được retry.
- Exception nào được coi là không thể phục hồi.
- Số lần retry và thời gian backoff.
- Topic đích của dead-letter record.
- Cách giữ key, headers và exception metadata.
- Quy trình phát lại sau khi sửa lỗi dữ liệu hoặc code.

Không nên retry vô hạn một record lỗi vì nó có thể làm partition không tiến triển và tăng lag cho toàn bộ consumer group.

### 7.3. Timeout và kết quả ghi không chắc chắn

Nếu producer timeout, không phải lúc nào cũng biết record đã được ghi hay chưa. Hãy dùng idempotent producer và cấu hình retry phù hợp. Ở tầng nghiệp vụ, gắn event ID hoặc idempotency key để consumer có thể nhận diện bản tin gửi lại.

Nếu side effect nằm trong database, dùng unique constraint, inbox table hoặc transaction phù hợp. Kafka exactly-once không tự mở rộng thành exactly-once cho mọi hệ thống bên ngoài.

### 7.4. Không retry mù quáng các lỗi fencing hoặc bảo mật

Một số lỗi cần thay đổi trạng thái ứng dụng hoặc cấu hình thay vì retry cùng request:

- ProducerFencedException: producer transactional đã bị fencing bởi producer khác cùng transactional ID; instance cũ cần dừng.
- AuthenticationException: credential hoặc cấu hình authentication cần được sửa.
- AuthorizationException: principal thiếu quyền; cần kiểm tra ACL.
- SerializationException: dữ liệu hoặc serializer cần được sửa.
- RecordTooLargeException: cần kiểm tra kích thước record và giới hạn tương ứng.
- InvalidTopicException hoặc cấu hình không hợp lệ: cần sửa tên topic hoặc cấu hình.

Đối với lỗi broker/leader tạm thời, Kafka client thường có cơ chế retry và metadata refresh. Hãy hiểu cấu hình retries, delivery.timeout.ms, request.timeout.ms, retry.backoff.ms và enable.idempotence thay vì tự viết vòng lặp retry không giới hạn bên ngoài client.

## 8. Tình huống thực tế và cách suy luận

### Tình huống A: Chỉ một consumer không đọc được record

Một consumer báo DeserializationException tại một offset, trong khi consumer group khác vẫn đọc topic bình thường.

Khả năng cao là lỗi dữ liệu, schema hoặc deserializer của ứng dụng. Kiểm tra raw record, schema version và cấu hình consumer. Nếu record không thể xử lý, đưa vào dead-letter theo chính sách rồi cho partition tiếp tục.

### Tình huống B: Nhiều producer cùng timeout trên một broker

Nhiều ứng dụng gửi đến các partition có leader trên broker-2 và cùng timeout. Các partition trên broker khác vẫn hoạt động.

Đây là dấu hiệu cần kiểm tra broker-2, network, disk, request queue và leader assignment. Xem partition nào offline hoặc under-replicated, sau đó kiểm tra broker log và tài nguyên máy chủ.

### Tình huống C: Topic creation và AdminClient đều thất bại

Các lệnh tạo topic hoặc thay đổi partition thất bại trong khi một số producer vẫn ghi vào partition đang hoạt động.

Cần kiểm tra active controller, KRaft quorum, controller log và khả năng broker kết nối đến controller. Nếu mất majority, control plane không thể commit metadata mới dù một số data-plane request vẫn chạy.

### Tình huống D: Một broker dừng, ISR giảm và producer bị từ chối ghi

Topic có replication factor 3, min.insync.replicas 2 và acks=all. Sau khi broker mất kết nối, một số partition chỉ còn một replica trong ISR.

Broker từ chối ghi để giữ điều kiện durability đã cấu hình. Khôi phục broker hoặc replica để ISR trở lại ngưỡng. Không hạ min.insync.replicas chỉ để loại bỏ lỗi khi chưa đánh giá nguy cơ mất dữ liệu.

### Tình huống E: Mọi client từ một mạng đều không truy cập được

Client trong cùng một subnet timeout khi kết nối đến broker, nhưng client trong mạng khác vẫn hoạt động.

Kiểm tra firewall, DNS, route, TLS inspection và advertised.listeners. Việc broker khỏe không bảo đảm mọi mạng client đều truy cập được địa chỉ mà broker quảng bá.

## 9. Những nhầm lẫn thường gặp

- **“Exception xuất hiện ở producer nghĩa là lỗi do producer.”** Client là nơi quan sát lỗi; nguyên nhân có thể nằm ở broker, network hoặc controller.
- **“Timeout chắc chắn record chưa được ghi.”** Kết quả có thể không rõ. Gửi lại cần có idempotency hoặc event ID.
- **“Một broker chết đồng nghĩa toàn bộ cluster dừng.”** Ảnh hưởng phụ thuộc partition leader, replica, ISR và phân bố tải.
- **“Mất controller quorum làm mọi produce/fetch dừng ngay.”** Data plane của partition đang có leader có thể tiếp tục một số hoạt động; các thay đổi metadata và leader election cần controller có thể bị đình trệ.
- **“NOT_LEADER_OR_FOLLOWER nghĩa là dữ liệu hỏng.”** Thường cần refresh metadata và kiểm tra leader assignment; đây có thể là lỗi tạm thời trong chuyển leader.
- **“Retry tất cả exception sẽ làm hệ thống bền vững hơn.”** Retry lỗi cố định làm tăng tải, kéo dài sự cố và có thể giữ partition ở một record không thể xử lý.
- **“Hạ min.insync.replicas luôn là cách khôi phục nhanh.”** Điều này làm giảm mức bảo vệ dữ liệu khi replica không đủ.
- **“KRaft controller và broker là một vai trò.”** Chúng có thể cùng nằm trên một node ở chế độ combined, nhưng vai trò điều phối metadata và phục vụ partition vẫn khác nhau.

## 10. Kết luận

Lỗi client, lỗi broker và lỗi điều phối cụm khác nhau ở nơi phát sinh và phạm vi ảnh hưởng. Lỗi client thường nằm ở code, schema, serializer, cấu hình kết nối hoặc bảo mật. Lỗi broker liên quan đến tiến trình, partition leader, replica, ISR và tài nguyên máy chủ. Lỗi điều phối cụm liên quan đến controller, metadata log và quorum KRaft.

Khi xử lý sự cố, hãy xác định phạm vi trước, đọc root cause và error code, kiểm tra leader/ISR, sau đó xác minh controller quorum và tài nguyên broker. Chỉ retry lỗi có khả năng phục hồi, dùng backoff và giới hạn số lần thử; với timeout hoặc side effect bên ngoài Kafka, luôn thiết kế idempotency. Cách phân loại theo data plane và control plane giúp tìm đúng thành phần cần khôi phục, giảm retry không cần thiết và bảo vệ tính nhất quán của luồng sự kiện.
