# Khái niệm site và sự khác biệt với origin

## Mục tiêu bài học

Trong bảo mật trình duyệt, **site** và **origin** đều mô tả phạm vi của một địa chỉ web nhưng được dùng cho những quyết định khác nhau. Sau bài này, bạn có thể:

- Xác định **site** của URL HTTP/HTTPS theo cách xét **schemeful same-site**, bao gồm scheme và miền có thể đăng ký.
- Phân biệt **same-origin**, **cross-origin**, **same-site** và **cross-site**, kể cả khi khác subdomain, port hoặc giao thức.
- Giải thích vai trò của **Public Suffix List** trong cách trình duyệt xác định ranh giới site.
- Phân tích tác động của site đến **SameSite cookie**, **CSRF**, **Fetch Metadata**, đồng thời nhận diện vì sao **CORS** vẫn cần thiết cho những yêu cầu cùng site nhưng khác origin.
- Vận dụng các khái niệm này khi kiểm tra API có cookie phiên trong Spring Security trên **Servlet** và **Reactive (WebFlux)**.

## 1. Nhắc lại origin: ranh giới gồm ba thành phần

Với URL HTTP/HTTPS thông thường:

**Origin = (scheme, host, port)**

Ví dụ:

~~~text
https://api.example.com:8443/v1/orders?limit=20
^^^^^   ^^^^^^^^^^^^^^^ ^^^^
scheme       host         port

Origin: https://api.example.com:8443
~~~

Hai URL **same-origin** nếu scheme, host và port giống nhau sau khi chuẩn hóa. Cổng mặc định của HTTPS là 443 và của HTTP là 80; các cổng mặc định thường được lược bỏ khi biểu diễn origin.

~~~text
https://app.example.com           ≡ https://app.example.com:443
https://app.example.com           ≠ https://app.example.com:8443
https://app.example.com           ≠ https://api.example.com
https://app.example.com           ≠ http://app.example.com
~~~

**Path, query và fragment không nằm trong origin.** Same-Origin Policy giới hạn một số khả năng đọc và tương tác giữa các origin, còn CORS là cơ chế máy chủ cho phép trình duyệt đọc phản hồi cross-origin có kiểm soát.

Tuy nhiên, **site** áp dụng một phép so sánh khác: subdomain và port không nhất thiết khiến hai địa chỉ thuộc hai site khác nhau.

## 2. Site là gì?

Trong những phép kiểm tra **same-site** hiện đại của trình duyệt, site thường được xác định dưới dạng:

**Schemeful site = (scheme, registrable domain)**

Trong đó:

- **Scheme** là giao thức của URL, thông thường là http hoặc https.
- **Registrable domain** là miền có thể đăng ký, thường được mô tả bằng công thức **eTLD+1**: phần hậu tố công cộng (effective top-level domain) cộng thêm một nhãn tên miền trực tiếp phía trước nó.
- **Port không được dùng để phân biệt site.** Các subdomain khác nhau cùng nằm dưới một miền có thể đăng ký thường được xem là cùng site.

Xét ba URL:

~~~text
https://app.example.com/dashboard
https://api.example.com:8443/orders
https://cdn.example.com/assets/logo.png

Registrable domain của cả ba: example.com
Scheme của cả ba:              https

=> Cả ba thuộc site: https://example.com
=> Ba URL có thể thuộc ba origin khác nhau.
~~~

Điều này không có nghĩa trình duyệt tự động tin cậy mọi subdomain của example.com. **Same-site là một quan hệ phân loại; nó không đồng nghĩa cùng quyền truy cập dữ liệu.**

### 2.1. Vì sao cần Public Suffix List?

Không thể tìm miền có thể đăng ký bằng cách lấy cố định hai thành phần cuối của hostname.

Ví dụ:

| Host | Hậu tố công cộng | Miền có thể đăng ký | Schemeful site nếu dùng HTTPS |
| --- | --- | --- | --- |
| app.example.com | com | example.com | https://example.com |
| api.example.co.uk | co.uk | example.co.uk | https://example.co.uk |
| shop.example.com.vn | com.vn | example.com.vn | https://example.com.vn |
| news.example.org | org | example.org | https://example.org |

**Public Suffix List (PSL)** là danh sách được trình duyệt và nhiều thư viện dùng để phân biệt phần hậu tố công cộng với phần miền mà một chủ thể có thể đăng ký hoặc quản lý. Với tên miền **shop.example.co.uk**, hậu tố công cộng là **co.uk** nên miền có thể đăng ký là **example.co.uk**; chỉ lấy hai nhãn cuối sẽ nhầm thành co.uk.

PSL còn có thể chứa **hậu tố riêng (private suffix)** dành cho nền tảng lưu trữ nhiều người thuê. Ví dụ, khi áp dụng mục liên quan tới **github.io** trong PSL, hai host **alice.github.io** và **bob.github.io** không được coi là cùng site chỉ vì cùng kết thúc bằng github.io. Việc hỗ trợ và cách dùng phần private suffix phụ thuộc cơ chế, thư viện và trình duyệt; khi triển khai cần dùng nguồn xác định miền có thể đăng ký phù hợp với môi trường thực tế.

**Không viết thuật toán bảo mật kiểu** “lấy hai nhãn cuối hostname”, cũng không dùng kiểm tra chuỗi có hậu tố giống nhau để xác định site đáng tin cậy. Ngoài ra, PSL phân định ranh giới tên miền, **không chứng minh ai sở hữu hoặc kiểm soát website**.

### 2.2. Với localhost, địa chỉ IP và host đặc biệt

Không phải host nào cũng có registrable domain theo PSL. Khi không xác định được miền có thể đăng ký, trình duyệt dùng các quy tắc dựa trên **host** tương ứng cho những phép so sánh site có liên quan.

Ví dụ với các URL HTTP thông thường:

~~~text
http://localhost:3000   và http://localhost:8080
=> Same-site (cùng scheme và host localhost), cross-origin (khác port).

http://localhost:3000   và http://127.0.0.1:3000
=> Khác host, không cùng site theo phép so sánh thông thường.

http://127.0.0.1:3000  và http://127.0.0.1:8080
=> Same-site, cross-origin.
~~~

Một hostname và địa chỉ IP có thể trỏ về cùng máy nhưng không vì thế trở thành cùng origin hoặc cùng site. Cũng không nên dùng giả định “cùng mạng nội bộ” để suy ra same-site.

## 3. So sánh site và origin qua ví dụ

Giả sử trang hiện tại là **https://app.example.com/dashboard**, sử dụng cổng HTTPS mặc định 443.

| URL đích | So với trang: origin | So với trang: site | Giải thích |
| --- | --- | --- | --- |
| https://app.example.com/account | Same-origin | Same-site | Cả scheme, host, port đều trùng; chỉ đổi path. |
| https://app.example.com:443/api | Same-origin | Same-site | Cổng mặc định 443 tương đương cổng bị lược bỏ. |
| https://app.example.com:8443/api | Cross-origin | Same-site | Port đổi; site không xét port. |
| https://api.example.com/api | Cross-origin | Same-site | Host/subdomain đổi; registrable domain và scheme trùng. |
| https://example.com/ | Cross-origin | Same-site | Host khác nhưng cùng registrable domain example.com. |
| http://app.example.com/api | Cross-origin | Cross-site | Scheme khác; schemeful site tính cả giao thức. |
| https://app.example.net/api | Cross-origin | Cross-site | Miền có thể đăng ký khác. |
| https://app.example.com.evil.test/ | Cross-origin | Cross-site | Đây là host dưới evil.test, không phải subdomain của example.com. |

Từ bảng này có thể rút ra:

- **Same-origin thường kéo theo same-site** trong các trường hợp HTTP/HTTPS thông thường.
- **Same-site không kéo theo same-origin**: hai subdomain hoặc hai port khác nhau vẫn có thể thuộc cùng site.
- **Cross-site kéo theo cross-origin** trong các ví dụ thông thường ở đây.
- Hai URL cùng hostname nhưng khác http/https là **cross-site** khi dùng cách xét schemeful site.

### 3.1. Schemeful same-site khác cách xét cũ

Khái niệm **schemeful same-site** coi **http://example.com** và **https://example.com** là hai site khác nhau. Một số tài liệu cũ mô tả site mà không xét scheme (schemeless site), nên có thể kết luận hai URL đó là same-site.

Khi phân tích SameSite cookie trong các trình duyệt hiện đại, hãy tính cả scheme. HSTS có thể giúp trình duyệt nâng cấp kết nối lên HTTPS theo chính sách đã biết, nhưng **không làm http và https thành cùng origin**.

### 3.2. Đừng nhầm site với tổ chức, địa chỉ IP hoặc tên thương hiệu

Hai miền **shop.example.com** và **api.example.com** thường cùng site, ngay cả khi được triển khai trên những máy chủ hay dịch vụ cloud khác nhau. Ngược lại, **example.com** và **example.net** là hai site khác nhau ngay cả khi thuộc một công ty, dùng chung chứng chỉ wildcard trong phạm vi cho phép, hoặc cùng trỏ đến một địa chỉ IP.

Site là ranh giới được trình duyệt tính từ URL và quy tắc hậu tố tên miền, không phải kết quả nhận diện một doanh nghiệp.

## 4. Vì sao trình duyệt cần cả site và origin?

Hai khái niệm hỗ trợ những cơ chế bảo vệ khác nhau:

| Cơ chế | Ranh giới quan trọng | Câu hỏi chính |
| --- | --- | --- |
| **Same-Origin Policy (SOP)** | Origin | JavaScript từ origin A có được đọc dữ liệu/DOM thuộc origin B không? |
| **CORS** | Origin | Máy chủ có cho phép JavaScript từ Origin A đọc phản hồi của origin B không? |
| **SameSite cookie** | Site, kèm ngữ cảnh yêu cầu | Cookie có đủ điều kiện gửi khi yêu cầu diễn ra từ ngữ cảnh cùng site hay khác site không? |
| **Fetch Metadata: Sec-Fetch-Site** | Quan hệ origin/site với ngữ cảnh yêu cầu | Yêu cầu được khởi tạo trong ngữ cảnh same-origin, same-site, cross-site hay một số ngữ cảnh none? |
| **CSRF defense** | Nhiều tín hiệu, không chỉ site | Yêu cầu thay đổi trạng thái có thực sự xuất phát từ tương tác được ứng dụng cho phép không? |

Ví dụ cùng một request:

~~~text
Trang nguồn:  https://app.example.com/dashboard
API đích:     https://api.example.com/orders

Quan hệ site:     SAME-SITE
Quan hệ origin:   CROSS-ORIGIN
~~~

Trình duyệt vẫn áp dụng CORS cho mã JavaScript cần đọc phản hồi API, **mặc dù hai địa chỉ cùng site**. Mặt khác, SameSite cookie sẽ nhìn nhận yêu cầu theo ngữ cảnh site thay vì đơn giản hỏi hai host có giống nhau không.

## 5. Site và SameSite cookie

Cookie có nhiều thuộc tính độc lập. Trong bài này, quan trọng nhất là **SameSite**, nhưng cần phân biệt với Domain, Path, Secure và HttpOnly.

### 5.1. Ba giá trị SameSite

| Thuộc tính | Quy tắc điển hình | Tình huống sử dụng |
| --- | --- | --- |
| **SameSite=Strict** | Chỉ gửi trong ngữ cảnh same-site theo quy tắc cookie tương ứng. | Cookie nhạy cảm khi ứng dụng chấp nhận việc không gửi cookie khi người dùng đi vào từ site khác. |
| **SameSite=Lax** | Gửi trong ngữ cảnh same-site; với cross-site, thường cho phép các điều hướng cấp cao nhất dùng phương thức an toàn như GET. | Thiết lập cân bằng phổ biến cho nhiều ứng dụng web. |
| **SameSite=None** | Không giới hạn gửi theo same-site/cross-site bởi thuộc tính này; với trình duyệt hiện đại phải dùng cùng **Secure**. | Luồng cần cookie trong ngữ cảnh cross-site, vẫn chịu chính sách chặn cookie bên thứ ba. |

Ví dụ phản hồi tạo cookie phiên:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session_id=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi trình duyệt gửi request, cookie chỉ đi kèm nếu **toàn bộ quy tắc liên quan** đều phù hợp. SameSite không quyết định cookie được gửi độc lập với Domain, Path, Secure, thời hạn cookie hoặc chính sách trình duyệt.

Một số trình duyệt mặc định xử lý cookie không khai báo SameSite theo kiểu Lax; có thể tồn tại ngoại lệ tương thích tạm thời đối với cookie mới tạo. Vì vậy, với ứng dụng bảo mật, hãy đặt chính sách SameSite **tường minh**, không dựa vào hành vi mặc định hoặc ngoại lệ của một trình duyệt.

### 5.2. Cross-origin nhưng same-site: cookie có được gửi không?

Giả sử:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com
Cookie:   session_id do https://api.example.com thiết lập
~~~

Nếu cookie là host-only cookie của **api.example.com** và có SameSite=Strict hoặc Lax, trình duyệt vẫn có thể gửi nó tới API trong yêu cầu được khởi tạo từ app.example.com, vì cả hai URL thường **same-site**. Host-only cookie có thể được gửi **đến đúng host API** dù JavaScript ở host frontend không thể đọc cookie đó.

Tuy nhiên, API vẫn là **cross-origin** so với frontend. Với fetch, chế độ credentials mặc định là **same-origin**; frontend muốn gửi cookie tới API cross-origin thường cần yêu cầu rõ ràng:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});

if (!response.ok) {
  throw new Error("Không đọc được dữ liệu người dùng");
}

const profile = await response.json();
~~~

Để JavaScript đọc được phản hồi khi yêu cầu có credentials, API phải cấu hình CORS phù hợp, chẳng hạn:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng** Access-Control-Allow-Origin: * cùng với yêu cầu có credentials. Cũng cần nhớ rằng **credentials: "include" không vượt qua SameSite**, Domain/Path, Secure hay chính sách chặn cookie của trình duyệt.

### 5.3. Domain và Path khác với Site

Cookie **host-only** (không khai báo Domain) được ràng buộc với host thiết lập cookie, ví dụ **api.example.com**. Cookie có **Domain=example.com** có thể được gửi tới những host thuộc phạm vi example.com theo quy tắc cookie, bao gồm nhiều subdomain.

Nhưng SameSite vẫn được xét riêng:

~~~http
Set-Cookie: session_id=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

~~~http
Set-Cookie: shared_pref=...; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

Cookie thứ nhất chỉ dành cho host đặt cookie; cookie thứ hai có phạm vi host rộng hơn. Cả hai đều có giá trị SameSite=Lax, nhưng điều đó **không** khiến chúng có phạm vi gửi giống nhau.

Với cookie phiên nhạy cảm, ưu tiên phạm vi host hẹp khi có thể. Cookie có tiền tố **__Host-** còn yêu cầu Secure, Path=/ và không có Domain (cùng các điều kiện chấp nhận của trình duyệt), qua đó hạn chế mở rộng cookie sang subdomain:

~~~http
Set-Cookie: __Host-session=opaque-value; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Không nên nhầm **Domain=example.com** với “same-site”: một thuộc tính xác định **host có thể nhận cookie**, thuộc tính còn lại điều chỉnh **ngữ cảnh khởi tạo yêu cầu**.

### 5.4. Ngữ cảnh trang ở cấp cao và iframe

Với SameSite cookie, “site của request” không phải lúc nào cũng được tính chỉ bằng cách so URL trang nguồn và URL đích. Trình duyệt còn xét **ngữ cảnh tài liệu**, chẳng hạn site của trang cấp cao nhất và các khung nhúng liên quan. Một iframe được nhúng trong site bên ngoài có thể chịu ràng buộc cross-site ngay cả khi JavaScript bên trong iframe gọi API cùng miền với nó.

Ví dụ:

~~~text
Trang cấp cao nhất: https://external.test
    └── iframe: https://app.example.com
            └── fetch https://api.example.com
~~~

Không được suy ra rằng cookie SameSite=Strict sẽ được gửi chỉ vì app.example.com và api.example.com có cùng registrable domain; **ngữ cảnh iframe được nhúng từ external.test** có thể khiến phép xét same-site của cookie khác với ví dụ trang cấp cao nhất cùng site.

Ngoài ra, SameSite=None; Secure vẫn có thể bị ảnh hưởng bởi chính sách cookie bên thứ ba, cơ chế phân vùng cookie và các hạn chế quyền riêng tư của trình duyệt. Vì vậy, phải thử nghiệm hành vi cookie trên trình duyệt và luồng nhúng thực tế.

## 6. SameSite giúp chống CSRF nhưng không thay thế CSRF token

**Cross-Site Request Forgery (CSRF)** xảy ra khi một website hoặc nội dung không đáng tin cậy khiến trình duyệt của người dùng đã xác thực gửi một thao tác ngoài ý muốn đến ứng dụng đích.

Ví dụ, người dùng đăng nhập tại **https://bank.example**, sau đó truy cập trang giả mạo ở **https://evil.test**. Nếu một request gây tác dụng phụ được gửi kèm thông tin xác thực tự động như cookie phiên, server có nguy cơ xử lý thao tác dù người dùng không chủ ý thực hiện.

Thuộc tính SameSite có thể ngăn cookie tham gia nhiều yêu cầu **cross-site**, từ đó giảm bề mặt CSRF. Nhưng nó **không phải giải pháp đầy đủ**, vì:

1. Có các luồng cần chấp nhận cookie cross-site, ví dụ tích hợp nhúng hoặc xác thực liên miền.
2. Những request **same-site nhưng cross-origin** có thể đến từ subdomain bị kiểm soát bởi bên không đáng tin cậy.
3. SameSite và khả năng gửi cookie còn phụ thuộc kiểu điều hướng, phương thức HTTP, ngữ cảnh nhúng và hành vi trình duyệt.
4. Cấu hình sai endpoint (ví dụ dùng GET cho thao tác thay đổi trạng thái) vẫn có thể tạo rủi ro.

Ví dụ một kẻ tấn công kiểm soát **https://untrusted.example.com** trong cùng registrable domain có thể cố gửi một biểu mẫu tới **https://api.example.com/transfer**. Với trang cấp cao nhất, hai origin khác nhau nhưng **same-site**, nên chỉ dựa vào cookie SameSite không đủ để chặn request đó. SOP/CORS có thể cản việc đọc kết quả, nhưng **không phải bảo đảm rằng request gây tác dụng phụ chưa được gửi**.

Khi bảo vệ ứng dụng dùng cookie phiên:

- Dùng **CSRF token** cho các thao tác thay đổi trạng thái và xác thực token phía máy chủ.
- Duy trì yêu cầu xác thực/phân quyền cho từng endpoint, kể cả khi request đến từ same-site.
- Dùng SameSite, Secure và HttpOnly phù hợp để củng cố bảo vệ cookie.
- Có thể bổ sung kiểm tra **Origin**/**Referer**, Fetch Metadata và chính sách về request có nội dung/kiểu dữ liệu được chấp nhận, tùy mô hình rủi ro.
- Không xử lý thao tác nguy hiểm bằng GET, HEAD hoặc những phương thức dự kiến chỉ để đọc.

**CORS không phải cơ chế chống CSRF.** CORS chủ yếu quy định JavaScript được đọc phản hồi cross-origin ra sao. Một biểu mẫu hoặc cơ chế gửi request khác vẫn có thể đến máy chủ dù trình duyệt không cho mã nguồn bên ngoài đọc phản hồi.

## 7. Fetch Metadata cho biết yêu cầu same-site hay cross-site

Trình duyệt hiện đại thường có thể gửi các header **Sec-Fetch-*** để server hiểu ngữ cảnh khởi tạo request. Một header hữu ích là **Sec-Fetch-Site**.

Các giá trị thường gặp:

| Sec-Fetch-Site | Ý nghĩa |
| --- | --- |
| **same-origin** | Ngữ cảnh khởi tạo và đích thuộc cùng origin. |
| **same-site** | Khác origin nhưng cùng site. |
| **cross-site** | Ngữ cảnh khởi tạo và đích khác site. |
| **none** | Request không có site khởi tạo thông thường, ví dụ điều hướng do người dùng trực tiếp kích hoạt. |

Trong ví dụ frontend gọi API khác subdomain:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Sec-Fetch-Site: same-site
~~~

Header **Origin** cho biết origin nguồn trong ngữ cảnh request phù hợp; **Sec-Fetch-Site** cho biết **quan hệ** giữa nguồn và đích. Giá trị same-site **không đồng nghĩa** same-origin và cũng **không xác thực** người gửi.

Có thể sử dụng Fetch Metadata như một lớp bổ sung để từ chối những request nguy hiểm **cross-site** không mong muốn. Tuy nhiên:

- Không phải mọi client/trình duyệt hoặc request đều cung cấp header.
- Các HTTP client ngoài trình duyệt có thể giả lập nhiều header; đây không phải chứng chỉ danh tính.
- Chính sách chỉ từ chối **cross-site** sẽ không tự ngăn request từ một subdomain không đáng tin cậy nhưng **same-site**.
- Kiểm tra Fetch Metadata không thay thế CSRF token, authentication, authorization và kiểm tra nghiệp vụ.

Khi ứng dụng có các endpoint công khai, liên kết từ bên ngoài hoặc tích hợp bên thứ ba, phải thiết kế chính sách phù hợp thay vì chặn mọi request khác site một cách máy móc.

## 8. Áp dụng vào Spring Security với Servlet và Reactive

Giả sử hệ thống sử dụng:

~~~text
Trang frontend:  https://app.example.com
API Spring:     https://api.example.com
Cơ chế phiên:   session cookie đặt bởi API
~~~

Hai endpoint **same-site, cross-origin**. Hệ thống phải xử lý đồng thời ba việc:

1. **CORS** cho phép JavaScript ở https://app.example.com đọc phản hồi của API.
2. **Cookie/session** chỉ được gửi khi phạm vi cookie và chế độ credentials tương thích.
3. **Spring Security** vẫn phải xác thực, phân quyền và bảo vệ CSRF cho request thay đổi trạng thái.

### 8.1. Ví dụ Servlet (Spring Security 6.x)

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
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                // CSRF mặc định của Spring Security vẫn được giữ.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Cấu hình minh họa giới hạn origin được phép và đường dẫn **/api/**. Khi triển khai thực tế, cần khai báo thêm phương thức và header theo nhu cầu hợp lệ của API. Với ứng dụng dựa trên cookie/session, **giữ CSRF protection** cho POST và các thao tác thay đổi trạng thái; phải có cách cấp và gửi CSRF token phù hợp với frontend.

CORS cần được xử lý trước các bộ lọc có thể từ chối **OPTIONS preflight**, vì preflight thông thường không mang cookie phiên.

### 8.2. Ví dụ Reactive (Spring WebFlux)

Với WebFlux, API CORS source nằm trong gói **org.springframework.web.cors.reactive**:

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
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                // CSRF mặc định vẫn được giữ.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

**Lưu ý:** Hai đoạn code là hai ví dụ cấu hình **cho hai stack khác nhau**; chọn một stack phù hợp với ứng dụng. Không trộn nhầm lớp CorsConfigurationSource thuộc servlet và reactive. Việc cho phép origin cụ thể **không** cấp quyền truy cập API nếu authentication, authorization hoặc kiểm tra CSRF thất bại.

### 8.3. Tình huống thường gặp: cùng site nhưng vẫn lỗi CORS

Frontend gửi:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Đoạn code giả định **csrfToken đã được ứng dụng cấp hợp lệ**. Trình duyệt có thể gửi preflight OPTIONS vì nội dung application/json và header X-CSRF-TOKEN. Một tình huống thất bại là OPTIONS bị bộ lọc bảo mật từ chối trước khi CORS trả lời. Khi đó DevTools có thể báo lỗi CORS dù app và API **same-site**.

Các bước chẩn đoán:

1. Xem **Network → OPTIONS**, đối chiếu Origin, Access-Control-Request-Method và Access-Control-Request-Headers với chính sách CORS của API.
2. Nếu preflight bị 401/403 hoặc redirect không phù hợp, kiểm tra vị trí xử lý CORS trong security filter chain.
3. Nếu preflight đạt nhưng POST bị 403, kiểm tra CSRF token và quyền truy cập; không kết luận mọi 403 đều do CORS.
4. Nếu API trả 200 nhưng frontend không đọc được dữ liệu, kiểm tra Access-Control-Allow-Origin và Access-Control-Allow-Credentials.
5. Nếu backend không thấy cookie, kiểm tra **credentials: "include"**, Domain, Path, Secure, SameSite, môi trường iframe và chính sách cookie của trình duyệt.
6. Nếu dùng reverse proxy, kiểm tra URL/Origin mà trình duyệt thực sự dùng, cũng như cấu hình scheme/host/port và CORS header trên proxy.

Có thể quan sát phản hồi preflight từ server bằng:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Lệnh curl giúp **quan sát HTTP header**, nhưng curl **không thực thi SOP hoặc CORS** theo cách trình duyệt làm. Với Windows PowerShell, dùng **curl.exe** nếu cần tránh bí danh curl của PowerShell.

## 9. Tình huống bảo mật: subdomain bị chiếm quyền

Giả sử doanh nghiệp có ba ứng dụng:

~~~text
https://app.example.com       (trang chính)
https://api.example.com       (API cần cookie phiên)
https://blog.example.com      (blog do bên thứ ba vận hành)
~~~

Theo phép so sánh schemeful site, cả ba đều thuộc **https://example.com**. Nhưng nếu blog cho phép chèn script tùy ý hoặc bị tấn công, script từ blog có thể tạo request **same-site nhưng cross-origin** tới API.

Điều này dẫn đến ba kết luận:

- **SameSite cookie không đủ** để coi mọi request từ blog là hợp lệ: quan hệ same-site không chứng minh hai ứng dụng cùng mức tin cậy.
- **CORS cần giới hạn origin cụ thể**. Nếu phản chiếu tùy tiện mọi Origin hoặc cho phép tất cả subdomain với credentials, blog có thể đọc những phản hồi nhạy cảm không nên đọc được.
- **CSRF token, authentication và authorization vẫn bắt buộc** cho các thao tác thay đổi trạng thái dùng cookie phiên. Chỉ dựa vào Sec-Fetch-Site: same-site để bỏ qua xác thực yêu cầu cũng là quyết định nguy hiểm.

Trong kiến trúc nhiều tenant hoặc nhiều subdomain không cùng mức tin cậy, xem xét tách ứng dụng không đáng tin cậy sang **registrable domain** riêng, đồng thời giới hạn phạm vi cookie bằng cách dùng host-only cookie và thiết kế chính sách CORS riêng cho API.

## 10. Bài tập tự kiểm tra

### Tình huống 1 — Khác port

Trang **https://localhost:3000** gọi **https://localhost:8443/api**. Hai URL có same-origin và same-site không? Nếu fetch muốn đọc JSON, có cần CORS không?

**Gợi ý đáp án:** Cross-origin vì khác port; same-site trong ngữ cảnh host localhost và scheme https giống nhau. Fetch đọc phản hồi cross-origin vẫn cần cấu hình CORS phù hợp.

### Tình huống 2 — Khác giao thức

Trang **http://app.example.com** gọi **https://api.example.com**. Hai URL có same-site không khi dùng schemeful same-site?

**Gợi ý đáp án:** Không. Dù cùng registrable domain example.com, scheme http và https khác nhau nên cross-site; đồng thời cũng cross-origin.

### Tình huống 3 — Hậu tố công cộng

Hai host **pay.example.co.uk** và **docs.example.co.uk** đều dùng HTTPS. Chúng có same-site không? Phải dựa vào phần nào để biết điều đó?

**Gợi ý đáp án:** Có, theo cách xét thông thường: đều thuộc registrable domain example.co.uk và cùng scheme https. Cần nhận ra co.uk là public suffix thông qua PSL, không lấy máy móc hai nhãn cuối.

### Tình huống 4 — Cookie cross-origin cùng site

Frontend **https://app.example.com** gọi API **https://api.example.com** qua fetch, sử dụng cookie phiên mà API đã đặt cho host api.example.com với SameSite=Strict. Cookie có thể được gửi không, và chỉ đặt SameSite=Strict đã đủ chưa?

**Gợi ý đáp án:** Có thể được gửi trong ngữ cảnh same-site phù hợp, miễn các quy tắc cookie và chế độ credentials cho phép. Vì vẫn cross-origin, fetch cần credentials phù hợp và API cần CORS cho phản hồi có credentials. SameSite=Strict không thay thế CSRF token hoặc kiểm tra quyền.

### Tình huống 5 — CSRF từ subdomain

**https://untrusted.example.com** có thể tạo form gửi POST đến **https://api.example.com**. Cả hai cùng HTTPS. Bật SameSite=Lax có chắc ngăn được CSRF không?

**Gợi ý đáp án:** Không. Đây thường là yêu cầu same-site dù cross-origin. Trong mô hình phiên cookie, server phải kiểm tra CSRF token hoặc biện pháp chống CSRF phù hợp; đồng thời bảo vệ endpoint bằng authentication và authorization.

### Tình huống 6 — Fetch Metadata

Một request đến API có **Sec-Fetch-Site: same-site** và **Origin: https://cms.example.com**, trong khi API ở **https://api.example.com**. Có nên bỏ qua CSRF token vì header đã cho biết same-site không?

**Gợi ý đáp án:** Không. same-site chỉ cho biết quan hệ site, không xác nhận người dùng chủ ý thực hiện thao tác hoặc origin có đáng tin cậy không. Cần đánh giá mức tin cậy của cms, áp dụng chính sách CSRF và phân quyền như thiết kế.

## 11. Ghi nhớ

- **Origin = scheme + host + port.** Origin được dùng để xác định ranh giới SOP và cơ chế CORS.
- **Schemeful site = scheme + registrable domain** đối với miền HTTP/HTTPS thông thường; việc xác định registrable domain phụ thuộc Public Suffix List. Với host không có registrable domain, phải dùng quy tắc phù hợp cho host đó.
- **Same-site có thể vẫn cross-origin** khi khác subdomain hoặc port. **HTTP và HTTPS khác site** theo cách xét schemeful.
- **SameSite cookie dựa trên ngữ cảnh site** và các điều kiện cookie khác; **CORS dựa trên origin** và điều chỉnh quyền JavaScript đọc phản hồi.
- **Same-site không đồng nghĩa đáng tin cậy.** Một subdomain bị chiếm quyền có thể cùng site với API nhạy cảm.
- Khi dùng Spring Security trên **Servlet hoặc Reactive**, hãy kết hợp CORS đúng origin, chính sách cookie phù hợp, CSRF protection, authentication và authorization. Phân biệt rõ lỗi CORS, cookie, CSRF và quyền truy cập khi chẩn đoán.
