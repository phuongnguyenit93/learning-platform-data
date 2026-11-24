# Access-Control-Allow-Origin: kiểm soát origin được phép đọc phản hồi CORS

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của response header **`Access-Control-Allow-Origin` (ACAO)** trong cơ chế Cross-Origin Resource Sharing (CORS).
2. Xác định giá trị ACAO hợp lệ theo **serialized origin**, phân biệt origin với URL đầy đủ, hostname, site và địa chỉ IP.
3. Chọn đúng giữa wildcard `*` và một origin cụ thể; giải thích vì sao wildcard không dùng được với request có credentials mode `include`.
4. Thiết kế allowlist origin an toàn, tránh phản chiếu `Origin` tùy tiện, tránh chấp nhận `null` và tránh kiểm tra bằng chuỗi con/tiền tố.
5. Cấu hình CORS nhất quán cho **preflight response** và **actual response**, xử lý cache với `Vary: Origin`.
6. Phân biệt CORS với xác thực, phân quyền, SOP và CSRF; kiểm chứng kết quả bằng DevTools và ví dụ backend.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web. ACAO là một phần của CORS, cho phép server tuyên bố origin nào được đọc phản hồi bằng JavaScript. Nó bổ sung cho SOP, cookie, CSRF defense và security headers; bản thân header này không xác thực người dùng hay cấp quyền truy cập dữ liệu ở phía server.

## 1. ACAO giải quyết vấn đề gì?

Theo **Same-Origin Policy (SOP)**, JavaScript của một origin thường không được tự do đọc phản hồi từ origin khác. CORS cho phép server đích chủ động chia sẻ một số phản hồi cross-origin với mã chạy trong browser.

Giả sử frontend ở `https://app.example.test` cần đọc API ở `https://api.example.test`. Hai URL **khác origin** vì hostname khác nhau, dù chúng có thể cùng site. Frontend gửi:

```http
GET /profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
```

Nếu server muốn cho JavaScript từ frontend đọc response, server có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Content-Type: application/json

{"id": 42, "displayName": "An"}
```

Browser so sánh origin của request với giá trị ACAO trong response theo thuật toán CORS. Khi các kiểm tra còn lại đều đạt, browser cho phép script nhận nội dung response. Nếu ACAO thiếu hoặc không khớp, JavaScript không được đọc response và DevTools thường hiển thị lỗi CORS.

**ACAO là một tuyên bố của server trên response:** “origin này được phép chia sẻ phản hồi với JavaScript”. Nó không phải header request và không có nghĩa server đã xác thực hoặc cấp quyền cho người dùng.

## 2. Cú pháp và cách browser đối chiếu ACAO

Với một response CORS thông thường, giá trị ACAO có một trong hai dạng:

```http
Access-Control-Allow-Origin: *
```

Hoặc:

```http
Access-Control-Allow-Origin: https://app.example.test
```

- **`*`:** cho phép chia sẻ response với mọi origin trong trường hợp request không dùng credentials mode `include`.
- **Một serialized origin cụ thể:** chỉ cho phép origin khớp chính xác với giá trị đó.

Với origin tuple HTTP(S), serialized origin gồm **scheme + host + port có hiệu lực**; cổng mặc định được chuẩn hóa và không có path hay dấu gạch chéo cuối.

| Giá trị ACAO | Kết quả với request từ `https://app.example.test` | Giải thích |
| --- | --- | --- |
| `https://app.example.test` | Hợp lệ nếu các kiểm tra CORS khác đạt | Khớp serialized origin |
| `https://app.example.test:443` | Không phải cách biểu diễn chuẩn cần gửi | Origin HTTPS mặc định được chuẩn hóa thành không ghi port |
| `https://app.example.test/` | Không khớp | Có dấu gạch chéo/path; không phải serialized origin |
| `http://app.example.test` | Không khớp | Khác scheme |
| `https://api.example.test` | Không khớp | Khác host |
| `https://app.example.test:8443` | Không khớp | Khác port |
| `*` | Hợp lệ với request không có credentials mode `include` | Wildcard |
| `https://app.example.test, https://admin.example.test` | Không hợp lệ | ACAO không nhận danh sách origin phân cách bằng dấu phẩy |

**Không được** gửi nhiều ACAO để liệt kê nhiều origin:

```http
# SAI
Access-Control-Allow-Origin: https://app.example.test, https://admin.example.test

# SAI: hai header ACAO riêng cũng không phải cơ chế allowlist
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: https://admin.example.test
```

Một response chỉ nên có **một giá trị ACAO** phù hợp với request hiện tại. Nếu cần cho nhiều frontend, server chọn origin hiện tại từ allowlist rồi trả đúng một origin, hoặc dùng `*` khi dữ liệu thật sự công khai và không cần credentials.

### Không nhầm origin với site hoặc URL đầy đủ

Lấy `https://app.example.test` làm origin được phép:

| Origin gửi trong request | Khớp ACAO cụ thể? | Lý do |
| --- | :---: | --- |
| `https://app.example.test` | Có | Cùng scheme, host, port |
| `https://app.example.test:443` | Có sau chuẩn hóa | Port mặc định HTTPS |
| `https://app.example.test:8443` | Không | Port khác |
| `http://app.example.test` | Không | Scheme khác |
| `https://admin.example.test` | Không | Subdomain khác |
| `https://app.example.test.attacker.test` | Không | Host khác |

Không đưa path vào ACAO. Ví dụ `https://app.example.test/dashboard` là URL, không phải giá trị origin hợp lệ cho header này.

## 3. Wildcard `*` và request có credentials

Một request có thể mang credentials như cookie, HTTP authentication hoặc thông tin xác thực liên quan mà browser quản lý. Với Fetch API, tùy chọn `credentials` xác định việc gửi credentials và xử lý response:

```js
// Mặc định: credentials mode "same-origin"
fetch("https://api.example.test/public-data");

// Gửi credentials trong request cross-origin (nếu browser cho phép)
fetch("https://api.example.test/profile", {
  credentials: "include"
});
```

Nếu credentials mode là `include`, server phải trả **origin cụ thể** và cho phép credentials:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
```

Header `Access-Control-Allow-Credentials` chỉ có giá trị cho phép là chuỗi chữ thường chính xác `true`. Với request có credentials mode `include`, browser **không chấp nhận** ACAO wildcard `*`, kể cả khi ở thời điểm đó không có cookie nào thực sự được gửi.

| Fetch credentials mode | ACAO | `Access-Control-Allow-Credentials` | Kết quả CORS |
| --- | --- | --- | --- |
| `omit` hoặc `same-origin` cho request cross-origin | `*` | Không cần | Có thể hợp lệ |
| `include` | `*` | `true` | **Không hợp lệ** |
| `include` | Origin cụ thể khớp request | Thiếu | Không hợp lệ |
| `include` | Origin cụ thể khớp request | `true` | Có thể hợp lệ nếu các kiểm tra khác đạt |
| `include` | Origin khác request | `true` | Không hợp lệ |

**Lưu ý cookie:** CORS thành công không đảm bảo cookie sẽ được gửi. Cookie vẫn chịu `SameSite`, `Secure`, domain/path, chính sách third-party cookie, partitioning và cài đặt quyền riêng tư của browser. `Access-Control-Allow-Credentials` cũng không tự tạo phiên đăng nhập.

### Ví dụ response không hợp lệ

```http
# SAI: wildcard không dùng được với credentials mode include
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Sửa thành:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
```

Chỉ dùng cấu hình credentials khi frontend thật sự cần credential. Nếu endpoint cung cấp dữ liệu công khai, nên cân nhắc không dùng credentials và giữ cấu hình đơn giản.

## 4. Origin `null` và opaque origin

Trong một số ngữ cảnh, browser tuần tự hóa origin thành chuỗi `null`, ví dụ document có **opaque origin**. Các trường hợp có thể gặp gồm:

- iframe bị sandbox nhưng không có token `allow-same-origin`;
- document tạo từ một số URL `data:`;
- một số ngữ cảnh file/local hoặc document đặc biệt, tùy chính sách browser.

Khi request có `Origin: null`, response sau đây có thể vượt qua phép so khớp ACAO cho serialized origin đó:

```http
Access-Control-Allow-Origin: null
```

Nhưng **không nên** mặc định cho phép `null`. Nhiều opaque origin khác nhau có thể cùng được biểu diễn bằng chuỗi này; nó không xác định một website hoặc ứng dụng đáng tin duy nhất. Một trang độc hại có thể tạo sandboxed iframe và phát sinh request với origin serialized `null`.

Quy tắc thực tế:

- Không thêm `null` vào allowlist chỉ để “sửa lỗi CORS” của file, iframe sandbox hoặc môi trường local.
- Không phản chiếu `Origin: null` thành ACAO `null` một cách tự động.
- Nếu có yêu cầu tích hợp đặc biệt với opaque origin, hãy đánh giá threat model riêng; thường nên thiết kế lại để dùng một origin HTTPS riêng, có danh tính rõ ràng.

## 5. Cho phép nhiều frontend bằng allowlist an toàn

Một backend có thể phục vụ nhiều frontend:

- `https://app.example.test`
- `https://admin.example.test`

Trong mỗi request, browser gửi `Origin`; backend kiểm tra giá trị này với **allowlist chính xác** rồi mới trả một ACAO tương ứng.

```text
Request A:
Origin: https://app.example.test

Response A:
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

Request B:
Origin: https://admin.example.test

Response B:
Access-Control-Allow-Origin: https://admin.example.test
Vary: Origin
```

### Không phản chiếu origin bất kỳ

Lỗi cấu hình nguy hiểm:

```js
// SAI: chấp nhận bất cứ origin nào mà client gửi
res.setHeader("Access-Control-Allow-Origin", req.headers.origin);
res.setHeader("Access-Control-Allow-Credentials", "true");
```

Khi kết hợp credentials, cách làm này có thể cho website do kẻ tấn công kiểm soát đọc response chứa dữ liệu của người dùng đã đăng nhập. Browser chỉ thực thi chính sách server khai báo; nó không biết origin nào đáng tin với nghiệp vụ của ứng dụng.

### Kiểm tra chính xác, không dùng chuỗi con hoặc tiền tố

Ví dụ các kiểm tra sai:

```js
const origin = req.headers.origin;

// SAI: chấp nhận host giả có phần đuôi trông giống
origin.endsWith("example.test");

// SAI: origin đáng tin xuất hiện ở bất kỳ vị trí nào trong chuỗi
origin.includes("app.example.test");

// SAI: chấp nhận subdomain ngoài dự kiến
origin.startsWith("https://app.example.test");
```

Các giá trị như `https://app.example.test.attacker.test`, `https://evil.test/?next=app.example.test` hoặc `https://app.example.test.evil` có thể đánh lừa kiểm tra chuỗi đơn giản.

Ví dụ allowlist rõ ràng:

```js
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test"
]);

function getAllowedOrigin(originHeader) {
  if (typeof originHeader !== "string") return null;
  if (!allowedOrigins.has(originHeader)) return null;
  return originHeader;
}
```

Với cấu hình đã biết trước, so sánh trực tiếp **serialized origin** với allowlist thường là lựa chọn dễ kiểm tra nhất. Nếu hệ thống nhận đầu vào URL và cần chuẩn hóa, hãy parse bằng URL parser, giới hạn scheme `https:`, sau đó so sánh `url.origin` với tập origin đã định nghĩa; không tự xây bộ parser bằng regex.

**Origin không phải danh tính người dùng.** Một origin được allowlist chỉ có nghĩa browser được phép chia sẻ response với script chạy tại đó. Backend vẫn phải kiểm tra session, role, quyền trên từng đối tượng và mục đích nghiệp vụ.

## 6. ACAO trong preflight và actual response

Một request CORS có thể là **simple request** hoặc cần **preflight**. Preflight là request `OPTIONS` do browser tự gửi trước request thực tế khi phương thức/header/content type không thuộc nhóm đơn giản theo quy tắc Fetch/CORS.

Ví dụ frontend gửi:

```js
fetch("https://api.example.test/orders/42", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": "token-value"
  },
  body: JSON.stringify({ status: "confirmed" })
});
```

Browser có thể gửi preflight:

```http
OPTIONS /orders/42 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
```

Server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Nếu preflight hợp lệ, browser mới tiếp tục request `PUT`. **Response thực tế** cũng cần ACAO khớp origin; với credentials mode `include`, response thực tế cũng cần `Access-Control-Allow-Credentials: true`. Chỉ trả header đúng trên OPTIONS nhưng quên response PUT vẫn làm JavaScript không đọc được dữ liệu.

| Giai đoạn | Header liên quan | Vai trò |
| --- | --- | --- |
| Request preflight `OPTIONS` | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` | Browser hỏi server có cho phép origin, method và header dự kiến không |
| Response preflight | `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, có thể cần `Access-Control-Allow-Credentials` | Server cho phép request thực tế được tiếp tục |
| Request thực tế | `Origin`; có thể có cookie khi credentials mode và cookie policy cho phép | Request thực hiện công việc thực tế |
| Response thực tế | `Access-Control-Allow-Origin`; `Access-Control-Allow-Credentials` khi cần | Browser quyết định có chia sẻ response cho JavaScript không |

**Preflight không phải cơ chế chống CSRF tổng quát.** Một số request đơn giản không cần preflight và có thể đến server dù response không được chia sẻ cho JavaScript. Hơn nữa, server không được coi việc có preflight là xác thực hoặc phân quyền.

## 7. Cache và `Vary: Origin`

Khi backend trả ACAO khác nhau tùy theo request `Origin`, response phụ thuộc header request đó. Cache trung gian (proxy/CDN) phải biết response có thể khác theo Origin:

```http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
```

Nếu thiếu `Vary: Origin`, một cache có thể lưu response dành cho frontend A rồi phục vụ nhầm cho frontend B, hoặc khiến ACAO không khớp. Kết quả thường là lỗi CORS hoặc, trong cấu hình sai nghiêm trọng, chia sẻ response không đúng chính sách dự kiến.

- **ACAO cố định `*`:** không cần `Vary: Origin` chỉ để phân biệt ACAO, vì giá trị không thay đổi theo Origin. Các yếu tố cache khác vẫn có thể cần Vary.
- **ACAO động từ allowlist:** dùng `Vary: Origin` vì header response thay đổi theo Origin được nhận.
- **Preflight cache HTTP:** nếu phản hồi OPTIONS được tạo khác nhau theo origin, method hoặc requested headers, cân nhắc thêm các header tương ứng vào `Vary`; browser còn có cache preflight riêng qua `Access-Control-Max-Age`.
- Khi thêm `Vary`, phải **gộp** giá trị hiện có (ví dụ `Accept-Encoding`), không ghi đè vô tình cấu hình cache của middleware khác.

## 8. Ví dụ cấu hình backend

### Ví dụ Java Spring MVC

Khi có hai frontend tin cậy và API cần cookie/session, cấu hình origin cụ thể:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                    .allowedOrigins(
                        "https://app.example.test",
                        "https://admin.example.test"
                    )
                    .allowedMethods("GET", "POST", "PUT", "DELETE")
                    .allowedHeaders("Content-Type", "X-CSRF-Token")
                    .allowCredentials(true)
                    .maxAge(600);
            }
        };
    }
}
```

Spring sẽ tạo response CORS dựa trên cấu hình; không cần tự phản chiếu `Origin` trong controller. Trong ứng dụng Spring Security, cần bảo đảm CORS được tích hợp đúng thứ tự trong security filter chain và request OPTIONS/preflight không bị chặn trước khi CORS xử lý. Cấu hình MVC ở trên là ví dụ nền tảng, không thay thế kiểm tra bảo mật API.

Nếu dữ liệu thật sự công khai và không dùng credentials, có thể cấu hình wildcard cho endpoint đó. Không dùng wildcard chỉ vì nó làm hết lỗi Console.

### Ví dụ Node.js thuần: allowlist và preflight

Đoạn dưới minh họa cách chọn một origin từ allowlist. Nó không phải server hoàn chỉnh cho production:

```js
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test"
]);

function appendVary(response, names) {
  const current = response.getHeader("Vary");
  const values = new Set(
    String(current || "")
      .split(",")
      .map(value => value.trim())
      .filter(Boolean)
  );
  for (const name of names) values.add(name);
  response.setHeader("Vary", [...values].join(", "));
}

function applyCors(request, response) {
  const origin = request.headers.origin;
  const allowed =
    typeof origin === "string" && allowedOrigins.has(origin);

  // Chính sách ACAO thay đổi theo Origin nên cache phải phân biệt.
  appendVary(response, ["Origin"]);

  if (allowed) {
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Access-Control-Allow-Credentials", "true");
  }

  const isPreflight =
    request.method === "OPTIONS" &&
    request.headers["access-control-request-method"];

  if (isPreflight) {
    appendVary(response, [
      "Access-Control-Request-Method",
      "Access-Control-Request-Headers"
    ]);

    if (!allowed) {
      response.writeHead(403);
      response.end();
      return true;
    }

    response.setHeader(
      "Access-Control-Allow-Methods",
      "GET, POST, PUT"
    );
    response.setHeader(
      "Access-Control-Allow-Headers",
      "Content-Type, X-CSRF-Token"
    );
    response.setHeader("Access-Control-Max-Age", "600");
    response.writeHead(204);
    response.end();
    return true;
  }

  return false; // Tiếp tục xử lý route; response route vẫn giữ ACAO nếu được phép.
}
```

Lưu ý:

- Gọi `applyCors` trước khi xử lý route để cả response lỗi phù hợp cũng có CORS header khi chính sách yêu cầu.
- Với request không được phép, không gửi ACAO. Server vẫn phải tự quyết định trả lỗi và không thực thi nghiệp vụ trái quyền.
- Production cần kiểm tra method/header thực tế, xử lý OPTIONS đúng, giới hạn origin theo môi trường, gộp `Vary` và bảo đảm các middleware/proxy không ghi đè ACAO.
- Không sao chép origin bất kỳ từ request; chỉ echo giá trị đã xác nhận trong allowlist.

## 9. CORS không thay thế xác thực, phân quyền hay CSRF

Đây là ranh giới quan trọng nhất khi thiết kế API.

| Cơ chế | Câu hỏi được trả lời | Không giải quyết thay |
| --- | --- | --- |
| **ACAO/CORS** | JavaScript từ origin nào được đọc response? | Đăng nhập, quyền nghiệp vụ, chống mọi request giả mạo |
| **SOP** | Script có được đọc/điều khiển dữ liệu cross-origin không? | Phân quyền API và CSRF |
| **Authentication** | Người gọi là ai? | Người đó có quyền với dữ liệu/hành động nào |
| **Authorization** | Người dùng có quyền làm hành động này trên tài nguyên này không? | Quyền đọc response của một origin khác |
| **CSRF defense** | Request dùng credential của nạn nhân có phải hành động được chủ ý cho phép không? | XSS và phân quyền nghiệp vụ |
| **Cookie SameSite/HttpOnly/Secure** | Khi nào cookie được gửi, ai có thể đọc cookie từ script, và cookie có yêu cầu HTTPS không? | Toàn bộ CORS hoặc xác thực/phân quyền |

Ví dụ một endpoint `POST /transfer` không được an toàn chỉ vì server không trả ACAO cho website tấn công. Request đơn giản có thể được gửi đến server; browser chỉ chặn script đọc response. Server phải:

1. Xác thực session/token.
2. Kiểm tra người dùng có quyền chuyển tiền từ tài khoản nguồn.
3. Kiểm tra CSRF token hoặc cơ chế chống CSRF thích hợp, kết hợp `Origin`/`Referer` và Fetch Metadata khi phù hợp.
4. Xác thực dữ liệu nghiệp vụ và giới hạn số tiền/người nhận.
5. Ghi nhận kết quả giao dịch và trả response theo chính sách CORS phù hợp.

**CORS không phải firewall và không phải authorization layer.** Một client ngoài trình duyệt (curl, server-to-server, script backend) có thể tự gửi request và không bị browser áp dụng CORS; server không được tin rằng mọi caller đều tuân thủ chính sách browser.

## 10. Kiểm thử ACAO bằng browser DevTools

Giả sử frontend `https://app.example.test` gọi API `https://api.example.test` trên môi trường thử nghiệm được phép:

### Kiểm tra request

1. Mở DevTools → **Network**, bật Preserve log nếu cần.
2. Gọi API bằng `fetch()` từ frontend.
3. Chọn request và xem **Request Headers**: `Origin` có đúng origin frontend không? Với preflight, xem thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
4. Nếu có OPTIONS, kiểm tra nó có được server/proxy trả lời trước khi request thực tế chạy hay không.

### Kiểm tra response

1. Xem **Response Headers** của OPTIONS: ACAO có đúng một origin và khớp request? Method/header được yêu cầu có nằm trong allowlist? Nếu credentials mode là `include`, có `Access-Control-Allow-Credentials: true` không?
2. Xem **Response Headers** của GET/POST/PUT thực tế: ACAO phải tiếp tục khớp; nếu có credentials, response thực tế cũng cần ACAC `true`.
3. Nếu server chọn origin động, kiểm tra `Vary: Origin`; xác minh CDN/proxy không cache response giữa hai origin.
4. Đọc Console để phân biệt lỗi preflight, ACAO không khớp, wildcard với credentials, header credentials thiếu hoặc lỗi mạng/TLS.

### Ma trận kiểm thử

| Ca kiểm thử | Cấu hình server | Kết quả mong đợi |
| --- | --- | --- |
| Frontend được allowlist | ACAO là origin chính xác | Browser có thể cho JS đọc response nếu các điều kiện khác đạt |
| Frontend không nằm trong allowlist | Không có ACAO | JS không đọc được response |
| Endpoint công khai | ACAO `*`, request không dùng credentials | JS có thể đọc response nếu các điều kiện khác đạt |
| Credentials include + wildcard | ACAO `*`, ACAC `true` | Browser từ chối chia sẻ response |
| Credentials include + origin cụ thể | ACAO khớp, ACAC `true` | Có thể đọc nếu cookie/policy và các kiểm tra khác đạt |
| Origin giả có hậu tố | Allowlist so sánh chính xác | Không được chấp nhận |
| Origin `null` | Không có ngoại lệ được phê duyệt | Không được chấp nhận |
| OPTIONS đúng nhưng GET thiếu ACAO | Chỉ preflight có CORS header | Request có thể được gửi, nhưng JS không đọc được response thực tế |
| ACAO động nhưng thiếu Vary | Cache response theo URL không phân biệt Origin | Có nguy cơ trả nhầm header/cache giữa các frontend |

**Không dùng Postman/curl làm bằng chứng CORS hoạt động.** Những công cụ đó không thực thi SOP/CORS như browser; chúng hữu ích để kiểm tra server có trả header gì, còn quyết định chia sẻ response phải kiểm tra bằng browser thật.

## 11. Lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gửi `Access-Control-Allow-Origin: https://app.example.test/` | Giá trị có slash cuối không khớp serialized origin | Gửi origin chính xác, không path/trailing slash |
| Gửi nhiều origin hoặc danh sách phân cách dấu phẩy | ACAO không hợp lệ | Chọn đúng một origin từ allowlist cho mỗi response |
| Dùng `*` cùng credentials mode `include` | Browser từ chối response | Trả origin cụ thể và ACAC `true` |
| Phản chiếu mọi `Origin` | Bất kỳ website nào cũng có thể được cấp quyền đọc response | Allowlist exact origin |
| Chỉ cấu hình CORS cho OPTIONS | Actual response thiếu ACAO/ACAC | Cấu hình cho cả preflight và response thực tế |
| Quên `Vary: Origin` khi ACAO động | Cache có thể phục vụ nhầm response | Thêm/gộp `Vary: Origin` |
| Allow `Origin: null` tùy tiện | Chia sẻ response cho nhiều opaque context không định danh | Không cho phép null trừ thiết kế đặc biệt đã đánh giá |
| Dùng CORS để chặn CSRF | Request có thể đến server và gây side effect | CSRF token, kiểm tra Origin/Fetch Metadata, SameSite và xác thực |
| Thêm CORS header vào controller nhưng proxy ghi đè | Duplicate hoặc ACAO mâu thuẫn | Xác định một nơi quản lý CORS và kiểm tra response cuối cùng |
| Dùng `mode: "no-cors"` để né CORS | Response trở thành opaque, JavaScript không đọc được nội dung | Cấu hình server/API chia sẻ đúng hoặc dùng backend proxy được bảo vệ |

## 12. Câu hỏi củng cố

**Câu 1.** Request từ `https://app.example.test` nhận `Access-Control-Allow-Origin: https://app.example.test/`. Vì sao vẫn lỗi?

**Giải đáp:** ACAO phải khớp serialized origin; dấu gạch chéo cuối không thuộc origin và không được thêm vào.

**Câu 2.** Vì sao `Access-Control-Allow-Origin: *` không hợp lệ khi frontend dùng `credentials: "include"`?

**Giải đáp:** CORS không cho wildcard ACAO trong credentials mode `include`. Server phải trả origin cụ thể khớp request và `Access-Control-Allow-Credentials: true`.

**Câu 3.** Server có hai frontend hợp lệ. Có thể gửi hai dòng ACAO trong một response để cho phép cả hai không?

**Giải đáp:** Không. Server phải xác định origin request có trong allowlist rồi trả đúng **một** origin cho response đó; nếu ACAO thay đổi theo request thì thêm `Vary: Origin`.

**Câu 4.** Tại sao không nên cho phép `Origin: null` chỉ để ứng dụng sandboxed iframe chạy được?

**Giải đáp:** `null` là dạng tuần tự hóa của nhiều opaque origin khác nhau, không đại diện cho một ứng dụng tin cậy duy nhất. Hãy thiết kế origin HTTPS riêng hoặc đánh giá một giao thức đặc biệt an toàn.

**Câu 5.** Preflight OPTIONS thành công nhưng JavaScript vẫn báo CORS sau PUT. Cần kiểm tra đâu?

**Giải đáp:** Kiểm tra **response PUT thực tế** có ACAO khớp và ACAC `true` khi dùng credentials hay không; không chỉ kiểm tra OPTIONS.

**Câu 6.** CORS chặn JavaScript đọc response có đồng nghĩa request không được server thực hiện không?

**Giải đáp:** Không. Request đơn giản có thể được gửi và server có thể xử lý. CORS chủ yếu quyết định quyền chia sẻ response với script; server vẫn phải chống CSRF và kiểm tra quyền.

## 13. Tổng kết

**`Access-Control-Allow-Origin`** là response header cốt lõi của CORS: server trả `*` cho dữ liệu công khai không dùng credentials, hoặc trả **một serialized origin cụ thể** khi muốn giới hạn frontend. Khi credentials mode là `include`, wildcard không hợp lệ; server cần origin cụ thể khớp request và `Access-Control-Allow-Credentials: true`. Với allowlist động, phải kiểm tra origin chính xác và dùng `Vary: Origin` để cache không trộn phản hồi.

Hãy nhớ: ACAO **không xác thực, không phân quyền và không chống CSRF**. Kiểm tra response cuối cùng trong browser, cấu hình cả preflight lẫn actual response, và giữ trách nhiệm bảo vệ dữ liệu ở backend.

## Tài liệu tham khảo

1. [Fetch Standard — CORS protocol and credentials](https://fetch.spec.whatwg.org/#http-cors-protocol): thuật toán CORS, ACAO, credentials và serialized origin.
2. [Fetch Standard — CORS check](https://fetch.spec.whatwg.org/#cors-check): cách browser đối chiếu ACAO và ACAC.
3. [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): cú pháp, wildcard, origin cụ thể và Vary.
4. [MDN — Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials): điều kiện chia sẻ response có credentials.
5. [MDN — CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple request, preflight và response CORS.
6. [MDN — Origin header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): ý nghĩa của Origin request header.
7. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): phân biệt CORS và phòng vệ CSRF ở server.
