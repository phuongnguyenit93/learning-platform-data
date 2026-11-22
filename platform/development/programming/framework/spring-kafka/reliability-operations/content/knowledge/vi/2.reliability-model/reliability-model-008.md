# Đánh đổi giữa độ trễ và độ bền

Trong hệ thống Spring Kafka, độ trễ (latency) và độ bền dữ liệu (durability) thường cùng ảnh hưởng đến cách một sự kiện đi từ producer đến consumer. Muốn xác nhận một record an toàn hơn, producer có thể phải chờ nhiều replica xác nhận. Muốn tăng thông lượng, producer có thể gom nhiều record thành batch trước khi gửi. Muốn tránh xử lý lại dữ liệu, consumer có thể commit offset sau mỗi record hoặc sau một batch. Mỗi lựa chọn đều tác động đến thời gian phản hồi, khả năng chịu lỗi, thông lượng và lượng công việc có thể phải phát lại khi sự cố xảy ra.

Đích đến của thiết kế tin cậy không phải là làm latency thấp nhất bằng mọi giá hoặc tăng replication cho mọi topic mà không xét tải. Cần xác định mức mất dữ liệu có thể chấp nhận, thời hạn xử lý nghiệp vụ, phạm vi lỗi phải chịu được và ngân sách độ trễ. Sau đó chọn cấu hình producer, topic, broker, consumer và transaction phù hợp với từng luồng sự kiện.

## 1. Phân biệt latency, throughput và durability

Ba khái niệm này liên quan với nhau nhưng không thể thay thế cho nhau:

- **Latency** là thời gian một thao tác hoặc một sự kiện cần để đi từ mốc bắt đầu đến mốc kết thúc. Với Kafka, có thể đo thời gian producer gửi và nhận xác nhận, thời gian record chờ trong topic, thời gian listener xử lý hoặc thời gian từ lúc phát đến khi nghiệp vụ hoàn tất.
- **Throughput** là lượng công việc hệ thống xử lý trong một đơn vị thời gian, ví dụ record/giây hoặc MB/giây. Một cấu hình có throughput cao vẫn có thể có latency p99 lớn nếu record phải chờ gom batch hoặc chờ xử lý phía sau.
- **Durability** là khả năng dữ liệu đã được chấp nhận vẫn tồn tại và có thể khôi phục sau các lỗi nằm trong phạm vi thiết kế, chẳng hạn một broker hoặc một ổ đĩa gặp sự cố. Durability phụ thuộc replication, ISR, xác nhận của producer, lưu trữ và quy trình phục hồi.

Ví dụ, một producer gửi 10.000 record/giây có thể đạt throughput cao nhờ batching, nhưng record đầu tiên trong batch phải chờ thêm một khoảng thời gian trước khi gửi. Ngược lại, gửi từng record ngay lập tức có thể giảm thời gian chờ ở producer nhưng làm tăng số request, overhead mạng và chi phí xử lý trên broker.

Độ trễ đầu cuối nên được nhìn như tổng thời gian ở nhiều chặng:

~~~text
Producer tạo record
      |
      v
Chờ buffer / gom batch
      |
      v
Gửi request và chờ broker xác nhận
      |
      v
Record nằm trong topic
      |
      v
Consumer poll và xử lý nghiệp vụ
      |
      v
Commit offset
      |
      v
Nghiệp vụ được xem là hoàn tất
~~~

Nếu chỉ đo thời gian gọi `KafkaTemplate.send()` mà không đo kết quả future, thời gian chờ consumer và thời điểm commit offset, ta chỉ nhìn thấy một phần latency. Một hệ thống có producer phản hồi nhanh vẫn có thể có độ trễ đầu cuối cao do consumer lag hoặc downstream chậm.

## 2. Xác định ngân sách độ trễ và mức mất dữ liệu chấp nhận được

Trước khi chọn cấu hình, hãy trả lời hai câu hỏi:

1. Sự kiện cần được xử lý xong trong bao lâu để nghiệp vụ vẫn đúng?
2. Khi có lỗi broker hoặc ứng dụng, hệ thống được phép mất bao nhiêu sự kiện đã xác nhận?

Không nên chỉ dùng một con số latency trung bình. Hãy đặt mục tiêu cho các phân vị như p50, p95 và p99. p50 cho biết trải nghiệm thường gặp; p95 và p99 thể hiện phần đuôi chậm mà người dùng hoặc hệ thống downstream vẫn có thể gặp. Một luồng thanh toán có thể yêu cầu p99 nghiêm ngặt hơn một luồng thu thập telemetry không đồng bộ.

Mức mất dữ liệu cần được mô tả theo RPO (Recovery Point Objective): lượng dữ liệu hoặc khoảng thời gian dữ liệu tối đa có thể mất trong một kịch bản sự cố. Thời gian đưa dịch vụ trở lại hoạt động được mô tả bằng RTO (Recovery Time Objective). Replication và acknowledgement có thể giảm RPO đối với lỗi broker đơn lẻ; chúng không tự đảm bảo RTO nếu cluster, mạng, ứng dụng hoặc quy trình vận hành không thể phục hồi.

| Loại luồng | Ví dụ | Ưu tiên thường gặp |
|---|---|---|
| Giao dịch quan trọng | Lệnh thanh toán, thay đổi số dư, xác nhận đơn hàng | Durability cao, idempotency, đối soát; latency phải nằm trong SLA |
| Cập nhật nghiệp vụ gần thời gian thực | Trạng thái giao hàng, đồng bộ tồn kho | Cân bằng latency và durability; theo dõi lag và thứ tự |
| Telemetry và log | Metric ứng dụng, log kỹ thuật, sự kiện quan sát | Throughput và chi phí thường quan trọng; có thể chấp nhận mất một phần dữ liệu tùy mục đích |
| Tín hiệu tạm thời | Typing indicator, trạng thái hiện diện | Latency thấp; dữ liệu cũ có thể hết giá trị nhanh |

Đây là các xu hướng lựa chọn, không phải quy tắc cứng. Một số telemetry phục vụ kiểm toán cũng cần durability cao; một số sự kiện giao dịch có thể xử lý bất đồng bộ nhưng vẫn phải bảo toàn dữ liệu.

## 3. Producer acknowledgement: tốc độ xác nhận và độ bền

Kafka producer có ba lựa chọn cơ bản cho `acks`:

| `acks` | Khi nào producer nhận xác nhận? | Hệ quả |
|---|---|---|
| `0` | Producer không chờ broker xác nhận | Latency thấp ở phía producer, nhưng không biết broker đã nhận record hay chưa; nguy cơ mất dữ liệu cao nhất |
| `1` | Leader xác nhận sau khi ghi record vào log cục bộ của leader | Thường nhanh hơn chờ toàn bộ ISR; nếu leader lỗi trước khi replica khác nhận record, record có thể mất |
| `all` | Leader chờ các replica hiện thuộc ISR xác nhận | Mức bảo vệ tốt hơn trước lỗi replica; latency và khả năng ghi phụ thuộc trạng thái ISR |

`acks=all` không có nghĩa là chờ mọi replica từng được cấu hình cho partition, kể cả replica đang mất kết nối. Nó chờ các replica hiện thuộc In-Sync Replica Set (ISR). Vì vậy, `acks=all` phải được kết hợp với replication factor và `min.insync.replicas` phù hợp.

Ví dụ topic có replication factor 3 và `min.insync.replicas=2`:

- Khi ISR có 3 replica, ghi với `acks=all` cần các replica trong ISR xác nhận.
- Khi một replica bị lỗi và ISR còn 2, producer vẫn có thể ghi nếu hai replica này xác nhận.
- Khi ISR giảm còn 1, broker từ chối ghi theo yêu cầu tối thiểu. Producer nhận lỗi và có thể retry theo cấu hình.

Từ chối ghi khi ISR không đủ là một lựa chọn bảo vệ durability. Nếu hệ thống tự hạ mức xác nhận để tiếp tục nhận ghi, nó có thể biến một sự cố khả dụng thành mất dữ liệu mà không có dấu hiệu rõ ràng ở tầng nghiệp vụ.

### 3.1. Ví dụ cấu hình producer ưu tiên độ bền

Với sự kiện quan trọng, cấu hình Spring Boot có thể bắt đầu từ:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Các giá trị thời gian và số lần retry trong ví dụ cần được điều chỉnh theo SLA, phiên bản Kafka client và khả năng của cluster. `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng giao một record; số lần retry rất lớn không đồng nghĩa với retry vô hạn.

`enable.idempotence=true` giúp producer tránh tạo bản ghi trùng do retry trong phạm vi session của producer và hỗ trợ bảo toàn thứ tự theo các điều kiện cấu hình tương thích. Idempotence thường là lựa chọn phù hợp cho luồng quan trọng vì giảm rủi ro duplicate do retry mà không buộc ứng dụng phải tắt các tối ưu hiệu năng khác.

### 3.2. Không đồng nhất send() với xác nhận thành công

Trong Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture`. Việc nhận được future chỉ cho biết thao tác gửi bất đồng bộ đã được khởi tạo; cần quan sát kết quả hoàn tất:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Publish failed, orderId={}", orderId, error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug("Publish acknowledged: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
~~~

Nếu API nghiệp vụ chỉ trả thành công sau khi record được broker xác nhận, cần phối hợp kết quả future với luồng request và ngân sách timeout. Không nên chặn thread không giới hạn. Nếu nghiệp vụ đã commit database nhưng Kafka gửi thất bại, hoặc kết quả gửi không rõ do timeout, cần có outbox và event id ổn định để phát lại an toàn.

## 4. Replication và min.insync.replicas

Replication tạo nhiều bản sao partition trên các broker khác nhau. Khi leader gặp lỗi, một replica phù hợp có thể được bầu làm leader mới. Replication factor càng cao thì số bản sao càng nhiều, nhưng cũng tăng dung lượng lưu trữ, lưu lượng sao chép và chi phí tài nguyên.

`min.insync.replicas` đặt số replica đồng bộ tối thiểu để broker chấp nhận ghi khi producer dùng `acks=all`. Cấu hình này tạo một ranh giới rõ giữa khả năng tiếp tục ghi và mức an toàn dữ liệu được yêu cầu.

Ví dụ thiết kế phổ biến cho topic quan trọng:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
unclean.leader.election.enable = false
~~~

Thiết kế trên thường có thể tiếp tục ghi khi một replica bị lỗi, miễn là còn ít nhất hai replica trong ISR. Nếu ISR xuống dưới hai, ghi bị từ chối để bảo vệ mức replication yêu cầu. Không nên áp dụng máy móc nếu cluster chỉ có hai broker, các broker cùng nằm trong một miền lỗi hoặc chi phí sao chép vượt năng lực hệ thống.

Đặt replica trên các broker hoặc rack/zone khác nhau giúp giảm nguy cơ một sự cố vật lý làm mất nhiều bản sao cùng lúc. Rack awareness chỉ có tác dụng khi metadata rack của broker phản ánh đúng topology hạ tầng.

### 4.1. Durability có chi phí vận hành

Replication không chỉ làm tăng thời gian xác nhận. Nó còn tiêu thụ network bandwidth, disk capacity, I/O và CPU. Khi một broker trở lại sau thời gian gián đoạn, quá trình bắt kịp replica có thể cạnh tranh tài nguyên với traffic bình thường. Cần theo dõi:

- Under-replicated partitions và offline partitions.
- ISR shrink/expand và thời gian replica bắt kịp.
- Broker network throughput, disk utilization và request latency.
- Số lần leader election và thời gian phục hồi sau broker restart.

Kafka thường dựa vào page cache của hệ điều hành và cơ chế replication để đạt hiệu năng ghi cao; không nên giả định mỗi acknowledgement tương đương một lần fsync đồng bộ xuống thiết bị lưu trữ cho từng record. Hãy dựa vào semantics của Kafka, cấu hình broker, replication và đặc tính lưu trữ thực tế khi xác định RPO.

## 5. Batching, linger và compression

Producer có thể gom nhiều record của cùng partition vào một batch. Gửi batch giúp giảm số request, tận dụng network và broker hiệu quả hơn, đồng thời có thể tăng throughput. Đổi lại, record có thể phải chờ thêm trước khi batch được gửi.

Các thiết lập quan trọng:

| Thiết lập | Tác động đến latency | Tác động đến throughput và tài nguyên |
|---|---|---|
| `linger.ms` | Tăng thời gian chờ có chủ đích khi batch chưa đầy | Có thể tạo batch lớn hơn và giảm overhead request |
| `batch.size` | Batch lớn có thể cần chờ lâu hơn mới đầy | Tăng hiệu quả gửi theo batch nhưng dùng thêm bộ nhớ |
| `compression.type` | Có thể thêm chi phí CPU để nén/giải nén | Giảm bytes truyền và lưu trữ; hiệu quả tùy dữ liệu |
| `buffer.memory` | Buffer thiếu có thể khiến send block hoặc lỗi theo giới hạn thời gian | Quyết định lượng dữ liệu producer có thể xếp hàng khi broker chậm |

### 5.1. Chọn linger theo đặc tính traffic

Với luồng ít record và yêu cầu phản hồi nhanh, `linger.ms` nhỏ giúp giảm thời gian chờ gom batch. Với luồng lưu lượng lớn, tăng linger một mức vừa phải có thể tạo batch hiệu quả hơn mà không làm vượt SLA.

Ví dụ cấu hình cân bằng:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[linger.ms]": 5
        "[batch.size]": 32768
        "[compression.type]": lz4
~~~

Đây chỉ là điểm bắt đầu để benchmark. `linger.ms=5` không đảm bảo mọi record luôn chờ đúng 5 ms; batch có thể được gửi sớm khi đầy hoặc khi có điều kiện gửi khác. Hiệu quả thực tế phụ thuộc số partition, phân bố key, kích thước record và tốc độ phát.

### 5.2. Chọn compression

Compression có thể giảm lượng dữ liệu đi qua mạng và ghi xuống log, đặc biệt khi các record trong batch có cấu trúc lặp lại. Đổi lại, producer và broker/consumer có thể phải dùng CPU để nén và giải nén.

- `lz4` thường được cân nhắc khi muốn giảm chi phí CPU và giữ tốc độ cao.
- `zstd` có thể đạt tỷ lệ nén tốt, nhưng cần benchmark CPU và latency.
- `snappy` là lựa chọn cân bằng trong nhiều workload.
- `gzip` có thể nén tốt nhưng thường tốn CPU hơn.

Không có codec tốt nhất cho mọi payload. Dữ liệu đã nén, mã hóa hoặc có entropy cao có thể không giảm kích thước đáng kể. Đo bytes trên mạng, CPU, batch size và p99 trước khi thay đổi codec.

## 6. Consumer acknowledgement và thời điểm commit offset

Consumer cũng tạo ra một đánh đổi latency/durability. Offset được commit càng sớm thì lag được báo cáo có thể giảm nhanh, nhưng nếu commit trước khi nghiệp vụ hoàn tất, record có thể bị bỏ qua sau khi ứng dụng gặp sự cố. Nếu commit sau khi xử lý thành công, record có thể được giao lại khi consumer chết trước thời điểm commit; vì vậy nghiệp vụ phải chịu được duplicate.

Với Spring Kafka, `enable.auto.commit=false` thường được dùng để listener container quản lý commit. Một số acknowledgement mode phổ biến:

| Ack mode | Khi nào commit? | Đặc điểm |
|---|---|---|
| `RECORD` | Sau khi listener xử lý thành công từng record | Dễ gắn thời điểm commit với kết quả từng record; có thể tăng số lần commit |
| `BATCH` | Sau khi tất cả record trong poll batch được xử lý thành công | Giảm overhead commit; nếu lỗi, có thể phải xử lý lại phần batch chưa được xác nhận |
| `TIME` / `COUNT` / `COUNT_TIME` | Khi đạt điều kiện thời gian, số record hoặc cả hai | Cho phép cân bằng commit overhead với lượng record có thể được phát lại |
| `MANUAL` / `MANUAL_IMMEDIATE` | Theo acknowledgement do ứng dụng điều khiển | Linh hoạt nhưng yêu cầu code ack đúng thời điểm và hiểu rõ semantics của container |

Ví dụ cấu hình listener quản lý offset theo batch:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        "[max.poll.records]": 100
    listener:
      ack-mode: batch
~~~

Batch lớn có thể tăng throughput và giảm overhead commit, nhưng thời gian xử lý batch lâu hơn, lượng record cần phát lại sau sự cố có thể lớn hơn và consumer cần gọi `poll()` đúng hạn. Batch nhỏ giảm phạm vi công việc đang chờ hoàn tất nhưng có thể làm tăng overhead.

### 6.1. Không commit trước khi tác động nghiệp vụ bền vững

Giả sử consumer nhận sự kiện `OrderPaid`, cập nhật database rồi commit offset:

1. Nếu database commit thành công và consumer chết trước khi Kafka commit offset, record có thể được giao lại. Consumer phải idempotent.
2. Nếu Kafka commit offset trước rồi database transaction thất bại, record có thể không được giao lại dù nghiệp vụ chưa hoàn tất. Đây là nguy cơ mất tác động nghiệp vụ.

Vì vậy, với xử lý database thông thường, hãy hoàn tất transaction database trước khi listener trả về thành công hoặc gọi ack. Nếu cần đảm bảo mạnh hơn, dùng inbox table với event id và unique constraint trong cùng database transaction với thay đổi nghiệp vụ.

### 6.2. Synchronous và asynchronous commit

Spring Kafka listener container thường có thể commit offset đồng bộ hoặc bất đồng bộ tùy cấu hình `syncCommits`. Commit đồng bộ chờ phản hồi từ broker, dễ quan sát lỗi commit tại thời điểm xảy ra nhưng thêm network round trip vào đường xử lý. Commit bất đồng bộ có thể giảm thời gian chờ, nhưng kết quả commit đến muộn hoặc lỗi commit cần được quan sát và xử lý cẩn thận.

Không nên đổi sang asynchronous commit chỉ vì muốn giảm latency vài mili giây mà chưa đo được commit đang chiếm bao nhiêu ngân sách. Cần theo dõi commit latency, commit failure và số record có khả năng được phát lại khi consumer dừng.

## 7. Batch size, poll interval và consumer lag

`max.poll.records` giới hạn số record trả về trong một lần poll. Giá trị lớn có thể giảm overhead poll và tăng hiệu quả xử lý theo lô, nhưng listener cần nhiều thời gian hơn để xử lý hết batch. Nếu khoảng thời gian giữa các lần poll vượt `max.poll.interval.ms`, consumer có thể bị rời group và partition được phân phối lại.

Hãy chọn batch size dựa trên thời gian xử lý thực tế:

~~~text
Thời gian xử lý batch
  = số record trong batch
    x thời gian xử lý trung bình mỗi record
    + overhead của batch
~~~

Đây là ước lượng đơn giản; phân bố thời gian xử lý, concurrency và downstream call có thể làm p99 cao hơn nhiều so với giá trị trung bình. Khi record có thời gian xử lý không đồng đều, batch lớn có thể bị chi phối bởi một record chậm.

Consumer lag biểu thị khoảng cách giữa offset đã được consumer group xác nhận và offset mới nhất của partition. Lag tăng liên tục thường cho thấy tốc độ phát cao hơn tốc độ xử lý hoặc consumer đang bị chặn. Lag giảm không nhất thiết chứng minh nghiệp vụ đã hoàn tất nếu ứng dụng commit offset sai thời điểm.

Theo dõi thêm tuổi của record cũ nhất. Hai group có cùng lag count nhưng tốc độ phát khác nhau có thể có độ trễ thực tế khác nhau. Một backlog 10.000 record có thể được xử lý trong vài giây ở luồng throughput cao, nhưng có thể tương đương nhiều giờ ở luồng lưu lượng thấp.

## 8. Transaction và chi phí của exactly-once trong Kafka

Kafka transaction cho phép ghi nhiều record và offset input trong cùng một giao dịch Kafka. Với consume-transform-produce, Spring Kafka có thể phối hợp transaction để output và offset được commit nguyên tử. Consumer sử dụng `isolation.level=read_committed` chỉ đọc các record thuộc transaction đã commit.

Transaction có thêm các bước điều phối và commit, nên thường có chi phí latency so với luồng produce/consume không transaction. Transaction timeout, thời gian xử lý và số record trong transaction phải được giới hạn. Transaction kéo dài có thể làm các consumer `read_committed` phải chờ ở cuối log cho đến khi transaction kết thúc.

Khi cấu hình transaction producer, cần có transaction id prefix duy nhất phù hợp giữa các instance ứng dụng. Cấu hình prefix trùng hoặc vòng đời transactional producer không phù hợp có thể gây lỗi fencing hoặc lỗi khởi tạo transaction.

Chỉ nên dùng Kafka transaction khi cần semantics nguyên tử cho dữ liệu Kafka, ví dụ một record input được biến đổi thành nhiều record output và offset input phải commit cùng output. Nếu luồng chỉ gửi một event và consumer cập nhật database, Kafka transaction không tự tạo transaction phân tán với database.

### 8.1. Outbox và inbox cho luồng có database

Transactional outbox ghi thay đổi nghiệp vụ và event cần phát vào cùng một database transaction. Một publisher đọc outbox rồi gửi event sang Kafka. Việc gửi có thể lặp nếu publisher gặp lỗi sau khi broker nhận record nhưng trước khi database đánh dấu đã phát; do đó consumer cần idempotency.

Inbox ở consumer ghi nhận event id và cập nhật nghiệp vụ trong cùng database transaction. Khi record được giao lại, unique constraint nhận diện event đã xử lý và ngăn tác động lặp.

Outbox/inbox có thể tăng độ trễ do thêm bước ghi/đọc database và publisher polling hoặc CDC. Đổi lại, nó tạo cơ chế phục hồi rõ ràng giữa database và Kafka mà không giả định hai hệ thống có một transaction nguyên tử chung.

## 9. Retention và độ bền theo thời gian

Replication bảo vệ trước một số lỗi broker; retention quyết định record còn khả dụng trong bao lâu để consumer đọc lại hoặc phục hồi sau outage.

`retention.ms` và `retention.bytes` giới hạn thời gian hoặc dung lượng log được giữ trên topic. Retention quá ngắn có thể khiến consumer dừng lâu hơn khoảng lưu giữ rồi mất khả năng đọc lại một phần dữ liệu. Retention dài hơn làm tăng nhu cầu disk và có thể ảnh hưởng chi phí broker.

Với topic `compact`, Kafka giữ giá trị mới nhất theo key theo chính sách compaction; compaction không phải một bản sao lưu đầy đủ mọi phiên bản sự kiện. Nếu nghiệp vụ cần audit lịch sử, không được xem compacted topic là kho lưu mọi thay đổi.

DLT và retry topics cũng cần retention phù hợp. Record lỗi phải tồn tại đủ lâu cho điều tra và replay, nhưng không nên lưu vô hạn mà không có chính sách bảo mật, dung lượng và dọn dẹp.

## 10. Multi-region và giới hạn của durability

Replication trong một Kafka cluster thường bảo vệ dữ liệu trước lỗi broker trong cluster và topology đã cấu hình. Nó không tự bảo vệ trước mất toàn bộ region, lỗi quản trị diện rộng hoặc sự cố làm mất quyền truy cập vào toàn cluster.

Sao chép dữ liệu giữa các region thường có độ trễ và có thể là asynchronous. Điều này tạo một khoảng thời gian mà dữ liệu đã được xác nhận ở region nguồn nhưng chưa được sao chép sang region dự phòng. Nếu region nguồn mất hoàn toàn trong khoảng đó, RPO có thể lớn hơn 0.

Khi thiết kế disaster recovery, cần xác định:

- Region nào là nguồn ghi chính và cách chuyển quyền ghi.
- Độ trễ replication liên vùng và RPO được chấp nhận.
- Cách tránh hai region cùng xử lý ghi độc lập ngoài ý muốn.
- Cách chuyển consumer group, offset và schema/config sang môi trường dự phòng.
- Quy trình đối soát record bị thiếu hoặc được xử lý trùng sau failover.

Tăng durability liên vùng thường làm tăng latency, chi phí network và độ phức tạp vận hành. Chỉ chọn synchronous cross-region acknowledgement khi SLA thực sự yêu cầu và hạ tầng có thể đáp ứng độ trễ đó.

## 11. Đo lường để tìm điểm cân bằng

Không nên điều chỉnh đồng thời nhiều tham số rồi kết luận từ một lần chạy benchmark. Hãy thay đổi từng nhóm, giữ tải và dữ liệu thử nghiệm ổn định, rồi so sánh cả latency, throughput lẫn hành vi khi có lỗi.

| Thành phần | Metrics cần đo | Câu hỏi |
|---|---|---|
| Producer | Send latency p50/p95/p99, error rate, retry rate, batch size, compression rate, buffer wait | Chờ broker, chờ batch hay chờ buffer đang chiếm thời gian? |
| Broker | Produce request latency, ISR, under-replicated partitions, disk/network utilization | Replication hoặc tài nguyên broker có tạo bottleneck không? |
| Consumer | Poll interval, processing duration, commit latency, lag và tuổi record cũ nhất | Độ trễ nằm ở poll, xử lý, commit hay backlog? |
| Transaction | Transaction duration, abort rate, timeout và fencing error | Transaction có quá dài hoặc thất bại thường xuyên không? |
| Nghiệp vụ | Thời gian từ event creation đến business completion, duplicate và missing event | Tối ưu kỹ thuật có cải thiện kết quả nghiệp vụ không? |

Đo trong nhiều điều kiện:

1. Tải nền thấp để quan sát ảnh hưởng của `linger.ms` và batching khi ít record.
2. Tải bình thường để đo latency và throughput ở điều kiện dự kiến.
3. Tải đỉnh để tìm giới hạn CPU, network, disk và consumer concurrency.
4. Broker mất một replica để xác nhận hành vi `acks=all` và `min.insync.replicas`.
5. Consumer dừng hoặc downstream chậm để quan sát lag, retry và thời gian phục hồi.
6. Replay backlog để biết hệ thống có thể bắt kịp tải mới trong bao lâu.

Kết quả benchmark chỉ có ý nghĩa khi bao gồm failure test. Một cấu hình đạt p99 thấp trong điều kiện bình thường nhưng mất record khi broker lỗi không đáp ứng yêu cầu durability của luồng quan trọng.

## 12. Các cấu hình tham khảo theo mục tiêu

### 12.1. Luồng ưu tiên latency

Với dữ liệu có thể tái tạo hoặc chấp nhận mất một phần, có thể cân nhắc:

- `linger.ms` thấp để hạn chế chờ gom batch.
- Batch size và compression được chọn theo kích thước record và tải.
- `acks=1` chỉ khi nghiệp vụ chấp nhận rủi ro mất record nếu leader lỗi trước khi replica khác nhận dữ liệu.
- Consumer xử lý batch nhỏ nếu yêu cầu phản hồi nhanh cho từng sự kiện.
- Retention và khả năng replay vẫn phải đủ cho mức phục hồi đã cam kết.

Không nên mặc định dùng `acks=0` cho mọi luồng realtime. Producer không nhận xác nhận từ broker nên ứng dụng khó biết record đã được nhận hay chưa; latency thấp ở API producer không chứng minh event đã tới hệ thống.

### 12.2. Luồng ưu tiên durability

Với sự kiện giao dịch hoặc dữ liệu không thể tái tạo:

- Topic có replication factor phù hợp và replica phân bố qua miền lỗi.
- `min.insync.replicas` được đặt theo số replica tối thiểu có thể chấp nhận.
- Producer dùng `acks=all` và idempotence.
- Consumer commit sau khi tác động nghiệp vụ bền vững.
- Consumer có inbox/deduplication hoặc idempotency key.
- Retention đủ dài cho thời gian phục hồi dự kiến.
- Có DLT, outbox hoặc cơ chế replay và đối soát phù hợp.

Latency cao hơn một mức có thể là chi phí hợp lý để giảm RPO. Cần kiểm chứng p99 vẫn đáp ứng SLA thay vì giả định durability cao luôn đồng nghĩa với không thể đáp ứng realtime.

### 12.3. Luồng ưu tiên throughput

Với stream có lưu lượng lớn:

- Dùng batching và compression sau khi benchmark.
- Chọn số partition và key để phân phối tải đều.
- Dùng consumer batch processing nếu nghiệp vụ cho phép.
- Tránh commit offset quá thường xuyên nếu commit overhead đáng kể, nhưng giới hạn số record có thể phải phát lại.
- Đặt giới hạn buffer, retry và poll để tránh tích tụ bộ nhớ hoặc làm downstream quá tải.

Throughput cao cần đi cùng kiểm soát backlog. Nếu hệ thống xử lý nhanh hơn trong một khoảng ngắn nhưng không thể bắt kịp sau outage, mục tiêu phục hồi vẫn chưa đạt.

## 13. Quy trình ra quyết định khi latency tăng

Khi p95 hoặc p99 tăng, không nên lập tức giảm `acks` hoặc `min.insync.replicas`. Hãy xác định chặng tạo ra độ trễ:

1. Nếu producer send latency tăng, kiểm tra broker request latency, ISR, retry, buffer wait và network.
2. Nếu batch wait tăng, xem `linger.ms`, lưu lượng theo partition và batch size.
3. Nếu broker latency tăng, xem disk, network, request queue và replica catch-up.
4. Nếu producer nhanh nhưng end-to-end chậm, kiểm tra consumer lag, poll interval, listener duration và downstream.
5. Nếu commit latency cao, xác định tần suất commit và cân nhắc ack mode hoặc sync commit sau khi đo lượng record có thể phát lại.
6. Nếu transaction kéo dài, giảm thời gian xử lý trong transaction hoặc chia nhỏ giao dịch theo ranh giới nghiệp vụ phù hợp.
7. Sau thay đổi, chạy lại benchmark và failure test để bảo đảm cải thiện latency không làm suy giảm durability ngoài mức chấp nhận.

## 14. Checklist lựa chọn cấu hình

### Trước khi chọn producer settings

- [ ] Đã xác định RPO và SLA latency cho luồng sự kiện.
- [ ] Đã quyết định mức `acks` dựa trên tác động của việc mất record.
- [ ] Replication factor và `min.insync.replicas` phù hợp với topology.
- [ ] Idempotence được bật khi producer retry có thể tạo duplicate.
- [ ] `delivery.timeout.ms` phù hợp với ngân sách thời gian nghiệp vụ.
- [ ] `linger.ms`, `batch.size` và compression được benchmark.

### Trước khi chọn consumer settings

- [ ] Auto commit được tắt nếu listener container quản lý offset.
- [ ] Ack mode phản ánh đúng thời điểm nghiệp vụ hoàn tất.
- [ ] Database commit diễn ra trước khi offset được xác nhận.
- [ ] Consumer idempotent khi record có thể được giao lại.
- [ ] Batch size và `max.poll.interval.ms` phù hợp thời gian xử lý.
- [ ] Commit latency và consumer lag được theo dõi.

### Trước khi đưa vào production

- [ ] Đã thử broker mất một replica và xác nhận hành vi ghi như thiết kế.
- [ ] Đã thử consumer dừng giữa xử lý và commit offset.
- [ ] Đã đo p50/p95/p99 ở tải nền, tải bình thường và tải đỉnh.
- [ ] Đã xác định thời gian phục hồi backlog sau outage.
- [ ] Retention đủ cho thời gian phục hồi và replay.
- [ ] Có cảnh báo cho ISR, under-replicated partition, lag và lỗi producer.
- [ ] Runbook giải thích cách xử lý khi phải đánh đổi khả năng ghi với durability.

## Kết luận

Độ trễ và độ bền cần được cân bằng theo giá trị của từng loại sự kiện. `acks=all`, replication và `min.insync.replicas` quyết định mức xác nhận ở phía producer; batching và compression tác động đến hiệu quả gửi; ack mode, poll và commit quyết định thời điểm consumer xác nhận xử lý; transaction và outbox/inbox xử lý các ranh giới nhất quán giữa Kafka với hệ thống khác. Đo latency đầu cuối, throughput, lag và hành vi khi có lỗi sẽ cho thấy điểm cân bằng thực tế. Một cấu hình tốt là cấu hình đáp ứng SLA với RPO đã cam kết và có thể phục hồi theo quy trình đã kiểm chứng.
