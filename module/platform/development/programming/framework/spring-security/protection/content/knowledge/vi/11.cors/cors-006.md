# Allowed origin patterns và phạm vi tin cậy được mở

## 1. Mục tiêu và bối cảnh

Trong mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, CORS là một trong các lớp phòng vệ HTTP và trình duyệt của Spring Security. Khi API phải phục vụ nhiều frontend khác origin, nhóm phát triển thường muốn cấu hình ngắn gọn, chẳng hạn cho phép tất cả subdomain trong một miền. Spring Framework cung cấp `CorsConfiguration#setAllowedOriginPatterns` để diễn đạt yêu cầu này.

Vấn đề quan trọng hơn cú pháp là **mỗi origin khớp với pattern được phép cho JavaScript tại origin đó đọc phản hồi CORS của API**. Nếu API sử dụng session cookie, quyền đọc có thể áp dụng cho dữ liệu của người dùng đang đăng nhập. Vì vậy mở rộng pattern cũng là **mở rộng ranh giới tin cậy**.

Sau bài học, người học có thể:

1. Phân biệt `allowedOrigins`, `allowedOriginPatterns` và header `Access-Control-Allow-Origin`.
2. Hiểu cách pattern của Spring so khớp scheme, hostname và port; biết các tình huống thường khớp hoặc không khớp.
3. Giải thích vì sao pattern được Spring hỗ trợ cùng credentials về mặt kỹ thuật nhưng vẫn có thể gây lộ dữ liệu khi cấu hình rộng.
4. Đánh giá các nguồn rủi ro: subdomain cho người dùng tự tạo, hosting bên thứ ba, subdomain takeover, XSS, tên miền thử nghiệm và thay đổi DNS.
5. Tích hợp CORS Servlet và Reactive; kiểm tra cả trường hợp cho phép và từ chối bằng preflight, trình duyệt và bài test tích hợp.
6. Thiết kế allowlist theo môi trường, tenant và mức độ tin cậy, đồng thời duy trì authentication, authorization, CSRF và bảo vệ session.

Các hostname `.example.com` và `.test` dưới đây là ví dụ giả định. Khi triển khai thực tế phải thay bằng origin của tổ chức.

## 2. Nhắc lại: CORS cấp quyền đọc cho một origin

**Origin** là bộ ba *scheme + host + port*. Ví dụ hai địa chỉ:

- `https://app.example.com`
- `https://app.example.com:8443`

là hai origin khác nhau vì port khác nhau. Trong khi đó `https://app.example.com/dashboard` và `https://app.example.com/profile` cùng origin; đường dẫn không tham gia định danh origin.

JavaScript chạy ở `https://team.ui.example.com` gửi:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://team.ui.example.com
~~~

Server chỉ nên cho JavaScript đọc response khi origin đó thuộc tập được tin cậy theo chính sách CORS. Response có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://team.ui.example.com
Vary: Origin

{"userId":42,"displayName":"Lan"}
~~~

`Access-Control-Allow-Origin` là header **server trả cho browser**. Giá trị của header này phải là một origin cụ thể được phép hoặc `*` khi quy tắc wildcard của CORS cho phép. Một pattern dạng `https://*.ui.example.com` không phải giá trị hợp lệ để browser tự mở rộng trong response header.

CORS không thay thế xác thực hay phân quyền: một trang được phép đọc response chỉ nhận dữ liệu mà request đã được API xác thực và cho phép. Ngược lại, một client như `curl` có thể tự đặt `Origin` và không bị SOP của browser chi phối; API vẫn phải kiểm tra quyền truy cập.

## 3. Ba cơ chế dễ nhầm với nhau

| Thành phần | Nơi cấu hình / xuất hiện | Ý nghĩa |
| --- | --- | --- |
| `setAllowedOrigins(List.of("https://app.example.com"))` | Cấu hình Spring Framework | Cho phép các origin được khai báo cụ thể |
| `setAllowedOriginPatterns(List.of("https://*.ui.example.com"))` | Cấu hình Spring Framework | Cho phép các origin **khớp mẫu** |
| `Access-Control-Allow-Origin: https://a.ui.example.com` | HTTP response từ API | Cho phép browser ở đúng origin này đọc response nếu các điều kiện khác hợp lệ |
| `Access-Control-Allow-Origin: *` | HTTP response từ API | Wildcard toàn phần, chỉ hợp lệ trong những trường hợp tương ứng của CORS |

Ví dụ:

~~~java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;

CorsConfiguration cors = new CorsConfiguration();

cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
~~~

Khi một request hợp lệ mang `Origin: https://team.ui.example.com`, Spring kiểm tra origin này với pattern; nếu khớp, Spring thường phát **origin cụ thể** trong response:

~~~http
Access-Control-Allow-Origin: https://team.ui.example.com
Vary: Origin
~~~

Spring **không** phát:

~~~http
# Không phải response hợp lệ theo cú pháp CORS:
Access-Control-Allow-Origin: https://*.ui.example.com
~~~

Điểm khác biệt cốt lõi: **pattern chỉ là cách server quyết định origin nào được chấp nhận**; browser xét giá trị `Access-Control-Allow-Origin` đã được server trả về, không chạy lại thuật toán pattern của Spring.

## 4. Cú pháp allowedOriginPatterns trong Spring

Spring Framework hỗ trợ origin pattern với ký tự `*` trong phần hostname và danh sách port đặt sau dấu hai chấm trong ngoặc vuông. Những ví dụ điển hình:

~~~java
CorsConfiguration cors = new CorsConfiguration();

// Cho phép một miền giao diện với các subdomain phù hợp.
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
~~~

~~~java
// Ví dụ port cụ thể cho môi trường phát triển có kiểm soát.
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com:[8443,9443]"
));
~~~

~~~java
// Cho phép mọi port của các hostname khớp mẫu.
// Chỉ dùng khi thực sự có lý do và đánh giá được phạm vi mở rộng.
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com:[*]"
));
~~~

Các điểm cần nhớ:

- **Scheme:** `https://...` không tự cho phép `http://...`. Mở HTTP vì tiện kiểm thử có thể tạo thêm rủi ro khi triển khai.
- **Host:** wildcard trong pattern được Spring áp dụng khi so khớp origin. Đừng suy luận nó chỉ có thể khớp đúng một cấp subdomain; hãy kiểm thử những hostname nhiều nhãn như `a.b.ui.example.com` nếu mô hình DNS có thể sinh ra chúng.
- **Port:** origin có port khác mặc định là origin khác. Dùng đúng danh sách port mà trình duyệt có thể gửi. Pattern cho port bất kỳ mở phạm vi nhiều hơn một allowlist port cụ thể.
- **Path:** `/login` hoặc `/api` không thuộc origin và không nên đặt trong pattern origin. Path của API được giới hạn riêng bằng cách đăng ký `CorsConfiguration` cho `/api/**`.
- **Giá trị `*`:** `setAllowedOriginPatterns(List.of("*"))` có nghĩa là cho phép **mọi origin** theo cơ chế pattern của Spring, không phải “mọi subdomain được tin cậy”.
- **Không phải regex:** đừng đưa biểu thức chính quy Java như `^https://.*\\.example\\.com$` vào và giả định Spring sẽ hiểu theo cú pháp regex.

Một `allowedOriginPatterns` rộng có thể khớp nhiều origin hơn dự kiến. Cần thử nghiệm chính sách thực tế với chính phiên bản Spring đang triển khai trước khi xem pattern là an toàn.

### 4.1. Bảng đối chiếu cụ thể

Giả sử:

~~~java
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
~~~

Với cách dùng pattern hostname thông thường của Spring, các tình huống nên kiểm thử là:

| Origin gửi tới API | Kết quả dự kiến | Lý do |
| --- | --- | --- |
| `https://team.ui.example.com` | Khớp | Subdomain phù hợp pattern |
| `https://admin.ui.example.com` | Khớp | Một subdomain khác cùng phạm vi |
| `https://a.b.ui.example.com` | Có thể khớp | `*` trong Spring có thể bao phủ nhiều ký tự, cần thử các cấp hostname |
| `https://ui.example.com` | Không khớp mẫu `*.ui.example.com` | Mẫu yêu cầu dấu chấm và phần subdomain ở phía trước |
| `http://team.ui.example.com` | Không khớp | Scheme khác |
| `https://team.ui.example.com:8443` | Không khớp với mẫu không khai báo port 8443 | Port khác |
| `https://team.ui.example.com.evil.test` | Không khớp | Phần hậu tố hostname không đúng |
| `https://evil.test` | Không khớp | Host ngoài phạm vi |

Chú ý: **khớp pattern về cú pháp không đồng nghĩa frontend đó đáng tin cậy**. Dòng `admin.ui.example.com` chỉ an toàn khi hostname thật sự do đội vận hành tin cậy kiểm soát; mọi origin khớp đều được hưởng quyền đọc CORS tương ứng.

Nếu cần cho phép cả hostname gốc `https://ui.example.com`, hãy cấu hình nó một cách riêng biệt và có chủ đích, thay vì coi ký tự `*` chắc chắn bao phủ cả hostname gốc.

### 4.2. Có thể kết hợp origin cụ thể và pattern không?

Spring cho phép cấu hình các nguồn origin được phép theo nhu cầu, nhưng điều đó **mở rộng tập origin được chấp nhận**. Tránh thêm pattern rộng bên cạnh allowlist cụ thể mà không nhận ra nó có thể làm allowlist mất ý nghĩa.

Ví dụ:

~~~java
CorsConfiguration cors = new CorsConfiguration();

cors.setAllowedOrigins(List.of(
    "https://app.example.com"
));
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
~~~

Chính sách này có thể chấp nhận origin cụ thể `https://app.example.com` **và** các origin khớp `https://*.ui.example.com`. Hãy xem cả hai tập như phạm vi tin cậy của API khi rà soát; không chỉ đọc danh sách cụ thể rồi bỏ qua pattern.

## 5. Pattern cùng credentials: hợp lệ về kỹ thuật, rủi ro về tin cậy

Spring Framework cho phép `allowedOriginPatterns` phối hợp với `allowCredentials(true)`. Khi origin khớp pattern, Spring trả **giá trị origin cụ thể**, vì vậy đáp ứng quy tắc browser không cho dùng `Access-Control-Allow-Origin: *` với request `credentials: "include"`.

Ví dụ:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
cors.setAllowCredentials(true);
~~~

Trang ở `https://team.ui.example.com` có thể gửi:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const profile = await response.json();
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://team.ui.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"userId":42,"email":"lan@example.com"}
~~~

Nếu cookie được browser gửi, người dùng đã đăng nhập và các điều kiện CORS đều hợp lệ, JavaScript từ `team.ui.example.com` có thể đọc dữ liệu cá nhân.

**Đây là một quyền rất đáng chú ý:** với `allowCredentials(true)`, mỗi origin khớp pattern có thể trở thành nơi đọc dữ liệu người dùng dựa trên session cookie. Vì vậy pattern phải phản ánh **tập ứng dụng được tin cậy**, không phản ánh “mọi DNS record thuộc cùng tên miền công ty”.

### 5.1. Vì sao `allowedOrigins("*")` khác `allowedOriginPatterns("*")`?

Hai cấu hình sau nhìn giống nhau nhưng khác cách Spring tạo response:

~~~java
// CORS wildcard ở allowedOrigins + credentials:
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true); // Không phải tổ hợp hợp lệ.
~~~

~~~java
// Pattern wildcard + credentials:
cors.setAllowedOriginPatterns(List.of("*"));
cors.setAllowCredentials(true); // Có thể được Spring chấp nhận về mặt cú pháp.
~~~

Ở trường hợp đầu, Spring không cho phép kết hợp wildcard origin `*` và credentials theo cách đó. Ở trường hợp thứ hai, Spring có thể phản chiếu **origin cụ thể đã khớp pattern `*`** vào response và gửi `Access-Control-Allow-Credentials: true`.

Tổ hợp thứ hai **vô cùng rộng**: bất kỳ origin nào cũng có thể được phản hồi là origin được cấp quyền đọc response chứa credentials. Việc nó hợp lệ theo cú pháp browser không có nghĩa nó an toàn trong ứng dụng có session cookie hoặc dữ liệu riêng tư.

### 5.2. Phân biệt mode của Fetch với việc cookie có thực sự được gửi

`credentials: "include"` khiến browser áp dụng kiểm tra CORS dành cho credentials mode tương ứng. Trình duyệt có thể vẫn **không gửi cookie** do `SameSite`, `Secure`, domain/path hoặc chính sách cookie bên thứ ba. Việc không thấy `Cookie` trong request **không làm** `Access-Control-Allow-Origin: *` trở thành hợp lệ đối với mode `include`.

Nếu backend dùng bearer token do frontend tự đặt qua `Authorization`, vẫn phải kiểm tra preflight cho header này và xác thực token ở API. Không vì có token mà coi origin tự động đáng tin cậy; một frontend độc hại có thể khai thác những nơi backend hoặc browser cung cấp quyền truy cập, đặc biệt khi còn tồn tại đường xác thực cookie.

## 6. Kịch bản tấn công: subdomain của người dùng được pattern cấp quyền

Giả sử tổ chức có:

- API xác thực bằng session cookie: `https://api.example.com`.
- Frontend chính thức: `https://app.example.com`.
- Dịch vụ cho khách hàng tự tạo trang HTML/JavaScript: `https://customer-123.ui.example.com`.

Đội phát triển đặt:

~~~java
cors.setAllowedOriginPatterns(List.of(
    "https://*.ui.example.com"
));
cors.setAllowCredentials(true);
~~~

Kẻ tấn công hợp pháp đăng ký một subdomain `attacker.ui.example.com` trong dịch vụ tạo trang. Người dùng đã đăng nhập API, đồng thời truy cập trang đó. Nếu browser cho phép gửi cookie API trong ngữ cảnh này và API trả dữ liệu theo session, JavaScript trên trang của kẻ tấn công có thể thực hiện:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const profile = await response.json();

// Kẻ tấn công có thể sử dụng dữ liệu mà browser đã cho JavaScript đọc.
console.log(profile);
~~~

Browser gửi:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://attacker.ui.example.com
Cookie: SESSION=<session-cookie-if-allowed>
~~~

Nếu Spring cho origin này qua pattern:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://attacker.ui.example.com
Access-Control-Allow-Credentials: true

{"userId":42,"email":"lan@example.com"}
~~~

JavaScript ở subdomain do kẻ tấn công kiểm soát có thể đọc dữ liệu của người dùng. **Không cần giả mạo header `Origin` trong browser**: kẻ tấn công đang chạy code ở một origin thực sự khớp pattern.

### 6.1. Vì sao SameSite có thể không cứu được cấu hình?

`https://attacker.ui.example.com` và `https://api.example.com` là **khác origin**, nhưng về chính sách cookie thông thường vẫn là **same-site**: cùng scheme HTTPS và registrable domain `example.com`.

Vì vậy một session cookie `SameSite=Lax` hoặc `SameSite=Strict` của API vẫn có thể được gửi trong request same-site thích hợp, nếu Fetch dùng `credentials: "include"` và các điều kiện cookie khác đạt. `SameSite` không phân biệt frontend chính thức với một subdomain nguy hiểm cùng site.

Đây là lý do **CORS allowlist** phải kiểm soát nơi JavaScript được đọc dữ liệu; chỉ dựa vào thuộc tính `SameSite` là chưa đủ để bù lại pattern quá rộng.

### 6.2. Nếu API yêu cầu token và phân quyền thì sao?

Authentication và authorization vẫn rất quan trọng; nếu request không có thông tin đăng nhập hợp lệ, API phải từ chối. Nhưng không nên giả định điều này khắc phục mọi rủi ro của CORS: ứng dụng có thể có session cookie, một endpoint dùng cookie cũ, hoặc thông tin phản hồi mà attacker đọc được khi browser tự đính kèm credentials. Trên một ứng dụng đã xác thực, CORS vẫn quyết định frontend nào được browser chia sẻ dữ liệu.

**Biện pháp phù hợp:** tách các subdomain cho người dùng tự đưa JavaScript lên khỏi tập frontend tin cậy; sử dụng hostname hoặc site riêng cho nội dung không tin cậy, và allowlist origin cụ thể với API nhạy cảm.

## 7. Nguồn gốc thực tế của phạm vi tin cậy mở rộng

Pattern hostname không phân tích được **ai đang điều khiển nội dung JavaScript** tại mỗi origin. Những trường hợp sau đều cần rà soát:

| Tình huống | Vì sao pattern có thể nguy hiểm? | Cách kiểm soát |
| --- | --- | --- |
| User-generated subdomain | Người dùng có thể tự đưa JavaScript lên origin khớp pattern | Tách miền hosting không tin cậy, tránh cho pattern credentials bao phủ |
| Subdomain takeover | DNS `CNAME` trỏ đến dịch vụ bên thứ ba đã bị bỏ hoặc chưa claim | Kiểm kê DNS, gỡ record mồ côi, kiểm soát quyền claim |
| Hosting/preview theo từng nhánh | Bản preview chứa code chưa được duyệt nhưng khớp wildcard | Tách môi trường, giới hạn quyền truy cập và origin |
| Subdomain của nhà cung cấp | Bên thứ ba quản lý nội dung hoặc chính sách bảo mật | Chỉ đưa origin vào allowlist sau đánh giá và kiểm soát quyền |
| XSS trên một subdomain | Script bị chèn có thể tận dụng CORS quyền của origin đó | Khắc phục XSS, CSP phù hợp, giảm số origin có quyền đọc |
| Môi trường staging/dev | App thử nghiệm có kiểm soát lỏng hơn production | Dùng allowlist, API và session tách môi trường |
| Wildcard port | Origin trên dịch vụ khác port có thể nhận quyền ngoài dự định | Khai báo đúng port hoặc không dùng wildcard port |
| Thay đổi ownership/DNS | Một hostname từng tin cậy có thể đổi người vận hành | Rà soát origin định kỳ và sau khi ngừng dịch vụ |

**TLS không đủ để chứng minh frontend đáng tin:** một subdomain có chứng chỉ HTTPS hợp lệ vẫn có thể chứa nội dung do khách hàng tự kiểm soát. Tương tự, cùng registrable domain không có nghĩa cùng mức độ tin cậy hay cùng chủ quản ứng dụng.

### 7.1. Không dùng phép so chuỗi đơn giản để thay Spring CORS

Hai ví dụ sai:

~~~java
// SAI: attacker.example.com.evil.test có thể lọt nếu chỉ kiểm tra chuỗi con.
boolean allowed = origin.contains("example.com");

// SAI: https://app.example.com.attacker.test bắt đầu cùng tiền tố.
boolean allowedByPrefix =
    origin.startsWith("https://app.example.com");
~~~

Không chỉ thiếu kiểm tra hostname trọn vẹn, cách này còn dễ bỏ qua scheme, port, `Origin: null` và định dạng origin bất thường. Hãy dùng danh sách origin cụ thể hoặc cơ chế pattern của framework, kết hợp đánh giá **quyền sở hữu và mức tin cậy thực tế** của từng nhóm host.

## 8. Thiết kế chính sách an toàn hơn cho nhiều frontend

Cách tiếp cận tùy thuộc phạm vi và nguồn gốc của frontend:

| Nhu cầu | Lựa chọn phù hợp | Điều cần tránh |
| --- | --- | --- |
| Một vài frontend production cố định | `allowedOrigins` với danh sách chính xác | Mở wildcard chỉ để tránh quản lý vài địa chỉ |
| Nhiều frontend nội bộ do một nhóm kiểm soát | Pattern giới hạn trong namespace được quản trị chặt | Đưa host preview/user-content vào cùng namespace |
| Nhiều tenant có domain riêng | Registry các origin đã được tenant xác minh, allowlist động có kiểm soát | Lấy mọi giá trị `Origin` rồi phản chiếu vô điều kiện |
| Local development | Origin localhost kèm đúng port ở cấu hình dev | Mở mọi port localhost trong production |
| API công khai, không dùng credentials | Cân nhắc CORS wildcard với yêu cầu truy cập công khai thực sự | Dùng wildcard cho dữ liệu cá nhân hóa |
| API quản trị hoặc có dữ liệu nhạy cảm | Origin cụ thể, session và authorization chặt | Pattern bao phủ mọi subdomain tổ chức |

### 8.1. Ví dụ tập frontend nội bộ hữu hạn

Thay vì pattern:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
    "https://app.example.com",
    "https://admin.example.com",
    "https://reports.example.com"
));
cors.setAllowCredentials(true);
~~~

Dù có thêm vài frontend về sau, allowlist cụ thể vẫn dễ rà soát: mỗi origin mới cần có lý do và một người chịu trách nhiệm vận hành.

### 8.2. Khi buộc phải dùng pattern

Giả sử tất cả frontend tin cậy được triển khai duy nhất trong namespace `*.internal-ui.example.com` do một đội chuyên trách quản lý. Nếu quy trình quản trị DNS/hosting đảm bảo không có subdomain do người ngoài chi phối, có thể cân nhắc:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.internal-ui.example.com"
));
cors.setAllowCredentials(true);
~~~

Cần có những điều kiện thực tế đi kèm:

1. Không cho người dùng, tenant hoặc đối tác tự đặt JavaScript tại một origin khớp.
2. Kiểm soát vòng đời DNS, chứng chỉ và ứng dụng để tránh subdomain bị chiếm.
3. Dùng HTTPS; không tự mở `http://` khi không cần.
4. Giới hạn port, môi trường và đường dẫn API đúng nơi áp dụng chính sách.
5. Có kiểm thử origin không tin cậy và cập nhật khi mô hình hosting thay đổi.
6. Xác thực, phân quyền và CSRF vẫn áp dụng cho actual request.

**Ranh giới bảo mật không nằm ở tên pattern đẹp hay xấu, mà ở tập ứng dụng có thể thực sự khớp pattern và chạy JavaScript.**

### 8.3. Nhiều tenant với custom domain

Trong ứng dụng đa tenant, có thể có frontend tại `https://store-one.customer.test` và `https://store-two.partner.test`. Pattern chung như `https://*` không xác nhận domain thuộc tenant hợp lệ. Một thiết kế chắc chắn hơn:

- Tenant đăng ký origin chính xác, server **xác minh quyền kiểm soát origin** qua quy trình độc lập, rồi lưu trong registry tin cậy.
- Chính sách CORS tìm origin trong registry đã được duyệt, không phản chiếu bất kỳ `Origin` nào.
- Danh tính người dùng hoặc token vẫn phải được ánh xạ tới tenant có quyền truy cập dữ liệu. **CORS không thay thế kiểm soát truy cập tenant**.
- Chỉ cho phép credentials nếu thật sự cần; nếu dùng cookie trên domain khác site, kiểm tra `SameSite=None; Secure`, chính sách cookie bên thứ ba và rủi ro CSRF.
- Thu hồi origin khi tenant ngừng hợp đồng, chuyển domain hoặc mất quyền kiểm soát.

Trong Spring, có thể triển khai `CorsConfigurationSource` trả cấu hình theo đường dẫn/yêu cầu dựa trên registry được kiểm soát. Không nên truy vấn dữ liệu rồi cấp quyền rộng chỉ dựa trên hostname do client khai báo. Phần xác minh tenant và domain là trách nhiệm của hệ thống vận hành, không tự có từ `allowedOriginPatterns`.

## 9. Cấu hình Spring Security Servlet

Với Spring MVC + Spring Security, có thể đăng ký `CorsConfigurationSource` và bật `http.cors(...)` để xử lý preflight đủ sớm:

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
class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chỉ dùng pattern nếu toàn bộ namespace được quản trị tin cậy.
        cors.setAllowedOriginPatterns(List.of(
            "https://*.internal-ui.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Ý nghĩa:**

- `allowedOriginPatterns` xác định tập origin frontend; không phải tên miền của API.
- `setAllowCredentials(true)` cho phép response CORS dành cho credentials mode phù hợp; không tạo cookie hoặc xác thực session.
- `allowedMethods`/`allowedHeaders` dùng khi browser thực hiện preflight, chẳng hạn `PUT` hoặc `Content-Type: application/json`.
- `registerCorsConfiguration("/api/**", cors)` áp dụng chính sách cho **đường dẫn API**, độc lập với pattern origin.
- `http.cors(Customizer.withDefaults())` giúp preflight được xử lý trước các filter yêu cầu xác thực khiến OPTIONS bị từ chối vì thiếu cookie.
- `anyRequest().authenticated()` là điều kiện bảo vệ actual request. Ví dụ chưa cấu hình cơ chế đăng nhập/token; dự án thực cần bổ sung authentication, authorization, CSRF và bảo vệ session.

Nếu ứng dụng đã cấu hình CORS tại Spring MVC bằng `@CrossOrigin` hoặc `WebMvcConfigurer`, cần tránh thiết lập trái ngược với cấu hình Security hoặc gateway. Đừng đồng thời bật nhiều nơi tự động phản chiếu origin làm response có header CORS lặp.

## 10. Cấu hình Spring Security Reactive / WebFlux

Trong Spring WebFlux, sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain` cùng nguồn CORS reactive:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOriginPatterns(List.of(
            "https://*.internal-ui.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }
}
~~~

Ý nghĩa pattern và header trả về giống ở Servlet. Điểm khác là pipeline và các thành phần `org.springframework.web.cors.reactive`. Nếu sử dụng `CorsWebFilter` độc lập, kiểm soát thứ tự tương đối với Spring Security và tránh nhiều filter cùng chèn `Access-Control-Allow-Origin`.

Cả Servlet và Reactive đều phải xử lý **preflight OPTIONS** phù hợp trước khi cơ chế xác thực làm nó lỗi vì thiếu cookie/token. Đồng thời, actual request vẫn phải qua authentication, authorization và CSRF protection theo loại ứng dụng. Pattern CORS không cấp quyền endpoint.

## 11. Kiểm thử cả positive và negative cases

Một cấu hình pattern chỉ được đánh giá tốt khi đã kiểm tra cả **origin khớp** và **origin không được tin cậy**. Chỉ thử frontend chính thức hoạt động là chưa đủ.

### 11.1. Ma trận thực tế

Giả sử chỉ khai báo `https://*.internal-ui.example.com`, `allowCredentials(true)` và cho phép `GET`/`POST`/`PUT`.

| Origin frontend | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| `https://app.internal-ui.example.com` | Cho phép | Khớp hostname pattern |
| `https://reports.internal-ui.example.com` | Cho phép | Khớp hostname pattern |
| `https://internal-ui.example.com` | Không khớp mẫu nếu chỉ có `*.internal-ui.example.com` | Thiếu phần subdomain trước dấu chấm |
| `http://app.internal-ui.example.com` | Từ chối | Sai scheme |
| `https://app.internal-ui.example.com:8443` | Từ chối nếu không khai báo port này | Sai port |
| `https://app.internal-ui.example.com.evil.test` | Từ chối | Hostname ngoài phạm vi |
| `https://evil.test` | Từ chối | Origin không có trong chính sách |
| `https://user-upload.example.com` | Từ chối | Tách vùng do người dùng kiểm soát khỏi namespace tin cậy |
| `null` | Từ chối | Opaque origin không được cấp quyền |

Ngay cả khi `https://reports.internal-ui.example.com` khớp, phải xác minh ứng dụng ở host này có đủ tin cậy. Nếu nó cho phép tự tải HTML có script lên, đó là vấn đề ở **mô hình tin cậy**, không phải lỗi của thuật toán so khớp.

### 11.2. Thử actual request bằng curl

~~~bash
# Origin khớp pattern:
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.internal-ui.example.com"

# Origin khác scheme:
curl -i "https://api.example.com/api/me" \
  -H "Origin: http://app.internal-ui.example.com"

# Host giả gần giống:
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.internal-ui.example.com.evil.test"
~~~

Khi origin khớp, response CORS có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.internal-ui.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Khi origin không được phép, đừng chỉ nhìn HTTP 200/403 mà đoán chính sách: xem response có `Access-Control-Allow-Origin` phù hợp hay không. Spring CORS thường trả `403 Invalid CORS request` khi xử lý request CORS không hợp lệ, nhưng gateway/filter có thể thay đổi biểu hiện.

`curl` không thực thi SOP/CORS như trình duyệt. Nếu API xác thực, curl không có session hợp lệ có thể nhận 401/403; đó là kiểm tra authentication và không thay thế việc xác minh origin trên preflight.

### 11.3. Thử preflight với credentials mode dự kiến

Giả sử frontend gọi `PUT` JSON kèm `X-CSRF-TOKEN`, browser gửi preflight:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.internal-ui.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Response hợp lệ có thể bao gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.internal-ui.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Thử lại với `Origin: https://evil.test` và xác minh preflight bị từ chối. Trong browser, preflight bị từ chối nghĩa là actual `PUT` không được gửi. Ngược lại, với request không cần preflight, server có thể đã nhận actual request trước khi browser quyết định JavaScript không được đọc response.

### 11.4. Ví dụ kiểm thử Servlet qua MockMvc

Với Spring Boot và Spring Security được cấu hình như mục 9:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPatternIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void permitsControlledSubdomain() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.internal-ui.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.internal-ui.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void rejectsUntrustedOrigin() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.test")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsHostnameWithUntrustedSuffix() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin",
                    "https://app.internal-ui.example.com.evil.test")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là mẫu kiểm thử giúp nêu rõ hành vi mong muốn của cấu hình minh họa, **không phải kết quả test đã chạy**. Khi dùng phiên bản Spring hoặc custom gateway khác, cần điều chỉnh chi tiết HTTP status nhưng luôn kiểm tra không cấp quyền đọc CORS cho origin ngoài chính sách.

Với WebFlux, dùng `WebTestClient` cùng các header `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`, xác minh response CORS trên `SecurityWebFilterChain` thực tế.

## 12. Chẩn đoán xung đột trong triển khai

| Dấu hiệu | Khả năng cần điều tra | Cách xác minh |
| --- | --- | --- |
| Frontend ở một subdomain mới bị lỗi | Pattern thiếu namespace, scheme hoặc port | Xem `Origin` thực tế và cấu hình Spring |
| Subdomain gốc không được chấp nhận | Mẫu `*.example.com` không nhất thiết bao gồm hostname gốc | Thêm origin gốc chính xác nếu cần và tin cậy |
| Local dev dùng `http` nhưng pattern chỉ `https` | Scheme không khớp | Tách cấu hình dev, tránh nới production |
| Một subdomain upload của người dùng đọc được dữ liệu phiên | Pattern quá rộng so với ranh giới tin cậy | Thu hẹp/loại origin đó, kiểm tra truy cập dữ liệu |
| `allowCredentials(true)` + `allowedOrigins("*")` gây lỗi | Tổ hợp wildcard không hợp lệ | Dùng allowedOrigins cụ thể; không lách bằng pattern `*` |
| Browser báo wildcard với credentials | Server/proxy trả `Access-Control-Allow-Origin: *` | Đảm bảo origin cụ thể và `Allow-Credentials: true` |
| OPTIONS nhận 401/403 | Security filter hoặc gateway chặn preflight trước CORS | Kiểm tra vị trí CORS trong Servlet/Reactive và proxy |
| Preflight được phép nhưng frontend vẫn lỗi | Actual response hoặc response lỗi thiếu quyền CORS | Kiểm tra `Allow-Origin` và `Allow-Credentials` trên actual response |
| Một số origin bị lỗi ngẫu nhiên sau CDN | Cache thiếu `Vary: Origin`, trộn response giữa origin | Kiểm tra cache key và header Vary |
| Header CORS lặp, browser từ chối | MVC/Security/gateway cùng ghi `Allow-Origin` | Đặt một chính sách nhất quán và một nơi chịu trách nhiệm |
| CORS đúng nhưng browser không gửi cookie | `SameSite`, `Secure`, Fetch credentials mode, chính sách cookie | Kiểm tra DevTools Cookies và request thực tế |
| API trả 403 dù origin hợp lệ | Authentication, authorization, CSRF hoặc endpoint policy | Xem log/security chain cho actual request |

Ở hệ thống có reverse proxy và TLS termination, hãy cấu hình origin theo **URL mà browser nhìn thấy**, thay vì theo hostname nội bộ của service. Việc backend nhận HTTP nội bộ không tự cho phép `http://frontend` và cũng không làm thay đổi origin của trang thực.

## 13. Checklist đánh giá pattern trước khi đưa vào production

- [ ] Mọi origin khớp pattern đều thực sự do các đội được tin cậy vận hành hoặc có quy trình kiểm soát tương đương.
- [ ] Đã kiểm tra subdomain cho người dùng/tenant upload JavaScript, nơi preview, staging và dịch vụ hosting của bên thứ ba.
- [ ] Có kiểm kê DNS và cơ chế tránh subdomain takeover sau khi dịch vụ ngừng hoạt động.
- [ ] Scheme và port được giới hạn theo nhu cầu, không dùng wildcard port chỉ để tiện phát triển.
- [ ] Pattern không vô tình bao phủ hostname gốc, các subdomain sâu hoặc vùng không tin cậy ngoài mong muốn.
- [ ] Không dùng `allowedOriginPatterns("*")` cùng credentials cho API có dữ liệu riêng tư.
- [ ] Response trả một origin cụ thể đã khớp, không trả nguyên pattern; `Vary: Origin` được xử lý khi cần.
- [ ] Có ma trận kiểm thử origin hợp lệ, không hợp lệ, giả gần giống và `Origin: null`.
- [ ] Preflight và actual response đều có quyền CORS phù hợp; proxy không chèn header trùng.
- [ ] Session cookie, CSRF, authentication và authorization được kiểm thử độc lập với CORS.
- [ ] Tập origin tin cậy được rà soát lại khi thêm, chuyển hoặc ngừng các frontend/domain.

## 14. Câu hỏi vận dụng

**Tình huống 1.** API cấu hình `allowedOriginPatterns("https://*.ui.example.com")`. Request từ `https://team.ui.example.com` được chấp nhận. Response nên trả `Access-Control-Allow-Origin` bằng gì?

**Đáp án:** Trả **origin cụ thể** `https://team.ui.example.com`. Không trả nguyên `https://*.ui.example.com`, vì browser không hỗ trợ wildcard hostname trong response header.

**Tình huống 2.** Có thể bật `allowCredentials(true)` cùng `allowedOriginPatterns("*")` nếu Spring cho chạy không?

**Đáp án:** Kết hợp có thể hợp lệ về mặt kỹ thuật, nhưng cho phép mọi origin được phản hồi cụ thể và đọc response theo credentials mode khi các điều kiện khác đạt. Với API có phiên đăng nhập hoặc dữ liệu cá nhân, đây là phạm vi tin cậy quá rộng.

**Tình huống 3.** Công ty quản lý `example.com` nhưng khách hàng tự tạo HTML/JavaScript tại `https://customer.ui.example.com`. Có nên mặc định dùng `https://*.ui.example.com` cho API session?

**Đáp án:** Không. Mọi origin do khách hàng kiểm soát khớp pattern có thể nhận quyền đọc CORS. Nên tách namespace không tin cậy và chỉ cấp quyền cho frontend thật sự do tổ chức kiểm soát.

**Tình huống 4.** Một site tại `https://attacker.ui.example.com` và API `https://api.example.com` khác origin nhưng thường same-site. Cookie `SameSite=Lax` có chắc chặn request của site đó không?

**Đáp án:** Không. Cả hai đều cùng site theo chính sách cookie trong ngữ cảnh HTTPS, nên cookie `Lax` có thể được gửi nếu điều kiện khác đạt. CORS phải giữ ranh giới giữa origin tin cậy và origin không tin cậy.

**Tình huống 5.** API cho `https://*.internal-ui.example.com` nhưng một bản preview mới chạy tại `http://preview.internal-ui.example.com:5173`. Có nên thêm pattern `*` toàn phần cho nhanh?

**Đáp án:** Không. Đó là origin khác về scheme và port. Nếu thực sự cần, thêm origin cụ thể vào cấu hình **dev/staging**, hoặc tách môi trường, thay vì mở mọi origin của production.

**Tình huống 6.** Preflight của `PUT` với `Origin: https://evil.test` bị từ chối. Có thể khẳng định API không bao giờ nhận bất kỳ request nào từ origin đó không?

**Đáp án:** Không. Preflight bị từ chối ngăn browser gửi **actual PUT của luồng này**. Một số request không cần preflight hoặc client ngoài browser vẫn có thể gửi tới API. Authentication, authorization và CSRF tiếp tục bảo vệ server.

**Tình huống 7.** Tenant có custom domain và đăng ký `Origin` mới. Chỉ cần nhận `Origin` request rồi trả lại là xong?

**Đáp án:** Không. Cần có registry origin đã xác minh quyền kiểm soát, cơ chế cấp/thu hồi và đối chiếu tenant. Phản chiếu tùy ý `Origin` khiến bất kỳ website nào có thể được cấp quyền đọc CORS.

---

**Ghi nhớ:** `allowedOriginPatterns` là công cụ để **mở rộng tập origin được chấp nhận** theo mẫu, không tự kiểm tra ai đang kiểm soát JavaScript ở những origin đó. Khi kết hợp với `allowCredentials(true)`, mỗi origin khớp có thể được cấp quyền đọc response sử dụng session của người dùng. Hãy ưu tiên allowlist chính xác cho API nhạy cảm, quản trị namespace subdomain, thử cả origin bị từ chối và duy trì các lớp bảo vệ authentication, authorization, CSRF, session trên Servlet và Reactive.
