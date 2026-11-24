# Mã định danh thông điệp, số thứ tự và phát hiện khoảng trống dữ liệu

Trong hệ thống realtime, message có thể được gửi lại sau timeout, đến sai thứ tự do xử lý song song, hoặc bị gián đoạn khi kết nối mất. Muốn phát hiện message trùng và khoảng trống dữ liệu, ứng dụng cần một hợp đồng định danh rõ ràng.

Ba khái niệm thường bị nhầm lẫn là **message ID**, **sequence number** và **RSocket Stream ID**. Message ID nhận diện một message cụ thể; sequence number xác định vị trí của message trong một chuỗi có phạm vi; Stream ID chỉ nhận diện một interaction trong phạm vi kết nối RSocket. Chúng giải quyết các vấn đề khác nhau và không thể thay thế nhau.

Một thiết kế tin cậy cần xác định phạm vi sequence, cách tạo số thứ tự, cách lưu trạng thái nhận, chính sách xử lý trùng/out-of-order, thời điểm gửi ACK và cách replay khi phát hiện gap. Các quyết định này phải gắn với yêu cầu nghiệp vụ về thứ tự, độ đầy đủ, idempotency và thời gian lưu dữ liệu.

## 1. Vì sao cần message ID và sequence number?

Giả sử một producer gửi các sự kiện trạng thái đơn hàng:

~~~text
101: ORDER_CREATED
102: PAYMENT_CONFIRMED
103: ORDER_PACKED
104: ORDER_SHIPPED
~~~

Nếu kết nối bị gián đoạn sau event 102, consumer có thể chỉ nhận được 101, 102 rồi reconnect. Nếu producer phát lại event 102 và tiếp tục với 103, consumer cần nhận biết:

- Event 102 đã xử lý rồi hay chưa?
- Event 103 có phải event tiếp theo hợp lệ không?
- Nếu nhận 104 trước 103, đó là out-of-order hay event 103 đã mất?
- Nếu không nhận 103 trong một khoảng thời gian, cần yêu cầu replay hay lấy snapshot mới?
- Khi consumer ACK, nó xác nhận đã nhận byte, đã nhận message hay đã commit nghiệp vụ?

Nếu chỉ dựa vào thời điểm nhận hoặc Stream ID, ứng dụng không thể trả lời chắc chắn những câu hỏi này. Message ID hỗ trợ nhận diện và deduplicate; sequence number hỗ trợ sắp thứ tự và phát hiện gap.

## 2. Phân biệt các loại định danh

| Giá trị | Mục đích | Phạm vi | Có thể dùng phát hiện gap? |
|---|---|---|---|
| Message ID | Nhận diện một message cụ thể | Toàn hệ thống hoặc namespace producer | Không, chỉ riêng ID không thể hiện thứ tự |
| Sequence number | Vị trí trong chuỗi event | Producer, partition, entity hoặc subscription | Có, nếu chuỗi được định nghĩa liên tục |
| RSocket Stream ID | Nhận diện interaction đang chạy | Một RSocket connection/session | Không, không phải số thứ tự nghiệp vụ |
| Correlation ID | Liên kết request với response/log | Một luồng xử lý hoặc distributed trace | Không |
| Causation ID | Chỉ ra message nào gây ra message hiện tại | Quan hệ giữa các message | Không |
| Cursor/offset | Vị trí đọc trong log hoặc nguồn dữ liệu | Một partition hoặc subscription | Có, theo semantics của nguồn |

Ví dụ một payload nghiệp vụ có thể chứa:

~~~java
public record EventEnvelope(
    String messageId,
    String producerId,
    String partitionKey,
    String epoch,
    long sequence,
    String eventType,
    String schemaVersion,
    Instant occurredAt,
    String correlationId,
    String causationId,
    String payloadHash,
    JsonNode payload
) {}
~~~

Ý nghĩa:

- messageId giữ nguyên qua mọi lần retry của cùng một event.
- producerId xác định nguồn phát.
- partitionKey xác định chuỗi có thứ tự, ví dụ orderId hoặc deviceId.
- epoch phân biệt các thế hệ sequence khi producer được reset hoặc partition được tạo lại.
- sequence là số thứ tự trong partition và epoch.
- eventType/schemaVersion giúp consumer diễn giải payload.
- occurredAt phục vụ quan sát thời gian, không thay thế sequence.
- correlationId và causationId hỗ trợ tracing và quan hệ nhân quả.

## 3. Message ID: nhận diện một message duy nhất

Message ID nên được tạo một lần khi message được hình thành và giữ nguyên trong mọi lần gửi lại. UUID hoặc ULID là các lựa chọn phổ biến:

~~~java
String messageId = UUID.randomUUID().toString();
~~~

ULID có phần thời gian giúp sắp xếp gần đúng theo thời điểm tạo, nhưng không nên dùng thứ tự từ ULID để thay thế sequence nghiệp vụ. Đồng hồ giữa các máy có thể lệch và nhiều message có thể được tạo đồng thời.

Một message ID tốt cần:

- Đủ duy nhất trong phạm vi mà consumer dùng để deduplicate.
- Không đổi khi retry hoặc replay.
- Không bị tái sử dụng cho nội dung khác.
- Có thể được lưu làm khóa idempotency.
- Có namespace hoặc producer identity nếu hệ thống cần kiểm tra nguồn phát.

Không tạo message ID mới ở mỗi lần retry. Nếu cùng một nghiệp vụ được gửi lại với ID mới, consumer không thể nhận ra đó là bản sao của message cũ.

Nếu một lệnh nghiệp vụ được gửi lại có chủ đích như một lệnh mới, nó cần ID mới; nếu chỉ truyền lại cùng lệnh do chưa biết lần trước đã thành công hay chưa, phải giữ ID cũ.

## 4. Sequence number: thứ tự trong một phạm vi xác định

Sequence number là số tăng đơn điệu trong một chuỗi. Nó chỉ có ý nghĩa khi biết chuỗi đó thuộc về ai và phạm vi nào.

Ví dụ:

~~~text
device-A / epoch-3:  1, 2, 3, 4, 5, ...
device-B / epoch-3:  1, 2, 3, 4, 5, ...
order-1001 / epoch-1: 1, 2, 3, ...
order-1002 / epoch-1: 1, 2, 3, ...
~~~

Không nhất thiết phải có một sequence toàn cục cho toàn hệ thống. Sequence theo partition thường dễ mở rộng hơn và cho phép xử lý song song giữa các partition.

Một khóa chuỗi có thể là:

~~~text
(producerId, partitionKey, epoch)
~~~

Consumer chỉ so sánh sequence trong cùng khóa. Sequence 12 của device-A không có quan hệ thứ tự với sequence 12 của device-B.

### Chọn partition key

Chọn partition key theo đơn vị cần giữ thứ tự:

- orderId nếu các event của cùng một đơn hàng phải theo thứ tự.
- deviceId nếu các lệnh và trạng thái của cùng thiết bị phải theo thứ tự.
- accountId nếu các thay đổi số dư cần được tuần tự hóa theo tài khoản.
- tenantId nếu nghiệp vụ cần thứ tự trong phạm vi tenant, nhưng cách này có thể tạo partition quá nóng.

Partition quá rộng gây tranh chấp và hạn chế song song; partition quá nhỏ có thể làm mất thứ tự mà nghiệp vụ cần. Phải chọn theo invariant của domain.

## 5. Tạo sequence an toàn khi có nhiều producer

Nếu chỉ có một producer ghi vào một partition, sequence có thể được tăng tuần tự trong bộ nhớ hoặc trong storage. Khi nhiều instance cùng phát event cho một partition, cần một cơ chế cấp số thứ tự nhất quán.

Các cách phổ biến:

- Một leader/owner duy nhất cho mỗi partition.
- Bộ đếm được cập nhật nguyên tử trong database.
- Offset do durable log/broker cấp trong partition.
- Một sequencer service quản lý thứ tự cho khóa nghiệp vụ.

Không dùng biến AtomicLong riêng trong từng instance nếu nhiều instance cùng phát cho một partition. Mỗi instance sẽ có dãy số riêng và tạo ra sequence trùng hoặc không liên tục.

### Gắn sequence với commit nghiệp vụ

Nếu consumer dùng sequence để phát hiện gap, sequence nên phản ánh thứ tự event đã được commit và công bố. Cần tránh cấp sequence trong một thao tác rồi để transaction rollback nhưng sequence vẫn bị tiêu thụ, nếu consumer hiểu mọi số bị thiếu là event thất lạc.

Một mô hình phổ biến là transactional outbox:

1. Trong cùng transaction nghiệp vụ, cập nhật dữ liệu domain.
2. Cấp sequence cho partition bằng thao tác có khóa/atomic.
3. Ghi outbox event với message ID và sequence đó.
4. Commit transaction.
5. Publisher đọc outbox và gửi event tới RSocket consumer.
6. Retry gửi lại cùng event với cùng ID và sequence.

Nếu dùng database sequence có thể có khoảng trống do rollback hoặc cache cấp số. Khi đó không được mặc định mọi khoảng trống số học là event bị mất. Hãy dùng offset có semantics liên tục theo partition, hoặc định nghĩa rõ sequence chỉ tăng chứ không đảm bảo không có số bị bỏ.

## 6. Epoch và reset sequence

Sequence có thể phải bắt đầu lại khi producer được thay thế, partition được tái tạo hoặc trạng thái được khôi phục từ snapshot. Nếu chỉ dùng sequence, consumer có thể nhầm event mới sequence 1 với event cũ sequence 1.

Epoch (generation) giải quyết vấn đề này:

~~~text
producer-7 / device-A / epoch-12 / sequence 100
producer-7 / device-A / epoch-13 / sequence 1
~~~

Consumer chỉ so sánh sequence khi epoch giống nhau. Khi epoch thay đổi, phải có quy tắc chuyển thế hệ:

- Epoch mới được công bố hoặc xác thực.
- Consumer nhận snapshot/checkpoint khởi đầu cho epoch mới.
- Event từ epoch cũ đến muộn được nhận diện và xử lý theo chính sách.
- Không tự động chấp nhận epoch bất kỳ do client gửi nếu điều đó có thể cho phép reset sequence để vượt dedup.

Nếu sequence dùng số nguyên 64-bit, nguy cơ tràn rất thấp trong phần lớn ứng dụng nhưng vẫn cần định nghĩa hành vi. Không để phép tăng long âm thầm quay vòng; dùng epoch mới hoặc từ chối khi đạt giới hạn.

## 7. RSocket Stream ID không phải sequence nghiệp vụ

RSocket gán Stream ID cho mỗi interaction trên một connection. ID này giúp protocol ghép frame với đúng request/stream đang hoạt động.

Stream ID:

- Chỉ có ý nghĩa trong phạm vi connection/session.
- Được dùng để phân biệt các interaction đồng thời.
- Có thể được cấp lại trên connection khác.
- Không biểu diễn thứ tự event trong domain.
- Không phải message ID và không phải cursor bền vững.

Ví dụ một request-stream có Stream ID 5 có thể phát hàng nghìn payload. Mỗi payload vẫn cần message ID hoặc sequence riêng nếu nghiệp vụ cần deduplicate hoặc phát hiện gap.

Sau reconnect, một interaction mới có thể có Stream ID khác. Không dùng Stream ID làm khóa lưu lịch sử, idempotency key hoặc sequence checkpoint.

## 8. Phát hiện duplicate bằng message ID

Consumer nên lưu message ID đã xử lý trong một khoảng thời gian phù hợp với retry/replay window. Khi nhận lại cùng ID:

- Nếu nội dung và sequence khớp, coi là duplicate và không thực hiện tác dụng phụ lần nữa.
- Nếu cùng ID nhưng payload hash khác, coi là conflict hoặc lỗi producer.
- Nếu ID chưa tồn tại nhưng sequence đã được xử lý, kiểm tra xem đây là bản sao được tạo ID mới hay lỗi hợp đồng.

Payload hash nên được tính trên biểu diễn đã chuẩn hóa của nội dung nghiệp vụ và các trường định danh quan trọng. Nếu cùng một JSON được serialize với thứ tự property khác nhau, hash trên byte thô có thể khác dù dữ liệu logic giống nhau; hãy chọn quy tắc canonicalization rõ ràng.

Deduplication phải được thực hiện nguyên tử với tác dụng phụ nghiệp vụ. Nếu chỉ kiểm tra ID rồi xử lý mà không có transaction/unique constraint, hai bản sao đến đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

Ví dụ cấu trúc bảng inbox:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name   VARCHAR(100) NOT NULL,
    producer_id     VARCHAR(100) NOT NULL,
    message_id      VARCHAR(100) NOT NULL,
    partition_key   VARCHAR(200) NOT NULL,
    epoch           VARCHAR(100) NOT NULL,
    sequence_no     BIGINT NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, producer_id, message_id),
    UNIQUE (consumer_name, producer_id, partition_key, epoch, sequence_no)
);
~~~

Khóa chính ngăn một message ID của producer được xử lý hai lần. Unique constraint trên producer/partition/epoch/sequence giúp phát hiện hai message khác ID cùng chiếm một vị trí trong chuỗi. Nếu message ID được bảo đảm duy nhất toàn cục, có thể chọn khóa chính đơn giản hơn; hãy làm cho phạm vi khóa trong schema khớp với hợp đồng định danh.

Bảng inbox cần được lưu đủ lâu để bao phủ khoảng thời gian producer có thể retry hoặc hệ thống có thể replay. Xóa dedup record quá sớm sẽ khiến event cũ được xử lý lại.

## 9. Phát hiện gap và out-of-order

Giả sử consumer đang chờ sequence 21:

~~~text
Nhận 21 -> xử lý bình thường
Nhận 22 -> xử lý bình thường
Nhận 24 -> thiếu 23, phát hiện gap
Nhận 23 -> xử lý 23, sau đó có thể xử lý 24
~~~

Khi nhận sequence lớn hơn expected sequence, chưa thể kết luận event đã mất. Event đó có thể đang trễ trên mạng, nằm trong queue hoặc được xử lý song song. Đây trước hết là **out-of-order**; gap chỉ trở thành mất dữ liệu được xác nhận sau khi có thêm bằng chứng, timeout hoặc phản hồi từ nguồn.

Một consumer có thể giữ reorder buffer:

- expectedSequence: sequence tiếp theo cần xử lý.
- pending: các event đến trước nhưng còn thiếu event đứng trước.
- maxReorderWindow: khoảng cách tối đa được phép chờ.
- gapTimeout: thời gian chờ event bị thiếu trước khi yêu cầu replay hoặc chuyển sang snapshot.

~~~mermaid
flowchart TD
    A[Nhận event] --> B{Message ID đã xử lý?}
    B -->|Có| C[Duplicate: bỏ tác dụng phụ]
    B -->|Không| D{Sequence so với expected}
    D -->|Nhỏ hơn| E[Stale hoặc duplicate: đối chiếu inbox]
    D -->|Bằng| F[Commit event kế tiếp]
    F --> G[Tăng expected và drain pending]
    D -->|Lớn hơn| H[Lưu vào reorder buffer]
    H --> I[Đánh dấu gap và chờ]
    I --> J{Gap được lấp đầy?}
    J -->|Có| F
    J -->|Hết timeout / vượt window| K[Yêu cầu replay hoặc snapshot]
~~~

Không xử lý sequence 24 trước 23 nếu nghiệp vụ yêu cầu thứ tự. Với dữ liệu trạng thái có thể bỏ qua trung gian, có thể chọn chính sách latest-state nhưng cần chứng minh việc bỏ qua không vi phạm invariant.

## 10. Ví dụ logic SequenceTracker

Ví dụ dưới đây minh họa phần quyết định khi nhận event. Trong hệ thống thực, pending buffer, expected sequence và thao tác commit cần được quản lý đồng bộ hoặc lưu bền vững theo partition; không dùng một object trong bộ nhớ làm nguồn sự thật sau restart.

~~~java
enum ReceiveDecision {
    READY_TO_COMMIT,
    DUPLICATE_OR_STALE,
    BUFFERED_GAP,
    CONFLICT,
    RESYNC_REQUIRED
}

final class SequenceTracker {

    private final int maxPending;
    private long expectedSequence;
    private final NavigableMap<Long, EventEnvelope> pending =
        new TreeMap<>();

    SequenceTracker(long firstExpectedSequence, int maxPending) {
        this.expectedSequence = firstExpectedSequence;
        this.maxPending = maxPending;
    }

    synchronized ReceiveDecision accept(EventEnvelope event) {
        long sequence = event.sequence();

        if (sequence < 0) {
            return ReceiveDecision.CONFLICT;
        }

        if (sequence < expectedSequence) {
            return ReceiveDecision.DUPLICATE_OR_STALE;
        }

        if (sequence == expectedSequence) {
            return ReceiveDecision.READY_TO_COMMIT;
        }

        EventEnvelope previous = pending.get(sequence);

        if (previous != null) {
            if (!previous.messageId().equals(event.messageId())
                    || !previous.payloadHash().equals(event.payloadHash())) {
                return ReceiveDecision.CONFLICT;
            }
            return ReceiveDecision.BUFFERED_GAP;
        }

        if (sequence - expectedSequence > maxPending
                || pending.size() >= maxPending) {
            return ReceiveDecision.RESYNC_REQUIRED;
        }

        pending.put(sequence, event);

        return ReceiveDecision.BUFFERED_GAP;
    }

    synchronized Optional<EventEnvelope> nextPending() {
        return Optional.ofNullable(
            pending.get(expectedSequence));
    }

    synchronized void markCommitted(long sequence) {
        if (sequence != expectedSequence) {
            throw new IllegalStateException(
                "Unexpected committed sequence: " + sequence);
        }

        expectedSequence++;
        pending.remove(sequence);
    }
}
~~~

Đây là bộ khung minh họa, không phải consumer hoàn chỉnh. firstExpectedSequence phải được nạp từ checkpoint đã commit cộng một; nếu chưa có checkpoint, lấy giá trị bắt đầu từ hợp đồng producer hoặc snapshot. Luồng thực tế cần:

1. Kiểm tra message ID và payload hash.
2. Kiểm tra partitionKey và epoch trước khi so sequence.
3. Commit inbox record và tác dụng phụ nghiệp vụ trong cùng transaction nếu có thể.
4. Chỉ gọi markCommitted sau khi commit thành công.
5. Sau đó drain event có sequence kế tiếp từ pending.
6. Nếu process crash, khôi phục expected sequence từ checkpoint bền vững.
7. Dùng gap timer/replay policy bên ngoài tracker, không để pending buffer tăng vô hạn.

Nếu hai thread cùng xử lý một partition, cần serialization theo partition hoặc transaction/locking ở storage. synchronized trong ví dụ chỉ bảo vệ một instance trong JVM, không đồng bộ nhiều replica.

## 11. Xác định gap thật hay chỉ là event đến trễ

Nhận sequence 105 trong khi đang chờ 103 có thể có nhiều nguyên nhân:

- Event 103 và 104 đang bị trễ.
- Publisher phát song song và event hoàn tất không theo thứ tự.
- Broker phân phối từ nhiều partition.
- Consumer lọc một loại event nhưng sequence lại được cấp trên toàn bộ event.
- Producer bị crash sau khi cấp sequence nhưng trước khi publish.
- Event bị mất hoặc bị xóa khỏi retention.
- Consumer đã chuyển sang epoch mới nhưng nhận event cũ đến muộn.

Trước khi báo mất dữ liệu, hãy kiểm tra:

- Sequence có cùng producer, partition và epoch không?
- Subscription có nhận mọi event trong sequence scope không?
- Nguồn có đảm bảo thứ tự publish không?
- Có khoảng thời gian reorder hợp lý không?
- Event bị thiếu còn trong retention không?
- Có snapshot hoặc checkpoint thay thế được không?

Nếu subscription chỉ nhận event type A nhưng sequence được đánh trên cả A, B và C, các số bị thiếu có thể là event B/C bị lọc có chủ đích. Khi đó cần sequence riêng cho subscription hoặc một cursor có semantics theo log nguồn.

## 12. Reorder window và gap timeout

Không nên yêu cầu replay ngay khi nhận một sequence lớn hơn expected. Mạng và xử lý song song có thể gây đảo thứ tự ngắn hạn.

Một chính sách có thể gồm:

- **Reorder window:** số sequence hoặc số byte tối đa được giữ chờ.
- **Gap timeout:** thời gian chờ event bị thiếu.
- **Max pending count:** giới hạn số event đang chờ.
- **Max pending bytes:** giới hạn tổng byte trong reorder buffer.
- **Retry limit:** số lần yêu cầu replay.
- **Resync policy:** snapshot hoặc reset checkpoint khi không thể replay.

Ví dụ:

~~~text
expected = 103
receive 105 -> buffer 105, gap [103..104]
receive 104 -> buffer 104, vẫn chờ 103
receive 103 -> commit 103, drain 104, drain 105
~~~

Nếu 103 không đến trong thời gian cho phép, consumer gửi ReplayRequest từ sequence 103. Nếu nguồn xác nhận 103 không còn trong retention, consumer phải lấy snapshot mới và tiếp tục từ checkpoint của snapshot.

Timeout cần dựa trên latency p99 và SLA của hệ thống, không chọn tùy tiện. Quá ngắn gây replay thừa; quá dài khiến dữ liệu mới bị giữ lại quá lâu.

## 13. ACK: nhận, xử lý và commit là ba mức khác nhau

Từ ACK có thể mang nhiều ý nghĩa. Một hệ thống cần định nghĩa chính xác ACK xác nhận điều gì:

| Loại ACK | Ý nghĩa | Có thể xóa event khỏi durable log? |
|---|---|---|
| Received ACK | Consumer đã nhận message | Thường chưa, vì chưa chắc đã xử lý |
| Accepted ACK | Consumer đã chấp nhận vào hàng đợi bền vững | Có thể theo chính sách lưu trữ/replication |
| Processed ACK | Handler đã xử lý xong | Chỉ khi xử lý có tính bền vững |
| Committed ACK | Tác dụng phụ và checkpoint đã commit | Có thể tiến checkpoint theo semantics đã thống nhất |

Với event quan trọng, ACK nên được gửi sau khi tác dụng phụ nghiệp vụ và checkpoint được commit. Nếu ACK trước commit rồi process crash, producer có thể xóa event trong khi consumer chưa lưu kết quả.

### Cumulative ACK

Cumulative ACK xác nhận mọi sequence đến một giá trị đã được xử lý liên tục. Nếu consumer đã xử lý 101 và 102 nhưng đang chờ 103, rồi nhận 104, highest contiguous committed sequence vẫn là 102 chứ không phải 104.

Có thể gửi:

~~~java
public record EventAck(
    String partitionKey,
    String epoch,
    long highestContiguousSequence,
    String consumerId
) {}
~~~

Nếu xử lý out-of-order, có thể dùng selective ACK/range để báo các sequence đã có nhưng chưa lấp gap. Tuy nhiên, producer chỉ được xóa dữ liệu theo quy tắc an toàn, thường dựa trên contiguous checkpoint.

## 14. Delivery semantics: at-most-once, at-least-once và effectively-once

Message ID, sequence và ACK giúp phát hiện trùng và khôi phục, nhưng không tự tạo ra exactly-once end-to-end.

- **At-most-once:** không gửi lại sau khi không rõ kết quả; có thể mất message.
- **At-least-once:** retry/replay cho tới khi có ACK; consumer có thể nhận trùng.
- **Effectively-once:** at-least-once kết hợp deduplication và tác dụng phụ idempotent/transactional để kết quả quan sát được như xử lý một lần trong phạm vi hệ thống được kiểm soát.

Không nên hứa exactly-once chỉ vì có message ID. Nếu gửi email, gọi API ngoài hoặc điều khiển thiết bị, tác dụng phụ có thể không nằm trong cùng transaction với inbox database. Cần idempotency key ở downstream hoặc quy trình reconciliation.

## 15. Lưu inbox và checkpoint một cách nguyên tử

Một consumer bền vững thường lưu:

- Inbox: message ID đã nhận/xử lý và payload hash.
- Checkpoint: sequence liên tục cao nhất đã commit cho mỗi partition/epoch.
- Pending/reorder: các event đến sớm nhưng chưa thể xử lý theo thứ tự.
- Domain state: kết quả nghiệp vụ đã cập nhật.

Một transaction có thể thực hiện:

~~~text
BEGIN
  INSERT inbox(message_id, partition, epoch, sequence)
    -- unique constraint chặn duplicate
  APPLY domain change
  UPDATE checkpoint
    SET last_contiguous_sequence = next_sequence
COMMIT
ACK highest contiguous sequence
~~~

Nếu insert inbox gặp duplicate key, đọc trạng thái đã tồn tại và không chạy lại tác dụng phụ. Nếu domain update thất bại, transaction rollback cả inbox và checkpoint để event có thể được retry.

Với downstream không hỗ trợ transaction chung, dùng inbox/outbox, idempotency key hoặc saga/reconciliation. Không cập nhật checkpoint trước khi tác dụng phụ quan trọng được xác nhận.

## 16. Kết hợp message ID và sequence trong RSocket

RSocket cung cấp các interaction model khác nhau; message ID và sequence nên được đặt trong payload hoặc metadata theo hợp đồng ứng dụng.

### Request-response cho publish và ACK

~~~java
@MessageMapping("events.publish")
public Mono<EventAck> publish(
        @Payload EventEnvelope event) {
    return eventService.acceptAndCommit(event);
}
~~~

Client:

~~~java
Mono<EventAck> ack = requester
    .route("events.publish")
    .data(event)
    .retrieveMono(EventAck.class);
~~~

Response nên thể hiện rõ accepted hay committed. Không trả ACK committed nếu event mới chỉ được đưa vào RAM.

### Request-stream cho replay/subscription

~~~java
@MessageMapping("events.subscribe")
public Flux<EventEnvelope> subscribe(
        @Payload SubscriptionRequest request) {
    return eventLog.readFrom(
        request.partitionKey(),
        request.epoch(),
        request.afterSequence());
}
~~~

Consumer có thể mở lại stream từ last committed sequence. Nếu event đã hết retention, server nên trả trạng thái cần snapshot/resync thay vì âm thầm bắt đầu từ event mới nhất.

### Fire-and-forget

~~~java
Mono<Void> sent = requester
    .route("events.ingest")
    .data(event)
    .send();
~~~

send() không phải application ACK. Nếu producer cần biết event đã được commit, hãy dùng request-response hoặc một kênh ACK riêng có message ID/sequence tương ứng.

### Request-channel

Trong channel, mỗi command/event đầu vào vẫn cần ID và sequence riêng nếu cần dedup hoặc gap detection. Response stream có thể trả ACK cho từng command, nhưng ACK phải chỉ rõ message ID/sequence mà nó xác nhận.

## 17. Phân biệt RSocket Resumption với application replay

RSocket Resumption hỗ trợ khôi phục một session sau gián đoạn trong phạm vi trạng thái và buffer của protocol. Cơ chế này có thể giúp tiếp tục trao đổi frame mà không cần ứng dụng tự xây dựng lại mọi interaction.

Tuy nhiên, resumption không thay thế:

- Message ID bền vững.
- Sequence nghiệp vụ.
- Inbox deduplication.
- Commit ACK.
- Cursor đọc từ event log.
- Snapshot/resync sau khi retention hết hạn.

Protocol resume không tự biết consumer đã commit database hay đã thực hiện tác dụng phụ bên ngoài. Nếu server đã gửi frame nhưng client crash trước khi commit, ứng dụng vẫn cần quy tắc retry/dedup. Vì vậy hãy phân biệt **khôi phục transport/session** với **khôi phục tiến độ nghiệp vụ**.

## 18. Snapshot và resynchronization khi gap không thể replay

Nếu event bị thiếu đã vượt retention, replay từ sequence cũ có thể không còn khả thi. Consumer cần lấy snapshot nhất quán và một checkpoint đi kèm.

Quy trình:

1. Consumer phát hiện gap vượt retention hoặc replay trả về cursor expired.
2. Consumer yêu cầu snapshot cho đúng partition/epoch.
3. Server tạo snapshot ở một sequence nhất quán S.
4. Consumer thay thế state local bằng snapshot.
5. Consumer lưu checkpoint S cùng transaction với state.
6. Consumer mở stream từ sequence S + 1.
7. Các event cũ đến muộn được nhận diện theo checkpoint và dedup policy.

Snapshot và checkpoint phải cùng một điểm nhất quán. Nếu snapshot phản ánh state tại S nhưng checkpoint lại ghi S+3, consumer sẽ bỏ qua event S+1 đến S+3. Nếu checkpoint thấp hơn snapshot, các event đã được áp dụng có thể bị phát lại; điều này cần idempotency.

## 19. Quan sát và kiểm thử gap detection

Các metric nên có:

- Duplicate count theo consumer và partition.
- Gap detected count và gap duration.
- Out-of-order event count.
- Reorder buffer size theo số phần tử và byte.
- Replay request/success/failure.
- Cursor lag so với producer head.
- Highest contiguous committed sequence.
- Event bị conflict do cùng sequence nhưng khác message ID.
- Snapshot/resync count.
- Thời gian từ publish đến commit ACK.

Các tình huống kiểm thử:

| Tình huống | Kết quả mong đợi |
|---|---|
| Nhận sequence liên tục | Commit tuần tự, checkpoint tăng |
| Nhận lại cùng message ID | Không chạy tác dụng phụ lần hai |
| Cùng ID nhưng payload hash khác | Báo conflict |
| Hai ID cùng sequence trong một partition/epoch | Phát hiện producer conflict |
| Sequence đến sai thứ tự trong reorder window | Buffer và drain đúng thứ tự |
| Gap không được lấp đầy | Replay sau timeout |
| Gap vượt retention | Snapshot/resync |
| Event từ epoch cũ đến muộn | Không trộn với sequence epoch mới |
| Crash sau domain commit nhưng trước ACK | Retry được deduplicate |
| Crash trước transaction commit | Event được retry và xử lý |
| Nhiều partition | Sequence độc lập, không so sánh chéo |
| Subscription filter bỏ một số event | Không báo gap giả nếu sequence scope được định nghĩa đúng |
| Reconnect/resumption | Stream ID có thể đổi; message ID và checkpoint vẫn có ý nghĩa |

Nên kiểm thử đồng thời nhiều consumer và nhiều replica. Unit test cho SequenceTracker không đủ để xác nhận transaction inbox/checkpoint hoặc replay qua RSocket transport.

## 20. Checklist thiết kế

- Message ID duy nhất và giữ nguyên qua retry.
- Sequence number tăng trong phạm vi partition được định nghĩa.
- Có producerId, partitionKey và epoch khi cần phân biệt nguồn/thế hệ.
- Không dùng timestamp hoặc RSocket Stream ID làm sequence nghiệp vụ.
- Cấp sequence và ghi outbox theo transaction/atomic mechanism.
- Consumer lưu inbox với unique constraint và payload hash.
- Checkpoint chỉ tiến theo highest contiguous committed sequence.
- Out-of-order được buffer trong giới hạn số phần tử và byte.
- Gap timeout, replay window và snapshot policy được xác định.
- ACK nói rõ received, accepted, processed hay committed.
- Tác dụng phụ có idempotency hoặc reconciliation.
- RSocket resumption được phân biệt với application replay.
- Có metric cho duplicate, gap, lag, replay và resync.
- Kiểm thử crash, retry, reorder, epoch reset và nhiều partition.

## 21. Kết luận

Message ID nhận diện một message và giúp consumer deduplicate khi retry. Sequence number xác định thứ tự trong một partition/epoch và giúp phát hiện duplicate, out-of-order cùng gap. RSocket Stream ID chỉ nhận diện interaction trong một connection, không thể dùng làm định danh hoặc checkpoint nghiệp vụ.

Để khôi phục tin cậy, producer cần giữ message ID qua retry và cấp sequence theo một phạm vi rõ ràng; consumer cần lưu inbox, xử lý theo thứ tự, cập nhật checkpoint sau commit và yêu cầu replay khi gap không tự được lấp đầy. Khi dữ liệu đã hết retention, snapshot/resynchronization phải đi cùng checkpoint nhất quán.

RSocket cung cấp transport, multiplexing, flow control và resumption; ứng dụng vẫn phải thiết kế idempotency, ACK, sequence, cursor và persistence theo yêu cầu nghiệp vụ. Phân tách đúng các lớp này giúp hệ thống realtime phát hiện mất dữ liệu, xử lý message trùng và phục hồi sau gián đoạn một cách có thể kiểm chứng.

Tài liệu tham khảo:
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Resumption](https://rsocket.io/about/protocol/#resumption)
- [Reactive Streams Specification](https://www.reactive-streams.org/)

