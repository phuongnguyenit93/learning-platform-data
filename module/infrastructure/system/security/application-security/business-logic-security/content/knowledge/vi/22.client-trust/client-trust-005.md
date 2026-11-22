# Untrusted client timestamps — Không cấp quyền bằng thời gian do client tự khai

## 1. Timestamp đúng định dạng chưa phải bằng chứng về thời gian

Một request có thể chứa `createdAt`, `submittedAt`, `expiresAt` hoặc `clientTime` với định dạng hoàn toàn hợp lệ. Điều đó không chứng minh hành động thật sự diễn ra ở thời điểm ấy, cũng không chứng minh một quyền vẫn còn hiệu lực.

Người gọi có thể sửa đồng hồ thiết bị, thay payload, phát lại request cũ hoặc gửi trực tiếp HTTP. Nếu server dùng timestamp đó để quyết định còn hạn phê duyệt, còn giá ưu đãi hoặc còn được tính vào một kỳ hạn mức, client đang tự chọn điều kiện cấp quyền cho mình.

Bất biến quan trọng là:

```text
Thời gian client tự khai không được tự quyết định quyền nghiệp vụ
phải dựa trên một thời điểm hoặc deadline có thẩm quyền.
```

Bài học dùng việc chấp nhận báo giá làm ví dụ. Nó cũng áp dụng cho phê duyệt, hạn thanh toán, reservation, mã ưu đãi, quota, command bất đồng bộ và dữ liệu khai báo được gửi từ thiết bị ngoại tuyến.

## 2. Phân biệt các loại thời gian trước khi kiểm tra

| Loại thời gian | Ý nghĩa | Có thể dùng trực tiếp làm quyền không? |
| --- | --- | --- |
| Thời gian client khai báo | Điều người gửi nói về đồng hồ hoặc sự kiện | Không, trừ khi có một giao thức tin cậy bổ sung phù hợp |
| Thời gian server nhận | Mốc do một thành phần server được tin cậy ghi nhận | Chỉ khi hợp đồng nghiệp vụ chọn đúng mốc nhận đó |
| Thời gian gate | Mốc server kiểm tra và nhận quyền thực hiện action | Có thể, theo chính sách được định nghĩa |
| Deadline do server phát hành | Giới hạn được server hoặc nguồn có thẩm quyền xác lập | Cần kiểm tra nguồn, phạm vi và trạng thái hiện tại |
| Thời gian bên ngoài báo cáo | Một nhà cung cấp nói về sự kiện thuộc trách nhiệm của họ | Cần xác thực nguồn, ngữ nghĩa sự kiện và quan hệ command |
| Ngày nghiệp vụ do người dùng chọn | Dữ liệu của hồ sơ, chẳng hạn ngày sử dụng dịch vụ | Là một khai báo cần validation, không tự thay đồng hồ cấp quyền |

Tên field không quyết định mức tin cậy. Một field tên `serverReceivedAt` nằm trong body do người dùng gửi vẫn là dữ liệu người dùng nếu server không tự thiết lập hoặc kiểm tra nó.

### 2.1. Chuẩn hóa múi giờ không làm dữ liệu đáng tin hơn

Chuyển `2026-12-01T17:00:00+07:00` thành một thời điểm UTC giúp so sánh đúng, nhưng không chứng minh người dùng thật sự gửi request lúc đó.

Cú pháp, độ chính xác và nguồn gốc là các vấn đề khác nhau. Một timestamp parse được vẫn có thể là lời khai giả.

## 3. Những cách lạm dụng thời gian client trong nghiệp vụ

| Cách lạm dụng | Thiết kế dễ bị ảnh hưởng | Hậu quả |
| --- | --- | --- |
| Lùi `submittedAt` về trước hạn | So sánh thời điểm client gửi với deadline | Dùng approval hoặc báo giá đã hết hiệu lực |
| Đẩy `expiresAt` ra xa | Nhận hạn dùng từ request | Tự kéo dài quyền hoặc reservation |
| Thay ngày request | Chọn bucket quota theo ngày client | Né giới hạn hoặc ghi nhận sai kỳ |
| Phát lại request có timestamp cũ | Coi timestamp hợp lệ là bằng chứng request mới hoặc duy nhất | Tạo hiệu ứng trùng |
| Khai đã hoàn thành trước mốc chốt | Tin `completedAt` để bỏ một bước kiểm tra | Đi tắt workflow hoặc ghi trạng thái sai |
| Đổi đồng hồ thiết bị | Dựa vào kiểm tra hoặc countdown ở frontend | Vượt giới hạn chỉ tồn tại trên giao diện |
| Gửi giờ tương lai | Tính độ mới bằng hiệu thời gian mà không chặn giá trị âm | Dữ liệu trông như luôn mới |

Một ví dụ không an toàn:

```java
// Không an toàn: thời điểm quyết định do client tự chọn.
if (request.clientSubmittedAt().isBefore(quote.expiresAt())) {
    acceptQuote(quote);
}
```

Đổi field thành `requestTime`, thêm chữ “verified” vào tên hoặc chuyển nó sang header không giải quyết vấn đề nguồn thẩm quyền.

## 4. Chọn đúng mốc mà deadline bảo vệ

Một hành động đi qua nhiều mốc:

```text
t_client  : thiết bị nói người dùng đã bấm xác nhận
t_ingress : thành phần đầu vào tin cậy nhận đủ yêu cầu theo hợp đồng
t_gate    : server kiểm tra và nhận quyền nghiệp vụ
t_commit  : transaction nhận command commit
t_send    : worker gửi yêu cầu ra nhà cung cấp
t_accept  : nhà cung cấp chấp nhận
t_finish  : hiệu ứng hoàn tất
```

Không được kiểm tra một mốc rồi khẳng định đã bảo vệ tất cả mốc còn lại.

### 4.1. Chính sách tại gate

Ví dụ của bài chọn:

> Báo giá phải còn hiệu lực tại thời điểm cơ sở dữ liệu kiểm tra việc nhận chấp nhận, sau khi đã lấy khóa báo giá. Chỉ transaction commit thành công mới tạo đơn hàng được nhận.

Theo hợp đồng này, người dùng bấm trước hạn nhưng request đến gate sau hạn vẫn có thể bị từ chối. Giao diện cần truyền đạt đúng điều kiện đó.

Mốc gate không đồng nghĩa chính xác với mốc commit. Nếu gate hợp lệ ngay trước hạn và commit hoàn tất ngay sau hạn, giao dịch có thể vẫn hợp lệ theo chính sách gate đã chọn.

### 4.2. Chính sách dựa trên thời điểm nhận

Một hệ thống có thể cam kết nhận yêu cầu đầy đủ trước deadline thì được xử lý sau. Khi đó cần một biên nhận do thành phần server tin cậy cấp, ràng buộc đúng nội dung, đối tượng, chủ thể và thời điểm nhận.

Không lấy `clientSubmittedAt` làm biên nhận. Cũng cần định nghĩa “nhận” là nhận đủ command cần thiết, không chỉ mở kết nối hoặc nhận vài header rồi để body đến sau hạn.

Queue, retry và chống replay phải được thiết kế để biên nhận của một request không được dùng cho nội dung khác.

### 4.3. Chính sách tại nhà cung cấp

Nếu bên ngoài chỉ được chấp nhận trước một deadline, cần cơ chế mà bên ngoài cũng thực thi theo hợp đồng. Kiểm tra đồng hồ cục bộ rồi gửi HTTP vẫn có thời gian truyền và xử lý.

Không thể hứa request không bao giờ được bên ngoài nhận muộn chỉ bằng một câu `if (now < expiresAt)` trong ứng dụng.

## 5. Deadline có thẩm quyền phải gắn với đúng quyền

Một báo giá không chỉ có một timestamp. Nó cần ràng buộc với nội dung và phạm vi được phát hành:

```text
PriceQuote = {
    tenant_id,
    quote_id,
    customer_or_owner_reference,
    content_digest,
    amount_minor,
    currency,
    not_before,
    expires_at,
    state,
    version
}
```

Client được gửi quote ID và expected version theo hợp đồng. Server đọc giá, tiền tệ, quyền sở hữu và deadline từ nguồn được quản lý; không nhận lại những giá trị đó như sự thật chỉ vì chúng từng xuất hiện trong response.

Điều kiện nhận có thể là:

```text
đúng_tenant_và_chủ_thể_được_phép
AND quote.state == OPEN
AND quote.version == expectedVersion
AND quote.not_before <= t_gate
AND t_gate < quote.expires_at
AND nội_dung_và_các_điều_kiện_nghiệp_vụ_còn_phù_hợp
```

### 5.1. Dùng khoảng nửa mở

Với khoảng `[not_before, expires_at)`, đúng `expires_at` là hết hiệu lực. Cần thống nhất quy tắc giữa service, cơ sở dữ liệu và những thành phần thực sự cấp quyền.

Không để frontend dùng một phép so sánh, API dùng phép khác và worker tự cộng thêm thời gian.

### 5.2. Không gia hạn khi đọc hoặc retry

Nếu mỗi lần đọc báo giá lại đặt `expires_at = now + TTL`, người dùng có thể giữ giá sống vô thời hạn bằng cách tải lại.

Gia hạn hoặc phát hành báo giá mới là một quyết định có policy riêng. Nó có thể cần định giá lại, kiểm tra ưu đãi, hạn mức hoặc những điều kiện khác. Không sửa deadline cũ ngầm chỉ để request đi qua.

## 6. Nguồn thời gian server cũng cần ngữ nghĩa rõ ràng

### 6.1. Một nguồn tin cậy cho điểm quyết định

Với dữ liệu chung trong một cơ sở dữ liệu, có thể chọn thời gian cơ sở dữ liệu cho gate. Với nhiều service, cần xác định nguồn, cách đồng bộ và giới hạn sai lệch chấp nhận được.

“Server time” không phải một giá trị bất kỳ từ node thuận tiện nhất. Nếu các node lệch đáng kể, cùng một quyền có thể được chấp nhận ở nơi này và từ chối ở nơi khác.

### 6.2. Đồng hồ UTC và đồng hồ đo khoảng thời gian

Trong Java, `Instant` phù hợp biểu diễn một mốc tuyệt đối, còn nguồn thời gian đơn điệu trong tiến trình có thể hữu ích để đo thời lượng hoặc timeout cục bộ.

Không lưu một giá trị từ `System.nanoTime()` rồi coi nó là timestamp UTC hoặc so sánh trực tiếp giữa các máy, các lần khởi động. Nó không thay thế deadline bền vững của một hồ sơ nghiệp vụ.

### 6.3. Đồng hồ server không tự bảo đảm luôn tiến

Đồng hồ hệ thống có thể được điều chỉnh. Dùng một hàm lấy thời gian thực không có nghĩa thời gian đó là một bộ đếm đơn điệu hoặc chính xác tuyệt đối.

Nếu nghiệp vụ cần bảo đảm một quyền đã được xác nhận hết hạn không sống lại, có thể cần trạng thái hết hiệu lực bền vững hoặc mốc quan sát có thẩm quyền cùng một thiết kế thời gian phù hợp. Không đặt lại trạng thái `EXPIRED` thành `OPEN` chỉ vì một lần đọc đồng hồ sau đó nhỏ hơn.

Một mốc lớn nhất đã quan sát không chứng minh hệ thống biết mọi khoảng thời gian đã trôi qua khi nó không quan sát được. Cần mô tả đúng giới hạn của cơ chế, đặc biệt trong mô hình phân tán hoặc khi đồng hồ gặp sự cố.

## 7. Transaction và thời gian chờ khóa

Một lỗi tinh vi là lấy thời gian trước khi chờ khóa:

```text
09:59:58  Transaction bắt đầu, ứng dụng lấy now.
09:59:59  Chờ khóa báo giá.
10:00:00  Báo giá hết hiệu lực.
10:00:02  Có khóa và dùng lại now của 09:59:58 để nhận đơn.
```

Theo chính sách gate sau khóa, việc nhận đó là sai. Thời điểm dùng để kiểm tra phải phù hợp với điểm mà server thực sự nhận quyền.

### 7.1. Ngữ nghĩa các hàm thời gian trong PostgreSQL

Trong PostgreSQL, `now()` và `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction. Một transaction dài không tự có giá trị mới khi gọi lại các biểu thức đó.

`statement_timestamp()` phản ánh lúc statement bắt đầu, còn `clock_timestamp()` phản ánh thời gian thực khi được đánh giá. Statement bắt đầu trước một lần chờ khóa cũng có thể mang mốc không phù hợp nếu hợp đồng cần kiểm tra sau lần chờ đó.

Ví dụ của bài lấy khóa bản ghi báo giá trước, rồi statement nhận quyền lấy một mốc mới bằng `clock_timestamp()`. Mốc đó là gate đã định nghĩa, không phải thời điểm commit hoặc thời điểm bên ngoài chấp nhận.

### 7.2. Khóa dữ liệu không dừng đồng hồ

Giữ row lock không đóng băng hiệu lực thời gian. Một quote hoặc approval vẫn có thể đi qua deadline trong lúc transaction đang chạy.

Giữ transaction ngắn, không gọi mạng bên ngoài và không lấy timestamp từ controller rồi giả định nó luôn còn mới khi ghi.

## 8. Ví dụ Java: chấp nhận báo giá mà không tin giờ client

### 8.1. Hợp đồng input

Một request có thể là:

```http
POST /price-quotes/quote-123/acceptances
Authorization: Bearer <access-token>
Idempotency-Key: 025dcf43-bbc1-4da5-9288-06e49840ff7d
Content-Type: application/json

{
  "expectedVersion": 18,
  "clientObservedAt": "2026-12-01T16:59:59+07:00"
}
```

Ví dụ cho phép `clientObservedAt` như telemetry tùy chọn. Nó không quyết định hiệu lực giá, không ghi đè `acceptedAt` và không được truyền xuống câu lệnh kiểm tra deadline như nguồn thời gian có thẩm quyền.

API cũng có thể không nhận timestamp client ở action này. Khi đó field ngoài hợp đồng phải được xử lý theo chính sách input của endpoint. Dù chọn cách nào, vẫn cần kiểm tra deadline từ nguồn server.

### 8.2. Service minh họa

Đây là thiết kế minh họa theo Spring transaction. Các repository, policy và kiểu dữ liệu cần được triển khai; constructor injection được lược bỏ.

```java
@Service
public class QuoteAcceptanceService {
    private final PriceQuoteRepository quotes;
    private final OrderRepository orders;
    private final QuoteAcceptancePolicy policy;
    private final IdempotencyRepository idempotency;
    private final WorkflowAuditRepository audits;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public QuoteAcceptanceReceipt accept(
            VerifiedActor actor,
            AcceptQuoteCommand command) {

        actor.requireAuthenticated();
        command.validateSyntaxAndBounds();

        PriceQuote quote = quotes.lockForUpdate(
                actor.tenantId(), command.quoteId())
            .orElseThrow(QuoteNotFoundException::new);

        // Quyền trên đối tượng; guard trạng thái cho lần nhận mới
        // và thời gian được kiểm tra riêng.
        policy.requireAcceptanceAuthority(actor, quote);

        CommandScope scope = new CommandScope(
                actor.tenantId(), quote.id(),
                actor.canonicalSubjectId(),
                "ACCEPT_QUOTE", command.idempotencyKey());
        String fingerprint = fingerprints.forQuoteAcceptance(command);

        var previous = idempotency.find(scope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        quote.requireOpenAtVersion(command.expectedVersion());
        policy.requireOtherAcceptanceConditions(actor, quote);

        // Repository tự lấy thời gian DB tại gate.
        // Không truyền clientObservedAt làm now hoặc deadline.
        QuoteClaim claim = quotes.claimIfValidNow(
                actor.tenantId(), quote.id(), quote.version())
            .orElseThrow(QuoteNotAcceptableNowException::new);

        UUID orderId = UUID.randomUUID();
        orders.insertFromServerQuote(
                orderId, quote, claim, actor.canonicalSubjectId());

        audits.appendQuoteAccepted(actor, orderId, quote, claim);
        outbox.appendOrderCreated(
                UUID.randomUUID(), actor.tenantId(), orderId);

        QuoteAcceptanceReceipt receipt = new QuoteAcceptanceReceipt(
                orderId, quote.id(), claim.checkedAt(),
                claim.amountMinor(), claim.currency());
        idempotency.insert(scope, fingerprint, receipt);
        return receipt;
    }
}
```

Các dependency `final` phải được khởi tạo qua constructor. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý và các repository phải dùng đúng transaction manager.

Ví dụ chỉ minh họa hiệu lực thời gian của quote và việc tạo đơn theo quote được nhận. Tồn kho, quota, giữ chỗ ưu đãi, phê duyệt hoặc những bất biến bổ sung phải được đưa vào giao thức khi nghiệp vụ cần; đây không phải một checkout hoàn chỉnh.

Giá, tiền tệ và nội dung đơn phải đến từ snapshot quote có thẩm quyền. Không lấy timestamp hoặc giá client gửi để bù cho một quote không còn hợp lệ.

### 8.3. Statement nhận quyền có thời điểm kiểm tra riêng

Sau khi service đã khóa báo giá, repository có thể dùng SQL dạng sau:

```sql
WITH gate_time AS MATERIALIZED (
    SELECT clock_timestamp() AS checked_at
)
UPDATE price_quote q
SET state = 'CONSUMED',
    consumed_at = g.checked_at,
    version = q.version + 1
FROM gate_time g
WHERE q.tenant_id = :tenantId
  AND q.id = :quoteId
  AND q.state = 'OPEN'
  AND q.version = :expectedVersion
  AND q.not_before <= g.checked_at
  AND g.checked_at < q.expires_at
RETURNING q.id,
          q.version,
          q.amount_minor,
          q.currency,
          q.content_digest,
          g.checked_at,
          q.expires_at;
```

Các dấu `:` là tham số bind của lớp truy cập dữ liệu. Thành công phải trả đúng một dòng. Không có dòng là không nhận được quyền theo các điều kiện đó; một lỗi kết nối hoặc lỗi SQL không được tự đổi thành kết luận chắc chắn quote hết hạn.

`MATERIALIZED` ở đây giúp dùng cùng một `checked_at` cho lần kiểm tra. Nó không làm statement và commit xảy ra tức thời, cũng không cung cấp một lời hứa thời gian ở nhà cung cấp.

Cần thêm ràng buộc nghiệp vụ thích hợp, chẳng hạn một quote chỉ sinh một đơn được chấp nhận trong mô hình này. Audit, order, trạng thái quote và idempotency phải commit hoặc rollback cùng nhau.

## 9. Replay và idempotency không được quyết định bằng timestamp

Một timestamp cũ không chứng minh request đã từng được xử lý. Một timestamp mới cũng không chứng minh đó là một ý định khác.

Không dùng riêng cặp `(objectId, clientTime)` để chống trùng. Người gọi có thể đổi thời gian trên cùng một ý định hoặc gửi hai request cùng timestamp.

Các lớp bảo vệ khác nhau:

| Lớp | Bảo vệ điều gì? |
| --- | --- |
| Thời hạn | Có được nhận một hành động mới tại gate không? |
| Idempotency | Retry cùng command có tạo lại hiệu ứng không? |
| Version và trạng thái | Có thao tác trên snapshot còn phù hợp không? |
| Ràng buộc nghiệp vụ | Một quote hoặc nghĩa vụ có được nhận nhiều lần không? |

### 9.1. Retry sau khi quote đã hết hạn

Nếu command đã commit hợp lệ trước đó, cùng key và cùng ý định có thể trả receipt cũ sau kiểm tra quyền phù hợp. Đây là đọc kết quả của lần nhận cũ, không dùng quote hết hạn để tạo một đơn mới.

Key mới phải đi qua guard hiện tại. Quote đã `CONSUMED` hoặc hết hạn không được nhận lại chỉ vì client gửi `clientObservedAt` trước deadline.

### 9.2. Telemetry và fingerprint

Nếu `clientObservedAt` chỉ là telemetry không ảnh hưởng ý định, hợp đồng có thể loại nó khỏi fingerprint nghiệp vụ. Khi đó thay telemetry không được làm thay đổi kết quả command.

Nếu một timestamp thực sự là dữ liệu nghiệp vụ của intent, nó cần tham gia ràng buộc nội dung theo policy và vẫn phải được đánh giá đúng mức tin cậy. Không gọi nó là telemetry trong code nhưng lại dùng để chọn deadline hoặc tính tiền ở bước sau.

### 9.3. ID chứa thời gian không phải bằng chứng thời gian

Một mã request hoặc ID có thành phần timestamp do client tạo vẫn là dữ liệu client. Không suy ra quyền trước hạn từ thứ tự từ điển hoặc phần thời gian trong ID đó.

## 10. Timestamp trong header, token và chữ ký

### 10.1. Header không tự đáng tin

Các header như `Date`, `X-Client-Time` hoặc `X-Received-At` do caller tự gửi không được dùng như đồng hồ server.

Nếu gateway tin cậy gắn mốc nhận, cần bảo vệ đường truyền metadata đó, xử lý header giả từ client và ràng buộc nó với request thực sự. Không để một tên header đặc biệt tạo ra nguồn tin cậy chỉ bằng quy ước.

### 10.2. Chữ ký chứng minh ai đã nói, không mặc nhiên chứng minh điều đã nói đúng

Một client ký payload có `occurredAt` cho thấy nguồn ký theo cơ chế được kiểm tra. Nếu client vẫn có thể chọn thời gian tùy ý, chữ ký không làm timestamp trở thành đồng hồ có thẩm quyền cho deadline của server.

Ngược lại, một token báo giá do server phát hành có thể bảo vệ deadline và nội dung mà server đã quyết định. Nó vẫn cần kiểm tra issuer, phạm vi, người dùng hoặc tenant liên quan, trạng thái thu hồi và replay theo mô hình đã chọn.

### 10.3. Thời điểm token không thay thế mọi thời điểm nghiệp vụ

Một token mới được cấp hoặc refresh không chứng minh người dùng vừa xác thực tăng cường, vừa phê duyệt hoặc vừa gửi một lệnh trước deadline.

Phải hiểu đúng ngữ nghĩa của từng claim từ bên phát hành được tin cậy. Không lấy một timestamp có chữ ký rồi dùng nó cho một sự kiện khác mà bên phát hành không chứng thực.

## 11. Callback và sự kiện từ hệ thống bên ngoài

Một nhà cung cấp có thể báo:

```json
{
  "executionId": "exec-123",
  "providerReportedAt": "2026-12-01T10:00:03Z",
  "status": "SUCCEEDED"
}
```

Hệ thống cần xác thực nguồn và gắn đúng execution command, tenant, số tiền hoặc nội dung theo giao thức. Timestamp trong callback không thay thế những kiểm tra đó.

Nên phân biệt:

```text
provider_reported_at : thời gian nhà cung cấp báo về sự kiện
server_received_at  : thời gian hệ thống mình nhận sự kiện
processed_at        : thời gian xử lý theo mô hình đã chọn
```

Không ghi đè audit server bằng thời gian trong payload rồi mất bằng chứng về độ trễ hoặc thứ tự tiếp nhận.

### 11.1. Đến muộn không đồng nghĩa không có hiệu ứng

Một callback thành công đến sau deadline không chứng minh lệnh sai, vì quyền có thể được xác lập tại gate trước đó theo hợp đồng. Nó cũng không được tự làm sống lại một workflow đã bị hủy hoặc mở đường chi lại.

Nếu deadline thực sự áp dụng tại nhà cung cấp, cần đối chiếu theo bằng chứng và khả năng mà giao thức bên ngoài hỗ trợ. Khi kết quả chưa rõ, dùng quy trình đối soát, không sửa timestamp để khớp trạng thái mong muốn.

### 11.2. Thứ tự sự kiện không chỉ dựa vào giờ client

Hai sự kiện có thể có đồng hồ lệch hoặc đến đảo thứ tự. State machine cần định danh command, version, sequence hoặc cơ chế thứ tự phù hợp, không đơn giản chọn payload có timestamp lớn hơn làm trạng thái mới nhất.

## 12. Dữ liệu offline và khai báo ngày nghiệp vụ

Một ứng dụng có thể hợp lệ nhận dữ liệu muộn, chẳng hạn chi phí phát sinh khi thiết bị không có mạng. Cần tách hai câu hỏi:

- Người dùng khai sự kiện xảy ra khi nào?
- Hệ thống còn cho phép nhận hoặc thực hiện nghiệp vụ đó vào lúc này không?

`claimedOccurredAt` có thể là dữ liệu cần lưu và kiểm tra bằng chứng. Nó không tự chuyển `serverReceivedAt` về quá khứ hoặc làm một approval đã hết hạn được dùng lại.

### 12.1. Chính sách nhận muộn phải có chủ ý

Có thể cần một khoảng tiếp nhận muộn, kiểm tra bổ sung hoặc phê duyệt ngoại lệ. Những điều đó phải do server xác định và ghi audit, không phải một cờ `wasOffline=true` mà client tự dùng để bỏ deadline.

Nếu muốn chứng minh sự kiện thật sự được ghi trước hạn trên thiết bị, cần một giao thức và mô hình tin cậy đủ cho yêu cầu đó. Một file ký bằng khóa client nhưng cho client tự chọn thời gian chưa tự đáp ứng yêu cầu chứng minh thời điểm.

### 12.2. Ngày dịch vụ có thể là input hợp lệ

Người dùng được chọn ngày dùng dịch vụ hoặc ngày đề nghị giao hàng không phải là lỗ hổng. Server cần validation khoảng ngày, quyền sửa, bằng chứng và những điều kiện nghiệp vụ liên quan.

Lỗ hổng xuất hiện khi lấy ngày khai báo ấy để tự cấp một quyền phụ thuộc đồng hồ có thẩm quyền, chẳng hạn tính request mới vào một kỳ quota cũ mà không có chính sách cho phép.

## 13. Quota, ưu đãi và reservation theo thời gian

### 13.1. Bucket thời gian phải do policy xác định

Nếu hạn mức tính theo ngày hoặc kỳ, cần múi giờ và quy tắc bucket rõ ràng. Không chọn bucket bằng `clientDate` rồi để caller tùy ý chuyển chi phí sang ngày khác.

Khi request chờ qua ranh giới kỳ, phải biết quota được giữ theo mốc nào. Gate, bucket và phần sử dụng được nhận cần nhất quán, với transaction hoặc cơ chế đồng bộ thích hợp.

### 13.2. Deadline của ưu đãi và quote

Nếu ưu đãi phải còn hiệu lực lúc nhận đơn, quote hoặc gate cần phản ánh điều kiện đó. Một giá chốt được phát trước đó không tự chứng minh mã ưu đãi còn dùng được theo mọi chính sách.

Không dùng `couponAppliedAt` do client gửi để coi ưu đãi đã được sử dụng trước khi hết hạn.

### 13.3. Reservation hết hạn không tự hủy mọi hiệu ứng

Nếu tài nguyên đã được chuyển sang một command thực thi hợp lệ, việc deadline của reservation trôi qua cần xử lý theo hợp đồng giữ chỗ và thực thi. Không vừa cho worker tiếp tục xử lý vừa cộng trả tài nguyên như thể chưa nhận lệnh.

Mỗi hành động giải phóng hoặc bù phải tham chiếu đúng reservation hay hiệu ứng gốc và chống thực hiện lặp. Thay timestamp không giải quyết được bất biến này.

## 14. Dung sai đồng hồ và trải nghiệm người dùng

### 14.1. Dung sai phải là chính sách server

Nếu có thời gian ân hạn hoặc dung sai, cần xác định ai được áp dụng, cho action nào và giới hạn bao nhiêu. Không nhận `clockSkewSeconds` hoặc `gracePeriod` tùy ý từ client.

Không tự cộng dung sai của một cơ chế kiểm tra token vào deadline nghiệp vụ. Đây là hai hợp đồng có thể khác nhau.

Nhiều lớp cùng tự cộng “một chút” có thể làm quyền kéo dài ngoài ý định. Cần biết deadline cuối cùng mà đường thực thi có thẩm quyền thực sự dùng.

### 14.2. Countdown chỉ là hướng dẫn

Giao diện có thể hiển thị deadline server và ước lượng thời gian còn lại để người dùng quyết định. Server vẫn kiểm tra tại gate.

Khi quote hết hạn, có thể yêu cầu lấy giá mới và xác nhận lại. Không tự thay giá hoặc deadline rồi thực hiện như thể người dùng đã đồng ý với nội dung mới.

### 14.3. Lỗi cần nói đúng tình trạng

Hết hạn là một thất bại có thể yêu cầu một quyết định mới. Lỗi lấy nguồn thời gian hoặc không xác định được tình trạng xử lý là lỗi khác.

Không biến lỗi cơ sở dữ liệu thành “quote expired”, cũng không coi timeout nhà cung cấp là validation chưa được nhận. Hướng phục hồi phải giữ đúng ý định và idempotency.

## 15. Audit và quản lý timestamp client

Audit nên giữ riêng:

- Thời điểm server dùng để đánh giá quyền.
- Deadline, version và snapshot nguồn được kiểm tra.
- Actor, tenant, đối tượng và command liên quan.
- Thời gian client hoặc provider khai báo nếu có nhu cầu chính đáng, với nhãn nguồn rõ ràng.
- Thời điểm server nhận và xử lý nếu cần phân tích độ trễ.

Không cho timestamp client ghi đè `approvedAt`, `consumedAt`, `createdAt` hoặc mốc audit có thẩm quyền qua một mapper cập nhật chung.

Telemetry cũng cần giới hạn định dạng, kích thước và miền giá trị. Đừng để một dữ liệu chỉ phục vụ chẩn đoán gây overflow, lỗi parse hoặc chi phối logic xử lý command.

| Tín hiệu | Điều cần kiểm tra |
| --- | --- |
| Nhiều request khai thời gian trước hạn nhưng đến sau hạn | Client giữ dữ liệu cũ, độ trễ hoặc cố lùi giờ |
| Timestamp client rất xa tương lai | Lỗi thiết bị, sai đơn vị hoặc ý đồ làm dữ liệu luôn mới |
| Quyền còn được dùng sau deadline server | Có đường tin thời gian client, cache cũ hoặc gate sai mốc |
| Lỗi hết hạn tăng khi chờ khóa | Giao diện, độ trễ và hợp đồng gate cần được xem xét |
| Deadline kéo dài sau mỗi lần đọc | Có thể đang tự gia hạn ngoài ý muốn |
| Callback và audit có thời gian bị ghi đè lẫn nhau | Mất nguồn gốc và khó đối soát |

Không ghi token hoặc bí mật trong link cùng toàn bộ raw payload chỉ để so sánh giờ. Dùng các trường chẩn đoán được kiểm soát và quyền đọc audit phù hợp.

## 16. Kiểm thử ranh giới và tình huống tấn công logic

### 16.1. Client không được điều khiển kết quả deadline

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Server đã qua hạn, client khai trước hạn | Không nhận quyền mới theo hợp đồng gate |
| Server còn hạn, client khai thời gian tương lai trong telemetry | Telemetry không tự làm đổi thời điểm cấp quyền; input vẫn chịu validation riêng |
| Client gửi `expiresAt` mới hoặc alias tương đương | Không ghi đè deadline có thẩm quyền |
| Client đổi đồng hồ thiết bị | Không thay đổi quyết định dựa trên server |
| Client tự đặt `X-Received-At` | Không được coi là mốc nhận tin cậy |
| Client ký một timestamp tùy chọn | Không được nâng thành thời gian có thẩm quyền ngoài hợp đồng |
| Thiếu timestamp tùy chọn | Không làm server mất khả năng kiểm tra deadline |
| Timestamp hỏng hoặc ngoài miền hỗ trợ | Lỗi có kiểm soát, không tự mặc định thành thời gian thuận lợi |

Nếu endpoint không nhận các field thời gian đó, kiểm tra việc từ chối field ngoài hợp đồng. Sau đó vẫn cần test riêng với payload đúng hình dạng để chứng minh quote thật sự hết hạn sẽ bị chặn; một lỗi field lạ không chứng minh kiểm tra thời gian đã đúng.

### 16.2. Kiểm thử biên thời gian

Với logic thuần Java, dùng `Clock` hoặc một abstraction thời gian có thể điều khiển để kiểm tra:

```text
t < not_before       → chưa được dùng
t == not_before      → có thể được dùng
not_before < t < end → có thể được dùng
t == end             → hết hiệu lực
t > end              → hết hiệu lực
```

Các điều kiện khác vẫn phải thỏa. Dùng độ chính xác thực tế của kiểu dữ liệu; không giả rằng một chênh lệch nano giây trong Java được cơ sở dữ liệu lưu nguyên vẹn.

Mock `Clock` ở Java không thay đổi `clock_timestamp()` trong PostgreSQL. Test phải biết nguồn thời gian nào đang thật sự được đường production sử dụng.

### 16.3. Kiểm thử chờ khóa qua hạn

Dùng transaction độc lập và điểm đồng bộ có điều khiển:

```text
T1 giữ khóa quote.
T2 bắt đầu request nhận quote trước deadline và chờ khóa.
Đến khi nguồn thời gian có thẩm quyền đã qua deadline, T1 nhả khóa.
T2 lấy khóa và thực hiện gate.

Kỳ vọng: T2 không dùng thời gian cũ trước lúc chờ để nhận quote.
```

Với đồng hồ DB trực tiếp, cần quan sát mốc DB hoặc có cơ chế thời gian test được thiết kế rõ ràng, cùng timeout giới hạn. Không dùng một khoảng sleep tùy ý làm bằng chứng rằng deadline chắc chắn đã bị vượt.

Test tích hợp cũng cần phát hiện việc thay nhầm gate bằng thời gian bắt đầu transaction. Những test dùng quote đã quá hạn từ trước giúp kiểm tra đường từ chối cơ bản nhưng chưa thay thế test về lần chờ này.

### 16.4. Retry, replay và tính nguyên tử

1. Command đã commit trước hạn, response mất, retry cùng key sau hạn: trả kết quả cũ theo quyền đọc phù hợp, không tạo đơn mới.
2. Key mới dùng quote đã consumed hoặc hết hạn: không nhận lại.
3. Thay timestamp client trên cùng ý định: không mở lại quyền hoặc vượt fingerprint theo hợp đồng.
4. Ghi order, audit hoặc outbox bắt buộc lỗi: trạng thái quote và dữ liệu liên quan rollback cùng nhau.
5. Hai request cạnh tranh cùng quote: không tạo hai đơn trái quy tắc duy nhất của ví dụ.
6. Quote mới được phát hành: kiểm tra lại nội dung và điều kiện, không chỉ kéo dài timestamp của quote cũ.

Kiểm tra dữ liệu quote, order, idempotency, audit và outbox, không chỉ HTTP status. Mock repository không chứng minh được khóa hoặc ranh giới commit.

### 16.5. Offline, callback và kỳ hạn mức

Kiểm tra dữ liệu đến muộn không tự nhận quyền nhờ `occurredAt`, callback không đổi audit server, và ngày client không chọn được bucket quota ngoài policy.

Nếu hệ thống có cơ chế tiếp nhận trước hạn hoặc ân hạn, test riêng bằng chứng nguồn, ràng buộc nội dung, giới hạn thời gian và chống replay. Không coi ngoại lệ đó là một nhánh cho qua mọi request gắn cờ offline.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao sai | Hướng thay thế |
| --- | --- | --- |
| So `clientSubmittedAt` với deadline | Người gọi tự lùi giờ | Mốc gate hoặc biên nhận server theo hợp đồng |
| Nhận `expiresAt` rồi lưu trực tiếp | Client tự kéo dài quyền | Deadline từ nguồn có thẩm quyền |
| Lấy now trước khi chờ khóa | Dùng mốc cũ để nhận quyền sau hạn | Lấy thời gian phù hợp tại gate |
| Dùng thời gian bắt đầu transaction cho gate hiện tại | Transaction dài có thể vượt deadline | Chọn ngữ nghĩa nguồn thời gian đúng |
| Chuẩn hóa UTC rồi coi dữ liệu đáng tin | Chỉ giải quyết biểu diễn, không giải quyết nguồn | Kiểm tra provenance và phạm vi |
| Chữ ký client làm timestamp thành sự thật | Người ký vẫn có thể chọn giờ | Giao thức thời gian và mô hình tin cậy phù hợp |
| Refresh token là mới phê duyệt hoặc mới xác thực | Nhầm ngữ nghĩa của sự kiện | Dùng đúng bằng chứng cho đúng action |
| Lấy timestamp làm khóa chống trùng | Có thể đổi giờ hoặc trùng giờ | Idempotency và ràng buộc nghĩa vụ riêng |
| Gia hạn quote ở mỗi lần đọc | Quyền không còn thời hạn thực tế | Phát hành hoặc gia hạn theo action được kiểm soát |
| Quota theo ngày client tự khai | Có thể chuyển request sang kỳ khác | Bucket và gate do server xác định |
| Hết hạn thì mở lại lệnh chưa rõ kết quả | Có thể tạo hiệu ứng tài chính trùng | Theo dõi command và đối soát |
| Callback ghi đè mọi mốc audit | Mất bằng chứng về nguồn và độ trễ | Lưu thời gian khai báo và thời gian server riêng |

## 18. Bài tập thiết kế

Thiết kế chức năng chấp nhận báo giá có hạn dùng, tạo đơn hàng một lần và xử lý qua worker. Ứng dụng có thể gửi telemetry đồng hồ thiết bị và một số request đến sau khi người dùng mất mạng.

Hãy mô tả:

1. Deadline bảo vệ `t_ingress`, `t_gate`, `t_send` hay một mốc khác, và vì sao?
2. Nguồn nào có thẩm quyền cho deadline và thời điểm kiểm tra?
3. Tenant, chủ thể, nội dung, giá và version được ràng buộc với quote như thế nào?
4. Tại sao `clientObservedAt` không được dùng để nhận một quote đã hết hạn?
5. Khi transaction chờ khóa qua deadline, gate lấy thời gian ở đâu?
6. Retry sau commit khác request mới sau hạn ra sao?
7. Nếu muốn chấp nhận dữ liệu offline hoặc yêu cầu nhận đủ trước hạn, bằng chứng server và giới hạn nào cần có?
8. Các test nào chứng minh cả API, worker, quota và callback không dùng thời gian client như quyền ngoài hợp đồng?

Một thiết kế đạt yêu cầu phải giữ rõ nguồn của từng timestamp, chọn đúng điểm cấp quyền và không để một lời khai về thời gian thay thế bằng chứng mà nghiệp vụ thực sự cần.
