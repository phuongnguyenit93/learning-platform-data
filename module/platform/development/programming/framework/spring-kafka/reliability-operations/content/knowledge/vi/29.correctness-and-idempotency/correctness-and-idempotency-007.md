# Side effect không thể rollback

Trong một hệ thống dùng Spring Kafka, một message có thể khiến ứng dụng thực hiện nhiều hành động: cập nhật đơn hàng trong cơ sở dữ liệu, trừ tiền qua cổng thanh toán, gửi email, tạo vận đơn hoặc gọi API của một dịch vụ khác. Các thay đổi trong cơ sở dữ liệu thường có thể rollback khi transaction thất bại. Nhưng một hành động đã xảy ra bên ngoài transaction thì không tự biến mất chỉ vì ứng dụng rollback.

Đây là vấn đề cốt lõi của **side effect không thể rollback**. Khi xử lý message, hệ thống phải tính đến trường hợp hành động bên ngoài đã thành công nhưng ứng dụng chưa kịp ghi nhận kết quả. Kafka có thể giao lại message, listener có thể chạy lại và một lần retry có thể tạo ra hành động lần thứ hai. Với thao tác như gửi email, phát hành vé, tạo tài khoản hoặc trừ tiền, lần lặp đó có thể gây hậu quả thật.

Mục tiêu của thiết kế không phải là giả định rằng mọi thứ sẽ chỉ chạy một lần. Mục tiêu là bảo đảm mỗi nghiệp vụ có một danh tính ổn định, ghi nhận được trạng thái của hành động, xử lý an toàn khi nhận lại message và có cách đối soát khi kết quả chưa rõ ràng.

## 1. Side effect không thể rollback là gì?

Side effect là một thay đổi do chương trình tạo ra bên ngoài giá trị trả về của hàm. Một số side effect có thể đảo ngược bằng transaction hoặc bằng một thao tác bù. Một số khác đã xảy ra thì không thể thu hồi hoàn toàn.

| Hành động | Có thể rollback trực tiếp? | Vấn đề khi chạy lặp |
|---|---|---|
| Cập nhật một bản ghi trong cùng DB transaction | Có, trước khi commit | Thường được DB bảo vệ trong transaction |
| Gửi email cho khách hàng | Không | Khách hàng có thể nhận nhiều email |
| Gửi SMS hoặc push notification | Không bảo đảm | Tin nhắn đã gửi có thể không thu hồi được |
| Trừ tiền qua payment provider | Không theo nghĩa DB rollback | Khách hàng có thể bị trừ tiền hai lần |
| Tạo vận đơn với hãng vận chuyển | Thường không | Có thể tạo nhiều mã vận đơn hoặc nhiều lần lấy hàng |
| Cấp quyền hoặc tạo tài khoản ở hệ thống ngoài | Tùy API | Có thể tạo tài nguyên trùng lặp hoặc quyền sai |
| Ghi một event vào Kafka | Không xóa được lịch sử đã đọc một cách tổng quát | Consumer có thể đã xử lý event trước khi event bị bù |

Một số API cung cấp thao tác hủy, hoàn tiền hoặc thu hồi. Những thao tác đó thường là **hành động mới**, có quy tắc và kết quả riêng. Chúng không làm cho hành động ban đầu chưa từng xảy ra. Ví dụ, hoàn tiền là một giao dịch tài chính mới; nó không phải rollback của lần trừ tiền trước đó.

## 2. Vì sao retry tạo ra rủi ro?

Giả sử consumer nhận event `OrderApproved` và gọi API để trừ tiền. Trình tự có thể diễn ra như sau:

1. Kafka giao event cho consumer.
2. Consumer gọi payment provider.
3. Provider đã trừ tiền thành công.
4. Kết nối bị timeout hoặc tiến trình consumer bị dừng trước khi ghi nhận kết quả.
5. Offset chưa được commit, hoặc một cơ chế retry phát lại event.
6. Consumer nhận lại event và gọi API trừ tiền lần nữa.

Từ góc nhìn của ứng dụng, lần gọi đầu tiên có thể chỉ hiện ra dưới dạng timeout. Nhưng timeout chỉ nói rằng ứng dụng không nhận được phản hồi trong thời gian chờ; nó **không chứng minh** rằng provider chưa thực hiện hành động.

Đây là tình huống *kết quả không xác định* (unknown outcome). Nếu ứng dụng coi mọi timeout là thất bại chắc chắn rồi gửi lại một yêu cầu mới, nó có thể tạo side effect trùng lặp. Nếu ứng dụng không bao giờ gửi lại, nó có thể bỏ sót một nghiệp vụ mà provider thực sự chưa thực hiện.

Vì vậy, cần phân biệt ba trường hợp:

- **Thành công đã xác nhận:** nhận được kết quả thành công và đã lưu kết quả đó.
- **Thất bại đã xác nhận:** provider trả về một kết quả cho biết hành động không được thực hiện, chẳng hạn giao dịch bị từ chối.
- **Chưa xác định:** timeout, mất kết nối, tiến trình dừng hoặc lỗi xảy ra ở khoảng giữa lúc gửi yêu cầu và lúc lưu kết quả. Trạng thái này cần đối soát hoặc retry có kiểm soát.

Không nên gộp trường hợp thứ ba vào trạng thái thất bại thông thường.

## 3. Ranh giới bảo đảm của Kafka transaction

Kafka hỗ trợ producer transaction và cơ chế exactly-once semantics cho một số luồng xử lý nằm trong Kafka. Ví dụ, một consumer có thể đọc record, tạo record mới và commit offset trong cùng Kafka transaction. Consumer đọc với `isolation.level=read_committed` sẽ không nhìn thấy các record thuộc transaction đã abort.

Phạm vi này rất hữu ích cho luồng **Kafka-to-Kafka**. Tuy nhiên, Kafka transaction không tự bao bọc một HTTP request, email, SMS hoặc transaction của một cơ sở dữ liệu quan hệ. Nếu listener gọi payment provider rồi Kafka transaction abort, provider không nhận được lệnh rollback từ Kafka.

Tương tự, commit một DB transaction và commit Kafka offset là hai thao tác ở hai hệ thống khác nhau nếu ứng dụng không triển khai một cơ chế phối hợp phân tán phù hợp. Có thể xảy ra tình huống DB đã commit nhưng offset chưa commit. Kafka giao lại event và listener chạy lần nữa. Vì thế, consumer vẫn cần xử lý duplicate an toàn.

Hãy xác định rõ loại bảo đảm đang cần:

| Bảo đảm | Ý nghĩa | Có giải quyết side effect bên ngoài không? |
|---|---|---|
| At-most-once | Một message có thể bị bỏ qua, nhưng không chủ động xử lý lại sau khi đã xác nhận | Không; có thể mất hành động |
| At-least-once | Message được giao lại cho đến khi được xác nhận theo cấu hình | Không; hành động có thể chạy nhiều lần |
| Exactly-once trong Kafka | Các thao tác đọc, ghi và offset thuộc phạm vi Kafka transaction được phối hợp | Không tự mở rộng sang HTTP, email hoặc DB ngoài Kafka |
| Effectively-once ở tầng nghiệp vụ | Nhiều lần giao hoặc gọi lại vẫn tạo ra một kết quả nghiệp vụ duy nhất | Có thể đạt được nếu có idempotency, lưu trạng thái và đối soát phù hợp |

Trong hệ thống có side effect bên ngoài, cách tiếp cận thực tế thường là **at-least-once delivery kết hợp idempotent processing**. Kafka có thể giao lại; ứng dụng bảo đảm việc xử lý lại không tạo ra kết quả nghiệp vụ thứ hai.

## 4. Bắt đầu bằng một danh tính nghiệp vụ ổn định

Mỗi side effect cần có một khóa idempotency đại diện cho **một hành động nghiệp vụ cụ thể**. Khóa phải giống nhau khi cùng một nghiệp vụ được thử lại, kể cả khi message được phát lại hoặc đi qua retry topic.

Ví dụ, nếu một đơn hàng chỉ được phép thu tiền một lần cho một lần thanh toán, khóa có thể là:

```text
order:ORD-8421:charge:payment-attempt-1
```

Nếu nghiệp vụ cho phép khách hàng thử thanh toán lại sau khi lần trước bị từ chối, mỗi lần thử hợp lệ phải có định danh riêng, chẳng hạn `payment-attempt-2`. Không dùng một khóa chung cho mọi lần thử vì điều đó có thể khiến một lần thanh toán mới bị nhầm thành lần cũ.

Một số lựa chọn thường gặp:

- `eventId` ổn định do producer tạo: phù hợp khi một event chỉ đại diện cho một side effect.
- ID nghiệp vụ cộng với loại hành động: ví dụ `orderId + effectType`, phù hợp khi một event có thể dẫn đến nhiều loại hành động.
- ID của lần thực hiện nghiệp vụ: phù hợp khi cùng một đơn hàng có nhiều lần thanh toán, gửi hàng hoặc hoàn tiền hợp lệ.

Không nên dùng Kafka offset làm khóa idempotency cho side effect. Offset chỉ có ý nghĩa trong một partition cụ thể; cùng một event khi được phát lại, sao chép hoặc đưa qua retry topic có thể có offset khác. Khóa idempotency phải theo nghiệp vụ, không phụ thuộc vị trí hiện tại của record trong Kafka.

Nếu provider hỗ trợ idempotency key, hãy gửi cùng một khóa trong mọi lần thử của cùng hành động. Provider thường lưu kết quả theo khóa và trả lại kết quả cũ khi nhận lại yêu cầu tương đương. Cần đọc kỹ hợp đồng API: thời gian lưu khóa, phạm vi duy nhất, cách xử lý payload khác nhau và loại lỗi nào được phép retry có thể khác nhau giữa các provider.

Một nguyên tắc quan trọng là **cùng một khóa phải luôn đại diện cho cùng một nội dung yêu cầu**. Nên lưu thêm hash của payload. Nếu một request mới dùng lại khóa cũ nhưng số tiền, loại tiền hoặc người nhận đã thay đổi, hệ thống phải phát hiện xung đột thay vì âm thầm coi đó là retry hợp lệ.

## 5. Ghi nhận ý định trước khi gọi hệ thống bên ngoài

Không nên đặt một HTTP call không thể rollback ở giữa một DB transaction dài rồi kỳ vọng DB rollback sẽ hoàn tác HTTP call. Thay vào đó, hãy ghi nhận rằng hệ thống cần thực hiện hành động, commit ý định đó, rồi để một worker thực hiện side effect ở bước riêng.

Một bảng theo dõi side effect có thể lưu các thông tin sau:

| Trường | Mục đích |
|---|---|
| `effect_key` | Khóa idempotency ổn định, có unique constraint |
| `event_id` | Liên kết với event nguồn |
| `effect_type` | Loại hành động, ví dụ `CHARGE_PAYMENT` |
| `request_hash` | Phát hiện cùng khóa nhưng payload khác nhau |
| `request_payload` | Nội dung cần gửi lại hoặc dữ liệu tham chiếu để tái tạo request |
| `status` | Trạng thái hiện tại của hành động |
| `provider_reference` | Mã giao dịch hoặc tài nguyên do provider trả về |
| `response_payload` | Kết quả cần lưu để xử lý hoặc đối soát |
| `attempt_count` | Số lần thử đã thực hiện |
| `next_attempt_at` | Thời điểm sớm nhất được phép thử tiếp |
| `lease_until` | Thời điểm hết hạn quyền xử lý của worker đang giữ việc |
| `last_error` | Lỗi gần nhất để điều tra |

Ví dụ schema rút gọn cho PostgreSQL:

```sql
CREATE TABLE external_effect (
    effect_key         varchar(200) PRIMARY KEY,
    event_id           varchar(100) NOT NULL,
    effect_type        varchar(80) NOT NULL,
    request_hash       varchar(128) NOT NULL,
    request_payload   jsonb NOT NULL,
    status             varchar(24) NOT NULL,
    provider_reference varchar(200),
    response_payload   jsonb,
    attempt_count      integer NOT NULL DEFAULT 0,
    next_attempt_at    timestamptz,
    lease_until        timestamptz,
    last_error         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_external_effect_pending
    ON external_effect (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRYABLE');
```

`effect_key` là khóa duy nhất để ngăn hai luồng tạo hai bản ghi cho cùng hành động. Trong hệ thống nhiều provider, có thể đưa tên provider vào khóa hoặc tạo unique constraint theo cặp `(provider, effect_key)`, tùy phạm vi duy nhất mà provider quy định.

### 5.1. Lưu inbox và ý định side effect trong cùng DB transaction

Khi listener nhận event, nó có thể thực hiện hai việc trong một transaction của DB:

1. Ghi nhận `eventId` vào bảng inbox để phát hiện event đã xử lý.
2. Tạo bản ghi `external_effect` ở trạng thái `PENDING` nếu hành động đó chưa tồn tại.

Ví dụ bảng inbox:

```sql
CREATE TABLE consumer_inbox (
    consumer_name varchar(100) NOT NULL,
    event_id      varchar(100) NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Listener có thể gọi một service Spring được quản lý bởi DB transaction:

```java
@Service
public class OrderApprovedHandler {
    private final JdbcTemplate jdbc;

    public OrderApprovedHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void recordIntent(OrderApproved event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "billing", event.eventId());

        if (inserted == 0) {
            // Event này đã được consumer ghi nhận trước đó.
            return;
        }

        String effectKey = "order:" + event.orderId()
            + ":charge:" + event.paymentAttemptId();

        jdbc.update("""
            INSERT INTO external_effect (
                effect_key, event_id, effect_type, request_hash,
                request_payload, status
            ) VALUES (?, ?, 'CHARGE_PAYMENT', ?, CAST(? AS jsonb), 'PENDING')
            ON CONFLICT (effect_key) DO NOTHING
            """,
            effectKey,
            event.eventId(),
            event.paymentRequestHash(),
            event.paymentRequestJson());
    }
}
```

Listener chỉ ghi nhận ý định trong DB:

```java
@KafkaListener(topics = "order-approved", groupId = "billing")
public void onOrderApproved(OrderApproved event) {
    orderApprovedHandler.recordIntent(event);
}
```

Khi `recordIntent` trả về, proxy transaction của Spring hoàn tất DB transaction trước khi lời gọi service trả lại cho listener. Sau đó listener mới trả về cho container để container xử lý việc xác nhận offset theo cấu hình. Nếu DB transaction thất bại, listener ném lỗi và message có thể được xử lý lại. Nếu DB đã commit nhưng offset chưa commit và event được giao lại, khóa inbox ngăn tạo ý định lần thứ hai.

Điều kiện quan trọng: việc ghi inbox và tạo ý định side effect phải nằm trong **cùng một DB transaction**. Nếu ghi inbox commit trước, sau đó tạo ý định thất bại, lần giao lại có thể bị coi là duplicate và hành động sẽ bị mất. Nếu tạo ý định commit trước nhưng inbox không được ghi, lần giao lại vẫn có thể an toàn nhờ unique constraint trên `effect_key`, nhưng trạng thái dữ liệu sẽ khó giải thích hơn.

Ví dụ trên minh họa phần cốt lõi. Trong code thực tế, cần kiểm tra kết quả insert và payload khi `effect_key` đã tồn tại. Nếu khóa đã có nhưng `request_hash` khác, phải ghi nhận lỗi xung đột nghiệp vụ và xử lý rõ ràng; không nên bỏ qua khác biệt đó.

## 6. Thực hiện side effect bằng worker có trạng thái

Một worker riêng đọc các bản ghi `PENDING` hoặc `RETRYABLE`, giữ quyền xử lý trong một khoảng thời gian, gọi provider và lưu kết quả. Việc claim bản ghi cần an toàn khi có nhiều worker chạy đồng thời. Với PostgreSQL, một cách triển khai phổ biến là transaction ngắn dùng `SELECT ... FOR UPDATE SKIP LOCKED`, cập nhật `IN_PROGRESS` cùng `lease_until`, rồi commit trước khi gọi mạng.

Trình tự nên là:

1. Claim một bản ghi và đặt lease trong DB transaction ngắn.
2. Commit transaction claim để worker khác không lấy cùng công việc.
3. Gọi provider bên ngoài DB transaction, gửi `effect_key` làm idempotency key.
4. Nếu thành công, lưu `SUCCEEDED`, mã tham chiếu và response.
5. Nếu provider xác nhận không thực hiện hành động và lỗi có thể thử lại, lưu `RETRYABLE` cùng `next_attempt_at`.
6. Nếu provider từ chối dứt điểm, lưu `FAILED_FINAL`.
7. Nếu timeout hoặc mất kết nối khiến kết quả chưa rõ, lưu `UNKNOWN` và chuyển sang bước đối soát.

Không giữ row lock hoặc DB transaction mở trong lúc chờ HTTP response. Một request bên ngoài có thể mất nhiều giây hoặc treo đến timeout; giữ transaction trong suốt thời gian đó làm tăng thời gian giữ lock, tranh chấp kết nối và nguy cơ nghẽn DB.

Ví dụ luồng xử lý ở mức khái niệm:

```java
public void dispatch(ExternalEffect effect) {
    try {
        ChargeResult result = paymentClient.charge(
            effect.requestPayload(),
            effect.effectKey() // cùng khóa cho mọi lần thử của hành động này
        );

        effectRepository.markSucceeded(
            effect.effectKey(), result.providerReference(), result.toJson());
    } catch (DefinitivePaymentDecline ex) {
        effectRepository.markFailedFinal(effect.effectKey(), ex.getMessage());
    } catch (TimeoutException | ConnectionException ex) {
        effectRepository.markUnknown(effect.effectKey(), ex.getMessage());
    }
}
```

Đây là ví dụ mô tả ranh giới xử lý; cách phân loại exception phải dựa trên hợp đồng cụ thể của payment client. Không phải mọi `4xx` đều là thất bại cuối cùng và không phải mọi `5xx` đều chứng minh provider chưa thực hiện hành động. Cần biết provider có thể đã xử lý request trước khi trả lỗi hay không.

### 6.1. Một state machine hữu ích

Các trạng thái nên phản ánh điều mà hệ thống thực sự biết:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| `PENDING` | Ý định đã được lưu, chưa có worker thực hiện | Claim để xử lý |
| `IN_PROGRESS` | Một worker đang giữ lease và thực hiện hành động | Chờ kết quả hoặc lease hết hạn |
| `SUCCEEDED` | Provider xác nhận thành công và kết quả đã được lưu | Không thực hiện lại; chỉ đọc kết quả |
| `RETRYABLE` | Đã xác định an toàn để thử lại sau | Retry theo lịch và cùng idempotency key |
| `UNKNOWN` | Có thể provider đã thực hiện nhưng ứng dụng chưa biết kết quả | Đối soát trước khi quyết định |
| `FAILED_FINAL` | Provider xác nhận hành động không thể hoặc không nên thử lại | Chuyển xử lý nghiệp vụ hoặc vận hành |
| `RECONCILING` | Đang truy vấn provider hoặc đối chiếu dữ liệu | Cập nhật thành công, thất bại hoặc tiếp tục chờ |

Một worker có thể chết sau khi provider đã hoàn thành nhưng trước khi cập nhật `SUCCEEDED`. Khi lease hết hạn, bản ghi cũ không nên tự động quay về `PENDING` rồi gửi một request mới với khóa mới. Hãy chuyển nó sang quy trình xử lý trạng thái không xác định. Nếu provider hỗ trợ idempotency key đúng cách, worker có thể gửi lại cùng request và cùng khóa; nếu provider hỗ trợ truy vấn theo mã tham chiếu hoặc khóa nghiệp vụ, hãy truy vấn kết quả trước.

Lease giúp phục hồi công việc bị bỏ dở, nhưng lease không tự bảo đảm không có hai worker cùng gọi provider. Một worker cũ có thể bị treo lâu hơn lease rồi hoạt động trở lại trong khi worker mới đã claim bản ghi. Cần kết hợp lease với cơ chế fencing/version nếu cần ngăn worker cũ ghi đè trạng thái mới, và với idempotency key ở provider để bảo vệ side effect bên ngoài.

## 7. Inbox, Outbox và Effect Ledger giải quyết các phần khác nhau

Ba mẫu thiết kế thường đi cùng nhau nhưng có nhiệm vụ riêng:

| Mẫu | Giải quyết vấn đề | Không tự giải quyết |
|---|---|---|
| Transactional Outbox | DB commit nhưng event cần publish lên Kafka có thể bị mất hoặc publish lệch trạng thái | Duplicate ở consumer và side effect ngoài Kafka |
| Inbox / Idempotent Consumer | Một event có thể được giao nhiều lần nhưng thay đổi DB chỉ được áp dụng một lần | API ngoài đã thực hiện hay chưa |
| Effect Ledger | Theo dõi từng side effect, idempotency key, kết quả và trạng thái chưa xác định | Không thể ép provider không hỗ trợ idempotency trở nên exactly-once |

### 7.1. Transactional Outbox

Khi một nghiệp vụ cập nhật DB và cần phát event Kafka, ghi thay đổi nghiệp vụ và một dòng outbox trong cùng DB transaction. Một publisher đọc outbox rồi gửi event lên Kafka. Sau khi publish thành công, publisher đánh dấu dòng outbox đã gửi.

Publisher có thể chết sau khi Kafka đã nhận event nhưng trước khi DB ghi `published`. Khi chạy lại, publisher gửi event thêm lần nữa. Vì vậy, event outbox cần có ID ổn định và consumer vẫn phải idempotent.

Outbox bảo đảm ý định phát event được lưu bền vững cùng thay đổi DB. Nó không biến một API thanh toán hoặc email thành một phần của Kafka transaction.

### 7.2. Inbox / Idempotent Consumer

Consumer ghi `consumerName + eventId` với unique constraint trong cùng transaction với thay đổi DB do event gây ra. Nếu insert không tạo dòng mới, event đã được xử lý và consumer có thể kết thúc an toàn.

Unique constraint là lớp bảo vệ quan trọng khi có nhiều instance cùng xử lý hoặc khi hai lần giao message xảy ra gần như đồng thời. Kiểm tra duplicate bằng một câu `SELECT` rồi mới `INSERT` mà không có constraint có thể gặp race condition: hai instance cùng thấy chưa có bản ghi và cùng thực hiện nghiệp vụ.

### 7.3. Effect Ledger

Inbox chỉ cho biết consumer đã ghi nhận event. Nó không đủ để trả lời câu hỏi “provider đã trừ tiền chưa?”. Effect ledger theo dõi riêng từng hành động bên ngoài và kết quả của nó. Một event có thể tạo nhiều effect record, ví dụ tạo vận đơn và gửi thông báo, mỗi effect có khóa và trạng thái riêng.

Kết hợp ba mẫu này giúp tách rõ: dữ liệu nghiệp vụ đã commit chưa, event đã được phát chưa, consumer đã ghi nhận event chưa và side effect bên ngoài đã có kết quả gì.

## 8. Retry phải dựa trên loại lỗi và trạng thái side effect

Retry là cơ chế phục hồi, không phải bằng chứng rằng lần gọi trước chưa xảy ra. Trước khi retry, hãy xác định lỗi thuộc nhóm nào:

| Loại tình huống | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Chắc chắn chưa gửi request | Validation thất bại trước khi mở kết nối | Sửa dữ liệu hoặc đánh dấu lỗi cuối cùng |
| Provider từ chối rõ ràng, không tạo side effect | Số dư không đủ và hợp đồng API xác nhận không có giao dịch | Có thể retry khi điều kiện thay đổi, theo nghiệp vụ |
| Lỗi tạm thời nhưng provider xác nhận request chưa được xử lý | Rate limit có hợp đồng retry rõ ràng | Backoff và retry cùng khóa |
| Timeout sau khi gửi request | Không nhận được response | Đánh dấu `UNKNOWN`, truy vấn hoặc retry có idempotency key |
| Provider thành công nhưng ghi DB thất bại | Tiến trình dừng sau khi nhận response | Đối soát hoặc gọi lại cùng khóa để lấy kết quả cũ |
| Payload sai hoặc vi phạm quy tắc nghiệp vụ | Số tiền, người nhận hoặc trạng thái không hợp lệ | Không retry mù quáng; chuyển xử lý lỗi |

Áp dụng exponential backoff, jitter và giới hạn số lần thử để tránh tạo đợt tải tăng đột biến lên provider. Tôn trọng `Retry-After` nếu API trả về và hợp đồng cho phép. Lưu thời điểm thử tiếp theo thay vì giữ thread ngủ trong lúc chờ.

Trong Spring Kafka, retry topic, retry interceptor hoặc dead-letter topic có thể giúp quản lý việc giao lại message. Nhưng chúng không thay thế idempotency. Một listener được gọi lại vẫn có thể gọi API lần nữa. Khi đưa event vào DLT, hãy giữ nguyên `eventId`, `effectKey` và thông tin tương quan để có thể điều tra, đối soát và phát lại an toàn.

Không nên tự động replay DLT cho một side effect có trạng thái `UNKNOWN` nếu chưa biết provider đã thực hiện hành động hay chưa. Hãy tra cứu effect ledger và provider trước khi quyết định.

## 9. Khi provider không hỗ trợ idempotency

Đây là trường hợp khó nhất. Giả sử ứng dụng gửi lệnh tạo vận đơn. Kết nối timeout sau khi gửi. API không nhận idempotency key và cũng không có endpoint tra cứu theo mã yêu cầu của ứng dụng. Ứng dụng không thể biết chắc vận đơn đã được tạo hay chưa.

Trong tình huống đó, không có cách retry nào bảo đảm tuyệt đối đồng thời tránh cả hai rủi ro:

- Gửi lại có thể tạo vận đơn thứ hai.
- Không gửi lại có thể khiến vận đơn chưa từng được tạo.

Hãy giảm vùng không chắc chắn bằng các biện pháp sau:

1. **Dùng mã tham chiếu do ứng dụng tạo:** gửi `merchantReference` hoặc một business key nếu API có hỗ trợ, rồi tra cứu theo mã đó.
2. **Tra cứu trước khi gửi lại:** nếu provider có API tìm theo đơn hàng, người nhận hoặc mã tham chiếu, hãy kiểm tra kết quả trước.
3. **Lưu request và correlation ID:** giữ lại payload, thời điểm, mã tương quan và response thô để hỗ trợ đối soát.
4. **Tạo hàng đợi reconciliation:** các bản ghi `UNKNOWN` cần được kiểm tra định kỳ hoặc chuyển cho nhân viên vận hành.
5. **Giới hạn retry tự động:** không lặp vô hạn một hành động có khả năng tạo hậu quả không thể thu hồi.
6. **Thiết kế thao tác bù:** nếu nghiệp vụ cho phép, chuẩn bị quy trình hủy, hoàn tiền hoặc thu hồi riêng, đồng thời ghi nhận rằng thao tác bù cũng có thể thất bại.

Nếu provider không hỗ trợ idempotency, không có khóa tra cứu và không cung cấp cơ chế đối soát, hệ thống phải công khai giới hạn bảo đảm đó trong thiết kế. Không nên tuyên bố exactly-once cho side effect này.

## 10. Compensation là hành động mới, không phải rollback

Trong một quy trình nhiều bước, có thể xảy ra trường hợp bước đầu đã hoàn thành nhưng bước sau thất bại. Ví dụ:

1. Thanh toán thành công.
2. Tạo vận đơn thất bại.
3. Nghiệp vụ quyết định hoàn tiền.

Hoàn tiền là một bước bù (compensation) trong Saga. Nó có ID, trạng thái, retry policy và khả năng thất bại riêng. Không xóa bản ghi thanh toán như thể giao dịch chưa từng xảy ra. Cần giữ lịch sử cả lần charge và lần refund để kiểm toán và đối soát.

Một Saga thường mô tả các bước nghiệp vụ và hành động bù tương ứng:

```text
Đơn hàng được xác nhận
        |
        v
Thu tiền ----------------------> Charge thành công
        |                              |
        | thất bại                     v
        |                        Tạo vận đơn
        |                              |
        |                              | thất bại
        |                              v
        |                         Yêu cầu hoàn tiền
        |                              |
        v                              v
  Chờ xử lý lỗi                  Theo dõi refund
```

Saga không tạo ra một transaction ACID duy nhất xuyên qua nhiều dịch vụ. Nó quản lý một chuỗi transaction cục bộ và các hành động bù. Vì mỗi bước có thể thất bại hoặc bị giao lại, từng bước và từng compensation đều cần idempotency.

Không phải side effect nào cũng có compensation hoàn hảo. Một email đã đọc không thể “thu hồi” khỏi trí nhớ người nhận. Một SMS có thể đã được chuyển tới thiết bị. Với những hành động này, thiết kế tốt thường tập trung vào việc hạn chế gửi trùng, lưu lịch sử, sửa sai bằng thông báo tiếp theo khi cần và có quy trình hỗ trợ rõ ràng.

## 11. Các điểm cần chú ý khi triển khai với Spring Kafka

### 11.1. Để DB commit trước khi listener hoàn tất

Nếu listener ghi inbox và effect intent bằng DB transaction, hãy bảo đảm DB transaction hoàn tất thành công trước khi listener trả về bình thường. Khi container chỉ xác nhận offset sau khi listener thành công, DB commit trước rồi offset commit thất bại vẫn có thể dẫn đến redelivery; inbox và unique constraint giúp lần giao lại an toàn.

Không ack message trước khi dữ liệu cần thiết đã commit. Nếu ack trước rồi DB rollback, Kafka có thể không giao lại event và ý định nghiệp vụ sẽ bị mất.

### 11.2. Không nhầm Kafka transaction với transaction của DB

`KafkaTransactionManager` quản lý Kafka transaction. `JpaTransactionManager` hoặc `DataSourceTransactionManager` quản lý transaction của DB tương ứng. Việc có cả hai manager trong ứng dụng không tự động làm cho HTTP request, DB và Kafka cùng commit hoặc rollback như một transaction phân tán.

Nếu dùng Kafka transaction cho luồng consume-transform-produce, hãy giữ side effect ngoài Kafka trong một quy trình có trạng thái riêng. Với luồng DB-to-Kafka, cân nhắc Transactional Outbox để lưu thay đổi DB và ý định phát event trong cùng DB transaction.

### 11.3. Retry topic và DLT cần giữ danh tính nghiệp vụ

Khi một event được chuyển qua retry topic hoặc DLT, header và metadata có thể thay đổi. Hãy giữ `eventId` trong payload hoặc một trường metadata được kiểm soát, và giữ nguyên `effectKey` qua mọi lần thử. Không tạo khóa mới chỉ vì message được chuyển sang topic khác.

### 11.4. Concurrency cần được bảo vệ ở DB

Kafka consumer group phân phối partition giữa các consumer, nhưng không phải là khóa duy nhất cho mọi side effect. Rebalance, retry topic, nhiều luồng xử lý hoặc một luồng phát lại thủ công có thể khiến cùng một nghiệp vụ xuất hiện ở nhiều nơi. Dùng unique constraint, transaction và cơ chế claim có kiểm soát để bảo vệ dữ liệu.

### 11.5. Không giữ transaction mở khi gọi API chậm

Tách thao tác claim, gọi provider và cập nhật kết quả thành các bước có transaction ngắn. Cách này giảm thời gian giữ connection và lock, đồng thời làm rõ trạng thái nếu tiến trình dừng giữa các bước.

### 11.6. Quan sát được trạng thái nghiệp vụ

Log và metric nên mang theo `eventId`, `effectKey`, loại side effect, provider reference và attempt number. Tránh ghi thông tin nhạy cảm như số thẻ hoặc token vào log. Các metric hữu ích gồm số effect đang `PENDING`, `IN_PROGRESS` quá lease, `UNKNOWN`, `RETRYABLE`, `FAILED_FINAL`, thời gian xử lý và tỷ lệ reconciliation thành công.

Một cảnh báo cho số lượng hoặc tuổi của bản ghi `UNKNOWN` thường có giá trị hơn cảnh báo đơn thuần rằng listener có exception. Exception cho biết code gặp lỗi; `UNKNOWN` cho biết một hành động bên ngoài có thể đã xảy ra nhưng hệ thống chưa xác nhận được.

## 12. Checklist thiết kế cho một side effect

Trước khi đưa một hành động bên ngoài vào consumer, hãy trả lời các câu hỏi sau:

- Hành động nào được xem là một lần thực hiện nghiệp vụ duy nhất?
- Khóa idempotency được tạo từ dữ liệu nào và có ổn định qua retry, replay, rebalance không?
- Provider có hỗ trợ idempotency key không? Khóa được lưu trong bao lâu và payload phải khớp như thế nào?
- Nếu timeout sau khi gửi request, hệ thống tra cứu kết quả bằng cách nào?
- Ý định side effect được lưu bền vững ở đâu và có unique constraint nào bảo vệ?
- Inbox record và effect intent có được commit trong cùng DB transaction không?
- Worker claim công việc thế nào để tránh nhiều instance cùng xử lý?
- Nếu worker chết sau khi provider thành công nhưng trước khi ghi DB, hệ thống phục hồi ra sao?
- Trạng thái `UNKNOWN` được đối soát bởi ai hoặc thành phần nào?
- Retry có backoff, jitter, giới hạn và phân loại lỗi không?
- DLT có giữ event ID, effect key và dữ liệu cần để điều tra không?
- Nếu cần compensation, hành động bù có ID, trạng thái và idempotency riêng chưa?
- Metric và cảnh báo nào giúp phát hiện side effect bị treo hoặc chưa xác định?

## 13. Ví dụ hoàn chỉnh: consumer tạo yêu cầu thu tiền

Giả sử dịch vụ Order phát `OrderApproved` với `eventId`, `orderId`, `paymentAttemptId`, số tiền và loại tiền. Dịch vụ Billing phải yêu cầu payment provider thu tiền.

**Bước 1 — Consumer ghi nhận event.** Listener gọi `recordIntent`. Trong một DB transaction, service insert `(billing, eventId)` vào inbox và insert effect với khóa `order:{orderId}:charge:{paymentAttemptId}` ở trạng thái `PENDING`. Nếu event được giao lại, inbox unique key chặn xử lý lặp. Nếu hai event khác nhau cùng đại diện cho một lần thu tiền, unique `effect_key` vẫn ngăn tạo hai effect.

**Bước 2 — Worker claim effect.** Worker lấy một effect `PENDING`, cập nhật `IN_PROGRESS`, tăng `attempt_count` và đặt `lease_until` trong transaction ngắn. Sau commit, worker mới gọi provider.

**Bước 3 — Gọi provider.** Worker gửi payload và `effect_key` làm idempotency key. Nếu lần gọi trước đã thành công nhưng response bị mất, lần gọi lại cùng khóa phải được provider xử lý theo hợp đồng idempotency, thường bằng cách trả lại kết quả của lần đầu thay vì tạo lần thu tiền mới.

**Bước 4 — Ghi kết quả.** Khi nhận được kết quả thành công, worker lưu `SUCCEEDED` cùng provider reference. Các lần giao lại event sau đó không tạo effect mới; các lần chạy dispatcher cũng bỏ qua effect đã thành công.

**Bước 5 — Đối soát khi kết quả không rõ.** Nếu timeout, worker lưu `UNKNOWN`. Một reconciliation job truy vấn provider theo idempotency key hoặc provider reference. Nếu tìm thấy giao dịch, nó cập nhật `SUCCEEDED`; nếu provider xác nhận không có giao dịch, nó có thể đưa effect về `RETRYABLE` theo chính sách; nếu vẫn không xác định, giữ trạng thái chờ hoặc chuyển xử lý thủ công.

Luồng này không ngăn mọi lỗi mạng hay mọi lần giao lại. Nó làm cho mỗi lần giao lại có thể được xử lý an toàn, đồng thời giữ lại đủ thông tin để phục hồi khi ứng dụng không biết provider đã làm gì.

## Kết luận

Với side effect không thể rollback, ranh giới quan trọng nằm giữa transaction nội bộ và hành động đã xảy ra ở hệ thống bên ngoài. Kafka có thể giao message nhiều lần; DB có thể commit trong khi offset chưa commit; provider có thể thành công dù ứng dụng chỉ nhìn thấy timeout.

Thiết kế bền vững cần một khóa idempotency theo nghiệp vụ, inbox để nhận diện event trùng, effect ledger để theo dõi từng hành động, worker có trạng thái và lease, retry theo loại lỗi, cùng quy trình reconciliation cho kết quả chưa xác định. Nếu quy trình gồm nhiều dịch vụ, compensation cần được xem là hành động nghiệp vụ mới với trạng thái và idempotency riêng.

Khi provider không hỗ trợ idempotency hoặc tra cứu kết quả, phải thừa nhận giới hạn bảo đảm và thiết kế quy trình đối soát phù hợp. Không có Kafka transaction nào có thể tự rollback một email đã gửi hoặc một khoản tiền đã được provider thu. Hệ thống đạt độ tin cậy bằng cách quản lý rõ điều đã biết, điều chưa biết và cách tiếp tục xử lý an toàn.
