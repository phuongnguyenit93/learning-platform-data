# Thứ tự theo khóa và giới hạn khi xử lý bất đồng bộ

Trong hệ thống xử lý sự kiện, thứ tự message có thể mang ý nghĩa nghiệp vụ. Ví dụ, một tài khoản được tạo trước khi số dư được cập nhật; một đơn hàng phải được xác nhận trước khi phát sự kiện giao hàng. Nếu các message liên quan bị xử lý sai thứ tự, trạng thái cuối cùng có thể không chính xác dù từng message đều hợp lệ.

Spring Cloud Stream hỗ trợ partitioning để phân phối message theo khóa. Những message có cùng partition key được đưa về cùng partition theo chiến lược của binder, giúp giữ thứ tự ở phạm vi partition mà broker hỗ trợ. Tuy nhiên, partitioning không tạo ra thứ tự toàn cục cho toàn bộ destination và cũng không tự bảo đảm thứ tự hoàn tất khi ứng dụng xử lý bất đồng bộ. Muốn thiết kế đúng, cần hiểu cả cách chọn khóa, cách broker phân phối partition và cách consumer thực thi công việc.

## 1. Partition và thứ tự message

Partition là một phần có thứ tự của destination. Với Kafka, một topic có thể gồm nhiều partition; mỗi partition lưu các record theo thứ tự append. Consumer đọc các record trong partition theo offset. Nhiều partition cho phép xử lý song song, nhưng không có một thứ tự tổng thể giữa các partition.

Ví dụ, luồng orders.events có ba partition:

~~~text
orders.events
  partition 0: A1 -> A2 -> A3
  partition 1: B1 -> B2 -> B3
  partition 2: C1 -> C2 -> C3
~~~

Consumer có thể đọc ba partition đồng thời. Thứ tự A1 trước A2 trước A3 được duy trì trong partition 0; hệ thống không cam kết A1 phải được xử lý xong trước B1 ở partition 1. Nếu nghiệp vụ chỉ cần thứ tự cho từng khách hàng hoặc từng đơn hàng, ta có thể chọn khóa để mọi sự kiện của cùng thực thể đi vào cùng partition.

Partitioning giải quyết hai mục tiêu liên quan:

- **Thứ tự theo khóa:** những message cùng khóa được định tuyến về cùng partition, nhờ đó có thể xử lý tuần tự trong phạm vi partition.
- **Khả năng mở rộng:** các partition khác nhau có thể được xử lý song song bởi nhiều consumer.

Số partition là giới hạn song song hữu ích của một consumer group. Nếu topic có ba partition, tăng số consumer trong cùng group lên mười không tạo ra mười luồng xử lý độc lập cho topic đó; một số consumer sẽ không được gán partition.

## 2. Chọn partition key theo thực thể nghiệp vụ

Partition key là giá trị dùng để quyết định message thuộc partition nào. Khóa nên đại diện cho thực thể mà nghiệp vụ yêu cầu giữ thứ tự:

| Nghiệp vụ | Khóa thường phù hợp | Lý do |
|---|---|---|
| Cập nhật trạng thái đơn hàng | orderId | Các thay đổi của cùng đơn hàng cần được xử lý theo thứ tự |
| Ghi sổ giao dịch tài khoản | accountId | Các giao dịch của một tài khoản cần được tuần tự hóa |
| Cập nhật hồ sơ khách hàng | customerId | Các thay đổi của cùng khách hàng không nên chạy đua |
| Xử lý tồn kho theo SKU | sku | Các cập nhật cùng sản phẩm cần được phối hợp |

Không nên chọn một khóa ngẫu nhiên cho từng message nếu mục tiêu là giữ thứ tự theo thực thể. Khóa ngẫu nhiên sẽ phân tán các sự kiện của cùng thực thể sang nhiều partition. Timestamp cũng không phải lựa chọn thay thế tự động: hai producer có thể tạo timestamp lệch nhau, đồng hồ có thể không đồng bộ và timestamp không bảo đảm thứ tự broker nhận message.

Khóa cần ổn định, có mặt trên mọi message thuộc cùng luồng nghiệp vụ và có cách biểu diễn nhất quán. Nếu customerId đôi khi null hoặc được chuẩn hóa khác nhau giữa producer, cùng một khách hàng có thể bị chia thành nhiều nhóm khóa. Hãy xác thực khóa trước khi phát và thống nhất quy tắc chuẩn hóa.

## 3. Cấu hình partitioning ở producer

Spring Cloud Stream cung cấp thuộc tính partitioning chung ở cấp producer. Ví dụ, mọi sự kiện của cùng khách hàng dùng customerId làm partition key:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
~~~

Trong cấu hình:

- **partition-key-expression** là biểu thức SpEL dùng để lấy khóa từ message. payload.customerId đọc trường customerId của payload.
- **partition-count** là số partition mà producer dùng trong phép chọn partition.
- **destination** xác định luồng logic mà message được phát đến.

Với message có payload là OrderEvent, biểu thức có thể là payload.orderId hoặc payload.accountId tùy yêu cầu thứ tự. Nếu dùng header làm khóa, biểu thức có thể tham chiếu header, chẳng hạn headers['partitionKey']; producer phải bảo đảm header đó tồn tại và có kiểu giá trị phù hợp.

Spring Cloud Stream có thể dùng partition key extractor và partition selector tùy chỉnh khi biểu thức mặc định không đáp ứng yêu cầu. Có thể khai báo bean extractor/selector và tham chiếu bằng tên trong cấu hình producer. Chỉ nên tùy chỉnh khi có quy tắc phân vùng rõ ràng; nhiều producer phải dùng cùng một thuật toán và cùng cách chuẩn hóa khóa để một thực thể không bị chuyển sang partition khác.

partition-count phải tương thích với số partition thực tế mà binder/broker hỗ trợ. Với Kafka, topic cần có đủ partition; cấu hình producer không tự làm cho topic hiện hữu tăng partition trong mọi chế độ triển khai. Kiểm tra topic trước khi phát hành.

## 4. Cách khóa được ánh xạ thành partition

Về khái niệm, producer thực hiện hai bước:

1. Trích xuất partition key từ payload hoặc header.
2. Đưa key qua partition selector để chọn một partition trong phạm vi partition count.

Với selector dựa trên hash, những lần phát cùng một khóa sẽ chọn cùng partition khi thuật toán và số partition không đổi:

~~~text
partitionKey = customerId
partition = selector(partitionKey, partitionCount)

customer-10 -> partition 2
customer-20 -> partition 0
customer-10 -> partition 2
customer-30 -> partition 1
~~~

Các số trong sơ đồ chỉ minh họa. Không tự giả định partition ID luôn bằng hashCode modulo partitionCount; thuật toán chính xác phụ thuộc selector, binder và phiên bản. Điều cần giữ là mọi producer tham gia cùng luồng phải áp dụng cùng quy tắc để các sự kiện của một khóa được định tuyến nhất quán.

Nếu dùng partition selector tùy chỉnh, kiểm thử các trường hợp khóa null, khóa rỗng, Unicode, giá trị âm và khóa có phân bố lệch. Tránh thuật toán tạo ra partition không hợp lệ hoặc làm phần lớn traffic dồn vào một partition.

Partition key chỉ quyết định nơi message được ghi. Nếu hai producer cùng phát sự kiện cho một orderId tại cùng thời điểm, thứ tự broker nhận có thể khác thứ tự nghiệp vụ mà hai producer dự định. Muốn có thứ tự nghiệp vụ xác định, cần một nơi điều phối hoặc sequence/version được cấp nhất quán cho aggregate; partitioning không tự sắp xếp message theo timestamp hay sequence.

## 5. Consumer group và phân phối partition

Các consumer trong cùng group thường chia nhau xử lý partition của một destination. Với Kafka, broker và Kafka consumer group coordinator phân công partition cho các consumer thành viên. Một partition tại một thời điểm chỉ được gán cho một consumer trong cùng group, nhưng các group khác có thể đọc độc lập cùng topic.

~~~text
Topic orders.events: 6 partitions

Consumer group: order-projection
  consumer A <- partitions 0, 1
  consumer B <- partitions 2, 3
  consumer C <- partitions 4, 5

Consumer group: billing
  consumer D <- partitions 0, 1, 2
  consumer E <- partitions 3, 4, 5
~~~

Ví dụ cho thấy hai dịch vụ có thể đọc cùng topic bằng group khác nhau. Trong từng group, partition được chia cho các instance; mỗi group có tiến độ tiêu thụ riêng. Nếu các instance của cùng dịch vụ vô tình dùng group khác nhau, chúng có thể nhận lại toàn bộ luồng độc lập thay vì chia tải.

Với Kafka binder, consumer group assignment là cơ chế native của Kafka. Khi số instance thay đổi, Kafka có thể thực hiện rebalance và phân công lại partition. Với mô hình partitioned consumer chung của Spring Cloud Stream, các thuộc tính instance-count, instance-index và consumer.partitioned có thể được dùng để mô tả tổng số instance và chỉ số instance; cách áp dụng cụ thể phụ thuộc binder. Không trộn cơ chế phân công của binder với cấu hình instance-level mà không kiểm tra tài liệu phiên bản đang sử dụng.

## 6. Thứ tự trong partition không phải thứ tự hoàn tất

Broker có thể giao message theo thứ tự trong partition, nhưng ứng dụng vẫn có thể hoàn tất xử lý sai thứ tự nếu chạy nhiều tác vụ bất đồng bộ.

Ví dụ, consumer nhận tuần tự:

~~~text
Message:  A1 -> A2 -> A3
Bắt đầu:  A1    A2    A3
Hoàn tất: A2    A3    A1
~~~

Nếu A1 cập nhật trạng thái đơn hàng thành PAID, còn A2 cập nhật thành SHIPPED, việc A2 hoàn tất trước A1 có thể khiến trạng thái cuối cùng bị ghi đè sai. Đây là lỗi ở tầng thực thi của ứng dụng, dù broker vẫn giao message đúng thứ tự.

Một số nguyên nhân thường gặp:

- Dùng flatMap với các tác vụ I/O bất đồng bộ có thời gian hoàn tất khác nhau.
- Dùng thread pool hoặc executor chung để xử lý nhiều message đồng thời.
- Gọi API ngoài hoặc cơ sở dữ liệu với độ trễ không ổn định.
- Commit offset hoặc xác nhận message trước khi side effect hoàn tất.
- Có nhiều consumer hoặc nhiều subscription cùng cập nhật một thực thể mà không có khóa đồng bộ.

Muốn bảo toàn thứ tự, phải quản lý cả thứ tự nhận, thứ tự bắt đầu xử lý, thứ tự hoàn tất và thời điểm commit/acknowledgement.

## 7. Tuần tự hóa xử lý bằng Reactor

Trong một pipeline reactive, concatMap xử lý lần lượt từng phần tử: publisher của phần tử hiện tại hoàn tất trước khi phần tử tiếp theo được xử lý. Ví dụ:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record OrderEvent(String orderId, String status, long sequence) {}

record OrderResult(String orderId, String status, long sequence) {}

@Configuration
class OrderedOrderFunctions {

    private Mono<OrderResult> applyOrderEvent(OrderEvent event) {
        // Thay bằng thao tác nghiệp vụ bất đồng bộ thực tế.
        return Mono.just(new OrderResult(
                event.orderId(), event.status(), event.sequence()));
    }

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processInOrder() {
        return events -> events.concatMap(this::applyOrderEvent);
    }
}
~~~

concatMap giữ thứ tự phát của luồng đầu vào ở luồng kết quả, nhưng chỉ xử lý một tác vụ tại một thời điểm trong pipeline đó. Cách này đơn giản và an toàn khi thứ tự toàn luồng quan trọng, đổi lại thông lượng bị giới hạn bởi tác vụ chậm nhất.

flatMap cho phép nhiều tác vụ chạy đồng thời và có thể phát kết quả theo thứ tự hoàn tất. Nó phù hợp khi các message độc lập hoặc nghiệp vụ không yêu cầu thứ tự. Không thay concatMap bằng flatMap chỉ để tăng thông lượng nếu các message của cùng thực thể có phụ thuộc trạng thái.

Reactor còn có flatMapSequential: nó có thể subscribe và chạy nhiều tác vụ đồng thời nhưng giữ thứ tự phát kết quả theo thứ tự phần tử đầu vào. Điều này chỉ sắp xếp lại tín hiệu đầu ra; side effect bên trong các tác vụ vẫn có thể xảy ra không đúng thứ tự. Nếu các tác vụ cùng cập nhật một aggregate và bản thân thao tác ghi phải tuần tự, flatMapSequential không thay thế concatMap hoặc cơ chế đồng bộ theo khóa.

Nếu muốn chạy song song giữa các khóa nhưng giữ thứ tự trong từng khóa, có thể phân vùng theo key ở tầng broker và xử lý tuần tự từng partition đó, hoặc thiết kế bộ điều phối theo key. Cách dùng groupBy rồi concatMap trong Reactor cần giới hạn concurrency, quản lý số lượng group và buffer; không nên áp dụng một cách máy móc cho số khóa không giới hạn.

## 8. Ví dụ bất đồng bộ làm đảo thứ tự

Giả sử service cập nhật trạng thái đơn hàng bằng lời gọi I/O:

~~~java
Flux<OrderResult> unsafe =
        events.flatMap(event ->
                orderService.updateAsync(event));
~~~

flatMap có thể bắt đầu xử lý A1, A2 và A3 gần như đồng thời. Nếu A2 hoàn tất trước A1, kết quả được phát ra trước A1. Nếu mỗi tác vụ ghi cùng một bản ghi đơn hàng, trạng thái cuối có thể phụ thuộc vào thứ tự hoàn tất thay vì thứ tự sự kiện.

Khi cần tuần tự hóa toàn bộ pipeline:

~~~java
Flux<OrderResult> ordered =
        events.concatMap(event ->
                orderService.updateAsync(event));
~~~

Trong trường hợp chỉ cần thứ tự theo orderId, cần chia tải sao cho mọi sự kiện cùng orderId đi vào cùng partition và đảm bảo xử lý tuần tự trong partition đó. Các partition khác vẫn có thể chạy song song. Nếu một partition dùng nhiều thread xử lý bất đồng bộ, thứ tự hoàn tất vẫn có thể bị đảo; phải giữ một chuỗi xử lý tuần tự cho partition hoặc khóa theo thực thể.

## 9. Thứ tự và giới hạn theo từng broker

Partitioning là khái niệm chung, nhưng ngữ nghĩa vật lý của từng broker khác nhau:

| Broker | Đơn vị có thứ tự | Cách giữ thứ tự theo khóa | Giới hạn cần nhớ |
|---|---|---|---|
| Kafka | Record trong một partition | Dùng record key/partition key ổn định để cùng khóa vào cùng partition | Không có thứ tự giữa các partition; consumer xử lý song song có thể hoàn tất sai thứ tự |
| RabbitMQ | Message trong một queue theo thứ tự broker đưa vào queue | Dùng exchange/routing key và queue được phân vùng theo khóa hoặc shard | Nhiều consumer, prefetch, requeue và xử lý bất đồng bộ có thể làm thứ tự hoàn tất khác thứ tự nhận |
| Pulsar | Message trong partition của topic; semantics phụ thuộc subscription | Dùng message key và kiểu subscription hỗ trợ phân phối theo key | Key_Shared hỗ trợ cùng key đến cùng consumer theo cơ chế của Pulsar; thứ tự và redelivery còn phụ thuộc cấu hình |

### Kafka

Kafka bảo đảm thứ tự record trong một partition theo offset. Nếu mọi sự kiện của một orderId dùng cùng record key, chúng có thể được đọc theo thứ tự trong partition đó. Một consumer group chia partition cho các consumer, nhưng không tạo thứ tự toàn cục giữa các partition. Khi producer dùng retry hoặc gửi bất đồng bộ, cần kiểm tra cấu hình producer để bảo toàn thứ tự gửi theo yêu cầu; không suy luận chỉ từ partition key.

Tăng số partition của topic có thể làm thay đổi phép ánh xạ key sang partition đối với producer dùng hash modulo số partition. Các message cũ của một key vẫn nằm ở partition cũ, còn message mới có thể sang partition khác. Nếu cần thứ tự xuyên suốt trong quá trình tăng partition, hãy lập kế hoạch migration, drain luồng cũ hoặc dùng version/shard strategy có kiểm soát.

### RabbitMQ

RabbitMQ định tuyến message từ exchange đến queue. Một queue cung cấp thứ tự enqueue, nhưng khi có nhiều consumer, prefetch lớn, acknowledgement bất đồng bộ hoặc message bị requeue, thứ tự xử lý hoàn tất có thể khác thứ tự trong queue. Muốn giữ thứ tự theo khóa, cần thiết kế routing và queue shard sao cho cùng khóa đi vào cùng queue, đồng thời kiểm soát số consumer và cách xác nhận.

Không giả định chỉ khai báo một partition key trong ứng dụng sẽ tự động tạo ra đúng mô hình queue mong muốn cho mọi cấu hình Rabbit binder. Kiểm tra cách binder tạo exchange, queue, routing key và dead-letter resource.

### Pulsar

Pulsar hỗ trợ partitioned topic và message key. Subscription type ảnh hưởng đến cách consumer nhận message. Với Key_Shared, message có cùng key được phân phối đến cùng consumer theo cơ chế của Pulsar, hỗ trợ xử lý song song giữa các key. Cần kiểm tra batching, redelivery và acknowledgement vì chúng có thể ảnh hưởng đến thứ tự quan sát ở phía ứng dụng.

Không coi Shared và Key_Shared là tương đương. Shared phân phối message cho các consumer theo cơ chế chia tải, không cam kết cùng key luôn đến cùng consumer. Chọn subscription type theo yêu cầu về thứ tự và throughput.

## 10. Thay đổi partition count và phân bố tải

Partition count ảnh hưởng đến khả năng song song, kích thước lưu trữ, phân bố khóa và cách consumer được gán việc. Tăng partition có thể tăng throughput, nhưng không phải thay đổi miễn phí:

- Khóa có thể được ánh xạ sang partition khác nếu thuật toán phụ thuộc partition count.
- Các message cũ và mới của cùng khóa có thể nằm ở hai partition khác nhau.
- Consumer group có thể rebalance và tạm thời thay đổi năng lực xử lý.
- Broker cần thêm tài nguyên và metadata cho partition mới.
- Một số key có tần suất cao vẫn tập trung vào một partition, tạo hot partition.

Nếu một khách hàng tạo lượng sự kiện lớn hơn hẳn các khách hàng khác, chọn customerId làm key có thể khiến một partition nóng. Tăng số partition không giải quyết được một khóa đơn lẻ bị dồn vào cùng partition. Cần đánh giá lại đơn vị tuần tự hóa, chia shard theo thực thể con hoặc tách loại sự kiện, nhưng không được chia khóa nếu điều đó phá vỡ yêu cầu thứ tự nghiệp vụ.

Không thay đổi partition count chỉ dựa trên số consumer mong muốn. Hãy đo throughput, lag, phân bố key, độ trễ xử lý và dung lượng broker trước khi quyết định.

## 11. Xử lý lỗi, retry và thứ tự

Retry có thể làm thay đổi thứ tự quan sát. Ví dụ, A1 lỗi và được thử lại trong khi A2 đã được xử lý. Nếu A2 cập nhật trạng thái trước, sau đó A1 retry thành công, trạng thái có thể quay về giá trị cũ.

Một số cách hạn chế:

- Xử lý tuần tự trong phạm vi partition hoặc key nếu nghiệp vụ yêu cầu.
- Dùng sequence number hoặc version trên aggregate để phát hiện sự kiện cũ.
- Khi cập nhật dữ liệu, chỉ chấp nhận version mới hơn version đã lưu.
- Phân biệt lỗi tạm thời với lỗi không thể phục hồi; không retry vô hạn một message lỗi dữ liệu.
- Dùng DLQ và quy trình phát lại có kiểm soát; phát lại phải xem xét thứ tự các message phía sau.
- Thiết kế consumer idempotent để giao lại không tạo side effect trùng.

Ví dụ kiểm tra sequence:

~~~java
if (event.sequence() <= currentState.lastSequence()) {
    // Bỏ qua message cũ hoặc đã xử lý.
    return;
}

apply(event);
saveLastSequence(event.sequence());
~~~

Đây là pseudocode; thao tác kiểm tra và cập nhật version phải được thực hiện nguyên tử trong kho dữ liệu nếu nhiều tiến trình có thể cập nhật cùng aggregate. Sequence number giúp phát hiện message cũ, nhưng không tự khôi phục một message bị thiếu. Nếu phát hiện khoảng trống sequence, ứng dụng cần chờ, truy vấn lại hoặc đưa aggregate vào trạng thái cần đối soát.

## 12. Kiểm thử thứ tự theo khóa

Kiểm thử nên xác nhận cả partition key và thứ tự xử lý:

1. Gửi nhiều sự kiện cùng khóa với sequence tăng dần.
2. Gửi sự kiện của nhiều khóa khác nhau để xác nhận chúng có thể được xử lý song song.
3. Kiểm tra partition hoặc queue thực tế mà broker nhận message.
4. Mô phỏng consumer xử lý chậm để xem thứ tự hoàn tất.
5. Mô phỏng lỗi và retry để kiểm tra message phía sau có vượt qua message lỗi hay không.
6. Kiểm tra rebalance hoặc restart consumer trong lúc đang xử lý.
7. Thử thay đổi partition count ở môi trường kiểm thử và xác nhận kế hoạch migration.

Test binder của Spring Cloud Stream phù hợp để kiểm tra biểu thức lấy partition key, header và logic hàm ở cấp ứng dụng nếu test được cấu hình tương ứng. Tuy nhiên, test binder không chứng minh Kafka partition assignment, RabbitMQ routing hay Pulsar Key_Shared. Các bảo đảm đó cần integration test với binder và broker thật.

## 13. Quan sát thứ tự và tình trạng partition

Trong production, theo dõi:

- Consumer lag hoặc backlog theo partition/queue/subscription.
- Tỷ lệ message theo partition và dấu hiệu hot partition.
- Thời gian từ lúc nhận đến lúc hoàn tất xử lý.
- Số lần retry, message vào DLQ và thời gian nằm trong DLQ.
- Số lần rebalance, consumer không được gán partition và thay đổi concurrency.
- Sequence gap, sự kiện cũ bị bỏ qua và lỗi cập nhật version.

Log nên có aggregate key, eventId, sequence, partition (nếu có), consumer instance và thời điểm bắt đầu/kết thúc xử lý. Tránh chỉ ghi timestamp mà không có sequence hoặc event ID; timestamp không đủ để chứng minh thứ tự nghiệp vụ.

## 14. Checklist thiết kế

- Chọn partition key theo thực thể cần giữ thứ tự, chẳng hạn orderId hoặc accountId.
- Bảo đảm key luôn có giá trị và được chuẩn hóa giống nhau ở mọi producer.
- Cấu hình partition count phù hợp với broker và kế hoạch mở rộng.
- Dùng cùng quy tắc partition selection cho các producer cùng destination.
- Hiểu group và cách binder phân công partition cho consumer instance.
- Phân biệt thứ tự broker giao message với thứ tự ứng dụng hoàn tất xử lý.
- Dùng concatMap hoặc cơ chế tuần tự hóa theo partition/key khi cần.
- Kiểm soát retry, redelivery, acknowledgement và DLQ để tránh áp dụng sự kiện cũ sau sự kiện mới.
- Có event sequence/version và cập nhật trạng thái theo cách nguyên tử khi nghiệp vụ yêu cầu.
- Kiểm thử với broker thật, gồm lỗi, restart, rebalance và thay đổi partition count.

Partition key giúp các message của cùng một thực thể đi vào cùng vùng có thứ tự, trong khi các partition khác có thể chạy song song. Bảo đảm đó chỉ hữu ích khi producer chọn khóa nhất quán và consumer không làm đảo thứ tự trong quá trình xử lý bất đồng bộ. Thiết kế cần kết hợp partitioning, consumer concurrency, retry, version nghiệp vụ và kiểm thử broker để giữ đúng thứ tự mà hệ thống thực sự yêu cầu.
