# group.id và sự độc lập giữa các nhóm đọc cùng topic

## Mục tiêu bài học

Kafka consumer group cho phép nhiều consumer cùng chia nhau xử lý một luồng dữ liệu. Giá trị `group.id` xác định nhóm logic mà một consumer tham gia. Các consumer dùng cùng `group.id` phối hợp phân chia partition và chia sẻ tiến độ đọc; các consumer dùng `group.id` khác nhau hoạt động như những nhóm độc lập, mỗi nhóm có assignment và offset riêng.

Sau bài học, bạn có thể:

- Giải thích vai trò của `group.id` trong consumer group.
- Phân biệt nhiều consumer cùng group với nhiều group độc lập cùng đọc một topic.
- Mô tả cách Kafka chia partition trong một group và cách mỗi group theo dõi offset riêng.
- Hiểu vị trí lưu committed offset và ý nghĩa của commit offset.
- Chọn `group.id` ổn định để ứng dụng tiếp tục từ tiến độ cũ sau restart.
- Sử dụng `auto.offset.reset` đúng khi group chưa có offset hợp lệ.
- Thiết kế nhiều luồng xử lý độc lập như nghiệp vụ, thông báo và phân tích cùng đọc một topic.
- Nhận diện lỗi do dùng nhầm `group.id`, tạo group mới ngoài ý muốn hoặc để group lag vượt retention.

## 1. `group.id` là gì?

### 1.1. Định danh một nhóm xử lý logic

`group.id` là cấu hình định danh consumer group. Các consumer có cùng giá trị `group.id` tham gia cùng một nhóm logic và được Kafka phối hợp phân công partition. Ví dụ:

```properties
bootstrap.servers=localhost:9092
group.id=order-projection
key.deserializer=org.apache.kafka.common.serialization.StringDeserializer
value.deserializer=org.apache.kafka.common.serialization.StringDeserializer
```

Trong ví dụ, `order-projection` là tên nhóm xử lý. Khi chạy thêm một instance khác với cùng `group.id`, instance đó gia nhập nhóm đang tồn tại và có thể nhận một phần partition từ các member khác.

`group.id` không phải tên consumer instance, tên topic hay mã định danh của một message. Nó đại diện cho một subscription logic có tiến độ đọc riêng. Tên group nên ổn định trong suốt vòng đời của cùng một ứng dụng xử lý, trừ khi chủ động muốn bắt đầu một tiến độ tiêu thụ độc lập.

### 1.2. Vì sao Kafka cần group ID?

Kafka cần biết consumer nào đang phối hợp với consumer nào để:

- Chia partition giữa các member trong cùng nhóm.
- Theo dõi member tham gia, rời đi hoặc mất kết nối.
- Điều phối rebalance khi membership hoặc subscription thay đổi.
- Lưu và khôi phục committed offset của nhóm theo từng topic-partition.
- Theo dõi tiến độ và consumer lag của từng nhóm.

Group coordinator quản lý hoạt động của group. Mỗi group có một coordinator phụ trách điều phối membership và offset commit. Các consumer trong group cần dùng cùng `group.id` để tham gia cùng cơ chế này.

### 1.3. `group.id` phải được cấu hình nhất quán

Nếu hai instance của cùng một ứng dụng cần chia tải, chúng phải dùng cùng giá trị `group.id`. Nếu vô tình cấu hình khác nhau, Kafka xem chúng là hai group riêng biệt; cả hai có thể đọc lại toàn bộ partition của topic và xử lý trùng ở cấp nghiệp vụ.

Ngược lại, nếu hai ứng dụng cần nhận toàn bộ event độc lập nhưng dùng chung `group.id`, chúng sẽ chia partition cho nhau. Mỗi ứng dụng chỉ nhận một phần luồng dữ liệu thay vì cả hai đều nhận toàn bộ.

## 2. Cùng `group.id`: chia partition và chia tải

### 2.1. Các member cùng group không broadcast mỗi record cho nhau

Khi nhiều consumer cùng đăng ký một topic và dùng cùng `group.id`, Kafka phân chia partition giữa các member. Tại một thời điểm, một partition được gán cho tối đa một member trong group. Vì vậy, các member cùng group chia nhau công việc; mỗi member không nhận bản sao của mọi record từ tất cả partition.

Ví dụ topic `orders` có sáu partition và group `order-service` có ba consumer:

```text
Topic: orders
  P0   P1   P2   P3   P4   P5
   |    |    |    |    |    |
   v    v    v    v    v    v
  C1   C1   C2   C2   C3   C3

Group ID: order-service
```

Assignment trên chỉ là ví dụ. Partition assignor có thể tạo cách phân phối khác. Điều quan trọng là mỗi partition chỉ được giao cho một member trong group tại một thời điểm, còn các partition khác nhau có thể được xử lý song song.

### 2.2. Số consumer không đồng nghĩa với mức song song vô hạn

Mức song song tối đa ở tầng consumer group bị giới hạn bởi số partition có thể được gán. Ví dụ topic có ba partition:

| Số consumer trong cùng group | Kết quả thường thấy |
|---:|---|
| 1 | Một consumer nhận cả ba partition |
| 2 | Hai consumer chia nhau ba partition |
| 3 | Mỗi consumer có thể nhận một partition |
| 5 | Tối đa ba consumer nhận partition; ít nhất hai consumer không có partition |

Thêm consumer vượt số partition không làm một partition được nhiều member cùng group xử lý song song. Nếu cần tăng mức song song, cần xem xét số partition, năng lực xử lý mỗi partition và yêu cầu ordering trước khi thay đổi topology.

### 2.3. Scale out bằng cách giữ nguyên group ID

Khi triển khai thêm instance của cùng một service, giữ nguyên `group.id` để instance mới tham gia nhóm hiện tại:

```text
Trước khi scale:
  group.id = order-projection
  Consumer A -> P0, P1, P2, P3

Sau khi scale:
  group.id = order-projection
  Consumer A -> P0, P1
  Consumer B -> P2, P3
```

Kafka có thể thực hiện rebalance để chuyển assignment. Trong thời gian rebalance, một số partition có thể tạm dừng tiêu thụ. Ứng dụng cần xử lý offset, công việc đang dang dở và side effect idempotent để tránh bỏ sót hoặc xử lý trùng.

Nếu mỗi instance dùng một `group.id` khác nhau, chúng không scale out theo cách chia tải. Thay vào đó, mỗi instance tạo một group độc lập và có thể đọc toàn bộ topic.

## 3. Group ID khác nhau: mỗi nhóm đọc độc lập

### 3.1. Một topic có thể phục vụ nhiều ứng dụng

Kafka lưu record trong topic. Nhiều consumer group có thể đọc cùng topic độc lập mà không cần producer gửi thêm một bản copy cho mỗi ứng dụng.

Ví dụ topic `orders` được ba ứng dụng sử dụng:

```text
                         Topic: orders
                      P0   P1   P2   P3
                       |    |    |    |
          +------------+----+----+----+------------+
          |                         |              |
          v                         v              v
  Group: order-service     Group: notification   Group: analytics
  group.id=order-service   group.id=notification group.id=analytics
          |                         |              |
          v                         v              v
  Cập nhật đơn hàng        Gửi email/push        Tổng hợp báo cáo
```

Mỗi group có thể đọc toàn bộ partition của topic theo assignment nội bộ của chính group đó. Các group không chia partition với nhau. Group `order-service` đọc record không làm group `notification` mất quyền đọc record đó.

### 3.2. Mỗi group có offset riêng

Committed offset được theo dõi theo tổ hợp group, topic và partition. Có thể hình dung khóa logic như sau:

```text
(group.id, topic, partition) -> committed offset
```

Ví dụ cùng topic `orders`, partition 0:

| Consumer group | Committed offset của P0 | Ý nghĩa |
|---|---:|---|
| `order-service` | 120 | Nhóm xử lý đơn hàng đã commit vị trí kế tiếp là 120 |
| `notification` | 95 | Nhóm thông báo đang ở tiến độ riêng |
| `analytics` | 180 | Nhóm phân tích đã đọc xa hơn hai nhóm còn lại |

Các con số chỉ minh họa. Việc một group commit offset 180 không thay đổi offset 120 của group khác. Một group có thể đang đọc nhanh, một group khác có thể lag, và group thứ ba có thể tạm dừng mà không làm thay đổi tiến độ của các group còn lại.

### 3.3. Độc lập về tiến độ, dùng chung dữ liệu topic

Consumer group độc lập về assignment và offset, nhưng không có một bản sao vật lý riêng của topic cho từng group. Các group đọc cùng log dữ liệu do broker lưu trữ.

Điều này có hai hệ quả:

- Tạo thêm consumer group không yêu cầu producer nhân bản record thành nhiều topic chỉ để phục vụ từng ứng dụng.
- Retention của topic vẫn áp dụng chung. Nếu segment bị xóa, mọi group chưa đọc đến dữ liệu đó đều không thể lấy lại record đã bị xóa từ topic.

Do đó, group độc lập không có nghĩa dữ liệu được giữ riêng hoặc vô thời hạn cho từng ứng dụng. Thời gian retention cần đủ cho group chậm nhất và yêu cầu replay của hệ thống.

## 4. Ví dụ: hai ứng dụng cùng đọc topic `orders`

Giả sử hệ thống bán hàng có hai nhu cầu:

- `order-projection` cập nhật trạng thái đơn hàng trong database nghiệp vụ.
- `order-analytics` đọc event để tổng hợp báo cáo.

Hai ứng dụng cần nhận đầy đủ sự kiện độc lập, nên cấu hình hai group ID khác nhau.

### 4.1. Cấu hình group nghiệp vụ

```java
Properties orderProps = new Properties();
orderProps.put("bootstrap.servers", "localhost:9092");
orderProps.put("group.id", "order-projection");
orderProps.put("key.deserializer",
    "org.apache.kafka.common.serialization.StringDeserializer");
orderProps.put("value.deserializer",
    "org.apache.kafka.common.serialization.StringDeserializer");
orderProps.put("enable.auto.commit", "false");
```

### 4.2. Cấu hình group phân tích

```java
Properties analyticsProps = new Properties();
analyticsProps.put("bootstrap.servers", "localhost:9092");
analyticsProps.put("group.id", "order-analytics");
analyticsProps.put("key.deserializer",
    "org.apache.kafka.common.serialization.StringDeserializer");
analyticsProps.put("value.deserializer",
    "org.apache.kafka.common.serialization.StringDeserializer");
analyticsProps.put("enable.auto.commit", "false");
```

Hai cấu hình có cùng bootstrap server và topic nhưng `group.id` khác nhau. Mỗi ứng dụng sẽ tham gia một consumer group riêng, nhận assignment riêng và commit offset riêng.

### 4.3. Tạo consumer và đăng ký topic

```java
KafkaConsumer<String, String> orderConsumer =
    new KafkaConsumer<>(orderProps);
orderConsumer.subscribe(List.of("orders"));

KafkaConsumer<String, String> analyticsConsumer =
    new KafkaConsumer<>(analyticsProps);
analyticsConsumer.subscribe(List.of("orders"));
```

Trong ứng dụng thực tế, hai consumer thường chạy trong hai service/process riêng. Nếu chạy trong cùng process để demo, mỗi consumer cần thread sở hữu riêng vì `KafkaConsumer` không thread-safe cho các thao tác thông thường.

### 4.4. Kết quả mong đợi

Nếu topic có record A, B, C, cả hai group đều có thể đọc A, B, C theo thứ tự offset trong từng partition:

```text
Producer -> orders: A, B, C
                 |
          +------+------+
          |             |
          v             v
   order-projection  order-analytics
       A, B, C          A, B, C
```

Nếu `order-projection` đã commit qua C còn `order-analytics` mới commit qua A, hai group vẫn độc lập. Group analytics tiếp tục từ tiến độ của chính nó.

## 5. Offset được lưu và khôi phục theo group

### 5.1. Offset là vị trí đọc, không phải bản sao dữ liệu

Consumer group lưu committed offset để ghi nhớ vị trí tiếp theo cần đọc cho mỗi partition. Offset commit thường biểu thị **offset kế tiếp cần đọc**, không phải số thứ tự nghiệp vụ và cũng không phải bản sao của record.

Ví dụ consumer đã xử lý record offset 41 thành công và commit offset 42. Khi consumer khởi động lại, group có thể tiếp tục đọc từ offset 42 nếu offset đó vẫn hợp lệ và còn trong log.

### 5.2. `__consumer_offsets`

Kafka lưu thông tin offset và metadata consumer group trong internal topic `__consumer_offsets`. Topic nội bộ này được Kafka quản lý, phân partition và replication theo cấu hình cluster.

Một commit offset gắn với group ID, topic và partition. Vì vậy, hai group khác nhau có thể lưu hai tiến độ khác nhau cho cùng một topic-partition.

Không nên thao tác trực tiếp với `__consumer_offsets` như một topic nghiệp vụ. Hãy dùng consumer API hoặc công cụ quản trị Kafka để xem và điều chỉnh group offset.

### 5.3. Commit offset tự động và thủ công

Với `enable.auto.commit=true`, consumer có thể tự commit offset theo chu kỳ `auto.commit.interval.ms`. Cách này đơn giản nhưng ứng dụng cần hiểu thời điểm commit có thể không trùng chính xác với thời điểm side effect nghiệp vụ đã hoàn tất.

Với `enable.auto.commit=false`, ứng dụng chủ động commit:

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("group.id", "order-projection");
props.put("enable.auto.commit", "false");
```

Sau khi xử lý record thành công, ứng dụng có thể gọi `commitSync()` hoặc `commitAsync()` theo chiến lược phù hợp. Nếu xử lý batch hoặc xử lý song song, chỉ commit qua vị trí liên tục đã hoàn tất; commit vượt qua record còn dang dở có thể khiến record đó bị bỏ qua sau restart.

Commit offset không xóa record khỏi topic và không ảnh hưởng tiến độ của group khác.

## 6. Điều gì xảy ra khi đổi `group.id`?

### 6.1. Group ID mới tạo một tiến độ độc lập

Giả sử ứng dụng đang dùng:

```properties
group.id=order-projection
```

Sau đó đổi thành:

```properties
group.id=order-projection-v2
```

Kafka xem đây là group khác. Group mới không tự động kế thừa committed offset của `order-projection`. Nếu chưa có committed offset hợp lệ, consumer áp dụng `auto.offset.reset` để chọn vị trí bắt đầu.

Điều này có thể hữu ích khi:

- Muốn chạy một pipeline mới từ đầu để dựng lại projection.
- Muốn kiểm tra một consumer mới mà không ảnh hưởng tiến độ group hiện tại.
- Muốn tách một ứng dụng thành một luồng xử lý độc lập.

Nhưng đổi group ID ngoài ý muốn có thể làm consumer đọc lại toàn bộ dữ liệu hoặc bắt đầu ở cuối log, tùy `auto.offset.reset`.

### 6.2. Giữ group ID khi restart cùng ứng dụng

Nếu ứng dụng được khởi động lại và vẫn dùng cùng `group.id`, nó có thể tiếp tục từ committed offset đã lưu, miễn là offset còn hợp lệ và dữ liệu tương ứng vẫn tồn tại trong retention.

Nếu mỗi lần deploy lại sinh một `group.id` ngẫu nhiên, Kafka sẽ thấy các group mới. Các group cũ có thể còn metadata/offset đến khi hết thời gian retention của group; số group không cần thiết có thể tăng và làm việc quản trị khó hơn.

Quy tắc thực hành: cùng một subscription logic cần tiếp tục tiến độ thì giữ group ID ổn định; một subscription logic độc lập cần tiến độ riêng thì dùng group ID khác.

### 6.3. Không dùng group ID của môi trường khác

Nếu staging và production vô tình dùng cùng `group.id` và cùng Kafka cluster, consumer ở hai môi trường có thể tham gia cùng group và chia partition cho nhau. Điều này khiến một môi trường nhận thiếu dữ liệu và có thể tạo rebalance ngoài dự kiến.

Nên đưa môi trường vào tên group, ví dụ:

```text
dev.order-projection
staging.order-projection
prod.order-projection
```

Nếu mỗi môi trường dùng cluster riêng, việc thêm environment vào tên vẫn giúp log, metric và ACL dễ đọc hơn.

## 7. `auto.offset.reset` khi group chưa có offset hợp lệ

Khi group mới chưa có committed offset cho partition, hoặc committed offset không còn hợp lệ vì nằm ngoài log hiện tại, consumer cần chính sách xác định vị trí bắt đầu. `auto.offset.reset` điều khiển trường hợp này.

| Giá trị | Hành vi |
|---|---|
| `earliest` | Đọc từ offset sớm nhất còn tồn tại trong log |
| `latest` | Bắt đầu từ cuối log hiện tại, bỏ qua record cũ hơn vị trí bắt đầu |
| `none` | Ném lỗi nếu không có offset hợp lệ thay vì tự chọn vị trí |

Ví dụ:

```java
props.put("auto.offset.reset", "earliest");
```

`auto.offset.reset` không được áp dụng mỗi lần consumer restart nếu group đã có committed offset hợp lệ. Nó chỉ được dùng khi không có offset hợp lệ để tiếp tục.

Chọn chính sách theo mục đích:

- Consumer dựng lại trạng thái hoặc cần xử lý lịch sử còn giữ: cân nhắc `earliest`.
- Consumer chỉ quan tâm event mới kể từ lúc bắt đầu và chấp nhận bỏ dữ liệu cũ: cân nhắc `latest`.
- Hệ thống cần operator quyết định rõ ràng khi thiếu offset: dùng `none` và xử lý lỗi có chủ đích.

Không chọn `latest` chỉ để tránh lỗi offset nếu nghiệp vụ không chấp nhận bỏ qua record đã có trong topic.

## 8. Mô hình sử dụng consumer group trong hệ thống thực tế

### 8.1. Một ứng dụng, nhiều instance, một group

Ví dụ service `inventory-projection` chạy bốn instance để xử lý event kho. Cả bốn instance dùng cùng `group.id=inventory-projection`. Kafka chia partition cho bốn instance; khi một instance dừng, group rebalance và các member còn lại có thể nhận partition của instance đó.

Mô hình này phù hợp khi các instance là bản sao của cùng một logic xử lý và chia tải cho nhau.

### 8.2. Nhiều ứng dụng, nhiều group

Ví dụ topic `payments` được dùng bởi:

| Ứng dụng | Group ID | Mục đích |
|---|---|---|
| Payment projection | `payment-projection` | Cập nhật trạng thái thanh toán |
| Fraud detection | `fraud-detection` | Phân tích giao dịch đáng ngờ |
| Notification | `payment-notification` | Gửi thông báo cho khách hàng |
| Data warehouse | `payment-warehouse` | Đưa dữ liệu sang hệ thống phân tích |

Mỗi ứng dụng có thể scale số consumer riêng mà không thay đổi offset của group khác. Một ứng dụng lag không làm ứng dụng khác bị chậm do chia partition; tuy nhiên, các ứng dụng vẫn dùng chung tài nguyên broker, network, disk và retention của topic.

### 8.3. Một ứng dụng có thể có nhiều group

Một service cũng có thể chạy hai luồng xử lý độc lập trên cùng topic, ví dụ một luồng dựng projection hiện tại và một luồng kiểm tra dữ liệu. Khi hai luồng cần tiến độ riêng, chúng dùng hai consumer group khác nhau.

Nếu hai consumer chỉ là các instance thay thế nhau để chia tải cho cùng một logic, chúng nên dùng chung một group. Không tạo group mới cho mỗi thread nếu mục tiêu là tăng throughput của một pipeline duy nhất.

## 9. Đặt tên và quản lý group ID

### 9.1. Quy ước tên

Group ID nên giúp nhận diện môi trường, service và mục đích xử lý. Ví dụ:

```text
<environment>.<service>.<purpose>

prod.order-service.projection
prod.order-service.notification
prod.payment-service.fraud-detection
staging.order-service.projection
```

Quy ước có thể khác giữa tổ chức, nhưng cần:

- Ổn định qua các lần restart và deploy của cùng pipeline.
- Phân biệt các ứng dụng cần đọc độc lập.
- Phân biệt các môi trường nếu chúng cùng cluster.
- Tránh tên ngẫu nhiên hoặc tên gắn với một pod/instance khi muốn các instance chia tải.
- Có owner và mục đích rõ ràng để quản lý ACL, metric và vòng đời group.

### 9.2. Group ID và quyền truy cập

Kafka authorization có thể kiểm soát quyền trên topic và consumer group. Một principal đọc topic thường cần quyền phù hợp trên topic và quyền sử dụng group tương ứng. Khi đổi `group.id`, ứng dụng có thể cần ACL cho group mới.

Không nên cấp quyền group rộng hơn mức cần thiết. Nếu một ứng dụng dùng group ID khác mà bị lỗi authorization, hãy kiểm tra ACL của group cùng ACL topic thay vì đổi sang group ID của ứng dụng khác.

### 9.3. Group cũ và offset không còn dùng

Khi pipeline ngừng hoạt động hoặc đổi group ID, metadata group cũ có thể vẫn tồn tại một thời gian. Kafka có chính sách retention cho committed offset của group không hoạt động; thời gian cụ thể phụ thuộc cấu hình broker và phiên bản.

Trước khi xóa hoặc reset offset của group, xác nhận:

- Không còn consumer instance đang sử dụng group.
- Không có quy trình replay hoặc khôi phục đang phụ thuộc offset hiện tại.
- Owner của ứng dụng đã đồng ý thay đổi tiến độ.
- Đã ghi nhận offset hiện tại nếu cần khả năng rollback hoặc điều tra.

## 10. Quan sát và quản trị consumer group

### 10.1. Liệt kê group

Dùng Kafka CLI để xem các group trong cluster:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

### 10.2. Xem trạng thái và lag của một group

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Kết quả thường có topic, partition, current offset, log end offset, lag và member/host/client tùy phiên bản, trạng thái group và cách gọi lệnh.

### 10.3. So sánh hai group trên cùng topic

Chạy `--describe` cho từng group để so sánh tiến độ. Nếu `order-projection` lag 0 nhưng `order-analytics` lag 50.000, hai group vẫn hoạt động độc lập; cần điều tra năng lực xử lý của analytics thay vì thay offset của order projection.

Consumer lag là tín hiệu về khoảng cách giữa tiến độ group và log end offset, không tự nó cho biết nguyên nhân. Cần xem thêm tốc độ produce, tốc độ xử lý, rebalance, lỗi deserializer, thời gian xử lý nghiệp vụ và retention còn lại.

### 10.4. Reset offset có phạm vi group

Kafka CLI hỗ trợ reset offset cho một group, nhưng thao tác này ảnh hưởng tiến độ của group được chỉ định. Không nhầm reset offset của một group với việc xóa record khỏi topic.

Ví dụ xem kế hoạch reset về đầu log (cần dừng consumer group theo yêu cầu của công cụ/phiên bản trước khi thực hiện):

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-analytics \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Chỉ bỏ `--dry-run` sau khi đã kiểm tra topic/partition và xác nhận tác động. Reset group `order-analytics` không đổi committed offset của `order-projection`, nhưng có thể làm analytics đọc lại nhiều record và lặp side effect nếu ứng dụng không idempotent.

## 11. Các lỗi thường gặp

| Lỗi/anti-pattern | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mỗi instance tạo một `group.id` khác nhau dù cùng xử lý một pipeline | Các instance trở thành group độc lập và đọc trùng toàn bộ luồng | Dùng một group ID ổn định chung cho các instance cùng logic |
| Hai ứng dụng độc lập dùng chung group ID | Kafka chia partition giữa hai ứng dụng | Đặt group ID riêng cho từng subscription logic |
| Mỗi lần deploy sinh group ID mới | Group không tìm thấy offset cũ và áp dụng reset policy | Giữ group ID ổn định qua deploy |
| Staging và production dùng chung group ID trên cùng cluster | Hai môi trường gia nhập cùng group và chia partition | Đưa môi trường vào group ID hoặc dùng cluster tách biệt |
| Tăng consumer vượt số partition nhưng throughput không tăng | Không còn partition để giao thêm | Đo bottleneck và xem xét partition topology |
| Nghĩ group độc lập có bản sao dữ liệu riêng | Các group dùng chung log topic | Thiết kế retention đủ cho group chậm nhất |
| Dùng `latest` cho group mới trong khi cần lịch sử | Consumer bắt đầu ở cuối log và bỏ qua record cũ | Chọn `earliest` nếu cần replay dữ liệu còn giữ |
| Reset offset nhầm group | Tiến độ của ứng dụng khác bị thay đổi | Xác minh group ID và dùng `--dry-run` trước |
| Không theo dõi lag từng group | Một group có thể chậm đến khi dữ liệu hết retention | Giám sát lag, tốc độ xử lý và thời gian retention còn lại |

## 12. Checklist thiết kế consumer group

Trước khi triển khai consumer, hãy trả lời:

- Các instance có phải bản sao của cùng một pipeline không? Nếu có, chúng có dùng cùng `group.id` không?
- Các ứng dụng có cần nhận toàn bộ event độc lập không? Nếu có, mỗi ứng dụng đã có group ID riêng chưa?
- Group ID có ổn định qua restart/deploy không?
- Tên group có phân biệt môi trường và mục đích xử lý không?
- Số partition có đủ cho mức song song mong muốn trong từng group không?
- `auto.offset.reset` có phù hợp khi group mới hoặc offset không còn hợp lệ không?
- Commit offset diễn ra sau khi xử lý thành công theo yêu cầu nghiệp vụ chưa?
- Retention của topic có đủ cho group lag nhiều nhất và nhu cầu replay không?
- ACL cho phép principal đọc topic và sử dụng đúng group không?
- Dashboard có theo dõi lag, member, assignment và rebalance theo từng group không?
- Quy trình reset offset có xác nhận group, topic, partition và kế hoạch trước khi thực thi không?

## 13. Câu hỏi tự kiểm tra

1. `group.id` định danh điều gì trong Kafka consumer?
2. Vì sao các instance cùng một ứng dụng cần dùng chung group ID khi muốn chia tải?
3. Nếu hai consumer cùng group đọc một topic có bốn partition, Kafka phân công partition như thế nào?
4. Vì sao thêm consumer vượt số partition không làm mức song song tăng vô hạn?
5. Hai group khác nhau cùng đọc topic `orders` có chia partition với nhau không?
6. Committed offset được xác định theo những thành phần nào?
7. Vì sao đổi `group.id` khiến consumer có thể đọc lại dữ liệu hoặc bắt đầu từ cuối log?
8. `auto.offset.reset=earliest` và `latest` khác nhau như thế nào khi group chưa có offset hợp lệ?
9. Vì sao group độc lập vẫn chịu ảnh hưởng retention chung của topic?
10. Điều gì có thể xảy ra nếu staging và production vô tình dùng cùng group ID trên một cluster?
11. Reset offset của group analytics có làm thay đổi offset của group projection không?
12. Nên dùng chung group ID hay group ID riêng khi triển khai thêm instance của cùng một pipeline?

## Kết luận

`group.id` xác định một consumer group và tiến độ đọc riêng của nhóm đó. Các consumer cùng group chia partition để scale out; các group khác nhau có thể đọc cùng topic độc lập, mỗi group có assignment và committed offset riêng. Giữ group ID ổn định giúp một pipeline tiếp tục từ tiến độ cũ sau restart, còn tạo group ID mới mở ra một luồng tiêu thụ độc lập và cần chọn chính sách offset ban đầu. Thiết kế group ID rõ ràng giúp nhiều ứng dụng cùng khai thác một event stream mà không vô tình chia tải hoặc làm ảnh hưởng tiến độ của nhau.
