# Mô tả lỗi

Application events giúp các module Spring Modulith giao tiếp qua những sự kiện mô tả điều đã xảy ra trong nghiệp vụ. Khi publisher, listener hoặc hệ thống nhận gặp sự cố, đội phát triển và vận hành cần mô tả lỗi theo một cách nhất quán để biết điều gì đã xảy ra, event nào bị ảnh hưởng, có thể thử lại hay không và cần làm gì tiếp theo.

Mô tả lỗi tốt không chỉ là một exception message. Nó là một hợp đồng chẩn đoán gồm mã lỗi ổn định, ý nghĩa, nguyên nhân có thể, ngữ cảnh event, khả năng retry, tác động và hướng khắc phục. Với Spring Modulith, tài liệu cần chỉ rõ lỗi xảy ra ở chặng publish, publication registry, listener nội bộ hay externalization; mỗi chặng có cách phục hồi khác nhau.

## 1. Vì sao cần chuẩn hóa mô tả lỗi?

Một event có thể đi qua nhiều thành phần: use case phát event, Event Publication Registry theo dõi listener, listener xử lý nghiệp vụ, adapter externalization gửi message tới broker và consumer cập nhật dữ liệu ở hệ thống khác. Một thông báo chung như `Event processing failed` không cho biết lỗi ở đâu hoặc ai cần hành động.

Mô tả lỗi có cấu trúc giúp:

- Tìm nhanh event, listener, destination và lần xử lý liên quan.
- Phân biệt lỗi tạm thời có thể retry với lỗi dữ liệu hoặc nghiệp vụ cần can thiệp.
- Giảm thời gian điều tra nhờ nguyên nhân và bước khắc phục được ghi rõ.
- Giúp dashboard nhóm lỗi theo mã ổn định thay vì phân tích chuỗi exception tự do.
- Tạo hợp đồng nhất quán giữa log, alert, API vận hành và tài liệu runbook.
- Tránh ghi payload hoặc thông tin nhạy cảm vào thông báo lỗi.

## 2. Xác định lỗi nằm ở chặng nào

Trước khi đặt tên lỗi, hãy xác định ranh giới nơi xử lý thất bại:

~~~mermaid
flowchart LR
    A[Publisher / use case] --> B[Event Publication Registry]
    B --> C[Internal listener]
    B --> D[Externalization listener]
    D --> E[Message broker]
    E --> F[External consumer]
    A -. error context .-> G[Error record / logs]
    B -. error context .-> G
    C -. error context .-> G
    D -. error context .-> G
    F -. error context .-> G
~~~

| Chặng | Ví dụ lỗi | Thông tin cần mô tả |
| --- | --- | --- |
| Publish event | Payload không hợp lệ, lỗi khi đăng ký publication | Use case, event type, transaction outcome và nguyên nhân publish thất bại |
| Publication registry | Không ghi hoặc đọc được publication bền vững | Listener target, publication ID, persistence adapter và trạng thái transaction |
| Internal listener | Exception trong xử lý nghiệp vụ hoặc cập nhật projection | Listener, event ID, aggregate ID/version và side effect đã thực hiện tới đâu |
| Externalization | Serialize hoặc gửi message thất bại | Destination, converter, content type, broker result và publication state |
| External consumer | Deserialize hoặc xử lý message thất bại | Consumer group, topic/partition/offset, event type/version và trạng thái side effect |

Không suy ra consumer đã lỗi chỉ vì externalization listener chưa hoàn tất. Ngược lại, publication externalization đã hoàn tất cũng không chứng minh consumer cuối cùng đã xử lý nghiệp vụ.

## 3. Cấu trúc của một mô tả lỗi

Một error catalog nên có các trường nhất quán. Có thể dùng mẫu sau cho từng lỗi:

| Trường | Nội dung cần ghi |
| --- | --- |
| `code` | Mã lỗi ổn định, duy nhất trong phạm vi hệ thống |
| `title` | Tiêu đề ngắn, dễ tìm |
| `description` | Điều gì đã thất bại và ở chặng nào |
| `category` | Nhóm kỹ thuật hoặc nghiệp vụ |
| `severity` | Mức độ ảnh hưởng và ưu tiên phản ứng |
| `retryable` | Có thể retry tự động hay cần xử lý trước |
| `symptoms` | Dấu hiệu trong log, metric, dashboard hoặc API |
| `causes` | Các nguyên nhân thường gặp |
| `context` | Event, listener, destination và correlation cần thu thập |
| `recovery` | Các bước khắc phục và phục hồi |
| `owner` | Nhóm chịu trách nhiệm xử lý |

Không nhất thiết mọi hệ thống phải lưu tất cả trường trong một object runtime. Đây là cấu trúc tài liệu và quan sát; chỉ những trường thực sự cần cho luồng vận hành mới nên được đưa vào payload hoặc database.

## 4. Quy ước mã lỗi

Mã lỗi cần ổn định qua các lần deploy. Một quy ước có thể dùng tiền tố theo miền và nhóm lỗi, ví dụ:

| Mã minh họa | Ý nghĩa |
| --- | --- |
| `EVENT-PUB-001` | Không thể đăng ký publication cho event |
| `EVENT-LISTENER-001` | Listener thất bại khi xử lý event |
| `EVENT-REGISTRY-001` | Không thể đọc hoặc cập nhật publication registry |
| `EVENT-EXT-001` | Không thể serialize hoặc externalize event |
| `EVENT-CONSUMER-001` | Consumer không thể deserialize hoặc xử lý message |
| `EVENT-CONTRACT-001` | Payload không tương thích với hợp đồng event được hỗ trợ |

Các mã trên là quy ước do ứng dụng định nghĩa để minh họa, không phải mã lỗi built-in của Spring Modulith. Không tái sử dụng mã đã công bố cho một ý nghĩa khác. Nếu nguyên nhân thay đổi nhưng ý nghĩa lỗi vẫn giống nhau, có thể giữ code và thay đổi chi tiết nguyên nhân.

Không nhúng event ID, order ID, timestamp hoặc exception message vào error code. Những giá trị đó thuộc ngữ cảnh của từng lần xảy ra lỗi; code phải có cardinality thấp để dashboard và alert có thể nhóm ổn định.

## 5. Phân loại lỗi và khả năng retry

Mô tả lỗi phải trả lời rõ có nên retry hay không. Phân loại tham khảo:

| Nhóm | Ví dụ | Retry? | Hành động |
| --- | --- | --- | --- |
| Transient infrastructure | Database tạm thời không kết nối, network reset, broker unavailable | Có giới hạn | Backoff, kiểm tra dependency và retry theo budget |
| Dependency throttling | HTTP 429, broker quota hoặc rate limit | Có điều kiện | Tôn trọng `Retry-After`, giảm concurrency hoặc tốc độ |
| Serialization/contract | Thiếu field bắt buộc, sai kiểu dữ liệu, schema không hỗ trợ | Không retry nguyên trạng | Sửa payload, schema hoặc phiên bản consumer |
| Business rejection | Trạng thái đơn hàng không hợp lệ, không đủ điều kiện nghiệp vụ | Thường không | Ghi nhận kết quả nghiệp vụ hoặc chuyển quy trình xử lý |
| Authorization/configuration | Credential hết hạn, ACL sai, thiếu quyền | Chỉ sau khi sửa nguyên nhân | Cảnh báo owner và cập nhật cấu hình |
| Unknown outcome | Request timeout nhưng hệ thống đích có thể đã tạo side effect | Cần xác minh | Tra cứu trạng thái hoặc retry bằng idempotency key |

Retryability là thuộc tính của lỗi trong một ngữ cảnh, không chỉ của exception class. Ví dụ HTTP 503 thường có thể retry; HTTP 400 thường không. Tuy nhiên, một lỗi 400 do request sai chỉ có thể giải quyết bằng sửa dữ liệu, còn lỗi 401 do credential vừa được luân chuyển có thể phục hồi sau khi cấu hình được sửa.

Không ghi `retryable=true` nếu không có giới hạn số lần, backoff, idempotency và cách kết thúc khi hết retry. Retry vô hạn có thể tạo backlog và làm dependency quá tải hơn.

## 6. Mẫu error record cho log và quan sát

Ví dụ một error record dạng JSON cho listener thất bại:

~~~json
{
  "code": "EVENT-LISTENER-001",
  "title": "Inventory listener failed",
  "category": "TRANSIENT_DEPENDENCY",
  "severity": "ERROR",
  "retryable": true,
  "eventId": "7d8b2c1a-...",
  "eventType": "OrderConfirmedV2",
  "listener": "inventoryProjectionListener",
  "aggregateId": "order-123",
  "aggregateVersion": 17,
  "correlationId": "flow-456",
  "attempt": 2,
  "dependency": "inventory-database",
  "exceptionType": "TransientDataAccessException",
  "occurredAt": "2026-11-25T10:30:00Z"
}
~~~

Đây là error record minh họa do ứng dụng định nghĩa. Chỉ đưa các trường thực sự có sẵn và hữu ích. Không lưu toàn bộ payload, địa chỉ, token, thông tin thanh toán hoặc exception message có thể chứa dữ liệu nhạy cảm.

Giữ `code` và `category` ổn định; `eventId`, `correlationId`, `attempt`, dependency và timestamp thay đổi theo từng lần xảy ra. Nếu cần lưu exception message để điều tra, hãy giới hạn quyền truy cập và lọc dữ liệu trước khi ghi.

## 7. Viết mô tả nguyên nhân và triệu chứng

Phần mô tả nên trả lời ba câu hỏi: điều gì xảy ra, điều gì bị ảnh hưởng và trạng thái hiện tại là gì.

Ví dụ chưa đủ thông tin:

> Event failed.

Ví dụ tốt hơn:

> Listener `inventoryProjectionListener` không cập nhật được projection cho event `OrderConfirmedV2` vì kết nối database bị timeout. Publication tới listener vẫn chưa hoàn tất; event có thể được retry sau khi database phục hồi. Chưa xác nhận trạng thái cập nhật ở projection.

Một mô tả tốt tránh khẳng định điều chưa biết. Nếu timeout xảy ra sau khi gửi request tới hệ thống ngoài, ghi rõ kết quả chưa xác định thay vì khẳng định thao tác đã thất bại hoàn toàn.

Triệu chứng nên có thể đối chiếu với tín hiệu quan sát:

- Error code xuất hiện trong log hoặc error record.
- Pending publication tăng hoặc có publication quá tuổi.
- Listener failure rate tăng.
- Processing latency vượt SLO.
- Externalization send failure hoặc consumer lag tăng.
- DLT/quarantine nhận thêm message.

## 8. Mô tả lỗi theo chặng Spring Modulith

### 8.1. Publisher và transaction

**Ví dụ:** use case không thể publish event hoặc transaction rollback.

Mô tả cần chỉ ra transaction có commit hay không. Nếu transaction rollback, không được mô tả event như một publication đã được giao thành công. Nếu lỗi xảy ra khi đăng ký publication trong transaction, cần ghi rõ transaction outcome và event type.

Thông tin cần thu thập: use case, event type, aggregate ID/version, transaction outcome, exception class và correlation ID.

### 8.2. Event Publication Registry

**Ví dụ:** publication chưa hoàn tất vì listener ném exception hoặc persistence registry không truy cập được.

Phân biệt lỗi listener với lỗi lưu trạng thái registry. Registry theo dõi publication tới listener; publication incomplete là tín hiệu cần điều tra hoặc phục hồi theo cấu hình. Không coi trạng thái này là bằng chứng event đã mất hoặc consumer bên ngoài đã lỗi.

Thông tin cần thu thập: publication identifier nếu adapter cung cấp, listener target, thời điểm tạo, trạng thái incomplete, lỗi gần nhất và tuổi publication.

### 8.3. Internal listener

**Ví dụ:** listener cập nhật projection nhưng gặp lỗi constraint hoặc dependency database.

Mô tả cần ghi listener nào, side effect nào đã commit hay chưa, lỗi có thể retry không và điều kiện để retry an toàn. Nếu listener đã thực hiện side effect ngoài database trước khi lỗi, phải xác minh trạng thái đó trước khi giao lại event.

Thông tin cần thu thập: event ID, event type, listener, aggregate ID/version, attempt, dependency, exception class và trạng thái idempotency.

### 8.4. Externalization

**Ví dụ:** serializer không thể chuyển payload thành message hoặc producer không gửi được tới broker.

Phân biệt lỗi serialize với lỗi gửi. Lỗi serialize thường không tự biến mất khi retry cùng payload; lỗi broker unavailable có thể tạm thời. Mô tả cần có destination, content type, event type/version, producer result và trạng thái publication externalization.

Thông tin cần thu thập: destination logic, adapter, serializer/converter, broker response, correlation ID và attempt.

### 8.5. External consumer

**Ví dụ:** consumer không deserialize được payload hoặc xử lý nghiệp vụ thất bại.

Đây là chặng sau khi broker đã nhận message. Error record cần chỉ rõ consumer group, topic, partition/offset nếu có, event type/version và trạng thái side effect. Không dùng publication status của ứng dụng phát để kết luận consumer đã hoàn tất.

## 9. Ví dụ exception có mã lỗi ổn định

Ứng dụng có thể ánh xạ exception kỹ thuật thành error code nội bộ để log và quan sát. Ví dụ:

~~~java
public enum EventErrorCode {
    LISTENER_FAILED("EVENT-LISTENER-001"),
    EXTERNALIZATION_FAILED("EVENT-EXT-001"),
    CONTRACT_UNSUPPORTED("EVENT-CONTRACT-001");

    private final String code;

    EventErrorCode(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Error code không nên thay thế exception gốc. Khi log, ghi code ổn định cùng exception class và stack trace có kiểm soát. Không gửi stack trace cho client hoặc consumer như một phần hợp đồng công khai.

Ví dụ một exception nghiệp vụ có chứa code và nguyên nhân:

~~~java
public class EventHandlingException extends RuntimeException {

    private final EventErrorCode errorCode;

    public EventHandlingException(
            EventErrorCode errorCode,
            String message,
            Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public EventErrorCode errorCode() {
        return errorCode;
    }
}
~~~

Không bọc mọi exception thành một loại chung nếu việc đó làm mất thông tin phân loại retry. Có thể giữ cause chain và ánh xạ category riêng dựa trên loại lỗi, dependency và trạng thái side effect.

## 10. Tài liệu hóa một lỗi hoàn chỉnh

Ví dụ một entry trong error catalog:

### EVENT-EXT-001 — Không thể externalize event

**Mô tả:** Adapter externalization không thể chuyển application event thành message hoặc không gửi được message tới destination đã cấu hình.

**Phạm vi ảnh hưởng:** Event được đánh dấu externalization có thể chưa tới broker. Publication listener externalization có thể chưa hoàn tất tùy vị trí phát sinh lỗi.

**Nguyên nhân có thể:**

- Serializer không hỗ trợ kiểu dữ liệu trong payload.
- Schema hoặc type metadata không tương thích.
- Broker không sẵn sàng hoặc kết nối bị timeout.
- Destination sai hoặc tài khoản producer không có quyền gửi.

**Khả năng retry:**

- Có thể retry có giới hạn khi broker/network tạm thời lỗi.
- Không retry vô hạn lỗi serializer, schema hoặc destination cấu hình sai.
- Với timeout có kết quả không xác định, kiểm tra khả năng message đã được broker nhận trước khi gửi lại; consumer phải idempotent.

**Thông tin điều tra:** event ID, event type/version, destination, serializer, content type, correlation ID, broker response và publication state.

**Khắc phục:**

1. Xác định lỗi ở bước serialize hay send.
2. Nếu payload/schema sai, sửa hợp đồng hoặc converter rồi kiểm thử lại bằng payload mẫu.
3. Nếu broker lỗi, kiểm tra health, ACL, network và quota.
4. Sau khi nguyên nhân được khắc phục, resubmit publication theo quy trình ứng dụng.
5. Theo dõi publication hoàn tất và xác minh message xuất hiện ở broker/consumer theo đúng chặng.

**Owner:** Nhóm sở hữu integration adapter hoặc nền tảng messaging.

Entry này là ví dụ do ứng dụng định nghĩa. Tên mã, owner và các bước cụ thể cần được thống nhất trong error catalog của tổ chức.

## 11. Phân biệt lỗi kỹ thuật và kết quả nghiệp vụ

Không phải mọi kết quả không thành công đều là exception. Ví dụ, một đơn hàng bị từ chối vì không đủ điều kiện có thể là kết quả nghiệp vụ hợp lệ, không phải lỗi listener.

| Tình huống | Cách mô tả |
| --- | --- |
| Không đủ tồn kho theo quy tắc nghiệp vụ | Business outcome như `RESERVATION_REJECTED`; ghi nhận lý do nghiệp vụ |
| Database timeout khi ghi projection | Technical failure; đánh giá retryability |
| Payload không đúng schema | Contract/data error; cần sửa payload hoặc consumer |
| Credential broker hết hạn | Configuration/authorization failure; cần owner cập nhật quyền |

Việc phân biệt giúp dashboard không tính mọi từ chối nghiệp vụ là lỗi hệ thống và không retry những thao tác vốn không nên thử lại.

## 12. Mô tả lỗi và trạng thái publication

Trong Spring Modulith, Event Publication Registry theo dõi publication tới listener. Khi listener hoàn tất, publication được đánh dấu hoàn tất; khi listener lỗi, publication có thể còn incomplete để được phục hồi theo cấu hình.

Tài liệu lỗi nên ghi rõ trạng thái liên quan nhưng tránh tự đặt tên trạng thái framework không cung cấp. Có thể mô tả theo các khái niệm:

- Publication đã được đăng ký cho listener.
- Listener đang xử lý hoặc chưa hoàn tất.
- Listener hoàn tất thành công.
- Publication còn incomplete sau exception hoặc gián đoạn.
- Publication được resubmit theo quy trình phục hồi.

Không giả định registry tự cung cấp mọi thông tin attempt, exception hoặc lịch retry. Nếu ứng dụng cần các trường đó, hãy instrument hoặc lưu chúng trong error/task store riêng.

Registry cũng không phải event store dài hạn. Publication completed có thể được dọn theo retention; error catalog và audit trail dài hạn cần được lưu ở nơi phù hợp.

## 13. Bảo mật trong thông báo lỗi

Error record thường được truy cập rộng hơn payload nghiệp vụ. Vì vậy, chỉ ghi thông tin cần thiết để điều tra:

- Ưu tiên event ID, event type, listener, destination và correlation ID.
- Không ghi access token, secret, credential hoặc khóa mã hóa.
- Che dữ liệu cá nhân, thông tin thanh toán và địa chỉ.
- Không đưa payload đầy đủ vào exception message hoặc alert.
- Kiểm soát quyền truy cập stack trace, DLT và error detail.
- Giới hạn thời gian lưu và ghi audit khi operator xem hoặc replay dữ liệu lỗi.

Error message có thể xuất hiện trong log, dashboard, email cảnh báo hoặc API vận hành. Hãy xem mọi nơi này là một bề mặt dữ liệu cần bảo vệ.

## 14. Checklist viết và cập nhật error catalog

Với mỗi lỗi mới, xác minh:

1. Mã lỗi ổn định và chưa được dùng cho ý nghĩa khác.
2. Tiêu đề mô tả rõ hành động hoặc chặng thất bại.
3. Nguyên nhân và triệu chứng được phân biệt với giả thuyết.
4. Event ID/type, listener, destination và correlation context cần thiết đã được liệt kê.
5. Retryability, giới hạn retry và điều kiện phục hồi được nêu rõ.
6. Side effect đã xảy ra hoặc trạng thái chưa xác định được đề cập.
7. Bước khắc phục có thứ tự và có thể thực hiện.
8. Owner và mức độ ưu tiên được xác định.
9. Thông tin nhạy cảm được loại bỏ hoặc che.
10. Dashboard, log và runbook sử dụng cùng mã lỗi.

Khi thay đổi hành vi lỗi, cập nhật error catalog cùng thay đổi code và cảnh báo. Không xóa mã cũ ngay nếu log, dashboard hoặc tài liệu vận hành vẫn cần tra cứu lịch sử.

## 15. Những sai lầm cần tránh

- Dùng một thông báo `Event failed` cho mọi chặng.
- Dùng exception message làm mã lỗi ổn định.
- Ghi `retryable=true` mà không có retry budget hoặc idempotency.
- Coi lỗi nghiệp vụ là lỗi kỹ thuật cần retry.
- Khẳng định event đã mất hoặc consumer đã lỗi khi chưa có bằng chứng.
- Ghi toàn bộ payload, token hoặc dữ liệu cá nhân vào log.
- Làm mất exception cause khi ánh xạ sang error code.
- Giả định Event Publication Registry tự lưu mọi chi tiết lỗi và attempt.
- Dùng mã lỗi có event ID hoặc order ID làm tăng cardinality.
- Không chỉ rõ owner và bước khắc phục tiếp theo.

## Kết luận

Mô tả lỗi cho application events cần cho biết lỗi xảy ra ở chặng nào, event và listener nào bị ảnh hưởng, nguyên nhân đã biết, khả năng retry và hành động phục hồi. Chuẩn hóa error code, category, severity, event context và recovery steps giúp log, dashboard và runbook cùng diễn đạt một sự cố. Trong Spring Modulith, luôn phân biệt publication registry, listener nội bộ, externalization và consumer bên ngoài; ghi rõ trạng thái đã xác minh và bảo vệ dữ liệu nhạy cảm. Nhờ đó, lỗi trở nên dễ tìm, dễ phân loại và có thể xử lý nhất quán.
