# Thời điểm truy cập

## 1. Thời điểm truy cập trong authentication context là gì?

Trong hệ thống xác thực, **thời điểm truy cập** cần được hiểu chính xác theo sự kiện mà hệ thống muốn đo: thời điểm người dùng thực sự hoàn tất xác thực, thời điểm session được tạo, thời điểm token được phát hành hay lần cuối người dùng hoạt động. Các mốc này liên quan nhưng không thể thay thế cho nhau.

Một session còn hiệu lực không có nghĩa người dùng vừa xác thực. Một access token mới được refresh cũng không có nghĩa người dùng vừa nhập password hoặc hoàn tất MFA. Nếu hệ thống dùng thời điểm sai để quyết định một hành động nhạy cảm, kẻ tấn công có thể lợi dụng session cũ hoặc token mới để vượt qua yêu cầu xác thực gần đây.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, thời điểm xác thực là thành phần quan trọng của authentication context cùng với principal, phương thức xác thực, mức assurance, authenticator, issuer và session. Ứng dụng cần biết người dùng đã xác thực khi nào, bằng phương thức nào, mức bảo đảm nào và bằng chứng đó còn đủ mới cho hành động hiện tại hay không.

Sau bài học, người học có thể:

- Phân biệt authentication time, token issue time, session creation time và last activity.
- Hiểu các claim thời gian trong OIDC/JWT như auth_time, iat, exp và nbf.
- Áp dụng max_age, prompt=login và yêu cầu xác thực lại.
- Thiết kế step-up authentication cho hành động nhạy cảm.
- Đánh giá độ mới của MFA và mức assurance, không chỉ thời gian.
- Quản lý session age, idle timeout, absolute timeout và refresh token.
- Xử lý clock skew, federation, account recovery và các tình huống session cũ.
- Kiểm thử chính sách xác thực gần đây và ràng buộc giao dịch.

## 2. Những mốc thời gian không được đánh đồng

Một ứng dụng có thể quan sát nhiều mốc thời gian khác nhau trong cùng một phiên:

| Mốc | Ý nghĩa | Không chứng minh điều gì |
| --- | --- | --- |
| **Authentication time** | Thời điểm người dùng hoàn tất một lần xác thực theo ngữ cảnh được ghi nhận | Không tự nói người dùng còn đang hoạt động hoặc đã dùng MFA nếu không có context tương ứng |
| **Token issued-at (iat)** | Thời điểm token được phát hành | Không chứng minh người dùng vừa xác thực; token có thể được cấp từ refresh token |
| **Token expiry (exp)** | Thời điểm token hết hiệu lực | Không phải thời điểm người dùng xác thực |
| **Not-before (nbf)** | Thời điểm token bắt đầu được chấp nhận | Không phản ánh thời điểm đăng nhập |
| **Session created-at** | Thời điểm session ứng dụng hoặc IdP được tạo | Có thể khác authentication time nếu session được khởi tạo từ một SSO session cũ |
| **Last activity** | Thời điểm ứng dụng ghi nhận hoạt động gần nhất | Hoạt động có thể chỉ là request nền, không phải xác thực |
| **MFA verified-at** | Thời điểm một yếu tố hoặc bước xác minh bổ sung được hoàn tất | Không nhất thiết bằng thời điểm password hoặc primary authentication |
| **Credential enrolled-at** | Thời điểm credential được đăng ký | Không chứng minh credential đã được dùng trong lần đăng nhập hiện tại |

Ví dụ: người dùng đăng nhập bằng passkey lúc 09:00. Ứng dụng tạo session lúc 09:00 và access token lúc 09:01. Token được refresh lúc 13:00, người dùng thực hiện một request lúc 14:00. Nếu không có lần xác thực mới, authentication time vẫn là 09:00 dù token iat là 13:00 và last activity là 14:00.

### 2.1. Authentication time

Authentication time là thời điểm xác thực được thực hiện theo authentication event mà issuer hoặc ứng dụng tin cậy ghi nhận. Với OIDC, claim auth_time trong ID token biểu diễn thời điểm end-user authentication occurred, dưới dạng NumericDate.

Nếu người dùng đã có SSO session tại IdP, lần truy cập một ứng dụng mới có thể không yêu cầu nhập credential lại. IdP có thể phát hành kết quả xác thực dựa trên lần xác thực trước đó. Khi đó, thời điểm đăng nhập vào ứng dụng và thời điểm người dùng thực sự xác thực tại IdP có thể khác nhau.

Ứng dụng cần dùng authentication time từ issuer đáng tin cậy và theo đúng ý nghĩa của giao thức. Không lấy thời gian do browser hoặc client tự gửi làm bằng chứng xác thực.

### 2.2. Token issue time

Claim iat thường cho biết token được phát hành lúc nào. Đây là mốc phục vụ kiểm tra tuổi token, phát hiện token có thời gian bất thường và áp dụng policy token.

Refresh token có thể được dùng để xin access token mới mà không yêu cầu người dùng xác thực lại. Vì vậy, iat mới chỉ chứng minh token mới được tạo; không chứng minh password, passkey hay MFA vừa được thực hiện.

### 2.3. Last activity

Last activity thường do ứng dụng tự ghi nhận khi nhận request hoặc hoạt động được chọn. Một trang web có thể gửi heartbeat định kỳ, làm last activity mới hơn dù người dùng không tương tác thực sự. Nếu dùng heartbeat để kéo dài session vô hạn, attacker có thể giữ session bị đánh cắp hoạt động lâu dài.

Nên định nghĩa rõ hoạt động nào được xem là activity có ý nghĩa, cách cập nhật và giới hạn tối đa của session. Last activity có thể phục vụ idle timeout, nhưng không thay thế authentication freshness.

## 3. Authentication freshness: xác thực còn mới đến mức nào?

**Authentication freshness** là mức độ gần đây của một lần xác thực so với thời điểm hệ thống cần ra quyết định. Một policy có thể yêu cầu người dùng đã xác thực trong vòng một khoảng thời gian nhất định trước khi xem dữ liệu hoặc thực hiện thao tác nhạy cảm.

Có thể mô hình hóa:

~~~text
authentication_age = current_server_time - authentication_time
fresh = authentication_age <= allowed_max_age
~~~

Công thức chỉ là mô hình khái niệm. Triển khai phải xử lý đơn vị thời gian, clock skew, timestamp trong tương lai, dữ liệu thiếu và issuer trust.

Ví dụ:

- Xem trang hồ sơ thông thường có thể chấp nhận session đã xác thực trước đó nếu vẫn còn hiệu lực.
- Đổi email hoặc số điện thoại recovery có thể yêu cầu xác thực lại gần đây.
- Thêm passkey mới có thể yêu cầu step-up bằng credential hiện có.
- Phê duyệt giao dịch giá trị cao có thể yêu cầu xác thực mạnh và ràng buộc với giao dịch.
- Thay đổi phương thức MFA hoặc tắt MFA cần yêu cầu xác thực mạnh hơn hành động xem thông tin thông thường.

Không có một ngưỡng freshness phù hợp cho mọi hành động. Khoảng thời gian phải dựa trên rủi ro, giá trị tài khoản, khả năng chiếm session và hậu quả nếu hành động bị thực hiện trái phép.

### 3.1. Freshness không đồng nghĩa assurance

Một lần xác thực vừa xảy ra có thể dùng phương thức yếu. Một lần xác thực mạnh có thể đã xảy ra từ lâu. Vì vậy, policy cần xem ít nhất hai chiều:

1. **Freshness:** lần xác thực xảy ra cách đây bao lâu?
2. **Assurance/context:** lần xác thực dùng phương thức nào, có MFA hay không, có user verification hay không và mức assurance được issuer khẳng định là gì?

Ví dụ, người dùng vừa xác thực bằng password đơn yếu có thể chưa đáp ứng policy phê duyệt chuyển tiền. Ngược lại, một lần MFA mạnh từ nhiều giờ trước có thể không còn đủ mới cho thao tác thay đổi thông tin recovery.

### 3.2. Không suy ra freshness từ request activity

Một request vừa đến server không làm authentication time tự đổi mới. Nếu session được tạo từ SSO cũ, các request liên tiếp chỉ cho thấy session đang được sử dụng. Muốn làm mới authentication time, cần một authentication event thực sự và bằng chứng tin cậy về event đó.

## 4. OIDC: auth_time, max_age và prompt

OpenID Connect cung cấp cơ chế để client yêu cầu xác thực gần đây và kiểm tra thời điểm xác thực.

### 4.1. Claim auth_time

Khi ID token chứa auth_time, giá trị này cho biết thời điểm end-user authentication occurred theo OpenID Provider. Giá trị là NumericDate, thường biểu diễn số giây kể từ Unix epoch.

Ví dụ ID token giản lược:

~~~json
{
  "iss": "https://id.example.test",
  "sub": "user-4821",
  "aud": "portal-web",
  "iat": 1795323000,
  "exp": 1795326600,
  "auth_time": 1795321200,
  "acr": "urn:example:loa:2"
}
~~~

Các giá trị trên chỉ minh họa cấu trúc. Client phải xác minh chữ ký, issuer, audience, expiry, nonce và các điều kiện OIDC khác trước khi tin claims. Không đọc payload JWT rồi coi đó là dữ liệu đã được xác thực.

### 4.2. Tham số max_age

Client có thể gửi max_age trong authorization request để yêu cầu OP bảo đảm thời điểm xác thực của người dùng không cũ hơn khoảng thời gian chỉ định. Nếu authentication time cũ hơn giới hạn hoặc OP không thể đáp ứng, OP cần tương tác lại với người dùng theo quy tắc OIDC.

Ví dụ request khái niệm:

~~~http
GET /authorize?
  response_type=code&
  client_id=portal-web&
  redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback&
  scope=openid%20profile&
  max_age=300&
  state=random-state&
  nonce=random-nonce&
  code_challenge=pkce-challenge&
  code_challenge_method=S256
~~~

max_age=300 yêu cầu lần xác thực gần đây trong giới hạn 300 giây. Đây là ví dụ minh họa; client phải xử lý response và claims theo OIDC, đồng thời áp dụng policy riêng cho hành động.

Khi max_age được yêu cầu, client cần kiểm tra auth_time trong ID token theo OIDC. Nếu thiếu claim bắt buộc hoặc giá trị không đáp ứng freshness policy, không được âm thầm coi session cũ là mới.

### 4.3. prompt=login

Giá trị prompt=login yêu cầu OP hiển thị trải nghiệm xác thực cho người dùng, thay vì chỉ dựa vào việc người dùng đã có session SSO mà không tương tác. Tuy nhiên, prompt=login không tự đảm bảo một phương thức cụ thể hoặc mức assurance cụ thể.

Nếu policy yêu cầu MFA, passkey hoặc mức ACR cụ thể, client cần yêu cầu và xác minh context tương ứng. Việc người dùng nhập lại password cũng không tự chứng minh đã hoàn tất MFA.

### 4.4. max_age và prompt=login khác nhau

| Cơ chế | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| **max_age** | Giới hạn tuổi tối đa của lần xác thực được chấp nhận | Cần xác thực còn mới theo thời gian |
| **prompt=login** | Yêu cầu OP tương tác lại để xác thực | Cần buộc người dùng đi qua bước đăng nhập |
| **acr_values / ACR request** | Yêu cầu context hoặc mức assurance cụ thể theo profile OP hỗ trợ | Cần phương thức/mức xác thực cụ thể |
| **nonce** | Ràng buộc ID token với authentication request | Bảo vệ transaction OIDC, chống token bị gắn nhầm hoặc replay |

max_age=0 tương đương yêu cầu prompt=login theo OIDC. Với max_age lớn hơn 0, OP có thể sử dụng session nếu lần xác thực trước đủ mới theo yêu cầu. Client vẫn phải kiểm tra auth_time và context.

## 5. ACR, AMR và độ mới của MFA

Thời điểm xác thực chỉ trả lời câu hỏi “khi nào”. Để biết “xác thực bằng cách nào” và “mức nào”, hệ thống có thể sử dụng authentication context.

- **ACR (Authentication Context Class Reference):** biểu thị lớp/ngữ cảnh xác thực mà OP khẳng định đã đáp ứng.
- **AMR (Authentication Methods References):** mô tả các phương thức xác thực được dùng, nếu issuer phát hành claim này.
- **auth_time:** thời điểm xác thực.
- **acr_values:** tham số client có thể dùng để yêu cầu một hoặc nhiều context theo khả năng OP.

Giá trị ACR và AMR cần được diễn giải theo hợp đồng với issuer. Không có một chuỗi ACR tùy ý nào tự mang ý nghĩa phổ quát cho mọi nhà cung cấp. Tổ chức cần định nghĩa mapping rõ ràng, ví dụ mức nào đáp ứng password-only, MFA, phishing-resistant MFA hoặc user verification theo policy.

### 5.1. MFA vừa hoàn tất hay chỉ có trong lịch sử?

Một user có thể có session được tạo sau khi MFA từ lâu. Nếu ứng dụng chỉ thấy cờ “MFA enabled” trong hồ sơ, điều đó không chứng minh MFA đã được thực hiện trong lần xác thực gần nhất.

Cần phân biệt:

- Người dùng đã đăng ký MFA.
- Tài khoản bắt buộc dùng MFA.
- MFA đã được thực hiện trong authentication event cụ thể.
- MFA được thực hiện gần đây trong khoảng thời gian policy yêu cầu.
- MFA đạt mức chống phishing hoặc loại authenticator được yêu cầu.

Nếu một thao tác yêu cầu MFA mới, cần có authentication context hoặc event đáng tin cậy thể hiện MFA đã được thực hiện và thời điểm tương ứng. Không tự đặt claim mfa=true ở client rồi gửi lên backend.

### 5.2. Step-up authentication

Step-up là yêu cầu người dùng bổ sung hoặc thực hiện lại xác thực khi hành động hiện tại có rủi ro cao hơn mức session hiện tại đáp ứng.

Ví dụ:

1. Người dùng đang có session đăng nhập thông thường.
2. Người dùng chọn thêm phương thức recovery hoặc chuyển tiền.
3. Server đánh giá auth_time, ACR/AMR và policy.
4. Nếu context quá cũ hoặc assurance chưa đủ, server yêu cầu step-up.
5. IdP thực hiện xác thực bổ sung.
6. Client nhận kết quả và server xác minh context mới.
7. Server ràng buộc kết quả step-up với hành động đang chờ rồi mới cho phép tiếp tục.

Step-up không nên chỉ là một màn hình nhập lại password không có ràng buộc. Cần biết yếu tố nào được dùng, transaction nào được xác nhận và kết quả có thể được tái sử dụng cho hành động khác hay không.

## 6. Reauthentication và session renewal

**Reauthentication** là thực hiện lại một authentication event để xác minh người dùng hiện đang kiểm soát credential hoặc đáp ứng policy. **Session renewal** là gia hạn hoặc cấp lại session/token dựa trên trạng thái hiện có.

Hai hoạt động này khác nhau:

| Hoạt động | Có cần người dùng xác thực lại? | Có làm mới authentication time? |
| --- | --- | --- |
| Refresh access token bằng refresh token | Thường không | Không, trừ khi có authentication event mới được xác minh |
| Gia hạn cookie/session theo hoạt động | Không nhất thiết | Không |
| Người dùng nhập lại password | Có | Có thể, nếu được ghi nhận là authentication event |
| Passkey assertion mới | Có | Có, theo context của issuer/ứng dụng |
| MFA step-up thành công | Có bước xác thực bổ sung | Cần ghi nhận thời điểm và assurance của step-up |
| Mở lại tab đang có session | Không | Không |
| Gọi API nền/heartbeat | Không | Không |

Không cập nhật auth_time khi chỉ refresh token. Nếu refresh token tạo access token mới và server ghi auth_time bằng iat mới, hệ thống sẽ đánh giá freshness sai và có thể cho phép hành động nhạy cảm dựa trên một lần xác thực cũ.

### 6.1. Sliding expiration và absolute expiration

Session có thể dùng hai giới hạn:

- **Idle timeout:** session hết hạn sau một khoảng không có hoạt động phù hợp.
- **Absolute timeout:** session hết hạn sau tổng thời gian tối đa kể từ khi được tạo hoặc từ mốc policy xác định, dù có hoạt động liên tục.

Sliding expiration thường kéo dài thời hạn khi có hoạt động; nếu không có absolute timeout, session bị đánh cắp có thể được giữ sống lâu bằng request tự động. Absolute timeout giới hạn tổng tuổi session, nhưng không thay thế reauthentication theo authentication time.

Nên xác định session age và authentication age riêng. Một session được tạo hôm qua từ lần xác thực hôm qua có thể còn hoạt động hôm nay, nhưng thao tác nhạy cảm có thể yêu cầu authentication age dưới vài phút.

## 7. Áp dụng freshness theo rủi ro và hành động

Không yêu cầu người dùng xác thực lại cho mọi request; điều đó làm tăng ma sát và có thể khuyến khích hành vi không an toàn. Thay vào đó, phân loại hành động và đặt policy tương xứng.

| Hành động | Context có thể yêu cầu | Ví dụ kiểm soát |
| --- | --- | --- |
| Xem nội dung thông thường | Session còn hiệu lực | Kiểm tra session/token và authorization |
| Xem dữ liệu cá nhân nhạy cảm | Authentication còn tương đối mới | max_age hoặc freshness check |
| Đổi email/điện thoại recovery | Authentication gần đây và assurance phù hợp | Reauth + xác minh kênh mới + thông báo kênh cũ |
| Thêm/xóa passkey hoặc MFA | Authentication mới và step-up | Passkey/MFA hiện có, transaction binding |
| Tạo API key hoặc client credential | Step-up và quyền quản trị phù hợp | Reauth mạnh, audit, hiển thị secret một lần |
| Chuyển tiền/phê duyệt giao dịch | Context mạnh, mới và gắn với transaction | Step-up, xác nhận nội dung, chống replay |
| Thay đổi quyền admin | Fresh authentication và assurance cao | MFA phishing-resistant, dual control khi cần |
| Xóa tài khoản | Fresh authentication và xác nhận ý định | Step-up, delay/recovery policy phù hợp |

Các ví dụ không phải ngưỡng cố định. Tổ chức phải xác định thời gian, ACR/AMR và loại authenticator theo threat model, luật áp dụng, giá trị tài sản và khả năng IdP.

### 7.1. Risk-based reauthentication

Ngoài thời gian, hệ thống có thể xét tín hiệu rủi ro:

- Đăng nhập từ thiết bị hoặc vị trí bất thường.
- Địa chỉ mạng thay đổi đột ngột hoặc dấu hiệu proxy/risk.
- Session vừa được khôi phục hoặc credential vừa thay đổi.
- Hành vi giao dịch khác thường.
- Tài khoản vừa đổi password, email hoặc phương thức MFA.
- Phát hiện token/session có thể đã bị lộ.

Tín hiệu rủi ro không nên được xem là bằng chứng danh tính độc lập. Chúng giúp quyết định có yêu cầu step-up, hạn chế hành động hoặc chuyển review. Không từ chối tự động chỉ dựa trên IP hoặc vị trí ước lượng nếu không có đánh giá và đường xử lý phù hợp.

## 8. Ràng buộc step-up với hành động nhạy cảm

Một lần xác thực mới không nhất thiết xác nhận ý định của người dùng đối với một giao dịch cụ thể. Ví dụ, attacker có thể dụ nạn nhân hoàn tất MFA cho một request khác, sau đó dùng context mới để thực hiện hành động mà nạn nhân không mong muốn.

Với giao dịch nhạy cảm, cần ràng buộc step-up với transaction:

- Tạo transaction ID phía server.
- Ghi nhận resource, action và các tham số quan trọng.
- Hiển thị rõ nội dung cần xác nhận cho người dùng.
- Gắn yêu cầu step-up với transaction hoặc audience/purpose cụ thể theo thiết kế.
- Xác minh callback/assertion thuộc đúng transaction.
- Tiêu thụ challenge/transaction một lần.
- Kiểm tra transaction chưa hết hạn hoặc bị thay đổi.
- Chỉ thực hiện side effect sau khi xác thực và authorization hoàn tất.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant I as Identity Provider
    participant D as Database
    U->>A: Yêu cầu thao tác nhạy cảm
    A->>D: Tạo transaction ID + nội dung + trạng thái pending
    A->>I: Yêu cầu reauth/step-up với context phù hợp
    I->>U: Xác thực lại / MFA
    U->>I: Hoàn tất xác thực
    I-->>A: Assertion/token context mới
    A->>A: Verify issuer, transaction, auth_time, ACR/AMR
    A->>D: Consume transaction atomically
    A->>D: Thực hiện hành động đã được xác nhận
    A-->>U: Kết quả
~~~

Không cho phép client gửi transaction amount hoặc destination mới sau khi step-up rồi dùng context cũ để xác nhận. Server cần giữ bản ghi giao dịch và so khớp các tham số đã xác nhận.

## 9. SSO và authentication time

Trong SSO, người dùng có thể xác thực tại IdP một lần rồi truy cập nhiều relying party. Mỗi ứng dụng có session riêng nhưng có thể dựa trên cùng một authentication event tại IdP.

Ví dụ:

- Người dùng xác thực tại IdP lúc 08:00.
- Ứng dụng A nhận ID token và tạo session lúc 08:01.
- Ứng dụng B được truy cập lúc 11:00 và IdP dùng lại SSO session.
- Ứng dụng B nhận kết quả mới nhưng auth_time vẫn có thể là 08:00.
- iat của ID token dành cho B có thể là 11:00.

Nếu ứng dụng B cần xác thực trong 5 phút gần nhất, chỉ nhìn iat=11:00 là sai. B cần yêu cầu max_age phù hợp và kiểm tra auth_time theo OIDC.

### 9.1. Federation và độ tin cậy của timestamp

Khi nhận authentication context từ IdP ngoài, RP cần tin issuer và hiểu ý nghĩa claim theo hợp đồng federation. Cần xác định:

- Timestamp do issuer nào tạo?
- Nó biểu diễn authentication event nào?
- Có phải thời điểm password/MFA/passkey được thực hiện hay chỉ thời điểm SSO session?
- Clock của issuer được đồng bộ và có độ chính xác ra sao?
- ACR/AMR được mapping sang policy nội bộ thế nào?
- Nếu claim thiếu hoặc issuer không hỗ trợ max_age, ứng dụng xử lý ra sao?

Không tự gán freshness cao cho token chỉ vì nó đến từ IdP đã được liên kết. Trust issuer là điều kiện cần, nhưng vẫn cần kiểm tra claims, audience, signature và policy.

## 10. Account recovery và thay đổi credential ảnh hưởng freshness

Account recovery có thể thay đổi trạng thái xác thực và mức tin cậy của tài khoản. Việc người dùng hoàn tất recovery không tự động tương đương một lần MFA mạnh.

Ví dụ, người dùng reset password qua email link. Hệ thống có thể cho phép đặt password mới nhưng cần đánh giá riêng:

- Email được xác minh gần đây hay chỉ là địa chỉ cũ?
- Có bằng chứng nào cho thấy người yêu cầu là chủ tài khoản?
- Recovery có yêu cầu thêm credential hoặc review không?
- Session/token cũ có bị thu hồi không?
- Có thông báo tới kênh liên hệ trước đó không?
- Có thời gian chờ hoặc hạn chế hành động nhạy cảm sau recovery không?
- Authentication context mới có mức assurance nào và thời điểm nào?

Sau recovery, nên thu hồi session/refresh token có rủi ro theo policy, ghi audit và có thể yêu cầu đăng nhập lại bằng credential vừa thiết lập. Không đặt auth_time là thời điểm reset password nếu reset flow không thực sự xác minh người dùng theo tiêu chuẩn authentication mà ứng dụng yêu cầu.

### 10.1. Credential enrollment không tự làm mới xác thực

Thêm một passkey, số điện thoại hoặc phương thức MFA là thay đổi credential lifecycle. Hành động đó cần được bảo vệ bằng authentication context đủ mới, nhưng bản thân việc đăng ký credential không chứng minh lần đăng nhập hiện tại đã dùng credential mới.

Ghi riêng thời điểm enrollment và thời điểm authentication. Nếu policy yêu cầu lần xác thực sau phải dùng passkey vừa đăng ký, cần thực hiện một assertion mới và xác minh rõ.

## 11. Clock, timezone và timestamp

Freshness phụ thuộc phép tính thời gian; lỗi clock có thể làm từ chối người dùng hợp lệ hoặc chấp nhận xác thực quá cũ.

### 11.1. Dùng thời gian phía server

- Dùng đồng hồ server được đồng bộ từ nguồn thời gian đáng tin.
- Chuẩn hóa timestamp nội bộ theo UTC.
- Giữ đúng đơn vị của claim giao thức; OIDC NumericDate thường dùng giây kể từ Unix epoch.
- Không dùng giờ local từ browser hoặc điện thoại làm nguồn quyết định.
- Kiểm tra timestamp quá xa trong tương lai và giá trị âm/bất thường.
- Định nghĩa clock skew tolerance theo policy, không mở rộng tùy tiện.
- Theo dõi drift giữa AS, RP, RS và các node trong cluster.

### 11.2. Clock skew

Nếu IdP và RP lệch giờ, một authentication time hợp lệ có thể bị xem là nằm trong tương lai hoặc cũ hơn thực tế. Có thể chấp nhận một khoảng sai lệch nhỏ theo policy, nhưng cần giới hạn và giám sát.

Không cho phép timestamp tương lai lớn được coi là “vừa xác thực”. Nếu auth_time nằm ngoài phạm vi hợp lý, yêu cầu xác thực lại hoặc từ chối theo policy và ghi audit.

### 11.3. Timestamp thiếu hoặc không đáng tin

Nếu policy cần freshness nhưng issuer không cung cấp auth_time hoặc không bảo đảm ý nghĩa của nó, client không nên suy từ iat hay thời điểm nhận response. Có thể yêu cầu reauthentication qua flow được hỗ trợ, dùng một nguồn context khác đã được thỏa thuận hoặc từ chối thao tác nhạy cảm cho tới khi có bằng chứng đủ tin cậy.

## 12. Lưu authentication context phía ứng dụng

Ứng dụng có thể lưu authentication context gắn với session để ra quyết định về freshness và assurance. Ví dụ mô hình khái niệm:

~~~json
{
  "principal_id": "user-4821",
  "issuer": "https://id.example.test",
  "authenticated_at": "2026-11-22T08:00:00Z",
  "session_created_at": "2026-11-22T08:01:00Z",
  "last_activity_at": "2026-11-22T11:00:00Z",
  "acr": "urn:example:loa:2",
  "amr": ["passkey", "user-verification"],
  "mfa_verified_at": "2026-11-22T08:00:00Z",
  "authentication_event_id": "evt-7a21"
}
~~~

Đây là ví dụ schema khái niệm, không phải chuẩn bắt buộc. Cần:

- Gắn context với principal, issuer, session và authentication event cụ thể.
- Chỉ ghi claim đã được xác minh từ issuer hoặc event nội bộ đáng tin.
- Phân biệt auth_time với mfa_verified_at nếu hai sự kiện khác nhau.
- Giữ nguồn và policy mapping cho ACR/AMR.
- Không cho client tự sửa các trường này.
- Bảo vệ context khi lưu và khi truyền giữa các service.
- Có quy tắc cập nhật khi reauthentication, step-up, recovery, credential change và session rotation.

Nếu backend nhận context từ gateway hoặc service khác, cần xác thực kênh và integrity của dữ liệu chuyển tiếp. Không tin header do browser tự gửi như X-Auth-Time hoặc X-MFA-Verified.

## 13. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng iat thay auth_time | Token refresh làm lần xác thực cũ trông như mới | Dùng auth_time đáng tin cậy cho freshness |
| Dùng last activity thay authentication time | Heartbeat hoặc request nền làm mới xác thực giả | Quản lý activity và auth event riêng |
| Coi session còn sống là vừa xác thực | Session cũ có thể thực hiện thao tác nhạy cảm | Freshness check và step-up |
| Chỉ kiểm tra MFA đã đăng ký | User chưa thực hiện MFA trong lần xác thực hiện tại | Kiểm tra ACR/AMR hoặc event MFA đã xác minh |
| Tin claim từ client | Client giả mạo auth_time/ACR | Chỉ tin token/assertion đã xác minh hoặc context nội bộ |
| Không kiểm tra issuer/audience | Claim thời gian từ token sai nguồn hoặc sai client được chấp nhận | Verify chữ ký, iss, aud, exp và token purpose |
| Bỏ qua clock skew | Từ chối nhầm hoặc chấp nhận timestamp bất thường | UTC, đồng bộ clock, tolerance có giới hạn |
| Reauth không gắn transaction | Context mới bị tái sử dụng cho hành động khác | Transaction binding và consume-once |
| Refresh token làm mới auth_time | Token refresh vượt freshness policy | Giữ nguyên thời điểm authentication event |
| Chỉ có idle timeout | Request nền giữ session sống quá lâu | Kết hợp absolute timeout và reauth |
| Không xử lý recovery | Recovery yếu tạo authentication context giả mạnh | Đánh giá recovery riêng, revoke và step-up |
| Không định nghĩa ACR/AMR mapping | Các issuer dùng giá trị khác nhau nhưng ứng dụng hiểu sai | Hợp đồng federation và mapping được review |

## 14. Kiểm thử authentication freshness

Một bộ kiểm thử cần xác minh cả thời gian lẫn context:

1. Đăng nhập mới và xác nhận auth_time được ghi nhận từ issuer đáng tin.
2. Refresh access token; xác nhận iat mới nhưng auth_time không tự đổi.
3. Tạo SSO session cũ, mở ứng dụng mới; xác nhận iat mới không bị hiểu là authentication mới.
4. Gửi max_age nhỏ hơn authentication age; xác nhận OP yêu cầu xác thực lại hoặc response không được client chấp nhận.
5. Gửi prompt=login; xác nhận flow tương tác theo policy và kiểm tra context trả về.
6. Yêu cầu ACR/MFA context; xác nhận issuer đáp ứng đúng mức hoặc client xử lý không hỗ trợ.
7. Gửi auth_time thiếu, quá cũ, nằm trong tương lai hoặc sai đơn vị; xác nhận fail theo policy.
8. Giả mạo auth_time ở header do client kiểm soát; xác nhận server bỏ qua.
9. Thực hiện step-up cho transaction A rồi đổi nội dung thành transaction B; xác nhận bị từ chối.
10. Dùng lại callback hoặc transaction ID; xác nhận challenge/transaction chỉ tiêu thụ một lần.
11. Kiểm thử clock skew giữa IdP và RP.
12. Kiểm thử idle timeout và absolute timeout riêng biệt.
13. Refresh token sau recovery; xác nhận session cũ bị xử lý theo policy.
14. Kiểm thử MFA đã đăng ký nhưng không được thực hiện trong lần authentication mới.
15. Kiểm thử session bị đánh cắp tiếp tục gửi heartbeat; xác nhận absolute timeout/reauth vẫn có hiệu lực.

Không dùng token, cookie hoặc thông tin tài khoản production trong test fixture. Log test chỉ nên chứa event ID và reason code đã được che dữ liệu nhạy cảm.

## 15. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Đã định nghĩa authentication time? | Có nguồn, ý nghĩa và đơn vị rõ |
| Có phân biệt iat, auth_time và last activity? | Không dùng thay thế lẫn nhau |
| Freshness được áp dụng theo hành động? | Mỗi thao tác có ngưỡng và lý do rủi ro |
| Có kiểm tra assurance riêng? | ACR/AMR hoặc event xác thực được mapping rõ |
| MFA có thực sự được thực hiện gần đây? | Có thời điểm/event xác minh, không chỉ cờ đã đăng ký |
| OIDC max_age/prompt được dùng đúng? | Kiểm tra auth_time và response theo giao thức |
| Issuer và token có được xác minh? | Signature, iss, aud, exp, nonce và token purpose |
| Step-up có transaction binding? | Challenge gắn với action/resource/parameters và consume-once |
| Session có idle và absolute timeout? | Hai giới hạn được quản lý riêng |
| Refresh token có làm mới auth_time sai? | Không; refresh chỉ cấp token mới |
| Recovery có tạo context phù hợp? | Recovery và authentication assurance được đánh giá riêng |
| Clock được quản lý? | UTC, đồng bộ và skew tolerance giới hạn |
| Context có được bảo vệ? | Server-side, integrity, principal/session binding |
| Có test negative cases? | Timestamp cũ/tương lai, replay, issuer sai và transaction substitution |
| Có audit? | Ghi authentication event ID, policy result và reason code an toàn |

### Tình huống tự kiểm tra

**Tình huống 1:** ID token mới có iat cách đây 10 giây nhưng auth_time từ 8 giờ trước. Người dùng có vừa xác thực không?

**Trả lời:** Không. Token mới được phát hành, nhưng authentication event được ghi nhận đã xảy ra 8 giờ trước. Refresh hoặc tạo token mới không tự làm mới auth_time.

**Tình huống 2:** Session còn hoạt động và last_activity vừa cập nhật. Có đủ để cho phép người dùng đổi số điện thoại recovery không?

**Trả lời:** Không nhất thiết. Đây là hành động nhạy cảm; cần kiểm tra authentication freshness và assurance theo policy, có thể yêu cầu reauthentication/step-up.

**Tình huống 3:** Tài khoản đã đăng ký MFA nhưng lần đăng nhập hiện tại chỉ dùng password. Có thể coi context là MFA không?

**Trả lời:** Không. Đăng ký MFA khác với việc MFA đã được thực hiện trong authentication event. Cần kiểm tra context hoặc bằng chứng MFA thực tế.

**Tình huống 4:** Client gửi max_age=300 nhưng ID token không có auth_time. Có nên giả định OP đã đáp ứng yêu cầu không?

**Trả lời:** Không. Client cần xử lý thiếu claim theo OIDC và policy; không suy ra từ iat hoặc thời điểm nhận token.

**Tình huống 5:** Người dùng vừa hoàn tất step-up cho giao dịch 100.000 đồng, sau đó client thay số tiền thành 10.000.000 đồng nhưng tái sử dụng kết quả step-up. Có chấp nhận không?

**Trả lời:** Không. Step-up phải được ràng buộc với transaction và các tham số đã xác nhận. Thay đổi nội dung cần một transaction/confirmation mới theo policy.

## 16. Ghi nhớ

**Thời điểm truy cập không đồng nghĩa với thời điểm xác thực.** Authentication time cho biết lần xác thực được ghi nhận xảy ra khi nào; iat cho biết token được phát hành khi nào; last activity cho biết ứng dụng thấy hoạt động gần nhất; session creation time cho biết phiên được tạo lúc nào. Refresh token hoặc heartbeat không tạo ra một authentication event mới.

Thiết kế an toàn cần đánh giá đồng thời freshness và assurance. Dùng auth_time/max_age của OIDC khi phù hợp, kiểm tra issuer và token, yêu cầu step-up cho hành động nhạy cảm, ràng buộc step-up với transaction, quản lý idle/absolute timeout riêng và xử lý clock/recovery cẩn thận. Chỉ cấp quyền khi authentication context thực sự đáp ứng yêu cầu của hành động hiện tại.
