# HTTP method an toàn và hành động làm thay đổi trạng thái

## Mục tiêu bài học

Trình duyệt có thể tự phát sinh yêu cầu HTTP khi người dùng bấm liên kết, tải hình, xem trước một trang hoặc được điều hướng từ website khác. Một số yêu cầu có thể tự mang cookie phiên và thông tin xác thực đã lưu. Do đó, **HTTP method có ý nghĩa bảo mật**, đặc biệt đối với ứng dụng dùng session và bảo vệ **Cross-Site Request Forgery (CSRF)**.

Bài thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**: áp dụng các lớp phòng vệ HTTP và trình duyệt bằng Spring Security, từ CSRF, CORS, security headers, CSP, HSTS, HTTP firewall đến bảo vệ session; đồng thời triển khai và chẩn đoán trên cả **Servlet** và **Reactive (WebFlux)**.

Sau bài học, bạn có thể:

1. Phân biệt **safe method**, **unsafe method**, **idempotent method** và tính **cacheable** của một yêu cầu.
2. Giải thích vì sao **GET, HEAD, OPTIONS và TRACE** được HTTP định nghĩa là safe, nhưng không có nghĩa server nên cho phép TRACE hay bỏ qua xác thực.
3. Thiết kế URL sao cho các thao tác như **đặt hàng, chuyển tiền, đổi mật khẩu, hủy đơn và đăng xuất** sử dụng method có ngữ nghĩa phù hợp.
4. Nhận diện rủi ro từ liên kết GET, tải ảnh, crawler, prefetch và cookie **SameSite=Lax**.
5. Giải thích cơ chế mặc định của Spring Security về CSRF theo method, áp dụng trên **HttpSecurity** (Servlet) và **ServerHttpSecurity** (WebFlux).
6. Kiểm tra một endpoint bằng DevTools, curl và các công cụ kiểm thử Spring Security, phân biệt lỗi **CSRF, CORS, xác thực và phân quyền**.

## 1. “An toàn” trong HTTP có nghĩa gì?

Trong ngữ nghĩa HTTP, một method được coi là **safe** nếu **hành động mà client yêu cầu không nhằm làm thay đổi trạng thái ứng dụng trên server**. Nói cách khác, client thực hiện method đó với mục đích truy xuất thông tin hoặc kiểm tra khả năng của tài nguyên, không yêu cầu server thực hiện tác vụ nghiệp vụ gây tác dụng phụ.

Ví dụ về hành vi mong đợi của một API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
~~~

Server trả thông tin đơn hàng, không tự tạo đơn hàng mới, thu tiền, xóa đơn hoặc xác nhận giao hàng chỉ vì GET được gọi.

Ngược lại:

~~~http
POST /api/orders HTTP/1.1
Host: shop.example.com
Content-Type: application/json

{"productId":42,"quantity":1}
~~~

Đây là một yêu cầu **chủ động tạo đơn hàng**, vì thế không thuộc nhóm safe.

### 1.1. Safe không có nghĩa server tuyệt đối không ghi gì

Việc xử lý một yêu cầu GET có thể tạo các tác dụng phụ phụ trợ, chẳng hạn:

- Ghi access log, trace hoặc số liệu vận hành.
- Tăng bộ đếm kỹ thuật phục vụ giám sát.
- Làm đầy cache, tạo bản sao tạm cho mục đích tối ưu truy xuất.

Những thay đổi phụ trợ này không nhất thiết vi phạm ngữ nghĩa safe, miễn **hành động mà client yêu cầu** không phải là thao tác thay đổi trạng thái có ý nghĩa nghiệp vụ.

Tuy vậy, nếu GET **đánh dấu hóa đơn đã thanh toán**, **ghi nhận sự đồng ý pháp lý**, **trừ lượt sử dụng có tính phí** hoặc **thay đổi trạng thái tài khoản**, thì endpoint đó đang triển khai sai ngữ nghĩa safe. Không thể gọi đó là GET an toàn chỉ vì server trả HTTP 200.

**Câu hỏi thiết kế quan trọng:** Nếu một crawler, trình duyệt hoặc công cụ xem trước liên kết tự mở URL, hành động nghiệp vụ nào sẽ xảy ra? Với một URL GET đúng nghĩa, không được có hành động làm thay đổi trạng thái theo ý định nghiệp vụ.

### 1.2. Safe không đồng nghĩa được công khai

Một yêu cầu GET để xem hồ sơ cá nhân vẫn phải được **xác thực và phân quyền**. Safe chỉ nói đến ngữ nghĩa hành động, không nói rằng người gọi đã có quyền.

Ví dụ:

~~~text
GET /api/users/me             → đọc dữ liệu, nhưng phải đăng nhập
GET /api/admin/audit-events   → đọc dữ liệu, nhưng chỉ quản trị viên có quyền
GET /api/public/catalog      → đọc dữ liệu công khai
~~~

Cả ba đều có thể là safe. Chính sách authentication/authorization của chúng có thể hoàn toàn khác nhau.

## 2. Phân loại các HTTP method phổ biến

Bảng sau nói về **ngữ nghĩa method theo HTTP**, không phải bảo đảm rằng mọi ứng dụng thực tế đã triển khai đúng.

| Method | Safe? | Idempotent? | Mục đích thông thường |
| --- | --- | --- | --- |
| **GET** | Có | Có | Truy xuất biểu diễn của tài nguyên. |
| **HEAD** | Có | Có | Nhận metadata của tài nguyên như GET nhưng không nhận response body. |
| **OPTIONS** | Có | Có | Hỏi về tùy chọn truyền thông hoặc khả năng của tài nguyên; còn dùng trong CORS preflight. |
| **TRACE** | Có theo ngữ nghĩa HTTP | Có | Kiểm tra đường truyền bằng việc phản chiếu thông điệp nhận được; thường bị vô hiệu hóa vì lý do bảo mật. |
| **POST** | Không | Không được bảo đảm | Gửi dữ liệu để server xử lý, tạo tài nguyên hoặc thực hiện hành động. |
| **PUT** | Không | Có theo ngữ nghĩa HTTP | Tạo hoặc thay thế trạng thái tài nguyên ở URI đích. |
| **PATCH** | Không | Không được bảo đảm | Cập nhật một phần tài nguyên. |
| **DELETE** | Không | Có theo ngữ nghĩa HTTP | Yêu cầu xóa liên kết giữa URI và chức năng/trạng thái hiện tại của tài nguyên. |

Lưu ý:

- Một ứng dụng có thể thiết kế **POST hoặc PATCH mang tính idempotent**, nhưng HTTP không mặc định bảo đảm điều đó.
- **PUT/DELETE idempotent vẫn là unsafe**: chúng yêu cầu thay đổi trạng thái. Đây là điểm dễ nhầm khi đánh giá CSRF.
- **TRACE được đặc tả là safe và idempotent về mặt ngữ nghĩa**, nhưng không vì thế nên bật TRACE trong ứng dụng. Nhiều hệ thống chặn TRACE để hạn chế việc phản chiếu request, dữ liệu nhạy cảm hoặc lộ thông tin qua công cụ chẩn đoán.
- **Cacheable** là thuộc tính riêng, không thể suy ra chỉ từ safe hoặc idempotent. GET/HEAD thường được cache theo các điều kiện HTTP; một số phản hồi POST có thể được cache khi thỏa yêu cầu đặc tả và chính sách triển khai, dù không phổ biến.

### 2.1. Sơ đồ quyết định khi thiết kế endpoint

~~~mermaid
flowchart TD
    A["Người dùng/client muốn thực hiện hành động gì?"] --> B{"Hành động có chủ đích thay đổi trạng thái nghiệp vụ?"}
    B -->|Không| C["Dùng ngữ nghĩa đọc: GET hoặc HEAD khi thích hợp"]
    B -->|Có| D{"Mô hình tài nguyên và cập nhật là gì?"}
    D -->|Tạo hoặc tác vụ| E["POST"]
    D -->|Thay thế trạng thái tài nguyên| F["PUT"]
    D -->|Cập nhật một phần| G["PATCH"]
    D -->|Xóa tài nguyên| H["DELETE"]
    C --> I["Vẫn xác thực/phân quyền và bảo vệ dữ liệu phản hồi"]
    E --> J["Xác thực, phân quyền và chống CSRF khi có credential tự gửi"]
    F --> J
    G --> J
    H --> J
~~~

Sơ đồ là cách chọn method ở mức thiết kế ban đầu. API thực tế cần cân nhắc hợp đồng nghiệp vụ, khả năng lặp lại request, giao dịch và cách các client đang sử dụng endpoint.

## 3. Safe khác idempotent như thế nào?

Hai thuật ngữ thường xuất hiện cùng nhau nhưng **không tương đương**.

- **Safe:** hành động được yêu cầu không nhằm thay đổi trạng thái ứng dụng trên server.
- **Idempotent:** hiệu quả dự định trên server của **nhiều request giống nhau** tương đương hiệu quả dự định của **một request**. Server có thể vẫn ghi log hoặc sinh metadata khác nhau.

Mọi method safe tiêu chuẩn đều idempotent theo ngữ nghĩa HTTP. Chiều ngược lại **không đúng**.

### 3.1. GET: safe và idempotent

~~~http
GET /api/products/42 HTTP/1.1
Host: shop.example.com
~~~

Gọi nhiều lần chỉ yêu cầu đọc sản phẩm. Dữ liệu sản phẩm có thể đổi do một người dùng khác cập nhật giữa các lần gọi; điều đó **không làm GET mất tính safe**.

### 3.2. PUT: idempotent nhưng unsafe

~~~http
PUT /api/profile/preferences HTTP/1.1
Host: app.example.com
Content-Type: application/json

{"theme":"dark"}
~~~

Nếu hai request PUT cùng đặt trạng thái theme=dark, hiệu quả dự định của việc thực hiện hai lần giống một lần: trạng thái cuối là dark. Tuy vậy, client **đã yêu cầu thay đổi trạng thái**, nên PUT là unsafe.

### 3.3. DELETE: idempotent nhưng unsafe

~~~http
DELETE /api/saved-items/42 HTTP/1.1
Host: app.example.com
~~~

Gọi một lần làm mục đã lưu không còn tồn tại; gọi thêm lần nữa về mặt **hiệu quả dự định** vẫn là mục đó không tồn tại. Server có thể trả **204** ở lần đầu và **404** ở lần sau; **status HTTP có thể khác mà hành động vẫn idempotent**.

Nếu triển khai DELETE thực hiện một hành động mới ở mỗi lần gọi, ví dụ tính thêm tiền mỗi lần xóa, thì ứng dụng đang phá vỡ tính idempotent được mong đợi của DELETE.

### 3.4. POST: thường không idempotent

~~~http
POST /api/orders HTTP/1.1
Host: shop.example.com
Content-Type: application/json

{"productId":42,"quantity":1}
~~~

Nếu client gửi hai POST giống nhau, server có thể tạo **hai đơn hàng**. Với thao tác có giá trị tài chính, cần thiết kế cách chống xử lý trùng khi retry hoặc người dùng bấm hai lần, chẳng hạn **idempotency key** do server kiểm tra và lưu đúng phạm vi.

~~~http
POST /api/payments HTTP/1.1
Host: pay.example.com
Idempotency-Key: 8fb169c0-2e45-4aa5-b419-demo-example
Content-Type: application/json

{"orderId":"o-42","amount":100000}
~~~

Đây là ví dụ về hợp đồng API tự thiết kế: header Idempotency-Key **không tự có tác dụng chỉ vì client gửi**; server phải định nghĩa cơ chế nhận diện request trùng, kiểm soát phạm vi, thời hạn và lưu kết quả đúng cách.

**Chống xử lý trùng không phải chống CSRF.** Một POST có idempotency key vẫn là unsafe và phải chịu kiểm tra xác thực, phân quyền, CSRF khi áp dụng mô hình session/cookie.

### 3.5. PATCH: an toàn về mặt lặp lại hay không là do thao tác

Hai PATCH khác nhau:

~~~http
PATCH /api/counters/42 HTTP/1.1
Content-Type: application/json

{"incrementBy":1}
~~~

Request trên mang ý nghĩa tăng 1 mỗi lần nên không idempotent.

~~~http
PATCH /api/profiles/42 HTTP/1.1
Content-Type: application/json

{"displayName":"An"}
~~~

Nếu endpoint chỉ đặt displayName thành An, thao tác có thể được thiết kế idempotent. Dù vậy, **PATCH vẫn unsafe** vì yêu cầu thay đổi trạng thái. Không thay đổi CSRF policy chỉ vì một kiểu PATCH cụ thể có tính idempotent.

## 4. Vì sao GET thay đổi trạng thái đặc biệt nguy hiểm?

Trình duyệt, crawler và các hệ thống hạ tầng thường giả định GET có thể được gọi nhằm **xem** dữ liệu, vì thế chúng có thể chủ động truy cập một URL GET mà không nhằm xác nhận hành động nghiệp vụ.

### 4.1. Liên kết, ảnh và bản xem trước

Một số ngữ cảnh có thể phát sinh GET:

~~~html
<a href="https://app.example.com/api/orders/42/cancel">
  Xem đơn hàng
</a>

<img src="https://app.example.com/api/orders/42/cancel" alt="Preview">
~~~

Nếu GET đến URL **/cancel** thực sự hủy đơn hàng thì việc bấm liên kết, nhúng ảnh hoặc crawler truy cập URL có thể **kích hoạt hủy đơn ngoài ý muốn**. Đây là thiết kế sai về ngữ nghĩa HTTP.

Các trình duyệt hoặc dịch vụ còn có thể:

- Tạo **link preview** khi người dùng chia sẻ URL.
- **Prefetch/prerender** tài nguyên hoặc trang, tùy trình duyệt và cấu hình.
- Tự theo liên kết để lập chỉ mục hoặc kiểm tra trạng thái.
- Retry yêu cầu đọc trong một số tình huống mạng.
- Sử dụng GET để kiểm tra đường dẫn hoặc làm ấm cache.

Không phải mọi trình duyệt thực hiện tất cả hành vi trên, nhưng **server không được dựa vào giả định rằng GET chỉ được gửi sau một cú nhấp có chủ ý**.

### 4.2. Cookie SameSite=Lax và điều hướng GET

Giả sử người dùng đã đăng nhập tại **https://bank.example**; trình duyệt giữ session cookie:

~~~http
Set-Cookie: session=opaque; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Kẻ tấn công gửi một liên kết từ **https://outside.test** dẫn tới:

~~~text
https://bank.example/transfer?to=someone&amount=100
~~~

Khi người dùng bấm liên kết, trình duyệt thực hiện **điều hướng cấp cao nhất bằng GET**. Cookie **SameSite=Lax thường được gửi** trong kiểu điều hướng cross-site này khi các điều kiện cookie khác phù hợp.

Nếu endpoint GET lại thực hiện chuyển tiền thì **SameSite=Lax không bảo vệ được thiết kế đó**. Ngoài ra, request GET có thể đến máy chủ dù trang nguồn khác origin không được phép đọc nội dung phản hồi.

Bài học: **Không thực hiện chuyển tiền, xác nhận email mang tác dụng nghiệp vụ, đổi mật khẩu, xóa dữ liệu hoặc đăng xuất qua GET chỉ vì có session cookie và SameSite.**

### 4.3. GET nhúng tài nguyên và GET điều hướng không hoàn toàn giống nhau

SameSite=Lax thường phân biệt **top-level navigation** với các dạng request subresource như ảnh, iframe hoặc fetch cross-site. Một request ảnh cross-site có thể **không mang cookie Lax**, trong khi người dùng bấm liên kết GET dẫn tới trang đích có thể **mang cookie Lax**.

Vì vậy không nên nói tuyệt đối rằng “mọi GET đều có cookie” hoặc “cookie Lax chặn mọi GET cross-site”. Cần xét **site, loại request, method, credentials và thuộc tính cookie**.

Bất kể cookie có được gửi hay không, GET vẫn phải giữ đúng ngữ nghĩa safe. Một API chỉ an toàn khi browser tình cờ không gửi cookie là một API có thiết kế rủi ro.

### 4.4. Không dùng GET cho đăng xuất

Đăng xuất thường vô hiệu hóa session, làm mới trạng thái xác thực hoặc xóa credential. Đây là **hành động làm thay đổi trạng thái**, không phải hoạt động đọc.

Một liên kết GET như:

~~~html
<a href="/logout">Đăng xuất</a>
~~~

có thể tạo hành vi không mong muốn nếu ứng dụng cho phép GET /logout làm mất hiệu lực session. Trong Spring Security khi bật CSRF, cơ chế logout mặc định sử dụng **POST với CSRF token** cho thao tác logout, thay vì biến GET thành endpoint thay đổi trạng thái chỉ để tiện làm liên kết.

Ví dụ form đăng xuất phía server-rendered với token đã được cấp hợp lệ:

~~~html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CAP">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Giá trị token ở đây là **chỗ giữ chỗ minh họa**, server phải cấp và xác thực token thực. Với các template engine tích hợp Spring Security, cách chèn trường CSRF có thể được hỗ trợ tự động tùy cấu hình.

## 5. CSRF gắn với hành động thay đổi trạng thái ra sao?

**Cross-Site Request Forgery (CSRF)** là tình huống bên ngoài khiến trình duyệt của một người dùng đã được xác thực thực hiện thao tác không mong muốn. Rủi ro điển hình xuất hiện khi cookie/session hay dạng credential khác được **browser tự đính kèm**.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant A as Website ngoài
    participant S as Spring Security / Ứng dụng
    U->>B: Đăng nhập ứng dụng
    B->>S: Yêu cầu đăng nhập
    S-->>B: Session cookie
    U->>A: Truy cập website ngoài
    A->>B: Kích hoạt request đến endpoint thay đổi trạng thái
    B->>S: Request (có thể kèm cookie nếu policy cho phép)
    S->>S: Kiểm tra xác thực, CSRF token và quyền
    alt Token/điều kiện không hợp lệ
        S-->>B: 403 hoặc phản hồi từ chối phù hợp
    else Hợp lệ
        S->>S: Thực hiện thao tác được phép
        S-->>B: Phản hồi nghiệp vụ
    end
~~~

Điểm quan trọng:

- **Có cookie hợp lệ** cho biết browser có thể đang sử dụng session của người dùng, **không chứng minh người dùng chủ ý khởi tạo request**.
- **SOP/CORS** chủ yếu điều chỉnh quyền mã trình duyệt đọc phản hồi cross-origin; một số request qua form hoặc điều hướng vẫn có thể tới server.
- **SameSite** giảm rủi ro khi cookie được dùng trong nhiều ngữ cảnh cross-site, nhưng một subdomain **same-site, cross-origin** không đáng tin vẫn có thể khởi tạo request.
- **CSRF token** là lớp phòng vệ ứng dụng cho các thao tác thay đổi trạng thái. Server phải cấp và kiểm tra token theo mô hình bảo mật được chọn.
- **Authentication và authorization** vẫn cần thiết dù CSRF token hợp lệ. Token CSRF không cấp quyền quản trị hay quyền truy cập tài nguyên của người khác.

### 5.1. Những phương thức nào Spring Security thường kiểm tra CSRF?

Với các cấu hình mặc định của Spring Security Servlet và WebFlux, bảo vệ CSRF được bật; bộ xác định mặc định thường coi **GET, HEAD, TRACE, OPTIONS** là những method không cần CSRF token và yêu cầu CSRF token cho **các method còn lại**, như POST, PUT, PATCH, DELETE.

Có thể hình dung:

~~~text
GET     /api/orders/42       → không yêu cầu CSRF token theo matcher mặc định
HEAD    /api/orders/42       → không yêu cầu CSRF token theo matcher mặc định
OPTIONS /api/orders          → không yêu cầu CSRF token theo matcher mặc định
TRACE   /diagnostics        → không yêu cầu CSRF token theo matcher mặc định

POST    /api/orders          → yêu cầu CSRF token
PUT     /api/orders/42       → yêu cầu CSRF token
PATCH   /api/orders/42       → yêu cầu CSRF token
DELETE  /api/orders/42       → yêu cầu CSRF token
~~~

Ví dụ trên giả định yêu cầu đi qua **security filter chain** có CSRF mặc định, các tùy chỉnh không vô hiệu hóa CSRF và trình xử lý token phù hợp. Đây là **quy tắc matcher**, không phải bằng chứng rằng endpoint GET không thể bị lạm dụng hay endpoint POST chỉ cần CSRF mà không cần xác thực.

**Nếu lập trình viên vô tình tạo GET /api/orders/42/cancel thực hiện hủy đơn, Spring Security mặc định sẽ không chặn GET đó bằng CSRF token**. Vấn đề cần sửa là **ngữ nghĩa và thiết kế endpoint**.

### 5.2. Idempotent vẫn cần CSRF

Một số người cho rằng PUT hoặc DELETE idempotent nên không cần chống CSRF. Điều này sai.

- PUT thay đổi nội dung hồ sơ, có thể làm mất dữ liệu người dùng.
- DELETE xóa tài nguyên, dù gọi lại nhiều lần không đổi trạng thái cuối.
- PATCH có thể cập nhật dữ liệu nhạy cảm.
- POST thường khởi tạo tác vụ hoặc tạo đối tượng mới.

Tất cả đều là **unsafe**. Nếu xác thực dựa trên cookie tự gửi, chúng là mục tiêu cần được đánh giá và bảo vệ CSRF theo mô hình ứng dụng.

### 5.3. Không tắt CSRF để chữa mọi lỗi 403

Khi SPA gửi POST mà Spring Security trả 403, nguyên nhân có thể là CSRF token không có/sai, nhưng cũng có thể do phân quyền. Tắt CSRF hàng loạt chỉ vì thấy 403 có thể làm mất lớp phòng vệ quan trọng.

Nếu API thực sự **stateless** và chỉ chấp nhận Bearer token trong Authorization do mã client chủ động cấp (không có credential tự động gửi có thể dùng cho các hành động), mô hình đe dọa CSRF có thể khác. Nhưng trước khi quyết định tùy chỉnh hoặc vô hiệu hóa CSRF, phải kiểm tra **cơ chế xác thực thực tế**, ví dụ cookie vẫn dùng để refresh token hay endpoint đăng nhập vẫn dựa trên session không.

**Không mặc định xem mọi API REST là miễn nhiễm CSRF.** Cách trình duyệt gửi credential quan trọng hơn tên gọi “REST”.

## 6. HEAD, OPTIONS và TRACE: safe nhưng không thể bỏ qua thiết kế bảo mật

### 6.1. HEAD phải nhất quán với ngữ nghĩa GET

**HEAD** yêu cầu metadata giống GET nhưng **response không có body**. Nó hữu ích để kiểm tra sự tồn tại, header, kích thước hoặc trạng thái tài nguyên mà không tải nội dung.

~~~http
HEAD /api/reports/42 HTTP/1.1
Host: app.example.com
~~~

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Cache-Control: private, no-store
~~~

HEAD không nên làm thay đổi trạng thái nghiệp vụ. Endpoint nào đang “xác nhận đã đọc báo cáo” khi HEAD được gọi là ví dụ vi phạm ngữ nghĩa safe.

Do nhiều framework có thể ánh xạ HEAD qua xử lý GET trong những trường hợp thích hợp, càng cần bảo đảm logic GET chỉ đọc. Nếu GET có tác dụng phụ, HEAD có thể gây tác dụng phụ theo đường xử lý tương ứng.

### 6.2. OPTIONS thường được trình duyệt dùng làm CORS preflight

Một SPA tại **https://app.example.com** muốn gọi API tại **https://api.example.com** bằng POST JSON kèm header CSRF:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Đây là **preflight** để browser hỏi server có cho phép một loại yêu cầu cross-origin hay không. Nó **không phải** yêu cầu đặt hàng và không phải bước xác thực người dùng.

Phản hồi ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Trong môi trường dùng session, preflight **thường không mang cookie**, vì vậy cần bảo đảm **CORS được xử lý trước các bước có thể chặn preflight do thiếu xác thực**. Browser chỉ gửi POST thực theo quy tắc CORS khi preflight được chấp nhận. **POST vẫn phải kiểm tra CSRF token và quyền**.

Không nên thay đổi trạng thái nghiệp vụ khi nhận OPTIONS. Nếu một OPTIONS /api/orders lại tạo đơn hàng, đó là lỗi thiết kế, dù OPTIONS thuộc nhóm safe.

### 6.3. TRACE: safe theo đặc tả, nhưng nên hạn chế hoặc vô hiệu hóa

TRACE là method chẩn đoán phản chiếu thông điệp đã nhận. Tuy được đặc tả safe và idempotent, việc bật TRACE có thể làm tăng bề mặt rò thông tin trong những kiến trúc cụ thể (chẳng hạn phản chiếu header nhạy cảm). Nó thường không cần thiết cho ứng dụng kinh doanh.

Một hệ thống có thể **chặn TRACE** tại web server, reverse proxy, container hoặc tầng bảo mật thích hợp. **Việc Spring Security không yêu cầu CSRF token cho TRACE theo matcher mặc định không phải khuyến nghị bật TRACE**.

Khi chẩn đoán, phân biệt:

- **CSRF matcher**: xem method có cần CSRF token theo cấu hình hay không.
- **HTTP firewall / web server / proxy**: có cho phép method đó đi qua hay không.
- **Authorization**: người gọi có được truy cập chức năng tương ứng không.

Ba quyết định có thể độc lập với nhau.

## 7. Thiết kế endpoint nghiệp vụ theo đúng method

Xét một API quản lý đơn hàng. Thiết kế rõ ràng giúp frontend, trình duyệt, crawler, cache và Spring Security hiểu đúng ý định request.

| Tác vụ | Endpoint đề xuất | Ngữ nghĩa |
| --- | --- | --- |
| Xem danh sách đơn | GET /api/orders | Safe: chỉ truy vấn. |
| Xem chi tiết đơn | GET /api/orders/{id} | Safe: chỉ đọc. |
| Kiểm tra metadata đơn | HEAD /api/orders/{id} | Safe: không trả body. |
| Tạo đơn hàng | POST /api/orders | Unsafe: tạo tài nguyên. |
| Thay thế thông tin có thể chỉnh | PUT /api/orders/{id} | Unsafe, idempotent theo hợp đồng. |
| Cập nhật một số trường | PATCH /api/orders/{id} | Unsafe, có thể idempotent hoặc không. |
| Hủy đơn | POST /api/orders/{id}/cancel | Unsafe: thực hiện tác vụ nghiệp vụ. |
| Xóa mục nháp | DELETE /api/draft-orders/{id} | Unsafe, idempotent theo ngữ nghĩa. |
| Đăng xuất | POST /logout | Unsafe: thay đổi trạng thái xác thực. |

Một thao tác nghiệp vụ như **hủy đơn** có thể biểu diễn bằng POST tới một action endpoint. Trong kiến trúc coi trạng thái hủy là một tài nguyên riêng, có thể chọn PUT/PATCH theo hợp đồng. Điều bắt buộc là **không dùng GET chỉ vì nó dễ tạo liên kết**.

### 7.1. Ví dụ controller Servlet bằng Spring MVC

Dưới đây là một controller minh họa cách tách thao tác đọc và ghi. **OrderService, Order và CreateOrderRequest** là các thành phần nghiệp vụ do ứng dụng định nghĩa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Order find(@PathVariable long id) {
        // Chỉ đọc; không tự hủy, thanh toán hay đánh dấu hoàn thành.
        return orders.findById(id);
    }

    @PostMapping
    ResponseEntity<Order> create(@RequestBody CreateOrderRequest request) {
        Order created = orders.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable long id) {
        orders.cancel(id);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/drafts/{id}")
    ResponseEntity<Void> deleteDraft(@PathVariable long id) {
        orders.deleteDraft(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Các mapping trên **không tự tạo đầy đủ authentication, authorization và CSRF protection**. Spring Security filter chain thực thi những kiểm tra đó theo cấu hình; service còn phải kiểm tra quyền sở hữu đơn, trạng thái hợp lệ và các quy tắc nghiệp vụ.

**Đặc biệt:** Phương thức GET **không gọi orders.cancel(id)** hoặc cập nhật thông tin nhạy cảm chỉ để đáp ứng ý muốn của frontend.

### 7.2. Ví dụ controller Reactive bằng Spring WebFlux

Trên WebFlux, annotation như GetMapping, PostMapping và DeleteMapping vẫn thể hiện ngữ nghĩa method. Service có thể cung cấp giá trị reactive:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class ReactiveOrderController {
    private final ReactiveOrderService orders;

    ReactiveOrderController(ReactiveOrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<Order> find(@PathVariable long id) {
        return orders.findById(id);
    }

    @PostMapping("/{id}/cancel")
    Mono<ResponseEntity<Void>> cancel(@PathVariable long id) {
        return orders.cancel(id)
                .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

Ở đây **ReactiveOrderService** và **Order** là thành phần nghiệp vụ minh họa; **orders.cancel(id)** được giả định trả một Publisher hoàn thành khi thao tác hoàn tất. Việc dùng Mono không thay đổi quy tắc safe/unsafe hay làm CSRF tự biến mất.

**Servlet và Reactive đều phải tuân thủ ngữ nghĩa HTTP**: GET/HEAD/OPTIONS không chủ ý làm thay đổi trạng thái; POST/PUT/PATCH/DELETE phải được kiểm soát quyền và chống CSRF khi cơ chế xác thực yêu cầu.

## 8. Spring Security Servlet: giữ CSRF theo method

Trong Spring Security với Servlet, CSRF protection mặc định được bật trừ khi cấu hình đã thay đổi. Ví dụ cấu hình bộ lọc bảo mật cho API dùng session cookie và CORS giới hạn frontend hợp lệ:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                // Không tắt csrf(): CSRF protection mặc định vẫn được giữ.
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        config.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "Authorization"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Giải thích:

1. **GET** đến endpoint được bảo vệ vẫn phải xác thực, nhưng matcher CSRF mặc định không yêu cầu CSRF token cho GET.
2. **POST/PUT/PATCH/DELETE** gửi tới các endpoint áp dụng CSRF mặc định cần token hợp lệ, kể cả khi chúng idempotent.
3. CORS cho phép frontend **https://app.example.com** gọi API **/api/** từ browser. Không ghi đường dẫn như **/dashboard** vào allowed origin.
4. Preflight OPTIONS cần được xử lý trước các bước xác thực có thể từ chối yêu cầu thiếu cookie.
5. **CORS chỉ kiểm soát quyền đọc phản hồi cross-origin**, không thay thế CSRF token hoặc quyền truy cập.
6. Các endpoint khác ngoài **/api/** phải có chính sách CORS phù hợp riêng nếu thực sự cần được truy cập cross-origin.

Ví dụ tập trung vào CORS và CSRF. Authentication thực tế có thể dùng form login, OAuth2 login hoặc cơ chế khác, và ứng dụng cần thiết kế **cách cấp CSRF token**. Đoạn code này không tự cung cấp endpoint lấy token cho SPA.

### 8.1. Khi dùng cookie phiên, phải có đường cấp CSRF token hợp lệ

Với một SPA hoạt động khác origin, một lựa chọn là cung cấp **endpoint JSON đã được bảo vệ** để frontend nhận token cho request thay đổi trạng thái. Token phải được tạo bởi cơ chế CSRF phía server và liên kết với session hoặc repository tương ứng.

Luồng minh họa:

~~~text
1. User đăng nhập → browser có session cookie phù hợp
2. SPA gọi endpoint cấp CSRF token do ứng dụng triển khai
3. Browser được phép đọc token response qua CORS phù hợp
4. SPA gửi POST/PUT/PATCH/DELETE kèm session cookie và token
5. Spring Security kiểm tra CSRF token, session và quyền truy cập
6. Nghiệp vụ chỉ được thực hiện sau khi các kiểm tra đạt
~~~

Tùy phiên bản Spring Security và cách lưu token, có thể cần xử lý **deferred token**, cách biểu diễn token và chiến lược đọc token từ request. **Không hard-code token cố định**, không tự sinh một giá trị ngẫu nhiên ở frontend rồi giả định server chấp nhận.

### 8.2. Không dùng ignoreRequestMatchers quá rộng

Một sai lầm là bỏ CSRF cho toàn bộ **/api/** để mọi request POST hết lỗi 403, trong khi chính API đó đang sử dụng **session cookie**.

Nếu có trường hợp cần bỏ CSRF cho một endpoint cụ thể do cơ chế xác thực của endpoint không dùng credential tự động, phải đánh giá đúng ranh giới, tách đường dẫn và kiểm tra phương thức xác thực thực tế. Những ngoại lệ đó không được suy ra chỉ vì endpoint trả JSON.

Không dùng cấu hình “bỏ CSRF cho tất cả POST/PUT/DELETE” trong một ứng dụng dùng session cookie.

## 9. Spring Security Reactive: ServerHttpSecurity và CSRF

Trên **WebFlux**, Spring Security dùng **SecurityWebFilterChain** và **ServerHttpSecurity**. Cơ chế mặc định về CSRF cũng bảo vệ các method unsafe theo cấu hình tương ứng.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                // CSRF mặc định vẫn được giữ.
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        config.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "Authorization"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

**Điểm tương đồng:** Spring Security không nên yêu cầu CSRF token cho GET/HEAD/OPTIONS theo matcher mặc định, nhưng vẫn yêu cầu cho unsafe methods khi CSRF đang hoạt động. Browser áp dụng SOP/CORS, cookie và SameSite như nhau dù backend dùng Servlet hay WebFlux.

**Điểm khác biệt:** WebFlux có WebSession, reactive chain và các lớp **CorsConfigurationSource** riêng. Không trộn gói Servlet **org.springframework.web.cors.UrlBasedCorsConfigurationSource** với gói WebFlux **org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource**.

Cũng như Servlet, ứng dụng WebFlux dùng session phải có cơ chế cấp/đọc token tương thích với CSRF repository và frontend. Xử lý CSRF có thể liên quan publisher bất đồng bộ; cần kiểm thử trên stack thực tế.

## 10. Frontend: gửi method đúng và kèm credential/CSRF phù hợp

Giả sử SPA tại **https://app.example.com** gọi API tại **https://api.example.com**. Hai origin khác nhau nhưng thường same-site nếu cùng scheme và miền có thể đăng ký.

### 10.1. GET: truy xuất thông tin

~~~javascript
const response = await fetch("https://api.example.com/api/orders/42", {
  credentials: "include"
});
if (!response.ok) throw new Error("GET thất bại: " + response.status);
const order = await response.json();
~~~

GET không cần CSRF token theo matcher mặc định, nhưng vẫn có thể cần cookie/session để xác thực. **credentials: "include"** yêu cầu browser xử lý credential cho request cross-origin; cookie chỉ được gửi khi Domain/Path/Secure/SameSite và các điều kiện khác phù hợp.

Để JavaScript đọc phản hồi có credentials từ origin khác, server cần trả header CORS đúng, chẳng hạn:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không sử dụng wildcard **Access-Control-Allow-Origin: *** cho phản hồi CORS có credentials.

### 10.2. POST: thao tác tạo hoặc thay đổi trạng thái

~~~javascript
// csrfToken phải được lấy từ cơ chế cấp token hợp lệ của ứng dụng.
const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});
if (!response.ok) throw new Error("POST thất bại: " + response.status);
~~~

Request JSON có custom header thường cần **OPTIONS preflight**. Browser kiểm tra CORS trước, rồi mới gửi POST thực nếu được phép. Sau đó Spring Security kiểm tra **CSRF token, xác thực và phân quyền**.

Mã JavaScript không được phép tự ý đặt header **Cookie** để vượt cookie policy. Browser quản lý Cookie header; **HttpOnly** ngăn JavaScript đọc cookie nhưng không chặn browser gửi cookie hợp lệ.

### 10.3. API dùng Authorization: Bearer có gì khác?

Nếu mã ứng dụng nhận access token và chủ động thêm:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

thì token không tự xuất hiện chỉ vì browser đã lưu nó trong localStorage hoặc bộ nhớ. Mô hình CSRF có thể khác hệ thống sử dụng cookie/session. Tuy vậy:

- Header Authorization thường khiến request cross-origin cần preflight.
- XSS hoặc lộ access token là rủi ro riêng.
- Nếu ứng dụng vẫn sử dụng cookie tự gửi để refresh token, logout hoặc chức năng khác, các endpoint đó vẫn phải được xem xét CSRF.
- Authentication và authorization không bao giờ biến mất chỉ vì dùng Bearer.

**Không thay đổi chính sách CSRF chỉ dựa vào tên HTTP method hay từ “REST”; phải xét thực sự credential được đưa vào request bằng cơ chế nào.**

## 11. Cache, retry, redirect và ảnh hưởng tới ngữ nghĩa method

### 11.1. GET có thể được cache nhưng vẫn cần bảo vệ dữ liệu

Các phản hồi GET có thể được browser/proxy cache theo header và trạng thái HTTP. Với dữ liệu riêng tư như hồ sơ hoặc sao kê, server phải cân nhắc **Cache-Control** thích hợp:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"accountBalance":100000}
~~~

**Safe không đồng nghĩa cache được**, và cũng không đồng nghĩa dữ liệu có thể chia sẻ công khai. Bảo vệ dữ liệu trong cache, CORS và phân quyền vẫn là trách nhiệm riêng của hệ thống.

### 11.2. Retry và idempotency

Hệ thống mạng có thể làm mất phản hồi dù server đã xử lý request. Client thường có thể retry một request idempotent theo chính sách riêng, nhưng với POST tạo giao dịch, retry vô điều kiện có thể gây tạo trùng.

Nếu cần retry nghiệp vụ nhạy cảm, thiết kế **idempotency key**, giao dịch và kiểm soát trùng ở server. Song song, vẫn phải bảo vệ **CSRF** nếu request mang credential tự gửi.

### 11.3. Redirect 303, 307 và 308

Redirect có thể ảnh hưởng phương thức của request:

- **303 See Other** hướng client thực hiện yêu cầu tới URL mới bằng **GET** (ngoại trừ trường hợp HEAD), thường dùng trong mẫu **POST → Redirect → GET** sau khi xử lý form.
- **307 Temporary Redirect** và **308 Permanent Redirect** yêu cầu giữ **method và body** theo ngữ nghĩa redirect.
- Với **301/302**, một số hành vi tương thích lịch sử cho phép chuyển POST thành GET; phải kiểm tra redirect thực tế thay vì giả định mọi redirect giữ nguyên method.

Ví dụ mẫu **POST → 303 → GET**:

~~~http
POST /checkout HTTP/1.1
Content-Type: application/x-www-form-urlencoded

cartId=42
~~~

~~~http
HTTP/1.1 303 See Other
Location: /orders/123/confirmation
~~~

~~~http
GET /orders/123/confirmation HTTP/1.1
~~~

POST thực hiện giao dịch; GET sau redirect **chỉ hiển thị kết quả**, không lặp lại giao dịch. Thiết kế này giúp tránh việc refresh trang xác nhận vô tình tái thực hiện POST, nhưng **không tự thay thế cơ chế chống request trùng hoặc CSRF**.

### 11.4. HEAD và điều kiện đọc

Một endpoint có thể hỗ trợ GET/HEAD với các header như **ETag**, **Last-Modified**, **If-None-Match**, nhưng bản thân những điều kiện HTTP đó không thay đổi yêu cầu GET phải safe. Response **304 Not Modified** cho GET có điều kiện không có nghĩa server được phép thay đổi trạng thái nghiệp vụ.

## 12. Kiểm thử hành động làm thay đổi trạng thái

Để kiểm thử đúng, dùng môi trường và dữ liệu do bạn kiểm soát, tránh thao tác thực với dữ liệu nhạy cảm khi minh họa request lặp lại.

### 12.1. Xác minh GET không làm thay đổi dữ liệu

Một kịch bản kiểm thử:

1. Ghi lại trạng thái đơn hàng **42** ở môi trường test.
2. Gọi **GET /api/orders/42** nhiều lần và có thể gọi **HEAD /api/orders/42**.
3. Kiểm tra trạng thái nghiệp vụ (status, số tiền, trạng thái thanh toán, thời gian xác nhận) **không bị thay đổi bởi việc đọc**.
4. Cho chạy crawler/link checker giả lập đối với các URL GET trong môi trường test; xác nhận không có thao tác gây tác dụng phụ nghiệp vụ.

Nếu GET thay đổi trạng thái đơn, sửa endpoint theo ngữ nghĩa HTTP trước khi cân nhắc cách cấu hình CSRF.

### 12.2. Kiểm tra POST thiếu hoặc sai CSRF token

Trong môi trường test dùng session/cookie, gọi endpoint thay đổi trạng thái mà **không có CSRF token hợp lệ**. Với Spring Security có CSRF protection đang bật, request thường bị từ chối **403** trước khi service thực hiện thay đổi.

Ví dụ request minh họa:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Cookie: session=valid-session
Content-Type: application/json

{"productId":42,"quantity":1}
~~~

Kết quả kỳ vọng trong môi trường có cấu hình CSRF chuẩn:

~~~http
HTTP/1.1 403 Forbidden
~~~

Tuy nhiên, **403 có nhiều nguyên nhân**: thiếu CSRF token, token không khớp, không đủ quyền hoặc lớp kiểm tra khác. Cần xem log, security trace và điều kiện thử nghiệm để xác định đúng nguyên nhân.

### 12.3. Ví dụ kiểm thử Servlet với MockMvc

Khi có **spring-security-test** và môi trường test tích hợp Spring Security, có thể so sánh request POST có/không có CSRF token. Ví dụ sau giả định endpoint **POST /api/orders** tồn tại và người dùng mock có quyền thực hiện thao tác:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCsrfMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42,\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfPassesCsrfValidation() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42,\"quantity\":1}"))
            .andExpect(status().isCreated());
    }
}
~~~

Giá trị **201 Created** ở test thứ hai là kỳ vọng khi controller và dữ liệu test được thiết kế đúng như ví dụ; ứng dụng thực tế có thể trả mã khác. Việc sử dụng **.with(csrf())** tạo dữ liệu test cho security filter, **không phải hướng dẫn client production tự tạo token tùy ý**.

Đừng chỉ khẳng định request có token là an toàn. Test cũng cần xác minh token không hợp lệ bị chặn, user không có quyền bị từ chối và dữ liệu nghiệp vụ không đổi sau request thất bại.

### 12.4. Reactive với WebTestClient

Trong WebFlux, có thể dùng **WebTestClient** và bộ hỗ trợ kiểm thử **spring-security-test**, ví dụ một đoạn minh họa về thao tác POST khi đã thiết lập client kiểm thử tích hợp security:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

// webTestClient là client đã được ứng dụng test cấu hình đầy đủ.
webTestClient
    .mutateWith(mockUser("tester"))
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isForbidden(); // Thiếu CSRF token.

webTestClient
    .mutateWith(mockUser("tester"))
    .mutateWith(csrf())
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isNoContent(); // Theo hợp đồng endpoint test.
~~~

Đoạn này minh họa các assertion bên trong bài test, chưa phải một lớp test hoàn chỉnh. Nó giả định endpoint hủy đơn và quyền của user test hợp lệ. Khi CSRF pass, authorization hoặc quy tắc nghiệp vụ vẫn có thể trả mã khác.

### 12.5. Dùng curl để quan sát phương thức và preflight

Trong môi trường test có endpoint phù hợp:

~~~bash
curl -i "https://api.example.com/api/orders/42"
~~~

Kiểm tra preflight:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

**curl không thực thi SOP/CORS hoặc các quy tắc SameSite giống browser.** Khi kiểm tra hành vi cookie và browser, dùng thêm **DevTools → Network, Application/Storage và Console**. Trong PowerShell, sử dụng **curl.exe** nếu cần tránh bí danh curl.

## 13. Chẩn đoán xung đột trong triển khai

Một SPA gọi API bằng POST, trả 403 hoặc bị browser chặn. Hãy tách rõ các nguyên nhân:

| Triệu chứng | Giả thuyết cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| GET thành công, POST trả 403. | POST thiếu CSRF token, token sai hoặc thiếu quyền. | Kiểm tra CSRF repository, session, quyền và log bảo mật. |
| OPTIONS trả 401/403 trước POST. | CORS preflight bị xử lý sau bộ lọc xác thực hoặc policy không cho phép method/header. | Kiểm tra thứ tự CORS và cấu hình allowed methods/headers. |
| OPTIONS đạt nhưng POST bị 403. | CORS đã cho phép preflight, request thực bị CSRF/authorization từ chối. | Kiểm tra POST thực và log Spring Security. |
| Browser báo CORS nhưng server log thấy POST đã thực hiện. | Response thiếu CORS header phù hợp; thao tác có thể đã xảy ra. | Không retry mù quáng; kiểm tra trạng thái nghiệp vụ, CORS và idempotency. |
| GET /cancel làm đơn bị hủy. | Thiết kế GET có tác dụng phụ nghiệp vụ. | Chuyển hành động sang method unsafe và bảo vệ CSRF/quyền. |
| DELETE bị 403 dù có thể gọi nhiều lần giống nhau. | Idempotent bị hiểu nhầm là safe. | Giữ CSRF protection khi cookie/session tự gửi. |
| Cookie không gửi cho POST cross-origin. | credentials mặc định, Domain/Path/Secure/SameSite hoặc chính sách browser. | Kiểm tra request Cookie, credentials và ngữ cảnh site. |
| Browser hiện cảnh báo Mixed Content khi gọi HTTP từ HTTPS. | Kết nối không an toàn hoặc bị chính sách trình duyệt chặn. | Dùng HTTPS và kiểm tra HSTS, proxy, redirect. |
| TRACE được trả lời dù ứng dụng không dùng. | Web server/proxy/container bật TRACE. | Đánh giá và chặn method ở tầng phù hợp. |
| Công cụ kiểm thử có CSRF pass nhưng production vẫn 403. | Khác cách cấp token, session, CORS hoặc token handler giữa test và browser. | Kiểm tra luồng thực bằng DevTools, cookie và CSRF token thực. |

### 13.1. Thứ tự điều tra với request POST từ SPA

1. **Xác định URL và method thực tế**, bao gồm redirect nếu có.
2. **Xem OPTIONS** có xảy ra không; nếu có, nó được phép hay bị chặn?
3. **Xem POST thực** đã tới server chưa; request có Cookie hoặc Authorization như dự kiến không?
4. **Kiểm tra CSRF token** có được ứng dụng cấp và được gửi đúng tên field/header hay không.
5. **Kiểm tra authentication và authorization**, không suy ra mọi 403 đều do CSRF.
6. **Xem chính sách CORS của phản hồi thực**, kể cả phản hồi lỗi; nếu thiếu header, frontend có thể chỉ thấy lỗi CORS và không đọc được lý do thật.
7. **Xem trạng thái nghiệp vụ** để tránh vô tình retry một POST đã thực hiện thành công ở server nhưng mất phản hồi trên browser.

Ở các hệ thống qua reverse proxy hoặc gateway, kiểm tra phương thức, URL, scheme và header được chuyển tiếp. Chỉ tin **Forwarded/X-Forwarded-*** từ proxy đã được cấu hình tin cậy. Các security headers/CSP có thể ảnh hưởng hành vi browser, nhưng không thay thế CSRF hoặc thiết kế method đúng.

## 14. Bài tập tình huống

### Tình huống A — GET xác nhận đơn hàng

Một API có **GET /api/orders/42/confirm**. Khi mở URL, server chuyển đơn từ PENDING sang CONFIRMED. Endpoint có safe không?

**Đáp án:** Không. Server đang thực hiện thay đổi trạng thái nghiệp vụ theo yêu cầu GET. Cần chuyển sang POST/PATCH phù hợp, kiểm tra quyền và CSRF khi dựa trên cookie/session.

### Tình huống B — GET ghi log

**GET /api/products/42** chỉ trả thông tin sản phẩm, đồng thời access log ghi thêm một dòng. Có thể coi GET này là safe không?

**Đáp án:** Có thể. Tác dụng phụ vận hành như log không nhất thiết vi phạm safe khi client không yêu cầu một hành động thay đổi trạng thái nghiệp vụ. Phải phân biệt log phụ trợ với tính phí hoặc thay đổi trạng thái được kỳ vọng từ endpoint.

### Tình huống C — DELETE có idempotent

**DELETE /api/draft-orders/42** xóa một bản nháp. Gửi lần đầu trả 204, gửi lần sau trả 404. Method có idempotent không, và có cần CSRF khi dùng session cookie không?

**Đáp án:** Có thể vẫn idempotent vì hiệu quả trạng thái mong muốn giống nhau sau nhiều lần. DELETE vẫn unsafe, nên cần đánh giá và bảo vệ CSRF nếu request sử dụng cookie/session.

### Tình huống D — Cookie Lax và liên kết chuyển tiền

Người dùng đã đăng nhập ngân hàng, cookie có SameSite=Lax. Website khác dẫn người dùng tới **GET /transfer?amount=100** bằng liên kết cấp cao nhất. Cookie có thể được gửi không?

**Đáp án:** Có thể, vì SameSite=Lax thường cho phép cookie trong điều hướng GET cấp cao nhất cross-site. Endpoint không được làm chuyển tiền qua GET.

### Tình huống E — OPTIONS preflight bị yêu cầu đăng nhập

Frontend gửi POST JSON đến API Spring Security khác origin. Browser gửi OPTIONS trước và nhận 401 vì không có cookie. Có nên bắt buộc OPTIONS phải có session?

**Đáp án:** Không. CORS preflight thông thường không mang session cookie. Hãy xử lý CORS trước các bước có thể chặn preflight; POST thực mới chịu xác thực, phân quyền và CSRF.

### Tình huống F — PUT idempotent

API dùng PUT để đặt trạng thái đơn thành CANCELLED. Lập trình viên cho rằng PUT idempotent nên tắt CSRF cho PUT. Đúng hay sai?

**Đáp án:** Sai. PUT là unsafe vì thay đổi trạng thái. Idempotency chỉ mô tả hiệu quả lặp lại, không xác nhận request được người dùng chủ ý thực hiện.

### Tình huống G — POST có CSRF token nhưng thiếu quyền

Người dùng đã đăng nhập và gửi POST với CSRF token hợp lệ để hủy đơn của người khác. Server có được xử lý không?

**Đáp án:** Không. CSRF token không cấp quyền thao tác với tài nguyên. Server phải kiểm tra authorization và các quy tắc sở hữu/nghiệp vụ.

### Tình huống H — Refresh trang xác nhận

Sau khi POST đặt hàng, server trả trang HTML xác nhận trực tiếp. Người dùng refresh, trình duyệt có thể hỏi gửi lại form. Cần cân nhắc mô hình nào?

**Đáp án:** Có thể dùng **POST → 303 See Other → GET** cho trang xác nhận chỉ đọc; đồng thời dùng cơ chế idempotency/deduplication khi cần để tránh tạo trùng trong trường hợp retry.

### Tình huống I — Trace có safe?

Một đồng nghiệp nói “TRACE là safe, nên có thể bật công khai trên production”. Đúng không?

**Đáp án:** Không. TRACE được HTTP định nghĩa là safe theo ngữ nghĩa, nhưng có thể tạo rủi ro lộ thông tin từ request; thường nên hạn chế hoặc vô hiệu hóa qua các tầng phù hợp.

### Tình huống J — API không dùng cookie session

API chỉ nhận Bearer token do ứng dụng khách chủ động gửi trong Authorization; không có credential tự gửi nào khác. Có thể điều chỉnh CSRF không?

**Đáp án:** Có thể đánh giá một chính sách CSRF khác theo mô hình đe dọa thực tế. Tuy nhiên phải xác minh không còn endpoint dùng cookie/session hoặc cơ chế credential tự động, và vẫn cần bảo vệ XSS, xác thực, phân quyền, token và quyền truy cập API. Không đưa ra quyết định chỉ vì API có tên REST.

### Tình huống K — HEAD cập nhật trạng thái đã đọc

Ứng dụng đánh dấu một tài liệu “đã xem” mỗi khi có HEAD request tới URL tài liệu. Đây có phải thiết kế phù hợp không?

**Đáp án:** Không nếu đó là thay đổi trạng thái có ý nghĩa nghiệp vụ. HEAD phải mang ngữ nghĩa truy vấn metadata an toàn, không dùng làm lệnh xác nhận đã đọc.

### Tình huống L — Bị CORS nhưng giao dịch đã thành công

Frontend gửi POST tạo đơn và nhận lỗi CORS; server log cho thấy đơn hàng đã được tạo. Có nên tự động gửi lại POST ngay không?

**Đáp án:** Không. Cần kiểm tra lại trạng thái giao dịch và nguyên nhân CORS, tránh tạo trùng đơn. Thiết kế idempotency phù hợp cho API tạo giao dịch và bảo đảm response CORS chính xác; xử lý lỗi HTTP/browser đúng theo từng lớp.

## 15. Ghi nhớ

- **Safe** nghĩa là request không **nhằm** thay đổi trạng thái nghiệp vụ. **GET, HEAD, OPTIONS và TRACE** được HTTP đặc tả là safe, nhưng TRACE thường cần hạn chế vì bảo mật.
- **Idempotent khác safe**: GET/HEAD/OPTIONS/TRACE safe và idempotent; PUT/DELETE idempotent nhưng **unsafe**; POST/PATCH có thể được thiết kế idempotent trong từng trường hợp cụ thể.
- **GET không được dùng để chuyển tiền, hủy đơn, đổi mật khẩu, đăng xuất hoặc thực hiện tác vụ trạng thái khác**. Trình duyệt, crawler, link preview, prefetch và điều hướng có thể kích hoạt GET mà không mang ý nghĩa xác nhận giao dịch.
- **SameSite=Lax có thể gửi cookie trong điều hướng GET cấp cao nhất từ website khác**; không dựa vào SameSite để hợp thức hóa GET có tác dụng phụ.
- **SOP/CORS giới hạn quyền JavaScript đọc phản hồi cross-origin**; một số request nguy hiểm vẫn có thể đến server. **CSRF token** và phân quyền bảo vệ hành động có credential tự gửi.
- Trong **Spring Security Servlet và Reactive**, CSRF mặc định bỏ qua những safe methods và yêu cầu token với **POST, PUT, PATCH, DELETE** khi CSRF đang hoạt động. **Không tắt CSRF hàng loạt chỉ để tránh lỗi 403**.
- **CORS preflight OPTIONS** cần được xử lý trước các bước xác thực có thể chặn request không có cookie; POST thực vẫn phải qua CSRF, authentication và authorization.
- Khi kiểm thử, hãy quan sát **method thật, cookie/credentials, OPTIONS, CSRF token, HTTP status, CORS header và trạng thái nghiệp vụ** để xác định đúng nguyên nhân và tránh xử lý trùng.
