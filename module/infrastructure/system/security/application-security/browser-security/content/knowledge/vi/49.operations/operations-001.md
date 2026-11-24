# Security header rollout

Triển khai security headers là một thay đổi vận hành đối với mọi phản hồi HTTP mà trình duyệt nhận từ ứng dụng. Mục tiêu là để trình duyệt áp dụng thêm các giới hạn về nguồn tài nguyên, nội dung được nhúng, quyền truy cập tính năng và cách chia sẻ ngữ cảnh giữa các cửa sổ. Những giới hạn này bổ sung cho Same-Origin Policy, CORS, cookie và các biện pháp bảo vệ ở tầng ứng dụng; chúng không thay thế xác thực, phân quyền, kiểm tra đầu vào hay mã hóa đầu ra.

Một đợt rollout tốt phải trả lời được ba câu hỏi: ứng dụng đang gửi những phản hồi nào, chính sách nào tương thích với các luồng sử dụng thực tế, và làm sao phát hiện cũng như khôi phục khi chính sách gây lỗi. Vì vậy, không nên bật đồng loạt một bộ header giống nhau cho mọi hệ thống mà chưa kiểm kê và thử nghiệm.

## 1. Xác định phạm vi và hành vi hiện tại

Trước khi thay đổi cấu hình, lập danh sách các hostname và đường đi của phản hồi:

- Trang HTML chính, trang đăng nhập, trang quản trị và các trang có dữ liệu nhạy cảm.
- API trả JSON, endpoint tải tệp, callback đăng nhập hoặc OAuth, webhook và các endpoint phục vụ nội dung nhúng.
- Tài nguyên tĩnh được phục vụ từ CDN hoặc domain riêng.
- Phản hồi chuyển hướng, lỗi 404/403/500 và trang lỗi do reverse proxy hoặc CDN tạo ra.
- Các hostname phụ, tên miền cũ và subdomain còn hoạt động.

Ghi lại header hiện có ở từng nhóm endpoint. Một số header chỉ có ý nghĩa với tài liệu HTML; một số khác nên có mặt trên nhiều loại phản hồi. Nếu chỉ kiểm tra trang chủ, nhóm triển khai có thể bỏ sót trang đăng nhập, API, trang lỗi hoặc nội dung được phục vụ trực tiếp từ CDN.

Cần xác định nơi nào đang thêm header: ứng dụng, web server, reverse proxy, API gateway hay CDN. Chọn một nơi quản lý chính sách cho từng header và kiểm tra phản hồi cuối cùng tại phía trình duyệt. Khi nhiều lớp cùng thêm một header, kết quả có thể là giá trị trùng lặp hoặc các chính sách cùng áp dụng ngoài dự kiến. Với Content-Security-Policy, nhiều policy được thực thi đồng thời; policy bổ sung có thể làm giới hạn chặt hơn và khiến tài nguyên hợp lệ bị chặn.

## 2. Chọn header theo mục tiêu bảo vệ

Bảng dưới đây là điểm khởi đầu để lập chính sách. Giá trị cụ thể phải dựa trên kiến trúc, tính năng và mức hỗ trợ trình duyệt mà sản phẩm cam kết.

| Header | Mục tiêu | Điểm cần kiểm tra khi rollout |
|---|---|---|
| `Content-Security-Policy` (CSP) | Giới hạn nguồn script, style, ảnh, kết nối, frame và các loại tài nguyên khác; giảm tác động của XSS và nội dung không mong muốn | Kiểm kê script inline, thư viện bên thứ ba, CDN, iframe, API và luồng đăng nhập trước khi enforce |
| `Strict-Transport-Security` (HSTS) | Yêu cầu trình duyệt dùng HTTPS cho các lần truy cập tiếp theo tới hostname | Chỉ gửi qua HTTPS; xác minh toàn bộ subdomain trước khi thêm `includeSubDomains` |
| `X-Content-Type-Options: nosniff` | Ngăn trình duyệt tự suy đoán MIME type trong các trường hợp được header điều chỉnh | Đảm bảo server trả `Content-Type` chính xác cho script, stylesheet và tệp tải xuống |
| `Referrer-Policy` | Giới hạn thông tin URL được gửi trong header `Referer` khi điều hướng hoặc tải tài nguyên | Kiểm tra luồng phân tích truy cập, thanh toán và tích hợp ngoài cần biết nguồn giới thiệu |
| `Permissions-Policy` | Giới hạn việc sử dụng các tính năng trình duyệt như camera, microphone, geolocation | Chỉ cho phép tính năng và origin thực sự cần; kiểm tra iframe được cấp quyền có chủ đích |
| `frame-ancestors` trong CSP | Quy định website nào được phép nhúng tài liệu vào frame | Xác định sản phẩm có cần nhúng trong cổng nội bộ, dashboard hoặc đối tác hay không |
| `Cross-Origin-Opener-Policy` (COOP) | Cách ly browsing context khỏi cửa sổ khác origin | Kiểm tra popup, OAuth, thanh toán và luồng trao đổi dữ liệu giữa các cửa sổ |
| `Cross-Origin-Embedder-Policy` (COEP) và `Cross-Origin-Resource-Policy` (CORP) | Kiểm soát việc nhúng và tải tài nguyên cross-origin; có thể tham gia thiết lập cross-origin isolation | Kiểm tra mọi tài nguyên bên thứ ba, CDN, font, ảnh, worker và yêu cầu dùng SharedArrayBuffer |

### CSP: bắt đầu từ tài nguyên mà ứng dụng thực sự sử dụng

CSP là chính sách có ảnh hưởng rộng vì nó quyết định trình duyệt được tải hoặc thực thi loại tài nguyên nào. Một policy khởi đầu cho trang không cần nhúng nội dung từ bên ngoài có thể trông như sau:

```http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'
```

Đây là ví dụ để giải thích các directive, không phải cấu hình dùng nguyên trạng cho mọi ứng dụng:

- `default-src 'self'` đặt nguồn mặc định là cùng origin cho những loại tài nguyên chưa có directive riêng.
- `base-uri 'self'` giới hạn URL cơ sở mà thẻ `base` có thể đặt.
- `object-src 'none'` chặn nội dung nhúng kiểu plugin cũ.
- `frame-ancestors 'none'` ngăn trang bị nhúng trong frame. Nếu sản phẩm cần được nhúng, thay bằng `'self'` hoặc danh sách origin được phê duyệt.
- `form-action 'self'` giới hạn nơi biểu mẫu được gửi đến. Nếu có luồng gửi biểu mẫu sang domain thanh toán hoặc identity provider, phải khai báo đúng đích cần thiết.

Bổ sung các directive như `script-src`, `style-src`, `img-src`, `font-src`, `connect-src`, `frame-src`, `worker-src` theo từng nhóm tài nguyên. Không mở rộng bằng wildcard chỉ để làm cho báo cáo biến mất. Hãy xác định tài nguyên nào cần được tải, origin nào sở hữu nó và vì sao ứng dụng cần quyền đó.

Ưu tiên nonce hoặc hash cho script inline thay vì cho phép rộng bằng `'unsafe-inline'`. Nonce phải được tạo bằng bộ sinh số ngẫu nhiên mật mã, khó đoán và thay đổi theo từng phản hồi; cùng nonce đó phải xuất hiện trong CSP và thẻ script được cho phép. Nếu HTML được cache ở CDN, cần bảo đảm nonce trong header và HTML luôn khớp, đồng thời không tái sử dụng nonce giữa các phản hồi độc lập. Với script tĩnh, hash có thể phù hợp hơn. Chỉ thêm `'unsafe-eval'` khi đã xác định rõ thư viện hoặc chức năng cần nó và có kế hoạch loại bỏ.

### Các header cần điều kiện tương thích

`X-Content-Type-Options: nosniff` phát huy tác dụng khi server cũng khai báo MIME type chính xác. Ví dụ, JavaScript phải được trả với MIME type phù hợp; không dùng một kiểu chung cho mọi tệp rồi trông chờ trình duyệt đoán.

`Referrer-Policy: strict-origin-when-cross-origin` là lựa chọn phổ biến để giữ thông tin referrer đầy đủ hơn trong cùng origin nhưng chỉ gửi origin khi đi sang origin khác, đồng thời không gửi referrer khi hạ cấp từ HTTPS xuống HTTP. Với trang có URL chứa mã định danh hoặc thông tin nhạy cảm, có thể cân nhắc `no-referrer` và nên tránh đưa bí mật vào URL ngay từ đầu.

`Permissions-Policy` nên phản ánh nhu cầu thật. Ví dụ, nếu ứng dụng không dùng camera, microphone hoặc geolocation, có thể tắt các tính năng đó:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Nếu một tính năng chỉ được dùng trong iframe của một đối tác, hãy khai báo origin được phép một cách cụ thể và kiểm thử quyền ở cả trang cha lẫn iframe.

Với chống clickjacking, ưu tiên directive `frame-ancestors` trong CSP vì nó cho phép khai báo nhiều origin. Có thể giữ `X-Frame-Options: DENY` hoặc `SAMEORIGIN` để hỗ trợ trình duyệt cũ; `ALLOW-FROM` đã lỗi thời và không nên dùng làm cơ chế kiểm soát chính. Không đặt `frame-ancestors 'none'` nếu sản phẩm có luồng nhúng hợp lệ.

COOP, COEP và CORP là nhóm chính sách có thể thay đổi cách các tài nguyên và cửa sổ cross-origin tương tác. Chỉ triển khai khi sản phẩm có yêu cầu cụ thể, chẳng hạn cần cross-origin isolation cho một API trình duyệt. Chúng có thể làm hỏng popup đăng nhập, nội dung nhúng, font, ảnh hoặc script từ bên thứ ba nếu các tài nguyên đó chưa đáp ứng chính sách.

## 3. Rollout theo từng giai đoạn

Một quy trình có thể kiểm soát thường gồm các giai đoạn sau.

### Giai đoạn 1: Lập baseline

Thu thập phản hồi hiện tại từ production hoặc môi trường staging có cấu hình gần production. Lưu lại header, status code, redirect chain và các luồng quan trọng. Xác định owner cho từng domain, endpoint và tích hợp bên thứ ba. Ghi lại các luồng cần được bảo toàn, chẳng hạn đăng nhập, thanh toán, upload, tải báo cáo, mở popup và nhúng dashboard.

### Giai đoạn 2: Tạo policy và kiểm thử trên staging

Viết policy theo nhu cầu của từng ứng dụng hoặc nhóm route. Dùng dữ liệu kiểm thử đại diện cho người dùng thật, bao gồm tài khoản có quyền khác nhau và các luồng ít được sử dụng. Kiểm tra console của trình duyệt, Network panel và log server để tìm tài nguyên bị chặn hoặc response bị thay đổi.

Không lấy việc trang chủ tải thành công làm tiêu chí duy nhất. Một CSP có thể không làm hỏng trang chủ nhưng chặn script chỉ chạy ở màn hình thanh toán hoặc callback đăng nhập.

### Giai đoạn 3: Bật CSP Report-Only

Gửi policy thử nghiệm bằng `Content-Security-Policy-Report-Only`. Trình duyệt sẽ ghi nhận vi phạm và có thể gửi báo cáo theo cơ chế reporting đã cấu hình, nhưng policy này không chặn tài nguyên như CSP enforce.

Ví dụ minh họa:

```http
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; report-uri /csp-report
```

`report-uri` vẫn được một số trình duyệt hỗ trợ nhưng đã được thay thế trong các hướng triển khai mới hơn; khi cần, cấu hình Reporting API với `Reporting-Endpoints` và `report-to` theo ma trận trình duyệt của sản phẩm. Không giả định mọi trình duyệt gửi cùng một định dạng báo cáo.

Phân loại báo cáo theo directive, route, browser và nguồn tài nguyên. Một vi phạm có thể là:

- Tài nguyên hợp lệ chưa được đưa vào policy.
- Script inline hoặc `eval` còn tồn tại trong ứng dụng.
- Một tiện ích mở rộng của người dùng can thiệp vào trang.
- Tài nguyên hoặc nội dung được nhúng từ domain không còn được quản lý.
- Một yêu cầu độc hại đang thử thực thi script hoặc tải nội dung ngoài dự kiến.

Báo cáo CSP là dữ liệu đầu vào không đáng tin cậy. Endpoint nhận báo cáo cần giới hạn kích thước, tốc độ gửi và thời gian lưu; không hiển thị trực tiếp dữ liệu báo cáo trong dashboard mà chưa escape. URL trong báo cáo có thể chứa thông tin nhạy cảm, vì vậy cần lọc hoặc rút gọn trước khi ghi log và phân quyền truy cập.

### Giai đoạn 4: Enforce theo phạm vi nhỏ

Sau khi xử lý các vi phạm hợp lệ, bật CSP enforce cho một nhóm route hoặc nhóm người dùng có thể quan sát tốt. Theo dõi lỗi JavaScript, tỷ lệ hoàn thành luồng nghiệp vụ, báo cáo vi phạm mới và phản hồi hỗ trợ. Mở rộng dần sang các route còn lại khi chỉ số ổn định.

Nếu policy chặn nhầm tài nguyên, xác định directive gây ra lỗi rồi sửa đúng nguồn hoặc cách tải tài nguyên. Trong thời gian điều tra, có thể đưa policy về Report-Only để khôi phục chức năng và tiếp tục thu thập dữ liệu. Tránh nới lỏng toàn bộ CSP chỉ vì một tài nguyên đơn lẻ.

### Giai đoạn 5: Tăng dần HSTS

HSTS có ảnh hưởng riêng vì trình duyệt lưu chính sách và tự chuyển các lần truy cập HTTP tiếp theo sang HTTPS. Chỉ gửi HSTS trên phản hồi HTTPS. Có thể bắt đầu với `max-age` ngắn để xác nhận cấu hình:

```http
Strict-Transport-Security: max-age=300
```

Sau khi xác nhận mọi luồng hoạt động qua HTTPS, tăng thời hạn theo các đợt, ví dụ 1 ngày, 1 tuần rồi 1 năm. Chỉ thêm `includeSubDomains` sau khi đã kiểm kê và chuyển toàn bộ subdomain cần phục vụ sang HTTPS. Một subdomain cũ chỉ hỗ trợ HTTP có thể trở nên không truy cập được với người dùng đã nhận chính sách HSTS.

`preload` cần được xem là một quyết định vận hành riêng. Chỉ cân nhắc khi domain đáp ứng các điều kiện của danh sách preload và tổ chức sẵn sàng duy trì HTTPS trên toàn bộ phạm vi liên quan. Việc gỡ header không xóa ngay chính sách đã được trình duyệt lưu; thời gian ảnh hưởng phụ thuộc `max-age` mà trình duyệt đã nhận và trạng thái preload.

### Giai đoạn 6: Mở rộng và duy trì

Sau khi policy ổn định, triển khai cho các domain và route còn lại. Lưu policy trong cấu hình có version control, gắn thay đổi với người chịu trách nhiệm và ghi lại lý do cho các ngoại lệ. Khi thêm thư viện, CDN, iframe hoặc tích hợp mới, yêu cầu cập nhật policy và kiểm thử cùng thay đổi đó.

## 4. Ví dụ cấu hình tại reverse proxy

Ví dụ sau minh họa việc thêm một số header cơ bản tại Nginx cho virtual host HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    # Chỉ dùng frame-ancestors 'none' nếu ứng dụng không cần được nhúng.
    add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'" always;

    # Bắt đầu bằng max-age ngắn trong giai đoạn xác minh HTTPS.
    add_header Strict-Transport-Security "max-age=300" always;
}
```

Đây là cấu hình minh họa. CSP phải được điều chỉnh theo tài nguyên thực tế của ứng dụng; nếu dùng nonce động, lớp ứng dụng thường là nơi phù hợp để tạo nonce và gắn nó nhất quán vào header cùng HTML. Chỉ thêm HSTS vào virtual host HTTPS. Không phát HSTS từ virtual host HTTP.

Từ khóa `always` giúp Nginx thêm header trên cả những status code ngoài nhóm mặc định, ví dụ một số phản hồi lỗi. Tuy vậy, cần kiểm tra cấu trúc `location`: trong Nginx, các directive `add_header` ở cấp thấp hơn có thể làm thay đổi quy tắc kế thừa từ cấp trên. Một `location` có header riêng có thể khiến các header ở `server` không còn xuất hiện như dự kiến. Kiểm tra response thực tế sau khi reload cấu hình, đặc biệt với trang lỗi và redirect.

Nếu CDN hoặc API gateway cũng thêm header, xác định lớp nào là nguồn cấu hình chính và loại bỏ giá trị trùng lặp. Không dựa vào file cấu hình để kết luận rollout thành công; trình duyệt chỉ nhìn thấy phản hồi cuối cùng sau khi đi qua toàn bộ chuỗi proxy.

## 5. Kiểm chứng sau triển khai

Dùng yêu cầu GET để quan sát header của phản hồi thực tế:

```bash
curl -sS -D - -o /dev/null https://app.example.test/
```

Kiểm tra cả chuỗi chuyển hướng khi cần:

```bash
curl -sS -D - -o /dev/null -L http://app.example.test/
```

Lặp lại cho các route đại diện: trang chủ, đăng nhập, callback, API, tệp tĩnh, trang lỗi và các hostname phụ. Với mỗi phản hồi, xác minh:

1. Header xuất hiện đúng một lần với giá trị dự kiến.
2. Header có mặt trên các status code cần bảo vệ, kể cả redirect và lỗi do proxy tạo ra.
3. HSTS chỉ được gửi qua HTTPS và thời hạn phù hợp với giai đoạn rollout.
4. CSP không chặn script, stylesheet, API, font, ảnh, worker hoặc iframe hợp lệ.
5. `Content-Type` phù hợp với nội dung, đặc biệt đối với JavaScript và CSS khi bật `nosniff`.
6. Referrer và Permissions Policy không làm hỏng tích hợp ngoài hoặc tính năng người dùng cần.
7. Header cuối cùng từ CDN, reverse proxy và ứng dụng không mâu thuẫn.

Tiếp đó mở ứng dụng trong các trình duyệt thuộc phạm vi hỗ trợ. Dùng DevTools Network để xem response headers và Console để tìm CSP violation hoặc lỗi tải tài nguyên. Chạy lại các kịch bản nghiệp vụ quan trọng: đăng nhập, đăng xuất, OAuth, thanh toán, upload, download, popup, nhúng iframe và gọi API. Kiểm thử tự động có thể xác nhận header trên từng route và status code, còn kiểm thử trình duyệt giúp phát hiện ảnh hưởng đến hành vi thật.

Một số lỗi thường gặp khi rollout:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Trang tải nhưng nút hoặc chức năng không hoạt động | CSP chặn script inline, script bên thứ ba hoặc kết nối API | Đọc directive trong báo cáo, xác định tài nguyên cần thiết rồi sửa policy hoặc cách tải |
| Đăng nhập popup không hoàn tất | COOP thay đổi quan hệ giữa cửa sổ mở popup và cửa sổ được mở | Kiểm tra luồng `window.opener`, callback và yêu cầu cách ly trước khi chọn giá trị COOP |
| Ảnh, font hoặc script từ CDN bị lỗi | CSP, COEP hoặc CORP không cho phép tài nguyên cross-origin | Xác minh origin, header của tài nguyên và cơ chế CORS/CORP phù hợp |
| Chỉ một số trang lỗi thiếu header | Header chỉ được thêm ở một route hoặc thiếu `always` trong cấu hình proxy | Kiểm tra cấu hình location, error handler và response cuối từ edge |
| Người dùng không truy cập được subdomain cũ | HSTS có `includeSubDomains` trong khi subdomain chưa hỗ trợ HTTPS | Khôi phục dịch vụ HTTPS cho subdomain; không thể trông chờ gỡ header để xóa ngay HSTS đã lưu |
| Có nhiều giá trị CSP hoặc header trùng lặp | Nhiều lớp cùng thêm header | Chọn một nguồn quản lý, kiểm tra cách các policy được kết hợp và loại bỏ cấu hình dư thừa |

## 6. Theo dõi, rollback và quản lý thay đổi

Trước rollout, ghi lại cấu hình cũ, phiên bản policy, danh sách route và cách khôi phục. Theo dõi tối thiểu:

- Tỷ lệ lỗi tải tài nguyên và lỗi JavaScript trên các route chính.
- Số lượng CSP violation theo directive, route và nguồn.
- Tỷ lệ hoàn thành các luồng đăng nhập, thanh toán và nghiệp vụ trọng yếu.
- Phản hồi từ hỗ trợ khách hàng và lỗi phát sinh tại CDN hoặc reverse proxy.
- Sự khác biệt header giữa các hostname, vùng triển khai và status code.

Nếu phát sinh sự cố, khoanh vùng theo header và route. Với CSP, có thể tạm chuyển policy đang enforce về Report-Only trong lúc điều tra, sau đó phát hành policy sửa đổi. Với Permissions Policy, chỉ mở lại tính năng cần thiết. Với COOP/COEP/CORP, khôi phục giá trị tương thích nếu một luồng cross-origin bị ảnh hưởng. HSTS cần quy trình riêng vì trình duyệt có thể đã lưu chính sách; giảm `max-age` trong response mới không xóa tức thời thời hạn còn lại ở mọi trình duyệt.

Mỗi thay đổi policy nên đi kèm người phê duyệt, lý do, phạm vi áp dụng, kết quả kiểm thử và kế hoạch quay lui. Khi có dependency mới, cập nhật danh sách nguồn hợp lệ thay vì thêm wildcard hoặc nới lỏng toàn bộ policy. Định kỳ rà soát các ngoại lệ để loại bỏ domain không còn sử dụng.

Không bật `X-XSS-Protection` như một lớp bảo vệ mới: header này đã lỗi thời và hành vi của bộ lọc XSS cũ không còn là cơ chế phòng vệ được khuyến nghị. Cũng không xem CSP là biện pháp thay thế cho output encoding, sanitization, kiểm soát quyền hoặc bảo vệ CSRF. Security headers chỉ tạo thêm giới hạn ở phía trình duyệt; ứng dụng vẫn phải xử lý dữ liệu và yêu cầu một cách an toàn ở phía server.

## 7. Checklist phát hành

- [ ] Đã kiểm kê hostname, route, redirect, response lỗi, CDN và các endpoint phục vụ tài nguyên.
- [ ] Đã xác định nơi quản lý từng header và kiểm tra phản hồi cuối cùng từ edge.
- [ ] CSP đã được xây dựng từ tài nguyên thực tế; các ngoại lệ có owner và lý do.
- [ ] CSP Report-Only đã chạy đủ lâu qua các luồng nghiệp vụ đại diện; báo cáo đã được phân loại.
- [ ] CSP enforce được bật theo từng phạm vi và có chỉ số theo dõi.
- [ ] HSTS chỉ phát qua HTTPS; `includeSubDomains` và `preload` chỉ được bật sau khi đánh giá đầy đủ.
- [ ] `nosniff`, Referrer Policy và Permissions Policy đã được kiểm tra với các loại nội dung và tích hợp.
- [ ] COOP, COEP và CORP chỉ được bật khi có yêu cầu, đã kiểm tra popup và tài nguyên cross-origin.
- [ ] Các route chính, redirect, 4xx/5xx và tài nguyên CDN đã được xác minh bằng HTTP client và trình duyệt.
- [ ] Đã lưu policy, kết quả kiểm thử, người chịu trách nhiệm và cách rollback.

Một đợt security header rollout được xem là hoàn tất khi policy đã được xác minh trên phản hồi thực tế, các luồng nghiệp vụ quan trọng hoạt động, báo cáo vi phạm được theo dõi và đội vận hành biết cách cập nhật hoặc khôi phục chính sách khi ứng dụng thay đổi.
