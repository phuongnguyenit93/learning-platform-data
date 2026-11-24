# CDN security: bảo vệ tài nguyên web khi phân phối qua CDN

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của Content Delivery Network (CDN) và ranh giới tin cậy khi tải tài nguyên bên thứ ba vào trang web.
2. Nhận diện rủi ro từ CDN compromise, tài khoản nhà cung cấp bị chiếm, DNS, cache poisoning và URL tài nguyên có thể thay đổi.
3. Dùng Subresource Integrity (SRI) để browser xác minh nội dung của script và stylesheet trước khi áp dụng.
4. Cấu hình version pinning, integrity hash, crossorigin và CORS phù hợp với tài nguyên cross-origin.
5. Kết hợp CDN allowlist với Content Security Policy (CSP), TLS, kiểm soát pipeline và quản trị dependency.
6. Phân biệt SRI với CORS, CSP, TLS và cơ chế sandbox của iframe.
7. Kiểm thử CDN asset bằng Chrome DevTools, curl và quy trình xử lý khi hash không khớp.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế. CDN security áp dụng các nguyên tắc đó cho tài nguyên được phân phối từ mạng lưới hoặc nhà cung cấp bên ngoài.

## 1. CDN làm gì và vì sao liên quan đến bảo mật?

Content Delivery Network (CDN) là mạng lưới máy chủ phân phối nội dung từ các điểm hiện diện gần người dùng. Website thường dùng CDN để phục vụ:

- JavaScript và CSS.
- Font, ảnh, video và tệp tĩnh.
- Thư viện frontend dùng chung.
- File tải xuống và nội dung được cache.
- API hoặc nội dung động trong một số kiến trúc.

Ví dụ một trang tải thư viện từ CDN:

```html
<script src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"></script>
<link
  rel="stylesheet"
  href="https://cdn.example.net/libs/ui/4.2.1/ui.min.css">
```

CDN giúp giảm độ trễ và tải cho origin server. Tuy nhiên, khi trang nhúng JavaScript từ CDN, website đang tin cậy nhà cung cấp, đường dẫn, phiên bản và quy trình phát hành của tài nguyên đó.

### Ranh giới tin cậy của script bên thứ ba

Một điểm rất quan trọng: JavaScript được tải từ CDN rồi thực thi trong document thường chạy với quyền của trang nhúng nó. Việc file nằm trên origin khác không biến script thành một sandbox riêng.

Script bên thứ ba có thể, tùy quyền của trang và browser:

- Đọc và sửa DOM của trang.
- Đọc dữ liệu hiển thị trong giao diện và các giá trị không được bảo vệ.
- Đọc cookie không có thuộc tính HttpOnly.
- Truy cập localStorage/sessionStorage của origin nhúng script.
- Gửi request tới API mà trang có thể gọi.
- Gắn event listener và thay đổi hành vi giao diện.

Cookie có HttpOnly vẫn không thể được JavaScript đọc trực tiếp, nhưng script độc hại có thể thực hiện thao tác trong phiên người dùng bằng quyền JavaScript của trang. Vì vậy, đưa script từ CDN vào trang gần như trao cho script đó mức tin cậy tương đương code first-party.

### Threat model: CDN hoặc đường phân phối bị xâm phạm

| Mối đe dọa | Ví dụ | Tác động |
| --- | --- | --- |
| CDN account compromise | Attacker chiếm tài khoản quản trị hoặc API token của nhà cung cấp | Thay nội dung file, redirect hoặc cấu hình phân phối |
| Publisher compromise | Tài khoản package/release của thư viện bị chiếm | Phiên bản mới chứa mã độc được phát hành |
| Mutable URL | Trang tham chiếu latest hoặc nhánh không cố định | Nội dung thay đổi mà HTML không đổi |
| DNS hoặc routing compromise | Người dùng bị điều hướng tới endpoint khác | Tài nguyên giả có thể được phân phối |
| Cache poisoning | Cache lưu response sai theo cache key hoặc request không được phân tách đúng | Nội dung độc hại hoặc nội dung tenant khác bị phục vụ |
| Build pipeline compromise | Pipeline bị chèn bước sửa artifact | File độc hại được phát hành cùng hash mới |
| Third-party script abuse | Script analytics/tag manager bị lạm dụng | Thu thập dữ liệu hoặc thay đổi DOM |

CDN không tự động làm tài nguyên an toàn. Cần xác minh nội dung, nguồn phát hành và quyền của code được tải.

## 2. Các lớp bảo vệ khi dùng CDN

Không có một header duy nhất giải quyết mọi rủi ro. Một cấu hình thực tế thường kết hợp:

| Lớp bảo vệ | Câu hỏi được giải quyết |
| --- | --- |
| HTTPS/TLS | Kết nối tới CDN có được mã hóa và xác thực server không? |
| Version pinning | Website có tham chiếu đúng phiên bản đã review không? |
| Subresource Integrity (SRI) | Bytes tải về có khớp hash đã được duyệt không? |
| CORS | Browser có được phép thực hiện CORS fetch tài nguyên cross-origin không? |
| CSP | Trang được phép tải script/style từ những nguồn nào? |
| Cache policy | CDN có cache đúng nội dung và đúng tenant không? |
| Supply-chain governance | Ai có quyền phát hành, cập nhật và phê duyệt dependency? |
| Monitoring/incident response | Có phát hiện thay đổi bất thường và rollback được không? |

SRI bảo vệ tính toàn vẹn của một số tài nguyên được browser tải qua các phần tử HTML. Nó không xác minh toàn bộ hành vi của script, không bảo vệ HTML gốc khỏi bị sửa và không thay thế quản trị dependency.

## 3. Version pinning: tham chiếu phiên bản cố định

Không dùng URL có nội dung có thể thay đổi theo thời gian:

```html
<!-- Rủi ro: URL trỏ tới phiên bản thay đổi -->
<script src="https://cdn.example.net/libs/ui/latest/ui.min.js"></script>
<script src="https://cdn.example.net/libs/ui/main/ui.min.js"></script>
```

Ưu tiên URL có version cụ thể:

```html
<script src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"></script>
```

Version pinning giúp:

- Xác định rõ artifact được sử dụng.
- Tránh cập nhật bất ngờ khi publisher thay file tại URL cũ.
- Tái tạo build và điều tra incident dễ hơn.
- Kết hợp được với SRI để browser kiểm tra bytes.

Tuy vậy, version cố định không tự chứng minh phiên bản đó an toàn. Một release đã bị compromise ngay từ đầu vẫn có thể được pin. Hãy review changelog, nguồn phát hành, chữ ký/provenance nếu có và kết quả kiểm thử trước khi nâng version.

### URL content-addressed

Một số hệ thống phát hành file với tên chứa hash nội dung, ví dụ:

```text
assets/app.8c7f1a2d.min.js
assets/vendor.4a5d9e10.min.css
```

Tên file content-addressed hỗ trợ cache lâu dài và giảm nhầm lẫn phiên bản. Hash trong tên file không thay thế SRI: browser không tự so sánh nội dung với hash trong tên URL nếu không có integrity metadata.

## 4. Subresource Integrity (SRI) là gì?

Subresource Integrity (SRI) cho phép trang khai báo hash mật mã của nội dung mong đợi. Browser tải tài nguyên, tính hash trên nội dung nhận được và so sánh với giá trị trong thuộc tính integrity.

Nếu nội dung không khớp, browser từ chối sử dụng tài nguyên và ghi lỗi trong Console.

Ví dụ:

```html
<script
  src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"
  integrity="sha384-BASE64_HASH_FROM_REVIEWED_FILE"
  crossorigin="anonymous"></script>
```

Giá trị minh họa BASE64_HASH_FROM_REVIEWED_FILE phải được thay bằng hash thật của đúng file. Không sao chép placeholder vào production.

### SRI kiểm tra điều gì?

SRI xác minh nội dung tài nguyên được tham chiếu có khớp với digest đã khai báo hay không. Nếu CDN, cache hoặc đường truyền trả một phiên bản khác, browser sẽ phát hiện mismatch và chặn tài nguyên.

```text
HTML khai báo hash của ui.min.js phiên bản 4.2.1
                     |
                     v
Browser tải bytes từ CDN
                     |
                     v
Browser tính SHA-384
                     |
            +--------+--------+
            |                 |
         Khớp hash         Không khớp
            |                 |
            v                 v
      Dùng tài nguyên     Chặn tài nguyên
```

### SRI không xác minh điều gì?

SRI không chứng minh:

- Code đã được review về logic hoặc không có backdoor.
- Publisher là người phát hành đáng tin.
- Phiên bản được pin không có lỗ hổng.
- HTML gốc và thuộc tính integrity không bị attacker sửa.
- Mọi script hoặc resource mà script tiếp tục tải đều an toàn.
- Request gửi từ trang không bị lạm dụng.

Nếu attacker chiếm quyền sửa HTML origin, họ có thể thay cả URL và integrity hash. Vì vậy, bảo vệ origin, build pipeline và quyền phát hành vẫn rất quan trọng.

### Tài nguyên nào thường hỗ trợ SRI?

SRI được dùng phổ biến với:

- Script ngoài được tải qua phần tử script.
- Stylesheet ngoài được tải qua link rel="stylesheet".

Không giả định có thể thêm integrity vào mọi loại resource như image, video, fetch hoặc mọi request do JavaScript tạo. Với các loại tài nguyên khác, dùng cơ chế kiểm soát phù hợp với API và platform.

## 5. Tạo integrity hash

Hash phải được tạo từ đúng artifact sẽ được phát hành. Không tạo hash từ file đã được format lại, từ một bản khác phiên bản hoặc từ response chưa xác minh nguồn.

### Dùng OpenSSL

Với SHA-384:

```bash
openssl dgst -sha384 -binary ui.min.js | openssl base64 -A
```

Ghép kết quả Base64 với prefix sha384-:

```text
sha384-<BASE64_OUTPUT>
```

Có thể dùng SHA-256 hoặc SHA-512; SHA-384 thường được dùng trong ví dụ SRI. Không dùng hash yếu hoặc tự tạo thuật toán.

### Tạo hash cho file tải về đã xác minh

Một quy trình hợp lý:

1. Lấy artifact từ release chính thức hoặc registry đã được tổ chức tin cậy.
2. Xác minh version, chữ ký/provenance và checksum do publisher cung cấp nếu có.
3. Lưu artifact vào build workspace.
4. Tính SRI hash từ chính file đó.
5. Review thay đổi trong HTML và dependency manifest.
6. Phát hành HTML và asset cùng một release đã kiểm thử.

Không lấy hash từ cùng CDN đang bị nghi ngờ rồi coi đó là nguồn xác minh độc lập. Nếu attacker kiểm soát CDN và nội dung, họ có thể cung cấp cả file độc hại lẫn hash của file đó.

### SRI và thay đổi bytes

Chỉ cần nội dung tài nguyên thay đổi, hash có thể không còn khớp:

- Publisher cập nhật file tại URL cũ.
- CDN minify hoặc rewrite JavaScript/CSS.
- Pipeline thêm banner, license comment hoặc sửa whitespace.
- Plugin tối ưu hóa thay đổi stylesheet.
- Một endpoint trả nội dung khác theo user-agent hoặc request.

SRI kiểm tra nội dung thực tế, không hiểu rằng hai file có logic tương đương. Hãy cố định artifact và tránh biến đổi nội dung sau khi tạo hash.

## 6. SRI cho tài nguyên cross-origin: cần CORS

Khi dùng SRI với tài nguyên từ origin khác, browser cần thực hiện CORS-enabled request và CDN phải cho phép origin của trang tải tài nguyên. Trong HTML, khai báo crossorigin="anonymous" cho tài nguyên công khai:

```html
<script
  src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"
  integrity="sha384-BASE64_HASH"
  crossorigin="anonymous"></script>

<link
  rel="stylesheet"
  href="https://cdn.example.net/libs/ui/4.2.1/ui.min.css"
  integrity="sha384-BASE64_HASH"
  crossorigin="anonymous">
```

CDN cần trả CORS response header phù hợp. Với asset công khai không cần cookie:

```http
Access-Control-Allow-Origin: *
```

Hoặc CDN có thể trả chính xác origin được phép:

```http
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
```

Không cần bật credential cho thư viện public. crossorigin="anonymous" không gửi credential cross-origin theo cách của chế độ anonymous CORS. Nếu tài nguyên thực sự cần cookie/credential, phải thiết kế CORS chính xác với origin cụ thể và đánh giá lại vì tài nguyên công khai thường không nên phụ thuộc session người dùng.

### CORS không sandbox script

CORS trong trường hợp này cho phép browser thực hiện fetch theo chế độ CORS và cung cấp response hợp lệ để kiểm tra SRI. Nó không biến JavaScript thành code chạy trong sandbox của CDN.

Sau khi script được chấp nhận và thực thi, script vẫn chạy trong context của document nhúng nó. Vì vậy:

- Không tải script từ nguồn chỉ vì CDN đó trả Access-Control-Allow-Origin: *.
- Không coi CORS là cơ chế kiểm soát hành vi script.
- Kết hợp exact version, SRI, CSP và review dependency.

### Lỗi thường gặp khi thiếu crossorigin

Nếu SRI cross-origin được khai báo nhưng CDN không cho phép CORS, browser có thể chặn tài nguyên và Console báo lỗi CORS hoặc integrity. Kiểm tra cả:

1. Thuộc tính crossorigin của element.
2. Response header Access-Control-Allow-Origin.
3. Redirect chain và response cuối.
4. URL có thực sự trỏ tới đúng file.
5. Hash có được tạo từ đúng bytes không.

## 7. CSP và SRI phối hợp với nhau

CSP và SRI giải quyết hai câu hỏi khác nhau:

| Cơ chế | Kiểm soát |
| --- | --- |
| CSP script-src | Trang được phép tải hoặc thực thi script từ nguồn nào và theo chính sách nào |
| SRI integrity | Nội dung script/stylesheet được tải có khớp hash đã khai báo không |
| CORS | Browser có được phép thực hiện CORS fetch tài nguyên cross-origin không |
| TLS | Kết nối tới server có được mã hóa và xác thực không |

Ví dụ policy CSP cho phép một CDN:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.net; style-src 'self' https://cdn.example.net; object-src 'none'; base-uri 'self'
```

Policy host allowlist này giới hạn nguồn script/style, nhưng nếu CDN host bị compromise thì file độc hại trên cùng host vẫn có thể thỏa host allowlist. SRI bổ sung kiểm tra nội dung ở từng element có integrity.

### Không cho phép cả một hệ sinh thái CDN nếu chỉ cần một file

Policy:

```http
Content-Security-Policy: script-src https:
```

cho phép script từ rất nhiều host HTTPS. Nếu ứng dụng chỉ dùng một CDN cụ thể, hãy thu hẹp source list. Tương tự, không thêm wildcard host hoặc domain của mọi dịch vụ marketing chỉ vì một script cần hoạt động.

### CSP không thay SRI

Một CSP host allowlist thường không ràng buộc bytes của file. Nếu file trên CDN bị thay đổi nhưng vẫn được phục vụ từ host được phép, CSP theo host có thể vẫn cho phép nó. SRI kiểm tra nội dung theo hash đã ghim.

Ngược lại, SRI không thay CSP: nó không giới hạn mọi nguồn script mà trang có thể tải, không bảo vệ inline script và không quản lý toàn bộ dynamic loading.

## 8. Ví dụ tích hợp CDN có SRI

### Script và stylesheet

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>CDN integrity demo</title>

  <link
    rel="stylesheet"
    href="https://cdn.example.net/libs/ui/4.2.1/ui.min.css"
    integrity="sha384-REPLACE_WITH_REVIEWED_CSS_HASH"
    crossorigin="anonymous">
</head>
<body>
  <main id="app"></main>

  <script
    src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"
    integrity="sha384-REPLACE_WITH_REVIEWED_JS_HASH"
    crossorigin="anonymous"
    defer></script>
</body>
</html>
```

Thay hai giá trị hash minh họa bằng digest của đúng file CSS và JS. Không dùng chung hash cho hai file khác nhau.

### Fallback có kiểm soát

Nếu CDN không khả dụng hoặc integrity mismatch, browser không tự tìm bản thay thế an toàn. Nếu sản phẩm cần fallback, có thể chuẩn bị một bản local đã được build và kiểm thử:

```html
<script>
  function loadLocalFallback() {
    const fallback = document.createElement("script");
    fallback.src = "/assets/ui-4.2.1.min.js";
    fallback.integrity = "sha384-REVIEWED_LOCAL_HASH";
    fallback.crossOrigin = "anonymous";
    document.head.append(fallback);
  }
</script>

<script
  src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"
  integrity="sha384-REVIEWED_CDN_HASH"
  crossorigin="anonymous"
  defer></script>

<script>
  const primary = document.querySelector(
    'script[src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"]'
  );
  primary.addEventListener("error", loadLocalFallback, { once: true });
</script>
```

Ví dụ chỉ minh họa cơ chế fallback. Trong ứng dụng thực, hãy tránh inline script nếu CSP cấm inline; chuyển logic sang file first-party hoặc dùng nonce/hash phù hợp. Fallback local phải là artifact độc lập đã review, có integrity riêng và được deploy cùng release. Không fallback sang URL latest hoặc một CDN thứ hai chưa xác minh.

## 9. CDN cache và cấu hình phân phối

SRI bảo vệ browser khỏi sử dụng bytes không khớp hash, nhưng CDN vẫn cần cấu hình cache đúng để tránh rò rỉ dữ liệu hoặc phục vụ nhầm nội dung.

### Cache key

Cache key có thể phụ thuộc hostname, path, query string, header hoặc cookie. Nếu cấu hình cache key thiếu một yếu tố làm thay đổi nội dung, CDN có thể phục vụ response của request này cho request khác.

Ví dụ rủi ro:

- API trả dữ liệu cá nhân nhưng CDN cache theo URL mà bỏ qua cookie/session.
- Multi-tenant endpoint cache chung giữa các tenant.
- Query parameter thay đổi nội dung nhưng bị bỏ khỏi cache key.
- Host header không được phân tách đúng.

Biện pháp:

- Không cache response cá nhân/nhạy cảm như asset công khai.
- Dùng Cache-Control: private, no-store cho dữ liệu không được chia sẻ qua cache công cộng khi phù hợp.
- Thiết kế cache key theo đúng các yếu tố quyết định representation.
- Kiểm tra behavior của CDN với request có cookie, authorization và query.
- Dùng test riêng cho từng tenant và từng hostname.

### Cache immutable cho asset đã version hóa

Với asset tĩnh có URL versioned hoặc content-addressed:

```http
Cache-Control: public, max-age=31536000, immutable
```

Đây là lựa chọn phù hợp khi nội dung tại URL không bao giờ thay đổi. Khi release mới, tạo URL mới thay vì ghi đè file cũ. Nếu phải thay đổi file tại cùng URL, cần purge cache và cập nhật integrity metadata đồng bộ; tốt hơn là phát hành URL/version mới.

### Bảo vệ quyền quản trị CDN

- Bật MFA cho tài khoản quản trị.
- Dùng role/permission tối thiểu cho người có thể purge hoặc publish.
- Tách quyền DNS, origin và CDN khi có thể.
- Giới hạn API token theo scope, thời hạn và môi trường.
- Xoay vòng token khi nhân sự rời nhóm hoặc có incident.
- Bật audit log cho thay đổi DNS, cache rule, origin và deployment.
- Chặn truy cập trực tiếp vào origin nếu kiến trúc yêu cầu chỉ CDN được kết nối.
- Bảo vệ origin credential và không nhúng secret vào frontend.

### Cache purge và rollback

Purge cache không thay thế quy trình release. Cần xác định:

- URL nào bị ảnh hưởng.
- Cache ở edge, regional cache và browser có thể giữ nội dung trong bao lâu.
- File mới có version/hash khác hay không.
- HTML đã trỏ tới URL và integrity mới chưa.
- Có thể quay lại artifact đã review trước đó không.

Đối với asset immutable, phát hành URL mới và cập nhật HTML thường an toàn hơn ghi đè URL cũ.

## 10. Quản trị supply chain của CDN dependency

CDN dependency cần được quản lý như dependency trong source code:

### Inventory

Lưu thông tin cho từng tài nguyên:

| Trường | Nội dung cần ghi |
| --- | --- |
| URL | URL đầy đủ và origin |
| Package | Tên thư viện và nhà phát hành |
| Version | Phiên bản cố định |
| Hash | SRI digest và thuật toán |
| Owner | Nhóm chịu trách nhiệm |
| Purpose | Lý do cần tài nguyên |
| Data access | Dữ liệu/DOM/API mà script có thể truy cập |
| CSP | Directive cho phép nguồn |
| Review date | Ngày đánh giá và lịch nâng cấp |
| Removal plan | Cách gỡ dependency khi có sự cố |

### Review update

Khi nâng phiên bản:

1. Đọc release notes và security advisory.
2. Kiểm tra package name, publisher và nguồn phát hành.
3. Review diff hoặc artifact provenance khi có thể.
4. Tính lại SRI hash từ artifact đã xác minh.
5. Chạy test chức năng và security test.
6. Cập nhật URL, integrity và dependency inventory trong cùng pull request.
7. Deploy staging, xác minh Network/Console rồi mới production.

Không tự động cập nhật hash mỗi khi CDN trả nội dung khác. Làm như vậy có thể hợp thức hóa một thay đổi chưa được review.

### Giảm số lượng script bên thứ ba

Mỗi script thêm vào trang mở rộng quyền của một nhà cung cấp. Hãy:

- Gỡ script không còn dùng.
- Hạn chế tag manager và script marketing có quyền rộng.
- Không tải URL script do user hoặc query parameter kiểm soát.
- Không dùng JSONP hoặc dynamic script loading nếu không có lý do và kiểm soát rõ.
- Ưu tiên self-host dependency quan trọng nếu tổ chức có thể vận hành an toàn.
- Dùng iframe sandbox cho tích hợp thực sự không tin cậy thay vì cấp quyền script trực tiếp vào document.

## 11. Giới hạn của SRI với dynamic loading và dependency tree

SRI trên một phần tử script kiểm tra nội dung của tài nguyên được phần tử đó tải. Nó không tự xác minh mọi tài nguyên mà code đó tiếp tục tải hoặc tạo ra:

- Script chèn thêm phần tử script khác.
- Dynamic import hoặc module dependency.
- Worker/service worker.
- Fetch API lấy JavaScript hoặc cấu hình.
- Code được tạo từ chuỗi.

Với dependency tree, phải quản lý từng nguồn và cơ chế integrity phù hợp với cách browser tải tài nguyên đó. Không giả định một hash ở script entrypoint bao phủ toàn bộ dependency graph.

### Module script

Ví dụ:

```html
<script
  type="module"
  src="/assets/app.8c7f1a2d.js"
  integrity="sha384-REVIEWED_MODULE_HASH"
  crossorigin="anonymous"></script>
```

Integrity ở đây gắn với module resource được tham chiếu. Các module dependency được import tiếp cần được quản lý riêng theo khả năng và cơ chế integrity của module loading; đừng xem hash của entry module là hash cho mọi file trong graph.

### SRI không bảo vệ inline code

SRI không phải cơ chế hash cho inline script trong HTML. Để quản lý inline script, dùng CSP nonce hoặc hash source phù hợp; tốt hơn là giảm inline code và tách logic ra file có thể quản lý.

## 12. Kiểm thử CDN security bằng Chrome DevTools

Thực hiện trong staging hoặc trang lab do bạn kiểm soát. Dùng một tài nguyên test có version cố định và hash đã tính từ file được review.

### Bước 1 — Kiểm tra request

1. Mở DevTools → Network.
2. Bật Disable cache trong khi DevTools đang mở.
3. Tải lại trang.
4. Chọn request script hoặc stylesheet CDN.
5. Kiểm tra Request URL, status, redirect, response headers và initiator.
6. Xác nhận response đến từ hostname/version mong muốn.

### Bước 2 — Kiểm tra CORS

Với tài nguyên cross-origin có SRI:

1. Xác nhận element có crossorigin="anonymous".
2. Xem response có Access-Control-Allow-Origin phù hợp.
3. Nếu CDN redirect, kiểm tra CORS trên response cuối và từng bước cần thiết trong chain.
4. Quan sát Console để phân biệt CORS error với integrity mismatch.

### Bước 3 — Thử integrity mismatch trong lab

Trong môi trường test, thay một ký tự trong hash:

```html
<script
  src="https://cdn.example.net/libs/ui/4.2.1/ui.min.js"
  integrity="sha384-INTENTIONALLY_WRONG_HASH"
  crossorigin="anonymous"></script>
```

Browser phải từ chối thực thi tài nguyên và ghi lỗi integrity trong Console. Khôi phục hash hợp lệ sau thí nghiệm.

### Bước 4 — Thử file thay đổi tại URL cũ

Trong CDN sandbox:

1. Tải asset versioned và ghi nhận hash.
2. Thay bytes ở URL test.
3. Purge cache để request nhận representation mới.
4. Tải lại trang vẫn dùng integrity hash cũ.
5. Xác nhận browser chặn tài nguyên vì mismatch.

Không thực hiện thao tác ghi đè trên CDN production.

### Bước 5 — Kiểm tra CSP

Tạm bỏ hostname CDN khỏi script-src trong staging. Xác nhận browser chặn script theo CSP ngay cả khi integrity hash đúng. Khôi phục policy sau test.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Version và hash đúng | URL cố định, hash đúng, CORS hợp lệ | Resource được sử dụng |
| Hash sai | Nội dung không khớp integrity | Browser chặn resource |
| CDN không có ACAO | Cross-origin SRI, CORS không hợp lệ | Browser chặn fetch/resource |
| Thiếu crossorigin | Cross-origin SRI không thiết lập CORS mode phù hợp | Có thể bị chặn; kiểm tra Console và cấu hình element |
| CSP không cho host | Hash đúng nhưng script-src không cho nguồn | Browser chặn theo CSP |
| URL latest thay nội dung | Nội dung thay đổi nhưng hash giữ nguyên | SRI mismatch và chặn |
| Script bị compromise trước khi hash | Hash được tạo từ artifact độc hại | SRI vẫn chấp nhận; lỗi nằm ở nguồn tin cậy/review |
| HTML origin bị compromise | Attacker sửa cả URL và integrity | SRI đơn lẻ không bảo vệ được |
| Script tải dependency khác | Entry script hợp lệ nhưng dependency không được quản lý | Phải kiểm soát dependency riêng |

## 13. Xử lý sự cố khi CDN asset bị nghi ngờ

Khi phát hiện script/stylesheet CDN bất thường hoặc integrity mismatch:

1. Xác định URL, version, hash, browser, thời điểm và nhóm người dùng bị ảnh hưởng.
2. Tạm ngừng tải tài nguyên nếu có thể; gỡ element hoặc chặn nguồn bằng CSP theo quy trình ứng phó.
3. So sánh bytes đang được CDN phục vụ với artifact đã review trong repository/build store.
4. Kiểm tra audit log tài khoản CDN, DNS, cache rule, API token và release pipeline.
5. Thu hồi/rotate credential bị lộ; khóa quyền publish hoặc purge bất thường.
6. Purge cache liên quan sau khi đã xác định artifact an toàn.
7. Phát hành lại URL/version mới và integrity hash được tính từ artifact đã xác minh.
8. Kiểm tra HTML origin, build pipeline và các dependency khác có cùng nguồn tin cậy.
9. Theo dõi browser Console, CSP report và telemetry để xác nhận sự cố đã được xử lý.

Không chỉ cập nhật hash để làm hết lỗi. Integrity mismatch có thể là tín hiệu duy nhất cho thấy CDN đang trả nội dung khác với bản đã được duyệt.

### Khi nào cần self-host?

Ưu tiên self-host hoặc loại bỏ dependency nếu:

- Nhà cung cấp không có quy trình bảo mật và thông báo incident đáng tin.
- URL không thể pin version hoặc nội dung thường xuyên thay đổi.
- Không hỗ trợ CORS cần thiết cho SRI.
- Script có quyền quá rộng so với giá trị chức năng.
- Tổ chức cần kiểm soát release, retention hoặc availability chặt hơn.

Self-host không tự động an toàn: origin server, pipeline, quyền ghi file và cache của chính bạn vẫn cần được bảo vệ.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng URL latest hoặc branch mutable | Nội dung thay đổi mà không có review | Pin version hoặc content-addressed URL |
| Không dùng SRI cho script quan trọng từ CDN | Không phát hiện bytes bị thay đổi | Tạo integrity hash từ artifact đã review |
| Lấy hash từ CDN đang bị nghi ngờ | Hash có thể xác nhận chính file độc hại | Xác minh artifact từ nguồn độc lập |
| Cho rằng SRI chứng minh code an toàn | Code độc hại được phát hành cùng hash vẫn hợp lệ | Review publisher, release và logic |
| Quên crossorigin với cross-origin SRI | CORS fetch có thể thất bại | Dùng crossorigin anonymous và cấu hình ACAO |
| Nghĩ CORS sandbox script | Script vẫn chạy trong context của trang | Chỉ tin script đã review; dùng iframe sandbox cho nội dung không tin cậy |
| Chỉ dùng CSP host allowlist | File bị thay đổi trên host vẫn có thể được cho phép | Kết hợp SRI và CSP |
| Nghĩ hash entrypoint bao phủ mọi dependency | Dynamic imports/resource khác có thể không được kiểm tra | Inventory và quản lý từng dependency |
| Tự động cập nhật integrity khi hash mismatch | Có thể chấp nhận mã chưa review | Điều tra, xác minh artifact rồi mới cập nhật |
| Cache response cá nhân như asset công khai | Rò rỉ dữ liệu giữa người dùng/tenant | Tách cache policy và cache key đúng |
| Cho quá nhiều người quyền publish CDN | Tăng nguy cơ account compromise | MFA, least privilege và audit log |
| Dùng fallback sang URL không pin | Fallback có thể tải code không xác minh | Dùng artifact local đã review và hash riêng |

## 15. Câu hỏi củng cố

**Câu 1.** Vì sao script từ CDN có thể truy cập DOM của trang nhúng nó?

**Giải đáp:** Script được thực thi trong JavaScript realm của document nhúng script. Origin của URL tải file không tạo sandbox riêng cho code.

**Câu 2.** SRI giải quyết vấn đề gì?

**Giải đáp:** Browser so sánh hash nội dung tải về với digest đã khai báo. Nếu bytes thay đổi, browser chặn sử dụng tài nguyên.

**Câu 3.** Vì sao cross-origin SRI cần CORS?

**Giải đáp:** Browser cần thực hiện CORS-enabled request để xác minh tài nguyên cross-origin. Element cần cấu hình crossorigin phù hợp và CDN phải trả Access-Control-Allow-Origin hợp lệ.

**Câu 4.** SRI có bảo vệ khi attacker sửa cả HTML và integrity hash không?

**Giải đáp:** Không. Nếu HTML origin bị kiểm soát, attacker có thể thay cả URL và hash. Cần bảo vệ origin, pipeline và quyền phát hành.

**Câu 5.** CSP cho phép cdn.example.net có thay SRI không?

**Giải đáp:** Không. CSP host allowlist kiểm soát nguồn được tải; nó không nhất thiết khóa bytes của file. SRI bổ sung kiểm tra nội dung.

**Câu 6.** Nếu entry script có SRI đúng, mọi dynamic import của nó có được xác minh tự động không?

**Giải đáp:** Không nên giả định như vậy. SRI trên element kiểm tra resource được element đó tải; các dependency và resource tiếp theo cần được quản lý theo cơ chế tương ứng.

**Câu 7.** Khi integrity mismatch xuất hiện, có nên tính lại hash từ response CDN rồi cập nhật HTML ngay không?

**Giải đáp:** Không. Hãy xác minh artifact từ nguồn phát hành đáng tin, điều tra thay đổi và chỉ cập nhật hash sau review.

## 16. Tổng kết

CDN giúp phân phối tài nguyên nhanh và ổn định, nhưng khi nhúng script từ CDN, website trao cho script đó quyền chạy trong context của trang. Hãy pin version, quản lý publisher và pipeline, dùng HTTPS, giới hạn nguồn bằng CSP và dùng SRI để browser xác minh bytes của script/stylesheet.

Với tài nguyên cross-origin có SRI, cấu hình CORS và crossorigin="anonymous" phù hợp; nhớ rằng CORS không sandbox script. SRI không xác minh logic code, không bảo vệ HTML origin bị compromise và không tự bao phủ toàn bộ dependency tree. Kết hợp inventory, review release, cache policy, quyền CDN tối thiểu, DevTools test và incident response để duy trì tính toàn vẹn của tài nguyên.

## Tài liệu tham khảo

1. [W3C — Subresource Integrity](https://www.w3.org/TR/SRI/): đặc tả integrity metadata, thuật toán hash và kiểm tra resource.
2. [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity): cú pháp SRI, CORS và ví dụ script/stylesheet.
3. [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): CORS request và response header.
4. [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): giới hạn nguồn và thực thi script.
5. [OWASP — Third Party JavaScript Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html): quản trị rủi ro JavaScript bên thứ ba.
6. [OWASP — Software Supply Chain Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html): kiểm soát dependency và pipeline phát hành.
