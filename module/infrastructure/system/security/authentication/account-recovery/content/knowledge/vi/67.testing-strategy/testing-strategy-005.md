# Recovery provider tests — Kiểm thử nhà cung cấp trong luồng khôi phục tài khoản

## 1. Mục tiêu và phạm vi

Một luồng khôi phục tài khoản có thể phụ thuộc vào dịch vụ gửi email, SMS, dịch vụ xác minh mã, nhà cung cấp xác minh danh tính hoặc hệ thống định danh của tổ chức. Trong bài này, **recovery provider** là thành phần cung cấp một năng lực bên ngoài miền điều phối khôi phục; nó có thể là dịch vụ từ xa hoặc một implementation nội bộ đứng sau cùng interface.

Kiểm thử provider phải trả lời hai câu hỏi: tích hợp có trao đổi đúng hợp đồng không, và kết quả tích hợp có làm hệ thống cấp đúng quyền khôi phục không. Một HTTP response thành công chỉ trả lời được một phần rất nhỏ của câu hỏi đầu tiên.

Ví dụ, provider đã nhận yêu cầu gửi email nhưng người dùng chưa nhận được thư. SMS đã được chuyển phát nhưng người nhập mã chưa chắc là chủ tài khoản cần khôi phục. Một hồ sơ xác minh danh tính đạt yêu cầu cũng chưa tự chứng minh hồ sơ ấy được gắn đúng tài khoản, đúng tenant và đúng yêu cầu khôi phục.

Trong phạm vi khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, người học cần biết cách:

- Phân biệt trạng thái chuyển phát với bằng chứng xác minh.
- Kiểm thử adapter, hợp đồng giao tiếp và ảnh hưởng tới trạng thái miền.
- Mô phỏng lỗi mạng, kết quả chưa xác định, retry và chuyển provider.
- Kiểm tra callback có xác thực, chống xử lý lặp và gắn đúng ngữ cảnh.
- Xác minh sự cố provider không vô tình bỏ qua kiểm soát rủi ro, sửa credential hoặc tạo session có quyền.
- Giữ bộ test xác định được kết quả, tái hiện được lỗi và không gửi thông tin đến người dùng thật.

Bài sử dụng một hợp đồng minh họa do ứng dụng tự định nghĩa. Tên trạng thái, endpoint, mã lỗi và thời hạn trong ví dụ đều cần được ánh xạ sang hợp đồng thực tế trước khi triển khai.

## 2. Tách trách nhiệm của provider khỏi quyết định khôi phục

Một lỗi thiết kế thường gặp là gom mọi kết quả thành boolean `success`. Khi đó, `success=true` có thể đồng thời mang nghĩa “đã xếp hàng gửi thư”, “mã đã đúng” hoặc “được phép thay MFA”. Bộ test khó phát hiện việc các ý nghĩa này bị đánh tráo.

| Vai trò | Kết quả provider có thể xác nhận | Điều ứng dụng vẫn phải xác minh |
|---|---|---|
| Chuyển phát email hoặc SMS | Yêu cầu được nhận, bị từ chối, hoặc có báo cáo chuyển phát | Người dùng đã cung cấp bằng chứng hợp lệ chưa |
| Xác minh mã hoặc challenge | Mã khớp một challenge theo hợp đồng | Challenge thuộc attempt, tenant, tài khoản, mục đích và phiên bản nào |
| Xác minh danh tính | Hồ sơ hoặc kiểm tra đạt một mức yêu cầu | Danh tính đã được liên kết với chủ tài khoản bằng quy tắc nào |
| Hệ thống định danh tổ chức | Kết quả xác thực hoặc quản trị từ một nguồn tin cậy | Nguồn ấy có thẩm quyền với tài khoản và hành động khôi phục đang xét không |
| Thành phần điều phối nội bộ | Áp dụng policy và chuyển trạng thái khôi phục | Các ràng buộc, giao dịch và tác động lên credential/session có đúng không |

Việc gửi email có thể kết thúc ở trạng thái `ACCEPTED` hoặc `DELIVERED`. Hai trạng thái ấy không phải bằng chứng đủ để đổi mật khẩu. Một kết quả xác minh mã có thể tạo ra `Evidence`, nhưng policy còn có thể yêu cầu thêm bằng chứng độc lập, thời gian chờ hoặc duyệt thủ công.

Với passkey, một provider xác minh danh tính không tái tạo được khóa riêng của passkey đã mất. Luồng được phép có thể dẫn đến đăng ký một authenticator mới sau khi đủ điều kiện. Test phải kiểm tra đúng hành động được cấp; không coi “recovery approved” là quyền thực hiện mọi thao tác bảo mật.

### Những bất biến cần làm oracle

**Oracle kiểm thử** là quy tắc dùng để quyết định một kết quả có đúng hay không. Với bài này, các bất biến của ứng dụng minh họa là:

1. Chỉ có kết quả chuyển phát thì chưa phát sinh recovery grant.
2. Bằng chứng khác tenant, khác subject, khác mục đích hoặc khác thế hệ challenge không được dùng.
3. Attempt đã hết hạn, bị hủy hoặc bị thay thế không được hồi sinh bởi phản hồi đến muộn.
4. Một sự kiện hợp lệ được xử lý nhiều lần không làm tăng số lần cấp quyền hoặc thay credential.
5. Kết quả không xác định của provider không được chuyển thành bằng chứng xác minh thành công.
6. Khi policy chưa cho phép, mật khẩu, MFA, danh sách passkey và quyền của session hiện hữu vẫn tuân theo trạng thái trước đó.
7. Khi khôi phục thực sự hoàn tất, các thay đổi credential và biện pháp kiểm soát session phải khớp policy đã chọn.

Các bất biến này là hợp đồng thiết kế của ví dụ, không phải lời khẳng định rằng mọi sản phẩm phải dùng cùng một state machine.

## 3. Mô hình dữ liệu kiểm thử và ràng buộc ngữ cảnh

Một fixture có ích cần chứa đủ thông tin để phát hiện việc gắn nhầm kết quả. Chỉ tạo `userId=1` và một provider giả luôn thành công sẽ che khuất hầu hết lỗi nguy hiểm.

Ví dụ một recovery attempt trong kho dữ liệu test:

```text
attemptId          = attempt-a7
tenantId           = tenant-blue
accountId          = account-17
purpose            = REPLACE_LOST_MFA
challengeGeneration= 4
providerBinding    = provider-p / provider-account-blue / test
providerOperationId= operation-91
trustedSubjectRef  = subject-blue-17
channelSnapshot    = channel-version-8
policyVersion      = policy-12
state              = AWAITING_EVIDENCE
expiresAt          = 2030-01-01T00:10:00Z
```

Các giá trị ngày giờ chỉ là dữ liệu cố định cho test. Không lấy thời gian hiện tại của máy làm mốc hết hạn.

Tạo thêm các fixture “gần giống nhưng không đúng”:

- Cùng `accountId` biểu diễn bên ngoài nhưng thuộc tenant khác.
- Cùng provider nhưng khác tài khoản dịch vụ hoặc khác môi trường.
- Cùng người dùng nhưng attempt khác, purpose khác hoặc challengeGeneration cũ.
- Kênh liên hệ đã thay đổi sau khi attempt được tạo.
- Attempt có trạng thái `CANCELLED`, `EXPIRED` hoặc đã hoàn tất.

`providerOperationId` không nên được giả định là duy nhất trên toàn bộ mọi provider. Kho ánh xạ cần thể hiện namespace thực của hợp đồng, chẳng hạn provider, tài khoản provider và môi trường. Nếu một tài khoản provider phục vụ nhiều tenant, ứng dụng phải lưu ánh xạ tin cậy từ operation đến attempt và tenant; không dùng trường `tenantId` do callback tự khai làm căn cứ duy nhất.

`trustedSubjectRef` cũng cần có nguồn gốc rõ ràng. Một định danh bên ngoài chỉ có ý nghĩa khi nó được liên kết với tài khoản nội bộ qua quy trình được kiểm soát. Test cần có trường hợp cùng một tên hoặc địa chỉ hiển thị nhưng khác subject ổn định.

## 4. Chia tầng kiểm thử theo điều cần chứng minh

| Tầng | Thành phần thật | Thành phần kiểm soát được | Lỗi có thể phát hiện |
|---|---|---|---|
| Unit test policy | Luật chấp nhận bằng chứng và state machine | Provider trả kết quả chuẩn hóa | Chấp nhận nhầm purpose, bằng chứng quá hạn hoặc thiếu điều kiện |
| Adapter test | Serializer, HTTP client, parser, ánh xạ lỗi | HTTP stub hoặc server cục bộ | Sai header, mất trường, hiểu sai trạng thái |
| Contract test | Adapter và bộ mẫu hợp đồng | Schema, fixture được quản lý hoặc sandbox | Hợp đồng drift, enum mới, trường bắt buộc đổi |
| Integration test | Repository, transaction, inbox/outbox, scheduler | Provider giả có kịch bản lỗi | Race, ghi dở dang, retry tạo tác động kép |
| End-to-end có kiểm soát | Luồng bắt đầu đến thay credential và kiểm soát session | Kênh test và tài khoản tổng hợp | Ghép sai các bước hoặc grant có quyền quá rộng |

Mock trực tiếp một interface phù hợp cho unit test policy. Nó không kiểm tra HTTP timeout, mã hóa request, TLS, redirect hay byte gốc dùng xác minh chữ ký. Vì vậy cần ít nhất một tầng đi qua adapter thật và một tầng đi qua lưu trữ thật.

Sandbox là bằng chứng bổ sung cho khả năng tương tác. Nó thường không thể tạo mọi tình huống như “provider đã ghi nhận tác động nhưng kết nối bị cắt trước response”. Những tình huống ấy cần fault injection trong môi trường cục bộ.

Một bộ contract test do consumer tự viết chỉ chứng minh adapter khớp các giả định đang lưu. Mức tin cậy cao hơn khi fixture/schema được đối chiếu với tài liệu phiên bản cụ thể, mẫu hợp lệ do provider cung cấp hoặc kiểm tra sandbox có kiểm soát.

## 5. Kiểm thử request và response của adapter

Giả sử adapter gọi một dịch vụ xác minh minh họa:

```http
POST /v1/checks HTTP/1.1
Host: verification.example.test
Authorization: Bearer <credential-do-test-inject>
Idempotency-Key: operation-91

{
  "subject_reference": "subject-blue-17",
  "purpose": "replace_lost_mfa",
  "challenge_reference": "challenge-a7-g4",
  "callback_reference": "callback-binding-61"
}
```

Đây là endpoint giả. Test cục bộ phải ánh xạ nó tới server kiểm soát được hoặc inject base URL cục bộ, không thực hiện network call ra ngoài.

### 5.1. Assertions ở chiều gửi

Test nên xác minh phương thức, đường dẫn, nội dung cần thiết và ràng buộc của request:

- Credential được chọn từ cấu hình tin cậy của đúng provider account.
- Operation retry sử dụng lại định danh đã được lưu.
- Purpose và challenge reference khớp attempt được cấp ownership.
- Callback URL, redirect URL và recovery URL xuất phát từ cấu hình được kiểm soát.
- Dữ liệu gửi đi chỉ gồm những trường provider thực sự cần.
- Serialization giữ đúng ký tự, kiểu dữ liệu và giới hạn độ dài.
- Client không tự động chuyển credential sang một host khác khi gặp redirect ngoài hợp đồng.

Nếu provider cần email hoặc số điện thoại để gửi thông điệp, test kiểm tra giá trị đến từ kênh đã được policy chọn, không lấy trực tiếp một địa chỉ mới do người gửi yêu cầu khôi phục nhập vào. Việc thay kênh liên hệ cần có luồng và mức xác minh riêng.

Đối với link khôi phục, fixture có thể dùng một token tổng hợp đã biết để kiểm tra template và URL encoding. Log, trace và báo cáo lỗi không được giữ token ấy. Không đưa token có hiệu lực vào snapshot được commit hoặc artifact CI.

### 5.2. Assertions ở chiều nhận

Định nghĩa kết quả miền cụ thể thay cho boolean:

```text
Accepted(providerOperationId)
Rejected(reasonCategory)
TemporarilyUnavailable(retryHint)
UnknownOutcome(operationId)
VerifiedEvidence(binding, evidenceType, observedAt)
InvalidProviderResponse(reasonCategory)
```

Không phải provider nào cũng hỗ trợ tất cả loại kết quả. Adapter chuyển dữ liệu theo hợp đồng của chính nó, còn orchestration quyết định bước tiếp theo.

Ma trận tối thiểu ở chiều nhận:

| Phản hồi mô phỏng | Kết quả mong đợi của ví dụ |
|---|---|
| 2xx, body báo accepted và có reference hợp lệ | Chỉ ghi nhận tác vụ đã được nhận |
| 2xx nhưng thiếu operation reference bắt buộc | Lỗi giao thức; không suy ra verified |
| 2xx nhưng body báo rejected | Ánh xạ trạng thái nghiệp vụ bị từ chối |
| 2xx với enum chưa biết | Không cấp bằng chứng; phát tín hiệu contract drift |
| 2xx với trường tùy chọn mới | Chấp nhận nếu hợp đồng cho phép mở rộng |
| JSON hỏng, content type sai hoặc body quá lớn | Từ chối trong giới hạn tài nguyên đã cấu hình |
| 401 hoặc 403 theo hợp đồng | Báo lỗi cấu hình/quyền; không retry dồn dập |
| 429 hoặc 5xx | Áp dụng quy tắc retry riêng của provider và ngân sách còn lại |
| Redirect ra host khác | Không rò credential hoặc tự mở rộng đích gọi |

Việc một mã lỗi có retry được hay không phải dựa trên tài liệu endpoint và tính chất thao tác. Mã HTTP đơn lẻ không chứng minh thao tác chưa gây tác động ở phía provider.

Kiểm tra cả malformed error response. Một parser lỗi không được nuốt exception rồi trả về trạng thái thành công mặc định. Trường mới nên được xử lý theo nguyên tắc tương thích đã định nghĩa; trường bắt buộc thiếu hoặc giá trị liên quan bảo mật không nhận diện được cần dừng cấp bằng chứng.

## 6. Timeout, retry và kết quả chưa xác định

### 6.1. Timeout không chứng minh provider chưa thực hiện

Xét chuỗi sau:

```text
Ứng dụng                       Provider
    | POST operation-91            |
    |----------------------------->|
    |                              | tạo challenge / gửi thông điệp
    |                mất kết nối   |
    |<------------- X -------------|
    | không nhận được response     |
```

Từ phía ứng dụng, kết quả là chưa xác định. Nếu mỗi retry lại tạo một operation mới, người dùng có thể nhận nhiều challenge khác nhau hoặc nhiều thông điệp, trong khi hệ thống chỉ lưu một phần lịch sử.

Kịch bản test cần cố tình làm provider giả **ghi nhận tác động trước**, sau đó đóng kết nối. Chỉ mô phỏng “ném exception trước khi gọi provider” không kiểm tra được lỗi này.

Với hợp đồng idempotency được provider hỗ trợ, test xác minh các lần thử của cùng operation giữ nguyên key, cùng ý nghĩa payload và không vượt thời hạn hiệu lực của key. Cùng key nhưng đổi subject hoặc purpose phải bị phát hiện, thay vì được coi là một retry hợp lệ. Đây là cách áp dụng ý tưởng định danh yêu cầu trong [AWS Builders’ Library: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

Nếu provider không có cơ chế idempotency hoặc tra cứu trạng thái đáng tin cậy, ứng dụng không thể tự tuyên bố exactly-once cho tác động từ xa. Test phải phản ánh giới hạn đó: operation có thể chuyển sang chờ đối soát, hết hạn an toàn hoặc chuyển xử lý theo policy đã được định nghĩa.

### 6.2. Một kịch bản retry có thời gian ảo

Ví dụ chính sách test: tối đa ba lần gửi tổng cộng, thời gian chờ lần lượt do scheduler ảo điều khiển, và không gửi thêm khi attempt đã hết hạn. Đây là cấu hình minh họa, không phải mức mặc định cho production.

```text
Given:
  attempt còn hạn; operation-91 đã được lưu
  lần 1: provider ghi tác động, sau đó read timeout
  lần 2: provider nhận cùng key, trả lại reference của tác động cũ

When:
  chạy lần 1
  tiến thời gian ảo tới lịch retry
  chạy lần 2

Then:
  có 2 HTTP invocation
  chỉ có 1 tác động nghiệp vụ ở provider giả
  cả hai request dùng operation-91
  local attempt vẫn chưa có bằng chứng verified
  chưa có recovery grant hay credential mutation
```

Phải phân biệt số lần gọi HTTP với số tác động nghiệp vụ. Đếm invocation bằng một không phải mục tiêu đúng cho một cơ chế retry.

### 6.3. Các biến thể cần có

- Connect timeout, read timeout và lỗi giữa lúc đọc body.
- Timeout sau khi provider tạo challenge nhưng trước khi local lưu reference.
- 429 có hướng dẫn chờ hợp lệ, thiếu hoặc không parse được.
- Thời điểm retry nằm ngoài tuổi thọ attempt hoặc ngoài cửa sổ idempotency.
- Hai instance cùng claim một outbox item.
- SDK tự retry cộng với retry của ứng dụng làm tăng tổng số request.
- Circuit breaker đang mở, vừa đóng lại hoặc đang thử thăm dò.
- Hủy attempt khi một invocation còn chạy; response thành công đến sau phải kiểm tra lại trạng thái hiện tại.

Inject clock, scheduler và nguồn jitter có seed để test điều khiển được thứ tự. Một assertion dùng `Thread.sleep` dài rồi hy vọng callback đã chạy sẽ vừa chậm vừa khó phân biệt lỗi logic với máy CI bận.

## 7. Callback và webhook: kiểm tra cả nguồn gốc lẫn ngữ cảnh

Webhook thường đi qua nhiều lớp: reverse proxy, HTTP framework, middleware parse body và handler nghiệp vụ. Test phải đi qua những lớp có thể làm thay đổi dữ liệu được ký, không chỉ gọi trực tiếp một method với object đã được đánh dấu hợp lệ.

Với cơ chế chữ ký trên payload, cách lấy byte gốc, thuật toán, phần dữ liệu được ký và giới hạn thời gian phải khớp hợp đồng provider. Sau xác thực nguồn gửi, ứng dụng vẫn cần chống xử lý lặp và xác minh operation thuộc attempt nào. Các nguyên tắc này được trình bày trong [OWASP Webhook Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html); bộ tình huống dưới đây là thiết kế kiểm thử cho ứng dụng minh họa.

### 7.1. Ma trận xác thực callback

| Tình huống | Điều phải quan sát |
|---|---|
| Chữ ký đúng cho byte gốc và key được phép | Callback được phép đi tiếp tới kiểm tra ngữ cảnh |
| Sửa một byte trong body sau khi ký | Không tạo evidence hoặc chuyển trạng thái |
| Thiếu chữ ký, sai định dạng hoặc sai thuật toán | Từ chối theo hợp đồng, không fallback sang chế độ bỏ xác thực |
| Chữ ký đúng nhưng dùng secret của provider account khác | Không gắn kết quả sang attempt hiện tại |
| Body bị middleware parse rồi serialize lại | Verifier vẫn dùng dữ liệu đúng như hợp đồng yêu cầu |
| Timestamp nằm ngoài cửa sổ đã cấu hình | Xử lý theo quy tắc freshness của provider, không tự kéo dài thời hạn attempt |
| Key mới và key cũ trong giai đoạn rotation | Chỉ tập key được phê duyệt còn hiệu lực được sử dụng |
| Key cũ đã bị thu hồi | Không còn được chấp nhận sau mốc hiệu lực |
| Kích thước body vượt giới hạn | Dừng sớm, không chiếm bộ nhớ không giới hạn |

Không phải mọi provider đều có timestamp ký hoặc cùng cơ chế xác thực. Nếu hợp đồng không cung cấp freshness theo timestamp, cần kiểm thử biện pháp được thiết kế thay thế, chẳng hạn đối soát trạng thái qua API đã xác thực và quản lý operation một lần. Không bịa thêm một header rồi coi nó là bảo đảm do provider cung cấp.

Key ID hoặc thông tin định tuyến trong request chỉ được dùng để tìm trong tập cấu hình đã được tin cậy. Test cần chứng minh chúng không thể kích hoạt việc tải key từ URL tùy ý hoặc lựa chọn secret của tenant bất kỳ.

### 7.2. Chữ ký hợp lệ chưa đủ

Tạo một callback được ký đúng bằng secret test nhưng có operation reference thuộc tenant khác. Callback này đã vượt qua lớp xác thực transport, song vẫn phải bị chặn trước khi tạo bằng chứng cho tài khoản đích.

Lần lượt thay đổi từng thành phần:

```text
providerId
providerAccount
environment
operationId
attemptId hoặc ánh xạ operation -> attempt
account/subject binding
purpose
challengeGeneration
```

Nếu callback không mang đủ các trường trên, ứng dụng lấy chúng từ ánh xạ local đã được tạo khi khởi tạo operation. Test không nên tự thêm những field mà provider thật không gửi, vì cách đó có thể tạo cảm giác an toàn giả.

Một receipt `DELIVERED` cho email hoặc SMS không thể trở thành `VerifiedEvidence`. Một kết quả `VERIFIED` cho purpose đăng nhập thông thường cũng không mặc nhiên đủ để tháo MFA hoặc đăng ký passkey mới. Test phải kiểm tra điểm ánh xạ giữa vocabulary của provider và vocabulary miền.

### 7.3. Replay và xử lý lặp

Đối với provider có event ID ổn định, một khóa khử trùng có thể là:

```text
(providerId, providerAccount, environment, eventId)
```

Phạm vi khóa phải theo tính duy nhất mà provider công bố. Không giả định event ID duy nhất toàn cầu nếu hợp đồng chỉ bảo đảm trong một tài khoản.

Kịch bản test quan trọng:

1. Gửi event chưa xác thực với một event ID đã đoán được.
2. Gửi event thật, xác thực hợp lệ, có cùng ID.
3. Xác minh lần gửi giả không chiếm trước khóa dedup và chặn mất event thật.
4. Gửi lại event thật nhiều lần, gồm cả đồng thời trên hai instance.
5. Xác minh chỉ một lần áp dụng bằng chứng và tối đa một lần phát sinh tác động miền theo policy.

Có hai mẫu xử lý thường gặp. Handler có thể áp dụng thay đổi miền và đánh dấu event trong cùng transaction. Hoặc handler xác thực rồi ghi event vào inbox bền vững; consumer áp dụng thay đổi và đánh dấu xử lý bằng giao dịch phù hợp. Test phải thể hiện đúng mẫu đang dùng.

Nếu trả 2xx trước khi event được lưu bền vững, một crash có thể làm mất sự kiện vì provider tưởng đã giao xong. Nếu lưu “đã xử lý” trước khi thực hiện thay đổi miền, crash có thể làm bỏ sót tác động. Cần chèn lỗi giữa các bước ấy để chứng minh cơ chế recovery của inbox.

### 7.4. Event đến muộn và sai thứ tự

Các chuỗi cần thử gồm:

```text
ACCEPTED -> DELIVERED
DELIVERED -> ACCEPTED
VERIFIED -> cùng VERIFIED gửi lại
CANCELLED cục bộ -> VERIFIED đến muộn
EXPIRED cục bộ -> VERIFIED có observedAt trước expiresAt
operation cũ -> callback sau khi tạo challengeGeneration mới
```

Không sắp xếp trạng thái bằng timestamp đơn thuần nếu provider không bảo đảm thứ tự ấy. Nếu cần quyết định dựa trên trạng thái authoritative, mô phỏng cả API đối soát và sự cố của API đó.

Trong hợp đồng ví dụ, attempt đã hết hạn ở thời điểm ứng dụng chấp nhận bằng chứng không được cấp quyền, kể cả callback khai thời điểm xác minh trước đó. Một sản phẩm cho phép khoảng trễ nhận kết quả phải định nghĩa khoảng trễ, nguồn thời gian và các điều kiện bổ sung một cách rõ ràng; test sẽ được viết theo policy ấy.

## 8. Ví dụ Java: kiểm thử điều kiện sử dụng bằng chứng

Đoạn dưới minh họa một unit test bằng Java 17 và JUnit 5. Nó không gọi provider thật. Kiểu `Evidence` ở đây đại diện dữ liệu đã đi qua xác thực callback và đối chiếu operation; trong hệ thống thực, không được cho controller tạo dữ liệu “đã xác thực” chỉ từ field người gọi gửi.

Hàm được kiểm tra chỉ quyết định evidence có đủ điều kiện để policy xem xét tiếp hay không. Nó chưa cấp grant, chưa thay credential và chưa thay thế các test transaction hoặc chữ ký.

```java
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProviderEvidencePolicyTest {
    enum State { AWAITING_EVIDENCE, CANCELLED, COMPLETED }
    enum Kind { DELIVERY_RECEIPT, VERIFIED_CHALLENGE }

    record Binding(
            String providerId,
            String providerAccount,
            String environment,
            String tenantId,
            String accountId,
            String attemptId,
            String operationId,
            String purpose,
            int generation) {}

    record Attempt(
            Binding binding,
            State state,
            Instant createdAt,
            Instant expiresAt) {}

    record Evidence(
            Binding binding,
            Kind kind,
            Instant observedAt) {}

    static final Instant START =
            Instant.parse("2030-01-01T00:00:00Z");
    static final Instant DEADLINE = START.plusSeconds(600);

    static Binding binding(String tenant, int generation) {
        return new Binding(
                "provider-p", "provider-account-blue", "test",
                tenant, "account-17", "attempt-a7", "operation-91",
                "REPLACE_LOST_MFA", generation);
    }

    static Attempt attempt(State state) {
        return new Attempt(
                binding("tenant-blue", 4), state, START, DEADLINE);
    }

    static boolean eligible(
            Attempt attempt, Evidence evidence, Instant now) {
        return attempt.state() == State.AWAITING_EVIDENCE
                && evidence.kind() == Kind.VERIFIED_CHALLENGE
                && attempt.binding().equals(evidence.binding())
                && !now.isBefore(attempt.createdAt())
                && now.isBefore(attempt.expiresAt())
                && !evidence.observedAt().isBefore(attempt.createdAt())
                && !evidence.observedAt().isAfter(now)
                && evidence.observedAt().isBefore(attempt.expiresAt());
    }

    static Evidence verified(String tenant, int generation) {
        return new Evidence(
                binding(tenant, generation),
                Kind.VERIFIED_CHALLENGE,
                START.plusSeconds(60));
    }

    @Test
    void matchingEvidenceCanBeConsideredBeforeDeadline() {
        assertTrue(eligible(
                attempt(State.AWAITING_EVIDENCE),
                verified("tenant-blue", 4),
                START.plusSeconds(90)));
    }

    @Test
    void deliveryReceiptDoesNotProveChallengeCompletion() {
        var receipt = new Evidence(
                binding("tenant-blue", 4),
                Kind.DELIVERY_RECEIPT,
                START.plusSeconds(60));

        assertFalse(eligible(
                attempt(State.AWAITING_EVIDENCE),
                receipt, START.plusSeconds(90)));
    }

    @Test
    void evidenceFromAnotherTenantIsRejected() {
        assertFalse(eligible(
                attempt(State.AWAITING_EVIDENCE),
                verified("tenant-red", 4),
                START.plusSeconds(90)));
    }

    @Test
    void previousChallengeGenerationIsRejected() {
        assertFalse(eligible(
                attempt(State.AWAITING_EVIDENCE),
                verified("tenant-blue", 3),
                START.plusSeconds(90)));
    }

    @Test
    void deadlineIsExclusiveEvenIfProviderVerifiedEarlier() {
        assertFalse(eligible(
                attempt(State.AWAITING_EVIDENCE),
                verified("tenant-blue", 4), DEADLINE));
    }

    @Test
    void terminalAttemptCannotBeReactivated() {
        for (var state : new State[] {
                State.CANCELLED, State.COMPLETED }) {
            assertFalse(eligible(
                    attempt(state),
                    verified("tenant-blue", 4),
                    START.plusSeconds(90)));
        }
    }
}
```

Khi mở rộng bộ test, dùng test tham số hóa để lần lượt thay provider account, environment, account, purpose và operation. Không chỉ có một test đổi tenant rồi suy ra toàn bộ các ràng buộc khác đã được kiểm chứng.

Ví dụ trên dùng so sánh thời gian chặt để dễ thấy điều kiện biên. Nếu hợp đồng provider có sai lệch đồng hồ cho phép, phần chuẩn hóa và xác thực thời gian phải được kiểm thử riêng, với giới hạn cụ thể. Thời hạn attempt và cửa sổ xác thực chữ ký là hai quy tắc khác nhau.

## 9. Kiểm thử giao dịch, inbox/outbox và cạnh tranh

Provider không tham gia transaction cơ sở dữ liệu local. Vì vậy test cần chủ động tạo các điểm dừng giữa lưu operation, gọi API, nhận callback và ghi trạng thái.

### 9.1. Khởi tạo operation

Một mẫu thiết kế là lưu attempt, operation và outbox item trong cùng transaction. Sau commit, dispatcher mới gọi provider.

Kiểm thử:

- Rollback transaction tạo attempt thì không có outbox item có thể được gửi.
- Crash sau commit nhưng trước khi dispatch vẫn cho phép worker lấy lại tác vụ.
- Hai dispatcher cạnh tranh không làm mất quyền sở hữu operation.
- Dispatcher bị dừng sau tác động từ xa thì việc chạy lại vẫn giữ định danh operation.
- Outbox item hết lease không làm retry vô hạn ngoài tuổi thọ attempt.
- Attempt đã hủy trước dispatch không còn được gửi chỉ vì item cũ vẫn nằm trong queue.

Outbox bảo đảm ý định gửi được lưu cùng dữ liệu local theo thiết kế này. Nó không tự cung cấp exactly-once ở provider; phần đó còn phụ thuộc hợp đồng từ xa.

### 9.2. Callback đến trước response

Một race thực tế là provider gửi callback rất nhanh trong khi HTTP request khởi tạo còn chưa trả response. Nếu ứng dụng chỉ tạo ánh xạ operation sau response, handler có thể không tìm thấy attempt.

Test cần điều khiển lịch:

```text
1. Local lưu operation và reference tương quan được phép dùng.
2. Provider giả tiếp nhận request.
3. Provider giả phát callback trước khi trả response.
4. Callback đi qua xác thực, inbox và đối chiếu context.
5. HTTP response khởi tạo mới được thả ra.
6. Consumer xử lý đến trạng thái nhất quán.
```

Nếu hợp đồng chỉ cho biết operation ID sau response, thiết kế cần một cơ chế đối soát hoặc lưu callback chờ ghép đã được xác thực và có giới hạn. Test kiểm tra cả trường hợp callback không bao giờ ghép được: hết hạn, cảnh báo và không cấp quyền.

### 9.3. Hai callback hợp lệ cùng lúc

Dùng barrier hoặc latch để hai transaction cùng nhìn thấy trạng thái ban đầu, rồi cho phép chúng cạnh tranh khi cập nhật. Chạy qua database thật của môi trường test để kiểm chứng unique constraint, locking hoặc compare-and-set đang dùng.

Sau khi cả hai kết thúc, kiểm tra:

- Một chuyển trạng thái nghiệp vụ hợp lệ được ghi nhận.
- Không có hai recovery grant còn hiệu lực cho cùng quyết định một lần của ví dụ.
- Không tăng credential version hai lần.
- Không tạo hai thông báo hoàn tất hoặc hai yêu cầu thu hồi session ngoài semantics đã định.
- Transaction thất bại có đường retry an toàn và không làm event bị đánh dấu xử lý nhầm.

Không dùng một mock repository lưu vào map rồi kết luận database production xử lý race đúng. Ngược lại, cũng không cần ép provider chỉ gửi một callback; hệ thống phải chịu được giao lặp theo hợp đồng.

### 9.4. Phạm vi transaction khi hoàn tất khôi phục

Nếu thay credential và đánh dấu grant đã dùng là một hành động local, test cần xác minh rollback không để lại trạng thái nửa chừng. Nếu session ở dịch vụ khác, thường không thể giả định một transaction bao trùm tất cả.

Thiết kế có thể dùng auth version, trạng thái hạn chế truy cập hoặc sự kiện thu hồi session qua outbox. Assertion phải kiểm tra đúng biện pháp đã chọn: session cũ không tiếp tục có quyền trái policy trong khoảng trễ, thông điệp thu hồi được giao lại khi lỗi, và API không báo hoàn tất theo nghĩa mạnh hơn bảo đảm thực tế.

## 10. Chuyển provider và fallback có giữ nguyên mức bảo đảm không

Khi nhà cung cấp A lỗi, việc chuyển sang B có thể cải thiện khả dụng nhưng cũng tạo thêm đường để tấn công luồng khôi phục. Đặc biệt nguy hiểm nếu “dịch vụ xác minh danh tính đang lỗi” tự động biến thành “chỉ cần email”.

Tách hai tình huống:

**Đổi tuyến chuyển phát cùng năng lực.** Ví dụ dùng nhà cung cấp email khác để gửi cùng loại thông điệp tới kênh đã được chọn. Cần kiểm thử idempotency, nội dung, reference, callback và chi phí gửi lặp. Hai provider có thể không chia sẻ idempotency key, nên cùng một intent có thể tạo hai lần chuyển phát nếu A thực tế đã nhận trước khi timeout.

**Đổi phương thức chứng minh.** Ví dụ chuyển từ một tổ hợp bằng chứng sang một phương thức khác. Chỉ thực hiện khi policy cho phép mức bảo đảm tương ứng. Test phải chứng minh thiếu provider không tự biến thành quyền bỏ MFA, bỏ thời gian chờ hoặc sử dụng địa chỉ mới chưa được xác minh.

Ma trận fallback nên có:

| Điểm gây lỗi | Câu hỏi cần kiểm tra |
|---|---|
| A từ chối rõ ràng trước tác động | B có được policy cho phép và nhận đúng context không |
| A timeout sau tác động | Có đối soát hoặc xử lý được rủi ro hai thao tác cùng tồn tại không |
| A trả kết quả sau khi B đã được chọn | Operation cũ còn đủ điều kiện đóng góp bằng chứng không |
| A gửi callback sau khi challenge mới thay thế | Generation cũ có bị loại theo policy không |
| B khác provider account của tenant | Routing có giữ đúng credential và namespace không |
| Cả A lẫn B lỗi | Luồng có chờ, hết hạn hoặc đi vào hỗ trợ được kiểm soát không |

Trong thiết kế thay thế operation của ví dụ, operation mới đi kèm một challengeGeneration mới và operation cũ bị đánh dấu superseded. Nếu thiết kế chủ động cho nhiều operation cùng hoạt động, cần kiểm thử luật gộp bằng chứng để cùng một yếu tố không bị tính thành hai yếu tố độc lập.

Fallback cũng không được vô hiệu hóa rate limit. Mọi tuyến cùng phục vụ một yêu cầu cần được tính vào ngân sách lạm dụng phù hợp, bên cạnh quota riêng từng provider.

## 11. Kết quả provider phải dẫn đến đúng quyền của tài khoản và session

Bộ test tích hợp nên có snapshot trước và sau của trạng thái bảo mật. Snapshot không chứa mật khẩu thô, token, private key hoặc dữ liệu xác minh danh tính đầy đủ.

Có thể ghi nhận các giá trị kiểm tra như:

```text
credentialVersion
passwordHashChanged
mfaEnrollmentCount
activePasskeyIds
activeRecoveryGrantCount
authVersion
existingSessionAuthorizationResult
recoveryNotificationOutboxCount
```

Đối với thao tác chỉ gửi email, timeout, callback chữ ký sai hoặc evidence không khớp, kiểm tra không phát sinh recovery grant hay thay đổi credential. Với thao tác đã được policy chấp nhận và người dùng thực hiện hoàn tất, kiểm tra đúng credential mục tiêu được đổi, grant đã dùng không thể dùng lại, và session được xử lý theo quy tắc đã định.

OWASP khuyến nghị token khôi phục mật khẩu có thời hạn, dùng một lần và được liên kết với người dùng; việc yêu cầu khôi phục không tự tạo thay đổi tài khoản. Các điểm này là cơ sở cho những assertion tương ứng trong [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Riêng reset MFA hoặc đăng ký passkey mới, test cần kiểm tra thêm:

- Grant có scope đủ hẹp cho hành động được duyệt.
- Không thể đổi purpose trong request cuối để thực hiện hành động khác.
- Đăng ký authenticator mới vẫn thực hiện nghi thức xác thực/đăng ký tương ứng.
- Authenticator bị mất hoặc nghi bị chiếm quyền được xử lý theo policy.
- Một session tạo trong giai đoạn khôi phục không được mặc nhiên có toàn bộ quyền của session đăng nhập bình thường.
- Callback đến sau khi credential đã đổi không thể mở lại một cửa sổ thay đổi mới.

Kiểm tra một endpoint trả 200 chưa chứng minh session cũ đã bị thu hồi. Cần dùng session cũ gọi một tài nguyên có bảo vệ sau hành động và kiểm tra kết quả thực thi quyền, hoặc quan sát cơ chế auth version nếu đó là thiết kế đang dùng.

## 12. Thông báo, dữ liệu nhạy cảm và quan sát vận hành

Provider error có thể chứa địa chỉ, số điện thoại, nội dung request hoặc đường dẫn có token. Test nên dùng những chuỗi sentinel tổng hợp để tìm xem chúng có xuất hiện ở log, trace, metric label, dead-letter queue và artifact CI không.

Ví dụ:

```text
syntheticEmail = recovery-sentinel-17@example.test
syntheticToken = TEST_ONLY_NEVER_VALID_TOKEN_17
syntheticOtp   = TEST_ONLY_CODE_17
```

Bộ kiểm tra cần bao phủ cả happy path và exception path. Việc log được che trên response thành công không bảo đảm SDK exception không in nguyên request.

Dữ liệu quan sát hữu ích thường là operation reference không mang bí mật, loại lỗi đã chuẩn hóa, provider account được biểu diễn bằng định danh nội bộ và độ trễ. Không gắn raw token, số điện thoại hay tài liệu định danh vào metric label.

Ở API khởi tạo công khai, kiểm tra phản hồi với tài khoản tồn tại và không tồn tại theo chính sách chống dò tài khoản của sản phẩm. Không trả lỗi provider chi tiết chỉ ở nhánh tài khoản có thật. Với timing, tránh assertion mong hai request có thời gian bằng nhau tuyệt đối; kiểm tra kiến trúc xử lý bất đồng bộ và dùng đánh giá phân bố có thiết kế khi cần xác minh kênh thời gian.

Các nhánh kiểm thử khác:

- Provider phản hồi địa chỉ không hợp lệ nhưng public API vẫn giữ thông điệp phù hợp.
- Người dùng yêu cầu gửi lại nhiều lần không tạo bão email/SMS.
- Template thể hiện đúng mục đích và ngôn ngữ, không chèn dữ liệu chưa escape.
- Link khôi phục sử dụng origin được cấu hình tin cậy, không theo Host header tùy ý.
- Thông báo hoàn tất khôi phục được tạo theo policy và có đường phục hồi khi gửi lỗi.
- Dead-letter không trở thành kho bí mật tồn tại vô thời hạn.

Nếu kiểm thử payload thực sự cần một token có khả năng được xác minh trong hệ thống test, chỉ giữ nó trong phạm vi test cần thiết và hủy dữ liệu sau test theo cơ chế fixture. Không xuất nội dung đó ra artifact chẩn đoán dùng chung.

## 13. Sandbox, contract drift và tổ chức chạy trên CI

Một pipeline thực dụng gồm ba nhóm:

1. **Mỗi thay đổi:** policy test, adapter với HTTP stub, các case callback chữ ký và các integration test quan trọng chạy cục bộ.
2. **Theo lịch hoặc trước thay đổi tích hợp:** contract/sandbox test bằng tài khoản tổng hợp, credential giới hạn và quota được kiểm soát.
3. **Trước phát hành thay đổi lớn:** kịch bản phục hồi crash, race, outage và fallback trên môi trường tích hợp cô lập.

Sandbox test cần có điều kiện tránh gọi nhầm production: kiểm tra endpoint, provider account, môi trường, credential test và danh sách người nhận được phép. Chỉ một biến cấu hình tên “test” không đủ chứng minh lệnh gửi sẽ tới môi trường test.

Không dùng test sandbox làm phụ thuộc bắt buộc của mọi unit test. Một sự cố bên ngoài cần được báo là lỗi khả dụng môi trường khi đúng bản chất, nhưng không được dùng nhãn ấy để che lỗi adapter đã tái hiện được.

Đối với contract drift, quản lý các fixture sau:

- Response thành công thực tế đã được khử dữ liệu nhạy cảm.
- Response lỗi nghiệp vụ và lỗi xác thực.
- Mẫu callback được ký bằng key test và byte body cố định.
- Mẫu enum chưa biết, thiếu field và có field mới.
- Phiên bản schema/API, ngày đối chiếu và các giả định quan trọng.

Fixture callback cần giữ đúng dữ liệu dùng ký; serializer thay đổi khoảng trắng có thể làm chữ ký hỏng dù object JSON có cùng ý nghĩa. Một test riêng nên chứng minh việc kiểm tra chữ ký thật sự thất bại khi payload bị sửa.

Khi đổi SDK hoặc API version, chạy lại adapter test và các kịch bản retry. SDK có thể thay đổi timeout, hành vi retry hoặc cách serialize ngay cả khi interface miền không đổi.

## 14. Kịch bản xuyên suốt: callback cũ sau khi người dùng đổi MFA

Giả sử người dùng mất thiết bị MFA và tạo attempt A:

```text
T0: A dùng generation 4, provider operation P1.
T1: P1 timeout sau khi provider đã tiếp nhận.
T2: Policy cho phép tạo operation thay thế P2, generation tăng lên 5.
T3: P2 trả evidence hợp lệ; các điều kiện policy khác đã được thỏa mãn.
T4: Người dùng hoàn tất thay MFA bằng grant giới hạn.
T5: Callback VERIFIED của P1, generation 4, mới tới.
```

Bộ test phải giữ callback P1 lại bằng một hàng đợi do fixture điều khiển, sau đó thả nó tại T5. Không dùng thời gian chờ ngẫu nhiên để tạo tình huống.

Assertions nên tập trung vào tác động:

- Callback P1 có thể được ghi nhận để audit nhưng không tạo evidence sử dụng được.
- Attempt đã hoàn tất giữ trạng thái terminal.
- Số grant được cấp không tăng.
- MFA vừa đăng ký không bị thay, xóa hoặc gắn thêm authenticator khác.
- Session cũ tiếp tục chịu cơ chế kiểm soát đã áp dụng ở T4.
- Không phát thêm thông báo “khôi phục thành công” cho cùng quyết định.
- Gửi lại callback P1 vẫn không gây tác động mới.

Sau đó chạy biến thể P1 dùng event ID trùng một callback của provider account khác. Nếu dedup chỉ dựa vào event ID mà thiếu namespace cần thiết, bộ test sẽ phát hiện sự kiện hợp lệ bị bỏ qua hoặc được gắn nhầm.

## 15. Hoàn thiện một bộ recovery provider tests có thể đánh giá được

Một danh sách test có giá trị cần thể hiện được liên kết từ rủi ro đến oracle, thay vì chỉ đếm số test hoặc tỷ lệ coverage.

| Rủi ro | Tình huống tái hiện | Oracle chính |
|---|---|---|
| Nhầm chuyển phát với xác minh | Chỉ nhận receipt DELIVERED | Không có recovery grant |
| Khôi phục chéo tenant | Callback hợp lệ của operation tenant khác | Không có thay đổi ở tài khoản đích |
| Retry tạo thao tác mới | Provider thực hiện rồi timeout | Cùng operation/key; tác động theo đúng hợp đồng |
| Replay làm cấp quyền lại | Gửi trùng callback đồng thời | Một quyết định miền và không có tác động kép |
| Evidence cũ hồi sinh attempt | Callback sau hủy/hết hạn/đổi generation | Attempt không được mở lại |
| Mất event sau crash | Dừng tiến trình giữa inbox và xử lý | Xử lý lại an toàn, không mất ý định bền vững |
| Fallback làm giảm mức bảo đảm | Provider mạnh lỗi, tuyến khác sẵn sàng | Policy vẫn yêu cầu bằng chứng đủ mức |
| Lộ bí mật khi gặp lỗi | SDK exception chứa sentinel | Log và artifact không có bí mật |
| Session còn quyền trái policy | Dùng session cũ sau hoàn tất | Quyền bị hạn chế/thu hồi theo thiết kế |

Có thể tự luyện bằng cách bỏ từng điều kiện trong adapter hoặc policy minh họa: biến mọi 2xx thành verified, bỏ tenant binding, cho phép generation cũ, tạo key mới mỗi retry, hoặc đánh dấu inbox đã xử lý trước transaction. Bộ test phù hợp phải thất bại ở oracle liên quan.

Khi một test thất bại, báo cáo cần có scenario, seed/lịch thực thi, trạng thái trước và sau, cùng reference đã được làm sạch. Một assertion chung “expected success but got error” không đủ để phân biệt lỗi provider, lỗi hợp đồng và lỗi cấp quyền.

Recovery provider tests hoàn chỉnh phải chứng minh rằng ứng dụng hiểu đúng bằng chứng từ hệ thống phụ thuộc và giữ được ràng buộc khôi phục khi hệ thống ấy chậm, lỗi, gửi lặp hoặc trả kết quả đến muộn. Đó là phần kết nối trực tiếp độ tin cậy của tích hợp với khả năng ngăn chiếm đoạt tài khoản.
