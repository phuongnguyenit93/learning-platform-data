# Token replacement event — Sự kiện thay thế token khôi phục

## 1. Thay thế token là thay đổi quyền sử dụng

Trong luồng khôi phục tài khoản, **token replacement event** ghi nhận việc hệ thống đưa một token mới vào sử dụng để thay cho token trước đó trong một phạm vi đã xác định. Sự kiện này phải phản ánh một thay đổi trạng thái đã được chốt ở máy chủ. Việc tạo một chuỗi ngẫu nhiên hoặc gửi thêm email chưa đủ để kết luận token đã được thay thế.

Ví dụ, người dùng đang có liên kết khôi phục chứa token T1. Họ yêu cầu cấp liên kết mới và hệ thống chấp nhận thay T1 bằng T2. Với chính sách chỉ cho phép một token hiện hành trong luồng, sau khi giao dịch thay thế hoàn tất:

- T1 không còn được dùng để nhận quyền khôi phục, dù thời hạn ghi trên T1 chưa hết.
- T2 có bí mật mới, thời hạn riêng và cùng phạm vi quyền đã được cho phép.
- Máy chủ lưu được quan hệ T1 → T2 phục vụ điều tra mà không ghi bí mật của hai token vào nhật ký.
- Một yêu cầu gửi lặp do mất kết nối không tự tạo thêm T3.

Điều cần bảo vệ là quyền đặt lại mật khẩu hoặc tiếp tục một bước xác minh cụ thể. Thay token không tự chứng minh người yêu cầu là chủ tài khoản, không tự cấp quyền bỏ MFA và không tự cho phép đăng ký passkey mới.

OWASP yêu cầu token đặt lại mật khẩu được sinh bằng nguồn ngẫu nhiên mật mã, lưu an toàn, có thời hạn, dùng một lần và có biện pháp chống yêu cầu tự động quá mức. Đây là các thuộc tính nền để thiết kế vòng đời token. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Mô hình sự kiện, trạng thái và giao dịch dưới đây là một thiết kế minh họa cho khôi phục tài khoản; không phải schema bắt buộc do OWASP quy định.

## 2. Phân biệt những thao tác dễ bị gọi chung là “gửi lại”

| Thao tác | Bí mật token thay đổi? | Trạng thái token trước | Ý nghĩa |
| --- | --- | --- | --- |
| Thử gửi lại cùng thông điệp | Không | Giữ nguyên nếu còn hợp lệ | Khắc phục lỗi chuyển phát của một lần cấp đã có |
| Thay token đang hiện hành | Có | Chuyển sang không được sử dụng | Cấp bí mật mới trong phạm vi được phép |
| Gia hạn thời hạn token | Có thể không | Có thể vẫn hiện hành | Tăng thời gian tồn tại của quyền cũ; cần chính sách riêng |
| Bắt đầu một luồng khôi phục mới | Thường có | Theo chính sách giữa các luồng | Tạo ngữ cảnh mới, không chỉ đổi token |
| Tiêu thụ token | Không tạo token thay thế theo mặc định | Đã dùng | Đổi bằng chứng sở hữu token thành hành động hoặc quyền hạn chế |
| Thu hồi do nghi lộ bí mật | Không nhất thiết có token mới | Bị thu hồi | Chặn quyền cũ; chỉ cấp tiếp nếu điều kiện phục hồi còn phù hợp |

Một nút “Gửi lại” trên giao diện phải được ánh xạ rõ sang hành vi ở máy chủ. Nếu nó chỉ thử lại tác vụ gửi, không nên ghi sự kiện token đã được thay thế. Nếu nó cấp bí mật mới, người dùng cần hiểu liên kết cũ có thể mất hiệu lực.

Khi máy chủ chỉ lưu giá trị kiểm chứng một chiều, nó không thể lấy lại token gốc từ giá trị đó để gửi lại. Khả năng thử lại chuyển phát phải được thiết kế ngay từ lúc cấp token, hoặc hệ thống phải thực hiện một lần cấp mới có kiểm soát.

## 3. Xác định chính xác phạm vi thay thế

Một tài khoản có thể đồng thời có nhiều công việc liên quan đến khôi phục. Ví dụ:

- Luồng đặt lại mật khẩu.
- Luồng xác minh bổ sung khi mất ứng dụng MFA.
- Luồng xử lý mất thiết bị chứa passkey.
- Một yêu cầu hỗ trợ đang được xem xét thủ công.

Token của các luồng này không được tự chuyển đổi quyền cho nhau. Trước khi thay token, máy chủ cần xác định phạm vi từ dữ liệu tin cậy, chẳng hạn:

~~~text
scope = tenant_id + account_id + purpose + recovery_flow_id
~~~

Trong đó:

- `tenant_id` giữ ranh giới giữa các tổ chức nếu hệ thống có nhiều tenant.
- `account_id` là tài khoản đích do máy chủ xác định.
- `purpose` là hành động hoặc bước xác minh được phép.
- `recovery_flow_id` phân biệt những yêu cầu khôi phục khác nhau.

Một định danh luồng khó đoán giúp giảm khả năng dò tìm, nhưng bản thân nó không thay thế quyết định cho phép thay token. Hệ thống vẫn phải xét tuyến khôi phục, bằng chứng hiện có và chính sách chống lạm dụng.

Cần công bố thêm chính sách **giữa các luồng**. Chỉ bảo đảm một token trong từng luồng chưa đồng nghĩa tài khoản chỉ có một token đặt lại mật khẩu trên toàn hệ thống. Nếu muốn “token mới nhất cho tài khoản và mục đích này là token duy nhất hợp lệ”, ranh giới đồng bộ phải bao trùm tất cả luồng thuộc phạm vi đó.

Không dùng câu lệnh “vô hiệu hóa tất cả token của account” cho mọi lần gửi lại nếu yêu cầu thực tế chỉ thay một token của một luồng. Ngược lại, cũng không chỉ thay token trong một luồng khi một sự cố yêu cầu thu hồi toàn bộ quyền khôi phục của tài khoản.

## 4. Các bất biến của mô hình minh họa

Bài này dùng chính sách: **mỗi luồng đang mở có tối đa một token hiện hành và không có thời gian chồng lấn sau khi thay thế**.

Các bất biến cần giữ gồm:

1. Một lần thay thành công làm token cũ mất quyền và đưa token mới vào trạng thái hiện hành trong cùng một giao dịch.
2. Token mới có bí mật độc lập, không lấy từ token cũ bằng phép biến đổi có thể đoán.
3. Token mới không được mở rộng mục đích, tài khoản, kênh nhận hoặc mức quyền của luồng.
4. Token đã thay thế không quay lại trạng thái hiện hành vì gửi email thất bại.
5. Yêu cầu retry có cùng danh tính thao tác không làm tăng thế hệ token lần nữa.
6. Mọi lần đổi token vẫn chịu thời hạn tổng và ngân sách chống lạm dụng của luồng.
7. Việc chấp nhận token dựa trên trạng thái hiện hành ở máy chủ, không chỉ dựa vào thông báo sự kiện hoặc dữ liệu cache.

Một hệ thống có thể chọn cho phép nhiều token đồng thời trong một phạm vi được giới hạn. Khi đó, nó phải định nghĩa rõ số lượng, thời gian chồng lấn và cách tiêu thụ hoặc thu hồi cả nhóm. Không được tuyên bố “token cũ đã bị thay thế ngay” trong khi vẫn âm thầm chấp nhận nó.

Nếu lý do thay là nghi token cũ bị lộ, giữ token đó hợp lệ trong một khoảng chồng lấn có thể làm mất mục tiêu của thao tác thay thế.

## 5. Trạng thái token và trạng thái luồng

Một mô hình token tối giản có thể sử dụng:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Cấp và chốt thành công
    ACTIVE --> REPLACED: Chốt token kế tiếp
    ACTIVE --> CONSUMED: Đổi lấy quyền hoặc hành động
    ACTIVE --> REVOKED: Thu hồi theo chính sách
    ACTIVE --> EXPIRED: Hết thời hạn
~~~

`REPLACED`, `CONSUMED`, `REVOKED` và `EXPIRED` đều không được chấp nhận để khôi phục, nhưng nguyên nhân khác nhau. Phân biệt chúng giúp điều tra đúng sự cố thay vì gom mọi trường hợp vào “mã sai”.

Không cần đợi một tác vụ nền đổi trạng thái thành `EXPIRED` mới từ chối token hết hạn. Điều kiện thời gian phải được kiểm tra trực tiếp lúc chấp nhận:

~~~text
token.state == ACTIVE
and server_now < token.expires_at
and token.id == flow.current_token_id
and token.generation == flow.current_generation
and flow.state == OPEN
and scope_and_policy_still_allow_the_action
~~~

Trạng thái luồng cần được quản lý riêng. Ví dụ:

| Trạng thái luồng | Có thay token bằng lệnh thông thường? |
| --- | --- |
| OPEN, token hiện hành còn hiệu lực | Có thể, nếu chính sách cho phép |
| OPEN nhưng token đã hết hạn | Đi theo nhánh cấp tiếp hoặc bắt đầu lại đã định nghĩa |
| REDEEMED, đã tạo quyền khôi phục hạn chế | Không tự mở lại bằng thao tác gửi lại |
| COMPLETED | Không |
| CANCELLED hoặc bị chặn vì rủi ro | Không, cho đến khi có quyết định hợp lệ khác |

Trong ví dụ của bài, lệnh thay thế chỉ áp dụng cho token hiện hành còn hiệu lực trong luồng `OPEN`. Token đã hết hạn được xử lý bằng nhánh cấp tiếp hoặc luồng mới, thay vì sửa lịch sử để làm như token cũ chưa hết hạn.

## 6. Lưu dữ liệu đủ để giải thích sự thay thế

Bản ghi token có thể chứa:

~~~yaml
token_id: tok_b
flow_id: flow_42
generation: 8
purpose: PASSWORD_RESET
state: ACTIVE
verifier: "<gia-tri-kiem-chung; khong-phai-token-goc>"
issued_at: "2026-11-23T03:00:00Z"
expires_at: "2026-11-23T03:10:00Z"
replaces_token_id: tok_a
replaced_by_token_id: null
~~~

Các định danh và thời hạn trên chỉ để minh họa. Chúng không phải cấu hình thời hạn phù hợp cho mọi hệ thống.

Luồng tương ứng giữ ít nhất:

~~~yaml
flow_id: flow_42
state: OPEN
current_token_id: tok_b
current_generation: 8
revision: 19
absolute_deadline: "2026-11-23T03:20:00Z"
~~~

Hai bộ đếm có vai trò khác nhau:

- `generation` tăng khi đổi token hiện hành.
- `revision` tăng khi aggregate luồng có thay đổi trạng thái liên quan, bao gồm thay token, tiêu thụ hoặc hủy.

Không dùng `generation` như phiên bản duy nhất cho mọi sự kiện. Một luồng có thể bị hủy sau khi cấp thế hệ 8 mà không có thế hệ 9; consumer vẫn cần nhận ra trạng thái hủy mới hơn.

Phạm vi tài khoản, tenant, mục đích, phương thức xác minh và kênh nhận cần được ràng buộc trong dữ liệu máy chủ. Nếu client gửi thêm những trường này, chúng phải được đối chiếu; không lấy chúng làm nguồn chuẩn thay cho bản ghi.

## 7. Sự kiện phải mô tả một thay đổi đã commit

Một sự kiện không chứa bí mật có thể có dạng:

~~~json
{
  "event_id": "evt_719",
  "event_type": "RecoveryTokenReplaced",
  "schema_version": 1,
  "flow_id": "flow_42",
  "flow_revision": 19,
  "purpose": "PASSWORD_RESET",
  "previous_token_id": "tok_a",
  "replacement_token_id": "tok_b",
  "previous_generation": 7,
  "replacement_generation": 8,
  "reason": "USER_REQUESTED_NEW_LINK",
  "command_id": "cmd_58",
  "occurred_at": "2026-11-23T03:00:00Z"
}
~~~

Các trường trả lời những câu hỏi khác nhau:

| Trường | Câu hỏi được giải đáp |
| --- | --- |
| `event_id` | Đây có phải thông điệp đã xử lý rồi không? |
| `command_id` | Lần thay này xuất phát từ thao tác nào? |
| `flow_id` | Thay đổi thuộc luồng nào? |
| `flow_revision` | Thay đổi này đứng trước hay sau trạng thái đã biết? |
| Cặp token ID | Token nào thay cho token nào? |
| Cặp generation | Phiên bản token tăng như thế nào? |
| `reason` | Vì sao chính sách đã chấp nhận thay? |
| `occurred_at` | Thời điểm thay đổi được ghi nhận theo đồng hồ máy chủ |

Không đưa token gốc, URL đầy đủ chứa token, giá trị kiểm chứng hoặc dữ liệu xác minh danh tính vào sự kiện này. Ngay cả ID nội bộ không phải bí mật token vẫn cần được giới hạn quyền truy cập và thời gian lưu.

Đặc biệt, `RecoveryTokenReplaced` không phải lệnh cho một dịch vụ khác “hãy bắt đầu vô hiệu hóa token cũ khi nhận được”. Theo mô hình đang xét, việc vô hiệu hóa đã hoàn tất trong kho trạng thái chuẩn trước khi sự kiện được phát ra. Consumer có thể cập nhật lịch sử, gửi thông báo hoặc làm mới projection, nhưng độ trễ của chúng không được kéo dài quyền của T1.

## 8. Chốt thay thế bằng giao dịch nguyên tử

Một cách triển khai là dùng bản ghi luồng làm điểm đồng bộ chung cho các thao tác thay, tiêu thụ và hủy. Mã giả dưới đây chỉ mô tả ranh giới nghiệp vụ; nó chưa phải mã dịch vụ hoàn chỉnh.

~~~text
replaceCurrentToken(serverContext, command):
    enforceTrafficAndAbuseControls(serverContext, command)

    allowedScope = resolveAllowedRecoveryScope(serverContext, command)
    requireReplacementAllowedByPolicy(allowedScope, command)

    newSecret = generateCryptographicallyRandomSecret()
    newVerifier = deriveVerifier(newSecret)
    newTokenId = generateIndependentTokenId()

    transaction:
        flow = lockFlowInAuthoritativeStore(allowedScope.flowId)

        previous = findCommandReceipt(flow.id, command.commandId)
        if previous exists:
            requireSameAuthorizedContextAndRequestFingerprint(previous, command)
            return previous.nonSecretOutcome

        require flow.state == OPEN
        require serverNow() < flow.absoluteDeadline
        require flow.currentGeneration == command.expectedGeneration

        oldToken = lockToken(flow.currentTokenId)
        require oldToken.state == ACTIVE
        require serverNow() < oldToken.expiresAt
        require oldToken.generation == flow.currentGeneration
        requireCurrentPolicyAndScopeStillAllowReplacement(flow, command)

        newExpiry = min(
            serverNow() + configuredTokenLifetime,
            flow.absoluteDeadline
        )
        require newExpiry > serverNow()

        markReplaced(oldToken, newTokenId)
        insertActiveToken(
            newTokenId,
            newVerifier,
            flow.currentGeneration + 1,
            newExpiry,
            oldToken.id,
            allowedScope
        )
        advanceCurrentTokenAndFlowRevision(flow, newTokenId)

        deliveryRef = persistProtectedDeliveryEnvelope(
            newSecret,
            approvedDestinationSnapshot(flow),
            newTokenId,
            newExpiry
        )
        saveDeliveryJobToOutbox(deliveryRef, flow.id, flow.revision)
        saveReplacementEventToOutbox(withoutSecrets())
        saveCommandReceipt(command, nonSecretAcceptedOutcome())

    return nonSecretAcceptedOutcome()
~~~

Những điểm cần chú ý:

- Lưu token mới, đánh dấu token cũ, đổi con trỏ hiện hành, ghi receipt và outbox nằm trong cùng ranh giới commit.
- Việc cho phép thay phải được kiểm tra lại với trạng thái hiện hành bên trong giao dịch; kết quả kiểm tra trước đó có thể đã cũ.
- Hai thao tác cùng nhắm vào một thế hệ phải cạnh tranh ở cùng điểm đồng bộ. Với `expectedGeneration`, chỉ thao tác phù hợp với phiên bản hiện tại được chốt.
- Bí mật được tạo trước nhưng giao dịch thất bại thì không được gửi hoặc chấp nhận như token đã cấp.
- Không thực hiện cuộc gọi đến nhà cung cấp email trong khi giữ khóa cơ sở dữ liệu.

Receipt cho idempotency cần gắn với đúng ngữ cảnh được cho phép, luồng, loại thao tác và nội dung yêu cầu. Một `command_id` do client gửi không phải quyền truy cập receipt của người khác.

Khi nhận lại cùng yêu cầu, trả kết quả không bí mật đã lưu hoặc trạng thái phù hợp; không tạo token mới chỉ vì ứng dụng không còn giữ token gốc trong bộ nhớ. Nếu token của thao tác đó đã bị thay tiếp, phản hồi retry cũng không được tuyên bố token cũ hiện vẫn hợp lệ.

Nếu phạm vi duy nhất là “một token trên toàn bộ account và purpose”, khóa một flow riêng lẻ là chưa đủ. Cần một bản ghi điều phối hoặc ràng buộc tương ứng cho chính phạm vi rộng hơn đó.

## 9. Cuộc đua giữa thay thế và tiêu thụ token

Giả sử T1 là token hiện hành và hai yêu cầu đến gần như cùng lúc:

- A muốn dùng T1 để nhận quyền đặt lại mật khẩu.
- B muốn thay T1 bằng T2.

Nếu A chỉ kiểm tra T1 trước giao dịch, còn B chỉ sửa trạng thái token mà không phối hợp với A, cả hai có thể dựa vào một snapshot đã lỗi thời.

Với điểm đồng bộ chung, có hai kết quả rõ ràng:

### A tiêu thụ trước

A khóa trạng thái hiện hành, kiểm chứng bí mật và các điều kiện, tiêu thụ T1 rồi chuyển luồng sang trạng thái đã đổi token lấy quyền hạn chế. B sau đó thấy luồng không còn `OPEN` và không được tự mở lại để cấp T2.

Nếu quy trình cần bắt đầu lại, nó phải đi qua thao tác được thiết kế riêng với chính sách cho quyền đã cấp trước đó.

### B thay thế trước

B chốt T1 thành `REPLACED` và T2 thành token hiện hành. A kiểm tra trạng thái dưới cùng cơ chế đồng bộ rồi thấy T1 không còn hợp lệ, nên không cấp quyền.

Việc A đã tính ra digest đúng của T1 trước đó không làm T1 còn quyền sử dụng. Biết đúng bí mật và được phép tiêu thụ tại thời điểm hiện tại là hai điều kiện riêng.

~~~text
Biết đúng bí mật T1
        +
T1 vẫn hiện hành và được phép sử dụng lúc chốt
        +
Tiêu thụ thành công theo điều kiện đồng thời
        =
Có thể cấp quyền khôi phục trong phạm vi đã duyệt
~~~

Ràng buộc tương tự phải áp dụng cho thao tác hủy luồng hoặc thu hồi vì rủi ro. Chỉ đồng bộ “thay với thay” mà bỏ qua “thay với tiêu thụ” vẫn để lại khe hở.

## 10. Gửi token mới mà không làm sai trạng thái đã chốt

Gửi email hoặc SMS là tác vụ ngoài giao dịch cơ sở dữ liệu. Nó có thể lỗi, bị lặp hoặc đến sai thứ tự. Outbox giúp lưu ý định gửi cùng với thay đổi nghiệp vụ để tác vụ có thể được thử lại sau commit.

Có một vấn đề phải giải quyết rõ: dịch vụ chuyển phát cần token gốc, trong khi bản ghi xác minh chỉ nên giữ giá trị kiểm chứng.

Một phương án là giữ token trong **delivery envelope được mã hóa**, có quyền đọc hẹp và thời gian sống ngắn. Outbox chỉ chứa tham chiếu đến envelope. Khóa giải mã không nằm chung với dữ liệu mã hóa theo cách khiến việc đọc một bảng tự đủ để lấy bí mật.

Envelope cần gắn với token ID, thời hạn và bản chụp kênh nhận đã được cho phép. Không để worker gửi chọn một email mới từ nội dung tùy ý do client cung cấp. Sau khi không còn cần thử gửi, hoặc khi hết thời hạn, dữ liệu bí mật phục vụ chuyển phát phải được xóa theo chính sách.

Đây vẫn là nơi lưu một bearer secret dưới dạng có thể khôi phục. Mã hóa không biến nó thành dữ liệu được tự do đưa vào log, trace hoặc hàng đợi lỗi.

Worker gửi có thể kiểm tra token còn hiện hành trước khi gửi để giảm email lỗi thời. Tuy nhiên, token có thể bị thay ngay sau phép kiểm tra đó. Vì vậy:

- Không thể coi kiểm tra trước khi gửi là bảo đảm email sẽ luôn chứa token mới nhất lúc tới hộp thư.
- Một email cũ tới muộn không được làm token cũ sống lại.
- Thông điệp trên giao diện cần giúp người dùng hiểu vì sao liên kết đã bị thay không còn dùng được.
- Nếu gửi T2 thất bại, hệ thống thử lại tác vụ được phép hoặc hướng người dùng qua tuyến tiếp tục phù hợp; không khôi phục hiệu lực T1.

Nếu tiến trình mất kết nối sau commit nhưng trước khi phản hồi HTTP, receipt và outbox đã lưu phải đủ để tiếp tục cùng thao tác. Không suy luận rằng “client chưa nhận phản hồi” có nghĩa giao dịch chưa xảy ra.

## 11. Sự kiện trùng lặp, lệch thứ tự và cache

Hệ thống sự kiện có thể giao cùng một thông điệp nhiều lần. Consumer cần xử lý lặp theo `event_id` hoặc cơ chế tương đương, và các tác vụ tạo tác dụng phụ phải có idempotency riêng phù hợp.

Ví dụ:

~~~text
Luồng ở revision 19: T1 được thay bằng T2
Luồng ở revision 20: T2 được thay bằng T3

Consumer nhận revision 20 trước, rồi mới nhận revision 19.
~~~

Projection hiện hành không được bị kéo lùi về T2. Nếu consumer cần một ảnh chụp đầy đủ, nó có thể đọc lại trạng thái chuẩn khi phát hiện thiếu revision. Nếu consumer cần thực hiện mọi tác dụng phụ theo thứ tự, chỉ bỏ sự kiện cũ bằng một phép so sánh revision là chưa đủ; nó còn cần cơ chế theo dõi và xử lý khoảng trống.

Lịch sử audit có thể lưu cả hai sự kiện theo định danh riêng trong khi projection chỉ phản ánh trạng thái mới nhất. Hai nhu cầu này không nên bị trộn vào một phép cập nhật “last write wins” dựa trên thời gian nhận thông điệp.

Đặc biệt, cache chưa nhận thông báo vô hiệu hóa không được tiếp tục cấp quyền cho T1. Với mô hình của bài, thao tác tiêu thụ đọc và chốt điều kiện trong kho trạng thái chuẩn. Sự kiện chỉ giúp đồng bộ các bản sao phục vụ đọc hoặc vận hành.

Token tự chứa có chữ ký cũng không tự biết rằng nó đã bị thay. Chữ ký và thời hạn có thể vẫn hợp lệ về mặt mật mã. Nếu muốn vô hiệu hóa ngay trước khi hết hạn, cần kiểm tra trạng thái, phiên bản hoặc cơ chế thu hồi có thẩm quyền tương ứng.

## 12. Không để thay token trở thành công cụ khóa đường khôi phục

Một thiết kế “ai biết email cũng có thể liên tục cấp token mới và vô hiệu hóa token trước” cho phép kẻ khác làm liên kết của người dùng mất hiệu lực trước khi họ kịp mở.

Vì vậy, yêu cầu công khai chưa được xác minh không nên mặc nhiên có quyền hủy mọi tiến trình khôi phục hiện có. Quyết định thay cần kết hợp chính sách của tuyến khôi phục, kiểm soát tần suất và bằng chứng ràng buộc với luồng.

Các biện pháp có thể phối hợp gồm:

- Giới hạn yêu cầu theo tài khoản đích, luồng, nguồn và phạm vi rủi ro thích hợp.
- Khoảng chờ giữa các lần cấp, có giới hạn số lần thay trong một luồng.
- Nhận diện yêu cầu gửi lặp do thao tác hoặc mạng thay vì cấp thêm token.
- Bằng chứng tiếp tục luồng được bảo vệ phù hợp với mức quyền, khi tuyến khôi phục có khả năng cung cấp.
- Xử lý rủi ro bổ sung khi đổi thiết bị, kênh nhận hoặc phương thức xác minh.
- Phản hồi công khai tránh tiết lộ sự tồn tại của tài khoản hoặc chi tiết token đang có.

Bằng chứng tiếp tục luồng không nhất thiết là một phiên đăng nhập đầy đủ, vì người dùng có thể đang mất khả năng đăng nhập. Nó phải được định nghĩa phù hợp với tuyến khôi phục, không được tự biến một ID luồng thành bằng chứng sở hữu tài khoản.

Không đặt lại bộ đếm thử sai về không chỉ vì generation tăng. Nếu không, kẻ thử mã ngắn có thể dùng thao tác thay để nhận lại ngân sách đoán không giới hạn.

Tương tự, token mới không nên kéo dài vô hạn cùng một luồng:

~~~text
new_token.expires_at =
    min(server_now + token_lifetime, flow.absolute_deadline)
~~~

Hết thời hạn tổng thì luồng phải đi theo nhánh kết thúc hoặc bắt đầu lại đã định nghĩa. Việc bắt đầu luồng mới vẫn cần chịu kiểm soát lạm dụng ở phạm vi tài khoản và các phạm vi liên quan; nó không được tự xóa lịch sử rủi ro trước đó.

## 13. Quan hệ với session, MFA và passkey

Thay token khôi phục không tự thay đổi trạng thái của mọi session đăng nhập. Cũng không tự hủy một quyền hạn chế đã được cấp trước đó nếu quyền đó tồn tại trong một bản ghi riêng.

Cần quyết định rõ hai phạm vi:

| Thay đổi | Chính sách cần xác định |
| --- | --- |
| Chỉ thay bí mật chưa được tiêu thụ | Token cũ mất hiệu lực; quyền đăng nhập hiện có xử lý riêng |
| Khởi động lại hoặc thay toàn bộ tiến trình khôi phục | Các bằng chứng và quyền hạn chế cũ có còn được dùng không? |
| Thu hồi do nghi chiếm đoạt tài khoản | Có cần tăng phiên bản an ninh, hủy session hoặc yêu cầu xác minh bổ sung không? |
| Đã đặt lại mật khẩu thành công | Token và session liên quan được xử lý theo chính sách kết thúc khôi phục |
| Chuẩn bị thay MFA hoặc đăng ký passkey | Bằng chứng đã thu thập có đủ cho hành động này không? |

Nếu chính sách yêu cầu vô hiệu hóa cả quyền khôi phục đã cấp, quyền đó phải gắn với một phiên bản hoặc trạng thái có thể kiểm tra lại tại hành động nhạy cảm. Chỉ đổi `flow.current_token_id` trong khi vẫn chấp nhận session khôi phục cũ sẽ không đạt mục tiêu này.

Ngược lại, không nên để một yêu cầu gửi lại chưa được xác minh tự gây đăng xuất toàn bộ tài khoản. Đó là một tác dụng phụ rộng hơn nhiều so với cấp lại liên kết.

Trong luồng mất MFA hoặc mất thiết bị chứa passkey, email mới chứa T2 chỉ tiếp tục bước mà kênh email được phép chứng minh. Nó không tự nâng mức xác minh lên đủ để gỡ mọi yếu tố bảo vệ. Mục đích và mức quyền phải được giữ qua cả lần thay token lẫn lần tạo session hạn chế.

## 14. Những kết quả vận hành cần giải thích được

| Tình huống | Hành vi phù hợp với mô hình |
| --- | --- |
| Người dùng yêu cầu thay một token hiện hành | Chốt token mới và trạng thái không hợp lệ của token cũ cùng nhau |
| Cùng yêu cầu được gửi lại sau timeout | Dùng receipt đã ràng buộc; không tự sinh thế hệ tiếp theo |
| Hai yêu cầu khác nhau cùng nhắm vào generation 7 | Chỉ yêu cầu phù hợp phiên bản hiện hành được chốt; yêu cầu còn lại xử lý xung đột |
| T1 được tiêu thụ trước lệnh thay | Không tự mở lại luồng đã đổi token lấy quyền |
| T1 được thay trước yêu cầu tiêu thụ | Từ chối T1 dù bí mật đúng và thời hạn chưa hết |
| Email T1 đến sau email T2 | T1 vẫn không hợp lệ; không suy trạng thái từ thứ tự email đến |
| Gửi T2 thất bại sau commit | Thử lại chuyển phát được phép; không phục hồi T1 |
| Outbox được giao lặp | Consumer không tạo tác dụng phụ trùng ngoài chính sách |
| Consumer nhận sự kiện cũ muộn | Không kéo lùi projection hiện hành |
| Kho trạng thái chuẩn không khả dụng lúc tiêu thụ | Không cấp quyền dựa trên cache có thể còn T1 |
| Token mới vẫn trong luồng cũ | Giữ giới hạn thời hạn tổng và lịch sử lạm dụng |
| Token email được thay trong luồng mất MFA | Giữ nguyên phạm vi bằng chứng của kênh email |

Nhật ký phục vụ điều tra nên cho phép truy từ command tới giao dịch, token ID, generation, revision và tác vụ chuyển phát. Mã lý do như `VERSION_CONFLICT`, `FLOW_CLOSED` hoặc `DELIVERY_FAILED` có thể hữu ích trong hồ sơ nội bộ; không nhất thiết hiển thị nguyên trạng cho người chưa được xác minh.

Một sự kiện thay token có ý nghĩa khi hệ thống trả lời được đồng thời: token nào đã mất quyền, token nào đang hiện hành, việc thay diễn ra trong phạm vi nào, và trạng thái nào quyết định lần sử dụng tiếp theo. Token mới chỉ hoàn thành vai trò của nó khi các câu trả lời đó vẫn đúng trong cả trường hợp retry, gửi chậm và yêu cầu đồng thời.