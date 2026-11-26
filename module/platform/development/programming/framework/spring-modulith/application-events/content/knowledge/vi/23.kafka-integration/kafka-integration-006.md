# Retry topic

Trong tích hợp Kafka, consumer có thể gặp lỗi khi xử lý một message dù broker đã giao message thành công. Lỗi có thể chỉ là tạm thời, chẳng hạn dịch vụ kho đang quá tải hoặc cơ sở dữ liệu mất kết nối trong thời gian ngắn. Retry topic cho phép chuyển message lỗi sang một topic retry và thử lại sau khoảng chờ đã cấu hình. Nếu message vẫn không xử lý được sau số lần thử, hệ thống có thể đưa nó vào dead-letter topic (DLT) để điều tra.

Trong module SPRING_MODULITH_APPLICATION_EVENTS, cần phân biệt retry ở hai chặng. Spring Modulith Event Publication Registry theo dõi việc giao application event tới listener trong ứng dụng, bao gồm listener externalization gửi message sang Kafka. Retry topic của Spring Kafka xử lý lỗi ở phía consumer sau khi message đã tới Kafka. Hai cơ chế giải quyết hai ranh giới khác nhau và có thể cùng xuất hiện trong một luồng.

## 1. Retry topic là gì?

Retry topic là topic Kafka được dùng làm nơi lưu message cần thử lại sau một khoảng thời gian. Thay vì giữ consumer ở lần xử lý hiện tại và chờ liên tục, Spring Kafka có thể chuyển message lỗi sang topic retry tương ứng. Consumer retry nhận message sau khi message đủ điều kiện được đọc; nếu vẫn lỗi, message tiếp tục đi qua các lần retry đã cấu hình. Khi hết số lần thử, message được chuyển tới DLT.

~~~mermaid
flowchart TD
    A[Topic chính: orders] --> B[Consumer xử lý]
    B -->|Thành công| C[Commit offset]
    B -->|Lỗi có thể retry| D[Retry topic lần 1]
    D -->|Đã chuyển message| C
    D --> E[Consumer thử lại]
    E -->|Thành công| C
    E -->|Vẫn lỗi| F[Retry topic tiếp theo]
    F --> G[Consumer thử lại]
    G -->|Thành công| C
    G -->|Hết lần thử| H[Dead-letter topic]
    H --> I[Điều tra hoặc xử lý lại có kiểm soát]
~~~

Retry topic đặc biệt hữu ích với lỗi tạm thời và khoảng chờ dài. Message lỗi được chuyển sang luồng retry, nhờ đó consumer của topic chính có thể tiếp tục xử lý các message khác thay vì bị giữ lại trong thời gian chờ.

## 2. Phân biệt retry của Spring Modulith và retry topic của Kafka

Đây là khác biệt quan trọng khi ứng dụng dùng Spring Modulith để externalize event sang Kafka:

| Cơ chế | Xử lý lỗi ở đâu? | Mục tiêu |
| --- | --- | --- |
| Event Publication Registry của Spring Modulith | Listener nội bộ hoặc listener externalization chưa hoàn tất | Theo dõi và phục hồi publication của application event trong ứng dụng |
| Retry topic của Spring Kafka | Kafka consumer đã nhận message nhưng xử lý thất bại | Thử lại message ở phía consumer theo lịch và số lần đã cấu hình |
| Dead-letter topic | Message không xử lý được sau chính sách retry hoặc được phân loại không retry | Cô lập message lỗi để cảnh báo, điều tra hoặc xử lý lại |

Ví dụ, module Orders publish `OrderConfirmed`. Spring Modulith ghi nhận publication và externalization listener gửi message tới Kafka. Nếu listener externalization không gửi được vì broker tạm thời mất kết nối, publication có thể còn chưa hoàn tất trong registry; ứng dụng cần phục hồi hoặc resubmit publication theo cơ chế Spring Modulith đã cấu hình. Nếu Kafka đã nhận message nhưng consumer Inventory lỗi khi cập nhật tồn kho, retry topic của Spring Kafka mới là cơ chế xử lý phù hợp.

Retry topic không thể khôi phục một event chưa từng được gửi thành công tới Kafka. Ngược lại, việc registry ghi nhận externalization listener đã hoàn tất cũng không chứng minh consumer đã xử lý xong nghiệp vụ. Hai trạng thái cần được quan sát riêng.

## 3. Cấu hình retry topic bằng Spring Kafka

Spring Kafka cung cấp `@RetryableTopic` để khai báo chính sách non-blocking retry cho một `@KafkaListener`. Có thể đặt số lần thử và backoff cho các lần nhận lại. Ví dụ sau dùng bốn lần giao tổng cộng, tính cả lần xử lý ban đầu, với thời gian chờ tăng dần:

~~~java
import java.util.UUID;

import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

record OrderConfirmed(UUID eventId, UUID orderId) { }

@Component
class InventoryEventConsumer {

    private final InventoryService inventory;

    InventoryEventConsumer(InventoryService inventory) {
        this.inventory = inventory;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000))
    @KafkaListener(topics = "orders", groupId = "inventory")
    public void onOrderConfirmed(OrderConfirmed event) {
        inventory.reserve(event.orderId());
    }

    @DltHandler
    public void onDeadLetter(OrderConfirmed event) {
        // Ghi nhận cảnh báo và chuyển tới quy trình điều tra.
    }
}
~~~

Trong ví dụ, listener nhận event từ topic `orders`. Khi xử lý thất bại theo chính sách retry, Spring Kafka chuyển message qua các retry topic đã được cấu hình và cuối cùng tới DLT nếu đã hết lượt thử. `@DltHandler` khai báo phương thức xử lý message ở DLT trong cùng lớp listener.

Ví dụ cần các dependency Spring Kafka và Spring Retry phù hợp với phiên bản ứng dụng. Cấu hình thực tế còn phải có deserializer hoặc message converter tương thích với payload `OrderConfirmed`, cấu hình broker và quyền truy cập topic. Cú pháp annotation và các tùy chọn cần được đối chiếu với phiên bản Spring Kafka đang dùng.

`attempts = "4"` biểu thị tổng số lần giao để xử lý, bao gồm lần đầu tiên. Backoff trên bắt đầu với khoảng chờ 1 giây, tăng theo hệ số 2 và bị giới hạn ở 10 giây. Hãy chọn số lần và khoảng chờ dựa trên SLA, thời gian phục hồi của dependency và mức tải hệ thống.

## 4. Chọn chính sách retry theo loại lỗi

Không phải lỗi nào cũng nên retry. Hãy phân loại lỗi theo khả năng tự phục hồi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi tạm thời | Timeout, kết nối database chập chờn, dịch vụ phụ thuộc tạm thời không sẵn sàng | Retry với backoff và giới hạn số lần |
| Lỗi dữ liệu hoặc hợp đồng | Thiếu field bắt buộc, sai định dạng, schema không tương thích | Thường đưa vào DLT để điều tra hoặc sửa dữ liệu |
| Lỗi nghiệp vụ không thể tự phục hồi | Đơn hàng ở trạng thái không cho phép giữ hàng, tham chiếu không tồn tại | Áp dụng quy tắc nghiệp vụ; không retry vô hạn |
| Lỗi cấu hình hoặc quyền | Sai ACL, credential hết hạn, serializer cấu hình sai | Cảnh báo và sửa cấu hình; retry chỉ sau khi nguyên nhân được khắc phục |

Spring Kafka cho phép cấu hình exception nào được retry và exception nào không retry. Hãy khai báo phân loại rõ ràng theo lỗi của ứng dụng. Nếu mọi exception đều bị retry theo cùng một lịch, message lỗi dữ liệu có thể chiếm tài nguyên và trì hoãn việc phát hiện vấn đề thật.

Với lỗi tạm thời, backoff giúp tránh tạo tải dồn lên dependency đang phục hồi. Có thể dùng backoff tuyến tính hoặc exponential; thêm jitter ở tầng thiết kế nếu nhiều consumer có nguy cơ retry đồng thời. Giới hạn thời gian và số lần thử để một message không bị giữ trong vòng lặp vô hạn.

## 5. Non-blocking retry và thứ tự message

Retry topic là cơ chế non-blocking: message lỗi được chuyển sang topic retry, còn consumer của topic chính có thể tiếp tục với message khác. Điều này cải thiện khả năng xử lý thông lượng, nhưng có một hệ quả: message đến sau có thể được xử lý trước message đang chờ retry.

Ví dụ, cùng một đơn hàng có hai event:

1. `OrderConfirmed` gặp lỗi và được chuyển sang retry topic.
2. `OrderCancelled` đến topic chính sau đó và được xử lý ngay.

Nếu `OrderCancelled` được áp dụng trước `OrderConfirmed` được retry, trạng thái nghiệp vụ có thể bị đảo thứ tự. Vì vậy, nếu thứ tự theo aggregate là bắt buộc, hãy cân nhắc cơ chế retry blocking, thiết kế consumer theo version/sequence, hoặc trì hoãn việc áp dụng event khi phát hiện event trước đó chưa được xử lý.

Chọn partition key ổn định như `orderId` giúp event của cùng aggregate được ghi vào cùng partition của topic tương ứng. Tuy nhiên, retry topic vẫn có thể làm thay đổi thứ tự xử lý giữa message đang chờ và message mới. Partition key không tự bảo đảm thứ tự end-to-end khi message đi qua các topic retry khác nhau.

Spring Kafka cũng có cơ chế xử lý lỗi blocking như `DefaultErrorHandler` với backoff. Cơ chế blocking giữ luồng xử lý chờ retry theo cấu hình và có thể phù hợp khi thứ tự trong partition quan trọng hơn thông lượng. Chọn chiến lược dựa trên yêu cầu thứ tự, độ trễ và khả năng cô lập lỗi.

## 6. Idempotency khi message được giao lại

Kafka consumer có thể nhận cùng một message nhiều lần. Điều này xảy ra khi consumer xử lý xong side effect nhưng chưa commit offset, khi retry hoặc khi DLT được phát lại. Vì thế, listener nên idempotent: nhận lại cùng một event không được thực hiện side effect nghiệp vụ lần thứ hai.

Một cách phổ biến là lưu `eventId` đã xử lý trong cùng transaction với cập nhật nghiệp vụ:

~~~java
@Transactional
public void reserveOnce(OrderConfirmed event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    inventory.reserveInDatabase(event.orderId());
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Đây là ví dụ khái niệm; `reserveInDatabase` biểu thị thay đổi dữ liệu nằm trong cùng transaction và cùng ranh giới lưu trữ với bản ghi `ProcessedEvent`. Cần bảo đảm thao tác kiểm tra, thay đổi nghiệp vụ và ghi nhận `eventId` có tính nguyên tử. Nếu side effect gọi sang hệ thống ngoài, transaction cơ sở dữ liệu không thể tự rollback side effect đó; hãy dùng idempotency key ở API đích hoặc một quy trình outbox phù hợp. Nếu hai consumer đồng thời xử lý cùng event, nên có unique constraint hoặc cơ chế khóa phù hợp để tránh race condition.

Idempotency đặc biệt quan trọng khi xử lý lại DLT. Một message có thể đã tạo ra side effect ở lần chạy trước nhưng bị đánh dấu lỗi do một bước sau đó thất bại. Trước khi replay, cần biết side effect nào đã hoàn thành và bảo đảm việc thực thi lại an toàn.

## 7. Dead-letter topic và quy trình xử lý

DLT là nơi cô lập message đã hết lượt retry hoặc được định tuyến tới dead-letter theo chính sách. DLT giúp consumer chính tiếp tục hoạt động trong khi message lỗi được giữ lại để điều tra.

Quy trình DLT nên bao gồm:

1. Lưu thông tin nhận diện như event ID, event type, topic nguồn, partition, offset, exception và thời điểm lỗi.
2. Phát cảnh báo khi số lượng message DLT tăng hoặc có message vượt quá thời gian xử lý cho phép.
3. Kiểm tra nguyên nhân: dữ liệu lỗi, schema, dependency, cấu hình, quyền truy cập hoặc bug trong consumer.
4. Xác định side effect đã xảy ra tới đâu và cách replay an toàn.
5. Sau khi sửa nguyên nhân, phát lại message theo quy trình có kiểm soát và theo dõi kết quả.

Không nên xóa DLT message ngay sau khi ghi log. DLT là dữ liệu phục vụ điều tra và phục hồi; cần chính sách retention, quyền truy cập và quy trình xử lý rõ ràng. Tránh tự động replay toàn bộ DLT khi chưa phân loại lỗi, vì message lỗi dữ liệu có thể tiếp tục thất bại hoặc gây side effect lặp.

## 8. Thiết kế retry topic và vận hành Kafka

Retry topic và DLT là các topic thật trong Kafka. Cần quản lý chúng như các tài nguyên production:

- Đặt quy ước tên topic nhất quán theo domain, consumer group và mục đích retry.
- Provision topic, partition, replication factor và ACL phù hợp qua hạ tầng quản lý cấu hình.
- Bảo đảm số partition và routing key tương thích với chiến lược phân phối của topic gốc.
- Chọn retention đủ để message không bị xóa trước khi có thể điều tra hoặc phục hồi.
- Kiểm soát quyền đọc DLT và quyền replay vì message có thể chứa dữ liệu nghiệp vụ.
- Theo dõi consumer lag của topic chính, từng retry topic và DLT.

Spring Kafka có thể hỗ trợ tạo các retry topic theo cấu hình, nhưng production nên quản lý việc tạo topic có chủ đích. Không mặc định mọi môi trường cho phép ứng dụng tự tạo topic hoặc có replication factor phù hợp.

## 9. Quan sát và chẩn đoán retry

Theo dõi ít nhất các chỉ số sau:

- Số message đang chờ ở topic chính và từng retry topic.
- Consumer lag, thời gian chờ và thời gian xử lý trung bình.
- Số lần retry theo event type, consumer group và loại exception.
- Số message được chuyển vào DLT và tuổi của message cũ nhất.
- Tỷ lệ xử lý thành công sau retry và tỷ lệ lỗi cuối cùng.
- Số lần replay DLT và kết quả sau replay.

Log nên có event ID, event type, correlation ID, topic, partition, offset, attempt và exception class. Tránh ghi toàn bộ payload nếu có dữ liệu nhạy cảm. Dùng correlation ID để liên kết luồng phát event trong Spring Modulith với message Kafka và thao tác của consumer.

Khi retry tăng đột biến, kiểm tra sức khỏe dependency, lag, partition assignment và lỗi theo exception. Nếu cùng một exception xuất hiện trên nhiều event type, có thể vấn đề nằm ở dependency dùng chung hoặc cấu hình consumer. Nếu chỉ một event type thất bại, kiểm tra payload và logic xử lý riêng.

## 10. Khi nào dùng retry topic?

Retry topic phù hợp khi consumer cần thử lại bất đồng bộ với khoảng chờ đáng kể và việc cho phép message mới đi trước message lỗi là chấp nhận được. Nó cũng hữu ích khi muốn tách message lỗi ra khỏi luồng chính và có DLT cho điều tra.

Không nên dùng retry topic như giải pháp duy nhất cho mọi lỗi. Với lỗi cấu hình khiến mọi message đều thất bại, retry topic chỉ làm tăng số topic và độ trễ. Với yêu cầu thứ tự nghiêm ngặt, non-blocking retry có thể không phù hợp. Với lỗi ở chặng gửi event từ ứng dụng sang Kafka, hãy xử lý publication chưa hoàn tất bằng cơ chế Spring Modulith và adapter tương ứng.

## Kết luận

Retry topic giúp Spring Kafka thử lại message consumer xử lý thất bại theo lịch backoff và chuyển message hết lượt sang DLT. Hãy phân loại lỗi, đặt giới hạn retry, thiết kế consumer idempotent và đánh giá ảnh hưởng tới thứ tự message. Trong hệ thống Spring Modulith, kết hợp retry topic với Event Publication Registry đúng ranh giới sẽ giúp theo dõi riêng việc gửi event sang Kafka và việc consumer xử lý message, từ đó phục hồi có kiểm soát và tránh mất dấu lỗi.
