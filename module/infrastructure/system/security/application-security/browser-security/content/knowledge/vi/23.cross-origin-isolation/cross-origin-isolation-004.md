# CORP: kiểm soát tài nguyên được nhúng từ origin khác

## 1. CORP là gì?

**Cross-Origin-Resource-Policy (CORP)** là một HTTP response header cho phép máy chủ sở hữu tài nguyên quy định tài liệu ở phạm vi nào được phép nhúng tài nguyên đó thông qua các request kiểu `no-cors`. Header này thường được dùng để bảo vệ tài nguyên khỏi việc bị nhúng ngoài dự kiến và hỗ trợ triển khai **cross-origin isolation**.

Một ví dụ đơn giản: website `https://app.example.com` cung cấp ảnh riêng tư tại `https://app.example.com/private/avatar.svg`. Nếu một website khác nhúng ảnh đó bằng thẻ `img`, browser có thể tải ảnh theo chế độ no-cors. JavaScript của website nhúng thường không đọc được response, nhưng tài nguyên vẫn có thể được sử dụng trong một số ngữ cảnh. Chủ sở hữu tài nguyên có thể trả về:

```http
Cross-Origin-Resource-Policy: same-origin
```

Browser sẽ từ chối việc nhúng tài nguyên qua request no-cors nếu requester không cùng origin với tài nguyên.

CORP có ba giá trị chính:

- `same-origin`: chỉ cho phép tài liệu cùng origin sử dụng tài nguyên theo cơ chế CORP.
- `same-site`: cho phép tài liệu cùng site, kể cả subdomain khác origin, theo quy tắc schemeful same-site của browser.
- `cross-origin`: cho phép tài liệu từ mọi origin sử dụng tài nguyên trong ngữ cảnh được CORP kiểm soát.

Nếu response không có CORP header, CORP không đặt thêm hạn chế. Những cơ chế khác như CORS, CSP, COEP, cookie policy và quy tắc tải tài nguyên của browser vẫn có thể áp dụng.

**Nguyên tắc:** CORP là chính sách do máy chủ tài nguyên công bố để kiểm soát việc nhúng cross-origin qua no-cors. Nó không cấp quyền cho JavaScript đọc response, không thay thế CORS và không thay thế xác thực/phân quyền ở server.

Bài viết thuộc chương **Cross-origin isolation** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Chủ đề kết nối CORP với SOP, CORS, COEP, COOP, CORB/ORB, XSS và cách browser cô lập tài nguyên giữa các origin.

Sau bài học, bạn có thể:

- Giải thích vai trò và vị trí của header Cross-Origin-Resource-Policy.
- Phân biệt same-origin, same-site và cross-origin.
- Phân biệt CORP với CORS và hiểu request mode no-cors.
- Hiểu quan hệ giữa CORP, CORB/ORB, COEP và COOP.
- Chọn policy phù hợp cho API, ảnh, script, font và tài nguyên CDN.
- Chẩn đoán lỗi CORP trong DevTools và response header.
- Triển khai header trong Node/Express hoặc Nginx.
- Thực hành kiểm chứng same-origin, same-site và cross-origin bằng hai local server.

## 2. Origin và site là hai khái niệm khác nhau

CORP có giá trị `same-origin` và `same-site`. Hai khái niệm này không đồng nghĩa.

### 2.1. Origin

Origin thông thường được xác định bởi bộ ba:

- Scheme: `https` hoặc `http`.
- Host: hostname hoặc địa chỉ IP.
- Port: cổng hiệu lực.

Ví dụ, các URL sau khác origin:

```text
https://app.example.com
https://static.example.com
https://app.example.com:8443
http://app.example.com
```

Khác path không làm thay đổi origin. Nhưng khác subdomain, port hoặc scheme sẽ tạo origin khác.

### 2.2. Site và schemeful same-site

Khái niệm site thường dựa trên scheme và registrable domain (eTLD+1), theo Public Suffix List. Port không tham gia vào site. Vì vậy:

| URL A | URL B | Quan hệ thường gặp |
|---|---|---|
| `https://app.example.com` | `https://static.example.com` | Khác origin, cùng site |
| `https://app.example.com` | `https://app.example.com:8443` | Khác origin, cùng site |
| `https://app.example.com` | `http://app.example.com` | Khác origin và khác schemeful site |
| `https://example.com` | `https://other.example.net` | Khác origin, khác site |

Browser hiện đại sử dụng khái niệm **schemeful same-site** trong các chính sách web liên quan: scheme cũng được tính. Vì vậy, không nên giả định HTTP và HTTPS trên cùng hostname là same-site.

Địa chỉ IP, localhost và public suffix có quy tắc đặc biệt khi xác định registrable domain. Khi cần kết quả chính xác, hãy kiểm tra bằng browser mục tiêu thay vì suy luận từ chuỗi hostname.

### 2.3. Vì sao same-site yếu hơn same-origin?

Hai subdomain cùng site có thể do các nhóm hoặc hệ thống khác nhau vận hành. Ví dụ:

- `app.example.com` chứa dữ liệu tài khoản.
- `uploads.example.com` nhận nội dung người dùng tải lên.
- `marketing.example.com` chạy hệ thống CMS.
- `static.example.com` phục vụ asset công khai.

Nếu dùng `Cross-Origin-Resource-Policy: same-site`, các subdomain cùng site có thể được phép nhúng tài nguyên qua no-cors. Nếu một subdomain bị chiếm quyền hoặc chứa nội dung attacker-controlled, phạm vi tin cậy có thể rộng hơn dự kiến.

Hãy dùng `same-origin` cho dữ liệu nhạy cảm cần giới hạn chặt. Chỉ dùng `same-site` khi thực sự tin cậy tất cả origin thuộc cùng site và đã đánh giá rủi ro từ subdomain.

## 3. Cú pháp và ý nghĩa ba giá trị CORP

CORP là **response header**. Server gửi header này cùng response của tài nguyên:

```http
Cross-Origin-Resource-Policy: same-origin
```

### 3.1. same-origin

`same-origin` chỉ cho phép request từ cùng origin sử dụng response theo CORP.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: image/svg+xml
Cross-Origin-Resource-Policy: same-origin
```

Nếu `https://app.example.com` tải ảnh từ cùng origin, request có thể tiếp tục theo các chính sách khác. Nếu `https://other.example.net` nhúng ảnh đó bằng request no-cors, browser sẽ chặn việc sử dụng response.

Đây là lựa chọn phù hợp cho:

- Ảnh đại diện riêng tư chỉ dành cho ứng dụng chính.
- Tài liệu hoặc dữ liệu nội bộ không cần nhúng từ origin khác.
- Tài nguyên mà server muốn giới hạn ở đúng origin phát hành.

### 3.2. same-site

`same-site` cho phép tài liệu cùng site, kể cả khi origin khác nhau, sử dụng tài nguyên qua CORP.

Ví dụ:

```text
https://app.example.com
https://cdn.example.com
```

Hai địa chỉ này khác origin nhưng thường cùng schemeful site. Nếu response đặt `Cross-Origin-Resource-Policy: same-site`, browser có thể cho phép request no-cors từ subdomain cùng site sử dụng tài nguyên.

Chọn same-site khi các subdomain là một ranh giới tin cậy được quản trị thống nhất. Không dùng chỉ vì các hostname có cùng hậu tố văn bản; browser xác định site theo quy tắc schemeful site và public suffix, không phải phép so chuỗi đơn giản.

### 3.3. cross-origin

`cross-origin` cho phép mọi origin nhúng tài nguyên trong các ngữ cảnh chịu kiểm tra CORP:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Giá trị này phù hợp với tài nguyên công khai được thiết kế để nhúng rộng rãi, ví dụ ảnh công khai hoặc một số asset CDN.

Tuy nhiên, `cross-origin` **không cấp quyền CORS**. Một trang khác có thể hiển thị ảnh trong thẻ `img` nhưng JavaScript vẫn không được đọc body của response bằng Fetch API nếu server không cho phép CORS.

### 3.4. Bảng so sánh

| Giá trị | Ai được phép nhúng qua no-cors? | Mức giới hạn |
|---|---|---|
| `same-origin` | Chỉ cùng origin | Chặt nhất |
| `same-site` | Cùng schemeful site, có thể gồm subdomain khác | Trung bình |
| `cross-origin` | Mọi origin | Rộng nhất |
| Không có header | CORP không đặt hạn chế | Phụ thuộc các chính sách khác |

Không có header không có nghĩa là response được JavaScript cross-origin đọc tự do. SOP, CORS và các chính sách khác vẫn có hiệu lực.

## 4. CORP áp dụng cho request nào?

CORP chủ yếu bảo vệ tài nguyên khi browser xử lý request có mode `no-cors`. Nhiều cơ chế nhúng tài nguyên trên web sử dụng no-cors theo mặc định, tùy loại phần tử và thuộc tính.

Ví dụ:

```html
<img src="https://cdn.example.net/banner.webp" alt="Banner">
<script src="https://cdn.example.net/legacy.js"></script>
<audio src="https://cdn.example.net/audio.ogg"></audio>
```

Các phần tử và thuộc tính `crossorigin` có thể làm thay đổi request mode. Script module và một số loại tài nguyên khác sử dụng CORS mode theo quy tắc riêng. Vì vậy, không kết luận chỉ dựa trên tên phần tử; hãy kiểm tra request mode thực tế trong Network hoặc theo HTML Fetch behavior.

### 4.1. no-cors không có nghĩa là không gửi request

Với request no-cors, browser vẫn có thể gửi request tới server. CORP được kiểm tra ở phía browser khi xử lý response. Nếu policy không cho phép, browser chặn việc response được sử dụng trong context đó.

Do đó, CORP không phải firewall và không đảm bảo server không nhận request. Nếu request có thể gây thay đổi trạng thái, server vẫn phải có CSRF protection, xác thực và phân quyền phù hợp.

### 4.2. no-cors response thường opaque với JavaScript

Ví dụ:

```js
const response = await fetch("https://cdn.example.net/data.json", {
  mode: "no-cors"
});

console.log(response.type); // "opaque"
```

Opaque response không cho JavaScript đọc status, headers hoặc body theo cách thông thường. CORP bổ sung quy tắc để chủ sở hữu tài nguyên có thể từ chối việc nhúng/tiêu thụ response no-cors từ context không được phép.

Không dùng `mode: "no-cors"` như một cách vượt CORS. Nó không cấp quyền đọc response cho JavaScript.

### 4.3. Request dùng CORS mode

Nếu ứng dụng cần JavaScript đọc response cross-origin, hãy dùng CORS mode và cấu hình CORS trên server:

```js
const response = await fetch("https://api.example.net/profile", {
  mode: "cors",
  credentials: "include"
});

const profile = await response.json();
```

Server phải trả CORS header phù hợp. CORP không thay thế bước đó. Với request CORS thành công, browser sử dụng quy tắc CORS để quyết định JavaScript có được đọc response hay không; CORP tập trung vào request no-cors.

## 5. CORP khác CORS như thế nào?

Hai cơ chế có tên gần nhau nhưng giải quyết hai câu hỏi khác nhau.

| Đặc điểm | CORP | CORS |
|---|---|---|
| Tên đầy đủ | Cross-Origin-Resource-Policy | Cross-Origin Resource Sharing |
| Header chính | `Cross-Origin-Resource-Policy` | `Access-Control-Allow-Origin` và các header liên quan |
| Nơi công bố | Response của tài nguyên | Response của server tài nguyên |
| Mục tiêu | Giới hạn việc nhúng/tiêu thụ tài nguyên qua no-cors | Cho phép hoặc từ chối JavaScript đọc response cross-origin trong CORS mode |
| Giá trị điển hình | same-origin, same-site, cross-origin | Origin cụ thể hoặc `*` trong trường hợp phù hợp |
| Có cấp quyền đọc body cho JS không? | Không | Có, nếu CORS check thành công |
| Có thay thế nhau không? | Không | Không |

### 5.1. CORP cross-origin không phải CORS wildcard

Giả sử response có:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Điều đó cho phép mọi origin sử dụng tài nguyên qua các request no-cors được CORP kiểm soát. Nó không tự động làm cho đoạn code sau đọc được response:

```js
const response = await fetch("https://assets.example.net/private.json");
const data = await response.json();
```

Nếu request dùng CORS mode mặc định của Fetch và server không trả `Access-Control-Allow-Origin` phù hợp, browser vẫn chặn JavaScript đọc response.

### 5.2. CORS cho phép đọc không có nghĩa mọi kiểu nhúng đều được mở

Ví dụ response có:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Header này cho phép origin được chỉ định đọc response khi request đáp ứng CORS. Nó không tự động thay đổi policy CORP của một request no-cors khác.

Hãy xác định request mode và mục tiêu:

- Cần nhúng resource mà JavaScript không đọc body: đánh giá CORP.
- Cần JavaScript đọc dữ liệu cross-origin: cấu hình CORS.
- Cần cả nhúng no-cors và đọc dữ liệu CORS: thiết kế và kiểm thử cả hai luồng.

### 5.3. Credentialed CORS

Nếu cần credential, không dùng `Access-Control-Allow-Origin: *`. Server phải phản hồi origin cụ thể và cho phép credentials theo quy tắc CORS:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

CORP không thay thế kiểm soát credential, cookie SameSite, CSRF token hoặc authorization server-side.

## 6. CORP, CORB và ORB

Các tên này thường bị nhầm lẫn vì đều liên quan đến việc hạn chế đọc tài nguyên cross-origin.

- **CORP** là policy tường minh do server sở hữu tài nguyên gửi qua response header.
- **CORB (Cross-Origin Read Blocking)** là cơ chế browser, nổi bật trong Chromium, nhằm hạn chế một số response cross-origin nhạy cảm bị đưa vào context no-cors.
- **ORB (Opaque Response Blocking)** là cơ chế browser liên quan việc chặn opaque response đáng ngờ dựa trên loại nội dung và các quy tắc phân tích response.

CORB/ORB dựa vào quy tắc browser và loại nội dung để giảm rủi ro rò rỉ dữ liệu. CORP cho phép chủ sở hữu tài nguyên khai báo trực tiếp phạm vi nhúng mong muốn.

Không dựa vào CORB/ORB như cấu hình bảo mật duy nhất. Nếu tài nguyên cần giới hạn embedding, hãy phát CORP header phù hợp và cấu hình các lớp liên quan.

## 7. CORP trong kiến trúc cross-origin isolation

Cross-origin isolation cho phép một tài liệu đạt trạng thái cô lập mạnh hơn trong browser, cần thiết cho một số khả năng như SharedArrayBuffer trong các browser hiện đại.

Các header thường phối hợp:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

- **COOP** kiểm soát quan hệ giữa top-level browsing context và các cửa sổ khác, giúp tách browsing context group.
- **COEP** yêu cầu tài liệu chỉ tải tài nguyên cross-origin khi tài nguyên đó opt-in bằng CORS hoặc CORP, tùy request mode và policy.
- **CORP** được đặt trên response của tài nguyên để cho phép hoặc giới hạn việc nhúng qua no-cors.

### 7.1. COEP require-corp

Khi tài liệu đặt:

```http
Cross-Origin-Embedder-Policy: require-corp
```

browser yêu cầu tài nguyên cross-origin phải opt-in. Một request no-cors cross-origin thường cần response CORP cho phép; một request CORS cần vượt qua CORS check.

Nếu tài nguyên CDN không gửi CORP hoặc CORS phù hợp, tài liệu có thể không tải được resource và không đạt trạng thái cross-origin isolated.

### 7.2. COEP credentialless

Một lựa chọn khác trên browser hỗ trợ là:

```http
Cross-Origin-Embedder-Policy: credentialless
```

Chế độ này thay đổi cách xử lý credential cho một số request no-cors cross-origin, cho phép tải một số tài nguyên opaque mà không yêu cầu CORP theo cùng cách với require-corp. Request được gửi mà không kèm credential trong trường hợp áp dụng.

Credentialless không phải cách bỏ mọi kiểm tra bảo mật. CORS mode vẫn cần CORS hợp lệ khi JavaScript muốn đọc response; cookie và các chính sách khác vẫn cần được đánh giá.

### 7.3. Kiểm tra trạng thái cross-origin isolated

Trong JavaScript:

```js
console.log(window.crossOriginIsolated);
```

Giá trị `true` cho biết document đang ở trạng thái cross-origin isolated trong browser hỗ trợ. Chỉ nhìn thấy header trong DevTools chưa đủ; hãy kiểm tra cả kết quả thực tế, console và việc tải các resource cần thiết.

CORP một mình không bật cross-origin isolation. Cần cấu hình COOP/COEP thích hợp trên document và đáp ứng các yêu cầu của tài nguyên được nhúng.

## 8. Chọn CORP cho từng loại tài nguyên

Không nên áp một giá trị duy nhất cho toàn bộ website nếu tài nguyên có mức nhạy cảm và nhu cầu nhúng khác nhau.

| Loại tài nguyên | Policy gợi ý | Lý do |
|---|---|---|
| API response chứa dữ liệu tài khoản | same-origin | Không cần nhúng từ origin khác |
| Ảnh avatar riêng tư | same-origin | Hạn chế embedding ngoài ứng dụng |
| Ảnh public trên CDN | cross-origin | Cho phép website khác hiển thị ảnh qua no-cors |
| Font public | Kiểm tra CORS trước; CORP tùy request mode và kiến trúc | Font thường dùng CORS mode |
| Script module trên CDN | CORS phù hợp | Module script dùng CORS fetching |
| Classic script nội bộ | same-origin nếu không cần cross-origin | Giới hạn embedding từ nơi khác |
| Tài nguyên dùng chung cho subdomain tin cậy | same-site | Cho phép các origin cùng site sử dụng |

Đây là điểm xuất phát. Hãy xác minh request mode và các yêu cầu của browser đối với từng loại tài nguyên.

### 8.1. Ảnh public

Nếu ảnh được thiết kế để hiển thị trên nhiều website, có thể trả:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Ảnh vẫn không tự động cho phép script đọc pixel sau khi vẽ vào canvas. Quy tắc same-origin/canvas tainting và CORS vẫn áp dụng.

### 8.2. API và dữ liệu nhạy cảm

Với response chứa dữ liệu tài khoản, hãy ưu tiên:

```http
Cross-Origin-Resource-Policy: same-origin
Cache-Control: private, no-store
```

CORP giảm khả năng response bị nhúng qua no-cors từ origin khác. Nhưng API vẫn phải kiểm tra authentication, authorization, CSRF và cache policy. Không dựa vào CORP để ngăn request đến server.

### 8.3. Tài nguyên CDN

Nếu ứng dụng dùng CDN khác origin:

- Với ảnh public chỉ cần hiển thị, CORP cross-origin có thể phù hợp.
- Với JavaScript module, font hoặc Fetch API cần đọc dữ liệu, cấu hình CORS đúng.
- Với COEP require-corp, đảm bảo từng resource cross-origin opt-in bằng CORP hoặc CORS tương ứng.
- Không dùng CORP cross-origin cho dữ liệu riêng tư chỉ để tránh lỗi tải resource.

## 9. Cấu hình CORP ở server

### 9.1. Node.js / Express

Có thể đặt header trên route:

```js
app.get("/private/avatar.svg", (req, res) => {
  res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  res.setHeader("Cache-Control", "private, no-store");
  res.type("image/svg+xml").send(svgContent);
});

app.get("/public/banner.webp", (req, res) => {
  res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
  res.sendFile(publicBannerPath);
});
```

Trong hệ thống thực tế, đặt policy theo loại tài nguyên và quyền truy cập. Không để client gửi query parameter để tự chọn CORP policy cho response nhạy cảm.

Có thể dùng middleware:

```js
function setCorp(policy) {
  const allowed = new Set(["same-origin", "same-site", "cross-origin"]);

  if (!allowed.has(policy)) {
    throw new TypeError("CORP policy không hợp lệ");
  }

  return (req, res, next) => {
    res.setHeader("Cross-Origin-Resource-Policy", policy);
    next();
  };
}

app.use("/private-assets", setCorp("same-origin"));
app.use("/public-assets", setCorp("cross-origin"));
```

### 9.2. Nginx

Ví dụ cấu hình cho hai nhóm đường dẫn:

```nginx
location /private-assets/ {
    add_header Cross-Origin-Resource-Policy "same-origin" always;
    add_header Cache-Control "private, no-store" always;
}

location /public-assets/ {
    add_header Cross-Origin-Resource-Policy "cross-origin" always;
}
```

Từ khóa `always` giúp Nginx thêm header cho nhiều response status, không chỉ response thành công thông thường. Hãy kiểm tra cấu hình thực tế khi có proxy/CDN phía trước vì header có thể bị ghi đè hoặc loại bỏ.

### 9.3. Kiểm tra response

Dùng curl:

```bash
curl -I https://app.example.com/private/avatar.svg
```

Kiểm tra:

- Header có xuất hiện trên response cuối cùng không?
- Có nhiều giá trị CORP mâu thuẫn do proxy thêm không?
- Redirect có dẫn đến response cuối cùng với policy mong muốn không?
- CDN cache có giữ đúng header cho đúng asset không?
- Error response có vô tình lộ thông tin hoặc thiếu header bảo vệ không?

CORP là response policy; hãy kiểm tra header trên chính response tài nguyên mà browser tải.

## 10. Chẩn đoán lỗi CORP trong DevTools

Khi một resource không tải được:

1. Mở tab **Network**, lọc theo loại resource.
2. Chọn request bị lỗi và xem Request URL, Initiator, Status và Response Headers.
3. Xác định request mode nếu DevTools hiển thị; đối chiếu phần tử/thuộc tính đã tạo request.
4. Đọc Console để tìm thông báo liên quan CORP hoặc COEP.
5. Kiểm tra response có `Cross-Origin-Resource-Policy` không và giá trị là gì.
6. Xác định requester cùng origin, same-site hay cross-site với resource.
7. Kiểm tra request có dùng CORS mode hay no-cors mode.
8. Nếu document có COEP require-corp, kiểm tra resource đã opt-in bằng CORP/CORS chưa.
9. Kiểm tra redirect, cache và response cuối cùng.
10. Sau khi sửa, kiểm tra lại các browser mục tiêu.

### 10.1. Một số tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ảnh cross-origin không hiển thị | Resource trả CORP same-origin hoặc same-site không phù hợp | Điều chỉnh policy theo nhu cầu thực tế |
| Resource hoạt động trước khi bật COEP nhưng hỏng sau đó | Resource cross-origin chưa opt-in | Thêm CORP hoặc CORS phù hợp |
| Fetch vẫn bị CORS error dù CORP cross-origin | CORP không cấp quyền đọc response cho JavaScript | Cấu hình Access-Control-Allow-Origin |
| Ảnh tải được nhưng canvas không đọc pixel | Canvas bị taint do cross-origin resource không có CORS opt-in phù hợp | Dùng CORS-enabled image và cấu hình ACAO |
| Một subdomain tải được, subdomain khác bị chặn | Khác site hoặc schemeful site | Xác định chính xác scheme/site và chọn policy |
| Header có trên origin nhưng mất qua CDN | Proxy/cache ghi đè hoặc loại bỏ header | Kiểm tra response tại edge và origin |

## 11. Lab local: kiểm chứng same-origin, same-site và cross-origin

Lab tạo một parent server và một asset server trên cùng máy. Hai server dùng port khác nhau để tạo hai origin. Ta đổi hostname đích để so sánh cùng site và khác site:

- Parent: `http://127.0.0.1:8080`.
- Asset cùng site nhưng khác origin: `http://127.0.0.1:8081`.
- Asset khác site: `http://localhost:8081`.

Cả hai hostname đều trỏ về loopback trên máy local. Port khác nhau làm origin khác nhau; hostname khác nhau giúp tạo site khác nhau cho phép thử.

### 11.1. Tạo file server

Tạo `corp-lab.mjs`:

```js
import http from "node:http";

const parentOrigin = "http://127.0.0.1:8080";

const parentHtml = [
  "<!doctype html>",
  "<html lang=\"vi\">",
  "<head>",
  "  <meta charset=\"utf-8\">",
  "  <title>CORP lab</title>",
  "</head>",
  "<body>",
  "  <h1>Cross-Origin-Resource-Policy lab</h1>",
  "  <label for=\"asset-host\">Host của asset:</label>",
  "  <select id=\"asset-host\">",
  "    <option value=\"127.0.0.1\">Cùng site, khác origin</option>",
  "    <option value=\"localhost\">Khác site, khác origin</option>",
  "  </select>",
  "  <label for=\"corp-policy\">CORP:</label>",
  "  <select id=\"corp-policy\">",
  "    <option value=\"none\">Không có header</option>",
  "    <option value=\"same-origin\">same-origin</option>",
  "    <option value=\"same-site\">same-site</option>",
  "    <option value=\"cross-origin\">cross-origin</option>",
  "  </select>",
  "  <button id=\"load-image\">Tải ảnh no-cors</button>",
  "  <img id=\"preview\" alt=\"Kết quả CORP\" width=\"320\" height=\"100\">",
  "  <p id=\"status\" aria-live=\"polite\"></p>",
  "  <button id=\"test-cors\">Thử fetch CORS</button>",
  "  <pre id=\"cors-result\"></pre>",
  "  <script>",
  "    const host = document.getElementById(\"asset-host\");",
  "    const policy = document.getElementById(\"corp-policy\");",
  "    const image = document.getElementById(\"preview\");",
  "    const status = document.getElementById(\"status\");",
  "    const assetUrl = () => \"http://\" + host.value + \":8081\";",
  "    document.getElementById(\"load-image\").addEventListener(\"click\", () => {",
  "      image.onload = () => { status.textContent = \"Ảnh đã tải.\"; };",
  "      image.onerror = () => { status.textContent = \"Ảnh bị chặn hoặc không tải được. Xem Console/Network.\"; };",
  "      image.src = assetUrl() + \"/image.svg?corp=\" + encodeURIComponent(policy.value) + \"&t=\" + Date.now();",
  "    });",
  "    document.getElementById(\"test-cors\").addEventListener(\"click\", async () => {",
  "      const output = document.getElementById(\"cors-result\");",
  "      try {",
  "        const response = await fetch(assetUrl() + \"/data?corp=same-origin\", { mode: \"cors\" });",
  "        output.textContent = JSON.stringify(await response.json(), null, 2);",
  "      } catch (error) {",
  "        output.textContent = error.name + \": \" + error.message;",
  "      }",
  "    });",
  "  </script>",
  "</body>",
  "</html>"
].join("\n");

const parentServer = http.createServer((req, res) => {
  if (req.url !== "/" && req.url !== "/index.html") {
    res.writeHead(404).end("Not found");
    return;
  }

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(parentHtml);
});

const assetServer = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8081");
  const corp = url.searchParams.get("corp");
  const allowedPolicies = new Set(["same-origin", "same-site", "cross-origin"]);

  if (allowedPolicies.has(corp)) {
    res.setHeader("Cross-Origin-Resource-Policy", corp);
  }

  res.setHeader("Cache-Control", "no-store");

  if (url.pathname === "/image.svg") {
    res.writeHead(200, { "Content-Type": "image/svg+xml" });
    res.end(
      "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"320\" height=\"100\">" +
      "<rect width=\"320\" height=\"100\" fill=\"#d1fae5\"/>" +
      "<text x=\"16\" y=\"56\" font-size=\"20\">CORP image</text></svg>"
    );
    return;
  }

  if (url.pathname === "/data") {
    res.setHeader("Access-Control-Allow-Origin", parentOrigin);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      ok: true,
      message: "CORS mode có thể đọc response",
      corp: "same-origin"
    }));
    return;
  }

  res.writeHead(404).end("Not found");
});

parentServer.listen(8080, "127.0.0.1", () => {
  console.log("Parent: http://127.0.0.1:8080");
});

assetServer.listen(8081, () => {
  console.log("Assets: http://127.0.0.1:8081 or http://localhost:8081");
});
```

### 11.2. Chạy lab

Trong thư mục chứa file:

```bash
node corp-lab.mjs
```

Mở `http://127.0.0.1:8080`. Chọn hostname asset và policy, sau đó nhấn **Tải ảnh no-cors**.

### 11.3. Kết quả mong đợi

| Host asset | CORP | Kết quả dự kiến |
|---|---|---|
| 127.0.0.1:8081 | Không có header | Không bị CORP chặn |
| 127.0.0.1:8081 | same-origin | Bị chặn vì port khác origin |
| 127.0.0.1:8081 | same-site | Được phép vì cùng site, khác origin |
| 127.0.0.1:8081 | cross-origin | Được phép |
| localhost:8081 | same-origin | Bị chặn |
| localhost:8081 | same-site | Bị chặn vì khác site trong lab |
| localhost:8081 | cross-origin | Được phép |

Kết quả còn phụ thuộc browser, chính sách riêng tư và cách browser xác định site cho địa chỉ local. Nếu có khác biệt, kiểm tra Console và Network thay vì kết luận chỉ từ hình ảnh.

### 11.4. So sánh với CORS mode

Nhấn **Thử fetch CORS**. Asset server trả:

```http
Access-Control-Allow-Origin: http://127.0.0.1:8080
Cross-Origin-Resource-Policy: same-origin
```

Fetch dùng mode `cors` và server cho phép origin parent đọc response. Response có CORP same-origin nhưng request không phải no-cors; do đó phép thử cho thấy CORS và CORP giải quyết hai trường hợp khác nhau.

### 11.5. Quan sát DevTools

1. Mở tab **Network** và tải lại parent.
2. Chọn request `image.svg`; kiểm tra Request URL và Response Headers.
3. Đổi CORP từ `same-origin` sang `cross-origin` và tải lại để thấy kết quả khác.
4. Đổi hostname asset từ `127.0.0.1` sang `localhost` để kiểm tra same-site.
5. Quan sát lỗi CORP trong Console khi response bị chặn.
6. Chạy fetch CORS và kiểm tra response JSON có thể đọc được.
7. Thử bỏ `Access-Control-Allow-Origin` trong asset server và xác nhận fetch CORS thất bại dù CORP là cross-origin.

Lab chỉ dùng tài nguyên local do bạn tự khởi chạy. Không thử nghiệm trên website hoặc tài nguyên không thuộc quyền kiểm thử.

## 12. Checklist triển khai CORP

Trước khi phát hành header:

1. **Phân loại tài nguyên:** Public asset, private asset, API response, font, script hay media?
2. **Xác định request mode:** Resource được tải bằng no-cors hay CORS mode?
3. **Chọn ranh giới:** Cần same-origin, same-site hay cross-origin?
4. **Đánh giá subdomain:** Nếu dùng same-site, mọi subdomain cùng site có thuộc cùng ranh giới tin cậy không?
5. **Kiểm tra CORS:** Nếu JavaScript cần đọc response, ACAO và credential policy đã đúng chưa?
6. **COEP:** Nếu document dùng require-corp, tất cả resource cross-origin đã opt-in bằng CORP hoặc CORS phù hợp chưa?
7. **COOP:** Nếu cần cross-origin isolation, top-level document có COOP phù hợp không?
8. **Cache/CDN:** Header có được giữ nguyên qua reverse proxy, CDN và cache không?
9. **Redirect:** Response cuối cùng sau redirect có policy đúng không?
10. **Error response:** Các response lỗi có lộ dữ liệu hoặc thiếu header quan trọng không?
11. **Cookie/CSRF:** Endpoint vẫn có authentication, authorization và CSRF protection độc lập chứ?
12. **Regression:** Đã kiểm tra các trang nhúng, canvas, font, module script và browser mục tiêu chưa?
13. **Monitoring:** Có theo dõi lỗi CORP/COEP sau khi triển khai không?

## 13. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "CORP và CORS là một." | CORP kiểm soát nhúng no-cors; CORS kiểm soát JavaScript đọc response cross-origin. |
| "CORP cross-origin cho phép fetch đọc dữ liệu." | Nó không cấp quyền CORS hoặc quyền đọc body cho JavaScript. |
| "same-site nghĩa là same-origin." | Subdomain hoặc port khác nhau có thể cùng site nhưng khác origin. |
| "Không có CORP nghĩa là ai cũng đọc được response." | SOP/CORS và các chính sách khác vẫn áp dụng. |
| "CORP ngăn request đến server." | Request có thể đã được gửi; browser kiểm tra response trước khi cho context sử dụng. |
| "CORS ngăn mọi request cross-origin." | CORS chủ yếu kiểm soát quyền đọc response; một số request vẫn được gửi. |
| "CORP một mình bật cross-origin isolation." | Cần COOP/COEP và các resource đáp ứng policy. |
| "same-site luôn an toàn cho tài nguyên riêng tư." | Subdomain cùng site có thể có mức tin cậy khác nhau. |
| "Font hoặc module script chỉ cần CORP cross-origin." | Các loại resource này thường cần CORS mode và CORS header phù hợp. |
| "CORB/ORB thay thế CORP." | Đây là cơ chế browser khác với policy tường minh do server công bố. |
| "Đặt CORP trên trang HTML là đủ cho mọi asset." | CORP cần được đặt trên response của từng tài nguyên cần policy. |

## 14. Câu hỏi ôn tập

1. CORP là gì và được gửi ở phía request hay response?
2. Ba giá trị same-origin, same-site và cross-origin khác nhau như thế nào?
3. Vì sao hai subdomain có thể cùng site nhưng khác origin?
4. Schemeful same-site tính những thành phần nào?
5. CORP chủ yếu kiểm soát request mode nào?
6. Vì sao request no-cors vẫn có thể đến server dù browser chặn response?
7. CORP cross-origin có cho phép JavaScript đọc body response không?
8. CORS khác CORP ở mục tiêu nào?
9. Vì sao CORS không thay thế CSRF protection?
10. CORP phối hợp với COEP require-corp như thế nào?
11. COOP có vai trò gì trong cross-origin isolation?
12. Vì sao same-site có thể quá rộng đối với tài nguyên nhạy cảm?
13. Vì sao CORP một mình không đủ để bật cross-origin isolation?
14. Làm thế nào xác định một resource bị chặn do CORP hay do CORS?

**Đáp án định hướng:** (1) Response header do chủ sở hữu tài nguyên gửi. (2) Cùng origin; cùng schemeful site; hoặc mọi origin. (3) Origin tính scheme/host/port, site dựa trên scheme và registrable domain. (4) Scheme và registrable domain; port không tham gia. (5) no-cors. (6) CORP kiểm tra việc sử dụng response ở browser, không phải firewall chặn request. (7) Không. (8) CORS cho phép JavaScript đọc response khi check thành công; CORP giới hạn embedding no-cors. (9) Request thay đổi trạng thái vẫn có thể được gửi. (10) COEP yêu cầu tài nguyên cross-origin opt-in bằng CORP hoặc CORS theo request mode. (11) COOP cô lập top-level browsing context khỏi opener cross-origin. (12) Subdomain khác nhau có thể không cùng mức tin cậy. (13) CORP chỉ là policy trên response tài nguyên; document cần COOP/COEP phù hợp và các tài nguyên nhúng phải đáp ứng yêu cầu của COEP. (14) Kiểm tra request mode, response header, Console và Network; lỗi CORS thường liên quan ACAO, còn CORP liên quan Cross-Origin-Resource-Policy.

## 15. Tài liệu tham khảo

- [W3C — Fetch Standard: Cross-Origin-Resource-Policy](https://fetch.spec.whatwg.org/#cross-origin-resource-policy-header): Định nghĩa và xử lý CORP.
- [W3C — Cross-Origin Resource Policy (CORP)](https://resourcepolicy.fyi/): Tổng quan policy và các giá trị CORP.
- [MDN — Cross-Origin-Resource-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy): Cú pháp, giá trị và tương thích browser.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): Request CORS và response headers.
- [MDN — Cross-Origin Embedder Policy (COEP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy): require-corp, credentialless và cross-origin isolation.
- [MDN — Cross-Origin Opener Policy (COOP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy): Cô lập browsing context.
- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/): Các policy tài nguyên và quan hệ với embedding.
- [Chromium — CORB](https://www.chromium.org/Home/chromium-security/corb-for-developers/): Cơ chế Cross-Origin Read Blocking.
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): Các lưu ý về ranh giới origin và dữ liệu phía client.

**Kết nối với mô hình bảo mật web:** CORP cho phép chủ sở hữu response xác định tài liệu cùng origin, cùng site hay mọi origin được nhúng tài nguyên qua no-cors. CORS vẫn chịu trách nhiệm cho quyền JavaScript đọc response; COEP dùng CORP/CORS để kiểm soát tài nguyên khi xây dựng cross-origin isolation, còn COOP cô lập browsing context. Chọn policy theo mức tin cậy thực tế của từng tài nguyên và kiểm tra request mode thay vì chỉ dựa vào hostname.
