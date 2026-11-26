# Content-Type, yêu cầu đơn giản và yêu cầu có preflight

## Mục tiêu bài học

Khi một trang web gọi API khác origin, có trường hợp trình duyệt gửi thẳng **POST**, nhưng cũng có trường hợp trình duyệt gửi **OPTIONS preflight** rồi mới quyết định có gửi POST thực hay không. Sự khác biệt thường đến từ **HTTP method, request headers**, đặc biệt là **Content-Type**, và cách request được tạo.

Bài này thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**. Kiến thức phục vụ các lớp phòng vệ HTTP và trình duyệt trong Spring Security: **CORS, CSRF, security headers, CSP, HSTS, HTTP firewall và bảo vệ session**, trong cả **Servlet** và **Reactive/WebFlux**.

Sau bài học, bạn có thể:

1. Phân biệt Content-Type **request** và Content-Type **response**, xác định media type nào thuộc CORS safelist.
2. So sánh **simple request** với yêu cầu cần **CORS preflight** theo điều kiện về method, request headers và ngữ cảnh.
3. Đọc đúng các header **Origin**, **Access-Control-Request-Method**, **Access-Control-Request-Headers**, **Access-Control-Allow-Origin/Methods/Headers/Credentials**.
4. Giải thích vì sao **preflight không thay thế xác thực, phân quyền và CSRF protection**.
5. Cấu hình, thử nghiệm và chẩn đoán CORS trong Spring Security trên cả **Servlet** và **Reactive**.

## 1. CORS xuất hiện khi nào?

Ví dụ frontend chạy tại **https://app.example.com**, API chạy tại **https://api.example.com**:

~~~text
Trang: https://app.example.com
API:   https://api.example.com

Cùng scheme (https), thường cùng site (https://example.com).
Khác host nên CROSS-ORIGIN.
~~~

Với các URL HTTP/HTTPS thông thường:

**Origin = (scheme, host, port)**

Khi JavaScript ở origin này muốn đọc dữ liệu do API khác origin trả về bằng fetch/XHR, trình duyệt sử dụng **Cross-Origin Resource Sharing (CORS)**. Trong CORS, phải tách ba câu hỏi:

- **Browser có gửi request thực không?** Có trường hợp gửi ngay, có trường hợp cần OPTIONS preflight trước.
- **Browser có gửi cookie/credentials không?** Phụ thuộc fetch credentials mode, cookie Domain/Path/Secure/SameSite và chính sách trình duyệt.
- **JavaScript có đọc được response không?** Browser kiểm tra CORS header của **response thực**, kể cả khi preflight đã đạt.

Cùng site không đồng nghĩa cùng origin. Hai subdomain có thể cùng site nên cookie SameSite đủ điều kiện gửi, nhưng vẫn phải có CORS nếu JavaScript muốn đọc response của API khác origin.

## 2. Content-Type của request khác Content-Type của response

**Content-Type** diễn tả media type của nội dung HTTP mà header đi kèm.

Ví dụ **request** gửi JSON:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json

{"productId":42,"quantity":1}
~~~

Ví dụ **response** trả JSON:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":101,"status":"CREATED"}
~~~

Khi tài liệu CORS nói **application/json thường kích hoạt preflight**, ý đang đề cập **Content-Type của request**, không phải Content-Type của response. Một GET có thể nhận JSON nhưng không cần preflight chỉ vì response là JSON.

### 2.1. Ba Content-Type thường thuộc CORS safelist

Trong các yêu cầu CORS thông thường, media type essence của **Content-Type request** được CORS safelist gồm:

- **application/x-www-form-urlencoded**
- **multipart/form-data**
- **text/plain**

Với các media type khác, chẳng hạn **application/json**, **application/xml**, **application/octet-stream** hoặc **application/problem+json**, Content-Type request sẽ không được safelist, và thường làm fetch cross-origin cần preflight.

| Request Content-Type | Body thường gặp | CORS-safelisted Content-Type? |
| --- | --- | --- |
| application/x-www-form-urlencoded | HTML form hoặc URLSearchParams | Có, nếu đáp ứng thêm các giới hạn. |
| multipart/form-data | FormData, form upload file | Có, nếu đáp ứng thêm các giới hạn. |
| text/plain | Văn bản thuần | Có, nếu đáp ứng thêm các giới hạn. |
| application/json | JSON body | Không. |
| application/xml | XML body | Không. |
| application/octet-stream | Dữ liệu nhị phân chung | Không. |

Safelist được xác định theo **MIME type đã phân tích** (media type essence), còn có các điều kiện về byte/ký tự và độ dài của giá trị header. Vì thế:

~~~http
Content-Type: text/plain;charset=UTF-8
~~~

vẫn có essence là text/plain và thường đủ điều kiện safelist nếu thỏa các giới hạn khác. Không suy ra “hễ có charset là sẽ preflight”.

### 2.2. FormData và multipart boundary

Với FormData, browser tự đặt boundary để phân tách các phần:

~~~javascript
const form = new FormData();
form.append("displayName", "An");
form.append("avatar", fileInput.files[0]);

await fetch("https://api.example.com/api/avatar", {
  method: "POST",
  body: form
});
~~~

Biến **fileInput** trong ví dụ là phần tử input file đã tồn tại và có file được chọn. **Không tự đặt Content-Type là multipart/form-data thiếu boundary**:

~~~javascript
// Không nên: browser không thể tự chèn boundary đúng theo ý định này.
await fetch("https://api.example.com/api/avatar", {
  method: "POST",
  headers: { "Content-Type": "multipart/form-data" },
  body: form
});
~~~

Nếu thiếu boundary, server có thể không phân tích được multipart body. Browser tự tạo Content-Type khi gửi FormData theo cách thông thường. Dù multipart có thể không cần preflight, API upload vẫn phải xác thực, phân quyền, kiểm tra CSRF nếu có cookie/session, kiểm tra file và giới hạn dung lượng.

## 3. “Simple request” thực chất là gì?

**Simple request** là thuật ngữ phổ biến trong tài liệu CORS để chỉ những request có thể được gửi **mà không cần preflight** khi đáp ứng điều kiện hạn chế. Trong đặc tả Fetch hiện đại, việc này dựa vào **CORS-safelisted method**, **CORS-safelisted request headers** và những điều kiện khác.

Cần phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **HTTP safe method** | Method không yêu cầu làm thay đổi trạng thái nghiệp vụ, như GET hoặc HEAD. |
| **CORS simple request** | Request đáp ứng các điều kiện để không cần bước kiểm tra OPTIONS trước. |
| **Same-origin request** | Request đến cùng scheme, host, port với nguồn. |
| **Authenticated request** | Server đã xác thực danh tính theo chính sách. |
| **CSRF-protected request** | Request đã thỏa cơ chế chống CSRF của ứng dụng. |

**POST có thể là simple request nhưng không phải HTTP safe method.** Một POST từ form có thể thay đổi trạng thái; vì thế “simple” không đồng nghĩa “an toàn”.

### 3.1. Điều kiện method

| Method | CORS-safelisted? | Ghi chú |
| --- | --- | --- |
| **GET** | Có | Thường không preflight nếu các điều kiện khác thỏa. |
| **HEAD** | Có | Tương tự GET về điều kiện method. |
| **POST** | Có | Có thể làm thay đổi trạng thái nghiệp vụ. |
| **PUT** | Không | Thường cần preflight nếu CORS request cross-origin. |
| **PATCH** | Không | Thường cần preflight. |
| **DELETE** | Không | Thường cần preflight. |
| **OPTIONS** | Không | Không thuộc ba method CORS safelist, dù bản thân OPTIONS được dùng làm preflight do browser tạo. |

OPTIONS và TRACE có ngữ nghĩa *safe* theo HTTP nhưng không vì thế trở thành phương thức thuộc CORS safelist dành cho các request nghiệp vụ. Safe theo HTTP và safelisted theo CORS là hai điều khác nhau.

### 3.2. Điều kiện request header

Những tên **request header** CORS-safelisted phổ biến gồm:

- **Accept**
- **Accept-Language**
- **Content-Language**
- **Content-Type**, chỉ với media type essence được safelist
- **Range**, với cú pháp single byte range được phép

Các header này còn phải đáp ứng giới hạn về **giá trị**, độ dài hoặc cú pháp. Không phải mọi giá trị tùy ý của Accept, Range hay Content-Type đều được safelist.

Ngược lại, các header như **Authorization**, **X-API-KEY**, **X-Requested-With** và **X-CSRF-TOKEN** không thuộc CORS safelist. Thêm các header này vào request fetch cross-origin thường khiến browser phải gửi OPTIONS.

### 3.3. Điều kiện khác ngoài method và header

Một số tính năng của API tạo request, chẳng hạn cách gửi streaming body hoặc một số upload event listener, có thể khiến request phải preflight dù method và Content-Type nhìn qua thuộc nhóm safelisted. Hãy dùng **DevTools → Network** để quan sát thực tế trước khi kết luận chắc chắn.

Không phải mọi request cross-origin đều là fetch/XHR. **Form HTML**, điều hướng, ảnh, iframe và script có các quy tắc riêng. Đặc biệt, form HTML có thể gửi request cross-origin mà không cần preflight CORS như một lệnh fetch JSON có custom header.

## 4. Ví dụ: POST form không preflight, POST JSON có preflight

Giả sử trang ở **https://app.example.com** gọi **https://api.example.com**.

### 4.1. POST application/x-www-form-urlencoded

~~~javascript
const params = new URLSearchParams();
params.set("message", "Hello");

await fetch("https://api.example.com/api/feedback", {
  method: "POST",
  body: params
});
~~~

Khi browser tạo Content-Type phù hợp và không có yếu tố khác buộc preflight, request này thường **được gửi ngay**. JavaScript vẫn chỉ đọc được response nếu API trả CORS header phù hợp.

Form HTML truyền thống cũng có thể gửi POST tương tự:

~~~html
<form action="https://api.example.com/api/feedback" method="post">
  <input name="message" value="Hello">
  <button type="submit">Gửi</button>
</form>
~~~

Không nên hiểu rằng mọi form POST đều không cần kiểm tra ở server. Nếu endpoint dùng cookie/session để thay đổi trạng thái, phải có bảo vệ CSRF và quyền phù hợp.

### 4.2. POST text/plain

~~~javascript
await fetch("https://api.example.com/api/notes", {
  method: "POST",
  headers: {
    "Content-Type": "text/plain;charset=UTF-8"
  },
  body: "Ghi chú minh họa"
});
~~~

Trường hợp này thường không preflight nếu các điều kiện khác thỏa. Nếu server định xử lý JSON, không nên gửi JSON giả dạng text/plain chỉ để tránh OPTIONS: điều đó khiến hợp đồng media type không rõ ràng và có thể tạo rủi ro CSRF nếu server chấp nhận nhiều dạng body bất ngờ.

### 4.3. POST application/json

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});
~~~

Đây là request CORS thường **cần preflight** vì Content-Type request không thuộc safelist. Trình duyệt gửi OPTIONS để hỏi server về POST và header content-type, chỉ tiếp tục gửi POST nếu preflight hợp lệ.

### 4.4. POST form có X-CSRF-TOKEN

~~~javascript
const params = new URLSearchParams({ productId: "42" });

await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRF-TOKEN": csrfToken
  },
  body: params
});
~~~

**csrfToken** phải được ứng dụng cấp hợp lệ. Dù Content-Type application/x-www-form-urlencoded được safelist, header **X-CSRF-TOKEN** không được safelist, nên request CORS thông thường phải preflight.

Việc tự thêm header X-CSRF-TOKEN **không tự bảo đảm CSRF được kiểm tra**. Server phải tạo, liên kết và xác minh token theo cơ chế thực tế.

### 4.5. Ma trận so sánh nhanh

| Request từ JavaScript | Thường cần OPTIONS preflight? | Nguyên nhân |
| --- | --- | --- |
| GET với các header được safelist | Không | Method và headers phù hợp. |
| POST text/plain | Không | Content-Type request được safelist. |
| POST application/x-www-form-urlencoded | Không | Content-Type request được safelist. |
| POST FormData multipart/form-data | Không | Media type được safelist, nếu không có điều kiện khác. |
| POST application/json | **Có** | Content-Type không được safelist. |
| POST application/xml | **Có** | Content-Type không được safelist. |
| GET kèm X-API-KEY | **Có** | Custom header không được safelist. |
| GET kèm Authorization: Bearer | **Có** | Authorization không được safelist. |
| POST kèm X-CSRF-TOKEN | **Có** | Custom header không được safelist. |
| PUT, PATCH hoặc DELETE | **Có** | Method không thuộc safelist. |

Các kết luận trên giả định **request fetch/XHR CORS thông thường**, không có ngoại lệ hoặc thuộc tính khác buộc preflight. **Content-Type application/json của response không làm preflight xảy ra.**

## 5. Browser gửi OPTIONS preflight ra sao?

Ví dụ frontend định gửi POST JSON kèm X-CSRF-TOKEN.

~~~mermaid
sequenceDiagram
    participant F as Frontend
    participant B as Trình duyệt
    participant A as API Spring
    F->>B: fetch POST JSON + X-CSRF-TOKEN
    B->>A: OPTIONS preflight
    A-->>B: CORS headers cho phép/từ chối
    alt Preflight được chấp nhận
        B->>A: POST thực
        A-->>B: Response POST
        B-->>F: Response nếu CORS của response thực đạt
    else Preflight bị từ chối
        B-->>F: Lỗi CORS, POST chưa được gửi
    end
~~~

### 5.1. Request preflight

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Ý nghĩa:

- **Origin**: origin của trang khởi tạo request, gồm scheme, host và port; không chứa path.
- **Access-Control-Request-Method**: method sẽ dùng trong request thực, ví dụ POST.
- **Access-Control-Request-Headers**: **tên** các request header browser muốn được phép gửi. Header này không chứa giá trị CSRF token hoặc JSON body.

Các header preflight được trình duyệt tạo; JavaScript không nên cố giả mạo Origin hoặc Access-Control-Request-*.

**Không phải mọi OPTIONS đều là CORS preflight.** Một HTTP client có thể gửi OPTIONS để hỏi khả năng server. CORS preflight thường được nhận ra qua **Origin** kết hợp **Access-Control-Request-Method**.

### 5.2. Response preflight

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN, Authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
~~~

| Response header | Ý nghĩa |
| --- | --- |
| **Access-Control-Allow-Origin** | Origin cụ thể được phép đọc response CORS. |
| **Access-Control-Allow-Methods** | Các method được CORS policy cho phép. |
| **Access-Control-Allow-Headers** | Các request header được CORS policy cho phép. |
| **Access-Control-Allow-Credentials** | Cho phép đọc response CORS với credentials khi cấu hình phù hợp. |
| **Access-Control-Max-Age** | Cho browser cache kết quả preflight trong giới hạn áp dụng. |
| **Vary: Origin** | Hỗ trợ cache phân biệt response theo Origin nếu policy phụ thuộc Origin. |

Chỉ nhìn **204 No Content** là chưa đủ. Browser còn kiểm tra CORS header có cho phép **origin, method và header dự kiến** hay không.

**Access-Control-Allow-Methods: POST không cấp quyền tạo đơn**, mà chỉ là kết quả kiểm tra CORS. API vẫn phải xác thực session, kiểm tra CSRF token và phân quyền người dùng ở request POST thực.

### 5.3. Request POST thực và CORS response thực

Sau khi preflight đạt, browser có thể gửi:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: valid-token-issued-by-application
Cookie: __Host-session=opaque-value

{"productId":42,"quantity":1}
~~~

Cookie xuất hiện ở đây **chỉ nếu** request thực có credentials mode thích hợp và mọi quy tắc cookie cho phép. Response có thể là:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"id":101,"status":"CREATED"}
~~~

**Browser kiểm tra CORS header của response POST thực một lần nữa.** Preflight thành công không đảm bảo browser sẽ cho JavaScript đọc response nếu response POST thiếu Allow-Origin hoặc Allow-Credentials.

Ta phải tách:

1. **Preflight CORS thành công.**
2. **Request thực được gửi và server xử lý.**
3. **Response thực được browser cho JavaScript đọc.**

Ba kết luận này không đồng nghĩa nhau.

### 5.4. CORS preflight cache

**Access-Control-Max-Age** cho phép browser cache kết quả preflight đối với những request tương ứng; browser có thể áp dụng giới hạn hoặc cache ngắn hơn con số server gửi. Đây là **preflight cache**, khác với HTTP cache của dữ liệu JSON.

Nếu request đầu có OPTIONS nhưng các request giống sau đó không thấy OPTIONS mới, đừng suy ra browser không còn áp dụng CORS. Browser có thể đang sử dụng một kết quả preflight đã được cache. Request thực vẫn phải vượt qua auth/CSRF/authorization và response thực vẫn chịu CORS.

## 6. Cookie, credentials và Authorization

### 6.1. Preflight thường không mang session cookie

Trong mô hình CORS thông thường, **OPTIONS preflight không mang session cookie** dù request POST thực dùng cookie. Nếu server đòi xác thực cookie ở bước OPTIONS, preflight có thể nhận 401/403, khiến browser không gửi POST.

Để hỗ trợ tích hợp frontend hợp lệ, **xử lý CORS phải diễn ra trước các bộ lọc có thể từ chối preflight**. Sau đó, POST thực vẫn phải qua authentication, authorization và CSRF token.

Một số nền tảng có chi tiết riêng liên quan TLS client certificate trong giai đoạn preflight, nhưng đó không phải cơ sở thiết kế authentication cho OPTIONS. Với ứng dụng HTTP/session, không kỳ vọng preflight có Cookie header.

### 6.2. fetch credentials mode

| credentials mode | Hành vi |
| --- | --- |
| **same-origin** (mặc định) | Credentials được xử lý cho request same-origin; fetch cross-origin không tự gửi credentials. |
| **include** | Cho phép gửi credentials với fetch cross-origin khi chính sách cookie/browser cho phép. |
| **omit** | Không gửi credentials và không xử lý Set-Cookie theo luồng credentials thông thường. |

Frontend **https://app.example.com** muốn gọi API **https://api.example.com** dùng cookie:

~~~javascript
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Trong trường hợp response CORS có credentials, API cần cho phép một origin cụ thể:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

cho response CORS có credentials, vì browser không chấp nhận wildcard Allow-Origin khi đọc response đó.

**credentials: "include" không vượt qua Domain, Path, Secure, SameSite hoặc chính sách cookie bên thứ ba.** Hai subdomain có thể same-site nhưng cross-origin; fetch vẫn cần credentials phù hợp và CORS khi muốn đọc response.

### 6.3. Authorization khiến cả GET thường có preflight

~~~javascript
await fetch("https://api.example.com/api/me", {
  headers: {
    "Authorization": "Bearer " + accessToken
  }
});
~~~

GET có header Authorization không thuộc CORS safelist. Browser thường gửi:

~~~http
OPTIONS /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

CORS cho phép Authorization **không có nghĩa API chấp nhận token**. Server phải xác minh chữ ký/giá trị token, phạm vi và quyền theo thiết kế ứng dụng.

Khác cookie tự gửi, Bearer token nằm trong biến JavaScript hoặc localStorage **không được browser tự lấy ra và gắn vào Authorization**; mã ứng dụng phải thực hiện điều đó. Với endpoint dùng credential tự gửi, CSRF vẫn cần được xem xét độc lập.

## 7. Vì sao simple request không đồng nghĩa an toàn trước CSRF?

Giả sử người dùng đã đăng nhập tại **https://bank.example**. Cookie session đang tồn tại. Một website không đáng tin **https://outside.test** có thể cố gửi form:

~~~html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="amount" value="100">
  <input type="hidden" name="to" value="unwanted-recipient">
  <button type="submit">Continue</button>
</form>
~~~

Form có thể gửi POST trong ngữ cảnh cross-origin **mà không cần CORS preflight**. Việc cookie có được gửi phụ thuộc SameSite và các thuộc tính khác. **CORS có thể chặn JavaScript từ outside.test đọc response, nhưng không bảo đảm server chưa nhận và xử lý POST.**

### 7.1. SameSite giúp giảm rủi ro nhưng có giới hạn

Cookie **SameSite=Lax** thường không gửi trong form POST cross-site thông thường, nhưng **có thể gửi trong điều hướng GET cấp cao nhất cross-site**. Vì vậy không tạo endpoint chuyển tiền, hủy đơn hoặc đăng xuất bằng GET.

Ngoài ra, một subdomain không đáng tin, ví dụ **https://untrusted.example.com**, thường **same-site** với API **https://api.example.com**. SameSite không phải ranh giới tin cậy đủ mạnh cho tất cả subdomain.

### 7.2. Không dùng preflight làm CSRF defense duy nhất

Đòi frontend dùng **application/json** hoặc custom header có thể khiến browser phải preflight, nhưng điều đó **không thay thế CSRF token và phân quyền**. Nếu server chấp nhận **text/plain**, **application/x-www-form-urlencoded** hoặc một định dạng khác rồi diễn giải như thao tác nghiệp vụ, request có thể được tạo bằng form không qua preflight.

Cần:

- Bật và tích hợp **CSRF protection** cho thao tác thay đổi trạng thái khi dựa vào cookie/session.
- Kiểm tra **Content-Type** và parser đúng với hợp đồng API; không nhận body không mong đợi chỉ vì có thể phân tích được.
- Thực thi authentication và authorization ngay cả với request có CSRF token hợp lệ.
- Dùng Secure, HttpOnly, SameSite và phạm vi cookie phù hợp.
- Có thể bổ sung kiểm tra Origin, Referer, Fetch Metadata theo thiết kế; các header này không phải chứng chỉ danh tính.
- Không dùng GET để làm thay đổi trạng thái nghiệp vụ.

Trong Spring Security, **GET/HEAD/TRACE/OPTIONS** thường được matcher CSRF mặc định xem là các method không yêu cầu CSRF token; **POST/PUT/PATCH/DELETE** cần token khi CSRF đang bật. Một POST JSON có OPTIONS trước vẫn cần CSRF token hợp lệ ở request POST thực.

## 8. Cấu hình CORS trong Spring Security Servlet

Giả sử API chạy trên Spring MVC/Servlet, frontend **https://app.example.com**, API endpoint nằm dưới **/api/** và sử dụng cookie phiên để xác thực.

Ví dụ cấu hình với Spring Security 6.x:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                // Giữ CSRF protection mặc định.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Điều cần hiểu:

1. **cors(Customizer.withDefaults())** tích hợp xử lý CORS vào security filter chain. CORS cần xử lý trước các bước bảo mật có thể từ chối preflight không có cookie.
2. **allowedOrigins** chỉ có origin chính xác **https://app.example.com**; không bao gồm đường dẫn **/dashboard** hoặc wildcard tùy tiện.
3. **allowedHeaders** bao gồm Content-Type, Authorization và X-CSRF-TOKEN: cho phép request CORS gửi những header cần thiết, nhưng không có nghĩa server bỏ kiểm tra token.
4. **allowedMethods** liệt kê những method API dự kiến nhận qua CORS. Phương thức OPTIONS preflight được bộ xử lý CORS nhận dạng riêng; đây là nơi khai báo **method của request thực**, không phải lời cho phép tùy ý mọi thao tác.
5. **allowCredentials(true)** chỉ thích hợp khi API có mục đích hỗ trợ credentials. Khi bật, không dùng Allow-Origin wildcard cho response có credentials.
6. **maxAge(600)** hướng trình duyệt cache preflight theo chính sách, browser có thể giới hạn thời gian.
7. Đường dẫn **/api/** được đăng ký chính sách CORS; các đường dẫn khác không tự có cùng chính sách.

Cấu hình minh họa giữ **CSRF protection mặc định**, nhưng không cung cấp sẵn endpoint login hoặc cấp CSRF token. Với SPA khác origin dùng cookie/session, cần thiết kế một luồng hợp lệ để frontend nhận CSRF token và gửi lại trong các thao tác thay đổi trạng thái.

### 8.1. Tại sao OPTIONS thường bị 401/403?

Một preflight thường không có session cookie. Nếu nó bị filter yêu cầu login, gateway hoặc HTTP firewall chặn **trước bộ xử lý CORS**, browser không gửi POST thực và có thể hiển thị lỗi CORS.

Khi đó, kiểm tra request có đến đúng **SecurityFilterChain** chứa cấu hình CORS không. Nếu ứng dụng có nhiều filter chain, reverse proxy hoặc gateway, phải kiểm tra từng tầng để xác định nơi trả 401/403.

Không sửa lỗi preflight bằng cách **tắt CSRF toàn bộ ứng dụng**. CSRF cần được kiểm tra trên **request POST thực**, còn OPTIONS preflight cần được đánh giá theo chính sách CORS.

### 8.2. Một method có thể được CORS cho phép nhưng bị Spring Security từ chối

Ví dụ browser có thể nhận OPTIONS 204 cho POST /api/orders, sau đó gửi POST kèm cookie nhưng CSRF token sai. Spring Security trả 403. Đây là kết quả phù hợp nếu yêu cầu thực không có bằng chứng CSRF hợp lệ.

Tương tự, một người dùng đã gửi token CSRF đúng nhưng không được phép cập nhật đơn của người khác vẫn phải bị từ chối do authorization. **CORS không cấp quyền truy cập nghiệp vụ.**

## 9. Cấu hình CORS trong Spring Security Reactive/WebFlux

Với WebFlux, dùng **ServerHttpSecurity** và các lớp CORS thuộc **gói reactive**:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveCorsSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                // Giữ CSRF protection mặc định.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trình duyệt dùng cùng quy tắc CORS/preflight cho frontend dù backend là Servlet hay WebFlux. Điểm khác nhau là API cấu hình, chuỗi xử lý bảo mật và hệ thống session:

- Servlet dùng **SecurityFilterChain**, **HttpSecurity** và các lớp CORS thuộc Spring Web servlet.
- WebFlux dùng **SecurityWebFilterChain**, **ServerHttpSecurity** và các lớp CORS thuộc **org.springframework.web.cors.reactive**.
- Không trộn các lớp **CorsConfigurationSource/UrlBasedCorsConfigurationSource** của hai stack.
- Với ứng dụng session/cookie trên WebFlux, phải có luồng cấp và kiểm tra CSRF token tương thích **WebSession** và frontend.
- Preflight là vấn đề phía browser/CORS, **không phải kết quả của reactive hay blocking backend**.

Các ví dụ Servlet và WebFlux là hai lựa chọn **cho hai stack riêng**, không dùng đồng thời trong cùng một ứng dụng chỉ để có CORS.

## 10. Kiểm thử OPTIONS và request thực tế

Bộ kiểm thử nên có cả trường hợp được phép và bị từ chối, kiểm tra method, Origin, headers và việc server có xử lý thao tác nghiệp vụ hay không.

### 10.1. Xem preflight qua curl

Trong môi trường thử nghiệm do bạn kiểm soát, có API tại **http://localhost:8080**, hãy mô phỏng request OPTIONS do frontend origin hợp lệ tạo:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Quan sát status và các header:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
~~~

Ví dụ header là chính sách được kỳ vọng nếu cấu hình tương ứng đã được áp dụng. Phản hồi thực có thể khác về thứ tự, chữ hoa/thường, cách liệt kê hoặc status.

Thử origin không được phép:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://untrusted.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

**Kết quả kỳ vọng:** API **không cấp quyền CORS** cho untrusted.test. Nó có thể trả 403 hoặc phản hồi từ chối khác tùy cấu hình; không cần yêu cầu mọi hệ thống phải cùng một mã lỗi.

Thử method/header chưa được phép:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: TRACE" \
  -H "Access-Control-Request-Headers: x-unapproved-header"
~~~

**curl không thực thi SOP hoặc CORS giống browser.** Nó chỉ giúp kiểm tra server trả gì. Để xác nhận JavaScript có thực sự đọc được response, phải thử bằng browser với Origin thực.

### 10.2. So sánh text/plain và application/json trong DevTools

Chạy từ trang thử nghiệm **https://app.example.com**:

~~~javascript
async function testRequest(contentType, body) {
  try {
    const response = await fetch("https://api.example.com/api/test", {
      method: "POST",
      headers: { "Content-Type": contentType },
      body
    });
    console.log(contentType, response.status, await response.text());
  } catch (error) {
    console.error(contentType, error);
  }
}

await testRequest("text/plain", "hello");
await testRequest("application/json", JSON.stringify({ hello: "world" }));
~~~

Đây là ví dụ cho **endpoint thử nghiệm**, không gọi vào endpoint production có thể làm thay đổi trạng thái. Trong **DevTools → Network**, xem:

1. POST text/plain có gửi ngay hay xuất hiện OPTIONS? Nếu có OPTIONS, kiểm tra các yếu tố khác của request.
2. POST application/json có OPTIONS không, với **Access-Control-Request-Headers: content-type**?
3. OPTIONS được trả lời bằng status và các CORS header nào?
4. POST thực có xuất hiện không?
5. Response POST thực có **Access-Control-Allow-Origin** hợp lệ không?
6. Có redirect hoặc policy **CSP connect-src / Mixed Content** đang chặn kết nối không?

Cần kiểm tra **Network và Console cùng nhau**. Thông báo “CORS error” không luôn nói rõ server đã nhận request thực hay chưa.

### 10.3. Kiểm tra request có credentials

Frontend cross-origin dùng cookie:

~~~javascript
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Trong **DevTools → Application/Storage → Cookies**, kiểm tra cookie của host API đã được lưu chưa. Trong **Network → Cookies/Request Headers**, kiểm tra request **thực** có Cookie header không.

Nếu OPTIONS không có cookie mà POST thực có cookie, đó là hành vi bình thường. Nếu POST thiếu cookie, kiểm tra Domain, Path, Secure, SameSite, credentials mode và chính sách cookie trình duyệt. Nếu POST có cookie nhưng trả 403, kiểm tra CSRF token và authorization.

### 10.4. Ma trận kiểm thử

| Trường hợp | Hành vi CORS dự kiến | Điều phải kiểm tra thêm |
| --- | --- | --- |
| GET cross-origin, chỉ header safelisted | Thường không preflight | Actual response phải có CORS phù hợp để script đọc. |
| POST text/plain | Thường không preflight | Server vẫn phải kiểm tra CSRF với session/cookie. |
| POST application/x-www-form-urlencoded | Thường không preflight | Không xử lý giao dịch nhạy cảm khi thiếu CSRF token. |
| POST FormData multipart/form-data | Thường không preflight | Boundary, kích thước file, quyền và CSRF. |
| POST application/json | Thường preflight | Allow-Headers cho phép Content-Type. |
| POST + X-CSRF-TOKEN | Thường preflight | Allow-Headers và giá trị token thực. |
| GET + Authorization | Thường preflight | Authorization được phép và token thực được xác thực. |
| PUT/PATCH/DELETE cross-origin | Thường preflight | Method được phép nhưng vẫn phải qua CSRF và quyền. |
| Origin không nằm trong allowlist | Không được CORS cấp quyền | Không tự phản chiếu Origin và bật credentials. |
| Preflight 204, POST 403 | OPTIONS đạt; POST bị từ chối | Phân biệt CSRF và authorization. |
| Preflight 204, POST 200, JavaScript vẫn lỗi | Actual response không đạt CORS | Kiểm tra Allow-Origin/Allow-Credentials của POST. |
| Một số request sau không thấy OPTIONS | Có thể cache kết quả preflight | Kiểm tra Max-Age, browser và cache state. |

## 11. Chẩn đoán các lỗi triển khai thường gặp

### 11.1. OPTIONS trả 401 hoặc 403

**Triệu chứng:** Browser hiển thị lỗi CORS, Network chỉ thấy OPTIONS 401/403 mà không thấy POST.

**Khả năng:** Preflight bị authentication filter, reverse proxy, gateway hoặc HTTP firewall chặn, hoặc CORS policy không cho phép Origin/method/header.

**Xử lý:** Kiểm tra nơi trả status, Origin, Access-Control-Request-Method/Headers, đường dẫn và thứ tự xử lý CORS. Cho preflight hợp lệ được bộ xử lý CORS đánh giá trước khi hệ thống yêu cầu xác thực cho request nghiệp vụ.

### 11.2. OPTIONS thành công, POST bị 403

**Triệu chứng:** OPTIONS 204 có header đúng, POST đã gửi nhưng trả 403.

**Khả năng:** CSRF token sai/thiếu, session không hợp lệ, user không có quyền hoặc logic bảo mật khác từ chối.

**Xử lý:** Xem log Spring Security, cách cấp và gửi token, session, quyền đối với tài nguyên. **Không mở CORS bừa bãi hoặc tắt CSRF** để xử lý một 403 thuộc tầng authorization/CSRF.

### 11.3. POST thành công nhưng JavaScript bị chặn đọc

**Triệu chứng:** Network thấy POST HTTP 200/201, server ghi nhận đơn đã tạo nhưng fetch báo lỗi CORS.

**Khả năng:** Response thực thiếu/sai Access-Control-Allow-Origin, thiếu Allow-Credentials khi dùng credentials, hoặc proxy làm mất/nhân đôi header.

**Xử lý:** Kiểm tra **response của POST**, không chỉ OPTIONS. Đừng retry POST tạo đơn hoặc thanh toán ngay, vì request có thể đã được server xử lý. Xác nhận trạng thái nghiệp vụ và cân nhắc idempotency khi phù hợp.

### 11.4. text/plain gửi được, application/json thất bại

**Triệu chứng:** POST text/plain gửi trực tiếp, đổi sang JSON thì browser gửi OPTIONS và chặn.

**Khả năng:** Allowed-Headers chưa có Content-Type, OPTIONS bị filter chặn, hoặc policy path/origin sai.

**Xử lý:** Điều chỉnh CORS và thứ tự preflight cho API JSON. Không biến toàn bộ JSON thành text/plain chỉ để bỏ OPTIONS; server nên kiểm tra Content-Type đúng hợp đồng.

### 11.5. GET có Authorization vẫn phát sinh OPTIONS

**Triệu chứng:** GET API có Bearer token, nhưng browser gửi OPTIONS dù không có body.

**Giải thích:** Authorization không thuộc CORS safelist, nên phải preflight. Cho phép Authorization trong CORS theo phạm vi origin hợp lệ, đồng thời **xác thực token trong request GET thực**.

### 11.6. Lỗi chỉ xuất hiện sau redirect

Một API có thể redirect 301/302/307/308 đến URL thuộc origin khác. CORS policy của đích mới, method thực tế và khả năng redirect trong luồng preflight có thể gây lỗi.

**Xử lý:** Quan sát **toàn bộ redirect chain** trong DevTools. Kiểm tra URL cuối, CORS headers của từng bước, HTTPS/HSTS và cấu hình proxy. Không suy ra URL đầu tiên hợp lệ nghĩa là mọi URL sau redirect hợp lệ.

### 11.7. CSP, Mixed Content hoặc firewall bị nhầm với CORS

- **CSP connect-src** có thể cấm fetch đến đích ngay cả khi API cho phép CORS.
- **Mixed Content** có thể chặn request HTTP từ trang HTTPS.
- **HSTS** có thể làm browser nâng cấp request sang HTTPS.
- **HTTP firewall**, reverse proxy hoặc gateway có thể chặn OPTIONS hoặc một method cụ thể trước khi request đến ứng dụng.

Cần đối chiếu thông báo Console với Network và log từng tầng. Giữ các security headers, HTTP firewall và chính sách HTTPS phù hợp; tránh thay đổi CORS nếu lỗi xuất phát từ tầng khác.

## 12. Bài tập tình huống

### Tình huống A — GET nhận JSON

Frontend gọi GET cross-origin với header request safelisted. API trả Content-Type: application/json. Chỉ vì response là JSON có bắt buộc preflight không?

**Đáp án:** Không. Content-Type response không tự quyết định preflight. JavaScript cần CORS header phù hợp trên response để đọc dữ liệu.

### Tình huống B — POST JSON

Frontend gửi POST application/json tới API khác origin, không có custom header nào khác. Có cần preflight không?

**Đáp án:** Thông thường có, vì Content-Type request application/json không thuộc CORS safelist.

### Tình huống C — POST text/plain có charset

Request POST dùng Content-Type: text/plain;charset=UTF-8, không thêm header lạ. Có chắc cần preflight vì có charset không?

**Đáp án:** Không. Media type essence vẫn là text/plain; nó thường đủ điều kiện safelist khi các giới hạn về header và đặc điểm request khác đều thỏa.

### Tình huống D — GET với Bearer

GET cross-origin có Authorization: Bearer token. Vì GET là safe HTTP method nên không cần preflight?

**Đáp án:** Sai. Authorization không thuộc safelist; request thường có OPTIONS. Safe theo HTTP không đồng nghĩa simple theo CORS.

### Tình huống E — Form POST không qua OPTIONS

Một website ngoài hệ thống tạo form POST tới endpoint thay đổi trạng thái dùng session cookie. Không thấy OPTIONS. Endpoint có an toàn trước CSRF không?

**Đáp án:** Không thể kết luận. Form có thể gửi mà không cần preflight; cookie có thể được gửi tùy SameSite và ngữ cảnh, nên server phải thực thi CSRF protection phù hợp.

### Tình huống F — OPTIONS không có Cookie

OPTIONS trả 401 vì không có session cookie, trong khi frontend sẽ dùng credentials: include cho POST. Có nên yêu cầu frontend tự gắn cookie vào OPTIONS?

**Đáp án:** Không. Browser quản lý preflight; OPTIONS thường không có session cookie. Xử lý CORS trước các bước yêu cầu xác thực, còn POST thực vẫn chịu auth/CSRF/quyền.

### Tình huống G — Preflight đạt, POST thiếu quyền

OPTIONS trả 204 và CORS header đúng, POST có cookie và CSRF token hợp lệ, nhưng user cố chỉnh đơn của người khác. Có xử lý thao tác không?

**Đáp án:** Không. CSRF token và CORS không cấp quyền sở hữu tài nguyên; server phải từ chối theo authorization.

### Tình huống H — Wildcard và credentials

API trả Allow-Origin: * đồng thời Allow-Credentials: true. Frontend dùng credentials: include. JavaScript có đọc response được không?

**Đáp án:** Không. CORS có credentials yêu cầu origin phù hợp, không chấp nhận Allow-Origin wildcard.

### Tình huống I — FormData bị lỗi multipart

Frontend tự đặt Content-Type multipart/form-data nhưng không khai báo boundary, gửi FormData. API có thể gặp lỗi gì?

**Đáp án:** Server có thể không phân tích được multipart. Nên để browser tạo Content-Type/boundary; vẫn kiểm tra file, quyền và CSRF.

### Tình huống J — Cache preflight

Lần gọi JSON đầu xuất hiện OPTIONS, các lần sau không thấy. Có chắc browser không còn kiểm tra CORS?

**Đáp án:** Không. Kết quả preflight có thể được cache theo Access-Control-Max-Age và giới hạn browser; actual response vẫn phải đáp ứng CORS.

### Tình huống K — Đổi JSON thành text/plain để tránh OPTIONS

Ứng dụng gửi body JSON nhưng đặt Content-Type: text/plain và server chấp nhận cả hai. Đây có phải thiết kế bảo mật tốt?

**Đáp án:** Không. Nó làm hợp đồng media type mơ hồ và có thể cho request không cần preflight kích hoạt logic nhạy cảm. Server cần giới hạn Content-Type và kiểm tra CSRF/permission thực sự.

### Tình huống L — Preflight đạt nhưng actual response thiếu Allow-Origin

OPTIONS thành công. POST tạo đơn thành công, nhưng response POST không có CORS header hợp lệ. Frontend có đọc JSON và nên retry ngay không?

**Đáp án:** Browser không cho frontend đọc JSON; không nên retry mù quáng vì đơn có thể đã tạo. Sửa CORS của response thực và kiểm tra trạng thái nghiệp vụ.

## 13. Ghi nhớ

- **Content-Type của request** là yếu tố quan trọng của CORS preflight. **Content-Type response: application/json không tự làm preflight xảy ra**.
- Media type essence thường được safelist: **application/x-www-form-urlencoded**, **multipart/form-data**, **text/plain**, cùng các giới hạn về giá trị header.
- **GET, HEAD và POST** là CORS-safelisted methods thường gặp; **PUT, PATCH, DELETE** và các request dùng **Authorization, X-CSRF-TOKEN** hoặc header tùy chỉnh thường cần preflight.
- **Simple request không đồng nghĩa safe HTTP method** và không bảo đảm chống CSRF; form POST có thể được gửi đến server không qua preflight.
- **OPTIONS preflight** hỏi về **Origin, method, request headers** dự kiến, thường không mang cookie và không chứa body nghiệp vụ.
- Preflight thành công cho phép browser tiếp tục gửi request thực theo CORS, nhưng **request thực vẫn phải qua authentication, authorization, CSRF** và response thực vẫn cần CORS header phù hợp để JavaScript đọc.
- **credentials: include** không vượt qua SameSite/Domain/Path/Secure. Response CORS có credentials không thể dùng Allow-Origin wildcard.
- Với Spring Security **Servlet và WebFlux**, cấu hình origin/method/header cụ thể, xử lý CORS trước những filter có thể chặn preflight, giữ CSRF khi dùng cookie/session.
- Khi chẩn đoán, phân biệt **OPTIONS 401/403**, **POST 403**, **POST thành công nhưng frontend bị chặn đọc**, và các lỗi CSP, Mixed Content, reverse proxy hoặc HTTP firewall.
