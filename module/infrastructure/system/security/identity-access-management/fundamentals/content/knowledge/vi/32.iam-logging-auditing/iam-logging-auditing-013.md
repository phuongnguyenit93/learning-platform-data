# Authorization denial

## 1. Authorization denial là gì?

**Authorization denial** là quyết định không cho phép một chủ thể thực hiện một hành động đối với tài nguyên trong ngữ cảnh đang xét. Trong logging và audit IAM, bản ghi từ chối quyền cần giúp trả lời: ai yêu cầu, muốn làm gì, với tài nguyên nào, trong phạm vi nào, vì sao bị từ chối và hệ thống đã thực thi việc chặn ra sao.

Ví dụ, Lan đăng nhập hợp lệ vào tenant An Phú và có quyền đọc tài liệu. Khi Lan gọi API xóa tài liệu, ứng dụng xác nhận Lan không có quyền `document.delete` rồi chặn thao tác. Đây là một tình huống từ chối phân quyền, dù bước xác thực của Lan đã thành công.

OWASP liệt kê thất bại kiểm soát truy cập trong các sự kiện bảo mật cần được ghi nhận. Việc chỉ giữ access log với URL và mã HTTP có thể không cung cấp đủ ngữ cảnh để hiểu quyết định IAM. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Tên event và schema trong bài là ví dụ thiết kế. Mỗi hệ thống có thể dùng taxonomy khác, nhưng cần giữ nhất quán ý nghĩa của quyết định, kết quả thực thi và phản hồi.

## 2. Không gộp mọi yêu cầu bị chặn thành một loại sự kiện

Một yêu cầu không được thực hiện có thể xuất phát từ nhiều nguyên nhân khác nhau.

| Tình huống | Ý nghĩa nội bộ | Cách phân loại có ích |
|---|---|---|
| Token không hợp lệ hoặc phiên đã hết hạn | Không có ngữ cảnh xác thực được chấp nhận cho luồng đó | Authentication failure hoặc session failure |
| Chủ thể đã được xác minh nhưng thiếu quyền | Policy xác định không được làm hành động | Authorization denial |
| Cần xác thực bổ sung trước thao tác nhạy cảm | Chưa đáp ứng một điều kiện có thể bổ sung | Authorization challenge hoặc yêu cầu step-up theo mô hình hệ thống |
| Dịch vụ policy timeout, hệ thống chặn an toàn | Không đánh giá được quyền; hành động bị chặn | Authorization evaluation error kèm trạng thái chặn |
| Không tìm thấy route hoặc tài nguyên theo hợp đồng API | Không nhất thiết đã có quyết định IAM | Routing hoặc resource lookup event tương ứng |
| Đã được phép nhưng cập nhật dữ liệu gặp lỗi | Thực thi nghiệp vụ không thành công | Operation failure, không tự đổi thành thiếu quyền |

Các trạng thái như `DENY`, `ERROR` và `CHALLENGE` không nên bị gộp thành một cờ `failed=true`. Nếu dịch vụ policy hỏng khiến mọi yêu cầu bị chặn, việc báo đó là hàng nghìn lần người dùng thiếu quyền sẽ che khuất sự cố vận hành.

Một hệ thống có thể cho phép đánh giá quyền của chủ thể ẩn danh đối với tài nguyên công khai. Khi đó, actor có thể được ghi rõ là `ANONYMOUS`. Không tự gán một người dùng đã xác thực chỉ bằng cách đọc tên hoặc claim từ credential chưa được kiểm tra.

Một lần từ chối cũng không đồng nghĩa đã xác định có tấn công. Người dùng có thể bấm một liên kết cũ, quyền vừa thay đổi hoặc ứng dụng client còn hiển thị một chức năng không còn được phép.

## 3. Ghi đúng quyết định trong đúng phạm vi

Một quyết định quyền cần liên kết ít nhất bốn yếu tố: **chủ thể**, **hành động**, **tài nguyên** và **ngữ cảnh**.

### 3.1. Chủ thể và thẩm quyền của lời gọi

Actor có thể là người dùng, workload hoặc một chủ thể được đại diện qua cơ chế ủy quyền. Cần biết những thông tin nào đã được xác minh và nguồn nào chịu trách nhiệm cho chúng.

Trong luồng service-to-service chạy thay người dùng, nên phân biệt workload thực hiện lời gọi với chủ thể được đại diện nếu policy dùng cả hai. Nếu chỉ ghi workload, người điều tra có thể không biết yêu cầu bắt nguồn từ ai; nếu chỉ ghi người dùng, có thể mất dấu dịch vụ đã thực thi.

Với identity liên kết, một chuỗi `subjectId` thường cần đi cùng ngữ cảnh nguồn phát hành hoặc directory tương ứng. Không ghép hai chủ thể từ hai nguồn khác nhau chỉ vì họ có cùng tên hiển thị.

### 3.2. Hành động có ý nghĩa nghiệp vụ

`DELETE /documents/71` mô tả một lời gọi HTTP, còn `document.delete` mô tả quyền nghiệp vụ được đánh giá. Nên có một cách liên kết hai ý nghĩa này mà không phụ thuộc hoàn toàn vào chuỗi URL.

Một endpoint có thể thực hiện nhiều thao tác; một thao tác cũng có thể có nhiều endpoint hoặc được gọi qua job nền. Tên action ổn định giúp truy vết quyết định qua những đường đó.

### 3.3. Tài nguyên và mức độ đã xác định

Cần phân biệt tài nguyên đã được phân giải trong phạm vi hợp lệ với một ID mà client mới trình bày. Nếu yêu cầu bị chặn trước khi tra cứu tài nguyên, log không nên khẳng định tài nguyên tồn tại hoặc biết ai sở hữu nó.

Có thể dùng các trạng thái như `RESOLVED_IN_SCOPE`, `NOT_RESOLVED` hoặc `LOOKUP_NOT_PERFORMED` theo schema của ứng dụng. Không thực hiện thêm một truy vấn đặc quyền xuyên tenant chỉ để điền đẹp một bản ghi denial.

### 3.4. Tenant và điều kiện policy

Role của Lan trong An Phú không được dùng làm quyền ở Bình Minh. Log cần thể hiện tenant context đã được xác minh, cùng phạm vi tài nguyên hoặc môi trường có liên quan.

Nếu người gọi đề xuất một tenant không được phép, cần tách giá trị đề xuất khỏi tenant đáng tin cậy của phiên hoặc credential. Dữ liệu client không được tự quyết định log sẽ được đưa vào không gian audit của tenant nào.

Nguyên nhân từ chối có thể là thiếu permission, membership không hoạt động, không thỏa quan hệ sở hữu hoặc vi phạm điều kiện tài nguyên. Một reason code tổng quát như `OUTSIDE_ALLOWED_SCOPE` có thể phù hợp hơn việc luôn mô tả bằng một tên role cụ thể.

## 4. Ba lớp thông tin: quyết định, thực thi và phản hồi

Không nên coi bản ghi từ thành phần đánh giá policy là bằng chứng đầy đủ rằng hành động đã được chặn tại tài nguyên.

```text
Yêu cầu truy cập
        ↓
Đánh giá policy: DENY
        ↓
Điểm thực thi chặn hành động
        ↓
Phản hồi cho client theo hợp đồng API
        ↓
Ghi nhận và liên kết các bằng chứng tương ứng
```

Ba lớp thông tin có thể được biểu diễn riêng:

| Lớp | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Quyết định | `decision.outcome = DENY` | Policy kết luận điều gì? |
| Thực thi | `enforcement.result = BLOCKED` | Điểm bảo vệ có ngăn hành động trong phạm vi nó quản lý không? |
| Phản hồi | `response.status = 403` | Client nhận phản hồi công khai nào? |

Nếu chỉ có sự kiện từ policy engine, trạng thái thực thi có thể chưa được biết. Không tự điền `BLOCKED` khi chưa có bằng chứng từ điểm thực thi phù hợp.

Ngược lại, một điểm thực thi có thể chặn vì policy engine không sẵn sàng. Khi đó nên ghi `decision.outcome = ERROR` cùng `enforcement.result = BLOCKED`, thay vì bịa ra một quyết định từ chối do thiếu quyền.

Nếu policy trả `DENY` nhưng hành động vẫn tạo thay đổi dữ liệu, đó là vấn đề thực thi cần được điều tra. Một dòng log ghi “denied” không làm thay đổi trái phép trở nên vô hại.

## 5. Ví dụ bản ghi có cấu trúc

Ví dụ sau mô tả Lan có thể được nhận diện và tài liệu đã được phân giải trong tenant hợp lệ, nhưng Lan thiếu quyền xóa.

```json
{
  "schemaVersion": 1,
  "eventId": "event-authz-903",
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-06-01T10:20:30Z",
  "receivedAt": "2026-06-01T10:20:31Z",
  "source": {
    "service": "document-api",
    "environment": "production"
  },
  "verifiedTenantId": "tenant-an-phu",
  "actor": {
    "kind": "USER",
    "subjectSource": "internal-iam",
    "subjectId": "user-lan"
  },
  "action": "document.delete",
  "resource": {
    "type": "DOCUMENT",
    "reference": "document-71",
    "resolutionState": "RESOLVED_IN_SCOPE"
  },
  "decision": {
    "id": "decision-612",
    "outcome": "DENY",
    "reasonCode": "MISSING_PERMISSION",
    "policyId": "document-access",
    "policyVersion": 17,
    "evaluationSource": "LOCAL"
  },
  "enforcement": {
    "point": "document-command-handler",
    "result": "BLOCKED"
  },
  "response": {
    "status": 403
  },
  "requestId": "request-846",
  "routeTemplate": "/documents/{documentId}"
}
```

Các ID và mốc thời gian đều là dữ liệu minh họa. Tham chiếu tài nguyên chỉ nên được ghi ở mức cần thiết và được quyền của hệ thống audit cho phép.

Một số reason code nội bộ có thể dùng:

- `MISSING_PERMISSION`: thiếu quyền tương ứng với action.
- `MEMBERSHIP_INACTIVE`: quan hệ truy cập trong tenant không còn hoạt động.
- `OUTSIDE_ALLOWED_SCOPE`: yêu cầu nằm ngoài phạm vi được cấp.
- `RESOURCE_POLICY_DENY`: policy của tài nguyên từ chối.
- `NO_APPLICABLE_ALLOW`: không có quy tắc cho phép phù hợp trong mô hình mặc định từ chối.

Lỗi tải policy nên có reason riêng cho sự kiện lỗi đánh giá. Yêu cầu xác thực bổ sung cũng cần ngữ nghĩa riêng nếu hệ thống phân biệt challenge với hard denial.

Không nhất thiết mọi denial đều có đầy đủ mọi trường. Nếu chưa xác định được resource hoặc actor, dùng trạng thái không biết đúng nghĩa thay vì suy đoán giá trị.

## 6. Mã HTTP không thay thế sự kiện phân quyền

Theo HTTP, `401` biểu diễn thiếu credential xác thực hợp lệ và phản hồi này cần challenge `WWW-Authenticate` phù hợp. `403` biểu diễn việc máy chủ hiểu yêu cầu nhưng từ chối thực hiện. [RFC 9110, mục 15.5.2 và 15.5.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2).

Máy chủ có thể dùng `404` thay cho `403` để không tiết lộ sự tồn tại hiện tại của tài nguyên bị cấm. Vì vậy, không thể đếm mọi authorization denial chỉ bằng cách lọc access log theo `403`. [RFC 9110, mục 15.5.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.4).

Chiều ngược lại cũng quan trọng: một `404` có thể thật sự là không có route hoặc không tìm thấy tài nguyên, chưa chắc là denial. Kết luận cần dựa vào sự kiện ngữ nghĩa từ ứng dụng hoặc điểm kiểm soát.

Với xử lý batch, phản hồi tổng thể còn có thể chứa kết quả riêng cho từng thao tác. Không dùng một mã HTTP ở cấp ngoài để khẳng định mọi phần tử đều được cho phép hoặc mọi phần tử đều bị từ chối.

### Thông tin nội bộ và thông tin công khai

Client có thể chỉ cần một thông báo an toàn và mã tham chiếu hỗ trợ. Ví dụ minh họa cho API chọn trả `403`:

```http
HTTP/1.1 403 Forbidden
Cache-Control: no-store
Content-Type: application/json

{
  "error": "ACCESS_DENIED",
  "requestId": "request-846"
}
```

Không cần trả toàn bộ role đang thiếu, ACL của tài nguyên, tenant sở hữu hoặc biểu thức policy cho người gọi chưa được phép biết những thông tin đó.

Khi sản phẩm chọn che sự tồn tại của tài nguyên, cần xem tính nhất quán của body, thời gian xử lý và những dấu hiệu khác. Chỉ đổi mã trạng thái trong khi thông báo vẫn nêu tên tài nguyên ngoài phạm vi không đạt được mục đích đó.

Request ID công khai nên là tham chiếu phục vụ hỗ trợ, không phải quyền đọc log hoặc credential dùng để tiếp tục thao tác.

## 7. Ghi ở đúng điểm kiểm tra quyền

Quyền cần được kiểm tra trên các yêu cầu liên quan ở phía máy chủ, không chỉ bằng cách ẩn nút trên giao diện. OWASP nhấn mạnh việc kiểm tra permission trên mỗi yêu cầu, bất kể yêu cầu được khởi tạo từ đâu. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request).

Ứng dụng có thể có nhiều điểm từ chối: gateway, middleware, kiểm tra tài nguyên trong dịch vụ và worker xử lý tác vụ nền. Cần nhận diện nguồn sự kiện để biết lớp nào thực sự ra quyết định.

Ví dụ, nếu gateway chặn yêu cầu trước khi backend nhận được, backend sẽ không tạo denial event cho yêu cầu đó. Chỉ thu log backend có thể bỏ mất một phần hoạt động bị từ chối.

Ngược lại, gateway có thể chỉ biết quyền ở cấp route. Backend vẫn cần kiểm tra quyền với tenant, tài liệu và trạng thái cụ thể. Một yêu cầu qua được gateway chưa bảo đảm được làm mọi thao tác phía sau.

### Luồng xử lý minh họa

```text
function handleProtectedAction(request):
    context = resolveValidatedIdentityOrAllowedAnonymousContext(request)
    resourceContext = resolveResourceWithinAllowedLookupScope(request, context)
    evaluation = evaluateAuthorization(context, request.action, resourceContext)

    if evaluation.outcome == ERROR:
        blockAction()
        recordEvaluationErrorWithBlockedEnforcement(evaluation, context)
        return safeUnavailableOrPolicyDefinedError()

    if evaluation.outcome == CHALLENGE:
        doNotExecuteProtectedAction()
        recordAdditionalEvidenceRequired(evaluation, context)
        return allowedChallengeResponse()

    if evaluation.outcome == DENY:
        blockAction()
        recordDenialWithoutSecrets(evaluation, context, resourceContext)
        return safePublicDenialResponse()

    require evaluation.outcome == ALLOW
    return executeWithinAuthorizedScopeWithRequiredRechecks(request, evaluation)
```

Đây là mã giả thể hiện trách nhiệm, không phải một thư viện hoàn chỉnh. `blockAction` có nghĩa đường xử lý không tiếp tục thực hiện hành động được bảo vệ, chứ không chỉ đặt một cờ rồi vẫn gọi nghiệp vụ.

Không ghi denial sau khi đã xóa hoặc cập nhật tài nguyên rồi coi đó là kiểm soát truy cập. Với thao tác nhạy cảm, có thể cần kiểm tra lại điều kiện tại ranh giới ghi để xử lý trường hợp quyền thay đổi sau quyết định ban đầu.

Lỗi ghi log cũng không được làm một nhánh `DENY` rơi xuống nhánh thực thi được phép. Cách ứng xử với lỗi audit phải được định nghĩa mà vẫn giữ quyết định chặn đã có.

## 8. Liên kết sự kiện qua nhiều lớp và nhiều lần thử

`eventId`, `decisionId` và `requestId` phục vụ những mục đích khác nhau:

- `eventId` nhận diện một lần phát sinh sự kiện.
- `decisionId` liên kết bằng chứng đánh giá và thực thi của cùng quyết định.
- `requestId` liên kết các sự kiện của một yêu cầu kỹ thuật.
- Tham chiếu thao tác hoặc job liên kết các phần của một luồng nghiệp vụ rộng hơn.

Một request có thể tạo nhiều quyết định quyền. Ví dụ, một batch gồm nhiều tài nguyên có thể được đánh giá theo từng phần tử. Không khử trùng mọi event cùng request ID thành một event rồi làm mất những quyết định khác nhau.

Ngược lại, một consumer có thể nhận lại cùng một event do retry. Cần nhận diện bản sao theo nguồn và event ID để không đếm một denial thành nhiều lần thử trái phép.

Nếu policy engine và điểm thực thi đều phát sự kiện, dashboard cần biết chúng mô tả hai bằng chứng của một quyết định hay hai quyết định độc lập. Số event không tự bằng số yêu cầu bị từ chối.

### Policy và cache

Khi dùng quyết định được cache, nên biết nguồn đánh giá và phiên bản liên quan. Lan vừa được cấp quyền nhưng vẫn bị từ chối bởi một cache cũ là tình huống điều tra khác với policy hiện tại thật sự cấm Lan.

Ngược lại, log denial ở một node không chứng minh mọi node đã áp dụng việc thu hồi. Cần đối chiếu phiên bản policy, quyền hiệu lực và kết quả ở những điểm thực thi liên quan.

Thời điểm xảy ra và thời điểm tiếp nhận cũng cần được tách rõ nếu có pipeline bất đồng bộ. Một denial đến muộn không nhất thiết xảy ra sau một lần cấp quyền chỉ vì nó được nhìn thấy sau trong hệ thống tập trung.

## 9. Không biến denial log thành nguồn rò rỉ

### Không ghi credential và payload tùy ý

Không ghi access token, refresh token, cookie phiên, mật khẩu hoặc authorization header đầy đủ. Chỉ cần định danh chủ thể đã xác minh và tham chiếu điều tra phù hợp, không cần lưu lại credential để chứng minh chủ thể đó.

Raw URL có thể chứa token, thông tin cá nhân hoặc ID nhạy cảm. Route template cùng những trường được phép ghi thường dễ kiểm soát hơn việc dump nguyên URL và query string.

Không mặc định ghi toàn bộ body của một yêu cầu bị cấm. Payload bị chặn vẫn có thể chứa dữ liệu nhạy cảm do người dùng nhập hoặc do client tự gửi.

### Không sao chép toàn bộ policy và thuộc tính

Một reason code và tham chiếu phiên bản policy thường hữu ích hơn việc ghi toàn bộ tập role, claims, nhóm và ACL vào mọi event. Nếu cần giải thích sâu hơn, có thể giữ bằng chứng trong một vùng kiểm soát truy cập riêng, theo nhu cầu điều tra.

Các thuộc tính chưa được xác minh cần được đánh dấu là đầu vào, không thể hiện như sự thật về actor. Độ dài, ký tự và cấu trúc dữ liệu log cũng cần được kiểm tra để ngăn log injection hoặc làm cạn tài nguyên.

### Bảo vệ chính quyền đọc audit

Một quản trị viên tenant không nên xem được denial log của tenant khác thông qua tìm kiếm, export hoặc dashboard chung. Log về một yêu cầu vượt tenant có thể chứa thông tin nhạy cảm ở cả ngữ cảnh actor lẫn tài nguyên được nhắm tới, nên cần quy tắc hiển thị phù hợp.

Người có quyền sửa policy không nên tùy ý xóa dấu vết denial và các thay đổi policy của chính mình. Quyền quản trị audit cần được phân tách và theo dõi tương xứng.

Truy cập kho audit cũng là một thao tác được bảo vệ. Khi ghi lại việc bị từ chối đọc audit, cần tránh thiết kế logger gọi ngược liên tục vào chính endpoint vừa bị từ chối, tạo vòng lặp log vô hạn.

## 10. Dùng denial để phát hiện vấn đề

Denial event có thể phản ánh truy cập ngoài phạm vi, lỗi client, lỗi cấu hình hoặc việc thu hồi quyền đang hoạt động đúng.

| Mẫu quan sát | Hướng điều tra | Giới hạn của kết luận |
|---|---|---|
| Một actor thử nhiều tham chiếu tài nguyên ngoài phạm vi | Có hành vi dò đối tượng hoặc lỗi chọn tài nguyên không? | Không tự chứng minh đã đọc được dữ liệu |
| Nhiều yêu cầu vào API quản trị từ role thông thường | Client sai chức năng hay cố vượt quyền? | Cần đối chiếu ngữ cảnh và nguồn gọi |
| Denial tăng mạnh ngay sau một phiên bản policy mới | Có triển khai nhầm quyền hoặc phạm vi không? | Nhiều denial không luôn đồng nghĩa nhiều kẻ tấn công hơn |
| Denial xuất hiện sau khi role bị thu hồi | Thu hồi đã tới những điểm thực thi nào? | Một điểm chặn thành công không chứng minh mọi điểm đều đã cập nhật |
| Thành công sau một chuỗi denial | Có cấp quyền hợp lệ, sửa cấu hình hoặc đổi action không? | Không gộp mọi thành công thành bằng chứng vượt kiểm soát |
| Evaluation error tăng đồng thời ở nhiều dịch vụ | Policy service hoặc nguồn thuộc tính có gián đoạn không? | Không báo sai thành người dùng đồng loạt thiếu permission |

Ngưỡng và mức độ cảnh báo nên phản ánh action, độ nhạy cảm tài nguyên, số đối tượng và mẫu hành vi. Một lần viewer bấm nút xóa do giao diện lỗi khác với nhiều lần gọi chức năng cấp đặc quyền ngoài nhiệm vụ.

Không dùng số lượng `403` hoặc số event đơn lẻ làm thước đo duy nhất về hiệu quả IAM. Cần biết số quyết định, số yêu cầu, nguồn dữ liệu và mức bao phủ thực tế.

Denial log cũng không thay thế việc kiểm tra đường truy cập được phép. Một lỗi kiểm soát có thể cho qua hoàn toàn mà không tạo denial event nào. Không có denial không chứng minh hệ thống không có truy cập trái phép.

## 11. Độ tin cậy của pipeline và tình huống minh họa

### Truyền và lưu bằng chứng

Sự kiện nên được tiếp nhận từ nguồn có xác thực, qua kênh bảo vệ thích hợp, có schema và theo dõi trạng thái gửi. Nếu cho client tự gửi sự kiện với tên tùy ý vào cùng nguồn audit tin cậy, kết quả điều tra có thể bị làm sai.

Pipeline cần xử lý retry, sự kiện lặp, queue đầy, lỗi chuẩn hóa và thời gian tiếp nhận. Nếu phải tổng hợp hoặc giới hạn lưu lượng log, cần biết bằng chứng nào vẫn được giữ và đo được phần mất mát. Không sampling tùy tiện những event đặc quyền cần lưu để điều tra.

Lưu lượng denial có thể rất lớn khi endpoint bị lạm dụng. Cần buffer có giới hạn và chế độ lỗi rõ ràng để việc gửi log không giữ vô hạn tài nguyên xử lý. Đồng thời, việc kho log tạm thời hỏng không phải lý do để cho phép hành động đã bị policy từ chối.

Kho audit phản ánh bằng chứng; nó không nên là nguồn duy nhất của quyền hiệu lực hoặc bộ đếm an ninh đòi hỏi tính tức thời. Những quyết định thực thi phải dựa trên trạng thái và cơ chế được thiết kế cho mục đích đó.

### Lan yêu cầu xóa tài liệu

Lan có role viewer ở An Phú. Một client cũ vẫn hiển thị chức năng xóa. Lan gửi yêu cầu xóa tài liệu 71 và bị policy phiên bản 17 từ chối do thiếu `document.delete`.

Điểm thực thi dừng trước hành động xóa, ghi denial với request ID và decision ID rồi trả phản hồi công khai. Không có thao tác xóa tương ứng trong trạng thái dữ liệu.

Sau đó, Lan được cấp quyền phù hợp qua một quy trình riêng. Quyết định mới được đánh giá theo quyền hiệu lực và cho phép một yêu cầu mới. Chuỗi này không tự là bằng chứng lách quyền; cần đối chiếu bản ghi cấp quyền và phiên bản quyết định.

Những biến thể cần được nhận diện:

| Biến thể | Cách hiểu đúng |
|---|---|
| Credential hết hạn trước khi tới lớp phân quyền | Phân loại theo xác thực; không bịa reason thiếu permission |
| Gateway đã chặn nên backend không có event | Cần lấy bằng chứng từ gateway để đánh giá độ bao phủ |
| Policy timeout và ứng dụng chặn | Ghi lỗi đánh giá kèm kết quả chặn |
| Client đổi tenant trong URL | Không lấy tenant tự khai làm tenant audit đáng tin cậy |
| API trả phản hồi che sự tồn tại tài nguyên | Dùng event nội bộ để hiểu denial, không chỉ mã HTTP |
| Hai bản sao cùng denial event tới collector | Không đếm thành hai lần thử độc lập |
| Log ghi denial nhưng dữ liệu tài liệu vẫn bị thay đổi | Điều tra lỗi thực thi; bản ghi denial không chứng minh thao tác đã an toàn |

## 12. Kiểm chứng và câu hỏi tự kiểm tra

Kiểm tra nên xác nhận không chỉ event có xuất hiện mà cả hành động bị cấm không tạo hiệu ứng trái phép. Với một thao tác xóa bị chặn, cần đối chiếu trạng thái tài nguyên, tác vụ nền và những hệ thống đích liên quan theo phạm vi kiến trúc.

Các tình huống hữu ích gồm actor thiếu quyền, tenant không phù hợp, tài nguyên chưa được phân giải, yêu cầu step-up, policy service lỗi, cache cũ, xử lý batch, job nền và việc từ chối xảy ra trước khi backend được gọi.

Về chất lượng dữ liệu, cần kiểm tra trường bắt buộc, outcome có ngữ nghĩa đúng, bản sao không làm tăng số lần thử, actor không được suy ra từ credential chưa xác minh và các secret không xuất hiện trong log, trace hoặc hàng đợi lỗi.

Câu hỏi tự kiểm tra:

1. Vì sao một `DENY` từ policy engine chưa đủ để kết luận tài nguyên đã được bảo vệ đúng?
2. Tại sao policy timeout dẫn tới chặn cần được phân biệt với một quyết định thiếu quyền?
3. Khi nào denial không xuất hiện dưới mã `403`, và vì sao một `404` chưa chắc là denial?
4. Request ID, decision ID và event ID khác nhau thế nào trong một yêu cầu batch hoặc pipeline có retry?
5. Cần xem thêm bằng chứng gì khi một actor thành công sau một chuỗi denial?

Authorization denial hữu ích khi mô tả đúng quyết định, phạm vi và kết quả thực thi mà không làm lộ dữ liệu cần bảo vệ. Kết hợp sự kiện có cấu trúc với trạng thái thực tế và bằng chứng policy giúp phân biệt truy cập ngoài quyền, cấu hình sai và sự cố hệ thống.
