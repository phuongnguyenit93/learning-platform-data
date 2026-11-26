# Consumer group của Kafka

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi sự kiện được externalize sang Kafka, consumer group quyết định cách nhiều instance của một ứng dụng cùng đọc topic và chia sẻ công việc. Hiểu đúng group, partition và offset giúp triển khai consumer có khả năng mở rộng, phục hồi sau lỗi và giữ được tính nhất quán của nghiệp vụ.

Một consumer group đại diện cho một nhóm consumer cùng hợp tác đọc dữ liệu từ topic. Trong cùng group, Kafka phân chia các partition cho các consumer đang hoạt động; mỗi partition tại một thời điểm chỉ được gán cho tối đa một consumer trong group đó. Một group khác có thể đọc cùng topic độc lập với group thứ nhất. Vì vậy, group ID vừa xác định danh tính của một subscriber logic, vừa quyết định cách Kafka quản lý offset của subscriber đó.

## 1. Consumer group là gì?

Kafka lưu message trong topic, và mỗi topic được chia thành một hoặc nhiều partition. Consumer đọc các record từ partition. Khi nhiều consumer thuộc cùng một group, Kafka phối hợp việc gán partition để các instance chia sẻ lượng công việc.

Ví dụ, topic orders.events có ba partition. Ba instance của dịch vụ Inventory cùng tham gia group inventory-service. Kafka có thể gán mỗi instance một partition. Khi có thêm instance thứ tư, instance mới có thể chưa nhận partition nào vì số consumer đang nhiều hơn số partition.

| Thành phần | Vai trò |
| --- | --- |
| Topic | Luồng record được producer ghi vào Kafka. |
| Partition | Đơn vị lưu trữ và phân phối thứ tự record trong topic. |
| Consumer | Tiến trình đọc record từ một hoặc nhiều partition. |
| Consumer group | Nhóm consumer cùng chia sẻ việc đọc topic và offset. |
| Group ID | Định danh ổn định của một subscriber logic. |
| Offset | Vị trí record trong một partition mà group đã đọc hoặc commit. |

Consumer group không phải là một hàng đợi riêng chứa bản sao message. Các group đọc cùng log của topic nhưng giữ tiến độ độc lập. Một record trong topic có thể được Inventory group, Analytics group và Notification group xử lý riêng.

## 2. Cùng group và khác group

Sự khác biệt giữa cùng group và khác group quyết định event được chia tải hay được nhiều ứng dụng xử lý độc lập.

| Cấu hình | Kết quả |
| --- | --- |
| Nhiều consumer cùng group ID | Chia partition và công việc của cùng một subscriber. |
| Mỗi ứng dụng có group ID riêng | Mỗi ứng dụng đọc toàn bộ luồng record theo tiến độ riêng. |
| Nhiều instance cùng group ID | Mở rộng năng lực xử lý của một ứng dụng. |
| Nhiều group cùng đọc một topic | Mỗi group nhận luồng record độc lập, phù hợp cho nhiều mục đích nghiệp vụ. |

Ví dụ, Inventory và Analytics đều cần nhận OrderConfirmed. Inventory có ba instance nhưng cả ba dùng group ID inventory-service. Analytics dùng group ID analytics-projection. Kafka phân chia partition trong Inventory group; Analytics group vẫn nhận toàn bộ record của topic theo offset riêng.

~~~mermaid
flowchart TD
    T[Topic orders.events]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    subgraph G1[Group inventory-service]
        I1[Inventory instance 1]
        I2[Inventory instance 2]
        I3[Inventory instance 3]
    end
    subgraph G2[Group analytics-projection]
        A1[Analytics consumer]
    end
    P0 --> I1
    P1 --> I2
    P2 --> I3
    P0 --> A1
    P1 --> A1
    P2 --> A1
~~~

Nếu vô tình cấp group ID khác nhau cho từng instance Inventory, mỗi instance trở thành một subscriber độc lập và tất cả có thể đọc toàn bộ topic. Kết quả là cùng một nghiệp vụ bị xử lý nhiều lần. Ngược lại, nếu Inventory và Analytics dùng chung group ID, hai ứng dụng sẽ chia partition với nhau và mỗi ứng dụng có thể bỏ lỡ một phần record. Hãy chọn group ID theo subscriber logic, không theo tên máy hoặc ID của pod.

## 3. Quan hệ giữa partition và số consumer

Kafka gán partition cho consumer trong từng group. Trong một group, một partition chỉ thuộc về tối đa một consumer tại cùng thời điểm. Một consumer có thể nhận nhiều partition nếu số consumer nhỏ hơn số partition.

Giả sử topic có sáu partition:

| Số consumer trong group | Tình huống điển hình |
| --- | --- |
| 1 | Một consumer đọc cả sáu partition. |
| 2 | Mỗi consumer có thể đọc ba partition. |
| 3 | Mỗi consumer có thể đọc hai partition. |
| 6 | Mỗi consumer có thể đọc một partition. |
| 8 | Hai consumer có thể không được gán partition. |

Đây là ví dụ minh họa; cách chia cụ thể phụ thuộc partition assignor, số consumer đang hoạt động và trạng thái group. Tăng số consumer vượt số partition không làm tăng số luồng đọc song song của group. Muốn tăng mức song song, cần cân nhắc số partition, khả năng xử lý của consumer và thứ tự nghiệp vụ.

Partition count cũng ảnh hưởng đến thứ tự. Kafka bảo đảm thứ tự record trong một partition, không bảo đảm thứ tự toàn cục giữa các partition. Nếu các event của cùng một aggregate phải được xử lý theo thứ tự, producer thường dùng aggregate ID làm message key để các record cùng key được đưa vào cùng partition. Consumer vẫn phải xử lý cẩn thận khi có retry hoặc xử lý bất đồng bộ.

## 4. Group ID và offset

Offset là vị trí của record trong một partition. Kafka lưu offset đã commit theo cặp consumer group và partition. Vì mỗi group có offset riêng, các subscriber có thể đọc cùng topic ở những tiến độ khác nhau.

Ví dụ, Inventory group đã commit đến offset 120 của partition 0, trong khi Analytics group mới commit đến offset 95. Điều này không làm thay đổi dữ liệu trong topic; mỗi group tiếp tục từ tiến độ đã lưu của chính nó.

Offset commit biểu thị tiến độ mà consumer group đã xác nhận với Kafka. Nếu consumer đã thực hiện side effect trong database nhưng dừng trước khi commit offset, record có thể được giao lại sau khi consumer khởi động hoặc partition được gán lại. Vì vậy, việc xử lý event cần idempotent.

### auto.offset.reset

Thuộc tính auto.offset.reset xác định hành vi khi group chưa có offset hợp lệ cho partition, chẳng hạn group mới hoặc offset cũ không còn nằm trong retention. Các giá trị thường gặp:

- earliest: bắt đầu từ record sớm nhất còn có trong partition.
- latest: bắt đầu từ record mới được ghi sau thời điểm consumer tham gia.
- none: phát lỗi nếu không tìm thấy offset hợp lệ.

Thiết lập này không tự đặt lại offset đã commit hợp lệ của một group đang hoạt động. Muốn phát lại dữ liệu đã đọc, cần một quy trình reset offset có kiểm soát hoặc tạo group ID mới theo chính sách vận hành. Trước khi replay, phải đánh giá tác động trùng lặp lên hệ thống nhận.

## 5. Cấu hình consumer group với Spring Kafka

Trong Spring Boot, group ID có thể được cấu hình ở consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: inventory-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Ví dụ trên dùng JSON deserializer để minh họa; cấu hình thực tế cần chỉ rõ kiểu payload, trusted package hoặc type mapping theo phiên bản Spring Kafka và chính sách bảo mật của ứng dụng. Không nên mở rộng trusted packages một cách tùy tiện khi consumer nhận dữ liệu từ hệ thống ngoài.

Một listener có thể khai báo group ID trực tiếp:

~~~java
@Component
class InventoryKafkaListener {

    @KafkaListener(
        topics = "orders.events",
        groupId = "inventory-service"
    )
    void on(OrderConfirmedPayload event) {
        // Xử lý event trong module Inventory.
    }
}
~~~

Khi khai báo groupId trong annotation, giá trị này được dùng cho listener đó và có thể ghi đè group ID mặc định trong consumer properties. Hãy thống nhất cấu hình ở một nơi nếu có thể để tránh các listener trong cùng một ứng dụng vô tình tham gia các group khác nhau.

Tên group ID nên ổn định qua các lần deploy và giống nhau giữa các instance của cùng một subscriber. Khi đổi group ID, Kafka xem đó là group mới với offset riêng. Điều này có thể khiến consumer đọc lại nhiều record hoặc chỉ đọc record mới tùy auto.offset.reset và dữ liệu offset hiện có.

## 6. Concurrency của listener container

Spring Kafka cho phép cấu hình concurrency cho listener container. Concurrency tạo các consumer instance trong cùng ứng dụng; Kafka vẫn chịu trách nhiệm gán partition cho từng consumer thuộc group.

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service",
    concurrency = "3"
)
void on(OrderConfirmedPayload event) {
    // Xử lý một record.
}
~~~

Nếu topic có ba partition và concurrency bằng ba, container có thể chạy tối đa ba consumer để đọc song song. Nếu topic chỉ có hai partition, consumer thứ ba có thể không được gán partition. Cần phối hợp concurrency với partition count, CPU, database connection pool và thời gian xử lý của handler.

Concurrency không tự làm cho logic nghiệp vụ thread-safe. Các consumer có thể chạy đồng thời và cập nhật các aggregate khác nhau hoặc thậm chí cùng một tài nguyên nếu key/partitioning không phù hợp. Hãy bảo vệ invariant bằng transaction, optimistic/pessimistic locking hoặc cơ chế đồng bộ phù hợp.

## 7. Rebalance và thay đổi thành viên group

Kafka group coordinator theo dõi thành viên consumer group. Khi consumer mới tham gia, consumer rời đi, heartbeat bị mất hoặc partition thay đổi, Kafka có thể thực hiện **rebalance** để phân phối lại partition.

Trong thời gian rebalance, một số consumer có thể tạm dừng nhận record. Sau khi assignment mới hoàn tất, consumer tiếp tục đọc từ offset đã commit hoặc vị trí được xác định theo cấu hình. Nếu handler xử lý lâu nhưng offset chưa được commit, record có thể được xử lý lại sau rebalance.

Các nguyên nhân thường gặp:

- Scale deployment tăng hoặc giảm số instance.
- Pod bị restart, bị terminate hoặc mất kết nối mạng.
- Consumer không gửi heartbeat kịp do xử lý quá lâu hoặc thread bị chặn.
- Thay đổi partition count của topic.
- Cấu hình timeout hoặc poll không phù hợp với thời gian xử lý.

Để giảm rebalance không cần thiết, giữ thời gian xử lý mỗi batch trong giới hạn phù hợp, cấu hình poll/heartbeat/session timeout theo phiên bản Kafka client, đóng consumer đúng cách khi shutdown và tránh giữ thread listener trong các tác vụ blocking quá lâu. Không nên tăng timeout vô hạn để che giấu handler bị treo.

## 8. Commit offset và acknowledgement

Consumer chỉ nên commit offset sau khi đã xử lý record theo mức đảm bảo mà nghiệp vụ yêu cầu. Nếu commit trước khi side effect hoàn tất, lỗi xảy ra sau đó có thể làm record bị bỏ qua khi consumer khởi động lại. Nếu side effect hoàn tất nhưng offset chưa commit, record có thể được giao lại.

Spring Kafka cung cấp các chế độ acknowledgement thông qua listener container. Với auto commit bị tắt, container có thể quản lý commit theo ack mode; ứng dụng cũng có thể dùng acknowledgement thủ công khi thật sự cần điều khiển thời điểm xác nhận.

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service"
)
void on(
        OrderConfirmedPayload event,
        Acknowledgment acknowledgment) {

    inventoryService.reserve(event.orderId());
    acknowledgment.acknowledge();
}
~~~

Ví dụ trên chỉ minh họa ý tưởng xác nhận sau khi service xử lý thành công. Để dùng tham số Acknowledgment, cần cấu hình container với chế độ manual acknowledgement tương ứng. Nếu service ném exception, không gọi acknowledge; error handler của Spring Kafka sẽ áp dụng chính sách retry/recovery đã cấu hình.

Commit offset là tiến độ của consumer group, không phải transaction database của module. Kafka transaction có thể phối hợp việc consume-transform-produce và commit offset trong một số kiến trúc, nhưng side effect vào database quan hệ không tự động nằm trong cùng một transaction Kafka. Với database side effect, cần idempotency/inbox hoặc một thiết kế tích hợp phù hợp.

## 9. At-least-once và idempotency

Trong nhiều cấu hình consumer thông dụng, ứng dụng hướng tới at-least-once: record có thể được giao lại nếu xử lý thành công nhưng offset chưa được commit. Điều này tránh mất record do commit quá sớm nhưng yêu cầu handler chịu được duplicate.

Ví dụ, Inventory nhận OrderConfirmed và tạo reservation. Nếu reservation đã được tạo nhưng consumer dừng trước khi offset commit, Kafka có thể giao lại event. Nếu handler tạo reservation mới mỗi lần, tồn kho sẽ bị giữ hai lần.

Các biện pháp chống xử lý trùng:

- Mang eventId ổn định trong payload hoặc metadata.
- Lưu eventId đã xử lý trong bảng inbox/deduplication có unique constraint.
- Cập nhật inbox record và dữ liệu nghiệp vụ trong cùng transaction database.
- Dùng business key như orderId và loại thao tác khi một nghiệp vụ chỉ được phép xảy ra một lần.
- Với API bên ngoài, truyền idempotency key nếu nhà cung cấp hỗ trợ.

Không dùng offset đơn lẻ làm khóa idempotency toàn hệ thống vì offset chỉ có ý nghĩa trong một partition của một topic và group. Khi event được phát lại qua topic khác hoặc được chuyển đổi, offset có thể khác trong khi event nghiệp vụ vẫn là một.

## 10. Retry, error handler và dead-letter topic

Lỗi khi xử lý record có thể là lỗi tạm thời như timeout database hoặc lỗi nghiệp vụ như dữ liệu không hợp lệ. Chính sách retry cần phân biệt các loại lỗi, giới hạn số lần thử và có cách xử lý khi không thể tiếp tục.

Trong Spring Kafka, error handler và cơ chế backoff/recovery có thể được cấu hình ở listener container factory. Tùy cấu hình, record có thể được retry tại consumer, chuyển sang dead-letter topic hoặc được xử lý bởi một recoverer. Dead-letter topic nên giữ thông tin nguồn như topic, partition, offset, exception và thời điểm lỗi để hỗ trợ điều tra.

Không retry vô hạn một record độc hại hoặc payload sai schema vì nó có thể chặn tiến độ của partition. Khi chuyển record sang dead-letter topic, cần xác định ai chịu trách nhiệm phân tích, sửa dữ liệu và replay; replay phải giữ eventId gốc để idempotency tiếp tục hoạt động.

Một điểm cần lưu ý là retry tại chỗ có thể ảnh hưởng thứ tự xử lý trong partition. Nếu một record lỗi giữ partition không tiến lên, các record sau có thể bị trì hoãn. Nếu error handler bỏ qua hoặc chuyển record lỗi đi, thứ tự nghiệp vụ có thể thay đổi. Hãy chọn chiến lược dựa trên yêu cầu ordering của domain.

## 11. Consumer group và Spring Modulith

Spring Modulith application events và Kafka consumer group giải quyết hai phạm vi giao tiếp khác nhau:

| Cơ chế | Phạm vi | Theo dõi tiến độ |
| --- | --- | --- |
| Spring application event | Listener trong application context của ứng dụng. | Dispatch nội bộ; transactional listener có thể được theo dõi bởi Event Publication Registry. |
| Kafka consumer group | Consumer đọc topic và partition trên Kafka. | Offset được commit theo group và partition. |

Event Publication Registry của Spring Modulith theo dõi publication đến transactional listener nội bộ; registry không thay thế Kafka group coordinator và không lưu offset của Kafka. Kafka group quản lý assignment và tiến độ đọc topic; nó không tự quản lý trạng thái nghiệp vụ của các module trong ứng dụng.

Nếu ứng dụng nhận message Kafka rồi công bố Spring application event nội bộ, cần xác định rõ ranh giới giữa hai cơ chế. Consumer Kafka có thể commit offset sau khi phần tiếp nhận đã được lưu bền vững; các listener nội bộ sau đó có thể được theo dõi riêng bởi publication registry. Không nên giả định commit offset và hoàn tất tất cả listener nội bộ là một transaction nguyên tử.

Một thiết kế phổ biến là Kafka listener xác thực message, lưu inbox hoặc dữ liệu tiếp nhận trong transaction, rồi phát application event nội bộ sau khi dữ liệu đã được ghi nhận. Nếu cần đảm bảo không mất event nội bộ giữa commit database và publish, hãy dùng cơ chế publication/outbox phù hợp với transaction thay vì chỉ dựa vào thứ tự gọi phương thức.

## 12. Kiểm thử consumer group

Unit test cho handler xác minh logic nghiệp vụ và idempotency. Integration test với Kafka thật hoặc test container phù hợp giúp kiểm tra group ID, partition assignment, offset, rebalance và retry.

Các trường hợp nên kiểm tra:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hai consumer cùng group | Partition được chia giữa consumer; một partition không bị gán đồng thời cho hai consumer trong group. |
| Hai group khác nhau | Cả hai group đều đọc được toàn bộ luồng record theo offset riêng. |
| Consumer mới tham gia | Rebalance diễn ra và record chưa commit có thể được giao lại. |
| Restart consumer | Consumer tiếp tục theo offset đã commit. |
| Group ID mới | Group có tiến độ độc lập và hành vi khởi đầu đúng theo auto.offset.reset. |
| Xử lý lỗi | Record được retry hoặc chuyển sang DLT theo chính sách. |
| Duplicate delivery | Handler không tạo side effect lặp. |
| Key và ordering | Các record cùng key được xử lý theo yêu cầu thứ tự của nghiệp vụ. |
| Nhiều partition | Concurrency và assignment phù hợp với partition count. |

Không nên viết test chỉ dựa vào thời gian sleep cố định để đoán rằng rebalance hoặc consume đã xong. Dùng consumer assignment, latch, condition hoặc kiểm tra offset với timeout hợp lý để test ổn định hơn.

## 13. Quan sát và vận hành consumer group

Theo dõi consumer group cần nhìn cả trạng thái thành viên, partition assignment và độ trễ xử lý. Các tín hiệu hữu ích gồm:

- Consumer group đang ổn định hay liên tục rebalance.
- Số member và số partition được gán cho mỗi member.
- Consumer lag theo từng partition và xu hướng tăng/giảm.
- Thời gian xử lý record và tỷ lệ exception theo event type.
- Số lần retry, số record chuyển vào dead-letter topic và tuổi của record lâu nhất.
- Offset commit gần nhất và thời điểm commit cuối.

Consumer lag là chênh lệch giữa vị trí record mới nhất và offset mà group đã commit hoặc đang xử lý, tùy công cụ đo. Lag tăng liên tục có thể cho thấy producer nhanh hơn consumer, handler chậm, partition bị nghẽn hoặc consumer group đang rebalance quá thường xuyên.

Log nên có group ID, topic, partition, offset, eventId và correlationId. Những trường này giúp nối lỗi ở Kafka listener với event nghiệp vụ và các bước xử lý nội bộ. Không log toàn bộ payload nếu có dữ liệu nhạy cảm.

Khi điều tra consumer không nhận được record, kiểm tra group ID có đúng không, topic có record và partition nào, consumer có được gán partition không, offset hiện tại ở đâu, auto.offset.reset có áp dụng không, có lỗi deserialization hoặc authorization không và listener có đang bị retry một record lỗi hay không.

## 14. Checklist thiết kế consumer group

- Mỗi subscriber logic có group ID ổn định và riêng biệt.
- Các instance của cùng subscriber dùng chung group ID.
- Các ứng dụng cần nhận độc lập dùng group ID khác nhau.
- Số partition và concurrency được chọn theo tải, ordering và năng lực xử lý.
- Message key hỗ trợ phân phối partition và thứ tự theo aggregate khi cần.
- Offset chỉ được xác nhận sau khi xử lý đạt mức an toàn đã chọn.
- Handler idempotent và có cơ chế deduplication bền vững.
- Retry phân biệt lỗi tạm thời với lỗi không thể phục hồi; có DLT và quy trình replay.
- Cấu hình timeout, poll và shutdown phù hợp để giảm rebalance không cần thiết.
- Consumer group được theo dõi bằng lag, assignment, rebalance và tỷ lệ lỗi.
- Ranh giới Kafka offset và Spring Modulith Event Publication Registry được thiết kế, quan sát riêng.
- Integration test bao phủ nhiều group, nhiều consumer, restart, retry và duplicate delivery.

Consumer group là cơ chế để nhiều instance cùng xử lý một luồng Kafka theo cách có kiểm soát. Khi group ID phản ánh đúng subscriber logic, partition phù hợp với mức song song, offset được commit đúng thời điểm và handler idempotent, ứng dụng có thể mở rộng consumer mà vẫn giữ được khả năng phục hồi. Kết hợp quan sát lag, rebalance và dead-letter flow sẽ giúp giao tiếp Kafka hỗ trợ tốt cho kiến trúc application events giữa các module.
