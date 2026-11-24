# Deep link — Thiết kế liên kết sâu an toàn cho xác thực mobile

> **Chương:** Authentication trong mobile  
> **Chủ đề:** Deep link  
> **Phạm vi:** Security Authentication Fundamentals — hiểu cách hệ điều hành chuyển URL tới ứng dụng mobile, phân biệt custom scheme với verified app/universal links, bảo vệ OAuth/OIDC callback, magic link và recovery link khỏi chiếm handler, open redirect, token leakage, replay và nhầm lẫn danh tính.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích deep link và phân biệt điều hướng nội bộ với callback mang dữ liệu xác thực.
2. So sánh custom URL scheme, Android App Links và iOS Universal Links.
3. Thiết lập domain association để hệ điều hành xác minh ứng dụng được phép xử lý HTTPS link.
4. Thiết kế OAuth/OIDC redirect cho native app bằng external user-agent, exact redirect matching, state và PKCE.
5. Ngăn app khác chiếm custom scheme, giả mạo callback hoặc chuyển code tới client không hợp lệ.
6. Bảo vệ magic link, email verification và account recovery link khỏi leakage, prefetch và replay.
7. Xác thực, canonicalize và route URI an toàn; tránh open redirect, parameter pollution và confusion giữa tenant/account.
8. Quản lý token, session và transaction state trong mobile app an toàn.
9. Xây dựng fallback khi app chưa cài, link không được xác minh hoặc callback bị gián đoạn.
10. Kiểm thử deep link trên Android/iOS, browser, email client, app link association và các tình huống tấn công.

## 1. Deep link là gì?

**Deep link** là URL hoặc URI đưa người dùng tới một màn hình, nội dung hoặc hành động cụ thể bên trong ứng dụng. Thay vì chỉ mở trang chủ, một liên kết có thể mở thẳng trang đơn hàng, màn hình hồ sơ, bước xác minh email hoặc callback của một luồng đăng nhập.

Ví dụ:

- Mở trang chi tiết đơn hàng trong app;
- Mở màn hình đặt lại mật khẩu;
- Xác nhận địa chỉ email;
- Quay lại ứng dụng sau khi người dùng đăng nhập tại identity provider;
- Mở màn hình MFA hoặc consent;
- Mời người dùng tham gia workspace.

Deep link có thể chỉ chứa dữ liệu định tuyến vô hại, nhưng cũng có thể mang authorization code, state, token hoặc một secret dùng một lần. Mức bảo vệ phải dựa trên dữ liệu và hành động mà link kích hoạt.

### Hai nhóm cần phân biệt

| Nhóm | Ví dụ | Yêu cầu bảo mật |
| --- | --- | --- |
| Navigation link | Mở màn hình đơn hàng hoặc bài viết | Xác thực URI, resource authorization và không tin dữ liệu route từ caller |
| Authentication/action link | OAuth callback, magic link, email verification, password reset | Binding với transaction/account, expiry, single-use, chống replay và leakage |

Một URL mở được app không chứng minh người mở có quyền xem resource. App vẫn phải xác thực session và kiểm tra authorization ở server.

## 2. Deep link là một ranh giới tin cậy

Khi người dùng nhấn một link, dữ liệu đi qua nhiều thành phần:

1. Email client, browser, chat app hoặc ứng dụng nguồn;
2. Hệ điều hành phân giải URI và chọn handler;
3. Ứng dụng nhận URL qua intent/activity hoặc universal-link callback;
4. Router trong app phân tích path và query;
5. Authentication client xử lý state, code hoặc token;
6. Backend xác minh transaction và cấp session/quyền.

Mỗi bước có thể bị giả mạo, thay đổi, ghi log hoặc chuyển tiếp. Vì vậy, không được xem URL là dữ liệu tin cậy chỉ vì hệ điều hành đã mở ứng dụng.

### Trust boundary

`````````mermaid
flowchart TD
    A["Email/browser/chat link"] --> B["OS URI resolver"]
    B --> C["App link association / scheme handler"]
    C --> D["Mobile app deep-link router"]
    D --> E["Validate scheme, host, path, state"]
    E --> F["Authentication backend / token endpoint"]
    F --> G{"Transaction and proof valid?"}
    G -- "No" --> H["Reject, clear transient state, audit"]
    G -- "Yes" --> I["Complete flow and establish session"]
`````````

OS association chỉ giúp chọn app handler đáng tin cậy cho domain. Nó không xác minh user, không xác minh quyền truy cập resource và không bảo đảm query parameter chưa bị attacker thay đổi.

## 3. Các loại deep link trên mobile

### Custom URL scheme

Ví dụ minh họa:

`````````text
acmeapp://auth/callback?code=...&state=...
`````````

Ứng dụng đăng ký một scheme riêng với hệ điều hành. Khi URL được mở, OS tìm app đã khai báo scheme đó.

Ưu điểm:

- Dễ tích hợp với ứng dụng cũ;
- Có thể dùng khi không kiểm soát domain HTTPS;
- URI ngắn và có thể định tuyến trực tiếp.

Rủi ro:

- App khác có thể đăng ký cùng scheme;
- OS có thể hiển thị chooser hoặc chọn handler không mong đợi;
- Không có xác minh domain-to-app mặc định;
- Callback có thể bị app khác nhận trước hoặc quan sát;
- Scheme collision và app impersonation.

Không dùng custom scheme làm bằng chứng duy nhất rằng callback đến đúng ứng dụng. Nếu buộc phải dùng, cần PKCE, state, exact redirect URI, transaction binding và không gửi access token trực tiếp trong URL.

### Android App Links

Android App Links dùng HTTPS URL thuộc domain mà ứng dụng được xác minh liên kết. Domain công bố association file tại đường dẫn well-known; Android kiểm tra mối liên hệ giữa website và package/signing certificate của ứng dụng.

Ví dụ domain association file:

`````````json
{
  "relation": [
    "delegate_permission/common.handle_all_urls"
  ],
  "target": {
    "namespace": "android_app",
    "package_name": "com.example.acme",
    "sha256_cert_fingerprints": [
      "AA:BB:CC:DD:..."
    ]
  }
}
`````````

File trên là ví dụ cấu trúc rút gọn; production cần tuân theo định dạng Digital Asset Links đầy đủ và fingerprint đúng với signing certificate thực tế, kể cả cấu hình Play App Signing.

### iOS Universal Links

iOS Universal Links dùng HTTPS URL và file apple-app-site-association (AASA) trên domain để khai báo app identifier/team và các path được phép mở trong app.

Ví dụ minh họa:

`````````json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["ABCDE12345.com.example.acme"],
        "components": [
          { "/": "/auth/*" },
          { "/": "/orders/*" }
        ]
      }
    ]
  }
}
`````````

Đây là ví dụ rút gọn. File AASA cần đúng schema theo phiên bản iOS được hỗ trợ, được phục vụ qua HTTPS và đặt tại vị trí Apple yêu cầu. App entitlement Associated Domains phải khai báo đúng domain.

### So sánh

| Cơ chế | Xác minh domain/app | Dạng URI | Gợi ý |
| --- | --- | --- | --- |
| Custom scheme | Không có domain association mặc định | appname:// | Chỉ dùng khi cần tương thích và có bảo vệ bổ sung |
| Android App Links | Digital Asset Links + package/signing fingerprint | https:// | Ưu tiên cho link domain do tổ chức kiểm soát |
| iOS Universal Links | AASA + Associated Domains entitlement | https:// | Ưu tiên cho link domain do tổ chức kiểm soát |

Verified app/universal links giảm nguy cơ app khác chiếm handler, nhưng không thay thế kiểm tra transaction và authorization trong app/backend.

## 4. Cấu hình domain association an toàn

Domain association là bằng chứng rằng website cho phép một ứng dụng cụ thể xử lý một tập URL. Cấu hình sai có thể khiến link mở sai app, không mở app hoặc mở path ngoài ý muốn.

### Android App Links

- Khai báo intent filter cho HTTPS scheme, host và path cần thiết;
- Bật auto verification theo cấu hình Android phù hợp;
- Phục vụ assetlinks.json qua HTTPS tại well-known path;
- Khai báo package name chính xác;
- Dùng SHA-256 fingerprint của signing certificate đúng môi trường;
- Kiểm tra cả debug, staging và production certificate;
- Chỉ khai báo path app thực sự cần xử lý;
- Kiểm tra trạng thái domain verification trên các phiên bản Android mục tiêu.

### iOS Universal Links

- Bật Associated Domains entitlement;
- Khai báo applinks domain chính xác;
- Phục vụ AASA qua HTTPS với content type và vị trí hợp lệ;
- Khai báo đúng Team ID/Bundle ID;
- Chỉ cho phép path cần thiết;
- Kiểm tra redirect, CDN và cache của AASA;
- Kiểm thử sau khi thay app signing hoặc domain configuration.

### Quản lý domain

- Dùng domain HTTPS do tổ chức kiểm soát;
- Không dùng domain shortener hoặc redirector không kiểm soát cho callback xác thực;
- Bảo vệ DNS, TLS certificate và hosting của association file;
- Theo dõi thay đổi AASA/assetlinks;
- Tránh wildcard path rộng hơn nhu cầu;
- Tách domain production và non-production khi phù hợp.

Nếu attacker chiếm quyền domain hoặc sửa association file, trust relationship có thể bị thay đổi. Domain ownership và file hosting cần được bảo vệ như một phần của authentication infrastructure.

## 5. Thiết kế URI và route an toàn

Deep-link router phải coi URI là input không tin cậy. Link có thể do user, website khác, QR code, notification, app khác hoặc attacker tạo.

### Kiểm tra cấu trúc

- Chỉ chấp nhận scheme mong đợi;
- Kiểm tra host chính xác;
- Chuẩn hóa path và xử lý encoding nhất quán;
- Từ chối userinfo, port hoặc authority bất thường nếu không thuộc contract;
- Kiểm tra query parameter bắt buộc và từ chối duplicate parameter nhạy cảm;
- Giới hạn độ dài URI và số lượng parameter;
- Không chấp nhận fragment làm nguồn credential nếu flow không định nghĩa;
- Không parse một lần ở gateway rồi parse khác ở app.

### Canonicalization

Các biểu diễn URI khác nhau có thể trỏ tới cùng resource hoặc bypass allowlist nếu hệ thống canonicalize không nhất quán. Cần xác định quy tắc cho:

- Percent encoding;
- Unicode/IDN hostname;
- Dấu chấm và slash lặp;
- Path traversal segment;
- Case sensitivity của host/path theo routing contract;
- Query parameter trùng lặp;
- Redirect URL được encode nhiều lần.

Không tự viết URI parser bằng split chuỗi đơn giản. Dùng thư viện chuẩn của nền tảng, sau đó so sánh scheme/host/path theo policy.

### Route không cấp quyền

Ví dụ link:

`````````text
https://links.example.com/orders/ORD-1042
`````````

App có thể mở màn hình order ORD-1042, nhưng backend vẫn phải xác minh session và kiểm tra caller có quyền xem order đó. Không dùng ID trong URL như một authorization decision.

## 6. Deep link và OAuth/OIDC trên native app

Native app thường là public client: binary được cài trên thiết bị người dùng và không thể giữ client secret như một confidential server. Không nhúng client secret vào app để coi đó là bí mật.

### External user-agent

Best practice cho native app là dùng browser/system authentication session làm external user-agent để người dùng đăng nhập trực tiếp tại identity provider. Tránh thu thập password IdP trong embedded WebView do app kiểm soát.

Trên iOS, có thể dùng ASWebAuthenticationSession hoặc cơ chế hệ thống tương đương. Trên Android, có thể dùng browser qua Custom Tabs hoặc cơ chế external user-agent phù hợp.

### Authorization Code Flow + PKCE

Luồng điển hình:

1. App tạo state ngẫu nhiên và code_verifier ngẫu nhiên;
2. App tạo code_challenge từ verifier theo PKCE;
3. App mở authorization endpoint trong external user-agent;
4. IdP xác thực người dùng và trả authorization code tới redirect URI;
5. OS chuyển HTTPS app link hoặc custom scheme callback tới app;
6. App kiểm tra state khớp transaction đang chờ;
7. App gửi code cùng code_verifier tới token endpoint;
8. Authorization server xác minh PKCE và cấp token;
9. App xác minh token theo thư viện/protocol profile và lưu token an toàn.

### Sơ đồ sequence

`````````mermaid
sequenceDiagram
    participant App as Native app
    participant Browser as System browser
    participant IdP as Identity provider
    participant OS as Mobile OS
    App->>App: Generate state and PKCE verifier
    App->>Browser: Open authorization request
    Browser->>IdP: User authentication
    IdP-->>Browser: Redirect with code and state
    Browser->>OS: HTTPS app link callback
    OS->>App: Deliver callback URI
    App->>App: Validate state and transaction
    App->>IdP: Exchange code + PKCE verifier
    IdP-->>App: Tokens
`````````

### Kiểm tra callback

- Redirect URI phải khớp chính xác với URI đã đăng ký;
- State phải tồn tại, chưa dùng, chưa hết hạn và thuộc đúng login transaction;
- Authorization code chỉ được đổi một lần;
- PKCE verifier phải được giữ riêng cho transaction;
- Kiểm tra issuer/authorization server nếu client hỗ trợ nhiều IdP;
- Xác minh ID token theo OIDC: signature, issuer, audience, expiry, nonce nếu đã gửi;
- Không tạo session chỉ vì nhận được một code parameter;
- Xóa transaction tạm sau thành công hoặc thất bại.

State chống callback injection/CSRF và liên kết response với request; PKCE bảo vệ code khỏi bị dùng bởi app khác lấy được code. Hai cơ chế bổ sung nhau, không thay thế nhau.

## 7. Redirect URI và nguy cơ app khác chiếm callback

### Custom scheme collision

Nếu hai ứng dụng đăng ký cùng custom scheme, hệ điều hành có thể không đảm bảo callback được chuyển tới app mong muốn. Attacker có thể tạo app giả đăng ký scheme giống app thật để nhận authorization code.

### Bảo vệ

- Ưu tiên claimed HTTPS redirect như App Links/Universal Links khi hỗ trợ;
- Dùng Authorization Code + PKCE;
- Không gửi access token trực tiếp trong redirect URI;
- Đăng ký exact redirect URI, không dùng wildcard host/path;
- Validate state và transaction;
- Kiểm tra issuer khi có nhiều authorization server;
- Không chấp nhận callback không có transaction đang chờ;
- Không log callback URL nguyên vẹn.

### Custom scheme khi bắt buộc

Nếu hệ sinh thái hoặc IdP yêu cầu custom scheme:

- Dùng scheme có namespace do ứng dụng sở hữu;
- Hạn chế path callback và kiểm tra đầy đủ;
- Dùng PKCE S256;
- State ngẫu nhiên, one-time;
- Authorization code ngắn hạn và single-use;
- Xác minh redirect URI ở authorization server;
- Không dựa vào package name do callback tự khai báo;
- Kiểm thử với một app khác cố đăng ký cùng scheme.

Custom scheme không có domain verification tương đương App Links/Universal Links. PKCE giảm tác động code interception nhưng không tự xác minh app nhận callback là app chính chủ trong mọi tình huống.

## 8. State, nonce và transaction binding

Deep link xác thực cần liên kết callback với một transaction do app khởi tạo. Không được xử lý callback như một request độc lập.

### State

State là giá trị ngẫu nhiên để liên kết authorization response với transaction khởi tạo. App cần lưu state ở vùng nhớ an toàn cho transaction, gắn với redirect/issuer và đánh dấu đã consume.

### Nonce

Trong OIDC, nonce được gửi trong authentication request để liên kết ID token với request đó. Client kiểm tra nonce claim trong ID token nếu đã gửi nonce. State và nonce có mục đích khác nhau.

### Transaction record

Có thể lưu tạm:

`````````json
{
  "transaction_id": "tx-9c31",
  "state_hash": "server-or-client-side-verifier",
  "issuer": "https://id.example.com",
  "redirect_uri": "https://links.example.com/mobile/callback",
  "pkce_verifier_ref": "secure-local-reference",
  "nonce": "random-oidc-nonce",
  "created_at": "2026-11-22T06:30:00Z",
  "expires_at": "2026-11-22T06:35:00Z",
  "status": "PENDING"
}
`````````

Đây là ví dụ schema khái niệm. Không ghi code_verifier hoặc token vào log. Secret cần lưu trong vùng bảo vệ của app và chỉ tồn tại đủ lâu cho transaction.

### Chống callback lặp

- State chỉ được chấp nhận một lần;
- Transaction hết hạn bị từ chối;
- Callback sai issuer/redirect/tenant bị từ chối;
- Hai callback đồng thời không được cùng hoàn tất transaction;
- Callback đã hoàn tất không được tạo session thứ hai;
- Dữ liệu tạm được xóa theo policy sau success/failure.

## 9. Magic link, email verification và recovery link

Magic link cho phép người dùng nhấn link trong email để đăng nhập hoặc hoàn thành một hành động. Nó tiện lợi nhưng URL trở thành một bearer secret nếu chứa token dùng để xác thực.

### Rủi ro

- Email bị forward hoặc mailbox bị compromise;
- Link bị ghi vào browser history, proxy log hoặc analytics;
- Email security scanner tự động mở link trước người dùng;
- Link bị copy sang thiết bị/app khác;
- Token bị replay trong thời hạn;
- Universal link association bị cấu hình sai;
- App hiển thị nội dung account trước khi backend xác minh token.

### Thiết kế token

- Token ngẫu nhiên có entropy cao;
- Lưu hash/verifier ở server thay vì plaintext khi phù hợp;
- Gắn token với account, purpose và transaction;
- Expiry ngắn theo risk;
- Single-use với atomic consumption;
- Không dùng cùng token cho login, email verification và password reset;
- Rate limit việc yêu cầu gửi link;
- Thông báo khi link được dùng hoặc thay đổi credential nhạy cảm.

### Email scanner và GET side effect

Nhiều hệ thống email/security tự động truy cập URL để kiểm tra phishing. Nếu một GET request lập tức tiêu thụ token và thay đổi trạng thái account, scanner có thể làm link mất hiệu lực trước khi người dùng nhấn.

Với hành động nhạy cảm, không nên để một GET đơn thuần hoàn tất side effect. Có thể dùng trang xác nhận trung gian: GET chỉ hiển thị transaction, sau đó user action rõ ràng gửi POST để xác minh/consume token; hoặc thiết kế handoff an toàn khác có khả năng chịu prefetch. Phải cân nhắc token exposure và không để trang trung gian trở thành open redirect.

### Không đưa access token vào deep link

Không gửi bearer access token hoặc refresh token qua URL callback. URL có thể được ghi vào browser/app logs và chuyển tới app khác. Với OAuth native app, dùng authorization code + PKCE rồi đổi code qua token endpoint.

## 10. App chưa cài, fallback và deferred deep link

Khi người dùng mở link nhưng app chưa được cài, domain có thể mở trang web fallback. Fallback cần có hành vi rõ ràng và không làm rò rỉ token.

### Fallback an toàn

- Trang web HTTPS thuộc domain kiểm soát;
- Chỉ hiển thị nội dung được phép trước khi xác thực;
- Có nút cài app từ store chính thức;
- Không chuyển token/secret vào query parameter của store URL;
- Không redirect tới domain tùy ý;
- Sau khi cài, nếu hỗ trợ deferred deep link, server phải xác minh transaction và expiry lại.

### Deferred deep link

Deferred deep link cố gắng đưa người dùng tới đúng nội dung sau khi cài app. Không nên dựa vào việc lưu nguyên authorization code hoặc bearer token trong clipboard, install referrer hoặc attribution parameter. Hãy lưu một opaque transaction reference, sau đó yêu cầu server xác minh trạng thái, account binding, expiry và user intent khi app khởi động.

### Fallback không được nâng quyền

Nếu app không mở được, browser fallback không được tự coi người dùng đã xác thực. Mọi action cần tiếp tục qua authentication flow an toàn trên web hoặc app.

## 11. Xử lý callback trong Android

Android nhận deep link qua intent filter và có thể chuyển URL vào Activity. Ứng dụng phải xác minh URI trước khi route.

### Intent filter

Ví dụ minh họa:

`````````xml
<activity
    android:name=".AuthCallbackActivity"
    android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data
            android:scheme="https"
            android:host="links.example.com"
            android:pathPrefix="/mobile/callback" />
    </intent-filter>
</activity>
`````````

Đây là cấu hình minh họa. Cần kiểm tra exported, intent filter, host/path, app signing và verified link state theo Android version. Nếu Activity exported, mọi app có thể thử gửi intent trực tiếp; do đó callback phải được xác minh ở app và server, không dựa vào nguồn intent.

### Kiểm tra intent

- Chỉ xử lý action VIEW và data URI đúng contract;
- Parse bằng Uri API;
- Kiểm tra scheme/host/path chính xác;
- Từ chối duplicate code/state hoặc parameter bất thường;
- Không tin extras tùy ý từ caller;
- Không tự động route tới WebView hoặc URL bất kỳ;
- Chống xử lý lặp khi Activity được tái tạo hoặc nhận onNewIntent;
- Xác minh transaction state trước khi gọi token endpoint.

### Android App Links

Đảm bảo assetlinks.json được phục vụ đúng và package/fingerprint khớp bản phát hành. Kiểm thử app link verification sau khi đổi signing key, app ID hoặc domain. Không giả định intent filter tự chứng minh domain đã được verify.

## 12. Xử lý callback trong iOS

iOS Universal Links được chuyển tới app qua lifecycle callback phù hợp, thường là scene delegate hoặc app delegate tùy kiến trúc.

### Universal Links

- Cấu hình Associated Domains entitlement;
- Phục vụ AASA đúng domain;
- Xử lý continuation user activity;
- Kiểm tra URL host/path theo allowlist;
- Xác minh state/transaction trước khi đổi authorization code;
- Xử lý trường hợp app không được mở và browser hiển thị website.

### Custom URL scheme

Custom scheme có thể được nhận qua URL handling callback. Vì scheme có thể bị app khác đăng ký, cần xem nó là input không tin cậy và áp dụng PKCE/state/exact redirect matching.

### Không tin callback chỉ vì iOS gọi app

OS routing không chứng minh callback thuộc transaction đang chờ. App cần kiểm tra transaction ID/state, issuer, expiry, redirect URI và one-time semantics ở server.

## 13. Open redirect và link wrapping

Một số dịch vụ email hoặc marketing bọc link qua redirector để đo click. Nếu redirector không được kiểm soát, nó có thể làm rò token hoặc tạo đường open redirect.

### Open redirect

Nếu app/web chấp nhận URL đích tùy ý từ query parameter, attacker có thể tạo link trông như thuộc domain tin cậy nhưng cuối cùng chuyển người dùng tới website giả.

Kiểm soát:

- Không dùng redirect target tùy ý;
- Dùng allowlist origin/path;
- Ưu tiên opaque route ID thay URL đầy đủ;
- Canonicalize trước khi so sánh;
- Chặn scheme không phải HTTPS nếu không được định nghĩa;
- Không redirect kèm authorization code/token tới host khác;
- Giữ nguyên state và transaction binding qua các bước hợp lệ.

### Link wrapping

Nếu email provider bọc URL, callback xác thực cần đi qua domain redirector được đánh giá và cấu hình rõ. Tốt hơn là dùng domain first-party cho magic link/OAuth callback. Không cho redirector log query chứa secret.

### Referrer và browser leakage

Trang landing có token trong URL nên dùng Referrer-Policy phù hợp, tránh tải third-party resource, không gửi URL đầy đủ tới analytics và chuyển secret khỏi URL sớm nhất có thể. Header không thể xóa những bản đã bị ghi ở hệ thống trung gian; thiết kế token cần giới hạn tác động nếu bị lộ.

## 14. URI parameter pollution và parser confusion

Attacker có thể thêm parameter trùng hoặc tạo cách encode khác nhau để app và backend hiểu URI khác nhau.

Ví dụ:

`````````text
https://links.example.com/auth/callback?state=expected&state=attacker
https://links.example.com/auth/callback?code=one&code=two
`````````

### Quy tắc

- Với parameter nhạy cảm như code, state, issuer, tenant, chỉ chấp nhận đúng số lượng theo protocol;
- Từ chối duplicate parameter nếu semantics không cho phép;
- Dùng cùng một parser/canonicalization policy xuyên suốt;
- Không trộn query và fragment như hai nguồn credential;
- Từ chối URI quá dài hoặc encoding lỗi;
- Không dùng substring matching cho host;
- Không coi suffix domain là bằng chứng domain thuộc tổ chức.

Kiểm tra host phải là so sánh hostname đã parse và canonicalize, không phải kiểm tra chuỗi có chứa links.example.com. Ví dụ attacker.example.com?next=links.example.com không thuộc domain tin cậy.

## 15. Token storage và app lifecycle

Sau khi deep link hoàn tất authentication, app cần lưu token/session phù hợp với nền tảng và threat model.

### Lưu token

- Ưu tiên Keychain trên iOS và Android Keystore-backed storage;
- Không lưu token trong log, clipboard, URL hoặc analytics;
- Tránh lưu bearer token trong plain SharedPreferences/UserDefaults;
- Dùng access token có lifetime phù hợp;
- Bảo vệ refresh token và rotation/reuse detection;
- Thu hồi token khi logout, account recovery hoặc compromise;
- Không backup secret sang cloud backup không kiểm soát.

### App lifecycle

- Không giữ authorization code trong global variable lâu hơn cần thiết;
- Xóa state/PKCE verifier sau khi exchange hoặc khi transaction hết hạn;
- Xử lý app bị kill giữa chừng và callback đến sau khi app khởi động lại;
- Không hoàn tất transaction hai lần sau process recreation;
- Khóa màn hình nhạy cảm khi app ở background theo risk;
- Không hiển thị nội dung riêng tư từ notification/deep link trước khi session được xác minh.

### Device binding

Nếu cần sender-constrained token hoặc key-based proof, khóa nên được tạo và giữ trong platform keystore khi có thể. Device binding cần threat model riêng: root/jailbreak hoặc malware có thể thay đổi assurance, và không nên tuyên bố thiết bị an toàn chỉ dựa trên một tín hiệu đơn lẻ.

## 16. Multi-account, tenant và account linking

Một app có thể đăng nhập nhiều account hoặc nhiều tenant. Deep link cần chỉ rõ transaction thuộc account/tenant nào mà không cho caller tự đổi binding.

### Rủi ro

- Callback của account A được xử lý trong context account B;
- Tenant ID trong URL bị sửa;
- Magic link gửi cho email A nhưng app đang đăng nhập email B;
- Link invitation được dùng để nâng quyền account khác;
- App tự liên kết account theo email không được xác minh.

### Kiểm soát

- Gắn transaction với subject/tenant hoặc trạng thái chưa xác định rõ;
- Xác minh issuer và audience;
- So sánh account context sau khi token exchange;
- Với account linking, yêu cầu xác thực/consent phù hợp cho cả hai danh tính;
- Không dùng email claim làm khóa liên kết duy nhất nếu issuer/verified semantics chưa đủ tin cậy;
- Ghi audit cho link, unlink và tenant switch;
- Không cho link mời tự cấp role vượt policy.

Nếu magic link được dùng để đăng nhập, server phải xác định account từ token record đã phát hành. Không tin account ID hoặc email do URI caller truyền vào.

## 17. Logging, monitoring và privacy

Deep link có thể chứa code, state, token hoặc thông tin nhận diện. Logging URL đầy đủ là một nguồn rò rỉ phổ biến.

### Không log

- Authorization code;
- Access/refresh/ID token;
- Magic-link hoặc password-reset token;
- PKCE verifier;
- CSRF/state/nonce raw value;
- Session cookie;
- URL query/fragment nguyên vẹn nếu có secret;
- Private key hoặc raw assertion.

### Event nên ghi

| Event | Trường gợi ý |
| --- | --- |
| mobile.deeplink.received | App version, route class, source context đã làm sạch |
| mobile.deeplink.rejected | Reason code, scheme/host class, request ID |
| mobile.deeplink.association_failed | Platform, domain, association status |
| mobile.auth.callback.started | Transaction reference, issuer reference |
| mobile.auth.callback.state_failed | Transaction reference, reason code |
| mobile.auth.callback.completed | Transaction reference, result |
| mobile.magic_link.consumed | Token reference, purpose, result |
| mobile.magic_link.replay_rejected | Token reference, time and source context |
| mobile.session.created | Subject reference, auth method, session reference |

### Monitoring

- Tỷ lệ app link association failure;
- Callback state mismatch;
- Authorization code exchange failure;
- Duplicate/replayed callback;
- Magic link expired/reused;
- Redirect tới host ngoài allowlist;
- App version hoặc signing fingerprint bất thường;
- Tỷ lệ fallback browser/app;
- Token issuance từ callback bất thường;
- Deep link mở resource không có quyền.

Log cần có correlation ID để điều tra nhưng không lưu URI chứa secret. Dùng route template, host class và token reference thay vì raw query.

## 18. Threat model: tấn công deep link

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Custom scheme hijacking** | App khác đăng ký cùng scheme để nhận callback | Verified HTTPS links, PKCE, state, exact redirect |
| **App impersonation** | App giả mạo handler hoặc UI | Domain association, app signing, transaction verification |
| **Open redirect** | Link chuyển tới host do attacker kiểm soát | Allowlist, canonicalization, không nhận URL tùy ý |
| **Authorization code interception** | Code bị app khác đọc qua callback | PKCE S256, short-lived single-use code |
| **Callback injection** | Gửi callback không có transaction | State/nonce binding, transaction pending check |
| **Callback replay** | Gửi lại callback đã hoàn tất | Atomic consume và one-time code |
| **Magic link leakage** | Token lộ trong email/log/history | Opaque single-use token, no-store, redaction, short expiry |
| **Email scanner prefetch** | Scanner mở link trước user | GET không thực hiện side effect, explicit confirmation |
| **Parameter pollution** | Duplicate state/code/tenant làm parser khác nhau | Strict parser và reject duplicates |
| **Host confusion** | Kiểm tra substring thay vì parsed hostname | Exact host validation |
| **Cross-account confusion** | Link account A dùng trong session B | Subject/tenant transaction binding |
| **Deferred link abuse** | Install referrer chứa token cũ | Opaque reference, server-side expiry and verification |
| **Token in fragment/query** | Token bị log hoặc chuyển tiếp | Không đặt bearer token trong URL |
| **Universal link misconfiguration** | Association file cho path/app quá rộng | Least privilege cho domain/path và monitoring |
| **AASA/assetlinks takeover** | Domain hosting hoặc DNS bị chiếm | Domain security, TLS, change review |
| **WebView credential capture** | App thu password IdP trong embedded WebView | External user-agent |
| **Session fixation** | Callback nâng quyền session cũ | Rotate session ID sau authentication |
| **Intent spoofing** | App khác gửi intent trực tiếp | Xem intent là untrusted input, verify transaction server-side |

## 19. Tình huống thiết kế: đăng nhập app từ email magic link

Một ứng dụng bán hàng gửi email chứa link dạng HTTPS. Khi người dùng nhấn, link mở app và tự động đăng nhập. Hệ thống hiện lưu token dạng plaintext trong database, token hết hạn sau một ngày và GET request lập tức consume token. App cũng nhận callback qua custom scheme để hỗ trợ thiết bị cũ.

### Thiết kế ban đầu có vấn đề

1. Email scanner có thể mở link trước người dùng và làm token mất hiệu lực;
2. Token có thời hạn dài và được lưu plaintext;
3. Link có thể bị ghi vào proxy/email/browser log;
4. Custom scheme có thể bị app khác đăng ký;
5. Callback không có state hoặc transaction binding;
6. App có thể đăng nhập account A trong context đang chọn account B;
7. Token có thể được dùng lại nếu hai request đồng thời cùng đọc trạng thái pending;
8. Error response tiết lộ email có account hay không.

### Thiết kế lại

1. Tạo token ngẫu nhiên entropy cao; lưu verifier/hash và token reference ở server.
2. Gắn token với account, purpose=login, transaction và expiry ngắn theo risk.
3. Dùng HTTPS Universal Link/App Link đã xác minh domain làm đường chính.
4. Link GET chỉ tải trang/transaction confirmation; thao tác consume nhạy cảm yêu cầu user action rõ và POST.
5. Nếu mở app, app gửi opaque token reference/transaction proof tới backend qua TLS để xác minh.
6. Server consume token bằng thao tác atomic; request thứ hai bị từ chối.
7. App xác nhận subject/tenant với session context trước khi hoàn tất login.
8. Với OAuth federation, dùng external user-agent, authorization code + PKCE và state/nonce.
9. Không đưa access/refresh token vào URI; không log query hoặc fragment.
10. Nếu fallback custom scheme, vẫn dùng PKCE/state và chỉ chấp nhận callback có transaction đang chờ.
11. Sau thành công, tạo session mới, revoke session cũ theo policy và thông báo qua kênh phù hợp.
12. Response công khai không tiết lộ account existence; audit nội bộ giữ reason code.

### Kết quả mong đợi

- Email scanner không tự hoàn tất login;
- Token bị lộ có thời hạn và phạm vi sử dụng hạn chế;
- App khác không thể tự hoàn tất callback chỉ bằng cách nhận URL;
- Link không thể đổi account/tenant tùy ý;
- Replay đồng thời chỉ có một request thành công;
- Có thể fallback sang web an toàn nếu app không được cài.

## 20. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Verified Android App Link | Mở HTTPS link trên thiết bị có app đã verify | Mở đúng app/path |
| Android unverified domain | Mở link khi association không hợp lệ | Không giả định app là handler tin cậy |
| Android wrong fingerprint | Dùng assetlinks fingerprint sai | Domain verification thất bại |
| iOS Universal Link | Mở link với AASA/entitlement đúng | Mở đúng app |
| iOS AASA mismatch | Sai Team ID/Bundle ID/path | Link không được app xử lý như verified |
| Custom scheme collision | Cài app thử đăng ký cùng scheme | Flow vẫn được bảo vệ bởi PKCE/state; không cấp token cho app không hợp lệ |
| Wrong scheme | Gửi URI scheme ngoài allowlist | Từ chối |
| Wrong host | Gửi host gần giống domain tin cậy | Từ chối |
| Wrong path | Gửi path ngoài callback allowlist | Từ chối hoặc route an toàn |
| Duplicate state | Gửi state hai lần trong query | Từ chối |
| Duplicate code | Gửi hai authorization code | Từ chối |
| Missing transaction | Gửi callback không có login đang chờ | Từ chối |
| State mismatch | Gửi state khác transaction | Từ chối |
| State replay | Gửi lại callback đã hoàn tất | Không tạo session mới |
| Expired transaction | Gửi callback sau TTL | Từ chối |
| PKCE mismatch | Dùng verifier không khớp challenge | Token endpoint từ chối |
| Redirect URI mismatch | Dùng URI không khớp registration | Authorization/token flow từ chối |
| Wrong issuer | Gửi callback từ issuer khác | Từ chối |
| OIDC nonce mismatch | ID token có nonce sai | Client từ chối |
| Authorization code replay | Đổi code lần thứ hai | Token endpoint từ chối |
| Access token in URL | Kiểm tra link/callback | Không có bearer token trong URI |
| Magic link scanner | GET link tự động như email scanner | Không hoàn tất action nhạy cảm |
| Magic link consume | User xác nhận link hợp lệ | Token consume đúng một lần |
| Magic link race | Gửi hai POST đồng thời cùng token | Chỉ một request thành công |
| Magic link expiry | Dùng link sau expiry | Từ chối |
| Wrong account context | Dùng link account A khi app đang ở account B | Yêu cầu xác nhận/switch theo policy; không silently link |
| Open redirect | Đặt return URL tới domain ngoài | Bị từ chối |
| Host confusion | Dùng attacker.example?next=links.example.com | Bị từ chối |
| Percent encoding | Thử path/host encoding bất thường | Canonicalization nhất quán, reject ambiguity |
| Oversized URI | Gửi URI/query quá dài | Từ chối an toàn |
| Intent spoofing | App khác gửi intent trực tiếp tới exported activity | Không hoàn tất nếu thiếu transaction/proof |
| App lifecycle replay | Gửi callback sau process recreation | Transaction chỉ được xử lý một lần |
| App not installed | Mở link trên thiết bị không có app | HTTPS fallback an toàn |
| Deferred deep link | Cài app sau khi mở link | Server xác minh lại reference/expiry/user intent |
| Token storage | Kiểm tra storage/log/backup | Token được bảo vệ, không có plaintext log |
| Referrer leakage | Mở trang landing có token context | Không gửi secret tới third-party resource |
| Account enumeration | Yêu cầu magic link với email tồn tại/không tồn tại | Response công khai nhất quán |
| Audit redaction | Kiểm tra event/log | Không có code, token, state hoặc verifier raw |

Kiểm thử phải chạy trên thiết bị Android/iOS thật, nhiều phiên bản OS, browser, email client và môi trường app chưa cài. Unit test parser không chứng minh domain association, OS routing hoặc callback lifecycle an toàn.

## 21. Checklist triển khai Deep link

- **Purpose:** Link chỉ điều hướng hay có thể thay đổi trạng thái/xác thực?
- **Scheme/domain:** Ưu tiên Android App Links/iOS Universal Links cho domain do tổ chức kiểm soát?
- **Association:** assetlinks/AASA, package/bundle ID, signing fingerprint và path chính xác?
- **Domain security:** DNS, TLS và hosting association file được bảo vệ?
- **URI validation:** Scheme, host, path, encoding, duplicate parameter và length được kiểm tra?
- **Routing:** Deep link không tự cấp quyền; backend xác minh resource authorization?
- **OAuth:** External user-agent, authorization code, PKCE S256, state, nonce và exact redirect URI?
- **Callback:** Chỉ chấp nhận transaction pending, đúng issuer/audience và chưa consume?
- **Custom scheme:** Có collision risk và fallback control phù hợp?
- **Magic link:** Token entropy cao, purpose-bound, short-lived, single-use và lưu verifier?
- **Scanner:** GET không thực hiện side effect nhạy cảm; có user confirmation phù hợp?
- **Token leakage:** Không đặt bearer/refresh token hoặc verifier trong URL/log/analytics?
- **Open redirect:** Return URL allowlist/canonicalization?
- **Account context:** Subject/tenant được binding; không tin account ID từ URI?
- **App lifecycle:** Callback lặp, process restart và concurrent delivery được xử lý?
- **Storage:** Token/secret lưu trong platform-protected storage và có revocation?
- **Fallback:** Browser/install/deferred link không tự nâng quyền?
- **Monitoring:** Có metric cho association failure, callback mismatch, replay và old link usage?
- **Privacy:** URL query/fragment được redaction; không có third-party script đọc secret?
- **Testing:** Đã thử hijack, spoof intent, replay, scanner, open redirect, parser ambiguity và OS routing?

### Câu hỏi tự kiểm tra

1. Deep link điều hướng khác authentication callback thế nào?
2. Vì sao custom URL scheme có nguy cơ bị app khác chiếm?
3. Android App Links và iOS Universal Links xác minh quan hệ app/domain bằng cách nào?
4. Verified app link có chứng minh người dùng được phép xem resource không?
5. Vì sao native app không thể giữ client secret như confidential server?
6. PKCE và state giải quyết hai rủi ro khác nhau nào?
7. OIDC nonce có vai trò gì trong callback?
8. Vì sao không nên đặt access token trong URL?
9. Email scanner có thể làm hỏng magic link nếu GET thực hiện side effect như thế nào?
10. Vì sao one-time token phải được consume atomically?
11. Deep-link router cần xử lý duplicate parameter và host confusion ra sao?
12. Khi app chưa cài, fallback/deferred link cần xác minh lại điều gì?

## Kết luận

**Deep link là input đến từ bên ngoài ứng dụng và phải được xem là không tin cậy cho tới khi được xác minh theo đúng transaction.** Với link điều hướng, app cần parse URI an toàn và backend vẫn phải kiểm tra authorization. Với authentication callback, ưu tiên Android App Links/iOS Universal Links đã xác minh domain; dùng external user-agent, exact redirect URI, authorization code + PKCE, state/nonce và one-time transaction. Magic link/recovery link cần token entropy cao, gắn purpose/account, expiry ngắn, single-use và không thực hiện side effect chỉ vì một GET bị email scanner mở. Không đưa bearer token vào URL, không cho redirect tùy ý và không tin account/tenant do caller truyền. Rotation/revocation, app lifecycle, fallback, audit và kiểm thử trên thiết bị thật hoàn thiện ranh giới bảo vệ giữa browser, hệ điều hành, mobile app và backend.
