# Code exchange at token endpoint

## 1. Đổi authorization code thành token thực chất là kiểm tra điều gì?

Trong chương **Authorization Code** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này tập trung vào bước nhạy cảm nhất sau khi Authorization Server (AS) trả authorization code: **client gửi code tới token endpoint để xin access token**. Đây là bước chuyển một bằng chứng ủy quyền **tạm thời, ngắn hạn và chỉ dùng một lần** thành credential có thể gọi API.

Giả sử Alice đã đăng nhập và chấp thuận cho ứng dụng **Shop Web** đọc đơn hàng. Authorization Server chuyển trình duyệt về:

~~~http
HTTP/1.1 302 Found
Location: https://shop.example.com/login/oauth2/code/shop?code=<AUTHORIZATION_CODE>&state=<STATE>
~~~

Tại thời điểm này Shop Web **chưa nên coi code là access token**, không đưa code đến Orders API và không tin các tham số do browser tự khai là danh tính đã được xác minh. Client cần:

1. Xác minh authorization response thuộc đúng request/phiên đang chờ bằng `state` hoặc cơ chế liên kết theo profile.
2. Xác định **đúng issuer và token endpoint** của request đã khởi tạo.
3. Lấy đúng `code_verifier` đã tạo trước khi điều hướng sang AS.
4. Gửi HTTP POST tới token endpoint qua TLS, kèm code, redirect URI và client authentication nếu thuộc confidential client.
5. Nhận token **chỉ sau khi AS xác minh code, client, PKCE, grant và chính sách cấp quyền**.

**Mô hình tin cậy:** code nằm trong **front channel** qua browser, trong khi token request/response sử dụng kết nối trực tiếp với AS. PKCE và các ràng buộc khác giúp ngăn người chỉ chiếm code từ redirect đem code đến AS để nhận token.

### 1.1. Bài học này khác phần giới thiệu Authorization Code flow

Authorization Code flow mô tả hành trình từ yêu cầu ủy quyền tới API. Riêng **code exchange at token endpoint** đi sâu vào:

- Hợp đồng HTTP của token request và token response (RFC 6749).
- Sự khác biệt giữa `code_challenge` và `code_verifier` (RFC 7636).
- Client authentication, code-to-client binding và redirect URI binding.
- Xác minh code **còn hạn, đúng grant và chưa được dùng** một cách nguyên tử.
- Không nâng scope, audience, subject hoặc quyền khi đổi code.
- Lỗi `invalid_grant`, `invalid_client`, replay, retry, race condition và audit.
- Nhận đúng access token, ID token khi có OIDC và refresh token nếu được cấp.

## 2. Ba vai trò và hai kênh giao tiếp

| Thành phần | Việc phải làm |
|---|---|
| **OAuth client** | Nhận callback, xác minh ngữ cảnh và gửi token request với bằng chứng đúng |
| **Authorization Server** | Sở hữu token endpoint; xác thực client, kiểm tra code/PKCE và phát token theo grant |
| **Resource Server** | Nhận access token sau khi phát hành, kiểm tra issuer/audience/scope và quyền theo resource |
| **Browser (user agent)** | Chuyển user tới authorization endpoint rồi mang code về redirect URI |

Hãy phân biệt:

~~~text
FRONT CHANNEL (Browser)
  AS --redirect--> Client callback: code + state (+ iss nếu profile hỗ trợ)

TOKEN REQUEST / BACK CHANNEL
  Client --HTTPS POST /token--> AS: code + code_verifier + client proof
  AS --HTTPS JSON response--> Client: access_token, ...

RESOURCE REQUEST
  Client --Authorization: Bearer access_token--> Orders API
~~~

Không tự chuyển access token, ID token hoặc refresh token vào callback URL chỉ vì authorization code đi qua redirect. **Authorization code cũng là credential nhạy cảm** và cần TTL ngắn, chống log, replay và open redirect.

### 2.1. Public và confidential client

| Loại client | Ví dụ | Bằng chứng ở token endpoint |
|---|---|---|
| **Public client** | SPA, native/mobile | `client_id` để định danh, PKCE verifier; không có shared secret đáng tin |
| **Confidential client** | Backend web, BFF | PKCE verifier **và** xác thực client theo phương thức đã đăng ký |

Client secret được nhúng trong JavaScript hoặc ứng dụng mobile có thể bị người dùng trích xuất; nó **không biến public client thành confidential client**. `client_id` là định danh, không phải bí mật chứng minh người gửi.

### 2.2. Bảo vệ endpoint phát hành không có nghĩa tin browser

Client không được lấy `iss`, `token_endpoint` hoặc `client_id` tùy ý từ URL callback rồi đổi code ở địa chỉ do browser chỉ định. Token endpoint phải xuất phát từ **client registration/metadata của issuer tin cậy** và liên kết với authorization request ban đầu.

Nếu một ứng dụng hỗ trợ nhiều AS, phải chống **authorization server mix-up**. RFC 9207 định nghĩa tham số `iss` trong authorization response khi được hỗ trợ; client cần đối chiếu nó với issuer đã mong đợi. Có thể dùng cơ chế chống mix-up tương đương theo profile, nhưng không bỏ qua ranh giới issuer.

## 3. Sơ đồ code exchange từ callback đến phát token

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API
    Note over C,AS: Trước đó C tạo code_verifier và gửi code_challenge S256
    AS-->>B: Redirect callback với authorization code + state
    B->>C: GET redirect_uri?code=...&state=...
    C->>C: Kiểm tra state, issuer, phiên và pending request
    C->>AS: POST /token: grant_type, code, redirect_uri, code_verifier + client auth nếu cần
    AS->>AS: Xác thực client và allowed grant
    AS->>AS: Code còn hạn, đúng client/redirect URI, chưa dùng
    AS->>AS: Kiểm tra PKCE S256 và granted scopes/resources
    AS->>AS: Tiêu thụ code một lần, commit trạng thái
    AS-->>C: JSON: access token, refresh/ID token nếu được cấp
    C->>RS: Authorization: Bearer access_token
    RS->>RS: Xác minh token, audience, scope, principal/action/resource
    RS-->>C: ALLOW hoặc DENY
~~~

Trong sơ đồ, **AS chỉ được phát token sau khi toàn bộ điều kiện cấp quyền đạt**. Một token có chữ ký hợp lệ nhưng đã được cấp cho sai client, sai subject hoặc audience vẫn là lỗi nghiêm trọng ở bước phát hành.

## 4. Trước khi exchange: code được ràng buộc với điều gì?

Khi xử lý authorization request, AS cấp code cho một client và một kết quả ủy quyền cụ thể. Code không phải một mã tự do có thể được bất kỳ ứng dụng nào đổi lấy token của Alice.

Ví dụ metadata **minh họa phía AS**:

~~~json
{
  "code_record_id": "ac-4f99",
  "client_id": "shop-web",
  "redirect_uri": "https://shop.example.com/login/oauth2/code/shop",
  "code_challenge": "<S256_CHALLENGE>",
  "code_challenge_method": "S256",
  "subject": "alice-123",
  "granted_scopes": ["orders:read"],
  "allowed_resources": ["https://orders.example.com"],
  "issued_at": "2030-01-01T10:00:00Z",
  "expires_at": "2030-01-01T10:05:00Z",
  "status": "ACTIVE"
}
~~~

Đây **không phải schema chuẩn OAuth**, cũng không phải payload authorization code công bố cho client. AS có thể lưu server-side hoặc dùng cơ chế khác có tính toàn vẹn, miễn các bất biến sau được giữ:

1. **Code không thể đoán:** đủ entropy, không sinh từ user ID hoặc timestamp đơn giản.
2. **Code có hạn ngắn:** chỉ tồn tại đủ lâu cho một lần chuyển hướng và đổi mã.
3. **Code thuộc một client:** không chuyển sang client khác chỉ vì client khác biết giá trị code.
4. **Code gắn redirect URI gốc:** token request phải tuân thủ quy tắc đối chiếu.
5. **Code gắn PKCE challenge:** verifier chỉ được kiểm tra dựa trên challenge của đúng authorization request.
6. **Code gắn grant/subject/scope/resource:** token endpoint không được lấy quyền mới từ dữ liệu client tự khai.
7. **Code chỉ dùng một lần:** cần kiểm tra trạng thái và tiêu thụ nguyên tử, kể cả khi có request đồng thời.

Không cần lưu raw code ở cơ sở dữ liệu nếu có thể lưu verifier/hash hoặc lookup an toàn từ code ngẫu nhiên có entropy đủ cao. Cần bảo vệ dữ liệu này khỏi log/backup không kiểm soát.

### 4.1. `code_verifier` và `code_challenge` không phải một giá trị

Với PKCE S256:

~~~text
code_verifier  = chuỗi bí mật ngẫu nhiên do client tạo cho một request
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
~~~

**Authorization request** gửi `code_challenge`, còn **token request** gửi `code_verifier`. AS xác minh verifier theo challenge đã ràng buộc với code khi phát hành.

Không gửi verifier trong URL authorization request, không dùng cùng một verifier cố định cho nhiều user/phiên và không tự hạ cấp sang phương thức `plain` vì code không đổi được. RFC 7636 quy định verifier có **43–128 ký tự** trong tập ký tự cho phép; với triển khai hiện đại nên ưu tiên **S256**.

### 4.2. Client phải lưu ngữ cảnh pending request

Ví dụ trạng thái client cần quản lý trong session/kho thích hợp:

~~~text
pending_authorization:
    state
    issuer
    client_registration_id
    redirect_uri
    code_verifier
    requested_scopes/resources
    created_at, expires_at
    consumed = false
~~~

`state` cần được tạo khó đoán, liên kết với request/phiên và được đối chiếu ở callback khi sử dụng. OIDC `nonce` là cơ chế khác, giúp liên kết ID token với yêu cầu xác thực khi được sử dụng theo profile; **nonce không thay PKCE hoặc state**.

Khi callback sai state/issuer, client nên **dừng trước token request** để tránh đưa code tới nhầm AS hoặc gắn session với một response không thuộc luồng hiện tại.

## 5. HTTP request đúng tại token endpoint

Theo RFC 6749 mục 4.1.3, client gửi **HTTP POST** tới token endpoint qua TLS với tham số dạng **`application/x-www-form-urlencoded`**. Authorization code, client credentials và PKCE verifier là dữ liệu nhạy cảm, không nên đưa vào query string.

### 5.1. Public client dùng Authorization Code + PKCE

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&client_id=shop-spa&code_verifier=<CODE_VERIFIER>
~~~

Các placeholder chỉ phục vụ học tập. Token request trong ví dụ có:

| Tham số | Mục đích |
|---|---|
| `grant_type=authorization_code` | Chọn grant đổi authorization code |
| `code` | Authorization code vừa được AS cấp, chỉ dùng một lần |
| `redirect_uri` | Đối chiếu URI của authorization request gốc theo quy tắc OAuth |
| `client_id` | Định danh client không xác thực bằng phương thức có secret |
| `code_verifier` | Bằng chứng PKCE đối chiếu với challenge ràng buộc với code |

**Không đặt `code_challenge` trong token request thay `code_verifier`.** Client đã gửi challenge trước đó; token endpoint cần verifier để tính lại challenge và so sánh.

### 5.2. Confidential client: PKCE cộng client authentication

Với confidential web backend được đăng ký dùng `client_secret_basic`:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <BASE64_OF_ENCODED_CLIENT_ID_AND_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&code_verifier=<CODE_VERIFIER>
~~~

Trong Basic OAuth, client ID và client secret phải được mã hóa theo quy tắc `application/x-www-form-urlencoded` trước khi ghép thành username/password cho Basic (RFC 6749 §2.3.1). **Base64 không phải mã hóa bảo mật**. Secret phải được giữ ở backend/secret manager, truyền qua TLS và không xuất hiện trong browser bundle.

Không tự gửi đồng thời `client_secret_basic`, `client_secret_post` và một client assertion rồi để AS tùy chọn phương thức bất kỳ. Client authentication phải **đúng method đã đăng ký** và được AS cho phép; nhiều cơ chế xác thực mâu thuẫn cần bị từ chối theo hợp đồng.

### 5.3. Redirect URI tại token request: điểm dễ sai

Nếu `redirect_uri` đã được client đưa vào authorization request, RFC 6749 yêu cầu token request cũng phải có nó và **giá trị phải giống hệt** giá trị ở bước authorization. Đối chiếu theo quy tắc của chuẩn/profile và registration, không tự coi một đường dẫn na ná là tương đương.

Ví dụ:

~~~text
Authorization request:
  redirect_uri = https://shop.example.com/callback

Token request:
  redirect_uri = https://shop.example.com/callback
  => Có thể vượt kiểm tra URI.

Token request:
  redirect_uri = https://shop.example.com/callback/other
  => DENY.

Token request:
  redirect_uri = https://shop.example.com.attacker.test/callback
  => DENY.
~~~

Đừng kiểm tra bằng `startsWith`, chỉ so hostname, bỏ qua path hoặc nhận wildcard chung. Một số profile native app như loopback redirect có ngoại lệ theo chuẩn (ví dụ cổng động lúc đăng ký), **không phải ngoại lệ để bỏ so khớp URI gắn với code**.

Nếu không có `redirect_uri` trong authorization request, quy tắc có thể khác theo RFC 6749 và cấu hình AS; không nên tự suy rằng token endpoint có quyền thay thế một redirect URI tùy ý. **Đơn giản nhất trong triển khai nhất quán là luôn gửi và ràng buộc redirect URI cụ thể ở cả hai bước khi profile cho phép/yêu cầu.**

### 5.4. Không thêm scope, subject hoặc audience tùy ý lúc đổi code

Token request dùng authorization_code grant không phải một authorization request mới. Client không được lén gửi:

~~~text
scope=orders:admin
sub=another-user
aud=https://payments.example.com
~~~

rồi mong AS cấp quyền mới. AS phải derive subject, granted scopes và allowed resources **từ grant đã được phê duyệt**; mọi extension như resource indicator hoặc audience selection (nếu hỗ trợ tại token endpoint) phải được ràng buộc bởi grant/chính sách, tuyệt đối không làm tăng quyền.

## 6. PKCE verification ở token endpoint

PKCE (RFC 7636) giúp người chỉ lấy được code từ front channel **không thể đổi code thành token** nếu không có verifier hợp lệ.

### 6.1. Chuỗi xử lý S256

Client tạo verifier bằng nguồn ngẫu nhiên mật mã, dùng challenge:

~~~text
challenge = BASE64URL_NO_PADDING(SHA256(ASCII(verifier)))
~~~

Authorization Server ghi challenge gắn với code. Khi token request đến:

1. AS tìm code và metadata đã xác minh.
2. AS lấy **phương thức PKCE từ bản ghi của authorization request**, không tin một method mới do token request khai.
3. AS kiểm tra cú pháp và độ dài verifier theo profile.
4. AS tính challenge từ verifier.
5. AS so sánh challenge tính được với **challenge đã lưu**, dùng API so sánh phù hợp với dữ liệu mật.
6. Nếu sai hoặc thiếu verifier, **không phát token**.

~~~mermaid
flowchart TD
    A[Token request: code + verifier] --> B[Tra record code]
    B --> C{Code còn hiệu lực và thuộc client?}
    C -- Không --> X[Từ chối invalid_grant]
    C -- Có --> D[Lấy code_challenge và method đã lưu]
    D --> E[Tính S256 challenge từ verifier]
    E --> F{Challenge khớp?}
    F -- Không --> X
    F -- Có --> G[Kiểm tra grant, resource và single-use]
    G --> H[Phát token đúng quyền]
~~~

### 6.2. Ví dụ Java để minh họa phép kiểm tra

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.regex.Pattern;

public final class PkceVerifier {
    private static final Pattern ALLOWED =
        Pattern.compile("^[A-Za-z0-9._~-]{43,128}$");

    public static boolean matchesS256(
            String codeVerifier,
            String storedCodeChallenge) throws Exception {

        if (codeVerifier == null
                || !ALLOWED.matcher(codeVerifier).matches()) {
            return false;
        }

        byte[] digest = MessageDigest.getInstance("SHA-256").digest(
            codeVerifier.getBytes(StandardCharsets.US_ASCII));

        String calculated = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);

        if (storedCodeChallenge == null) {
            return false;
        }
        return MessageDigest.isEqual(
            calculated.getBytes(StandardCharsets.US_ASCII),
            storedCodeChallenge.getBytes(StandardCharsets.US_ASCII));
    }
}
~~~

Đây là **đoạn minh họa riêng phép PKCE**, không phải token endpoint production: còn thiếu client auth, code lookup, issuer, redirect URI, single-use transaction, error semantics và chính sách S256. **Không tự dùng đoạn này thay Authorization Server framework**. AS phải lưu method/challenge từ authorization request và tránh PKCE downgrade.

### 6.3. Vì sao không được fallback khi verifier sai?

Ví dụ thiết kế nguy hiểm:

~~~java
// SAI: code đã được cấp kèm PKCE challenge.
if (codeVerifier == null || !pkceMatches) {
    return issueTokenFromCodeWithoutPkce(code);
}
~~~

Nhánh fallback làm mọi bảo vệ PKCE trở nên vô nghĩa. Nếu code yêu cầu PKCE, **thiếu hoặc sai verifier phải từ chối**. Nếu client đăng ký luồng yêu cầu PKCE, AS cũng cần từ chối authorization request thiếu challenge thay vì cấp code không có ràng buộc.

PKCE **không thay**:

- Client authentication của confidential client.
- Kiểm tra redirect URI, issuer, state/request binding.
- Quy tắc cấp scope/audience và quyền theo resource.
- Bảo vệ access token/refresh token sau khi được phát hành.
- Phòng chống XSS/malware có thể lấy cả code và verifier.

## 7. Xác thực client ở token endpoint

Token endpoint cần phân biệt việc **nhận diện public client** và **xác thực confidential client**. PKCE chứng minh bên xin token nắm verifier của authorization request; client authentication chứng minh confidential client sở hữu credential đã đăng ký.

### 7.1. Các phương thức thường gặp

| Phương thức | Dữ liệu trình bày | Kiểm tra quan trọng |
|---|---|---|
| **client_secret_basic** | Client ID/secret qua HTTP Basic | Secret đúng và phương thức được phép |
| **client_secret_post** (nếu hỗ trợ) | Client ID/secret trong form body | TLS, bảo vệ log và policy chấp nhận |
| **private_key_jwt** | JWT client assertion được ký | Chữ ký, iss/sub, aud, exp/iat/jti theo profile, chống replay |
| **mTLS client authentication** | Client certificate trong handshake TLS | Chuỗi chứng chỉ/khóa, đăng ký client và chính sách hạ tầng |
| **Public client không có secret** | `client_id` cùng PKCE verifier | Code được cấp đúng client, PKCE và grant; không coi client_id là secret |

Một client đăng ký `private_key_jwt` không nên được AS tự chuyển sang `client_secret_post` khi assertion thất bại. Thay đổi method là vấn đề cấu hình/chính sách, **không phải fallback tự động để tiện tương thích**.

### 7.2. Client assertion và replay

Với `private_key_jwt`, assertion được ký bằng private key của client. AS cần kiểm tra chữ ký, định danh client, audience hướng tới token endpoint, thời hạn và `jti`/replay theo profile. Một assertion còn hạn nhưng đã dùng có thể là tín hiệu phát lại nếu hệ thống áp quy tắc single-use; phải thiết kế anti-replay tương ứng.

Không đặt private key của client trong frontend, repo, debug log hoặc chia sẻ giữa nhiều tenant nếu chính sách không cho phép. Quản lý key rotation, secret storage và client registration như một phần của trust boundary.

### 7.3. `client_id` trong public client dùng để làm gì?

Client ID giúp AS xác định **client mà code được cấp cho**, từ đó so khớp registration và grant. Bất kỳ ai có thể biết ID của public app; chỉ cung cấp ID không làm một token request trở thành xác thực mạnh.

AS vẫn phải kiểm tra code **thuộc đúng client ID**, dù public client không có secret. Không thể dùng code được cấp cho App A tại App B chỉ bằng cách gửi `client_id` của B.

## 8. Single-use code: chống race và replay ở nhiều instance

Khi PKCE/client/redirect đã qua, code vẫn chỉ được đổi **một lần**. Nếu hai HTTP requests đồng thời gửi cùng code, AS không được cấp hai bộ token độc lập.

### 8.1. Race condition điển hình

~~~text
Node A: SELECT code => ACTIVE
Node B: SELECT code => ACTIVE
Node A: phát token A1, đánh dấu USED
Node B: phát token A2, đánh dấu USED
=> Hai lần phát từ một code: VI PHẠM SINGLE-USE.
~~~

Chỉ kiểm tra `status=ACTIVE` tại đầu request rồi đổi trạng thái sau khi ký token là chưa đủ. Cần **transaction/row lock, compare-and-swap hoặc cơ chế lưu trữ nhất quán tương đương**.

### 8.2. Conditional update và transaction

Ví dụ SQL khái niệm:

~~~sql
UPDATE authorization_codes
SET consumed_at = CURRENT_TIMESTAMP,
    status = 'USED'
WHERE code_hash = :verified_code_hash
  AND client_id = :verified_client_id
  AND status = 'ACTIVE'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Việc update chỉ thành công khi code vẫn ACTIVE, còn hạn và thuộc đúng client. **Một transaction** phải kiểm tra số hàng cập nhật; request còn lại phải từ chối. Nhưng một lệnh UPDATE riêng lẻ vẫn chưa đủ cho **tính nhất quán của grant và credential đã phát hành**: AS phải điều phối việc đánh dấu code, ghi authorization/token state và kết quả trả về theo một quy trình fail-closed.

Nếu dùng nhiều AS nodes và database replica có độ trễ, không thể dựa vào cache riêng từng node để đảm bảo single-use toàn cụm. Cần cơ chế trạng thái dùng chung có consistency phù hợp; tối thiểu đảm bảo tối đa một lần tiêu thụ thành công.

### 8.3. Retry sau timeout

Tình huống:

~~~text
T0: Client gửi code + verifier.
T1: AS xác minh và commit code=USED, phát token.
T2: Network timeout, client không nhận token response.
T3: Client retry code cũ.
T4: AS từ chối vì code đã USED.
~~~

Đây là **hành vi fail-closed** quan trọng. Client không nên retry vô hạn cùng authorization code hoặc tạo logic "nếu timeout thì code vẫn hợp lệ". Thường cần **bắt đầu authorization flow mới** hoặc dùng cơ chế khôi phục riêng đã thiết kế an toàn, thay vì mở đường đổi lại cùng code.

Khi AS phát hiện code replay, không phải lúc nào cũng biết request nào là của người hợp lệ. RFC 6749 yêu cầu từ chối reuse, đồng thời nêu việc thu hồi các token đã cấp dựa trên code đó **khi có thể**. Cần thiết kế liên kết code→grant/token để xử lý sự cố theo rủi ro.

## 9. Token issuance: cấp đúng subject, scope và audience

Code exchange không chỉ là bài toán kiểm tra mật mã. Trước khi phát token, AS phải xác định **quyền nào đã được cấp trong authorization grant** và liệu quyền đó có còn được phát hành theo chính sách hiện tại hay không.

Ví dụ authorization request ban đầu yêu cầu:

~~~text
client_id = shop-web
scope = orders:read orders:delete
resource = https://orders.example.com
~~~

Nếu chính sách/consent chỉ cho phép `orders:read`, AS có thể đã từ chối yêu cầu hoặc chấp thuận một tập quyền hẹp hơn theo giao thức/contract. **Token endpoint tuyệt đối không được tự cấp lại `orders:delete` chỉ vì client có code hợp lệ.**

### 9.1. Bốn yếu tố cần ràng buộc

| Yếu tố | Nguồn dữ liệu đáng tin | Quy tắc phát hành |
|---|---|---|
| **Subject** (`sub`) | User/session/ủy quyền đã được AS xác thực trong authorization grant | Không cho client tự khai subject khác |
| **Client** (`client_id`) | Client registration và code-to-client binding | Token phải ràng buộc với client được cấp code |
| **Scope** | Quyền được AS cấp sau consent/policy | Không vượt granted scopes; áp least privilege |
| **Resource/audience** (`aud`) | AS policy, client eligibility, granted resources | Không tự biến code của Orders API thành token cho Payments API |

Ngoài ra AS cần xác định **issuer, token type/profile, thời gian sống, grant/session state, tenant và các điều kiện token binding**. JWT được ký đúng nhưng có claim sai là credential sai quyền được AS hậu thuẫn.

### 9.2. Audience và resource indicator

Với kiến trúc đa API, client có thể xin token dành cho resource cụ thể qua **RFC 8707 Resource Indicators** khi AS hỗ trợ. Việc client được phép gọi token endpoint **không đồng nghĩa** được cấp token cho mọi resource nó yêu cầu.

~~~text
Authorization grant cho:
  resource = https://orders.example.com
  scope = orders:read

Token endpoint nhận code gắn grant đó.

Access token được cấp:
  aud = https://orders.example.com
  scope = orders:read

=> Không được âm thầm đổi thành aud=https://payments.example.com.
~~~

Một token có nhiều audience có thể phù hợp một số thiết kế, nhưng cần được chủ động đánh giá nguy cơ dùng lại giữa các API; **không mặc định tạo multi-audience token chỉ để tiện tái sử dụng**.

### 9.3. Context và tenant

Nếu AS phục vụ nhiều tenant, grant phải xác định principal thuộc tenant hoặc phạm vi delegated authorization nào. Client không được gửi `tenant_id=another-tenant` ở token endpoint rồi nhận quyền của tenant khác.

Resource server còn phải kiểm tra **principal + action + resource + context**. Token có scope `orders:read` không tự cho phép Alice đọc đơn hàng của Bob chỉ vì hai người thuộc cùng một API.

## 10. Token response: access token, ID token và refresh token

Khi thành công, token endpoint trả **JSON response** qua HTTPS. Ví dụ OAuth bearer response:

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

**Không phải mọi Authorization Code flow đều được cấp refresh token.** AS quyết định theo loại client, chính sách, grant và các điều kiện bảo mật. Với OIDC Authorization Code flow hợp lệ, token response còn có **ID token** theo đặc tả OIDC.

### 10.1. Phân biệt các trường trong response

| Trường | Ý nghĩa |
|---|---|
| `access_token` | Credential dùng để gọi resource server đúng audience |
| `token_type` | Cách sử dụng access token, ví dụ Bearer; với DPoP-bound token có thể là DPoP theo profile |
| `expires_in` | Khoảng thời gian sống tương đối **tính bằng giây** |
| `scope` | Scope được cấp thực tế khi response có trường này |
| `refresh_token` | Credential tùy chọn dùng tại AS/token endpoint để xin access token mới |
| `id_token` | Với OIDC, dành cho client xác minh thông tin đăng nhập, không thay access token API |

Nếu client yêu cầu `orders:read orders:delete` nhưng AS chỉ cấp `orders:read`, client phải **đánh giá response/authorized client state theo quyền thực tế**. Client không được tự đánh dấu rằng người dùng có quyền xóa dựa trên các tham số request ban đầu.

`expires_in` là số giây tương đối. Trong JWT, `exp` là mốc thời gian tuyệt đối dạng NumericDate (giây UTC). Không nhầm giây và mili giây khi xử lý TTL.

### 10.2. JWT access token và opaque access token

Ví dụ payload **JWT access token minh họa**, không phải JWT hoàn chỉnh có chữ ký:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893492900,
  "jti": "at-demo-8c91"
}
~~~

Resource server phải xác minh **chữ ký, thuật toán/khóa, issuer, audience, thời hạn, loại token, scope và quyền trên đối tượng cụ thể** trước khi cấp quyền. Nếu AS phát hành **opaque access token**, RS dùng introspection hoặc cơ chế kiểm tra đã thỏa thuận, không giả định có thể giải mã nó thành JWT.

**Định dạng access token không thay đổi yêu cầu kiểm tra code tại token endpoint.** JWT vs opaque là lựa chọn representation/verification của access token sau phát hành, còn code exchange có các điều kiện độc lập.

### 10.3. OIDC ID token và nonce

Khi client thực hiện **OpenID Connect** (thường có `openid` trong scope), token endpoint của Authorization Code flow có thể trả:

~~~json
{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 900,
  "id_token": "<SIGNED_ID_TOKEN>"
}
~~~

ID token dành cho **client xác minh kết quả xác thực**. Client phải kiểm tra chữ ký hoặc cơ chế tương ứng, issuer, audience là client, thời gian, authorized party nếu áp dụng và **nonce khi nonce đã được gửi/yêu cầu theo profile**. Không dùng ID token làm Bearer credential gửi Orders API.

**Nonce, state và PKCE khác nhau:** nonce liên kết kết quả xác thực/ID token; state hoặc cơ chế tương đương liên kết authorization response với request; PKCE ràng buộc authorization code với verifier.

### 10.4. Refresh token được bảo vệ thế nào?

Refresh token không được đưa vào URL, browser history, analytics hoặc log. Khi AS cấp refresh token cho public client, RFC 9700 yêu cầu bảo vệ replay bằng **refresh token rotation hoặc sender-constrained refresh token** theo profile. Có thể kết hợp refresh token rotation, lưu trữ bảo vệ, TTL/idle/absolute lifetime, client binding và revocation.

~~~text
R1 ACTIVE --refresh thành công--> R1 USED, R2 ACTIVE
R1 USED   --bị dùng lại-------> nghi replay, xử lý family/grant
~~~

Thu hồi refresh token **không tự vô hiệu mọi access token JWT xác minh offline** đã cấp trước đó nếu RS không có kiểm tra trạng thái bổ sung.

### 10.5. Bảo vệ token response

- Dùng HTTPS/TLS và kết nối đến token endpoint đúng issuer.
- Với response chứa token/secret, dùng `Cache-Control: no-store`, `Pragma: no-cache` theo OAuth 2.0.
- Không đặt token vào response `Location`, query, fragment hoặc JavaScript console.
- Không log raw response JSON ở gateway, SDK HTTP, APM, proxy hoặc crash reporter.
- Giới hạn quyền truy cập token theo client type; cân nhắc BFF để tránh phơi access/refresh token cho JavaScript browser.
- Chỉ gửi access token đúng audience cho resource server qua `Authorization` header hoặc transport được profile chỉ định.

## 11. Các lỗi ở token endpoint và ý nghĩa

Khi validation thất bại, AS trả **lỗi theo OAuth**, không cấp token từng phần. Các lỗi phổ biến:

| Error | Tình huống điển hình |
|---|---|
| `invalid_request` | Request thiếu/sai tham số bắt buộc, không đúng cú pháp hoặc trùng tham số không hợp lệ |
| `invalid_client` | Confidential client authentication thất bại, method/credential không hợp lệ |
| `invalid_grant` | Code sai, hết hạn, đã dùng, không thuộc client, redirect không khớp hoặc PKCE verifier sai |
| `unauthorized_client` | Client không được sử dụng Authorization Code grant |
| `unsupported_grant_type` | AS không hỗ trợ grant type được yêu cầu |
| `invalid_scope` | Scope không biết, không hợp lệ hoặc vượt phạm vi được phép trong ngữ cảnh request |

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

**Phân biệt `invalid_client` với `invalid_grant`:**

- `invalid_client`: client chưa được xác thực thành công tại token endpoint.
- `invalid_grant`: grant/code không thể đổi thành token, ngay cả khi client đã xác thực đúng.

Theo RFC 6749, `invalid_client` có quy tắc status/header riêng, chẳng hạn **HTTP 401** với `WWW-Authenticate` khi client dùng Authorization header. Không trả chi tiết secret, code verifier, subject hoặc toàn bộ nguyên nhân nội bộ trong error description để tránh credential probing.

### 11.1. Xử lý lỗi an toàn ở client

- `invalid_grant`: không retry vô hạn cùng code; kiểm tra sai state, PKCE, redirect hoặc code đã dùng và bắt đầu authorization flow mới khi cần.
- `invalid_client`: kiểm tra client registration/secret/key ở backend, không thử client authentication method yếu hơn như fallback.
- `invalid_request`: rà soát form encoding, field bắt buộc và việc truyền code/verifier.
- `invalid_scope`: kiểm tra granted permissions, không tự mở rộng quyền hoặc sửa claim trong JWT.
- HTTP 5xx/network timeout: retry có kiểm soát ở mức **flow**, không coi code có thể dùng lại sau khi AS đã xử lý thành công.

Không đưa authorization code, raw token, `code_verifier` hay client secret vào log lỗi để debugging.

### 11.2. Lỗi token endpoint khác lỗi resource server

| Bước | Ví dụ lỗi | Hệ quả |
|---|---|---|
| **Token endpoint** | `invalid_grant` | Không cấp access token từ code |
| **Orders API** | `invalid_token`, HTTP 401 | Access token sai chữ ký/audience/expiry hoặc thiếu credential |
| **Orders API** | `insufficient_scope`, HTTP 403 | Token có hiệu lực nhưng thiếu quyền action theo scope |
| **Orders API** | 403 hoặc 404 theo policy | Chủ thể không có quyền trên resource cụ thể |

Không giải quyết lỗi 401 ở Orders API bằng cách bỏ audience validation; hãy kiểm tra token đã được cấp cho đúng API và đang dùng đúng loại credential.

## 12. Ví dụ thiết kế token endpoint bằng Java

**Đây là pseudocode mô tả trách nhiệm, không phải implementation production của OAuth.** Các lớp `VerifiedClient`, `AuthorizationCodeStore`, `CodeGrant`, `TokenPolicy` và `TokenService` là khái niệm do ứng dụng định nghĩa. Trong triển khai thực tế, ưu tiên framework Authorization Server được duy trì thay vì tự xây endpoint cấp token và crypto.

### 12.1. Ví dụ sai: ký token khi chỉ thấy code tồn tại

~~~java
// SAI: không kiểm tra client, PKCE, redirect và single-use.
TokenResponse exchange(TokenRequest req) {
    CodeGrant grant = codeStore.find(req.code());
    if (grant == null) {
        throw new InvalidGrantException();
    }
    return tokenService.issueForSubject(
        grant.subject(),
        req.requestedScope(),
        req.requestedAudience());
}
~~~

Hệ thống này có thể cấp scope/audience do client tự khai, cho bên khác đổi code bị chặn hoặc tạo hai token từ cùng một code. Chữ ký JWT đúng **không cứu được quyết định phát hành sai**.

### 12.2. Phân rã quá trình exchange thành những bước xác minh

~~~java
// Pseudocode: không tự thực thi giao thức OAuth/cryptography từ đầu.
TokenResponse exchangeCode(
        HttpRequest request,
        Instant now) {

    // 1. Nhận diện và xác thực confidential client nếu áp dụng.
    VerifiedClient client = clientAuthenticator.verify(request);
    require(client.allowedGrants().contains("authorization_code"));

    // 2. Tra code, sau đó khóa grant/code theo transaction.
    CodeLookup lookup = codeStore.secureLookup(request.code());
    require(lookup != null);

    ConsumedGrant consumed = transaction.run(() -> {
        CodeGrant grant = codeStore.lockAndRead(lookup.id());

        require(grant.status() == ACTIVE);
        require(now.isBefore(grant.expiresAt()));
        require(grant.clientId().equals(client.id()));

        redirectValidator.verifyOriginalBinding(
            grant.redirectUri(), request.redirectUri());
        pkceVerifier.verify(
            grant.codeChallenge(),
            grant.codeChallengeMethod(),
            request.codeVerifier());

        ApprovedPermissions allowed = tokenPolicy.evaluate(
            client,
            grant.subject(),
            grant.grantedScopes(),
            grant.allowedResources());

        // Consume-once và grant state phải commit nhất quán.
        codeStore.markConsumed(grant.id(), now);
        return new ConsumedGrant(grant, allowed);
    });

    // Fail-closed: nếu token issuance thất bại, code vẫn đã tiêu thụ;
    // client phải khởi tạo flow mới, không đổi lại cùng code.
    return tokenService.issueWithinApprovedGrant(consumed);
}
~~~

Ví dụ nêu rõ thứ tự **client → code → redirect/PKCE → scope/audience → consume-once → issue**. Nhưng khi chuyển thành kiến trúc thực tế cần chú ý:

- `require(...)` được minh họa như phép kiểm tra có lỗi OAuth thích hợp; không phải ném tùy ý lỗi HTTP 500.
- Phải bảo đảm trạng thái code được **tiêu thụ nguyên tử trên toàn bộ cụm**; row lock không hữu ích nếu các node đọc từ replica thiếu nhất quán.
- **Lưu grant/token state, ký token, commit và trả HTTP response** cần có thiết kế transactional/fail-closed nhất quán với framework: không được có hai request cùng nhận token từ một code.
- Nếu code bị replay, AS cần từ chối và ghi audit; nếu đánh dấu thu hồi token đã cấp, thay đổi revocation phải **được commit** kể cả khi response trả lỗi.
- Không tái cấp token từ code đã USED chỉ vì client báo timeout.
- Những kiểm tra issuer, client method, client registration, resource indicators, policy và error response cần được framework thực thi theo profile thực tế.

### 12.3. Điều kiện cập nhật một lần bằng SQL

~~~sql
-- Minh họa; các kiểm tra PKCE/client/redirect đã diễn ra theo chính sách.
UPDATE authorization_codes
SET status = 'USED',
    consumed_at = CURRENT_TIMESTAMP
WHERE code_hash = :verified_code_hash
  AND client_id = :verified_client_id
  AND status = 'ACTIVE'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Ứng dụng phải kiểm tra số hàng cập nhật bằng 1; nếu 0 thì từ chối `invalid_grant`. Một câu SQL không đủ biểu diễn toàn bộ token issuance/rollback/revocation, nhưng **điều kiện thay đổi trạng thái** là minh họa cho tính single-use.

### 12.4. Đường xử lý reuse không được rollback nhầm

Giả sử AS đã cấp token từ code C1. Một request khác gửi lại C1, AS muốn thu hồi các token đã phát hành theo C1:

~~~text
BEGIN TRANSACTION
  lock code C1
  detect C1 == USED
  revoke grants/tokens liên quan nếu policy yêu cầu và khả thi
  insert audit event redacted
COMMIT
respond invalid_grant
~~~

**Không ném exception làm rollback lệnh revoke/audit** bên trong một transaction mặc định rồi tuyên bố đã thu hồi. Cần ranh giới transaction hoặc result type cho phép commit trạng thái bảo mật **trước khi trả lỗi**. Không log code thô hay access/refresh token đã cấp.

## 13. Spring Security: client và authorization server là hai vai trò khác nhau

Trong Java, nên phân biệt framework chức năng:

| Thành phần Spring | Nhiệm vụ |
|---|---|
| **Spring Security OAuth2 Client/OIDC Login** | Tạo authorization request, lưu request, xử lý callback, đổi code, quản lý authorized client |
| **Spring Authorization Server** | Cung cấp authorization endpoint/token endpoint, đăng ký client, xác thực client và phát token |
| **Spring Security OAuth2 Resource Server** | Kiểm tra JWT/opaque access token khi API được gọi |

Một backend đăng nhập bằng OAuth2 Login **không tự trở thành Authorization Server**. Và một resource server biết giải mã JWT **không nên tự nhận authorization code rồi phát refresh token** nếu không có vai trò issuer.

### 13.1. Cấu hình OAuth2 client

Ví dụ cấu hình `application.yml` cho confidential web client:

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
              - orders:read
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Đây chỉ là **cấu hình minh họa**, không chứa secret thật. Thực tế cần client registration ở AS, redirect URI được đăng ký đúng, secrets từ kho bảo vệ, dependencies và OIDC/AS metadata tương ứng. `issuer-uri` chỉ ra issuer, **không tự buộc AS cấp audience của Orders API**; cần chính sách resource/audience đúng.

### 13.2. OAuth2 Login dùng Authorization Code

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ShopWebSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
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

Ví dụ chưa có đầy đủ session/CSRF, login failure handling, cookie policy, authorized client storage, logout và các chi tiết bảo mật production. Cần xác nhận **PKCE S256 được cấu hình và thực thi** cho loại client theo **phiên bản Spring Security thực tế**; không mặc định mọi confidential client luôn được framework bật PKCE.

### 13.3. Không tự tạo `/token` bằng controller thường

Một phương án sai:

~~~java
// SAI: đây không phải OAuth token endpoint đúng chuẩn.
@PostMapping("/token")
public String token(@RequestParam String code) {
    return jwtSigner.sign(code);
}
~~~

Code phải được AS xác minh grant, client, redirect URI, PKCE, single-use và quyền thực tế. Không thể thay thế bằng JWT ký từ chuỗi code. Với Spring Authorization Server, dùng framework quản lý token endpoint và các validation mặc định/cấu hình bắt buộc, sau đó thêm validators/policy phù hợp nhu cầu hệ thống.

### 13.4. Resource server kiểm tra token sau exchange

Orders API là một cấu hình riêng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Đây mới chỉ là cấu hình issuer. Resource server còn phải đặt **expected audience validator**, kiểm tra token type/profile, expiry, scope mapping và authorization theo order ID/tenant/owner. Nếu AS phát hành opaque token, cần introspection. **Không dùng ID token của oauth2Login để gọi Orders API**.

### 13.5. Gọi API bằng access token, không mang code sang API

Backend có thể dùng Spring `RestClient` với base URL cố định khi đã nhận access token đúng audience:

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

`accessToken` là giá trị do OAuth2 authorized client/token lifecycle cung cấp, không lấy từ URL callback không xác minh. Cần TLS, timeout, redirect allowlist, refresh policy và redaction. Không gửi authorization code hoặc refresh token tới Orders API.

## 14. Threat model tập trung vào code exchange

Một token endpoint có thể trả JWT được ký hợp lệ nhưng vẫn không an toàn nếu quá trình **chọn client, kiểm tra grant hoặc quyết định quyền** bị sai. Các mối đe dọa sau cần được xét cùng nhau.

| Tấn công/sai sót | Điều attacker cố đạt | Điều kiện bảo vệ |
|---|---|---|
| **Intercept authorization code** | Lấy code từ callback và đổi token | PKCE S256, client/code binding, redirect an toàn |
| **Code injection** | Đưa code từ phiên của attacker vào callback của nạn nhân | State/request binding, PKCE, issuer checking |
| **Code replay** | Dùng lại code đã được đổi | Atomic single-use, từ chối `invalid_grant`, theo dõi grant |
| **Code redemption race** | Đổi cùng code đồng thời tại hai AS nodes | Transaction/compare-and-swap nhất quán |
| **PKCE downgrade/stripping** | Bỏ challenge hoặc verifier để AS không kiểm tra | Chặn downgrade tại authorization và token endpoint |
| **Redirect URI substitution** | Đổi code với redirect khác | Code-bound redirect URI, strict registration |
| **Client impersonation** | Dùng code của client khác hoặc secret bị lộ | Client binding/authentication và secret rotation |
| **Authorization Server mix-up** | Client gửi code đến AS khác | Issuer/request binding, metadata/token endpoint đáng tin |
| **Scope/audience escalation** | Xin token với quyền lớn hơn grant | AS áp granted scope/resource policy |
| **Token substitution** | Dùng ID token làm access token hoặc sai aud | Token typing/claims validation tại RS |
| **Credential leakage** | Đọc code/verifier/secret/token từ log/URL | TLS, redaction, browser/BFF storage bảo vệ |
| **Retry ambiguity** | Client đổi lại code sau network timeout | Fail-closed, code single-use, flow restart có kiểm soát |
| **DoS / brute force** | Đoán code, thử credential hoặc chiếm tài nguyên AS | Entropy, TTL, rate limit, resource controls và giám sát |
| **Downstream confused deputy** | Service quyền rộng phục vụ yêu cầu user không đủ quyền | Delegation context và resource/action authorization |

### 14.1. Code bị đánh cắp trước khi đổi

Kẻ tấn công có code nhưng không có verifier:

~~~text
Kẻ tấn công biết:
    code = C1

AS đang giữ:
    code_challenge = S256(V1)

Kẻ tấn công không có:
    code_verifier = V1

POST /token với C1 và verifier sai
    => DENY, không phát access token.
~~~

Nếu attacker lấy được cả **code và verifier**, PKCE không thể bảo vệ hoàn toàn. Cần bảo vệ client session, script, redirect URI, storage và những thành phần có quyền đọc pending authorization state.

### 14.2. Attacker đổi code trước và kết quả phát hiện replay

Nếu một AS thiếu PKCE hoặc client secrets bị lộ, attacker có thể đổi code trước client hợp lệ. Khi client hợp lệ thử đổi lại code, AS phát hiện USED và từ chối. **Không thể kết luận request đầu tiên chắc chắn là của client hợp lệ chỉ vì nó đến trước**. Cần liên kết code với token/grant đã phát hành, đánh giá revoke và điều tra.

### 14.3. Log/telemetry là một phần của trust boundary

Không ghi raw:

~~~text
GET /callback?code=<AUTHORIZATION_CODE>&state=<STATE>
POST body: code_verifier=<SECRET>
Authorization: Basic <CLIENT_CREDENTIALS>
HTTP 200 token response: access_token=<SECRET>, refresh_token=<SECRET>
~~~

Có thể lưu metadata có kiểm soát:

~~~text
traceId
issuerId
clientId
grantType=authorization_code
authRequestId (không chứa secret)
result=SUCCESS | FAILURE
failureCategory=CODE_EXPIRED | PKCE_MISMATCH | REPLAY | ...
latencyBucket
tokenType
scopeNames/audienceIds nếu chính sách cho phép
~~~

Ngay cả `clientId`, `subjectId`, địa chỉ IP và scope có thể là dữ liệu cá nhân hoặc nhạy cảm; cần quản lý retention/quyền truy cập. Tuyệt đối không dựa vào log chứa token thật để phân tích một lỗi PKCE.

## 15. Ma trận kiểm thử token endpoint

### 15.1. Bảo vệ client, code và PKCE

| Tình huống | Kết quả mong muốn |
|---|---|
| Code hợp lệ, đúng client, redirect URI, PKCE S256 và còn hạn | Có thể phát token trong giới hạn grant |
| Code không tồn tại | `invalid_grant`; không tiết lộ thêm về user |
| Code hết hạn | Từ chối |
| Code đã được dùng | Từ chối và xử lý replay theo policy |
| Hai request dùng cùng code đồng thời | **Tối đa một lần** đổi thành công |
| Code của client A dùng ở client B | Từ chối |
| Confidential client không xác thực | `invalid_client` hoặc lỗi theo contract |
| Confidential client dùng auth method khác registration | Từ chối |
| Public client gửi client_id và giả như có secret | Không coi client_id là bằng chứng bí mật |
| Code có PKCE challenge nhưng token request thiếu verifier | Từ chối; không downgrade |
| Code verifier sai | Từ chối |
| Code verifier sai độ dài/tập ký tự | Từ chối |
| Authorization request dùng S256 nhưng token request cố thay method | AS dùng method đã lưu; từ chối sai |
| Redirect URI trong token request khác URI gốc | Từ chối |
| Request thiếu/sai grant_type | Không đổi code thành token |
| Request có tham số bị trùng hoặc malformed | Từ chối theo OAuth error contract |

### 15.2. Policy cấp quyền và token response

| Tình huống | Kết quả mong muốn |
|---|---|
| Client request scope rộng hơn scope AS đã cấp | Token chỉ phản ánh quyền được phép hoặc AS từ chối |
| Client cố tự khai `sub=admin` tại token endpoint | Không thay subject của grant |
| Code dành cho Orders API nhưng xin audience Payments API | Không mở rộng quyền resource |
| Grant của tenant A được dùng để xin tenant B | Từ chối theo policy |
| Token response thành công | TLS, JSON và header chống cache phù hợp |
| Access token JWT có `iss`, `aud`, `scope`, `exp` sai | Test phát hiện lỗi phát hành |
| OIDC code flow nhưng ID token sai issuer/audience/nonce | Client từ chối ID token |
| Resource server nhận ID token thay access token | Từ chối |
| Opaque token inactive khi introspection | Resource server từ chối |
| Access token đủ scope nhưng người dùng không có quyền với order ID | Resource server từ chối |
| Refresh token được cấp cho public client | Rotation hoặc sender constraint theo security BCP |

### 15.3. Race, retry và hạ tầng

- Gửi đồng thời 10–100 token requests với cùng code qua nhiều AS instances; **chỉ một transaction được tiêu thụ code thành công**.
- Khi AS commit code=USED nhưng response bị mất, client không thể đổi lại code tùy ý.
- Khi mã bị dùng lại, audit/revocation (nếu policy yêu cầu) được **commit**, không rollback vì exception trả cho caller.
- Request vượt giới hạn kích thước và malformed form bị từ chối với tài nguyên xử lý được kiểm soát.
- Rate limit giúp giảm brute force/DoS mà không phá người dùng hợp lệ sau NAT hoặc nhiều browser tabs.
- Token endpoint yêu cầu HTTPS; không để code, verifier, client secret hoặc token trong query.
- CDN/API gateway/APM/error logger và client HTTP logger không ghi credential.
- Clock skew và TTL được kiểm thử; không cho code đã hết hạn được đổi chỉ vì một node có giờ sai.
- Callback và token endpoint có issuer binding đúng trong trường hợp client cấu hình nhiều AS.
- Key rotation của AS không làm RS chấp nhận khóa từ issuer bất kỳ; JWT mới được xác minh với khóa tin cậy.

### 15.4. Phân biệt kiểm thử token endpoint với resource server

Một token endpoint trả HTTP 200 **không chứng minh** Orders API đã có quyền đọc `order-721`. Cần hai nhóm test:

1. **Issuance tests:** code/grant/client/PKCE/redirect được kiểm tra đúng, token được phát với các quyền hợp lệ.
2. **Resource authorization tests:** RS xác minh token và policy, từ chối tenant/owner/action ngoài quyền.

Thiếu nhóm thứ hai vẫn có nguy cơ BOLA/IDOR. Thiếu nhóm thứ nhất khiến issuer có thể phát token rộng quyền cho sai client.

## 16. Tình huống tự kiểm tra

### A. Code và verifier khác request

Shop Web nhận code `C1` từ tab A nhưng chọn `code_verifier` của tab B khi gọi token endpoint.

**Kết quả?** AS phải từ chối vì PKCE challenge của C1 không khớp verifier của tab B. Client nên giữ pending authorization state theo từng request/tab thay vì một biến toàn cục dễ bị ghi đè.

### B. Client secret đúng nhưng PKCE sai

Confidential client xác thực thành công bằng secret, nhưng gửi verifier sai cho code đã ràng buộc PKCE.

**Kết quả?** Không cấp token. Client authentication và PKCE là hai điều kiện độc lập; secret đúng không bỏ qua PKCE.

### C. Token request không có redirect URI

Authorization request có `redirect_uri=https://shop.example.com/callback`. Client đổi code nhưng bỏ tham số `redirect_uri`.

**Kết quả?** Theo RFC 6749, khi URI đã được đưa vào authorization request, token request phải chứa cùng giá trị đó. AS phải từ chối nếu thiếu hoặc không khớp.

### D. Hai request cùng code

Hai instance backend đồng thời gửi token request dùng cùng code còn hạn.

**Kết quả?** Chỉ tối đa một request được phép tiêu thụ code. AS cần atomic single-use; một lần kiểm tra trạng thái ACTIVE trước khi ký là không đủ.

### E. Browser callback cung cấp token endpoint

Callback có query `token_endpoint=https://other.example.net/token` và client sử dụng ngay URL đó để gửi code.

**Kết quả?** Không an toàn. Token endpoint phải được lấy từ issuer/client registration đáng tin; không cho browser tự chỉ đích gửi code/verifier/client secret.

### F. Code đổi thành công nhưng không đủ quyền xem đơn hàng

Alice nhận access token scope `orders:read` hợp lệ, nhưng yêu cầu order của Bob.

**Kết quả?** API phải từ chối nếu không có quyền chia sẻ/delegation. Code exchange thành công chỉ chứng minh grant được cấp đúng; scope không thay ownership/resource authorization.

### G. OIDC ID token được dùng làm Bearer access token

Shop Web nhận `id_token` có audience là `shop-web`, sau đó gửi nó tới Orders API.

**Kết quả?** API phải từ chối vì token sai mục đích/profile/audience. OIDC ID token dành cho client xác minh login; API cần access token dành cho chính mình.

### H. Mạng timeout sau khi token được cấp

AS commit code USED và trả token, nhưng response bị mất. Client retry cùng code rồi nhận `invalid_grant`.

**Kết quả?** Đây có thể là hệ quả an toàn của single-use. Client không retry vô hạn; cần thực hiện authorization flow mới hoặc cơ chế khôi phục đã được thiết kế riêng mà không cho đổi lại code một cách tùy tiện.

### I. Access token được cấp quá scope

Alice chỉ đồng ý `orders:read`, nhưng token endpoint trả access token với `orders:admin`.

**Kết quả?** Đây là lỗi nghiêm trọng của policy tại AS; cần ngừng phát hành sai, đánh giá token đã cấp và khả năng thu hồi. Chữ ký JWT hợp lệ không bù được quyết định cấp quyền sai.

### J. AS có nhiều node và cache riêng

Node A ghi code USED vào cache của A, node B chưa thấy cập nhật và vẫn cấp token.

**Kết quả?** Trạng thái single-use không đủ nhất quán toàn cụm. Cần kho hoặc cơ chế đồng bộ đảm bảo không có hai request đổi cùng code thành công.

## 17. Ghi nhớ và checklist trước production

Một **code exchange an toàn** phải giữ chuỗi điều kiện:

~~~text
Authorization callback hợp lệ
    |
    v
State / issuer / pending request phù hợp
    |
    v
POST /token qua HTTPS đến issuer tin cậy
    |
    v
Client identity / authentication và allowed grant đúng
    |
    v
Code tồn tại, đúng client, redirect URI, còn hạn
    |
    v
PKCE verifier khớp challenge từ authorization request
    |
    v
Code được tiêu thụ một lần nguyên tử
    |
    v
Access token chỉ có subject/scope/audience đã được phê duyệt
    |
    v
Client bảo vệ token và RS kiểm tra token + resource authorization
~~~

Trước khi go-live, tự hỏi:

1. **Đúng issuer chưa?** Token endpoint lấy từ metadata tin cậy, không từ callback tùy ý?
2. **Đúng client chưa?** Public vs confidential, grant type, client authentication method?
3. **Đúng code chưa?** Còn hạn, do đúng AS cấp, thuộc client, chưa dùng?
4. **Đúng redirect URI chưa?** Ràng buộc với authorization request gốc?
5. **Đúng PKCE chưa?** S256, verifier của cùng request, không downgrade?
6. **Đúng grant chưa?** Không tăng subject, scope, audience hoặc tenant?
7. **Đúng tính một lần chưa?** Atomicity trên nhiều node, replay response và audit?
8. **Đúng token response chưa?** TLS, JSON, no-store, token type, TTL, ID/refresh nếu được cấp?
9. **Đúng ở RS chưa?** Issuer, audience, scope, thời gian, ownership và resource/action?
10. **Đúng vận hành chưa?** Log redaction, rate limiting, key rotation, retry và incident response?

**Kết luận:** code exchange là **ranh giới chuyển một authorization code ngắn hạn thành credential có thể sử dụng**. Token endpoint phải kiểm tra **client, code, redirect URI, PKCE, grant và single-use** trước khi phát access token. Phía client phải bảo vệ request-response binding và nơi lưu token; resource server vẫn phải xác minh **issuer, audience, scope, thời gian và quyền trên từng tài nguyên**. Bất kỳ mắt xích nào bị bỏ qua đều có thể biến một JWT đúng chữ ký thành quyền truy cập được cấp sai.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, §4.1.3–4.1.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.3): authorization code exchange tại token endpoint và token response.
- [RFC 6749 — Token Endpoint Error Response, §5.2](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): mã lỗi và quy tắc phản hồi OAuth.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): verifier, challenge, S256 và code interception.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, code injection, redirect, refresh replay và an toàn OAuth hiện đại.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): chống authorization server mix-up.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): redirect, external browser và PKCE cho native clients.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): khám phá endpoints/issuer đáng tin.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): token dành cho resource cụ thể.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): downstream token/delegation.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer và lỗi resource server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, issuer, audience, scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): yêu cầu thu hồi token.
- [RFC 9449 — Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): code flow OIDC, ID token, nonce và token endpoint.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client và quản lý token.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): triển khai authorization/token endpoints ở Java.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): thực hành OAuth an toàn.
