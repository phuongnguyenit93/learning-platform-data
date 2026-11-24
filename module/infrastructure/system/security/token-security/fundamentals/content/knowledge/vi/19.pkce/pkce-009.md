# Verifier storage in the client

Trong luồng **OAuth 2.0 Authorization Code + PKCE** (*Proof Key for Code Exchange*), client tạo một giá trị ngẫu nhiên bí mật gọi là **`code_verifier`**, tính `code_challenge` và gửi **challenge** trong authorization request. Sau khi user hoàn thành đăng nhập/consent ở Authorization Server (AS), client nhận **authorization code** qua redirect và phải gửi **chính verifier ban đầu** tới token endpoint để đổi code lấy token.

Thách thức: giữa hai bước đó, ứng dụng có thể **rời trang, reload, mở nhiều tab, mất phiên hoặc bị hệ điều hành dừng tiến trình**. Nếu verifier biến mất, code không đổi được. Nếu verifier bị lưu trong URL/log hoặc ở một kho sai, attacker có thể lấy nó cùng authorization code. Vì thế, **“Verifier storage in the client”** là bài toán về **bí mật, tuổi thọ và liên kết transaction**, không đơn giản là chọn API lưu trữ.

Bài học thuộc chương **PKCE** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, kết nối OAuth 2.0/OIDC với mô hình tin cậy, JWT/opaque token, access/refresh token, claims, scope, audience, lưu trữ, thu hồi và chống đánh cắp/phát lại.

**Nguyên tắc:** giữ `code_verifier` **chỉ trong thời gian cần thiết, chỉ cho một authorization transaction, gắn với đúng `state`/issuer/client/redirect**, không đưa vào authorization URL và không ghi log. Khi callback hoàn tất, lỗi hoặc hết hạn, phải **xóa transaction**.

## 1. Vì sao client cần giữ verifier đến khi callback?

PKCE theo [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) bảo vệ việc đổi code trước tình huống attacker chỉ có authorization code bị chặn bắt. Client gửi **challenge công khai** khi bắt đầu và **verifier bí mật** khi đổi code.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant S as Client transaction store
    participant B as Browser
    participant AS as Authorization Server

    C->>C: Tạo verifier V, state S, challenge C=S256(V)
    C->>S: Lưu V gắn state S và issuer/context
    C->>B: Mở authorization URL chứa C và S
    B->>AS: GET /authorize
    AS->>AS: User authentication / consent
    AS->>AS: Gắn challenge C với code K
    AS-->>B: Redirect code=K và state=S
    B-->>C: Callback
    C->>S: Tra đúng S, consume transaction
    S-->>C: V và metadata đã lưu
    C->>C: Kiểm tra state và issuer/context
    C->>AS: POST /token với K và V
    AS->>AS: Verify code, client, redirect, S256(V), grant
    AS-->>C: Token response hoặc invalid_grant
    C->>C: Dọn verifier và transaction
~~~

Với PKCE S256:

~~~text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)
code_challenge_method = S256
~~~

`code_verifier` theo RFC 7636 có **43–128 ký tự** thuộc tập unreserved `A-Z a-z 0-9 - . _ ~`, được sinh đủ entropy. Phương pháp phổ biến: tạo **32 byte CSPRNG**, mã hóa Base64url không padding thành **43 ký tự**.

**Phải giữ verifier gốc**, không thể chỉ lưu `code_challenge` rồi gửi challenge như verifier. AS sẽ tính S256 trên giá trị client trình và so với challenge đã gắn với code.

## 2. Verifier là loại bí mật gì?

| Giá trị | Mục đích | Được gửi ở đâu? | Rủi ro nếu lộ |
|---|---|---|---|
| **`code_verifier`** | Proof của một transaction | Chỉ ở token request `/token` | Bị lợi dụng khi attacker cũng có code và vượt được ràng buộc khác |
| **`code_challenge`** | Cam kết một chiều từ verifier | `/authorize` qua browser | Một mình nó không đủ tìm verifier entropy cao |
| **`state`** | Liên kết callback với authorization transaction, chống CSRF | `/authorize` và callback | Không phải bearer token; vẫn cần giữ khỏi rò/giả mạo theo threat model |
| **Authorization code** | Grant tạm thời, dùng một lần | Callback rồi token endpoint | Bị đổi nếu không có PKCE/client binding đúng |
| **Access token** | Gọi API đúng audience/scope | Resource Server | Bearer token bị sao chép có thể replay |
| **Refresh token** | Xin token mới theo grant | AS token endpoint | Có thể kéo dài quyền truy cập |
| **ID token (OIDC)** | Authentication event cho client | OIDC client | Lộ claims hoặc bị dùng sai mục đích |

**Verifier không phải client secret hoặc password lâu dài**. Việc lộ riêng verifier chưa tự tạo quyền gọi API; attacker cần code tương ứng, và với confidential client còn phải vượt client authentication. Nhưng không vì vậy mà được đưa verifier vào log hoặc front channel.

**PKCE không mã hóa code, không thay user authentication, client authentication hay kiểm tra access token tại API.** Nó là ràng buộc proof-of-possession của lần **authorization code exchange**.

## 3. Hai yêu cầu đối lập: giữ bí mật và không làm mất transaction

Verifier storage phải đạt cả hai:

1. **Confidentiality:** không lộ cho bên không cần biết, không gửi qua URL, redirect, analytics, third-party script, log hay API nghiệp vụ.
2. **Continuity:** client vẫn lấy được đúng verifier khi browser quay về, dù document JavaScript bị reload, app di chuyển qua system browser hoặc process được khởi tạo lại.

Cùng một giải pháp không phù hợp mọi môi trường:

- **Backend/BFF:** có thể giữ verifier **server-side**, browser chỉ mang cookie phiên và `state`.
- **SPA:** full-page redirect thường hủy memory JS; OAuth SDK có thể cần `sessionStorage` hoặc cơ chế transaction ngắn hạn.
- **Mobile:** OS có thể kill app trong lúc system browser đang login; memory đôi khi không đủ, cần protected temporary storage.
- **Desktop:** external browser/loopback callback và app restart có vấn đề tương tự mobile.

**Memory-only** giảm tồn tại at rest nhưng mất khi process/tab thay đổi. **Persist dài hạn** tăng bề mặt rò và dễ gây stale transaction. Thiết kế tốt giữ **ít và ngắn**, nhưng không để client phải bỏ PKCE để “cho login thành công”.

## 4. Threat model của verifier storage

| Bối cảnh | Lỗi có thể xuất hiện | Biện pháp |
|---|---|---|
| XSS trong SPA | JS cùng origin đọc `sessionStorage`/`localStorage` | Chống XSS, CSP, giảm third-party JS, cân nhắc BFF |
| Verifier trong localStorage | Tồn tại lâu qua restart và nhiều tab | Ưu tiên transaction storage ngắn hạn, cleanup |
| Nhiều login song song | Một `currentVerifier` global bị flow khác ghi đè | Lưu record theo state/transaction |
| Callback giả hoặc issuer sai | Dùng verifier cho code/AS không thuộc giao dịch | Bind state, browser session, issuer, redirect và client |
| Mobile process death | Callback tới sau khi RAM mất | Persist tạm có bảo vệ nếu cần, TTL và khôi phục theo state |
| Backup/restore thiết bị | Record cũ sang device/context khác | Backup exclusion, device-only và reject stale flow |
| Crash/error reporting | Serialized transaction bị ghi log | Redaction/allowlist fields, không in verifier |
| Có cả code và verifier | PKCE không còn chặn riêng bằng proof | Code TTL/one-time, client auth nếu áp dụng, điều tra |
| Trộn tab/account | Token user A gắn vào phiên B | Transaction ownership, account/session binding |
| Bị giả mạo token endpoint | Verifier được gửi sang attacker | Chỉ dùng endpoint issuer cấu hình tin cậy |

**Giới hạn cần nêu rõ:** nếu attacker đã kiểm soát tiến trình client hoặc JavaScript origin, họ có thể đọc verifier khi client cần sử dụng, bất kể storage được mã hóa at rest. Secure storage giúp giảm nhiều đường rò, **không bảo đảm an toàn tuyệt đối trước runtime compromise**.

## 5. Mỗi authorization request cần record riêng

Một transaction điển hình mang thông tin sau (JSON **minh họa nội bộ**, **tuyệt đối không log nguyên record**):

~~~json
{
  "transaction_id": "tx-pseudo-72",
  "state": "<RANDOM_STATE>",
  "code_verifier": "<EPHEMERAL_SECRET_DO_NOT_LOG>",
  "client_id": "orders-web",
  "expected_issuer": "https://auth.example.test",
  "redirect_uri": "https://app.example.test/auth/callback",
  "created_at": "2026-11-23T10:00:00Z",
  "expires_at": "2026-11-23T10:05:00Z",
  "used": false
}
~~~

Record cần giữ:

- `state` ngẫu nhiên mạnh, làm khóa lookup và liên kết với phiên client/browser đang khởi tạo flow.
- `code_verifier` được sinh **mới cho mỗi flow**, không dùng chung với state.
- Issuer/redirect URI/client ID, token endpoint tham chiếu **cấu hình tin cậy**, không nhận từ query callback.
- `created_at`/`expires_at` cho **transaction TTL phía client**.
- Trạng thái consumed/used, đủ để chống callback xử lý trùng.
- `nonce` OIDC nếu client sử dụng và profile yêu cầu kiểm tra ID token.

**Transaction TTL không phải authorization code TTL.** Client tạo verifier trước khi user login, còn AS chỉ phát code sau khi authorization hoàn tất. TTL code tính từ **thời điểm AS phát hành code**, không phải lúc client tạo verifier.

## 6. State key, session binding và issuer binding

Khi có hai flow song song:

~~~text
Flow A:
    state = S_A
    verifier = V_A
    expectedIssuer = AS_1

Flow B:
    state = S_B
    verifier = V_B
    expectedIssuer = AS_1

Callback code=K_A&state=S_A
    -> chỉ lấy V_A
    -> chỉ gửi tới token endpoint AS_1

Callback code=K_B&state=S_B
    -> chỉ lấy V_B
    -> chỉ gửi tới token endpoint AS_1
~~~

Một biến `pkceVerifier` duy nhất ở app-global scope sẽ bị ghi đè; callback A có thể dùng V_B và nhận `invalid_grant`. Ngoài lỗi khả dụng, cách liên kết tùy tiện còn tạo bề mặt confusion khi có nhiều issuer/client.

**State một mình không đủ làm quyền truy xuất verifier trong kho server toàn cục.** Với BFF, callback cần đúng **browser session** và record state thuộc phiên đó. Với SPA, transaction store/SDK cần giới hạn đúng origin, context/tab hoặc popup.

### Khi có nhiều Authorization Server

Client phải lưu **issuer dự kiến** và dùng token endpoint lấy từ registration/metadata tin cậy. Trong callback, so khớp state và issuer (`iss` RFC 9207 khi hỗ trợ); nếu profile cấu hình yêu cầu `iss` mà thiếu nó cũng phải từ chối.

Không nhận `token_endpoint` do attacker chèn vào URL callback rồi gửi verifier đến đó. **Phòng AS mix-up là lớp bảo vệ bổ sung, không phải chức năng của storage encryption.**

## 7. Vòng đời lưu, lấy và xóa verifier

~~~mermaid
stateDiagram-v2
    [*] --> CREATED: Sinh state + verifier + challenge
    CREATED --> STORED: Lưu record theo state
    STORED --> AUTHORIZING: Mở authorization URL
    AUTHORIZING --> RETURNED: Callback code + state
    AUTHORIZING --> EXPIRED: User bỏ dở/transaction TTL
    RETURNED --> CONSUMED: Xác minh context, atomic takeOnce
    RETURNED --> REJECTED: State/issuer sai
    CONSUMED --> EXCHANGED: POST token endpoint thành công
    CONSUMED --> FAILED: POST token endpoint lỗi
    EXCHANGED --> CLEANED: Dọn verifier
    FAILED --> CLEANED: Dọn hoặc xử lý policy an toàn
    REJECTED --> CLEANED: Không làm lộ verifier
    EXPIRED --> CLEANED: Xóa record cũ
    CLEANED --> [*]
~~~

**Lưu trước khi điều hướng.** Nếu app gọi `location.assign()` rồi mới lưu verifier, trang có thể rời origin trước khi thao tác lưu hoàn tất.

**Xóa sau khi hoàn tất, thất bại hoặc hết hạn.** Khi response `/token` bị mất, AS có thể đã tiêu thụ code, nên không coi verifier còn trong storage là giấy phép retry vô hạn cùng code. Hướng phục hồi thường là **authorization flow mới**.

**Lấy một lần** (atomic get-and-delete) phù hợp khi callback có thể trùng hoặc tới đồng thời. BFF đa node cần storage có consistency; mutex nội bộ một JVM không đủ.

## 8. Bảng chọn storage theo kiến trúc client

| Kiến trúc | Nơi lưu phù hợp | Qua redirect/process death | Nguy cơ còn lại |
|---|---|---|---|
| **BFF/confidential web backend** | Server-side session/transaction store | Có nếu backend store ổn định | Session fixation, stale session, log/backup server |
| **SPA full-page redirect** | SDK transaction store ngắn hạn; có thể `sessionStorage` | Cùng tab/origin, thường qua navigation/reload | XSS/third-party JS có thể đọc |
| **SPA popup** | Parent-window memory + message protocol được bảo vệ | Parent phải còn sống | `postMessage` sai targetOrigin/source, popup lifecycle |
| **iOS native** | Memory; Keychain item tạm khi cần qua process restart | Keychain có thể tồn tại lâu hơn process | Entitlement, access class, reinstall/restore |
| **Android native** | Memory; Keystore-backed encrypted app-private record | Ciphertext sống qua process restart | Key invalidation, backup mismatch |
| **Desktop** | Memory; OS credential storage khi cần | Phụ thuộc app lifecycle | File cấu hình plaintext, crash dump |
| **BFF browser cookie** | **Chỉ opaque session ID**, verifier nằm server | Cookie liên kết browser session | CSRF, session fixation, session theft |

**Không có “luôn dùng Keychain” hoặc “luôn dùng sessionStorage”** cho mọi ứng dụng. Cân bằng yếu tố cần survive navigation, khả năng chống XSS/malware, deadline, backup và user experience.

## 9. BFF: giữ verifier server-side, browser chỉ giữ session

BFF là lựa chọn dễ tách bí mật khỏi JavaScript của browser. Backend sinh verifier và state; chỉ challenge/state qua browser. Token exchange từ backend tới AS, theo client authentication khi confidential client.

~~~mermaid
flowchart LR
    B["Browser: session cookie"]
    C["BFF login/callback controller"]
    S[("Server-side transaction store")]
    AS["Authorization Server"]
    API["Orders Resource Server"]

    B -->|"GET /login"| C
    C -->|"Lưu state → verifier + expiry + issuer"| S
    C -->|"Authorization URL challenge + state"| B
    B -->|"GET /authorize"| AS
    AS -->|"Redirect code + state"| B
    B -->|"GET /callback + session cookie"| C
    C -->|"Atomic take session + state"| S
    C -->|"POST /token + verifier + client auth"| AS
    AS -->|"Tokens nếu grant hợp lệ"| C
    C -->|"Gọi API với access token"| API
    C -->|"Session cookie an toàn"| B
~~~

### Session store phải đảm bảo

1. Record được khóa logic bởi **browser session reference + state**, tránh nhầm user/tab/tenant.
2. `code_verifier`, issuer, redirect URI và TTL nằm server-side, không ghi vào cookie client-side hoặc HTML.
3. `takeOnce` được bảo vệ atomicity/transaction trên các backend instances.
4. Session cookie là giá trị khó đoán, có `Secure`/`HttpOnly`/`SameSite` và hạn phù hợp.
5. Với authorization callback top-level **GET**, `SameSite=Lax` thường hoạt động; nếu dùng cross-site `form_post` cần xem lại cookie policy và CSRF, không tắt bảo mật tùy tiện.
6. BFF vẫn cần chống session fixation, xử lý logout/cancel và không log raw transaction.

**HttpOnly cookie không phải nơi để SPA đọc verifier.** Với BFF, cookie chỉ giúp backend tìm **server-side** record.

## 10. Java 17: mô hình transaction store theo state và session

Đoạn Java 17 dưới đây minh họa cách sinh verifier/challenge và ràng buộc verifier với session, state, issuer và deadline. `Store` chỉ là **interface**, không phải triển khai database/Redis sản xuất.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;

public final class PkceTransactionService {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder BASE64URL =
            Base64.getUrlEncoder().withoutPadding();

    // Đây là TTL phía client, không phải authorization code TTL.
    private static final Duration TRANSACTION_TTL =
            Duration.ofMinutes(5);

    public record PendingTransaction(
            String codeVerifier,
            String expectedIssuer,
            String clientId,
            String redirectUri,
            Instant expiresAt
    ) {}

    public record Start(String state, String codeChallenge) {}

    public interface Store {
        void save(String sessionRef, String state,
                  PendingTransaction pending);

        // Phải lấy và xóa atomically trong server-side store.
        PendingTransaction takeOnce(String sessionRef, String state);
    }

    private static String randomValue() {
        byte[] bytes = new byte[32];
        RNG.nextBytes(bytes);
        return BASE64URL.encodeToString(bytes);
    }

    private static String challenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(
                            StandardCharsets.US_ASCII));
            return BASE64URL.encodeToString(digest);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static Start begin(
            String sessionRef, Store store, Clock clock
    ) {
        Objects.requireNonNull(sessionRef);
        String state = randomValue();
        String verifier = randomValue();
        PendingTransaction tx = new PendingTransaction(
                verifier,
                "https://auth.example.test",
                "orders-bff",
                "https://app.example.test/auth/callback",
                clock.instant().plus(TRANSACTION_TTL)
        );
        store.save(sessionRef, state, tx); // trước redirect
        return new Start(state, challenge(verifier));
    }

    public static PendingTransaction finish(
            String sessionRef, String returnedState,
            Store store, Clock clock
    ) {
        PendingTransaction tx =
                store.takeOnce(sessionRef, returnedState);
        if (tx == null
                || !clock.instant().isBefore(tx.expiresAt())) {
            throw new SecurityException(
                    "Unknown or expired OAuth transaction"
            );
        }

        return tx;
        // Caller phải kiểm tra issuer/redirect/client context,
        // đổi code tại token endpoint của đúng AS,
        // xác thực confidential client theo registration.
    }

    private PkceTransactionService() {}
}
~~~

**Giới hạn bảo mật của ví dụ:**

- `Store.save/takeOnce` phải có implementation đáng tin, TTL, giới hạn transaction và **atomic consume trên toàn bộ node**.
- `sessionRef` lấy từ server-side browser session được bảo vệ, **không lấy từ query** do client tự khai.
- `finish` chỉ lấy record; **chưa kiểm tra code, response issuer, token endpoint, PKCE server-side hoặc quyền API**. Phần này do OAuth client SDK và AS xử lý.
- `String` giữ verifier trong heap; không đảm bảo zeroize. Tránh debug serialization/log/snapshot và giữ lifetime ngắn.
- Khi thiếu/expired state, không tạo verifier mới cho cùng code; bắt đầu authorization transaction mới.

## 11. SPA: memory, sessionStorage và localStorage

Với SPA public client, browser redirect thường làm document unload nên biến JS có thể biến mất. OAuth SDK có thể lưu verifier ngắn hạn trong `sessionStorage` để callback trong cùng tab lấy lại.

| Nơi lưu | Sống qua full redirect? | Ai đọc được? | Đánh giá |
|---|---|---|---|
| **JS memory** | Thường không nếu document bị thay | JS trong context đó | Tốt nếu parent window/popup còn sống |
| **`sessionStorage`** | Thường có trong cùng tab + origin | JS cùng origin/tab | Thực dụng cho transaction ngắn hạn, **không chống XSS** |
| **`localStorage`** | Có qua restart/tab | JS cùng origin | Không ưu tiên: tồn tại lâu và dễ bỏ sót cleanup |
| **IndexedDB** | Bền vững | JS cùng origin | Không tự bảo vệ khỏi XSS; thường không cần cho PKCE |
| **JS-readable cookie** | Tùy cookie policy | JS và request đúng scope | Không phù hợp để chứa raw verifier |
| **HttpOnly cookie** | Có thể qua redirect | JS không đọc | Phù hợp session BFF, không thể dùng SPA thuần lấy verifier |
| **URL query/fragment/state** | Có thể đi qua browser | JS, history, telemetry và một số log | **Không dùng lưu verifier** |

**`sessionStorage` là giải pháp tồn tại qua navigation, không phải kho bí mật an toàn tuyệt đối.** Script cùng origin (kể cả script bên thứ ba được nhúng trong document) có thể đọc. Browser có thể khôi phục sessionStorage sau session restore, và opener có thể ảnh hưởng initial storage của tab mới. Cần TTL/callback context và kiểm thử browser thực tế.

### Hạn chế XSS

- Giảm third-party scripts ở login/callback, dùng CSP phù hợp và xử lý input/output chống XSS.
- Không chạy analytics trước callback cleanup; không gửi raw URL/verifier cho crash reporter.
- Nếu threat model không chấp nhận việc JS thấy refresh/access token, cân nhắc BFF. PKCE không làm client thành confidential client.
- Không chuyển verifier sang `localStorage` chỉ vì `sessionStorage` có thể bị mất; xử lý missing transaction như lỗi flow và restart an toàn.

## 12. JavaScript: lưu verifier theo state trong sessionStorage

Ví dụ JavaScript dưới đây minh họa public SPA với Authorization Code + PKCE S256. Nó **chỉ tập trung vào transaction storage và callback**, không phải OAuth SDK hoàn chỉnh. AS phải hỗ trợ public client và CORS tương ứng ở token endpoint.

~~~javascript
const AUTH = Object.freeze({
    issuer: "https://auth.example.test",
    authorize: "https://auth.example.test/authorize",
    token: "https://auth.example.test/token",
    clientId: "orders-spa",
    redirectUri: "https://app.example.test/auth/callback",
    scope: "openid orders:read"
});

const TX_TTL_MS = 5 * 60 * 1000;
const txKey = (state) => "oauth.pkce.tx." + state;

function randomBase64url32() {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const binary = Array.from(bytes, b => String.fromCharCode(b))
        .join("");
    return btoa(binary).replaceAll("+", "-")
        .replaceAll("/", "_").replace(/=+$/, "");
}

async function s256(verifier) {
    const digest = await crypto.subtle.digest(
        "SHA-256", new TextEncoder().encode(verifier)
    );
    const binary = Array.from(new Uint8Array(digest),
        b => String.fromCharCode(b)).join("");
    return btoa(binary).replaceAll("+", "-")
        .replaceAll("/", "_").replace(/=+$/, "");
}

async function beginAuthorization() {
    const state = randomBase64url32();
    const verifier = randomBase64url32();
    const challenge = await s256(verifier);

    sessionStorage.setItem(txKey(state), JSON.stringify({
        state,
        codeVerifier: verifier,
        issuer: AUTH.issuer,
        redirectUri: AUTH.redirectUri,
        expiresAt: Date.now() + TX_TTL_MS
    }));  // Lưu trước khi rời trang; fail nếu storage bị chặn.

    const url = new URL(AUTH.authorize);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("client_id", AUTH.clientId);
    url.searchParams.set("redirect_uri", AUTH.redirectUri);
    url.searchParams.set("scope", AUTH.scope);
    url.searchParams.set("state", state);
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");

    window.location.assign(url.toString());
}

async function finishAuthorization() {
    const callback = new URL(window.location.href);
    const state = callback.searchParams.get("state");
    const code = callback.searchParams.get("code");
    const error = callback.searchParams.get("error");
    const responseIssuer = callback.searchParams.get("iss");

    // Bỏ query nhạy cảm khỏi URL hiện tại càng sớm càng tốt.
    window.history.replaceState(null, "", "/auth/processing");

    if (!state || !/^[A-Za-z0-9_-]{43}$/.test(state)) {
        throw new Error("Invalid OAuth state");
    }

    const key = txKey(state);
    const raw = sessionStorage.getItem(key);
    sessionStorage.removeItem(key); // Consume một lần.
    if (!raw) {
        throw new Error("Missing OAuth transaction");
    }

    let tx;
    try {
        tx = JSON.parse(raw);
    } catch {
        throw new Error("Invalid OAuth transaction");
    }

    if (tx.state !== state
            || tx.issuer !== AUTH.issuer
            || tx.redirectUri !== AUTH.redirectUri
            || Date.now() >= tx.expiresAt) {
        throw new Error("Mismatched or expired OAuth transaction");
    }

    // Nếu AS/profile yêu cầu RFC 9207 iss, cũng phải reject
    // nếu trường iss bị thiếu, không chỉ khi giá trị khác.
    if (responseIssuer !== null
            && responseIssuer !== tx.issuer) {
        throw new Error("Issuer mismatch");
    }

    if (error) {
        throw new Error("Authorization denied or failed");
    }
    if (!code) {
        throw new Error("Authorization code missing");
    }

    const body = new URLSearchParams({
        grant_type: "authorization_code",
        client_id: AUTH.clientId,
        redirect_uri: tx.redirectUri,
        code,
        code_verifier: tx.codeVerifier
    });

    const response = await fetch(AUTH.token, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
        credentials: "omit",
        cache: "no-store",
        body
    });

    if (!response.ok) {
        // Không log token endpoint response/raw request body.
        throw new Error("Token exchange failed");
    }

    const tokens = await response.json();
    // SDK/auth state chịu trách nhiệm kiểm tra và lưu token.
    // KHÔNG đưa tokens vào URL/sessionStorage/localStorage.
    return tokens;
}
~~~

### Giới hạn và việc cần bổ sung

1. `txKey` giúp nhiều giao dịch trong cùng tab không ghi đè. Nhưng callback ở **tab khác** có thể không thấy sessionStorage; SDK cần cơ chế phù hợp hoặc restart.
2. Nếu sessionStorage bị chặn, `setItem` có thể throw. **Không fallback đưa verifier vào URL**.
3. `sessionStorage` **JS-readable**, nên không bảo vệ khỏi XSS/third-party script. Đây là trade-off có chủ đích cho một public SPA.
4. `expiresAt` là deadline **transaction client**, không phải code expiry do AS kiểm tra.
5. Nếu AS bắt buộc `iss` trong authorization response, phải kiểm tra cả **sự hiện diện**; ví dụ hiện chỉ đối chiếu khi có.
6. Sau `removeItem`, nếu AS đã consume code nhưng response mất, retry cùng code không đáng tin. Không giữ verifier vĩnh viễn để thử lại.
7. Khi dùng OIDC, client phải kiểm tra `id_token` đúng issuer, audience và nonce/profile; không coi `return tokens` là đủ để tạo authenticated session.
8. Nên dùng OAuth/OIDC SDK được bảo trì cho CSRF, issuer mix-up, multi-tab, token lifecycle, SDK callback parsing và network errors; snippet chỉ minh họa lưu verifier.

## 13. Multi-tab, popup và postMessage

### Flow song song trong cùng tab

Nếu user bấm login hai lần, mỗi flow phải có **state/verifier riêng**. SDK có thể hỗ trợ nhiều pending transactions hoặc hủy flow cũ theo policy; không dùng một key global `pkce_verifier`.

### Callback trở về tab khác

`sessionStorage` được phân vùng theo origin/top-level browsing context nên **không thể giả định tab B thấy dữ liệu của tab A**. Một số trình duyệt có thể sao chép initial storage từ opener; đó không phải giao thức chia sẻ verifier an toàn.

### Popup flow

Khi parent window còn sống, parent có thể giữ verifier trong memory; popup chuyển code+state cho parent bằng `postMessage` với xác thực:

- Kiểm tra `event.origin` đúng origin của callback và `event.source` đúng popup.
- Gửi với `targetOrigin` cụ thể, không dùng `"*"`.
- Parent đối chiếu `state`, rồi exchange bằng verifier đã lưu.
- Không gửi verifier sang popup hoặc nguồn bên thứ ba nếu không cần.
- Khi parent đóng hoặc popup không liên lạc được, hủy flow an toàn.

Cross-Origin-Opener-Policy, popup blockers và browser behavior có thể ảnh hưởng thiết kế. **Dùng SDK đã xử lý các góc cạnh này** nếu sản phẩm không chủ đích triển khai giao thức tương tác cửa sổ.

## 14. Native mobile: OS có thể kill app khi browser login

Native app nên dùng external/system browser theo [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252). OS có thể dừng app khi user đang nhập MFA ở browser; callback qua App Link/Universal Link/custom scheme sau đó mở một process mới.

### iOS/iPadOS

- Khi process vẫn sống: giữ verifier trong memory/authorization session object và xóa sau exchange.
- Khi cần survive termination: lưu một **Keychain item tạm** với access class phù hợp, chẳng hạn `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` cho flow foreground; gắn state + issuer + expiry.
- Không lưu trong `UserDefaults` hoặc file plaintext.
- Keychain có thể tồn tại qua uninstall/reinstall ở một số trường hợp; cleanup bằng TTL, account/session binding và first-run logic để tránh dùng stale verifier.
- Nếu restore sang thiết bị khác làm item không còn, **bắt đầu login mới**, không lấy verifier từ URL.

### Android

- Khi không cần survive process death: giữ verifier memory.
- Khi cần persist: mã hóa record bằng authenticated encryption với key trong **Android Keystore**, lưu ciphertext trong app-private storage; có TTL và backup exclusion phù hợp.
- Không ghi raw verifier vào `SharedPreferences`/DataStore, deep link URI, `Intent` extras hoặc `SavedStateHandle` như chiến lược lưu secret mặc định.
- Khi restore ciphertext mà key không có, hoặc key invalidated, **không fallback plaintext**; xóa transaction và restart login.
- Nếu nhiều Activity/process, repository cần lookup/consume đúng state có đồng bộ.

**Refresh token và PKCE verifier khác vòng đời.** Refresh token có thể được lưu dài hạn theo grant policy; verifier chỉ tồn tại qua **một authorization code flow**, không được backup/migrate nhiều ngày.

## 15. Kotlin: contract cho protected ephemeral transaction storage

Ví dụ Kotlin cho mobile callback. Interface `ProtectedTransactionStore` phải được triển khai bằng secure mechanism của platform; **đoạn mã không tự mã hóa**.

~~~kotlin
import java.time.Clock
import java.time.Instant

data class PendingPkce(
    val state: String,
    val verifier: String,
    val expectedIssuer: String,
    val clientId: String,
    val redirectUri: String,
    val expiresAt: Instant
)

interface ProtectedTransactionStore {
    suspend fun save(pending: PendingPkce)
    suspend fun takeOnce(state: String): PendingPkce?
    suspend fun deleteExpired(now: Instant)
}

sealed interface CallbackDecision {
    data class Continue(val transaction: PendingPkce) :
        CallbackDecision

    data object RestartAuthorization : CallbackDecision
}

suspend fun resolveCallback(
    stateFromRedirect: String?,
    issuerFromRedirect: String?,
    store: ProtectedTransactionStore,
    clock: Clock
): CallbackDecision {
    if (stateFromRedirect.isNullOrBlank()) {
        return CallbackDecision.RestartAuthorization
    }

    val pending = store.takeOnce(stateFromRedirect)
        ?: return CallbackDecision.RestartAuthorization

    if (clock.instant() >= pending.expiresAt) {
        return CallbackDecision.RestartAuthorization
    }

    // Nếu AS bắt buộc RFC 9207 iss, kiểm tra cả trường hợp thiếu.
    if (issuerFromRedirect != null &&
        issuerFromRedirect != pending.expectedIssuer
    ) {
        return CallbackDecision.RestartAuthorization
    }

    return CallbackDecision.Continue(pending)
}
~~~

Bên xử lý `Continue` còn phải:

1. Kiểm tra redirect URI/client/context và issuer theo profile.
2. Đổi code **tại token endpoint đã đăng ký của issuer** với `pending.verifier` qua HTTPS.
3. Với OIDC, kiểm tra ID token/nonce sau response; với API dùng access token đúng audience/scope.
4. Không log code, verifier hoặc token; không cho callback thứ hai reuse record.
5. Nếu missing/expired, bắt đầu flow mới với state/verifier mới.

**`takeOnce` phải nguyên tử** nếu nhiều callback/process có thể cạnh tranh. Hợp đồng này không tự xử lý lỗi mạng, rollback storage, refresh token hoặc AS single-use code; đó là những lớp riêng.

## 16. Desktop native và loopback callback

Ứng dụng desktop có thể mở browser ngoài rồi nhận callback qua loopback redirect hoặc URI scheme theo profile. Nếu app bị đóng giữa flow, memory-only verifier biến mất.

- Nếu sản phẩm chấp nhận restart login: giữ verifier memory và bắt đầu transaction mới sau crash.
- Nếu cần phục hồi: OS credential store/encrypted app-private state ngắn hạn, không lưu trong plaintext config, command-line args hoặc URI.
- Listener callback phải kiểm tra **state + expected issuer + redirect** trước khi dùng verifier.
- Nhiều app windows/instances cần định danh transaction owner.
- Không dùng verifier sau khi đã có access token/refresh token để “đăng nhập nhanh” những lần sau.

**Không biến code_verifier thành khóa đăng nhập dài hạn**. PKCE được thiết kế cho **một vòng code exchange**, không phải session credential.

## 17. Khi nào xóa verifier và xử lý lỗi thế nào?

| Tình huống | Hành động với transaction | Lý do |
|---|---|---|
| Callback state/issuer sai | Không dùng verifier, xử lý deny/cleanup theo policy | Chặn CSRF/mix-up |
| Callback trả `error` | Dọn flow liên quan | Không có code để exchange |
| Code exchange thành công | Xóa verifier và record | Không cần dùng lại |
| AS trả `invalid_grant` | Dọn; tạo authorization flow mới khi cần | Code đã dùng/hết hạn/PKCE sai |
| Token request timeout | Không mặc định retry cùng code | AS có thể đã tiêu thụ code |
| User cancel login | Dọn nếu app biết; TTL dọn khi bỏ dở | Tránh stale records |
| Logout/switch account | Dọn pending flows gắn phiên/account | Không cho callback cũ đăng nhập nhầm |
| App restart | Khôi phục chỉ nếu TTL/context hợp lệ | Không dùng stale verifier |
| Backup/restore | Nếu key/context không hợp lệ, restart login | Không hạ cấp storage |
| Duplicate callback | Chỉ một handler lấy được record | Không gửi code hai lần |

**Không dọn quá sớm:** nếu xóa record trước khi lấy verifier vào memory cho token exchange, flow hợp lệ thất bại. **Không dọn quá muộn:** callback đã xử lý xong không cần giữ verifier qua ngày.

### TTL của client transaction

RFC 7636 không ấn định TTL của **verifier storage phía client**. Ví dụ 5 phút là **policy minh họa**. Thời gian người dùng nhập MFA/consent diễn ra **trước khi AS phát code**, nên không được nhầm TTL transaction với code TTL.

Cần giới hạn số record pending, dọn expired lúc app startup, ghi reason codes an toàn và tạo transaction mới nếu đã hết thời hạn.

## 18. Các anti-pattern cần tránh

**Đặt verifier trong `state`, query hoặc fragment.** `state` đi qua front channel và có thể bị log; Base64 hay obfuscation không làm verifier bí mật. Không “mã hóa tạm” vào URL trừ một kiến trúc được kiểm toán nghiêm ngặt; thông thường nên tránh.

**Gửi verifier ở `/authorize`.** Authorization request chỉ nên mang challenge; verifier gốc dùng ở `/token`.

**Dùng cùng verifier cho mọi lần login.** Vi phạm mục tiêu transaction-scoped, tăng hậu quả nếu lộ và gây confusion nhiều tab.

**Chuyển verifier giữa tab qua localStorage dài hạn.** Dữ liệu dễ sống quá lâu và bị script cùng origin đọc. Dùng SDK/cấu trúc popup hoặc restart flow.

**Lưu verifier chung với refresh token dài hạn.** Hai hiện vật có threat model và lifetime khác nhau. Không cần giữ verifier sau khi refresh token đã được cấp.

**Dùng `code_challenge` thay verifier.** AS sẽ tính S256 sai; không thể khôi phục verifier từ challenge.

**Bỏ PKCE khi không tìm thấy verifier.** Đây là downgrade nguy hiểm. Flow phải fail closed hoặc bắt đầu authorization mới.

**Nhầm storage an toàn với API authorization.** Sau token issuance, Resource Server vẫn kiểm tra JWT signature/claims hoặc opaque introspection, issuer, audience, scope và object/tenant policy. Verifier tốt không tự cho user quyền đọc mọi dữ liệu.

## 19. Logging, telemetry và backup

Verifier có thể bị lộ ngoài storage qua debug tooling hoặc SDK thu thập dữ liệu. Không log:

- Raw `code_verifier`, authorization code, access/refresh/ID token, client secret, raw token endpoint body.
- `state`/`nonce` đầy đủ hoặc serialized pending transaction khi không cần.
- Full URL callback, JavaScript state dump, network interceptor output, HAR production có credential.
- App crash data/analytics được phép tự chụp `sessionStorage` hoặc request payload nhạy cảm.
- Mobile cloud backup chứa pending transaction hoặc key material.

Thay bằng **audit allowlist**: transaction reference pseudonym, issuer/client được xác minh, PKCE method, outcome, latency, error category, timestamp. Ví dụ JSON **không có verifier**:

~~~json
{
  "event_type": "oauth.pkce.transaction.completed",
  "occurred_at": "2026-11-23T10:02:15Z",
  "client_id": "orders-web",
  "issuer": "https://auth.example.test",
  "transaction_ref": "tx-pseudo-72",
  "pkce_method": "S256",
  "storage_kind": "server_session",
  "outcome": "SUCCESS",
  "raw_verifier_logged": false
}
~~~

Trường `raw_verifier_logged=false` là **mô tả minh họa**, không chứng minh hệ thống logs toàn bộ an toàn. Phải kiểm thử bằng canary giả ở CDN, proxy, APM, SDK analytics, mobile logs và crash reporting.

**Backup/restore:** PKCE verifier không cần đồng bộ xuyên thiết bị. Nếu bị mất sau restore, khởi tạo authorization flow mới hợp lý hơn việc hạ cấp bí mật.

## 20. Case study: SPA hai tab và mobile process death

Giả sử `orders-spa` và `orders-mobile` cùng dùng AS `https://auth.example.test` để xin access token scope `orders:read` cho Orders API.

### Trường hợp SPA

| Lúc | Sự kiện | Một key global (sai) | State-keyed transaction (đúng) |
|---|---|---|---|
| 10:00 | Tab A tạo state SA/verifier VA | Ghi `pkce.verifier=VA` | Lưu record SA → VA |
| 10:01 | Tab B tạo state SB/verifier VB | Ghi đè key thành VB | Lưu record SB → VB riêng |
| 10:02 | Callback A trở lại | Dùng VB, `invalid_grant` | Dùng VA từ SA đúng context |
| 10:03 | Callback B trở lại | Verifier bị lẫn/xóa | Dùng VB từ SB |
| 10:04 | Callback A reload | Retry code đã dùng | Record A consumed, không replay |

Nếu hai tab có `sessionStorage` riêng, chúng **không tự chia sẻ** verifier. Điểm cốt lõi vẫn là **context ownership và state binding**, không chỉ cấu trúc key.

### Trường hợp mobile

| Lúc | Sự kiện | Chỉ memory | Protected temporary storage |
|---|---|---|---|
| 10:00 | App tạo SM/VM, mở browser | VM còn | Lưu record trước browser |
| 10:01 | OS hủy app | VM mất | Ciphertext record có thể còn |
| 10:02 | Callback mở process mới | Không exchange được | Lấy đúng SM nếu TTL/context đúng |
| 10:03 | AS cấp token | Phải restart flow | Xóa VM; lưu token theo policy riêng |
| 10:04 | Device restore không có encryption key | Không record | Không decrypt, restart login |

**Bài học:** secure temporary storage chỉ giúp **hoàn tất một authorization transaction**. Không được coi verifier như phương tiện đăng nhập dài hạn hoặc tự gia hạn code đã hết hạn.

## 21. Ma trận kiểm thử verifier storage

| Test | Đầu vào/thao tác | Kết quả mong đợi |
|---|---|---|
| **T1 — Randomness** | Sinh verifier cho 100 flow test | Mỗi verifier khác nhau, đúng 43–128 chars, CSPRNG |
| **T2 — S256 vector** | Test vector RFC 7636 | Challenge đúng Base64url(SHA256(ASCII(verifier))) |
| **T3 — Store before redirect** | Redirect ngay sau tạo verifier | Record tồn tại trước navigation |
| **T4 — No verifier in URL** | Inspect `/authorize`, callback | Chỉ có challenge, không có raw verifier |
| **T5 — BFF cookie** | Inspect browser cookie/session | Không có raw verifier client-side |
| **T6 — BFF cross-session** | State A trên browser session B | Không lấy được verifier A |
| **T7 — SPA redirect** | Callback cùng tab sau full reload | Lấy đúng transaction nếu chưa hết hạn |
| **T8 — SPA XSS test** | Kiểm tra khả năng JS đọc sessionStorage trong staging | Ghi nhận rủi ro, không tuyên bố secret chống XSS |
| **T9 — Multi-tab** | Hai flow đồng thời | Không ghi đè hoặc đổi chéo verifier |
| **T10 — Popup origin** | Giả postMessage từ origin/source lạ | Parent từ chối |
| **T11 — Missing record** | Callback có state nhưng không có record | Fail closed; không generate verifier mới cho code cũ |
| **T12 — Expired transaction** | Callback sau client TTL | Từ chối/cleanup |
| **T13 — Duplicate callback** | Hai callback cùng state | At most one consume; không đổi code hai lần |
| **T14 — Wrong issuer** | Response từ AS khác | Không gửi verifier sang endpoint lạ |
| **T15 — Wrong client/redirect** | Metadata callback bị tráo | Client/AS từ chối |
| **T16 — PKCE mismatch** | Token request dùng verifier sai | AS từ chối `invalid_grant` |
| **T17 — Android process death** | Kill app khi system browser login | Khôi phục an toàn hoặc restart |
| **T18 — iOS termination** | Callback mở app process mới | Lookup đúng record hoặc restart |
| **T19 — Backup without key** | Restore ciphertext sang device mới | Không fallback plaintext |
| **T20 — Token request timeout** | AS có thể đã consume code | Không retry vô hạn bằng code cũ |
| **T21 — Logout/account switch** | Thay user khi pending flow | Không dùng verifier của user cũ |
| **T22 — Log canary** | Verifier giả trong staging | Không lộ trong log/APM/analytics |
| **T23 — Stale cleanup** | User bỏ dở nhiều flow | TTL và giới hạn số records |
| **T24 — Refresh grant** | Xin access token bằng refresh token sau login | Không dùng lại PKCE verifier cũ |
| **T25 — API validation** | Access token sai audience/scope | API từ chối dù PKCE thành công |

**Không đưa verifier/code/token production thật** vào HAR, CI log, screenshot hay security-test report; dùng staging/canary giả.

## 22. Checklist triển khai

1. **Sinh verifier ngẫu nhiên mới cho từng flow** từ CSPRNG, đúng 43–128 unreserved chars, ưu tiên S256.
2. **Gửi challenge trong authorization request**, giữ verifier gốc chỉ để POST tới token endpoint.
3. **Không cho verifier vào URL, state, nonce, logs, analytics, exception, JS global debug hoặc persistent config**.
4. **Lưu transaction theo state + browser/app context**, gắn client, issuer, redirect, timestamp và nonce OIDC nếu dùng.
5. **Phân biệt client transaction TTL với code lifetime của AS**; code chỉ tồn tại sau issuance.
6. **BFF:** giữ verifier server-side, cookie giữ opaque session ID có Secure/HttpOnly/SameSite phù hợp.
7. **SPA:** dùng SDK transaction store ngắn hạn, `sessionStorage` khi cần qua redirect; hiểu rõ XSS, origin/tab và popup.
8. **Mobile/desktop:** ưu tiên memory; khi cần survive restart, dùng OS protected temporary storage và backup exclusions.
9. **Lưu record trước navigation** và consume một lần đúng state/session; đa node/process cần atomicity.
10. **Kiểm tra issuer/token endpoint/redirect context**, không tin URL do callback cung cấp để chọn AS.
11. **Không fallback khi thiếu verifier**: không đổi code cũ với verifier mới, không hạ cấp `plain`/không PKCE.
12. **Dọn transaction đúng lúc:** success, failure, cancel, logout, account switch, expired.
13. **Giảm thời gian sống secret trong memory**, không sao chép sang request/log ngoài token endpoint.
14. **Xử lý code replay/response lost** theo policy, thường restart authorization flow; không retry vô hạn.
15. **Bảo vệ token sau khi cấp** bằng storage/TTL/rotation/revoke riêng; API vẫn phải kiểm tra issuer, audience, scope, object policy.
16. **Kiểm thử negative paths**: XSS, cross-session/issuer/tab, duplicate callback, process death, restore và logging leak.

**Kết luận:** `code_verifier` cần tồn tại **từ lúc client khởi tạo PKCE cho đến khi đổi authorization code**, không lâu hơn. Lưu đúng nơi tùy kiến trúc: **BFF giữ server-side**, **SPA dùng transaction storage ngắn hạn và chấp nhận/giảm rủi ro XSS**, **mobile/desktop dùng memory hoặc protected temporary storage khi cần qua process restart**. Điều quan trọng nhất là **một verifier gắn đúng một state/issuer/client/redirect**, được consume đúng giao dịch và xóa kịp thời.

### Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): verifier, S256, flow và chống code interception.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): PKCE, chống downgrade, token security.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code flow, state và token endpoint.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external browser và redirect native.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer binding và chống AS mix-up.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC ID token và nonce.
- [MDN — Window.sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage): tab/origin và vòng đời session storage.
- [MDN — Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API): CSPRNG và SHA-256.
- [Apple — Keychain Services](https://developer.apple.com/documentation/security/keychain-services): lưu bí mật tạm trên iOS.
- [Android Developers — Keystore](https://developer.android.com/privacy-and-security/keystore): bảo vệ khóa mã hóa dữ liệu.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): kiểm soát OAuth client.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): giới hạn Web Storage.
