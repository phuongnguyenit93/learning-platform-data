# Cross-Origin-Resource-Policy — kiểm soát việc website khác tải tài nguyên

> **Chương:** Security headers  
> **Mục tiêu:** Hiểu Cross-Origin-Resource-Policy (CORP), cách browser áp dụng header này với các request tài nguyên cross-origin ở chế độ no-CORS; phân biệt same-origin, same-site và cross-origin; chọn giữa các giá trị `same-origin`, `same-site`, `cross-origin`; phối hợp CORP với CORS và COEP; triển khai theo từng loại tài nguyên và kiểm chứng bằng DevTools.

## 1. CORP giải quyết vấn đề gì?

Một website có thể tải tài nguyên từ website khác mà không cần JavaScript được phép đọc nội dung response. Ví dụ, trang có thể hiển thị ảnh từ CDN, nhúng một script cổ điển hoặc tải một số tài nguyên theo chế độ no-CORS. Browser thường cho phép những request này và giữ response ở trạng thái không cho script cross-origin đọc trực tiếp.

Điều đó vẫn có thể tạo ra rủi ro. Một website bên ngoài có thể cố nhúng hoặc tải tài nguyên từ ứng dụng của bạn trong một ngữ cảnh cross-origin. Việc tài nguyên có được sử dụng hay không đôi khi có thể làm lộ tín hiệu về trạng thái đăng nhập, nội dung riêng tư hoặc sự tồn tại của dữ liệu. Những kỹ thuật suy luận qua hành vi tải tài nguyên thường được xếp vào nhóm cross-site leaks (XS-Leaks).

**Cross-Origin-Resource-Policy (CORP)** là response header cho phép server nói rõ site/origin nào được phép sử dụng tài nguyên trong các request no-CORS thuộc phạm vi kiểm tra CORP.

Ví dụ:

```http
Cross-Origin-Resource-Policy: same-origin
```

Với policy này, browser chặn việc một trang khác origin sử dụng response trong ngữ cảnh no-CORS không thỏa điều kiện same-origin. Đây là lớp bảo vệ do browser thực thi dựa trên chỉ thị của server sở hữu tài nguyên.

CORP không phải cơ chế xác thực hoặc authorization phía server. Nó cũng không thay thế CORS, CSP, frame protection, CSRF protection hay kiểm tra quyền truy cập tài nguyên.

## 2. CORP là response header của tài nguyên

CORP được gửi trong response chứa tài nguyên cần bảo vệ:

```http
HTTP/1.1 200 OK
Content-Type: image/png
Cross-Origin-Resource-Policy: same-origin
```

Ví dụ tài nguyên có thể áp dụng:

- Ảnh riêng tư hoặc ảnh đại diện chỉ dùng trong ứng dụng.
- Script, stylesheet hoặc dữ liệu tĩnh chỉ dành cho site của ứng dụng.
- Một số response JSON hoặc tài nguyên nội bộ được tải qua no-CORS.
- Tài nguyên được dùng trong trang yêu cầu cross-origin isolation.

CORP là policy của **response tài nguyên**, không phải allowlist đặt ở trang nhúng. Server trả tài nguyên quyết định nó có thể được dùng bởi request cross-origin theo các giá trị CORP hay không.

Header không có nghĩa mọi request khác origin sẽ bị chặn. Cần xem request mode và cách browser sử dụng response. CORP chủ yếu được kiểm tra với request mode no-CORS; request mode CORS dựa vào kiểm tra CORS.

## 3. Ba giá trị CORP

CORP có ba giá trị chính:

| Giá trị | Ý nghĩa |
| --- | --- |
| `same-origin` | Chỉ cho phép tài nguyên được dùng trong ngữ cảnh cùng origin |
| `same-site` | Cho phép cùng site, kể cả khác origin; chặn site khác |
| `cross-origin` | Cho phép tài nguyên được dùng trong ngữ cảnh cross-origin |

Ví dụ:

```http
Cross-Origin-Resource-Policy: same-origin
```

```http
Cross-Origin-Resource-Policy: same-site
```

```http
Cross-Origin-Resource-Policy: cross-origin
```

Nếu response không có CORP header, browser không có chỉ thị CORP tường minh để hạn chế tài nguyên. Hành vi vẫn phụ thuộc các cơ chế khác như CORS, CSP, COEP, MIME checking và chính sách của browser.

Không có giá trị CORP dạng danh sách hostname tùy ý. Nếu cần cho phép JavaScript từ một số origin cụ thể đọc response, hãy dùng CORS với allowlist phù hợp. Nếu cần cho phép tài nguyên được nhúng bởi một tập đối tác theo kiểu no-CORS, CORP không biểu diễn được allowlist đó; cần thiết kế lại cách tải, dùng CORS hoặc phân phối tài nguyên qua origin phù hợp.

## 4. Same-origin, same-site và cross-origin

Muốn chọn CORP đúng, cần phân biệt origin với site.

**Origin** của URL HTTP(S) gồm scheme, host và port:

```text
https://app.example.com:443
scheme = https
host   = app.example.com
port   = 443 (cổng mặc định)
```

**Site** trong ngữ cảnh cookie và các cơ chế browser hiện đại thường dựa trên schemeful site: scheme cùng registrable domain (thường được xác định qua Public Suffix List). Port không phải thành phần của site.

Ví dụ:

| URL A | URL B | Cùng origin? | Cùng schemeful site? |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://app.example.com:443` | Có | Có |
| `https://app.example.com` | `https://static.example.com` | Không | Có |
| `https://app.example.com` | `http://static.example.com` | Không | Không |
| `https://app.example.com` | `https://example.net` | Không | Không |
| `https://app.example.com:8443` | `https://app.example.com` | Không | Có |

Vì vậy, CORP `same-site` rộng hơn `same-origin`. Nó có thể cho phép một subdomain khác origin trong cùng site tải tài nguyên theo no-CORS.

Không đồng nhất “cùng site” với “cùng mức tin cậy”. Một sibling subdomain có thể do nhóm khác, tenant khác hoặc hệ thống upload nội dung quản lý. Nếu các subdomain không cùng trust boundary, `same-site` có thể rộng hơn yêu cầu bảo mật.

## 5. CORP áp dụng với request mode no-CORS

Browser có nhiều cách tải tài nguyên. Trong request mode no-CORS, trang có thể yêu cầu tài nguyên cross-origin nhưng JavaScript thường không được đọc response body như một response CORS bình thường.

Ví dụ:

- Một số ảnh được tải bằng `<img src>` mặc định ở chế độ no-CORS.
- Script cổ điển không khai báo thuộc tính `crossorigin` thường được tải theo no-CORS.
- Một số stylesheet và tài nguyên nhúng khác có thể dùng no-CORS tùy loại request.
- Fetch với `mode: "no-cors"` trả về opaque response và bị giới hạn về method/header.

CORP giúp server chủ động hạn chế những response tài nguyên được sử dụng qua các request no-CORS này.

Ví dụ một ảnh chỉ dành cho cùng origin:

```http
HTTP/1.1 200 OK
Content-Type: image/png
Cross-Origin-Resource-Policy: same-origin
```

Nếu trang khác origin cố tải ảnh trong ngữ cảnh no-CORS, browser có thể chặn response theo CORP. Request mạng vẫn có thể đã được gửi tới server; CORP không phải firewall và không đảm bảo request chưa chạm tới endpoint.

### CORP không phải quy tắc cho mọi kiểu navigation

CORP chủ yếu kiểm soát việc response được dùng trong các request no-CORS thuộc phạm vi của nó. Nó không phải header chống nhúng tài liệu trong iframe và không thay thế chính sách điều hướng hoặc framing. Với clickjacking, dùng CSP `frame-ancestors`; với quyền đọc response từ JavaScript cross-origin, dùng CORS.

## 6. Phân biệt CORP với CORS

Tên hai cơ chế gần giống nhau nhưng chúng giải quyết các vấn đề khác nhau:

| Cơ chế | Câu hỏi chính | Cách hoạt động |
| --- | --- | --- |
| **CORS** | JavaScript từ origin khác có được đọc response không? | Server trả Access-Control-Allow-Origin và các header CORS phù hợp; browser thực hiện CORS check |
| **CORP** | Tài nguyên có được dùng trong request cross-origin no-CORS không? | Server khai báo same-origin, same-site hoặc cross-origin; browser áp dụng CORP check |

Ví dụ response CORS cho một ứng dụng cụ thể:

```http
Access-Control-Allow-Origin: https://dashboard.partner.example
Vary: Origin
```

Ví dụ response CORP:

```http
Cross-Origin-Resource-Policy: same-site
```

Một request dùng mode CORS cần response thỏa CORS policy. CORP không cấp quyền cho JavaScript đọc response và không thay thế Access-Control-Allow-Origin.

Ngược lại, CORS không phải chỉ thị chung cho mọi kiểu nhúng no-CORS. Một ảnh được tải bằng no-CORS không trở thành response có thể đọc bằng JavaScript chỉ vì server có CORP `cross-origin`.

### Ví dụ với fetch

Fetch mặc định dùng mode CORS:

```js
const response = await fetch("https://api.example.net/data");
const data = await response.json();
```

Để JavaScript đọc response cross-origin, server phải cho phép origin qua CORS. Chỉ thêm CORP `cross-origin` là chưa đủ.

Ngược lại:

```js
const response = await fetch("https://cdn.example.net/image.png", {
  mode: "no-cors",
});

console.log(response.type); // "opaque" trong trường hợp no-CORS thành công
```

Opaque response không cho JavaScript đọc body, status hoặc headers theo cách thông thường. CORP có thể quyết định response no-CORS đó có được phép sử dụng hay bị chặn theo policy tài nguyên.

## 7. CORP và COEP: tạo môi trường cross-origin isolated

Cross-Origin-Embedder-Policy (COEP) được đặt trên document muốn giới hạn cách nhúng tài nguyên cross-origin. Một cấu hình phổ biến:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Với COEP `require-corp`, các tài nguyên cross-origin cần opt-in phù hợp:

- Tài nguyên được tải theo mode CORS phải vượt qua CORS check.
- Tài nguyên được tải theo mode no-CORS cần có CORP cho phép theo ngữ cảnh.

Ví dụ tài nguyên CDN không cần JavaScript đọc response nhưng cần được nhúng no-CORS có thể trả:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Điều này cho phép tài nguyên opt-in để được dùng cross-origin theo no-CORS trong bối cảnh phù hợp. Nếu tài nguyên chỉ dành cho cùng site, chọn `same-site`; nếu chỉ dành cho cùng origin, chọn `same-origin`.

COEP `credentialless` là một chế độ khác: browser có thể tải một số tài nguyên cross-origin no-CORS mà không gửi credentials, theo quy tắc hỗ trợ, và không yêu cầu cùng cách opt-in CORP như `require-corp`. Cần kiểm tra browser support và tác động tới cookie/HTTP authentication trước khi chọn.

### Kiểm tra cross-origin isolation

Sau khi cấu hình COOP/COEP và sửa các tài nguyên phụ thuộc, kiểm tra trong Console:

```js
console.log(window.crossOriginIsolated);
```

Giá trị `true` cho biết document đang ở trạng thái cross-origin isolated theo browser. CORP chỉ là một phần của bức tranh; cần cả COOP, COEP và mọi điều kiện liên quan.

## 8. Chọn CORP cho từng loại tài nguyên

Không nên đặt một giá trị CORP giống nhau cho mọi response nếu tài nguyên có nhu cầu chia sẻ khác nhau.

| Tài nguyên | Policy có thể cân nhắc | Lý do |
| --- | --- | --- |
| API response chứa dữ liệu riêng tư, chỉ dùng trong app | `same-origin` | Giảm việc nhúng response qua no-CORS từ site khác |
| Ảnh nội bộ chỉ dùng trên các subdomain cùng site | `same-site` | Cho phép CDN/app sibling cùng site sử dụng |
| Font hoặc ảnh công khai được nhúng bởi nhiều website | `cross-origin` hoặc CORS tùy cách tải | Cho phép phân phối công khai theo nhu cầu |
| Script CDN được tải no-CORS bởi nhiều site | `cross-origin` nếu thực sự công khai | Opt-in rõ ràng cho việc nhúng cross-origin |
| Tài nguyên chỉ dành cho cùng origin | `same-origin` | Hạn chế request no-CORS cross-origin |
| Widget đối tác cần đọc dữ liệu bằng JavaScript | CORS phù hợp, không chỉ CORP | JavaScript cần đọc response theo CORS mode |

Các giá trị trong bảng là điểm bắt đầu. Cần kiểm tra loại request thực tế, thuộc tính `crossorigin`, COEP của document nhúng và yêu cầu của sản phẩm.

## 9. Ví dụ: bảo vệ API response và tài nguyên nội bộ

Giả sử ứng dụng trả response nội bộ:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: private, no-store
Cross-Origin-Resource-Policy: same-origin
X-Content-Type-Options: nosniff
```

CORP `same-origin` giúp browser từ chối việc một trang khác origin dùng response trong request no-CORS thuộc phạm vi kiểm tra. Cache-Control giảm lưu response nhạy cảm ngoài ý muốn; nosniff giúp tránh MIME sniffing trong các ngữ cảnh áp dụng.

Nhưng API vẫn phải:

- Xác thực session/token.
- Kiểm tra quyền truy cập từng resource.
- Không trả dữ liệu riêng tư cho request chưa được phép.
- Dùng CSRF protection cho thao tác thay đổi trạng thái dựa trên cookie.
- Cấu hình CORS chính xác nếu có client cross-origin hợp lệ.

CORP không làm endpoint trở thành private. Client ngoài browser vẫn có thể gửi request HTTP trực tiếp; server phải tự bảo vệ dữ liệu.

## 10. Ví dụ: tài nguyên công khai từ CDN

Một ảnh công khai cần được nhiều site nhúng có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: image/avif
Cache-Control: public, max-age=86400
Cross-Origin-Resource-Policy: cross-origin
```

`cross-origin` thể hiện server cho phép tài nguyên được dùng trong ngữ cảnh cross-origin no-CORS. Nó không làm response có thể đọc bởi JavaScript cross-origin; nếu client cần đọc bytes qua Fetch/CORS, CDN cần cấu hình CORS phù hợp.

Không đặt `cross-origin` cho mọi tài nguyên theo thói quen. Tài nguyên công khai và dữ liệu riêng tư có threat model khác nhau. Chọn header dựa trên việc ai cần nhúng tài nguyên, có cần đọc response hay không và tài nguyên có chứa dữ liệu theo phiên hay không.

## 11. Ví dụ: tài nguyên chỉ dành cho cùng site

Một ứng dụng có:

- `https://app.example.com`: giao diện chính.
- `https://static.example.com`: tài nguyên tĩnh.
- `https://uploads.example.com`: nội dung do người dùng tải lên.

Nếu ảnh tại static chỉ được dùng bởi các subdomain cùng site, có thể cân nhắc:

```http
Cross-Origin-Resource-Policy: same-site
```

Tuy nhiên, cùng site không đồng nghĩa cùng trust boundary. Nếu uploads có nội dung người dùng kiểm soát và một ứng dụng cùng site có thể nhúng tài nguyên đó, hãy đánh giá rủi ro riêng. Có thể cần origin tách biệt, policy `same-origin`, CORS hạn chế hoặc cách phục vụ nội dung khác.

Không dùng `same-site` để thay thế xác thực quan hệ giữa các subdomain. CORP chỉ dựa vào site/origin mà browser nhìn thấy; nó không biết nhóm nào sở hữu subdomain.

## 12. CORP không phải frame protection

Một hiểu nhầm phổ biến là đặt:

```http
Cross-Origin-Resource-Policy: same-origin
```

trên HTML document rồi cho rằng website khác không thể nhúng trang đó trong iframe. CORP không phải cơ chế chống framing cho document navigation.

Để kiểm soát ai được phép nhúng trang:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Hoặc dùng X-Frame-Options cho tương thích legacy khi phù hợp:

```http
X-Frame-Options: DENY
```

Phân biệt:

| Cơ chế | Bảo vệ |
| --- | --- |
| CORP | Việc dùng tài nguyên trong request cross-origin no-CORS |
| CORS | Việc JavaScript cross-origin đọc response |
| CSP `frame-ancestors` | Ai được phép nhúng document hiện tại |
| CSP `frame-src` | Document hiện tại được tải frame từ đâu |
| X-Frame-Options | Lớp kiểm soát framing legacy |

Chọn đúng cơ chế theo loại request và mục tiêu bảo vệ.

## 13. CORP không ngăn request tới server

CORP được browser kiểm tra khi response được dùng trong ngữ cảnh liên quan. Nó không phải network firewall và không đảm bảo request chưa được gửi.

Điều này có các hệ quả:

- Server vẫn có thể nhận request và ghi log.
- Endpoint vẫn cần authorization và rate limit.
- CORP không ngăn request làm thay đổi trạng thái server nếu endpoint thiết kế sai.
- CORP không thay CSRF token, SameSite cookie hoặc kiểm tra Origin.
- Client ngoài browser không bị ràng buộc bởi browser CORP enforcement.

Không dùng CORP như biện pháp duy nhất để giữ bí mật response. Nếu dữ liệu nhạy cảm, server chỉ trả dữ liệu cho caller đã xác thực và được phân quyền.

## 14. CORP, XS-Leaks và giới hạn bảo vệ

Một số tấn công XS-Leaks không đọc trực tiếp response cross-origin mà suy luận thông tin qua side channel, ví dụ:

- Tài nguyên có tải thành công hay bị chặn.
- Kích thước hoặc thời gian tải thay đổi theo trạng thái đăng nhập.
- Hành vi cache hoặc lỗi khác nhau theo nội dung.
- Một phần tử có kích thước/chiều cao khác nhau theo response.

CORP giúp hạn chế một số cách website ngoài sử dụng response trong no-CORS context. Tuy nhiên, nó không loại bỏ mọi side channel:

- Request vẫn có thể được gửi.
- Timing, cache, navigation và các hành vi browser khác vẫn có thể tạo tín hiệu.
- CORS-enabled resource có cơ chế kiểm soát riêng.
- Một origin cùng site nhưng khác origin có thể vẫn được phép nếu policy là `same-site`.
- Dữ liệu đã được công khai hoặc nhúng theo policy rộng vẫn có thể được quan sát theo cách khác.

Kết hợp CORP với cache policy, response đồng nhất khi không được phép, authorization, COEP và thiết kế endpoint phù hợp.

## 15. CORP và tài nguyên người dùng tải lên

Nội dung do người dùng tải lên thường có mức tin cậy thấp hơn code ứng dụng. Nếu phục vụ ảnh, HTML hoặc file từ cùng origin với ứng dụng, tài nguyên có thể được nhúng trong những ngữ cảnh không dự kiến.

Một số hướng thiết kế:

- Lưu nội dung upload trên origin riêng không mang cookie ứng dụng.
- Phục vụ đúng Content-Type và cân nhắc Content-Disposition.
- Dùng `X-Content-Type-Options: nosniff`.
- Chọn CORP `same-origin` hoặc `same-site` theo nhu cầu nhúng thực tế.
- Không cho nội dung upload chạy script trong origin ứng dụng.
- Dùng CSP và sandbox phù hợp nếu cần hiển thị HTML do người dùng tạo.

CORP không thay thế origin isolation. Nếu file upload có thể chứa HTML/SVG hoặc nội dung chủ động, tách origin thường là biện pháp quan trọng hơn.

## 16. Cấu hình CORP tại server

### Node.js/Express

Ví dụ một route tài nguyên nội bộ:

```js
app.get("/private-assets/:name", requireUser, (req, res) => {
  // Kiểm tra quyền truy cập tài nguyên trước khi gửi file.
  const asset = findAuthorizedAsset(req.user, req.params.name);
  if (!asset) {
    return res.sendStatus(404);
  }

  res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Cache-Control", "private, no-store");
  res.type(asset.contentType);
  res.send(asset.bytes);
});
```

Đây là ví dụ cấu trúc; hàm authorization và storage cần được triển khai theo ứng dụng. Không dùng tên file từ request làm đường dẫn filesystem trực tiếp.

### Nginx

Ví dụ áp dụng CORP cho một location:

```nginx
location /private-assets/ {
    add_header Cross-Origin-Resource-Policy "same-origin" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Cache-Control "private, no-store" always;
}
```

Kiểm tra quy tắc kế thừa add_header và cấu hình upstream. Đảm bảo header xuất hiện trên response thực tế, kể cả error response nếu chính sách yêu cầu.

### CDN/object storage

Nếu tài nguyên được phục vụ trực tiếp từ CDN hoặc object storage, header phải được cấu hình tại metadata object, response header policy hoặc edge rule phù hợp. Thay đổi tại ứng dụng origin không có tác dụng nếu browser nhận response từ CDN không mang CORP.

Kiểm tra cache invalidation khi thay policy; CDN có thể tiếp tục trả response cũ cho đến khi hết TTL hoặc bị purge.

## 17. Kết hợp CORP với thuộc tính crossorigin

Thuộc tính `crossorigin` trên HTML element ảnh hưởng request mode và credentials mode trong một số loại tài nguyên.

Ví dụ:

```html
<!-- Mặc định thường là no-CORS cho ảnh. -->
<img src="https://cdn.example.net/photo.png" alt="Ảnh">

<!-- Yêu cầu chế độ CORS. -->
<img
  src="https://cdn.example.net/photo.png"
  crossorigin="anonymous"
  alt="Ảnh CORS"
>
```

Với request CORS, server tài nguyên phải trả CORS header phù hợp. CORP không thay thế CORS check.

Một số điểm cần nhớ:

- Classic script có thể tải no-CORS nếu không có thuộc tính crossorigin; module script dùng CORS mode.
- Font cross-origin thường yêu cầu CORS.
- Ảnh no-CORS có thể hiển thị nhưng làm canvas bị taint; CORS phù hợp có thể cho phép dùng ảnh trong canvas theo điều kiện.
- Thêm `crossorigin="anonymous"` không tự cấp quyền; server vẫn phải trả ACAO tương ứng.

Khi một tài nguyên đột nhiên bị chặn sau khi bật COEP/CORP, hãy kiểm tra request mode và thuộc tính crossorigin trước khi thay header một cách rộng rãi.

## 18. Rollout CORP mà không làm hỏng ứng dụng

Áp dụng CORP `same-origin` cho mọi tài nguyên có thể phá các tích hợp hợp lệ như CDN, ảnh dùng chung, font, script hoặc widget.

Lộ trình:

1. **Kiểm kê tài nguyên:** xác định tài nguyên nào được tải cross-origin, request mode, origin/site của bên nhúng và có cần JavaScript đọc response không.
2. **Phân loại dữ liệu:** public, nội bộ cùng site, private cùng origin hoặc nội dung upload.
3. **Chọn policy:** dùng same-origin cho tài nguyên nội bộ; same-site chỉ khi sibling subdomain cùng trust boundary; cross-origin chỉ khi tài nguyên cần công khai.
4. **Kiểm tra CORS:** với request mode CORS, cấu hình ACAO và credentials đúng thay vì trông chờ CORP.
5. **Kiểm tra COEP:** nếu document dùng require-corp, xác minh mọi cross-origin resource opt-in bằng CORP hoặc CORS.
6. **Staging/canary:** thử với các luồng chính, browser mục tiêu và tài nguyên CDN.
7. **Quan sát:** kiểm tra Console, Network, lỗi tải script/font/image và trạng thái crossOriginIsolated.
8. **Enforce:** phát hành policy theo từng loại response và theo dõi cache/CDN sau triển khai.

Không đặt CORP `cross-origin` trên tài nguyên private chỉ để khắc phục lỗi COEP. Hãy xác định tài nguyên có thực sự cần chia sẻ cross-origin không.

## 19. Kiểm thử CORP bằng DevTools

Thực hành trong hai origin lab do bạn kiểm soát, ví dụ `https://app.example.test` và `https://cdn.example.test`. Không dùng dữ liệu riêng tư hoặc endpoint của bên thứ ba.

### Bước 1 — Tạo tài nguyên thử nghiệm

Phục vụ một ảnh công khai hoặc file text nhỏ từ origin CDN. Bắt đầu không có CORP để quan sát hành vi mặc định.

### Bước 2 — Thêm same-origin

Trả response:

```http
Cross-Origin-Resource-Policy: same-origin
```

Tải tài nguyên bằng no-CORS từ trang khác origin. Quan sát browser chặn việc sử dụng response và ghi nhận lỗi liên quan trong Console.

### Bước 3 — Thử same-site

Dùng hai subdomain HTTPS cùng registrable domain trong lab. Đặt CORP `same-site`, xác minh tài nguyên được dùng trong no-CORS context cùng site nhưng khác origin; thử một site khác để thấy bị chặn.

### Bước 4 — Thử cross-origin

Đổi thành CORP `cross-origin`. Xác minh resource có thể được dùng trong no-CORS context cross-origin. Sau đó thử Fetch mode CORS để thấy JavaScript vẫn cần CORS header nếu muốn đọc response.

### Bước 5 — Kết hợp COEP

Bật COEP `require-corp` trên document lab. Kiểm tra tài nguyên cross-origin nào bị chặn do thiếu CORP/CORS. Thêm opt-in đúng cho từng resource và quan sát thay đổi.

### Bước 6 — Kiểm tra request thực tế

Trong Network, xem:

- Request mode và initiator nếu DevTools cung cấp.
- Response header CORP.
- CORS response header nếu request mode là CORS.
- Console message giải thích resource bị chặn.
- Header COEP của document nhúng.

Đừng kết luận chỉ từ việc ảnh không hiển thị; kiểm tra cả request, response và policy ở hai phía.

## 20. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ảnh cross-origin không hiển thị | CORP same-origin/same-site không cho phép site nhúng | Chọn policy theo nhu cầu chia sẻ thực tế |
| Script CDN bị chặn sau khi bật COEP | Script no-CORS không có CORP opt-in phù hợp | Thêm CORP nếu thực sự công khai hoặc chuyển sang CORS phù hợp |
| Fetch mode CORS vẫn lỗi dù có CORP cross-origin | Thiếu hoặc sai Access-Control-Allow-Origin | Cấu hình CORS allowlist trên server tài nguyên |
| Tài nguyên cùng site vẫn bị chặn | Schemeful site khác nhau hoặc request thuộc site khác | Kiểm tra scheme, registrable domain và response policy |
| Tài nguyên cùng site được tải dù khác origin | CORP same-site cho phép theo site | Nếu cần ranh giới chặt hơn, dùng same-origin |
| Tài nguyên tải được nhưng JS không đọc body | Request no-CORS trả opaque response | Dùng CORS mode và ACAO nếu cần đọc |
| Iframe vẫn nhúng được trang | CORP không phải framing policy | Dùng CSP frame-ancestors/X-Frame-Options |
| Server vẫn nhận request dù browser chặn tài nguyên | CORP kiểm soát việc dùng response, không phải firewall | Bảo vệ endpoint bằng authentication, authorization và rate limit |
| Sau deploy vẫn thấy header cũ | CDN/browser cache response | Purge hoặc chờ TTL; kiểm tra response cuối |
| COEP làm hỏng font/ảnh bên thứ ba | Thiếu CORS/CORP opt-in hoặc request mode khác dự kiến | Kiểm tra từng tài nguyên và cách tải |

## 21. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “CORP cho JavaScript cross-origin đọc response.” | Đó là việc của CORS; CORP không cấp quyền đọc response. |
| “CORP same-site nghĩa là cùng origin.” | Same-site có thể gồm nhiều subdomain và port khác nhau. |
| “CORP chặn mọi request cross-origin trước khi gửi.” | Request có thể vẫn tới server; CORP kiểm soát việc browser sử dụng response trong ngữ cảnh liên quan. |
| “CORP ngăn iframe nhúng trang.” | Dùng CSP frame-ancestors hoặc X-Frame-Options cho framing. |
| “cross-origin nghĩa là response có thể đọc bằng fetch.” | No-CORS vẫn có thể trả opaque response; muốn đọc cần CORS. |
| “Cứ đặt same-origin cho mọi thứ là an toàn.” | Có thể làm hỏng CDN, font, ảnh và tích hợp hợp lệ; policy phải theo loại tài nguyên. |
| “same-site luôn đáng tin.” | Sibling subdomain có thể thuộc trust boundary khác hoặc do tenant quản lý. |
| “COEP require-corp chỉ cần bật trên document.” | Tài nguyên cross-origin phải opt-in qua CORP hoặc CORS phù hợp. |
| “CORP thay authentication.” | Client ngoài browser không bị CORP ràng buộc; server vẫn phải kiểm tra quyền. |

## 22. Checklist triển khai CORP

- Xác định tài nguyên nào được tải qua no-CORS và site/origin nào cần dùng chúng.
- Chọn `same-origin` cho tài nguyên chỉ dùng trong origin; chọn `same-site` chỉ khi sibling subdomain cùng trust boundary; chọn `cross-origin` cho tài nguyên cần nhúng công khai.
- Không coi CORP là allowlist origin tùy ý; dùng CORS nếu cần cho phép JavaScript đọc response từ origin cụ thể.
- Kiểm tra request mode, thuộc tính crossorigin và loại tài nguyên.
- Khi bật COEP require-corp, xác minh tài nguyên no-CORS có CORP phù hợp và tài nguyên CORS có ACAO đúng.
- Không dùng CORP thay frame-ancestors, XFO, CSRF hoặc authorization.
- Bảo vệ endpoint bằng authentication, authorization, cache policy và rate limit độc lập.
- Đánh giá kỹ sibling subdomain, user uploads và tài nguyên đa tenant trước khi chọn same-site.
- Kiểm tra CDN/object storage/reverse proxy để header có mặt trên response cuối.
- Kiểm thử browser mục tiêu, Console, Network, cache hit và crossOriginIsolated.
- Theo dõi lỗi tài nguyên sau rollout; không mở rộng policy quá mức chỉ để làm hết lỗi.

## 23. Câu hỏi tự kiểm tra

1. CORP là response header của bên nào: trang nhúng hay tài nguyên được tải?
2. CORP chủ yếu được kiểm tra với request mode nào?
3. same-origin, same-site và cross-origin khác nhau như thế nào?
4. Vì sao hai subdomain HTTPS có thể same-site nhưng khác origin?
5. Vì sao CORP cross-origin không cho JavaScript đọc response?
6. Khi nào cần CORS thay vì CORP?
7. COEP require-corp yêu cầu gì ở tài nguyên cross-origin?
8. Vì sao CORP không ngăn iframe navigation hoặc clickjacking?
9. Vì sao CORP không thay authentication và authorization?
10. Khi tài nguyên bị chặn, cần kiểm tra những header và thông tin request nào trong DevTools?

**Ghi nhớ:** CORP cho phép server của tài nguyên giới hạn việc browser sử dụng response trong request cross-origin no-CORS. Chọn `same-origin` cho ranh giới chặt, `same-site` khi các subdomain thực sự cùng mức tin cậy, và `cross-origin` cho tài nguyên cần chia sẻ công khai. CORP không cấp quyền CORS, không chặn mọi request mạng, không thay frame protection và không thay authorization. Khi dùng COEP require-corp, kiểm tra từng tài nguyên cross-origin, request mode và response header ở browser thực tế.
