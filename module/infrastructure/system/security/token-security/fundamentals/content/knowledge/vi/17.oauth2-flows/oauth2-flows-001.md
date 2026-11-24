# Authorization Code flow

## 1. Authorization Code flow giải quyết vấn đề gì?

Trong chương **OAuth2 flows** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, **Authorization Code flow** là luồng OAuth 2.0 cho phép một ứng dụng (client) nhận **access token** sau khi người dùng được chuyển tới **Authorization Server (AS)** để xác thực và thực hiện quy trình ủy quyền theo chính sách. Thay vì đưa access token trực tiếp qua bước chuyển hướng trình duyệt, AS cấp một **authorization code** ngắn hạn; client mang code đến **token endpoint** để đổi lấy token.

Hãy xét ứng dụng quản lý đơn hàng **Shop Web**:

1. Alice chọn chức năng **Xem đơn hàng**.
2. Shop Web cần access token dành cho **Orders API**, nhưng không nên yêu cầu Alice đưa mật khẩu cho Shop Web.
3. Shop Web chuyển Alice tới Authorization Server tin cậy.
4. Sau khi xác thực/ủy quyền, AS chuyển trình duyệt về redirect URI của Shop Web cùng một **authorization code**.
5. Shop Web đổi code tại token endpoint, dùng **PKCE** và client authentication nếu thuộc loại confidential client.
6. Shop Web gọi Orders API bằng access token đúng audience và scope, thông thường qua `Authorization: Bearer <ACCESS_TOKEN>`.

Điều quan trọng là **authorization code không phải access token**. Code là một grant tạm thời, dùng một lần, chỉ có thể được đổi khi thỏa các ràng buộc của luồng. Nó không được đem gọi resource server và không nên xuất hiện trong log hay công cụ analytics.

### 1.1. Mục tiêu bảo mật

Authorization Code flow hiện đại cần đạt các mục tiêu:

- Không để **client thu thập mật khẩu** của người dùng như một phần luồng cấp quyền thông thường.
- Tránh gửi **access token qua front channel** (địa chỉ/redirect của trình duyệt).
- Ràng buộc authorization response với **request gốc, client, redirect URI và issuer**.
- Dùng **PKCE** để hạn chế kẻ chặn authorization code đem code đi đổi token.
- Đảm bảo AS chỉ cấp **subject, scope, resource/audience và thời hạn** đúng grant/policy.
- Cho phép resource server **tự xác minh token và phân quyền đối tượng**, không chỉ tin client.

**Lưu ý:** OAuth 2.0 chủ yếu là **khung ủy quyền (authorization)**; bản thân OAuth Authorization Code flow không phải một giao thức đăng nhập hoàn chỉnh cho client. Nếu client cần danh tính người dùng đã xác thực, hãy áp dụng **OpenID Connect (OIDC)** với ID token và các quy tắc xác minh OIDC.

### 1.2. Phạm vi bài học

Ta tập trung vào Authorization Code + **PKCE S256**, các ranh giới tin cậy của client, Authorization Server và resource server, cũng như việc phát hành và sử dụng access token, ID token (khi có OIDC) và refresh token. Các thuật ngữ **JWT/opaque** nói về định dạng access token, không phải một loại OAuth flow.

## 2. Các vai trò và điểm cuối trong luồng

| Vai trò hoặc thành phần | Trách nhiệm |
|---|---|
| **Resource owner** | Người dùng hoặc chủ thể có quyền đối với dữ liệu; trong ví dụ là Alice |
| **User agent** | Trình duyệt/thiết bị nơi Alice tương tác với AS và client |
| **OAuth client** | Shop Web, ứng dụng yêu cầu phạm vi truy cập thay cho người dùng |
| **Authorization Server (AS)** | Xác thực/ngữ cảnh ủy quyền, kiểm tra client/policy và phát hành code/token |
| **Resource Server (RS)** | Orders API, nhận access token, xác minh token và kiểm tra quyền trên từng đơn hàng |
| **Authorization endpoint** | Nhận authorization request qua user agent, xử lý tương tác và trả code hoặc lỗi |
| **Token endpoint** | Nhận authorization code cùng bằng chứng cần thiết để cấp access token và các token khác khi thích hợp |
| **Redirect URI** | Điểm nhận authorization response mà client đã đăng ký với AS |

Ví dụ các điểm cuối:

~~~text
Authorization endpoint: https://login.example.com/oauth2/authorize
Token endpoint:         https://login.example.com/oauth2/token
Redirect URI:           https://shop.example.com/login/oauth2/code/shop
Resource Server:        https://orders.example.com
~~~

Các URL chỉ minh họa. OAuth không yêu cầu mọi sản phẩm dùng đúng những path này. Client cần lấy metadata/endpoint của **issuer đã tin cậy**, không chọn một token endpoint bất kỳ theo dữ liệu redirect không đáng tin.

### 2.1. Public client và confidential client

| Loại client | Ví dụ | Khả năng giữ client secret |
|---|---|---|
| **Public client** | SPA chạy trong browser; ứng dụng mobile/native phân phối cho người dùng | Không thể coi secret nhúng trong app là bí mật dài hạn |
| **Confidential client** | Web backend/BFF do tổ chức kiểm soát và có secret manager | Có thể giữ secret/khóa riêng, xác thực với token endpoint |

**PKCE áp dụng cho Authorization Code flow và đặc biệt quan trọng với public client.** Theo best current practice, nên dùng PKCE cho mọi loại client khi có thể, kể cả confidential client để giảm rủi ro code injection/interception. Với confidential client, **PKCE không thay thế client authentication** đã được đăng ký. Với public client, `client_id` chỉ là định danh, không chứng minh ứng dụng đang chạy là một thực thể giữ bí mật.

### 2.2. Ba kênh truyền cần phân biệt

| Kênh | Ví dụ | Thông tin chính |
|---|---|---|
| **Front channel** | Browser điều hướng đến authorization endpoint rồi quay lại redirect URI | Request metadata, **authorization code**, state, issuer khi hỗ trợ |
| **Back channel/token exchange** | Client gửi HTTP POST tới token endpoint của AS | Code, code_verifier, client authentication khi áp dụng; nhận token |
| **Resource request** | Client gọi Orders API qua HTTPS | **Access token** dùng trong Authorization header |

**Không để access token hoặc refresh token di chuyển qua URL của browser chỉ vì authorization code được phép đi qua redirect URI trong luồng này.**

## 3. Sơ đồ tổng thể Authorization Code + PKCE

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant C as Shop Web / OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API
    U->>C: Muốn xem đơn hàng
    C->>C: Tạo state, code_verifier, code_challenge
    C-->>B: Redirect tới AS /authorize
    B->>AS: response_type=code, client_id, redirect_uri, scope, state, PKCE
    AS->>AS: Xác thực Alice, policy/consent nếu cần
    AS->>AS: Ràng buộc code với client, redirect URI, PKCE, grant
    AS-->>B: 302 về redirect_uri với code, state và issuer nếu hỗ trợ
    B->>C: GET callback với code và state
    C->>C: Kiểm tra state/issuer và ngữ cảnh request
    C->>AS: POST /token với code, redirect_uri, code_verifier, client authentication khi cần
    AS->>AS: Code còn hạn, một lần, đúng client, redirect, PKCE và grant
    AS-->>C: Access token, ID/refresh token nếu đủ điều kiện
    C->>RS: Authorization: Bearer access_token
    RS->>RS: Xác minh token, audience, scope, quyền trên resource
    RS-->>C: Dữ liệu được phép hoặc từ chối
~~~

Sơ đồ biểu diễn logic luồng. Với SPA, các bước client/AS/token endpoint có thể do SDK chạy ở browser; với BFF, code exchange và token storage thường ở backend. Dù kiến trúc khác nhau, **các ràng buộc PKCE, client, redirect URI, issuer và quyền cấp token vẫn phải được thực thi**.

### 3.1. Vì sao có hai bước phát hành?

AS không trả access token ngay trong URL redirect. Thay vào đó, code được gửi qua front channel và **chỉ đổi ở token endpoint** với những bằng chứng cần thiết. Cách tách này giúp giảm đường lộ access token qua URL/history/script. Nhưng authorization code **vẫn nhạy cảm**, phải có TTL ngắn, chỉ dùng một lần và bị ràng buộc với đúng client/redirect URI/PKCE.

## 4. Bước 1: client tạo authorization request

Client phải xác định **issuer tin cậy**, `client_id`, `redirect_uri` đã đăng ký, scopes và resource/audience mong muốn trong giới hạn grant. Với PKCE, client tạo một cặp:

~~~text
code_verifier  = chuỗi mật mã ngẫu nhiên riêng cho một authorization request
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

`code_verifier` phải được giữ riêng cho luồng đang chạy và chỉ gửi đến **token endpoint** khi đổi code. Trên authorization request qua browser, client gửi **code_challenge**, không gửi code_verifier.

### 4.1. Ví dụ URL /authorize

~~~http
GET /oauth2/authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&scope=openid%20orders%3Aread&state=<RANDOM_STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Đây là ví dụ minh họa; trong request thật, placeholder được thay bằng giá trị sinh an toàn và tham số phải được mã hóa theo HTTP/URL. `openid` ở ví dụ thể hiện đây còn là yêu cầu **OIDC**; nếu chỉ dùng OAuth 2.0 thuần để cấp quyền API, không bắt buộc thêm `openid`.

| Tham số | Ý nghĩa |
|---|---|
| `response_type=code` | Yêu cầu authorization code, không yêu cầu access token qua redirect |
| `client_id` | Định danh client đã đăng ký ở AS |
| `redirect_uri` | URI callback phải tuân thủ chính sách đăng ký và đối chiếu tại token endpoint |
| `scope` | Phạm vi xin quyền, ví dụ `orders:read`; khi có `openid` là yêu cầu OIDC |
| `state` | Liên kết authorization response với request/phiên đã khởi tạo, giảm nguy cơ CSRF/mix-up theo thiết kế |
| `code_challenge` | Giá trị challenge tính từ verifier, liên kết code với client đang giữ verifier |
| `code_challenge_method=S256` | Dùng SHA-256 thay vì phương pháp yếu hơn |

Trong triển khai hỗ trợ **Resource Indicators (RFC 8707)**, client còn có thể gửi tham số `resource` theo hợp đồng để xin token dành cho API cụ thể; AS phải kiểm tra client/grant có quyền yêu cầu resource đó hay không.

### 4.2. Ví dụ tính PKCE S256 bằng Java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceValues {
    private static final SecureRandom RANDOM = new SecureRandom();

    public record Pair(String verifier, String challenge) {}

    public static Pair create() throws Exception {
        byte[] entropy = new byte[32];     // 256 bit entropy
        RANDOM.nextBytes(entropy);

        String verifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(entropy);

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));

        String challenge = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);

        return new Pair(verifier, challenge);
    }
}
~~~

Mã nhằm minh họa cách tính. RFC 7636 yêu cầu `code_verifier` gồm **43–128 ký tự** trong tập unreserved được phép và có entropy phù hợp; dùng 32 byte ngẫu nhiên rồi Base64url không padding tạo verifier dài 43 ký tự. Ứng dụng thực tế nên để **OAuth/OIDC SDK đã được duy trì** tạo/lưu verifier và liên kết nó với authorization request, không tự xây toàn bộ security flow.

Không dùng timestamp, user ID, một mật khẩu cố định hoặc `Math.random()` để tạo code_verifier.

### 4.3. `state` và ngữ cảnh request

Client tạo state bằng dữ liệu không thể đoán, ràng buộc với phiên/request gốc. Ví dụ conceptual:

~~~text
pending_authorization_request:
    state_hash
    issuer
    client_id
    redirect_uri
    code_verifier (bảo vệ khỏi rò rỉ)
    requested_scope
    created_at, expires_at
~~~

Đây là metadata minh họa, không phải chuẩn lưu trữ. Khi callback về, client kiểm tra state, issuer, request chưa được tiêu thụ và phiên liên quan. **Không dùng một state cố định cho mọi người dùng** hoặc chỉ mã hóa user ID rồi coi đó là chống CSRF.

Một số profile có thể dùng cơ chế PKCE/nonce và request binding để đạt CSRF protection theo BCP; nếu sử dụng state, phải tạo và xác minh đúng. **Không bỏ qua bảo vệ request-response chỉ vì ứng dụng đã dùng PKCE.**

## 5. Bước 2: Authorization Server xác thực và cấp authorization code

Trình duyệt điều hướng đến authorization endpoint của issuer. AS phải:

1. Kiểm tra client tồn tại, được dùng Authorization Code flow và có redirect URI hợp lệ.
2. Kiểm tra tham số PKCE, scope, resource/audience và chính sách dành cho client.
3. Xác thực Alice khi cần; tái sử dụng phiên SSO nếu được chính sách cho phép.
4. Áp consent hoặc phê duyệt quản trị khi phù hợp; **không cấp quyền chỉ vì client đã yêu cầu**.
5. Tạo authorization code ngắn hạn không thể đoán, liên kết code với client, redirect URI, PKCE và grant thực sự được cấp.
6. Trả response về redirect URI đã đăng ký qua user agent.

**AS có trách nhiệm chọn đúng user/subject và scopes được cấp.** Việc client đính kèm `login_hint`, scope hoặc resource trong request không chứng minh client được phép tự quyết định danh tính, quyền admin hoặc audience.

### 5.1. Metadata cần ràng buộc với authorization code

Một cách biểu diễn khái niệm:

| Dữ liệu | Mục đích |
|---|---|
| `code_id`/`code_verifier_hash` hoặc định danh mã an toàn | Tra cứu code đủ khó đoán |
| `client_id` | Code chỉ được đổi bởi đúng client |
| `redirect_uri` | Liên kết với redirect URI của authorization request gốc |
| `code_challenge` + `method` | Kiểm tra PKCE ở token endpoint |
| `subject` | Danh tính do AS xác minh trong grant |
| `granted_scopes` | Scope được cấp thực tế, không phải chỉ scope client xin |
| `allowed_resources` | Resource/audience mà grant cho phép |
| `issued_at`, `expires_at` | Hạn sử dụng code |
| `used`/`consumed_at` | Ngăn đổi code nhiều lần |
| `issuer`, `authorization_context` | Ngữ cảnh bảo vệ các bước sau |

Đây là **metadata minh họa**, không phải schema OAuth bắt buộc. Code có thể là giá trị opaque gắn với trạng thái ở server hoặc được AS triển khai theo cơ chế khác, nhưng các bất biến bảo mật phải được duy trì.

### 5.2. Redirect về client

Sau khi Alice hoàn tất bước cần thiết, AS phản hồi qua browser:

~~~http
HTTP/1.1 302 Found
Location: https://shop.example.com/login/oauth2/code/shop?code=<AUTHORIZATION_CODE>&state=<ORIGINAL_STATE>&iss=https%3A%2F%2Flogin.example.com
Cache-Control: no-store
~~~

`iss` trong ví dụ là **authorization response issuer identifier** khi AS hỗ trợ RFC 9207. Client nên so sánh issuer này với issuer được lưu từ request gốc để giảm nguy cơ **authorization server mix-up** khi làm việc với nhiều AS. Nếu AS/client dùng cơ chế khác theo profile để chống mix-up, cần thực thi đúng cơ chế đó, không tự lấy issuer từ một URL không đáng tin.

`state` trong response phải khớp với request tương ứng. Không dùng một code hoặc state từ luồng của tab khác để kết thúc phiên hiện tại.

**Chỉ có authorization code trong URL callback không có nghĩa được đặt access token trong URL.** Code được thiết kế để dùng một lần và cần PKCE/client/redirect binding trước khi thành token. Nhưng code vẫn là **credential nhạy cảm**: không log query chứa code, không gửi qua analytics hay redirect đến open redirect.

### 5.3. Redirect URI phải được kiểm soát

AS cần kiểm tra redirect URI theo hồ sơ client và quy tắc giao thức:

- Với web callback thông thường, dùng URI được đăng ký và đối chiếu **chính xác** theo chính sách.
- Không dùng wildcard hoặc so prefix kiểu `startsWith("https://shop.example.com")` để chấp nhận `https://shop.example.com.attacker.test/...`.
- Không cho client tự chuyển code tới URL khác qua một open redirect có thể bị lạm dụng.
- Native app loopback URI có ngoại lệ về **cổng động** theo RFC 8252; phải xử lý theo profile, không biến ngoại lệ đó thành wildcard cho mọi redirect.
- Ở token endpoint, đối chiếu redirect URI của request đổi code với URI của authorization request **khi tham số đó đã được dùng/được yêu cầu theo giao thức**.

Nếu redirect URI không hợp lệ, AS không được gửi authorization code hoặc chi tiết lỗi nhạy cảm tới URI đó.

## 6. Bước 3: client nhận callback và kiểm tra response

Client nhận request callback từ browser. Trước khi đổi code, nó cần:

1. Tìm authorization request đang chờ bằng state/phiên đã được bảo vệ.
2. Kiểm tra **state** khớp, chưa hết hạn, không bị dùng lại.
3. Kiểm tra **issuer** đúng AS đã bắt đầu và client registration phù hợp, nhất là khi dùng nhiều issuer.
4. Kiểm tra callback tới đúng redirect URI dự kiến.
5. Kiểm tra response có code hoặc một lỗi OAuth hợp lệ, **không coi tham số do caller tự thêm là claims đã xác minh**.
6. Lấy đúng code_verifier đã tạo riêng cho request gốc và chuẩn bị đổi code tại **token endpoint cố định của issuer đó**.

### 6.1. Không đưa code sang token endpoint của issuer khác

Giả sử một client hỗ trợ cả:

~~~text
https://login.company-a.example
https://login.partner-b.example
~~~

Nếu code từ AS A được chuyển nhầm sang token endpoint AS B, client có thể làm lộ code hoặc tạo **mix-up attack**. Do đó, pending authorization request phải giữ quan hệ giữa **issuer ↔ client registration ↔ redirect URI ↔ state/PKCE ↔ token endpoint**. Chỉ tin metadata của AS đã cấu hình, không suy token endpoint từ callback do browser cung cấp.

### 6.2. Lỗi từ authorization endpoint

Trong trường hợp người dùng từ chối consent, AS có thể trả response lỗi thích hợp:

~~~http
HTTP/1.1 302 Found
Location: https://shop.example.com/login/oauth2/code/shop?error=access_denied&state=<ORIGINAL_STATE>
~~~

Client cần kiểm tra state/issuer/ngữ cảnh trước khi xử lý lỗi và phản hồi người dùng. Không gửi error description chứa secret hoặc thông tin nội bộ nhạy cảm vào URL. Khi redirect URI không an toàn hoặc không hợp lệ, AS phải xử lý lỗi tại chính AS thay vì redirect dữ liệu tới nơi không tin cậy.

## 7. Bước 4: đổi authorization code tại token endpoint

Sau khi kiểm tra callback, client gửi **HTTP POST** trực tiếp tới token endpoint của AS tin cậy. Với public client:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&client_id=shop-web&code_verifier=<CODE_VERIFIER>
~~~

Request ở trên mang **code_verifier**, không phải code_challenge. AS tính lại challenge theo phương thức được ghi cùng authorization code và so sánh với challenge của request gốc.

### 7.1. Confidential client còn phải xác thực client

Với backend/confidential client đã đăng ký client authentication bằng secret, một request có thể sử dụng HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <ENCODED_CLIENT_ID_AND_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&code_verifier=<CODE_VERIFIER>
~~~

Giá trị Basic chỉ là placeholder. **Base64 không phải mã hóa**, nên client secret phải được giữ ở backend/secret manager và truyền qua HTTPS. Các phương thức khác như **private_key_jwt** và **mTLS client authentication** có thể dùng nếu AS/client hỗ trợ và đã đăng ký.

**Public client không thể giữ một client secret bí mật dài hạn chỉ bằng cách nhúng secret trong JavaScript hoặc app mobile.** `client_id` một mình không được coi là bằng chứng xác thực confidential client.

### 7.2. Các kiểm tra bắt buộc tại token endpoint

| Kiểm tra | Nếu sai thì sao? |
|---|---|
| Client tồn tại và được phép dùng `authorization_code` | Không phát hành token |
| Confidential client xác thực bằng phương thức đã đăng ký | Không cấp token khi chứng thực client thất bại |
| Code tồn tại, còn hạn và chưa dùng | Từ chối code sai/hết hạn/dùng lại |
| Code thuộc đúng client | Ngăn client khác đổi code bị chặn |
| Redirect URI đúng code/request gốc | Ngăn code được dùng ở redirect sai |
| PKCE verifier khớp challenge đã lưu và S256 | Ngăn kẻ chỉ có code đổi được token |
| Issuer/ngữ cảnh cấp code đúng | Tránh code/token mix-up |
| Scope, resource, subject trong grant hợp lệ | Ngăn tăng quyền bằng tham số token request |
| Code chỉ được tiêu thụ **một lần** | Ngăn double redemption/race |

**Bảo vệ PKCE downgrade:** nếu authorization request đã có code_challenge, token endpoint không được bỏ qua kiểm tra PKCE chỉ vì request đổi code không chứa verifier. AS cũng phải áp chính sách yêu cầu PKCE đối với client/luồng phù hợp, tránh request cố bỏ challenge để hạ cấp.

### 7.3. Atomicity của authorization code

Một code có thể bị gửi tới token endpoint gần như đồng thời bởi hai request:

~~~text
Request A đọc code: chưa dùng
Request B đọc code: chưa dùng
Request A xin access token
Request B cũng xin access token
~~~

Nếu AS chỉ kiểm tra trạng thái trước rồi cập nhật sau mà thiếu transaction/compare-and-swap, có thể phát hành hai bộ token từ cùng code. AS phải **tiêu thụ code một lần một cách nguyên tử** và đảm bảo trạng thái grant/token nhất quán.

Ví dụ SQL khái niệm:

~~~sql
UPDATE authorization_codes
SET consumed_at = CURRENT_TIMESTAMP
WHERE code_hash = :verified_code_hash
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
  AND client_id = :verified_client_id;
~~~

Chỉ transaction có đúng trạng thái và update thành công mới có thể tiếp tục phát hành token; phải phối hợp việc ghi trạng thái và phát hành token bằng một giao dịch/thiết kế nhất quán. Code không được đổi hơn một lần. RFC 6749 nêu cách xử lý trường hợp code bị dùng lại, gồm từ chối và cân nhắc thu hồi token dựa trên code đó khi khả thi.

Không nên tự triển khai giao thức OAuth từ đầu chỉ dựa trên vài lệnh SQL; nên sử dụng Authorization Server framework được duy trì.

## 8. Bước 5: Authorization Server trả token

Một token response OAuth có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<REFRESH_TOKEN_IF_ISSUED>"
}
~~~

Đây là ví dụ có refresh token; **không phải mọi grant hoặc AS đều bắt buộc cấp refresh token**. Với OIDC Authorization Code flow, token response còn có **ID token** theo đặc tả khi client thực hiện OIDC request hợp lệ.

### 8.1. Phân biệt các trường

| Trường | Ý nghĩa |
|---|---|
| `access_token` | Credential để gọi resource server đúng audience |
| `token_type` | Ví dụ Bearer; client phải sử dụng đúng kiểu token đã cấp |
| `expires_in` | Khoảng thời gian tương đối tính bằng giây, không phải epoch |
| `scope` | Scope thực sự được cấp nếu được trả; không mặc định mọi scope đã xin đều được chấp thuận |
| `refresh_token` | Tùy chọn theo grant/policy; dùng ở token endpoint để xin access token mới |
| `id_token` | Khi dùng OIDC Authorization Code flow, cho client xác minh kết quả đăng nhập |

Với JWT access token, claim `exp` là **NumericDate UTC theo giây từ epoch**, khác `expires_in` là **thời lượng tương đối**. Client có thể dự đoán thời điểm cần refresh, nhưng resource server tự kiểm tra thời gian khi nhận API request.

### 8.2. Không lộ token response

- Truyền token response qua HTTPS/TLS, không qua URL callback.
- Đặt header chống cache phù hợp như `Cache-Control: no-store` và `Pragma: no-cache`.
- Không log raw access token, refresh token, ID token, client secret, code hoặc code_verifier.
- Giới hạn quyền truy cập token ở backend, SPA, mobile hoặc BFF theo kiến trúc.
- Không tự redirect kèm token trong `Location`, fragment, query hoặc `Referer`.

Nếu client dùng BFF, có thể chỉ trả session cookie bảo vệ cho browser và giữ OAuth tokens ở backend. Với public browser client, cần xử lý token storage và nguy cơ XSS rất cẩn thận.

### 8.3. OIDC nonce và ID token

Nếu ứng dụng dùng **OpenID Connect**, thường request thêm `scope=openid` và có thể gửi một **nonce** tùy profile/cơ chế; AS phải đưa thông tin nonce vào ID token khi tương ứng theo đặc tả. Client xác minh ID token, trong đó có issuer, audience, chữ ký, thời gian và nonce nếu đã sử dụng.

**Nonce không phải PKCE và không phải state.** Chúng có thể cùng hiện diện nhưng giải quyết các vấn đề khác nhau: ID token replay/correlation, code interception và request-response binding.

Không dùng **ID token** làm bearer access token cho Orders API: audience của ID token thường là client, còn access token phải dành cho resource server.

## 9. Bước 6: dùng access token để gọi resource server

Khi token response đã được client nhận đúng quy trình, client gọi Orders API:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
Accept: application/json
~~~

**Authorization Code flow kết thúc ở việc client nhận token**, nhưng bảo mật hệ thống chưa kết thúc. Orders API phải tự xác minh credential và thực hiện authorization nghiệp vụ.

### 9.1. JWT và opaque access token

| Tiêu chí | JWT access token | Opaque access token |
|---|---|---|
| Cách kiểm tra | RS xác minh chữ ký và claims theo issuer/profile | RS thường dùng introspection hoặc token service đáng tin |
| Metadata | Có thể chứa iss, sub, aud, exp, iat, scope | Không nhất thiết giải mã được từ chuỗi token |
| Thu hồi trước expiry | Cần cơ chế trạng thái bổ sung nếu RS xác minh offline | Introspection có thể báo inactive, phụ thuộc cache |
| Điểm tin cậy | Khóa/hợp đồng của issuer | Endpoint và trạng thái token của AS |
| Ảnh hưởng đến Authorization Code flow | Không làm thay đổi các bước xin code/đổi code | Không làm thay đổi các bước xin code/đổi code |

Payload JWT access token minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893492900,
  "jti": "at-example-001"
}
~~~

Đây chỉ là payload, **không phải JWT hoàn chỉnh đã ký**. Với JWT, RS phải xác minh thuật toán/chữ ký/issuer/loại token, audience, thời gian và scope. Với opaque token, RS kiểm tra trạng thái active và các thuộc tính cần thiết theo hợp đồng introspection.

### 9.2. Scope không thay thế quyền trên từng object

~~~text
Access token:
    sub = alice-123
    aud = https://orders.example.com
    scope = orders:read

GET /api/orders/order-721  (đơn hàng Alice)
  -> Có thể ALLOW nếu các policy khác đều đạt.

GET /api/orders/order-999  (đơn hàng Bob)
  -> DENY nếu Alice không có quyền chia sẻ hoặc ủy quyền.
~~~

API cần kiểm tra **principal + action + resource + context**, gồm ownership và tenant. Chỉ có scope mà trả bất kỳ order ID là nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**.

### 9.3. Không dùng token sai audience

Access token có audience Orders API **không được dùng** để gọi Billing API chỉ vì hai API tin cùng issuer. Nếu cần nhiều resource, AS phải cấp token có audience phù hợp hoặc dùng token exchange/delegation theo kiến trúc. Downstream service phải tôn trọng quyền caller, tránh trở thành **confused deputy**.

## 10. Khi access token hết hạn: refresh và vòng đời grant

Client có thể được cấp refresh token tùy loại client, grant, chính sách và threat model. Khi access token gần hết hạn:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&client_id=shop-web
~~~

Với confidential client, token endpoint còn phải xác thực client theo phương thức đã đăng ký. Refresh token chỉ được gửi tới AS bằng kênh bảo vệ, **không** gửi cho Orders API hoặc đặt vào URL/log.

### 10.1. Refresh không tự mở rộng scope

Theo RFC 6749, phạm vi xin trong refresh request **không được vượt quá scope của grant ban đầu**:

~~~text
Grant ban đầu: orders:read
Refresh request: orders:read orders:delete
=> Không được cấp orders:delete chỉ vì refresh token còn hiệu lực.
~~~

Muốn thêm quyền nhạy cảm phải trải qua cơ chế authorization/approval mới phù hợp. **Refresh token rotation là bảo vệ credential; cấp scope mới là thay đổi quyền.**

### 10.2. Rotation và replay detection

Theo OAuth 2.0 Security BCP (RFC 9700), refresh token cấp cho **public client** cần cơ chế **rotation hoặc sender constraint** để giảm nguy cơ token bị đánh cắp sử dụng lại:

~~~text
R1 ACTIVE --refresh thành công--> R1 USED, R2 ACTIVE
R1 USED   --bị dùng lại-------> nghi replay, xử lý family
~~~

AS có thể thu hồi refresh token family để ngừng khả năng refresh tiếp khi token cũ bị dùng lại. Phải tính tới request đồng thời, retry sau timeout và atomic state transition.

**Thu hồi refresh token không tự làm mọi JWT access token đã cấp mất hiệu lực ngay** nếu RS kiểm tra offline mà không có denylist/session state. Kiến trúc cần xét TTL, introspection cache và cơ chế revoke.

### 10.3. Logout và xác thực lại

Đăng xuất thường cần xóa session/token phía client và có thể dùng token revocation của AS. Với OIDC, logout có profile riêng. Không coi việc xóa một cookie frontend đồng nghĩa mọi access token còn hạn bị vô hiệu hóa ở mọi resource server.

Tham số OIDC như prompt hoặc max_age phục vụ các yêu cầu xác thực/đăng nhập riêng; chúng không thay việc resource server kiểm tra thời gian và quyền khi nhận access token.

## 11. Chọn triển khai theo loại ứng dụng

| Loại ứng dụng | Kiến trúc phổ biến | Điểm chú ý |
|---|---|---|
| **Backend web app** | Authorization Code + PKCE với confidential client authentication | Token lưu phía server; bảo vệ cookie và session |
| **Backend-for-Frontend (BFF)** | BFF làm OAuth client; browser dùng session cookie | Giảm JavaScript tiếp xúc với OAuth tokens; vẫn chống CSRF và XSS |
| **Single Page Application (SPA)** | Public client + Authorization Code + PKCE | Không có client secret đáng tin trong JS; bảo vệ lưu trữ token |
| **Native/mobile** | Public client + Authorization Code + PKCE | External browser và redirect URI theo profile native |
| **Server-to-server không có user** | Client Credentials Grant, không phải Authorization Code | Quyền của workload/client thay vì user delegation |

### 11.1. SPA

Với SPA trực tiếp thực hiện Authorization Code flow:

- Dùng SDK OAuth/OIDC được duy trì để tạo PKCE verifier/challenge và state, quản lý callback.
- Client ID có thể công khai, không nhúng client secret rồi coi nó là bí mật.
- Xác minh state/issuer, dùng verifier đúng request để đổi code.
- Không đưa access token hoặc refresh token vào URL, fragment hay browser console/log.
- Phòng chống XSS, giảm script bên thứ ba, áp CSP và quản lý storage/refresh token theo policy.
- Chỉ gửi bearer access token cho resource server đúng audience qua HTTPS.

AS phải hỗ trợ token endpoint cho browser client theo giao thức và cấu hình CORS phù hợp nếu kiến trúc cần. **CORS không phải cơ chế xác thực** và không thay PKCE/client/grant validation.

### 11.2. BFF và backend web

BFF có thể giữ access/refresh token tại backend; browser chỉ sử dụng session cookie:

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant F as BFF
    participant AS as Authorization Server
    participant API as Orders API
    U->>B: Mở Shop Web
    B->>F: Bắt đầu đăng nhập
    F-->>B: Redirect tới AS với PKCE challenge
    B->>AS: Authorization request
    AS-->>B: Redirect về BFF callback với code
    B->>F: Callback code/state
    F->>AS: Token request với verifier và client authentication
    AS-->>F: Access token và token khác nếu được cấp
    F-->>B: Session cookie đã bảo vệ
    B->>F: Business request bằng cookie
    F->>API: Authorization: Bearer access_token
    API-->>F: Dữ liệu đã phân quyền
    F-->>B: Response không chứa OAuth token
~~~

Cookie phiên cần cấu hình **Secure, HttpOnly, SameSite**, domain/path và expiry phù hợp. BFF cần **CSRF protection**, session fixation protection và kiểm tra authorization. HttpOnly cản JavaScript đọc cookie nhưng không ngăn mọi XSS sử dụng session để thực hiện hành động.

### 11.3. Native/mobile

Ứng dụng native nên theo **RFC 8252**: sử dụng external user agent hoặc browser thích hợp thay vì webview nhúng tự yêu cầu người dùng nhập mật khẩu. Tùy platform, redirect có thể dùng app-claimed HTTPS URI, custom scheme hoặc loopback với kiểm soát tương ứng. PKCE giúp giảm nguy cơ một ứng dụng khác chặn code rồi đổi token.

Lưu refresh token trong kho credential được OS bảo vệ nếu có, không nhúng client secret dài hạn trong app phân phối. Cân nhắc sender-constrained token như DPoP nếu client/AS hỗ trợ; không giải quyết tuyệt đối rủi ro khi thiết bị bị xâm phạm.

### 11.4. Nhiều resource server và delegation

Nếu Shop Web cần gọi Orders API và Billing API, hãy thiết kế **audience/resource và scope rõ ràng cho từng API**. Có thể sử dụng Resource Indicators (RFC 8707) hoặc token exchange (RFC 8693) khi AS/kiến trúc hỗ trợ. Không sử dụng token Orders API ở Billing API chỉ vì cùng issuer.

Một backend có service token mạnh hơn quyền người dùng không được tự dùng quyền đó để đáp ứng yêu cầu trên tài nguyên ngoài quyền Alice. Đây là lỗi **confused deputy**; cần duy trì actor/delegation và policy ở mỗi downstream hop.

## 12. Spring Security OAuth2 Client trong Java

Backend Java có thể dùng **Spring Security OAuth2 Client và OIDC Login** thay vì tự viết một controller thu thập username/password, đổi code và quản lý session/PKCE.

### 12.1. Client registration

Ví dụ application.yml minh họa confidential web client (không chứa secret thật):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company
            client-id: shop-web
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders:read
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Đây là **cấu hình minh họa**. Cần dependency phù hợp, OIDC discovery ở issuer, client registration chính xác và secret manager. Không commit giá trị OAUTH_CLIENT_SECRET vào repository. Với OAuth AS không hỗ trợ OIDC discovery, có thể phải cấu hình authorization-uri, token-uri và metadata khác theo framework.

Scope orders:read trong client registration không tự buộc AS cấp quyền. issuer-uri cũng **không tự chỉ định audience của Orders API**; cần cấu hình resource indicator/token policy hoặc quy tắc phát hành đúng AS.

### 12.2. SecurityFilterChain cho backend web

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ShopWebSecurity {
    @Bean
    SecurityFilterChain shopFilter(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ **không phải cấu hình production hoàn chỉnh**: cần thêm session/CSRF, security headers, authorized client storage, consent/claim mapping, logout và các quy tắc phát hành token đúng môi trường.

**Hãy xác minh PKCE S256 đã bật cho client này theo Spring Security version/config đang dùng.** Không mặc định PKCE luôn bật với confidential client trong mọi phiên bản; nếu cần, cấu hình OAuth2AuthorizationRequestResolver hoặc Customizer thích hợp.

### 12.3. Backend gọi Orders API sau khi có access token

Sau khi OAuth2 Client có access token dành cho Orders API, backend có thể gửi header:

~~~java
RestClient ordersClient = RestClient.builder()
    .baseUrl("https://orders.example.com")
    .build();

OrderSummary summary = ordersClient.get()
    .uri("/api/orders/{id}/summary", orderId)
    .headers(headers -> headers.setBearerAuth(accessToken))
    .retrieve()
    .body(OrderSummary.class);
~~~

accessToken là biến minh họa đã lấy từ authorized client/token storage an toàn, không phải dữ liệu từ callback chưa kiểm tra. Cần quản lý refresh, TLS, redirect, timeout, error handling và log redaction. Spring Security có các thành phần như OAuth2AuthorizedClientManager để hỗ trợ lifecycle; không tự lưu secret vào session/frontend một cách tùy tiện.

### 12.4. Resource server là cấu hình khác

Orders API nên dùng **Spring Security OAuth2 Resource Server** để xác minh JWT/opaque access token **độc lập** với việc Shop Web đã sử dụng oauth2Login:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Cấu hình issuer chỉ là bước đầu. Orders API còn cần **expected audience validator**, token type/profile, scope authority mapping, authorization trên owner/tenant/resource, và revocation/cache policy khi áp dụng.

**Không lấy OIDC ID token của oauth2Login gửi sang Orders API** chỉ vì backend đã xác thực Alice.

## 13. Threat model: các cuộc tấn công vào Authorization Code flow

Authorization Code flow an toàn chỉ khi nhiều lớp bảo vệ hoạt động cùng nhau. Bảng dưới đây phân biệt nơi tấn công và biện pháp chính.

| Mối đe dọa | Cách nó xảy ra | Phòng vệ cốt lõi |
|---|---|---|
| **Authorization code interception** | Một ứng dụng hoặc thành phần khác đọc code trong redirect | PKCE S256, redirect đúng profile, code TTL ngắn |
| **Code replay** | Code đã đổi token được gửi lại | Code chỉ dùng một lần, tiêu thụ nguyên tử, phát hiện reuse |
| **Authorization code injection** | Code của một luồng khác bị đưa vào callback client | State/request binding, PKCE và issuer binding |
| **Login CSRF** | Nạn nhân bị buộc hoàn tất response do attacker khởi tạo | Request-response binding/CSRF protection, state khi sử dụng |
| **Redirect URI manipulation** | AS chuyển code tới URL attacker kiểm soát | URI đăng ký chặt, tránh wildcard/prefix và open redirect |
| **PKCE downgrade/stripping** | Client hoặc attacker bỏ challenge/verifier khiến code được đổi không cần proof | AS yêu cầu và kiểm tra PKCE theo client/profile, không fallback |
| **Authorization Server mix-up** | Client dùng token endpoint của AS B cho code của AS A | Issuer identification/binding, token endpoint từ metadata đáng tin |
| **Client impersonation** | Client secret lộ hoặc public app bị xem như confidential | Phân loại client đúng, client authentication phù hợp, PKCE |
| **Scope/audience escalation** | AS cấp scope hoặc resource chỉ vì client yêu cầu | Grant, client registration, consent và policy tại AS |
| **Token substitution** | Client dùng ID token thay access token, hoặc API nhận token sai audience | Token type/profile, iss, aud, scope, time validation |
| **Token leakage** | Token/code bị ghi vào URL, log, telemetry, cache | Back-channel token response, TLS, redaction và safe storage |
| **Refresh token replay** | Token làm mới bị sao chép rồi dùng lại | Rotation hoặc sender constraint, client binding, revocation |
| **Malicious client-side code** | XSS/script bên thứ ba đọc token hoặc thao tác phiên | CSP, chống XSS, BFF khi phù hợp, giới hạn quyền token |
| **Downstream confused deputy** | Service dùng token quyền rộng phục vụ caller không đủ quyền | Actor/delegation binding và authorization từng resource |

### 13.1. PKCE có chống mọi kiểu tấn công không?

**Không.** PKCE làm một authorization code bị chặn khó đổi thành token nếu attacker không có `code_verifier`; nhưng:

- PKCE không xác thực người dùng.
- PKCE không thay client authentication của confidential client.
- PKCE không sửa một redirect URI mở hoặc policy cấp quá scope.
- PKCE không bảo vệ access token đã lộ sau khi cấp.
- Nếu attacker kiểm soát môi trường client đủ sâu để lấy cả code và verifier, chỉ PKCE không ngăn được.
- PKCE không thay kiểm tra issuer, audience hay quyền trên Orders API.

PKCE chỉ là một lớp trong mô hình tin cậy từ **request → code → token → resource**.

### 13.2. Vì sao không dùng implicit flow cho ứng dụng mới?

Trong implicit flow lịch sử, access token có thể xuất hiện trực tiếp trong authorization response qua browser (thường trong fragment). Cách này làm access token đi qua front channel, có thêm nguy cơ lộ qua script, lịch sử, telemetry và các cơ chế của browser.

Theo OAuth 2.0 Security Best Current Practice, các ứng dụng hiện đại nên dùng **Authorization Code + PKCE** thay vì thiết kế mới dựa vào implicit flow. Việc sử dụng code không loại bỏ mọi rủi ro, nhưng cho phép AS kiểm tra client/PKCE và trả token qua token endpoint.

### 13.3. Authorization Code flow không phải ROPC

Trong Resource Owner Password Credentials Grant (ROPC) cũ, ứng dụng nhận trực tiếp username/password rồi đưa tới token endpoint. Đây là ranh giới bảo mật khác hẳn: client tiếp xúc mật khẩu và dễ gây nhầm lẫn/phishing. OAuth 2.0 Security BCP khuyến nghị không dùng ROPC.

Authorization Code flow chuyển trách nhiệm xác thực người dùng sang AS tin cậy. Client không nên tự dựng một form đăng nhập giả AS rồi yêu cầu Alice nhập mật khẩu để "tiện" đổi token.

## 14. Lỗi OAuth và cách chẩn đoán theo từng bước

### 14.1. Lỗi từ authorization endpoint

Nếu Alice từ chối quyền, AS có thể chuyển trình duyệt về client với:

~~~http
HTTP/1.1 302 Found
Location: https://shop.example.com/login/oauth2/code/shop?error=access_denied&state=<ORIGINAL_STATE>
~~~

Client phải kiểm tra ngữ cảnh callback trước khi hiển thị thông báo. Khi redirect URI không hợp lệ, AS không được chuyển secret hoặc lỗi nhạy cảm tới URI không tin cậy.

### 14.2. Lỗi từ token endpoint

| Lỗi OAuth | Nguyên nhân điển hình | Hướng kiểm tra |
|---|---|---|
| `invalid_request` | Thiếu tham số, request sai cú pháp hoặc bị trùng bất hợp lệ | Form encoding và các trường bắt buộc |
| `invalid_client` | Confidential client authentication thất bại | Secret, private_key_jwt, mTLS, method đăng ký |
| `invalid_grant` | Code sai/hết hạn/đã dùng, sai client/redirect hoặc PKCE sai | Code binding, TTL, verifier và atomic redemption |
| `unauthorized_client` | Client không được dùng grant type đó | Client registration, allowed grant types |
| `unsupported_grant_type` | AS không hỗ trợ grant type được yêu cầu | Chính sách/khả năng AS |
| `invalid_scope` | Scope không hợp lệ, không được biết hoặc vượt phạm vi | Registration, policy/consent, tên scope chính xác |

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

HTTP status/header thực tế phải tuân thủ quy tắc OAuth cho từng lỗi; `invalid_client` có thể đi kèm yêu cầu riêng về status và `WWW-Authenticate`. Không trả raw code, client secret, verifier, refresh token hoặc chi tiết người dùng nhạy cảm trong response. Lý do kỹ thuật chi tiết có thể được audit ở AS nhưng phải redaction.

### 14.3. Lỗi tại resource server

Một access token không hợp lệ hoặc hết hạn thường dẫn đến HTTP **401** và Bearer challenge khi thích hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

Token hợp lệ nhưng thiếu scope thường dẫn đến HTTP **403** và có thể có `insufficient_scope`:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:read"
~~~

Đối với resource ngoài quyền Alice, ứng dụng có thể trả 403 hoặc 404 theo policy che sự tồn tại. Không dựa vào mã HTTP của OAuth callback để suy rằng request tới Orders API sẽ được cấp quyền.

### 14.4. Debug theo đúng trust boundary

Nếu đăng nhập thành công nhưng gọi API bị 401, hãy phân biệt:

1. Client đã **nhận access token** hay chỉ có ID token?
2. Token có audience của Orders API hay dành cho API khác?
3. Chữ ký/issuer/JWKS và token type có đúng không?
4. `exp`, `nbf` và clock skew có hợp lý không?
5. Resource server đang mong JWT nhưng AS cấp opaque token hoặc ngược lại?
6. Header Authorization có đi đến API qua proxy không?

Nếu API trả 403, hãy kiểm tra **scope được cấp thực tế** và quyền theo owner/tenant/action. Đừng tự sửa scope trong JWT hoặc tắt audience validation để "giải quyết nhanh".

## 15. Ma trận kiểm thử Authorization Code + PKCE

### 15.1. Authorization request và callback

| Trường hợp | Kết quả mong muốn |
|---|---|
| Client hợp lệ, redirect URI đúng, PKCE S256, scope được phép | AS có thể bắt đầu xác thực và ủy quyền |
| Client ID không được đăng ký | Không cấp code |
| Client không được phép dùng authorization_code | Từ chối theo policy |
| Redirect URI không nằm trong registration | Từ chối; không redirect code/lỗi nhạy cảm tới URI đó |
| Redirect URI chỉ khớp tiền tố nhưng host khác | Từ chối |
| Client được yêu cầu PKCE nhưng không gửi code_challenge | Từ chối thay vì downgrade |
| S256 challenge sai cú pháp | Từ chối request |
| Scope vượt quyền client | AS từ chối hoặc không cấp phần vượt chính sách |
| Callback thiếu/sai state | Client từ chối, không đổi code |
| Callback đến từ issuer khác issuer ban đầu | Client từ chối theo cơ chế chống mix-up |
| Callback bị phát lại sau khi request đã hoàn tất | Client từ chối |
| Người dùng từ chối consent | Client nhận lỗi hợp lệ, không có access token |

### 15.2. Token endpoint và tính dùng một lần

| Trường hợp | Kết quả mong muốn |
|---|---|
| Code đúng client, redirect, PKCE, còn hạn, chưa dùng | Có thể phát token trong phạm vi grant |
| Code hết hạn | `invalid_grant` hoặc phản hồi theo profile |
| Code được đổi lần thứ hai | Từ chối; xử lý replay theo chính sách |
| Hai request đồng thời cùng đổi một code | Tối đa một lần phát hành thành công từ code |
| Code do client A nhận nhưng client B đổi | Từ chối |
| Client dùng verifier sai | Từ chối |
| Request đổi code thiếu verifier khi code gắn với challenge | Từ chối |
| Client thử đổi phương thức PKCE sang cách khác | Từ chối downgrade |
| Redirect URI lúc đổi khác authorization request | Từ chối theo quy tắc của giao thức |
| Confidential client thiếu client authentication | Từ chối |
| Public client chỉ gửi client_id | Không coi như confidential client đã xác thực |
| Client tự gửi subject=admin hoặc scope=orders:delete | Không tự cấp subject/scope ngoài grant |

### 15.3. Access token, resource server và OIDC

| Trường hợp | Kết quả mong muốn |
|---|---|
| Access token hợp lệ, đúng aud/scope và principal có quyền resource | Có thể ALLOW |
| Access token đúng chữ ký nhưng sai issuer | DENY |
| Access token đúng issuer nhưng sai audience | DENY |
| Access token hết hạn hoặc chưa đến nbf | DENY theo thời gian và leeway được cấu hình |
| Opaque token bị introspection báo inactive | DENY |
| ID token gửi thay access token đến Orders API | DENY do sai mục đích/profile |
| Access token có orders:read nhưng Alice xin order của Bob | DENY nếu không được ủy quyền |
| Client request scope rộng nhưng AS chỉ cấp scope hẹp | Client phải tuân thủ quyền được cấp, không giả định scope rộng |
| Token bị lộ trong URL/log | Phát hiện qua test redaction; áp phản ứng sự cố |
| Refresh token bị dùng lại sau rotation | AS phát hiện replay và xử lý family/grant |

### 15.4. Những điều cần quan sát trong hệ thống thật

- Tỷ lệ authorization request hoàn tất, lỗi do redirect/PKCE/state/issuer và tình trạng consent.
- Tỷ lệ token endpoint trả `invalid_grant` hoặc `invalid_client` phân loại an toàn.
- Số lượng access token được cấp theo **client, audience, grant type, scope và TTL** mà không log raw token.
- Tỷ lệ 401 tại resource server do issuer/audience/time, tỷ lệ 403 do scope/resource authorization.
- Sự kiện code reuse và refresh token reuse.
- Độ lệch đồng hồ giữa AS, client/backend và resource server.
- Đường đi redirect qua proxy, CDN và tình trạng redaction ở tracing/APM.

Log chỉ nên chứa metadata phục vụ phân tích theo chính sách bảo vệ dữ liệu. Không ghi nguyên authorization code, `code_verifier`, access token, refresh token, ID token, client assertion hoặc secret.

## 16. Tình huống suy luận

### Tình huống A — code bị chặn

Alice hoàn thành login và AS redirect code về một native app. Một app độc hại đọc được code nhưng không có code_verifier.

**Câu hỏi:** Kẻ tấn công có đổi code thành access token được không?

**Trả lời:** Nếu AS thực thi PKCE S256 và code/client/redirect binding đúng, chỉ có code là chưa đủ. Tuy nhiên, vẫn cần bảo vệ redirect, storage và ngăn cả verifier bị lộ.

### Tình huống B — dùng state cố định

Shop Web dùng `state=123` cho mọi lần đăng nhập vì AS đã hỗ trợ PKCE.

**Câu hỏi:** Có đáp ứng tốt request-response binding không?

**Trả lời:** Không nên. State cố định không liên kết an toàn với phiên/request cụ thể. Client cần thực thi cơ chế CSRF/request binding phù hợp, chẳng hạn state khó đoán gắn với phiên và các kiểm tra PKCE/issuer theo profile.

### Tình huống C — code không giới hạn số lần đổi

Token endpoint chỉ kiểm tra code còn hạn, không lưu trạng thái consumed. Hai request song song cùng nhận token.

**Câu hỏi:** Sai ở đâu?

**Trả lời:** Authorization code phải dùng một lần; cần transaction/compare-and-swap nguyên tử và xử lý replay. TTL ngắn không thay thế single-use.

### Tình huống D — redirect sang domain na ná

Client đăng ký `https://shop.example.com/callback`, nhưng AS cho phép bất kỳ URL nào có tiền tố `https://shop.example.com`.

**Câu hỏi:** Rủi ro gì?

**Trả lời:** So prefix thiếu kiểm soát có thể dẫn tới redirect URI manipulation, đặc biệt nếu có open redirect hoặc cách phân tích host sai. Phải đối chiếu URI theo registration và chuẩn tương ứng.

### Tình huống E — OAuth và đăng nhập

Client nhận access token có `scope=orders:read` và dùng claims trong token như bằng chứng đăng nhập của browser mà không thực hiện OIDC validation.

**Câu hỏi:** Có phù hợp không?

**Trả lời:** OAuth access token chủ yếu dành cho resource server, không phải giao thức đăng nhập của client. Nếu cần thông tin xác thực người dùng, dùng OIDC ID token với issuer/audience/nonce/time validation theo profile.

### Tình huống F — client xin thêm quyền sau refresh

Alice đã cấp orders:read, sau đó ứng dụng dùng refresh token xin thêm orders:delete.

**Câu hỏi:** AS có được cấp không?

**Trả lời:** Không được mở rộng grant chỉ vì refresh token hợp lệ. Muốn quyền mới phải theo quy trình authorization/consent hoặc phê duyệt tương ứng.

### Tình huống G — đã đăng nhập nhưng API trả 401

Shop Web nhận ID token có audience `shop-web`, rồi dùng nó gọi Orders API.

**Câu hỏi:** 401 là lỗi gì?

**Trả lời:** API không nhận access token đúng mục đích/audience. Client cần lấy access token dành cho Orders API, không sử dụng ID token làm bearer API credential.

### Tình huống H — token đúng nhưng resource ngoài quyền

Alice có access token đúng audience, đúng scope orders:read, còn hạn. Cô yêu cầu dữ liệu đơn hàng của Bob không được chia sẻ.

**Câu hỏi:** API có được trả dữ liệu không?

**Trả lời:** Không. Cần authorization theo principal, action, resource và tenant; scope chỉ là một điều kiện.

### Tình huống I — client dùng hai AS

Shop Web hỗ trợ cả issuer A và B. Callback có code của A nhưng client chọn token endpoint B từ một tham số không đáng tin trong URL.

**Câu hỏi:** Cần bảo vệ gì?

**Trả lời:** Đây là nguy cơ authorization server mix-up. Client phải ràng buộc issuer/token endpoint với pending authorization request, dùng metadata tin cậy và xác minh issuer authorization response khi áp dụng.

### Tình huống J — code đã đổi nhưng log ghi token response

Hệ thống dùng PKCE đúng, token endpoint thành công, nhưng HTTP debug log ghi raw refresh token và access token.

**Câu hỏi:** PKCE đã đủ bảo vệ chưa?

**Trả lời:** Không. PKCE giảm rủi ro đổi code bị chặn, nhưng không bảo vệ các token đã phát hành bị log. Cần redaction, lưu trữ an toàn, TTL/rotation/revocation và ứng cứu lộ credential.

## 17. Checklist thiết kế Authorization Code flow an toàn

Trước khi đưa OAuth client và Authorization Server vào production:

1. **Client registration:** đúng client type, allowed grant types, redirect URIs và authentication method.
2. **PKCE:** tạo verifier ngẫu nhiên cho từng request, dùng S256, AS kiểm tra không bị bỏ qua/downgrade.
3. **Request binding:** kiểm tra state/CSRF, issuer và pending authorization request; dùng nonce khi OIDC/profile cần.
4. **Authorization endpoint:** xác thực người dùng theo AS, cấp scope/resource đúng chính sách và consent.
5. **Redirect:** URI được đăng ký và kiểm tra chặt, không có open redirect làm lộ code.
6. **Authorization code:** TTL ngắn, khó đoán, gắn client/redirect/PKCE/grant, dùng một lần nguyên tử.
7. **Token endpoint:** POST qua HTTPS, xác thực confidential client, từ chối code sai/hết hạn/replay.
8. **Token issuance:** phát access token đúng subject/client/scope/audience, TTL và token type/profile.
9. **OIDC:** xác minh ID token đúng issuer, audience, chữ ký, thời gian, nonce nếu áp dụng; không dùng ID token gọi API.
10. **Resource server:** xác minh JWT/opaque token, issuer, aud, exp/nbf, scope và quyền trên resource cụ thể.
11. **Refresh:** grant không bị mở rộng, rotation hoặc sender constraint khi cần, có kế hoạch thu hồi.
12. **Transport/storage:** không đặt token/code/verifier trong log hoặc URL không phù hợp; TLS và secret storage.
13. **Browser:** CORS đúng, không coi CORS là authentication; CSP, chống XSS, session/CSRF cho BFF.
14. **Vận hành:** key/secret rotation, code/reuse alerts, redaction, incident response và ma trận kiểm thử âm tính.

**Kết luận:** Authorization Code flow giúp client nhận token từ Authorization Server bằng một **authorization code ngắn hạn và dùng một lần** thay vì đưa access token trực tiếp qua redirect. **PKCE S256, state/request binding, issuer/redirect validation và client authentication khi áp dụng** bảo vệ quá trình đổi code. Sau khi token được cấp, hệ thống vẫn phải bảo vệ **access token, refresh token, audience, scope, thời gian, thu hồi và quyền trên resource/action**. Luồng cấp token an toàn là một chuỗi quyết định tin cậy, không phải chỉ một redirect thành công.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code Grant, authorization endpoint, token endpoint, scope và refresh token.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE, code_verifier, code_challenge và S256.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, redirect security, refresh replay và bảo vệ luồng OAuth hiện đại.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): ràng buộc issuer trong authorization response, chống mix-up.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external browser, redirect URI và native client.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata và khám phá endpoint AS đáng tin.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): đẩy authorization request qua back channel khi profile hỗ trợ.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token cho resource cụ thể.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token downstream và delegation.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer, 401/403 và transport access token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims và token validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi access token/refresh token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449): DPoP sender-constrained token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code flow, ID token, nonce và xác minh đăng nhập.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): triển khai OAuth2/OIDC client login.
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): đăng ký client, authorized clients và token lifecycle.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): hướng dẫn bảo vệ OAuth flow.
