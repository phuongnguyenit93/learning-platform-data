# Cấu hình số phân vùng, hệ số sao chép và thuộc tính topic

Kafka Binder kết nối binding của Spring Cloud Stream với topic Kafka. Khi binding cần một topic chưa tồn tại, binder có thể tạo topic và cấu hình số partition, replication factor cùng một số thuộc tính topic. Khi topic đã tồn tại, binder cần kiểm tra cấu hình hiện tại có đáp ứng yêu cầu của binding hay không; một số tùy chọn có thể bổ sung partition, nhưng việc thay đổi replica assignment hoặc topic config hiện hữu thường cần thao tác quản trị riêng.

Ba nhóm cấu hình cần được phân biệt:

- **Số partition** quyết định cách topic được chia thành các luồng log có thứ tự độc lập và ảnh hưởng đến khả năng xử lý song song.
- **Replication factor** xác định số bản sao của mỗi partition trên các broker, từ đó ảnh hưởng đến khả năng chịu lỗi và chi phí lưu trữ.
- **Topic properties** điều khiển thời gian lưu giữ, chính sách compact, giới hạn kích thước message, số replica đồng bộ tối thiểu và các hành vi lưu trữ khác.

Spring Cloud Stream cung cấp cấu hình ở cấp Kafka binder và từng binding. Chọn đúng phạm vi giúp nhiều topic có thể dùng mặc định chung, trong khi topic đặc biệt có cấu hình riêng phù hợp với yêu cầu nghiệp vụ.

## 1. Cấu trúc topic Kafka

Một topic chứa một hoặc nhiều partition. Mỗi partition là một log append-only có thứ tự record riêng và được định danh bằng số thứ tự. Record trong cùng partition có offset tăng dần; Kafka không tạo thứ tự toàn cục giữa các partition.

~~~text
Topic: orders.events

Partition 0:  offset 0 -> offset 1 -> offset 2
Partition 1:  offset 0 -> offset 1 -> offset 2
Partition 2:  offset 0 -> offset 1 -> offset 2
~~~

Producer chọn partition cho từng record, thường dựa trên record key hoặc partitioning strategy. Consumer group chia các partition cho các consumer thành viên để xử lý song song. Số partition vì vậy là một yếu tố quan trọng khi thiết kế throughput và concurrency.

Mỗi partition có một replica leader và có thể có nhiều follower replica trên các broker khác. Producer ghi vào leader; follower sao chép dữ liệu từ leader. Kafka theo dõi tập replica đang đồng bộ, gọi là ISR (In-Sync Replicas). Nếu leader gặp sự cố, một replica đủ điều kiện có thể được bầu làm leader mới theo chính sách của cluster.

## 2. Số partition và replication factor

Hai thông số có ý nghĩa khác nhau:

| Thông số | Ý nghĩa | Ví dụ |
|---|---|---|
| Partition count | Số log độc lập của topic | 6 partition |
| Replication factor | Số bản sao của mỗi partition, bao gồm leader | 3 replica |

Nếu topic có 6 partition và replication factor 3, tổng cộng có 18 bản sao partition được phân bố trên các broker. Điều này không có nghĩa topic có 18 partition logic; consumer group vẫn chỉ phân phối 6 partition gốc.

Replication factor 3 thường cần ít nhất 3 broker để đặt các replica trên các broker khác nhau. Nếu cluster có ít broker hơn, việc tạo topic với replication factor lớn hơn số broker có thể thất bại hoặc không đạt được phân bố mong muốn tùy cấu hình và phiên bản.

Số partition ảnh hưởng đến:

- Mức song song tối đa của một consumer group đối với topic đó.
- Số lượng leader và metadata mà cluster phải quản lý.
- Kích thước log segment, file handle và chi phí vận hành.
- Phân bố khóa và thứ tự theo partition.

Replication factor ảnh hưởng đến:

- Khả năng tiếp tục đọc/ghi khi một broker gặp sự cố.
- Lượng dữ liệu lưu trữ và lưu lượng replication giữa broker.
- Số replica cần bắt kịp để một partition trở lại trạng thái đầy đủ.
- Khả năng ghi khi số ISR giảm dưới ngưỡng yêu cầu.

Không tăng partition chỉ để tăng số consumer. Nếu một topic có 6 partition, một consumer group có thể gán tối đa 6 partition cho 6 consumer tại một thời điểm; consumer bổ sung có thể không được gán partition. Cần chọn số partition dựa trên throughput đo được, độ trễ xử lý, concurrency dự kiến và tài nguyên broker.

## 3. Cấu hình ở cấp Kafka binder

Kafka Binder cung cấp các thuộc tính toàn cục trong phần binder:

| Thuộc tính | Vai trò |
|---|---|
| auto-create-topics | Cho phép binder tạo topic khi cần |
| auto-add-partitions | Cho phép binder bổ sung partition khi topic hiện có thiếu |
| min-partition-count | Số partition tối thiểu binder yêu cầu khi provisioning |
| replication-factor | Replication factor mặc định cho topic được binder tạo |
| required-acks | Mức xác nhận ghi mà Kafka producer yêu cầu |

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 3
          replication-factor: 3
          required-acks: all
~~~

Ý nghĩa:

- **auto-create-topics: true** cho phép binder tạo topic khi topic chưa tồn tại và binder cần provisioning.
- **auto-add-partitions: true** cho phép binder tăng số partition của topic hiện hữu khi số partition hiện tại thấp hơn mức yêu cầu.
- **min-partition-count: 3** đặt mức partition tối thiểu ở cấp binder.
- **replication-factor: 3** đặt replication factor mặc định cho topic được tạo tự động.
- **required-acks: all** yêu cầu producer chờ xác nhận từ các replica đang nằm trong ISR theo semantics của Kafka.

Trong tài liệu Kafka Binder hiện hành, min-partition-count chỉ có hiệu lực khi auto-create-topics hoặc auto-add-partitions được bật. Giá trị này có thể bị vượt qua bởi partition-count của producer hoặc tích số instance-count và concurrency nếu một trong các giá trị đó lớn hơn. Vì vậy, số partition thực tế được provisioning có thể lớn hơn min-partition-count.

Replication factor ở cấp binder áp dụng cho topic được tạo tự động và có thể bị ghi đè ở từng binding. Từ Kafka Binder 3.0.8, giá trị mặc định là -1 để dùng cấu hình default.replication.factor của broker. Với các phiên bản cũ hơn, mặc định và cách xử lý khác nhau; một số phiên bản yêu cầu giá trị ít nhất là 1. Hãy xác nhận phiên bản binder trước khi dựa vào mặc định.

## 4. Phân biệt auto-create-topics của binder và broker

Thuộc tính auto-create-topics của Kafka Binder độc lập với cấu hình auto.create.topics.enable của Kafka broker:

- Nếu binder bật auto-create-topics, binder có thể chủ động provisioning topic theo cấu hình ứng dụng.
- Nếu binder tắt auto-create-topics, binder mong đợi topic đã được tạo và cấu hình trước; nếu topic không tồn tại, binding có thể không khởi động được.
- Nếu broker vẫn bật auto.create.topics.enable, broker có thể tự tạo topic khi nhận yêu cầu metadata cho topic chưa tồn tại, sử dụng cấu hình mặc định phía broker.

Trong môi trường production, nếu tổ chức muốn kiểm soát topic qua quy trình hạ tầng, nên tạo topic trước bằng công cụ quản trị hoặc operator, tắt tự tạo topic ngoài ý muốn và cấu hình binder theo chế độ sử dụng topic có sẵn. Khi đó, pipeline hạ tầng chịu trách nhiệm partition count, replica assignment và topic properties.

## 5. Cấu hình partition count cho từng binding

Ngoài min-partition-count toàn binder, producer binding có thuộc tính partition-count. Thuộc tính này là gợi ý số partition khi binder provisioning topic:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-count: 6
            partition-key-expression: payload.orderId
~~~

Trong ví dụ, binding publishOrder-out-0 phát đến topic orders.events và yêu cầu ít nhất 6 partition khi provisioning. partition-key-expression chọn orderId làm khóa phân vùng theo cơ chế partitioning chung của Spring Cloud Stream. Các message có cùng orderId có thể được định tuyến cùng partition khi dùng cùng thuật toán và cùng số partition.

partition-count không phải lệnh giảm số partition của topic. Kafka không hỗ trợ giảm partition count bằng thao tác alter thông thường. Nếu topic đã có 8 partition trong khi binding yêu cầu 6, binder sử dụng số partition hiện có; nó không tự giảm về 6.

Nếu topic đã có ít partition hơn giá trị yêu cầu:

- Khi auto-add-partitions là false, binder có thể từ chối provisioning và không khởi động binding.
- Khi auto-add-partitions là true, binder có thể bổ sung partition để đạt mức yêu cầu.

Tăng partition count có thể làm thay đổi phép ánh xạ key sang partition. Với hash partitioner, cùng một orderId có thể được ghi vào partition cũ trước khi mở rộng và partition mới sau khi mở rộng. Vì vậy, tăng partition có thể làm các message cũ và mới của cùng khóa nằm ở các partition khác nhau, ảnh hưởng đến thứ tự nghiệp vụ. Cần lập kế hoạch migration và đánh giá consumer trước khi thay đổi.

## 6. Replication factor theo từng binding

Một topic đặc biệt có thể cần replication factor khác mặc định toàn binder. Kafka Binder cho phép đặt replication factor trong cấu hình topic của producer binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
~~~

Đường dẫn cấu hình đầy đủ là spring.cloud.stream.kafka.bindings.<binding-name>.producer.topic.replication-factor. Giá trị này ghi đè replication-factor toàn binder khi provisioning topic cho binding đó.

Replication factor theo binding chỉ được dùng khi provisioning topic. Nếu topic đã tồn tại, thay đổi giá trị trong application.yml không tự động phân bố lại replica của topic. Việc thay đổi replication factor của topic hiện hữu cần thao tác replica reassignment bằng công cụ quản trị Kafka hoặc nền tảng quản lý cluster.

Có thể khai báo replica assignment tường minh bằng topic.replicas-assignment. Đây là map từ partition ID đến danh sách broker ID được gán replica cho partition đó. Khi cung cấp replica assignment, replication-factor bị bỏ qua vì danh sách broker đã xác định số replica và vị trí cụ thể. Cần bảo đảm broker ID tồn tại, phân bố hợp lý và không đặt mọi replica của một partition trên cùng một broker.

## 7. Cấu hình topic properties theo binding

Kafka topic có nhiều thuộc tính điều khiển cách lưu trữ và vận hành. Kafka Binder cho phép đặt chúng qua map topic.properties trong cấu hình producer hoặc consumer binding. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
                  retention.ms: 604800000
                  cleanup.policy: delete
                  max.message.bytes: 1048576
                  segment.bytes: 1073741824
~~~

Ví dụ đặt:

- **min.insync.replicas: 2** yêu cầu ít nhất hai replica trong ISR khi producer ghi với acks=all.
- **retention.ms: 604800000** đặt thời gian lưu log tối đa theo chính sách delete là bảy ngày.
- **cleanup.policy: delete** dùng chính sách xóa log theo retention.
- **max.message.bytes: 1048576** đặt giới hạn kích thước record batch theo cấu hình topic.
- **segment.bytes: 1073741824** đặt kích thước segment mục tiêu khoảng 1 GiB.

topic.properties là map cấu hình topic của Kafka, không phải map Kafka client producer properties. Các thuộc tính như linger.ms, batch.size hoặc compression.type thuộc producer client và phải được đặt trong nhóm producer.configuration hoặc thuộc tính producer tương ứng, không đặt nhầm vào topic.properties.

topic.properties được dùng khi binder provisioning topic. Đối với topic đã tồn tại, không nên giả định việc thay đổi map này sẽ cập nhật cấu hình đang lưu trên broker. Dùng Kafka Admin API, kafka-configs.sh hoặc operator quản lý topic để thay đổi cấu hình hiện hữu.

## 8. Một số topic properties thường dùng

| Thuộc tính | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| cleanup.policy | Chính sách delete, compact hoặc kết hợp | Event log hoặc changelog theo key |
| retention.ms | Thời gian lưu log theo chính sách delete | Giữ dữ liệu trong khoảng thời gian nghiệp vụ |
| retention.bytes | Giới hạn dung lượng log theo partition | Kiểm soát dung lượng lưu trữ |
| min.insync.replicas | Số ISR tối thiểu để ghi với acks=all thành công | Cân bằng độ bền dữ liệu và khả năng ghi |
| max.message.bytes | Giới hạn kích thước record batch | Ngăn message quá lớn làm tăng áp lực broker |
| segment.bytes | Kích thước segment log | Điều chỉnh quản lý log và tác vụ retention |
| message.timestamp.type | Chọn CreateTime hoặc LogAppendTime | Chuẩn hóa cách diễn giải timestamp |

### cleanup.policy

Với **delete**, Kafka xóa các segment cũ khi vượt retention time hoặc retention size theo cấu hình. Đây là lựa chọn thường gặp cho event log có thời hạn lưu giữ.

Với **compact**, Kafka giữ lại giá trị mới nhất theo key trong quá trình compaction, đồng thời có thể giữ tombstone trong một khoảng thời gian để biểu diễn việc xóa key. Chính sách này phù hợp với changelog hoặc topic lưu trạng thái hiện tại theo khóa.

Có thể dùng kết hợp delete và compact khi cần cả compaction lẫn giới hạn thời gian lưu trữ. Không dùng compact cho mọi event topic: nếu nghiệp vụ cần toàn bộ lịch sử sự kiện, compact có thể loại bỏ các giá trị cũ cùng key.

### retention.ms và retention.bytes

retention.ms đặt thời gian tối đa lưu log theo chính sách delete. retention.bytes đặt giới hạn dung lượng log theo từng partition. Khi cấu hình cả hai, Kafka có thể xóa segment cũ khi một trong các giới hạn retention được đáp ứng. Hãy tính tổng dung lượng dự kiến dựa trên số partition, tốc độ ghi và thời gian lưu giữ.

Retention là chính sách lưu trữ, không phải cam kết message được lưu chính xác đến từng mili giây rồi mới xóa. Kafka thực hiện xóa theo segment và chu kỳ kiểm tra của broker.

## 9. Kết hợp replication factor, min.insync.replicas và acks

Replication factor đơn lẻ chưa đủ để mô tả độ bền ghi. Cần hiểu mối quan hệ giữa:

- **replication.factor:** tổng số replica được gán cho mỗi partition.
- **min.insync.replicas:** số replica tối thiểu phải còn trong ISR để ghi với acks=all được chấp nhận.
- **acks:** mức xác nhận mà producer yêu cầu.

Một cấu hình thường gặp cho topic quan trọng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          required-acks: all
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
~~~

Với replication factor 3 và min.insync.replicas 2:

- Khi cả ba replica còn trong ISR, acks=all yêu cầu tất cả replica đang trong ISR xác nhận.
- Khi một replica bị mất và ISR còn hai replica, ghi vẫn có thể thành công sau khi hai replica trong ISR xác nhận.
- Khi ISR giảm xuống dưới hai, producer ghi với acks=all sẽ nhận lỗi thay vì chấp nhận ghi dưới ngưỡng tối thiểu.

Cấu hình này ưu tiên độ bền dữ liệu; khi cluster mất quá nhiều replica, hệ thống có thể tạm từ chối ghi. Đây là trade-off giữa availability và durability. Không hạ min.insync.replicas chỉ để loại bỏ lỗi ghi nếu điều đó làm giảm bảo đảm dữ liệu mà nghiệp vụ yêu cầu.

Giá trị mặc định required-acks có thể thay đổi giữa các phiên bản binder. Trong tài liệu hiện hành, mặc định là all; hãy đặt tường minh khi yêu cầu độ bền quan trọng và kiểm tra cấu hình thực tế của phiên bản ứng dụng.

## 10. Cấu hình hoàn chỉnh cho topic orders.events

Ví dụ kết hợp số partition, replication factor, topic properties và partition key:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-count: 6
            partition-key-expression: payload.orderId
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 3
          replication-factor: 3
          required-acks: all
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
                  retention.ms: 604800000
                  cleanup.policy: delete
                  max.message.bytes: 1048576
~~~

Trong cấu hình này, binder có thể tạo orders.events với ít nhất 6 partition vì partition-count của producer lớn hơn min-partition-count. Topic được tạo với replication factor 3, có min.insync.replicas bằng 2 và lưu log tối đa bảy ngày theo chính sách delete. Các message có cùng orderId được định tuyến theo khóa để giữ thứ tự trong cùng partition khi các producer dùng chung partitioning strategy.

Ví dụ dùng auto-create-topics và auto-add-partitions để minh họa provisioning tự động. Với production, tổ chức có thể tắt hai tùy chọn này, tạo topic qua pipeline hạ tầng và giữ cấu hình binder chỉ để kết nối. Dù dùng cách nào, hãy xác minh topic thực tế sau khi ứng dụng khởi động.

## 11. Quản lý topic có sẵn bằng công cụ Kafka

Khi topic được quản lý bên ngoài Spring Cloud Stream, có thể tạo topic bằng kafka-topics.sh:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.events \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete
~~~

Xem partition và replica assignment:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events
~~~

Xem topic config override:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe
~~~

Tăng partition count:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders.events \
  --partitions 9
~~~

Lệnh alter partition count chỉ tăng số partition; không giảm số partition đã tạo. Sau khi tăng, kiểm tra phân bố leader/replica và đánh giá lại partition key vì ánh xạ key có thể thay đổi.

Thay topic config hiện hữu có thể dùng kafka-configs.sh với thao tác alter. Thay replication factor cần quy trình reassignment replica; chỉ thay thuộc tính replication-factor trong application.yml không di chuyển replica của topic đã tồn tại.

## 12. Quy tắc khi topic đã tồn tại

Trước khi khởi động binding, binder kiểm tra topic hiện tại và các yêu cầu provisioning. Các tình huống phổ biến:

| Trạng thái topic | Cấu hình binder | Kết quả cần dự đoán |
|---|---|---|
| Topic chưa tồn tại | auto-create-topics bật | Binder có thể tạo topic theo cấu hình provisioning |
| Topic chưa tồn tại | auto-create-topics tắt | Binding có thể lỗi vì topic chưa được tạo |
| Topic có ít partition hơn yêu cầu | auto-add-partitions tắt | Binder có thể từ chối khởi động binding |
| Topic có ít partition hơn yêu cầu | auto-add-partitions bật | Binder có thể bổ sung partition |
| Topic có nhiều partition hơn yêu cầu | Bất kỳ | Binder giữ số partition hiện có |
| Topic có replication factor khác cấu hình | Topic đã tồn tại | Cần quản trị replica riêng; không giả định binder tự thay đổi |
| Topic có topic properties khác cấu hình | Topic đã tồn tại | Cần kiểm tra và cập nhật bằng công cụ quản trị nếu muốn đổi |

Không dùng cấu hình provisioning để thay thế kiểm tra drift. Một topic có thể tồn tại và binding vẫn khởi động, nhưng retention, cleanup policy hoặc replica assignment không đúng yêu cầu. Nên có bước kiểm tra cấu hình topic trong pipeline hoặc quy trình vận hành.

## 13. Lập kế hoạch số partition

Số partition nên được chọn từ yêu cầu tải và khả năng xử lý:

1. Ước lượng tốc độ message trung bình và đỉnh.
2. Đo throughput xử lý của một consumer instance với payload thực tế.
3. Xác định số consumer tối đa cần chạy song song trong một group.
4. Dự phòng headroom cho tăng trưởng và rebalance.
5. Kiểm tra số broker, số partition tổng và tài nguyên lưu trữ.
6. Đánh giá yêu cầu thứ tự theo key trước khi tăng partition.

Ví dụ, nếu một consumer xử lý ổn định 500 message/giây và hệ thống cần khoảng 2.000 message/giây, bốn partition có thể là điểm khởi đầu để chạy song song bốn consumer. Đây chỉ là ước lượng ban đầu; thực tế còn phụ thuộc phân bố key, độ trễ I/O, batch, producer throughput, broker và consumer concurrency.

Tránh tạo quá nhiều partition khi chưa cần. Mỗi partition có metadata, log segment, replica và chi phí xử lý. Tăng partition cũng có thể làm thay đổi thứ tự theo key và tăng công việc rebalance.

## 14. Lập kế hoạch replication factor

Replication factor nên phản ánh mức chịu lỗi và topology broker:

- RF=1 không có follower replica; mất broker chứa leader có thể làm partition unavailable cho đến khi broker phục hồi.
- RF=2 có một bản sao bổ sung, nhưng khả năng chịu lỗi đồng thời và chính sách ISR cần được cân nhắc.
- RF=3 thường cho phép đặt leader và hai follower trên các broker khác nhau, cân bằng phổ biến giữa độ bền và chi phí.

Replication factor 3 làm tăng dung lượng lưu trữ xấp xỉ ba lần so với một bản sao, chưa tính overhead, segment và metadata. Với nhiều topic hoặc lưu lượng lớn, cần tính tổng dung lượng theo số partition, retention và replication factor.

Replica nên được phân bố trên các broker và failure domain phù hợp. Nếu tất cả broker nằm trên cùng một rack hoặc vùng lỗi, replication factor cao vẫn có thể không bảo vệ được trước sự cố ở cấp rack hoặc zone. Dùng rack awareness và quy trình reassignment phù hợp với hạ tầng.

## 15. Thay đổi partition và replica trong production

Trước khi thay đổi topic hiện hữu:

- Kiểm tra consumer group lag và thời điểm có thể thực hiện thay đổi.
- Xác định các producer đang dùng partition key hoặc custom partitioner.
- Đánh giá việc tăng partition có làm một key chuyển partition và phá vỡ thứ tự không.
- Kiểm tra dung lượng broker, vị trí replica và tải mạng khi reassignment.
- Xác định tác động đến Kafka Streams state store hoặc ứng dụng dựa trên số partition.
- Thực hiện thay đổi ở môi trường thử nghiệm, xác nhận leader/ISR và throughput.
- Lưu cấu hình trước/sau và kế hoạch rollback hoặc phương án bù trừ.

Kafka cho phép tăng partition count nhưng không giảm bằng thao tác thông thường. Thay replication factor yêu cầu phân phối lại replica; quá trình này có thể tiêu thụ băng thông và I/O đáng kể. Không chạy reassignment hàng loạt khi cluster đang thiếu tài nguyên hoặc có replica chưa bắt kịp.

## 16. Kiểm tra cấu hình sau provisioning

Sau khi ứng dụng tạo hoặc kết nối topic, kiểm tra:

- Topic tồn tại đúng tên và có đúng số partition.
- Replication factor của từng partition khớp yêu cầu.
- Leader và follower phân bố trên broker hợp lý.
- ISR đủ số lượng theo min.insync.replicas.
- Topic config như cleanup.policy, retention.ms và max.message.bytes đúng giá trị.
- Producer thực sự dùng acks và partition key mong muốn.
- Consumer group có thể nhận partition và lag nằm trong ngưỡng.

Nên ghi nhận cấu hình mong muốn dưới dạng IaC hoặc manifest topic để có thể so sánh với trạng thái thực tế. Không chỉ dựa vào log khởi động thành công của ứng dụng; binder khởi động được không có nghĩa mọi topic properties đã đúng như thiết kế.

## 17. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Binding không khởi động vì topic chưa tồn tại | auto-create-topics tắt và topic chưa được provision | Tạo topic qua hạ tầng hoặc bật provisioning có kiểm soát |
| Binder báo thiếu partition | Topic hiện tại ít partition hơn yêu cầu và auto-add-partitions tắt | Tăng partition có kế hoạch hoặc bật auto-add-partitions |
| Topic được tạo với replication factor thấp | Binder dùng default broker replication factor hoặc cấu hình phiên bản khác | Đặt replication-factor tường minh và kiểm tra phiên bản |
| Producer bị lỗi NotEnoughReplicas | ISR thấp hơn min.insync.replicas khi dùng acks=all | Khôi phục replica, kiểm tra broker và ISR; không hạ ngưỡng tùy tiện |
| Topic properties không đổi sau deploy | Topic đã tồn tại; map chỉ áp dụng khi provisioning | Cập nhật qua Kafka Admin API, kafka-configs hoặc operator |
| Message cùng key đổi partition sau khi mở rộng topic | Partition count thay đổi thuật toán ánh xạ key | Lập kế hoạch migration và xử lý thứ tự theo aggregate |
| Tăng consumer nhưng throughput không tăng | Số partition thấp hoặc key bị lệch tải | Đo partition lag và phân bố key, điều chỉnh thiết kế |

## 18. Checklist trước khi phát hành

- Đã xác định số partition theo throughput, concurrency và yêu cầu thứ tự.
- Replication factor phù hợp số broker và failure domain.
- min.insync.replicas và producer acks được cấu hình theo mức durability mong muốn.
- Đã phân biệt min-partition-count toàn binder với partition-count của từng producer binding.
- Đã xác định auto-create-topics và auto-add-partitions có được phép trong môi trường hay không.
- Topic properties được cấu hình đúng phạm vi và chỉ kỳ vọng áp dụng khi provisioning.
- Topic hiện hữu đã được kiểm tra; không giả định application.yml tự thay đổi replica assignment hoặc config.
- Có kế hoạch cho việc tăng partition, reassignment replica và tác động đến key ordering.
- Có bước describe topic, kiểm tra ISR và xác minh topic config sau triển khai.
- Cấu hình mong muốn được lưu trong pipeline hoặc công cụ quản lý hạ tầng.

Kafka Binder cho phép đặt cấu hình topic ở cấp binder và từng binding, nhờ đó ứng dụng có thể yêu cầu partition count, replication factor và các topic properties phù hợp với từng luồng sự kiện. Hãy phân biệt rõ cấu hình provisioning với trạng thái topic đã tồn tại, kết hợp replication factor với min.insync.replicas và producer acks, đồng thời đánh giá ảnh hưởng của việc tăng partition đến key ordering. Kiểm tra topic thực tế sau triển khai giúp bảo đảm cấu hình ứng dụng, broker và yêu cầu nghiệp vụ cùng nhất quán.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Apache Kafka — Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/)
