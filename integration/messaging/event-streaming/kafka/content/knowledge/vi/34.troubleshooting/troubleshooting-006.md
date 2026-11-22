# NotEnoughReplicas và ISR không đạt yêu cầu

Khi producer ghi dữ liệu với chế độ xác nhận đầy đủ, Kafka chỉ chấp nhận bản ghi nếu số replica đang đồng bộ đáp ứng ngưỡng an toàn của topic. Nếu số replica trong ISR giảm xuống dưới ngưỡng này, producer có thể nhận lỗi NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend. Đây thường là dấu hiệu cụm Kafka đang mất replica, replica theo kịp chậm hoặc cấu hình độ bền không phù hợp với số broker đang hoạt động.

Bài học thuộc chương **Chẩn đoán sự cố** của module **KAFKA**. Phần này hướng dẫn đọc trạng thái ISR, phân biệt lỗi thiếu replica với lỗi mất leader, xác định nguyên nhân từ broker và mạng, khôi phục replication an toàn, rồi cấu hình producer Java/Spring Kafka để ứng dụng phản ứng đúng khi cụm suy giảm.

Sau bài học, người học có thể:

- Giải thích quan hệ giữa replication factor, ISR, acks và min.insync.replicas.
- Nhận diện thời điểm Kafka trả NotEnoughReplicas và NotEnoughReplicasAfterAppend.
- Dùng công cụ dòng lệnh và metric để tìm partition có ISR thấp hoặc replica chưa đồng bộ.
- Xác định nguyên nhân từ broker, đĩa, mạng, tải hoặc cấu hình.
- Khôi phục replica và kiểm tra lại độ bền trước khi đưa hệ thống về trạng thái bình thường.
- Thiết kế retry, timeout và xử lý lỗi producer mà không làm mất hoặc nhân đôi tác dụng phụ nghiệp vụ.

## 1. ISR là gì và tại sao có thể bị thiếu?

Một partition có một leader và không hoặc nhiều follower replica. Producer gửi bản ghi tới leader. Follower lấy dữ liệu từ leader bằng cơ chế replication và cập nhật log của partition trên broker riêng.

ISR (in-sync replicas) là tập replica đang theo kịp leader đủ điều kiện được xem là đồng bộ. Tập này bao gồm leader. ISR có thể thay đổi theo thời gian: follower chậm hoặc ngừng fetch đủ lâu có thể bị loại khỏi ISR; khi bắt kịp lại, follower có thể được thêm trở lại.

Ví dụ topic có replication factor bằng 3:

| Replica | Broker | Trạng thái |
|---|---:|---|
| Leader | 1 | Trong ISR |
| Follower | 2 | Trong ISR |
| Follower | 3 | Ngoài ISR, đang bắt kịp |

Trong ví dụ này, ISR có 2 replica dù partition có 3 bản sao được cấu hình. Kafka không coi follower ngoài ISR là bản sao đủ điều kiện cho xác nhận ghi với acks=all.

### Các cấu hình liên quan

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| replication.factor | Topic | Số replica được phân bổ cho mỗi partition |
| min.insync.replicas | Topic hoặc mặc định broker | Số replica tối thiểu phải có trong ISR để chấp nhận ghi với acks=all |
| acks | Producer | Mức xác nhận producer yêu cầu từ broker |
| enable.idempotence | Producer | Hạn chế bản ghi trùng do retry của producer và giữ thứ tự theo các ràng buộc cấu hình |
| replica.lag.time.max.ms | Broker | Thời gian follower có thể không fetch hoặc không theo kịp leader trước khi bị loại khỏi ISR |
| unclean.leader.election.enable | Broker | Cho phép hay không bầu replica ngoài ISR làm leader khi không còn leader ISR khả dụng |

Replication factor là số replica được cấu hình, còn ISR là số replica hiện đang đồng bộ. Hai con số này không nhất thiết bằng nhau.

### acks và min.insync.replicas

Producer có thể chọn các mức xác nhận:

- acks=0: producer không chờ broker xác nhận. Ứng dụng không có xác nhận đáng tin cậy về việc broker đã ghi bản tin.
- acks=1: leader xác nhận sau khi ghi vào log cục bộ. Follower có thể chưa nhận bản ghi tại thời điểm producer nhận xác nhận.
- acks=all (hoặc acks=-1): leader chờ các replica hiện có trong ISR xác nhận theo giao thức replication trước khi trả thành công.

min.insync.replicas đặt ngưỡng tối thiểu cho số replica trong ISR khi producer dùng acks=all. Cấu hình này không có tác dụng cưỡng chế tương đương với producer dùng acks=1 hoặc acks=0.

Giả sử topic có replication factor bằng 3 và min.insync.replicas bằng 2:

- ISR có 3 replica: ghi với acks=all được chấp nhận.
- ISR có 2 replica: ghi vẫn được chấp nhận; cả hai replica trong ISR phải tham gia xác nhận.
- ISR chỉ còn 1 replica: ghi với acks=all bị từ chối vì không đạt ngưỡng tối thiểu.

Như vậy, min.insync.replicas là ngưỡng bảo vệ độ bền của ghi dữ liệu. Nó không tự tạo thêm replica và cũng không khôi phục follower bị lỗi.

### Hai lỗi NotEnoughReplicas

Kafka phân biệt hai tình huống:

| Lỗi | Ý nghĩa | Cách diễn giải |
|---|---|---|
| NotEnoughReplicasException | Số replica trong ISR thấp hơn min.insync.replicas khi broker kiểm tra yêu cầu ghi | Bản ghi bị từ chối trước khi append theo điều kiện kiểm tra này |
| NotEnoughReplicasAfterAppendException | Bản ghi đã được append nhưng số ISR đủ điều kiện giảm dưới ngưỡng trước khi hoàn tất xác nhận | Không được coi phản hồi lỗi là bằng chứng chắc chắn bản ghi chưa tồn tại trên leader |

Với lỗi sau append, cần thận trọng khi retry ở tầng nghiệp vụ. Producer có thể nhận lỗi dù leader đã ghi bản ghi. Nếu ứng dụng gửi lại bằng một event id mới hoặc thực hiện tác dụng phụ trước khi xác minh, hệ thống có thể tạo bản ghi hoặc giao dịch nghiệp vụ trùng lặp. Hãy dùng idempotent producer và event id ổn định; ở consumer hoặc tầng lưu trữ nghiệp vụ vẫn cần cơ chế chống xử lý trùng khi hợp đồng yêu cầu.

## 2. Nhận diện triệu chứng và khoanh vùng

Sự cố thiếu ISR thường xuất hiện ở producer trước tiên:

- Producer trả NotEnoughReplicasException hoặc NotEnoughReplicasAfterAppendException.
- Spring Kafka bọc lỗi producer trong KafkaProducerException hoặc một ngoại lệ gửi bản tin tương ứng với phiên bản thư viện.
- Tỷ lệ gửi thành công giảm, retry tăng và thời gian chờ gửi kéo dài.
- Consumer có thể giảm tốc độ nhận dữ liệu vì producer không ghi thêm được; consumer lag tăng có thể là hệ quả, không nhất thiết là nguyên nhân.
- Metric UnderMinIsrPartitionCount tăng hoặc ISR shrink xuất hiện liên tục.

Phân biệt với các lỗi gần giống:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| NotEnoughReplicas | ISR nhỏ hơn min.insync.replicas |
| NotEnoughReplicasAfterAppend | ISR giảm dưới ngưỡng sau khi bản ghi đã append |
| NotLeaderOrFollower | Producer hoặc client gửi yêu cầu tới broker không còn là leader hợp lệ hoặc broker không phải replica của partition |
| LeaderNotAvailable | Partition hiện không có leader khả dụng |
| TimeoutException | Có thể do broker, mạng, request queue hoặc replication chậm; cần đối chiếu log và metric để tìm nguyên nhân gốc |

NotEnoughReplicas là lỗi phía ghi. Nếu consumer báo lỗi đọc hoặc lag cao, hãy kiểm tra riêng trạng thái leader, fetch, rebalance và tốc độ xử lý; đừng kết luận consumer gây ra thiếu ISR chỉ từ lag.

## 3. Quy trình chẩn đoán từng bước

### Bước 1: Xác định topic và partition bị ảnh hưởng

Từ log ứng dụng, lấy topic, partition, thời điểm lỗi và exception gốc. Nếu producer gửi nhiều topic, hãy nhóm lỗi theo topic và partition để biết sự cố tập trung ở một partition, một broker hay toàn cụm.

Mô tả topic:

    kafka-topics.sh \
      --bootstrap-server kafka-1:9092 \
      --describe \
      --topic orders

Kết quả hiển thị leader, replicas và ISR cho từng partition. Ví dụ:

    Topic: orders  Partition: 4  Leader: 1
    Replicas: 1,2,3  Isr: 1,2

Partition này có replication factor 3 nhưng chỉ có 2 replica trong ISR. Nếu min.insync.replicas là 2, ghi vẫn có thể hoạt động. Nếu một follower nữa rời ISR, ghi với acks=all sẽ bị từ chối.

Nếu leader hiển thị -1 hoặc partition không có leader, xử lý đây là sự cố leader/offline partition trước. Khi đó nguyên nhân và quy trình khôi phục khác với trường hợp leader vẫn hoạt động nhưng ISR không đủ.

### Bước 2: Đọc cấu hình thực tế của topic

Kiểm tra cấu hình topic, đặc biệt là min.insync.replicas:

    kafka-configs.sh \
      --bootstrap-server kafka-1:9092 \
      --entity-type topics \
      --entity-name orders \
      --describe

Nếu topic không có cấu hình ghi đè, giá trị hiệu lực có thể đến từ cấu hình mặc định broker. Kiểm tra cấu hình broker đang áp dụng qua công cụ quản trị và cấu hình triển khai của cụm. Đừng suy ra giá trị hiệu lực chỉ từ file cấu hình của một broker; các broker có thể có cấu hình khác nhau hoặc cấu hình động.

Đối chiếu ba thông tin:

1. Replication factor của topic.
2. Số replica hiện có trong ISR của partition lỗi.
3. min.insync.replicas hiệu lực tại thời điểm xảy ra lỗi.

Nếu min.insync.replicas lớn hơn replication factor, topic không thể đáp ứng ngưỡng khi dùng acks=all. Nếu min ISR bằng replication factor, chỉ cần một replica rời ISR là ghi bị chặn. Hãy xác nhận đây có phải chủ đích về độ bền hay là cấu hình quá chặt so với năng lực vận hành.

### Bước 3: Kiểm tra broker đang giữ replica ngoài ISR

Đối chiếu danh sách replicas với ISR để tìm broker có follower không theo kịp. Kiểm tra:

- Broker có đang chạy và còn kết nối tới cluster hay không.
- Log broker có lỗi ổ đĩa, thư mục log offline, quyền truy cập hoặc lỗi I/O không.
- Dung lượng đĩa còn đủ không; có phân vùng nào gần đầy hoặc bị read-only không.
- Mạng giữa leader và follower có mất gói, độ trễ cao hoặc giới hạn băng thông không.
- CPU, garbage collection, page cache và tải request có khiến broker không fetch kịp không.
- Log có lỗi xác thực, TLS, DNS hoặc kết nối giữa các broker không.

Nếu broker bị dừng, khôi phục tiến trình và xác nhận broker gia nhập cluster. Nếu broker chạy nhưng follower không bắt kịp, xem log replication/fetcher và tài nguyên của cả leader lẫn follower. Leader quá tải cũng có thể làm follower fetch chậm.

### Bước 4: Kiểm tra metric và xu hướng

Theo dõi các metric broker thường dùng:

| Metric | Dấu hiệu cần chú ý |
|---|---|
| UnderReplicatedPartitions | Partition có replica chưa theo kịp hoặc chưa đủ trạng thái đồng bộ |
| UnderMinIsrPartitionCount | Partition có ISR thấp hơn min.insync.replicas |
| IsrShrinksPerSec | ISR liên tục giảm, gợi ý follower chậm hoặc mất kết nối |
| IsrExpandsPerSec | Replica bắt kịp và được thêm lại vào ISR |
| OfflinePartitionsCount | Partition không có leader khả dụng |
| RequestHandlerAvgIdlePercent | Broker có thể thiếu năng lực xử lý request nếu mức nhàn rỗi thấp kéo dài |
| NetworkProcessorAvgIdlePercent | Network processor có thể quá tải nếu mức nhàn rỗi thấp kéo dài |

Metric cần được xem theo broker, topic/partition nếu hệ thống giám sát hỗ trợ, và theo thời gian. Một lần ISR shrink ngắn rồi expand có thể là dao động tạm thời; ISR shrink liên tục trên cùng broker thường gợi ý lỗi tài nguyên hoặc kết nối dai dẳng.

Tên metric và cách expose có thể khác giữa phiên bản Kafka hoặc hệ thống giám sát. Hãy đối chiếu JMX MBean và dashboard đang triển khai thay vì giả định mọi bản phát hành đều có cùng bộ metric.

### Bước 5: Kiểm tra metadata quorum nếu cụm dùng KRaft

Trong KRaft, controller quorum quản lý metadata và trạng thái cluster; ISR của partition là trạng thái replication dữ liệu giữa các broker. Đây là hai lớp khác nhau.

Nếu broker mất kết nối controller hoặc metadata quorum không ổn định, thao tác metadata và khả năng điều phối leader có thể bị ảnh hưởng. Hãy kiểm tra sức khỏe controller quorum cùng với log broker. Không nên xem việc quorum controller khỏe là bằng chứng rằng mọi partition đều có đủ ISR; cũng không nên xem một partition thiếu ISR là bằng chứng quorum KRaft đã lỗi.

## 4. Nguyên nhân thường gặp và cách xử lý

| Nguyên nhân | Dấu hiệu | Hướng khắc phục |
|---|---|---|
| Broker dừng hoặc restart liên tục | Replica trên broker đó rời ISR; nhiều partition cùng bị ảnh hưởng | Khôi phục broker, kiểm tra log và nguyên nhân restart |
| Đĩa đầy hoặc I/O chậm | Lỗi log directory, fetch chậm, nhiều replica trên cùng ổ đĩa bị ảnh hưởng | Giải phóng hoặc mở rộng dung lượng theo quy trình vận hành; xử lý thiết bị lỗi |
| Mạng broker không ổn định | ISR shrink/expand lặp lại, lỗi kết nối hoặc fetch timeout | Kiểm tra DNS, route, firewall, packet loss, băng thông và độ trễ |
| Leader quá tải | Nhiều follower của cùng leader tụt hậu, request latency tăng | Giảm tải, bổ sung năng lực, phân bố lại partition nếu cần |
| Follower quá tải | Chỉ replica trên một broker chậm trên nhiều partition | Điều tra CPU, GC, đĩa, network và số partition đặt trên broker |
| Reassignment kéo dài | Replica mới chưa bắt kịp, ISR thiếu trong khi di chuyển | Theo dõi reassignment, bảo đảm broker đích đủ tài nguyên và mạng |
| Cấu hình min ISR quá cao | ISR ổn định nhưng thấp hơn ngưỡng đã đặt | Điều chỉnh ngưỡng sau khi đánh giá yêu cầu độ bền và rủi ro |
| Replication factor thấp | Ít bản sao, mất một broker đã ảnh hưởng nhiều partition | Tăng replication factor có kế hoạch và phân bố replica trên broker/rack phù hợp |

Không hạ min.insync.replicas ngay khi thấy lỗi. Thay đổi này có thể làm ghi tiếp tục nhưng đồng thời giảm mức bảo vệ dữ liệu. Trước khi điều chỉnh, cần xác định số replica còn lại, replication factor, mức độ quan trọng của dữ liệu và khả năng chấp nhận rủi ro mất dữ liệu.

### Khôi phục follower

Khi broker và tài nguyên đã ổn định:

1. Xác nhận broker tham gia cluster và thư mục log của replica ở trạng thái khả dụng.
2. Kiểm tra leader hiện tại và follower cần bắt kịp.
3. Theo dõi log replication/fetcher để chắc chắn follower đang lấy dữ liệu.
4. Quan sát ISR shrink/expand và mô tả topic cho đến khi follower trở lại ISR.
5. Kiểm tra UnderReplicatedPartitions và UnderMinIsrPartitionCount giảm về mức kỳ vọng.
6. Gửi bản tin kiểm chứng có kiểm soát và xác nhận producer nhận thành công với cấu hình acks dự kiến.

Nếu cần di chuyển replica, dùng quy trình partition reassignment có kế hoạch. Đánh giá dung lượng, rack awareness, tải mạng và tiến độ đồng bộ trước khi chuyển bước tiếp theo. Không xóa thủ công thư mục log của replica để ép Kafka tạo lại dữ liệu; thao tác đó có thể phá hủy bản sao cần phục hồi.

### Khi nào cần thay đổi min.insync.replicas?

Chỉ cân nhắc hạ ngưỡng khi tổ chức chấp nhận rõ ràng việc giảm số bản sao xác nhận. Ví dụ, replication factor 3 và min ISR 2 thường cho phép tiếp tục ghi khi một replica rời ISR. Hạ min ISR xuống 1 sẽ cho phép ghi khi chỉ còn leader trong ISR, nhưng khi đó producer nhận xác nhận dù không còn bản sao follower đồng bộ cùng tham gia.

Nếu quyết định thay đổi, thực hiện có kiểm soát:

- Ghi nhận giá trị hiện tại và lý do thay đổi.
- Xác định phạm vi topic cần áp dụng; tránh thay đổi mặc định toàn cụm nếu chỉ một topic bị ảnh hưởng.
- Xác nhận producer vẫn dùng acks=all nếu yêu cầu là tận dụng ngưỡng min ISR.
- Theo dõi số ISR, replica phục hồi và lỗi producer.
- Khôi phục ngưỡng ban đầu sau khi nguyên nhân gốc đã được xử lý nếu việc hạ ngưỡng chỉ là biện pháp tạm thời.

Không bật unclean leader election chỉ để làm partition có leader trở lại nhanh hơn. Bầu một replica ngoài ISR có thể làm mất các bản ghi đã được xác nhận trước đó. Chỉ sử dụng khi chính sách phục hồi cho phép đánh đổi độ bền dữ liệu để lấy tính sẵn sàng, và người vận hành hiểu rõ hậu quả.

## 5. Cấu hình producer Java và Spring Kafka

Với dữ liệu quan trọng, một cấu hình thường gặp là replication factor 3, min.insync.replicas 2 và producer acks=all. Cấu hình này cho phép ghi khi có ít nhất hai replica trong ISR và từ chối ghi khi ISR giảm còn một.

Ví dụ tạo topic:

    kafka-topics.sh \
      --bootstrap-server kafka-1:9092 \
      --create \
      --topic orders \
      --partitions 12 \
      --replication-factor 3 \
      --config min.insync.replicas=2

Với topic đã tồn tại, kiểm tra cấu hình trước khi cập nhật. Cấu hình topic có thể được điều chỉnh bằng kafka-configs:

    kafka-configs.sh \
      --bootstrap-server kafka-1:9092 \
      --entity-type topics \
      --entity-name orders \
      --alter \
      --add-config min.insync.replicas=2

Đây là ví dụ cấu hình; chọn số partition, replication factor và min ISR theo số broker, yêu cầu throughput, rack layout và mục tiêu phục hồi thực tế.

### Producer Java

    Properties props = new Properties();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30000);

    KafkaProducer<String, String> producer = new KafkaProducer<>(props);

Idempotence giúp producer xử lý retry an toàn hơn trong phạm vi session producer và các điều kiện cấu hình được Kafka hỗ trợ. Nó không thay thế idempotency của nghiệp vụ, không chống trùng khi ứng dụng tạo một event mới để gửi lại sau khi process khởi động lại, và không biến thao tác ghi Kafka cùng cập nhật database thành một transaction phân tán.

Hãy chọn delivery.timeout.ms và request.timeout.ms dựa trên latency, thời gian retry và SLA của ứng dụng. Timeout quá ngắn có thể khiến producer trả lỗi trong khi broker vẫn đang phục hồi; timeout quá dài làm lỗi lan truyền chậm và giữ request lâu hơn. Không tăng timeout một cách mù quáng khi nguyên nhân là replica bị mất hoặc broker không còn đủ ISR.

### Spring Kafka

Với Spring Boot, cấu hình producer có thể khai báo trong application.yml:

    spring:
      kafka:
        producer:
          acks: all
          properties:
            enable.idempotence: true
            delivery.timeout.ms: 120000
            request.timeout.ms: 30000

Khi gửi bằng KafkaTemplate, xử lý lỗi từ future hoặc callback. Không chỉ ghi log rồi bỏ qua kết quả gửi:

    kafkaTemplate.send("orders", orderId, event)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Ghi nhận topic, key, eventId và nguyên nhân gốc.
                // Chuyển sang retry có kiểm soát hoặc báo lỗi cho caller.
                handleSendFailure(event, error);
                return;
            }

            // Có thể ghi nhận partition và offset để phục vụ trace.
            RecordMetadata metadata = result.getRecordMetadata();
            recordPublishSuccess(event.eventId(),
                    metadata.partition(), metadata.offset());
        });

Tên kiểu trả về và API callback có thể khác theo phiên bản Spring Kafka; điều quan trọng là phải quan sát hoàn tất bất đồng bộ và không coi lời gọi send() là bằng chứng bản tin đã được broker xác nhận.

### Retry ở tầng ứng dụng

Không retry vô hạn với vòng lặp chặt. Dùng retry có giới hạn, backoff tăng dần và jitter để tránh nhiều producer đồng loạt dồn tải vào cluster đang phục hồi. Khi hết số lần thử, chuyển lỗi tới cơ chế xử lý phù hợp như outbox, hàng đợi retry riêng hoặc trạng thái chờ xử lý.

Với lỗi sau append, kết quả ghi có thể chưa rõ ràng ở góc nhìn ứng dụng. Dùng cùng event id cho mọi lần thử và thiết kế consumer/lưu trữ đích có khả năng khử trùng. Nếu dùng transactional producer, phân biệt lỗi có thể retry, lỗi cần khởi tạo lại transaction và lỗi yêu cầu ứng dụng dừng luồng xử lý; tuân theo trạng thái transaction của client.

## 6. Runbook xử lý sự cố

Khi cảnh báo NotEnoughReplicas hoặc UnderMinIsrPartitionCount xuất hiện, thực hiện theo trình tự:

1. **Khoanh vùng:** lấy topic, partition, leader, replicas, ISR và thời điểm lỗi từ log producer.
2. **Đọc cấu hình:** xác nhận replication factor, min.insync.replicas hiệu lực và acks của producer.
3. **Xác định broker lỗi:** kiểm tra broker giữ replica ngoài ISR, log, dung lượng đĩa, I/O, CPU và mạng.
4. **Phân loại:** xác định partition còn leader hay đã offline; kiểm tra KRaft quorum riêng nếu cụm có vấn đề metadata.
5. **Khôi phục nguyên nhân:** đưa broker/tài nguyên/kết nối về trạng thái ổn định; theo dõi follower bắt kịp và trở lại ISR.
6. **Xác minh:** kiểm tra ISR đạt ngưỡng, metric under-min-ISR giảm, producer gửi thử thành công và consumer tiếp tục xử lý.
7. **Đóng sự cố:** lưu thời điểm, partition ảnh hưởng, nguyên nhân, cấu hình thay đổi và biện pháp phòng ngừa.

Trong lúc sự cố diễn ra, tránh đồng thời thay đổi replication factor, min ISR, leader election và reassignment. Thay đổi quá nhiều biến cùng lúc làm khó xác định nguyên nhân và tăng nguy cơ mất dữ liệu.

## 7. Kịch bản thực hành

Giả sử topic orders có replication factor 3 và min.insync.replicas 2. Producer dùng acks=all.

**Tình huống A: một follower ngừng hoạt động.** ISR giảm từ 3 xuống 2. Producer vẫn có thể ghi vì ISR đạt ngưỡng. Hệ thống cần cảnh báo vì mức dự phòng đã giảm; nếu thêm một replica rời ISR, ghi sẽ bị từ chối.

**Tình huống B: hai follower không còn trong ISR.** ISR chỉ còn leader. Producer nhận NotEnoughReplicasException khi broker kiểm tra điều kiện ghi. Khôi phục broker/follower và chờ chúng bắt kịp trước khi xác nhận sự cố đã kết thúc.

**Tình huống C: ISR giảm trong lúc ghi.** Broker có thể trả NotEnoughReplicasAfterAppendException. Điều tra trạng thái partition tại đúng thời điểm ghi; khi xử lý retry nghiệp vụ, dùng event id ổn định vì bản ghi có thể đã được append trên leader.

**Tình huống D: partition không có leader.** Producer thường nhận lỗi leader hoặc metadata liên quan. Kiểm tra replica có thể bầu làm leader theo chính sách election và trạng thái broker. Không xử lý tình huống này bằng cách chỉ hạ min.insync.replicas, vì min ISR không tạo ra leader.

## 8. Checklist phòng ngừa

- [ ] Replication factor phù hợp với số broker và yêu cầu độ bền dữ liệu.
- [ ] min.insync.replicas không lớn hơn replication factor và có chủ đích vận hành rõ ràng.
- [ ] Producer của dữ liệu quan trọng dùng acks=all.
- [ ] Idempotence được bật và cấu hình tương thích với Kafka client đang dùng.
- [ ] Broker có dung lượng đĩa, CPU, mạng và I/O đủ cho replication.
- [ ] Replica được phân bố qua rack hoặc vùng lỗi theo thiết kế cụm.
- [ ] Có cảnh báo cho UnderReplicatedPartitions, UnderMinIsrPartitionCount, ISR shrink và offline partition.
- [ ] Log broker và producer có đủ topic, partition, broker id và event id để điều tra.
- [ ] Retry có giới hạn, backoff và cơ chế khử trùng ở tầng nghiệp vụ.
- [ ] Runbook phân biệt thiếu ISR, mất leader và lỗi metadata quorum.
- [ ] Quy trình reassignment và phục hồi broker đã được diễn tập.

Khi hiểu quan hệ giữa ISR và min.insync.replicas, đội vận hành có thể xác định vì sao Kafka từ chối ghi, chọn cách khôi phục phù hợp và giữ nguyên mục tiêu độ bền dữ liệu. Mục tiêu không chỉ là làm producer hết lỗi, mà là đưa replica trở lại trạng thái đồng bộ và chứng minh cụm đáp ứng lại chính sách xác nhận đã đặt ra.
