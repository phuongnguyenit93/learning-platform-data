# Federation assurance: mức độ tin cậy trong xác thực liên kết

> **Chương:** Mức độ tin cậy  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** nghiên cứu xác thực từ credential, mật khẩu, MFA, passkey, chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách một ứng dụng đặt niềm tin vào kết quả xác thực do hệ thống danh tính khác cung cấp, cách định lượng rủi ro của **giao dịch liên kết danh tính** và những kiểm soát để tránh phishing, replay, chèn assertion hoặc lạm dụng phiên.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **identity federation**, vai trò của **Identity Provider (IdP)**, **Relying Party (RP)**, chủ thể đăng nhập và cơ sở thiết lập quan hệ tin cậy.
2. Phân biệt **Identity Assurance Level (IAL)**, **Authenticator Assurance Level (AAL)** và **Federation Assurance Level (FAL)**; hiểu vì sao chúng đánh giá những rủi ro khác nhau.
3. Mô tả assertion, subject identifier, session và luồng truyền kết quả xác thực qua OIDC hoặc SAML.
4. Phân tích kiểm soát chống giả mạo, thay thế, phát lại, chèn assertion, nhầm RP, nhầm issuer và liên kết sai tài khoản.
5. Hiểu ý nghĩa khái quát của FAL1/FAL2/FAL3 và cách lựa chọn yêu cầu assurance dựa trên giao dịch cụ thể, đồng thời không nhầm một cấu hình kỹ thuật với chứng nhận đạt một mức FAL.
6. Thiết kế và kiểm thử luồng xác thực liên kết có ranh giới tin cậy rõ ràng, kiểm tra authorization và quản lý vòng đời danh tính.

## 2. Federation là gì, và vì sao cần đánh giá assurance?

**Identity federation (liên kết danh tính)** là mô hình trong đó một ứng dụng (**RP**) nhận và sử dụng thông tin danh tính hoặc sự kiện xác thực từ một bên khác (**IdP**) dựa trên thỏa thuận và giao thức tin cậy. RP không nhất thiết trực tiếp kiểm tra mật khẩu, passkey hay MFA của người dùng; IdP thực hiện xác thực rồi cung cấp một **assertion** hoặc các thông điệp giao thức mà RP kiểm chứng.

Ví dụ: nhân viên An đăng nhập ứng dụng quản lý công việc bằng hệ thống danh tính của công ty. Ứng dụng quản lý công việc không nhận mật khẩu doanh nghiệp của An. Thay vào đó, ứng dụng chuyển An tới IdP, IdP kiểm tra phương thức đăng nhập, và ứng dụng xử lý kết quả trả về theo giao thức OIDC. Sau khi kiểm tra hợp lệ, ứng dụng có thể tạo phiên riêng cho An.

Mô hình này giảm nhu cầu phát hành mật khẩu riêng cho từng ứng dụng, nhưng làm xuất hiện **ranh giới tin cậy mới**:

- RP cần xác định **IdP nào được phép phát biểu về người dùng**.
- RP cần biết **thông điệp có thật sự do IdP đó phát hành, dành cho RP này và còn hiệu lực hay không**.
- RP cần liên hệ thông điệp nhận được với **yêu cầu đăng nhập do chính RP khởi tạo**, tránh nhận assertion được chèn từ một luồng khác.
- RP phải xác định **subject nào** tại IdP đang được ánh xạ vào **tài khoản nội bộ nào**.
- RP phải hiểu **mức độ xác thực** tại IdP có đáp ứng yêu cầu rủi ro hay không.
- RP vẫn phải kiểm tra **authorization** cho hành động và tài nguyên hiện tại.

**Federation assurance** đánh giá mức độ bảo đảm của chính việc truyền và sử dụng kết quả danh tính/xác thực **qua biên IdP → RP**. Một IdP có cơ chế xác thực mạnh vẫn có thể dẫn đến đăng nhập sai nếu RP chấp nhận assertion sai đối tượng nhận, không kiểm tra issuer hoặc ghép nhầm tài khoản.

## 3. Các thành phần và ranh giới tin cậy

| Thành phần | Vai trò | Câu hỏi bảo mật quan trọng |
|---|---|---|
| **Subscriber / người dùng** | Người hoặc thực thể có danh tính được IdP quản lý | Có kiểm soát đúng authenticator/credential không? |
| **Identity Provider (IdP)** | Xác thực người dùng và phát thông tin liên kết theo giao thức | IdP có đáng tin, sử dụng khóa và chính sách đúng không? |
| **Relying Party (RP)** | Ứng dụng nhận kết quả từ IdP, lập phiên và phục vụ người dùng | RP có xác thực thông điệp, ánh xạ tài khoản và kiểm tra quyền đúng không? |
| **Assertion** | Phát biểu về subject, có thể gồm thời điểm, phương thức hoặc ngữ cảnh xác thực | Assertion được bảo vệ chống giả mạo, thay thế, phát lại và sử dụng sai nơi nhận không? |
| **Federation protocol** | Quy ước chuyển hướng, trao đổi thông điệp và xác minh giữa các bên | Luồng có gắn với yêu cầu đúng và bảo vệ các điểm chuyển tiếp không? |
| **Federation trust agreement** | Thỏa thuận chính sách và kỹ thuật giữa IdP và RP | Ai chịu trách nhiệm kiểm tra gì, dữ liệu nào được tin và khi có sự cố sẽ thu hồi thế nào? |
| **Local account và session** | Tài khoản/phiên RP dùng sau khi chấp nhận assertion | Việc ánh xạ và quản lý phiên có tránh chiếm tài khoản, vượt quyền không? |
| **Policy enforcement** | Quyết định permit/deny cho thao tác và tài nguyên | Principal đã liên kết có được làm hành động này trong tenant này không? |

Trong **OpenID Connect (OIDC)**, RP thường được gọi là *client*, còn IdP tương ứng với *OpenID Provider (OP)*. Trong **SAML**, thuật ngữ thường là *Identity Provider* và *Service Provider (SP)*; SP có vai trò gần với RP. Hai giao thức có biểu diễn và trình tự khác nhau nhưng cùng cần kiểm soát quan hệ tin cậy.

**Phân biệt điều được xác nhận và điều được suy diễn:**

- IdP xác nhận “subject X đã trải qua một sự kiện xác thực theo điều kiện Y” trong phạm vi IdP và giao thức.
- RP kiểm tra “assertion này đến từ IdP tin cậy, dành cho mình và liên quan đúng giao dịch hiện tại”.
- RP mới ánh xạ “X tại IdP này tương ứng tài khoản nội bộ A”.
- RP sau đó đánh giá “A có quyền làm hành động Z với tài nguyên R không?”.

Không được gộp bốn quyết định này vào một điều kiện “token tồn tại”.

## 4. Ba trục IAL, AAL và FAL

Trong họ hướng dẫn danh tính số **NIST SP 800-63**, ba khía cạnh assurance thường được xem xét riêng:

| Trục | Đánh giá điều gì? | Ví dụ câu hỏi | Lỗi điển hình nếu thiếu |
|---|---|---|---|
| **IAL — Identity Assurance Level** | Mức bảo đảm của quy trình thẩm định/gắn danh tính với chủ thể | Đã thẩm định người này tương ứng hồ sơ danh tính ngoài đời ở mức nào? | Hệ thống xác thực đúng một tài khoản giả mạo danh tính thật |
| **AAL — Authenticator Assurance Level** | Mức bảo đảm rằng người đang đăng nhập kiểm soát authenticator của tài khoản | Đăng nhập bằng phương thức nào; chống phishing, replay và chiếm credential đến đâu? | Kẻ tấn công dùng mật khẩu bị lộ hoặc OTP bị phishing |
| **FAL — Federation Assurance Level** | Mức bảo đảm của giao dịch truyền kết quả xác thực/danh tính từ IdP sang RP | RP có chống giả mạo và sử dụng sai assertion, đúng người nhận và đúng giao dịch không? | Assertion bị chèn, phát lại, gửi nhầm RP hoặc bị ghép vào phiên khác |

### Ví dụ để không nhầm ba trục

Một nhân viên đã được công ty xác minh danh tính bằng quy trình nhân sự (IAL theo mức phù hợp), đăng nhập IdP bằng passkey chống phishing (AAL theo phương thức và cấu hình cụ thể), nhưng ứng dụng RP lại nhận bất kỳ ID token nào chưa kiểm tra **audience**. Lỗ hổng tại RP là **rủi ro federation** dù phương thức xác thực rất mạnh.

Ngược lại, nếu RP kiểm tra đầy đủ thông điệp liên kết nhưng IdP chỉ kiểm tra mật khẩu yếu đã bị đánh cắp, đường truyền federation có thể bảo đảm tốt nhưng **AAL hoặc chính sách xác thực không đạt yêu cầu của giao dịch**.

**IAL, AAL và FAL không cộng lại thành một “điểm tổng” đơn giản.** Một hệ thống cần chọn yêu cầu cho từng trục dựa trên loại người dùng, tác động khi lạm dụng, dữ liệu xử lý và tiêu chuẩn/ấn bản áp dụng.

### Authentication khác authorization

Ngay cả khi ba khía cạnh assurance đáp ứng chính sách, **authorization** vẫn là quyết định riêng: một tài khoản nhân viên hợp lệ có thể không được xem hồ sơ lương của đồng nghiệp, sửa quyền admin hoặc truy xuất tài liệu thuộc tenant khác.

## 5. Hiểu FAL1, FAL2, FAL3 ở mức nguyên tắc

Trong các ấn bản của NIST SP 800-63C, **FAL** được phân cấp nhằm mô tả sức mạnh bảo vệ khi RP dựa vào kết quả federation. Phân loại thực tế, các yêu cầu bắt buộc và cách kiểm chứng phải tuân theo **đúng ấn bản và hồ sơ giao thức được tổ chức áp dụng**; không thể tự suy ra FAL chỉ bằng việc thấy JWT có chữ ký, dùng TLS hoặc bật PKCE.

| Mức khái quát | Mục tiêu rủi ro | Hình dung về bảo vệ |
|---|---|---|
| **FAL1** | Bảo vệ giao dịch federation ở mức cơ sở | Assertion/token phải được RP kiểm tra đúng nguồn, đúng nơi nhận, hiệu lực và luồng sử dụng; các bảo vệ giao thức cần thiết vẫn bắt buộc |
| **FAL2** | Tăng bảo vệ trước việc lộ, thay thế hoặc chèn assertion theo yêu cầu của hồ sơ áp dụng | Bổ sung kiểm soát mạnh hơn cho cách assertion được truyền và gắn với giao dịch; có thể gồm bảo vệ bí mật thông điệp và chống assertion injection theo quy định ấn bản |
| **FAL3** | Bảo đảm rất cao rằng assertion không thể bị dùng thành công bởi bên không kiểm soát bằng chứng mật mã liên quan | Cơ chế ràng buộc mật mã và chứng minh quyền kiểm soát khóa/thiết bị của subscriber tại RP theo hồ sơ áp dụng; chú trọng chống kẻ đánh cắp hoặc chuyển tiếp assertion |

**Lưu ý về tính chuẩn tắc:** bảng trên giải thích định hướng rủi ro, **không** phải danh sách điều kiện kiểm định NIST. Những ấn bản và profile cụ thể có thể quy định khác nhau về encryption, assertion injection, proof-of-possession, khóa do subscriber kiểm soát, thành phần bắt buộc hoặc ngoại lệ. Khi lập hồ sơ tuân thủ, phải dẫn đúng tài liệu, phiên bản, điều khoản và bằng chứng triển khai; không gán nhãn “FAL2” hoặc “FAL3” chỉ vì có một tính năng đơn lẻ.

### Ba câu hỏi khi chọn mức FAL

1. **Hậu quả nếu RP nhận nhầm assertion là gì?** Đăng nhập trang tin nội bộ khác với phê duyệt chuyển tiền, truy cập dữ liệu sức khỏe hoặc quyền quản trị hệ thống.
2. **Mô hình tấn công thực tế là gì?** Kẻ tấn công có thể chiếm trình duyệt, lấy assertion, kiểm soát một client khác, thay redirect, sử dụng mạng không đáng tin hoặc giả mạo IdP hay không?
3. **RP thật sự xác minh được điều gì?** Có kiểm soát hợp lệ với issuer, audience, ràng buộc giao dịch, chống replay và phương pháp bảo vệ assertion ở cấp yêu cầu không?

Mức FAL cần được chọn **trước khi** gắn nhãn cho giao thức triển khai; các yêu cầu bảo đảm phải được kiểm tra từ thiết kế đến vận hành, không chỉ từ cấu hình ban đầu.

## 6. Assertion, token và bằng chứng cần hiểu đúng

Trong OIDC, **ID token** thường là JWT chứa thông tin về sự kiện xác thực và subject dành cho **RP/client**. Trong SAML, **SAML assertion** là tài liệu có cấu trúc cung cấp các phát biểu về subject và ngữ cảnh xác thực. Các assertion khác nhau về định dạng nhưng đều nhạy cảm với việc sử dụng sai ngữ cảnh.

| Trường/khái niệm | Ý nghĩa trong thực hành | Sai lầm cần tránh |
|---|---|---|
| **Issuer (iss)** | Bên phát hành và không gian định danh | Chấp nhận issuer bất kỳ hoặc tự ánh xạ một subject sang IdP khác |
| **Subject (sub) / NameID** | Định danh subject theo quy tắc IdP và profile | Dùng email, tên hiển thị hay sub đơn lẻ làm khóa chung của mọi IdP |
| **Audience (aud)** | Bên nhận được chỉ định cho thông điệp | Dùng ID token phát hành cho app A để đăng nhập app B |
| **Expiration / validity** | Khoảng thời gian có hiệu lực | Chấp nhận token/assertion quá hạn |
| **Nonce / request correlation** | Gắn phản hồi với giao dịch đăng nhập thích hợp theo profile | Chấp nhận phản hồi tự đến, bị chèn từ một phiên khác |
| **Signature / validation key** | Xác minh nguồn phát hành và tính toàn vẹn theo profile | Chỉ giải mã payload, tin khóa do token tự chỉ định mà chưa đối chiếu nguồn tin cậy |
| **Encryption / confidentiality** | Bảo vệ nội dung assertion nếu profile yêu cầu | Nghĩ rằng mã hóa thay cho kiểm tra chữ ký, issuer hoặc audience |
| **Authentication context** | Thông tin về cách/độ mới của xác thực tại IdP | Tự coi một chuỗi acr/amr bất kỳ là đáp ứng AAL mong muốn |
| **Binding / proof of possession** | Chứng minh bên sử dụng có quyền kiểm soát khóa liên quan khi profile đòi hỏi | Xem một bearer assertion như bằng chứng không thể bị dùng lại bởi người khác |

**Bearer assertion/token** là dạng mà bên sở hữu giá trị có thể sử dụng trong các điều kiện cho phép. Vì vậy, bị lộ có thể gây rủi ro nếu cơ chế chống replay, giới hạn thời gian, ràng buộc giao dịch hoặc kiểm soát khác không đủ.

**Proof-of-possession (PoP)** bổ sung yêu cầu chứng minh quyền kiểm soát khóa thay vì chỉ trình ra một chuỗi giá trị. Tuy nhiên, PoP trong một loại access token giữa client và API **không tự động chứng minh** luồng đăng nhập liên kết đã đạt FAL3; cần xét đúng chuẩn, vị trí kiểm tra và chủ thể kiểm soát khóa.

### ID token khác OAuth access token

- **ID token** được RP/client dùng để tiếp nhận phát biểu OIDC về kết quả xác thực và subject.
- **Access token** được một resource server/API kiểm tra để xử lý truy cập tài nguyên theo phạm vi ủy quyền và chính sách áp dụng.
- **Refresh token** phục vụ cấp lại token theo quy tắc cấp phát và vòng đời; không phải bằng chứng danh tính dành để đưa tới mọi API.

Không đưa ID token vào header Authorization của một API chỉ vì nó là JWT có chữ ký; API cần **access token** đúng issuer, audience, thời hạn, quyền và ràng buộc sử dụng.

## 7. OIDC Authorization Code Flow: ranh giới cần bảo vệ

Sơ đồ dưới đây mô tả luồng đăng nhập liên kết bằng **OIDC Authorization Code Flow với PKCE** ở mức khái niệm:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant RP as RP - Ứng dụng
    participant IdP as IdP - OpenID Provider
    participant Store as Liên kết danh tính
    participant Policy as Kiểm tra quyền

    User->>Browser: Chọn đăng nhập doanh nghiệp
    Browser->>RP: Bắt đầu login
    RP->>RP: Tạo state, nonce, PKCE và giao dịch tạm
    RP-->>Browser: Chuyển hướng tới đúng IdP
    Browser->>IdP: Authorization request gắn client và redirect URI
    IdP->>IdP: Xác thực người dùng và áp chính sách IdP
    IdP-->>Browser: Authorization response chứa code và state
    Browser->>RP: Callback code và state
    RP->>RP: Kiểm tra state, đúng request và redirect/correlation
    RP->>IdP: Đổi code qua token endpoint với PKCE và client authentication khi cần
    IdP-->>RP: ID token và các token theo giao thức
    RP->>RP: Verify token, issuer, audience, hạn, nonce, chính sách
    RP->>Store: Lookup (verified issuer, subject)
    Store-->>RP: Local account hợp lệ
    RP->>RP: Tạo phiên ứng dụng bảo vệ an toàn
    Browser->>RP: Yêu cầu hành động với phiên RP
    RP->>Policy: Principal, action, resource, tenant và context
    Policy-->>RP: Permit hoặc Deny
    RP-->>Browser: Kết quả theo quyền
~~~

Các bước có thể khác theo loại client và profile. Bảo vệ **state** giúp gắn phản hồi với yêu cầu đăng nhập và chống CSRF trong luồng; **nonce** gắn ID token với giao dịch theo quy định; **PKCE** ràng buộc bước đổi authorization code với bên khởi tạo phù hợp. Chúng bổ trợ nhau và không thay thế việc kiểm tra issuer, audience, chữ ký hoặc quản lý session.

Các hệ thống thực tế nên dựa trên thư viện OIDC có hỗ trợ chuẩn và cấu hình đúng, không tự ghép luồng redirect/token từ các chuỗi URL thủ công.

### Quy tắc quan trọng ở RP

1. **Chỉ tin IdP trong danh sách được chấp nhận** cho ứng dụng/tenant đó; lấy metadata và khóa xác minh từ nguồn đã xác lập quan hệ tin cậy.
2. **Dùng redirect URI đã đăng ký và so khớp nghiêm ngặt**; không cho phép một tham số bên ngoài tùy ý quyết định nơi nhận code/token.
3. **Gắn response với giao dịch do RP khởi tạo:** state, nonce, PKCE và các kiểm tra theo profile, đồng thời chống xử lý lại callback.
4. **Xác minh ID token đúng cấu hình:** thuật toán/chữ ký, issuer, audience, thời điểm hết hạn, nonce khi cần, các claim và kiểm tra bổ sung theo profile.
5. **Không cho token tự chọn khóa đáng tin:** tránh key confusion, algorithm confusion, tin URL khóa trong token từ nguồn không được phép hoặc chấp nhận chữ ký rỗng.
6. **Ánh xạ danh tính theo nguồn:** cặp (issuer, subject) là điểm khởi đầu đáng tin sau xác minh; cần quy trình liên kết tài khoản rõ ràng.
7. **Tạo phiên RP an toàn và độc lập về chính sách:** cookie phù hợp, chống fixation, timeout, CSRF khi dùng cookie, thu hồi khi cần.
8. **Kiểm tra authorization tại mọi hành động/tài nguyên:** token hợp lệ không phải quyền mặc định trên tất cả dữ liệu.

## 8. SAML và những điểm tương ứng

Với SAML, RP/SP cần kiểm tra theo profile và binding đang dùng. Ví dụ với Web Browser SSO, cần xem:

- Chữ ký trên đúng phần thông điệp/assertion được tin cậy; cấu hình kiểm chứng XML Signature an toàn để tránh **XML signature wrapping**.
- **Issuer** thuộc IdP được phép, chứng chỉ/khóa đúng tập đã cấu hình và xử lý thay đổi khóa theo quy trình.
- **AudienceRestriction**, **Recipient**, **Destination**, các điều kiện thời gian (**NotBefore / NotOnOrAfter**) và **SubjectConfirmationData** đúng nơi nhận và request.
- **InResponseTo** khớp yêu cầu đăng nhập trước đó trong SP-initiated flow, hoặc áp chính sách chặt riêng nếu cho phép IdP-initiated flow.
- Assertion ID/message ID không được chấp nhận lại ngoài quy tắc; thời gian sống ngắn và cache chống replay khi cần.
- Subject/NameID được ánh xạ vào đúng account và đúng tenant; không tự tin email/NameID không có namespace.

**Lưu ý:** không phải hệ thống SAML nào cũng dùng cùng binding và cùng mô hình request. Một lời gọi “SAML đã ký” không chứng minh các điều kiện trên đã được kiểm tra đầy đủ.

## 9. Authentication context: RP biết người dùng đã xác thực mạnh đến đâu?

RP có thể cần biết rằng IdP đã dùng một phương thức đủ mạnh, nhất là khi người dùng truy cập chức năng quản trị, thay authenticator hoặc phê duyệt giao dịch giá trị cao.

Trong OIDC, các claim thường gặp:

| Claim | Diễn giải khái quát | Giới hạn |
|---|---|---|
| **auth_time** | Thời điểm xảy ra sự kiện xác thực của người dùng | Không tự chứng minh phương thức xác thực mạnh; RP phải hiểu độ mới được chấp nhận |
| **acr** | Một giá trị chỉ lớp/ngữ cảnh xác thực theo hệ thống hoặc hợp đồng IdP | Chuỗi acr phải có **định nghĩa được hai bên thống nhất**; không suy từ tên gọi rằng đạt AAL cụ thể |
| **amr** | Thông tin về các phương thức được dùng trong xác thực | Danh sách phương thức không tự chứng minh hiệu lực chống phishing, triển khai hoặc đạt AAL |
| **max_age** (trong yêu cầu) | RP yêu cầu giới hạn tuổi của xác thực tại IdP | Cần kiểm tra kết quả được đáp ứng và quy tắc liên quan đến auth_time |
| **prompt / các điều kiện yêu cầu** | Gợi ý hoặc ràng buộc tương tác người dùng theo profile | Không nên coi việc yêu cầu một tham số đồng nghĩa IdP chắc chắn đáp ứng nếu không có bằng chứng phù hợp |

Ví dụ: RP yêu cầu bước xác thực gần đây trước khi thêm phương thức khôi phục tài khoản. RP có thể yêu cầu IdP xác thực lại và kiểm tra **auth_time** cùng chính sách đã thống nhất. Một lần đăng nhập SSO diễn ra nhiều giờ trước không nhất thiết đủ cho tác vụ nhạy cảm, dù session RP còn sống.

**Passkey/WebAuthn chống phishing là tính chất của phương thức và ngữ cảnh xác thực**, thuộc cách đánh giá AAL và các yêu cầu cụ thể; không tự chứng minh toàn bộ giao dịch IdP → RP đạt FAL cao. Ngược lại, federation an toàn không khắc phục được việc IdP chấp nhận credential bị phishing.

## 10. Các lỗi và kiểu tấn công đặc trưng của federation

| Tình huống | Cơ chế lỗi | Biện pháp trọng tâm |
|---|---|---|
| **Assertion/token substitution** | Thay assertion của người dùng/luồng khác vào callback hiện tại | Kiểm tra state, nonce, request correlation, audience, issuer và thời gian |
| **Assertion replay** | Tái sử dụng một thông điệp bị lộ | Thời hạn ngắn, ràng buộc giao dịch, cache chống replay và kiểm soát PoP theo profile |
| **Assertion injection / login CSRF** | Chèn kết quả xác thực hợp lệ nhưng từ giao dịch do kẻ khác khởi tạo | RP-initiated flow với correlation mạnh; hạn chế unsolicited assertions |
| **Mix-up giữa IdP** | RP xử lý phản hồi của IdP A như thể từ IdP B | Ràng buộc issuer đã chọn vào giao dịch, xác minh issuer ở response/token, sử dụng biện pháp mix-up defense của giao thức |
| **Audience confusion** | ID token của RP khác được sử dụng làm vé đăng nhập | Kiểm tra audience và các yêu cầu liên quan khi nhiều audience |
| **Redirect URI / open redirect abuse** | Code hoặc thông điệp bí mật chuyển tới nơi kẻ tấn công kiểm soát | Redirect URI đã đăng ký, so khớp đúng, giới hạn open redirect, PKCE và client authentication |
| **Token/key validation flaw** | Tin JWT chỉ vì parse được hoặc tin khóa từ nguồn tùy ý | Whitelist thuật toán phù hợp, khóa từ metadata tin cậy và kiểm chứng chữ ký/claims |
| **SAML XML signature wrapping** | Chữ ký hợp lệ trên phần khác với assertion được ứng dụng đọc | Thư viện SAML an toàn; xử lý đúng phần tử đã ký, schema/profile và reference |
| **Account linking takeover** | Tự ghép hai danh tính do trùng email | Dùng namespace issuer+subject và quy trình chứng minh kiểm soát trước khi liên kết |
| **Session fixation/hijack tại RP** | Assertion đúng nhưng phiên RP bị gán hoặc đánh cắp | Rotate session tại login, cookie an toàn, timeout, CSRF và bảo vệ thiết bị khi cần |
| **Quá tin acr/amr** | Xem chuỗi claim tùy ý là MFA chống phishing đạt chuẩn | Hợp đồng assurance rõ, kiểm tra claim được IdP tin cậy phát và kiểm toán phương thức |
| **Confused deputy qua service federation** | Service có quyền rộng dùng assertion người dùng vào sai ngữ cảnh | Phân biệt actor/service principal/delegation và giới hạn quyền theo audience, tài nguyên |

### Vì sao chữ ký số chưa đủ?

Một ID token có chữ ký hợp lệ của IdP nhưng được phát cho ứng dụng B. Nếu ứng dụng A bỏ qua audience, A có thể chấp nhận sai token. Chữ ký chỉ chứng minh tính toàn vẹn và nguồn phát hành **theo khóa đang tin**, không chứng minh token dành cho A hay gắn với đúng yêu cầu A đã khởi tạo.

Tương tự, ID token có issuer và audience đúng vẫn cần quy trình đúng để liên hệ với một login transaction cụ thể; bỏ qua state/nonce và các điều kiện của luồng có thể dẫn đến sự nhầm lẫn phiên hoặc chèn assertion.

## 11. Liên kết danh tính và chủ thể tại RP

Một hệ thống có nhiều IdP nên xem danh tính bên ngoài là một giá trị được định danh bởi ít nhất:

~~~text
external_identity = (verified_issuer, verified_subject)
local_account     = linkTable.lookup(external_identity)
~~~

Hai issuer có thể cấp **cùng giá trị subject** cho hai chủ thể khác nhau. Trong OIDC, subject cũng có thể là **pairwise identifier** khác nhau theo sector để giảm khả năng liên kết chéo ứng dụng.

Ví dụ:

| Issuer đã kiểm chứng | Subject | Tài khoản nội bộ | Quy tắc |
|---|---|---|---|
| https://id.company.example | emp-028 | A-100 | Liên kết theo quy trình doanh nghiệp |
| https://login.partner.example | emp-028 | B-204 | **Không** tự nhập vào A-100 dù subject trùng |
| https://login.partner.example | contractor-77 | A-100 | Chỉ hợp lệ nếu người dùng đã chứng minh quyền kiểm soát hai danh tính và chính sách cho phép |

Email, số điện thoại hoặc tên hiển thị có thể thay đổi, tái sử dụng hoặc chưa được kiểm chứng. Một claim **email_verified** trong ngữ cảnh IdP không tự chứng minh tài khoản ở hai issuer là cùng một người. Liên kết tài khoản, khôi phục và thay IdP cần kiểm chứng danh tính/chủ thể theo mức rủi ro.

### Vòng đời phải được tính đến

- **Cấp tài khoản và onboarding:** ai được tạo account RP mới, ai được tự liên kết IdP, ai được mời vào tenant?
- **Khi IdP vô hiệu hóa tài khoản:** RP biết bằng cách nào? Session RP đã tồn tại có tiếp tục hay cần bị thu hồi?
- **Khi người dùng bị gỡ quyền:** role, tenant membership và quyền ở RP được làm mới ra sao?
- **Khi thay khóa IdP:** RP tải metadata/JWKS theo nguồn tin cậy và cập nhật khóa có kiểm soát thế nào?
- **Khi IdP gặp sự cố:** RP có đường khôi phục đủ an toàn mà không tạo tài khoản song song hoặc cho phép bypass MFA?
- **Khi người dùng yêu cầu logout:** logout ở IdP có tự động kết thúc session RP không? Không nên mặc định có; cần thiết kế front-channel/back-channel logout hoặc cơ chế tương ứng nếu yêu cầu.

Federation là một **quan hệ tin cậy đang vận hành**, không chỉ một redirect được cài đặt một lần.

## 12. Triển khai minh họa: ứng dụng Java dùng OIDC

Với Spring Security, RP nên sử dụng thành phần OIDC client có sẵn, thiết lập issuer/registration tin cậy và để framework xác minh luồng. Cấu hình minh họa dưới đây chỉ cho phép các tuyến đăng nhập công khai, còn ứng dụng cần principal đã xác thực để truy cập dữ liệu:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(routes -> routes
            .requestMatchers("/login/**", "/oauth2/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

Để ví dụ chạy đúng, ứng dụng cần dependency OAuth2 Client, registration và issuer URI, redirect URI được đăng ký đúng tại IdP, quản lý secret an toàn và cấu hình session/CSRF/cookie phù hợp. Các chi tiết PKCE, nonce, state và token validation phải tuân theo luồng/profile thực tế; không dùng đoạn cấu hình ngắn làm bằng chứng hệ thống đã đạt một FAL cụ thể.

Sau khi framework đã xác minh đăng nhập, có thể lấy danh tính đã xác thực và ánh xạ vào tài khoản nội bộ:

~~~java
@GetMapping("/api/me")
AccountProfile me(@AuthenticationPrincipal OidcUser principal) {
    String issuer = principal.getIdToken().getIssuer().toString();
    String subject = principal.getSubject();

    // Tra theo (issuer, subject), không dựa vào email tự khai.
    Account account = accounts.findByExternalIdentity(issuer, subject)
        .orElseThrow(() ->
            new AccessDeniedException("No linked account"));

    // Kiểm tra account còn hoạt động và được phép vào tenant.
    if (!account.isActive()) {
        throw new AccessDeniedException("Account disabled");
    }
    return AccountProfile.from(account);
}
~~~

**Đây là mã minh họa:** các kiểu Account, AccountProfile, repository và exception handling do ứng dụng định nghĩa. Không lấy trực tiếp issuer/subject từ request body hoặc header do client gửi. Một lớp authorization khác vẫn phải kiểm tra quyền truy cập đối tượng, đặc biệt khi ứng dụng nhiều tenant hoặc có quyền quản trị.

### Pseudocode kiểm tra ngữ cảnh assurance

~~~text
verifiedLogin = protocolAdapter.verify(callback, pendingLogin)
assert verifiedLogin.issuer in configuredTrustedIssuers
account = identityLink.lookup(verifiedLogin.issuer,
                              verifiedLogin.subject)
require account.active

if action.requiresRecentStrongAuthentication:
    require trustedAssuranceContract.isSatisfied(
        verifiedLogin.authenticationContext,
        policy.requiredFreshness,
        policy.requiredAuthenticationStrength)

authorize(account, action, resource, activeTenant)
~~~

Đối tượng **verifiedLogin** chỉ được tạo sau khi adapter thực hiện đầy đủ kiểm tra bắt buộc của protocol/profile, và **trustedAssuranceContract** chỉ có ý nghĩa khi RP và IdP thống nhất chính xác ngữ nghĩa các claim. Không coi tên claim hay string acr đơn lẻ là chứng nhận assurance.

## 13. Lựa chọn federation assurance theo nghiệp vụ

Hãy bắt đầu bằng **tác động khi giao dịch federation bị giả mạo hoặc bị lạm dụng**, rồi xác định các yêu cầu xác thực và quyền tách biệt.

| Kịch bản | Mức rủi ro minh họa | Cần quan tâm thêm ngoài luồng federation |
|---|---|---|
| SSO vào kho tài liệu học tập thông thường | Thấp đến vừa tùy dữ liệu | Quản lý session, phân quyền tài liệu, chống lộ token và rủi ro phishing |
| Đăng nhập quản trị tenant | Cao | AAL phù hợp, xác thực lại, giới hạn tenant, log và chính sách thu hồi |
| Xem dữ liệu nhân sự/tài chính | Cao | IAL theo yêu cầu định danh, dữ liệu nhạy cảm, phân quyền theo vai trò/đối tượng |
| Phê duyệt giao dịch giá trị lớn | Rất cao | Bằng chứng xác thực mạnh/gần đây, ràng buộc giao dịch, kiểm soát phê duyệt nghiệp vụ |
| Liên kết IdP mới với tài khoản hiện có | Cao | Chứng minh quyền kiểm soát cả hai danh tính, chống account takeover, thông báo thay đổi |
| Onboarding nhà thầu từ IdP đối tác | Vừa đến cao | Kiểm tra issuer và tenant, giới hạn vòng đời tài khoản, quyền tối thiểu, thu hồi tự động |

**Không gán FAL từ bảng rủi ro này:** cùng một nghiệp vụ có thể có yêu cầu pháp lý, tổ chức và mô hình đe dọa khác nhau. Quy trình đúng là xác định kết quả assurance cần đạt, chọn **ấn bản chuẩn/profile** đang áp dụng, rồi kiểm tra khả năng của IdP, RP và hợp đồng vận hành.

Một checklist lựa chọn hữu ích:

1. RP tin những IdP nào và điều kiện để gia nhập/bị loại khỏi danh sách?
2. RP yêu cầu IAL và AAL nào cho loại tài khoản hoặc thao tác này?
3. Quy trình federation có bảo vệ phù hợp trước assertion injection, replay, mix-up và token theft không?
4. Nếu muốn mức FAL cao, cơ chế ràng buộc assertion/khóa và phần cứng có thực sự được **bên cần thiết kiểm chứng** theo chuẩn áp dụng không?
5. Ai vận hành khóa, metadata, chứng chỉ và phát hiện sự cố giữa IdP/RP?
6. Tài khoản RP, session, tenant membership và quyền xử lý thay đổi hoặc thu hồi ra sao?
7. Có hồ sơ thiết kế, bằng chứng cấu hình, kiểm thử và giám sát đủ để xác nhận mức đã tuyên bố không?

## 14. Các tình huống để phân tích

### Tình huống A: SSO với passkey nhưng RP bỏ qua audience

Nhân viên An xác thực bằng passkey chống phishing tại IdP. Một ID token được phát cho ứng dụng A, nhưng ứng dụng B chấp nhận token đó vì chữ ký hợp lệ và issuer đúng.

**Phân tích:** điểm yếu ở **federation token validation**; B phải kiểm tra audience dành cho B, mục đích sử dụng, tính hợp lệ và toàn bộ bảo vệ luồng. AAL của An tại IdP không xóa lỗi này.

### Tình huống B: cùng email, khác issuer

Nhà thầu dùng IdP đối tác và có email trùng với hồ sơ nhân viên cũ trong RP. RP tự ghép hai account, cấp quyền của nhân viên cũ cho nhà thầu.

**Phân tích:** lỗi **identity linking/provisioning**. RP cần dùng issuer + subject được xác minh và quy trình liên kết có kiểm chứng; không coi email là một khóa toàn cục đáng tin.

### Tình huống C: chuyển phiên từ IdP sang RP

An đăng nhập IdP từ sáng, sau đó đăng nhập RP vào chiều cùng ngày bằng phiên SSO còn hiệu lực. An yêu cầu thêm phương thức khôi phục tài khoản.

**Phân tích:** RP phải áp chính sách về **độ mới và mức mạnh của xác thực**. Có thể yêu cầu xác thực lại hoặc step-up rồi kiểm tra kết quả phù hợp; việc assertion hợp lệ không mặc nhiên có nghĩa vừa xác thực lại bằng MFA.

### Tình huống D: IdP thu hồi người dùng, RP còn phiên

Doanh nghiệp khóa tài khoản của An ở IdP, nhưng phiên của An tại một RP còn hiệu lực vài giờ.

**Phân tích:** cần thiết kế vòng đời session và tín hiệu thu hồi/đồng bộ trạng thái giữa các hệ thống. Chỉ có giao thức đăng nhập ban đầu không bảo đảm mọi RP tự động đăng xuất tức thời.

### Tình huống E: chèn assertion hợp lệ của người khác

Kẻ tấn công khởi tạo đăng nhập bằng chính tài khoản của họ, rồi tìm cách đưa kết quả callback đến trình duyệt của nạn nhân. RP bỏ kiểm tra state và ngữ cảnh giao dịch.

**Phân tích:** đây là kiểu **login CSRF/assertion injection**; nếu thành công, nạn nhân có thể dùng ứng dụng trong session gắn với tài khoản kẻ tấn công, gây rò rỉ dữ liệu do nạn nhân nhập hoặc gây nhầm attribution. RP phải gắn kết quả với đúng giao dịch đăng nhập, xử lý callback an toàn và chống sử dụng lại thông điệp.

## 15. Ma trận kiểm thử federation assurance

| Kiểm thử | Kỳ vọng |
|---|---|
| Token hợp lệ nhưng **issuer** không thuộc IdP được tin cậy | Từ chối |
| Token ký đúng nhưng **audience** là RP khác | Từ chối |
| Token hết hạn hoặc chưa có hiệu lực | Từ chối theo quy tắc thời gian |
| Callback state sai, mất state hoặc không có login transaction đang chờ | Không lập phiên đăng nhập |
| Nonce trong ID token không khớp yêu cầu đã tạo khi profile áp dụng | Từ chối |
| Authorization code bị dùng lại hoặc đổi bởi bên không có PKCE verifier | Không nhận kết quả đăng nhập trái phép |
| Token tự chỉ định khóa/thuật toán không thuộc cấu hình tin cậy | Từ chối |
| Hai IdP có cùng subject string | Không tự ghép thành một tài khoản |
| Email trùng ở hai IdP hoặc đã thay đổi | Không tự động account linking |
| Assertion SAML có audience, recipient, destination hoặc InResponseTo sai | Từ chối theo binding/profile |
| SAML assertion bị copy/phát lại trong điều kiện không hợp lệ | Không lập thêm phiên trái phép |
| IdP trả acr/amr không đáp ứng hợp đồng assurance của thao tác | Yêu cầu step-up hoặc từ chối thao tác nhạy cảm |
| ID token hợp lệ nhưng account RP đã bị vô hiệu hóa | Không cấp quyền truy cập |
| Người dùng ở tenant T1 gọi tài nguyên T2 | Kiểm tra AuthZ từ chối dù SSO hợp lệ |
| Logout hoặc thu hồi tại IdP | Hành vi phiên RP đúng chính sách/khả năng tích hợp đã thiết kế |
| Đổi khóa ký IdP đúng quy trình | RP tiếp tục xác minh khóa mới từ nguồn tin cậy, không tự chấp nhận khóa lạ |

Nên kiểm thử bằng **identity provider giả lập và token/assertion thử nghiệm** trong môi trường kiểm thử để tạo các tình huống issuer, audience, nonce, thời gian và chữ ký. Tránh thử nghiệm bằng cách thu thập hoặc phát lại token thật của người dùng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một IdP yêu cầu passkey chống phishing. Tại sao RP vẫn cần kiểm tra FAL?

*Trả lời:* Passkey liên quan đến bảo đảm xác thực tại IdP (AAL). FAL liên quan đến việc truyền và chấp nhận kết quả ở RP. Nếu RP bỏ kiểm tra issuer, audience, transaction binding hoặc assertion validity, một kết quả xác thực mạnh vẫn có thể bị sử dụng sai.

**Câu 2.** Có thể khẳng định “dùng OIDC Authorization Code + PKCE là FAL2” không?

*Trả lời:* Không. Đó là những thành phần thiết kế có ích, nhưng mức FAL cần đáp ứng toàn bộ yêu cầu của ấn bản tiêu chuẩn/profile đang áp dụng và có bằng chứng triển khai phù hợp.

**Câu 3.** Hai IdP phát cùng giá trị subject; RP có được coi là cùng người dùng không?

*Trả lời:* Không. Danh tính ngoài thường cần namespace (issuer, subject). Liên kết hai identity với cùng account nội bộ đòi hỏi chính sách và bước xác minh riêng.

**Câu 4.** ID token có chữ ký đúng và audience đúng. RP có thể bỏ qua state/nonce không?

*Trả lời:* Không tự động. RP vẫn phải kiểm tra các điều kiện chống CSRF, injection, mix-up và gắn phản hồi với giao dịch ban đầu theo giao thức/profile. Chữ ký và audience không thay thế correlation.

**Câu 5.** Federation assurance có quyết định quyền đọc một hóa đơn hay không?

*Trả lời:* Không. Federation bảo đảm RP nhận đúng kết quả danh tính/xác thực; quyền đọc hóa đơn do authorization quyết định dựa vào account, hành động, đối tượng, tenant và chính sách nghiệp vụ.

## 17. Ghi nhớ trọng tâm

- **Federation assurance bảo vệ ranh giới IdP → RP:** RP chỉ nên tin assertion khi đúng nguồn, đúng người nhận, đúng giao dịch và đáp ứng các điều kiện giao thức/pháp lý áp dụng.
- **IAL, AAL và FAL là những trục assurance khác nhau.** Xác thực mạnh ở IdP không sửa được lỗi nhận assertion tại RP; federation an toàn không tự chứng minh danh tính ngoài đời hoặc cấp quyền dữ liệu.
- **FAL1/FAL2/FAL3 cần được hiểu và đánh giá theo ấn bản chuẩn/profile cụ thể.** Không tự gán một mức FAL chỉ từ việc dùng JWT, TLS, encryption, PKCE hoặc chữ ký số.
- **OIDC và SAML đều cần kiểm soát thông điệp và giao dịch:** issuer, audience, hiệu lực, signature/khóa, chống replay, correlation và mapping subject.
- **Danh tính ngoài được ánh xạ theo issuer và subject đã xác minh**, không tự liên kết tài khoản chỉ bằng email, tên hiển thị hoặc giá trị subject không có nguồn.
- **Phiên RP, vòng đời tài khoản và authorization vẫn cần quản lý riêng**: đăng nhập thành công không bảo đảm quyền, đồng bộ thu hồi tức thời hay mức xác thực đủ mới cho mọi thao tác.
- **Thiết kế theo mô hình đe dọa và bằng chứng kiểm thử**, nhất là với login CSRF, assertion injection, mix-up, token theft, cross-tenant access và khôi phục tài khoản.

Nắm chắc federation assurance giúp hệ thống khai thác lợi ích của SSO mà vẫn kiểm soát được sự tin cậy giữa các tổ chức và dịch vụ: ai xác thực, ai phát biểu về danh tính, ai xác minh phát biểu, và ai chịu trách nhiệm quyết định quyền khi yêu cầu đã vào ứng dụng.
