# Session creation: tạo và cấp phát phiên làm việc an toàn trên trình duyệt

## 1. Browser session là gì?

**Browser session** là trạng thái liên tục giúp ứng dụng nhận biết các request tiếp theo thuộc về cùng một người dùng hoặc cùng một lần tương tác đã được xác thực. HTTP về bản chất là giao thức không lưu trạng thái giữa các request; vì vậy ứng dụng thường dùng **session identifier (session ID)** để liên kết các request với một bản ghi session được quản lý ở server.

Ví dụ, sau khi người dùng đăng nhập thành công, server tạo một session ID ngẫu nhiên và gửi nó trong cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Ở request tiếp theo, browser tự gửi cookie phù hợp:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: __Host-session=RANDOM_OPAQUE_VALUE
~~~

Server tra cứu session ID trong kho session, xác định phiên còn hiệu lực, lấy danh tính và quyền tương ứng, rồi xử lý request. Cookie thường chỉ mang **mã định danh bí mật**, không nên mang trực tiếp mật khẩu hoặc toàn bộ hồ sơ người dùng.

Bài học thuộc chương **Session trên browser** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung tập trung vào thời điểm tạo session, sinh session ID, lưu trạng thái ở server, cấp cookie cho browser, xoay vòng session sau xác thực và quản lý vòng đời phiên. Những bước này tạo nền tảng cho bảo vệ cookie, chống session fixation, CSRF, chiếm quyền phiên và kiểm soát truy cập ứng dụng web.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả vòng đời tạo browser session từ request ẩn danh tới đăng nhập thành công.
2. Giải thích vai trò của session ID ngẫu nhiên, khó đoán và không chứa thông tin định danh.
3. Phân biệt session cookie ở browser với session record được lưu ở server.
4. Thiết kế bước tạo mới và rotate session ID để phòng session fixation.
5. Chọn thuộc tính cookie phù hợp như `Secure`, `HttpOnly`, `SameSite` và prefix `__Host-`.
6. Xác định thời hạn idle, absolute lifetime, revoke và logout server-side.
7. Liên hệ session creation với CSRF, XSS, CORS, HTTPS và authorization.
8. Kiểm chứng hành vi qua DevTools, Network và log server trong môi trường thử nghiệm.

## 2. Session được tạo khi nào?

Ứng dụng không nhất thiết phải tạo session xác thực ngay khi browser mở trang. Thời điểm tạo phụ thuộc chức năng và kiến trúc.

Các tình huống thường gặp:

| Tình huống | Có thể tạo session? | Mục đích |
| --- | --- | --- |
| Người dùng chỉ đọc trang công khai | Không nhất thiết | Không cần trạng thái riêng cho mỗi visitor. |
| Người dùng bắt đầu giỏ hàng hoặc quy trình nhiều bước | Có thể tạo anonymous session | Lưu trạng thái tạm, chưa xác thực danh tính. |
| Người dùng đăng nhập thành công | **Phải tạo hoặc rotate sang authenticated session** | Gắn phiên với danh tính đã xác minh. |
| Người dùng hoàn thành MFA hoặc step-up authentication | Thường rotate hoặc nâng cấp session có kiểm soát | Ghi nhận mức xác thực mới và thời điểm xác thực. |
| Người dùng thay đổi mật khẩu, vai trò hoặc quyền nhạy cảm | Có thể rotate và/hoặc revoke các phiên khác | Giảm nguy cơ phiên cũ tiếp tục có quyền quá rộng. |
| Người dùng đăng xuất | Revoke session ở server và xóa cookie ở browser | Kết thúc phiên hiện tại. |

Một session ẩn danh có thể hữu ích cho giỏ hàng hoặc CSRF token trước đăng nhập. Nhưng khi chuyển sang trạng thái đã xác thực, không nên đơn giản giữ nguyên ID ẩn danh nếu ID đó có thể đã bị kẻ tấn công biết trước. Server nên tạo session ID mới và liên kết dữ liệu hợp lệ cần giữ sang session mới.

### 2.1. Luồng tổng thể

~~~mermaid
flowchart TD
    A["Browser gửi request"] --> B{"Có session hợp lệ?"}
    B -->| "Không" | C["Tạo trạng thái ẩn danh nếu cần"]
    B -->| "Có" | D["Tra cứu và kiểm tra session"]
    C --> E["Hiển thị trang / đăng nhập"]
    E --> F["Người dùng gửi thông tin xác thực"]
    F --> G["Server xác minh mật khẩu / MFA / policy"]
    G -->| "Thất bại" | H["Từ chối, giới hạn thử lại, ghi nhận sự kiện"]
    G -->| "Thành công" | I["Tạo session ID mới"]
    I --> J["Lưu session record phía server"]
    J --> K["Set-Cookie với thuộc tính an toàn"]
    K --> L["Browser gửi cookie ở request tiếp theo"]
    L --> D
~~~

Điểm quyết định: **server xác minh danh tính trước khi cấp phiên đã xác thực**. Việc browser có cookie hay có một giá trị do client gửi không tự chứng minh user đã đăng nhập.

## 3. Hai thành phần: session ID và session record

Một mô hình phổ biến tách session thành hai phần.

### 3.1. Session ID ở browser

Session ID là một **bearer secret**: ai sở hữu giá trị hợp lệ có thể được server coi là đang nắm phiên, trừ khi có thêm ràng buộc hoặc kiểm tra khác. Do đó nó phải:

- Được sinh bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG).
- Có entropy đủ lớn để không thể dò đoán thực tế.
- Không chứa username, email, role, user ID hoặc dữ liệu nhạy cảm có thể đọc được.
- Không được tái sử dụng giữa các lần đăng nhập hoặc sau khi nâng quyền.
- Không xuất hiện trong URL, log, analytics hoặc thông báo lỗi.
- Được truyền qua HTTPS và lưu trong cookie với thuộc tính phù hợp.

Một cách triển khai phổ biến là sinh 32 byte ngẫu nhiên (256 bit) rồi encode base64url:

~~~js
import { randomBytes } from "node:crypto";

const sessionId = randomBytes(32).toString("base64url");
~~~

Đây là ví dụ Node.js. Dùng CSPRNG của nền tảng; không dùng `Math.random()`, timestamp, bộ đếm, UUID tự chế hoặc hash của username/password làm session ID.

### 3.2. Session record ở server

Server lưu một bản ghi gắn với session ID, ví dụ:

~~~json
{
  "userId": "user-482",
  "createdAt": "2026-11-22T05:00:00Z",
  "lastSeenAt": "2026-11-22T05:10:00Z",
  "expiresAt": "2026-11-22T13:00:00Z",
  "authLevel": "password+mfa",
  "csrfToken": "server-generated-random-value",
  "revoked": false
}
~~~

Đây là dữ liệu minh họa, không phải cấu trúc bắt buộc. Tùy hệ thống, record có thể lưu trong Redis, database, session service hoặc bộ nhớ server có kiểm soát.

Server có thể chỉ lưu **hash của session ID** thay vì giá trị gốc, tương tự cách bảo vệ bearer secret ở kho dữ liệu. Khi nhận cookie, server hash ID nhận được rồi tra cứu record tương ứng. Điều này giúp giảm tác động nếu kho session bị đọc trái phép; tuy nhiên session ID vẫn phải được bảo vệ trong transit, log và runtime.

Không lưu mật khẩu gốc, access token không cần thiết hoặc dữ liệu nhạy cảm không phục vụ kiểm tra session trong record.

### 3.3. Vì sao không đưa toàn bộ session vào cookie?

Nếu cookie chứa trực tiếp dữ liệu như:

~~~text
user=alice&role=admin&expires=...
~~~

người dùng có thể sửa giá trị nếu dữ liệu không được bảo vệ bằng cơ chế mật mã đúng. Kể cả khi cookie được ký hoặc mã hóa, ứng dụng vẫn cần quản lý khóa, expiry, revoke, rotation và replay.

Với **opaque server-side session**, browser chỉ giữ ID ngẫu nhiên; quyền và trạng thái được server tra cứu. Cách này thuận tiện cho revoke tức thời và cập nhật quyền, đổi lại cần kho session sẵn sàng và cơ chế đồng bộ giữa các instance.

Một số hệ thống dùng token tự chứa (ví dụ JWT) thay cho session ID tra cứu. Đó là mô hình khác, có trade-off riêng về thu hồi, rotation và kiểm soát trạng thái; không nên gọi mọi token là server-side browser session.

## 4. Sinh session ID an toàn

### 4.1. Entropy và khả năng đoán

Session ID cần đủ ngẫu nhiên để việc đoán thử không khả thi. Một lựa chọn thực tế là ít nhất 128 bit entropy từ CSPRNG; 256 bit thường đơn giản và có biên an toàn rộng.

Nếu ID là 32 byte ngẫu nhiên, có 256 bit entropy trước khi encode. Base64url chỉ đổi cách biểu diễn, không tạo thêm entropy.

Không nên tự xây format như:

~~~text
session-<userId>-<timestamp>-<counter>
~~~

Các thành phần dễ dự đoán, có thể tiết lộ danh tính hoặc tạo không gian đoán nhỏ. Hash một chuỗi dễ đoán cũng không làm nó trở nên ngẫu nhiên.

### 4.2. Mỗi phiên phải có ID riêng

Không tái sử dụng session ID:

- Giữa hai người dùng.
- Giữa các lần đăng nhập của cùng người dùng.
- Giữa anonymous và authenticated session.
- Trước và sau khi hoàn thành MFA.
- Trước và sau khi thay đổi quyền quan trọng.

Khi rotate, tạo ID mới từ CSPRNG. Không biến ID cũ thành ID mới bằng cách nối thêm timestamp hoặc tăng bộ đếm.

### 4.3. Không đặt session ID trong URL

Tránh:

~~~text
https://app.example.test/account?session=SECRET
https://app.example.test/#session=SECRET
~~~

Session ID trong URL có thể bị lưu trong browser history, bookmark, log, analytics, ảnh chụp màn hình hoặc liên kết được chia sẻ. Fragment không gửi trong request-target HTTP ban đầu nhưng JavaScript cùng trang vẫn có thể đọc và chuyển tiếp nó.

Dùng cookie với thuộc tính phù hợp cho browser session. Không dùng query hoặc fragment như phương tiện thay thế cookie cho session secret.

## 5. Tạo session sau khi xác thực thành công

Một quy trình đăng nhập server-side thường gồm:

1. Nhận thông tin xác thực qua HTTPS.
2. Validate cấu trúc đầu vào và áp dụng rate limit/lockout phù hợp.
3. Xác minh mật khẩu bằng password hash đã lưu; nếu có MFA, xác minh yếu tố bổ sung theo chính sách.
4. Kiểm tra trạng thái tài khoản, yêu cầu xác thực lại và các policy liên quan.
5. **Hủy hoặc vô hiệu hóa session ID trước đăng nhập**, nếu có.
6. Sinh session ID mới bằng CSPRNG.
7. Tạo session record gắn với user ID, auth level, thời gian tạo/hết hạn và trạng thái revoke.
8. Gửi cookie session qua `Set-Cookie` với thuộc tính an toàn.
9. Trả response không cache dữ liệu nhạy cảm và chuyển người dùng sang trang phù hợp.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Pragma: no-cache
Content-Type: application/json
~~~

Không trả session ID trong JSON body đồng thời với cookie nếu frontend không có yêu cầu rõ ràng và threat model đã đánh giá. Việc có nhiều bản sao bearer secret làm tăng bề mặt rò rỉ.

### 5.1. Mẫu pseudocode

~~~js
async function login(request, response) {
  const credentials = validateLoginInput(request.body);

  const user = await users.findByEmail(credentials.email);
  const passwordValid = user
    ? await verifyPassword(credentials.password, user.passwordHash)
    : false;

  if (!user || !passwordValid || user.disabled) {
    await recordFailedLogin(credentials.email);
    throw unauthorized();
  }

  if (user.requiresMfa) {
    return beginMfaChallenge(user);
  }

  // Vô hiệu hóa anonymous/pre-auth session nếu có.
  await revokeSessionFromRequest(request);

  const sessionId = randomBytes(32).toString("base64url");
  const now = new Date();

  await sessionStore.create({
    idHash: hashSessionId(sessionId),
    userId: user.id,
    createdAt: now,
    lastSeenAt: now,
    expiresAt: addHours(now, 8),
    authLevel: "password",
    revoked: false
  });

  response.setHeader(
    "Set-Cookie",
    "__Host-session=" + sessionId +
      "; Path=/; Secure; HttpOnly; SameSite=Lax"
  );
  response.setHeader("Cache-Control", "no-store");
  response.status(200).json({ authenticated: true });
}
~~~

Đây là pseudocode minh họa, cần bổ sung xử lý lỗi, giao dịch nguyên tử, MFA, CSRF, cookie serialization đúng thư viện và quản lý vòng đời. `hashSessionId` nên là một phép băm phù hợp với thiết kế lookup; không dùng nó thay CSPRNG khi sinh ID.

### 5.2. MFA và session creation

Nếu ứng dụng yêu cầu MFA, **chưa cấp session có đầy đủ quyền** chỉ sau khi mật khẩu đúng. Có thể tạo một trạng thái pre-authentication ngắn hạn, giới hạn quyền và chỉ dùng cho bước MFA. Khi MFA thành công:

- Rotate sang session ID mới.
- Ghi nhận auth level và thời điểm MFA.
- Hủy pre-auth session.
- Chỉ cấp quyền đã được xác minh.
- Đặt timeout ngắn cho challenge và giới hạn số lần thử.

Nếu ứng dụng cho phép một session tạm trong lúc MFA, mọi endpoint phải phân biệt trạng thái `pre-auth` với trạng thái `authenticated`; không chỉ dựa vào việc cookie tồn tại.

## 6. Session fixation và lý do phải rotate ID

**Session fixation** xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết hoặc kiểm soát trước khi nạn nhân đăng nhập. Nếu ứng dụng giữ nguyên ID đó sau đăng nhập, kẻ tấn công có thể dùng lại ID để truy cập phiên đã xác thực.

Luồng lỗi:

~~~mermaid
sequenceDiagram
    participant A as Kẻ tấn công
    participant V as Nạn nhân
    participant S as Server

    A->>S: Tạo session ẩn danh, nhận ID = X
    A->>V: Khiến nạn nhân dùng URL/cookie có ID X
    V->>S: Đăng nhập với session ID X
    S-->>V: Giữ nguyên ID X và gắn user vào session
    A->>S: Gửi lại ID X
    S-->>A: Có thể truy cập phiên đã xác thực
~~~

Cách phòng vệ:

~~~mermaid
sequenceDiagram
    participant V as Nạn nhân
    participant S as Server

    V->>S: Đăng nhập với session ID cũ X
    S->>S: Xác minh credentials / MFA
    S->>S: Revoke X, sinh session ID mới Y
    S-->>V: Set-Cookie session=Y
    V->>S: Request tiếp theo với Y
    S-->>V: Xác định phiên mới hợp lệ
~~~

Nguyên tắc quan trọng:

- Rotate session ID sau khi đăng nhập thành công.
- Rotate khi nâng quyền hoặc hoàn thành step-up authentication.
- Vô hiệu hóa ID cũ để nó không còn truy cập session.
- Không cho client tự chọn session ID.
- Không chỉ rotate cookie phía browser mà bỏ session record cũ còn hiệu lực ở server.

## 7. Cấp session cookie với scope phù hợp

Session ID thường được gửi trong cookie. Với một ứng dụng HTTPS chỉ cần session trên một host, mẫu thường phù hợp là:

~~~http
Set-Cookie: __Host-session=OPAQUE_RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Ý nghĩa với session |
| --- | --- |
| `__Host-` | Browser hỗ trợ prefix yêu cầu Secure, Path=/ và không có Domain; giúp ràng buộc cookie với host. |
| `Secure` | Chỉ gửi cookie trên kết nối an toàn theo quy tắc browser. |
| `HttpOnly` | Không cho JavaScript đọc cookie qua document.cookie. |
| `Path=/` | Cookie phù hợp các request path trên host. |
| Không có `Domain` | Host-only cookie, không mở rộng tự động sang subdomain. |
| `SameSite=Lax` | Giảm gửi cookie trong nhiều ngữ cảnh cross-site, vẫn hỗ trợ một số điều hướng top-level. |

### 7.1. Secure

`Secure` yêu cầu browser chỉ gửi cookie qua kết nối an toàn theo quy tắc cookie. Không dùng cookie session nhạy cảm qua HTTP production. Cấu hình TLS và HSTS phù hợp; Secure không tự mã hóa dữ liệu trong server storage và không chống XSS.

### 7.2. HttpOnly

`HttpOnly` ngăn JavaScript truy cập session cookie qua các API như `document.cookie`. Nó làm giảm nguy cơ script đánh cắp trực tiếp cookie, nhưng XSS vẫn có thể gọi API trong phiên của người dùng vì browser tự đính kèm cookie phù hợp.

### 7.3. SameSite

- `Strict`: giới hạn cookie trong ngữ cảnh same-site chặt hơn, có thể ảnh hưởng link đi từ trang ngoài và SSO.
- `Lax`: thường là lựa chọn cân bằng cho session cookie web thông thường; một số điều hướng top-level cross-site với method an toàn vẫn gửi cookie.
- `None`: cho phép cookie trong ngữ cảnh cross-site nếu chính sách browser cho phép và phải kèm `Secure` trên browser hiện đại.

SameSite không đồng nghĩa same-origin. Hai subdomain có thể khác origin nhưng cùng site. Vì vậy SameSite giúp giảm CSRF nhưng không thay thế token hoặc kiểm tra backend trong mọi kiến trúc.

### 7.4. Domain và Path

Với session cookie, tránh `Domain=example.test` nếu không thật sự cần chia sẻ giữa subdomain. Cookie host-only giảm phạm vi nhận cookie. `Path=/` thường cần để session hoạt động trên toàn ứng dụng; Path không tạo ranh giới JavaScript hoặc authorization.

Cookie không được cách ly theo port. Hai ứng dụng cùng host nhưng khác port có thể liên quan đến cùng cookie nếu các điều kiện cookie khác phù hợp, dù chúng khác origin theo SOP.

## 8. Session lifetime: idle timeout và absolute timeout

Session không nên tồn tại vô hạn. Server thường quản lý ít nhất hai giới hạn:

- **Idle timeout:** thời gian tối đa không có hoạt động phù hợp trước khi session hết hiệu lực.
- **Absolute lifetime:** thời gian tối đa kể từ khi session được tạo hoặc xác thực, bất kể có hoạt động liên tục.

Ví dụ:

~~~text
createdAt       = 09:00
lastSeenAt      = 10:15
idleTimeout     = 30 phút
absoluteExpiry  = 17:00

Nếu không có hoạt động phù hợp sau 10:15,
session hết hạn theo idle timeout vào khoảng 10:45.
Nếu có hoạt động đều đặn, session vẫn hết hạn không muộn hơn 17:00.
~~~

Giá trị thời gian phải dựa trên mức nhạy cảm của ứng dụng, chính sách tổ chức và trải nghiệm người dùng. Tài khoản ngân hàng hoặc trang quản trị có thể cần thời gian ngắn hơn ứng dụng nội dung thông thường.

### 8.1. Browser cookie expiry không phải server session expiry

Cookie có thể là session cookie (không có Expires/Max-Age) hoặc persistent cookie. Nhưng browser đóng cửa sổ không đảm bảo server đã hủy session; browser có thể khôi phục session hoặc giữ cookie theo cài đặt.

Ngược lại, cookie có thể vẫn nằm trong browser sau khi server session đã hết hạn hoặc bị revoke. Khi request tới, server phải kiểm tra record và từ chối session không còn hiệu lực.

Do đó có hai thời điểm độc lập:

1. Cookie còn được browser lưu và gửi hay không.
2. Server có còn chấp nhận session ID đó hay không.

Server-side expiry và revoke mới là căn cứ quyết định session có hợp lệ.

### 8.2. Gia hạn idle timeout có kiểm soát

Mỗi request không nhất thiết phải cập nhật `lastSeenAt` theo cách ghi database quá thường xuyên. Có thể cập nhật theo ngưỡng, nhưng phải tránh race condition làm kéo dài phiên đã hết hạn hoặc bỏ qua absolute expiry.

Với thao tác nhạy cảm, kiểm tra lại thời gian xác thực gần nhất (reauthentication age) thay vì chỉ dựa vào session còn hiệu lực. Ví dụ đổi email, đổi mật khẩu, tạo API key hoặc xóa tài khoản có thể yêu cầu nhập lại mật khẩu/MFA.

## 9. Session rotation và thay đổi quyền

Rotate session ID không chỉ cần sau đăng nhập. Cân nhắc rotate khi:

- Người dùng hoàn thành MFA hoặc step-up authentication.
- Người dùng chuyển từ vai trò thường sang vai trò đặc quyền.
- Tài khoản thay đổi mật khẩu hoặc thông tin xác thực quan trọng.
- Server phát hiện dấu hiệu session bị lộ hoặc có rủi ro.
- Người dùng thực hiện hành động bảo mật yêu cầu phiên mới.

Khi rotate:

1. Tạo ID mới bằng CSPRNG.
2. Tạo hoặc cập nhật session record mới theo giao dịch an toàn.
3. Chuyển dữ liệu trạng thái hợp lệ sang record mới nếu cần.
4. Vô hiệu hóa ID cũ theo chính sách.
5. Gửi Set-Cookie với ID mới.
6. Đảm bảo request đồng thời không làm session cũ được tái kích hoạt.

### 9.1. Xử lý request đồng thời

Một browser có thể gửi nhiều request cùng lúc khi session đang rotate. Nếu một request cũ đến trễ, server không được vô tình tạo lại hoặc kéo dài session đã bị revoke.

Có thể dùng version/generation của session, trạng thái revoked, transaction hoặc quy trình chuyển tiếp ngắn hạn được thiết kế rõ. Không giữ session cũ hoạt động vô thời hạn chỉ để tránh lỗi giao diện.

Với ứng dụng có nhiều server instance, rotation và revoke cần nhất quán trên kho session dùng chung hoặc qua cơ chế đồng bộ đáng tin cậy.

## 10. Logout và revoke session

Logout không chỉ là xóa cookie ở browser. Server cần vô hiệu hóa session record:

~~~text
1. Nhận request logout hợp lệ.
2. Xác định session hiện tại.
3. Đánh dấu session revoked hoặc xóa record.
4. Gửi Set-Cookie cùng tên/scope với Max-Age=0.
5. Trả response không cache.
~~~

Ví dụ:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Nếu chỉ xóa cookie, một bản sao session ID đã bị đánh cắp vẫn có thể dùng được cho tới khi server hết hạn. Revoke server-side làm session ID không còn được chấp nhận.

Để xóa đúng cookie, cần cùng name và phạm vi Path/Domain tương ứng. Prefix `__Host-` yêu cầu không có Domain và Path=/.

### 10.1. Logout tất cả thiết bị

Một trang quản lý bảo mật có thể cho user xem và revoke các session khác. Server có thể lưu session theo user ID, thiết bị hoặc thời điểm đăng nhập, rồi:

- Revoke một session cụ thể.
- Revoke tất cả session ngoại trừ session hiện tại.
- Revoke tất cả session khi đổi mật khẩu hoặc phát hiện compromise.
- Thu hồi refresh token liên quan nếu kiến trúc có token riêng.

Không dựa vào tên thiết bị hoặc user-agent làm bằng chứng xác thực; chúng chỉ là metadata hỗ trợ hiển thị và điều tra.

## 11. CSRF và session creation

Cookie session thường được browser gửi tự động theo cookie policy. Điều này tạo rủi ro CSRF nếu server dựa vào cookie mà không kiểm tra ý định/nguồn request phù hợp.

Một số endpoint nhạy cảm:

- Đăng nhập (login CSRF).
- Đổi email hoặc mật khẩu.
- Thay đổi địa chỉ giao hàng.
- Tạo giao dịch hoặc đặt hàng.
- Liên kết tài khoản hoặc bật/tắt MFA.

### 11.1. Login CSRF

CSRF không chỉ xảy ra sau khi user đã đăng nhập. Một trang ngoài có thể cố khiến browser đăng nhập vào tài khoản do kẻ tấn công kiểm soát, khiến nạn nhân vô tình sử dụng tài khoản đó và nhập dữ liệu cá nhân vào sai nơi.

Phòng vệ cho login flow có thể gồm:

- CSRF token hoặc cơ chế chống login CSRF phù hợp.
- Kiểm tra Origin/Referer theo policy và Fetch Metadata khi phù hợp.
- Không tự động chấp nhận thông tin xác thực hoặc trạng thái do trang ngoài điều khiển.
- Rotate session sau khi login thành công.
- Thiết kế xác nhận tài khoản rõ ràng, đặc biệt khi liên kết danh tính.

### 11.2. Session ID không phải CSRF token

Session ID chứng minh browser đang mang một bearer secret để server tra cứu phiên. CSRF token là một cơ chế khác nhằm chứng minh request đến từ luồng ứng dụng mong muốn trong mô hình đe dọa phù hợp.

Không dùng chính session ID làm CSRF token có thể đọc được từ DOM. CSRF token nên được ràng buộc với session hoặc được thiết kế theo pattern đã kiểm chứng; server phải xác minh trước khi xử lý hành động thay đổi trạng thái.

SameSite là một lớp giảm rủi ro, nhưng không thay thế toàn bộ CSRF defense, nhất là khi có subdomain same-site, tích hợp legacy hoặc các luồng phức tạp.

## 12. XSS và nguy cơ chiếm session

Nếu session cookie không có HttpOnly, XSS có thể đọc trực tiếp cookie qua `document.cookie` trong những điều kiện phù hợp. Nếu có HttpOnly, script độc vẫn có thể thực hiện request trong phiên người dùng, đọc dữ liệu mà trang có quyền đọc và thao tác giao diện.

Các biện pháp:

- Dùng HttpOnly cho session cookie nếu JavaScript không cần đọc.
- Render dữ liệu bằng DOM API an toàn; tránh sink HTML không tin cậy.
- Áp dụng CSP với nonce/hash và nguồn script tối thiểu.
- Cân nhắc Trusted Types cho DOM injection sinks trên browser hỗ trợ.
- Hạn chế script bên thứ ba và dùng iframe cách ly cho widget ít tin cậy.
- Đặt session scope hẹp, expiry phù hợp và revoke được.
- Kiểm tra quyền backend cho từng thao tác, không tin frontend.

HttpOnly giảm một đường lấy cắp cookie; **nó không ngăn XSS hành động thay người dùng**. Cần giảm khả năng XSS và giới hạn quyền của session.

## 13. CORS và browser session

Nếu frontend và API khác origin, browser có thể cần gửi cookie cross-origin bằng:

~~~js
const response = await fetch("https://api.example.test/profile", {
  credentials: "include"
});
~~~

Để JavaScript đọc response credentialed, API cần cấu hình origin cụ thể và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng wildcard `Access-Control-Allow-Origin: *` với credentialed response. Cookie vẫn chịu Domain/host, Path, Secure, SameSite và chính sách third-party cookie của browser.

CORS chỉ kiểm soát quyền JavaScript đọc response cross-origin. Nó không xác thực user, không thay authorization và không tự ngăn CSRF.

## 14. Session store trong hệ thống nhiều instance

Ứng dụng production có thể chạy trên nhiều server instance:

~~~mermaid
flowchart LR
    B["Browser<br/>session cookie"] --> LB["Load balancer"]
    LB --> A["App instance A"]
    LB --> C["App instance B"]
    A --> R["Shared session store"]
    C --> R
    R --> DB["Session records"]
~~~

Nếu session chỉ lưu trong memory của instance A, request tiếp theo tới instance B có thể không tìm thấy session. Có một số lựa chọn:

| Thiết kế | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| In-memory session một instance | Đơn giản cho local/dev | Mất session khi restart; không chia sẻ giữa instance. |
| Sticky session | Giảm nhu cầu chia sẻ ngay lập tức | Phụ thuộc load balancer; failover và scale phức tạp. |
| Shared store như Redis/database | Các instance có thể tra cứu cùng session | Cần bảo vệ, availability, latency và xử lý consistency. |
| Stateless token | Không cần tra cứu record cho mỗi request theo cách truyền thống | Khó revoke tức thời; cần quản lý expiry, key rotation, replay và claims. |

Với server-side session, shared store thường giúp revoke và rotation nhất quán. Kho session là dữ liệu nhạy cảm: giới hạn network access, credentials, quyền đọc/ghi, encryption-at-rest khi phù hợp, backup và audit. Không ghi session ID gốc vào log.

### 14.1. Atomicity khi tạo và rotate

Session creation có thể gồm nhiều thao tác: tạo record, revoke ID cũ, cập nhật trạng thái user và gửi Set-Cookie. Cần xác định thứ tự và cơ chế transaction/idempotency để tránh:

- Cookie mới được gửi nhưng record không được lưu.
- Record mới tồn tại nhưng browser không nhận cookie.
- ID cũ vẫn hợp lệ sau rotation.
- Hai request đồng thời tạo hai session không mong muốn.
- Retry của login tạo nhiều session ngoài chính sách.

Thiết kế cụ thể tùy store và framework. Ưu tiên thao tác nguyên tử hoặc quy trình có thể phục hồi rõ ràng; không để lỗi mạng làm session cũ tự sống lại.

## 15. Bảo vệ session metadata và logging

Log cần giúp điều tra mà không biến thành nơi lưu bearer secret.

Không log:

- Giá trị session cookie hoặc session ID nguyên gốc.
- Password, OTP, recovery code, CSRF token hoặc bearer token.
- Request header Cookie đầy đủ.
- URL chứa secret trong query/fragment nếu ứng dụng vô tình sử dụng.

Có thể log:

- Một định danh correlation riêng không phải session secret.
- User ID nội bộ sau khi xác thực, theo chính sách bảo vệ dữ liệu.
- Thời điểm tạo, rotate, revoke và lý do.
- Auth level (password, MFA, step-up) mà không ghi OTP.
- Kết quả đăng nhập thành công/thất bại và tín hiệu bảo mật phù hợp.
- Metadata thiết bị/UA ở mức cần thiết, tránh coi chúng là yếu tố xác thực.

Nếu cần liên kết sự kiện với một session mà không lộ ID, có thể dùng fingerprint/hash một chiều có khóa riêng cho mục đích audit và rotation. Không tái sử dụng hash đó như credential.

## 16. Thực hành A — Quan sát session creation trong DevTools

Thực hiện trong ứng dụng local/staging do bạn kiểm soát, dùng tài khoản test và không ghi thông tin xác thực thật.

1. Mở DevTools → **Network** và bật Preserve log.
2. Truy cập trang đăng nhập.
3. Đăng nhập thành công bằng tài khoản test.
4. Chọn response của endpoint login, xem **Response Headers**.
5. Tìm `Set-Cookie` và ghi nhận các thuộc tính: Secure, HttpOnly, SameSite, Path, Domain hoặc prefix.
6. Mở tab **Application/Storage → Cookies** để xem cookie đã được browser lưu.
7. Tải trang tài khoản hoặc gọi endpoint yêu cầu đăng nhập; xem request có header Cookie phù hợp.
8. Trong tab Network, xác minh session ID không xuất hiện trong URL hoặc query.

**Kết luận cần chứng minh:** Server cấp cookie sau khi xác thực; browser lưu và gửi cookie theo scope; server vẫn phải tra cứu session record.

## 17. Thực hành B — Xác minh rotate session sau đăng nhập

Trong môi trường test, quan sát cookie trước và sau login:

1. Truy cập trang trước đăng nhập; nếu ứng dụng tạo anonymous session, ghi nhận ID demo bằng DevTools (không copy secret thật vào báo cáo).
2. Đăng nhập thành công.
3. Quan sát response `Set-Cookie` mới.
4. So sánh giá trị session ID bằng cách kiểm tra cục bộ an toàn, không đưa giá trị vào log.
5. Thử dùng session ID cũ trong môi trường test sau khi server đã revoke nó; request cần bị từ chối hoặc yêu cầu xác thực lại.

**Kết luận cần chứng minh:** Session ID trước xác thực không tiếp tục làm credential sau khi đăng nhập. Nếu ứng dụng không tạo session mới, cần xem xét nguy cơ session fixation.

## 18. Thực hành C — Kiểm tra HttpOnly, Secure và SameSite

Với cookie test:

~~~http
Set-Cookie: __Host-session=demo-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Kiểm tra:

- `document.cookie` không hiển thị cookie HttpOnly.
- Request phù hợp vẫn mang cookie trong Network.
- Cookie Secure chỉ được gửi theo điều kiện transport an toàn của browser; localhost có thể có ngoại lệ cho phát triển.
- Thử điều hướng từ site test khác và quan sát SameSite, nhưng không gửi request thay đổi dữ liệu thật.
- Kiểm tra cookie có Domain không; prefix `__Host-` yêu cầu không có Domain, Path=/ và Secure trong browser hỗ trợ.

Ghi lại browser, phiên bản, scheme và top-level site vì chính sách cookie có thể khác nhau theo môi trường.

## 19. Thực hành D — Logout và revoke server-side

Trong ứng dụng test:

1. Đăng nhập và xác nhận endpoint tài khoản hoạt động.
2. Thực hiện logout.
3. Kiểm tra response xóa cookie với đúng Path/Domain và Max-Age=0 hoặc Expires trong quá khứ.
4. Dùng lại cookie test cũ trong môi trường do bạn kiểm soát.
5. Xác minh backend từ chối session cũ vì record đã revoke hoặc hết hạn, kể cả khi client cố gửi lại cookie.

**Kết luận cần chứng minh:** Xóa cookie phía browser là chưa đủ; server-side revoke mới làm session ID mất hiệu lực.

## 20. Checklist review session creation

- [ ] Chỉ tạo authenticated session sau khi server xác minh credentials và các bước MFA/policy cần thiết.
- [ ] Dùng CSPRNG sinh session ID có entropy cao; không dùng timestamp, counter hoặc dữ liệu user.
- [ ] Session ID là opaque bearer secret, không chứa role/user profile và không xuất hiện trong URL.
- [ ] Server lưu session record với user, createdAt, lastSeenAt, expiry, auth level và trạng thái revoke phù hợp.
- [ ] Cân nhắc lưu hash của session ID ở kho session để giảm tác động khi kho bị đọc trái phép.
- [ ] Rotate ID sau login, MFA, step-up hoặc thay đổi quyền quan trọng.
- [ ] Revoke ID cũ; không để session fixation hoặc replay.
- [ ] Dùng cookie scope nhỏ nhất cần thiết; cân nhắc __Host-, Secure, HttpOnly, SameSite và Path=/.
- [ ] Không giả định cookie được tách theo port hoặc Path là sandbox.
- [ ] Đặt idle timeout và absolute timeout theo mức nhạy cảm.
- [ ] Kiểm tra server-side expiry/revoke độc lập với cookie còn ở browser.
- [ ] Logout phải revoke server-side và xóa cookie đúng scope.
- [ ] Có cơ chế revoke phiên khác khi đổi mật khẩu hoặc phát hiện compromise nếu nghiệp vụ cần.
- [ ] Dùng CSRF token/kiểm tra nguồn request cho hành động thay đổi trạng thái.
- [ ] Chống XSS; HttpOnly không ngăn script độc thao tác trong session.
- [ ] CORS credentialed chỉ cho origin tin cậy cụ thể; backend vẫn xác thực và phân quyền.
- [ ] Session store có kiểm soát truy cập, availability, consistency và logging an toàn.
- [ ] Không log session ID, cookie, OTP hoặc token bí mật.

## 21. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Browser tự tạo session an toàn chỉ bằng cookie.” | **Sai** | Server phải sinh ID, lưu record và xác minh. |
| “Session ID có thể là user ID cộng timestamp.” | **Sai** | Dễ đoán và tiết lộ thông tin. |
| “Chỉ cần đổi cookie sau login, không cần revoke ID cũ.” | **Sai** | ID cũ có thể vẫn hợp lệ ở server. |
| “Cookie hết hạn thì session server tự hết hạn.” | **Sai** | Cookie expiry và server session expiry độc lập. |
| “Đóng browser luôn xóa session.” | **Sai** | Browser có thể khôi phục session; server vẫn phải quản lý expiry. |
| “HttpOnly ngăn mọi tác động của XSS.” | **Sai** | XSS vẫn có thể gọi API trong phiên. |
| “SameSite thay thế CSRF token trong mọi trường hợp.” | **Sai** | Cần xét site context, subdomain và endpoint. |
| “Cookie session nên đặt trong URL để tránh CORS.” | **Sai** | URL dễ rò rỉ qua history, log, referrer và analytics. |
| “CORS thành công chứng minh user có quyền.” | **Sai** | CORS là chính sách đọc response; authorization thuộc server. |
| “Session store local memory đủ cho nhiều instance.” | **Sai** | Instance khác có thể không tìm thấy record; cần chia sẻ hoặc thiết kế khác. |
| “Logout chỉ cần xóa cookie.” | **Sai** | Phải revoke session server-side để ID cũ không còn dùng được. |
| “Rotate session chỉ cần lúc đăng nhập.” | **Chưa đủ** | Cần đánh giá MFA, step-up và thay đổi quyền. |

## 22. Tổng kết

Session creation là quá trình server tạo một định danh phiên khó đoán, gắn nó với trạng thái đã xác minh và cấp cho browser qua cơ chế lưu trữ phù hợp. Một thiết kế an toàn không dừng ở việc phát Set-Cookie: nó phải quản lý cả **ID, session record, rotation, expiry, revoke, cookie scope và quyền của từng request**.

Ba nguyên tắc cốt lõi:

1. **Tạo ID mới và ngẫu nhiên:** dùng CSPRNG, entropy cao, opaque; rotate sau đăng nhập và nâng quyền, revoke ID cũ để chống session fixation.
2. **Cấp cookie đúng scope:** ưu tiên host-only khi phù hợp, Secure, HttpOnly, SameSite và prefix __Host-; không đặt session secret trong URL.
3. **Quản lý phiên ở server:** kiểm tra expiry, auth level, revoke, CSRF và authorization cho mọi thao tác nhạy cảm; cookie còn tồn tại không đồng nghĩa session còn hợp lệ.

Khi review một luồng đăng nhập, hãy hỏi: **session ID được sinh ở đâu, khi nào được cấp, record được lưu và thu hồi thế nào, ID cũ còn hiệu lực không, cookie được gửi trong ngữ cảnh nào, và backend kiểm tra điều gì trước mỗi hành động?** Trả lời rõ những câu hỏi này giúp tạo browser session có vòng đời kiểm soát được thay vì chỉ phát một cookie và hy vọng browser tự bảo vệ ứng dụng.
