# session.timeout.ms và heartbeat

Trong Kafka consumer group, broker cần biết consumer nào còn tham gia nhóm để giữ hoặc phân phối lại các partition. Consumer định kỳ gửi heartbeat để thông báo rằng nó vẫn còn hoạt động. Nếu broker không nhận heartbeat trong khoảng thời gian được phép, broker xem member đã mất và có thể bắt đầu rebalance.

Hai cấu hình thường gặp trong classic consumer group protocol là **session.timeout.ms** và **heartbeat.interval.ms**. Chúng liên quan trực tiếp đến việc phát hiện consumer mất kết nối, nhưng không thay thế cho việc kiểm tra consumer có tiếp tục gọi poll() và xử lý record hay không. Để vận hành Spring Kafka ổn định, cần hiểu thêm max.poll.interval.ms, thời gian xử lý listener, commit offset và tác động của rebalance.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích heartbeat, consumer session và cách broker phát hiện member không còn hoạt động.
- Phân biệt session.timeout.ms, heartbeat.interval.ms và max.poll.interval.ms.
- Chọn giá trị timeout phù hợp với độ trễ failover và mức chịu đựng gián đoạn mạng.
- Cấu hình các thuộc tính consumer trong Spring Boot và ConsumerFactory.
- Phân tích tác động của listener xử lý lâu, garbage collection, network pause và rebalance.
- Nhận biết sự khác biệt giữa classic consumer group protocol và consumer group protocol mới.
- Kiểm thử và quan sát heartbeat, consumer lag, rebalance và xử lý lặp.

## 1. Heartbeat giữ membership của consumer group

Một consumer group có thể gồm nhiều consumer instance cùng chia sẻ việc đọc các partition của topic. Coordinator của group (một broker được Kafka chọn cho group) quản lý membership và partition assignment.

Consumer cần duy trì liên lạc với coordinator. Trong classic protocol, consumer gửi heartbeat định kỳ. Heartbeat cho coordinator biết member vẫn đang tham gia group. Nếu coordinator không nhận heartbeat trước khi session hết hạn, member bị xem là đã rời nhóm và partition của nó có thể được phân phối cho member khác.

Luồng đơn giản:

~~~text
Consumer A                         Group Coordinator
    |                                      |
    | -------- JoinGroup / SyncGroup ----> |
    | <------- partition assignment ------ |
    |                                      |
    | ------------ Heartbeat ------------> |
    | ------------ Heartbeat ------------> |
    | ------------ Heartbeat ------------> |
    |                                      |
    |       mất kết nối / không heartbeat  |
    |                                      |
    |             session hết hạn         |
    |                                      |
    | <--------- rebalance group --------- |
    |                                      |
Consumer B nhận các partition được phân phối lại
~~~

Heartbeat không chứa kết quả nghiệp vụ của listener. Nó không nói rằng record đã được ghi vào database, đã được xử lý thành công hoặc offset đã được commit. Nó chỉ phục vụ membership và liveness của consumer group.

Vì vậy, cần tách ba tín hiệu:

| Tín hiệu | Câu hỏi được trả lời |
|---|---|
| Heartbeat | Consumer còn duy trì membership với coordinator không? |
| poll() | Consumer có tiếp tục lấy dữ liệu và tiến triển theo vòng đọc không? |
| Offset commit | Consumer group đã ghi nhận vị trí đọc tiếp theo đến đâu? |

Một consumer có thể vẫn gửi heartbeat nhưng listener đang xử lý quá lâu. Ngược lại, consumer có thể xử lý xong một record nhưng chưa commit offset. Không nên dùng heartbeat làm chỉ số thay thế cho trạng thái xử lý nghiệp vụ.

## 2. session.timeout.ms

session.timeout.ms xác định khoảng thời gian coordinator chờ heartbeat của một consumer trước khi xem consumer đó đã mất. Nếu heartbeat không đến trong khoảng thời gian này, coordinator loại member khỏi group và kích hoạt quy trình phân phối lại partition.

Ví dụ giả định:

- session.timeout.ms = 15 giây.
- Coordinator nhận heartbeat gần nhất lúc 10:00:00.
- Consumer bị mất mạng ngay sau heartbeat đó.
- Nếu không có heartbeat tiếp theo trước khi session hết hạn, coordinator có thể đánh dấu member đã mất vào khoảng 10:00:15, tùy thời điểm xử lý và lịch heartbeat thực tế.

Con số trên chỉ minh họa cơ chế timeout; không phải cam kết thời điểm failover chính xác đến từng mili giây.

### Timeout ngắn

Ưu điểm:

- Phát hiện consumer chết hoặc mất kết nối nhanh hơn.
- Partition có thể được giao cho consumer còn hoạt động sớm hơn.
- Giảm thời gian chờ khi một instance thực sự đã ngừng hoạt động.

Đánh đổi:

- Một đợt network pause ngắn, CPU quá tải hoặc JVM stop-the-world có thể khiến heartbeat bị trễ.
- Consumer khỏe mạnh có thể bị loại khỏi group ngoài ý muốn.
- Rebalance thường xuyên làm gián đoạn việc đọc và tăng chi phí khởi tạo lại assignment.

### Timeout dài

Ưu điểm:

- Chịu đựng tốt hơn với gián đoạn mạng hoặc pause tạm thời.
- Giảm nguy cơ loại nhầm consumer trong môi trường có độ trễ không ổn định.

Đánh đổi:

- Khi consumer thực sự chết, coordinator cần chờ lâu hơn mới phát hiện.
- Partition bị giữ trong trạng thái chờ phát hiện lỗi lâu hơn trước khi có thể được phân phối lại.

Chọn timeout theo mục tiêu phục hồi và đặc tính hạ tầng. Không nên đặt càng thấp càng tốt; một timeout quá nhạy có thể làm hệ thống rebalance liên tục.

### Giới hạn từ broker

Với classic protocol, giá trị session timeout do consumer gửi phải nằm trong khoảng broker cho phép. Hai cấu hình broker thường liên quan là:

- group.min.session.timeout.ms: giới hạn dưới.
- group.max.session.timeout.ms: giới hạn trên.

Nếu client gửi giá trị nằm ngoài khoảng broker cho phép, yêu cầu tham gia group có thể bị từ chối. Khi thay đổi session timeout, cần kiểm tra cả cấu hình consumer và chính sách broker.

## 3. heartbeat.interval.ms

heartbeat.interval.ms xác định khoảng thời gian giữa các lần consumer gửi heartbeat trong classic protocol. Giá trị này cần nhỏ hơn session.timeout.ms. Một hướng dẫn cấu hình phổ biến là đặt heartbeat interval không lớn hơn khoảng một phần ba session timeout để có nhiều cơ hội gửi lại heartbeat trước khi session hết hạn.

Ví dụ:

~~~yaml
session-timeout: 15000
heartbeat-interval: 5000
~~~

Với cấu hình minh họa này, consumer dự kiến gửi heartbeat mỗi 5 giây trong khi coordinator chờ tối đa 15 giây kể từ heartbeat hợp lệ gần nhất trước khi hết session.

Nếu heartbeat interval quá gần session timeout, consumer có ít cơ hội khôi phục khi một heartbeat bị trễ hoặc thất lạc. Nếu đặt quá nhỏ, số heartbeat request tăng và tạo thêm lưu lượng điều khiển giữa consumer với coordinator. Hãy giữ khoảng cách hợp lý thay vì đặt hai giá trị gần bằng nhau.

Heartbeat interval không phải chu kỳ xử lý record. Nó cũng không có nghĩa consumer poll Kafka theo chu kỳ đó. Việc poll dữ liệu và việc duy trì heartbeat là hai hoạt động có quan hệ nhưng có mục đích khác nhau.

## 4. Phân biệt với max.poll.interval.ms

Đây là điểm dễ nhầm nhất khi cấu hình consumer.

- session.timeout.ms kiểm soát thời gian coordinator chờ heartbeat trước khi xem member đã mất.
- heartbeat.interval.ms điều khiển nhịp heartbeat trong classic protocol.
- max.poll.interval.ms giới hạn thời gian giữa các lần gọi poll() của consumer đang hoạt động theo cơ chế consumer progress.

Từ Kafka hỗ trợ heartbeat nền, heartbeat có thể tiếp tục được gửi trong khi ứng dụng đang xử lý record. Vì vậy, listener xử lý quá lâu không nhất thiết lập tức làm session timeout. Tuy nhiên, nếu ứng dụng không gọi poll() trở lại trước khi max.poll.interval.ms hết hạn, consumer được xem là không còn tiến triển và phải rời group hoặc ngừng heartbeat theo quy tắc của client.

Ví dụ:

~~~text
Thời điểm       Sự kiện
-----------------------------------------------------
T0              Consumer gọi poll(), nhận batch
T1              Listener bắt đầu xử lý batch
T1 - T2         Heartbeat vẫn có thể tiếp tục
T2              max.poll.interval.ms bị vượt
T3              Consumer rời group / ngừng heartbeat
T4              Coordinator phân phối lại partition
~~~

Trong trường hợp consumer xử lý record đồng bộ, tổng thời gian xử lý batch cần được xem cùng max.poll.interval.ms. Nếu batch có 100 record và mỗi record mất 2 giây, thời gian xử lý có thể vượt 200 giây, chưa tính thời gian gọi dịch vụ phụ thuộc và commit. Cần đánh giá thời gian xấu nhất, không chỉ thời gian trung bình.

Với static membership (cấu hình group.instance.id), khi vượt max.poll.interval.ms, hành vi rời group có thể trì hoãn việc phân phối lại partition cho đến khi session timeout hết hạn. Cách này có thể giảm rebalance khi instance khởi động lại nhanh, nhưng làm failover chậm hơn nếu instance thực sự đã chết. group.instance.id phải duy nhất giữa các consumer instance đang hoạt động trong cùng group.

## 5. Heartbeat trong classic và consumer group protocol mới

Các thuộc tính session.timeout.ms và heartbeat.interval.ms được sử dụng theo cách quen thuộc trong **classic consumer group protocol**.

Ở các phiên bản Kafka hỗ trợ consumer group protocol mới, client có thể chọn group.protocol=consumer. Trong protocol này, broker kiểm soát nhịp heartbeat và session timeout thông qua các cấu hình phía broker, thường là:

- group.consumer.heartbeat.interval.ms
- group.consumer.session.timeout.ms

Khi dùng protocol mới, không nên giả định hai client property session.timeout.ms và heartbeat.interval.ms vẫn điều khiển hành vi như classic protocol. Hãy kiểm tra phiên bản Kafka broker, kafka-clients và tài liệu tương ứng trước khi chuyển protocol. Khả năng sử dụng protocol mới phụ thuộc phiên bản và cấu hình cụm.

| Nội dung | Classic protocol | Consumer protocol mới |
|---|---|---|
| Session timeout | Consumer cấu hình qua session.timeout.ms, broker áp giới hạn cho phép | Broker quản lý qua group.consumer.session.timeout.ms |
| Heartbeat interval | Consumer cấu hình qua heartbeat.interval.ms | Broker quản lý qua group.consumer.heartbeat.interval.ms |
| Cấu hình group protocol | group.protocol=classic | group.protocol=consumer |
| Khi cần điều chỉnh | Kiểm tra client property và broker min/max session | Điều chỉnh broker-side config và kiểm tra khả năng tương thích |

Nếu chưa có nhu cầu chuyển đổi protocol, hãy dùng cấu hình phù hợp với protocol hiện tại của cụm. Tránh sao chép cấu hình từ một phiên bản Kafka khác mà không kiểm tra client và broker đang chạy.

## 6. Cấu hình trong Spring Boot

Spring Boot cho phép truyền các thuộc tính Kafka Consumer thông qua spring.kafka.consumer.properties. Với YAML, dùng bracket notation để giữ nguyên tên property có dấu chấm.

Ví dụ cho classic protocol:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      properties:
        "[group.protocol]": "classic"
        "[session.timeout.ms]": "15000"
        "[heartbeat.interval.ms]": "5000"
        "[max.poll.interval.ms]": "300000"
        "[max.poll.records]": "100"
~~~

Ý nghĩa:

- group-id xác định consumer group.
- enable-auto-commit=false để Spring Kafka container quản lý commit theo acknowledgement mode.
- session.timeout.ms và heartbeat.interval.ms điều khiển membership heartbeat theo classic protocol.
- max.poll.interval.ms giới hạn khoảng thời gian giữa các lần poll.
- max.poll.records giới hạn số record tối đa được trả về trong một lần poll.

Các giá trị trên chỉ là ví dụ để minh họa mối quan hệ giữa các tham số. Hãy điều chỉnh theo broker, phiên bản Kafka, thời gian xử lý thực tế và mục tiêu phục hồi của hệ thống.

Nếu ứng dụng dùng nhiều ConsumerFactory với cấu hình khác nhau, cần bảo đảm các thuộc tính được truyền vào đúng factory mà listener container sử dụng. Đặt thuộc tính trong spring.kafka.consumer không đảm bảo mọi ConsumerFactory tự tạo đều nhận được cấu hình đó nếu chúng được khởi tạo từ một map riêng.

## 7. Cấu hình bằng ConsumerFactory

Khi tự tạo ConsumerFactory, có thể truyền thuộc tính qua Kafka ConsumerConfig:

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class);

    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 15_000);
    props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 5_000);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Đoạn code minh họa các thuộc tính liên quan đến timeout và heartbeat. Trong ứng dụng thực tế, hãy cấu hình serializer/deserializer, trusted package và type mapping phù hợp với hợp đồng message của ứng dụng. Không dùng cấu hình minh họa này như một bộ cấu hình production hoàn chỉnh.

Nếu sử dụng consumer group protocol mới, hãy kiểm tra các thuộc tính client nào còn được hỗ trợ và cấu hình heartbeat/session ở broker theo protocol đó.

## 8. Quan hệ với Spring Kafka listener container

Mỗi Kafka consumer do listener container tạo ra duy trì membership riêng trong consumer group. Với ConcurrentMessageListenerContainer, mỗi container con có consumer riêng; mỗi consumer có heartbeat và session riêng.

Ví dụ factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Concurrency bằng 3 tạo tối đa ba consumer con. Nó không làm session timeout trở thành một giá trị chung cho toàn container; từng consumer có vòng đời heartbeat và membership riêng.

Nếu topic có ít partition hơn số consumer, một số consumer có thể không được gán partition. Các consumer đó vẫn là member của group và vẫn duy trì membership theo cơ chế client. Vì vậy, tăng concurrency không đồng nghĩa tăng số partition hoặc tăng tốc heartbeat.

Listener nên xử lý có giới hạn thời gian. Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Nếu processIdempotently gọi một API chậm, hãy kiểm soát timeout của HTTP client, database và các dependency. Khi xử lý đồng bộ kéo dài, max.poll.interval.ms là tham số cần xem xét cùng session timeout.

## 9. Điều gì xảy ra khi heartbeat bị gián đoạn?

Một số tình huống thường gặp:

| Tình huống | Tác động có thể xảy ra | Hướng xử lý |
|---|---|---|
| Consumer process bị kill | Không còn heartbeat; session hết hạn và partition được phân phối lại | Khởi động lại instance, theo dõi rebalance và consumer lag |
| Network partition giữa consumer và coordinator | Heartbeat không tới coordinator dù process vẫn chạy | Kiểm tra network, broker connectivity và timeout |
| JVM stop-the-world pause | Heartbeat có thể bị trễ hoặc ngừng trong thời gian pause | Theo dõi GC pause, heap pressure và CPU |
| Broker/coordinator quá tải | Heartbeat request hoặc response bị chậm | Theo dõi broker request latency, network và tải coordinator |
| Listener xử lý quá lâu | Có thể vượt max.poll.interval.ms dù heartbeat vẫn đang chạy trước đó | Tối ưu listener, giảm batch hoặc điều chỉnh poll interval |
| Consumer rebalance | Partition được thu hồi và gán lại; listener có thể tạm dừng | Theo dõi nguyên nhân rebalance và xử lý idempotent |

Khi consumer bị loại khỏi group, record chưa commit có thể được giao lại cho consumer mới hoặc chính consumer cũ sau khi rejoin. Nếu side effect đã hoàn tất nhưng offset chưa commit, xử lý lặp có thể xảy ra. Do đó, handler nên idempotent và offset chỉ được xác nhận sau khi side effect cần thiết hoàn tất.

Một lần heartbeat thất bại đơn lẻ không nhất thiết đồng nghĩa consumer đã chết. Client có thể retry heartbeat hoặc xử lý lỗi tạm thời. Điều cần quan sát là xu hướng heartbeat failure, session expiration và rebalance, thay vì chỉ phản ứng với một log đơn lẻ.

## 10. Chọn timeout theo đặc tính hệ thống

Không có một bộ timeout đúng cho mọi môi trường. Có thể bắt đầu bằng các nguyên tắc:

1. Chọn session timeout đủ ngắn để đáp ứng mục tiêu phục hồi khi consumer thật sự chết, nhưng đủ dài để chịu được network/GC pause thường gặp.
2. Trong classic protocol, đặt heartbeat interval thấp hơn session timeout; mốc khoảng một phần ba là hướng dẫn cấu hình phổ biến.
3. Đặt max.poll.interval.ms dựa trên thời gian xử lý batch trong trường hợp tải cao hoặc dependency chậm.
4. Chọn max.poll.records sao cho thời gian xử lý một batch nằm trong giới hạn poll interval.
5. Đặt timeout của database và HTTP client để listener không bị treo vô thời hạn.
6. Kiểm tra broker min/max session timeout trước khi triển khai cấu hình mới.
7. Thử nghiệm khi một consumer bị dừng đột ngột và khi network bị gián đoạn.

Một cấu hình session timeout ngắn có thể giúp failover nhanh, nhưng nếu ứng dụng thường xuyên có pause dài thì nó sẽ làm rebalance lặp lại. Một cấu hình timeout dài có thể giảm false positive nhưng làm thời gian phát hiện lỗi dài hơn. Chọn giá trị dựa trên dữ liệu vận hành và SLO phục hồi.

## 11. Kiểm thử heartbeat và session timeout

Kiểm thử tích hợp nên xác nhận hành vi của consumer group khi member ngừng gửi heartbeat hoặc không tiếp tục poll. Có thể sử dụng Kafka thật hoặc Testcontainers để kiểm tra với broker tương thích phiên bản đang triển khai.

Các kịch bản có ích:

- Khởi chạy hai consumer trong cùng group, sau đó dừng đột ngột một consumer và quan sát partition được gán lại.
- Giả lập network delay hoặc ngắt kết nối consumer với broker để kiểm tra thời gian phát hiện member mất.
- Tạo listener xử lý lâu hơn max.poll.interval.ms để quan sát việc consumer rời group và rebalance.
- Gửi record, hoàn tất side effect nhưng làm tiến trình dừng trước commit offset để xác nhận handler chịu được giao lại.
- Tăng concurrency và xác nhận số consumer được gán partition phù hợp với số partition của topic.
- Thử giá trị session timeout nằm ngoài broker min/max để xác nhận lỗi cấu hình được phát hiện.

Không nên dùng sleep dài trong unit test để suy luận chính xác thời điểm broker hết session. Hãy dùng integration test, đồng bộ theo sự kiện rebalance hoặc trạng thái assignment và đặt timeout chờ có giới hạn.

## 12. Quan sát trong môi trường chạy thật

Các tín hiệu nên theo dõi:

- Số lần rebalance theo consumer group và nguyên nhân nếu có.
- Số consumer đang hoạt động và partition assignment.
- Consumer lag theo partition.
- Heartbeat request latency, heartbeat failure và session expiration trong client/broker logs hoặc metrics có sẵn.
- Thời gian xử lý listener và khoảng thời gian giữa các lần poll.
- JVM GC pause, CPU, network error và broker coordinator load.
- Số record được giao lại, retry và dead-letter.

Nếu rebalance tăng đột ngột, hãy đối chiếu timestamp với deployment, restart, network incident, GC pause và thay đổi tải. Chỉ tăng session.timeout.ms có thể che bớt triệu chứng mà không giải quyết nguyên nhân gốc.

## 13. Checklist cấu hình

- [ ] Xác định consumer đang dùng classic hay consumer group protocol mới.
- [ ] Với classic protocol, session.timeout.ms nằm trong khoảng broker cho phép.
- [ ] Với classic protocol, heartbeat.interval.ms nhỏ hơn session.timeout.ms và có khoảng dự phòng phù hợp.
- [ ] max.poll.interval.ms phù hợp với thời gian xử lý batch trong tình huống xấu.
- [ ] max.poll.records không tạo batch vượt quá thời gian xử lý cho phép.
- [ ] Listener có timeout cho dependency và không giữ consumer thread vô thời hạn.
- [ ] Side effect có idempotency để chịu được record giao lại sau rebalance.
- [ ] Có metric/log để phân biệt heartbeat failure, poll timeout và rebalance.
- [ ] Đã kiểm thử consumer chết, network gián đoạn và listener xử lý lâu.
- [ ] Cấu hình trong Spring Boot hoặc ConsumerFactory thực sự được listener container sử dụng.

## Kết luận

session.timeout.ms xác định thời gian coordinator chờ heartbeat trước khi loại một consumer khỏi group trong classic protocol. heartbeat.interval.ms điều khiển nhịp gửi heartbeat; max.poll.interval.ms kiểm soát tiến triển của vòng poll. Ba thuộc tính giải quyết các vấn đề liên quan nhưng khác nhau. Trong Spring Kafka, mỗi consumer do listener container tạo ra duy trì membership riêng, vì vậy cần chọn timeout theo phiên bản protocol, giới hạn broker, thời gian xử lý listener và mục tiêu phục hồi. Heartbeat giúp Kafka phát hiện member mất, còn tính đúng đắn của nghiệp vụ vẫn phụ thuộc vào commit offset, retry và idempotency.

