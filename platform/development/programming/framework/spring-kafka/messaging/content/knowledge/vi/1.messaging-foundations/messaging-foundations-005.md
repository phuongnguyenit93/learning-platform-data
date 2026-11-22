# Mô hình queue thông qua consumer group

## 1. Vì sao Kafka có thể hoạt động như một queue?

Kafka lưu sự kiện trong topic dưới dạng log có thứ tự. Producer ghi record vào topic; consumer đọc record theo offset. Kafka không xóa record ngay khi một consumer đọc xong. Record được giữ theo chính sách retention của topic, còn mỗi consumer group tự lưu tiến độ đọc của mình.

Khi nhiều consumer dùng chung một `group.id`, Kafka phân chia các partition của topic giữa những consumer đó. Mỗi record thuộc một partition được giao cho một consumer trong group tại một thời điểm. Các consumer cùng group vì vậy cạnh tranh để xử lý khối lượng công việc chung. Đây là cách dùng consumer group để tạo ra mô hình gần giống queue với competing consumers.

Điểm cần nhớ là queue ở đây là một cách tổ chức việc tiêu thụ. Dữ liệu vẫn nằm trong Kafka log; tiến độ xử lý được biểu diễn bằng offset của từng group.

## 2. Topic, partition và consumer group phối hợp với nhau

Ba khái niệm có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Topic | Luồng sự kiện mà producer ghi vào và consumer đăng ký đọc |
| Partition | Đơn vị lưu trữ, thứ tự và phân phối tải của topic |
| Consumer group | Một nhóm consumer cùng chia sẻ việc đọc topic và cùng quản lý tiến độ bằng group ID |

Ví dụ, topic `orders` có sáu partition. Group `order-processor` có ba consumer. Kafka gán các partition cho những consumer trong group, chẳng hạn:

| Consumer trong group `order-processor` | Partition được gán |
|---|---|
| Consumer A | P0, P1 |
| Consumer B | P2, P3 |
| Consumer C | P4, P5 |

Mỗi partition chỉ được gán cho tối đa một consumer trong cùng group tại một thời điểm. Một consumer có thể nhận nhiều partition. Việc gán cụ thể do cơ chế partition assignment của Kafka quyết định; bảng trên chỉ minh họa một cách phân chia cân bằng.

Sơ đồ dưới đây cho thấy hai group độc lập cùng đọc một topic:

~~~mermaid
flowchart LR
    T["Topic orders<br/>P0 ... P5"]
    T --> G1["Group order-processor"]
    T --> G2["Group fraud-monitor"]
    G1 --> A["Consumer A"]
    G1 --> B["Consumer B"]
    G1 --> C["Consumer C"]
    G2 --> D["Consumer D"]
    G2 --> E["Consumer E"]
~~~

Trong `order-processor`, các consumer A, B và C chia nhau partition nên một record chỉ được một thành viên của group nhận xử lý tại một thời điểm. Group `fraud-monitor` có tiến độ đọc riêng và cũng đọc các record của topic `orders`. Vì vậy, cùng một sự kiện có thể được mỗi group nhận và xử lý độc lập, chẳng hạn cho nghiệp vụ đơn hàng và cho kiểm tra gian lận.

Có thể liên hệ như sau:

- Các consumer có cùng group ID giống những worker cùng lấy việc từ một queue.
- Hai group ID khác nhau giống hai hệ thống đăng ký độc lập; mỗi hệ thống có thể đọc cùng một luồng sự kiện.
- Một consumer bị dừng không làm record biến mất. Consumer khác trong group có thể nhận partition sau khi Kafka phân phối lại.

## 3. Consumer group quyết định khả năng xử lý song song

Số consumer hoạt động hữu ích trong một group bị giới hạn bởi số partition của topic.

Giả sử topic có sáu partition:

| Số consumer trong group | Kết quả |
|---:|---|
| 1 | Một consumer đọc cả sáu partition |
| 3 | Ba consumer có thể chia nhau sáu partition |
| 6 | Tối đa sáu consumer cùng có partition để đọc |
| 8 | Tối đa sáu consumer có partition; hai consumer còn lại chưa được gán partition |

Tăng số consumer vượt quá số partition không làm tăng mức song song của topic đó. Nếu cần nhiều luồng xử lý độc lập hơn, phải cân nhắc tăng số partition, đồng thời đánh giá ảnh hưởng đến thứ tự theo key, phân bố dữ liệu và tài nguyên broker.

### Thứ tự của record

Kafka bảo đảm thứ tự trong phạm vi một partition, không bảo đảm một thứ tự toàn cục giữa nhiều partition. Nếu producer gửi các sự kiện có cùng key, chẳng hạn `orderId`, các record đó thường được đưa vào cùng partition theo partitioner đang sử dụng. Điều này giúp các sự kiện của cùng một đơn hàng được đọc theo thứ tự trong partition đó.

Vì thế, khi thiết kế topic, hãy chọn key theo thực thể nghiệp vụ cần giữ thứ tự. Nếu không có key phù hợp, các record có thể phân tán qua nhiều partition và được xử lý song song theo những thứ tự khác nhau.

### Nhiều instance của ứng dụng Spring Kafka

Các replica của cùng một dịch vụ thường dùng chung group ID. Ví dụ, ba pod của dịch vụ xử lý đơn hàng đều tham gia group `order-processor`; Kafka sẽ chia partition giữa các consumer thuộc cả ba pod.

Trong một ứng dụng Spring Kafka, thuộc tính `concurrency` của listener container có thể tạo nhiều consumer trong cùng group. Nếu mỗi pod đặt `concurrency = 3` và có hai pod, group có thể có tổng cộng sáu consumer. Số consumer thực sự nhận partition vẫn bị giới hạn bởi số partition được đăng ký.

Khi consumer tham gia, rời group hoặc mất kết nối, Kafka có thể thực hiện rebalance để phân phối lại partition. Trong lúc rebalance, việc đọc có thể tạm gián đoạn; sau đó consumer mới tiếp tục từ tiến độ đã commit của group.

## 4. Offset là tiến độ riêng của từng group

Kafka theo dõi offset theo tổ hợp group ID, topic và partition. Hai group đọc cùng một topic không dùng chung offset. Group `order-processor` có thể đã xử lý đến một vị trí, trong khi `fraud-monitor` vẫn đang đọc ở vị trí trước đó.

Offset đã commit là mốc tiến độ được lưu để group có thể tiếp tục sau khi consumer khởi động lại hoặc partition được giao cho consumer khác. Việc đọc một record không tự xóa record khỏi topic và cũng không đồng nghĩa rằng nghiệp vụ đã hoàn tất an toàn.

Với xử lý có ghi dữ liệu hoặc gọi dịch vụ bên ngoài, thứ tự xử lý và commit rất quan trọng:

1. Nếu ứng dụng xử lý thành công rồi dừng trước khi commit offset, record có thể được đọc và xử lý lại.
2. Nếu ứng dụng commit offset trước khi xử lý hoàn tất, lỗi xảy ra sau đó có thể khiến nghiệp vụ bị bỏ sót khi group tiếp tục đọc.

Vì vậy, ứng dụng thường cần xử lý thành công rồi mới xác nhận tiến độ, đồng thời thiết kế thao tác nghiệp vụ có tính idempotent để chịu được việc nhận lại record. Việc một record được giao cho một thành viên trong group không phải là cam kết rằng hiệu ứng nghiệp vụ chỉ xảy ra đúng một lần.

Thuộc tính `auto.offset.reset` chỉ quyết định vị trí bắt đầu khi group chưa có offset hợp lệ. Chẳng hạn, `earliest` yêu cầu đọc từ record cũ nhất còn được giữ trong topic; nó không khôi phục dữ liệu đã hết hạn retention. Khi group đã có offset hợp lệ, Kafka tiếp tục theo offset đã lưu.

## 5. Khai báo consumer group bằng Spring Kafka

Có thể cấu hình group ID và chính sách bắt đầu đọc trong `application.yml`:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Một listener tham gia group đó:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${spring.kafka.consumer.group-id}",
        concurrency = "3"
    )
    public void consume(String payload) {
        // Validate và xử lý sự kiện đơn hàng.
        // Chỉ xác nhận tiến độ sau khi xử lý theo chính sách đã chọn.
    }
}
~~~

Trong ví dụ này:

- `groupId` xác định danh tính subscription và tiến độ đọc của dịch vụ xử lý đơn hàng.
- `concurrency = "3"` yêu cầu listener container tạo ba consumer đồng thời trong group.
- `enable-auto-commit: false` tắt việc consumer client tự commit theo lịch; Spring Kafka quản lý việc xác nhận offset theo cấu hình ack mode của listener container.
- `auto-offset-reset: earliest` áp dụng khi group chưa có offset hợp lệ.

Ví dụ dùng `String` để tập trung vào cơ chế group. Ứng dụng thực tế cần cấu hình deserializer phù hợp với định dạng payload, xử lý lỗi và chọn ack mode theo yêu cầu nghiệp vụ. Nếu chạy nhiều replica, các replica của cùng dịch vụ cần tham gia cùng group ID để chia tải.

Nếu một dịch vụ khác cũng cần nhận toàn bộ sự kiện `orders`, dịch vụ đó nên dùng group ID riêng, ví dụ `fraud-monitor`. Nếu dùng chung `order-processor`, hai dịch vụ sẽ chia partition với nhau và mỗi dịch vụ chỉ nhận phần dữ liệu được giao, thay vì cả hai cùng nhận toàn bộ sự kiện.

## 6. Chọn mô hình group cho bài toán thực tế

Khi thiết kế consumer group cho một luồng messaging, hãy trả lời các câu hỏi sau:

- **Ai cần nhận sự kiện?** Các replica của cùng một nghiệp vụ nên dùng chung group ID. Mỗi nghiệp vụ độc lập cần nhận toàn bộ sự kiện nên có group ID riêng.
- **Cần xử lý song song đến mức nào?** Chọn số partition theo thông lượng và mức song song mong muốn; số consumer hữu ích trong một group không thể vượt số partition đang được gán.
- **Cần giữ thứ tự theo thực thể nào?** Chọn message key phù hợp, chẳng hạn `orderId`, và xử lý các sự kiện của key đó trong cùng partition.
- **Điều gì xảy ra khi xử lý lỗi?** Xác định thời điểm commit offset, cách retry và cách chống tác động trùng lặp. Theo dõi consumer lag để biết group đang chậm bao nhiêu so với cuối log.
- **Điều gì xảy ra khi scale ứng dụng?** Dự kiến rebalance khi consumer tăng, giảm hoặc mất kết nối; bảo đảm listener có thể tiếp tục an toàn từ offset đã commit.

Ví dụ, topic `orders` có sáu partition. Group `order-processor` chạy ba consumer để chia tải xử lý đơn hàng. Group `fraud-monitor` chạy hai consumer để kiểm tra gian lận. Cả hai group đều có thể đọc toàn bộ luồng sự kiện `orders`, nhưng mỗi group có thành viên, phân công partition và offset độc lập. Khi một consumer trong `order-processor` dừng, Kafka phân phối lại partition cho các thành viên còn lại và group tiếp tục từ tiến độ đã commit.

Đó là nền tảng của mô hình queue thông qua consumer group trong Kafka: **cùng group thì chia việc; khác group thì có tiến độ tiêu thụ độc lập**. Hiểu rõ ranh giới này giúp thiết kế số partition, số consumer, group ID và cơ chế commit phù hợp với từng nghiệp vụ Spring Kafka.
