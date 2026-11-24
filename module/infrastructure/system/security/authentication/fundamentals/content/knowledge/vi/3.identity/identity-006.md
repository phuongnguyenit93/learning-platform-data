# Federated identity — Danh tính liên kết giữa các hệ thống

## 1. Federated identity là gì?

**Federated identity** (danh tính liên kết, hay liên kết định danh) là mô hình trong đó một hệ thống **dựa vào kết quả xác thực do một hệ thống khác phát hành** theo một quan hệ tin cậy đã thiết lập. Ứng dụng không cần trực tiếp quản lý mật khẩu của mọi người dùng: một **nhà cung cấp danh tính** xác thực người dùng, rồi chuyển cho ứng dụng một bằng chứng có thể kiểm tra được.

Ví dụ: nhân viên đăng nhập cổng quản trị của công ty bằng tài khoản doanh nghiệp do bộ phận CNTT quản lý. Cổng quản trị nhận bằng chứng từ hệ thống danh tính của công ty và tạo phiên sử dụng riêng. Một nhân viên rời công ty có thể bị vô hiệu hóa tại hệ thống danh tính tập trung, giúp giảm nguy cơ vẫn đăng nhập vào các ứng dụng tích hợp.

Đây là một chủ đề thuộc chương **Identity** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Khi học về credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản, cần hiểu **danh tính đi qua ranh giới tin cậy như thế nào**. Mục tiêu không chỉ là cho phép đăng nhập thuận tiện, mà còn chống phishing, replay, lạm dụng đăng nhập và các lỗi dẫn đến chiếm tài khoản.

Ba khái niệm gần nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity federation** | Hai hoặc nhiều miền tin cậy có thỏa thuận để một bên chấp nhận bằng chứng danh tính của bên khác. | Ứng dụng của đối tác chấp nhận người dùng từ IdP doanh nghiệp. |
| **Single Sign-On (SSO)** | Người dùng có thể sử dụng nhiều ứng dụng với ít lần đăng nhập tương tác hơn. | Sau khi đăng nhập IdP, người dùng mở thêm một ứng dụng mà không phải gõ lại mật khẩu. |
| **Account linking** | Gắn một danh tính bên ngoài với một tài khoản nội bộ cụ thể. | Tài khoản trong ứng dụng được liên kết với danh tính OIDC của một IdP. |

**SSO là một trải nghiệm** có thể được triển khai qua federation, nhưng federation không tự đảm bảo mọi ứng dụng có cùng một phiên hoặc cùng chính sách đăng xuất. **Liên kết tài khoản là một quyết định bảo mật riêng**: xác thực thành công với IdP không mặc nhiên chứng minh người đó sở hữu một tài khoản nội bộ có cùng địa chỉ email.

## 2. Các bên tham gia và ranh giới tin cậy

- **Người dùng / trình duyệt (user agent):** nơi bắt đầu luồng đăng nhập và vận chuyển một số thông điệp qua chuyển hướng. Trình duyệt, tham số URL và biểu mẫu không phải nguồn dữ liệu đáng tin chỉ vì chúng hiển thị đúng giao diện.
- **Identity Provider (IdP):** hệ thống xác thực người dùng, có thể yêu cầu mật khẩu, MFA, passkey hoặc xác thực bằng chứng chỉ; phát hành thông tin danh tính theo giao thức đã cấu hình.
- **Relying Party (RP) trong OpenID Connect hoặc Service Provider (SP) trong SAML:** ứng dụng sử dụng bằng chứng danh tính từ IdP, kiểm chứng bằng chứng đó và quyết định có tạo phiên nội bộ hay không.
- **Tài khoản/phiên nội bộ:** ánh xạ từ danh tính đã xác minh bên ngoài sang một người dùng nội bộ; phiên của ứng dụng có vòng đời và quyền riêng.
- **API/tài nguyên:** tiếp tục kiểm tra quyền truy cập, không chỉ dựa vào việc người dùng đã đi qua IdP.

~~~mermaid
flowchart LR
    U["Người dùng / trình duyệt"]
    I["IdP<br/>xác thực danh tính"]
    R["RP / SP<br/>xác minh bằng chứng"]
    M[("Ánh xạ tài khoản<br/>và chính sách nội bộ")]
    S[("Phiên của ứng dụng")]
    A["API / tài nguyên"]
    U -->|"Yêu cầu đăng nhập"| R
    R -->|"Chuyển hướng / yêu cầu xác thực"| I
    U <-->|"Tương tác đăng nhập"| I
    I -->|"Bằng chứng qua kênh giao thức"| R
    R -->|"Đối chiếu danh tính"| M
    R -->|"Tạo phiên sau kiểm chứng"| S
    U -->|"Gọi tài nguyên với phiên"| A
    A -->|"Kiểm tra phiên và phân quyền"| S
~~~

Sơ đồ trên minh họa **quan hệ trách nhiệm**; đường đi thực tế phụ thuộc giao thức. Trong OIDC, mã ủy quyền thường đi qua trình duyệt nhưng RP đổi mã lấy token bằng yêu cầu tới token endpoint; trong SAML Web Browser SSO, trình duyệt có thể chuyển tiếp SAML Response cho SP. Dù theo cách nào, **RP/SP phải tự kiểm chứng bằng chứng và chính sách tin cậy trước khi tạo phiên**.

Quan hệ tin cậy thường gồm các cấu hình hoặc dữ liệu được thiết lập từ trước:

1. **Ai được phép phát hành bằng chứng:** issuer hoặc entityID và nơi nhận thông điệp đã đăng ký.
2. **Bằng chứng được bảo vệ ra sao:** khóa xác thực chữ ký, metadata/cấu hình tin cậy, thuật toán được phép.
3. **Bằng chứng dành cho ai:** client ID hoặc audience của ứng dụng, điểm nhận phản hồi và loại token.
4. **Bằng chứng dùng được khi nào:** thời hạn hiệu lực, challenge/nonce, mã yêu cầu hoặc các điều kiện chống phát lại.
5. **Thông tin nào được ứng dụng sử dụng:** subject ổn định, thuộc tính người dùng và mức bảo đảm xác thực; quy tắc cấp quyền vẫn do ứng dụng quyết định.

Đặt một nút “Đăng nhập bằng công ty” lên giao diện **không** tự tạo quan hệ tin cậy. RP chỉ được chấp nhận phản hồi đến từ IdP đã cấu hình và thỏa mọi kiểm tra tương ứng với giao thức.

## 3. Các giao thức thường gặp: OIDC, OAuth 2.0 và SAML

| Giao thức | Vai trò chính | Thông điệp thường gặp | Ngữ cảnh triển khai |
| --- | --- | --- | --- |
| **OpenID Connect (OIDC)** | Lớp xác thực danh tính xây trên OAuth 2.0. | ID token, authorization code, UserInfo, discovery/JWKS. | Web/mobile hiện đại, đăng nhập doanh nghiệp hoặc xã hội. |
| **OAuth 2.0** | Khung **ủy quyền** truy cập tài nguyên thay mặt chủ thể hoặc ứng dụng. | Access token, scopes, authorization code, refresh token. | Ứng dụng gọi API theo quyền được cấp. |
| **SAML 2.0** | Trao đổi các assertion về xác thực và thuộc tính giữa IdP/SP. | SAML AuthnRequest, Response, Assertion, metadata. | SSO doanh nghiệp, tích hợp hệ thống lâu năm. |

**Access token không mặc nhiên là “thẻ căn cước” cho ứng dụng.** Token truy cập được phát hành để gọi một tài nguyên cụ thể, với audience, scope và chính sách của tài nguyên đó. Trong OIDC, **ID token** mới là loại token mang thông tin về sự kiện xác thực cho RP; RP phải kiểm tra ID token theo giao thức trước khi sử dụng.

SAML và OIDC có thể cùng được dùng trong một kiến trúc thông qua **identity broker**: broker tin cậy một hoặc nhiều IdP ở phía trên và lại đóng vai trò IdP với ứng dụng ở phía dưới. Mô hình này giúp tập trung tích hợp nhưng tạo thêm một ranh giới tin cậy: ứng dụng cần hiểu broker đã kiểm chứng nguồn danh tính, ánh xạ subject và chuyển tiếp mức bảo đảm như thế nào.

## 4. Luồng OIDC Authorization Code với PKCE

Một cách triển khai OIDC phổ biến cho ứng dụng mới là **Authorization Code Flow**, kết hợp **PKCE** để giảm nguy cơ mã ủy quyền bị chặn và đổi lấy token bởi bên khác. Với ứng dụng web có backend, phần trao đổi token thường diễn ra giữa backend và IdP; client public như mobile hoặc SPA cần bảo vệ token theo mô hình phù hợp của mình.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant R as RP / Ứng dụng
    participant I as OIDC IdP
    B->>R: Mở ứng dụng, chọn đăng nhập
    R->>R: Sinh state, nonce và PKCE verifier/challenge
    R-->>B: Redirect tới authorization endpoint
    B->>I: Gửi yêu cầu đăng nhập với state, nonce, challenge
    I->>B: Xác thực (có thể yêu cầu MFA/passkey)
    I-->>B: Redirect về callback kèm code và state
    B->>R: Chuyển code và state
    R->>R: Kiểm tra state và giao dịch đăng nhập
    R->>I: Đổi code bằng PKCE verifier tại token endpoint
    I-->>R: Trả token theo giao thức
    R->>R: Kiểm chứng ID token, issuer, audience, nonce, thời hạn
    R->>R: Ánh xạ issuer + sub sang tài khoản
    R-->>B: Tạo phiên ứng dụng và chuyển tới trang đích
~~~

**Các bước cần hiểu sâu:**

1. **Bắt đầu giao dịch:** RP tạo trạng thái đăng nhập gắn với phiên trình duyệt. Giá trị **state** khó đoán được dùng để ràng buộc phản hồi với giao dịch, giúp phòng login CSRF và phản hồi không mong đợi. RP sinh **code_verifier** bí mật cho PKCE và gửi **code_challenge** tương ứng. Nếu dùng **nonce**, RP phải lưu và đối chiếu nonce trong ID token.
2. **Chuyển sang IdP được tin cậy:** RP gửi client ID, redirect URI đã đăng ký, response type, scope phù hợp, state, code challenge và các tham số OIDC cần thiết. Redirect URI phải khớp chính sách đăng ký; tránh open redirect và endpoint callback chung chấp nhận tùy tiện đích chuyển hướng.
3. **IdP xác thực người dùng:** IdP có thể sử dụng mật khẩu, MFA, passkey hoặc phiên IdP đã có. RP không được tự suy ra phương thức xác thực chỉ từ việc không thấy màn hình mật khẩu.
4. **Callback nhận code:** RP đối chiếu state với giao dịch còn hiệu lực, ràng buộc issuer/IdP đã chọn, ngăn dùng lại giao dịch. **Code là giá trị tạm**, không phải ID token và không được coi là bằng chứng danh tính trước khi đổi và kiểm chứng token.
5. **Trao đổi token:** RP gửi code, redirect URI và code_verifier tới đúng token endpoint qua TLS; nếu là confidential client thì dùng cơ chế xác thực client đã đăng ký. PKCE giúp buộc code với bên đã tạo challenge; **PKCE không thay thế state** trong việc bảo vệ trạng thái giao dịch.
6. **Xác minh ID token:** Kiểm tra chữ ký bằng khóa tin cậy của issuer; đối chiếu issuer, audience/client ID, thời hạn, nonce đã gửi, và các điều kiện khác theo bối cảnh như azp nếu cần. Không tin JWT chỉ vì có thể base64-decode được payload.
7. **Ánh xạ và tạo phiên:** Dùng cặp **issuer + sub** làm khóa danh tính liên kết (với quy tắc phù hợp cho broker), tra bản ghi nội bộ rồi mới tạo phiên. Ứng dụng vẫn thực hiện phân quyền trên tài nguyên của chính mình.

### Ví dụ dữ liệu đã kiểm chứng

ID token OIDC có thể mang các claim tương tự ví dụ khái niệm sau:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "user-4f8c2",
  "aud": "portal-web",
  "exp": 1900000000,
  "iat": 1899999700,
  "nonce": "nonce-cua-giao-dich",
  "email": "lan@example.org",
  "email_verified": true,
  "amr": ["pwd", "otp"]
}
~~~

**Đây chỉ là payload minh họa, không phải ID token có chữ ký hợp lệ.** Ứng dụng không nên lấy các trường trên từ một chuỗi JSON do trình duyệt gửi rồi xem như đã xác thực. Cần kiểm tra token nguyên vẹn, thuật toán/chữ ký và toàn bộ điều kiện giao thức. Giá trị **sub** định danh một chủ thể trong phạm vi issuer; một giá trị sub giống nhau do **hai issuer khác nhau** phát hành không bảo đảm chỉ cùng một người.

**JWKS** là tập thông tin khóa công khai mà IdP có thể công bố để RP kiểm chứng chữ ký. Việc lấy/cập nhật khóa phải gắn với **issuer đã tin cậy**, không tùy ý theo URL do token tự chỉ định. Xử lý quay vòng khóa theo cấu hình đáng tin và không chấp nhận thuật toán bất ngờ, chữ ký không hợp lệ hay khóa không có quan hệ với issuer.

## 5. Luồng SAML Web Browser SSO

SAML 2.0 sử dụng các **assertion XML** để mô tả chủ thể, sự kiện xác thực và/hoặc thuộc tính. Một luồng **SP-initiated** điển hình:

1. Người dùng tới SP và chọn đăng nhập. SP tạo **AuthnRequest**, lưu ID/yêu cầu đang chờ và chuyển hướng trình duyệt tới IdP đã cấu hình.
2. IdP xác thực người dùng. Tùy binding, IdP gửi một **SAML Response** về **Assertion Consumer Service (ACS)** của SP qua trình duyệt.
3. SP xác minh chữ ký đúng đối tượng cần tin cậy theo hồ sơ tích hợp, issuer và khóa IdP đã cấu hình; kiểm tra **Destination**, **InResponseTo** (khi có yêu cầu), **AudienceRestriction**, **SubjectConfirmationData** với recipient và điều kiện thời gian, cùng các điều kiện khác áp dụng cho assertion.
4. SP kiểm soát replay thông qua ID assertion/response đã xử lý, cửa sổ thời gian ngắn và ràng buộc với giao dịch ban đầu, rồi ánh xạ subject vào người dùng nội bộ.
5. SP tạo phiên ứng dụng của chính mình; assertion không thay cho mọi lần kiểm tra quyền về sau.

**Những điều dễ làm sai trong SAML:**

- **Tin XML chưa đúng phạm vi chữ ký:** XML Signature có cấu trúc phức tạp; lỗi *signature wrapping* có thể xảy ra nếu phần được ứng dụng đọc để cấp quyền khác với phần thực sự được xác minh chữ ký. Dùng thư viện SAML được duy trì và cấu hình chặt, không tự ghép bộ phân tích XML/chữ ký.
- **Chấp nhận assertion sai đích:** một assertion dành cho SP khác hoặc ACS khác không được dùng để đăng nhập SP này.
- **Bỏ qua replay và điều kiện thời gian:** assertion cũ bị sao chép có thể dẫn đến đăng nhập lại nếu không kiểm tra ID, thời hạn và ngữ cảnh phản hồi.
- **Tự động tin metadata không xác minh:** metadata và chứng chỉ ký phải đến từ nguồn đã được xác lập tin cậy; thay chứng chỉ cần có quy trình quay vòng, kiểm thử và giám sát.
- **Không phân biệt SP-initiated và IdP-initiated:** trong IdP-initiated SSO, có thể không có AuthnRequest/InResponseTo để so khớp; vì vậy cần đánh giá riêng khả năng login CSRF, replay và các ràng buộc bù đắp, thay vì bỏ qua kiểm tra chung.

OIDC và SAML khác định dạng, nhưng điểm chung là **RP/SP phải kiểm tra bằng chứng trong ngữ cảnh của chính giao dịch và đúng đối tác tin cậy**.

## 6. Ánh xạ danh tính và liên kết tài khoản an toàn

Một tài khoản ứng dụng thường có ID nội bộ bất biến, chẳng hạn ID hồ sơ người dùng. Federation thêm một **bảng ánh xạ** từ danh tính được IdP xác nhận tới tài khoản đó:

~~~text
ExternalIdentity
---------------
provider_issuer      https://idp.example.org
provider_subject     user-4f8c2
local_user_id        u-00815
linked_at            <thời điểm liên kết>
~~~

Với OIDC trực tiếp, khóa tra cứu thích hợp thường là **(iss, sub)**. Với SAML, phải dùng bộ định danh chủ thể có ngữ nghĩa, phạm vi và độ bền phù hợp với thỏa thuận IdP/SP; không mặc định mọi NameID đều bất biến qua thời gian. Các IdP có thể dùng *pairwise subject identifiers*, nên cùng người dùng có thể mang sub khác nhau giữa các ứng dụng.

### Vì sao không nên nối tài khoản chỉ bằng email?

Email có thể thay đổi, được tái cấp phát hoặc có quy tắc xác minh khác nhau giữa các IdP. Ngay cả claim **email_verified=true** cũng chỉ phản ánh tuyên bố xác minh của issuer theo chính sách của họ, **không chứng minh quyền sở hữu một tài khoản nội bộ khác**. Nếu tự động gộp tài khoản khi chuỗi email trùng nhau, người mới kiểm soát địa chỉ email hoặc IdP có cấu hình yếu có thể chiếm dữ liệu của người dùng cũ.

Quy trình liên kết an toàn thường yêu cầu:

1. Người dùng đang ở một **phiên nội bộ đã xác thực đủ mạnh** hoặc thực hiện bước xác minh sở hữu tài khoản nội bộ.
2. Người dùng chủ động chọn IdP muốn liên kết; ứng dụng bắt đầu giao dịch federation mới với state/nonce và biện pháp chống replay.
3. Sau khi kiểm chứng phản hồi từ IdP, ứng dụng kiểm tra danh tính ngoài chưa bị liên kết với tài khoản khác và xác nhận thao tác liên kết theo mức rủi ro.
4. Lưu cặp định danh ngoài và ID nội bộ bằng thao tác có tính nhất quán, ngăn hai yêu cầu đồng thời tạo liên kết chồng chéo.
5. Ghi sự kiện, thông báo cho chủ tài khoản khi cần và cung cấp cơ chế gỡ liên kết có kiểm soát. Không cho gỡ phương thức đăng nhập cuối cùng nếu không có đường khôi phục an toàn khác.

Khi **vừa đăng nhập lần đầu** bằng IdP được tin cậy, ứng dụng có thể tạo người dùng mới bằng **Just-in-Time (JIT) provisioning** theo chính sách. Điều đó khác với việc tự ý **ghép** người dùng vừa xác thực vào một tài khoản đã tồn tại. Cần thiết kế rõ xử lý tài khoản trùng, đổi email, đổi IdP và chuyển đổi nhà cung cấp danh tính.

## 7. Federation không tự động giải quyết phân quyền

IdP cung cấp thông tin về việc **ai đã xác thực** và có thể phát hành thuộc tính, nhóm, vai trò hoặc mức bảo đảm đăng nhập. Ứng dụng vẫn cần quyết định người đó **được làm gì**, dựa trên chính sách và nguồn dữ liệu phù hợp.

Ví dụ: đối tác A và đối tác B cùng đăng nhập vào một cổng quản lý đơn hàng. Dù cả hai được xác thực bởi một IdP, API phải kiểm tra quyền trên **từng đơn hàng thuộc đúng tổ chức**. Không thể coi claim “đã đăng nhập” hoặc chuỗi “role=admin” do client gửi là đủ để mở mọi tài nguyên.

Một số cách quản lý quyền và vòng đời:

- **Ánh xạ nhóm/role từ IdP:** chỉ tin claim đã được xác minh từ nguồn cấu hình; xác định phạm vi tenant, đặt mặc định quyền tối thiểu và hiểu độ trễ khi nhóm thay đổi.
- **JIT provisioning:** tạo hồ sơ khi người dùng đăng nhập lần đầu, nhưng chưa chắc cập nhật việc vô hiệu hóa giữa các lần đăng nhập.
- **SCIM hoặc tích hợp cấp phát vòng đời:** đồng bộ tạo, sửa, vô hiệu hóa tài khoản; là **quy trình provisioning**, không phải bằng chứng đăng nhập.
- **Kiểm tra quyền ở API:** đánh giá user, tenant, resource, action tại điểm sử dụng; không trao quyền chỉ vì danh tính từng vượt qua federation.

Khi IdP khóa một tài khoản, **phiên cũ tại RP có thể vẫn còn hiệu lực**. Nếu yêu cầu thu hồi gần như tức thì, cần thiết kế thời hạn phiên, đồng bộ trạng thái, cơ chế thu hồi hoặc xác minh lại theo rủi ro. Không được giả định “vô hiệu hóa tại IdP” lập tức đăng xuất ở tất cả ứng dụng.

## 8. MFA, passkey, mức bảo đảm và phiên

Federation giúp đưa **quyết định xác thực** về IdP, nhưng mức bảo đảm của từng lần đăng nhập có thể khác nhau:

- **Mật khẩu đơn lẻ** dễ bị phishing, tái sử dụng hoặc lộ từ dịch vụ khác.
- **MFA với OTP** cải thiện khả năng chống dùng mật khẩu lộ đơn lẻ, song OTP vẫn có thể bị chuyển tiếp trên trang giả.
- **Passkey/WebAuthn** với kiểm tra origin và RP ID cung cấp khả năng chống phishing mạnh hơn, khi được triển khai và kiểm chứng đúng.
- **Chứng chỉ/mTLS** có thể hữu ích trong xác thực thiết bị hoặc dịch vụ; chứng chỉ thiết bị không tự suy ra người đang dùng thiết bị là chủ tài khoản được phép.

Trong OIDC, các claim như **amr** (phương thức xác thực), **acr** (ngữ cảnh/lớp bảo đảm theo thỏa thuận) và **auth_time** có thể hỗ trợ RP đánh giá yêu cầu đăng nhập tăng cường. Không nên gán một giá trị amr/acr thành “an toàn cao” khi chưa có thỏa thuận ngữ nghĩa với IdP và chưa kiểm chứng ID token. Với SAML, cần hiểu **AuthnContext** theo cấu hình tích hợp.

Đối với thao tác nhạy cảm như thay phương thức đăng nhập, đổi email, liên kết IdP mới, rút tiền hoặc xuất dữ liệu, ứng dụng có thể yêu cầu **xác thực lại gần thời điểm thao tác** và mức bảo đảm phù hợp. Việc chỉ còn một phiên RP cũ không chứng minh chủ tài khoản vẫn đang thao tác.

**Hai loại phiên riêng biệt:**

1. **Phiên IdP:** cho phép IdP nhớ người dùng đã được xác thực và có thể cấp trải nghiệm SSO sang ứng dụng khác.
2. **Phiên RP/SP:** ứng dụng tự tạo sau khi kiểm chứng kết quả federation; có cookie/token, thời hạn, chống CSRF, chính sách thu hồi và logout riêng.

Đăng xuất RP thường kết thúc phiên RP; **không chắc** phiên IdP hoặc phiên của các ứng dụng khác cũng kết thúc. Các cơ chế single logout/front-channel/back-channel logout nếu sử dụng phải được kiểm thử rõ, đặc biệt khi mạng gián đoạn, tab bị đóng hoặc phía nhận không xử lý được thông báo.

## 9. Các tấn công điển hình và lớp kiểm soát

| Rủi ro | Điều gì có thể xảy ra? | Kiểm soát phù hợp |
| --- | --- | --- |
| **Login CSRF / nhầm giao dịch** | Kẻ tấn công khiến trình duyệt nạn nhân hoàn thành đăng nhập vào tài khoản do kẻ tấn công chọn. | Kiểm tra state, giao dịch, ngữ cảnh phiên, issuer; bảo vệ callback. |
| **Mix-up giữa nhiều IdP** | RP gửi code/token tới endpoint sai hoặc chấp nhận issuer không phải bên đã chọn. | Gắn giao dịch với issuer, kiểm tra issuer/response; dùng cấu hình IdP tĩnh, đáng tin. |
| **Token substitution / audience confusion** | Dùng token của ứng dụng hoặc API khác để đăng nhập RP này. | Kiểm tra loại token, issuer, audience, client, chữ ký và các claim bắt buộc. |
| **Replay code/assertion** | Phát lại code hoặc assertion đã dùng. | Code dùng một lần, PKCE, nonce, state, cache ID SAML đã xử lý và kiểm tra thời hạn. |
| **Open redirect / rò rỉ code** | Tham số redirect không kiểm soát đưa code/token sang trang của kẻ tấn công. | Đăng ký redirect URI chính xác, tránh chuyển hướng tùy ý và loại token khỏi URL/log. |
| **Liên kết nhầm email** | Claim email trùng bị dùng để chiếm tài khoản nội bộ. | Khóa danh tính ổn định, xác minh cả tài khoản cũ và mới khi liên kết. |
| **Tin role không đúng nguồn** | Claim tùy ý hoặc dữ liệu chưa xác minh thành quyền quản trị. | Kiểm chứng chữ ký/nguồn, ánh xạ role có kiểm soát và kiểm tra quyền ở API. |
| **IdP hoặc khóa ký bị xâm phạm** | Bằng chứng giả có thể vượt kiểm tra nếu bên phát hành thực sự bị chiếm. | Quy trình quản trị IdP, bảo vệ và quay vòng khóa, phân quyền quản trị, giám sát và phương án xử lý sự cố. |
| **Phiên RP tồn tại sau khi vô hiệu hóa IdP** | Nhân viên đã nghỉ vẫn dùng session chưa hết hạn. | Đồng bộ trạng thái, thu hồi RP, TTL hợp lý, kiểm tra lại cho hành động nhạy cảm. |
| **Lỗi khôi phục tài khoản IdP** | Kẻ tấn công chiếm IdP qua email/SMS hoặc quy trình hỗ trợ yếu. | Đánh giá chính sách khôi phục của IdP, phát hiện bất thường và bước xác minh tăng cường khi cần. |

**Bảo mật liên kết là bảo mật chuỗi phụ thuộc.** Một RP kiểm tra chữ ký đúng vẫn có thể gặp nguy cơ nếu IdP chấp nhận quy trình khôi phục quá yếu hoặc nếu RP tự động ghép người dùng theo email. Ngược lại, IdP dùng MFA mạnh vẫn không bảo vệ dữ liệu nếu RP bỏ qua audience hoặc API cấp quyền quá rộng.

## 10. Mã giả: xử lý callback OIDC một cách có kiểm soát

Mã giả này diễn tả những quyết định bắt buộc; **không phải mã sẵn sàng đưa vào production**. Khi triển khai, nên dùng thư viện OIDC phù hợp đã được kiểm thử và duy trì.

~~~text
handleOidcCallback(request):
    transaction = findPendingLoginTransaction(request.browserSession)
    require transaction != null
    require constantTimeEqual(request.state, transaction.state)
    require transaction.notExpired
    require transaction.notConsumed

    idp = configuredTrustedIssuer(transaction.selectedIssuer)
    require responseBelongsToIssuer(request, idp, transaction)

    tokens = oidcClient.exchangeAuthorizationCode(
        tokenEndpoint = idp.tokenEndpoint,
        code = request.code,
        redirectUri = transaction.redirectUri,
        codeVerifier = transaction.pkceVerifier,
        clientAuthentication = configuredClientAuthentication()
    )

    claims = oidcClient.verifyIdToken(
        idToken = tokens.idToken,
        trustedIssuer = idp.issuer,
        expectedAudience = configuredClientId(),
        trustedSigningKeys = idp.trustedKeys,
        expectedNonce = transaction.nonce,
        requiredTimeAndContextChecks = true
    )

    markTransactionConsumedAtomically(transaction)

    identityKey = (claims.iss, claims.sub)
    localAccount = lookupLinkedAccount(identityKey)

    if localAccount == null:
        localAccount = applyExplicitProvisioningOrLinkPolicy(claims)
        // Không tự động nhận tài khoản chỉ vì claims.email trùng.

    require localAccount.active
    require policy.allowsLogin(localAccount, claims.authenticationContext)

    session = createFreshLocalSession(localAccount.id)
    auditWithoutTokens("federated_login_succeeded", localAccount.id, claims.iss)
    return secureSessionResponse(session)
~~~

Trong thực tế cần quản lý kết quả lỗi và khả năng thực hiện lại một cách nguyên tử để tránh chấp nhận callback cũ; kiểm soát hành vi khi IdP không khả dụng; đặt timeout và retry hợp lý; lưu nonce/verifier bên server hoặc theo cơ chế bảo vệ tương đương; tránh log code, state bí mật, token và thông tin nhận dạng không cần thiết. Hàm **responseBelongsToIssuer** là một yêu cầu bảo mật cần được thực hiện theo giao thức thực tế, không phải lời gọi tùy ý trên một URL hoặc tham số do client tự chọn.

## 11. Tình huống thực tế: ba doanh nghiệp dùng chung cổng đối tác

Một công ty xây dựng cổng đặt hàng cho ba đối tác A, B và C. Mỗi đối tác có IdP riêng; một số nhân viên đăng nhập bằng OIDC, một số qua SAML. Cổng có một dịch vụ tài khoản nội bộ và API quản lý đơn hàng.

**Thiết kế dễ gây lỗi:**

- Callback nhận token từ bất kỳ issuer nào có thể phân giải được URL JWKS.
- Nếu claim email trùng tài khoản đang có, hệ thống nối luôn vào tài khoản đó.
- Role “admin” được cấp nguyên văn từ claim bất kỳ IdP nào gửi.
- Khi tài khoản bên IdP bị khóa, RP giữ session 60 ngày và không có cách thu hồi.

**Thiết kế theo ranh giới tin cậy:**

1. Quản trị viên cấu hình và phê duyệt **từng issuer/entityID**, endpoint, khóa/chứng chỉ và phương thức xác minh với từng đối tác. Hệ thống không tự tin bất kỳ issuer do client đưa vào.
2. Mỗi giao dịch đăng nhập gắn với IdP đã chọn; callback OIDC hoặc SAML phải qua kiểm tra giao thức và chống replay trước khi ánh xạ người dùng.
3. Bảng danh tính ngoài gắn với tài khoản nội bộ bằng khóa ổn định theo IdP; quy trình JIT tạo mới và quy trình liên kết vào tài khoản cũ là hai trường hợp xử lý riêng.
4. Cổng ánh xạ role theo chính sách của **từng tenant**, giới hạn quyền mặc định và kiểm tra tenant/resource/action trên mỗi yêu cầu API.
5. Cổng quản lý vòng đời phiên độc lập, tiếp nhận sự kiện vô hiệu hóa hoặc đồng bộ vòng đời khi có, và yêu cầu xác thực lại cho hành động nhạy cảm.

**Câu hỏi phân tích:** Nếu hai nhân viên của hai đối tác đều có email sales@example.org nhưng IdP khác nhau, có nên gộp tài khoản không? **Không.** Việc trùng địa chỉ email không thay thế bằng chứng sở hữu tài khoản; khi thật sự cần hợp nhất, phải có luồng liên kết được chủ tài khoản xác nhận.

## 12. Danh sách kiểm tra trước khi đưa federation vào sử dụng

- [ ] Danh sách IdP được cho phép và quy trình thiết lập trust rõ ràng; khóa/metadata được quản lý, quay vòng và giám sát.
- [ ] RP/SP kiểm tra đúng giao thức: issuer, chữ ký, audience/recipient, thời hạn, ràng buộc giao dịch và chống replay.
- [ ] OIDC dùng luồng phù hợp, state và PKCE; xác minh ID token trước khi dùng làm danh tính, bảo vệ redirect URI và token.
- [ ] Với SAML, sử dụng thư viện xử lý XML Signature đáng tin, kiểm tra điều kiện assertion và ACS/Response.
- [ ] Bảng ánh xạ danh tính dùng định danh ngoài ổn định; không tự động ghép tài khoản theo email.
- [ ] Việc thêm, gỡ hoặc thay đổi IdP liên kết yêu cầu xác minh sở hữu tài khoản tương ứng với rủi ro.
- [ ] Chính sách role, tenant và quyền tài nguyên được thực thi bởi ứng dụng/API, kể cả khi IdP đã xác thực.
- [ ] Mức bảo đảm đăng nhập và các yêu cầu xác thực lại thao tác nhạy cảm có ngữ nghĩa được thỏa thuận.
- [ ] Phiên RP có TTL, cookie/token an toàn, chống CSRF, đăng xuất/thu hồi và kế hoạch xử lý tài khoản bị vô hiệu hóa.
- [ ] Đã thử tình huống sai issuer, sai audience, token hết hạn, code/assertion lặp lại, login CSRF, mất khóa ký và IdP tạm ngừng hoạt động.
- [ ] Log đủ để điều tra, nhưng không ghi code ủy quyền, access token, ID token, mật khẩu hoặc mã khôi phục.

## 13. Ghi nhớ

**Federated identity là việc chuyển giao bằng chứng xác thực giữa các miền tin cậy có quy tắc**, không phải một nút đăng nhập hay một chuỗi email trùng nhau. IdP chịu trách nhiệm xác thực và phát hành bằng chứng; RP/SP kiểm chứng đúng bên phát hành, đúng người nhận, đúng giao dịch và đúng thời hạn; ứng dụng ánh xạ danh tính, cấp phiên và tự quyết định quyền truy cập. Khi các ranh giới này được thiết kế rõ ràng, federation hỗ trợ SSO thuận tiện đồng thời giảm rủi ro phishing, replay, liên kết nhầm tài khoản và duy trì quyền truy cập trái phép.
