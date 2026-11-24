# frame-ancestors: ngăn website không tin cậy nhúng trang của bạn

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cách tấn công clickjacking lợi dụng việc nhúng trang vào iframe để lừa người dùng thao tác.
2. Cấu hình CSP directive **frame-ancestors** để giới hạn ancestor nào được phép nhúng một tài liệu.
3. Phân biệt frame-ancestors với frame-src, default-src, X-Frame-Options, iframe sandbox và CORS.
4. Hiểu vì sao mọi ancestor trong chuỗi frame lồng nhau đều phải được cho phép.
5. Chọn allowlist theo scheme, host và port; tránh wildcard hoặc cho phép mọi website.
6. Triển khai bằng HTTP response header, kiểm thử trên môi trường staging và đọc lỗi bằng Chrome DevTools.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web, đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. frame-ancestors là cơ chế chống clickjacking ở phía tài liệu được nhúng: nó xác định website nào được phép làm ancestor của trang hiện tại.

## 1. Clickjacking hoạt động như thế nào?

Clickjacking (UI redressing) là kiểu tấn công khiến người dùng tưởng họ đang nhấn vào một thành phần giao diện, trong khi thao tác thực tế được chuyển tới một trang khác được đặt chồng hoặc căn chỉnh bên dưới/trên giao diện giả.

Một kịch bản thường gặp:

1. Nạn nhân đăng nhập vào **https://account.example.test**; browser giữ session cookie.
2. Người dùng mở website do kẻ tấn công kiểm soát, ví dụ **https://promo.attacker.test**.
3. Trang attacker nhúng trang tài khoản vào iframe, rồi căn chỉnh hoặc làm trong suốt iframe để nút nhạy cảm nằm dưới vị trí người dùng định nhấn.
4. Người dùng tưởng mình đang nhấn nút nhận quà, nhưng thực tế nhấn nút thay đổi email, cấp quyền hoặc xác nhận thao tác trong trang tài khoản.

Minh họa cấu trúc:

```text
Trang do attacker kiểm soát
┌──────────────────────────────────────────┐
│  "Nhấn để nhận quà"                      │
│                                          │
│  [nội dung dụ nhấp / lớp phủ giao diện]   │
│       ┌──────────────────────────┐       │
│       │ iframe trang tài khoản   │       │
│       │ [nút xác nhận nhạy cảm]   │       │
│       └──────────────────────────┘       │
└──────────────────────────────────────────┘
```

Browser có thể gửi cookie của trang được nhúng nếu cookie và chính sách browser cho phép. Kẻ tấn công không nhất thiết phải đọc DOM hoặc response của iframe; mục tiêu là khiến người dùng thực hiện thao tác trong giao diện đã đăng nhập.

### Vì sao Same-Origin Policy không đủ?

Same-Origin Policy (SOP) hạn chế script ở một origin đọc dữ liệu/DOM của origin khác. Nhưng SOP không mặc định cấm một trang hiển thị tài liệu cross-origin trong iframe. Vì vậy, trang attacker có thể không đọc được nội dung iframe nhưng vẫn đặt iframe vào giao diện để lừa người dùng nhấp.

Đây là lý do cần cơ chế riêng để kiểm soát **ai được phép nhúng trang**.

## 2. frame-ancestors là gì?

**frame-ancestors** là CSP directive được gửi trong response của **tài liệu muốn bảo vệ**. Nó khai báo những nguồn ancestor được phép nhúng tài liệu đó qua các ngữ cảnh frame.

Directive này kiểm soát việc nhúng tài liệu qua các phần tử như frame, iframe, object, embed và applet. Phạm vi cụ thể của từng loại nội dung còn chịu các directive CSP khác, chẳng hạn object-src.

Ví dụ, trang tài khoản không muốn bị nhúng ở bất kỳ website nào:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Nếu sản phẩm chỉ cho phép portal nội bộ nhúng trang:

```http
Content-Security-Policy: frame-ancestors https://portal.example.test
```

Nếu trang có thể được mở trực tiếp hoặc nhúng trong cùng origin:

```http
Content-Security-Policy: frame-ancestors 'self'
```

frame-ancestors kiểm tra nguồn của các ancestor trong cây browsing context. Nếu có một ancestor không khớp source list, browser chặn việc hiển thị tài liệu trong frame.

### Đặt policy ở response của child

Giả sử:

- Parent: **https://portal.example.test**
- Child: **https://account.example.test**
- Attacker: **https://attacker.test**

Response của **account.example.test** mới là nơi khai báo ai được phép nhúng trang tài khoản:

```http
# Response từ https://account.example.test/profile
Content-Security-Policy: frame-ancestors https://portal.example.test
```

Portal được phép nhúng trang tài khoản. Website attacker không được phép.

Nếu bạn đặt frame-ancestors trong response của portal, policy đó chỉ kiểm soát ai được phép nhúng chính portal. Nó không quyết định portal được nhúng account hay không.

## 3. Cú pháp và source expression

Cú pháp tổng quát:

```http
Content-Security-Policy: frame-ancestors <source-list>
```

Các source expression thường dùng:

| Source expression | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| 'none' | Không cho bất kỳ ancestor nào nhúng tài liệu | Trang tài khoản, admin hoặc trang nhạy cảm không cần embed |
| 'self' | Chỉ cho ancestor cùng origin | Ứng dụng chỉ nhúng trang trong cùng origin |
| https://portal.example.test | Cho phép origin portal qua HTTPS | Một parent cụ thể được tin cậy |
| https://*.partner.test | Cho phép host phù hợp dưới wildcard domain | Chỉ khi mọi subdomain phù hợp đều thuộc ranh giới tin cậy |
| https: | Cho phép ancestor dùng HTTPS trên nhiều host | Rất rộng; thường không phù hợp với trang nhạy cảm |

Keyword 'self' và 'none' phải có dấu nháy đơn. Scheme/host source không đặt trong dấu nháy.

### 'none' nên dùng riêng

Nếu không muốn bất kỳ website nào nhúng trang, khai báo:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Không ghép 'none' với một allowlist và kỳ vọng nó hoạt động như deny rule:

```http
# Không diễn đạt ý định "chặn tất cả trừ portal"
Content-Security-Policy: frame-ancestors 'none' https://portal.example.test
```

Hãy khai báo chính xác source list muốn cho phép:

```http
Content-Security-Policy: frame-ancestors https://portal.example.test
```

Không dùng 'none' như một deny-list đứng cạnh allowlist.

### So khớp origin chính xác

Origin bao gồm scheme, host và port có hiệu lực. Những nguồn sau không tương đương:

| Source được khai báo | Ancestor thực tế | Có khớp? |
| --- | --- | --- |
| https://portal.example.test | https://portal.example.test | Có |
| https://portal.example.test | http://portal.example.test | Không, scheme khác |
| https://portal.example.test | https://portal.example.test:8443 | Không, port khác |
| https://portal.example.test | https://admin.example.test | Không, host khác |
| https://portal.example.test | https://portal.example.test.attacker.test | Không, host khác |

Không dùng wildcard scheme/host chỉ để tránh lỗi cấu hình. Mỗi origin được cho phép cần có chủ sở hữu và mục đích nhúng rõ ràng.

## 4. Mọi ancestor trong chuỗi frame đều phải được phép

Một trang có thể được nhúng lồng nhiều lớp:

```text
https://wrapper.example.test
        |
        v
https://portal.example.test
        |
        v
https://account.example.test
```

Khi account.example.test trả:

```http
Content-Security-Policy: frame-ancestors https://portal.example.test
```

browser kiểm tra toàn bộ chuỗi ancestor của tài liệu account. Portal khớp, nhưng wrapper không khớp. Vì vậy việc nhúng vẫn bị chặn.

Nếu ứng dụng thật sự cần hỗ trợ chuỗi lồng nhiều tầng, phải liệt kê mọi origin ancestor hợp lệ:

```http
Content-Security-Policy: frame-ancestors https://portal.example.test https://wrapper.example.test
```

Chỉ thêm wrapper nếu đã xác minh luồng sản phẩm cần thiết và website đó thuộc ranh giới tin cậy. Không thêm một origin rộng chỉ vì một tích hợp hiện tại bị lỗi.

### frame-ancestors không phải danh sách parent trực tiếp

Tên directive có chữ "ancestors" vì browser xét tất cả tổ tiên, không chỉ iframe cha trực tiếp. Khi debug, cần kiểm tra cả lớp wrapper, portal, shell hoặc trang host do nền tảng tích hợp tạo ra.

## 5. Phân biệt frame-ancestors với frame-src và các cơ chế liên quan

Hai directive thường bị nhầm:

| Directive | Đặt trong response của | Kiểm soát |
| --- | --- | --- |
| frame-ancestors | Child/tài liệu được nhúng | Ai được phép nhúng tài liệu hiện tại? |
| frame-src | Parent/tài liệu chứa frame | Tài liệu hiện tại được phép tải frame từ nguồn nào? |
| default-src | Tài liệu hiện tại | Fallback cho nhiều loại tài nguyên khi directive cụ thể thiếu |
| object-src | Tài liệu hiện tại | Nguồn cho nội dung qua object/embed |
| form-action | Tài liệu hiện tại | Đích mà form được phép submit |

### frame-ancestors không fallback sang default-src

Đây là điểm rất quan trọng:

```http
# default-src không thay thế frame-ancestors
Content-Security-Policy: default-src 'none'
```

Policy trên **không tự cấm website khác nhúng tài liệu**. Nếu muốn cấm embedding, phải khai báo rõ:

```http
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
```

Khi frame-ancestors không có mặt, directive này không tạo ra giới hạn ancestor. Không suy luận rằng default-src 'none' đã chống clickjacking.

### CORS không thay frame-ancestors

CORS quyết định JavaScript cross-origin có thể đọc response hay không. frame-ancestors quyết định website nào được phép nhúng tài liệu. Một trang có thể bị SOP ngăn parent đọc DOM nhưng vẫn được hiển thị trong iframe nếu child cho phép.

### iframe sandbox không thay frame-ancestors

Thuộc tính sandbox trên iframe giới hạn một số khả năng của nội dung bên trong như script, form, popup hoặc top navigation tùy token được cấp. Nó không quyết định website nào được phép nhúng trang của bạn. frame-ancestors mới là chính sách ở response child để giới hạn ancestor.

## 6. frame-ancestors và X-Frame-Options

Trước CSP, nhiều ứng dụng dùng header:

```http
X-Frame-Options: DENY
```

hoặc:

```http
X-Frame-Options: SAMEORIGIN
```

| Header | Giá trị | Ý nghĩa |
| --- | --- | --- |
| X-Frame-Options | DENY | Không cho trang được hiển thị trong frame |
| X-Frame-Options | SAMEORIGIN | Chỉ cho phép nhúng cùng origin theo cơ chế XFO |
| CSP frame-ancestors | 'none' | Không cho ancestor nào nhúng |
| CSP frame-ancestors | 'self' | Chỉ cho ancestor cùng origin |
| CSP frame-ancestors | Danh sách origin | Cho phép nhiều origin cụ thể |

X-Frame-Options ALLOW-FROM đã lỗi thời và không được hỗ trợ nhất quán. Khi cần allowlist nhiều parent, dùng CSP frame-ancestors.

### Có nên gửi cả hai header?

CSP frame-ancestors là cơ chế hiện đại và được browser hỗ trợ sẽ quyết định chính sách framing; X-Frame-Options có thể được giữ như lớp tương thích cho browser cũ. Tránh cấu hình hai header mâu thuẫn vì hành vi ở browser cũ có thể khác nhau.

Ví dụ một ứng dụng không cho nhúng:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Nếu ứng dụng cho phép một portal bên ngoài nhúng, XFO SAMEORIGIN không thể biểu đạt allowlist portal đó. Trong trường hợp này, xác định rõ browser mục tiêu và chỉ giữ XFO nếu giá trị của nó không phá vỡ luồng tương thích cần hỗ trợ.

## 7. Chọn policy theo nhu cầu ứng dụng

| Loại trang | Policy thường phù hợp | Lý do |
| --- | --- | --- |
| Admin console | frame-ancestors 'none' | Không có nhu cầu nhúng; giảm clickjacking |
| Trang tài khoản/ngân hàng | frame-ancestors 'none' | Thao tác nhạy cảm không nên xuất hiện trong frame ngoài |
| Ứng dụng nội bộ có trang shell cùng origin | frame-ancestors 'self' | Chỉ cho thành phần cùng origin nhúng |
| Widget được nhúng bởi một portal | frame-ancestors https://portal.example.test | Chỉ cấp quyền cho parent đã xác minh |
| Widget đối tác có nhiều portal | Liệt kê từng origin HTTPS cụ thể | Có thể kiểm soát và rà soát từng tích hợp |

### Không cho phép mọi HTTPS ancestor

Policy:

```http
Content-Security-Policy: frame-ancestors https:
```

cho phép rất nhiều website HTTPS nhúng trang. Kẻ tấn công cũng có thể vận hành website HTTPS. Scheme HTTPS chỉ nói về giao thức kết nối, không chứng minh website đó đáng tin.

### Cẩn thận với wildcard subdomain

Policy:

```http
Content-Security-Policy: frame-ancestors https://*.example.test
```

có thể bao phủ nhiều subdomain, gồm staging, preview, user-content hoặc host cũ. Nếu một subdomain có nội dung do người dùng kiểm soát hoặc bị chiếm quyền, việc cho phép toàn bộ wildcard có thể mở rộng ranh giới tin cậy.

Ưu tiên liệt kê chính xác từng origin:

```http
Content-Security-Policy: frame-ancestors https://portal.example.test https://embed.example.test
```

Nếu phải dùng wildcard, cần kiểm kê mọi host phù hợp, chủ sở hữu, quy trình cấp subdomain và cơ chế thu hồi.

## 8. Triển khai qua HTTP response header

frame-ancestors phải được gửi bằng HTTP response header. Directive này không có hiệu lực khi đặt trong meta http-equiv Content-Security-Policy; nó cũng không được hỗ trợ trong Content-Security-Policy-Report-Only.

### Nginx

Không cho phép nhúng:

```nginx
add_header Content-Security-Policy "frame-ancestors 'none'; object-src 'none'; base-uri 'self'" always;
add_header X-Frame-Options "DENY" always;
```

Cho phép một portal cụ thể:

```nginx
add_header Content-Security-Policy "frame-ancestors https://portal.example.test; object-src 'none'; base-uri 'self'" always;
```

Lưu ý:

- always giúp header xuất hiện trên nhiều response status hơn.
- Kiểm tra quy tắc kế thừa add_header giữa server và location.
- Tránh CDN, proxy và ứng dụng cùng thêm những CSP header mâu thuẫn.
- Xác minh response cuối cùng từ browser, không chỉ đọc file cấu hình.

### Node.js / Express

```js
app.use((req, res, next) => {
  res.setHeader(
    "Content-Security-Policy",
    [
      "default-src 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'"
    ].join("; ")
  );
  res.setHeader("X-Frame-Options", "DENY");
  next();
});
```

Nếu một số route cần được portal nhúng, cấu hình policy riêng theo route và allowlist được quản trị ở server. Không lấy origin cho phép từ query parameter hoặc header do request tự khai báo.

### Java / Spring Security

Ví dụ cấu hình Spring Security hiện đại:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "frame-ancestors 'none'; " +
            "object-src 'none'; " +
            "base-uri 'self'"
        )
    )
);
```

Nếu cần portal nhúng:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "frame-ancestors https://portal.example.test; " +
            "object-src 'none'; base-uri 'self'"
        )
    )
);
```

API cấu hình có thể khác nhẹ theo phiên bản Spring Security. Đảm bảo header áp dụng cho đúng response của child page và không bị filter/proxy khác ghi đè.

### Vì sao meta tag không dùng được?

Ví dụ sau không bảo vệ trang khỏi bị nhúng:

```html
<meta
  http-equiv="Content-Security-Policy"
  content="frame-ancestors 'none'">
```

Browser chỉ áp dụng frame-ancestors từ HTTP response header. Đặt directive trong meta tag không tạo ra cơ chế chống clickjacking.

### Vì sao Report-Only không dùng được cho frame-ancestors?

Không thể dựa vào:

```http
Content-Security-Policy-Report-Only: frame-ancestors 'none'
```

để quan sát trước khi enforce. frame-ancestors không được hỗ trợ trong Content-Security-Policy-Report-Only, nên không có chế độ report-only tương đương cho directive này.

Thay vào đó:

1. Kiểm kê các parent hợp lệ theo tài liệu tích hợp và cấu hình sản phẩm.
2. Triển khai trên staging hoặc route canary với browser test tự động.
3. Kiểm tra các luồng nhúng thực tế từ mọi portal được cho phép.
4. Bật policy enforce ở production theo kế hoạch rollout và theo dõi lỗi từ ứng dụng.

## 9. Kiểm thử bằng Chrome DevTools với hai origin local

Lab dùng hai port khác nhau để tạo hai origin:

- Parent: **http://localhost:8080**
- Child: **http://localhost:8081**

Hai URL này khác origin vì port khác nhau. Child sẽ cho phép parent cụ thể nhúng nó.

### Tạo file lab

Tạo file **frame-ancestors-lab.mjs**:

```js
import http from "node:http";

const parentHtml = [
  "<!doctype html>",
  '<html lang="vi">',
  '<meta charset="utf-8">',
  "<title>Parent frame lab</title>",
  "<h1>Parent: localhost:8080</h1>",
  '<iframe title="Child" src="http://localhost:8081/child" width="640" height="220"></iframe>',
  "</html>"
].join("\n");

const childHtml = [
  "<!doctype html>",
  '<html lang="vi">',
  '<meta charset="utf-8">',
  "<title>Child frame lab</title>",
  "<h2>Child: localhost:8081</h2>",
  "<p>Nếu bạn thấy dòng này, ancestor policy đã cho phép parent.</p>",
  "</html>"
].join("\n");

const parentServer = http.createServer((request, response) => {
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; frame-src http://localhost:8081; object-src 'none'"
  );
  response.end(parentHtml);
});

const childServer = http.createServer((request, response) => {
  const path = new URL(request.url, "http://localhost:8081").pathname;
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");

  if (path !== "/child") {
    response.writeHead(404);
    response.end("Not found");
    return;
  }

  // Cho phép đúng parent origin ở port 8080.
  response.setHeader(
    "Content-Security-Policy",
    "frame-ancestors http://localhost:8080"
  );
  response.end(childHtml);
});

parentServer.listen(8080, "127.0.0.1", () => {
  console.log("Parent: http://localhost:8080/");
});

childServer.listen(8081, "127.0.0.1", () => {
  console.log("Child:  http://localhost:8081/child");
});
```

Chạy **node frame-ancestors-lab.mjs**, sau đó mở **http://localhost:8080/**. Parent có frame-src cho phép port 8081, còn child có frame-ancestors cho phép port 8080. Hai phía đều cho phép nên iframe hiển thị.

### Thí nghiệm A — Cho phép parent chính xác

1. Mở DevTools → Network và bật Preserve log.
2. Tải **http://localhost:8080/**.
3. Chọn request /child ở port 8081.
4. Trong Response Headers, xác nhận **Content-Security-Policy: frame-ancestors http://localhost:8080**.
5. Xác nhận iframe hiển thị.

### Thí nghiệm B — Chặn parent

Đổi header response child thành:

```js
response.setHeader(
  "Content-Security-Policy",
  "frame-ancestors 'self'"
);
```

Tải lại parent. Child ở port 8081 chỉ chấp nhận ancestor cùng origin của nó; parent port 8080 khác origin nên browser chặn việc nhúng. Console hiển thị vi phạm frame-ancestors.

### Thí nghiệm C — Thử ancestor lồng nhiều tầng

Tạo thêm một wrapper ở origin/port khác, rồi đặt portal vào iframe của wrapper và account vào iframe của portal. Chỉ cho phép portal trong child policy; xác nhận wrapper không được phép sẽ khiến toàn bộ lần nhúng thất bại. Sau đó thêm wrapper vào allowlist chỉ để quan sát khác biệt, rồi bỏ cấu hình thử nghiệm.

### Thí nghiệm D — Kiểm tra meta và Report-Only

1. Xóa header frame-ancestors ở child.
2. Thử thêm meta tag frame-ancestors 'none'; xác nhận nó không chặn parent.
3. Thử đưa directive vào Content-Security-Policy-Report-Only; xác nhận đây không phải cách kiểm thử report-only hợp lệ cho frame-ancestors.
4. Khôi phục HTTP response header enforce sau lab.

### Ma trận kiểm thử

| Ca kiểm thử | Child response policy | Ancestor | Kết quả mong đợi |
| --- | --- | --- | --- |
| Parent được cho phép | frame-ancestors http://localhost:8080 | http://localhost:8080 | Cho phép |
| Parent sai port | frame-ancestors http://localhost:8080 | http://localhost:8082 | Chặn |
| Chỉ cùng origin | frame-ancestors 'self' | Origin khác | Chặn |
| Cấm tất cả | frame-ancestors 'none' | Bất kỳ origin nào | Chặn |
| Nested wrapper không được phép | Chỉ cho portal | Wrapper + portal | Chặn vì có ancestor không khớp |
| Chỉ có default-src | default-src 'none' | Origin khác | frame-ancestors không tạo giới hạn; kiểm tra directive khác riêng |
| Chỉ có meta frame-ancestors | Không có header | Origin khác | Meta không bảo vệ framing |

## 10. Đọc lỗi và xử lý sự cố

Khi browser chặn một lần nhúng, kiểm tra response của **tài liệu child**:

1. Mở Network và chọn request document trong iframe.
2. Xem Response Headers, tìm tất cả Content-Security-Policy header.
3. Kiểm tra source list của frame-ancestors.
4. Xác định origin của từng ancestor trong chuỗi frame, gồm wrapper và portal.
5. So sánh scheme, host và port; không chỉ nhìn hostname.
6. Kiểm tra X-Frame-Options, redirect, response cuối cùng và header do CDN/proxy thêm.

Nếu response có nhiều Content-Security-Policy header, browser thực thi tất cả policy cùng lúc; một policy bổ sung có thể tiếp tục chặn ancestor mà policy còn lại cho phép. Vì vậy, hãy kiểm tra toàn bộ header chứ không chỉ tìm directive đầu tiên.

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Console báo frame-ancestors | Parent hoặc ancestor không nằm trong allowlist | Kiểm tra toàn bộ ancestor chain |
| Parent trực tiếp được phép nhưng vẫn bị chặn | Có wrapper ancestor không được phép | Kiểm tra cấu trúc frame lồng nhau |
| CSP trông đúng nhưng vẫn bị chặn | Có CSP header thứ hai hạn chế hơn | Xem tất cả response headers |
| Chỉ lỗi trên production | CDN/proxy thêm CSP hoặc origin production khác | So sánh response cuối giữa môi trường |
| Thêm meta nhưng không có tác dụng | frame-ancestors không có hiệu lực trong meta | Đưa directive vào HTTP response header |
| Report-Only không báo cáo | frame-ancestors không hỗ trợ Report-Only | Dùng staging/canary và test browser |
| Browser cũ xử lý khác | Khác biệt hỗ trợ CSP/XFO | Kiểm thử browser matrix, cân nhắc XFO tương thích |

## 11. Giới hạn của frame-ancestors

frame-ancestors là lớp bảo vệ quan trọng, nhưng không thay thế toàn bộ bảo mật giao diện:

- Không ngăn trang bị mở trực tiếp ở top-level.
- Không ngăn phishing hoặc social engineering diễn ra ngoài iframe.
- Không ngăn XSS trong chính origin được phép nhúng.
- Không thay CSRF token, SameSite cookie, authentication hoặc authorization.
- Không bảo vệ nếu allowlist chứa một parent bị chiếm quyền hoặc có nội dung không tin cậy.
- Không thay iframe sandbox khi cần hạn chế quyền của nội dung child.

Nếu một portal được cho phép nhúng trang, hãy xem portal đó là một phần của ranh giới tin cậy. Kiểm soát XSS, nội dung do người dùng tạo và quyền quản trị ở portal đó. Một parent được phép nhưng bị XSS vẫn có thể tạo giao diện lừa người dùng.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt frame-ancestors ở parent | Không bảo vệ child khỏi website khác nhúng | Đặt header trên response của tài liệu cần bảo vệ |
| Dùng frame-src để cấm người khác nhúng trang | Chỉ giới hạn nguồn child mà trang tự tải | Dùng frame-ancestors |
| Nghĩ default-src 'none' đã chặn framing | default-src không phải fallback của frame-ancestors | Khai báo frame-ancestors tường minh |
| Chỉ cho phép parent trực tiếp | Wrapper ancestor vẫn có thể không được phép | Kiểm tra toàn bộ ancestor chain |
| Cho phép https: | Website HTTPS bất kỳ có thể nhúng | Allowlist origin cụ thể |
| Cho phép wildcard subdomain rộng | Tin cậy staging/user-content ngoài ý muốn | Liệt kê từng origin cần thiết |
| Đặt directive trong meta tag | Browser bỏ qua frame-ancestors ở meta | Dùng HTTP response header |
| Dùng Content-Security-Policy-Report-Only | Directive không được hỗ trợ trong Report-Only | Kiểm thử enforce ở staging/canary |
| Chỉ dựa vào X-Frame-Options ALLOW-FROM | Giá trị lỗi thời, hỗ trợ không nhất quán | Dùng CSP frame-ancestors |
| Cho rằng CORS ngăn clickjacking | CORS kiểm soát đọc response, không phải quyền nhúng | Kết hợp frame-ancestors với các lớp khác |
| Cho rằng frame-ancestors chống XSS | Parent được phép vẫn có thể bị XSS | Phòng XSS ở tất cả origin được tin cậy |

## 13. Câu hỏi củng cố

**Câu 1.** Trang account trả frame-ancestors 'none'. Website attacker có thể nhúng account vào iframe không?

**Giải đáp:** Không. Browser chặn tài liệu account được nhúng bởi mọi ancestor, kể cả website cùng origin.

**Câu 2.** Vì sao frame-ancestors phải được gửi từ response của trang child?

**Giải đáp:** Chính tài liệu được nhúng quyết định những ancestor nào được phép hiển thị nó. Header trên parent kiểm soát chính parent khi nó bị nhúng, không quyết định child nào được tải.

**Câu 3.** Nếu portal được cho phép nhưng wrapper của portal không được phép thì sao?

**Giải đáp:** Browser vẫn chặn. Mọi ancestor trong chuỗi frame phải khớp source list.

**Câu 4.** default-src 'none' có thay thế frame-ancestors 'none' không?

**Giải đáp:** Không. frame-ancestors không có fallback sang default-src; phải khai báo riêng.

**Câu 5.** frame-ancestors có thể đặt trong meta tag hoặc Report-Only không?

**Giải đáp:** Không. Directive này cần HTTP response header và không được hỗ trợ trong Content-Security-Policy-Report-Only.

**Câu 6.** frame-ancestors có thay CORS không?

**Giải đáp:** Không. frame-ancestors kiểm soát quyền nhúng tài liệu; CORS kiểm soát quyền script đọc response cross-origin.

## 14. Tổng kết

**frame-ancestors** bảo vệ tài liệu khỏi clickjacking bằng cách giới hạn website nào được phép nhúng nó. Hãy đặt directive trên HTTP response của child, bắt đầu bằng 'none' nếu không cần embedding hoặc 'self' nếu chỉ cần cùng origin. Khi cần portal đối tác, liệt kê chính xác từng origin và nhớ browser kiểm tra toàn bộ ancestor chain.

frame-ancestors không fallback sang default-src, không có hiệu lực trong meta hoặc Report-Only, và không thay frame-src, CORS, X-Frame-Options, sandbox, CSRF hay phòng XSS. Kiểm thử trên staging với các chuỗi frame thực tế, xác minh response header cuối cùng và chỉ cấp quyền nhúng cho parent thuộc ranh giới tin cậy.

## Tài liệu tham khảo

1. [W3C — Content Security Policy Level 3: frame-ancestors](https://www.w3.org/TR/CSP3/#directive-frame-ancestors): định nghĩa, source list và kiểm tra ancestor.
2. [MDN — CSP frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors): cú pháp, ví dụ và giới hạn triển khai.
3. [MDN — X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options): cơ chế tương thích cũ để hạn chế framing.
4. [OWASP — Clickjacking Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html): threat model và các lớp phòng clickjacking.
5. [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): triển khai CSP và kiểm tra response header.
6. [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): cách gửi CSP bằng HTTP response header.
