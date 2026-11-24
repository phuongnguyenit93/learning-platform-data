# Strict-Transport-Security (HSTS): buộc browser sử dụng HTTPS

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích HSTS và cách browser ghi nhớ chính sách chỉ kết nối HTTPS cho một hostname.
2. Cấu hình header Strict-Transport-Security với max-age phù hợp.
3. Đánh giá tác động của includeSubDomains và điều kiện trước khi bật trên domain cha.
4. Phân biệt HSTS với HTTP-to-HTTPS redirect, CSP upgrade-insecure-requests và cookie Secure.
5. Hiểu giới hạn của HSTS ở lần truy cập đầu tiên và vai trò của HSTS preload.
6. Triển khai HSTS sau TLS termination trên Nginx, Node.js/Express và Spring Security.
7. Kiểm tra header, hành vi nâng cấp HTTP và các trường hợp rollback bằng browser DevTools.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. HSTS là security header giúp browser ghi nhớ rằng một hostname phải được truy cập bằng HTTPS, từ đó giảm nguy cơ SSL stripping và kết nối HTTP ngoài ý muốn.

## 1. HSTS giải quyết vấn đề gì?

Website có thể hỗ trợ cả HTTP và HTTPS. Nếu người dùng gõ một địa chỉ không có scheme hoặc bấm một liên kết HTTP, browser có thể bắt đầu bằng request không mã hóa:

```text
Người dùng
   |
   | http://shop.example.test
   v
Browser ---- HTTP request ----> Server
   |
   +---- có thể bị quan sát hoặc sửa trên đường truyền
```

Kẻ tấn công ở vị trí trung gian có thể cố giữ kết nối ở HTTP, loại bỏ redirect sang HTTPS hoặc sửa nội dung trước khi browser chuyển sang kết nối bảo mật. Kỹ thuật hạ cấp như vậy thường được gọi là SSL stripping.

HSTS (HTTP Strict Transport Security) cho phép server gửi chính sách:

```http
Strict-Transport-Security: max-age=31536000
```

Sau khi nhận header hợp lệ qua một kết nối HTTPS đã được xác thực, browser lưu chính sách theo hostname. Trong thời gian chính sách còn hiệu lực, browser tự chuyển các URL HTTP tới hostname đó thành HTTPS trước khi gửi request mạng.

```text
Người dùng nhập http://shop.example.test
                 |
                 v
        Browser tra HSTS state
                 |
                 v
        Nâng cấp thành HTTPS
                 |
                 v
        Kết nối TLS tới server
```

HSTS giúp browser tránh khởi tạo kết nối HTTP không an toàn tới hostname đã biết. Nó không phải một redirect do server trả về; việc nâng cấp được browser thực hiện trước khi gửi request HTTP.

## 2. Cú pháp Strict-Transport-Security

Header cơ bản:

```http
Strict-Transport-Security: max-age=31536000
```

Các directive chính:

| Directive | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| max-age | Số giây browser ghi nhớ chính sách cho hostname | Giá trị 0 xóa policy đã lưu của hostname đó |
| includeSubDomains | Áp dụng chính sách của hostname này cho các subdomain | Chỉ bật khi mọi subdomain cần truy cập đều sẵn sàng HTTPS |
| preload | Tín hiệu được một số chương trình preload sử dụng | Không phải directive cốt lõi của RFC 6797; cần đáp ứng điều kiện của preload program |

### max-age

max-age tính bằng giây, không phải ngày hoặc tháng:

```http
# 1 ngày
Strict-Transport-Security: max-age=86400

# 1 năm thường dùng trong triển khai HSTS ổn định
Strict-Transport-Security: max-age=31536000

# Xóa policy động đã lưu cho hostname này
Strict-Transport-Security: max-age=0
```

Một năm có 365 ngày:

```text
365 × 24 × 60 × 60 = 31,536,000 giây
```

Khi browser nhận lại HSTS header từ cùng hostname qua HTTPS, max-age mới thay thế thời hạn đã lưu trước đó. Nếu không nhận được header mới, policy đã lưu tiếp tục có hiệu lực cho đến khi hết hạn.

### includeSubDomains

Ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Nếu header được gửi từ example.test, browser áp dụng chính sách HSTS cho:

```text
example.test
www.example.test
api.example.test
admin.example.test
legacy.example.test
```

Đây là một quyết định có phạm vi lớn. Trước khi bật includeSubDomains, phải xác minh mọi subdomain đang hoạt động, kể cả hệ thống cũ, dịch vụ email trên web, trang hỗ trợ, môi trường quản trị, staging và các host do bên thứ ba vận hành.

includeSubDomains không có nghĩa mọi subdomain tự nhận một policy riêng. Browser áp dụng policy của domain cha cho các hostname con phù hợp trong thời gian policy cha còn hiệu lực.

### preload

Ví dụ thường gặp:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

Token preload không tự thêm domain vào danh sách preload của browser. Nó chỉ thể hiện ý định và là một trong những điều kiện mà chương trình preload có thể yêu cầu. Chủ sở hữu domain phải gửi đăng ký, đáp ứng tiêu chí hiện hành và chờ danh sách được tích hợp vào các phiên bản browser.

Không bật preload chỉ để đạt điểm kiểm tra header. Việc đưa domain vào danh sách preload có thể khiến mọi người dùng browser có danh sách đó buộc phải dùng HTTPS ngay từ lần đầu.

## 3. Browser xử lý HSTS như thế nào?

Quy trình đơn giản:

1. Browser truy cập https://shop.example.test.
2. TLS handshake thành công và certificate được browser chấp nhận.
3. Server trả Strict-Transport-Security.
4. Browser ghi nhớ policy theo hostname và thời hạn max-age.
5. Lần sau người dùng truy cập http://shop.example.test, browser tự nâng cấp URL sang HTTPS trước khi gửi request.
6. Nếu HTTPS có lỗi certificate, browser hiển thị lỗi bảo mật và không cho người dùng bỏ qua theo cách thông thường đối với HSTS host.

### HSTS chỉ được học qua kết nối bảo mật

Browser chỉ chấp nhận HSTS header khi nhận từ một kết nối HTTPS an toàn và certificate được xác thực. Header gửi qua HTTP không được dùng để tạo hoặc thay đổi HSTS state.

Điều này ngăn attacker ở đường truyền HTTP gửi một header giả nhằm xóa hoặc thay đổi chính sách HSTS của website.

Ví dụ header sau trên response HTTP không tạo policy:

```http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000
```

Hãy cấu hình header trên response HTTPS sau khi TLS được thiết lập đúng.

### HSTS áp dụng theo hostname, không theo port

Policy gắn với hostname. Nó không chỉ áp dụng cho một port cụ thể. Khi browser nâng cấp URL HTTP:

- Nếu URL dùng port 80, browser thay bằng port HTTPS mặc định 443.
- Nếu URL chỉ định port khác 80, port đó được giữ lại khi đổi scheme; dịch vụ tại port đó phải hỗ trợ TLS.

Ví dụ:

| URL ban đầu | URL sau HSTS upgrade |
| --- | --- |
| http://shop.example.test | https://shop.example.test |
| http://shop.example.test:80/cart | https://shop.example.test:443/cart |
| http://shop.example.test:8080/health | https://shop.example.test:8080/health |

Vì vậy, không giả định HSTS sẽ chuyển mọi port HTTP tùy chỉnh về 443. Hãy kiểm kê endpoint và port thực tế trước khi bật policy.

### HSTS không phải redirect 301/308

Khi HSTS được áp dụng, browser tự nâng cấp URL trước khi gửi request HTTP. Server không cần nhận request HTTP rồi mới trả redirect.

Trong Chrome DevTools, có thể thấy một dòng nội bộ như 307 Internal Redirect hoặc chú thích liên quan đến HSTS. Đây là hành vi do browser thực hiện, không phải response 307 từ server.

## 4. HSTS bảo vệ điều gì và không bảo vệ điều gì?

HSTS giúp:

- Ngăn browser khởi tạo HTTP tới hostname đã có HSTS policy.
- Giảm nguy cơ SSL stripping trên các lần truy cập sau khi policy được ghi nhớ.
- Buộc browser giữ HTTPS sau khi người dùng truy cập hostname đã biết.
- Làm cho lỗi certificate trở thành lỗi chặn đối với hostname HSTS, giảm khả năng người dùng bỏ qua cảnh báo.

HSTS không:

- Bảo vệ lần truy cập đầu tiên nếu browser chưa có policy và domain chưa được preload.
- Sửa certificate hết hạn, sai hostname hoặc cấu hình TLS yếu.
- Thay thế redirect HTTP-to-HTTPS cho client không áp dụng HSTS.
- Chặn XSS, CSRF, SQL injection hoặc lỗi authorization.
- Tự bảo vệ mọi subdomain nếu không có includeSubDomains hoặc policy riêng.
- Buộc mọi HTTP client như curl, ứng dụng mobile hoặc thư viện server tự áp dụng HSTS như browser.
- Mã hóa dữ liệu ở tầng ứng dụng hoặc thay thế kiểm soát quyền truy cập.

## 5. HSTS và lần truy cập đầu tiên

HSTS động chỉ có tác dụng sau khi browser đã nhận và lưu policy qua HTTPS. Nếu người dùng lần đầu truy cập bằng HTTP và browser chưa có HSTS state, request HTTP đầu tiên vẫn có thể xảy ra.

```text
Lần đầu, chưa có policy:

Browser ---- HTTP ----> Attacker có thể can thiệp
   |
   +---- nếu bị chuyển hướng đúng ----> HTTPS
```

Có hai cách giảm rủi ro:

1. Phát URL HTTPS trong email, link, sitemap, canonical URL và tài liệu sản phẩm; redirect HTTP sang HTTPS cho các client chưa có HSTS.
2. Đăng ký HSTS preload nếu domain đáp ứng yêu cầu và chủ sở hữu chấp nhận phạm vi cam kết dài hạn.

### HSTS preload

Browser có thể tích hợp danh sách hostname được preload sẵn. Với domain trong danh sách, browser biết phải dùng HTTPS ngay cả khi người dùng chưa từng truy cập domain đó.

Một số điều kiện phổ biến của chương trình preload gồm:

- Website phục vụ HTTPS hợp lệ.
- HTTP được chuyển hướng sang HTTPS.
- HSTS có max-age tối thiểu theo yêu cầu hiện hành của chương trình.
- Có includeSubDomains.
- Có token preload trong header nếu chương trình yêu cầu.
- Các subdomain cần thiết đều hoạt động qua HTTPS.

Tiêu chí có thể thay đổi. Trước khi đăng ký, hãy đọc yêu cầu hiện tại của chương trình preload và kiểm tra toàn bộ hostname thuộc phạm vi.

### Rủi ro khi preload

Preload là quyết định vận hành dài hạn:

- Một subdomain HTTP cũ có thể không truy cập được trong browser đã preload.
- Dịch vụ của đối tác trên subdomain có thể chưa hỗ trợ TLS.
- Gỡ domain khỏi danh sách preload không diễn ra tức thì; cần quy trình cập nhật danh sách và chờ browser phát hành phiên bản mới.
- max-age=0 không tự xóa entry đã được tích hợp sẵn trong preload list.

Chỉ đăng ký khi đội vận hành kiểm soát được domain và subdomain trong dài hạn.

## 6. Triển khai an toàn: rollout theo từng giai đoạn

Không bật max-age dài và includeSubDomains trên domain cha ngay khi chưa kiểm kê.

### Giai đoạn 1 — Kiểm kê HTTPS

Lập danh sách:

- Domain gốc và các subdomain đang hoạt động.
- Các cổng dịch vụ public.
- CDN, load balancer và reverse proxy kết thúc TLS.
- Redirect từ HTTP sang HTTPS.
- Certificate chain, hostname, hạn sử dụng và quy trình gia hạn.
- Ứng dụng cũ, trang quản trị, trang hỗ trợ và dịch vụ do bên thứ ba quản lý.

Kiểm tra cả các hostname ít được truy cập; một subdomain cũ có thể chỉ được dùng trong một quy trình nội bộ nhưng vẫn bị includeSubDomains bao phủ.

### Giai đoạn 2 — Bật HSTS ngắn hạn trên một hostname

Sau khi HTTPS ổn định, bắt đầu với max-age ngắn:

```http
Strict-Transport-Security: max-age=300
```

Năm phút đủ để kiểm tra hành vi trong môi trường test. Sau đó tăng dần thời gian khi đã xác minh redirect, TLS và các luồng người dùng.

### Giai đoạn 3 — Tăng max-age

Ví dụ rollout:

```http
# Thử nghiệm ngắn
Strict-Transport-Security: max-age=300

# Giai đoạn ổn định
Strict-Transport-Security: max-age=86400

# Production khi đã xác minh
Strict-Transport-Security: max-age=31536000
```

Các mốc này là ví dụ vận hành, không phải lịch bắt buộc. Chọn thời gian theo khả năng rollback và mức độ chắc chắn của hạ tầng.

### Giai đoạn 4 — Cân nhắc includeSubDomains

Chỉ thêm sau khi mọi subdomain đã có HTTPS và được kiểm thử:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Nếu một subdomain không thể hỗ trợ HTTPS, cần xử lý kiến trúc hoặc phạm vi domain trước khi bật directive ở domain cha.

### Giai đoạn 5 — Cân nhắc preload

Chỉ thực hiện sau khi:

1. Domain và mọi subdomain trong phạm vi đã sẵn sàng HTTPS.
2. Redirect HTTP đã ổn định.
3. Certificate lifecycle có thể duy trì lâu dài.
4. Chủ sở hữu domain chấp nhận cam kết dài hạn.
5. Đã kiểm tra tiêu chí đăng ký preload hiện hành.

## 7. Rollback và gỡ HSTS

Nếu cần ngừng policy HSTS động cho một hostname, server có thể trả qua HTTPS:

```http
Strict-Transport-Security: max-age=0
```

Browser nhận header này qua HTTPS sẽ xóa policy động đã lưu cho hostname đó.

Lưu ý:

- Gửi max-age=0 qua HTTP không xóa HSTS state.
- Xóa policy trên domain cha không nhất thiết xóa policy riêng mà một subdomain đã tự thiết lập.
- Nếu parent từng bật includeSubDomains, browser có thể đã ghi nhớ policy cha; hãy kiểm tra đúng hostname và state trong browser.
- max-age=0 không xóa domain khỏi preload list đã được đóng gói trong browser.
- Người dùng có thể đang dùng browser/profile khác với browser dùng để thử nghiệm.

Nếu đang rollout includeSubDomains, phương án an toàn thường là giảm max-age hoặc gỡ includeSubDomains trên domain cha qua HTTPS, đồng thời xử lý các HSTS policy riêng và kiểm tra trạng thái từng hostname.

## 8. Phân biệt HSTS với các cơ chế khác

| Cơ chế | Nơi hoạt động | Vai trò |
| --- | --- | --- |
| HSTS | Browser lưu policy theo hostname | Tự nâng cấp HTTP sang HTTPS cho hostname đã biết |
| HTTP-to-HTTPS redirect | Web server/proxy | Chuyển client gửi HTTP sang URL HTTPS |
| CSP upgrade-insecure-requests | Browser xử lý tài nguyên của document | Nâng cấp URL tài nguyên insecure trong phạm vi document |
| Cookie Secure | Browser quản lý cookie | Chỉ gửi cookie qua kênh bảo mật theo quy tắc cookie |
| TLS certificate | TLS endpoint/browser | Xác thực danh tính server và bảo vệ kênh truyền |
| CSP frame-ancestors | Browser kiểm tra ancestor | Hạn chế website được phép nhúng trang |

### HSTS và redirect

Redirect vẫn cần thiết vì:

- Client không phải browser có thể không áp dụng HSTS.
- Browser lần đầu chưa có HSTS state vẫn cần được chuyển sang HTTPS.
- Link HTTP cũ vẫn cần chuyển hướng cho người dùng và công cụ tìm kiếm.

HSTS giúp browser đã biết policy bỏ qua bước gửi request HTTP. Redirect giúp các client khác tìm đến endpoint HTTPS.

### HSTS và CSP upgrade-insecure-requests

upgrade-insecure-requests nâng cấp các URL tài nguyên insecure trong document, ví dụ image hoặc script được tham chiếu bằng HTTP. HSTS là policy theo hostname được browser ghi nhớ và áp dụng cho truy cập tới hostname đó.

Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

### HSTS và cookie Secure

Cookie Secure chỉ điều khiển việc browser gửi cookie qua kênh bảo mật. Nó không tự nâng cấp mọi navigation HTTP. HSTS giúp browser dùng HTTPS cho hostname đã biết; cookie session vẫn nên có Secure, HttpOnly và SameSite phù hợp.

### HSTS và TLS certificate

HSTS không làm certificate hợp lệ. Server vẫn phải dùng certificate đúng hostname, còn hạn, chain tin cậy và cấu hình TLS phù hợp. Khi HSTS đã có hiệu lực, lỗi certificate sẽ chặn truy cập thay vì cho người dùng dễ dàng tiếp tục.

## 9. Triển khai trên Nginx

Hãy phát HSTS từ server block HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name shop.example.test;

    ssl_certificate     /etc/ssl/certs/shop.example.test.pem;
    ssl_certificate_key /etc/ssl/private/shop.example.test.key;

    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://application;
    }
}
```

HTTP server chỉ redirect:

```nginx
server {
    listen 80;
    server_name shop.example.test;

    return 301 https://shop.example.test$request_uri;
}
```

Chỉ thêm includeSubDomains khi đã kiểm tra mọi subdomain:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Lưu ý:

- Không phát HSTS trên server block HTTP.
- always giúp header xuất hiện trên response lỗi và redirect HTTPS phù hợp.
- Kiểm tra kế thừa add_header khi location có header riêng.
- Tránh để CDN và origin phát nhiều HSTS header mâu thuẫn.
- Nếu TLS kết thúc ở load balancer, xác định tầng nào chịu trách nhiệm phát header và chỉ tin proxy đúng cấu hình.

## 10. Triển khai trên Node.js / Express

Có thể dùng Helmet để quản lý HSTS:

```js
import express from "express";
import helmet from "helmet";

const app = express();

app.use(
  helmet.hsts({
    maxAge: 31536000,
    includeSubDomains: false,
    preload: false
  })
);
```

Ví dụ bắt đầu không bật includeSubDomains hoặc preload. Chỉ đổi các option sau khi đã kiểm kê và kiểm thử.

Nếu TLS kết thúc ở reverse proxy, ứng dụng phải nhận biết đúng request gốc là HTTPS. Cấu hình trust proxy chỉ cho địa chỉ/tầng proxy thực sự tin cậy; không bật tin mọi forwarded header từ client Internet.

```js
// Chỉ dùng khi ứng dụng thực sự nằm sau đúng một proxy tin cậy.
app.set("trust proxy", 1);
```

Helmet có thể dựa vào trạng thái secure của request để quyết định phát HSTS. Hãy kiểm tra response thực tế phía browser sau reverse proxy; không giả định header đã có chỉ vì middleware được cài.

## 11. Triển khai trên Spring Security

Spring Security hỗ trợ cấu hình Strict-Transport-Security qua security headers:

```java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(false)
    )
);
```

Sau khi kiểm kê toàn bộ subdomain và xác nhận HTTPS:

```java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
    )
);
```

API cấu hình cụ thể có thể khác theo phiên bản Spring Security. Hãy kiểm tra version của dự án và xác minh header trên response HTTPS thực tế.

Spring Security thường chỉ phát HSTS trên request được xem là secure. Nếu TLS termination xảy ra ở proxy, cấu hình forwarded headers và trust boundary đúng cách để ứng dụng nhận diện scheme HTTPS từ proxy đáng tin cậy. Không tin X-Forwarded-Proto từ một client có thể kết nối trực tiếp.

## 12. Kiểm thử HSTS bằng Chrome DevTools

Thực hiện trên domain staging do bạn kiểm soát, có HTTPS certificate hợp lệ. Không thử max-age dài hoặc includeSubDomains trên domain production chưa được kiểm kê.

### Bước 1 — Kiểm tra response header HTTPS

1. Mở https://shop.example.test.
2. DevTools → Network.
3. Chọn document chính.
4. Xem Response Headers.
5. Xác nhận có đúng một policy Strict-Transport-Security với max-age mong muốn.

HSTS header gửi qua HTTP không được browser dùng để thiết lập policy.

### Bước 2 — Kiểm tra nâng cấp HTTP

1. Sau khi browser đã nhận HSTS header từ HTTPS, mở tab mới.
2. Nhập http://shop.example.test.
3. Quan sát address bar chuyển sang HTTPS.
4. Trong Network, tìm dấu hiệu browser internal redirect/HSTS upgrade.
5. Xác nhận server không nhận request HTTP cho lần truy cập này.

Để thử lại từ trạng thái chưa có HSTS, dùng profile test riêng hoặc xóa HSTS state qua công cụ phù hợp của browser. Đừng xóa state của domain người dùng đang làm việc nếu chưa hiểu tác động.

### Bước 3 — Kiểm tra includeSubDomains

Trong staging, tạo subdomain HTTPS như app.staging.example.test và một subdomain thử nghiệm khác. Khi browser đã học policy của domain cha có includeSubDomains, thử mở HTTP tới subdomain. Xác nhận browser tự nâng cấp.

Không dùng subdomain production đang phục vụ HTTP để làm phép thử này.

### Bước 4 — Kiểm tra max-age=0

Trên HTTPS response của hostname thử nghiệm, trả:

```http
Strict-Transport-Security: max-age=0
```

Mở lại hostname bằng HTTP và xác nhận browser không còn áp dụng policy động sau khi nhận header xóa. Nếu domain nằm trong preload list, max-age=0 không gỡ entry preload.

### Bước 5 — Kiểm tra TLS lỗi

Dùng một hostname lab có certificate không hợp lệ trong môi trường cô lập. Khi browser đã có HSTS state, xác nhận lỗi certificate không có lựa chọn bỏ qua thông thường. Không cố tạo lỗi certificate trên website production.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Header trên HTTPS | Certificate hợp lệ, max-age dương | Browser ghi nhớ HSTS |
| Header trên HTTP | Response không mã hóa | Browser bỏ qua HSTS header |
| HTTP sau khi đã học HSTS | Hostname còn policy | Browser nâng cấp sang HTTPS trước request |
| includeSubDomains | Parent policy còn hiệu lực | Subdomain được nâng cấp sang HTTPS |
| max-age=0 qua HTTPS | Hostname có policy động | Browser xóa policy động của hostname |
| Certificate không hợp lệ | Hostname đang HSTS | Browser chặn lỗi certificate |
| Non-default HTTP port | URL dùng port khác 80 | Scheme đổi sang HTTPS, port được giữ |
| Domain trong preload list | Browser có danh sách preload | HTTPS được áp dụng ngay từ lần đầu |

## 13. Xử lý sự cố và sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gửi HSTS trên HTTP | Browser bỏ qua header | Phát header từ response HTTPS hợp lệ |
| Bật includeSubDomains quá sớm | Subdomain HTTP cũ không truy cập được | Kiểm kê và triển khai HTTPS cho mọi subdomain |
| Dùng max-age dài ngay từ đầu | Rollback khó chịu hơn nếu TLS có lỗi | Tăng max-age theo từng giai đoạn |
| Nghĩ HSTS thay redirect | Client chưa có HSTS vẫn có thể dùng HTTP | Duy trì redirect HTTP-to-HTTPS |
| Nghĩ HSTS bảo vệ lần đầu | SSL stripping vẫn có thể xảy ra trước khi học policy | Dùng HTTPS link và cân nhắc preload |
| Đăng ký preload khi chưa sẵn sàng | Domain/subdomain có thể bị buộc HTTPS lâu dài | Đánh giá preload criteria và rollback trước khi đăng ký |
| Nghĩ max-age=0 xóa preload | Browser vẫn có thể giữ entry preload tích hợp | Thực hiện quy trình removal của preload program |
| Nghĩ Secure cookie thay HSTS | Navigation HTTP vẫn có thể xảy ra | Kết hợp cookie Secure với HSTS và redirect |
| Không kiểm tra port tùy chỉnh | HTTPS upgrade có thể đi tới port không phục vụ TLS | Kiểm kê port và endpoint trước khi bật |
| Tin forwarded header từ mọi client | Có thể phát hiện sai scheme hoặc cấu hình sai HSTS | Chỉ tin proxy đã cấu hình |
| Phát nhiều HSTS header | Khó dự đoán và khó debug policy | Chỉ định một tầng chịu trách nhiệm phát header |

### Browser vẫn gửi HTTP dù đã cấu hình HSTS?

Kiểm tra:

1. Browser có nhận header từ HTTPS với certificate hợp lệ không?
2. Header có đúng hostname mà người dùng truy cập không?
3. max-age có lớn hơn 0 không?
4. Policy đã hết hạn hoặc bị xóa bởi response max-age=0 không?
5. Người dùng đang ở browser profile khác không?
6. URL có port tùy chỉnh và endpoint HTTPS tương ứng có hoạt động không?
7. Domain có trong preload list của browser đang thử hay không?

### Website bị lỗi sau khi bật includeSubDomains?

Xác định subdomain nào chưa có HTTPS hoặc certificate không hợp lệ. Nếu cần rollback, gửi max-age=0 hoặc bỏ includeSubDomains từ response HTTPS của domain cha; sau đó kiểm tra policy riêng ở từng subdomain. Người dùng có thể tiếp tục bị ảnh hưởng trong thời gian browser chưa nhận policy mới.

## 14. Câu hỏi củng cố

**Câu 1.** Vì sao browser không chấp nhận HSTS header gửi qua HTTP?

**Giải đáp:** Kết nối HTTP có thể bị attacker sửa. Nếu browser tin header đó, attacker có thể xóa hoặc thay đổi HSTS policy. HSTS chỉ được học từ response HTTPS đã xác thực.

**Câu 2.** HSTS có tự bảo vệ lần truy cập đầu tiên không?

**Giải đáp:** Không, trừ khi hostname đã nằm trong preload list hoặc browser đã có policy từ lần truy cập trước. Hãy dùng HTTPS URL và redirect; cân nhắc preload sau khi đánh giá.

**Câu 3.** includeSubDomains trên example.test ảnh hưởng tới app.example.test không?

**Giải đáp:** Có. Browser áp dụng policy của domain cha cho các subdomain trong phạm vi khi policy còn hiệu lực.

**Câu 4.** max-age=0 gửi qua HTTPS có xóa domain khỏi preload list không?

**Giải đáp:** Không. Nó xóa policy động mà browser học được; entry preload cần quy trình removal riêng và chờ cập nhật browser.

**Câu 5.** HSTS có thay thế redirect HTTP-to-HTTPS không?

**Giải đáp:** Không. Client chưa học HSTS và các HTTP client không áp dụng HSTS vẫn cần redirect.

**Câu 6.** Nếu HTTP URL dùng port 8080, HSTS có luôn đổi sang port 443 không?

**Giải đáp:** Không. Port 80 được đổi thành 443; port khác 80 thường được giữ nguyên khi browser đổi scheme sang HTTPS. Dịch vụ tại port đó phải hỗ trợ TLS.

## 15. Tổng kết

**Strict-Transport-Security (HSTS)** giúp browser ghi nhớ rằng một hostname chỉ nên được truy cập qua HTTPS. Header chỉ có hiệu lực khi được nhận qua kết nối HTTPS hợp lệ; max-age xác định thời gian ghi nhớ, còn includeSubDomains mở rộng chính sách tới toàn bộ subdomain.

Hãy rollout từ hostname đã kiểm soát, bắt đầu với max-age ngắn, xác minh TLS/redirect/port và tăng dần thời hạn. Chỉ bật includeSubDomains khi mọi subdomain đã sẵn sàng; chỉ cân nhắc preload khi đội vận hành chấp nhận cam kết dài hạn và đã đáp ứng tiêu chí hiện hành. HSTS bổ sung cho redirect, cookie Secure và CSP; nó không thay TLS certificate hợp lệ hoặc các biện pháp phòng XSS, CSRF và authorization.

## Tài liệu tham khảo

1. [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797): đặc tả HSTS, max-age, includeSubDomains và hành vi browser.
2. [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): cú pháp header và triển khai.
3. [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html): rollout, preload và rủi ro vận hành.
4. [Chromium — HSTS](https://www.chromium.org/hsts/): cách Chromium quản lý HSTS và preload.
5. [HSTS Preload](https://hstspreload.org/): yêu cầu và quy trình đăng ký/gỡ domain khỏi preload list.
