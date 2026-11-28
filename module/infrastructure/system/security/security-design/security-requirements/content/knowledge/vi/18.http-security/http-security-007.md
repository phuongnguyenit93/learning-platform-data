# Referrer-Policy

## 1. Vấn đề bảo mật cần giải quyết

Khi trình duyệt tải một tài nguyên hoặc điều hướng từ trang hiện tại tới trang khác, request có thể chứa header Referer cho biết nguồn của hành động đó.

Nếu nguồn có đường dẫn hoặc query nhạy cảm, thông tin này có thể đi tới một hệ thống không cần biết nó.

Ví dụ URL trang nguồn:

```text
https://portal.example/reports/customer-482?case=internal-review
```

Trang này có liên kết tới dịch vụ hỗ trợ, ảnh từ một nhà cung cấp hoặc tài nguyên theo dõi. Nếu request gửi cả đường dẫn và query của trang nguồn, bên nhận có thể biết mã khách hàng hoặc ngữ cảnh xử lý nội bộ.

Referrer-Policy là cơ chế để ứng dụng quy định mức thông tin nguồn được gửi trong những request liên quan. Tên response header viết là Referrer-Policy; tên request header lịch sử là Referer, với cách viết thiếu một chữ r. Cơ chế và tên gọi được mô tả trong [tài liệu header Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

Đối với thiết kế yêu cầu bảo mật, câu hỏi không chỉ là “đã có header chưa”, mà là:

> Những đích nào được biết thông tin gì về URL nguồn, trong loại request nào, và quyết định đó có được duy trì qua mọi đường tạo request hay không?

### 1.1. Tài sản và hậu quả

Các dữ liệu có thể trở nên nhạy cảm khi nằm trong URL nguồn:

- Mã hồ sơ, mã khách hàng hoặc số đơn hàng.
- Từ khóa tìm kiếm thể hiện thông tin cá nhân.
- Tên dự án nội bộ trong path.
- Tenant hoặc tổ chức được nhận diện trong hostname.
- Token tạm thời hoặc mã khôi phục nếu hệ thống đưa chúng vào query.
- Thông tin nghiệp vụ không cần chia sẻ với nhà cung cấp tài nguyên.

Hậu quả không nhất thiết là chiếm tài khoản. Chỉ việc metadata nghiệp vụ xuất hiện trong log của bên thứ ba cũng có thể vi phạm yêu cầu tối thiểu hóa dữ liệu.

### 1.2. Không đưa bí mật vào URL rồi chỉ dựa vào header

Referrer-Policy chỉ xử lý một kênh truyền thông tin nguồn. Nó không xóa URL khỏi lịch sử, log của server nhận request gốc, telemetry hoặc code JavaScript trong trang.

Do đó, thiết kế nên giảm dữ liệu nhạy cảm trong URL ngay từ đầu. Nếu một giao thức buộc dùng mã tạm thời trong URL, cần quản lý vòng đời, cách tiêu thụ mã, tài nguyên bên thứ ba và những kênh ghi nhận dữ liệu theo hợp đồng riêng.

## 2. Phân biệt URL nguồn, URL đích và origin

### 2.1. URL đích vẫn được gửi tới server đích

Xét hành động:

```text
Trang nguồn:
https://portal.example/account?view=private

Liên kết đích:
https://support.example/help?ticket=123
```

Ngay cả khi không gửi Referer, server support.example vẫn nhận đường dẫn và query của chính request tới nó.

Nếu ứng dụng chủ động đưa dữ liệu nhạy cảm vào URL đích, chẳng hạn:

```text
https://support.example/help?sourceUrl=<URL-nguồn-đầy-đủ>
```

thì Referrer-Policy không loại bỏ tham số sourceUrl đó.

Yêu cầu phải phân biệt “không gửi metadata referrer” với “không gửi dữ liệu nhạy cảm theo bất kỳ cách nào”.

### 2.2. Origin không phải toàn bộ URL

Với ví dụ:

```text
https://portal.example:8443/reports/42?view=private#details
```

origin tương ứng gồm scheme, host và port. Một dạng referrer chỉ-origin có thể được serialize thành:

```text
https://portal.example:8443/
```

Thông tin path và query không còn trong biểu diễn chỉ-origin.

Tuy nhiên, origin vẫn có thể tiết lộ dữ liệu. Nếu tenant nằm trong hostname như tenant-a.portal.example, chỉ gửi origin cũng đã chia sẻ dấu hiệu về tenant đó.

### 2.3. Same-origin không đồng nghĩa với cùng tổ chức

Những URL sau khác origin với https://portal.example:

| URL | Yếu tố khác |
|---|---|
| https://api.portal.example | Host |
| https://portal.example:8443 | Port khác cổng HTTPS mặc định |
| http://portal.example | Scheme |

Một subdomain do cùng công ty sở hữu vẫn có thể là cross-origin. Ngược lại, nhiều đường dẫn phục vụ bởi các nhóm khác nhau có thể ở cùng origin.

Vì vậy, lựa chọn policy phải dựa vào ranh giới dữ liệu và kiến trúc thật, không chỉ dựa vào tên tổ chức.

### 2.4. “Đầy đủ” trong Referer có giới hạn

URL dùng làm referrer được loại bỏ fragment và thông tin user/password. “Đầy đủ” trong phần so sánh dưới đây có nghĩa là có thể gồm path và query, không phải mọi thành phần của URL ban đầu. Quy tắc này nằm trong [thuật toán chuẩn hóa referrer của W3C](https://w3c.github.io/webappsec-referrer-policy/#strip-url).

Không nên suy ra rằng fragment là nơi lưu bí mật an toàn. Script trong trang vẫn có thể đọc nó và truyền đi bằng một kênh khác.

## 3. So sánh các giá trị policy

Bảng dưới dùng một trang nguồn HTTPS thông thường và ba loại đích. “Đầy đủ” là URL nguồn đã được chuẩn hóa như mô tả ở trên; “Origin” không chứa path/query; “Không” nghĩa không gửi Referer.

| Policy | Cùng origin | Khác origin qua HTTPS | Đích HTTP công khai |
|---|---|---|---|
| no-referrer | Không | Không | Không |
| same-origin | Đầy đủ | Không | Không |
| origin | Origin | Origin | Origin |
| strict-origin | Origin | Origin | Không |
| origin-when-cross-origin | Đầy đủ | Origin | Origin |
| strict-origin-when-cross-origin | Đầy đủ | Origin | Không |
| no-referrer-when-downgrade | Đầy đủ | Đầy đủ | Không |
| unsafe-url | Đầy đủ | Đầy đủ | Đầy đủ |

Ngữ nghĩa các giá trị được định nghĩa trong [Referrer Policy của W3C](https://w3c.github.io/webappsec-referrer-policy/#referrer-policies).

Đây là mức thông tin policy cho phép, không phải cam kết mọi request thực tế luôn có header đó. Điều kiện request, trạng thái trình duyệt hoặc thiết lập bảo vệ riêng tư có thể làm thông tin được gửi ít hơn. Những trường hợp đặc biệt như địa chỉ local đáng tin không được mô hình hóa bằng cột HTTP công khai này.

### 3.1. Không xếp mọi policy theo một thang đơn giản

Hai yêu cầu có thể khác nhau:

- Không chia sẻ path/query cho đích bên ngoài.
- Không gửi bất kỳ thông tin nguồn nào tới đích không được bảo vệ.

Một policy có thể tốt hơn ở tiêu chí thứ nhất nhưng không tốt hơn ở tiêu chí thứ hai. Vì vậy, không nên chỉ gắn nhãn “mạnh” hoặc “yếu” mà không nói rõ thông tin và đích đang xét.

Khi xét một ngoại lệ, hãy ghi lại chính xác nó cho phép lộ thêm thành phần nào và tới đâu.

### 3.2. Không phụ thuộc ngầm vào mặc định

Dù các môi trường trình duyệt có policy mặc định, yêu cầu sản phẩm nên công bố giá trị dự kiến một cách tường minh và kiểm chứng trên tập client được hỗ trợ.

Nếu chỉ ghi “dùng mặc định của browser”, một thay đổi môi trường hoặc một cấu hình khác có thể làm hành vi không khớp cam kết dữ liệu của sản phẩm.

Cũng không nên coi giá trị sai chính tả là cấu hình bảo mật thành công. Kiểm tra header phải bao gồm đúng tên, đúng giá trị và hiệu lực thực tế.

## 4. Chọn policy từ yêu cầu dữ liệu

Các lựa chọn trong phần này là ví dụ thiết kế cho một sản phẩm giả định, không phải policy bắt buộc cho mọi ứng dụng.

### 4.1. Trang công khai thông thường

Một trang nội dung có thể cần:

- Giữ thông tin đường dẫn cho một số phân tích điều hướng nội bộ.
- Không gửi path/query tới bên ngoài.
- Không gửi referrer khi điều hướng từ HTTPS tới HTTP công khai.

Theo ma trận ở trên, nhóm yêu cầu đó có thể phù hợp với:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Nhưng nếu hostname đã chứa tenant nhạy cảm, việc chia sẻ origin vẫn cần được đánh giá. Không nên dùng policy này chỉ vì tên có chữ strict.

### 4.2. Trang tài khoản và hồ sơ nhạy cảm

Nếu trang không có nhu cầu gửi thông tin nguồn cho bất kỳ request nào, một lựa chọn thiết kế là:

```http
Referrer-Policy: no-referrer
```

Điều này còn ảnh hưởng tới request cùng origin theo ma trận, nên các tính năng đang dựa vào Referer cần được đánh giá trước khi triển khai.

Yêu cầu không nên chỉ áp dụng cho URL trang chính. Các trang lỗi, trạng thái hết phiên hoặc màn hình trung gian cũng có thể chứa ngữ cảnh nhạy cảm và tạo request ra ngoài.

### 4.3. Chỉ giữ referrer trong cùng origin

Nếu sản phẩm cần thông tin nguồn nội bộ nhưng không có lý do chia sẻ origin với bên ngoài, có thể đánh giá:

```http
Referrer-Policy: same-origin
```

Điểm cần lưu ý là “nội bộ” ở đây gắn với origin. Path/query vẫn có thể đến các endpoint khác cùng origin, bao gồm những endpoint có log hoặc telemetry do nhóm khác quản lý.

Yêu cầu tối thiểu hóa dữ liệu phải xét cả những nơi đó.

### 4.4. Origin tối thiểu cho mọi request được phép

Một sản phẩm có thể chỉ cần biết site nguồn, không cần path/query kể cả cùng origin. Khi đó strict-origin là một lựa chọn cần xem xét.

Điều quan trọng là mô tả nhu cầu trước rồi đối chiếu bảng ngữ nghĩa. Không chọn policy theo thói quen rồi cố giải thích rằng mọi luồng đều cần hành vi đó.

### 4.5. Ngoại lệ cần có chủ sở hữu

Nếu tích hợp yêu cầu referrer chi tiết hơn, cần ghi rõ:

- Thành phần nào cần thông tin.
- Đích nhận và những trường dữ liệu có thể xuất hiện.
- Lý do không dùng cơ chế xác thực hoặc truyền metadata rõ ràng hơn.
- Phạm vi trang hoặc request được áp dụng.
- Người phê duyệt về dữ liệu và thời hạn xem xét lại.
- Tiêu chí kiểm chứng không ảnh hưởng các trang nhạy cảm.

Không thay policy toàn site sang unsafe-url chỉ để sửa một tích hợp không được phân tích đầy đủ.

## 5. Cách chuyển policy tới trình duyệt

### 5.1. Response header

Một HTML response có thể chứa:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Referrer-Policy: no-referrer
```

Thiết kế có thể chọn edge, web server hoặc middleware làm nơi quản lý header. Cần xác định một nguồn cấu hình có thẩm quyền để tránh nhiều lớp tự gắn những giá trị khác nhau.

Đây là response header. Nó không xóa Referer đã có trong request đi vào server trước đó. Vì vậy, gắn no-referrer ở trang đích không thu hồi được dữ liệu mà trang đích đã nhận.

### 5.2. Meta trong HTML

Một cách biểu diễn trong tài liệu:

```html
<head>
  <meta name="referrer" content="no-referrer">
  <title>Thông tin tài khoản</title>
</head>
```

Đây là meta name=referrer, không phải một http-equiv tùy ý.

Nếu chọn cơ chế meta, cần đặt sớm trước những tài nguyên có thể khởi phát request và kiểm tra thời điểm hiệu lực. Thêm meta sau khi request đã bắt đầu không thu hồi được thông tin đã gửi.

Để giảm cấu hình khó hiểu, một dự án có thể quy định header là nguồn chính; meta chỉ xuất hiện ở những trường hợp được thiết kế rõ.

### 5.3. Thuộc tính theo phần tử

Một liên kết cụ thể có thể chọn:

```html
<a
  href="https://support.example/help"
  referrerpolicy="no-referrer"
>
  Mở trang hỗ trợ
</a>
```

Một tài nguyên hình ảnh cũng có thể có policy theo phần tử:

```html
<img
  src="https://assets.example/banner.png"
  alt="Thông tin hỗ trợ"
  referrerpolicy="no-referrer"
>
```

Các cơ chế HTML này được mô tả trong [HTML Standard về referrer policy attributes](https://html.spec.whatwg.org/multipage/urls-and-fetching.html#referrer-policy-attributes).

Nếu mục tiêu là toàn trang không gửi thông tin nguồn, gắn thuộc tính trên một liên kết riêng không bao phủ các request còn lại.

### 5.4. rel=noreferrer và noopener

Với một liên kết mở tab mới, có thể dùng:

```html
<a
  href="https://support.example/help"
  target="_blank"
  rel="noopener noreferrer"
>
  Mở hỗ trợ trong tab mới
</a>
```

Trong thiết kế, cần phân biệt yêu cầu không gửi referrer với yêu cầu kiểm soát quan hệ opener của cửa sổ. Không nên thay một yêu cầu bằng tên một thuộc tính mà không xác định mục tiêu.

Một wrapper tạo liên kết ngoài có thể thống nhất cả hai theo policy của ứng dụng. Tuy nhiên, wrapper đó vẫn cần kiểm tra URL đích và render nhãn an toàn; Referrer-Policy không giải quyết các trách nhiệm này.

## 6. Override và policy có hiệu lực

### 6.1. Header tài liệu không phải sàn bất biến

Có nhiều điểm cấu hình: response header, meta, thuộc tính HTML, lựa chọn của một request và các xử lý trong chuỗi điều hướng.

Không nên giả định tất cả cơ chế luôn kết hợp theo quy tắc “giá trị nghiêm ngặt nhất thắng”. Chuẩn không cấm mọi chuyển sang policy ít hạn chế hơn. HTML cũng định nghĩa các tín hiệu theo ngữ cảnh xử lý, thay vì một phép so sánh đơn giản. Xem [phần downgrade policy của W3C](https://w3c.github.io/webappsec-referrer-policy/#downgrade) và [quy tắc xử lý trong HTML](https://html.spec.whatwg.org/multipage/urls-and-fetching.html#referrer-policy-attributes).

Hệ quả thiết kế: nếu policy trang là yêu cầu bảo mật, phải kiểm kê những override mà code ứng dụng có thể tạo, không chỉ kiểm tra header ở server.

### 6.2. Ví dụ fetch có policy riêng

```javascript
async function loadStatus() {
    const response = await fetch("/api/status", {
        method: "GET",
        referrerPolicy: "no-referrer"
    });

    if (!response.ok) {
        throw new Error("Unable to load status");
    }

    return response.json();
}
```

referrerPolicy là lựa chọn dành cho request trong Fetch API; nó khác với tự đặt một header tên Referer. Fetch Standard mô tả lựa chọn này trong [RequestInit và Request class](https://fetch.spec.whatwg.org/#request-class).

Ví dụ không xác định chính sách cookie, quyền truy cập API hoặc cache. Nếu chức năng cần những ràng buộc đó, phải đặc tả riêng.

Một dự án có thể quy định rằng wrapper fetch không cho phép caller tùy ý chọn policy ít hạn chế hơn phân loại dữ liệu của trang. Cần thực thi quy tắc đó trong code và kiểm tra các đường gọi bỏ qua wrapper.

### 6.3. Không coi request không gửi cookie là không có referrer

credentials và referrerPolicy là những lựa chọn khác nhau của request trong [Fetch Standard](https://fetch.spec.whatwg.org/#request-class).

Một request không gửi credential vẫn có thể tiết lộ thông tin nguồn nếu policy cho phép. Ngược lại, không gửi Referer không làm request mất khả năng mang credential theo chính sách cookie hoặc xác thực khác.

Khi yêu cầu là “không chia sẻ dữ liệu với bên thứ ba”, cần kiểm kê các kênh truyền dữ liệu thay vì chỉ thay một option.

### 6.4. Tập policy cho phép của ứng dụng

Ứng dụng không nhất thiết phải mở mọi giá trị chuẩn cho mọi component.

Ví dụ một policy nội bộ chỉ cho phép:

```text
Trang công khai: strict-origin-when-cross-origin
Trang nhạy cảm: no-referrer
Ngoại lệ: phải được định danh và quản lý riêng
```

Tập này là lựa chọn của sản phẩm giả định. Lợi ích là giảm số cấu hình phải hiểu và giảm nguy cơ một component tự chọn unsafe-url để “làm tích hợp hoạt động”.

## 7. Redirect, iframe, CSS và ứng dụng nhiều trang

### 7.1. Theo dõi từng chặng redirect

Xét một luồng:

```text
Trang tài khoản
    → liên kết chuyển hướng nội bộ
    → dịch vụ tracking
    → trang hỗ trợ
```

Nếu một chặng đã nhận thông tin nhạy cảm, policy ở chặng sau không thể xóa dữ liệu đó khỏi log chặng trước.

Trong Fetch, response redirect có thể cập nhật policy trước request tiếp theo. Vì vậy, không được chỉ quan sát request cuối và kết luận toàn chuỗi an toàn. Cơ chế cập nhật được mô tả trong [thuật toán redirect của Referrer Policy](https://w3c.github.io/webappsec-referrer-policy/#set-requests-referrer-policy-on-redirect).

Đối với thiết kế yêu cầu, cần ghi lại những chặng được phép và thông tin tối đa mỗi chặng được nhận.

### 7.2. Iframe có ranh giới tài liệu riêng

Có thể đặt referrerpolicy cho iframe để điều khiển request tải frame theo cơ chế của phần tử.

Tuy nhiên, không nên suy ra rằng mọi request do tài liệu bên trong khởi tạo đều bị điều khiển vĩnh viễn bởi một thuộc tính ở trang cha. Nội dung trong frame có môi trường và policy liên quan riêng.

Khi nhúng một trang bên ngoài vào khu vực nhạy cảm, yêu cầu cần xem xét cả thông tin gửi lúc tải frame lẫn dữ liệu được trao đổi qua postMessage, URL hoặc script tích hợp. Chỉ thêm referrerpolicy không chứng minh toàn bộ tích hợp không lấy dữ liệu trang cha.

### 7.3. CSS có thể khởi phát request

Request không chỉ đến từ thẻ a hoặc fetch trong JavaScript. Stylesheet có thể tham chiếu ảnh, font hoặc tài nguyên khác.

Stylesheet bên ngoài có thể áp dụng policy từ response của chính nó; CSS inline sử dụng ngữ cảnh của tài liệu chủ. Đây là điểm cần lưu ý trong [tài liệu về tích hợp CSS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#integration_with_css).

Hệ quả thiết kế là không giới hạn kiểm kê vào các liên kết người dùng bấm. Cần quan sát request phát sinh tự động khi trang tải hoặc giao diện thay đổi.

### 7.4. SPA chuyển sang trang nhạy cảm

Một SPA có thể tải shell công khai rồi chuyển sang màn hình có URL nhạy cảm mà không nhận HTML response mới.

Yêu cầu đặt theo nhóm trang phải tính đến mô hình đó. Không nên giả định một route phía client tự có response header riêng chỉ vì đường dẫn trên thanh địa chỉ đã thay đổi.

Có thể chọn một policy shell đáp ứng được các màn hình nhạy cảm, tách tài liệu hoặc thực hiện một cơ chế đã thiết kế rõ. Cần kiểm tra các request phát sinh ngay sau chuyển route, không chỉ lần tải đầu.

### 7.5. Tài liệu lỗi và callback

Những trang sau có thể được tạo bởi các thành phần khác nhau:

- Trang 404 hoặc lỗi ứng dụng.
- Trang bảo trì từ edge.
- Callback sau đăng nhập.
- Trang phục hồi tài khoản.
- Trang kết quả upload hoặc download.
- HTML từ một dịch vụ con.

Nếu một trang có thể chứa thông tin nhạy cảm hoặc tạo request ra ngoài, nó cần được phân loại trong phạm vi policy. Header chỉ tồn tại ở controller trang chủ không bảo vệ đầy đủ hệ thống.

## 8. Giới hạn và quan hệ với kiểm soát khác

### 8.1. Không phải cơ chế xác thực hoặc chống CSRF hoàn chỉnh

Referer có thể thiếu hoặc bị giảm thông tin vì lý do hợp lệ. Client ngoài trình duyệt cũng không phải bằng chứng đáng tin chỉ vì tự gửi một header nguồn.

Vì vậy:

- Không dùng sự hiện diện của Referer làm bằng chứng người dùng đã xác thực.
- Không cấp quyền đối tượng chỉ vì referrer thuộc domain của ứng dụng.
- Không thiết kế CSRF protection chỉ dựa trên việc mọi request chắc chắn có full referrer.
- Nếu hệ thống dùng kiểm tra nguồn request như một lớp bổ sung, phải đặc tả hành vi với dữ liệu thiếu hoặc bị cắt giảm.

Việc siết Referrer-Policy có thể làm lộ ra phụ thuộc không phù hợp ở backend. Cách giải quyết cần dựa vào thiết kế xác thực và chống CSRF của chức năng, không mặc định nới lỏng policy toàn site.

### 8.2. Không thay CORS hoặc CSP

Referrer-Policy tập trung vào thông tin nguồn được gửi kèm request. CORS liên quan đến quyền chia sẻ response cho code theo mô hình trình duyệt; CSP kiểm soát những hành vi và nguồn nội dung theo các directive của nó.

Không gửi Referer không có nghĩa request bị chặn. Một pixel theo dõi vẫn có thể được tải, và bên nhận vẫn thấy những dữ liệu khác của request theo cơ chế liên quan.

Nếu mục tiêu là không tải tài nguyên từ bên thứ ba, cần kiểm soát nguồn và tích hợp, không chỉ metadata referrer.

### 8.3. HTTPS không che thông tin với bên nhận

HTTPS bảo vệ dữ liệu trên chặng truyền tải, nhưng bên nhận request vẫn có thể thấy header được gửi cho nó.

Không nên kết luận rằng gửi full referrer cho một đối tác qua HTTPS là không có rủi ro riêng tư. Cần biết đối tác có cần dữ liệu đó hay không, lưu ở đâu và có chính sách xử lý nào.

### 8.4. Không ngăn script trong trang gửi URL chủ động

Một script có quyền truy cập dữ liệu trang có thể gửi URL hoặc metadata bằng query, body hoặc telemetry. Header no-referrer không ngăn được mọi kênh đó.

Do đó, trang nhạy cảm cần kiểm soát script và tích hợp bên thứ ba theo threat model. Referrer-Policy là giảm một kênh rò rỉ, không phải một hàng rào chống exfiltration toàn diện.

## 9. Ví dụ Java: ánh xạ policy theo loại trang

Ví dụ Java 17 trở lên sau chỉ minh họa việc chọn giá trị header từ metadata route đáng tin. Nó không phụ thuộc một framework web cụ thể.

```java
import java.util.Objects;

public final class PageReferrerPolicies {
    public enum PageClass {
        PUBLIC,
        SENSITIVE
    }

    public enum Policy {
        NO_REFERRER("no-referrer"),
        STRICT_ORIGIN_WHEN_CROSS_ORIGIN(
                "strict-origin-when-cross-origin"
        );

        private final String headerValue;

        Policy(String headerValue) {
            this.headerValue = headerValue;
        }

        public String headerValue() {
            return headerValue;
        }
    }

    private PageReferrerPolicies() {
    }

    public static Policy forPage(PageClass pageClass) {
        Objects.requireNonNull(pageClass, "pageClass");

        return switch (pageClass) {
            case PUBLIC ->
                    Policy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN;
            case SENSITIVE ->
                    Policy.NO_REFERRER;
        };
    }
}
```

Adapter HTTP có thể áp dụng ý tưởng:

```text
pageClass = phân loại từ cấu hình route do ứng dụng quản lý
policy = PageReferrerPolicies.forPage(pageClass)
response.setHeader("Referrer-Policy", policy.headerValue())
```

Các yêu cầu kèm theo:

- pageClass không lấy từ query hoặc header do client tự khai.
- Giá trị không phải một chuỗi tùy ý được phản chiếu vào response.
- Route chưa phân loại không tự rơi vào một ngoại lệ chia sẻ nhiều thông tin.
- Edge không thêm một giá trị khác sau khi ứng dụng đã gắn header.
- Template, thuộc tính phần tử và fetch không vô tình nới lỏng quyết định.
- Cách sinh trang lỗi và shell SPA cũng nằm trong phạm vi.

Code chỉ quản lý lựa chọn policy. Bằng chứng hiệu lực vẫn cần quan sát response thật và request do trình duyệt tạo.

## 10. Đặc tả yêu cầu có thể kiểm chứng

### 10.1. Phát biểu mơ hồ

> Hệ thống phải có Referrer-Policy để bảo vệ dữ liệu.

Phát biểu này không xác định loại thông tin bị cấm, nơi nhận, phạm vi trang hoặc những override được phép.

### 10.2. Yêu cầu cho trang nhạy cảm

> Mọi tài liệu thuộc nhóm trang tài khoản, hồ sơ nội bộ và phục hồi truy cập phải phát policy no-referrer trước khi tài nguyên được khởi tạo. Code ứng dụng không được đặt policy khác cho những request phát sinh từ các trang đó, trừ ngoại lệ đã được định danh. Kết quả chấp nhận là các request thử theo phạm vi không mang Referer, kể cả khi nguồn có path và query đánh dấu.

Cần điền danh sách route hoặc quy tắc phân loại cụ thể theo kiến trúc sản phẩm.

### 10.3. Yêu cầu cho trang thông thường

> Các trang công khai đã phân loại sử dụng strict-origin-when-cross-origin. Đối với các đích HTTPS ngoài origin trong bộ kiểm thử, path/query của trang nguồn không được xuất hiện trong Referer. Những trang có hostname nhạy cảm phải được đánh giá riêng trước khi áp dụng policy cho phép gửi origin.

Đây là yêu cầu dữ liệu rõ hơn một phát biểu chỉ kiểm tra sự tồn tại của header.

### 10.4. Yêu cầu về cấu hình và ngoại lệ

> Header có một nguồn cấu hình có thẩm quyền. Mọi meta referrer, thuộc tính referrerpolicy, rel=noreferrer và lựa chọn referrerPolicy trong JavaScript phải tuân theo phân loại trang. Ngoại lệ có chủ sở hữu, lý do, phạm vi đích và tiêu chí kiểm chứng; không có override động do dữ liệu không tin cậy điều khiển.

### 10.5. Mẫu truy vết

```text
ID: HTTP-REF-01
Tài sản:
    ngữ cảnh hồ sơ và định danh nằm trong URL nguồn
Rủi ro:
    thông tin đi vào log hoặc telemetry của bên thứ ba
Phạm vi:
    các trang được phân loại SENSITIVE
Quy tắc:
    no-referrer
    không override ngoài danh sách đã kiểm soát
Điểm thực thi:
    response header + template + wrapper request
Bằng chứng:
    response thật và Referer tại endpoint thử được kiểm soát
Chủ sở hữu:
    nhóm ứng dụng, edge và chủ sở hữu tích hợp liên quan
```

Mẫu này chỉ là cách diễn đạt; quy ước ID và danh sách trang cần phù hợp hệ thống thực tế.

## 11. Ma trận rủi ro và tiêu chí chấp nhận

| Rủi ro | Yêu cầu | Bằng chứng |
|---|---|---|
| Path/query hồ sơ tới bên ngoài | Không chia sẻ thành phần đó | Endpoint nhận không thấy marker trong Referer |
| Hostname chứa tenant | Đánh giá cả origin | Chọn policy đáp ứng phân loại hostname |
| Trang nhạy cảm chỉ được bảo vệ một link | Bao phủ mọi đường khởi tạo request | Kiểm tra điều hướng, tài nguyên và fetch |
| Component nới policy | Quản lý override | Không có override ngoài phạm vi được phép |
| Header bị edge thay đổi | Một nguồn cấu hình có thẩm quyền | Response qua đường mạng thật đúng giá trị |
| Redirect làm lộ dữ liệu ở chặng giữa | Kiểm tra từng hop | Log thử không có dữ liệu vượt mức cho phép |
| Trang lỗi thiếu policy | Bao phủ tài liệu lỗi có liên quan | Các response đại diện đáp ứng phân loại |
| Script gửi URL trong body | Kiểm soát telemetry riêng | Payload không chứa dữ liệu ngoài hợp đồng |
| Backend phụ thuộc full referrer để cấp quyền | Tách authorization khỏi metadata nguồn | Thiếu referrer không tạo bypass |
| Dữ liệu kiểm thử thành rò rỉ thật | Dùng marker tổng hợp | Không gửi token hoặc hồ sơ thật tới đích thử |

## 12. Thiết kế kiểm chứng trên trình duyệt

Các tình huống sau là tiêu chí để dùng khi triển khai, không phải kết quả kiểm thử đã chạy cho một ứng dụng cụ thể.

### 12.1. Dùng nguồn có marker tổng hợp

Ví dụ:

```text
https://portal.example/test/referrer-marker?case=ref-check-007
```

Marker không chứa thông tin thật nhưng đủ để xác định path/query có bị gửi hay không.

Tạo các đích thử thuộc phạm vi kiểm soát:

- Cùng origin.
- Khác subdomain.
- Khác origin HTTPS.
- Đích HTTP công khai trong môi trường thử khi cần đánh giá downgrade.
- Chuỗi redirect nhiều chặng.
- Endpoint nhận request từ ảnh, liên kết và fetch.

Nếu trình duyệt chặn request HTTP do một cơ chế khác, phải ghi nhận đúng là request không diễn ra. Không suy ra rằng Referrer-Policy là cơ chế đã loại bỏ header chỉ từ việc không thấy request.

### 12.2. Kiểm tra cả policy và hành vi

Hai lớp bằng chứng:

1. Response HTML hoặc tài nguyên có policy dự kiến sau khi đi qua proxy/CDN.
2. Request tới đích thử có lượng thông tin nguồn không vượt policy của sản phẩm.

Chỉ thấy header trên trang không chứng minh một request cụ thể không bị override.

Ngược lại, không thấy Referer trong một profile có cấu hình bảo vệ riêng tư mạnh không chứng minh server đã phát đúng header. Cần kết hợp cả hai.

### 12.3. Không dùng curl để giả lập toàn bộ browser policy

Một HTTP client có thể giúp kiểm tra response header, nhưng không mặc định xử lý HTML, meta, thuộc tính phần tử và chính sách điều hướng giống trình duyệt.

Nếu tự thêm một Referer vào request rồi nhận response, kết quả đó không cho biết trình duyệt sẽ tính referrer như thế nào.

Để kiểm chứng ngữ nghĩa phía browser, cần trình duyệt trong môi trường kiểm soát cùng endpoint quan sát phù hợp. Ghi lại engine, phiên bản và thiết lập liên quan khi đó là bằng chứng cần lưu.

### 12.4. Ma trận kết quả cho policy trang nhạy cảm

Với policy sản phẩm no-referrer:

| Tình huống | Kết quả chấp nhận |
|---|---|
| Bấm liên kết cùng origin | Không gửi Referer |
| Bấm liên kết ngoài origin | Không gửi Referer |
| Tải ảnh từ đích thử | Không gửi Referer |
| fetch theo hợp đồng của trang | Không gửi Referer |
| Component thêm override ngoài policy | Bị phát hiện hoặc ngăn theo cơ chế dự án |
| Chuyển route trong SPA | Vẫn đáp ứng policy của màn hình nhạy cảm |
| Trang lỗi có marker trong URL | Không tạo request lộ marker qua referrer |
| Redirect qua nhiều chặng | Không có chặng nhận dữ liệu vượt mức được phép |

Với policy khác, cần thay expected result bằng ma trận tương ứng và kiểm tra cả những thành phần URL được phép giữ lại.

### 12.5. Kiểm tra phụ thuộc nghiệp vụ

Siết policy có thể ảnh hưởng analytics, hotlink protection hoặc một tích hợp cũ đang dựa vào nguồn trang.

Tiêu chí cần bao phủ:

- Điều hướng hợp lệ vẫn hoạt động.
- API không dựa vào referrer để cấp quyền trái thiết kế.
- Chống CSRF có hành vi rõ khi metadata bị thiếu.
- Analytics chỉ nhận dữ liệu được cho phép.
- Liên kết ngoài không cần nới policy cho toàn bộ trang.
- Các lỗi tích hợp được xử lý bằng hợp đồng phù hợp, không tự fallback sang unsafe-url.

Đây là kiểm tra tính đúng của cả yêu cầu bảo mật và chức năng, không phải lý do để giữ việc chia sẻ dữ liệu không cần thiết.

## 13. Vận hành và thay đổi cấu hình

### 13.1. Tránh cấu hình khác nhau giữa các lớp

Một ứng dụng có thể đặt no-referrer nhưng CDN thêm giá trị khác. Một template cũ có thể thêm meta trái phân loại. Một thư viện frontend có thể tạo fetch với option riêng.

Cần xác định ai sở hữu:

- Policy theo loại trang.
- Header tại edge và origin.
- Template hoặc shell ứng dụng.
- Component tạo liên kết ngoài.
- Wrapper fetch.
- Danh sách ngoại lệ tích hợp.

Khi thay đổi một lớp, phải kiểm tra những đường tạo request liên quan thay vì chỉ xem diff cấu hình server.

### 13.2. Cache và response cũ

Nếu HTML được cache, việc sửa header ở origin có thể chưa xuất hiện ngay trên đường client thật. Cache ở edge, trình duyệt hoặc service worker đều cần được xem xét theo kiến trúc.

Kế hoạch triển khai phải xác định thời điểm policy mới có hiệu lực và cách kiểm chứng những response được phục vụ từ cache. Không kết luận rollout xong chỉ từ một request bỏ qua cache.

### 13.3. Log tối thiểu

Khi điều tra referrer, tránh thu thập toàn bộ URL thật từ người dùng nếu không cần. Có thể dùng marker tổng hợp, log loại origin hoặc mã tình huống theo chính sách dữ liệu.

Một dự án phòng rò rỉ referrer không nên tạo thêm một kho URL nhạy cảm trong hệ thống quan sát.

### 13.4. Những thay đổi cần đánh giá lại

- Thêm bên thứ ba, pixel hoặc thư viện analytics.
- Đưa tenant hoặc mã hồ sơ vào hostname/path.
- Đổi policy của shell SPA.
- Thêm iframe, stylesheet ngoài hoặc service worker.
- Thêm redirect phục vụ tracking.
- Thay wrapper liên kết hoặc fetch.
- Tạo một nhóm trang mới có dữ liệu nhạy cảm.
- Đổi logic backend đang dùng Referer.

Mỗi thay đổi cần xác định lại thông tin nguồn tối đa và đích được phép nhận.

## 14. Điểm cần ghi nhớ

Referrer-Policy giúp giảm thông tin URL nguồn được gửi trong những request do ngữ cảnh web khởi tạo. Một policy chỉ-origin vẫn có thể chia sẻ hostname nhạy cảm; một policy không gửi referrer cũng không ngăn script hoặc URL đích truyền dữ liệu bằng kênh khác.

Thiết kế tốt bắt đầu từ dữ liệu, ranh giới origin và nhu cầu tích hợp, sau đó chọn policy, giới hạn override và chỉ định nơi thực thi. Không coi header là một sàn bất biến cho mọi request hoặc là cơ chế xác thực.

Bằng chứng chấp nhận cần kết hợp response thực tế với request quan sát được trên trình duyệt, bao phủ tài nguyên tự động, điều hướng, fetch, redirect và những tài liệu đặc biệt. Mục tiêu là thông tin gửi đi không vượt hợp đồng dữ liệu của sản phẩm.
