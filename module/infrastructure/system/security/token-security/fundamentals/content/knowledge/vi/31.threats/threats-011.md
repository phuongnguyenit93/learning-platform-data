# Open redirect: lỗ hổng chuyển hướng trong OAuth 2.0/OIDC và an toàn token

## 1. Open redirect là gì và vì sao ảnh hưởng đến token?

**Open redirect** (chuyển hướng mở) xảy ra khi ứng dụng dùng một địa chỉ do người gọi kiểm soát để chuyển trình duyệt sang trang khác, nhưng không kiểm tra đích đến theo một chính sách tin cậy. Bản thân phản hồi HTTP `302` hoặc `303` là tính năng hợp lệ; lỗ hổng nằm ở **quyền quyết định URL đích bị trao cho đầu vào không đáng tin**.

Ví dụ chức năng "đăng nhập xong quay lại trang cũ":

```http
GET /login?next=https%3A%2F%2Fattacker.example%2Flanding HTTP/1.1
Host: app.example.com
```

Nếu server lấy nguyên `next` và trả:

```http
HTTP/1.1 302 Found
Location: https://attacker.example/landing
```

thì một liên kết bắt đầu từ `https://app.example.com` có thể điều hướng người dùng đến website do kẻ tấn công kiểm soát. Đây là ví dụ cơ bản của open redirect.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, open redirect đáng quan tâm vì luồng xác thực OAuth 2.0/OIDC dựa trên **chuỗi chuyển hướng giữa trình duyệt, OAuth client (relying party) và Authorization Server (AS)/OpenID Provider (OP)**. Nếu một điểm chuyển hướng bị khai thác hoặc kiểm tra `redirect_uri` lỏng lẻo, hậu quả có thể gồm:

- Dẫn người dùng từ tên miền đáng tin đến trang giả mạo nhằm lừa nhập thông tin đăng nhập hoặc cấp quyền.
- Chuyển authorization response chứa `code`, `state` hoặc (ở các flow cũ) token đến đích ngoài dự kiến, **khi luồng và cách xây dựng URL cho phép dữ liệu đi theo**.
- Làm rò rỉ dữ liệu xác thực qua URL, trang trung gian, script, lịch sử trình duyệt hoặc log nếu ứng dụng đặt dữ liệu nhạy cảm trong URL.
- Chuyển người dùng đến vị trí bất ngờ sau login/logout, gây nhầm lẫn phiên, phá luồng ứng dụng hoặc tạo bước đệm cho cuộc tấn công khác.

**Phân biệt quan trọng:** open redirect **không tự động đồng nghĩa** access token bị đánh cắp. Tính khai thác phụ thuộc điểm chuyển hướng, nội dung authorization response, kiểu flow, nơi token được lưu, PKCE, cách callback xử lý mã và các lớp bảo vệ khác.

## 2. Nhận diện các điểm chuyển hướng

| Điểm chuyển hướng | Chủ thể quyết định đích | Ý nghĩa trong OAuth/OIDC | Rủi ro nếu chấp nhận URL tùy ý |
| --- | --- | --- | --- |
| `redirect_uri` trong `/authorize` | OAuth client đăng ký với AS/OP; AS phải đối chiếu | Địa chỉ AS đưa trình duyệt về cùng `code`/`state` sau xác thực | Authorization response có thể đi tới trang do kẻ tấn công kiểm soát |
| Callback của client, ví dụ `/oauth/callback` | Client xử lý response | Kiểm tra `state`, đổi `code`, xác thực ID Token, lập phiên | Có thể chuyển tiếp response hoặc token trước khi xác minh |
| Tham số quay về sau đăng nhập, ví dụ `next`, `returnUrl` | Ứng dụng client | Điều hướng người dùng tới màn hình họ cần | Open redirect/phishing, đôi khi rò rỉ dữ liệu qua URL |
| Endpoint chuyển hướng tiện ích, ví dụ `/redirect?url=...` | Ứng dụng hoặc dịch vụ trung gian | Điều hướng tới tài nguyên khác | Có thể bị lạm dụng nếu đặt làm `redirect_uri` hoặc trên luồng nhạy cảm |
| `post_logout_redirect_uri` trong OIDC RP-Initiated Logout | RP đã đăng ký đích tại OP | Sau khi OP kết thúc phiên, chuyển browser về RP | Chuyển sang website ngoài dự kiến sau logout |
| Link do frontend tự xử lý | JavaScript đọc query/hash rồi gán `location` | Điều hướng trong ứng dụng | Có thể là **client-side open redirect** dù backend không trả `302` |

Một dạng open redirect đơn giản trong Java Servlet:

```java
// Ví dụ KHÔNG AN TOÀN: chỉ dùng để nhận diện lỗi.
String target = request.getParameter("next");
response.sendRedirect(target);
```

Nếu `target` đến từ query, body, cookie hoặc từ một giá trị chưa kiểm soát trong `state`, caller có thể điều khiển đích. Việc chuyển redirect từ server sang JavaScript cũng không làm rủi ro biến mất:

```javascript
// Ví dụ KHÔNG AN TOÀN.
const target = new URLSearchParams(location.search).get("next");
if (target) location.assign(target);
```

Cả hai ví dụ đều bỏ qua bước kiểm tra URL đích.

## 3. Ranh giới tin cậy trong Authorization Code Flow

Luồng khuyến nghị cho ứng dụng web hiện đại thường là **Authorization Code Flow + PKCE**, phối hợp `state` (và `nonce` khi dùng OIDC):

```mermaid
sequenceDiagram
    autonumber
    participant U as Trình duyệt
    participant C as OAuth Client / RP
    participant A as Authorization Server / OP
    U->>C: GET /login (màn hình muốn quay về)
    C->>C: Tạo state, PKCE verifier/challenge, nonce nếu OIDC
    C->>C: Lưu giao dịch và đích quay về đã kiểm duyệt
    C-->>U: Redirect tới /authorize với redirect_uri đã đăng ký
    U->>A: Yêu cầu xác thực
    A->>A: Xác minh client, redirect_uri, yêu cầu
    A-->>U: Redirect về callback?code=...&state=...
    U->>C: Gọi callback của client
    C->>C: Xác minh state và issuer, tiêu thụ giao dịch
    C->>A: Đổi code với PKCE code_verifier
    A-->>C: Token response
    C->>C: Xác minh ID Token nếu OIDC; tạo phiên
    C-->>U: Redirect tới route nội bộ đã cho phép
```

Ba quyết định cần tách biệt:

1. **AS/OP quyết định địa chỉ callback hợp lệ** bằng cách so `redirect_uri` trong authorization request với các URI client đã đăng ký.
2. **Client quyết định có chấp nhận authorization response** bằng cách đối chiếu `state` với giao dịch phiên, ràng buộc issuer, đổi code qua đúng token endpoint và xác minh token.
3. **Ứng dụng quyết định màn hình sau đăng nhập** từ danh sách các đường dẫn được phép, không tin giá trị đích do callback hoặc trình duyệt tự cung cấp.

Điểm thứ ba hay bị bỏ sót vì developer nghĩ rằng "đã xác thực thành công thì redirect đi đâu cũng được". Tuy nhiên một callback an toàn vẫn có thể kết thúc bằng open redirect nếu sử dụng `next` tùy ý.

### 3.1. Vì sao không thể lấy "đã cùng domain" làm bằng chứng an toàn?

Giả sử AS chỉ cho phép:

```text
https://app.example.com/oauth/redirect?target=https://attacker.example/collect
```

Nếu chính `/oauth/redirect` là endpoint chuyển hướng mở, AS có thể hoàn thành redirect tới URL dưới tên miền client và **endpoint đó lại chuyển trình duyệt sang nơi khác**. Exact matching chỉ có ý nghĩa khi URI được đăng ký thực sự là một endpoint an toàn, cố định và không đẩy dữ liệu xác thực ra ngoài.

Một URI kiểu `https://app.example.com/redirect?to=...` vì vậy không nên được dùng làm callback OAuth, kể cả khi thuộc domain của ứng dụng.

## 4. Các chuỗi tấn công cần hiểu đúng

### 4.1. Authorization Server kiểm tra `redirect_uri` yếu

Kịch bản: AS cho phép client đăng ký `https://client.example.com/oauth/callback` nhưng khi xử lý authorization request lại chấp nhận mọi URL bắt đầu bằng chuỗi `https://client.example.com`. Một URL như:

```text
https://client.example.com.attacker.example/callback
```

**không** thuộc hostname `client.example.com`. Nếu AS vẫn gửi authorization response đến đó, kẻ tấn công có thể nhận authorization code hoặc dữ liệu response.

Khi code bị lộ, PKCE S256 làm giảm khả năng đổi code thành token nếu kẻ tấn công không có `code_verifier` tương ứng. Nhưng PKCE không biến cấu hình `redirect_uri` thiếu chính xác thành an toàn: vẫn có nguy cơ lộ dữ liệu và nhiều cách kết hợp lỗi khác.

### 4.2. OAuth client có open redirect tại callback hoặc endpoint trung gian

Kịch bản: client đăng ký endpoint nhận response hợp lệ nhưng sau khi nhận `code`/`state` lại chuyển hướng đến `next` tùy ý, hoặc sử dụng một redirector khác làm callback. Hậu quả thay đổi theo thứ tự xử lý:

- Nếu client **đổi code thành token, xác minh và xóa tham số nhạy cảm** trước khi chuyển trang, việc redirect ra ngoài có thể chủ yếu tạo đường dẫn phishing; vẫn cần chặn.
- Nếu client **chuyển tiếp nguyên query chứa authorization code** sang đích khác hoặc phản chiếu code vào URL mới, code có thể bị lộ.
- Với các flow cũ đưa token trong fragment (`#access_token=...`), hành vi xử lý fragment và chuyển hướng của browser/script có thể khiến token đi theo hoặc được đọc tại trang ngoài; không dựa vào đặc tính fragment để bảo vệ token.

Không suy luận rằng mọi `302` trên callback đều làm rò rỉ code: cần kiểm tra thực tế `Location` và dữ liệu có được chuyển tiếp hay không.

### 4.3. Return URL bị nhét vào `state`

`state` được dùng để liên kết authorization response với yêu cầu xác thực; nó **không phải nơi để tin tưởng URL trả về**. Lỗi thiết kế thường gặp:

```text
state = "https://attacker.example/after-login"
...
sau callback: redirect(state)
```

Hoặc ứng dụng mã hóa cả URL vào `state` nhưng không bảo vệ tính toàn vẹn và ràng buộc phiên. Kẻ tấn công có thể dẫn nạn nhân vào quy trình xác thực có đích kết thúc do mình chọn.

Mẫu tốt hơn: tạo `state` ngẫu nhiên không đoán được, lưu một bản ghi giao dịch phía server gồm `state`, session ID, mã route đã cho phép, PKCE verifier, nonce và thời hạn. Khi callback, kiểm tra và **tiêu thụ giao dịch một lần**, rồi chọn đích từ dữ liệu đã kiểm duyệt.

### 4.4. Open redirect hỗ trợ phishing

Một URL khởi đầu từ domain tin cậy khiến nạn nhân ít nghi ngờ:

```text
https://app.example.com/go?next=https%3A%2F%2Fattacker.example%2Ffake-login
```

Người dùng được điều hướng tới trang giả. Đây là rủi ro ngay cả khi URL không làm lộ token tự động. Kẻ tấn công có thể lợi dụng độ tin cậy của domain để thuyết phục người dùng cung cấp mật khẩu, OTP hoặc chấp thuận quyền truy cập.

### 4.5. Logout redirect

OIDC RP-Initiated Logout có thể dùng `post_logout_redirect_uri` để chuyển trình duyệt về RP. OP cần xác minh giá trị đó theo cơ chế đăng ký của client; client cũng không nên tự tạo "logout thành công rồi redirect đến `next` tùy ý". Kết thúc phiên thành công không làm một URL bên ngoài trở nên đáng tin cậy.

## 5. Bảo vệ `redirect_uri` tại Authorization Server

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), cách kiểm tra cơ bản cho authorization endpoint là **so khớp chính xác** với URI đã đăng ký, với ngoại lệ được chuẩn quy định như cổng thay đổi đối với loopback redirect URI của native app theo RFC 8252.

| Cách kiểm tra | Đánh giá | Vì sao |
| --- | --- | --- |
| So khớp chuỗi URI chính xác với redirect URI đã đăng ký | Nên dùng cho web client | Tránh khác biệt host/path/query không dự kiến |
| Chỉ kiểm tra hostname bằng `startsWith` | Nguy hiểm | Có thể bị qua mặt bởi hostname trông giống hoặc userinfo |
| Cho phép wildcard `https://*.example.com/*` | Nên tránh | Mở rộng bề mặt tới subdomain hoặc endpoint có open redirect |
| Chỉ kiểm tra `endsWith("example.com")` | Không đủ | Có thể nhận domain sai nếu thiếu ranh giới dấu chấm và chính sách URI đầy đủ |
| Cho phép mọi URL khi client_id đã hợp lệ | Không an toàn | Đưa authorization response ra ngoài client đã đăng ký |
| Khớp toàn bộ URL nhưng endpoint đích là redirector | Vẫn rủi ro | Endpoint hợp lệ tiếp tục chuyển dữ liệu ra nơi khác |

Ví dụ mô tả quy tắc kiểm tra tại AS:

```java
// Giả mã: danh sách đã đăng ký lấy từ dữ liệu client tin cậy.
Set<String> registeredUris = registeredClient.redirectUris();
String requestedUri = authorizationRequest.redirectUri();

if (requestedUri == null || !registeredUris.contains(requestedUri)) {
    // Trả thông báo lỗi tại AS; KHÔNG redirect về requestedUri.
    renderLocalAuthorizationError();
    return;
}

// Tiếp tục kiểm tra client, response_type, scope, PKCE, consent...
```

Đây là **mô tả chính sách**, không phải một authorization server đầy đủ. Trong hệ thống có nhiều hình thức redirect hợp lệ, thư viện OAuth đã được bảo trì cần thực hiện các điều kiện tiêu chuẩn tương ứng. Nếu `redirect_uri` thiếu, AS xử lý theo quy định của giao thức/profile và cấu hình client; không tự nhận giá trị từ một URL người dùng gửi lên.

Các nguyên tắc đi kèm:

1. **Đăng ký URI cụ thể**, ưu tiên HTTPS đối với web client. Chỉ dùng redirect scheme/loopback cho native app theo profile và RFC áp dụng.
2. **Không redirect đến `redirect_uri` khi xác thực URI thất bại.** AS nên hiển thị lỗi cục bộ để tránh biến chính AS thành open redirector.
3. **Không cho open redirect endpoint làm callback.** Việc URI có ở danh sách đăng ký không bảo đảm nội dung endpoint an toàn.
4. **Ràng buộc authorization code với client và redirect URI**, kiểm tra redirect URI tại token endpoint theo quy tắc của giao thức, dùng code một lần và tuổi thọ ngắn.
5. **Bắt buộc hoặc sử dụng PKCE S256 theo profile phù hợp**, và ở client kiểm tra `state`/issuer; PKCE, `state` và `nonce` bảo vệ các giai đoạn khác nhau.

## 6. Bảo vệ đích chuyển trang bên trong client

### 6.1. Lựa chọn an toàn nhất: route ID thay vì URL do người dùng nhập

Nếu sản phẩm chỉ cần quay về vài màn hình đã biết, hãy nhận một **mã route** rồi map sang đường dẫn nội bộ cố định. Đây là cách tránh toàn bộ bài toán phân tích URL phức tạp.

Ví dụ Java:

```java
import java.util.Map;

public final class PostLoginRoutes {
    private static final Map<String, String> ROUTES = Map.of(
        "home", "/app/home",
        "orders", "/app/orders",
        "profile", "/app/profile"
    );

    private PostLoginRoutes() {}

    public static String resolve(String requestedRoute) {
        return ROUTES.getOrDefault(requestedRoute, "/app/home");
    }
}
```

Trong một luồng có session phía server:

```java
// Bắt đầu login: routeKey lấy từ request chỉ là mã lựa chọn.
String approvedReturnPath = PostLoginRoutes.resolve(requestedRouteKey);
String state = cryptographicallyRandomState();

// Lưu state, sessionId, approvedReturnPath, PKCE verifier,
// issuer dự kiến, OIDC nonce (nếu dùng), expiresAt.
loginAttemptStore.save(state, sessionId, approvedReturnPath /* ... */);

// Callback: kiểm tra state + session, issuer, code/PKCE, token trước.
// consumeAtomically phải trả về đúng giao dịch chưa từng được dùng.
LoginAttempt attempt = loginAttemptStore.consumeAtomically(sessionId, callbackState)
    .orElseThrow(() -> new SecurityException("Invalid or replayed state"));

verifyOAuthCallbackAndCreateSession(attempt, callbackParams);

// Chỉ đích đã được chọn từ bảng route được sử dụng.
response.sendRedirect(attempt.approvedReturnPath());
```

Các tên `cryptographicallyRandomState`, `loginAttemptStore` và `verifyOAuthCallbackAndCreateSession` là API **minh họa**, không có sẵn trong JDK. Triển khai thực tế nên dùng thư viện OAuth/OIDC được bảo trì, có kiểm tra state, issuer, PKCE và xác minh ID Token khi OIDC.

Nếu ứng dụng cần trở về đường dẫn với tham số như `/app/orders/42`, tốt hơn nên lưu mã định danh nghiệp vụ đã xác thực và tạo URL bằng **route builder** tin cậy với encode từng thành phần. Không nối một URL đầy đủ do client nhập vào `Location`.

### 6.2. Khi phải chấp nhận đường dẫn nội bộ động

Có thể cho phép **đường dẫn tương đối thuộc ứng dụng** với chính sách kiểm tra chặt chẽ, nhưng cần tính cả quy tắc phân tích URL của browser và thư viện framework. Ví dụ:

- Đường dẫn `/app/orders` có thể hợp lệ nếu thuộc nhóm route được cho phép.
- Chuỗi bắt đầu bằng `//` là **scheme-relative URL**: `//attacker.example/path` có thể đưa browser ra ngoài domain hiện tại.
- Dấu gạch chéo ngược `\`, percent encoding, double encoding và chuỗi Unicode dễ tạo cách hiểu khác nhau giữa bộ lọc, proxy, framework và browser.
- Các đường dẫn `/app/../redirect` hoặc path đã chuẩn hóa khác với đường dẫn kiểm tra ban đầu phải được xử lý nhất quán.
- Phải xét query và fragment riêng; không cho một query như `?next=https://...` kích hoạt redirector ở trang đích.

Vì vậy quy tắc `target.startsWith("/")` **không đủ**; cần tối thiểu chặn `//`, dấu gạch chéo ngược và các biến thể phân tích mơ hồ, chuẩn hóa rồi kiểm tra chính xác route/prefix theo ranh giới phân đoạn. Với đầu vào URL không thể kiểm chứng rõ ràng, sử dụng route ID là giải pháp ít sai sót hơn.

### 6.3. Chuyển đến dịch vụ bên ngoài có chủ đích

Nếu sản phẩm bắt buộc chuyển người dùng sang một số dịch vụ đối tác, đăng ký **danh sách URL đích cố định** và để client chọn bằng mã:

```java
import java.net.URI;
import java.util.Map;

public final class ExternalDestinations {
    private static final Map<String, URI> DESTINATIONS = Map.of(
        "help", URI.create("https://support.example.com/help"),
        "docs", URI.create("https://docs.example.com/start")
    );

    private ExternalDestinations() {}

    public static URI resolve(String destinationId) {
        return DESTINATIONS.get(destinationId);
    }
}
```

Nếu không tìm thấy mã, từ chối hoặc điều hướng tới trang nội bộ an toàn. Không xây URL động như `"https://partner.example/" + userInput` khi phần đường dẫn có thể điều hướng ngoài hoặc gọi tiếp endpoint khác không được kiểm soát. Đối với luồng rời khỏi ứng dụng nhạy cảm, cân nhắc trang thông báo chuyển sang domain khác.

**Không** sử dụng whitelist dựa trên substring, userinfo, regex tùy tiện hoặc giả định hậu tố domain. Ví dụ `https://app.example.com@attacker.example/path` hiển thị chuỗi tên miền quen thuộc trước ký tự `@`, nhưng hostname thực tế là `attacker.example`.

## 7. Những trường hợp kiểm tra URL dễ bị vượt qua

| Dữ liệu do kẻ tấn công nhập (minh họa) | Vì sao nguy hiểm | Kiểm tra cần có |
| --- | --- | --- |
| `https://app.example.com.attacker.example` | Nhìn có prefix đúng nhưng host khác | So khớp URI/host chính xác theo chính sách |
| `https://app.example.com@attacker.example` | Phần trước `@` là userinfo, không phải host | Không dùng prefix; chặn userinfo nếu không cần |
| `//attacker.example/path` | Browser hiểu là URL theo scheme hiện tại nhưng host ngoài | Không chấp nhận scheme-relative URL làm local path |
| `\\attacker.example\path` | Một số bộ phân tích/chuẩn hóa xử lý backslash gần giống slash | Không dựa vào parser bất nhất; chặn dạng mơ hồ |
| `%2F%2Fattacker.example` | Decoding ở tầng sau có thể tạo `//` | Chặn/chuẩn hóa một cách nhất quán; tránh decode hai lần |
| `https://app.example.com/redirect?to=https://attacker.example` | Host đầu tiên hợp lệ nhưng endpoint cuối là redirector | Kiểm tra cả hành vi endpoint; không đăng ký redirector |
| `javascript:alert(1)`, `data:text/html,...` | Không phải HTTP(S) điều hướng an toàn | Chỉ cho scheme được phép hoặc dùng route ID |
| `/app/../redirect?to=...` | Dot segment có thể đổi route đích sau chuẩn hóa | Normalize path và kiểm tra route cuối |
| `https://аpp.example.com` (ký tự giống Latin) | Tên miền Unicode có thể gây nhầm lẫn thị giác | Kiểm tra danh tính host đã xác thực và hạn chế homograph |

Các giá trị ở bảng dùng để giải thích cơ chế lọc sai. URL hợp lệ cuối cùng phụ thuộc browser, proxy và framework; thử nghiệm phải xác định **Location thực tế và nguồn gốc cuối cùng** thay vì chỉ so chuỗi đầu vào.

Đặc biệt cần phân biệt **canonicalization để so sánh host** với quy tắc **exact redirect URI matching của OAuth**. AS không nên tự chuẩn hóa/sửa URI theo ý mình để làm hai `redirect_uri` khác nhau trở thành một URI được chấp nhận.

## 8. Các cơ chế token security nào liên quan?

| Cơ chế | Giúp hạn chế điều gì? | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| Exact `redirect_uri` registration/matching | Không cho AS gửi authorization response đến callback chưa đăng ký | Callback đã đăng ký không được là open redirector |
| Authorization Code + PKCE S256 | Authorization code bị lấy cắp khó đổi thành token nếu thiếu verifier | Client vẫn phải giữ verifier, kiểm tra state và token |
| `state` gắn phiên và dùng một lần | Giảm login CSRF và callback không thuộc giao dịch | Không dùng raw state như URL đích; không thay thế allowlist |
| OIDC `nonce` | Ràng buộc ID Token với yêu cầu xác thực tương ứng | Không ngăn redirect sang trang khác, không chống mọi access-token replay |
| Issuer binding, kiểm tra `iss`/`aud` | Hạn chế mix-up, token từ issuer/audience sai | Không cho token lọt qua URL/log; kiểm tra đúng loại token |
| Quyền tối thiểu `scope`, `aud`, token ngắn hạn | Giảm phạm vi và khoảng thời gian token bị lộ có thể bị dùng | Không làm open redirect biến mất |
| DPoP/mTLS sender constraint | Token bị sao chép khó sử dụng nếu thiếu khóa/chứng chỉ | Không cứu luồng có token và private key cùng bị chiếm; không chống phishing |
| Refresh token rotation/reuse detection | Giúp phát hiện dùng lại refresh token đã luân chuyển | Bảo vệ lưu trữ refresh token và cơ chế thu hồi |
| Không lưu token trong URL/log | Hạn chế đường rò rỉ qua referrer, lịch sử, proxy/analytics | Kiểm soát XSS, CSRF, lưu trữ và bên nhận token |

**JWT và opaque token đều có thể bị lộ qua open redirect** nếu ứng dụng đưa chính giá trị token vào vị trí có thể chuyển tiếp/đọc được. JWT được ký chỉ bảo đảm tính toàn vẹn và nguồn phát hành; chữ ký không giúp giữ bí mật nội dung. Opaque token không chứa claims đọc được nhưng thường vẫn có giá trị như một bearer secret.

Không dùng **ID Token** làm access token để gọi API. RS phải xác thực access token theo loại token/profile thích hợp, bao gồm issuer, audience, thời hạn, quyền và cơ chế sender constraint nếu có.

## 9. Thực hành với Java/Spring: mẫu nên tránh và mẫu nên dùng

### 9.1. Mẫu sai: tin `returnUrl` từ callback

```java
// KHÔNG AN TOÀN. Người gọi có thể tự chọn địa chỉ bên ngoài.
@GetMapping("/oauth/callback")
public void callback(HttpServletRequest request, HttpServletResponse response)
        throws IOException {
    String returnUrl = request.getParameter("returnUrl");
    response.sendRedirect(returnUrl);
}
```

Đoạn mã còn thiếu hoàn toàn xác minh OAuth; nó chỉ dùng để chỉ ra lỗi chuyển hướng. Không nên tự bổ sung "kiểm tra đã có code" rồi coi callback an toàn.

### 9.2. Mẫu sai: chỉ kiểm tra tiền tố

```java
// KHÔNG AN TOÀN.
String returnUrl = request.getParameter("returnUrl");
if (returnUrl != null && returnUrl.startsWith("https://app.example.com")) {
    response.sendRedirect(returnUrl);
}
```

Chuỗi `https://app.example.com.attacker.example` vượt qua kiểm tra trên dù hostname không nằm trong hệ thống. Tương tự, kiểm tra bằng `contains("example.com")` không có giá trị ràng buộc nguồn gốc.

### 9.3. Mẫu nên dùng: đích quay về nằm trong giao dịch đã xác minh

Với Spring Security OAuth2 Client/OIDC Client, nên dùng bộ xử lý authorization request và authentication success handler của framework, cấu hình `redirect-uri` cố định và lưu `state`/PKCE trong kho giao dịch tin cậy. Khi xác thực thành công, dùng route ID đã kiểm duyệt, ví dụ:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

// Ví dụ bộ điều hướng sau khi Spring Security đã xác thực thành công.
// approvedRouteKey phải lấy từ login-attempt store gắn với state/session
// đã được framework hoặc luồng OAuth đáng tin cậy xác minh.
public final class ApprovedRouteSuccessHandler
        implements AuthenticationSuccessHandler {

    private final ApprovedRouteLookup routeLookup;

    public ApprovedRouteSuccessHandler(ApprovedRouteLookup routeLookup) {
        this.routeLookup = routeLookup;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication
    ) throws IOException {
        String routeKey = routeLookup.consumeApprovedRouteForAuthenticatedAttempt(
            request, authentication
        );
        String internalPath = PostLoginRoutes.resolve(routeKey);
        response.sendRedirect(response.encodeRedirectURL(internalPath));
    }
}

// ApprovedRouteLookup là giao diện do ứng dụng định nghĩa để lấy
// giao dịch đã gắn với phiên và được xác thực, không đọc query tùy ý.
```

Đây là **ví dụ thành phần**, không phải một chương trình Spring hoàn chỉnh: `ApprovedRouteLookup` và kho giao dịch phải do ứng dụng triển khai và kiểm tra. Tùy phiên bản Spring Security, các cách tích hợp cụ thể có thể khác. Cần bảo đảm không lấy `routeKey` từ query callback hoặc từ dữ liệu có thể bị sửa sau khi xác thực; nếu không, lỗi open redirect có thể tái xuất hiện ở tầng điều hướng.

## 10. Kiểm thử open redirect

Nên kiểm thử theo **điểm vào – giá trị nhập – Location thực tế – nguồn gốc cuối cùng – dữ liệu nhạy cảm có bị truyền đi không**. Các trường hợp sau vừa dùng cho unit/integration test vừa dùng cho kiểm thử bảo mật có kiểm soát.

| Thử nghiệm | Kỳ vọng an toàn |
| --- | --- |
| `next=https://attacker.example` | Bị từ chối hoặc quy về route nội bộ cố định |
| `next=//attacker.example` | Không xuất hiện `Location` trỏ ra host ngoài |
| `next=\\attacker.example\path` | Bị từ chối nếu parser có thể hiểu thành địa chỉ ngoài |
| `next=https://app.example.com.attacker.example` | Không được coi là host ứng dụng |
| `next=https://app.example.com@attacker.example` | Không được coi là host ứng dụng |
| `next=javascript:...` hoặc `data:...` | Không dùng làm đích redirect |
| `next=%2F%2Fattacker.example`, double encoding | Không vượt được kiểm tra sau các tầng decode |
| `next=/app/../redirect?to=...` | Kiểm tra route cuối sau chuẩn hóa, không tới redirector |
| `redirect_uri` chưa đăng ký tại AS | AS hiển thị lỗi cục bộ, không redirect đến giá trị không hợp lệ |
| URI có đúng host nhưng khác path/query so với URI đăng ký | Không được chấp nhận trái quy tắc exact matching |
| Client callback nhận `state` lạ, sai phiên hoặc dùng lại | Từ chối, không đổi code và không tạo session |
| Client callback nhận `code` kèm `returnUrl` ngoài danh sách | Không dùng `returnUrl` tùy ý để chuyển hướng |
| Callback hợp lệ | Đổi code qua PKCE, xác minh ID Token khi OIDC, điều hướng đúng route đã lưu |
| Thử redirect endpoint đặt trong redirect URI đã đăng ký | Không chuyển tiếp code/token/query sang trang ngoài |
| OIDC `post_logout_redirect_uri` không đăng ký | Không cho logout flow redirect đến URL đó |
| Frontend có xử lý query/hash để redirect | Không cho script điều hướng đến nguồn gốc ngoài trái chính sách |

Kiểm thử nên được thực hiện ở cả **AS**, **OAuth client**, **frontend**, **reverse proxy** và bộ xử lý logout nếu có. Test đầu vào chỉ kiểm tra chuỗi `Location` là chưa đủ: có thể có nhiều lần redirect liên tiếp dẫn tới điểm đến bên ngoài.

Khi giả lập luồng OAuth, không đưa token thật vào địa chỉ kiểm thử, log hoặc công cụ chia sẻ URL. Dùng tenant/môi trường test, tài khoản test và token có phạm vi tối thiểu.

## 11. Xử lý khi phát hiện open redirect trong luồng xác thực

1. **Khoanh vùng endpoint:** xác định đầu vào điều khiển redirect, điều kiện kích hoạt, client/AS/OP liên quan, liệu endpoint có được đăng ký làm `redirect_uri` hoặc `post_logout_redirect_uri` hay không.
2. **Xác định dữ liệu có thể lộ:** code, state, ID Token, access token, refresh token, cookie hoặc tham số nội bộ. Kiểm tra hành vi chuyển tiếp query, fragment, `Referer` và log; không giả định chắc chắn có lộ token.
3. **Chặn đường khai thác:** sửa điều hướng sang route/URL cho phép, vô hiệu endpoint redirector nếu cần, loại bỏ URI rủi ro khỏi đăng ký OAuth, tránh làm gián đoạn các callback hợp lệ.
4. **Đánh giá khả năng đổi code và dùng token:** có PKCE S256 không, code đã hết hạn/dùng một lần chưa, token còn hạn và dành cho audience/scope nào, refresh token có bị lộ không.
5. **Thu hồi theo mức ảnh hưởng:** thu hồi session, grant, refresh token hoặc access token qua cơ chế khả dụng; RS xác minh JWT offline có thể không nhận biết việc thu hồi ngay khi chưa có giải pháp hỗ trợ.
6. **Điều tra và giám sát:** rà soát sự kiện auth/token/API, cảnh báo chuyển hướng bất thường, phát hiện token reuse; không sao chép token nguyên văn vào ticket/chat/log.
7. **Chống tái diễn:** bổ sung kiểm thử URI mơ hồ, exact redirect URI matching, kiểm tra quyền sở hữu URI đã đăng ký, kiểm soát thay đổi cấu hình OAuth và rà soát mã dùng `sendRedirect`/`location.assign`.

Không nên chỉ cố gắng "che URL xấu" bằng cách encode mà không đổi cơ chế chọn đích: trình duyệt hoặc tầng khác có thể decode và điều hướng lại. Cần sửa **chính sách tin cậy đối với đích chuyển hướng**.

## 12. Câu hỏi tình huống

**Tình huống A.** AS chỉ kiểm tra `redirect_uri.startsWith("https://client.example.com")`. Vì sao đây là lỗi, và client có PKCE thì có cần sửa không?

**Gợi ý:** URI thuộc `client.example.com.attacker.example` vượt qua kiểm tra chuỗi; PKCE có thể hạn chế việc đổi code bị đánh cắp nhưng không thay thế exact matching hoặc ngăn phishing.

**Tình huống B.** Ứng dụng nhận query `next` trước login, lưu nó vào `state`, rồi sau callback `response.sendRedirect(state)`. Vì sao kiểm tra state khớp cũng chưa chắc đủ?

**Gợi ý:** state có thể khớp giao dịch nhưng giá trị đích ngay từ đầu đã do attacker chọn. Cần ràng buộc state với session và lưu **route đã kiểm duyệt** tách biệt khỏi state.

**Tình huống C.** Sau login, backend chỉ chuyển tới URL ngoài qua `302`; access token nằm trong cookie `HttpOnly` riêng. Token có bị lộ ngay qua `Location` hay không?

**Gợi ý:** Không thể kết luận token tự động lộ chỉ từ redirect. Cần kiểm tra cookie scope, query/fragment, referrer, script, redirect chain và việc gửi dữ liệu từ client. Tuy vậy open redirect vẫn là lỗi cần sửa vì phishing và khả năng kết hợp với các lỗ hổng khác.

## 13. Ghi nhớ

- **Open redirect** phát sinh khi đích redirect được quyết định bởi đầu vào không đáng tin; đây là rủi ro đặc biệt trong những giao dịch OAuth/OIDC có nhiều bước chuyển hướng.
- **AS** phải kiểm tra `redirect_uri` theo đăng ký và quy tắc exact matching, không trả redirect tới URI không hợp lệ, cũng không đăng ký open redirector làm callback.
- **Client** phải kiểm tra `state`/phiên, PKCE, issuer và token, sau đó chỉ chuyển người dùng đến **đích đã kiểm duyệt**. Mã route và bảng URL cố định giúp giảm sai sót.
- **PKCE, `state`, OIDC `nonce`, xác minh JWT/opaque token, `aud` và `scope`** là các lớp bảo vệ khác nhau; không lớp nào một mình sửa được open redirect.
- **Không đặt token trong URL hoặc log.** Phải xem xét toàn bộ chuỗi redirect và các tầng xử lý URL để đánh giá nguy cơ lộ token thực tế.
- Với các endpoint login/logout, kiểm tra cả giá trị đặc biệt (`//`, `@`, percent encoding, backslash, dot segment), frontend redirect và cấu hình reverse proxy.

**Chuẩn tham khảo:** OAuth 2.0 (RFC 6749); OAuth 2.0 Security Best Current Practice (RFC 9700); Proof Key for Code Exchange – PKCE (RFC 7636); OAuth 2.0 for Native Apps (RFC 8252); OAuth 2.0 Authorization Server Issuer Identification (RFC 9207); OpenID Connect Core 1.0; OpenID Connect RP-Initiated Logout 1.0.

