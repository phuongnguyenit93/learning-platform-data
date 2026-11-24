# Binding token to browser — Ràng buộc token khôi phục với trình duyệt

## 1. Ràng buộc với trình duyệt bảo vệ điều gì?

Một token khôi phục dạng bearer cho phép bên có token chứng minh quyền tiếp tục một bước khôi phục trong phạm vi đã được cấp. Nếu chỉ cần token trong email, người lấy được liên kết có thể thử dùng nó ở một trình duyệt khác.

**Binding token to browser** bổ sung điều kiện: ngoài token hợp lệ, yêu cầu còn phải xuất phát từ ngữ cảnh trình duyệt mà máy chủ đã ràng buộc khi cấp token. Trong mô hình của bài, ngữ cảnh đó được đại diện bằng một bí mật ngẫu nhiên riêng trong cookie.

Ví dụ:

~~~text
T = bí mật token gửi qua email
B = bí mật ngữ cảnh trình duyệt, giữ trong cookie

Điều kiện tiếp tục:
    T hợp lệ
    và B hợp lệ
    và T được ràng buộc với ngữ cảnh của B
    và luồng vẫn cho phép hành động
~~~

T và B được tạo độc lập. Email chỉ chứa T; không chứa B hoặc dữ liệu đủ để dựng lại B.

Cơ chế này giúp hạn chế việc dùng **một liên kết bị lộ riêng lẻ** ở nơi không có cookie tương ứng. Nó không chứng minh danh tính người ngồi trước máy, không bảo đảm máy tính sạch mã độc và không tự biến khôi phục qua email thành xác thực MFA.

Ở đây, “browser binding” là một lựa chọn thiết kế của ứng dụng. Nó không có nghĩa ứng dụng đang triển khai một giao thức có tên Token Binding, cũng không có nghĩa trình duyệt cung cấp một ID phần cứng đáng tin để máy chủ nhận diện người dùng.

## 2. Hiểu đúng mô hình đe dọa

Giả sử người dùng bắt đầu khôi phục trong trình duyệt A. Máy chủ cấp cookie B cho A và gửi token T qua kênh khôi phục đã đăng ký.

| Bên đang thực hiện yêu cầu | Có T? | Có B đúng? | Kết quả mong muốn |
| --- | --- | --- | --- |
| Người dùng tiếp tục ở A | Có | Có | Có thể tiếp tục nếu các điều kiện khác đạt |
| Bên chỉ lấy được liên kết | Có | Không | Không được dùng T theo tuyến ràng buộc này |
| Bên chỉ lấy được cookie ngữ cảnh | Không | Có | Không đủ để tiếp tục |
| Bên lấy được cả token và cookie | Có | Có | Ràng buộc bằng cookie không tự phân biệt được |
| Mã độc điều khiển A | Có thể có | Có thể sử dụng gián tiếp | Cần các lớp bảo vệ khác |
| Người dùng mở email trong trình duyệt B | Có | Không | Cần cách tiếp tục được thiết kế rõ ràng |

Một giới hạn quan trọng: kẻ tấn công có thể **tự bắt đầu** yêu cầu khôi phục cho tài khoản nạn nhân trong trình duyệt của họ. Khi đó, cookie ràng buộc thuộc về trình duyệt của kẻ tấn công. Nếu họ còn chiếm được token gửi đến nạn nhân, điều kiện ràng buộc vẫn có thể đạt.

Vì vậy, cookie chứng minh sự liên tục với nơi khởi tạo yêu cầu; nó không chứng minh nơi khởi tạo đó được chủ tài khoản kiểm soát. Bảo vệ kênh nhận, chống lạm dụng, đánh giá rủi ro và yêu cầu xác minh phù hợp vẫn quyết định độ an toàn của toàn tuyến khôi phục.

Không mô tả T và B là hai yếu tố xác thực độc lập chỉ vì chúng nằm ở hai vị trí. Cả hai có thể cùng bị sử dụng bởi một môi trường trình duyệt đã bị kiểm soát.

## 3. Ba loại bí mật và ba vai trò khác nhau

Một thiết kế dễ hiểu nên tách:

| Dữ liệu | Vai trò | Nơi sử dụng |
| --- | --- | --- |
| Token khôi phục T | Bằng chứng từ kênh khôi phục | Gửi qua email hoặc kênh đã được phép |
| Bí mật ngữ cảnh B | Chứng minh sự liên tục với ngữ cảnh trình duyệt | Cookie được máy chủ kiểm tra |
| Token chống CSRF C | Ràng buộc yêu cầu thay đổi trạng thái với phiên/ngữ cảnh hợp lệ | Form hoặc header theo cơ chế của ứng dụng |

T không thay thế C. Cookie B cũng không thay thế C, vì trình duyệt tự gửi cookie theo quy tắc của nó. Máy chủ phải phân biệt “cookie có mặt” với “người dùng chủ động gửi một yêu cầu được phép”.

Tương tự, một giá trị `flow_id` trong URL chỉ giúp định vị luồng. Nó không được dùng thay B nếu đây là dữ liệu công khai hoặc có thể sao chép cùng liên kết.

Ví dụ cấu trúc lưu trữ ở máy chủ:

~~~yaml
browser_context:
  id: browser_ctx_17
  binding_lookup: "<gia-tri-kiem-chung-cua-B>"
  state: ACTIVE
  expires_at: "2026-11-23T04:20:00Z"

recovery_token:
  id: recovery_tok_29
  flow_id: recovery_flow_8
  browser_context_id: browser_ctx_17
  purpose: PASSWORD_RESET
  verifier: "<gia-tri-kiem-chung-cua-T>"
  state: ACTIVE
  expires_at: "2026-11-23T04:10:00Z"
~~~

Đây là schema minh họa, không phải cấu hình thời hạn bắt buộc.

Máy chủ có thể dùng giá trị kiểm chứng hoặc tra cứu có khóa cho B, thay vì lưu cookie nguyên văn. Nếu dùng HMAC, khóa phải được bảo vệ và dữ liệu đầu vào phải được mã hóa không nhập nhằng. Bản ghi token lưu liên hệ tới ngữ cảnh, không cần nhét B vào token được gửi cho người dùng.

Bản ghi ngữ cảnh chỉ là một thực thể phục vụ khôi phục; có nó không đồng nghĩa đang có session đăng nhập của tài khoản.

## 4. Thiết lập ràng buộc trước khi phát hành token

Điểm thời gian tạo ràng buộc rất quan trọng. Một trình tự minh họa:

1. Người dùng mở trang bắt đầu khôi phục.
2. Máy chủ kiểm tra cookie ngữ cảnh hiện có. Nếu cần tạo mới, nó tự sinh B bằng nguồn ngẫu nhiên mật mã và lưu ngữ cảnh tương ứng.
3. Trang hiển thị form cùng biện pháp chống CSRF phù hợp.
4. Người dùng gửi yêu cầu khôi phục. Máy chủ kiểm tra ngữ cảnh, CSRF, tần suất và chính sách của tuyến.
5. Máy chủ tạo T độc lập và lưu token với `browser_context_id` đã xác định ở phía máy chủ.
6. Máy chủ gửi T đến kênh nhận đã được cho phép.
7. Khi người dùng nộp T, máy chủ yêu cầu cookie B khớp với ràng buộc đã lưu.

~~~mermaid
sequenceDiagram
    participant A as Trình duyệt khởi tạo
    participant S as Dịch vụ khôi phục
    participant M as Kênh nhận đã đăng ký
    A->>S: Mở trang khôi phục
    S-->>A: Cookie ngữ cảnh B và form
    A->>S: Yêu cầu khôi phục + B + bảo vệ CSRF
    S->>S: Lưu token T gắn với ngữ cảnh B
    S-->>M: Gửi liên kết chứa T
    M-->>A: Người dùng mở liên kết
    A->>S: Xác nhận sử dụng T + cookie B
    S->>S: Kiểm tra và tiêu thụ nguyên tử
    S-->>A: Quyền khôi phục hạn chế, nếu được phép
~~~

Không chờ đến khi nhận T lần đầu mới ghi “trình duyệt hiện tại là trình duyệt được ràng buộc”. Làm như vậy cho phép người lấy được T đến trước và tự nhận ràng buộc.

Nếu máy chủ lưu một quyết định `binding_required=true` cho token, client không được đổi thành `false`, cung cấp context khác hoặc chọn một endpoint thay thế để bỏ qua điều kiện đó.

## 5. Dùng cookie với phạm vi và thuộc tính rõ ràng

Một header minh họa trên host HTTPS dành cho khôi phục:

~~~http
Set-Cookie: __Host-RecoveryContext=<B>; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=900
~~~

Ý nghĩa của các thuộc tính:

| Thuộc tính | Tác dụng |
| --- | --- |
| `Secure` | Cookie được gửi qua HTTPS |
| `HttpOnly` | JavaScript không đọc trực tiếp cookie qua API cookie thông thường |
| `__Host-` | Với trình duyệt hỗ trợ, yêu cầu Secure, Path=/ và không có Domain |
| `SameSite=Lax` | Cho phép một số điều hướng cấp cao nhất từ site khác bằng phương thức an toàn |
| `Max-Age=900` | Ví dụ giới hạn lưu cookie phía trình duyệt; không thay thời hạn máy chủ |

Các thuộc tính cookie được mô tả trong tài liệu [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie). Giá trị 900 giây ở đây chỉ minh họa.

Do tiền tố `__Host-` yêu cầu `Path=/`, không dùng nó cùng `Path=/recovery`. Nếu cần cô lập ứng dụng khôi phục với các ứng dụng khác, có thể cân nhắc host chuyên dụng cùng ranh giới triển khai phù hợp; không coi Path là ranh giới chống mã độc trên cùng origin.

Cookie không cần chứa email, account ID, token khôi phục hoặc kết quả xác minh danh tính. Một bí mật ngẫu nhiên không mang nghĩa nghiệp vụ giúp giảm dữ liệu bị lộ khi cookie bị quan sát.

Máy chủ vẫn phải kiểm tra thời hạn và trạng thái của ngữ cảnh. Việc người dùng xóa cookie không tự thu hồi bản sao đã bị lấy cắp; việc cookie còn trên trình duyệt cũng không chứng minh nó còn quyền ở máy chủ.

### SameSite và liên kết mở từ email

Email web thường là một site khác với ứng dụng khôi phục. Với `SameSite=Strict`, cookie có thể không đi kèm lần điều hướng đầu tiên từ email. `Lax` có thể phù hợp với liên kết điều hướng cấp cao nhất dùng GET, nhưng thiết kế phải xét tuyến điều hướng thực tế. OWASP giải thích sự khác nhau giữa Strict và Lax trong [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Thiếu cookie trên yêu cầu đầu tiên chưa đủ để kết luận người dùng chắc chắn dùng một trình duyệt khác. Nó có thể liên quan đến quy tắc cookie hoặc môi trường mở liên kết.

Trang đích nên tách việc hiển thị hướng dẫn khỏi việc tiêu thụ token. Nếu thiết kế có bước điều hướng nội bộ hoặc xác nhận tiếp, máy chủ vẫn phải kiểm tra ràng buộc tại yêu cầu quyết định. Không được coi việc điều hướng qua một trang trung gian là lý do để tự tạo B mới và gắn lại token.

## 6. Kiểm tra ở phía máy chủ tại điểm cấp quyền

Một phép kiểm tra đúng không chỉ hỏi “request có cookie không?”. Nó phải kiểm tra quan hệ giữa cookie, token và hành động.

Mã giả:

~~~text
redeemBoundRecoveryToken(request):
    enforceRequestSizeAndTrafficLimits(request)
    validateCsrfAndAllowedRequestOrigin(request)

    submittedSecret = parseRecoveryTokenStrictly(request.body.token)
    browserSecret = parseBindingCookieStrictly(request.cookies)

    context = lookupActiveBrowserContext(browserSecret)
    tokenSnapshot = lookupTokenFromSubmittedValue(submittedSecret)

    if context missing or tokenSnapshot missing:
        rejectWithoutGrantingRights()

    require verifyTokenSecret(submittedSecret, tokenSnapshot.verifier)
    require tokenSnapshot.browserContextId == context.id

    transaction:
        flow = lockRecoveryFlow(tokenSnapshot.flowId)
        currentToken = lockCurrentToken(flow)
        currentContext = lockOrVersionCheckBrowserContext(context.id)

        require currentToken.id == tokenSnapshot.id
        require verifierAndTokenVersionStillMatchCheckedSnapshot()
        require currentToken.state == ACTIVE
        require serverNow() < currentToken.expiresAt
        require currentContext.state == ACTIVE
        require serverNow() < currentContext.expiresAt
        require currentToken.browserContextId == currentContext.id
        require flowStillOpenAndCurrentPolicyAllowsAction()
        require tenantAccountPurposeAndRequestedActionMatchServerState()

        markTokenConsumed()
        grant = createFreshRestrictedRecoveryGrant(
            currentContext.id,
            approvedAccountAndPurpose(),
            boundedExpiry()
        )
        commitConsistentTokenAndGrantState()

    deliverRestrictedGrantSecurely(grant)
~~~

Mã giả lược bỏ chi tiết thuật toán, cấu trúc giao dịch và cách phục hồi sau lỗi mạng. Khi triển khai, mọi thao tác thu hồi hoặc đổi ngữ cảnh phải phối hợp với cùng cơ chế khóa hoặc kiểm tra phiên bản, để ngữ cảnh không bị thu hồi mà vẫn được chấp nhận từ snapshot cũ.

Không tin `browser_context_id`, `account_id` hoặc `purpose` mà client gửi để thay bản ghi chuẩn. Tài khoản và hành động đích phải được xác định từ dữ liệu đã ràng buộc ở máy chủ.

Giá trị bí mật cần được kiểm chứng bằng cơ chế phù hợp, có xử lý độ dài và định dạng rõ ràng. Không dùng so sánh tiền tố, bỏ phân biệt hoa thường hoặc coi hai giá trị thiếu là một kết quả khớp.

Nếu B không khớp, không tiêu thụ T chỉ để “ngăn thử lại”. Một người chỉ biết liên kết có thể dùng cách đó để làm hỏng cơ hội khôi phục của chủ tài khoản. Hệ thống vẫn ghi nhận thất bại và áp dụng kiểm soát lạm dụng theo phạm vi thích hợp.

Hai yêu cầu hợp lệ đồng thời cũng không được tạo hai quyền mới từ cùng T. Ràng buộc trình duyệt không thay thế tính dùng một lần và thao tác tiêu thụ nguyên tử.

## 7. Quyền hạn chế sau khi xác minh phải có định danh mới

Ngữ cảnh B ban đầu được tạo trước khi xác minh tài khoản. Vì vậy, không nên đơn giản đổi bản ghi đó thành một session đăng nhập đầy đủ sau khi T hợp lệ.

Một cách tách vai trò:

~~~text
B: ngữ cảnh trình duyệt phục vụ khôi phục
T: bằng chứng từ kênh khôi phục
G: quyền khôi phục hạn chế mới, được cấp sau khi T và B hợp lệ
~~~

G có định danh mới, thời hạn riêng và chỉ cho phép hành động đã duyệt. Nếu G tiếp tục phải gắn với cùng trình duyệt, bản ghi của G cần lưu liên hệ tới ngữ cảnh B và kiểm tra điều kiện đó khi thực hiện hành động nhạy cảm.

Ví dụ, G cho phép nộp mật khẩu mới thì không tự có quyền:

- Đổi địa chỉ email nhận khôi phục.
- Bỏ mọi yếu tố MFA.
- Đăng ký passkey mới.
- Xem dữ liệu cá nhân của tài khoản.
- Trở thành session đăng nhập thông thường.

Việc đổi định danh khi chuyển mức quyền và tách trạng thái trước/sau xác minh giúp giảm nguy cơ session fixation. Các nguyên tắc vòng đời và đổi session ID được trình bày trong [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Nếu phản hồi bị mất sau khi máy chủ đã tiêu thụ T và tạo G, không được giải quyết bằng cách cho T dùng lại không giới hạn. Cần một cơ chế retry hoặc tiếp tục giao dịch gắn với đúng ngữ cảnh và thao tác, có giới hạn quyền rõ ràng.

Sau khi khôi phục hoàn tất, thu hồi G và các dữ liệu của luồng theo chính sách. Việc xử lý session đăng nhập đang tồn tại là một quyết định riêng của quy trình kết thúc khôi phục.

## 8. Cookie không phải dấu vân tay của thiết bị

Một lỗi thiết kế thường gặp là gắn token với User-Agent hoặc IP rồi gọi đó là ràng buộc an toàn với trình duyệt.

| Dữ liệu | Có ích cho điều gì? | Vì sao không đủ làm bằng chứng chính? |
| --- | --- | --- |
| User-Agent | Quan sát thay đổi môi trường | Có thể bị giả mạo; nhiều người có cùng giá trị |
| Địa chỉ IP | Tín hiệu nguồn truy cập và rủi ro | Có thể đổi khi chuyển mạng; nhiều người dùng chung NAT |
| Độ phân giải, font, múi giờ | Một số phân tích môi trường | Có thể thay đổi, trùng lặp hoặc bị thao túng |
| Tên thiết bị do client gửi | Hiển thị hoặc hỗ trợ người dùng | Là dữ liệu tự khai |
| Cookie B ngẫu nhiên | Chứng minh biết bí mật ngữ cảnh | Vẫn có thể bị đánh cắp hoặc sử dụng trong môi trường bị kiểm soát |

Nếu người dùng chuyển từ Wi-Fi sang mạng di động nhưng vẫn có T và B hợp lệ, sự thay đổi IP không tự chứng minh họ là người khác. Nếu người tấn công sao chép User-Agent và truy cập từ cùng mạng, điều đó cũng không chứng minh họ là chủ tài khoản.

Có thể đưa các tín hiệu này vào đánh giá rủi ro để yêu cầu bước xác minh thêm hoặc chuyển tuyến. Không tự thay thế bằng một phép quyết định “IP bằng nhau thì cho qua, IP khác nhau thì khóa mọi cách khôi phục”.

Một cookie gắn với một kho cookie trong profile trình duyệt, không gắn tuyệt đối với con người hoặc phần cứng. Cùng máy nhưng khác profile, chế độ riêng tư và webview của ứng dụng email có thể không chia sẻ ngữ cảnh đó.

Nếu yêu cầu thật sự là chứng minh sở hữu khóa riêng, cần thiết kế cơ chế chứng minh bằng khóa và giao thức phù hợp. Không gọi cookie bearer hoặc một dấu vân tay là bằng chứng mật mã về thiết bị.

## 9. Chống CSRF, fixation và XSS là những lớp riêng

### CSRF

Do cookie tự được gửi, một website khác có thể cố khiến trình duyệt nạn nhân gửi yêu cầu thay đổi trạng thái. Cần dùng cơ chế chống CSRF phù hợp của framework hoặc thiết kế tương đương, kiểm tra ở máy chủ và ràng buộc với đúng ngữ cảnh.

Không dùng `flow_id` công khai như token CSRF. Không đưa bí mật B ra JavaScript chỉ để sao chép nó vào hidden field làm “CSRF token”. Các vai trò nên được tách để không làm mất lợi ích của HttpOnly.

OWASP mô tả synchronizer token, kiểm tra nguồn yêu cầu và các lớp hỗ trợ trong [Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

### Session fixation

Máy chủ phải tự tạo B. Không nhận một giá trị tùy ý từ URL như `browser_binding=abc` rồi tạo ngữ cảnh có bí mật đúng bằng giá trị đó.

Một cookie lạ không được mặc nhiên trở thành ngữ cảnh có quyền. Tại bước bắt đầu, ứng dụng có thể cấp ngữ cảnh mới do máy chủ sinh; tại bước sử dụng T đã ràng buộc, không được dùng cách đó để thay thế ràng buộc cũ.

Không phản chiếu B vào URL, email, liên kết chia sẻ hoặc một cơ chế “đồng bộ trình duyệt” không được xác minh.

### XSS và môi trường bị kiểm soát

HttpOnly hạn chế việc đọc trực tiếp cookie, nhưng mã độc đang chạy trên origin của ứng dụng vẫn có thể gửi yêu cầu trong ngữ cảnh người dùng. Vì vậy, không thể tuyên bố browser binding chống được XSS chỉ vì B không xuất hiện trong JavaScript.

Cần giữ trang khôi phục có bề mặt nội dung nhỏ, xử lý đầu vào đúng ngữ cảnh và hạn chế mã bên thứ ba. Các biện pháp với cookie không thay thế việc phòng ngừa mã thực thi không được tin cậy.

## 10. Mở liên kết ở trình duyệt khác và mất cookie

Trường hợp thường gặp:

~~~text
Khởi tạo trên Chrome ở máy tính
    ↓
Email đến điện thoại
    ↓
Người dùng bấm liên kết trong webview của ứng dụng email
    ↓
Có T nhưng không có B của Chrome
~~~

Nếu chính sách yêu cầu cùng ngữ cảnh trình duyệt, đây là một trường hợp thiếu điều kiện, dù người dùng có thể hoàn toàn hợp pháp.

Ứng dụng cần hướng dẫn rõ ràng, chẳng hạn:

- Mở liên kết bằng trình duyệt đã dùng để bắt đầu yêu cầu.
- Quay lại màn hình khôi phục đang mở và tiếp tục theo thao tác được cung cấp.
- Bắt đầu yêu cầu mới tại trình duyệt muốn sử dụng, theo chính sách cấp mới và chống lạm dụng.
- Chọn một tuyến xác minh bổ sung đã được thiết kế cho việc mất ngữ cảnh.

Không chuyển B từ máy tính sang điện thoại bằng cách nhét nó vào cùng liên kết T. Khi cả hai bí mật đi chung một URL, việc lộ URL có thể làm mất lợi ích của sự tách biệt ban đầu.

Không sửa bản ghi token sang cookie mới chỉ vì người mở liên kết chọn “Tôi là chủ tài khoản”. Tương tự, CAPTCHA hoặc một ô xác nhận không tự thay thế bằng chứng còn thiếu.

Nếu có cơ chế chuyển ngữ cảnh, nó cần điều kiện cho phép riêng, xác minh phù hợp, giới hạn thời gian và chốt trạng thái nhất quán. Việc chuyển phải làm mất quyền của ngữ cảnh cũ theo chính sách, thay vì để cả hai âm thầm cùng dùng một quyền.

Khi B bị xóa hoặc hết hạn, cần xử lý như mất bằng chứng ngữ cảnh. Không âm thầm bỏ điều kiện ràng buộc khi người dùng bật chế độ riêng tư hoặc chặn cookie.

## 11. Trang đích, link scanner và dữ liệu có token

Một hệ thống quét email có thể mở liên kết trước người dùng. Một lần GET của liên kết không nên tự tiêu thụ T hoặc cấp G chỉ vì máy chủ nhìn thấy token.

Có thể tách:

1. GET hiển thị trang xác nhận không làm thay đổi quyền.
2. Người dùng thực hiện thao tác rõ ràng.
3. POST kiểm tra T, B, CSRF và trạng thái hiện hành trước khi cấp quyền.

Trong mô hình cần B, scanner thường không có ngữ cảnh tương ứng; nhưng không được dựa hoàn toàn vào giả định đó. Thiết kế vẫn cần phân biệt việc đọc trang với việc thực hiện chuyển trạng thái.

Nếu T có mặt trong query string của lần truy cập đầu, nó có thể xuất hiện ở hạ tầng ghi log hoặc lịch sử truy cập. Cần kiểm soát log ở các tầng, tránh tài nguyên bên thứ ba trên trang nhạy cảm và đặt chính sách phản hồi thích hợp.

Ví dụ:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

OWASP lưu ý hạn chế rò token qua referrer trong [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Sau khi trao đổi token thành trạng thái hạn chế, điều hướng sang URL sạch giúp giảm việc tiếp tục truyền token. Nó không tự xóa những bản sao đã có trong log, email hoặc lịch sử trước đó.

Không ghi nguyên T, B, G, header Cookie hoặc URL đầy đủ có token vào audit. Có thể ghi token ID không bí mật, flow ID, phiên bản, nhóm lý do từ chối và kết quả xử lý theo quyền truy cập phù hợp.

## 12. Nhiều tab, nhiều luồng và thời hạn

Cookie thường được chia sẻ giữa các tab trong cùng profile và phạm vi cookie. Điều này có hai hệ quả:

- Browser binding không phân biệt người dùng đã mở đúng tab ban đầu hay một tab khác cùng ngữ cảnh.
- Nếu mỗi yêu cầu khôi phục đều ghi đè B bằng một giá trị mới, một tab có thể làm hỏng ràng buộc của tab khác.

Một phương án là giữ ngữ cảnh B còn hợp lệ cho profile và cho phép các luồng được quản lý riêng tham chiếu tới ngữ cảnh đó. Số luồng, thời hạn và hành vi cấp mới vẫn cần giới hạn rõ.

Không chỉ dùng B để đoán “token hiện tại thuộc account nào”. Một trình duyệt dùng chung có thể có nhiều yêu cầu. Mỗi T và G phải gắn với đúng tài khoản, tenant, mục đích và luồng ở máy chủ.

Các thời hạn cần được kiểm tra độc lập:

~~~text
token còn hạn
and browser context còn hạn
and recovery flow còn hạn
and restricted grant còn hạn, nếu đã được cấp
~~~

Cookie còn hiệu lực phía client không gia hạn token. Token được cấp lại cũng không tự gia hạn vô hạn ngữ cảnh hoặc thời hạn tổng của luồng.

Khi ngữ cảnh bị thu hồi vì rủi ro, mọi quyền yêu cầu ngữ cảnh đó cần kiểm tra lại trạng thái hoặc phiên bản theo thiết kế. Chỉ xóa cookie trên một phản hồi không đủ thu hồi một bản sao đã bị lấy đi.

Việc kết thúc một luồng cũng không nên vô tình hủy ngữ cảnh của các luồng khác nếu chúng được chính sách cho phép tồn tại riêng. Phạm vi thu hồi phải được mô tả trước.

## 13. Những tình huống cần có kết quả rõ ràng

| Tình huống | Kết quả theo mô hình ràng buộc bằng cookie |
| --- | --- |
| T đúng, B đúng, trạng thái còn cho phép | Có thể tiêu thụ T và cấp quyền hạn chế nguyên tử |
| T đúng, không có B | Không tự cấp quyền hoặc tạo lại ràng buộc từ T |
| T đúng, B thuộc ngữ cảnh khác | Từ chối tuyến hiện tại; không tiêu thụ T chỉ vì không khớp |
| B đúng nhưng T sai | Không đủ bằng chứng |
| T đã hết hạn nhưng B còn hạn | Từ chối T |
| T đúng nhưng ngữ cảnh đã bị thu hồi | Không dùng bản sao cookie để vượt trạng thái máy chủ |
| IP đổi nhưng T và B vẫn hợp lệ | Đánh giá theo chính sách rủi ro; không coi IP là bí mật |
| User-Agent giống nhau nhưng thiếu B | Không được xem là cùng ngữ cảnh đã ràng buộc |
| GET từ link scanner | Không tự tạo quyền hoặc tiêu thụ token |
| Hai POST hợp lệ cùng dùng T | Chỉ một lần tiêu thụ tạo quyền theo chính sách |
| Mở email bằng profile khác | Hướng dẫn tiếp tục hoặc tuyến xác minh được phép |
| Kẻ khác khởi tạo yêu cầu và chiếm được T | Binding có thể vẫn đạt; cần các lớp xác minh khác |

Trong luồng mất mật khẩu, cơ chế này có thể giúp kiểm soát việc dùng một liên kết bị lộ riêng lẻ. Trong luồng mất MFA, passkey hoặc thiết bị xác thực, nó vẫn chỉ là bằng chứng về sự liên tục của một ngữ cảnh web. Nó không tự tăng mức tin cậy của kênh email hoặc cho phép bỏ các yếu tố bảo vệ còn lại.

Ràng buộc token với trình duyệt có giá trị khi máy chủ thiết lập quan hệ trước lúc phát hành, giữ bí mật ngữ cảnh tách khỏi token và kiểm tra quan hệ đó tại thời điểm cấp quyền. Cách tiếp tục khi mất ngữ cảnh cũng là một phần của thiết kế: tuyến thay thế không được âm thầm bỏ điều kiện mà tuyến chính đang dựa vào.