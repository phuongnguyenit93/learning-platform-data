# Chọn chiến lược retry

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua những sự thật nghiệp vụ đã xảy ra. Listener có thể chạy sau commit, chạy bất đồng bộ hoặc được externalize ra broker. Khi listener hoặc hệ thống downstream gặp lỗi tạm thời, retry giúp công việc tiếp tục mà không yêu cầu người dùng gửi lại command. Tuy nhiên, retry sai cách có thể tạo vòng lặp nóng, làm tăng tải lên dependency đang lỗi, gây xử lý trùng hoặc khiến một event cũ chặn toàn bộ luồng.

**Chọn chiến lược retry** là quyết định về việc lỗi nào được thử lại, thử ở đâu, chờ bao lâu, tối đa bao nhiêu lần và khi nào chuyển sang xử lý khác. Chiến lược phù hợp phải dựa trên semantics nghiệp vụ, khả năng idempotency, thời hạn hoàn tất và cơ chế giao nhận đang dùng. Không có một chính sách retry duy nhất phù hợp cho mọi listener hoặc mọi event.

## 1. Retry giải quyết vấn đề gì?

Trong hệ thống bất đồng bộ, một event có thể thất bại vì dependency tạm thời không sẵn sàng. Ví dụ:

- Database tạm hết connection.
- Dịch vụ thanh toán trả HTTP 503.
- Broker hoặc network mất kết nối trong thời gian ngắn.
- API ngoài giới hạn tốc độ và trả 429.
- Một consumer vừa restart và chưa sẵn sàng.
- Transaction gặp deadlock hoặc optimistic locking conflict.

Nếu lỗi có khả năng tự hết sau một khoảng thời gian, retry có thể giúp listener hoàn tất mà không cần can thiệp thủ công.

Retry không sửa được mọi lỗi. Payload sai schema, thiếu dữ liệu bắt buộc, vi phạm domain invariant hoặc credential hết hạn thường không tự trở nên hợp lệ chỉ bằng cách gửi lại cùng một event. Thử lại vô hạn các lỗi như vậy chỉ làm tăng backlog và che khuất nguyên nhân thật.

Mục tiêu của retry là phục hồi lỗi tạm thời trong giới hạn tài nguyên và thời gian đã định, đồng thời giữ cho kết quả nghiệp vụ an toàn khi một thao tác được thực hiện nhiều lần.

## 2. Phân loại lỗi trước khi chọn retry

Bước đầu tiên là phân loại lỗi theo khả năng phục hồi, không chỉ theo exception class.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Network timeout, connection reset, deadlock | Retry có giới hạn và backoff |
| Quá tải | HTTP 429, HTTP 503, broker throttling | Giảm tốc, tôn trọng Retry-After nếu có |
| Phụ thuộc không sẵn sàng | Database failover, dịch vụ đang restart | Retry sau khoảng chờ; có thể kết hợp circuit breaker |
| Dữ liệu không hợp lệ | Payload thiếu field bắt buộc, sai định dạng | Cách ly/DLQ và điều tra |
| Không tương thích schema | Consumer không hỗ trợ version event | Cách ly hoặc chuyển qua upcaster/compatibility path |
| Từ chối nghiệp vụ | Không đủ tồn kho, đơn đã bị hủy | Ghi nhận outcome nghiệp vụ; không retry mù |
| Lỗi cấu hình/quyền | Credential sai, ACL từ chối | Cảnh báo và sửa cấu hình trước khi thử lại |
| Xung đột có thể giải quyết | Optimistic lock conflict | Reload state và retry theo quy tắc domain |

Không phân loại chỉ bằng mã HTTP hoặc tên exception. Ví dụ HTTP 409 có thể là xung đột tạm thời trong một API, nhưng cũng có thể là kết quả nghiệp vụ không thể retry. Tương tự, `DataIntegrityViolationException` thường cần điều tra dữ liệu/constraint, không nên tự động retry như lỗi network.

Mỗi consumer nên có một bảng phân loại lỗi và owner chịu trách nhiệm thay đổi policy.

## 3. Chọn retry boundary

Retry có thể được đặt ở nhiều lớp:

- Application listener hoặc application service.
- Event Publication Registry của Spring Modulith.
- Outbox relay.
- Message broker/consumer container.
- HTTP client gọi dịch vụ ngoài.
- Job hoặc scheduler vận hành.

Mỗi lớp có hiểu biết khác nhau về lỗi và trạng thái. Retry ở lớp gọi HTTP biết response code và Retry-After. Retry ở consumer biết message ID và acknowledgement. Retry qua publication registry biết listener publication nào chưa hoàn tất.

Tránh để nhiều lớp retry cùng một lỗi mà không có giới hạn tổng. Ví dụ HTTP client retry 3 lần, listener retry 4 lần và broker redeliver 5 lần có thể tạo tối đa hàng chục lần gọi downstream cho một event. Hãy xác định một retry owner chính cho mỗi boundary, đồng thời ghi rõ các lớp retry khác đang hoạt động.

Quy tắc hữu ích:
- Retry gần nơi hiểu rõ lỗi nhất.
- Không retry lại toàn bộ workflow nếu chỉ một bước downstream thất bại.
- Không giữ transaction hoặc thread request trong lúc chờ backoff dài.
- Bảo đảm mỗi lớp có timeout và retry budget hữu hạn.
- Ghi nhận tổng số lần thử xuyên các lớp nếu có thể.

## 4. Retry trong Spring Modulith application events

Spring Modulith Event Publication Registry theo dõi publication của application event đến từng listener. Khi listener hoàn tất thành công, registry ghi nhận publication hoàn tất. Nếu listener thất bại hoặc tiến trình dừng trước khi hoàn tất được ghi nhận, publication có thể vẫn ở trạng thái chưa hoàn tất.

Với persistent registry, ứng dụng có thể tìm và resubmit các publication chưa hoàn tất theo API/operation được phiên bản Spring Modulith hỗ trợ. Điều này giúp phục hồi listener sau lỗi hoặc restart.

Cần hiểu đúng phạm vi:

- Registry theo dõi publication đến listener trong ứng dụng.
- Một event có nhiều listener thì mỗi listener có publication riêng.
- Publication chưa hoàn tất không tự nói rõ lỗi là tạm thời hay vĩnh viễn.
- Resubmit có thể gọi listener lại; listener phải idempotent.
- Registry không tự thay thế mọi retry policy, backoff scheduler hoặc DLQ cho broker.
- Registry không theo dõi toàn bộ consumer bên ngoài hoặc trạng thái business workflow.

Nên cấu hình persistent registry khi cần phục hồi sau restart. Cách lưu trữ, transaction manager, API resubmit và actuator integration phụ thuộc phiên bản/implementation; dùng API được hỗ trợ thay vì thao tác trực tiếp vào schema nội bộ.

Với `@ApplicationModuleListener`, listener thường được xử lý bất đồng bộ sau commit theo cấu hình Spring Modulith. Khi xử lý thất bại, cần có cách phát hiện publication chưa hoàn tất và chính sách resubmit có kiểm soát. Không giả định annotation tự cung cấp một lịch retry exponential backoff cho mọi loại lỗi.

## 5. Retry với listener sau commit

`@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ được gọi sau khi transaction phát event commit thành công. Nếu listener thất bại, transaction nghiệp vụ ban đầu đã hoàn tất và không thể rollback lại bằng exception của listener.

Ví dụ:

~~~java
@Component
class InventoryListener {

    private final InventoryService inventory;

    InventoryListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        inventory.reserve(event.orderId(), event.items());
    }
}
~~~

Nếu phần xử lý listener ghi database, cần transaction riêng phù hợp. Với persistent publication registry, trạng thái publication có thể giúp xác định công việc còn chưa hoàn tất để phục hồi. Nhưng nếu listener gọi API ngoài thành công rồi process dừng trước khi registry ghi nhận hoàn tất, resubmit có thể gọi API lần nữa.

Vì vậy, trước khi bật retry:
- Xác định tác dụng phụ nào đã có thể xảy ra trước khi lỗi.
- Ghi event ID hoặc operation ID ổn định.
- Dùng inbox/unique constraint cho cập nhật database.
- Dùng idempotency key ở API ngoài nếu dịch vụ hỗ trợ.
- Không đánh dấu publication hoàn tất trước khi tác dụng phụ được bảo vệ và commit theo contract.

## 6. Exponential backoff

Retry liên tục ngay khi thất bại có thể làm dependency đang lỗi chịu thêm tải. Exponential backoff tăng thời gian chờ sau mỗi lần thử.

Một công thức cơ bản:

[
delay_n = min(delay_{max}, delay_{initial} 	imes 2^{n-1})
]

Ví dụ với thời gian đầu 500 ms và giới hạn 20 giây:

| Lần thử tiếp theo | Delay trước giới hạn |
|---:|---:|
| 1 | 0,5 giây |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| 5 | 8 giây |
| 6 | 16 giây |
| 7 | 32 giây, bị giới hạn còn 20 giây |

Các con số chỉ minh họa. Delay cần phù hợp với timeout downstream, latency bình thường và thời hạn nghiệp vụ. Backoff không giới hạn số lần thử vẫn có thể giữ event vô thời hạn; luôn kết hợp với retry budget hoặc chính sách chuyển trạng thái.

## 7. Jitter để tránh retry đồng loạt

Nếu hàng nghìn event cùng thất bại tại một thời điểm và đều retry sau 10 giây, chúng có thể tạo một đợt tải mới đúng lúc dependency vừa phục hồi. Hiện tượng này gọi là retry synchronization hoặc thundering herd.

Jitter thêm ngẫu nhiên vào thời gian chờ để phân tán lần thử.

Một lựa chọn phổ biến là full jitter:

[
delay_n = random(0,min(delay_{max},delay_{initial}	imes 2^{n-1}))
]

Ví dụ, nếu exponential backoff cho giới hạn 8 giây, mỗi event chọn ngẫu nhiên một delay từ 0 đến 8 giây. Một lựa chọn khác là equal jitter, giữ một phần delay cố định và ngẫu nhiên phần còn lại.

Dùng jitter đặc biệt hữu ích khi nhiều listener hoặc consumer cùng phụ thuộc vào một database, API hoặc broker. Nếu downstream cung cấp `Retry-After`, cần kết hợp tín hiệu đó với policy và giới hạn tổng thời gian chờ.

## 8. Retry budget và số lần thử tối đa

Retry budget giới hạn tổng chi phí phục hồi mà hệ thống chấp nhận cho một operation. Budget có thể được định nghĩa theo:

- Số lần thử tối đa.
- Tổng thời gian tối đa từ lúc event được nhận đến lúc hoàn tất.
- Deadline nghiệp vụ.
- Tổng thời gian chờ backoff.
- Số lần retry trong một cửa sổ thời gian của consumer/dependency.

Ví dụ, một notification có thể được retry tối đa 5 lần trong 10 phút. Một tác vụ đồng bộ tồn kho có thể có deadline ngắn hơn vì kết quả ảnh hưởng đến khả năng đặt hàng. Một báo cáo analytics có thể chấp nhận retry lâu hơn.

Không dùng một số lần retry chung cho mọi event. Chọn budget theo mức quan trọng, thời hạn nghiệp vụ và khả năng phục hồi của dependency.

Khi budget hết:
- Chuyển message sang DLQ/quarantine hoặc trạng thái cần can thiệp.
- Ghi nguyên nhân cuối cùng và số lần thử.
- Phát cảnh báo theo mức độ nghiệp vụ.
- Giữ khả năng replay sau khi khắc phục.
- Không âm thầm drop event quan trọng.

## 9. Retry và timeout phải được thiết kế cùng nhau

Timeout giới hạn thời gian một lần thử; retry budget giới hạn toàn bộ quá trình. Nếu một lần gọi có timeout 30 giây và cho phép 10 lần thử, một operation có thể kéo dài nhiều phút trước khi kết thúc.

Cần xác định:
- Timeout connect và response của HTTP client.
- Timeout truy vấn database hoặc lock acquisition.
- Timeout xử lý listener.
- Delay giữa các lần thử.
- Deadline tổng của business operation.
- Thời gian còn lại có đủ cho lần thử tiếp theo không.

Trước khi bắt đầu retry, kiểm tra deadline còn đủ cho một lần thử có ý nghĩa. Không khởi động request mới khi operation đã hết thời hạn nghiệp vụ.

Công thức ước lượng tổng thời gian:

[
T_total = sum(attempt_time_i) + sum(delay_i)
]

Trong đó `attempt_time_i` bị giới hạn bởi timeout của lần thử tương ứng. Dùng công thức để kiểm tra budget có phù hợp với SLO và thời gian người dùng chấp nhận hay không.

## 10. Không retry lỗi nghiệp vụ vĩnh viễn

Một event có thể được xử lý thành công về mặt kỹ thuật nhưng kết quả nghiệp vụ là từ chối. Ví dụ Inventory nhận yêu cầu giữ hàng nhưng không còn đủ số lượng. Đây không phải lỗi hạ tầng để retry liên tục.

Hãy phân biệt:
- **Technical failure:** listener không thể hoàn thành do dependency hoặc runtime.
- **Business outcome:** nghiệp vụ đã đánh giá và trả kết quả như ReservationRejected.
- **Invalid message:** event không thể được diễn giải theo contract.
- **Configuration failure:** hệ thống không có quyền hoặc cấu hình để thực hiện.

Business outcome nên được biểu đạt bằng trạng thái hoặc event kết quả phù hợp, không ném exception chỉ để kích hoạt retry. Nếu điều kiện nghiệp vụ có thể thay đổi sau này, đó là một workflow mới hoặc một yêu cầu retry có chủ đích với deadline rõ, không phải redelivery vô hạn của event cũ.

## 11. Idempotency là điều kiện của retry an toàn

At-least-once delivery và resubmit có nghĩa một listener có thể nhận cùng event nhiều lần. Retry chỉ an toàn khi lần xử lý lặp không tạo thêm tác dụng phụ nghiệp vụ.

Các cơ chế thường dùng:

**Inbox pattern:** lưu `consumerName + eventId` với unique constraint. Ghi inbox và cập nhật domain trong cùng transaction.

**Idempotency key:** với một business operation có thể được phát thành nhiều message ID, dùng operation key ổn định như `capture-payment:order-123`.

**State transition có điều kiện:** chỉ cập nhật khi trạng thái hiện tại cho phép; lần lặp sau đó trở thành no-op hợp lệ.

**Version/sequence:** bỏ qua snapshot cũ hoặc phát hiện khoảng trống sequence theo semantics event.

**External API idempotency:** gửi cùng key trong mọi lần gọi lại nếu dịch vụ đích hỗ trợ.

Không chỉ deduplicate trong bộ nhớ hoặc bằng `exists()` rồi `save()` tách rời. Hai consumer đồng thời có thể cùng vượt qua bước kiểm tra. Dùng unique constraint và thao tác claim nguyên tử để bảo vệ concurrency.

## 12. Retry khi gọi dịch vụ bên ngoài

Khi listener gọi payment gateway, email provider hoặc API khác, timeout không cho biết chắc dịch vụ đích đã thực hiện tác dụng phụ hay chưa.

Ví dụ:
1. Consumer gửi yêu cầu capture payment.
2. Payment gateway thực hiện thành công.
3. Response bị mất trên network.
4. Consumer nhận timeout và retry.
5. Nếu gateway không hỗ trợ idempotency, khách hàng có thể bị thu tiền hai lần.

Giải pháp:
- Dùng idempotency key ổn định theo business operation.
- Nếu timeout, tra cứu trạng thái operation trước khi gửi lại khi API hỗ trợ.
- Ghi operation state và attempt history.
- Tách side effect ra outbox command nếu cần phục hồi sau restart.
- Có reconciliation khi kết quả ở hệ thống đích không xác định.
- Không tạo key mới ở mỗi lần retry.

Với email, có thể lưu notification operation ID và kiểm tra provider message ID nếu dịch vụ hỗ trợ. Với payment, refund hoặc shipment, cần mức bảo vệ và audit chặt hơn vì tác động nghiệp vụ lớn.

## 13. Outbox, Inbox và retry

Transactional outbox bảo vệ phía producer: thay đổi domain và ý định gửi message được ghi trong cùng transaction. Relay đọc outbox và gửi message; nếu không chắc broker đã nhận hay chưa, relay có thể gửi lại.

Inbox bảo vệ phía consumer: event ID được claim cùng transaction với cập nhật domain. Nếu message được giao lại sau khi consumer đã commit, consumer nhận ra duplicate và không lặp tác dụng phụ.

~~~mermaid
flowchart TD
    A[Producer transaction] --> B[Update domain]
    B --> C[Write outbox]
    C --> D[Commit]
    D --> E[Relay publish]
    E --> F[Broker]
    F --> G[Consumer receives]
    G --> H[Atomic inbox claim]
    H --> I{First delivery?}
    I -- No --> J[Ack duplicate]
    I -- Yes --> K[Apply domain change]
    K --> L[Commit inbox and domain]
    L --> M[Ack message]
    E --> N[Retry relay on transient failure]
    N --> E
~~~

Outbox không làm broker chỉ giao một lần. Inbox không đảm bảo producer publish thành công. Hai mẫu giải quyết hai boundary khác nhau và cần được kết hợp với retry policy phù hợp.

## 14. Retry, dead-letter queue và quarantine

Khi retry budget hết hoặc message không thể xử lý tự động, cần một nơi giữ message để điều tra và phục hồi. DLQ/quarantine giúp tránh một message lỗi làm kẹt luồng chính.

Thông tin nên lưu:
- Event/message ID.
- Event type và schema version.
- Consumer hoặc listener.
- Số lần thử và thời điểm thử gần nhất.
- Exception class và mã lỗi đã chuẩn hóa.
- Correlation ID/causation ID.
- Thời điểm chuyển vào DLQ.
- Lý do cách ly và trạng thái xử lý thủ công.

Quy trình DLQ:
1. Cảnh báo khi message mới vào DLQ hoặc số lượng vượt ngưỡng.
2. Phân loại lỗi dữ liệu, schema, cấu hình hay dependency.
3. Khắc phục nguyên nhân.
4. Xác nhận listener/consumer đã sẵn sàng.
5. Replay một nhóm nhỏ.
6. Theo dõi duplicate, latency và backlog.
7. Ghi audit kết quả.

Không replay hàng loạt khi dependency còn quá tải. Không xóa DLQ để làm dashboard sạch nếu message còn giá trị nghiệp vụ. Với Spring Modulith, publication chưa hoàn tất trong registry nội bộ và message ở broker DLQ là hai loại công việc khác nhau; cần runbook riêng.

## 15. Circuit breaker và bulkhead

Retry có thể làm tăng áp lực lên dependency đang lỗi. Circuit breaker ngăn gọi liên tục khi tỷ lệ lỗi vượt ngưỡng; bulkhead giới hạn tài nguyên dành cho một dependency hoặc nhóm listener.

Kết hợp thường gặp:
- Timeout giới hạn một lần gọi.
- Circuit breaker mở khi dependency lỗi liên tục.
- Backoff/jitter trì hoãn lần thử tiếp theo.
- Retry budget giới hạn tổng số lần thử.
- Bulkhead giới hạn concurrency để một downstream không chiếm hết thread/connection.
- DLQ/quarantine giữ công việc không thể phục hồi tự động.

Thứ tự các decorator cần được chọn theo semantics của thư viện và mục tiêu. Ví dụ retry bên trong circuit breaker có thể khiến breaker nhìn thấy từng attempt; circuit breaker bên ngoài có thể nhìn thấy kết quả sau toàn bộ retry. Không có thứ tự đúng cho mọi trường hợp; hãy kiểm tra cách thư viện tính failure và metrics.

Không dùng circuit breaker để bỏ message. Khi circuit mở, consumer cần giữ message hoặc chuyển sang trạng thái retry có backoff theo cơ chế transport.

## 16. Retry và ordering

Retry có thể làm event cũ hoàn tất sau event mới. Nếu listener xử lý theo aggregate, việc này có thể khiến state bị lùi hoặc bỏ qua chuyển trạng thái.

Ví dụ:
- OrderConfirmed được giao trước.
- Listener gặp lỗi và retry sau 10 giây.
- OrderShipped được xử lý thành công trước đó.
- OrderConfirmed retry đến muộn và có nguy cơ ghi đè trạng thái mới.

Cần:
- Gắn aggregate version hoặc sequence.
- Xác định ordering guarantee theo aggregate/partition.
- Dùng state transition có điều kiện.
- Cách ly event thiếu sequence hoặc sai thứ tự nếu cần.
- Tránh retry một partition theo cách làm chặn mọi message không liên quan.
- Thiết kế consumer idempotent và có khả năng nhận biết event cũ.

Nếu thứ tự là bắt buộc, retry policy phải cân nhắc head-of-line blocking. Nếu có thể xử lý song song giữa các aggregate, partition theo aggregate ID giúp giữ thứ tự cục bộ mà vẫn mở rộng throughput.

## 17. Retry cho lỗi tạm thời và poison message

Poison message là message luôn thất bại do nội dung hoặc điều kiện không thể tự phục hồi. Ví dụ payload thiếu field bắt buộc, schema không hỗ trợ hoặc dữ liệu gây lỗi parse. Retry liên tục không làm message hợp lệ hơn.

Cách xử lý:
- Giới hạn số lần thử nhanh ban đầu.
- Chuyển message sang quarantine sau khi nhận diện lỗi không retryable.
- Ghi payload hash và metadata đủ để điều tra.
- Sửa producer hoặc viết migration/upcaster nếu cần.
- Chỉ replay sau khi xác nhận bản sửa tương thích.
- Giữ event ID hoặc operation ID gốc để idempotency vẫn hoạt động.

Với lỗi tạm thời, retry có backoff và có thể quay lại luồng chính. Với poison message, cách ly sớm để tránh chặn consumer và làm tăng chi phí vận hành.

## 18. Retry và graceful degradation

Không phải mọi event đều cần chờ xử lý xong mới phục vụ người dùng. Có thể cho phép một số chức năng hoạt động với dữ liệu tạm thời cũ, đồng thời giữ công việc để retry.

Ví dụ:
- Search index cập nhật chậm: kết quả tìm kiếm có thể trễ trong giới hạn đã công bố.
- Analytics cập nhật chậm: dashboard hiển thị thời điểm refresh gần nhất.
- Notification chậm: đơn hàng vẫn được xác nhận nếu notification không phải điều kiện nghiệp vụ bắt buộc.
- Inventory reservation chậm: nếu reservation là điều kiện xác nhận đơn, workflow cần trạng thái pending và không tuyên bố hoàn tất quá sớm.

Retry policy phải phù hợp với mức độ quan trọng của consumer. Một consumer phục vụ audit hoặc tài chính có thể cần lưu giữ và cảnh báo nghiêm ngặt; consumer analytics có thể chấp nhận backlog lâu hơn.

## 19. Quan sát và vận hành retry

Không thể vận hành retry chỉ bằng cách đếm exception. Cần metric cho thấy retry đang giúp phục hồi hay đang làm hệ thống tệ hơn.

Metric hữu ích:
- Attempt count theo listener/event type.
- Retry rate và retry success rate.
- Delay giữa các lần thử.
- Retry budget exhausted count.
- Oldest retry age.
- Incomplete publication count và oldest age.
- DLQ/quarantine count.
- Downstream error rate và latency.
- Circuit breaker state.
- Consumer lag/backlog.
- Duplicate/idempotency hit rate.

Log nên có event ID, listener, attempt number, error category, next retry time, correlation ID và deadline còn lại. Tránh log toàn bộ payload hoặc secret.

Cảnh báo theo tác động nghiệp vụ: publication quan trọng vượt deadline, DLQ tăng, retry success giảm hoặc oldest event age vượt SLO. Không cảnh báo chỉ vì có một lần retry bình thường.

## 20. Ví dụ chọn policy cho các consumer

| Consumer | Loại lỗi có thể retry | Policy minh họa | Khi hết budget |
|---|---|---|---|
| InventoryListener | Deadlock, DB connection tạm thời | 3–5 lần, exponential backoff + jitter, deadline ngắn | Cảnh báo và giữ publication để phục hồi |
| NotificationListener | Provider 429/503, timeout | Tôn trọng Retry-After, backoff, budget dài hơn | DLQ/quarantine và tra cứu provider |
| AnalyticsProjection | DB tạm lỗi | Retry có giới hạn, batch/replay | Giữ backlog, rebuild/replay có kiểm soát |
| PaymentCapture | Timeout kết quả không rõ | Tra cứu operation, cùng idempotency key | Manual reconciliation |
| SchemaConsumer | Version không hỗ trợ | Không retry liên tục | Quarantine, nâng consumer/upcaster |

Các con số cần được xác định bằng workload và SLO thực tế. Bảng chỉ minh họa cách chọn theo tính chất nghiệp vụ, không phải cấu hình mặc định cho Spring Modulith.

## 21. Quy trình ra quyết định retry

Với mỗi event listener hoặc consumer, trả lời lần lượt:

1. Lỗi này có khả năng tự hết không?
2. Có thể xác định lỗi retryable từ exception/response nào?
3. Tác dụng phụ đã có thể xảy ra trước khi lỗi chưa?
4. Consumer có idempotent không?
5. Retry được thực hiện ở boundary nào?
6. Timeout mỗi attempt và deadline tổng là bao nhiêu?
7. Dùng backoff và jitter nào?
8. Retry budget tối đa theo số lần hoặc thời gian là gì?
9. Khi hết budget, message được giữ ở đâu?
10. Ai nhận cảnh báo và ai có quyền replay?
11. Event có yêu cầu ordering theo aggregate không?
12. Có metric để biết retry đang phục hồi hay gây retry storm không?

Nếu chưa trả lời được câu hỏi về idempotency và tác dụng phụ, chưa nên bật retry tự động cho side effect quan trọng.

## 22. Checklist chọn chiến lược retry

- [ ] Đã phân loại lỗi retryable, permanent và business outcome.
- [ ] Có một retry owner rõ cho mỗi boundary.
- [ ] Không có nhiều lớp retry nhân số lần thử ngoài kiểm soát.
- [ ] Mỗi attempt có timeout hữu hạn.
- [ ] Có exponential backoff và jitter khi phù hợp.
- [ ] Có retry budget/deadline tổng.
- [ ] Tôn trọng Retry-After hoặc tín hiệu throttling của downstream.
- [ ] Listener idempotent trước redelivery/resubmit.
- [ ] Database inbox và domain update dùng transaction nguyên tử.
- [ ] External side effect có idempotency key hoặc reconciliation.
- [ ] Event Publication Registry được cấu hình persistent khi cần phục hồi.
- [ ] Publication registry và broker DLQ được vận hành như hai boundary riêng.
- [ ] Có DLQ/quarantine và quy trình replay.
- [ ] Ordering/version được bảo vệ khi retry làm event đến muộn.
- [ ] Circuit breaker/bulkhead được dùng khi cần giới hạn áp lực.
- [ ] Có metric retry success, oldest age, budget exhausted và DLQ.
- [ ] Có runbook, owner và quyền audit cho resubmit/replay.

## 23. Nguyên tắc chọn retry

Retry là một phần của thiết kế độ tin cậy, không phải một vòng lặp bắt exception. Hãy phân loại lỗi, chọn boundary hiểu rõ nguyên nhân, đặt timeout, exponential backoff, jitter và retry budget; khi hết budget, chuyển sang DLQ/quarantine hoặc xử lý nghiệp vụ có kiểm soát.

Trong Spring Modulith, Event Publication Registry giúp theo dõi và phục hồi publication chưa hoàn tất đến listener, nhưng không thay thế idempotency, outbox/inbox hoặc retry policy của broker. Chọn chiến lược theo tác dụng phụ, ordering, deadline và mức quan trọng của từng consumer. Khi retry có giới hạn, quan sát được và có đường phục hồi rõ ràng, hệ thống có thể chịu lỗi tạm thời mà không tạo tải dây chuyền hoặc xử lý nghiệp vụ lặp ngoài ý muốn.
