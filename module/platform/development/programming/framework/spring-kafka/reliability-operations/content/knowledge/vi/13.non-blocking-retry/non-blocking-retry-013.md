# Độ chính xác của backoff delay

Trong **non-blocking retry** của Spring Kafka, một record thất bại được chuyển sang retry topic và chỉ được xử lý lại khi đã đến thời điểm đủ điều kiện. Cấu hình **backoff delay** thường được hiểu là “chờ 2 giây rồi thử lại”, nhưng trong hệ thống thực tế nó **không phải lịch hẹn được thực hiện chính xác đến từng millisecond**. Delay là khoảng chờ dự kiến hoặc khoảng chờ tối thiểu theo cơ chế retry; thời điểm listener thực sự chạy còn phụ thuộc consumer poll, pause/resume, scheduler, partition assignment, tải hệ thống và độ trễ hạ tầng.

Vì vậy, khi vận hành non-blocking retry, cần tách ba câu hỏi:

1. **Khi nào record được phép thử lại?** Đó là thời điểm đủ điều kiện, được tính từ chính sách backoff và metadata của lần retry.
2. **Khi nào listener thật sự nhận record?** Đó là thời điểm xử lý thực tế, có thể muộn hơn thời điểm đủ điều kiện.
3. **Độ lệch bao nhiêu là chấp nhận được?** Câu trả lời phụ thuộc SLA, độ chính xác của đồng hồ, độ trễ poll và capacity của consumer.

Bài học này giải thích cơ chế khiến delay có sai lệch, cách đo lường sai lệch, cách cấu hình và kiểm thử trong **Spring Kafka Reliability Operations**, đồng thời phân biệt backoff delay với cam kết thực thi đúng thời điểm.

## 1. Non-blocking retry không phải cơ chế hẹn giờ của Kafka broker

Kafka topic là một log theo partition. Broker lưu record theo offset và cho consumer đọc theo giao thức fetch; Kafka broker không tự giữ một record cho đến một thời điểm xử lý nghiệp vụ đã chỉ định.

Spring Kafka xây dựng non-blocking retry bằng cách dùng **retry topics**:

1. Listener ở topic chính xử lý record và ném exception.
2. Retry infrastructure xác định attempt, delay và topic đích theo cấu hình.
3. Một record tương ứng được publish tới retry topic kèm metadata phục vụ retry, trong đó có mốc thời gian đủ điều kiện xử lý.
4. Consumer của retry topic có thể nhận record trước hạn.
5. Retry infrastructure trì hoãn việc gọi listener cho đến khi đến hạn, thường bằng cơ chế pause/resume container hoặc partition và tiếp tục poll thích hợp.
6. Khi record đến hạn, listener được gọi lại; nếu vẫn lỗi, record có thể đi tới retry topic khác hoặc DLT.

~~~mermaid
sequenceDiagram
    participant M as Main topic listener
    participant P as Retry publisher
    participant K as Kafka retry topic
    participant C as Retry consumer
    participant S as Backoff/scheduler
    M->>M: Xử lý record A thất bại
    M->>P: Yêu cầu retry
    P->>P: Tính due timestamp
    P->>K: Publish record A + retry metadata
    K-->>C: Consumer poll record A
    C->>S: Chưa đến due timestamp
    S-->>C: Pause / chờ và tiếp tục poll phù hợp
    S-->>C: Đã đến thời điểm đủ điều kiện
    C->>C: Invoke listener với record A
~~~

Các bước pause, poll và resume là cơ chế ở phía Spring Kafka consumer, không phải một bộ đếm thời gian được broker thực thi trên từng message. Chi tiết lifecycle và bộ lập lịch có thể khác theo phiên bản Spring Kafka.

**Kết luận quan trọng:** record không được hứa sẽ chạy đúng tại mốc due; nó có thể chỉ chạy trong một lần poll hoặc lần được scheduler đánh thức sau mốc đó.

## 2. Backoff delay: thời điểm đủ điều kiện so với thời điểm xử lý

Giả sử lỗi đầu tiên xảy ra lúc 10:00:00.000. Chính sách yêu cầu delay 2.000 ms.

Ta có thể phân biệt các mốc:

| Ký hiệu | Mốc | Ví dụ |
|---|---|---|
| F | Listener phát hiện lỗi | 10:00:00.000 |
| P | Retry record được tạo và metadata thời gian được xác định | 10:00:00.080 |
| D | Mốc đủ điều kiện (due timestamp) dựa trên P và delay | 10:00:02.080 |
| A | Retry record sẵn sàng trong Kafka và được consumer nhận biết | 10:00:00.160 |
| R | Retry listener thật sự được gọi | 10:00:02.470 |

Trong ví dụ, delay yêu cầu là 2.000 ms; retry listener chạy sau mốc đủ điều kiện 390 ms. Tính từ lúc lỗi đầu tiên F, khoảng cách đến R là 2.470 ms.

Đây không phải một lần retry “chờ sai chính sách” chỉ vì listener không chạy chính xác lúc 10:00:02.080. Nó phản ánh rằng **backoff delay và end-to-end retry latency là hai đại lượng khác nhau**.

Cần nhớ điểm gốc để tính backoff có thể là thời điểm retry record/metadata được tạo, không nhất thiết chính là thời điểm exception đầu tiên xuất hiện. Không nên lấy mốc lỗi đầu tiên làm mốc so sánh duy nhất khi đo độ chính xác của cơ chế chờ.

### 2.1 Ba đại lượng thời gian cần đo

Ký hiệu:

- **t_failure**: thời điểm listener phát sinh lỗi.
- **t_due**: thời điểm retry record đủ điều kiện.
- **t_start**: thời điểm retry listener bắt đầu xử lý.

Định nghĩa:

~~~text
requested_delay = giá trị BackOff áp dụng cho attempt

effective_retry_wait = t_start - t_failure

scheduler_lateness = t_start - t_due

on_time_ratio = tỷ lệ retry có scheduler_lateness
                nằm trong ngưỡng chấp nhận
~~~

Trong môi trường hoạt động bình thường, **scheduler_lateness** thường không âm vì cơ chế retry cố gắng không xử lý record trước due timestamp. Tuy nhiên, nếu đồng hồ giữa các node bị lệch, metadata sai hoặc instrumentation dùng nguồn thời gian không nhất quán, số đo có thể bất thường; không nên coi đây là một cam kết thời gian thực tuyệt đối.

Tách **effective_retry_wait** khỏi **scheduler_lateness** giúp biết thời gian tăng do lỗi ở publisher/network hay do consumer/scheduler chạy muộn.

### 2.2 Ví dụ thực tế

Cấu hình delay là 5 giây, nhưng thấy retry bắt đầu sau 7 giây tính từ lỗi.

Có thể 2 giây chênh lệch đến từ:

- Retry publisher đợi broker ACK trước khi record sẵn sàng.
- Retry consumer đang xử lý record khác.
- Partition của retry topic bị pause hoặc đang chờ resume.
- Rebalance hoặc restart xảy ra.
- Consumer thread hoặc scheduler thiếu CPU.
- Poll không kịp phục vụ record đủ điều kiện.

Vì vậy, kết luận “backoff 5 giây không chính xác” cần đi cùng mốc t_due, t_start và thông tin capacity.

## 3. Backoff có phải là thời gian tối thiểu?

Đối với non-blocking retry, thời điểm đủ điều kiện dùng để tránh gọi listener trước hạn. Về mặt thiết kế, delay được xem như **khoảng chờ tối thiểu** trước khi retry attempt có thể được thực hiện, chứ không phải cam kết xử lý tại đúng thời điểm.

Điều đó không có nghĩa cứ yêu cầu 5 giây thì chắc chắn retry xảy ra trong khoảng từ 5,000 đến 5,001 giây. Scheduler và consumer thường chỉ kiểm tra/đánh thức ở những thời điểm rời rạc. Nếu due timestamp rơi giữa hai lần wake-up, record được xử lý ở lần kế tiếp.

### 3.1 Minh họa về độ trễ poll

Giả sử retry due lúc 12:00:05.000. Consumer đang chờ hoặc poll và việc kiểm tra tiếp theo xảy ra lúc 12:00:05.280.

~~~text
12:00:00.000  Retry được publish
12:00:05.000  Record đủ điều kiện
12:00:05.280  Consumer/scheduler tiếp tục xử lý
                -> Listener bắt đầu
~~~

Lateness là khoảng 280 ms. Đây là hiện tượng có thể gặp ngay cả khi cấu hình delay hoàn toàn đúng.

### 3.2 Không có cận trên tự động

Nếu broker bận, partition không được gán, downstream chậm hoặc ứng dụng ngừng hoạt động, retry có thể muộn hơn nhiều so với delay. Kafka và Spring Kafka không tự cung cấp giới hạn kiểu “bắt buộc thực thi không muộn hơn 10 ms”.

SLA cần phân biệt:

- **Minimum wait**: không xử lý trước mốc đủ điều kiện trong điều kiện đồng hồ và metadata chính xác.
- **Delivery freshness**: record được đưa tới listener muộn bao nhiêu sau mốc đủ điều kiện.
- **Recovery time**: nghiệp vụ hoàn tất sau lỗi ban đầu mất bao lâu, bao gồm tất cả lần retry.

Một hệ thống có backoff đúng nhưng thiếu capacity vẫn có thể vi phạm recovery SLA.

## 4. Những nguyên nhân khiến retry được thực thi muộn

### 4.1 Poll cycle của Kafka consumer

Consumer không nhận event trực tiếp từng millisecond; nó thực hiện poll và xử lý record theo vòng lặp. Một retry record có thể trở nên đủ điều kiện trong lúc consumer đang:

- Chờ poll trả về.
- Xử lý record khác.
- Thực thi callback hoặc container task.
- Chờ partition resume.
- Tham gia rebalance.

Do đó, poll cadence và thời gian xử lý listener ảnh hưởng tới khoảng trễ sau due timestamp.

Cấu hình như **pollTimeout** và các thuộc tính poll khi container đang pause có thể tác động đến khả năng đáp ứng, nhưng không có một công thức cố định “poll timeout 1 giây thì lateness tối đa 1 giây”. Đây còn là vấn đề thread scheduling, load và assignment.

### 4.2 Pause/resume và lịch đánh thức

Non-blocking retry có thể tạm pause việc tiêu thụ ở retry consumer/partition cho tới khi record đến hạn. Khi thời gian chờ kết thúc, container phải chuyển về trạng thái có thể xử lý và tiếp tục vòng poll.

Các độ trễ có thể xuất hiện tại:

- Lúc phát hiện record chưa đến hạn.
- Lúc tính khoảng chờ đến mốc due.
- Lúc scheduler thực thi công việc resume.
- Lúc consumer thread thực sự nhận và xử lý việc resume.
- Lúc có record đủ điều kiện để gọi listener.

Nếu worker thread bị nghẽn, một callback đúng hạn không đồng nghĩa listener chạy ngay lập tức.

### 4.3 CPU, garbage collection và thread contention

Khi application bị thiếu CPU, có GC pause dài hoặc có nhiều listener/scheduler task cạnh tranh thread, retry có thể được gọi muộn.

Trong môi trường container, CPU throttling có thể làm thread chỉ được thực thi trễ hơn thời điểm mong muốn. Cần theo dõi:

- CPU usage và CPU throttling.
- GC pause time.
- Thread pool saturation.
- Consumer poll latency.
- Scheduler task delay.
- Listener invocation duration.

Thay đổi delay không sửa được nguyên nhân thiếu năng lực xử lý.

### 4.4 Rebalance và partition assignment

Khi một retry consumer restart hoặc consumer group rebalance, partition có thể tạm thời chưa có owner đang xử lý. Một record đã đến hạn trong lúc đó sẽ chờ đến khi assignment ổn định và consumer được phép đọc.

Rebalance có thể đến từ:

- Scale số pod hoặc concurrency.
- Rolling deployment.
- Consumer vượt max.poll.interval.ms.
- Broker/group coordinator thay đổi.
- Consumer crash hoặc network partition.

Do đó, p99 lateness thường xấu đi trong đợt deploy ngay cả khi p50 vẫn ổn định.

### 4.5 Backlog trong retry topic

Retry topic có thể có hàng nghìn record đến hạn. Một consumer chỉ xử lý được số lượng giới hạn mỗi giây. Record đủ điều kiện nhưng đứng sau một lượng record lớn sẽ được gọi muộn.

Ví dụ:

~~~text
09:00:00  10.000 record của retry topic cùng đến hạn
09:00:00  Consumer có thể xử lý 500 record/giây
09:00:01  Nhiều record vẫn đang chờ
09:00:10  Một số record đã trễ hơn due khoảng 10 giây
~~~

Nâng cao năng lực tiêu thụ hoặc chia partition hợp lý giúp giảm backlog, nhưng phải xét giới hạn downstream và tính công bằng giữa các key.

### 4.6 Record trước đang chờ trên cùng partition

Kafka giữ thứ tự log theo partition. Nếu một record ở vị trí trước đang chờ due timestamp muộn, một record phía sau trên cùng retry partition có thể phải chờ theo cơ chế pause/ordering của container, kể cả khi record phía sau có due timestamp sớm hơn.

Đây là một dạng **head-of-line blocking**. Việc dùng nhiều retry topics theo mức delay hoặc bố trí partition thích hợp có thể thay đổi phạm vi ảnh hưởng, nhưng không xóa hoàn toàn giới hạn thứ tự của từng partition.

Không nên mặc định rằng mỗi record trong retry topic có bộ hẹn giờ độc lập được Kafka broker thực hiện.

### 4.7 Đồng hồ lệch giữa các node

Backoff timestamp thường được tạo ở một thành phần và kiểm tra ở consumer. Nếu hai node có thời gian hệ thống khác nhau, phép so sánh với epoch timestamp có thể cho kết quả sớm hoặc muộn so với thời gian thực.

Ví dụ publisher có đồng hồ nhanh hơn retry consumer 800 ms. Mốc due chứa trong metadata có thể khiến retry consumer cảm nhận thời gian chờ lâu hơn khoảng 800 ms khi so sánh bằng đồng hồ của chính nó.

Vì vậy:

- Đồng bộ thời gian bằng cơ chế hạ tầng phù hợp, ví dụ NTP.
- Theo dõi clock offset của node.
- Ghi rõ timestamp lấy từ producer, consumer hay monitoring host.
- Không trộn đồng hồ monotonic cục bộ và wall-clock timestamp giữa các tiến trình khi tính elapsed time.

Độ lệch âm khi đo lateness có thể là tín hiệu clock skew hoặc lỗi instrumentation. Không chỉ sửa số đo bằng cách ép về 0 rồi bỏ qua nguyên nhân.

### 4.8 Độ trễ publish và broker

Nếu record chưa được ghi thành công vào retry topic, retry consumer chưa thể nhìn thấy nó. Độ trễ publish và broker có thể làm tăng thời gian từ lần lỗi đầu tiên đến lần retry, đặc biệt khi:

- Retry publisher đang chờ ACK.
- Retry topic dưới ngưỡng min.insync.replicas.
- Broker có request latency cao.
- Retry producer bị buffer pressure hoặc timeout.
- Metadata refresh, leader election hoặc network interruption xảy ra.

Cần phân biệt publish delay với scheduler lateness. Khi truy vết nên ghi cả thời điểm lỗi và thời điểm retry record đã được gửi/ghi nhận.

## 5. Các kiểu backoff ảnh hưởng đến lịch retry thế nào?

Spring Kafka cho phép cấu hình backoff cố định, tăng theo cấp số nhân hoặc có độ ngẫu nhiên trong những phiên bản/cách cấu hình hỗ trợ.

### 5.1 Fixed backoff

Ví dụ:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000)
)
@KafkaListener(
    topics = "orders",
    groupId = "order-worker"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Giả sử annotation này sử dụng semantics phổ biến của Spring Kafka: **attempts = 4** gồm lần xử lý ban đầu và tối đa ba lần retry. Mỗi lần retry áp dụng delay theo backoff đã cấu hình.

Thời gian thực thi có thể như sau:

| Attempt | Delay theo cấu hình | Lúc đủ điều kiện | Lúc xử lý thực tế |
|---|---:|---|---|
| 1 - topic chính | Không có retry delay | 10:00:00.000 | 10:00:00.000 |
| 2 - retry 1 | 2 giây | 10:00:02.100 | 10:00:02.440 |
| 3 - retry 2 | 2 giây | 10:00:04.600 | 10:00:05.010 |
| 4 - retry 3 | 2 giây | 10:00:07.180 | 10:00:07.500 |

Mốc đủ điều kiện ở mỗi lần thử phụ thuộc thời điểm lần thất bại và việc tạo retry record tiếp theo; không phải ba mốc cố định cộng 2/4/6 giây từ lần lỗi đầu.

### 5.2 Exponential backoff

Ví dụ:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 8_000
    )
)
@KafkaListener(
    topics = "orders",
    groupId = "order-worker"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Các khoảng chờ dự kiến giữa các lần thử có thể là 1, 2, 4, 8 giây cho bốn retry attempts. Đây là **giá trị delay mong muốn**, không phải các timestamp tuyệt đối mà listener bắt buộc chạy trúng.

Nếu mỗi lần retry bị trễ thêm vài trăm millisecond hoặc vài giây do backlog, tổng thời gian từ lần lỗi đầu đến DLT có thể cao hơn đáng kể tổng các delay cấu hình.

### 5.3 Randomized backoff và jitter

Randomized backoff giúp các consumer tránh đồng loạt retry cùng thời điểm khi downstream phục hồi. Khi dùng jitter, delay được chọn cho từng lần retry có thể khác nhau. Do đó, đo accuracy phải so với **delay đã được chọn cho attempt đó**, không phải chỉ so với giá trị khởi tạo.

Ví dụ cấu hình một dải delay không có nghĩa retry phải xảy ra đúng một giá trị duy nhất. Mỗi attempt cần có due timestamp thực tế để đo độ lệch.

### 5.4 Topic reuse và cách phân nhóm delay

Spring Kafka có các chiến lược tạo hoặc tái sử dụng retry topic, khác nhau theo phiên bản và loại BackOff. Việc nhiều attempt cùng dùng một retry topic hay dùng các topic riêng cho mức delay có thể ảnh hưởng:

- Số partition/topic phải vận hành.
- Số consumer và overhead vận hành.
- Mức độ nhiều record với due timestamp khác nhau cùng nằm trên một partition.
- Phạm vi head-of-line blocking.
- Khả năng scale từng mức retry độc lập.

Đừng mặc định tên retry topic hoặc số retry topic chỉ từ số attempts. Hãy kiểm tra retry-topic topology được sinh ở runtime.

## 6. Cấu hình Spring Boot và Spring Kafka để kiểm soát độ trễ

Một ví dụ cấu hình đơn giản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-worker
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      ack-mode: record
      concurrency: 3
      poll-timeout: 1s
~~~

Các giá trị chỉ minh họa. Điều quan trọng là lựa chọn có chủ đích giữa throughput, số consumer, thời gian poll và năng lực downstream.

**poll-timeout** không phải núm điều chỉnh trực tiếp để biến non-blocking retry thành scheduler chính xác tới millisecond. Poll interval thực tế còn chịu ảnh hưởng data availability, pause/resume, callback execution và tải runtime.

### 6.1 Các tham số nên xem cùng nhau

| Tham số hoặc thành phần | Ảnh hưởng vận hành |
|---|---|
| BackOff delay | Thời gian chờ dự kiến trước attempt tiếp theo |
| Retry-topic topology | Số luồng retry, cách chia và tái sử dụng retry topic |
| Consumer poll timeout | Nhịp poll và thời gian phản hồi ở một số trạng thái |
| Pause/resume scheduler | Thời điểm container trở lại xử lý record đủ điều kiện |
| Consumer concurrency | Số consumer thread có thể xử lý song song |
| Partition count | Mức song song tối đa của group trên các partition được subscribe |
| max.poll.records | Lượng record trong mỗi poll và thời gian xử lý đợt |
| max.poll.interval.ms | Giới hạn thời gian giữa các poll trước nguy cơ mất assignment |
| Listener duration | Thời gian giữ consumer thread trên một invocation |
| CPU/GC và broker latency | Độ trễ thực thi ngoài logic backoff |

Với một số Spring Kafka version, container có tùy chọn cấu hình poll khi đã pause và cơ chế BackOffHandler/scheduler tương ứng. Tên API và default có thể thay đổi; hãy đọc runtime configuration của phiên bản đang sử dụng thay vì giả định một giá trị mặc định chung cho mọi hệ thống.

### 6.2 Chọn concurrency theo partition

Giả sử retry topic có 4 partition và retry listener group có 2 pod, mỗi pod concurrency 3. Tổng số consumer là 6 nhưng chỉ tối đa 4 consumer có thể được gán partition của topic đó nếu chỉ xét topic này.

Tăng concurrency mỗi pod từ 3 lên 8 không làm retry topic có thêm partition. Một số consumer sẽ idle. Nếu lateness tăng vì một partition nóng, chỉ tăng consumer count chưa chắc cải thiện.

Cần so sánh tải **theo partition**, không chỉ nhìn tổng số consumer hoặc tổng lag.

### 6.3 Giảm workload không liên quan

Nếu retry consumer cùng process với nhiều listener và tác vụ CPU nặng, contention có thể làm scheduler chạy trễ. Một số biện pháp:

- Đặt giới hạn công việc đồng thời ở downstream.
- Đo và tối ưu thời gian listener xử lý.
- Đảm bảo thread/scheduler pool không bị nghẽn.
- Phân bổ CPU và memory đủ cho app.
- Tách workload retry nặng sang deployment phù hợp nếu kiến trúc yêu cầu.
- Kiểm tra GC và thread dump khi độ trễ có spike.

Một hệ thống retry nhanh phải có capacity để thực hiện lần thử, không chỉ có cấu hình thời gian nhỏ.

## 7. Đo độ chính xác của delay trong production

Không nên dùng metric “retry count” làm đại diện cho độ chính xác thời gian. Cần đo trực tiếp **record đủ điều kiện lúc nào** và **listener được gọi lúc nào**.

### 7.1 Metadata cho retry attempt

Spring Kafka retry topic infrastructure sử dụng metadata để xác định attempt và thời điểm đủ điều kiện. Có thể quan sát các retry headers hoặc instrumentation xung quanh publisher/container theo API của phiên bản dự án.

Một số điểm cần phân biệt:

- **Event created timestamp**: thời điểm nghiệp vụ tạo event.
- **Original Kafka record timestamp**: timestamp của record ở topic chính.
- **Retry record append/create timestamp**: timestamp gắn với record của retry topic theo cấu hình Kafka.
- **Retry backoff due timestamp**: timestamp phục vụ quyết định khi nào record được retry.
- **Retry listener start timestamp**: mốc bắt đầu xử lý lại thực tế.

Không lấy Kafka record timestamp làm due timestamp nếu framework không đảm bảo hai mốc trùng nhau. Nếu tự gửi thêm timestamp trong business headers, đặt tên rõ ràng để không nhầm với header nội bộ do Spring Kafka sử dụng.

### 7.2 Công thức đo lateness

Với mỗi attempt:

~~~text
due_at_ms = timestamp đủ điều kiện của retry attempt
listener_started_at_ms = thời điểm listener được gọi

lateness_ms = listener_started_at_ms - due_at_ms
effective_wait_ms = listener_started_at_ms - failed_at_ms

early_execution = lateness_ms < 0
late_by_1s = lateness_ms > 1000
~~~

Các timestamp dùng để trừ phải dùng cùng mốc epoch và có đồng hồ được đồng bộ. Nếu cần tính một khoảng elapsed trong cùng JVM, nên dùng đồng hồ monotonic để tránh wall clock bị điều chỉnh; nhưng timestamp truyền qua Kafka giữa nhiều JVM thường là wall-clock epoch, nên cần xem xét clock skew.

### 7.3 Phân tích phân phối thay vì một ví dụ đơn lẻ

Nên đo:

- p50 lateness: hành vi thường gặp.
- p95 và p99 lateness: tình huống load cao và tail latency.
- Max lateness trong một khoảng thời gian.
- Tỷ lệ retry bắt đầu quá sớm so với due timestamp.
- Tỷ lệ retry trễ trên ngưỡng SLA, ví dụ 1 hoặc 5 giây.
- Lateness theo topic, partition, consumer instance và retry attempt.

Ví dụ:

| Chỉ số | Giá trị quan sát | Diễn giải |
|---|---:|---|
| Cấu hình fixed delay | 2.000 ms | Delay dự kiến |
| p50 lateness | 120 ms | Phần lớn attempt bắt đầu hơi sau due |
| p95 lateness | 650 ms | Tail latency đáng kể |
| p99 lateness | 3.400 ms | Một số attempt trễ nhiều |
| Max lateness | 42 giây | Cần điều tra rebalance/backlog |
| Retry sớm hơn due | 0,02% | Cần kiểm tra đồng hồ hoặc instrumentation |

Đây là dữ liệu giả định để minh họa cách đọc dashboard, không phải mức hiệu năng mặc định của Spring Kafka.

### 7.4 Log có ngữ cảnh

Một log hợp lý:

~~~text
service=order-worker
topic=orders-retry-2000
partition=2
offset=1184
eventId=evt-1001
attempt=2
dueAtMs=1900000002000
startedAtMs=1900000002290
latenessMs=290
consumerClientId=order-worker-2
~~~

Cần giữ thông tin event id, attempt và partition để khoanh vùng. Không log toàn bộ payload nhạy cảm.

Nếu application log không có due timestamp tin cậy, đừng báo metric “scheduler lateness” dựa trên việc lấy timestamp của lỗi ban đầu cộng delay một cách tùy ý. Hãy gọi đó là **observed retry interval** và ghi rõ cách tính.

## 8. Độ chính xác delay dưới tác động của tải và sự cố

### 8.1 Khi tải thấp

Consumer có ít backlog, scheduler và CPU rảnh, các lần retry thường bắt đầu gần due timestamp hơn. Tuy nhiên, chênh lệch nhỏ vẫn xuất hiện vì vòng poll và thread scheduling.

### 8.2 Khi retry storm

Một downstream bị lỗi trong vài phút khiến hàng loạt record được gửi tới retry topic. Khi service phục hồi, nhiều record cùng đến hạn. Retry consumer có thể không đủ throughput để xử lý hết đúng thời điểm.

Để giảm ảnh hưởng:

- Dùng exponential backoff/jitter phù hợp.
- Giới hạn concurrency downstream.
- Tăng partition hoặc consumer capacity nếu đã xác định là bottleneck.
- Sử dụng circuit breaker/rate limiting khi cần.
- Quan sát backlog và retry-topic age.
- Cân nhắc tránh mọi pod deploy cùng lúc khi dependency vừa phục hồi.

Không chỉ giảm delay từ 2 giây xuống 200 ms vì thấy retry “chậm”. Điều đó có thể khiến tải lên downstream tăng và p99 lateness xấu đi.

### 8.3 Khi một broker hoặc network gặp lỗi

Record không thể được xử lý nếu retry consumer chưa truy cập được partition leader, hoặc publisher chưa publish thành công. Nếu retry topic có ISR suy giảm, produce latency hoặc lỗi ghi có thể tăng.

Lúc này, metric scheduler lateness có thể tăng, nhưng nguyên nhân là availability/replication chứ không phải thuật toán tính BackOff. Nên kết hợp broker health, producer retry và consumer assignment.

### 8.4 Khi deploy hoặc scale

Rolling deployment gây consumer join/leave group và có thể rebalance. Trong giai đoạn đó, record đã đến hạn có thể chờ assignment.

Nếu độ trễ p99 chỉ tăng trong deploy, hãy so sánh:

- Thời điểm rebalance.
- Number of assigned partitions.
- Consumer restart time.
- Lateness theo pod/partition.
- Tiến triển offset sau khi group ổn định.

Không nên gán mọi spike delay cho cấu hình poll timeout.

## 9. Độ chính xác và thứ tự xử lý là hai yêu cầu khác nhau

Một sai lầm phổ biến là nghĩ rằng khi retry delay đến hạn, record sẽ được xử lý trước các record phát sinh sau nó. Non-blocking retry không đảm bảo điều này giữa topic chính và retry topic.

Ví dụ:

~~~text
09:00:00  Topic orders, key=order-1, event A thất bại
09:00:00  A được chuyển tới retry topic, due sau 10 giây
09:00:01  Topic orders nhận event B cùng key=order-1
09:00:02  Main listener xử lý B thành công
09:00:10  Retry listener xử lý lại A
~~~

Đối với business flow cần A trước B, kết quả này có thể không hợp lệ mặc dù backoff delay của A được thực hiện đúng.

Vì vậy, phải đánh giá đồng thời:

- **Timing requirement**: không retry quá sớm; lateness chấp nhận được.
- **Ordering requirement**: event theo key có được phép vượt nhau không?
- **Idempotency requirement**: cùng event được xử lý lại có tạo side effect trùng không?

Nếu strict ordering là bắt buộc, có thể chọn blocking retry trên partition, xây dựng cơ chế sequencing theo business key hoặc đưa trạng thái chờ vào kho bền vững có điều phối. Không đánh đổi thứ tự nghiệp vụ chỉ để đạt throughput cao.

## 10. Khi nào non-blocking retry không đáp ứng yêu cầu thời gian?

Backoff delay trong retry topic phù hợp với retry nghiệp vụ cần chờ từ vài giây tới nhiều phút, nơi một mức jitter và lateness là chấp nhận được.

Nó không phải lựa chọn thích hợp nếu yêu cầu là:

- Thực hiện chính xác tại một thời điểm tuyệt đối với độ lệch vài millisecond.
- Có deadline cứng: mọi record phải được xử lý trước mốc T dù cluster đang rebalance hoặc broker gặp sự cố.
- Bảo đảm thứ tự nghiêm ngặt giữa topic chính và các retry topics.
- Cung cấp lịch trình dài hạn có độ bền và khả năng điều khiển như scheduler nghiệp vụ.
- Cần phân biệt lịch đặt, hủy, gia hạn, điều chỉnh ưu tiên của tác vụ một cách trực tiếp.

Khi đó, nên cân nhắc thiết kế khác:

- Một scheduler/queue có semantic delayed job rõ ràng và SLA đã xác định.
- Database job table với due_at, ownership, lease, index và worker có kiểm soát.
- Workflow engine cho tác vụ có nhiều bước, timeout hoặc hẹn giờ dài.
- Một dịch vụ điều phối có khả năng theo dõi deadline và xử lý quá hạn.

Dù dùng scheduler riêng, vẫn cần thực tế về clock skew, availability và xử lý trùng. Không hệ thống phân tán thông thường nào tự đảm bảo real-time tuyệt đối trong mọi điều kiện lỗi.

## 11. Cách đặt SLO về độ chính xác backoff

Thay vì cam kết “delay chính xác 2 giây”, hãy đặt một SLO có thể đo và hành động.

Ví dụ:

~~~text
Khi retry topic và consumer group khả dụng,
99% retry attempts bắt đầu trong vòng 2 giây
sau thời điểm đủ điều kiện (due timestamp),
đo trên cửa sổ 30 phút.
~~~

SLO cần quy định:

- Tập record được đo: tất cả retry attempts hay chỉ retry của một topic.
- Mốc thời gian: due timestamp từ retry infrastructure.
- Điều kiện loại trừ nếu có: maintenance, cluster outage, clock drift lớn.
- Percentile và cửa sổ thời gian.
- Ngưỡng alert trước khi vi phạm.
- Cách phát hiện record chưa chạy, không chỉ record đã chạy.

Điểm cuối rất quan trọng: chỉ tính lateness trên record **đã được listener gọi** tạo ra survivorship bias. Nếu một partition bị kẹt và không record nào được xử lý, dashboard lateness có thể vẫn đẹp vì thiếu dữ liệu. Cần đo thêm tuổi của record đã đến hạn nhưng chưa tiến triển, backlog, consumer lag và retry-topic end-to-end age.

### 11.1 Gợi ý alert

Một số alert có thể kết hợp:

| Tín hiệu | Ý nghĩa |
|---|---|
| p99 lateness tăng | Retry xử lý chậm so với due |
| Tỷ lệ attempt muộn quá ngưỡng | SLO có nguy cơ vi phạm |
| Retry topic lag tăng | Capacity không theo kịp |
| Partition offset không tiến triển | Có khả năng head-of-line blocking hoặc consumer kẹt |
| Rebalance tăng | Assignment gián đoạn |
| CPU throttling/GC tăng | Scheduler và listener thiếu thời gian CPU |
| DLT publish lỗi | Recovery sau retry cũng thất bại |
| Clock drift vượt ngưỡng | Không thể tin cậy phép so sánh due timestamp |

Cần tránh cảnh báo chỉ dựa vào một metric. Ví dụ, lateness tăng nhưng lag thấp có thể liên quan thread scheduling, còn lag cao cùng throughput chậm gợi ý backlog.

## 12. Kiểm thử độ chính xác trong môi trường tích hợp

Nên dùng Kafka thật qua Testcontainers hoặc môi trường staging để kiểm tra retry-topic infrastructure. Unit test gọi trực tiếp listener không thể kiểm chứng pause/resume, consumer poll và partition assignment.

### 12.1 Kiểm thử fixed delay

Giả sử cấu hình delay 2.000 ms và attempts 3:

1. Tạo topic chính và retry/DLT topic phù hợp.
2. Consumer listener ném một exception đã được phân loại retryable ở lần đầu.
3. Ghi mốc failure và metadata due timestamp.
4. Đo thời điểm retry listener bắt đầu.
5. Xác nhận retry không được gọi trước mốc due ngoài sai số đo/clock được xác định.
6. Đo lateness và kiểm tra nó dưới ngưỡng **rộng, có cơ sở** của môi trường kiểm thử.
7. Xác nhận record được xử lý thành công sau retry.

Không viết assertion kiểu “retry chạy đúng 2000 ms” với tolerance 1 ms. Test đó dễ flaky vì JVM, broker, scheduler và CI đều có jitter.

### 12.2 Ví dụ ý tưởng đo thời gian

~~~java
public record RetryObservation(
    String eventId,
    int attempt,
    long dueAtEpochMillis,
    long listenerStartedAtEpochMillis
) {
    public long latenessMillis() {
        return listenerStartedAtEpochMillis - dueAtEpochMillis;
    }
}
~~~

Đây là model đo lường; nó không tự cung cấp due timestamp. Hệ thống kiểm thử cần trích due timestamp đúng từ retry metadata theo Spring Kafka version hoặc ghi mốc due thông qua instrumentation đáng tin cậy.

Một assertion tích hợp nên xem xét:

~~~java
RetryObservation observation = awaitRetryObservation("evt-1001");

assertThat(observation.attempt()).isEqualTo(2);
assertThat(observation.latenessMillis())
    .isGreaterThanOrEqualTo(-allowedClockToleranceMillis);
assertThat(observation.latenessMillis())
    .isLessThan(maxAcceptableTestLatenessMillis);
~~~

Giá trị tolerance phải dựa trên môi trường test và SLO. Khi phép đo dùng cùng JVM nhưng due timestamp đến từ node khác, vẫn phải tính clock skew.

### 12.3 Kiểm thử exponential backoff

- Cấu hình attempts và delay theo cấp số nhân.
- Làm listener lỗi trong nhiều lần thử.
- Ghi due timestamp và thời điểm chạy từng attempt.
- Xác nhận chuỗi delay dự kiến áp dụng đúng theo config.
- Đo lateness **riêng cho từng attempt**, không chỉ tổng thời gian retry.
- Xác nhận record đi DLT khi exhausted.

### 12.4 Kiểm thử dưới tải

- Tạo backlog trong retry topic.
- Tăng concurrency đến mức tối đa hữu ích theo partition.
- Đo p50, p95, p99 lateness khi tải tăng.
- Kiểm tra CPU, GC, broker latency, rebalance và poll.
- Xác định điểm bắt đầu SLO vi phạm.
- Thử lại khi downstream bị rate limit.

Kết quả từ test môi trường tải thấp không thể thay thế capacity test.

### 12.5 Kiểm thử clock skew và restart

Trong môi trường cô lập:

- Ghi nhận tác động nếu đồng hồ node có độ lệch.
- Restart retry consumer khi record đã đủ điều kiện.
- Thực hiện rebalance khi retry topic có backlog.
- Kiểm tra record được xử lý sau khi assignment phục hồi.
- Xác nhận retry metadata và attempt không biến mất ngoài ý muốn.
- Kiểm tra duplicate side effect được ngăn bằng idempotency key.

Không chỉnh đồng hồ trên production node để thử nghiệm. Có thể mô phỏng bằng test clock/instrumentation hoặc môi trường riêng.

## 13. Quy trình điều tra khi retry chậm hơn delay

Khi operator báo “đặt delay 5 giây nhưng record chạy sau 30 giây”, hãy điều tra theo thứ tự:

1. **Xác định record:** event id, topic, partition, offset, attempt, retry topic.
2. **Xác định mốc:** thời gian lỗi, retry publish, due timestamp, listener start.
3. **Tính đúng metric:** effective retry wait và lateness so với due.
4. **Kiểm tra retry topology:** retry topic nào, cùng một topic có nhiều mức delay hay không.
5. **Kiểm tra partition:** backlog, offset progression, head-of-line blocking.
6. **Kiểm tra consumer group:** member count, assignment, rebalance và restart.
7. **Kiểm tra consumer thread:** poll time, pause/resume, listener duration.
8. **Kiểm tra runtime:** CPU throttling, GC, thread pool và scheduler queue.
9. **Kiểm tra Kafka:** publish latency, broker/ISR, leader election, network.
10. **Kiểm tra đồng hồ:** clock skew giữa nơi tạo và nơi kiểm tra due timestamp.
11. **Thử thay đổi có kiểm soát:** giảm workload, điều chỉnh concurrency hoặc partition topology.
12. **Đo lại:** xác nhận p95/p99 lateness và backlog thực sự cải thiện.

Không sửa ngay backoff delay nếu chưa xác định mốc nào bị trễ. Ví dụ, nếu delay là 5 giây và record đã đến hạn từ lâu nhưng chưa được xử lý vì retry topic lag, giảm delay xuống 1 giây chỉ khiến thêm record đến hạn sớm hơn và có thể tăng backlog.

### 13.1 Phân biệt hai tình huống dễ nhầm

**Tình huống A: Backoff policy áp dụng sai.** Attempt 2 dự kiến chờ 5 giây nhưng due timestamp thực tế được tạo chỉ sau 1 giây. Cần kiểm tra annotation, profile, policy, version và routing retry topic.

**Tình huống B: Policy đúng nhưng thực thi trễ.** Due timestamp đúng sau 5 giây; listener được gọi sau 25 giây vì backlog và rebalance. Cần xử lý capacity/lifecycle, không thay đổi phép tính backoff.

Cả hai cùng tạo triệu chứng “retry delay không như mong muốn”, nhưng hướng sửa hoàn toàn khác nhau.

## 14. Những hiểu nhầm phổ biến

**“Kafka broker tự hẹn giờ retry tới từng millisecond.”** Không. Kafka broker lưu record trong log; Spring Kafka consumer áp dụng logic trì hoãn.

**“Đặt delay = 2000 có nghĩa listener bắt đầu đúng sau 2000 ms.”** Không. Mốc due chỉ là thời điểm record đủ điều kiện; listener có thể chạy muộn.

**“Delay bị trễ là do Spring Kafka tính sai.”** Chưa chắc. Poll, scheduler, backlog, rebalance, CPU và clock skew đều ảnh hưởng.

**“Tăng concurrency luôn làm retry chính xác hơn.”** Không. Partition count giới hạn song song; downstream có thể thành bottleneck.

**“Đo thời gian từ exception đầu tiên là đủ.”** Không. Cần phân biệt retry publish, due timestamp và listener start.

**“Nếu p50 lateness nhỏ thì mọi record đều đúng SLA.”** Không. Tail latency và record chưa được xử lý có thể nghiêm trọng.

**“Giảm poll timeout luôn làm retry chính xác.”** Không. Nó có thể giảm một phần độ trễ nhưng không thay thế capacity, assignment và scheduler.

**“Exponential backoff nghĩa là mọi attempt có mốc thực thi tuyệt đối dự đoán được từ lần lỗi đầu.”** Không. Mốc attempt tiếp theo phụ thuộc thời điểm lần trước thất bại/publish, backoff và điều kiện hạ tầng.

**“Non-blocking retry giữ thứ tự event theo business key.”** Không mặc định. Record ở topic chính có thể vượt record đã chuyển sang retry topic.

**“Retry delay nhỏ luôn giúp hệ thống phục hồi nhanh hơn.”** Không. Delay quá nhỏ khi downstream chưa phục hồi có thể gây retry storm.

## 15. Checklist thiết kế và vận hành

**Thiết kế backoff**

- [ ] Phân biệt backoff tối thiểu và end-to-end retry latency.
- [ ] Attempts và delay được định nghĩa rõ cho từng loại exception.
- [ ] Có giới hạn thời gian retry và recovery/DLT khi exhausted.
- [ ] Có jitter hoặc chiến lược chống retry storm khi cần.
- [ ] Đánh giá strict ordering trước khi dùng non-blocking retry.

**Cấu hình**

- [ ] Retry topic topology và consumer assignment được quan sát.
- [ ] Concurrency phù hợp số partition và năng lực downstream.
- [ ] Poll, pause/resume và scheduler theo Spring Kafka version được hiểu đúng.
- [ ] Clock synchronization và CPU/GC được giám sát.
- [ ] Retry publisher và DLT có cấu hình durability phù hợp.

**Đo lường**

- [ ] Có due timestamp đáng tin cậy theo attempt.
- [ ] Đo listener start, effective retry wait và scheduler lateness.
- [ ] Theo dõi p50/p95/p99 và max lateness.
- [ ] Theo dõi record quá hạn chưa được xử lý, không chỉ record đã hoàn tất.
- [ ] Tách metric theo topic, partition, attempt và consumer instance.
- [ ] Theo dõi retry topic lag, rebalance, producer publish và clock skew.

**Kiểm thử và runbook**

- [ ] Có integration test với Kafka thật cho fixed/exponential backoff.
- [ ] Temporal assertions có tolerance hợp lý, không đòi chính xác từng millisecond.
- [ ] Đã kiểm thử backlog, restart, rebalance và CPU contention.
- [ ] Đã kiểm thử idempotency và thay đổi thứ tự giữa topic chính/retry topic.
- [ ] Có runbook phân biệt policy tính due sai với execution lateness.

**Độ chính xác của backoff delay** trong non-blocking retry phải được hiểu là độ chính xác của **thời điểm đủ điều kiện**, cộng với sai lệch của hệ thống khi thực sự gọi listener. Spring Kafka không bảo đảm một record được xử lý đúng từng millisecond sau lỗi; delay chỉ định lúc có thể retry, còn poll, pause/resume, scheduler, backlog, rebalance và đồng hồ quyết định lúc retry thực tế diễn ra. Thiết kế tin cậy cần đo due-to-start lateness, đặt SLO thực tế, giữ retry hữu hạn và bảo vệ thứ tự cùng side effect nghiệp vụ bằng cơ chế phù hợp.

