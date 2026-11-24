# Passive mixed content — nhận diện và xử lý tài nguyên HTTP trong trang HTTPS

> **Chương:** Mixed content  
> **Mục tiêu:** Hiểu passive mixed content (còn được gọi là optionally blockable mixed content), nhận diện ảnh, âm thanh và video tải qua HTTP trong trang HTTPS; phân tích rủi ro toàn vẹn, quyền riêng tư và theo dõi; phân biệt cơ chế tự nâng cấp của browser với CSP `upgrade-insecure-requests` và HSTS; sửa URL, CMS, CDN và kiểm chứng trên DevTools.

## 1. Passive mixed content là gì?

Một trang HTTPS được tải qua kết nối đã mã hóa, nhưng trang đó có thể tham chiếu tới tài nguyên qua HTTP. Khi tài nguyên không an toàn được tải trong một document an toàn, browser phải xử lý theo quy tắc **mixed content**.

**Passive mixed content** là nhóm tài nguyên không trực tiếp tạo môi trường thực thi script trong document theo cách thông thường, chủ yếu gồm:

- Ảnh qua `img`, `picture`, `srcset` hoặc ảnh nền CSS.
- Âm thanh qua `audio` và `source`.
- Video qua `video`, `source` và một số tài nguyên poster.

Tên gọi cũ trong đặc tả là **optionally blockable mixed content**. Tên này phản ánh lịch sử khi browser có thể cho tải một số loại nội dung thụ động dù chúng đến qua HTTP. Browser hiện đại thường tự nâng cấp các request ảnh, âm thanh và video HTTP sang HTTPS; nếu không thể tải tài nguyên an toàn, browser có thể chặn request.

Ví dụ:

```html
<!-- Document được tải qua HTTPS, ảnh lại dùng HTTP. -->
<img src="http://cdn.example.net/banner.jpg" alt="Banner">
```

Nếu trang được mở tại `https://shop.example.com`, request ảnh HTTP ở ví dụ trên là mixed content. Browser có thể thử tải `https://cdn.example.net/banner.jpg` thay cho URL HTTP. Nếu endpoint HTTPS không tồn tại hoặc không có certificate hợp lệ, ảnh sẽ không hiển thị.

## 2. Vì sao gọi là passive?

Ảnh, âm thanh và video thông thường không được browser thực thi như JavaScript trong document. Vì vậy, rủi ro trực tiếp khác với script hoặc stylesheet không an toàn.

Tuy nhiên, “passive” không có nghĩa là vô hại. Tài nguyên vẫn có thể ảnh hưởng tới những gì người dùng nhìn thấy hoặc nghe thấy, và request vẫn tạo ra một tương tác mạng:

- Ảnh có thể bị thay thế bằng nội dung giả mạo, hướng dẫn sai hoặc hình ảnh gây hiểu nhầm.
- Âm thanh/video có thể bị thay đổi, làm gián đoạn hoặc thay nội dung.
- Server tài nguyên có thể quan sát IP, thời điểm request, user agent và thông tin referrer mà browser cho phép gửi.
- Một bên có khả năng sửa lưu lượng HTTP trên đường truyền có thể thay response trước khi browser hiển thị.
- Sự hiện diện hoặc thời gian tải của tài nguyên có thể tạo tín hiệu phụ trong một số tình huống cross-site leak.

Passive mixed content thường không cho phép attacker chạy JavaScript trong origin của trang chỉ bằng cách thay nội dung ảnh. Nhưng attacker vẫn có thể tác động tới tính toàn vẹn của giao diện và quyền riêng tư của người dùng.

## 3. Ví dụ về passive mixed content

### Ảnh trong HTML

```html
<img src="http://images.example.net/products/item-42.png" alt="Sản phẩm">
```

### Ảnh responsive qua srcset

```html
<img
  src="https://images.example.net/photo-640.jpg"
  srcset="
    http://images.example.net/photo-640.jpg 640w,
    http://images.example.net/photo-1280.jpg 1280w
  "
  sizes="100vw"
  alt="Ảnh minh họa"
>
```

Chỉ sửa thuộc tính `src` là chưa đủ nếu `srcset` vẫn chứa URL HTTP. Browser có thể chọn candidate từ srcset theo viewport và mật độ pixel.

### Ảnh nền CSS

```css
.hero {
  background-image: url("http://cdn.example.net/hero.jpg");
}
```

Tài nguyên có thể được tham chiếu gián tiếp từ stylesheet. Khi rà soát mixed content, cần tìm cả URL trong CSS, CSS module, inline style và nội dung được tạo từ CMS.

### Âm thanh và video

```html
<audio controls src="http://media.example.net/intro.mp3"></audio>

<video controls poster="http://media.example.net/poster.jpg">
  <source src="http://media.example.net/demo.mp4" type="video/mp4">
</video>
```

Trong ví dụ này, cả audio source, video source và poster đều cần được kiểm tra. Không giả định browser sẽ nâng cấp mọi URL thành công.

## 4. Browser xử lý passive mixed content như thế nào?

Browser hiện đại thường **tự nâng cấp** các request ảnh, âm thanh và video được tham chiếu bằng HTTP trong trang HTTPS sang HTTPS trước khi tải. Đây là hành vi của mixed content handling, độc lập với việc ứng dụng có khai báo CSP `upgrade-insecure-requests` hay không.

Quy trình khái quát:

1. Document được tải qua HTTPS.
2. Browser phát hiện một tài nguyên thuộc nhóm có thể tự nâng cấp được tham chiếu bằng HTTP.
3. Browser thử request cùng host/path bằng HTTPS.
4. Nếu tài nguyên HTTPS tải được và đáp ứng các kiểm tra khác, browser sử dụng response.
5. Nếu HTTPS không khả dụng hoặc bị lỗi, browser có thể chặn tài nguyên và ghi lỗi trong DevTools.

Ví dụ:

```text
URL trong markup:
http://cdn.example.net/images/logo.png

URL browser thử nâng cấp:
https://cdn.example.net/images/logo.png
```

### Trường hợp địa chỉ IP

Một số browser không tự nâng cấp URL HTTP có host là địa chỉ IP literal theo cùng cách với hostname; mixed content dạng này có thể bị chặn. Không dựa vào cơ chế auto-upgrade để sửa URL IP. Hãy phục vụ tài nguyên qua hostname HTTPS có certificate hợp lệ.

### Hành vi có thể khác theo browser

Quy tắc và thông báo DevTools có thể khác giữa browser engine và phiên bản. Khi xử lý ứng dụng thực tế, hãy xác minh request cuối trong Network và thử trên browser nằm trong ma trận hỗ trợ của sản phẩm.

## 5. Passive mixed content khác active mixed content

Browser phân biệt các loại tài nguyên vì mức độ ảnh hưởng khác nhau:

| Nhóm | Ví dụ | Cách xử lý thường gặp |
| --- | --- | --- |
| Passive/optionally blockable | Ảnh, audio, video | Browser hiện đại thường thử nâng cấp HTTP sang HTTPS; nếu không tải an toàn được thì chặn |
| Active/blockable | Script, stylesheet, iframe, fetch/XHR, font, worker, object và một số kết nối khác | Thường bị chặn khi tải qua HTTP từ document HTTPS |

Active mixed content có thể thực thi code, thay đổi DOM hoặc can thiệp hành vi trang. Vì vậy, browser chặn nhóm này nghiêm ngặt hơn.

Ví dụ active mixed content:

```html
<!-- Script qua HTTP: browser thường chặn. -->
<script src="http://cdn.example.net/app.js"></script>

<!-- Stylesheet qua HTTP: browser thường chặn. -->
<link rel="stylesheet" href="http://cdn.example.net/site.css">

<!-- Iframe qua HTTP: browser thường chặn. -->
<iframe src="http://legacy.example.net/"></iframe>
```

Không áp dụng cách phân loại chỉ dựa vào phần mở rộng file. Cùng một định dạng có thể có ngữ nghĩa khác tùy cách nhúng. Ví dụ SVG dùng như ảnh trong `img` khác với một tài liệu SVG được nhúng qua `object` hoặc mở như document.

## 6. Rủi ro toàn vẹn nội dung

Khi tài nguyên tải qua HTTP, kết nối không cung cấp bảo vệ TLS cho request đó. Một bên có thể sửa nội dung trên đường truyền nếu có vị trí phù hợp trong mạng hoặc kiểm soát được hạ tầng trung gian.

Ví dụ:

- Banner khuyến mãi bị thay bằng thông báo giả.
- Ảnh sản phẩm bị thay bằng ảnh khác để gây nhầm lẫn.
- Poster video bị thay bằng hình ảnh lừa đảo.
- Nội dung audio/video bị thay đổi hoặc gây hại cho trải nghiệm.

Browser auto-upgrade giúp giảm rủi ro bằng cách thử HTTPS, nhưng chỉ có hiệu quả nếu server đích thực sự hỗ trợ HTTPS và response được bảo vệ đúng. Nếu HTTPS endpoint không tồn tại, ứng dụng có thể mất tài nguyên thay vì tự động rơi về HTTP an toàn.

Không sửa bằng cách cho phép lại HTTP. Hãy triển khai HTTPS cho host chứa tài nguyên, cập nhật URL và xác minh certificate.

## 7. Rủi ro quyền riêng tư và tracking

Request tài nguyên bên ngoài có thể tiết lộ một số metadata cho server nhận:

- Địa chỉ IP công khai hoặc IP của proxy/VPN.
- Thời điểm và tần suất tải.
- User-Agent hoặc client hints tùy browser.
- Header Referer theo Referrer-Policy và ngữ cảnh request.
- Một số cookie hoặc credential nếu cookie policy, SameSite, Secure và request context cho phép.

Không phải mọi request cross-site đều gửi cookie phiên. Browser áp dụng cookie attributes và các biện pháp bảo vệ quyền riêng tư; third-party cookie behavior cũng thay đổi theo browser. Tuy nhiên, việc không gửi cookie không loại bỏ mọi metadata leakage.

Nếu ảnh tracking được nhúng từ server HTTP, bên nhận vẫn có thể quan sát request khi browser gửi. HTTPS bảo vệ nội dung truyền giữa browser và server đích, nhưng không ngăn chính server đích ghi nhận request. Muốn giảm tracking, cần xem xét nguồn tài nguyên, Referrer-Policy, proxy/privacy controls và việc có thực sự cần tải tài nguyên bên thứ ba hay không.

## 8. Vì sao passive content vẫn cần được xử lý như vấn đề bảo mật?

Một ảnh không chạy JavaScript trong document nhưng vẫn có thể ảnh hưởng quyết định của người dùng. Hình ảnh giả mạo trong trang thanh toán, banner hỗ trợ hoặc nút giao diện có thể khiến người dùng làm theo hướng dẫn sai.

Ngoài ra, một HTTP request từ trang HTTPS vẫn tạo ra một kết nối không được bảo vệ TLS. Browser không thể xác minh tính toàn vẹn của response qua kết nối đó.

Do đó, không nên xem passive mixed content là cảnh báo thẩm mỹ. Nó là dấu hiệu cho thấy trang bảo mật đang phụ thuộc vào một tài nguyên qua transport không an toàn.

## 9. Cách sửa đúng: phục vụ mọi tài nguyên qua HTTPS

Biện pháp tốt nhất là loại bỏ URL HTTP khỏi document HTTPS:

```html
<!-- Trước -->
<img src="http://cdn.example.net/banner.jpg" alt="Banner">

<!-- Sau -->
<img src="https://cdn.example.net/banner.jpg" alt="Banner">
```

Hãy rà soát toàn bộ vị trí tạo URL:

- Template server-side.
- Component frontend và dữ liệu cấu hình.
- `src`, `srcset`, `poster`, `source`.
- CSS `url()` và CSS được build.
- CMS, rich text, nội dung bài viết và widget.
- Database lưu URL tài nguyên.
- Email/template được tái sử dụng trong webview.
- CDN, object storage và URL được sinh từ API.

Nếu URL được lưu trong database hoặc CMS, sửa nguồn dữ liệu hoặc lớp chuyển đổi có kiểm soát. Đừng chỉ thay một template trong khi bản ghi cũ vẫn chứa HTTP.

## 10. Dùng URL tương đối hay URL HTTPS tuyệt đối?

Hai cách thường an toàn:

```html
<!-- URL HTTPS tuyệt đối -->
<img src="https://cdn.example.net/logo.png" alt="Logo">

<!-- URL tương đối cùng origin -->
<img src="/assets/logo.png" alt="Logo">
```

URL tương đối cùng origin kế thừa scheme của document. Nếu document được phục vụ qua HTTPS, tài nguyên sẽ được tải qua HTTPS.

Protocol-relative URL:

```html
<img src="//cdn.example.net/logo.png" alt="Logo">
```

được resolve theo scheme hiện tại của document. Trên trang HTTPS nó thường resolve thành HTTPS, nhưng trên trang HTTP vẫn là HTTP. Trong hệ thống chỉ hỗ trợ HTTPS, URL HTTPS tường minh hoặc URL tương đối cùng origin thường dễ audit hơn.

Không dùng URL tương đối cho một CDN khác origin nếu base URL hoặc `<base>` có thể thay đổi ngoài dự kiến. Hãy kiểm tra URL sau khi browser resolve.

## 11. CSP upgrade-insecure-requests

Content Security Policy có directive:

```http
Content-Security-Policy: upgrade-insecure-requests
```

Directive này yêu cầu browser nâng cấp các URL tài nguyên không an toàn trong document sang scheme an toàn trước khi request. Nó hữu ích trong quá trình chuyển đổi ứng dụng cũ còn nhiều URL HTTP trong markup, CSS hoặc dữ liệu.

Ví dụ:

```http
Content-Security-Policy: default-src 'self'; upgrade-insecure-requests
```

Nếu trang có:

```html
<img src="http://cdn.example.net/photo.jpg" alt="Ảnh">
```

browser sẽ thử tải phiên bản HTTPS của URL theo directive. Nếu endpoint HTTPS không hỗ trợ, tài nguyên có thể bị lỗi.

### upgrade-insecure-requests không phải phương án thay thế sửa nguồn

Directive này giúp chuyển đổi nhưng có giới hạn:

- Không tạo HTTPS endpoint nếu server chưa hỗ trợ.
- Không sửa URL được lưu trong database/CMS.
- Không bảo đảm certificate của host đích hợp lệ.
- Có thể làm hỏng tích hợp legacy nếu host chỉ có HTTP.
- Không thay thế việc rà soát và sửa URL trong source/configuration.

Hãy dùng nó như lớp hỗ trợ migration, theo dõi tài nguyên bị lỗi và sửa URL gốc.

## 12. upgrade-insecure-requests khác HSTS như thế nào?

Hai cơ chế có thể cùng làm request HTTP chuyển sang HTTPS, nhưng phạm vi và mục đích khác nhau:

| Cơ chế | Phạm vi | Ai khai báo? |
| --- | --- | --- |
| CSP `upgrade-insecure-requests` | Các URL không an toàn được tham chiếu bởi document áp dụng policy | Chủ sở hữu document |
| HSTS | Host đã ghi nhận HSTS; browser nâng cấp điều hướng/request tới host đó theo policy | Server của host qua HTTPS response |

Ví dụ HSTS:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

HSTS chỉ áp dụng cho host đã gửi policy và các subdomain nếu có `includeSubDomains`. Nó không tự động bảo vệ một CDN bên ngoài không nằm trong phạm vi HSTS.

`upgrade-insecure-requests` có thể nâng cấp URL của host khác được document tham chiếu; HSTS có thể tiếp tục bảo vệ host đích ở các lần truy cập khác. Hai cơ chế bổ sung cho nhau nhưng không thay thế việc đảm bảo mọi host hỗ trợ HTTPS.

## 13. block-all-mixed-content có còn cần không?

Directive cũ:

```http
Content-Security-Policy: block-all-mixed-content
```

từng yêu cầu browser chặn mixed content thay vì cho phép một số loại nội dung thụ động. Trong browser hiện đại, mixed content blockable đã bị chặn và passive/optionally blockable thường được tự nâng cấp sang HTTPS; directive này đã lỗi thời/không còn cần cho chính sách mới.

Không dựa vào `block-all-mixed-content` để thay cho việc sửa URL. Nếu tài nguyên HTTP không có HTTPS tương ứng, browser hiện đại vẫn có thể không tải được sau khi tự nâng cấp.

## 14. Kết hợp CSP và HSTS trong giai đoạn migration

Một response HTML có thể khai báo:

```http
Content-Security-Policy: default-src 'self'; upgrade-insecure-requests; object-src 'none'; base-uri 'self'
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
```

Đây chỉ là ví dụ; CSP thực tế cần các nguồn script, style, ảnh, font, API và frame phù hợp với ứng dụng.

Lộ trình:

1. Đảm bảo document chính được phục vụ qua HTTPS.
2. Kiểm kê tài nguyên HTTP trong HTML, CSS, CMS, API và database.
3. Bật `upgrade-insecure-requests` ở staging hoặc rollout có giám sát.
4. Theo dõi tài nguyên bị lỗi sau nâng cấp, đặc biệt host CDN và media legacy.
5. Chuyển URL gốc sang HTTPS hoặc thay nhà cung cấp không hỗ trợ HTTPS.
6. Bật/duy trì HSTS cho host do ứng dụng quản lý sau khi xác minh HTTPS.
7. Loại bỏ URL HTTP và giữ CSP upgrade như lớp phòng vệ bổ sung nếu phù hợp.

Không bật HSTS `includeSubDomains` hoặc preload chỉ để xử lý mixed content nếu chưa xác minh toàn bộ subdomain.

## 15. Tìm passive mixed content trong source code

Tìm kiếm chuỗi `http://` là bước đầu, nhưng không đủ vì URL có thể được ghép động hoặc nằm trong dữ liệu bên ngoài.

Các điểm cần kiểm tra:

- HTML: `src`, `srcset`, `poster`, `source`.
- CSS: `url(...)`, `@import`, font-face và background image.
- JavaScript: URL sinh động từ config/API.
- CMS/rich text: nội dung bài viết, banner, profile và nội dung marketing.
- Database: URL ảnh/media cũ.
- CDN: rewrite, redirect và response URL cuối.
- Service Worker: cache hoặc response được tạo từ URL cũ.

Ví dụ tìm kiếm trong repository:

```powershell
rg -n -i "http://" src public styles
```

Đây chỉ là tìm chuỗi tĩnh. Sau khi tìm được, xác định URL có thật sự được dùng trên trang HTTPS và tài nguyên thuộc nhóm passive hay active.

### Rà soát URL trong CMS

Với nội dung do CMS quản lý:

1. Xuất danh sách URL tài nguyên đang dùng.
2. Phân loại host, scheme, loại file và chủ sở hữu.
3. Xác minh HTTPS endpoint và certificate.
4. Cập nhật URL theo batch có thể rollback.
5. Kiểm tra nội dung render sau khi cập nhật.
6. Thêm validation để nội dung mới không lưu URL HTTP ngoài chính sách.

Không thay mọi chuỗi `http://` bằng `https://` một cách mù quáng. Có thể tồn tại URL văn bản, liên kết ngoài, dữ liệu code sample hoặc endpoint không có HTTPS. Cần phân loại theo mục đích và kiểm tra host đích.

## 16. Cấu hình CDN và media server

Nếu tài nguyên được phục vụ từ CDN, cần xác minh:

- CDN có HTTPS trên hostname đang dùng không.
- Certificate bao phủ đúng hostname.
- Origin server có hỗ trợ HTTPS hoặc CDN có kết nối origin an toàn.
- Redirect HTTP → HTTPS không tạo vòng lặp.
- URL ký số hoặc tokenized URL vẫn hợp lệ sau khi đổi scheme.
- `srcset`, CSS và metadata CMS đã được cập nhật.
- Cache CDN đã purge hoặc hết TTL sau khi thay URL/response.

Không dùng HTTP cho tài nguyên media chỉ vì origin server chưa hỗ trợ HTTPS. Có thể chuyển tài nguyên sang CDN/host có HTTPS, hoặc nâng cấp origin trước khi phát hành URL mới.

## 17. Những trường hợp dễ bỏ sót

| Vị trí | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| `srcset` | Candidate ảnh độ phân giải cao dùng HTTP | Kiểm tra tất cả candidate, không chỉ `src` |
| CSS background | `url(http://...)` | Rà soát source CSS và file build |
| Poster video | `poster="http://..."` | Kiểm tra cả poster lẫn media source |
| CMS content | Ảnh bài viết lưu URL HTTP | Kiểm tra database và nội dung render |
| API response | Backend trả URL ảnh HTTP | Sửa URL generator hoặc dữ liệu gốc |
| Redirect | URL HTTPS chuyển hướng xuống HTTP | Kiểm tra chuỗi redirect trong Network |
| SVG | SVG nhúng như image so với document/object | Xác định context nhúng và khả năng thực thi |
| WebView/in-app browser | Browser engine hoặc policy khác desktop | Kiểm thử trên client thực tế |
| Service Worker | Cache response hoặc URL cũ | Kiểm tra cache storage và version worker |

Redirect từ HTTPS xuống HTTP vẫn có thể tạo mixed content hoặc bị browser chặn. Hãy sửa redirect tại server thay vì dựa vào browser auto-upgrade.

## 18. Kiểm thử passive mixed content bằng DevTools

Thực hiện trên ứng dụng lab/staging do bạn kiểm soát, với tài nguyên thử nghiệm không nhạy cảm.

### Bước 1 — Tạo trang HTTPS có một ảnh HTTP

```html
<!doctype html>
<html lang="vi">
  <meta charset="utf-8">
  <title>Passive mixed content lab</title>
  <img
    src="http://cdn.example.test/lab-image.png"
    alt="Ảnh kiểm thử"
  >
</html>
```

Phục vụ document qua HTTPS và ảnh thử nghiệm qua HTTP trên hostname lab.

### Bước 2 — Quan sát Console và Network

1. Mở DevTools → Console.
2. Tải lại trang.
3. Tìm cảnh báo mixed content hoặc thông báo auto-upgrade.
4. Mở Network và xem URL request thực tế.
5. Xác minh browser thử HTTPS hay chặn tài nguyên.

Thông báo cụ thể phụ thuộc browser và phiên bản.

### Bước 3 — Sửa URL gốc

Đổi ảnh sang URL HTTPS đã được xác minh. Tải lại và kiểm tra request không còn mixed content.

### Bước 4 — Thử upgrade-insecure-requests

Thêm CSP `upgrade-insecure-requests` trong lab. Giữ URL HTTP trong markup và quan sát browser nâng cấp request. Sau đó thử một host chỉ hỗ trợ HTTP để thấy tài nguyên có thể bị lỗi.

### Bước 5 — Kiểm tra các loại media

Thử ảnh `srcset`, CSS background, audio, video source và poster. Ghi lại URL gốc, URL cuối, status và thông báo Console.

### Bước 6 — Kiểm tra redirect và CDN

Quan sát redirect chain của tài nguyên. Xác minh không có bước nào quay về HTTP và CDN trả certificate/response hợp lệ.

## 19. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ảnh không hiển thị trên trang HTTPS | Browser nâng cấp HTTP sang HTTPS nhưng host không phục vụ HTTPS | Bật HTTPS trên host hoặc chuyển URL sang CDN HTTPS |
| Ảnh chính đúng nhưng ảnh responsive lỗi | Một candidate trong `srcset` vẫn dùng HTTP | Cập nhật toàn bộ candidate |
| Background image bị cảnh báo | URL HTTP nằm trong CSS hoặc CSS được tải động | Rà soát CSS source và build output |
| Audio/video không phát | URL bị nâng cấp nhưng HTTPS endpoint không tồn tại hoặc certificate lỗi | Kiểm tra Network, TLS và media URL |
| CSP upgrade không sửa được tài nguyên | Host không hỗ trợ HTTPS hoặc redirect sai | Sửa server/URL; không quay lại HTTP |
| Tài nguyên chỉ lỗi trên một số browser | Khác biệt mixed content handling hoặc hỗ trợ | Kiểm thử browser mục tiêu, dùng URL HTTPS rõ ràng |
| Đã sửa template nhưng vẫn thấy mixed content | URL còn trong CMS, API, database hoặc cache | Theo dõi initiator, sửa nguồn dữ liệu và purge cache |
| URL HTTPS vẫn bị chặn | CSP source policy, certificate, CORP/CORS hoặc lỗi mạng khác | Đọc lỗi cụ thể trong Console/Network |
| Chỉ lỗi qua CDN | Edge cache hoặc redirect còn URL cũ | Kiểm tra response cuối và invalidation |

## 20. Checklist phòng vệ passive mixed content

- Dùng HTTPS cho document và mọi ảnh, audio, video, poster, srcset và CSS image.
- Không dựa vào browser auto-upgrade như cách sửa lâu dài.
- Kiểm tra cả URL tĩnh và URL được tạo từ API/CMS/database.
- Xác minh CDN/media host có HTTPS và certificate hợp lệ.
- Kiểm tra redirect chain không chuyển tài nguyên trở lại HTTP.
- Dùng `upgrade-insecure-requests` như lớp hỗ trợ migration khi phù hợp.
- Không dựa vào `block-all-mixed-content` cho browser hiện đại; directive này đã lỗi thời.
- Phân biệt passive mixed content với active mixed content và mixed downloads.
- Đặt Referrer-Policy phù hợp để giảm thông tin URL bị gửi ra ngoài.
- Đánh giá tài nguyên tracking và bên thứ ba; chỉ tải nguồn thực sự cần thiết.
- Kiểm tra `srcset`, CSS, poster, media source, SVG và nội dung CMS.
- Kiểm thử Console/Network trên browser và WebView mục tiêu.
- Duy trì HTTPS cho toàn bộ host và subdomain do ứng dụng quản lý; bật HSTS theo lộ trình riêng.

## 21. Câu hỏi tự kiểm tra

1. Passive mixed content là gì và vì sao còn có tên optionally blockable?
2. Vì sao ảnh không chạy JavaScript trực tiếp nhưng vẫn tạo rủi ro bảo mật?
3. Browser hiện đại thường xử lý ảnh/audio/video HTTP trong trang HTTPS như thế nào?
4. Vì sao một URL HTTP trỏ tới IP literal có thể không được auto-upgrade giống hostname?
5. Passive mixed content khác active mixed content ở mức độ rủi ro nào?
6. Vì sao cần rà soát cả `srcset`, CSS background và poster?
7. `upgrade-insecure-requests` khác HSTS về phạm vi ra sao?
8. Vì sao `block-all-mixed-content` không còn là giải pháp chính?
9. CORP/CORS có vai trò gì khi tài nguyên HTTPS đã được tải?
10. Cần kiểm tra những gì trong DevTools khi ảnh/media không hiển thị?

**Ghi nhớ:** Passive mixed content là ảnh, audio hoặc video được trang HTTPS tham chiếu qua HTTP. Browser hiện đại thường thử nâng cấp các request này sang HTTPS và chặn nếu không tải an toàn được, nhưng auto-upgrade không thay thế việc sửa URL gốc. Hãy rà soát HTML, srcset, CSS, CMS, API và CDN; phục vụ mọi tài nguyên qua HTTPS; dùng `upgrade-insecure-requests` như lớp hỗ trợ migration và kiểm tra request cuối trong DevTools.
