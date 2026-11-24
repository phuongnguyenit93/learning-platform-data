# Redirect sau logout

Một người dùng đăng nhập vào ứng dụng quản lý đơn hàng bằng **OpenID Connect (OIDC)**. Khi bấm **Đăng xuất**, ứng dụng xóa session của mình rồi chuyển trình duyệt về **https://app.example.org/signed-out**. Màn hình báo “Bạn đã đăng xuất”, nhưng người dùng mở lại nút **Đăng nhập** và lập tức được xác thực qua Identity Provider mà không cần nhập mật khẩu. Điều gì đã xảy ra?

Ứng dụng đã kết thúc **phiên cục bộ của Relying Party (RP)**, nhưng **phiên đăng nhập tại OpenID Provider (OP)** có thể vẫn còn. Ngược lại, một redirect từ trang logout của OP về ứng dụng **không chứng minh** mọi access token, refresh token hay phiên ở các ứng dụng khác đã bị thu hồi. Nếu redirect đích còn được lấy trực tiếp từ tham số **returnUrl** do người dùng gửi, hệ thống thậm chí có thể trở thành **open redirect** phục vụ phishing.

**Redirect sau logout** là bước điều hướng trình duyệt trong quy trình kết thúc phiên, **không phải bản thân việc thu hồi phiên/token**. Một triển khai đúng phải trả lời ba câu hỏi độc lập:

1. **Đã kết thúc trạng thái nào?** RP session, OP session, token/grant hay các phiên khác?
2. **Ai được phép quyết định đích chuyển hướng?** Chỉ các URI được cấu hình/đăng ký và xác minh đáng tin.
3. **Khi quay về, ứng dụng tin được điều gì?** Chỉ một callback có liên kết giao dịch phù hợp; nó không tự chứng minh mọi token và phiên toàn hệ thống đã hết hiệu lực.

Bài thuộc chương **Logout** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là OIDC **RP-Initiated Logout 1.0**, thiết kế **post_logout_redirect_uri**, **id_token_hint**, **state**, chống open redirect, logout CSRF, cùng quan hệ giữa logout và vòng đời JWT, opaque access token, refresh token, scope, audience, introspection, revocation và phòng chống token bị đánh cắp/phát lại.

Sau bài này, bạn có thể phân biệt redirect của OAuth login với redirect sau logout, thiết kế cả luồng local logout và OP logout, xác minh callback, xây dựng quy tắc allowlist, xử lý lỗi khi OP không trả về, và kiểm thử các ranh giới bảo mật từ trình duyệt tới Resource Server.

## 1. Redirect sau logout thực sự là thao tác gì?

**Redirect** là hành vi hướng trình duyệt từ một địa chỉ sang địa chỉ khác, thường qua HTTP 302/303 hoặc điều hướng phía client. Trong logout, nó thường phục vụ một trong hai mục đích:

- **Điều hướng nội bộ sau local logout:** sau khi xóa RP session, ứng dụng đưa người dùng về trang “Đã đăng xuất” hoặc trang công khai.
- **Điều hướng liên hệ với OP:** RP đưa trình duyệt tới **end_session_endpoint** đã xác định từ OP tin cậy; OP xử lý phiên của mình rồi **có thể** đưa trình duyệt trở lại một **post_logout_redirect_uri** đã đăng ký.

| Thành phần | Đối tượng nắm quyền | Chức năng |
|---|---|---|
| **RP/application logout endpoint** | Ứng dụng của bạn | Kết thúc RP session, dọn credential và trạng thái local |
| **OP end_session_endpoint** | Nhà cung cấp danh tính OIDC | Xử lý yêu cầu kết thúc phiên ở OP theo giao thức/chính sách |
| **post_logout_redirect_uri** | Đích RP đã đăng ký với OP | Trang RP nhận trình duyệt sau OP logout |
| **Authorization redirect_uri** | Callback đăng nhập/ủy quyền OAuth của RP | Nhận authorization code/error khi hoàn tất authorize; **khác mục đích** |
| **API/Resource Server** | Dịch vụ bảo vệ tài nguyên | Kiểm access token và quyền của từng request; không tự logout chỉ nhờ browser redirect |

**Một redirect đúng URL không có nghĩa session đã được xóa.** Chẳng hạn, response 302 có thể đã được gửi trước khi transaction xóa server session commit; nếu thao tác xóa sau đó thất bại, người dùng nhìn thấy trang đã đăng xuất nhưng phiên vẫn có hiệu lực.

Ngược lại, một lỗi mạng chặn redirect sau logout **không nhất thiết làm mất tác dụng của việc xóa RP session** đã hoàn tất. Cần tách **security state transition** khỏi **navigation UX**.

## 2. Phân biệt bốn khái niệm thường bị gọi chung là logout

| Hành động | Kết quả trực tiếp | Không tự bảo đảm |
|---|---|---|
| **Local/RP logout** | Session cookie và trạng thái xác thực của ứng dụng được vô hiệu | OP SSO session chấm dứt |
| **OP logout** | OP thực hiện chính sách kết thúc OP session | Mọi RP khác đã dọn session nếu không có cơ chế propagation |
| **OAuth token revocation** | AS vô hiệu hóa token/grant được chỉ định theo policy | JWT access token cũ bị mọi API từ chối ngay nếu chỉ validate offline |
| **Federated/Single Logout (SLO)** | Phối hợp thông báo logout giữa nhiều RPs/OP | Delivery hoàn hảo tới mọi client, browser, thiết bị khi thiếu kiểm soát trạng thái |

**Authentication session** và **OAuth authorization grant** là hai đối tượng khác nhau. Người dùng có thể hết phiên SSO ở OP nhưng refresh token của một client vẫn được AS chấp nhận theo chính sách, hoặc refresh token đã bị revoke nhưng phiên đăng nhập browser tại OP vẫn tồn tại.

OIDC bổ sung **ID token** và giao thức logout phối hợp với OP. Nhưng **ID token không phải access token để gọi API**; gửi nó trong một yêu cầu logout làm **id_token_hint** không biến nó thành credential truy cập Resource Server.

### Ví dụ thực tế

Người dùng đã mở **Shop Web** và **Reports Dashboard**, cả hai đăng nhập qua cùng một OP. Bấm logout ở Shop Web có thể kết thúc session Shop Web. Nếu Shop Web tiếp tục gọi **RP-Initiated Logout**, OP session có thể bị kết thúc. Còn Reports Dashboard có đóng phiên đang mở không phụ thuộc **Front-Channel Logout**, **Back-Channel Logout**, session management hoặc policy riêng, chứ không tự động vì Shop Web vừa được redirect về trang signed-out.

## 3. Luồng OIDC RP-Initiated Logout end-to-end

OIDC **RP-Initiated Logout 1.0** mô tả cách RP yêu cầu OP kết thúc phiên và, khi hợp lệ, chuyển trình duyệt về một URI của RP đã được đăng ký.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant RP as Ứng dụng / Relying Party
    participant OP as OpenID Provider
    participant RS as Resource Server
    U->>RP: Bấm Đăng xuất
    RP->>RP: Kiểm session/CSRF theo policy
    RP->>RP: Vô hiệu RP session và token local theo chính sách
    RP->>RP: Tạo logout transaction + state ngẫu nhiên
    RP-->>B: Điều hướng đến OP end_session_endpoint
    B->>OP: id_token_hint, post_logout_redirect_uri, state...
    OP->>OP: Kiểm request và registered redirect URI
    OP->>U: Xử lý kết thúc OP session (có thể hỏi xác nhận)
    alt OP cho phép chuyển về RP
        OP-->>B: 302 đến registered post_logout_redirect_uri + state
        B->>RP: GET /signed-out/callback?state=...
        RP->>RP: Kiểm state và transaction, không khôi phục session
        RP-->>U: Trang thông báo đã đăng xuất
    else OP không redirect / người dùng hủy
        OP-->>U: OP UI hoặc lỗi/không hoàn tất
        Note over RP,RS: RP local session có thể đã kết thúc
    end
~~~

**Sơ đồ là một thiết kế RP-first minh họa, không phải mọi OP bắt buộc thực hiện từng bước y hệt.** OP có thể yêu cầu tương tác, từ chối redirect, hoặc không hỗ trợ RP-Initiated Logout. RP cần tự xử lý lifecycle phiên cục bộ và không phụ thuộc vào một redirect mà mình không kiểm soát.

**Tách hai thành công:** RP session đã bị vô hiệu cục bộ; OP session đã được OP xử lý theo điều kiện riêng. Không gộp hai trạng thái vào một boolean **logout=true** thiếu ngữ cảnh.

## 4. Đọc đúng các tham số của logout request

Ví dụ RP yêu cầu OP logout:

~~~http
GET /oidc/logout?id_token_hint=<previous-id-token>&post_logout_redirect_uri=https%3A%2F%2Fapp.example.org%2Fsigned-out%2Fcallback&state=<opaque-random-state> HTTP/1.1
Host: login.example.org
~~~

Đường dẫn **/oidc/logout** ở đây chỉ là ví dụ. Endpoint thực phải lấy từ **end_session_endpoint** do OP đáng tin cung cấp; không suy ra bằng cách tự nối **/logout** sau issuer URL.

| Tham số | Vai trò | Lưu ý bảo mật |
|---|---|---|
| **id_token_hint** | Gợi ý về ID token OP đã cấp cho RP trong phiên liên quan | **RECOMMENDED** theo OIDC RP-Initiated Logout; phải thuộc đúng OP/client; không log token |
| **post_logout_redirect_uri** | Đích browser trở lại RP sau OP logout | Phải khớp **registered post-logout URI** và được OP xác minh |
| **state** | Giá trị RP dùng đối chiếu giao dịch logout khi browser trở lại | Không phải bằng chứng OP đã revoke token; phải kiểm trên callback |
| **client_id** | Giúp OP nhận diện RP, đặc biệt khi thiếu id_token_hint trong tình huống được hỗ trợ | Phải thuộc client registration; không dùng một client_id tự khai để vượt kiểm URI |
| **logout_hint** | Gợi ý phiên/người dùng cho OP, tùy profile | Không phải mật khẩu; tránh gửi PII tùy tiện |
| **ui_locales** | Gợi ý ngôn ngữ UI của OP | Không ảnh hưởng quyền đăng xuất hoặc validate redirect |

**id_token_hint không phải tham số bắt buộc tuyệt đối trong mọi triển khai**, nhưng được khuyến nghị; khi không có hoặc không xác định được RP hợp lệ, OP có thể cần cách xác minh khác hoặc yêu cầu người dùng xác nhận. **Không được thực hiện post-logout redirection nếu OP không có căn cứ xác minh tính hợp lệ của RP đang yêu cầu** theo giao thức/chính sách.

**state phải được đưa lại nguyên giá trị khi OP redirect về RP** nếu được cung cấp trong request. RP cần có cách kiểm state ngay cả khi đã xóa login session, chẳng hạn một **logout transaction lưu server-side có TTL** và cookie đối chiếu ngắn hạn.

## 5. post_logout_redirect_uri khác authorization redirect_uri

OIDC và OAuth có **hai loại callback** với ý nghĩa trái ngược:

~~~text
Authorization Code + PKCE:
  /authorize  -> redirect_uri -> /oauth/callback
  mang authorization code + state hoặc authorization error

RP-Initiated Logout:
  end_session_endpoint -> post_logout_redirect_uri -> /signed-out/callback
  mang state để đối chiếu giao dịch logout nếu được gửi
~~~

| Câu hỏi | Authorization redirect URI | Post-logout redirect URI |
|---|---|---|
| Được dùng khi nào? | Hoàn thành authorization request | OP xử lý logout và chuyển về RP |
| Thường nhận gì? | Authorization code/error và state | State nếu được dùng |
| Có nên xử lý code tại đây? | Có, theo flow/PKCE | **Không** |
| Có khởi tạo phiên đăng nhập không? | Có thể sau token exchange và ID token validation | **Không bao giờ chỉ vì callback logout hợp lệ** |
| Có đăng ký riêng với provider không? | Có, theo client registration | Có, qua **post_logout_redirect_uris** hoặc tương đương của OP |

Không suy rằng URI đăng ký làm **redirect_uri** để login tự động được phép làm **post_logout_redirect_uri**; đây là hai allowlists/mục đích khác nhau. Có OP cho phép cấu hình tương tự qua portal, nhưng **contract vẫn phải được kiểm riêng**.

Một RP có thể đăng ký:

~~~text
login redirect:
  https://app.example.org/oauth/callback

post-logout redirect:
  https://app.example.org/signed-out/callback
~~~

Giữ callback logout **tách khỏi endpoint chấp nhận authorization code** để giảm lỗi xử lý nhầm giao thức, login/logout CSRF và nhầm state.

## 6. Lấy end_session_endpoint từ nguồn nào?

Một ứng dụng đa IdP có thể gặp các OP có đường logout khác nhau. Không nên hard-code URL kiểu:

~~~text
issuer + "/logout"
~~~

Trong OIDC, RP có thể đọc **OP metadata** từ nguồn discovery/configuration đáng tin, ví dụ chứa:

~~~json
{
  "issuer": "https://login.example.org",
  "authorization_endpoint": "https://login.example.org/connect/authorize",
  "token_endpoint": "https://login.example.org/connect/token",
  "end_session_endpoint": "https://login.example.org/connect/endsession"
}
~~~

JSON là **minh họa cấu hình**, không phải metadata của dịch vụ cụ thể. RP phải xác minh **issuer** và tính nhất quán metadata theo quy tắc discovery, TLS, các IdP được cho phép và chính sách mạng. Không chấp nhận một URL end_session_endpoint do người dùng gắn vào **returnUrl**, **idp** hoặc JWT chưa xác minh mà không đối chiếu allowlist.

### Vì sao cấu hình issuer quan trọng?

Giả sử người dùng có phiên tại OP-A, nhưng ứng dụng điều hướng tới **end_session_endpoint của OP-B** vì đọc nhầm provider từ query. OP-B có thể logout một phiên không liên quan hoặc redirect về sai RP. Trường hợp tệ hơn, một endpoint do attacker kiểm soát có thể thu nhận **id_token_hint** cùng thông tin phiên.

**Logout request phải gắn với issuer/client đã tạo phiên thật**, không chỉ với hostname mà caller yêu cầu lúc logout. Với multi-tenant/multi-issuer, nên lưu **trusted issuer ID và client registration** trong session/transaction trước khi xóa.

## 7. Kiểm tra redirect URI chính xác để chặn open redirect

**Open redirect** xảy ra khi một ứng dụng cho phép caller chọn đích chuyển hướng tùy ý nhưng hiển thị link dưới domain đáng tin. Kẻ tấn công có thể phát tán:

~~~text
https://app.example.org/logout?returnUrl=https://evil.example/phish
~~~

Nếu ứng dụng logout rồi redirect thẳng sang **evil.example**, nạn nhân thấy URL bắt đầu trên domain hợp pháp và có thể bị dụ vào trang giả mạo. Vấn đề càng nguy hiểm nếu app chuyển tiếp **state, token, ID token hoặc thông tin tài khoản** trong URL.

### Cách sai: kiểm prefix

~~~java
// SAI: domain "app.example.org.evil.test" vẫn bắt đầu bằng prefix này.
if (returnUrl.startsWith("https://app.example.org")) {
    response.sendRedirect(returnUrl);
}
~~~

Các chuỗi gây nhầm lẫn:

~~~text
https://app.example.org.evil.test/signed-out
https://app.example.org@evil.test/signed-out
//evil.test/phish
%2F%2Fevil.test%2Fphish
https://app.example.org/signed-out%0d%0aLocation:%20https://evil.test/
~~~

Với ứng dụng, cần **không phản chiếu returnUrl bất kỳ**; tốt nhất là chuyển hướng tới một **URI cố định cấu hình server-side**. Với OP, **post_logout_redirect_uri phải được đối chiếu với danh sách URI đã đăng ký của đúng RP**, tránh wildcard domain, suffix match, prefix match, open redirect qua query tham số.

### Mẫu kiểm an toàn

~~~text
registered_post_logout_uris:
  - https://app.example.org/signed-out/callback

requested URI:
  https://app.example.org/signed-out/callback

decision:
  accept only if contract-equivalent/exact registered URI
  belongs to the authenticated/validated RP
~~~

Đây là mô tả policy. Với redirect liên quan OAuth/OIDC, nên ưu tiên **exact string matching** theo profile/registration; nếu thư viện có canonicalization, phải hiểu quy tắc và kiểm thử các biểu diễn bất thường. Không tự “chuẩn hóa” URL attacker thành một URI được phép rồi chuyển hướng mà không có đánh giá an ninh.

## 8. State trong logout để ràng buộc đúng giao dịch quay về

Khi RP gửi **state** tới OP logout endpoint, OP chuyển lại state tại post-logout redirect. RP dùng nó để nhận diện browser callback là kết quả điều hướng liên quan **logout transaction đã khởi tạo**.

Ví dụ:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/signed-out/callback?state=<opaque-random-state>
~~~

**Không dùng state cố định** như **logout**, email, client_id, userId hoặc timestamp dễ đoán. Có thể dùng giá trị **CSPRNG ít nhất đủ entropy** và lưu **hash/HMAC** phía server; ràng buộc với context cần thiết.

~~~text
logout_transaction:
  state_hash: HMAC(server_key, opaque_state)
  issuer_ref: op-main
  client_id: shop-web
  expected_post_logout_uri: https://app.example.org/signed-out/callback
  initiating_browser_binding: short-lived correlation cookie
  created_at: trusted timestamp
  expires_at: short TTL
  consumed: false
~~~

### Callback phải kiểm gì?

1. **state** tồn tại, đúng định dạng/kích thước và khớp transaction chưa dùng.
2. Transaction **chưa hết hạn**, không thuộc browser khác nếu ứng dụng áp dụng browser binding.
3. **Issuer và client** của transaction là OP/RP đã cấu hình trước logout.
4. Callback đang đi vào đúng **registered post-logout route**, không phải login callback.
5. Transaction được **consume một lần**; refresh hoặc phát lại callback không đổi trạng thái xác thực.
6. UI chỉ xác nhận mức kết quả **có thể chứng minh được**; không tự kết luận mọi tokens đã bị vô hiệu.

**State không phải chữ ký của OP.** Một callback chứa state đúng là bằng chứng tương quan với giao dịch RP đã tạo theo mô hình kiểm soát state, không tự bảo đảm OP đã xóa mọi session hoặc RS đã từ chối token. Không dùng kết quả callback để tạo phiên đăng nhập mới.

## 9. Xóa session trước redirect: giữ dữ liệu nào, xóa dữ liệu nào?

Một vấn đề thực tế: RP muốn xóa server session để logout, nhưng **id_token_hint** và dữ liệu tạo callback state có thể đang nằm trong chính session ấy. Nếu xóa quá sớm mà không giữ ngữ cảnh cần thiết, RP không dựng được logout request hoặc không kiểm callback. Nếu giữ toàn bộ session quá lâu, user vẫn có thể dùng API.

### Thiết kế RP-first hợp lý

1. Nhận thao tác logout có chủ đích, kiểm **RP session/CSRF** theo policy.
2. Từ session đã xác thực, lấy **issuer ID, client registration, ID token hint nếu có và các token references cần xử lý**.
3. Tạo **logout transaction độc lập với login session**, TTL ngắn, có state CSPRNG, browser binding và expected redirect.
4. **Vô hiệu RP session tại server**, thu hồi/xóa credential theo logout policy; không để request tiếp theo tái sử dụng session ID đã logout.
5. Xóa session cookie phía browser với **đúng name/path/domain/SameSite/Secure settings**.
6. Điều hướng browser đến **trusted OP end_session_endpoint** với tham số đã được cấu hình/encode.
7. Trên callback, kiểm transaction độc lập và hiển thị trang public; không khôi phục session cũ.

~~~mermaid
flowchart TD
    A["User POST /logout"] --> B{"Session/CSRF hợp lệ?"}
    B -->|Không| X["Reject hoặc xử lý đã logout theo contract"]
    B -->|Có| C["Snapshot issuer/client và ID token hint cần thiết"]
    C --> D["Tạo logout transaction độc lập, TTL ngắn"]
    D --> E["Invalidate RP session + dọn token theo policy"]
    E --> F{"OP hỗ trợ RP-Initiated Logout?"}
    F -->|Có| G["Redirect trusted end_session_endpoint"]
    F -->|Không| H["Hiển thị local signed-out page"]
    G --> I{"Có post-logout callback hợp lệ?"}
    I -->|Có| J["Validate state, consume, render public page"]
    I -->|Không| H
~~~

Thứ tự chi tiết có thể khác theo kiến trúc và chính sách, nhưng nguyên tắc là **không để session có hiệu lực chỉ vì đang chờ OP redirect**. Nếu RP đã invalidate session và sau đó OP logout thất bại, RP phải nói rõ **local logout hoàn tất nhưng OP session có thể còn**; không âm thầm khôi phục session.

## 10. Session cookie, cache trình duyệt và nút Back sau logout

Một redirect tới **/signed-out** không xóa cookie của RP hoặc dữ liệu private ở browser. Cần phân biệt:

- **Server-side session invalidation:** session ID không còn được RP chấp nhận, kể cả cookie cũ được gửi lại.
- **Cookie deletion:** response set cookie hết hạn với **đúng Path/Domain**; ưu tiên cookie **Secure, HttpOnly, SameSite** theo kiến trúc.
- **Access/refresh token cleanup:** nếu BFF lưu server-side, xóa và thu hồi theo policy; nếu app lưu token trong browser, có quy trình dọn lưu trữ tương ứng.
- **Browser cache và BFCache:** người dùng bấm Back có thể nhìn thấy snapshot trang trước đó, nhưng server phải **không cung cấp dữ liệu mới** nếu phiên đã hết.
- **Cross-tab state:** các tab khác có thể đang giữ UI hoặc in-flight requests; cần đồng bộ logout local khi có thể.

Ví dụ trả nội dung riêng tư:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: text/html; charset=utf-8
~~~

**Cache-Control: no-store** hỗ trợ hạn chế cache nội dung riêng tư, nhưng không thay thế server-side session validation và token revocation. **Clear-Site-Data** là một header có thể hữu ích ở một số browser để xóa dữ liệu theo origin, nhưng phải kiểm phạm vi hỗ trợ/hậu quả (xóa dữ liệu của các ứng dụng cùng origin) và không dùng mù quáng.

Nếu dùng **SPA**, cần dọn cache state, optimistic UI và token local ở các tab/worker theo kiến trúc. Các API vẫn phải xác minh token/phiên; không phụ thuộc vào việc JavaScript đã kịp xóa dữ liệu trong mọi tab.

## 11. RP session và OP session: redirect không bảo đảm Single Logout

Một OP có thể có session SSO tại **login.example.org**, trong khi hai RPs có hai cookie khác nhau:

~~~text
OP SSO session:
  login.example.org   -> op_session_1

RP sessions:
  shop.example.org    -> shop_session_9
  reports.example.org -> reports_session_7
~~~

Khi Shop RP khởi tạo logout:

| Mốc | Shop RP | OP | Reports RP |
|---|---|---|---|
| Trước logout | Session active | SSO active | Session active |
| Sau local logout Shop | Session invalid | Có thể active | Có thể active |
| Sau OP xử lý logout | Session invalid | SSO có thể bị kết thúc | **Không nhất thiết** invalid |
| Sau SLO propagation đáng tin | Session invalid | SSO ended | Có thể invalid nếu Reports RP nhận/xử lý logout |

**Một browser redirect chỉ đi qua luồng của browser và OP**, không tự gửi lệnh xóa session tới mọi RP. Nếu yêu cầu **Single Logout**, cần các cơ chế phối hợp và cách xử lý failure/retry riêng.

### Không nhầm SSO với quyền API

Kết thúc OP session có thể ngăn **silent login** ở lần tương tác sau, nhưng một bearer access token đã được phát vẫn có thể được RS chấp nhận nếu đúng issuer/audience/scope/exp và chưa bị revoke theo mô hình của hệ thống. **RP logout, OP logout và token revocation phải có tiêu chí thành công riêng**.

## 12. Front-Channel Logout và Back-Channel Logout khác redirect sau logout

OIDC có những cơ chế phối hợp logout khác nhau:

| Cơ chế | Kênh truyền | Mục đích | Giới hạn quan trọng |
|---|---|---|---|
| **RP-Initiated Logout** | Browser đi RP → OP, có thể quay về RP | RP yêu cầu OP kết thúc phiên và điều hướng | Không tự bảo đảm mọi RP đều nhận logout |
| **Front-Channel Logout** | Browser/iframe điều hướng tới logout URI của RPs | OP thông báo logout qua browser | Cookie third-party, iframe restrictions, trình duyệt bị đóng có thể cản trở |
| **Back-Channel Logout** | OP gửi request server-to-server cho RP | Thông báo logout độc lập browser bằng Logout Token | Phải kiểm chữ ký/claims/replay, định danh session và xử lý retry/độ trễ |
| **OAuth Token Revocation** | Client gọi AS revocation endpoint | Chấm dứt hiệu lực token/grant theo policy | Không tự xóa mọi browser sessions ở các RPs |

**post_logout_redirect_uri không phải frontchannel_logout_uri hay backchannel_logout_uri.** Một URI đón browser sau RP-Initiated Logout không được tái sử dụng làm endpoint nhận logout notification nếu không có hợp đồng giao thức và kiểm tra riêng.

Với **OIDC Back-Channel Logout 1.0**, OP có thể gửi **Logout Token** là một JWT theo profile. RP phải kiểm **issuer, audience, thời hạn/thời điểm phát hành, chữ ký, sự kiện logout, jti chống replay và sid/sub theo hợp đồng**; không dùng Logout Token như ID token đăng nhập hoặc access token API. Chỉ một callback browser có **state** không thay những kiểm tra server-to-server đó.

**Logout Token là token thông báo sự kiện**, khác **ID token** dùng làm id_token_hint và khác **access token** cấp quyền API.

## 13. Logout redirect không thay được OAuth Token Revocation

Giả sử Shop RP đang giữ:

~~~text
OP / Authorization Server:
  issuer = https://login.example.org

Client:
  client_id = shop-web

Tokens:
  ID token  -> RP kiểm chứng đăng nhập
  AT-1      -> access token, aud=orders-api, scope=orders:read
  RT-1      -> refresh token dùng tại token endpoint nếu được cấp
~~~

Khi người dùng logout, redirect tới OP chỉ giải quyết một phần trạng thái **phiên đăng nhập**. Nếu muốn **không cho ứng dụng tiếp tục làm mới access token**, RP/BFF cần xử lý **RT-1 tại revocation endpoint** theo chính sách. **RFC 7009** mô tả cách client yêu cầu thu hồi token; một revocation request hợp lệ có thể trả **HTTP 200** cả khi token đã không hợp lệ, nhưng HTTP 200 không bảo đảm toàn bộ access tokens của grant bị mọi RS từ chối tức thì.

| Credential/trạng thái | Sau local/OP logout nên kiểm điều gì? |
|---|---|
| **RP session cookie** | Server có thực sự vô hiệu hóa session ID và xóa cookie đúng scope chưa? |
| **OP SSO session** | OP đã xử lý logout theo giao thức/chính sách chưa? Có user confirmation không? |
| **Refresh token** | Đã xóa khỏi RP và đã revoke tại AS theo hợp đồng chưa? |
| **Opaque access token** | AS introspection đã trả active=false nếu token bị revoke? Cache RS còn giữ active cũ bao lâu? |
| **JWT access token tự chứa** | RS có denylist/epoch/introspection hoặc chỉ kiểm chữ ký, exp và policy? |
| **OIDC ID token** | Không dùng làm Bearer API; không mặc định việc OP logout “thu hồi ID token” giống access token |
| **Authorization grant/consent** | Logout có thật sự ngắt kết nối ứng dụng hay chỉ kết thúc phiên browser? |

**Refresh token và access token không có cùng hiệu lực thu hồi tự động.** Một AS có thể revoke refresh token mà access token JWT đang tồn tại vẫn được RS chấp nhận tới khi hết hạn. Nếu yêu cầu “logout là dừng mọi API ngay”, hệ thống cần **mô hình revocation/freshness riêng**.

### Cửa sổ replay của access token đã bị đánh cắp

Ngay sau khi người dùng thấy trang **signed-out**, attacker giữ được một **Bearer access token** vẫn có thể thử gọi API trong phạm vi audience, scope và thời hạn nếu chưa có revocation thực thi được. Để giảm nguy cơ:

- Access token có TTL phù hợp, audience và scope giới hạn.
- Token được lưu an toàn, không xuất ra URL, log hoặc browser storage không cần thiết.
- RS có chính sách thu hồi sớm nếu yêu cầu rủi ro.
- Có thể dùng **sender-constrained access tokens** như DPoP hoặc mTLS khi AS/RS/client cùng hỗ trợ; việc RP-Initiated Logout **không tự biến bearer token thành proof-of-possession token**.

**Không đưa refresh token vào URL logout hay post-logout callback** để “nhờ OP xóa hộ”. Credential phải được xử lý qua các endpoint và phương thức xác thực dành riêng cho chúng.

## 14. id_token_hint và rủi ro lộ token trong URL

Trong OIDC RP-Initiated Logout, **id_token_hint** được khuyến nghị vì giúp OP nhận diện phiên và RP liên quan. Nhưng ID token là một JWT có thể chứa **subject và claims nhận dạng**; một JWS thông thường được **ký chứ không mã hóa**, nên payload có thể đọc được.

Nếu RP gửi qua **GET redirect**:

~~~text
https://login.example.org/connect/endsession
  ?id_token_hint=<signed-id-token>
  &post_logout_redirect_uri=<registered-return-uri>
  &state=<random-state>
~~~

giá trị **id_token_hint** xuất hiện trong URL request tới OP. Nó có thể bị thu thập bởi:

- Browser history, crash report hoặc tiện ích trình duyệt.
- Reverse proxy/gateway/access log tại OP.
- APM, tracing, debug HTTP logger ở RP hoặc OP.
- Referrer/các tài nguyên bên ngoài nếu trang OP không quản lý chính sách phù hợp.
- Hệ thống hỗ trợ nếu người dùng gửi ảnh chụp/địa chỉ URL.

**Không coi ID token là password hay access token**, nhưng vẫn phải bảo vệ vì có thể chứa claims riêng tư và là bằng chứng liên quan phiên đăng nhập.

### Giảm thiểu

1. **Ưu tiên phương thức POST tới OP khi OP hỗ trợ** RP-Initiated Logout theo giao thức/profile. Không tự chuyển sang POST nếu endpoint cụ thể không hỗ trợ.
2. Cấu hình **redaction** cho query chứa **id_token_hint, logout_hint, state**, và không log raw URI logout.
3. Đặt **Referrer-Policy** thích hợp cho các trang OP/RP quản lý; hạn chế tài nguyên third-party không cần thiết trên trang logout.
4. Không đưa **access token, refresh token, session cookie, code_verifier hoặc client_secret** vào logout URL.
5. Giữ ID token hint trong bộ nhớ/server-side session hoặc kho an toàn **chỉ đến khi cần khởi tạo logout**, tránh giữ raw token lâu trong logout transaction.
6. Dùng **HTTPS/TLS** trên mọi chặng và không redirect qua URL attacker kiểm soát.

**Lưu ý:** POST giảm nguy cơ lộ tham số trên URL nhưng **không tự giải quyết việc request body bị ghi log**. Cần bảo vệ cả body, telemetry và quyền truy cập ở hai bên.

## 15. returnUrl động: hạn chế thành route ID hoặc đường dẫn đã duyệt

Một ứng dụng thường muốn sau logout trở về trang người dùng đã vào trước đó. Không nên để caller cung cấp URL tùy ý:

~~~text
POST /logout?returnUrl=https://evil.example/login
~~~

Rủi ro gồm phishing, logout confusion, lộ dữ liệu qua redirect, và **redirect chains**: một URI nhìn có vẻ tin cậy nhưng tự là open redirect dẫn tới trang khác.

### Phương án đơn giản và an toàn nhất

Luôn dùng URI cố định:

~~~text
post_logout_redirect_uri =
    https://app.example.org/signed-out/callback
~~~

Khi callback hợp lệ, RP hiển thị trang công khai với link **Đăng nhập lại** hoặc **Về trang chủ**. Không cần giữ **returnUrl** tùy ý từ trước logout.

### Nếu sản phẩm cần nhiều đích

Sử dụng **ID nội bộ** rồi map sang route công khai đã cấu hình:

~~~text
return_target = "home"      -> /
return_target = "help"      -> /help
return_target = "signedout" -> /signed-out
~~~

Không map **return_target** trực tiếp thành URL external; không truyền một danh sách tùy ý sang **post_logout_redirect_uri**. OP vẫn phải kiểm rằng **post_logout_redirect_uri nằm trong registration của đúng client**.

Nếu ứng dụng thực sự có nhiều host theo tenant, hãy đăng ký URI chính xác cho từng RP/client/environment hoặc dùng một **callback chung** rồi chọn đích từ **server-side allowlist** sau khi state hợp lệ. Không cho tenant mới tự đăng ký domain callback qua một query logout chưa được kiểm chứng sở hữu và trust.

### Quy tắc tránh open redirect

| Sai lầm | Nguy cơ | Hướng đúng |
|---|---|---|
| **startsWith("https://app.example.org")** | Nhận **app.example.org.evil.test** | Khớp registered URI chính xác |
| Chỉ kiểm hostname chứa **example.org** | Nhận domain do attacker kiểm soát | Kiểm host đúng và policy rõ |
| Cho **//evil.test** làm relative URL | Browser hiểu scheme-relative URL ra domain ngoài | Chỉ cho route ID/path hợp lệ đã xét |
| Decode URL nhiều lần rồi điều hướng | Double-encoding bypass | Hạn chế chọn đích động; kiểm chuẩn hóa một lần rõ ràng |
| Chấp nhận bất kỳ URI có HTTPS | Attacker cũng có HTTPS | Chỉ URI thuộc registration/allowlist |
| Dùng tham số **next** để đổi OP endpoint | Rò id_token_hint cho endpoint khác | OP endpoint từ trusted issuer config |
| Đưa original user URL vào **state** ở dạng thô | State bị lộ, tamper và redirect abuse | Opaque state + server-side transaction |

**HTTPS là điều kiện vận chuyển, không phải bằng chứng đích logout thuộc ứng dụng của bạn.**

## 16. Logout CSRF: logout không nên bị kích hoạt bởi ảnh hoặc link lạ

Một endpoint như:

~~~http
GET /logout HTTP/1.1
Host: app.example.org
Cookie: session=<browser-session-cookie>
~~~

nếu tự động xóa phiên và kích hoạt OP logout, có thể bị website khác nhúng hoặc điều hướng bất ngờ. Kẻ tấn công không nhất thiết lấy được dữ liệu, nhưng có thể **cưỡng ép logout**, phá trải nghiệm, tạo nhầm lẫn account hoặc đưa người dùng vào một chuỗi đăng nhập lừa đảo.

**Logout CSRF** là vấn đề cần cân nhắc cùng login CSRF và session fixation. Một hướng thiết kế cho **RP logout do người dùng chủ động kích hoạt**:

- Dùng **POST** từ giao diện đã xác thực thay vì một GET có side effect.
- Kiểm **CSRF token hoặc cơ chế anti-CSRF** phù hợp cùng SameSite/Origin/Referer policies.
- Nếu người dùng đã logout, xử lý lặp an toàn nhưng không để request công khai kích hoạt logout OP phiên khác.
- Ghi lại một logout transaction mới chỉ sau khi thao tác hợp lệ.
- Cung cấp xác nhận khi rủi ro cao hoặc khi có nhiều phiên/account cần chọn.

**Đừng trộn quy tắc này với Front-Channel/Back-Channel Logout.** Các callback OP gửi đến RP có **giao thức riêng** và không thể mặc nhiên yêu cầu form CSRF token của người dùng; chúng phải được bảo vệ bằng **issuer/source validation, logout token/event validation, session ID binding và trust contract** tương ứng.

### Idempotence của local logout

Nếu một browser gửi **POST /logout** hai lần sau timeout:

~~~text
logout(session ACTIVE)  -> INVALID
logout(session INVALID) -> INVALID
~~~

Session không được **hồi sinh** và lần hai không được tự mở một phiên login mới. Tuy nhiên, chỉ request đầu hợp lệ mới được khởi tạo OP logout transaction; mọi retry cần tuân thủ CSRF/auth contract. Một local logout idempotent **không đồng nghĩa mọi external logout notification cần được gửi lặp không kiểm soát**.

## 17. Multi-issuer, multi-client và multi-tenant

Một ứng dụng có thể chấp nhận đăng nhập từ **OP-A** và **OP-B**, mỗi bên có:

~~~text
OP-A:
  issuer: https://login-a.example.org
  client_id: shop-a
  end_session_endpoint: https://login-a.example.org/endsession
  registered post_logout_redirect_uri: https://app.example.org/signed-out/a

OP-B:
  issuer: https://login-b.example.org
  client_id: shop-b
  end_session_endpoint: https://login-b.example.org/oidc/logout
  registered post_logout_redirect_uri: https://app.example.org/signed-out/b
~~~

RP phải lấy **issuer/client của phiên đã xác thực**, không để người dùng chọn tùy ý bằng:

~~~text
/logout?issuer=https://attacker.example&post_logout_redirect_uri=https://evil.test
~~~

Nếu RP gửi **id_token_hint do OP-A ký** tới OP-B, OP-B không nên tin token ấy như bằng chứng phiên của OP-B. Ngay cả khi RP không gửi ID token hint, OP phải có cách xác minh tính hợp lệ của RP và post-logout URI theo contract trước khi redirect.

### Các lỗi mix-up

| Lỗi | Hậu quả | Bảo vệ |
|---|---|---|
| Session OP-A nhưng end_session_endpoint OP-B | Logout sai provider hoặc không logout | Pin issuer trong trusted session context |
| OP-A client_id nhưng URI đăng ký của client khác | Open redirect hoặc RP mix-up | Binding client ↔ registered URI |
| Dùng state của OP-A tại callback OP-B | Cross-flow correlation error | Store issuer/client/URI trong transaction |
| Cùng callback chung không có issuer binding | Nhầm logout flow giữa các tenants | Validate transaction + expected issuer/client context |
| Logout tenant-A xóa session/token của tenant-B ngoài policy | Unauthorized global logout | Phân biệt phạm vi actor, account và grant |
| Sử dụng một JWKS/issuer validation chung cho mọi OP | Chấp nhận thông tin sai nguồn | Trust registry tách issuer và key/profile |

**Đăng xuất account nào** phải được xác định từ session đã xác thực hoặc thao tác chọn account đáng tin, không từ một tham số **email/subject** tự khai trong URL.

## 18. Khi OP không redirect hoặc callback state sai

Trong hệ thống thật, browser có thể:

- Đóng tab khi đang ở trang OP.
- Mất mạng trước khi được redirect trở lại.
- Người dùng hủy thao tác ở OP hoặc OP yêu cầu xác nhận.
- OP không hỗ trợ RP-Initiated Logout hay không cho post-logout redirect.
- Callback đến với **state thiếu/sai/hết hạn/đã dùng**.
- Một tab cũ phát lại URL callback trong browser history.

### Nguyên tắc xử lý

**Nếu RP session đã bị vô hiệu**, callback lỗi không được làm session ấy active trở lại. RP có thể hiển thị trang công khai:

~~~text
Bạn đã đăng xuất khỏi ứng dụng này.

Trạng thái đăng xuất tại nhà cung cấp đăng nhập chưa được xác nhận.
Nếu sử dụng máy tính chung, hãy đóng trình duyệt hoặc đăng xuất
tại nhà cung cấp danh tính theo hướng dẫn.

[Về trang chủ]   [Đăng nhập lại]
~~~

**Trang trên chỉ là UI minh họa**. Không nói **“Đã đăng xuất khỏi tất cả ứng dụng và thiết bị”** nếu không có cơ chế xác nhận phạm vi đó.

### Phản ứng với callback state sai

~~~text
callback(state):
    tx = lookupAndConsumeValidLogoutTransaction(state)
    if tx missing, expired, wrong browser or already consumed:
        do not authenticate anyone
        do not redirect to a caller-supplied URL
        show generic public signed-out/error page
    else:
        show public signed-out page for the expected RP
~~~

Một callback state hợp lệ **không cấp token**, không đổi code, không cho phép gắn user account mới; nó chỉ kết thúc phần **correlation/UX** của logout flow. Với trạng thái OP logout cần xác nhận chắc chắn, dùng cơ chế/contract riêng thay vì suy ra từ sự xuất hiện của GET callback.

### Có nên retry OP logout từ RP?

Nếu browser không quay lại, server RP không thể tự giả lập mọi thao tác phiên browser tại OP. Có thể hướng dẫn người dùng truy cập OP logout chính thức hoặc bắt đầu giao dịch mới có chủ đích. **Không lặp vô hạn redirect** hoặc lén gửi ID token hint qua một endpoint khác.

## 19. Java: dựng URL end_session_endpoint an toàn

Ví dụ Java sau minh họa cách **chỉ dùng endpoint và redirect URI đã được cấu hình**, thay vì lấy URL của người dùng rồi nối chuỗi.

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Set;

public final class OidcLogoutUrlBuilder {
    private final URI trustedEndSessionEndpoint;
    private final Set<String> registeredPostLogoutUris;

    public OidcLogoutUrlBuilder(
            URI trustedEndSessionEndpoint,
            Set<String> registeredPostLogoutUris
    ) {
        if (!"https".equalsIgnoreCase(trustedEndSessionEndpoint.getScheme())
                || trustedEndSessionEndpoint.getHost() == null
                || trustedEndSessionEndpoint.getRawFragment() != null) {
            throw new IllegalArgumentException("Invalid trusted OP endpoint");
        }
        this.trustedEndSessionEndpoint = trustedEndSessionEndpoint;
        this.registeredPostLogoutUris = Set.copyOf(registeredPostLogoutUris);
    }

    public URI create(
            URI registeredPostLogoutUri,
            String idTokenHint,
            String opaqueState
    ) {
        // URI đăng ký đến từ server config, KHÔNG phải request returnUrl.
        if (!registeredPostLogoutUris.contains(
                registeredPostLogoutUri.toASCIIString())) {
            throw new IllegalArgumentException("Unregistered logout redirect");
        }
        if (idTokenHint == null || idTokenHint.isBlank()
                || opaqueState == null || opaqueState.isBlank()) {
            throw new IllegalArgumentException("Missing logout context");
        }

        String query = "id_token_hint=" + encode(idTokenHint)
                + "&post_logout_redirect_uri="
                + encode(registeredPostLogoutUri.toASCIIString())
                + "&state=" + encode(opaqueState);

        String base = trustedEndSessionEndpoint.toASCIIString();
        String separator = trustedEndSessionEndpoint.getRawQuery() == null
                ? "?" : "&";
        return URI.create(base + separator + query);
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
~~~

**Java 17+**. Đây là ví dụ **xây dựng request URL**, không phải OIDC SDK hay security middleware hoàn chỉnh:

- **trustedEndSessionEndpoint** phải đến từ **verified OP configuration/discovery**, không phải bất kỳ URI HTTPS nào người dùng truyền vào. Constructor kiểm HTTPS chỉ là một kiểm tra phụ.
- **registeredPostLogoutUris** lấy từ cấu hình RP và thực sự phải được đăng ký ở OP. Việc URI nằm trong Set ở RP **không thay bước OP kiểm registration**.
- Ví dụ giả định **id_token_hint có sẵn**; nếu không có, ứng dụng phải theo flow/profile OP hỗ trợ, không tự chế token hoặc bỏ qua điều kiện tin cậy.
- **opaqueState** phải được tạo bằng CSPRNG, lưu trong logout transaction độc lập và được validate trên callback. Code không tự tạo hay validate state.
- **URLEncoder** là phép encode giá trị query dạng form URL-encoding. Tại production hãy dùng thư viện URI builder của framework với contract rõ ràng; tránh double encoding/canonicalization bất ngờ.
- Khi endpoint metadata đã có query, builder thêm tham số theo cách minh họa; không hỗ trợ đầy đủ mọi URI kỳ lạ, userinfo hay redirect chain. Nên validate metadata nghiêm ngặt ở tầng cấu hình.
- Đầu ra có **ID token hint trong URL** khi dùng GET: **không log URI trả về**. Nếu OP hỗ trợ POST, cân nhắc phương thức đó để giảm lộ dữ liệu qua URL.

### Chặn truyền returnUrl tùy ý

~~~java
// SAI:
URI postLogout = URI.create(request.getParameter("returnUrl"));

// ĐÚNG VỀ NGUYÊN TẮC:
URI postLogout = URI.create(
        trustedRpConfig.getRegisteredPostLogoutRedirectUri()
);
~~~

Nếu có nhiều URI, chọn từ **enum/route ID đã được cấu hình server-side**, không lấy chuỗi URL tùy ý từ HTTP request.

## 20. Java: state và callback sau khi RP session đã bị xóa

Một thiết kế không được lưu **logout state chỉ trong login session** rồi lại xóa session trước khi browser quay về. Cần nơi lưu transaction sống ngắn và chống replay.

Ví dụ sinh state bằng CSPRNG:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class LogoutStateGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String generate() {
        byte[] bytes = new byte[32]; // 256 bits ngẫu nhiên
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

### Pseudocode Spring MVC/BFF

~~~java
// PSEUDOCODE: Không phải endpoint production copy-paste.
@PostMapping("/logout")
public RedirectView logout(
        AuthenticatedSession session,
        CsrfValidatedRequest request,
        HttpServletResponse response
) {
    // Lấy trusted context trước khi xóa session.
    TrustedOpRegistration op = registrations.forIssuer(session.issuer());
    String idTokenHint = session.idTokenForLogout();

    String state = LogoutStateGenerator.generate();
    logoutTransactions.saveShortLived(
            hmac(state),
            op.issuer(),
            op.clientId(),
            op.postLogoutRedirectUri(),
            browserCorrelationCookie(response)
    );

    // Server-side invalidation phải là thật, không chỉ Set-Cookie maxAge=0.
    invalidateRpSession(session);
    clearRpCookies(response);
    revokeAndEraseCredentialsAccordingToPolicy(session);

    URI opLogout = logoutUrlBuilder(op).create(
            op.postLogoutRedirectUri(), idTokenHint, state
    );
    return redirectWithSeeOther(opLogout); // HTTP 303, tùy framework
}

@GetMapping("/signed-out/callback")
public ModelAndView logoutCallback(
        @RequestParam(required = false) String state,
        HttpServletRequest request
) {
    LogoutTransaction tx = logoutTransactions.consumeIfValid(
            hmacIfWellFormed(state),
            browserCorrelationCookie(request)
    );
    // Không bao giờ tạo login session hoặc phát token từ callback logout.
    return tx == null
            ? renderPublicLogoutNotice("NOT_VERIFIED")
            : renderPublicLogoutNotice("CORRELATED_RETURN");
}
~~~

Các tên lớp, hàm và method ở trên là **pseudocode**; controller thật cần hợp đồng lỗi/transaction, CSRF, BFF token storage, issuer validation, cookie scope, network timeout, audit, logout propagation và hỗ trợ OP.

### Ba điều dễ sai khi chuyển pseudocode thành production

**1. Transaction độc lập chưa đủ nếu browser binding sai.** Một state bị lộ rồi gửi từ browser khác có thể tạo logout callback confusion; dùng cookie ngắn hạn **Secure, HttpOnly, SameSite=Lax** phù hợp với cross-site top-level return, kiểm cùng transaction và consume một lần. Không mặc định **SameSite=Strict** sẽ được gửi trên mọi callback từ OP.

**2. Đừng giữ nguyên RP session chỉ vì revocation endpoint không khả dụng.** Nếu policy cho phép local logout, phải invalid RP session và ghi rõ revocation chưa chắc thành công. Nếu yêu cầu transactional guarantee phức tạp, triển khai server-side retry bền vững không làm lộ raw token; không báo “mọi token đã revoke” từ một timeout.

**3. Không ghi idTokenHint hoặc redirect URL ra log**. Cần audit thì dùng **issuer_ref, client_id đáng tin, request ID, logout transaction reference, trạng thái local/OP attempt** và lý do chuẩn hóa.

Trong triển khai thực tế, phải **chụp lại các token reference cần revoke trước khi invalid session**, nhưng không giữ raw token trong audit hoặc trong giao dịch callback dài hạn. Khi tạo cookie correlation, bảo đảm thao tác **clearRpCookies** chỉ xóa cookie phiên cũ, **không vô tình xóa cả cookie correlation vừa tạo**; cách đơn giản là thiết kế response cookie operations một cách nguyên tử và kiểm tra bằng integration test. Đừng để ví dụ pseudo tự biến thành race condition do gọi sai thứ tự.

## 21. BFF, SPA và ứng dụng native: redirect có gì khác?

Không phải OAuth client nào cũng quản lý phiên và token cùng một chỗ. Hãy xác định **bên giữ credential** trước khi thiết kế redirect.

| Kiến trúc | Trạng thái chính | Cách logout và redirect nên cân nhắc |
|---|---|---|
| **Server-rendered confidential RP** | Server session cookie; token server-side | Invalid session, revoke token theo policy, RP-Initiated Logout, callback public |
| **BFF cho SPA** | Browser chỉ giữ RP session cookie; BFF giữ token | Browser POST BFF/logout có CSRF, BFF dọn token và invalid session, chuyển OP |
| **SPA thuần public client** | App state/browser token storage theo thiết kế | Dọn local, điều hướng OP theo profile hỗ trợ, không nhúng client secret trong JavaScript |
| **Native/mobile public client** | Secure storage hệ điều hành; system browser/external user-agent | Xóa local credentials, revoke theo AS policy, dùng callback/deep link được đăng ký đúng profile |
| **Desktop/CLI** | Token store local và browser tương tác nếu có | Revoke/erase local token; nếu yêu cầu logout OP cần hiểu browser session không hoàn toàn thuộc CLI |
| **Nhiều app trên một origin** | Cookie, storage và session có thể chia sẻ | Chỉ xóa đúng phạm vi hoặc phối hợp có chủ đích để tránh ảnh hưởng app khác |

### BFF: redirect browser không được mang access token

Với BFF, backend đã có thể giữ **refresh token và access token** trong kho server-side. Sau logout:

~~~text
Browser -> POST /logout (cookie + CSRF)
BFF -> invalidate session / revoke token theo policy
BFF -> 303 tới OP end_session_endpoint
OP -> 302 tới registered post_logout_redirect_uri
Browser -> GET /signed-out/callback (state)
~~~

Không cần trả access token hoặc refresh token cho browser chỉ để phục vụ redirect. Nếu OP yêu cầu **id_token_hint**, BFF có thể lấy **ID token** được OP cấp trong phiên liên quan, theo phương thức gửi mà OP hỗ trợ và kiểm soát việc lộ token.

### Native/mobile: deep link không phải URL nào cũng an toàn

Một ứng dụng native có thể dùng app/universal links để nhận callback khi OP hỗ trợ và đăng ký. Cần kiểm **URI ownership, package/app association, client registration và cơ chế mở app**. Một custom URI scheme không có khả năng xác thực quyền sở hữu mạnh như HTTPS claimed links trong một số hệ sinh thái; không để app khác cướp callback chỉ vì biết tên scheme.

**Đừng mặc định yêu cầu post_logout_redirect_uri HTTP localhost, custom scheme hoặc wildcard được mọi OP chấp nhận.** Phải dựa trên profile và registered URI được nhà cung cấp hỗ trợ.

## 22. Thiết kế UX: nói đúng về phạm vi logout

Sau local logout, người dùng cần hiểu điều gì đã hoàn tất, chứ không chỉ thấy spinner chuyển hướng.

### Mẫu trang local signed-out

~~~text
Bạn đã đăng xuất khỏi ứng dụng Shop Web.

Bạn có thể đóng tab này hoặc quay về trang chủ.
Nếu dùng máy chung, hãy kiểm tra việc đăng xuất ở nhà cung cấp
đăng nhập và các ứng dụng khác khi cần.

[Về trang chủ]  [Đăng nhập lại]
~~~

### Mẫu cảnh báo khi OP logout chưa được xác nhận

~~~text
Phiên của bạn tại Shop Web đã kết thúc.

Chúng tôi chưa thể xác nhận việc đăng xuất tại nhà cung cấp
đăng nhập. Nếu đang dùng thiết bị chung, hãy kiểm tra phiên SSO
tại nhà cung cấp trước khi rời thiết bị.

[Đến trang đăng nhập của nhà cung cấp]  [Về trang chủ]
~~~

Link tới OP trong ví dụ phải tới **URL đáng tin đã cấu hình**, không lấy từ query string. Không hiển thị ID token hay session identifier trong trang lỗi.

### Những thông báo không nên sử dụng khi thiếu bằng chứng

- **“Đã đăng xuất khỏi tất cả tài khoản và thiết bị”** khi chỉ invalid RP session.
- **“Mọi token đã hết hiệu lực”** khi AS revoke chưa hoàn tất hoặc RS dùng JWT offline.
- **“OP logout thành công”** chỉ vì browser được redirect về callback có state hợp lệ.
- **“Có thể đóng tab an toàn tuyệt đối”** khi trình duyệt lưu dữ liệu riêng tư ở extension/session replay hoặc thiết bị công cộng.
- **“Đã xóa quyền truy cập của ứng dụng”** khi thực tế chỉ kết thúc login session mà grant/refresh token vẫn còn.

Nếu UX cần phân biệt nhiều kết quả, hãy dùng **local logout completed**, **OP logout requested**, **OP return observed**, **token revoke confirmed** và **revocation propagation pending** như những trạng thái kỹ thuật khác nhau, nhưng chỉ hiển thị phần hữu ích cho người dùng.

## 23. Năm tình huống thực tế về redirect sau logout

### Tình huống A — Người dùng logout và đăng nhập lại ngay

Người dùng logout Shop Web, về trang signed-out rồi bấm **Đăng nhập**. OP session vẫn active nên Authorization Code + PKCE Flow mới có thể hoàn tất mà không cần nhập mật khẩu. **Đây không chứng minh local logout thất bại**; nó chứng minh **OP session hoặc cơ chế xác thực lại vẫn đáp ứng yêu cầu**.

Nếu sản phẩm muốn logout cả OP, cần **RP-Initiated Logout** tới end_session_endpoint và đánh giá trạng thái OP theo hợp đồng; không dùng một redirect nội bộ để giả lập OP logout.

### Tình huống B — Kẻ tấn công lợi dụng returnUrl

Attacker gửi:

~~~text
https://app.example.org/logout?returnUrl=https://evil.test/support-login
~~~

RP logout rồi chuyển nạn nhân sang **evil.test**. Trang đó giả dạng đăng nhập lại. Nạn nhân tưởng vẫn đang ở hành trình của ứng dụng hợp pháp. **Khắc phục:** POST logout có CSRF, URI cố định hoặc route ID nội bộ, kiểm registered post_logout_redirect_uri và không phản chiếu URL caller.

### Tình huống C — RP session đã xóa, OP callback thất bại

Shop Web invalid session tại server, trình duyệt sang OP, nhưng mạng rớt trước khi nhận callback. **Local logout vẫn có hiệu lực**. Nếu người dùng quay lại API qua tab cũ, server phải từ chối session cookie đã vô hiệu; không chờ callback mới xóa session.

App nên có trang/đường dẫn public an toàn để người dùng tiếp tục khi chưa có xác nhận OP, thay vì hiển thị vô hạn “Đang đăng xuất” hoặc hồi sinh session cũ.

### Tình huống D — Session đã logout nhưng access token bị đánh cắp vẫn dùng được

Shop Web đã xóa session và OP đã redirect về. Nhưng attacker giữ **Bearer AT51** với **aud=orders-api, scope=orders:read** và token còn 10 phút. Nếu Orders API chỉ kiểm signature, exp, aud và scope, token có thể tiếp tục được chấp nhận khi chưa có revocation sớm. **Giải pháp không nằm trong post_logout_redirect_uri**, mà ở **access token lifetime, revocation/denylist/introspection, sender-constraining và chính sách Resource Server**.

### Tình huống E — Cùng một người dùng mở Shop và Reports

Shop logout thành công, OP SSO session kết thúc. Reports vẫn giữ server session riêng. Nếu Reports không tham gia Front-/Back-Channel Logout hay không nhận logout event đúng, session Reports có thể còn hiệu lực. Không tuyên bố **“single logout toàn bộ”** nếu chưa có cơ chế phối hợp và test browser/RS thực tế.

## 24. Ma trận kiểm thử redirect sau logout

Một bộ kiểm thử nên dùng **mock/test OP** có registered logout URI đúng và khả năng điều khiển response, kết hợp một Resource Server test để quan sát việc token cũ còn được chấp nhận hay không.

| ID | Tình huống | Kết quả cần xác nhận |
|---|---|---|
| **S01** | User chủ động POST logout với RP session và CSRF hợp lệ | RP session bị invalid, cookie cũ không dùng lại được |
| **S02** | OP hỗ trợ RP-Initiated Logout; RP có id_token_hint và registered URI | Browser được điều hướng tới đúng trusted end_session_endpoint |
| **S03** | OP trả callback với state hợp lệ | RP consume transaction và hiển thị public signed-out page |
| **S04** | OP không hỗ trợ RP-Initiated Logout | Local logout vẫn hoàn tất và hiển thị fallback an toàn |
| **S05** | End-user logout trong BFF giữ token server-side | BFF dọn token local và revoke theo policy; không gửi RT/AT vào browser URL |
| **F01** | POST logout thiếu/sai CSRF trong flow cần CSRF | Không kích hoạt logout ngoài ý muốn |
| **F02** | GET /logout bị nhúng dưới dạng ảnh/link từ site khác | Không tự thay đổi RP session nếu thiết kế yêu cầu POST |
| **F03** | returnUrl=https://evil.test/phish | Không redirect ra evil.test |
| **F04** | returnUrl=https://app.example.org.evil.test | Không bị bypass bằng prefix match |
| **F05** | returnUrl=https://app.example.org@evil.test | Không bị nhầm userinfo với host |
| **F06** | returnUrl=//evil.test hoặc biến thể encoded | Không chuyển sang host ngoài |
| **F07** | post_logout_redirect_uri chưa đăng ký ở OP | OP từ chối post-logout redirection theo policy |
| **F08** | OP thiếu cách xác minh RP, nhưng request đòi redirect | Không cho post-logout redirection không có cơ sở tin cậy |
| **F09** | RP gửi id_token_hint của OP-A đến OP-B | Không xử lý nhầm issuer/session |
| **F10** | Request chuyển sang end_session_endpoint do caller tự nhập | RP không dùng endpoint không tin cậy |
| **F11** | RP session đã invalid nhưng cookie cũ vẫn gửi | Server từ chối session cũ |
| **F12** | Cookie xóa sai Path/Domain | Test phát hiện cookie cũ còn hiệu lực/khả dụng |
| **F13** | Nhấn Back tới private page sau logout | Không lấy dữ liệu riêng tư mới từ API/session cũ; xem xét browser cache |
| **F14** | Tab khác giữ state cũ | Các API vẫn từ chối session/token đã vô hiệu theo policy |
| **F15** | Callback thiếu state | Không khôi phục session, hiển thị trang công khai phù hợp |
| **F16** | Callback state khác transaction được tạo | Từ chối correlation, không dùng URL động |
| **F17** | Callback state đã hết hạn | Không chấp nhận transaction cũ |
| **F18** | Cùng state callback đến hai lần | Transaction consume một lần; không tạo side effect mới |
| **F19** | State hợp lệ nhưng browser correlation cookie khác | Không nhận callback là transaction của browser khác theo policy |
| **F20** | Logout state được lưu trong login session rồi session bị xóa | Test phát hiện callback không thể đối chiếu; yêu cầu storage độc lập |
| **F21** | OP không redirect hoặc user đóng tab | RP session vẫn đã invalid; không treo security state |
| **F22** | OP trả redirect nhưng không thật sự chấm dứt mọi session | UX không tự tuyên bố toàn bộ hệ thống logout |
| **F23** | OP gửi Back-Channel Logout Token sai chữ ký | RP từ chối thông báo không đáng tin |
| **F24** | Back-Channel Logout Token bị replay jti | RP chống replay theo profile |
| **F25** | Front-channel logout bị browser chặn iframe/cookie | Test nhận diện partial SLO, không giả định mọi RP đã invalid |
| **F26** | OP logout callback vô tình dùng login code handler | Không đổi authorization code hoặc tạo session từ logout callback |
| **F27** | Redirect GET chứa id_token_hint và proxy bật debug | Test phát hiện raw token bị ghi log/telemetry |
| **F28** | Logout URL chứa access_token hoặc refresh_token | Test phải phát hiện và ngăn credential leak |
| **F29** | RP logout thành công nhưng refresh token vẫn server-side | Xóa/revoke theo logout policy đã khai báo, hoặc nêu giới hạn rõ |
| **F30** | Revoke RT ở AS nhưng JWT AT cũ RS vẫn chấp nhận | Test phản ánh mô hình revoke/TTL thực, không suy tức thì |
| **F31** | Opaque AT đã revoked, RS cache active=true | Độ trễ từ chối không vượt revocation freshness policy |
| **F32** | Multi-issuer callback dùng state của OP khác | Context issuer/client/URI không được trộn |
| **F33** | Multi-tenant logout tenant-A vô tình xóa grant tenant-B | Chỉ tác động phạm vi đã được người dùng/chính sách cho phép |
| **F34** | URL có CRLF/double encoding hoặc Unicode hostname giống nhau | Không có header injection/open redirect qua parsing |
| **F35** | OP outage khi RP đã local logout | Không hồi sinh session; thông báo OP trạng thái chưa chắc chắn |
| **F36** | Browser quay về signed-out page nhiều lần | Không tạo login state hay chuyển quyền; UI idempotent |
| **F37** | GET logout URL do attacker nhúng trong email/chat | Không thể cưỡng ép thao tác RP logout trái CSRF policy |
| **F38** | Logout user A, browser đang có account B tại OP | Không tự khẳng định OP xóa đúng account nếu chưa xác minh và xử lý theo OP |
| **F39** | Ứng dụng mobile dùng custom-scheme post logout không được provider đăng ký | Không chấp nhận callback chưa đăng ký hoặc mơ hồ app ownership |
| **F40** | Kết quả 303 sau POST logout được browser điều hướng bằng GET | Không lặp body POST có session/CSRF trong redirect chain |
| **F41** | Công cụ APM ghi logout state và user claims | Redaction và retention bảo vệ dữ liệu correlation/PII |
| **F42** | User gọi lại login ngay sau OP logout | Login flow mới phải đi qua OIDC authorization/PKCE; không tái sử dụng logout callback |

**Đối với mỗi test lỗi, xác minh cả trạng thái thật và response**. Một HTTP 302 đúng host không đủ chứng minh server session invalid; tương tự, một màn hình “Signed out” không đủ chứng minh refresh token đã bị revoke hoặc API từ chối JWT access token còn hạn.

## 25. Integration tests cho ba ranh giới quan trọng

### Test A — Chống open redirect và logout CSRF

~~~text
Given:
  RP có session A đang ACTIVE.
  Chỉ có registered post-logout URI:
    https://app.example.org/signed-out/callback
When:
  Browser ngoài origin gửi GET /logout?returnUrl=//evil.test.
Then:
  Không được kích hoạt logout do GET không được phép.
  Không có 302/303 Location tới evil.test.
  Session A vẫn theo chính sách trước request trái phép.

When:
  RP nhận POST /logout hợp lệ với CSRF và session A.
Then:
  RP invalid session A và chọn URI cố định đã đăng ký.
  Không phụ thuộc bất kỳ returnUrl nào do browser truyền.
~~~

### Test B — Callback state sau khi login session bị xóa

~~~text
Given:
  RP session A đã xác thực bởi OP-A.
  RP sinh logout state S1 có transaction lưu server-side, TTL ngắn.
  RP đã invalid session A.
When:
  OP-A redirect browser về registered callback cùng state S1.
Then:
  RP kiểm S1, browser binding và consume một lần.
  RP hiển thị trang signed-out công khai.
  Không tạo lại session A, không cấp token mới.

When:
  Attacker gửi state S2 sai hoặc replay S1 ở browser khác.
Then:
  RP không coi là callback tương ứng.
  Không khôi phục session, không redirect sang URL do attacker chỉ định.
~~~

### Test C — Tách logout UX khỏi revocation thực tế

~~~text
Given:
  RP có RT1 và AT1 cho Orders API.
  AT1 còn 10 phút, aud=orders-api, scope=orders:read.
When:
  User logout; RP invalid session và yêu cầu revoke RT1.
  Browser được OP redirect về signed-out callback.
Then:
  RP session phải invalid và RT1 không thể refresh nếu AS đã revoke.
  API behavior với AT1 phải đúng AS/RS revocation policy hiện hành.
  Nếu AT1 là JWT tự chứa chưa có denylist, test ghi nhận
  khả năng nó tiếp tục được chấp nhận tới exp.
  Không dùng callback thành công như assertion AT1 chắc chắn invalid.
~~~

**Với yêu cầu “logout ngay trên tất cả thiết bị”**, cần thêm các test đa RP, nhiều browser sessions, Back-Channel Logout delivery, event retry, Redis/introspection cache, grant revocation và token family. Đừng thêm một vòng redirect rồi gọi đó là bằng chứng đủ cho logout toàn cục.

## 26. Checklist thiết kế redirect sau logout

1. **Mục tiêu:** Có tách rõ local RP logout, OP SSO logout, Single Logout và OAuth token revocation?
2. **OP tin cậy:** end_session_endpoint lấy từ verified OIDC configuration/issuer allowlist thay vì query tùy ý?
3. **Session context:** issuer, client ID và ID token hint được lấy từ phiên đang xác thực đúng account?
4. **Local logout:** Server-side session thật sự invalid trước khi hiển thị thành công; cookie được xóa đúng name/path/domain?
5. **CSRF:** Hành động chủ động dùng POST/CSRF và không bị GET/image/link từ bên ngoài cưỡng ép?
6. **Registered URI:** post_logout_redirect_uri nằm trong registration đúng client và được OP kiểm?
7. **Không open redirect:** Không dùng returnUrl tùy ý, prefix match, wildcard hoặc scheme-relative redirect?
8. **Phân biệt callback:** Login redirect_uri và post-logout redirect URI được cấu hình/route riêng?
9. **State:** CSPRNG, TTL ngắn, transaction lưu độc lập login session, browser binding và one-time consume?
10. **OP request:** id_token_hint/client_id/logout_hint được gửi theo profile, không biến chúng thành bearer API credentials?
11. **Privacy:** Không log ID token hint, access/refresh tokens, logout URL, correlation cookies hoặc PII không cần thiết?
12. **Transport:** TLS và HTTP request encoding phù hợp; cân nhắc POST tới OP khi có hỗ trợ?
13. **RP và OP:** Có fallback nếu OP không hỗ trợ, không redirect hoặc user đóng tab?
14. **UX:** Thông báo đúng phạm vi đã logout và không tuyên bố “all devices” khi không có bằng chứng?
15. **Cookie/cache:** Có xử lý browser Back, BFCache, cross-tab UI state và no-store cho nội dung nhạy cảm?
16. **SLO:** Front-/Back-Channel Logout hoặc server-side session invalidation có cơ chế đo/giám sát nếu cần?
17. **Revocation:** RT/AT/grant được xử lý theo logout policy riêng; RS biết độ trễ revoke thực tế?
18. **Token validation:** API luôn kiểm issuer, audience, thời hạn, scope và quyền đối tượng; không chấp nhận ID/refresh token làm AT?
19. **Multi-issuer:** Logout transaction pin đúng OP/client/post-logout URI/tenant, tránh mix-up?
20. **Mobile/SPA/BFF:** Credential và callback xử lý phù hợp khả năng bảo vệ của loại client?
21. **Failure tests:** Có wrong state, expired state, replay, wrong URI, OP outage, token leak và open-redirect fuzzing?
22. **Audit:** Có thể phân biệt RP session invalid, OP request sent, callback correlated, token revoke confirmed mà không lưu credential thô?
23. **Operations:** Có cách giải quyết khi OP thay metadata/end_session_endpoint, signing key hoặc cấu hình registered URI?
24. **Hỗ trợ người dùng:** Có hướng dẫn xử lý phiên SSO còn tồn tại ở thiết bị chung hoặc ứng dụng khác?

## 27. Câu hỏi tự đánh giá

**1. Redirect sau logout có tự xóa session không?** Không. Redirect là điều hướng; RP/OP phải thật sự invalidate session theo policy.

**2. post_logout_redirect_uri có phải redirect_uri nhận authorization code không?** Không. Đây là hai mục đích và registration/validation khác nhau.

**3. end_session_endpoint được lấy từ đâu?** Từ metadata/configuration của **OP đã được tin cậy và xác minh**, không tự đoán URL hoặc nhận endpoint tùy ý từ browser.

**4. id_token_hint có phải access token để gọi API không?** Không. Đó là ID token dùng làm gợi ý cho OP trong logout request, phải bảo vệ dữ liệu khi gửi qua browser.

**5. State trong post-logout callback chứng minh điều gì?** Nó giúp RP đối chiếu giao dịch đã khởi tạo; không tự chứng minh OP logout toàn bộ hoặc token đã bị revoke.

**6. Vì sao không dùng returnUrl bắt đầu bằng domain của ứng dụng?** Prefix match bị lách bằng hostname dài hơn, userinfo, scheme-relative URL, encoding và các kiểu URL parsing khác.

**7. Nếu OP không redirect trở lại, RP session có được tiếp tục active không?** Không nên phụ thuộc vào OP callback; nếu local logout đã hoàn tất, phiên RP vẫn phải invalid.

**8. Logout một RP có tự logout mọi RP khác cùng OP không?** Không mặc định. Cần cơ chế Single Logout như front/back channel hoặc policy phối hợp riêng.

**9. Revoke refresh token có khiến mọi JWT access token cũ bị RS từ chối ngay không?** Không tự động. Cần cơ chế kiểm trạng thái/denylist/introspection hoặc chấp nhận TTL còn lại theo policy.

**10. Vì sao nên dùng POST cho hành động local logout?** Giảm nguy cơ logout CSRF bị kích hoạt bởi GET/link/ảnh; cần CSRF protection/session validation phù hợp.

**11. Có thể đặt raw refresh token vào post_logout_redirect_uri để OP xử lý không?** Không. Refresh token chỉ dành cho AS token/revocation flow được phép; không phơi credential trong URL.

**12. Một callback state đúng có được tạo phiên login mới không?** Không. Login chỉ diễn ra qua luồng authorization/OIDC được xác minh riêng; callback logout là trang public sau kết thúc phiên.

**13. Front-Channel Logout và Back-Channel Logout khác nhau ở đâu?** Front-channel đi qua browser và có thể bị trình duyệt hạn chế; back-channel là thông báo server-to-server có Logout Token cần validate.

**14. Nếu người dùng logout nhưng bấm Đăng nhập lại và được OP xác thực ngay, local logout đã sai chưa?** Không nhất thiết. Có thể OP SSO session vẫn còn trong khi RP local session đã được xóa đúng.

**15. Trong môi trường nhiều issuer, tham số nào do người dùng gửi quyết định OP cần logout?** Không nên để tham số tùy ý quyết định; dùng **issuer/client đã được tin và gắn với phiên**.

**16. Test quan trọng nhất để kết luận “redirect sau logout an toàn” là gì?** Phải kiểm **RP session invalid**, **URI đúng registration, không open redirect**, **state callback đúng/replay-safe**, **không lộ credential**, và mô hình **OP/token/RS revocation** được diễn giải chính xác.

## 28. Tài liệu chuẩn và tổng kết

Những đặc tả quan trọng để đối chiếu khi thiết kế cho OP cụ thể:

- **OpenID Connect RP-Initiated Logout 1.0:** tham số và quy trình RP yêu cầu OP logout, bao gồm **id_token_hint, post_logout_redirect_uri và state**.
- **OpenID Connect Front-Channel Logout 1.0:** cơ chế thông báo logout giữa OP và RPs qua browser.
- **OpenID Connect Back-Channel Logout 1.0:** thông báo server-to-server bằng **Logout Token**; RP phải kiểm chữ ký, claims và chống replay theo profile.
- **OpenID Connect Discovery 1.0:** cơ chế metadata giúp RP xác định OP và các endpoint được quảng bá, khi provider hỗ trợ.
- **RFC 6749 / OAuth 2.0:** vai trò AS/RS/client và authorization flow; **redirect_uri trong authorization** có mục đích riêng.
- **RFC 7009 / Token Revocation:** yêu cầu client thu hồi token và ngữ nghĩa response.
- **RFC 7662 / Token Introspection:** RS xác minh trạng thái token tại AS; cache có giới hạn freshness.
- **RFC 8725 / JWT Best Current Practices:** nguyên tắc xác minh JWT theo ngữ cảnh, tránh nhầm thuật toán/loại token.

Khi triển khai, phải **đối chiếu tài liệu của OP, loại client, registration thực tế và phiên bản profile được hỗ trợ**. Không phải mọi OP cung cấp RP-Initiated Logout, hỗ trợ POST, yêu cầu cùng bộ tham số hay triển khai Front-/Back-Channel Logout giống nhau.

**Ghi nhớ:** **Redirect sau logout là đường điều hướng giữa các miền tin cậy, không phải bằng chứng phiên và token đã mất hiệu lực.** RP cần **invalidate session thật**, OP cần kiểm **end_session_endpoint/registered post_logout_redirect_uri**, và callback cần **state ngẫu nhiên ràng buộc transaction, TTL ngắn, chống replay**. Không nhận **returnUrl** tùy ý, không lộ ID/access/refresh tokens qua URL hoặc telemetry, và không nhầm **local logout, OP logout, Single Logout với OAuth token revocation**. Cuối cùng, Resource Server vẫn phải xác minh **issuer, audience, thời hạn, scope và quyền tài nguyên**, vì người dùng nhìn thấy trang “Đã đăng xuất” không tự ngăn một access token bị đánh cắp được dùng lại.
