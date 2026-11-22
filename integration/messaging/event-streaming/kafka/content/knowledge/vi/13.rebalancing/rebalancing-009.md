# Ngăn rebalance lặp do poll chậm, GC hoặc kết nối không ổn định

Kafka consumer group dùng rebalance để phân phối partition cho các consumer member. Rebalance là hoạt động bình thường khi member tham gia, rời group, mất kết nối hoặc subscription thay đổi. Vấn đề xuất hiện khi group liên tục rebalance dù số consumer và topic không thay đổi. Hiện tượng này thường được gọi là **rebalance storm**: partition bị thu hồi và gán lại nhiều lần, consumer phải khởi tạo lại trạng thái xử lý, throughput giảm và consumer lag tăng.

Ba nguyên nhân thường gặp là xử lý record quá lâu giữa hai lần gọi `poll()`, JVM bị dừng lâu do garbage collection (GC), và kết nối mạng không ổn định khiến heartbeat không đến được coordinator. Muốn ngăn rebalance lặp, cần xác định chính xác timeout nào bị vượt, giảm thời gian xử lý trong poll loop, kiểm soát backpressure và khắc phục nguyên nhân hạ tầng. Chỉ tăng timeout có thể giúp trong một số workload, nhưng không thay thế việc sửa một consumer bị nghẽn hoặc một mạng thường xuyên mất kết nối.

## 1. Rebalance và vì sao nó có thể lặp liên tục?

Một consumer group có một tập member và một tập partition được phân phối cho các member đó. Khi membership hoặc subscription thay đổi, group coordinator phối hợp rebalance để tạo assignment mới.

Ví dụ group billing đang có ba consumer:

~~~text
Trước rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
~~~

Nếu Consumer B bị coi là không còn hoạt động, group có thể phân phối lại partition:

~~~text
Sau rebalance:
  Consumer A -> P0, P1, P2
  Consumer C -> P3, P4, P5
~~~

Khi Consumer B quay lại, group có thể rebalance lần nữa để phân bổ partition cho ba member. Nếu B lại bị timeout, rồi phục hồi, chu kỳ này tiếp tục lặp.

Một rebalance có thể làm:

- Consumer tạm ngừng nhận record trong thời gian assignment thay đổi.
- Partition bị thu hồi khỏi member cũ và gán cho member mới.
- Consumer phải hoàn tất hoặc dừng công việc đang xử lý theo chính sách ứng dụng.
- Consumer có thể đọc lại record chưa commit, dẫn đến xử lý lặp.
- Consumer group lag và latency tăng.
- Downstream như database hoặc HTTP service nhận tải đột biến khi consumer bắt đầu xử lý lại.

Rebalance không nhất thiết là lỗi. Nó là cơ chế quản lý membership và assignment. Mục tiêu vận hành là giảm những lần rebalance không cần thiết và làm cho mỗi lần rebalance diễn ra nhanh, an toàn.

## 2. Ba nhóm timeout cần phân biệt

Các cấu hình poll và heartbeat có quan hệ với nhau nhưng không đo cùng một điều kiện.

| Cấu hình | Theo dõi điều gì? | Khi vượt ngưỡng |
|---|---|---|
| `max.poll.interval.ms` | Khoảng thời gian tối đa giữa hai lần gọi `poll()` của ứng dụng | Consumer không tiếp tục poll đúng hạn và có thể bị loại khỏi group |
| `session.timeout.ms` | Khoảng thời gian coordinator chờ heartbeat hợp lệ từ member trong classic group protocol | Coordinator coi member đã mất và kích hoạt thay đổi membership |
| `heartbeat.interval.ms` | Tần suất consumer gửi heartbeat trong classic group protocol | Điều chỉnh nhịp heartbeat; thường nhỏ hơn đáng kể so với session timeout |

### 2.1. max.poll.interval.ms

`max.poll.interval.ms` giới hạn thời gian giữa hai lần gọi `poll()`. Sau khi `poll()` trả về một batch, ứng dụng có thể xử lý các record trước khi gọi poll tiếp theo. Nếu xử lý batch quá lâu và khoảng cách giữa hai lần poll vượt giới hạn, consumer bị coi là không còn tiến triển đúng hạn.

Đây là cơ chế bảo vệ group khỏi một consumer vẫn còn process nhưng không tiếp tục lấy dữ liệu. Ví dụ, listener xử lý từng record trong 20 giây, còn poll trả về 30 record; thời gian xử lý batch có thể vượt xa poll interval nếu ứng dụng xử lý tuần tự.

Cần nhớ: `max.poll.interval.ms` không phải thời gian tối đa để broker trả lời một fetch request. Nó kiểm soát nhịp gọi poll của ứng dụng.

### 2.2. session.timeout.ms

Trong classic group protocol, coordinator chờ heartbeat từ consumer. Nếu không nhận được heartbeat trong khoảng `session.timeout.ms`, member bị coi là đã mất.

Kafka Java consumer có cơ chế heartbeat nền, nên trong nhiều trường hợp heartbeat vẫn được gửi khi ứng dụng đang xử lý record. Tuy nhiên, nếu ứng dụng không gọi poll vượt `max.poll.interval.ms`, client có thể chủ động rời group hoặc ngừng duy trì membership theo hành vi của protocol và loại member.

Nếu JVM bị stop-the-world GC, cả poll thread lẫn heartbeat thread đều có thể bị dừng. Khi khoảng dừng đủ dài, session timeout cũng có thể bị vượt.

### 2.3. heartbeat.interval.ms

Trong classic group protocol, `heartbeat.interval.ms` xác định nhịp gửi heartbeat. Giá trị thường được đặt thấp hơn đáng kể so với `session.timeout.ms`; một hướng dẫn phổ biến là không lớn hơn khoảng một phần ba session timeout.

Giảm heartbeat interval có thể giúp coordinator nhận biết member nhanh hơn và có nhiều cơ hội gửi heartbeat trước khi session timeout. Tuy nhiên, nó không sửa được GC pause dài, network partition hoặc poll loop bị block. Gửi heartbeat thường xuyên hơn cũng không làm record xử lý nhanh hơn.

### 2.4. Lưu ý về consumer group protocol mới

Kafka có các phiên bản và group protocol khác nhau. Với protocol `classic`, các cấu hình client như `heartbeat.interval.ms` và `session.timeout.ms` có vai trò như mô tả trên. Với consumer group protocol mới, một số nhịp heartbeat và timeout được điều khiển phía broker thay vì dùng các cấu hình client cũ. Hãy kiểm tra phiên bản Kafka, `group.protocol` và tài liệu cấu hình tương ứng trước khi thay đổi timeout.

## 3. Poll chậm: nguyên nhân trực tiếp thường gặp

Mẫu xử lý đơn giản thường có dạng:

~~~java
while (running) {
    ConsumerRecords<String, OrderEvent> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        process(record);
    }
}
~~~

Đoạn mã dễ hiểu nhưng toàn bộ thời gian xử lý record nằm giữa hai lần poll. Nếu batch lớn hoặc `process()` chậm, consumer có thể vượt `max.poll.interval.ms`.

Thời gian giữa hai lần poll có thể bao gồm:

- Thời gian xử lý tất cả record trả về trong batch.
- Gọi database hoặc dịch vụ HTTP đồng bộ.
- Retry và backoff thực hiện ngay trong poll thread.
- Chờ lock, connection pool hoặc thread khác.
- Ghi file, gọi API bên ngoài hoặc thực hiện tác vụ CPU nặng.
- GC pause và scheduling delay.

### 3.1. Ước lượng thời gian xử lý batch

Nếu poll trả về tối đa \(N\) record và thời gian xử lý p99 mỗi record là \(T_r\), ước lượng thận trọng ban đầu cho xử lý tuần tự là:

\[
T_{batch} \approx N \times T_r + T_{overhead}
\]

Ví dụ:

- `max.poll.records = 200`
- Thời gian xử lý p99 mỗi record khoảng 250 ms
- Thời gian xử lý tuần tự ước lượng khoảng 50 giây, chưa tính retry, database contention và GC.

Nếu `max.poll.interval.ms` là 60 giây, khoảng dự phòng có thể quá nhỏ. Chỉ một đợt downstream chậm cũng có thể khiến consumer vượt timeout.

Đây là phép ước lượng để sizing, không phải cam kết thời gian thực. Phải đo thời gian xử lý batch thực tế, gồm cả tail latency và thời gian chờ downstream.

### 3.2. Giảm max.poll.records khi batch quá lớn

`max.poll.records` giới hạn số record tối đa được trả về trong một lần poll. Giảm giá trị này có thể làm mỗi batch xử lý nhanh hơn, giúp ứng dụng gọi poll thường xuyên hơn.

Ví dụ:

~~~properties
max.poll.records=100
max.poll.interval.ms=300000
~~~

Giảm batch size có thể giảm throughput nếu ứng dụng tận dụng xử lý batch hiệu quả hoặc mỗi lần poll có overhead lớn. Hãy benchmark với kích thước record và thời gian xử lý thực tế.

`max.poll.records` không giới hạn tổng byte fetch từ broker. Các cấu hình fetch như `fetch.max.bytes` và `max.partition.fetch.bytes` điều khiển lượng dữ liệu fetch ở tầng khác.

### 3.3. Không chờ retry dài trong poll thread

Nếu một record gặp lỗi database và listener sleep 30 giây rồi retry, poll loop cũng bị dừng trong thời gian đó. Nếu nhiều record liên tiếp lỗi, khoảng cách giữa hai lần poll có thể vượt giới hạn.

Nên phân loại lỗi và chọn cách xử lý:

- Lỗi tạm thời: retry có giới hạn, backoff được quản lý.
- Lỗi dữ liệu cố định: chuyển dead-letter topic (DLT) hoặc quy trình cách ly.
- Downstream quá tải: pause partition hoặc áp dụng backpressure, đồng thời vẫn duy trì poll.
- Tác vụ kéo dài: đưa vào worker pool có giới hạn và quản lý offset theo partition.

Retry vô hạn trong listener là một nguyên nhân phổ biến làm group không tiến triển.

## 4. GC pause có thể làm mất membership như thế nào?

GC pause là khoảng thời gian JVM tạm dừng một phần hoặc toàn bộ application thread để thu gom bộ nhớ. Stop-the-world pause dài có thể ảnh hưởng đồng thời đến poll thread và heartbeat thread.

Ví dụ:

~~~text
Thời điểm 0s: consumer gửi heartbeat bình thường
Thời điểm 5s: JVM bắt đầu stop-the-world GC
Thời điểm 20s: GC kết thúc
Thời điểm 21s: consumer tiếp tục poll và heartbeat
~~~

Nếu khoảng dừng đủ dài so với timeout, coordinator có thể đã coi consumer là mất. Khi consumer tiếp tục chạy, nó có thể phải tham gia lại group và nhận assignment mới.

GC có thể liên quan đến:

- Heap quá nhỏ hoặc allocation rate quá cao.
- Record payload lớn, deserialize tạo nhiều object.
- Batch quá lớn.
- Cache hoặc collection tăng không giới hạn.
- Logging và chuyển đổi object tốn nhiều allocation.
- Memory leak hoặc giữ reference khiến heap tăng liên tục.
- JVM bị áp giới hạn container memory không phù hợp.

### 4.1. Cách xác định GC có phải nguyên nhân không

Đối chiếu timestamp của rebalance với GC log và metrics JVM:

- Thời gian pause của từng GC event.
- Tần suất full GC hoặc concurrent cycle.
- Heap occupancy trước và sau GC.
- Allocation rate và promoted bytes.
- CPU throttling và container memory pressure.
- Thread dump quanh thời điểm consumer mất poll/heartbeat.

Có thể bật GC logging phù hợp với phiên bản JDK đang dùng, ví dụ với JDK hiện đại:

~~~text
-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags
~~~

Dùng Java Flight Recorder (JFR) để phân tích allocation, GC pause, thread scheduling và lock contention. Không kết luận GC là nguyên nhân chỉ vì heap sử dụng cao; cần có bằng chứng pause hoặc CPU/safepoint trùng thời điểm rebalance.

### 4.2. Cách giảm GC pause

- Chọn heap phù hợp với giới hạn memory của container.
- Giảm allocation không cần thiết trong đường xử lý record.
- Tránh deserialize lặp lại cùng payload.
- Giới hạn batch và kích thước payload.
- Dùng streaming hoặc xử lý theo batch khi thư viện hỗ trợ.
- Loại bỏ cache không giới hạn và giữ object lâu hơn cần thiết.
- Đo lại với workload production-like sau khi thay đổi JVM.

Đổi garbage collector hoặc tăng heap không tự động giải quyết mọi pause. Cần dựa trên GC log, JFR và giới hạn tài nguyên thực tế.

## 5. Kết nối mạng không ổn định và heartbeat thất bại

Consumer phải giao tiếp với broker và group coordinator. Network instability có thể làm heartbeat hoặc request bị trễ, mất gói hoặc timeout.

Các nguyên nhân thường gặp:

- Packet loss hoặc latency tăng đột biến.
- DNS phân giải broker hostname không ổn định.
- Firewall hoặc NAT đóng kết nối nhàn rỗi.
- Network policy hoặc service mesh reset connection.
- Broker bị quá tải và phản hồi chậm.
- TLS handshake hoặc certificate rotation gây gián đoạn.
- Client kết nối bootstrap server được nhưng không truy cập được advertised.listeners của broker khác.
- Network giữa consumer và coordinator bị gián đoạn dù đường tới broker partition leader vẫn hoạt động.

### 5.1. Phân biệt poll timeout và heartbeat timeout

Nếu log báo consumer không poll đúng hạn hoặc vượt `max.poll.interval.ms`, hãy kiểm tra thời gian xử lý ứng dụng, GC và scheduling.

Nếu log thể hiện heartbeat thất bại, coordinator không truy cập được hoặc session timeout, hãy kiểm tra network, broker và JVM pause.

Một sự cố mạng cũng có thể gây cả hai: request bị treo khiến xử lý chậm, trong khi heartbeat không đến coordinator. Cần đối chiếu log client, broker và hạ tầng theo cùng timestamp.

### 5.2. Không chỉ tăng timeout để che network lỗi

Tăng `session.timeout.ms` có thể giúp group chịu được một khoảng gián đoạn ngắn hơn, nhưng cũng làm thời gian phát hiện consumer chết kéo dài hơn. Nếu network thường xuyên mất gói hoặc DNS sai, timeout lớn chỉ làm sự cố kéo dài và khó quan sát.

Hãy kiểm tra:

- Packet loss, round-trip latency và TCP retransmission.
- DNS resolution và địa chỉ broker quảng bá.
- Firewall idle timeout và connection reset.
- Broker request latency, network processor và request queue.
- TLS certificate expiry, truststore và SASL authentication.
- Kết nối từ đúng subnet/container nơi consumer chạy.

## 6. Cấu hình consumer để giảm rebalance do poll chậm

Một bộ cấu hình minh họa cho classic group protocol:

~~~properties
bootstrap.servers=broker-1:9092,broker-2:9092
group.id=billing-service

enable.auto.commit=false

max.poll.records=100
max.poll.interval.ms=300000

session.timeout.ms=45000
heartbeat.interval.ms=3000

partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Các giá trị trên chỉ là điểm khởi đầu. Chúng không phải cấu hình tối ưu cho mọi workload. Cần điều chỉnh dựa trên thời gian xử lý batch, độ trễ downstream, GC pause và network latency.

### 6.1. Chọn max.poll.interval.ms

Chọn giá trị lớn hơn thời gian xử lý batch ở tail latency, đồng thời để lại khoảng dự phòng cho:

- Database chậm.
- Retry hữu hạn.
- GC pause bình thường.
- CPU throttling hoặc scheduling delay.
- Logging và commit offset.

Không nên tăng quá lớn mà không có cảnh báo. Nếu consumer treo thật sự, group có thể mất nhiều thời gian hơn mới phát hiện nó không còn tiến triển.

### 6.2. Chọn max.poll.records

Chọn batch size sao cho consumer có thể xử lý và quay lại poll trước khi hết poll interval. Có thể bắt đầu từ giá trị thấp hơn, đo p95/p99 thời gian xử lý batch, sau đó tăng dần để tối ưu throughput.

### 6.3. Chọn session timeout và heartbeat

Trong classic protocol, heartbeat interval phải thấp hơn session timeout. Chọn session timeout đủ chịu được các gián đoạn ngắn có thể xảy ra trong môi trường, nhưng không quá lớn khiến failover chậm.

Nếu dùng group protocol mới, kiểm tra cấu hình broker và client tương ứng vì một số tham số heartbeat/session được quản lý khác với classic protocol.

## 7. Dùng pause/resume để tạo backpressure mà vẫn poll

Khi downstream quá tải, consumer có thể tạm dừng nhận record từ một hoặc nhiều partition bằng `pause()`. Poll loop vẫn tiếp tục gọi `poll()` để duy trì tiến trình group và nhận các sự kiện quản lý cần thiết.

Mô hình:

~~~text
Consumer poll loop
       |
       v
Kiểm tra worker queue / downstream
       |
       +-- Queue đầy --> pause(partitions)
       |                    |
       |                    v
       |              tiếp tục poll()
       |
       +-- Queue giảm --> resume(partitions)
                            |
                            v
                       xử lý tiếp
~~~

Ví dụ Java minh họa, giả định tất cả thao tác KafkaConsumer được thực hiện trên cùng poll thread:

~~~java
int maxPollRecords = 100; // Phải khớp với cấu hình max.poll.records.

while (running) {
    // Đọc assignment hiện tại sau mỗi poll/rebalance.
    Set<TopicPartition> assigned = consumer.assignment();

    if (!assigned.isEmpty()) {
        if (workerQueue.remainingCapacity() < maxPollRecords) {
            consumer.pause(assigned);
        } else {
            consumer.resume(assigned);
        }
    }

    ConsumerRecords<String, OrderEvent> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        if (!workerQueue.offer(toTask(record))) {
            // Invariant capacity đã bị vi phạm: dừng xử lý và không commit
            // offset vượt qua record này. Production code cần shutdown an toàn.
            throw new IllegalStateException("Worker queue capacity invariant violated");
        }
    }
}
~~~

Đây là khung minh họa với các giả định: worker queue có dung lượng ít nhất bằng max.poll.records, chỉ poll thread thêm task vào queue, và assignment được đọc lại sau mỗi poll. Khi remaining capacity nhỏ hơn số record tối đa có thể trả về, consumer pause các partition trước lần poll tiếp theo nhưng vẫn tiếp tục poll để duy trì membership. Nếu invariant dung lượng bị vi phạm, ứng dụng phải dừng an toàn và không commit offset vượt qua record chưa được enqueue; không được âm thầm bỏ record.

Các điểm quan trọng:

- `pause()` không làm consumer rời group.
- Tiếp tục gọi poll trong khi partition đang pause.
- Gọi pause/resume trên thread sở hữu KafkaConsumer vì KafkaConsumer không thread-safe.
- Khi partition được gán mới, cập nhật tập partition cần pause theo trạng thái backpressure hiện tại.
- Không để buffer trung gian tăng không giới hạn.

## 8. Worker pool: giảm thời gian xử lý trong poll thread nhưng giữ offset an toàn

Một cách khác là để poll thread nhận record nhanh rồi gửi tác vụ sang worker pool. Cách này có thể tăng throughput cho xử lý I/O-bound, nhưng làm việc quản lý offset và thứ tự phức tạp hơn.

Mô hình:

~~~text
KafkaConsumer poll thread
       |
       v
ConsumerRecords
       |
       v
Bounded worker queue
       |
       +--> Worker 1
       +--> Worker 2
       +--> Worker 3
       |
       v
Completion tracker theo partition
       |
       v
Commit offset liên tục đã xử lý xong
~~~

### 8.1. Dùng queue có giới hạn

Không dùng cached thread pool hoặc queue không giới hạn cho record đến từ Kafka. Nếu downstream chậm, task sẽ tích tụ, tiêu thụ memory và cuối cùng tạo GC pressure.

Dùng bounded queue và pause partition khi queue đạt ngưỡng cao. Resume khi queue giảm dưới ngưỡng thấp để tránh pause/resume liên tục.

### 8.2. Commit theo offset liên tục đã hoàn tất

Giả sử một partition trả về offset 10, 11 và 12. Worker xử lý offset 12 xong trước offset 10. Consumer không được commit vượt qua offset 10 nếu các record trước nó chưa hoàn thành.

Kafka commit lưu offset tiếp theo cần đọc. Nếu offset 10 là record đầu tiên chưa hoàn tất, không được commit offset 13 chỉ vì record 12 đã xong. Cần theo dõi tiến độ hoàn tất liên tục theo từng partition.

### 8.3. Bảo vệ thứ tự nghiệp vụ

Nếu các event cùng key cần xử lý tuần tự, có thể:

- Dùng worker lane theo partition hoặc theo key.
- Đảm bảo một key chỉ có một tác vụ đang chạy.
- Dùng sequence/version để phát hiện event đến sai thứ tự.
- Dùng idempotency để chịu được record được giao lại.
- Chỉ commit sau khi các tác vụ trước đó trong partition đã hoàn tất.

Không nên chuyển record sang worker pool rồi commit ngay sau khi enqueue. Nếu process chết trước khi worker hoàn thành, record đã bị commit có thể không được đọc lại.

## 9. Rebalance listener và xử lý partition được thu hồi

Khi group rebalance, ứng dụng cần xử lý trạng thái công việc đang chạy cho các partition được thu hồi.

Kafka Java API cung cấp `ConsumerRebalanceListener` với các callback như:

- `onPartitionsRevoked()`: partition sắp bị thu hồi trong quá trình rebalance; ứng dụng có thể hoàn tất hoặc commit tiến độ an toàn.
- `onPartitionsAssigned()`: partition mới được gán; ứng dụng có thể khởi tạo state hoặc resume/pause phù hợp.
- `onPartitionsLost()`: partition đã mất quyền sở hữu; không được giả định ứng dụng còn quyền commit hoặc tiếp tục xử lý như trước.

Ví dụ:

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            // Chỉ commit offset của record đã xử lý liên tục và an toàn.
            commitCompletedOffsets(partitions);
            stopOrDrainTasks(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            initializePartitionState(partitions);
        }

        @Override
        public void onPartitionsLost(
                Collection<TopicPartition> partitions) {
            // Partition đã mất; hủy tác vụ chưa hoàn tất
            // hoặc bảo đảm chúng không ghi side effect lỗi thời.
            cancelTasks(partitions);
        }
    }
);
~~~

Các hàm trong ví dụ là placeholder cho logic ứng dụng. Việc drain worker phải có giới hạn thời gian; không để callback rebalance block vô hạn. Nếu partition đã lost, một consumer khác có thể đang xử lý partition đó, vì vậy task cũ không được tiếp tục ghi side effect không được bảo vệ.

Với xử lý bất đồng bộ, cần có completion tracker để biết record nào đã hoàn tất trước khi commit. Nếu không kịp hoàn tất trong thời gian thu hồi, để record được đọc lại thường an toàn hơn commit vượt qua công việc chưa xong.

## 10. Cooperative rebalancing và static membership

Hai cơ chế này có thể giảm gián đoạn do thay đổi membership, nhưng không sửa được nguyên nhân gốc của rebalance lặp.

### 10.1. CooperativeStickyAssignor

Eager rebalance thường thu hồi toàn bộ assignment trước khi phân phối lại. Cooperative rebalancing cho phép chuyển partition theo từng phần, giảm số partition phải dừng cùng lúc.

Với Java consumer classic protocol, có thể cấu hình:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Cần bảo đảm tất cả member trong group có cấu hình assignor tương thích. Chuyển đổi assignor nên theo quy trình rollout phù hợp phiên bản Kafka và cấu hình hiện có.

Cooperative assignor giảm phạm vi gián đoạn trong một số lần rebalance. Nó không ngăn member bị loại vì poll quá chậm, GC pause hoặc network mất kết nối.

### 10.2. Static membership

Cấu hình `group.instance.id` cho phép một consumer có định danh thành viên ổn định. Khi instance tạm thời restart và quay lại với cùng ID trong giới hạn timeout, Kafka có thể giữ assignment lâu hơn và tránh một số rebalance không cần thiết.

Ví dụ:

~~~properties
group.id=billing-service
group.instance.id=billing-worker-03
~~~

Mỗi instance chạy đồng thời trong group phải có `group.instance.id` duy nhất. Nếu nhiều process dùng trùng ID, một member có thể bị fencing hoặc bị thay thế.

Static membership hữu ích với restart ngắn hoặc rollout có kiểm soát. Nó không phải cách chữa poll loop bị block kéo dài. Với static member vượt `max.poll.interval.ms`, việc thu hồi partition có thể được trì hoãn đến khi session timeout hết; điều này có thể kéo dài thời gian failover nếu instance thực sự đã chết.

## 11. Cấu hình và xử lý trong Spring Kafka

Với Spring Kafka, listener container quản lý poll loop và consumer lifecycle. Tuy nhiên, nếu listener chạy đồng bộ lâu, thread xử lý listener cũng làm chậm nhịp poll tiếp theo.

Ví dụ cấu hình consumer factory:

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> consumerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                   "localhost:9092");
    properties.put(ConsumerConfig.GROUP_ID_CONFIG,
                   "billing-service");
    properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                   false);
    properties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
                   100);
    properties.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG,
                   300_000);
    properties.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG,
                   45_000);
    properties.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG,
                   3_000);

    return new DefaultKafkaConsumerFactory<>(
        properties,
        new StringDeserializer(),
        new JsonDeserializer<>(OrderEvent.class, false)
    );
}
~~~

Đây là ví dụ cho classic group protocol; hãy kiểm tra phiên bản Kafka client và Spring Kafka đang dùng, đặc biệt nếu chuyển sang consumer group protocol mới.

### 11.1. Giới hạn concurrency theo partition

Có thể dùng concurrency của listener container để tạo nhiều consumer instance trong cùng group:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);
    return factory;
}
~~~

Concurrency không làm một partition được gán đồng thời cho nhiều member trong cùng group. Đặt concurrency cao hơn partition count không giải quyết poll chậm của một partition nóng.

### 11.2. Giữ listener ngắn và có giới hạn

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void consume(OrderEvent event) {
    billingService.processQuickly(event);
}
~~~

Nếu `processQuickly` thực tế gọi nhiều dịch vụ hoặc chờ database lâu, listener vẫn có thể vượt poll interval. Khi đó cần tối ưu downstream, xử lý theo batch phù hợp, pause/resume container hoặc chuyển sang mô hình xử lý bất đồng bộ có quản lý offset.

Không nên tự tạo thread cho từng record bên trong listener mà không giới hạn queue và không có completion tracker. Cách đó chỉ chuyển vấn đề từ poll thread sang memory và offset management.

## 12. Chẩn đoán rebalance storm theo bằng chứng

Hãy đối chiếu log consumer, broker, JVM và network theo cùng một khoảng thời gian.

### 12.1. Kiểm tra trạng thái group và lag

Dùng CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --group billing-service
~~~

Quan sát:

- Member có thay đổi liên tục không?
- Partition có thường xuyên đổi consumer ID không?
- Lag tăng trên toàn group hay chỉ một vài partition?
- Có partition nào bị kẹt ở cùng offset?
- Thời điểm assignment thay đổi có trùng với deploy hoặc restart không?

Tùy phiên bản Kafka, có thể dùng thêm tùy chọn hiển thị member và assignment chi tiết.

### 12.2. Kiểm tra log consumer

Tìm các thông báo liên quan đến:

- Poll interval exceeded hoặc consumer không tiếp tục poll.
- Heartbeat failed hoặc session timeout.
- Member bị removed khỏi group.
- Rebalance started/completed.
- Coordinator unavailable hoặc coordinator discovery.
- Commit failed do generation/member thay đổi.

Log message và tên exception có thể khác giữa các phiên bản client. Hãy lấy nguyên nhân gốc và timestamp thay vì chỉ tìm một chuỗi log cố định.

### 12.3. Kiểm tra consumer metrics

Các metric hữu ích tùy phiên bản client và cách expose:

| Metric/nhóm metric | Dấu hiệu cần quan sát |
|---|---|
| `time-between-poll-max` hoặc poll timing | Khoảng cách giữa các lần poll tăng cao |
| `last-poll-seconds-ago` | Consumer đã lâu không gọi poll |
| `poll-idle-ratio-avg` | Poll loop dành bao nhiêu thời gian ở trạng thái idle |
| Heartbeat rate/response time | Heartbeat chậm, thất bại hoặc bị gián đoạn |
| Rebalance rate/total/latency | Tần suất và thời gian rebalance |
| `records-lag-max` | Lag lớn nhất theo partition |
| Commit latency/failure | Commit chậm hoặc thất bại trong lúc rebalance |
| Assigned partitions | Số partition và thay đổi assignment |

Tên metric cụ thể có thể khác theo phiên bản Kafka client và exporter. Không giả định mọi JMX exporter đều expose cùng tên.

### 12.4. Kiểm tra JVM và network

Đối chiếu:

- GC pause và safepoint log.
- CPU utilization và container CPU throttling.
- Heap occupancy, allocation rate và memory pressure.
- Thread dump xem poll thread đang xử lý, block hay chờ lock.
- Network RTT, packet loss, TCP retransmission và connection reset.
- Broker request latency, coordinator log và broker restart.

Nếu rebalance xảy ra đúng lúc GC pause 40 giây, trong khi session timeout là 30 giây, GC là nghi vấn mạnh. Nếu poll interval bị vượt nhưng heartbeat vẫn đều trước đó, hãy tập trung vào thời gian xử lý listener hoặc poll loop.

## 13. Quy trình khắc phục theo từng nguyên nhân

| Nguyên nhân | Biện pháp ưu tiên | Điều cần tránh |
|---|---|---|
| Xử lý batch quá lâu | Giảm max.poll.records, tối ưu handler, giới hạn retry | Chỉ tăng poll interval mà không đo batch time |
| Downstream chậm | Timeout rõ ràng, bulkhead, pause/resume, bounded queue | Chờ vô hạn trong listener |
| GC pause dài | Phân tích GC/JFR, giảm allocation, điều chỉnh heap và payload | Đổi GC hoặc tăng heap theo cảm tính |
| Network chập chờn | Sửa DNS, route, firewall, TLS, advertised.listeners | Tăng session timeout để che packet loss kéo dài |
| Rebalance do restart | Static membership nếu phù hợp, rollout có kiểm soát | Dùng group.instance.id trùng nhau |
| Assignment gây gián đoạn lớn | CooperativeStickyAssignor nếu tương thích | Nghĩ cooperative rebalance ngăn mọi rebalance |
| Worker pool quá tải | Bounded queue, pause partition, completion tracking | Queue không giới hạn và commit ngay khi enqueue |
| Một partition nóng | Xem lại key distribution và xử lý theo key | Thêm consumer mà không tăng partition hoặc đổi cách phân vùng |

Một trình tự xử lý thực tế:

1. Ghi lại thời điểm rebalance và member bị ảnh hưởng.
2. Xác định nguyên nhân là poll interval, heartbeat/session hay coordinator/network.
3. Đo p95/p99 thời gian xử lý batch và thời gian GC pause.
4. Kiểm tra network từ đúng môi trường chạy consumer.
5. Điều chỉnh batch size hoặc xử lý downstream trước.
6. Chỉ thay timeout sau khi có số đo phù hợp.
7. Cân nhắc cooperative rebalance hoặc static membership nếu mô hình triển khai phù hợp.
8. Theo dõi lag, rebalance rate và thời gian poll sau thay đổi.

## 14. Checklist phòng ngừa rebalance lặp

| Hạng mục | Câu hỏi kiểm tra |
|---|---|
| Poll loop | Có gọi poll đều đặn trong mọi trạng thái backpressure không? |
| Batch size | Thời gian xử lý p99 của một batch có thấp hơn max.poll.interval với khoảng dự phòng không? |
| Downstream | Có timeout hữu hạn và retry có giới hạn không? |
| GC | Có GC pause hoặc safepoint dài trùng thời điểm rebalance không? |
| Network | Có packet loss, DNS lỗi hoặc connection reset không? |
| Heartbeat | Session timeout và heartbeat interval có phù hợp với group protocol không? |
| Worker pool | Queue có giới hạn và có pause/resume theo ngưỡng không? |
| Offset | Chỉ commit offset liên tục đã xử lý thành công theo từng partition? |
| Rebalance callback | Có xử lý revoked, assigned và lost an toàn không? |
| Assignment | Có cân nhắc cooperative assignor khi phù hợp không? |
| Static membership | group.instance.id có duy nhất và ổn định không? |
| Monitoring | Có cảnh báo rebalance rate, lag, poll interval và GC pause không? |

## 15. Những nhầm lẫn thường gặp

- **“Heartbeat còn gửi được thì consumer không thể bị rebalance.”** Consumer vẫn có thể vượt max.poll.interval.ms dù heartbeat nền đang hoạt động.
- **“max.poll.interval.ms là thời gian chờ broker trả lời poll.”** Nó giới hạn khoảng cách giữa hai lần gọi poll của ứng dụng.
- **“Tăng session.timeout.ms giải quyết poll chậm.”** Poll chậm được kiểm soát bởi max.poll.interval.ms; session timeout theo dõi heartbeat.
- **“Giảm heartbeat.interval.ms sẽ chữa network không ổn định.”** Heartbeat dày hơn không khắc phục packet loss, DNS hoặc broker mất kết nối.
- **“GC chỉ ảnh hưởng memory.”** Stop-the-world pause có thể dừng poll và heartbeat, làm member mất membership.
- **“pause() làm consumer rời group.”** Pause partition dừng fetch record từ partition đó nhưng consumer vẫn cần poll để duy trì hoạt động.
- **“Tăng concurrency luôn ngăn rebalance.”** Nhiều consumer hơn có thể làm tăng membership churn và không sửa được listener xử lý chậm.
- **“CooperativeStickyAssignor loại bỏ mọi rebalance.”** Nó giảm phạm vi thu hồi partition trong một số lần rebalance, không loại bỏ nguyên nhân member timeout.
- **“Đưa record vào worker pool rồi commit ngay là an toàn.”** Nếu process chết trước khi worker hoàn tất, record đã commit có thể bị mất khỏi luồng xử lý của ứng dụng.
- **“Static membership là cách chữa consumer treo.”** Static membership có thể trì hoãn việc thu hồi partition; nó không làm poll loop tiến triển.

## 16. Kết luận

Rebalance lặp thường là dấu hiệu consumer không duy trì được nhịp poll hoặc heartbeat ổn định. Xử lý record quá lâu có thể vượt `max.poll.interval.ms`; GC pause dài có thể chặn cả poll và heartbeat; network không ổn định có thể khiến coordinator không nhận được heartbeat trong `session.timeout.ms`.

Hãy đo thời gian giữa các lần poll, thời gian xử lý batch, GC pause và network latency để xác định đúng nguyên nhân. Giảm batch size khi cần, không block poll loop bằng retry dài, dùng bounded worker pool cùng pause/resume, commit offset liên tục đã xử lý an toàn và xử lý rebalance callback đúng cách. Cooperative rebalancing và static membership có thể giảm gián đoạn trong các tình huống phù hợp, nhưng hiệu quả lâu dài đến từ việc loại bỏ nguyên nhân khiến consumer liên tục bị coi là không hoạt động.
