# API authentication

## 1. Xác thực API cần chứng minh điều gì?

Một yêu cầu gửi đến API có thể mang tên người dùng, mã khách hàng, mã tenant hoặc một chuỗi tự gọi là token. Việc những giá trị này xuất hiện trong request không chứng minh bên gửi thực sự có danh tính tương ứng.

**API authentication**, hay xác thực API, là quá trình kiểm tra bằng chứng để thiết lập danh tính của chủ thể đang gọi API. Chủ thể có thể là người dùng thông qua một ứng dụng, một dịch vụ nội bộ hoặc một đối tác tích hợp.

Kết quả cần đạt không chỉ là “request có token”. Hệ thống phải xác định được:

1. Bằng chứng do nguồn nào phát hành hoặc quản lý?
2. Bằng chứng có hợp lệ tại thời điểm xử lý và dành cho API này không?
3. Danh tính nào được thiết lập sau khi kiểm tra?
4. Danh tính ấy được truyền tới lớp nghiệp vụ bằng cách nào mà bên gọi không thể giả mạo?
5. Khi không xác minh được, request bị xử lý ra sao?

Trong thiết kế yêu cầu bảo mật, câu “API phải có authentication” chưa đủ để triển khai hoặc nghiệm thu. Cần chỉ rõ endpoint nào được bảo vệ, cơ chế được chấp nhận, các điều kiện kiểm tra và hành vi thất bại.

## 2. Phân biệt xác thực với những khái niệm gần nhau

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Identification | Bên gọi tự nhận là ai? | Request gửi `userId=42` |
| Authentication | Có bằng chứng đáng tin cho danh tính đó không? | Access token được kiểm tra và ánh xạ tới người dùng |
| Authorization | Danh tính đã xác thực được làm gì với tài nguyên này? | Người dùng chỉ được xem đơn hàng thuộc phạm vi được cấp |
| Transport protection | Ai có thể đọc hoặc sửa dữ liệu trên đường truyền? | HTTPS bảo vệ kênh giữa hai điểm kết thúc TLS |
| Request integrity hoặc proof of possession | Request có gắn với một khóa hoặc bằng chứng sở hữu theo giao thức không? | Request có bằng chứng mật mã được kiểm tra theo cơ chế đã chọn |

Xác thực thành công không đồng nghĩa được phép truy cập mọi endpoint. Ngược lại, một luật phân quyền kiểm tra `userId` trong body sẽ không có cơ sở đáng tin nếu danh tính gọi API chưa được xác thực.

HTTPS cũng không tự xác thực người dùng cuối. Trong TLS thông thường, client chủ yếu xác minh máy chủ; việc xác thực client cần một cơ chế bổ sung như access token hoặc mTLS được cấu hình phù hợp.

Một API key có thể xác thực một ứng dụng tích hợp theo hợp đồng đã định. Không được tự suy ra nó chứng minh danh tính của từng người dùng đang sử dụng ứng dụng đó.

## 3. Mô hình đe dọa tối thiểu

Giả sử API quản lý đơn hàng có ba loại bên gọi:

- Người dùng sử dụng ứng dụng web hoặc ứng dụng di động.
- Dịch vụ nền thực hiện công việc tự động.
- Đối tác gọi một tập chức năng tích hợp đã được cấp.

Những rủi ro cần xét không giống nhau hoàn toàn, nhưng đều có các câu hỏi chung về bằng chứng xác thực.

| Đe dọa | Điều có thể xảy ra | Yêu cầu cần hình thành |
| --- | --- | --- |
| Bỏ qua xác thực | Một route mới hoặc một HTTP method không có kiểm tra | Bảo vệ mặc định, chỉ công khai các route được phê duyệt rõ ràng |
| Giả mạo thông tin danh tính | Client tự gửi `X-User-Id`, `tenantId` hoặc claim chưa được xác minh | Chỉ tạo danh tính từ bằng chứng đã kiểm tra |
| Dùng token sai nơi | Token dành cho một API khác được chấp nhận | Kiểm tra audience theo hợp đồng của API |
| Dùng token sai nguồn | Token do một issuer không tin cậy phát hành được chấp nhận | Ràng buộc issuer và cấu hình khóa tin cậy |
| Dùng bằng chứng quá hạn | Token hết hạn hoặc credential đã vô hiệu hóa vẫn hoạt động | Kiểm tra thời gian và chính sách thu hồi phù hợp |
| Đánh cắp bearer token | Người có token sử dụng lại để mạo danh | Bảo vệ token, giới hạn thời gian và phạm vi; cân nhắc ràng buộc sở hữu khi cần |
| Tấn công dependency | Dịch vụ danh tính lỗi làm API bỏ qua xác thực | Chính sách đóng khi không xác minh được, cùng hành vi lỗi xác định |
| Nhầm danh tính qua gateway | Backend tin header client có thể tự đặt | Ranh giới tin cậy và cơ chế truyền danh tính được bảo vệ |

Mô hình này giúp tránh một đặc tả chỉ nói tên công nghệ mà không nêu thuộc tính an toàn cần có. “Dùng JWT” không tự trả lời các câu hỏi trong bảng.

## 4. Chọn cơ chế theo chủ thể và luồng gọi

Không có một loại credential phù hợp cho mọi API. Lựa chọn phải phản ánh ai đang gọi, credential được cấp ở đâu, bên gọi có giữ bí mật được hay không và yêu cầu thu hồi nghiêm ngặt đến mức nào.

| Cơ chế | Danh tính thường được thiết lập | Điểm cần đặc tả |
| --- | --- | --- |
| Access token dạng bearer | Người dùng, ứng dụng hoặc dịch vụ tùy luồng cấp token | Issuer, audience, thời hạn, loại token, cách kiểm tra và giới hạn sử dụng |
| API key | Ứng dụng hoặc đối tác được cấp key | Chủ sở hữu, entropy, lưu trữ, luân chuyển, vô hiệu hóa, giới hạn phạm vi |
| mTLS | Chủ thể gắn với chứng thư và khóa riêng | Chuỗi tin cậy, hạn chứng thư, ánh xạ danh tính, chính sách thu hồi và kết thúc TLS |
| Session cookie | Phiên người dùng đã được tạo qua quy trình đăng nhập | Thuộc tính cookie, vòng đời phiên, CSRF và phạm vi cookie |
| Cơ chế ký request hoặc token có ràng buộc sở hữu | Chủ thể có thể chứng minh quyền sở hữu khóa theo giao thức | Cách tạo và kiểm tra bằng chứng, ràng buộc request và chống phát lại |

OAuth 2.0 cung cấp khuôn khổ cấp quyền và access token; không nên coi chỉ riêng tên OAuth là một quy trình đăng nhập người dùng hoàn chỉnh. Khi ứng dụng cần đăng nhập theo OpenID Connect, ID token và access token có vai trò khác nhau.

API tài nguyên không nên chấp nhận ID token như access token chỉ vì cả hai đều có thể dùng định dạng JWT. ID token phục vụ client trong quy trình xác thực OpenID Connect; API cần bằng chứng có loại, mục đích và audience phù hợp với hợp đồng truy cập tài nguyên của chính nó.

### Ứng dụng công khai không giữ được một bí mật dùng chung theo cách của server

Một khóa được nhúng trong mã JavaScript gửi cho trình duyệt hoặc trong gói ứng dụng có thể bị trích xuất. Không được đặc tả nó như bằng chứng đủ mạnh rằng request chỉ có thể đến từ một ứng dụng tin cậy.

Điều này không có nghĩa mọi API key ở client đều vô dụng. Một key có thể phục vụ định tuyến, đo mức sử dụng hoặc nhận diện dự án với quyền hạn hạn chế. Nhưng những chức năng đó không được âm thầm biến thành quyền truy cập dữ liệu nhạy cảm hoặc bằng chứng danh tính người dùng.

### Dịch vụ nền cần danh tính dịch vụ riêng

Một job tự động không nên dùng token của một nhân viên cố định chỉ để gọi API được. Danh tính dịch vụ giúp xác định chủ sở hữu, phạm vi quyền, trách nhiệm luân chuyển credential và hành vi khi dịch vụ ngừng hoạt động.

Nếu dịch vụ thực sự gọi thay người dùng, phải có hợp đồng ủy quyền rõ ràng. Không thay luồng này bằng việc gắn `userId` tùy ý bên cạnh một credential của dịch vụ rồi coi đó là xác thực người dùng.

## 5. Bearer token: ai giữ token có thể dùng token

Với bearer token, việc sở hữu token là cơ sở để trình bằng chứng truy cập. Kẻ lấy được token có thể sử dụng nó trong phạm vi và thời hạn mà hệ thống chấp nhận, trừ khi có cơ chế ràng buộc bổ sung.

Ví dụ request:

```http
GET /api/orders/ord-1042 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

`<access-token>` là chỗ giữ chỗ trong tài liệu, không phải token thực. Request này chỉ có ý nghĩa an toàn khi đi qua kênh truyền được bảo vệ và token được API kiểm tra đúng.

Đối với API dùng header Authorization, yêu cầu nên xác định duy nhất vị trí nhận token. Không tự mở thêm cách nhận token từ query string, body hoặc một header riêng nếu chưa có hợp đồng và đánh giá tương ứng.

Token trong URL dễ đi vào lịch sử, access log, công cụ quan sát, báo cáo lỗi hoặc các đường truyền tiếp URL. Đổi tên tham số thành một tên ít ai biết không giải quyết được vấn đề.

Khi request có nhiều header Authorization, token sai định dạng hoặc các nguồn credential mâu thuẫn, hệ thống cần từ chối theo quy tắc đã công bố. Không nối các giá trị lại rồi chọn một phần tùy ý; gateway và backend diễn giải khác nhau có thể tạo đường bỏ qua kiểm tra.

### Bảo vệ token trong toàn bộ vòng đời

Yêu cầu không chỉ nằm ở API nhận token. Cần xét nơi token được cấp, truyền, lưu, làm mới và hủy:

- Không ghi nguyên token vào log, thông báo lỗi hoặc telemetry thông thường.
- Không đưa token vào ví dụ thật, mã nguồn, ảnh chụp hoặc dữ liệu kiểm thử được chia sẻ.
- Không trả token lại trong response chỉ để client biết server đã nhận được nó.
- Xác định nơi lưu token phù hợp với môi trường client và mô hình đe dọa.
- Giới hạn thời gian sử dụng cùng phạm vi được cấp theo rủi ro.
- Có quy trình xử lý khi token hoặc credential gốc bị lộ.

Mã hóa token khi lưu giúp giảm một số rủi ro tại nơi lưu, nhưng không tự ngăn token bị đánh cắp sau khi ứng dụng giải mã hoặc bị sử dụng sai ở phía client.

## 6. JWT: kiểm tra bằng chứng, không chỉ giải mã nội dung

JWT là một định dạng có thể mang claim. Nhìn thấy ba phần phân cách bằng dấu chấm hoặc đọc được JSON bên trong không chứng minh token hợp lệ.

Các hàm decode thường chỉ chuyển biểu diễn thành dữ liệu có thể đọc. Chúng không nhất thiết xác minh chữ ký, issuer, audience hoặc thời gian. Yêu cầu phải gọi đúng hành vi **verify/validate**, theo một profile token xác định.

### Các điều kiện kiểm tra cho một profile access token

| Thành phần | Điều cần xác định | Lỗi thiết kế cần tránh |
| --- | --- | --- |
| Nguồn phát hành | Issuer tin cậy lấy từ cấu hình đã phê duyệt | Tin bất kỳ `iss` nào token tự khai báo |
| Khóa xác minh | Khóa gắn với issuer và cơ chế quản lý khóa tin cậy | Dùng khóa hoặc URL do token tự chọn mà không kiểm soát |
| Thuật toán | Tập thuật toán cho phép, tương thích loại khóa và profile | Chấp nhận thuật toán chỉ vì header token yêu cầu |
| Chữ ký hoặc bảo vệ tương ứng | Bằng chứng mật mã phải được kiểm tra bằng thư viện phù hợp | Chỉ decode rồi dùng claim |
| Audience | Token được phát hành cho API hoặc tập tài nguyên bao gồm API này | Chấp nhận token dành cho dịch vụ khác |
| Thời gian | `exp`, `nbf` nếu có, cùng các ràng buộc thời gian của profile | Bỏ qua hết hạn hoặc nới clock skew không có giới hạn |
| Loại và mục đích token | Bằng chứng phải là loại access token được API hỗ trợ | Dùng ID token hoặc token cho luồng khác |
| Claim danh tính | Các claim bắt buộc có kiểu và ý nghĩa đúng hợp đồng | Tự lấy email hoặc trường tùy ý làm danh tính ổn định |

Đối với profile yêu cầu token hết hạn, phải kiểm tra sự hiện diện và hiệu lực của `exp`; không coi thiếu claim là token có thể sống vô hạn. `iat` hoặc các claim khác có bắt buộc hay không phụ thuộc profile, không nên giả định mọi JWT đều có cùng tập claim.

Clock skew là một khoảng dung sai có giới hạn cho sai lệch đồng hồ, không phải lý do chấp nhận token quá hạn tùy ý. Cần đồng bộ đồng hồ của hệ thống và đưa giá trị dung sai vào cấu hình được kiểm soát.

Không tự viết thuật toán xác minh chữ ký. Thư viện được chọn phải được cấu hình để thực hiện đúng profile và các điều kiện ứng dụng cần, thay vì dựa vào giả định rằng mọi kiểm tra đều tự bật.

### Không dùng claim trước khi xác minh

Một số thông tin chưa xác minh có thể được đọc để phục vụ chọn một cấu hình trong tập tin cậy, nhưng chúng vẫn là đầu vào không đáng tin. Không được dựa vào chúng để cấp quyền, tạo danh tính có thẩm quyền hoặc tải một nguồn khóa tùy ý.

Ví dụ, `kid` chỉ nên giúp tìm khóa trong bộ khóa đã gắn với issuer được chấp nhận. Nó không phải đường dẫn file, câu truy vấn hoặc địa chỉ mạng mà ứng dụng được phép sử dụng trực tiếp.

Tương tự, `iss`, `jku` hoặc thông tin khóa trong token không được biến thành quyền gọi một URL bất kỳ. Hệ thống đa issuer cần danh mục issuer và nguồn khóa được cho phép rõ ràng.

### Danh tính nên có namespace theo issuer

Hai issuer khác nhau có thể sử dụng cùng một giá trị `sub` cho hai người khác nhau. Nếu hệ thống hỗ trợ nhiều issuer, danh tính thường cần được ràng buộc với cả issuer và subject theo mô hình đã chọn.

Email, tên hiển thị hoặc mã tenant do request tự cung cấp không nên thay thế mối ràng buộc đó. Việc ánh xạ sang tài khoản nội bộ phải có quy tắc rõ ràng, đặc biệt khi email có thể thay đổi hoặc một người thuộc nhiều tenant.

## 7. Opaque token và introspection

Không phải access token nào cũng là JWT. Opaque token có thể là một giá trị mà API không tự đọc được ý nghĩa. API kiểm tra nó bằng dịch vụ có thẩm quyền hoặc bằng cơ chế tra cứu phiên/token đã thiết kế.

Những yêu cầu chính gồm:

1. Chỉ gọi endpoint xác minh được cấu hình tin cậy qua kênh bảo vệ phù hợp.
2. API xác thực chính nó với dịch vụ kiểm tra bằng cơ chế đã cấp cho API đó.
3. Kiểm tra trạng thái hợp lệ, thời gian, audience hoặc ràng buộc tài nguyên và thông tin danh tính theo hợp đồng.
4. Không dùng một response chỉ parse thành công làm bằng chứng token đang hoạt động.
5. Quy định timeout, cache, hành vi khi lỗi và mức chậm thu hồi chấp nhận được.

Nếu kết quả introspection được cache, một token đã bị thu hồi có thể vẫn được chấp nhận trong khoảng cache cho phép. Đây là thuộc tính cần mô tả và nghiệm thu, không phải chi tiết vận hành có thể bỏ qua.

### Phân biệt token không hợp lệ với không thể xác minh

Hai tình huống sau khác nhau:

- Dịch vụ có thẩm quyền xác nhận token không hoạt động.
- API không nhận được câu trả lời vì timeout hoặc dependency không khả dụng.

Cả hai đều không được đi tiếp vào nghiệp vụ được bảo vệ nếu chưa có bằng chứng hợp lệ theo chính sách. Tuy nhiên, mã phản hồi, metric và xử lý vận hành có thể khác nhau. Tình huống dependency lỗi có thể sử dụng lỗi tạm thời, chẳng hạn 503 theo hợp đồng, thay vì kết luận sai rằng credential của người dùng không hợp lệ.

Một thiết kế xác minh JWT offline có thể tiếp tục xử lý bằng khóa tin cậy còn hợp lệ trong cache khi issuer tạm thời không truy cập được. Điều đó không phải bỏ qua xác thực nếu toàn bộ điều kiện của chính sách vẫn được đáp ứng. Phải xác định rõ giới hạn độ mới của khóa và dữ liệu cần thiết; không cho phép cache hết hạn vô thời hạn chỉ để giữ hệ thống hoạt động.

## 8. Ranh giới gateway và backend

Một hệ thống thường đặt API gateway hoặc reverse proxy trước dịch vụ. Gateway có thể kiểm tra token rồi chuyển thông tin danh tính xuống backend.

Ví dụ một header nội bộ:

```http
X-Authenticated-Subject: user-42
```

Header này chỉ đáng tin khi có toàn bộ các điều kiện thiết kế cần thiết. Tên có chữ `Authenticated` không tạo ra sự tin cậy.

Cần đặc tả:

- Backend có thể bị gọi trực tiếp từ đâu và bằng cách nào.
- Gateway xử lý các header danh tính do client gửi lên ra sao.
- Kênh gateway–backend xác thực bên gửi và bảo vệ tính toàn vẹn thế nào.
- Danh tính được ràng buộc với request, dịch vụ đích và thời gian bằng cơ chế nào nếu dùng assertion nội bộ.
- Thành phần nào kiểm tra bằng chứng ban đầu, thành phần nào kiểm tra thông tin được chuyển tiếp.
- Có thể giả mạo danh tính qua một route hoặc một đường mạng thay thế hay không.

Một phương án là backend tự xác minh access token phù hợp. Một phương án khác là backend chỉ tin assertion nội bộ được bảo vệ theo một hợp đồng rõ ràng. Lựa chọn phụ thuộc kiến trúc; yêu cầu bảo mật phải nói đủ điều kiện của phương án được chọn.

Không nên chuyển tiếp một token tới mọi dịch vụ mà không xem audience và phạm vi. Nếu token dành cho API A, việc A gửi nó sang B không tự làm nó thành bằng chứng phù hợp cho B.

### Danh tính người dùng và danh tính dịch vụ gọi không phải luôn là một

Khi dịch vụ A gọi B thay người dùng, có thể cần phân biệt người dùng được đại diện và ứng dụng đang thực hiện lời gọi. Chỉ giữ một trường `userId` rồi làm mất thông tin bên gọi có thể khiến việc truy vết và áp dụng chính sách sai lệch.

Quy tắc ủy quyền hoặc token exchange, nếu dùng, phải xác định được các chủ thể này theo giao thức đã chọn. Không tự sáng tác một header để thay thế mọi quan hệ ủy quyền.

## 9. Pipeline xử lý cho một endpoint được bảo vệ

Một luồng xử lý có thể được mô tả như sau:

```text
Request đến route được bảo vệ
    → đọc credential theo hợp đồng và giới hạn đầu vào
    → chọn verifier từ cấu hình tin cậy
    → xác minh bằng chứng, thời gian, nguồn và đích sử dụng
    → tạo danh tính nội bộ đã xác thực
    → kiểm tra quyền với hành động và tài nguyên
    → xử lý nghiệp vụ
```

Bước xác thực phải hoàn thành trước các tác dụng nghiệp vụ của endpoint. Một request không được tạo đơn hàng rồi mới phát hiện token hết hạn.

Mã giả dưới đây thể hiện trách nhiệm, không phải một bộ triển khai xác thực có thể sao chép thay cho thư viện hoặc framework:

```text
handleProtectedRequest(request):
    credential = readCredentialStrictly(request)

    if credential is absent:
        return authenticationRequired()

    verification = configuredVerifier.verify(credential)

    if verification is INVALID:
        recordBoundedAuthenticationFailure()
        return invalidCredential()

    if verification is UNAVAILABLE:
        recordVerificationDependencyFailure()
        return verificationUnavailable()

    identity = mapVerifiedEvidenceToIdentity(verification)

    if identity cannot be established under the accepted profile:
        return invalidCredential()

    if not authorizationPolicy.allows(identity, request.action, request.resource):
        return forbidden()

    return executeBusinessOperation(identity, request)
```

`configuredVerifier` ở đây phải bao gồm các kiểm tra của cơ chế đã chọn. Không được hiện thực nó bằng hàm chỉ decode JWT rồi trả `VALID`.

Danh tính nội bộ nên được truyền qua security context hoặc kiểu dữ liệu có nguồn gốc rõ ràng. Lớp nghiệp vụ không nên tự đọc lại `userId` từ một header không tin cậy rồi bỏ qua danh tính đã thiết lập.

Trong hệ thống dùng thread pool hoặc xử lý bất đồng bộ, security context phải được gắn và dọn đúng vòng đời. Không để request sau vô tình nhận danh tính còn sót của request trước. Nếu một job chạy muộn thay mặt người dùng, cần xác định cả thời điểm kiểm tra quyền và giới hạn ủy quyền của job.

## 10. Phản hồi khi xác thực thất bại

Một API dùng bearer token thường cần phân biệt các trường hợp sau:

| Tình huống | Ý nghĩa | Hành vi điển hình |
| --- | --- | --- |
| Thiếu bằng chứng ở endpoint được bảo vệ | Chưa có cơ sở xác thực | 401 cùng challenge phù hợp |
| Token không hợp lệ hoặc hết hạn | Bằng chứng không được chấp nhận | 401 theo hợp đồng bearer của API |
| Đã xác thực nhưng không đủ quyền | Danh tính hợp lệ, quyền không đáp ứng | 403 theo chính sách phân quyền |
| Credential sai cú pháp hoặc nhiều nguồn mâu thuẫn | Request không theo hợp đồng | Từ chối theo quy tắc đã công bố; có thể là 400 tùy dạng lỗi |
| Không thể hoàn tất xác minh do dependency lỗi | Chưa có bằng chứng hợp lệ để đi tiếp | Không xử lý nghiệp vụ; trả lỗi khả dụng theo hợp đồng |

Ví dụ thiếu bearer token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/json

{"code":"AUTHENTICATION_REQUIRED","message":"Cần xác thực để truy cập."}
```

Với token không được chấp nhận, API có thể cung cấp thông tin lỗi bearer phù hợp với hợp đồng, nhưng không nên đưa nguyên token, chi tiết khóa, stack trace hoặc cấu hình nội bộ vào response.

API dành cho máy gọi thường nên trả phản hồi lỗi API thay vì chuyển hướng 302 sang trang đăng nhập HTML. Client cần phân biệt lỗi credential với lỗi dữ liệu nghiệp vụ và lỗi hạ tầng bằng giao diện đã công bố.

Không dùng một response 200 chứa thông báo “token invalid” như thể request thành công. Các lớp client, retry và quan sát thường dựa vào mã HTTP để xử lý.

Mức chi tiết công khai của lỗi cũng phải được cân nhắc. Một endpoint nhận mật khẩu có thể cần thông báo chung để hạn chế dò tài khoản; chi tiết vận hành nên được ghi bằng reason code có kiểm soát ở kênh phù hợp.

## 11. Vòng đời credential, thu hồi và luân chuyển khóa

### Không hứa thu hồi tức thì nếu cơ chế không có thuộc tính đó

Một JWT được API xác minh offline bằng khóa tin cậy có thể tiếp tục được chấp nhận đến khi hết hạn, trừ khi API có thêm thông tin thu hồi hoặc cơ chế thay đổi trạng thái liên quan.

Đăng xuất khỏi một giao diện không tự xóa token đã bị sao chép. Thu hồi refresh token có thể chặn việc cấp access token mới nhưng không nhất thiết vô hiệu hóa ngay mọi access token đã cấp.

Yêu cầu cần mô tả rõ:

- Sự kiện nào bắt buộc làm credential mất hiệu lực.
- Mức trễ tối đa chấp nhận được giữa sự kiện và việc API từ chối.
- Cơ chế nào đáp ứng mức trễ đó.
- Khi cơ chế thu hồi không truy cập được, API ứng xử thế nào.

Các giải pháp có thể gồm token ngắn hạn, introspection, kiểm tra trạng thái phiên hoặc danh sách thu hồi theo thiết kế. Không dùng tên giải pháp để thay cho chỉ tiêu có thể đo được.

### Luân chuyển khóa phải giữ đúng ranh giới tin cậy

Đổi khóa ký cần tính đến token đã cấp, thời hạn token, cache khóa và khả năng sự cố. Trong luân chuyển thông thường có thể cần thời gian chồng lấn giữa khóa mới và khóa cũ; khi nghi lộ khóa, chính sách khẩn cấp có thể cần hành vi khác.

API nên nhận khóa từ nguồn tin cậy được cấu hình, giới hạn thời gian sử dụng cache và có cơ chế cập nhật phù hợp. Không thực hiện một lần tải mạng không giới hạn cho mọi `kid` lạ do client gửi; điều đó có thể biến xác thực thành nguồn tiêu thụ tài nguyên hoặc gây lỗi dây chuyền.

Các tiêu chí kiểm chứng cần có cả trường hợp token hợp lệ khi đổi khóa, token dùng khóa không được phép và dependency khóa tạm thời không hoạt động.

### API key cũng có vòng đời

API key phải có chủ sở hữu, mục đích, trạng thái và cơ chế thu hồi. Cần tránh một key dùng chung cho nhiều đối tác vì khi bị lộ sẽ khó xác định nguồn và luân chuyển riêng.

Key đủ khó đoán vẫn có thể bị lộ qua log hoặc mã nguồn. Khả năng thay key mà không cần sửa mã ứng dụng và thời gian vô hiệu hóa key cũ là các yêu cầu vận hành cần được đưa vào thiết kế.

## 12. Trình duyệt, cookie và CSRF

Khi API được gọi từ trình duyệt, cách credential được đính kèm ảnh hưởng đến mô hình đe dọa.

Với session cookie, trình duyệt có thể tự gửi cookie theo quy tắc cookie và chính sách request. Vì vậy, cần xét CSRF cho các thao tác thay đổi trạng thái, bên cạnh xác thực phiên.

Các thuộc tính như `Secure`, `HttpOnly`, `SameSite`, phạm vi domain/path và thời hạn cookie phải phù hợp với kiến trúc. Chúng có tác dụng khác nhau: `HttpOnly` hạn chế JavaScript đọc cookie, nhưng không ngăn mọi request do một trang có mã độc thực hiện trong cùng ngữ cảnh.

Với bearer token mà JavaScript có thể đọc, rủi ro token bị lấy qua XSS cần được đánh giá. Không chọn nơi lưu token chỉ vì thao tác lập trình thuận tiện hoặc vì một danh sách kiểm tra nói chung chung rằng nơi đó “an toàn”.

Một số kiến trúc sử dụng backend phục vụ frontend để quản lý credential ở phía server và phiên trình duyệt riêng. Nếu dùng, phải đặc tả cả phiên, CSRF, ranh giới cookie và các lời gọi từ backend tới API; không coi việc thêm một lớp server là tự giải quyết mọi rủi ro.

CORS quyết định một số khả năng truy cập response từ mã chạy trong trình duyệt. Nó không phải cơ chế xác thực người gọi API và không ngăn một client ngoài trình duyệt gửi request trực tiếp.

## 13. Quan sát và kiểm soát lạm dụng

Hệ thống cần thấy được hoạt động xác thực nhưng không làm lộ credential qua chính cơ chế quan sát.

Những dữ liệu có thể hữu ích, tùy chính sách riêng tư và vận hành, gồm:

- Request ID và thời điểm.
- Endpoint hoặc nhóm endpoint.
- Loại cơ chế xác thực.
- Kết quả cùng reason code thuộc tập giá trị hữu hạn.
- Danh tính đã được xác minh nếu có và được phép ghi.
- Thông tin bên gọi đủ để phân tích lạm dụng theo chính sách.

Không lấy `sub` từ token chưa xác minh rồi ghi như một tài khoản đã được xác thực. Có thể ghi sự kiện credential không hợp lệ mà chưa gán nó cho một danh tính có thẩm quyền.

Giá trị đưa vào log cần được giới hạn độ dài và xử lý theo định dạng log. Không ghi nguyên Authorization header, refresh token, API key, private key hoặc toàn bộ response introspection chứa dữ liệu nhạy cảm.

Các kiểm soát lạm dụng có thể đặt ở nhiều nơi:

| Điểm kiểm soát | Mục đích |
| --- | --- |
| Endpoint cấp token hoặc đăng nhập | Hạn chế thử credential, credential stuffing và tiêu thụ tài nguyên |
| Endpoint xác minh token hoặc introspection | Tránh kiểm tra không giới hạn làm quá tải dependency |
| Cơ chế cập nhật khóa | Hạn chế refresh theo `kid` lạ và lỗi nguồn khóa |
| API tài nguyên | Hạn chế lưu lượng theo chủ thể và theo nguồn theo thiết kế |

Rate limiting không thay thế xác thực. Một request được phép đi qua bộ giới hạn tốc độ vẫn phải cung cấp bằng chứng hợp lệ. Tương tự, khóa tài khoản cứng theo các lần thử có thể bị lạm dụng để gây từ chối dịch vụ; chính sách cần cân bằng rủi ro và có hành vi được xác định.

## 14. Mẫu yêu cầu bảo mật có thể nghiệm thu

Bảng dưới đây minh họa cho một API đơn hàng sử dụng access token từ issuer đã cấu hình. Các con số về thời hạn, cache và timeout phải được dự án xác định theo rủi ro; không để những mục đó thành giá trị ngầm không ai chịu trách nhiệm.

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| API-AUTHN-01 | Mọi route và HTTP method truy cập dữ liệu được bảo vệ phải xác thực trước khi xử lý nghiệp vụ; route công khai phải nằm trong danh mục rõ ràng | Kiểm kê route và gửi request thiếu credential tới từng nhóm route, gồm route mới và method khác |
| API-AUTHN-02 | API chỉ nhận credential tại vị trí và theo cú pháp đã công bố | Kiểm tra token ở query, nguồn credential mâu thuẫn và header lặp không tạo đường bỏ qua |
| API-AUTHN-03 | Access token chỉ được chấp nhận khi nguồn, đích, loại token, bằng chứng mật mã và thời gian đáp ứng profile được phê duyệt | Các token thử sai issuer, audience, chữ ký, thời hạn hoặc mục đích đều bị từ chối |
| API-AUTHN-04 | Danh tính nội bộ chỉ được tạo từ kết quả xác minh thành công và ánh xạ theo namespace đã chọn | Sửa `userId` trong body hoặc header không thay đổi danh tính đã xác thực |
| API-AUTHN-05 | Không thể đi vào nghiệp vụ được bảo vệ khi thiếu hoặc không xác minh được bằng chứng theo chính sách | Gây lỗi verifier/dependency và kiểm tra không có tác dụng nghiệp vụ |
| API-AUTHN-06 | Ranh giới gateway–backend chống giả mạo danh tính và không có đường gọi trực tiếp bỏ qua hợp đồng | Kiểm tra header giả, kênh thay thế và request tới backend theo mô hình triển khai |
| API-AUTHN-07 | Thu hồi credential đáp ứng mức trễ tối đa đã công bố cho từng loại | Đo từ lúc thu hồi đến lúc API từ chối, gồm hành vi cache |
| API-AUTHN-08 | Luân chuyển khóa có kiểm soát và không tin nguồn khóa do request tùy ý chỉ định | Kiểm tra khóa mới/cũ theo chính sách, `kid` lạ và nguồn khóa lỗi |
| API-AUTHN-09 | Credential không xuất hiện trong log, response lỗi hoặc telemetry thông thường | Gửi credential kiểm thử có thể nhận diện và kiểm tra các kênh quan sát thuộc phạm vi |
| API-AUTHN-10 | Phản hồi phân biệt lỗi xác thực, thiếu quyền và lỗi khả dụng theo hợp đồng | Đối chiếu status code, challenge, schema lỗi và hành vi client |
| API-AUTHN-11 | Security context không bị lẫn giữa các request hoặc tác vụ bất đồng bộ | Gửi request đồng thời với các danh tính khác nhau và kiểm tra ngữ cảnh nghiệp vụ |
| API-AUTHN-12 | Cơ chế cấp và kiểm tra credential có giới hạn tài nguyên cùng tín hiệu lạm dụng phù hợp | Kiểm tra giới hạn đầu vào, timeout, rate limit và reason code mà không lộ secret |

Một yêu cầu hoàn chỉnh cần có chủ sở hữu triển khai và môi trường kiểm chứng. Ví dụ, API-AUTHN-06 không thể nghiệm thu chỉ bằng unit test của một hàm đọc header nếu rủi ro phụ thuộc cấu hình mạng hoặc TLS termination.

## 15. Kịch bản chấp nhận cho API đơn hàng

### 15.1. Token hợp lệ cho đúng API

```text
Given:
  Endpoint GET /api/orders/{id} được bảo vệ.
  Token do issuer được cho phép phát hành.
  Token còn hiệu lực và audience phù hợp với API đơn hàng.
  Claim danh tính đáp ứng profile của API.

When:
  Request gửi token tại Authorization header theo hợp đồng.

Then:
  API tạo danh tính nội bộ từ bằng chứng đã xác minh.
  API tiếp tục sang bước phân quyền với đơn hàng được yêu cầu.
  Xác thực thành công chưa tự quyết định rằng đơn hàng được phép trả về.
```

### 15.2. Token đúng chữ ký nhưng sai audience

```text
Given:
  Token có chữ ký hợp lệ từ issuer tin cậy.
  Token được cấp cho một API khác.

When:
  Token được dùng tại API đơn hàng.

Then:
  Xác thực truy cập tài nguyên không được chấp nhận.
  Không thực hiện thao tác nghiệp vụ.
  Response tuân theo hợp đồng lỗi xác thực.
```

Trường hợp này cho thấy kiểm tra chữ ký là cần nhưng chưa đủ. Việc nhiều API cùng tin một issuer không làm mọi token của issuer trở thành token dùng được ở mọi nơi.

### 15.3. Header tự khai không thay đổi chủ thể

```text
Given:
  Request mang token hợp lệ của người dùng A.
  Client thêm X-User-Id của người dùng B.

When:
  Request đi qua đường truy cập API được hỗ trợ.

Then:
  Danh tính có thẩm quyền không trở thành người dùng B.
  Header không tin cậy được xử lý đúng chính sách biên.
  Phân quyền sử dụng danh tính đã xác minh.
```

### 15.4. Dịch vụ xác minh không khả dụng

```text
Given:
  Loại token yêu cầu kết quả từ dependency xác minh.
  Không có kết quả cache còn hợp lệ theo chính sách.
  Dependency bị timeout.

When:
  Request tới endpoint được bảo vệ.

Then:
  Không thực hiện nghiệp vụ dựa trên danh tính chưa xác minh.
  API trả lỗi khả dụng theo hợp đồng.
  Có metric hoặc sự kiện lỗi dependency phù hợp.
  Không ghi nguyên credential để phục vụ chẩn đoán.
```

## 16. Ma trận trường hợp kiểm chứng

| Trường hợp | Kết quả cần bảo vệ |
| --- | --- |
| Thiếu token | Không vào nghiệp vụ được bảo vệ |
| Token rỗng, quá dài hoặc sai cấu trúc | Từ chối có kiểm soát, không gây xử lý tốn tài nguyên không giới hạn |
| Token bị sửa nội dung hoặc chữ ký | Không tạo danh tính tin cậy |
| Token từ issuer ngoài danh mục | Không được chấp nhận dù cấu trúc hợp lệ |
| Token sai audience | Không dùng bằng chứng của tài nguyên khác |
| Token hết hạn hoặc chưa đến thời điểm được phép dùng | Từ chối theo thời gian và clock skew đã công bố |
| ID token dùng thay access token | Từ chối nếu không đáp ứng đúng loại token được API hỗ trợ |
| Thuật toán không được cho phép | Không được token tự chọn phương án kiểm tra yếu hơn |
| `kid` lạ hoặc thông tin URL khóa tùy ý | Không đọc file hoặc gọi mạng ngoài nguồn tin cậy; có giới hạn refresh |
| Nhiều credential mâu thuẫn | Gateway và backend không chọn danh tính khác nhau |
| Claim danh tính thiếu hoặc sai kiểu | Không suy đoán danh tính từ một trường thay thế tùy ý |
| Header danh tính do client tự gửi | Không thay thế danh tính đã xác minh |
| Credential bị thu hồi | Bị từ chối trong mức trễ đã cam kết |
| Đổi khóa bình thường hoặc khẩn cấp | Hành vi đúng chính sách tương ứng, không mở rộng tin cậy ngoài ý muốn |
| Token hợp lệ nhưng không đủ quyền | Đi qua xác thực, bị chặn ở phân quyền |
| Request đồng thời của nhiều người dùng | Không lẫn security context |
| Verifier hoặc nguồn khóa lỗi | Hành vi đúng chính sách, không bỏ qua kiểm tra |
| Request thất bại được ghi log | Có thông tin chẩn đoán hữu ích mà không lộ secret |

Các credential dùng để kiểm chứng nên được tạo cho môi trường thử nghiệm và quản lý theo quy tắc của môi trường đó. Không sao chép token sản xuất vào tài liệu, báo cáo hoặc repository để làm minh chứng.

Khi xác nhận “không có tác dụng nghiệp vụ”, cần kiểm tra đúng tác dụng mà endpoint có thể gây ra: ghi dữ liệu, phát sự kiện, gửi thông báo hoặc tạo job. Chỉ quan sát mã HTTP có thể không đủ nếu việc xử lý đã diễn ra trước khi kiểm tra xác thực.

## 17. Những lỗi đặc tả thường gặp

### “Có HTTPS nên request đã đáng tin”

HTTPS bảo vệ kênh theo các điểm kết thúc TLS. Nó không thay việc xác minh access token hoặc danh tính client theo cơ chế đã chọn. Khi TLS kết thúc ở proxy, cần xét tiếp ranh giới proxy–backend.

### “JWT đọc được claim là đã xác thực”

Decode không đồng nghĩa verify. Các claim chỉ trở thành cơ sở cho danh tính khi token vượt qua đầy đủ kiểm tra của profile, gồm nguồn, đích, thời gian và mục đích.

### “API nằm trong mạng nội bộ nên bỏ authentication”

Vị trí mạng có thể là một lớp kiểm soát, nhưng không tự chứng minh danh tính dịch vụ. Cần xác định rõ mô hình tin cậy, các đường truy cập và yêu cầu khi có máy hoặc dịch vụ nội bộ bị chiếm quyền.

### “Gateway xác thực rồi thì backend tin mọi header”

Chỉ đúng khi thiết kế đã bảo vệ nguồn header và kênh truyền, đồng thời chặn đường bỏ qua. Một client tự đặt được header danh tính không phải bằng chứng xác thực.

### “Khi identity provider lỗi thì tạm cho qua để giữ uptime”

Điều này làm mất thuộc tính bảo mật của endpoint đúng lúc hệ thống khó quan sát nhất. Cần thiết kế cache hợp lệ, dự phòng và lỗi khả dụng trước; không thay chúng bằng bỏ kiểm tra bằng chứng.

### “Đăng xuất đồng nghĩa mọi access token mất hiệu lực ngay”

Khả năng này phụ thuộc loại token và cơ chế thu hồi. Yêu cầu phải có mức trễ đo được và bằng chứng đáp ứng, thay vì dựa vào hành vi giao diện.

### “Xác thực thành công là được xem tài nguyên”

API vẫn cần kiểm tra quyền trên hành động, đối tượng và tenant phù hợp. Danh tính hợp lệ chỉ cung cấp một đầu vào đáng tin cho quyết định đó.

## 18. Chuyển mục tiêu bảo mật thành thiết kế cụ thể

Với mỗi API được bảo vệ, nhóm nên xác định được một đường đi đầy đủ: chủ thể nhận credential theo luồng nào, API nhận bằng chứng ở đâu, verifier kiểm tra điều kiện gì, danh tính được ánh xạ thế nào và lớp nghiệp vụ nhận danh tính ấy bằng cách nào.

Sau đó, gắn đường đi này với các tình huống thất bại: token sai đích, khóa thay đổi, credential bị lộ, dependency timeout, route mới chưa cấu hình hoặc request đi qua một đường mạng khác. Mỗi tình huống phải có hành vi quan sát được và người chịu trách nhiệm thực hiện.

Thiết kế xác thực API đạt mục tiêu khi request được bảo vệ chỉ đi tiếp với bằng chứng hợp lệ theo hợp đồng, danh tính không thể bị thay bằng dữ liệu tự khai và hệ thống giữ được các điều kiện ấy trong cả đường thành công lẫn đường lỗi. Việc quyết định chủ thể được phép làm gì với từng tài nguyên tiếp tục thuộc lớp phân quyền.
