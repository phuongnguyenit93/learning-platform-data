# Mode no-cors

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích `mode: "no-cors"` điều khiển loại request và response như thế nào trong Fetch API.
- Nhận biết giới hạn method, request header và body khi gửi no-cors request.
- Đọc đúng đặc điểm của opaque response và hiểu vì sao JavaScript không thể đọc status, header hoặc body của response cross-origin này.
- Phân biệt `no-cors` với `cors`, `same-origin` và hành vi cross-origin của XMLHttpRequest.
- Đánh giá use case hợp lý trong service worker/Cache API và các rủi ro CSRF, cache dữ liệu sai hoặc hiểu nhầm response.
- Kiểm chứng request bằng DevTools và chọn giải pháp phù hợp khi ứng dụng cần đọc dữ liệu từ origin khác.

## 1. `mode` trong Fetch API là gì?

Fetch API dùng thuộc tính `mode` để xác định cách một request tương tác với ranh giới origin và response được phép đưa về JavaScript ở dạng nào. Các giá trị thường gặp gồm:

| Mode | Ý nghĩa |
| --- | --- |
| `cors` | Cho phép request cross-origin theo cơ chế CORS. Nếu server cho phép origin của trang, JavaScript có thể đọc response theo các quy tắc CORS. Đây là mode mặc định của `fetch()` khi không chỉ định mode. |
| `same-origin` | Chỉ cho phép request cùng origin. Request đến origin khác bị từ chối. |
| `no-cors` | Cho phép một số request cross-origin bị giới hạn. Với response cross-origin, JavaScript nhận opaque response và không đọc được nội dung hoặc metadata HTTP. |
| `navigate` | Dành cho request điều hướng do trình duyệt tạo; không phải mode để ứng dụng tùy ý đặt cho một lệnh `fetch()`. |

Origin được xác định bởi bộ ba scheme, host và port. Ví dụ `https://app.example.com` và `https://api.example.com` là hai origin khác nhau dù có cùng domain gốc. `https://app.example.com` và `http://app.example.com` cũng khác origin.

Một request `no-cors` không cấp thêm quyền đọc dữ liệu cross-origin. Nó cho phép trình duyệt thực hiện một loại request bị giới hạn và giữ response ở trạng thái opaque. Vì thế, không nên xem `no-cors` là cách tắt Same-Origin Policy hoặc cách sửa lỗi CORS.

## 2. Gửi một request no-cors

Có thể đặt mode trong `RequestInit`:

```js
const response = await fetch("https://static.example.net/banner.png", {
  method: "GET",
  mode: "no-cors"
});

console.log(response.type);
console.log(response.status);
console.log(response.ok);
```

Với response cross-origin ở mode này, kết quả thường là:

```text
type   = "opaque"
status = 0
ok     = false
```

`fetch()` vẫn có thể resolve thành công với một opaque response. `status: 0` không có nghĩa server trả HTTP status 0; đó là giá trị được API dùng để che status thật. `ok` là `false` vì status không nằm trong khoảng 200–299. JavaScript cũng không thể đọc header hoặc body của response opaque.

Trong bài toán cross-origin, chính `no-cors` khiến response bị giữ ở dạng opaque. Nếu ứng dụng cần đọc dữ liệu, hãy chọn `cors` và cấu hình server chia sẻ response theo CORS.

Có thể kiểm tra rõ hơn:

```js
const response = await fetch("https://static.example.net/banner.png", {
  mode: "no-cors"
});

console.log(response.type);             // "opaque" với response cross-origin
console.log(response.status);           // 0
console.log(response.headers.get("content-type")); // null
console.log(response.body);             // null
```

Trình duyệt vẫn nhận và xử lý response ở tầng mạng. Nhưng JavaScript không được quyền quan sát dữ liệu đó. Công cụ Network trong DevTools có thể hiển thị thêm thông tin HTTP để chẩn đoán; điều đó không có nghĩa trang web có thể đọc cùng thông tin qua Fetch API.

## 3. Giới hạn của request no-cors

Để tránh dùng `no-cors` như một kênh gửi request tùy ý, trình duyệt giới hạn method, header và một số kiểu body. Những giới hạn này áp dụng cho request no-cors, đặc biệt khi request đi cross-origin.

### 3.1. Method được phép

Request no-cors chỉ cho phép các method:

- `GET`
- `HEAD`
- `POST`

Các method như `PUT`, `PATCH` và `DELETE` không được phép trong mode này. Nếu API yêu cầu các method đó, hãy dùng CORS đúng cách hoặc một kiến trúc server-side phù hợp.

### 3.2. Request header được phép

Header bị giới hạn ở nhóm CORS-safelisted request headers và các header do trình duyệt tự quản lý. Những header phổ biến trong nhóm safelisted gồm `Accept`, `Accept-Language`, `Content-Language` và `Content-Type` với giá trị bị giới hạn. Một số trường hợp còn cho phép `Range` theo cú pháp byte range đơn.

Các header tùy chỉnh như `Authorization`, `X-Api-Key`, `X-CSRF-Token` hoặc `X-Requested-With` không thuộc nhóm safelisted. Ứng dụng không thể dựa vào việc gửi các header này bằng `no-cors`; chúng sẽ không được đưa vào request theo cách ứng dụng mong muốn. Các header `Sec-Fetch-*`, `Origin`, `Cookie` và nhiều header kiểm soát khác do trình duyệt quản lý, JavaScript không thể tùy ý đặt.

Ví dụ sau không tạo được request API mang bearer token như mong muốn:

```js
await fetch("https://api.example.net/profile", {
  mode: "no-cors",
  headers: {
    Authorization: "Bearer example-token",
    "X-Client-Version": "5"
  }
});
```

Ngay cả khi lệnh fetch không ném lỗi, các header không được phép có thể bị loại bỏ. Không được giả định server đã nhận được `Authorization` hoặc header tùy chỉnh.

### 3.3. Giới hạn `Content-Type` và body

Với request `POST`, `Content-Type` chỉ được safelist cho một số loại dữ liệu như:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

`application/json` không thuộc nhóm này. Vì vậy, no-cors không phù hợp để gọi API JSON thông thường. Nếu cố gửi `Content-Type: application/json`, header có thể bị loại bỏ hoặc request không đáp ứng các ràng buộc của no-cors; server có thể nhận body nhưng không diễn giải theo định dạng mà ứng dụng dự kiến.

Ví dụ một request POST dạng form đơn giản có thể được gửi cross-origin mà không cần CORS preflight:

```js
await fetch("https://forms.example.net/collect", {
  method: "POST",
  mode: "no-cors",
  headers: {
    "Content-Type": "text/plain"
  },
  body: "event=opened"
});
```

Đoạn code chỉ minh họa một request bị giới hạn. Việc JavaScript không đọc được response không ngăn server tiếp nhận hoặc xử lý request. Vì vậy, endpoint nhận dữ liệu vẫn cần xác minh input, xác thực và kiểm soát hành động theo threat model.

## 4. Opaque response và các giới hạn quan sát

Opaque response là response bị che metadata và nội dung khỏi JavaScript. Với response cross-origin trong mode `no-cors`, các đặc điểm chính là:

| Thuộc tính | Giá trị nhìn thấy từ JavaScript |
| --- | --- |
| `response.type` | `"opaque"` |
| `response.status` | `0` |
| `response.ok` | `false` |
| `response.headers` | Không thể đọc các header của response; truy vấn thường trả `null`. |
| `response.body` | `null` |
| Nội dung thực | Không thể đọc bằng `text()`, `json()`, `blob()` hoặc `arrayBuffer()`. |

Ứng dụng không thể phân biệt đáng tin cậy response opaque đại diện cho một ảnh hợp lệ, một trang lỗi 404 hay một lỗi HTTP khác chỉ bằng các thuộc tính JavaScript được phép quan sát. `fetch()` reject khi có lỗi mạng hoặc lỗi bị trình duyệt chặn; một response HTTP lỗi thông thường vẫn có thể resolve. Với opaque response, status thật bị che nên ứng dụng không thể áp dụng logic xử lý status như với response CORS-readable.

Nếu dùng `redirect: "manual"` với một số request cross-origin, trình duyệt có thể trả response loại `opaqueredirect`. Đây cũng là response bị che, không cung cấp URL redirect và header để script tự đọc. Không dùng cách này để dò hoặc lấy URL redirect cross-origin.

Điều cần nhớ là opaque response vẫn có thể mang nội dung để trình duyệt dùng cho một số mục đích, chẳng hạn tải một tài nguyên ảnh hoặc lưu trong Cache Storage. “Opaque” mô tả quyền quan sát của JavaScript, không có nghĩa response rỗng ở tầng mạng.

## 5. Phân biệt no-cors với CORS

Giả sử trang chạy tại `https://app.example.com` cần tải dữ liệu từ `https://api.example.net`.

### 5.1. Khi cần đọc dữ liệu API

Dùng mode `cors` và cấu hình server trả header CORS phù hợp:

```js
const response = await fetch("https://api.example.net/profile", {
  mode: "cors"
});

if (!response.ok) {
  throw new Error(`API failed: ${response.status}`);
}

const profile = await response.json();
```

Server có thể trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json
```

Khi request cần gửi cookie cross-origin, client có thể dùng `credentials: "include"`; server phải trả `Access-Control-Allow-Credentials: true` và một `Access-Control-Allow-Origin` cụ thể, không được dùng `*`. Cookie vẫn chịu chính sách `SameSite`, Secure, third-party cookie blocking và storage partitioning của trình duyệt.

### 5.2. Khi không cần đọc dữ liệu

Một use case có thể chấp nhận opaque response là lấy một tài nguyên công khai từ origin khác để trình duyệt sử dụng như ảnh hoặc một asset được kiểm soát chặt. Nếu ứng dụng cần đọc byte, kiểm tra status, xác minh content type hoặc xử lý lỗi theo status, server nên hỗ trợ CORS hoặc tài nguyên nên được cung cấp qua một endpoint cùng origin đáng tin cậy.

So sánh:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Đọc JSON từ API cross-origin | `mode: "cors"` và cấu hình CORS trên server. |
| Chặn hoàn toàn request cross-origin từ Fetch API | `mode: "same-origin"`. |
| Tải tài nguyên cross-origin nhưng không cần JavaScript đọc response | Có thể dùng `no-cors` trong trường hợp phù hợp; cũng cân nhắc thẻ tài nguyên HTML và thuộc tính `crossorigin` theo loại tài nguyên. |
| Gửi request API có bearer token hoặc header tùy chỉnh | CORS với preflight và cấu hình server phù hợp; không dùng `no-cors`. |
| Gọi endpoint thay đổi trạng thái | Thiết kế xác thực và CSRF protection phía server; không dựa vào mode để bảo vệ endpoint. |

## 6. No-cors và XMLHttpRequest

XMLHttpRequest không có thuộc tính tương đương `fetch(..., { mode: "no-cors" })`. Khi XHR gửi request đến origin khác, trình duyệt áp dụng cơ chế CORS. Nếu server không cho phép origin của trang, script không thể đọc response và XHR phát sinh lỗi theo cơ chế bảo mật.

Ví dụ XHR cross-origin:

```js
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.net/profile");
xhr.onload = () => {
  console.log(xhr.status);
  console.log(xhr.responseText);
};
xhr.onerror = () => {
  console.error("Request failed or was blocked by CORS.");
};
xhr.send();
```

Nếu server trả CORS header hợp lệ, XHR có thể đọc response. Nếu không, XHR không cung cấp một opaque response tương đương để ứng dụng dùng theo kiểu `no-cors`. Cũng không thể dùng `withCredentials` để bỏ qua CORS; khi gửi credential cross-origin, server phải cho phép credential theo đúng quy tắc CORS.

Một số thẻ HTML như `img`, `script`, `audio` hoặc `video` có cơ chế tải tài nguyên cross-origin riêng. Việc một ảnh hiển thị được trong trang không có nghĩa JavaScript có thể đọc pixel của ảnh qua canvas; canvas có thể bị taint nếu tài nguyên không được tải theo CORS phù hợp. Hãy chọn cơ chế theo mục đích sử dụng tài nguyên, không suy luận rằng mọi request cross-origin đều có cùng quy tắc.

## 7. No-cors trong Service Worker và Cache API

Service worker có thể nhận request no-cors trong `fetch` event. Nếu request cross-origin, response có thể là opaque. Worker không thể đọc status hoặc body của response, nhưng trong một số trường hợp có thể lưu response đó vào Cache Storage để trình duyệt sử dụng lại như tài nguyên.

Ví dụ minh họa cache một asset công khai có URL cố định:

```js
async function cachePublicOpaqueAsset(cache, assetUrl) {
  const request = new Request(assetUrl, {
    method: "GET",
    mode: "no-cors"
  });

  const response = await fetch(request);

  if (response.type !== "opaque" && !response.ok) {
    throw new Error(`Asset request failed: ${response.status}`);
  }

  await cache.put(request, response);
}
```

Đoạn code chỉ phù hợp với asset công khai đã được xác định trước, ví dụ một ảnh tĩnh từ CDN đáng tin cậy. Khi response là opaque, điều kiện trong ví dụ không thể xác minh status HTTP thật. Một URL bị cấu hình sai hoặc trả 404 cũng có thể tạo opaque response; vì vậy không dùng mẫu này để cache URL do người dùng nhập, API riêng tư hoặc nội dung có ảnh hưởng bảo mật. Nếu cần xác minh response trước khi cache, hãy yêu cầu server hỗ trợ CORS hoặc đưa tài nguyên qua một endpoint cùng origin có kiểm soát.

`Cache.put(request, response)` có thể lưu opaque response trong khi `Cache.add()` và `Cache.addAll()` yêu cầu response thành công có thể kiểm tra và thường từ chối opaque response. Khi thiết kế cache, cần hiểu khác biệt này thay vì đổi `add()` sang `put()` một cách máy móc.

Một số lưu ý khi cache opaque response:

- Không thể kiểm tra status, header `Cache-Control`, `ETag` hoặc `Last-Modified` từ JavaScript qua response opaque.
- Không thể đọc body để xác nhận loại nội dung hoặc tính toàn vẹn ở phía client.
- Quota accounting của trình duyệt có thể tính thêm phần đệm cho opaque response nhằm giảm rò rỉ thông tin; mức tiêu thụ thực tế có thể khác kích thước file và khác nhau giữa trình duyệt.
- Chính sách cập nhật và xóa cache cần có versioning, giới hạn dung lượng và allowlist URL.
- Không cache opaque response cho dữ liệu xác thực, hồ sơ người dùng hoặc API riêng tư.

Nếu server tài nguyên hỗ trợ CORS, dùng mode `cors` thường cho phép service worker kiểm tra status/header và xử lý lỗi rõ ràng hơn. Đây là lựa chọn dễ kiểm soát hơn khi ứng dụng cần quản lý vòng đời asset.

## 8. No-cors không phải biện pháp chống CSRF

Một hiểu lầm nguy hiểm là response không đọc được đồng nghĩa request không gây tác động. Thực tế, server có thể nhận và xử lý request no-cors dù JavaScript của trang gửi không đọc được response. Một request cross-origin đơn giản có thể được tạo mà không cần CORS preflight.

Ví dụ, endpoint thay đổi trạng thái nhận POST với `text/plain` có thể bị gọi từ một trang khác. Nếu cookie xác thực được gửi theo chính sách cookie hiện hành, endpoint có thể nhận request trong khi attacker không đọc được response. Khả năng cookie được gửi phụ thuộc `credentials`, `SameSite`, Secure, quan hệ site/origin và chính sách chặn cookie bên thứ ba.

Fetch mặc định dùng `credentials: "same-origin"`, vì vậy cookie không tự động được gửi cho request cross-origin chỉ vì mode là `no-cors`. Nếu code đặt `credentials: "include"`, trình duyệt vẫn chỉ gửi cookie đủ điều kiện theo `SameSite`, Secure, third-party cookie policy và các cơ chế phân vùng. `no-cors` không tự bật hoặc vượt qua các quy tắc credential này.

Do đó:

- Không dùng CORS như biện pháp duy nhất chống CSRF. CORS chủ yếu quyết định script origin khác có được đọc response hay không.
- Bảo vệ endpoint thay đổi trạng thái bằng CSRF token hoặc cơ chế tương đương phù hợp với kiến trúc.
- Cấu hình cookie `SameSite` phù hợp, thường kết hợp `Secure` và `HttpOnly` cho session cookie.
- Kiểm tra `Origin` và/hoặc Fetch Metadata như `Sec-Fetch-Site` ở server khi phù hợp; đây là lớp phòng vệ bổ sung, không thay thế kiểm tra quyền và CSRF token trong mọi trường hợp.
- Không thực hiện thao tác nhạy cảm chỉ dựa trên một request `POST` có content type `text/plain` hoặc form đơn giản.
- Với endpoint JSON, xác minh content type, schema, quyền và CSRF; không dựa vào giả định browser sẽ luôn chặn request từ site khác.

`mode: "no-cors"` cũng không làm request vượt qua CSP `connect-src`, mixed-content blocking, CORP/COEP hoặc các chính sách mạng và quyền riêng tư của trình duyệt. Các cơ chế này có mục đích riêng và có thể chặn request hoặc việc sử dụng response.

## 9. Fetch Metadata và chẩn đoán phía server

Trình duyệt có thể gửi các header Fetch Metadata như:

```http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: no-cors
Sec-Fetch-Dest: empty
```

Giá trị cụ thể phụ thuộc loại request và ngữ cảnh. `Sec-Fetch-Mode` giúp server nhận biết request được tạo theo mode nào; `Sec-Fetch-Site` mô tả quan hệ site giữa initiator và target; `Sec-Fetch-Dest` cho biết loại đích như `image`, `script` hoặc `empty`.

Server có thể dùng Fetch Metadata để áp dụng chính sách phòng vệ theo ngữ cảnh, ví dụ từ chối một số request thay đổi trạng thái có `Sec-Fetch-Site: cross-site`. Tuy nhiên, hãy thiết kế theo tập trình duyệt mục tiêu, xử lý client không gửi header và tránh dùng một header đơn lẻ làm cơ chế xác thực. Các header `Sec-*` do trình duyệt kiểm soát; JavaScript thông thường không thể tùy ý ghi đè chúng.

Khi kiểm tra DevTools:

1. Mở tab Network và tạo request bằng `fetch()` với `mode: "no-cors"`.
2. Chọn request để xem method, request header và `Sec-Fetch-Mode` nếu trình duyệt hiển thị.
3. Kiểm tra response thực tế trong Network. DevTools có thể hiển thị status và header HTTP mà script không được đọc.
4. Trong Console, in `response.type`, `status`, `ok`, `headers` và `body` để quan sát góc nhìn của JavaScript.
5. So sánh với cùng URL khi dùng `mode: "cors"` và cấu hình CORS hợp lệ.
6. Thử một request có `Authorization` hoặc `Content-Type: application/json` để thấy giới hạn header/body của no-cors.
7. Kiểm tra server log để xác nhận request có tới server hay không; đừng suy luận request không được gửi chỉ vì script không đọc được response.

## 10. Các lỗi thường gặp

| Cách hiểu hoặc cách làm sai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `no-cors` để sửa lỗi CORS khi gọi API | JavaScript nhận opaque response, không đọc được JSON/status/header. | Cấu hình CORS chính xác ở server hoặc dùng endpoint cùng origin. |
| Kiểm tra `response.ok` để biết asset opaque tải thành công | `ok` luôn false với status 0 của opaque response, kể cả khi tài nguyên thực có thể dùng được. | Chỉ dùng opaque cho tài nguyên cố định, tin cậy và không cần kiểm tra status; ưu tiên CORS nếu cần xác minh. |
| Gửi `Authorization` hoặc header tùy chỉnh trong no-cors | Header không được phép sẽ bị loại bỏ hoặc không được gửi như dự kiến. | Dùng CORS với preflight và xác thực đúng cách. |
| Gửi JSON API bằng no-cors | `application/json` không phải safelisted content type; server có thể không nhận định dạng mong muốn. | Dùng `mode: "cors"` và cấu hình API. |
| Nghĩ response opaque đồng nghĩa request không chạy | Server vẫn có thể thực hiện side effect; rủi ro CSRF vẫn tồn tại. | Bảo vệ endpoint bằng CSRF, xác thực, kiểm tra quyền và Fetch Metadata phù hợp. |
| Dùng `Cache.put()` để lưu mọi opaque response | Có thể cache nhầm lỗi, nội dung không mong muốn hoặc tài nguyên không còn hợp lệ. | Allowlist URL, giới hạn cache và dùng CORS khi cần kiểm tra response. |
| Nghĩ XHR có mode no-cors | XHR cross-origin dùng CORS; không có tùy chọn mode no-cors tương đương. | Dùng Fetch API khi cần no-cors hoặc cấu hình CORS cho XHR. |

## 11. Bài thực hành

Tạo một trang thử nghiệm tại origin A và một static server tại origin B. Dùng dữ liệu giả, không dùng token hoặc thông tin cá nhân thật.

1. Từ trang A, gọi một ảnh công khai ở origin B bằng `fetch()` với `mode: "no-cors"`.
2. In `type`, `status`, `ok`, `headers` và `body`; ghi lại khác biệt giữa góc nhìn của JavaScript và Network panel.
3. Thử gọi cùng tài nguyên bằng mode `cors`. Cấu hình `Access-Control-Allow-Origin` trên origin B và quan sát response có thể đọc được.
4. Thử gửi `Authorization`, `X-Test` và `Content-Type: application/json` ở mode no-cors. Kiểm tra request thực tế trong Network và log của server.
5. Đăng ký service worker, thử lưu asset opaque bằng `Cache.put()` rồi đọc lại từ cache để trình duyệt hiển thị tài nguyên. So sánh với `Cache.add()`.
6. Tạo một endpoint POST thử nghiệm chỉ ghi nhận sự kiện. Gửi request no-cors và xác nhận server có nhận request dù client không đọc được response.
7. Thêm CSRF protection phù hợp cho endpoint thay đổi trạng thái và kiểm thử lại từ một trang cross-site trong môi trường lab.
8. Thử cùng request bằng XMLHttpRequest để xác nhận XHR không có mode no-cors và cần CORS hợp lệ để đọc response cross-origin.

Hoàn thành bài thực hành khi bạn giải thích được vì sao no-cors có thể gửi một request bị giới hạn nhưng không cho script đọc response, xác định được trường hợp opaque response có thể dùng trong cache tài nguyên công khai, và chứng minh rằng khả năng đọc response độc lập với việc server có xử lý request hay không.
