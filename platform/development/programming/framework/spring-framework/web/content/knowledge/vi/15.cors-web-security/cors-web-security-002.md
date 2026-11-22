# Yêu cầu đơn giản, preflight OPTIONS và các header CORS trong Spring MVC

## 1. Bài toán thực tế: frontend khác origin gọi API

Một frontend chạy tại `https://app.example.test` gọi API tại `https://api.example.test`:

~~~javascript
const response = await fetch("https://api.example.test/api/demo/items");
const items = await response.json();
console.log(items);
~~~

Hai địa chỉ có hostname khác nhau nên là **khác origin**, dù đều dùng HTTPS. Trình duyệt áp dụng **same-origin policy**: JavaScript ở một origin không được tự ý đọc response từ origin khác nếu server không cấp quyền thông qua **Cross-Origin Resource Sharing (CORS)**.

Server có thể gửi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test

[{"id":1,"name":"Spring MVC"}]
~~~

Nếu request/response thỏa chính sách CORS, browser cho phép script đọc JSON. Nếu thiếu header phù hợp, server **vẫn có thể đã xử lý HTTP request và gửi response**, nhưng browser không cho JavaScript đọc kết quả. Đây là điểm căn bản: **CORS là cơ chế kiểm soát truy cập response của trình duyệt**, không phải hệ thống xác thực người dùng.

### 1.1. Mục tiêu của bài

Sau bài này, bạn cần phân biệt rõ:
1. **Origin** được tính từ scheme, host, port như thế nào.
2. Request **CORS-safelisted / simple** là gì, vì sao nó **không có preflight** nhưng vẫn cần response header.
3. Khi nào browser tự gửi **preflight OPTIONS**, nội dung `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
4. Ý nghĩa chính xác của các header `Access-Control-Allow-Origin`, `-Methods`, `-Headers`, `-Credentials`, `-Expose-Headers`, `-Max-Age` và `Vary`.
5. Cách cấu hình CORS trong Spring MVC bằng `WebMvcConfigurer` hoặc `@CrossOrigin`, và cách tích hợp Spring Security đúng thứ tự.
6. Kiểm thử simple/preflight bằng MockMvc, nhận diện cấu hình quá rộng, origin sai, cookie/credential và lỗi security.

Bài dùng Java 17+, Spring Boot 3.x / Spring MVC Servlet stack. Các ví dụ Spring Boot 3.3.5 nhằm tái hiện cơ chế, còn tiêu chuẩn CORS do browser Fetch/HTTP quyết định, **không phải do Spring tự định nghĩa lại**.

## 2. Origin và same-origin policy

Một origin gồm bộ ba:

~~~text
origin = (scheme, hostname, effective port)
~~~

Ví dụ xét trang đang chạy ở `https://app.example.test`:

| URL đích | Same-origin? | Lý do |
| --- | --- | --- |
| `https://app.example.test/api/items` | Có | Cùng scheme, hostname và port mặc định 443 |
| `https://app.example.test:443/api/items` | Có | Port 443 là port mặc định của HTTPS |
| `http://app.example.test/api/items` | Không | Scheme HTTP khác HTTPS |
| `https://api.example.test/api/items` | Không | Khác hostname/subdomain |
| `https://app.example.test:8443/api/items` | Không | Port 8443 khác 443 |
| `https://app.example.test/other/path` | Có | Khác path **không làm khác origin** |

Origin không bằng site: trong một số trường hợp, hai subdomain khác origin nhưng được xem là same-site cho chính sách cookie. **CORS, SameSite cookie và CSRF không phải một cơ chế duy nhất**.

Request CORS thường mang header:

~~~http
Origin: https://app.example.test
~~~

Giá trị `Origin` **không có path**, không có dấu gạch cuối URL, gồm scheme + host + port nếu khác port mặc định. Một số trường hợp đặc biệt có origin `null` (sandboxed frame, file/opaque origins); **không cấp quyền `null` một cách tùy tiện** vì nhiều ngữ cảnh không tin cậy có thể mang giá trị này.

Request không có `Origin`, ví dụ nhiều client server-to-server hoặc curl mặc định, không có cùng quy trình thực thi CORS như browser. Có header `Origin` giả lập bằng curl chỉ giúp quan sát response server, **không tái hiện toàn bộ quyết định của browser**.

## 3. Request “simple” / CORS-safelisted là gì?

Thuật ngữ *simple request* thường dùng để chỉ request thuộc phạm vi **không cần CORS preflight** theo Fetch. Đây không phải “request GET thì luôn simple”: các điều kiện về method và request headers **phải đồng thời thỏa**.

### 3.1. Phương thức

Các phương thức CORS-safelisted cho trường hợp thường gặp:

- `GET`
- `HEAD`
- `POST`

`PUT`, `PATCH`, `DELETE` thường yêu cầu preflight khi được gọi cross-origin từ browser, kể cả không có body. `OPTIONS` là phương thức browser dùng để hỏi quyền trước khi gửi actual request; bạn **không cần** tự gọi OPTIONS từ JavaScript chỉ vì endpoint sử dụng PUT.

### 3.2. Request headers

Các request header được script chủ động đặt phải nằm trong nhóm **CORS-safelisted request headers** và đáp ứng thêm điều kiện về giá trị/kích thước. Nhóm thường gặp gồm:
- `Accept`.
- `Accept-Language`.
- `Content-Language`.
- `Content-Type` với ràng buộc media type bên dưới.
- `Range` trong một số trường hợp value đơn giản chỉ có **một** byte range.

Fetch còn có những ràng buộc chi tiết về giá trị, độ dài, byte không an toàn và user-agent; vì vậy bảng chỉ là hướng dẫn thực hành, **không phải thuật toán đầy đủ thay cho Fetch spec**. Header do trình duyệt tự đặt như `User-Agent`, `Host` và một số forbidden request headers không được coi như tùy ý do script gắn.

Với `Content-Type`, media type essence CORS-safelisted phổ biến là:

~~~text
application/x-www-form-urlencoded
multipart/form-data
text/plain
~~~

**`application/json` không nằm trong danh sách này.** Do đó `POST` JSON cross-origin thường kích hoạt preflight mặc dù `POST` là safelisted method. Ngược lại, một form POST được trình duyệt tạo với `application/x-www-form-urlencoded`, không có custom headers, thường không cần preflight.

Cũng cần chú ý tên “simple” là phân loại kiểm soát CORS, **không có nghĩa request an toàn hoặc chỉ đọc**. Simple `POST` vẫn có thể thay đổi trạng thái, và browser có thể gửi request trước khi được xác nhận quyền đọc response.

### 3.3. Bảng tình huống

| Request từ JS ở frontend khác origin | Preflight thông thường? | Giải thích |
| --- | --- | --- |
| `fetch(url)`, GET, không custom header | Không | GET + safelisted headers |
| `fetch(url, {method:"HEAD"})` | Không | HEAD |
| POST `application/x-www-form-urlencoded` | Không | POST + safelisted media type, nếu các điều kiện khác thỏa |
| POST `text/plain` | Không | Tương tự |
| POST `application/json` | Có | `Content-Type` không safelisted |
| GET với `Authorization: Bearer ...` | Có | Authorization không là safelisted request header |
| GET với `X-Request-Id` do script đặt | Có | Custom header |
| `PUT` với JSON | Có | Method và Content-Type đều ngoài safelist |
| `DELETE` không body | Có | DELETE không safelisted |
| POST multipart FormData với browser tự đặt boundary | Thường không | Nếu không thêm header không safelisted và các điều kiện còn lại thỏa |

**Không tự thêm `Content-Type: multipart/form-data` khi gửi `FormData` bằng fetch**: browser cần tạo boundary khớp body; tự đặt sai header có thể làm backend không parse multipart. Trường hợp có upload streaming, event listeners hoặc chính sách trình duyệt đặc biệt có thể ảnh hưởng preflight; hãy quan sát Network tab trên browser mục tiêu.

## 4. Luồng simple request: không có OPTIONS, vẫn phải có CORS headers

Frontend:

~~~javascript
const r = await fetch("https://api.example.test/api/demo/items", {
  method: "GET",
  headers: { Accept: "application/json" }
});
const items = await r.json();
~~~

Trình duyệt gửi trực tiếp request thực:

~~~http
GET /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

Server xử lý GET và thêm ít nhất một chính sách origin hợp lệ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

[{"id":1,"name":"Spring MVC"}]
~~~

**Không có `Access-Control-Request-Method` trong GET bình thường**, và `Access-Control-Allow-Methods` không phải điều kiện bắt buộc trên response của simple GET. Browser kiểm tra `Access-Control-Allow-Origin` (và credentials nếu request có credentials) để quyết định script có được đọc response.

Nếu server thiếu `Access-Control-Allow-Origin` hoặc giá trị không khớp origin, JavaScript thường thấy lỗi CORS/`TypeError: Failed to fetch`, không được đọc HTTP body/status như một response bình thường. Trong server logs, GET vẫn có thể được ghi nhận là 200. Vì vậy **“Network thấy 200” không chứng minh JavaScript có quyền đọc**.

### 4.1. Tại sao simple request không phải bảo vệ CSRF?

Một trang độc hại có thể gây browser gửi form POST đơn giản tới website khác khi cookie được trình duyệt đính kèm theo chính sách cookie. Dù CORS cấm script đọc response, **side effect trên server có thể đã xảy ra**.

CORS không phải bộ lọc CSRF. Với session/cookie authentication và các method có thay đổi dữ liệu, cần CSRF token hoặc cơ chế chống CSRF phù hợp, kiểm soát `SameSite`/`Secure`, kiểm tra Origin/Referer khi thích hợp và authorization cho từng hành động. Không tắt CSRF chỉ vì đã đặt allowlist CORS.

## 5. Preflight OPTIONS: browser hỏi gì trước khi gửi request thực?

Giả sử frontend muốn tạo tài nguyên bằng JSON:

~~~javascript
await fetch("https://api.example.test/api/demo/items", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-42"
  },
  body: JSON.stringify({ name: "Spring CORS" })
});
~~~

Vì JSON Content-Type và custom header không safelisted, browser thường gửi **preflight OPTIONS**:

~~~http
OPTIONS /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Ý nghĩa:
- `Origin`: trang gọi API.
- `Access-Control-Request-Method`: phương thức **dự định dùng trên request sau**, ở đây POST. Phương thức hiện tại là OPTIONS.
- `Access-Control-Request-Headers`: các header không safelisted mà actual request muốn sử dụng. Browser thường chuẩn hóa tên/lowercase và có thể sắp xếp thứ tự.
- Preflight **không gửi JSON body của POST**. Nó chỉ là hỏi chính sách.
- Theo Fetch, CORS preflight **không gửi credentials** (ví dụ cookies) của actual request. Một số môi trường TLS client certificates có sai lệch triển khai; không thiết kế quy trình app dựa trên credentials xuất hiện trong preflight.

Nếu server cấp quyền:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT
Access-Control-Allow-Headers: Content-Type, X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Dạng header `Vary` có thể được gộp thành một dòng danh sách thay vì ba dòng, ví dụ `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers`.

Sau khi preflight được chấp thuận, browser mới gửi actual request:

~~~http
POST /api/demo/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Content-Type: application/json
X-Request-Id: req-42

{"name":"Spring CORS"}
~~~

Response thực vẫn cần `Access-Control-Allow-Origin` phù hợp:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: create-1

{"id":2,"name":"Spring CORS"}
~~~

**Preflight thành công không thay thế kiểm tra CORS ở response thực.** Nếu response thực thiếu/không khớp allow-origin, browser vẫn không cho JavaScript đọc, dù POST đã chạy.

### 5.1. Browser không phải lúc nào cũng gửi OPTIONS trước từng request

Browser có thể cache một kết quả preflight theo origin/URL/method/headers và các quy tắc Fetch. `Access-Control-Max-Age` cho phép server đề xuất thời lượng cache; browser có thể đặt giới hạn riêng hoặc bỏ cache sau khi điều kiện thay đổi. Đây thường là cache riêng cho **kết quả preflight**, không phải cache HTTP payload của GET/POST.

Do đó việc DevTools không hiển thị OPTIONS ở lần thứ hai **không chứng minh API tự động trở thành simple**. Hãy thử “Disable cache”/cache-clearing, network conditions và origin/header cụ thể, nhưng hiểu rằng DevTools và user agent có thể quản lý preflight cache khác HTTP cache thông thường.

### 5.2. Khi preflight bị từ chối

Server có thể không trả allow headers tương ứng, hoặc Spring MVC/Spring Security có thể trả lỗi như **403 Invalid CORS request**. Browser lúc này **không gửi actual POST/PUT**. Ở JavaScript, ứng dụng thường nhận network/CORS rejection thay vì body 403 để phân tích bằng `response.json()`.

Không tạo controller `@RequestMapping(method=OPTIONS)` riêng chỉ để echo mọi header trong production. Spring MVC có CORS processor và policy tập trung; nếu tự echo `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` vô điều kiện, bạn đang mở quyền cross-origin ngoài ý muốn.

## 6. Bảng tất cả header CORS cần nhớ

### 6.1. Request headers

| Header | Ai gửi? | Xuất hiện khi nào? |
| --- | --- | --- |
| `Origin` | Browser / user-agent | Cross-origin request và preflight; cũng có thể có trên một số same-origin request |
| `Access-Control-Request-Method` | Browser | Preflight OPTIONS; chỉ phương thức actual mà client dự định dùng |
| `Access-Control-Request-Headers` | Browser | Preflight khi có header cần xin phép; là **danh sách tên header**, không phải giá trị Authorization/token |

Không cấu hình frontend tự gán `Access-Control-Request-Method` hoặc `Origin` để “vượt CORS”; browser quản lý những header đó. Client dùng `fetch` với method và headers thật, trình duyệt tự quyết định có preflight.

### 6.2. Response headers

| Header | Nơi có ý nghĩa | Ý nghĩa |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Preflight và actual response | Cho phép một origin cụ thể hoặc `*` khi không dùng credentials |
| `Access-Control-Allow-Methods` | Preflight | Cho phép các HTTP methods được hỏi |
| `Access-Control-Allow-Headers` | Preflight | Cho phép request headers mà browser đã liệt kê |
| `Access-Control-Allow-Credentials` | Preflight và actual với credentialed requests | Giá trị hợp lệ `true` cho phép credentials theo điều kiện CORS |
| `Access-Control-Max-Age` | Preflight | Số giây cache kết quả preflight (subject to browser limits) |
| `Access-Control-Expose-Headers` | Actual response | Cho phép JavaScript đọc thêm response headers ngoài nhóm được expose mặc định |
| `Vary` | Response có nội dung phụ thuộc Origin/preflight headers | Hướng dẫn cache phân biệt các biến thể response |

**Không nhầm `Access-Control-Allow-Headers` với `Access-Control-Expose-Headers`.** Allow-Headers liên quan header mà **client được gửi** (ví dụ Authorization, X-Request-Id). Expose-Headers liên quan header **server trả về** mà script được đọc qua `Response.headers.get(...)` (ví dụ X-Request-Id).

Ví dụ JavaScript:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/demo/items",
  { headers: { Accept: "application/json" } }
);

console.log(response.headers.get("X-Request-Id"));
~~~

Để JS đọc `X-Request-Id`, response cross-origin cần `Access-Control-Expose-Headers: X-Request-Id`. Header có thể vẫn hiển thị trong Network tab khi chưa expose, nhưng JS không được truy cập nó; cấu hình expose ở server, không tự thêm `Access-Control-Expose-Headers` vào request.

## 7. Wildcard, credentials, cookies và những giới hạn quan trọng

### 7.1. `Access-Control-Allow-Origin: *`

Với **request không dùng credentials**, policy `Access-Control-Allow-Origin: *` có thể cho phép code từ mọi origin đọc response. Nó phù hợp hơn với dữ liệu thật sự công khai, được chủ ý cung cấp cho mọi website.

Đối với request có credentials, **không được dùng `Access-Control-Allow-Origin: *`**. Browser yêu cầu allow-origin khớp một origin cụ thể; server cũng cần `Access-Control-Allow-Credentials: true`. Trong Spring Framework, `allowCredentials(true)` không tương thích với `allowedOrigins("*")`. Nếu thật sự cần pattern khớp nhiều origin, Spring có `allowedOriginPatterns` nhưng phải giới hạn pattern chặt chẽ; việc echo origin qua pattern quá rộng vẫn có thể mở quyền cho các website không đáng tin.

### 7.2. `fetch` và credentials

Frontend khi cần browser gửi cookie cross-origin:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

`credentials:"include"` chỉ là **ý định của client**; cookie còn phải thỏa domain/path/`Secure`/`SameSite` và chính sách browser về third-party cookies. Server phải phản hồi allow-origin cụ thể và `Access-Control-Allow-Credentials: true` để script được đọc.

Ngay cả khi CORS cho phép, cookie với `SameSite=Lax` hoặc `Strict` có thể không được gửi trong một request thật sự cross-site. Với `SameSite=None`, browser hiện đại yêu cầu `Secure`; một số browser hoặc policy người dùng vẫn chặn third-party cookies. **CORS không ép cookie vượt qua những giới hạn đó**.

Ví dụ actual response cho credentialed request:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"user":"example"}
~~~

Không bật credentials chỉ vì API có authentication bearer token: bearer header `Authorization` thường kích hoạt preflight do không safelisted, nhưng việc có header auth và việc dùng cookie/`credentials:"include"` là hai khía cạnh riêng. Hãy chọn policy dựa trên mô hình xác thực thực tế.

### 7.3. Preflight và Spring Security

Với browser thông thường, preflight OPTIONS **không mang session cookie**. Nếu security filter yêu cầu authentication cho OPTIONS trước khi CORS policy được kiểm tra, server có thể từ chối bằng 401/403 và browser không gửi request thực. Trong Spring Security nên xử lý CORS ở vị trí phù hợp **trước khi yêu cầu xác thực**. Tuy nhiên, cho preflight đi qua **không** có nghĩa mở quyền cho actual POST/DELETE: phương thức thật vẫn phải được authenticate/authorize/CSRF-check theo cấu hình.

### 7.4. CORS không phải authorization

- Browser thực thi kiểm tra CORS; client server-to-server có thể gọi API mà không cần tuân theo `Access-Control-Allow-Origin`.
- Không dùng header `Origin` thay `Authentication`/`Authorization`. Header Origin không phải danh tính đã xác thực.
- CORS không bảo vệ server khỏi mọi request thay đổi trạng thái và không thay thế CSRF.
- CORS không quyết định role/permission của user sau khi login.
- Cross-origin không đồng nghĩa cross-site; cookie rules và origin rules khác nhau.
- Một lỗi CORS trên browser không chứng minh endpoint backend là 404/500; server có thể đã thành công nhưng response không được script đọc.

## 8. Cấu hình CORS trong Spring MVC

Có hai cách chính: annotation trên controller (`@CrossOrigin`) hoặc cấu hình URL patterns toàn cục qua `WebMvcConfigurer`. Cả hai dùng `CorsConfiguration` / CORS processor nội bộ của Spring MVC.

### 8.1. `@CrossOrigin`

Ví dụ fragment:

~~~java
@RestController
@RequestMapping("/api/public")
@CrossOrigin(origins = "https://app.example.test", maxAge = 600)
class PublicApiController {

    @GetMapping("/status")
    public String status() {
        return "ok";
    }
}
~~~

Đây là snippet cần imports Spring tương ứng và nằm trong project Spring MVC. `@CrossOrigin` có thể đặt cấp method hoặc class. Với cấu hình mặc định không chỉ rõ origins, Spring MVC có thể cho phép tất cả origins, nên **không dùng `@CrossOrigin` trống trên controller nhạy cảm mà chưa xét security model**.

Khi cấu hình class-level và method-level cùng tồn tại, Spring MVC có thể kết hợp cấu hình. Không tự giả định annotation ở method sẽ luôn “thu hẹp” toàn bộ origin ở class theo kiểu deny-by-default; kiểm tra thực tế bằng MockMvc nếu có nhiều lớp config.

### 8.2. `WebMvcConfigurer` và allowlist tường minh

Đối với nhiều endpoint, policy tập trung dễ kiểm soát hơn:

~~~java
package com.example.corsdemo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/demo/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST", "PUT")
                .allowedHeaders("Content-Type", "X-Request-Id", "Authorization")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

Trong policy ví dụ:
- Chỉ allow `https://app.example.test`.
- Chỉ CORS-enable GET, POST, PUT trên các path `/api/demo/**`; không cấp quyền CORS cho tất cả URL của server.
- `Content-Type`, `X-Request-Id`, `Authorization` là những **header có thể xin phép qua preflight**. **Chúng không tự tạo authentication**; controller/security phải xử lý Authorization nếu dùng.
- `X-Request-Id` được expose để JavaScript đọc trong actual response.
- `allowCredentials(false)` cho biết demo không hỗ trợ credentialed CORS.
- `maxAge(600)` đề xuất cache kết quả preflight 600 giây; browser có giới hạn riêng.

**Đừng đồng nhất allowedMethods với methods thật của controller:** cấu hình CORS cho phép một method không làm Spring tạo endpoint chưa tồn tại. Ví dụ cho phép `PUT` nhưng handler không có `@PutMapping` vẫn có thể nhận 405 khi actual request được xử lý.

Spring MVC global config thường có các mặc định cho origins/headers/methods khi chưa đặt giá trị, và `maxAge` mặc định hay gặp là 1800 giây. Nhưng một đối tượng `new CorsConfiguration()` thuần không mặc nhiên cho mọi origin; các defaults được áp theo ngữ cảnh cấu hình. Với API có yêu cầu rõ ràng, **nêu tất cả giới hạn quan trọng tường minh** như snippet trên.

### 8.3. Global và local config chồng nhau

Nếu một method có `@CrossOrigin` và ứng dụng đồng thời khai báo `WebMvcConfigurer.addCorsMappings`, Spring MVC có thể kết hợp local/global `CorsConfiguration`. Với các thuộc tính collection như allowed origins, cấu hình ghép có thể rộng hơn dự định. Nếu mục tiêu là allowlist nghiêm ngặt, ưu tiên một nguồn policy rõ ràng hoặc viết MockMvc test chứng minh các origin/method/headers thực tế bị từ chối đúng.

Nếu có Spring Security, CORS filter và MVC configuration phải phối hợp. **Không thêm thủ công một CorsFilter trùng policy** mà không hiểu thứ tự filter chain và việc merge/override; hai bộ phát header khác nhau có thể tạo ra phản hồi khó dự đoán.

## 9. Ứng dụng hoàn chỉnh: Java 17 + Spring Boot 3.3.5

Một project Spring MVC nhỏ, **không bật Spring Security**, để quan sát CORS độc lập với login/CSRF. Sau đó mục 12 trình bày cách tích hợp Spring Security.

~~~text
cors-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/corsdemo/
    │   ├── CorsDemoApplication.java
    │   └── web/
    │       ├── CorsConfig.java
    │       └── ItemController.java
    └── test/java/com/example/corsdemo/web/
        └── ItemCorsTest.java
~~~

### 9.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'cors-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` chứa Spring MVC và JSON converter cần cho ví dụ. Không có dependency Spring Security, nên **đừng suy luận demo đã bảo vệ API thực tế**. Trong sản phẩm production cần thêm cơ chế auth, authorization, CSRF/rate limiting theo use case.

### 9.2. Main application

`src/main/java/com/example/corsdemo/CorsDemoApplication.java`:

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

Cấu hình `CorsConfig.java` chính là file đầy đủ ở mục 8.2, lưu tại `src/main/java/com/example/corsdemo/web/CorsConfig.java`.

### 9.3. REST controller: GET, POST, PUT

`src/main/java/com/example/corsdemo/web/ItemController.java`:

~~~java
package com.example.corsdemo.web;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo/items")
public class ItemController {

    public record Item(long id, String name) {}
    public record ItemInput(String name) {}

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<List<Item>> list() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "list-1")
                .body(List.of(new Item(1L, "Spring MVC")));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> create(@RequestBody ItemInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-Id", "create-1")
                .body(new Item(2L, input.name()));
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> update(
            @PathVariable("id") long id,
            @RequestBody ItemInput input) {
        return ResponseEntity.ok(new Item(id, input.name()));
    }
}
~~~

Giải thích:
- GET trả danh sách JSON và header `X-Request-Id`. CORS config expose header này cho JS.
- POST nhận JSON rồi tạo representation cố định ID 2; **không lưu database**, nên đây không phải API quản lý dữ liệu hoàn chỉnh.
- PUT chứng minh một method yêu cầu preflight khi gọi từ browser cross-origin.
- Controller không tự đọc header `Origin` và không set `Access-Control-Allow-Origin` bằng tay. Spring MVC CORS mapping chịu trách nhiệm về chính sách.
- `@PostMapping(consumes=application/json)` điều khiển request body/media type; **khác** việc CORS kiểm tra request headers. CORS success không bảo đảm JSON hợp lệ hoặc business action thành công.

## 10. Gọi thử HTTP và phân tích response

Chạy trong project có Gradle wrapper và Java 17:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell/CMD dùng `.\gradlew.bat bootRun`. Phần HTTP local chạy ở `http://localhost:8080`, còn allow-origin trong config là `https://app.example.test`: điều này **vẫn hợp lệ** để kiểm tra server CORS response bằng curl, vì `Origin` là giá trị nguồn do browser/curl mô tả, không cần chạy một trang frontend thực để dùng curl.

### 10.1. Mô phỏng GET simple

~~~bash
curl -i 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Accept: application/json'
~~~

Dự kiến HTTP **200**, body:

~~~json
[{"id":1,"name":"Spring MVC"}]
~~~

Quan sát response headers:
- `Access-Control-Allow-Origin: https://app.example.test`.
- `Access-Control-Expose-Headers: X-Request-Id`.
- `X-Request-Id: list-1`.
- Thường có `Vary: Origin` và các preflight-related Vary values do Spring thêm.

**Không thấy OPTIONS** vì curl không tự preflight như browser. Nếu gọi cùng GET từ browser với điều kiện CORS-safelisted, browser gửi GET trực tiếp.

### 10.2. Mô phỏng OPTIONS preflight cho POST JSON

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id'
~~~

Với policy `CorsConfig`, dự kiến status 2xx (thường HTTP 200), và:
- `Access-Control-Allow-Origin` là origin được cho phép.
- `Access-Control-Allow-Methods` bao gồm POST.
- `Access-Control-Allow-Headers` bao gồm Content-Type và X-Request-Id.
- `Access-Control-Max-Age` là 600 giây.
- Response có `Vary` thích hợp.

Body preflight thường rỗng. **Không phải controller `create()` đang chạy**; OPTIONS được CORS processor xử lý. Vì vậy không kỳ vọng ID 2 hay JSON item ở response OPTIONS.

### 10.3. Mô phỏng actual POST sau preflight

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://app.example.test' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req-42' \
  -d '{"name":"Spring CORS"}'
~~~

Dự kiến HTTP **201 Created**, body:

~~~json
{"id":2,"name":"Spring CORS"}
~~~

Response có `Access-Control-Allow-Origin`; header `X-Request-Id` do controller tạo ra có giá trị `create-1` và được expose trong CORS config. CORS không buộc server phải echo giá trị `req-42` từ request.

**curl chỉ gửi đúng một POST**, không tự gửi OPTIONS ở trước. Để quan sát hai requests browser gửi thật, cần trang frontend khác origin hoặc DevTools Network. Vì vậy kết quả của curl là phép thử **chính sách CORS ở server**, không chứng minh browser chắc chắn không bị lỗi cookie, CSP, mixed content hay preflight caching.

### 10.4. Origin không được cấp quyền

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/demo/items' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Trong Spring MVC với CORS mapping này, preflight có origin không hợp lệ thường bị từ chối **403 Invalid CORS request**. Browser không gửi actual POST nếu preflight không qua. Đối với request GET cross-origin thực, Spring có thể từ chối 403, trong khi những hệ thống khác có thể trả response không kèm allow-origin rồi để browser chặn đọc.

**Không viết frontend dựa trên body 403 của CORS rejection**, vì browser thường che response khỏi script. Quan sát status và log qua DevTools/server diagnostics.

### 10.5. Không có Origin

~~~bash
curl -i 'http://localhost:8080/api/demo/items'
~~~

Dự kiến vẫn trả HTTP 200 và JSON. Không có request origin thì policy CORS thường không thêm `Access-Control-Allow-Origin`. Điều này không phải lỗ hổng trong CORS; CORS không được thiết kế để ngăn mọi HTTP client ngoài browser gửi request. Authentication/authorization phải hoạt động độc lập.

## 11. MockMvc: kiểm thử cả simple và preflight

`src/test/java/com/example/corsdemo/web/ItemCorsTest.java`:

~~~java
package com.example.corsdemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalToIgnoringCase;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemCorsTest {

    private static final String ORIGIN = "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void simpleGetHasCorsOriginAndExposesResponseHeader() throws Exception {
        mvc.perform(get("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(header().string(
                        "Access-Control-Expose-Headers", "X-Request-Id"))
                .andExpect(header().string("X-Request-Id", "list-1"))
                .andExpect(jsonPath("$[0].name").value("Spring MVC"));
    }

    @Test
    void preflightOptionsAllowsConfiguredPostAndHeaders() throws Exception {
        mvc.perform(options("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type,x-request-id"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(header().string("Access-Control-Allow-Methods",
                        containsString("POST")))
                .andExpect(header().string("Access-Control-Max-Age", "600"));
    }

    @Test
    void actualJsonPostStillRequiresRealHandler() throws Exception {
        mvc.perform(post("/api/demo/items")
                        .header("Origin", ORIGIN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Spring CORS\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Access-Control-Allow-Origin", ORIGIN))
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.name").value("Spring CORS"));
    }

    @Test
    void rejectedOriginCannotPreflight() throws Exception {
        mvc.perform(options("/api/demo/items")
                        .header("Origin", "https://evil.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "content-type"))
                .andExpect(status().isForbidden());
    }

    @Test
    void getWithoutOriginDoesNotNeedCorsResponseHeader() throws Exception {
        mvc.perform(get("/api/demo/items"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }
}
~~~

Trong file test, không cần import matcher `equalToIgnoringCase` vì chưa sử dụng; nếu IDE/Checkstyle kiểm tra unused imports, hãy xóa dòng đó. Các assertion còn lại đủ minh họa preflight và actual response. Chạy:

~~~bash
./gradlew test
~~~

MockMvc không mở browser thật và **không tự gửi preflight** khi test dùng `post(...)`. Việc tạo `options(...)` trong test là mô phỏng yêu cầu preflight và kiểm chính sách Spring. Với browser thật cần kiểm tra thêm network stack, cache, cookie policy, origin hiện tại, reverse proxy và security filters. `MockMvc` giúp kiểm những quyết định server, nhưng không thay thế E2E cross-origin test.

### 11.1. Test header permissions có thực sự được trả không?

Test trên chỉ kiểm allow-origin, method và max-age để tránh phụ thuộc format/casing của allow-headers. Hãy bổ sung một assertion **case-insensitive** hoặc tách danh sách header để xác nhận `Content-Type` và `X-Request-Id` trong `Access-Control-Allow-Headers` nếu đây là hợp đồng cần bảo vệ. Header names HTTP không phân biệt hoa/thường; đừng viết test thất bại chỉ vì server trả `content-type` thay vì `Content-Type`.

Với ứng dụng production, test **ít nhất**:
- Origin cho phép và origin từ chối.
- Method cho phép và method từ chối.
- Headers được phép và header không nằm trong allowlist.
- Credentials on/off, wildcard bị chặn đúng.
- Response actual có allow-origin, expose-headers khi cần.
- CORS đi qua Spring Security filter chain trước authentication/CSRF.
- Request không có Origin không bị CORS policy khóa nhầm.

## 12. Khi tích hợp Spring Security

Đối với Spring MVC có Spring Security, CORS phải được tích hợp để preflight không bị authentication challenge vô lý **trước khi** Spring xem CORS policy. Spring Security có `HttpSecurity.cors(...)` và có thể dùng CORS configuration do MVC cung cấp khi có đúng `HandlerMappingIntrospector`/integration và không có nguồn cấu hình CORS khác cạnh tranh.

Ví dụ **fragment** để đưa vào dự án đã có `spring-boot-starter-security`, controller và CorsConfig của mục 8:

~~~java
package com.example.corsdemo.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/demo/**").authenticated()
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

Đoạn code là file độc lập nếu đã thêm Spring Security starter, nhưng **không thuộc app runnable không-security ở mục 9**. Việc `authenticated()` ở đây chỉ để minh họa policy thực tế: request POST vẫn chịu CSRF mặc định nếu dùng cookie/session authentication; nếu không có credential phù hợp, actual request sẽ bị từ chối. Không mong tất cả MockMvc tests ở mục 11 vẫn đạt khi thêm class này mà không cấu hình test user/CSRF tokens. Ví dụ JWT resource server có chính sách CSRF/session khác và phải được thiết kế riêng.

**Không cấu hình security kiểu “permitAll OPTIONS” như giải pháp duy nhất** rồi quên CORS: OPTIONS phải được CORS processor kiểm tra origin/method/headers; cho phép tất cả OPTIONS ở security layer không tự làm browser nhận `Access-Control-Allow-Origin` hợp lệ. Ngược lại, CORS preflight được duyệt không làm user authorized cho request thực.

Nếu ứng dụng dùng nhiều `SecurityFilterChain`, một chain có `cors()` không đảm bảo chain khác cũng xử lý đúng route; hãy test đường dẫn thực dưới toàn bộ filter chain.

## 13. Các lỗi CORS phổ biến, phân biệt theo tầng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / sửa |
| --- | --- | --- |
| Console báo thiếu `Access-Control-Allow-Origin` | Route/proxy/error response không thêm CORS header | Kiểm Network + actual HTTP response và policy mapping |
| GET bằng curl được, fetch bị chặn | Browser kiểm CORS, curl không | Gửi `Origin` bằng curl và quan sát allow-origin |
| OPTIONS 401/403 trước POST | Security hoặc CORS policy chặn preflight | Kiểm filter ordering, `cors()`, origin, method, headers |
| POST form hoạt động nhưng POST JSON bị CORS | JSON Content-Type kích hoạt preflight | Cấu hình POST và Content-Type trong allowlist |
| GET với Authorization bị preflight | Authorization không safelisted | Cho phép Authorization header có chủ đích; vẫn xác thực actual |
| OPTIONS 200 nhưng POST/PUT không đến | Preflight response thiếu/mismatch allow-origin/method/headers | So `Access-Control-Request-*` với `Access-Control-Allow-*` |
| OPTIONS qua nhưng actual response bị chặn | Actual response không có CORS headers hợp lệ | Kiểm response thực/error handler/reverse proxy |
| Cookie không gửi với `credentials:include` | SameSite, Secure, domain/path, third-party cookie policy | Kiểm cookie attributes và browser policy |
| Có cookie nhưng JavaScript vẫn không đọc body | Thiếu `Access-Control-Allow-Credentials:true` hoặc allow-origin là `*` | Dùng origin cụ thể + credentials true |
| JS không đọc được `X-Request-Id` | Chưa expose response header | `Access-Control-Expose-Headers` |
| `@CrossOrigin` trên controller không áp dụng | Path không match, khác handler, Spring Security trước MVC | Kiểm handler mapping/filter chain |
| CORS vô tình mở mọi origin | `@CrossOrigin` quá rộng hoặc global/local config merge | Dùng explicit allowlist và negative tests |
| OPTIONS response bị redirect | Reverse proxy/auth redirect hoặc URL normalize | Preflight nên trả policy trực tiếp, kiểm gateway |
| DevTools không thấy OPTIONS lần hai | Preflight caching | Kiểm `Access-Control-Max-Age` và browser cache behavior |
| Header `Vary` thiếu khi origin phản hồi động | Cache dùng response sai biến thể | Thiết lập Vary đúng qua CORS processor/proxy |
| HTTP 500 bị báo như CORS error | Error path không thêm allow-origin | Xem server logs/status, xử lý CORS cho error responses đúng policy |
| Browser báo mixed content | HTTPS frontend gọi HTTP backend | Dùng HTTPS; đây không chỉ là CORS |
| Browser báo CSP `connect-src` | CSP của frontend chặn đích | Chỉnh Content Security Policy, không phải CORS ở backend |

### 13.1. Quy trình gỡ lỗi có thứ tự

1. Xác định **origin thực** của trang frontend, bao gồm scheme/host/port. Đừng lẫn origin của API với origin frontend.
2. Trong DevTools Network, tìm request OPTIONS (nếu có) và actual request. Ghi rõ method, URL, `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Với preflight, đối chiếu status và `Access-Control-Allow-Origin/Methods/Headers/Max-Age`. Nếu OPTIONS thất bại, đừng tập trung sửa controller POST trước khi kiểm policy.
4. Với actual response, đối chiếu allow-origin, allow-credentials, expose-headers; xem cookie flags và `fetch(credentials)`.
5. Kiểm mappings `@CrossOrigin` / `CorsRegistry`, có config chồng nhau hay không.
6. Nếu có Spring Security, đảm bảo CORS chạy trước bước auth cần credential; đồng thời kiểm actual permissions/CSRF độc lập.
7. Kiểm ingress/API gateway/CDN có tự xử lý OPTIONS, ghi đè/xóa header, cache sai `Vary` hoặc redirect HTTPS không.
8. Dùng curl với headers tương đương để xác nhận server behavior, rồi trở lại browser kiểm SameSite, mixed content, CSP và preflight cache.
9. Thêm MockMvc test cho allow + deny để regression không âm thầm mở origin hoặc header ngoài ý muốn.
10. Ghi log có kiểm soát route, origin/method/header names và error status; không log Authorization token/cookie/session ID.

## 14. Câu hỏi tự kiểm tra

**1.** Hai URL cùng hostname nhưng khác port có cùng origin không?

**Trả lời:** Không, trừ khi port được diễn giải cùng effective port; port là một phần của origin.

**2.** Vì sao POST JSON cross-origin thường có OPTIONS trong khi POST form urlencoded thường không?

**Trả lời:** `application/json` không nằm trong CORS-safelisted Content-Type. `application/x-www-form-urlencoded` có thể safelisted nếu các điều kiện method/headers khác thỏa.

**3.** Một simple GET không có OPTIONS thì có cần `Access-Control-Allow-Origin` không?

**Trả lời:** Có, để browser cho phép JavaScript đọc response cross-origin. “Không preflight” không đồng nghĩa “bỏ kiểm CORS”.

**4.** Header nào trong OPTIONS nói browser muốn dùng method thật là PUT?

**Trả lời:** `Access-Control-Request-Method: PUT`; còn HTTP method của request hỏi phép vẫn là `OPTIONS`.

**5.** Phân biệt Allow-Headers và Expose-Headers?

**Trả lời:** `Access-Control-Allow-Headers` cho biết header **request** nào được gửi; `Access-Control-Expose-Headers` cho biết header **response** nào script được đọc.

**6.** Có thể dùng `Access-Control-Allow-Origin:*` với cookie-authenticated credentialed CORS không?

**Trả lời:** Không. Với credentialed CORS, response cần origin cụ thể phù hợp và `Access-Control-Allow-Credentials:true`; cookie vẫn chịu SameSite/Secure/browser policy.

**7.** Vì sao `curl -H 'Origin: ...'` thành công không bảo đảm frontend chạy được?

**Trả lời:** curl không triển khai toàn bộ browser CORS enforcement, preflight cache, cookie policy, mixed content và CSP. Nó chỉ giúp quan sát response server.

**8.** Nếu browser preflight không mang cookie nên Spring Security trả 401 thì nên xử lý ở đâu?

**Trả lời:** Tích hợp CORS processor trước yêu cầu authentication, thường với `http.cors(...)` và MVC CORS configuration phù hợp; actual request vẫn phải đi qua security/CSRF rules.

**9.** CORS có bảo vệ khỏi CSRF khi browser đã gửi simple POST không?

**Trả lời:** Không. Simple request có thể được gửi và gây side effect trước khi browser quyết định có cho đọc response. Phải dùng CSRF/authorization controls phù hợp.

## 15. Checklist khi cấu hình CORS trên production

1. Định nghĩa explicit allowed origins có scheme/host/port đúng, không dùng wildcard cho dữ liệu nhạy cảm.
2. Giới hạn allowed methods theo API thực, và allowed request headers theo nhu cầu thực tế.
3. Chỉ bật credentials khi có use case, không kết hợp wildcard origin với credentials.
4. Định nghĩa exposed response headers tối thiểu cần thiết, tránh expose thông tin bí mật.
5. Đặt maxAge hợp lý, hiểu browser có cache giới hạn.
6. Đảm bảo `Vary` đúng khi response phụ thuộc Origin/request method/request headers.
7. Đưa CORS vào đúng filter chain nếu có Spring Security; actual request vẫn cần auth, authorization và CSRF.
8. Cấu hình reverse proxy/CDN/gateway không phá CORS headers, không cache phản hồi từ origin khác.
9. Kiểm cả browser và MockMvc: simple GET, JSON POST preflight, PUT preflight, allowed/denied origin, allowed/denied headers, credentialed flow.
10. Đừng dùng CORS làm substitute cho authentication, tenant validation, network ACL, CSRF hoặc rate limiting.
11. Kiểm URL HTTPS, frontend CSP `connect-src`, cookie SameSite/Secure/third-party policy.
12. Khi lỗi production, đối chiếu OPTIONS và actual request trước khi sửa logic controller.

## 16. Tài liệu chính thức

- [Spring Framework — CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `@CrossOrigin`, global `WebMvcConfigurer`, credentialed requests, policy defaults và kết hợp local/global.
- [Spring Framework — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowed origins/origin patterns, methods, headers, credentials, maxAge và validate wildcard.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước authentication và tích hợp `http.cors`.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple/safelisted requests, preflight và giải thích các request/response headers.
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request): OPTIONS, access-control-request headers và preflight cache.
- [Fetch Standard — CORS Protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): định nghĩa chuẩn về preflight, safelisted request headers, credentials và kiểm CORS.
- [MDN — Set-Cookie, SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cơ chế cookie tách biệt với CORS.
- [Spring Framework — CORS support in HandlerMapping](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS preflight handling và các điểm cấu hình ở MVC mapping.

**Kết luận cần nhớ:** request *simple* **không có preflight nhưng vẫn phải được browser cho phép đọc response**; request JSON/custom-header/non-safelisted method thường đi qua **OPTIONS preflight** để xin quyền trước actual request. Spring MVC phát header theo `CorsConfiguration`; Spring Security cần tích hợp đúng thứ tự. CORS bảo vệ việc script đọc dữ liệu cross-origin theo browser policy, **không thay authentication, authorization hoặc CSRF**.
