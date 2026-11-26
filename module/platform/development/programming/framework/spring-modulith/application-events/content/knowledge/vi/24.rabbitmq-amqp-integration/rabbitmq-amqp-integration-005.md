# Acknowledgement của AMQP

Acknowledgement (ack) là cơ chế xác nhận trạng thái xử lý message giữa consumer và RabbitMQ. Với AMQP 0-9-1, broker giữ message trong trạng thái chưa xác nhận sau khi giao cho consumer. Consumer gửi ack khi đã xử lý thành công; nếu xử lý thất bại, consumer có thể reject hoặc nack để yêu cầu broker xử lý message theo chính sách requeue hoặc dead-letter.

Ack quyết định message có được loại khỏi hàng đợi hay được giao lại. Chọn sai thời điểm xác nhận có thể làm mất message hoặc tạo xử lý trùng. Trong ứng dụng Spring Modulith, cần hiểu riêng publication ở phía producer và acknowledgement ở phía consumer: producer registry theo dõi việc externalize event tới broker; consumer ack xác nhận việc ứng dụng nhận đã xử lý message theo quy tắc của nó.

Bài này tập trung vào RabbitMQ sử dụng AMQP 0-9-1 và Spring AMQP. AMQP 1.0 có mô hình settlement và disposition khác, vì vậy không áp dụng nguyên xi các phương thức basic.ack, basic.nack hoặc basic.reject của 0-9-1 cho giao thức đó.

## 1. Hai chiều xác nhận trong luồng message

Một luồng event qua RabbitMQ có hai ranh giới xác nhận riêng:

1. **Publisher confirm:** broker phản hồi cho producer biết message publish đã được broker xử lý theo mức xác nhận được cấu hình.
2. **Consumer acknowledgement:** consumer phản hồi broker rằng một delivery đã được xử lý hoặc yêu cầu xử lý theo cách khác.

~~~mermaid
sequenceDiagram
    participant P as Producer adapter
    participant B as RabbitMQ broker
    participant C as Consumer
    P->>B: Publish message
    B-->>P: Publisher confirm
    B->>C: Deliver message
    C->>C: Xử lý nghiệp vụ
    C-->>B: basic.ack
    B->>B: Loại message khỏi queue
~~~

Publisher confirm không chứng minh consumer đã xử lý message. Consumer ack cũng không chứng minh producer đã nhận publisher confirm. Mỗi xác nhận thuộc một chặng khác nhau.

| Xác nhận | Chiều truyền | Ý nghĩa |
|---|---|---|
| Publisher confirm | Broker → Producer | Broker xác nhận việc publish theo cấu hình |
| Consumer ack | Consumer → Broker | Consumer xác nhận delivery đã được xử lý |
| Reject/Nack | Consumer → Broker | Consumer từ chối delivery và chọn requeue hoặc dead-letter/discard |

Nếu producer mất kết nối sau khi broker đã nhận message nhưng trước khi nhận confirm, producer có thể retry và tạo duplicate. Nếu consumer đã commit nghiệp vụ nhưng ack không đến được broker, broker có thể giao lại message. Cả hai tình huống đều yêu cầu xử lý trùng an toàn.

## 2. Trạng thái message khi được giao

Trong chế độ manual acknowledgement, message được broker giao cho consumer sẽ trở thành một delivery chưa xác nhận (unacknowledged). Message vẫn được broker quản lý và chưa được xóa khỏi queue.

Khi consumer gửi ack hợp lệ trên channel đã nhận delivery, broker có thể loại message khỏi queue. Khi consumer gửi reject hoặc nack, broker áp dụng lựa chọn requeue và cấu hình dead-letter tương ứng. Nếu channel hoặc connection đóng trước khi delivery được xác nhận, các message chưa ack thường được requeue để consumer khác hoặc consumer khởi động lại nhận lại.

Các trạng thái khái quát:

| Trạng thái | Ý nghĩa |
|---|---|
| Ready | Message đang chờ consumer |
| Unacknowledged | Broker đã giao message nhưng chưa nhận ack/reject/nack |
| Acknowledged | Broker nhận ack và có thể loại message khỏi queue |
| Requeued | Message được đưa trở lại luồng giao nhận |
| Dead-lettered | Message được chuyển tới dead-letter exchange nếu cấu hình |
| Discarded | Message bị loại bỏ, ví dụ reject không requeue và không có DLX |

Trạng thái Ready và Unacknowledged thường được hiển thị trong RabbitMQ Management UI. Theo dõi cả hai giúp phân biệt backlog chưa được giao với message đã giao nhưng consumer xử lý chậm hoặc không xác nhận.

## 3. basic.ack: xác nhận xử lý thành công

Trong AMQP 0-9-1, basic.ack xác nhận một hoặc nhiều delivery đã được xử lý. Mỗi delivery có một delivery tag do broker cấp trong phạm vi channel.

Ví dụ lệnh giao thức:

~~~text
basic.ack(
    delivery-tag = 42,
    multiple = false
)
~~~

Khi multiple=false, chỉ delivery có tag 42 được xác nhận. Khi multiple=true, broker xác nhận tất cả delivery chưa ack trên cùng channel có tag nhỏ hơn hoặc bằng 42.

Chỉ dùng multiple=true khi ứng dụng chắc chắn mọi delivery trước tag đó đã xử lý xong. Nếu consumer xử lý song song và message có tag 41 vẫn đang chạy nhưng tag 42 đã hoàn tất, ack tag 42 với multiple=true có thể xác nhận nhầm cả tag 41. Khi xử lý đồng thời, cách an toàn thường là ack từng delivery với multiple=false hoặc duy trì cơ chế hoàn tất theo thứ tự.

Delivery tag có phạm vi theo channel, không phải định danh message toàn cục. Ack một tag trên channel khác với channel đã nhận delivery là lỗi giao thức và có thể khiến broker đóng channel. Không lưu delivery tag để sử dụng sau khi channel đã được thay thế; khi message được giao lại, broker cấp delivery tag mới.

## 4. basic.reject và basic.nack

Khi consumer không thể xử lý message, nó có thể từ chối delivery:

- **basic.reject:** từ chối một delivery.
- **basic.nack:** từ chối một hoặc nhiều delivery, có tùy chọn xác nhận theo lô thông qua cờ multiple.

Cả hai có cờ requeue:

~~~text
basic.reject(
    delivery-tag = 42,
    requeue = true
)

basic.nack(
    delivery-tag = 43,
    multiple = false,
    requeue = false
)
~~~

| Thao tác | Kết quả |
|---|---|
| basic.ack | Xác nhận xử lý và loại message khỏi queue |
| basic.reject, requeue=true | Từ chối một delivery và yêu cầu giao lại |
| basic.reject, requeue=false | Từ chối một delivery; chuyển qua DLX nếu có, nếu không thì loại bỏ |
| basic.nack, requeue=true | Từ chối một hoặc nhiều delivery và yêu cầu giao lại |
| basic.nack, requeue=false | Từ chối một hoặc nhiều delivery; chuyển qua DLX nếu có, nếu không thì loại bỏ |

Không dùng requeue=false mà không hiểu chính sách dead-letter. Nếu queue không cấu hình dead-letter exchange, message có thể bị loại bỏ. Nếu cần giữ message lỗi để điều tra, hãy cấu hình DLX và queue đích trước khi áp dụng chính sách này.

## 5. Thời điểm gửi acknowledgement

Ack chỉ nên được gửi sau khi consumer đã hoàn tất công việc cần bảo đảm. Với consumer cập nhật database, thứ tự phổ biến là:

~~~mermaid
flowchart TD
    A["Nhận delivery"] --> B["Validate payload"]
    B --> C["Thực hiện nghiệp vụ trong transaction"]
    C --> D{"Commit thành công?"}
    D -->|Có| E["Gửi basic.ack"]
    D -->|Không| F["Reject/Nack theo retry policy"]
    E --> G["Broker loại message khỏi queue"]
    F --> H["Requeue hoặc dead-letter"]
~~~

Nếu ack trước khi commit database, tiến trình có thể dừng sau ack nhưng trước commit. Broker đã loại message, còn thay đổi nghiệp vụ chưa được lưu; message có thể bị mất khỏi luồng xử lý.

Nếu commit database trước rồi tiến trình dừng trước khi broker nhận ack, broker có thể giao lại message. Đây là duplicate, nhưng dữ liệu nghiệp vụ đã commit. Consumer phải dùng idempotency để lần giao lại không tạo hóa đơn, thanh toán hoặc side effect thứ hai.

Không có thứ tự đơn giản nào biến database transaction và RabbitMQ acknowledgement thành một giao dịch nguyên tử. Nếu cần phối hợp hai hệ thống, hãy thiết kế idempotency, outbox/inbox hoặc quy trình đối soát phù hợp.

## 6. Ack mode trong Spring AMQP

Spring AMQP cung cấp ba chế độ xác nhận chính qua AcknowledgeMode. Cần phân biệt tên chế độ của Spring với cách gọi auto-ack trong giao thức RabbitMQ.

| Spring AcknowledgeMode | Hành vi |
|---|---|
| NONE | Broker dùng auto-ack: message được coi là đã giao thành công khi gửi tới consumer; ứng dụng không gửi consumer ack |
| AUTO | Listener container gửi ack khi listener hoàn tất bình thường; exception được container xử lý theo chính sách reject/requeue |
| MANUAL | Listener hoặc code ứng dụng chủ động gửi ack, nack hoặc reject |

Trong nhiều ứng dụng Spring AMQP, AUTO là lựa chọn mặc định của listener container. Tuy nhiên, hãy kiểm tra cấu hình thực tế, vì Spring Boot properties, container factory và cấu hình riêng có thể thay đổi hành vi.

### NONE: broker auto-ack

NONE tương ứng với việc consumer đăng ký nhận message mà không yêu cầu broker chờ ack. Broker coi message đã được giao thành công khi chuyển nó tới consumer. Nếu tiến trình dừng ngay sau khi nhận message nhưng trước khi xử lý xong, message có thể không được giao lại.

Chế độ này phù hợp với một số luồng dữ liệu có thể chấp nhận mất message hoặc có cơ chế tái tạo dữ liệu khác. Không dùng nó cho công việc nghiệp vụ cần bảo đảm xử lý.

### AUTO: container xác nhận sau listener

Với AUTO, listener method chỉ cần hoàn tất bình thường; container quản lý việc gửi ack. Nếu listener ném exception, container xử lý message theo cấu hình requeue/reject và loại exception.

Đây thường là lựa chọn thuận tiện vì code nghiệp vụ không phải thao tác delivery tag. Nhưng listener phải để exception truyền tới container khi xử lý thất bại. Nếu bắt exception rồi nuốt lỗi, container có thể coi listener hoàn tất thành công và ack message dù nghiệp vụ chưa hoàn tất.

Các cấu hình như defaultRequeueRejected và các exception điều khiển requeue cần được thiết lập theo chính sách retry của ứng dụng. Không nên dựa vào giá trị mặc định mà không kiểm tra cấu hình đang chạy.

### MANUAL: ứng dụng tự xác nhận

Với MANUAL, listener phải tự gửi ack hoặc reject/nack. Cách này hữu ích khi ứng dụng cần quyết định chính xác thời điểm xác nhận, ví dụ sau khi một giao dịch hoặc bước xử lý bất đồng bộ hoàn tất.

Ví dụ Spring AMQP:

~~~java
@RabbitListener(queues = "orders.order-paid")
public void handle(
        OrderPaidPayload payload,
        Message message,
        Channel channel
) throws IOException {

    long deliveryTag =
        message.getMessageProperties().getDeliveryTag();

    try {
        orderService.applyPaymentEvent(payload);
        channel.basicAck(deliveryTag, false);
    } catch (TemporaryProcessingException ex) {
        channel.basicNack(deliveryTag, false, true);
    } catch (Exception ex) {
        channel.basicReject(deliveryTag, false);
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thực tế, không nên requeue ngay mọi TemporaryProcessingException nếu điều đó có thể tạo vòng lặp nhanh. Hãy chuyển lỗi tạm thời qua retry queue có backoff hoặc chính sách retry có giới hạn. Khi dùng MANUAL, mỗi nhánh xử lý cần xác định rõ message được ack, nack hay reject; không để delivery bị treo vô hạn.

## 7. Requeue, retry queue và dead-letter exchange

Requeue=true yêu cầu broker đưa message trở lại hàng đợi để giao lại. Điều này hữu ích khi consumer gặp sự cố ngắn hạn, nhưng có thể tạo vòng lặp nóng nếu lỗi luôn tái diễn.

Ví dụ: consumer nhận message, gọi dịch vụ thanh toán đang ngừng, nack với requeue=true; broker lập tức giao lại message cho consumer; consumer tiếp tục thất bại và lặp lại. Vòng lặp này tiêu tốn CPU, network và log, đồng thời làm các message khác khó được xử lý.

Một thiết kế retry có kiểm soát thường dùng:

1. Queue xử lý chính nhận message.
2. Consumer thất bại và reject/nack không requeue.
3. Dead-letter exchange định tuyến message sang retry queue.
4. Retry queue giữ message trong khoảng TTL đã cấu hình.
5. Hết TTL, retry queue dead-letter message trở lại queue chính.
6. Sau số lần thử tối đa, message được chuyển sang parking/dead-letter queue để điều tra.

~~~mermaid
flowchart TD
    A["orders.order-paid"] --> B["Consumer xử lý"]
    B -->|Thành công| C["ACK"]
    B -->|Lỗi tạm thời| D["NACK không requeue"]
    D --> E["Retry DLX"]
    E --> F["Retry queue có TTL"]
    F -->|Hết TTL| A
    B -->|Hết lượt thử / lỗi không thể phục hồi| G["Parking queue"]
~~~

RabbitMQ có thể cấu hình dead-letter exchange bằng queue arguments hoặc policy. Với môi trường vận hành, policy thường dễ thay đổi hơn khi cần điều chỉnh cấu hình queue. Hãy kiểm tra dead-letter routing key, exchange, queue đích, TTL và giới hạn số lần thử.

Dead-letter không tự động đồng nghĩa với retry. DLX chỉ định tuyến message bị dead-letter theo điều kiện cấu hình. Ứng dụng cần thiết kế topology và metadata retry nếu muốn thực hiện retry có giới hạn. Nếu message bị dead-letter nhiều lần, cần tránh vòng định tuyến vô hạn giữa các queue.

## 8. Prefetch và số message chưa xác nhận

Prefetch giới hạn số message broker có thể giao nhưng chưa được consumer xác nhận trong phạm vi cấu hình QoS. Nó là cơ chế backpressure, giúp consumer không bị ngập bởi quá nhiều delivery đang chờ xử lý.

Ví dụ, prefetch 10 có nghĩa broker chỉ giao tối đa số message chưa ack theo giới hạn QoS đã cấu hình; khi consumer ack một message, broker có thể giao thêm message khác.

| Prefetch | Tác động thường thấy |
|---|---|
| Quá thấp | Consumer có thể chờ network round-trip và không tận dụng hết năng lực |
| Vừa phải | Giữ số message đang xử lý ở mức phù hợp với concurrency và tài nguyên |
| Quá cao | Tăng số message unacknowledged, bộ nhớ và thời gian chờ; có thể làm một consumer giữ quá nhiều việc |

Trong Spring AMQP, prefetch được cấu hình trên listener container hoặc container factory. Giá trị phù hợp phụ thuộc thời gian xử lý, kích thước message, concurrency, số consumer và khả năng của broker.

Prefetch không thay thế ack. Message vẫn phải được xác nhận theo ack mode đã chọn. Prefetch lớn không làm xử lý nhanh hơn nếu database hoặc dịch vụ downstream đã là nút thắt. Cũng cần xem xét giới hạn số message đang được giữ trong bộ nhớ và thời gian tối đa một delivery có thể ở trạng thái unacknowledged.

## 9. Redelivery, duplicate và idempotency

Khi message được giao lại, RabbitMQ có thể đánh dấu cờ redelivered trong metadata. Cờ này cho biết message có thể đã được giao trước đó; nó không phải khóa chống trùng và cũng không chứng minh consumer trước đã chạy tới bước nghiệp vụ nào.

Consumer cần dùng event ID hoặc message ID ổn định để chống xử lý trùng. Ví dụ, lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ:

~~~text
BEGIN TRANSACTION

Nếu eventId đã có trong inbox:
    không thực hiện side effect lần nữa
Ngược lại:
    áp dụng thay đổi nghiệp vụ
    lưu eventId vào inbox

COMMIT
Gửi ACK
~~~

Inbox cần unique constraint trên event ID hoặc khóa chống trùng được chọn. Nếu xử lý thất bại và transaction rollback, dấu mốc inbox cũng phải rollback để lần giao lại có thể thử lại.

Nếu consumer gọi dịch vụ bên ngoài, database transaction không thể rollback side effect từ xa. Hãy truyền event ID làm idempotency key cho dịch vụ đích nếu hỗ trợ hoặc dùng quy trình đối soát. Không chỉ dựa vào cờ redelivered để quyết định bỏ qua message.

## 10. Ack theo lô và xử lý song song

Ack theo lô có thể giảm số frame giao thức khi consumer xử lý tuần tự. Với basic.ack multiple=true, broker xác nhận tất cả delivery chưa ack đến delivery tag được chỉ định trên channel.

Cần thận trọng khi xử lý song song. Giả sử consumer nhận delivery tag 10, 11 và 12. Nếu tác vụ 12 hoàn thành trước nhưng 10 và 11 chưa xong, ack tag 12 với multiple=true có thể xác nhận cả 10 và 11. Khi đó, nếu tiến trình dừng, hai công việc chưa hoàn tất có thể bị mất khỏi queue.

Các lựa chọn:

- Dùng multiple=false để ack từng delivery độc lập.
- Chỉ ack theo lô khi biết tất cả delivery trước đó trên channel đã hoàn tất.
- Dùng consumer concurrency và channel riêng theo cách container quản lý.
- Giới hạn prefetch để tránh quá nhiều delivery cùng tồn tại.
- Kiểm thử tình huống hoàn tất không theo thứ tự và channel đóng giữa chừng.

Không chia sẻ một Channel tùy ý giữa các thread. Channel là đối tượng giao thức có phạm vi và vòng đời riêng; hãy tuân theo cách Spring AMQP container quản lý channel và listener.

## 11. Publisher confirms và Spring Modulith publication registry

Trong ứng dụng Spring Modulith, Event Publication Registry theo dõi publication của application event và hỗ trợ phục hồi publication chưa hoàn tất. Khi event được externalize qua RabbitMQ adapter, producer-side publication chỉ nên được đánh dấu hoàn tất sau khi adapter đạt mức gửi thành công đã quy định.

Publisher confirms là phản hồi từ RabbitMQ tới producer. Consumer acknowledgements là phản hồi từ consumer tới broker. Hai cơ chế không thay thế nhau.

Một luồng hoàn chỉnh có thể được hiểu như sau:

- Module nghiệp vụ commit và application event được ghi nhận.
- Externalization adapter publish message.
- Producer nhận publisher confirm theo cấu hình.
- Adapter hoàn tất publication mà registry theo dõi.
- RabbitMQ giao message cho consumer.
- Consumer xử lý nghiệp vụ và gửi consumer ack.
- Broker loại message khỏi queue.

Publication registry của producer không theo dõi việc consumer đã commit nghiệp vụ hay chưa. Nếu cần biết trạng thái xử lý cuối cùng, consumer cần phát event phản hồi, cập nhật trạng thái xử lý hoặc cung cấp metric/audit riêng.

Publisher confirm cũng cần được cấu hình rõ trong RabbitMQ client. Nếu adapter chỉ nhận được kết quả gửi vào buffer nội bộ mà không chờ confirm, registry có thể đánh dấu publication hoàn tất quá sớm. Hãy xác minh behavior của adapter cụ thể thay vì suy ra từ việc gọi RabbitTemplate.convertAndSend.

## 12. Transaction và giới hạn bảo đảm

Consumer ack và transaction database thường không nằm trong cùng một giao dịch nguyên tử. Một số cấu hình Spring AMQP có thể phối hợp transaction channel và transaction manager, nhưng không nên giả định chúng tạo exactly-once end-to-end giữa RabbitMQ, database và dịch vụ ngoài.

Với xử lý nghiệp vụ dựa trên database, thứ tự phổ biến là commit dữ liệu rồi ack. Nếu ack thất bại sau commit, message được giao lại và idempotency ngăn side effect trùng. Nếu ack trước commit, có nguy cơ mất message khi transaction rollback hoặc tiến trình dừng.

Với thao tác không thể lặp như gửi tiền, gửi email hoặc tạo vận đơn ở hệ thống ngoài, hãy dùng idempotency key, inbox/outbox hoặc trạng thái workflow có thể đối soát. Ack chỉ phản ánh consumer đã chấp nhận hoàn tất delivery theo logic của nó; nó không tự đảm bảo mọi side effect phân tán đã hoàn tất đúng một lần.

## 13. Quan sát acknowledgement

Theo dõi acknowledgement giúp phát hiện consumer chậm, lỗi lặp và message bị giữ quá lâu.

Các chỉ số hữu ích:

- Số message Ready và Unacknowledged trên từng queue.
- Consumer count và prefetch hiện tại.
- Tốc độ delivery, ack, nack và reject.
- Số redelivery và số message dead-letter.
- Thời gian từ delivery đến ack.
- Số channel đóng do protocol error hoặc ack sai delivery tag.
- Tuổi message lâu nhất và tỷ lệ retry thành công.

Log nên chứa event ID, message ID, queue, delivery tag trong phạm vi xử lý, redelivered flag, thời gian bắt đầu/kết thúc, kết quả nghiệp vụ và nguyên nhân reject/nack. Không dùng delivery tag làm định danh lâu dài vì nó chỉ có ý nghĩa trong channel.

Cảnh báo khi số Unacknowledged tăng liên tục, consumer không ack trong thời gian dự kiến, queue backlog vượt ngưỡng hoặc dead-letter tăng đột biến. Khi điều tra, cần phân biệt consumer xử lý chậm với message bị giao lại do connection/channel mất.

## 14. Kiểm thử acknowledgement

Kiểm thử cần xác nhận cả hành vi broker và kết quả nghiệp vụ. Unit test của listener có thể kiểm tra nhánh xử lý, nhưng integration test với RabbitMQ hoặc môi trường tương thích mới xác minh được ack mode, requeue, DLX và redelivery.

Các tình huống nên kiểm tra:

- Listener thành công thì message được ack và biến mất khỏi queue.
- Listener thất bại trong AUTO mode thì container áp dụng đúng reject/requeue policy.
- MANUAL mode gửi ack đúng delivery tag và channel.
- Reject/nack với requeue=false chuyển message tới DLQ khi topology được cấu hình.
- Requeue=true tạo redelivery và không gây vòng lặp retry vô hạn.
- Consumer dừng trước ack khiến message chưa xác nhận được giao lại.
- Consumer commit database rồi mất ack không tạo side effect trùng khi redelivery.
- Prefetch giới hạn số delivery unacknowledged theo cấu hình.
- Ack multiple không xác nhận nhầm delivery chưa hoàn tất.
- Publisher confirm và consumer ack được kiểm tra như hai ranh giới riêng.
- Channel đóng hoặc delivery tag không hợp lệ được phát hiện và quan sát.

Hãy dùng message ID/event ID cố định trong test để kiểm tra idempotency. Với retry queue dùng TTL, kiểm tra cả thời gian chờ, số lần thử và tuyến chuyển cuối cùng sang parking queue.

## 15. Lỗi thường gặp

**Dùng NONE cho công việc nghiệp vụ cần bảo đảm.** Broker auto-ack khi giao message nên tiến trình dừng giữa lúc xử lý có thể làm mất message. Hãy chọn AUTO hoặc MANUAL theo nhu cầu.

**Ack trước khi commit nghiệp vụ.** Message có thể bị loại khỏi queue dù thay đổi database chưa được lưu. Hãy xác nhận sau khi xử lý thành công.

**Bắt exception rồi trả về bình thường trong AUTO mode.** Container có thể coi listener thành công và ack message. Hãy để exception truyền tới container hoặc áp dụng chính sách xử lý thay thế có kết quả rõ ràng.

**Requeue ngay mọi lỗi.** Lỗi kéo dài tạo vòng lặp nóng. Hãy dùng retry queue có backoff, giới hạn lượt thử và dead-letter.

**Reject không requeue mà không có DLX.** Message có thể bị loại bỏ. Hãy cấu hình và kiểm tra dead-letter routing trước khi triển khai.

**Ack delivery tag trên channel khác.** Delivery tag thuộc channel nhận message. Hãy xác nhận trên đúng channel và không lưu tag qua vòng đời channel.

**Dùng multiple=true khi xử lý song song.** Có thể ack nhầm các delivery chưa hoàn tất. Hãy ack riêng hoặc quản lý thứ tự hoàn tất.

**Coi publisher confirm là consumer ack.** Producer confirm chỉ xác nhận chặng publish; consumer ack xác nhận chặng xử lý. Hãy theo dõi cả hai nếu cần quan sát end-to-end.

## Kết luận

Acknowledgement của AMQP 0-9-1 quyết định broker làm gì với message sau khi giao cho consumer. basic.ack xác nhận xử lý thành công; basic.reject và basic.nack từ chối delivery với lựa chọn requeue hoặc dead-letter. Trong Spring AMQP, NONE, AUTO và MANUAL xác định ai chịu trách nhiệm gửi acknowledgement.

Để tránh mất message và xử lý trùng, hãy ack sau khi nghiệp vụ hoàn tất, dùng idempotency, giới hạn prefetch, thiết kế retry/DLX có kiểm soát và theo dõi delivery chưa xác nhận. Đồng thời, giữ publisher confirms và consumer acknowledgements thành hai ranh giới riêng trong thiết kế Spring Modulith externalization.

