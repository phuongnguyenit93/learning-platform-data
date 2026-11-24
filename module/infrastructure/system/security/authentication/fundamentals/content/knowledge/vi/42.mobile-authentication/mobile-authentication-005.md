# App redirect — Thiết kế callback đăng nhập an toàn cho ứng dụng mobile

Một người dùng mở ứng dụng ngân hàng trên điện thoại và chọn đăng nhập. Ứng dụng chuyển sang trang xác thực của identity provider trong browser hệ thống. Sau khi người dùng xác thực và đồng ý, browser điều hướng về ứng dụng bằng một redirect URI. Ứng dụng nhận authorization code rồi trao đổi code lấy token. Nếu nhiều ứng dụng có thể đăng ký cùng một custom URI scheme, một ứng dụng độc hại có thể giành quyền nhận callback. Nếu app dùng embedded WebView, nó có thể kiểm soát trang đăng nhập hoặc thu thập thông tin xác thực. Nếu app không ràng buộc callback với transaction đã khởi tạo, response cũ hoặc response của một login khác có thể bị chấp nhận.

**App redirect** là cơ chế đưa browser hoặc identity provider quay lại một ứng dụng mobile sau một thao tác như đăng nhập, consent hoặc xác minh. Trong OAuth/OIDC, redirect URI là một phần của authorization flow và phải được đăng ký, ràng buộc chính xác với client. Ứng dụng native cần bảo vệ callback khỏi app khác chiếm URI, response injection, code interception, open redirect và replay.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học thiết kế redirect cho Android/iOS, hiểu khác biệt giữa private-use URI scheme và claimed HTTPS app/universal links, áp dụng OAuth 2.0 Authorization Code Flow với PKCE, ràng buộc state/nonce với browser transaction, xác minh callback trước khi đổi code và quản lý vòng đời session sau redirect. Mục tiêu là bảo đảm chỉ đúng ứng dụng, đúng transaction và đúng identity provider mới có thể hoàn tất đăng nhập.

## 1. App redirect trong mobile authentication

Ứng dụng native thường không tự hiển thị form đăng nhập của identity provider. Thay vào đó, app mở một external user-agent (thường là browser hệ thống hoặc authentication session do OS cung cấp), để người dùng xác thực tại origin của identity provider. Khi flow hoàn tất, authorization server chuyển browser tới redirect URI của ứng dụng.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant A as Mobile app
    participant B as System browser
    participant I as Identity provider
    participant T as Token endpoint
    A->>A: Tạo state, nonce, PKCE verifier
    A->>B: Mở authorization request
    B->>I: HTTPS authorization request
    I->>I: Người dùng xác thực và consent
    I-->>B: Redirect URI + authorization code + state
    B->>A: OS mở app qua redirect callback
    A->>A: Kiểm tra state và transaction
    A->>T: Gửi code + PKCE verifier
    T-->>A: Token response
    A->>A: Xác minh ID token và tạo app session
~~~

Các thành phần có vai trò riêng:

- **Mobile app:** khởi tạo transaction, tạo PKCE verifier, nhận callback và trao đổi code.
- **System browser/authentication session:** hiển thị trang xác thực ở user-agent tách biệt với app.
- **Identity provider / authorization server:** xác thực người dùng, phát authorization code và chuyển hướng về redirect URI.
- **Operating system:** định tuyến callback tới ứng dụng đã đăng ký URI scheme hoặc domain association.
- **Token endpoint:** xác minh code, client và PKCE verifier rồi cấp token.

Redirect chỉ là phương tiện chuyển response về app. Nó không tự xác thực người dùng và không thay thế kiểm tra state, PKCE, issuer, audience, nonce hay chữ ký token.

## 2. External user-agent và embedded WebView

Với native app, nên dùng external user-agent theo thực hành OAuth cho native applications. Browser hệ thống tách cookie và trang đăng nhập khỏi môi trường JavaScript của app, giúp identity provider kiểm soát origin, TLS, password manager và session browser.

Không nên nhúng trang đăng nhập của identity provider vào WebView do app tự kiểm soát:

- App có thể quan sát nội dung trang và tương tác của người dùng.
- Người dùng khó xác minh origin thật và chứng chỉ.
- Cookie/session có thể không được chia sẻ đúng với browser hệ thống.
- Identity provider khó áp dụng các biện pháp chống phishing và quản lý phiên nhất quán.
- Một WebView tùy biến có thể làm suy yếu SSO, passkey hoặc MFA.

Một số SDK cung cấp system browser tab hoặc authentication session với callback OS-native. Dùng API được nền tảng hỗ trợ và tuân theo hướng dẫn của identity provider. Không tự dựng browser giả để hiển thị trang đăng nhập.

### 2.1. Lựa chọn user-agent

| Cách mở trang xác thực | Đặc điểm | Đánh giá |
| --- | --- | --- |
| System browser | Browser độc lập, session và origin rõ | Lựa chọn phổ biến cho native OAuth |
| Android Custom Tabs | Giao diện browser do browser provider cung cấp | Dùng khi cần trải nghiệm tích hợp nhưng vẫn là external user-agent |
| iOS AuthenticationServices / ASWebAuthenticationSession | OS quản lý authentication session và callback | Lựa chọn phù hợp cho native sign-in |
| Embedded WebView | App sở hữu context hiển thị và có thể kiểm soát nội dung | Tránh dùng cho OAuth authorization request |

Nếu app cần đăng nhập bằng tài khoản nội bộ không phải OAuth, vẫn phải bảo vệ credential entry, origin, session và callback theo threat model riêng. Không dùng WebView để giả giao diện IdP bên ngoài.

## 3. Chọn redirect URI: custom scheme hay HTTPS app link?

Có hai nhóm callback thường gặp:

1. **Private-use URI scheme:** ví dụ `com.example.mobile:/oauth2redirect`.
2. **Claimed HTTPS redirect:** ví dụ `https://login.example.com/mobile/callback`, được OS liên kết với ứng dụng qua cơ chế xác minh domain.

| Thuộc tính | Private-use URI scheme | Claimed HTTPS link |
| --- | --- | --- |
| Ví dụ | `com.example.app:/callback` | `https://login.example.com/callback` |
| OS dispatch | Dựa trên app đăng ký scheme | Dựa trên association đã xác minh giữa domain và app |
| Rủi ro app khác chiếm callback | Có thể xảy ra nếu scheme không được độc quyền | Giảm đáng kể khi domain association được xác minh đúng |
| Cấu hình | Scheme/intent filter/URL type | Android App Links hoặc Apple Universal Links |
| Phụ thuộc domain | Không nhất thiết | Có; cần asset association file và domain control |
| Khuyến nghị | Chỉ dùng khi không có lựa chọn claimed HTTPS phù hợp | Thường ưu tiên cho app production khi nền tảng hỗ trợ |

Không dùng custom scheme chung như `myapp`, `login` hoặc `auth` nếu có thể chọn scheme gắn với reverse-domain của tổ chức. Tuy nhiên, tên dài và khó đoán không tạo ra bảo đảm độc quyền; app khác vẫn có thể đăng ký cùng scheme. PKCE là lớp bảo vệ quan trọng khi callback bị app khác nhận.

### 3.1. Claimed HTTPS redirect

Android App Links và Apple Universal Links cho phép OS kiểm tra mối liên kết giữa domain HTTPS và ứng dụng. Khi association được xác minh, OS có thể ưu tiên mở app đã được domain claim thay vì hiển thị lựa chọn ứng dụng tùy ý.

Lợi ích:

- Giảm nguy cơ một app không liên quan chiếm callback bằng cách đăng ký cùng URI scheme.
- Người dùng có thể dùng cùng domain callback cho browser và app theo cấu hình.
- Domain association là một trust statement có thể kiểm tra và quản lý.
- Redirect URI vẫn thuộc namespace HTTPS đã đăng ký tại authorization server.

Giới hạn:

- Domain hoặc website association file bị compromise có thể ảnh hưởng trust.
- Cấu hình sai package/bundle ID hoặc signing fingerprint khiến link không được xác minh.
- OS version, browser và app state có thể ảnh hưởng cách dispatch.
- Nếu app chưa cài, link có thể mở website; website fallback không được làm lộ code/token.
- Universal/App Links không thay PKCE, state hay exact redirect URI validation.

## 4. Android App Links và intent filters

Android có thể dùng intent filter với `android:autoVerify="true"` cho HTTPS domain. Website cần cung cấp asset links association để xác nhận package name và signing certificate fingerprint.

Ví dụ intent filter khái niệm:

~~~xml
<activity
    android:name=".auth.AuthCallbackActivity"
    android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data
            android:scheme="https"
            android:host="login.example.com"
            android:path="/mobile/callback" />
    </intent-filter>
</activity>
~~~

Website tại domain tương ứng cần phục vụ `/.well-known/assetlinks.json` với package và fingerprint phù hợp. Phải kiểm tra fingerprint của signing certificate dùng cho bản phát hành thực tế; debug signing key không được đưa vào association production.

### 4.1. Xử lý callback Android

Activity callback phải xem intent là input không tin cậy. Kiểm tra:

- Scheme, host, port và path chính xác.
- Chỉ chấp nhận callback cho transaction đang chờ.
- State khớp với giá trị được lưu trước khi mở browser.
- Không có tham số trùng lặp hoặc tham số không hợp lệ.
- Authorization code chỉ được chuyển tới token endpoint tin cậy.
- PKCE verifier được lấy từ transaction local, không lấy từ callback.
- Intent không chứa token/identity do app khác tự thêm rồi được tin.

Ví dụ Kotlin minh họa kiểm tra callback:

~~~kotlin
fun handleAuthCallback(intent: Intent) {
    val uri = intent.data ?: return rejectCallback()

    if (uri.scheme != "https" ||
        uri.host != "login.example.com" ||
        uri.port != -1 ||
        uri.path != "/mobile/callback") {
        return rejectCallback()
    }

    val states = uri.getQueryParameters("state")
    val codes = uri.getQueryParameters("code")
    if (states.size != 1 || codes.size != 1) {
        return rejectCallback()
    }

    val tx = pendingTransactions.findByState(states.single())
        ?: return rejectCallback()

    if (tx.isExpired() || tx.isConsumed()) {
        return rejectCallback()
    }

    val claim = pendingTransactions.claimForExchange(tx.id)
        ?: return rejectCallback()

    try {
        val tokens = exchangeAuthorizationCode(
            code = codes.single(),
            codeVerifier = claim.pkceVerifier(),
            redirectUri = claim.redirectUri()
        )
        validateTokenResponse(tokens, claim.expectedIssuer(), claim.expectedNonce())
        sessionStore.commitForTransaction(claim.id, tokens)
        pendingTransactions.markCompleted(claim.id)
    } catch (error: TokenExchangeException) {
        // Nếu không rõ token endpoint đã consume code hay chưa, không mở lại transaction.
        pendingTransactions.markFailedOrOutcomeUnknown(claim.id)
        rejectCallback()
    }
}
~~~

Đây là pseudocode. Android URI parsing APIs và cách lấy query parameters cần được triển khai cẩn thận để phát hiện duplicate parameter, malformed encoding và parser differences. Chuyển transaction nguyên tử từ pending sang exchanging trước khi gọi token endpoint để ngăn hai callback đồng thời đổi cùng code. Nếu timeout khiến không biết authorization code đã được consume hay chưa, không đưa transaction trở lại pending một cách mù quáng; đánh dấu outcome unknown và yêu cầu khởi động flow mới nếu không thể khôi phục kết quả an toàn. Không log raw code hoặc verifier.

### 4.2. Custom scheme trên Android

Nếu dùng private-use scheme, intent filter phải giới hạn scheme, host/path và activity cụ thể. Không dùng wildcard rộng. Cần giả định app khác có thể đăng ký cùng scheme; vì vậy callback không được tự tin vào việc OS mở đúng app. PKCE verifier phải được giữ trong app đã khởi tạo transaction và code bị chặn ở app khác sẽ không đổi được token nếu verifier không có.

## 5. iOS Universal Links và URL schemes

Apple Universal Links dùng HTTPS domain đã liên kết với app qua Associated Domains entitlement và file `apple-app-site-association` (AASA). OS xác minh association để quyết định mở app cho link thuộc domain đã claim.

Các bước khái niệm:

1. Cấu hình Associated Domains entitlement cho app, ví dụ `applinks:login.example.com`.
2. Phục vụ file AASA đúng domain qua HTTPS, không redirect sai và với nội dung hợp lệ.
3. Khai báo app identifier và path/component được phép mở trong app.
4. Kiểm tra bundle ID/team ID và môi trường signing.
5. Xử lý URL trong callback của NSUserActivity hoặc scene lifecycle tùy kiến trúc.
6. Xác minh callback state/PKCE/transaction trước khi trao đổi code.

### 5.1. Universal Link callback

App nhận URL trong callback của NSUserActivity hoặc scene lifecycle tùy kiến trúc. Chỉ xử lý URL nếu host/path/scheme khớp chính xác với callback đã cấu hình.

Swift pseudocode:

~~~swift
func handleUniversalLink(_ url: URL) {
    guard url.scheme == "https",
          url.host == "login.example.com",
          url.path == "/mobile/callback",
          let components = URLComponents(
              url: url,
              resolvingAgainstBaseURL: false
          ) else {
        rejectCallback()
        return
    }

    let stateValues = components.queryItems?
        .filter { $0.name == "state" }
        .compactMap { $0.value } ?? []
    let codeValues = components.queryItems?
        .filter { $0.name == "code" }
        .compactMap { $0.value } ?? []

    guard stateValues.count == 1,
          codeValues.count == 1,
          let transaction = pendingTransactions.find(
              state: stateValues[0]
          ),
          !transaction.isExpired,
          !transaction.isConsumed else {
        rejectCallback()
        return
    }

    exchangeCode(
        codeValues[0],
        verifier: transaction.pkceVerifier,
        redirectURI: transaction.redirectURI
    )
}
~~~

Pseudocode cần được điều chỉnh theo API Swift/SDK thực tế. URLComponents giúp parse có cấu trúc, nhưng app vẫn cần exact callback validation, duplicate parameter handling, state binding, expiry và atomic consume. Không ghi callback URL đầy đủ vào analytics/crash report.

### 5.2. Custom URL scheme trên iOS

URL type có thể đăng ký scheme riêng trong app bundle. Scheme này không tạo ra quyền sở hữu độc quyền; một app khác có thể khai báo cùng scheme. Khi callback đến nhầm app, PKCE giúp ngăn app đó đổi authorization code nếu nó không có verifier. Ưu tiên Universal Links khi có thể quản lý domain association đáng tin cậy.

## 6. OAuth Authorization Code Flow với PKCE

Native app là public client: binary và dữ liệu cài trên thiết bị không thể giữ client secret như một confidential server. Không nhúng client secret cố định vào APK, IPA hoặc source code. Dùng Authorization Code Flow với PKCE.

### 6.1. Khởi tạo transaction

Trước khi mở browser, app tạo:

- `code_verifier`: chuỗi ngẫu nhiên có entropy cao, chỉ giữ trong app transaction.
- `code_challenge`: BASE64URL(SHA256(code_verifier)).
- `state`: giá trị ngẫu nhiên gắn với transaction/browser session.
- `nonce`: giá trị ngẫu nhiên cho OIDC, được kiểm tra trong ID token.
- `redirect_uri`: URI chính xác đã đăng ký.

App lưu transaction trong vùng lưu trữ phù hợp, gắn với thời hạn và trạng thái pending. Không ghi verifier hoặc token vào log. Tránh lưu verifier ở nơi app khác có thể đọc.

### 6.2. Authorization request

Ví dụ request khái niệm:

~~~http
GET /authorize?
  response_type=code&
  client_id=mobile-client&
  redirect_uri=https%3A%2F%2Flogin.example.com%2Fmobile%2Fcallback&
  scope=openid%20profile&
  state=<random-state>&
  nonce=<random-nonce>&
  code_challenge=<base64url-sha256>&
  code_challenge_method=S256
Host: id.example.org
~~~

Authorization server cần exact-match redirect URI với client registration, yêu cầu PKCE S256 cho native public client và không cho phép redirect tới domain tùy ý. Không dùng `plain` PKCE khi S256 được hỗ trợ.

### 6.3. Callback và token exchange

Khi app nhận callback:

1. Kiểm tra scheme/host/port/path chính xác.
2. Parse query/form response theo protocol; từ chối duplicate hoặc malformed parameter.
3. Tìm transaction đang pending bằng state và kiểm tra state khớp.
4. Kiểm tra transaction chưa hết hạn, chưa consume và thuộc đúng app/client.
5. Xử lý OAuth error response an toàn nếu có.
6. Gửi authorization code, code_verifier, client_id và redirect_uri đúng tới token endpoint qua HTTPS.
7. Xác minh token response và OIDC ID token: issuer, audience, signature, expiry, nonce và các claim cần thiết.
8. Atomically claim transaction bằng trạng thái pending → exchanging trước token exchange; sau khi xác minh response, lưu session và đánh dấu completed.
9. Xóa verifier/state khỏi bộ nhớ transaction sau khi hoàn tất.

PKCE ngăn app khác dùng authorization code bị chặn ở callback nếu app đó không có code_verifier. State ràng buộc response với transaction đã khởi tạo và chống response injection/login CSRF. OIDC nonce ràng buộc ID token với authentication request. Không cơ chế nào thay thế hoàn toàn cơ chế khác.

## 7. Redirect URI registration và validation

Authorization server cần quản lý redirect URI theo client registration. Không cho client gửi một redirect URI mới bất kỳ trong request rồi tin đó là đích hợp lệ.

### 7.1. Exact matching

- Đăng ký URI cụ thể cho từng app/environment.
- So khớp scheme, host, port, path và quy tắc query theo protocol.
- Không dùng wildcard host/path rộng.
- Không chấp nhận userinfo hoặc fragment nếu profile không cho phép.
- Không tự động chuẩn hóa theo cách khiến hai URI khác nhau trở thành cùng một callback ngoài ý muốn.
- Không redirect theo return_to, next hoặc URL do callback query tự khai.

Với custom scheme, đăng ký đúng reverse-domain scheme và callback path theo policy. Với claimed HTTPS redirect, đăng ký origin/path chính xác và duy trì domain association.

### 7.2. Môi trường dev/staging/production

Không dùng chung redirect URI và signing association giữa mọi môi trường nếu có thể tránh. Một app debug hoặc staging bị compromise không nên có khả năng nhận callback production. Tách client ID, redirect URI, signing fingerprint và trust configuration.

### 7.3. Error callback

OAuth error response cũng phải được ràng buộc với state transaction. Không hiển thị nguyên error_description từ authorization server như HTML tin cậy; escape output và chỉ hiển thị thông báo phù hợp. Xóa transaction pending khi user hủy hoặc flow thất bại theo policy, tránh state cũ được tái sử dụng.

## 8. Callback hijacking và code interception

### 8.1. Custom scheme hijacking

Nhiều app có thể khai báo cùng một private-use scheme. OS có thể hỏi người dùng, chọn app mặc định hoặc dispatch theo platform behavior. Attacker có thể tạo app giả đăng ký cùng scheme và nhận authorization code.

Giảm thiểu:

- Ưu tiên claimed HTTPS redirect (App Links/Universal Links).
- Dùng PKCE S256; verifier chỉ có trong app khởi tạo.
- Dùng state và OIDC nonce gắn transaction.
- Không nhúng client secret trong app.
- Giới hạn scope và lifetime của code/token.
- Authorization server exact-match redirect URI và yêu cầu PKCE.
- Phát hiện callback không khớp transaction; không đổi code nếu state sai.

### 8.2. Authorization code interception

Code là credential tạm nhưng vẫn nhạy cảm. Nếu attacker chặn code:

- PKCE làm code không đủ để đổi token khi thiếu verifier.
- Authorization code phải ngắn hạn và one-time.
- Token endpoint phải ràng buộc code với client và redirect URI.
- Không đưa code vào log, analytics hoặc crash report.
- Không chuyển tiếp code tới app/service khác.

### 8.3. Response injection và login CSRF

Attacker có thể cố đưa callback của một transaction do họ khởi tạo vào browser/app của nạn nhân. Nếu app không kiểm tra state và transaction binding, nạn nhân có thể bị đăng nhập vào account của attacker hoặc gắn nhầm session.

State phải ngẫu nhiên, khó đoán, gắn với transaction đang chờ và chỉ dùng một lần. Không dùng một state cố định cho mọi lần đăng nhập. Không coi việc callback đến đúng URI là bằng chứng response thuộc lần login mà app vừa mở.

## 9. Deep link và app navigation

Không phải mọi deep link đều là authentication callback. App có thể nhận link mở invoice, profile, payment hoặc password reset. Deep link là input bên ngoài và phải được validate như request.

Kiểm soát:

- Chỉ allowlist scheme, host, path và action cần thiết.
- Parse URL bằng thư viện chuẩn; tránh nối chuỗi thủ công.
- Không cho deep link gọi thẳng route đặc quyền hoặc bỏ qua login.
- Kiểm tra user/session hiện tại có quyền với resource được chỉ định.
- Không để query parameter ghi đè tenant, role hoặc user identity.
- Dùng one-time state cho link reset/verification và kiểm tra expiry.
- Không auto-execute hành động tài chính hoặc destructive chỉ vì app được mở qua link.
- Với link nhạy cảm, hiển thị confirmation và step-up phù hợp.

Ví dụ, deep link `https://app.example.com/invoice/123` chỉ yêu cầu app mở màn hình hóa đơn. Backend vẫn phải kiểm tra user có quyền đọc invoice 123. Không suy ra quyền từ việc link đã được ký hoặc domain đã được xác minh.

## 10. Session lifecycle sau redirect

Sau khi token exchange thành công, app cần tạo session local an toàn:

- Lưu refresh token hoặc credential dài hạn trong secure storage của OS khi flow yêu cầu.
- Access token ngắn hạn có thể giữ trong memory/cache theo policy.
- Không lưu token trong log, clipboard, notification payload hoặc analytics.
- Ràng buộc account/session với issuer, subject và client.
- Rotate refresh token nếu authorization server hỗ trợ và xử lý reuse detection.
- Xóa session local khi logout; revoke server-side token/session khi cần.
- Khi đổi account, xóa transaction/token cache của account cũ và tránh trộn state.
- Reauthenticate/step-up trước thao tác nhạy cảm theo auth age và risk.

### 10.1. Android secure storage

Android Keystore có thể tạo/giữ key không xuất được khỏi keystore; app có thể mã hóa dữ liệu token cần lưu bằng key được bảo vệ. Không lưu token plaintext trong SharedPreferences hoặc file log. Nếu dùng encrypted preferences/storage, bảo vệ master key bằng Android Keystore và xử lý backup/restore để secret không bị sao chép ngoài ý muốn.

### 10.2. iOS Keychain

iOS Keychain cung cấp vùng lưu credential được hệ điều hành quản lý. Chọn accessibility class phù hợp với yêu cầu thiết bị khóa, background access và đồng bộ. Không bật Keychain sync cho credential nhạy cảm nếu không có yêu cầu và threat model rõ. Xóa item khi logout hoặc account bị thu hồi theo policy.

Secure storage không bảo vệ token khỏi malware hoặc code đã chạy trong process app khi app đang sử dụng token. Giảm thời gian token ở memory, hạn chế logging và bảo vệ integrity của app.

## 11. Account switching, cancellation và retry

Mobile app có thể có nhiều login transaction đồng thời: người dùng mở hai tab, chuyển account hoặc nhấn login nhiều lần. Nếu app dùng một biến global pendingState hoặc currentVerifier, transaction sau có thể ghi đè transaction trước.

Thiết kế:

- Mỗi login transaction có ID riêng và state/verifier/nonce riêng.
- Callback tìm đúng transaction bằng state, không dùng transaction mới nhất.
- Mỗi transaction có TTL và trạng thái pending/consumed/cancelled.
- Callback đến trễ sau khi user hủy phải bị từ chối.
- Token response phải được gắn với transaction và account tương ứng.
- Atomic consume tránh hai callback đồng thời hoàn tất cùng transaction.
- Khi retry, tạo transaction và verifier mới; không tái dùng code verifier/state cũ ngoài policy.

Nếu app bị OS dừng trong lúc browser mở, transaction có thể cần lưu bền vững an toàn để app khởi động lại tiếp tục. Dữ liệu lưu phải được mã hóa/bảo vệ và có expiry; không dựa vào biến RAM duy nhất nếu UX cần process restoration.

## 12. Java/Kotlin và Swift: callback handling

Các ví dụ dưới đây là pseudocode minh họa nguyên tắc. Trong production, ưu tiên AppAuth hoặc SDK OAuth/OIDC được duy trì và API authentication session của nền tảng.

### 12.1. Android transaction model

~~~kotlin
data class PendingAuthTransaction(
    val id: String,
    val stateHash: String,
    val pkceVerifierEncrypted: ByteArray,
    val nonceHash: String,
    val redirectUri: Uri,
    val expiresAt: Instant,
    val status: TransactionStatus
)

fun beginLogin(): AuthorizationRequest {
    val verifier = secureRandomPkceVerifier()
    val state = secureRandomValue()
    val nonce = secureRandomValue()

    transactionStore.insert(
        createEncryptedTransaction(
            state = state,
            verifier = verifier,
            nonce = nonce,
            redirectUri = configuredRedirectUri,
            expiresAt = clock.instant().plusSeconds(300)
        )
    )

    return buildAuthorizationRequest(
        redirectUri = configuredRedirectUri,
        state = state,
        nonce = nonce,
        codeChallenge = s256(verifier),
        codeChallengeMethod = "S256"
    )
}
~~~

Transaction store cần mã hóa verifier, ràng buộc với app/client và có thao tác consume nguyên tử. Không ghi verifier hoặc state raw vào log.

### 12.2. Callback validation

~~~kotlin
fun completeLogin(callback: Uri): Result<Session> {
    requireExactRedirectUri(callback, configuredRedirectUri)

    val state = requireSingleQueryValue(callback, "state")
    val code = requireSingleQueryValue(callback, "code")
    val tx = transactionStore.findPendingByStateHash(sha256(state))
        ?: return Result.failure(InvalidCallback())

    if (tx.expiresAt <= clock.instant() ||
        tx.status != TransactionStatus.PENDING) {
        return Result.failure(StaleCallback())
    }

    val claim = transactionStore.claimForExchangeAtomically(tx.id)
        ?: return Result.failure(CallbackAlreadyProcessing())

    val tokens = tokenClient.exchangeCode(
        code = code,
        verifier = transactionStore.decryptVerifier(claim),
        redirectUri = claim.redirectUri
    )

    validateOidcResponse(tokens, expectedNonceHash = claim.nonceHash)
    sessionStore.commitForTransaction(claim.id, tokens)
    transactionStore.markCompleted(claim.id)
    return Result.success(sessionStore.findForTransaction(claim.id))
}
~~~

Đây là pseudocode; production phải xử lý OAuth error callback, duplicate parameter, network retry sau token exchange, transaction state transition và session commit sao cho không tạo trạng thái nửa hoàn tất. Nếu token endpoint đã consume code nhưng response bị mất, retry code có thể thất bại; không được mở lại transaction cũ và coi callback đó là mới. Thư viện OAuth/OIDC chuẩn thường đã xử lý nhiều chi tiết protocol và nên được ưu tiên.

### 12.3. iOS authentication session

~~~swift
let session = ASWebAuthenticationSession(
    url: authorizationURL,
    callbackURLScheme: callbackScheme
) { callbackURL, error in
    guard error == nil, let callbackURL = callbackURL else {
        handleCancelledOrFailedAuthentication(error)
        return
    }

    authCoordinator.validateAndComplete(callbackURL)
}

session.presentationContextProvider = presentationProvider
session.prefersEphemeralWebBrowserSession = false
session.start()
~~~

Ví dụ minh họa API hệ thống; với claimed HTTPS callback, cấu hình callback handling theo SDK/API và phiên bản OS đang dùng. callbackURLScheme không tự xác minh state, PKCE, issuer hoặc exact path. Auth coordinator vẫn phải kiểm tra transaction và token response. Chọn ephemeral browser session chỉ khi policy SSO/privacy yêu cầu; nó thay đổi cookie reuse và trải nghiệm đăng nhập.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Dùng embedded WebView cho OAuth login | App có thể kiểm soát hoặc quan sát trang xác thực | External user-agent/system browser |
| Custom scheme chung | App khác có thể đăng ký cùng callback | Claimed HTTPS link hoặc reverse-domain scheme + PKCE |
| Không dùng PKCE | App nhận nhầm code có thể đổi token | Authorization Code + PKCE S256 |
| Không kiểm tra state | Response injection/login CSRF | State ngẫu nhiên, transaction binding, one-time |
| Bỏ OIDC nonce | ID token có thể bị ghép từ authentication request khác | Nonce riêng và kiểm tra trong ID token |
| Redirect URI wildcard | Code có thể bị gửi tới host/path attacker | Exact registration và matching |
| Client secret nhúng trong app | Secret có thể bị trích xuất từ binary | Public client + PKCE |
| Tin callback chỉ vì OS mở app | Callback có thể sai transaction hoặc bị app khác gửi | Validate URI, state, expiry và transaction |
| Chấp nhận duplicate query parameters | Parser khác nhau có thể chọn giá trị khác | Từ chối duplicate/ambiguous parameters |
| Dùng global pending verifier | Concurrent login/account switching làm lẫn transaction | Store theo transaction ID/state |
| Log callback URL hoặc code | Lộ authorization code và metadata | Redaction và URL hygiene |
| Lưu refresh token trong plaintext | Backup/file compromise làm lộ credential | Keystore/Keychain và rotation |
| Deep link tự thực hiện action | Link ngoài có thể kích hoạt thao tác nhạy cảm | Authorization và explicit confirmation |
| Universal/App Links cấu hình sai | App không nhận link hoặc domain trust bị chiếm | Verify association, signing fingerprint và domain |
| Chỉ dựa vào PKCE mà bỏ state | Vẫn có thể gặp login CSRF/response mix-up | PKCE, state và nonce theo đúng vai trò |
| Token exchange retry không idempotent | Callback có thể tạo session/side effect lặp | Transaction state machine và xử lý code one-time |

## 14. Ma trận kiểm thử app redirect

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Login bình thường qua system browser | Callback đúng app và đúng transaction |
| Callback có state không khớp | Từ chối, không đổi code |
| Callback state đã dùng | Từ chối replay |
| Callback transaction hết hạn | Từ chối |
| App khác đăng ký cùng custom scheme | Không thể đổi code nếu thiếu PKCE verifier |
| Authorization code bị chặn ở callback | Token endpoint từ chối nếu thiếu/wrong verifier |
| PKCE challenge dùng plain khi policy yêu cầu S256 | Authorization server từ chối |
| Redirect URI khác path/host/port đã đăng ký | Authorization server hoặc app từ chối |
| Callback có code/state trùng lặp | Từ chối ambiguous response |
| Callback có issuer/authorization server không mong đợi | Từ chối theo issuer/transaction binding |
| ID token nonce sai | Từ chối authentication result |
| Custom scheme bị app giả chiếm | PKCE/state ngăn hoàn tất transaction |
| Android App Links association sai fingerprint | Domain verification không đạt; không tin association |
| iOS AASA thiếu app identifier/path | Universal Link không được xác minh cho route |
| App nhận deep link tới resource khác tenant | Backend authorization từ chối |
| Người dùng hủy browser session | Transaction bị đánh dấu cancelled/expired |
| Hai login transaction chạy đồng thời | Callback hoàn tất đúng transaction theo state |
| Callback đến sau khi user đổi account | Không gắn token vào account/session khác |
| App bị kill rồi khởi động lại | Chỉ resume transaction còn hạn và được lưu an toàn |
| Token exchange timeout sau khi code có thể đã consume | Retry/restart theo protocol; không tạo session mơ hồ |
| Refresh token lưu trữ | Dùng secure storage và không xuất hiện trong backup/log ngoài policy |
| Logout | Session/token bị revoke hoặc xóa theo policy; callback cũ không tái đăng nhập |
| Error callback từ IdP | State được xác minh; error text được escape |
| Callback URL được gửi tới analytics | Test xác nhận code/verifier/token không bị gửi |
| Embedded WebView được bật cho OAuth | Architecture/test policy phát hiện và từ chối |

### Tình huống thực hành

Một app Android dùng custom scheme `companyauth://callback`. App không dùng PKCE vì developer cho rằng scheme chỉ thuộc app của công ty. App giữ một biến `pendingState` và một `pendingVerifier` toàn cục. Người dùng nhấn đăng nhập hai lần cho hai account. Một app khác trên thiết bị cũng đăng ký scheme đó và nhận callback đầu tiên. Backend authorization server chấp nhận redirect URI wildcard cho mọi path của scheme.

**Yêu cầu:** xác định lỗi và thiết kế lại.

**Hướng phân tích:**

1. Custom scheme không có quyền sở hữu độc quyền; app khác có thể nhận callback.
2. Chuyển sang claimed HTTPS App Link nếu có domain control; nếu chưa thể, dùng reverse-domain private scheme và PKCE S256.
3. Authorization server exact-match redirect URI, yêu cầu PKCE cho public client và không dùng wildcard.
4. Mỗi login có state, verifier, nonce và transaction ID riêng; lưu an toàn, có TTL và consume một lần.
5. Callback kiểm tra exact URI, một state/code duy nhất, transaction pending và expiry trước token exchange.
6. Token endpoint xác minh code, client, redirect URI và verifier; app xác minh ID token issuer/audience/signature/nonce.
7. Không nhúng client secret; không log code/state/verifier/token.
8. Hủy transaction cũ khi user cancel/account switch; không để callback cũ tạo session sau khi đổi account.

## 15. Câu hỏi tự kiểm tra

1. **App redirect là gì?** Là cơ chế browser/IdP đưa người dùng quay lại native app qua URI đã đăng ký sau một bước xác thực hoặc consent.
2. **Vì sao native app nên dùng external user-agent?** Giữ trang xác thực trong browser/OS context đáng tin, giảm app quan sát credential và hỗ trợ SSO.
3. **Custom URI scheme có rủi ro gì?** App khác có thể đăng ký cùng scheme và nhận authorization response.
4. **Claimed HTTPS App Links/Universal Links giúp gì?** OS xác minh quan hệ domain-app, giảm nguy cơ app không liên quan chiếm callback.
5. **PKCE bảo vệ điều gì?** Authorization code bị chặn không đủ để đổi token nếu attacker không có code_verifier.
6. **State và nonce khác nhau thế nào?** State ràng buộc callback với transaction của client; OIDC nonce ràng buộc ID token với authentication request.
7. **Vì sao redirect URI phải exact-match?** Ngăn authorization code bị chuyển tới host/path ngoài ý muốn.
8. **Có nên lưu client secret trong APK/IPA?** Không. Native app là public client; dùng PKCE và cơ chế client phù hợp.
9. **Deep link đã được xác minh có tự cấp quyền đọc tài nguyên không?** Không. Backend vẫn phải kiểm tra user/session, tenant và object authorization.
10. **Vì sao mỗi login transaction cần verifier riêng?** Tránh callback của login này dùng state/verifier hoặc session của login khác.

**Ghi nhớ:** App redirect là một ranh giới xác thực nhạy cảm giữa browser, OS và native app. Dùng external user-agent, Authorization Code Flow với PKCE S256, redirect URI exact-match, ưu tiên claimed HTTPS App Links/Universal Links, và ràng buộc callback bằng state/nonce/transaction riêng. Xem mọi deep link là input không tin cậy, lưu verifier/token trong secure storage phù hợp, xử lý callback một lần và không để app khác hoặc callback cũ hoàn tất đăng nhập thay người dùng.
