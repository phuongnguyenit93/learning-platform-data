# Phân biệt origin, site, hostname và đường dẫn

## Mục tiêu học tập

Khi bảo vệ một ứng dụng Spring, người phát triển thường gặp các từ *origin*, *site*, *hostname*, *domain* và *path*. Các từ này mô tả những phạm vi khác nhau của URL. Nhầm lẫn chúng có thể khiến ta cấu hình CORS quá rộng, hiểu sai phạm vi gửi cookie, tắt CSRF không đúng lý do, hoặc cho rằng hai endpoint nằm ở đường dẫn khác nhau thì đã được trình duyệt cô lập về bảo mật.

Sau bài học, bạn có thể:

1. Tách một URL thành **scheme, hostname, port, path, query và fragment**.
2. So sánh **same-origin**, **same-site** và **same-hostname** bằng ví dụ cụ thể.
3. Giải thích vai trò của **Public Suffix List** trong việc xác định *site*, cùng ảnh hưởng của scheme và port.
4. Phân tích mối liên hệ giữa **Same-Origin Policy, CORS, cookie Domain/Path/SameSite và CSRF**.
5. Phân biệt ranh giới URL của trình duyệt với **phân quyền API bằng Spring Security**.
6. Dùng Java 17 để kiểm tra các thành phần URL và cấu hình Spring Boot/Spring Security một cách có chủ đích.

**Ngữ cảnh:** các khái niệm browser/HTTP hiện đại, Spring MVC chạy trên Servlet, Java 17 và ví dụ Spring Boot 3.x/Spring Security 6.x. Khi đổi stack hoặc phiên bản, hãy đối chiếu API tương ứng; nguyên tắc so sánh URL ở đây không phụ thuộc riêng Spring.

## 1. Bóc tách một URL trước khi bàn về bảo mật

Xét URL:

```text
https://api.shop.example.com:8443/v1/orders/42?view=detail#items
\___/   \__________________/ \__/ \____________/ \_________/ \___/
scheme        hostname      port      path        query     fragment
```

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Chỉ loại giao thức và cách xử lý URL, bao gồm việc dùng HTTPS. |
| Hostname | `api.shop.example.com` | Tên máy chủ trong URL (không chứa scheme, port, path). |
| Port | `8443` | Cổng mà client hướng kết nối tới; HTTP/HTTPS có cổng mặc định nếu không chỉ rõ. |
| Path | `/v1/orders/42` | Đường dẫn tài nguyên được HTTP server/router xử lý. |
| Query | `view=detail` | Thông tin sau `?`; thường dùng làm tham số tìm kiếm hoặc lọc. |
| Fragment | `items` | Phần sau `#` do user agent xử lý; **không được gửi trong HTTP request target** khi thực hiện request HTTP thông thường. |

Một số thuật ngữ liên quan:

- **Host** trong URL thường được dùng gần nghĩa hostname, nhưng không nên nhầm **host** với **authority**. Authority của ví dụ là `api.shop.example.com:8443`, gồm hostname và port (có thể có userinfo trong URL dạng tổng quát; tránh dùng userinfo cho đăng nhập HTTP).
- **Domain name** là tên trong DNS; hostname của URL có thể là DNS name, IP literal hoặc `localhost`. “Domain” còn xuất hiện trong thuộc tính `Domain` của cookie và trong quy tắc public suffix, nên cần nói chính xác ngữ cảnh.
- **Origin** và **site** là hai khái niệm so sánh phạm vi an ninh web, suy ra từ URL; chúng **không** phải đoạn chữ đứng riêng trong địa chỉ như path hay query.
- **Path không bao gồm query/fragment**. `/orders/42?mode=edit` và `/orders/42?mode=view` có cùng path nhưng khác query.
- Trình duyệt và server có thể chuẩn hóa host, cổng mặc định, dấu chấm, percent-encoding và dot segment khác với cách nhìn chuỗi thô. Đừng quyết định quyền truy cập bằng kiểm tra chuỗi URL đơn giản.

Ví dụ `https://app.example.com/a` và `https://app.example.com/b` có hai path khác nhau nhưng thường vẫn cùng **origin**, cùng **site** và cùng hostname.

## 2. Bốn khái niệm cốt lõi

### 2.1. Hostname: tên host mà URL đang chỉ đến

Trong `https://api.example.com:8443/users`, **hostname** là `api.example.com`.

Hostname **không chứa** scheme, port, path, query hoặc fragment. Các subdomain là hostname khác nhau:

- `app.example.com` và `api.example.com`: **khác hostname**.
- `app.example.com:443` và `app.example.com:8443`: **cùng hostname**, khác port.
- `http://app.example.com` và `https://app.example.com`: **cùng hostname**, khác scheme.

DNS có thể ánh xạ nhiều hostname tới cùng IP; ngược lại một hostname có thể trỏ tới nhiều IP. **Cùng IP không tạo ra cùng hostname, cùng origin hay cùng quyền truy cập.**

Hostname không phải bằng chứng danh tính người dùng. Không dùng `Host` header, `X-Forwarded-Host` hoặc hostname trong query để xác định role/ownership. Metadata reverse proxy chỉ được tin khi đến qua những proxy đã cấu hình tin cậy.

### 2.2. Origin: bộ ba scheme + host + effective port

Với một URL HTTP(S) thông thường có *tuple origin*, quy tắc thực dụng là:

```text
origin = (scheme, host, effective-port)
```

**Same-origin** khi cả ba thành phần tương ứng bằng nhau sau khi chuẩn hóa phù hợp. Ví dụ:

- `https://app.example.com/a` và `https://app.example.com/b`: **same-origin**.
- `https://app.example.com` và `https://app.example.com:443`: **same-origin**, vì HTTPS mặc định là port 443.
- `http://app.example.com` và `http://app.example.com:80`: **same-origin**, vì HTTP mặc định là port 80.
- `https://app.example.com` và `https://app.example.com:8443`: **cross-origin**, vì port khác.
- `https://app.example.com` và `https://api.example.com`: **cross-origin**, vì hostname khác.
- `http://app.example.com` và `https://app.example.com`: **cross-origin**, vì scheme khác.

Path, query và fragment **không tham gia** xác định origin. Trong browser, Same-Origin Policy dùng origin làm một trong những ranh giới trọng yếu để giới hạn cách trang web/script truy cập tài nguyên của origin khác.

Có những trường hợp đặc biệt như `file:`, `data:`, sandboxed document, opaque origin và inherited origin. Công thức bộ ba ở trên dành cho **URL HTTP(S) thông thường**; không nên tự dùng nó để mô phỏng toàn bộ thuật toán origin của trình duyệt cho mọi scheme.

### 2.3. Site: scheme + registrable domain (schemeful site)

Trong ngữ cảnh chính sách web hiện đại như `SameSite` cookie, **site** thường được xác định theo *schemeful site*:

```text
site = (scheme, registrable domain)
```

**Registrable domain** được xác định dựa trên **Public Suffix List (PSL)**. Với nhiều tên miền thông thường, đó là *eTLD+1* (effective top-level domain cộng một label do chủ thể đăng ký).

Ví dụ minh họa:

- `app.example.com` và `api.example.com` có registrable domain `example.com`; khi cả hai đều dùng `https`, chúng là **same-site** dù **cross-origin**.
- `example.co.uk` và `shop.example.co.uk` cùng registrable domain `example.co.uk`; không thể đơn giản lấy “hai label cuối”, vì `co.uk` là public suffix.
- `app.example.com` và `app.example.org` thuộc hai registrable domain khác nhau, nên **cross-site**.
- `https://app.example.com` và `http://app.example.com` là **cross-site theo schemeful site**, dù hostname bằng nhau.

**Port không tham gia so sánh site.** Do đó `https://app.example.com:5173` và `https://app.example.com:8443` có thể **same-site** nhưng **cross-origin**.

Site không phải ranh giới phân quyền cho từng API. Hai subdomain cùng site có thể được vận hành bởi hai hệ thống, nhóm phát triển hoặc nhà cung cấp khác nhau; không thể vì *same-site* mà tự động cho phép đọc dữ liệu hoặc cấp quyền admin.

**Điểm cần thận trọng về PSL:** Một số miền dịch vụ lưu trữ cho nhiều khách hàng có quy tắc public suffix đặc biệt. Việc tính site không thể làm an toàn chỉ bằng `host.endsWith("example.com")` hoặc tách hostname theo dấu chấm rồi lấy hai label cuối. Đừng tự viết bộ kiểm tra site để quyết định phân quyền; khi cần thao tác chuẩn web, dùng thuật toán/thư viện có Public Suffix List được cập nhật.

`localhost`, IP literal và một số hostname nội bộ không có registrable domain theo nghĩa tên miền công cộng. Trình duyệt có quy tắc xử lý riêng; khi thử nghiệm local nên ghi rõ scheme/hostname/port và kiểm tra trên trình duyệt đích, đừng tùy tiện coi mọi hostname nội bộ là một site.

### 2.4. Path: đường dẫn tài nguyên trong một origin

Trong `https://app.example.com/admin/users`, **path** là `/admin/users`.

- `/admin/users` và `/api/users` thuộc cùng origin nếu các thành phần scheme/hostname/port bằng nhau.
- Path là đầu vào quan trọng cho router web, static resource handler, reverse proxy và rule `requestMatchers(...)` của Spring Security.
- Path khác nhau **không tạo ra origin mới**, cũng không tự tạo một sandbox JavaScript hay ranh giới xác thực mới.
- Server có thể phân biệt chữ hoa/chữ thường của path và cách xử lý dấu slash; cấu hình proxy, servlet container và routing framework có thể ảnh hưởng kết quả khớp.
- Query và fragment không phải thành phần để Spring Security tự động suy luận URL authorization theo cách ghép chuỗi thủ công.

Ví dụ người dùng đã đăng nhập vào `/shop` không được mặc nhiên phép gọi `/admin` chỉ vì hai path cùng hostname. Quyền truy cập vẫn do **chính sách server** quyết định.

## 3. Bảng so sánh nhanh: cùng gì, khác gì?

Chọn URL gốc `https://app.example.com:443/dashboard`. Với cách hiểu HTTP(S) thông thường, so sánh:

| URL cần so sánh với URL gốc | Cùng hostname? | Same-origin? | Same-site? | Lý do |
| --- | :---: | :---: | :---: | --- |
| `https://app.example.com/profile` | Có | **Có** | **Có** | Chỉ đổi path; port mặc định 443. |
| `https://app.example.com:8443/profile` | Có | Không | **Có** | Khác port; site bỏ qua port. |
| `https://api.example.com/profile` | Không | Không | **Có** | Subdomain khác nhưng cùng `https` và `example.com`. |
| `https://example.com/profile` | Không | Không | **Có** | Host khác, cùng registrable domain `example.com`. |
| `http://app.example.com/profile` | Có | Không | Không | Khác scheme; schemeful site cũng khác. |
| `https://app.example.org/profile` | Không | Không | Không | Registrable domain khác. |
| `https://evil-example.com/profile` | Không | Không | Không | Chuỗi có chữ `example` không tạo cùng site. |
| `https://app.example.com:443/dashboard?tab=2#main` | Có | **Có** | **Có** | Query và fragment không tham gia hai phép so sánh. |

Hình dung theo quan hệ bao hàm trong bối cảnh HTTP(S) bình thường:

```text
Cùng origin  =>  cùng hostname, cùng scheme, cùng effective port
             =>  cùng site theo schemeful site

Cùng site    =>  CHƯA CHẮC cùng origin
Cùng hostname=>  CHƯA CHẮC cùng origin hoặc same-site nếu scheme khác
Cùng path    =>  CHƯA CHẮC cùng hostname, origin hay site
```

Không có quan hệ “cùng hostname thì an toàn hơn” theo nghĩa cấp quyền người dùng. Các phép so sánh phục vụ **những chính sách browser khác nhau**.

## 4. Origin trong Same-Origin Policy và CORS

### 4.1. Same-Origin Policy (SOP) kiểm soát khả năng truy cập qua browser

Giả sử một trang chạy tại:

```text
https://app.example.com
```

Trang đó gọi JavaScript:

```javascript
fetch("https://api.example.com/api/me");
```

Đây là **cross-origin request**, dù hai host cùng `example.com` và cùng HTTPS. Browser áp dụng chính sách cross-origin khi JavaScript muốn đọc response; API cần CORS phù hợp nếu muốn cho phép truy cập từ origin này.

SOP **không** có nghĩa browser tuyệt đối không gửi được bất kỳ request cross-origin nào. Link, navigation, form submission, hình ảnh và một số tài nguyên được phép tải/gửi theo quy tắc riêng. Chính vì có những request cross-origin **được gửi**, bảo vệ CSRF vẫn có vai trò với cơ chế xác thực dựa trên cookie tự động đính kèm.

### 4.2. CORS so sánh *origin*, không so sánh *site*

Khi browser gửi `Origin`, giá trị có dạng ví dụ:

```http
Origin: https://app.example.com
```

Thông thường giá trị origin không chứa path, query hay fragment. API có thể cho phép origin cụ thể:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Với request có credentials như cookie và cơ chế browser phù hợp, cần cấu hình tương ứng, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Khi gửi credentials, không thể dùng `Access-Control-Allow-Origin: *` để browser cấp quyền đọc response có credentials. CORS phải được cấu hình bằng allowlist origin thực sự cần thiết. Không phản chiếu mọi giá trị `Origin` vào `Access-Control-Allow-Origin` mà thiếu kiểm tra, vì như vậy có thể mở quyền đọc cho những website ngoài dự kiến.

**Một số điểm dễ nhầm:**

- `https://app.example.com` và `https://api.example.com`: **same-site nhưng vẫn cross-origin, cần CORS** nếu script ở app muốn đọc response từ API.
- `http://localhost:5173` và `http://localhost:8080`: khác port nên **cross-origin**, dù cùng hostname và thường cùng site trong bối cảnh local.
- Một request có header `Authorization` do JavaScript chủ động đặt thường kích hoạt **CORS preflight** nếu là cross-origin; browser gửi `OPTIONS` trước để hỏi server các method/header được phép.
- CORS là quy tắc được browser thực thi khi script truy cập response. `curl` hoặc backend-to-backend client **không bị CORS dùng làm cơ chế phân quyền**.
- Có CORS hợp lệ **không** đồng nghĩa người dùng đã đăng nhập hay có quyền xem tài nguyên. API vẫn cần authentication và authorization của riêng nó.

### 4.3. Vì sao port rất quan trọng khi phát triển local?

Một ứng dụng React/Vite ở `http://localhost:5173` gọi API Boot ở `http://localhost:8080`:

```text
Frontend: http://localhost:5173
Backend : http://localhost:8080
            \________________/
               cùng hostname
```

Đây là **cross-origin vì port 5173 khác 8080**. Kể cả khi bạn chuyển frontend sang `http://127.0.0.1:5173`, hostname lại khác `localhost`. Hãy khai báo **đúng origin đầy đủ** của browser; chuỗi `localhost`, `127.0.0.1`, HTTP/HTTPS và port đều cần được xem xét đúng phạm vi.

Ví dụ frontend gửi request:

```javascript
const result = await fetch("http://localhost:8080/api/me", {
  headers: { Authorization: "Basic " + credentialsBase64 },
  credentials: "include"
});
```

Đây là **mã minh họa cho cơ chế CORS**, không phải cách lưu password trong frontend. Trong ứng dụng thực, không hard-code credentials trong JavaScript hoặc mã nguồn công khai. `credentials: "include"` là lựa chọn cần thiết khi muốn browser gửi một số loại credentials trên cross-origin request; nó không tự tạo quyền và không vượt qua quy định cookie SameSite hoặc chính sách browser về third-party cookies.

## 5. Site, cookie Domain/Path/SameSite và CSRF

### 5.1. Cookie không được gửi chỉ dựa trên same-origin

Browser quyết định có gửi cookie trong một request dựa vào nhiều thuộc tính: host/domain, path, Secure, SameSite, thời hạn, partitioning khi áp dụng, loại request và chính sách riêng tư.

Ví dụ server trả:

```http
Set-Cookie: SESSION_ID=opaque-value; Secure; HttpOnly; Path=/; SameSite=Lax
```

Giải thích:

- **Không có `Domain`**: cookie là **host-only**, thường chỉ gửi lại cho hostname đã đặt cookie, không tự mở sang toàn bộ subdomain.
- **`Domain=example.com`** (nếu hợp lệ): có thể cho phép gửi cookie tới `example.com` và các subdomain phù hợp; không phải cách an toàn mặc định nếu không cần chia sẻ.
- **`Path=/`**: cookie có thể được gửi cho các request path phù hợp trên phạm vi host/domain được phép; `Path=/admin` thường thu hẹp việc *gửi* cookie theo path nhưng **không tạo ranh giới bảo mật tuyệt đối giữa các path**.
- **`Secure`**: cookie được giới hạn gửi trong ngữ cảnh kết nối an toàn theo quy tắc browser; nên dùng với HTTPS ở production. Có một số ngoại lệ/hành vi đặc biệt cho localhost trong trình duyệt.
- **`HttpOnly`**: chặn đọc trực tiếp qua `document.cookie`, nhưng không ngăn browser tự gửi cookie kèm request và không thay thế phòng chống XSS.
- **`SameSite=Lax`**: hạn chế một số tình huống gửi cookie cross-site, nhưng vẫn có ngoại lệ, chẳng hạn navigation top-level dùng phương thức an toàn. Không xem Lax là bảo vệ CSRF đầy đủ cho mọi luồng.
- **`SameSite=Strict`**: hạn chế hơn với bối cảnh cross-site; có thể ảnh hưởng các luồng chuyển hướng/đăng nhập.
- **`SameSite=None; Secure`**: cấu hình hỗ trợ những tình huống cookie cần gửi trong bối cảnh cross-site theo chuẩn hiện đại; browser hoặc chính sách third-party cookie vẫn có thể chặn.

**Phân biệt “được browser gửi cookie” với “JavaScript được đọc response”:** cookie được xét bởi Domain/Path/SameSite/Secure và browser credentials mode; quyền đọc cross-origin response lại chịu SOP/CORS. Chúng không phải cùng một phép kiểm tra.

### 5.2. Cookie Domain có thể bao phủ nhiều origin nhưng không nên chia sẻ bừa bãi

Ví dụ:

```text
https://app.example.com
https://api.example.com
https://blog.example.com
```

Ba hostname trên có thể **same-site** nhưng là **ba origin** khác nhau. Một cookie có `Domain=example.com` có phạm vi rộng hơn cookie host-only tại `api.example.com`. Nếu một subdomain bị kiểm soát trái phép, cấu hình cookie domain rộng có thể tăng bề mặt rủi ro. Vì vậy ưu tiên host-only session cookie nếu không có nhu cầu chia sẻ thực sự.

Khi phù hợp, tiền tố cookie `__Host-` được các browser hỗ trợ dùng để bắt buộc một số ràng buộc quan trọng: `Secure`, `Path=/` và **không có `Domain`**. Đây là cách giảm nguy cơ cấu hình cookie vượt host ngoài ý muốn. Tên cookie/prefix không thay thế session management, HTTPS hay chống XSS/CSRF.

Không thể dùng `Domain=co.uk` hay các public suffix khác để chia sẻ cookie với mọi site; browser thực thi quy tắc public suffix. Điều đó minh họa vì sao PSL quan trọng hơn cách tách hostname thủ công.

### 5.3. Same-site không đồng nghĩa same-origin, càng không đồng nghĩa đáng tin cậy

Một trang ở `https://blog.example.com` và API `https://api.example.com` có thể **same-site**. Nhưng chúng là **cross-origin**; browser vẫn áp dụng CORS để giới hạn đọc response từ JavaScript.

Nếu một subdomain bị chiếm quyền hoặc có nội dung do người dùng tùy ý đăng lên, request đến API ở cùng site vẫn có thể mang cookie tùy thuộc vào thuộc tính cookie và browser. **SameSite cookie không đủ để quyết định ai được phép thực hiện thao tác**; API nên kiểm tra CSRF với những luồng dễ bị tấn công, cùng quyền của người dùng tại server.

### 5.4. CORS không phải cơ chế chống CSRF

Hãy tách mục tiêu:

| Câu hỏi | Cơ chế liên quan |
| --- | --- |
| Script ở origin A có được **đọc response** từ origin B? | **Same-Origin Policy và CORS**. |
| Cookie phiên có được **gửi** trong request hay không? | Cookie host/domain/path, Secure, SameSite, browser credentials mode và các chính sách browser. |
| Một request thay đổi trạng thái có thật sự xuất phát từ hành động có ý định của người dùng? | **CSRF protection**, kết hợp với kiến trúc xác thực và các lớp khác. |
| User đã đăng nhập có quyền đổi số dư của tài khoản X? | **Server-side authorization** theo user, resource, tenant và nghiệp vụ. |

Ví dụ form từ website khác có thể gửi request `POST` đến ứng dụng nếu browser cho phép. Việc attacker **không đọc được response** không có nghĩa request không gây tác động. Với session cookie tự động đính kèm, cần đánh giá rủi ro CSRF. Spring Security Servlet thường bật CSRF protection mặc định cho các phương thức HTTP thay đổi trạng thái. Khi làm API stateless, chỉ điều chỉnh CSRF dựa trên cách credentials thực sự được gửi, không dựa riêng vào câu “đã cấu hình CORS”.

## 6. Spring Security xét path khi phân quyền, CORS xét origin khi browser truy cập

Giả sử API có ba nhóm route:

```text
/public/**   : cho phép truy cập công khai
/api/**      : cần xác thực
/admin/**    : cần quyền ADMIN
```

Đây là chính sách **đường dẫn và quyền người dùng**. Nó khác hoàn toàn với yêu cầu chỉ cho trang frontend ở `http://localhost:5173` đọc response cross-origin từ backend ở `http://localhost:8080`.

| Tình huống | Cơ chế liên quan | Suy luận đúng |
| --- | --- | --- |
| `GET /public/ping` trên API | Spring Security URL authorization | Có thể `permitAll()`. |
| `GET /api/me` không có credentials | Spring Security authentication | Bị từ chối/challenge theo cơ chế đăng nhập. |
| `GET /admin/reports` với USER thường | Spring Security authorization | Không có quyền ADMIN dù cùng origin/path prefix khác. |
| JS trên `http://localhost:5173` đọc `http://localhost:8080/api/me` | Browser CORS | Cần CORS cho đúng **origin** frontend và vẫn cần đăng nhập. |
| JS trên `http://localhost:3000` gọi cùng API | Browser CORS | Nếu origin không trong allowlist, browser không cấp quyền đọc response theo CORS; server vẫn cần bảo vệ API. |
| Hai trang `/a` và `/b` cùng hostname/scheme/port | Same-Origin Policy | Path khác không tạo origin riêng. |

Trong Spring Security, thứ tự matcher có ý nghĩa: các rule được xét theo thứ tự; rule tổng quát quá sớm có thể khiến rule cụ thể phía sau không được xét. `requestMatchers("/admin/**").hasRole("ADMIN")` là rule cho **HTTP request path** tại server, không phải cách định nghĩa browser origin. Ngược lại, CORS origin `http://localhost:5173` không nên viết thành `requestMatchers(...)`.

## 7. Thực hành A — Java 17 phân tích URL và so sánh origin

Để kiểm tra hiểu biết, ta viết chương trình Java **độc lập, không cần thư viện ngoài**. Nó chỉ xử lý các URL HTTP/HTTPS dạng tuyệt đối có hostname hợp lệ; mục đích minh họa tuple origin, **không thay thế thuật toán origin/site đầy đủ của browser**.

Tạo file `UrlOriginDemo.java`:

```java
import java.net.URI;
import java.util.Locale;
import java.util.Objects;

public class UrlOriginDemo {

    static int effectivePort(URI uri) {
        if (uri.getPort() >= 0) {
            return uri.getPort();
        }
        return switch (uri.getScheme().toLowerCase(Locale.ROOT)) {
            case "http" -> 80;
            case "https" -> 443;
            default -> throw new IllegalArgumentException("Only HTTP(S)");
        };
    }

    static boolean sameOrigin(URI a, URI b) {
        Objects.requireNonNull(a.getHost());
        Objects.requireNonNull(b.getHost());
        return a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b);
    }

    public static void main(String[] args) {
        URI base = URI.create("https://app.example.com/home");
        URI pathChanged = URI.create("https://app.example.com/settings?tab=1");
        URI explicitDefault = URI.create("https://app.example.com:443/anything");
        URI portChanged = URI.create("https://app.example.com:8443/home");
        URI subdomainChanged = URI.create("https://api.example.com/home");
        URI schemeChanged = URI.create("http://app.example.com/home");

        System.out.println("path changed: " + sameOrigin(base, pathChanged));
        System.out.println("explicit :443: " + sameOrigin(base, explicitDefault));
        System.out.println("port changed: " + sameOrigin(base, portChanged));
        System.out.println("subdomain changed: " + sameOrigin(base, subdomainChanged));
        System.out.println("scheme changed: " + sameOrigin(base, schemeChanged));

        System.out.println("hostname: " + base.getHost());
        System.out.println("path: " + pathChanged.getPath());
        System.out.println("query: " + pathChanged.getQuery());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac UrlOriginDemo.java
java UrlOriginDemo
```

**Stdout chính xác**:

```text
path changed: true
explicit :443: true
port changed: false
subdomain changed: false
scheme changed: false
hostname: app.example.com
path: /settings
query: tab=1
```

Từ ví dụ:

- `getHost()` giúp đọc hostname; `getPort()` có thể trả `-1` khi URL không ghi port, nên code quy đổi cổng mặc định cho HTTP/HTTPS.
- Đổi path hoặc query không đổi origin.
- Đổi port, hostname hoặc scheme làm đổi origin.
- **Không** có hàm `sameSite()` viết bằng vài dòng, vì Java `URI` không tự cung cấp Public Suffix List/thuật toán schemeful site của browser. Không suy ra site bằng cách lấy hai phần cuối hostname.
- Code được giới hạn có chủ đích cho các URI hợp lệ như trong ví dụ. Với dữ liệu tùy ý, còn phải validate scheme, host, URL parsing, normalization và các trường hợp opaque/IDN/IPv6 theo nhu cầu; không tái sử dụng hàm này như một security policy production.

## 8. Thực hành B — Spring Boot 3.x: tách CORS origin khỏi quyền truy cập theo path

Bài lab sau chạy một API tại `http://localhost:8080`, có các endpoint `/public/ping` và `/api/me`. CORS chỉ cho phép frontend origin `http://localhost:5173` truy cập API bằng browser; endpoint `/api/me` vẫn yêu cầu xác thực HTTP Basic. Các endpoint khác bị từ chối theo rule. Đây là lab **GET-only** để làm rõ origin và path; không phải thiết kế đăng nhập production.

### 8.1. Tạo cấu trúc dự án

```text
origin-path-lab/
├── pom.xml
└── src/main/java/com/example/originpath/
    ├── LabApplication.java
    ├── WebSecurityConfig.java
    └── DemoController.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>origin-path-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

Spring Boot quản lý các phiên bản dependency tương thích trong BOM. Version trên là một điểm minh họa của dòng Boot 3.x; khi dùng dự án thật hãy chọn bản vá đang được hỗ trợ.

### 8.3. `LabApplication.java`

```java
package com.example.originpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LabApplication.class, args);
    }
}
```

### 8.4. `WebSecurityConfig.java`

```java
package com.example.originpath;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.webbuilders.WebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of("Authorization"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-secret"))
                .roles("USER")
                .build()
        );
    }
}
```

**Giải thích từng cơ chế:**

1. `.cors(Customizer.withDefaults())` tích hợp xử lý CORS với Spring Security, để các CORS preflight hợp lệ được xử lý trước logic xác thực thông thường. Preflight của browser thường không chứa cookie đăng nhập, nên cần CORS ở vị trí thích hợp trong filter chain.
2. `cors.setAllowedOrigins(...)` khai báo **origin đầy đủ** của frontend, gồm scheme, hostname và port; không khai báo path, không dùng một suffix domain tự suy diễn.
3. `source.registerCorsConfiguration("/api/**", cors)` chỉ định **những path phía server** sử dụng CORS policy này. Nó không có nghĩa `/api/**` là một origin.
4. `cors.setAllowCredentials(true)` cho phép browser cân nhắc đọc response có credentials khi những điều kiện khác phù hợp. Nó không làm cookie tự động vượt SameSite/Path/Secure hay tạo session đăng nhập.
5. `.requestMatchers("/public/**").permitAll()` cho phép route công khai; `.requestMatchers("/api/**").authenticated()` yêu cầu người gọi đăng nhập; `.anyRequest().denyAll()` chặn các route chưa định nghĩa trong policy.
6. Spring Security hỗ trợ CSRF theo mặc định cho các request cần bảo vệ. Lab này chỉ khai báo GET, **không tắt CSRF**; khi mở thêm API POST/PUT/DELETE phải thiết kế phù hợp với kiểu xác thực và CSRF threat model.
7. `InMemoryUserDetailsManager` và credentials minh họa phục vụ chạy local. Trong hệ thống thật, dùng identity provider, secret handling, HTTPS và chính sách session/token phù hợp.

Để tránh nhầm, **`setAllowedOrigins` kiểm tra nguồn trang web gọi API qua browser**, còn **`authenticated()` kiểm tra danh tính người dùng gọi endpoint**. Một request từ origin được CORS cho phép nhưng không đăng nhập vẫn không truy cập được `/api/me`.

### 8.5. `DemoController.java`

```java
package com.example.originpath;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }
}
```

Hai `@GetMapping` là **hai đường dẫn trong cùng origin** của backend. Spring MVC ánh xạ path tới controller; Spring Security quyết định từng đường dẫn có cần xác thực không.

### 8.6. Chạy thử với curl

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Trên macOS/Linux gọi `curl`; trên Windows PowerShell ưu tiên `curl.exe` nếu `curl` là alias. Các lệnh sau dùng cú pháp curl chuẩn:

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/me

curl -i -u student:demo-secret http://localhost:8080/api/me

curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"

curl -i -u student:demo-secret http://localhost:8080/api/me \
  -H "Origin: http://localhost:5173"

curl -i -u student:demo-secret http://localhost:8080/api/me \
  -H "Origin: http://localhost:3000"
```

**Kết quả kỳ vọng với đúng cấu hình:**

| Request | Kết quả đáng chú ý |
| --- | --- |
| `GET /public/ping` | `200 OK`, body `pong`. |
| `GET /api/me` không credentials | `401 Unauthorized` với HTTP Basic challenge. |
| `GET /api/me` với `student:demo-secret` | `200 OK`; JSON `{"username":"student"}`. |
| `OPTIONS` preflight từ `http://localhost:5173` với header `authorization` | Được xử lý theo CORS policy; response cho phép origin, method và header tương ứng. |
| `GET /api/me` có credentials hợp lệ và `Origin: http://localhost:5173` | `200` với CORS allow-origin tương ứng, thường thêm `Access-Control-Allow-Credentials: true`. |
| `GET /api/me` với `Origin: http://localhost:3000` | Không nằm trong allowlist; CORS filter có thể từ chối với `403 Invalid CORS request` trong cấu hình này. |

Đừng đánh đồng việc lệnh curl in ra response với việc JavaScript browser được đọc response. **curl không thi hành Same-Origin Policy hoặc CORS.** Muốn kiểm tra CORS thực sự, mở trang ở origin `http://localhost:5173` và quan sát Network/Console của browser, bao gồm preflight. Nếu chưa có frontend ở port đó, preflight curl vẫn đủ để đọc header máy chủ, nhưng không thay thế kiểm chứng trên browser.

Tài khoản/mật khẩu trong bài chỉ để chạy local; không đưa credentials demo vào SPA public hay dùng Basic không có HTTPS trong sản phẩm thật.

## 9. Các trường hợp khó hơn: proxy, host header, URL encoding và nhiều domain

### 9.1. Reverse proxy có thể khiến origin bên ngoài khác URL nội bộ

Một ứng dụng Boot có thể chạy nội bộ ở `http://localhost:8080` nhưng được người dùng truy cập qua `https://api.example.com` sau load balancer. **Origin mà browser thấy** là URL bên ngoài, không phải socket nội bộ giữa proxy và app.

Nếu ứng dụng tạo redirect, cookie hoặc absolute URL dựa trên `X-Forwarded-Proto`/`Forwarded`, chỉ nên chấp nhận các header đó từ **proxy tin cậy, cấu hình rõ ràng**. Client Internet có thể tự gửi header giả nếu proxy không loại bỏ/chỉnh sửa. Không dùng header tự xưng từ browser làm chứng cứ để bỏ qua authorization.

### 9.2. Hostname giống một phần chuỗi không có nghĩa cùng domain

Ví dụ các URL:

```text
https://app.example.com/
https://app.example.com.evil.test/
https://evil-example.com/
https://app.example.com@evil.test/
```

Trong URL cuối, phần trước `@` là **userinfo**, hostname thực là `evil.test`, không phải `app.example.com`. Kiểm tra kiểu `url.startsWith("https://app.example.com")` có thể bị đánh lừa. Với bất kỳ quyết định whitelist đích network hoặc callback, phải parse URL bằng parser chuẩn, xác minh scheme/host/port và chính sách redirect/đích kết nối; khi cần bảo vệ outbound HTTP còn phải kiểm soát DNS resolution, IP đích và egress để tránh SSRF.

Cũng không dùng `host.endsWith("example.com")` để nhận diện subdomain hợp lệ vì `notexample.com` sẽ khớp chuỗi. Nếu cần allowlist host, so sánh hostname canonical chính xác hoặc ranh giới dấu chấm, có chính sách riêng cho subdomain, IDN và PSL.

### 9.3. Path matching không nên phụ thuộc vào chuỗi chưa chuẩn hóa

Những chuỗi có dấu `..`, slash mã hóa `%2F`, dấu chấm được mã hóa hoặc nhiều slash có thể được proxy/servlet/router xử lý khác nhau tùy thiết lập. Đường dẫn hiển thị trong log, request target thực tế và path dùng để security match có thể không hoàn toàn giống chuỗi ban đầu.

Với Spring Security, sử dụng matcher tương thích stack và cấu hình web hiện tại; thử nghiệm các biến thể đường dẫn quan trọng sau proxy. Không tự kiểm tra kiểu `request.getRequestURI().startsWith("/admin")` như lớp phân quyền chính duy nhất, vì route và security có thể bất đồng về cách chuẩn hóa.

Một khác biệt nữa: **query không tạo origin mới nhưng vẫn là đầu vào nghiệp vụ**. `GET /api/users?role=admin` vẫn thuộc cùng origin với `GET /api/users?role=user`; endpoint server không được tự cấp quyền admin chỉ từ query đó.

### 9.4. Nhiều ứng dụng cùng domain gốc vẫn cần ranh giới quyền riêng

Ví dụ một tổ chức có `help.example.com`, `app.example.com` và `admin.example.com`. Các origin này có thể cùng schemeful site. Không nên vì vậy chia sẻ session cookie toàn `example.com` hoặc dùng CORS `https://*.example.com` nếu một số subdomain do bên thứ ba hoặc người dùng tùy ý vận hành.

Thiết kế tốt thường có: cookie host-only; CORS allowlist origin cụ thể; identity và audience/token được xác định rõ cho API; kiểm soát CSRF theo cơ chế credential; quyền nghiệp vụ ở server; hạn chế quyền và dữ liệu giữa các service.

## 10. Checklist chọn đúng loại ranh giới

Khi gặp lỗi đăng nhập/CORS/cookie hoặc viết mới một endpoint, hãy trả lời lần lượt:

1. **URL bên client chính xác là gì?** Ghi cả scheme, hostname, explicit/default port, path; tách query và fragment.
2. **Frontend và backend same-origin hay cross-origin?** So cả ba phần `scheme + host + port`, không nhìn mỗi hostname hoặc tên công ty.
3. **Nếu có cookie, hai request same-site hay cross-site?** Xét schemeful site bằng registrable domain/PSL; đừng suy bằng tách hai label cuối.
4. **Cookie có đủ điều kiện được gửi không?** Xét host-only/Domain, Path, Secure, SameSite, browser credentials mode và chính sách third-party cookie.
5. **Có cần JavaScript đọc cross-origin response không?** Nếu có, cấu hình CORS với các origin/method/header/credentials cần thiết. CORS không thay authentication/authorization.
6. **Request thay đổi trạng thái có nguy cơ CSRF không?** Đánh giá cách browser tự đính kèm cookie/credentials; giữ kiểm tra server theo thiết kế.
7. **Endpoint path nào cần quyền gì?** Áp Spring Security URL rule và authorization nghiệp vụ; đừng suy quyền từ origin được CORS cho phép.
8. **Có proxy, callback URL hoặc URL do client cung cấp không?** Validate host/scheme/redirect và chỉ tin forwarded metadata từ proxy xác định.
9. **Đã có negative test chưa?** Thử port khác, subdomain khác, scheme khác, path khác, cookie không hợp lệ, user không đủ quyền và Origin không nằm trong allowlist.

## 11. Bài tập tự kiểm tra (có lời giải)

**Bài 1.** `https://shop.example.com/cart` và `https://shop.example.com/checkout` khác path. Có phải cross-origin không?

**Đáp án:** Không. Nếu scheme, hostname và effective port bằng nhau, chúng same-origin và same-site. Hai path vẫn có thể được áp **hai chính sách phân quyền server khác nhau**.

**Bài 2.** `https://app.example.com` gọi `https://api.example.com`. Hai URL là same-site hay same-origin?

**Đáp án:** Same-site nếu registrable domain đều `example.com` và scheme đều HTTPS; cross-origin vì hostname khác. JavaScript đọc API response phải tuân theo CORS.

**Bài 3.** `http://localhost:5173` gọi `http://localhost:8080`. Nếu cả hai cùng hostname `localhost`, sao browser vẫn báo CORS?

**Đáp án:** Vì port khác nên origin khác. CORS allowlist phải khớp origin frontend, ví dụ `http://localhost:5173`.

**Bài 4.** `https://app.example.com` và `http://app.example.com` có phải same-site không?

**Đáp án:** Theo schemeful site, **không**: HTTPS và HTTP là hai scheme khác nhau; chúng cũng cross-origin dù hostname bằng nhau.

**Bài 5.** Cookie `Domain=example.com; Path=/admin` có tạo vùng bảo mật JavaScript riêng cho `/admin` so với `/profile` không?

**Đáp án:** Không. Path là điều kiện lựa chọn gửi cookie, không tạo origin riêng; script cùng origin không được cô lập chỉ vì khác path. Server phải xác thực/phân quyền mỗi thao tác.

**Bài 6.** API trả `Access-Control-Allow-Origin: https://app.example.com`. Người dùng chưa đăng nhập có được phép đọc `/api/me`?

**Đáp án:** CORS chỉ liên quan quyền browser đọc response. Nếu server yêu cầu authentication thì request chưa đăng nhập vẫn bị từ chối/challenge.

**Bài 7.** Nếu hai hostname có cùng IP, chúng có trở thành same-origin không?

**Đáp án:** Không. Origin xét scheme/hostname/port, không so địa chỉ IP được DNS phân giải đến.

**Bài 8.** Với `www.example.co.uk` và `api.example.co.uk`, lấy hai label cuối `co.uk` để tính site có đúng không?

**Đáp án:** Không. `co.uk` là public suffix; registrable domain trong ví dụ là `example.co.uk`. Phải xét PSL, không đếm label thủ công.

**Bài 9.** Vì sao cross-origin request vẫn có nguy cơ CSRF ngay cả khi server không bật CORS?

**Đáp án:** Browser có thể gửi một số request cross-origin như form submit. Việc không cho JavaScript đọc response không bảo đảm request không tới server hoặc không gây tác động; phải xét CSRF, cookie và quyền server.

**Bài 10.** Spring Security `requestMatchers("/admin/**").hasRole("ADMIN")` có đồng nghĩa với “trang /admin là một origin riêng” không?

**Đáp án:** Không. Matcher áp chính sách truy cập cho path của server; origin được xác định bằng scheme, host và port. Hai khái niệm vận hành độc lập nhưng bổ trợ nhau để bảo vệ ứng dụng.

## Kết luận

Bốn khái niệm phục vụ bốn loại câu hỏi:

- **Hostname:** URL đang chỉ đến host nào?
- **Origin:** Hai URL có cùng scheme, host và effective port không, để xét ranh giới Same-Origin Policy/CORS?
- **Site:** Hai URL có cùng schemeful registrable domain không, để hiểu nhiều hành vi cookie/SameSite?
- **Path:** Server đang định tuyến đến tài nguyên hoặc endpoint nào, và cần áp policy nào tại đó?

Trong ứng dụng Spring, CORS là chính sách **origin** dành cho browser; cookie SameSite làm việc với khái niệm **site**; hostname/Domain xác định nhiều phần phạm vi cookie và routing; Spring Security `requestMatchers` cùng authorization nghiệp vụ kiểm soát **path và quyền truy cập**. Phân biệt rõ các phạm vi này giúp cấu hình đúng mà không nhầm lẫn giữa việc browser được đọc response và việc user được phép thực hiện hành động.