# Load test với partition thực tế

Load test Kafka chỉ có giá trị khi cấu trúc topic, cách phân phối key, số consumer và mức xử lý dữ liệu gần với môi trường vận hành. Một bài test dùng topic 3 partition, payload nhỏ và consumer chỉ đọc rồi bỏ dữ liệu có thể cho throughput rất cao, nhưng kết quả đó không dự báo được năng lực của hệ thống đang chạy 24 partition, có key nóng và phải ghi dữ liệu xuống database.

Mục tiêu của bài test là tìm mức tải mà toàn bộ pipeline có thể duy trì trong thời gian đủ dài, với độ trễ và consumer lag nằm trong SLO, đồng thời vẫn có dư địa cho burst và sự cố thông thường. Kết quả phải trả lời được: hệ thống xử lý ổn định bao nhiêu record hoặc byte mỗi giây, bottleneck nằm ở producer, broker, consumer hay dịch vụ phụ trợ, và cần bao nhiêu partition cùng consumer để đáp ứng tải dự kiến.

## 1. Vì sao phải test với số partition thực tế?

Partition là đơn vị lưu trữ và phân phối song song của Kafka. Trong một consumer group, tại một thời điểm, mỗi partition chỉ được gán cho tối đa một consumer. Vì vậy, số consumer có thể xử lý song song trong group bị giới hạn bởi số partition được gán.

Ví dụ, topic có 12 partition:

- Một instance ứng dụng với concurrency 4 tạo ra tối đa 4 consumer trong group.
- Ba instance, mỗi instance concurrency 4, có thể tạo tổng cộng 12 consumer và sử dụng hết 12 partition.
- Bốn instance, mỗi instance concurrency 4, tạo 16 consumer; tối đa 12 consumer nhận partition, 4 consumer còn lại không có partition để đọc.

Concurrency trong Spring Kafka là số consumer thread do listener container tạo ra. Khi chạy nhiều pod hoặc instance, cần tính tổng consumer của tất cả instance trong cùng group:

**Tổng consumer = số instance × concurrency mỗi instance**

Số consumer có thể hoạt động song song không vượt quá số partition đang được group sử dụng. Tăng concurrency vượt số partition không làm tăng khả năng xử lý của group; nó còn tạo thêm consumer và làm việc quản lý group phức tạp hơn.

Số partition cũng ảnh hưởng đến cách producer phân phối record. Nếu producer gửi record có key, partitioner thường đưa cùng một key về cùng partition để giữ thứ tự theo key. Một key xuất hiện quá thường xuyên có thể làm một partition trở thành điểm nóng, trong khi các partition khác còn nhiều năng lực. Nếu test chỉ dùng key ngẫu nhiên hoặc phân phối đều, hiện tượng lệch tải trong production sẽ không xuất hiện.

Tăng số partition cũng không phải giải pháp miễn phí. Mỗi partition có metadata, log segment, index và hoạt động replica cần broker quản lý. Việc tăng partition có thể làm thay đổi cách ánh xạ key sang partition đối với các record mới; do đó, thứ tự của cùng một key qua ranh giới thời gian có thể không còn nằm trên cùng một partition như trước. Hãy chọn số partition theo nhu cầu song song, throughput đã đo và giới hạn vận hành, sau đó kiểm chứng bằng test.

## 2. Mô tả workload giống production

Trước khi chạy, hãy viết rõ workload mà bài test cần đại diện. Chỉ ghi “1.000 record/giây” là chưa đủ vì chi phí xử lý còn phụ thuộc kích thước record, số key, độ phân bố key, kiểu dữ liệu và công việc của consumer.

| Thuộc tính | Cần xác định |
|---|---|
| Throughput | Tải trung bình, tải giờ cao điểm, burst và tốc độ tăng tải |
| Kích thước record | Phân bố payload nhỏ, trung bình, lớn; số byte sau serialization |
| Key | Key có thực sự được dùng không, số lượng key và tần suất của từng key |
| Phân bố | Đồng đều hay lệch; có hot key hoặc nhóm key chiếm phần lớn traffic không |
| Loại sự kiện | Tỷ lệ từng loại event, header, schema và kích thước trường |
| Producer | Số ứng dụng, số producer, tốc độ gửi và cấu hình batching |
| Consumer | Số instance, concurrency, xử lý đồng bộ hay bất đồng bộ |
| Xử lý phụ trợ | Gọi API, truy vấn database, ghi cache, xử lý nghiệp vụ hoặc publish tiếp |
| Độ trễ | Thời gian chấp nhận được từ lúc gửi đến lúc nghiệp vụ hoàn tất |

Dùng phân bố dữ liệu thực tế hoặc dữ liệu tổng hợp có cùng đặc tính. Không cần sao chép dữ liệu nhạy cảm từ production. Nếu payload production có nhiều kích thước, hãy tạo dữ liệu test có phân bố tương tự thay vì chỉ dùng một record cố định. Nếu một số key nhận phần lớn lưu lượng, hãy giữ tỷ lệ đó trong test.

Đặc biệt, cần phân biệt ba loại độ trễ:

1. **Producer send latency:** thời gian producer chờ Kafka xác nhận record.
2. **Consumer processing latency:** thời gian consumer xử lý một record hoặc một batch.
3. **End-to-end latency:** thời gian từ lúc event được tạo hoặc gửi đến lúc tác vụ nghiệp vụ hoàn tất.

Producer có thể gửi rất nhanh trong khi consumer lag tăng liên tục. Chỉ đo tốc độ gửi sẽ che khuất tình trạng pipeline không theo kịp.

## 3. Chuẩn bị môi trường và topic

Môi trường test nên khớp các thuộc tính ảnh hưởng trực tiếp đến năng lực Kafka:

- Cùng số partition của topic production hoặc đúng số partition dự kiến sau khi mở rộng.
- Cùng replication factor và chính sách durability, gồm producer acknowledgment và min.insync.replicas.
- Số broker, loại ổ đĩa, giới hạn I/O, network và phiên bản Kafka tương đương.
- Cấu hình retention, compression, TLS, authentication và quota tương đương khi các yếu tố đó có mặt trong production.
- Cùng phiên bản ứng dụng, serializer, producer/consumer config và cách triển khai instance.
- Cùng loại database hoặc dịch vụ phụ trợ, connection pool và giới hạn tài nguyên nếu chúng nằm trong đường xử lý.

Nếu không thể tái tạo đầy đủ production, hãy ghi rõ khác biệt. Không ngoại suy kết quả từ một broker đơn lẻ sang cluster nhiều broker có replication mà không có phép đo bổ sung.

Tạo topic test riêng trên cluster dành cho load test. Ví dụ dưới đây tạo topic 24 partition, replication factor 3:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --create \
  --topic orders-load-test \
  --partitions 24 \
  --replication-factor 3
~~~

Kiểm tra cấu trúc topic và replica:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders-load-test
~~~

Đối chiếu số partition, leader và replica với cấu hình mục tiêu trước khi chạy. Nếu môi trường dùng TLS hoặc SASL, bổ sung file cấu hình client bằng tùy chọn command config phù hợp.

Không chạy load test trên topic production nếu chưa có kế hoạch được phê duyệt. Tải test có thể chiếm CPU, network, disk I/O, connection và quota dùng chung; dữ liệu thử cũng có thể kích hoạt consumer nghiệp vụ thật nếu dùng nhầm topic hoặc group.

## 4. Cấu hình ứng dụng cần giữ nhất quán

Ví dụ cấu hình Spring Boot dưới đây minh họa các thuộc tính thường cần cố định khi đo. Giá trị chỉ là điểm bắt đầu; hãy thay bằng cấu hình thực tế của hệ thống cần đánh giá.

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092,broker3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 5
        batch.size: 65536
        compression.type: lz4
    consumer:
      group-id: orders-load-test
      enable-auto-commit: false
      max-poll-records: 500
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 12
      ack-mode: batch
~~~

Các điểm cần chú ý:

- **acks và replication:** nếu production dùng acks=all và replication factor 3, test với acks=1 hoặc replication factor 1 sẽ đo một hệ thống có mức durability và chi phí khác.
- **Idempotence và retry:** giữ cấu hình producer tương đương production. Retry có thể làm tăng thời gian gửi và thay đổi thứ tự quan sát được nếu cấu hình không phù hợp.
- **Batching và compression:** linger.ms, batch.size và compression.type ảnh hưởng đến throughput, CPU, kích thước network và độ trễ. Hãy đo với cấu hình production trước, sau đó thay từng biến trong các lượt benchmark riêng.
- **Consumer polling:** max.poll.records và max.poll.interval.ms phải phù hợp với thời gian xử lý. Nếu xử lý một batch quá lâu, consumer có thể vượt poll interval và bị xem là không còn hoạt động, dẫn đến rebalance.
- **Acknowledgment và commit:** giữ ack mode, transaction và cách commit giống ứng dụng thật. Thay đổi các thiết lập này có thể làm khác độ trễ, khả năng phát lại và ngữ nghĩa xử lý.

Nếu production dùng Kafka transaction hoặc exactly-once semantics, test phải bao gồm đường xử lý transaction đó. Một consumer chỉ đọc record rồi commit nhanh không thể đại diện cho consumer phải xử lý nghiệp vụ và commit transaction.

Trong Spring Kafka, tổng concurrency cần được tính trên mọi instance. Ví dụ 3 pod với concurrency 4 tạo 12 consumer trong cùng group. Nếu topic có 24 partition, group có thể còn partition chưa được sử dụng hết; nếu có 8 pod, concurrency 4, chỉ tối đa 24 consumer nhận partition trong cùng thời điểm.

## 5. Chạy baseline để tách năng lực Kafka khỏi năng lực ứng dụng

Nên đo từng tầng trước khi chạy bài test tích hợp. Công cụ benchmark đi kèm Kafka hữu ích để tạo mốc tham chiếu cho broker:

~~~bash
kafka-producer-perf-test.sh \
  --topic orders-load-test \
  --num-records 1000000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props \
    bootstrap.servers=broker1:9092 \
    acks=all \
    linger.ms=5 \
    batch.size=65536 \
    compression.type=lz4
~~~

Đo consumer baseline trên cùng topic:

~~~bash
kafka-consumer-perf-test.sh \
  --bootstrap-server broker1:9092 \
  --topic orders-load-test \
  --messages 1000000 \
  --group orders-perf-baseline \
  --from-beginning
~~~

Các công cụ perf test tạo baseline hữu ích nhưng workload của chúng thường đơn giản hơn ứng dụng thật. Producer perf test với record cố định không đại diện cho phân bố key, payload và callback của ứng dụng. Consumer perf test cũng không đại diện cho xử lý nghiệp vụ, database hoặc API. Vì vậy, hãy dùng chúng để tìm giới hạn tương đối của broker, sau đó chạy load generator và consumer ứng dụng thật để đo end-to-end.

Trong bài test tích hợp, nên ghi nhận số record theo partition từ producer metadata hoặc metric của ứng dụng. Một producer callback có thể lấy partition được Kafka chọn cho mỗi record:

~~~java
producer.send(new ProducerRecord<>(topic, key, payload), (metadata, exception) -> {
    if (exception != null) {
        sendErrorCounter.increment();
        return;
    }

    sentByPartition
        .computeIfAbsent(metadata.partition(), ignored -> new LongAdder())
        .increment();
});
~~~

Đây là cách quan sát phân bố record theo partition trong load generator. Trong ứng dụng thật, hãy dùng metric có cardinality được kiểm soát; tránh tạo label theo key hoặc ID của từng record.

## 6. Thiết kế các lượt load test

Một lượt test tốt có các giai đoạn riêng để phân biệt warm-up, tải ổn định, burst và khả năng phục hồi. Giữ nguyên cấu hình giữa các lượt so sánh; chỉ thay một nhóm biến có chủ đích.

### 6.1. Warm-up và baseline

Khởi động producer, consumer và các dịch vụ phụ trợ. Chờ cache, connection pool, JVM JIT và các thành phần nền ổn định. Ghi lại metric khi chưa có tải đáng kể để biết mức nền của CPU, memory, network và lag.

Sau đó chạy tải thấp trong vài phút. Xác nhận record được phân phối lên đúng các partition, consumer group được gán như dự kiến, không có lỗi serialization, authentication hoặc commit.

### 6.2. Ramp-up và tải ổn định

Tăng dần tải theo các mức, chẳng hạn 10%, 25%, 50%, 75%, 100% và 120% tải mục tiêu. Mỗi mức cần giữ đủ lâu để quan sát xu hướng, không chỉ đọc một mẫu throughput tức thời. Thời gian giữ có thể bắt đầu từ 15–30 phút và tăng lên nếu hệ thống có chu kỳ xử lý dài.

Ở mỗi mức, ghi nhận:

- Producer throughput theo record/giây và byte/giây.
- Producer send latency p50, p95, p99 và tỷ lệ send error.
- Consumer throughput, processing latency và lag theo từng partition.
- End-to-end latency từ thời điểm tạo event đến khi hoàn tất xử lý.
- Broker CPU, disk I/O, network, request queue và trạng thái replica.
- Tài nguyên của ứng dụng và dịch vụ phụ trợ.

Một mức tải chỉ được xem là ổn định khi consumer theo kịp producer, lag không tăng đều theo thời gian, độ trễ không vượt SLO và lỗi không tăng bất thường.

### 6.3. Burst và recovery

Tạo một đợt tải cao hơn mức bình thường trong khoảng thời gian đã định, sau đó đưa tải về mức thường. Mục đích là quan sát lượng backlog hình thành, thời gian consumer xử lý hết backlog và mức độ ổn định sau burst.

Đừng chỉ ghi nhận throughput đỉnh. Hãy đo **recovery time**: thời gian từ khi tải trở về bình thường đến khi lag trở lại ngưỡng mục tiêu. Nếu lag không giảm dù producer đã giảm tải, consumer hoặc dịch vụ phụ trợ có thể đang bị nghẽn.

### 6.4. Soak test

Giữ tải đại diện cho production trong thời gian dài, ví dụ 1–4 giờ hoặc lâu hơn tùy mục tiêu. Soak test giúp phát hiện vấn đề tích lũy như memory tăng dần, GC kéo dài, connection leak, disk đầy, log segment tăng nhanh, retry tích tụ hoặc consumer lag trôi lên theo thời gian.

Theo dõi cả tốc độ tăng dữ liệu trên broker và dung lượng còn lại. Retention và tốc độ ghi có thể khiến cluster đầy disk dù throughput ngắn hạn vẫn tốt.

### 6.5. Rebalance và thay đổi số consumer

Trong môi trường test riêng, lần lượt dừng một consumer, khởi động lại instance hoặc thay đổi số instance. Ghi lại:

- Thời gian group phát hiện thành viên thay đổi và hoàn tất rebalance.
- Khoảng thời gian consumer ngừng xử lý.
- Lag tăng bao nhiêu trong thời gian rebalance.
- Thời gian group trở lại throughput bình thường.
- Có duplicate, xử lý lại hoặc lỗi commit theo đúng ngữ nghĩa ứng dụng hay không.

Thử nghiệm này đặc biệt quan trọng khi concurrency lớn, số partition cao hoặc xử lý từng batch mất nhiều thời gian. Rebalance thường xuyên có thể làm throughput thực tế thấp hơn nhiều so với benchmark khi group đứng yên.

## 7. Đo partition distribution và consumer lag

Không chỉ xem tổng lag của group. Tổng lag có thể che giấu một partition bị nghẽn trong khi các partition còn lại gần như rỗng. Hãy theo dõi lag, throughput và processing time theo từng partition.

Kiểm tra group bằng công cụ Kafka:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-load-test
~~~

Kết quả thường có current offset, log end offset và lag cho từng partition. Dùng kết quả này cùng metric của ứng dụng để tìm partition nào tăng lag hoặc có tốc độ xử lý thấp.

Hãy kiểm tra ba dạng phân bố:

1. **Số record theo partition:** partition nào nhận nhiều record nhất?
2. **Số byte theo partition:** record có kích thước khác nhau có thể khiến số record cân bằng nhưng byte không cân bằng.
3. **Consumer processing time theo partition:** cùng số record nhưng payload hoặc key có thể dẫn đến chi phí xử lý khác nhau.

Nếu một partition nhận phần lớn traffic, hãy xác định key nào gây lệch và kiểm tra logic partitioner. Không tự động đổi sang key ngẫu nhiên để làm biểu đồ cân bằng: cách đó có thể phá vỡ yêu cầu ordering theo key. Nếu nghiệp vụ cần ordering, hãy đánh giá lại thiết kế key, cách phân vùng dữ liệu hoặc xử lý riêng nhóm key nóng.

Consumer lag là chênh lệch offset giữa record cuối trên broker và offset consumer đã xử lý hoặc commit, tùy công cụ và cơ chế commit. Lag không trực tiếp bằng thời gian trễ nghiệp vụ. Để đo tuổi của event, hãy ghi timestamp tạo event và timestamp hoàn tất xử lý, rồi tính end-to-end latency. Cả lag và tuổi event đều hữu ích nhưng trả lời hai câu hỏi khác nhau.

## 8. Các metric cần quan sát

| Thành phần | Metric cần theo dõi | Dấu hiệu cần điều tra |
|---|---|---|
| Producer | Records/sec, bytes/sec, send latency, retry, error, buffer wait | Send latency tăng, retry nhiều hoặc producer phải chờ buffer |
| Broker | CPU, disk I/O, network, request handler idle, request queue, produce/fetch latency | CPU hoặc disk bão hòa, request queue tăng, thời gian xử lý request kéo dài |
| Replica | Under-replicated partitions, ISR shrink/expand, replica fetch lag | Replica tụt lại hoặc ISR thay đổi liên tục |
| Consumer | Records/sec, processing time, poll interval, commit error, rebalance, lag từng partition | Lag tăng đều, xử lý chậm, poll timeout hoặc rebalance lặp lại |
| Ứng dụng | CPU, heap, GC pause, thread pool, connection pool, exception | Thread bị chặn, GC dài, pool cạn hoặc exception tăng |
| Dịch vụ phụ trợ | DB latency, query rate, connection usage, API latency và error | Consumer chờ downstream, làm giảm tốc độ poll và xử lý |

Với broker, cần quan sát cả tải theo node và theo partition/leader. Một broker có thể trở thành điểm nóng nếu giữ nhiều leader của các partition có traffic cao. Với consumer, cần xem partition assignment và processing time bên cạnh lag để phân biệt thiếu consumer với một partition có workload nặng.

Nếu hệ thống dùng Micrometer hoặc hệ thống giám sát khác, thống nhất tên metric, đơn vị và khoảng lấy mẫu giữa các lượt test. Giữ dashboard và log ở cùng mốc thời gian với load generator để có thể đối chiếu nguyên nhân khi latency hoặc lag thay đổi.

## 9. Ước lượng capacity từ kết quả

Hãy dùng throughput ổn định đã đo trong điều kiện gần production, không dùng throughput đỉnh trong vài giây. Với một workload cụ thể, có thể ước lượng ban đầu số partition cần thiết:

~~~text
partition cần thiết
    = ceil(throughput mục tiêu / throughput an toàn đã đo trên mỗi partition)
~~~

Ví dụ, nếu một partition duy trì được 800 record/giây với payload, replication và xử lý consumer đã chọn, còn tải mục tiêu là 12.000 record/giây, phép chia ban đầu cho ra 15 partition. Đây chỉ là ước lượng. Throughput của partition không hoàn toàn độc lập vì các partition dùng chung CPU, network, disk và broker. Cần test lại với tổng số partition dự kiến, replication factor thực tế, phân bố key và số consumer thực tế.

Nên chừa headroom cho peak, burst, rebalance, broker bảo trì và tăng trưởng traffic. Mức headroom phải dựa trên SLO, biến động tải và thời gian cần để mở rộng hệ thống; không có một tỷ lệ cố định phù hợp với mọi workload.

Khi báo cáo capacity, nêu rõ:

- Throughput ổn định theo record/giây và byte/giây.
- p95/p99 producer latency và end-to-end latency.
- Consumer lag bình thường, lag cao nhất và recovery time sau burst.
- Số partition, replication factor, số broker và cấu hình topic.
- Số producer, số consumer, số instance và concurrency mỗi instance.
- Kích thước record, phân bố key, compression và cấu hình acknowledgment.
- Tài nguyên broker, ứng dụng và downstream tại mức tải đó.
- Bottleneck quan sát được và điều kiện khiến kết quả không còn áp dụng.

## 10. Cách đọc kết quả và tìm bottleneck

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Producer latency tăng, broker CPU hoặc request queue cao | Broker hoặc network đang gần giới hạn |
| Producer gửi nhanh nhưng lag tăng liên tục | Consumer hoặc downstream không theo kịp |
| Một partition lag cao, partition khác thấp | Hot key, phân bố key lệch hoặc xử lý không đồng đều |
| Tăng consumer nhưng throughput không đổi | Đã chạm giới hạn partition, broker hoặc downstream |
| Consumer thường xuyên rebalance | Xử lý batch quá lâu, poll interval không phù hợp, instance không ổn định hoặc group có churn |
| Broker disk I/O cao, replica lag tăng | Disk hoặc replication đang giới hạn throughput |
| Consumer CPU thấp nhưng processing time cao | Có thể đang chờ DB, API, lock hoặc connection pool |
| Throughput ban đầu tốt rồi giảm dần | Kiểm tra GC, memory, disk growth, connection leak, retry và backlog downstream |

Thay đổi từng yếu tố trong các lượt test có kiểm soát. Ví dụ, nếu nghi ngờ concurrency, giữ nguyên producer rate, payload, partition count và broker config rồi chỉ thay concurrency. Nếu đồng thời tăng partition, tăng consumer và đổi batch size, sẽ khó xác định thay đổi nào tạo ra kết quả.

## 11. Tiêu chí hoàn tất bài test

Trước khi bắt đầu, xác định tiêu chí chấp nhận dựa trên SLO của hệ thống. Một bộ tiêu chí thường gồm:

- Đạt throughput mục tiêu trong toàn bộ khoảng giữ tải.
- Có headroom phù hợp so với peak dự kiến.
- p95 và p99 end-to-end latency nằm trong giới hạn.
- Consumer lag ổn định ở tải thường và giảm về ngưỡng chấp nhận được sau burst.
- Không có lỗi gửi, xử lý, commit hoặc retry kéo dài ở mức bất thường.
- Không có under-replicated partition kéo dài hoặc ISR liên tục co lại.
- Ứng dụng, broker và dịch vụ phụ trợ không bị bão hòa tài nguyên.
- Sau khi consumer restart hoặc rebalance, group phục hồi trong thời gian chấp nhận được.

Một bài test không đạt vẫn có giá trị nếu chỉ ra bottleneck và điều kiện tái hiện được. Hãy ghi lại tải tại thời điểm bắt đầu suy giảm, metric thay đổi đầu tiên, partition bị ảnh hưởng và thay đổi cấu hình đã thử.

## 12. Những lỗi thường làm kết quả sai lệch

1. **Dùng ít partition hơn production:** kết quả không phản ánh mức song song, leader distribution và chi phí metadata thực tế.
2. **Không mô phỏng hot key:** traffic được chia đều trong test nhưng dồn vào một partition khi chạy thật.
3. **Chỉ đo producer:** producer throughput cao không chứng minh consumer xử lý kịp.
4. **Consumer không làm nghiệp vụ:** bỏ qua chi phí serialization, validation, database, API và commit.
5. **Dùng replication hoặc acknowledgment khác:** benchmark đo một mức durability khác production.
6. **Không theo dõi lag theo partition:** tổng lag che mất partition nóng hoặc consumer chậm.
7. **Chỉ chạy vài phút:** bỏ lỡ GC, memory leak, retention, disk growth và sự suy giảm tích lũy.
8. **Thay nhiều cấu hình cùng lúc:** không thể quy kết nguyên nhân của cải thiện hoặc suy giảm.
9. **Bỏ qua rebalance:** benchmark khi group ổn định không phản ánh thời gian phục hồi khi instance thay đổi.
10. **Chạy chung môi trường với workload không kiểm soát:** nhiễu từ ứng dụng khác làm kết quả khó lặp lại.

## 13. Checklist trước khi kết luận

- [ ] Topic có đúng số partition và replication factor mục tiêu.
- [ ] Broker, phiên bản Kafka, storage, network và cấu hình durability đã được ghi lại.
- [ ] Workload có kích thước record, key distribution và tỷ lệ event gần production.
- [ ] Producer, consumer, số instance và concurrency đã được xác định.
- [ ] Đã đo baseline broker và bài test tích hợp với ứng dụng thật.
- [ ] Dashboard hiển thị throughput, latency, lag theo partition và tài nguyên downstream.
- [ ] Đã chạy ramp-up, steady-state, burst/recovery và soak test.
- [ ] Đã kiểm tra consumer restart hoặc rebalance trong môi trường test.
- [ ] Kết quả ghi rõ điều kiện test, bottleneck, SLO và headroom.

Một kết luận capacity đáng tin cậy luôn gắn với cấu hình và workload cụ thể. Khi số partition, phân bố key, replication, payload hoặc logic consumer thay đổi đáng kể, hãy chạy lại benchmark tương ứng trước khi dùng kết quả cũ để cam kết năng lực hệ thống.
