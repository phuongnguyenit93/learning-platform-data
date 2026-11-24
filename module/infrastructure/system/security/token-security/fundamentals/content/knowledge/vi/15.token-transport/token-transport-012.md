# Xóa token khỏi URL referrer

Trong OAuth 2.0/OpenID Connect (OIDC), **token là thông tin bảo mật**, kể cả khi chuỗi chỉ có vẻ như dữ liệu ngẫu nhiên hoặc Base64url. Một **bearer access token** có thể được bên giữ bản sao dùng để gọi Resource Server trong phạm vi `aud`, `scope` và thời gian được cấp; một **refresh token** có thể giúp xin access token mới theo authorization grant. Vì thế, **đặt token trong URL** có thể làm lộ credential qua nhiều đường: lịch sử trình duyệt, request log, công cụ phân tích, bản ghi crash, liên kết chia sẻ và đặc biệt là header HTTP **`Referer`**.

Bài học **“Xóa token khỏi URL referrer”** thuộc chương **Token transport** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối vòng đời token, JWT/opaque, access/refresh token, OAuth 2.0/OIDC, issuer, audience, scope, lưu trữ, thu hồi và chống đánh cắp/phát lại. Mục tiêu là biết **phòng ngừa URL chứa credential từ đầu**, cấu hình **`Referrer-Policy`**, làm sạch callback an toàn và kiểm chứng bằng mạng/log rằng URL nhạy cảm không tiếp tục bị truyền đi.

**Nguyên tắc cốt lõi:** **không gửi access token hoặc refresh token trong URL** của ứng dụng/API thông thường. Với OAuth mới, ưu tiên **Authorization Code + PKCE**, exchange code tại token endpoint, không dùng implicit flow trả access token qua front channel. Đối với URL callback có **authorization code** một lần dùng, hãy xử lý giao dịch đúng chuẩn và **chuyển ngay sang URL sạch**, đồng thời bảo vệ log, lịch sử, tài nguyên bên thứ ba và các redirect.

> **Điểm dễ nhầm:** phần **fragment** sau dấu `#` thường **không được gửi trong HTTP request hoặc header `Referer`**, nhưng vẫn có thể bị JavaScript đọc và xuất hiện trong lịch sử/telemetry. Không đặt token trong fragment chỉ vì nó không có mặt trong `Referer`.

## 1. Phân biệt URL, Referer và Referrer-Policy

Giả sử một trình duyệt đang mở:

~~~text
https://app.example.test/auth/callback?code=AUTH_CODE&state=STATE#section
|---- origin -----------|------ path ------|---- query ---------|fragment
~~~

- **Origin** gồm scheme, host và port (nếu khác mặc định): `https://app.example.test`.
- **Path** là `/auth/callback`.
- **Query** bắt đầu sau `?`: ở ví dụ này có `code` và `state`.
- **Fragment** bắt đầu sau `#`: `section`. Fragment được trình duyệt xử lý ở phía client; **không nằm trong request-target HTTP** khi trình duyệt truy cập URL theo cơ chế thông thường.

Khi trang tải ảnh, script, CSS, iframe hoặc người dùng nhấn liên kết, trình duyệt có thể gửi header:

~~~http
GET /collect HTTP/1.1
Host: metrics.example.test
Referer: https://app.example.test/
~~~

**`Referer`** (viết thiếu một chữ “r” theo tên header HTTP lịch sử) cho bên nhận biết trang/URL giới thiệu request. **`Referrer-Policy`** (viết đúng “referrer”) là **response header** hoặc chính sách HTML kiểm soát **bao nhiêu thông tin URL được đưa vào `Referer` của những request tiếp theo**.

Bảng phân biệt:

| Thành phần | Ai tạo/sử dụng? | Có thể chứa token? | Lưu ý |
|---|---|---|---|
| URL trên thanh địa chỉ | Browser, người dùng, ứng dụng | Có nếu thiết kế sai | Lộ qua lịch sử, copy/paste, ảnh chụp và telemetry |
| HTTP request path/query | Browser gửi tới máy chủ đích | Có nếu token nằm ở path/query | Có thể bị access log, reverse proxy, APM và CDN lưu |
| URL fragment (`#...`) | Browser/client-side script | Có trong flow cũ như implicit | Thường không gửi tới máy chủ qua HTTP, cũng **không nằm trong Referer**, nhưng JS có thể đọc |
| HTTP `Referer` | Browser gửi khi điều hướng/tải tài nguyên | Có thể chứa **path/query** tùy policy | Không mặc định an toàn cho secret |
| HTTP `Referrer-Policy` | Server/trang đặt chính sách | Không phải nơi chứa token | Giảm thông tin truyền qua `Referer`; không xóa lịch sử hoặc log request gốc |

Tên field **`Referer`** và **`Referrer-Policy`** khác nhau là **cố ý theo tiêu chuẩn thực tế**, không phải lỗi đánh máy. Cấu hình nhầm `Referer-Policy` sẽ không đạt hành vi mong muốn.

## 2. Token trong URL bị lộ qua những con đường nào?

Giả sử API/website có URL **không an toàn**:

~~~text
https://app.example.test/account?access_token=ACCESS_TOKEN_SECRET
~~~

Bản thân URL có thể đi qua nhiều thành phần:

~~~mermaid
flowchart TD
    U["Browser mở URL có token trong query/path"] --> W["Máy chủ / CDN / proxy ghi request URL"]
    U --> H["Browser history / bookmark / copy-paste"]
    U --> R["Tải resource hoặc click link"]
    R --> P["Header Referer tùy Referrer-Policy"]
    U --> J["JavaScript, analytics, error reporting"]
    W --> L["Access log, APM, SIEM"]
    P --> T["Bên nhận Referer có thể ghi URL"]
    H --> X["Người khác hoặc thiết bị đồng bộ"]
    J --> Y["SDK/third-party collector"]
~~~

| Đường rò | Dữ liệu có thể lộ | Cần chặn ở đâu? |
|---|---|---|
| **Truy cập URL ban đầu** | Query/path trong request line, CDN/gateway/server log | Không thiết kế token trong URL; redact hoặc bỏ log raw URL |
| **Same-origin subresource/navigation** | `Referer` có thể chứa path/query gốc theo policy mặc định hiện đại | `Referrer-Policy: no-referrer` ở trang nhạy cảm |
| **Cross-origin subresource/navigation** | Tùy policy: full URL, origin hoặc không có gì | Cấu hình policy và hạn chế tài nguyên bên thứ ba |
| **Browser history/bookmark/sync** | URL gồm cả query/fragment | Dùng URL sạch và `history.replaceState`/server redirect sớm |
| **JavaScript/analytics/SDK** | `window.location.href` có query và fragment | Không chạy SDK trước khi làm sạch; tránh collect full URL |
| **HTTP proxy/APM/crash log** | Path/query, header, stack context | Allowlist trường log, redact token/code/state và không log `Authorization` |
| **Link preview/chat/support** | Người dùng hoặc app khác chia sẻ URL có token | Không cung cấp URL có token; thu hồi nếu đã lộ |
| **Redirect chain** | URL có credential được đưa vào `Location` hoặc request đích | Không đưa token/code vào `Location` sau khi xử lý callback |

**HTTPS rất cần thiết nhưng không giải quyết tất cả.** TLS bảo vệ dữ liệu trên đường truyền khỏi nhiều bên nghe lén, **không** ngăn chính browser, server, reverse proxy, app analytics hoặc người đã nhận một URL bí mật ghi lại nó.

## 3. Cơ chế `Referer`: query có thể đi, fragment thì không

Lấy URL nguồn:

~~~text
https://app.example.test/callback?code=ONE_TIME_CODE&state=RANDOM_STATE#access_token=LEGACY_TOKEN
~~~

Trong trình duyệt hiện đại, chính sách mặc định thường là **`strict-origin-when-cross-origin`** (nhưng không nên giả định mọi browser, WebView hay máy chủ đều giống nhau).

| Request từ trang nguồn | Referer với `strict-origin-when-cross-origin` thường như thế nào? |
|---|---|
| Tới `https://app.example.test/assets/app.js` (**cùng origin**) | `https://app.example.test/callback?code=ONE_TIME_CODE&state=RANDOM_STATE` |
| Tới `https://metrics.example.test/collect` (**khác origin, HTTPS**) | `https://app.example.test/` |
| Tới `http://legacy.example.test/` (**HTTPS → HTTP**) | Thường không gửi `Referer` |
| Tới bất kỳ đích nào với `no-referrer` | Không gửi header `Referer` |

**Fragment `#access_token=LEGACY_TOKEN` không nằm trong các giá trị `Referer` trên** vì fragment bị loại khỏi Referer theo quy tắc browser. Tuy nhiên, script chạy trong trang vẫn có thể đọc `window.location.hash` hoặc `window.location.href`; hệ thống analytics cũng có thể thu toàn URL ở phía JavaScript. Vì thế fragment **không phải kho bí mật**.

**Lưu ý quan trọng:** policy mặc định chỉ làm giảm một số đường lộ *cross-origin*. Với request **same-origin**, nó có thể vẫn đưa **cả path/query** vào `Referer`. Nếu URL hiện tại chứa authorization code, những subrequest đến asset/API cùng origin có thể làm code xuất hiện trong log khác.

## 4. Chính sách Referrer-Policy nào phù hợp?

Những giá trị thường gặp:

| Policy | Hành vi cơ bản | Có phù hợp trang callback nhạy cảm? |
|---|---|---|
| **`no-referrer`** | Không gửi `Referer` khi trang tạo request/điều hướng | **Có, lựa chọn chặt nhất** cho callback/error page có khả năng nhận thông tin nhạy cảm |
| **`same-origin`** | Gửi URL nguồn cho request cùng origin; bỏ header khi khác origin | **Chưa đủ** nếu query có code/token và same-origin log được thu |
| **`origin`** | Chỉ gửi origin, không path/query | Giảm rò query, nhưng vẫn tiết lộ origin |
| **`strict-origin`** | Chỉ gửi origin khi mức bảo mật không giảm; HTTPS → HTTP không gửi | Hữu ích cho nhiều trang nhưng không chặt bằng `no-referrer` |
| **`strict-origin-when-cross-origin`** | Same-origin: full URL; cross-origin: origin nếu không downgrade | Mặc định phổ biến, **chưa đủ** để bảo vệ query nhạy cảm trong same-origin |
| **`no-referrer-when-downgrade`** | Có thể gửi full URL tới cả cross-origin HTTPS, không gửi khi downgrade | **Không phù hợp** nếu URL có secrets |
| **`unsafe-url`** | Có thể gửi đầy đủ path/query cho nhiều đích | **Không sử dụng** trên trang có dữ liệu URL nhạy cảm |

Ví dụ server trả trang callback hoặc trang trung gian nhạy cảm:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Content-Security-Policy: default-src 'none'; script-src 'self'; base-uri 'none'; form-action 'self'
~~~

Ý nghĩa:

- **`Referrer-Policy: no-referrer`** giảm rò URL nguồn qua **request sau đó** của trang.
- **`Cache-Control: no-store`** hạn chế response bị lưu cache; **không** tự xóa URL khỏi history hoặc request log đã có.
- **CSP** giúp giảm tài nguyên/script không được cho phép; cần hiệu chỉnh theo ứng dụng thực tế. CSP **không thay thế việc bỏ token khỏi URL**.

Có thể đặt meta khi không kiểm soát được header:

~~~html
<meta name="referrer" content="no-referrer">
~~~

Nhưng **response header thường tốt hơn**, vì meta chỉ có hiệu lực sau khi browser parse tới nó; resource/script tải trước đó có thể đã phát request. Nếu cần kiểm soát một liên kết ra ngoài:

~~~html
<a href="https://docs.example.test/" rel="noreferrer">Tài liệu</a>
~~~

`rel=noreferrer` là hàng rào bổ sung cho liên kết đó; không giải quyết toàn bộ subresource, XHR, log máy chủ và history. `referrerpolicy="no-referrer"` trên `<a>`/`<img>` cũng có phạm vi phần tử tương tự.

## 5. Ngăn từ nguồn: không truyền access/refresh token trong URL

Theo OAuth 2.0 Bearer Token Usage (RFC 6750), cách thông dụng để gọi API là **`Authorization` header** qua HTTPS:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

**Không dùng**:

~~~http
GET /orders/123?access_token=<ACCESS_TOKEN> HTTP/1.1
Host: orders-api.example.test
~~~

Trong trường hợp ngoài ý muốn, một số giao thức/legacy API vẫn đưa token trong query. Nhưng **Bearer URI query method có nhiều rủi ro và không được khuyến khích**; chỉ dựa vào `Referrer-Policy` hay URL encoding không làm nó thành an toàn.

**Phân biệt các kênh:**

- **Access token:** gửi cho Resource Server đúng audience theo scheme đã được AS/RS hỗ trợ, phổ biến nhất `Authorization: Bearer`. Với DPoP-bound token, dùng `Authorization: DPoP` kèm proof theo profile, không đổi sang Bearer thuần.
- **Refresh token:** gửi **chỉ tới AS token endpoint** trong request phù hợp (thường là form body POST qua TLS, với client authentication/binding cần thiết), **không gửi cho API nghiệp vụ**.
- **ID token (OIDC):** dùng cho OIDC client để xác minh sự kiện authentication; **không thay access token**, không đưa vào URL để chia sẻ.
- **Authorization code:** được truyền qua OAuth redirect theo flow phù hợp và **dùng một lần**, vẫn là hiện vật nhạy cảm cần che khỏi log/Referer.
- **Cookie phiên:** nếu kiến trúc BFF/server session, dùng cookie có `Secure`, `HttpOnly` và `SameSite` phù hợp, cùng CSRF/session security; **không chuyển session ID sang URL**.

### Ví dụ hệ thống bị thiết kế sai

~~~text
User mở:
  https://app.example.test/dashboard?token=<ACCESS_TOKEN>

Trang tải:
  https://app.example.test/assets/chart.js

Referer theo policy same-origin mặc định có thể chứa:
  https://app.example.test/dashboard?token=<ACCESS_TOKEN>

Proxy ghi raw Referer -> nhiều bản sao bearer token xuất hiện trong log.
~~~

Giải pháp **đúng gốc** là không phát sinh đường link dashboard có token. Chuyển token sang kênh bảo mật phù hợp, thay thế toàn bộ link, xóa khỏi cache/history nơi có thể, redact log và xử lý revocation nếu token đã bị lộ.

## 6. OAuth Authorization Code + PKCE giảm nguy cơ front-channel token

Trong flow **Authorization Code + PKCE**, browser nhận **authorization code** qua redirect, sau đó client đổi code thành token tại **token endpoint**. Access token và refresh token **không cần xuất hiện trong URL của browser**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant C as Client / BFF
    participant AS as Authorization Server
    participant API as Resource Server

    C->>C: Tạo state và PKCE verifier/challenge
    C-->>B: Chuyển tới AS /authorize
    B->>AS: Authorization request + code_challenge S256
    AS->>U: Xác thực / consent theo chính sách
    AS-->>B: Redirect_uri?code=CODE&state=STATE
    B->>C: GET /auth/callback?code=...&state=...
    C->>C: Kiểm tra state, issuer/flow context
    C->>AS: POST /token + code + code_verifier + client auth nếu cần
    AS->>AS: Kiểm tra code/client/PKCE/redirect
    AS-->>C: Access token (+ refresh/ID token nếu có)
    C-->>B: 303 See Other -> /app (URL sạch)
    B->>C: GET /app với session cookie an toàn
    C->>API: Access token qua Authorization header
~~~

**Authorization code không phải access token**, nhưng vẫn cần bảo vệ: code có thời hạn ngắn, dùng một lần, gắn với client/redirect, PKCE S256, `state` được kiểm tra, và chống mix-up với nhiều AS. Nếu code lộ, attacker chỉ khai thác được khi đáp ứng các ràng buộc cần thiết, nhưng vẫn phải xử lý nó như dữ liệu nhạy cảm.

Khi backend là **confidential client**, client authentication tại token endpoint (secret/private_key_jwt/mTLS theo registration) bổ sung một lớp bảo vệ; nó không thay PKCE hoặc việc kiểm tra grant. Với native app/SPA là **public client**, không hardcode client secret trong app rồi xem là bảo mật.

### Cách xử lý callback

1. Browser vào callback qua HTTPS với `code` và `state` trong query theo response mode.
2. **Không phục vụ trang callback chứa analytics, font/script bên thứ ba** trước khi loại bỏ dữ liệu nhạy cảm.
3. Client/BFF kiểm tra `state` đúng authorization transaction đã tạo, issuer/AS tương ứng nếu cần, code chưa bị dùng lại và các ràng buộc redirect.
4. Đổi code với PKCE verifier còn giữ bí mật phù hợp tại token endpoint. Không ghi code/verifier/token vào log.
5. **Đưa trình duyệt sang URL sạch**, thường bằng `303 See Other` với `Location` **không chứa code, state, token**.
6. Nếu callback do SPA xử lý bằng JavaScript, **`history.replaceState` sớm** sau khi giữ tạm các tham số cần thiết trong bộ nhớ, trước khi tải thêm SDK/third-party.
7. Xử lý access/refresh token theo kiến trúc storage tin cậy; không dùng query/hash của trang ứng dụng để giữ token.

**Không viết logic “đợi tải xong analytics rồi mới xóa code”.** Kể cả với URL chỉ chứa code, mục tiêu là giảm tối đa thời gian giá trị nhạy cảm xuất hiện trong các bề mặt có thể quan sát.

## 7. Backend/BFF: POST đổi code, rồi 303 sang URL sạch

Kiến trúc BFF cho phép browser chỉ giữ **cookie phiên ứng dụng**, còn access/refresh token nằm phía backend. Một mẫu callback:

~~~http
GET /auth/callback?code=<ONE_TIME_CODE>&state=<STATE> HTTP/1.1
Host: app.example.test
~~~

Sau khi kiểm tra và xử lý thành công, server trả:

~~~http
HTTP/1.1 303 See Other
Location: /app
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Set-Cookie: session=<SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ở response này:

- `Location: /app` **không** chứa `code`, `state` hay token; browser điều hướng đến URL sạch.
- Cookie phiên không được nhúng vào `Location`, URL, HTML hoặc log.
- `Referrer-Policy: no-referrer` và `Cache-Control: no-store` hỗ trợ giảm rò/ghi cache.
- OAuth backend **phải** kiểm tra `state`/PKCE/redirect/issuer theo context và quản lý cookie session chống CSRF, session fixation và tấn công liên quan.
- Một browser có thể đã gửi URL query tới backend **trước response 303**. Vì thế proxy/CDN/server phải **không log raw query** của callback hoặc phải redact trường nhạy cảm. Redirect **không hoàn tác** những bản log đã ghi.

### Java Spring Boot minh họa

Ví dụ Java 17/Spring MVC dưới đây thể hiện **ràng buộc callback và redirect sạch**. `CallbackExchangeService` là interface nội bộ giả định, không phải lớp OAuth tiêu chuẩn; implementation thực tế phải dùng thư viện OAuth/OIDC có bảo trì.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OAuthCallbackController {
    private final CallbackExchangeService callbackService;

    public OAuthCallbackController(
            CallbackExchangeService callbackService
    ) {
        this.callbackService = callbackService;
    }

    @GetMapping("/auth/callback")
    public ResponseEntity<Void> callback(
            @RequestParam("code") String code,
            @RequestParam("state") String state,
            HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid callback"
            );
        }

        // Service phải xác minh state/context, PKCE verifier, issuer,
        // client registration, exchange code và lưu session an toàn.
        // Tuyệt đối không log code, state, verifier hoặc token.
        callbackService.finishAndExchange(code, state, session);

        // Browser nhận URL sạch; không đưa code/token vào Location.
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/app"))
                .cacheControl(CacheControl.noStore())
                .header("Referrer-Policy", "no-referrer")
                .header("Pragma", "no-cache")
                .build();
    }

    public interface CallbackExchangeService {
        void finishAndExchange(
                String code, String state, HttpSession session
        );
    }
}
~~~

**Giới hạn ví dụ:** service cần xác thực `state` với transaction lưu server-side, PKCE code verifier, chống replay, issuer/mix-up và xử lý lỗi theo flow; không triển khai ở snippet. Cần cấu hình cookie an toàn, CSRF cho BFF, timeout, error page không lộ query và log redaction. `/auth/callback` trả `400` khi thiếu tham số hoặc state sai phải dùng **error handler không in raw URL**. Nếu session không đủ an toàn, 303 và cookie có `HttpOnly` cũng không giải quyết session hijacking.

Nếu dùng OAuth/OIDC framework đã quản lý callback, nên cấu hình **success handler/redirect** của framework và log policy; tránh tự viết lại giao thức chỉ để xóa URL.

## 8. SPA: dùng history.replaceState sớm, nhưng không gọi nó là phòng vệ duy nhất

Một SPA public client có thể nhận authorization code tại URL callback rồi đổi code qua OAuth SDK với PKCE. Vì JavaScript nhìn thấy URL, cần giữ logic callback **tối thiểu và chạy trước các SDK khác**.

Ví dụ minh họa thao tác dọn URL:

~~~javascript
// Ví dụ xử lý ở entrypoint callback, trước analytics và third-party code.
// Hàm finishOAuthTransaction là API GIẢ ĐỊNH của lớp OAuth SDK nội bộ.
// Nó phải kiểm tra state/PKCE/issuer và đổi code theo hợp đồng AS.

async function handleCallback() {
    const callbackUrl = new URL(window.location.href);
    const code = callbackUrl.searchParams.get("code");
    const state = callbackUrl.searchParams.get("state");
    const error = callbackUrl.searchParams.get("error");

    // Chỉ dùng một đường dẫn sạch, cố định, cùng origin.
    // Không giữ nguyên pathname/query nếu pathname có secret.
    window.history.replaceState(
        window.history.state, "", "/auth/processing"
    );

    if (error) {
        throw new Error("Authorization failed");
    }

    if (!code || !state) {
        throw new Error("Invalid OAuth callback");
    }

    // SDK phải lấy code_verifier của transaction state tương ứng.
    // Không gửi code/state cho analytics, logger hoặc bên thứ ba.
    await finishOAuthTransaction({
        code,
        state,
        redirectUri: "https://app.example.test/auth/callback"
    });
}
~~~

Điều kiện để mẫu này an toàn hơn:

1. **`finishOAuthTransaction` không phải API thực sẵn có**; dùng một OAuth/OIDC SDK đúng chuẩn, kiểm tra `state`/PKCE và issuer. Ví dụ chỉ dạy cách làm sạch URL trước khi tiếp tục.
2. **Đường `/auth/processing` phải là route hợp lệ cùng origin.** `replaceState` thay entry hiện tại của lịch sử mà không tạo network navigation; nó không tự dọn request đã gửi tới server.
3. Ghi nhớ `redirectUri` **ban đầu** dùng trong authorization/token request; không lấy `window.location.href` sau khi đã thay URL làm redirect URI để đổi code.
4. Không copy `code`/`state` sang `localStorage`, analytics, exception message, query mới hoặc history state. Các biến chỉ tồn tại tạm thời để xử lý transaction.
5. Đặt `Referrer-Policy: no-referrer` trên response callback, hạn chế tài nguyên bên thứ ba và dùng CSP thích hợp; nếu analytics chạy **trước** đoạn cleanup, URL có thể đã bị thu thập.
6. Nếu trang có thể chứa token trong **path** hoặc **fragment** do legacy flow, chọn đường sạch cố định thay vì chỉ xóa `search`; nhưng không biến việc giữ legacy token thành thiết kế mới.
7. Nếu SDK yêu cầu tự đọc URL, tích hợp **callback xử lý và cleanup theo SDK**; đừng tự xóa trước khi SDK có đủ thông tin, hoặc cố đưa credential vào chỗ khác không an toàn.

### replaceState làm được và không làm được

| Việc | `history.replaceState` có xử lý không? |
|---|---|
| Bỏ query/fragment khỏi **URL hiện tại trên thanh địa chỉ** | Có, nếu chọn URL mới đúng |
| Thay **entry history hiện tại** bằng URL sạch | Có |
| Gửi request HTTP mới | **Không** |
| Xóa URL đã lưu trong CDN/reverse proxy log | **Không** |
| Xóa URL đã gửi đến analytics trước khi chạy | **Không** |
| Thu hồi token đã bị sao chép | **Không** |
| Xóa mọi bản sao khỏi screenshot, clipboard, crash logs | **Không** |
| Ngăn script thứ ba đọc URL **trước khi cleanup** | **Không** |

Vì vậy, `replaceState` là **giảm thời gian phơi bày trong client**, không phải phương án giải quyết toàn bộ vòng đời token transport.

## 9. Implicit flow và token trong URL fragment: vì sao cần loại bỏ

Trong các OAuth flow lịch sử, **Implicit grant** có thể trả access token qua fragment redirect:

~~~text
https://app.example.test/callback#access_token=TOKEN&token_type=Bearer&expires_in=3600
~~~

Với URL trên:

- Fragment `#access_token=...` **không nằm trong request HTTP tới `app.example.test`**, và **không nằm trong header `Referer`** của subrequest theo cơ chế browser thông thường.
- Nhưng bất kỳ script có quyền chạy trong cùng trang, extension có quyền hoặc môi trường runtime bị chiếm có thể truy cập `window.location.hash`.
- Token có thể lọt vào browser history, ảnh chụp/copy URL, crash reporting hoặc analytics tự đọc `window.location.href`.
- Fragment chứa bearer access token từ front channel làm tăng bề mặt rò rỉ, đặc biệt với third-party script và injection.

**Giải pháp bền vững** không phải chỉ `replaceState`, mà là **chuyển sang Authorization Code + PKCE** và không cấp access token trực tiếp trong authorization response cho ứng dụng mới theo khuyến nghị hiện đại. Nếu đang vận hành flow cũ, cần lên kế hoạch migration, xoá fragment càng sớm càng tốt, hạn chế script và xử lý token có thể đã lộ; **không coi việc fragment bị loại khỏi `Referer` là đủ an toàn**.

### OIDC hybrid/form_post

Một số profile OIDC có thể chuyển thông tin qua front channel hoặc `response_mode=form_post`. POST body tránh hiển thị giá trị trong URL, nhưng **không tự bảo đảm không bị log, XSS, CSRF hoặc gửi nhầm**, nên vẫn phải kiểm tra token purpose/audience/nonce và chính sách ứng dụng. Đối với ứng dụng web thông thường, chọn **Code + PKCE** phù hợp và không tự đưa access/refresh token vào URL.

## 10. Thông tin nhạy cảm không chỉ có access token

Cần phân loại khi thiết kế URL:

| Dữ liệu | Có thể xuất hiện trong URL? | Cách xử lý |
|---|---|---|
| **Access token** | Không nên | Đưa vào header đúng scheme; không dùng query/path/fragment |
| **Refresh token** | Không | Chỉ gửi token endpoint qua kênh yêu cầu đúng protocol; bảo vệ storage |
| **ID token** | Tránh front channel nếu không có profile cần thiết | Client OIDC xác minh và lưu tối thiểu; không dùng thay API token |
| **Authorization code** | Có thể có trong `?code=...` của OAuth code response | Dùng một lần, PKCE, state, redirect sạch, không log raw query |
| **`state` OAuth** | Có thể có trong callback | Không phải access token, nhưng là giá trị chống CSRF/liên kết transaction; không log/analytics |
| **`nonce` OIDC / code_verifier PKCE** | Không đưa verifier vào URL callback | Lưu tạm theo transaction, kiểm tra/xóa sau khi dùng |
| **Password reset token / magic link** | Một số sản phẩm bắt buộc có một lần trong liên kết | Hạn ngắn, một lần, no-referrer, không có third-party, đổi sang session an toàn rồi redirect sạch |
| **Signed download URL** | Có thể là thiết kế đặc thù | Coi URL là bearer capability; ràng buộc scope/tài nguyên/TTL và hạn chế log/Referer |

**Authorization code không “vô hại” chỉ vì không phải access token.** Nó thường gắn client/PKCE và dùng một lần, nhưng vẫn là dữ liệu cần bảo vệ; nếu lộ cùng verifier hoặc có cấu hình flow yếu, có thể bị lợi dụng.

### Magic link và signed URL là ngoại lệ có kiểm soát

Có trường hợp thiết kế cần link chứa một **token một lần** hoặc URL có chữ ký, chẳng hạn xác nhận email hoặc tải file. Khi đó:

1. Coi toàn bộ link là **credential/capability nhạy cảm**, tránh analytics, ảnh/font/script ngoài domain trước khi redeem.
2. Giới hạn TTL, số lần dùng, tài nguyên/quyền và bind vào context phù hợp; phát hiện replay.
3. Dùng `Referrer-Policy: no-referrer` cho landing page; chuyển sang URL sạch sau khi redeem.
4. Không log raw query; tránh việc email security scanner/link preview **tự thực hiện hành động tiêu thụ token** bằng request GET. Thiết kế bước xác nhận có CSRF/user intent khi thích hợp.
5. Không lấy sự tồn tại của ngoại lệ để hợp thức hóa `access_token=...` trong URL API.

## 11. Log, proxy, CDN và analytics: chặn rò tại nhiều tầng

Một callback URL sạch sau `303` vẫn có thể đã bị **ngược dòng** ghi lại:

~~~text
Browser -> CDN -> Reverse proxy -> App /auth/callback?code=...
          |            |               |
          v            v               v
        access log    request log    framework/APM
~~~

**Nguồn có thể ghi query:** CDN edge log, load balancer, ingress, reverse proxy, application server access log, tracing/APM, error monitor, SIEM, API gateway, WAF và analytics script đọc `window.location.href`.

### Quy tắc log tối thiểu

| Không nên ghi | Thay bằng dữ liệu an toàn hơn |
|---|---|
| Full URL của callback gồm `code`/`state` | Route template `/auth/callback`, method, status, request ID |
| Header `Authorization`, cookie, client secret | Credential type, client reference, outcome, error code |
| Refresh/access token, JWT compact string | Token reference pseudonym hoặc grant reference do hệ thống tin cậy cấp |
| Full `Referer` trên trang nhạy cảm | Không ghi hoặc chỉ lưu **origin** khi có lý do và chính sách cho phép |
| Request/response body của token endpoint | Tên grant type, scope được cấp, audience và outcome đã allowlist |
| Query dạng tự do trong exception/APM | Error code có cấu trúc, loại event, ID tương quan an toàn |

Ví dụ cấu trúc log an toàn cho callback:

~~~json
{
  "event": "oauth.callback.completed",
  "route_template": "/auth/callback",
  "http_method": "GET",
  "http_status": 303,
  "client_ref": "orders-web",
  "correlation_id": "req-pseudo-8f2",
  "outcome": "SUCCESS",
  "raw_url_logged": false,
  "token_in_log": false
}
~~~

Đây chỉ là **sự kiện minh họa**: hai trường boolean không tự chứng minh log toàn hệ thống không lộ token. Cần **kiểm thử bằng giá trị canary giả** ở từng thành phần thu thập và kiểm tra chính sách log thực tế.

### Tại sao “regex che query” có thể chưa đủ?

- Secret có thể nằm trong **path**, fragment mà client-side telemetry gửi, header hoặc JSON payload.
- URL encoding, case variation, nested query, ký tự phân tách, log pipeline normalize khác nhau có thể làm lọt value.
- Chỉ redact tên `access_token` nhưng không che `code`, `id_token`, `refresh_token`, `token`, `session` hoặc vendor-specific fields.
- Full `Referer` có thể chứa query nhạy cảm từ **trang khác**, không chỉ request URL hiện tại.
- Một hệ thống downstream đã lưu log trước khi bộ redaction chạy thì không thể “thu hồi” bản sao đó tự động.

**Ưu tiên allowlist trường cần log** (route template, status, latency, correlation ID, authenticated client reference sau xác minh) thay cho blacklist tên param. Với endpoint nhạy cảm, có thể tắt raw access log hoặc dùng redaction tại **điểm đầu tiên** của pipeline.

## 12. Khi nào nên dùng no-referrer toàn trang, khi nào dùng chính sách theo đường dẫn?

`Referrer-Policy: no-referrer` chặn `Referer` phát sinh từ trang, kể cả điều hướng cùng origin. Nó làm giảm khả năng gắn nguồn điều hướng trong analytics/attribution; một số chức năng phụ thuộc `Referer` có thể cần đổi cách hoạt động.

Một chính sách thực tế:

- **Callback OAuth, password-reset/magic-link landing, trang có thể nhận URL nhạy cảm:** áp dụng `no-referrer` ngay tại response, không tải third-party trước khi cleanup.
- **Trang ứng dụng bình thường không có secret trong URL:** có thể dùng `strict-origin-when-cross-origin` hoặc `origin` theo privacy/threat model, **nhưng đừng cho phép token trong URL chỉ vì policy “ít gửi”**.
- **Các link tới miền không tin cậy:** `rel=noreferrer` hoặc referrer policy riêng khi cần.
- **Gateway/edge:** kiểm tra response header ở chính đường callback và error handler, không chỉ cấu hình trên trang homepage.
- **Bên thứ ba có thể override policy:** rà HTML element `referrerpolicy`, `<meta name="referrer">`, redirects, môi trường WebView cũ và compatibility.

**Đừng dùng `Referer` làm bằng chứng xác thực hoặc CSRF token.** Header này có thể bị thiếu bởi policy/browser, hoặc bị giả mạo trong các loại HTTP client khác; bảo vệ CSRF cần cơ chế được thiết kế riêng như state/CSRF token và cookie attributes.

## 13. Phân biệt referrer leak với token replay và token confusion

**Referrer leak** là một đường khiến một token/authorization code đi tới nơi không được phép thấy. Nhưng nguy cơ cuối cùng phụ thuộc **loại hiện vật và kiểm tra phía nhận**.

| Kịch bản | Lộ gì? | Thành phần phải kiểm soát thêm |
|---|---|---|
| Bearer access token nằm trong query và xuất hiện trong Referer/log | Bản sao bearer token đầy đủ | AS/RS scope/audience/TTL, token revocation hoặc denylist, API object policy |
| Authorization code một lần trong query | Code gắn transaction | AS kiểm tra client, redirect, PKCE, state/mix-up, dùng một lần |
| ID token trong URL | Claims định danh; có thể bị lạm dụng ở hệ thống nhầm purpose | OIDC client kiểm tra ID token; API **không nhận** ID token thay access token |
| Refresh token trong URL | Credential có thể xin token mới | AS token endpoint, client/grant binding, rotation/reuse detection, revoke |
| DPoP-bound access token trong URL | Bản sao token nhưng không tự có private key | RS kiểm tra DPoP proof, `cnf.jkt`, `htm`/`htu`/`ath` và anti-replay |
| Mã reset mật khẩu trong URL | One-time capability | Endpoint reset hạn ngắn, một lần, không có subresource bên thứ ba, confirmation policy |

**Có chữ ký JWT không có nghĩa không thể replay.** JWS bảo vệ tính toàn vẹn claims khi verify đúng, nhưng một bản sao bearer token nguyên vẹn vẫn có thể được trình lại. Ngay cả token có `scope=read` cũng cần kiểm tra quyền trên object/tenant cụ thể.

**Không dùng Referrer-Policy để thay token validation.** API vẫn phải xác minh JWT signature hoặc opaque introspection, issuer, audience, thời gian, token purpose, scope, và quyền dữ liệu.

## 14. Phản ứng khi phát hiện token đã xuất hiện trong URL hoặc Referer

Khi phát hiện có access token/refresh token thật trong URL, xử lý như **sự cố nghi lộ credential**.

~~~mermaid
flowchart TD
    D["Phát hiện URL/Referer có credential"] --> Q["Khoanh vùng token type, issuer, audience, scope"]
    Q --> I["Cô lập nguồn log/analytics và chặn tiếp tục ghi"]
    I --> R{"Có thể chặn quyền sử dụng token không?"}
    R -->|"Có"| V["Revoke token / grant / refresh family theo policy"]
    R -->|"JWT offline chưa có state"| M["Giới hạn phơi nhiễm đến exp, triển khai denylist hoặc state phù hợp"]
    V --> P["Kiểm tra propagation tại AS và mọi RS"]
    M --> P
    P --> L["Rà audit usage, refresh, các API/tenant liên quan"]
    L --> F["Sửa URL transport, callback, Referrer-Policy, log và test"]
~~~

Các bước thực hiện:

1. **Không dán token thật vào ticket/chat** để giải thích sự cố. Dùng tham chiếu/pseudonym, đường dẫn hệ thống và mốc thời gian.
2. **Định loại hiện vật** từ metadata tin cậy của AS/RS: access/refresh/ID/code, JWT/opaque, audience/scope/client/grant, thời hạn và trạng thái.
3. **Giảm phát tán ngay:** gỡ URL có token khỏi ứng dụng, xóa link công khai, tắt hoặc redact log/analytics đang thu full URL, khóa quyền xem log theo chính sách. Việc xóa một bản log không bảo đảm mọi bản sao đã bị xóa.
4. **Thu hồi đúng đối tượng:** access token tại các RS nếu cần chặn sớm; refresh token/grant tại AS để ngăn phát hành tiếp; nếu lộ client credential/key, xử lý rộng hơn.
5. **Kiểm tra hiệu lực thực tế:** revocation endpoint trả HTTP 200 **không chứng minh JWT đang được API tự xác minh đã bị chặn ngay**. Đo propagation, cache, multi-region và hạn còn lại.
6. **Điều tra tác động:** bằng audit có kiểm soát, xem API usage, token refresh, client, tenant và thời điểm sau khi credential bị lộ; không giả định luôn có attacker.
7. **Sửa nguyên nhân:** chuyển token khỏi URL, bật `no-referrer` ở callback, redirect sạch, loại bỏ log query, giới hạn script bên thứ ba, kiểm thử toàn bộ redirect chain.
8. **Khôi phục:** cấp lại credential/reauthentication qua kênh tin cậy, không tái sử dụng token đã bị nghi ngờ lộ.

### Nếu chỉ có fragment chứa token thì sao?

Dù `Referer` **không mang fragment**, token có thể đã bị thu qua script hoặc URL copy/paste. Hãy kiểm tra analytics, XSS, browser history và các dấu hiệu lộ thực tế. Nếu toàn bộ bearer token đã được truyền tới bên không đáng tin, áp dụng quy trình revoke tương ứng; đừng coi “Referer không có fragment” là bằng chứng token an toàn.

## 15. Case study: callback OAuth và tài nguyên analytics

Một app `orders-web` dùng Authorization Code + PKCE. AS redirect về:

~~~text
https://app.example.test/auth/callback?code=C123&state=S123
~~~

Giả sử trang callback trả HTML và tải ngay:

~~~html
<script src="/assets/app.js"></script>
<script src="https://metrics.example.test/analytics.js"></script>
~~~

Với default `strict-origin-when-cross-origin`:

1. Request `/assets/app.js` **cùng origin** có thể mang `Referer` chứa `?code=C123&state=S123`; asset/CDN log nhìn thấy code.
2. Request analytics script **khác origin HTTPS** thường chỉ mang origin trong `Referer`, không phải full query. Nhưng script đó nếu được chạy trong document có quyền truy cập `window.location.href` và **có thể tự thu query/fragment**.
3. Nếu trang hoặc element dùng `unsafe-url` hoặc policy cũ, **cross-origin Referer cũng có thể mang path/query**.
4. Nếu server đổi code và trả `303 Location: /app` ngay, browser cuối cùng đến URL sạch, nhưng **request callback đã vào log** vẫn phải redact.
5. Nếu app chỉ xóa query bằng `replaceState` sau khi analytics đã chạy, việc xóa là **quá muộn** đối với dữ liệu analytics đã gửi.

### Phương án sửa

| Lớp | Trước (rủi ro) | Sau (kiểm soát) |
|---|---|---|
| OAuth flow | Implicit/đưa token vào URL | Authorization Code + PKCE, token trao đổi tại AS |
| Callback response | Render đầy đủ HTML và analytics | Backend xử lý rồi `303` sạch, hoặc SPA callback tối giản |
| Referrer | Chỉ dựa policy mặc định | `Referrer-Policy: no-referrer` trên callback/error |
| JavaScript | SDK bên thứ ba chạy trước cleanup | Cleanup sớm nhất, không thu full URL |
| Logging | Ghi `request_uri`/raw query/Referer | Allowlist route template, status, correlation ID |
| Browser history | Query/token còn trong entry | URL sạch qua 303/`replaceState` khi phù hợp |
| Token storage | Token trong URL/local copy | Token theo kênh/lưu trữ bảo mật phù hợp |
| Revocation | Không có playbook nếu lộ | Revoke/denylist/introspection + audit/SLA rõ |

**Kết luận tình huống:** `Referrer-Policy` giảm một phần nguy cơ rò, nhưng sửa triệt để phải **không đặt bearer token trong URL** và **không để authorization code đi vào analytics, request log hay history lâu hơn cần thiết**.

## 16. Kiểm thử thực tế: không dùng token production

Dùng **giá trị giả** tại môi trường test/staging để kiểm tra request, logs và hành vi browser. Có thể dùng các marker như `TEST_CODE_CANARY_123` hoặc `TEST_TOKEN_CANARY_456` để tìm đường rò mà không đưa credential thật vào công cụ phân tích.

### Ma trận test

| Test | Cách làm | Kết quả mong đợi |
|---|---|---|
| **T1 — Cùng origin** | Mở callback chứa code giả, tải `/assets/app.js` | Với `no-referrer`, không có `Referer` chứa code giả |
| **T2 — Khác origin HTTPS** | Trang test tải asset/analytics giả | Không có code/token giả trong `Referer` hoặc telemetry |
| **T3 — URL fragment** | Mở `/callback#access_token=TEST_TOKEN...` | Fragment không nằm trong HTTP request/Referer; app vẫn dọn và không gửi cho SDK |
| **T4 — Callback sạch** | Hoàn tất code flow test | Browser được chuyển sang URL cố định không có `code`, `state`, token |
| **T5 — Redirect Location** | Kiểm tra 302/303 response | `Location` không mang token/code/secret |
| **T6 — Server/edge logs** | Tìm canary trong CDN/proxy/app/APM logs | Không thấy canary ở các nguồn log cho phép kiểm tra |
| **T7 — Third-party analytics** | Ghi nhận payload analytics test | Không có `window.location.href` đầy đủ chứa query/fragment nhạy cảm |
| **T8 — Authorization header** | Client gọi API test bằng bearer token giả hợp lệ theo staging | Token không nằm trong URL hoặc logs |
| **T9 — Error page** | Cố ý gửi callback thiếu/sai `state` | Error response vẫn `no-referrer`/`no-store`, không in raw URL |
| **T10 — Browser history** | Hoàn tất callback, back/forward/reload | Không tái xuất hiện URL nhạy cảm trong entry hiện tại; hành vi callback cũ được xử lý an toàn |
| **T11 — State/PKCE** | Đổi code với state sai hoặc verifier không khớp | Token endpoint/Client từ chối; cleanup không phá validation |
| **T12 — Multi-provider OAuth** | Response từ issuer không mong đợi | Client từ chối mix-up, không gửi code sang sai AS |
| **T13 — Refresh token** | Test luồng refresh | RT chỉ đến AS/token endpoint; không URL/log/API nghiệp vụ |
| **T14 — DPoP/mTLS** | Dùng token-bound trên API test không có proof | RS từ chối; không hạ cấp thành query bearer |
| **T15 — Revoke sau lộ** | Revoke token test rồi gọi các RS | Từ chối theo cơ chế/SLA đã định nghĩa |
| **T16 — Legacy browser/WebView** | Thử policy/redirect trên client được hỗ trợ | Có hành vi phù hợp; nếu không hỗ trợ policy cần giảm nguy cơ ở thiết kế URL |

**Không dùng token production thật** để kiểm thử referrer leak hay tìm canary. Những phép thử có thể ghi URL vào công cụ; phải dùng token giả hoặc credentials staging có quyền tối thiểu và theo quy trình cho phép.

### Lưu ý khi kiểm tra bằng Developer Tools

- Xem **Network → Request Headers** để xác định `Referer` thực sự gửi tới từng origin.
- Xem **Response Headers** của callback/redirect để xác nhận `Referrer-Policy` và `Cache-Control`.
- Xem **Location** của redirect để chắc chắn không có query/code/token.
- Kiểm tra **Request URL** của callback để nhớ rằng query đã vào tầng server ban đầu; `Referer-Policy` không thể làm nó biến mất ở đó.
- Kiểm tra analytics payload/log test có xuất hiện marker không, ngay cả khi `Referer` chỉ là origin.
- Không chụp màn hình hoặc chia sẻ HAR file có credential thật; HAR có thể chứa cookie, token và authorization code.

## 17. Các hiểu lầm phổ biến

**“Chỉ cần HTTPS là token trong URL an toàn.”** Sai. HTTPS không ngăn browser history, app/CDN logs hoặc bên nhận referrer hợp lệ lưu URL.

**“Token trong fragment `#...` sẽ xuất hiện trong Referer.”** Thường sai: fragment bị loại khỏi `Referer` theo cơ chế browser. Tuy vậy script, telemetry và lịch sử vẫn có thể thấy token.

**“Browser hiện đại mặc định chỉ gửi origin, nên query không bao giờ lộ.”** Sai. Với `strict-origin-when-cross-origin`, request **cùng origin** có thể mang full path/query; policy/override/browser khác cũng thay đổi hành vi.

**“Đặt `Referrer-Policy: no-referrer` là đủ để xóa token.”** Sai. Nó kiểm soát header `Referer` phát sinh từ trang; không xóa raw URL trong request ban đầu, history, JavaScript hoặc log đã ghi.

**“Gọi `history.replaceState` xong là token đã được thu hồi.”** Sai. Nó chỉ thay entry lịch sử phía browser, không tác động AS/Resource Server.

**“Authorization code không phải access token nên có thể log.”** Sai. Code là hiện vật nhạy cảm, thường dùng một lần và có ràng buộc, nhưng vẫn không được log hoặc phát tán.

**“JWT đã ký không cần quan tâm URL leak.”** Sai. Chữ ký JWS ngăn sửa claims, **không ngăn replay** một bản sao bearer token đã bị lấy.

**“Đưa token từ query sang path sẽ tránh leak.”** Sai. Path cũng là thành phần request URL và có thể xuất hiện trong `Referer` hoặc log.

**“Cứ xóa query là xong, không cần kiểm tra state/PKCE.”** Sai. Callback phải hoàn thành các kiểm tra bảo mật; cleanup cần được đặt đúng thứ tự để **không làm mất transaction context** hoặc vô tình gửi code sang AS sai.

## 18. Checklist triển khai và xử lý sự cố

1. **Loại bỏ token khỏi URL:** không có bearer access/refresh token trong query, path hoặc fragment của API/browser flow hiện đại.
2. **Gửi đúng kênh:** access token trong `Authorization` header phù hợp; refresh token chỉ tới AS token endpoint theo chuẩn; ID token chỉ cho OIDC client.
3. **Chọn Code + PKCE:** với browser/native client, không phát hành access token qua implicit front-channel flow cho thiết kế mới.
4. **Bảo vệ callback:** kiểm tra `state`, PKCE, issuer/AS mix-up, code một lần dùng, redirect URI và client binding.
5. **Chuyển sang URL sạch sớm:** `303 See Other` từ BFF hoặc `history.replaceState` trong SPA callback tối giản; `Location` không có credential.
6. **Dùng `Referrer-Policy: no-referrer` trên callback và các trang nhạy cảm**, kể cả error handler, trước khi tải subresource.
7. **Không chỉ dựa vào policy mặc định:** kiểm tra same-origin `Referer` và cả môi trường browser/WebView được hỗ trợ.
8. **Phân biệt fragment:** không xuất hiện trong HTTP Referer, nhưng có thể bị JS, analytics, history và URL sharing đọc.
9. **Chặn third-party trước cleanup:** không chạy analytics/tag manager ở callback chứa dữ liệu nhạy cảm.
10. **Đảm bảo TLS và bảo vệ cookie:** HTTPS, `Secure`/`HttpOnly`/`SameSite` thích hợp, CSRF/session policy cho BFF.
11. **Bảo vệ toàn bộ log pipeline:** CDN/edge/proxy/APM/error report/analytics không ghi raw URL, `Referer` hay `Authorization` chứa credential.
12. **Xử lý URL capability ngoại lệ:** magic link/signed URL hạn ngắn, một lần/quyền hẹp nếu cần, no-referrer và redeem rồi URL sạch.
13. **Đừng nhầm cleanup với revoke:** token thật đã lộ phải được xử lý qua AS/RS, refresh/grant/denylist/introspection khi cần.
14. **Kiểm thử với canary giả:** mạng, log, history, redirect, error page, JS telemetry, CSRF/PKCE/mix-up và policy.
15. **Ghi nhận giới hạn:** `Referrer-Policy` không xóa request ban đầu, history đã đồng bộ, HAR/log đã ghi hoặc bản sao token bị đánh cắp.
16. **Rà soát endpoint downstream:** mỗi Resource Server vẫn xác minh issuer, audience, token purpose, scope, thời gian, trạng thái và object/tenant policy.

**Kết luận:** muốn **xóa token khỏi URL referrer** một cách đáng tin, trước hết phải **không đưa bearer token vào URL**, sau đó **giữ authorization code trong callback ngắn nhất có thể**, cấu hình **`Referrer-Policy: no-referrer`**, chuyển về URL sạch, và chặn việc ghi query/`Referer` ở mọi tầng log/analytics. Fragment thường không đi trong `Referer` nhưng cũng không phải nơi an toàn để chứa access token. Mọi sự cố token đã lộ vẫn cần **thu hồi thực tế tại AS và Resource Server**, bên cạnh xác minh JWT/opaque, audience, scope và quyền tài nguyên.

### Tài liệu chuẩn và tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình bearer token, rủi ro URI query và bảo vệ credential.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code, token response và các flow lịch sử.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc code exchange với verifier.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo mật flow và ngăn access token lộ qua front-channel.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): browser ngoài ứng dụng và redirect cho native app.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer identification và giảm authorization-server mix-up.
- [MDN — Referer request header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer): cách browser gửi URL nguồn.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): các chính sách `no-referrer`, `origin`, `strict-origin-when-cross-origin`.
- [MDN — History.replaceState()](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState): thay URL của history entry hiện tại.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): các điểm kiểm tra OAuth 2.0.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh ghi bí mật và bảo vệ audit log.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): thiết kế reset token một lần và giới hạn đường rò.
