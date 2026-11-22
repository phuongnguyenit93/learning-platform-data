# max.poll.records và thời gian xử lý

Trong Kafka consumer, max.poll.records giới hạn số record tối đa mà một lần gọi poll() trả về cho ứng dụng. Tham số này ảnh hưởng trực tiếp đến lượng công việc consumer nhận trong một chu kỳ poll, thời gian xử lý trước lần poll tiếp theo, kích thước batch, khả năng giữ nhịp với consumer group và nguy cơ bị rebalance.

Tham số cần được xem cùng max.poll.interval.ms. max.poll.interval.ms xác định khoảng thời gian tối đa consumer được phép không gọi poll() trước khi bị xem là không còn tiến triển. Nếu ứng dụng xử lý quá lâu sau một lần poll, consumer có thể vượt giới hạn này, rời group và kích hoạt rebalance. Consumer khác có thể nhận lại partition, còn công việc đang chạy ở consumer cũ có thể hoàn tất muộn và tạo duplicate nếu offset chưa được commit.

Mục tiêu cấu hình là chọn lượng record mỗi poll sao cho consumer xử lý kịp trong khoảng thời gian cho phép, đồng thời vẫn đạt throughput và sử dụng tài nguyên hợp lý. Tăng max.poll.records không tự động làm consumer nhanh hơn; nếu thời gian xử lý tăng theo số record, batch lớn có thể khiến poll tiếp theo đến quá muộn.

## 1. Vòng lặp poll và xử lý của consumer

Kafka consumer hoạt động theo vòng lặp: lấy dữ liệu, xử lý dữ liệu, ghi nhận tiến độ và tiếp tục poll. Trong một consumer đồng bộ đơn giản, chu kỳ có dạng:

~~~
poll()
  |
  v
Nhận tối đa max.poll.records record
  |
  v
Xử lý record / batch
  |
  v
Commit offset theo cấu hình
  |
  v
poll() lần tiếp theo
~~~

Consumer group dựa vào nhịp poll để biết consumer còn tham gia xử lý hay không. max.poll.interval.ms đặt giới hạn cho thời gian giữa hai lần gọi poll(). Nếu consumer không poll lại trong thời hạn này, coordinator có thể xem consumer đã bị treo hoặc không còn khả năng xử lý và bắt đầu thu hồi partition.

Một điểm quan trọng: poll() có thể trả về ít record hơn max.poll.records. Giá trị này là giới hạn trên của số record trả về trong một lần poll, không phải cam kết rằng mỗi lần poll luôn có đủ số record đó.

## 2. max.poll.records kiểm soát điều gì?

max.poll.records là cấu hình của Kafka consumer. Nó giới hạn số record tối đa mà consumer trả về từ một lần poll cho ứng dụng.

Ví dụ:

~~~properties
max.poll.records=100
~~~

Với cấu hình này, một lần poll trả về tối đa 100 record. Nếu dữ liệu sẵn có ít hơn, consumer nhận ít hơn. Nếu dữ liệu sẵn có nhiều hơn, phần còn lại sẽ được trả ở các lần poll sau.

Tham số này tác động đến:

- **Khối lượng xử lý mỗi chu kỳ:** batch lớn hơn có thể giảm overhead cố định trên mỗi record.
- **Thời gian giữa các lần poll:** nếu xử lý tuần tự, nhiều record hơn thường kéo dài thời gian xử lý trước lần poll tiếp theo.
- **Bộ nhớ và kích thước batch:** ứng dụng giữ nhiều record cùng lúc hơn, đặc biệt khi payload lớn hoặc listener chuyển đổi dữ liệu thành object.
- **Phạm vi retry và replay:** một batch lớn có thể khiến nhiều record phải được xử lý lại khi một lỗi làm batch rollback.
- **Độ trễ:** record ở đầu hoặc cuối batch có thời điểm bắt đầu xử lý khác nhau; batch lớn có thể làm record phía sau chờ lâu hơn.

max.poll.records không phải giới hạn tổng số byte được fetch từ broker. Kafka còn có các cấu hình fetch như max.partition.fetch.bytes và fetch.max.bytes. Consumer có thể fetch dữ liệu vào bộ đệm nội bộ trước khi ứng dụng lấy record qua poll(). Do đó, giảm max.poll.records không nhất thiết làm giảm ngay lượng byte mà client đã fetch hoặc giữ trong bộ nhớ.

Số record thực tế mỗi poll còn phụ thuộc dữ liệu có sẵn, partition được gán, kích thước record, giới hạn fetch và tiến độ đọc của consumer.

## 3. max.poll.interval.ms kiểm soát điều gì?

max.poll.interval.ms là thời gian tối đa consumer được phép không gọi poll() trước khi group xem consumer không còn tiến triển. Giá trị này cần lớn hơn thời gian xử lý của một chu kỳ poll, cộng với các khoảng thời gian liên quan trước lần poll tiếp theo.

Ví dụ cấu hình:

~~~properties
max.poll.interval.ms=300000
~~~

Giá trị 300.000 ms tương đương 5 phút. Nếu ứng dụng nhận một batch rồi mất hơn 5 phút mới gọi poll() tiếp theo, consumer có thể vượt giới hạn.

Không nên nhầm max.poll.interval.ms với session.timeout.ms:

| Cấu hình | Theo dõi điều gì? | Hệ quả khi vượt giới hạn |
|---|---|---|
| max.poll.interval.ms | Mức độ tiến triển của ứng dụng thông qua các lần gọi poll() | Consumer có thể rời group và partition được phân phối lại |
| session.timeout.ms | Khoảng thời gian coordinator không nhận heartbeat hợp lệ | Coordinator xem consumer mất kết nối và thực hiện rebalance |
| heartbeat.interval.ms | Nhịp gửi heartbeat trong cấu hình consumer group truyền thống | Ảnh hưởng tần suất heartbeat, thường được đặt thấp hơn session timeout |

Heartbeat và poll phục vụ hai mục đích khác nhau. Consumer có thể còn gửi heartbeat nhưng ứng dụng không gọi poll() đủ lâu. max.poll.interval.ms vẫn là giới hạn bảo vệ tiến độ xử lý. Cơ chế heartbeat cụ thể phụ thuộc consumer group protocol và phiên bản Kafka, nhưng không nên dùng heartbeat để thay thế việc bảo đảm poll đúng hạn.

## 4. Quan hệ giữa số record và thời gian xử lý

Với xử lý tuần tự, thời gian xử lý một chu kỳ có thể ước lượng bằng:

~~~
T_poll_cycle
  = T_poll_and_fetch
  + T_processing
  + T_commit
  + T_application_overhead
~~~

Nếu mỗi record có thời gian xử lý trung bình gần như ổn định:

~~~
T_processing ≈ N × T_record
~~~

Trong đó:

- N là số record thực tế được xử lý trong chu kỳ, không vượt max.poll.records.
- T_record là thời gian xử lý một record.
- T_poll_cycle là khoảng thời gian từ lần poll này đến lần poll tiếp theo.

Điều kiện vận hành là T_poll_cycle phải nhỏ hơn max.poll.interval.ms với khoảng dự phòng đủ lớn. Không nên thiết kế sát đúng giới hạn vì thời gian thực tế biến động do GC, tải database, network, broker, scheduler, retry và commit.

Ví dụ, nếu listener xử lý tuần tự mỗi record mất khoảng 250 ms và một poll trả về 400 record, riêng phần xử lý có thể mất khoảng 100 giây. Nếu max.poll.interval.ms là 60 giây, batch đó có nguy cơ vượt giới hạn ngay cả khi consumer và broker vẫn khỏe.

Đây chỉ là phép ước lượng ban đầu. Với hệ thống production, hãy đo trực tiếp thời gian của toàn bộ batch hoặc chu kỳ poll ở các percentile cao như p95 và p99. Thời gian từng record có phân phối không đồng đều; một vài record chậm có thể làm cả batch kéo dài.

### 4.1. Tính giới hạn batch từ ngân sách thời gian

Giả sử:

- max.poll.interval.ms là 300.000 ms.
- Ứng dụng dành 60.000 ms làm khoảng dự phòng cho commit, scheduling, GC và biến động.
- Thời gian xử lý tuần tự p95 của một record là 500 ms.

Ngân sách ước lượng cho phần xử lý là 240.000 ms. Số record tối đa theo ước lượng này:

~~~
N <= 240.000 / 500
N <= 480 record
~~~

Không nên coi 480 là giá trị cấu hình chắc chắn an toàn. p95 từng record không có nghĩa tổng thời gian của 480 record luôn nằm trong ngân sách. Hãy đo p95/p99 của cả batch ở tải thực tế, thử nghiệm với record chậm và chọn giới hạn thấp hơn nếu thời gian biến động lớn.

Nếu batch thực tế có thời gian p99 là 190 giây và max.poll.interval.ms là 300 giây, còn khoảng 110 giây dự phòng. Nếu p99 gần 295 giây, cấu hình đang quá sát giới hạn và một đợt GC hoặc dependency chậm có thể gây rebalance.

## 5. Cấu hình trong Spring Boot và Spring Kafka

Với Spring Boot, max.poll.records có thể cấu hình trực tiếp qua consumer properties. max.poll.interval.ms được truyền vào Kafka consumer properties.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
~~~

Các giá trị trên chỉ minh họa. Chúng cần được điều chỉnh theo broker, consumer group protocol, thời gian xử lý và SLO thực tế. Spring Kafka listener container thường quản lý việc commit offset theo AckMode; khi dùng container, hãy cấu hình ack mode và transaction phù hợp thay vì bật auto commit một cách tùy tiện.

Có thể cấu hình concurrency của listener container để nhiều consumer instance xử lý song song:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

Concurrency tạo nhiều consumer trong cùng listener container. Mỗi consumer có poll loop và giới hạn max.poll.interval.ms riêng. Tăng concurrency có thể tăng khả năng xử lý song song nếu topic có đủ partition và hệ thống phụ thuộc còn khả năng chịu tải. Nếu số partition ít hơn số consumer, một số consumer sẽ không có partition để xử lý.

Không nên tăng concurrency chỉ để bù cho một batch quá lớn hoặc một record xử lý quá chậm. Hãy xác định nút thắt nằm ở CPU, database, HTTP dependency, số partition hay thời gian xử lý từng record.

## 6. Record listener và batch listener

Spring Kafka hỗ trợ listener xử lý từng record và listener xử lý cả batch. Cách chọn listener ảnh hưởng đến cách tính thời gian và phạm vi công việc trong một poll.

### 6.1. Record listener

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    billingService.process(event);
}
~~~

Với record listener, container gọi listener cho từng record được lấy từ poll. Tuy listener nhận từng record, consumer vẫn phải tiếp tục poll theo nhịp của container. Nếu một poll trả về 100 record và mỗi lần gọi listener mất 2 giây, xử lý cả nhóm có thể mất khoảng 200 giây cộng overhead trước khi container poll tiếp.

Vì vậy, không nên chỉ nhìn thời gian xử lý một lần gọi listener. Hãy đo tổng thời gian từ khi container nhận kết quả poll đến khi nó có thể gọi poll tiếp theo.

### 6.2. Batch listener

Batch listener nhận danh sách record trong một lần gọi:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "batchOrdersListenerFactory"
)
public void handleBatch(List<OrderEvent> events) {
    billingService.processBatch(events);
}
~~~

Batch listener hữu ích khi dependency hỗ trợ thao tác bulk, chẳng hạn ghi nhiều dòng database trong một transaction hoặc gọi một API nhận danh sách. Khi đó thời gian xử lý có thể thấp hơn xử lý tuần tự từng record.

Tuy nhiên, batch lớn có thể:

- Tăng bộ nhớ dùng cho danh sách và object đã deserialize.
- Tăng thời gian hoàn tất một callback.
- Làm tăng số record phải xử lý lại nếu batch thất bại.
- Tạo độ trễ lớn cho record ở cuối batch.
- Tăng tải đột biến lên database hoặc dịch vụ downstream.

Chọn max.poll.records theo kích thước batch mà listener thực sự xử lý được trong giới hạn poll, không chỉ theo khả năng fetch của broker.

## 7. Điều gì xảy ra khi vượt max.poll.interval.ms?

Khi consumer không gọi poll() tiếp theo trong thời gian cho phép, group coordinator có thể xem consumer đã mất khả năng tiến triển và kích hoạt rebalance. Các partition đang được consumer giữ có thể được thu hồi và giao cho consumer khác.

Một chuỗi sự kiện điển hình:

~~~
Consumer A poll() nhận record
          |
          v
Xử lý batch quá lâu
          |
          v
Không gọi poll() trước max.poll.interval.ms
          |
          v
Consumer A rời group / bị thu hồi partition
          |
          v
Group rebalance
          |
          v
Consumer B nhận partition
          |
          v
Consumer B đọc từ offset đã commit gần nhất
~~~

Nếu consumer A chưa commit offset của các record đang xử lý, consumer B có thể đọc lại chúng. Đây là hành vi at-least-once thường gặp: record có thể được xử lý nhiều lần, nhưng không nên mất nếu offset chỉ được commit sau khi xử lý thành công và side effect được thiết kế phù hợp.

Một rủi ro khác là consumer A vẫn tiếp tục thực hiện side effect sau khi partition đã được giao cho consumer B. Khi đó cả hai có thể cùng tác động lên một nghiệp vụ. Cần dùng idempotency key, transaction ở tài nguyên đích hoặc cơ chế kiểm soát quyền sở hữu phù hợp.

Với static membership, hành vi thu hồi partition có thể khác về thời điểm: partition có thể được giữ đến khi session timeout thay vì được chuyển ngay khi max.poll.interval.ms bị vượt. Static membership không loại bỏ giới hạn tiến độ poll; nó chỉ thay đổi một số hành vi khi thành viên tạm thời ngừng poll.

## 8. Commit offset và phạm vi xử lý

max.poll.records quyết định lượng record có thể được trả về trong poll; AckMode và cách commit quyết định offset nào được ghi nhận là đã xử lý. Hai khái niệm này liên quan nhưng không thay thế nhau.

Với Spring Kafka:

- AckMode.RECORD commit offset sau khi listener xử lý thành công từng record theo cơ chế container.
- AckMode.BATCH commit offset của các record đã xử lý trong batch khi batch hoàn tất.
- AckMode.MANUAL và MANUAL_IMMEDIATE cho phép listener điều khiển acknowledgement theo cấu hình và ngữ cảnh thực thi.
- Kafka transaction có thể đưa offset đã xử lý vào cùng transaction với record đầu ra khi container được cấu hình transactional phù hợp.

Nếu batch listener xử lý một phần rồi thất bại, hành vi retry và commit phụ thuộc AckMode, error handler, batch listener semantics và cấu hình transaction. Hãy xác định rõ record nào đã hoàn tất, record nào phải đọc lại và side effect có thể lặp hay không.

Không commit offset trước khi công việc cần bảo vệ đã thành công. Nếu commit offset quá sớm rồi ứng dụng lỗi, record có thể bị bỏ qua khi consumer khởi động lại. Ngược lại, nếu side effect đã thành công nhưng offset chưa commit, record có thể được xử lý lại; idempotency giúp xử lý trường hợp này.

## 9. Xử lý record chậm và dependency không ổn định

Một record có thể mất thời gian lâu hơn nhiều so với phần còn lại vì database lock, API timeout, retry, payload lớn hoặc xử lý CPU nặng. Nếu một record chậm làm cả poll cycle vượt giới hạn, cần xử lý nguyên nhân ở cấp record và ở cấp batch.

### 9.1. Đặt timeout cho dependency

Mỗi lần gọi database hoặc HTTP nên có timeout hữu hạn. Nếu một listener có thể chờ vô hạn, consumer có thể ngừng poll vô thời hạn.

Ví dụ, nếu một record gọi ba dependency tuần tự, tổng thời gian tối đa có thể là tổng timeout của cả ba cộng thời gian xử lý cục bộ. Hãy tính tổng ngân sách này vào thời gian xử lý một poll.

### 9.2. Giảm batch khi có record chậm

Giảm max.poll.records làm giảm số record tối đa cần xử lý trong một chu kỳ. Điều này có thể đưa poll cycle về dưới max.poll.interval.ms, đổi lại tăng số lần poll và có thể tăng overhead.

Nếu chỉ một loại record có xử lý rất chậm, cân nhắc tách luồng/topic hoặc xử lý loại công việc đó bằng worker chuyên biệt. Một batch chung với thời gian xử lý rất khác nhau khiến việc chọn một giới hạn batch tối ưu trở nên khó khăn.

### 9.3. Dùng pause/resume khi cần chờ

Spring Kafka listener container hỗ trợ pause và resume để tạm ngừng nhận thêm record trong khi container vẫn duy trì vòng lặp poll theo cơ chế của nó. Đây là cách hữu ích khi downstream đang quá tải hoặc ứng dụng cần chờ một điều kiện phục hồi.

Pause không có nghĩa là consumer ngừng mọi hoạt động. Container vẫn cần tiếp tục poll để duy trì trạng thái group và xử lý điều khiển. Hãy dùng API pause/resume của listener container và kiểm tra hành vi theo phiên bản Spring Kafka đang chạy.

### 9.4. Tránh offload tùy tiện khỏi consumer thread

Đẩy công việc sang executor có thể giúp consumer thread gọi poll() đều hơn, nhưng tạo thêm bài toán về offset và quyền sở hữu partition. Nếu listener trả về trước khi công việc hoàn tất, container có thể commit offset trong khi side effect chưa xong.

Nếu dùng xử lý bất đồng bộ:

- Chỉ acknowledge/commit sau khi công việc tương ứng hoàn tất.
- Bảo đảm xử lý kết quả theo partition và thứ tự nếu nghiệp vụ yêu cầu ordering.
- Xử lý partition revoke trong khi task còn chạy.
- Không gọi trực tiếp các API Kafka Consumer từ thread tùy ý; consumer không an toàn cho truy cập đồng thời nói chung.
- Dùng cơ chế async acknowledgment hoặc listener/container support đúng phiên bản và hiểu rõ việc container có thể pause để chờ các acknowledgment còn thiếu.

Offload chỉ cải thiện poll cadence nếu thiết kế commit, backpressure và rebalance được giải quyết đầy đủ.

## 10. Retry và backoff có thể làm poll chậm như thế nào?

Nếu error handler thực hiện retry blocking ngay trong luồng listener/container, thời gian retry và backoff cũng được tính vào khoảng thời gian trước lần poll tiếp theo. Ví dụ, 5 lần retry với backoff lần lượt 1, 2, 4, 8 và 16 giây đã tiêu tốn 31 giây, chưa tính thời gian xử lý và commit.

Với retry kéo dài:

- Tính tổng thời gian xử lý cộng backoff vào ngân sách max.poll.interval.ms.
- Dùng cơ chế pause container khi phù hợp để duy trì poll trong lúc chờ.
- Cân nhắc non-blocking retry topic nếu nghiệp vụ cho phép thay đổi thứ tự và luồng xử lý.
- Tránh retry đồng bộ lâu trên consumer thread khi nhiều partition dùng chung consumer.

Non-blocking retry chuyển record sang topic retry và cho phép consumer tiếp tục, nhưng có thể thay đổi thứ tự xử lý giữa các record cùng key hoặc partition. Chọn cách retry dựa trên yêu cầu ordering, không chỉ dựa trên throughput.

## 11. Ảnh hưởng của concurrency và số partition

Trong Spring Kafka, concurrency của ConcurrentMessageListenerContainer tạo nhiều child listener container, mỗi child có consumer riêng. Số consumer thực sự hoạt động bị giới hạn bởi số partition được gán.

Ví dụ topic có 6 partition:

- Concurrency 1: một consumer xử lý cả 6 partition.
- Concurrency 3: tối đa 3 consumer có thể nhận partition, trung bình 2 partition mỗi consumer nếu assignment cân bằng.
- Concurrency 6: tối đa 6 consumer có thể xử lý song song, mỗi consumer có thể nhận một partition.
- Concurrency 10: có thể có consumer không được gán partition.

max.poll.records áp dụng cho từng consumer, không phải tổng batch của toàn bộ listener container. Với concurrency 3 và max.poll.records 100, một poll của mỗi consumer có thể trả tối đa 100 record; tổng số record đang được các consumer xử lý có thể lớn hơn 100.

Tăng concurrency làm tăng số poll loop song song và tổng khả năng xử lý, nhưng cũng tăng số kết nối, bộ nhớ, tải database và số tác vụ đồng thời. Nếu database chỉ chịu được 10 truy vấn đồng thời, tăng concurrency lên 30 có thể làm thời gian xử lý tăng thay vì giảm.

Hãy điều chỉnh concurrency theo số partition và capacity của downstream. Theo dõi thời gian xử lý theo từng consumer để phát hiện phân phối tải không đều hoặc partition có record nặng.

## 12. Đọc metric để biết có cần điều chỉnh hay không

Không nên điều chỉnh max.poll.records chỉ dựa trên consumer lag. Lag tăng có thể do tốc độ producer vượt tốc độ xử lý, dependency chậm, ít partition, phân phối key lệch hoặc consumer liên tục rebalance.

Các tín hiệu hữu ích:

| Tín hiệu | Cách diễn giải |
|---|---|
| Thời gian giữa hai lần poll | Có đang tiến gần max.poll.interval.ms không? |
| Thời gian xử lý mỗi record và mỗi batch | Batch hiện tại có nằm trong ngân sách thời gian không? |
| Số record thực tế mỗi poll | Có thường xuyên đạt max.poll.records hay không? |
| Consumer lag theo partition | Partition nào đang tụt lại? |
| Rebalance count và duration | Consumer có bị thu hồi partition thường xuyên không? |
| Commit latency và commit failure | Commit có làm poll cycle kéo dài không? |
| Retry count và backoff duration | Error handler có giữ consumer thread quá lâu không? |
| CPU, GC pause và heap | Consumer có bị giới hạn bởi tài nguyên JVM không? |
| Database/API latency | Dependency nào kéo dài thời gian xử lý? |

Metric consumer có thể được export qua Kafka client JMX, Micrometer hoặc hệ thống observability của ứng dụng. Tên metric và cách gắn tag phụ thuộc phiên bản. Hãy xác minh metric thực tế và gắn nhãn theo group, client và topic/partition ở mức cardinality có kiểm soát.

### 12.1. Ví dụ đọc tình huống

**Lag tăng, thời gian xử lý batch thấp, không có rebalance:** có thể throughput tổng không đủ so với tốc độ producer. Kiểm tra concurrency, số partition, CPU và khả năng xử lý bulk trước khi tăng max.poll.records.

**Lag tăng, thời gian batch gần max.poll.interval.ms, rebalance tăng:** batch có thể quá lớn hoặc dependency xử lý quá chậm. Giảm max.poll.records, giảm thời gian xử lý từng record hoặc điều chỉnh max.poll.interval.ms sau khi đánh giá tác động.

**Lag chỉ tăng ở một partition:** có thể key phân phối lệch hoặc một nhóm record có xử lý chậm. Tăng concurrency không thể chia một partition cho nhiều consumer trong cùng group tại cùng thời điểm; cần xem lại key, partitioning hoặc cách xử lý công việc nặng.

**Batch size nhỏ nhưng poll cycle vẫn dài:** có thể một vài record mất thời gian rất lâu, commit chậm, error handler retry blocking hoặc JVM có GC pause lớn. Hãy tìm thành phần chiếm thời gian thay vì tiếp tục giảm batch một cách mù quáng.

## 13. Quy trình điều chỉnh max.poll.records

Một quy trình thực tế:

1. Đo số record mỗi poll, thời gian xử lý record, thời gian xử lý batch và khoảng cách giữa hai lần poll.
2. Xác định listener đang xử lý record hay batch, tuần tự hay song song.
3. Đo p95/p99 của thời gian xử lý ở tải production-like, gồm cả retry và dependency timeout.
4. Chọn ngân sách thời gian thấp hơn max.poll.interval.ms để dành chỗ cho commit, GC và biến động.
5. Chọn max.poll.records sao cho batch p99 nằm trong ngân sách.
6. Thử nghiệm tăng/giảm batch ở tải đại diện, theo dõi throughput, lag, memory và rebalance.
7. Kiểm tra hành vi khi một record bị chậm, broker mất leader hoặc downstream timeout.
8. Triển khai dần và có ngưỡng rollback cấu hình nếu rebalance hoặc lag tăng bất thường.

Không có một giá trị max.poll.records phù hợp cho mọi ứng dụng. Consumer xử lý dữ liệu nhẹ có thể dùng batch lớn để giảm overhead. Consumer gọi API chậm hoặc thực hiện nhiều side effect có thể cần batch nhỏ và concurrency được giới hạn.

## 14. Các cấu hình thường bị nhầm lẫn

| Cấu hình | Điều khiển | Không có nghĩa là |
|---|---|---|
| max.poll.records | Số record tối đa trả về trong một poll | Số byte tối đa fetch từ broker |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll | Timeout của một record hoặc một HTTP call |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch cho mỗi partition trong một request theo quy tắc Kafka | Số record listener nhận |
| fetch.max.bytes | Giới hạn dữ liệu fetch tổng thể trong một request theo quy tắc Kafka | Kích thước batch ứng dụng cố định |
| session.timeout.ms | Giới hạn mất heartbeat | Thời gian tối đa listener được phép xử lý |
| heartbeat.interval.ms | Nhịp heartbeat | Thời điểm commit offset |
| AckMode | Cách container ghi nhận/commit offset | Số record tối đa trong poll |
| concurrency | Số consumer/container con chạy song song | Số partition có thể xử lý vượt quá số partition được gán |

Phân biệt đúng các cấu hình giúp tránh sửa nhầm tầng. Nếu record quá lớn, tăng max.poll.records không giải quyết được. Nếu listener xử lý quá lâu, tăng fetch.max.bytes không giúp consumer poll sớm hơn.

## 15. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Đặt max.poll.records rất cao mà không đo thời gian batch | Poll cycle có thể vượt max.poll.interval.ms | Đo p95/p99 batch và chọn giới hạn phù hợp |
| Chỉ tăng max.poll.interval.ms để che record treo | Rebalance đến muộn, tác vụ bị treo lâu hơn và recovery chậm | Đặt timeout cho dependency, giới hạn batch và xử lý record chậm |
| Nhầm max.poll.records với giới hạn byte | Bộ nhớ vẫn tăng do fetch cache hoặc payload lớn | Kiểm tra cả fetch byte limits và kích thước payload |
| Tăng concurrency vượt số partition | Có consumer không được gán partition và tăng chi phí tài nguyên | Căn cứ vào số partition và capacity downstream |
| Offload task rồi commit offset ngay | Có thể mất xử lý khi worker lỗi sau commit | Acknowledge sau khi task hoàn tất và xử lý revoke |
| Retry blocking quá lâu trong listener | Không poll đúng hạn, gây rebalance | Tính backoff vào ngân sách hoặc dùng pause/non-blocking retry |
| Giảm batch quá thấp mà không đo | Tăng poll/commit overhead và giảm throughput | Thử nghiệm theo tải và theo dõi latency/throughput |
| Tăng batch để chữa lag do một partition nóng | Partition nóng vẫn là nút thắt | Xem lại key distribution và partitioning |

## 16. Checklist vận hành

Trước khi đưa cấu hình consumer vào production, hãy xác định:

1. max.poll.records đang đặt bao nhiêu và số record thực tế mỗi poll là bao nhiêu?
2. Listener là record listener hay batch listener?
3. Xử lý diễn ra tuần tự hay song song, và thời gian p95/p99 của một batch là bao nhiêu?
4. Tổng thời gian xử lý, commit, retry và backoff có thấp hơn max.poll.interval.ms với khoảng dự phòng không?
5. Dependency có timeout hữu hạn và có cơ chế backpressure không?
6. AckMode và thời điểm commit offset có phù hợp với side effect không?
7. Khi vượt poll interval, record có thể được xử lý lại an toàn không?
8. Nếu dùng async processing, task còn chạy sau partition revoke được xử lý thế nào?
9. Concurrency có phù hợp số partition và capacity database/API không?
10. Dashboard có thể phát hiện poll cycle dài, rebalance, lag, commit failure và dependency latency không?

max.poll.records và thời gian xử lý cần được thiết kế cùng nhau. Batch đủ lớn giúp giảm overhead, nhưng batch phải hoàn tất trước giới hạn poll với khoảng dự phòng thực tế. Khi xử lý dài hoặc biến động, giảm lượng công việc mỗi poll, cải thiện dependency, giới hạn retry và quản lý pause/resume sẽ giúp consumer duy trì tiến độ ổn định hơn.
