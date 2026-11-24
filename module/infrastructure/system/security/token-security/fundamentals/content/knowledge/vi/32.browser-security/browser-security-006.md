# PKCE cho public browser client

## 1. PKCE giải quyết vấn đề gì trong trình duyệt?

Một ứng dụng web chạy JavaScript trong trình duyệt, chẳng hạn **Single Page Application (SPA)**, thường là **public OAuth client**: mã ứng dụng được gửi tới thiết bị người dùng và bất kỳ ai cũng có thể xem mã nguồn, phân tích gói mạng do chính họ tạo hoặc lấy các giá trị nhúng trong bundle. Vì vậy ứng dụng **không thể bảo mật client secret dài hạn** như một backend có vùng lưu trữ bí mật. Đưa **client_secret** vào JavaScript, biến môi trường được đóng gói vào frontend hoặc file cấu hình công khai không biến SPA thành confidential client.

Trong **OAuth 2.0 Authorization Code Flow**, client chuyển hướng người dùng tới **authorization server (AS)**, nhận **authorization code** qua redirect rồi gửi code đến token endpoint để đổi lấy access token và, nếu được cấp, refresh token. Nếu kẻ tấn công lấy được authorization code và có thể đổi code, họ có cơ hội nhận token dành cho ứng dụng và truy cập tài nguyên.

**Proof Key for Code Exchange (PKCE, RFC 7636)** gắn authorization code với một **bí mật ngẫu nhiên sinh riêng cho từng giao dịch**, gọi là **code_verifier**. Client chỉ gửi giá trị băm dẫn xuất **code_challenge** qua authorization request, giữ code_verifier lại và chứng minh nó khi đổi code tại token endpoint. AS chỉ chấp nhận code nếu verifier khớp challenge đã ghi nhận.

PKCE đặc biệt quan trọng với public browser client vì:

- Không cần lưu client secret cố định trong browser.
- Giảm khả năng đổi **authorization code bị chặn/lộ** khi bên tấn công không có code_verifier.
- Liên kết bước **xin code** với bước **đổi code** trong cùng một giao dịch.
- Có thể kết hợp với kiểm tra **state**, **issuer**, **OIDC nonce**, **redirect URI**, **scope**, **audience**, **token lifetime** và **sender-constraining**.

**Giới hạn cốt lõi:** PKCE giúp bảo vệ việc **đổi authorization code**. Nó **không** bảo vệ toàn bộ phiên trình duyệt, không tự ngăn XSS hoặc mã JavaScript độc hại, không thay xác minh access token/ID token và không bảo đảm access/refresh token sau khi được cấp sẽ không bị đánh cắp.

## 2. Public browser client nằm ở đâu trong mô hình OAuth/OIDC?

| Thành phần | Vai trò | Điều cần kiểm soát |
|---|---|---|
| **Trình duyệt + SPA** | Public client khởi tạo authorization request, giữ verifier ngắn hạn, xử lý callback và có thể gọi API | Giao dịch đăng nhập, state/nonce, code_verifier, token và giới hạn của JavaScript |
| **Authorization server / OpenID Provider** | Xác thực người dùng, nhận code_challenge, cấp authorization code, kiểm tra verifier, phát hành token | Authorization code phải ràng buộc client và giao dịch PKCE, chỉ dùng một lần |
| **Resource server** | Nhận access token và quyết định truy cập API | Issuer, audience, thời gian, scope/quyền, ràng buộc token và thu hồi theo chính sách |
| **Backend for Frontend (BFF), nếu có** | Backend thực hiện OAuth flow và giữ token server-side thay cho JavaScript | Bảo vệ cookie phiên, CSRF, quản lý session/token, không lộ token ra frontend |

Một **public client** vẫn có **client_id** để định danh đăng ký ứng dụng, nhưng client_id là dữ liệu công khai, không phải mật khẩu. PKCE không chứng minh người gửi request là một bản sao ứng dụng “chính hãng”: bất kỳ chương trình nào biết client_id vẫn có thể bắt đầu flow của chính nó. PKCE chỉ chứng minh request đổi code có **verifier tương ứng với challenge đã gắn lúc phát hành code**.

Một số hệ thống dùng OAuth để đăng nhập (OIDC) rồi tạo **session cookie cục bộ**; hệ thống khác dùng SPA giữ access token để gọi API. Trong cả hai trường hợp, cần nhận diện rõ **credential nào thực sự được dùng ở mỗi ranh giới tin cậy**:

- **Authorization code:** mã tạm thời, dùng một lần, đổi tại token endpoint.
- **Access token:** cấp quyền truy cập resource server đúng audience và phạm vi quyền; có thể là JWT hoặc opaque.
- **Refresh token:** dùng để xin access token mới tại AS, cần bảo vệ và có vòng đời/thu hồi riêng.
- **ID token:** nếu dùng OIDC, cung cấp kết quả xác thực cho OIDC client; không mặc nhiên thay access token của API.
- **Session cookie:** nếu ứng dụng hoặc BFF quản lý phiên, credential có thể được browser tự gửi đến backend, phải chống CSRF, session fixation và chiếm phiên.

## 3. Mô hình đe dọa: authorization code bị lộ

Giả sử SPA đăng ký client_id **browser-app** với AS. Người dùng đăng nhập thành công, AS redirect về:

~~~text
https://app.example.test/oauth/callback?code=CODE_A&state=STATE_A
~~~

Nếu một bên khác nhìn thấy **CODE_A**, họ có thể thử gọi token endpoint để đổi lấy token. Code có thể lộ do log, cấu hình redirect sai, phần mềm độc hại, tiện ích trình duyệt, mã bên thứ ba hoặc lỗ hổng xử lý callback. Redirect URI được kiểm tra chính xác và HTTPS giảm rủi ro nhưng không thay việc bảo vệ bước đổi code.

**Không có PKCE**, một public client thường không có bí mật riêng để bảo vệ token request. Nếu AS chỉ kiểm tra code, client_id và redirect_uri, kẻ tấn công có những dữ liệu cần thiết có thể thử đổi code trước ứng dụng hợp lệ.

**Có PKCE**, AS đã lưu **code_challenge** cùng code. Bên đánh cắp chỉ có CODE_A nhưng không có **code_verifier** tương ứng sẽ bị từ chối ở token endpoint. Nếu kẻ tấn công lấy được cả code **và** verifier (ví dụ XSS đọc bộ nhớ/trạng thái JavaScript), PKCE không còn tạo được ranh giới bảo vệ đó.

~~~mermaid
sequenceDiagram
    participant B as Browser SPA
    participant AS as Authorization Server
    participant X as Bên đánh cắp code
    B->>B: Sinh code_verifier V và challenge C
    B->>AS: Authorization request với C, method=S256
    AS-->>B: Redirect callback với code A
    X->>AS: Đổi A, thiếu V hoặc gửi verifier sai
    AS-->>X: invalid_grant; không cấp token
    B->>AS: Đổi A cùng code_verifier V
    AS->>AS: SHA256(V) khớp C đã gắn với A
    AS-->>B: Token response theo quyền đã cấp
~~~

Trong thực tế, nếu code đã bị kẻ tấn công đổi thành công thì code không còn hợp lệ cho client; các thông báo lỗi không phân biệt rõ “code bị lộ” với “code đã dùng” để tránh lộ thông tin nội bộ.

## 4. Cơ chế PKCE với phương pháp S256

### 4.1. Hai giá trị quan trọng

- **code_verifier:** chuỗi ngẫu nhiên có entropy cao, do client sinh riêng cho từng authorization transaction. Theo RFC 7636, độ dài **43–128 ký tự**, dùng tập ký tự unreserved: chữ cái, chữ số, dấu gạch ngang, dấu chấm, gạch dưới và dấu ngã.
- **code_challenge:** giá trị dẫn xuất từ verifier. Với phương pháp **S256**, challenge được tính theo công thức:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

**BASE64URL-ENCODE** ở đây là dạng URL-safe **không có dấu đệm "="**. Không gửi raw code_verifier ở authorization endpoint. Phương pháp **plain** làm challenge bằng verifier, vì vậy không cung cấp mức bảo vệ chống việc kẻ khác nhìn thấy authorization request như S256; public browser client nên yêu cầu **S256** và không âm thầm hạ cấp xuống plain.

Một lựa chọn phổ biến là sinh **32 byte ngẫu nhiên bằng CSPRNG** rồi base64url không padding: kết quả có **43 ký tự** và chứa **256 bit entropy** trước khi mã hóa. Không dùng username, thời gian hiện tại, Math.random(), một hằng số trong source code hoặc một verifier chung cho nhiều phiên đăng nhập.

### 4.2. Vòng đời một giao dịch

1. SPA tạo **code_verifier V** mới, **code_challenge C = S256(V)** và **state** ngẫu nhiên cho giao dịch.
2. SPA lưu V cùng state, issuer dự kiến, redirect URI, thời điểm tạo và **nonce** nếu OIDC dùng nonce.
3. Browser được chuyển hướng tới **authorization endpoint đã được cấu hình tin cậy**, mang response_type=code, client_id, redirect_uri, scope, state, code_challenge và code_challenge_method=S256.
4. AS xác thực người dùng/nhận sự đồng ý theo chính sách, phát hành **authorization code A** có liên kết với **client_id, redirect_uri và C**.
5. Browser nhận callback với **code A** và **state**; client kiểm tra callback đúng giao dịch, issuer (nếu áp dụng), thời hạn và dấu hiệu request bất thường.
6. SPA gửi **A và V** tới **token endpoint của AS dự kiến**. AS tính S256(V), so với C đã lưu, xác nhận code chưa dùng/hết hạn và các ràng buộc khác.
7. Nếu hợp lệ, AS **tiêu thụ code một lần** rồi phát hành token theo ủy quyền. Client loại bỏ dữ liệu giao dịch nhạy cảm và xử lý token theo kiến trúc đã chọn.

~~~mermaid
sequenceDiagram
    participant SPA as Browser public client
    participant AS as Authorization Server
    participant API as Resource Server
    SPA->>SPA: V = random(32 bytes); C = base64url(SHA256(V))
    SPA->>SPA: Lưu V, state, issuer dự kiến cho giao dịch
    SPA->>AS: GET /authorize?response_type=code&code_challenge=C&method=S256...
    AS-->>SPA: Redirect ?code=A&state=STATE
    SPA->>SPA: Kiểm tra state, issuer và giao dịch
    SPA->>AS: POST /token: code=A, code_verifier=V, client_id
    AS->>AS: Code chưa dùng, đúng client/redirect, S256(V)=C
    AS-->>SPA: access token; ID/refresh token nếu được cấp
    SPA->>API: API request với access token cho đúng audience
    API-->>SPA: Kết quả theo scope và phân quyền
~~~

PKCE kiểm tra **mối liên kết giữa code và verifier**, không quyết định người dùng được phép làm gì ở API. AS và RS vẫn cần thực thi đúng loại token, issuer, audience, scope, thời gian sống và chính sách thu hồi.

## 5. Tạo verifier và challenge trong JavaScript browser

Browser hiện đại cung cấp **Web Crypto API**. Ví dụ sau sử dụng **crypto.getRandomValues** và **crypto.subtle.digest**, không cần thư viện mã hóa bên thứ ba. Mã mang tính minh họa cho frontend chạy trong **secure context**; không bao gồm toàn bộ phần lưu transaction, callback và token verification của sản phẩm thực tế.

~~~javascript
function base64url(bytes) {
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("");
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function secureRandomBase64url(byteCount = 32) {
  const bytes = new Uint8Array(byteCount);
  crypto.getRandomValues(bytes);
  return base64url(bytes);
}

async function createPkcePair() {
  // 32 byte ngẫu nhiên -> verifier dài 43 ký tự, đủ 256 bit entropy.
  const codeVerifier = secureRandomBase64url(32);
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(codeVerifier)
  );
  const codeChallenge = base64url(new Uint8Array(digest));

  return { codeVerifier, codeChallenge, codeChallengeMethod: "S256" };
}

// Dùng một lần cho mỗi authorization transaction.
const { codeVerifier, codeChallenge } = await createPkcePair();
const state = secureRandomBase64url(32);
const nonce = secureRandomBase64url(32); // Khi cần OIDC nonce
~~~

**Kiểm tra logic:** verifier là chuỗi ASCII thuộc tập ký tự hợp lệ. SHA-256 nhận byte của chuỗi verifier; challenge là base64url của 32 byte digest, không có dấu "=". Việc hash chuỗi nhị phân hoặc encode nhầm sang Base64 thường khác có thể làm AS từ chối verifier.

**Không sử dụng** Math.random() để tạo verifier, state hay nonce. **Không ghi** verifier/challenge nhạy cảm vào log debug. Challenge có thể xuất hiện trong authorization URL và không được coi là bí mật, nhưng verifier chỉ được gửi **đúng token endpoint** trong bước đổi code.

### 5.1. Khởi tạo authorization request

~~~javascript
const issuer = "https://identity.example.test"; // Cấu hình đáng tin cậy
const clientId = "browser-app";
const redirectUri = "https://app.example.test/oauth/callback";
const tokenEndpoint = issuer + "/token";
const authorizeEndpoint = issuer + "/authorize";

const { codeVerifier, codeChallenge } = await createPkcePair();
const state = secureRandomBase64url(32);
const nonce = secureRandomBase64url(32);
const transaction = {
  expectedIssuer: issuer,
  clientId,
  redirectUri,
  tokenEndpoint,
  codeVerifier,
  nonce,
  createdAt: Date.now()
};

// Chỉ minh họa một nơi lưu ngắn hạn. XSS cùng origin vẫn có thể đọc dữ liệu.
// Mỗi state là một khóa riêng để hỗ trợ nhiều tab/giao dịch song song.
sessionStorage.setItem("oauth_tx_" + state, JSON.stringify(transaction));

const url = new URL(authorizeEndpoint);
url.searchParams.set("response_type", "code");
url.searchParams.set("client_id", clientId);
url.searchParams.set("redirect_uri", redirectUri);
url.searchParams.set("scope", "openid profile");
url.searchParams.set("state", state);
url.searchParams.set("nonce", nonce);
url.searchParams.set("code_challenge", codeChallenge);
url.searchParams.set("code_challenge_method", "S256");

window.location.assign(url.toString());
~~~

Các URL trên là ví dụ giả lập. Trong hệ thống thật, endpoints phải lấy từ **metadata được xác minh** hoặc cấu hình tin cậy cho đúng issuer, không tự suy ra từ chuỗi issuer bằng phép nối path nếu AS có endpoints khác. Việc dùng **sessionStorage** có thể giúp giữ verifier qua một lần redirect trong cùng tab, nhưng không biến verifier thành bí mật trước **XSS, extension độc hại hoặc mã JavaScript cùng origin**. Phương án BFF thường lưu verifier phía máy chủ, giảm số credential trực tiếp nằm trong browser.

**Đừng tái sử dụng** một verifier cho tất cả những lần login, lưu verifier vĩnh viễn trong localStorage, hoặc gửi verifier trong authorization URL. Nếu có nhiều giao dịch song song, mỗi giao dịch phải có một state và verifier riêng; không giữ một biến toàn cục có thể bị request mới ghi đè.

## 6. Các HTTP request mẫu

### 6.1. Authorization request: chỉ gửi challenge

~~~http
GET /authorize?response_type=code&client_id=browser-app&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth%2Fcallback&scope=openid%20profile&state=<STATE>&nonce=<NONCE>&code_challenge=<CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

AS sau đó có thể redirect:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth/callback?code=<AUTH_CODE>&state=<STATE>&iss=https%3A%2F%2Fidentity.example.test
Cache-Control: no-store
~~~

Tham số **iss** ở authorization response trong ví dụ giả định AS hỗ trợ **RFC 9207**. Client nhiều AS cần kiểm tra issuer được trả về so với issuer dự kiến của giao dịch hoặc áp dụng biện pháp chống **authorization server mix-up** phù hợp. Không được chọn token endpoint theo một tham số URL chưa xác minh từ callback.

### 6.2. Token request: gửi verifier

~~~http
POST /token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTH_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth%2Fcallback&client_id=browser-app&code_verifier=<VERIFIER>
~~~

Token endpoint kiểm tra:

- Authorization code tồn tại, **chưa được dùng**, chưa hết hạn và thuộc đúng client.
- **redirect_uri** của token request khớp giá trị gắn với authorization code theo yêu cầu giao thức/AS.
- Method được ghi với code là **S256**, verifier hợp lệ và **BASE64URL(SHA256(ASCII(verifier)))** khớp challenge lưu lúc cấp code.
- Các điều kiện xác thực client và bảo mật khác nếu flow/kiểu client yêu cầu.

Public browser client **không gửi client_secret** và cũng không nên tự phát hành một giá trị secret được nhúng sẵn trong frontend. Nếu endpoint đăng ký public client mà AS vẫn đòi client_secret, cần xem lại đăng ký client và khả năng hỗ trợ browser client của AS.

Khi verifier sai hoặc code không còn hợp lệ, token endpoint nên trả **invalid_grant** phù hợp OAuth; không nên phát hành token mới hay “thử lại với plain”. Một phản hồi lỗi điển hình:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_grant"}
~~~

**Authorization code phải dùng một lần.** Nếu một request đổi code thành công, việc dùng lại cùng code cần bị từ chối dù verifier đúng. PKCE bổ sung bảo vệ cho code nhưng không thay giới hạn thời gian sống, client binding, redirect URI binding hoặc tính một lần của code.

## 7. Xử lý callback trong SPA một cách an toàn

Callback là nơi browser nhận **code**, **state** hoặc **error**. Client nên xử lý theo thứ tự để không gửi nhầm code tới AS hoặc nhầm giao dịch:

1. Nhận **code/state** qua response mode đã cấu hình. Với flow redirect dạng query, tránh để các scripts ngoài nhu cầu và bộ theo dõi phân tích thu thập URL callback.
2. Xác minh **state** có giao dịch đang chờ, chưa hết hạn, thuộc đúng tab/phiên logic, chưa sử dụng. Từ chối state bị thiếu, lặp hoặc không tìm thấy.
3. Từ transaction, lấy **expectedIssuer, clientId, tokenEndpoint, redirectUri, codeVerifier**. Không đọc các giá trị này từ URL tùy ý mà gán lại cấu hình.
4. Nếu AS sử dụng **RFC 9207**, xác minh **iss trong authorization response** khớp issuer dự kiến **trước khi đổi code**.
5. Loại bỏ thông tin nhạy cảm khỏi URL hiển thị khi có thể, ví dụ dùng History API sau khi đã lấy và kiểm tra dữ liệu callback, đồng thời không làm hỏng các lần khôi phục/refresh trang.
6. Gửi code và verifier tới **đúng token endpoint** với CORS và HTTPS; chỉ khi AS trả token hợp lệ mới ghi nhận giao dịch hoàn tất.
7. Nếu dùng OIDC, kiểm tra **ID token** theo issuer, audience dành cho client_id, chữ ký, thời hạn và **nonce** tương ứng; dùng thư viện OIDC có kiểm chứng cho bước xác minh giao thức.
8. Xóa code_verifier, state, nonce và dữ liệu giao dịch khi hoàn tất hoặc thất bại; ngăn **callback replay** và không tự động lặp token request với cùng code sau khi có kết quả không rõ.

**Pseudocode** tối giản:

~~~text
handleCallback(response):
    require exactlyOneValidState(response.state)
    tx = findPendingTransaction(response.state)
    require tx exists && !tx.expired && !tx.consumed

    if response.error exists:
        expireTransaction(tx)
        return genericLoginError

    require response.code exists
    require correctIssuerForAuthorizationResponse(response, tx)
    require tx.tokenEndpoint is registered trusted endpoint

    markTransactionExchanging(tx)
    tokens = POST tx.tokenEndpoint(
        grant_type = authorization_code,
        code = response.code,
        client_id = tx.clientId,
        redirect_uri = tx.redirectUri,
        code_verifier = tx.codeVerifier
    )

    require validTokenResponse(tokens, tx)
    if OIDC:
        validateIdTokenIssuerAudienceSignatureNonce(tokens.id_token, tx)
    consumeAndDeleteTransaction(tx)
    establishApplicationState(tokens)
~~~

Trong SPA, đánh dấu transaction đã xử lý chỉ bằng **sessionStorage** không bảo vệ trước mã độc cùng origin, nhưng giúp hạn chế bug callback đôi và việc tự gửi lại code do logic ứng dụng. Với hệ thống có nhiều tab hoặc nhiều instance, phải kiểm soát cạnh tranh phù hợp; AS vẫn là nơi buộc authorization code **chỉ dùng một lần**.

### 7.1. Tại sao phải kiểm tra state nếu đã có PKCE?

**PKCE** xác minh quyền sở hữu verifier khi đổi code. **state** liên kết authorization response với **giao dịch đăng nhập mà client đã tạo**, thường đồng thời phục vụ phòng chống CSRF và giữ bối cảnh của request. Một số profile có thể dùng PKCE như một phần của biện pháp chống CSRF khi đáp ứng điều kiện hỗ trợ của AS; trong browser client, giữ state đủ ngẫu nhiên và ràng buộc đúng transaction vẫn giúp dễ kiểm thử, theo dõi và tránh trộn các request.

Đặc biệt với nhiều issuer, **state đúng không tự xác minh issuer**. Client cần biết AS nào dự kiến cấp code và dùng cơ chế định danh issuer của authorization response theo giao thức.

### 7.2. OIDC nonce khác PKCE ra sao?

Khi dùng OIDC, **nonce** giúp ràng buộc ID token với yêu cầu xác thực thích hợp; client phải kiểm tra giá trị được trả trong ID token theo profile đang dùng. Nonce không phải verifier để đổi authorization code, còn **code_verifier** không thay việc kiểm tra chữ ký, audience, issuer hoặc nonce của ID token.

Không gửi ID token đến API chỉ vì nó là JWT ký hợp lệ. **Access token** mới là credential dành cho resource server; các API phải kiểm tra **audience, scope và token type** theo cấu hình của chúng.

## 8. Cấu hình authorization server dành cho browser client

PKCE chỉ an toàn khi AS **thực thi** đúng mọi ràng buộc; một frontend sinh challenge chuẩn nhưng backend token endpoint chấp nhận thiếu verifier thì cơ chế đã bị vô hiệu hóa.

Các yêu cầu triển khai quan trọng:

- Đăng ký SPA là **public client**, có **client_id** và redirect URI theo chính sách. Không giả định secret có thể giữ kín trong JavaScript.
- Bắt buộc **Authorization Code Flow với PKCE S256** cho client đó; từ chối request thiếu code_challenge, thiếu method hoặc dùng method không được phép theo chính sách.
- Tại thời điểm cấp code, lưu **code_challenge + method + client_id + redirect_uri** (và các điều kiện ủy quyền khác) vào trạng thái đáng tin cậy gắn với code.
- Tại token endpoint, kiểm tra verifier đúng chuẩn và **đối chiếu challenge đã lưu**; không cho client sửa method hoặc challenge của code trong bước đổi token.
- Code phải **ngắn hạn, dùng một lần**, được bảo vệ khỏi race condition trong môi trường nhiều instance.
- Kiểm tra **redirect_uri chính xác** theo cấu hình, không chấp nhận wildcard/open redirect thiếu kiểm soát.
- Cấu hình HTTPS bắt buộc cho authorization, callback và token endpoint (trừ môi trường thử nghiệm có ngoại lệ được kiểm soát).
- Nếu có nhiều AS, cung cấp/cấu hình **issuer metadata** và cơ chế chống mix-up; không để callback quyết định AS tùy ý.
- Token được cấp phải bị giới hạn scope, audience, lifetime và gắn với đúng client/ủy quyền. Việc PKCE hợp lệ **không phải lý do cấp nhiều quyền hơn**.

### 8.1. CORS tại token endpoint

Nếu SPA thực hiện **fetch** trực tiếp tới token endpoint từ origin khác, trình duyệt áp dụng **CORS**. AS phải hỗ trợ kiểu gọi này nếu chấp nhận browser client, thường cho phép những origin đã đăng ký phù hợp và các method/header cần thiết.

CORS là **chính sách truy cập phản hồi bằng JavaScript ở browser**; nó **không phải client authentication** và không chứng minh bên gọi là SPA chính hãng. Một chương trình không chạy trong browser vẫn có thể gửi HTTP request tới token endpoint; vì vậy server **phải kiểm tra code, verifier, client_id, redirect_uri và các điều kiện khác**, ngay cả khi cấu hình CORS chặt.

Tránh cấu hình phản hồi tùy tiện theo mọi Origin nếu chính sách không cho phép. Không dùng việc “CORS bị chặn” để che một thiết kế thiếu PKCE. Nếu token endpoint không hỗ trợ CORS cho SPA, cần điều chỉnh kiến trúc client/AS hợp lệ, ví dụ BFF, thay vì làm lộ secret trong frontend.

## 9. PKCE có giải quyết việc lưu access token hoặc refresh token không?

**Không.** PKCE bảo vệ bước đổi **authorization code**. Sau khi AS phát hành token, bảo mật phụ thuộc vào **nơi token được lưu, cách gửi và cách xác minh**.

| Vị trí/kiến trúc | Lợi ích | Giới hạn |
|---|---|---|
| **SPA giữ access token trong bộ nhớ** | Hạn chế dữ liệu tồn tại lâu sau khi đóng/làm mới trang | XSS/mã độc đang chạy cùng origin vẫn có thể đọc token hoặc phát request thay người dùng |
| **sessionStorage** | Gắn với tab và sống qua reload/redirect trong một số tình huống | JavaScript cùng origin có thể đọc; XSS vẫn là nguy cơ |
| **localStorage** | Dễ dùng, tồn tại qua nhiều lần mở trang | Bất kỳ JavaScript cùng origin bị chiếm quyền có thể đọc và đánh cắp; không nên coi là kho bí mật an toàn |
| **Cookie HttpOnly ở BFF** | JavaScript frontend không trực tiếp đọc token server-side; browser chỉ giữ session cookie | Phải chống CSRF, session fixation, bảo vệ cookie, XSS gây request trái ý và quản lý session |
| **Sender-constrained token (DPoP)** | Giảm giá trị của access/refresh token bị lộ khi không có khóa tương ứng | Không giải quyết XSS có thể yêu cầu browser ký proof; cần bảo vệ khóa và kiểm tra replay proof |
| **Refresh token rotation** | Có thể phát hiện reuse refresh token đã bị dùng | Cần trạng thái family, xử lý đồng thời, thu hồi và chính sách cấp refresh token phù hợp |

Nếu AS cấp **refresh token** cho browser client, hãy áp dụng **sender-constraining hoặc refresh token rotation** theo OAuth 2.0 Security BCP (RFC 9700), giới hạn vòng đời và phạm vi quyền. Không cho phép refresh token vô hạn mà không có bảo vệ khỏi lộ/reuse. Cần kiểm tra cả chính sách expiry, khả năng thu hồi, logout và tình huống trình duyệt mất token.

Trong mô hình **BFF**, backend thường là **confidential OAuth client** (nếu có khả năng giữ secret và xác thực client phù hợp) hoặc ít nhất là thành phần giữ code_verifier và token server-side. Trình duyệt gọi BFF bằng cookie phiên, còn BFF gọi API bằng access token. Đây là một lựa chọn kiến trúc hữu ích khi cần giảm phạm vi token xuất hiện trong JavaScript, nhưng việc **chống CSRF, session fixation và khóa phiên** vẫn rất quan trọng.

**Quan hệ với JWT và opaque token:** định dạng access token được cấp sau PKCE không thay đổi ý nghĩa của PKCE. JWT cần chữ ký đáng tin cậy cùng issuer/audience/exp/scope; opaque token cần nguồn introspection/tra cứu tin cậy. Không dùng thành công của PKCE để bỏ kiểm tra tại resource server.

## 10. Các tấn công PKCE không tự ngăn

| Tình huống | PKCE giúp đến đâu? | Biện pháp bổ sung |
|---|---|---|
| Bên khác lấy được **authorization code**, không có verifier | Chặn đổi code nếu AS kiểm tra S256 đúng | HTTPS, redirect URI chính xác, code ngắn hạn |
| Kẻ tấn công có **code và verifier** | Không ngăn được đổi code chỉ bằng PKCE | Chống XSS, hạn chế mã bên thứ ba, bảo vệ giao dịch, rà soát thiết bị |
| XSS hoạt động trong origin SPA | Có thể đọc verifier/token hoặc điều khiển luồng | CSP, escaping, giảm third-party scripts, SRI khi phù hợp, kiểm tra dependency |
| AS cho phép bỏ qua verifier khi đổi code | PKCE mất tác dụng | Bắt buộc PKCE tại AS; ca kiểm thử negative |
| Kẻ tấn công ép client dùng **plain** hoặc bỏ challenge | Có thể làm mất mục đích S256 | Cấu hình chỉ chấp nhận S256, không downgrade |
| Authorization response từ **AS sai** | PKCE không tự ràng buộc issuer | RFC 9207/biện pháp chống mix-up, issuer được cấu hình tin cậy |
| Token trả về sai audience/scope | PKCE không phải kiểm tra phân quyền | AS cấp quyền tối thiểu; RS kiểm tra aud/scope và policy |
| Access token bị đánh cắp sau login | Không bảo vệ token đã phát hành | Lifetime ngắn, sender-constraining, không lộ token qua URL/log |
| Refresh token bị lộ hoặc phát lại | Không phát hiện reuse của refresh token | Rotation, token family, sender-constraining và thu hồi |
| Session cookie bị fixation tại BFF | PKCE không đổi cookie phiên | Rotate session ID khi đăng nhập, vô hiệu hóa ID cũ |
| OAuth login CSRF/code injection | PKCE giúp ràng buộc code với giao dịch nhưng không giải quyết mọi biến thể | state, issuer, redirect URI, nonce khi OIDC, xác minh giao dịch |

**Ghi nhớ:** cơ chế chống một hình thức replay tại bước **đổi code** không đồng nghĩa có cơ chế chống replay cho mọi bearer token về sau. Mỗi credential có **đối tượng nhận, nơi lưu, vòng đời và phương thức kiểm tra** riêng.

## 11. Sai sót triển khai thường gặp

### 11.1. Dùng một verifier dùng chung

~~~text
Sai:
  const CODE_VERIFIER = "hard-coded-value-for-all-users-and-logins"

Đúng:
  login attempt #1: verifier V1, state S1
  login attempt #2: verifier V2, state S2
  V1 và V2 độc lập, ngẫu nhiên, mỗi giá trị chỉ dùng cho giao dịch của nó
~~~

Verifier cố định hoặc tái sử dụng làm mất phần lớn khả năng bảo vệ khi một giao dịch bị quan sát. Với nhiều tab, tránh lưu duy nhất một khóa sessionStorage tên **code_verifier** rồi vô tình ghi đè khi tab thứ hai bắt đầu login.

### 11.2. Tạo verifier thiếu entropy

~~~javascript
// Không an toàn:
const verifier = Date.now().toString() + Math.random().toString();

// Dùng CSPRNG:
const verifier = secureRandomBase64url(32);
~~~

PKCE đòi bí mật không thể đoán thực tế. SHA-256 không “cứu” được một verifier sinh từ dữ liệu dễ đoán.

### 11.3. Gửi verifier ở authorization request

~~~text
Sai:
  /authorize?...&code_verifier=V

Đúng:
  /authorize?...&code_challenge=S256(V)&code_challenge_method=S256
  /token: code_verifier=V
~~~

Nếu verifier đi cùng authorization request, một bên quan sát request có thể lấy cả code_challenge lẫn verifier, làm giảm đáng kể bảo vệ PKCE dự kiến.

### 11.4. Tin redirect hoặc issuer từ callback

~~~text
Sai:
  tokenEndpoint = query.get("token_endpoint")
  issuer = query.get("issuer")
  POST code đến URL đó

Đúng:
  tx = transactionStore.get(validatedState)
  expectedIssuer = tx.expectedIssuer
  tokenEndpoint = trustedMetadata[expectedIssuer].tokenEndpoint
  kiểm tra response issuer rồi mới POST code
~~~

Đây cũng là nguyên tắc ngăn **authorization server mix-up**: không để dữ liệu chưa được xác thực điều hướng nơi gửi authorization code hoặc verifier.

### 11.5. Quên loại bỏ authorization code khỏi URL

Callback chứa code ở query có thể xuất hiện trong lịch sử, log hoặc dữ liệu phân tích. Client nên xử lý và dọn URL một cách sớm, kiểm soát Referrer-Policy và tránh load script bên thứ ba ở callback. Tuy nhiên, dọn URL không thay việc code **một lần, ngắn hạn** và **PKCE bắt buộc** tại AS.

### 11.6. Xem CORS như xác thực client

CORS chỉ hạn chế tương tác của browser với response từ origin khác; nó không biến JavaScript SPA thành bên giữ bí mật. Một request ngoài browser không nhất thiết tuân theo CORS. Public client vẫn phải có PKCE và các kiểm tra OAuth phía AS.

## 12. Bộ kiểm thử PKCE cho public browser client

### 12.1. Ma trận ca kiểm thử tích hợp

| Trường hợp | Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|---|
| **Luồng S256 thành công** | Challenge từ verifier V, code chưa dùng, client/redirect đúng | Token được cấp theo quyền đã đồng ý |
| **Thiếu code_verifier** | Token request không có verifier | Bị từ chối, không cấp token |
| **Verifier khác** | Code tạo từ V1, token request gửi V2 | Bị từ chối với invalid_grant thích hợp |
| **Verifier sai định dạng** | Quá ngắn, quá dài hoặc chứa ký tự ngoài chuẩn | Bị từ chối |
| **Sai method** | Authorization request thiếu/đòi plain khi policy yêu cầu S256 | Bị từ chối, không downgrade |
| **Không có challenge** | Public client xin authorization code mà không PKCE | AS từ chối theo chính sách bắt buộc PKCE |
| **Authorization code dùng lại** | Đổi A thành công rồi gửi A lần hai với đúng verifier | Lần sau bị từ chối |
| **Code hết hạn** | Token request sau khi code timeout | Bị từ chối |
| **Code không thuộc client** | Dùng client_id B để đổi code của client A | Bị từ chối |
| **Redirect URI không khớp** | Token request dùng redirect URI không đúng với giao dịch | Bị từ chối |
| **State lạ hoặc đã dùng** | Callback với state không khớp | Client không gửi token request |
| **Issuer mismatch** | State của AS_A nhưng response iss=AS_B | Client không gửi code/verifier đến token endpoint B |
| **Nhiều tab đồng thời** | Hai login tạo hai transaction | Không ghi đè verifier, mỗi callback chỉ đổi code thuộc giao dịch của nó |
| **ID token không khớp nonce** | OIDC trả nonce khác transaction | Không chấp nhận đăng nhập |
| **CORS hợp lệ** | SPA từ origin được phép gọi token endpoint | Trình duyệt nhận response theo cấu hình được phép |
| **CORS sai origin** | Browser origin không được phép | Không đọc được response qua browser; AS vẫn kiểm tra OAuth của mọi HTTP request |
| **Token sai aud/scope** | Token hợp lệ về mật mã nhưng không dành cho API/quyền yêu cầu | RS từ chối |
| **Refresh token bị dùng lại** | Rotation: gửi lại token đã dùng | AS xử lý reuse và thu hồi family theo chính sách |

### 12.2. Kiểm thử công thức S256

Đối chiếu triển khai Web Crypto với **test vector trong RFC 7636**:

~~~text
code_verifier:
  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

S256(code_verifier):
  E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Giá trị trên là **test vector công khai**, không dùng làm verifier thực tế. Nếu code JavaScript tạo challenge khác, cần kiểm tra encoding (ASCII/UTF-8 đối với tập ký tự verifier hợp lệ), SHA-256, base64url và việc loại bỏ dấu "=".

### 12.3. Kiểm thử qua browser và API

Ngoài unit test công thức, nên kiểm thử end-to-end qua **browser thật** hoặc công cụ mô phỏng chính xác hành vi redirect, sessionStorage và CORS. Giả lập hai đăng nhập đồng thời, refresh trang ở callback, callback lỗi, pop-up login và người dùng nhấn Back. Kiểm tra mọi token request được gửi **đúng AS**, và ứng dụng không gửi lại code/verifier khi giao dịch đã hoàn tất.

Khi đo log/network ở môi trường kiểm thử, che **authorization code, verifier, access token, refresh token** khỏi kết quả được xuất hoặc chia sẻ; việc test đúng không có nghĩa các credential ấy được phép lưu công khai.

## 13. Hướng dẫn triển khai có thể kiểm tra

Đối với một SPA dùng OAuth 2.0/OIDC, đội phát triển có thể tự xác minh:

1. **Client registration:** public client, redirect URI đúng, Authorization Code + PKCE S256 bắt buộc; không có client secret trong bundle.
2. **Khởi tạo flow:** mỗi lần login tạo verifier/state mới đủ entropy, nonce khi OIDC yêu cầu; các giá trị được gắn với đúng transaction và issuer.
3. **Authorization request:** gửi challenge S256, không gửi verifier; URL đến authorization endpoint tin cậy, đúng scope.
4. **Callback:** kiểm tra state và issuer trước khi đổi code, từ chối callback sai/hết hạn/đã dùng.
5. **Token request:** POST tới token endpoint được cấu hình, kèm verifier đúng, code dùng một lần; CORS được thiết lập phù hợp.
6. **Nhận token:** kiểm tra ID token theo OIDC nếu có; không sử dụng ID token thay access token.
7. **Gọi API:** dùng access token có audience/scope phù hợp; resource server kiểm tra issuer, aud, exp và quyền.
8. **Lưu token:** đánh giá rủi ro XSS, third-party scripts và khả năng áp dụng BFF; hạn chế thời gian sống credential trong browser.
9. **Refresh/logout:** nếu có refresh token, yêu cầu rotation hoặc sender-constraining phù hợp; thu hồi và xóa trạng thái theo chính sách.
10. **Giám sát và kiểm thử:** bắt buộc ca verifier sai/thiếu, downgrade, state/issuer mismatch, concurrency, code replay và token lộ qua log.

Trong ứng dụng thực tế nên ưu tiên một thư viện OAuth/OIDC được duy trì, hỗ trợ PKCE, state, nonce, issuer validation và kiểm tra callback theo chuẩn. Tự viết một phần tạo challenge là đơn giản, nhưng **toàn bộ giao thức đăng nhập** gồm nhiều quy tắc khó kiểm soát bằng những đoạn code rời rạc.

## 14. Tự kiểm tra kiến thức

1. Vì sao một SPA chạy trong trình duyệt là public client dù mã JavaScript được minify và triển khai trên HTTPS?
2. code_verifier và code_challenge khác nhau như thế nào? Vì sao authorization request chỉ gửi challenge?
3. Tại sao sinh 32 byte bằng **crypto.getRandomValues** là lựa chọn phù hợp, còn Math.random() không phù hợp?
4. Công thức **S256** chính xác là gì? Base64url có thêm dấu "=" ở cuối không?
5. Nếu kẻ tấn công có authorization code nhưng không có verifier, token endpoint phải xử lý thế nào?
6. Nếu kẻ tấn công có **cả code và verifier** do XSS, PKCE còn bảo vệ được phần nào?
7. Vì sao không được chọn token endpoint dựa vào một URL lấy trực tiếp từ callback?
8. **state**, **PKCE**, **OIDC nonce** và **issuer identification** có vai trò riêng ra sao?
9. CORS có thể thay thế client authentication hoặc PKCE được không? Vì sao?
10. Sau khi đổi code thành công, resource server cần kiểm tra những thông tin nào của access token?
11. Vì sao SPA dùng PKCE vẫn có thể bị đánh cắp refresh token? Nên thiết kế refresh token theo chính sách nào?
12. Khi một user mở hai tab login cùng lúc, cách lưu một verifier duy nhất có thể gây lỗi gì?
13. BFF thay đổi chỗ lưu access token và code_verifier như thế nào, và vì sao cookie phiên của BFF vẫn cần bảo vệ?
14. Hãy viết kịch bản kiểm thử chứng minh code đã dùng một lần không thể đổi lại dù verifier vẫn đúng.

**Ghi nhớ:** Với **public browser client**, dùng **Authorization Code Flow + PKCE S256** để ràng buộc authorization code với một verifier ngẫu nhiên **riêng từng giao dịch**. AS phải thực thi ràng buộc đó khi đổi code. Client vẫn phải kiểm tra state/issuer/nonce, còn token và phiên sau đăng nhập vẫn cần được lưu trữ, xác minh, giới hạn quyền, thu hồi và phòng chống replay phù hợp.

## Tài liệu tham khảo

- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients:** đặc tả code_verifier, code_challenge, S256, validation và test vector.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code grant, token endpoint, redirect URI, state và các loại client.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị PKCE, bảo vệ authorization code/refresh token, issuer mix-up và các rủi ro OAuth hiện đại.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** tham số iss của authorization response để chống nhầm nhà phát hành.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata và endpoint của authorization server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** cơ chế ràng buộc access/refresh token với khóa để giảm khả năng sử dụng token bị lộ.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** xác minh JWT access token theo issuer, audience, expiration, client và token type.
- **OpenID Connect Core 1.0:** xác minh ID token và nonce trong flow OIDC.
- **OWASP OAuth 2.0 Cheat Sheet và OAuth 2.0 for Browser-Based Apps guidance:** triển khai OAuth/PKCE trong browser, mô hình token storage và bảo vệ ứng dụng web.

