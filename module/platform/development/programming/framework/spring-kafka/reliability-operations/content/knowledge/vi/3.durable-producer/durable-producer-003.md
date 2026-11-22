# acks và mức xác nhận ghi

Trong Kafka, producer gửi record đến broker leader của partition và nhận phản hồi về kết quả ghi. Thuộc tính **acks** quyết định producer cần broker xác nhận ở mức nào trước khi xem một lần gửi là thành công. Đây là một lựa chọn cốt lõi của chương **Producer bền vững** vì nó ảnh hưởng trực tiếp đến khả năng chịu lỗi broker, nguy cơ mất record và độ trễ ghi.

Chọn mức ACK không chỉ là chọn giữa nhanh và an toàn. Cần hiểu ACK được gửi ở thời điểm nào, replica nào phải tham gia, điều kiện nào khiến broker từ chối ghi và ứng dụng sẽ làm gì khi không nhận được phản hồi. Một cấu hình tốt phải phối hợp **acks**, replication factor, **min.insync.replicas**, ISR, idempotent producer, timeout và cách xử lý lỗi trong ứng dụng.

## 1. ACK là gì trong luồng ghi Kafka?

Mỗi topic được chia thành các partition. Mỗi partition có một leader và có thể có các follower replica trên những broker khác. Producer gửi record đến leader của partition đích. Leader ghi record vào log và follower lấy dữ liệu từ leader để duy trì bản sao.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Partition leader
    participant F1 as Follower 1
    participant F2 as Follower 2
    P->>L: Produce record
    L->>L: Append vào log
    F1->>L: Fetch dữ liệu
    L-->>F1: Record mới
    F2->>L: Fetch dữ liệu
    L-->>F2: Record mới
    L-->>P: ACK theo cấu hình acks
~~~

Sơ đồ minh họa replication; trong thực tế follower chủ động fetch dữ liệu từ leader. Producer không gửi một bản ghi riêng đến từng replica. Producer gửi request đến leader, còn Kafka quản lý việc nhân bản.

ACK là phản hồi của broker cho request ghi. Từ góc nhìn producer, ACK thành công có nghĩa request đã đáp ứng mức xác nhận được cấu hình. Nó không có nghĩa mọi bản sao được cấu hình đều đã nhận dữ liệu, cũng không đồng nghĩa mọi bản sao đã được flush vật lý xuống thiết bị lưu trữ.

Các bước cần phân biệt:

1. Producer serialize record, xác định partition và gửi request.
2. Leader nhận request và append record vào log.
3. Các follower trong ISR sao chép dữ liệu từ leader.
4. Leader trả phản hồi theo chính sách ACK.
5. Producer nhận phản hồi và hoàn tất future/callback tương ứng.

Nếu kết nối bị ngắt sau khi leader ghi record nhưng trước khi producer nhận ACK, producer có thể không biết request đã được ghi hay chưa. Đây là tình huống **kết quả không rõ ràng** (ambiguous outcome). Retry có thể tạo record trùng nếu không có idempotence hoặc cơ chế deduplication phù hợp.

## 2. Ba mức acks

Kafka producer hỗ trợ ba mức xác nhận chính: **acks=0**, **acks=1** và **acks=all**. Giá trị **acks=-1** là alias của **acks=all**.

### 2.1 acks=0 — không chờ xác nhận

Với **acks=0**, producer gửi request nhưng không chờ broker trả ACK. Producer có thể tiếp tục gửi nhanh vì không phải đợi phản hồi ghi.

Đặc điểm:

- Producer không có xác nhận rằng broker đã nhận hoặc append record.
- Nếu request bị mất trên đường truyền, broker không khả dụng hoặc broker từ chối ghi, producer không có ACK để phát hiện chính xác kết quả.
- Retry ở phía producer không thể dựa trên phản hồi lỗi của broker vì producer không chờ phản hồi.
- Latency quan sát ở producer thấp hơn, nhưng độ tin cậy của kết quả ghi thấp nhất trong ba mức.

**acks=0** chỉ phù hợp với dữ liệu có thể mất, có thể tái tạo hoặc không quan trọng đối với nghiệp vụ, chẳng hạn một số luồng telemetry có thể chấp nhận mất mẫu. Không nên dùng cho đơn hàng, thanh toán, trạng thái giao dịch, lệnh nghiệp vụ hoặc event cần được lưu bền vững.

### 2.2 acks=1 — leader xác nhận

Với **acks=1**, producer nhận ACK sau khi leader đã append record vào log cục bộ. Leader không cần chờ follower trong ISR xác nhận record đó trước khi phản hồi.

Đặc điểm:

- Producer biết leader đã nhận và append record.
- Độ trễ thường thấp hơn **acks=all**, đặc biệt khi follower có độ trễ replication.
- Nếu leader hỏng sau khi ACK nhưng trước khi record được follower sao chép, record có thể không còn trên replica đủ điều kiện kế nhiệm.
- Mức xác nhận này không bảo vệ trước mọi tình huống leader mất đột ngột.

Ví dụ, partition có leader A và follower B, C. Producer gửi record đến A. A append record rồi trả ACK ngay. Trước khi B và C sao chép record, A mất nguồn. Nếu B được bầu làm leader mới và chưa có record đó, record đã được producer xem là gửi thành công có thể biến mất khỏi log được phục vụ.

Vì vậy, **acks=1** phù hợp hơn với dữ liệu có thể chấp nhận một mức rủi ro mất record nhỏ để đổi lấy độ trễ thấp hơn. Không nên mặc định rằng ACK từ leader đồng nghĩa record đã có trên nhiều broker.

### 2.3 acks=all — chờ ISR xác nhận

Với **acks=all**, leader chờ các replica hiện thuộc tập ISR (in-sync replicas) xác nhận đã theo kịp record trước khi trả ACK. Đây là mức thường được chọn cho dữ liệu nghiệp vụ quan trọng.

Đặc điểm:

- Producer nhận ACK sau khi record được append và các replica thuộc ISR đáp ứng điều kiện xác nhận.
- Mức bảo vệ tốt hơn khi leader gặp sự cố sau khi ghi.
- Độ trễ có thể tăng do phải chờ replication.
- Nếu số ISR thấp hơn **min.insync.replicas**, broker từ chối request ghi thay vì chấp nhận ở mức replication không đủ theo policy.

Điểm quan trọng: **acks=all không có nghĩa tất cả replica được khai báo bởi replication factor đều phải xác nhận.** Nó chờ các replica đang nằm trong ISR tại thời điểm ghi. Replica đã bị loại khỏi ISR vì lag hoặc mất kết nối không nằm trong tập phải ACK cho request đó.

Điều này có nghĩa mức bảo vệ thực tế phụ thuộc cả vào số lượng ISR còn hoạt động. Một topic có replication factor 3 nhưng chỉ còn 1 ISR không còn mức dự phòng như khi có đủ 3 ISR. Cần cấu hình **min.insync.replicas** để xác định ngưỡng tối thiểu mà broker chấp nhận ghi.

## 3. So sánh acks=0, acks=1 và acks=all

| Thuộc tính | acks=0 | acks=1 | acks=all |
|---|---|---|---|
| Chờ broker ACK | Không | Có | Có |
| Điều kiện phản hồi thành công | Không có ACK từ broker | Leader append record | Các replica hiện trong ISR đáp ứng xác nhận |
| Phụ thuộc follower trước khi ACK | Không | Không | Có |
| Khả năng phát hiện lỗi ghi qua phản hồi broker | Rất hạn chế | Có | Có |
| Rủi ro khi leader hỏng ngay sau ACK | Không có xác nhận để đánh giá | Có thể mất record chưa replicate | Thấp hơn khi ISR đủ và cấu hình đúng |
| Độ trễ ghi | Thường thấp nhất | Thường thấp | Có thể cao hơn |
| Phù hợp với | Dữ liệu có thể mất | Dữ liệu ít nhạy với mất record | Dữ liệu cần độ bền cao |

Bảng này mô tả xu hướng chung. Latency thực tế phụ thuộc tải, kích thước batch, network, broker disk, số ISR và vị trí các broker. Không thể suy ra một con số latency cố định chỉ từ giá trị ACK.

## 4. ISR, replication factor và min.insync.replicas

Để hiểu đúng **acks=all**, cần phân biệt ba khái niệm.

### 4.1 Replication factor

Replication factor (RF) là số replica được cấu hình cho mỗi partition, tính cả leader. Ví dụ RF=3 nghĩa là một partition có một leader và hai follower replica.

RF tạo khả năng dự phòng khi một broker hỏng. Tuy nhiên, có ba replica không có nghĩa cả ba luôn theo kịp nhau. Follower có thể bị chậm hoặc mất kết nối.

Replica của cùng partition nên được phân bố trên các broker và failure domain độc lập. Nếu cả ba replica cùng nằm trên một node vật lý hoặc một AZ, sự cố của node/AZ đó có thể làm mất toàn bộ bản sao.

### 4.2 ISR — in-sync replicas

ISR là tập replica đang được xem là theo kịp leader theo cơ chế replication và ngưỡng cấu hình của Kafka. ISR bao gồm leader và các follower đang đủ điều kiện.

Ví dụ:

- RF=3: partition có leader A, follower B và follower C.
- Ban đầu ISR = {A, B, C}.
- B bị chậm quá ngưỡng hoặc mất kết nối, Kafka loại B khỏi ISR.
- ISR lúc này có thể là {A, C}.
- Nếu C cũng rời ISR, ISR chỉ còn {A}.

Khi số ISR giảm, khả năng chịu lỗi của partition giảm. Một partition chỉ còn leader trong ISR có thể vẫn phục vụ một số request nếu policy cho phép, nhưng không còn bản sao theo kịp để kế nhiệm an toàn khi leader hỏng.

ISR có thể thay đổi theo thời gian. Vì vậy, đánh giá durability phải dựa trên trạng thái ISR khi ghi, không chỉ nhìn replication factor trong cấu hình topic.

### 4.3 min.insync.replicas

**min.insync.replicas** đặt số replica tối thiểu phải có trong ISR để broker chấp nhận ghi với **acks=all**.

Giả sử:

- Replication factor = 3.
- min.insync.replicas = 2.
- Producer dùng acks=all.

Các tình huống:

| ISR hiện tại | Broker xử lý ghi với acks=all |
|---|---|
| 3 replica | Cho phép ghi; chờ toàn bộ 3 ISR xác nhận |
| 2 replica | Cho phép ghi; chờ cả 2 ISR xác nhận |
| 1 replica | Từ chối ghi vì thấp hơn min ISR |

Cấu hình này tạo ra lựa chọn rõ ràng: khi cluster suy giảm dưới ngưỡng, Kafka từ chối ghi để bảo vệ mức durability đã cam kết. Ứng dụng phải chấp nhận ghi tạm thời thất bại, retry có giới hạn và cảnh báo vận hành.

Nếu không đặt min ISR phù hợp, **acks=all** vẫn có thể chấp nhận ghi khi ISR chỉ còn một replica. Khi đó, tên gọi “all” không đảm bảo có nhiều bản sao; nó chỉ có nghĩa là tất cả replica hiện còn trong ISR đã xác nhận.

### 4.4 Chọn RF và min ISR

Một cấu hình thường gặp cho dữ liệu quan trọng là:

- RF=3.
- min.insync.replicas=2.
- Producer dùng acks=all.

Cấu hình này cho phép ghi khi còn ít nhất hai ISR, và request được xác nhận bởi mọi ISR hiện tại. Khi một replica mất khả năng theo kịp, partition vẫn có thể tiếp tục ghi với hai ISR. Nếu chỉ còn một ISR, broker từ chối ghi cho đến khi replication phục hồi.

Đây không phải cấu hình tối ưu cho mọi hệ thống. Chọn RF và min ISR cần xét:

- Mức mất dữ liệu tối đa mà nghiệp vụ chấp nhận.
- Số broker và failure domain vật lý.
- Khả năng chịu tải khi một broker/AZ mất.
- Độ trễ replication giữa broker.
- Yêu cầu availability: hệ thống có chấp nhận tạm dừng ghi để giữ durability hay không.
- Dung lượng lưu trữ và chi phí replication.

RF=3 chỉ có ý nghĩa khi ba replica thực sự được phân bố độc lập. Cần kiểm tra rack awareness hoặc cơ chế phân bố tương ứng trong môi trường triển khai.

## 5. Điều gì xảy ra khi broker hoặc replica gặp lỗi?

Một số tình huống điển hình giúp thấy rõ quan hệ giữa ACK và trạng thái cluster.

### 5.1 Mất một follower

Giả sử RF=3, ISR ban đầu có A, B, C. Broker B mất kết nối và bị loại khỏi ISR, tập ISR còn A và C.

Với min ISR=2 và acks=all:

- Broker vẫn có thể chấp nhận ghi.
- Leader A chờ A và C đáp ứng replication.
- Mức dự phòng giảm từ ba replica xuống hai.
- Cần cảnh báo vì partition đang thiếu một replica so với replication factor.

Khi B phục hồi và bắt kịp leader, B có thể được thêm lại vào ISR. Không nên chỉ dựa vào trạng thái broker “online”; phải xác nhận partition replica đã theo kịp và ISR đã phục hồi.

### 5.2 Mất leader

Nếu A là leader và hỏng, Kafka cần bầu leader mới từ replica đủ điều kiện. Nếu B hoặc C còn trong ISR, một replica đó có thể trở thành leader.

Với acks=all và min ISR được thiết kế phù hợp, các record đã ACK có xác suất được bảo vệ tốt hơn vì đã được các ISR xác nhận. Tuy nhiên, khả năng tiếp tục ghi còn phụ thuộc số ISR còn lại sau khi bầu leader và min ISR.

Nếu không có replica đủ điều kiện, partition có thể không có leader và không phục vụ ghi cho đến khi phục hồi. Đây là đánh đổi giữa tính nhất quán/durability và availability.

### 5.3 ISR giảm dưới min ISR

Giả sử RF=3, min ISR=2, nhưng hiện tại ISR chỉ còn một replica. Khi producer gửi với acks=all, broker từ chối ghi vì không đáp ứng ngưỡng tối thiểu.

Đây là hành vi bảo vệ dữ liệu. Không nên lập tức hạ min ISR hoặc đổi sang acks=1 chỉ để loại bỏ lỗi producer. Làm vậy có thể biến một cảnh báo suy giảm replication thành nguy cơ mất dữ liệu thực tế.

Trình tự xử lý nên là:

1. Xác định partition và broker replica đang thiếu.
2. Kiểm tra broker, disk, network và tình trạng follower fetch.
3. Khôi phục replica để ISR đạt ngưỡng.
4. Theo dõi lỗi producer và replication metrics cho đến khi ổn định.
5. Chỉ thay đổi policy sau khi đã đánh giá yêu cầu durability và có quyết định vận hành rõ ràng.

### 5.4 Leader trả ACK rồi gặp sự cố

Với acks=1, leader có thể ACK trước khi follower sao chép record. Nếu leader hỏng ngay sau đó, record có thể không có trên replica được bầu làm leader mới.

Với acks=all, leader chỉ ACK sau khi các replica trong ISR xác nhận. Điều này giảm rủi ro record đã ACK bị mất khi một broker gặp lỗi. Mức bảo vệ còn phụ thuộc ISR, cấu hình bầu leader và việc các replica có thực sự nằm trong failure domain độc lập hay không.

### 5.5 Mất nhiều broker hoặc mất một AZ

Nếu nhiều replica cùng partition mất đồng thời, ISR có thể xuống dưới min ISR hoặc không còn replica đủ điều kiện làm leader. Producer sẽ nhận lỗi ghi hoặc partition không khả dụng.

Nếu các replica được phân bố qua nhiều AZ và một AZ mất, các AZ còn lại có thể tiếp tục phục vụ nếu còn đủ ISR và capacity. Nếu các replica cùng nằm trong AZ bị mất, RF=3 không giúp bảo vệ trước sự cố đó.

## 6. ACK không đồng nghĩa với fsync hay bảo vệ mọi loại lỗi

Cần hiểu giới hạn của ACK để không diễn giải quá mức.

**acks=all** xác nhận replication theo giao thức Kafka. Nó không có nghĩa broker thực hiện một thao tác fsync bắt buộc xuống thiết bị lưu trữ cho từng record trước khi phản hồi. Kafka tận dụng page cache và cơ chế flush của hệ điều hành để tối ưu hiệu năng. Vì vậy, ACK không nên được hiểu là “mọi bản sao đã được ghi vật lý xuống đĩa theo cách chống mọi sự cố nguồn điện”.

Durability còn phụ thuộc:

- Số ISR và chất lượng replication.
- Sự độc lập của broker và failure domain.
- Cấu hình leader election, đặc biệt là có cho phép bầu replica ngoài ISR hay không.
- Tình trạng filesystem, disk controller và hạ tầng lưu trữ.
- Cấu hình retention và các thao tác quản trị topic.
- Khả năng khôi phục cluster và backup/DR.

### 6.1 Unclean leader election

Khi mọi replica trong ISR không khả dụng, Kafka có thể có lựa chọn về việc cho phép một replica ngoài ISR trở thành leader hay không. Cho phép unclean leader election có thể giúp partition sớm có leader trở lại, nhưng replica ngoài ISR có thể thiếu các record đã được leader cũ ACK.

Tắt unclean leader election giúp tránh bầu một replica không đồng bộ làm leader, qua đó ưu tiên bảo toàn dữ liệu đã replicate. Đổi lại, partition có thể không khả dụng cho đến khi một replica đủ điều kiện phục hồi.

Đây là một quyết định durability/availability ở cấp cluster. Cần hiểu phiên bản Kafka, cấu hình cluster và runbook trước khi thay đổi.

## 7. Kết hợp acks với idempotent producer và retry

ACK quyết định mức xác nhận của broker. Idempotence giải quyết một vấn đề khác: gửi lại request khi kết quả lần gửi trước không rõ ràng.

Ví dụ:

1. Producer gửi record đến leader.
2. Broker ghi record và gửi ACK.
3. Mạng bị ngắt trước khi ACK đến producer.
4. Producer thấy timeout và thử gửi lại.
5. Nếu không có idempotence, lần gửi lại có thể tạo thêm một record giống record trước.

Idempotent producer sử dụng producer identity và sequence number để broker nhận biết retry của cùng một producer session và loại bỏ duplicate do retry ở tầng protocol.

Để dùng idempotence, cần cấu hình tương thích. Trong Kafka client hiện đại, idempotence yêu cầu **acks=all**; cấu hình retry và số request in-flight cũng phải thỏa điều kiện của client version. Nên bật rõ ràng và kiểm tra startup/config log thay vì dựa vào giá trị mặc định thay đổi theo phiên bản.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

**delivery.timeout.ms** giới hạn tổng thời gian producer cố gắng hoàn tất việc gửi, bao gồm chờ request và retry. Hết thời gian này, ứng dụng nhận lỗi gửi. Giá trị cần phù hợp với SLA, request timeout, broker latency và thời gian phục hồi dự kiến.

Idempotent producer không thay thế idempotency nghiệp vụ. Nếu ứng dụng khởi động lại rồi tạo một lần gửi mới cho cùng một lệnh nghiệp vụ, Kafka có thể xem đó là record mới. Nên có event id hoặc business key ổn định để consumer có thể deduplicate khi cần.

### 7.1 Retry không phải cách sửa lỗi durability

Retry giúp vượt qua lỗi tạm thời như leader election, network interruption hoặc broker restart. Nhưng retry không thể khắc phục một policy replication sai hoặc một cluster mất nhiều replica kéo dài.

Cần tránh:

- Retry vô hạn khiến producer buffer đầy.
- Timeout quá dài làm request giữ tài nguyên và che giấu sự cố.
- Nhiều tầng retry nhân số lần gọi: application retry, Kafka producer retry và retry ở downstream.
- Retry đồng loạt không có backoff/jitter làm cluster quá tải khi vừa phục hồi.

Khi producer nhận lỗi do ISR dưới min ISR, retry chỉ thành công sau khi replication phục hồi hoặc policy thay đổi. Ứng dụng nên có backoff, timeout tổng thể và cảnh báo theo loại lỗi.

## 8. Cấu hình acks trong Spring Kafka

Spring Boot cung cấp property để cấu hình producer ACK. Ví dụ dưới đây dùng cấu hình bền vững phổ biến cho dữ liệu quan trọng:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Ý nghĩa:

- **bootstrap-servers**: địa chỉ broker dùng để khám phá metadata cluster.
- **acks: all**: producer yêu cầu mức xác nhận từ ISR.
- **enable.idempotence: true**: bật idempotent producer để chống duplicate do retry trong cùng producer session.
- **delivery.timeout.ms**: giới hạn tổng thời gian gửi.
- **request.timeout.ms**: thời gian chờ phản hồi cho một request.

Các giá trị timeout chỉ là ví dụ. Không nên sao chép nguyên xi cho mọi hệ thống. Hãy đo latency, xác định SLA, kích thước record và thời gian broker có thể phục hồi rồi hiệu chỉnh.

### 8.1 Cấu hình topic và broker

**min.insync.replicas** là cấu hình ở topic hoặc broker, không phải property của producer. Ví dụ cấu hình topic:

~~~properties
replication.factor=3
min.insync.replicas=2
~~~

Trong triển khai thật, replication factor thường được chỉ định khi tạo topic hoặc qua công cụ quản trị. **min.insync.replicas** có thể được đặt ở cấp topic hoặc broker theo cách quản trị của cluster. Cần xác minh cấu hình hiệu lực của topic, vì giá trị mặc định cấp broker có thể khác với override ở topic.

Producer không thể tự nâng min ISR bằng cách đặt property trong ứng dụng. Việc thay đổi policy replication cần được quản trị ở phía Kafka.

### 8.2 ProducerFactory và KafkaTemplate

Nếu cấu hình bằng Java thay vì Spring Boot YAML, các producer properties có thể được truyền vào ProducerFactory:

~~~java
@Bean
ProducerFactory<String, OrderCreated> producerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
              StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
              JsonSerializer.class);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);

    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

Ví dụ tập trung vào các thuộc tính liên quan đến ACK và durability. Ứng dụng thực tế cần cấu hình serializer, security, schema, transaction và quan sát lỗi phù hợp với môi trường.

### 8.3 Xử lý kết quả gửi trong ứng dụng

Với KafkaTemplate, ứng dụng có thể quan sát kết quả gửi bất đồng bộ. Không nên bỏ qua future khi nghiệp vụ cần biết record đã được broker xác nhận hay chưa.

Ví dụ:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka publish failed for orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Published orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

Callback thành công có nghĩa producer nhận phản hồi thành công theo ACK policy đã cấu hình. Callback lỗi cần được ghi nhận và xử lý theo nghiệp vụ. Nếu gửi thất bại, ứng dụng cần quyết định lưu lại để gửi sau, trả lỗi cho caller, hoặc dùng transactional outbox.

Không nên chỉ log lỗi rồi bỏ record nếu đây là event bắt buộc phải phát. Với nghiệp vụ quan trọng, transactional outbox thường giúp không mất ý định phát event khi database đã commit.

## 9. Đọc lỗi producer liên quan đến ACK

Một số lỗi thường gặp:

| Lỗi hoặc triệu chứng | Ý nghĩa có thể có | Hướng điều tra |
|---|---|---|
| NotEnoughReplicasException | ISR thấp hơn min ISR khi broker xử lý request | Kiểm tra ISR, broker replica, network và min ISR hiệu lực |
| NotEnoughReplicasAfterAppendException | Record đã được append nhưng không đủ replica đáp ứng điều kiện sau đó | Kiểm tra thay đổi ISR trong lúc ghi và trạng thái partition |
| TimeoutException | Producer không hoàn tất request trong giới hạn thời gian | Kiểm tra broker latency, network, request timeout, delivery timeout và retry |
| NetworkException | Kết nối broker bị gián đoạn | Kiểm tra DNS, route, TLS, firewall và broker availability |
| NotLeaderOrFollowerException | Request đến broker không còn là leader hoặc không phù hợp vai trò | Kiểm tra metadata refresh, leader election và broker state |
| RecordTooLargeException | Record vượt giới hạn kích thước | Kiểm tra producer max request size và broker/topic limits |

Tên exception có thể khác theo ngữ cảnh hoặc phiên bản client, và một số lỗi được bọc trong exception tổng quát. Cần đọc root cause, topic, partition và metadata request thay vì chỉ dựa vào thông báo ngoài cùng.

**NotEnoughReplicas** không nhất thiết có nghĩa broker đã hỏng hoàn toàn. Có thể broker còn hoạt động nhưng follower lag hoặc mất kết nối khiến ISR giảm. Đây là lý do phải quan sát ISR và broker health cùng lúc.

## 10. Ma trận lựa chọn ACK theo nghiệp vụ

| Loại dữ liệu | Mức ACK thường cân nhắc | Lý do và điều kiện |
|---|---|---|
| Metrics/telemetry có thể mất mẫu | acks=0 hoặc acks=1 | Chỉ khi hệ thống chấp nhận mất dữ liệu và có thể tổng hợp lại |
| Log ứng dụng không trọng yếu | acks=1 hoặc acks=all | Phụ thuộc yêu cầu lưu giữ và khả năng chấp nhận mất log |
| Event nghiệp vụ thông thường | acks=all | Nên đi cùng RF, min ISR và idempotence phù hợp |
| Đơn hàng, thanh toán, trạng thái tài khoản | acks=all | Cần durability cao, idempotency nghiệp vụ và quy trình outbox/transaction phù hợp |
| Event có thể tái tạo từ nguồn khác | acks=1 hoặc acks=all | Quyết định dựa trên chi phí tái tạo và hậu quả khi mất |

Không có một mức ACK đúng cho tất cả topic. Một cluster có thể phục vụ nhiều nhóm dữ liệu với yêu cầu khác nhau, nhưng policy cần được quản trị rõ theo topic và nghiệp vụ. Tránh để cấu hình mặc định vô tình quyết định durability cho dữ liệu quan trọng.

## 11. Độ trễ, throughput và batch

Mức ACK ảnh hưởng đến latency của producer. Với acks=all, producer có thể phải chờ follower chậm nhất trong ISR. Khi một follower có network latency hoặc disk I/O cao, thời gian phản hồi có thể tăng.

Tuy nhiên, không nên đánh đổi durability chỉ để giảm vài millisecond nếu dữ liệu không thể tái tạo. Trước khi thay đổi ACK, cần kiểm tra:

- Batch size và linger time.
- Compression.
- Số partition và phân bố key.
- Broker request latency.
- Network round trip giữa các broker.
- Follower fetch lag và ISR churn.
- Disk I/O và request handler saturation.
- Số request in-flight và khả năng batch của producer.

Batching và compression có thể cải thiện throughput mà vẫn giữ acks=all. Tối ưu nên bắt đầu từ bottleneck đo được. Nếu độ trễ tăng vì follower lag, cần tìm nguyên nhân ở broker/network/disk thay vì tự động hạ ACK.

## 12. Quan sát durability và cảnh báo

Producer metrics chỉ phản ánh một phần. Cần kết hợp metrics của producer, broker và partition.

**Phía producer:**

- Record send rate và record error rate.
- Request latency và request size.
- Retry rate và số request bị retry.
- Record queue time và buffer available bytes.
- Số lần timeout hoặc lỗi gửi.
- Tỷ lệ gửi thành công theo topic.

**Phía Kafka:**

- Under-replicated partitions.
- Under-min-ISR partitions.
- Offline partitions.
- ISR shrink/expand rate.
- Leader election rate và partition leader distribution.
- Produce request latency, request handler saturation.
- Follower fetch lag, disk usage và network throughput.

**Phía ứng dụng:**

- Số event cần phát nhưng chưa được publish.
- Outbox backlog và tuổi bản ghi outbox lâu nhất.
- Số lần retry gửi event.
- Số event thất bại cuối cùng và số event được replay.
- Correlation/event id để đối chiếu database với Kafka.

Nên đặt cảnh báo cho trạng thái **under-min-ISR** và **under-replicated partitions**. Hai tín hiệu này có ý nghĩa khác nhau: partition có thể thiếu replica nhưng vẫn đủ min ISR để ghi; hoặc có thể xuống dưới min ISR và producer bị từ chối ghi. Cần theo dõi cả hai.

Một producer vẫn gửi được record không chứng minh toàn bộ topic đang có đủ replication. Ngược lại, producer nhận lỗi do min ISR có thể là hệ thống đang bảo vệ durability đúng như thiết kế. Cần nhìn lỗi producer cùng trạng thái ISR để quyết định hành động.

## 13. Quy trình xử lý khi producer nhận lỗi ACK

Khi có lỗi gửi liên quan đến replica hoặc ACK, thực hiện theo trình tự:

1. Xác định topic, partition, producer client, thời điểm lỗi và loại exception gốc.
2. Kiểm tra producer config thực tế: acks, idempotence, retries, request timeout và delivery timeout.
3. Kiểm tra leader của partition và danh sách ISR hiện tại.
4. Kiểm tra broker nào mất kết nối, follower nào lag và liệu có broker đang restart hoặc disk/network quá tải.
5. Xác minh min.insync.replicas hiệu lực ở topic/broker và replication factor.
6. Khôi phục broker hoặc network để follower bắt kịp, theo dõi ISR tăng trở lại.
7. Xác nhận producer retry thành công hoặc ứng dụng đã lưu event để gửi lại.
8. Đối chiếu event id và offset để xác định record đã được ghi trước timeout hay chưa.
9. Sau phục hồi, xác minh under-replicated và under-min-ISR partitions đã về ngưỡng bình thường.

Không nên xóa topic, giảm replication factor hoặc hạ min ISR như phản xạ đầu tiên. Những thao tác đó có thể làm giảm durability hoặc gây mất dữ liệu. Nếu business cần tiếp tục nhận request trong lúc Kafka không đạt ngưỡng ghi, hãy cân nhắc lưu event vào outbox hoặc durable queue khác đã được thiết kế trước.

## 14. Kiểm thử mức xác nhận ghi

Nên kiểm thử trong môi trường staging hoặc cluster thử nghiệm có topology tương tự production. Một số tình huống hữu ích:

- Gửi record với RF=3, min ISR=2 và acks=all; xác nhận ghi thành công khi ISR có đủ 2 hoặc 3 replica.
- Làm một follower rời ISR; xác nhận producer vẫn ghi được nếu còn đủ min ISR và quan sát under-replicated partitions.
- Làm ISR giảm xuống dưới min ISR; xác nhận broker từ chối ghi với acks=all và ứng dụng xử lý lỗi có kiểm soát.
- Khôi phục follower; xác nhận replica bắt kịp và ISR trở lại.
- Dừng leader; xác nhận leader election, producer retry và record đã ACK vẫn có thể đọc được sau phục hồi.
- Ngắt mạng sau khi broker có thể đã ghi nhưng producer chưa nhận ACK; xác nhận idempotent producer hạn chế duplicate do retry trong cùng session.
- Kiểm tra outbox/replay để xác nhận event nghiệp vụ không bị mất khi Kafka tạm thời không thể ghi.

Mỗi bài kiểm thử cần ghi rõ giả thuyết, điều kiện dừng, record id, topic/partition, kết quả mong đợi và dữ liệu quan sát. Không thực hiện fault injection trên production nếu chưa có phạm vi, phê duyệt và cơ chế dừng an toàn.

## 15. Các hiểu nhầm cần tránh

**“acks=all nghĩa là tất cả broker trong cluster đều xác nhận.”** Sai. Chỉ các replica thuộc ISR của partition đích tham gia xác nhận.

**“Replication factor=3 đảm bảo luôn có ba bản sao đồng bộ.”** Sai. RF là số replica được cấu hình; ISR có thể nhỏ hơn do replica lag hoặc mất kết nối.

**“acks=all tự động bảo vệ khi ISR chỉ còn một replica.”** Không nhất thiết. Nếu min ISR cho phép một replica, broker vẫn có thể chấp nhận ghi với chỉ một ISR. Phải đặt min.insync.replicas phù hợp.

**“ACK thành công nghĩa là record đã fsync xuống mọi ổ đĩa.”** Sai. ACK phản ánh điều kiện replication của Kafka; không phải cam kết fsync đồng bộ từng record trên mọi thiết bị.

**“acks=all đảm bảo exactly-once.”** Sai. ACK liên quan đến xác nhận ghi. Exactly-once cần idempotent producer hoặc transaction trong phạm vi phù hợp; side effect ngoài Kafka vẫn cần idempotency hoặc cơ chế phối hợp.

**“Nếu producer timeout thì chắc chắn record chưa được ghi.”** Sai. Broker có thể đã append record nhưng phản hồi bị mất trên mạng. Cần xử lý kết quả không rõ ràng và chống duplicate.

**“Producer báo NotEnoughReplicas thì cứ đổi sang acks=1.”** Đây là thay đổi làm giảm mức xác nhận. Trước tiên cần khôi phục ISR và đánh giá yêu cầu durability. Chỉ thay đổi policy khi đã hiểu rõ rủi ro và có quyết định vận hành.

## 16. Checklist cấu hình và vận hành

**Thiết kế durability**

- [ ] Mỗi topic được phân loại theo mức độ quan trọng và khả năng tái tạo dữ liệu.
- [ ] Replication factor phù hợp với số broker và failure domain vật lý.
- [ ] Replica của cùng partition được phân bố qua broker/rack/AZ độc lập.
- [ ] min.insync.replicas được đặt rõ ràng theo policy của topic.
- [ ] Producer dùng acks=all cho dữ liệu cần độ bền cao.
- [ ] Unclean leader election được đánh giá theo đánh đổi durability và availability.

**Producer**

- [ ] Idempotent producer được bật cho luồng cần chống duplicate do retry.
- [ ] Timeout và retry có giới hạn phù hợp SLA.
- [ ] Future/callback gửi được quan sát; lỗi không bị bỏ qua.
- [ ] Event quan trọng có event id hoặc business key ổn định.
- [ ] Có outbox hoặc cơ chế lưu bền vững khi Kafka tạm thời không nhận ghi.

**Quan sát và phục hồi**

- [ ] Theo dõi ISR, under-replicated và under-min-ISR partitions.
- [ ] Theo dõi producer error, retry, timeout và request latency.
- [ ] Có runbook xử lý NotEnoughReplicas và mất leader.
- [ ] Có quy trình đối chiếu event id, topic, partition và offset.
- [ ] Đã diễn tập follower loss, leader loss và ISR dưới ngưỡng trong môi trường phù hợp.

Mức ACK là một phần của hợp đồng độ bền giữa producer và Kafka. Với dữ liệu quan trọng, cấu hình **acks=all** cùng replication factor, **min.insync.replicas**, ISR được phân bố độc lập và idempotent producer tạo ra nền tảng ghi bền vững. Khi cluster không còn đáp ứng ngưỡng replication, việc từ chối ghi có thể là hành vi đúng để bảo vệ dữ liệu; ứng dụng cần có timeout, retry, quan sát và cơ chế lưu lại ý định phát event để phục hồi có kiểm soát.

