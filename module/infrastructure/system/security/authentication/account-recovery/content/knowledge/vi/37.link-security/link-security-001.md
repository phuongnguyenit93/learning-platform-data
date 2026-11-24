# Secure recovery link scheme — Thiết kế liên kết khôi phục an toàn

## 1. Liên kết khôi phục là một đường dẫn mang quyền hạn chế

Một liên kết khôi phục không chỉ dẫn người dùng đến một trang web. Nó thường mang token có thể được dùng để tiếp tục một bước khôi phục tài khoản. Vì vậy, toàn bộ đường đi của liên kết cần được xem như đường đi của một bí mật có quyền hạn chế.

**Secure recovery link scheme** bao gồm hai lớp thiết kế:

- URI scheme và cấu trúc URL: giao thức nào, host nào, đường dẫn nào và dữ liệu nào được đưa vào liên kết.
- Hợp đồng sử dụng: máy chủ kiểm chứng token ra sao, khi nào tiêu thụ và hành động nào được phép sau đó.

Một URL dùng HTTPS chưa đủ an toàn nếu host do người tấn công lựa chọn. Một token ngẫu nhiên mạnh cũng chưa đủ nếu nó bị đưa qua hệ thống theo dõi click hoặc được tiêu thụ ngay khi bộ quét email mở trang.

Ví dụ cấu trúc minh họa:

~~~text
https://accounts.example.com/recovery/continue?v=1&token=<opaque-token>
~~~

Tên miền, phiên bản và placeholder trên chỉ phục vụ giải thích. Không có token thật trong ví dụ.

Máy chủ cần bảo đảm liên kết trỏ đến đúng ứng dụng, token chỉ có phạm vi đã cấp và việc mở trang không tự trở thành một hành động khôi phục ngoài ý muốn.

## 2. Xác định rõ từng thành phần của URL

| Thành phần | Ví dụ | Quy tắc thiết kế |
| --- | --- | --- |
| Scheme | https | Phát hành URL HTTPS ngay từ đầu |
| Host | accounts.example.com | Lấy từ cấu hình hoặc mapping đã được cho phép |
| Port | Mặc định của HTTPS | Chỉ dùng giá trị nằm trong chính sách origin |
| Path | /recovery/continue | Route cố định của tuyến khôi phục |
| Query version | v=1 | Chọn định dạng trong danh mục được hỗ trợ; không cho phép downgrade tùy ý |
| Token | Giá trị opaque | Chứa phần bí mật đủ mạnh và chỉ được kiểm chứng ở máy chủ |
| Đích tiếp tục | Một route nội bộ đã định nghĩa | Không nhận URL bất kỳ để chuyển tiếp |

Token opaque không cần làm lộ email, số điện thoại, account ID hoặc thông tin mất MFA trong URL. Máy chủ có thể giữ quan hệ giữa token và những dữ liệu đó trong bản ghi nội bộ.

Không lấy `purpose=DISABLE_MFA`, `account=...` hoặc `expires=...` trong query làm nguồn quyết định quyền. Nếu có những trường đó cho mục đích định tuyến hoặc hiển thị, chúng phải được đối chiếu với dữ liệu có thẩm quyền.

Tương tự, `v=1` không được biến thành quyền yêu cầu máy chủ dùng bất kỳ thuật toán nào. Phiên bản đầu vào phải thuộc danh mục cho phép và phù hợp với bản ghi hoặc giao thức đã được bảo vệ.

## 3. Origin phát hành phải đến từ nguồn tin cậy

Một lỗi nguy hiểm là dựng URL từ request hiện tại:

~~~text
recoveryUrl =
    request.scheme
    + "://"
    + request.host
    + "/recovery/continue?token="
    + token
~~~

Nếu host hoặc thông tin proxy có thể bị người gọi điều khiển, email hợp lệ của dịch vụ có thể chứa một liên kết đến host của kẻ tấn công. Người dùng bấm vào đó có thể gửi token tới nơi không được phép.

OWASP yêu cầu tránh dựa trực tiếp vào Host header để tạo URL đặt lại mật khẩu; dùng URL đã cấu hình hoặc danh sách domain tin cậy, đồng thời dùng HTTPS. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Một cách tổ chức:

~~~text
tenant được máy chủ xác định hợp lệ
    ↓
mapping origin khôi phục đã được quản lý
    ↓
endpoint cố định của tuyến
    ↓
token do máy chủ vừa cấp
    ↓
URL được dựng bằng quy tắc encoding đã xác định
~~~

Với nhiều tenant hoặc custom domain, mapping cần có quy trình cho phép và quản lý riêng. Một domain tồn tại trong dữ liệu do client gửi không tự trở thành đích được phát hành token.

Nếu đứng sau reverse proxy, chỉ tin các header chuyển tiếp từ proxy nằm trong ranh giới được cấu hình. Đọc `X-Forwarded-Host` thay cho Host không tự giải quyết vấn đề nếu người ngoài vẫn có thể đưa giá trị đó tới ứng dụng.

Nên so sánh origin theo các thành phần URL đã phân tích: scheme, hostname và port hiệu lực theo chính sách. Không kiểm tra bằng một phép tìm chuỗi con.

Hai URL sau không trỏ đến host mong muốn:

~~~text
https://accounts.example.com.attacker.example/recovery/continue
https://accounts.example.com@attacker.example/recovery/continue
~~~

Trong ví dụ thứ hai, phần trước ký tự @ là userinfo, không phải host đích. Việc chuỗi hiển thị có tên thương hiệu không chứng minh URL thuộc dịch vụ.

## 4. HTTPS bảo vệ đường truyền, không quyết định quyền

Phát hành liên kết HTTPS ngay từ đầu giúp tránh việc token phải đi qua một yêu cầu HTTP không mã hóa trước khi bị chuyển hướng.

Không nên tạo:

~~~text
http://accounts.example.com/recovery/continue?token=...
~~~

rồi dựa vào redirect sang HTTPS như toàn bộ biện pháp bảo vệ. Token có thể đã đi qua chặng không được bảo vệ trước đó.

Ứng dụng cần giữ toàn tuyến nhạy cảm trên HTTPS, gồm trang đích, tài nguyên tải kèm và các yêu cầu trao đổi token. Cấu hình TLS và hạ tầng kết thúc TLS cũng thuộc ranh giới bảo vệ.

Tuy nhiên, HTTPS không giúp phân biệt:

- Token còn hiệu lực hay đã được dùng.
- Người mở liên kết là chủ tài khoản hay người lấy được email.
- Một host có chứng chỉ hợp lệ có thuộc dịch vụ của mình hay không.
- Mục đích của token có cho phép thay mật khẩu hoặc gỡ MFA không.

Kẻ tấn công có thể có một website HTTPS của riêng họ. Vì thế, kiểm soát host và kiểm chứng quyền ở máy chủ vẫn là các điều kiện riêng.

## 5. Chọn vị trí token và hiểu đường rò tương ứng

| Vị trí | Đặc điểm | Điều phải xử lý |
| --- | --- | --- |
| Query string | Máy chủ nhận được trong URL yêu cầu | Access log, proxy, lịch sử, referrer theo chính sách |
| Path | Máy chủ cũng nhận được trong URL | Không tự tránh log hoặc lịch sử chỉ vì bỏ dấu hỏi |
| Fragment | Không được gửi trong HTTP request ban đầu | Cần logic phía trình duyệt nếu muốn chuyển cho máy chủ; script vẫn có thể đọc |
| Body của POST | Phù hợp cho bước nộp token sau trang đích | Vẫn có thể bị log bởi ứng dụng, APM hoặc hạ tầng |
| Cookie quyền hạn chế sau trao đổi | Giảm việc tiếp tục mang token gốc trong URL | Cần quản lý cookie, CSRF, phạm vi quyền và thời hạn |

Không có lựa chọn nào tự xóa toàn bộ rủi ro.

Query string có thể là lựa chọn thực dụng cho một liên kết email, nếu hệ thống kiểm soát các đường rò tương ứng. Path không phải cách “giấu token khỏi server log”.

Fragment có thể giảm việc token xuất hiện trong request URL ban đầu, nhưng nó đưa thêm trách nhiệm vào frontend. Mã bên thứ ba, mã độc cùng origin hoặc công cụ phân tích đọc toàn bộ location có thể vẫn thấy token. Không nên chọn fragment rồi tuyên bố token không thể rò.

POST giúp tách bước thay đổi trạng thái khỏi việc điều hướng đọc trang. Nó không phải một cơ chế mã hóa và không bảo đảm body bị ẩn khỏi mọi hệ thống ghi log.

Lựa chọn vị trí phải đi cùng hợp đồng parsing duy nhất. Không để một lớp đọc token từ query, lớp khác đọc từ path, còn một endpoint dự phòng nhận digest thay cho token gốc.

## 6. Token phải được ràng buộc với dữ liệu máy chủ

Một bản ghi minh họa:

~~~yaml
token_id: recovery_tok_12
tenant_id: tenant_3
account_id: account_28
flow_id: recovery_flow_6
purpose: PASSWORD_RESET
verifier_scheme: SHA256_RANDOM_SECRET_V1
verifier: "<gia-tri-kiem-chung-khong-phai-token-goc>"
state: ACTIVE
generation: 2
expires_at: "2026-11-23T05:10:00Z"
~~~

Máy chủ kiểm chứng phần bí mật đã nhận theo scheme được phép. Sau đó, nó kiểm tra phạm vi và trạng thái hiện hành trước khi chấp nhận.

Các thuộc tính cần có:

- Bí mật được sinh bằng nguồn ngẫu nhiên mật mã, không suy từ email hoặc thời gian.
- Phần bí mật có đủ không gian để chống đoán theo yêu cầu của tuyến.
- Bản ghi xác minh không cần giữ token nguyên văn.
- Token có thời hạn và mục đích cụ thể.
- Token đã tiêu thụ, thu hồi hoặc bị thay thế không được tiếp tục cấp quyền.
- Thao tác tiêu thụ phối hợp với việc tạo quyền hoặc hành động được bảo vệ.

Một token có chữ ký cũng cần kiểm chứng đúng giao thức và các claim phù hợp. Chữ ký hợp lệ không tự chứng minh token chưa được dùng hoặc chưa bị thay thế.

Nếu hệ thống yêu cầu ràng buộc trình duyệt hay ngữ cảnh khác, liên kết phải được dùng cùng điều kiện đó. Không có cookie tương ứng không phải lý do để một endpoint dự phòng bỏ điều kiện ràng buộc.

## 7. Tách mở liên kết khỏi tiêu thụ token

Một liên kết email có thể được mở bởi:

- Người dùng.
- Bộ quét an toàn thư.
- Trình xem trước.
- Công cụ tự động phân tích liên kết.
- Người được chuyển tiếp email.

Vì vậy, không nên gắn hành động thay đổi mật khẩu, bỏ MFA hoặc cấp session có quyền vào một GET đơn thuần.

RFC 9110 định nghĩa các phương thức safe với ngữ nghĩa về cơ bản là đọc, và GET thuộc nhóm này. Việc áp dụng ở đây là giữ hành động khôi phục có tác dụng an ninh ngoài lần mở trang đọc thông thường. [RFC 9110 — Safe Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1)

Một luồng minh họa:

~~~text
GET /recovery/continue?v=1&token=...
    → Hiển thị trang xác nhận tối giản.
    → Không tiêu thụ token hoặc cấp quyền khôi phục.

POST /recovery/redeem
    → Người dùng thực hiện thao tác rõ ràng.
    → Kiểm tra token, ngữ cảnh, CSRF và chính sách.
    → Tiêu thụ nguyên tử và tạo quyền hạn chế G.

303 tới /recovery/reset
    → URL không tiếp tục mang token gốc.
    → G được chuyển bằng cơ chế session phù hợp.

POST /recovery/reset
    → Kiểm tra G, CSRF và phạm vi hành động.
    → Thực hiện thay đổi được duyệt và kết thúc quyền tương ứng.
~~~

Một POST tự động chạy ngay khi trang vừa tải có thể vẫn bị môi trường quét có thực thi script kích hoạt. Đổi tên phương thức không thay thế việc thiết kế hành vi và điều kiện chuyển trạng thái.

Trang xác nhận cũng không phải bằng chứng xác minh danh tính mới. Một nút “Tiếp tục” giúp thể hiện ý định thao tác; nó không biến người có liên kết bị đánh cắp thành chủ tài khoản hợp lệ.

Mỗi quyền G chỉ nên cho phép bước đã được duyệt. Với tuyến đặt lại mật khẩu, G không tự có quyền đăng ký passkey hoặc vô hiệu hóa MFA.

## 8. Giảm rò qua referrer, cache và nội dung trang

Một trang chứa token trong URL không nên tải tùy ý mã theo dõi, công cụ ghi phiên hoặc tài nguyên bên thứ ba.

Ví dụ chính sách phản hồi:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

`Referrer-Policy: no-referrer` yêu cầu bỏ thông tin Referer trong các request liên quan theo chính sách đó. Tài liệu MDN mô tả ý nghĩa của directive này. [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)

Không phải mọi request cross-origin ở mọi cấu hình đều gửi nguyên path và query. Nội dung referrer phụ thuộc chính sách và ngữ cảnh. Tuy nhiên, tự cấu hình một chính sách phù hợp giúp tuyến khôi phục không phải dựa vào giả định mơ hồ về mặc định của môi trường.

`no-store` hướng đến việc không lưu phản hồi trong HTTP cache. Nó không tự xóa:

- URL đã có trong email hoặc lịch sử trình duyệt.
- Log ở CDN, reverse proxy hoặc load balancer.
- Trace ứng dụng.
- Ảnh chụp màn hình.
- Bản sao ở nhà cung cấp chuyển phát.

Trang đích cần tối giản dữ liệu. Trước khi xác minh, không nhất thiết hiển thị tên đầy đủ, danh sách yếu tố MFA hoặc các thông tin tài khoản chỉ vì query có một token trông hợp lệ.

Nếu đặt token vào form để nộp POST, phải encode đúng ngữ cảnh HTML và không đưa nó vào mã thực thi. Cơ chế bảo vệ XSS và CSRF vẫn cần được áp dụng theo thiết kế của ứng dụng.

## 9. Redirect và tracking có thể làm token đi sai nơi

### Tránh đích chuyển tiếp tùy ý

Một URL dạng:

~~~text
https://accounts.example.com/recovery/continue
    ?token=<T>
    &next=https://attacker.example/collect
~~~

có thể tạo nguy cơ chuyển hướng không được phép. Nếu logic còn chuyển tiếp token hoặc grant đến `next`, quyền khôi phục cũng có thể bị mang đi.

Một phương án dễ kiểm soát hơn là dùng một khóa route nội bộ:

~~~text
continuation = PASSWORD_RESET_FORM
~~~

Máy chủ ánh xạ khóa đó sang route cố định đã cho phép. Không cần cho caller chọn URL bất kỳ.

Nếu phải nhận return URL, dùng bộ phân tích URL hoặc helper phù hợp, kiểm tra thành phần và quyền sử dụng. Không chỉ kiểm tra chuỗi bắt đầu bằng dấu /, vì giá trị dạng `//attacker.example/path` có thể được diễn giải là đích ngoài.

OWASP khuyến nghị hạn chế và xác thực đích redirect thay vì tin đầu vào chưa được kiểm chứng. [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)

### Theo dõi click và rút gọn liên kết

Một dịch vụ trung gian có thể bọc URL thành liên kết theo dõi. Nếu URL đích chứa T, hệ thống trung gian có thể giữ bản sao của T trong cấu hình, log hoặc báo cáo.

Với tuyến khôi phục, cần quyết định rõ việc có cho phép tracking và rút gọn hay không. Không tự dùng cùng cấu hình marketing cho email mang token bảo mật.

Ngay cả khi tắt tracking của nhà cung cấp gửi, hệ thống bảo vệ thư ở phía người nhận vẫn có thể xử lý liên kết. Thiết kế không được mặc định chỉ trình duyệt người dùng có thể nhìn hoặc mở URL.

Không đặt một liên kết chứa token thật vào công cụ kiểm tra URL công khai để chẩn đoán một sự cố. Việc dán vào đó là cung cấp bí mật cho một bên khác.

## 10. Dựng liên kết theo một hợp đồng hẹp

Mã giả dưới đây minh họa bước phát hành, không phải một triển khai dịch vụ hoàn chỉnh:

~~~text
createRecoveryLink(serverContext, recoveryRequest):
    enforceAbuseControls(recoveryRequest)

    scope = resolveAllowedRecoveryScope(serverContext, recoveryRequest)
    endpoint = configuredRecoveryEndpoint(scope.tenant, scope.route)

    require endpoint.scheme == "https"
    require endpoint.origin is explicitly approved
    require endpoint has no userinfo
    require endpoint.path == approvedPathFor(scope.route)
    require endpoint has no unexpected query or fragment

    secret = generateCryptographicallyRandomSecret()
    publicToken = encodeAccordingToTokenVersion(secret)
    verifier = deriveServerVerifier(secret, scope)

    transaction:
        requireCurrentScopeAndPolicyStillAllowIssuance(scope)
        saveTokenVerifierAndBoundMetadata(verifier, scope)
        saveProtectedDeliveryTaskForApprovedDestination(
            endpoint,
            publicToken,
            scope
        )
        commit()

    return genericRequestAcceptedResponse()
~~~

Những điều cần giữ rõ:

- Endpoint được lấy từ cấu hình đã quản lý, không ghép từ một base URL do client gửi.
- Dữ liệu động được encode theo đúng vị trí trong URL.
- Không gửi token như đã được cấp nếu giao dịch lưu trạng thái thất bại.
- Kênh nhận được lấy từ quyết định được cho phép, không tùy ý đổi theo request.
- Nếu giữ token phục vụ gửi lại, bản lưu chuyển phát cần bảo vệ riêng và thời gian lưu phù hợp.
- Phản hồi công khai không cần trả token cho người chỉ mới khai địa chỉ email.

Ở bước nhận liên kết, parser cần giới hạn độ dài, bảng ký tự, số trường và phiên bản. Nếu có hai tham số token trùng tên, không nên để proxy, framework và logic nghiệp vụ chọn những giá trị khác nhau. Hợp đồng nhận cần xử lý trường hợp nhập nhằng một cách nhất quán.

Không giải mã URL nhiều lần ở các tầng khác nhau mà không có quy tắc. Không “sửa hộ” token bằng cách đổi hoa/thường hoặc bỏ ký tự dư để cố làm nó khớp.

## 11. Điểm chốt quyền cần kiểm tra lại trạng thái

Một quy trình nhận token minh họa:

~~~text
redeemRecoveryLink(request):
    enforceSizeAndRateLimits()
    validateExpectedRequestMethodAndCsrfContext()

    token = parseExactlyOneSupportedToken(request)
    snapshot = locateTokenInTrustedScope(token)
    require verifySubmittedSecret(token, snapshot)

    transaction:
        current = lockCurrentTokenAndRecoveryState(snapshot)
        require checkedVerifierAndVersionStillMatch(current, snapshot)
        require current.state == ACTIVE
        require currentTokenAndFlowHaveNotExpired()
        require currentTokenHasNotBeenReplacedOrRevoked()
        require tenantAccountPurposeAndContextStillMatch()
        require recoveryPolicyAllowsTheRequestedStep()

        consumeTokenConditionally()
        grant = createUniqueRestrictedGrant()
        recordAuditWithoutSecrets()
        commit()

    return grantUsingApprovedSessionMechanism()
~~~

Đường dẫn trong URL không tự xác định quyền. Token được cấp cho bước xác minh email không được dùng để gọi route gỡ MFA chỉ vì người gọi thay path.

Khi hai node cùng nhận một liên kết, việc tiêu thụ và tạo quyền cần giữ nhất quán để chỉ kết quả được phép thành công. Chữ ký hoặc digest khớp không ngăn được dùng lại nếu trạng thái chưa được chốt nguyên tử.

Nếu kho dữ liệu có thẩm quyền không khả dụng, không dùng một bản cache ACTIVE cũ để cấp quyền. Nếu client mất phản hồi sau commit, cơ chế retry phải tránh tạo thêm grant từ cùng token.

Liên kết đã dùng hoặc hết hạn có thể dẫn đến thông báo tiếp tục phù hợp. Không hiển thị chi tiết nội bộ như verifier, số byte khớp hoặc toàn bộ trạng thái tài khoản cho người chưa được xác minh.

## 12. Cấp lại, bàn giao cho ứng dụng và session sau khôi phục

### Cấp liên kết mới

Cần định nghĩa việc “gửi lại” là gửi lại cùng tác vụ hay cấp token mới. Nếu token mới thay token cũ, máy chủ cần chốt quan hệ hiệu lực nhất quán.

Không cho một yêu cầu công khai liên tục vô hiệu hóa mọi liên kết đang dùng mà thiếu kiểm soát lạm dụng. Điều đó có thể bị dùng để cản chủ tài khoản hoàn thành khôi phục.

Email cũ đến muộn không làm token cũ sống lại. Thứ tự chuyển phát không phải nguồn chuẩn của token hiện hành.

### Bàn giao cho ứng dụng

Nếu tuyến cần mở ứng dụng di động, cần thiết kế riêng việc xác định ứng dụng nhận và trao đổi quyền. Không cho client tùy ý đổi scheme từ HTTPS sang một giá trị tự khai rồi chuyển raw token theo.

Một mã bàn giao hạn chế, có thời hạn và dùng một lần có thể là một thành phần của thiết kế, nhưng nó cũng cần được ràng buộc với đúng đích và hành động. Không coi thêm một redirect là đủ để bảo vệ bàn giao.

### Session và mức xác minh

Hoàn thành bước từ liên kết có thể tạo session khôi phục hạn chế. Session này cần định danh và thời hạn phù hợp, bảo vệ cookie và kiểm tra quyền tại hành động nhạy cảm.

Khôi phục mật khẩu không tự cho phép tự động đăng nhập đầy đủ hoặc thay mọi yếu tố xác thực. Luồng mất MFA, passkey hoặc thiết bị xác thực có thể cần thêm bằng chứng và quyết định rủi ro riêng.

Sau khi hành động cuối hoàn tất, xử lý grant, token liên quan và các session hiện có theo chính sách của tuyến. Không chỉ xóa token khỏi thanh địa chỉ rồi coi vòng đời quyền đã kết thúc.

## 13. Những tình huống cần có kết quả rõ ràng

| Tình huống | Hành vi phù hợp |
| --- | --- |
| Request đưa Host khác vào bước yêu cầu khôi phục | Không dùng trực tiếp giá trị đó để phát hành URL |
| URL dùng HTTPS nhưng host ngoài danh sách | Không coi là URL khôi phục hợp lệ của dịch vụ |
| Token nằm trong path | Vẫn kiểm soát log, lịch sử và các đường rò |
| Token nằm trong fragment | Không mặc định frontend hoặc script không thể thấy |
| Bộ quét mở GET | Không tự tiêu thụ token hoặc tạo quyền |
| POST tự động khi trang vừa tải | Không coi tên phương thức là đủ chứng minh ý định |
| Tham số next trỏ ra ngoài | Từ chối hoặc ánh xạ sang đích đã cho phép |
| URL có nhiều tham số token | Xử lý theo hợp đồng không nhập nhằng |
| Token đúng nhưng đã bị thay | Không cấp quyền dù thời hạn cũ chưa hết |
| Token đúng nhưng purpose khác | Không cho đổi hành động bằng cách sửa route |
| Hai yêu cầu cùng nộp token | Chỉ chốt kết quả theo quy tắc dùng một lần |
| URL sạch sau redirect | Giảm truyền token tiếp; không xóa các bản sao đã có |
| Tracking giữ bản sao URL | Xem đó là một đường truy cập dữ liệu bí mật |
| Liên kết email dùng trong luồng mất MFA | Chỉ có mức bằng chứng mà tuyến email được phép cung cấp |

Một thiết kế liên kết an toàn cần giữ đúng cả đích đến lẫn ý nghĩa quyền: origin được kiểm soát, token được bảo vệ trên đường đi, parsing rõ ràng và trạng thái được chốt ở máy chủ. Những thuộc tính đó phải còn đúng khi liên kết được mở tự động, chuyển tiếp, gửi lại hoặc dùng đồng thời.