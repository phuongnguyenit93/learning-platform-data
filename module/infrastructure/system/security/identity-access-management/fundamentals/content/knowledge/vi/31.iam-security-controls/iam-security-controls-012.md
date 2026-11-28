# Fail closed: giữ ranh giới truy cập khi kiểm soát IAM gặp lỗi

## 1. Lỗi kiểm tra không được trở thành quyền truy cập

**Fail closed** là nguyên tắc giữ trạng thái không cho thực hiện một hành động được bảo vệ khi hệ thống không thể xác minh một điều kiện bảo mật bắt buộc để cho phép hành động đó.

Trong IAM, lỗi có thể xuất hiện ở nhiều nơi: không truy cập được kho phiên, dịch vụ phân quyền hết thời gian chờ, dữ liệu thành viên bị thiếu, kết quả xác thực MFA không xác minh được hoặc bộ máy chính sách trả về dữ liệu không hợp lệ.

Nguyên tắc quan trọng là:

```text
Không xác minh được điều kiện bắt buộc
    không đồng nghĩa
Điều kiện đã được đáp ứng
```

Ví dụ, Lan yêu cầu xuất hợp đồng của An Bình. Chính sách yêu cầu Lan có quyền xuất còn hiệu lực và hoàn tất điều kiện xác thực tương ứng. Nếu dịch vụ quyền không phản hồi và hệ thống không có bằng chứng hợp lệ thay thế theo chính sách, request không được tự chạy chỉ để tránh gián đoạn công việc.

Fail closed không nhất thiết làm ứng dụng dừng toàn bộ. Trang giới thiệu công khai có thể tiếp tục hoạt động, trong khi API xuất hợp đồng từ chối xử lý do chưa đủ bằng chứng. Phạm vi bị ảnh hưởng cần đi theo điều kiện kiểm soát của từng tài nguyên và hành động.

## 2. Phân biệt fail closed, fail open và deny by default

| Khái niệm | Tình huống chính | Ví dụ |
| --- | --- | --- |
| Deny by default | Không có một căn cứ cho phép áp dụng được | Người dùng không có grant đọc tài nguyên thì bị từ chối |
| Fail closed | Không thể hoàn tất một kiểm tra bắt buộc | Không đọc được trạng thái thu hồi quyền thì không thực hiện thao tác cần trạng thái đó |
| Fail open | Lỗi kiểm tra dẫn đến bỏ qua điều kiện hoặc cho phép | PDP timeout thì coi như có quyền |
| Suy giảm có kiểm soát | Một chính sách đã định cho phép một khả năng hạn chế với bằng chứng còn hợp lệ | Chỉ cho đọc một loại dữ liệu đã được cấp khi đáp ứng đủ điều kiện của chế độ đó |

Fail closed và deny by default hỗ trợ nhau nhưng giải quyết hai câu hỏi khác nhau. Một hệ thống có thể mặc định từ chối khi không có quyền, nhưng lại cho qua mọi request khi dịch vụ quyền lỗi. Hệ thống đó vẫn có đường fail open.

Cũng cần phân biệt lỗi vận hành với việc xác minh thất bại:

- Token có chữ ký sai là bằng chứng không được chấp nhận.
- Dịch vụ cần thiết để kiểm tra token không truy cập được là một tình trạng chưa xác minh được.
- Chủ thể có danh tính hợp lệ nhưng thiếu quyền là một quyết định từ chối nghiệp vụ.

Cả ba có thể dẫn đến không thực hiện hành động, nhưng cần lý do nội bộ, phản hồi và cách khắc phục khác nhau.

## 3. Xác định điều kiện nào thực sự bắt buộc

Không thể áp dụng fail closed chính xác nếu hệ thống chưa định nghĩa rõ dữ liệu nào cần cho quyết định.

Với một yêu cầu xuất hợp đồng, có thể cần:

1. Danh tính của người yêu cầu đã được xác thực.
2. Token hoặc phiên áp dụng đúng dịch vụ đang bảo vệ.
3. Tài khoản và tư cách thành viên còn được chấp nhận.
4. Quyền xuất dữ liệu đúng tenant và tài nguyên.
5. Điều kiện xác thực tăng cường nếu chính sách yêu cầu.
6. Các nghĩa vụ như giới hạn dữ liệu hoặc ghi nhận audit bắt buộc.

Không phải mọi request đều phải gọi tất cả dịch vụ này trực tuyến. Kiến trúc có thể cho phép sử dụng bằng chứng đã được kiểm chứng và còn hiệu lực trong một phạm vi thời gian rõ ràng.

Điều cần hỏi là: “Theo hợp đồng bảo mật của hành động này, bằng chứng hiện có đã đủ chưa?”. Không nên biến câu hỏi thành “Mọi phụ thuộc có đang trực tuyến không?” hoặc “Có lỗi mạng nào thì cứ chặn hết ứng dụng”.

Ví dụ, nếu API được thiết kế xác minh token bằng một khóa đã có trong tập khóa tin cậy còn hiệu lực, việc dịch vụ phân phối khóa tạm thời lỗi không nhất thiết làm bằng chứng đó mất giá trị ngay. Nhưng nếu token chỉ đến một khóa chưa được nhận diện, lỗi tải khóa không phải lý do bỏ qua kiểm tra chữ ký.

## 4. Những vị trí thường phát sinh fail open

### 4.1. Khối xử lý ngoại lệ trả về cho phép

Mã giả nguy hiểm:

```text
function canExport(request):
    try:
        return authorizationService.isAllowed(request)
    catch anyError:
        return true
```

Bất kỳ lỗi kết nối, lỗi định dạng hoặc lỗi chương trình nào cũng có thể biến thành quyền xuất dữ liệu.

Một nguyên tắc phù hợp hơn:

```text
Chỉ một quyết định ALLOW hợp lệ mới đi tiếp.
Lỗi, kết quả thiếu hoặc kết quả không nhận diện được đều không chạy hành động.
```

### 4.2. Dùng giá trị mặc định rộng

Các giá trị mặc định có thể tạo đường vượt kiểm soát:

```text
roles = loadRoles() or ["admin"]
tenantId = verifiedTenantId or "all-tenants"
mfaRequired = loadPolicy() or false
```

Khi dữ liệu thiếu, những mặc định này làm quyền rộng hơn.

Đối với dữ liệu bắt buộc, cần biểu diễn trạng thái thiếu hoặc lỗi rõ ràng. Không dùng `null`, danh sách rỗng hoặc một giá trị đặc biệt để vừa mang nghĩa “không có dữ liệu” vừa mang nghĩa “không giới hạn”.

### 4.3. Chuyển sang một đường xác thực yếu hơn

Nếu kiểm tra SSO hoặc MFA lỗi, ứng dụng không nên tự mở một đường đăng nhập thay thế bỏ các điều kiện bắt buộc.

Một đường dự phòng có thể hợp lệ nếu được thiết kế và bảo vệ bằng chính sách riêng. Nó không nên xuất hiện như một nhánh tiện lợi trong xử lý lỗi của luồng chính.

### 4.4. Cho phép dữ liệu đi qua trước khi kiểm tra xong

Trả dữ liệu rồi mới gọi PDP, bắt đầu xuất tệp trong khi chờ kiểm tra hoặc thực hiện một phần thao tác trước khi xác minh đầy đủ đều làm fail closed mất tác dụng.

Một response từ chối sau khi side effect đã xảy ra không bảo vệ được tác động đã tạo.

## 5. Luồng xử lý tại điểm thực thi

Một điểm thực thi chính sách cần giữ request ở trạng thái chưa được phép cho đến khi có quyết định hợp lệ và các nghĩa vụ có thể được thực hiện.

```text
Nhận request
    -> xác minh danh tính và phạm vi
    -> lấy bằng chứng bắt buộc
    -> đánh giá chính sách
    -> kiểm tra quyết định và nghĩa vụ
    -> thực hiện hành động
```

Nếu một bước trước thực thi không hoàn tất, hành động được bảo vệ chưa được chạy.

Mã giả minh họa:

```text
function exportContracts(request, credential):
    identity = validateCredential(credential)
    scope = establishVerifiedScope(identity, request.tenantId)

    try:
        evidence = resolveRequiredEvidence(identity, scope)
        decision = policyEngine.evaluate(
            subject = identity.subject,
            action = "contract:export",
            resourceScope = scope,
            evidence = evidence
        )
    catch requiredDependencyFailure:
        recordAuthorizationUnavailable(request)
        return temporaryFailureWithoutStartingExport()

    if decision is missing or not wellFormed:
        recordInvalidAuthorizationResult(request)
        return failureWithoutStartingExport()

    if decision.type != "ALLOW":
        return denyWithoutStartingExport()

    if not decisionMatchesCurrentRequest(decision, identity, scope):
        return denyWithoutStartingExport()

    if not requiredObligationsCanBeEnforced(decision):
        return failureWithoutStartingExport()

    return executeExportWithinDecision(decision)
```

Một kết quả `ALLOW` cần đúng chủ thể, hành động, tài nguyên, phạm vi và hiệu lực. Không dùng kết quả cũ cho request khác hoặc bỏ qua nghĩa vụ chỉ vì đã thấy chữ cho phép.

Trong triển khai thực tế, các bước xác minh danh tính và phạm vi cũng phải có xử lý lỗi an toàn. Không đặt chúng ngoài thiết kế fail closed chỉ vì chúng nằm trước ví dụ về dịch vụ quyền.

## 6. Áp dụng vào từng lớp IAM

### 6.1. Xác thực và kiểm tra token

Nếu không xác minh được chữ ký, nguồn phát hành, đối tượng nhận hoặc điều kiện hiệu lực bắt buộc của token, không sử dụng danh tính tự khai trong token để mở quyền.

Không chuyển từ “không kiểm tra được chữ ký” sang “chỉ giải mã payload để lấy user ID”.

Nếu một API bắt buộc truy vấn trạng thái token trực tuyến và không có cơ chế bằng chứng thay thế được chấp nhận, lỗi truy vấn không được hiểu là token đang hoạt động.

Với xác minh cục bộ, phải áp dụng đúng tập khóa và giới hạn tin cậy đã cấu hình. Không tải hoặc chấp nhận một khóa từ địa chỉ tùy ý mà token yêu cầu chỉ để vượt qua lỗi nhận diện khóa.

### 6.2. Kho phiên

Nếu ứng dụng cần đọc kho phiên để xác nhận phiên còn hiệu lực, lỗi đọc không được biến thành một phiên đã xác thực.

Cũng không nên tạo một phiên mới đã đăng nhập chỉ vì bản ghi phiên cũ không đọc được.

Một đường đọc công khai có thể tiếp tục phục vụ như truy cập công khai nếu được thiết kế tường minh. Nó không được vô tình trả nội dung cá nhân hóa hoặc quyền của phiên chưa xác minh.

### 6.3. Phân quyền và tenant context

Không lấy được quan hệ thành viên không có nghĩa người dùng được coi là thành viên mặc định.

Thiếu tenant context không có nghĩa bỏ bộ lọc tenant. Cần đặc biệt kiểm tra các hàm dựng truy vấn động: nếu chỉ thêm điều kiện khi `tenantId != null`, lỗi xác lập tenant có thể khiến truy vấn mở rộng sang toàn bộ dữ liệu.

### 6.4. MFA và xác thực tăng cường

Kết quả xác thực bổ sung cần được kiểm tra và ràng buộc với đúng chủ thể, luồng và mục đích.

Nếu dịch vụ MFA lỗi, không tự sửa chính sách thành “MFA không bắt buộc”. Nếu callback thiếu dữ liệu xác minh, không đánh dấu hoàn tất dựa trên tham số do client tự gửi.

Tình trạng lỗi cũng không chứng minh người dùng nhập sai mã. Cần phân loại đúng để tránh biến lỗi hạ tầng thành khóa tài khoản không cần thiết.

### 6.5. Đăng ký và khôi phục tài khoản

Nếu không xác minh được bằng chứng khôi phục, không đổi mật khẩu, thêm phương thức MFA hoặc cấp lại quyền quản trị.

Một luồng khôi phục yếu khi hệ thống chính lỗi có thể trở thành đường vượt toàn bộ các kiểm soát đăng nhập khác.

### 6.6. Workload và job nền

Danh tính dịch vụ hợp lệ chưa đủ để bỏ qua quyền của tác vụ.

Nếu job không có phạm vi hoặc quyền ủy nhiệm cần thiết, không thực hiện với toàn bộ quyền kỹ thuật của worker. Có thể đưa job vào trạng thái chờ hoặc thất bại có lý do để tiếp tục có kiểm soát khi phụ thuộc phục hồi.

Retry không được bỏ qua bước xác minh chỉ vì lần xử lý trước đã bị lỗi.

## 7. Cache còn hiệu lực không đồng nghĩa fail open

Cache thường cần thiết để giảm độ trễ và phụ thuộc. Vấn đề không phải có dùng cache hay không, mà là bằng chứng cache có còn đáp ứng hợp đồng của quyết định không.

Ví dụ một bản ghi:

```text
subject: user-lan
tenant: tenant-an-binh
action: contract:export
resourceScope: project-27
policyVersion: policy-24
validatedAt: thời điểm xác minh
validUntil: giới hạn được chấp nhận
decision: ALLOW
```

Có thể tái sử dụng nếu toàn bộ điều kiện áp dụng vẫn được đáp ứng theo thiết kế. Không được dùng bản ghi này để xuất tenant khác hoặc một tập dữ liệu rộng hơn.

Một chính sách cache cần xác định:

- Những thành phần nào tạo nên khóa cache.
- Thời điểm nào là mốc tính độ mới.
- Phiên bản chính sách hoặc trạng thái nào làm mất hiệu lực.
- Hành động nào cho phép bằng chứng cache, hành động nào cần dữ liệu mới.
- Cách xử lý khi cache hết hiệu lực nhưng không thể làm mới.

Không làm mới tuổi của bằng chứng chỉ bằng cách đọc lại cache. Nếu mỗi lần đọc lại đặt thời hạn mới mà không xác minh lại nguồn cần thiết, một quyết định cũ có thể tồn tại không giới hạn.

Tương tự, một bản chính sách đã biết là hợp lệ có thể được dùng khi đáp ứng điều kiện phiên bản và hiệu lực của hệ thống. Không tự quay về một chính sách cũ, rộng hơn hoặc đã bị thu hồi chỉ vì bản hiện hành không tải được.

## 8. Quyền thay đổi trong khi thao tác đang chạy

Fail closed cần được xét cả với kết nối dài hạn và công việc có nhiều bước.

### 8.1. Khoảng cách giữa kiểm tra và thực thi

Một request có thể được cho phép lúc bắt đầu, nhưng tài nguyên hoặc quyền thay đổi trước khi ghi dữ liệu.

Với hành động nhạy cảm, hệ thống cần xác định điều kiện nào phải còn đúng tại thời điểm thực thi. Có thể cần kiểm tra lại, ràng buộc phiên bản hoặc cơ chế giao dịch phù hợp.

Không có một cách duy nhất cho mọi nghiệp vụ, nhưng phải tránh giả định rằng quyết định ban đầu luôn áp dụng vô thời hạn.

### 8.2. Kết nối và luồng dữ liệu

Một kết nối đã được thiết lập có thể tiếp tục gửi dữ liệu sau lúc nguồn quyền gặp lỗi hoặc quyền bị thu hồi.

Thiết kế cần quy định thời điểm đánh giá lại và cách dừng gửi dữ liệu hoặc đóng kết nối khi không còn đủ bằng chứng bắt buộc. Không để kết nối tồn tại mãi chỉ vì đã xác thực lúc mở.

### 8.3. Công việc nhiều bước và hàng loạt

Với xuất báo cáo hoặc xử lý hàng loạt, cần xác định đơn vị cấp quyền và đơn vị tạo tác động.

Nếu hợp đồng yêu cầu kiểm tra toàn bộ trước khi chạy, lỗi ở một điều kiện bắt buộc phải ngăn tác động chưa được cho phép. Nếu hỗ trợ từng phần, chỉ phần đã được xác lập quyền theo hợp đồng mới được xử lý.

Khi một tác động không thể hoàn tác đã xảy ra, hệ thống không nên tuyên bố rằng việc từ chối cuối cùng đã xóa được hậu quả. Cần ghi nhận trạng thái thực tế để phục hồi và điều tra.

## 9. Audit bắt buộc và lỗi ghi nhật ký

Không phải mọi lỗi gửi telemetry đều có cùng ý nghĩa bảo mật.

Nếu metrics phục vụ quan sát tạm thời lỗi nhưng kiểm soát truy cập và audit bắt buộc vẫn hoạt động, không nhất thiết phải chặn mọi request. Ngược lại, nếu một hành động đặc quyền yêu cầu có dấu vết audit bền vững trước khi hoàn tất, không ghi được dấu vết đó có thể là điều kiện ngăn hành động.

Cần tách rõ:

| Loại dữ liệu | Mục đích | Hành vi khi lỗi cần được định nghĩa |
| --- | --- | --- |
| Metrics vận hành | Theo dõi tải và độ trễ | Có thể suy giảm quan sát theo chính sách |
| Log chẩn đoán | Hỗ trợ xử lý lỗi | Không mặc định làm mất mọi khả năng truy cập |
| Audit bắt buộc | Ghi nhận hành động nhạy cảm và trách nhiệm | Phải đáp ứng mức bền vững đã yêu cầu |

Nếu audit được gửi bất đồng bộ, cần xác định thời điểm đã được coi là ghi nhận bền vững. Một bản ghi còn nằm trong bộ nhớ tiến trình có thể mất khi tiến trình dừng.

Có thể cần cơ chế ghi bền vững hoặc phối hợp với giao dịch nghiệp vụ. Không chỉ bắt lỗi gửi log rồi tiếp tục một hành động mà chính sách yêu cầu audit phải thành công.

Các bản ghi lỗi cũng không được chứa token, mật khẩu hoặc bí mật để “dễ điều tra”.

## 10. Giảm gián đoạn mà vẫn giữ fail closed

### 10.1. Giới hạn thời gian chờ

Một kiểm soát không phản hồi có thể làm request bị treo và chiếm tài nguyên.

Thời gian chờ cần có giới hạn phù hợp với luồng xử lý. Khi hết giới hạn, request không thực hiện hành động được bảo vệ và trả về trạng thái lỗi phù hợp.

Không retry vô hạn hoặc làm nhiều lớp cùng retry đến mức sự cố phụ thuộc trở thành quá tải toàn hệ thống.

### 10.2. Circuit breaker không cấp quyền

Circuit breaker có thể giúp ngừng gọi dồn dập vào một dịch vụ đang lỗi. Khi ngắt mạch, hành vi thay thế vẫn phải giữ điều kiện bảo mật.

Một kết quả “không gọi PDP vì mạch đang mở” không phải kết quả `ALLOW`.

### 10.3. Dự phòng và thu hẹp phạm vi ảnh hưởng

Có thể tăng độ sẵn sàng bằng nguồn dữ liệu dự phòng, sao chép chính sách hợp lệ và tách phụ thuộc giữa các nhóm chức năng.

Ví dụ, lỗi dịch vụ kiểm tra điều kiện đặc biệt cho xuất dữ liệu không nhất thiết ngăn mọi trang công khai. Nhưng nó vẫn phải ngăn thao tác xuất nếu điều kiện đó là bắt buộc.

Điểm cần bảo vệ là điều kiện của hành động, không phải mục tiêu làm tất cả tính năng cùng thành công hoặc cùng thất bại.

### 10.4. Suy giảm có kiểm soát phải được thiết kế trước

Một chế độ hạn chế chỉ hợp lệ nếu đã xác định chủ thể, dữ liệu, hành động, thời hạn và bằng chứng được chấp nhận.

Không thiết kế chế độ này bằng cách bắt ngoại lệ rồi bỏ điều kiện gây lỗi. Nếu một hành động yêu cầu trạng thái thu hồi hiện hành, việc nguồn trạng thái lỗi không tự tạo ra quyền dùng trạng thái cũ vô hạn.

## 11. Phục hồi và truy cập khẩn cấp

Một hệ thống fail closed vẫn cần có cách quản trị sự cố khi phụ thuộc IAM chính không hoạt động.

Quy trình khẩn cấp có thể dùng danh tính hoặc đường quản trị được bảo vệ riêng, nhưng phải có:

- Điều kiện kích hoạt và người chịu trách nhiệm.
- Danh tính người thực hiện được xác minh.
- Phạm vi hành động và tài nguyên hạn chế.
- Thời hạn sử dụng.
- Cách ghi nhận hoạt động khi một số dịch vụ đang lỗi.
- Cách thu hồi và rà soát sau khi phục hồi.

Một tham số `skipAuthorization=true` do client gửi không phải quy trình khẩn cấp. Một mật khẩu chung để ở tài liệu công khai nội bộ cũng không phải nền tảng tin cậy thích hợp.

Đường phục hồi cần được kiểm thử trước khi có sự cố. Nếu chỉ phát hiện lúc IAM chính hỏng rằng mọi công cụ phục hồi đều phụ thuộc chính thành phần đó, nhóm vận hành dễ bị đẩy vào việc tắt kiểm soát ngoài kế hoạch.

Sau phục hồi, cần xử lý các request hoặc job đang chờ theo quyền hiện hành. Không mặc định phát lại mọi tác vụ với kết quả cho phép đã có trước sự cố.

## 12. Quan sát lỗi mà không nhầm thành truy cập trái phép

Một bản ghi nội bộ có thể thể hiện:

```json
{
  "eventType": "PROTECTED_ACTION_NOT_EXECUTED",
  "subjectId": "user-lan",
  "tenantId": "tenant-an-binh",
  "action": "contract:export",
  "result": "AUTHORIZATION_UNAVAILABLE",
  "dependency": "membership-state",
  "sideEffectStarted": false,
  "correlationId": "corr-92"
}
```

Cần phân biệt ít nhất:

- Từ chối vì chính sách không cấp quyền.
- Không thể đánh giá do phụ thuộc lỗi.
- Bằng chứng không hợp lệ.
- Bằng chứng hết hiệu lực hoặc không đủ mới.
- Nghĩa vụ của quyết định không thực hiện được.

Thông tin này giúp vận hành sửa đúng vấn đề. Không nên tự khóa hàng loạt người dùng chỉ vì một dịch vụ xác minh đang timeout.

Phản hồi ra ngoài cần cho client biết yêu cầu chưa được thực hiện và cách xử lý phù hợp, nhưng không lộ dữ liệu nhạy cảm về tài nguyên hay chính sách.

Các chỉ số hữu ích gồm tỷ lệ lỗi kiểm tra bắt buộc, số request bị chặn do phụ thuộc, thời gian chờ, số quyết định cache hết hiệu lực và backlog công việc chưa được phép chạy.

## 13. Kiểm thử lỗi chủ động

Fail closed không chỉ được kiểm tra bằng request của người thiếu quyền. Cần chủ động tạo lỗi ở những điểm kiểm soát có liên quan.

| Tình huống lỗi | Điều phải xác nhận |
| --- | --- |
| PDP hết thời gian chờ | Hành động được bảo vệ không chạy |
| PDP trả kết quả rỗng hoặc sai định dạng | Không bị diễn giải thành cho phép |
| Không đọc được kho phiên | Không tạo danh tính đã đăng nhập từ dữ liệu chưa xác minh |
| Không tải được khóa chưa biết của token | Không bỏ qua kiểm tra chữ ký |
| Có khóa tin cậy còn hiệu lực trong cache | Hành vi phù hợp với hợp đồng xác minh đã định |
| Không đọc được quan hệ thành viên | Không cấp tư cách thành viên mặc định |
| Thiếu tenant context | Không bỏ bộ lọc tenant hoặc xử lý toàn hệ thống |
| Dịch vụ MFA không phản hồi | Không đánh dấu xác thực tăng cường đã hoàn tất |
| Cache quyền hết hiệu lực | Không tự kéo dài thời hạn mà không đủ căn cứ |
| Không ghi được audit bắt buộc | Áp dụng điều kiện thực thi đã định |
| Circuit breaker đang mở | Không dùng nhánh dự phòng để cho phép vô điều kiện |
| Một bước kiểm tra lỗi giữa tác vụ nhiều bước | Không tạo thêm tác động ngoài phạm vi đã được xác lập |
| Nguồn IAM phục hồi sau sự cố | Tác vụ chờ được đánh giá đúng trước khi tiếp tục |
| Endpoint công khai không phụ thuộc kiểm tra bị lỗi | Có thể tiếp tục theo đúng chính sách công khai |

Ngoài response, phải kiểm tra cơ sở dữ liệu, tệp xuất, thông báo, sự kiện và tác động bên ngoài. Nếu request trả lỗi nhưng tệp đã được gửi đi, kiểm soát chưa fail closed tại điểm cần thiết.

Cũng cần có trường hợp thành công sau phục hồi để xác nhận hệ thống trở lại hoạt động bằng chính sách hợp lệ, thay vì chỉ kiểm tra rằng mọi thao tác đều bị chặn.

## 14. Áp dụng vào yêu cầu xuất hợp đồng của Lan

Lan có một phiên hợp lệ và yêu cầu xuất hợp đồng của An Bình. API cần xác nhận quyền xuất còn phù hợp và các điều kiện bắt buộc khác trước khi tạo job.

Nếu nguồn trạng thái thành viên không hoạt động, hệ thống xem bằng chứng hiện có có còn đáp ứng chính sách của thao tác xuất không. Nếu chưa đủ, API không tạo job và ghi nhận lỗi đánh giá.

Nếu có một bằng chứng cache còn hợp lệ và được chính sách chấp nhận cho đúng request, việc dùng nó phải giữ nguyên phạm vi, thời hạn và điều kiện; không mở rộng sang mọi hợp đồng hoặc mọi tenant.

Khi dịch vụ phục hồi, Lan có thể gửi lại yêu cầu theo hợp đồng retry của ứng dụng. Hệ thống đánh giá lại và chỉ xuất dữ liệu khi có quyết định cho phép hợp lệ.

Fail closed giữ cho sự cố kiểm soát không tự biến thành cơ hội vượt quyền. Khả năng vận hành được duy trì bằng thiết kế phụ thuộc, bằng chứng có hiệu lực và quy trình phục hồi rõ ràng, thay vì bỏ kiểm tra khi hệ thống gặp khó khăn.
