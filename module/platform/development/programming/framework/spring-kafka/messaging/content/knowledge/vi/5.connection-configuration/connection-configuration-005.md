# group.id và tên consumer group

## 1. group.id là gì?

Trong Kafka, `group.id` là định danh của một consumer group. Các consumer có cùng `group.id` tham gia cùng một nhóm, phối hợp đọc topic và chia nhau các partition được gán. Kafka dùng định danh này để quản lý thành viên group, phân phối partition và lưu tiến độ đọc.

Trong ứng dụng Spring Kafka, `group.id` thường được khai báo qua cấu hình consumer của Spring Boot hoặc đặt riêng trên từng `@KafkaListener`. Đây là một trong những cấu hình quan trọng nhất khi triển khai consumer vì nó quyết định consumer thuộc subscription nào và sẽ tiếp tục đọc từ tiến độ nào.

Ví dụ, ba instance của dịch vụ xử lý đơn hàng cùng dùng `group.id=orders-processor-prod`. Kafka xem chúng là ba thành viên của một group và phân chia partition giữa chúng. Nếu dịch vụ kiểm tra gian lận cũng cần nhận tất cả sự kiện đơn hàng, dịch vụ đó cần một group ID riêng, chẳng hạn `fraud-monitor-prod`.

## 2. group.id liên hệ với topic, partition và offset như thế nào?

Một topic có thể được nhiều consumer group đăng ký đọc. Trong từng group, mỗi partition được gán cho tối đa một consumer tại một thời điểm. Vì vậy, các consumer trong cùng group chia việc; những group khác nhau có thể đọc độc lập cùng một luồng sự kiện.

~~~mermaid
flowchart TB
    T["Topic orders<br/>P0 · P1 · P2 · P3"]
    T --> G1["Group: orders-processor"]
    T --> G2["Group: fraud-monitor"]
    G1 --> A["Consumer A<br/>P0, P1"]
    G1 --> B["Consumer B<br/>P2, P3"]
    G2 --> C["Consumer C<br/>P0, P1"]
    G2 --> D["Consumer D<br/>P2, P3"]
~~~

Trong sơ đồ:

- `orders-processor` có hai consumer cùng chia bốn partition. Mỗi record thuộc một partition được một thành viên của group nhận.
- `fraud-monitor` có tiến độ đọc riêng và cũng có thể đọc toàn bộ sự kiện trong topic `orders`.
- Cùng một record có thể được cả hai group đọc, nhưng mỗi group quản lý offset riêng.

Kafka lưu offset đã commit theo tổ hợp group ID, topic và partition. Do đó, group `orders-processor` có thể đã đọc đến offset 120 của partition P0, trong khi `fraud-monitor` mới ở offset 75 của cùng partition. Một group đọc record không làm record biến mất khỏi topic và cũng không thay đổi offset của group khác.

Offset của consumer group được Kafka lưu trong topic nội bộ `__consumer_offsets`. Khi consumer khởi động lại hoặc partition được giao cho consumer khác, group có thể tiếp tục từ offset đã commit gần nhất.

Kafka chọn một broker làm group coordinator cho mỗi consumer group. Coordinator quản lý thành viên, heartbeat và quá trình phân phối partition. Khi consumer tham gia hoặc rời group, heartbeat hết hạn, subscription thay đổi hoặc số partition thay đổi, Kafka có thể thực hiện rebalance để tính lại assignment. Trong thời gian rebalance, việc tiêu thụ có thể tạm gián đoạn.

## 3. Khai báo group.id trong Spring Boot

Cách phổ biến là khai báo group ID mặc định trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-processor
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

Với cấu hình trên, các listener không chỉ định group ID riêng sẽ sử dụng group mặc định `orders-processor` từ cấu hình consumer.

Ví dụ một listener nhận sự kiện đơn hàng:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders")
    public void handle(OrderCreatedEvent event) {
        // Xử lý sự kiện tạo đơn hàng.
    }
}
~~~

Khi ứng dụng chạy nhiều instance, mỗi instance của cùng dịch vụ dùng chung cấu hình và group ID. Kafka đưa các consumer đó vào cùng một group để chia partition.

### Gán group ID riêng cho từng listener

Nếu một ứng dụng có nhiều listener phục vụ các nghiệp vụ khác nhau, có thể chỉ định `groupId` trực tiếp trên `@KafkaListener`:

~~~java
@Component
public class FraudDetectionListener {

    @KafkaListener(
        topics = "orders",
        groupId = "fraud-monitor"
    )
    public void inspect(OrderCreatedEvent event) {
        // Kiểm tra dấu hiệu gian lận.
    }
}
~~~

Thuộc tính `groupId` trên `@KafkaListener` ghi đè group ID mặc định trong cấu hình consumer cho listener đó. Ví dụ này cho phép `FraudDetectionListener` nhận luồng `orders` độc lập với listener dùng group `orders-processor`.

Có thể dùng placeholder để quản lý tên group trong cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-processor
~~~

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "${spring.kafka.consumer.group-id}"
)
public void handle(OrderCreatedEvent event) {
    // Xử lý sự kiện.
}
~~~

Dùng cấu hình tập trung giúp đổi tên group theo môi trường mà không phải sửa mã nguồn.

## 4. Đặt tên consumer group như thế nào?

Tên group nên mô tả dịch vụ hoặc nghiệp vụ tiêu thụ sự kiện. Một quy ước dễ quản lý là kết hợp tên chức năng, môi trường và phiên bản khi cần:

~~~text
<service>-<purpose>-<environment>[-v<version>]
~~~

Ví dụ:

| Group ID | Mục đích |
|---|---|
| `orders-processor-dev` | Xử lý đơn hàng ở môi trường phát triển |
| `orders-processor-prod` | Xử lý đơn hàng ở môi trường production |
| `fraud-monitor-prod` | Phân tích gian lận trong production |
| `billing-service-prod` | Xử lý sự kiện phục vụ thanh toán |
| `orders-processor-prod-v2` | Consumer mới có tiến độ đọc độc lập với phiên bản trước |

Một số nguyên tắc khi đặt tên:

- **Ổn định:** các lần triển khai của cùng một logical consumer thường dùng lại group ID để tiếp tục offset đã commit.
- **Phân biệt môi trường:** dev, test, staging và production nên có group ID riêng nếu kết nối cùng một Kafka cluster, tránh consumer thử nghiệm tham gia group production.
- **Phân biệt nghiệp vụ:** hai dịch vụ cần nhận toàn bộ cùng một sự kiện phải có group ID khác nhau.
- **Có chủ đích khi thêm phiên bản:** thêm hậu tố phiên bản sẽ tạo một group mới với tiến độ đọc riêng. Chỉ làm vậy khi thực sự muốn một subscription độc lập, chẳng hạn chạy song song consumer mới để kiểm tra hoặc replay dữ liệu.
- **Dùng cùng tên cho các replica:** các pod hoặc instance cùng triển khai một consumer logic phải dùng chung group ID để chia tải.

Không nên tạo group ID ngẫu nhiên hoặc gắn mã pod vào group ID cho từng lần khởi động nếu mục tiêu là scale ngang một dịch vụ. Khi mỗi pod dùng group ID khác nhau, Kafka xem mỗi pod là một subscriber độc lập; tất cả có thể đọc toàn bộ topic theo offset riêng, làm tăng số lần xử lý và tải hệ thống.

## 5. Điều gì xảy ra khi thay đổi group.id?

Group ID không chỉ là tên hiển thị. Nó là một phần của khóa định danh tiến độ tiêu thụ. Khi đổi group ID, Kafka xem consumer là một group mới nếu tên đó chưa có trạng thái tương ứng.

Giả sử `orders-processor-prod` đã commit offset đến 500 của partition P0. Nếu triển khai ứng dụng với group ID mới `orders-processor-prod-v2`, group mới chưa có offset đã commit. Khi đó, `auto.offset.reset` quyết định vị trí bắt đầu:

| Cấu hình | Hành vi khi group chưa có offset hợp lệ |
|---|---|
| `earliest` | Bắt đầu từ record cũ nhất còn được giữ trong partition |
| `latest` | Bắt đầu ở cuối log tại thời điểm khởi tạo vị trí đọc; thường chỉ nhận record được ghi sau đó |
| `none` | Phát sinh lỗi nếu không tìm thấy offset hợp lệ |

`auto.offset.reset` không ghi đè offset hợp lệ đã commit. Nếu group đã có offset, consumer tiếp tục từ tiến độ đó. Với `earliest`, Kafka cũng chỉ có thể đọc các record còn trong thời hạn lưu giữ; dữ liệu đã bị retention xóa không thể được khôi phục bằng cách đổi cấu hình.

Trước khi đổi group ID, cần xác định rõ mục tiêu:

- Nếu chỉ triển khai thêm replica để tăng thông lượng, giữ nguyên group ID.
- Nếu thay một phiên bản ứng dụng nhưng muốn tiếp tục tiến độ hiện tại, dùng lại group ID hiện tại và kiểm soát quá trình rollout.
- Nếu muốn consumer mới đọc độc lập hoặc replay dữ liệu, tạo group ID mới và chọn `auto.offset.reset` phù hợp.
- Nếu không còn dùng group cũ, cân nhắc chính sách quản lý offset và dữ liệu liên quan theo quy trình vận hành của Kafka cluster.

Đổi group ID có thể khiến nghiệp vụ xử lý lại nhiều sự kiện hoặc bỏ qua lịch sử, tùy offset và `auto.offset.reset`. Consumer vẫn nên hỗ trợ xử lý idempotent vì retry, rebalance và lỗi sau khi xử lý nhưng trước khi commit có thể dẫn đến nhận lại record.

## 6. Phân biệt group.id với client.id và listener id

Các định danh này có mục đích khác nhau:

| Thuộc tính | Mục đích | Phạm vi sử dụng |
|---|---|---|
| `group.id` | Xác định consumer group và tiến độ đọc chung | Các consumer phối hợp chia partition |
| `client.id` | Nhận diện một Kafka client để phục vụ log, metric và quan sát | Từng consumer/producer client |
| `@KafkaListener(id = "...")` | Định danh listener container trong Spring Kafka | Quản lý listener container trong ứng dụng |
| `group.instance.id` | Định danh ổn định một thành viên khi dùng static membership | Từng consumer instance trong một group |

Không dùng `client.id` thay cho `group.id`. Hai consumer có `client.id` khác nhau vẫn có thể thuộc cùng một group nếu dùng cùng `group.id`. Ngược lại, các consumer có `client.id` giống nhau nhưng group ID khác nhau vẫn thuộc các group khác nhau.

`@KafkaListener` có thuộc tính `id` để định danh container. Trong các cấu hình Spring Kafka phổ biến, nếu chỉ đặt `id` mà không đặt `groupId`, ID này có thể được dùng làm group ID theo mặc định `idIsGroup`. Để tránh nhầm lẫn giữa định danh container và định danh consumer group, nên khai báo rõ `groupId` khi cần kiểm soát subscription.

`group.instance.id` là tùy chọn nâng cao cho static membership. Mỗi consumer instance trong cùng group phải có một giá trị riêng và ổn định theo vòng đời instance. Không gán cùng một `group.instance.id` cho tất cả replica. Thuộc tính này không thay thế `group.id`; nó chỉ giúp Kafka nhận diện thành viên cụ thể và có thể giảm rebalance không cần thiết khi thành viên tạm thời mất kết nối trong giới hạn cấu hình.
## 7. Các lỗi cấu hình thường gặp

### Mỗi replica dùng một group ID khác nhau

**Hiện tượng:** mọi replica đều đọc gần như toàn bộ sự kiện, khiến số lần xử lý tăng theo số replica.

**Nguyên nhân:** group ID được tạo động, chứa pod ID hoặc mã ngẫu nhiên.

**Cách sửa:** cấu hình một group ID ổn định cho cùng một logical consumer. Để Kafka phân chia partition giữa các replica.

### Hai dịch vụ độc lập dùng chung group ID

**Hiện tượng:** dịch vụ A nhận một phần record, dịch vụ B nhận phần còn lại; mỗi dịch vụ không thấy toàn bộ sự kiện như mong đợi.

**Nguyên nhân:** hai dịch vụ cần xử lý độc lập nhưng lại dùng chung group ID nên Kafka xem chúng là thành viên cạnh tranh trong cùng một group.

**Cách sửa:** cấp group ID riêng cho từng nghiệp vụ cần nhận toàn bộ luồng sự kiện.

### Đổi group ID ngoài ý muốn

**Hiện tượng:** consumer đọc lại nhiều dữ liệu cũ hoặc bỏ qua lịch sử.

**Nguyên nhân:** tên group thay đổi, khiến Kafka không tìm thấy offset đã commit của group mới và áp dụng `auto.offset.reset`.

**Cách sửa:** giữ tên group ổn định giữa các lần triển khai; chỉ đổi khi có kế hoạch rõ ràng về tiến độ đọc mới.

### Tăng consumer nhưng số partition không đổi

**Hiện tượng:** một số consumer ở trạng thái không được gán partition và không xử lý record.

**Nguyên nhân:** số consumer trong group lớn hơn số partition có thể phân phối.

**Cách sửa:** đánh giá số partition và concurrency theo thông lượng mong muốn. Một partition chỉ được giao cho tối đa một consumer trong cùng group tại một thời điểm.

### Dùng nhầm group ID giữa các môi trường

**Hiện tượng:** consumer chạy thử tham gia cùng group với ứng dụng production hoặc làm thay đổi tiến độ đọc chung.

**Nguyên nhân:** các môi trường dùng chung cluster nhưng cấu hình group ID giống nhau.

**Cách sửa:** đưa tên môi trường vào group ID và kiểm tra cấu hình theo profile trước khi triển khai.

## 8. Theo dõi và kiểm tra consumer group

Khi vận hành, cần theo dõi group membership, partition assignment, offset đã commit và consumer lag. Consumer lag thể hiện khoảng cách giữa vị trí cuối log và tiến độ consumer đã commit; lag tăng kéo dài có thể báo hiệu consumer xử lý chậm, thiếu consumer hoặc có vấn đề kết nối.

Có thể dùng Kafka CLI để xem các group trong cluster:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

Xem thành viên, partition assignment, offset và lag của một group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-processor-prod
~~~

Tên script có thể khác theo cách cài đặt Kafka hoặc hệ điều hành. Khi chạy trên Windows, có thể sử dụng script `.bat` tương ứng trong thư mục `bin/windows`.

Khi điều tra một consumer không nhận record, nên kiểm tra theo thứ tự:

1. Consumer có kết nối đúng cluster và subscribe đúng topic không?
2. `group.id` thực tế của listener là gì? Có bị `@KafkaListener(groupId=...)` ghi đè cấu hình mặc định không?
3. Group có thành viên đang hoạt động và partition đã được gán không?
4. Offset đã commit đang ở đâu? `auto.offset.reset` có được áp dụng do group chưa có offset hợp lệ không?
5. Consumer lag có tăng không? Log có lỗi deserialization, xử lý hoặc rebalance không?

## 9. Checklist lựa chọn group.id

- [ ] Cùng một nghiệp vụ chạy nhiều replica dùng chung group ID ổn định.
- [ ] Mỗi nghiệp vụ cần nhận toàn bộ sự kiện có group ID riêng.
- [ ] Tên group phân biệt môi trường khi các môi trường dùng chung Kafka cluster.
- [ ] Không gắn pod ID hoặc chuỗi ngẫu nhiên vào group ID nếu mục tiêu là chia tải.
- [ ] Biết rõ việc đổi group ID sẽ tạo tiến độ tiêu thụ độc lập.
- [ ] Chọn `auto.offset.reset` có chủ đích cho group mới.
- [ ] Phân biệt `group.id`, `client.id`, listener `id` và `group.instance.id`.
- [ ] Theo dõi partition assignment, committed offset và consumer lag.

Trong Spring Kafka, `group.id` xác định danh tính subscription mà consumer tham gia. Dùng chung group ID giúp các replica chia nhau công việc; dùng group ID khác nhau giúp các nghiệp vụ có tiến độ đọc độc lập trên cùng topic. Đặt tên ổn định và có quy ước rõ ràng sẽ giúp triển khai, mở rộng và vận hành consumer dễ dự đoán hơn.
