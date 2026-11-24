# Cookie size limit: giới hạn kích thước và tác động tới ứng dụng web

## 1. Vì sao kích thước cookie quan trọng?

Cookie thường được dùng để lưu session ID, tùy chọn giao diện, mã định danh theo dõi hoặc một lượng nhỏ trạng thái mà server cần nhận lại trong các request tiếp theo. Cookie có vẻ nhỏ và tiện lợi, nhưng trình duyệt, máy chủ web, reverse proxy và CDN đều có giới hạn đối với header HTTP.

Nếu cookie quá lớn, trình duyệt có thể từ chối lưu cookie, loại bỏ cookie cũ theo chính sách quota, hoặc gửi một request có header quá lớn khiến server/proxy từ chối. Ngay cả khi cookie vẫn được chấp nhận, nó có thể làm tăng băng thông vì được gửi lặp lại trên nhiều request phù hợp.

**Cookie size limit** là giới hạn về kích thước của một cookie và tổng dữ liệu cookie được gửi trong header. Không có một con số duy nhất bảo đảm áp dụng giống hệt cho mọi trình duyệt, server, proxy và CDN. RFC 6265 đặt ra mức hỗ trợ tối thiểu được khuyến nghị cho user agent, còn triển khai thực tế và giới hạn hạ tầng có thể khác nhau.

Trong mô hình bảo mật trình duyệt, cần hiểu kích thước cookie cùng với domain/path scope, Secure, HttpOnly, SameSite, quản lý session và giới hạn HTTP header. Sau bài học, bạn có thể:

- Phân biệt giới hạn một cookie với giới hạn tổng request header.
- Hiểu vì sao cần đo bằng byte thay vì số ký tự.
- Nhận diện lỗi lưu cookie, eviction và HTTP 431.
- Thiết kế cookie phiên nhỏ gọn và an toàn.
- Kiểm tra kích thước Set-Cookie/Cookie trong DevTools và hạ tầng.

## 2. Giới hạn kích thước một cookie

RFC 6265 khuyến nghị user agent hỗ trợ tối thiểu **4096 byte cho mỗi cookie**, tính theo tổng độ dài của tên, giá trị và các thuộc tính cookie. Đây là mức hỗ trợ tối thiểu được khuyến nghị trong tiêu chuẩn, không nên hiểu là mọi trình duyệt và mọi tầng hạ tầng đều có cùng một hard limit chính xác.

Trong thực tế, khoảng **4 KiB cho một cookie** là mốc thường được dùng khi thiết kế tương thích. Cách tính và xử lý khi vượt giới hạn có thể khác theo trình duyệt. Một số triển khai giới hạn phần tên/giá trị; các triển khai khác xét cách biểu diễn cookie và thuộc tính. Vì vậy, ứng dụng nên để dư khoảng an toàn và kiểm tra trên những browser được hỗ trợ.

Ví dụ:

```http
Set-Cookie: session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie trên có:

- Tên: `session`.
- Giá trị: `abc123`.
- Thuộc tính: `Path`, `Secure`, `HttpOnly`, `SameSite`.

Khi tính ngân sách kích thước, không chỉ nhìn riêng giá trị `abc123`. Tên và phần biểu diễn thuộc tính cũng có thể đóng góp vào kích thước cookie được lưu theo cách triển khai hoặc tiêu chí của tiêu chuẩn.

**Quy tắc thực hành:** giữ cookie nhỏ hơn đáng kể so với mốc 4 KiB thay vì thiết kế sát giới hạn. Ví dụ, có thể đặt ngân sách nội bộ khoảng 2–3 KiB cho tên và giá trị để dành chỗ cho thuộc tính, khác biệt triển khai và thay đổi trong tương lai. Đây là mục tiêu kỹ thuật thận trọng, không phải giới hạn chuẩn bắt buộc.

## 3. Byte khác với ký tự

Giới hạn kích thước được đo bằng **byte (octet)**, không phải số ký tự hiển thị. Với nội dung chỉ gồm ASCII, số ký tự thường trùng số byte. Với Unicode hoặc dữ liệu được mã hóa, số byte có thể lớn hơn.

Ví dụ:

| Nội dung | Số ký tự | Kích thước UTF-8 |
| --- | ---: | ---: |
| `hello` | 5 | 5 byte |
| `café` | 4 | 5 byte |
| `Xin chào` | 8 | 9 byte |
| Một emoji ngoài BMP | 1 ký tự hiển thị | Thường 4 byte UTF-8 |

JavaScript `string.length` đếm đơn vị mã UTF-16, không phải số byte UTF-8:

```javascript
const value = "Xin chào 🌱";

console.log(value.length); // Số UTF-16 code units
console.log(new TextEncoder().encode(value).length); // Số byte UTF-8
```

Cookie value có tập ký tự được phép theo cú pháp cookie. Ứng dụng thường encode dữ liệu không phải ASCII trước khi đặt vào cookie. Ví dụ `encodeURIComponent` biến nhiều ký tự thành chuỗi phần trăm mã hóa; chuỗi kết quả dùng các ký tự ASCII nhưng có thể dài hơn đáng kể.

### 3.1 Base64 cũng làm dữ liệu dài hơn

Nếu dữ liệu nhị phân được chuyển sang Base64, kích thước tăng khoảng một phần ba so với dữ liệu gốc, chưa tính tên và thuộc tính cookie:

```javascript
const bytes = new Uint8Array(1024);
const binary = String.fromCharCode(...bytes);
const base64 = btoa(binary);

console.log(bytes.byteLength); // 1024 byte
console.log(base64.length);    // khoảng 1368 ký tự
```

Không nên nhét ảnh, file, object JSON lớn hoặc dữ liệu nhị phân vào cookie chỉ vì có thể encode chúng thành chuỗi. Mã hóa không làm dữ liệu nhỏ đi; Base64 còn làm tăng kích thước.

### 3.2 Đo kích thước chuỗi cookie trong JavaScript

Có thể dùng hàm đơn giản để ước lượng byte UTF-8 của một chuỗi:

```javascript
function utf8Bytes(value) {
  return new TextEncoder().encode(value).length;
}

const name = "session";
const value = "opaque-session-id";
const nameValue = name + "=" + value;

console.log("Name/value bytes:", utf8Bytes(nameValue));
```

Đây là phép đo phần tên/giá trị theo UTF-8 để theo dõi ngân sách ứng dụng. Nó **không thay thế thuật toán giới hạn cookie riêng của từng trình duyệt** và chưa tính mọi thuộc tính trong Set-Cookie.

## 4. Giới hạn một cookie khác giới hạn tổng Cookie header

Một ứng dụng thường có nhiều cookie: session, CSRF state, ngôn ngữ, tùy chọn, phân tích truy cập và cookie của các thành phần khác. Mỗi cookie có thể nằm dưới giới hạn riêng, nhưng tổng các cookie phù hợp vẫn có thể làm request header quá lớn.

Ví dụ:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: session=...; preferences=...; analytics=...; feature-state=...
```

Header `Cookie` chứa các cặp tên/giá trị được trình duyệt chọn gửi cho request đó. Các thuộc tính như `Secure`, `HttpOnly`, `SameSite`, `Path` và `Domain` không được gửi lặp lại trong request header Cookie.

Phân biệt hai giới hạn:

| Loại giới hạn | Đo lường | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Kích thước một cookie | Một cookie riêng lẻ khi lưu/được xử lý. | Trình duyệt từ chối cookie hoặc xử lý theo chính sách triển khai. |
| Tổng Cookie header | Tất cả cookie được gửi cùng request. | Server, proxy hoặc CDN từ chối request do header quá lớn. |
| Tổng request headers | Cookie cộng với Authorization, User-Agent, tracing và các header khác. | Vượt giới hạn header tổng của một tầng hạ tầng. |
| Response Set-Cookie headers | Các header Set-Cookie và header response khác. | Server/proxy có thể từ chối hoặc cắt response header quá lớn. |

Giới hạn tổng header thường do web server, reverse proxy, load balancer, WAF hoặc CDN đặt ra. Chúng có thể khác nhau ngay trong cùng một hệ thống. Vì vậy, cookie nhỏ vẫn có thể góp phần gây lỗi nếu có quá nhiều cookie hoặc các header khác đã chiếm phần lớn ngân sách.

## 5. Điều gì xảy ra khi cookie hoặc header quá lớn?

### 5.1 Trình duyệt không lưu cookie

Khi response gửi Set-Cookie vượt giới hạn mà trình duyệt áp dụng, trình duyệt có thể bỏ qua cookie đó. Ứng dụng có thể thấy:

- Người dùng đăng nhập xong nhưng request tiếp theo không có session cookie.
- Cookie mới không xuất hiện trong Application/Storage.
- Cookie cũ vẫn tồn tại vì cookie mới không được chấp nhận hoặc không thay thế nó.
- Hành vi khác nhau giữa các trình duyệt hoặc phiên bản.

Không nên dựa vào việc một browser chấp nhận cookie lớn để kết luận browser khác cũng sẽ làm như vậy.

### 5.2 Cookie bị eviction do quota

Trình duyệt còn quản lý số lượng cookie và tổng dung lượng cookie theo host/domain hoặc các vùng lưu trữ liên quan. Khi vượt quota, trình duyệt có thể xóa cookie theo chính sách eviction. Thứ tự xóa không phải lúc nào cũng giống nhau và có thể phụ thuộc tuổi cookie, thời điểm truy cập, mức ưu tiên hoặc triển khai cụ thể.

Điều đó có nghĩa cookie chưa vượt giới hạn kích thước riêng lẻ vẫn có thể biến mất khi ứng dụng tạo quá nhiều cookie hoặc sử dụng quá nhiều dung lượng. Ứng dụng không nên coi cookie là một kho lưu trữ bền vững.

### 5.3 Server trả lỗi 431 hoặc 400

Nếu tổng request header vượt giới hạn, server có thể trả:

```http
HTTP/1.1 431 Request Header Fields Too Large
```

Một số hệ thống có thể trả 400 Bad Request hoặc mã lỗi riêng. Lỗi cũng có thể xuất hiện ở reverse proxy trước khi request tới ứng dụng. Do đó, log của backend có thể không ghi nhận request bị chặn ở tầng proxy.

Response header quá lớn cũng có thể bị từ chối bởi server hoặc proxy. Vì vậy, cần kiểm tra cả kích thước request Cookie lẫn tổng các header Set-Cookie mà server trả.

## 6. Vì sao cookie lớn gây tốn băng thông?

Cookie được gửi tự động trên mọi request thỏa domain/host, path, secure transport và các điều kiện khác. Nếu cookie session có 3 KiB và trang tải 40 tài nguyên cùng host với phạm vi path phù hợp, lượng dữ liệu cookie được gửi lặp lại có thể lên tới khoảng 120 KiB chỉ cho cookie đó, chưa tính header khác.

Ví dụ:

```text
Một cookie lớn:          3 KiB
Số request phù hợp:      40
Tổng dữ liệu lặp lại:   120 KiB
```

Đây là phép tính minh họa, không tính nén header, kết nối, cache hoặc các chi tiết giao thức khác. HTTP/2 và HTTP/3 có nén header, nhưng điều đó không làm biến mất giới hạn header, chi phí xử lý, cookie store quota hoặc nguy cơ dữ liệu bị gửi tới nhiều endpoint.

Cookie lớn có thể:

- Tăng byte truyền trên mạng và độ trễ, nhất là trên kết nối di động.
- Làm tăng chi phí parse header ở proxy và ứng dụng.
- Tăng nguy cơ vượt giới hạn request header.
- Gửi dữ liệu không cần thiết tới endpoint tĩnh trên cùng phạm vi host/path.
- Tăng phạm vi dữ liệu nhạy cảm bị lộ nếu log hoặc hệ thống giám sát ghi lại Cookie header.

## 7. Không dùng cookie như một kho lưu trữ ứng dụng

Cookie được thiết kế cho dữ liệu nhỏ mà trình duyệt gửi cùng request. Không nên dùng nó để lưu toàn bộ trạng thái ứng dụng hoặc object lớn.

### 7.1 Tránh lưu JSON lớn

Ví dụ không nên làm:

```javascript
// Không nên: lưu toàn bộ trạng thái hồ sơ vào cookie.
const profile = {
  id: "user-123",
  displayName: "Lan",
  roles: ["admin", "billing", "support"],
  preferences: { /* nhiều cấu hình */ },
  recentOrders: [ /* danh sách lớn */ ]
};

document.cookie =
  "profile=" + encodeURIComponent(JSON.stringify(profile)) +
  "; Path=/; Secure; SameSite=Lax";
```

Những vấn đề:

- Kích thước JSON và phần encode tăng nhanh.
- Cookie được gửi lại trên nhiều request, kể cả khi endpoint không cần profile.
- Client có thể sửa dữ liệu cookie; server không được tin nội dung chỉ vì nó đã được lưu ở browser.
- Nếu ký hoặc mã hóa payload, kích thước vẫn lớn và việc quản lý khóa/rotation phức tạp hơn.
- Thay đổi cấu trúc dữ liệu có thể tạo lỗi tương thích giữa phiên bản frontend và backend.

### 7.2 Dùng session ID nhỏ gọn

Mô hình thường phù hợp hơn là lưu một mã phiên ngẫu nhiên trong cookie:

```http
Set-Cookie: __Host-session=Qm9...opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Server dùng session ID để tra cứu trạng thái phiên ở kho lưu trữ phía server:

```text
Browser
  Cookie: __Host-session=<opaque-id>
        │
        ▼
Application server
        │
        ├─ Validate session ID
        ├─ Load session from server-side store
        ├─ Check user and permissions
        └─ Process request
```

Cookie chỉ mang mã tham chiếu nhỏ; dữ liệu hồ sơ, quyền, giỏ hàng và trạng thái nghiệp vụ được lưu phía server hoặc hệ thống phù hợp. Server có thể thu hồi session mà không phải chờ cookie payload cũ hết hạn.

### 7.3 JWT trong cookie cũng có giới hạn

JWT có thể được đặt trong cookie, nhưng token thường chứa header, claims và chữ ký đã được encode. Nhiều claim hoặc dữ liệu profile làm JWT lớn; nếu cookie gửi JWT trên mọi request, header sẽ phình ra.

Không nên đưa danh sách quyền dài, dữ liệu cá nhân hoặc dữ liệu nghiệp vụ biến đổi thường xuyên vào JWT chỉ để tránh truy vấn session. Hãy cân nhắc token ngắn gọn, claim tối thiểu, thời hạn phù hợp và cơ chế thu hồi/rotation. Chữ ký JWT đảm bảo tính toàn vẹn theo thuật toán, không tự mã hóa payload thành bí mật.

## 8. Cookie chunking có phải giải pháp?

Một số thư viện chia payload lớn thành nhiều cookie nhỏ, ví dụ:

```http
Set-Cookie: session.0=part-one; Path=/; Secure; HttpOnly
Set-Cookie: session.1=part-two; Path=/; Secure; HttpOnly
Set-Cookie: session.2=part-three; Path=/; Secure; HttpOnly
```

Kỹ thuật này được gọi là **cookie chunking**. Nó có thể giúp một thư viện vượt giới hạn một cookie trong một số triển khai, nhưng không làm giảm tổng dữ liệu:

- Tất cả chunk vẫn được gửi trong Cookie header nếu cùng phạm vi.
- Tổng header vẫn có thể vượt giới hạn server/proxy.
- Nhiều cookie tiêu thụ quota số lượng và dung lượng của browser.
- Nếu thiếu một chunk hoặc chunk cũ còn sót lại, ứng dụng có thể không tái tạo được payload.
- Việc cập nhật/thu hồi phải xóa mọi chunk với thuộc tính Domain/Path phù hợp.

Cookie chunking vì vậy không phải lựa chọn mặc định cho session hoặc JWT lớn. Trước hết hãy giảm dữ liệu; nếu payload vẫn lớn, chuyển dữ liệu về server-side store và chỉ giữ một opaque ID trong cookie.

## 9. Cookie size và các thuộc tính bảo mật

Các thuộc tính bảo mật không làm cookie “nhỏ hơn” theo cùng một cách, nhưng chúng có thể thêm vài byte vào phần Set-Cookie và quan trọng hơn là xác định cách cookie được bảo vệ.

| Thuộc tính | Vai trò | Tác động liên quan đến kích thước |
| --- | --- | --- |
| `Secure` | Chỉ gửi qua kênh an toàn như HTTPS. | Thêm một token thuộc tính trong Set-Cookie; không được gửi lại trong Cookie request header. |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua document.cookie. | Thêm thuộc tính trong Set-Cookie; không được gửi lại trong Cookie request header. |
| `SameSite` | Điều khiển gửi cookie trong ngữ cảnh same-site/cross-site. | Thêm giá trị thuộc tính trong Set-Cookie. |
| `Domain` | Mở rộng cookie tới domain/subdomain phù hợp. | Thêm domain vào Set-Cookie; không xuất hiện trong Cookie request header. |
| `Path` | Giới hạn path phù hợp. | Thêm path trong Set-Cookie; không xuất hiện trong Cookie request header. |
| `Max-Age` / `Expires` | Kiểm soát thời hạn. | Thêm thuộc tính trong Set-Cookie. |
| Prefix `__Host-` | Ràng buộc Secure, Path=/ và không có Domain. | Prefix làm tên cookie dài hơn, đổi lại có ràng buộc scope tốt hơn. |

Không loại bỏ `Secure`, `HttpOnly` hoặc `SameSite` chỉ để tiết kiệm vài byte. Hãy tối ưu payload và số cookie, không hy sinh thuộc tính bảo mật thiết yếu.

Cookie không được phân vùng theo port như origin. Vì vậy, nhiều ứng dụng trên cùng hostname có thể chia sẻ một số cookie phù hợp dù chạy ở port khác nhau. Path cũng không phải ranh giới bảo mật mạnh; đừng dùng Path để thay thế hostname riêng khi cần cô lập ứng dụng.

## 10. Kiểm tra kích thước và chẩn đoán lỗi

### 10.1 DevTools Application/Storage

Trong Chrome/Chromium:

1. Mở DevTools → **Application** → **Storage → Cookies**.
2. Chọn host đang kiểm tra.
3. Quan sát tên, domain, path, kích thước hoặc giá trị cookie (giao diện có thể khác theo phiên bản).
4. Kiểm tra các cookie cũ, cookie trùng tên nhưng khác Path/Domain và cookie không cần thiết.
5. Không copy hoặc chia sẻ giá trị session cookie; che dữ liệu nhạy cảm trong ảnh chụp.

### 10.2 DevTools Network

1. Mở tab **Network**, bật Preserve log nếu cần.
2. Tải trang hoặc gọi endpoint gây lỗi.
3. Chọn request → **Headers**.
4. Kiểm tra request header `Cookie` và response header `Set-Cookie`.
5. Xem response status, đặc biệt `431 Request Header Fields Too Large` hoặc `400 Bad Request`.
6. Kiểm tra request nào đang gửi cookie lớn và cookie đó có thực sự cần cho endpoint hay không.

Lưu ý: trình duyệt có thể ẩn hoặc giới hạn hiển thị một số chi tiết Set-Cookie trong JavaScript; `Set-Cookie` là forbidden response-header name và không được expose cho frontend qua Fetch API.

### 10.3 Đo kích thước phía server

Backend hoặc reverse proxy có thể ghi log **độ dài** Cookie header mà không ghi giá trị:

```javascript
function cookieHeaderBytes(req) {
  const value = req.headers.cookie ?? "";
  return Buffer.byteLength(value, "utf8");
}

// Chỉ log kích thước, không log nội dung cookie.
console.log({
  cookieHeaderBytes: cookieHeaderBytes(req)
});
```

Đo tổng header ở đúng tầng nhận request nếu có thể. Middleware ứng dụng không nhìn thấy request đã bị load balancer hoặc reverse proxy từ chối trước đó. Tránh ghi raw Cookie header vào log vì có thể làm lộ session ID.

### 10.4 Quy trình xử lý lỗi 431

Khi nhận 431 hoặc lỗi header tương tự:

1. Xác định tầng trả lỗi: CDN, WAF, reverse proxy, web server hay ứng dụng.
2. Đo tổng request header và riêng Cookie header.
3. Liệt kê cookie theo domain/path; tìm cookie lớn, cookie trùng tên, chunk cũ hoặc cookie hết nhu cầu.
4. Giảm payload và xóa cookie dư bằng Set-Cookie có cùng tên, Domain và Path phù hợp.
5. Chuyển dữ liệu nghiệp vụ sang server-side store; giữ opaque session ID nhỏ.
6. Kiểm tra lại các request tĩnh/API và luồng đăng nhập sau khi thay đổi.

Không tăng giới hạn header ở proxy như giải pháp duy nhất. Điều đó có thể che vấn đề và tăng bộ nhớ/bề mặt từ chối dịch vụ. Chỉ điều chỉnh giới hạn khi đã hiểu ngân sách, có lý do và cấu hình đồng nhất trên các tầng.

## 11. Checklist thiết kế cookie gọn và an toàn

- [ ] Cookie chỉ chứa dữ liệu cần gửi lại tự động trong request.
- [ ] Session cookie dùng một ID ngẫu nhiên, không chứa profile hoặc quyền dài.
- [ ] Kích thước được đo bằng byte; có khoảng dự phòng dưới giới hạn triển khai.
- [ ] Không lưu JSON lớn, file, ảnh hoặc payload nhị phân trong cookie.
- [ ] Không tạo quá nhiều cookie và dọn cookie/chunk cũ khi cập nhật.
- [ ] Cookie phiên có `Secure` và `HttpOnly`.
- [ ] `SameSite` được chọn theo luồng nghiệp vụ và CSRF threat model.
- [ ] Cookie host-only được ưu tiên khi không cần chia sẻ giữa subdomain.
- [ ] Xem xét prefix `__Host-` cho session cookie.
- [ ] Không log giá trị Cookie hoặc Set-Cookie.
- [ ] Đã kiểm tra giới hạn ở browser, CDN, proxy và web server.
- [ ] Đã thử các request tải trang, API và tài nguyên tĩnh để phát hiện header bloat.

## 12. Câu hỏi tự kiểm tra

1. RFC 6265 khuyến nghị user agent hỗ trợ ít nhất bao nhiêu byte cho mỗi cookie, và vì sao không nên xem đó là giới hạn giống hệt ở mọi tầng?
2. Vì sao `string.length` không đủ để đo kích thước cookie có Unicode?
3. Cookie riêng lẻ dưới 4 KiB nhưng request vẫn có thể bị 431 vì lý do gì?
4. Vì sao cookie được gửi lặp lại trên nhiều request có thể làm tăng băng thông?
5. Cookie chunking giải quyết được giới hạn nào và không giải quyết được giới hạn nào?
6. Vì sao JWT lớn trong cookie có thể làm header phình ra dù JWT đã được ký?
7. Khi điều tra 431, vì sao cần kiểm tra cả CDN/reverse proxy thay vì chỉ log ứng dụng?
8. Vì sao không nên bỏ Secure hoặc HttpOnly để tiết kiệm kích thước?

## 13. Tổng kết

Cookie có giới hạn kích thước riêng và còn góp phần vào giới hạn tổng HTTP header. RFC 6265 khuyến nghị user agent hỗ trợ ít nhất 4096 byte cho mỗi cookie theo cách đo của tiêu chuẩn, nhưng browser và hạ tầng có thể có cách xử lý khác nhau. Kích thước phải được xem theo byte, không chỉ theo số ký tự; tổng nhiều cookie có thể làm request vượt giới hạn và nhận lỗi 431 hoặc 400.

Thiết kế tốt là giữ cookie nhỏ, chỉ chứa một session ID opaque hoặc dữ liệu trạng thái tối thiểu. Tránh JSON/JWT lớn, cookie chunking không cần thiết và Domain quá rộng. Đo request/response header tại DevTools và các tầng hạ tầng, không log giá trị cookie; đồng thời giữ nguyên Secure, HttpOnly, SameSite và các kiểm soát session/CSRF cần thiết. Cookie là phương tiện mang một lượng nhỏ trạng thái, không phải kho lưu trữ ứng dụng.
