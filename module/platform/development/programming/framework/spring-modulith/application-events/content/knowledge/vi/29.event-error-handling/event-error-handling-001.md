# Phân loại lỗi handler

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi listener nhận event, quá trình xử lý có thể thất bại vì nhiều nguyên nhân: dependency tạm thời không sẵn sàng, payload không hợp lệ, nghiệp vụ từ chối yêu cầu, xung đột đồng thời hoặc lỗi lập trình. Mỗi loại lỗi cần cách phản ứng khác nhau.

**Phân loại lỗi handler** là bước xác định bản chất, khả năng phục hồi và hành động tiếp theo khi một event listener ném exception hoặc không thể hoàn thành nghiệp vụ. Phân loại đúng giúp retry có giới hạn, tránh lặp side effect, không che giấu lỗi dữ liệu và cung cấp thông tin rõ ràng cho vận hành.

## 1. Vì sao phải phân loại lỗi?

Giả sử module Inventory nhận OrderConfirmed để giữ hàng. Nếu database tạm thời mất kết nối, thử lại sau một khoảng chờ có thể thành công. Nếu event thiếu orderId, retry cùng payload sẽ tiếp tục thất bại. Nếu hàng không đủ, đó có thể là kết quả nghiệp vụ cần phát InventoryUnavailable thay vì xem là lỗi hạ tầng. Nếu handler đã giữ hàng nhưng process dừng trước khi publication được xác nhận hoàn tất, event có thể được giao lại và handler phải nhận diện thao tác đã thực hiện.

Một chính sách chung kiểu bắt mọi exception rồi retry sẽ tạo ra nhiều vấn đề:

- Lỗi vĩnh viễn bị thử lại vô hạn, chiếm tài nguyên và làm backlog tăng.
- Lỗi nghiệp vụ bình thường bị ghi nhận như lỗi kỹ thuật, gây cảnh báo sai.
- Lỗi lập trình bị che khuất bởi retry, làm chậm việc tìm nguyên nhân.
- Side effect có thể bị thực hiện nhiều lần nếu kết quả lần trước không rõ.
- Người vận hành không biết lỗi nào có thể tự phục hồi và lỗi nào cần can thiệp.

Mỗi handler nên xác định rõ lỗi nào có thể retry, lỗi nào cần kết thúc xử lý, lỗi nào phải chuyển sang quy trình nghiệp vụ khác và lỗi nào cần điều tra.

## 2. Các nhóm lỗi thường gặp

Không có một taxonomy duy nhất phù hợp với mọi hệ thống. Bảng dưới đây là mô hình thực hành để phân loại lỗi khi xử lý application events:

| Nhóm lỗi | Ví dụ | Hướng xử lý thường dùng |
| --- | --- | --- |
| Hạ tầng tạm thời | Timeout database, connection reset, broker hoặc service tạm mất kết nối. | Retry có backoff và giới hạn; kiểm tra dependency. |
| Giới hạn tải | HTTP 429, rate limit, pool cạn, service quá tải. | Tôn trọng Retry-After nếu có, giảm tốc độ và retry có kiểm soát. |
| Lỗi hợp đồng/dữ liệu | Payload thiếu field bắt buộc, schema không hỗ trợ, deserialize thất bại. | Dừng retry tự động; quarantine hoặc dead-letter để điều tra. |
| Từ chối nghiệp vụ | Hàng không đủ, đơn đã hủy, thanh toán bị từ chối. | Biểu diễn kết quả nghiệp vụ bằng state/event phù hợp. |
| Xung đột đồng thời | Optimistic lock conflict, deadlock, unique constraint do race. | Đánh giá có thể retry transaction hay cần xử lý xung đột. |
| Lỗi lập trình | NullPointerException, invariant bị vi phạm, lỗi mapping. | Ghi nhận lỗi, sửa code; tránh retry mù quáng. |
| Kết quả không xác định | Request timeout sau khi hệ thống ngoài có thể đã thực hiện side effect. | Đối soát trạng thái và dùng idempotency key trước khi gửi lại. |
| Lỗi cấu hình/quyền | Credentials hết hạn, thiếu quyền truy cập, endpoint sai. | Dừng vòng retry nhanh; cảnh báo và sửa cấu hình/quyền. |

Tên nhóm không quyết định hành vi một cách máy móc. Ví dụ lỗi kết nối có thể tạm thời, nhưng DNS sai hoặc firewall chặn kéo dài có thể không tự hết. HTTP 5xx thường có thể retry, nhưng một số response 5xx vẫn có thể xảy ra sau khi hệ thống đích đã commit side effect. Luôn xét ngữ cảnh và hợp đồng của dependency.

## 3. Phân biệt lỗi kỹ thuật và kết quả nghiệp vụ

Một listener không phải lúc nào cũng cần ném exception khi không thể thực hiện một hành động. Nếu kết quả là một nhánh hợp lệ của nghiệp vụ, hãy mô hình hóa nó thành kết quả hoặc event riêng.

Ví dụ, Inventory nhận ReserveInventoryRequested:

- Database tạm mất kết nối: lỗi kỹ thuật, có thể retry.
- Reservation ID không tồn tại: có thể là lỗi dữ liệu hoặc yêu cầu không hợp lệ.
- Hàng không đủ: kết quả nghiệp vụ, có thể phát InventoryUnavailable.
- Đơn hàng đã bị hủy: kiểm tra trạng thái và trả kết quả phù hợp theo quy tắc domain.

Không nên ném RuntimeException cho mọi trường hợp hàng không đủ rồi để error handler retry liên tục. Điều đó không làm hàng xuất hiện thêm và cũng không giúp process manager hiểu cần chuyển saga sang nhánh nào.

Một kiểu kết quả tường minh có thể giúp tách outcome nghiệp vụ khỏi exception kỹ thuật:

~~~java
public sealed interface ReservationResult {
    record Reserved(UUID reservationId) implements ReservationResult {}
    record Unavailable(String reason) implements ReservationResult {}
    record OrderAlreadyCancelled() implements ReservationResult {}
}
~~~

Listener xử lý kết quả:

~~~java
@Component
@RequiredArgsConstructor
class ReserveInventoryListener {

    private final InventoryService inventory;
    private final ApplicationEventPublisher events;

    @ApplicationModuleListener
    void on(ReserveInventoryRequested request) {
        ReservationResult result = inventory.reserve(request);

        if (result instanceof ReservationResult.Reserved reserved) {
            events.publishEvent(new InventoryReserved(
                request.sagaId(),
                request.orderId(),
                reserved.reservationId()
            ));
        } else if (result instanceof ReservationResult.Unavailable unavailable) {
            events.publishEvent(new InventoryUnavailable(
                request.sagaId(),
                request.orderId(),
                unavailable.reason()
            ));
        } else if (result instanceof ReservationResult.OrderAlreadyCancelled) {
            events.publishEvent(new InventoryReservationRejected(
                request.sagaId(),
                request.orderId(),
                "ORDER_CANCELLED"
            ));
        }
    }
}
~~~

Các record và service trong ví dụ là mô hình minh họa. Điều quan trọng là kết quả nghiệp vụ được biểu đạt bằng kiểu dữ liệu hoặc event có ý nghĩa, còn exception dành cho tình huống xử lý không thể hoàn tất theo hợp đồng kỹ thuật.

## 4. Phân loại theo khả năng phục hồi

Một câu hỏi thực tế hơn tên exception là: nếu gửi lại cùng event, khả năng thành công có tăng lên không và có gây side effect lặp không?

| Khả năng | Dấu hiệu | Chính sách |
| --- | --- | --- |
| Retryable | Nguyên nhân có thể tự hết sau thời gian ngắn và thao tác có thể lặp an toàn. | Retry có backoff, jitter và giới hạn. |
| Non-retryable | Payload hoặc điều kiện cố định khiến lần thử sau vẫn thất bại. | Dừng retry; lưu thông tin lỗi và chuyển xử lý thủ công/DLT. |
| Business outcome | Hệ thống xử lý đúng nhưng kết quả nghiệp vụ là từ chối hoặc không đủ điều kiện. | Phát event kết quả hoặc chuyển state nghiệp vụ. |
| Reconciliation required | Không biết side effect ở hệ thống đích đã xảy ra chưa. | Tra cứu trạng thái trước khi retry hoặc bù trừ. |

Retryable không có nghĩa là retry vô hạn. Một lỗi tạm thời vẫn có thể kéo dài; cần giới hạn số lần thử, tổng thời gian và mức tải. Non-retryable cũng không có nghĩa là xóa event. Event có thể được giữ trong dead-letter/quarantine để sửa dữ liệu hoặc replay có kiểm soát.

## 5. Xây dựng exception taxonomy rõ ràng

Tạo các exception theo ý nghĩa xử lý giúp handler và error policy dễ đọc hơn. Ví dụ:

~~~java
public class RetryableEventException extends RuntimeException {
    public RetryableEventException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class NonRetryableEventException extends RuntimeException {
    public NonRetryableEventException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class EventContractException extends NonRetryableEventException {
    public EventContractException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đoạn code minh họa một hierarchy đơn giản; trong Java, constructor của lớp cha cần được thiết kế phù hợp với cách kế thừa và API exception của dự án. Có thể dùng các lớp riêng cho lỗi kết nối, schema không hỗ trợ, lỗi nghiệp vụ hoặc kết quả không xác định.

Không nên phân loại chỉ bằng cách so khớp chuỗi message. Message có thể thay đổi theo phiên bản thư viện hoặc ngôn ngữ. Ưu tiên exception type, mã lỗi có cấu trúc và thông tin từ dependency. Nếu phải kiểm tra cause chain, hãy giới hạn phạm vi và giữ nguyên exception gốc làm cause khi wrap.

Ví dụ chuyển lỗi dependency:

~~~java
try {
    paymentGateway.capture(command);
} catch (SocketTimeoutException ex) {
    throw new RetryableEventException(
        "Payment gateway timed out",
        ex
    );
} catch (InvalidPaymentRequestException ex) {
    throw new EventContractException(
        "Payment request is invalid",
        ex
    );
}
~~~

Trong thực tế, SDK có thể ném exception tổng quát hơn hoặc wrap lỗi socket trong nhiều lớp. Hãy dùng loại exception và mã trạng thái mà client chính thức cung cấp, đồng thời phân biệt timeout trước khi gửi request với timeout sau khi request có thể đã được xử lý.

## 6. Lỗi trong listener đồng bộ và bất đồng bộ

Hành vi quan sát được phụ thuộc cách listener được gọi:

| Cách listener | Đặc điểm lỗi |
| --- | --- |
| @EventListener đồng bộ | Listener thường chạy trong luồng dispatch của publisher; exception có thể truyền ngược về nơi publish tùy multicaster và cấu hình. |
| @TransactionalEventListener | Listener được ràng buộc với transaction phase; exception xảy ra khi listener được gọi ở phase tương ứng. |
| @Async listener | Listener chạy bất đồng bộ; exception không thể truyền ngược như lời gọi đồng bộ thông thường. Cần cấu hình và quan sát lỗi async phù hợp. |
| @ApplicationModuleListener | Listener module của Spring Modulith được xử lý bất đồng bộ và sau commit theo cấu hình của annotation; publication registry có thể theo dõi completion và publication chưa hoàn tất. |

Không giả định publisher nhận được mọi exception từ listener bất đồng bộ. publishEvent có thể trả về trước khi listener hoàn tất. Nếu cần theo dõi giao event nội bộ đáng tin cậy, dùng transactional listener phù hợp và cấu hình Event Publication Registry với persistent repository theo yêu cầu durability.

Với listener đồng bộ, việc exception truyền về publisher có thể làm luồng gọi thất bại; điều đó không tự động có nghĩa event đã được lưu bền vững để retry sau restart. Với listener bất đồng bộ, cần dựa vào error handling và cơ chế theo dõi riêng, không chỉ dựa vào log của publisher.

## 7. Phân loại lỗi trong Spring Modulith

Spring Modulith Event Publication Registry theo dõi publication đến transactional listener. Khi listener xử lý thành công, publication được đánh dấu completed. Nếu listener thất bại và completion không được ghi nhận, publication có thể còn incomplete để ứng dụng tìm và recovery/resubmit theo API, cấu hình và phiên bản đang sử dụng.

Registry giúp nhận biết lần giao nào chưa được xác nhận hoàn tất. Nó không tự quyết định mọi exception là retryable hay non-retryable, không phân biệt kết quả nghiệp vụ thay cho domain và không cung cấp một chính sách retry vô hạn an toàn.

Một quy trình phân loại có thể là:

~~~mermaid
flowchart TD
    A[Listener nhận event] --> B[Thực hiện xử lý]
    B --> C{Có exception?}
    C -->|Không| D[Commit xử lý và xác nhận publication]
    C -->|Có| E[Phân loại nguyên nhân]
    E --> F{Kết quả nghiệp vụ hợp lệ?}
    F -->|Có| G[Phát event kết quả hoặc cập nhật state]
    F -->|Không| H{Có thể retry an toàn?}
    H -->|Có| I[Retry có giới hạn và backoff]
    H -->|Không| J[Quarantine/DLT hoặc cần can thiệp]
    I --> K{Đã đạt giới hạn?}
    K -->|Chưa| B
    K -->|Rồi| J
~~~

Nếu dùng persistent publication repository, hãy kiểm thử việc ghi publication và completion trên cùng transaction boundary thích hợp. Nếu dùng store chỉ trong bộ nhớ, trạng thái incomplete có thể mất khi process dừng; khả năng recovery sau restart sẽ bị giới hạn.

## 8. Retry có kiểm soát

Retry phù hợp với lỗi tạm thời, nhưng cần có chính sách rõ ràng:

- Giới hạn số lần thử hoặc tổng thời gian retry.
- Dùng exponential backoff và jitter khi phù hợp.
- Tôn trọng Retry-After hoặc rate limit từ dependency.
- Không retry lỗi hợp đồng hoặc lỗi nghiệp vụ cố định.
- Tránh retry đồng thời quá nhiều event khi dependency đang quá tải.
- Ghi nhận attempt, nguyên nhân và thời điểm thử lại.

Ví dụ, với lỗi database tạm thời, có thể thử lại sau 1 giây, 2 giây, 4 giây rồi dừng hoặc chuyển sang xử lý thủ công. Đây chỉ là ví dụ; backoff phải được điều chỉnh theo latency và SLA của hệ thống.

Retry tại listener và retry publication là hai cấp khác nhau. Một error handler có thể thử lại cùng invocation trước khi ném lỗi ra ngoài; publication registry có thể giúp recovery một publication chưa hoàn tất sau đó. Cần tránh cấu hình hai lớp retry nhân lên ngoài dự kiến. Ví dụ 3 lần retry ở listener kết hợp 5 lần resubmit có thể tạo ra nhiều lần thực thi hơn con số người vận hành nghĩ.

## 9. Dead-letter và quarantine cho lỗi không thể retry

Khi event không thể xử lý tự động, hệ thống cần giữ thông tin để điều tra. Với broker, có thể chuyển record sang dead-letter topic/queue. Với application events nội bộ, có thể dùng bảng quarantine hoặc một quy trình lưu lỗi riêng tùy kiến trúc.

Thông tin nên lưu:

| Trường | Mục đích |
| --- | --- |
| eventId | Nhận diện event gốc và hỗ trợ replay idempotent. |
| eventType/schemaVersion | Xác định hợp đồng payload. |
| listener/module | Xác định nơi xử lý thất bại. |
| failureCategory/errorCode | Phân loại lỗi mà không phụ thuộc message text. |
| firstFailedAt/lastFailedAt | Theo dõi thời gian tồn tại của lỗi. |
| attemptCount | Biết số lần đã thử. |
| correlationId | Nối event với quy trình nghiệp vụ. |
| payload reference | Tham chiếu đến payload được lưu an toàn nếu cần điều tra. |

Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào DLT/quarantine nếu không có kiểm soát truy cập và retention phù hợp. Nếu payload chứa dữ liệu cá nhân, cần xác định thời hạn lưu và quy trình xóa.

Replay chỉ nên thực hiện sau khi đã sửa nguyên nhân hoặc có quyết định nghiệp vụ. Giữ eventId gốc để chống tác động trùng; ghi lại ai replay, vì sao, lúc nào và kết quả ra sao.

## 10. Idempotency khi handler có thể chạy lại

Một publication chưa hoàn tất có thể được giao lại. Cũng có thể listener thực hiện side effect thành công rồi process dừng trước khi registry ghi completion. Do đó, retry an toàn cần đi cùng idempotency.

Các cách thường dùng:

- Dùng eventId ổn định để nhận diện một event.
- Lưu eventId đã xử lý trong cùng transaction với thay đổi nghiệp vụ.
- Dùng unique constraint hoặc inbox table để chống insert trùng.
- Với API bên ngoài, dùng idempotency key ổn định cho cùng một hành động.
- Trước khi tạo side effect, kiểm tra trạng thái nghiệp vụ hiện tại.

Không nên tạo eventId mới mỗi lần retry cùng một event. Nếu eventId thay đổi, hệ thống nhận có thể coi lần retry là một nghiệp vụ mới và thực hiện tác động lần nữa.

## 11. Xử lý lỗi không xác định từ hệ thống ngoài

Timeout hoặc mất kết nối có thể xảy ra sau khi hệ thống đích đã thực hiện side effect. Đây là nhóm lỗi đặc biệt cần phân loại riêng, ví dụ payment request timeout nhưng chưa biết giao dịch đã được capture hay chưa.

Không nên lập tức đánh dấu thất bại rồi gửi lại lệnh với idempotency key mới. Thay vào đó:

1. Lưu trạng thái step là UNKNOWN hoặc RECONCILIATION_REQUIRED.
2. Tra cứu giao dịch bằng business key hoặc idempotency key đã dùng.
3. Nếu đã thành công, ghi nhận kết quả thành công.
4. Nếu chưa thực hiện, retry cùng khóa theo hợp đồng provider.
5. Nếu vẫn không rõ, giữ trạng thái cần can thiệp và cảnh báo.

Phân biệt lỗi request chưa gửi được với lỗi response bị mất sau khi request đã đến hệ thống đích. Hai trường hợp có mức độ an toàn khi retry khác nhau.

## 12. Không nuốt exception và không đánh dấu hoàn tất sai

Một lỗi nguy hiểm là bắt exception rồi chỉ ghi log:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        inventory.reserveFor(event.orderId());
    } catch (Exception ex) {
        log.error("Could not reserve inventory", ex);
    }
}
~~~

Trong ví dụ này, listener kết thúc bình thường sau khi bắt exception. Framework có thể xem invocation đã hoàn tất, trong khi nghiệp vụ giữ hàng chưa thành công. Publication có thể được đánh dấu completed và cơ chế recovery không còn biết cần giao lại event.

Nếu lỗi phải được retry hoặc cần giữ publication incomplete, hãy để exception phù hợp truyền ra ngoài listener sau khi ghi log cần thiết, hoặc chuyển lỗi sang một quy trình nghiệp vụ/quarantine rõ ràng. Chỉ kết thúc bình thường khi handler đã xử lý thành công hoặc đã ghi nhận một kết quả nghiệp vụ hợp lệ.

Không nên bắt Throwable để che cả lỗi nghiêm trọng của JVM. Nếu cần bổ sung ngữ cảnh, wrap exception nhưng giữ cause gốc. Tránh log cùng một exception ở nhiều lớp với stack trace lặp; chọn nơi có đủ thông tin để ghi một lần rõ ràng.

## 13. Kiểm thử phân loại lỗi

Unit test nên xác minh từng exception hoặc outcome được phân loại đúng. Integration test cần kiểm tra listener, transaction và publication registry trên cấu hình tương tự môi trường chạy thật.

Các trường hợp nên bao phủ:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Dependency tạm thời lỗi | Exception được phân loại retryable và retry có giới hạn. |
| Payload sai schema | Không retry vô hạn; event được quarantine hoặc báo lỗi hợp đồng. |
| Từ chối nghiệp vụ | Phát event kết quả phù hợp thay vì coi là lỗi hạ tầng. |
| Optimistic lock conflict | Transaction được retry có kiểm soát hoặc xung đột được xử lý rõ. |
| Lỗi lập trình | Không bị che bởi retry vô hạn; có log và alert. |
| Timeout sau side effect | Đối soát trước khi gửi lại thao tác. |
| Listener bắt và nuốt exception | Test phát hiện publication bị đánh dấu hoàn tất sai hoặc handler phải được sửa. |
| Listener ném exception | Publication chưa hoàn tất theo cơ chế registry và có thể recovery theo cấu hình. |
| Retry thành công | Side effect chỉ xuất hiện một lần nhờ idempotency. |
| Hết giới hạn retry | Event được chuyển sang DLT/quarantine hoặc trạng thái cần can thiệp. |

Nên kiểm thử crash window: side effect đã commit nhưng completion chưa được ghi. Khi event được giao lại, handler phải nhận diện duplicate và kết thúc an toàn.

## 14. Quan sát lỗi handler trong môi trường chạy thật

Log và metric cần thể hiện cả loại lỗi lẫn vị trí xảy ra. Các trường hữu ích gồm eventId, eventType, listenerId, module, correlationId, failureCategory, errorCode, attemptCount và publication identifier nếu có.

Các chỉ số nên theo dõi:

- Tỷ lệ thành công/thất bại theo listener và event type.
- Số lỗi retryable, non-retryable và business outcome.
- Số lần retry, tuổi của publication incomplete và thời gian xử lý.
- Số event trong DLT/quarantine và tuổi của event lâu nhất.
- Tỷ lệ lỗi deserialize/schema mismatch.
- Số lỗi kết quả không xác định đang chờ đối soát.
- Số lần replay và tỷ lệ replay thành công.

Alert nên dựa trên ngưỡng và xu hướng, không chỉ tổng số exception. Một spike lỗi timeout có thể báo dependency đang suy giảm; một event schema mismatch duy nhất sau deploy cũng có thể chỉ ra publisher và consumer không tương thích.

Khi điều tra, xác định event và listener trước, sau đó xem exception type/cause, failure category, trạng thái transaction, publication status và side effect có thể đã xảy ra hay chưa. Tránh log toàn bộ payload nếu có dữ liệu nhạy cảm.

## 15. Checklist phân loại lỗi handler

- Mỗi handler có danh sách lỗi kỹ thuật và outcome nghiệp vụ có thể gặp.
- Lỗi hạ tầng tạm thời được phân biệt với lỗi dữ liệu, cấu hình và lỗi lập trình.
- Từ chối nghiệp vụ được biểu đạt bằng kết quả/event domain phù hợp.
- Exception taxonomy dựa trên type hoặc error code, không dựa vào chuỗi message.
- Retry có giới hạn, backoff, jitter khi phù hợp và không retry lỗi cố định.
- Kết quả UNKNOWN được đối soát trước khi retry hoặc bù trừ.
- Handler không nuốt exception khi publication cần được recovery.
- Listener idempotent để chịu được duplicate và crash window.
- DLT/quarantine giữ đủ metadata để điều tra và replay có kiểm soát.
- Event Publication Registry được phân biệt với trạng thái nghiệp vụ và chính sách retry domain.
- Integration test bao phủ các nhóm lỗi, transaction, retry, replay và side effect.
- Dashboard/alert phân loại lỗi theo listener, event type, dependency và tuổi backlog.

Phân loại lỗi handler giúp hệ thống chọn đúng phản ứng cho từng nguyên nhân: retry khi có khả năng phục hồi, chuyển nhánh khi đó là kết quả nghiệp vụ, quarantine khi payload không thể xử lý và đối soát khi side effect chưa rõ. Kết hợp exception taxonomy, listener idempotent, publication registry, retry có giới hạn và quan sát theo event sẽ giúp giao tiếp bằng application events đáng tin cậy mà không che giấu lỗi hoặc lặp tác động nghiệp vụ.
