# HTTP API call: xử lý mixed content khi gọi API từ trang HTTPS

## 1. HTTP API call trong trang HTTPS là gì?

Một trang web được tải qua HTTPS có thể gọi API bằng Fetch API hoặc XMLHttpRequest. Nếu trang dùng HTTPS nhưng endpoint API lại dùng HTTP, browser có thể coi đây là **mixed content** (nội dung hỗn hợp) và chặn request.

Ví dụ trang ứng dụng:

~~~text
https://app.example.test
~~~

gọi API:

~~~js
fetch("http://api.example.test/v1/profile");
~~~

Trang được bảo vệ bằng TLS, nhưng request API lại đi qua HTTP không mã hóa. Người dùng có thể nhìn thấy giao diện HTTPS trong khi dữ liệu API có nguy cơ bị nghe lén hoặc sửa đổi nếu request được phép đi qua mạng. Vì Fetch/XHR là các request có thể trả dữ liệu chủ động cho script, browser phân loại chúng là blockable mixed content và chặn trong browser hiện đại.

Cách sửa đúng là cung cấp endpoint API qua HTTPS:

~~~js
fetch("https://api.example.test/v1/profile");
~~~

Hoặc dùng đường dẫn cùng origin nếu ứng dụng có reverse proxy:

~~~js
fetch("/api/v1/profile");
~~~

HTTP API call từ một trang HTTPS không chỉ là lỗi cấu hình URL. Nó có thể làm lộ thông tin đăng nhập, dữ liệu cá nhân, nội dung giao dịch và response mà JavaScript xử lý. Ngoài ra, request bị chặn có thể làm hỏng đăng nhập, dashboard, form, thanh toán hoặc các chức năng realtime.

Bài học thuộc chương **Mixed content** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; bao gồm Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types, clickjacking và các security headers. Bài này tập trung vào request API do browser khởi tạo, cách nhận diện mixed content, phân biệt với CORS và triển khai HTTPS xuyên suốt.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao Fetch API và XMLHttpRequest qua HTTP từ trang HTTPS bị chặn.
2. Phân biệt mixed content với same-origin policy và CORS.
3. Nhận diện URL HTTP bị hard-code trong frontend, cấu hình môi trường hoặc redirect.
4. Hiểu vai trò của CSP connect-src, upgrade-insecure-requests và HSTS.
5. Chuyển API sang HTTPS và cấu hình reverse proxy phù hợp.
6. Xử lý CORS đúng sau khi API đã dùng HTTPS.
7. Phân biệt request browser với request server-to-server.
8. Debug mixed content bằng Console, Network và initiator.
9. Xây dựng quy trình kiểm tra để không phát hành bundle hoặc cấu hình còn HTTP endpoint.

## 2. Mixed content và secure context

Một document được tải qua HTTPS thường được xem là secure context. Khi document đó tham chiếu hoặc gọi tài nguyên qua HTTP, browser đánh giá request có làm suy yếu bảo vệ của trang hay không.

Mixed content được chia thành những nhóm có cách xử lý khác nhau. Một số loại tài nguyên có thể được tự động nâng cấp từ HTTP lên HTTPS theo quy tắc browser; những loại có khả năng thực thi hoặc trao đổi dữ liệu nhạy cảm sẽ bị chặn.

Với chủ đề HTTP API call, cần nhớ:

- `fetch("http://...")` từ trang HTTPS là request mixed content.
- `XMLHttpRequest` tới endpoint HTTP cũng là mixed content.
- Các request API thường được xem là blockable mixed content.
- Browser hiện đại chặn loại request này; ứng dụng không nên dựa vào browser tự nâng cấp API call.
- Dùng HTTPS cho endpoint API và cho mọi redirect trong chuỗi request.

### 2.1. Vì sao API call có rủi ro cao?

API thường chứa dữ liệu có giá trị hơn một ảnh trang trí:

- Session-related data hoặc thông tin user.
- Hồ sơ, địa chỉ, số điện thoại và dữ liệu cá nhân.
- Số dư, đơn hàng, thanh toán và trạng thái giao dịch.
- Access token hoặc dữ liệu cấp quyền.
- Nội dung quản trị và dữ liệu nội bộ.
- Request thay đổi trạng thái như cập nhật email, tạo đơn hoặc xóa tài nguyên.

Nếu một API request đi qua HTTP, bên trung gian trên mạng có thể quan sát hoặc sửa nội dung trong những điều kiện mạng tương ứng. TLS bảo vệ cả request lẫn response trên đường truyền; chỉ mã hóa trang HTML mà để API dùng HTTP sẽ không tạo được bảo vệ xuyên suốt.

### 2.2. Browser chặn ở phía client

Khi browser chặn mixed content, request có thể không tới được API server. Backend có thể không thấy access log cho request đó. Vì vậy, chỉ kiểm tra server log không đủ để tìm nguyên nhân; cần mở browser DevTools và xem Console/Network.

Một request bị browser chặn không có nghĩa server trả 403 hay CORS error. Đây có thể là lỗi security policy xảy ra trước khi response API tồn tại.

## 3. Luồng một API request từ trang HTTPS

Ví dụ trang:

~~~text
https://app.example.test
~~~

thực hiện:

~~~js
const response = await fetch("http://api.example.test/v1/orders");
~~~

Browser xử lý request qua nhiều bước bảo mật và mạng. Ở mức khái quát:

~~~mermaid
flowchart TD
    A["Trang HTTPS gọi Fetch/XHR"] --> B["Browser phân tích URL request"]
    B --> C{"HSTS hoặc upgrade-insecure-requests áp dụng?"}
    C -->| "Có" | D["Nâng URL lên HTTPS"]
    C -->| "Không" | E["Giữ URL ban đầu"]
    D --> F{"URL hiệu lực còn dùng HTTP?"}
    E --> F
    F -->| "Có" | G["Mixed content block"]
    F -->| "Không" | H["Kiểm tra CSP connect-src"]
    H --> I{"Policy cho phép?"}
    I -->| "Không" | J["Chặn theo CSP"]
    I -->| "Có" | K["Fetch/network/TLS"]
    K --> L{"Cross-origin?"}
    L -->| "Có" | M["Áp dụng CORS khi cần"]
    L -->| "Không" | N["Tiếp tục xử lý response"]
    M --> O["CORS response check"]
    O --> N
~~~

Sơ đồ là mô hình khái quát để định vị các lớp kiểm soát. Thứ tự chi tiết và thông báo có thể khác theo loại request, browser và redirect. Điều cần nhớ là CORS không cấp quyền vượt qua mixed content: endpoint HTTP vẫn không an toàn chỉ vì server gửi Access-Control-Allow-Origin.

### 3.1. HTTPS page gọi HTTP API

~~~js
fetch("http://api.example.test/v1/profile");
~~~

Browser hiện đại chặn request này như blockable mixed content. Không nên kỳ vọng API server nhận được request hoặc trả CORS header để giải quyết.

### 3.2. HTTPS page gọi HTTPS API khác origin

~~~js
fetch("https://api.example.test/v1/profile");
~~~

Đây không phải mixed content vì request cũng dùng HTTPS. Nếu app và API khác origin, browser có thể áp dụng CORS. Server API cần trả các CORS headers phù hợp với origin của app và loại request.

### 3.3. HTTPS page gọi HTTPS API cùng origin

~~~js
fetch("/api/v1/profile");
~~~

URL tương đối được resolve theo origin của trang. Nếu trang ở https://app.example.test, request sẽ tới https://app.example.test/api/v1/profile. Đây thường là cách đơn giản nếu reverse proxy định tuyến /api tới backend nội bộ.

## 4. Mixed content khác CORS như thế nào?

Cả hai cơ chế đều có thể khiến JavaScript không đọc được dữ liệu từ API, nhưng chúng giải quyết các vấn đề khác nhau.

| Cơ chế | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Mixed content | Trang HTTPS có đang yêu cầu tài nguyên qua HTTP không an toàn? | HTTPS app gọi HTTP API. |
| CORS | JavaScript origin này có được phép đọc response cross-origin không? | HTTPS app gọi HTTPS API khác origin. |
| Same-Origin Policy | Script có được truy cập dữ liệu cross-origin theo mặc định không? | app.example.test đọc response của api.example.test. |
| CSP connect-src | Trang được phép kết nối tới những endpoint nào? | Policy chỉ cho phép API host đã duyệt. |
| TLS certificate validation | Kết nối HTTPS có xác minh được danh tính server không? | SAN không khớp hostname hoặc chain không tin cậy. |

### 4.1. CORS không thể cho phép HTTP mixed content

Một server HTTP có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Nhưng header này không biến kết nối HTTP thành HTTPS. Browser vẫn áp dụng mixed content policy và có thể chặn request trước khi JavaScript nhận response.

Tương tự, thêm:

~~~js
fetch("http://api.example.test/data", {
  mode: "cors"
});
~~~

không thay đổi scheme và không bỏ qua mixed content protection.

### 4.2. mode: no-cors không phải cách sửa

Không dùng:

~~~js
fetch("http://api.example.test/data", {
  mode: "no-cors"
});
~~~

để né lỗi. no-cors không biến request thành HTTPS và không vượt qua mixed content blocking. Trong các trường hợp request được phép, response còn có thể là opaque response mà JavaScript không đọc được nội dung.

### 4.3. JSONP cũng không phải giải pháp

JSONP dùng script loading để trao đổi dữ liệu trong các ứng dụng cũ. Nó không phải cách an toàn để thay thế API HTTPS/CORS hiện đại, đặc biệt vì response được thực thi như JavaScript. Không chuyển API nhạy cảm sang JSONP để tránh lỗi mixed content.

## 5. HTTP và HTTPS là hai origin khác nhau

Origin được xác định bởi scheme, host và port. Do đó:

~~~text
http://api.example.test
https://api.example.test
~~~

là hai origin khác nhau vì scheme khác nhau, dù hostname giống nhau.

Điều này có hai hệ quả:

1. Request từ HTTPS tới HTTP là mixed content.
2. Nếu gọi từ HTTP sang HTTPS hoặc giữa các hostname HTTPS khác nhau, same-origin policy/CORS vẫn có thể liên quan tùy origin.

Không cho rằng chỉ cần hostname giống là request cùng origin. Scheme và port đều là thành phần của origin.

### 5.1. Port khác nhau cũng tạo origin khác

~~~text
https://app.example.test
https://app.example.test:8443
~~~

là hai origin khác nhau. Cả hai dùng HTTPS nên không phải mixed content chỉ vì port khác, nhưng browser có thể áp dụng CORS khi JavaScript gọi giữa chúng.

### 5.2. URL tương đối và URL tuyệt đối

URL tương đối:

~~~js
fetch("/api/v1/orders");
~~~

được resolve theo base URL của document. Với trang HTTPS, URL tương đối thông thường tiếp tục dùng scheme HTTPS của trang.

URL tuyệt đối hard-code HTTP:

~~~js
fetch("http://api.example.test/v1/orders");
~~~

giữ scheme HTTP và có thể bị chặn.

Một lỗi phổ biến là backend render API base URL từ biến môi trường sai hoặc bundle frontend chứa URL HTTP cũ. Cần kiểm tra URL thực tế trong browser, không chỉ xem source code hoặc file cấu hình.

## 6. Vì sao không nên downgrade API về HTTP?

Một số ứng dụng xử lý lỗi HTTPS bằng cách thử lại qua HTTP:

~~~js
try {
  return await fetch("https://api.example.test/data");
} catch {
  return await fetch("http://api.example.test/data");
}
~~~

Đây là downgrade nguy hiểm. Nếu HTTPS lỗi do certificate mismatch, TLS interception hoặc cấu hình server, fallback HTTP có thể che giấu lỗi bảo mật và đưa dữ liệu ra kết nối không được mã hóa.

Nguyên tắc:

- Không tự động fallback từ HTTPS sang HTTP.
- Không cho người dùng “tiếp tục không bảo mật” để gọi API nhạy cảm.
- Sửa certificate, DNS, proxy hoặc endpoint HTTPS.
- Giữ lỗi hiển thị rõ và ghi nhận telemetry không chứa secret.
- Nếu endpoint HTTPS tạm thời không khả dụng, xử lý như lỗi kết nối và retry qua HTTPS theo backoff.

Mixed content blocking là cơ chế bảo vệ. Đừng vô hiệu hóa hoặc né nó để giữ ứng dụng chạy bằng mọi giá.

## 7. CSP connect-src kiểm soát API endpoint

Content Security Policy directive **connect-src** giới hạn những nguồn mà document có thể kết nối bằng các API như fetch, XMLHttpRequest, WebSocket, EventSource và Beacon.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.test; object-src 'none'; base-uri 'none'
~~~

Policy cho phép kết nối same-origin và API host đã nêu. Các endpoint không nằm trong source list có thể bị browser chặn theo CSP.

### 7.1. connect-src không tự mã hóa request

connect-src chỉ là allowlist đích kết nối. Nó không nâng HTTP lên HTTPS, không xác minh certificate thay TLS và không cấp quyền CORS.

Ví dụ policy rộng:

~~~http
Content-Security-Policy: connect-src *
~~~

không phải giải pháp an toàn cho API HTTP. Hãy dùng HTTPS endpoint và allowlist nguồn cụ thể.

### 7.2. Khai báo API host đúng scheme

~~~http
Content-Security-Policy: connect-src 'self' https://api.example.test
~~~

Nếu ứng dụng còn gọi websocket bảo mật, khai báo endpoint WSS tương ứng theo nhu cầu:

~~~http
Content-Security-Policy: connect-src 'self' https://api.example.test wss://realtime.example.test
~~~

Không thêm ws: hoặc http: chỉ để làm một kết nối legacy hoạt động. Chuyển endpoint realtime sang WSS và kiểm tra redirect/handshake phù hợp.

### 7.3. connect-src 'self' không phải lúc nào cũng bao gồm WebSocket cùng host

Theo cách xử lý CSP của browser, self trong connect-src không phải lúc nào cũng bao phủ scheme WebSocket như nhà phát triển kỳ vọng. Nếu dùng WebSocket, khai báo wss: host phù hợp tường minh và kiểm thử trên browser mục tiêu.

## 8. upgrade-insecure-requests

CSP directive **upgrade-insecure-requests** yêu cầu browser nâng các URL insecure được tham chiếu trong document lên scheme bảo mật tương ứng trước khi tải.

Ví dụ response header:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Một URL:

~~~js
fetch("http://api.example.test/v1/profile");
~~~

có thể được browser nâng thành HTTPS URL tương ứng trong các trường hợp directive áp dụng.

### 8.1. Đây là lớp hỗ trợ migration, không thay code

upgrade-insecure-requests có ích khi một website còn URL HTTP cũ trong HTML, CSS hoặc JavaScript. Tuy nhiên, ứng dụng vẫn nên sửa URL nguồn thành HTTPS hoặc URL tương đối.

Lý do:

- Nếu host không phục vụ HTTPS, request sau nâng cấp sẽ thất bại.
- URL trong code vẫn gây nhầm lẫn khi review và debug.
- Không phải mọi loại request/protocol đều được xử lý giống nhau.
- Hành vi redirect và các browser cũ có thể khác nhau.
- Nó không thay việc cấu hình endpoint, certificate và CSP allowlist.

### 8.2. Không có fallback về HTTP

Khi browser nâng một request HTTP thành HTTPS theo directive, nếu HTTPS endpoint không hoạt động thì request thất bại. Browser không được yêu cầu quay lại HTTP chỉ để hoàn tất request.

Đây là hành vi mong muốn: không âm thầm hạ cấp bảo vệ truyền tải.

### 8.3. Không nhầm với HSTS

| Cơ chế | Phạm vi |
| --- | --- |
| upgrade-insecure-requests | Nâng các URL insecure được tham chiếu trong document hiện tại theo policy CSP. |
| HSTS | Ghi nhớ rằng một host phải được truy cập qua HTTPS trong thời hạn policy. |
| HTTPS URL trong code | Chỉ định trực tiếp endpoint secure ở tầng ứng dụng. |

HSTS áp dụng theo hostname và policy đã lưu; upgrade-insecure-requests áp dụng theo document. Hai cơ chế có thể bổ trợ nhưng không thay thế nhau.

## 9. HSTS và HTTP API

HTTP Strict Transport Security (HSTS) cho browser biết chỉ được truy cập host qua HTTPS trong thời hạn policy.

Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Nếu api.example.test tự gửi HSTS qua HTTPS hợp lệ, browser có thể ghi nhớ policy cho host đó. Với includeSubDomains, phạm vi có thể bao phủ các subdomain theo quy tắc HSTS.

### 9.1. HSTS chỉ hoạt động sau khi browser biết policy

Trước lần đầu nhận HSTS hoặc khi host chưa nằm trong preload list, có thể có khoảng trống first-visit. Không dựa vào HSTS để thay URL HTTP trong code. API endpoint vẫn nên được cấu hình HTTPS rõ ràng.

### 9.2. HSTS không sửa certificate hoặc endpoint

Nếu API HTTPS có certificate hết hạn, sai hostname hoặc chain không tin cậy, HSTS không làm request thành công. Sửa TLS certificate và chain ở server.

### 9.3. Cẩn trọng với includeSubDomains

Chỉ bật includeSubDomains khi mọi subdomain trong phạm vi có thể phục vụ HTTPS hợp lệ. Nếu api.example.test là subdomain cần HTTPS nhưng legacy.example.test chưa hỗ trợ, policy trên example.test với includeSubDomains có thể ảnh hưởng legacy endpoint.

HSTS cần được triển khai theo inventory hostname và quy trình rollout.

## 10. Redirect từ HTTPS API sang HTTP

Một trường hợp khó tìm là code gọi HTTPS endpoint nhưng server/proxy redirect sang HTTP:

~~~text
https://api.example.test/v1/profile
    -> 302 Location: http://legacy-api.example.test/v1/profile
~~~

Browser kiểm tra các URL trong quá trình fetch và có thể chặn redirect tới HTTP như mixed content. Request ban đầu dùng HTTPS không bảo đảm toàn bộ redirect chain an toàn.

Cần:

1. Kiểm tra redirect chain trong Network.
2. Sửa Location header để đích cuối dùng HTTPS.
3. Cập nhật cấu hình base URL hoặc gateway.
4. Loại bỏ redirect HTTP trong backend/proxy.
5. Kiểm tra cả 301, 302, 303, 307 và 308 theo luồng ứng dụng.

Không dùng `redirect: "manual"` hoặc `no-cors` như cách né mixed content; chúng không làm HTTP endpoint trở nên an toàn.

### 10.1. Redirect sau authentication

Một API có thể redirect tới trang đăng nhập hoặc SSO khi session hết hạn. Nếu một bước trong redirect chain dùng HTTP, browser có thể chặn. Đảm bảo login endpoint, callback và API gateway đều HTTPS, đồng thời thiết kế response API (ví dụ 401 JSON) phù hợp thay vì redirect bất ngờ sang trang HTTP.

## 11. HTTPS frontend và backend HTTP nội bộ

Không phải mọi hop trong hạ tầng đều cần browser trực tiếp kết nối. Một kiến trúc phổ biến:

~~~text
Browser
  -- HTTPS -->
Reverse proxy / API gateway
  -- private network -->
Internal service
~~~

Browser chỉ thấy HTTPS endpoint công khai. Reverse proxy chuyển request tới backend nội bộ bằng HTTP trong một mạng riêng được kiểm soát, hoặc dùng TLS/mTLS giữa các service theo yêu cầu threat model.

Ví dụ frontend gọi:

~~~js
fetch("/api/v1/orders");
~~~

Reverse proxy định tuyến:

~~~text
/api/v1/orders -> http://orders-service.internal:8080/v1/orders
~~~

Browser không trực tiếp gọi HTTP backend nội bộ, nên không tạo mixed content trong request của trang. Tuy nhiên, HTTP nội bộ vẫn có rủi ro nếu mạng không tin cậy hoặc có thể bị xâm nhập; dùng TLS/mTLS giữa service khi cần bảo vệ hop nội bộ.

### 11.1. Forwarded headers và scheme detection

Reverse proxy thường truyền thông tin scheme gốc qua header như `Forwarded` hoặc `X-Forwarded-Proto`. Backend cần chỉ tin các forwarded headers từ proxy đáng tin cậy; không tin giá trị do client bất kỳ tự gửi.

Nếu backend nghĩ request gốc là HTTP, nó có thể sinh absolute URL hoặc redirect dùng HTTP dù browser đã gọi HTTPS. Cấu hình proxy trust và public base URL chính xác để tránh downgrade trong Location/API links.

### 11.2. Không đưa hostname nội bộ vào frontend bundle

Đừng để frontend gọi:

~~~js
fetch("http://orders-service.internal:8080/v1/orders");
~~~

Hostname nội bộ không nên xuất hiện trong browser code và HTTP request từ HTTPS page sẽ bị mixed content block. Dùng API gateway hoặc reverse proxy công khai qua HTTPS.

## 12. CORS sau khi chuyển API sang HTTPS

Khi API đã dùng HTTPS nhưng khác origin với frontend, CORS có thể vẫn cần.

Ví dụ:

- Frontend: `https://app.example.test`
- API: `https://api.example.test`

Server API có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Nếu cần cookie credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Client:

~~~js
const response = await fetch("https://api.example.test/v1/profile", {
  credentials: "include"
});
~~~

Khi credentials được dùng, Access-Control-Allow-Origin không được là wildcard `*`. Cookie còn chịu Domain, Path, Secure, SameSite và browser third-party cookie policy.

### 12.1. Preflight và HTTPS

Request CORS có thể cần preflight OPTIONS nếu dùng method/header không simple. Preflight cũng cần đi tới endpoint HTTPS và được server xử lý đúng.

Đừng nhầm lỗi preflight với mixed content:

- Mixed content: URL request là HTTP từ secure page hoặc có redirect tới HTTP.
- CORS/preflight: request HTTPS cross-origin nhưng response không đáp ứng CORS policy.

### 12.2. CORS không phải authorization

CORS điều khiển browser JavaScript có được đọc response cross-origin hay không. Nó không thay authentication/authorization ở API. Client ngoài browser có thể gọi endpoint trực tiếp; server phải xác minh user và quyền trên mỗi request.

## 13. Fetch API: pattern gọi HTTPS an toàn

Một helper có thể kiểm tra API base URL ngay khi khởi tạo:

~~~js
function createApiClient(baseUrl) {
  const base = new URL(baseUrl);

  if (base.protocol !== "https:") {
    throw new TypeError("API phải dùng HTTPS");
  }

  return async function apiFetch(path, options = {}) {
    const url = new URL(path, base);

    if (url.protocol !== "https:" || url.origin !== base.origin) {
      throw new TypeError("API URL phải dùng HTTPS và cùng origin đã cấu hình");
    }

    const response = await fetch(url, {
      ...options,
      redirect: "error"
    });

    if (!response.ok) {
      throw new Error("API request thất bại: " + response.status);
    }

    return response;
  };
}

const apiFetch = createApiClient("https://api.example.test/");
~~~

Ví dụ này yêu cầu HTTPS và khóa request vào đúng origin API đã cấu hình. redirect: "error" giúp ứng dụng phát hiện endpoint API có redirect thay vì âm thầm đi theo đích khác. Nếu nghiệp vụ cần redirect, hãy xác minh redirect ở gateway/server và kiểm thử destination. Với local development, ưu tiên HTTPS local bằng certificate dev được trust có kiểm soát thay vì thêm ngoại lệ HTTP vào helper production.

### 13.1. Không để user input chọn API origin tùy ý

Nếu API base URL lấy từ query string, localStorage hoặc message cross-origin, người dùng có thể làm ứng dụng gửi dữ liệu tới endpoint ngoài dự kiến. Chỉ cho phép API origin từ cấu hình build/server được kiểm soát hoặc allowlist cố định.

### 13.2. Không gửi credential khi không cần

Chọn credentials mode phù hợp:

- same-origin là mặc định cho Fetch API.
- include gửi credential theo quy tắc cookie/CORS và browser policy.
- omit không gửi credential.

Không thêm credentials: "include" cho mọi API chỉ để “sửa CORS”. Cookie session cần Secure, HttpOnly nếu phù hợp, SameSite và server-side CSRF defense.

## 14. XMLHttpRequest và thư viện HTTP cũ

Một số ứng dụng legacy dùng XMLHttpRequest:

~~~js
const xhr = new XMLHttpRequest();
xhr.open("GET", "http://api.example.test/v1/profile");
xhr.onload = () => {
  console.log(xhr.responseText);
};
xhr.send();
~~~

Từ trang HTTPS, đây vẫn là request mixed content và browser hiện đại chặn. Chuyển URL sang HTTPS:

~~~js
xhr.open("GET", "https://api.example.test/v1/profile");
~~~

Các thư viện như Axios hoặc wrapper nội bộ cuối cùng vẫn dùng browser network APIs. Việc dùng thư viện không tránh mixed content. Tìm URL trong cấu hình, interceptor, generated client và runtime environment.

## 15. WebSocket và realtime API

Một trang HTTPS kết nối WebSocket bằng ws: tạo ra kênh không mã hóa. Dùng WSS:

~~~js
const socket = new WebSocket("wss://realtime.example.test/events");
~~~

CSP connect-src cần cho phép endpoint WSS tương ứng. Server cần TLS certificate hợp lệ và xác minh Origin/authorization theo threat model của WebSocket.

Không dùng ws: từ trang HTTPS hoặc fallback ws: khi wss: thất bại. Cần kiểm tra redirect/upgrade handshake và policy của reverse proxy.

## 16. Local development và localhost

Trong môi trường phát triển, có thể thấy frontend HTTPS gọi API HTTP trên localhost. Browser có một số quy tắc đặc biệt cho loopback/localhost và secure context; hành vi cụ thể phụ thuộc URL và browser. Không lấy ngoại lệ localhost làm quy tắc cho hostname private LAN hoặc production.

Khuyến nghị:

- Dùng HTTPS local cho frontend và API nếu cần mô phỏng production.
- Dùng certificate dev được trust có kiểm soát, ví dụ local CA của công cụ phát triển.
- Không tắt certificate validation toàn browser.
- Không dùng HTTP endpoint nội bộ trong production bundle.
- Tách config development/staging/production và kiểm tra build artifact.
- Kiểm tra cả IPv4/IPv6 loopback nếu môi trường dùng localhost/127.0.0.1/::1.

### 16.1. Private LAN không đồng nghĩa localhost

Các địa chỉ như 192.168.x.x hoặc hostname máy trong LAN không tự động có ngoại lệ giống loopback. HTTPS page gọi HTTP API trên thiết bị LAN vẫn có thể bị mixed content block. Dùng HTTPS và certificate phù hợp cho endpoint LAN nếu browser phải truy cập trực tiếp.

## 17. Mixed content và cookie/session

Nếu browser chặn HTTP API request, ứng dụng không thể dựa vào cookie hoặc CORS để làm request thành công. Ngoài ra, cookie có thuộc tính Secure chỉ được gửi qua secure transport theo quy tắc cookie; cookie session cần được cấu hình đúng trên HTTPS.

Các thuộc tính liên quan:

- Secure: cookie chỉ được gửi qua kênh an toàn theo quy tắc browser.
- HttpOnly: JavaScript không đọc trực tiếp cookie qua document.cookie.
- SameSite: kiểm soát một số trường hợp cookie được gửi trong cross-site context.
- Domain/Path: xác định phạm vi cookie.

Các thuộc tính này không thay HTTPS cho API. Cũng không cho rằng SameSite thay CSRF token trong mọi ứng dụng; kiểm soát CSRF cần dựa trên kiến trúc authentication và request state-changing.

## 18. Phân biệt browser API call và server-to-server request

Mixed content là chính sách của browser khi document secure yêu cầu tài nguyên không an toàn. Nó không áp dụng theo cùng cách cho một backend server tự gọi HTTP service khác.

Ví dụ:

~~~text
Browser HTTPS -> HTTP API
~~~

có thể bị browser chặn như mixed content.

Trong khi:

~~~text
Backend service -> HTTP internal service
~~~

không phải browser mixed content. Nhưng request server-to-server vẫn có thể cần TLS/mTLS để bảo vệ mạng, xác thực service và tránh nghe lén/sửa đổi.

Không dùng việc backend gọi HTTP thành công để kết luận browser cũng được phép gọi HTTP.

## 19. Kiểm tra URL API và redirect trong dự án

Các nguồn gây ra HTTP API call không mong muốn:

- API base URL hard-code trong source.
- Biến môi trường build có giá trị http://.
- Config runtime được tải từ endpoint cũ.
- Generated OpenAPI/GraphQL client.
- Axios baseURL hoặc interceptor.
- URL được ghép từ window.location nhưng làm mất scheme.
- Redirect response từ HTTPS endpoint sang HTTP.
- WebSocket URL ws://.
- Service worker cache hoặc config cũ.
- CDN còn phục vụ bundle JavaScript cũ.

Quy trình kiểm tra:

1. Tìm các chuỗi `http://` và `ws://` trong source/config.
2. Phân loại URL chỉ dùng ở test/documentation với URL chạy trong browser.
3. Kiểm tra build output để tìm endpoint còn sót.
4. Mở Network và xem request thực tế, initiator và redirect chain.
5. Xác nhận HTTPS endpoint có certificate hợp lệ.
6. Kiểm tra CSP connect-src có cho phép đúng endpoint không.
7. Nếu cross-origin, kiểm tra CORS response/preflight sau khi mixed content đã được xử lý.
8. Kiểm tra service worker/cache và CDN nếu browser vẫn dùng URL cũ.

Không thay hàng loạt mọi chuỗi HTTP trong repository một cách mù quáng; có thể có URL trong fixture, tài liệu, test negative hoặc backend-only config. Sửa đúng cấu hình browser-facing.

## 20. Debug bằng DevTools

Khi API không hoạt động từ trang HTTPS:

1. Mở DevTools → Console và tìm thông báo Mixed Content.
2. Mở Network, lọc Fetch/XHR.
3. Xác định Request URL có dùng http:// hay không.
4. Xem cột Status và lý do blocked nếu browser hiển thị.
5. Kiểm tra Initiator để tìm file/script đã tạo request.
6. Xem redirect chain nếu request bắt đầu HTTPS.
7. Mở Security panel để kiểm tra TLS certificate của endpoint HTTPS.
8. Nếu request đã là HTTPS và cross-origin, kiểm tra CORS headers/preflight.
9. Kiểm tra CSP violation xem connect-src có chặn endpoint không.
10. Sửa API base URL hoặc redirect và tải lại trang với cache phù hợp.

### 20.1. Thông báo lỗi có thể khác nhau

Browser có thể hiển thị thông báo như “Mixed Content”, “blocked:mixed-content”, “blocked by Content Security Policy” hoặc lỗi CORS/network tùy tình huống. Không kết luận chỉ từ dòng lỗi JavaScript “Failed to fetch”; xem Console và Network để tìm lớp policy thực sự chặn.

### 20.2. Vì sao curl không tái hiện mixed content?

curl là HTTP client độc lập, không chạy trong document HTTPS và không áp dụng browser mixed content policy theo cùng cách. curl có thể gọi HTTP API thành công trong khi browser chặn request đó.

Dùng curl để kiểm tra TLS, redirect và response server; dùng browser thật để xác minh mixed content, CORS, CSP và cookie behavior.

## 21. Thực hành A — Tái hiện mixed content trong lab

Tạo một trang test phục vụ qua HTTPS và một API test chỉ phục vụ HTTP trên môi trường local/staging do bạn kiểm soát.

Trong Console của trang HTTPS:

~~~js
fetch("http://api-lab.example.test/data")
  .then((response) => response.text())
  .then(console.log)
  .catch(console.error);
~~~

Quan sát Console và Network. Browser hiện đại có thể chặn request dưới dạng mixed content trước khi API trả response.

Không dùng domain hoặc API của bên thứ ba để thử. Không gửi dữ liệu thật.

## 22. Thực hành B — Chuyển API sang HTTPS

Cấu hình API lab có certificate hợp lệ cho hostname API. Sau đó gọi:

~~~js
fetch("https://api-lab.example.test/data")
  .then((response) => response.text())
  .then(console.log)
  .catch(console.error);
~~~

Nếu frontend và API khác origin, kiểm tra CORS. Nếu cùng origin hoặc đi qua reverse proxy, thử URL tương đối:

~~~js
fetch("/api/data");
~~~

Xác minh request dùng HTTPS trong Network và certificate được browser tin cậy.

## 23. Thực hành C — Kiểm tra CSP connect-src

Trên response trang test, đặt:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api-lab.example.test
~~~

Thử gọi một API HTTPS host được allowlist và một host khác không được phép. Quan sát Console.

Sau đó thử thêm endpoint đúng vào connect-src trong môi trường lab và xác nhận request chỉ được phép khi URL khớp policy. Không dùng connect-src * như cách xử lý nhanh.

## 24. Thực hành D — Tìm redirect downgrade

Cấu hình một HTTPS endpoint test trả redirect tới một URL HTTP do bạn kiểm soát:

~~~http
HTTP/1.1 302 Found
Location: http://api-lab.example.test/final
~~~

Từ trang HTTPS, gọi endpoint đầu tiên:

~~~js
fetch("https://api-lab.example.test/redirect");
~~~

Quan sát Network redirect chain và Console. Browser có thể chặn bước đi tới HTTP như mixed content. Sửa Location thành HTTPS, kiểm tra certificate và chạy lại.

## 25. Checklist review HTTP API call

- [ ] Mọi API endpoint được browser gọi từ trang HTTPS đều dùng HTTPS hoặc URL tương đối resolve thành HTTPS.
- [ ] Không có fetch/XHR tới http:// trong production bundle.
- [ ] Không có fallback tự động từ HTTPS xuống HTTP.
- [ ] Redirect chain không đưa request sang HTTP.
- [ ] API base URL được lấy từ config build/runtime được kiểm soát.
- [ ] Frontend không gọi hostname service nội bộ.
- [ ] Nếu có reverse proxy, browser chỉ gọi public HTTPS endpoint.
- [ ] Backend chỉ tin forwarded scheme headers từ proxy đáng tin cậy.
- [ ] CSP connect-src allowlist đúng API host và WSS endpoint.
- [ ] Không dùng connect-src * để né policy.
- [ ] Không dùng mode: no-cors hoặc JSONP để né mixed content/CORS.
- [ ] CORS được cấu hình riêng sau khi endpoint đã dùng HTTPS.
- [ ] Access-Control-Allow-Origin khớp origin frontend; credentials không dùng wildcard.
- [ ] Certificate API có SAN đúng, chain tin cậy và thời hạn hợp lệ.
- [ ] WebSocket dùng wss: và không fallback về ws:.
- [ ] Localhost exception không bị áp dụng nhầm cho private LAN hoặc production.
- [ ] Cookie session có Secure, HttpOnly và SameSite phù hợp.
- [ ] API server vẫn xác thực, phân quyền và bảo vệ CSRF cho thao tác thay đổi trạng thái.
- [ ] Kiểm tra bundle, generated client, service worker và CDN cache.
- [ ] Dùng browser DevTools để xác minh request thực tế, không chỉ dựa vào curl.
- [ ] Theo dõi lỗi Mixed Content và endpoint HTTP còn sót sau release.

## 26. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Trang HTTPS có thể gọi API HTTP nếu API có CORS.” | **Sai** | CORS không vượt mixed content blocking. |
| “mode: no-cors cho phép HTTP API.” | **Sai** | Không bỏ qua mixed content; response opaque cũng không đọc được. |
| “Cùng hostname thì HTTP và HTTPS là cùng origin.” | **Sai** | Scheme là thành phần của origin. |
| “Browser tự nâng mọi Fetch/XHR HTTP lên HTTPS.” | **Sai** | Không dựa vào cơ chế auto-upgrade của các loại tài nguyên khác cho API call. |
| “upgrade-insecure-requests sửa được server không có HTTPS.” | **Sai** | Request sau nâng cấp thất bại nếu endpoint HTTPS không phục vụ được. |
| “HSTS cấp certificate cho API.” | **Sai** | HSTS buộc HTTPS; certificate vẫn phải hợp lệ. |
| “HTTPS endpoint ban đầu bảo đảm redirect chain an toàn.” | **Sai** | Redirect cuối sang HTTP vẫn có thể bị chặn. |
| “connect-src thay mixed content.” | **Sai** | connect-src allowlist endpoint; không biến HTTP thành TLS. |
| “CORS và mixed content là cùng một lỗi.” | **Sai** | Một cơ chế chặn tải insecure resource; cơ chế kia kiểm soát đọc response cross-origin. |
| “curl gọi được API thì browser cũng gọi được.” | **Sai** | curl không áp dụng browser mixed content policy. |
| “Backend gọi HTTP nội bộ thành công nghĩa browser cũng được.” | **Sai** | Server-to-server không phải browser mixed content. |
| “localhost exception áp dụng cho mọi IP private.” | **Sai** | Loopback/localhost có quy tắc riêng; private LAN không tự động tương đương. |
| “Cookie Secure thay HTTPS cho API.” | **Sai** | Secure cookie không mã hóa toàn bộ request/response hay thay TLS endpoint. |
| “Thêm wildcard vào connect-src là cách sửa an toàn.” | **Sai** | Nó mở rộng phạm vi kết nối và không sửa scheme HTTP. |
| “Nếu JavaScript chỉ báo Failed to fetch thì chắc chắn là CORS.” | **Sai** | Mixed content, CSP, TLS, DNS và network đều có thể tạo lỗi này. |

## 27. Tổng kết

HTTP API call từ một trang HTTPS là trường hợp mixed content quan trọng vì Fetch/XHR có thể mang dữ liệu nhạy cảm và thay đổi trạng thái ứng dụng. Browser hiện đại chặn request HTTP này. CORS, no-cors hoặc cookie settings không thể biến một endpoint HTTP thành kết nối bảo mật.

Ba nguyên tắc cần nhớ:

1. **HTTPS xuyên suốt phía browser:** frontend gọi HTTPS API hoặc URL tương đối qua same-origin reverse proxy; không downgrade và không để redirect chain quay về HTTP.
2. **Tách đúng các lớp policy:** mixed content kiểm soát tải không an toàn, CSP connect-src giới hạn đích kết nối, CORS kiểm soát đọc response cross-origin, TLS xác minh và mã hóa kết nối.
3. **Kiểm chứng request thực tế:** rà soát build config, bundle, redirect, certificate, proxy và service worker; dùng DevTools để xác định lớp nào chặn request.

Khi API không hoạt động từ trang HTTPS, hãy hỏi: **Request URL thực tế có dùng HTTP không, có redirect downgrade không, CSP connect-src cho phép endpoint không, HTTPS certificate có hợp lệ, và nếu khác origin thì CORS đã cấu hình đúng chưa?** Trả lời lần lượt giúp sửa đúng nguyên nhân mà vẫn giữ bảo vệ truyền tải cho dữ liệu ứng dụng.
