# State — Ràng buộc phản hồi OAuth/OIDC với yêu cầu đã khởi tạo

Một người dùng bấm “Đăng nhập bằng tài khoản công ty”. Ứng dụng chuyển trình duyệt tới nhà cung cấp danh tính (Identity Provider, IdP), người dùng hoàn tất đăng nhập rồi trình duyệt quay lại callback của ứng dụng. Ở thời điểm đó, ứng dụng phải biết phản hồi này có thuộc đúng giao dịch mà chính trình duyệt vừa khởi tạo hay không. Nếu không ràng buộc phản hồi với yêu cầu ban đầu, kẻ tấn công có thể tìm cách tráo callback, ép nạn nhân đăng nhập vào tài khoản do kẻ tấn công kiểm soát hoặc gắn nhầm phiên đăng nhập.

Trong OAuth 2.0 và OpenID Connect (OIDC), tham số **`state`** giúp client tương quan phản hồi với authorization request đã khởi tạo. Khi được tạo ngẫu nhiên, lưu theo giao dịch, ràng buộc với đúng browser/session và kiểm tra một lần, state là kiểm soát quan trọng chống CSRF và callback injection.

Bài học thuộc chương **OpenID Connect** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối state với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết phân biệt state với nonce và PKCE, mô hình hóa ranh giới tin cậy, phòng chống giả mạo/replay và thiết kế callback an toàn.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích mục đích của OAuth/OIDC `state` và cách nó ràng buộc authorization response với request đang chờ.
- Phân biệt state với OIDC `nonce`, PKCE `code_verifier` và session cookie.
- Tạo state bằng CSPRNG, đủ entropy, không chứa dữ liệu nhạy cảm và gắn với transaction có TTL.
- Kiểm tra state chính xác tại callback, xử lý lỗi, tiêu thụ một lần và chống callback replay.
- Thiết kế state cho BFF, web app, SPA và nhiều tab/browser transaction đồng thời.
- Nhận diện login CSRF, authorization response injection, open redirect và issuer mix-up.
- Kết hợp state với PKCE, nonce, redirect URI validation và xác minh ID token theo đúng vai trò.
- Viết tiêu chí kiểm thử cho state thiếu/sai/hết hạn/trùng, callback lỗi và phản hồi từ sai authorization server.

## 2. State là gì và giải quyết vấn đề nào?

`state` là một giá trị do client tạo khi bắt đầu authorization request. Authorization server (AS) trả lại giá trị đó trong authorization response, nếu client đã gửi nó. Client so sánh state nhận được với giao dịch đang chờ để xác định phản hồi có tương ứng với yêu cầu ban đầu hay không.

Một luồng giản lược:

1. Ứng dụng tạo giá trị state ngẫu nhiên.
2. Ứng dụng lưu state cùng thông tin giao dịch và ngữ cảnh browser/session.
3. Ứng dụng gửi state trong authorization request tới AS.
4. AS xác thực người dùng/áp dụng consent và trả authorization response có state.
5. Callback nhận state; ứng dụng tìm giao dịch tương ứng, kiểm tra đúng phiên và thời hạn.
6. Nếu hợp lệ, ứng dụng tiếp tục xử lý code/error và đóng giao dịch theo cơ chế một lần.

Ví dụ authorization request:

```http
GET /authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Foidc%2Fcallback
    &scope=openid%20profile
    &state=<random-opaque-state>
    &code_challenge=<pkce-challenge>
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.test
```

Ví dụ authorization response:

```http
GET /oidc/callback?code=<authorization-code>
    &state=<same-random-opaque-state> HTTP/1.1
Host: app.example.test
```

Các chuỗi trong dấu ngoặc nhọn là placeholder, không phải giá trị hoạt động. Trong request thực, URL được mã hóa đúng quy tắc và nằm trên một dòng.

### State là một correlation value

State giúp client trả lời câu hỏi: **“Phản hồi này có gắn với một giao dịch authorization mà tôi đã khởi tạo và còn đang chờ không?”** Nó không phải bằng chứng rằng người dùng đã xác thực, không phải access token, không phải danh tính, không phải quyền truy cập và không thay thế việc xác minh authorization code/ID token.

Một giá trị state hợp lệ chỉ cho phép ứng dụng tiếp tục xử lý đúng transaction. Ứng dụng vẫn phải kiểm tra code exchange, PKCE, issuer, token signature, audience, thời hạn, nonce khi dùng OIDC và authorization sau đăng nhập.

## 3. Login CSRF và authorization response injection

### 3.1. Login CSRF

Trong login CSRF, kẻ tấn công cố làm trình duyệt nạn nhân hoàn tất đăng nhập vào tài khoản của kẻ tấn công tại ứng dụng mục tiêu. Nạn nhân có thể không nhận ra mình đang dùng tài khoản khác. Họ có thể tải lên dữ liệu, lưu thông tin thanh toán hoặc thực hiện thao tác khiến dữ liệu bị gắn vào tài khoản của attacker.

Ví dụ khái niệm:

1. Attacker bắt đầu đăng nhập vào ứng dụng bằng tài khoản của chính attacker.
2. Attacker lấy authorization response/callback tương ứng với giao dịch đó.
3. Attacker dụ nạn nhân mở callback hoặc link được tạo sẵn.
4. Nếu ứng dụng không kiểm tra state và ràng buộc browser transaction, callback có thể tạo phiên đăng nhập của attacker trên browser nạn nhân.

State ngẫu nhiên được gắn với browser/session ban đầu khiến callback do attacker khởi tạo không khớp transaction của nạn nhân và bị từ chối.

### 3.2. Authorization response injection

Kẻ tấn công có thể cố chèn authorization code hoặc response từ giao dịch khác vào callback. Nếu client chỉ kiểm tra “có code” rồi đổi code, ứng dụng có thể nhận kết quả không thuộc request đang chờ. State giúp ràng buộc response; PKCE tiếp tục ràng buộc code với verifier của transaction ban đầu.

### 3.3. Tại sao đây là rủi ro xác thực?

Kết quả là một phiên ứng dụng được tạo trong browser không đúng với ý định đăng nhập của người dùng. Điều này có thể gây tráo danh tính, gắn nhầm tài khoản, rò dữ liệu hoặc khiến hành động sau đó được ghi nhận cho sai principal. Đây là lý do state cần được xem là một phần của ranh giới tin cậy trong authentication flow.

## 4. Tạo state an toàn

### 4.1. Dùng CSPRNG

State cần khó đoán trước khi AS trả về. Dùng bộ tạo số ngẫu nhiên mật mã (CSPRNG), không dùng:

- Timestamp hoặc số thứ tự tăng dần.
- Email, user ID, session ID hoặc chuỗi nối từ dữ liệu người dùng.
- UUID/PRNG không được thiết kế cho mục đích bảo mật.
- Giá trị cố định hoặc dùng lại giữa các lần đăng nhập.

Một lựa chọn triển khai phổ biến là sinh 32 byte ngẫu nhiên rồi Base64url encode. Đây là ví dụ về mức entropy, không phải định dạng bắt buộc duy nhất cho mọi giao thức.

```ts
const state = base64url(secureRandomBytes(32));
```

### 4.2. Không nhúng dữ liệu nhạy cảm

Không dùng state làm nơi chứa:

- Access token, refresh token, authorization code hoặc client secret.
- Mật khẩu, OTP, recovery code hoặc private key.
- Email, số điện thoại, dữ liệu hồ sơ hoặc thông tin định danh không cần thiết.
- URL redirect tùy ý do người dùng cung cấp.

State thường xuất hiện trong URL của authorization request và callback; URL có thể được ghi vào history, proxy log hoặc hệ thống quan sát. Cách an toàn và dễ kiểm soát là dùng **opaque random state** làm khóa tra cứu transaction phía server. Nếu một kiến trúc dùng state tự chứa có ký/mã hóa, nó vẫn cần bảo vệ tính toàn vẹn, thời hạn, chống replay và ràng buộc browser; không nên tự thiết kế định dạng nếu không có nhu cầu rõ.

### 4.3. Lưu state gắn với transaction

Một transaction đang chờ có thể lưu:

```text
state_digest             hash/HMAC của state nếu muốn tránh lưu giá trị thô
transaction_id           định danh nội bộ
browser_session_binding  ràng buộc với browser/session đã bắt đầu
expected_issuer          authorization server đã chọn
client_id                client đã đăng ký
redirect_uri             callback đã cấu hình
code_verifier             PKCE verifier
nonce                     OIDC nonce nếu dùng
intent                    LOGIN / LINK / STEP_UP
return_path                đường dẫn nội bộ đã kiểm tra
created_at / expires_at   giới hạn thời gian
status                    PENDING / CONSUMED / EXPIRED
```

State cần gắn với một transaction duy nhất. Khi callback tới, server tra state đã nhận để tìm transaction và xác minh browser/session binding, expected issuer, redirect URI, intent và thời hạn. Không lấy `user_id`, tenant, role hoặc return URL từ state chưa được kiểm tra rồi tin trực tiếp.

### 4.4. TTL và one-time use

- Transaction phải có thời hạn ngắn phù hợp với thời gian đăng nhập và trải nghiệm người dùng.
- State đã tiêu thụ, hết hạn hoặc bị hủy phải bị từ chối.
- Việc tìm transaction và đánh dấu tiêu thụ cần nguyên tử để hai callback đồng thời không cùng thành công.
- Không tái sử dụng state cho nhiều tab, nhiều lần thử hoặc nhiều IdP.
- Giới hạn số transaction đang chờ để tránh lạm dụng tài nguyên.

State không nhất thiết phải giữ bí mật sau khi đã gửi tới AS, nhưng nó phải khó đoán trước và chỉ có thể được chấp nhận trong đúng ngữ cảnh transaction. Opaque state cũng không nên được xem như bearer capability có quyền truy cập độc lập.

## 5. State khác gì nonce và PKCE?

Ba cơ chế này thường xuất hiện cùng nhau nhưng bảo vệ những mối đe dọa khác nhau:

| Cơ chế | Được tạo bởi | Được gửi ở đâu? | Được kiểm tra ở đâu? | Mục đích chính |
| --- | --- | --- | --- | --- |
| **state** | OAuth/OIDC client | Authorization request và được trả lại trong authorization response | Client callback | Tương quan response với request; chống CSRF/login response injection |
| **nonce** | OIDC client | Authentication request; được phản ánh trong ID token | Client kiểm tra ID token | Ràng buộc ID token với authentication request; giảm replay/token injection |
| **code_verifier / code_challenge** | OAuth client | Challenge ở authorization request; verifier ở token request | Authorization server tại token endpoint | Ràng buộc authorization code với client instance đã khởi tạo |

### 5.1. State không thay thế nonce

State được trả về ở authorization response để client xác định transaction. Nonce nằm trong ID token và được client kiểm tra sau khi xác minh token. Hai giá trị đi qua các phần khác nhau của giao thức và có mục đích riêng.

Trong OIDC, nếu client gửi nonce thì phải kiểm tra nonce trong ID token khớp đúng transaction. Không lấy state làm nonce hoặc dùng một giá trị thay cho cả hai chỉ để giảm số biến.

### 5.2. State không thay thế PKCE

State giúp kiểm tra callback có thuộc transaction đang chờ. PKCE bảo vệ authorization code khỏi bị đổi bởi bên không có verifier. Một callback có state hợp lệ nhưng code bị chặn/thay thế vẫn cần PKCE để ngăn code interception.

### 5.3. Có thể PKCE giúp chống CSRF không?

PKCE có thể cung cấp bảo vệ CSRF trong một số triển khai khi client ràng buộc code với verifier bí mật và transaction được quản lý đúng. Tuy nhiên, ứng dụng vẫn cần correlation/transaction handling rõ ràng; state tiếp tục hữu ích để xác định callback, xử lý lỗi, liên kết return path và phân biệt các giao dịch đồng thời. Hãy theo best practice và profile giao thức đang dùng thay vì bỏ kiểm soát mà chưa đánh giá.

## 6. Kiểm tra state tại callback

Khi browser quay lại callback, client phải xác minh state trước khi chấp nhận response:

1. Kiểm tra callback được gửi tới endpoint đã cấu hình.
2. Đọc state theo đúng kiểu dữ liệu/encoding; từ chối nếu thiếu hoặc malformed khi transaction yêu cầu state.
3. Tra transaction đang chờ bằng state đã nhận.
4. Xác minh transaction còn hạn, chưa tiêu thụ và gắn với đúng browser/session.
5. Xác minh transaction có intent và issuer phù hợp với callback.
6. Tiêu thụ transaction nguyên tử để callback không thể phát lại.
7. Nếu response có authorization code, đổi code bằng PKCE verifier và redirect URI đã lưu.
8. Với OIDC, xác minh ID token đầy đủ và nonce nếu đã gửi.
9. Ánh xạ issuer/subject đã xác minh sang principal theo policy; tạo phiên mới sau khi mọi kiểm tra đạt.
10. Chỉ redirect tới return path nội bộ đã lưu và kiểm tra trước đó.

Nếu AS trả lỗi như `access_denied`, `login_required` hoặc `interaction_required`, callback vẫn cần được tương quan với transaction thông qua state. Client xử lý lỗi rồi đóng transaction; không bỏ qua state chỉ vì response không có code.

### Không chấp nhận state do client tự khai báo lại

Không cho frontend gửi một giá trị `expectedState` tùy ý trong callback request rồi server so sánh với chính giá trị đó. Giá trị kỳ vọng phải đến từ transaction đã lưu trước khi redirect và được ràng buộc với browser/session. Tương tự, không tin state đã giải mã nếu nó không có integrity protection và transaction validation.

## 7. State trong các kiến trúc client

### 7.1. Backend/BFF

Với backend-for-frontend, server tạo state, lưu transaction trong session store/database/cache có bảo vệ và gắn với browser session. Callback về backend; server tra state, kiểm tra session binding, đổi code và giữ token phía server. Browser chỉ nhận cookie phiên phù hợp.

Ưu điểm là state và PKCE verifier có thể được giữ phía server, giảm khả năng script browser đọc trực tiếp. Tuy nhiên, cookie phiên tự động gửi nên callback và các endpoint thay đổi trạng thái vẫn cần cookie policy/CSRF protection phù hợp.

### 7.2. SPA

SPA có thể giữ transaction state trong memory hoặc sessionStorage theo thiết kế, nhưng dữ liệu ở browser chịu rủi ro XSS. State không phải credential dài hạn; tuy vậy, transaction cần được bảo vệ khỏi script độc hại và chỉ tồn tại trong thời gian ngắn. Với SPA, cân nhắc BFF để giữ token và transaction nhạy cảm phía server.

Nếu SPA giữ state trong browser:

- Dùng CSPRNG và transaction riêng cho mỗi lần authorize.
- Ràng buộc với tab/browser context theo kiến trúc.
- Xóa transaction sau khi xử lý callback hoặc hết hạn.
- Không nhúng PII, token hoặc return URL tùy ý vào state.
- Dùng PKCE S256 và xác minh state đúng giá trị đã lưu.

### 7.3. Mobile và desktop

Ứng dụng native thường dùng system browser/external user-agent và redirect URI phù hợp nền tảng (app-claimed HTTPS hoặc loopback theo profile). State cần gắn với giao dịch khởi tạo trong ứng dụng và kiểm tra khi nhận app link/custom URI callback. Không chấp nhận callback từ ứng dụng khác hoặc transaction không được khởi tạo.

PKCE đặc biệt quan trọng vì authorization code đi qua front-channel và có thể bị một ứng dụng khác cố chặn. Client phải bảo vệ verifier trong phạm vi vòng đời giao dịch.

## 8. Nhiều tab, nhiều giao dịch và response mode

Một người dùng có thể mở hai tab và bắt đầu hai lần đăng nhập gần nhau. Mỗi lần phải có state và transaction riêng. Nếu server chỉ lưu một biến `current_state` rồi ghi đè ở lần thứ hai, callback của tab đầu có thể bị từ chối hoặc tệ hơn bị gắn nhầm transaction.

Thiết kế phù hợp:

- Lưu nhiều transaction pending với TTL và giới hạn số lượng.
- Mỗi state ánh xạ tới đúng transaction ID, browser binding, issuer và intent.
- Callback chỉ tiêu thụ transaction khớp state; không lấy transaction “mới nhất”.
- Dùng thao tác consume nguyên tử và chống callback lặp.
- Khi người dùng hủy/đóng tab, transaction hết hạn tự nhiên hoặc được hủy có kiểm soát.

### Query và form_post

Authorization response có thể được trả qua query mode hoặc `form_post` tùy response mode/profile. Với query mode, state xuất hiện trong URL callback; cần tránh log query string nhạy cảm và áp dụng Referrer-Policy phù hợp. Với `form_post`, browser gửi form POST cross-site; cookie SameSite và browser behavior có thể ảnh hưởng khả năng tìm browser session binding. Hãy kiểm thử luồng thật trên trình duyệt mục tiêu và chọn cookie/transaction strategy tương thích mà vẫn giữ kiểm soát CSRF.

Không đổi cookie sang `SameSite=None` một cách rộng rãi chỉ để “làm callback chạy”. Cần xác định đúng response mode, ranh giới site và cơ chế ràng buộc transaction.

## 9. State và issuer mix-up

Ứng dụng có thể hỗ trợ nhiều authorization server/IdP. Nếu client không gắn transaction với đúng issuer, kẻ tấn công có thể cố làm phản hồi từ AS này được xử lý như phản hồi của AS khác. State tự nó không xác minh issuer; nó chỉ giúp tìm transaction.

Trong transaction, lưu:

- Provider/connection ID đã chọn từ cấu hình tin cậy.
- Expected issuer và authorization/token endpoint tương ứng.
- Client ID và redirect URI đã đăng ký.
- PKCE verifier, nonce và state.

Khi callback:

- Chỉ đổi code tại token endpoint của AS đã lưu trong transaction.
- Xác minh issuer trong ID token theo cấu hình tin cậy.
- Dùng issuer identification/response parameter nếu profile hỗ trợ và xác minh đúng.
- Nếu có nhiều AS, cân nhắc redirect URI riêng theo issuer hoặc biện pháp chống mix-up được đặc tả.
- Không lấy issuer hoặc token endpoint từ callback/query string không tin cậy.

State không thay thế xác minh issuer, audience hoặc chữ ký token.

## 10. Open redirect và return path

Ứng dụng thường muốn đưa người dùng trở lại trang họ đang xem sau khi đăng nhập. Nếu lưu một URL tùy ý trong state hoặc transaction mà không kiểm tra, attacker có thể biến callback thành open redirect tới domain giả mạo.

Quy tắc:

- Chỉ lưu đường dẫn nội bộ đã chuẩn hóa, ví dụ `/settings/profile`.
- Từ chối URL tuyệt đối, scheme lạ, protocol-relative URL như `//attacker.test`, ký tự điều khiển và các dạng encoding gây diễn giải khác nhau.
- Nếu cần redirect tới host khác, dùng allowlist cố định và quy trình riêng.
- Không decode/normalize ở nhiều tầng theo cách làm thay đổi ý nghĩa sau khi kiểm tra.
- Không để state trở thành container của return URL chưa kiểm tra.

State opaque chỉ nên trỏ tới transaction phía server; return path đã được kiểm tra được lưu trong transaction đó.

## 11. Pseudocode: tạo và xử lý state

Ví dụ dưới đây mô tả backend/BFF. Các hàm là khái niệm; triển khai thực cần dùng thư viện OAuth/OIDC được duy trì.

### 11.1. Bắt đầu authorization

```ts
async function startLogin(request) {
  const provider = trustedProviderFor(request.tenantContext);
  const state = base64url(secureRandomBytes(32));
  const codeVerifier = securePkceVerifier();
  const nonce = base64url(secureRandomBytes(32));

  const transaction = {
    stateDigest: sha256(state),
    browserBinding: request.session.binding,
    providerId: provider.id,
    expectedIssuer: provider.issuer,
    clientId: provider.clientId,
    redirectUri: provider.registeredRedirectUri,
    codeVerifier,
    nonce,
    intent: "LOGIN",
    returnPath: validateLocalPath(request.query.returnTo) ?? "/",
    createdAt: now(),
    expiresAt: nowPlusShortTTL()
  };

  await pendingTransactions.create(transaction);

  return redirect(provider.authorizationEndpoint, {
    response_type: "code",
    client_id: transaction.clientId,
    redirect_uri: transaction.redirectUri,
    scope: "openid profile",
    state,
    nonce,
    code_challenge: pkceS256(codeVerifier),
    code_challenge_method: "S256"
  });
}
```

Trong ví dụ, state thô chỉ được gửi tới AS và digest được lưu phía server; có thể dùng một cách lưu khác nếu kho transaction bảo vệ tốt. Nonce và PKCE verifier là giá trị riêng, có vai trò riêng. Transaction cần được tạo trước khi redirect và gắn với đúng browser session.

### 11.2. Xử lý callback

```ts
async function completeLogin(request) {
  const returnedState = parseSingleStateParameter(request);
  if (!returnedState) return rejectCallback();

  const digest = sha256(returnedState);
  const tx = await pendingTransactions.findByDigest(digest);
  if (!tx) return rejectCallback();

  if (tx.expiresAt <= now() ||
      tx.status !== "PENDING" ||
      tx.browserBinding !== request.session.binding) {
    return rejectCallback();
  }

  const provider = trustedProviderById(tx.providerId);
  if (!provider || provider.issuer !== tx.expectedIssuer) {
    return rejectCallback();
  }

  // Atomic compare-and-consume prevents two callbacks from succeeding.
  const consumed = await pendingTransactions.consumeOnce(tx.id);
  if (!consumed) return rejectCallback();

  if (request.query.error) {
    return handleAuthorizationError(request.query.error);
  }

  const tokens = await oidcClient.exchangeCode({
    provider,
    code: request.query.code,
    redirectUri: tx.redirectUri,
    codeVerifier: tx.codeVerifier
  });

  const identity = await verifyIdToken(tokens.idToken, {
    issuer: tx.expectedIssuer,
    audience: tx.clientId,
    nonce: tx.nonce
  });
  if (!identity) return rejectCallback();

  await rotateAndEstablishSession(identity);
  return redirect(tx.returnPath);
}
```

Đây là pseudocode rút gọn. Trong triển khai thật, phải xử lý cả error response theo đúng giao thức, xác minh response issuer/mix-up, client authentication khi confidential, token signature/algorithm, audience, `azp` khi áp dụng, `exp`, `iat`, nonce và mapping danh tính. Cần bảo đảm việc consume transaction và xử lý callback có tính nhất quán; nếu tiêu thụ state trước rồi lỗi tạm thời ở token endpoint, cần một chính sách retry an toàn thay vì cho phép replay tùy ý.

Không redirect tới `returnPath` lấy trực tiếp từ callback. Đường dẫn phải là giá trị nội bộ đã lưu và xác minh khi bắt đầu login.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| State cố định hoặc dễ đoán | Attacker có thể tạo callback khớp | CSPRNG, entropy cao, giá trị mới mỗi transaction |
| Không kiểm tra state ở callback | Login CSRF/response injection | So khớp với transaction đang chờ và browser binding |
| Chỉ kiểm tra state có tồn tại | State của attacker có thể được chấp nhận trong ngữ cảnh sai | Tra transaction server-side, kiểm tra session, issuer, intent, TTL |
| Dùng một state cho nhiều tab | Callback có thể bị nhầm hoặc ghi đè | Mỗi transaction một state, lưu nhiều pending transaction |
| State chứa URL tùy ý | Open redirect | Lưu return path nội bộ đã chuẩn hóa phía server |
| State dùng thay nonce | ID token không được ràng buộc đúng request | Dùng nonce riêng và xác minh trong ID token |
| State dùng thay PKCE | Code interception vẫn có thể xảy ra | Dùng PKCE S256 và verifier riêng |
| Không tiêu thụ state một lần | Callback replay có thể tạo nhiều phiên | Atomic one-time consume và TTL |
| Tin issuer từ callback | Authorization server mix-up | Lưu expected issuer trong transaction và xác minh token |
| Log toàn bộ callback URL | Code/state có thể rò qua log | Redact query, hạn chế log và Referrer-Policy |
| Dùng transaction toàn cục thay vì browser binding | Callback có thể bị ghép sang browser khác | Ràng buộc state với session/tab context phù hợp |
| Cookie SameSite không phù hợp response mode | Callback hợp lệ không tìm được transaction hoặc developer nới cookie quá rộng | Thiết kế theo response mode và kiểm thử browser |

## 13. Tình huống thực tế: hai tab đăng nhập SSO

Một người dùng mở hai tab của ứng dụng quản lý nhân sự:

- Tab A bắt đầu đăng nhập bằng IdP công ty.
- Tab B bắt đầu đăng nhập bằng IdP đối tác để liên kết thêm danh tính.

Nếu ứng dụng chỉ lưu một `state` toàn cục trong session, lần bắt đầu ở tab B có thể ghi đè state của tab A. Khi callback A về, ứng dụng từ chối nhầm hoặc dùng transaction B. Nếu callback không được kiểm tra chặt, việc tráo intent LOGIN/LINK có thể dẫn tới gắn nhầm danh tính vào tài khoản.

### Thiết kế an toàn

1. Mỗi thao tác tạo state, nonce và PKCE verifier riêng.
2. Transaction lưu intent rõ ràng: `LOGIN` hay `LINK`; không đổi intent từ callback.
3. Transaction gắn với browser session và provider/issuer đã chọn.
4. Callback A chỉ tìm transaction A; callback B chỉ tìm transaction B.
5. Với intent LINK, xác minh lại tài khoản nội bộ đang đăng nhập và yêu cầu bằng chứng phù hợp trước khi gắn external identity.
6. Mỗi transaction chỉ được consume một lần; callback đến muộn hoặc lặp bị từ chối.
7. Sau login/link, audit event ghi principal, provider và kết quả mà không lưu token/state thô.

## 14. Kiểm thử và tiêu chí chấp nhận

| Tình huống | Kết quả mong đợi |
| --- | --- |
| State ngẫu nhiên hợp lệ được trả về trong callback của đúng browser | Transaction khớp và luồng tiếp tục |
| Callback thiếu state | Từ chối, không tạo phiên |
| State sai hoặc không tồn tại | Từ chối, không tạo phiên |
| State hết hạn | Từ chối và đánh dấu transaction expired |
| State đã được consume | Callback replay bị từ chối |
| State thuộc browser/session khác | Từ chối, không ghép callback vào phiên hiện tại |
| Hai tab có hai state khác nhau | Mỗi callback xử lý đúng transaction tương ứng |
| State của LOGIN được dùng cho callback LINK | Từ chối do intent không khớp |
| Authorization error response có state đúng | Tương quan đúng transaction rồi xử lý lỗi; không tạo phiên |
| Authorization error response thiếu/sai state | Từ chối callback |
| Return path là URL ngoài hoặc protocol-relative | Không redirect ra ngoài; dùng đường dẫn an toàn |
| Code bị tráo nhưng state đúng | PKCE verifier không khớp, token endpoint từ chối |
| ID token có nonce sai | OIDC client từ chối |
| Response đến từ issuer khác transaction | Từ chối do issuer/AS mismatch |
| Callback URL bị log | State/code được redact hoặc log policy loại query nhạy cảm |
| Callback trùng đến đồng thời trên hai node | Atomic consume bảo đảm tối đa một callback thành công |
| Cookie SameSite ảnh hưởng form_post | Transaction binding vẫn hoạt động theo thiết kế đã kiểm thử; không nới policy tùy tiện |

### Kiểm thử bảo mật cần bao phủ

- Login CSRF bằng callback do attacker khởi tạo.
- Authorization response injection bằng code/state từ transaction khác.
- Replay callback sau khi đã tạo phiên.
- Nhiều tab và nhiều IdP đồng thời.
- State sai encoding, duplicate parameter hoặc nhiều tham số state.
- Open redirect qua return path.
- Issuer mix-up và callback lỗi.
- Race condition khi consume state trên hệ thống nhiều instance.

## 15. Bài tập tự kiểm tra

Một ứng dụng doanh nghiệp hỗ trợ đăng nhập OIDC từ hai IdP và liên kết thêm tài khoản đối tác. Ứng dụng dùng Authorization Code + PKCE, có BFF và cookie phiên HttpOnly. Người dùng có thể mở nhiều tab.

Hãy:

1. Mô tả state được tạo, lưu và gửi như thế nào khi bắt đầu LOGIN.
2. Giải thích state, nonce và PKCE bảo vệ những phần nào khác nhau.
3. Thiết kế transaction record có browser binding, expected issuer, intent, return path và TTL.
4. Mô tả cách xử lý callback thành công, callback lỗi, callback replay và callback từ browser khác.
5. Giải thích cách hỗ trợ hai tab và hai IdP mà không ghi đè state.
6. Nêu cách chống open redirect và issuer mix-up.
7. Viết ít nhất năm test case chứng minh callback của attacker không thể tạo phiên hoặc link identity cho nạn nhân.

**Gợi ý đánh giá:** câu trả lời tốt phải xem state là correlation handle gắn với transaction server-side, không coi nó là token xác thực. Phải có CSPRNG, TTL, browser binding, one-time consume, issuer/intent validation và phân biệt rõ state với nonce/PKCE.

---

**Ghi nhớ:** `state` ràng buộc authorization response với giao dịch OAuth/OIDC mà client đã khởi tạo. Hãy tạo state ngẫu nhiên bằng CSPRNG, gắn với browser/session và expected issuer, đặt TTL, kiểm tra chính xác ở callback và consume một lần. State hỗ trợ chống CSRF và callback injection; nó **không thay thế PKCE, nonce, redirect URI validation, xác minh token hoặc authorization**.
