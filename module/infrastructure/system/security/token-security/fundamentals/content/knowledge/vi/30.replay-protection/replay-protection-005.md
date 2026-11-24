# Nonce và state trong replay protection

## 1. Bài toán cần giải quyết

Trong hệ thống xác thực dùng OAuth 2.0 và OpenID Connect (OIDC), người dùng thường bắt đầu đăng nhập ở ứng dụng (client/relying party – RP), được chuyển sang Authorization Server (AS)/OpenID Provider (OP), rồi quay lại ứng dụng qua một địa chỉ callback. Trong khoảng thời gian chuyển hướng đó, ứng dụng phải biết **phản hồi nào thuộc về yêu cầu đăng nhập nào**.

Hai giá trị thường xuất hiện trong quy trình này là **`state`** và **`nonce`**. Chúng đều phải khó đoán và được tạo mới cho từng giao dịch, nhưng được dùng ở những vị trí khác nhau:

- **`state`**: ràng buộc *phản hồi chuyển hướng* từ AS với giao dịch OAuth mà client đã khởi tạo; giúp phòng chống login CSRF và phát hiện phản hồi không thuộc phiên hiện tại.
- **`nonce`** trong OIDC: ràng buộc *ID Token* do OP phát hành với yêu cầu xác thực đã gửi; giúp phát hiện ID Token bị chèn hoặc phát lại từ yêu cầu khác.

Ví dụ: kẻ tấn công đăng nhập vào tài khoản của **chính họ**, lấy đường dẫn callback chứa authorization code rồi dụ nạn nhân mở đường dẫn đó. Nếu ứng dụng không kiểm tra `state`, trình duyệt nạn nhân có thể bị đăng nhập nhầm vào tài khoản của kẻ tấn công (login CSRF). Một ví dụ khác: ứng dụng chấp nhận ID Token hợp lệ về chữ ký nhưng được phát hành cho **lần đăng nhập khác**; việc đối chiếu `nonce` sẽ giúp từ chối token đó.

**Giới hạn quan trọng:** `state` và OIDC `nonce` bảo vệ *giao dịch đăng nhập*. Nếu access token dạng bearer đã bị đánh cắp, bên giữ token vẫn có thể gọi API trong thời hạn token còn hiệu lực; cần các cơ chế bảo vệ token khác, được trình bày ở phần 7.

## 2. Phân biệt state, nonce và các giá trị gần giống

| Giá trị | Ai tạo và gửi? | Kiểm tra ở đâu? | Mục đích chính |
| --- | --- | --- | --- |
| `state` | Client tạo, gửi trong authorization request; AS trả lại trong authorization response | Client đối chiếu ngay khi nhận callback, trước khi đổi code | Ràng buộc phản hồi OAuth với yêu cầu và phiên trình duyệt tương ứng; giảm login CSRF |
| OIDC `nonce` | RP tạo, gửi cho OP trong authorization request; OP đưa vào claim `nonce` của ID Token | RP kiểm tra trên **ID Token đã được xác thực** | Ràng buộc ID Token với lần xác thực hiện tại; hạn chế chèn/phát lại ID Token từ lần khác |
| PKCE `code_verifier` / `code_challenge` | Client giữ bí mật `code_verifier`, gửi `code_challenge` tới AS | AS kiểm tra lúc client đổi authorization code thành token | Hạn chế kẻ đánh cắp/chèn authorization code đổi được code thành token |
| `jti` (JWT ID) | Bên phát hành JWT đặt vào claim (nếu dùng) | Bên nhận có thể kết hợp cache chống dùng lại trong cửa sổ thời gian | Định danh token; **chỉ có `jti` không tự ngăn replay** |
| DPoP nonce | Authorization Server hoặc Resource Server cấp khi cần | Server kiểm tra trong DPoP proof theo quy tắc DPoP | Giới hạn việc tái sử dụng DPoP proof; khác OIDC `nonce` |

Không nên coi `state`, `nonce` và PKCE là ba tên gọi cho cùng một cơ chế: chúng bảo vệ các bước khác nhau của giao thức.

### Mối liên hệ với JWT, opaque token, access token và refresh token

- **ID Token** là JWT dùng để mô tả sự kiện xác thực cho client OIDC; claim `nonce` của nó phục vụ kiểm tra giao dịch đăng nhập, khi request có truyền nonce.
- **Access token** dùng để truy cập tài nguyên/API. Nó có thể là JWT hoặc opaque token; Resource Server phải kiểm tra chữ ký hoặc introspection, `iss`, `aud`, thời hạn và quyền (`scope`/permission) theo loại token. Không dùng `nonce` từ ID Token làm cơ chế chống replay cho access token.
- **Refresh token** dùng để xin access token mới. Bảo vệ bằng lưu trữ an toàn, rotation và phát hiện tái sử dụng khi phù hợp; `state` không áp dụng cho mỗi lần refresh.

## 3. Luồng Authorization Code + PKCE + OIDC

```mermaid
sequenceDiagram
    autonumber
    participant B as Trình duyệt
    participant C as Ứng dụng / OIDC Client
    participant A as Authorization Server / OP
    B->>C: GET /login
    C->>C: Sinh state, nonce, code_verifier
    C->>C: Lưu giao dịch theo phiên; TTL ngắn
    C-->>B: Redirect tới /authorize (state, nonce, code_challenge)
    B->>A: Yêu cầu xác thực /authorize
    A->>B: Xác thực và đồng ý cấp quyền
    A-->>B: Redirect về callback?code=...&state=...
    B->>C: Gửi callback
    C->>C: Kiểm tra state và consume giao dịch đúng một lần
    C->>A: POST /token (code, code_verifier, redirect_uri)
    A-->>C: ID Token, access token, ...
    C->>C: Xác minh ID Token và đối chiếu nonce
    C-->>B: Tạo phiên đăng nhập ứng dụng
```

Ví dụ authorization request (các giá trị rút gọn để minh họa):

```http
GET /authorize?response_type=code
  &client_id=web-client
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
  &scope=openid%20profile
  &state=state-random-cho-giao-dich-01
  &nonce=nonce-random-cho-giao-dich-01
  &code_challenge=base64url-sha256-code-verifier
  &code_challenge_method=S256
```

Khi callback thành công, AS trả `code` và lặp lại `state` client đã gửi. Client phải kiểm tra `state` **trước khi** đưa `code` đi đổi token. Sau đó client gửi `code_verifier` qua token endpoint; OP trả ID Token chứa claim `nonce` (nếu nonce đã được yêu cầu). Client xác thực ID Token, rồi so sánh claim `nonce` với giá trị đã lưu cho giao dịch đó.

Trong OIDC Authorization Code Flow, `nonce` là tham số tùy chọn theo OIDC Core, nhưng sử dụng và kiểm tra nó là lựa chọn phòng vệ hữu ích. Một số flow OIDC cũ có yêu cầu nonce nghiêm ngặt hơn; với ứng dụng mới nên ưu tiên Authorization Code Flow cùng PKCE thay cho Implicit Flow.

## 4. Quy tắc xử lý `state`

1. **Sinh mới cho mỗi lần bắt đầu đăng nhập:** dùng trình sinh số ngẫu nhiên an toàn mật mã (CSPRNG), ví dụ 32 byte ngẫu nhiên rồi mã hóa Base64URL. Không sử dụng ID tăng dần, timestamp, username, hash không có bí mật hoặc giá trị cố định.
2. **Ràng buộc với phiên của trình duyệt:** lưu `state` phía server cùng session đăng nhập tạm thời, mã định danh AS/issuer, `nonce`, `code_verifier`, thời điểm hết hạn và dữ liệu điều hướng dự định. Với SPA thuần frontend, cần dùng cách lưu giao dịch phù hợp với thư viện OIDC và mô hình đe dọa; mô hình backend-for-frontend (BFF) giúp giữ bí mật và token ở backend.
3. **Xác minh trên mọi callback:** `state` phải tồn tại, khớp chính xác với giao dịch đang chờ của đúng phiên trình duyệt và chưa hết hạn. Áp dụng cả khi AS trả tham số `error`, vì phản hồi lỗi cũng cần gắn với đúng giao dịch.
4. **Dùng một lần:** khi xử lý callback, đánh dấu/tiêu thụ giao dịch bằng thao tác nguyên tử (ví dụ atomic get-and-delete trong store). Không cho cùng `state` hoàn tất hai lần. Nếu xảy ra lỗi đổi token sau khi đã consume, người dùng bắt đầu lại giao dịch đăng nhập.
5. **Ràng buộc đúng AS:** nếu client làm việc với nhiều issuer, lưu issuer dự kiến theo giao dịch, dùng endpoint đã cấu hình và kiểm tra `iss` trong authorization response khi giao thức/AS hỗ trợ (RFC 9207). Việc chỉ kiểm tra `state` không đủ để giải quyết mọi trường hợp authorization-server mix-up.

Không gói access token, refresh token, mật khẩu, thông tin cá nhân hoặc URL chuyển hướng tùy ý vào `state`. Nếu cần quay lại một màn hình sau đăng nhập, lưu `returnUrl` ở server và chỉ chấp nhận đường dẫn nội bộ hợp lệ để tránh open redirect.

Nếu callback nhận một `state` lạ, thiếu, sai phiên, hết hạn hoặc đã dùng, ứng dụng **từ chối đăng nhập**, không đổi code, không tự ghép với giao dịch gần nhất và không tạo session xác thực.

## 5. Quy tắc xử lý OIDC `nonce`

1. **Sinh riêng biệt với `state`** cho mỗi yêu cầu xác thực bằng CSPRNG; ví dụ 32 byte ngẫu nhiên. Không dùng lại nonce giữa các lần login.
2. **Gửi nonce trong authorization request** tới OP và lưu giá trị dự kiến cùng giao dịch `state` trong kho có thời hạn.
3. **Xác thực ID Token trước khi tin claim:** kiểm tra chữ ký bằng khóa hợp lệ của OP, thuật toán được cho phép, `iss` đúng issuer, `aud` chứa client ID, `azp` khi quy tắc OIDC yêu cầu, `exp` và các điều kiện thời gian liên quan. Không lấy claim từ JWT chưa xác minh để ra quyết định tin cậy.
4. **Đối chiếu giá trị:** nếu đã gửi nonce, claim `nonce` trong ID Token phải có mặt và bằng đúng nonce lưu cho giao dịch đã kiểm tra `state`. Mismatch, thiếu claim hoặc không còn giao dịch hợp lệ đều là lỗi đăng nhập.
5. **Hủy giao dịch sau khi dùng:** khi đã xử lý callback, nonce không được tái sử dụng làm nonce dự kiến cho một lần xác thực khác.

**Ví dụ:** Client gửi `nonce=N1` khi người dùng bắt đầu đăng nhập. Kẻ tấn công cố đưa vào một ID Token cũ có `nonce=N0` và chữ ký OP vẫn hợp lệ. Việc kiểm tra chữ ký, issuer, audience, hạn sử dụng có thể chưa phân biệt được token thuộc lần xác thực nào; so sánh `N0 != N1` giúp phát hiện token sai giao dịch.

Nonce **không mã hóa** token, không thay thế việc kiểm tra chữ ký/claims, không bảo vệ mọi API sử dụng access token và không ngăn kẻ tấn công điều khiển toàn bộ phiên trình duyệt đang bị chiếm quyền. Nó hiệu quả khi được lưu, so sánh và tiêu thụ cùng một giao dịch xác thực đáng tin cậy.

## 6. Ví dụ triển khai với Java

Đoạn mã sau minh họa việc sinh giá trị an toàn và tính PKCE S256. Giá trị thực tế phải được lưu trong kho giao dịch của ứng dụng, không ghi trực tiếp vào log.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class OAuthRequestValues {
    private static final SecureRandom RANDOM = new SecureRandom();

    private OAuthRequestValues() {}

    public static String newRandomValue() {
        byte[] bytes = new byte[32]; // 256 bit ngẫu nhiên
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String pkceS256Challenge(String codeVerifier) {
        try {
            byte[] sha256 = MessageDigest.getInstance("SHA-256").digest(
                codeVerifier.getBytes(StandardCharsets.US_ASCII)
            );
            return Base64.getUrlEncoder().withoutPadding().encodeToString(sha256);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }
}
```

Khi mở giao dịch:

```java
String state = OAuthRequestValues.newRandomValue();
String nonce = OAuthRequestValues.newRandomValue();
String codeVerifier = OAuthRequestValues.newRandomValue();
String codeChallenge = OAuthRequestValues.pkceS256Challenge(codeVerifier);

// Lưu (sessionId, state, nonce, codeVerifier, issuer, redirectUri, expiresAt)
// trong một store có TTL ngắn; mỗi giao dịch phải độc lập.
// Tạo URL /authorize với state, nonce, codeChallenge và S256.
// Giữ codeVerifier tại client, KHÔNG gửi nó trong /authorize.
```

Mẫu xử lý callback dưới đây là **giả mã Java** nhằm diễn tả thứ tự kiểm tra. Các tên `attemptStore`, `tokenClient`, `idTokenValidator` là giao diện do ứng dụng cung cấp, không phải API có sẵn trong JDK:

```java
// 1. Xác minh và tiêu thụ giao dịch theo đúng session + callback state.
LoginAttempt attempt = attemptStore.consumeAtomically(sessionId, callbackState)
    .orElseThrow(() -> new SecurityException("Invalid or replayed state"));

if (attempt.expiresAt().isBefore(clock.instant())) {
    throw new SecurityException("Expired login attempt");
}
verifyExpectedAuthorizationServer(attempt.issuer(), callbackIssuer);

// 2. Nếu callback có error: kết thúc với lỗi, không đổi code.
rejectIfAuthorizationError(callbackError);

// 3. Đổi code bằng đúng code_verifier + redirect_uri của giao dịch.
TokenResponse tokens = tokenClient.exchangeCode(
    authorizationCode, attempt.codeVerifier(), attempt.redirectUri()
);

// 4. Kiểm tra chữ ký, issuer, audience, thời hạn và các claims OIDC.
VerifiedIdToken idToken = idTokenValidator.verify(
    tokens.idToken(), attempt.issuer(), expectedClientId
);

// 5. Chỉ tin nonce sau khi ID Token đã được xác minh.
if (idToken.nonce() == null || !idToken.nonce().equals(attempt.nonce())) {
    throw new SecurityException("OIDC nonce mismatch");
}

// 6. Tạo session ứng dụng và đưa người dùng tới returnUrl đã kiểm duyệt.
createAuthenticatedSession(idToken.subject());
```

Lưu ý thực thi:

- `consumeAtomically` cần **nguyên tử** trong hệ nhiều instance; đọc rồi xóa bằng hai thao tác tách biệt tạo ra cửa sổ race condition. Có thể lưu khóa theo `sessionId + state` và thao tác get-and-delete phù hợp.
- Với callback có `error`, vẫn kiểm tra `state` trước rồi mới xử lý lỗi; trong triển khai thực tế, thứ tự các lệnh cần thể hiện rõ điều đó. Dữ liệu callback phải được kiểm tra hình thức và tính hợp lệ trước khi truy cập kho giao dịch.
- Sử dụng thư viện OIDC/OAuth được duy trì để kiểm tra ID Token và các tham số chuẩn; ví dụ trên cố ý không tự viết bộ xác minh JWT hoặc xử lý JWK rotation.
- Nếu dùng cookie phiên, cấu hình `HttpOnly`, `Secure` và `SameSite` phù hợp với kiểu callback (chẳng hạn `Lax` với callback GET điều hướng top-level). Dùng HTTPS cho toàn bộ luồng, không ghi code, token, verifier, state hoặc nonce nguyên văn vào log.

## 7. Khi nào state và nonce vẫn chưa đủ?

| Tình huống tấn công | Kiểm soát cần thiết |
| --- | --- |
| Kẻ tấn công gắn callback OAuth thuộc giao dịch khác vào trình duyệt nạn nhân | `state` ngẫu nhiên, gắn phiên, đối chiếu, TTL và consume một lần |
| ID Token từ lần đăng nhập khác bị chèn/phát lại | Xác thực ID Token và đối chiếu OIDC `nonce` của giao dịch hiện tại |
| Authorization code bị đánh cắp trên đường đi hoặc bị chèn | Authorization Code Flow với **PKCE S256**, redirect URI chính xác, TLS, kiểm tra `state` |
| Nhầm lẫn giữa nhiều Authorization Server/issuer | Ràng buộc issuer theo giao dịch, kiểm tra issuer của phản hồi khi có và luôn xác thực `iss` của ID Token |
| Bearer access token bị đánh cắp và gọi API nhiều lần | Thời hạn token ngắn, kiểm tra `aud`/`scope`, bảo vệ kênh và lưu trữ; cân nhắc token ràng buộc bên gửi như DPoP hoặc mTLS |
| Refresh token bị lấy cắp và dùng lại | Refresh token rotation với reuse detection, hoặc sender-constrained refresh token theo mô hình hệ thống |
| DPoP proof hoặc yêu cầu có chữ ký bị phát lại | Kiểm tra `jti`, `iat`/cửa sổ thời gian và DPoP nonce theo yêu cầu của server; cần cơ chế lưu/chống dùng lại ở bên xác minh |

Với API có thao tác nhạy cảm như chuyển tiền, chống phát lại **nghiệp vụ** còn cần idempotency key, mã giao dịch duy nhất và kiểm soát giao dịch phía server. OIDC nonce không thay thế các biện pháp này.

## 8. Các lỗi thường gặp và kiểm thử

| Lỗi triển khai | Hậu quả | Kiểm thử mong đợi |
| --- | --- | --- |
| Một `state` cố định cho mọi lần đăng nhập | Dễ đoán hoặc ghép sai callback | Hai lần login liên tiếp sinh state khác nhau |
| Chỉ kiểm tra state có tồn tại, không so với đúng phiên | Login CSRF hoặc nhầm lẫn giao dịch | State hợp lệ của browser A bị từ chối ở browser B |
| Giữ lại state sau callback đầu tiên | Có thể xử lý lặp hoặc race condition | Callback thứ hai với cùng state bị từ chối |
| Chấp nhận state hết hạn | Giao dịch cũ vẫn có thể được hoàn tất | State quá TTL bị từ chối |
| Chỉ giải mã ID Token mà không xác minh chữ ký và claims | Có thể chấp nhận token giả/misissued | Token sai chữ ký, `iss`, `aud`, `exp` bị từ chối |
| Có gửi nonce nhưng không so sánh với claim trong ID Token | Token hợp lệ nhưng khác giao dịch vẫn được chấp nhận | Token có nonce cũ, khác hoặc thiếu bị từ chối |
| Gửi `code_verifier` trong URL authorization hoặc log | Làm lộ bằng chứng PKCE | `code_verifier` chỉ xuất hiện ở kho client và token request |
| Tưởng rằng `state`/`nonce` chống được access token replay | Bỏ sót cơ chế bảo vệ Resource Server | API vẫn áp dụng hạn dùng, audience, scope và kiểm soát phù hợp |

Một bộ kiểm thử tối thiểu nên có: luồng hợp lệ thành công; thiếu/sai state; sai phiên; giao dịch hết hạn; callback lặp; ID Token thiếu/sai nonce; ID Token sai chữ ký/issuer/audience; code sai PKCE; AS khác issuer dự kiến; và hai giao dịch đăng nhập song song không ghi đè nhau.

## 9. Ghi nhớ

- `state` trả lời câu hỏi: **"Phản hồi OAuth này có thuộc đúng giao dịch và phiên trình duyệt mà tôi đã khởi tạo không?"**
- OIDC `nonce` trả lời câu hỏi: **"ID Token đã xác minh này có được phát hành cho đúng yêu cầu xác thực hiện tại không?"**
- **PKCE** ràng buộc bước đổi authorization code với client đã khởi tạo luồng; cả ba nên phối hợp trong Authorization Code Flow.
- Mọi giá trị chống replay phải được **sinh ngẫu nhiên an toàn, giới hạn thời gian, gắn với đúng ngữ cảnh và kiểm tra trước khi tin kết quả**. Với giao dịch một lần, cần tiêu thụ nguyên tử.
- Việc kiểm tra token ở Resource Server, bảo vệ refresh token và phòng chống phát lại thao tác nghiệp vụ là các lớp bảo vệ riêng.

**Chuẩn tham khảo:** OAuth 2.0 (RFC 6749); OpenID Connect Core 1.0; PKCE (RFC 7636); OAuth 2.0 Authorization Server Issuer Identification (RFC 9207); DPoP (RFC 9449); OAuth 2.0 Security Best Current Practice (RFC 9700).
