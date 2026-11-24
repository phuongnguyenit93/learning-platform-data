# Expires và Max-Age: kiểm soát thời hạn cookie an toàn

> **Chương:** Cookie  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Cookie thường được dùng để duy trì trạng thái đăng nhập, ghi nhớ tùy chọn giao diện, phân tích phiên truy cập hoặc lưu một mã định danh ngắn hạn. Hai thuộc tính **`Expires`** và **`Max-Age`** cho trình duyệt biết cookie có thể được giữ đến khi nào. Cấu hình thời hạn ảnh hưởng trực tiếp đến trải nghiệm người dùng, vòng đời phiên đăng nhập và mức độ rủi ro khi cookie bị đánh cắp.

Điểm quan trọng là **thời hạn cookie phía trình duyệt và thời hạn phiên phía máy chủ là hai cơ chế riêng**. Cookie còn nằm trong trình duyệt không chứng minh phiên đăng nhập vẫn hợp lệ; ngược lại, xóa cookie trên máy khách không tự động thu hồi một session mà máy chủ vẫn chấp nhận.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa thời điểm hết hạn tuyệt đối của `Expires` và khoảng thời gian tương đối của `Max-Age`.
2. Xác định thuộc tính nào được ưu tiên khi một `Set-Cookie` có cả hai thuộc tính.
3. Phân biệt session cookie với persistent cookie và cookie session với phiên đăng nhập phía server.
4. Xóa cookie đúng phạm vi bằng cách giữ đúng tên, `Path` và `Domain`.
5. Đánh giá ảnh hưởng của clock skew, session restore, browser eviction và chính sách quyền riêng tư.
6. Thiết kế thời hạn cookie phiên đăng nhập theo nguyên tắc tối thiểu, kết hợp `Secure`, `HttpOnly`, `SameSite` và timeout phía server.
7. Dùng DevTools và Node.js để kiểm chứng cookie thực sự được lưu, gửi và hết hạn.

## 1. Cookie được tạo và lưu như thế nào?

### 1.1 Server gửi `Set-Cookie`

Máy chủ tạo hoặc cập nhật cookie bằng response header `Set-Cookie`:

~~~http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; Max-Age=86400; SameSite=Lax
Content-Type: text/html; charset=utf-8
~~~

Trình duyệt đọc header, kiểm tra các thuộc tính và quyết định có lưu cookie hay không. Một cookie có thể bị từ chối do cú pháp không hợp lệ, chính sách bảo mật, giới hạn lưu trữ hoặc thiết lập quyền riêng tư.

Khi gửi request tiếp theo đến host/path phù hợp, trình duyệt thường đính kèm:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Cookie: theme=dark
~~~

Header `Cookie` chỉ chứa các cặp tên/giá trị phù hợp. Các thuộc tính như `Expires`, `Max-Age`, `Path`, `Domain`, `Secure`, `HttpOnly` và `SameSite` **không được gửi ngược lại** trong header này.

### 1.2 Thuộc tính cookie là chỉ dẫn cho trình duyệt

| Thuộc tính | Vai trò |
|---|---|
| `Expires` | Thời điểm tuyệt đối mà cookie hết hạn |
| `Max-Age` | Thời lượng cookie được giữ tính từ lúc nhận cookie |
| `Domain` | Xác định host/domain có thể nhận cookie |
| `Path` | Giới hạn đường dẫn request phù hợp |
| `Secure` | Giới hạn gửi cookie trong ngữ cảnh kết nối an toàn |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua `document.cookie` |
| `SameSite` | Kiểm soát việc gửi cookie trong ngữ cảnh same-site/cross-site |
| `Partitioned` | Yêu cầu cookie phân vùng theo ngữ cảnh site khi được browser hỗ trợ và đáp ứng điều kiện cần thiết |

Cookie không phải dữ liệu được bảo vệ bằng mã hóa chỉ vì nó được lưu trong browser. Với session cookie, nên lưu một **mã định danh phiên ngẫu nhiên, khó đoán**, còn dữ liệu và quyền của phiên được quản lý phía server.

### 1.3 Một cookie được xác định bởi phạm vi lưu trữ

Khi phân tích cookie, không chỉ nhìn tên. Cùng một tên có thể tồn tại ở các phạm vi khác nhau, ví dụ:

- Cookie host-only cho `app.example.com`.
- Cookie có `Domain=example.com` dùng được cho host phù hợp trong domain đó.
- Cookie có `Path=/admin` và cookie có `Path=/`.

Vì vậy, khi xóa hoặc cập nhật cookie, cần biết **name + domain scope + path** của cookie ban đầu. Chỉ gửi một header có cùng tên nhưng khác path/domain có thể tạo hoặc xóa một cookie khác.

## 2. `Expires`: thời điểm hết hạn tuyệt đối

### 2.1 Cú pháp và ý nghĩa

`Expires` chứa một ngày giờ theo định dạng HTTP-date. Giá trị nên dùng dạng chuẩn IMF-fixdate, có múi giờ GMT:

~~~http
Set-Cookie: remember_me=opaque-value; Expires=Thu, 31 Dec 2026 23:59:59 GMT; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa: trình duyệt có thể giữ cookie đến thời điểm ngày 31 tháng 12 năm 2026, 23:59:59 GMT, trừ khi cookie bị xóa, bị thay thế hoặc bị browser loại bỏ sớm hơn.

Các điểm cần nhớ:

- `Expires` là **mốc thời gian**, không phải số giây.
- Dùng GMT/UTC để tránh nhập nhằng múi giờ.
- Ngày không hợp lệ hoặc không parse được có thể khiến thuộc tính bị bỏ qua.
- Thời điểm đã nằm trong quá khứ khiến cookie hết hạn ngay khi browser xử lý.
- Một cookie có `Expires` hợp lệ là persistent cookie, trừ khi có cơ chế khác làm cookie bị loại bỏ.

Không dùng định dạng ngày tùy ý như `31/12/2026` hoặc chuỗi theo locale của máy chủ. Hãy dùng thư viện HTTP/cookie chuẩn để tạo HTTP-date.

### 2.2 Tạo Expires trong JavaScript phía server

Node.js có thể tạo HTTP-date bằng `toUTCString()`:

~~~js
const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);

const cookie = [
  'remember_me=opaque-value',
  'Expires=' + expiresAt.toUTCString(),
  'Path=/',
  'Secure',
  'HttpOnly',
  'SameSite=Lax'
].join('; ');

res.setHeader('Set-Cookie', cookie);
~~~

Đây là ví dụ xây dựng response header phía server. Không tạo cookie đăng nhập bằng JavaScript client nếu ứng dụng cần thuộc tính `HttpOnly`; JavaScript không thể đặt `HttpOnly` qua `document.cookie`.

### 2.3 Clock skew và thời gian tuyệt đối

`Expires` phụ thuộc một mốc thời gian tuyệt đối. Nếu đồng hồ máy khách và máy chủ lệch nhau, cách browser diễn giải thời điểm hết hạn có thể khác với kỳ vọng của ứng dụng.

Một số browser điều chỉnh độ lệch bằng header `Date` trong response khi tính thời gian cookie; hành vi chi tiết có thể khác giữa trình duyệt. Do đó:

- Không dùng thời hạn cookie client làm nguồn duy nhất để quyết định phiên còn hợp lệ.
- Server cần quản lý expiration độc lập bằng đồng hồ phía server.
- Với cookie cần một khoảng thời gian tương đối, `Max-Age` thường diễn đạt ý định rõ hơn và tránh phụ thuộc trực tiếp vào đồng hồ lịch của máy khách.

## 3. `Max-Age`: thời lượng tính bằng giây

### 3.1 Cú pháp và ý nghĩa

`Max-Age` biểu diễn số giây cookie được phép tồn tại tính từ khi browser nhận header:

~~~http
Set-Cookie: cart_hint=opaque-value; Max-Age=1800; Path=/; Secure; SameSite=Lax
~~~

Cookie này có thời lượng 1.800 giây, tương đương 30 phút, tính từ lúc nhận cookie.

| Giá trị | Ý nghĩa |
|---|---|
| `Max-Age=3600` | Khoảng một giờ |
| `Max-Age=86400` | Khoảng một ngày |
| `Max-Age=604800` | Khoảng bảy ngày |
| `Max-Age=0` | Hết hạn ngay; thường dùng để xóa |
| `Max-Age` âm hoặc không dương theo cách browser chấp nhận | Hết hạn ngay |
| Giá trị không hợp lệ | Thuộc tính có thể bị bỏ qua |

`Max-Age` là **số giây**, không phải milliseconds. Trong JavaScript, `Date.now()` trả về milliseconds; nếu tính toán một mốc ngày để tạo `Expires`, cần chuyển đổi đơn vị đúng.

### 3.2 Vì sao Max-Age hữu ích?

Với thời lượng tương đối, server có thể nói rõ “cookie này sống trong 30 phút sau khi browser nhận nó” thay vì tự tạo một ngày giờ tuyệt đối.

Ví dụ:

~~~js
const maxAgeSeconds = 30 * 60;

res.setHeader(
  'Set-Cookie',
  'preference=compact; Max-Age=' + maxAgeSeconds +
    '; Path=/; SameSite=Lax'
);
~~~

`Max-Age` đặc biệt tiện khi tính từ thời điểm response được phát ra. Tuy vậy, nó vẫn là **thời hạn phía browser**. Server không thể dựa vào việc cookie tự biến mất để thay thế kiểm tra thời hạn session.

### 3.3 Max-Age không phải timeout hoạt động

`Max-Age=1800` không có nghĩa “người dùng không thao tác trong 30 phút thì bị đăng xuất”. Nó có nghĩa cookie hết hạn sau khoảng thời gian kể từ khi nhận/cập nhật cookie.

Nếu server phát lại cùng cookie và đặt `Max-Age` mới sau mỗi request, thời hạn phía browser có thể được kéo dài. Đó là một dạng **sliding expiration** nếu được thiết kế có chủ đích.

Phân biệt:

- **Absolute lifetime:** phiên không được sống quá một mốc tối đa, ví dụ 8 giờ kể từ khi đăng nhập.
- **Idle timeout:** phiên hết hạn nếu không có hoạt động hợp lệ trong 15 phút.
- **Cookie Max-Age:** thời gian browser giữ cookie.
- **Session token expiry:** thời hạn token/phiên mà server kiểm tra.

Một hệ thống an toàn có thể áp dụng đồng thời absolute lifetime và idle timeout phía server, rồi đặt cookie lifetime phù hợp để browser không giữ credential lâu hơn mức cần thiết.

## 4. Khi có cả Expires và Max-Age

### 4.1 Max-Age được ưu tiên

Nếu một header `Set-Cookie` có cả hai thuộc tính hợp lệ, **`Max-Age` có ưu tiên hơn `Expires`** khi xác định thời điểm hết hạn.

Ví dụ:

~~~http
Set-Cookie: demo=value; Expires=Thu, 31 Dec 2026 23:59:59 GMT; Max-Age=60; Path=/
~~~

Cookie có thời lượng 60 giây theo `Max-Age`, dù `Expires` nằm xa hơn. Trình duyệt hiện đại áp dụng `Max-Age` làm nguồn quyết định khi cả hai thuộc tính hợp lệ.

| Expires | Max-Age | Kết quả trong browser hỗ trợ cả hai |
|---|---|---|
| Một ngày trong tương lai | Không có | Dùng thời điểm Expires |
| Không có | 3600 | Dùng thời lượng 3600 giây |
| Một ngày trong tương lai | 60 | **Dùng Max-Age 60 giây** |
| Một ngày trong quá khứ | 3600 | **Dùng Max-Age 3600 giây** |
| Không có | 0 | Hết hạn ngay |
| Một ngày trong tương lai | Giá trị Max-Age không hợp lệ | Thuộc tính không hợp lệ bị bỏ qua; Expires có thể được dùng |

Một số client cũ có thể không hỗ trợ `Max-Age`. Trong môi trường cần tương thích, server có thể gửi cả hai: `Max-Age` cho browser hiện đại và `Expires` làm fallback. Phải đảm bảo hai giá trị biểu đạt **cùng một thời hạn dự kiến**, để browser cũ không giữ cookie lâu hơn ngoài ý muốn.

### 4.2 Ví dụ tạo hai giá trị tương ứng

~~~js
const lifetimeSeconds = 15 * 60;
const expiresAt = new Date(Date.now() + lifetimeSeconds * 1000);

const cookie = [
  'session_hint=opaque-value',
  'Max-Age=' + lifetimeSeconds,
  'Expires=' + expiresAt.toUTCString(),
  'Path=/',
  'Secure',
  'HttpOnly',
  'SameSite=Lax'
].join('; ');

res.setHeader('Set-Cookie', cookie);
~~~

Nếu browser hỗ trợ cả hai, `Max-Age` quyết định. `Expires` cung cấp fallback cho client không hiểu `Max-Age`.

**Không đảo ngược vai trò:** `Expires` không ghi đè một `Max-Age` hợp lệ chỉ vì ngày Expires gần hơn hoặc xa hơn.

## 5. Session cookie và persistent cookie

### 5.1 Session cookie

Nếu `Set-Cookie` không có `Expires` và cũng không có `Max-Age`, cookie thường là **session cookie**:

~~~http
Set-Cookie: temporary_state=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser giữ cookie trong phiên trình duyệt theo định nghĩa session của browser. Khi phiên kết thúc, session cookie thông thường bị loại bỏ.

Tuy nhiên, **không nên giả định đóng cửa sổ là cookie lập tức biến mất**. Tính năng khôi phục phiên (session restore), crash recovery hoặc đồng bộ trạng thái có thể khôi phục session cookie trong một số trình duyệt/cấu hình.

Session cookie cũng không có nghĩa server tự động xóa session record khi người dùng đóng tab. Browser không gửi một thông báo logout đáng tin cậy chỉ vì tab đóng.

### 5.2 Persistent cookie

Cookie có `Expires` hoặc `Max-Age` là persistent cookie:

~~~http
Set-Cookie: language=vi; Max-Age=2592000; Path=/; SameSite=Lax
~~~

Browser có thể lưu cookie qua nhiều lần khởi động, đến khi hết hạn hoặc bị xóa. Persistent cookie phù hợp với tùy chọn như ngôn ngữ hoặc giao diện, nhưng cần cân nhắc kỹ trước khi dùng để lưu credential.

### 5.3 So sánh hai loại

| Đặc điểm | Session cookie | Persistent cookie |
|---|---|---|
| Thuộc tính hết hạn | Không có `Expires`/`Max-Age` | Có một hoặc cả hai |
| Thời gian giữ | Theo vòng đời session browser | Theo thời hạn cookie |
| Có thể sống qua restart? | Có thể được khôi phục tùy browser/session restore | Thường có nếu chưa hết hạn và chưa bị xóa |
| Phù hợp | Trạng thái ngắn hạn không cần tồn tại lâu | Tùy chọn ghi nhớ, preference hoặc token có thời hạn rõ |
| Tự động logout server? | Không | Không |
| Có thể bị browser xóa sớm? | Có | Có |

**Không dùng session cookie như bảo đảm an toàn tuyệt đối.** Kẻ tấn công có thể đánh cắp cookie khi nó còn hiệu lực; session cần có timeout, rotation và thu hồi phía server.

## 6. Xóa cookie và thay đổi thời hạn

### 6.1 Xóa bằng Max-Age=0

Cách phổ biến để yêu cầu browser xóa cookie:

~~~http
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Có thể dùng `Expires` ở quá khứ:

~~~http
Set-Cookie: theme=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/
~~~

`Max-Age=0` thể hiện trực tiếp ý định hết hạn ngay và thường được ưu tiên nếu có cả hai thuộc tính.

### 6.2 Phải khớp phạm vi cookie ban đầu

Giả sử cookie được tạo:

~~~http
Set-Cookie: cart=abc; Path=/checkout; Domain=shop.example.com; Max-Age=3600
~~~

Nếu muốn xóa, phải gửi cookie cùng tên và đúng phạm vi Domain/Path:

~~~http
Set-Cookie: cart=; Path=/checkout; Domain=shop.example.com; Max-Age=0
~~~

Nếu xóa với `Path=/`, browser có thể coi đó là một cookie khác và cookie ban đầu vẫn còn. Nếu cookie ban đầu là host-only (không có Domain), đừng tùy tiện thêm Domain khi xóa.

Đối với prefix `__Host-`, cookie phải có `Secure`, `Path=/` và không có `Domain`. Khi cập nhật/xóa, giữ các yêu cầu prefix hợp lệ.

### 6.3 Logout cần thu hồi session phía server

Một luồng logout nên:

1. Xác thực yêu cầu logout theo session hiện tại.
2. Thu hồi hoặc đánh dấu session/token phía server không còn hợp lệ.
3. Gửi header xóa cookie với cùng name/domain/path và `Max-Age=0` hoặc `Expires` quá khứ.
4. Xóa trạng thái session liên quan ở client nếu có.
5. Trả response phù hợp và tránh cache trang chứa dữ liệu nhạy cảm.

Nếu chỉ xóa cookie ở browser mà server vẫn chấp nhận token cũ, token bị đánh cắp trước đó vẫn có thể được dùng cho tới khi hết hạn hoặc bị thu hồi.

### 6.4 Nhiều cookie phải dùng nhiều Set-Cookie header

Không nối nhiều cookie vào một header duy nhất bằng dấu phẩy. `Expires` chứa dấu phẩy trong HTTP-date, nên việc gộp có thể khiến parser hiểu sai.

Ví dụ đúng:

~~~http
Set-Cookie: preference=dark; Max-Age=86400; Path=/
Set-Cookie: __Host-session=opaque; Max-Age=1800; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong Node.js, có thể đặt một mảng header:

~~~js
res.setHeader('Set-Cookie', [
  'preference=dark; Max-Age=86400; Path=/',
  '__Host-session=opaque; Max-Age=1800; Path=/; Secure; HttpOnly; SameSite=Lax'
]);
~~~

## 7. Thời hạn cookie và thiết kế phiên đăng nhập an toàn

### 7.1 Cookie lifetime không phải session lifetime

Ví dụ browser có cookie:

~~~http
Cookie: __Host-session=abc123
~~~

Server vẫn cần tra cứu session và kiểm tra:

- Session có tồn tại không?
- Session đã hết absolute lifetime chưa?
- Người dùng có idle quá lâu không?
- Session có bị logout hoặc revoke không?
- User có bị khóa hoặc cần xác thực lại không?
- Quyền truy cập tài nguyên có còn hợp lệ không?

Cookie có thể vẫn được browser gửi sau khi server đã thu hồi session; server phải từ chối token đó. Ngược lại, browser có thể xóa cookie sớm dù session phía server chưa hết hạn, khiến người dùng cần đăng nhập lại.

### 7.2 Một mẫu cookie session an toàn hơn

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_ID; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính có ý nghĩa:

- `__Host-`: giảm rủi ro cookie bị đặt từ subdomain khác bằng Domain attribute.
- `Path=/`: bắt buộc với prefix __Host- và áp dụng trên toàn host.
- `Secure`: chỉ gửi trong kết nối an toàn.
- `HttpOnly`: giảm khả năng script đọc trực tiếp session ID.
- `SameSite=Lax`: giảm một số request cookie cross-site, nhưng không thay thế CSRF protection.
- `Max-Age=1800`: browser giữ cookie khoảng 30 phút tính từ lúc nhận.

Đây là ví dụ cấu hình, không phải thời hạn phù hợp cho mọi sản phẩm. Ứng dụng cần chọn lifetime dựa trên độ nhạy dữ liệu, mức độ rủi ro, yêu cầu xác thực lại và trải nghiệm người dùng.

### 7.3 Sliding expiration và absolute expiration

**Sliding expiration** gia hạn idle timeout khi có hoạt động hợp lệ. Ví dụ, mỗi lần request được xác thực và đáp ứng điều kiện, server cập nhật thời hạn session và có thể phát lại cookie với `Max-Age` mới.

**Absolute expiration** là mốc tối đa mà phiên không thể vượt qua, kể cả khi người dùng hoạt động liên tục. Ví dụ: phiên hết sau 8 giờ kể từ khi đăng nhập; người dùng phải xác thực lại.

Một thiết kế có thể kết hợp:

| Chính sách | Ví dụ minh họa | Kiểm tra ở đâu |
|---|---|---|
| Cookie Max-Age | 30 phút | Browser |
| Idle timeout | 15 phút không hoạt động | Server |
| Absolute lifetime | 8 giờ từ lúc login | Server |
| Revoke khi logout | Ngay lập tức | Server/session store |
| Re-authentication | Trước thao tác rủi ro cao | Server/identity provider |

Không lấy cookie Max-Age làm đồng hồ duy nhất của session. Nếu server chỉ gia hạn cookie mà không áp dụng absolute lifetime, phiên có thể tồn tại lâu hơn dự kiến.

### 7.4 Thời hạn càng dài, cửa sổ rủi ro càng lớn

Một persistent session cookie tồn tại nhiều ngày có thể giúp người dùng tiện lợi nhưng cũng kéo dài thời gian credential bị lạm dụng nếu bị đánh cắp. Hãy cân nhắc:

- Thời gian sử dụng thực tế và mức nhạy cảm của tài khoản.
- Xác thực lại khi đổi mật khẩu, thay email, thay phương thức MFA hoặc thực hiện giao dịch quan trọng.
- Rotation session ID sau đăng nhập, nâng quyền hoặc thay đổi trạng thái xác thực.
- Thu hồi session ở server khi logout, phát hiện bất thường hoặc tài khoản bị khóa.
- Giới hạn số phiên và cung cấp khả năng quản lý/đăng xuất thiết bị nếu phù hợp.
- Dùng cookie flags, TLS và CSRF protection; Max-Age ngắn không sửa được XSS hoặc lỗi phân quyền.

## 8. Những giới hạn thực tế của expiration

### 8.1 Browser có thể xóa cookie trước hạn

Ngày hết hạn là thời hạn tối đa mà cookie được phép tồn tại theo chỉ dẫn, không phải cam kết browser sẽ giữ tới đúng giây đó. Browser có thể xóa cookie sớm vì:

- Người dùng xóa dữ liệu trang web.
- Chế độ riêng tư kết thúc.
- Chính sách chống tracking hoặc phân vùng cookie.
- Giới hạn số lượng/dung lượng cookie.
- Browser dọn dẹp dữ liệu để giải phóng bộ nhớ.
- Người dùng hoặc extension thay đổi dữ liệu lưu trữ.

Do đó, ứng dụng phải hoạt động đúng khi cookie biến mất: yêu cầu đăng nhập lại, khôi phục dữ liệu an toàn hoặc báo lỗi phiên hết hạn.

### 8.2 Browser có thể khôi phục session cookie

Session cookie không có mốc hết hạn tường minh, nhưng tính năng khôi phục phiên có thể lưu và phục hồi trạng thái session. Không dùng việc “đóng trình duyệt” như cơ chế revoke session phía server.

### 8.3 Cookie expiration không hủy request đã gửi

Nếu browser đã gửi request mang cookie, việc server phát response xóa cookie không thể thu hồi request đó hoặc hoàn tác thao tác đã xử lý. Muốn ngăn request tiếp theo, cần thu hồi session phía server và kiểm tra session trên mọi request cần bảo vệ.

### 8.4 Cookie không nên lưu dữ liệu bí mật tùy tiện

Cookie được tự động gửi theo phạm vi phù hợp, nên giá trị cookie có thể xuất hiện trong request log, proxy, tracing hoặc hệ thống giám sát. Không lưu mật khẩu, access token dài hạn hoặc dữ liệu nhạy cảm không cần thiết. Nếu lưu session ID, cần tạo ngẫu nhiên mạnh, tránh lộ qua URL và giới hạn lifetime.

## 9. Thực hành: kiểm chứng Expires, Max-Age và HttpOnly

Bài lab dùng Node.js và browser trên cùng máy. Cookie chỉ là dữ liệu giả, không sử dụng tài khoản thật.

### 9.1 Tạo file `cookie-expiration-lab.mjs`

~~~js
import { createServer } from 'node:http';

const html = [
  '<!doctype html><html lang="vi"><meta charset="utf-8">',
  '<title>Cookie expiration lab</title>',
  '<h1>Cookie expiration lab</h1>',
  '<p>Cookie demo dùng dữ liệu giả trên localhost.</p>',
  '<button id="set">1. Set cookies</button>',
  '<button id="inspect">2. Inspect cookies</button>',
  '<button id="delete">3. Delete cookies</button>',
  '<pre id="output"></pre>',
  '<script>',
  'const output = document.querySelector("#output");',
  'async function call(path) {',
  '  const response = await fetch(path);',
  '  const data = await response.json();',
  '  output.textContent = JSON.stringify({',
  '    server: data,',
  '    documentCookie: document.cookie',
  '  }, null, 2);',
  '}',
  'document.querySelector("#set").onclick = () => call("/set");',
  'document.querySelector("#inspect").onclick = () => call("/inspect");',
  'document.querySelector("#delete").onclick = () => call("/delete");',
  '</script></html>'
].join('\n');

function readCookieNames(header = '') {
  return header
    .split(';')
    .map(part => part.trim().split('=')[0])
    .filter(Boolean);
}

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (url.pathname === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store'
    });
    return res.end(html);
  }

  if (url.pathname === '/set') {
    const expires = new Date(Date.now() + 5 * 60 * 1000);
    const cookies = [
      'expires_demo=expires-value; Expires=' +
        expires.toUTCString() + '; Path=/; SameSite=Lax',
      'maxage_demo=maxage-value; Max-Age=60; Path=/; SameSite=Lax',
      'both_demo=both-value; Expires=' +
        new Date(Date.now() + 60 * 60 * 1000).toUTCString() +
        '; Max-Age=15; Path=/; SameSite=Lax',
      'session_demo=session-value; Path=/; SameSite=Lax',
      'http_only_demo=hidden-value; Max-Age=120; Path=/; HttpOnly; SameSite=Lax'
    ];

    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Set-Cookie': cookies
    });
    return res.end(JSON.stringify({
      message: 'Đã gửi 5 Set-Cookie header riêng biệt.',
      expected: {
        expires_demo: 'Khoảng 5 phút',
        maxage_demo: '60 giây',
        both_demo: '15 giây; Max-Age ưu tiên Expires',
        session_demo: 'Session cookie',
        http_only_demo: '120 giây; HttpOnly'
      }
    }));
  }

  if (url.pathname === '/delete') {
    const names = [
      'expires_demo',
      'maxage_demo',
      'both_demo',
      'session_demo',
      'http_only_demo'
    ];

    const cookies = names.map(name =>
      name + '=; Max-Age=0; Path=/; SameSite=Lax'
    );

    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Set-Cookie': cookies
    });
    return res.end(JSON.stringify({
      message: 'Đã gửi lệnh xóa cùng tên và Path=/ cho cookie demo.'
    }));
  }

  if (url.pathname === '/inspect') {
    const names = readCookieNames(req.headers.cookie || '');
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    });
    return res.end(JSON.stringify({
      receivedCookieNames: names,
      httpOnlyReceived: names.includes('http_only_demo')
    }));
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
}).listen(3000, 'localhost', () => {
  console.log('Cookie lab: http://localhost:3000');
});
~~~

### 9.2 Chạy và quan sát

1. Lưu file thành `cookie-expiration-lab.mjs`.
2. Chạy `node cookie-expiration-lab.mjs`.
3. Mở `http://localhost:3000` trong browser.
4. Mở DevTools → **Application/Storage → Cookies** để quan sát cookie và expiration.
5. Nhấn **Set cookies**; kiểm tra response của `/set` có năm `Set-Cookie` header.
6. Nhấn **Inspect cookies**; so sánh cookie browser gửi với `document.cookie`.
7. Chờ khoảng 20 giây rồi Inspect lại để quan sát `both_demo` đã hết hạn dù Expires còn ở xa.
8. Chờ khoảng 65 giây rồi Inspect lại để so sánh `maxage_demo`.
9. Nhấn **Delete cookies** để xóa các cookie demo.

### 9.3 Kết quả cần quan sát

| Cookie | Thuộc tính | Kết quả dự kiến |
|---|---|---|
| `expires_demo` | Expires khoảng 5 phút | Còn trong browser trước thời điểm đó |
| `maxage_demo` | Max-Age 60 | Hết hạn sau khoảng 60 giây |
| `both_demo` | Expires 1 giờ, Max-Age 15 | Hết hạn theo Max-Age khoảng 15 giây |
| `session_demo` | Không có Expires/Max-Age | Session cookie |
| `http_only_demo` | Max-Age 120, HttpOnly | Server nhận được; JavaScript không thấy trong document.cookie |

Thời điểm browser dọn cookie có thể không trùng chính xác từng giây; điều cần kiểm tra là thứ tự và quy tắc ưu tiên.

**Lưu ý lab:** cookie demo không có `Secure` để chạy trên HTTP localhost đơn giản. Không dùng cấu hình này cho production. Cookie session thật cần HTTPS và `Secure`, cùng các thuộc tính phù hợp.

## 10. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Cookie vẫn còn sau thời gian Expires mong đợi | `Max-Age` hợp lệ dài hơn; header khác cập nhật cookie; browser restore/cache | Kiểm tra response Set-Cookie mới nhất và cookie cùng name/domain/path |
| Cookie biến mất sớm | Browser eviction, người dùng xóa, private mode hoặc chính sách privacy | Không giả định cookie luôn tồn tại; xử lý session mất an toàn |
| Cookie không bị xóa bởi Max-Age=0 | Sai Path/Domain hoặc đang xóa cookie khác cùng tên | Đối chiếu scope của cookie gốc và lệnh xóa |
| Cookie session tồn tại sau restart | Session restore của browser | Thu hồi session ở server; không dựa vào đóng browser |
| Cookie có Max-Age nhưng hết hạn khác dự kiến | Đơn vị nhầm milliseconds/seconds, giá trị bị ghi đè hoặc header không hợp lệ | Kiểm tra Max-Age theo giây và response thực tế |
| Cookie có Expires không đúng ngày | Format HTTP-date hoặc clock skew | Dùng UTC/GMT chuẩn, kiểm tra Date header và browser |
| JS không thấy cookie nhưng server nhận được | Cookie có HttpOnly | Đây là hành vi mong đợi; kiểm tra Network/Application thay vì document.cookie |
| Server không nhận cookie dù chưa hết hạn | Domain/Path/Secure/SameSite/credentials không phù hợp | Kiểm tra request context và thuộc tính gửi cookie |
| Logout xong token cũ vẫn truy cập được | Chỉ xóa cookie phía browser, chưa revoke session | Thu hồi session/token phía server |
| Cookie bị ghi đè ngoài dự kiến | Nhiều Set-Cookie cùng name nhưng khác scope hoặc response khác cập nhật | Kiểm tra từng response và khóa nhận diện name/domain/path |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một cookie có `Expires` là ngày mai và `Max-Age=60`. Browser hiện đại ưu tiên thuộc tính nào?

**Đáp án:** `Max-Age` hợp lệ được ưu tiên; cookie có thời lượng khoảng 60 giây kể từ lúc browser nhận response.

**Câu 2.** `Expires` khác `Max-Age` ở điểm cốt lõi nào?

**Đáp án:** `Expires` là mốc ngày giờ tuyệt đối; `Max-Age` là khoảng thời gian tương đối tính bằng giây từ lúc nhận cookie.

**Câu 3.** Cookie không có `Expires` lẫn `Max-Age` có chắc chắn biến mất ngay khi đóng tab không?

**Đáp án:** Không. Đây là session cookie theo session browser, không theo tab. Session restore có thể khôi phục cookie; server cũng không tự động được báo logout.

**Câu 4.** Vì sao nên gửi cả Expires và Max-Age trong một số môi trường tương thích?

**Đáp án:** Browser hiện đại ưu tiên Max-Age; Expires có thể làm fallback cho client cũ không hỗ trợ Max-Age. Hai thời hạn cần được tính tương ứng.

**Câu 5.** Muốn xóa cookie được tạo với `Path=/checkout` và `Domain=shop.example.com`, có thể gửi lệnh xóa với `Path=/` và bỏ Domain không?

**Đáp án:** Không đảm bảo. Đó có thể là một cookie khác. Cần khớp name, path và domain scope của cookie gốc.

**Câu 6.** Cookie có `Max-Age=0` nhưng server vẫn chấp nhận session ID cũ. Vì sao?

**Đáp án:** Max-Age chỉ yêu cầu browser loại cookie. Nó không thu hồi session/token phía server. Server cần revoke hoặc hết hạn session riêng.

**Câu 7.** `Max-Age=1800` có phải idle timeout 30 phút không?

**Đáp án:** Không. Đó là thời gian browser giữ cookie sau khi nhận. Idle timeout phải được server tính từ hoạt động hợp lệ cuối cùng.

**Câu 8.** Vì sao JavaScript không thấy `http_only_demo` trong `document.cookie` nhưng server vẫn nhận được?

**Đáp án:** HttpOnly chặn JavaScript đọc cookie; browser vẫn tự đính kèm cookie trong request nếu các điều kiện gửi phù hợp.

**Câu 9.** Nếu Expires ở tương lai nhưng browser đã xóa cookie, ứng dụng nên làm gì?

**Đáp án:** Xử lý trạng thái thiếu cookie một cách an toàn, ví dụ yêu cầu đăng nhập lại hoặc khôi phục phiên theo quy trình được bảo vệ. Không giả định browser giữ cookie tới hạn.

**Câu 10.** Có nên đặt session cookie sống một năm chỉ để tránh người dùng đăng nhập lại không?

**Đáp án:** Không nên quyết định chỉ theo tiện lợi. Cần đánh giá rủi ro credential bị đánh cắp, absolute lifetime, idle timeout, re-authentication, rotation và khả năng thu hồi phía server.

## 12. Checklist thiết kế expiration an toàn

Trước khi phát hành cookie, hãy kiểm tra:

1. **Mục đích cookie:** preference, analytics hay session credential? Cookie nhạy cảm cần lifetime ngắn và kiểm soát chặt hơn.
2. **Thời hạn browser:** chọn `Max-Age` cho khoảng thời gian tương đối; thêm `Expires` tương ứng khi cần tương thích.
3. **Phạm vi:** xác định host-only/Domain và Path tối thiểu; dùng prefix `__Host-` cho session cookie khi phù hợp.
4. **Thuộc tính bảo vệ:** `Secure`, `HttpOnly`, `SameSite`; cân nhắc `Partitioned` theo kiến trúc.
5. **Server session:** có idle timeout, absolute lifetime, rotation và revoke khi logout không?
6. **Xóa cookie:** response xóa có đúng name, Domain và Path không?
7. **Nhiều header:** mỗi cookie được gửi bằng một `Set-Cookie` header riêng.
8. **Kiểm thử:** xác minh bằng DevTools/Network và request thực tế; không chỉ nhìn `document.cookie`.
9. **Khôi phục và eviction:** ứng dụng có xử lý cookie bị xóa sớm hoặc session restore không?
10. **Bảo vệ request:** SameSite không thay thế CSRF token, authorization hoặc kiểm tra nghiệp vụ.

**Ghi nhớ:** `Expires` nói “hết hạn vào thời điểm nào”; `Max-Age` nói “giữ trong bao lâu”. Khi cả hai hợp lệ, `Max-Age` được ưu tiên. Cả hai chỉ điều khiển thời hạn cookie ở browser; **server vẫn phải quản lý vòng đời, xác thực và thu hồi phiên độc lập**.

## Tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
- [RFC 6265bis — Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/)
- [MDN — Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Session Management: Session Expiration](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-expiration)

