# HTTP script: vì sao trình duyệt chặn script không an toàn trên trang HTTPS

Một trang HTTPS được bảo vệ bằng TLS khi trình duyệt trao đổi dữ liệu với máy chủ. Nếu trang đó tải JavaScript từ một URL HTTP, nội dung script có thể bị thay đổi trên đường truyền bởi bên trung gian. Khi script được thực thi, nó chạy trong ngữ cảnh của trang nhúng và có thể đọc dữ liệu, gửi request hoặc thay đổi giao diện theo quyền của trang đó.

Đây là một dạng mixed content (nội dung hỗn hợp). Trình duyệt hiện đại xem script tải qua HTTP là nội dung chủ động có khả năng thay đổi hành vi trang, nên sẽ chặn request này khi trang cha được tải qua HTTPS. Cấu hình CORS, SRI hoặc thuộc tính crossorigin không biến một URL HTTP thành kết nối an toàn.

Bài học này tập trung vào script HTTP được tham chiếu từ trang HTTPS, các đường tải script thường gặp, cách trình duyệt xử lý redirect và cách sửa lỗi trong ứng dụng thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mixed content và vì sao HTTP script bị chặn trên trang HTTPS.
- Phân biệt blockable mixed content với upgradable mixed content.
- Nhận diện script HTTP trong HTML, JavaScript, module, worker và thư viện bên thứ ba.
- Hiểu cách redirect có thể biến một URL HTTPS ban đầu thành request HTTP không an toàn.
- Phân biệt vai trò của HTTPS, CSP, CORS, SRI và HSTS.
- Dùng upgrade-insecure-requests trong giai đoạn chuyển đổi.
- Sửa nguồn tải script và xác minh kết quả bằng DevTools.
- Thiết kế quy trình kiểm tra để ngăn URL HTTP quay trở lại trong bản build.

## 1. Mixed content là gì?

Mixed content xảy ra khi một tài liệu được tải qua một kết nối an toàn, thường là HTTPS, nhưng tài liệu đó yêu cầu một tài nguyên qua kết nối không an toàn như HTTP.

Ví dụ, người dùng mở:

~~~text
https://shop.example.test
~~~

Nhưng trang lại chứa:

~~~html
<script src="http://cdn.example.test/app.js"></script>
~~~

Tài liệu chính được bảo vệ bằng TLS, còn JavaScript được yêu cầu qua HTTP. Kẻ tấn công có khả năng can thiệp vào mạng có thể thay đổi nội dung app.js trước khi trình duyệt nhận được. Nếu script bị sửa được thực thi, nó có thể chạy với quyền của trang shop.example.test.

### 1.1 Vì sao script có rủi ro cao?

Script không chỉ là dữ liệu hiển thị. JavaScript được tải vào trang có thể:

- Đọc hoặc sửa DOM mà script được phép truy cập.
- Đọc dữ liệu trong bộ nhớ JavaScript của ứng dụng.
- Gửi request đến máy chủ và thực hiện các thao tác mà người dùng hiện tại được phép.
- Thay đổi form, nút bấm hoặc nội dung hiển thị.
- Đọc dữ liệu không được bảo vệ khỏi JavaScript, kể cả khi dữ liệu đó đến từ một API hợp lệ.
- Cài listener để quan sát tương tác của người dùng.

Một script bên thứ ba được nhúng trực tiếp thường chạy trong môi trường của trang nhúng. Same-Origin Policy không cô lập mã script chỉ vì file JavaScript được tải từ một hostname khác. Vì vậy, nguồn tải script và độ tin cậy của nhà cung cấp đều quan trọng.

### 1.2 HTTP và HTTPS khác nhau ở lớp truyền tải

HTTP gửi request và response mà không mã hóa, không xác thực máy chủ bằng TLS và không bảo đảm tính toàn vẹn dữ liệu trên đường truyền.

HTTPS sử dụng TLS để bảo vệ kết nối giữa trình duyệt và máy chủ. Trình duyệt xác minh chứng thư theo chuỗi tin cậy và tên máy chủ, sau đó mã hóa dữ liệu truyền đi.

TLS không chứng minh mã JavaScript của nhà cung cấp là an toàn về mặt nghiệp vụ. Nó bảo vệ đường truyền và xác thực endpoint theo chứng thư; ứng dụng vẫn phải quyết định có tin cậy nhà cung cấp script hay không.

## 2. Vì sao HTTP script bị chặn?

Trình duyệt phân loại một số tài nguyên được tải từ trang HTTPS theo mức độ ảnh hưởng đến bảo mật.

Script là nội dung có thể thực thi và thay đổi hành vi của trang. Do đó, request script qua HTTP được xem là blockable mixed content (nội dung hỗn hợp phải chặn).

Ví dụ:

~~~html
<!-- Trang cha được tải bằng HTTPS -->
<script src="http://static.example.test/app.js"></script>
~~~

Trình duyệt chặn request này trước khi JavaScript HTTP được thực thi. Người dùng thường thấy lỗi Mixed Content trong Console và request có trạng thái blocked trong Network.

Việc trang chính vẫn hiển thị không có nghĩa mọi tài nguyên đã tải thành công. CSS, ảnh hoặc nội dung tĩnh có thể hiển thị trong khi script quan trọng bị chặn, làm ứng dụng thiếu chức năng hoặc không khởi tạo được.

### 2.1 Blockable và upgradable mixed content

Các tài nguyên hỗn hợp được chia thành hai nhóm khái quát:

| Nhóm | Hành vi | Ví dụ thường gặp |
|---|---|---|
| Blockable mixed content | Trình duyệt chặn request không an toàn | Script, stylesheet, iframe, fetch/XHR, worker và nhiều loại nội dung có thể thực thi |
| Upgradable mixed content | Trình duyệt có thể tự nâng URL HTTP thành HTTPS trước khi tải | Một số tài nguyên ảnh, audio và video |

Danh sách và chi tiết triển khai có thể thay đổi theo tiêu chuẩn và trình duyệt. Điểm cần nhớ cho bài học này là script thuộc nhóm blockable. Trình duyệt không nên tự động cho chạy một script HTTP chỉ vì tài nguyên đó có vẻ vô hại.

### 2.2 Không phải cứ trang có HTTP URL là mixed content

Cần xét ngữ cảnh tải:

- Trang HTTP tải script HTTP: không phải mixed content vì tài liệu cha cũng không được tải bằng HTTPS. Trang vẫn không an toàn.
- Trang HTTPS tải script HTTP: mixed content và script bị chặn.
- Trang HTTPS tải script HTTPS: không phải mixed content; vẫn cần kiểm tra nguồn script và CSP.
- Trang HTTPS tải tài nguyên từ http://localhost hoặc loopback: một số địa chỉ loopback được trình duyệt xem là potentially trustworthy cho mục đích secure context. Đây là ngoại lệ phục vụ phát triển cục bộ, không phải lý do để dùng HTTP cho máy chủ triển khai.

Đừng dùng một địa chỉ IP nội bộ bất kỳ và giả định nó được hưởng ngoại lệ localhost. Hãy kiểm thử đúng hostname và trình duyệt mà ứng dụng hỗ trợ.

## 3. Những cách script HTTP đi vào trang

URL HTTP không nhất thiết xuất hiện trực tiếp trong file HTML. Nó có thể đến từ cấu hình, mã JavaScript, package hoặc script bên thứ ba.

### 3.1 Script tag trong HTML

Đây là trường hợp dễ nhận biết:

~~~html
<script src="http://cdn.example.test/library.js"></script>
~~~

Khi trang được phục vụ qua HTTPS, trình duyệt chặn script này.

Sửa URL sang HTTPS sau khi xác minh máy chủ hỗ trợ TLS:

~~~html
<script src="https://cdn.example.test/library.js"></script>
~~~

Không chỉ thay chuỗi URL cho hết lỗi. Hãy kiểm tra hostname, chứng thư, redirect và nội dung thực tế của tài nguyên.

### 3.2 Script được tạo bằng JavaScript

Ứng dụng có thể tạo phần tử script sau khi người dùng mở một tính năng:

~~~js
const script = document.createElement("script");
script.src = "http://cdn.example.test/chart.js";
document.head.append(script);
~~~

Đường tải này vẫn chịu quy tắc mixed content. Việc tạo phần tử bằng JavaScript không né được kiểm tra của trình duyệt.

Hãy tìm cả các vị trí gán src động:

~~~js
script.src = config.libraryUrl;
script.setAttribute("src", config.libraryUrl);
~~~

Nếu config.libraryUrl đến từ API, CMS, remote config hoặc biến môi trường, cần kiểm tra nguồn dữ liệu đó thay vì chỉ tìm chuỗi http:// trong HTML.

### 3.3 JavaScript module và dynamic import

Module script có thể được khai báo trong HTML:

~~~html
<script type="module" src="http://cdn.example.test/main.js"></script>
~~~

Hoặc được tải động:

~~~js
const module = await import("http://cdn.example.test/feature.js");
~~~

Các request module vẫn phải tuân theo chính sách mixed content. Module script cũng có quy tắc CORS riêng khi tải cross-origin; CORS không làm request HTTP trở nên an toàn.

Hãy chuyển module sang HTTPS và cấu hình CORS trên máy chủ nếu module cross-origin cần được phép tải theo chế độ CORS.

### 3.4 Worker và importScripts

Worker chạy trong một môi trường JavaScript riêng, nhưng script khởi tạo worker vẫn phải được tải an toàn và tuân theo các ràng buộc origin của Worker API.

Ví dụ không phù hợp:

~~~js
const worker = new Worker("http://app.example.test/workers/search.js");
~~~

Trang HTTPS không thể dùng URL HTTP này để khởi tạo worker an toàn. Hãy phục vụ worker qua HTTPS cùng origin theo yêu cầu của API:

~~~js
const worker = new Worker("/workers/search.js");
~~~

Trong classic worker, importScripts() cũng có thể tải thêm script. Các URL phụ thuộc trong worker phải được kiểm tra để không tạo ra request không an toàn hoặc vượt ngoài chính sách của ứng dụng.

Service Worker yêu cầu secure context. Trên website triển khai, đăng ký Service Worker qua HTTPS; ngoại lệ localhost chỉ dành cho phát triển cục bộ theo quy tắc secure context của trình duyệt.

### 3.5 Script bên thứ ba, tag manager và widget

Một script bên thứ ba có thể chèn thêm script khác. Ví dụ:

~~~js
const loader = document.createElement("script");
loader.src = "http://legacy-vendor.example.test/widget.js";
document.head.append(loader);
~~~

Nếu script ban đầu được tải qua HTTPS nhưng sau đó tạo URL HTTP, request thứ hai vẫn là mixed content và bị chặn.

Các nguồn cần rà soát:

- Tag manager và analytics.
- SDK thanh toán hoặc đăng nhập.
- Widget chat và hỗ trợ khách hàng.
- Thư viện biểu đồ, trình soạn thảo và trình xem tài liệu.
- Script quảng cáo hoặc đo lường.
- Remote configuration và CMS có lưu URL script.

Một script được tải từ HTTPS vẫn có thể là nguồn đưa URL HTTP vào trang. Hãy kiểm tra toàn bộ chuỗi tải, không chỉ thẻ script đầu tiên.

## 4. Redirect HTTPS sang HTTP vẫn có thể bị chặn

Một lỗi khó tìm là URL trong mã có scheme HTTPS nhưng máy chủ redirect sang HTTP.

~~~text
Trang HTTPS
    |
    | GET https://cdn.example.test/app.js
    v
Máy chủ CDN
    |
    | 302 Location: http://legacy.example.test/app.js
    v
Đích HTTP
    |
    X Trình duyệt chặn mixed content
~~~

URL ban đầu có HTTPS không đảm bảo response cuối cùng vẫn dùng HTTPS. Trình duyệt kiểm tra request và các bước điều hướng tiếp theo; nếu tài nguyên script cuối cùng được tải qua HTTP, request không an toàn sẽ bị chặn.

Kiểm tra trong Network:

- Request URL ban đầu.
- Mã trạng thái 301, 302, 307 hoặc 308.
- Header Location.
- URL cuối cùng.
- Máy chủ nào tạo redirect.
- Redirect có đưa sang hostname hoặc scheme ngoài dự kiến không.

Sửa redirect ở máy chủ nguồn để đích cuối cùng là HTTPS. Nếu nhà cung cấp chỉ hỗ trợ HTTP, hãy thay thế hoặc loại bỏ tích hợp đó.

Không dựa vào việc trình duyệt tự theo redirect để biến một endpoint HTTP thành an toàn.

## 5. Mixed content và các cơ chế bảo mật khác

Các cơ chế bảo mật web giải quyết những câu hỏi khác nhau. Không thể dùng một cơ chế để bỏ qua việc tải script qua HTTP.

| Cơ chế | Câu hỏi được giải quyết | Có làm HTTP script an toàn không? |
|---|---|---|
| HTTPS/TLS | Kết nối đến máy chủ có được mã hóa và xác thực không? | Không trực tiếp; tài nguyên phải thực sự được tải qua HTTPS hợp lệ |
| Mixed Content blocking | Trang HTTPS có đang yêu cầu tài nguyên không an toàn không? | Chặn request script HTTP |
| CORS | Origin nào được phép đọc response cross-origin theo chế độ CORS? | Không |
| SRI | Nội dung tải về có khớp hash mong đợi không? | Không |
| CSP script-src | Nguồn script nào được phép tải hoặc thực thi? | Không |
| HSTS | Trình duyệt có nên tự nâng request HTTP của hostname đã biết sang HTTPS không? | Có thể giúp nâng URL của host có HSTS, nhưng không thay thế sửa URL |
| Trusted Types | Dữ liệu nào được phép đi vào một số DOM sink? | Không |

### 5.1 CORS không bỏ qua mixed content

CORS kiểm soát quyền truy cập response giữa các origin. Ví dụ, module script cross-origin cần máy chủ trả header CORS phù hợp.

Nhưng CORS không nâng cấp HTTP thành HTTPS. Nếu trang HTTPS yêu cầu script qua HTTP, trình duyệt có thể chặn request ở lớp mixed content trước khi CORS trở thành yếu tố quyết định.

Thêm Access-Control-Allow-Origin: * vào máy chủ HTTP không phải cách sửa mixed content.

### 5.2 SRI không thay thế HTTPS

Subresource Integrity (SRI) cho phép trình duyệt kiểm tra nội dung tải về có khớp hash mong đợi hay không:

~~~html
<script
  src="https://cdn.example.test/library-4.2.0.min.js"
  integrity="sha384-BASE64_HASH_DUOC_TAO_TU_FILE"
  crossorigin="anonymous"></script>
~~~

SRI có thể phát hiện nội dung bị thay đổi so với hash đã ghim. Tuy nhiên:

- SRI không làm request HTTP trở thành HTTPS.
- SRI không thay thế kiểm soát nguồn script.
- Hash cần được tạo và cập nhật từ artifact đáng tin cậy.
- Script động hoặc phiên bản thay đổi cần quy trình quản lý hash phù hợp.

Trước tiên phải có đường truyền HTTPS hợp lệ. Sau đó, dùng SRI khi phù hợp để kiểm tra tính toàn vẹn của nội dung.

### 5.3 CSP script-src không cho phép vượt qua mixed content

CSP script-src giới hạn nguồn script mà trang được phép tải:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.test
~~~

Directive này giúp giới hạn nguồn script. Tuy nhiên, nếu trang vẫn có URL HTTP, trình duyệt có thể chặn request đó theo mixed content dù một cấu hình CSP khác vô tình cho phép nguồn tương ứng.

Không đưa scheme HTTP vào allowlist chỉ để làm ứng dụng chạy. Hãy dùng HTTPS và danh sách nguồn tối thiểu.

## 6. Nâng cấp URL bằng CSP upgrade-insecure-requests

Trong quá trình chuyển đổi ứng dụng cũ, có thể còn nhiều URL HTTP nằm trong HTML, CSS, JavaScript hoặc dữ liệu CMS. CSP cung cấp directive upgrade-insecure-requests để yêu cầu trình duyệt nâng các URL không an toàn thành HTTPS trước khi tải.

Ví dụ:

~~~http
Content-Security-Policy: upgrade-insecure-requests
~~~

Trang có thể kết hợp directive này với các chính sách khác:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.test; upgrade-insecure-requests
~~~

Khi trình duyệt xử lý một URL tài nguyên HTTP phù hợp, nó sẽ thử tải qua HTTPS. Ví dụ:

~~~text
http://cdn.example.test/app.js
          |
          | upgrade-insecure-requests
          v
https://cdn.example.test/app.js
~~~

### 6.1 Điều kiện để nâng cấp thành công

Directive chỉ giúp nếu endpoint HTTPS thực sự hoạt động:

- Hostname có chứng thư TLS hợp lệ.
- Máy chủ phục vụ đúng tài nguyên trên HTTPS.
- Đường dẫn và cấu hình virtual host tương ứng.
- Redirect tiếp theo không quay lại HTTP.
- CSP script-src cho phép nguồn HTTPS sau khi nâng cấp.
- Máy chủ không phụ thuộc vào cookie hoặc cấu hình chỉ hoạt động trên HTTP.

Nếu máy chủ không hỗ trợ HTTPS hoặc chứng thư không hợp lệ, request nâng cấp sẽ thất bại. Directive không thể tạo TLS cho máy chủ không có TLS.

### 6.2 Directive không thay thế việc sửa mã nguồn

upgrade-insecure-requests là lớp hỗ trợ chuyển đổi và giảm lỗi URL cũ. Hãy cập nhật URL gốc trong:

- HTML template.
- JavaScript và module.
- Cấu hình build.
- Remote configuration.
- CMS và cơ sở dữ liệu.
- Tag manager và dashboard của nhà cung cấp.
- Redirect trên CDN hoặc reverse proxy.

Khi URL gốc đã được sửa, ứng dụng dễ kiểm soát hơn và ít phụ thuộc vào hành vi nâng cấp của trình duyệt.

### 6.3 Report-Only không thực hiện nâng cấp

Không dùng Content-Security-Policy-Report-Only để kỳ vọng URL HTTP được nâng lên HTTPS. Chế độ Report-Only dùng để báo cáo vi phạm CSP theo chính sách thử nghiệm; nó không thực thi hành vi của upgrade-insecure-requests.

Nếu muốn nâng cấp thực tế, directive phải nằm trong CSP enforcement header. Trước khi bật, xác nhận endpoint HTTPS của các URL cần nâng cấp đã sẵn sàng.

## 7. HSTS có thể hỗ trợ nhưng không thay thế sửa URL

HTTP Strict Transport Security (HSTS) cho phép máy chủ yêu cầu trình duyệt luôn dùng HTTPS cho hostname đã khai báo:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Nếu hostname đã có chính sách HSTS còn hiệu lực, trình duyệt có thể nâng request HTTP đến hostname đó thành HTTPS trước khi gửi ra mạng.

HSTS hữu ích khi:

- Hostname đã hỗ trợ HTTPS đầy đủ.
- Ứng dụng cần ngăn truy cập HTTP đến hostname đã triển khai.
- Có quy trình triển khai và gia hạn chứng thư TLS ổn định.

HSTS không giải quyết mọi mixed content:

- Không giúp hostname bên thứ ba chưa có HSTS.
- Không sửa URL trong mã nguồn hoặc cấu hình.
- Không bảo đảm redirect của nhà cung cấp không quay lại HTTP.
- Không thay thế CSP upgrade-insecure-requests.
- includeSubDomains có thể ảnh hưởng mọi subdomain, nên chỉ bật khi toàn bộ subdomain đã sẵn sàng HTTPS.

HSTS thường được thiết lập từ response HTTPS. Với website mới, hãy triển khai HTTPS và kiểm tra toàn bộ subdomain trước khi cân nhắc includeSubDomains hoặc preload.

## 8. Cách sửa lỗi HTTP script

### 8.1 Xác minh endpoint HTTPS

Trước khi thay URL, thử mở trực tiếp endpoint HTTPS trong trình duyệt hoặc kiểm tra response bằng công cụ HTTP:

~~~bash
curl -I https://cdn.example.test/app.js
~~~

Kiểm tra:

- TLS handshake và chứng thư có hợp lệ không.
- Response có trả đúng tài nguyên không.
- Có redirect không.
- Content-Type có phù hợp với JavaScript không.
- Máy chủ có trả lỗi do cấu hình host hoặc đường dẫn không.

Không dùng tùy chọn bỏ qua xác minh chứng thư như -k để kết luận endpoint HTTPS đã sẵn sàng. Chứng thư không được xác minh là một lỗi cần sửa.

### 8.2 Thay URL trong HTML và mã nguồn

Thay:

~~~html
<script src="http://cdn.example.test/app.js"></script>
~~~

Bằng:

~~~html
<script src="https://cdn.example.test/app.js"></script>
~~~

Với script được tạo động:

~~~js
const script = document.createElement("script");
script.src = "https://cdn.example.test/app.js";
script.async = true;
document.head.append(script);
~~~

Nếu URL được đọc từ cấu hình, hãy sửa cấu hình gốc và kiểm tra dữ liệu đã được cache hoặc publish.

### 8.3 Ưu tiên URL cùng origin khi có thể

Nếu ứng dụng đã đóng gói thư viện trong artifact của mình, có thể phục vụ từ cùng origin:

~~~html
<script src="/assets/app.8f2a.js"></script>
~~~

Đường dẫn tương đối theo origin của trang sẽ dùng HTTPS khi trang được tải qua HTTPS. Cách này giảm phụ thuộc vào một hostname bên ngoài, nhưng vẫn cần kiểm soát quy trình build, phân phối và tính toàn vẹn của artifact.

### 8.4 Xử lý nhà cung cấp chỉ hỗ trợ HTTP

Nếu nhà cung cấp không có endpoint HTTPS hợp lệ:

1. Liên hệ nhà cung cấp để xác nhận hỗ trợ TLS và endpoint chính thức.
2. Tìm SDK hoặc nhà cung cấp thay thế có hỗ trợ HTTPS.
3. Nếu phù hợp, đóng gói một phiên bản thư viện đã được kiểm tra và phân phối qua pipeline HTTPS của tổ chức.
4. Nếu script không cần chạy trong ngữ cảnh trang chính, cân nhắc tích hợp qua iframe trên origin riêng với sandbox và giao thức message có kiểm tra.
5. Nếu không có phương án an toàn, bỏ tính năng hoặc tích hợp đó.

Không dùng proxy HTTP công khai tùy tiện để “bọc” một script không an toàn. Proxy cần được kiểm soát, xác minh nguồn, quản lý phiên bản và phục vụ qua HTTPS; nếu proxy chỉ chuyển tiếp nội dung tùy ý, rủi ro chuỗi cung ứng vẫn còn.

## 9. Kiểm tra nguồn script trong ứng dụng

Một lỗi mixed content có thể được tạo bởi nhiều lớp ứng dụng. Hãy rà soát theo luồng dữ liệu:

~~~text
HTML / cấu hình / API / CMS
          |
          v
   Script loader hoặc module
          |
          v
   Tạo URL script / worker
          |
          v
     HTTP hoặc HTTPS?
          |
          v
   Redirect và response cuối
          |
          v
    Mixed content check
          |
      +---+---+
      |       |
    HTTPS    HTTP
      |       |
   CSP/CORS   Bị chặn
   và tải tiếp
~~~

Các điểm cần tìm trong code:

~~~js
script.src = value;
script.setAttribute("src", value);
new Worker(value);
import(value);
importScripts(value);
~~~

Đây là các vị trí điều tra. Mỗi API có quy tắc origin, CORS và tải tài nguyên riêng; không kết luận rằng mọi API đều là cùng một loại sink.

Tìm các chuỗi URL cũ trong source và artifact build. Ví dụ với ripgrep:

~~~bash
rg -n --hidden "http://" src public config
~~~

Sau đó phân loại kết quả:

- URL tài nguyên thật sự được tải từ trang.
- URL trong tài liệu hoặc ví dụ không chạy.
- URL chỉ dùng cho backend nội bộ.
- URL redirect hoặc remote config.
- URL test chỉ xuất hiện trong môi trường phát triển.

Không thay mọi chuỗi http:// một cách tự động. Có thể có URL tài liệu, callback test hoặc dữ liệu không phải request tài nguyên. Hãy xác định từng trường hợp trước khi sửa.

## 10. Kiểm thử bằng DevTools

### 10.1 Console

Mở trang HTTPS, bật DevTools và xem Console. Khi trình duyệt chặn mixed content, thông báo thường nêu:

- Trang cha có origin HTTPS.
- URL HTTP bị yêu cầu.
- Loại tài nguyên bị chặn, ví dụ script.
- Lý do trình duyệt không tải nội dung không an toàn.

Đọc URL cụ thể để lần về script tag, module loader hoặc thư viện tạo request.

### 10.2 Network

Trong Network:

1. Bật Preserve log để giữ request qua redirect.
2. Tải lại trang.
3. Lọc theo JS hoặc tìm hostname của script.
4. Xem request bị blocked hoặc trạng thái lỗi.
5. Mở Initiator để tìm đoạn mã tạo request.
6. Kiểm tra redirect chain và URL cuối cùng.
7. Xác minh script HTTPS đã tải thành công sau khi sửa.

Nếu URL ban đầu là HTTPS nhưng đích cuối cùng là HTTP, lần theo từng response Location.

### 10.3 Security panel

Nếu DevTools có Security panel, kiểm tra trạng thái kết nối của trang và tài nguyên liên quan. Panel có thể giúp phát hiện certificate, TLS hoặc mixed-content issue.

Thông tin hiển thị khác nhau theo trình duyệt và phiên bản. Console và Network vẫn là nơi cần kiểm tra request cụ thể.

### 10.4 Xác nhận script thực sự được tải

Sau khi sửa, đừng chỉ dựa vào việc lỗi Console biến mất. Xác minh:

- Request script dùng HTTPS.
- TLS certificate hợp lệ.
- Response có đúng nội dung.
- Script không redirect sang HTTP.
- CSP cho phép script.
- Ứng dụng khởi tạo chức năng tương ứng thành công.

## 11. Ví dụ cấu hình CSP cho trang HTTPS

Một cấu hình khởi đầu có thể giới hạn script vào cùng origin và CDN đã duyệt, đồng thời nâng các URL HTTP cũ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.test; upgrade-insecure-requests; object-src 'none'; base-uri 'self'
~~~

Giải thích:

- default-src 'self': mặc định chỉ cho phép tài nguyên cùng origin nếu directive cụ thể không ghi đè.
- script-src 'self' https://cdn.example.test: giới hạn nguồn script.
- upgrade-insecure-requests: yêu cầu nâng các URL không an toàn sang HTTPS.
- object-src 'none': chặn nội dung plugin kiểu object.
- base-uri 'self': giới hạn URL cơ sở mà thẻ base có thể đặt.

Đây chỉ là ví dụ để minh họa. CSP thật cần phản ánh script inline, nonce/hash, worker, API và các tài nguyên mà ứng dụng đang dùng. Không sao chép nguyên header nếu chưa kiểm thử.

Directive block-all-mixed-content đã lỗi thời trong các trình duyệt hiện đại vì blockable mixed content vốn đã bị chặn. Không thêm directive này như biện pháp bảo vệ chính.

## 12. Các tình huống đặc biệt

### 12.1 URL protocol-relative

URL bắt đầu bằng hai dấu gạch chéo:

~~~html
<script src="//cdn.example.test/app.js"></script>
~~~

Đây là URL kế thừa scheme của trang hiện tại. Trên trang HTTPS, nó thường được phân giải thành HTTPS; trên trang HTTP, nó thành HTTP.

Cách viết này không tự bảo đảm máy chủ hỗ trợ HTTPS. Nếu endpoint không phục vụ HTTPS, request có thể thất bại. Trong ứng dụng mới, ưu tiên URL HTTPS rõ ràng hoặc URL cùng origin để dễ review.

### 12.2 URL được tạo từ API hoặc CMS

Nếu máy chủ trả:

~~~json
{
  "scriptUrl": "http://cdn.example.test/widget.js"
}
~~~

thì sửa ở frontend chưa chắc đủ. Cần sửa dữ liệu cấu hình gốc, migration dữ liệu và giao diện quản trị có thể tạo URL đó.

Ở phía frontend, chỉ chấp nhận scheme và origin đã được phê duyệt. Không dùng URL từ API để tải script tùy ý.

### 12.3 Redirect của CDN

CDN có thể trả redirect theo vùng, phiên bản hoặc cấu hình cache. Kiểm tra response ở môi trường production vì local hoặc staging có thể đi theo đường khác.

Nếu CDN có nhiều hostname, xác định hostname nào phục vụ tài nguyên cuối cùng và đưa đúng hostname HTTPS vào CSP.

### 12.4 localhost trong phát triển

Trình duyệt xem localhost và địa chỉ loopback là potentially trustworthy trong một số quy tắc secure context. Vì vậy, một số request HTTP đến loopback có thể không bị phân loại giống HTTP đến máy chủ bên ngoài.

Điều này giúp chạy công cụ phát triển cục bộ, nhưng không nên được dùng để thiết kế production. Kiểm thử staging và production với hostname thật, TLS thật và cấu hình redirect thật.

### 12.5 WebSocket không an toàn

Một trang HTTPS dùng ws:// để mở kết nối WebSocket có thể gặp mixed-content blocking. Dùng wss:// để bảo vệ kết nối. Đây là request kết nối thời gian thực, không phải script file, nhưng cùng nguyên tắc là trang bảo mật không nên hạ cấp kênh truyền xuống HTTP.

## 13. Lỗi triển khai thường gặp

### 13.1 Chỉ sửa script tag trong HTML

Script loader hoặc tag manager có thể tiếp tục tạo URL HTTP. Rà soát initiator và toàn bộ chuỗi tải.

### 13.2 Nghĩ CORS giải quyết được mixed content

CORS không nâng scheme và không bỏ qua mixed-content blocking. Cần endpoint HTTPS.

### 13.3 Nghĩ SRI cho phép tải script HTTP

SRI kiểm tra hash của nội dung; nó không biến đường truyền HTTP thành an toàn. Trình duyệt vẫn chặn mixed content.

### 13.4 Dùng upgrade-insecure-requests mà không kiểm tra endpoint

Nếu host không có HTTPS hợp lệ, request được nâng cấp sẽ thất bại. Xác minh TLS và response trước khi bật directive.

### 13.5 Bỏ qua redirect

URL nguồn là HTTPS nhưng redirect cuối sang HTTP vẫn có thể bị chặn. Bật Preserve log và xem toàn bộ redirect chain.

### 13.6 Chỉ kiểm thử local

Localhost có ngoại lệ secure-context nhất định và cấu hình CDN/redirect khác production. Kiểm thử trên môi trường HTTPS có hostname thật.

### 13.7 Thêm HTTP vào CSP allowlist

Cho phép nguồn HTTP trong script-src không làm nó an toàn. Hãy dùng HTTPS và allowlist origin tối thiểu.

### 13.8 Tin rằng script từ CDN khác origin bị SOP cô lập

Script được nhúng trực tiếp thường chạy với quyền của trang nhúng. Hãy xem nhà cung cấp script như một phần của trusted computing base của trang.

## 14. Bài thực hành

Thực hiện trên hai máy chủ lab do bạn kiểm soát. Không dùng script độc hại hoặc endpoint bên ngoài.

### Bài 1: Quan sát HTTP script bị chặn

Tạo một trang HTTPS và đặt một script URL HTTP trong HTML. Mở Console và Network. Ghi lại thông báo mixed content và xác định request bị chặn.

### Bài 2: Sửa URL sang HTTPS

Cấu hình cùng script trên endpoint HTTPS có chứng thư hợp lệ. Thay URL và tải lại trang. Xác nhận request thành công, không redirect về HTTP và script được thực thi.

### Bài 3: Kiểm tra redirect

Cho endpoint HTTPS lab trả redirect đến endpoint HTTP lab. Nhúng URL HTTPS ban đầu vào trang. Bật Preserve log và quan sát request cuối bị chặn. Sửa redirect để đích cuối dùng HTTPS.

### Bài 4: Thử upgrade-insecure-requests

Đặt CSP enforcement:

~~~http
Content-Security-Policy: upgrade-insecure-requests; script-src 'self' https://cdn.example.test
~~~

Để một URL script HTTP trỏ đến host lab đã có HTTPS. Xác nhận trình duyệt thử URL HTTPS. Sau đó thử host không có HTTPS và ghi lại lỗi kết nối.

### Bài 5: Phân biệt CORS và mixed content

Dùng một script module cross-origin trên endpoint HTTP. Thử thêm Access-Control-Allow-Origin vào response. Quan sát request vẫn bị chặn bởi mixed content. Sau đó chuyển endpoint sang HTTPS và cấu hình CORS đúng để so sánh.

### Bài 6: Rà soát script loader

Tạo một loader đọc URL từ cấu hình JSON. Cố ý đặt URL HTTP, xác định nơi tạo request bằng Initiator. Sửa cấu hình để chỉ chấp nhận HTTPS và origin đã duyệt.

## 15. Checklist review HTTP script

- [ ] Trang triển khai được phục vụ qua HTTPS với chứng thư hợp lệ.
- [ ] Không có script src HTTP trong HTML hoặc template.
- [ ] Script được tạo động chỉ dùng URL HTTPS hoặc đường dẫn cùng origin.
- [ ] Module script và dynamic import không dùng URL HTTP.
- [ ] Worker và script phụ thuộc của worker được phục vụ an toàn.
- [ ] Tag manager, analytics, SDK và widget bên thứ ba không tạo request HTTP.
- [ ] Đã kiểm tra redirect chain đến URL cuối cùng.
- [ ] CSP script-src chỉ cho phép nguồn script cần thiết.
- [ ] Đã cân nhắc upgrade-insecure-requests trong giai đoạn chuyển đổi.
- [ ] Không dựa vào block-all-mixed-content như cơ chế bảo vệ chính.
- [ ] Không dùng CORS hoặc SRI để thay thế HTTPS.
- [ ] Endpoint CDN có TLS và chứng thư hợp lệ.
- [ ] HSTS được triển khai theo kế hoạch phù hợp với hostname/subdomain.
- [ ] Đã kiểm tra Console, Network và Initiator trên môi trường triển khai.
- [ ] Có kiểm tra build/config để phát hiện URL HTTP mới.

## 16. Câu hỏi tự kiểm tra

**1. Mixed content là gì?**

Là tình huống tài liệu được tải qua HTTPS nhưng yêu cầu tài nguyên qua kết nối không an toàn như HTTP.

**2. Vì sao HTTP script bị chặn?**

Vì script có thể thực thi mã với quyền của trang. Nếu tải qua HTTP, nội dung có thể bị thay đổi trên đường truyền.

**3. Script thuộc blockable hay upgradable mixed content?**

Script thuộc nhóm blockable mixed content. Trình duyệt chặn request HTTP thay vì tự động coi script là an toàn.

**4. CORS có bỏ qua mixed-content blocking không?**

Không. CORS kiểm soát quyền truy cập response giữa các origin; nó không biến HTTP thành HTTPS.

**5. SRI có cho phép tải script HTTP không?**

Không. SRI kiểm tra hash nội dung và không thay thế TLS hoặc mixed-content policy.

**6. HTTPS URL redirect sang HTTP có an toàn không?**

Không. Đích cuối vẫn là HTTP và request script có thể bị chặn. Cần sửa redirect để giữ HTTPS.

**7. upgrade-insecure-requests làm gì?**

Nó yêu cầu trình duyệt nâng các URL không an toàn sang HTTPS trước khi tải. Endpoint phải hỗ trợ HTTPS hợp lệ để request thành công.

**8. Report-Only có thực thi upgrade-insecure-requests không?**

Không. Report-Only chỉ báo cáo theo chính sách thử nghiệm; nó không thực hiện việc nâng URL.

**9. localhost có thể có ngoại lệ nào?**

Một số hostname và địa chỉ loopback được xem là potentially trustworthy cho secure context. Đây là ngoại lệ phục vụ phát triển cục bộ, không áp dụng chung cho máy chủ production.

**10. Cách xác minh đã sửa mixed content?**

Kiểm tra Console và Network, xác nhận request script cuối dùng HTTPS, chứng thư hợp lệ, không redirect sang HTTP và chức năng ứng dụng hoạt động.

## Ghi nhớ

Trang HTTPS phải tải script qua HTTPS. Script HTTP là blockable mixed content vì mã có thể thay đổi hành vi và truy cập dữ liệu của trang. CORS, SRI và CSP script-src có vai trò riêng nhưng không thay thế TLS. Hãy sửa URL và redirect gốc, dùng upgrade-insecure-requests khi cần chuyển đổi, rồi xác minh toàn bộ request chain trong DevTools.

## Tài liệu tham khảo

- [MDN: Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content)
- [W3C: Mixed Content](https://www.w3.org/TR/mixed-content/)
- [MDN: Content-Security-Policy upgrade-insecure-requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/upgrade-insecure-requests)
- [MDN: Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
