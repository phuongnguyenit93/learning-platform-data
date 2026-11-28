# Authentication statement

## 1. Authentication statement là gì?

Trong SAML 2.0, **authentication statement** là phát biểu của bên phát hành assertion về một sự kiện xác thực đã diễn ra đối với chủ thể. Phần tử XML tương ứng là `AuthnStatement`.

Trong mô hình đăng nhập liên kết thông dụng, Identity Provider (IdP) xác thực người dùng và phát hành assertion. Service Provider (SP) tiếp nhận assertion, xác minh theo quan hệ tin cậy đã cấu hình, rồi sử dụng authentication statement để biết người dùng đã được xác thực khi nào và trong ngữ cảnh nào.

Ví dụ, nhân viên đăng nhập vào cổng nhân sự bằng tài khoản doanh nghiệp. IdP xác nhận rằng chủ thể `employee-1842` đã được xác thực lúc 08:00 UTC bằng một ngữ cảnh xác thực cụ thể. Cổng nhân sự không cần nhận mật khẩu của nhân viên; nó dựa vào assertion hợp lệ của IdP và chính sách cục bộ để quyết định có thiết lập phiên hay không.

Authentication statement không tự cấp quyền duyệt lương hoặc quản lý tài khoản. Nó cung cấp thông tin về xác thực; SP vẫn phải thực hiện kiểm soát quyền truy cập phù hợp với ứng dụng.

## 2. Vị trí trong SAML assertion

Một SAML assertion có thể chứa chủ thể, điều kiện sử dụng và các statement. Những loại statement cần phân biệt gồm:

| Thành phần | Câu hỏi được trả lời |
|---|---|
| `Subject` | Assertion nói về chủ thể nào? |
| `Conditions` | Assertion chỉ được sử dụng trong những giới hạn nào? |
| `AuthnStatement` | Sự kiện xác thực nào đã diễn ra với chủ thể? |
| `AttributeStatement` | Bên phát hành cung cấp những thuộc tính nào về chủ thể? |
| `AuthzDecisionStatement` | Bên phát hành đưa ra quyết định ủy quyền nào đối với tài nguyên và hành động? |

Trong SSO, authentication statement thường được sử dụng cùng thông tin chủ thể và có thể kèm các thuộc tính như phòng ban hoặc nhóm. Không phải mọi loại statement đều xuất hiện trong mọi assertion hoặc mọi hồ sơ tích hợp.

```text
SAML Response
└── Assertion
    ├── Issuer
    ├── Subject
    ├── Conditions
    ├── AuthnStatement
    │   ├── AuthnInstant
    │   ├── SessionIndex, nếu có
    │   ├── SessionNotOnOrAfter, nếu có
    │   ├── SubjectLocality, nếu có
    │   └── AuthnContext
    └── AttributeStatement, nếu có
```

Sơ đồ lược bỏ chữ ký và các chi tiết khác để thể hiện vị trí của `AuthnStatement`. Một authentication statement đứng riêng không phải một phản hồi đăng nhập SAML hoàn chỉnh có thể chấp nhận trong môi trường thật.

## 3. Cấu trúc của AuthnStatement

Ví dụ XML rút gọn:

```xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2026-01-15T08:00:00Z"
    SessionIndex="_idp-session-example-1842"
    SessionNotOnOrAfter="2026-01-15T09:00:00Z">

    <saml:AuthnContext>
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </saml:AuthnContext>
</saml:AuthnStatement>
```

Các thời điểm và định danh trong ví dụ là dữ liệu minh họa. Phần tử này chưa có assertion bao ngoài, subject, điều kiện sử dụng hay bằng chứng chữ ký cần thiết của một phản hồi đăng nhập thực tế.

| Trường hoặc phần tử | Ý nghĩa | Sự hiện diện trong AuthnStatement |
|---|---|---|
| `AuthnInstant` | Thời điểm sự kiện xác thực diễn ra | Bắt buộc |
| `SessionIndex` | Tham chiếu tới phiên xác thực do bên phát hành quản lý | Tùy chọn |
| `SessionNotOnOrAfter` | Mốc mà phiên được mô tả không còn được coi là hợp lệ | Tùy chọn |
| `SubjectLocality` | Thông tin địa chỉ mạng hoặc DNS về nơi xác thực | Tùy chọn |
| `AuthnContext` | Ngữ cảnh của sự kiện xác thực | Bắt buộc |

Tên trường phân biệt chữ hoa và chữ thường. `AuthnInstant` là thuộc tính của `AuthnStatement`, không phải một thuộc tính người dùng nằm trong `AttributeStatement`.

## 4. AuthnInstant: thời điểm xác thực

### 4.1. Khác với thời điểm phát hành assertion

`AuthnInstant` cho biết sự kiện xác thực được mô tả diễn ra lúc nào. `IssueInstant` trên assertion cho biết assertion được phát hành lúc nào. Hai thời điểm có thể khác nhau.

Ví dụ:

| Sự kiện | Thời điểm UTC |
|---|---|
| Người dùng xác thực tại IdP | 08:00 |
| Người dùng truy cập ứng dụng A và nhận assertion | 08:05 |
| Người dùng tiếp tục truy cập ứng dụng B bằng phiên SSO sẵn có | 08:25 |

Assertion cho ứng dụng B có thể được phát hành lúc 08:25 nhưng vẫn mô tả sự kiện xác thực lúc 08:00. Nhận một assertion mới không tự chứng minh người dùng vừa nhập lại mật khẩu hoặc vừa thực hiện MFA.

### 4.2. Liên quan tới độ mới của xác thực

Một ứng dụng có thể yêu cầu xác thực đủ mới trước khi cho phép thao tác nhạy cảm. Khi đó, nó cần đánh giá thời điểm xác thực cùng chính sách tương ứng, thay vì chỉ xem assertion còn hạn hay không.

```text
Tuổi của sự kiện xác thực
    = thời điểm đánh giá của SP - AuthnInstant
```

Đây là một phép tính hỗ trợ chính sách. SP còn cần xử lý sai lệch đồng hồ có giới hạn, định dạng thời gian và các điều kiện của hồ sơ SAML đang dùng. Không tự chấp nhận một thời điểm xác thực bất hợp lý trong tương lai bằng cách mở rộng khoảng dung sai tùy ý.

Nếu yêu cầu xác thực lại chưa được đáp ứng, ứng dụng có thể khởi tạo luồng xác thực mới theo cấu hình hỗ trợ. Không sửa `AuthnInstant` trong assertion để làm cho sự kiện trông mới hơn.

## 5. AuthnContext: xác thực trong ngữ cảnh nào?

`AuthnContext` mô tả ngữ cảnh xác thực mà IdP đưa ra. Một cách biểu diễn thường gặp là `AuthnContextClassRef`, tham chiếu tới một lớp ngữ cảnh bằng URI.

Ví dụ `PasswordProtectedTransport` biểu thị một lớp ngữ cảnh liên quan tới xác thực bằng mật khẩu qua kênh truyền được bảo vệ theo định nghĩa của lớp đó. Nó không tự chứng minh người dùng đã thực hiện hai yếu tố xác thực, và cũng không mô tả đầy đủ mọi biện pháp bảo vệ của hạ tầng IdP.

SAML còn cho phép những cách biểu diễn ngữ cảnh khác như khai báo hoặc tham chiếu khai báo. Vì vậy, không giả định mọi `AuthnContext` hợp lệ đều chỉ có duy nhất một cách biểu diễn mà ứng dụng tự viết mã để đọc.

### 5.1. Không suy diễn MFA từ một tên bất kỳ

Một số liên kết sử dụng lớp ngữ cảnh hoặc URI riêng theo thỏa thuận để thể hiện mức xác thực mạnh hơn. SP cần biết rõ:

- Giá trị nào được IdP phát hành và cam kết với ý nghĩa gì.
- Chính sách tại IdP có thực sự bảo đảm điều kiện đó hay không.
- Những giá trị nào được ứng dụng chấp nhận cho từng hoạt động.
- Cách xử lý khi ngữ cảnh không có, không hiểu được hoặc không đáp ứng yêu cầu.

Không tìm một chuỗi chứa chữ `MFA` rồi mặc định đó là bằng chứng xác thực nhiều yếu tố có thể tin cậy. Giá trị chỉ có ý nghĩa khi được phát hành trong thông điệp đã xác minh và nằm trong quan hệ tin cậy, chính sách đã thống nhất.

### 5.2. Quan hệ với RequestedAuthnContext

SP có thể gửi `RequestedAuthnContext` trong `AuthnRequest` để biểu đạt yêu cầu về ngữ cảnh xác thực. IdP xử lý yêu cầu theo khả năng và hồ sơ tích hợp, rồi phản hồi kết quả tương ứng.

SP cần kiểm tra ngữ cảnh thực sự được trả về có đáp ứng chính sách hay không. Không coi việc mình đã yêu cầu một ngữ cảnh là bằng chứng IdP chắc chắn đã thực hiện thành công.

Các cách so sánh ngữ cảnh, chẳng hạn `exact` hoặc `minimum`, phải được hiểu theo quy tắc của hồ sơ và quan hệ tích hợp. Không so sánh URI theo thứ tự chữ cái hoặc tự quy đổi mọi lớp thành một thang điểm mạnh yếu chung.

### 5.3. ForceAuthn không đồng nghĩa với MFA

`ForceAuthn` trong yêu cầu xác thực liên quan tới việc yêu cầu IdP xác thực lại thay vì chỉ dựa vào phiên xác thực trước đó. Nó không tự quy định phải sử dụng hai yếu tố hay một phương thức cụ thể.

Nếu ứng dụng cần cả độ mới và mức xác thực thích hợp, nó phải thiết kế yêu cầu và kiểm tra kết quả cho cả hai điều kiện. Chỉ nhìn `AuthnInstant` mới hoặc chỉ nhìn tên ngữ cảnh đều chưa đủ cho mọi trường hợp.

## 6. SessionIndex và phiên xác thực

`SessionIndex` là một tham chiếu tới phiên được IdP mô tả. Nó có thể được sử dụng trong phối hợp quản lý phiên, bao gồm các luồng Single Logout khi triển khai hỗ trợ.

Không nên xem `SessionIndex` là:

- Session cookie của ứng dụng SP.
- Một access token có thể gửi tới API.
- Một credential chứng minh bên gửi là người dùng.
- Một định danh toàn cục có thể đối chiếu giữa mọi IdP mà không có ngữ cảnh.

Khi lưu dữ liệu phiên liên kết, ứng dụng cần giữ ngữ cảnh cần thiết như issuer, định danh chủ thể và session index nếu có. Một mình giá trị session index không đủ để xác định an toàn mọi phiên hoặc mọi người dùng.

`SessionIndex` là tùy chọn trong authentication statement. Khả năng đăng xuất liên kết còn phụ thuộc metadata, endpoint, binding, thông điệp logout và chính sách của từng bên. Có trường này không đồng nghĩa Single Logout đã hoạt động đầy đủ.

## 7. Phân biệt các mốc thời gian

Trong một luồng SAML SSO, nhiều mốc thời gian có thể cùng xuất hiện nhưng giới hạn những đối tượng khác nhau:

| Mốc thời gian | Đối tượng hoặc ý nghĩa chính |
|---|---|
| `AuthnStatement.AuthnInstant` | Thời điểm sự kiện xác thực |
| `Assertion.IssueInstant` | Thời điểm assertion được phát hành |
| `Conditions.NotBefore` | Giới hạn sớm của việc sử dụng assertion theo điều kiện |
| `Conditions.NotOnOrAfter` | Giới hạn cuối của việc sử dụng assertion theo điều kiện |
| `SubjectConfirmationData.NotOnOrAfter` | Giới hạn thời gian của dữ liệu xác nhận chủ thể tương ứng |
| `AuthnStatement.SessionNotOnOrAfter` | Giới hạn phiên xác thực được statement mô tả |
| Thời hạn session cục bộ của SP | Do ứng dụng quản lý theo chính sách và hồ sơ liên kết |

`NotOnOrAfter` có nghĩa tại thời điểm đó hoặc sau đó, điều kiện tương ứng không còn được đáp ứng. Cần xử lý dung sai đồng hồ theo chính sách rõ ràng, không coi mọi mốc thời gian là một trường hết hạn chung rồi bỏ các kiểm tra còn lại.

Một assertion có thể chỉ được chấp nhận trong vài phút để thiết lập phiên, trong khi phiên ứng dụng có vòng đời riêng. Ngược lại, một phiên ứng dụng còn cookie không bảo đảm sự kiện xác thực ban đầu vẫn đủ mới cho một hành động đặc quyền.

SP cần xử lý `SessionNotOnOrAfter` theo hồ sơ và chính sách đã thỏa thuận, đồng thời kiểm soát phiên cục bộ của mình. Không lấy thời hạn assertion làm thời gian được phép tái gửi assertion, và không dùng việc assertion mới phát hành để tự kéo dài vô hạn phiên đã có.

## 8. SubjectLocality: thông tin hỗ trợ, không phải bằng chứng thiết bị

`SubjectLocality` có thể cung cấp thông tin như địa chỉ IP hoặc tên DNS liên quan tới nơi chủ thể được xác thực.

Thông tin này có thể hữu ích cho quan sát hoặc đánh giá rủi ro, nhưng không mặc định là địa chỉ mà SP đang nhìn thấy ở callback. IdP và SP có thể nằm sau proxy, người dùng có thể đổi mạng, và nhiều thiết bị có thể chia sẻ một địa chỉ NAT.

Không cấp quyền quản trị chỉ vì một địa chỉ được xem là nội bộ xuất hiện trong statement. SP phải đánh giá nguồn dữ liệu, ý nghĩa đã thỏa thuận và chính sách liên quan; sự hiện diện của địa chỉ không chứng minh thiết bị đã được quản lý hoặc người dùng đã đáp ứng MFA.

## 9. SP sử dụng authentication statement như thế nào?

Xử lý `AuthnStatement` nằm trong quá trình xác minh toàn bộ phản hồi SAML theo hồ sơ sử dụng. Nó không phải bước tách một đoạn XML bất kỳ rồi tin nội dung.

Một trình tự khái niệm cho SSO do SP khởi tạo:

1. Tìm yêu cầu xác thực đang chờ và cấu hình IdP tương ứng.
2. Phân tích thông điệp bằng thành phần SAML/XML được cấu hình an toàn.
3. Kiểm tra nguồn phát hành và chữ ký theo metadata, khóa tin cậy cùng chính sách của liên kết.
4. Kiểm tra trạng thái phản hồi, audience, địa chỉ đích, recipient, tương quan yêu cầu và subject confirmation theo hồ sơ áp dụng.
5. Kiểm tra các giới hạn thời gian, ID đã được sử dụng và những điều kiện cần thiết để chống replay.
6. Đọc authentication statement từ chính assertion đã được xác minh; đánh giá thời điểm và ngữ cảnh xác thực theo yêu cầu của ứng dụng.
7. Ánh xạ chủ thể tới danh tính cục bộ một cách có kiểm soát, thiết lập phiên và kiểm tra quyền nghiệp vụ.

Thứ tự nội bộ cụ thể phụ thuộc thư viện, nhưng phiên người dùng chỉ được thiết lập sau khi các kiểm tra cần thiết thành công.

```text
validatedAssertion = validateSamlResponseUsingTrustedConfiguration(response)
subject = resolveSubjectFromValidatedAssertion(validatedAssertion)
authnStatement = selectStatementAccordingToConfiguredPolicy(validatedAssertion)

requireAcceptableAuthenticationTime(authnStatement)
requireAcceptableAuthenticationContext(authnStatement)

account = mapFederatedSubjectToLocalAccount(subject)
requireAccountAllowedToSignIn(account)
session = establishLocalSession(account, authnStatement)
```

Đây là mã giả minh họa trách nhiệm, không phải bộ xác minh SAML hoàn chỉnh. Không triển khai bằng cách dùng XPath tùy ý lấy `AuthnStatement` đầu tiên mà bỏ qua việc assertion nào đã được chữ ký bảo vệ.

Nếu một assertion có nhiều statement hoặc thông điệp có nhiều assertion, SP phải áp dụng chính sách xử lý đã xác định. Không chọn tùy ý statement có vẻ mới nhất hoặc mạnh nhất mà không xét chủ thể, ngữ cảnh và đối tượng đã xác minh.

## 10. Chữ ký, mã hóa và giới hạn tin cậy

### 10.1. Chữ ký phải bảo vệ đúng dữ liệu được sử dụng

Thông tin xác thực chỉ đáng tin khi nằm trong thông điệp được xác minh theo chính sách liên kết. Một lỗi nguy hiểm là xác minh chữ ký trên một phần tử nhưng đọc danh tính hoặc authentication statement từ một phần tử khác do kẻ tấn công đưa vào.

Đây là lý do cần thư viện xử lý SAML đúng cách, kiểm tra cấu trúc và liên kết rõ dữ liệu được sử dụng với đối tượng đã xác minh. Không tự giải quyết bằng cách chỉ kiểm tra trong XML có xuất hiện một phần tử `Signature` hay không.

### 10.2. Mã hóa không thay thế kiểm tra nguồn phát hành

Một assertion được mã hóa giúp bảo vệ tính bí mật cho bên nhận dự kiến theo cơ chế sử dụng. Việc giải mã thành công không tự thay cho xác minh tính toàn vẹn, nhà phát hành, audience và các điều kiện khác.

Tương tự, một chứng chỉ được nhúng trong thông điệp không tự trở thành khóa tin cậy chỉ vì nó có thể xác minh chữ ký. Nguồn tin cậy phải đến từ metadata hoặc cấu hình đã được quản lý phù hợp.

### 10.3. Authentication statement không phải quyền truy cập

Một statement cho biết người dùng đã xác thực theo ngữ cảnh được chấp nhận chưa đủ để cho phép xem lương hoặc cấp quyền quản trị. SP còn phải kiểm tra trạng thái tài khoản, tenant, vai trò, thuộc tính và chính sách trên hành động cụ thể.

Việc tự tạo tài khoản khi đăng nhập liên kết cũng là quyết định vòng đời danh tính riêng. Không tự cấp quyền rộng chỉ vì một assertion có chủ thể chưa từng xuất hiện trong cơ sở dữ liệu cục bộ.

## 11. Tình huống: SSO có sẵn nhưng thao tác cần xác thực mới

Lan xác thực tại IdP lúc 08:00. Lúc 08:25, Lan mở cổng quản trị và IdP phát hành một assertion dựa trên phiên SSO đang có. Authentication statement vẫn có thể ghi `AuthnInstant` là 08:00.

Cổng cho phép xem trang tổng quan nhưng quy định việc cấp đặc quyền phải dựa trên xác thực mới trong một khoảng thời gian ngắn do tổ chức lựa chọn, đồng thời cần ngữ cảnh xác thực đáp ứng yêu cầu bổ sung.

Khi Lan chọn cấp đặc quyền, ứng dụng không được kết luận rằng assertion phát hành lúc 08:25 có nghĩa Lan vừa xác thực lại. Nó cần đánh giá cả `AuthnInstant` và `AuthnContext`, rồi thực hiện luồng yêu cầu phù hợp nếu chưa đáp ứng.

Sau khi nhận assertion mới, ứng dụng xác minh toàn bộ thông điệp và kết quả thực tế. Nếu IdP không cung cấp được ngữ cảnh cần thiết hoặc thời điểm xác thực không đạt chính sách, hành động cấp đặc quyền phải bị từ chối hoặc chuyển sang quy trình xử lý được phê duyệt.

Tình huống này phân biệt ba câu hỏi độc lập: người dùng là ai, lần xác thực có đáp ứng yêu cầu hay không, và người dùng có quyền thực hiện hành động hay không.

## 12. Lỗi thường gặp và cách chẩn đoán

| Lỗi hoặc hiện tượng | Vấn đề | Hướng xử lý |
|---|---|---|
| Dùng `IssueInstant` làm thời điểm người dùng xác thực | Nhầm phát hành assertion với sự kiện xác thực | Đọc `AuthnInstant` từ statement đã xác minh |
| Coi mọi `AuthnContext` là MFA | Đánh giá sai mức xác thực | Ánh xạ giá trị theo thỏa thuận và chính sách thực tế |
| Bật `ForceAuthn` rồi bỏ kiểm tra kết quả | Yêu cầu gửi đi không phải bằng chứng đã đáp ứng | Đánh giá thời điểm và ngữ cảnh được trả về |
| Dùng `SessionIndex` như credential | Nhầm tham chiếu phiên với bằng chứng truy cập | Chỉ dùng trong đúng cơ chế quản lý phiên liên kết |
| Coi session SP và session IdP là một | Đăng xuất hoặc hết hạn không đạt kỳ vọng | Theo dõi riêng từng phiên và thiết kế phối hợp vòng đời |
| Bỏ qua audience hoặc recipient vì chữ ký đúng | Assertion có thể được dùng sai bên nhận | Xác minh đầy đủ theo hồ sơ SAML |
| Đọc statement không thuộc phần tử đã xác minh | Có nguy cơ tin dữ liệu XML bị thay thế | Dùng kết quả xác minh có ràng buộc cấu trúc rõ ràng |
| Nới dung sai thời gian để xử lý lỗi đồng hồ kéo dài | Mở rộng ngoài dự kiến cửa sổ chấp nhận | Sửa đồng bộ thời gian và giữ dung sai có giới hạn |
| Đăng nhập thành công nhưng cấp quyền sai | Trộn xác thực với ủy quyền nghiệp vụ | Kiểm tra tài khoản, tenant và RBAC/ABAC riêng |

Khi điều tra, nên ghi issuer, định danh tương quan, loại lỗi và dữ liệu thời gian cần thiết theo chính sách bảo vệ thông tin. Tránh lưu nguyên SAML response hoặc assertion vào log thông thường vì chúng có thể chứa dữ liệu cá nhân và bằng chứng đăng nhập nhạy cảm.

Authentication statement có giá trị khi SP hiểu đúng sự kiện xác thực được mô tả, xác minh đúng assertion chứa nó và áp dụng thông tin đó trong chính sách phiên cùng kiểm soát quyền truy cập của ứng dụng.
