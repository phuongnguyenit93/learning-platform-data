# Dead-letter event

Trong kiến trúc module, application event giúp module phát sự kiện nghiệp vụ mà không cần biết module nào sẽ xử lý. Cách tổ chức này giảm phụ thuộc trực tiếp và giữ ranh giới nghiệp vụ rõ ràng. Tuy vậy, sau khi một sự kiện được phát, listener vẫn có thể thất bại vì dịch vụ bên ngoài tạm ngừng, dữ liệu không hợp lệ, lỗi lập trình hoặc một điều kiện nghiệp vụ không còn đúng.

Nếu chỉ ghi log rồi bỏ qua lỗi, hệ thống có thể mất một phần công việc cần hoàn tất. Nếu thử lại vô hạn, một sự kiện lỗi có thể chiếm tài nguyên và liên tục gây lỗi. **Dead-letter event** là cách đưa một publication đã hết khả năng thử lại tự động vào vùng cách ly có lưu vết, để con người hoặc một quy trình có kiểm soát quyết định cách xử lý tiếp theo.

Trong Spring Modulith, cần phân biệt hai phần: Event Publication Registry theo dõi việc giao một application event đến từng listener; chính sách dead-letter là phần ứng dụng thiết kế thêm để cách ly, kiểm tra, phát lại hoặc bù trừ các publication không thể xử lý. Registry cung cấp nền tảng bền vững cho việc theo dõi và thử lại, nhưng không tự biến mọi lỗi thành một dead-letter queue có chính sách nghiệp vụ hoàn chỉnh.

## 1. Phân biệt event, publication và dead letter

Một application event biểu diễn một sự kiện đã xảy ra trong miền nghiệp vụ. Ví dụ, module Đơn hàng phát ra sự kiện OrderPaid sau khi thanh toán được xác nhận. Module Kho có thể nhận sự kiện để chuẩn bị giao hàng; module Kế toán có thể nhận cùng sự kiện để ghi nhận doanh thu.

Khi một event có nhiều listener, hệ thống cần theo dõi việc giao đến từng listener riêng biệt. Vì vậy, một event có thể tạo ra nhiều publication. Một listener hoàn tất không có nghĩa tất cả listener khác cũng đã hoàn tất.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Application event | Sự kiện nghiệp vụ được module phát ra | OrderPaid |
| Event publication | Một lần giao event đến một listener cụ thể | OrderPaid gửi đến ShippingListener |
| Incomplete publication | Publication chưa được xác nhận hoàn tất | ShippingListener lỗi khi gọi dịch vụ vận chuyển |
| Retry | Thực hiện lại một publication còn có khả năng thành công | Thử lại sau khi dịch vụ vận chuyển hoạt động |
| Dead letter | Bản ghi cách ly publication đã hết lượt thử hoặc gặp lỗi không thể tự khắc phục | OrderPaid của ShippingListener bị đưa vào vùng cách ly |
| Compensation | Hành động nghiệp vụ để xử lý hậu quả của một bước đã hoàn tất | Hoàn tiền khi không thể tiếp tục xử lý đơn |

Dead letter gắn với **publication và listener cụ thể**, không nhất thiết gắn với toàn bộ event. Nếu module Kho đã xử lý thành công nhưng module Kế toán thất bại, không nên phát lại công việc cho module Kho chỉ vì publication của Kế toán còn lỗi.

Một dead-letter record cần giữ đủ thông tin để nhận diện công việc bị lỗi, tìm nguyên nhân và quyết định cách khôi phục. Bản ghi thường gồm event ID, loại event, listener đích, payload hoặc tham chiếu payload, số lần thử, thời điểm lỗi đầu tiên và gần nhất, loại lỗi, thông báo lỗi, trạng thái xử lý và mã tương quan.

## 2. Luồng xử lý từ publication đến dead letter

Với listener được theo dõi bởi Spring Modulith, Event Publication Registry ghi nhận publication và theo dõi trạng thái hoàn tất. Khi listener xử lý thành công, publication được đánh dấu hoàn tất. Khi listener ném exception, publication chưa được hoàn tất và có thể được xem xét để thử lại.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Module phát event trong giao dịch"] --> B["Registry ghi nhận publication"]
    B --> C["Giao dịch commit"]
    C --> D["Listener xử lý event"]
    D -->|Thành công| E["Publication hoàn tất"]
    D -->|Thất bại| F["Publication còn incomplete"]
    F --> G{"Lỗi tạm thời và còn lượt thử?"}
    G -->|Có| H["Chờ đến thời điểm retry"]
    H --> D
    G -->|Không| I["Lưu dead-letter record"]
    I --> J["Kiểm tra và khắc phục nguyên nhân"]
    J --> K{"Cách xử lý"}
    K -->|Phát lại có kiểm soát| D
    K -->|Bù trừ nghiệp vụ| L["Thực hiện compensation"]
    K -->|Kết thúc có kiểm soát| M["Lưu quyết định và audit"]
~~~

Điểm quan trọng là giao dịch phát event và giao dịch xử lý event thường có vòng đời khác nhau. Với listener chạy sau commit, giao dịch nghiệp vụ ban đầu đã commit trước khi listener xử lý. Vì thế, lỗi của listener không tự động hoàn tác giao dịch đã tạo ra event. Hệ thống cần registry và chính sách phục hồi để theo dõi phần việc còn dang dở.

## 3. Dùng Application Module Listener và Event Publication Registry

Spring Modulith cung cấp annotation **@ApplicationModuleListener** để khai báo listener ở ranh giới module. Annotation này được thiết kế cho xử lý bất đồng bộ và giao dịch riêng sau khi giao dịch phát event commit. Listener có thể tập trung vào hành vi của module nhận mà không buộc module phát phải gọi trực tiếp module nhận.

Ví dụ, module Đơn hàng phát event:

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Module Giao hàng nhận event:

~~~java
@Component
class ShippingEventListener {

    private final ShippingService shippingService;

    ShippingEventListener(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        shippingService.prepareShipment(
            event.orderId(),
            event.eventId()
        );
    }
}
~~~

Event ID nên ổn định trong suốt vòng đời phát lại. Listener có thể dùng ID này làm khóa idempotency để nhận ra một event đã được xử lý trước đó. Đây là điều cần thiết vì retry có thể khiến cùng một event được giao lại sau khi listener đã thực hiện một phần side effect.

Event Publication Registry lưu trạng thái publication cho các listener được quản lý. Trong môi trường cần phục hồi sau khi tiến trình dừng đột ngột, hãy dùng implementation có lưu trữ bền vững phù hợp với hạ tầng của ứng dụng, chẳng hạn JDBC, JPA hoặc MongoDB. Registry chỉ nằm trong bộ nhớ không đủ để bảo đảm trạng thái publication còn nguyên sau khi tiến trình bị dừng.

Spring Modulith cung cấp API **IncompleteEventPublications** để tìm và resubmit các publication chưa hoàn tất. Có thể dùng API này trong thao tác quản trị hoặc trong một tiến trình phục hồi có lịch chạy. Ví dụ sau minh họa việc chọn publication của một event cụ thể để phát lại; cách lấy event ID và lọc listener cần khớp với kiểu event và phiên bản Spring Modulith của ứng dụng.

~~~java
@Component
class PublicationRecovery {

    private final IncompleteEventPublications publications;

    PublicationRecovery(IncompleteEventPublications publications) {
        this.publications = publications;
    }

    void retryOrderPaid(UUID eventId) {
        publications.resubmitIncompletePublications(publication ->
            publication.getEvent() instanceof OrderPaid event
                && event.eventId().equals(eventId)
        );
    }
}
~~~

Lời gọi resubmit chỉ yêu cầu Spring Modulith giao lại publication phù hợp. Nó không tự định nghĩa số lần thử tối đa, thời gian chờ, phân loại lỗi hay quy trình phê duyệt dead letter. Những chính sách này cần được ứng dụng quản lý riêng. Hãy kiểm tra API của đúng phiên bản Spring Modulith đang dùng khi tích hợp, vì các chi tiết phương thức có thể thay đổi giữa các phiên bản.

## 4. Thiết kế chính sách retry

Không phải mọi exception đều nên được xử lý giống nhau. Trước khi retry, hãy phân loại lỗi theo khả năng tự khắc phục.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout, HTTP 503, kết nối cơ sở dữ liệu gián đoạn | Retry sau một khoảng chờ |
| Có thể khắc phục bằng cấu hình hoặc vận hành | Credential hết hạn, dịch vụ đích bị cấu hình sai | Tạm dừng, cảnh báo, retry sau khi sửa cấu hình |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, payload sai định dạng | Cách ly để kiểm tra hoặc sửa dữ liệu |
| Vi phạm quy tắc nghiệp vụ | Đơn đã bị hủy, trạng thái không cho phép giao hàng | Xác minh quy tắc; có thể cần compensation hoặc kết thúc có kiểm soát |
| Lỗi lập trình | Null bất ngờ, lỗi chuyển đổi dữ liệu | Cách ly sau ngưỡng phù hợp và sửa phần mềm |

Với lỗi tạm thời, nên dùng backoff tăng dần. Ví dụ, các lần thử có thể cách nhau 10 giây, 30 giây, 2 phút, 10 phút rồi 30 phút. Thời gian thực tế cần dựa trên đặc tính dịch vụ đích và mức độ khẩn cấp của nghiệp vụ. Có thể thêm jitter để nhiều publication không cùng retry tại một thời điểm.

Một retry policy cần xác định rõ:

- Số lần thử tối đa cho từng loại lỗi hoặc nhóm listener.
- Khoảng chờ giữa các lần thử và thời điểm được phép thử tiếp.
- Điều kiện tạm dừng khi dịch vụ đích đang gặp sự cố diện rộng.
- Cách ghi nhận số lần thử và nguyên nhân của từng lần thất bại.
- Thời điểm chuyển publication sang vùng cách ly.
- Người hoặc tiến trình được quyền yêu cầu phát lại.

Không nên tăng số lần thử vô hạn. Một payload sai định dạng sẽ tiếp tục thất bại dù được gửi lại hàng nghìn lần. Retry vô hạn cũng có thể tạo tải lớn lên dịch vụ đích và làm chậm các publication đang có khả năng thành công.

Nếu cần giới hạn số lần thử, hãy lưu retry state bền vững theo khóa event ID và listener ID. Không suy ra số lần thử chỉ từ số log hoặc số lần tiến trình khởi động lại. Mỗi lần thử cần có một bản ghi có thể truy vết, cùng thời điểm bắt đầu, kết quả và lỗi tương ứng.

## 5. Xây dựng vùng cách ly dead letter

Vùng dead letter là nơi lưu publication không còn được retry tự động. Có thể triển khai bằng một bảng trong cơ sở dữ liệu của ứng dụng hoặc một kho lưu trữ riêng. Thiết kế cần hỗ trợ tra cứu theo event ID, listener, trạng thái và thời điểm lỗi.

Ví dụ về cấu trúc dữ liệu ở mức khái niệm:

~~~text
DeadLetterRecord
- id: UUID
- eventId: UUID
- eventType: String
- listenerId: String
- payload: JSON hoặc payloadReference
- attempts: Integer
- firstFailedAt: Instant
- lastFailedAt: Instant
- nextActionAt: Instant hoặc null
- exceptionType: String
- errorMessage: String
- correlationId: String
- status: NEW | INVESTIGATING | REPLAY_REQUESTED | RESOLVED | COMPENSATED
- createdAt: Instant
- updatedAt: Instant
~~~

Nên có ràng buộc duy nhất cho cặp event ID và listener ID nếu mỗi publication chỉ có một dead-letter record đang hoạt động. Nếu cần lưu lịch sử nhiều lần chuyển vào vùng cách ly, hãy tách bản ghi hiện tại khỏi bảng lịch sử lần thử.

Quy trình chuyển sang dead letter cần bảo đảm bản ghi cách ly được lưu bền vững trước khi publication gốc bị loại khỏi danh sách incomplete hoặc được xử lý như một trường hợp đã kết thúc. Nếu lưu dead-letter record thất bại, publication gốc phải còn khả năng được phục hồi. Khi hai phần dữ liệu nằm trong cùng cơ sở dữ liệu, có thể dùng một giao dịch để phối hợp việc lưu bản ghi và cập nhật trạng thái. Nếu chúng nằm ở hai hệ thống khác nhau, cần thiết kế thao tác lặp an toàn và đối soát để xử lý trường hợp một bên thành công còn bên kia thất bại.

Không nên chỉ lưu chuỗi exception. Cần giữ event ID, loại event, listener đích và dữ liệu đủ để tái hiện tình huống. Tuy nhiên, payload có thể chứa dữ liệu cá nhân, thông tin thanh toán hoặc bí mật vận hành. Hãy chỉ lưu trường cần thiết, mã hóa dữ liệu nhạy cảm, giới hạn quyền truy cập và đặt thời hạn lưu trữ phù hợp.

## 6. Phát lại và compensation

Khi một dead letter được xử lý, người vận hành cần xác định nguyên nhân trước khi phát lại. Các bước thường gồm:

1. Tra cứu event ID, listener đích, số lần thử và lỗi gần nhất.
2. Xác định lỗi do hạ tầng, dữ liệu, thay đổi schema hay quy tắc nghiệp vụ.
3. Khắc phục nguyên nhân, chẳng hạn khôi phục dịch vụ đích hoặc sửa dữ liệu theo quy trình có kiểm soát.
4. Kiểm tra listener có hỗ trợ idempotency và payload còn tương thích với phiên bản hiện tại hay không.
5. Yêu cầu replay đúng publication cần xử lý, ghi người yêu cầu, thời điểm và lý do.
6. Xác nhận publication hoàn tất hoặc chuyển sang trạng thái kết thúc có giải thích.

Không nên phát lại toàn bộ event đến tất cả module nếu chỉ một listener thất bại. Việc phát lại phải giữ event ID ban đầu để listener có thể nhận diện lần giao trùng. Nếu payload đã thay đổi schema, cần có bước chuyển đổi hoặc tương thích ngược trước khi phát lại.

Dead letter cũng không đồng nghĩa với compensation. Replay cố gắng hoàn tất công việc ban đầu. Compensation tạo ra hành động nghiệp vụ mới để đưa hệ thống về một trạng thái chấp nhận được khi không thể hoặc không nên tiếp tục công việc cũ.

Ví dụ, sau khi OrderPaid được phát, module Giao hàng không thể tạo vận đơn vì địa chỉ không hợp lệ. Nếu khách hàng có thể cập nhật địa chỉ, sửa dữ liệu rồi replay là phù hợp. Nếu đơn hàng đã bị hủy và không thể giao nữa, hệ thống có thể cần hoàn tiền hoặc giải phóng phần tồn kho đã giữ. Những hành động này là compensation theo quy tắc nghiệp vụ, không phải thao tác xóa publication để che giấu lỗi.

Mọi thao tác replay, discard hoặc compensation cần có audit trail. Một dead letter chỉ nên được đánh dấu RESOLVED khi có bằng chứng rằng công việc đã được xử lý hoặc có quyết định nghiệp vụ được lưu lại. Không xóa dữ liệu lỗi trước khi giữ đủ thông tin phục vụ đối soát.

## 7. Bảo đảm idempotency khi listener được gọi lại

Retry tạo ra khả năng cùng một event được giao nhiều lần. Listener cần chịu được tình huống này, kể cả khi lần xử lý trước đã tạo side effect nhưng tiến trình dừng trước khi publication được đánh dấu hoàn tất.

Một cách phổ biến là lưu event ID đã xử lý trong cùng giao dịch với thay đổi nghiệp vụ:

~~~java
@Transactional
public void prepareShipment(UUID orderId, UUID eventId) {
    if (!processedEventRepository.registerIfAbsent(eventId)) {
        return;
    }

    shipmentRepository.createFor(orderId);
}
~~~

Repository nên thực hiện thao tác đăng ký nguyên tử trên event ID có unique constraint. Việc đăng ký và thay đổi nghiệp vụ phải nằm trong cùng giao dịch; nếu tạo vận đơn thất bại, giao dịch rollback cả dấu mốc đã đăng ký. Ví dụ trên chỉ phù hợp khi thao tác nghiệp vụ và dấu mốc đã xử lý có thể commit trong cùng một cơ sở dữ liệu. Nếu listener gọi dịch vụ bên ngoài, không thể dựa vào một giao dịch cơ sở dữ liệu để hoàn tác side effect từ xa. Khi đó, hãy truyền event ID làm idempotency key cho dịch vụ đích nếu dịch vụ hỗ trợ, hoặc dùng một quy trình đối soát riêng.

Đừng dùng một cờ đã xử lý được commit trước khi side effect hoàn tất. Nếu tiến trình dừng sau khi ghi cờ nhưng trước khi tạo vận đơn, lần retry tiếp theo có thể bỏ qua công việc còn thiếu. Dấu mốc idempotency và thay đổi nghiệp vụ cần được phối hợp theo một ranh giới nhất quán.

## 8. Quan sát và vận hành

Dead-letter flow chỉ hữu ích khi đội vận hành nhìn thấy publication nào đang chậm, lỗi ở listener nào và nguyên nhân gì đang lặp lại. Nên theo dõi ít nhất các chỉ số sau:

- Số incomplete publication hiện tại, phân theo listener hoặc module nhận.
- Tuổi của incomplete publication lâu nhất.
- Số lần retry và tỷ lệ retry thành công.
- Số dead-letter record mới trong từng khoảng thời gian.
- Thời gian từ lúc phát event đến khi publication hoàn tất.
- Số replay thành công, replay thất bại và compensation đã thực hiện.

Log có cấu trúc nên chứa event ID, event type, listener ID, correlation ID, attempt number, exception type và thời điểm retry tiếp theo. Tránh ghi toàn bộ payload vào log. Một dashboard có thể nhóm theo module nhận để nhanh chóng nhận ra một listener đang tạo ra nhiều incomplete publication.

Cần cảnh báo khi tuổi publication vượt ngưỡng nghiệp vụ, số dead letter tăng đột biến hoặc retry liên tục thất bại. Một publication chậm vài giây có thể chấp nhận được với tác vụ nền; một publication liên quan đến xác nhận thanh toán có thể cần cảnh báo sớm hơn.

Quy trình vận hành nên quy định ai được xem payload, ai được replay, ai được discard và ai phê duyệt compensation. Các hành động này cần được ghi nhận để tránh nhiều người cùng phát lại một publication hoặc đưa ra các quyết định trái ngược.

## 9. Kiểm thử luồng retry và dead letter

Nên kiểm thử với implementation lưu trữ publication thực tế của ứng dụng trong integration test. Các tình huống quan trọng gồm:

- Listener thành công thì publication được đánh dấu hoàn tất.
- Listener ném exception thì publication vẫn được nhận diện là incomplete.
- Resubmit đúng publication làm listener được gọi lại.
- Lỗi tạm thời được retry theo thời gian chờ đã cấu hình.
- Khi hết số lần thử, dead-letter record được lưu với event ID và listener chính xác.
- Nếu lưu dead-letter record thất bại, publication gốc vẫn có thể được phục hồi.
- Replay không tạo side effect trùng khi listener đã xử lý event trước đó.
- Event có nhiều listener chỉ phát lại publication còn lỗi.
- Tiến trình khởi động lại không làm mất trạng thái publication đã lưu bền vững.
- Replay và compensation tạo audit record có thể truy vết.

Ngoài kiểm thử thành công, hãy kiểm thử tình huống tiến trình dừng giữa hai bước: listener đã tạo side effect nhưng chưa hoàn tất publication; dead-letter record đã lưu nhưng thao tác cập nhật publication gốc chưa hoàn tất; hoặc dịch vụ đích trả lỗi trong lúc đang replay. Những tình huống này giúp kiểm tra tính lặp an toàn và khả năng đối soát của thiết kế.

## 10. Những lỗi thiết kế thường gặp

**Coi Event Publication Registry là dead-letter queue hoàn chỉnh.** Registry theo dõi publication và hỗ trợ tìm hoặc resubmit publication chưa hoàn tất. Chính sách số lần thử, phân loại lỗi, lưu dead letter, phê duyệt replay và compensation vẫn cần được ứng dụng định nghĩa.

**Bắt exception rồi trả về bình thường trong listener.** Nếu listener nuốt lỗi và kết thúc như thể xử lý thành công, registry có thể ghi nhận publication hoàn tất dù side effect chưa xảy ra. Chỉ bắt exception khi có xử lý thay thế đầy đủ và trạng thái kết quả được quản lý rõ ràng.

**Retry vô hạn với cùng một khoảng thời gian.** Cách này có thể làm quá tải dịch vụ đích và khiến dữ liệu lỗi không bao giờ được xử lý. Hãy dùng backoff, giới hạn lượt thử và vùng cách ly.

**Đánh dấu publication kết thúc trước khi lưu dead letter.** Nếu thao tác lưu dead letter thất bại sau khi publication đã bị loại khỏi luồng phục hồi, công việc có thể mất dấu. Hãy bảo đảm thứ tự ghi bền vững và có cơ chế đối soát.

**Replay mọi listener của một event.** Việc này có thể lặp lại side effect đã hoàn tất ở module khác. Hãy chọn đúng publication theo listener và event ID.

**Không thiết kế idempotency.** Một listener có thể được gọi lại sau khi side effect đã xảy ra. Hãy phối hợp dấu mốc xử lý với thay đổi nghiệp vụ và dùng idempotency key cho lời gọi từ xa.

**Dùng dead letter để thay thế quyết định nghiệp vụ.** Cách ly chỉ giữ lại công việc cần xem xét. Nó không tự quyết định hoàn tiền, hủy đơn hay giải phóng tồn kho. Các quyết định đó phải đi qua quy tắc nghiệp vụ và quy trình compensation tương ứng.

## Kết luận

Với Spring Modulith, Event Publication Registry giúp theo dõi việc giao application event đến từng listener và giữ lại các publication chưa hoàn tất để phục hồi. API IncompleteEventPublications hỗ trợ tìm và resubmit những publication này. Để xây dựng dead-letter flow đáng tin cậy, ứng dụng cần bổ sung retry policy có giới hạn, vùng cách ly lưu bền vững, idempotency, audit trail, quan sát vận hành và quy trình replay hoặc compensation rõ ràng.

Khi các phần này được phối hợp đúng, lỗi ở một listener không làm mất dấu công việc, không buộc các module khác thực hiện lại side effect đã hoàn tất và vẫn giữ được ranh giới nghiệp vụ giữa các module.

