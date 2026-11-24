# Secure flag

## 1. Secure flag là gì?

**Secure** là thuộc tính của cookie yêu cầu trình duyệt chỉ gửi cookie qua một kênh được xem là an toàn, thông thường là kết nối HTTPS được bảo vệ bằng TLS. Khi server phát hành cookie có thuộc tính này, trình duyệt không nên gửi cookie đó trong request HTTP thông thường không được bảo vệ.

Ví dụ:

~~~http
Set-Cookie: session_id=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong ví dụ, server tạo cookie phiên và yêu cầu trình duyệt chỉ gửi nó qua kênh an toàn. Giá trị cookie là một mã phiên ngẫu nhiên, không phải dữ liệu danh tính hoặc quyền truy cập nên được nhúng trực tiếp vào URL.

Secure giúp giảm nguy cơ kẻ nghe lén mạng đọc được cookie khi người dùng truy cập qua HTTP. Tuy nhiên, **Secure không tự mã hóa cookie ở nơi lưu trữ, không bảo vệ endpoint bị chiếm và không thay thế các thuộc tính HttpOnly, SameSite hoặc biện pháp chống CSRF**.

| Thuộc tính | Bảo vệ chính | Không tự giải quyết |
| --- | --- | --- |
| `Secure` | Chỉ gửi cookie qua kênh an toàn theo quy tắc của trình duyệt. | XSS, CSRF, session fixation, cookie bị lấy từ máy đã nhiễm mã độc. |
| `HttpOnly` | Ngăn JavaScript thông thường đọc cookie qua API như `document.cookie`. | JavaScript độc hại vẫn có thể thực hiện request thay người dùng trong phiên. |
| `SameSite` | Hạn chế gửi cookie trong một số ngữ cảnh request cross-site. | Mọi dạng CSRF, XSS hoặc tấn công cùng site. |
| `Path` / `Domain` | Xác định phạm vi URL/host mà cookie được gửi tới. | Cô lập bảo mật mạnh giữa các ứng dụng cùng host. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, Secure flag là một kiểm soát quan trọng cho cookie phiên và các cookie nhạy cảm trong trình duyệt. Nó bảo vệ một đoạn của đường truyền credential/session; hệ thống vẫn phải bảo vệ đăng nhập, session, authorization và khôi phục tài khoản.

## 2. Trình duyệt xử lý cookie Secure như thế nào?

Khi nhận header `Set-Cookie`, trình duyệt lưu cookie cùng các thuộc tính. Ở request sau, trình duyệt xét host, path, thời hạn, ngữ cảnh và thuộc tính cookie trước khi quyết định có đính kèm cookie hay không.

~~~mermaid
flowchart TD
    A["Server gửi Set-Cookie có Secure"] --> B["Browser lưu cookie và thuộc tính"]
    B --> C["Trang tạo request"]
    C --> D{"Request đi qua kênh an toàn?"}
    D -->|Có, ví dụ HTTPS| E["Xét thêm host, path, expiry, SameSite..."]
    D -->|Không, HTTP thông thường| F["Không gửi cookie Secure"]
    E --> G{"Các điều kiện gửi cookie hợp lệ?"}
    G -->|Có| H["Đính kèm Cookie header"]
    G -->|Không| I["Không đính kèm cookie"]
~~~

Ví dụ cùng một host:

~~~text
https://app.example.test/account
  -> Trình duyệt có thể gửi cookie Secure phù hợp.

http://app.example.test/account
  -> Trình duyệt không gửi cookie Secure trong request HTTP thông thường.
~~~

Quyết định gửi cookie thuộc về trình duyệt. Server không nên dựa vào việc client tự khai một header như `X-Forwarded-Proto: https` để kết luận cookie đã được truyền an toàn; header đó chỉ đáng tin nếu đến từ proxy được cấu hình và xác thực đúng.

Một số trình duyệt có xử lý ngoại lệ cho địa chỉ localhost trong môi trường phát triển. Không nên dựa vào ngoại lệ này cho production hoặc coi mọi hostname nội bộ đều là secure context.

## 3. Secure bảo vệ điều gì trên đường truyền?

Nếu cookie phiên được gửi qua HTTP không mã hóa, người có khả năng quan sát lưu lượng trên mạng có thể đọc header `Cookie` và lấy mã phiên. Với bearer session cookie, người có mã phiên thường có thể sử dụng nó để hành động dưới danh nghĩa phiên đó cho đến khi hết hạn hoặc bị thu hồi.

HTTPS/TLS cung cấp bảo vệ cho kết nối giữa các đầu cuối TLS:

- **Confidentiality:** bên nghe lén mạng không dễ đọc nội dung request/response, bao gồm cookie.
- **Integrity:** dữ liệu trên kết nối được bảo vệ trước việc sửa đổi trái phép.
- **Server authentication:** client có cơ sở xác minh server thông qua chứng chỉ TLS và tên máy chủ.

Secure flag khiến trình duyệt giới hạn việc gửi cookie vào kênh an toàn. Nó không tự bật HTTPS cho website, không tự cấp chứng chỉ TLS và không tự chuyển HTTP sang HTTPS.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant N as Mạng
    participant S as HTTPS server
    B->>S: TLS handshake, xác minh server
    S-->>B: Kết nối TLS được thiết lập
    B->>N: HTTPS request + Cookie header
    Note over N: Nội dung được TLS bảo vệ trên đường truyền
    N->>S: Request đã được TLS giải mã tại endpoint
    S-->>B: HTTPS response
~~~

Nếu người dùng truy cập website qua HTTP và cookie không có Secure, cookie có thể bị gửi trong request không mã hóa. Nếu cookie có Secure, trình duyệt không gửi cookie đó qua HTTP thông thường; nhưng người dùng vẫn có thể gặp rủi ro từ nội dung HTTP khác, chuyển hướng downgrade, hoặc ứng dụng tạo một cookie khác không có Secure.

## 4. Secure không thay thế HttpOnly và SameSite

Ba thuộc tính thường được dùng cùng nhau vì chúng giải quyết các mối đe dọa khác nhau.

### 4.1. Secure và HttpOnly

Secure giới hạn kênh truyền. HttpOnly giới hạn việc truy cập cookie qua API JavaScript trong trình duyệt.

Nếu cookie chỉ có Secure nhưng thiếu HttpOnly, JavaScript chạy trong origin có thể đọc cookie thông qua các API được phép và gửi giá trị ra ngoài. Nếu cookie có cả Secure và HttpOnly, script thông thường không đọc trực tiếp được giá trị cookie, nhưng XSS vẫn có thể thực hiện request cùng origin và sử dụng phiên của nạn nhân.

Vì vậy, cookie phiên web thường cần cả hai:

~~~http
Set-Cookie: __Host-SessionID=random-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

### 4.2. Secure và SameSite

SameSite kiểm soát việc trình duyệt gửi cookie trong một số ngữ cảnh cross-site. Nó giúp giảm rủi ro CSRF, nhưng không thay thế hoàn toàn token chống CSRF hoặc kiểm tra Origin/Referer cho các thao tác nhạy cảm.

Một số chế độ phổ biến:

- `SameSite=Strict`: hạn chế gửi cookie trong các điều hướng/request khởi phát từ site khác; có thể ảnh hưởng trải nghiệm khi người dùng đi từ liên kết bên ngoài.
- `SameSite=Lax`: cho phép một số điều hướng cấp cao an toàn từ site khác nhưng hạn chế nhiều request cross-site khác; thường là lựa chọn mặc định thực tế cho session web.
- `SameSite=None`: cho phép gửi trong ngữ cảnh cross-site theo quy tắc trình duyệt và phải đi cùng `Secure` trong các trình duyệt hiện đại.

Secure không đồng nghĩa SameSite. Một cookie có Secure vẫn có thể được gửi trong request cross-site nếu các quy tắc SameSite và cookie context cho phép. Ngược lại, SameSite không mã hóa cookie trên đường truyền HTTP.

## 5. Cấu hình cookie phiên an toàn

Với ứng dụng web thông thường, cookie phiên nên được cấu hình tập trung ở server/framework và dùng một giá trị phiên ngẫu nhiên, khó đoán. Ví dụ:

~~~http
Set-Cookie: __Host-SessionID=7f8c...random...; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
~~~

Ý nghĩa:

- `__Host-SessionID`: tên cookie dùng prefix `__Host-` với các điều kiện tương ứng của trình duyệt hỗ trợ prefix.
- `Path=/`: cookie có phạm vi path toàn host.
- `Secure`: chỉ gửi qua kênh an toàn.
- `HttpOnly`: không cho JavaScript thông thường đọc giá trị cookie.
- `SameSite=Lax`: hạn chế nhiều request cross-site.
- `Max-Age=1800`: cookie có thời hạn lưu tối đa 30 phút kể từ lúc nhận, theo quy tắc cookie.

Server vẫn nên quản lý thời hạn idle/absolute của session phía server. Hết hạn cookie ở browser không tự xóa bản ghi session server; ngược lại, session server bị thu hồi thì cookie còn lưu cũng không được chấp nhận.

### 5.1. Vì sao dùng prefix __Host-?

Các trình duyệt hỗ trợ cookie prefixes có thể áp dụng điều kiện bổ sung cho tên cookie:

| Prefix | Điều kiện chính |
| --- | --- |
| `__Secure-` | Cookie phải có thuộc tính Secure và được đặt từ secure origin theo quy tắc trình duyệt. |
| `__Host-` | Phải có Secure, Path=/ và không được có thuộc tính Domain; cookie được giới hạn ở host đã đặt nó. |

`__Host-SessionID` phù hợp với session cookie cần host-only scope. Bỏ thuộc tính Domain giúp cookie không được chia sẻ tới mọi subdomain của domain cha. Prefix được trình duyệt hỗ trợ sẽ giúp từ chối một số cấu hình sai, nhưng server vẫn cần phát hành cookie đúng và kiểm tra tương thích trình duyệt mục tiêu.

Nếu ứng dụng cần chia sẻ cookie giữa các subdomain, `__Host-` không phù hợp vì yêu cầu không có Domain. Cần xem lại kiến trúc xác thực giữa các subdomain thay vì mở rộng Domain chỉ vì tiện lợi.

### 5.2. Tránh cookie phiên trùng tên

Cookie có thể tồn tại đồng thời với cùng tên nhưng khác Domain hoặc Path. Server không nên dựa vào thứ tự trong header `Cookie` để đoán cookie nào là phiên đúng. Tránh phát hành nhiều cookie phiên trùng tên ở các path/domain khác nhau; khi thay đổi cấu hình, xóa cookie cũ bằng đúng phạm vi Domain/Path đã dùng.

## 6. Secure flag và phạm vi Domain/Path

Secure chỉ quyết định việc gửi cookie qua kênh an toàn. Nó không giới hạn cookie vào một port cụ thể và không tự tạo ranh giới bảo mật giữa các ứng dụng chạy cùng host.

Ví dụ:

~~~http
Set-Cookie: session=abc; Domain=example.test; Path=/; Secure; HttpOnly
~~~

Cookie có Domain rộng có thể được gửi tới host phù hợp trong phạm vi domain đó, bao gồm subdomain theo quy tắc cookie. Nếu một subdomain yếu hoặc bị chiếm, phạm vi cookie rộng có thể làm tăng rủi ro. Với session nhạy cảm, thường nên bỏ Domain để tạo host-only cookie; prefix `__Host-` hỗ trợ ràng buộc này.

Path giúp trình duyệt quyết định request path nào phù hợp để gửi cookie, nhưng **không phải cơ chế cô lập bảo mật mạnh** giữa các ứng dụng cùng host. Các ứng dụng cùng host vẫn chia sẻ origin và có thể có các tương tác bảo mật khác.

## 7. HTTP downgrade và HSTS

Secure flag không tự ngăn người dùng lần đầu truy cập website qua HTTP. Attacker trên mạng có thể cố gắng khiến trình duyệt truy cập HTTP hoặc chặn chuyển hướng downgrade trong một số tình huống nếu website chưa được bảo vệ đúng.

**HTTP Strict Transport Security (HSTS)** cho phép website thông báo rằng trình duyệt nên chỉ truy cập domain qua HTTPS trong thời gian chính sách có hiệu lực.

Ví dụ response header:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

- `max-age` xác định thời gian chính sách được lưu trong trình duyệt.
- `includeSubDomains` mở rộng chính sách tới subdomain; chỉ bật khi toàn bộ subdomain đã sẵn sàng HTTPS.
- `preload` là cơ chế đăng ký domain vào danh sách preload của trình duyệt theo quy trình riêng; chỉ thêm khi đáp ứng điều kiện và có kế hoạch vận hành dài hạn.

HSTS và Secure cookie bổ sung cho nhau:

| Kiểm soát | Vai trò |
| --- | --- |
| HTTPS/TLS | Bảo vệ kết nối và xác thực server. |
| Secure cookie | Không gửi cookie qua HTTP thông thường. |
| HSTS | Hướng trình duyệt chỉ truy cập domain qua HTTPS sau khi nhận chính sách hoặc có trong preload list. |

HSTS header phải được gửi qua HTTPS. Nếu cấu hình `includeSubDomains` khi một subdomain còn dùng HTTP, ứng dụng đó có thể bị lỗi truy cập. Không dùng HSTS thay cho Secure flag; vẫn cần đặt Secure trên từng cookie nhạy cảm.

## 8. TLS termination và reverse proxy

Trong nhiều hệ thống, TLS kết thúc tại load balancer hoặc reverse proxy, sau đó proxy chuyển request đến application server. Ứng dụng có thể nhìn thấy kết nối nội bộ là HTTP dù trình duyệt đã kết nối HTTPS với proxy.

Điều này có thể khiến framework tự động phát hành cookie thiếu Secure nếu nó dựa vào scheme mà backend quan sát. Cấu hình sai cũng có thể khiến ứng dụng tin header `X-Forwarded-Proto` do client bên ngoài tự gửi.

~~~mermaid
flowchart LR
    B["Browser"] -->|HTTPS + Secure cookie| P["Trusted reverse proxy / TLS terminator"]
    P -->|HTTP nội bộ hoặc TLS nội bộ| A["Application server"]
    A -->|Set-Cookie có Secure| P
    P -->|HTTPS response| B
~~~

Các nguyên tắc:

1. Cấu hình proxy là thành phần tin cậy và chỉ chấp nhận forwarded headers từ proxy được chỉ định.
2. Proxy phải xóa hoặc ghi đè các forwarded header do client tự gửi trước khi thêm giá trị của nó.
3. Cấu hình framework để nhận biết đúng scheme bên ngoài qua chuỗi proxy tin cậy; không bật trust proxy cho mọi nguồn.
4. Phát hành Secure cookie rõ ràng trong production, không chỉ phụ thuộc vào việc backend thấy request là HTTPS.
5. Bảo vệ kết nối proxy → application; nếu đi qua mạng không tin cậy, dùng TLS nội bộ hoặc cơ chế bảo vệ tương ứng.
6. Kiểm thử response Set-Cookie tại điểm người dùng nhận, không chỉ kiểm tra cấu hình nội bộ của application.

Secure flag chỉ điều khiển hành vi trình duyệt tới endpoint HTTPS. Nó không tự mã hóa đoạn truyền từ TLS terminator đến application server.

## 9. Cookie Secure trong môi trường phát triển và production

Một lỗi thường gặp là dùng chung cấu hình cookie giữa localhost, staging và production. Trình duyệt có một số ngoại lệ phục vụ localhost, nhưng hành vi có thể khác giữa browser và môi trường. Cần đặt cấu hình theo môi trường rõ ràng.

| Môi trường | Cách xử lý |
| --- | --- |
| Local development | Ưu tiên chạy HTTPS local nếu có thể; nếu dùng ngoại lệ localhost, chỉ áp dụng cho phát triển và kiểm thử riêng. |
| Staging | Dùng HTTPS thực tế và cấu hình Secure giống production để phát hiện lỗi sớm. |
| Production | Bắt buộc HTTPS cho toàn bộ luồng đăng nhập/session; phát hành cookie nhạy cảm với Secure. |
| Internal service | Xác định TLS boundary; không mặc định mạng nội bộ luôn đáng tin hoặc không thể bị nghe lén. |

Không nên viết logic kiểu “nếu không thấy HTTPS thì bỏ Secure” dựa trên header không đáng tin. Nếu ứng dụng production nhận request qua proxy, hãy cấu hình đúng proxy trust và vẫn giữ Secure cho cookie production.

## 10. Các giới hạn và mối đe dọa Secure không giải quyết

| Mối đe dọa | Secure có giúp không? | Kiểm soát bổ sung |
| --- | --- | --- |
| Nghe lén cookie trên HTTP | Có, trình duyệt không gửi cookie Secure qua HTTP thông thường. | HTTPS toàn site, HSTS và TLS đúng cấu hình. |
| XSS đọc cookie | Không tự ngăn. | HttpOnly, CSP, output encoding, kiểm soát script và dependency. |
| XSS dùng phiên thay người dùng | Không. | Giảm XSS, step-up cho thao tác nhạy cảm, giới hạn quyền và giám sát. |
| CSRF | Không tự ngăn. | SameSite, CSRF token, kiểm tra Origin/Referer và thiết kế request. |
| Session fixation | Không. | Tạo session ID mới sau đăng nhập và thay đổi mức quyền. |
| Cookie bị lấy từ endpoint/máy nhiễm mã độc | Không. | Bảo vệ thiết bị, runtime, browser profile và quy trình revoke session. |
| Cookie bị lộ trong log/backup | Không. | Redaction, kiểm soát log, mã hóa backup và giới hạn lưu giữ. |
| Cookie injection từ subdomain | Secure đơn lẻ không giải quyết mọi trường hợp. | Host-only cookie, prefix __Host-, quản lý subdomain và TLS/HSTS. |
| Token/session bị replay sau khi đánh cắp | Không. | Session expiry/revocation, sender-constrained token khi phù hợp, phát hiện bất thường. |

Một lưu ý quan trọng: thuộc tính Secure bảo vệ tính bí mật của cookie trên kênh không an toàn, nhưng bản thân nó không cung cấp đầy đủ tính toàn vẹn cookie trước mọi attacker chủ động trên mạng. Các cơ chế cookie prefix như `__Host-` giúp giảm một số trường hợp cookie injection từ kênh hoặc host không phù hợp trên trình duyệt hỗ trợ. Không nên coi Secure đơn lẻ là giải pháp hoàn chỉnh cho cookie tossing hoặc mọi dạng cookie integrity attack.

## 11. Ví dụ cấu hình server

Ví dụ Express minh họa cookie session:

~~~ts
import express from "express";
import session from "express-session";

const app = express();

app.set("trust proxy", 1); // Chỉ đúng nếu có đúng một proxy tin cậy phía trước.

app.use(session({
  name: "__Host-SessionID",
  secret: process.env.SESSION_SIGNING_SECRET!,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: true,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 60 * 1000
    // Không đặt Domain để đáp ứng prefix __Host-.
  }
}));
~~~

Đây là ví dụ minh họa, cần dùng session store bền vững phù hợp production thay cho MemoryStore mặc định của một số middleware. Cấu hình `trust proxy` phải khớp topology thật; con số 1 chỉ phù hợp khi có đúng một proxy tin cậy. Nếu có nhiều tầng, cấu hình trust theo địa chỉ/range hoặc topology được kiểm soát, không tin mọi forwarded header.

Ví dụ response mong đợi:

~~~http
Set-Cookie: __Host-SessionID=<opaque-session-id>; Path=/; Expires=<date>; HttpOnly; Secure; SameSite=Lax
~~~

Hãy kiểm tra header thực tế qua HTTPS ở môi trường staging/production. Đảm bảo không có cookie cùng tên được phát hành thiếu Secure hoặc có Domain/Path xung đột.

## 12. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cookie session thiếu Secure | Có thể bị gửi qua HTTP thông thường và lộ trên mạng. | Bật Secure cho mọi cookie phiên/credential nhạy cảm. |
| Chỉ dùng Secure mà bỏ HttpOnly | JavaScript có thể đọc cookie nếu có XSS. | Thêm HttpOnly cho cookie không cần truy cập từ script. |
| Nghĩ Secure ngăn CSRF | Cookie vẫn tự động được gửi trong một số request cross-site. | Dùng SameSite, CSRF token và kiểm tra origin. |
| Bật Secure chỉ khi backend thấy HTTPS | TLS termination khiến backend nhìn thấy HTTP và phát hành cookie thiếu Secure. | Cấu hình proxy trust đúng và Secure rõ ràng ở production. |
| Tin mọi X-Forwarded-Proto từ client | Attacker có thể ảnh hưởng logic phát hiện scheme. | Chỉ tin proxy được cấu hình; proxy ghi đè header đầu vào. |
| Đặt Domain quá rộng | Cookie có thể được gửi tới nhiều subdomain. | Dùng host-only cookie; cân nhắc prefix __Host-. |
| Dùng Path như ranh giới bảo mật | Ứng dụng cùng host có thể không được cô lập như mong đợi. | Tách origin/host khi cần ranh giới mạnh. |
| Dùng SameSite=None nhưng thiếu Secure | Browser hiện đại có thể từ chối cookie. | Chỉ dùng None khi cần cross-site và luôn kèm Secure. |
| Chỉ chuyển hướng HTTP sang HTTPS nhưng không dùng HSTS | Downgrade vẫn có thể xảy ra trước khi browser nhận chính sách. | Cấu hình HSTS sau khi HTTPS đã sẵn sàng. |
| Cho rằng Secure mã hóa cookie trong database | Cookie vẫn có thể lộ từ log, storage hoặc endpoint. | Bảo vệ lưu trữ, log, endpoint và session lifecycle. |

## 13. Checklist triển khai Secure flag

Trước khi đưa cookie phiên lên production, hãy kiểm tra:

1. Cookie nào chứa session ID, refresh token, recovery token hoặc dữ liệu nhạy cảm?
2. Tất cả cookie nhạy cảm có thuộc tính Secure không?
3. Toàn bộ luồng đăng nhập và sử dụng phiên có HTTPS, chứng chỉ hợp lệ và cấu hình TLS phù hợp không?
4. Có HSTS và kế hoạch xử lý subdomain trước khi bật includeSubDomains/preload không?
5. Cookie phiên có HttpOnly và SameSite phù hợp không?
6. Có cân nhắc prefix __Host- để tạo host-only cookie với Path=/ và không Domain không?
7. Proxy/TLS termination có được cấu hình tin cậy đúng; forwarded headers từ client có bị ghi đè không?
8. Ứng dụng có tránh phát hành cookie trùng tên với Domain/Path khác nhau không?
9. Session có rotation sau đăng nhập, expiry, logout và revoke phía server không?
10. Có chống XSS/CSRF, kiểm soát log/telemetry và bảo vệ endpoint không?
11. Cấu hình Secure có được kiểm thử qua response header thực tế trên staging/production không?
12. Có kiểm tra hành vi trình duyệt mục tiêu, localhost exception và các luồng cross-site cần thiết không?

**Kết luận:** Secure flag yêu cầu trình duyệt chỉ gửi cookie qua kênh an toàn, thường là HTTPS. Nó giảm nguy cơ cookie phiên bị nghe lén trên HTTP nhưng không tự bảo vệ cookie khỏi XSS, CSRF, endpoint bị chiếm, log hoặc replay sau khi cookie bị đánh cắp. Cấu hình cookie phiên nên kết hợp Secure, HttpOnly, SameSite phù hợp, host-only scope/prefix khi thích hợp, HTTPS toàn site, HSTS và quản lý session có khả năng thu hồi.
