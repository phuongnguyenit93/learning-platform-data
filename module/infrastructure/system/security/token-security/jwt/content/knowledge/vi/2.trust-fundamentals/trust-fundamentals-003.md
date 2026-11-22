# Ranh giới tin cậy giữa trình duyệt, ứng dụng và dịch vụ

Một hệ thống dùng JSON Web Token (JWT) thường có nhiều thành phần: trình duyệt của người dùng, ứng dụng giao diện, máy chủ ứng dụng, nhà cung cấp danh tính, API gateway và các dịch vụ phía sau. Các thành phần này không có cùng mức độ tin cậy và không nên chia sẻ cùng một giả định bảo mật. **Ranh giới tin cậy (trust boundary)** là nơi dữ liệu, danh tính, quyền hoặc lệnh đi từ một miền kiểm soát sang miền khác; tại đó hệ thống phải xác minh lại những điều kiện cần thiết trước khi tin và sử dụng dữ liệu.

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Nội dung áp dụng cho ứng dụng web, ứng dụng di động, API và hệ thống phân tán nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Ranh giới tin cậy là gì?

Một ranh giới tin cậy xuất hiện khi một thành phần nhận đầu vào từ thành phần khác mà nó không trực tiếp kiểm soát. Đầu vào có thể là:

- Danh tính được khai báo, thông tin xác thực hoặc token.
- Dữ liệu người dùng, tham số URL, header HTTP và nội dung request.
- Quyền, vai trò, tenant, trạng thái phiên hoặc quyết định từ một hệ thống khác.
- Thông điệp giữa các dịch vụ, webhook, sự kiện hàng đợi hoặc kết quả từ nhà cung cấp bên ngoài.

**Tin cậy không đồng nghĩa với kết nối được mã hóa hoặc nằm trong mạng nội bộ.** HTTPS/TLS bảo vệ dữ liệu trên đường truyền và xác thực endpoint theo cấu hình chứng chỉ; nó không tự chứng minh rằng người dùng có quyền xem một hóa đơn, rằng một service được phép gọi service khác, hoặc rằng dữ liệu đầu vào hợp lệ về nghiệp vụ.

### 1.1. Ba câu hỏi phải đặt ở mỗi ranh giới

| Câu hỏi | Ví dụ khi nhận JWT |
| --- | --- |
| **Ai gửi hoặc phát hành?** | Token có đến từ issuer được tin cậy và khóa xác minh có thực sự thuộc issuer đó không? |
| **Dữ liệu có hợp lệ trong ngữ cảnh này không?** | Token dành cho API nào, loại token nào, còn hạn không, claims có đáp ứng hợp đồng không? |
| **Bên gửi được làm gì?** | Chủ thể có scope phù hợp và có quyền truy cập tài nguyên cụ thể không? |

Ba câu hỏi này cần được giải quyết riêng. Một chữ ký JWT hợp lệ chỉ cung cấp bằng chứng mật mã trong phạm vi dữ liệu được ký và khóa được tin cậy; nó không tự cấp quyền truy cập cho mọi thành phần.

## 2. Nhìn hệ thống theo các miền tin cậy

Một kiến trúc web điển hình có thể được đơn giản hóa như sau:

~~~mermaid
flowchart LR
    U["Người dùng và thiết bị"] --> B["Trình duyệt / frontend"]
    B <-->|"Đăng nhập, redirect"| I["Identity Provider"]
    B -->|"HTTPS, session hoặc access token"| A["Ứng dụng / BFF"]
    A -->|"Token dành cho API"| G["API Gateway"]
    G --> S1["Service hóa đơn"]
    G --> S2["Service thanh toán"]
    S1 <-->|"Danh tính service / token riêng"| S2
~~~

Các miền trong sơ đồ có mục đích và rủi ro khác nhau:

| Thành phần | Vai trò | Giả định tin cậy cần tránh |
| --- | --- | --- |
| Thiết bị và trình duyệt | Hiển thị giao diện, nhận thao tác, giữ một phần trạng thái phiên | Không thể giả định thiết bị sạch, JavaScript không bị can thiệp hoặc dữ liệu phía client là đúng |
| Frontend chạy trong trình duyệt | Gửi request tới ứng dụng/API | Mã frontend, biến cấu hình và mọi bí mật nhúng trong bundle đều có thể bị người dùng xem |
| Identity Provider (IdP) / Authorization Server | Xác thực người dùng, cấp token theo giao thức và chính sách | Chỉ tin issuer, endpoint, khóa và luồng cấp token đã được cấu hình |
| Backend / Backend-for-Frontend (BFF) | Quản lý phiên, xử lý nghiệp vụ, gọi API phía sau | Phải xác thực đầu vào từ browser và chỉ sử dụng credential/token đúng mục đích |
| API Gateway | Điểm vào chung, định tuyến, giới hạn lưu lượng và có thể kiểm tra token | Request đi qua gateway chưa có nghĩa mọi service phía sau đều được phép tin payload hoặc bỏ kiểm tra quyền |
| Resource Server / service | Cung cấp tài nguyên hoặc thực thi hành động | Phải xác minh token và quyền dành cho chính tài nguyên/hành động của nó |
| Dịch vụ bên thứ ba | Cung cấp API, webhook hoặc tích hợp | Không chia sẻ token nội bộ hoặc tin dữ liệu chỉ vì kết nối tới đối tác thành công |

Một hệ thống nhỏ có thể gộp nhiều vai trò vào cùng một tiến trình. Dù triển khai vật lý chung, các vai trò bảo mật vẫn cần được phân biệt: browser là client, backend có thể là confidential client, còn API là resource server. Một thành phần có thể đảm nhiệm nhiều vai trò nhưng phải biết token nào được dùng cho vai trò nào.

## 3. Trình duyệt là một miền không thể giữ bí mật lâu dài

Trình duyệt chạy trên thiết bị do người dùng kiểm soát. Người dùng có thể xem mã JavaScript, sửa request, thay đổi dữ liệu gửi lên, cài extension, dùng công cụ phát triển hoặc chạy phần mềm độc hại trên thiết bị. HTTPS bảo vệ kết nối nhưng không biến browser thành một môi trường thực thi đáng tin tuyệt đối.

### 3.1. Frontend không phải nơi giữ client secret

Một ứng dụng SPA tải JavaScript và chạy trực tiếp trong trình duyệt là **public client** trong mô hình OAuth: nó không thể giữ một bí mật dùng chung theo cách mà máy chủ có thể giữ. Mọi giá trị nhúng vào bundle, kể cả biến môi trường được thay thế khi build, đều có thể bị người dùng đọc.

Không đặt các dữ liệu sau trong mã frontend với kỳ vọng chúng được giữ kín:

- OAuth `client_secret` hoặc khóa ký JWT.
- Khóa HMAC dùng chung với backend.
- Credential truy cập cơ sở dữ liệu, dịch vụ nội bộ hoặc cloud.
- Refresh token dài hạn hay thông tin xác thực có phạm vi quyền rộng nếu kiến trúc có thể tránh việc đưa chúng xuống browser.

Một public client vẫn có thể có `client_id`; giá trị này dùng để nhận diện ứng dụng, không phải mật khẩu. Với luồng đăng nhập OAuth/OIDC cho public client, sử dụng **Authorization Code Flow với PKCE**. PKCE ràng buộc việc đổi authorization code với một verifier do client tạo; nó không biến browser thành confidential client và không bảo vệ token khỏi mọi dạng XSS.

### 3.2. Luồng đăng nhập của ứng dụng trình duyệt

Luồng khái quát:

1. Frontend tạo yêu cầu đăng nhập và chuyển người dùng tới authorization server đáng tin.
2. Yêu cầu mang `state` để liên kết phản hồi với phiên bắt đầu đăng nhập; nếu dùng OpenID Connect, `nonce` giúp ràng buộc ID token với yêu cầu xác thực.
3. Public client tạo PKCE `code_verifier`, gửi `code_challenge` trong yêu cầu cấp quyền.
4. Sau khi người dùng xác thực và cấp quyền, authorization server chuyển authorization code về redirect URI đã đăng ký.
5. Client gửi code cùng `code_verifier` để đổi lấy token; authorization server kiểm tra PKCE.
6. Ứng dụng sử dụng access token đúng audience để gọi resource server. ID token, nếu có, phục vụ client xác nhận sự kiện đăng nhập theo OpenID Connect.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / public client
    participant I as Authorization Server
    participant R as Resource Server
    U->>B: Bắt đầu đăng nhập
    B->>B: Tạo state, PKCE verifier và challenge
    B->>I: Authorization request + challenge
    I->>U: Xác thực và xin cấp quyền
    U->>I: Hoàn tất xác thực / consent
    I->>B: Redirect về URI với authorization code + state
    B->>B: Kiểm tra state
    B->>I: Đổi code + PKCE verifier
    I->>B: Access token (và ID token nếu OIDC)
    B->>R: Request với access token
    R->>R: Xác minh token và quyền
    R->>B: Kết quả API
~~~

`state`, PKCE và `nonce` có mục đích khác nhau:

| Giá trị | Mục đích |
| --- | --- |
| `state` | Liên kết callback với yêu cầu đăng nhập ban đầu, giúp chống request forgery và nhầm lẫn phiên |
| PKCE `code_verifier` / `code_challenge` | Ngăn bên chặn được authorization code đổi code nếu không có verifier |
| OIDC `nonce` | Ràng buộc ID token với yêu cầu xác thực và giúp phát hiện token bị phát lại trong ngữ cảnh đó |

Redirect URI phải được đăng ký và so khớp chặt chẽ. Không chuyển authorization code hoặc token tới URL tùy ý từ tham số do người dùng điều khiển.

### 3.3. Token trong browser: nơi lưu và rủi ro

Access token dạng bearer là thông tin xác thực: ai có token hợp lệ có thể sử dụng token theo quyền được cấp, trừ khi có thêm cơ chế ràng buộc người gửi. Vì vậy, vị trí lưu token ảnh hưởng trực tiếp đến tác động của XSS, malware và việc chiếm quyền thiết bị.

| Cách lưu | Ưu điểm | Rủi ro / giới hạn |
| --- | --- | --- |
| Biến trong bộ nhớ ứng dụng | Không tồn tại lâu qua lần tải lại trang hoặc đóng tab theo cách lưu bền vững | JavaScript đang chạy, bao gồm mã XSS, vẫn có thể đọc hoặc sử dụng token |
| `localStorage` | Dễ sử dụng và tồn tại sau khi tải lại trang | JavaScript cùng origin có thể đọc; token có thể tồn tại lâu và bị lấy khi XSS xảy ra |
| `sessionStorage` | Thường giới hạn theo tab và phiên tab | JavaScript cùng origin vẫn có thể đọc; không ngăn XSS |
| Cookie `HttpOnly` | JavaScript không thể đọc trực tiếp giá trị cookie | Browser tự gửi cookie theo quy tắc cookie; cần thiết kế chống CSRF, phạm vi domain/path và thời hạn |
| BFF giữ token phía server | Browser không cần giữ access/refresh token OAuth | BFF trở thành thành phần nhạy cảm; cần bảo vệ session, cookie, CSRF và backend |

Không có nơi lưu nào biến browser thành môi trường đáng tin. Nếu dùng token trong browser, hãy giảm quyền và thời gian sống, tránh lưu bền vững nếu không cần, không ghi token vào URL/log, và giảm nguy cơ XSS bằng output encoding, xử lý DOM an toàn, Content Security Policy phù hợp và quản lý dependency.

### 3.4. BFF: đặt token ở phía máy chủ

Với mô hình **Backend-for-Frontend (BFF)**, browser tương tác với backend qua session cookie; BFF giữ access token và refresh token ở phía server, rồi gọi API thay browser.

~~~mermaid
flowchart LR
    B["Browser"] -->|"Cookie phiên"| F["BFF"]
    F -->|"Access token"| R["Resource Server"]
    R --> F
    F -->|"Dữ liệu đã xử lý"| B
    I["Authorization Server"] <-->|"Code / token"| F
~~~

Cookie phiên nên được cấu hình phù hợp, thường gồm:

- `Secure`: chỉ gửi qua kết nối an toàn.
- `HttpOnly`: JavaScript không đọc trực tiếp được cookie.
- `SameSite`: hạn chế cookie được gửi trong một số ngữ cảnh cross-site; chọn `Lax`, `Strict` hoặc `None` theo luồng nghiệp vụ.
- `Path`, `Domain`, thời hạn và tên cookie được giới hạn đúng nhu cầu; tránh phạm vi chia sẻ rộng không cần thiết.

Cookie tự động được browser đính kèm theo quy tắc gửi cookie, vì vậy BFF phải xử lý **CSRF** cho thao tác làm thay đổi trạng thái: anti-CSRF token hoặc cơ chế tương đương, kiểm tra `Origin`/`Referer` khi phù hợp và cấu hình SameSite. `HttpOnly` giúp giảm khả năng đọc trộm cookie qua JavaScript nhưng **không ngăn XSS thực hiện hành động thay người dùng** khi trang đang bị chiếm quyền.

Sau khi đăng nhập hoặc thay đổi mức quyền, cần quản lý vòng đời session an toàn, đổi session identifier khi thích hợp, hết hạn và thu hồi phiên khi đăng xuất hoặc có sự cố. BFF cũng phải kiểm tra quyền ở server; không được xem việc browser gọi được endpoint BFF là bằng chứng người dùng được phép thao tác với mọi dữ liệu.

### 3.5. Ứng dụng di động cũng thường là public client

Ứng dụng cài trên điện thoại có thể được phân phối qua cửa hàng ứng dụng, nhưng người dùng vẫn kiểm soát thiết bị và có thể phân tích gói cài đặt. Vì vậy không nhúng `client_secret` hoặc khóa phát hành token vào ứng dụng di động với kỳ vọng giữ bí mật. Với OAuth, ứng dụng native thường dùng Authorization Code Flow với PKCE qua **trình duyệt hệ thống hoặc external user-agent**, thay vì tự dựng một vùng đăng nhập nhúng để thu thập mật khẩu.

Sau khi xác thực, redirect về ứng dụng cần được ràng buộc với ứng dụng đã đăng ký, ví dụ qua claimed HTTPS link hoặc custom URI scheme được cấu hình chặt chẽ. Token và khóa cục bộ nên dùng vùng lưu trữ bảo vệ do hệ điều hành cung cấp khi phù hợp; không ghi refresh token vào file cấu hình hoặc vùng lưu trữ văn bản thuần. Thiết bị bị root/jailbreak hoặc có malware vẫn có thể làm suy yếu các bảo vệ này, nên cần giới hạn quyền, thời hạn token và cơ chế thu hồi.

## 4. Ứng dụng máy chủ là một miền tin cậy riêng

Ứng dụng chạy ở backend có thể giữ credential bí mật tốt hơn browser, nhưng chỉ khi credential được quản lý đúng cách. Máy chủ có thể hoạt động như:

- **Confidential OAuth client:** giữ credential và trao đổi authorization code hoặc xin token theo luồng được cho phép.
- **BFF:** duy trì phiên browser và gọi các API thay mặt người dùng.
- **Resource server:** nhận access token, xác minh và bảo vệ tài nguyên.
- **Workload/service client:** gọi dịch vụ khác bằng danh tính của chính workload hoặc bằng quyền được ủy quyền.

Một tiến trình có thể có nhiều vai trò, nhưng không nên dùng chung một credential hoặc token rộng quyền cho tất cả các vai trò.

### 4.1. Phân biệt danh tính người dùng và danh tính ứng dụng

Khi backend gọi service thanh toán, service đích cần biết request đại diện cho ai:

- **Ứng dụng đang tự gọi:** backend sử dụng danh tính workload/client của chính nó. OAuth Client Credentials là một ví dụ luồng cấp quyền cho ứng dụng, không có người dùng cuối làm chủ thể trực tiếp.
- **Ứng dụng gọi thay người dùng:** backend sử dụng cơ chế ủy quyền/delegation được hệ thống hỗ trợ để chuyển tiếp quyền người dùng trong phạm vi phù hợp. Token có thể chứa chủ thể người dùng cùng thông tin client/actor tùy hồ sơ token.

Không tự suy ra danh tính người dùng từ một header như `X-User-Id` do browser gửi. Nếu một gateway hoặc proxy được phép thiết lập header danh tính, phải có ranh giới mạng và xác thực rõ ràng: loại bỏ header do client tự gửi, chỉ chấp nhận giá trị do thành phần tin cậy tạo và bảo vệ đường truyền giữa các thành phần.

### 4.2. Access token dành cho ai?

Access token phải được cấp cho resource server dự kiến. Claim `aud` xác định audience, còn `iss` xác định issuer. Mỗi API phải kiểm tra token dành cho chính nó theo hợp đồng và chính sách đã cấu hình.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Token ví dụ chỉ minh họa claims, không phải token có chữ ký thực. Nếu billing API nhận token có audience dành cho payment API, nó phải từ chối dù chữ ký có thể hợp lệ. Nếu một token có nhiều audience theo hợp đồng, từng resource server phải xác minh rằng chính nó nằm trong tập audience được phép và token đó thực sự được phát hành cho mục đích tương ứng.

**Không dùng ID token thay access token.** ID token của OpenID Connect được phát hành cho client để cung cấp thông tin về lần xác thực; audience của nó thường là client. Access token dành cho resource server để truy cập API. Đọc được `sub` hoặc thấy chữ ký hợp lệ không làm hai loại token trở thành tương đương.

### 4.3. Xác minh token tại mỗi service

Một resource server nên kiểm tra tối thiểu các nội dung theo hồ sơ token mà nó chấp nhận:

1. Chữ ký/MAC được xác minh bằng khóa thuộc issuer đã cấu hình tin cậy và thuật toán nằm trong allowlist.
2. `iss` đúng issuer được chấp nhận.
3. `aud` bao gồm resource server hiện tại và đúng mục đích.
4. `exp`, `nbf` và các giới hạn thời gian khác được kiểm tra theo chính sách.
5. Loại token và cấu trúc claims đúng hợp đồng; không nhận ID token như access token.
6. Scope/permission đáp ứng hành động được yêu cầu.
7. Quyền trên đối tượng cụ thể, tenant, trạng thái và ngữ cảnh được kiểm tra ở nơi thực thi.

JWT có chữ ký hợp lệ không nhất thiết phản ánh quyền hiện tại: role có thể đã bị thu hồi, tài khoản có thể bị khóa hoặc tenant có thể đã thay đổi. Với quyết định nhạy cảm, cần tra cứu trạng thái/chính sách hiện hành hoặc dùng TTL và cơ chế thu hồi phù hợp.

## 5. Ranh giới giữa API Gateway và các service phía sau

API gateway thường đảm nhiệm định tuyến, xác thực ban đầu, giới hạn lưu lượng, quan sát và một số chính sách dùng chung. Nó giúp giảm bề mặt tiếp xúc trực tiếp của service, nhưng không nên trở thành lý do để mọi service tin tuyệt đối request nội bộ.

### 5.1. Vì sao không nên chỉ xác minh ở gateway?

- Một service có thể bị truy cập qua đường nội bộ khác, job nền, message consumer hoặc endpoint quản trị.
- Lỗi cấu hình mạng có thể làm lộ service ra ngoài dự kiến.
- Token có thể được gửi nhầm audience hoặc chứa scope không phù hợp với service đích.
- Gateway có thể chuyển tiếp header do client giả mạo nếu không loại bỏ và tạo lại header đáng tin.
- Quyền trên một tài nguyên cụ thể thường chỉ service sở hữu dữ liệu mới có đủ thông tin để quyết định chính xác.

Vì vậy, gateway có thể xác minh sớm để chặn request sai, còn resource server vẫn cần xác minh danh tính/token và thực thi chính sách thuộc trách nhiệm của nó. Có thể dùng xác thực workload giữa các service, mTLS, network policy và token có audience/scope riêng để giảm khả năng một service bị xâm nhập lan sang toàn hệ thống.

### 5.2. Không dùng một token rộng quyền cho mọi service

Giả sử backend có một access token `aud=all-internal-services` với quyền đọc hóa đơn, sửa thông tin khách hàng và tạo thanh toán. Nếu token bị lộ ở một service, tác động có thể lan sang mọi API chấp nhận nó.

Thiết kế an toàn hơn là:

- Cấp token với audience dành cho service cần gọi.
- Chỉ cấp scope/permission tối thiểu cho tác vụ.
- Giới hạn thời hạn token và quyền của workload.
- Tách credential giữa môi trường và giữa các workload.
- Không ghi token vào log, trace, URL hoặc message không cần thiết.

### 5.3. Token forwarding và ủy quyền qua nhiều service

Một API nhận access token của người dùng rồi chuyển nguyên token đó tới nhiều service phía sau có thể vô tình mở rộng phạm vi sử dụng token. Service nhận tiếp theo có thể không phải audience dự kiến, hoặc có thể sử dụng quyền rộng hơn tác vụ hiện tại.

Khi service A cần gọi service B:

1. Xác định request là hành động của chính A hay là hành động được ủy quyền thay người dùng.
2. Dùng credential của A cho trường hợp workload tự gọi.
3. Với delegation, dùng cơ chế được authorization server hỗ trợ, chẳng hạn OAuth Token Exchange khi hệ thống triển khai hồ sơ phù hợp, để nhận token dành cho B và giới hạn quyền theo tác vụ.
4. B xác minh issuer, audience, thời hạn, loại token, client/actor và quyền cần thiết.

Không biến header hoặc claim do service trước tự khai báo thành bằng chứng độc lập. Nếu service A được phép khẳng định người dùng là Alice, service B phải biết vì sao A có quyền đưa ra khẳng định đó và đường truyền giữa hai service được bảo vệ như thế nào.

## 6. Các giao thức và cơ chế hỗ trợ ranh giới tin cậy

| Cơ chế | Ranh giới được hỗ trợ | Vai trò và giới hạn |
| --- | --- | --- |
| TLS | Browser–server, server–server | Bảo vệ kênh truyền và xác thực endpoint theo chứng chỉ; không thay thế xác thực người dùng hoặc phân quyền |
| OAuth 2.0 Authorization Code + PKCE | Public client–authorization server | Bảo vệ việc đổi authorization code; không làm public client giữ được client secret |
| OpenID Connect | Client–identity provider | Chuẩn hóa thông tin xác thực người dùng; ID token dành cho client, không phải access token cho API |
| JWT/JWS | Issuer–resource server | Mang claims và cung cấp kiểm tra toàn vẹn/xác thực nguồn theo khóa; không che giấu payload |
| JWE | Issuer–người nhận được phép giải mã | Bảo vệ bí mật nội dung; cần kiểm tra lớp xác thực nguồn riêng khi yêu cầu xác định issuer |
| OAuth Client Credentials | Workload/client–authorization server | Cấp quyền cho ứng dụng tự gọi API; không đại diện cho người dùng cuối |
| mTLS | Workload–workload hoặc client–server | Xác thực bằng chứng chỉ hai chiều và bảo vệ kênh; quản lý vòng đời chứng chỉ vẫn là điều kiện bắt buộc |
| DPoP / token ràng buộc người gửi | Client–resource server | Giảm khả năng dùng token bị đánh cắp ở nơi khác; không bảo vệ khỏi mã độc có thể sử dụng khóa trên chính client |
| OAuth Token Exchange | Service–authorization server–service đích | Hỗ trợ đổi token/ủy quyền cho audience và phạm vi mới theo chính sách; không tự động làm mọi delegation an toàn |

Các cơ chế trên có thể kết hợp. Ví dụ, service dùng mTLS để xác thực workload ở tầng kết nối và access token JWT để mô tả quyền ở tầng ứng dụng. Hai lớp này trả lời các câu hỏi khác nhau.

## 7. Những khái niệm trình duyệt thường bị nhầm với bảo mật API

### 7.1. CORS không phải xác thực và không phải phân quyền

**Cross-Origin Resource Sharing (CORS)** là cơ chế browser dùng để quyết định JavaScript từ một origin có được phép đọc phản hồi cross-origin hay không, dựa trên các response header của server và quy tắc trình duyệt.

CORS không chứng minh người gọi là ai, không xác minh JWT và không thay thế kiểm tra quyền tại API. Client ngoài browser như script, ứng dụng di động hoặc công cụ dòng lệnh không bị ràng buộc bởi cùng chính sách CORS của browser.

Khi dùng credential/cookie cross-origin, cấu hình origin và credential phải chặt chẽ; không phản chiếu tùy tiện mọi origin được gửi lên. CORS cấu hình quá rộng có thể làm lộ phản hồi cho website không mong muốn, nhưng cấu hình CORS đúng vẫn không thay thế xác thực và phân quyền.

### 7.2. CSRF và XSS là hai rủi ro khác nhau

| Rủi ro | Cách tấn công | Biện pháp trọng tâm |
| --- | --- | --- |
| **CSRF** | Website khác khiến browser gửi request mang cookie phiên tự động tới ứng dụng | SameSite phù hợp, anti-CSRF token, kiểm tra Origin/Referer, xác nhận thao tác nhạy cảm |
| **XSS** | Mã độc chạy trong origin hợp lệ và thao tác với trang/phiên của người dùng | Output encoding, API/DOM an toàn, CSP, kiểm soát dependency và giảm quyền JavaScript |

`HttpOnly` giúp JavaScript không đọc trực tiếp cookie nhưng không ngăn mã XSS gửi request từ trang đang bị chiếm quyền. Ngược lại, access token chỉ được JavaScript chủ động thêm vào header thường ít chịu kiểu CSRF dựa trên cookie tự động, nhưng nếu token có thể bị XSS đọc thì kẻ tấn công có thể đánh cắp và sử dụng nó.

## 8. Các tình huống sai ranh giới tin cậy

### Tình huống A — Tin dữ liệu phân quyền từ frontend

Frontend gửi `{ "userId": "alice", "role": "admin" }` cùng request cập nhật hồ sơ. Nếu backend tin trực tiếp các trường này, người dùng có thể sửa request để tự nhận vai trò quản trị. Backend phải lấy danh tính từ ngữ cảnh xác thực đã kiểm tra và lấy quyền từ nguồn/chính sách đáng tin; dữ liệu client gửi chỉ là dữ liệu yêu cầu, không phải bằng chứng quyền.

### Tình huống B — Đặt client secret trong JavaScript

Một SPA gửi `client_secret` khi đổi authorization code vì nghĩ mã nguồn đã được minify. Người dùng có thể tải bundle và đọc secret. Đây là lỗi đặt bí mật qua ranh giới server–browser. Dùng public client với PKCE hoặc chuyển phần giữ credential và đổi code sang BFF/confidential client.

### Tình huống C — API tin token chỉ vì gateway đã xác thực

Gateway xác minh chữ ký nhưng chuyển tiếp token có audience dành cho API khác tới service hóa đơn. Service hóa đơn không kiểm tra `aud` và xử lý request. Đây là lỗi token substitution/confused deputy. Resource server cần kiểm tra audience và quyền theo chính sách của chính nó.

### Tình huống D — Dùng ID token gọi API

Frontend nhận ID token có chữ ký hợp lệ từ IdP và gửi tới payment API. Payment API chấp nhận vì thấy `sub`. Nhưng ID token được phát hành cho client, không nhất thiết dành cho payment API. API phải yêu cầu access token đúng audience và hồ sơ token được hỗ trợ.

### Tình huống E — Service tin header danh tính từ request nội bộ

Một service nhận `X-User-Id: admin` và tin đây là header do gateway thêm. Nếu gateway không xóa header client tự gửi, kẻ tấn công có thể tự chọn danh tính. Phải thiết lập ranh giới rõ: gateway loại bỏ header không đáng tin, tạo lại giá trị từ danh tính đã xác thực, bảo vệ kênh tới backend và giới hạn backend chỉ nhận request từ gateway/workload được phép.

### Tình huống F — Chuyển tiếp token người dùng tới mọi service

Backend nhận access token dành cho API A, rồi chuyển nguyên token tới service B và C. Các service này cùng chấp nhận một audience rộng và scope lớn. Khi một service bị xâm nhập, token có thể bị dùng ở nhiều nơi. Cần token audience riêng, scope tối thiểu và delegation/token exchange khi cần đại diện người dùng ở service tiếp theo.

### Tình huống G — Tin mạng nội bộ

Service B bỏ qua xác thực vì chỉ nhận request từ subnet nội bộ. Một workload bị xâm nhập hoặc cấu hình mạng sai có thể gọi trực tiếp B. Ranh giới mạng là một lớp kiểm soát hữu ích, nhưng không thay thế danh tính workload, xác minh token và phân quyền.

### Tình huống H — Token còn chữ ký hợp lệ sau khi người dùng bị khóa

Người dùng bị khóa tài khoản nhưng JWT đã phát hành vẫn còn hạn. Chữ ký vẫn đúng vì nội dung token chưa thay đổi. Resource server cần chính sách về TTL, trạng thái tài khoản, thu hồi, introspection hoặc danh sách từ chối cho trường hợp cần vô hiệu hóa nhanh.

## 9. Quy trình thiết kế và rà soát ranh giới tin cậy

Với mỗi luồng dữ liệu, hãy xác định thành phần gửi, thành phần nhận, dữ liệu đi qua, danh tính được khẳng định và hành động cuối cùng. Sau đó trả lời các câu hỏi sau:

1. **Nguồn gốc:** issuer hoặc workload nào được phép gửi? Khóa, chứng chỉ hoặc credential nào chứng minh danh tính đó?
2. **Đối tượng nhận:** token có đúng `aud` và loại token cho thành phần đang xử lý không?
3. **Toàn vẹn:** chữ ký/MAC hoặc cơ chế bảo vệ thông điệp có bao phủ phần dữ liệu cần tin không?
4. **Bí mật:** dữ liệu nào được phép xuất hiện ở browser, log, URL, trace và message queue? Có cần JWE hoặc mã hóa ở tầng lưu trữ không?
5. **Quyền:** scope, tenant, quyền sở hữu và trạng thái hiện tại có cho phép hành động này không?
6. **Ủy quyền:** request đại diện cho ứng dụng hay người dùng? Có đang chuyển tiếp quyền vượt mục đích ban đầu không?
7. **Chống lạm dụng:** token có thể bị đánh cắp, phát lại hoặc dùng ở service khác không? TTL, sender constraint và thu hồi được thiết kế ra sao?
8. **Bảo vệ client:** browser có giữ bí mật không cần thiết? Cookie có CSRF protection? Ứng dụng có giảm thiểu XSS và token exposure?
9. **Kiểm soát nội bộ:** service có xác minh độc lập? Gateway có loại bỏ header giả mạo? Network policy và workload identity có phù hợp?
10. **Quan sát:** log có ghi lý do từ chối mà không ghi token, secret hoặc dữ liệu nhạy cảm không?

### Bảng kiểm theo từng ranh giới

| Luồng | Bằng chứng cần xác minh | Quyết định cần thực hiện |
| --- | --- | --- |
| Browser → BFF | Session cookie hợp lệ, CSRF/origin theo chính sách, dữ liệu đầu vào | Người dùng có được thực hiện hành động qua BFF không? |
| Browser → API | Access token đúng issuer, audience, thời hạn, loại token và quyền | API này có chấp nhận token và cho phép hành động không? |
| BFF → API | Danh tính BFF, access token dành cho API, delegation nếu đại diện user | BFF được phép gọi API này với quyền nào? |
| Gateway → Service | Danh tính gateway/workload, token đúng audience, header đã chuẩn hóa | Service có chấp nhận request và có quyền truy cập tài nguyên không? |
| Service A → Service B | Danh tính A, token/ủy quyền dành cho B, phạm vi tối thiểu | B có thực thi đúng tác vụ A được phép yêu cầu không? |
| Service → đối tác | Credential/khóa của tích hợp, audience và hợp đồng webhook/API | Đối tác có đúng danh tính và chỉ nhận dữ liệu được phép không? |

## 10. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Có thể giữ OAuth client secret an toàn trong JavaScript frontend bằng cách minify không? | **Không.** Mã và cấu hình gửi tới browser có thể bị xem; frontend là public client. |
| PKCE có thay thế việc xác minh access token tại API không? | **Không.** PKCE bảo vệ việc đổi authorization code, API vẫn phải xác minh access token. |
| CORS có ngăn một script ngoài browser hoặc người dùng tự gửi request tới API không? | **Không.** CORS là cơ chế browser kiểm soát việc đọc phản hồi cross-origin. |
| JWT có audience dành cho service A có mặc nhiên hợp lệ tại service B không? | **Không.** B phải kiểm tra audience và hồ sơ token của chính B. |
| API gateway đã xác minh token thì service phía sau có thể bỏ qua mọi kiểm tra không? | **Không.** Service cần bảo vệ tài nguyên và thực thi quyền thuộc phạm vi của nó. |
| Cookie HttpOnly có ngăn CSRF không? | **Không.** HttpOnly ngăn JavaScript đọc cookie; CSRF cần biện pháp riêng. |
| mTLS có tự quyết định người dùng được đọc hóa đơn nào không? | **Không.** mTLS xác thực workload/endpoint; quyền trên tài nguyên vẫn cần được đánh giá. |
| Access token bị đánh cắp nhưng còn hạn có thể bị sử dụng lại không? | **Có**, nếu token là bearer và không có cơ chế ràng buộc/thu hồi phù hợp. |
| Service A có nên chuyển nguyên token của người dùng tới mọi service không? | **Không mặc định.** Cần kiểm tra audience, quyền và dùng delegation/token exchange khi phù hợp. |

## 11. Những nguyên tắc cần ghi nhớ

- Browser là miền do người dùng kiểm soát; không nhúng bí mật và không tin dữ liệu phân quyền do frontend tự khai báo.
- Dùng Authorization Code Flow với PKCE cho public client; dùng BFF khi muốn giữ access/refresh token ở server và quản lý session qua cookie an toàn.
- ID token phục vụ client xác nhận đăng nhập; access token dành cho resource server. Luôn kiểm tra issuer, audience, thời hạn, loại token và quyền.
- Mỗi API/service phải thực thi chính sách tại ranh giới tài nguyên của mình. Gateway và mạng nội bộ là lớp kiểm soát bổ sung.
- Phân biệt danh tính người dùng với danh tính workload; phân biệt ứng dụng tự gọi với ứng dụng gọi thay người dùng.
- Dùng audience và scope hẹp, token ngắn hạn, quản lý khóa/credential riêng cho từng workload và cơ chế delegation rõ ràng.
- CORS, TLS, chữ ký JWT, mTLS, CSRF protection và phân quyền giải quyết các vấn đề khác nhau; không cơ chế đơn lẻ nào thay thế toàn bộ các lớp còn lại.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 6749 – The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 – Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 – OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8705 – OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8693 – OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
