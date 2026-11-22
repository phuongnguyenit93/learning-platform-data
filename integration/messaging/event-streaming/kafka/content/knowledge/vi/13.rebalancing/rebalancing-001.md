# Các nguyên nhân kích hoạt rebalance

## Mục tiêu bài học

Rebalance là quá trình Kafka phân phối lại partition giữa các member của một consumer group. Quá trình này cần thiết khi số member, subscription hoặc tập partition thay đổi. Tuy nhiên, rebalance lặp lại quá thường xuyên có thể làm consumer tạm ngừng nhận dữ liệu, tăng độ trễ và khiến công việc đang xử lý phải được tiếp tục hoặc thực hiện lại.

Sau bài học, bạn có thể:

- Giải thích khi nào Kafka cần rebalance một consumer group.
- Phân biệt thay đổi membership, thay đổi subscription và lỗi heartbeat/poll.
- Nhận diện tác động của `session.timeout.ms`, `heartbeat.interval.ms` và `max.poll.interval.ms`.
- Hiểu vì sao topic mới, tăng partition hoặc regex subscription có thể làm assignment thay đổi.
- Phân biệt rebalance bình thường với rebalance liên tục do cấu hình hoặc sự cố.
- Dùng log, metric và Kafka CLI để tìm member hoặc partition gây ra rebalance.
- Giảm rebalance ngoài ý muốn mà vẫn giữ khả năng phát hiện consumer đã lỗi.

## 1. Rebalance là gì?

Một consumer group chia các partition của những topic đã đăng ký cho các consumer member. Khi tập member hoặc tập partition cần đọc thay đổi, Kafka phải tính lại assignment để các member có quyền sở hữu partition phù hợp. Quá trình tính toán và áp dụng assignment mới được gọi là **rebalance**.

Ví dụ group `order-service` có ba member và sáu partition:

```text
Trước rebalance
  P0  P1  P2  P3  P4  P5
   |   |   |   |   |   |
   v   v   v   v   v   v
  C1  C1  C2  C2  C3  C3

C3 rời group
       |
       v
Group phát hiện membership thay đổi
       |
       v
Tính assignment mới
       |
       v
Sau rebalance
  P0  P1  P2  P3  P4  P5
   |   |   |   |   |   |
   v   v   v   v   v   v
  C1  C1  C1  C2  C2  C2
```

Sơ đồ chỉ minh họa một cách phân phối có thể xảy ra. Assignment thực tế phụ thuộc partition assignor, số member, subscription và trạng thái group.

Rebalance không phải lỗi. Nó là cơ chế bình thường để group thích nghi với việc scale out, scale in, topic thay đổi hoặc member gặp sự cố. Vấn đề xuất hiện khi rebalance xảy ra liên tục, kéo dài hoặc lặp lại mà không có thay đổi hợp lý.

## 2. Những nhóm nguyên nhân chính

Các nguyên nhân thường được chia thành bốn nhóm:

1. **Membership thay đổi:** consumer mới tham gia, consumer đóng, crash hoặc bị xem là không còn hoạt động.
2. **Subscription thay đổi:** ứng dụng đổi danh sách topic, regex bắt đầu khớp topic mới hoặc consumer rời subscription.
3. **Metadata partition thay đổi:** topic được tạo/xóa hoặc số partition thay đổi, làm tập partition mà group quan tâm thay đổi.
4. **Coordinator hoặc giao tiếp group gặp sự cố:** heartbeat, poll, network, broker hoặc coordinator không hoạt động ổn định.

Các nguyên nhân này có thể xuất hiện cùng lúc. Ví dụ một broker mất kết nối làm consumer bỏ lỡ heartbeat, sau đó member bị loại khỏi group; khi broker phục hồi, consumer gia nhập lại và gây thêm một lần rebalance.

## 3. Consumer mới tham gia group

### 3.1. Scale out ứng dụng

Khi khởi động thêm một instance dùng cùng `group.id`, instance mới gửi yêu cầu tham gia group. Kafka cần tính lại assignment để chia partition cho member mới.

Ví dụ:

```text
Trước:
  group.id = order-service
  C1 -> P0, P1, P2, P3

Khởi động C2 với cùng group.id:
  group membership thay đổi
  -> rebalance

Sau:
  C1 -> P0, P1
  C2 -> P2, P3
```

Rebalance khi scale out là hành vi mong đợi. Nếu triển khai nhiều instance cùng lúc, group có thể trải qua nhiều lần membership change trong một khoảng ngắn. Nên dùng rolling deployment có kiểm soát và tránh khởi động/tắt hàng loạt member không cần thiết.

### 3.2. Consumer khởi động lại

Khi một process khởi động lại, Kafka nhìn thấy member cũ rời đi hoặc hết hạn và member mới tham gia. Tùy thời gian dừng, static membership và group protocol, group có thể thực hiện một hoặc nhiều lần rebalance.

Nếu ứng dụng restart thường xuyên do health check, lỗi cấu hình, crash loop hoặc triển khai thiếu ổn định, group có thể rebalance liên tục. Hãy điều tra nguyên nhân restart của process thay vì chỉ tăng timeout để che triệu chứng.

### 3.3. Có nhiều consumer hơn partition

Thêm member vẫn có thể làm group rebalance ngay cả khi số member đã vượt số partition. Sau khi tính lại, một số member sẽ không được gán partition. Các member dư không làm tăng song song của group, nhưng membership change vẫn cần được group xử lý.

Trước khi scale consumer, so sánh số partition, số member, throughput mỗi partition và thời gian xử lý. Nếu số partition là giới hạn, thêm instance sẽ không tạo thêm partition để xử lý.

## 4. Consumer rời group hoặc bị mất

### 4.1. Đóng consumer có chủ đích

Khi ứng dụng gọi `consumer.close()` hoặc `unsubscribe()`, consumer rời subscription/group-managed assignment. Các partition đang thuộc member đó cần được phân phối lại cho những member còn lại.

Đóng consumer có kiểm soát giúp group nhận biết member rời đi sớm hơn so với chờ timeout. Trước khi đóng, ứng dụng nên dừng nhận công việc mới, hoàn tất hoặc hủy có kiểm soát công việc đang chạy và commit offset đã xử lý an toàn.

### 4.2. Process crash hoặc máy bị tắt

Nếu consumer bị crash, bị kill -9, máy mất điện hoặc container bị xóa đột ngột, nó không thể gửi thông báo rời group bình thường. Coordinator phải phát hiện member không còn hoạt động thông qua heartbeat/session timeout rồi khởi động quy trình phân phối lại.

Vì coordinator cần thời gian phát hiện lỗi, partition có thể tạm thời chưa được giao cho member khác. Thời gian phát hiện quá dài làm tăng thời gian gián đoạn; đặt timeout quá ngắn lại có thể loại nhầm consumer chỉ vì mạng hoặc JVM tạm thời chậm.

### 4.3. Rời group do lỗi ứng dụng

Một số lỗi ứng dụng có thể khiến consumer đóng hoặc không còn tham gia group:

- Exception không được xử lý làm process kết thúc.
- Container bị liveness probe đánh dấu unhealthy và restart.
- Thread sở hữu consumer bị dừng hoặc không tiếp tục vòng lặp `poll()`.
- Lỗi deserializer hoặc xử lý nghiệp vụ làm ứng dụng liên tục restart.
- Ứng dụng chủ động gọi `unsubscribe()` hoặc thay đổi subscription.

Hãy đối chiếu thời điểm rebalance với log shutdown/restart, exit code của container và exception đầu tiên. Dòng log rebalance thường là hệ quả; nguyên nhân gốc có thể xuất hiện trước đó.

## 5. Không gửi heartbeat đúng hạn

### 5.1. Vai trò của heartbeat

Consumer gửi heartbeat đến group coordinator để cho biết member còn hoạt động và muốn tiếp tục tham gia group. Nếu coordinator không nhận heartbeat trong thời gian quy định, member có thể bị xem là đã mất và partition được phân phối lại.

Với **classic consumer group protocol**, các cấu hình thường gặp gồm:

| Cấu hình | Vai trò |
|---|---|
| `heartbeat.interval.ms` | Khoảng thời gian client dự kiến gửi heartbeat |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem member đã mất |
| `max.poll.interval.ms` | Khoảng thời gian tối đa giữa hai lần gọi `poll()` trong group management |

Thông thường `heartbeat.interval.ms` được đặt nhỏ hơn đáng kể so với `session.timeout.ms`; nhiều cấu hình dùng khoảng một phần ba session timeout làm điểm khởi đầu. Giá trị phù hợp phụ thuộc latency mạng, tải broker và yêu cầu phát hiện lỗi.

### 5.2. Mất heartbeat do mạng hoặc broker

Consumer có thể vẫn chạy nhưng heartbeat không đến coordinator vì:

- Network partition, packet loss hoặc latency tăng đột biến.
- DNS, route hoặc firewall làm kết nối đến coordinator bị gián đoạn.
- Group coordinator broker đang restart, quá tải hoặc chuyển vai trò.
- JVM pause dài, CPU starvation hoặc thread bị block.
- Container bị giới hạn CPU khiến heartbeat không được gửi đúng hạn.

Khi kết nối phục hồi, consumer có thể phải tìm coordinator và tham gia lại group. Nếu nhiều consumer cùng bị ảnh hưởng, nhiều partition có thể được phân phối lại trong một khoảng thời gian ngắn.

### 5.3. Session timeout quá thấp hoặc quá cao

Nếu `session.timeout.ms` quá thấp so với biến động bình thường của mạng và JVM, consumer có thể bị loại khỏi group dù chỉ chậm tạm thời. Điều này tạo rebalance không cần thiết.

Nếu timeout quá cao, group mất nhiều thời gian hơn để phát hiện một consumer đã chết thật sự. Trong thời gian đó, partition có thể chưa được member khác tiếp quản.

Không có một giá trị đúng cho mọi cluster. Hãy đo heartbeat latency, GC pause, network latency và thời gian phục hồi thực tế trước khi thay đổi.

### 5.4. Lưu ý về consumer group protocol mới

Các phiên bản Kafka mới hỗ trợ consumer group protocol mới bên cạnh classic protocol. Với protocol mới, một số thông số heartbeat/session có thể được quản lý ở broker và tên/cách cấu hình phía client khác với `heartbeat.interval.ms` và `session.timeout.ms` của classic protocol.

Vì vậy, trước khi áp dụng một runbook timeout, hãy xác định `group.protocol` và phiên bản Kafka client/broker. Không sao chép cấu hình classic sang một group đang dùng protocol mới nếu tài liệu phiên bản không yêu cầu như vậy.

## 6. Không gọi `poll()` đúng hạn

### 6.1. `max.poll.interval.ms`

`max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa các lần gọi `poll()` khi consumer dùng group management. Nếu ứng dụng xử lý record quá lâu và không gọi `poll()` lại trong giới hạn, consumer bị xem là không còn tiến triển và group có thể rebalance.

Ví dụ cấu hình:

```java
props.put("max.poll.interval.ms", 300_000); // 5 phút
props.put("max.poll.records", 100);
```

Hai giá trị chỉ minh họa. `max.poll.records` giới hạn số record trả về trong một lần poll; giảm batch size có thể giúp thời gian xử lý mỗi batch nằm trong poll interval. Tuy nhiên, cần đo thời gian xử lý thực tế và throughput để chọn giá trị phù hợp.

### 6.2. Xử lý nghiệp vụ quá lâu trong poll loop

Ví dụ anti-pattern:

```java
while (running) {
    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, String> record : records) {
        // Có thể mất nhiều phút vì gọi API bên ngoài hoặc xử lý batch nặng.
        processSlowBusinessOperation(record);
    }
}
```

Nếu tổng thời gian xử lý batch vượt `max.poll.interval.ms`, consumer có thể bị loại khỏi group. Việc gọi `poll()` sau đó có thể khiến consumer phải tham gia lại và nhận assignment mới.

Các nguyên nhân thường gặp:

- Gọi HTTP/database đồng bộ với timeout quá dài.
- Xử lý một batch lớn trong một thread.
- Lock contention hoặc deadlock trong ứng dụng.
- Ghi file hoặc thao tác I/O chậm.
- Retry nghiệp vụ không giới hạn ngay trong poll loop.

### 6.3. Cách khắc phục

- Giảm `max.poll.records` để giảm số record xử lý trong mỗi batch.
- Tối ưu thao tác database/API và đặt timeout hữu hạn.
- Chia nhỏ công việc dài thành các bước có thể tiếp tục.
- Dùng worker pool có giới hạn nếu cần xử lý bất đồng bộ; theo dõi offset hoàn tất riêng cho từng partition.
- Gọi `pause()` với partition cần tạm dừng để kiểm soát lượng record mới, nhưng vẫn tiếp tục gọi `poll()` định kỳ để duy trì group membership.
- Chỉ tăng `max.poll.interval.ms` khi thời gian xử lý dài là yêu cầu có chủ đích và đã tính đến thời gian phát hiện consumer lỗi.

Nếu chuyển record sang worker thread, không được để worker tùy ý gọi các thao tác trên `KafkaConsumer`. Consumer không thread-safe cho các thao tác thông thường; một thread nên sở hữu consumer và phối hợp với worker qua queue/thread-safe state.

### 6.4. `max.poll.interval.ms` khác session timeout

Hai timeout bảo vệ hai khía cạnh khác nhau:

- `session.timeout.ms` trong classic protocol phát hiện member không còn gửi heartbeat.
- `max.poll.interval.ms` phát hiện ứng dụng không tiếp tục gọi `poll()` trong khoảng thời gian cho phép, dù thread heartbeat có thể vẫn hoạt động.

Một consumer có thể gửi heartbeat nhưng xử lý nghiệp vụ quá lâu và vi phạm max poll interval. Vì vậy, chỉ nhìn heartbeat không đủ để kết luận consumer đang tiến triển bình thường.

Với static membership (`group.instance.id`), khi vượt max poll interval, client ngừng heartbeat nhưng partition reassignment có thể được trì hoãn đến khi session timeout hết hạn. Hành vi chi tiết phụ thuộc protocol và phiên bản; static membership không làm consumer được phép bỏ qua poll interval.

## 7. Thay đổi subscription

### 7.1. Gọi `subscribe()` với tập topic khác

Khi ứng dụng đổi danh sách topic đã đăng ký, tập partition quan tâm của group có thể thay đổi. Kafka cần tính lại assignment để phù hợp với subscription mới.

Ví dụ:

```java
consumer.subscribe(List.of("orders", "payments"));

// Sau khi cấu hình ứng dụng thay đổi:
consumer.subscribe(List.of("orders", "payments", "shipments"));
```

Lần gọi thứ hai đặt subscription mới gồm cả ba topic. Nếu topic mới có partition, các partition đó có thể được thêm vào assignment sau rebalance.

### 7.2. `unsubscribe()`

Gọi `unsubscribe()` làm consumer rời subscription hiện tại. Các partition đã được giao cho member này cần được phân phối lại cho member còn lại trong group. Nếu member không còn topic nào để đọc, group membership/subscription của nó thay đổi theo API và protocol đang dùng.

### 7.3. Regex subscription phát hiện topic mới

Consumer đăng ký bằng `subscribe(Pattern)` có thể tự động nhận topic mới khi tên topic khớp pattern và metadata được làm mới.

Ví dụ:

```java
consumer.subscribe(Pattern.compile("^orders\\..+$"));
```

Khi topic `orders.refunded` được tạo, consumer có thể phát hiện topic này qua metadata refresh. Nếu topic có partition mới đối với group, tập partition cần phân phối thay đổi và có thể kích hoạt rebalance.

Regex quá rộng có thể khiến một topic mới ngoài dự kiến được thêm vào subscription, kéo theo rebalance và tăng tải xử lý. Hãy giới hạn namespace và kiểm tra naming convention.

## 8. Thay đổi metadata topic và partition

### 8.1. Tạo topic mới

Nếu topic mới thuộc subscription của group, group cần cập nhật tập partition. Điều này đặc biệt dễ thấy với pattern subscription; với danh sách topic tĩnh, topic mới chỉ ảnh hưởng group nếu ứng dụng cập nhật subscription hoặc topic đó là một phần của subscription hiện tại.

### 8.2. Tăng số partition

Khi tăng partition của topic mà group đang đọc, số partition có thể được gán thay đổi. Consumer group cần tính lại assignment để các partition mới được giao cho member.

Ví dụ topic `orders` tăng từ bốn lên sáu partition:

```text
Trước:
  P0 P1 P2 P3
  C1 C1 C2 C2

Sau khi topic có thêm P4, P5:
  P0 P1 P2 P3 P4 P5
  C1 C1 C2 C2 C1 C2
```

Tăng partition có thể ảnh hưởng mapping key-partition của producer và ordering theo key. Trước khi thay đổi, cần đánh giá cả consumer assignment lẫn producer partitioning.

### 8.3. Xóa topic hoặc thay đổi trạng thái topic

Topic bị xóa, partition offline hoặc metadata thay đổi có thể làm assignment cần được cập nhật. Client có thể phải refresh metadata và group có thể trải qua quá trình điều phối lại. Hành vi cụ thể phụ thuộc loại thay đổi, protocol và phiên bản Kafka.

Không nên xem mọi lần metadata refresh đều gây rebalance. Rebalance chỉ cần khi thay đổi làm ảnh hưởng subscription, membership hoặc tập partition/assignment mà group quản lý.

## 9. Group coordinator thay đổi hoặc gặp sự cố

Group coordinator là broker chịu trách nhiệm điều phối membership và offset của một consumer group. Nếu broker đang giữ vai trò coordinator bị dừng, mất kết nối hoặc partition nội bộ liên quan chuyển leader, consumer có thể phải tìm coordinator mới và tham gia lại group.

Các nguyên nhân có thể gồm:

- Broker coordinator restart hoặc bị mất kết nối.
- Leader của partition trong `__consumer_offsets` thay đổi.
- Broker quá tải khiến JoinGroup, SyncGroup hoặc heartbeat request timeout.
- Network giữa consumer và coordinator không ổn định.
- Cluster đang bảo trì hoặc có sự cố control plane.

Khi điều tra, kiểm tra log coordinator, trạng thái broker, leader của `__consumer_offsets`, request latency và lỗi `NOT_COORDINATOR`, `COORDINATOR_NOT_AVAILABLE` hoặc timeout tương ứng. Consumer thường tự tìm coordinator mới theo client protocol, nhưng quá trình này có thể làm group gián đoạn tạm thời.

## 10. Static membership và cooperative assignment

### 10.1. Static membership với `group.instance.id`

Static membership cho phép một consumer dùng `group.instance.id` ổn định để đại diện cho một instance logic. Khi instance tạm thời restart trong thời gian phù hợp, group có thể giữ chỗ membership của instance thay vì lập tức phân phối lại partition như dynamic member.

Ví dụ:

```java
props.put("group.id", "order-service");
props.put("group.instance.id", "order-service-1");
```

Mỗi instance tĩnh trong cùng group phải có `group.instance.id` duy nhất và ổn định. Nếu hai instance cùng dùng một ID, một member có thể bị fencing với lỗi như `FencedInstanceIdException`; đây là lỗi cấu hình identity cần xử lý, không phải cách scale consumer.

Static membership có thể giảm rebalance do restart ngắn, nhưng nếu instance mất hẳn, group có thể chờ đến khi session timeout trước khi giải phóng assignment. Chọn timeout quá dài sẽ kéo dài thời gian phát hiện lỗi.

### 10.2. Cooperative sticky assignment

Với eager rebalance, partition assignment cũ có thể bị thu hồi toàn bộ trước khi assignment mới được áp dụng. Với cooperative/incremental rebalance, chỉ các partition cần chuyển owner mới bị thu hồi theo từng bước, giúp giảm phạm vi dừng tiêu thụ.

Một assignor thường gặp là `CooperativeStickyAssignor`, nếu phiên bản Kafka client và cấu hình group hỗ trợ:

```java
props.put(
    "partition.assignment.strategy",
    "org.apache.kafka.clients.consumer.CooperativeStickyAssignor"
);
```

Cooperative assignment không loại bỏ nguyên nhân rebalance. Nó thay đổi cách chuyển partition để giảm việc thu hồi toàn bộ assignment. Khi chuyển đổi assignor hoặc rolling upgrade, cần làm theo hướng dẫn tương thích của phiên bản Kafka để tránh member dùng chiến lược không tương thích.

### 10.3. Static membership và cooperative assignment giải quyết vấn đề khác nhau

| Cơ chế | Mục tiêu chính | Giới hạn |
|---|---|---|
| Static membership | Giảm rebalance khi một instance tạm thời restart | Instance phải có ID duy nhất; lỗi thật có thể được phát hiện chậm hơn do chờ timeout |
| Cooperative assignment | Giảm số partition bị thu hồi trong một lần rebalance | Vẫn có rebalance khi membership/subscription/partition thay đổi |
| Tăng timeout | Giảm việc loại nhầm member do chậm tạm thời | Làm chậm phát hiện member chết thật |
| Giảm `max.poll.records` | Giảm thời gian xử lý một batch | Có thể giảm throughput nếu batch quá nhỏ |

Chọn cơ chế theo nguyên nhân quan sát được. Không bật tất cả tùy chọn cùng lúc mà không hiểu tác động.

## 11. Cách nhận biết nguyên nhân từ dấu hiệu thực tế

| Dấu hiệu | Nguyên nhân có khả năng | Hướng kiểm tra |
|---|---|---|
| Rebalance ngay khi deploy thêm instance | Member mới tham gia group | Kiểm tra lịch triển khai và group membership |
| Rebalance khi một pod restart | Process rời group hoặc heartbeat bị mất | Kiểm tra pod events, exit code và shutdown log |
| Rebalance lặp sau các batch xử lý lớn | `max.poll.interval.ms` bị vượt | Đo thời gian xử lý batch, giảm `max.poll.records` hoặc tối ưu handler |
| Rebalance ngẫu nhiên khi tải CPU cao | CPU starvation hoặc GC pause | Kiểm tra CPU throttling, GC log và thread dump |
| Nhiều consumer cùng rời group | Network/coordinator/broker có vấn đề | Kiểm tra heartbeat, request timeout và broker coordinator |
| Rebalance sau khi tạo topic mới | Regex subscription hoặc metadata partition thay đổi | Kiểm tra pattern và topic metadata |
| Rebalance sau khi tăng partition | Tập partition thay đổi | Kiểm tra lịch alter topic và assignment |
| Member liên tục bị loại rồi gia nhập lại | Session timeout, heartbeat hoặc poll không ổn định | Kiểm tra timeout, network và poll loop |
| Rebalance khi thay đổi assignor/phiên bản client | Group member metadata hoặc protocol thay đổi | Kiểm tra cấu hình assignor và kế hoạch rolling upgrade |

## 12. Quan sát rebalance bằng log, metric và CLI

### 12.1. Log consumer

Log của Kafka client thường có thông tin về:

- Consumer đang tham gia group hoặc gửi JoinGroup.
- Group coordinator được tìm thấy hoặc thay đổi.
- Partition bị revoke và partition được assign.
- Heartbeat thất bại hoặc session timeout.
- Consumer vượt `max.poll.interval.ms`.
- Lỗi authorization, coordinator hoặc protocol.

Khi điều tra, lấy một khoảng thời gian đủ rộng trước và sau dòng log rebalance. Tìm exception hoặc cảnh báo xuất hiện trước thời điểm group bắt đầu rejoin; đó thường là manh mối nguyên nhân gốc.

### 12.2. ConsumerRebalanceListener

Ứng dụng có thể log nguyên nhân quan sát được từ callback và partition assignment:

```java
consumer.subscribe(List.of("orders"), new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        log.info("Partitions revoked: {}", partitions);
        commitCompletedOffsets(partitions);
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        log.info("Partitions assigned: {}", partitions);
    }
});
```

Callback cho biết partition nào bị thu hồi hoặc được giao, nhưng không phải lúc nào cũng cho biết chính xác nguyên nhân ban đầu. Cần kết hợp với log group coordinator, heartbeat, poll interval và lịch thay đổi hạ tầng.

### 12.3. Kafka CLI

Liệt kê consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

Mô tả một group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Lệnh describe giúp xem topic, partition, current offset, log end offset, lag và thông tin member tùy phiên bản/trạng thái group. Nó không thay thế log rebalance, nhưng giúp xác định group có member hay assignment bất thường và lag có tăng trong lúc rebalance hay không.

### 12.4. Metric cần theo dõi

Các metric hữu ích tùy client/exporter gồm:

- Số lần rebalance và thời gian rebalance.
- Số consumer member và số partition được assign.
- Số lần heartbeat thất bại hoặc heartbeat latency.
- Thời gian giữa hai lần `poll()`.
- Consumer lag theo group và partition.
- Thời gian xử lý record/batch.
- Số lần commit offset thất bại.
- Coordinator request latency và lỗi network.

Tên metric cụ thể thay đổi theo Kafka client, protocol và hệ thống monitoring. Hãy xác minh MBean/metric thực tế trước khi tạo dashboard hoặc alert.

## 13. Quy trình điều tra rebalance liên tục

Khi một group rebalance quá thường xuyên, thực hiện theo thứ tự:

1. **Xác định thời điểm:** đối chiếu rebalance với deploy, autoscaling, restart container, topic creation hoặc partition increase.
2. **Kiểm tra membership:** member nào tham gia/rời group, có instance nào restart hoặc bị fencing không?
3. **Kiểm tra poll loop:** thời gian giữa các lần `poll()` có vượt `max.poll.interval.ms` không?
4. **Kiểm tra heartbeat:** có timeout, coordinator change hoặc network interruption không?
5. **Kiểm tra xử lý nghiệp vụ:** batch có quá lớn, API/database có chậm hoặc retry không giới hạn không?
6. **Kiểm tra metadata:** regex có match topic mới, topic có đổi partition hoặc bị xóa không?
7. **Kiểm tra coordinator/broker:** broker có restart, quá tải hoặc lỗi partition `__consumer_offsets` không?
8. **Chọn biện pháp:** tối ưu handler, điều chỉnh poll batch, ổn định deployment, sửa network hoặc cân nhắc static/cooperative membership.
9. **Đo lại:** theo dõi số lần rebalance, thời gian gián đoạn, lag và throughput sau thay đổi.

Không bắt đầu bằng việc tăng mọi timeout. Timeout lớn hơn có thể giảm rebalance do chậm tạm thời nhưng cũng kéo dài thời gian phát hiện consumer chết thật.

## 14. Cách giảm rebalance ngoài ý muốn

- Giữ `group.id` ổn định giữa các instance cùng một pipeline.
- Dùng `group.instance.id` duy nhất và ổn định nếu static membership phù hợp với cách triển khai.
- Giữ poll loop hoạt động thường xuyên; tránh xử lý nghiệp vụ dài đồng bộ trên consumer thread.
- Điều chỉnh `max.poll.records` theo thời gian xử lý thực tế.
- Đặt timeout mạng và heartbeat dựa trên latency đo được.
- Dùng cooperative assignment nếu client/protocol và hệ thống hỗ trợ.
- Tránh deploy hoặc scale tất cả member cùng lúc khi không cần thiết.
- Giới hạn regex subscription vào namespace topic thực sự cần đọc.
- Lên kế hoạch trước khi tạo topic hoặc tăng partition.
- Giữ broker coordinator và network ổn định; theo dõi broker restart và `__consumer_offsets`.
- Xử lý exception có kiểm soát để tránh consumer crash loop.
- Commit offset chỉ đến vị trí đã xử lý liên tục thành công và làm side effect idempotent để chịu được xử lý lại.

## 15. Câu hỏi tự kiểm tra

1. Rebalance được kích hoạt khi những thành phần nào của consumer group thay đổi?
2. Vì sao khởi động thêm một consumer với cùng `group.id` có thể làm assignment thay đổi?
3. Điều gì xảy ra khi một consumer crash mà không gọi `close()`?
4. `heartbeat.interval.ms` và `session.timeout.ms` có quan hệ như thế nào trong classic protocol?
5. Vì sao consumer có thể gửi heartbeat nhưng vẫn vi phạm `max.poll.interval.ms`?
6. Gọi `subscribe()` với tập topic mới có thể tác động đến group như thế nào?
7. Vì sao regex subscription có thể kích hoạt rebalance khi một topic mới được tạo?
8. Tăng partition của topic đang được consumer group đọc có thể làm thay đổi điều gì?
9. Group coordinator broker restart có thể ảnh hưởng đến consumer group ra sao?
10. Static membership với `group.instance.id` giúp giảm loại rebalance nào và có đánh đổi gì?
11. Cooperative assignment khác eager rebalance ở cách thu hồi partition như thế nào?
12. Vì sao tăng `session.timeout.ms` hoặc `max.poll.interval.ms` không phải lúc nào cũng là cách khắc phục tốt nhất?

## Kết luận

Rebalance thường xuất phát từ membership thay đổi, subscription hoặc metadata partition thay đổi, hay consumer không duy trì heartbeat/poll đúng hạn. Việc thêm instance hoặc tạo topic mới có thể gây rebalance hợp lệ; crash loop, xử lý batch quá lâu, network chập chờn hoặc coordinator quá tải có thể tạo rebalance lặp lại. Muốn giảm gián đoạn, hãy xác định đúng trigger qua log và metric, giữ poll loop ổn định, quản lý deployment và subscription có kế hoạch, rồi mới cân nhắc timeout, static membership hoặc cooperative assignment.
