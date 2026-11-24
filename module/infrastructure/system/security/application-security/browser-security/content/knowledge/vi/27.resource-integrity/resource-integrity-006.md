# Dependency resource

**Dependency resource** là tài nguyên mà một trang web cần tải từ một thành phần hoặc nhà cung cấp khác để hoạt động, ví dụ JavaScript library, stylesheet, font, widget hoặc module được phân phối qua CDN. Những tài nguyên này mở rộng chức năng và giúp ứng dụng tái sử dụng mã, nhưng cũng tạo thêm một ranh giới tin cậy: browser đang nhận mã hoặc nội dung từ một nguồn nằm ngoài ứng dụng.

Nếu một dependency bị thay đổi, bị thay thế hoặc bị phân phối nhầm phiên bản, trang web có thể nhận nội dung khác với nội dung mà nhóm phát triển đã kiểm tra. Với JavaScript, mã bên thứ ba thường chạy trong origin của trang nhúng và có thể truy cập DOM, dữ liệu hiển thị và các API mà trang được phép dùng. Vì vậy, quản lý dependency resource là một phần của bảo mật chuỗi cung ứng phần mềm.

Một cách bảo vệ tài nguyên tĩnh từ bên ngoài là **Subresource Integrity (SRI)**. Ứng dụng khai báo hash mong đợi trong thuộc tính integrity; browser tính hash từ nội dung tải về và chỉ sử dụng tài nguyên khi bytes nhận được khớp hash. Với tài nguyên cross-origin, SRI cần request CORS phù hợp, thường dùng thêm thuộc tính crossorigin="anonymous".

Bài học thuộc chương **Resource integrity** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào nguồn dependency, tính toàn vẹn tài nguyên, SRI, CORS, CSP, quản lý phiên bản và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện dependency resource trong ứng dụng web và giải thích vì sao mỗi nguồn ngoài là một phần của ranh giới tin cậy.
2. Phân biệt dependency được đóng gói cùng ứng dụng với dependency tải trực tiếp từ CDN.
3. Giải thích rủi ro khi CDN, package, tài khoản publish hoặc pipeline build bị xâm phạm.
4. Dùng SRI để xác minh bytes của script hoặc stylesheet external.
5. Hiểu vai trò của hash, thuộc tính integrity và crossorigin.
6. Phân biệt SRI với TLS, CORS, CSP và lockfile của package manager.
7. Quản lý phiên bản, cập nhật dependency và thay đổi hash có kiểm soát.
8. Nhận diện giới hạn của SRI với dynamic script, nội dung inline và dependency thay đổi thường xuyên.
9. Dùng Node.js lab hai origin để quan sát tài nguyên đúng hash được chạy, tài nguyên sai hash bị chặn và lỗi CORS.

## 2. Dependency resource trong browser là gì?

Một ứng dụng web có thể phụ thuộc vào nhiều tài nguyên không nằm trong mã nguồn chính:

| Loại dependency | Ví dụ | Vai trò |
| --- | --- | --- |
| JavaScript library | Framework, charting, date picker, analytics | Thêm chức năng chạy trong trang |
| Stylesheet | CSS framework, icon font stylesheet | Định dạng giao diện |
| Font | Web font từ nhà cung cấp ngoài | Hiển thị typography |
| Widget/iframe | Video, bản đồ, chat, payment widget | Nhúng một trải nghiệm từ dịch vụ khác |
| WebAssembly/module | Module tính toán hoặc codec | Cung cấp khả năng chạy mã bổ sung |
| Runtime config/data | File JSON cấu hình hoặc manifest | Điều khiển tính năng và endpoint |

Không phải tất cả loại tài nguyên đều được SRI bảo vệ theo cùng cách. SRI thường được áp dụng trực tiếp cho external script và stylesheet thông qua phần tử script hoặc link có thuộc tính integrity. Với widget/iframe, cần đánh giá origin, CSP, sandbox, postMessage và chính sách của tài liệu được nhúng.

### 2.1. Dependency được đóng gói và dependency tải từ CDN

**Dependency được đóng gói (bundled)** thường được cài trong quá trình build, sau đó bundler tạo ra file JavaScript/CSS do ứng dụng hoặc CDN của chính ứng dụng phân phối.

~~~text
package registry
      |
      v
package manager + lockfile
      |
      v
build pipeline
      |
      v
app bundle / static assets
      |
      v
browser
~~~

**Dependency tải trực tiếp từ CDN** được browser yêu cầu ở runtime:

~~~text
HTML của ứng dụng
      |
      v
browser tải script/style từ CDN bên ngoài
      |
      v
browser kiểm tra policy và integrity
      |
      v
script chạy hoặc stylesheet được áp dụng
~~~

Hai mô hình có rủi ro khác nhau. Bundling giảm số nguồn runtime nhưng đặt nhiều niềm tin vào package registry, dependency tree và build pipeline. CDN runtime giúp triển khai nhanh và chia sẻ cache, nhưng browser phụ thuộc trực tiếp vào tính toàn vẹn, khả dụng và cấu hình của nhà cung cấp CDN.

### 2.2. Một dependency JavaScript có quyền gì?

Ví dụ:

~~~html
<script src="https://cdn.example.net/library-4.2.1.min.js"></script>
~~~

Script external được tải về và thực thi trong môi trường của tài liệu nhúng nó. Nếu trang là https://app.example.com, script thường chạy với quyền JavaScript của trang đó. Nó có thể:

- Đọc hoặc thay đổi DOM mà trang có quyền truy cập.
- Đọc dữ liệu được render trong trang.
- Gọi API bằng quyền và credential mà browser cho phép trong ngữ cảnh đó.
- Đăng ký event listener, quan sát tương tác và sửa giao diện.
- Tải thêm script hoặc gửi dữ liệu tới endpoint khác.

Không nên suy luận rằng script từ CDN chạy trong một sandbox riêng. Nếu cần cô lập một ứng dụng bên thứ ba, cân nhắc iframe với origin riêng và cấu hình sandbox; SRI không tạo sandbox.

## 3. Rủi ro chuỗi cung ứng từ dependency resource

Một dependency có thể bị xâm phạm ở nhiều điểm trước khi browser nhận được file:

~~~mermaid
flowchart TD
    A["Nhà phát triển chọn dependency"] --> B["Package/source repository"]
    B --> C["Tài khoản maintainer và quyền publish"]
    C --> D["Package registry hoặc CDN"]
    D --> E["Build/deploy pipeline"]
    E --> F["HTML và resource URL"]
    F --> G["Browser tải tài nguyên"]
    G --> H["Mã được thực thi trong trang"]
    X["Attacker chiếm tài khoản, package hoặc CDN"] --> C
    X --> D
    X --> E
~~~

Các kịch bản thường gặp:

- **CDN compromise:** file tại URL quen thuộc bị thay bằng nội dung khác.
- **Account takeover:** attacker chiếm tài khoản maintainer hoặc tài khoản quản lý CDN.
- **Dependency confusion/typosquatting:** dự án cài nhầm package cùng tên hoặc tên gần giống.
- **Malicious update:** phiên bản mới của package chứa mã độc hoặc hành vi không mong muốn.
- **Build pipeline compromise:** artifact bị thay đổi sau khi dependency đã được kiểm tra.
- **Mutable URL:** URL trỏ tới latest hoặc nhánh không cố định nên nội dung thay đổi mà HTML không đổi.
- **Transitive dependency:** package trực tiếp kéo theo nhiều package gián tiếp mà nhóm phát triển không review từng package.

Một URL HTTPS chỉ bảo vệ đường truyền tới server; nó không chứng minh nội dung trên server là phiên bản mà ứng dụng đã phê duyệt. SRI giúp kiểm tra nội dung so với hash đã được đưa vào HTML đáng tin cậy.

## 4. Subresource Integrity (SRI)

**Subresource Integrity** cho phép ứng dụng khai báo hash kỳ vọng của tài nguyên external. Browser tải tài nguyên, tính digest bằng thuật toán được khai báo và so sánh với hash trong thuộc tính integrity. Nếu nội dung không khớp, browser từ chối sử dụng tài nguyên.

Ví dụ:

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

BASE64_DIGEST là chỗ giữ chỗ để minh họa; trong ứng dụng thật phải thay bằng digest được tính từ đúng file đã kiểm tra.

### 4.1. Hash được tính từ bytes của tài nguyên

SRI kiểm tra nội dung thực tế được browser nhận, không kiểm tra tên file, version string hoặc URL. Một thay đổi nhỏ trong file có thể làm hash không còn khớp:

- Thêm hoặc bỏ một ký tự.
- Thay đổi whitespace hoặc newline.
- CDN phục vụ bản minified khác.
- Build lại file với dependency hoặc compiler khác.
- Server trả trang lỗi hoặc nội dung khác thay vì tài nguyên mong đợi.

Ví dụ tính SHA-384 bằng Node.js:

~~~js
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const bytes = readFileSync('./library.min.js');
const digest = createHash('sha384').update(bytes).digest('base64');

console.log('sha384-' + digest);
~~~

Kết quả có dạng sha384-... và được đặt vào thuộc tính integrity. Tính hash trên đúng artifact sẽ được deploy; không tính từ một bản khác có cùng tên file.

### 4.2. Các thuật toán hash

SRI hỗ trợ metadata hash dùng các thuật toán SHA-256, SHA-384 và SHA-512. Hãy dùng thuật toán mạnh được browser hỗ trợ và theo hướng dẫn của công cụ build/CDN. SHA-384 là lựa chọn thường thấy trong ví dụ SRI.

Không dùng MD5 hoặc SHA-1 làm integrity metadata. Hash ở đây dùng để kiểm tra tính toàn vẹn của bytes, không phải để ký danh tính nhà phát hành.

### 4.3. SRI với stylesheet

SRI cũng có thể bảo vệ stylesheet external:

~~~html
<link
  rel="stylesheet"
  href="https://cdn.example.net/ui-3.1.0.min.css"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous">
~~~

Nếu CSS trả về khác bytes đã được phê duyệt, browser không áp dụng stylesheet. Điều này giúp ngăn CDN hoặc đường truyền cung cấp một bản CSS ngoài dự kiến.

### 4.4. SRI không đánh giá mã có an toàn hay không

Nếu nhóm phát triển tính hash từ một package đã chứa mã độc rồi đưa hash đó vào HTML, browser vẫn chấp nhận đúng file độc hại ấy. SRI chỉ trả lời câu hỏi:

**“Bytes nhận được có khớp bytes mà ứng dụng đã khai báo là mong đợi không?”**

Nó không trả lời:

- Mã có làm điều nguy hiểm không?
- Maintainer có đáng tin không?
- Package có lỗ hổng đã biết không?
- Build pipeline có bị xâm phạm trước khi tạo hash không?
- Phiên bản đã được review có phù hợp với quyền mà script sẽ có không?

Vì vậy, SRI cần đi cùng review dependency, pin version, kiểm soát publish/build và CSP.

## 5. Vì sao SRI cross-origin cần CORS?

Khi tài nguyên ở cùng origin, browser có thể đọc bytes để kiểm tra integrity theo cơ chế cùng origin. Với tài nguyên cross-origin, browser cần response được chia sẻ qua CORS để có thể thực hiện integrity check.

Ví dụ:

~~~html
<script
  src="https://cdn.example.net/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

CDN cần trả header CORS phù hợp, ví dụ:

~~~http
Access-Control-Allow-Origin: *
~~~

Hoặc giới hạn về origin ứng dụng:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
~~~

crossorigin="anonymous" yêu cầu tài nguyên cross-origin bằng CORS mode và không gửi credential cross-origin thông thường. Nếu CDN không trả Access-Control-Allow-Origin phù hợp, browser không thể sử dụng tài nguyên đó theo SRI và request bị chặn.

### 5.1. anonymous và use-credentials

| Giá trị | Hành vi credential | Yêu cầu CORS điển hình |
| --- | --- | --- |
| crossorigin="anonymous" | Không gửi credential cross-origin | Access-Control-Allow-Origin: * hoặc origin cụ thể |
| crossorigin="use-credentials" | Cho phép gửi credential theo credential mode | Origin phải được chỉ rõ và response cần Access-Control-Allow-Credentials: true |

Với thư viện JavaScript/CSS công khai từ CDN, thường nên dùng anonymous. Không dùng use-credentials chỉ để làm request hoạt động; chỉ bật khi dependency thực sự cần credential và đã đánh giá rủi ro.

### 5.2. CORS không thay SRI

CORS cho phép browser chia sẻ response cross-origin với trang gọi. Nó không xác minh nội dung có phải bản đã được phê duyệt hay không.

SRI kiểm tra bytes theo hash. Với cross-origin resource, CORS cho phép browser có response phù hợp để thực hiện kiểm tra đó. Hai cơ chế bổ sung cho nhau:

- CORS: browser có được phép dùng response cross-origin trong ngữ cảnh này không?
- SRI: bytes của response có khớp hash mong đợi không?

Không thêm Access-Control-Allow-Origin: * vào server ứng dụng một cách tùy tiện. Header này phải được cấu hình ở server đang phục vụ dependency và theo yêu cầu truy cập thực tế.

## 6. SRI, TLS, CSP và package lockfile khác nhau thế nào?

| Cơ chế | Bảo vệ điều gì? | Không bảo vệ điều gì? |
| --- | --- | --- |
| TLS/HTTPS | Mã hóa và xác thực kết nối tới server | Không chứng minh file là bản dependency đã review |
| SRI | Bytes tài nguyên external khớp hash đã khai báo | Không đánh giá mã có an toàn hoặc hash có được tạo từ nguồn đáng tin |
| CORS | Cho phép/chặn việc chia sẻ response cross-origin | Không xác minh tính toàn vẹn hoặc độ an toàn của mã |
| CSP | Giới hạn nguồn và loại hành vi tài nguyên được phép | Không xác minh bytes của từng file nếu không dùng hash phù hợp |
| Lockfile | Cố định cây dependency/version và metadata cài đặt theo package manager | Không tự kiểm soát mọi URL runtime hoặc bảo đảm package không độc hại |
| Review/SBOM | Hỗ trợ hiểu nguồn gốc và thành phần dependency | Không tự ngăn browser tải một file đã bị thay thế |

### 6.1. SRI và CSP

CSP script-src kiểm soát nguồn script được phép tải/thực thi. SRI kiểm tra nội dung của một tài nguyên cụ thể. Ví dụ:

~~~http
Content-Security-Policy: script-src 'self' https://cdn.example.net; object-src 'none'; base-uri 'self'
~~~

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

Host CDN được CSP cho phép nhưng file vẫn phải khớp SRI. Nếu file trên CDN bị thay đổi, SRI chặn nó dù URL vẫn nằm trong host được phép.

Với CSP dùng nonce/hash và strict-dynamic, cần hiểu riêng cơ chế trust propagation. SRI vẫn có thể kiểm tra một external resource, nhưng không tự động áp dụng cho mọi script được loader tạo động. Loader phải gắn đúng integrity và crossOrigin cho từng script cần kiểm tra.

### 6.2. SRI và lockfile

Ví dụ dự án dùng package manager:

~~~bash
npm ci
~~~

package-lock.json cố định phiên bản và thông tin integrity của package tarball theo lockfile. npm ci cài theo lockfile và phù hợp với CI reproducible install.

Lockfile giúp kiểm soát dependency ở thời điểm cài/build. Khi bundler tạo file app.bundle.js và đưa lên CDN, browser không tự đọc package-lock để kiểm tra file đó. Nếu muốn browser xác minh bundle external, cần dùng SRI trên HTML hoặc cơ chế phân phối có kiểm tra integrity tương đương.

## 7. Pin version và quản lý nguồn dependency

### 7.1. Tránh URL mutable

Không nên tải thư viện qua URL thay đổi nội dung mà không đổi tên:

~~~html
<script src="https://cdn.example.net/library/latest.js"></script>
~~~

URL latest.js có thể trỏ tới nội dung mới mà HTML không thay đổi. Hash SRI cũ sẽ chặn nội dung mới, nhưng nếu không có SRI, ứng dụng có thể nhận một bản khác ngoài kế hoạch.

Ưu tiên URL có version cố định:

~~~html
<script
  src="https://cdn.example.net/library/4.2.1/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

Version cố định giúp review thay đổi rõ ràng, nhưng version string không thay thế SRI. Nhà cung cấp vẫn có thể vô tình hoặc cố ý thay nội dung tại cùng URL.

### 7.2. Quy trình cập nhật dependency

Một lần cập nhật dependency nên có các bước:

1. Xác định phiên bản và nguồn phát hành chính thức.
2. Đọc release notes, security advisory và thay đổi API.
3. Cài hoặc tải đúng artifact trong môi trường build được kiểm soát.
4. Review thay đổi mã và dependency bắc cầu khi phù hợp.
5. Tính lại SRI hash từ artifact cuối cùng.
6. Cập nhật version URL và integrity cùng một thay đổi code review.
7. Kiểm thử chức năng, CSP, CORS và browser support.
8. Theo dõi lỗi integrity sau deploy để phát hiện CDN/cache phục vụ sai bytes.

Không cập nhật hash chỉ để làm lỗi SRI biến mất. Trước tiên phải xác minh vì sao bytes thay đổi và artifact mới có được phê duyệt hay không.

### 7.3. Quản lý package gián tiếp

Một package trực tiếp có thể kéo theo hàng chục package gián tiếp. Nên:

- Dùng lockfile và cài đặt reproducible trong CI.
- Review thay đổi lockfile trong pull request.
- Giới hạn quyền publish và token trong pipeline.
- Quét lỗ hổng và theo dõi advisory của dependency.
- Tạo SBOM khi quy trình sản phẩm yêu cầu khả năng truy xuất thành phần.
- Loại package không dùng và giảm quyền của script build không cần thiết.

npm audit hoặc công cụ quét tương tự là tín hiệu hỗ trợ; kết quả sạch không chứng minh package không có mã độc hoặc lỗ hổng chưa được công bố.

## 8. Tự host hay dùng CDN?

Không có lựa chọn phù hợp cho mọi dependency. Hãy so sánh dựa trên khả năng kiểm soát, vận hành và mô hình đe dọa.

| Tiêu chí | Self-host | CDN bên ngoài |
| --- | --- | --- |
| Kiểm soát artifact | Nhóm ứng dụng kiểm soát file deploy | Phụ thuộc nhà cung cấp và cấu hình CDN |
| Khả dụng | Phụ thuộc hạ tầng ứng dụng | Có thể hưởng lợi từ mạng phân phối rộng |
| Cache | Cần tự cấu hình cache/CDN | Nhà cung cấp có thể tối ưu cache |
| Nguồn cập nhật | Quy trình release của ứng dụng | Có thể cập nhật từ nhà cung cấp |
| Rủi ro | Build/deploy/storage của chính ứng dụng | CDN/account/publish chain của nhà cung cấp |
| SRI | Hữu ích khi file được tải từ origin khác hoặc cần xác minh artifact | Đặc biệt hữu ích cho script/style cross-origin |

Self-host không loại bỏ supply-chain risk ở package và build pipeline. CDN không mặc nhiên kém an toàn; nó cần version pinning, SRI, CORS và quản lý nhà cung cấp phù hợp.

## 9. Giới hạn của SRI

SRI là một lớp kiểm soát hữu ích nhưng có phạm vi cụ thể:

- Thuộc tính integrity được áp dụng cho tài nguyên external được browser hỗ trợ, phổ biến nhất là script và stylesheet. Không phải mọi request fetch, ảnh hoặc iframe đều có thể gắn SRI theo cùng cách.
- SRI không kiểm tra inline script trong HTML. Với inline script, dùng CSP hash/nonce và quy trình kiểm soát nội dung phù hợp.
- SRI không tự động bảo vệ script con mà một loader tải động nếu loader không gắn integrity cho script con.
- SRI không cô lập script. Một file đúng hash vẫn có toàn bộ quyền mà browser cấp cho script trong trang.
- SRI không bảo vệ HTML chính khỏi bị thay đổi. Nếu attacker sửa được HTML và thay cả hash, browser có thể chấp nhận artifact do attacker chọn.
- SRI không chứng minh nguồn phát hành đáng tin. Hash cần được lấy từ quy trình review/build đáng tin cậy.
- Tài nguyên thay đổi theo từng request hoặc được cá nhân hóa thường không phù hợp với hash tĩnh.
- Nếu CDN thay đổi nội dung hợp lệ nhưng HTML chưa cập nhật hash, ứng dụng sẽ gặp lỗi tải tài nguyên.

## 10. Tích hợp SRI trong HTML và JavaScript

### 10.1. Script external

~~~html
<script
  src="https://cdn.example.net/library-4.2.1.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
~~~

Đặt version URL, hash và CORS mode trong cùng một thay đổi đã review. Không copy hash từ một blog hoặc ví dụ không gắn với đúng artifact đang sử dụng.

### 10.2. Stylesheet external

~~~html
<link
  rel="stylesheet"
  href="https://cdn.example.net/ui-3.1.0.min.css"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous">
~~~

Nếu stylesheet bị chặn vì mismatch, giao diện có thể mất style nhưng trang vẫn chạy. Theo dõi Console và Network để phát hiện lỗi thay vì chỉ kiểm tra JavaScript.

### 10.3. Script được tạo động

Nếu ứng dụng phải tải script động, đặt integrity và crossOrigin trước khi thêm element vào DOM:

~~~js
function loadPinnedScript(url, integrity) {
  const script = document.createElement('script');
  script.src = url;
  script.integrity = integrity;
  script.crossOrigin = 'anonymous';

  script.onload = () => {
    console.log('Pinned script loaded');
  };

  script.onerror = () => {
    console.error('Script failed CORS or integrity validation');
  };

  document.head.append(script);
}

loadPinnedScript(
  'https://cdn.example.net/charts-2.8.0.min.js',
  'sha384-BASE64_DIGEST'
);
~~~

Không nhận URL hoặc hash từ dữ liệu người dùng. Hãy dùng registry cố định do ứng dụng kiểm soát:

~~~js
const dependencies = Object.freeze({
  charts: {
    url: 'https://cdn.example.net/charts-2.8.0.min.js',
    integrity: 'sha384-BASE64_DIGEST',
  },
});
~~~

Loader chỉ nên nhận tên dependency đã biết và lấy URL/hash từ registry được review.

### 10.4. Preload và các resource hint

Resource hint như preload có thể giúp browser tải tài nguyên sớm. Nếu preload một script cross-origin có SRI, cấu hình crossorigin và integrity phải tương thích với request thực tế để tránh tải lặp hoặc khác mode. Hãy kiểm tra Network panel và tài liệu browser khi tối ưu preload; không thêm hint chỉ vì muốn giảm thời gian tải.

## 11. Thực hành: kiểm tra SRI với Node.js và hai origin

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Hai server chạy trên hai port:

- http://localhost:3000: trang ứng dụng.
- http://localhost:3001: CDN mô phỏng.

Port khác nhau tạo hai origin khác nhau. CDN trả ba loại response: file có hash đúng, file có bytes đã thay đổi và file không bật CORS. Trang ứng dụng gắn cùng hash kỳ vọng để browser cho thấy SRI/CORS chặn các trường hợp không hợp lệ.

### 11.1. Tạo file sri-dependency-lab.mjs

~~~js
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';

const goodScript = Buffer.from(
  "document.querySelector('#good-status').textContent = 'Script đúng hash đã chạy.';"
);

const changedScript = Buffer.from(
  "document.querySelector('#changed-status').textContent = 'Nội dung đã bị thay đổi nhưng không được chạy.';"
);

const digest = createHash('sha384').update(goodScript).digest('base64');
const integrity = 'sha384-' + digest;

function appPage() {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<title>SRI dependency lab</title></head><body>',
    '<h1>Subresource Integrity</h1>',
    '<p id="good-status">Script đúng hash chưa chạy.</p>',
    '<p id="changed-status">Script sai hash chưa chạy.</p>',
    '<p id="cors-status">Script không có CORS chưa chạy.</p>',
    '<script src="http://localhost:3001/good.js"',
    ' integrity="' + integrity + '" crossorigin="anonymous"></script>',
    '<script src="http://localhost:3001/changed.js"',
    ' integrity="' + integrity + '" crossorigin="anonymous"></script>',
    '<script src="http://localhost:3001/no-cors.js"',
    ' integrity="' + integrity + '" crossorigin="anonymous"></script>',
    '<p>Hash được tạo từ đúng bytes của good.js ở server lab.</p>',
    '</body></html>',
  ].join('\n');
}

createServer((req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(appPage());
}).listen(3000, () => {
  console.log('App: http://localhost:3000');
});

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3001').pathname;
  let bytes;
  let enableCors = true;

  if (path === '/good.js') {
    bytes = goodScript;
  } else if (path === '/changed.js') {
    bytes = changedScript;
  } else if (path === '/no-cors.js') {
    bytes = goodScript;
    enableCors = false;
  } else {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  const headers = {
    'Content-Type': 'text/javascript; charset=utf-8',
    'Cache-Control': 'no-store',
  };

  if (enableCors) {
    headers['Access-Control-Allow-Origin'] = 'http://localhost:3000';
  }

  res.writeHead(200, headers);
  res.end(bytes);
}).listen(3001, () => {
  console.log('CDN mock: http://localhost:3001');
  console.log('Expected integrity:', integrity);
});
~~~

### 11.2. Chạy lab

~~~bash
node sri-dependency-lab.mjs
~~~

Mở http://localhost:3000 trong browser.

### 11.3. Kết quả mong đợi

| Resource | CORS | Hash | Kết quả |
| --- | --- | --- | --- |
| /good.js | Cho phép origin ứng dụng | Khớp | Script chạy và cập nhật dòng trạng thái |
| /changed.js | Cho phép origin ứng dụng | Không khớp | Browser từ chối script vì integrity mismatch |
| /no-cors.js | Không có ACAO | Nội dung có hash đúng | Browser từ chối do kiểm tra CORS không thành công |

Mở DevTools → Console và Network:

1. Request /good.js trả 200, có ACAO phù hợp và script chạy.
2. Request /changed.js có CORS hợp lệ nhưng browser báo integrity mismatch; mã không chạy.
3. Request /no-cors.js có thể trả 200 ở Network nhưng bị browser chặn do CORS; việc server trả bytes không có nghĩa trang được phép sử dụng resource.

### 11.4. Thử thay đổi nội dung

Sửa một ký tự trong goodScript nhưng giữ hash đã tạo trước đó hoặc dùng một hash cũ. Browser sẽ từ chối file vì bytes không còn khớp.

Trong lab hiện tại, hash được tính lại khi server khởi động. Vì vậy, để mô phỏng CDN bị thay đổi sau khi HTML đã chốt hash, hãy giữ giá trị integrity cố định đã in ra ở lần chạy đầu rồi thay bytes của goodScript và khởi động lại. Khi đó HTML vẫn mang hash cũ, còn CDN trả nội dung mới.

Không dùng payload nguy hiểm trong thử nghiệm; lab chỉ thay đổi text trong DOM.

### 11.5. Giới hạn lab

- Lab dùng HTTP localhost để đơn giản hóa CORS/SRI; production cần HTTPS cho cả ứng dụng và CDN.
- Hai port khác nhau tạo cross-origin request; CORS được bật có chủ đích cho hai endpoint.
- Lab không mô phỏng package registry, build pipeline hoặc CDN thật.
- Browser có thể hiển thị thông báo lỗi khác nhau; kiểm tra cả Console và Network.

## 12. Theo dõi lỗi và xử lý khi SRI fail

Khi browser chặn dependency:

1. Kiểm tra URL và phiên bản tài nguyên.
2. Xác minh bytes được CDN trả về có đúng artifact đã review không.
3. Kiểm tra redirect chain và cache/CDN edge.
4. Kiểm tra hash được tính từ file nào, sau bước minify/bundle hay trước đó.
5. Với cross-origin, kiểm tra crossorigin và Access-Control-Allow-Origin.
6. Xác minh response không phải trang lỗi HTML hoặc nội dung fallback.
7. Chỉ cập nhật hash sau khi xác nhận artifact mới là hợp lệ và đã được review.

Không tắt SRI hoặc xóa thuộc tính integrity chỉ để khôi phục trang nhanh. Nếu dependency quan trọng bị chặn, có thể rollback về phiên bản artifact và hash đã biết là đúng.

## 13. Checklist quản lý dependency resource

1. **Kiểm kê dependency:** liệt kê script, stylesheet, widget và tài nguyên external.
2. **Xác định owner:** biết nhóm nào chịu trách nhiệm cập nhật và xử lý sự cố từng dependency.
3. **Pin version:** dùng URL hoặc package version cố định, tránh latest và URL mutable.
4. **Xác minh nguồn:** chỉ lấy artifact từ registry/CDN chính thức và pipeline đã kiểm soát.
5. **Bật SRI:** thêm hash cho script/style external tĩnh khi browser hỗ trợ.
6. **Cấu hình CORS:** với SRI cross-origin, dùng crossorigin và response CORS phù hợp.
7. **Dùng CSP:** giới hạn host/script source; không coi allowlist host là kiểm tra integrity.
8. **Review hash:** cập nhật version và integrity trong cùng thay đổi đã review.
9. **Khóa dependency tree:** commit lockfile và dùng chế độ cài reproducible trong CI.
10. **Kiểm tra transitive dependency:** theo dõi package gián tiếp, advisory và quyền publish.
11. **Bảo vệ pipeline:** giới hạn token, quyền deploy, secret và quyền ghi CDN.
12. **Có phương án rollback:** lưu artifact/hash đã phê duyệt để khôi phục khi CDN hoặc bản phát hành có vấn đề.
13. **Theo dõi runtime:** giám sát lỗi SRI, CORS, CSP và tải tài nguyên trên browser thực tế.
14. **Đánh giá quyền:** chỉ cấp cho script bên thứ ba những tích hợp thật sự cần thiết; cân nhắc iframe origin riêng khi cần cô lập.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “HTTPS CDN nghĩa là file chắc chắn đúng.” | TLS bảo vệ kết nối; SRI kiểm tra bytes có khớp hash đã phê duyệt không. |
| “CORS cho phép script thì script đã an toàn.” | CORS chỉ điều khiển chia sẻ response; không xác minh nội dung hoặc hành vi. |
| “Hash đúng chứng minh package không độc hại.” | Hash chỉ chứng minh nội dung khớp giá trị đã khai báo; nguồn tạo hash vẫn phải đáng tin. |
| “SRI tạo sandbox cho script.” | Script vẫn chạy với quyền của trang nhúng nó. |
| “Lockfile bảo vệ mọi URL runtime.” | Lockfile quản lý dependency ở bước cài/build; browser CDN resource cần kiểm soát riêng. |
| “Version URL cố định là đủ.” | Nội dung tại cùng URL vẫn có thể bị thay; SRI xác minh bytes. |
| “SRI tự bảo vệ script con được loader tải.” | Loader phải gắn integrity và CORS mode cho từng script con cần kiểm tra. |
| “Chỉ cần đổi hash khi browser báo lỗi.” | Phải xác minh artifact, nguồn và quy trình phát hành trước khi cập nhật hash. |
| “SRI áp dụng cho mọi loại resource.” | SRI phổ biến với external script và stylesheet; không phải mọi fetch/image/iframe đều hỗ trợ cùng cách. |
| “Self-host loại bỏ supply-chain risk.” | Package, registry, build và deploy pipeline vẫn có thể bị xâm phạm. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Dependency resource là gì?

**Gợi ý trả lời:** Là tài nguyên bên ngoài hoặc thành phần được ứng dụng phụ thuộc để hoạt động, như JavaScript, CSS, font hoặc widget.

**Câu 2.** Vì sao JavaScript tải từ CDN là một phần của ranh giới tin cậy?

**Gợi ý trả lời:** Script thường chạy trong môi trường của trang nhúng và có thể truy cập DOM/API mà trang được phép dùng.

**Câu 3.** SRI xác minh điều gì?

**Gợi ý trả lời:** Browser tính hash từ bytes tài nguyên tải về và so sánh với hash trong thuộc tính integrity; mismatch thì từ chối sử dụng.

**Câu 4.** Vì sao SRI cross-origin cần CORS?

**Gợi ý trả lời:** Browser cần response cross-origin được chia sẻ qua CORS để thực hiện integrity check; thường dùng crossorigin=anonymous và ACAO phù hợp.

**Câu 5.** CORS và SRI khác nhau thế nào?

**Gợi ý trả lời:** CORS quyết định response cross-origin có được chia sẻ cho trang hay không; SRI kiểm tra bytes có khớp hash mong đợi không.

**Câu 6.** Vì sao lockfile không thay SRI cho script tải trực tiếp từ CDN?

**Gợi ý trả lời:** Lockfile cố định dependency ở bước cài/build; browser không đọc lockfile để kiểm tra file external tại runtime.

**Câu 7.** Có nên cập nhật hash ngay khi SRI mismatch không?

**Gợi ý trả lời:** Không. Trước tiên phải xác minh CDN, redirect, cache và artifact mới; chỉ cập nhật hash sau khi nội dung đã được review và phê duyệt.

## Tài liệu tham khảo

- W3C — [Subresource Integrity](https://www.w3.org/TR/SRI/).
- MDN — [Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity).
- MDN — [HTML script element: integrity and crossorigin](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/script).
- MDN — [HTML link element](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/link).
- OWASP — [Third Party JavaScript Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_JavaScript_Management_Cheat_Sheet.html).
- OWASP — [Software Supply Chain Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html).
