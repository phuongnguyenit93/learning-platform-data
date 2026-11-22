# Pub/sub, xử lý theo nhóm và khả năng đọc lại dữ liệu

Apache Kafka hỗ trợ mô hình publish/subscribe (pub/sub): producer công bố sự kiện lên topic, còn các ứng dụng quan tâm đăng ký đọc luồng sự kiện đó. Điểm quan trọng là Kafka tổ chức dữ liệu thành log phân vùng được lưu giữ theo chính sách retention. Mỗi consumer group có tiến độ đọc riêng, vì vậy nhiều nhóm ứng dụng có thể nhận cùng một luồng sự kiện và xử lý độc lập.

Cần phân biệt hai cách dùng consumer group. Các consumer có cùng group ID chia nhau partition để mở rộng xử lý cho một ứng dụng. Các consumer thuộc group ID khác nhau hoạt động như những subscriber độc lập; mỗi group có thể đọc toàn bộ luồng topic theo tiến độ riêng. Cơ chế này tạo ra fan-out giữa các hệ thống và khả năng phát lại dữ liệu mà không yêu cầu producer gửi lại sự kiện.

Bài học đặt các cơ chế đó trong bối cảnh xây dựng hệ thống event streaming với Apache Kafka, nơi Java và Spring Kafka thường được dùng để phát, tiêu thụ, xử lý và tái dựng dữ liệu từ sự kiện.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích pub/sub và cách Kafka lưu giữ luồng sự kiện trong topic.
- Phân biệt nhiều consumer cùng một group với nhiều group độc lập.
- Chọn group ID phù hợp để chia tải hoặc tạo một subscriber mới.
- Giải thích offset, committed offset, consumer lag và retention.
- Đọc lại dữ liệu từ đầu hoặc từ một mốc xác định trong phạm vi dữ liệu còn lưu.
- Lập kế hoạch replay an toàn, hạn chế tác dụng phụ và bảo vệ consumer đang chạy.

## 1. Pub/sub trong Kafka hoạt động như thế nào?

Pub/sub là mô hình giao tiếp trong đó bên phát không cần biết cụ thể bên nhận. Producer công bố sự kiện lên một topic; các ứng dụng subscriber tự đăng ký topic và đọc những sự kiện chúng quan tâm. Producer không cần gọi trực tiếp từng ứng dụng tiêu thụ.

Trong Kafka, broker nhận record từ producer rồi append record vào partition của topic. Consumer chủ động fetch dữ liệu từ broker và quản lý vị trí đọc của mình thông qua offset. Vì vậy, Kafka kết hợp mô hình pub/sub với một log phân tán có thể lưu giữ và đọc lại.

Ví dụ, dịch vụ đơn hàng phát sự kiện vào topic `orders.events`. Dịch vụ thanh toán cần các sự kiện để cập nhật quy trình thu tiền; hệ thống phân tích cần chúng để tổng hợp doanh thu; dịch vụ tìm kiếm cần chúng để cập nhật chỉ mục. Cả ba ứng dụng đều quan tâm cùng một luồng sự kiện, nhưng có thể xử lý ở tốc độ và thời điểm khác nhau.

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer"] --> T["orders.events<br/>Kafka topic"]
    T --> B["Consumer group<br/>billing-service"]
    T --> A["Consumer group<br/>analytics-service"]
    T --> S["Consumer group<br/>search-indexer"]
    B --> B1["Billing consumers<br/>chia partition"]
    A --> A1["Analytics consumers<br/>tiến độ riêng"]
    S --> S1["Indexer consumers<br/>tiến độ riêng"]
~~~

Topic là luồng dữ liệu dùng chung. Mỗi consumer group duy trì vị trí đọc riêng nên một group đọc đến cuối topic không làm dữ liệu biến mất đối với group khác. Kafka không xóa một record ngay sau khi một consumer đọc xong; broker giữ dữ liệu theo chính sách retention và cleanup của topic.

Đây là khác biệt quan trọng so với cách hình dung hàng đợi đơn giản: một thông điệp được lấy khỏi hàng đợi dùng chung sau khi được xử lý. Trong Kafka, nhiều group có thể đọc cùng record độc lập trong thời gian record còn tồn tại trên log.

## 2. Cùng group chia tải, khác group nhận luồng độc lập

Consumer group là một tập hợp consumer phối hợp để đọc topic. Group ID xác định danh tính logic của subscriber và là khóa để Kafka lưu tiến độ đọc.

### Các consumer cùng group

Giả sử topic có ba partition và ứng dụng thanh toán chạy hai instance với cùng group ID là `billing-service`. Kafka phân công partition cho các thành viên của group. Một instance có thể nhận partition 0 và 1, instance còn lại nhận partition 2. Hai instance chia nhau công việc của cùng một subscriber.

Trong một consumer group, mỗi partition được gán cho tối đa một consumer tại một thời điểm. Vì thế:

- Các consumer trong group không cùng nhận mọi bản sao của một record.
- Tổng số partition giới hạn số consumer có thể tích cực xử lý partition song song trong group.
- Nếu có nhiều consumer hơn partition, một số consumer sẽ không được gán partition.
- Khi thành viên tham gia, rời đi hoặc lỗi, Kafka có thể thực hiện rebalance để phân công lại partition.

Ví dụ, topic có sáu partition và group có ba consumer. Nếu assignment phân bố đều, mỗi consumer nhận khoảng hai partition. Nếu group tăng lên sáu consumer, mỗi consumer có thể nhận một partition. Nếu tăng lên tám consumer, ít nhất hai consumer sẽ không có partition để xử lý trong trạng thái assignment đó.

Số partition, thuật toán assignor và trạng thái group quyết định assignment thực tế. Không nên giả định partition luôn được chia đều tuyệt đối trong mọi cấu hình.

### Các group khác nhau

Nếu dịch vụ phân tích dùng group ID `analytics-service`, đây là một subscriber độc lập. Group này có tiến độ đọc riêng và có thể đọc tất cả partition của topic, ngay cả khi group thanh toán đã đọc xong.

Tương tự, `search-indexer` có thể đọc cùng topic để cập nhật chỉ mục. Nếu hệ thống phân tích tạm dừng vài giờ, group thanh toán vẫn tiếp tục xử lý theo tiến độ của nó. Khi hệ thống phân tích hoạt động lại, nó tiếp tục từ offset đã commit nếu dữ liệu tương ứng vẫn còn trên log.

| Cách tổ chức | Điều xảy ra | Mục đích phù hợp |
|---|---|---|
| Nhiều consumer cùng group ID | Chia partition và chia công việc của một subscriber | Mở rộng một dịch vụ theo chiều ngang |
| Một consumer trong mỗi group ID khác nhau | Mỗi group có tiến độ độc lập và đọc toàn bộ luồng | Fan-out đến nhiều ứng dụng hoặc mục đích xử lý |
| Nhiều instance cùng tên ứng dụng nhưng group ID khác nhau | Mỗi instance trở thành một subscriber riêng | Chỉ dùng khi thật sự cần mỗi instance nhận toàn bộ sự kiện |

Một lỗi cấu hình phổ biến là tạo group ID khác nhau cho từng replica của cùng một dịch vụ. Thay vì chia tải, mỗi replica sẽ trở thành một subscriber độc lập và có thể xử lý toàn bộ sự kiện. Điều đó làm tăng tải broker và có thể lặp tác dụng phụ ở hệ thống đích.

Với một dịch vụ cần scale ngang, các replica thường dùng chung một group ID ổn định. Với hai ứng dụng cần nhận cùng luồng, mỗi ứng dụng dùng một group ID riêng.

## 3. Group ID là danh tính của subscriber

Group ID gắn tiến độ đọc với một mục đích tiêu thụ cụ thể. Chọn group ID vì vậy là quyết định kiến trúc, không chỉ là đặt tên cấu hình.

Một số quy tắc thực tế:

- Dùng một group ID ổn định cho các replica của cùng một dịch vụ.
- Dùng group ID khác nhau cho các ứng dụng có mục đích xử lý độc lập.
- Phân biệt môi trường phát triển, kiểm thử và production để chúng không vô tình chia sẻ tiến độ.
- Không tạo group ID ngẫu nhiên mỗi lần khởi động nếu muốn tiếp tục từ offset đã commit.
- Đặt tên thể hiện vai trò, ví dụ `billing-service`, `analytics-service`, `search-indexer`.

Group ID mới được Kafka xem là một subscriber mới. Nếu group đó chưa có committed offset, cách bắt đầu đọc phụ thuộc vào cấu hình `auto.offset.reset`. Đây là cơ chế hữu ích để xây dựng một consumer mới hoặc tái dựng một read model, nhưng cũng có thể làm ứng dụng đọc lại nhiều dữ liệu ngoài dự kiến nếu group ID bị đổi nhầm.

Trong triển khai nhiều môi trường, có thể đặt tên như `billing-service-prod` và `billing-service-staging`. Cách đặt tên phải thống nhất giữa các replica trong cùng môi trường.

## 4. Offset và tiến độ đọc của từng group

Mỗi record trong partition có offset. Offset là vị trí của record trong log partition đó; nó không phải số thứ tự toàn cục của topic và không thể dùng để so sánh thứ tự giữa hai partition khác nhau.

Consumer group duy trì committed offset riêng cho từng topic-partition. Kafka lưu thông tin này trong topic nội bộ `__consumer_offsets`. Nhờ đó, khi consumer khởi động lại hoặc group rebalance, thành viên mới có thể tiếp tục từ vị trí group đã commit.

Committed offset thường biểu diễn vị trí tiếp theo cần đọc. Nếu ứng dụng đã xử lý thành công record có offset 41 và commit offset 42, lần đọc tiếp theo bắt đầu từ offset 42.

Ví dụ với một topic có hai partition:

| Group | Partition 0 | Partition 1 |
|---|---:|---:|
| `billing-service` | committed offset 120 | committed offset 98 |
| `analytics-service` | committed offset 75 | committed offset 95 |
| `search-indexer` | committed offset 118 | committed offset 60 |

Bảng chỉ minh họa rằng mỗi group có tiến độ riêng. Không thể kết luận group có offset lớn hơn ở partition 0 đã xử lý nhiều sự kiện hơn trên toàn topic, bởi mỗi partition có tốc độ ghi và lịch sử riêng.

### Commit offset và xử lý bản ghi

Thời điểm commit ảnh hưởng đến khả năng mất hoặc lặp xử lý:

- Nếu commit trước khi hoàn thành tác dụng phụ, ứng dụng có thể lỗi sau commit và bỏ qua record đó khi khởi động lại.
- Nếu hoàn thành tác dụng phụ rồi mới commit, ứng dụng có thể lỗi giữa hai bước; record được đọc lại và tác dụng phụ có thể lặp.
- Vì vậy, xử lý theo kiểu at-least-once thường cần thao tác idempotent hoặc cơ chế deduplication ở hệ thống đích.

Ví dụ, consumer cập nhật cơ sở dữ liệu rồi mới commit offset. Nếu tiến trình dừng sau khi database commit nhưng trước khi Kafka nhận commit offset, record có thể được xử lý lại. Ứng dụng nên có event ID duy nhất, bảng inbox/deduplication hoặc ràng buộc nghiệp vụ để lần xử lý lặp không tạo thêm tác dụng phụ.

Kafka transaction có thể phối hợp việc đọc và ghi giữa các topic Kafka theo cấu hình phù hợp. Nếu tác dụng phụ nằm trong hệ thống bên ngoài như cơ sở dữ liệu, dịch vụ thanh toán hoặc API, cần thiết kế tính nhất quán với hệ thống đó; chỉ bật transaction của Kafka không tự làm cho toàn bộ giao dịch đa hệ thống trở thành một transaction nguyên tử.

## 5. Retention quyết định dữ liệu có thể đọc lại trong bao lâu

Kafka giữ record theo chính sách của topic, không phụ thuộc việc tất cả consumer group đã đọc record hay chưa. Với topic dùng chính sách xóa theo thời gian hoặc dung lượng, broker có thể xóa các segment cũ khi điều kiện retention được đáp ứng.

Hai cấu hình thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| `retention.ms` | Thời gian lưu dữ liệu theo chính sách retention |
| `retention.bytes` | Ngưỡng dung lượng lưu giữ áp dụng cho partition theo cấu hình topic |

Ví dụ, topic có retention bảy ngày cho phép subscriber đọc lại dữ liệu trong khoảng lưu giữ đó, với điều kiện record chưa bị xóa sớm hơn do giới hạn dung lượng. Đây không phải cam kết mọi record luôn tồn tại đủ bảy ngày trong mọi tình huống nếu đồng thời có giới hạn dung lượng.

Consumer chậm hơn tốc độ ghi có thể bị tăng lag. Nếu lag vượt quá cửa sổ retention và các record cũ đã bị xóa, group không thể đọc lại phần dữ liệu đó từ Kafka. Do đó, retention cần được chọn dựa trên thời gian gián đoạn tối đa dự kiến, tốc độ phát sinh dữ liệu, dung lượng lưu trữ và nhu cầu replay.

### Delete và compaction

Hai kiểu cleanup phổ biến có mục tiêu khác nhau:

- `cleanup.policy=delete`: xóa segment cũ theo retention time/size. Đây là lựa chọn thường gặp cho event log cần giữ lịch sử trong một cửa sổ thời gian.
- `cleanup.policy=compact`: giữ trạng thái mới nhất theo key bằng cách loại bỏ các bản ghi cũ hơn cho cùng key trong quá trình compaction.

Topic compacted không phải bản lưu trữ đầy đủ của mọi sự kiện đã từng phát. Nếu cần dựng lại toàn bộ lịch sử giao dịch, không thể mặc định rằng compacted topic còn đủ mọi event. Tombstone cũng có thể bị loại bỏ sau thời gian lưu giữ tombstone được cấu hình.

Một số topic có thể kết hợp `compact,delete`, khi đó cả hai cơ chế cùng ảnh hưởng đến dữ liệu còn đọc được. Trước khi thiết kế replay, hãy hiểu cleanup policy của topic thay vì chỉ nhìn vào committed offset.

## 6. Đọc lại dữ liệu từ đầu hoặc từ một mốc xác định

Replay là việc consumer đọc lại record đã tồn tại trên Kafka. Có hai cách phổ biến để bắt đầu một lượt đọc lại.

### Dùng group ID mới

Tạo group ID mới cho mục đích replay hoặc dựng lại dữ liệu. Nếu group chưa có committed offset và `auto.offset.reset=earliest`, consumer bắt đầu từ offset sớm nhất còn tồn tại trong mỗi partition.

Cách này thường an toàn hơn cho việc tái dựng read model vì group production hiện tại tiếp tục giữ tiến độ riêng. Có thể chạy consumer mới để dựng bảng hoặc chỉ mục mới, đối chiếu kết quả, rồi chuyển ứng dụng đọc sang dữ liệu đã dựng xong.

Ví dụ đọc topic bằng Kafka CLI:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.events \
  --group billing-replay-2026-11 \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Với group ID chưa có offset, `--from-beginning` yêu cầu bắt đầu từ dữ liệu sớm nhất còn lưu. Nếu group ID đã có committed offset hợp lệ, consumer tiếp tục từ offset đó; tham số này không tự ghi đè tiến độ đã commit.

### Đặt lại offset của group hiện tại

Có thể reset offset của group hiện tại để đọc lại dữ liệu. Đây là thao tác ảnh hưởng đến tiến độ của subscriber đó. Cần dừng các consumer thuộc group trước khi reset để tránh chúng tiếp tục xử lý trong lúc thay đổi offset.

Trước tiên, xem trạng thái group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service
~~~

Chạy thử kế hoạch reset về đầu topic:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders.events \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Nếu kết quả đúng với phạm vi cần replay, thực thi bằng cách thay `--dry-run` thành `--execute`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders.events \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Cú pháp và các tùy chọn reset có thể khác đôi chút theo phiên bản Kafka CLI. Hãy kiểm tra `--help` của bản đang cài trước khi vận hành. Sau khi reset, khởi động lại consumer group và quan sát offset, lag, lỗi xử lý cũng như tác dụng phụ ở hệ thống đích.

### auto.offset.reset không phải lệnh reset offset

Cấu hình `auto.offset.reset` thường có các giá trị:

| Giá trị | Hành vi khi group không có offset hợp lệ |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất còn có thể đọc |
| `latest` | Bắt đầu từ cuối log hiện tại và nhận các record mới |
| `none` | Phát sinh lỗi nếu không tìm được offset hợp lệ |

Cấu hình này chỉ được dùng khi không có committed offset hợp lệ, chẳng hạn group mới hoặc offset đã nằm ngoài phạm vi log còn tồn tại. Nó không tự reset một group đang có committed offset hợp lệ về đầu topic.

Khi offset cũ đã bị xóa do retention, consumer có thể cần áp dụng chính sách reset để tiếp tục. Hãy theo dõi tình huống này vì việc tự chuyển sang earliest hoặc latest có thể khiến ứng dụng đọc lại dữ liệu hoặc bỏ qua khoảng dữ liệu đã hết hạn.

## 7. Ví dụ với Spring Kafka: nhiều subscriber cùng đọc một topic

Giả sử dịch vụ đơn hàng phát sự kiện vào `orders.events`. Dịch vụ thanh toán và dịch vụ phân tích đều cần nhận các sự kiện này.

Subscriber thanh toán:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "billing-service"
    )
    public void handle(OrderEvent event) {
        // Kiểm tra trạng thái và xử lý nghiệp vụ thanh toán.
        billingService.process(event);
    }
}
~~~

Subscriber phân tích:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class AnalyticsOrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "analytics-service"
    )
    public void handle(OrderEvent event) {
        // Cập nhật số liệu phân tích từ cùng luồng sự kiện.
        analyticsService.record(event);
    }
}
~~~

Hai listener dùng group ID khác nhau nên tiến độ đọc độc lập. Mỗi replica của dịch vụ thanh toán cần dùng cùng group ID `billing-service`; các replica của dịch vụ phân tích dùng `analytics-service`.

Cấu hình consumer cơ bản cho dịch vụ thanh toán có thể được đặt trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Ví dụ chỉ minh họa các thuộc tính chính. Với JSON deserialization, ứng dụng còn cần cấu hình type mapping hoặc trusted packages phù hợp với hợp đồng dữ liệu và phiên bản Spring Kafka đang sử dụng. Spring Kafka quản lý commit theo listener container khi auto commit bị tắt; cần chọn acknowledgement mode và cách xử lý exception phù hợp với yêu cầu nghiệp vụ.

Nếu cần chạy một lượt tái dựng phân tích, có thể triển khai một consumer có group ID riêng, ví dụ `analytics-rebuild-2026-11`, trỏ đến kho dữ liệu đích mới. Sau khi hoàn thành và kiểm tra kết quả, ứng dụng có thể chuyển sang kho dữ liệu đã dựng. Không nên đổi group ID production chỉ để thử replay, vì group ID mới có thể bắt đầu đọc lại toàn bộ cửa sổ retention.

## 8. Replay an toàn và kiểm soát tác dụng phụ

Replay giúp khôi phục read model, dựng chỉ mục, kiểm tra dữ liệu hoặc chuyển đổi schema. Tuy nhiên, đọc lại record đồng nghĩa logic consumer có thể chạy lại. Nếu logic đó tạo tác dụng phụ, replay có thể gây ra hành động lặp.

Ví dụ, một consumer thanh toán nhận `PaymentRequested` rồi gọi cổng thanh toán. Nếu replay toàn bộ topic bằng một group mới và gọi lại cổng thanh toán cho từng record, khách hàng có thể bị thu tiền lần nữa. Kafka không biết tác dụng phụ đó đã xảy ra ở hệ thống bên ngoài.

Một quy trình replay có kiểm soát nên bao gồm:

1. **Xác định mục đích.** Replay để dựng read model, sửa dữ liệu, kiểm thử hay thực thi lại nghiệp vụ? Mỗi mục đích cần chính sách tác dụng phụ khác nhau.
2. **Chọn group ID.** Dùng group mới khi cần chạy độc lập và giữ nguyên tiến độ production; chỉ reset group hiện tại khi đã hiểu ảnh hưởng đến subscriber đó.
3. **Chọn phạm vi dữ liệu.** Xác định topic, partition, offset hoặc mốc thời gian và kiểm tra dữ liệu vẫn còn trong retention.
4. **Chọn kho đích.** Ưu tiên dựng vào bảng, index hoặc môi trường riêng rồi đối chiếu trước khi chuyển sang sử dụng.
5. **Bảo vệ tác dụng phụ.** Dùng event ID, idempotency key, inbox/deduplication hoặc chế độ chỉ đọc để ngăn lặp hành động.
6. **Điều tiết tải.** Replay có thể tạo tải đọc lớn lên broker và tải ghi lớn lên hệ thống đích. Cần giới hạn tốc độ và theo dõi lag của các group đang chạy.
7. **Đối chiếu và kết thúc.** Kiểm tra số lượng record, lỗi, trạng thái nghiệp vụ và chênh lệch dữ liệu trước khi hoàn tất.

Một event ID duy nhất giúp nhận diện cùng một sự kiện qua nhiều lần phát hoặc replay. Hệ thống đích có thể lưu ID đã xử lý và bỏ qua lần xử lý trùng. Tuy nhiên, deduplication cần có phạm vi lưu giữ phù hợp với cửa sổ replay; nếu xóa dấu vết quá sớm, một replay muộn vẫn có thể lặp tác dụng phụ.

Nếu replay để xây dựng read model, có thể xóa hoặc tạo mới kho đích rồi nạp lại từ Kafka. Nếu replay để sửa dữ liệu production, nên có kế hoạch đối chiếu, giới hạn phạm vi và cơ chế khôi phục. Không dùng replay như một cách thay thế cho migration dữ liệu có kiểm soát.

## 9. Theo dõi group và phát hiện subscriber bị tụt lại

Một subscriber độc lập có thể chậm hơn các group khác. Điều này không ngăn các group còn lại tiếp tục đọc, nhưng nếu lag kéo dài vượt retention thì subscriber chậm có thể mất khả năng đọc lại các record cũ.

Dùng lệnh sau để xem tiến độ group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group analytics-service
~~~

Các cột thường hữu ích:

| Thông tin | Ý nghĩa |
|---|---|
| CURRENT-OFFSET | Offset đã commit của group |
| LOG-END-OFFSET | Vị trí cuối hiện tại của partition |
| LAG | Chênh lệch giữa log end offset và committed offset theo cách công cụ tính |
| CONSUMER-ID | Thành viên consumer đang giữ assignment |
| PARTITION | Partition mà dòng thông tin mô tả |

Lag là chỉ báo về lượng dữ liệu chưa được group tiêu thụ theo offset. Nó không trực tiếp biểu diễn độ trễ thời gian nghiệp vụ. Nếu cần biết một sự kiện mất bao lâu từ lúc phát đến lúc xử lý, hãy theo dõi timestamp nghiệp vụ, timestamp record và thời điểm xử lý ở consumer.

Khi lag tăng, hãy xem xét tốc độ producer, số partition, năng lực consumer, thời gian xử lý từng record, rebalance, lỗi downstream và giới hạn tài nguyên. Không nên chỉ tăng số consumer: nếu số partition không tăng hoặc một partition bị nóng, thêm consumer có thể không cải thiện throughput.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Mỗi consumer đều nhận mọi record trong cùng một group | Consumer trong cùng group chia partition; chỉ các group khác nhau mới đọc luồng độc lập |
| Kafka xóa record sau khi consumer đọc xong | Record được giữ theo retention/cleanup policy, không theo việc một group đã đọc |
| Đổi group ID chỉ đổi tên ứng dụng | Group ID mới có tiến độ riêng và có thể bắt đầu đọc lại dữ liệu theo auto.offset.reset |
| `--from-beginning` luôn đưa group về đầu topic | Nó chỉ có tác dụng bắt đầu từ earliest khi group chưa có offset hợp lệ; không ghi đè committed offset đang tồn tại |
| auto.offset.reset luôn reset group khi khởi động | Nó chỉ áp dụng khi không có offset hợp lệ |
| Tăng consumer luôn tăng khả năng xử lý | Số partition và assignment giới hạn mức song song trong group |
| Compacted topic lưu toàn bộ lịch sử event | Compaction giữ trạng thái mới nhất theo key, không bảo đảm lưu mọi phiên bản |
| Replay luôn an toàn vì Kafka không gửi trùng | Replay chủ động đọc lại record; tác dụng phụ bên ngoài có thể bị thực thi lặp |

## 11. Tình huống thực hành: thêm subscriber phân tích mà không ảnh hưởng thanh toán

Một hệ thống đang có topic `orders.events` với ba partition. Dịch vụ thanh toán chạy hai replica trong group `billing-service`. Nhóm dữ liệu muốn bổ sung một subscriber để dựng báo cáo doanh thu từ dữ liệu lịch sử.

Có thể triển khai theo trình tự:

1. Tạo consumer phân tích với group ID riêng, ví dụ `analytics-rebuild`.
2. Cấu hình bắt đầu từ earliest để đọc phần dữ liệu còn lưu trong topic.
3. Ghi kết quả vào schema hoặc bảng báo cáo mới, không gọi lại API thanh toán.
4. Theo dõi partition, offset và lag của group phân tích trong khi group thanh toán tiếp tục hoạt động.
5. Đối chiếu số đơn hàng, tổng doanh thu và các trường hợp hủy/hoàn tiền với nguồn dữ liệu kiểm chứng.
6. Khi dữ liệu đạt yêu cầu, chuyển báo cáo sang bảng mới và quyết định group phân tích sẽ tiếp tục tiêu thụ dữ liệu mới bằng chính group ID đó hay kết thúc lượt rebuild.

Trong tình huống này, group ID riêng giúp subscriber phân tích có tiến độ độc lập. Kafka không cần producer gửi lại sự kiện và dịch vụ thanh toán không phải reset offset hay dừng xử lý.

Nếu retention không còn bao phủ toàn bộ lịch sử cần dựng, Kafka không thể cung cấp phần record đã bị xóa. Khi đó phải kết hợp nguồn lưu trữ khác hoặc một quy trình snapshot/backfill đã được thiết kế từ trước.

## 12. Checklist thiết kế pub/sub và replay

- [ ] Mỗi ứng dụng subscriber có group ID riêng khi cần tiến độ độc lập.
- [ ] Các replica của cùng một ứng dụng dùng chung group ID để chia partition.
- [ ] Group ID ổn định qua các lần khởi động và được tách theo môi trường.
- [ ] Đã xác định retention đủ cho thời gian gián đoạn và nhu cầu replay.
- [ ] Đã phân biệt topic delete với compact và hiểu giới hạn lịch sử của compacted topic.
- [ ] Hiểu committed offset và phạm vi áp dụng của auto.offset.reset.
- [ ] Có quy trình xem trước và thực thi khi reset offset.
- [ ] Consumer xử lý idempotent hoặc có deduplication khi record có thể được đọc lại.
- [ ] Replay có kho đích, giới hạn tốc độ và cách đối chiếu kết quả.
- [ ] Theo dõi lag theo từng group và từng partition.

## Kết luận

Pub/sub trong Kafka cho phép một topic phục vụ nhiều subscriber độc lập. Các consumer cùng group chia partition để mở rộng một ứng dụng; các group khác nhau có offset riêng và có thể đọc cùng luồng theo nhịp riêng. Khả năng đọc lại đến từ việc Kafka lưu giữ log theo retention, kết hợp với cơ chế offset và replay của consumer group. Muốn sử dụng an toàn, cần chọn group ID đúng mục đích, hiểu giới hạn retention, quản lý commit offset và bảo vệ tác dụng phụ khi xử lý lại dữ liệu.

