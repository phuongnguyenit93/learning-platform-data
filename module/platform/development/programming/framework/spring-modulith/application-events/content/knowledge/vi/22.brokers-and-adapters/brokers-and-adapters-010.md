# Chọn broker phù hợp

*Lựa chọn message broker và adapter cho application event trong Spring Modulith*

Khi một application event cần đi từ ứng dụng Spring Modulith đến một tiến trình khác, nhóm phát phải chọn nơi tiếp nhận message và cách kết nối đến nơi đó. Message broker chịu trách nhiệm nhận, lưu giữ, định tuyến và phân phối message theo ngữ nghĩa của nền tảng. Adapter nối mô hình application event của Spring Modulith với API cụ thể của broker.

Chọn broker phù hợp là quyết định kiến trúc dựa trên cách consumer sử dụng event, yêu cầu thứ tự, khả năng replay, độ bền dữ liệu, thông lượng và năng lực vận hành của nhóm. Broker có nhiều tính năng nhất chưa chắc là lựa chọn tốt nhất; broker phù hợp là nền tảng đáp ứng được yêu cầu thực tế với độ phức tạp mà đội ngũ có thể duy trì.

## 1. Bắt đầu từ nhu cầu giao sự kiện

Trước khi so sánh sản phẩm, hãy xác định event được dùng để làm gì. Một event có thể thông báo cho nhiều hệ thống độc lập, kích hoạt một công việc cần worker xử lý, hoặc tạo thành luồng dữ liệu cần lưu giữ và đọc lại. Những nhu cầu này dẫn đến topology và lựa chọn broker khác nhau.

Ví dụ, khi module `orders` hoàn tất một đơn hàng:

- Dịch vụ phân tích cần đọc lại luồng sự kiện để dựng báo cáo.
- Dịch vụ hóa đơn cần nhận mỗi event một lần theo luồng xử lý riêng.
- Dịch vụ thông báo cần phân phối nhiều tác vụ gửi email cho các worker.

Ba nhu cầu này có thể dùng chung một hợp đồng nghiệp vụ `OrderCompleted`, nhưng cách lưu giữ và phân phối message có thể khác nhau. Có thể dùng một topic với nhiều consumer group, một exchange định tuyến đến nhiều queue, hoặc tách luồng event và hàng đợi công việc theo mục đích.

Hãy trả lời các câu hỏi sau trước khi chọn nền tảng:

1. Có bao nhiêu nhóm consumer độc lập? Một message cần đến tất cả nhóm hay chỉ một worker trong nhóm?
2. Consumer có cần đọc lại message cũ sau khi triển khai lại hoặc khôi phục dữ liệu không?
3. Thứ tự cần được bảo đảm toàn cục hay chỉ theo aggregate như `orderId`?
4. Lưu lượng trung bình, lưu lượng đỉnh, kích thước message và độ trễ mục tiêu là bao nhiêu?
5. Message phải được lưu trong bao lâu? Mất message có thể chấp nhận hay phải có cơ chế phục hồi?
6. Hệ thống cần retry, dead-letter, routing theo thuộc tính hay phân phối theo partition?
7. Nhóm đã có broker, kỹ năng vận hành, công cụ giám sát và quy trình xử lý sự cố nào?

Không nên chọn broker chỉ dựa trên benchmark thông lượng. Kết quả benchmark phụ thuộc cấu hình, kích thước message, số partition hoặc queue, số consumer, replication, độ bền ghi và mạng. Hãy đánh giá bằng workload gần với hệ thống thực tế.

## 2. So sánh các mô hình broker phổ biến

Các nền tảng thường gặp giải quyết những bài toán có phần giao nhau, nhưng mô hình lưu giữ và phân phối message khác nhau.

| Nền tảng / mô hình | Điểm mạnh thường gặp | Phù hợp khi | Cần cân nhắc |
|---|---|---|---|
| Apache Kafka | Log phân tán theo partition, retention, consumer group và khả năng replay | Luồng event lớn, nhiều consumer độc lập, cần đọc lại dữ liệu và xử lý theo thứ tự trong partition | Vận hành cluster, partition, replication, consumer lag và schema cần được quản lý tốt |
| RabbitMQ / AMQP | Exchange, routing key, binding, queue, acknowledgement và mô hình phân phối công việc linh hoạt | Định tuyến message đến queue, xử lý tác vụ, competing consumers và routing theo quy tắc | Cần thiết kế durability, prefetch, retry, dead-letter và giới hạn queue; replay lịch sử không phải mô hình chính |
| JMS provider | API messaging chuẩn trong hệ sinh thái Java/Jakarta, hỗ trợ queue và topic theo provider | Tổ chức đã chuẩn hóa JMS hoặc cần tích hợp với middleware doanh nghiệp hiện có | Tính năng, giao thức, khả năng mở rộng và cách vận hành phụ thuộc provider cụ thể |
| Dịch vụ messaging được quản lý trên cloud | Giảm công việc vận hành hạ tầng broker, tích hợp với IAM và hệ sinh thái cloud | Hệ thống đã chạy trên một cloud và muốn dùng dịch vụ messaging do nhà cung cấp quản lý | Phụ thuộc nhà cung cấp, giới hạn dịch vụ, chi phí theo lưu lượng và khả năng di chuyển cần được đánh giá |

Kafka thường được xem như một event log có thể đọc lại theo offset. RabbitMQ thường được dùng như một broker định tuyến và phân phối message đến queue. JMS mô tả API lập trình; đặc tính vận hành thực tế phụ thuộc message broker triển khai API đó. Dịch vụ cloud có thể cung cấp queue, topic hoặc cả hai, nhưng tên gọi không bảo đảm ngữ nghĩa giống Kafka hay RabbitMQ.

## 3. Chọn Kafka khi cần event stream và replay

Kafka phù hợp khi event là một luồng dữ liệu có giá trị theo thời gian và nhiều consumer cần đọc độc lập. Producer ghi message vào topic; topic được chia thành partition để mở rộng song song. Consumer group có offset riêng, vì vậy nhóm phân tích có thể đọc cùng luồng với nhóm hóa đơn mà không làm mất message của nhau.

Kafka là lựa chọn đáng cân nhắc khi:

- Nhiều nhóm consumer cần tiêu thụ cùng một event stream theo tốc độ riêng.
- Cần replay message trong thời hạn retention để dựng lại projection hoặc khôi phục consumer.
- Thông lượng cao và có thể chia workload theo partition.
- Cần giữ thứ tự cho các event cùng aggregate bằng message key ổn định.
- Hệ thống có năng lực vận hành partition, replication, broker, offset và schema.

Ví dụ, topic `orders.events` dùng `orderId` làm key. Các thay đổi của cùng đơn hàng thường được đưa vào cùng partition, nơi Kafka bảo toàn thứ tự message. Điều này hỗ trợ consumer dựng trạng thái đơn hàng theo chuỗi event. Thứ tự không được bảo đảm giữa các partition; một key có lưu lượng quá lớn cũng có thể tạo hot partition.

Kafka không tự động làm cho consumer xử lý nghiệp vụ đúng một lần. Consumer có thể đọc lại message khi offset chưa được commit hoặc khi group rebalance. Cần kết hợp commit offset phù hợp, xử lý idempotent và cơ chế đối soát cho side effect bên ngoài. Retention cũng có giới hạn; replay chỉ khả dụng khi message còn được lưu.

## 4. Chọn RabbitMQ hoặc AMQP khi cần routing và queue

RabbitMQ phù hợp khi message cần được định tuyến linh hoạt đến một hoặc nhiều queue. Producer publish vào exchange; exchange dùng direct, topic, fanout hoặc headers routing để chọn queue theo binding. Consumer nhận message từ queue và xác nhận xử lý bằng acknowledgement.

RabbitMQ là lựa chọn đáng cân nhắc khi:

- Một event cần được phân phối đến nhiều queue độc lập.
- Routing key hoặc header quyết định nhóm nhận message.
- Tác vụ cần được chia cho nhiều worker cùng đọc một queue.
- Cần acknowledgement, retry và dead-letter queue theo luồng xử lý công việc.
- Hệ thống cần mô hình request/reply hoặc các pattern messaging mà broker hỗ trợ.

Ví dụ, exchange `orders.events` nhận routing key `orders.completed`. Binding có thể đưa message đến `billing.order-completed` và `analytics.order-events`. Mỗi queue có consumer và chính sách xử lý riêng. Producer chỉ cần biết target logic; topology queue được quản lý ở tầng tích hợp và vận hành.

Queue không phải kho lưu event dài hạn mặc định. Message có thể bị loại khỏi queue sau acknowledgement; nếu cần replay lịch sử, cần thiết kế lưu trữ hoặc luồng event log riêng. Khi có nhiều consumer, retry và requeue, thứ tự xử lý có thể thay đổi. Nếu nghiệp vụ cần thứ tự, hãy giới hạn song song hoặc bổ sung sequence/version để phát hiện message đến sai thứ tự.

## 5. Chọn JMS hoặc dịch vụ messaging được quản lý

JMS phù hợp khi tổ chức đã có message-oriented middleware và ứng dụng Java cần tích hợp theo API chuẩn. Tuy nhiên, JMS là hợp đồng API; khả năng lưu bền, routing, clustering, throughput, replay và quản trị phụ thuộc provider. Hãy đánh giá sản phẩm đang dùng và các extension riêng của nó trước khi giả định hai JMS provider có hành vi giống nhau.

Dịch vụ messaging được quản lý phù hợp khi đội ngũ muốn giảm trách nhiệm vận hành broker. Nhà cung cấp thường đảm nhận phần lớn công việc về hạ tầng, cập nhật và tính sẵn sàng, còn ứng dụng tập trung vào destination, quyền truy cập, retry và consumer. Cần kiểm tra giới hạn message size, throughput, retention, ordering, redrive, region, SLA và chi phí. Chi phí có thể tăng theo số request, dữ liệu truyền, dung lượng lưu và số lần giao lại.

Đối với cả hai mô hình, hãy kiểm tra khả năng tương thích với Spring Boot và phiên bản Spring Modulith đang dùng. Nếu không có integration adapter phù hợp, có thể viết adapter riêng dựa trên API của nền tảng, nhưng cần sở hữu thêm mã tích hợp, kiểm thử và vận hành.

## 6. Vai trò của adapter trong Spring Modulith

Module nghiệp vụ nên phát application event bằng Spring application event mechanism. Adapter đảm nhiệm việc chuyển event đã được đánh dấu sang broker. Cách tổ chức này giữ code nghiệp vụ độc lập với Kafka producer API, RabbitMQ exchange hoặc JMS destination.

Ví dụ một event được đánh dấu externalize:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
    UUID eventId,
    UUID orderId,
    Instant completedAt
) {}
```

Service nghiệp vụ chỉ phát event trong transaction:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CompleteOrder {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    CompleteOrder(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    void complete(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.complete();
        events.publishEvent(new OrderCompleted(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
```

`orders.completed` là target identifier do ứng dụng quy ước. Adapter được cấu hình có thể ánh xạ target thành topic Kafka, exchange/routing key AMQP hoặc destination tương ứng. Annotation không tự tạo topic, queue, exchange, quyền truy cập hay schema registry. Cách ánh xạ và các thuộc tính vận chuyển là chi tiết của integration module và cấu hình broker.

Spring Modulith có các integration module cho một số nền tảng messaging, chẳng hạn Kafka và AMQP. Tên dependency, cấu hình và khả năng cụ thể thay đổi theo phiên bản. Hãy chọn module cùng phiên bản tương thích với Spring Modulith của ứng dụng và đọc tài liệu tương ứng trước khi cấu hình. Với provider khác, có thể cần adapter tùy chỉnh.

Adapter nên tập trung vào các trách nhiệm vận chuyển: ánh xạ target, serialize payload, gửi message, xử lý phản hồi từ broker và báo kết quả publication. Tránh đưa quy tắc nghiệp vụ như “đơn hàng nào được phép hoàn tất” vào adapter.

## 7. Publication registry và ranh giới transaction

Gửi message qua mạng và commit cơ sở dữ liệu nghiệp vụ là hai thao tác ở hai hệ thống khác nhau. Nếu broker nhận message nhưng transaction nghiệp vụ rollback, consumer sẽ thấy một event không có hiệu lực. Nếu transaction commit nhưng ứng dụng dừng trước khi gửi message, broker có thể không nhận được event.

Event publication registry của Spring Modulith theo dõi publication cần được xử lý cho listener hoặc externalization target. Khi dùng persistence phù hợp, thông tin publication được ghi nhận trong ranh giới transaction nghiệp vụ; adapter thực hiện giao event sau commit và cập nhật trạng thái publication khi hoàn tất. Nếu lần gửi thất bại hoặc tiến trình dừng giữa chừng, publication chưa hoàn tất có thể được phát hiện để retry hoặc resubmit theo chính sách ứng dụng.

Mô hình này giúp phục hồi việc giao message mà không buộc service nghiệp vụ gọi broker trực tiếp. Tuy nhiên, nếu broker đã nhận message nhưng ứng dụng chưa kịp ghi nhận publication hoàn tất, lần gửi lại có thể tạo message trùng. Không nên tuyên bố exactly-once end-to-end chỉ vì có publication registry hoặc broker transaction.

Consumer cần idempotent. Dùng event ID ổn định làm khóa chống trùng, lưu dấu đã xử lý cùng transaction cập nhật dữ liệu consumer và dùng idempotency key khi gọi hệ thống ngoài nếu API hỗ trợ. Với side effect không thể đảo ngược, cần có quy trình đối soát.

## 8. Chọn theo độ tin cậy và semantics giao nhận

Đừng chỉ hỏi broker có “guarantee delivery” hay không. Hãy xác định chính xác điều gì được bảo đảm, trong phạm vi nào và điều kiện cấu hình nào phải thỏa mãn.

| Yêu cầu | Câu hỏi cần kiểm tra |
|---|---|
| Durability | Message có tồn tại sau restart broker hoặc node lỗi không? Replication và persistence được bật thế nào? |
| Acknowledgement | Producer nhận xác nhận khi broker nhận vào bộ nhớ, ghi bền hay replicate? Consumer ack ở thời điểm nào? |
| Retry | Message được thử lại ở producer, adapter, broker hay consumer? Có backoff và giới hạn không? |
| Dead-letter | Message lỗi được chuyển đi đâu, ai theo dõi và cách replay ra sao? |
| Ordering | Thứ tự được bảo đảm toàn cục, theo partition, queue hay key? Retry có thể làm thay đổi thứ tự không? |
| Replay | Có thể đọc lại message đã xử lý không? Thời hạn retention và cách chọn offset là gì? |
| Duplicate | Có thể giao lặp trong trường hợp timeout, restart hoặc mất acknowledgement không? |
| Backpressure | Điều gì xảy ra khi consumer chậm hơn producer? Có giới hạn queue, lag alert hoặc flow control không? |

Thông thường, hệ thống nên thiết kế theo khả năng message được giao ít nhất một lần và consumer idempotent, trừ khi có lý do rõ ràng để chọn semantics khác. Exactly-once thường chỉ áp dụng trong một phạm vi transaction hoặc nền tảng cụ thể; side effect qua nhiều hệ thống vẫn cần idempotency và đối soát.

## 9. Serialization, schema và kích thước message

Broker truyền byte hoặc message theo định dạng mà producer và consumer thống nhất. Hãy chọn serializer dựa trên khả năng tương thích, công cụ kiểm tra và nhu cầu tiến hóa schema. JSON dễ quan sát và tương thích rộng; Avro, Protobuf hoặc định dạng schema khác có thể phù hợp khi cần hợp đồng có kiểm soát và payload gọn hơn. Không có định dạng tốt nhất cho mọi hệ thống.

Hợp đồng message nên có event ID, event type, thời điểm xảy ra, schema version và correlation metadata khi cần. Tránh serialize trực tiếp JPA entity hoặc object nội bộ có thể thay đổi theo refactor. Chỉ gửi dữ liệu cần thiết cho consumer; message quá lớn làm tăng chi phí mạng, lưu trữ và độ trễ.

Nếu broker hoặc hệ sinh thái hỗ trợ schema registry, hãy định nghĩa compatibility rule cho việc thêm, bỏ hoặc đổi field. Nếu không dùng schema registry, vẫn cần quản lý schema bằng version, fixture JSON và kiểm thử hợp đồng. Producer và consumer phải có kế hoạch triển khai tương thích khi nâng cấp.

## 10. Bảo mật và vận hành

Broker là ranh giới bảo mật giữa các tiến trình. Producer chỉ nên có quyền publish vào destination cần thiết; consumer chỉ nên subscribe đúng luồng dữ liệu được cấp phép. Dùng TLS, cơ chế xác thực của nền tảng, quản lý secret tập trung và chính sách xoay vòng credential. Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào payload, header hay tên destination.

Chọn broker cũng là chọn mô hình vận hành. Cần biết ai chịu trách nhiệm nâng cấp, backup, restore, capacity planning, chứng thư, quyền truy cập, cảnh báo và ứng phó sự cố. Với dịch vụ managed, trách nhiệm hạ tầng giảm nhưng nhóm vẫn phải quản lý quota, destination, quyền, retry, consumer lag và chi phí.

Các chỉ số nên quan sát gồm:

- Tỷ lệ publish thành công, lỗi theo destination và độ trễ xác nhận từ broker.
- Số publication chưa hoàn tất và tuổi publication lâu nhất.
- Consumer lag hoặc queue depth, tốc độ tiêu thụ và số message unacknowledged.
- Số lần retry, redelivery, dead-letter và event trùng.
- Dung lượng lưu trữ, throughput, partition skew hoặc queue có tải bất thường.
- Event ID, correlation ID và trace ID để nối log giữa producer, adapter, broker và consumer.

Không ghi toàn bộ payload vào log mặc định. Log event ID, target, schema version, trạng thái và mã lỗi để điều tra mà hạn chế lộ dữ liệu nghiệp vụ.

## 11. Kiểm thử adapter và broker

Unit test cho service nghiệp vụ nên xác nhận event được phát khi trạng thái nghiệp vụ thay đổi hợp lệ. Test adapter cần xác nhận mapping target, serialization và xử lý phản hồi broker. Integration test phải kiểm tra hành vi với broker hoặc môi trường tương thích thực tế.

Các tình huống quan trọng gồm:

1. **Transaction commit:** event chỉ được externalize sau khi transaction nghiệp vụ commit.
2. **Transaction rollback:** thay đổi rollback không tạo message bên ngoài.
3. **Target mapping:** target logic được ánh xạ đến đúng topic, exchange hoặc destination.
4. **Serialization:** payload có event ID, type, timestamp và schema version đúng hợp đồng.
5. **Broker unavailable:** lỗi kết nối được ghi nhận; publication chưa hoàn tất có thể retry hoặc resubmit.
6. **Duplicate delivery:** consumer nhận cùng event nhiều lần nhưng side effect chỉ áp dụng một lần.
7. **Ordering và routing:** message đến đúng partition, queue hoặc consumer group theo topology dự kiến.
8. **Security:** producer và consumer chỉ có quyền cần thiết; kết nối dùng cấu hình bảo mật.
9. **Load và backpressure:** consumer chậm không làm hệ thống vượt giới hạn bộ nhớ hoặc mất kiểm soát queue/lag.

Mock broker hữu ích cho unit test mapping, nhưng không chứng minh durability, acknowledgement, routing, partition, authentication hoặc redelivery hoạt động đúng. Dùng integration test cho các semantics phụ thuộc broker.

## 12. Quy trình ra quyết định và chuyển đổi

Một quy trình chọn broker có thể thực hiện theo các bước:

1. **Ghi yêu cầu:** mô tả nhóm consumer, thông lượng, độ trễ, thứ tự, retention, replay và mức mất dữ liệu có thể chấp nhận.
2. **Chọn mô hình:** quyết định cần event log, publish-subscribe, queue work distribution hay kết hợp nhiều mô hình.
3. **Đánh giá ứng viên:** so sánh broker theo semantics, hệ sinh thái Spring, kỹ năng vận hành, bảo mật, chi phí và SLA.
4. **Thử nghiệm workload:** đo thông lượng và độ trễ với message size, số consumer và failure mode gần thực tế.
5. **Xác định hợp đồng:** thống nhất event type, schema, target, routing, idempotency và versioning.
6. **Triển khai consumer trước:** bảo đảm consumer có thể đọc schema và xử lý message trước khi producer phát rộng.
7. **Theo dõi và mở rộng:** quan sát publication, lag, queue depth, retry và chi phí; điều chỉnh partition, worker hoặc retention khi có số liệu.

Nếu chuyển từ broker này sang broker khác, tránh thay đổi đồng thời event contract và semantics giao nhận. Có thể dùng adapter mới cho cùng target logic, triển khai song song có kiểm soát, đối chiếu event ID và kết quả consumer, sau đó chuyển traffic theo từng giai đoạn. Cần xác định cách xử lý message tồn đọng và tránh phát hai luồng gây side effect trùng.

## 13. Những điểm cần nhớ

- Chọn broker từ nhu cầu consumer, thứ tự, retention, replay, throughput và năng lực vận hành.
- Kafka phù hợp với event stream có partition, consumer group và replay; RabbitMQ/AMQP phù hợp với routing và queue work distribution.
- JMS là API messaging, còn hành vi cụ thể phụ thuộc provider; dịch vụ managed giảm gánh nặng hạ tầng nhưng vẫn có quota, chi phí và semantics riêng.
- Spring Modulith adapter ánh xạ event externalized sang broker; target logic không tự tạo topology hoặc quyền truy cập.
- Publication registry hỗ trợ theo dõi và phục hồi việc giao sau commit; consumer vẫn phải xử lý duplicate an toàn.
- Kiểm thử broker thực tế, quan sát vận hành và quản lý schema là một phần của quyết định chọn nền tảng.

Khi broker phản ánh đúng mô hình tiêu thụ, adapter giữ ranh giới giữa application event và API vận chuyển, còn publication registry cùng consumer idempotent xử lý các tình huống lỗi, ứng dụng Spring Modulith có thể giao tiếp đáng tin cậy mà không buộc module nghiệp vụ phụ thuộc vào công nghệ messaging cụ thể.
