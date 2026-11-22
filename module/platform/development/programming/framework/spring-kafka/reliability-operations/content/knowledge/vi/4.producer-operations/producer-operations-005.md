# Xử lý unknown topic hoặc partition

Trong vận hành producer Kafka, lỗi **unknown topic hoặc partition** xuất hiện khi broker không thể xác định topic hoặc partition mà request đang tham chiếu. Producer có thể đã kết nối được tới cluster nhưng vẫn không gửi được record vì topic chưa tồn tại, tên topic sai, partition được chỉ định không hợp lệ hoặc metadata mà client đang dùng chưa phản ánh trạng thái hiện tại.

Lỗi này thường được biểu diễn bằng **UnknownTopicOrPartitionException** ở Kafka client. Đây là lỗi có thể retry vì đôi khi nguyên nhân chỉ là metadata chưa cập nhật hoặc topic vừa được tạo. Tuy nhiên, nếu topic thực sự không tồn tại, producer đang trỏ nhầm cluster hoặc ứng dụng gửi tới partition không có, retry liên tục sẽ không giải quyết được nguyên nhân.

Trong chương **Producer vận hành**, cần xử lý lỗi theo hai hướng: xác định chính xác topic/partition và trạng thái cluster; sau đó quyết định để Kafka client tự retry, sửa cấu hình, tạo topic theo quy trình quản trị hay điều chỉnh logic chọn partition.

## 1. Hiểu lỗi unknown topic hoặc partition

Kafka lưu dữ liệu trong topic, mỗi topic gồm một hoặc nhiều partition. Producer gửi record đến một partition cụ thể. Để thực hiện việc đó, producer cần metadata về topic, partition, leader broker và các thông tin liên quan.

Broker có thể trả lỗi **UNKNOWN_TOPIC_OR_PARTITION** khi topic hoặc partition được yêu cầu không được nhận diện tại thời điểm xử lý. Ở phía Java client, lỗi thường xuất hiện dưới dạng **org.apache.kafka.common.errors.UnknownTopicOrPartitionException**.

Tên lỗi gộp hai trường hợp:

- **Unknown topic**: topic không tồn tại trong cluster mà client đang kết nối, hoặc broker chưa có metadata hợp lệ cho topic đó.
- **Unknown partition**: topic có thể tồn tại nhưng partition được request tham chiếu không tồn tại hoặc chưa được broker nhận diện tại thời điểm đó.

Đây là lỗi ở tầng metadata/định tuyến của Kafka. Nó không tự động có nghĩa broker đã mất dữ liệu, producer không có quyền truy cập, hoặc record đã bị ghi rồi mất.

### 1.1 Producer cần metadata như thế nào?

Trước khi gửi record, producer cần biết partition đích và broker leader của partition. Kafka client lưu metadata trong bộ nhớ và cập nhật metadata theo chu kỳ hoặc khi gặp lỗi cần làm mới metadata.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant P as Kafka producer
    participant M as Kafka metadata
    participant L as Partition leader

    App->>P: send(topic, key, value)
    P->>M: Lấy metadata topic/partition
    M-->>P: Partition list và leader
    P->>L: Produce request
    alt Topic/partition hợp lệ
        L-->>P: ACK hoặc lỗi ghi khác
        P-->>App: Hoàn tất future
    else Metadata chưa hợp lệ
        L-->>P: UNKNOWN_TOPIC_OR_PARTITION
        P->>M: Refresh metadata
        P->>L: Retry nếu còn thời gian
        P-->>App: Thành công hoặc future hoàn tất lỗi
    end
~~~

Producer có thể chưa gửi record ngay khi gọi **send()**: client có thể phải chờ metadata trước. Khi metadata không sẵn sàng hoặc broker trả lỗi retriable, client có thể refresh metadata và thử lại theo chính sách retry, trong giới hạn thời gian gửi.

Vì vậy, cần phân biệt:

- Ứng dụng gọi **send()** thành công về mặt API: request đã được đưa vào quy trình gửi bất đồng bộ, chưa chắc broker đã ghi record.
- Producer nhận ACK: broker đã xác nhận ghi theo cấu hình **acks**.
- Producer nhận exception: lần gửi không hoàn tất thành công theo chính sách hiện tại. Với timeout hoặc kết nối đứt, kết quả có thể không rõ ràng nếu broker đã ghi nhưng ACK không đến client.

## 2. Những nguyên nhân thường gặp

### 2.1 Topic chưa được tạo

Ứng dụng gửi record tới topic mới nhưng topic chưa được tạo trong cluster. Tình huống thường gặp khi:

- Producer service được triển khai trước bước provisioning topic.
- Topic được tạo thủ công ở môi trường dev nhưng bị thiếu ở staging hoặc production.
- Pipeline triển khai ứng dụng không có dependency tới bước tạo topic.
- Topic bị xóa trong lúc ứng dụng vẫn tiếp tục gửi.
- Tên topic được cấu hình nhưng không có resource tương ứng trong Kafka.

Nếu cluster tắt tự động tạo topic, producer không thể tự tạo topic chỉ bằng việc gửi record. Broker trả lỗi và producer có thể retry cho đến khi hết thời gian gửi.

**Cách xử lý:** xác minh đúng cluster và tên topic, sau đó tạo topic qua quy trình quản trị được phê duyệt. Kiểm tra metadata sau khi tạo để bảo đảm producer có thể nhìn thấy topic và các partition.

### 2.2 Sai tên topic

Tên topic thường phân biệt chữ hoa và chữ thường. Các lỗi cấu hình như **order-events**, **order_event**, **Order-Events** hoặc một dấu gạch nối/underscore khác nhau có thể khiến producer gửi đến một tên không tồn tại.

Nguồn gây sai tên thường là:

- Hard-code tên topic ở nhiều module.
- Profile Spring khác nhau giữa local, staging và production.
- Biến môi trường bị thiếu hoặc chứa khoảng trắng.
- Tên topic được ghép từ prefix môi trường hoặc tenant.
- Producer và consumer dùng hai naming convention khác nhau.

Không nên tự động tạo topic mỗi khi gặp một tên mới. Nếu tên sai mà broker cho phép auto-create, cluster có thể tạo ra một topic ngoài ý muốn, khiến record bị gửi nhầm và consumer chính không nhận được dữ liệu.

**Cách xử lý:** log tên topic thực tế sau khi resolve cấu hình; so sánh với danh sách topic trong đúng cluster; chuẩn hóa tên topic ở một nơi dùng chung và kiểm tra cấu hình khi khởi động.

### 2.3 Producer kết nối nhầm Kafka cluster

Một topic có thể tồn tại ở production nhưng không tồn tại trong cluster mà producer đang sử dụng. Điều này thường xảy ra khi:

- **bootstrap-servers** trỏ tới cluster khác.
- Secret hoặc ConfigMap của môi trường bị gắn nhầm.
- Service DNS phân giải sang endpoint cũ.
- Ứng dụng dùng profile mặc định thay vì profile triển khai.
- Có nhiều cluster cho từng region, tenant hoặc workload.

Đây là nguyên nhân cần kiểm tra sớm khi topic “chắc chắn có tồn tại” theo hiểu biết của đội vận hành. Danh sách topic phải được kiểm tra trên cùng cluster mà producer thực sự kết nối.

Không ghi credentials hoặc toàn bộ secret vào log để chứng minh cluster. Có thể log tên môi trường, alias cluster, bootstrap endpoint đã được làm sạch và cluster id lấy từ công cụ quản trị nếu quy trình cho phép.

### 2.4 Chỉ định partition không tồn tại

Producer có thể chỉ định partition rõ ràng thay vì để partitioner chọn:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        7,
        "order-1001",
        "{\"status\":\"CREATED\"}"
    );
~~~

Tham số partition là **index bắt đầu từ 0**. Nếu topic có 6 partition, index hợp lệ là **0** đến **5**. Index **6** hoặc **7** không tồn tại trong topic đó.

Lỗi có thể xuất hiện khi:

- Code hard-code partition id.
- Ứng dụng dùng số partition theo cấu hình cũ.
- Topic được tạo với ít partition hơn dự kiến.
- Một service giả định partition count giống nhau ở mọi môi trường.
- Partition count thay đổi nhưng producer vẫn dùng logic cũ.

Nếu producer không chỉ định partition, Kafka partitioner sẽ chọn dựa trên metadata, key và cấu hình partitioner. Khi code chỉ định partition tường minh, ứng dụng phải chịu trách nhiệm bảo đảm index hợp lệ.

**Cách xử lý:** mô tả topic để lấy partition count và danh sách partition id; kiểm tra nơi tạo **ProducerRecord**; bỏ hard-code nếu không có yêu cầu định tuyến nghiệp vụ thực sự.

### 2.5 Topic vừa được tạo, xóa hoặc thay đổi

Ngay sau khi topic được tạo, metadata có thể chưa đồng nhất ở mọi broker hoặc chưa được client cập nhật. Một producer đang giữ metadata cũ có thể gặp lỗi tạm thời khi topic vừa xuất hiện.

Các tình huống khác:

- Topic bị xóa trong khi producer đang gửi.
- Topic được xóa rồi tạo lại với cấu hình hoặc partition count khác.
- Leader của partition đang được bầu hoặc thay đổi.
- Controller/metadata quorum đang gặp vấn đề.
- Broker vừa restart hoặc đang phục hồi metadata.

Trong những trường hợp này, lỗi có thể chỉ tồn tại ngắn hạn. Kafka client có cơ chế metadata refresh và retry cho các lỗi retriable. Tuy nhiên, ứng dụng vẫn phải có timeout và quan sát kết quả cuối cùng.

Không nên xóa rồi tạo lại topic để “làm mới metadata” như một cách xử lý mặc định. Việc xóa topic có thể làm mất dữ liệu và phá vỡ contract với consumer.

### 2.6 Auto-create topic bị tắt hoặc hoạt động ngoài dự kiến

Kafka có tùy chọn broker **auto.create.topics.enable**. Tùy cấu hình cluster và loại request/client, việc truy cập topic chưa tồn tại có thể dẫn tới tự động tạo topic hoặc bị từ chối. Một số môi trường quản trị tắt auto-create để tránh topic phát sinh ngoài kiểm soát.

Không nên phụ thuộc vào auto-create cho topic nghiệp vụ quan trọng vì:

- Topic có thể được tạo với partition count hoặc replication factor mặc định không phù hợp.
- Retention, cleanup policy, min ISR và quota có thể không đúng yêu cầu.
- Tên topic sai có thể tạo ra topic rác.
- Quyền tạo topic có thể khác quyền ghi topic.
- Hành vi có thể khác giữa các môi trường và phiên bản.

Hãy provision topic tường minh bằng IaC, công cụ quản trị hoặc quy trình release. Producer nên bắt đầu gửi sau khi topic đã được tạo và xác minh.

## 3. Phân biệt unknown topic/partition với các lỗi Kafka khác

Nhiều lỗi cùng xuất hiện khi producer không gửi được record, nhưng cách khắc phục khác nhau. Không nên gom mọi exception thành “topic không tồn tại”.

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý chính |
|---|---|---|
| **UnknownTopicOrPartitionException** | Broker không nhận diện topic hoặc partition tại thời điểm request | Kiểm tra cluster, topic, partition, metadata và provisioning |
| **InvalidTopicException** | Tên topic không hợp lệ theo quy tắc Kafka | Sửa tên topic; kiểm tra ký tự và naming convention |
| **TopicAuthorizationException** | Principal không có quyền với topic | Kiểm tra ACL và service account |
| **ClusterAuthorizationException** | Principal không có quyền thực hiện thao tác cấp cluster | Kiểm tra quyền cluster/admin phù hợp |
| **LeaderNotAvailableException** | Partition chưa có leader khả dụng | Kiểm tra leader election, broker và trạng thái partition |
| **NotLeaderOrFollowerException** | Request đến broker không còn là leader hoặc không đúng vai trò | Refresh metadata; kiểm tra leader và broker |
| **TimeoutException** | Request không hoàn tất trong giới hạn thời gian | Kiểm tra network, broker latency, retry và delivery timeout |
| **NetworkException** | Kết nối tới broker bị gián đoạn | Kiểm tra DNS, route, TLS, firewall và broker |
| **NotEnoughReplicasException** | ISR thấp hơn min ISR khi ghi với policy yêu cầu | Khôi phục replica/ISR và kiểm tra durability policy |

Một số lỗi có thể xuất hiện liên tiếp trong cùng một sự cố. Ví dụ, topic được tạo nhưng leader chưa sẵn sàng có thể dẫn đến lỗi leader; một ACL sai có thể khiến thao tác AdminClient không thể mô tả topic. Cần ghi nhận exception gốc và trạng thái metadata để xác định lỗi đầu tiên.

### 3.1 Không nhầm lỗi phân quyền với topic không tồn tại

Nếu principal không có quyền đọc/ghi hoặc mô tả topic, Kafka thường trả lỗi authorization tương ứng. Không nên kết luận topic không tồn tại chỉ vì ứng dụng không thể nhìn thấy topic qua công cụ quản trị.

Khi kiểm tra bằng CLI hoặc AdminClient, dùng đúng principal và security configuration tương đương với producer. Một tài khoản quản trị nhìn thấy topic không chứng minh service account của producer có đủ quyền.

### 3.2 Không nhầm partition chưa có leader với partition không tồn tại

Partition có thể tồn tại nhưng tạm thời không có leader khả dụng. Đây là tình trạng khác với partition id không có trong topic. Kiểm tra describe để xem partition id, leader, replicas và ISR. Nếu partition tồn tại nhưng leader là trạng thái không khả dụng, xử lý broker/controller thay vì tạo thêm topic hoặc tăng partition count.

## 4. Quy trình chẩn đoán từ producer

Khi thấy **UnknownTopicOrPartitionException**, nên thu thập dữ liệu trước khi thay đổi cấu hình.

### Bước 1: Ghi nhận đầy đủ ngữ cảnh lỗi

Tối thiểu cần có:

- Thời điểm xảy ra lỗi.
- Tên topic thực tế sau khi resolve cấu hình.
- Partition id nếu ứng dụng chỉ định tường minh hoặc exception cung cấp thông tin.
- Producer client id và application instance.
- Bootstrap endpoint/cluster alias đã làm sạch.
- Exception class, root cause và số lần retry.
- Key hoặc event id để đối chiếu nghiệp vụ; tránh log payload nhạy cảm.
- Kết quả gửi cuối cùng và thời gian gửi đã tiêu tốn.

Không chỉ log **Failed to send message**. Cần ghi đủ thông tin để xác định producer gửi tới topic nào, trên cluster nào và request thất bại ở bước nào.

### Bước 2: Xác minh cluster

So sánh bootstrap server và môi trường của producer với cluster dự kiến. Nếu dùng nhiều profile, kiểm tra giá trị hiệu lực trong runtime chứ không chỉ file YAML trong repository.

Kiểm tra DNS, service discovery và secret/config injection nếu endpoint khác với dự kiến. Đảm bảo producer không dùng nhầm cluster dev hoặc staging.

### Bước 3: Xác minh topic

Dùng công cụ Kafka với đúng bootstrap endpoint và principal:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

Để mô tả topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders
~~~

Lệnh describe giúp xem partition count, leader, replicas và ISR. Nếu lệnh báo topic không tồn tại, xác minh lại cluster và tên topic trước khi tạo.

Trong môi trường bật TLS/SASL, cần truyền đúng client configuration theo quy trình bảo mật của môi trường. Không đưa password hoặc secret trực tiếp vào shell history hay log.

### Bước 4: Xác minh partition

Nếu topic tồn tại, kiểm tra partition id được khai báo trong code có nằm trong danh sách partition hay không.

Ví dụ topic có 4 partition thì các id hợp lệ là:

~~~text
0
1
2
3
~~~

Nếu ứng dụng chỉ định partition **4**, sửa logic hoặc cấu hình. Không tăng partition count chỉ để che lỗi index nếu định tuyến nghiệp vụ không yêu cầu điều đó.

Nếu partition tồn tại nhưng leader không khả dụng, kiểm tra broker leader, replica, ISR và controller.

### Bước 5: Kiểm tra thay đổi gần thời điểm lỗi

Đối chiếu với lịch sử triển khai:

- Topic vừa được tạo hoặc xóa?
- Có thay đổi partition count?
- Có thay đổi bootstrap server hoặc secret?
- Có release producer mới?
- Có thay đổi ACL?
- Có broker restart, controller failover hoặc network maintenance?
- Có thay đổi auto-create policy?

Mốc thời gian giúp phân biệt lỗi do provisioning race với lỗi cấu hình kéo dài.

### Bước 6: Xác định retry còn phù hợp không

Nếu topic vừa được tạo và metadata đang hội tụ, để Kafka client refresh metadata và retry trong delivery timeout có thể đủ.

Nếu tên topic sai, cluster sai hoặc partition index không tồn tại, retry chỉ lặp lại cùng lỗi. Sửa nguyên nhân cấu hình/logic và xử lý các record chưa gửi theo chính sách nghiệp vụ.

## 5. Xử lý theo từng tình huống

### 5.1 Topic chưa tồn tại

1. Xác minh tên topic và cluster.
2. Kiểm tra topic có nằm trong manifest/IaC hoặc danh sách resource của môi trường không.
3. Tạo topic qua quy trình quản trị được phê duyệt.
4. Chọn partition count, replication factor, retention, cleanup policy và min ISR theo yêu cầu.
5. Mô tả topic sau khi tạo để xác nhận leader/replica/ISR.
6. Cho producer gửi lại các event đang chờ theo cơ chế retry/outbox.

Không nên cấp quyền create topic rộng cho mọi producer chỉ để tự xử lý lỗi. Quyền tạo topic có thể tạo ra sai lệch cấu hình và topic ngoài kiểm soát.

### 5.2 Sai tên topic trong cấu hình

- Log tên topic thực tế sau khi resolve.
- So sánh với topic chuẩn của môi trường.
- Kiểm tra prefix/suffix, dấu phân cách và chữ hoa/chữ thường.
- Chuyển tên topic thành cấu hình tập trung hoặc constant dùng chung.
- Thêm kiểm tra cấu hình khi ứng dụng khởi động.
- Triển khai bản sửa và xác nhận record được gửi tới đúng topic.

Nếu producer đã gửi record vào một topic ngoài ý muốn do auto-create, cần đánh giá dữ liệu ở topic đó trước khi xóa. Không xóa topic ngay khi chưa xác định có consumer hoặc dữ liệu hợp lệ nào đang sử dụng.

### 5.3 Chỉ định partition không hợp lệ

Tìm nơi tạo **ProducerRecord** hoặc nơi gọi **KafkaTemplate.send** với tham số partition.

Ví dụ Spring Kafka gửi tới partition tường minh:

~~~java
kafkaTemplate.send(
    "orders",
    2,
    "order-1001",
    orderCreated
);
~~~

Partition **2** là partition thứ ba vì index bắt đầu từ 0. Chỉ dùng cách gửi này khi nghiệp vụ thực sự yêu cầu chọn partition cụ thể, ví dụ định tuyến theo shard đã được quản trị.

Nếu muốn Kafka chọn partition theo key, dùng overload không truyền partition:

~~~java
kafkaTemplate.send(
    "orders",
    "order-1001",
    orderCreated
);
~~~

Partitioner mặc định sẽ sử dụng key và metadata để chọn partition. Với key có giá trị, các record cùng key thường được định tuyến tới cùng partition khi partition count và partitioner không đổi. Khi tăng số partition, mapping của key có thể thay đổi; không nên giả định key luôn gắn vĩnh viễn với một partition id.

### 5.4 Topic vừa tạo nhưng producer vẫn lỗi

- Xác nhận lệnh tạo topic đã hoàn tất thành công.
- Chờ metadata topic/partition được broker công bố.
- Dùng describe topic để kiểm tra partition và leader.
- Để producer refresh metadata và retry trong thời gian hợp lý.
- Nếu lỗi kéo dài, kiểm tra controller, broker, network và quyền truy cập.
- Tránh tạo/xóa topic liên tục vì có thể làm trạng thái metadata phức tạp hơn.

Đối với pipeline release, thêm bước chờ topic sẵn sàng sau khi provisioning. Không chỉ kiểm tra lệnh create đã trả về; cần xác minh topic có partition và leader hợp lệ trước khi mở traffic producer.

### 5.5 Partition count thay đổi

Kafka cho phép tăng số partition của topic trong các điều kiện phù hợp, nhưng không hỗ trợ giảm partition count theo cách thông thường. Khi tăng partition count:

- Producer cần cập nhật metadata để nhìn thấy partition mới.
- Partitioner có thể phân phối record sang các partition mới.
- Key-to-partition mapping có thể thay đổi.
- Consumer group có thể rebalance để nhận partition mới.
- Thứ tự toàn cục không được đảm bảo; thứ tự chỉ có ý nghĩa trong từng partition.

Nếu producer hard-code partition id, cần kiểm tra partition mới đã tồn tại trước khi gửi. Nếu code chỉ dùng key, vẫn cần xác nhận logic nghiệp vụ có chấp nhận thay đổi mapping khi tăng partition hay không.

### 5.6 Broker hoặc metadata cluster đang phục hồi

Nếu topic và partition đều tồn tại nhưng lỗi xảy ra trong lúc broker/controller phục hồi:

- Kiểm tra cluster health và controller/quorum.
- Kiểm tra leader của partition có sẵn sàng không.
- Theo dõi leader election và ISR.
- Xác nhận broker đã phục vụ metadata request ổn định.
- Để client retry có giới hạn; tránh khởi động lại tất cả producer đồng loạt nếu không cần thiết.

Nếu lỗi kéo dài, xử lý theo runbook Kafka cluster. Không tạo topic trùng tên hoặc thay đổi partition count để phản ứng với lỗi metadata tạm thời.

## 6. Kafka client retry và metadata refresh

**UnknownTopicOrPartitionException** thuộc nhóm retriable exception của Kafka client. Điều này cho phép producer thử lại sau khi refresh metadata, vì lỗi có thể do topic vừa được tạo, metadata chưa đồng nhất hoặc trạng thái partition đang thay đổi.

Retry của producer có giới hạn bởi cấu hình gửi. Các thuộc tính liên quan gồm:

- **delivery.timeout.ms**: tổng thời gian tối đa để producer hoàn tất việc gửi, bao gồm thời gian chờ và retry.
- **request.timeout.ms**: thời gian chờ phản hồi cho một request.
- **retry.backoff.ms**: thời gian chờ giữa các lần retry.
- **retry.backoff.max.ms**: giới hạn backoff tối đa trên các phiên bản client hỗ trợ thuộc tính này.
- **enable.idempotence**: bảo vệ trước duplicate do retry ở tầng producer protocol khi được cấu hình đúng.

Không nên chỉ tăng **delivery.timeout.ms** khi topic không tồn tại. Thời gian dài hơn chỉ kéo dài việc chờ một nguyên nhân không thể tự phục hồi.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        retry.backoff.ms: 500
~~~

Các con số trên chỉ là ví dụ. Cần hiệu chỉnh theo SLA, độ trễ cluster và thời gian phục hồi dự kiến. **delivery.timeout.ms** phải tương thích với **request.timeout.ms** và cấu hình retry của Kafka client.

### 6.1 Retry ở Kafka client và retry ở application

Kafka producer đã có retry nội bộ. Nếu ứng dụng tiếp tục retry toàn bộ **send()** sau khi future hoàn tất lỗi, có thể tạo thêm một lớp retry khác.

Phải phân biệt:

- Retry nội bộ của producer cho một lần gửi.
- Ứng dụng gửi lại event sau khi nhận lỗi cuối cùng.
- Outbox publisher đọc lại cùng một bản ghi chưa được đánh dấu publish.
- Retry ở tầng HTTP/API gọi vào nghiệp vụ phát event.

Nếu nhiều tầng cùng retry, tổng số lần gửi có thể tăng theo cấp số nhân. Cần có một chính sách retry rõ ràng và giới hạn tổng thời gian.

Với lỗi topic/partition cố định như sai tên hoặc index không hợp lệ, application retry không giúp ích. Với timeout hoặc mất kết nối, kết quả có thể không rõ ràng; cần idempotence và event id để chống duplicate.

## 7. Spring Kafka: quan sát kết quả gửi

### 7.1 KafkaTemplate và future

**KafkaTemplate.send()** trả về **CompletableFuture<SendResult<K, V>>** trên các phiên bản Spring Kafka hiện đại. Có thể xử lý kết quả bất đồng bộ để ghi nhận lỗi và metadata khi thành công.

~~~java
public void publish(OrderCreated event) {
    String topic = "orders";

    kafkaTemplate.send(topic, event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed: topic={}, eventId={}",
                    topic,
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Kafka send succeeded: topic={}, partition={}, offset={}, eventId={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                event.eventId()
            );
        });
}
~~~

Khi future thất bại, log exception class và root cause. Nếu cần phân loại exception, có thể unwrap **CompletionException** hoặc cause chain để tìm lỗi Kafka gốc.

Không log payload nhạy cảm. Event id, topic, partition và correlation id thường đủ để truy vết.

### 7.2 Phân loại lỗi trước khi retry ở tầng ứng dụng

Ví dụ helper để nhận diện unknown topic/partition trong cause chain:

~~~java
static boolean isUnknownTopicOrPartition(Throwable error) {
    Throwable current = error;

    while (current != null) {
        if (current instanceof
                UnknownTopicOrPartitionException) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
~~~

Cách phân loại này chỉ là một phần của xử lý lỗi. Không nên chỉ kiểm tra exception ngoài cùng vì Spring hoặc Java future có thể bọc lỗi trong exception khác. Cũng cần tránh vòng cause bị lỗi bất thường trong các wrapper tự tạo; trong ứng dụng thực tế có thể dùng utility chung để unwrap exception.

Khi xác định lỗi unknown topic/partition:

- Gắn nhãn lỗi theo topic và môi trường.
- Kiểm tra provisioning và metadata.
- Không retry vô hạn nếu nguyên nhân là cấu hình cố định.
- Nếu topic đang trong quá trình tạo, cho phép một khoảng chờ có giới hạn hoặc retry theo chính sách release.
- Lưu event chưa gửi nếu nghiệp vụ yêu cầu không mất ý định phát event.

### 7.3 Provision topic bằng KafkaAdmin và NewTopic

Spring Kafka hỗ trợ khai báo topic bằng bean **NewTopic** và dùng **KafkaAdmin** để quản lý việc tạo topic khi ứng dụng khởi tạo context.

Ví dụ minh họa:

~~~java
@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

Cách này có thể hữu ích trong ứng dụng nhỏ hoặc môi trường thử nghiệm. Với production, topic thường nên được quản lý bởi IaC hoặc pipeline provisioning độc lập để quyền tạo topic, replication, retention, min ISR và partition count được kiểm soát.

Nếu dùng KafkaAdmin, cần bảo đảm:

- Ứng dụng có kết nối và quyền quản trị cần thiết.
- Tên topic và cấu hình phù hợp từng môi trường.
- Startup behavior khi broker tạm thời không khả dụng đã được quyết định.
- Có bước xác minh topic thực sự sẵn sàng trước khi producer nhận traffic.
- Không dùng bean topic như cách che giấu tên topic sai trong code.

Không phải mọi ứng dụng đều nên tự tạo topic. Chọn một chủ thể chịu trách nhiệm provisioning rõ ràng để tránh nhiều service cùng thay đổi cấu hình topic.

## 8. Kiểm tra topic và partition bằng AdminClient

Khi cần chẩn đoán bằng code, **AdminClient** có thể mô tả topic và trả về danh sách partition. Ví dụ:

~~~java
Properties properties = new Properties();
properties.put(
    AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-1:9092"
);

try (AdminClient admin = AdminClient.create(properties)) {
    TopicDescription description =
        admin.describeTopics(List.of("orders"))
            .allTopicNames()
            .get(10, TimeUnit.SECONDS)
            .get("orders");

    for (TopicPartitionInfo partition :
            description.partitions()) {
        System.out.printf(
            "topic=%s partition=%d leader=%s replicas=%d isr=%d%n",
            description.name(),
            partition.partition(),
            partition.leader(),
            partition.replicas().size(),
            partition.isr().size()
        );
    }
}
~~~

Đoạn code tập trung vào việc mô tả topic. Ứng dụng thực tế cần thêm security properties, timeout, xử lý exception và đóng AdminClient đúng vòng đời. API chi tiết có thể khác theo Kafka client version; dùng đúng version mà ứng dụng đang biên dịch.

Nếu topic không tồn tại hoặc principal không có quyền, future của AdminClient sẽ hoàn tất lỗi. Phân loại root cause để phân biệt unknown topic với authorization và timeout.

Không nên gọi **describeTopics()** cho từng record. Metadata/health check nên được thực hiện ở startup, readiness hoặc tác vụ giám sát có tần suất hợp lý; producer client đã có cơ chế metadata riêng.

## 9. Thiết kế provisioning để tránh lỗi ngay từ đầu

Cách tốt nhất để xử lý unknown topic/partition là tránh để producer gửi trước khi topic và partition sẵn sàng.

### 9.1 Quản lý topic như một resource triển khai

Mỗi topic nghiệp vụ nên có định nghĩa rõ:

- Tên topic và môi trường.
- Chủ sở hữu (owner) và producer/consumer liên quan.
- Partition count.
- Replication factor.
- **min.insync.replicas**.
- Retention và cleanup policy.
- Schema/serialization contract.
- ACL của producer và consumer.
- Quy trình tăng partition hoặc thay đổi cấu hình.

Lưu định nghĩa topic trong IaC hoặc repository quản trị để thay đổi có review, audit và rollback plan phù hợp.

### 9.2 Sắp xếp thứ tự release

Một thứ tự triển khai thường an toàn:

1. Provision topic và ACL.
2. Mô tả topic, xác nhận partition, leader, replica và ISR.
3. Xác nhận service account producer có quyền ghi.
4. Triển khai producer hoặc mở traffic.
5. Triển khai/kiểm tra consumer group.
6. Theo dõi send error, consumer lag và record đầu tiên.

Nếu producer và topic được phát hành độc lập, cần có dependency rõ trong pipeline hoặc readiness gate. Không dùng sleep cố định làm bảo đảm duy nhất; hãy kiểm tra trạng thái topic bằng AdminClient hoặc công cụ quản trị.

### 9.3 Kiểm tra cấu hình khi khởi động

Ứng dụng có thể xác thực tên topic bắt buộc trước khi nhận traffic. Việc kiểm tra cần cân nhắc tính sẵn sàng:

- Nếu topic là dependency bắt buộc, startup/readiness có thể không thành công khi topic không tồn tại.
- Nếu ứng dụng có thể lưu event vào outbox trong lúc Kafka chưa sẵn sàng, ứng dụng có thể khởi động nhưng publisher chưa gửi.
- Nếu topic là tùy chọn theo feature flag, chỉ kiểm tra khi feature được bật.

Readiness nên phản ánh khả năng phục vụ nghiệp vụ thực tế. Không nên làm liveness fail chỉ vì Kafka tạm thời không khả dụng, nếu việc restart liên tục không giúp phục hồi và còn làm tăng áp lực lên cluster.

## 10. Partitioning và thay đổi partition count

Lỗi unknown partition thường liên quan tới cách ứng dụng định tuyến record.

### 10.1 Partition index bắt đầu từ 0

Nếu topic có N partition, partition id hợp lệ là **0** đến **N-1**. Ví dụ:

| Partition count | Partition id hợp lệ |
|---:|---|
| 1 | 0 |
| 3 | 0, 1, 2 |
| 6 | 0, 1, 2, 3, 4, 5 |
| 12 | 0 đến 11 |

Không được nhầm partition count với partition id lớn nhất. Topic có 6 partition không có partition id 6.

### 10.2 Chọn partition bằng key

Khi gửi record có key và không chỉ định partition, partitioner mặc định thường dùng hash của key kết hợp số partition để chọn partition. Các record cùng key thường đi cùng partition, giúp duy trì thứ tự theo key trong điều kiện cấu hình ổn định.

Tuy nhiên, khi tăng partition count, kết quả hash modulo partition count có thể đổi. Các record cùng key trong tương lai có thể đi sang partition mới, trong khi record cũ vẫn ở partition trước. Vì thế, tăng partition count có thể ảnh hưởng đến thứ tự xử lý theo key xuyên suốt lịch sử dữ liệu.

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt cho một aggregate/key, cần đánh giá chiến lược partitioning và kế hoạch mở rộng trước khi tăng partition.

### 10.3 Không hard-code partition count

Nếu phải định tuyến theo partition id, lấy partition count từ metadata hoặc cấu hình được quản trị và xác thực trước khi gửi. Không sao chép số partition từ môi trường dev sang production.

Với yêu cầu sharding nghiệp vụ, nên có một lớp định tuyến được kiểm thử và có versioning. Tránh để từng producer service tự tính partition theo quy tắc khác nhau.

## 11. Tác động đến consumer và dữ liệu

Dù lỗi phát sinh ở producer, xử lý sai có thể ảnh hưởng consumer và tính toàn vẹn dữ liệu.

### 11.1 Record gửi nhầm topic

Nếu auto-create cho phép tạo topic do typo, producer có thể nhận ACK thành công nhưng consumer chính không nhận được event vì đang subscribe topic đúng. Đây là tình huống nguy hiểm hơn một lỗi gửi thất bại vì hệ thống có thể nghĩ event đã được phát.

Cần theo dõi topic đích trong metadata gửi thành công và cảnh báo các topic không thuộc danh mục quản trị. Tránh cho phép auto-create rộng trong production.

### 11.2 Record chưa được gửi thành công

Nếu producer future hoàn tất lỗi và ứng dụng bỏ qua event, ý định phát event có thể bị mất dù database đã commit. Với nghiệp vụ quan trọng, transactional outbox giúp lưu event trong cùng transaction database và publisher có thể gửi lại khi Kafka sẵn sàng.

Publisher cần đánh dấu outbox row đã gửi sau khi nhận kết quả thành công theo policy. Nếu process chết sau khi broker ghi nhưng trước khi đánh dấu outbox, publisher có thể gửi lại; consumer nên idempotent theo event id.

### 11.3 Kết quả không rõ ràng

Timeout không luôn chứng minh broker chưa ghi. Nếu producer không nhận được ACK, broker có thể đã append record. Khi application gửi lại sau đó, duplicate có thể xuất hiện nếu không có idempotence hoặc deduplication.

Với producer idempotent, retry nội bộ trong cùng session được bảo vệ theo protocol. Với retry ở tầng application, process restart hoặc publisher mới, event id ổn định và consumer idempotency vẫn quan trọng.

## 12. Quan sát và cảnh báo

Nên kết hợp metrics producer, log ứng dụng và trạng thái Kafka.

| Phạm vi | Tín hiệu cần theo dõi | Ý nghĩa |
|---|---|---|
| Producer | Record send error rate | Tỷ lệ record gửi thất bại |
| Producer | Retry rate, request latency | Client đang phải retry hoặc chờ lâu |
| Producer | Record queue time, buffer availability | Producer có bị nghẽn khi broker/metadata chậm |
| Application | Exception theo class và topic | Phân biệt unknown topic với authorization/timeout |
| Application | Topic name sau khi resolve | Phát hiện cấu hình sai |
| Kafka metadata | Topic/partition existence | Xác nhận resource đã được provision |
| Partition | Leader, replicas và ISR | Phân biệt partition không tồn tại với partition chưa có leader |
| Admin/provisioning | Create/describe topic result | Phát hiện race hoặc lỗi pipeline |
| Outbox | Backlog và tuổi record lâu nhất | Đo event đang chờ gửi |
| Business | Event id chưa được consumer xác nhận | Phát hiện khoảng trống giữa publish và xử lý |

Các cảnh báo hữu ích:

- UnknownTopicOrPartitionException vượt ngưỡng trong một khoảng thời gian.
- Producer send failure tăng đột ngột sau deployment.
- Topic bắt buộc không tồn tại trong một môi trường.
- Partition không có leader hoặc ISR suy giảm.
- Outbox backlog tăng hoặc record cũ nhất vượt SLA.
- Xuất hiện topic ngoài danh mục quản trị.

Tránh tạo alert riêng cho từng lần retry metadata thoáng qua. Nên cảnh báo khi lỗi kéo dài, ảnh hưởng tỷ lệ gửi hoặc làm event age vượt ngưỡng nghiệp vụ.

## 13. Runbook xử lý sự cố

Khi producer phát sinh unknown topic hoặc partition, thực hiện theo thứ tự:

1. **Khoanh vùng:** xác định service, môi trường, cluster, topic, partition, client id và thời điểm bắt đầu.
2. **Đọc root cause:** xác nhận lỗi thực sự là **UnknownTopicOrPartitionException**, không phải authorization, invalid topic, leader unavailable hoặc timeout.
3. **Xác minh cluster:** kiểm tra bootstrap endpoint và môi trường runtime.
4. **Xác minh topic:** dùng đúng principal để list/describe topic.
5. **Xác minh partition:** kiểm tra partition id hợp lệ, leader, replicas và ISR.
6. **Đối chiếu thay đổi:** kiểm tra release, topic provisioning, ACL, broker restart, controller và network.
7. **Khắc phục nguyên nhân:** sửa tên, tạo topic theo quy trình, sửa partition index hoặc phục hồi broker/metadata.
8. **Xử lý event chưa gửi:** xác nhận retry nội bộ đã kết thúc; xử lý outbox hoặc hàng đợi pending theo event id.
9. **Xác minh phục hồi:** producer nhận ACK, metadata có topic/partition, send error giảm và consumer nhận được event.
10. **Ghi nhận hậu kiểm:** lưu nguyên nhân, thời gian ảnh hưởng, số event pending/replayed và thay đổi phòng ngừa.

Không xóa hoặc tạo lại topic, không giảm replication, không tăng partition count và không bật auto-create chỉ để làm biến mất exception. Mỗi thay đổi cần gắn với nguyên nhân đã xác minh và tác động dữ liệu đã được đánh giá.

## 14. Kiểm thử lỗi unknown topic/partition

Nên kiểm thử trong môi trường staging có cấu hình tương đương production:

- Gửi tới một topic chưa tồn tại khi auto-create bị tắt; xác nhận producer nhận lỗi cuối cùng trong giới hạn timeout.
- Tạo topic sau khi producer đã bắt đầu gửi; xác nhận metadata refresh và retry có thể phục hồi khi topic sẵn sàng.
- Gửi tới partition index ngoài phạm vi; xác nhận lỗi được phân loại và không retry vô hạn.
- Trỏ producer tới cluster không có topic; xác nhận kiểm tra startup/runbook phát hiện sai môi trường.
- Dùng principal thiếu ACL; xác nhận lỗi authorization được phân biệt với unknown topic.
- Làm broker/leader unavailable trong môi trường thử nghiệm; xác nhận lỗi leader/metadata được xử lý theo runbook.
- Kiểm tra outbox khi Kafka không khả dụng; xác nhận event được giữ lại và publish sau khi phục hồi.
- Kiểm tra topic typo trong môi trường có auto-create; xác nhận cơ chế kiểm soát ngăn tạo topic ngoài danh mục.

Mỗi bài kiểm thử nên có topic thử nghiệm riêng, event id riêng, tiêu chí dừng và cách dọn dữ liệu. Không thử xóa topic production hoặc gửi record vào topic nghiệp vụ để mô phỏng lỗi.

## 15. Checklist vận hành

**Cấu hình và provisioning**

- [ ] Producer kết nối đúng cluster theo môi trường.
- [ ] Tên topic được quản lý tập trung và phân biệt rõ chữ hoa/chữ thường.
- [ ] Topic bắt buộc được provision trước khi mở traffic producer.
- [ ] Partition count, replication factor, retention và min ISR được quản trị.
- [ ] Auto-create policy được quyết định rõ; production không phụ thuộc vào topic mặc định ngoài kiểm soát.
- [ ] Producer và công cụ chẩn đoán dùng đúng principal/security configuration.

**Producer và partitioning**

- [ ] Không hard-code partition id nếu không có yêu cầu nghiệp vụ.
- [ ] Partition index được kiểm tra trong khoảng **0..N-1**.
- [ ] Partition count thay đổi có đánh giá ảnh hưởng tới key mapping và thứ tự.
- [ ] Kafka client retry có giới hạn theo delivery timeout.
- [ ] Application retry không nhân vô hạn với retry nội bộ của producer.
- [ ] Event quan trọng có event id và cơ chế lưu bền vững/outbox.

**Quan sát và phục hồi**

- [ ] Log có topic, partition, client id, event id và root cause.
- [ ] Có dashboard send error, retry, request latency và metadata/partition health.
- [ ] Có cảnh báo topic bắt buộc không tồn tại hoặc partition không có leader.
- [ ] Có runbook phân biệt unknown topic, authorization, leader và timeout.
- [ ] Có quy trình xử lý outbox/replay và chống duplicate.
- [ ] Đã diễn tập topic chưa tạo, partition index sai và metadata cập nhật chậm trong môi trường phù hợp.

Unknown topic hoặc partition là lỗi định tuyến và metadata cần được xử lý dựa trên trạng thái thực tế của cluster. Khi topic được provision có kiểm soát, partition index hợp lệ, producer dùng đúng cluster và retry có giới hạn, lỗi tạm thời có thể tự phục hồi còn lỗi cấu hình sẽ được phát hiện nhanh. Với event quan trọng, cần kết hợp theo dõi ACK, event id và outbox để bảo đảm producer không âm thầm làm mất ý định phát dữ liệu khi Kafka chưa sẵn sàng.

