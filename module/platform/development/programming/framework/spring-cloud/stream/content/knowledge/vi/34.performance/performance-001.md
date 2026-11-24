# Xác lập mục tiêu thông lượng, độ trễ và độ tin cậy

Hiệu năng của ứng dụng Spring Cloud Stream không thể được đánh giá chỉ bằng số message xử lý trong một giây. Một hệ thống có thể đạt throughput cao nhưng để message chờ quá lâu trong queue; cũng có thể có độ trễ thấp khi tải nhỏ nhưng mất ổn định lúc traffic tăng đột biến. Khi tối ưu, cần đặt mục tiêu đồng thời cho thông lượng, độ trễ, backlog và độ tin cậy giao nhận.

Spring Cloud Stream cung cấp mô hình function, binding và binder để kết nối Supplier, Function, Consumer với Kafka, RabbitMQ hoặc Pulsar. Các thuộc tính chung như consumer concurrency, retry và batching giúp điều chỉnh ứng dụng; mỗi binder còn có các cơ chế riêng như Kafka partition, producer batch và consumer poll, hoặc RabbitMQ prefetch, consumer concurrency và acknowledgement. Không có một bộ giá trị tối ưu cho mọi binder hay mọi workload. Hãy xác định SLO, đo baseline, tìm nút thắt rồi thay đổi từng nhóm cấu hình.

## 1. Ba mục tiêu cần xác lập

### Thông lượng (throughput)

Throughput là số message được xử lý thành công trong một đơn vị thời gian, thường đo bằng message/giây (msg/s). Cần phân biệt:

- **Offered rate**: số message nguồn gửi đến hệ thống.
- **Ingress rate**: số message broker nhận và chấp nhận.
- **Processing rate**: số message consumer xử lý xong.
- **Completion rate**: số message hoàn thành toàn bộ luồng nghiệp vụ, bao gồm bước publish tiếp theo hoặc ghi dữ liệu đích.

Không dùng ingress rate làm throughput hoàn tất. Nếu producer gửi 2.000 msg/s nhưng consumer chỉ xử lý 1.500 msg/s, backlog tăng 500 message mỗi giây dù biểu đồ producer trông rất tốt.

### Độ trễ (latency)

Độ trễ là thời gian từ một mốc bắt đầu đến mốc kết thúc đã định nghĩa. Với event processing, nên theo dõi ít nhất:

- **Publish latency**: thời gian producer gửi message và nhận kết quả theo acknowledgement policy.
- **Queue wait**: thời gian message chờ trước khi được consumer xử lý.
- **Processing latency**: thời gian function thực thi logic nghiệp vụ.
- **End-to-end latency**: từ lúc event được tạo hoặc chấp nhận đến lúc kết quả cuối cùng được xác nhận.

Đo p50, p95 và p99 thay vì chỉ nhìn trung bình. p50 cho biết trải nghiệm điển hình; p95/p99 giúp phát hiện tail latency do queueing, retry, GC pause, network hoặc broker throttling. Nếu một message phải đi qua nhiều function/broker, đo cả từng chặng và toàn tuyến.

### Độ tin cậy (reliability)

Độ tin cậy mô tả hệ thống có xử lý đủ và đúng message khi gặp tải cao hoặc lỗi hay không. Hãy định lượng:

- Tỷ lệ message hoàn tất thành công.
- Số message retry, dead-letter và bị từ chối.
- Số lần redelivery/duplicate và tỷ lệ xử lý idempotent.
- Backlog tối đa và thời gian backlog trở về mức bình thường.
- Khả năng phục hồi khi consumer, broker hoặc một node ứng dụng dừng.
- Mức mất dữ liệu được chấp nhận; với luồng quan trọng, mục tiêu thường là không mất message đã được broker xác nhận.

Throughput cao không bù được việc mất message hoặc xử lý trùng gây sai số dư. Đừng hạ acknowledgement, replication hay durability chỉ để cải thiện một con số benchmark.

## 2. Viết SLO trước khi chỉnh cấu hình

Một SLO tốt mô tả tải, thời gian và điều kiện đo. Ví dụ dưới đây chỉ minh họa cách viết mục tiêu; hãy thay số bằng yêu cầu thực tế:

| Chỉ tiêu | Mục tiêu ví dụ | Cách xác minh |
|---|---:|---|
| Throughput ổn định | 1.500 msg/s trong 30 phút | Đếm message hoàn tất ở output |
| Burst | 3.000 msg/s trong 5 phút | Kiểm tra backlog và khả năng phục hồi |
| End-to-end latency | p95 dưới 250 ms, p99 dưới 1 s | Timestamp/correlation ID ở đầu và cuối luồng |
| Backlog recovery | Trở về mức bình thường trong 3 phút sau burst | Đo tốc độ drain |
| Xử lý lỗi | Không mất message đã được broker xác nhận; duplicate được xử lý idempotent | Fault injection và đối soát |
| DLQ | Mọi poison message được giữ lại để điều tra | Đếm, kiểm tra và replay DLQ |

SLO cần ghi rõ kích thước payload, số partition/queue, consumer group, số instance, loại broker, cấu hình durability và tỷ lệ lỗi giả lập. Nếu thay một điều kiện, kết quả benchmark không còn so sánh trực tiếp với baseline cũ.

## 3. Mô tả workload trước khi sizing

Thu thập dữ liệu thực tế hoặc mô hình hóa các yếu tố sau:

| Đặc điểm | Câu hỏi cần trả lời | Ảnh hưởng |
|---|---|---|
| Arrival rate | Trung bình, peak và burst dài bao lâu? | Quyết định capacity và backlog |
| Payload | Kích thước trung vị, p95, p99? | Ảnh hưởng network, memory, serialization và batch |
| Key distribution | Key phân bố đều hay có hot key? | Ảnh hưởng partition và ordering |
| Processing cost | Function mất bao lâu, CPU-bound hay I/O-bound? | Quyết định concurrency và thread pool |
| Fan-out | Một input tạo bao nhiêu output? | Throughput downstream có thể lớn hơn ingress |
| Ordering | Cần thứ tự toàn cục, theo key hay không cần? | Giới hạn partition/concurrency |
| Failure rate | Bao nhiêu lỗi transient, bao nhiêu poison message? | Ảnh hưởng retry, DLQ và latency |
| Retention | Broker giữ backlog trong bao lâu? | Quyết định khả năng phục hồi sau sự cố |

Ví dụ: 1.000 input msg/s nhưng mỗi input tạo ba output thì downstream phải chịu 3.000 output msg/s, chưa tính retry. Đo riêng từng binding để tìm chặng có capacity thấp nhất.

## 4. Công thức capacity cơ bản

Gọi:

- λ là tốc độ message đến (message/giây).
- μ là tốc độ xử lý tối đa của một worker (message/giây).
- N là số worker xử lý song song.
- S là thời gian xử lý trung bình của một message trên một worker (giây).
- ρ là mức sử dụng mục tiêu của worker.

Với một worker xử lý tuần tự, xấp xỉ μ = 1 / S. Tổng capacity lý thuyết là N × μ. Để backlog không tăng vô hạn, capacity phải lớn hơn arrival rate: N × μ > λ.

Không nên thiết kế hệ thống chạy sát 100% utilization trong mọi thời điểm. Khi arrival rate tiến gần capacity, queueing delay có thể tăng rất nhanh và hệ thống thiếu dư địa để hấp thụ burst. Có thể dùng công thức sizing sơ bộ:

N >= (λ × S) / ρ

Ví dụ cần xử lý 1.500 msg/s, thời gian xử lý trung bình của một worker là 8 ms (0,008 s), và chọn mức sử dụng mục tiêu 65%:

N >= (1500 × 0,008) / 0,65 = 18,46

Ước lượng ban đầu là 19 worker. Đây chỉ là mô hình gần đúng; phải benchmark vì thời gian xử lý thay đổi, I/O có thể chạy đồng thời, và broker/partition có thể giới hạn số consumer hoạt động.

### Little's Law và backlog

Trong một hệ thống ổn định:

L = λ × W

Trong đó L là số message trung bình đang ở trong hệ thống, λ là throughput, W là thời gian trung bình message nằm trong hệ thống. Nếu xử lý 1.000 msg/s và có trung bình 20.000 message đang chờ hoặc đang xử lý, thời gian lưu trung bình xấp xỉ 20 giây.

Thời gian drain backlog có thể ước lượng bằng:

T_drain = B / (C - λ)

B là backlog hiện có, C là capacity xử lý trong lúc hệ thống vẫn nhận traffic. Ví dụ backlog 60.000 message, capacity 1.800 msg/s và traffic mới 1.200 msg/s thì tốc độ drain ròng là 600 msg/s; cần khoảng 100 giây để xóa backlog. Nếu C nhỏ hơn hoặc bằng λ, backlog không thể tự giảm.

## 5. Partition và concurrency quyết định mức song song

Với Kafka, partition là đơn vị song song hóa cơ bản trong một consumer group. Một partition tại một thời điểm chỉ được gán cho một consumer member trong group. Vì vậy:

- Nếu topic có 8 partition, một consumer group thường không tận dụng được hơn 8 consumer hoạt động cho topic đó.
- Nếu chạy 12 consumer cho topic 8 partition, ít nhất 4 consumer sẽ không có partition để đọc.
- Tăng partition có thể tăng mức song song, nhưng cũng làm tăng chi phí metadata, file, replication, rebalance và tài nguyên broker.
- Key được hash để chọn partition; hot key có thể khiến một partition quá tải trong khi partition khác nhàn rỗi.

Trong Spring Cloud Stream, consumer concurrency là thuộc tính chung cho input binding. Với Kafka binder, concurrency tạo các consumer container tương ứng; hiệu quả vẫn bị giới hạn bởi số partition được gán. Với Kafka Streams binder, concurrency trên input binding được chuyển thành số stream thread (num.stream.threads), nên cần phân biệt với regular Kafka binder.

Không tăng concurrency theo cảm tính. Trước tiên kiểm tra partition count, số instance, key skew, consumer lag và CPU. Nếu partition nóng do key phân bố lệch, tăng consumer không giải quyết được nguyên nhân.

### Ví dụ cấu hình regular Kafka consumer

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-service
          consumer:
            concurrency: 4
~~~

Với topic có 12 partition, có thể thử 4 consumer trên mỗi instance hoặc chia instance/concurrency sao cho tổng consumer không vượt quá số partition nếu mục tiêu là tránh consumer nhàn rỗi. Số thực tế còn phụ thuộc cách triển khai, rebalance và tải xử lý.

### Ví dụ cho Kafka Streams binder

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
          consumer:
            concurrency: 3
~~~

Với Kafka Streams binder, thuộc tính này được chuyển thành num.stream.threads theo tài liệu binder. Khi function có nhiều input binding, đặt concurrency trên input binding đầu tiên. Kiểm tra đúng binder và phiên bản đang sử dụng trước khi áp dụng.

## 6. Producer Kafka: batching, compression và acknowledgement

Producer Kafka gom record theo partition thành batch. Batch lớn hơn thường giúp giảm số request và cải thiện throughput, nhưng có thể phải chờ thêm dữ liệu trước khi gửi. Compression nén cả batch nên hiệu quả phụ thuộc vào kích thước và mức độ gom batch.

Các thuộc tính thường cần benchmark:

| Thuộc tính | Tác dụng | Đánh đổi |
|---|---|---|
| batch.size | Kích thước batch tối đa theo byte | Quá nhỏ giảm batching; quá lớn dùng thêm memory |
| linger.ms | Thời gian chờ thêm record để gom batch | Có thể tăng latency khi tải thấp |
| compression.type | Nén batch (lz4, zstd, snappy, gzip) | Giảm network/disk, tốn CPU |
| buffer.memory | Bộ nhớ producer dùng để đệm record chờ gửi | Tăng khả năng hấp thụ burst nhưng tăng memory |
| acks | Mức acknowledgement từ broker | Durability và latency phụ thuộc cấu hình |
| enable.idempotence | Tránh duplicate do retry producer trong phạm vi bảo đảm của Kafka producer | Có ràng buộc cấu hình và chi phí nhất định |
| delivery.timeout.ms | Giới hạn thời gian chờ gửi thành công hoặc thất bại | Quá thấp dễ báo lỗi trong lúc broker chậm; quá cao kéo dài xử lý lỗi |

Ví dụ thử batching và compression trên một output binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                batch.size: 65536
                linger.ms: 5
                compression.type: lz4
                buffer.memory: 67108864
                acks: all
                enable.idempotence: true
~~~

Đây là điểm bắt đầu cho benchmark, không phải cấu hình tối ưu mặc định. Đo cả latency p95/p99, CPU producer, tỷ lệ batch đầy, network throughput và số lần buffer cạn. Khi tăng linger.ms, kiểm tra latency ở tải thấp vì ít message có thể phải chờ hết khoảng linger.

Spring Cloud Stream Kafka binder cũng có producer.bufferSize và producer.batchTimeout. bufferSize là giới hạn buffer/batch phía binder; batchTimeout là thời gian chờ thêm message để gom batch. Chúng có ý nghĩa riêng với batch.size và linger.ms của Kafka client. Tránh chỉnh nhiều lớp cùng lúc mà không biết thuộc tính nào đang chi phối.

acks=all cùng replication phù hợp khi độ bền dữ liệu quan trọng. Giảm acknowledgement có thể làm send latency thấp hơn nhưng thay đổi xác suất mất dữ liệu khi broker lỗi. Chỉ chọn mức acknowledgement sau khi đã xác định RPO và yêu cầu durability.

## 7. Producer synchronous hay asynchronous?

Kafka binder có thuộc tính producer sync. Khi bật, producer chờ kết quả gửi thay vì tiếp tục ngay; điều này giúp caller biết kết quả gửi nhưng có thể làm giảm throughput và tăng latency của luồng gọi.

Dùng synchronous send khi logic nghiệp vụ cần biết broker đã xác nhận trước khi tiếp tục. Nếu chỉ cần publish theo luồng bất đồng bộ, giữ asynchronous và quan sát send result/error channel hoặc metadata phù hợp. Không bỏ qua lỗi publish chỉ vì API trả về nhanh.

Khi cần đo kết quả gửi, Kafka binder có thể gửi metadata thành công vào recordMetadataChannel; metadata gồm partition và offset. Điều này hữu ích để phân biệt function đã tạo message với broker đã ghi nhận message.

## 8. Consumer Kafka: poll, fetch và batch

Consumer Kafka nhận record qua poll(). Một số thuộc tính có tác động lớn:

| Thuộc tính | Vai trò | Đánh đổi |
|---|---|---|
| max.poll.records | Số record tối đa trả về trong một lần poll | Batch lớn tăng hiệu quả nhưng kéo dài thời gian xử lý mỗi poll |
| fetch.min.bytes | Lượng dữ liệu tối thiểu broker nên trả về | Giá trị lớn có thể tăng throughput nhưng tăng chờ |
| fetch.max.wait.ms | Thời gian broker chờ đủ dữ liệu fetch | Tăng giá trị có thể tăng gom batch và latency |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll | Nếu xử lý batch quá lâu, consumer có thể bị coi là không hoạt động và rebalance |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch theo partition | Cần phù hợp với kích thước record batch |

Ví dụ cấu hình cho input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            batch-mode: true
      kafka:
        bindings:
          orders-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                fetch.min.bytes: 65536
                fetch.max.wait.ms: 10
                max.poll.interval.ms: 300000
~~~

Khi bật batch-mode, function nhận một List hoặc Message<List<?>> theo chữ ký phù hợp. Xử lý theo batch có thể giảm overhead gọi function và tăng hiệu quả ghi bulk. Nhưng batch lớn làm tăng memory, thời gian xử lý một poll và số message có thể redeliver khi lỗi.

Với Kafka binder, retry bên trong binder không được hỗ trợ khi bật batch mode; maxAttempts bị ghi đè thành 1. Nếu cần retry cho batch, phải cấu hình error handler ở listener container và xác định rõ cách xử lý partial batch/offset. Không bật batch mode chỉ vì muốn tăng throughput mà chưa kiểm tra semantics lỗi.

## 9. Acknowledgement và độ tin cậy consumer

Commit offset sau mỗi record giúp giảm số record có thể bị redeliver khi consumer lỗi, nhưng có thêm overhead. Commit theo batch/poll có thể cải thiện throughput, nhưng khi process chết giữa batch, một số record đã xử lý có thể được giao lại.

Hãy chọn acknowledgement theo yêu cầu:

- **Record-level acknowledgement**: phù hợp khi muốn giới hạn cửa sổ duplicate; có thể tốn thêm chi phí commit.
- **Batch acknowledgement**: phù hợp với xử lý batch và workload throughput cao; cần chấp nhận khả năng redelivery nhiều record hơn.
- **Manual acknowledgement**: dùng khi ứng dụng phải kiểm soát thời điểm commit; cần bảo đảm chỉ ack sau khi công việc đã hoàn tất và không commit vượt quá record thực sự an toàn.
- **Kafka transaction**: dùng khi cần đồng bộ việc ghi output Kafka và commit offset trong một transaction; phải cấu hình đúng transaction manager và consumer isolation phù hợp.

Producer idempotence không thay thế idempotency nghiệp vụ ở consumer. Nếu consumer ghi cơ sở dữ liệu rồi lỗi trước khi offset được commit, record có thể được giao lại. Dùng unique event ID, unique constraint, inbox table hoặc thao tác upsert có điều kiện để xử lý duplicate an toàn.

## 10. Consumer RabbitMQ: concurrency và prefetch

RabbitMQ phân phối message từ queue đến consumer. Hai tham số quan trọng là concurrency và prefetch:

- concurrency/maxConcurrency quyết định số consumer có thể hoạt động đồng thời.
- prefetch giới hạn số message chưa acknowledgement được giao cho mỗi consumer.

Prefetch lớn có thể giữ consumer bận và tăng throughput, nhưng làm tăng số message chưa ack đang nằm trong bộ nhớ client. Với message lớn hoặc xử lý chậm, prefetch quá cao có thể gây áp lực memory. Nếu cần thứ tự chặt hoặc phân phối đều giữa nhiều consumer ở tải thấp, prefetch thấp (có thể bằng 1) thường phù hợp hơn.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders
          group: order-service
          consumer:
            concurrency: 4
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-concurrency: 8
              prefetch: 100
~~~

Ví dụ này bắt đầu với 4 consumer và cho phép mở rộng đến 8 consumer theo container/binder. Prefetch 100 là giá trị thử nghiệm; hãy đo queue depth, unacked messages, memory, processing latency và phân phối tải trước khi giữ cấu hình.

Nếu cần strict ordering, xem xét một consumer/queue partition hoặc single active consumer và prefetch thấp. Không thể vừa yêu cầu thứ tự toàn cục nghiêm ngặt vừa tùy ý tăng concurrency trên cùng queue.

## 11. Batching trên RabbitMQ

Rabbit binder hỗ trợ batching phía producer và consumer. Producer batching gom nhiều message thành một batch trước khi publish; consumer batching gom message nhận được thành List để xử lý một lần.

Ví dụ consumer-side batching:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          group: order-service
          consumer:
            batch-mode: true
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              enable-batching: true
              batch-size: 10
              receive-timeout: 200
~~~

Batch có thể phát khi đủ số lượng hoặc khi hết receive timeout, nên batch thực tế có thể nhỏ hơn batch-size khi traffic thấp. Batching giảm overhead per-message nhưng tăng thời gian chờ để gom đủ message. Cần đo p95/p99 ở cả tải thấp và tải cao.

Producer-side batching có các thuộc tính như batching-enabled, batch-size, batch-buffer-limit và batch-timeout. Khi dùng, kiểm tra listener có xử lý đúng batch và DLQ/ack semantics có phù hợp. Đừng nhầm batch do producer tạo thành batch do consumer tự gom; hai cơ chế có cách chuyển payload khác nhau.

## 12. Retry, backoff và DLQ là một phần của hiệu năng

Retry không miễn phí. Một message lỗi có thể giữ consumer bận, làm giảm throughput của partition/queue và kéo dài latency của các message sau. Nếu retry mọi exception, lỗi dữ liệu vĩnh viễn có thể tạo retry storm.

Spring Cloud Stream consumer properties có các giá trị chung:

| Thuộc tính | Vai trò | Giá trị mặc định trong tài liệu |
|---|---|---:|
| max-attempts | Tổng số lần xử lý, bao gồm lần đầu | 3 |
| back-off-initial-interval | Khoảng chờ đầu tiên | 1.000 ms |
| back-off-max-interval | Khoảng chờ tối đa | 10.000 ms |
| back-off-multiplier | Hệ số tăng backoff | 2.0 |

Chỉ retry lỗi transient như timeout ngắn hoặc dịch vụ phụ thuộc tạm thời không sẵn sàng. Lỗi schema, dữ liệu sai hoặc vi phạm business rule thường cần reject/DLQ hoặc quy trình sửa dữ liệu. Dùng exponential backoff có giới hạn và jitter khi cần tránh nhiều consumer retry đồng loạt.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 500
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

Với Kafka binder, nếu tổng thời gian retry và backoff vượt max.poll.interval.ms, consumer có thể bị rebalance. Tài liệu binder mô tả cách chuyển retry/DLQ sang listener container khi tổng thời gian retry quá dài. Với Rabbit binder, tránh requeueRejected=true trong tình huống lỗi vĩnh viễn vì message có thể được redeliver liên tục.

DLQ giữ message lỗi để điều tra và replay có kiểm soát. Nó không làm message tự biến mất khỏi backlog nghiệp vụ: cần dashboard, cảnh báo, owner, thời hạn xử lý và quy trình replay. Nếu DLQ tăng liên tục, throughput thành công có thể vẫn tốt nhưng độ tin cậy của pipeline đã suy giảm.

## 13. Độ tin cậy Kafka: acknowledgement, replication và transaction

Với Kafka, độ bền dữ liệu phụ thuộc vào producer acknowledgement, replication, ISR và chính sách broker/topic. Kafka binder hiện có thuộc tính requiredAcks; tài liệu binder mô tả mặc định là all. Producer có thể dùng acks=all và idempotence để tăng độ an toàn khi retry producer.

Các lựa chọn cần được đánh giá cùng nhau:

- acks=all yêu cầu broker chờ acknowledgement từ các replica in-sync theo điều kiện của Kafka.
- Replication factor quyết định số bản sao topic.
- min.insync.replicas ở broker/topic quyết định số replica tối thiểu để chấp nhận ghi với acks=all.
- enable.idempotence giúp producer retry mà tránh duplicate do gửi lại trong phạm vi bảo đảm của producer.
- Transactional binder có thể kết hợp output record và input offset trong một Kafka transaction khi được cấu hình đúng.

Không hạ acks hoặc min.insync.replicas chỉ để đạt benchmark nếu yêu cầu là không mất message đã xác nhận. Cũng không gọi giao dịch giữa Kafka và cơ sở dữ liệu là exactly-once chỉ vì bật Kafka transaction; cần thiết kế đồng bộ với hệ thống ngoài Kafka.

## 14. Độ tin cậy RabbitMQ: durable, persistent, confirm và acknowledgement

Với RabbitMQ, độ tin cậy cần xem xét exchange/queue durability, message delivery mode, publisher confirms, consumer acknowledgement, queue type và dead-letter policy. Publisher confirm cho biết broker đã xử lý publish theo semantics của broker; consumer acknowledgement cho biết message đã được consumer xử lý hoặc từ chối.

Các lựa chọn này ảnh hưởng hiệu năng:

- Confirm cho từng publish hoặc cơ chế chờ confirm có thể tăng round-trip.
- Batch publish/confirm có thể tăng throughput nhưng mở rộng cửa sổ lỗi.
- Quorum queue cung cấp replication semantics khác classic queue và có chi phí tài nguyên riêng.
- Prefetch cao tăng utilization nhưng giữ nhiều message unacked hơn.
- Transaction channel có chi phí lớn hơn publish/ack không transaction.

Hãy benchmark với loại queue và durability thực tế. Kết quả từ queue tạm thời, non-durable hoặc message không persistent không thể dùng để dự báo throughput của workload production có yêu cầu durability.

## 15. Backpressure và giới hạn bộ nhớ

Một pipeline ổn định cần giới hạn tốc độ message được đưa vào từng bước xử lý. Nếu producer phát nhanh hơn consumer trong thời gian dài, backlog sẽ tăng. Nếu consumer lấy quá nhiều message vào memory, heap và GC có thể trở thành nút thắt trước cả broker.

Các cơ chế cần kiểm soát:

- Giới hạn concurrency và số tác vụ bất đồng bộ đang chờ.
- Giới hạn queue nội bộ hoặc buffer giữa các stage.
- Chọn max.poll.records, prefetch và batch size phù hợp với kích thước message.
- Không giữ toàn bộ payload trong memory khi chỉ cần metadata hoặc một phần dữ liệu.
- Dùng timeout cho I/O và circuit breaker phù hợp với dịch vụ phụ thuộc.
- Không dùng parallel() hoặc thread pool không giới hạn để che giấu một dependency đang chậm.

Reactive function có thể dùng backpressure trong Reactor pipeline, nhưng không phải binder/transport nào cũng hỗ trợ backpressure đầu-cuối theo cùng cách. Xác minh khả năng của binder đang dùng; queue của broker vẫn có thể tăng dù downstream Reactor có request pattern giới hạn.

## 16. Tách bottleneck theo từng chặng

Khi latency hoặc lag tăng, đo từng đoạn thay vì tăng concurrency toàn hệ thống:

| Triệu chứng | Nơi cần kiểm tra | Hướng xử lý đầu tiên |
|---|---|---|
| Producer latency tăng | Serialization, compression, buffer, broker ack, network | Đo send time, batch fill, buffer exhaustion và broker request latency |
| Kafka lag tăng ở một partition | Hot key, partition assignment, consumer processing time | Kiểm tra phân bố key, partition lag và xử lý theo key |
| Tất cả partition lag tăng | Consumer capacity thấp hơn arrival rate | Đo CPU/I/O, tăng worker có giới hạn, tối ưu logic |
| Rabbit queue depth tăng, consumer utilization thấp | Consumer bị chặn, prefetch thấp hoặc dependency chậm | Kiểm tra unacked, prefetch, thread pool và downstream |
| p99 cao nhưng p50 thấp | Tail event, retry, GC, hot partition hoặc I/O timeout | Phân rã trace và phân bố thời gian từng bước |
| Heap tăng cùng backlog | Buffer/prefetch/batch lớn hoặc giữ payload | Giảm in-flight messages, giới hạn concurrency, phân tích heap |
| Rebalance lặp lại | Poll interval vượt giới hạn, consumer chết/chậm hoặc deploy liên tục | Giảm batch/work per poll, xem retry và max.poll.interval |
| DLQ tăng | Poison message, schema incompatibility hoặc dependency lỗi | Phân loại exception, retry có chọn lọc, sửa contract/dữ liệu |

Một nút thắt thường nằm ở hệ thống phụ thuộc như database, HTTP API hoặc object storage. Tăng consumer chỉ làm tăng số request đồng thời tới dependency đó, có thể khiến lỗi và retry tăng thêm.

## 17. Quy trình benchmark có thể lặp lại

### Bước 1: Ghi baseline

Chạy với cấu hình hiện tại, ghi lại:

- Throughput vào, throughput xử lý xong và throughput output.
- p50/p95/p99 end-to-end latency.
- Consumer lag hoặc queue depth và tốc độ thay đổi backlog.
- CPU, heap, GC pause, thread count, network và disk.
- Broker request latency, bytes in/out, under-replicated partitions hoặc unacked messages.
- Retry, DLQ, timeout, duplicate và error rate.

### Bước 2: Chạy nhiều profile tải

1. **Warm-up:** cho JVM, JIT và connection pool ổn định.
2. **Steady load:** giữ tải mục tiêu đủ lâu để đo ổn định.
3. **Peak load:** tăng đến tải cao nhất dự kiến.
4. **Burst:** gửi nhanh trong thời gian ngắn rồi đo thời gian drain backlog.
5. **Soak:** chạy lâu để phát hiện memory leak, GC hoặc connection/resource exhaustion.
6. **Failure:** dừng một consumer hoặc broker/node theo kịch bản test để kiểm tra phục hồi.

### Bước 3: Thay một nhóm cấu hình

Ví dụ lần lượt thử:

- Tăng consumer concurrency nhưng giữ nguyên partition count.
- Tăng partition nếu cần thêm song song và key distribution cho phép.
- Thử batch size hoặc max.poll.records khác nhau.
- Thử producer compression và linger.
- Thử prefetch/concurrency của RabbitMQ.
- Thử retry/backoff và acknowledgement policy.

Giữ nguyên workload và môi trường trong mỗi lần chạy. Ghi lại cấu hình, phiên bản binder/client, payload size và kết quả để có thể lặp lại.

### Bước 4: Chọn cấu hình theo SLO

Chọn cấu hình nhỏ nhất đáp ứng throughput và latency mục tiêu với dư địa cho burst, đồng thời vẫn đáp ứng durability và recovery. Không chọn cấu hình chỉ vì throughput cao nhất nếu p99 vượt ngưỡng hoặc backlog không thể drain.

## 18. Ví dụ kế hoạch tuning cho luồng đơn hàng

Giả sử luồng có:

- Kafka topic orders.events.
- Một consumer group order-service.
- Function kiểm tra dữ liệu, gọi dịch vụ tồn kho và ghi kết quả sang orders.accepted.
- Tải mục tiêu 1.200 msg/s, burst 2.400 msg/s trong 2 phút.
- Yêu cầu p95 end-to-end dưới 300 ms và p99 dưới 1,2 s.

Kế hoạch:

1. Đo thời gian function và thời gian gọi tồn kho riêng biệt. Nếu dependency tồn kho chiếm 80% latency, tối ưu serialization hoặc Kafka batch không giải quyết được p99.
2. Xác định số partition và phân bố key. Nếu có một customer key tạo phần lớn traffic, cần kiểm tra hot partition.
3. Đo consumer lag ở từng partition. Nếu tất cả partition tăng đều, capacity tổng thể thấp; nếu một partition tăng riêng, có thể key skew.
4. Thử tăng concurrency trong giới hạn partition count và kiểm tra CPU/dependency.
5. Thử batch mode nếu logic có thể xử lý list và chấp nhận semantics retry/DLQ của batch mode.
6. Thử producer batching/compression cho output và kiểm tra p95/p99.
7. Chạy burst, sau đó đo thời gian drain backlog. Không kết luận đạt SLO chỉ từ thời điểm burst kết thúc.
8. Dừng một instance, chờ rebalance và xác nhận message tiếp tục được xử lý mà không mất dữ liệu.

Nếu gọi tồn kho đồng bộ cho từng message, có thể cân nhắc bulk API hoặc cache có kiểm soát. Nếu dùng bulk API, cần giữ idempotency cho từng order và biết cách xử lý một phần batch thất bại.

## 19. Theo dõi trong production

Dashboard hiệu năng nên thể hiện các tín hiệu theo cùng một cửa sổ thời gian:

- Throughput ingress, processed và completed.
- p50/p95/p99 latency theo binding và theo bước.
- Kafka consumer lag theo topic/partition/group; Rabbit queue depth và unacked.
- Producer send latency, error, retry và batch/compression metrics.
- Consumer concurrency, active/idle consumers và partition assignment.
- DLQ rate, retry rate, redelivery và message age.
- CPU, heap, GC pause, thread pool, connection pool và network.
- Broker health, replication/ISR, disk, request latency và throttling.

Đặt alert dựa trên SLO và tốc độ thay đổi, không chỉ một ngưỡng queue depth cố định. Ví dụ backlog 50.000 message có thể bình thường với consumer xử lý 20.000 msg/s nhưng nghiêm trọng với consumer chỉ xử lý 200 msg/s. Kết hợp queue depth, oldest-message age, processing rate và estimated drain time.

## 20. Các lỗi tối ưu thường gặp

**Tăng concurrency mà không tăng partition.** Với Kafka, consumer dư không tạo thêm song song nếu không có partition để gán. Với RabbitMQ, concurrency quá cao có thể làm dependency phía sau quá tải.

**Tăng batch size để giảm overhead nhưng bỏ qua latency.** Batch chờ đủ message hoặc timeout; tải thấp có thể làm message chờ lâu. Batch lớn cũng tăng memory và số message có thể redeliver.

**Đặt prefetch rất cao cho message lớn.** Nhiều message chưa ack cùng lúc có thể chiếm heap, làm GC tăng và giảm độ ổn định.

**Retry mọi exception.** Poison message hoặc lỗi nghiệp vụ sẽ lặp lại, giữ partition/consumer bận và làm backlog tăng.

**Giảm acknowledgement để đạt throughput.** Kết quả benchmark có thể tốt hơn nhưng RPO và khả năng redelivery đã thay đổi.

**Chỉ đo throughput producer.** Message được gửi đi chưa chắc đã được consumer xử lý xong hoặc output đã được broker xác nhận.

**Chạy benchmark quá ngắn.** JIT, cache, connection pool và batch chưa ổn định; kết quả không đại diện cho production.

**Tối ưu nhiều thuộc tính cùng lúc.** Khi kết quả thay đổi, không biết nguyên nhân nằm ở concurrency, batching, compression hay acknowledgement.

## 21. Checklist trước khi phát hành

- [ ] SLO throughput, p95/p99 latency, backlog recovery và reliability đã được ghi rõ.
- [ ] Workload test bao gồm payload size, key skew, burst và tỷ lệ lỗi thực tế.
- [ ] Đã đo baseline ingress, processing và completion rate riêng biệt.
- [ ] Partition count phù hợp với mức song song và yêu cầu ordering.
- [ ] Consumer concurrency không vượt quá khả năng của broker, partition hoặc dependency.
- [ ] Producer batching/compression đã được thử ở cả tải thấp và tải cao.
- [ ] Consumer batch/prefetch không vượt giới hạn memory và poll/ack time.
- [ ] Retry chỉ áp dụng cho lỗi transient; poison message có DLQ hoặc quy trình xử lý.
- [ ] Acknowledgement, replication, idempotence và transaction đáp ứng yêu cầu durability.
- [ ] Duplicate được xử lý idempotent ở tầng nghiệp vụ.
- [ ] Backlog drain sau burst nằm trong mục tiêu.
- [ ] Đã thử consumer restart, rebalance và broker/dependency outage.
- [ ] Dashboard có p95/p99, lag/queue age, retry/DLQ và tài nguyên runtime.
- [ ] Có thể tái lập benchmark với cùng workload và cấu hình.

Hiệu năng của Spring Cloud Stream là kết quả của toàn tuyến producer, broker, consumer, function và dependency. Xác lập SLO trước, tính capacity và mức song song từ workload, sau đó điều chỉnh batching, concurrency, partition, prefetch, retry và acknowledgement theo đúng binder. Một cấu hình tốt phải đạt throughput mục tiêu, giữ p95/p99 trong ngưỡng, phục hồi backlog sau burst và duy trì semantics giao nhận đã cam kết.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html)
