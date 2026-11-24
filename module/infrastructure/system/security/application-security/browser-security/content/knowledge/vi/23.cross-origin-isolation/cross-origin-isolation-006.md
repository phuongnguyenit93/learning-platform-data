# Cross-origin resource policy

## 1. Vì sao browser cần Cross-Origin Resource Policy?

Một trang web có thể yêu cầu tài nguyên từ origin khác: ảnh, font, script, stylesheet, video, tài liệu hoặc dữ liệu. Same-Origin Policy (SOP) giới hạn việc JavaScript đọc trực tiếp response và DOM từ origin khác, nhưng browser vẫn cho phép nhiều loại tài nguyên cross-origin được nhúng hoặc tải theo các chế độ nhất định.

Điều này tạo ra một rủi ro riêng: một trang độc hại có thể cố tải tài nguyên từ website khác bằng request mà JavaScript không được đọc response. Trong một số tình huống, việc tải tài nguyên vẫn có thể làm lộ thông tin qua các kênh phụ hoặc khai thác hành vi của browser. **Cross-Origin Resource Policy (CORP)** giúp chủ sở hữu tài nguyên nói rõ origin/site nào được phép nhúng tài nguyên đó trong các request cross-origin kiểu `no-cors`.

CORP là một **response header** do server của tài nguyên gửi về. Browser đọc header và quyết định có cho phép document khác origin sử dụng response trong ngữ cảnh request hiện tại hay không.

Ví dụ server có thể trả:

```http
Cross-Origin-Resource-Policy: same-origin
```

Điều này thể hiện tài nguyên chỉ được sử dụng bởi document cùng origin trong những trường hợp CORP áp dụng. Một trang ở origin khác không thể đơn giản nhúng tài nguyên đó bằng một request `no-cors`.

CORP là một phần của hệ sinh thái cross-origin isolation, cùng với CORS, COEP và COOP. Các cơ chế này có mục tiêu và vị trí áp dụng khác nhau. Hiểu đúng vai trò của từng header giúp triển khai chính sách vừa bảo vệ tài nguyên vừa không làm hỏng các luồng nhúng hợp lệ.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích mục đích của Cross-Origin Resource Policy và vị trí của nó trong browser.
2. Phân biệt `same-origin`, `same-site` và `cross-origin`.
3. Xác định request `no-cors` và vai trò của CORP đối với tài nguyên được nhúng.
4. Phân biệt CORP với CORS, COEP và COOP.
5. Chọn policy phù hợp cho tài nguyên riêng tư, tài nguyên dùng chung trong site và tài nguyên công khai.
6. Hiểu cách CORP phối hợp với COEP khi bật cross-origin isolation.
7. Kiểm tra header và chẩn đoán lỗi tải tài nguyên trong DevTools.

## 2. CORP bảo vệ điều gì?

### 2.1. SOP không đồng nghĩa với việc chặn mọi request cross-origin

Browser thường cho phép trang tải một số tài nguyên cross-origin, dù JavaScript không được đọc response tùy ý. Ví dụ, một trang có thể hiển thị ảnh từ origin khác bằng phần tử img. Một classic script có thể được tải bằng script src, tùy chính sách của server và browser.

Điều này có nghĩa:

- Có thể gửi request cross-origin.
- Browser có thể sử dụng response cho một mục đích cụ thể, ví dụ giải mã và hiển thị ảnh.
- JavaScript thường không được đọc nội dung response của một request no-cors.
- Việc không đọc được response không loại bỏ mọi nguy cơ rò rỉ dữ liệu cross-origin.

CORP cho phép server tài nguyên giới hạn việc browser sử dụng response trong các request no-cors cross-origin. Mục tiêu quan trọng là giảm khả năng một site khác nhúng tài nguyên nhạy cảm và suy luận thông tin qua các hành vi phụ của browser.

### 2.2. Request mode là chi tiết quan trọng

Fetch API có các request mode như same-origin, cors và no-cors.

| Mode | Hành vi khái quát | Quan hệ với CORP |
| --- | --- | --- |
| same-origin | Request chỉ được gửi tới cùng origin; cross-origin bị chặn | Không phải đường tải cross-origin để CORP cấp quyền |
| cors | Browser dùng CORS protocol; server cần cho phép origin qua response header | CORS quyết định JavaScript có được đọc response; CORP không thay thế CORS |
| no-cors | Một số request cross-origin được phép nhưng response bị giới hạn/opaque với JavaScript | Đây là ngữ cảnh chính mà CORP dùng để giới hạn việc nhúng tài nguyên cross-origin |

Nhiều HTML element tạo request no-cors theo mặc định nếu không bật chế độ CORS, ví dụ ảnh hoặc classic script trong một số trường hợp. Hành vi chính xác phụ thuộc loại tài nguyên, thuộc tính crossorigin, request destination và browser.

### 2.3. CORP là chính sách trên response

Server tài nguyên gửi header CORP cùng response:

```http
HTTP/1.1 200 OK
Content-Type: image/png
Cross-Origin-Resource-Policy: same-origin
```

Browser kiểm tra policy này khi xử lý request phù hợp. Đây không phải một request header mà client tự khai báo để xin quyền, cũng không phải CORS preflight.

CORP không thay thế authentication hay authorization. Nếu endpoint chứa dữ liệu riêng tư, server vẫn phải xác thực người dùng và kiểm tra quyền truy cập. CORP là một lớp bảo vệ bổ sung ở browser.

Phạm vi của CORP cũng có giới hạn: nó chủ yếu kiểm soát response cho request cross-origin ở mode no-cors. Nó không phải bộ lọc mạng cho mọi loại request, không thay thế CORS cho request mode cors và không phải chính sách chặn điều hướng top-level. Các HTTP client ngoài browser cũng có thể không thực thi header này.

## 3. Ba giá trị của Cross-Origin-Resource-Policy

CORP có ba giá trị chính:

- same-origin
- same-site
- cross-origin

### 3.1. same-origin

```http
Cross-Origin-Resource-Policy: same-origin
```

Chỉ cho phép sử dụng response trong các ngữ cảnh CORP áp dụng khi requester cùng origin với tài nguyên.

Origin được xác định bởi scheme, host và port. Vì vậy:

| Trang yêu cầu | Tài nguyên | Cùng origin? |
| --- | --- | --- |
| https://app.example.com | https://app.example.com/avatar.png | Có |
| https://app.example.com | https://app.example.com:8443/avatar.png | Không |
| https://app.example.com | http://app.example.com/avatar.png | Không |
| https://app.example.com | https://cdn.example.com/avatar.png | Không |

Đây thường là lựa chọn phù hợp cho tài nguyên nội bộ không có nhu cầu được nhúng từ origin khác, ví dụ response chứa dữ liệu cá nhân hoặc tài nguyên chỉ dành cho chính ứng dụng.

### 3.2. same-site

```http
Cross-Origin-Resource-Policy: same-site
```

Cho phép requester thuộc cùng site với tài nguyên, kể cả khi hai bên khác origin. Giá trị này hữu ích khi ứng dụng dùng nhiều subdomain có cùng ranh giới tin cậy, ví dụ:

- https://app.example.com
- https://static.example.com
- https://media.example.com

Các origin trên khác nhau, nhưng có thể cùng schemeful site.

Khái niệm site không giống origin. Trong cách tính schemeful site, scheme và registrable domain là các thành phần quan trọng; port không tham gia phép so sánh site. Vì vậy, hai origin khác port có thể cùng site, trong khi http://example.com và https://example.com là khác schemeful site.

**Cảnh báo:** same-site rộng hơn same-origin. Nếu một subdomain cho phép người dùng tự lưu nội dung, chạy ứng dụng không tin cậy hoặc bị bên thứ ba kiểm soát, tài nguyên đặt same-site có thể được nhúng từ subdomain đó. Chỉ dùng same-site khi mọi origin cùng site đều nằm trong ranh giới tin cậy đã đánh giá.

### 3.3. cross-origin

```http
Cross-Origin-Resource-Policy: cross-origin
```

Cho phép browser sử dụng response trong các request cross-origin thuộc phạm vi CORP. Đây có thể là lựa chọn cho tài nguyên công khai, được thiết kế để nhúng từ website khác, ví dụ hình ảnh công khai hoặc một số tài nguyên CDN.

cross-origin không có nghĩa là JavaScript trên mọi origin được đọc response. Nếu request dùng CORS mode, CORS vẫn cần được cấu hình để JavaScript đọc dữ liệu. CORP cross-origin chỉ thể hiện rằng tài nguyên không từ chối việc sử dụng trong các ngữ cảnh cross-origin mà CORP điều khiển.

### 3.4. Bảng so sánh

| Policy | Ai được phép theo CORP? | Ví dụ sử dụng |
| --- | --- | --- |
| same-origin | Cùng scheme, host và port | Tài nguyên riêng của một ứng dụng |
| same-site | Cùng schemeful site, có thể khác subdomain/port | Các subdomain cùng tổ chức và cùng ranh giới tin cậy |
| cross-origin | Origin khác cũng được phép trong ngữ cảnh CORP | Tài nguyên công khai dành cho nhúng cross-origin |

Chọn policy theo chủ sở hữu và mục đích của từng tài nguyên. Không nên đặt cross-origin trên toàn bộ website chỉ để sửa một lỗi tải ảnh hoặc font.

## 4. CORP và CORS giải quyết hai vấn đề khác nhau

Hai header thường bị nhầm lẫn vì cùng có từ “cross-origin”, nhưng chúng có vai trò khác nhau.

### 4.1. CORS: cho phép JavaScript đọc response

CORS (Cross-Origin Resource Sharing) là cơ chế browser dùng để quyết định JavaScript có được phép đọc response của request cross-origin hay không. Server thể hiện quyền bằng header như:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Ví dụ JavaScript gọi:

```js
const response = await fetch("https://api.example.com/profile", {
  mode: "cors"
});

const profile = await response.json();
```

Để JavaScript đọc response, server phải trả CORS header phù hợp. Nếu không, browser chặn quyền truy cập response cho script.

### 4.2. CORP: giới hạn việc sử dụng response trong request no-cors

CORP không cấp quyền cho JavaScript đọc response. Nó cho phép server tài nguyên từ chối việc nhúng response trong các request no-cors từ site/origin khác.

Ví dụ một ảnh có:

```http
Cross-Origin-Resource-Policy: same-origin
```

Một trang ở origin khác có thể gửi request ảnh, nhưng browser sẽ chặn việc sử dụng response theo CORP. Nếu response không có CORP hoặc có policy cho phép, ảnh có thể được hiển thị; JavaScript vẫn không tự động được đọc bytes ảnh hoặc response body.

### 4.3. So sánh trực tiếp

| Câu hỏi | CORS | CORP |
| --- | --- | --- |
| Header nằm ở đâu? | Response của server tài nguyên | Response của server tài nguyên |
| Mục tiêu | Cho phép origin khác đọc response bằng API CORS | Giới hạn nhúng/sử dụng tài nguyên trong request no-cors cross-origin |
| Kiểm tra chính | Access-Control-Allow-Origin và các CORS headers | Cross-Origin-Resource-Policy |
| Có làm JavaScript đọc response được không? | Có, nếu CORS thành công | Không |
| Có thay thế nhau không? | Không | Không |

### 4.4. crossorigin attribute không phải CORP

Một số HTML element hỗ trợ thuộc tính crossorigin, ví dụ:

```html
<img src="https://cdn.example.com/photo.png" crossorigin="anonymous" alt="Ảnh">
<script src="https://cdn.example.com/app.js" crossorigin="anonymous"></script>
```

Thuộc tính này khiến browser sử dụng chế độ CORS phù hợp cho request của element. Server cần trả CORS header tương ứng. Nó không yêu cầu server gửi Cross-Origin-Resource-Policy, và không thay thế CORP trong request no-cors.

Với module script, CORS mode được sử dụng theo quy tắc của module loading; server cần cấu hình CORS phù hợp. Đừng áp dụng quy tắc của classic script cho module script mà không kiểm tra request mode thực tế.
## 5. CORP phối hợp với COEP như thế nào?

### 5.1. COEP là chính sách của document nhúng tài nguyên

Cross-Origin-Embedder-Policy (COEP) là response header của document hoặc worker, kiểm soát việc document đó có được phép nhúng tài nguyên cross-origin hay không.

Một policy phổ biến:

```http
Cross-Origin-Embedder-Policy: require-corp
```

Khi document dùng require-corp, các tài nguyên cross-origin phải thể hiện quyền cho phép theo cơ chế phù hợp:

- Request dùng CORS mode: tài nguyên phải đáp ứng CORS.
- Request dùng no-cors: tài nguyên cần CORP cho phép, ví dụ cross-origin hoặc policy same-site phù hợp với requester.

Như vậy:

- CORP là lựa chọn của **server tài nguyên**.
- COEP là lựa chọn của **document đang nhúng tài nguyên**.
- CORS là giao thức cho phép script đọc response cross-origin.

### 5.2. Ví dụ một document dùng COEP require-corp

Response của trang ứng dụng:

```http
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
```

Response của một ảnh công khai ở CDN được nhúng bằng no-cors:

```http
Cross-Origin-Resource-Policy: cross-origin
Content-Type: image/png
```

Response của API mà JavaScript đọc bằng CORS:

```http
Access-Control-Allow-Origin: https://app.example.com
Content-Type: application/json
```

Trong thiết kế này, ảnh công khai opt-in bằng CORP; API opt-in bằng CORS. Tài nguyên cross-origin không có cơ chế opt-in phù hợp có thể bị COEP chặn.

### 5.3. credentialless

COEP có một lựa chọn khác:

```http
Cross-Origin-Embedder-Policy: credentialless
```

Với các request cross-origin no-cors, browser có thể tải tài nguyên mà không gửi credentials, thay vì yêu cầu tài nguyên phải cấp quyền bằng CORP như require-corp. Vì cookie và HTTP authentication không được gửi theo cách thông thường trong request này, tài nguyên phụ thuộc phiên đăng nhập có thể trả nội dung khác. Đây là một chế độ có semantics riêng; không hiểu nó như “bỏ qua mọi kiểm soát cross-origin”.

Request CORS vẫn tuân theo CORS. Ứng dụng cần kiểm tra hỗ trợ browser và hành vi cache/credentials theo môi trường triển khai trước khi chọn credentialless.

### 5.4. Vì sao cần cross-origin isolation?

Một số API nhạy cảm về timing hoặc bộ nhớ, đáng chú ý là SharedArrayBuffer trong các browser hiện đại, yêu cầu document ở trạng thái cross-origin isolated. Một cấu hình phổ biến là kết hợp:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Hoặc dùng COEP credentialless nếu phù hợp. Browser cung cấp thuộc tính:

```js
if (crossOriginIsolated) {
  console.log("Document đang cross-origin isolated");
}
```

CORP một mình không bật cross-origin isolation. Nó chỉ là một trong những cách để tài nguyên opt-in khi document áp dụng COEP require-corp.

## 6. Phân biệt CORP, COEP và COOP

| Cơ chế | Đặt trên response của | Vai trò chính |
| --- | --- | --- |
| CORP | Tài nguyên được tải | Quyết định tài nguyên có cho phép được dùng trong request no-cors cross-origin |
| COEP | Document hoặc worker đang nhúng tài nguyên | Yêu cầu tài nguyên cross-origin opt-in bằng CORS hoặc CORP, tùy request mode |
| COOP | Document cấp top-level browsing context | Tách browsing context group/opener relationship theo policy |
| CORS | Tài nguyên/API được JavaScript gọi | Cho phép JavaScript đọc response cross-origin khi kiểm tra CORS thành công |

COOP không phải header cấp quyền nhúng ảnh hay script. Nó kiểm soát quan hệ giữa browsing context, ví dụ cửa sổ mở popup. COEP không phải header của ảnh để xin phép được nhúng. CORP không phải CORS và không cho JavaScript đọc response.

Một hệ thống có thể cần nhiều header cùng lúc, nhưng mỗi header phải được đặt trên đúng loại response và đúng mục tiêu.

## 7. Chọn policy CORP theo loại tài nguyên

### 7.1. Tài nguyên nội bộ hoặc dữ liệu riêng

Với ảnh đại diện riêng tư, file tải về theo phiên, response chứa thông tin người dùng hoặc tài nguyên chỉ ứng dụng chính được phép nhúng, cân nhắc:

```http
Cross-Origin-Resource-Policy: same-origin
```

Đây không phải cơ chế xác thực. Nếu URL ảnh có thể truy cập công khai mà không cần session, CORP không thay thế việc bảo vệ endpoint. Server vẫn phải quyết định người dùng có quyền tải tài nguyên.

### 7.2. Tài nguyên dùng chung giữa các subdomain

Nếu app.example.com cần nhúng ảnh từ media.example.com, có thể cân nhắc:

```http
Cross-Origin-Resource-Policy: same-site
```

Chỉ chọn khi tất cả subdomain có thể gửi request đều thuộc cùng ranh giới tin cậy. Nếu có subdomain dành cho nội dung người dùng, môi trường thử nghiệm hoặc dịch vụ do bên thứ ba quản lý, đánh giá kỹ nguy cơ trước khi cho phép toàn bộ same-site.

Nếu chỉ một origin cần quyền, same-origin có thể quá chặt; khi đó hãy cân nhắc kiến trúc CORS hoặc phân phối tài nguyên qua origin được kiểm soát riêng thay vì mặc định tin toàn site.

### 7.3. Tài nguyên công khai

Với ảnh hoặc tài nguyên được thiết kế để nhúng công khai từ nhiều website, có thể trả:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Nếu JavaScript ở website khác cần đọc bytes hoặc response body, cần cấu hình CORS riêng. CORP cross-origin không tự cấp quyền đọc cho fetch() ở CORS mode.

### 7.4. Ma trận tham khảo

| Tài nguyên | Policy gợi ý ban đầu | Câu hỏi cần xác minh |
| --- | --- | --- |
| JSON riêng của tài khoản | same-origin | Endpoint có thực sự cần được nhúng cross-origin không? |
| Avatar riêng tư | same-origin | Quyền tải ảnh có được kiểm tra ở server không? |
| Ảnh dùng chung giữa các subdomain tin cậy | same-site | Mọi subdomain có cùng ranh giới tin cậy không? |
| Ảnh public trên CDN | cross-origin | Có website nào cũng được phép nhúng không? |
| API cho frontend bên ngoài đọc dữ liệu | CORS phù hợp; CORP đánh giá riêng | Origin nào được phép đọc và credentials có cần không? |
| Font công khai | Theo cách tải và COEP của trang tiêu thụ | Request dùng CORS hay no-cors? Server có CORS/CORP tương ứng không? |

Không có một giá trị CORP mặc định phù hợp cho tất cả tài nguyên. Hãy phân loại theo tính riêng tư, nhu cầu nhúng và ranh giới tin cậy.

## 8. Cấu hình header trên server

CORP là response header, vì vậy hãy cấu hình tại application server, reverse proxy, CDN hoặc storage service thực sự trả tài nguyên. Cần đảm bảo header xuất hiện trên response cuối cùng mà browser nhận được.

### 8.1. Node.js HTTP server

```js
const http = require("node:http");

http.createServer((req, res) => {
  if (req.url === "/private/avatar.png") {
    res.writeHead(200, {
      "Content-Type": "image/png",
      "Cross-Origin-Resource-Policy": "same-origin"
    });
    // Trả bytes ảnh từ storage đã xác thực quyền ở server.
    res.end(imageBytes);
    return;
  }

  res.writeHead(404);
  res.end("Not found");
}).listen(8080);
```

Đây là ví dụ minh họa header. Trong ứng dụng thật, imageBytes phải được đọc từ storage và authorization phải được kiểm tra trước khi trả dữ liệu.

### 8.2. Express middleware

```js
function setCorp(policy) {
  const allowed = new Set(["same-origin", "same-site", "cross-origin"]);
  if (!allowed.has(policy)) {
    throw new Error("CORP policy không hợp lệ");
  }

  return (_req, res, next) => {
    res.setHeader("Cross-Origin-Resource-Policy", policy);
    next();
  };
}

// Áp dụng riêng cho nhóm tài nguyên.
app.use("/private-assets", authenticate, setCorp("same-origin"), privateAssetRouter);
app.use("/public-assets", setCorp("cross-origin"), publicAssetRouter);
```

Không nên gắn cùng một policy cho mọi route nếu ứng dụng phục vụ cả tài nguyên riêng và công khai. Middleware cần được đặt đúng thứ tự và không để route xử lý response trước khi header được thêm.

### 8.3. Nginx

Ví dụ header cho một location:

```nginx
location /private-assets/ {
    add_header Cross-Origin-Resource-Policy "same-origin" always;
}
```

Từ khóa always giúp header được thêm trên nhiều loại response status theo cấu hình Nginx. Kiểm tra header thực tế sau reverse proxy/CDN vì một tầng khác có thể xóa hoặc ghi đè header.

### 8.4. CDN và object storage

Nếu tài nguyên được phục vụ từ CDN hoặc object storage:

- Cấu hình response metadata hoặc edge response header phù hợp.
- Kiểm tra header sau cache hit và cache miss.
- Đảm bảo mọi biến thể response đều có policy mong muốn.
- Không để CDN gộp response có policy khác nhau vào cùng cache key nếu nội dung/policy phụ thuộc request.
- Khi đổi policy, purge hoặc version cache nếu response cũ còn được phân phối.

## 9. Các lỗi cấu hình thường gặp

### 9.1. Dùng same-site như thể nó là same-origin

Hai subdomain cùng site vẫn có thể được kiểm soát bởi nhóm khác nhau. Nếu một subdomain nhận nội dung không tin cậy, same-site có thể cho phép tài nguyên nội bộ được nhúng từ nơi không mong muốn.

Hãy kiểm kê subdomain, chủ sở hữu, quy trình deploy, upload và khả năng chạy nội dung trước khi chọn same-site.

### 9.2. Dùng cross-origin cho mọi thứ

Header cross-origin làm tài nguyên opt-in cho việc sử dụng cross-origin trong ngữ cảnh CORP. Đặt nó trên response chứa dữ liệu riêng tư hoặc tài nguyên không cần chia sẻ sẽ làm mất một lớp bảo vệ.

Phân loại route theo mục đích và chọn policy riêng.

### 9.3. Nghĩ CORP cho phép JavaScript đọc response

CORP cross-origin không thay CORS. Một fetch() ở mode cors vẫn cần Access-Control-Allow-Origin phù hợp. Một fetch() ở mode no-cors vẫn trả opaque response cho JavaScript, dù tài nguyên được phép tải.

### 9.4. Chỉ thêm CORP vào trang nhúng

CORP phải được trả bởi **server của tài nguyên**. Thêm header vào HTML document nhúng không quyết định policy của ảnh hoặc script từ server khác.

Ngược lại, COEP được đặt trên document đang nhúng. Cần phân biệt header của bên cung cấp tài nguyên và header của bên tiêu thụ.

### 9.5. Nghĩ CORP là authentication

CORP là browser-enforced policy, không phải kiểm soát truy cập cho mọi client. curl, ứng dụng mobile, server-to-server hoặc một HTTP client tùy chỉnh có thể không thực thi CORP. Endpoint nhạy cảm vẫn cần authentication và authorization ở server.

### 9.6. Quên request mode của tài nguyên

Nếu một element chuyển từ no-cors sang CORS mode bằng thuộc tính crossorigin, yêu cầu thay đổi: CORS header cần thiết để browser chấp nhận response. Không nên chẩn đoán mọi lỗi cross-origin bằng cách thêm CORP.

Kiểm tra request mode, destination và response header trong DevTools trước khi đổi cấu hình.
## 10. Thực hành: kiểm tra CORP trên hai origin local

Bài lab tạo hai server local:

- Ứng dụng tại http://127.0.0.1:8000.
- Server tài nguyên tại http://127.0.0.1:8001.

Khác port tạo ra hai origin khác nhau. Trang ứng dụng tải một ảnh SVG từ server tài nguyên. Ta thay đổi CORP header của response ảnh để quan sát browser.

### 10.1. Tạo server tài nguyên tại port 8001

Tạo file resource-server.js:

```js
const http = require("node:http");
const { URL } = require("node:url");

http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8001");

  if (url.pathname !== "/pixel.svg") {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  const allowedPolicies = new Set([
    "same-origin",
    "same-site",
    "cross-origin"
  ]);
  const corp = url.searchParams.get("corp") || "same-origin";

  if (!allowedPolicies.has(corp)) {
    res.writeHead(400);
    res.end("Invalid CORP value");
    return;
  }

  const headers = {
    "Content-Type": "image/svg+xml; charset=utf-8",
    "Cross-Origin-Resource-Policy": corp,
    "Cache-Control": "no-store"
  };

  if (url.searchParams.get("cors") === "1") {
    headers["Access-Control-Allow-Origin"] = "http://127.0.0.1:8000";
  }

  res.writeHead(200, headers);
  res.end(
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="80">' +
    '<rect width="160" height="80" fill="#2878c8"/>' +
    '<text x="12" y="46" fill="white" font-size="16">CORP test</text>' +
    '</svg>'
  );
}).listen(8001, "127.0.0.1", () => {
  console.log("Resource server: http://127.0.0.1:8001");
});
```

### 10.2. Tạo trang ứng dụng tại port 8000

Tạo file app-server.js:

```js
const http = require("node:http");

const html = `<!doctype html>
<meta charset="utf-8">
<title>CORP local lab</title>
<h1>Cross-Origin Resource Policy lab</h1>
<p>Trang này chạy ở 127.0.0.1:8000; tài nguyên ở 127.0.0.1:8001.</p>
<img
  id="corp-image"
  src="http://127.0.0.1:8001/pixel.svg?corp=same-origin"
  alt="CORP test">
<p>
  <button id="same-origin">CORP same-origin</button>
  <button id="same-site">CORP same-site</button>
  <button id="cross-origin">CORP cross-origin</button>
</p>
<p>
  <button id="no-cors">Fetch no-cors</button>
  <button id="cors">Fetch CORS</button>
</p>
<pre id="result">Chưa kiểm tra</pre>
<script>
  const image = document.querySelector("#corp-image");
  const result = document.querySelector("#result");
  const resource = "http://127.0.0.1:8001/pixel.svg";

  document.querySelector("#same-origin").onclick = () => {
    image.src = resource + "?corp=same-origin";
  };
  document.querySelector("#same-site").onclick = () => {
    image.src = resource + "?corp=same-site";
  };
  document.querySelector("#cross-origin").onclick = () => {
    image.src = resource + "?corp=cross-origin";
  };

  document.querySelector("#no-cors").addEventListener("click", async () => {
    try {
      const response = await fetch(resource + "?corp=cross-origin", {
        mode: "no-cors"
      });
      result.textContent =
        "type=" + response.type + ", status=" + response.status;
    } catch (error) {
      result.textContent = String(error);
    }
  });

  document.querySelector("#cors").addEventListener("click", async () => {
    try {
      const response = await fetch(resource + "?corp=same-origin&cors=1", {
        mode: "cors"
      });
      result.textContent =
        "type=" + response.type + ", status=" + response.status;
    } catch (error) {
      result.textContent = String(error);
    }
  });
</script>`;

http.createServer((_req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(html);
}).listen(8000, "127.0.0.1", () => {
  console.log("App server: http://127.0.0.1:8000");
});
```

Hai file dùng các thao tác local vô hại để quan sát browser policy. Chạy mỗi file trong terminal riêng:

```powershell
node resource-server.js
node app-server.js
```

Mở http://127.0.0.1:8000 trong browser.

### 10.3. Quan sát kết quả

- Ban đầu ảnh dùng same-origin, nên browser chặn việc trang 127.0.0.1:8000 sử dụng response từ 127.0.0.1:8001.
- Chọn same-site: hai URL cùng scheme và host 127.0.0.1 nhưng khác port; chúng khác origin và cùng schemeful site, vì vậy policy same-site cho phép ảnh.
- Chọn cross-origin: ảnh được phép nhúng cross-origin.
- Chọn Fetch no-cors: response có kiểu opaque; JavaScript không đọc được status/body thực như một CORS response.
- Chọn Fetch CORS: server gửi Access-Control-Allow-Origin phù hợp nên JavaScript đọc được response; CORP không thay CORS.

Trong DevTools → Network, chọn request pixel.svg và xem:

1. Request URL và Initiator.
2. Response header Cross-Origin-Resource-Policy.
3. Response header Access-Control-Allow-Origin khi chọn CORS fetch.
4. Console message khi CORP chặn response.
5. Request mode và response type khi kiểm tra fetch.

Nếu browser hoặc cấu hình local có cách tính site đặc biệt, hãy ưu tiên quan sát header và hành vi same-origin/cross-origin; không suy luận same-site chỉ từ việc hai URL nhìn gần giống nhau.

## 11. Ma trận kiểm thử CORP và COEP

| Mã | Request/response | Kết quả mong muốn |
| --- | --- | --- |
| CORP-01 | no-cors cross-origin + same-origin | Browser chặn sử dụng response |
| CORP-02 | no-cors same-origin + same-origin | Tài nguyên được sử dụng |
| CORP-03 | no-cors same-site + same-site | Tài nguyên được sử dụng |
| CORP-04 | no-cors cross-site + same-site | Browser chặn sử dụng response |
| CORP-05 | no-cors cross-origin + cross-origin | Tài nguyên được sử dụng |
| CORP-06 | CORS mode + CORS header hợp lệ | JavaScript đọc response nếu các kiểm tra CORS khác thành công |
| CORP-07 | CORS mode thiếu CORS header | JavaScript không được đọc response |
| CORP-08 | no-cors response opaque | JavaScript không đọc được body/status như response CORS |
| CORP-09 | COEP require-corp + no-cors resource thiếu opt-in | Document chặn resource |
| CORP-10 | COEP require-corp + no-cors resource có CORP phù hợp | Resource có thể được nhúng |
| CORP-11 | COEP require-corp + CORS resource được cấp quyền | Resource có thể được tải theo CORS |
| CORP-12 | Header bị mất sau CDN | Hành vi khác với cấu hình origin; cần sửa tầng phân phối |
| CORP-13 | Resource công khai có cross-origin | Website ngoài có thể nhúng trong ngữ cảnh CORP |
| CORP-14 | Endpoint riêng chỉ dựa vào CORP | Vẫn phải có authentication/authorization server-side |

## 12. Quy trình triển khai trong production

1. **Lập danh mục tài nguyên:** phân loại ảnh, font, script, stylesheet, API, file tải về và dữ liệu cá nhân.
2. **Xác định chủ sở hữu và nhu cầu nhúng:** tài nguyên chỉ dùng nội bộ, dùng chung trong site hay công khai.
3. **Đánh giá ranh giới site:** kiểm kê subdomain, host do bên thứ ba quản lý, user-generated content và môi trường staging.
4. **Chọn policy tối thiểu:** ưu tiên same-origin cho tài nguyên nội bộ; chỉ mở same-site hoặc cross-origin khi có nhu cầu đã xác minh.
5. **Triển khai ở đúng response:** đặt CORP tại application, storage hoặc CDN phục vụ tài nguyên.
6. **Kiểm tra COEP:** nếu document dùng require-corp, xác nhận mọi tài nguyên cross-origin opt-in bằng CORS hoặc CORP đúng request mode.
7. **Kiểm tra browser thực tế:** xác nhận request mode, response header và Console/Network.
8. **Theo dõi lỗi sau release:** đặc biệt ảnh, font, script và widget được tải từ CDN hoặc subdomain.
9. **Rà soát khi thêm subdomain/nhà cung cấp:** thay đổi ranh giới site có thể làm policy same-site rộng hơn dự kiến.

CORP không có chế độ Report-Only tương đương CSP. Để thử nghiệm, có thể triển khai trên một route/staging resource trước, kiểm tra hành vi thực tế và theo dõi lỗi trước khi áp dụng rộng.

## 13. Những nhận định sai thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| CORP và CORS là một | CORS cấp quyền đọc response; CORP giới hạn sử dụng response trong request no-cors cross-origin |
| same-site giống same-origin | Same-site có thể gồm nhiều subdomain và port khác nhau |
| cross-origin cho phép mọi JavaScript đọc response | Không; CORS vẫn quyết định quyền đọc response trong CORS mode |
| Chỉ cần CORP trên trang HTML | CORP phải được trả bởi server của tài nguyên |
| COEP và CORP là cùng một header | COEP đặt trên document/worker; CORP đặt trên resource |
| CORP bảo vệ endpoint khỏi mọi client | Browser thực thi; client không phải browser có thể bỏ qua |
| CORP thay authentication | Server vẫn phải xác thực và kiểm tra quyền |
| Thêm crossorigin là bật CORP | crossorigin chuyển request sang CORS mode; không phải CORP response header |
| CORP một mình bật cross-origin isolation | Cần COOP và COEP phù hợp cùng các điều kiện khác |
| Tất cả resource cross-origin đều dùng no-cors | Request mode phụ thuộc loại tài nguyên và thuộc tính tải |

## 14. Checklist

- [ ] Xác định tài nguyên nào cần CORP và tài nguyên nào cần CORS.
- [ ] Phân loại từng resource là riêng tư, dùng chung same-site hay công khai.
- [ ] Dùng same-origin khi chỉ ứng dụng cùng origin cần sử dụng tài nguyên.
- [ ] Chỉ dùng same-site khi tất cả subdomain liên quan đều đáng tin cậy.
- [ ] Chỉ dùng cross-origin cho tài nguyên thực sự được phép nhúng công khai.
- [ ] Kiểm tra request mode (no-cors, cors, same-origin) trong DevTools.
- [ ] Không dùng CORP thay cho CORS, authentication hoặc authorization.
- [ ] Nếu bật COEP require-corp, kiểm tra tất cả tài nguyên cross-origin.
- [ ] Đặt header ở server thực sự trả tài nguyên và xác minh sau CDN/proxy.
- [ ] Kiểm tra cache hit/miss và các response status.
- [ ] Kiểm thử các browser mục tiêu, đặc biệt luồng ảnh, font, script và iframe.
- [ ] Rà soát lại policy khi thêm subdomain hoặc nhà cung cấp tài nguyên.

### Ghi nhớ

**CORP là response policy của tài nguyên, dùng để giới hạn việc browser nhúng response trong request no-cors cross-origin.** same-origin giới hạn theo origin chính xác; same-site mở rộng tới các origin cùng schemeful site; cross-origin cho phép nhúng từ origin khác trong ngữ cảnh CORP. CORS vẫn là cơ chế cho phép JavaScript đọc response. COEP là chính sách của document nhúng tài nguyên, còn COOP điều khiển quan hệ browsing context. Chọn CORP theo ranh giới tin cậy thực tế, đặt header ở đúng server tài nguyên và vẫn bảo vệ endpoint bằng authentication, authorization cùng các lớp bảo mật khác.
