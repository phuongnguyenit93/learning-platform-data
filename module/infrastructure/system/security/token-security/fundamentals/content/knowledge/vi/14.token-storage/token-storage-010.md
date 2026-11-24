# Xóa token khi logout hoặc revoke

Người dùng bấm **Đăng xuất** trong ứng dụng bán hàng. Giao diện xóa access token khỏi bộ nhớ và chuyển về trang đăng nhập. Liệu access token đã bị sao chép trước đó có lập tức vô dụng? **Không nhất thiết.** Xóa token ở thiết bị chỉ ngăn **bản sao tại thiết bị đó** tiếp tục được sử dụng. Nếu token vẫn có hiệu lực tại authorization server (AS) hoặc resource server (RS), một bản sao khác có thể tiếp tục được trình đến API.

Ngược lại, khi AS **revoke** một refresh token, ứng dụng cũng không nên giữ refresh token cũ trong Keychain, kho phiên hoặc bộ nhớ browser. Một quy trình an toàn phải kết hợp **xóa token ở nơi lưu**, **vô hiệu hóa credential/grant/phiên ở phía server**, **xử lý access token chưa hết hạn** và **bảo đảm không tác vụ nền nào tự làm mới credential sau logout**.

Bài thuộc chương **Token storage** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Mục tiêu là thiết kế và kiểm thử việc **xóa token khi logout hoặc revoke** trong hệ thống OAuth 2.0/OpenID Connect (OIDC), áp dụng cho browser BFF, SPA, mobile, backend Java/Spring; phân biệt JWT và opaque token, access/refresh/ID token, scope, audience, cơ chế thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## 1. “Xóa token” không phải một thao tác duy nhất

Cùng một từ *logout* có thể chỉ nhiều thay đổi trạng thái:

| Hành động | Diễn ra ở đâu? | Điều thực sự đạt được | Điều **không** tự bảo đảm |
|---|---|---|---|
| **Xóa access token local** | Bộ nhớ browser, ứng dụng mobile, backend cache | Ứng dụng không còn dùng bản sao đó để gọi API. | Bản sao đã bị lấy cắp không tự mất hiệu lực. |
| **Xóa refresh token local** | Client hoặc token store của BFF | Client không thể dùng bản sao đó để yêu cầu access token mới. | Refresh token đã bị sao chép vẫn có thể dùng ở AS. |
| **Vô hiệu session ứng dụng** | Server phiên BFF và cookie browser | Cookie/session cũ không được backend chấp nhận. | OAuth grant hoặc phiên SSO tại IdP có thể còn hiệu lực. |
| **Revoke token tại AS** | OAuth revocation endpoint, grant/token store | AS đánh dấu token/grant không còn được chấp nhận theo chính sách. | JWT access token đã phát hành có thể vẫn hợp lệ tại RS tự xác minh. |
| **Làm RS ngừng chấp nhận access token** | Introspection, denylist, revocation propagation, kiểm tra phiên | Chặn access token còn sống mà RS nhận được. | Không tự xóa bản sao token khỏi log, backup hoặc máy khác. |
| **Đăng xuất phiên OIDC tại OP** | OpenID Provider (IdP/OP) và các RP tham gia | Có thể kết thúc phiên đăng nhập SSO theo giao thức được hỗ trợ. | Không mặc nhiên thu hồi mọi OAuth token của mọi API. |

Vì vậy, tiêu chí hoàn tất phải gắn với **phạm vi yêu cầu**: đăng xuất trên thiết bị này, vô hiệu phiên của ứng dụng, thu hồi một refresh-token family, hay đăng xuất khỏi tất cả thiết bị.

### Phân biệt access token, refresh token và ID token

- **Access token** dành cho resource server đúng `audience`, được dùng trong phạm vi `scope` và chính sách dữ liệu; có thể là JWT hoặc opaque.
- **Refresh token** dành cho **token endpoint của AS** nhằm xin access token mới; thường cần bảo vệ nghiêm ngặt vì có thể kéo dài khả năng truy cập.
- **ID token** trong OIDC dành cho **client/relying party** để xác nhận authentication; không gửi tới API thay access token.
- **Cookie phiên BFF** là credential của **phiên ứng dụng**, không phải refresh token; backend có thể giữ các OAuth token gắn với phiên này.

Xóa sai một loại credential hoặc sai nơi lưu có thể khiến nút logout chỉ đổi giao diện mà không chấm dứt quyền truy cập thực.

## 2. Mô hình đe dọa: bản sao token có thể nằm ở nhiều nơi

Giả sử access token `AT-1` và refresh token `RT-1` được phát hành sau đăng nhập. Những vị trí có khả năng chứa bản sao:

```mermaid
flowchart TD
    AS[Authorization Server] -->|Phát AT-1 / RT-1| CLIENT[Client hoặc BFF]
    CLIENT --> MEM[Memory / token manager]
    CLIENT --> STORE[Session / secure storage]
    CLIENT -. Rò rỉ ngoài ý muốn .-> LOG[Log / tracing / error report]
    CLIENT -. Bị sao chép .-> ATT[Thiết bị hoặc bên tấn công]
    CLIENT -->|AT-1| API[Resource Server]
    ATT -->|Bản sao AT-1| API
    ATT -->|Bản sao RT-1| AS
```

Một quy trình logout chỉ gọi `memoryToken = null` **không thể thu hồi** bản sao đã đi vào crash report hoặc tay kẻ tấn công. Khi đánh giá thiết kế, cần hỏi:

1. Access token/refresh token được phát hành cho **client nào, issuer nào và grant nào**?
2. Token đang được giữ ở browser, BFF, mobile, nền server, nhiều tab, nhiều node hay worker?
3. Có **bản sao ngoài ý muốn** ở log, analytics, backup, clipboard, URL, debugger không?
4. Token còn hạn bao lâu? Token dạng **Bearer** thuần túy hay được ràng buộc người gửi bằng DPoP/mTLS?
5. Các API nhận token bằng JWT self-validation hay **opaque introspection**? Có cache kết quả không?
6. Logout được kỳ vọng ảnh hưởng **thiết bị hiện tại** hay **mọi phiên/grant liên quan**?

**Nguyên tắc nền tảng:** xóa bản sao local giảm khả năng client dùng lại; **revocation** hạn chế hiệu lực credential còn tồn tại ở nơi khác; **authorization theo audience/scope/tài nguyên** tiếp tục giới hạn thiệt hại nếu token chưa bị ngăn hoàn toàn.

## 3. Định nghĩa hợp đồng logout trước khi viết code

Đừng để sản phẩm chỉ có nút “Logout” nhưng không xác định chính xác điều gì xảy ra. Nên thiết lập một trong các mức sau:

| Kiểu logout | Ví dụ yêu cầu | Hành động tối thiểu |
|---|---|---|
| **Local sign-out** | “Đóng phiên ứng dụng trên thiết bị này.” | Xóa local credential, vô hiệu session hiện tại tại backend nếu có. |
| **Logout + revoke grant hiện tại** | “Thiết bị này không được tiếp tục làm mới token.” | Xóa local, revoke refresh token/grant tương ứng tại AS, xử lý access token chưa hết hạn. |
| **Logout toàn bộ thiết bị** | “Thoát khỏi tất cả phiên của tài khoản.” | Vô hiệu các phiên/refresh grants thuộc phạm vi được cấp phép, phối hợp với nhiều ứng dụng nếu hợp đồng yêu cầu. |
| **OIDC sign-out** | “Kết thúc phiên SSO tại nhà cung cấp danh tính.” | Dùng cơ chế RP-initiated/back-channel/front-channel logout được OP/RP hỗ trợ; vẫn xử lý token/phiên ứng dụng riêng. |
| **Security-incident revocation** | “Token bị lộ hoặc thiết bị bị đánh cắp.” | Thu hồi nhanh credential/grant/family phù hợp, phối hợp RS, điều tra token đã dùng và lưu audit. |

Có thể có các thao tác trong cùng một luồng logout, nhưng chúng **không đồng nghĩa** và không nhất thiết thành công đồng thời.

### Trình tự ưu tiên an toàn

1. **Chặn phát sinh tác vụ mới** dùng credential đang bị đăng xuất, gắn trạng thái ứng dụng `LOGGING_OUT`.
2. **Khóa/đồng bộ token manager**, không cho tiến trình refresh tạo và lưu token mới sau khi logout bắt đầu.
3. **Yêu cầu server vô hiệu phiên/grant** theo chính sách; backend nên vô hiệu session ngay, còn revoke ở AS có thể gặp lỗi mạng.
4. **Xóa mọi credential local** ở kho sử dụng thực tế, không phụ thuộc vào việc revocation HTTP thành công.
5. **Hủy/đánh dấu không dùng kết quả các request đang chạy**, tránh response refresh đến muộn ghi đè token vừa xóa.
6. **Cập nhật UI** và thông báo phạm vi logout thật: local đã xóa, hoặc remote revoke đã được xác nhận, hoặc còn đang có lỗi cần xử lý.

Không để lỗi kết nối tới AS khiến browser vẫn giữ credential và tiếp tục gọi API. Mặt khác, **không báo “đã thu hồi trên mọi thiết bị”** nếu mới xóa local hoặc AS chưa xác nhận.

## 4. Một luồng logout với refresh token và access token

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Browser / Mobile
    participant B as BFF hoặc Token Manager
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Nhấn Logout
    C->>B: Yêu cầu logout / khóa refresh mới
    B->>B: Xác định phiên, grant và credential liên quan
    B->>AS: Revoke refresh token nếu có và được hỗ trợ
    AS-->>B: Kết quả revocation
    B->>B: Vô hiệu phiên và xóa token trong kho thuộc quyền quản lý
    B-->>C: Trạng thái logout
    C->>C: Xóa credential local / cookie ứng dụng / UI state
    Note over RS: JWT AT có thể vẫn còn hạn nếu không có denylist
    C->>RS: Bản sao AT cũ (nếu ai đó còn giữ)
    RS->>RS: Kiểm tra chữ ký/introspection, aud, thời hạn và revoke
    RS-->>C: Từ chối nếu chính sách RS đã vô hiệu token
```

Sơ đồ mô tả **ý định hợp đồng**; revocation và vô hiệu session có thể được sắp xếp hoặc tách khác nhau để bảo đảm không phát sinh request mới. Với SPA không có BFF, client có thể gọi revocation endpoint trực tiếp **nếu AS hỗ trợ public client và CORS/chính sách cần thiết**. Với BFF, thông thường backend quản lý OAuth token và thực hiện revocation; browser không cần biết refresh token.

Cần phân biệt hai sự kiện:

- **Logout request thành công tại ứng dụng:** có thể chứng minh phiên BFF bị vô hiệu, token local đã được xóa.
- **Revoke đã có hiệu lực tại mọi RS:** cần cơ chế và bằng chứng riêng, nhất là khi JWT có thể được RS xác minh độc lập và khi introspection có cache.

## 5. Browser BFF: xóa cookie không đủ nếu session server còn sống

Trong mô hình **Backend-for-Frontend (BFF)**, browser giữ cookie phiên của ứng dụng, còn backend nắm access token/refresh token và thực hiện OAuth client logic.

```mermaid
flowchart LR
    WEB[Browser + session cookie] --> BFF[BFF / application backend]
    BFF --> SESSION[(Session store)]
    BFF --> TOKEN[(Authorized-client / token store)]
    BFF --> AS[Authorization Server]
    BFF --> API[Resource Server]
```

Một logout phù hợp thường gồm:

1. Browser gửi request logout với bảo vệ **CSRF** phù hợp, thường bằng `POST`.
2. BFF xác định phiên đang hoạt động và các authorized clients/tokens gắn với phiên.
3. Backend yêu cầu AS **revoke** refresh token hoặc grant nếu chính sách và endpoint hỗ trợ; với nhiều AS/client cần xử lý từng bên.
4. BFF vô hiệu **server-side session**, xóa hoặc đánh dấu không còn sử dụng authorized-client state, ngăn cache/token refresh tái tạo phiên.
5. Browser được chỉ thị xóa **cookie phiên** và không còn giữ trạng thái đăng nhập trên UI.

### Ví dụ cookie sau logout

```http
HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Đây là ví dụ cho cookie `__Host-session` **đã được tạo với `Path=/` và không có `Domain`**, đúng quy tắc prefix. Xóa cookie phải khớp tên, path/domain liên quan với cookie đã tạo; thuộc tính khác nên nhất quán theo chính sách. Nếu ứng dụng dùng `JSESSIONID` hoặc tên khác thì phải xóa đúng tên đó.

**Không chỉ gọi `document.cookie = ...` rồi coi như logout.** JavaScript không thể đọc/sửa cookie `HttpOnly` theo cách trực tiếp; server phải phát `Set-Cookie` thích hợp và vô hiệu session phía server. Nếu chỉ xóa cookie mà phiên server chưa bị vô hiệu, một bản sao cookie bị đánh cắp có thể vẫn truy cập phiên.

### XSS, CSRF và cookie

- `HttpOnly` giảm khả năng JavaScript trực tiếp lấy cookie, nhưng **XSS vẫn có thể gọi API với phiên của browser**.
- Cookie được browser tự động đính kèm theo quy tắc; cần **CSRF defense** cho thao tác nhạy cảm, gồm cả logout nếu endpoint có tác động trạng thái.
- Dùng `Secure`, `SameSite` và ràng buộc `Domain`/`Path` chặt; `SameSite` không thay mọi cơ chế CSRF.
- Không gửi refresh token trong JSON response logout cho browser “để tự xóa”.

Lợi ích của BFF là browser JavaScript **không tiếp xúc trực tiếp** OAuth refresh token trong thiết kế chuẩn, giảm phạm vi token có thể bị lấy qua XSS. Tuy nhiên, backend phải bảo vệ token store và phiên đúng cách.

## 6. SPA: xóa token trong memory và persistent storage

Một **single-page application (SPA)** không có backend token-mediating có thể nhận access token và, nếu AS cho phép, refresh token trong môi trường browser. Vì JavaScript không phải kho bí mật đáng tin, nên **tránh giữ refresh token lâu dài trong `localStorage`** nếu có lựa chọn an toàn hơn.

Khi logout, ứng dụng cần xét mọi nơi từng cất token:

- Token trong **biến memory**, state manager, query cache, global singleton.
- Dữ liệu cũ trong `sessionStorage`, `localStorage`, IndexedDB do phiên bản trước đã sử dụng.
- **Service worker** hoặc web worker đang giữ trạng thái token nếu kiến trúc dùng chúng.
- Các tab cùng origin có token manager riêng, tác vụ refresh đang chờ hoặc polling chạy nền.
- HTTP client/interceptor đã cài sẵn header `Authorization` từ token cache.

Ví dụ **chỉ minh họa local cleanup**:

```javascript
let accessToken = null;
let refreshToken = null; // Không khuyến nghị lưu persistent mặc định.
let sessionGeneration = 0;

function clearLocalSession() {
  sessionGeneration += 1; // Kết quả async cũ không được ghi lại token.
  accessToken = null;
  refreshToken = null;

  // Dọn các khóa legacy nếu ứng dụng từng dùng storage này.
  sessionStorage.removeItem("legacy_access_token");
  localStorage.removeItem("legacy_refresh_token");

  // Thông báo sự kiện, KHÔNG gửi token qua channel.
  const channel = new BroadcastChannel("app-auth-state");
  channel.postMessage({ type: "LOGOUT" });
  channel.close();
}
```

Đoạn mã **không đủ để logout an toàn**: chưa gọi AS revoke, chưa xóa IndexedDB/service-worker state, chưa xử lý request đang chạy, chưa có fallback browser khi `BroadcastChannel` không khả dụng và chưa kiểm tra `sessionGeneration` tại điểm nhận refresh response. Các tên storage `legacy_*` chỉ là ví dụ dọn dữ liệu đã tồn tại, **không phải lời khuyên bắt đầu lưu refresh token vào `localStorage`**.

### Tránh token “sống lại” do request bất đồng bộ

Ví dụ:

```text
09:00:00  Refresh request A bắt đầu bằng RT-1.
09:00:01  Người dùng logout, ứng dụng xóa token.
09:00:02  Refresh response A trả AT-2, RT-2.
09:00:03  Token manager cũ lưu AT-2, RT-2 lại vào memory/storage.
```

Nếu không có **generation/version check, cancelation hoặc điều phối đồng thời**, token có thể bị ghi lại sau logout. Cần đánh dấu một phiên đã kết thúc và từ chối **mọi phản hồi async thuộc phiên cũ**. Với nhiều tab, gửi sự kiện logout không chứa token và đồng bộ trạng thái; không giả định mọi tab đều nhận được thông báo khi tab bị treo, offline hoặc đã đóng.

## 7. Mobile native: xóa token khỏi nơi lưu của hệ điều hành

Ứng dụng iOS/Android thường là **public client**, nên cần Authorization Code + PKCE qua external user-agent để đăng nhập, không nhúng client secret vào APK/IPA. Refresh token có thể được lưu trong vùng bí mật của hệ điều hành, không phải file/preferences plain text.

### iOS Keychain

Một ứng dụng lưu refresh token trong Keychain cần dùng **chính các thuộc tính tìm kiếm** đã dùng khi lưu để xóa mục tương ứng.

```swift
import Foundation
import Security

func deleteRefreshToken(account: String) -> OSStatus {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.example.orders.refresh",
        kSecAttrAccount as String: account
    ]
    return SecItemDelete(query as CFDictionary)
}
```

Ví dụ này minh họa **xóa mục Keychain theo service/account**, không phải quy trình logout hoàn chỉnh. Thực tế cần phân biệt kết quả `errSecSuccess`, `errSecItemNotFound` và lỗi hệ thống; xử lý nhiều tài khoản, access group, thiết bị và chính sách backup. Tránh xóa bằng truy vấn quá rộng khiến credential của tài khoản khác cũng bị mất.

**Không bảo đảm “xóa vật lý mọi byte”**: hệ điều hành, flash storage, backup hoặc snapshot có thể có những đặc điểm riêng. Bảo đảm quan trọng về bảo mật OAuth là **token đã bị thu hồi tại AS khi cần**, không chỉ dựa vào xóa local. Các lựa chọn Keychain như `ThisDeviceOnly` giúp giảm rủi ro di chuyển credential qua backup, nhưng có đánh đổi khi khôi phục thiết bị.

### Android Keystore và storage mã hóa

Android Keystore quản lý khóa mật mã; ứng dụng có thể lưu refresh token dưới dạng ciphertext trong app-private storage và dùng khóa Keystore để giải mã khi cần. Khi logout:

1. Dừng token refresh và các tác vụ nền liên quan.
2. Xóa mục ciphertext/metadata tương ứng với tài khoản và môi trường.
3. Khi phù hợp, **xóa hoặc vô hiệu khóa mã hóa** chỉ dành riêng cho token/phiên đó, để ciphertext cũ không giải mã được.
4. Xử lý backup/restore và dữ liệu đồng bộ; không tự giả định dữ liệu có thể truy hồi từ thiết bị khác đã bị xóa.
5. Gửi revoke tới AS theo chính sách; nếu thiết bị offline, phải xử lý độ trễ revocation và thông báo phạm vi thực tế.

**Lưu ý quan trọng:** nếu một khóa Keystore được dùng chung cho nhiều tài khoản hoặc nhiều mục dữ liệu, xóa khóa đó có thể làm hỏng dữ liệu không liên quan. Cần thiết kế vòng đời khóa và phạm vi xóa trước khi triển khai. Không tự cho rằng Keystore luôn được phần cứng bảo vệ hoặc có thể chống lại mọi thiết bị đã root/jailbreak.

### Mobile background tasks và nhiều tài khoản

- Xóa token trong memory **và** secure storage; không chỉ xóa biến UI.
- Ngắt background synchronization, job queue, push-triggered refresh và upload dùng credential của tài khoản vừa logout.
- Dùng khóa/phiên bản token manager để tránh request hoàn thành muộn ghi token mới sau logout.
- Xóa đúng credential gắn với **issuer + client + account + environment**, không làm mất session của user khác nếu ứng dụng hỗ trợ nhiều tài khoản.
- Khi token đã revoke từ server (ví dụ remote device wipe), app cần nhận tín hiệu hoặc phát hiện tại lần refresh/check tiếp theo và dọn local credential.

## 8. RFC 7009: revoke token là bước server-side

**OAuth 2.0 Token Revocation** (RFC 7009) định nghĩa endpoint để client yêu cầu AS vô hiệu một token đã được cấp. Nó đặc biệt quan trọng đối với **refresh token**, vì refresh token có thể được dùng để xin nhiều access token mới.

Ví dụ confidential client/BFF gọi revoke endpoint:

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
```

Giá trị trong ví dụ **chỉ là placeholder**, không phải token hoặc secret thật. `token_type_hint` là gợi ý, **không phải điều kiện tin cậy** để AS bỏ xác minh loại token. Client phải xác thực/được AS định danh phù hợp theo loại client và chính sách endpoint; dùng TLS, không gửi credential qua URL query.

Các điểm cần hiểu:

- Theo RFC 7009, AS **phải hỗ trợ revocation của refresh token** và **nên hỗ trợ revocation của access token** trong phạm vi tiêu chuẩn; hành vi triển khai, token type và ràng buộc giữa các token tùy theo AS.
- AS thường trả **HTTP 200** cho yêu cầu revoke thành công, kể cả khi token không tồn tại/đã không còn hợp lệ, nhằm không để endpoint tiết lộ tình trạng token.
- Một response 200 **không có nghĩa** tất cả JWT access token đã được cấp bởi cùng grant đều lập tức bị mọi RS từ chối.
- AS có thể có quy tắc thu hồi token hoặc grant liên quan; **client phải hiểu hợp đồng cụ thể**, không giả định revoke một access token luôn tự revoke refresh token, hoặc ngược lại.
- Nếu AS không hỗ trợ thu hồi một loại token, có thể trả lỗi `unsupported_token_type` theo quy tắc chuẩn.
- Với lỗi mạng/timeout, client **không thể khẳng định AS đã nhận hoặc chưa nhận** request. Phải làm local cleanup, ghi trạng thái chưa xác nhận và xử lý retry có giới hạn theo chính sách.

### HTTP 200 không phải bằng chứng phủ toàn hệ thống

AS phản hồi thành công là căn cứ cho **yêu cầu revocation tại AS** theo hợp đồng. Hiệu lực tại resource server còn phụ thuộc cách RS xác minh token (JWT tại chỗ hay opaque introspection), cache, denylist và tuổi thọ access token. Nếu tiêu chí của hệ thống là “ngay sau logout không một API nào được dùng token cũ”, kiến trúc phải triển khai và kiểm thử **cơ chế enforcement phù hợp**, không chỉ gọi revocation endpoint.

## 9. JWT access token: vì sao vẫn dùng được sau logout?

Một **JWT access token tự chứa** được resource server xác minh tại chỗ bằng chữ ký, issuer, `aud`, `exp`, `nbf`, loại token và scope. Khi AS thu hồi refresh token, RS chỉ biết điều đó nếu có thêm cơ chế liên kết trạng thái.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as JWT Resource Server
    C->>AS: Revoke refresh token
    AS-->>C: 200 (AS xử lý revoke)
    C->>RS: Một bản sao access JWT cũ chưa hết hạn
    RS->>RS: Xác minh signature, iss, aud, exp
    Note over RS: Không tra denylist / grant state
    RS-->>C: Vẫn có thể cho phép trong scope và policy
```

Đây là hệ quả của **validation không trạng thái thu hồi**. Nếu cần ngừng access token trước `exp`, hệ thống có thể chọn:

| Cơ chế | Cách giảm rủi ro | Đánh đổi |
|---|---|---|
| **Access token sống ngắn** | Giảm cửa sổ token cũ còn được chấp nhận. | Không ngừng tức thì; tăng nhu cầu refresh. |
| **Denylist token** | RS tra danh sách token bị thu hồi trước khi cho phép. | Cần trạng thái phân tán, kiểm soát cache/TTL và độ sẵn sàng. |
| **Token version / session version** | So sánh version trong token với version hiện hành từ nguồn quyền. | Thêm lookup/cache và chính sách version theo user/grant. |
| **Introspection/JWT state check** | Xác minh token còn active với AS hoặc nguồn trạng thái. | Tăng độ trễ, phụ thuộc AS; cache có thể chậm cập nhật. |
| **Event propagation** | Phát sự kiện revoke tới RS/gateway để làm mới denylist/cache. | Cần đảm bảo phân phối, xử lý thất bại và nhất quán cuối. |

Nếu dùng `jti` làm khóa denylist, cần bảo đảm `jti` đến từ **JWT đã xác minh**, gắn với issuer và token profile, có tính duy nhất theo hợp đồng. Có thể lưu một tham chiếu HMAC an toàn tới token hoặc `iss + jti` theo thiết kế; giới hạn retention tối thiểu đến khi token hết hạn cộng clock-skew cần thiết. Không log nguyên bearer token để dùng làm khóa đối soát.

**Không dùng khóa ký bị lộ và revoke token cá biệt như cùng một thao tác.** Xoay/loại bỏ khóa ký có thể làm nhiều token hợp lệ khác bị từ chối; chỉ áp dụng khi có yêu cầu bảo mật hoặc sự cố khóa tương ứng.

## 10. Opaque access token: trạng thái ở AS và cache ở RS

**Opaque token** thường là chuỗi tham chiếu khó đoán; RS có thể gọi **RFC 7662 Token Introspection** tới AS tin cậy để biết token có còn `active` hay không.

Trước revocation:

```json
{
  "active": true,
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900
}
```

Sau revocation theo chính sách AS:

```json
{
  "active": false
}
```

**HTTP 200 từ introspection endpoint không tự mang nghĩa `active=true`.** Resource server phải đọc đúng phản hồi, xác minh nguồn introspection, audience, scope, loại token, quyền dữ liệu và trạng thái.

### Điểm khó: cache `active=true`

Nếu RS cache kết quả introspection trong 60 giây, AS đã revoke token tại thời điểm T nhưng RS có thể tiếp tục sử dụng response cache đến T+60 (nếu chưa invalidation). Muốn giảm độ trễ:

1. Đặt TTL cache phù hợp với rủi ro và **không vượt hạn token còn lại**.
2. Chủ động làm mới/invalidate cache khi nhận sự kiện revoke đáng tin từ AS.
3. Với hành động đặc biệt nhạy cảm, cân nhắc introspection mới hoặc kiểm tra trạng thái phiên/quyền tại thời điểm dùng.
4. Khi AS lỗi, không **tự coi `active=true`**; chỉ dùng cache đã xác minh còn hợp lệ nếu chính sách cho phép, hoặc fail closed.
5. Giám sát queue sự kiện, cache staleness, timeout và độ trễ revoke-to-enforcement.

Một token `active=false` hoặc đã hết hạn không được làm sống lại chỉ vì bản ghi cache cũ. Cũng không được bỏ kiểm tra `aud`/`scope` vì AS đã trả `active=true`.

## 11. Thu hồi refresh token và token family

Refresh token có thể có **rotation**: mỗi lần refresh thành công AS cấp refresh token mới và đánh dấu token trước đó đã dùng. Một chuỗi như `RT-1 → RT-2 → RT-3` có thể thuộc cùng một **token family** liên kết với grant/phiên.

```mermaid
flowchart LR
    RT1[RT-1 spent] --> RT2[RT-2 spent]
    RT2 --> RT3[RT-3 active]
    RT3 -->|Logout / security revoke| R[Family revoked]
```

Khi logout, phải xác định rõ:

- Chỉ revoke refresh token **hiện tại** hay cả **grant/family** được AS xác định?
- Có access token phát hành trước đó đang còn hạn không?
- Có nhiều phiên/thiết bị sử dụng cùng user nhưng **khác family** không?
- Trong lúc logout có refresh request đang chạy tạo RT tiếp theo không?
- Nếu phát hiện reuse token cũ, AS có tự thu hồi family và yêu cầu xác thực lại không?

Một public client được cấp refresh token cần các biện pháp bảo vệ **rotation hoặc sender constraint** theo OAuth 2.0 Security Best Current Practice (RFC 9700), phù hợp hệ thống đang triển khai.

**Race đáng chú ý:** request refresh dùng RT-2 bắt đầu ngay trước logout; response trả RT-3 sau khi app đã xóa RT-2. Nếu client lưu RT-3 từ response cũ, credential sẽ **sống lại**. Phải dùng token-manager state/generation và, tại AS, bảo đảm revoke có phạm vi family/grant thích hợp, phối hợp transaction/idempotency để không tạo “cửa sổ” ngoài ý định.

Không được làm yếu reuse detection bằng cách cho mọi token đã spent tiếp tục cấp token mới trong thời gian không giới hạn. Các cơ chế retry/overlap, nếu có, phải được thiết kế có giới hạn và phân biệt lỗi mạng với hành vi phát lại khi khả thi.

## 12. Logout ứng dụng khác OIDC Single Sign-Out

Trong OIDC, **RP-initiated logout** có thể điều hướng client đến endpoint logout của OpenID Provider (OP) để kết thúc phiên đăng nhập OP, khi OP hỗ trợ. Một số hệ thống còn dùng **Front-Channel Logout** hoặc **Back-Channel Logout** để thông báo các relying parties (RP) về việc phiên kết thúc.

Nhưng cần tách ba phạm vi:

| Phạm vi | Ví dụ | Cần xử lý riêng |
|---|---|---|
| **Application session** | Cookie `__Host-session` tại ứng dụng bán hàng. | Hủy session backend và cookie. |
| **OAuth grants/tokens** | Refresh token của ứng dụng, access token cho Orders API. | Revoke AS, xử lý access JWT/opaque và cache RS. |
| **OP/SSO session** | Phiên đăng nhập của người dùng tại IdP. | OIDC logout protocol khi hệ thống hỗ trợ và được cấu hình. |

Nếu chỉ revoke refresh token, phiên browser tại OP **có thể vẫn đang đăng nhập**. Nếu chỉ logout OP, API có thể tiếp tục nhận access JWT chưa hết hạn nếu không có cơ chế kiểm tra trạng thái bổ sung.

### “Đăng xuất khỏi mọi thiết bị” là một hợp đồng khác

Để thực hiện theo nghĩa bảo mật, cần có danh sách hoặc cơ chế xác định **các phiên ứng dụng**, **token families/grants** và **resource servers** liên quan, có thẩm quyền revoke theo phạm vi account/device. Không chỉ xóa credential trên thiết bị đã gửi yêu cầu.

Khi làm “logout all” cần kiểm thử **thiết bị khác vẫn online**, thiết bị offline, nhiều BFF instances, nhiều AS và cache của API. Không tuyên bố đã logout mọi nơi nếu các RS vẫn có thể chấp nhận access JWT đến khi `exp` theo thiết kế.

## 13. Backend/token store: xóa dữ liệu mà không làm mất bằng chứng kiểm toán

Trong ứng dụng BFF hoặc một OAuth client backend, token có thể nằm ở:

- `OAuth2AuthorizedClient` repository/store của Spring Security hoặc bảng riêng.
- Session store, distributed cache, secret vault, encrypted database.
- Bộ nhớ node backend, token manager, hàng đợi job hoặc background worker.
- Backup, snapshot, log/tracing, lịch sử audit.

**Xóa logic khỏi token store đang hoạt động** là quan trọng, nhưng đừng đồng nhất với “mọi bản sao vật lý trên mọi phương tiện đã bị xóa ngay”. Backup/WORM và quy định retention có vòng đời riêng; nơi cần lưu bằng chứng phải dùng **định danh tham chiếu an toàn**, không giữ raw refresh token chỉ để phục vụ điều tra.

Ví dụ trạng thái nên quản lý:

| Trường | Mục đích |
|---|---|
| `issuer` + `client_id` + `principal_ref` | Phân biệt AS/client/tài khoản. |
| `session_id` hoặc `grant_ref` | Xác định phạm vi logout/revoke. |
| `token_digest` / token reference | Tra cứu, đối soát mà không log raw token. |
| `expires_at`, `revoked_at` | Trạng thái vòng đời/TTL. |
| `token_family_ref` | Liên kết rotation hoặc revoke grant. |
| `policy_version`, `audit_id` | Điều tra quyết định và nguyên nhân thu hồi. |

Nếu AS/ứng dụng **chỉ lưu digest của token** và không còn giá trị token gốc, client backend có thể **không thể gọi RFC 7009 bằng raw token**. Khi đó cần cơ chế thu hồi theo grant/session được AS hỗ trợ và cho phép, hoặc giữ token ở kho mã hóa có kiểm soát để có thể revoke trước khi xóa. Đừng ghi token nguyên bản vào log để “sau này dễ revoke”.

### Hủy dữ liệu mã hóa và bí mật

Có thể áp dụng **crypto-erasure** khi mỗi vùng dữ liệu có khóa mã hóa phù hợp và xóa khóa khiến ciphertext cũ không thể giải mã. Nhưng phải xét khóa có dùng chung, backup, snapshot, HSM/KMS retention và chính sách pháp lý. Không khẳng định một lệnh `DELETE` trong DB hoặc `removeItem` trong browser bảo đảm xóa vật lý mọi byte.

## 14. Java/Spring Security: tách local cleanup và remote revocation

Trong ứng dụng Spring Security chạy phía server, có thể quản lý thông tin OAuth client bằng `OAuth2AuthorizedClientRepository` (gắn với HTTP request/session) hoặc service/store tương ứng. Xóa authorized-client state **không tự gọi revocation endpoint**.

Ví dụ một `LogoutHandler` thực hiện local cleanup theo đúng client registration của ứng dụng:

```java
// Spring Security servlet: ví dụ cấu phần, không phải class độc lập.
@Bean
LogoutHandler clearAuthorizedClient(
        OAuth2AuthorizedClientRepository authorizedClients) {

    return (request, response, authentication) -> {
        if (authentication != null) {
            authorizedClients.removeAuthorizedClient(
                "orders-client",
                authentication,
                request,
                response
            );
        }
    };
}
```

Khi tích hợp, ứng dụng cần đăng ký handler vào logout chain, bảo đảm **session invalidation**, cookie cleanup, CSRF protection và xử lý nhiều client registrations. Quan trọng hơn, ví dụ chỉ **xóa authorized-client local**; **chưa revoke refresh token tại AS**. Nếu muốn gọi revoke, phải lấy credential từ kho được phép truy cập **trước khi xóa**, gọi endpoint theo chính sách và xử lý trạng thái chưa xác nhận an toàn. Không truyền secret vào browser.

### Mẫu service điều phối logout

```java
// Pseudocode: các interface sau do ứng dụng định nghĩa.
// Không phải API Spring Security có thể chạy nguyên bản.
public LogoutResult logoutCurrentSession(SessionId sessionId) {
    sessionCoordinator.blockNewRefresh(sessionId);

    RevocationCandidate candidate =
        tokenStore.readRevocationCandidate(sessionId);

    // Vô hiệu session ứng dụng phải có hiệu lực ngay cả khi AS lỗi.
    sessionStore.invalidate(sessionId);

    RevocationResult remote = RevocationResult.NOT_APPLICABLE;
    if (candidate != null) {
        remote = revokeClient.requestRevocation(candidate);
    }

    tokenStore.removeAuthorizedClientData(sessionId);
    audit.recordWithoutCredentials(sessionId, remote);

    return LogoutResult.localClosed(remote);
}
```

Mẫu khái niệm này làm rõ **trách nhiệm**, không phải bảo đảm nguyên tử giữa nhiều hệ thống. Nếu AS timeout, không thể hứa mọi grant đã revoke. Ứng dụng có thể dùng retry/outbox bảo vệ thích hợp cho những trường hợp cần xử lý tiếp, nhưng phải cân nhắc **lưu token bí mật thế nào để retry** và TTL của dữ liệu; nếu không còn raw token thì không được giả vờ vẫn có thể gọi revocation bằng token đó. Hệ thống nhiều node cần khóa/transaction, tránh một node đã logout còn node khác refresh và tái tạo token.

### Cẩn thận với thứ tự logout

Nếu đọc token sau khi đã xóa repository hoặc sau khi `Authentication` bị loại khỏi context, có thể không còn dữ liệu cần cho revocation. Mặt khác, thực hiện HTTP call đến AS rồi **không** vô hiệu session khi AS lỗi sẽ tạo tình trạng nguy hiểm. Thiết kế cần tách rõ:

- Thu thập tham chiếu/credential cần revoke trong phạm vi quyền và thời gian ngắn.
- Chặn dùng credential mới, **vô hiệu phiên local ngay**.
- Yêu cầu AS revoke và ghi nhận kết quả thực.
- Xóa hoặc hủy token ở kho phù hợp, không giữ raw token trong log.

Không coi một handler chạy thành công là bằng chứng rằng **mọi node và mọi API** đã được cập nhật trạng thái.

## 15. Những race condition sau logout

### Refresh response đến muộn

```text
T0  Request refresh RT-1 đã được gửi.
T1  User logout, xóa RT-1 local.
T2  AS trả access token AT-2 và refresh token RT-2.
T3  Callback cũ cất lại AT-2 / RT-2 nếu không có generation guard.
```

**Giải pháp:** quản lý thế hệ phiên, khóa refresh mới khi bắt đầu logout, bỏ kết quả thuộc phiên cũ; AS nên ràng buộc refresh token với grant/family và xử lý revoke nhất quán. Client-side guard chỉ giúp không ghi lại credential **trên client**; nó không chứng minh AS đã vô hiệu token mới.

### Request API đang bay

Một request đã gửi access token trước thời điểm logout có thể đến RS và được xử lý trước hoặc sau thao tác revoke. Nếu cần kiểm soát hành động đặc biệt nhạy cảm, phải xác định **điểm cắt hiệu lực** và thứ tự enforcement ở phía server, không chỉ hủy `fetch` hoặc đóng màn hình.

### Nhiều tab, nhiều device, nhiều node

- **SPA nhiều tab:** mọi tab có state/token cache riêng phải nhận tín hiệu logout hoặc tự kiểm tra phiên đã vô hiệu; không gửi raw token qua `BroadcastChannel`.
- **BFF nhiều node:** server-side session và authorized-client state phải được chia sẻ hoặc có cơ chế vô hiệu nhất quán; token refresh cần single-flight/lock thích hợp.
- **Mobile background jobs:** hủy lịch đồng bộ theo tài khoản; đáp ứng thông tin revoke khi online trở lại.
- **Nhiều thiết bị:** logout thiết bị A không mặc định xóa token thiết bị B, trừ khi AS/ứng dụng áp dụng “logout all”.

Trạng thái “logout đã xong” phải được định nghĩa đủ rõ để tester biết **thành phần nào bắt buộc đã ngừng sử dụng credential**.

## 16. Khi revoke từ phía server: client cần dọn local thế nào?

Không phải mọi sự kiện revoke đều do nút logout trên thiết bị. Ví dụ AS hoặc quản trị viên thu hồi grant khi phát hiện thiết bị mất, người dùng đổi mật khẩu hoặc quyền bị hạ.

Client có thể phát hiện:

- Token refresh endpoint trả `invalid_grant`.
- API trả lỗi token không còn hợp lệ (ví dụ `401 invalid_token`) sau khi credential đã được AS thu hồi hoặc hết hạn.
- BFF nhận một tín hiệu tin cậy từ hệ thống phiên/IdP hoặc kiểm tra trạng thái grant.
- Mobile nhận thông báo bảo mật phù hợp, rồi kiểm tra với backend/AS trước khi xử lý theo chính sách.

Khi biết credential không còn hợp lệ:

1. Ngừng vòng lặp tự refresh; **không retry vô hạn** với cùng một refresh token đã bị revoke.
2. Vô hiệu local session/token manager ngay và xóa credential khỏi kho lưu thực.
3. Hủy/purge các tác vụ nền dùng credential cũ; nếu cần, xóa cache dữ liệu nhạy cảm gắn với tài khoản.
4. Đưa người dùng về authorization flow thích hợp nếu cần, không tự tái sử dụng ID token/refresh token cũ.
5. Phân biệt **lỗi mạng tạm thời** với `invalid_grant`: timeout chưa chứng minh revoke, còn lỗi grant đã được AS trả hợp lệ thường buộc ngừng dùng credential đó.

Không xóa dữ liệu của tài khoản khác chỉ vì một tài khoản bị revoke. Với các ứng dụng có nhiều issuer/tenant, local storage key cần phân biệt issuer + client + account + environment.

## 17. Xử lý sự cố: đã xóa local nhưng token bị đánh cắp từ trước

Nếu kẻ tấn công đã sao chép `RT-1`, thao tác `localStorage.removeItem(...)`, `SecItemDelete(...)` hoặc xóa một hàng token store trên BFF **không lấy lại được bản sao của họ**. Cần:

1. **Ngăn nguồn lộ**: redact logs, tracing, crash reports, query params; hạn chế quyền đọc/lan truyền bản sao credential.
2. **Xác định phạm vi**: issuer, client, grant/token family, thiết bị, audience, scope, thời hạn và resource servers liên quan bằng nguồn dữ liệu đáng tin.
3. **Revoke tại AS**: refresh token/grant/family và access token nếu được hỗ trợ.
4. **Đảm bảo enforcement tại RS**: đánh giá JWT đến `exp`, denylist, introspection cache, session-version checks hoặc công cụ phù hợp.
5. **Kiểm tra lịch sử**: các request được `PERMIT` và business actions thực sự diễn ra, không chỉ đếm `401`/`403`.
6. **Phục hồi**: khởi tạo phiên mới, buộc xác thực lại theo rủi ro, rà soát quyền/credential liên quan, hỗ trợ người dùng và thông báo theo chính sách tổ chức.

**Audience và scope giảm thiệt hại, không thay revoke.** Nếu token chỉ có `aud=orders-api` và `scope=orders.read`, API thanh toán phải từ chối; nhưng một kẻ giữ token có thể vẫn đọc dữ liệu tại Orders API trong phạm vi quyền đã cấp khi token còn hiệu lực.

Sender-constrained token như DPoP/mTLS có thể giảm nguy cơ kẻ chỉ có chuỗi token phát lại từ môi trường khác; nhưng chúng cũng **không thay việc xử lý sự cố** nếu khóa ràng buộc bị chiếm hoặc client runtime bị điều khiển.

## 18. Audit và quyền riêng tư khi logout/revoke

Một sự kiện kiểm toán hữu ích nên ghi:

| Trường | Mục đích |
|---|---|
| `event_id`, `trace_id` | Liên kết thao tác ứng dụng, AS và các dịch vụ. |
| `occurred_at`, `service` | Biết thời điểm và nguồn event, dùng UTC. |
| `principal_ref`, `issuer`, `client_id` | Xác định chủ thể, issuer/client theo nguồn đã xác minh. |
| `session_ref`, `grant_ref`, `token_family_ref` | Xác định phạm vi logout/revoke bằng tham chiếu được bảo vệ. |
| `event_type` | `LOCAL_SESSION_CLEARED`, `REVOCATION_REQUESTED`, `REVOCATION_ACKNOWLEDGED`, `REUSE_DETECTED`, v.v. |
| `result`, `reason_code`, `policy_version` | Phân biệt kết quả thực, lỗi mạng, admin revoke, security incident. |
| `enforcement_state` | Nếu có bằng chứng: RS đã invalidate denylist/cache hay chưa. |

**Không ghi** raw access token, refresh token, ID token, cookie phiên, header `Authorization`, client secret, DPoP private key hoặc payload JWT không cần thiết. Nếu cần tương quan theo token, có thể dùng token reference/HMAC dẫn xuất với khóa được bảo vệ, không giữ credential nguyên bản trong audit.

**Không gộp các trạng thái khác nhau thành “logout success”** nếu nghiệp vụ cần biết mức độ an toàn. Ví dụ event `LOCAL_SESSION_CLEARED` có thể thành công, nhưng `AS_REVOCATION_TIMEOUT` vẫn phải được lưu riêng để điều tra/khắc phục. Kho audit phải có quyền truy cập, retention và tính toàn vẹn phù hợp; không trở thành điểm rò rỉ token mới.

## 19. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Phương án đúng |
|---|---|---|
| Chỉ xóa token khỏi UI memory. | Bản sao trong storage/worker/tab khác vẫn có thể được dùng. | Dọn mọi storage/token manager, chặn refresh và revoke ở AS khi cần. |
| Chỉ xóa browser cookie. | Session backend hoặc grant OAuth có thể vẫn sống. | Vô hiệu server-side session và xử lý grant/token riêng. |
| Chỉ revoke refresh token và hứa access JWT ngừng ngay. | RS tự xác minh JWT có thể vẫn chấp nhận đến `exp`. | Cấu hình denylist/introspection hoặc nói rõ cửa sổ hiệu lực. |
| Xóa raw token trước khi có cách revoke remote. | Mất credential cần gửi tới revocation endpoint. | Thu thập và quản lý an toàn revocation candidate trước, xử lý lifecycle có kiểm soát. |
| AS revoke timeout làm ứng dụng tiếp tục giữ token local. | Vẫn có thể dùng credential tại client. | Local cleanup không phụ thuộc remote success; trạng thái remote chưa xác nhận. |
| Trả HTTP 200 từ revoke rồi ghi “logout tất cả thiết bị”. | Overclaim mức enforcement. | Kiểm tra thật grants/sessions/RS/cache theo phạm vi. |
| Không khóa refresh request trong lúc logout. | Access/refresh token mới có thể bị ghi lại. | Generation/epoch, single-flight, CAS/transaction và bỏ response cũ. |
| SPA xóa `localStorage` nhưng giữ token trong memory/Service Worker. | Credential còn hiện diện và tiếp tục gửi request. | Dọn mọi lớp, quản lý tác vụ nền và nhiều tab. |
| Mobile xóa UI state nhưng không xóa Keychain/Keystore-backed data. | Thiết bị vẫn có refresh token dùng lại được. | Xóa credential theo đúng account/issuer và xử lý background. |
| Xóa quá rộng mọi tài khoản. | Người dùng khác mất session/dữ liệu hoặc security incident. | Scope storage key theo account/client/issuer/environment. |
| Ghi nguyên token vào log để điều tra revoke. | Kho log trở thành nguồn token bị đánh cắp. | Log tham chiếu an toàn và mã nguyên nhân. |
| Tin rằng `active=true` hoặc chữ ký đúng là đủ sau logout. | Bỏ qua trạng thái revoke, aud/scope/tenant. | Kết hợp validation, trạng thái và authorization bắt buộc. |

## 20. Ma trận kiểm thử xóa token và thu hồi

Giả sử ứng dụng có access JWT sống 10 phút, refresh token rotation, BFF hoặc mobile client theo từng luồng, Orders API có audience `orders-api` và phạm vi `orders.read`.

| ID | Tình huống | Kỳ vọng kiểm thử |
|---|---|---|
| L01 | Người dùng logout tại BFF. | Server session bị vô hiệu; cookie bị xóa đúng path; repository authorized-client không còn credential dùng được. |
| L02 | Browser chỉ xóa cookie, session ID bị sao chép vẫn gửi lại. | Session backend từ chối cookie cũ. |
| L03 | Logout request CSRF từ site lạ. | Endpoint từ chối theo chính sách CSRF/Origin. |
| L04 | SPA logout khi token nằm trong memory và storage legacy. | Mọi nơi được quản lý đều bị dọn; token mới không tự xuất hiện. |
| L05 | Tab A logout, tab B đang mở. | B nhận tín hiệu/kiểm tra trạng thái và không tiếp tục sử dụng phiên cũ. |
| L06 | Refresh response trả về sau logout. | Response bị bỏ, không lưu AT/RT mới. |
| L07 | Hai node BFF cùng có phiên. | Vô hiệu phiên/token state có hiệu lực trên tất cả node theo chính sách. |
| L08 | Mobile logout nhưng app có background sync. | Job dùng credential cũ bị dừng/vô hiệu. |
| L09 | iOS xóa Keychain token của tài khoản A. | Token A không còn trong kho ứng dụng; token của B không bị xóa. |
| L10 | Android xóa ciphertext và khóa token riêng. | Credential của tài khoản đó không còn dùng được, khóa dùng chung không bị xóa nhầm. |
| L11 | AS trả HTTP 200 revoke refresh token. | Ghi nhận AS đã xử lý request; không tự coi mọi JWT access token hết hiệu lực. |
| L12 | AS trả HTTP 200 cho token không tồn tại. | Client xử lý an toàn, không suy từ response sự tồn tại token. |
| L13 | Revocation endpoint timeout. | Local logout vẫn có hiệu lực, remote state được ghi chưa xác nhận. |
| L14 | JWT access token chưa hết hạn, không có denylist. | Tài liệu/test thể hiện RS có thể vẫn chấp nhận token, không giả báo revoke tức thì. |
| L15 | JWT token trong denylist đã xác minh. | RS từ chối dù `exp` chưa qua. |
| L16 | Opaque `active=false` sau revoke. | RS từ chối. |
| L17 | Opaque `active=true` còn cache sau revoke. | Test độ trễ chấp nhận theo TTL/invalidation; không tuyên bố thời gian thực sai. |
| L18 | RT-1 đã rotation thành RT-2; logout lúc request refresh đang bay. | AS/client không để RT mới tái tạo grant/phiên ngoài ý định. |
| L19 | Token bị revoke từ admin panel, mobile đang offline. | Khi online/refresh tiếp, app nhận trạng thái và dọn token theo chính sách; không khẳng định dọn tức thì khi offline. |
| L20 | “Logout all devices” với hai thiết bị online, một offline. | Các session/grant thuộc phạm vi bị thu hồi, RS enforcement phù hợp và thiết bị offline bị từ chối khi liên lạc lại. |
| L21 | Logout ứng dụng nhưng OP vẫn có phiên SSO. | Không nhầm ứng dụng đã logout với OP đã logout; test giao thức OIDC nếu yêu cầu. |
| L22 | Logout OP nhưng JWT RS còn hạn. | Phát hiện cửa sổ token còn sống nếu không có trạng thái bổ sung. |
| L23 | Access token chỉ cho `orders.read` bị lộ. | Payments API từ chối sai audience, Orders API vẫn kiểm tra revoke + owner/tenant. |
| L24 | Sau logout, dữ liệu token vẫn xuất hiện trong logs/traces. | Test redaction thất bại và yêu cầu khắc phục nguồn rò. |
| L25 | Client refresh bị `invalid_grant`. | Ngừng retry vô hạn, dọn token local và vào luồng đăng nhập lại khi phù hợp. |
| L26 | Token service account không thuộc phiên người dùng bị logout. | Không xóa nhầm grant/client credential độc lập ngoài phạm vi. |

### Đừng nhầm kiểm thử local và kiểm thử hiệu lực server

- **Unit test token manager** có thể chứng minh state/async response bị bỏ sau logout, nhưng không chứng minh AS đã revoke.
- **Integration test BFF/mobile** có thể kiểm tra cookie, session store, secure storage và request tới revocation endpoint.
- **Integration test RS** phải xác minh access token cũ còn bị chấp nhận hay không sau revoke, kể cả JWT/opaque và cache.
- **End-to-end “logout all” test** cần nhiều client/thiết bị/phiên, không chỉ một tab.
- Khi giả lập AS, test phải mô phỏng đúng **HTTP 200 với token không tồn tại**, timeout, `unsupported_token_type` và cập nhật token family theo hợp đồng.

## 21. Tình huống học tập

### A. Đã xóa localStorage nhưng request vẫn thành công

Một SPA xóa `localStorage["access_token"]` khi người dùng nhấn logout. Trước đó attacker đã sao chép access JWT. JWT còn hạn, resource server chỉ kiểm chữ ký và `exp`.

**Câu hỏi:** Logout có ngăn bản sao attacker gọi API không?

> **Không.** Xóa local không vô hiệu bản sao. Muốn ngừng token trước `exp` cần cơ chế revocation/denylist/trạng thái tại RS. Nếu chưa có, phải nêu rõ cửa sổ rủi ro còn lại.

### B. Refresh token bị revoke nhưng response cũ lưu token mới

Ứng dụng có refresh request đang chờ, đồng thời người dùng logout. Callback refresh đến muộn và ghi access token mới vào storage.

**Câu hỏi:** Lỗi nằm ở đâu?

> Ở **điều phối vòng đời token**: thiếu khóa/generation guard, chưa chặn refresh và/hoặc phạm vi revoke không bao phủ grant/token family đúng cách. Cần bảo vệ cả client state lẫn phía AS.

### C. BFF xóa cookie nhưng phiên backend còn sống

Một bản sao cookie được gửi lại từ máy khác sau logout và backend vẫn chấp nhận session ID.

**Câu hỏi:** Xóa cookie browser có đủ không?

> **Không.** Backend phải vô hiệu server-side session. Cookie chỉ là bản sao credential trên thiết bị hiện tại; xóa nó không xóa bản sao đã bị lấy cắp.

### D. Opaque token đã revoke nhưng API vẫn truy cập được vài chục giây

AS đã trả `active=false` cho introspection mới, nhưng API vẫn dùng cache `active=true` từ trước.

**Câu hỏi:** Có thể tuyên bố “revoke lập tức có hiệu lực” không?

> **Không**, trừ khi API có cơ chế invalidation/thời gian nhất quán đáp ứng cam kết. Phải xác định TTL và độ trễ từ AS đến RS, đặc biệt với API nhạy cảm.

### E. Một tài khoản có ba thiết bị

Người dùng logout trên điện thoại A, laptop B vẫn đăng nhập và điện thoại C đang offline.

**Câu hỏi:** Có nên xóa tất cả refresh token cùng `sub` không?

> **Không mặc định.** Phạm vi tùy yêu cầu “logout thiết bị này” hay “logout all”. AS cần quản lý grant/session/family theo thiết bị hoặc client và xác định phạm vi thu hồi chính xác. Khi “logout all”, C sẽ bị từ chối tại lần liên lạc tiếp theo nếu cơ chế đã được áp dụng phù hợp.

### Câu hỏi tự đánh giá

1. Ba khái niệm **local deletion**, **server revocation** và **resource-server enforcement** khác nhau ở đâu?
2. Vì sao xóa access token trong RAM không ngăn kẻ đã sao chép Bearer token?
3. Xóa cookie `HttpOnly` cần tác động gì ở browser và ở server?
4. Vì sao SPA có thể “hồi sinh” token sau logout nếu refresh response đến muộn?
5. iOS Keychain và Android Keystore giúp giảm rủi ro gì? Vì sao vẫn cần revoke?
6. RFC 7009 trả HTTP 200 có bảo đảm mọi JWT access token bị từ chối ngay không?
7. Introspection cache ảnh hưởng độ trễ revoke của opaque token thế nào?
8. Khi nào OIDC logout khác với thu hồi OAuth grant?
9. Làm sao kiểm thử “logout mọi thiết bị” thay vì chỉ “logout tab hiện tại”?
10. Cần ghi những gì vào audit mà không làm lộ token/secret?

## 22. Ghi nhớ

- **Xóa token local không đồng nghĩa thu hồi token đã phát hành.** Một bản sao ở thiết bị khác hoặc trong tay attacker vẫn có thể được trình đến hệ thống khi token còn hiệu lực.
- **Logout phải có phạm vi rõ**: thiết bị hiện tại, phiên BFF, OAuth grant/token family, mọi thiết bị hay phiên SSO OIDC.
- **Browser BFF** cần vô hiệu server-side session và authorized-client state, xóa cookie đúng cách, bảo vệ CSRF; **SPA** phải dọn memory/storage/tabs/workers và chặn response refresh đến muộn.
- **Mobile** cần xóa credential khỏi Keychain/Keystore-backed storage, quản lý backup, background tasks và multi-account; không chỉ xóa UI.
- **RFC 7009** giúp yêu cầu AS revoke token; response 200 không thay cơ chế xác nhận hiệu lực tại mọi resource server.
- **JWT tự chứa** có thể tiếp tục hợp lệ đến `exp` nếu không có trạng thái revoke bổ sung; **opaque token** có thể ngừng ở lần introspection mới nhưng bị trì hoãn bởi cache.
- **Refresh token rotation/token family** cần điều phối race và chính sách revoke phù hợp để không phát hành token mới sau logout.
- **ID token, access token, refresh token và session cookie có vai trò khác nhau**. Audience/scope và object-level authorization vẫn phải được kiểm tra ở API.
- **Không log nguyên token**, không hứa revoke tức thì nếu chưa có enforcement, và kiểm thử cả local cleanup, AS state lẫn các RS.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, token endpoint và grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, token hint và HTTP response.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái opaque token và `active`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token, lỗi `invalid_token` và phương thức truyền token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519) và [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `exp`, `aud`, access-token claims và validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, giới hạn quyền và giảm nguy cơ token bị đánh cắp/phát lại.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained access tokens.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) và [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): phiên OIDC và logout giữa OP/RP khi hỗ trợ.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) và [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): session, token storage, logout và giảm rủi ro.
- [Apple Keychain Services](https://developer.apple.com/documentation/security/keychain_services) và [Android Keystore system](https://developer.android.com/privacy-and-security/keystore): lưu và xóa credential ở mobile.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html) và [Spring Security Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): authorized-client state, logout handlers và phiên ứng dụng.
