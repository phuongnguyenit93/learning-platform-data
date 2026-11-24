# Header Referrer

**Referrer-Policy** là HTTP response header cho phép website kiểm soát lượng thông tin về trang nguồn mà browser gửi trong request header **Referer**. Chính sách này giúp hạn chế việc URL của trang hiện tại bị tiết lộ cho website khác, đặc biệt khi URL chứa đường dẫn nội bộ, mã định danh hoặc tham số nhạy cảm.

Tên header chính sách viết là **Referrer-Policy** với hai chữ r trong từ Referrer. Header request truyền URL nguồn lại có tên lịch sử **Referer** với một chữ r sau Ref. Đây là cách viết chuẩn của giao thức, không phải lỗi đánh máy trong ứng dụng.

Trong browser hiện đại, chính sách mặc định phổ biến là **strict-origin-when-cross-origin**: request cùng origin có thể gửi đầy đủ URL nguồn; request cross-origin chỉ gửi origin; khi điều hướng từ HTTPS xuống HTTP thì không gửi referrer. Tuy nhiên, ứng dụng nên đặt chính sách rõ ràng để tránh phụ thuộc vào mặc định, browser cũ hoặc thay đổi cấu hình.

Bài học thuộc chương **Security headers** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới browser, origin, cookie và ứng dụng web; tập trung vào cách kiểm soát referrer, giảm rò rỉ URL và hiểu đúng giới hạn của header này khi phối hợp với CORS, CSRF và các security header khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Referer header và Referrer-Policy header khác nhau thế nào.
2. Phân biệt origin với full URL và xác định phần thông tin nào có thể bị gửi sang website khác.
3. So sánh các giá trị no-referrer, same-origin, origin, strict-origin và strict-origin-when-cross-origin.
4. Giải thích hành vi khi request cùng origin, cross-origin và chuyển từ HTTPS xuống HTTP.
5. Cấu hình Referrer-Policy bằng HTTP response header, meta element, thuộc tính referrerpolicy và Fetch API.
6. Hiểu document.referrer có thể bị rút gọn hoặc rỗng và không phải bằng chứng xác thực.
7. Nhận diện nguy cơ rò rỉ token, email, mã định danh hoặc dữ liệu tìm kiếm qua path/query.
8. Phân biệt Referrer-Policy với CORS, SOP, CSRF token, Origin header và Fetch Metadata.
9. Kiểm tra header thực tế bằng DevTools, curl và một lab Node.js hai origin.

## 2. Referer là gì và có thể làm lộ thông tin nào?

Khi người dùng mở một liên kết hoặc browser tải tài nguyên, browser có thể gửi thông tin về URL của tài liệu đã khởi tạo request trong header Referer.

Ví dụ người dùng đang ở:

~~~text
https://shop.example.com/account/orders?filter=recent&email=alice%40example.com
~~~

Sau đó họ click liên kết sang:

~~~text
https://partner.example.net/offer
~~~

Nếu chính sách cho phép gửi full referrer, website đối tác có thể nhận được path và query của trang nguồn. Điều đó có thể làm lộ:

- Tên route nội bộ như /account, /admin, /reset-password.
- Từ khóa tìm kiếm, bộ lọc hoặc mã hồ sơ trong query string.
- Email, mã đơn hàng, mã mời hoặc identifier có thể liên kết với một người dùng.
- Token đặt trong URL do thiết kế ứng dụng không an toàn.
- Cấu trúc đường dẫn giúp attacker suy đoán chức năng hoặc trạng thái của ứng dụng.

**Fragment (#...) và userinfo không được gửi trong Referer theo quy tắc URL.** Tuy vậy, không nên đưa bí mật vào URL: path và query vẫn có thể xuất hiện trong log server, lịch sử browser, analytics, screenshot hoặc các kênh khác.

### 2.1. Origin và full URL khác nhau

Origin gồm ba thành phần:

~~~text
scheme + host + port
https://shop.example.com:443
~~~

Full URL còn có thể chứa:

~~~text
https://shop.example.com:443/account/orders?filter=recent#summary
|------------------------------|---------------------------|
             origin                  path/query/fragment
~~~

Khi policy chỉ gửi origin, server nhận thông tin về scheme, host và port nhưng không nhận path hoặc query. Fragment không được gửi trong HTTP request.

### 2.2. Same-origin không đồng nghĩa same-site

Referrer Policy dùng khái niệm same-origin/cross-origin để quyết định lượng thông tin. Hai URL khác port là khác origin dù có thể cùng site. Hai subdomain như app.example.com và cdn.example.com cũng khác origin dù có thể cùng site.

Đừng dùng suy luận cookie SameSite để đoán Referrer-Policy. Hai cơ chế có mục tiêu và tiêu chí khác nhau.

## 3. Referrer-Policy kiểm soát điều gì?

Referrer Policy quyết định browser gửi bao nhiêu thông tin referrer trong request. Nó không quyết định request có được gửi hay không và không xác thực người dùng.

Header toàn trang thường được cấu hình như sau:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Chính sách của tài liệu nguồn áp dụng cho các request do tài liệu đó khởi tạo, bao gồm điều hướng và tải tài nguyên. Có thể ghi đè chính sách cho một số request bằng thuộc tính referrerpolicy trên element hoặc tùy chọn referrerPolicy của Fetch API.

### Luồng quyết định referrer

~~~mermaid
flowchart TD
    A["Tài liệu nguồn khởi tạo request"] --> B["Lấy policy của document"]
    B --> C{"Request có policy riêng?"}
    C -->|Có| D["Dùng referrerpolicy của element<br/>hoặc referrerPolicy của Fetch"]
    C -->|Không| E["Dùng policy của document"]
    D --> F["So sánh origin và mức bảo mật scheme"]
    E --> F
    F --> G{"Kết quả policy"}
    G -->|No referrer| H["Không gửi Referer"]
    G -->|Origin only| I["Gửi scheme + host + port"]
    G -->|Full URL| J["Gửi URL nguồn, bỏ fragment và userinfo"]
~~~

### 3.1. Các thành phần có thể xuất hiện trong referrer

| Thành phần URL | Có thể được gửi trong Referer? | Ghi chú |
| --- | :---: | --- |
| Scheme | Có | Ví dụ https: |
| Host | Có | Ví dụ shop.example.com |
| Port | Có | Port mặc định thường được chuẩn hóa và không hiển thị tường minh |
| Path | Tùy policy | Có thể bị lược bỏ khi chỉ gửi origin |
| Query string | Tùy policy | Có thể chứa dữ liệu nhạy cảm; không đặt secret ở đây |
| Fragment | Không | Phần sau # không được gửi trong HTTP Referer |
| Username/password trong URL | Không | Userinfo bị loại khỏi referrer |

### 3.2. Referrer không phải là nguồn xác thực

Server không nên dùng Referer để chứng minh người dùng đến từ một trang đáng tin cậy, để cấp quyền hoặc để xác nhận request là hợp lệ. Header có thể bị browser rút gọn, bỏ qua, thay đổi bởi privacy setting, extension hoặc client không phải browser.

Nếu cần bảo vệ request thay đổi trạng thái, dùng xác thực, phân quyền, CSRF token và các tín hiệu request phù hợp như Origin hoặc Fetch Metadata theo threat model.

## 4. Các giá trị Referrer-Policy

Có tám giá trị chính thường gặp. Bảng dưới giả định request được khởi tạo từ một tài liệu có URL đầy đủ và browser áp dụng đúng policy.

| Policy | Cùng origin | Cross-origin | HTTPS → HTTP |
| --- | --- | --- | --- |
| no-referrer | Không gửi | Không gửi | Không gửi |
| no-referrer-when-downgrade | Full URL | Full URL | Không gửi |
| same-origin | Full URL | Không gửi | Không gửi nếu khác origin |
| origin | Chỉ origin | Chỉ origin | Vẫn gửi origin |
| strict-origin | Chỉ origin | Chỉ origin | Không gửi |
| origin-when-cross-origin | Full URL | Chỉ origin | Vẫn gửi origin |
| strict-origin-when-cross-origin | Full URL | Chỉ origin | Không gửi |
| unsafe-url | Full URL | Full URL | Full URL |

no-referrer-when-downgrade từng là mặc định phổ biến trong browser cũ. Mặc định hiện đại phổ biến là strict-origin-when-cross-origin; hãy khai báo policy tường minh để hành vi có thể dự đoán.

### 4.1. no-referrer

~~~http
Referrer-Policy: no-referrer
~~~

Browser không gửi Referer trong các request chịu policy này.

Phù hợp khi:

- Trang không cần chia sẻ thông tin nguồn truy cập với website khác.
- Nội dung có khả năng chứa URL nhạy cảm và muốn giảm metadata gửi đi.
- Ứng dụng ưu tiên quyền riêng tư hơn attribution/analytics dựa trên referrer.

Đổi lại, website nhận request không thể biết trang nào đã dẫn người dùng tới.

### 4.2. same-origin

~~~http
Referrer-Policy: same-origin
~~~

Browser gửi full URL khi request cùng origin; request cross-origin không có Referer.

Policy này hữu ích khi ứng dụng muốn giữ referrer cho điều hướng nội bộ nhưng không tiết lộ origin hoặc path cho website khác. Hãy nhớ khác port hoặc khác subdomain có thể là cross-origin.

### 4.3. origin

~~~http
Referrer-Policy: origin
~~~

Browser chỉ gửi origin cho mọi request, kể cả request cross-origin và request downgrade. Path và query được lược bỏ.

Vì policy này vẫn gửi origin trong trường hợp HTTPS chuyển xuống HTTP, nó có thể tiết lộ tên host qua kết nối kém an toàn. Nếu cần tránh gửi referrer khi downgrade, cân nhắc strict-origin.

### 4.4. strict-origin

~~~http
Referrer-Policy: strict-origin
~~~

Browser chỉ gửi origin, trừ khi request là downgrade từ HTTPS xuống HTTP; trong trường hợp đó không gửi referrer.

Policy này giảm rò rỉ path/query và không gửi origin qua kết nối kém an toàn.

### 4.5. strict-origin-when-cross-origin

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Hành vi:

- Cùng origin: gửi full URL nguồn.
- Cross-origin: chỉ gửi origin.
- HTTPS xuống HTTP: không gửi referrer.

Đây là lựa chọn cân bằng thường dùng cho website hiện đại: giữ thông tin đầy đủ cho điều hướng nội bộ, giảm chi tiết gửi tới bên ngoài và tránh gửi referrer khi downgrade.

### 4.6. no-referrer-when-downgrade

~~~http
Referrer-Policy: no-referrer-when-downgrade
~~~

Browser gửi full URL cho request không phải downgrade và bỏ referrer khi HTTPS chuyển xuống HTTP. Policy này vẫn có thể làm lộ path/query cho website cross-origin dùng HTTPS, nên không nên chọn chỉ vì tên gọi có vẻ an toàn.

### 4.7. origin-when-cross-origin

~~~http
Referrer-Policy: origin-when-cross-origin
~~~

Browser gửi full URL cùng origin, chỉ gửi origin cho request cross-origin. Khác với strict-origin-when-cross-origin, policy này vẫn gửi origin trong trường hợp downgrade HTTPS → HTTP.

### 4.8. unsafe-url

~~~http
Referrer-Policy: unsafe-url
~~~

Browser gửi full URL nguồn trong cả request cross-origin và downgrade. Điều này có thể tiết lộ path/query cho website bên ngoài và qua kết nối HTTP. Tránh dùng policy này trong ứng dụng thông thường.

## 5. Mặc định strict-origin-when-cross-origin hoạt động thế nào?

Giả sử trang nguồn là:

~~~text
https://app.example.com/account/orders?tab=recent&customer=42
~~~

Với strict-origin-when-cross-origin:

| Request đích | Loại | Referer dự kiến |
| --- | --- | --- |
| https://app.example.com/settings | Cùng origin | Full URL nguồn, gồm path và query |
| https://api.example.com/profile | Cross-origin | https://app.example.com/ |
| https://partner.example.net/offer | Cross-origin | https://app.example.com/ |
| http://legacy.example.net/offer | Downgrade | Không gửi |

Điều này cho thấy policy giảm rò rỉ cho website bên ngoài, nhưng không che path/query khỏi request cùng origin. Nếu URL cùng origin chứa token hoặc dữ liệu cá nhân, các request nội bộ vẫn có thể mang full referrer. **Không đưa bí mật vào URL ngay từ đầu.**

## 6. Cách cấu hình Referrer-Policy

### 6.1. HTTP response header

Đây là cách nên ưu tiên để áp dụng nhất quán:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Referrer-Policy: strict-origin-when-cross-origin
~~~

Nên cấu hình tập trung ở web server, reverse proxy, CDN hoặc middleware framework. Kiểm tra cả response HTML chính, trang lỗi và các route nhạy cảm.

### 6.2. HTML meta element

Có thể khai báo trong phần head:

~~~html
<meta name="referrer" content="strict-origin-when-cross-origin">
~~~

Meta element hữu ích khi không thể sửa response header ngay, nhưng HTTP header giúp chính sách rõ ràng và dễ quản lý tập trung hơn. Meta phải xuất hiện sớm trong tài liệu để có tác dụng với các request được khởi tạo sau đó; không nên dùng nó thay cho cấu hình server khi có thể.

### 6.3. Thuộc tính referrerpolicy trên element

Một liên kết có thể giảm referrer riêng cho request đó:

~~~html
<a
  href="https://partner.example.net/offer"
  referrerpolicy="no-referrer"
  rel="noopener">
  Mở đối tác
</a>
~~~

Ảnh cũng có thể đặt policy riêng:

~~~html
<img
  src="https://images.example.net/banner.png"
  referrerpolicy="no-referrer"
  alt="Banner">
~~~

Thuộc tính element giúp kiểm soát ngoại lệ cụ thể. Không nên rải nhiều policy không nhất quán trên từng link; hãy có baseline toàn trang và chỉ override khi có lý do rõ ràng.

### 6.4. rel="noreferrer"

Với liên kết:

~~~html
<a href="https://partner.example.net/" target="_blank" rel="noreferrer">
  Mở website đối tác
</a>
~~~

rel="noreferrer" yêu cầu không gửi Referer cho điều hướng đó. Trong browser hiện đại, noreferrer cũng ngụ ý noopener, ngăn trang mới truy cập window.opener. Nếu chỉ cần ngăn opener mà vẫn muốn gửi referrer theo policy, dùng rel="noopener" riêng.

### 6.5. Fetch API

Có thể đặt policy cho từng request:

~~~js
fetch('https://api.example.net/public-data', {
  method: 'GET',
  mode: 'cors',
  referrerPolicy: 'no-referrer',
});
~~~

referrerPolicy chỉ kiểm soát referrer metadata. Nó không thay mode, CORS, credentials mode hoặc xác thực API. Nếu request cần đọc response cross-origin, server vẫn phải cấu hình CORS phù hợp.

### 6.6. Thứ tự lựa chọn policy

Hãy nghĩ theo thứ tự:

1. Đặt policy mặc định ở response header cho tài liệu.
2. Chỉ dùng meta khi cần và không kiểm soát được header.
3. Dùng referrerpolicy hoặc rel="noreferrer" cho một liên kết/tài nguyên cần chặt hơn.
4. Dùng referrerPolicy trong Fetch API khi request có yêu cầu riêng.

Thuộc tính hoặc tùy chọn riêng đặt policy cho request tương ứng và có thể thay đổi policy mặc định của document. Vì vậy, hãy review các override này để chúng không vô tình gửi nhiều thông tin hơn baseline đã chọn.

## 7. document.referrer là gì?

JavaScript có thể đọc:

~~~js
console.log(document.referrer);
~~~

Giá trị này là referrer của navigation đã đưa người dùng tới tài liệu hiện tại, nếu browser có gửi. Nó có thể:

- Là full URL.
- Chỉ là origin.
- Là chuỗi rỗng.

Giá trị rỗng có thể xuất hiện khi người dùng mở URL trực tiếp, đi từ bookmark, policy là no-referrer, nguồn không gửi referrer hoặc browser privacy control loại bỏ nó.

### 7.1. Không dùng document.referrer để cấp quyền

Ví dụ không an toàn:

~~~js
if (document.referrer.includes('trusted.example')) {
  showAdminAction();
}
~~~

Attacker có thể điều khiển luồng điều hướng, header có thể bị lược bỏ hoặc giả mạo trong một số client. Quyền admin phải được server kiểm tra dựa trên session và authorization.

### 7.2. document.referrer không phải Referer của mọi request

document.referrer mô tả navigation nguồn của document hiện tại. Nó không phải bản ghi đầy đủ mọi request mà trang đã thực hiện, cũng không phản ánh tất cả referrer của image, script hoặc fetch được tải sau đó.

Muốn kiểm tra request cụ thể, xem Network panel hoặc log server của endpoint nhận request.

## 8. Rủi ro và giới hạn của Referrer-Policy

### 8.1. URL vẫn có thể rò rỉ qua nhiều kênh khác

Referrer-Policy không che URL khỏi:

- Log ở reverse proxy, CDN, web server hoặc analytics của chính ứng dụng.
- Browser history, bookmark hoặc screenshot.
- URL được gửi trực tiếp trong link, query, form hoặc postMessage.
- Request khác do JavaScript chủ động tạo và đưa dữ liệu vào body/header.
- Log của website đích khi người dùng truy cập trực tiếp URL có token.

Do đó, không dùng URL làm nơi chứa session ID, reset token dài hạn, access token, email hoặc thông tin cá nhân nhạy cảm.

### 8.2. Không phải mọi request đều có Referer

Browser có thể không gửi Referer do policy, privacy mode, extension, ứng dụng native hoặc request không có referrer source. Server phải chấp nhận header vắng mặt theo giao thức và không dựa vào nó như điều kiện duy nhất cho một chức năng hợp lệ.

### 8.3. Redirect và nhiều bước điều hướng

Request có thể đi qua một hoặc nhiều redirect. Referrer Policy và cách browser xử lý referrer trong redirect chain có quy tắc riêng; header của response redirect có thể ảnh hưởng policy cho bước tiếp theo theo chuẩn. Khi luồng chuyển hướng quan trọng, hãy kiểm tra toàn bộ chain trong DevTools/Network và log ở từng hop, không suy ra chỉ từ URL cuối.

### 8.4. HTTPS downgrade

Downgrade là request từ tài liệu HTTPS sang đích HTTP. Các policy có chữ strict trong tên sẽ không gửi referrer khi downgrade. Tránh tải nội dung nhạy cảm hoặc chuyển người dùng từ ứng dụng HTTPS sang endpoint HTTP; referrer policy chỉ giảm metadata, không bảo vệ nội dung request khỏi nghe lén.

## 9. Referrer-Policy khác gì CORS, SOP và CSRF?

| Cơ chế | Mục tiêu | Kiểm soát điều gì? |
| --- | --- | --- |
| Referrer-Policy | Giảm rò rỉ URL nguồn | Lượng referrer browser gửi |
| Same-Origin Policy | Cách ly dữ liệu giữa origin | Quyền đọc DOM/response và truy cập tài nguyên cross-origin |
| CORS | Cho phép một số truy cập response cross-origin | Browser có cho JavaScript đọc response hay không |
| CSRF token | Xác minh request thay đổi trạng thái | Request có token hợp lệ gắn với session/ý định ứng dụng hay không |
| Origin header | Cung cấp origin của nguồn request trong một số request | Scheme/host/port của origin khởi tạo |
| Fetch Metadata | Mô tả ngữ cảnh request | Các header như Sec-Fetch-Site, Sec-Fetch-Mode, Sec-Fetch-Dest |

### 9.1. Referrer-Policy không thay CORS

Một request có thể không gửi Referer nhưng vẫn là cross-origin. CORS quyết định JavaScript có được đọc response theo policy server hay không. Referrer-Policy chỉ quyết định referrer metadata có được gửi và ở mức nào.

### 9.2. Referrer-Policy không thay CSRF defense

Không gửi Referer có thể làm server mất một tín hiệu phụ để kiểm tra nguồn request. Điều đó không tự làm CSRF an toàn hơn. Với request thay đổi trạng thái, ưu tiên:

- CSRF token được kiểm tra ở server.
- Cookie SameSite phù hợp với luồng ứng dụng.
- Kiểm tra Origin khi có thể và theo threat model.
- Dùng Fetch Metadata như tín hiệu phòng vệ bổ sung.
- Không dùng GET cho thao tác thay đổi trạng thái.

Không bật no-referrer rồi dùng sự vắng mặt của Referer làm bằng chứng rằng request là an toàn.

## 10. Chọn policy cho ứng dụng

Không có một giá trị duy nhất phù hợp mọi sản phẩm. Chọn theo lượng thông tin mà website muốn chia sẻ và nhu cầu attribution.

| Nhu cầu | Policy gợi ý | Lý do |
| --- | --- | --- |
| Website thông thường, muốn giữ điều hướng nội bộ và giảm lộ path ra ngoài | strict-origin-when-cross-origin | Full URL cùng origin, origin-only cross-origin, không gửi khi downgrade |
| Ứng dụng nội bộ không muốn tiết lộ referrer cho bất kỳ origin ngoài nào | same-origin | Chỉ gửi full URL trong cùng origin |
| Trang nhạy cảm không cần chia sẻ referrer | no-referrer | Không gửi referrer |
| Muốn chia sẻ origin nhưng không path/query | strict-origin | Origin-only và bỏ khi downgrade |
| Tài nguyên cụ thể không nên gửi referrer | no-referrer trên element/request hoặc rel=noreferrer | Giới hạn cho request đó |

### 10.1. Gợi ý cho trang đăng nhập và tài khoản

Với trang đăng nhập, reset password, trang tài khoản hoặc trang quản trị:

- Không đặt token, email hoặc identifier nhạy cảm trong URL.
- Cân nhắc no-referrer hoặc same-origin nếu không cần gửi referrer ra bên ngoài.
- Dùng strict-origin-when-cross-origin nếu cần giữ thông tin nội bộ và chỉ gửi origin khi điều hướng ra ngoài.
- Đặt policy ở response header để áp dụng nhất quán.
- Kiểm tra script analytics, ảnh, link ngoài và redirect vì chúng có thể khởi tạo request mang referrer.

### 10.2. Không chọn unsafe-url chỉ để analytics biết trang nguồn

Nếu cần attribution, ưu tiên cơ chế analytics có kiểm soát, event ID ngẫu nhiên không nhạy cảm hoặc campaign parameter đã được thiết kế cho mục đích đó. Đừng gửi full URL có query chứa dữ liệu người dùng sang mọi website bên ngoài chỉ để biết nguồn traffic.

## 11. Thực hành: quan sát Referer bằng Node.js

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Hai server chạy trên cùng hostname nhưng khác port:

- http://localhost:3000: trang nguồn, nơi đặt Referrer-Policy.
- http://localhost:3001: trang nhận, ghi lại Referer server nhận được và hiển thị document.referrer.

Khác port nghĩa là khác origin. Lab cho phép đổi policy ở trang nguồn và so sánh full URL, origin-only hoặc không có referrer.

### 11.1. Tạo file referrer-policy-lab.mjs

~~~js
import { createServer } from 'node:http';

const policies = new Set([
  'no-referrer',
  'no-referrer-when-downgrade',
  'same-origin',
  'origin',
  'strict-origin',
  'origin-when-cross-origin',
  'strict-origin-when-cross-origin',
  'unsafe-url',
]);

function sourcePage(policy) {
  const safePolicy = policies.has(policy)
    ? policy
    : 'strict-origin-when-cross-origin';

  return '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
    '<title>Referrer source lab</title></head><body>' +
    '<h1>Trang nguồn</h1>' +
    '<p>Policy đang áp dụng: <strong>' + safePolicy + '</strong></p>' +
    '<p>URL nguồn có path và query để quan sát phần browser gửi đi.</p>' +
    '<ul>' +
    '<li><a href="http://localhost:3000/destination?from=same-origin">' +
    'Điều hướng cùng origin</a></li>' +
    '<li><a href="http://localhost:3001/destination?from=cross-origin">' +
    'Điều hướng cross-origin</a></li>' +
    '<li><a href="http://localhost:3001/destination?from=element-no-referrer" ' +
    'referrerpolicy="no-referrer">Cross-origin với referrerpolicy=no-referrer</a></li>' +
    '<li><a href="http://localhost:3001/destination?from=rel-noreferrer" ' +
    'rel="noreferrer">Cross-origin với rel=noreferrer</a></li>' +
    '</ul>' +
    '<p><a href="/?policy=no-referrer">no-referrer</a> | ' +
    '<a href="/?policy=same-origin">same-origin</a> | ' +
    '<a href="/?policy=origin">origin</a> | ' +
    '<a href="/?policy=strict-origin">strict-origin</a> | ' +
    '<a href="/?policy=strict-origin-when-cross-origin">' +
    'strict-origin-when-cross-origin</a> | ' +
    '<a href="/?policy=unsafe-url">unsafe-url</a></p>' +
    '</body></html>';
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[char]);
}

function destinationPage(serverReferer) {
  const shown = serverReferer || '(Referer không được gửi)';
  return '<!doctype html><html lang="vi"><head><meta charset="utf-8">' +
    '<title>Referrer destination lab</title></head><body>' +
    '<h1>Trang nhận</h1>' +
    '<p>Referer server nhận được: <code>' + escapeHtml(shown) + '</code></p>' +
    '<p>document.referrer: <code id="document-referrer"></code></p>' +
    '<script>' +
    "document.querySelector('#document-referrer').textContent = " +
    'document.referrer || "(chuỗi rỗng)";' +
    '</script></body></html>';
}

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (url.pathname === '/destination') {
    const referer = req.headers.referer || '';
    console.log('[source origin destination] Referer:', referer || '(none)');
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(destinationPage(referer));
    return;
  }

  const policy = url.searchParams.get('policy') ||
    'strict-origin-when-cross-origin';

  if (!policies.has(policy)) {
    res.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Unsupported policy');
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Referrer-Policy': policy,
    'Cache-Control': 'no-store',
  });
  res.end(sourcePage(policy));
}).listen(3000, () => {
  console.log('Source: http://localhost:3000');
});

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3001');
  if (url.pathname !== '/destination') {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  const referer = req.headers.referer || '';
  console.log('[cross origin destination] Referer:', referer || '(none)');
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(destinationPage(referer));
}).listen(3001, () => {
  console.log('Destination: http://localhost:3001');
});
~~~

Hàm escapeHtml chỉ dùng để hiển thị giá trị Referer trong lab; không dùng kết quả này làm URL policy hoặc sanitizer tổng quát.

### 11.2. Chạy lab

~~~bash
node referrer-policy-lab.mjs
~~~

Mở http://localhost:3000/?policy=strict-origin-when-cross-origin.

1. Click **Điều hướng cùng origin**. Server port 3000 thường nhận full URL nguồn.
2. Quay lại trang nguồn, click **Điều hướng cross-origin**. Server port 3001 thường chỉ nhận origin http://localhost:3000/.
3. Click liên kết có referrerpolicy="no-referrer". Server port 3001 không nhận Referer.
4. Click liên kết có rel="noreferrer". Server port 3001 không nhận Referer và trang mới không có quan hệ opener thông thường.
5. Thử thay policy bằng các liên kết ở cuối trang và lặp lại để so sánh.

### 11.3. Kết quả mong đợi

Với URL nguồn http://localhost:3000/?policy=strict-origin-when-cross-origin:

| Thử nghiệm | Referer dự kiến |
| --- | --- |
| Cùng origin tới port 3000 | Full URL nguồn |
| Cross-origin tới port 3001 | http://localhost:3000/ |
| Element referrerpolicy="no-referrer" | Không có header |
| Element rel="noreferrer" | Không có header |

Browser có thể điều chỉnh referrer do privacy setting, extension hoặc phiên bản. Dùng log server và DevTools Network để xác minh request thực tế.

### 11.4. Kiểm tra bằng curl

Kiểm tra response header:

~~~bash
curl -I "http://localhost:3000/?policy=strict-origin-when-cross-origin"
~~~

Quan sát dòng:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

curl không tự mô phỏng chính sách referrer của browser khi điều hướng giữa các trang. Dùng nó để kiểm tra header response; dùng browser để kiểm tra hành vi Referer.

### 11.5. Giới hạn lab

- Lab dùng HTTP localhost, không mô phỏng HTTPS downgrade. Hành vi downgrade được mô tả trong bảng policy.
- Hai port khác nhau tạo hai origin; chúng không mô phỏng hai registrable domain khác nhau.
- Không đưa token, email thật hoặc dữ liệu nhạy cảm vào query string.
- Browser privacy setting và extension có thể làm header khác với kết quả dự kiến.

## 12. Kiểm tra triển khai trên website thật

Khi rà soát website:

1. Mở DevTools → Network.
2. Chọn một request điều hướng hoặc tải tài nguyên cross-origin.
3. Xem Request Headers và tìm Referer.
4. Chọn response HTML nguồn và kiểm tra Referrer-Policy.
5. Kiểm tra các link có referrerpolicy hoặc rel=noreferrer.
6. Kiểm tra request do Fetch API tạo có referrerPolicy riêng không.
7. Kiểm tra cả redirect chain và route lỗi.
8. Đối chiếu log ở server nhận để biết dữ liệu nào thực sự tới backend.

Có thể kiểm tra header từ terminal:

~~~bash
curl -I https://app.example.com/
~~~

Nếu response không có Referrer-Policy, browser sẽ dùng default của nó hoặc policy khác đã áp dụng trong tài liệu. Không nên coi header vắng mặt là một cấu hình an toàn cụ thể.

## 13. Checklist triển khai

1. **Đặt baseline:** cấu hình Referrer-Policy ở HTTP response header.
2. **Chọn policy:** thường cân nhắc strict-origin-when-cross-origin; dùng same-origin hoặc no-referrer nếu cần giảm thông tin hơn.
3. **Loại bỏ secret khỏi URL:** không đưa session ID, access token, reset token, email hoặc PII vào path/query.
4. **Kiểm tra same-origin/cross-origin:** nhớ rằng khác scheme, host hoặc port là khác origin.
5. **Kiểm tra downgrade:** không gửi referrer từ HTTPS xuống HTTP; ưu tiên loại bỏ endpoint HTTP.
6. **Xử lý link ngoài:** dùng referrerpolicy hoặc rel=noreferrer khi có yêu cầu riêng.
7. **Xử lý fetch:** chỉ override referrerPolicy khi request cần policy riêng; vẫn cấu hình CORS/auth đúng.
8. **Không tin document.referrer:** không dùng nó làm cơ chế xác thực, phân quyền hoặc CSRF defense.
9. **Kiểm tra toàn bộ route:** HTML chính, trang lỗi, redirect, trang login và trang tài khoản.
10. **Kiểm tra hạ tầng:** reverse proxy, CDN hoặc framework có thể xóa/ghi đè response header.
11. **Kiểm thử browser:** kiểm tra Network panel và browser/version thực tế mà sản phẩm hỗ trợ.
12. **Theo dõi rò rỉ:** rà soát log, analytics và URL của bên thứ ba để tránh gửi dữ liệu nhạy cảm.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Referer và Referrer-Policy là cùng một header.” | Referer là request header; Referrer-Policy là response header đặt quy tắc gửi referrer. |
| “Origin-only nghĩa là không lộ website nguồn.” | Origin vẫn tiết lộ scheme, host và port; chỉ path/query được lược bỏ. |
| “strict-origin-when-cross-origin luôn giấu toàn bộ URL.” | Request cùng origin vẫn có thể gửi full URL nguồn. |
| “no-referrer làm request biến mất.” | Request vẫn được gửi; chỉ referrer metadata bị bỏ. |
| “document.referrer rỗng chứng minh người dùng truy cập trực tiếp.” | Policy, privacy control hoặc browser có thể đã loại bỏ referrer. |
| “Referer là bằng chứng request hợp lệ.” | Header có thể thiếu hoặc bị thay đổi; không dùng để cấp quyền. |
| “CORS được bật thì referrer tự an toàn.” | CORS và Referrer-Policy giải quyết hai vấn đề khác nhau. |
| “no-referrer thay được CSRF token.” | CSRF token xác minh request; Referrer-Policy chỉ kiểm soát metadata nguồn. |
| “Fragment sẽ bị gửi nếu policy là unsafe-url.” | Fragment không được gửi trong HTTP Referer theo quy tắc URL. |
| “Không có header nghĩa là browser luôn dùng một policy cố định.” | Default có thể khác theo browser/version; hãy đặt policy tường minh. |
| “unsafe-url chỉ gửi origin.” | Nó gửi full URL kể cả cross-origin và downgrade; tránh dùng. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Sự khác nhau giữa Referer và Referrer-Policy là gì?

**Gợi ý trả lời:** Referer là request header chứa thông tin URL nguồn; Referrer-Policy là response header quy định browser gửi lượng thông tin đó như thế nào.

**Câu 2.** Origin gồm những thành phần nào?

**Gợi ý trả lời:** Scheme, host và port. Path, query và fragment không thuộc origin.

**Câu 3.** strict-origin-when-cross-origin gửi gì khi request cross-origin?

**Gợi ý trả lời:** Chỉ gửi origin; nếu HTTPS chuyển xuống HTTP thì không gửi referrer.

**Câu 4.** Vì sao same-origin request vẫn có thể làm lộ path/query?

**Gợi ý trả lời:** Policy strict-origin-when-cross-origin gửi full URL cho request cùng origin. Vì vậy không đặt secret trong URL.

**Câu 5.** document.referrer có thể dùng để xác thực người dùng không?

**Gợi ý trả lời:** Không. Giá trị có thể rỗng hoặc bị rút gọn do policy/privacy; quyền phải được xác minh ở server.

**Câu 6.** rel=noreferrer có tác dụng gì với liên kết mở tab mới?

**Gợi ý trả lời:** Không gửi Referer cho navigation và trong browser hiện đại cũng ngụ ý noopener, ngăn trang mới truy cập window.opener.

**Câu 7.** Referrer-Policy có thay CORS hoặc CSRF token không?

**Gợi ý trả lời:** Không. Nó chỉ kiểm soát referrer metadata; CORS quản lý quyền đọc response cross-origin, còn CSRF token xác minh request thay đổi trạng thái.

## Tài liệu tham khảo

- W3C — [Referrer Policy](https://www.w3.org/TR/referrer-policy/).
- MDN — [Referrer-Policy HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).
- MDN — [Referer HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer).
- MDN — [Document.referrer](https://developer.mozilla.org/en-US/docs/Web/API/Document/referrer), [HTML referrerpolicy attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/noreferrer).
- OWASP — [HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html).
