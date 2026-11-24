# Hàng đợi, chủ đề và mô hình điểm tới điểm

Trong một ứng dụng đơn lẻ, các thành phần thường gọi trực tiếp phương thức của nhau. Khi hệ thống được tách thành nhiều dịch vụ, cách giao tiếp trực tiếp khiến bên gửi phải biết bên nhận đang chạy ở đâu và có sẵn sàng hay không. Truyền tin bất đồng bộ giải quyết vấn đề này bằng cách để dịch vụ gửi tạo thông điệp, đưa thông điệp đến một địa chỉ logic, rồi để dịch vụ nhận xử lý khi có thể.

Spring Cloud Stream cung cấp mô hình lập trình hướng hàm để xây dựng các ứng dụng như vậy. Ứng dụng khai báo hàm phát sinh, biến đổi hoặc tiêu thụ thông điệp; binding nối đầu vào và đầu ra của hàm với destination; binder kết nối destination đó với hệ thống truyền tin như Kafka, RabbitMQ hoặc Pulsar. Để thiết kế luồng đúng, trước hết cần hiểu hàng đợi, chủ đề và hai cách phân phối phổ biến: điểm tới điểm và phát hành/đăng ký.

## 1. Thông điệp, destination và broker

Một **thông điệp** thường gồm phần payload và metadata. Payload chứa dữ liệu nghiệp vụ, chẳng hạn mã đơn hàng và tổng tiền. Metadata có thể chứa mã sự kiện, thời điểm phát sinh, khóa phân vùng, kiểu nội dung hoặc thông tin truy vết. Không nên phụ thuộc vào metadata do broker tự sinh như thể đó là định danh nghiệp vụ ổn định.

**Destination** là tên logic mà ứng dụng dùng để gửi hoặc nhận thông điệp. Tùy binder, destination có thể ánh xạ đến topic, exchange, queue hoặc một tài nguyên tương ứng trên broker. Vì vậy, cùng một tên destination trong mã nguồn không có nghĩa là mọi broker đều có cùng cấu trúc vật lý.

**Broker** nhận thông điệp từ producer, lưu giữ hoặc định tuyến chúng theo cấu hình, rồi chuyển chúng đến consumer. Broker thường đảm nhiệm một số việc mà ứng dụng không nên tự xây dựng: lưu đệm khi consumer chậm, phân phối tải, xác nhận xử lý, lưu giữ thông điệp và chuyển thông điệp lỗi sang nơi cách ly.

Có thể hình dung luồng cơ bản như sau:

~~~text
Producer
   |
   | gửi message đến destination
   v
Broker
   |
   | lưu giữ / định tuyến / phân phối
   v
Consumer
   |
   | xử lý và xác nhận
   v
Hoàn tất hoặc thử lại / chuyển DLQ
~~~

Producer và consumer không cần gọi trực tiếp nhau. Producer chỉ cần biết destination và hợp đồng thông điệp; consumer có thể được triển khai, mở rộng hoặc khởi động lại độc lập.

## 2. Hàng đợi và mô hình điểm tới điểm

**Hàng đợi (queue)** là nơi chứa thông điệp đang chờ được xử lý. Producer gửi thông điệp vào hàng đợi; một hoặc nhiều consumer cùng đăng ký nhận từ hàng đợi đó. Khi nhiều consumer cùng cạnh tranh trên một hàng đợi, broker phân phối mỗi thông điệp cho một consumer trong nhóm xử lý. Cách tổ chức này thường được gọi là **competing consumers**.

Mô hình **điểm tới điểm (point-to-point, P2P)** mô tả mục tiêu phân phối: mỗi thông điệp được giao cho một bên xử lý logic. “Một bên” ở đây là một nhóm consumer của cùng một dịch vụ, không nhất thiết là một tiến trình hay một máy chủ duy nhất. Có thể chạy nhiều bản sao của dịch vụ để tăng năng lực xử lý; chúng cùng cạnh tranh trên một hàng đợi hoặc cùng tham gia một consumer group.

Ví dụ, dịch vụ đơn hàng gửi một sự kiện OrderCreated vào luồng xử lý kho. Nhiều instance của dịch vụ kho có thể cùng nhận thông điệp. Với mỗi thông điệp, chỉ một instance trong nhóm kho thực hiện công việc đặt trước hàng. Nếu hai instance cùng xử lý một bản sao của cùng thông điệp do cơ chế giao nhận lại, ứng dụng vẫn cần bảo vệ thao tác nghiệp vụ bằng tính idempotent.

~~~text
                    +--> Consumer kho A
Producer --> Queue -+--> Consumer kho B
                    +--> Consumer kho C

Mỗi message được phân cho một consumer trong nhóm.
~~~

Queue giúp tách thời điểm gửi khỏi thời điểm xử lý. Nếu dịch vụ kho tạm thời dừng, broker có thể giữ thông điệp để xử lý sau, trong giới hạn chính sách lưu giữ và dung lượng đã cấu hình. Khi consumer xác nhận thành công, broker hoặc hệ thống truyền tin ghi nhận tiến độ xử lý theo cơ chế của nó. Nếu consumer lỗi trước khi xác nhận, thông điệp có thể được giao lại.

Điều đó dẫn đến ba điểm cần thiết kế:

- **Xác nhận (acknowledgement):** xác định thời điểm một thông điệp được coi là đã xử lý. Xác nhận quá sớm có thể làm mất công việc khi tiến trình dừng giữa chừng; xác nhận quá muộn có thể gây giao lại.
- **Thử lại (retry):** xử lý lỗi tạm thời như dịch vụ phụ thuộc chưa sẵn sàng. Cần giới hạn số lần thử và cân nhắc khoảng chờ để tránh làm broker hoặc dịch vụ phụ thuộc quá tải.
- **Hàng đợi lỗi (dead-letter queue, DLQ):** cô lập thông điệp không thể xử lý sau chính sách thử lại, để điều tra và xử lý có kiểm soát thay vì lặp vô hạn.

Queue phù hợp với công việc cần được một nhóm xử lý hoàn thành, ví dụ gửi hóa đơn, tạo vận đơn hoặc cập nhật tồn kho. Nếu nhiều dịch vụ độc lập đều cần nhận cùng một sự kiện, chỉ một hàng đợi dùng chung thường không diễn tả đúng yêu cầu đó.

## 3. Chủ đề và mô hình phát hành/đăng ký

**Chủ đề (topic)** là một địa chỉ logic đại diện cho một loại luồng thông điệp, chẳng hạn orders.created hoặc payments.completed. Producer phát hành thông điệp lên chủ đề; các bên quan tâm đăng ký nhận thông điệp. Mô hình này thường được gọi là **phát hành/đăng ký (publish/subscribe, pub/sub)**.

Điểm quan trọng là mỗi bên đăng ký cần có tiến độ nhận độc lập. Ví dụ, sau khi đơn hàng được tạo:

- Dịch vụ kho cần đặt trước hàng.
- Dịch vụ thanh toán cần khởi tạo giao dịch.
- Dịch vụ phân tích cần ghi nhận sự kiện để tính chỉ số.

Ba dịch vụ đều cần biết một đơn hàng đã được tạo. Nếu chúng cùng cạnh tranh trên một queue duy nhất, mỗi thông điệp có thể chỉ đến một dịch vụ và hai dịch vụ còn lại sẽ không nhận được. Với pub/sub, mỗi dịch vụ có một subscription hoặc hàng đợi riêng; broker phân phối bản sao logic của thông điệp đến từng subscription.

~~~text
                         +--> Subscription kho --> Consumer kho
Producer --> Topic ------+--> Subscription thanh toán --> Consumer thanh toán
                         +--> Subscription phân tích --> Consumer phân tích

Mỗi subscription nhận luồng sự kiện độc lập.
~~~

Topic không có cùng cách triển khai ở mọi broker:

- **Kafka:** topic là log được chia thành partition. Consumer group có offset riêng để theo dõi tiến độ. Nhiều group đọc cùng topic một cách độc lập; các consumer trong cùng group chia nhau partition.
- **RabbitMQ:** producer thường gửi đến exchange; exchange định tuyến thông điệp đến các queue đã bind. Mỗi dịch vụ đăng ký có thể có queue riêng. Các consumer của cùng dịch vụ cùng đọc queue đó để chia tải.
- **Pulsar:** producer ghi vào topic; consumer đọc thông qua subscription. Kiểu subscription quyết định cách nhiều consumer phối hợp, ví dụ Exclusive, Failover, Shared hoặc Key_Shared.

Vì vậy, khi nói “đăng ký một topic”, cần xác định cả broker và subscription/group cụ thể. Tên topic chỉ xác định luồng; subscription hoặc consumer group xác định tiến độ và cách phân phối cho một nhóm người nhận.

## 4. So sánh P2P và pub/sub

| Tiêu chí | Điểm tới điểm (P2P) | Phát hành/đăng ký (pub/sub) |
|---|---|---|
| Mục tiêu | Một nhóm xử lý hoàn thành mỗi thông điệp | Nhiều nhóm độc lập cùng nhận một sự kiện |
| Người nhận | Một consumer trong nhóm xử lý | Mỗi subscription/group có luồng nhận riêng |
| Mở rộng | Thêm consumer vào cùng queue/group để chia tải | Thêm subscription/group để thêm bên nhận; thêm consumer trong group để chia tải |
| Ví dụ | Đặt trước hàng, gửi hóa đơn | Đơn hàng mới được kho, thanh toán và phân tích cùng quan sát |
| Rủi ro thiết kế | Giao lại có thể khiến thao tác bị thực hiện nhiều lần | Các subscription có thể xử lý cùng sự kiện ở thời điểm khác nhau |

P2P và pub/sub là ngữ nghĩa giao tiếp ở mức ứng dụng. Không nên đồng nhất P2P với một loại broker hoặc cho rằng cứ có tên topic là hệ thống tự động phát tán đến mọi consumer. Chẳng hạn, Kafka dùng topic cùng một consumer group để tạo hành vi chia tải gần với P2P; hai consumer group khác nhau trên cùng topic tạo hành vi pub/sub. Với RabbitMQ, nhiều consumer cùng đọc một queue là competing consumers; nhiều queue được bind vào exchange có thể tạo fan-out đến các dịch vụ độc lập.

## 5. Biểu diễn mô hình bằng Spring Cloud Stream

Spring Cloud Stream tách logic xử lý khỏi chi tiết kết nối broker:

- **Supplier** tạo dữ liệu hoặc sự kiện để phát đi.
- **Function** nhận dữ liệu, biến đổi hoặc tạo kết quả đầu ra.
- **Consumer** nhận dữ liệu và thực hiện tác vụ, thường không có đầu ra.
- **Binding** nối cổng vào/ra của hàm với một destination.
- **Binder** chuyển thao tác gửi/nhận của binding thành thao tác phù hợp với Kafka, RabbitMQ, Pulsar hoặc broker được hỗ trợ khác.

Trong mô hình hàm, tên binding mặc định được tạo từ tên hàm và hướng dữ liệu. Ví dụ, hàm validateOrder có đầu vào validateOrder-in-0 và đầu ra validateOrder-out-0. Thuộc tính destination đặt tên luồng mà binding kết nối đến; thuộc tính group xác định nhóm consumer cho binding đầu vào.

Ví dụ một hàm kiểm tra đơn hàng và phát kết quả đã xác thực:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderValidationFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> {
            // Kiểm tra dữ liệu và tạo sự kiện kết quả.
            return new OrderValidated(event.orderId(), event.customerId());
        };
    }
}

record OrderCreated(String orderId, String customerId) {}

record OrderValidated(String orderId, String customerId) {}
~~~

Cấu hình binding cho hàm trên:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
        validateOrder-out-0:
          destination: orders.validated
~~~

Binding đầu vào nhận sự kiện từ orders.created; binding đầu ra phát kết quả lên orders.validated. Binder quyết định cách ánh xạ hai destination này sang tài nguyên của broker đang được cấu hình. Mã xử lý không cần trực tiếp tạo KafkaProducer, RabbitTemplate hay client Pulsar.

Một consumer xử lý sự kiện đã xác thực có thể được khai báo như sau:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class InventoryFunctions {

    @Bean
    Consumer<Message<OrderValidated>> reserveInventory() {
        return message -> {
            OrderValidated event = message.getPayload();
            // Đặt trước hàng cho event.orderId().
        };
    }
}
~~~

Và cấu hình đầu vào:

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.validated
          group: inventory-service
~~~

Group inventory-service thể hiện một nhóm xử lý logic. Khi triển khai nhiều instance của dịch vụ kho với cùng cấu hình group, chúng tham gia cùng nhóm và chia tải theo khả năng của binder/broker. Nếu bỏ qua group, một số binder có thể tạo consumer hoặc subscription ẩn danh; hành vi và khả năng khôi phục tiến độ có thể khác với nhóm có tên. Với consumer nghiệp vụ cần tiến độ ổn định, hãy đặt group rõ ràng và kiểm tra hành vi của binder đang dùng.

## 6. Destination và group được ánh xạ ra sao?

### Kafka binder

Với Kafka, destination thường ánh xạ đến topic. Group ánh xạ đến consumer group:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.created
          group: inventory-service
~~~

Các instance cùng dùng group inventory-service chia nhau partition của topic orders.created. Mỗi record trong partition được một consumer thuộc group đó xử lý tại một thời điểm theo cơ chế phân công của Kafka. Một group khác, ví dụ billing-service, có offset riêng và có thể đọc cùng các record để xử lý thanh toán. Đây là cách tạo hai luồng xử lý độc lập trên cùng topic.

Nếu chạy nhiều consumer hơn số partition, một số consumer trong group sẽ không được gán partition và không tăng thêm mức song song hữu ích. Muốn tăng khả năng xử lý song song, cần xem xét số partition, tải từng partition và khả năng xử lý của từng instance.

### RabbitMQ binder

Với RabbitMQ, destination của binding thường đại diện cho exchange. Consumer group xác định queue gắn với exchange cho nhóm đó. Nhiều instance cùng group cạnh tranh đọc queue của nhóm; một group khác có queue riêng để nhận cùng loại thông điệp.

Ví dụ, exchange orders.created có thể định tuyến đến queue của inventory-service và queue của billing-service. Các consumer kho cùng đọc queue kho; các consumer thanh toán cùng đọc queue thanh toán. Exchange type và routing key quyết định thông điệp được định tuyến đến queue nào, vì vậy cần cấu hình và kiểm tra chúng theo yêu cầu nghiệp vụ.

### Pulsar binder

Với Pulsar, destination ánh xạ đến topic và group liên quan đến subscription. Subscription type quyết định cách consumer chia sẻ thông điệp. Shared phù hợp với nhiều consumer cùng chia tải; Exclusive giới hạn một consumer hoạt động; Failover cung cấp consumer dự phòng; Key_Shared phân phối theo khóa để giữ các thông điệp cùng khóa trên cùng consumer trong phạm vi cơ chế của Pulsar.

Các ánh xạ trên giúp hiểu ý nghĩa chung của destination và group. Khi triển khai, cần kiểm tra tài liệu và cấu hình của đúng phiên bản binder vì tên thuộc tính và một số mặc định có thể khác nhau giữa các binder.

## 7. Partition, khóa và thứ tự xử lý

Một luồng có thể được chia thành nhiều **partition** để tăng khả năng ghi và đọc song song. Trong Kafka, record được ghi vào một partition; consumer group phân công các partition cho thành viên. Thứ tự được đảm bảo trong một partition, không phải trên toàn bộ topic khi có nhiều partition.

Producer thường chọn partition dựa trên key. Nếu mọi sự kiện của cùng một đơn hàng dùng orderId làm key, chúng có cơ hội đi vào cùng partition và được đọc theo thứ tự trong partition đó. Nếu không có key phù hợp hoặc key thay đổi giữa các sự kiện, hai sự kiện liên quan có thể được xử lý song song và đến đích theo thứ tự khác nhau.

Không nên giả định mọi broker đều cung cấp cùng một bảo đảm thứ tự. RabbitMQ có thể thay đổi thứ tự quan sát được khi nhiều consumer cùng đọc, khi thông điệp được thử lại hoặc khi định tuyến đến nhiều queue. Pulsar có các kiểu subscription và chính sách phân phối theo khóa riêng. Nếu nghiệp vụ yêu cầu tuần tự, hãy xác định rõ phạm vi cần tuần tự hóa (theo đơn hàng, khách hàng hay toàn hệ thống), chọn key và kiểu subscription phù hợp, rồi kiểm thử với cấu hình triển khai thực tế.

## 8. Hợp đồng và schema của thông điệp

Queue hay topic chỉ vận chuyển thông điệp; chúng không tự bảo đảm producer và consumer hiểu cùng một cấu trúc dữ liệu. Hai phía cần thống nhất **hợp đồng thông điệp**:

- Tên sự kiện và ý nghĩa nghiệp vụ, ví dụ OrderCreated là sự kiện đã xảy ra, không phải yêu cầu tạo đơn.
- Các trường bắt buộc, kiểu dữ liệu, đơn vị đo và quy tắc null.
- Định danh sự kiện ổn định để phát hiện giao lại, cùng định danh thực thể như orderId.
- Thời điểm xảy ra sự kiện và thông tin tương quan để truy vết luồng xử lý.
- Quy tắc tương thích khi thêm, đổi tên hoặc bỏ trường.

Ưu tiên thay đổi tương thích ngược: thêm trường tùy chọn có giá trị mặc định hợp lý thường an toàn hơn đổi kiểu hoặc đổi nghĩa trường đang được dùng. Khi cần thay đổi không tương thích, cân nhắc phiên bản schema hoặc sự kiện mới và có kế hoạch chuyển đổi consumer. Không dùng tên class Java nội bộ làm hợp đồng duy nhất giữa các dịch vụ có vòng đời triển khai độc lập.

## 9. Giao nhận, lỗi và tính idempotent

Broker có thể giao lại một thông điệp nếu consumer đã thực hiện một phần công việc nhưng chưa xác nhận, hoặc nếu kết nối bị gián đoạn tại thời điểm xác nhận. Vì vậy, mô hình at-least-once thường dẫn đến khả năng một sự kiện được quan sát nhiều lần. Consumer nên xử lý lặp an toàn bằng cách lưu eventId đã xử lý, dùng khóa duy nhất ở cơ sở dữ liệu hoặc thiết kế thao tác cập nhật có tính idempotent.

At-most-once giảm nguy cơ xử lý lặp nhưng có thể mất thông điệp nếu xác nhận trước khi công việc hoàn tất. Exactly-once là bảo đảm phức tạp, phụ thuộc vào broker, transaction, phạm vi lưu trạng thái và cách thực hiện side effect. Một cấu hình broker đơn lẻ không thể bảo đảm rằng mọi thao tác bên ngoài như gọi API thanh toán hoặc gửi email chỉ xảy ra đúng một lần.

Một chính sách lỗi thực tế thường gồm:

1. Thử lại lỗi tạm thời với số lần và khoảng chờ hữu hạn.
2. Chuyển thông điệp không thể xử lý sang DLQ hoặc cơ chế cách ly tương đương.
3. Ghi log có eventId, destination, group và nguyên nhân lỗi để truy vết.
4. Có quy trình kiểm tra, sửa dữ liệu và phát lại thông điệp từ DLQ.
5. Theo dõi độ trễ, số lượng thông điệp tồn đọng, tỷ lệ retry và số thông điệp vào DLQ.

Không nên dùng retry để che giấu lỗi dữ liệu vĩnh viễn. Một thông điệp sai schema hoặc vi phạm quy tắc nghiệp vụ cần được cách ly và xử lý theo quy trình rõ ràng.

## 10. Kiểm thử và chọn mô hình phù hợp

Kiểm thử nên xác minh cả logic hàm lẫn ngữ nghĩa phân phối:

- **Kiểm thử hàm:** truyền một payload mẫu vào Function hoặc Consumer và xác nhận kết quả nghiệp vụ. Kiểm tra cả dữ liệu hợp lệ, dữ liệu thiếu trường và trường hợp xử lý lặp.
- **Kiểm thử binding:** dùng test binder của Spring Cloud Stream để gửi thông điệp vào binding và đọc kết quả từ binding đầu ra. Kiểm tra tên binding, payload và header quan trọng.
- **Kiểm thử tích hợp:** chạy broker phù hợp trong môi trường kiểm thử, chẳng hạn bằng Testcontainers, để xác minh group, queue, partition, routing, ack, retry và DLQ. Test binder không thay thế được kiểm thử hành vi riêng của Kafka, RabbitMQ hoặc Pulsar.
- **Kiểm thử triển khai:** chạy nhiều instance cùng group để xác nhận chia tải; chạy hai group khác nhau để xác nhận mỗi bên nhận được luồng độc lập.

Khi chọn mô hình, hãy bắt đầu từ câu hỏi nghiệp vụ:

| Nhu cầu | Mô hình nên xem xét |
|---|---|
| Một dịch vụ cần xử lý mỗi công việc; có thể chạy nhiều bản sao để chia tải | Queue hoặc topic cùng một consumer group |
| Nhiều dịch vụ độc lập đều cần phản ứng với cùng sự kiện | Topic với subscription/group riêng cho từng dịch vụ |
| Cần thứ tự theo một thực thể | Partition/key hoặc subscription theo khóa, tùy broker |
| Consumer có thể dừng lâu và cần tiếp tục từ tiến độ đã lưu | Group/subscription có tên và chính sách lưu giữ phù hợp |
| Cần cách ly thông điệp lỗi để điều tra | Retry hữu hạn kết hợp DLQ |

Trước khi phát hành, hãy xác nhận destination thực tế mà binder tạo ra, group/subscription của từng dịch vụ, cách broker phân phối khi tăng số instance, chính sách lưu giữ và xác nhận, cũng như khả năng tương thích schema. Những kiểm tra này giúp tránh lỗi thường gặp: nhiều dịch vụ vô tình dùng chung một nhóm nên chỉ một dịch vụ nhận được sự kiện, hoặc mỗi instance lại dùng group riêng khiến mọi instance đều xử lý cùng một sự kiện.

Khi nắm rõ queue, topic và group, ta có thể chọn đúng ngữ nghĩa giao tiếp rồi dùng binding của Spring Cloud Stream để triển khai. Queue và group phù hợp khi cần chia tải một công việc; topic cùng nhiều subscription/group phù hợp khi nhiều dịch vụ cần quan sát cùng một sự kiện. Binder giúp giữ mã xử lý gọn, còn quyết định về phân phối, thứ tự, schema và giao nhận vẫn cần được thiết kế theo yêu cầu của hệ thống.
