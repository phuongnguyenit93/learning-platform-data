# Một record đến bao nhiêu consumer group?

## 1. Một record có thể được nhiều consumer group đọc

Trong Kafka, một record được ghi vào một partition của topic. Nhiều consumer group có thể đăng ký đọc cùng topic và mỗi group duy trì tiến độ đọc riêng. Vì vậy, một record có thể được đọc độc lập bởi nhiều group khác nhau.

Ví dụ, khi Order Service phát record `OrderCreated` lên topic `orders`, ba hệ thống có thể cùng quan tâm:

- Inventory Service giữ hàng.
- Notification Service gửi email hoặc thông báo.
- Analytics Service cập nhật báo cáo.

Mỗi hệ thống dùng một `group.id` riêng. Cả ba group đều có thể đọc record `OrderCreated`, mỗi group xử lý theo tiến độ của mình.

```text
                         Topic: orders
                    Partition 0, 1, 2, ...
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
      Group inventory   Group notification   Group analytics
             |                |                |
        giữ hàng          gửi thông báo      cập nhật báo cáo
```

Không có một con số cố định như một record chỉ được đọc bởi một hoặc hai group. Về mặt mô hình, nhiều group độc lập có thể đọc cùng một record. Giới hạn thực tế đến từ tài nguyên broker, số consumer, thông lượng đọc, retention và năng lực xử lý của các hệ thống nhận.

Điều kiện quan trọng là group phải đăng ký topic và có vị trí đọc cho phép tiếp cận record đó trong thời gian record còn được lưu. Một group mới bắt đầu đọc từ `latest` có thể bỏ qua các record đã tồn tại trước lúc group bắt đầu; record đã bị retention xóa thì không thể đọc lại từ topic.

## 2. Consumer group khác nhau: fan-out theo từng group

Kafka lưu record trong partition log. Consumer chủ động poll dữ liệu từ broker; Kafka không tạo một bản sao vật lý riêng của record cho từng group khi record được publish.

Mỗi group có committed offset riêng cho từng partition. Do đó, cùng một record có thể được group A đọc hôm nay, group B đọc sau đó, còn group C đọc lại nhiều lần trong quá trình replay. Các group không cần xử lý cùng tốc độ và không cần commit cùng thời điểm.

Ví dụ một record `OrderCreated` có offset `120` trong `orders-1`:

| Consumer group | Tiến độ trước khi đọc | Hành vi với record offset 120 |
|---|---:|---|
| `inventory-service` | 120 | Đọc và xử lý record |
| `notification-service` | 115 | Đọc các record tiếp theo, trong đó có offset 120 |
| `analytics-service` | 121 | Đã đi qua record này, không đọc lại trong luồng bình thường |

Nếu `analytics-service` đã commit offset `121`, group đó không tự quay lại offset `120` chỉ vì group khác đang đọc record này. Muốn đọc lại, cần chủ động reset offset hoặc tạo group mới với chính sách bắt đầu phù hợp.

Đây là cơ chế fan-out ở mức consumer group: mỗi group là một subscriber logic độc lập. Kafka chỉ lưu log theo topic/partition; trạng thái tiến độ của từng group được quản lý riêng.

## 3. Consumer trong cùng group: chia nhau partition

Một điểm rất dễ nhầm là nhiều consumer group có thể cùng đọc một record, nhưng nhiều consumer thuộc **cùng một group** không phải mỗi consumer đều nhận một bản của record đó.

Trong một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer member. Consumer trong group chia nhau các partition để tăng khả năng xử lý song song.

Giả sử topic `orders` có 3 partition và group `inventory-service` có 3 consumer:

```text
Topic orders
  Partition 0 ─────▶ inventory consumer A
  Partition 1 ─────▶ inventory consumer B
  Partition 2 ─────▶ inventory consumer C
```

Một record ở partition 1 được consumer B xử lý trong group này. Consumer A và C không nhận cùng record đó trong cùng group. Khi group khác cũng đăng ký topic `orders`, group đó có assignment riêng và có thể đọc lại record ở partition 1.

### So sánh hai trường hợp

| Cấu hình | Hành vi |
|---|---|
| Nhiều consumer cùng `group.id` | Chia partition và tải xử lý; một partition được tối đa một member trong group sở hữu tại một thời điểm |
| Nhiều consumer group có `group.id` khác nhau | Mỗi group đọc độc lập cùng topic và có thể đọc cùng một record |

Vì vậy, muốn nhiều dịch vụ đều nhận sự kiện, hãy dùng group ID khác nhau. Muốn nhiều instance của cùng một dịch vụ chia nhau công việc, hãy dùng chung group ID.

## 4. Ví dụ ba group cùng đọc một topic

Giả sử topic `orders` có 4 partition. Có ba nhóm nghiệp vụ:

| Group ID | Số consumer | Mục đích |
|---|---:|---|
| `inventory-service` | 2 | Giữ hàng và cập nhật tồn kho |
| `notification-service` | 1 | Gửi email và thông báo |
| `analytics-service` | 4 | Xây dựng số liệu phân tích |

Mỗi group có assignment riêng:

```text
                         Topic orders
                    P0    P1    P2    P3
                     |     |     |     |
       +-------------+-----+-----+-----+-------------+
       |                   |                   |
       v                   v                   v
 inventory-service  notification-service  analytics-service
   Consumer A/B       Consumer N             Consumer X/Y/Z/W
   chia 4 partition   đọc cả 4 partition     chia 4 partition
```

Nếu record `OrderCreated` nằm ở partition 2:

- `inventory-service` có một consumer được gán partition 2 đọc record.
- `notification-service` có consumer duy nhất đọc record đó.
- `analytics-service` có consumer được gán partition 2 đọc record đó.

Như vậy, record có thể được xử lý ba lần ở cấp hệ thống, một lần bởi mỗi group trong luồng xử lý bình thường. Mỗi group có thể xử lý thành công, retry hoặc bị chậm độc lập với hai group còn lại.

Với 4 partition, `analytics-service` có thể dùng tối đa 4 consumer tích cực cho topic này trong group. Nếu tăng lên 6 consumer, hai consumer có thể không được gán partition. Việc tăng số consumer trong một group không tạo thêm bản sao record cho từng consumer.

## 5. Group ID quyết định danh tính subscriber logic

`group.id` là định danh của consumer group. Kafka dùng nó để quản lý membership, assignment và committed offset. Các instance cùng một dịch vụ thường dùng chung group ID ổn định để chia nhau tải và tiếp tục từ tiến độ đã lưu.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-service
      auto-offset-reset: earliest
```

Khi nhiều instance của Inventory Service cùng chạy với `group.id=inventory-service`, chúng tham gia cùng một group. Nếu Notification Service cũng dùng nhầm group ID này, hai dịch vụ sẽ chia partition và record; chúng không còn nhận độc lập tất cả sự kiện.

Ngược lại, nếu mỗi lần khởi động tạo một group ID ngẫu nhiên, mỗi lần chạy có thể được xem là subscriber mới. Với `auto.offset.reset=earliest`, group mới có thể đọc lại toàn bộ dữ liệu còn lưu; với `latest`, group có thể chỉ nhận record được ghi sau khi nó bắt đầu. Đây thường là hành vi ngoài ý muốn của consumer nghiệp vụ cần duy trì tiến độ.

Quy tắc thực tế:

- Cùng một dịch vụ cần scale ngang: dùng chung group ID ổn định.
- Hai dịch vụ cần nhận độc lập cùng sự kiện: dùng group ID khác nhau.
- Job replay hoặc phân tích một lần: có thể dùng group ID riêng, nhưng phải chọn offset bắt đầu và retention có chủ đích.

## 6. Offset độc lập giữa các group

Kafka lưu tiến độ đọc theo consumer group và partition. Vì mỗi group có committed offset riêng, group này không làm thay đổi tiến độ của group khác.

Ví dụ cùng topic `orders`, partition 0:

| Group ID | Committed offset | Diễn giải |
|---|---:|---|
| `inventory-service` | 250 | Group tiếp tục từ offset 250 |
| `notification-service` | 210 | Group còn đọc chậm hơn |
| `analytics-service` | 300 | Group đã đọc xa hơn hai group còn lại |

Nếu `notification-service` bị dừng một giờ, hai group còn lại vẫn tiếp tục đọc và commit offset của chúng. Khi Notification Service chạy lại, nó tiếp tục từ committed offset của chính group `notification-service`, miễn là dữ liệu cần đọc vẫn còn trong retention.

Điều này giúp các hệ thống downstream độc lập về thời gian hoạt động và tốc độ xử lý. Một consumer group bị lag không bắt buộc các group khác phải dừng theo.

## 7. auto.offset.reset và việc group mới có đọc được record cũ không?

Một group chỉ đọc được record nếu offset bắt đầu của nó nằm trước hoặc tại record đó và record vẫn còn trong log. Khi group chưa có committed offset hợp lệ, Kafka dùng `auto.offset.reset` để chọn điểm bắt đầu.

| Cấu hình | Hành vi với group chưa có offset hợp lệ |
|---|---|
| `earliest` | Bắt đầu từ beginning offset còn tồn tại của partition |
| `latest` | Bắt đầu từ end offset hiện tại; thường chỉ nhận record được ghi sau khi group tham gia |
| `none` | Ném lỗi nếu không có committed offset hợp lệ |

Ví dụ topic đã có các record từ offset `0` đến `99` trước khi `reporting-service` chạy:

- Nếu group mới dùng `earliest`, group có thể đọc từ offset cũ nhất còn được lưu.
- Nếu group mới dùng `latest`, group bắt đầu ở cuối log và không đọc lại các record trước điểm bắt đầu.
- Nếu record offset `20` đã bị retention xóa, không cấu hình nào có thể làm record đó xuất hiện trở lại từ topic hiện tại.

`auto.offset.reset` chỉ được dùng khi group không có committed offset hợp lệ hoặc offset không còn hợp lệ. Nó không ghi đè committed offset đang tồn tại. Để replay một group đã có tiến độ, cần thực hiện reset offset có chủ đích hoặc dùng group ID mới.

## 8. Một group có thể nhận record nhiều lần không?

Có. Cần phân biệt **một lần đọc logic của group** với số lần record thực sự được giao cho ứng dụng. Kafka consumer thường được triển khai theo at-least-once: nếu ứng dụng xử lý record thành công nhưng dừng trước khi commit offset, record có thể được giao lại sau restart hoặc rebalance.

Ví dụ:

1. `inventory-service` đọc record offset `250`.
2. Service cập nhật database thành công.
3. Process dừng trước khi committed offset `251` được lưu.
4. Consumer mới nhận partition và tiếp tục từ committed offset cũ.
5. Record offset `250` được giao lại.

Vì thế, không nên khẳng định mỗi group chỉ nhận một lần tuyệt đối. Cần thiết kế consumer idempotent, chẳng hạn lưu `eventId` đã xử lý với ràng buộc duy nhất hoặc dùng khóa nghiệp vụ để thao tác lặp không tạo thêm tác dụng phụ.

Producer idempotence và consumer idempotency giải quyết các vấn đề khác nhau. Idempotent producer bảo vệ retry nội bộ của producer theo phạm vi Kafka; nó không tự ngăn consumer xử lý lại record sau restart, và cũng không tự khử trùng lặp các lần gửi mới do ứng dụng chủ động gọi.

## 9. Một group đọc nhiều topic như thế nào?

Một consumer group có thể subscribe nhiều topic. Group đó duy trì offset độc lập cho từng partition của tất cả topic đã đăng ký. Mỗi group khác cũng có thể subscribe cùng tập topic hoặc chỉ một phần trong đó.

Ví dụ Notification Service cần nhận cả sự kiện tạo đơn và thanh toán:

```java
@Component
public class NotificationListener {

    @KafkaListener(
            topics = {"orders", "payments"},
            groupId = "notification-service")
    public void onEvent(String payload) {
        // Phân loại và xử lý sự kiện.
    }
}
```

Group `notification-service` có assignment cho các partition của cả hai topic. Nếu Analytics Service cũng subscribe `orders` và `payments` với `groupId=analytics-service`, group Analytics có thể đọc độc lập các record từ hai topic đó.

Nếu cần định tuyến từng loại sự kiện đến các phương thức xử lý riêng, có thể khai báo nhiều `@KafkaListener` hoặc dùng `@KafkaHandler` với cấu hình phù hợp. Điều quan trọng là group ID xác định tiến độ và cơ chế chia partition; nó không tự phân loại payload theo nghiệp vụ.

## 10. Triển khai nhiều group bằng Spring Kafka

Trong Spring Kafka, thuộc tính `groupId` của `@KafkaListener` xác định consumer group cho endpoint. Có thể khai báo hai listener cùng topic nhưng khác group ID:

```java
@Component
public class OrderEventListeners {

    @KafkaListener(
            topics = "orders",
            groupId = "inventory-service")
    public void updateInventory(OrderCreated event) {
        // Inventory xử lý độc lập.
    }

    @KafkaListener(
            topics = "orders",
            groupId = "analytics-service")
    public void updateAnalytics(OrderCreated event) {
        // Analytics cũng nhận record của topic.
    }
}
```

Hai listener tạo hai group độc lập và mỗi group có tiến độ riêng. Cần cấu hình deserializer/converter tương thích với kiểu `OrderCreated`.

Nếu dùng `spring.kafka.consumer.group-id` làm giá trị mặc định, `groupId` khai báo trực tiếp trên `@KafkaListener` có thể ghi đè group ID mặc định cho endpoint đó. Nên đặt tên group theo dịch vụ hoặc mục đích xử lý để tránh hai luồng nghiệp vụ vô tình dùng chung group.

### Scale ngang trong một group

Để chạy nhiều consumer trong cùng một group, có thể tăng số instance ứng dụng hoặc đặt concurrency cho listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        concurrency = "3")
public void updateInventory(OrderCreated event) {
    // Xử lý một record được gán cho consumer này.
}
```

`concurrency=3` yêu cầu container tạo ba consumer cho endpoint trong group đó. Số consumer thực sự được gán partition không thể vượt số partition được group nhận từ topic subscription. Nếu topic chỉ có hai partition, tối đa hai consumer có partition hoạt động tại một thời điểm; consumer còn lại không nhận partition.

## 11. Nhiều group có làm Kafka lưu nhiều bản sao dữ liệu không?

Không theo cách mỗi group có một bản sao vật lý riêng. Record được lưu một lần trong partition log, với số replica do replication factor quyết định. Các group đọc cùng log và lưu tiến độ riêng trong cơ chế quản lý offset của Kafka (topic nội bộ `__consumer_offsets`).

Tuy vậy, thêm group vẫn làm tăng tải đọc:

- Mỗi group có consumer riêng và tạo các yêu cầu fetch.
- Broker phải phục vụ thêm lưu lượng đọc, mạng và metadata.
- Các ứng dụng downstream dùng CPU, bộ nhớ, kết nối và tài nguyên database riêng.
- Nếu nhiều group đọc chậm, chúng có thể giữ tiến độ cũ trong khi retention tiếp tục áp dụng theo cấu hình topic.

Do đó, nhiều group không nhân số bản sao dữ liệu trên đĩa theo số group, nhưng có thể làm tăng đáng kể chi phí phục vụ consumer. Cần theo dõi consumer lag, fetch rate, broker network, request latency và tải của hệ thống nhận.

## 12. Xem tiến độ từng group bằng Kafka CLI

Lệnh sau hiển thị offset và lag của một consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group inventory-service
```

Chạy tương tự với `notification-service` và `analytics-service` để thấy mỗi group có tiến độ độc lập. Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `GROUP` | Consumer group đang được truy vấn |
| `TOPIC` / `PARTITION` | Partition mà group có tiến độ |
| `CURRENT-OFFSET` | Committed offset của group |
| `LOG-END-OFFSET` | End offset dùng để so sánh tiến độ |
| `LAG` | Khoảng cách offset giữa end và committed offset |

Ví dụ cùng một partition có thể hiển thị:

```text
GROUP                 TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
inventory-service     orders  0          250              300             50
notification-service orders  0          210              300             90
analytics-service    orders  0          300              300             0
```

Analytics đã commit đến cuối log tại thời điểm quan sát, trong khi Inventory và Notification còn lag khác nhau. Điều này không ảnh hưởng đến offset của group còn lại.

Nếu group chưa có committed offset, một số cột có thể hiển thị `-`. Điều đó không đồng nghĩa topic không có record; group có thể chưa bắt đầu đọc hoặc chưa commit offset.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhiều dịch vụ dùng chung một `group.id` dù cần nhận độc lập | Các dịch vụ chia partition; mỗi record không đến tất cả dịch vụ | Dùng group ID riêng cho từng subscriber logic |
| Mỗi instance của cùng dịch vụ dùng group ID khác nhau | Mỗi instance đọc độc lập toàn bộ luồng, gây xử lý lặp ở cấp hệ thống | Dùng chung group ID ổn định cho các replica cùng dịch vụ |
| Tạo group ID ngẫu nhiên sau mỗi lần restart | Group mới không kế thừa offset cũ; có thể replay hoặc bỏ qua dữ liệu tùy reset policy | Dùng group ID ổn định cho consumer dài hạn |
| Nghĩ rằng nhiều consumer trong cùng group đều nhận cùng record | Thiết kế fan-out sai và bỏ sót xử lý | Phân biệt work-sharing trong group với fan-out giữa các group |
| Nghĩ mỗi group có bản sao topic riêng | Hiểu sai dung lượng lưu trữ và retention | Nhớ rằng các group đọc cùng partition log, offset được lưu riêng |
| Cho rằng một group chỉ nhận record đúng một lần | Side effect có thể bị lặp khi restart/rebalance | Thiết kế consumer idempotent và commit sau xử lý |
| Đặt `latest` cho group mới nhưng mong đọc lịch sử | Group bỏ qua record trước điểm bắt đầu | Dùng `earliest` nếu cần đọc lại dữ liệu còn retention hoặc reset offset có kiểm soát |

## 14. Kịch bản kiểm thử fan-out và work-sharing

Có thể kiểm chứng hành vi bằng một topic thử nghiệm và ba group độc lập:

1. Tạo topic `orders` có ít nhất hai partition.
2. Khởi chạy hai consumer trong group `inventory-service`.
3. Khởi chạy một consumer trong group `notification-service`.
4. Khởi chạy một consumer trong group `analytics-service`.
5. Gửi một record có key cố định để xác định partition.
6. Xác nhận một member của mỗi group đọc được record; hai consumer thuộc cùng group Inventory không cùng nhận một bản của record đó.
7. Tắt Notification Service, tiếp tục gửi record và xác nhận hai group còn lại vẫn đọc được.
8. Khởi động lại Notification Service với cùng group ID và kiểm tra nó tiếp tục từ committed offset của chính group.
9. Thử group mới với `earliest` và `latest` để quan sát khác biệt khi đọc record lịch sử.
10. Cho listener xử lý thành công nhưng dừng trước commit để xác nhận record có thể được giao lại trong cùng group.

Khi kiểm thử, không chỉ dựa vào log console. Hãy ghi `eventId`, `groupId`, topic, partition và offset vào kết quả test để xác định record được group nào xử lý và có bị giao lại hay không.

## 15. Tổng kết

- Một record có thể được đọc độc lập bởi nhiều consumer group khác nhau đăng ký cùng topic.
- Mỗi group có committed offset riêng; group này bị chậm hoặc dừng không làm group khác mất tiến độ.
- Consumer trong cùng group chia partition; một partition chỉ được gán cho tối đa một member của group tại một thời điểm.
- Muốn nhiều dịch vụ cùng nhận sự kiện, dùng group ID khác nhau; muốn scale ngang một dịch vụ, các instance dùng chung group ID.
- Group mới chỉ đọc được dữ liệu lịch sử nếu offset bắt đầu cho phép và record vẫn còn trong retention.
- Kafka không tạo một bản sao vật lý của topic cho từng group; nhiều group vẫn làm tăng tải đọc và tài nguyên downstream.
- At-least-once có thể khiến một record được giao lại trong cùng group; consumer cần idempotent.

Khi phân biệt đúng fan-out giữa các consumer group và work-sharing bên trong một group, có thể thiết kế nhiều dịch vụ cùng phản ứng với một sự kiện mà vẫn mở rộng từng dịch vụ độc lập bằng Spring Kafka.
