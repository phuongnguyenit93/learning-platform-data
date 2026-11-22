# Cookie, phiên làm việc và giới hạn của trạng thái qua HTTP

HTTP là giao thức trao đổi **request–response**. Một request thường được xử lý dựa trên method, URL, header, body và những dữ liệu mà server có thể tra cứu. Bản thân HTTP **không tự nhớ** request trước thuộc về ai hoặc điều gì đã diễn ra ở request đó. Muốn có giỏ hàng, đăng nhập, tùy chọn ngôn ngữ hay tiến trình nhiều bước, ứng dụng phải thiết kế cơ chế liên kết các request.

Ba khái niệm cần phân biệt ngay từ đầu:

- **Cookie** là một cặp tên–giá trị cùng các thuộc tính, được server yêu cầu user agent lưu qua `Set-Cookie`, rồi user agent có thể gửi lại bằng `Cookie` khi điều kiện phù hợp. Cookie nằm phía client.
- **Session (phiên làm việc)** là cách ứng dụng liên kết nhiều request trong một khoảng thời gian. Trong mô hình server-side session phổ biến, cookie chỉ mang **session ID**, còn trạng thái thật nằm ở server hoặc session store.
- **Authentication state (trạng thái xác thực)** là việc ứng dụng biết ai đang được xác thực, thường gắn với session hoặc token. Có cookie/session **không đồng nghĩa** người dùng đã đăng nhập.

Bài này tập trung vào cơ chế HTTP, cách trình duyệt vận hành cookie, trạng thái phiên phía server, các giới hạn và hệ quả bảo mật, rồi nối với Spring MVC.

## 1. Vì sao HTTP được gọi là stateless?

Xét hai request độc lập:

```http
GET /catalog HTTP/1.1
Host: shop.example
```

```http
GET /checkout HTTP/1.1
Host: shop.example
```

Chỉ nhìn hai thông điệp này, server không biết chắc cùng một người dùng đã gửi chúng. Kết nối TCP/TLS có thể được tái sử dụng nhưng **kết nối không phải danh tính người dùng**. Client có thể mở nhiều kết nối; proxy, load balancer và HTTP/2/HTTP/3 thay đổi cách các request được truyền mà không làm HTTP tự tạo session nghiệp vụ.

Tính stateless không có nghĩa **server không thể lưu dữ liệu**. Server có thể lưu tài khoản, đơn hàng, giỏ hàng hoặc session vào cơ sở dữ liệu. Điểm mấu chốt là giao thức không tự quy định một bộ nhớ hội thoại giữa các request. Ứng dụng cần cung cấp một cách xác định request hiện tại liên quan đến trạng thái nào.

```text
Request 1: client ── HTTP ──> server  → tạo trạng thái
Request 2: client ── HTTP ──> server  → cần khóa tra cứu trạng thái cũ
                                    ↑
                        Cookie / token / dữ liệu request
```

Có ứng dụng thiết kế **stateless ở tầng ứng dụng**: mỗi request mang token hoặc dữ liệu cần kiểm tra, server không cần lưu session đăng nhập tương ứng. Có ứng dụng dùng **stateful server session**: request mang session ID để server tìm lại dữ liệu phiên. Cả hai vẫn dùng HTTP.

## 2. Cookie đi qua HTTP như thế nào?

### 2.1. Set-Cookie và Cookie là hai hướng khác nhau

Một response ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Set-Cookie: sid=opaqueRandomIdentifier; Path=/; Secure; HttpOnly; SameSite=Lax

Đã tạo phiên.
```

Sau khi nhận response, trình duyệt **có thể lưu** cookie nếu phù hợp với chính sách cookie và ngữ cảnh hiện tại. Ở request sau đến host/path phù hợp:

```http
GET /profile HTTP/1.1
Host: shop.example
Cookie: sid=opaqueRandomIdentifier
```

Lưu ý:

1. `Set-Cookie` là **response header**; `Cookie` là **request header**. Trong `Cookie`, client gửi chủ yếu các cặp `name=value`, **không gửi lại** `HttpOnly`, `Secure`, `SameSite` hay `Path` như thuộc tính.
2. Một response có thể có nhiều header `Set-Cookie`; một request có thể gửi nhiều cặp cookie.
3. Giá trị `sid` ở đây chỉ là chuỗi giả minh họa. Session ID thật cần có tính ngẫu nhiên/khó đoán phù hợp; **không tự dùng username hay số thứ tự làm session ID**.
4. Trình duyệt tự xét có gửi cookie hay không theo host/domain, path, HTTPS, thời hạn, ngữ cảnh site và chính sách riêng. Server không thể giả định mọi client luôn giữ hoặc gửi cookie.
5. JavaScript `fetch` chịu quy tắc credentials/CORS riêng; việc biết URL hợp lệ không bảo đảm request cross-origin tự mang cookie.

Cookie là dữ liệu phía client: bất cứ giá trị nào do client gửi đều phải được coi là **đầu vào không đáng tin cậy**. Cookie thường không được mã hóa hay ký theo mặc định; người dùng có thể sửa cookie của mình, dù `HttpOnly` hạn chế khả năng truy cập qua JavaScript trong trang.

### 2.2. Các thuộc tính cốt lõi

| Thuộc tính | Ý nghĩa thực tế | Cần nhớ |
| --- | --- | --- |
| `Domain` | Giới hạn phạm vi host/domain nhận cookie | Nếu không đặt `Domain`, cookie thường là **host-only**; đặt `Domain=example.com` có thể cho phép các subdomain phù hợp nhận cookie. Không thể dùng để đặt cookie cho domain không được phép. |
| `Path` | Giới hạn path URL được đính kèm cookie | Ví dụ `Path=/account`; **không phải cơ chế phân quyền/bảo mật cô lập** các khu vực ứng dụng. |
| `Secure` | Chỉ gửi cookie trên các kết nối được coi là an toàn theo quy tắc user agent | Trong môi trường triển khai thông thường, dùng HTTPS; một số hành vi dành cho localhost tùy browser. |
| `HttpOnly` | Ngăn JavaScript phía trang đọc/ghi trực tiếp cookie qua các API như `document.cookie` | Trình duyệt **vẫn tự gửi** cookie trong request phù hợp, kể cả request do JavaScript tạo. Không tự chống CSRF hoặc XSS hoàn toàn. |
| `SameSite=Strict` | Giới hạn chặt việc gửi cookie trong ngữ cảnh cross-site | Tăng bảo vệ trước một số CSRF, nhưng có thể ảnh hưởng luồng người dùng đi từ site khác sang. |
| `SameSite=Lax` | Hạn chế đa số request cross-site, vẫn cho một số top-level navigation đủ điều kiện | Phù hợp nhiều session thông thường; **không thay thế CSRF defense đầy đủ**. |
| `SameSite=None` | Cho phép gửi trong các ngữ cảnh cross-site nếu chính sách browser cho phép | Browser hiện đại thường yêu cầu kèm `Secure`; còn chịu hạn chế third-party cookie/partitioning. |
| `Max-Age` | Thời gian lưu cookie tính bằng giây | Nếu cả `Max-Age` và `Expires` có hiệu lực, `Max-Age` được ưu tiên theo chuẩn. |
| `Expires` | Thời điểm hết hạn theo ngày giờ HTTP | Đồng hồ và chính sách browser có thể ảnh hưởng hành vi lưu/xóa. |

Ví dụ cookie tùy chọn ngôn ngữ tồn tại một giờ:

```http
Set-Cookie: lang=vi; Max-Age=3600; Path=/; Secure; SameSite=Lax
```

Ví dụ cookie session mà JavaScript trang không đọc trực tiếp:

```http
Set-Cookie: sid=unpredictableValue; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong phát triển local qua HTTP, cookie gắn `Secure` có thể không hoạt động như trong môi trường HTTPS thực. Cần thử trong môi trường tương ứng và quan sát header/cookie store thật của trình duyệt.

### 2.3. Session cookie và persistent cookie

- **Session cookie** thường không có `Max-Age` hoặc `Expires`. User agent có thể xóa nó khi kết thúc phiên trình duyệt; chức năng khôi phục phiên có thể khiến cookie còn tồn tại khi mở lại trình duyệt.
- **Persistent cookie** có thời hạn lưu rõ hơn qua `Max-Age`/`Expires`, nhưng vẫn có thể bị người dùng xóa, trình duyệt chặn hoặc bị giới hạn bởi chính sách riêng.
- **Cookie lifetime** và **server session lifetime** là hai đồng hồ khác nhau. Cookie còn ở client không có nghĩa session ID đó còn tồn tại hoặc còn được server chấp nhận.

Xóa cookie thường thực hiện bằng `Set-Cookie` với **đúng tên và phạm vi Path/Domain tương ứng**, đồng thời `Max-Age=0` (hoặc hạn đã qua):

```http
Set-Cookie: sid=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
```

Đặt `Max-Age=0` với `Path` hoặc `Domain` khác cookie ban đầu có thể không xóa đúng cookie mong muốn. Với cookie đăng nhập, **chỉ xóa cookie phía client là chưa đủ**: server cũng cần hủy session hoặc thu hồi token theo thiết kế.

### 2.4. “Origin” khác “site”: nguồn gốc nhầm lẫn phổ biến

**Origin** thường được xác định bằng *scheme + host + port*: `https://app.example.com:443` và `https://app.example.com:8443` khác origin. Khái niệm **site** dùng cho SameSite được xây dựng từ scheme và registrable domain theo các quy tắc browser: `https://app.example.com` và `https://api.example.com` có thể cùng site, dù khác origin.

Các hệ quả:

- Cookie **không tách biệt theo port** giống origin. Hai ứng dụng ở các port khác nhau trên cùng host cần rất cẩn thận với tên/phạm vi cookie.
- CORS chủ yếu quyết định JavaScript ở một origin có được đọc response cross-origin hay không, và một số request có được trình duyệt gửi hay không; CORS **không phải hệ thống phân quyền tài nguyên**.
- `SameSite` xem xét quan hệ site, không chỉ quan hệ origin. Hai subdomain cùng site vẫn có thể tạo rủi ro CSRF nếu tin tưởng quá rộng.
- Cấu hình `Domain`, `Path` chỉ ảnh hưởng chọn gửi cookie, không bảo đảm quyền đọc dữ liệu server hay quyền truy cập endpoint.

Nên ưu tiên cookie host-only cho session khi không có nhu cầu chia sẻ giữa subdomain. Với browser hỗ trợ cookie prefix, tên bắt đầu bằng `__Host-` yêu cầu `Secure`, `Path=/` và **không có `Domain`**; `__Secure-` yêu cầu `Secure`. Prefix tăng tính kiểm tra cấu hình nhưng không thay cơ chế xác thực/phân quyền.

## 3. Server-side session hoạt động ra sao?

Ví dụ mô hình session phổ biến:

```text
Lần đầu:
Browser -- POST /preferences (chưa có sid) --> Spring MVC
                                     │
                          session store tạo ID ngẫu nhiên
                                     │
Browser <-- Set-Cookie: JSESSIONID=abc... -----┘

Lần sau:
Browser -- Cookie: JSESSIONID=abc... --> Spring MVC
                                      │
                         tìm ID abc... trong session store
                                      │
                         đọc / ghi các session attributes
```

**Session ID là khóa tham chiếu**, không phải nơi phải chứa toàn bộ thông tin của người dùng. Với Servlet `HttpSession` thông thường, state được giữ phía server dưới dạng attribute như `language=vi` hoặc `cartId=...`. Cách lưu bên trong tùy container, cấu hình và hệ thống lưu session. Spring MVC dựa trên Servlet API; Spring Session là một lựa chọn bổ sung để quản lý/lưu trữ session theo hệ thống khác.

Session thường có ba thời điểm quan trọng:

1. **Tạo**: khi ứng dụng thực sự cần lưu state; trong Servlet, `request.getSession(true)` có thể tạo mới nếu chưa có.
2. **Sử dụng/làm mới**: request có ID hợp lệ được liên kết với session; quy tắc inactivity timeout do container/session infrastructure quyết định.
3. **Hết hạn hoặc hủy**: inactivity timeout, logout, invalidate hoặc xóa dữ liệu ở session store làm ID cũ không còn trỏ đến session hợp lệ.

Không nên coi `JSESSIONID` là “người dùng đã đăng nhập”. Một session của khách chưa xác thực vẫn có thể tồn tại; sau login, ứng dụng cần liên kết session đúng principal và vòng đời xác thực.

### 3.1. Vì sao cần session ID khó đoán?

Nếu session ID bị đoán, đánh cắp hoặc bị ép sử dụng, kẻ tấn công có thể dùng nó để truy cập cùng session khi server chỉ dựa vào ID. Do đó:

- Sinh ID bằng cơ chế an toàn của framework/container; không tự chế từ timestamp, user ID hay counter.
- Luôn ưu tiên HTTPS/TLS; cookie xác thực nên có `Secure`, `HttpOnly` và `SameSite` phù hợp.
- Khi đăng nhập hoặc tăng đặc quyền, **đổi/rotate session ID** để phòng session fixation. Servlet có `HttpServletRequest.changeSessionId()`; Spring Security cũng cung cấp quản lý bảo vệ session fixation khi cấu hình đúng.
- Hết hạn và hủy session phía server khi logout. Đặt inactivity timeout phù hợp, cân nhắc giới hạn thời gian tuyệt đối khi nghiệp vụ cần.
- Không ghi session ID vào URL, log truy cập công khai, analytics hoặc thông điệp lỗi. URL có thể lộ qua lịch sử, referrer, bookmark và log.
- Bảo vệ chống XSS: `HttpOnly` hạn chế đọc cookie qua script, nhưng XSS vẫn có thể thực hiện các hành động dưới ngữ cảnh người dùng hoặc đọc dữ liệu trang.

Nếu cần giữ người dùng đăng nhập lâu dài (“remember me”), đó thường là cơ chế quản lý token/vòng đời riêng, không nên chỉ tăng vô hạn tuổi thọ session.

### 3.2. Cookie do server ký khác với session server-side

Không phải mọi cookie có chữ “session” đều chứa ID tra cứu. Có ba cách thiết kế thường gặp:

| Thiết kế | Client giữ gì? | Server cần lưu trạng thái tương ứng? | Cần kiểm tra gì? |
| --- | --- | --- | --- |
| Server-side session | ID ngẫu nhiên | Có, trong bộ nhớ hoặc session store | ID còn hợp lệ, phiên hết hạn/chưa bị thu hồi, quyền hiện tại |
| Cookie chứa dữ liệu có chữ ký/MAC | Dữ liệu và chữ ký | Không nhất thiết cho từng phiên | Chữ ký, thời hạn, audience/ý nghĩa, xử lý thu hồi nếu cần |
| Token như JWT trong cookie | Token chứa claims | Không nhất thiết cho mỗi request | Chữ ký/thuật toán, issuer, audience, expiry, quyền và chính sách thu hồi |

**Chữ ký/MAC bảo vệ tính toàn vẹn, không tự bảo mật nội dung**: người cầm cookie vẫn có thể nhìn dữ liệu không được mã hóa. Mã hóa và chữ ký là những nhu cầu khác nhau. Token chứa claims không khiến giao thức HTTP trở thành stateful; đây là cách mang thông tin trạng thái/xác thực qua từng request.

Quyết định đặt token trong cookie hay trong `Authorization: Bearer ...` ảnh hưởng cách browser đính kèm credential và mô hình đe dọa. Cookie được gửi tự động theo quy tắc phù hợp nên cần đánh giá CSRF; token JavaScript tự đính kèm thường thay đổi cơ chế CSRF nhưng lại cần bảo vệ nơi lưu token khỏi XSS.

## 4. Giới hạn thực tế của trạng thái qua HTTP

### 4.1. Cookie có giới hạn dung lượng và vòng đời

Cookie không phù hợp làm kho dữ liệu lớn. Browser áp dụng giới hạn về kích thước từng cookie, số cookie trên domain/site và tổng dung lượng, nhưng mức chính xác **khác nhau theo browser và phiên bản**. Quy tắc kinh nghiệm là giữ từng cookie nhỏ (thường quanh vài kilobyte hoặc ít hơn), tránh dồn giỏ hàng hoặc hồ sơ người dùng đầy đủ vào đó.

Cookie phù hợp sẽ được gửi trong **nhiều request**, kể cả request không cần chính dữ liệu ấy, làm tăng kích thước header và chi phí truyền tải. Session ID ngắn thường tốt hơn nhồi dữ liệu dài vào cookie.

Cookie có thể bị xóa hoặc từ chối, user dùng private mode, mở nhiều thiết bị, đổi trình duyệt hoặc chặn third-party cookie. **Cookie không phải bộ nhớ vĩnh viễn**, cũng không xác định duy nhất một con người.

### 4.2. Session phía server tạo bài toán mở rộng

Với một server giữ session trong RAM:

```text
Browser -- sid=abc --> Load Balancer
                          ├── Node A: có session abc
                          └── Node B: không có session abc
```

Nếu request sau chuyển sang Node B, state trong RAM của A có thể không được tìm thấy. Một số lựa chọn:

- **Sticky session**: load balancer cố đưa các request của client về cùng instance; dễ bắt đầu, nhưng có rủi ro khi instance lỗi/thay thế và khó điều phối tải.
- **Shared/distributed session store**: nhiều instance truy cập cùng một kho session phù hợp (ví dụ Redis qua cơ chế như Spring Session), cần tính đến TTL, độ trễ, serialization, tính nhất quán và bảo mật.
- **Stateless authentication**: mỗi request mang token xác minh được; giảm nhu cầu lưu session đăng nhập, nhưng logout/thu hồi trước hạn, thay đổi quyền hoặc token bị lộ lại có khó khăn khác.
- **Lưu dữ liệu nghiệp vụ vào database**: giỏ hàng, đơn hàng và các sự kiện quan trọng thường nên có định danh/dữ liệu bền vững riêng, thay vì chỉ nằm trong session dễ hết hạn.

Một session store dùng chung không tự bảo đảm mọi thao tác **atomic**. Hai request đồng thời có thể cùng đọc rồi ghi một attribute, gây lost update. Khi dữ liệu cần tính nhất quán, dùng transaction, atomic update, versioning hoặc cơ chế đồng bộ tương ứng.

### 4.3. Session không thay database và cơ chế phân quyền

Session được dùng cho state ngắn hạn, nhưng không nên biến thành nơi lưu mọi dữ liệu nghiệp vụ:

- Đơn hàng phải tồn tại sau khi session hết hạn; session có thể chỉ giữ khóa `cartId`.
- Giá, vai trò, quyền hạn hoặc trạng thái thanh toán cần được xác minh phía server ở thời điểm thao tác; không được tin một chuỗi client tự gửi.
- Session không bảo đảm “mỗi người dùng chỉ có một tab”: nhiều tab trong cùng browser/profile thường chia sẻ cookie/session; thay đổi ở tab này có thể ảnh hưởng tab khác.
- Session cũng không bảo đảm “mỗi người dùng chỉ có một thiết bị”: các trình duyệt hoặc thiết bị khác có session ID riêng.
- Session timeout thường dựa trên khoảng không hoạt động; có thể cần thêm absolute expiry, giới hạn số phiên hoặc cơ chế logout trên mọi thiết bị theo yêu cầu.

## 5. Cookie, CSRF, XSS và ranh giới tin cậy

### 5.1. CSRF phát sinh khi credential được gửi tự động

Nếu trình duyệt tự đính kèm session cookie cho một request, một trang độc hại có thể cố khiến browser của người dùng gửi request đến ứng dụng đang đăng nhập. Đó là một nguồn rủi ro **cross-site request forgery (CSRF)** khi endpoint chấp nhận thao tác nhạy cảm mà thiếu bảo vệ thích hợp.

Ví dụ xấu: `/transfer?amount=1000` thực hiện chuyển tiền bằng GET chỉ vì trình duyệt đang có cookie phiên. GET được kỳ vọng **safe** theo ngữ nghĩa HTTP; thay đổi nghiệp vụ có ý nghĩa không nên đặt ở GET.

Biện pháp thường phối hợp:

1. Dùng HTTP method đúng ý nghĩa: GET/HEAD chỉ đọc; POST/PUT/PATCH/DELETE cho thay đổi.
2. Dùng **CSRF token** hoặc biện pháp tương đương đã được framework hỗ trợ cho các thao tác có nguy cơ; không coi `SameSite` là lớp bảo vệ duy nhất.
3. Cấu hình `SameSite` phù hợp và xét thêm `Origin`/`Referer` nơi thích hợp.
4. Tránh bật `Access-Control-Allow-Credentials: true` cùng origin tùy ý; chỉ cho phép các origin thực sự cần và kiểm tra phía server. CORS không thay xác thực/ủy quyền.
5. Không tin rằng mọi request `Content-Type: application/json` đều tự chống CSRF; hành vi browser, preflight, endpoint hỗ trợ content type nào và các kênh khác cần được đánh giá.

**CSRF khác XSS**: CSRF lợi dụng browser tự gửi credential; XSS chạy script độc hại trong ngữ cảnh trang. Một ứng dụng có thể cần phòng cả hai.

### 5.2. `HttpOnly`, `Secure`, `SameSite` giải quyết các nguy cơ khác nhau

- `HttpOnly` hạn chế JavaScript đọc cookie; **không** ngăn browser gửi cookie trên request.
- `Secure` hạn chế truyền cookie qua kết nối không an toàn; **không** khiến giá trị cookie được mã hóa hoặc đáng tin nếu client tự sửa.
- `SameSite` hạn chế một số tình huống cookie được gửi cross-site; **không** thay CSRF token/kiểm tra quyền, đặc biệt với các trường hợp cùng site hoặc lỗ hổng khác.
- Mã hóa TLS bảo vệ dữ liệu **trên đường truyền**; không giải quyết việc lộ cookie qua log, XSS khai thác phiên, malware, sai cấu hình hoặc server bị xâm nhập.
- **Authentication** xác định ai đang truy cập; **authorization** xác định tài khoản đó có được thực hiện thao tác cụ thể hay không. Một session hợp lệ không cho phép bỏ qua kiểm tra quyền ở từng tài nguyên.

Trong production nên thiết lập chính sách cookie, timeout, CSRF, CORS và logout cùng với cấu hình Spring Security phù hợp luồng đăng nhập. Không dùng riêng một annotation controller để tuyên bố endpoint đã an toàn.

## 6. Ví dụ Spring MVC: lưu tùy chọn bằng HttpSession

Ví dụ này thể hiện đúng ranh giới: request đầu tiên tạo session và lưu `language`; những request sau dùng cookie chứa session ID để đọc giá trị đã lưu. Đây là bài thực hành cơ chế phiên, **không triển khai đăng nhập hoặc phân quyền**.

Yêu cầu: **JDK 17+**, **Spring Boot 3.x** với dependency `spring-boot-starter-web` (Spring MVC trên Servlet API `jakarta.servlet`). Đặt file sau tại `src/main/java/demo/session/SessionDemoApplication.java` trong dự án Spring Boot đã cấu hình build. Đây là **một file ứng dụng đầy đủ khi có dependency Spring Boot**, không phải chương trình có thể biên dịch bằng `javac` thuần không có thư viện.

```java
package demo.session;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class PreferenceController {
    record PreferenceInput(String language) {}
    record PreferenceOutput(String language) {}

    @PostMapping("/preference")
    ResponseEntity<Void> save(
            @RequestBody PreferenceInput input,
            HttpServletRequest request) {
        if (input == null ||
                (!"vi".equals(input.language()) &&
                 !"en".equals(input.language()))) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "language must be vi or en");
        }

        HttpSession session = request.getSession(true);
        session.setAttribute("language", input.language());
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/preference")
    PreferenceOutput read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String language = session == null
                ? null
                : (String) session.getAttribute("language");
        return new PreferenceOutput(language == null ? "vi" : language);
    }

    @DeleteMapping("/session")
    ResponseEntity<Void> signOutOfDemoSession(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
```

**Giải thích các điểm quan trọng:**

- `getSession(true)` lấy session hiện có hoặc tạo session mới. Container thường phản hồi với `Set-Cookie: JSESSIONID=...` khi cần gửi ID để client dùng lại.
- `getSession(false)` chỉ trả session hiện có, hoặc `null` nếu không có. GET không tạo session ngoài ý muốn.
- `setAttribute("language", ...)` lưu dữ liệu vào session phía server; cookie thông thường chỉ chứa session ID, **không chứa `language=en`**.
- `invalidate()` hủy session phía server. Browser có thể vẫn giữ cookie chứa ID cũ, nhưng ID đó không còn truy cập được session cũ.
- POST trả `204 No Content`, GET trả JSON và status 200, DELETE trả 204. Các trạng thái này do controller chỉ định hoặc được Spring MVC chọn theo quy tắc mapping.
- Hai request đồng thời ghi chung attribute trên cùng session có thể **ghi đè nhau**; ví dụ chưa xử lý xung đột cập nhật. Ở tình huống nghiệp vụ phức tạp, cần thiết kế đồng thời và nhất quán dữ liệu.
- Endpoint DELETE này minh họa hủy session; nếu dùng cho ứng dụng thật có cookie đăng nhập thì phải tích hợp Spring Security, CSRF defense, và quy trình logout phù hợp.

### 6.1. Tự kiểm tra bằng curl và cookie jar

Giả sử ứng dụng chạy tại `http://localhost:8080`. Ví dụ lệnh sau theo cú pháp shell Bash; trên Windows PowerShell nên gọi `curl.exe` và điều chỉnh cách đặt dấu nháy JSON nếu cần.

**A. GET chưa gửi cookie** — chưa có session nên nhận mặc định:

```bash
curl -i http://localhost:8080/api/preference
```

Response body tương đương:

```json
{"language":"vi"}
```

**B. POST tạo session**, lưu cookie server gửi về vào `cookies.txt`:

```bash
curl -i -c cookies.txt -X POST \
  http://localhost:8080/api/preference \
  -H 'Content-Type: application/json' \
  -d '{"language":"en"}'
```

Status mong đợi: `204 No Content`. Trong một thiết lập Servlet thông thường, response khi tạo session có header gần giống:

```http
Set-Cookie: JSESSIONID=<ID-do-server-sinh>; Path=/; HttpOnly
```

Tên cookie, cờ bảo vệ và các thuộc tính khác **phụ thuộc cấu hình/HTTPS/container**. Dòng trên chỉ là ví dụ minh họa, không phải output bất biến của mọi môi trường.

**C. GET có cookie jar** — curl gửi cookie đã lưu:

```bash
curl -i -b cookies.txt http://localhost:8080/api/preference
```

Body tương đương:

```json
{"language":"en"}
```

**D. GET không gửi cookie** vẫn cho:

```bash
curl -i http://localhost:8080/api/preference
```

```json
{"language":"vi"}
```

**E. Hủy session rồi thử cookie cũ:**

```bash
curl -i -b cookies.txt -X DELETE http://localhost:8080/api/session
curl -i -b cookies.txt http://localhost:8080/api/preference
```

Lệnh DELETE trả 204; GET sau đó trả mặc định `{"language":"vi"}` dù curl có thể vẫn gửi ID cũ. Đó là minh chứng **server-side invalidation**.

Nếu dùng HTTP client khác, nhớ phân biệt các chế độ “giữ cookie tự động” và “không giữ cookie”; không dùng kết quả lẫn nhau để kết luận sai.

### 6.2. Cấu hình cookie và timeout trong Spring Boot

Ví dụ **chỉ áp dụng khi triển khai HTTPS** với cấu hình Spring Boot Servlet session phù hợp, trong `application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Ý nghĩa:

- `timeout: 30m` đặt mục tiêu thời gian không hoạt động của session theo cơ chế/container đang dùng, **không bảo đảm** một giới hạn tồn tại tuyệt đối 30 phút cho mọi phiên.
- `http-only` giúp ngăn script trực tiếp đọc cookie phiên.
- `secure: true` yêu cầu cookie được gửi qua kết nối an toàn; trên local HTTP cần cân nhắc cấu hình phát triển riêng, không âm thầm tắt bảo vệ trên production.
- `same-site: lax` giới hạn một số trường hợp cross-site; tùy luồng đăng nhập/cross-site legitimate mà chính sách cần thay đổi.

Khi dùng reverse proxy TLS termination, phải cấu hình nhận diện scheme/forwarded headers đáng tin cậy cho ứng dụng. Khi dùng Spring Session hoặc custom cookie serializer, cần kiểm tra cấu hình thực tế của thành phần quản lý cookie/session đó; không suy luận đơn thuần từ một đoạn YAML.

## 7. Các tình huống lỗi cần chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Mỗi request có phiên mới | Client không lưu/gửi cookie, `Secure` trên HTTP, sai Domain/Path, cookie bị chặn | Xem `Set-Cookie` response, `Cookie` request, URL và cookie jar trong DevTools |
| Cookie có nhưng session như mất | Session hết hạn, server restart, load balancer chuyển instance, session store lỗi, ID không hợp lệ | Kiểm tra session store/TTL, routing, logs có che ID |
| CORS lỗi với fetch dùng cookie | Origin chưa được phép, credentials/cookie policy không phù hợp | Cấu hình origin cụ thể, credentials, SameSite/Secure; kiểm tra preflight |
| Logout rồi vẫn thấy dữ liệu | Server chưa invalidate, token khác còn hiệu lực, trình duyệt cache dữ liệu | Kiểm tra invalidate/thu hồi credential, cache policy và dữ liệu client |
| Hai tab thấy cùng tùy chọn | Hai tab đang dùng cùng cookie/session | Kiểm tra thiết kế dữ liệu theo tab nếu thực sự cần tách |
| Session ID bị lộ | Log, URL, XSS hoặc kênh không an toàn | Loại ID khỏi log/URL, TLS, cookie flags, rotation, revoke |
| GET vô tình tạo nhiều session | Gọi `getSession()` thay vì `getSession(false)` trong luồng chỉ đọc | Rà lại chỗ tạo session và response `Set-Cookie` |
| Session store tăng dung lượng | Lưu object quá lớn, timeout quá dài, cleanup không hiệu quả | Chỉ lưu thuộc tính cần thiết, theo dõi TTL/capacity |
| Request cross-site có lúc gửi cookie, có lúc không | Khác origin/site, `SameSite`, browser policy, HTTPS hoặc điều kiện navigation | Phân tích request context và chính sách của từng browser |

Không dùng việc “thấy cookie trong DevTools” để chứng minh server nhận đúng nó: cần xem **request header thực tế** và đối chiếu thời hạn, scope, session store.

## 8. Lỗi hiểu sai thường gặp

1. **“HTTP stateless nên Spring không thể có session.”** Sai: stateful session là tầng ứng dụng ghép các request bằng ID.
2. **“Cookie là session.”** Sai: cookie là cơ chế lưu/gửi dữ liệu phía client; session là cách quản lý trạng thái và vòng đời, có thể dùng hoặc không dùng cookie.
3. **“Cookie có `HttpOnly` thì không thể bị lợi dụng.”** Sai: browser vẫn gửi cookie tự động; XSS còn có cách thực hiện hành động và CSRF vẫn cần xem xét.
4. **“Đặt `Secure` là cookie được mã hóa.”** Sai: `Secure` giới hạn kênh gửi, không mã hóa giá trị được lưu trên client.
5. **“CORS chặn mọi yêu cầu đến API từ bên ngoài.”** Sai: CORS là chính sách trình duyệt, không thay authorization của server; client không phải browser có thể gọi API theo điều kiện riêng.
6. **“Tất cả cookie sẽ sống đúng số giây cấu hình.”** Sai: browser có thể xóa/chặn; session phía server cũng có hạn riêng.
7. **“Mỗi tab có một session độc lập.”** Sai trong mô hình cookie thông thường của cùng browser profile/site; nhiều tab hay dùng chung session.
8. **“Sticky session đảm bảo state không mất.”** Sai: instance chết/redeploy vẫn có thể mất dữ liệu session trong RAM.
9. **“JWT luôn tốt hơn server session.”** Không có kết luận chung: token giảm truy vấn phiên trong một số thiết kế nhưng làm thu hồi tức thì/phân quyền thay đổi phức tạp hơn.
10. **“Xóa cookie là đủ logout.”** Sai với session server-side; cần vô hiệu ID cũ trên server, kết thúc trạng thái xác thực và xử lý token liên quan.
11. **“Chỉ có một session cho cả một người dùng.”** Không nhất thiết; mỗi thiết bị/browser có thể có session riêng, và một browser có thể có nhiều phiên theo domain hoặc cách tổ chức ứng dụng.
12. **“SameSite và CORS là cùng một thứ.”** Sai: SameSite quyết định một số hoàn cảnh gửi cookie; CORS điều khiển một số tương tác cross-origin của browser.

## 9. Câu hỏi tự kiểm tra và cách áp dụng

1. **Không có cookie:** Vì sao hai request từ cùng laptop vẫn chưa đủ để server xác định cùng một phiên? Hãy nêu một thiết kế dùng `Authorization` thay cookie.
2. **Có cookie, không có session:** Browser gửi `Cookie: JSESSIONID=abc` nhưng session store không còn `abc`. Server có thể suy ra người dùng vẫn đăng nhập không? Vì sao?
3. **Cookie scope:** `Path=/admin` có ngăn JavaScript ở `/` truy cập tất cả endpoint quản trị hay thay thế xác thực không? Phân biệt cookie scope với authorization.
4. **Hết hạn:** Vì sao `Max-Age=3600` không đồng nghĩa server giữ session hợp lệ đúng một giờ? Nếu muốn logout ngay trên mọi thiết bị cần quản lý trạng thái nào?
5. **Security:** Với cookie đăng nhập, giải thích tác dụng riêng của `Secure`, `HttpOnly`, `SameSite` và CSRF token. Điểm nào không thay cho kiểm tra quyền?
6. **Mở rộng:** Nếu session lưu trong RAM của Node A nhưng request tới Node B, điều gì xảy ra? So sánh sticky session với shared session store.
7. **Thực hành:** Chạy ví dụ ở mục 6, kiểm tra `Set-Cookie` và `Cookie`; sau đó DELETE session và thử GET cùng cookie cũ. Hãy chỉ rõ dữ liệu nào nằm ở client và dữ liệu nào ở server.
8. **Thiết kế:** Với ngôn ngữ giao diện, giỏ hàng và đơn hàng đã thanh toán, bạn sẽ chọn cookie nhỏ, session attribute hay database bền vững? Giải thích khi browser xóa cookie hoặc session hết hạn.

**Điểm cần nắm:** HTTP không tự duy trì phiên; cookie là phương tiện client lưu/gửi dữ liệu có phạm vi và thời hạn; session là cơ chế ứng dụng gắn nhiều request với trạng thái. Một ứng dụng web tốt phải giải quyết đồng thời **danh tính, quyền truy cập, vòng đời phiên, rủi ro CSRF/XSS, giới hạn browser và tính nhất quán khi mở rộng nhiều server**. Hiểu những ranh giới đó trước khi triển khai đăng nhập, session management hoặc Spring Security.
