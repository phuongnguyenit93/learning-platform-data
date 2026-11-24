# State parameter

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **state parameter** là gì, nó đi qua **authorization request** và **authorization response** ở đâu trong OAuth 2.0/OIDC.
- Mô tả cách state liên kết callback với **giao dịch và phiên client đã khởi tạo**, giúp giảm **login CSRF, authorization response injection và nhầm luồng đăng nhập**.
- Sinh state bằng **CSPRNG**, lưu giao dịch chờ có hạn, đối chiếu đúng phiên và **consume một lần**.
- Phân biệt **state**, **PKCE code_verifier/code_challenge**, **OIDC nonce**, **issuer (iss)** và cookie phiên.
- Xử lý state đúng trong **web backend/BFF, SPA, nhiều tab, nhiều Authorization Server**, callback thành công và callback lỗi.
- Nhận biết các lỗi như state đoán được, thiếu state validation, state global, reuse, callback từ phiên khác, open redirect và logging dữ liệu nhạy cảm.
- Thiết kế mã giả, Java/JavaScript và bộ **negative tests** để kiểm chứng một luồng OAuth an toàn.

## 1. State parameter là gì?

OAuth 2.0 định nghĩa tham số **state** để client có thể mang một giá trị qua luồng authorization bằng trình duyệt. Client gửi state đến **authorization endpoint** của Authorization Server (AS). Nếu request có state, AS trả lại **chính giá trị đó** trong authorization response theo quy tắc giao thức.

Ví dụ request Authorization Code + PKCE, với các giá trị minh họa:

~~~http
GET /oauth2/authorize?response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread&state=EXAMPLE_RANDOM_STATE&code_challenge=EXAMPLE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Khi xử lý ủy quyền xong, AS có thể chuyển trình duyệt về callback:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/callback?code=EXAMPLE_AUTH_CODE&state=EXAMPLE_RANDOM_STATE
~~~

Client không chấp nhận callback chỉ vì **code** có mặt. Nó phải kiểm **state trả về** có khớp một giao dịch **đã được chính client tạo trước đó cho đúng phiên** hay không.

**State không phải access token, refresh token, ID token, scope, role hay client secret.** Nó là một giá trị correlation trong luồng OAuth. State có thể dùng để giữ ngữ cảnh ứng dụng, nhưng trong mô hình an toàn nên là một tham chiếu ngẫu nhiên **opaque**, trỏ tới transaction context đã lưu.

### Tiêu chuẩn nói gì về state?

RFC 6749 khuyến nghị (**RECOMMENDED**) state trong authorization request, yêu cầu AS trả state nếu client đã gửi, và nêu cách dùng nó để bảo vệ CSRF ở redirect URI.

RFC 9700 (OAuth 2.0 Security Best Current Practice) đặt yêu cầu **client phải có cơ chế CSRF protection** cho redirect URI. Nếu client đã bảo đảm AS hỗ trợ PKCE, tiêu chuẩn cho phép dựa vào sự bảo vệ CSRF do PKCE mang lại trong những điều kiện phù hợp; với OIDC, nonce cũng có vai trò bảo vệ theo profile.

Điều này **không làm state hết giá trị**: state giúp client correlation rõ ràng **trước khi token exchange**, liên kết đúng verifier/issuer/phiên, quản lý nhiều giao dịch song song và xử lý callback lỗi. Bài học sử dụng mẫu thực hành dễ kiểm tra: **Authorization Code + PKCE + state ngẫu nhiên một lần gắn phiên**.

## 2. State bảo vệ ranh giới tin cậy nào?

Trong luồng Authorization Code, client khởi tạo request, chuyển browser đến AS rồi nhận authorization response qua redirect. Browser là môi trường mà người dùng và những nguồn bên ngoài có thể điều hướng; vì thế **callback của client là một trust boundary**.

~~~text
Client tạo giao dịch và random state
    -> Browser được chuyển tới Authorization Server
    -> AS xử lý authentication / authorization
    -> Browser trở về client: code + state
    -> Client xác minh callback thuộc đúng giao dịch đã mở
    -> Client mới tiếp tục đổi code và xác minh token
~~~

Một URL callback có thể được mở trực tiếp, dán từ nơi khác hoặc bị kẻ tấn công cố tình gửi tới browser. Không phải request nào vào đường dẫn **/callback** cũng thuộc một authorization flow hợp lệ.

State giúp phân biệt:

- **Callback mong đợi**: state có trong pending transactions của **phiên này**, còn hạn và chưa dùng.
- **Callback không có giao dịch**: state không có hoặc không tồn tại trong pending transactions.
- **Callback của phiên khác**: state thuộc giao dịch của người khác, không thuộc browser session hiện tại.
- **Callback phát lại**: state đã được consume trước đó.
- **Callback chéo luồng**: state thuộc AS, client, verifier hoặc login intent khác với dữ liệu đang được sử dụng.

**Giới hạn quan trọng:** state là bằng chứng correlation ở phía client, không thay xác minh chữ ký/token tại Resource Server, không trực tiếp cấm một bên có code gọi token endpoint, và không tự giải quyết mọi vấn đề mix-up giữa nhiều AS.

## 3. Một tình huống login CSRF

Giả sử Dashboard cho người dùng đăng nhập qua một OpenID Provider.

1. Kẻ tấn công bắt đầu authorization flow cho tài khoản **attacker-account** do mình sở hữu.
2. AS phát authorization code cho giao dịch của kẻ tấn công.
3. Kẻ tấn công dụ browser nạn nhân mở URL callback có code đó.
4. Dashboard **không kiểm state**, đổi code rồi tạo phiên ứng dụng.
5. Nạn nhân có thể thấy giao diện như thể đã đăng nhập, nhưng phiên gắn với **tài khoản của kẻ tấn công**.

Đây là một kiểu **login CSRF/session swapping**. Ví dụ người dùng có thể vô tình nhập dữ liệu vào tài khoản do attacker sở hữu.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant A as Attacker
    participant V as Browser nạn nhân
    participant C as OAuth Client
    participant AS as Authorization Server

    A->>AS: Bắt đầu login với attacker-account
    AS-->>A: Authorization code cho giao dịch A
    A->>V: Điều hướng tới callback chứa code A
    V->>C: Callback code A và state A
    C->>C: Tìm state A trong pending store của phiên nạn nhân
    C-->>V: Từ chối vì không có transaction tương ứng
    Note over C: Không đổi code A; không tạo phiên attacker-account
~~~

Khi client có state đúng và ràng buộc với **phiên đã khởi tạo**, callback với code/state của phiên khác không thể được coi là giao dịch của nạn nhân.

### Tại sao chỉ kiểm state khác rỗng chưa đủ?

Kiểm như dưới đây không có tác dụng chống CSRF thực chất:

~~~text
if callback.state != null:
    acceptCallback()
~~~

State không phải một dấu hiệu được AS “chứng nhận đúng phiên”; AS chỉ **echo** nó. Client phải có pending record được tạo **trước khi redirect**, trong **đúng ngữ cảnh browser/session**, rồi kiểm giá trị đầy đủ.

## 4. Vòng đời của state

Một triển khai an toàn có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Created: Client tạo state CSPRNG
    Created --> Pending: Lưu transaction và session binding
    Pending --> Matched: Callback đúng state còn hạn
    Pending --> Rejected: State thiếu, sai, hết hạn
    Matched --> Consumed: Consume một lần
    Consumed --> Continued: Kiểm issuer và xử lý code/error
    Continued --> [*]
    Rejected --> [*]
~~~

Có sáu thao tác chính.

**1. Generate.** Tạo giá trị ngẫu nhiên mật mã **mới cho từng authorization request**.

**2. Store.** Lưu state trong một transaction record có **browser/session binding**, TTL, issuer được chọn và dữ liệu cho flow.

**3. Send.** Gửi state qua authorization request. AS không cần biết semantics của record phía client.

**4. Validate.** Khi callback đến, tìm đúng transaction của phiên hiện tại; kiểm state, thời hạn, issuer và context.

**5. Consume.** Đánh dấu đã sử dụng/xóa transaction bằng thao tác nguyên tử để callback lặp không được chấp nhận.

**6. Cleanup.** Xóa giao dịch bị bỏ dở hoặc hết hạn; giới hạn số pending state để tránh memory exhaustion.

Một record minh họa:

~~~text
PendingAuthorization:
    state                 random opaque value
    browserSessionId      session của người khởi tạo
    issuer                trusted AS đã chọn
    clientId              client đã đăng ký
    redirectUri           callback URI đã đăng ký
    codeVerifier          PKCE verifier riêng của giao dịch
    oidcNonce             nonce OIDC nếu flow dùng
    returnPath            đường dẫn nội bộ đã kiểm
    createdAt             thời điểm tạo
    expiresAt             hạn ngắn
    consumed              false
~~~

Đây chỉ là mô hình nội bộ. OAuth 2.0 không yêu cầu mọi client lưu đúng các field này. Ý nghĩa cốt lõi là **state trỏ đến đúng một giao dịch đã có và không được tái sử dụng**.

## 5. Sinh state khó đoán

State bảo vệ CSRF phải có đủ entropy. Một lựa chọn thực hành phổ biến là **128–256 bit ngẫu nhiên mật mã**, mã hóa thành Base64URL. Đây là hướng dẫn kỹ thuật, **không phải một con số cố định được RFC 6749 bắt buộc**.

Không dùng các giá trị dễ đoán hoặc lặp:

~~~text
state = "login"
state = "12345"
state = userId
state = currentUnixTimestamp
state = hash(email)
state = Math.random().toString()
state = hardcodedConstant
~~~

Hash của dữ liệu dễ đoán vẫn có thể đoán được. Timestamp và userId cũng có thể lộ dữ liệu hoặc giúp attacker tạo giá trị trùng.

### Java: SecureRandom

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class StateGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String createState() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    private StateGenerator() {}
}
~~~

32 bytes là 256 bit; biểu diễn Base64URL không padding có **43 ký tự**. Không dùng state này như client secret hoặc token API; nó vẫn phải được lưu và kiểm cùng transaction.

### JavaScript: Web Crypto

~~~javascript
function generateState() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);

  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

const state = generateState();
~~~

Ví dụ sử dụng API browser và cần môi trường hỗ trợ Web Crypto. **Không dùng Math.random** cho state. Đối với SPA thật, cần sinh **code_verifier** riêng có entropy và định dạng theo PKCE, chứ không lấy state thay verifier.

## 6. State phải được lưu ở ngữ cảnh nào?

Giá trị state gửi trong URL có thể nhìn thấy trên đường redirect, nên nó không được thiết kế như một secret giữ kín vĩnh viễn. Bảo vệ CSRF phụ thuộc vào **state không đoán được, transaction tồn tại trước callback và có liên kết đúng phiên**.

### 6.1 BFF hoặc web backend

Một web backend có thể dùng session cookie để xác định browser, và lưu map transactions ở server-side:

~~~text
Browser:
    Cookie __Host-session=opaque-id; Secure; HttpOnly; SameSite=Lax

Backend session store:
    session-id:
        pendingStateA -> issuer A, verifier A, TTL A
        pendingStateB -> issuer B, verifier B, TTL B
~~~

Cookie ở đây là **cookie phiên ứng dụng**, không phải refresh token OAuth. Backend giữ thông tin pending riêng cho từng browser session. Callback có state thuộc **session khác** phải bị từ chối.

**Secure, HttpOnly, SameSite** có các vai trò bổ sung nhưng không tự thay thế state. Cần chống **session fixation**, hạn cookie đúng host/path, bảo vệ store và kiểm policy trước khi tạo authenticated session.

Nếu backend chạy nhiều instance, state store cần shared session storage hoặc routing nhất quán, đồng thời thao tác **consume one-time** không được thành công ở hai node cùng lúc.

### 6.2 SPA thuần trình duyệt

SPA không có backend có thể giữ pending transaction trong **sessionStorage** của tab hoặc một store tạm tương đương. Callback phải tìm đúng transaction đã được tạo trước redirect.

~~~javascript
const state = generateState();

const pending = {
  issuer: "https://identity.example.test",
  codeVerifier: "EXAMPLE_PKCE_VERIFIER",
  createdAtMs: Date.now()
};

sessionStorage.setItem(
  "oauth_tx:" + state,
  JSON.stringify(pending)
);

// Khi browser quay về callback:
const params = new URLSearchParams(window.location.search);
const returnedState = params.get("state");
const key = returnedState && "oauth_tx:" + returnedState;
const saved = key ? sessionStorage.getItem(key) : null;

if (!saved) {
  throw new Error("No matching authorization transaction");
}
sessionStorage.removeItem(key);
// Sau đó phải kiểm TTL/issuer và xử lý code hoặc error.
~~~

**Đây là ví dụ correlation tối giản, không phải một OAuth client hoàn chỉnh.** Code thực phải sinh PKCE verifier đúng chuẩn, xử lý tham số trùng, kiểm issuer, TTL, token response và mọi lỗi.

**sessionStorage không phải secret vault chống XSS**. Script độc hại chạy cùng origin có thể đọc storage và sử dụng logic của SPA. Lưu context theo tab có ích cho correlation nhưng có thể làm callback tới tab mới không tìm thấy state; cần thiết kế UI/redirect phù hợp.

### 6.3 Chỉ dùng store toàn cục theo state có ổn không?

Một map dùng chung **state → pending** cho toàn bộ người dùng, rồi cho bất kỳ browser nào có state thực hiện callback, có thể **không bảo đảm ràng buộc phiên**. Bên nhận phải chứng minh state **thuộc context đã khởi tạo**, không chỉ “được tìm thấy đâu đó trong hệ thống”.

## 7. Callback cần kiểm những gì?

| Điều kiện | Vì sao quan trọng | Hành vi khi sai |
| --- | --- | --- |
| **Có state** nếu authorization request đã gửi state | Không chấp nhận response thiếu correlation. | Từ chối. |
| **State đầy đủ khớp pending transaction** | Chống phản hồi giả/misrouting. | Từ chối. |
| **Transaction thuộc browser session hiện tại** | Chống login CSRF/session swapping. | Từ chối. |
| **Chưa hết TTL** | Không giữ state có hiệu lực vô hạn. | Từ chối và cleanup. |
| **Chưa consume lần nào** | Chống lặp/replay callback. | Từ chối. |
| **Đúng issuer/client/redirect URI theo transaction** | Không đổi code tại AS hoặc client sai. | Từ chối. |
| **PKCE verifier thuộc cùng transaction** | Code được AS gắn với challenge của flow. | Không đổi code với verifier tùy ý. |
| **Response parse nghiêm ngặt** | Tránh state/code bị đọc khác nhau do tham số lặp. | Từ chối response không hợp lệ. |

Ví dụ so khớp sai:

~~~text
Sai:
    returnedState != null
    returnedState.startsWith("oauth-")
    returnedState.substring(0, 5) == expected.substring(0, 5)

Đúng:
    returnedState == pendingTransaction.state
    AND pendingTransaction.belongsTo(currentBrowserSession)
    AND pendingTransaction.isNotExpired()
    AND pendingTransaction.isUnused()
~~~

Client phải kiểm **giá trị nguyên vẹn**, không chỉ prefix hoặc số ký tự. Nếu đối chiếu secret trực tiếp, có thể dùng hàm so sánh thích hợp để tránh rò rỉ qua timing, nhưng **binding và one-time** quan trọng hơn một phép so sánh chuỗi riêng lẻ.

### Kiểm state trước token exchange

Không làm theo thứ tự:

~~~text
Nhận code
    -> gửi /token để đổi code
    -> tạo session đăng nhập
    -> sau đó mới so sánh state
~~~

Vì token đã được đổi hoặc phiên đã thay đổi trước khi biết callback thuộc flow chính xác.

Thứ tự hợp lý:

~~~text
1. Parse callback và xác định browser session.
2. Lấy pending transaction tương ứng state.
3. Kiểm state, TTL, one-time, issuer và context cần thiết.
4. Nếu response là lỗi, xử lý lỗi theo transaction và dừng.
5. Nếu có code, dùng verifier của transaction đổi code ở token endpoint tin cậy.
6. Xác minh token/OIDC response và chỉ khi đạt mới hoàn tất phiên.
~~~

## 8. Mã giả: một pending transaction cho mỗi state

~~~text
function beginAuthorization(session, chosenIssuer, returnPath):
    require chosenIssuer in configuredTrustedIssuers
    require returnPath is validatedInternalPath

    state = randomBase64UrlCSPRNG(32 bytes)
    verifier = generatePkceVerifier()
    nonce = generateOidcNonceIfNeeded()

    session.pendingOAuth[state] = {
        issuer: chosenIssuer,
        verifier: verifier,
        nonce: nonce,
        redirectUri: registeredRedirectUri(chosenIssuer),
        returnPath: returnPath,
        expiresAt: serverNow() + SHORT_TTL
    }

    return buildAuthorizationUrl(
        trustedAuthorizationEndpoint(chosenIssuer),
        state,
        pkceS256Challenge(verifier),
        nonce
    )

function handleCallback(session, response):
    state = strictParseExactlyOneState(response)
    if state is missing:
        reject("missing_state")

    transaction = session.pendingOAuth.removeAtomically(state)
    if transaction is missing:
        reject("unknown_or_reused_state")
    if serverNow() >= transaction.expiresAt:
        reject("expired_state")

    verifyAuthorizationResponseIssuerIfRequired(
        response,
        transaction.issuer
    )

    if response.error is present:
        showSafeAuthorizationError(response.error)
        stop

    code = strictParseExactlyOneAuthorizationCode(response)
    if code is missing:
        reject("missing_code")

    tokenResult = exchangeCodeUsingTrustedConfiguration(
        issuer = transaction.issuer,
        redirectUri = transaction.redirectUri,
        code = code,
        codeVerifier = transaction.verifier
    )

    validateTokenAndOidcResponse(tokenResult, transaction)
    finishSessionWithValidatedIdentity(transaction.returnPath)
~~~

Những ranh giới được giữ:

- **chosenIssuer** từ danh sách tin cậy, không lấy token endpoint tự khai trong callback.
- **returnPath** nội bộ đã kiểm, không dùng state làm URL mở tùy ý.
- **pendingOAuth** thuộc riêng browser session và có TTL.
- **removeAtomically** bảo đảm một transaction không thể được dùng thành công đồng thời hai lần.
- **codeVerifier** lưu trước redirect, gắn đúng state; không dùng verifier do callback gửi tới.
- **ID token/access token** vẫn được kiểm theo profile sau token exchange.
- Không bao giờ coi code hoặc state tự thân là permission truy cập Orders API.

## 9. Ví dụ Java 17: lưu state theo session và consume một lần

Đoạn sau chỉ minh họa **lớp lưu transaction**, không thực hiện HTTP OAuth, không quản lý cookie và không xác minh ID token. **perSession** phải là map thuộc đúng một browser session; để hỗ trợ concurrent callback trên một node nên dùng ConcurrentHashMap hoặc store có thao tác tương đương.

~~~java
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class OAuthStateStore {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Duration TTL = Duration.ofMinutes(5);

    public record Pending(
            String issuer,
            String redirectUri,
            String codeVerifier,
            String oidcNonce,
            String allowedReturnPath,
            Instant createdAt
    ) {}

    public static String create(
            Map<String, Pending> perSession,
            Clock clock,
            String trustedIssuer,
            String registeredRedirectUri,
            String pkceVerifier,
            String nonce,
            String allowedReturnPath
    ) {
        Objects.requireNonNull(perSession);
        Objects.requireNonNull(clock);

        byte[] random = new byte[32];
        RNG.nextBytes(random);
        String state = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(random);

        perSession.put(state, new Pending(
                trustedIssuer,
                registeredRedirectUri,
                pkceVerifier,
                nonce,
                allowedReturnPath,
                clock.instant()));
        return state;
    }

    public static Optional<Pending> consume(
            Map<String, Pending> perSession,
            Clock clock,
            String receivedState
    ) {
        Objects.requireNonNull(perSession);
        Objects.requireNonNull(clock);

        if (receivedState == null || receivedState.length() != 43) {
            return Optional.empty();
        }

        // Với ConcurrentHashMap, remove key là thao tác atomic.
        Pending pending = perSession.remove(receivedState);
        if (pending == null) {
            return Optional.empty();
        }

        Instant expiresAt = pending.createdAt().plus(TTL);
        if (!clock.instant().isBefore(expiresAt)) {
            return Optional.empty();
        }
        return Optional.of(pending);
    }

    private OAuthStateStore() {}
}
~~~

### Giới hạn của ví dụ

- Map phải là **per-browser-session**. Một global map chung không có session binding **không đủ bảo vệ login CSRF**.
- Code không giới hạn số transaction đang chờ hoặc dọn các record không có callback. Bản production phải bổ sung TTL cleanup, giới hạn lưu trữ và rate limiting.
- Code không xử lý collision cực hiếm của random state trong cùng map; khi yêu cầu chặt, tạo mới nếu key đã tồn tại hoặc dùng putIfAbsent.
- Khi nhiều instance backend, một ConcurrentHashMap trên một node chưa đủ; cần shared store và **atomic consume** xuyên instance.
- Giá trị **43 ký tự** dựa vào 32 byte ngẫu nhiên. Nếu đổi cấu trúc state thì phải đồng bộ rule parse.
- **TTL 5 phút chỉ là ví dụ**, không phải giá trị mặc định của OAuth.
- Caller phải kiểm **trustedIssuer**, **redirectUri** và **returnPath** từ cấu hình/allowlist; code không chứng minh chúng đáng tin.
- Phần xử lý callback còn phải kiểm **iss**, PKCE, OIDC nonce, state trùng tham số và token validation.

## 10. State, PKCE, OIDC nonce và iss là những cơ chế khác nhau

| Cơ chế | Gửi đi trong bước nào? | Kiểm ở đâu? | Bảo vệ chính |
| --- | --- | --- | --- |
| **state** | Authorization request; AS echo trong response. | **Client ở callback**. | Correlation giao dịch, CSRF protection, chọn đúng pending context. |
| **code_challenge** | Authorization request. | AS ghi nhận và ràng buộc với code. | Ràng buộc code với verifier theo PKCE. |
| **code_verifier** | Client giữ trong transaction, gửi ở token request. | **AS tại token endpoint**. | Ngăn bên thiếu verifier đổi authorization code bị chặn. |
| **OIDC nonce** | Authorization request. | **Client kiểm nonce trong ID token** khi áp dụng. | Liên kết ID token với phiên, giảm replay/nhầm token. |
| **iss/issuer identification** | AS được xác minh theo profile/metadata. | Client/RS theo vị trí tin cậy. | Nhận diện đúng issuer, giảm AS mix-up. |
| **Cookie phiên** | Browser ↔ client/backend. | Backend/browser session layer. | Nhận diện phiên đang khởi tạo và hoàn tất login. |

### PKCE không phải state

PKCE cung cấp bằng chứng tại **token endpoint** rằng bên đổi code sở hữu verifier tương ứng với challenge trong authorization request. State hỗ trợ client xác định authorization response thuộc giao dịch nào **trước token exchange**. Hai cơ chế thường được triển khai cùng nhau.

Một code bị chặn không tự giải mã được verifier, và một state ngẫu nhiên không tự chứng minh bên đổi code có verifier. Chúng khác mục đích và vị trí kiểm tra.

### Nonce không phải state

Trong OIDC:

~~~text
Authorization request:
    state = random-state-A
    nonce = random-nonce-B

Authorization response:
    state = random-state-A

ID token:
    "nonce": "random-nonce-B"
~~~

Client đối chiếu **state ở callback**, sau đó xác minh **nonce trong ID token** khi profile yêu cầu. Không so nonce với state hoặc dùng ID token như access token của Orders API.

### Issuer không phải state

Một client có thể gửi state đúng đến AS-A, nhưng nhận một phản hồi từ AS-B theo một đường tấn công mix-up. Transaction correlation giúp biết client dự kiến AS nào; vẫn cần cách **nhận diện AS thực sự trả response** theo profile.

Nếu triển khai **RFC 9207**, client đối chiếu tham số **iss của authorization response** với issuer dự kiến. Các phương án khác như redirect URI riêng cho AS có thể phù hợp theo thiết kế. **State đơn thuần không được coi là bảo vệ hoàn chỉnh trước mọi mix-up attack**.

## 11. Callback lỗi vẫn cần state validation

AS có thể trả lỗi khi người dùng từ chối consent hoặc yêu cầu không được cấp phép:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/callback?error=access_denied&state=EXAMPLE_RANDOM_STATE
~~~

Client vẫn phải:

1. Nhận diện browser session và tìm pending transaction.
2. Kiểm state trả về đúng transaction, còn hạn và chưa dùng.
3. Consume transaction.
4. Xử lý error và hiển thị thông báo an toàn.
5. **Không** tạo phiên đăng nhập thành công hoặc đổi code từ callback có error.

Nếu state sai, không nên cập nhật trạng thái của giao dịch khác chỉ vì error hợp lệ về mặt tên. Một callback lỗi không có correlation vẫn là response không thuộc phiên đã tạo.

Phần AS cũng có trách nhiệm không redirect lỗi tới một **redirect_uri không hợp lệ**; client không được bỏ qua kiểm state để bù cho lỗi cấu hình AS.

## 12. Nhiều tab và nhiều authorization transactions

Một bug phổ biến khi web app chỉ lưu **một state duy nhất**:

~~~text
Tab A tạo state-A và verifier-A.
Session expectedState = state-A.

Tab B tạo state-B và verifier-B.
Session expectedState = state-B.

Tab A nhận callback state-A.
Ứng dụng chỉ nhớ state-B -> login A lỗi.
~~~

Một cách sửa sai là tắt state validation cho mọi tab; điều này phá cơ chế bảo vệ.

### Thiết kế đúng hơn

~~~text
Session.pendingOauth = {
    state-A: { verifier-A, issuer-A, createdAt-A, returnPath-A },
    state-B: { verifier-B, issuer-B, createdAt-B, returnPath-B }
}
~~~

Khi callback A đến, dùng đúng verifier-A và issuer-A; B vẫn chờ nếu chưa hết hạn.

**Các yêu cầu với multi-tab:**

- Mỗi flow có state và code_verifier **riêng**.
- Lưu transaction keyed by state, không dùng biến global currentVerifier/currentIssuer.
- Consume one-time và TTL cho từng record.
- Giới hạn số pending transactions trong một phiên để chống abuse.
- SPA sessionStorage thường tách theo tab; callback qua tab khác có thể không thấy state.
- BFF nhiều instance cần shared session store/atomic operation.
- Nếu hai tab hoàn tất login với hai tài khoản khác nhau, ứng dụng cần **chính sách thay phiên rõ ràng**, không để callback cũ tùy tiện ghi đè phiên mới.

## 13. State và return URL: tránh open redirect

Ứng dụng có thể cần quay về trang trước khi login:

~~~text
Before login: /orders/123
After login:  /orders/123
~~~

Không nên đưa một URL do người dùng cung cấp vào state rồi chuyển hướng trực tiếp:

~~~text
KHÔNG AN TOÀN:
    state = "https://untrusted.example/collect"
    onCallback: redirect(response.state)
~~~

Đây có thể trở thành **open redirect**, lừa đảo người dùng hoặc góp phần rò rỉ thông tin trong một flow cấu hình sai.

Mẫu an toàn:

~~~text
state = randomOpaqueState

pending[state] = {
    returnPath: "/orders/123",
    issuer: "https://identity.example.test",
    verifier: "...",
    expiresAt: "..."
}
~~~

Chỉ chấp nhận **returnPath nội bộ đã được kiểm**. Tránh redirect theo chuỗi có scheme/host tùy ý, dạng **//external.example**, backslash, mã hóa URL nhiều lớp hoặc đường dẫn được parser xử lý khác kỳ vọng.

Nếu cần chuyển về URL bên ngoài, phải có **allowlist cụ thể và chính sách riêng**; không tin state hoặc query tự khai.

### Signed hoặc encrypted state

Một số client lưu thông tin vào **state đã ký** thay vì lưu server-side:

- **Chữ ký** giúp kiểm dữ liệu không bị sửa, nhưng **không mã hóa nội dung**.
- **Mã hóa** giúp giấu dữ liệu nếu khóa được quản lý an toàn, nhưng không tự bảo vệ session binding.
- Signed state không mặc nhiên **one-time**; cần nonce/replay storage hoặc cơ chế tương đương.
- Nếu browser có thể sử dụng state của phiên khác mà không bị phát hiện, CSRF protection vẫn không đủ.
- Không đặt access token, refresh token, secret hoặc dữ liệu cá nhân nhạy cảm vào URL ngay cả khi thiết kế có signing/encryption, trừ khi profile được đánh giá kỹ.

Với web backend có session store, state **opaque ngẫu nhiên** và context server-side thường dễ hiểu, dễ thu hồi và dễ kiểm toán hơn.

## 14. Có phải state là một secret tuyệt đối?

State có mặt trong URL authorization/callback, nên có thể lọt vào:

- Browser history hoặc phần URL được sao chép.
- Proxy access log, tracing, analytics và debug network.
- Request callback, crash report hoặc error telemetry.
- Ngữ cảnh Referer và script bên thứ ba trên callback, tùy browser và chính sách.

Do đó, state nên là **chuỗi opaque không có PII**, tồn tại ngắn và chỉ dùng một lần. Không đặt password, access/refresh token, client secret hay thông tin y tế/định danh nhạy cảm trong state.

**Không log raw code, state và verifier** nếu không có lý do bảo mật được đánh giá; log lý do lỗi dạng **STATE_MISSING**, **STATE_MISMATCH**, **STATE_REUSED** an toàn hơn. Khi cần correlation trong logs, dùng transaction ID nội bộ không phải credential.

Dùng **HTTPS/TLS**, redirect URI chính xác và hạn chế script bên thứ ba trên callback. Với SPA, có thể dọn code/state khỏi URL bằng **history.replaceState** sau khi parse và xử lý an toàn, nhưng không được dọn trước khi lấy đủ dữ liệu kiểm.

Nếu state bị lộ trực tiếp từ phiên nạn nhân, sức mạnh bảo vệ có thể suy giảm; cần phối hợp PKCE, chống XSS và issuer validation.

## 15. State không giải quyết mọi vấn đề của token security

| Nguy cơ | State hỗ trợ đến đâu? | Cơ chế bổ sung |
| --- | --- | --- |
| **Login CSRF / response injection** | Trực tiếp giúp liên kết đúng callback với phiên. | PKCE, session binding, TTL/one-time. |
| **Authorization code interception** | Không trực tiếp ngăn đổi code tại AS. | PKCE, client authentication/binding, TLS. |
| **AS mix-up** | Giúp truy lại issuer đã chọn nhưng không đủ một mình. | RFC 9207 iss hoặc biện pháp mix-up phù hợp. |
| **OIDC ID token replay/confusion** | Không thay validation ID token. | nonce, iss/aud/exp theo OIDC. |
| **Open redirect** | Không tự chặn. | Redirect URI strict, return URL allowlist. |
| **XSS trong SPA** | Không chặn script độc hại cùng origin. | CSP, chống XSS, giảm credential browser. |
| **AT bị sao chép** | Không. | TLS, TTL, scope/audience, sender-constraining, revocation. |
| **RT bị đánh cắp** | Không. | Rotation hoặc sender-constraining, lưu trữ an toàn, revoke. |
| **Role/scope sai trên API** | Không. | RS kiểm token và phân quyền tài nguyên. |
| **CSRF trên API dùng cookie** | Không đủ; khác trust boundary. | SameSite, Origin checks, CSRF token/app policy. |
| **Client credentials misuse** | Không phải flow qua browser callback có state. | Client authentication, grant và scope policy. |

**State giải quyết một vấn đề giao dịch OAuth cụ thể.** Từ một state đã được kiểm không thể suy ra user có quyền sửa Order #123 hoặc một JWT chắc chắn đáng tin.

## 16. OAuth callback CSRF khác CSRF ứng dụng sau login

Hai trường hợp:

~~~text
OAuth callback:
    GET /oauth/callback?code=...&state=...

Ứng dụng sau login:
    POST /orders/123/approve
    Cookie: __Host-session=...
~~~

Với callback OAuth, câu hỏi là **response có thuộc authorization request của phiên này không?** State/PKCE/issuer context giải quyết.

Với POST duyệt đơn hàng, câu hỏi là **một site khác có thể lợi dụng browser gửi request tự động kèm session cookie không?** Ứng dụng cần anti-CSRF theo mô hình cookie, như SameSite, Origin/Referer checks, CSRF token hoặc cơ chế tương ứng.

**State OAuth không thay anti-CSRF protection của Orders API**, và token CSRF của form duyệt đơn hàng không tự thay state OAuth.

### Cookie SameSite và redirect từ AS

Authorization response là một **cross-site navigation** khi AS và client ở khác site.

- **SameSite=Lax** thường phù hợp với top-level navigation GET trong một số luồng authorization code theo điều kiện browser.
- Với **response_mode=form_post**, iframe hoặc thiết kế khác, cookie có thể hành xử khác; phải kiểm theo môi trường và profile.
- Không “sửa” callback mất session bằng cách **bỏ kiểm state** hoặc chấp nhận session không khớp.
- Điều chỉnh cookie/session/redirect design đúng thay vì tạo bypass bảo mật.

## 17. Nhiều Authorization Server và nguy cơ mix-up

Một client tích hợp hai AS:

~~~text
Issuer A: https://identity-a.example.test
Issuer B: https://identity-b.example.test
~~~

State-A liên kết với AS-A, state-B liên kết với AS-B. Client phải biết **issuer nào đã được chọn** và bảo đảm authorization response không khiến client gửi code, client secret hoặc code_verifier tới **token endpoint sai**.

Ví dụ không an toàn:

~~~text
Callback chứa:
    code = some-code
    state = some-state
    token_endpoint = https://attacker.example/token

Client:
    gửi code/client secret tới token_endpoint do callback tự khai
~~~

Mẫu an toàn:

1. Tìm đúng pending transaction bằng state **và browser session**.
2. Lấy **expected issuer** từ dữ liệu đã lưu.
3. Xác minh issuer của authorization response theo profile áp dụng, ví dụ **RFC 9207 iss**.
4. Dùng **trusted token endpoint** đã cấu hình/discovery cho issuer đó, không lấy URL từ callback.
5. Nếu issuer không phù hợp, từ chối chứ không “thử AS khác”.

**State là một khóa correlation quan trọng nhưng không tự đóng vai trò xác thực Authorization Server**.

## 18. Bộ kiểm thử âm tính và hành vi mong đợi

| Tình huống | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| **State đúng** | Pending thuộc phiên, còn hạn, chưa dùng. | Tiếp tục kiểm issuer, code, PKCE, token. |
| **Thiếu state** | Request ban đầu có state, callback không có. | Từ chối trước token exchange. |
| **State sai** | Callback gửi giá trị khác. | Từ chối, không tạo session. |
| **State của phiên khác** | state-A của browser A gửi tới browser B. | Từ chối. |
| **State đã consume** | Callback thứ hai dùng lại cùng state. | Từ chối replay. |
| **State hết TTL** | Callback sau expiry của pending record. | Từ chối và cleanup. |
| **Prefix giống nhau** | Chỉ vài ký tự đầu state khớp. | Từ chối. |
| **Tham số state trùng** | Callback có hai state khác nhau. | Từ chối theo strict parser. |
| **State quá dài/bất thường** | Chuỗi hàng MB hoặc sai format đã thiết kế. | Từ chối sớm, giới hạn tài nguyên. |
| **Login CSRF** | Attacker code và state của phiên attacker được đưa vào browser nạn nhân. | Từ chối. |
| **Authorization error đúng state** | error=access_denied, state hợp lệ. | Consume, báo lỗi, không tạo session. |
| **Authorization error sai state** | error hợp lệ nhưng state khác. | Không áp lỗi vào giao dịch không liên quan. |
| **Multi-tab** | Hai state và verifier song song. | Mỗi callback dùng đúng giao dịch. |
| **Issuer sai** | State đúng nhưng iss không đúng expected issuer. | Từ chối theo mix-up protection. |
| **Verifier sai** | Code-A được đổi với verifier-B. | AS từ chối do PKCE, client không tráo verifier. |
| **Return URL độc hại** | returnPath cố chuyển tới external host. | Không redirect theo dữ liệu không tin cậy. |
| **Session cookie thiếu** | Callback không có context đã mở flow. | Không chấp nhận chỉ nhờ global state. |
| **Race** | Hai callback đồng thời với cùng state. | Tối đa một consume thành công. |
| **State trong log** | Request query xuất hiện ở proxy/telemetry. | Redact và hạn chế lưu credential/transaction token. |

### Kiểm thử biên thời hạn

Giả sử TTL pending state là **5 phút**:

~~~text
10:00:00 -> tạo state-A.
10:04:59 -> consume state-A thành công.
10:05:00 -> callback state-A nữa: bị từ chối vì đã dùng.

10:10:00 -> tạo state-B.
10:15:00 -> consume state-B: hết hạn, bị từ chối.
~~~

Khi test Java, dùng **Clock.fixed** hoặc fake Clock; không dựa vào đồng hồ thực và sleep. **Mốc 5 phút chỉ là ví dụ chính sách**, không phải quy tắc bắt buộc của OAuth.

## 19. Kịch bản tổng hợp: Dashboard, hai tab và hai IdP

Một Dashboard có hai lựa chọn đăng nhập:

~~~text
Company SSO:
    issuer = https://company-id.example.test

Partner SSO:
    issuer = https://partner-id.example.test
~~~

Người dùng mở hai tab:

- **Tab A:** login Company SSO, state-A, verifier-A, returnPath=/orders.
- **Tab B:** login Partner SSO, state-B, verifier-B, returnPath=/reports.

Tab B hoàn tất trước:

1. Client nhận state-B, tìm transaction của browser session và kiểm còn hạn.
2. Kiểm issuer của response là Partner SSO theo cơ chế đã triển khai.
3. Consume state-B.
4. Đổi code tại token endpoint của Partner SSO với verifier-B.
5. Xác minh token/ID token theo profile.
6. Cập nhật phiên theo policy và chỉ redirect đến **/reports** đã được kiểm.

Tab A về sau:

- Có thể được xử lý theo policy nếu transaction A vẫn hợp lệ và phiên chưa đổi context không tương thích.
- Nếu user/account của phiên đã thay đổi, ứng dụng có thể yêu cầu khởi tạo lại flow thay vì âm thầm ghi đè session.
- Dù lựa chọn nào, **không được bỏ state validation** hoặc dùng verifier-B cho callback A.

Một app chỉ lưu **currentState** hoặc **currentIssuer** toàn cục sẽ dễ nhầm luồng; chính transaction keyed by state giải quyết correlation, không chỉ sự tồn tại của một tham số trên URL.

## 20. Checklist triển khai state parameter

1. **Sinh:** State mới cho từng authorization request bằng CSPRNG, đủ entropy và không đoán được?
2. **Định dạng:** State là opaque/URL-safe, không chứa AT, RT, client secret, password hay PII?
3. **Lưu trước redirect:** Pending transaction có state, issuer, verifier, TTL, redirect URI và nonce OIDC nếu cần?
4. **Session binding:** Callback chỉ chấp nhận state thuộc **đúng browser session/client context** đã khởi tạo?
5. **State exact match:** Có từ chối state thiếu/sai/hết hạn/đã dùng/trùng tham số không?
6. **One-time:** Transaction được consume atomic, không cho callback lặp hay hai request race cùng thành công?
7. **Multi-tab:** Có map nhiều pending transactions, mỗi cái có verifier/issuer riêng, giới hạn số lượng và cleanup?
8. **PKCE:** Code verifier/challenge S256 đúng profile; AS kiểm verifier tại token endpoint?
9. **OIDC nonce:** Nếu dùng, client có kiểm nonce trong ID token theo OIDC?
10. **Multi-AS:** Có kiểm issuer hoặc cơ chế mix-up defense (ví dụ RFC 9207) và không chọn token endpoint từ callback?
11. **Redirect URI:** AS/client có kiểm URI đúng đăng ký, không cho open redirect?
12. **Return URL:** Chỉ dùng đường dẫn nội bộ đã kiểm/allowlist, không redirect theo state string tự khai?
13. **Error callback:** State vẫn được kiểm khi response có error; không tạo authenticated session khi user từ chối?
14. **Cookie:** Backend session cookie đủ thuộc tính bảo vệ và tương thích callback SameSite/form_post theo flow?
15. **SPA:** Không coi sessionStorage/localStorage là secret vault, có bảo vệ XSS và xử lý callback đúng tab?
16. **TLS:** Authorization/token endpoints qua HTTPS, certificate/hostname và issuer đáng tin?
17. **Log/telemetry:** Không log raw code, state, verifier và token; có mã lỗi/correlation metadata an toàn?
18. **Token validation:** Sau state vẫn kiểm ID token/access token theo profile, issuer/audience/exp và policy?
19. **Negative tests:** Có test login CSRF, replay, wrong session, TTL, wrong issuer, multi-tab, callback error và redirect độc hại?
20. **Vai trò:** Không nhầm state với role, scope, audience hoặc quyền trên tài nguyên của Resource Server?

## Kết luận

**State parameter là công cụ liên kết authorization response với authorization request mà client thực sự đã khởi tạo.** Giá trị này cần **khó đoán, được lưu theo đúng phiên/giao dịch, có hạn và dùng một lần**. Client phải xác minh callback trước khi đổi authorization code hoặc thiết lập phiên; có code hợp lệ nhưng state không khớp **không đủ để chấp nhận đăng nhập**.

Trong OAuth 2.0/OIDC hiện đại, state phối hợp với **PKCE, OIDC nonce khi áp dụng, xác minh issuer, redirect URI, TLS và bảo vệ session**. Nó không thay các phép kiểm này, cũng không thay authorization của Resource Server. Một kiến trúc đúng giữ rõ ranh giới tin cậy: **client xác minh giao dịch của mình; AS xác minh grant và cấp token; Resource Server xác minh access token và quyền trên tài nguyên**.

### Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.1.1: Authorization Request](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.1)
- [RFC 6749 — Section 4.1.2: Authorization Response](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2)
- [RFC 6749 — Section 10.12: Cross-Site Request Forgery](https://www.rfc-editor.org/rfc/rfc6749#section-10.12)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)
- [OpenID Connect Core 1.0 — Authentication Response Validation](https://openid.net/specs/openid-connect-core-1_0.html#AuthResponseValidation)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
