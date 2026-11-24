# Subresource Integrity: xác minh nội dung script và stylesheet trước khi sử dụng

> **Chương:** Resource integrity  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Subresource Integrity (SRI)** cho phép website khai báo trước nội dung chính xác mà browser phải nhận được từ một tài nguyên bên ngoài. Ứng dụng cung cấp một digest mật mã trong thuộc tính **integrity**. Browser tải tài nguyên, tính lại hash trên nội dung nhận được và chỉ thực thi script hoặc áp dụng stylesheet khi digest khớp.

SRI đặc biệt hữu ích khi tải thư viện JavaScript hoặc CSS từ CDN. Nếu CDN bị xâm nhập, file bị thay thế hoặc nội dung bị sửa ngoài dự kiến, browser phát hiện sai khác và từ chối sử dụng tài nguyên. SRI vì vậy là một lớp bảo vệ chuỗi cung ứng phần mềm ở phía trình duyệt.

SRI không xác thực toàn bộ website, không thay thế HTTPS/CSP/CORS và không tự bảo vệ các dependency mà script tải tiếp khi chạy. Giá trị hash phải được tạo từ đúng file cuối cùng được phát hành, review cùng thay đổi dependency và cập nhật đồng bộ với URL phiên bản.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích SRI bảo vệ tài nguyên ngoài bằng cách so sánh nội dung với hash đã khai báo.
2. Dùng SHA-256, SHA-384 hoặc SHA-512 để tạo integrity metadata.
3. Gắn thuộc tính integrity cho script và stylesheet.
4. Hiểu vì sao tài nguyên cross-origin có SRI phải dùng CORS và thường cần crossorigin="anonymous".
5. Phân biệt vai trò của SRI, CORS, CSP, HTTPS và package lockfile.
6. Hiểu cách browser chọn thuật toán hash mạnh nhất và xử lý nhiều hash.
7. Nhận diện rủi ro khi CDN minify, rewrite hoặc thay đổi nội dung.
8. Dùng integrity option của Fetch API để kiểm tra response được fetch.
9. Hiểu giới hạn của SRI với module graph, script tải động và dependency bắc cầu.
10. Triển khai Integrity-Policy ở chế độ Report-Only khi browser mục tiêu hỗ trợ.
11. Thực hành tạo hash và quan sát browser từ chối script có nội dung bị thay đổi.

## 1. SRI giải quyết rủi ro nào?

### 1.1 Tin cậy CDN không đồng nghĩa tin mọi nội dung CDN trả về

Một website thường tải thư viện từ dịch vụ bên ngoài:

~~~html
<script src="https://cdn.example.net/library.js"></script>
<link rel="stylesheet" href="https://cdn.example.net/theme.css">
~~~

Cách này giảm tải cho server ứng dụng và tận dụng cache của CDN. Tuy nhiên, browser sẽ sử dụng đúng nội dung mà CDN trả về tại thời điểm request.

Nếu attacker chiếm quyền quản trị CDN, xâm nhập tài khoản nhà cung cấp, thay đổi object storage hoặc sửa response qua một hệ thống trung gian, file có thể chứa mã độc. Script bên thứ ba chạy trong document của ứng dụng thường có quyền rất lớn: nó có thể đọc DOM, thao tác giao diện và gửi request theo quyền của trang.

SRI cho phép ứng dụng nói rõ: “Chỉ sử dụng file nếu bytes nhận được khớp với phiên bản mà bản phát hành này đã duyệt.”

### 1.2 Browser kiểm tra trước khi thực thi hoặc áp dụng

Luồng cơ bản:

~~~text
HTML document
    |
    | src + integrity metadata
    v
Browser tải tài nguyên
    |
    v
Tính SHA-256 / SHA-384 / SHA-512
    |
    v
So sánh digest với integrity metadata
    |
    +---- Khớp ----> Thực thi script / áp dụng stylesheet
    |
    +---- Sai ------> Từ chối tài nguyên, phát sinh network error
~~~

Với script, browser xác minh trước khi thực thi. Với stylesheet, browser xác minh trước khi áp dụng. Khi hash không khớp, tài nguyên bị từ chối và thường có thông báo integrity check failed trong DevTools Console.

SRI kiểm tra nội dung được tải. Nó không kiểm tra file đó có an toàn về logic hay không. Nếu nhóm phát triển chủ động đưa một thư viện độc hại vào bản phát hành rồi cập nhật hash tương ứng, SRI vẫn xác nhận đúng bytes đã khai báo.

### 1.3 HTTPS và SRI giải quyết hai rủi ro khác nhau

HTTPS/TLS xác thực server và bảo vệ kết nối khỏi bị nghe lén hoặc sửa đổi trên đường truyền. SRI xác minh nội dung tài nguyên khớp với digest đã được trang khai báo.

| Cơ chế | Điều được bảo vệ |
|---|---|
| HTTPS/TLS | Kết nối tới server, tính bí mật và toàn vẹn của dữ liệu truyền |
| SRI | Nội dung chính xác của resource có integrity metadata |
| CORS | Quyền chia sẻ response cross-origin với script/requestor |
| CSP | Nguồn và loại tài nguyên được phép tải/thực thi |
| Dependency lockfile | Phiên bản dependency được chọn trong quá trình cài/build |

SRI nên được phân phối qua một trang HTTPS đáng tin cậy. Nếu HTML và hash được gửi qua HTTP, attacker trên đường truyền có thể thay cả resource lẫn hash, làm mất ý nghĩa kiểm tra.

## 2. Integrity metadata và thuật toán hash

### 2.1 Cấu trúc của một digest

Giá trị integrity có dạng:

~~~text
<algorithm>-<base64-digest>
~~~

Ví dụ cấu trúc:

~~~html
<script
  src="https://cdn.example.net/library.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

Các thuật toán SRI hiện được chuẩn hóa:

| Thuật toán | Độ dài digest | Ghi chú |
|---|---:|---|
| SHA-256 | 256 bit | Hợp lệ, nhưng yếu hơn hai lựa chọn còn lại |
| SHA-384 | 384 bit | Lựa chọn baseline thực tế tốt |
| SHA-512 | 512 bit | Mạnh hơn SHA-384, digest dài hơn |

Không dùng MD5 hoặc SHA-1 cho SRI. Các thuật toán này không còn phù hợp cho mục đích kiểm tra toàn vẹn mật mã.

### 2.2 Browser chọn thuật toán mạnh nhất có trong metadata

Một thuộc tính có thể chứa nhiều hash, phân tách bằng khoảng trắng:

~~~html
<script
  src="https://cdn.example.net/library.js"
  integrity="
    sha256-SHA256_DIGEST
    sha384-SHA384_DIGEST
    sha512-SHA512_DIGEST"
  crossorigin="anonymous"></script>
~~~

Browser chọn nhóm hash dùng thuật toán mạnh nhất mà nó hỗ trợ trong metadata. Theo thứ tự hiện tại:

~~~text
SHA-256 < SHA-384 < SHA-512
~~~

Nếu có SHA-512, browser hiện đại sẽ kiểm tra các digest SHA-512 và bỏ qua các digest SHA-256/SHA-384 trong cùng metadata. Vì vậy, không thể trông chờ browser tự fallback xuống SHA-384 khi SHA-512 có mặt nhưng không khớp.

Có thể cung cấp nhiều digest cùng thuật toán mạnh nhất để chấp nhận một trong vài payload đã được duyệt, ví dụ khi CDN có hai bản nội dung hợp lệ trong giai đoạn rollout. Browser chấp nhận nếu nội dung khớp ít nhất một digest thuộc nhóm thuật toán mạnh nhất.

### 2.3 Hash là dấu vân tay của bytes, không phải của tên file

Hai URL giống nhau có thể trả nội dung khác nhau theo thời gian. Ngược lại, hai URL khác nhau có thể trả cùng nội dung và cùng digest.

SRI không xác minh:

- Tên package hoặc tên file có đúng không.
- Phiên bản được đặt trong URL có đáng tin không.
- Mã nguồn có chất lượng hay không.
- Tác giả package có ý đồ tốt hay không.
- Dependency có lỗ hổng logic hay không.

Nó chỉ xác minh nội dung nhận được có khớp với digest mà ứng dụng đã khai báo hay không.

### 2.4 Tại sao nên ưu tiên SHA-384?

SHA-384 được hỗ trợ rộng rãi và có độ mạnh phù hợp cho SRI. SHA-512 cũng là lựa chọn hợp lệ. Hãy thống nhất thuật toán trong build pipeline để hash được sinh lặp lại và dễ review.

Nếu khai báo nhiều thuật toán để hỗ trợ browser cũ, hãy hiểu quy tắc chọn thuật toán mạnh nhất. Không thêm digest giả hoặc digest của một file khác vào cùng thuộc tính.

## 3. Dùng SRI với script và stylesheet

### 3.1 Script từ CDN

Ví dụ:

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="anonymous"
  defer></script>
~~~

Các phần quan trọng:

- **src:** URL của tài nguyên.
- **integrity:** hash của nội dung phiên bản được chấp nhận.
- **crossorigin="anonymous":** yêu cầu cross-origin fetch theo CORS mà không gửi credential cross-origin.
- **defer:** điều khiển thời điểm thực thi script; không phải thành phần của SRI.

Không sao chép chuỗi placeholder vào production. Hãy tạo digest từ chính file phát hành.

### 3.2 Stylesheet từ CDN

SRI cũng áp dụng cho stylesheet:

~~~html
<link
  rel="stylesheet"
  href="https://cdn.example.net/theme-4.2.1.min.css"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="anonymous">
~~~

Browser chỉ áp dụng stylesheet khi nội dung khớp. Nếu CDN đổi khoảng trắng, minify lại, đổi comment hoặc thay một rule CSS, digest có thể khác và stylesheet bị từ chối.

### 3.3 Preload và modulepreload

Các phần tử link với rel="preload" hoặc rel="modulepreload" cũng có thể mang integrity metadata:

~~~html
<link
  rel="preload"
  href="/assets/app.js"
  as="script"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="anonymous">

<link
  rel="modulepreload"
  href="/assets/feature.js"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="anonymous">
~~~

Khi preload và phần tử sử dụng resource cùng tồn tại, hãy bảo đảm URL, request mode, credentials mode và integrity metadata nhất quán để browser có thể tái sử dụng request/cache đúng cách.

### 3.4 Tài nguyên cùng origin

Với resource cùng origin:

~~~html
<script
  src="/assets/app.8f31c.js"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  defer></script>
~~~

Request same-origin không cần CORS để SRI hoạt động. Thuộc tính crossorigin thường chỉ cần thiết khi resource được tải cross-origin; với module script, cơ chế tải module vốn sử dụng CORS.

### 3.5 Không gắn SRI cho URL nội dung thay đổi liên tục

Một URL như:

~~~text
https://api.example.net/user/profile
~~~

thường trả dữ liệu thay đổi theo người dùng hoặc thời gian. Không phù hợp để dùng một digest cố định trong HTML. SRI hướng đến resource tĩnh, phiên bản hóa và có nội dung xác định như thư viện JavaScript hoặc stylesheet.

Nếu muốn xác minh một response fetch cụ thể, có thể dùng Fetch API integrity option; phần sau sẽ trình bày.

## 4. SRI và CORS với tài nguyên cross-origin

### 4.1 Vì sao cần CORS?

Khi dùng SRI cho tài nguyên cross-origin, browser bắt buộc sử dụng CORS. Nếu chỉ tải resource ở chế độ no-cors, attacker có thể thử nhiều digest và quan sát sự kiện load/error để suy đoán nội dung của một response cross-origin mà SOP không cho đọc.

Do đó, SRI cross-origin cần resource provider xác nhận việc chia sẻ nội dung bằng response header CORS phù hợp.

Ví dụ CDN cho phép mọi origin tải resource công khai:

~~~http
Access-Control-Allow-Origin: *
~~~

### 4.2 crossorigin="anonymous"

Ví dụ đầy đủ:

~~~html
<script
  src="https://cdn.example.net/library.js"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="anonymous"></script>
~~~

Thuộc tính crossorigin chuyển request sang CORS mode. Với giá trị anonymous, browser không gửi credential cross-origin. CDN có thể trả:

~~~http
Access-Control-Allow-Origin: *
Content-Type: text/javascript
~~~

Nếu tài nguyên chỉ cho phép một website cụ thể, server có thể trả origin cụ thể thay cho wildcard và thêm Vary: Origin khi response thay đổi theo Origin request header.

### 4.3 crossorigin="use-credentials"

Nếu tài nguyên thực sự cần cookie hoặc credential cross-origin:

~~~html
<script
  src="https://private-cdn.example.net/app.js"
  integrity="sha384-REPLACE_WITH_REAL_DIGEST"
  crossorigin="use-credentials"></script>
~~~

Server phải trả origin cụ thể và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng Access-Control-Allow-Origin: * cùng credentialed CORS. Với thư viện JavaScript public, ưu tiên anonymous để không phụ thuộc cookie của người dùng.

### 4.4 CORS đúng nhưng SRI sai vẫn bị chặn

CORS và SRI là hai bước kiểm tra khác nhau:

1. CORS xác định request cross-origin có được chia sẻ response theo quy tắc hay không.
2. SRI so sánh bytes của response với digest đã khai báo.

Một resource có CORS hợp lệ nhưng hash sai vẫn bị từ chối. Ngược lại, digest đúng nhưng CORS thất bại thì browser cũng không thể hoàn tất integrity-protected cross-origin request.

### 4.5 Kiểm tra response CORS của CDN

Khi gặp lỗi SRI với CDN, kiểm tra:

- Request có thuộc CORS mode không?
- Markup có crossorigin phù hợp không?
- Response có Access-Control-Allow-Origin không?
- Origin cụ thể có khớp chính xác scheme/host/port không?
- Nếu dùng credential, response có Access-Control-Allow-Credentials: true không?
- Redirect có đưa request qua origin khác không?
- CDN có trả nội dung khác nhau theo header, cookie hoặc user agent không?

Không dùng no-cors để né lỗi CORS. SRI cross-origin cần CORS để bảo vệ cả tính toàn vẹn và tính riêng tư.

## 5. Tạo SRI hash chính xác

### 5.1 Tính hash bằng OpenSSL

Với file JavaScript cuối cùng:

~~~bash
openssl dgst -sha384 -binary library.min.js | openssl base64 -A
~~~

Kết quả là Base64 digest. Ghép tiền tố:

~~~text
sha384-<BASE64_OUTPUT>
~~~

Sau đó đưa chuỗi hoàn chỉnh vào thuộc tính integrity.

Không hash URL, tên file hoặc nội dung source trước build. Hãy hash đúng file mà browser sẽ nhận được.

### 5.2 Tính hash bằng Node.js

Tạo file sri-hash.mjs:

~~~js
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);

if (files.length === 0) {
  console.error('Usage: node sri-hash.mjs <file> [file...]');
  process.exit(1);
}

for (const file of files) {
  const bytes = readFileSync(file);
  const digest = createHash('sha384')
    .update(bytes)
    .digest('base64');

  console.log(file + ': sha384-' + digest);
}
~~~

Chạy:

~~~bash
node sri-hash.mjs dist/vendor.min.js dist/vendor.min.css
~~~

Node đọc bytes trực tiếp từ file và tính SHA-384. Đây là cách phù hợp để đưa vào build script hoặc CI pipeline.

### 5.3 Tính hash sau bước build cuối cùng

Pipeline thường gồm:

~~~text
Source code
   |
   v
Dependency install (lockfile)
   |
   v
Build / bundle / minify
   |
   v
Post-process / optimize
   |
   v
Final artifact
   |
   v
Generate SRI digest
   |
   v
Write digest into HTML / manifest
   |
   v
Deploy immutable asset + document
~~~

Nếu tạo hash trước bước minify, nén nội dung ở cấp ứng dụng hoặc post-process, digest sẽ không khớp file cuối cùng. Tính hash sau bước cuối cùng làm thay đổi nội dung.

### 5.4 Những thay đổi nhỏ cũng làm hash thay đổi

Digest sẽ khác nếu bytes thay đổi, kể cả khi JavaScript/CSS vẫn có hành vi tương đương:

- Minifier đổi cách đặt dấu cách hoặc xuống dòng.
- Build tool thêm banner hoặc source marker.
- Comment bị thêm/xóa.
- Thứ tự property CSS thay đổi.
- CDN rewrite URL hoặc tối ưu CSS.
- Phiên bản thư viện được nâng cấp.
- Encoding hoặc newline trong artifact thay đổi.

Vì vậy, không lấy hash từ một bản file “tương tự”. Hãy lấy đúng artifact phát hành.

### 5.5 CDN và proxy không nên biến đổi resource đã pin

Nếu CDN hoặc proxy tự minify, rewrite hoặc chèn nội dung vào file sau khi digest được tạo, browser sẽ từ chối resource.

Có hai cách quản lý:

- Phục vụ đúng artifact canonical đã được hash, tắt biến đổi nội dung tự động.
- Nếu nội dung thực sự thay đổi, tạo digest mới và cập nhật metadata cùng bản phát hành.

Có thể dùng Cache-Control: no-transform trên response resource để thông báo cho intermediary rằng không nên biến đổi representation. Đây là một tín hiệu cho proxy; vẫn cần kiểm tra cấu hình CDN thực tế.

## 6. Quản lý phiên bản và dependency

### 6.1 Pin URL và hash cùng nhau

Một tích hợp tốt dùng URL phiên bản cố định:

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-REAL_DIGEST_FOR_4_2_1"
  crossorigin="anonymous"></script>
~~~

Khi nâng lên 4.2.2, thay URL và digest trong cùng một thay đổi đã review. Tránh URL không phiên bản có nội dung thay đổi tùy thời điểm, ví dụ latest.js, nếu nhà cung cấp không cam kết nội dung bất biến.

### 6.2 SRI và lockfile không thay thế nhau

| Công cụ | Giai đoạn | Vai trò |
|---|---|---|
| package-lock.json / pnpm-lock.yaml / yarn.lock | Cài dependency và build | Ghi lại phiên bản/package resolution |
| SRI | Browser tải resource | Kiểm tra bytes của resource được nhúng |
| HTTPS | Truyền tải | Bảo vệ kết nối và xác thực server |
| CSP | Browser tải/thực thi | Giới hạn nguồn và loại resource |

Lockfile không tự tạo thuộc tính integrity cho script CDN trong HTML. SRI cũng không thay thế lockfile trong quá trình build package.

### 6.3 Review thay đổi digest như thay đổi dependency

Khi hash đổi, hãy hỏi:

- URL/version có thay đổi không?
- Artifact có được lấy từ nguồn chính thức không?
- Diff source hoặc release notes nói gì?
- Build có thay đổi do toolchain hay không?
- CDN có biến đổi nội dung không?
- Có phải thay đổi hash được review cùng code không?

Không tự động chấp nhận hash mới chỉ vì CI báo hash cũ không khớp. Hash mismatch có thể là lỗi build hợp lệ, nhưng cũng có thể là dấu hiệu nội dung đã bị thay đổi ngoài dự kiến.

### 6.4 Fallback resource phải được pin độc lập

Nếu CDN không tải được hoặc hash mismatch, ứng dụng có thể chọn một fallback đã được duyệt từ origin của mình. Fallback cũng cần version pinning và integrity metadata phù hợp. Không fallback sang một URL bất kỳ hoặc bỏ integrity để “làm cho trang chạy”.

## 7. SRI với Fetch API

### 7.1 integrity option của fetch()

Fetch API hỗ trợ thuộc tính integrity trong RequestInit:

~~~js
const response = await fetch('/assets/catalog.json', {
  integrity: 'sha384-REPLACE_WITH_REAL_DIGEST',
  cache: 'no-cache'
});

if (!response.ok) {
  throw new Error('HTTP status: ' + response.status);
}

const catalog = await response.json();
~~~

Browser tính hash của resource khi fetch và từ chối request bằng network error nếu digest không khớp. Giá trị integrity có cùng định dạng algorithm-prefix và Base64 digest.

### 7.2 Fetch cross-origin vẫn cần CORS

Ví dụ:

~~~js
const response = await fetch('https://api.example.net/public-config.json', {
  mode: 'cors',
  credentials: 'omit',
  integrity: 'sha384-REPLACE_WITH_REAL_DIGEST'
});
~~~

Server API cần cho phép CORS. SRI không bỏ qua CORS và không làm response no-cors trở nên đọc được.

Fetch integrity phù hợp với response có nội dung cố định, ví dụ một manifest public hoặc file cấu hình phiên bản hóa. Không phù hợp với JSON cá nhân hóa theo session vì mỗi người dùng có thể nhận bytes khác nhau.

### 7.3 Integrity không phải chữ ký số cho dữ liệu động

Nếu API trả dữ liệu thay đổi, digest phải được tin cậy từ một kênh độc lập mới có ý nghĩa. Không thể lấy hash của response từ chính response đó rồi xem như đã xác minh nguồn gốc.

SRI thường được dùng với digest nằm trong HTML hoặc build artifact đã được phát hành qua kênh tin cậy.

## 8. Giới hạn bảo vệ của SRI

### 8.1 Không bảo vệ HTML document chứa hash

Nếu attacker kiểm soát HTML document hoặc pipeline phát hành, họ có thể thay cả URL, integrity metadata và script. SRI bảo vệ resource so với metadata mà browser nhận, không xác minh nguồn gốc của metadata.

Vì vậy, cần bảo vệ origin ứng dụng, TLS, quyền deploy, CI/CD và quy trình review.

### 8.2 Không tự kiểm tra mọi dependency bắc cầu

Một script đã qua SRI có thể tải thêm script khác bằng cách tạo phần tử script động. Hash của script ban đầu không tự động kiểm tra nội dung của mọi script được tải sau đó.

Tương tự, integrity metadata trên entry module không nên được hiểu là hash đệ quy cho toàn bộ module graph. Mỗi resource dependency cần có cơ chế integrity phù hợp hoặc được kiểm soát bằng build/deployment strategy. Với modulepreload, có thể khai báo integrity cho resource module được preload.

### 8.3 Không thay thế CSP

SRI xác minh bytes của một resource cụ thể. CSP giới hạn những nguồn và loại script được phép chạy.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.net; object-src 'none'; base-uri 'self'
~~~

CSP cho phép script từ CDN nhưng không bảo đảm CDN trả đúng phiên bản. SRI pin nội dung script. Dùng cả hai khi phù hợp:

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-REAL_DIGEST"
  crossorigin="anonymous"></script>
~~~

### 8.4 Không thay thế HTTPS

Nếu trang được phân phối qua HTTP, attacker trên đường truyền có thể thay đổi HTML và integrity metadata. Hãy chỉ phát hành SRI từ secure context và luôn dùng HTTPS cho document lẫn resource.

### 8.5 Không đảm bảo code là vô hại

Một file có digest hợp lệ có thể chứa lỗ hổng, hành vi xấu hoặc dependency có vấn đề ngay từ lúc phát hành. SRI chỉ chứng minh bytes đúng như metadata, không phải chứng nhận chất lượng hay độ an toàn của mã.

### 8.6 Có thể gây mất availability

Khi CDN cập nhật nội dung mà URL vẫn giữ nguyên, digest cũ không còn khớp. Browser từ chối tải resource. Đây là hành vi bảo vệ đúng, nhưng có thể làm giao diện mất chức năng.

Dùng URL phiên bản hóa, immutable cache, quy trình release có cập nhật hash và giám sát lỗi tải resource.

### 8.7 Phạm vi phần tử được hỗ trợ

SRI metadata trên HTML hiện được hỗ trợ cho:

- Phần tử script.
- Phần tử link dùng rel stylesheet.
- Phần tử link dùng rel preload.
- Phần tử link dùng rel modulepreload.

Không mặc định rằng có thể gắn integrity vào mọi loại tài nguyên HTML như img, iframe, video hoặc audio. Với request Fetch API, dùng RequestInit.integrity nếu phù hợp và browser hỗ trợ.

## 9. Integrity-Policy và Report-Only

### 9.1 Từ khai báo từng resource tới policy bắt buộc

SRI truyền thống yêu cầu developer tự thêm integrity cho từng script/link. Một trang lớn có thể bỏ sót một script mới được thêm vào, đặc biệt khi script do tag manager hoặc thư viện khác tải.

Các header **Integrity-Policy** và **Integrity-Policy-Report-Only** được định nghĩa trong SRI-2, hiện là W3C Working Draft công bố ngày 20-03-2026 và chưa phải Recommendation cuối cùng. Chúng cho phép document đặt yêu cầu ở cấp policy đối với các destination như script và style:

- Integrity-Policy có thể chặn request thuộc destination được chọn nếu request không có integrity metadata hoặc không dùng CORS/same-origin mode phù hợp.
- Integrity-Policy-Report-Only ghi nhận vi phạm nhưng không chặn request chỉ vì policy thử nghiệm.
- Reporting endpoint có thể nhận báo cáo vi phạm qua Reporting API.

Đây là tính năng mới và mức hỗ trợ có thể khác nhau giữa browser/phiên bản. Hãy kiểm tra compatibility của browser mục tiêu và dùng Report-Only trước khi bật enforcement.

### 9.2 Khai báo Reporting-Endpoints

Ví dụ đặt endpoint:

~~~http
Reporting-Endpoints: sri="https://app.example.com/reports/integrity"
~~~

### 9.3 Bật Report-Only

~~~http
Integrity-Policy-Report-Only: blocked-destinations=(script style), endpoints=(sri)
~~~

Browser hỗ trợ có thể báo các script/style request không đáp ứng integrity policy. Endpoint cần được cấu hình và giám sát; report là dữ liệu do client gửi nên phải giới hạn kích thước, tần suất và tránh render dữ liệu thô bằng HTML.

### 9.4 Chuyển sang enforcement

Sau khi đã xử lý các violation hợp lệ:

~~~http
Integrity-Policy: blocked-destinations=(script style), endpoints=(sri)
~~~

Policy này hỗ trợ yêu cầu script/style có integrity metadata và request mode phù hợp. Nó không tạo digest thay developer và không tự xác minh rằng hash được chọn là hash tốt. Browser vẫn dùng SRI metadata của request để xác minh bytes.

Không triển khai header mới trên toàn bộ traffic nếu chưa xác nhận browser support và hành vi fallback. Giữ đường tương thích cho browser không hỗ trợ policy header.

### 9.5 Quan sát report trong JavaScript

Trong browser hỗ trợ ReportingObserver:

~~~js
if ('ReportingObserver' in window) {
  const observer = new ReportingObserver((reports) => {
    for (const report of reports) {
      if (report.type === 'integrity-violation') {
        console.log('Integrity violation:', report.body);
      }
    }
  }, {
    types: ['integrity-violation'],
    buffered: true
  });

  observer.observe();
}
~~~

ReportingObserver là công cụ quan sát bổ sung. Báo cáo gửi về endpoint vẫn cần được xử lý ở server; không phụ thuộc hoàn toàn vào JavaScript observer để giám sát production.

## 10. Quy trình triển khai SRI trong dự án

### 10.1 Kiểm kê tài nguyên bên ngoài

Tìm các resource:

- Script từ CDN.
- Stylesheet từ CDN.
- Preload/modulepreload bên ngoài.
- Script analytics, tag manager hoặc SDK.
- Resource được tạo động trong runtime.
- Dependency được nhúng qua template hoặc CMS.

Phân loại theo chủ sở hữu, URL, phiên bản, request mode, nhu cầu credential và khả năng hỗ trợ CORS.

### 10.2 Chọn resource phù hợp

Ưu tiên SRI cho file:

- Có phiên bản cố định.
- Nội dung ổn định giữa người dùng.
- Có thể tạo digest trong build/release pipeline.
- Có server hỗ trợ CORS nếu cross-origin.
- Không bị CDN biến đổi sau khi digest được tạo.

Không cố pin file có nội dung thay đổi theo người dùng hoặc response cá nhân hóa.

### 10.3 Sinh hash trong build/CI

Sau bước build cuối:

1. Tính SHA-384 cho artifact.
2. Ghi digest vào HTML/manifest.
3. Kiểm tra URL và hash thuộc cùng phiên bản.
4. Kiểm tra CDN CORS response.
5. Kiểm tra file không bị transform sau bước hash.
6. Review thay đổi dependency và digest.
7. Deploy asset và HTML nhất quán.

### 10.4 Kiểm thử trước khi phát hành

Kiểm tra các trường hợp:

- Hash đúng: script/style tải thành công.
- Hash sai một ký tự: browser từ chối.
- Resource bytes bị thay đổi: browser từ chối.
- CORS header bị thiếu ở cross-origin: browser từ chối.
- CDN redirect sang host khác: CORS và SRI vẫn phải hợp lệ trên response cuối.
- Browser không hỗ trợ Integrity-Policy: các thuộc tính SRI riêng lẻ vẫn được xử lý theo support SRI thông thường.

### 10.5 Giám sát sau phát hành

Theo dõi:

- Console integrity check failed.
- CORS errors.
- Script/style resource load error.
- CDN deploy hoặc cache purge.
- Digest mismatch theo browser và phiên bản.
- Integrity-Policy report nếu triển khai.
- Dependency update và thay đổi build pipeline.

Không tự động bỏ integrity khi có lỗi. Xác định resource thực tế, so sánh artifact và digest, kiểm tra CORS/redirect rồi mới phát hành hash mới.

## 11. Thực hành: tạo hash và kiểm tra script CDN bằng Node.js

Lab tạo hai origin theo port: trang HTML ở localhost:3000 và resource server ở localhost:3001. Khác port nghĩa là khác origin. Resource server gửi CORS header để browser có thể xác minh SRI cross-origin.

Lab dùng HTTP localhost để đơn giản hóa chạy thử. Trong production, hãy phân phối HTML và resource qua HTTPS; SRI metadata cần được bảo vệ bằng secure context.

### 11.1 Tạo cấu trúc thư mục

~~~text
sri-lab/
  server.mjs
  sri-hash.mjs
  public/
    index.html
    app.js
    theme.css
~~~

File public/app.js:

~~~js
document.querySelector('#status').textContent =
  'Script đã qua kiểm tra Subresource Integrity.';
~~~

File public/theme.css (dùng ở phần thử stylesheet):

~~~css
body {
  font-family: sans-serif;
  background: #f4f6f8;
}
~~~

### 11.2 Tạo trang public/index.html

Thay placeholder bằng digest được tạo ở bước kế tiếp:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>SRI lab</title>
</head>
<body>
  <h1>Subresource Integrity lab</h1>
  <p id="status">Script chưa chạy.</p>

  <script
    src="http://localhost:3001/app.js"
    integrity="sha384-REPLACE_WITH_REAL_DIGEST"
    crossorigin="anonymous"
    defer></script>
</body>
</html>
~~~

### 11.3 Tạo sri-hash.mjs

~~~js
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const file = process.argv[2] || './public/app.js';
const bytes = readFileSync(file);
const digest = createHash('sha384')
  .update(bytes)
  .digest('base64');

console.log('sha384-' + digest);
~~~

Chạy từ thư mục sri-lab:

~~~bash
node sri-hash.mjs public/app.js
~~~

Copy toàn bộ kết quả vào thuộc tính integrity trong index.html. Không thêm dấu nháy hoặc ký tự khác vào digest.

### 11.4 Tạo server.mjs

~~~js
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';

const page = createServer((req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });

  res.end(readFileSync('./public/index.html'));
});

const resource = createServer((req, res) => {
  const files = {
    '/app.js': {
      type: 'text/javascript; charset=utf-8',
      path: './public/app.js'
    },
    '/theme.css': {
      type: 'text/css; charset=utf-8',
      path: './public/theme.css'
    }
  };
  const file = files[req.url];

  if (!file) {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': file.type,
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': 'no-store'
  });

  res.end(readFileSync(file.path));
});

page.listen(3000, 'localhost', () => {
  console.log('Page:     http://localhost:3000');
});

resource.listen(3001, 'localhost', () => {
  console.log('Resources: http://localhost:3001/app.js and /theme.css');
});
~~~

### 11.5 Chạy lab

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Kết quả mong đợi: dòng trạng thái đổi thành “Script đã qua kiểm tra Subresource Integrity.”.

Trong DevTools → Network, kiểm tra:

- Document tải từ port 3000.
- Script tải từ port 3001.
- Request script dùng CORS vì có crossorigin="anonymous".
- Response script có Access-Control-Allow-Origin: *.
- Console không báo integrity mismatch.

### 11.6 Thử thay đổi nội dung

Giữ nguyên hash trong index.html, sửa public/app.js:

~~~js
document.querySelector('#status').textContent =
  'Nội dung đã bị thay đổi sau khi hash được tạo.';
~~~

Reload trang. Browser phải từ chối script và dòng trạng thái vẫn là “Script chưa chạy.”. Console hiển thị lỗi integrity check.

Khôi phục app.js về nội dung ban đầu hoặc chạy lại sri-hash.mjs và cập nhật digest. Khi digest mới khớp bytes mới, script có thể chạy trở lại.

### 11.7 Thử bỏ CORS header

Trong server.mjs, tạm xóa:

~~~http
Access-Control-Allow-Origin: *
~~~

Reload trang. Dù digest đúng, request cross-origin không hoàn thành CORS check nên SRI không thể được sử dụng. Khôi phục header sau thử nghiệm.

### 11.8 Thử stylesheet

Tạo stylesheet public/theme.css, tính hash bằng cách truyền file đó vào sri-hash.mjs, rồi thêm:

~~~html
<link
  rel="stylesheet"
  href="http://localhost:3001/theme.css"
  integrity="sha384-REPLACE_WITH_CSS_DIGEST"
  crossorigin="anonymous">
~~~

Resource server cần trả Content-Type: text/css và Access-Control-Allow-Origin phù hợp. Sửa một rule CSS sau khi hash đã tạo rồi reload để quan sát stylesheet bị từ chối.

Sau lab, dừng hai server.

## 12. Chẩn đoán lỗi SRI

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Console báo Failed to find a valid digest | Hash không khớp bytes được tải | Tạo lại hash từ artifact cuối cùng và xác minh URL/version |
| Script CDN bị chặn dù hash đúng | Thiếu crossorigin hoặc CORS response không hợp lệ | Dùng CORS mode và kiểm tra Access-Control-Allow-Origin |
| Stylesheet không áp dụng | Digest sai hoặc request CORS thất bại | Kiểm tra hash, response header và redirect |
| Hash chỉ sai trên production | CDN/proxy minify hoặc rewrite file | Tắt transform hoặc tạo hash từ canonical production artifact |
| Resource đổi sau mỗi lần deploy | URL không phiên bản hoặc nội dung CDN mutable | Pin URL/version và cập nhật hash theo release |
| Thêm SHA-512 nhưng browser vẫn báo mismatch | Digest SHA-512 sai; browser chọn thuật toán mạnh nhất | Tính đúng SHA-512 hoặc bỏ digest sai, không trông chờ fallback |
| Resource cross-origin không tải với no-cors | SRI cross-origin yêu cầu CORS | Thêm crossorigin và cấu hình CORS tại resource server |
| Script chính qua SRI nhưng script phụ bị thay | SRI không đệ quy qua dependency được tải động | Pin/kiểm soát từng dependency và dùng CSP |
| Module entry qua SRI nhưng import bị thay | Integrity entry không tự pin toàn bộ module graph | Kiểm soát module dependencies, dùng modulepreload integrity khi phù hợp |
| API fetch integrity thất bại | Response bytes thay đổi hoặc digest lấy sai artifact | Tính digest đúng response representation và kiểm tra CORS |
| Integrity-Policy chặn script mới | Script thiếu integrity hoặc request không dùng CORS/same-origin mode | Thêm metadata, sửa CORS hoặc điều chỉnh rollout policy |
| Report-Only có violation nhưng script vẫn chạy | Đây là hành vi dự kiến | Xử lý report rồi chuyển enforcement khi đã sẵn sàng |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** SRI xác minh điều gì?

**Đáp án:** Browser tính hash của nội dung resource nhận được và so sánh với digest mà document khai báo. Nếu không khớp, browser từ chối thực thi script hoặc áp dụng stylesheet.

**Câu 2.** Những thuật toán nào được dùng trong SRI?

**Đáp án:** SHA-256, SHA-384 và SHA-512. SHA-384 là baseline thực tế tốt; không dùng MD5 hoặc SHA-1.

**Câu 3.** Vì sao SRI cross-origin cần CORS?

**Đáp án:** CORS bảo đảm resource provider chủ động chia sẻ response với origin yêu cầu. Nếu không, attacker có thể dùng thành công/thất bại của hash để suy đoán nội dung cross-origin.

**Câu 4.** crossorigin="anonymous" có ý nghĩa gì?

**Đáp án:** Nó yêu cầu CORS mode và không gửi credential cross-origin. Server resource vẫn cần Access-Control-Allow-Origin phù hợp.

**Câu 5.** Browser xử lý nhiều hash khác thuật toán thế nào?

**Đáp án:** Browser chọn nhóm digest của thuật toán mạnh nhất mà nó hỗ trợ trong metadata. Trong nhóm đó, chỉ cần một digest khớp.

**Câu 6.** Nếu CDN thay đổi một dấu cách trong file CSS, SRI có thể thất bại không?

**Đáp án:** Có. Digest được tính trên bytes; thay đổi nội dung dù không đổi ý nghĩa CSS vẫn làm hash khác.

**Câu 7.** SRI có bảo vệ mọi script được thư viện chính tải động không?

**Đáp án:** Không. Hash của resource chính không tự động kiểm tra dependency bắc cầu. Cần kiểm soát từng resource hoặc build/deployment graph.

**Câu 8.** SRI có thay thế CSP không?

**Đáp án:** Không. SRI pin bytes của resource; CSP giới hạn nguồn và loại tài nguyên được phép tải/thực thi. Hai cơ chế bổ sung nhau.

**Câu 9.** Fetch API có thể dùng SRI không?

**Đáp án:** Có. RequestInit.integrity cho phép browser xác minh response của fetch bằng digest. Request cross-origin vẫn phải đáp ứng CORS.

**Câu 10.** Integrity-Policy khác thuộc tính integrity thế nào?

**Đáp án:** Thuộc tính integrity pin nội dung của từng resource. Integrity-Policy đặt yêu cầu ở cấp document để chặn hoặc báo cáo các script/style request thiếu integrity metadata hoặc không dùng request mode phù hợp; cần kiểm tra browser support.

## 14. Checklist triển khai Subresource Integrity

Trước khi phát hành resource có SRI, hãy kiểm tra:

1. **Resource inventory:** xác định script, stylesheet, preload và modulepreload từ bên ngoài.
2. **Version pinning:** dùng URL/version ổn định; tránh endpoint trả nội dung thay đổi bất ngờ.
3. **Digest:** ưu tiên SHA-384 hoặc SHA-512; không dùng MD5/SHA-1.
4. **Build timing:** tính hash sau build, minify và mọi bước biến đổi nội dung.
5. **Exact artifact:** digest phải thuộc đúng file browser nhận được.
6. **CORS:** resource cross-origin có crossorigin phù hợp và ACAO đúng.
7. **Credentials:** ưu tiên anonymous; nếu dùng use-credentials, cần origin cụ thể và ACAC true.
8. **CDN transform:** tắt rewrite/minify không kiểm soát hoặc cập nhật hash sau transform.
9. **Dependency graph:** đánh giá script tải động, module imports và dependency bắc cầu.
10. **CSP:** kết hợp script-src/style-src hẹp với SRI.
11. **HTTPS:** phân phối document và resource qua HTTPS; bảo vệ integrity metadata trong HTML.
12. **Release review:** review URL, version và hash như một thay đổi dependency.
13. **Report-only:** dùng Integrity-Policy-Report-Only nếu browser mục tiêu hỗ trợ.
14. **Enforcement:** chỉ bật Integrity-Policy sau khi xử lý violation và kiểm tra tương thích.
15. **Monitoring:** theo dõi hash mismatch, CORS failure và resource load error.
16. **Recovery:** fallback chỉ tới resource đã được duyệt và pin độc lập.

**Ghi nhớ:** SRI biến nội dung mong đợi của một script hoặc stylesheet thành digest mà browser có thể kiểm tra. Hãy tạo hash từ artifact cuối cùng, dùng CORS cho tài nguyên cross-origin, pin URL theo phiên bản và review mọi thay đổi digest. Kết hợp SRI với HTTPS, CSP, lockfile và quy trình phát hành để giảm rủi ro supply-chain attack.

## Tài liệu tham khảo

- [W3C — Subresource Integrity](https://www.w3.org/TR/sri/)
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Subresource_Integrity)
- [MDN — integrity HTML attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/integrity)
- [MDN — crossorigin attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/crossorigin)
- [MDN — RequestInit.integrity](https://developer.mozilla.org/en-US/docs/Web/API/RequestInit)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [OWASP — Third Party JavaScript Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html)

