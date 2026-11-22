# Source message id và duplicate detection

Trong Spring Integration, producer tạo `Message<?>` rồi gửi message vào channel để các endpoint phía sau xử lý. Mỗi message có một định danh kỹ thuật do Spring quản lý, nhưng định danh đó không tự giải quyết được việc một sự kiện nghiệp vụ bị phát hoặc giao nhiều lần. Muốn phát hiện bản trùng đáng tin cậy, producer và consumer cần thống nhất một khóa đại diện cho **cùng một sự kiện nghiệp vụ**.

## 1. Phân biệt message ID và event ID

`Message<T>` là envelope chứa payload và headers. Khi tạo message, Spring Messaging tự sinh header `id` và `timestamp`. `id` thường là UUID, dùng để nhận diện một message instance trong log, trace hoặc lúc chẩn đoán luồng xử lý. `timestamp` ghi thời điểm message được tạo.

Hai giá trị này có ý nghĩa kỹ thuật:

- `id` trả lời: “Đây là message instance nào?”
- `timestamp` trả lời: “Message instance này được tạo lúc nào?”

Chúng không nhất thiết trả lời được câu hỏi: “Đây có phải cùng một sự kiện đơn hàng mà tôi đã xử lý trước đó không?”. Ví dụ producer nhận cùng một sự kiện `OrderCreated` hai lần và dựng hai `Message` mới. Mỗi message có thể có `id` khác nhau dù payload mô tả cùng một đơn hàng và cùng một sự kiện.

Vì vậy, ứng dụng nên mang theo một khóa ổn định do miền nghiệp vụ hoặc hệ thống nguồn cung cấp, thường gọi là `eventId`, `idempotencyKey` hoặc tên tương đương. Khóa này phải giữ nguyên khi cùng một sự kiện được retry, phát lại hoặc giao lại.

| Giá trị | Ý nghĩa | Dùng cho |
| --- | --- | --- |
| `MessageHeaders.id` | Định danh của message instance do framework tạo | Log, trace, điều tra một lần truyền message |
| `eventId` / `idempotencyKey` | Định danh ổn định của một sự kiện nghiệp vụ | Duplicate detection và idempotent processing |
| `correlationId` | Định danh nhóm message thuộc cùng một cuộc trao đổi hoặc workflow | Liên kết request/reply, saga hoặc các message liên quan |
| `sequenceNumber` / `sequenceSize` | Vị trí và kích thước của một nhóm message có thứ tự | Ghép hoặc xử lý chuỗi message |

Không dùng `correlationId` thay cho `eventId`: nhiều sự kiện khác nhau có thể cùng thuộc một workflow. Tương tự, `sequenceNumber` chỉ mô tả vị trí trong chuỗi, không phải khóa duy nhất của sự kiện.

## 2. Tạo message với khóa ổn định ở producer

Producer nên lấy khóa từ sự kiện nguồn hoặc tạo và lưu khóa một lần trước khi công bố sự kiện. Nếu mỗi lần retry producer lại sinh một UUID mới, consumer sẽ nhìn thấy các khóa khác nhau và không nhận ra đó là cùng một sự kiện.

Ví dụ một producer chuyển sự kiện đơn hàng thành Spring message:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId) {
}

public Message<OrderCreated> toMessage(OrderCreated event) {
    return MessageBuilder.withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("sourceSystem", "order-service")
            .build();
}
```

Khi `build()` tạo message, Spring cung cấp `MessageHeaders.id` cho message instance. Header `eventId` vẫn giữ định danh nghiệp vụ ổn định. Nếu cùng `OrderCreated` được phát lại, producer cần dùng lại `eventId` ban đầu.

Trong hệ thống nhận message từ broker hoặc adapter, header chứa ID của broker có thể được ánh xạ từ metadata của transport. Ví dụ, một adapter có thể cung cấp message ID, partition, offset hoặc delivery metadata riêng. Tên và cách ánh xạ phụ thuộc adapter. Không nên giả định ID của broker luôn giống `MessageHeaders.id`, hoặc luôn được giữ nguyên qua mọi bước chuyển đổi message. Khi cần đối chiếu nguồn, hãy lưu metadata transport vào header có tên rõ ràng và giữ `eventId` nghiệp vụ riêng.

## 3. Vì sao message bị giao trùng?

Duplicate có thể xuất hiện trong các tình huống bình thường của hệ thống phân tán:

- Producer gửi thành công nhưng không nhận được xác nhận do timeout, nên gửi lại.
- Broker giao lại message khi consumer chưa xác nhận, consumer bị dừng hoặc phiên xử lý bị rollback.
- Consumer đã thực hiện tác động nghiệp vụ nhưng bị lỗi trước khi xác nhận message; lần giao sau chạy lại cùng sự kiện.
- Người vận hành phát lại message để khôi phục hoặc chạy bù dữ liệu.
- Nhiều consumer cùng nhận hoặc xử lý đồng thời một sự kiện do cấu hình subscription, retry hay chuyển vùng.

Do đó, không thể chỉ dựa vào việc producer “chỉ gửi một lần” hoặc consumer “thường chỉ nhận một lần”. Hệ thống nên giả định cùng một sự kiện có thể đến nhiều lần và thiết kế thao tác nghiệp vụ theo hướng idempotent.

## 4. Duplicate detection bằng khóa và MetadataStore

Một cách phổ biến trong Spring Integration là lưu các khóa đã tiếp nhận trong `MetadataStore`. Với xử lý đồng thời trên nhiều thread hoặc nhiều instance, cần một triển khai hỗ trợ thao tác nguyên tử như `ConcurrentMetadataStore.putIfAbsent(key, value)`. Kết quả cho biết khóa đã tồn tại hay chưa: chỉ một lần xử lý có thể giành được khóa trong cùng phạm vi lưu trữ được chia sẻ.

Ví dụ dưới đây minh họa bước kiểm tra đầu vào. `metadataStore` là một `ConcurrentMetadataStore` được cấu hình cho ứng dụng:

```java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.messaging.Message;

public boolean isFirstDelivery(
        Message<?> message,
        ConcurrentMetadataStore metadataStore) {

    Object rawEventId = message.getHeaders().get("eventId");
    if (rawEventId == null || rawEventId.toString().isBlank()) {
        throw new IllegalArgumentException("Message is missing eventId");
    }

    String key = "order-created:" + rawEventId;
    return metadataStore.putIfAbsent(key, "PROCESSING") == null;
}
```

Nếu hàm trả về `true`, message đã giành được khóa và có thể đi tiếp vào xử lý. Nếu trả về `false`, khóa đã được ghi nhận; consumer cần áp dụng chính sách duplicate đã chọn, chẳng hạn bỏ qua có ghi log, tăng metric hoặc chuyển message sang luồng kiểm tra. Prefix `order-created:` tạo namespace để khóa của các loại sự kiện khác nhau không va chạm.

Spring Integration cũng cung cấp cơ chế Idempotent Receiver, gồm `IdempotentReceiverInterceptor` và selector dựa trên metadata store, để đánh dấu message trùng tại endpoint. Cơ chế này hữu ích khi muốn đưa quy tắc kiểm tra vào cấu hình endpoint. Hãy cấu hình selector bằng khóa nghiệp vụ ổn định và quyết định rõ handler sẽ bỏ qua, ghi nhận hay xử lý message được đánh dấu duplicate.

## 5. Đặt duplicate detection đúng ranh giới transaction

Một thao tác `putIfAbsent` nguyên tử chỉ giải quyết việc giành quyền xử lý khóa. Nó chưa tự bảo đảm tác động nghiệp vụ chỉ xảy ra một lần trong mọi tình huống lỗi.

Ví dụ, nếu ghi dấu đã xử lý trước rồi ứng dụng dừng trước khi cập nhật đơn hàng, lần giao lại sẽ bị bỏ qua dù nghiệp vụ chưa hoàn tất. Nếu chỉ ghi dấu sau khi cập nhật đơn hàng, hai consumer đồng thời có thể cùng cập nhật trước khi một consumer ghi được khóa.

Khi metadata store và dữ liệu nghiệp vụ dùng chung một cơ sở dữ liệu hỗ trợ transaction, có thể đặt thao tác ghi khóa và cập nhật nghiệp vụ trong cùng transaction. Ví dụ khái niệm:

```java
public boolean handleOnce(Message<OrderCreated> message) {
    String eventId = (String) message.getHeaders().get("eventId");
    if (eventId == null || eventId.isBlank()) {
        throw new IllegalArgumentException("Message is missing eventId");
    }

    String key = "order-created:" + eventId;
    return transactionTemplate.execute(status -> {
        if (metadataStore.putIfAbsent(key, "DONE") != null) {
            return false; // Sự kiện đã được commit trước đó.
        }

        orderService.apply(message.getPayload());
        return true;
    });
}
```

Đoạn mã giả định `metadataStore` và `orderService` tham gia cùng transaction manager và cùng ranh giới commit. Khi `orderService.apply` thất bại, transaction rollback cả thay đổi nghiệp vụ lẫn khóa; khi commit thành công, cả hai được ghi nhận. Nếu metadata store và dữ liệu nghiệp vụ nằm ở hai hệ thống không có transaction chung, đoạn mã này không tạo ra tính nguyên tử. Khi đó nên dùng inbox/outbox, thao tác nghiệp vụ có tính idempotent, hoặc một giao thức phục hồi phù hợp với kiến trúc.

Với xử lý nhiều bước, có thể lưu trạng thái như `PROCESSING`, `COMPLETED` và thông tin lease/thời hạn để phục hồi một lần xử lý bị bỏ dở. Cần xác định rõ khi nào được phép thử lại, cách phát hiện lease hết hạn và cách tránh hai worker cùng tiếp tục một công việc. Không giữ trạng thái `PROCESSING` vĩnh viễn sau lỗi.

## 6. Chọn nơi lưu khóa và thời gian lưu

Phạm vi của metadata store quyết định phạm vi duplicate detection:

- Store trong bộ nhớ của một process chỉ bảo vệ instance đó; restart sẽ mất dữ liệu và instance khác không nhìn thấy khóa.
- Store dùng chung và bền vững, chẳng hạn triển khai dựa trên JDBC hoặc Redis phù hợp với hạ tầng, có thể phối hợp nhiều instance và giữ dữ liệu qua restart.
- Nếu dùng store phân tán, cần xác nhận semantics của thao tác nguyên tử, độ bền, transaction, tính nhất quán và cách xử lý khi store tạm thời không truy cập được.

Khóa cũng cần chính sách hết hạn. Lưu quá ngắn có thể khiến message phát lại muộn bị xử lý như mới; lưu vô hạn khiến metadata tăng liên tục. Thời hạn cần dựa trên cửa sổ retry, thời gian broker có thể redeliver, chính sách replay và yêu cầu nghiệp vụ. Nếu sự kiện cũ có thể được phát lại sau nhiều tháng, cần lưu dấu lâu hơn hoặc có ràng buộc duy nhất trong dữ liệu nghiệp vụ.

Không xóa khóa chỉ vì consumer đã nhận được ACK từ broker. ACK và commit nghiệp vụ là hai sự kiện khác nhau; thứ tự của chúng phải phù hợp với transaction và cơ chế phục hồi của hệ thống.

## 7. Quan sát và chẩn đoán duplicate

Khi log hoặc trace một lần xử lý, nên ghi cả `MessageHeaders.id` và `eventId`, cùng tên channel/endpoint, nguồn message, kết quả duplicate check và trạng thái transaction. Điều này giúp phân biệt hai message instance khác nhau cùng đại diện cho một sự kiện với một message instance được theo dõi qua nhiều endpoint.

Một số dấu hiệu cần theo dõi:

- Tỷ lệ message bị đánh dấu duplicate theo producer, loại sự kiện và endpoint.
- Số lần retry/redelivery, số khóa đang ở trạng thái `PROCESSING` và tuổi của chúng.
- Lỗi hoặc độ trễ khi đọc/ghi metadata store.
- Sự kiện thiếu `eventId`, khóa xung đột bất thường hoặc số lượng khóa tăng nhanh.
- Chênh lệch giữa số message nhận, số sự kiện mới, số sự kiện duplicate và số cập nhật nghiệp vụ đã commit.

Tránh dùng `eventId` làm metric label có cardinality cao. Có thể ghi nó trong log có kiểm soát để tra cứu một sự kiện cụ thể, còn metric nên nhóm theo loại sự kiện, endpoint hoặc kết quả xử lý.

## 8. Quy trình kiểm tra khi triển khai

1. Xác định một sự kiện nghiệp vụ cụ thể và nguồn tạo `eventId`; xác nhận khóa không đổi qua retry và replay.
2. Tạo hai message riêng cho cùng sự kiện. Xác nhận `MessageHeaders.id` có thể khác nhau trong khi `eventId` giống nhau.
3. Gửi đồng thời hai bản của cùng sự kiện qua endpoint. Chỉ một lần được phép thực hiện tác động nghiệp vụ.
4. Làm consumer lỗi trước commit rồi giao lại message. Xác nhận khóa và dữ liệu nghiệp vụ cùng rollback hoặc được phục hồi theo thiết kế.
5. Khởi động lại ứng dụng hoặc chạy trên hai instance để xác minh store có đúng phạm vi và độ bền mong muốn.
6. Phát lại một sự kiện sau khoảng thời gian dài hơn cửa sổ retry dự kiến để kiểm tra chính sách retention.

Khi các điều kiện trên được xác minh, message ID có thể hỗ trợ truy vết từng message instance, còn khóa idempotency giúp bảo vệ tác động nghiệp vụ trước việc giao trùng. Hai loại định danh bổ sung cho nhau và cần được ghi nhận riêng trong runtime của Spring Integration.
