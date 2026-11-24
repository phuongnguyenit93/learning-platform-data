# Redirect URI and exact matching

Giả sử ứng dụng **shop-web** dùng OAuth 2.0 để đăng nhập và xin quyền đọc đơn hàng. Sau khi người dùng cấp quyền, Authorization Server sẽ chuyển trình duyệt về một địa chỉ của ứng dụng, ví dụ **https://app.example.org/oauth/callback**, kèm một **authorization code**. Điều gì xảy ra nếu kẻ tấn công có thể khiến Authorization Server chuyển code đó sang **https://attacker.example/collect** thay vì địa chỉ đã đăng ký? Mã ủy quyền có thể bị lộ trước khi client hợp pháp nhận được; các biện pháp như PKCE có thể giảm khả năng đổi code, nhưng không khiến việc chuyển hướng sai nơi trở nên an toàn.

**Redirect URI** là địa chỉ callback mà Authorization Server dùng để trả authorization response về cho client qua trình duyệt trong các flow có chuyển hướng. **Exact matching** là nguyên tắc so sánh giá trị redirect URI trong authorization request với một **URI đã được đăng ký và được phép cho client ấy**, không chấp nhận một địa chỉ chỉ “na ná”, trùng domain một phần hoặc khớp wildcard tùy tiện.

Bài thuộc chương **OAuth2 flows** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung đặt redirect URI vào mô hình tin cậy và vòng đời token: Authorization Code + PKCE, OAuth 2.0/OIDC, issuer/client binding, access token và refresh token, claims, audience, scope, lưu trữ, thu hồi và phòng chống code/token bị đánh cắp hoặc phát lại.

Sau bài này, bạn sẽ hiểu ranh giới bảo mật của callback, phân biệt kiểm tra URI tại authorization endpoint với ràng buộc tại token endpoint, biết các trường hợp không khớp phải từ chối, xử lý ngoại lệ loopback redirect của ứng dụng native, phòng open redirect/mix-up và lập ma trận kiểm thử cho hệ thống thật.

## 1. Redirect URI giải quyết vấn đề gì?

Trong **Authorization Code Flow**, client không nhận access token ngay khi người dùng hoàn tất đăng nhập. Thay vào đó, Authorization Server trả **authorization code** ngắn hạn cho client qua user agent. Redirect URI chỉ ra **nơi code và trạng thái của flow được trả về**.

| Thành phần | Vai trò | Điều cần tin cậy |
|---|---|---|
| **Resource Owner / người dùng** | Tương tác xác thực, consent hoặc chính sách ủy quyền khi cần | Giao diện đăng nhập và tên ứng dụng/tài nguyên được cấp quyền |
| **Client / Relying Party** | Bắt đầu flow, tạo state/PKCE, nhận code tại callback, đổi code lấy token | Địa chỉ callback do chính ứng dụng kiểm soát |
| **Authorization Server (AS)** | Kiểm client, redirect URI, grant, người dùng/ủy quyền; phát code/token | Danh sách redirect URI đã đăng ký cho từng client |
| **Resource Server (RS)** | Nhận access token để bảo vệ API | Issuer, audience, thời hạn, scope và policy tài nguyên |

Ví dụ:

~~~text
Authorization Server: https://auth.example.org
OAuth client_id:       shop-web
Registered redirect:  https://app.example.org/oauth/callback
Resource Server:      https://orders.example.org
Expected audience:    orders-api
~~~

**Redirect URI không phải token endpoint.** Callback thuộc ứng dụng **shop-web**. Token endpoint thuộc **Authorization Server**. Sau khi nhận code, shop-web phải dùng token endpoint để nhận access token; nó không được gửi code đến Orders API thay cho access token.

**Redirect URI cũng không phải audience.** Audience của access token thường nhận diện Resource Server, chẳng hạn **orders-api**; redirect URI lại nhận diện điểm mà authorization response quay về cho OAuth client. Hai giá trị có thể là các URI khác nhau và không thay thế cho nhau.

## 2. Luồng Authorization Code + PKCE: URI xuất hiện ở hai thời điểm

~~~mermaid
sequenceDiagram
    actor U as Người dùng / Browser
    participant C as shop-web / Client
    participant A as Authorization endpoint
    participant T as Token endpoint
    participant R as Orders API
    U->>C: Bắt đầu kết nối OAuth
    C->>C: Tạo state và PKCE verifier/challenge
    C->>A: Authorization request với redirect_uri đã đăng ký
    A->>A: Kiểm client_id và exact redirect URI
    A->>U: Xác thực / consent nếu cần
    U-->>A: Hoàn tất
    A-->>U: Redirect đến callback hợp lệ, kèm code + state
    U->>C: GET /oauth/callback?code=...&state=...
    C->>C: Kiểm state và ngữ cảnh flow
    C->>T: POST authorization_code + code_verifier + redirect_uri
    T->>T: Kiểm code, client, redirect binding, PKCE, single-use
    T-->>C: Access token và token khác khi được phép
    C->>R: Bearer access token dành cho orders-api
    R-->>C: Kết quả sau kiểm issuer/audience/scope/policy
~~~

Trong ví dụ này có **hai lần phải bảo vệ liên kết với callback**:

1. **Tại authorization endpoint:** trước khi gửi authorization response, AS xác nhận redirect URI trong request **chính xác thuộc allowlist của client_id**.
2. **Tại token endpoint:** khi code được đổi lấy token, AS kiểm ràng buộc code với **client** và **redirect URI đã sử dụng trong authorization request**, cùng với PKCE và trạng thái code.

Nếu Authorization Server chỉ kiểm redirect URI ở bước đầu nhưng không ràng buộc code với client/URI khi đổi, kẻ tấn công có thể khai thác các đường đổi code không nhất quán. Nếu chỉ kiểm ở token endpoint mà trước đó đã chuyển code đến địa chỉ kẻ tấn công kiểm soát, bí mật tạm thời đã bị phát tán.

**PKCE và exact matching bổ sung cho nhau; không thay thế nhau.** Exact matching hạn chế địa chỉ được nhận authorization response. PKCE chứng minh bên đổi code sở hữu **code_verifier** tương ứng với challenge của request ban đầu.

## 3. Exact matching thực chất so sánh những gì?

Một Authorization Server nên giữ tập **redirect URIs được đăng ký rõ ràng cho từng OAuth client**. Khi nhận tham số **redirect_uri**, nó phải đối chiếu với tập giá trị đã đăng ký bằng cách so khớp **chuỗi URI chính xác** theo yêu cầu của OAuth security best current practice (**RFC 9700**), thay vì tìm kiếm tiền tố, hậu tố, biểu thức wildcard rộng hoặc tên domain chứa chuỗi nào đó.

Theo **RFC 6749**, khi đăng ký toàn bộ redirect URI, phép so khớp URI trong authorization request dùng **simple string comparison**. Hướng dẫn an ninh hiện đại siết chặt việc đăng ký/so khớp toàn bộ URI, với ngoại lệ có kiểm soát cho **loopback redirect của ứng dụng native** được trình bày bên dưới.

Giả sử **shop-web** chỉ đăng ký:

~~~text
https://app.example.org/oauth/callback
~~~

| URI được yêu cầu | Chấp nhận? | Tại sao? |
|---|---|---|
| **https://app.example.org/oauth/callback** | **Có** | Khớp URI đăng ký |
| **https://app.example.org/oauth/callback/** | **Không** | Thêm dấu gạch chéo cuối |
| **https://app.example.org/oauth/callback2** | **Không** | Chỉ trùng tiền tố đường dẫn |
| **https://app.example.org/oauth/callback?next=/orders** | **Không** | Thêm query chưa đăng ký |
| **https://app.example.org/oauth/callback#done** | **Không** | Redirect URI chứa fragment không hợp lệ cho đăng ký OAuth |
| **http://app.example.org/oauth/callback** | **Không** | Scheme khác; HTTP không an toàn cho web callback thông thường |
| **https://login.app.example.org/oauth/callback** | **Không** | Host khác |
| **https://app.example.org.evil.example/oauth/callback** | **Không** | Host của kẻ tấn công |
| **https://APP.example.org/oauth/callback** | **Không** | Không khớp chuỗi đã đăng ký, dù URI parser có thể coi host tương đương |
| **https://app.example.org:443/oauth/callback** | **Không** | Có cổng tường minh, khác chuỗi đã đăng ký |
| **https://app.example.org/oauth/callback%2F** | **Không** | Chuỗi URI khác; không tự decode/normalize rồi chấp nhận |

Phép so khớp này áp dụng **giá trị URI đã được giải mã khỏi lớp truyền tham số HTTP**. Ví dụ `redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback` trong query của authorization request tương ứng với giá trị URI **https://app.example.org/oauth/callback**. **Không** so chuỗi phần trăm-encoded của form/query với chuỗi URI đăng ký; cũng **không** chuẩn hóa tùy tiện nội dung URI sau khi đã lấy được giá trị tham số.

**Chính sách nên dễ giải thích: nếu URI không nằm trong danh sách chính xác của client, từ chối.** Việc trình duyệt cuối cùng có thể dẫn đến cùng trang qua DNS, redirect phụ hoặc HTTP normalization **không làm URI trở nên được đăng ký**.

## 4. Đăng ký redirect URI: cấu hình là gốc tin cậy

Ví dụ cấu hình logic phía Authorization Server:

~~~yaml
oauthClients:
  shop-web:
    allowedRedirectUris:
      - https://app.example.org/oauth/callback
      - https://admin.example.org/auth/return
    allowedGrantTypes:
      - authorization_code
    requirePkceS256: true
~~~

Đây chỉ là **mô hình minh họa**, không phải format cấu hình của một nhà cung cấp cụ thể. Với **hai redirect URIs** trong allowlist, client có thể chọn một trong **hai giá trị đã được đăng ký đúng chính tả**, không thể thêm URI thứ ba bằng query parameter.

Những quy tắc quan trọng:

- Redirect URI phải được quản lý như **cấu hình của OAuth client**, không như dữ liệu do trình duyệt tự quyết định.
- Với web app, đăng ký **HTTPS URI** của domain thuộc quyền kiểm soát ứng dụng; tránh endpoint không được bảo vệ hay có open redirect.
- URI phải là **absolute URI** và **không chứa fragment** theo yêu cầu OAuth cơ bản.
- Mỗi môi trường **production/staging/development** nên có cấu hình redirect riêng phù hợp; không mặc nhiên cho production redirect đến localhost hoặc máy thử nghiệm.
- Không dùng biểu thức dạng **https://*.example.org/** hoặc **https://app.example.org/** làm giấy phép cho mọi path/query.
- Không dựa vào so khớp chuỗi con của host như **endsWith("example.org")**; **example.org.attacker.test** hoặc domain lừa đảo có thể qua kiểm tra cẩu thả.

### Nếu client có nhiều callback hợp lệ?

Một client có thể đăng ký **nhiều URI cụ thể**, miễn ứng dụng và AS hỗ trợ. Việc lựa chọn callback của một authorization request phải được gắn với **chính giao dịch OAuth ấy**, không dùng một redirect URI ngẫu nhiên từ một request khác.

Nếu URI không được đăng ký, **đừng tự động thêm vào allowlist vì client yêu cầu**. Thay đổi đăng ký client là thao tác quản trị hoặc quy trình đăng ký được xác thực, có kiểm tra quyền sở hữu/cấp phép và audit.

### Không dùng redirect URI làm cơ chế chọn tenant tùy ý

Trong ứng dụng nhiều tenant, thay vì cho client gửi **https://{tenant}.example.org/callback** rồi cho phép wildcard, nên đăng ký rõ tập callback được phép hoặc dùng callback cố định của hệ thống và tra tenant từ **transaction state** đã được bảo vệ. Tenant nhận kết quả phải được liên kết với phiên OAuth và cơ chế xác thực tenant, không chỉ chuỗi do caller tự khai.

## 5. Authorization request đầy đủ: client, callback, state và PKCE

Một request tối giản ở dạng HTTP minh họa:

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback&scope=orders%3Aread&state=<opaque-random-state>&code_challenge=<base64url-S256-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.org
~~~

AS cần kiểm **client_id**, URI đã đăng ký, response type/flow, phạm vi quyền và các ràng buộc chính sách. Với PKCE, **code_challenge** là dữ liệu được gửi ở authorization request; **code_verifier** bí mật tương ứng được giữ ở client và chỉ cung cấp khi đổi code. Với OIDC, request còn có các tham số được profile yêu cầu, ví dụ scope chứa **openid** và **nonce** trong những ngữ cảnh thích hợp.

**state** do client tạo để liên kết response với giao dịch bắt đầu flow. Nên sử dụng giá trị ngẫu nhiên khó đoán, gắn với browser/session/transaction, kiểm trước khi dùng code và chỉ chấp nhận một lần theo policy. State không tự thay thế exact redirect validation hay PKCE.

### AS phải xử lý callback không hợp lệ ra sao?

Nếu redirect URI trong authorization request **thiếu khi cần, không hợp lệ, không khớp client hoặc không thể xác minh**, Authorization Server phải **không chuyển trình duyệt tới URI đó**, kể cả để hiển thị thông báo lỗi OAuth. RFC 6749 yêu cầu đặc biệt tránh tự redirect sang URI sai trong trường hợp client identifier/redirect URI không hợp lệ.

Thay vào đó, AS có thể hiển thị trang lỗi của **chính Authorization Server** hoặc từ chối yêu cầu theo cách không rò authorization code, state hay thông tin người dùng ra URL không được tin.

Đừng tạo phản hồi kiểu:

~~~text
302 Location: <unverified-redirect-uri>?error=invalid_request
~~~

Ngay cả trường hợp “chỉ gửi lỗi”, việc redirect đến địa chỉ tùy ý khiến AS trở thành **open redirector**, có thể hỗ trợ phishing và làm lộ dữ liệu đính kèm.

## 6. Khi nhận callback: client còn phải xác minh state và phiên giao dịch

Giả sử AS đã kiểm URI và redirect đúng về:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/oauth/callback?code=<one-time-code>&state=<original-state>
~~~

Tới callback, client **chưa được coi request là đăng nhập thành công chỉ vì có code**. Những bước quan trọng:

1. Xác định **giao dịch OAuth đã được khởi tạo trước đó** trong đúng browser/session và kiểm state khớp.
2. Phân biệt **authorization response hợp lệ** với request bất ngờ, response lỗi, state đã dùng hoặc giao dịch hết hạn.
3. Xác định AS/issuer đang được dùng theo cấu hình và các cơ chế chống **authorization server mix-up** thích hợp.
4. Lấy **code_verifier** đúng giao dịch, không tái sử dụng verifier ngẫu nhiên của request khác.
5. Gửi code tới **token endpoint của đúng issuer**, với client authentication, redirect URI binding và PKCE theo profile.
6. Chỉ tạo phiên đăng nhập sau khi xử lý **token response** và xác minh chứng cứ danh tính theo OIDC nếu đây là flow đăng nhập.

**state không phải chỗ để lưu access token hay refresh token**. Nếu ứng dụng cần đưa người dùng về một màn hình sau đăng nhập, có thể lưu một **relative return path** trong session server gắn với state, sau đó kiểm đường dẫn nội bộ được cho phép khi điều hướng. Không lấy tham số **returnUrl=https://...** bất kỳ làm đích redirect mới.

### OIDC: nonce và ID token không phải access token

Trong OIDC, **ID token** chứng minh kết quả xác thực danh tính với **client**. Client phải kiểm issuer, audience chứa client_id, chữ ký, thời hạn và điều kiện flow, bao gồm **nonce khi được yêu cầu**. ID token không phải Bearer access token dành cho Orders API; API cần access token riêng có audience phù hợp.

**state** bảo vệ liên kết authorization response với giao dịch; **nonce** bảo vệ các yêu cầu cụ thể của ID token/OIDC flow. Không xem chúng là hai tên cho cùng một bước bảo mật.

## 7. Token endpoint: redirect_uri là một phần ràng buộc của code

Sau callback, client gửi token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback&client_id=shop-web&code_verifier=<original-verifier>
~~~

Ví dụ minh họa **public client**; confidential client cần xác thực theo phương thức được AS đăng ký. RFC 6749 quy định nếu redirect_uri đã được cung cấp trong authorization request, token request cũng phải cung cấp **redirect_uri** và giá trị phải **giống hệt** giá trị ban đầu. AS phải ràng buộc code với **client** mà nó được cấp, và không đổi code đã hết hạn, đã dùng hoặc bị thu hồi.

Ví dụ ràng buộc trong trạng thái authorization code:

~~~text
code_id:          code-example-81
client_id:        shop-web
redirect_uri:     https://app.example.org/oauth/callback
code_challenge:   <S256 challenge>
scope:            orders:read
approved_resource: orders-api
expires_at:       <short-lived timestamp>
consumed:         false
~~~

Trạng thái là ví dụ kiến trúc; trong thực tế AS có thể lưu hoặc bảo vệ nó theo những cách khác. Khi đổi code, AS cần kiểm **đúng client + đúng redirect URI + đúng PKCE verifier + code hợp lệ và dùng một lần**, không chỉ kiểm rằng code trông có vẻ đúng cấu trúc.

### Ví dụ mismatch tại token endpoint

Authorization request dùng:

~~~text
https://app.example.org/oauth/callback
~~~

Nhưng token request gửi:

~~~text
https://app.example.org/oauth/callback/
~~~

Hai chuỗi không giống hệt nhau. Nếu URI đã dùng ban đầu là giá trị thứ nhất, token endpoint phải **từ chối yêu cầu đổi code** theo ràng buộc redirect URI; không tự loại dấu gạch chéo cuối để “sửa giúp client”.

**Authorization code là credential ngắn hạn một lần.** PKCE làm giảm khả năng đổi code bị đánh cắp, nhưng không cho phép kéo dài thời hạn, tái sử dụng code hay bỏ qua URI binding.

## 8. Exact matching không có nghĩa callback được phép open redirect

Giả sử AS chỉ cho phép callback:

~~~text
https://app.example.org/oauth/callback
~~~

Nhưng endpoint callback của app lại có logic:

~~~text
GET /oauth/callback?code=...&state=...&next=https://attacker.example
=> HTTP 302 Location: https://attacker.example?code=...
~~~

Đây là **open redirect tại client**. Dù AS đã chuyển response tới URI đăng ký, logic của ứng dụng có thể **chuyển tiếp code hoặc thông tin phiên** sang địa chỉ kẻ tấn công.

Không chỉ dựa vào cấu hình redirect của AS: client phải bảo vệ **callback handler**. Quy tắc:

- Callback chỉ nhận và xử lý response OAuth; **không chuyển tiếp query chứa code/state** tới domain tùy ý.
- Không tạo Location header từ giá trị **next**, **returnTo**, **continue** hoặc **redirect** chưa được kiểm định.
- Nếu cần điều hướng sau đăng nhập, chỉ cho **relative path được phê duyệt** hoặc URL nằm trong allowlist cực kỳ chặt và **không mang code/state/token theo**.
- Loại code/state khỏi URL trình duyệt khi flow đã được xử lý theo cách an toàn, không chuyển chúng vào analytics, session replay, referrer hoặc error logging.
- Hạn chế third-party scripts trên callback và đặt **Referrer-Policy** phù hợp, chẳng hạn **no-referrer** khi cần ngăn rò URL chứa code/state.
- Tránh hiển thị lỗi bằng cách in toàn bộ callback URL, authorization code, state hoặc token vào DOM.

**Exact matching kiểm tra đúng địa chỉ AS được phép quay về; nó không bảo đảm code callback đó không tự gửi thông tin đi tiếp**. Bảo vệ callback là trách nhiệm phía client.

## 9. Vì sao so khớp theo prefix, subdomain hay wildcard nguy hiểm?

Một số anti-pattern:

~~~text
requestedRedirect.startsWith("https://app.example.org")
requestedRedirect.includes("example.org")
requestedRedirect.endsWith("example.org")
registeredPattern = "https://*.example.org/*"
~~~

Các phép kiểm kiểu này tạo những lỗ hổng khác nhau:

| Điều kiện sai | Giá trị có thể gây nhầm | Vấn đề |
|---|---|---|
| **startsWith(https://app.example.org)** | https://app.example.org.attacker.example/collect | Domain thật khác, chỉ trùng tiền tố |
| **substring chứa example.org** | https://example.org.attacker.example/cb | String chứa tên domain nhưng host không thuộc quyền sở hữu |
| **Cho mọi subdomain** | https://abandoned.example.org/cb | Subdomain có thể không do cùng đội bảo vệ hoặc đã bị chiếm |
| **Cho mọi path trên cùng host** | https://app.example.org/open-redirect?next=... | Path được mở rộng tới endpoint không phù hợp |
| **Tự bỏ trailing slash** | /oauth/callback và /oauth/callback/ | AS chấp nhận giá trị không được đăng ký |
| **So khớp sau normalize tùy tiện** | Mã hóa đường dẫn, dấu chấm, query biến thể | Thao tác normalize giữa proxy/server có thể khác nhau |
| **Cho HTTP thay HTTPS** | http://app.example.org/oauth/callback | Rủi ro nghe lén/sửa nội dung trên đường truyền |

Đừng cho rằng **địa chỉ trông giống một URL hợp lệ** là đủ. Phải so **giá trị đã đăng ký cho client**, không tự suy từ Host header, Origin, Referer hoặc tên domain xuất hiện trong query.

### Phân biệt URI và HTTP request sau redirect

Khi AS redirect tới callback đã đăng ký có sẵn query:

~~~text
Registered URI:
https://app.example.org/oauth/callback?channel=web

Authorization response:
https://app.example.org/oauth/callback?channel=web&code=<code>&state=<state>
~~~

**Không so toàn bộ URL của request callback sau redirect với URI đăng ký** rồi từ chối chỉ vì nó có thêm **code/state**; đây là những tham số response hợp lệ do AS thêm vào theo response mode. Exact matching ở AS so **redirect_uri mà client yêu cầu** với URI đã đăng ký **trước khi** AS gắn các response parameters. Client cần phân tích callback theo đúng flow và kiểm state/code, không coi các tham số mới là thay đổi đăng ký.

## 10. Ứng dụng native: ngoại lệ loopback port phải được giới hạn rõ

Native app có đặc thù: nó có thể chạy HTTP listener trên **loopback interface** của thiết bị với **cổng tạm thời do hệ điều hành cấp**. **OAuth 2.0 for Native Apps (RFC 8252)** và OAuth security guidance cho phép **ngoại lệ phần port** đối với **loopback IP redirect URI** của native app.

Ví dụ app đăng ký một redirect URI loopback tương ứng và khi chạy thực tế chọn cổng ngẫu nhiên:

~~~text
Registered native callback:
http://127.0.0.1:38120/oauth2/callback

Actual callback at runtime:
http://127.0.0.1:52341/oauth2/callback
~~~

Trong profile native loopback cho phép cổng biến đổi, AS có thể chấp nhận **sự khác nhau ở port**, nhưng **scheme, loopback host literal, path và các thành phần khác vẫn phải tuân theo quy tắc**. Một số hệ thống lưu đăng ký loopback ở dạng đại diện thay vì một port cố định; cách biểu diễn cụ thể do AS/profile quy định.

Điều quan trọng:

- Ngoại lệ chỉ dành cho **loopback redirect của native app** theo profile, **không phải wildcard port cho web app production**.
- Dùng **loopback IP literal** như **127.0.0.1** hoặc **[::1]**; RFC 8252 không khuyến nghị dùng tên **localhost** để tránh phụ thuộc phân giải tên.
- Chấp nhận **port động** không có nghĩa chấp nhận host tùy ý, subdomain lạ, path bất kỳ hoặc redirect đến IP mạng ngoài.
- Native app vẫn cần **Authorization Code + PKCE** và phải bảo vệ state/code/verifier.
- Loopback HTTP là ngoại lệ vì kết nối nằm trên giao diện cục bộ, **không phải giấy phép dùng HTTP trên Internet**.

### Custom URI scheme và claimed HTTPS

Native app có thể đăng ký private-use URI scheme hoặc dùng **claimed HTTPS redirects** khi nền tảng hỗ trợ. Custom scheme có nguy cơ ứng dụng khác trên thiết bị cũng đăng ký cùng scheme và tranh nhận redirect, nên PKCE và xác minh app identity rất quan trọng. Claimed HTTPS có thể cung cấp liên kết domain–ứng dụng qua cơ chế nền tảng, nhưng phải cấu hình/kiểm chứng đúng quyền sở hữu domain.

**Không áp dụng ngoại lệ loopback cho tất cả redirect URI có chữ “localhost” hay “127.0.0.1” trong một phần chuỗi.** Cần phân tích đúng host thuộc URI và kiểm loại client/profile được phép.

## 11. Reverse proxy, HTTPS termination và callback URL trong thực tế

Ứng dụng chạy sau load balancer hoặc reverse proxy thường nhìn thấy request nội bộ dưới dạng **http://service:8080**, trong khi URL công khai mà người dùng dùng là **https://app.example.org**. Nếu framework tự xây redirect_uri từ URL nội bộ, AS sẽ từ chối vì không khớp đăng ký. Đây là lỗi cấu hình thường gặp và **không nên xử lý bằng cách nới lỏng matching**.

Thiết kế an toàn:

1. Đăng ký **public HTTPS callback URI ổn định** tại AS.
2. Cấu hình OAuth client dùng đúng callback URI công khai hoặc base URL đã được quản trị.
3. Chỉ tin các **Forwarded/X-Forwarded-Host/X-Forwarded-Proto** headers khi chúng được proxy tin cậy thiết lập và tầng ứng dụng có chính sách xử lý cụ thể.
4. Không để caller ngoài Internet tự đặt Host/Forwarded header để điều khiển redirect URI hoặc Location response.
5. Nếu triển khai nhiều domain/tenant, giữ allowlist cụ thể và ánh xạ vào client/tenant được kiểm chứng.

Ví dụ pseudocode cho client không tự lấy callback từ request thô:

~~~text
beginOAuthLogin(session):
    flow = createOneTimeTransaction(state, pkceVerifier)
    redirectUri = configuredPublicCallbackForClient("shop-web")

    authorizationUrl = buildAuthorizationRequest(
        trustedAuthorizationEndpoint,
        clientId = "shop-web",
        redirectUri = redirectUri,
        state = flow.state,
        codeChallenge = S256(flow.pkceVerifier)
    )
    persistTransactionBoundToSession(flow, redirectUri)
    redirectBrowser(authorizationUrl)

onOAuthCallback(request, session):
    flow = requireMatchingUnusedState(request.state, session)
    tokens = exchangeCodeAtTrustedTokenEndpoint(
        code = request.code,
        clientId = "shop-web",
        redirectUri = flow.redirectUri,
        codeVerifier = flow.pkceVerifier
    )
    validateTokenResponseForExpectedIssuerAndClient(tokens)
    completeSessionWithoutExposingCodeOrTokens()
~~~

Đây là **pseudocode kiến trúc**, không phải thư viện OAuth có thể dùng trực tiếp. Nó nhấn mạnh rằng client giữ **redirectUri gắn với giao dịch gốc**, thay vì tái dựng từ URL callback hiện tại có thể đã bị proxy rewrite hoặc caller thao túng.

## 12. Multiple Authorization Servers và nguy cơ mix-up

Một ứng dụng có thể cho người dùng đăng nhập qua nhiều OpenID Providers/Authorization Servers. Khi đó, chỉ kiểm redirect URI và state có thể chưa đủ nếu client xử lý nhầm **issuer** của authorization response.

**Authorization server mix-up** xảy ra khi client nhầm response/grant của AS này với AS khác, có thể gửi code hoặc dữ liệu nhạy cảm tới token endpoint sai nếu quản lý phiên và issuer kém an toàn.

Các kiểm soát quan trọng:

- Mỗi giao dịch OAuth lưu **Authorization Server/issuer dự kiến**, token endpoint và cấu hình client tương ứng.
- Khi callback đến, client chỉ dùng **token endpoint thuộc issuer đã được chọn trong giao dịch**, không dựa vào tham số URL không đáng tin.
- Áp dụng biện pháp chống mix-up được profile hỗ trợ, chẳng hạn **issuer identification trong authorization response (RFC 9207)** hoặc cơ chế tương đương phù hợp, và kiểm issuer chính xác.
- Với OIDC, kiểm **issuer trong ID token**, audience của client và các ràng buộc riêng của flow.
- Cân nhắc **redirect URI tách riêng** giữa các AS khi kiến trúc/profile cần hoặc khi không có cơ chế chống mix-up tương ứng; callback chung đòi lưu ngữ cảnh phiên chính xác.

Một authorization code do issuer A cấp **không được tự đưa tới token endpoint issuer B**. Mã hóa hay ký token sau này không sửa được một yêu cầu token đã được gửi sai nguồn và có thể làm lộ code/client credentials.

## 13. Những kiểm tra nào phải đặt ở AS và client?

### Tại Authorization Server

| Điểm kiểm | Việc phải làm | Điều phải tránh |
|---|---|---|
| **Client registration** | Duy trì allowlist exact callback của đúng client | Cho caller thêm URI động mà không được quản trị/xác thực |
| **Authorization request** | Xác minh client, redirect URI, flow, scope và PKCE theo profile | Prefix/wildcard match, redirect về URI không được đăng ký |
| **Authorization response** | Chỉ gửi code/state tới callback hợp lệ | Redirect code/error sang URL không tin cậy |
| **Token request** | Code đúng client/redirect/PKCE, còn hạn và single-use | Chấp nhận URI đã normalize khác, đổi code nhiều lần |
| **Token issuance** | Access token đúng issuer, audience, scope, thời hạn | Cấp quyền từ dữ liệu request mà không kiểm grant |

### Tại OAuth client

| Điểm kiểm | Việc phải làm | Điều phải tránh |
|---|---|---|
| **Flow initiation** | Dùng redirect URI đã cấu hình, tạo state/PKCE riêng giao dịch | Xây URI từ untrusted Host/next |
| **Callback** | Kiểm state, issuer/mix-up, flow còn hiệu lực, code/error | Nhận callback bất ngờ rồi tạo session |
| **Code exchange** | Gửi code đến token endpoint đúng issuer, dùng redirect_uri/verifier ban đầu | Gửi code sai AS hoặc bỏ PKCE |
| **Post-login navigation** | Relative return path đã được kiểm tra, xóa secrets khỏi browser URL | Open redirect hoặc chuyển code/state tới domain lạ |
| **Token storage** | Bảo vệ access/refresh/ID token, không log credential | Đưa token vào analytics, URL, local debug hoặc ticket |

**Kiểm ở cả hai phía không phải lặp vô ích.** AS bảo vệ nơi gửi response và điều kiện đổi code; client bảo vệ phiên và cách xử lý response. Resource Server tiếp tục kiểm access token sau khi token được phát hành.

## 14. Java: so khớp chính xác tại Authorization Server

Ví dụ Java minh họa **nguyên tắc so chuỗi exact**:

~~~java
import java.util.Set;

public final class RedirectUriCheck {
    private static final Set<String> ALLOWED_FOR_SHOP_WEB = Set.of(
            "https://app.example.org/oauth/callback",
            "https://admin.example.org/auth/return"
    );

    public static boolean isRegistered(String clientId, String redirectUri) {
        if (!"shop-web".equals(clientId) || redirectUri == null) {
            return false;
        }
        return ALLOWED_FOR_SHOP_WEB.contains(redirectUri);
    }
}
~~~

Ví dụ cố tình dùng tập URI cố định và **String.equals** ngầm qua **Set.contains**. **Không** dùng **startsWith**, **contains**, regex wildcard, URI normalization hoặc chỉ so host. Trong hệ thống thực tế, URI đăng ký phải được quản lý qua client registry đáng tin, kiểm absolute URI/fragment tại registration và áp dụng chính sách security profile, native loopback exception, PKCE và code binding; đoạn Java này **không thay một Authorization Server chuẩn**.

### Test cases cho Java ví dụ

~~~text
isRegistered("shop-web", "https://app.example.org/oauth/callback")
=> true

isRegistered("shop-web", "https://app.example.org/oauth/callback/")
=> false

isRegistered("shop-web", "https://app.example.org.evil.example/callback")
=> false

isRegistered("other-client", "https://app.example.org/oauth/callback")
=> false
~~~

**Không nên tự viết toàn bộ OAuth authorization server** chỉ dựa trên đoạn kiểm URI. Thư viện và framework được duy trì cần kiểm grant/client, PKCE, issuer, trạng thái code, xác thực client, threat model và các yêu cầu profile hiện hành.

## 15. Các anti-pattern thường gặp

1. **Redirect URI wildcard:** chấp nhận mọi path/subdomain, khiến endpoint có open redirect hoặc subdomain bị chiếm trở thành đích nhận code.
2. **So prefix:** URI **https://app.example.org.evil.example** được chấp nhận vì bắt đầu bằng tên host hợp pháp.
3. **Client tự đăng ký redirect URI tại mỗi request:** attacker biến dữ liệu không tin thành trust configuration.
4. **Bỏ redirect_uri binding ở token endpoint:** code có thể bị đổi trong ngữ cảnh URI không đúng giao dịch ban đầu.
5. **Chỉ dựa vào state:** state có thể khớp nhưng redirect URI được phát tới nơi sai; PKCE/state không phải giấy phép bỏ exact matching.
6. **Không dùng PKCE:** code bị chặn có thể dễ bị đổi hơn, đặc biệt với public clients.
7. **Dùng HTTP cho web callback production:** token/code có thể đi qua đường truyền không bảo mật; ngoại lệ loopback native không áp dụng.
8. **Open redirect ở callback:** đã nhận code tại URI đúng nhưng sau đó chuyển tiếp code/state sang nơi khác.
9. **Tin Forwarded/Host headers từ caller:** ứng dụng tạo callback URL do bên ngoài kiểm soát.
10. **Callback chung nhiều AS nhưng không ràng buộc issuer:** nguy cơ mix-up và gửi code sai token endpoint.
11. **Cho thêm query tự do vào redirect_uri:** client dùng **next**/tenant/url do caller chọn như một phần callback; có thể phá exact registration và mở đường lộ code.
12. **Không phân biệt authorization request với callback response URL:** so sai URI sau khi AS đã thêm code/state, dẫn đến lỗi flow hoặc nới lỏng so khớp vô lý.
13. **Lộ code/state trong log và analytics:** callback raw URL xuất hiện trong access log, tracing, session replay hoặc Referer.
14. **Nhận ID token làm access token:** sai mục đích; API phải kiểm loại token và audience độc lập với redirect flow.

## 16. Ma trận kiểm thử an toàn cho redirect URI

| Test case | Kết quả mong đợi |
|---|---|
| Authorization request dùng đúng URI đăng ký | Qua bước redirect validation; tiếp tục các điều kiện flow |
| URI thiếu khi profile/đăng ký yêu cầu | Từ chối, không redirect đến URI không xác minh |
| URI không thuộc danh sách của client | Từ chối và không gửi code/error tới URI đó |
| URI của client A được client B yêu cầu | Từ chối vì allowlist phải gắn với client_id |
| URI hợp lệ nhưng thay trailing slash | Từ chối |
| URI có hostname trùng tiền tố nhưng thực ra nằm trên domain khác | Từ chối |
| URI cùng host nhưng thêm path hoặc query chưa đăng ký | Từ chối |
| URI được thay scheme HTTPS thành HTTP | Từ chối với web client |
| URI chứa fragment | Từ chối theo quy tắc OAuth redirect URI |
| URI có explicit default port chưa đăng ký | Từ chối |
| URI chứa percent-encoding variant, normalization khác | Không tự normalize rồi chấp nhận; kiểm exact giá trị URI |
| Native loopback URI thay port động theo profile được hỗ trợ | Chấp nhận **chỉ sự khác biệt port** theo exception |
| Web redirect URI thay port động | Từ chối nếu không được đăng ký đúng giá trị |
| Authorization code đúng nhưng token request gửi redirect_uri khác | Từ chối đổi code |
| Code đã được đổi một lần | Từ chối replay |
| Code đúng URI nhưng PKCE verifier sai | Từ chối |
| Client callback nhận state lạ/đã dùng | Không tạo session, từ chối response |
| Client callback open redirects tới domain tùy ý | Không chuyển code/state/token sang domain khác |
| Authorization request chọn issuer A nhưng callback xử lý như issuer B | Từ chối/chặn mix-up |
| Proxy rewrite khiến client tạo http://internal:8080 callback | Sửa public callback configuration; **không** nới lỏng AS |
| Callback URL xuất hiện trong log với code/state | Redact/không ghi secrets; test telemetry không chứa raw code/state |
| Authorization response mang code và state được AS thêm vào URI đã đăng ký | Client xử lý đúng response params, không coi chúng là lỗi đăng ký |
| Callback hợp lệ và đổi code thành access token cho Orders API | RS vẫn kiểm issuer, audience, scope, thời hạn và quyền tài nguyên |

Đối với negative tests, kiểm cả **không có authorization code bị gửi về URI sai**, **không phát token từ code không hợp lệ** và **không có dữ liệu API được trả ra**. Sử dụng domain/credential thử nghiệm trong môi trường được phép; không chuyển hướng người dùng thật tới địa chỉ ngoài phạm vi kiểm soát để thử lỗ hổng.

## 17. Checklist thiết kế và vận hành

1. **Registration:** Mỗi OAuth client có allowlist redirect URI cụ thể, không wildcard/prefix?
2. **Ownership:** Domain/path callback thuộc thành phần được quản trị và bảo vệ, không open redirect?
3. **HTTPS:** Web callbacks dùng HTTPS; các ngoại lệ native app được xử lý riêng theo RFC 8252?
4. **Exact matching:** AS so chuỗi URI chính xác sau khi giải mã lớp tham số HTTP, không normalize tùy tiện?
5. **Client binding:** Callback gắn đúng **client_id**; token endpoint cũng ràng buộc code với client?
6. **Redirect binding:** Khi authorization request gửi redirect_uri, token request có gửi **giá trị giống hệt**?
7. **PKCE:** Authorization Code Flow dùng PKCE (ưu tiên S256), code_verifier không lộ và khớp challenge?
8. **state:** Client có tạo state khó đoán, gắn phiên giao dịch và kiểm response không?
9. **OIDC:** Có phân biệt nonce/ID token validation với state, access token và audience API?
10. **Mix-up:** Nếu nhiều AS, client có ràng buộc issuer/token endpoint đúng giao dịch và biện pháp chống mix-up?
11. **Reverse proxy:** Public callback URI cố định hoặc lấy từ proxy headers đã được xác minh, không tin Host tự khai?
12. **Post-login:** Không có next/returnTo tùy ý chuyển tiếp code/state hoặc dẫn đến open redirect?
13. **Token issuance:** Code ngắn hạn, single-use, PKCE/client/redirect validation, access token đúng issuer/audience/scope?
14. **Observability:** Gateway, callbacks, AS, APM và analytics có tránh log raw code/state/token không?
15. **Incident response:** Khi callback bị chiếm hoặc code/token bị lộ, có thể ngăn redirect, vô hiệu hóa grant/token và điều tra bản sao?
16. **Tests:** Đã chạy các trường hợp sai URI, encoded variants, native port, wrong issuer, wrong PKCE, code replay và open redirect?

## 18. Câu hỏi tự đánh giá

**1. Redirect URI trong Authorization Code Flow dùng để làm gì?** Là địa chỉ callback đã được phép để Authorization Server trả authorization response (thường chứa code và state) về client qua trình duyệt.

**2. Vì sao không thể kiểm bằng startsWith("https://app.example.org")?** Vì một URI có host **app.example.org.attacker.example** vẫn có cùng tiền tố chuỗi nhưng là domain khác; chỉ exact matching với URI đăng ký mới loại trừ được trường hợp ấy.

**3. Nếu app đăng ký /oauth/callback, có được dùng /oauth/callback/ không?** Không, khi áp dụng exact matching; dấu gạch chéo cuối làm chuỗi URI khác giá trị đăng ký.

**4. URI được encode thành https%3A%2F%2F... trong authorization request có phải URI khác không?** Không. Encoding đó là lớp truyền tham số HTTP. AS lấy giá trị redirect_uri rồi đối chiếu chuỗi URI với đăng ký; không so raw percent-encoded query.

**5. AS nên làm gì nếu redirect_uri sai?** Từ chối yêu cầu và **không redirect người dùng tới URI chưa xác minh**, kể cả khi muốn trả lỗi OAuth.

**6. PKCE có thay thế exact redirect matching không?** Không. Exact matching bảo vệ nơi nhận response; PKCE ràng buộc việc đổi code với verifier. Cả hai vẫn cần cùng các kiểm soát client/issuer/state.

**7. Tại sao token endpoint cần biết redirect_uri đã dùng ban đầu?** Để xác minh code được đổi trong đúng ngữ cảnh callback/client đã được cấp; với authorization request có redirect_uri, token request phải cung cấp cùng giá trị theo RFC 6749.

**8. Có thể chấp nhận port động cho mọi localhost callback không?** Không. Ngoại lệ cổng chỉ dành cho **native loopback IP redirect** theo profile; không cho port wildcard cho web production hoặc hostname bất kỳ.

**9. Nếu AS redirect đúng nhưng callback có open redirect thì có an toàn không?** Không. Client có thể chuyển tiếp code/state tới domain ngoài ý muốn; cần kiểm soát logic callback và post-login navigation.

**10. Sau khi callback nhận code, Resource Server có cần kiểm access token không?** Có. Client phải đổi code tại AS; Resource Server kiểm access token đúng issuer, audience, thời hạn, scope và quyền tài nguyên.

**Ghi nhớ:** **Redirect URI là ranh giới bảo vệ nơi authorization response được gửi tới; exact matching buộc AS chỉ gửi về callback đã đăng ký của đúng client.** Authorization Code + PKCE còn cần **state, code binding, token endpoint verification và issuer validation**, trong khi client phải ngăn **open redirect, code leakage và mix-up**. Ngoại lệ cổng động chỉ áp dụng cho native loopback redirect theo profile. Khi access token được phát hành, **Resource Server vẫn có trách nhiệm kiểm token và phân quyền trên từng tài nguyên**; một callback đúng không tự chứng minh mọi quyền API.
