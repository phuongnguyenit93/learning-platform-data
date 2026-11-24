# External response freshness

## 1. Phản hồi đúng nguồn vẫn có thể không còn dùng được

Một hệ thống thường hỏi dịch vụ bên ngoài để quyết định giá, hạn mức, tồn kho, trạng thái thanh toán hoặc điều kiện giao dịch. Phản hồi có thể đúng định dạng, đến từ đúng đối tác và có chữ ký hợp lệ, nhưng mô tả một trạng thái đã hết hiệu lực.

**External response freshness** là việc xác định phản hồi còn đủ mới, đúng ngữ cảnh và còn hiệu lực tại thời điểm ứng dụng dùng nó để ra quyết định. “Vừa nhận được” không đồng nghĩa “dữ liệu vừa được quan sát”. Một phản hồi vừa đến có thể đã nằm trong cache, queue hoặc tiến trình retry từ trước.

Trong bảo mật logic nghiệp vụ, kẻ lạm dụng có thể giữ lại giá ưu đãi cũ, dùng kết quả kiểm tra của đơn khác, gửi chậm một phản hồi chấp thuận hoặc làm kết quả cũ ghi đè một lần từ chối mới. Vì vậy, freshness cần gắn với bất biến, state machine, quyền theo đối tượng, transaction và idempotency.

Mục tiêu của bài là thiết kế điều kiện chấp nhận phản hồi, xử lý hết hạn và cạnh tranh, đồng thời kiểm thử những đường lạm dụng khiến ứng dụng dùng dữ liệu cũ để thực hiện hành động mới.

### Tình huống xuyên suốt

Một nền tảng thương mại hỏi dịch vụ kiểm tra rủi ro trước khi cho phép xử lý đơn “order-81” của tenant “t-acme”. Kết quả chỉ có ý nghĩa với:

~~~text
tenant = t-acme
order = order-81
order_revision = 12
amount_minor = 1250000
currency = VND
beneficiary = merchant-9
operation = AUTHORIZE_ORDER
~~~

Số tiền dùng đơn vị nhỏ nhất theo hợp đồng tiền tệ; không diễn giải một số nguyên mà thiếu currency và quy tắc đơn vị.

Lần kiểm tra đầu chấp thuận. Sau đó đơn đổi người nhận hoặc số tiền, và lần kiểm tra mới từ chối. Nếu phản hồi đầu đến chậm rồi làm đơn chuyển sang APPROVED, ứng dụng đã vi phạm logic dù cả hai phản hồi đều do đối tác thật gửi.

Các thời hạn, tên trạng thái và schema dưới đây là thiết kế minh họa, không phải thông số chung của mọi dịch vụ bên ngoài.

## 2. Tách bốn câu hỏi trước khi tin một phản hồi

| Câu hỏi | Điều cần chứng minh | Không thể suy từ |
| --- | --- | --- |
| Đúng nguồn và toàn vẹn? | Đúng endpoint/issuer, cơ chế xác thực và nội dung được bảo vệ | Mã HTTP 200 hoặc JSON hợp lệ |
| Đúng ngữ cảnh? | Đúng tenant, đối tượng, thao tác, input và lần kiểm tra | Chỉ có một request ID bất kỳ |
| Còn đủ mới? | Tuổi dữ liệu và thời hạn phù hợp policy hiện tại | Thời điểm ứng dụng vừa nhận response |
| Còn đủ để thực hiện hành động? | Trạng thái, quyền và cam kết nghiệp vụ vẫn cho phép chuyển bước | Chữ ký đúng hoặc TTL chưa hết |

Một phản hồi mới nhưng thuộc tenant khác phải bị từ chối. Một phản hồi đúng đơn nhưng tính trên số tiền cũ cũng không dùng được. Một phản hồi còn hạn vẫn không làm tài khoản bị khóa trở lại có quyền giao dịch.

Freshness là một điều kiện trong quyết định tổng thể:

~~~text
Được dùng phản hồi để chuyển trạng thái
  = nguồn/toàn vẹn hợp lệ
  AND ràng buộc ngữ cảnh hợp lệ
  AND đủ mới theo policy
  AND đúng lần kiểm tra đang có hiệu lực
  AND trạng thái và quyền hiện tại cho phép
  AND chưa tạo cùng hiệu ứng nghiệp vụ trước đó
~~~

Chữ ký không bảo đảm đối tác đã đọc dữ liệu mới nhất. Nếu nguồn phát hành sai, bị xâm nhập hoặc chỉ ký lại dữ liệu cache mà không công bố tuổi quan sát, ứng dụng không thể tự tạo ra bằng chứng về độ mới còn thiếu.

## 3. Hiểu đúng các mốc thời gian

| Mốc | Ý nghĩa | Nguồn |
| --- | --- | --- |
| requested_at | Hệ thống gửi yêu cầu lúc nào | Máy chủ của ứng dụng |
| observed_at | Dữ liệu nghiệp vụ được nguồn quan sát lúc nào | Đối tác có hợp đồng ngữ nghĩa rõ |
| issued_at | Phản hồi hoặc quyết định được phát hành lúc nào | Đối tác |
| signature_created_at | Chữ ký được tạo lúc nào | Metadata chữ ký đã xác minh |
| expires_at | Nguồn cho phép dùng phản hồi đến lúc nào | Đối tác |
| received_at | Ứng dụng nhận phản hồi lúc nào | Máy chủ của ứng dụng |
| decided_at | Ứng dụng áp dụng điều kiện để ra quyết định lúc nào | Máy chủ tại điểm quyết định |
| business_valid_until | Quote, reservation hoặc quyền cụ thể hết hạn lúc nào | Nguồn có thẩm quyền đối với cam kết đó |

Các mốc này không thay thế lẫn nhau:

- issued_at mới có thể bao quanh observed_at cũ.
- received_at mới không đặt lại tuổi dữ liệu.
- Chữ ký mới không gia hạn quote đã hết hạn.
- expires_at rất xa không được nới max-age mà ứng dụng tự quy định.
- requested_at chứng minh lúc hỏi, không chứng minh nguồn đã đọc trạng thái sau thời điểm đó.

Nếu dùng JWT, RFC 7519 phân biệt exp, nbf và iat; iat là thời điểm phát hành token. Tuổi token không tự trở thành tuổi của dữ liệu nghiệp vụ được token mô tả. Profile tích hợp phải quy định claim bắt buộc và cách kiểm tra. [RFC 7519, mục 4.1](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1).

Nếu đối tác không cung cấp observed_at đáng tin, cần làm rõ họ cam kết “đọc dữ liệu tại thời điểm xử lý request”, “dữ liệu có thể trễ tối đa bao lâu” hay chỉ trả một bản chụp không có giới hạn độ trễ. Không tự điền observed_at bằng received_at để làm phản hồi trông mới hơn.

### Đồng hồ thực và đồng hồ đơn điệu

Dùng thời gian UTC cùng định dạng, độ chính xác và giới hạn giá trị đã thống nhất. Từ chối timestamp sai đơn vị, sai định dạng, thiếu timezone hoặc gây tràn số.

Wall clock phù hợp để so sánh với timestamp bên ngoài và lưu bằng chứng. Đồng hồ đơn điệu phù hợp đo timeout, thời gian xử lý và ngân sách còn lại trong một tiến trình. Không lưu System.nanoTime để so với máy khác hoặc dùng sau restart.

Phải theo dõi sai lệch đồng hồ. Khi vượt giới hạn tin cậy, quyết định nhạy cảm nên chuyển sang trạng thái chờ hoặc luồng ngoại lệ đã kiểm soát. Không tự tăng clock-skew tolerance vô hạn để làm kiểm tra đi qua. Một deadline lưu bằng wall clock cũng cần chính sách khi đồng hồ bị lùi; timer đơn điệu và nguồn thời gian được giám sát giúp phát hiện, không thay thế hoàn toàn ngữ nghĩa thời gian liên máy.

## 4. Định nghĩa cửa sổ sử dụng bằng policy cục bộ

Một policy freshness cần chỉ rõ:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Decision type | Dùng để hiển thị, phê duyệt hay thực hiện hành động nào? |
| Authority | Nguồn nào có quyền xác nhận dữ liệu này? |
| max_data_age | Dữ liệu quan sát được phép cũ tối đa bao lâu? |
| max_response_validity | Nguồn được cấp thời hạn response dài nhất bao lâu? |
| clock_uncertainty | Sai lệch đồng hồ tối đa được tin cậy là bao nhiêu? |
| request_deadline | Lần kiểm tra local hết thời gian chờ khi nào? |
| Required binding | Cần khớp tenant, object revision, số tiền và những field nào? |
| Reuse scope | Chỉ dùng một command hay được dùng lại có điều kiện? |
| Unknown behavior | Hết hạn, mất nguồn hoặc sai đồng hồ thì chuyển bước nào? |

Các giá trị do phía máy chủ chọn theo rủi ro và hợp đồng nguồn, không lấy từ request của người dùng. Policy cho hiển thị giá tham khảo có thể khác policy cho chốt thanh toán. Không áp dụng cùng một TTL tùy tiện cho mọi hành động.

### Một cách tính bảo thủ

Giả sử timestamp của nguồn đã được xác thực, observed_at và issued_at dùng cùng đồng hồ theo hợp đồng; độ lệch giữa nguồn và ứng dụng không vượt quá delta. Thiết kế minh họa lấy:

~~~text
data_deadline     = observed_at + max_data_age - delta
response_deadline = expires_at - delta
signature_deadline = signature_expires_at - delta   (nếu profile có)
business_deadline = business_valid_until - delta    (nếu có)
local_deadline   = request_deadline

effective_deadline = min(các deadline áp dụng)

Chấp nhận về thời gian chỉ khi:
  now < effective_deadline
~~~

Dấu trừ delta dành cho chính sách bảo thủ: nếu đồng hồ nguồn chạy nhanh, phản hồi có thể hết hạn thực sớm hơn timestamp biểu diễn. Đây là lựa chọn của bài cho quyết định nhạy cảm, không phải công thức bắt buộc của JWT hay HTTP.

Timestamp quá xa trong tương lai phải bị chặn riêng. Không dùng việc trừ tuổi ra số âm để kết luận “chưa cũ”. Kiểm tra cả thứ tự thời gian, giới hạn thời hạn và các mốc bắt buộc theo profile.

Một triển khai chọn cộng tolerance vào expiry phải hiểu rằng nó đang chấp nhận một cửa sổ sau hạn danh nghĩa. Không vừa cộng grace period nhiều nơi vừa tuyên bố dữ liệu chắc chắn không quá tuổi.

### Ví dụ tính deadline

~~~text
observed_at        = 03:15:00.000Z
issued_at          = 03:15:00.200Z
expires_at         = 03:15:10.000Z
max_data_age       = 5 giây
delta              = 0,200 giây
request_deadline   = 03:15:06.000Z
Không có deadline bổ sung sớm hơn.

data_deadline      = 03:15:04.800Z
response_deadline  = 03:15:09.800Z
effective_deadline = 03:15:04.800Z
~~~

Quyết định lúc 03:15:03.000Z có thể qua điều kiện thời gian. Đúng 03:15:04.800Z thì không qua vì quy tắc dùng dấu nhỏ hơn nghiêm ngặt. Nếu response nằm trong queue đến 03:15:05.000Z, không được dùng dù nó còn expires_at đến giây thứ 10.

Policy phải nêu mốc áp dụng là lúc nhận, lúc ra quyết định, lúc xác nhận với nguồn hay thời điểm khác. Kiểm tra lúc nhận không đủ cho một hành động được thực thi nhiều giây sau.

## 5. Ràng buộc phản hồi với đúng giao dịch

Một envelope minh họa, sau khi được xác thực và bảo vệ toàn vẹn:

~~~json
{
  "schema_version": 1,
  "issuer": "risk-provider-a",
  "audience": "order-service",
  "response_id": "rsp-551",
  "request_id": "risk-req-703",
  "nonce": "example-server-generated-random-value",
  "attempt_epoch": 3,
  "tenant_id": "t-acme",
  "subject_id": "order-81",
  "subject_revision": 12,
  "operation": "AUTHORIZE_ORDER",
  "input_digest": "sha256:example",
  "decision": "ALLOW",
  "source_version": 104,
  "observed_at": "2026-11-22T03:15:00.000Z",
  "issued_at": "2026-11-22T03:15:00.200Z",
  "expires_at": "2026-11-22T03:15:10.000Z",
  "policy_version": "risk-model-9"
}
~~~

Đây không phải JWT hoàn chỉnh hay ví dụ header chữ ký. Các field chỉ có giá trị tin cậy khi cơ chế xác thực của profile bảo vệ chúng cùng kết quả quyết định.

Pending request do ứng dụng tạo phải lưu nonce ngẫu nhiên, tenant, object, revision, loại thao tác, digest input, attempt epoch và deadline. Khi response đến, so khớp với bản pending đó; không chỉ so hai giá trị do client cùng gửi lên.

Digest input nên bao gồm mọi thuộc tính thay đổi ý nghĩa quyết định: số tiền, currency, người nhận, giỏ hàng, điều kiện ưu đãi hoặc phạm vi quyền liên quan. Chuẩn hóa dữ liệu theo quy tắc ổn định trước khi băm; không dùng phép băm để thay cho kiểm tra quyền hoặc che giấu input dễ đoán.

Issuer và audience phải được kiểm tra bằng cấu hình tin cậy. Không lấy URL hoặc khóa xác minh tùy ý từ response rồi gọi mạng theo chỉ dẫn đó. Không nhận một chữ ký hợp lệ của đối tác khác chỉ vì dùng cùng thuật toán.

Nếu dùng HTTP Message Signatures, profile phải yêu cầu đủ thành phần được ký và bảo vệ cả nội dung qua cơ chế digest phù hợp; chỉ ký timestamp không bảo vệ kết quả trong body. RFC 9421 cũng mô tả nonce và nguy cơ replay: chữ ký đúng vẫn có thể bị dùng lại nếu thiếu ràng buộc. [RFC 9421, mục 7.2](https://www.rfc-editor.org/rfc/rfc9421.html#section-7.2).

Nonce giúp liên kết một lần trao đổi, nhưng không buộc đối tác quan sát dữ liệu mới. Đối tác vẫn có thể trả cache cũ trong một envelope ký mới; cần hợp đồng observed_at hoặc độ trễ nguồn để đánh giá trường hợp đó.

## 6. Replay, retry và phản hồi đến sai thứ tự

Freshness, anti-replay và idempotency giải quyết các vấn đề khác nhau:

| Cơ chế | Mục đích | Chưa giải quyết |
| --- | --- | --- |
| TTL/max-age | Giới hạn cửa sổ dùng dữ liệu | Dùng cùng response nhiều lần trong cửa sổ |
| Nonce/request binding | Gắn response với request cụ thể | Tác dụng phụ lặp nếu hai worker cùng xử lý |
| Idempotency | Không tạo thêm hiệu ứng cho cùng command | Nội dung response đã cũ hoặc sai đối tượng |
| Attempt epoch | Vô hiệu hóa lần kiểm tra đã bị thay thế | Trạng thái mới nhất tại nguồn nếu nguồn không cung cấp bảo đảm |
| Source version | Phát hiện hồi quy theo thứ tự của nguồn | Tuổi tuyệt đối và các thay đổi nguồn chưa biết |

### Một pending check chỉ được hoàn tất một lần

Không đánh dấu nonce đã dùng trước rồi cập nhật đơn ở transaction khác. Nếu phần sau thất bại, lần retry hợp lệ có thể bị chặn trong khi đơn chưa được xử lý.

Trong cùng transaction local, ràng buộc response với pending check, kiểm tra trạng thái, cập nhật đơn, hoàn tất pending check và ghi audit/outbox. Unique constraint hoặc conditional update bảo đảm chỉ một worker tiêu thụ kết quả.

Cùng response đến lại sau khi đã commit có thể được nhận diện là duplicate và trả kết quả cũ; không tạo thêm quyết định hoặc tác dụng phụ. Nếu cùng response_id nhưng payload khác, coi là bất nhất hoặc vi phạm toàn vẹn, không ghi đè bản đầu.

### Lần kiểm tra cũ không được thắng lần mới

~~~text
A: attempt_epoch=2, input revision=12, phản hồi đến chậm
B: attempt_epoch=3, input revision=13, phản hồi đến trước

Đã bắt đầu B và công bố B là lần kiểm tra hiện hành
=> response của A không được hoàn tất B hoặc sửa revision 13.
~~~

Khi khởi tạo một lần kiểm tra thay thế, tăng epoch và lưu trạng thái nguyên tử. Nếu chỉ retry vận chuyển của cùng một lần trao đổi, có thể giữ request/nonce theo hợp đồng. Nếu tạo một lần quan sát nghiệp vụ mới, tạo attempt mới và vô hiệu hóa attempt cũ rõ ràng.

Source version chỉ so sánh trong cùng miền thứ tự, chẳng hạn cùng issuer, subject và stream epoch do nguồn định nghĩa. Không so số phiên bản của hai nhà cung cấp hoặc hai tài khoản khác nhau. Timestamp phát hành không thay thế sequence/version.

Version thấp hơn mốc đã chấp nhận là ứng viên hồi quy; cùng version nhưng nội dung khác là bất nhất. Version cao hơn vẫn có thể đã cũ hoặc thuộc sai input. Không giả định local biết version mới nhất của nguồn chỉ vì nó biết một version đã từng nhận.

## 7. Áp dụng phản hồi qua state machine và transaction

Một state machine local minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CHECK_PENDING: Chốt input và tạo pending check
    CHECK_PENDING --> READY_FOR_CONFIRMATION: ALLOW hợp lệ, còn đủ mới
    CHECK_PENDING --> REJECTED: DENY hợp lệ
    CHECK_PENDING --> RECHECK_REQUIRED: Hết hạn hoặc input thay đổi
    CHECK_PENDING --> CHECK_UNKNOWN: Timeout hoặc thiếu bằng chứng
    CHECK_UNKNOWN --> CHECK_PENDING: Kiểm tra lại có kiểm soát
    RECHECK_REQUIRED --> CHECK_PENDING: Tạo attempt mới
    READY_FOR_CONFIRMATION --> RECHECK_REQUIRED: Căn cứ hết hạn hoặc input đổi
    READY_FOR_CONFIRMATION --> CONFIRMING: Đủ điều kiện thực hiện
    CONFIRMING --> COMPLETED: Xác nhận kết quả ngoài hệ thống
    CONFIRMING --> RECONCILING: Kết quả bên ngoài chưa rõ
    RECONCILING --> COMPLETED: Đối soát thành công
    RECONCILING --> REJECTED: Xác nhận không thực hiện được
~~~

READY_FOR_CONFIRMATION không phải cam kết tồn kho hay đã thanh toán. Nó chỉ nói lần kiểm tra rủi ro đã đủ điều kiện ở điểm quyết định local. Tại bước CONFIRMING phải xét lại những điều kiện mà policy yêu cầu còn hiệu lực.

Khi đơn thay đổi field ảnh hưởng quyết định, tăng revision và vô hiệu hóa pending check hoặc căn cứ hiện có trong cùng transaction. Không chỉ kiểm tra freshness ở controller rồi để service tiếp tục dùng một object có thể đã đổi.

### Mã giả Java: nhận kết quả kiểm tra

Đoạn dưới minh họa ranh giới xử lý, không phải chương trình hoàn chỉnh để biên dịch:

~~~java
ApplyResult acceptExternalResponse(byte[] raw) {
    // Giới hạn kích thước, parse nghiêm ngặt, kiểm tra schema và chữ ký.
    VerifiedEnvelope response = verifier.verify(raw);

    return unitOfWork.inTransaction(() -> {
        PendingCheck check = checks.lockByTrustedRequestId(
            response.issuer(), response.requestId());

        Order order = orders.lockByTenantAndId(
            check.tenantId(), check.orderId());

        authorization.requireCurrentDecisionRights(check, order);
        response.requireBindingTo(check); // Nonce, tenant, input, operation...
        trustPolicy.requireIssuerStillAccepted(response);

        if (check.isCompleted()) {
            check.requireSameAcceptedResponse(
                response.responseId(), response.payloadDigest());
            return ApplyResult.alreadyApplied(check.savedResult());
        }

        check.requirePending();
        check.requireEpoch(order.activeCheckEpoch());
        order.requireRevision(check.orderRevision());
        order.requireState(CHECK_PENDING);

        FreshnessPolicy policy = policies.forDecision(
            check.operation(), order.riskClass());
        sourceVersions.lockAndRequireNotOlder(response);

        // Đọc thời gian sau khi đã chờ các khóa liên quan.
        Instant decisionTime = trustedClock.instant();
        FreshnessDecision freshness = freshnessValidator.requireUsable(
            response, check, policy, decisionTime);

        if (response.decision() == ALLOW) {
            order.markReadyForConfirmation(
                response.responseId(), freshness.effectiveDeadline());
        } else if (response.decision() == DENY) {
            order.rejectFromCurrentCheck(response.responseId());
        } else {
            throw new UnsupportedDecision();
        }

        checks.completeOnce(check, response, order.result());
        sourceVersions.recordAccepted(response);
        orders.save(order);

        AuditRecord record = audit.externalDecisionApplied(
            order, check, response, policy, freshness, decisionTime);
        auditRepository.insert(record);
        outboxRepository.insert(record);

        return ApplyResult.applied(order.result());
    });
}
~~~

VerifiedEnvelope là dữ liệu bất biến đã được xác thực; nó không phải JSON do client tự gắn nhãn “verified”. requireBindingTo kiểm tra toàn bộ ngữ cảnh bắt buộc. Việc tra pending check bằng request ID chỉ xác định ứng viên, không thay thế xác minh chữ ký, issuer và binding.

freshnessValidator phải kiểm tra nguồn thời gian khỏe, timestamp bắt buộc, thứ tự thời gian, future skew, max validity và effective deadline theo policy. sourceVersions chỉ có ý nghĩa nếu đối tác cung cấp miền phiên bản so sánh được; không tự tạo thứ tự từ một ID ngẫu nhiên.

Các đường sửa đơn, đổi epoch và áp dụng response phải dùng chiến lược khóa/version nhất quán. Nếu cấp quyền liên quan nằm ở dịch vụ ngoài, cần giao thức phiên bản hoặc thu hồi được thiết kế riêng; kiểm tra từ xa không tự tạo transaction chung với database local.

### Kiểm tra ở đúng thời điểm

Một request có thể nhận response trước hạn nhưng chờ khóa đến sau hạn. Vì vậy, lấy thời gian ngay trước điểm quyết định, sau các bước có thể chờ lâu. Với cơ sở dữ liệu có hàm thời gian cố định ở đầu transaction, phải biết rõ ngữ nghĩa trước khi dùng để kiểm tra hết hạn.

Ngay cả kiểm tra trong transaction cũng không tự bảo đảm timestamp commit luôn trước deadline: tiến trình có thể bị treo sau câu lệnh kiểm tra. Thiết kế phải định nghĩa bảo đảm tại điểm quyết định local và giới hạn thời gian xử lý; nếu cần nguồn bên ngoài xác nhận tính hợp lệ ở thời điểm thực hiện, dùng giao thức xác nhận tại nguồn.

Kết quả đã áp dụng rồi bị gửi trùng không cần được coi là một quyết định mới. Có thể trả “đã xử lý” dù thời hạn response đã qua, miễn chỉ đọc kết quả cũ với quyền hiện tại, không tái kích hoạt đơn hoặc phát thêm tác dụng phụ.

### Đường lỗi cũng phải có trạng thái rõ

Response hết hạn không được chuyển đơn sang ALLOW mặc định. Có thể ghi RECHECK_REQUIRED bằng một command riêng đã khóa lại trạng thái, hoặc lên lịch kiểm tra lại có quota. Response sai chữ ký hoặc sai binding không được phép tự đổi đơn theo nội dung mà nó khai báo.

Nếu audit/outbox bắt buộc nằm cùng transaction, lỗi ghi chúng làm rollback việc áp dụng quyết định. Sự kiện từ chối hoặc rollback cần kênh security event riêng, vì audit trong transaction bị rollback sẽ không còn.

## 8. Cache không được biến dữ liệu cũ thành dữ liệu mới

Cache HTTP và cache ứng dụng giải quyết việc tái sử dụng dữ liệu, nhưng không quyết định thay policy nghiệp vụ.

RFC 9111 định nghĩa độ mới HTTP qua tuổi response và freshness lifetime. no-cache yêu cầu xác nhận lại trước khi tái sử dụng theo ngữ nghĩa tương ứng; no-store yêu cầu không lưu vào cache. Chúng không phải cùng một chỉ thị. [RFC 9111, mục 4.2 và 5.2](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2).

Một response HTTP còn fresh không tự chứng minh dữ liệu rủi ro bên trong đủ mới cho giao dịch. Ngược lại, dữ liệu được lưu để audit không có nghĩa được phép tiếp tục dùng làm căn cứ.

### Các lỗi cache thường gặp

| Lỗi | Vì sao nguy hiểm | Cách thiết kế |
| --- | --- | --- |
| TTL bắt đầu lại mỗi lần đọc | Response cũ sống mãi khi có lưu lượng | Giữ deadline tuyệt đối của bằng chứng |
| Ghi received_at mới khi copy cache | Che mất tuổi dữ liệu nguồn | Giữ observed_at, issued_at và provenance gốc |
| Chỉ dùng customer ID làm cache key | Dùng nhầm tenant hoặc thao tác | Key chứa toàn bộ miền ngữ cảnh cần thiết |
| Cache ALLOW cho mọi số tiền | Kết quả của input nhỏ dùng cho input lớn | Ràng buộc input digest và decision policy |
| stale-while-revalidate cho quyết định nhạy cảm | Cho phép thao tác bằng căn cứ đã hết hạn | Chỉ dùng stale cho các mục đích được policy cho phép |
| Refresh lỗi nhưng vẫn đặt TTL mới | Biến lỗi nguồn thành thời hạn hợp lệ mới | Không gia hạn dữ liệu khi chưa có bằng chứng mới |
| 304 làm ứng dụng tự đổi observed_at | Xác nhận representation không nhất thiết là quan sát nghiệp vụ mới | Giữ ngữ nghĩa theo hợp đồng nguồn |

Không lưu verdict chỉ theo boolean và timestamp cache local. Cache entry cần giữ issuer, subject/input binding, tuổi quan sát, hạn nguồn, phiên bản policy và provenance cần thiết.

Cache key phải bao gồm tenant, subject, thao tác, input revision/digest và miền quyền hoặc policy thích hợp. Tránh đưa secret thô vào key. Trước khi dùng vẫn kiểm tra quyền hiện tại; cache hit không duy trì quyền đã bị thu hồi.

Không cố đưa response có nonce một lần của request A vào request B bằng cách sửa request ID. Nếu được phép tái sử dụng một kết quả nguồn, profile phải định nghĩa một dạng bằng chứng có phạm vi tái sử dụng riêng, rồi ứng dụng áp policy cho từng lần dùng.

### Phản hồi 304 và sự kiện invalidation

Xác nhận HTTP rằng representation chưa thay đổi không tự nói rằng phép kiểm tra nghiệp vụ vừa chạy lại trên dữ liệu authoritative. Ví dụ nguồn có thể xác nhận cùng một tài liệu snapshot cũ. Chỉ cập nhật mốc quan sát nếu hợp đồng nguồn cung cấp bằng chứng tương ứng.

Thông báo invalidation giúp giảm trễ, nhưng có thể đến chậm hoặc bị mất. Kết hợp version và deadline; không biến việc chưa nhận invalidation thành bằng chứng quyền vẫn còn mãi.

## 9. Đủ mới không đồng nghĩa giữ nguyên được trạng thái bên ngoài

Giả sử nguồn báo còn một sản phẩm lúc 10:00:00, TTL là hai giây. Hai đơn hỏi cùng lúc đều có thể thấy còn hàng và cùng chốt trong cửa sổ đó. Không phản hồi nào quá tuổi, nhưng hệ thống vẫn có thể bán vượt tồn.

Tương tự, hạn mức khả dụng vừa đọc không phải quyền trừ tiền; trạng thái thanh toán quan sát được cũng không thay thế đúng thao tác xác nhận hoặc đối soát cần thiết.

| Nhu cầu | Cơ chế cần thêm ngoài freshness |
| --- | --- |
| Bảo đảm giữ hàng | Reservation có ID, số lượng, chủ sở hữu và hạn giữ |
| Khóa giá cho giao dịch | Quote ràng buộc input, currency, thời hạn và điều kiện xác nhận |
| Thực hiện trừ/chuyển tiền | Command có idempotency tại nguồn, kiểm tra trạng thái và giới hạn |
| Áp dụng với đúng phiên bản nguồn | Compare-and-set hoặc precondition do nguồn thực thi |
| Chờ nhiều hệ thống hoàn tất | State machine, saga/compensation và reconciliation |

Ứng dụng nên phân biệt ba loại chứng cứ:

- **Observation:** nguồn đã thấy một trạng thái; trạng thái có thể đổi ngay sau đó.
- **Decision:** nguồn chấp thuận một yêu cầu trong phạm vi và thời hạn cụ thể.
- **Commitment:** nguồn đã giữ tài nguyên hoặc cam kết chấp nhận một thao tác đáp ứng điều kiện xác định.

Một decision về rủi ro không mặc nhiên là commitment về tồn kho. Hợp đồng phải xác định điều kiện nào được bảo đảm đến hạn, điều kiện nào chỉ là thông tin quan sát.

### Không giữ transaction database qua lời gọi mạng

Không giữ khóa database trong khi chờ đối tác rồi giả định cả hai hệ thống commit nguyên tử. Lời gọi mạng có thể timeout dù thao tác bên ngoài đã thành công; transaction local rollback không đảo ngược hệ thống bên ngoài.

Một luồng điển hình:

1. Transaction local chốt input, tạo operation ID và chuyển sang CONFIRMING.
2. Worker thực hiện command bên ngoài với idempotency key ổn định.
3. Nguồn kiểm tra quote/reservation/precondition tại điểm thực hiện.
4. Transaction local ghi kết quả xác nhận đúng operation và trạng thái.
5. Nếu kết quả chưa rõ, chuyển RECONCILING và truy vấn/đối soát bằng operation ID.

Outbox giúp chuyển tiếp command bền vững, nhưng job nằm lâu trong outbox vẫn có thể hết deadline. Worker phải kiểm tra điều kiện tại lúc xử lý, không chỉ lúc enqueue.

Không tự tạo idempotency key mới để retry một thao tác có thể đã thành công. Giữ danh tính operation để xác định kết quả; việc phát sinh một quyết định mới cần là bước nghiệp vụ mới được kiểm soát.

## 10. Khi hết hạn, timeout hoặc mất dịch vụ nguồn

Không gộp tất cả kết quả thành true/false. Nên phân biệt:

| Kết quả | Ý nghĩa | Hành vi điển hình |
| --- | --- | --- |
| ALLOW_FRESH | Căn cứ hợp lệ tại điểm quyết định | Chuyển bước nếu các điều kiện khác cũng đúng |
| DENY_FRESH | Nguồn từ chối cho ngữ cảnh hiện tại | Từ chối hoặc chuyển quy trình đã quy định |
| STALE | Bằng chứng đã quá thời hạn ứng dụng cho phép | Kiểm tra lại, không dùng để cấp quyền mới |
| CONTEXT_MISMATCH | Sai tenant, input, thao tác hoặc epoch | Chặn, điều tra nếu có dấu hiệu lạm dụng |
| UNVERIFIABLE | Không xác minh được nguồn/toàn vẹn/schema | Không dùng làm căn cứ |
| UNKNOWN | Chưa biết kết quả do timeout/mất nguồn | Giữ trạng thái chờ hoặc đối soát |

Các tên trên là mô hình ứng dụng. Không suy quyết định ALLOW chỉ từ HTTP 200, và không suy thao tác bên ngoài chưa chạy chỉ từ HTTP 500 hoặc timeout.

“Fail closed” cho bước nhạy cảm có nghĩa không thực hiện hành động thiếu căn cứ bắt buộc. Nó không nhất thiết là hủy đơn, từ chối khách hàng vĩnh viễn hoặc trả lỗi khó hiểu. Trạng thái chờ, retry có hạn và luồng xem xét thủ công thường giúp giữ cả an toàn lẫn khả năng vận hành.

Nếu có ngoại lệ vận hành, cần vai trò riêng, lý do, phạm vi, thời hạn và phê duyệt phù hợp; ngoại lệ là một quyết định mới có audit, không phải sửa timestamp cũ để làm response hợp lệ.

Kết quả DENY cũng cần freshness. Một lần từ chối cũ không nên khóa giao dịch mới vô thời hạn, trừ khi policy nguồn quy định đó là một lệnh chặn còn hiệu lực với vòng đời riêng.

Retry dùng backoff, jitter, giới hạn số lần và deadline nghiệp vụ. Khi không đủ thời gian còn lại cho lần thử có ích, chuyển trạng thái phù hợp thay vì kéo dài request_deadline vô hạn. Chống lạm dụng bằng quota theo tenant, đối tượng và operation; người gọi không được ép vô hạn lần kiểm tra để tìm một kết quả thuận lợi.

## 11. Audit và quan sát độ mới

Để điều tra vì sao ứng dụng chấp nhận một phản hồi, cần giữ được dữ liệu ra quyết định và policy thực sự áp dụng.

| Nhóm | Dữ liệu nên ghi |
| --- | --- |
| Đối tượng | Tenant, subject ID, local revision, operation ID |
| Lần kiểm tra | Request ID, attempt epoch, response ID, issuer |
| Ràng buộc | Input digest, kiểu thao tác, audience đã kiểm tra |
| Thời gian | Observed/issued/received/decided time, các deadline áp dụng |
| Policy | Policy ID/version, max age, clock uncertainty |
| Phiên bản nguồn | Version và miền thứ tự, nếu có |
| Kết quả | Accepted/duplicate/stale/mismatch/unknown và reason code |
| Liên kết | Audit ID, trace ID, outbox ID, operation bên ngoài |

Không ghi token, khóa, toàn bộ hồ sơ cá nhân hoặc raw response nhạy cảm vào log chỉ để chứng minh freshness. Có thể lưu digest và metadata tối thiểu, cùng bản bằng chứng được bảo vệ riêng nếu nhu cầu điều tra yêu cầu. Cấu hình redaction phải áp dụng cho log lỗi, retry, dead-letter queue và export.

Không tin timestamp hoặc actor do client khai báo. decided_at do máy chủ ra quyết định ghi; observed_at được lưu kèm nguồn xác nhận, không trình bày như sự thật do ứng dụng tự quan sát.

Nên theo dõi:

- Tuổi dữ liệu tại lúc quyết định và thời gian từ nhận đến áp dụng.
- Tỷ lệ hết hạn trong queue hoặc trong lúc chờ khóa.
- Phản hồi cũ đến sau attempt mới, duplicate và context mismatch.
- Clock skew bất thường, timestamp tương lai và lỗi parse.
- Cache trả dữ liệu không còn đủ điều kiện cho loại quyết định.
- Số operation ở CHECK_UNKNOWN hoặc RECONCILING và thời gian bị treo.

Metric không thay audit cấp đối tượng. Khi policy thay đổi, cần biết một quyết định đã áp dụng policy nào, không tính lại lịch sử bằng cấu hình hiện tại rồi cho rằng đó là điều hệ thống đã làm.

## 12. Kiểm thử tình huống tấn công logic

Không dùng thời gian thực và sleep dài để kiểm tra TTL. Tiêm clock có thể điều khiển, fake provider, queue thử nghiệm và barrier/latch cho race. Mỗi ca cần kiểm tra phản hồi API, trạng thái đơn, số hiệu ứng nghiệp vụ và bằng chứng audit.

| Tình huống | Cách thử | Điều cần khẳng định |
| --- | --- | --- |
| Replay đã hết hạn | Gửi lại ALLOW có chữ ký đúng sau deadline | Không cấp quyền mới, reason STALE |
| Replay trong hạn | Hai worker áp dụng cùng response đồng thời | Một lần chuyển trạng thái, không nhân đôi outbox |
| Sai tenant | Dùng response hợp lệ của tenant A cho B | Không đọc/sửa đơn B qua nội dung response |
| Sai số tiền/currency | Đổi input sau khi gửi check | Revision/digest mismatch; cần check mới |
| Sai người nhận | Giữ số tiền nhưng đổi beneficiary | Quyết định cũ mất hiệu lực |
| Đảo thứ tự | ALLOW attempt cũ đến sau DENY attempt mới | ALLOW cũ không ghi đè kết quả hiện hành |
| Chữ ký mới, dữ liệu cũ | issued_at mới nhưng observed_at quá tuổi | Không dùng tuổi chữ ký làm tuổi dữ liệu |
| Timestamp tương lai | observed_at hoặc signature time vượt giới hạn | Không coi tuổi âm là hợp lệ |
| Hạn nguồn quá dài | expires_at xa nhưng max_data_age ngắn | Policy local vẫn giới hạn |
| Biên hết hạn | Thử ngay trước, đúng và sau effective deadline | Hành vi nhất quán với dấu so sánh đã công bố |
| Chờ khóa | Nhận trước hạn, giữ khóa đến sau hạn | Kiểm tra lại sau khi lấy khóa |
| Chờ queue | Để job/outbox cũ được xử lý muộn | Không áp dụng quyết định chỉ vì lúc enqueue còn mới |
| Cache sliding TTL | Đọc/copy nhiều lần qua thời hạn gốc | Không gia hạn tuổi bằng lần đọc |
| Refresh thất bại | Nguồn lỗi sau khi entry hết hạn | Không đổi received_at/TTL để cấp quyền |
| Cache lẫn ngữ cảnh | Cùng customer ID ở hai tenant hoặc hai input | Không chia sẻ verdict sai phạm vi |
| Rollback khi tiêu thụ | Gây lỗi sau bước xử lý pending check | Đơn, consumption, audit/outbox cùng rollback |
| Response ID bất nhất | Cùng ID nhưng body khác | Chặn và ghi sự kiện bất nhất |
| Version nguồn hồi quy | Gửi version thấp hơn mốc đã nhận trong cùng miền | Không ghi đè bằng trạng thái cũ |
| Clock bị lùi | Điều khiển clock vượt ngưỡng tin cậy | Không kéo dài quyền dùng bằng chứng âm thầm |
| Commit ngoài chưa rõ | Nguồn thực hiện rồi làm mất response | RECONCILING, không retry bằng operation mới |
| Quyền bị thu hồi | Khóa tài khoản/grant khi check đang chạy | ALLOW bên ngoài không bỏ qua quyền hiện tại |
| Nguồn không có observed_at | Chỉ trả kết quả và HTTP Date | Không tự khẳng định độ mới dữ liệu không được bảo đảm |

Với kiểm thử duplicate sau commit, cố tình làm mất response trả về rồi gửi lại. Kết quả phải chỉ đọc lại hiệu ứng cũ, không kéo dài deadline cho một lần áp dụng mới.

Với kiểm thử cạnh tranh, xác nhận số hàng consumption, số lần chuyển trạng thái và số outbox event, không chỉ kiểm tra mã HTTP. Với thao tác bên ngoài, fake provider cần mô phỏng “đã thực hiện nhưng client timeout” để kiểm tra idempotency và reconciliation.

## 13. Phân tích một lỗi thực tế giả định

Một đội phát triển lưu kết quả kiểm tra rủi ro như sau:

~~~text
cache[customer_id] = {
    approved: true,
    checked_at: thời điểm đọc cache gần nhất
}
~~~

Khi checkout, họ chấp nhận nếu checked_at cách hiện tại dưới năm phút. Đoạn xử lý có ba vấn đề độc lập:

1. checked_at được cập nhật mỗi lần đọc nên kết quả cũ có thể sống mãi.
2. Cache key không có tenant, amount, beneficiary hoặc input revision.
3. Boolean approved không giữ request/attempt identity, nguồn và căn cứ thời gian.

Đặt TTL ngắn hơn không sửa được hai lỗi ràng buộc còn lại. Thêm chữ ký vào boolean cũng không khiến nó áp dụng được cho mọi đơn.

Một hướng sửa có thể gồm:

- Tạo pending check gắn đúng input và epoch.
- Giữ observed_at, thời hạn nguồn và metadata đã xác thực.
- Tính effective deadline theo policy máy chủ.
- Kiểm tra binding, quyền, state và freshness tại điểm quyết định.
- Áp dụng kết quả một lần trong transaction cùng audit/outbox.
- Dùng giao thức xác nhận/giữ chỗ khi bước thực hiện cần cam kết của nguồn.

Nếu đối tác không cung cấp bằng chứng tuổi dữ liệu, cần thay hợp đồng tích hợp hoặc chọn quy trình chỉ dựa trên những bảo đảm họ thật sự cung cấp. Không che khoảng trống đó bằng một field timestamp local.

## 14. Tiêu chí hoàn thành thiết kế

- Mỗi loại quyết định có policy freshness riêng, nguồn có thẩm quyền và hành vi khi chưa rõ kết quả.
- Phân biệt thời điểm quan sát, phát hành, ký, nhận và áp dụng; không đặt lại tuổi khi đọc cache hoặc retry.
- Phản hồi được ràng buộc với tenant, đối tượng, input, operation và attempt hiện hành.
- Response trùng không tạo thêm hiệu ứng; response cũ không thắng attempt mới.
- Kiểm tra sau thời gian chờ khóa/queue và nêu rõ điểm mà bảo đảm freshness được áp dụng.
- Thu hồi quyền hoặc thay input làm mất hiệu lực căn cứ cũ theo state machine.
- Không dùng TTL để thay cho reservation, precondition hay xác nhận của nguồn.
- Timeout ngoài hệ thống có đường idempotency và reconciliation.
- Audit đủ để dựng lại policy, deadline và quyết định mà không làm lộ bí mật.
- Kiểm thử bao phủ replay, biên thời gian, sai ngữ cảnh, cạnh tranh, cache và rollback.
