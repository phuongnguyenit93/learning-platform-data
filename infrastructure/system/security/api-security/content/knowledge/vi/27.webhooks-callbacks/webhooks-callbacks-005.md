# Idempotency cho event gửi lại

## 1. Vì sao webhook cần idempotency?

Webhook provider gửi HTTP request đến endpoint của ứng dụng khi một sự kiện xảy ra, chẳng hạn thanh toán thành công, đơn hàng được giao hoặc subscription thay đổi. Mạng có thể mất kết nối, response có thể bị thất lạc, server có thể timeout sau khi đã xử lý xong, hoặc provider không nhận được mã `2xx`. Trong những trường hợp đó, provider thường gửi lại cùng event.

Vì vậy, webhook delivery thường có ngữ nghĩa **at-least-once**: một event có thể được gửi một hoặc nhiều lần cho đến khi provider nhận được xác nhận hoặc hết chính sách retry. Ứng dụng phải dự kiến duplicate delivery và bảo đảm cùng một event không tạo tác dụng phụ nghiệp vụ nhiều lần.

Ví dụ, provider gửi event `payment.succeeded` cho payment `pay-123`. Ứng dụng đã ghi nhận thanh toán nhưng response `200` bị mất trên đường truyền. Provider gửi lại event. Nếu handler cộng số dư hoặc tạo đơn giao hàng mỗi lần nhận request, khách hàng có thể bị ghi nhận thanh toán hai lần hoặc nhận hai lệnh giao hàng.

**Idempotency** là thuộc tính mà việc xử lý lặp lại cùng một logical operation không làm thay đổi kết quả cuối nhiều hơn một lần. Với webhook, điều này thường được thực hiện bằng event identity ổn định, lưu dấu đã nhận/xử lý một cách bền vững và bảo vệ các side effect trong cùng ranh giới transaction hoặc bằng cơ chế phối hợp tương đương.

Không nên giả định webhook chỉ đến một lần, đến đúng thứ tự hoặc chỉ retry khi handler chưa chạy. Server có thể đã xử lý thành công nhưng response bị thất lạc; đó là tình huống duplicate phổ biến.

## 2. Phân biệt delivery attempt, event và business operation

Ba khái niệm cần được tách biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Một sự kiện logic do provider phát ra. | `evt_789` biểu thị payment đã thành công. |
| Delivery attempt | Một lần provider gửi event qua HTTP. | Lần gửi thứ nhất timeout, lần thứ hai nhận `200`. |
| Business operation | Tác động nghiệp vụ mà ứng dụng thực hiện khi xử lý event. | Đánh dấu invoice đã thanh toán và phát lệnh fulfillment. |

Một event có thể có nhiều delivery attempt nhưng chỉ nên tạo một business operation tương ứng. Ngược lại, hai event khác ID có thể mô tả hai sự kiện riêng biệt và hợp lệ ngay cả khi payload giống nhau.

Không dùng hash của toàn bộ payload làm idempotency key mặc định. Hai event hợp lệ có thể có payload giống nhau, ví dụ hai lần cập nhật cùng trạng thái hoặc hai giao dịch có cùng amount. Nếu dedupe bằng payload hash, ứng dụng có thể bỏ qua một sự kiện hợp lệ. Hãy dùng event ID do provider cấp hoặc một khóa logic ổn định được định nghĩa trong contract.

## 3. Chọn idempotency key ổn định và có phạm vi

Ưu tiên event identifier do provider cấp, ví dụ `event_id`, `delivery_id` hoặc ID tương đương. Khóa nên được định danh trong phạm vi provider/account/endpoint để tránh trùng giữa các nguồn.

Một khóa deduplication có thể gồm:

```text
provider_id + provider_account_id + event_id
```

Nếu cùng provider có nhiều môi trường, tenant hoặc endpoint subscription, cần quyết định scope theo semantics của provider. Đừng thêm delivery attempt ID vào khóa dedupe nếu mỗi lần retry có attempt ID khác nhau; làm vậy sẽ khiến mỗi lần gửi lại trông như event mới.

| Nguồn khóa | Đánh giá |
|---|---|
| Event ID ổn định từ provider | Lựa chọn ưu tiên nếu contract bảo đảm ID không đổi qua retry. |
| Business object ID + event type + version | Dùng khi provider không có event ID, nhưng phải bảo đảm phân biệt được các thay đổi hợp lệ trên cùng object. |
| Client-generated key trong event đã ký | Có thể dùng nếu provider contract định nghĩa rõ uniqueness và retry semantics. |
| Timestamp + payload hash | Không nên dùng đơn lẻ; timestamp có thể thay đổi, payload giống nhau có thể là hai event hợp lệ. |
| Delivery attempt ID | Không phù hợp để nhận diện event nếu mỗi retry có ID khác. |

Nếu provider không cung cấp ID ổn định, hãy xác định một khóa nghiệp vụ dựa trên dữ liệu có semantics rõ ràng, chẳng hạn `provider + payment_id + transition_version`. Cần phối hợp với provider để biết event có thể được phát lại, sửa đổi hoặc phát nhiều lần cho cùng một object hay không.

## 4. Xác minh chữ ký trước khi tin event

Idempotency không thay thế authentication. Kẻ tấn công có thể tự gửi request với event ID đã từng thấy hoặc ID mới. Handler cần xác minh nguồn event trước khi lưu hoặc xử lý.

Một luồng webhook điển hình:

1. Nhận raw HTTP body và các signature headers.
2. Xác minh chữ ký theo đúng thuật toán, secret/public key, timestamp và format mà provider quy định.
3. Kiểm tra timestamp/replay window theo clock skew cho phép.
4. Parse envelope và kiểm tra các trường bắt buộc, provider account, event ID và event type.
5. Kiểm tra event có thuộc integration/tenant mà endpoint đang phục vụ không.
6. Ghi nhận event bền vững bằng idempotency key.
7. Chỉ trả `2xx` sau khi event đã được lưu bền vững hoặc xử lý đồng bộ thành công theo thiết kế.

Với HMAC signature, thường phải tính chữ ký trên đúng raw bytes và timestamp/header theo contract của provider. Không parse JSON rồi serialize lại trước khi xác minh nếu provider ký raw body; thay đổi whitespace, thứ tự field hoặc encoding có thể làm chữ ký khác. So sánh chữ ký theo constant-time comparison khi tự triển khai, hoặc ưu tiên SDK chính thức đã được kiểm chứng.

Timestamp signature giúp giới hạn việc phát lại request cũ trong một khoảng thời gian, nhưng không thay thế event deduplication. Một delivery hợp lệ có thể được provider retry trong thời gian sau đó bằng timestamp/chữ ký mới nhưng cùng event ID. Vì vậy cần cả replay-window validation lẫn idempotency record bền vững.

Không ghi webhook secret, signature đầy đủ hoặc raw payload nhạy cảm vào log. Hỗ trợ rotation secret/key theo contract provider và có thể chấp nhận key cũ/mới trong một giai đoạn chuyển tiếp có giới hạn.

## 5. Lưu event đã nhận bằng unique constraint

Deduplication phải được thực hiện nguyên tử ở nơi lưu trữ dùng chung giữa mọi instance. Một map trong RAM hoặc cache cục bộ không đủ: hai instance có thể nhận cùng event đồng thời, hoặc ứng dụng khởi động lại sẽ mất trạng thái.

Ví dụ bảng inbox trong PostgreSQL:

```sql
CREATE TABLE webhook_inbox (
    id                  BIGSERIAL PRIMARY KEY,
    provider_id         VARCHAR(80) NOT NULL,
    provider_account_id VARCHAR(120) NOT NULL,
    event_id            VARCHAR(200) NOT NULL,
    event_type          VARCHAR(120) NOT NULL,
    payload             JSONB NOT NULL,
    payload_sha256      CHAR(64) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at        TIMESTAMPTZ,
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error_code     VARCHAR(80),
    CONSTRAINT uq_webhook_event
        UNIQUE (provider_id, provider_account_id, event_id)
);
```

Unique constraint là lớp bảo vệ quyết định trước race condition. Không thực hiện `SELECT` để kiểm tra event có tồn tại rồi mới `INSERT` như hai thao tác tách biệt; hai request đồng thời có thể cùng thấy “chưa tồn tại” và cùng xử lý. Hãy dùng unique index/constraint và thao tác insert nguyên tử.

Ví dụ insert không làm lỗi transaction khi duplicate:

```sql
INSERT INTO webhook_inbox (
    provider_id,
    provider_account_id,
    event_id,
    event_type,
    payload,
    payload_sha256,
    status
)
VALUES (
    :provider_id,
    :provider_account_id,
    :event_id,
    :event_type,
    CAST(:payload AS jsonb),
    :payload_sha256,
    'RECEIVED'
)
ON CONFLICT (provider_id, provider_account_id, event_id)
DO NOTHING
RETURNING id;
```

Nếu insert trả về một row, event mới đã được ghi nhận. Nếu không có row, khóa đã tồn tại và đây là duplicate theo scope đã chọn. Có thể đọc record hiện tại để kiểm tra trạng thái và payload fingerprint.

Nếu cùng event ID nhưng payload hash khác, không âm thầm coi là duplicate bình thường. Đây có thể là lỗi provider, key scope sai, event ID bị tái sử dụng hoặc dấu hiệu giả mạo. Ghi security/operational alert, lưu bằng chứng an toàn và xử lý theo contract. Không ghi raw payload nhạy cảm vào alert.

## 6. Hai chiến lược xử lý: đồng bộ và inbox bất đồng bộ

### Xử lý đồng bộ trong một transaction

Phù hợp khi công việc ngắn, chỉ tác động đến cùng database và có thể hoàn tất trong thời gian request hợp lý.

1. Xác minh chữ ký.
2. Bắt đầu transaction.
3. Insert event ID vào bảng inbox với unique constraint.
4. Nếu duplicate đã hoàn tất, trả kết quả thành công mà không lặp side effect.
5. Nếu mới, cập nhật domain state và đánh dấu event processed trong cùng transaction.
6. Commit; chỉ sau commit mới trả `2xx`.

Nếu transaction rollback, cả inbox row và domain change đều rollback; provider có thể retry. Nếu transaction commit nhưng response bị mất, retry tiếp theo gặp unique constraint và không lặp tác dụng phụ.

### Nhận event rồi xử lý bất đồng bộ

Phù hợp khi cần gọi service ngoài, xử lý file, gửi email hoặc thực hiện công việc lâu. HTTP handler chỉ xác minh và lưu event vào inbox bền vững; worker xử lý sau.

1. Xác minh chữ ký và envelope.
2. Insert inbox row và thông tin cần thiết trong transaction.
3. Nếu insert mới thành công, commit.
4. Sau commit, trả `2xx` cho provider.
5. Worker claim event chưa xử lý, thực hiện business operation idempotently và cập nhật trạng thái.
6. Lỗi tạm thời được retry nội bộ; lỗi không thể khắc phục được đưa vào dead-letter/manual review.

Không trả `2xx` trước khi event đã được ghi bền vững. Nếu process chết sau khi trả `2xx` nhưng trước khi lưu event, provider sẽ không gửi lại và event bị mất. Nếu cần phát tín hiệu cho worker, dùng transactional outbox hoặc cơ chế queue được ghi cùng transaction với inbox row.

## 7. Trạng thái xử lý và concurrency

Một event có thể đi qua các trạng thái như:

```text
RECEIVED -> PROCESSING -> PROCESSED
                    \-> RETRY_WAIT -> PROCESSING
                    \-> DEAD_LETTER
```

Ý nghĩa:

- `RECEIVED`: event đã được xác minh và lưu bền vững.
- `PROCESSING`: worker đã claim event; có lease/lock để tránh worker khác xử lý đồng thời.
- `RETRY_WAIT`: lỗi tạm thời, chờ thời điểm retry.
- `PROCESSED`: business operation đã commit thành công.
- `DEAD_LETTER`: hết retry hoặc gặp lỗi không thể xử lý tự động; cần cảnh báo/đối soát.

Với nhiều worker, claim event bằng row lock (`SELECT ... FOR UPDATE SKIP LOCKED`), atomic status transition hoặc queue visibility timeout. Cần lease timeout để phục hồi khi worker chết giữa chừng. Worker chỉ được chuyển sang `PROCESSED` sau khi business state và các outbox records liên quan đã commit.

Nếu worker chết sau side effect nhưng trước khi ghi `PROCESSED`, event có thể được claim lại. Vì vậy, status lock đơn thuần không bảo đảm idempotency; domain operation hoặc downstream call vẫn phải có idempotency key/unique constraint.

## 8. Bảo vệ business side effect

Ghi event ID vào inbox chỉ ngăn cùng event được nhận nhiều lần theo khóa đó. Nó chưa bảo đảm mọi side effect đều chỉ xảy ra một lần, nhất là khi xử lý có nhiều hệ thống.

### Database update

Nếu domain update nằm trong cùng database transaction với inbox state, hãy commit cả hai cùng nhau. Có thể lưu `source_event_id` với unique constraint trên bảng business operation để bảo vệ thêm ở tầng domain.

### Gửi email, tạo invoice hoặc phát message

Không thể gộp transaction database với SMTP, HTTP API hoặc queue bên ngoài theo cách ACID thông thường. Dùng transactional outbox:

1. Trong transaction xử lý event, cập nhật domain state và insert một outbox record có operation ID duy nhất.
2. Commit transaction.
3. Dispatcher đọc outbox và gửi tới hệ thống ngoài.
4. Đánh dấu đã gửi hoặc retry khi lỗi.
5. Consumer/downstream cũng dedupe theo operation ID.

Outbox dispatcher có thể gửi cùng message nhiều lần nếu crash sau khi downstream nhận nhưng trước khi đánh dấu `SENT`. Consumer phải idempotent hoặc hỗ trợ idempotency key. Outbox cung cấp bảo đảm không mất ý định gửi khi domain transaction commit; nó không tự tạo exactly-once delivery xuyên hệ thống.

### Gọi API thanh toán hoặc đối tác

Nếu downstream hỗ trợ `Idempotency-Key`, dùng một key ổn định cho cùng business operation, ví dụ `refund:{internal_refund_id}`. Không tạo key mới mỗi lần retry. Lưu mapping giữa event ID, internal operation ID và downstream idempotency key để có thể điều tra.

Nếu downstream không hỗ trợ idempotency, cần thiết kế reconciliation/query trạng thái trước khi retry một thao tác có thể tạo tác dụng phụ. Không giả định timeout nghĩa là downstream chưa thực hiện.

## 9. Event ordering và event đến trễ

Idempotency xử lý duplicate, không bảo đảm event được xử lý đúng thứ tự. Provider có thể gửi `subscription.updated` trước `subscription.created`, hoặc event cũ đến sau event mới do retry và network delay.

Nếu thứ tự quan trọng:

- Dùng sequence number, object version hoặc event timestamp có semantics được provider xác nhận.
- Lưu version hiện tại của aggregate và chỉ áp dụng event nếu version mới hơn theo contract.
- Nếu phát hiện gap, lấy trạng thái hiện tại từ provider qua API đáng tin cậy hoặc đưa event vào hàng đợi chờ.
- Không dựa vào timestamp đơn thuần nếu clock/provider semantics không bảo đảm thứ tự.
- Xử lý event trễ theo domain rule; một trạng thái cũ không được ghi đè trạng thái mới hơn.

Ví dụ, order version 12 đã ở `SHIPPED`. Một event version 10 đến trễ báo `PAID`. Không nên ghi đè order về trạng thái cũ; cần xác minh transition hợp lệ và version.

Nếu provider gửi snapshot hiện tại thay vì event delta, có thể xử lý theo cách cập nhật trạng thái mới nhất sau khi xác minh version. Contract cần nói rõ event là delta, snapshot hay notification để consumer chọn đúng semantics.

## 10. Retry và acknowledgement với provider

Provider thường retry khi nhận timeout, lỗi mạng hoặc mã response thuộc nhóm được cấu hình retry. Chính sách khác nhau theo provider; cần đọc contract và không giả định mọi provider retry cùng status code.

Các nguyên tắc:

- Trả `2xx` sau khi đã xử lý đồng bộ thành công hoặc đã lưu event bền vững vào inbox.
- Trả `5xx`/timeout khi không thể lưu event và muốn provider retry theo contract.
- Với event duplicate đã được lưu bền vững, thường trả `2xx` để dừng retry; không xử lý lại side effect.
- Không trả `2xx` chỉ vì request đã đến controller nếu chưa commit durable record.
- Đặt timeout xử lý ngắn ở webhook endpoint; công việc dài chuyển sang worker.
- Ghi nhận delivery attempt và provider request ID để điều tra, nhưng không dùng attempt ID thay event ID.

Retry của provider thường dùng exponential backoff, có thể kèm jitter và giới hạn thời gian/số lần. Consumer nội bộ cũng cần backoff, jitter, retry budget và circuit breaker để tránh retry storm. Không retry lỗi validation/chữ ký sai như lỗi tạm thời; phản hồi phù hợp theo contract và tạo security alert khi cần.

## 11. Retention của idempotency record

Không xóa deduplication record quá sớm. Nếu provider có thể retry event trong 7 ngày nhưng ứng dụng chỉ giữ event ID 24 giờ, một retry muộn có thể chạy side effect lần nữa.

Retention nên dài hơn:

- Thời gian retry tối đa của provider.
- Khoảng thời gian provider cho phép replay/redelivery thủ công.
- Độ trễ xử lý nội bộ và thời gian phục hồi sau outage.
- Thời gian cần thiết cho audit, reconciliation hoặc yêu cầu pháp lý.

Với nghiệp vụ tài chính, có thể cần lưu business operation ID lâu dài hơn inbox payload. Có thể xóa payload nhạy cảm theo data retention policy nhưng giữ tombstone gồm provider/account/event ID, kết quả và thời điểm xử lý để tiếp tục dedupe. Bảo vệ bảng inbox như dữ liệu nhạy cảm: giới hạn quyền đọc, mã hóa khi cần và không log payload đầy đủ.

## 12. Ví dụ triển khai với Spring Boot

Ví dụ controller dưới đây minh họa thứ tự xử lý. Phần xác minh chữ ký nên dùng SDK/logic theo contract provider; `rawBody` phải là đúng bytes đã nhận nếu chữ ký được tính trên raw body.

```java
@RestController
@RequestMapping("/webhooks/provider-a")
public class ProviderWebhookController {
    private final ProviderSignatureVerifier signatureVerifier;
    private final WebhookInboxService inboxService;

    public ProviderWebhookController(
            ProviderSignatureVerifier signatureVerifier,
            WebhookInboxService inboxService) {
        this.signatureVerifier = signatureVerifier;
        this.inboxService = inboxService;
    }

    @PostMapping
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader("Provider-Signature") String signature) {

        VerifiedWebhook event = signatureVerifier.verify(rawBody, signature);
        InboxResult result = inboxService.storeIfNew(event);

        // NEW: đã lưu bền vững để worker xử lý.
        // DUPLICATE: event đã được ghi nhận, không tạo side effect lần nữa.
        return ResponseEntity.ok().build();
    }
}
```

Service lưu inbox trong transaction:

```java
@Service
public class WebhookInboxService {
    private final JdbcTemplate jdbc;

    public WebhookInboxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public InboxResult storeIfNew(VerifiedWebhook event) {
        int inserted = jdbc.update("""
            INSERT INTO webhook_inbox (
                provider_id, provider_account_id, event_id,
                event_type, payload, payload_sha256, status
            ) VALUES (?, ?, ?, ?, CAST(? AS jsonb), ?, 'RECEIVED')
            ON CONFLICT (provider_id, provider_account_id, event_id)
            DO NOTHING
            """,
            event.providerId(),
            event.accountId(),
            event.eventId(),
            event.eventType(),
            event.rawJson(),
            event.payloadSha256()
        );

        if (inserted == 1) {
            return InboxResult.NEW;
        }

        // Production: đọc fingerprint/status hiện tại để phát hiện
        // cùng event ID nhưng payload khác; không xử lý lại duplicate.
        return InboxResult.DUPLICATE;
    }
}
```

Đây là ví dụ rút gọn cho PostgreSQL/JDBC. Cần triển khai `VerifiedWebhook` chỉ sau khi chữ ký, timestamp, event schema và provider/account binding đã được xác minh. Không tin `providerId`/`accountId` do payload tự khai báo nếu chúng chưa được ràng buộc với endpoint/credential đã xác thực. Nếu transaction insert thất bại, exception phải khiến request không trả `2xx` để provider có thể retry.

Trong thực tế, `storeIfNew` nên trả trạng thái phân biệt `NEW`, `DUPLICATE_SAME_PAYLOAD` và `DUPLICATE_DIFFERENT_PAYLOAD`. Worker cần claim row nguyên tử, cập nhật domain và outbox trong transaction, rồi đánh dấu `PROCESSED`. Không thực hiện HTTP call hoặc gửi email trực tiếp trong transaction database dài.

## 13. Các anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Giả định provider chỉ gửi một lần | Duplicate tạo side effect lặp. | Thiết kế at-least-once và dedupe bền vững. |
| Dedupe bằng payload hash | Hai event hợp lệ có payload giống nhau bị gộp. | Dùng event ID ổn định và scope provider/account. |
| Dùng delivery attempt ID | Mỗi retry có ID mới nên duplicate không bị phát hiện. | Dùng logical event ID theo contract. |
| SELECT rồi INSERT không atomic | Request đồng thời cùng xử lý event. | Unique constraint và insert nguyên tử. |
| Lưu event ID trong memory/cache local | Restart hoặc nhiều instance làm mất dedupe. | Durable shared datastore với retention đủ dài. |
| Trả 2xx trước khi lưu bền vững | Process chết có thể làm mất event vĩnh viễn. | Commit inbox/outbox trước acknowledgement. |
| Chỉ đánh dấu processed sau HTTP call | Crash sau side effect có thể gọi lại side effect. | Downstream idempotency key, outbox và reconciliation. |
| Tin event ID mà không verify signature | Attacker giả mạo event hoặc chiếm khóa dedupe. | Verify signature/timestamp trước khi nhận event. |
| Coi timestamp replay window là dedupe | Retry hợp lệ có timestamp mới vẫn chạy lại. | Tách replay protection và event idempotency. |
| Xóa dedupe record quá sớm | Retry muộn chạy lại nghiệp vụ. | Retention theo provider retry/replay và business audit. |
| Xử lý mọi lỗi bằng retry vô hạn | Retry storm, queue backlog và duplicate side effect. | Phân loại lỗi, retry budget, backoff và DLQ. |
| Giả định event đến đúng thứ tự | Event cũ ghi đè trạng thái mới. | Version/sequence và domain transition checks. |

## 14. Kiểm thử idempotency và redelivery

Kiểm thử cần xác nhận cả trạng thái dữ liệu lẫn side effect. Chỉ kiểm tra response `200` không chứng minh event được xử lý đúng một lần.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Event lần đầu | Gửi event ID mới với signature hợp lệ. | Inbox có một record; event được xử lý theo flow. |
| Duplicate tuần tự | Gửi lại cùng provider/account/event ID và payload. | Trả acknowledgement; không lặp domain update hoặc side effect. |
| Duplicate đồng thời | Gửi cùng event qua nhiều request/instance cùng lúc. | Unique constraint chỉ tạo một record; chỉ một logical processing path. |
| Response bị mất | Handler commit xong nhưng client/provider không nhận response; gửi lại. | Retry được nhận diện duplicate và không xử lý lại. |
| Crash trước commit | Dừng process trước khi transaction commit. | Không có trạng thái nửa chừng; provider retry có thể được xử lý. |
| Crash sau commit trước response | Dừng process sau commit. | Retry được dedupe; event không mất và side effect không lặp. |
| Crash sau downstream success | Downstream đã nhận operation nhưng worker chưa đánh dấu processed. | Retry dùng cùng downstream idempotency key hoặc reconciliation để không lặp. |
| Same ID, different payload | Gửi cùng event ID nhưng payload khác. | Không xử lý âm thầm; tạo alert/incident record. |
| Invalid signature | Thay body/header hoặc dùng secret sai. | Bị từ chối trước khi tạo inbox record. |
| Stale signature timestamp | Gửi signed request ngoài replay window. | Bị từ chối theo policy; không tạo side effect. |
| Out-of-order event | Gửi version cũ sau version mới. | Domain state không bị rollback trái phép. |
| Retention boundary | Gửi lại event gần/cuối thời hạn retention. | Dedupe vẫn hoạt động theo chính sách đã định. |
| Poison event | Event hợp lệ nhưng dữ liệu nghiệp vụ không xử lý được. | Retry có giới hạn rồi DLQ/manual review; không chặn toàn bộ queue. |
| Provider/account collision | Hai account có cùng event ID. | Scope composite key phân biệt đúng hai event. |

Kiểm tra số lần email được gửi, invoice được tạo, payment/refund được gọi, message được phát, row được cập nhật và audit event được ghi. Dùng test với nhiều thread/instance để phát hiện race condition; chạy test crash/retry ở các điểm sau commit và trước acknowledgement.

## 15. Giám sát và xử lý sự cố

Theo dõi các metric và audit field:

- Số event mới, duplicate, duplicate payload mismatch và event bị signature reject.
- Tỷ lệ delivery attempt theo provider/account/event type.
- Inbox backlog, tuổi event lâu nhất, processing latency và retry count.
- Worker lease timeout, lock contention, dead-letter count và queue lag.
- Downstream idempotency conflict, timeout, duplicate operation và reconciliation mismatch.
- Event đến sai thứ tự, version gap hoặc event quá cũ.
- Thay đổi signature key, secret rotation và lỗi xác minh.

Log nên chứa provider/account ID đã xác minh, event ID, event type, trạng thái, attempt/correlation ID, thời điểm nhận/xử lý và lỗi đã chuẩn hóa. Không log webhook secret, access token, signature đầy đủ hoặc payload nhạy cảm. Có thể lưu payload fingerprint để phát hiện cùng ID nhưng nội dung khác.

Khi duplicate tăng bất thường, kiểm tra provider retry policy, endpoint latency, response delivery, network errors và các lỗi transaction. Khi phát hiện event bị xử lý lặp, dừng consumer/side effect liên quan nếu cần, xác định danh sách business operation bị ảnh hưởng, đối soát với provider/downstream và khắc phục dữ liệu bằng quy trình có audit. Không xóa inbox record để “cho chạy lại” nếu chưa xác định tác động; dùng replay có kiểm soát với operation ID và trạng thái rõ ràng.

## 16. Checklist triển khai webhook idempotency

- [ ] Provider contract xác định event ID ổn định qua các lần redelivery?
- [ ] Dedupe key có scope provider/account/endpoint phù hợp và không dùng attempt ID?
- [ ] Chữ ký, timestamp và provider identity được xác minh trước khi tin payload?
- [ ] Replay-window protection được tách khỏi event deduplication?
- [ ] Inbox lưu bền vững trong datastore dùng chung và có unique constraint?
- [ ] Insert/dedupe được thực hiện nguyên tử để chống duplicate đồng thời?
- [ ] Event chỉ được acknowledge sau durable commit hoặc xử lý đồng bộ hoàn tất?
- [ ] Worker có trạng thái, claim/lease và recovery khi process chết?
- [ ] Domain update và inbox status được commit nhất quán?
- [ ] External side effect dùng outbox và downstream idempotency/reconciliation?
- [ ] Event ordering/version và event đến trễ được xử lý theo domain rule?
- [ ] Retention dài hơn retry/replay window và đáp ứng audit requirement?
- [ ] Có retry budget, backoff/jitter, dead-letter và quy trình manual replay?
- [ ] Có test duplicate tuần tự/đồng thời, crash window, signature fail và side effect count?
- [ ] Có metric, alert và runbook cho duplicate spike, backlog, mismatch và reconciliation?

Webhook cần được thiết kế theo giả định event có thể được gửi lại. Event ID ổn định, xác minh chữ ký, unique constraint, durable inbox, transaction và idempotent downstream operation giúp một event tạo đúng tác dụng nghiệp vụ dù có nhiều delivery attempt. Outbox, retry có giới hạn, xử lý ordering và reconciliation hoàn thiện độ tin cậy của toàn bộ luồng; không nên tuyên bố exactly-once chỉ vì handler đã lưu event ID.
