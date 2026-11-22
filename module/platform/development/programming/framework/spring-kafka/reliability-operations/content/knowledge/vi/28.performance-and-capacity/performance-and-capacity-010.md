# Nghẽn do DLT publish

## Mục tiêu

Trong Spring Kafka, Dead Letter Topic (DLT) là nơi lưu những record không thể xử lý thành công sau chính sách retry hoặc được xác định là lỗi không thể retry. DLT giúp giữ lại dữ liệu lỗi để điều tra và xử lý lại, nhưng đường publish sang DLT cũng là một phần của luồng tiêu thụ.

Nghẽn do DLT publish xảy ra khi consumer không thể chuyển record lỗi sang DLT đủ nhanh hoặc việc gửi thất bại. Nếu error handler phải chờ kết quả gửi, listener thread bị giữ lại; nếu lỗi gửi không được xử lý đúng, record có thể bị đánh dấu recovered trong khi chưa được lưu an toàn. Cả hai tình huống đều ảnh hưởng đến độ tin cậy và throughput.

Bài này tập trung vào đường đi từ listener đến DLT: tốc độ phát sinh record lỗi, cấu hình recoverer, Kafka producer, topic đích và năng lực broker.

## Luồng xử lý và điểm có thể nghẽn

Một luồng phổ biến với **DefaultErrorHandler** và **DeadLetterPublishingRecoverer**:

~~~text
Kafka source topic
       |
       v
Listener xử lý record
       |
       +---- thành công ----------------------> commit offset
       |
       +---- thất bại
                |
                v
          retry + backoff
                |
                +---- xử lý lại thành công ---> commit offset
                |
                +---- hết retry / không retry
                              |
                              v
                 DeadLetterPublishingRecoverer
                              |
                              v
                       KafkaTemplate
                              |
                              v
                         Broker
                              |
                              v
                         Topic DLT
~~~

Đường publish có thể chậm ở nhiều điểm: producer phải chờ metadata hoặc buffer, broker xử lý request chậm, partition đích không tồn tại, ISR không đủ, ACL từ chối, hoặc serializer không thể chuyển payload. Khi recoverer chờ xác nhận gửi thành công, thời gian này nằm ngay trên đường xử lý của consumer.

Cần phân biệt ba loại độ trễ:

- **Listener chậm:** thời gian xử lý nghiệp vụ cao trước khi record được chuyển sang DLT.
- **DLT publish chậm:** thời gian từ lúc recoverer gửi đến lúc producer nhận kết quả gửi thành công cao.
- **DLT consumer chậm:** record đã được ghi vào DLT nhưng hệ thống đọc và xử lý DLT bị tụt lag.

DLT consumer lag cao không tự động có nghĩa publish đang nghẽn. Producer vẫn có thể ghi bình thường trong khi DLT consumer không theo kịp; chỉ khi broker gặp áp lực về dung lượng, quota, replication hoặc I/O thì backlog này mới có thể gián tiếp ảnh hưởng đường ghi.

## Dấu hiệu vận hành

Các dấu hiệu thường xuất hiện cùng nhau:

- Consumer lag của source topic tăng dù thời gian xử lý record hợp lệ không đổi.
- Tỷ lệ record được chuyển sang DLT tăng đột ngột; DLT ingress đạt mức cao hơn nhiều so với baseline.
- Listener thread dành nhiều thời gian trong error handler hoặc chờ kết quả gửi DLT.
- Producer có **record-error-rate**, **record-retry-rate**, request latency hoặc buffer pool wait tăng.
- Log xuất hiện lỗi gửi như **TimeoutException**, **NotEnoughReplicas**, **UnknownTopicOrPartition**, **TopicAuthorizationException**, **RecordTooLargeException** hoặc lỗi serialization.
- DLT topic có partition thiếu leader, ISR không đủ, hoặc một partition nhận lưu lượng cao bất thường.

Một dấu hiệu riêng lẻ chưa đủ kết luận. Ví dụ, source consumer lag tăng cũng có thể do listener xử lý chậm, rebalance, broker đọc chậm hoặc downstream dependency bị lỗi. Hãy đối chiếu thời điểm tăng lag với thời gian publish DLT và metric của producer.

## Nguyên nhân thường gặp

### 1. Tỷ lệ record lỗi tăng đột biến

Một lỗi dữ liệu hoặc thay đổi contract có thể khiến phần lớn record cùng thất bại. Ví dụ: schema mới không tương thích, downstream service ngừng hoạt động, dữ liệu đầu vào chứa giá trị ngoài miền hợp lệ hoặc một bug được triển khai lên listener.

Retry làm tăng số lần xử lý trước khi record được chuyển sang DLT. Nếu retry quá nhiều, backoff quá ngắn hoặc lỗi có tính hệ thống, consumer tiếp tục tiêu tốn tài nguyên trong khi DLT vẫn nhận một lượng record lớn. Đây là tình huống retry storm.

Cần đo tỷ lệ record lỗi trên tổng record đầu vào, số lần retry trung bình và tốc độ DLT ingress. Nếu tỷ lệ lỗi tăng cùng lúc với một lần deploy hoặc một thay đổi dữ liệu, hãy xử lý nguyên nhân gốc trước khi tăng capacity.

### 2. DLT topic thiếu partition hoặc không sẵn sàng

Cấu hình mặc định của **DeadLetterPublishingRecoverer** thường tạo tên đích bằng cách thêm hậu tố **.DLT** và giữ partition nguồn. Nếu source topic có 12 partition thì DLT cần có các partition tương ứng khi dùng cách ánh xạ này.

Các trường hợp gây lỗi:

- DLT chưa được tạo trong môi trường tắt auto topic creation.
- DLT có ít partition hơn source topic.
- Partition đích chưa có leader hoặc replica chưa vào ISR.
- Tên topic hoặc partition resolver bị cấu hình sai.
- Producer không có quyền **WRITE** trên DLT hoặc quyền cần thiết để lấy metadata.
- Retention, quota hoặc dung lượng broker khiến broker không thể tiếp tục nhận dữ liệu.

Tạo topic DLT trước khi consumer chạy và quản lý topic bằng quy trình hạ tầng. Không phụ thuộc vào auto creation để xử lý lỗi trong production.

### 3. Kafka producer bị backpressure

DLT publish dùng Kafka producer thông qua **KafkaTemplate**. Producer có thể chậm khi:

- Tốc độ record lỗi vượt throughput mà producer hoặc broker đang phục vụ.
- Buffer producer đầy; lời gọi **send()** có thể chờ buffer đến giới hạn **max.block.ms**.
- Metadata cho topic hoặc partition chưa sẵn sàng.
- Broker phản hồi chậm, retry tăng hoặc request timeout thường xuyên.
- Một partition nóng do phân phối key hoặc do ánh xạ partition nguồn sang DLT.
- Producer dùng cấu hình batch/compression chưa phù hợp với kích thước và tốc độ record.

Các cấu hình thường cần quan sát gồm **batch.size**, **linger.ms**, **compression.type**, **buffer.memory**, **max.block.ms**, **request.timeout.ms**, **delivery.timeout.ms**, **acks** và **retries**. Không tăng hoặc giảm các giá trị này một cách đồng loạt: thay đổi cần dựa trên metric và yêu cầu durability.

### 4. Broker hoặc cluster hết capacity

DLT thường dùng chung Kafka cluster với source topic. Khi cluster đã gần giới hạn CPU, disk I/O, network, request handler hoặc quota, producer DLT chịu cùng áp lực.

**acks=all** cùng **min.insync.replicas** giúp bảo vệ durability nhưng có thể khiến publish thất bại hoặc chậm khi ISR không đủ. Hạ **acks** hoặc **min.insync.replicas** để làm mất triệu chứng có thể làm giảm mức bảo vệ dữ liệu. Chỉ thay đổi durability khi đã đánh giá rõ rủi ro và yêu cầu của hệ thống.

### 5. Payload, serializer và header quá lớn

DLT cần giữ được dữ liệu gốc để điều tra hoặc phát lại. Tuy nhiên, payload lỗi có thể không tương thích với serializer của producer DLT.

Trường hợp thường gặp là lỗi deserialize: listener chưa có object Java hợp lệ nhưng vẫn cần gửi byte gốc sang DLT. Hãy dùng cấu hình deserializer/serializer hỗ trợ cả kiểu dữ liệu đã deserialize và **byte[]** của record lỗi, thường thông qua **ErrorHandlingDeserializer** và serializer phù hợp cho DLT.

Ngoài payload, các header chứa exception message hoặc stack trace có thể làm record lớn hơn đáng kể. Nếu record vượt giới hạn **max.request.size** của producer hoặc giới hạn message của broker, DLT publish sẽ thất bại với lỗi kích thước. Giữ header chẩn đoán ở kích thước có kiểm soát và kiểm tra cả giới hạn phía producer lẫn broker.

### 6. Consumer thread bị giữ trong lúc chờ publish

**KafkaTemplate.send()** có API bất đồng bộ, nhưng recoverer có thể được cấu hình để chờ kết quả gửi nhằm xác nhận record đã vào DLT. Ví dụ, bật **setFailIfSendResultIsError(true)** khiến lỗi gửi được truyền ngược lại error handler. Đây là lựa chọn hữu ích cho độ tin cậy, nhưng khi broker chậm, listener thread có thể bị giữ lâu hơn.

Nếu mỗi listener thread phải chờ một lần publish chậm, throughput của consumer giảm và source lag tăng. Tăng concurrency không phải lúc nào cũng giải quyết được: nếu producer hoặc broker là nút thắt, thêm listener thread chỉ tạo thêm request cạnh tranh cùng một tài nguyên.

## Cách điều tra có thứ tự

### Bước 1: Xác định thời điểm và phạm vi

Ghi nhận thời điểm bắt đầu sự cố, consumer group, source topic, DLT topic, số partition bị ảnh hưởng và lần deploy/thay đổi cấu hình gần nhất. So sánh với baseline trước sự cố.

Xác định vấn đề xảy ra với mọi partition hay chỉ một vài partition. Nếu chỉ một partition có lag hoặc DLT ingress bất thường, kiểm tra key distribution, leader và partition mapping trước khi tăng capacity toàn cluster.

### Bước 2: Đọc lỗi recoverer và producer

Tìm log quanh thời điểm record được chuyển sang DLT. Phân loại lỗi:

| Lỗi hoặc dấu hiệu | Hướng kiểm tra |
|---|---|
| **TimeoutException** | Broker latency, network, metadata, buffer và timeout producer |
| **NotEnoughReplicas** | ISR, replication factor và **min.insync.replicas** |
| **UnknownTopicOrPartition** | Tên DLT, topic đã tồn tại và partition đích |
| **TopicAuthorizationException** | ACL của principal dùng bởi DLT producer |
| **RecordTooLargeException** | Payload, exception headers và giới hạn kích thước |
| **SerializationException** | Serializer có hỗ trợ kiểu dữ liệu thực tế của record lỗi không |
| Producer buffer wait tăng | Tốc độ gửi, **buffer.memory**, broker throughput và thời gian request |

Đừng chỉ tìm exception của listener. Cần tìm cả exception phát sinh trong quá trình recoverer publish.

### Bước 3: Kiểm tra topic và consumer lag

Dùng lệnh Kafka CLI với bootstrap server và tên topic/group của môi trường:

~~~bash
kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --describe --topic orders.DLT

kafka-consumer-groups.sh --bootstrap-server "$BOOTSTRAP" --describe --group orders-consumer
~~~

Kiểm tra DLT có đủ partition theo chiến lược ánh xạ hay không, partition có leader hay không, ISR có đủ theo chính sách replication hay không. So sánh lag của source consumer với lag của DLT consumer để xác định nghẽn nằm ở publish hay ở bước xử lý sau publish.

### Bước 4: Đối chiếu metric

Theo dõi các nhóm metric sau trong cùng một khoảng thời gian:

| Nhóm | Metric nên xem | Ý nghĩa |
|---|---|---|
| DLT ingress | Records/second, bytes/second theo topic và partition | Tốc độ record lỗi được gửi |
| Recoverer | Số lần recover, publish latency, số lần publish thất bại | Thời gian và kết quả chuyển record |
| Producer | **record-error-rate**, **record-retry-rate**, **request-latency-avg**, **bufferpool-wait-time**, **buffer-available-bytes**, **record-queue-time-avg**, **outgoing-byte-rate**, **batch-size-avg** | Producer có bị backpressure hoặc broker phản hồi chậm |
| Source consumer | Lag theo partition, thời gian xử lý listener, số lần retry, rebalance | Ảnh hưởng đến throughput của luồng nguồn |
| Broker | Request latency, network/disk I/O, under-replicated partitions, ISR và quota | Cluster có đủ năng lực ghi hay không |
| DLT consumer | Lag và tốc độ xử lý | Khả năng xử lý record sau khi đã publish |

Tên và cách expose metric phụ thuộc phiên bản Kafka, Spring Kafka và hệ thống monitoring. Dùng JMX/Micrometer exporter hiện có để lấy metric tương đương nếu tên hiển thị khác.

### Bước 5: Ước lượng capacity cần thiết

Tốc độ dữ liệu DLT gần đúng:

~~~text
DLT bytes/second
    = số record lỗi/second × kích thước trung bình của một record
~~~

Ví dụ, nếu có 400 record lỗi mỗi giây và mỗi record trung bình 12 KB:

- Payload DLT vào khoảng 4,8 MB/s.
- Với replication factor 3, cluster phải phục vụ thêm lưu lượng replication; lượng ghi nội bộ xấp xỉ 14,4 MB/s trước khi tính overhead, protocol và hiệu quả compression.

Tính riêng lưu lượng theo partition để phát hiện partition nóng. Khi ước lượng capacity, dùng kích thước record sau khi thêm header và dùng tốc độ lỗi ở đỉnh sự cố, không chỉ dùng trung bình ngày thường.

## Biện pháp xử lý

### Ứng phó ngay trong sự cố

1. Xác nhận DLT topic tồn tại, đủ partition, có leader/ISR và producer có ACL phù hợp.
2. Nếu lỗi bắt nguồn từ một đợt deploy hoặc dependency, dừng hoặc rollback thay đổi gây lỗi để giảm tốc độ record đi vào DLT.
3. Nếu một partition đang quá tải, xác định nguyên nhân phân phối trước khi thay đổi concurrency hoặc partition mapping.
4. Khôi phục broker, network, quota hoặc dung lượng nếu đây là nguyên nhân.
5. Giữ record chưa publish ở trạng thái có thể retry hoặc phục hồi. Không coi record là đã recovered nếu DLT send thất bại.
6. Khi đường publish ổn định, theo dõi DLT ingress, source lag và producer error rate trước khi phát lại dữ liệu với tốc độ cao.

### Cải thiện ngắn hạn

- Tạo DLT topic trước, với số partition và replication phù hợp với source topic.
- Cấu hình retry có giới hạn và backoff đủ dài để tránh retry storm khi lỗi có tính hệ thống.
- Bật cơ chế phát hiện lỗi gửi DLT để error handler biết publish thất bại; xác minh hành vi cụ thể theo phiên bản Spring Kafka đang dùng.
- Điều chỉnh batch, compression và buffer producer dựa trên kích thước record, throughput và metric thực tế.
- Cân nhắc producer factory riêng cho DLT nếu producer dùng chung đang cạnh tranh tài nguyên với luồng publish khác. Cách này cô lập tài nguyên phía client; nó không làm tăng capacity của broker dùng chung.
- Thiết lập retention cho DLT đủ dài để đội vận hành có thời gian điều tra, đồng thời dự trù dung lượng theo tốc độ lỗi cực đại.

### Cải thiện dài hạn

- Theo dõi DLT ingress và publish failure như metric vận hành chính thức; cảnh báo khi publish thất bại hoặc tốc độ DLT tăng vượt baseline.
- Kiểm thử tình huống DLT broker unavailable, ACL sai, partition thiếu và payload quá lớn. Xác minh record không bị mất khi recoverer thất bại.
- Tách lỗi có thể retry khỏi lỗi không thể retry; tránh retry dài với lỗi dữ liệu cố định.
- Duy trì quy trình replay có giới hạn tốc độ, có khả năng chống xử lý trùng và có kiểm soát vòng lặp khi record phát lại tiếp tục thất bại.
- Nếu hệ thống dùng Kafka transaction, thiết kế recoverer và after-rollback processing theo mô hình transaction của ứng dụng. Không áp dụng cấu hình error handler non-transactional một cách máy móc; cần bảo đảm việc publish DLT và xử lý offset tuân theo yêu cầu atomicity.

## Ví dụ cấu hình Spring Kafka

Ví dụ dưới đây minh họa error handler non-transactional. Recoverer ánh xạ record sang partition cùng số ở topic có hậu tố **.DLT**; vì vậy DLT phải được tạo với đủ partition. **FixedBackOff** giới hạn số lần retry trước khi chuyển record sang recoverer.

~~~java
@Bean
DefaultErrorHandler dltErrorHandler(KafkaTemplate<Object, Object> kafkaTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) ->
                            new TopicPartition(
                                    record.topic() + ".DLT",
                                    record.partition()));

    // Truyền lỗi publish về error handler nếu broker không nhận được record.
    recoverer.setFailIfSendResultIsError(true);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
~~~

Gắn error handler vào listener container factory:

~~~java
factory.setCommonErrorHandler(dltErrorHandler);
~~~

Các điểm cần xác nhận khi áp dụng:

- Serializer của **KafkaTemplate** phải hỗ trợ kiểu value thực tế. Với lỗi deserialize, cần giữ và publish được byte gốc.
- DLT phải có partition tương ứng với partition nguồn nếu resolver giữ nguyên partition.
- **setFailIfSendResultIsError(true)** giúp lỗi publish quay lại error handler, nhưng có thể làm listener chờ kết quả gửi. Chọn timeout và retry dựa trên SLO.
- Số lần retry, loại exception được retry và backoff cần phù hợp với bản Spring Kafka đang dùng và đặc tính lỗi.
- Nếu container dùng transaction, hãy dùng cơ chế xử lý sau rollback và recoverer tương thích transaction của phiên bản đó.

## Checklist khi kết thúc incident

- [ ] Đã xác định nguyên nhân gốc của record lỗi tăng cao.
- [ ] DLT topic tồn tại, đủ partition, leader/ISR ổn định và ACL hợp lệ.
- [ ] DLT producer không còn lỗi gửi hoặc buffer wait bất thường.
- [ ] Source consumer lag giảm theo dự kiến sau khi publish được khôi phục.
- [ ] DLT consumer có thể xử lý backlog và retention đủ để giữ dữ liệu.
- [ ] Quy trình replay có giới hạn tốc độ và tránh xử lý trùng.
- [ ] Đã bổ sung cảnh báo cho DLT publish failure, DLT ingress bất thường và source lag.


