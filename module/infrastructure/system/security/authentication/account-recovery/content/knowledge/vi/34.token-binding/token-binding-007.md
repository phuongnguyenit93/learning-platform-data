# Binding token to risk decision

## 1. Vì sao token cần gắn với quyết định rủi ro?

Một token khôi phục có thể được phát hành sau khi máy chủ đánh giá ngữ cảnh và cho phép một bước cụ thể. **Binding token to risk decision** là việc giữ mối liên hệ có thể kiểm chứng giữa token với quyết định đó, bao gồm đối tượng, thao tác, điều kiện và thời gian hiệu lực.

Ví dụ, dịch vụ cho phép đặt lại mật khẩu của tài khoản A sau khi xác minh bằng chứng cần thiết và đánh giá ngữ cảnh hiện tại. Token được cấp không được dùng để:

- Khôi phục tài khoản B.
- Thay MFA trong khi quyết định chỉ cho phép đặt lại mật khẩu.
- Bỏ qua một bước xác minh bổ sung.
- Tiếp tục sử dụng quyết định đã hết hạn hoặc bị thu hồi.
- Mang kết quả rủi ro thấp của một yêu cầu sang yêu cầu khác.

Mối liên hệ cần thể hiện được:

```text
token
    -> quyết định cấp quyền cụ thể
    -> tài khoản + yêu cầu + thao tác
    -> bằng chứng và điều kiện đã được chấp nhận
    -> giới hạn thời gian và cơ chế vô hiệu hóa
```

OWASP mô tả xác thực thích ứng là việc điều chỉnh yêu cầu xác thực theo ngữ cảnh; các tín hiệu như IP hoặc đặc điểm thiết bị không thay thế bằng chứng xác thực. Xem [OWASP Authentication Cheat Sheet — Adaptive or Risk Based Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#adaptive-or-risk-based-authentication).

Các tên trường, trạng thái và thuật toán trong bài là một mô hình thiết kế minh họa cho khôi phục tài khoản, không phải một schema chuẩn bắt buộc.

## 2. Phân biệt tín hiệu, điểm số, quyết định và bằng chứng

Bốn khái niệm này có vai trò khác nhau:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Tín hiệu | Lịch sử thiết bị, thay đổi kênh liên hệ, số lần thử | Đầu vào có chất lượng và độ mới cần được đánh giá |
| Điểm hoặc mức rủi ro | Một điểm số hoặc nhãn theo mô hình nội bộ | Kết quả phân tích, cần chính sách diễn giải |
| Quyết định | Cho tiếp tục, yêu cầu bổ sung, tạm giữ, từ chối | Xác định bước nào được phép thực hiện |
| Bằng chứng đã xác minh | Recovery code hợp lệ, xác nhận qua phương thức được chấp nhận | Cơ sở xác minh theo chính sách khôi phục |

Một điểm rủi ro thấp không tự chứng minh người đang thao tác là chủ tài khoản. Nó cũng không tự cấp quyền thay thế yếu tố xác thực.

Có thể mô hình hóa quyết định:

```text
decision = evaluatePolicy(
    subject,
    recoveryRequest,
    requestedAction,
    verifiedEvidence,
    riskSignals,
    accountSecurityState
)
```

Kết quả không nên chỉ là `riskScore = 12`, vì ý nghĩa của số 12 còn phụ thuộc phiên bản mô hình, chiều thang điểm, ngưỡng và loại thao tác. Thành phần thực thi cần một kết luận rõ ràng cùng các điều kiện phải đáp ứng.

| Kết quả minh họa | Ý nghĩa |
| --- | --- |
| ALLOW | Cho phép đúng thao tác đã nêu khi các điều kiện còn hợp lệ |
| REQUIRE_MORE_EVIDENCE | Chưa cho phép hoàn tất; cần bằng chứng bổ sung được chấp nhận |
| HOLD | Tạm giữ theo quy trình có điều kiện tiếp tục rõ ràng |
| DENY | Không cho phép thao tác trong phạm vi quyết định này |

Nếu kết quả yêu cầu thêm bằng chứng, hệ thống có thể phát token chỉ cho phép hoàn tất challenge. Token đó không được có cùng quyền với token cho phép đặt lại credential.

Người mất MFA có thể không còn phương thức thông thường để xác minh lại. Chính sách cần một nhánh khôi phục đã được thiết kế cho trường hợp đó; không tự bỏ yêu cầu chứng minh danh tính, cũng không buộc người dùng lặp mãi một bước họ không còn khả năng thực hiện.

## 3. Một quyết định có thể ràng buộc cần chứa gì?

Quyết định phải đủ cụ thể để không bị dùng ngoài phạm vi. Một mô hình khái niệm:

```json
{
  "decisionId": "rd_demo_81",
  "decisionRevision": 1,
  "tenantId": "tenant_demo_1",
  "accountId": "account_demo_A",
  "recoveryRequestId": "request_demo_18",
  "action": "COMPLETE_PASSWORD_RESET",
  "outcome": "ALLOW",
  "evidenceSetRef": "evidence_demo_24",
  "contextDigest": "DIGEST_CUA_NGU_CANH_DA_CHUAN_HOA",
  "accountSecurityEpoch": 7,
  "policyVersion": "recovery-policy-demo-4",
  "modelVersion": "risk-model-demo-2",
  "evaluatedAt": "2026-01-01T03:00:00Z",
  "validUntil": "2026-01-01T03:05:00Z",
  "status": "CURRENT"
}
```

Tất cả ID và thời điểm trên là dữ liệu giả. Thời hạn năm phút chỉ phục vụ ví dụ, không phải mức khuyến nghị chung.

Những trường cần được hiểu đúng:

- `decisionId` xác định quyết định cụ thể; biết ID không đồng nghĩa có quyền sử dụng.
- `decisionRevision` phân biệt các lần thay đổi hoặc thay thế theo hợp đồng của hệ thống.
- `action` là thao tác đã được xét, không phải mọi hành động liên quan tài khoản.
- `evidenceSetRef` tham chiếu đến kết quả xác minh có thẩm quyền; một nhãn do client tự khai không đủ.
- `accountSecurityEpoch` ghi lại phiên bản trạng thái bảo mật quan trọng để kiểm tra lại khi sử dụng.
- `validUntil` là hạn dùng quyết định, độc lập với thời hạn của token.
- `policyVersion` và `modelVersion` giúp diễn giải, truy vết và áp dụng quy tắc tương thích.

Không cần sao chép toàn bộ dữ liệu thiết bị, địa chỉ IP hoặc tài liệu danh tính vào token. Nên giữ các dữ liệu nhạy cảm trong hệ thống được kiểm soát quyền truy cập và chỉ tham chiếu phần cần thiết.

### Context digest có tác dụng gì?

Máy chủ có thể tính digest trên một tập thuộc tính đã chuẩn hóa:

```text
contextDigest = Hash(canonicalEncode(
    tenantId,
    accountId,
    recoveryRequestId,
    action,
    targetReference,
    evidenceSetRevision,
    accountSecurityEpoch
))
```

Danh sách này là ví dụ. Cần chọn những thuộc tính quyết định quyền và quy định rõ giá trị rỗng, kiểu dữ liệu, thứ tự và ranh giới trường.

Digest giúp phát hiện hai ngữ cảnh không giống nhau. Nó không chứng minh ai tạo dữ liệu. Nếu client được tự thay cả ngữ cảnh lẫn digest, ràng buộc không có giá trị cấp quyền.

Việc đảm bảo nguồn gốc và tính toàn vẹn phải đến từ kho dữ liệu có thẩm quyền hoặc thông điệp được bảo vệ bằng cơ chế mật mã phù hợp.

## 4. Gắn token với quyết định ở phía máy chủ

Với token opaque, một bản ghi có thể giữ:

```text
RecoveryToken {
    tokenRecordId
    secretVerifier
    tenantId
    accountId
    recoveryRequestId
    purpose
    decisionId
    decisionRevision
    contextDigest
    accountSecurityEpoch
    expiresAt
    state
}
```

Client giữ bí mật token; máy chủ quản lý các thuộc tính cấp quyền. Khi xác minh token, dịch vụ truy xuất đúng quyết định mà bản ghi đã tham chiếu.

Một lỗi cần tránh:

```text
request:
    token = token_hop_le
    decisionId = mot_quyet_dinh_ALLOW_bat_ky
```

Nếu máy chủ chỉ kiểm tra rằng hai giá trị đều hợp lệ riêng lẻ, người gửi có thể ghép token của một quy trình với quyết định của quy trình khác.

Điều kiện đúng phải là:

```text
token.decision_id == decision.id
token.decision_revision == decision.revision

token.tenant_id == decision.tenant_id
token.account_id == decision.account_id
token.recovery_request_id == decision.recovery_request_id
token.purpose được decision.action cho phép

token.context_digest == decision.context_digest
```

Máy chủ lấy tham chiếu quyết định từ bản ghi token đã xác minh. Một trường `decisionId` do client gửi, nếu API cần có, chỉ được dùng sau khi đối chiếu với tham chiếu đó.

### Nếu quyết định đi qua dịch vụ khác

Dịch vụ phát hành token cần xác thực nguồn phản hồi, kiểm tra đúng request, chủ thể, hành động và thời hạn. Không chấp nhận một JSON `ALLOW` chỉ vì nó đến đúng endpoint callback.

Nếu dùng một assertion có chữ ký, bên nhận phải xác minh chữ ký, bên phát hành, bên nhận dự kiến, thời gian và toàn bộ thuộc tính liên kết. Payload mới được decode chưa phải dữ liệu đã xác minh.

Chữ ký bảo vệ assertion không bị sửa mà không bị phát hiện. Nó không tự giải quyết token dùng một lần, thu hồi quyết định hoặc ngữ cảnh đã thay đổi sau lúc ký.

## 5. Tách thời hạn token khỏi thời hạn quyết định

Một token có thể còn hạn trong khi quyết định cho phép nó đã hết hạn.

Ví dụ:

```text
09:00  đánh giá và tạo quyết định ALLOW
09:05  validUntil của quyết định
09:15  expiresAt của token
09:07  người dùng gửi token để hoàn tất
```

Chỉ kiểm tra `token.expiresAt` sẽ bỏ qua việc quyết định đã quá thời hạn được phép sử dụng.

Một lựa chọn thiết kế đơn giản là giới hạn token theo quyết định:

```text
token.expiresAt <= decision.validUntil
```

Nếu cần token sống lâu hơn để người dùng có thời gian nhận thông điệp, phải quy định rõ rằng đến lúc hoàn tất sẽ đánh giá lại và cấp quyền mới phù hợp. Không mặc định rằng token kéo dài hiệu lực của quyết định cũ.

Điều kiện thực thi có thể gồm:

```text
token còn hoạt động
AND token chưa hết hạn
AND decision còn được chấp nhận
AND decision.outcome == ALLOW
AND thời gian hiện tại < decision.validUntil
AND mọi ràng buộc đối tượng, thao tác và ngữ cảnh đều khớp
```

Thời gian phải lấy từ nguồn có thẩm quyền của hệ thống. Retry hoặc việc mở lại liên kết không được đặt lại `evaluatedAt` hay kéo dài `validUntil`.

Lưu phiên bản chính sách không có nghĩa mọi lần triển khai chính sách mới đều phải vô hiệu hóa toàn bộ token cũ. Hệ thống cần quy tắc tương thích cụ thể và cách thu hồi khẩn cấp khi cần. Nếu một phiên bản không còn được chấp nhận, endpoint sử dụng token phải thực thi điều đó.

## 6. Khi nào phải xem xét lại quyết định?

Quyết định chỉ có ý nghĩa trong ngữ cảnh mà nó đã xét. Một số thay đổi có thể làm mất hiệu lực cơ sở cấp quyền:

| Thay đổi | Vấn đề cần xem xét |
| --- | --- |
| Kênh khôi phục vừa bị sửa | Bằng chứng dựa trên kênh cũ hoặc mới có còn được chấp nhận không? |
| Một yếu tố xác thực bị báo mất hoặc lộ | Quyết định có đang dựa trên yếu tố đó không? |
| Tài khoản bị đánh dấu đang bị chiếm đoạt | Có cần dừng quyền khôi phục đã cấp không? |
| Mục đích chuyển từ đổi mật khẩu sang thay MFA | Quyết định cũ chưa xét thao tác mới |
| Yêu cầu được mở lại hoặc thay đổi đối tượng phụ | Phạm vi giao dịch có còn khớp không? |
| Bằng chứng bổ sung hết hạn hoặc bị thu hồi | Điều kiện ALLOW còn được đáp ứng không? |
| Quyết định bị thay thế bằng kết quả mới | Token cũ có đang tham chiếu phiên bản không còn hiện hành không? |

Các thay đổi cần vô hiệu hóa phải được quy định bởi chính sách, cùng cách cập nhật phiên bản hoặc trạng thái có thẩm quyền. Không chỉ ghi một cảnh báo rồi để endpoint hoàn tất bỏ qua nó.

### Tín hiệu thay đổi không đồng nghĩa phải từ chối ngay

Người khôi phục có thể dùng điện thoại mới, chuyển từ Wi-Fi sang mạng di động hoặc đang ở một địa điểm khác. Đây là tình huống bình thường khi họ mất thiết bị xác thực.

Chính sách cần phân biệt:

- Thay đổi làm mất ràng buộc quyền, như đổi tài khoản đích hoặc mục đích.
- Thay đổi bằng chứng quan trọng, như thu hồi phương thức vừa dùng để xác minh.
- Tín hiệu ngữ cảnh cần đánh giá lại, như IP khác trước.
- Tín hiệu yếu hoặc không đáng tin, không đủ để tự kết luận.

Nếu muốn ràng buộc quyền với thiết bị bằng mật mã, cần cơ chế chứng minh quyền giữ khóa hoặc một giao thức phù hợp. So sánh User-Agent hay fingerprint trình duyệt không tạo ra cùng một bảo đảm.

## 7. Kiểm tra ràng buộc tại điểm thực hiện thay đổi

Một lỗi thường gặp là chỉ hỏi risk engine lúc phát hành token. Vài phút sau, endpoint hoàn tất chỉ kiểm tra token còn hạn rồi đổi credential.

Máy chủ cần một điểm kiểm soát cuối gắn với thao tác ghi. OWASP cũng khuyến nghị kiểm tra việc cấp quyền trước khi thực thi giao dịch để hạn chế bỏ qua bước và lỗi TOCTOU. Xem [OWASP Transaction Authorization Cheat Sheet — Final control gate](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html#28-system-should-check-each-transaction-execution-and-make-sure-it-has-been-properly-authorized).

Mã giả sau giả định token, yêu cầu, trạng thái tài khoản và quyết định có thẩm quyền cùng nằm trong một database hỗ trợ giao dịch:

```text
completeRecovery(rawToken, requestedAction):
    parse và giới hạn đầu vào
    chuẩn bị dữ liệu thay đổi theo chính sách của thao tác

    BEGIN TRANSACTION

    đọc và khóa các bản ghi liên quan
        theo thứ tự khóa thống nhất
    lấy thời gian có thẩm quyền cho điểm kiểm soát cuối

    xác minh bí mật token
    kiểm tra token ACTIVE và chưa hết hạn

    decision = đọc từ token.decisionId + token.decisionRevision
    kiểm tra decision còn được chấp nhận và chưa hết hạn
    kiểm tra decision.outcome == ALLOW

    kiểm tra token, decision và request khớp:
        tenant, account, request, purpose, contextDigest
    kiểm tra requestedAction thuộc đúng phạm vi đã cấp
    kiểm tra các bằng chứng bắt buộc còn hợp lệ
    kiểm tra phiên bản bảo mật và quy tắc chính sách hiện hành
    kiểm tra request chưa hoàn tất hoặc bị hủy

    thực hiện đúng thay đổi đã được cho phép
    đánh dấu token CONSUMED
    đánh dấu request hoàn tất theo hợp đồng của quy trình
    vô hiệu hóa các quyền liên quan theo chính sách
    ghi audit và ý định thông báo vào outbox

    COMMIT
```

Đây là mã giả mô tả ranh giới nhất quán. Nó không thay thế các chi tiết triển khai như kiểm tra số dòng cập nhật, thứ tự khóa, xử lý rollback và giới hạn thời gian giao dịch.

Nếu hai token cùng tham chiếu một quyết định và một yêu cầu, kiểm tra từng token là chưa đủ để bảo đảm yêu cầu chỉ hoàn tất một lần. Trạng thái yêu cầu hoặc ràng buộc cấp quyền tương ứng cũng phải được tuần tự hóa.

Nếu một giao dịch khác đang thu hồi quyết định, hai thao tác cần được sắp thứ tự theo trạng thái có thẩm quyền. Một lần hoàn tất được xếp trước thu hồi khác với một lần tiếp tục dùng quyền sau khi thu hồi đã có hiệu lực.

Các việc như gửi email hoặc xử lý phiên ở dịch vụ khác có thể cần cơ chế phối hợp riêng. Việc ghi outbox không tự chứng minh mọi phiên cũ đã bị vô hiệu hóa ngay tại thời điểm commit.

## 8. Quyết định mới, step-up và hệ thống phân tán

### Hoàn tất bằng chứng bổ sung

Một quy trình minh họa:

```text
decision-1: REQUIRE_MORE_EVIDENCE
    -> chỉ cho phép bước cung cấp bằng chứng

bằng chứng bổ sung được xác minh

decision-2: ALLOW cho COMPLETE_MFA_REPLACEMENT
    -> cấp quyền phù hợp với quyết định mới
```

Không để client đổi `outcome` của decision-1 thành `ALLOW`. Kết quả bổ sung phải được máy chủ liên kết đúng challenge, yêu cầu và tài khoản, rồi đi qua chính sách đánh giá tương ứng.

Một lựa chọn dễ kiểm soát là phát một token mới cho decision-2, đánh dấu quyền cũ bị thay thế và giữ dấu vết liên hệ giữa hai quyết định. Việc cấp lại không được tự mở rộng hạn tuyệt đối của cả yêu cầu khôi phục.

Nếu hệ thống cho phép cập nhật ràng buộc của token hiện có, đó phải là một chuyển trạng thái được kiểm soát với kiểm tra phiên bản và audit đầy đủ. Không đổi `decisionId` âm thầm để một token cũ trở thành quyền rộng hơn.

### Gọi risk engine ở ngoài database

Trong kiến trúc phân tán, dịch vụ khôi phục có thể hỏi risk engine trước khi mở giao dịch ghi. Kết quả cần mang định danh, phạm vi, phiên bản trạng thái đầu vào và thời hạn rõ ràng.

Tại giao dịch ghi, dịch vụ có thể đối chiếu phiên bản bảo mật với bản ghi tài khoản hiện tại. Nếu phiên bản đã khác, kết quả đánh giá không còn khớp ngữ cảnh và cần xử lý lại theo chính sách.

Tuy nhiên, khóa bản ghi tài khoản ở database local không khóa mọi thay đổi ở risk engine từ xa. Một kết quả vừa được kiểm tra vẫn có thể bị thu hồi tại hệ thống khác.

Kiến trúc phải lựa chọn hợp đồng nhất quán phù hợp, chẳng hạn:

- Một nơi có thẩm quyền cùng quản lý việc chấp nhận quyết định và hoàn tất quyền.
- Một giao thức xác nhận và tiêu thụ quyền dùng một lần có thể phối hợp với thao tác đích.
- Một khoảng chấp nhận hữu hạn được quy định rõ, cùng giới hạn độ trễ thu hồi mà hệ thống chấp nhận.

Không gọi một cache quyết định là nguồn chuẩn rồi tuyên bố có hiệu lực thu hồi tức thời. Nếu đường truyền cập nhật bị trễ, khả năng quan sát thay đổi cũng bị giới hạn.

### Quyết định đến sai thứ tự

Nếu message ALLOW cũ đến sau message thu hồi hoặc thay thế, nó không được làm sống lại quyền cũ. Consumer phải dùng định danh, phiên bản và quy tắc chuyển trạng thái, thay vì áp dụng kết quả theo thứ tự message tình cờ được nhận.

Audit hoặc projection phục vụ giao diện có thể cập nhật bất đồng bộ. Điểm thực thi khôi phục phải đáp ứng hợp đồng cấp quyền mà hệ thống đã chọn.

## 9. Các lỗi triển khai làm mất ràng buộc

### Cache quá rộng

Các khóa cache như `risk:account-A = ALLOW` có thể làm một quyết định của yêu cầu này bị dùng cho một yêu cầu khác hoặc cho thao tác nhạy cảm hơn.

Khóa cache và dữ liệu lưu phải phản ánh đầy đủ phạm vi cần thiết: đối tượng, request, action, phiên bản quyết định và những phiên bản ngữ cảnh liên quan. TTL cache không được vượt quá thời hạn còn lại của quyền được cache.

Ngay cả cache có khóa đúng vẫn cần cơ chế đáp ứng yêu cầu thu hồi. Cache chính xác về phạm vi không đồng nghĩa luôn đủ mới.

### Cho client tự khai tín hiệu có thẩm quyền

Không tin trực tiếp các trường như:

```json
{
  "riskLevel": "LOW",
  "identityVerified": true,
  "requiredEvidenceComplete": true
}
```

Máy chủ cần biết nguồn gốc từng tín hiệu. Ví dụ, header địa chỉ IP chuyển tiếp chỉ được diễn giải trong chuỗi proxy tin cậy đã cấu hình; một giá trị tự gửi từ Internet không có cùng độ tin cậy.

Không đưa giá trị mặc định rủi ro thấp vào các trường bị thiếu hoặc parse lỗi. Dữ liệu không xác định cần được xử lý theo chính sách cho dữ liệu không xác định.

### Tự cho phép khi dịch vụ rủi ro lỗi

Timeout không phải một quyết định ALLOW. Nếu không thể xác nhận điều kiện cần thiết, luồng phải tạm giữ, thử lại có giới hạn hoặc chuyển sang phương án khôi phục đã được phê duyệt.

Một cơ chế dự phòng, nếu có, cần được thiết kế trước với phạm vi, bằng chứng và giới hạn rõ ràng. Không hạ yêu cầu chỉ vì một API nội bộ đang lỗi.

### Bỏ qua quyết định qua công cụ hỗ trợ

Một thao tác hỗ trợ thủ công cần tạo quyết định có chủ thể thực hiện, lý do, phạm vi, thời hạn và các phê duyệt cần thiết theo chính sách. Một cờ `skipRisk=true` không được kiểm soát có thể trở thành đường bỏ qua toàn bộ mô hình.

### Ghi quá nhiều dữ liệu nhạy cảm

Audit có thể ghi `decisionId`, phiên bản, token record ID, request ID, action, mã kết quả và lý do nội bộ có cấu trúc. Không ghi raw token, OTP, cookie hoặc toàn bộ hồ sơ danh tính vào log.

Không trả chi tiết ngưỡng chống gian lận hoặc dữ liệu tài khoản ra thông báo lỗi công khai. Giao diện chỉ cần đủ thông tin để người dùng thực hiện bước hợp lệ tiếp theo.

## 10. Ví dụ: ngữ cảnh thay đổi trước khi thay MFA

Giả sử một người mất thiết bị chứa yếu tố xác thực và bắt đầu quy trình thay MFA:

```text
10:00  request-18 được tạo cho account-A
10:02  bằng chứng cần thiết được xác minh
10:03  decision-81 cho phép thay đúng yếu tố đã được xét
10:03  token-42 gắn với decision-81, accountSecurityEpoch = 7
10:04  một sự kiện bảo mật quan trọng làm epoch tăng lên 8
10:05  token-42 được gửi để hoàn tất
```

Tại 10:05, secret của token có thể đúng và token vẫn còn hạn. Tuy nhiên, phiên bản bảo mật không còn khớp quyết định.

Hệ thống cần dừng việc hoàn tất dựa trên decision-81 và chuyển sang xử lý tương ứng: đánh giá lại, yêu cầu bằng chứng khác, tạm giữ hoặc từ chối theo chính sách. Không được dùng riêng cờ `tokenValid=true` để tiếp tục.

Nếu đánh giá mới cho phép tiến hành, quyền được cấp phải liên kết với quyết định mới và ngữ cảnh hiện tại. Nếu kết quả mới yêu cầu thêm bằng chứng, quyền cũ không được dùng để bỏ qua bước đó.

Cơ chế này cũng có giới hạn: nếu một sự kiện nguy hiểm chưa được hệ thống phát hiện hoặc chưa được truyền đến nguồn có thẩm quyền theo hợp đồng, phép so sánh epoch không tự biết về sự kiện đó. Cần đánh giá bảo đảm của cả chuỗi thu thập tín hiệu, quyết định và thực thi.

## 11. Hợp đồng cần thể hiện trong thiết kế

| Tình huống | Hành vi cần được quy định |
| --- | --- |
| Token của A ghép với quyết định của B | Từ chối vì sai đối tượng |
| Token đúng request nhưng sai action | Từ chối mở rộng phạm vi |
| Token còn hạn, quyết định hết hạn | Không hoàn tất dựa trên quyết định cũ |
| Kết quả REQUIRE_MORE_EVIDENCE | Chỉ cho phép bước có phạm vi phù hợp |
| Bằng chứng từng hợp lệ đã bị thu hồi | Không dùng lại điều kiện cũ để cấp quyền |
| Chính sách có phiên bản mới | Áp dụng quy tắc tương thích hoặc thu hồi đã định |
| Mạng của người dùng thay đổi | Xét theo độ tin cậy và chính sách, không tự đồng nhất với tấn công |
| Message ALLOW cũ đến muộn | Không khôi phục quyết định đã bị thay thế |
| Risk engine timeout | Không tự coi là ALLOW |
| Hai request cùng hoàn tất | Chỉ cho một lần thực hiện quyền một lần thành công |
| Người dùng cần nhánh khôi phục khác | Đi qua quy trình được chấp nhận, không bỏ kiểm chứng danh tính |

Một token gắn với quyết định rủi ro cần trả lời được ba câu hỏi: **quyết định nào đã cấp quyền này, quyền đó có đúng với thao tác hiện tại không, và cơ sở cấp quyền còn được chấp nhận tại điểm thực thi không**. Lưu `decisionId` chỉ là bước đầu; giá trị bảo mật đến từ việc thực thi đầy đủ mối liên hệ đó.
