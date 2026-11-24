# SRI deployment

> **Chương:** Resource integrity  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Subresource Integrity (SRI) chỉ phát huy tác dụng khi hash được gắn đúng với artifact đã kiểm tra và được phát hành đồng bộ với HTML. Trong một ứng dụng thực tế, JavaScript/CSS có thể đi qua package manager, bundler, CDN, reverse proxy, cache, service worker và cơ chế tải động. Nếu một bước thay đổi nội dung sau khi hash được tạo, browser sẽ từ chối tài nguyên; nếu pipeline tự động tin nội dung không được review rồi cập nhật hash theo nó, SRI có thể hợp thức hóa chính tài nguyên độc hại.

**SRI deployment** là quá trình đưa integrity metadata vào chuỗi build và phát hành: kiểm kê tài nguyên, pin phiên bản, tạo hash từ artifact cuối cùng, cấu hình CORS cho CDN, phát hành HTML cùng manifest, kiểm tra trên browser và chuẩn bị rollback. SRI bảo vệ byte của tài nguyên được gắn `integrity`; nó không thay thế việc bảo vệ HTML, kiểm soát nguồn tải bằng CSP hay quản trị dependency.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định tài nguyên nào nên được bảo vệ bằng SRI trong ứng dụng.
2. Pin phiên bản và chọn nguồn phát hành đáng tin cậy cho asset.
3. Tạo digest từ artifact cuối cùng sau build/minify.
4. Tích hợp `integrity` vào HTML, template và build manifest.
5. Cấu hình CORS cho asset cross-origin trên CDN.
6. Phân biệt SRI runtime với trường `integrity` trong lockfile của package manager.
7. Quản lý tài nguyên động, module và dependency graph.
8. Đồng bộ HTML, asset, CDN cache và service worker trong một release.
9. Tự động kiểm tra SRI trong CI và xử lý mismatch.
10. Triển khai cập nhật, giám sát và rollback mà không bỏ integrity protection.

## 2. Mục tiêu của SRI trong quy trình phát hành

SRI tạo liên kết giữa một HTML document đã được phê duyệt và nội dung của tài nguyên mà document tải. Ví dụ:

```html
<script
  src="https://cdn.example.net/vendor/chart/5.4.0/chart.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

Browser tải file, tính digest theo thuật toán được khai báo và so sánh với metadata. Nếu nội dung không khớp, browser không thực thi script. Với stylesheet, browser không áp dụng CSS không vượt qua kiểm tra integrity.

Trong deployment, câu hỏi quan trọng là: **digest này được tạo từ artifact nào, ai đã phê duyệt artifact đó, và có bước nào thay đổi byte sau khi digest được tạo không?** Nếu không trả lời được ba câu hỏi này, thuộc tính `integrity` chỉ là một chuỗi hash không có quy trình tin cậy đứng sau.

## 3. SRI bảo vệ gì và không bảo vệ gì?

| SRI giúp bảo vệ | SRI không tự bảo vệ |
| --- | --- |
| Script hoặc stylesheet có nội dung khác digest được phê duyệt | HTML document chứa URL và hash |
| Asset CDN bị thay byte ngoài quy trình release | Quy trình build/release tự động chấp nhận artifact độc hại |
| Lỗi CDN trả nhầm phiên bản file | Mọi dependency mà script/CSS tải tiếp |
| Một số thay đổi ngoài dự kiến trên đường phân phối asset | Tính an toàn logic của thư viện đã được phê duyệt |
| Tài nguyên tĩnh được pin bằng digest | API, JSON, dữ liệu runtime hoặc nội dung người dùng |

Nếu attacker sửa được HTML, họ có thể đổi cả URL lẫn `integrity` để trỏ tới tài nguyên khác. Vì vậy, HTML phải được bảo vệ bằng HTTPS, kiểm soát deploy, CSP và các biện pháp bảo vệ ứng dụng phù hợp. SRI không thay thế review dependency, xác minh nguồn package hoặc bảo vệ tài khoản phát hành.

## 4. Kiểm kê tài nguyên trước khi bật SRI

Tạo inventory từ HTML render cuối, template server, manifest bundler và các đoạn code tải tài nguyên động. Phân loại tối thiểu:

| Nhóm | Ví dụ | Quyết định |
| --- | --- | --- |
| Script bên thứ ba cố định | Thư viện analytics hoặc chart có version cụ thể | Ưu tiên SRI nếu URL/content ổn định và CDN hỗ trợ CORS |
| Stylesheet CDN | CSS framework hoặc icon set | Dùng SRI khi file tĩnh, versioned |
| Asset cùng origin | Bundle do ứng dụng build | Có thể dùng SRI; cân nhắc lợi ích so với độ phức tạp phát hành |
| Script tải động | Plugin hoặc SDK được thêm bằng JavaScript | Cần manifest URL/hash đáng tin và gán metadata trước request |
| Module graph | Entry module và các import con | Kiểm tra cách từng dependency được pin; hash entrypoint không mặc nhiên pin toàn graph |
| Nội dung runtime | JSON API, HTML người dùng, cấu hình động | SRI không phải cơ chế phù hợp; dùng schema, auth, validation và các biện pháp tương ứng |

Với mỗi tài nguyên, ghi nhận URL, owner, version, nguồn artifact, hash, request mode, CORS response, CSP directive và nơi HTML được tạo. Đừng chỉ tìm thẻ `<script>` tĩnh: framework, tag manager và dependency có thể tạo element lúc runtime.

## 5. Chọn tài nguyên phù hợp để pin

SRI phù hợp nhất với file có nội dung bất biến theo phiên bản. Chọn asset có:

- Version rõ ràng trong URL hoặc tên file content-addressed.
- Artifact tải/build được từ nguồn đã xác minh.
- Nội dung không bị CDN hoặc proxy rewrite sau khi phát hành.
- Chủ sở hữu chịu trách nhiệm cập nhật và xử lý sự cố.
- CORS được cấu hình nếu asset nằm ở origin khác.

Tránh dùng URL như `/latest.js`, `/current.css` hoặc alias luôn trỏ tới bản mới. Nếu nội dung tại cùng URL thay đổi, HTML đang cache có thể giữ hash cũ và browser sẽ chặn tài nguyên mới.

Không phải mọi tài nguyên đều cần SRI. Ưu tiên script và stylesheet có ảnh hưởng lớn tới ứng dụng, đặc biệt là dependency bên thứ ba. Đừng thêm metadata cho một resource nếu pipeline không thể duy trì hash đáng tin cậy.

## 6. Pin phiên bản và kiểm soát nguồn artifact

Với dependency CDN, dùng version cụ thể:

```html
<!-- URL có version cố định -->
<script src="https://cdn.example.net/vendor/library/4.2.1/library.min.js"></script>
```

Với dependency cài qua package manager:

- Pin version trực tiếp hoặc dùng range có chủ đích.
- Commit lockfile và review thay đổi dependency.
- Xác minh package registry, publisher và nguồn tarball theo quy trình của tổ chức.
- Chạy kiểm tra lỗ hổng và license phù hợp.
- Build từ dependency tree đã khóa trong môi trường CI được kiểm soát.

SRI không chứng minh package an toàn; nó chỉ chứng minh asset runtime khớp digest đã đưa vào HTML. Một package độc hại được phê duyệt rồi build thành bundle vẫn có hash hợp lệ. Vì vậy, review nguồn và thay đổi package phải xảy ra trước bước tạo hash.

## 7. Tạo hash sau bước build cuối cùng

Digest phải được tạo từ byte của artifact mà browser sẽ nhận sau khi giải mã content-encoding. Các bước như transpile, bundling, minify, tree-shaking, banner injection, license comment removal hoặc CDN rewriting có thể thay đổi nội dung.

Quy trình đúng:

1. Cài dependency từ lockfile.
2. Build trong CI theo cấu hình phát hành.
3. Chạy kiểm tra và review artifact.
4. Chạy bước minify/transform cuối cùng.
5. Tính SHA-256, SHA-384 hoặc SHA-512 trên file output.
6. Tạo manifest và HTML/template có `integrity`.
7. Phát hành đúng artifact đã hash.

Ví dụ Node.js:

```js
const { createHash } = require("node:crypto");
const { readFileSync } = require("node:fs");

function sriFor(path) {
  const bytes = readFileSync(path);
  const digest = createHash("sha384").update(bytes).digest("base64");
  return `sha384-${digest}`;
}

console.log(sriFor("dist/assets/vendor.min.js"));
```

Ví dụ OpenSSL:

```bash
openssl dgst -sha384 -binary dist/assets/vendor.min.js | openssl base64 -A
```

Không tính hash từ source trước khi bundling rồi dùng cho file đã minify. Cũng không lấy hash từ một response CDN đang hoạt động mà không so sánh với artifact đã được xác minh; CDN có thể đang phục vụ nội dung đã bị thay đổi.

## 8. Tạo manifest integrity trong build

Một build có thể tạo manifest nối tên asset với URL và digest:

```json
{
  "vendorChart": {
    "url": "https://cdn.example.net/vendor/chart/5.4.0/chart.min.js",
    "integrity": "sha384-BASE64_DIGEST",
    "crossorigin": "anonymous"
  },
  "appStyles": {
    "url": "/assets/app.8f31c2.css",
    "integrity": "sha384-ANOTHER_BASE64_DIGEST"
  }
}
```

Các digest trong ví dụ là placeholder. Manifest nên được tạo tự động từ artifact đã build và được version hóa cùng release. Template server hoặc frontend bootstrap chỉ đọc manifest đã phát hành; không tự tính lại hash từ URL do người dùng cung cấp.

Manifest giúp:

- Tránh cập nhật URL và hash ở nhiều nơi.
- Đồng bộ HTML với asset version.
- Tạo báo cáo dependency và nguồn phát hành.
- Kiểm tra integrity metadata trước khi deploy.
- Hỗ trợ rollback về một release có manifest đầy đủ.

Không đưa bí mật hoặc token vào manifest; URL và digest đều có thể được người dùng nhìn thấy trong HTML.

## 9. Gắn SRI cho script tĩnh

Khi render HTML, đặt URL, integrity và crossorigin trên cùng element:

```html
<script
  src="https://cdn.example.net/vendor/chart/5.4.0/chart.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"
  defer></script>
```

`defer` điều khiển thời điểm thực thi script classic; nó không ảnh hưởng cách SRI xác minh nội dung. Có thể đặt thuộc tính theo thứ tự khác nhau trong HTML, nhưng tất cả phải có mặt khi browser xử lý request.

Với script cùng origin, CORS không cần thiết cho SRI theo cách tài nguyên cross-origin cần. Với CDN cross-origin, dùng `crossorigin="anonymous"` cho asset công khai và cấu hình response CORS phù hợp.

## 10. Gắn SRI cho stylesheet

Ví dụ CSS trên CDN:

```html
<link
  rel="stylesheet"
  href="https://cdn.example.net/ui/3.8.0/ui.min.css"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous">
```

Nếu digest sai, browser không áp dụng stylesheet. Người dùng có thể thấy layout không được định dạng; cần có giám sát để phân biệt lỗi SRI với CSS tải chậm, lỗi mạng hoặc CSP.

Hash chỉ xác minh file CSS được gắn `integrity`. Nếu CSS tham chiếu font, ảnh nền hoặc `@import`, những tài nguyên đó cần được quản lý riêng bằng URL/version/CORS/CSP và cơ chế integrity thích hợp nếu được hỗ trợ.

## 11. CORS cho asset CDN cross-origin

SRI với tài nguyên cross-origin cần CORS-enabled request và response phải vượt qua CORS check. Với asset công khai không cần cookie, cấu hình thường dùng là:

```html
<script
  src="https://cdn.example.net/vendor/library/4.2.1/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

Response từ CDN:

```http
Access-Control-Allow-Origin: *
```

Nếu CDN chỉ cho phép một frontend cụ thể:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Không phản chiếu tùy ý request `Origin`. Nếu response cần credential, phải dùng origin cụ thể và `Access-Control-Allow-Credentials: true`; không dùng wildcard `*` cho credentialed CORS. Asset JavaScript/CSS công khai thường không cần credential, vì vậy `anonymous` là lựa chọn đơn giản hơn.

## 12. Phân biệt SRI runtime với lockfile integrity

Package manager có thể ghi trường `integrity` trong lockfile để xác minh tarball package khi cài dependency. Ví dụ, npm lockfile có thể lưu digest của package tarball. Cơ chế này hoạt động ở bước cài package trong môi trường build.

SRI trên HTML hoạt động ở browser runtime:

| Tiêu chí | Lockfile integrity | Browser SRI |
| --- | --- | --- |
| Thời điểm | Khi package manager tải/cài package | Khi browser tải script/stylesheet |
| Metadata | Lockfile/package manager | HTML `integrity` hoặc API được hỗ trợ |
| Nội dung xác minh | Package archive/tarball theo định dạng package manager | Byte của resource response |
| Chủ thể thực hiện | npm/yarn/pnpm hoặc công cụ tương ứng | Browser |
| Thay thế nhau? | Không | Không |

Lockfile giúp bảo đảm CI cài đúng package archive đã khóa; nó không tự tạo `integrity` cho thẻ `<script>` trong HTML. Ngược lại, SRI runtime không thay thế lockfile hoặc kiểm tra package supply chain.

## 13. Tải tài nguyên động

Nếu ứng dụng tạo script element bằng JavaScript, lấy URL và hash từ manifest tin cậy rồi gán metadata trước khi append:

```js
const asset = buildManifest.vendorChart;
const script = document.createElement("script");

script.src = asset.url;
script.integrity = asset.integrity;
script.crossOrigin = asset.crossorigin;
script.async = true;

script.addEventListener("error", () => {
  showAssetLoadError("Không thể tải thư viện biểu đồ đã xác minh.");
});

document.head.append(script);
```

Không append element trước rồi mới đặt `integrity`; browser có thể đã bắt đầu request. Không nhận URL và hash từ hai nguồn không tin cậy rồi ghép lại. Cần kiểm tra manifest schema, allowlist host/path và phiên bản trước khi tạo element.

Không tự động retry bằng cách bỏ `integrity` khi request thất bại. Nếu hash mismatch, hành động an toàn là dừng sử dụng asset, báo lỗi có kiểm soát và khôi phục artifact đã xác minh.

## 14. Module script và dependency graph

Module script có thể import các module khác:

```html
<script type="module" src="/assets/main.js"></script>
```

Việc gắn `integrity` vào entrypoint chỉ xác minh tài nguyên được gắn metadata đó; không nên giả định một hash đơn lẻ tự động pin mọi module import riêng biệt hoặc toàn bộ dependency graph. Module loading còn sử dụng CORS và các quy tắc module fetch.

Các lựa chọn deployment:

- Bundle dependency quan trọng vào một artifact đã kiểm tra rồi gắn SRI cho bundle.
- Dùng URL versioned và quản lý integrity metadata cho từng tài nguyên theo cơ chế browser/tooling hỗ trợ.
- Nếu dùng import map hoặc cơ chế integrity metadata cho module graph, xác minh browser support và hành vi chính xác trước khi dựa vào nó.
- Giới hạn host bằng CSP `script-src` và không cho module import từ URL tùy ý.

Kiểm thử cả entrypoint lẫn các request module con trong Network. Không suy luận toàn graph an toàn chỉ từ việc entrypoint vượt qua SRI.

## 15. Preload và tải sớm tài nguyên

Một số tài nguyên có thể được preload để browser tải sớm. Khi sử dụng `link rel="preload"` cho tài nguyên có SRI, integrity metadata và CORS mode cần nhất quán với cách tài nguyên được tiêu thụ:

```html
<link
  rel="preload"
  as="script"
  href="https://cdn.example.net/vendor/library/4.2.1/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous">
```

Sau đó script dùng cùng URL, integrity và CORS mode. Nếu preload và request tiêu thụ khác mode hoặc khác URL, browser có thể không tái sử dụng response đã preload và phát sinh request khác.

Chỉ preload tài nguyên thực sự cần thiết; preload quá nhiều asset làm tăng cạnh tranh băng thông và có thể ảnh hưởng hiệu năng. Kiểm tra Network để xác nhận browser tái sử dụng đúng response.

## 16. Kết hợp SRI với CSP

CSP và SRI bảo vệ hai phần khác nhau của quá trình tải:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.net; style-src 'self' https://cdn.example.net; object-src 'none'; base-uri 'self'
```

```html
<script
  src="https://cdn.example.net/vendor/library/4.2.1/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"></script>
```

CSP giới hạn nguồn script được phép tải; SRI kiểm tra nội dung file cụ thể. Cả hai cùng cần đúng: host được CSP cho phép nhưng hash sai vẫn bị SRI chặn; hash đúng nhưng host bị CSP chặn vẫn không được tải.

Không nới `script-src` thành `*` chỉ vì đã thêm SRI. Một allowlist host rõ ràng vẫn giảm bề mặt request và hạn chế URL mà HTML bị sửa có thể trỏ tới.

## 17. CDN, cache và phát hành bất biến

SRI hoạt động ổn định khi asset là immutable. Mô hình phát hành nên dùng:

- URL chứa version hoặc content hash.
- Cache dài cho asset bất biến, ví dụ `Cache-Control: public, max-age=31536000, immutable` khi phù hợp.
- Không ghi đè nội dung tại URL đã phát hành.
- HTML/manifest được cập nhật cùng release.
- CDN không minify, inject banner hoặc rewrite asset sau khi hash được tạo.
- Purge/invalidate có kế hoạch cho HTML, không xóa asset cũ khi HTML cache vẫn tham chiếu.

Ví dụ:

```text
Release A:
  /assets/app.81ac2f.js  -> hash A
  /index.html            -> integrity A

Release B:
  /assets/app.95bd73.js  -> hash B
  /index.html            -> integrity B
```

Giữ asset của release A trong thời gian HTML cũ có thể còn được cache hoặc mở ở tab đang hoạt động. Khi HTML mới được phát hành, nó tham chiếu URL và hash của release B. Cách này giảm lỗi do HTML và asset lệch phiên bản.

## 18. Service worker và cache runtime

Service worker có thể intercept request và trả response từ Cache Storage hoặc mạng. SRI vẫn kiểm tra response body được browser nhận cho resource có integrity; nếu service worker trả byte không khớp, browser có thể từ chối resource.

Khi triển khai SRI cùng service worker:

- Cache asset theo URL/version bất biến.
- Không ghi đè cache entry bằng nội dung khác tại cùng URL.
- Cập nhật cache manifest cùng release HTML.
- Giữ asset cũ đủ lâu cho client đang chạy release trước.
- Test offline, update worker, activation và rollback.
- Không coi service worker là nguồn hash độc lập nếu chính worker/HTML có thể bị thay đổi.

Nếu worker bị xâm nhập hoặc HTML bị sửa, attacker có thể thay đổi URL/hash ở lớp document. SRI không tự bảo vệ service worker script hoặc HTML nếu chúng không được bảo vệ bằng một cơ chế riêng phù hợp.

## 19. Cập nhật dependency và thay hash

Khi nâng cấp thư viện, URL và digest cần thay đổi cùng nhau:

1. Chọn version mới và review release notes/changelog.
2. Cập nhật dependency và lockfile.
3. Build artifact trong CI.
4. Chạy test và kiểm tra artifact.
5. Tính lại digest từ output cuối cùng.
6. Cập nhật manifest/template chứa URL và integrity.
7. Phát hành asset mới trước hoặc cùng thời điểm HTML tham chiếu nó.
8. Xác minh CDN response và browser runtime.
9. Giữ artifact cũ trong giai đoạn chuyển tiếp.

Không cập nhật hash bằng cách tải URL CDN hiện tại rồi tự động chấp nhận digest mới. Nếu CDN đã bị thay đổi, thao tác đó sẽ biến nội dung chưa xác minh thành nội dung được allowlist. Hash phải đến từ artifact đã kiểm tra trong pipeline đáng tin cậy.

## 20. CI/CD: kiểm tra tự động trước release

Pipeline có thể xác minh rằng mọi asset cần pin đều có metadata hợp lệ:

- Manifest không thiếu URL hoặc integrity.
- Prefix thuật toán là SHA-256/384/512.
- Digest là Base64 đúng định dạng và có độ dài phù hợp.
- Hash tính lại từ artifact khớp manifest.
- URL là host/path được phép.
- Asset cross-origin có CORS header đúng.
- HTML production render chứa cùng URL/hash với manifest.
- Không có script/stylesheet quan trọng được thêm động mà thiếu integrity theo policy dự án.
- Không có fallback code tự xóa integrity khi lỗi.

Ví dụ kiểm tra hash trong Node.js:

```js
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { readFileSync } = require("node:fs");

const bytes = readFileSync("dist/assets/vendor.min.js");
const actual = `sha384-${createHash("sha384").update(bytes).digest("base64")}`;
const expected = buildManifest.vendor.integrity;

assert.equal(actual, expected, "SRI metadata does not match release artifact");
```

Đây là ví dụ kiểm tra một artifact. Hệ thống thực tế nên lặp qua manifest và xác minh tất cả asset cần pin, đồng thời kiểm tra HTML render cuối cùng. Không tính hash từ URL production làm nguồn chuẩn duy nhất.

## 21. Kiểm thử runtime và giám sát

Trong browser, kiểm tra:

1. Network request tới đúng URL và version.
2. Response body là đúng asset, không phải HTML error page hoặc redirect bất ngờ.
3. Console không có lỗi integrity, CORS hoặc CSP.
4. Script thực thi và stylesheet được áp dụng như mong đợi.
5. CDN response có CORS header phù hợp.
6. Preload và request tiêu thụ có URL/CORS mode/integrity nhất quán.
7. Cache và service worker trả đúng artifact qua các lần reload/offline.

Có thể theo dõi lỗi thông qua browser test, telemetry và báo cáo lỗi ứng dụng. Không log dữ liệu nhạy cảm trong telemetry. SRI mismatch có thể là dấu hiệu deploy lệch phiên bản, lỗi CDN hoặc sự cố supply chain; cần phân loại và điều tra thay vì tự động bỏ qua.

## 22. Rollback khi SRI mismatch

Khi browser từ chối resource:

- Giữ integrity enforcement; không xóa attribute để “khôi phục nhanh”.
- Xác định release, URL, digest và response thực tế.
- So sánh asset CDN với artifact trong build manifest.
- Nếu asset bị lỗi, khôi phục asset đã xác minh tại URL versioned cũ hoặc phát hành release mới với hash hợp lệ.
- Phát hành HTML/manifest tương ứng; giữ tương thích với HTML cache cũ.
- Kiểm tra CDN cache, service worker và các client còn mở release trước.
- Nếu nghi ngờ bị xâm nhập, dừng phát hành, thu hồi dependency/credential liên quan và xử lý theo incident process.

Không tái sử dụng cùng URL versioned cho nội dung khác. Một URL bất biến giúp rollback và điều tra dễ hơn.

## 23. Các lỗi deployment thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tính hash trước minify | Digest không khớp file phát hành | Tính hash sau bước transform cuối |
| CDN rewrite nội dung | Browser từ chối asset | Tắt rewrite hoặc hash đúng artifact cuối được phục vụ |
| Dùng URL `latest` | HTML và asset có thể lệch version | Pin URL versioned/content-addressed |
| Cập nhật asset nhưng quên HTML | Hash cũ không khớp file mới | Phát hành HTML/manifest cùng release |
| CORS CDN thiếu ACAO | Cross-origin SRI thất bại | Cấu hình CORS cho asset công khai |
| Dùng `use-credentials` không cần thiết | Tăng phụ thuộc credential và cấu hình CORS | Ưu tiên `anonymous` cho asset công khai |
| Tính hash từ CDN live mà không xác minh | Có thể allowlist file đã bị thay đổi | Hash từ artifact build đã review |
| Chỉ pin entrypoint module | Dependency import riêng có thể chưa được pin | Kiểm soát module graph hoặc bundle theo thiết kế |
| Service worker cache file cũ | Client nhận asset lệch HTML | Version cache và đồng bộ lifecycle release |
| Fallback bỏ integrity khi lỗi | File không xác minh có thể được thực thi | Dừng tải, báo lỗi và rollback an toàn |
| Xóa asset cũ ngay khi deploy | HTML cache/tab cũ bị lỗi | Giữ asset cũ trong thời gian chuyển tiếp |
| Nhầm lockfile integrity với SRI HTML | Browser không được bảo vệ runtime | Triển khai cả package verification và SRI khi cần |

## 24. Thực hành kiểm chứng trong môi trường lab

Chỉ sử dụng asset và CDN/domain lab do bạn kiểm soát. Dùng script vô hại, không thử thay đổi tài nguyên của website bên ngoài.

### Bài thử A — Sinh hash từ artifact cuối

1. Tạo `hello.js` và build/minify thành `dist/hello.min.js`.
2. Tính SHA-384 bằng Node.js hoặc OpenSSL.
3. Đặt URL, `integrity` vào trang lab.
4. Tải trang và quan sát script chạy.
5. Thay một byte của file nhưng giữ hash cũ.

**Kỳ vọng:** Artifact ban đầu chạy; artifact đã thay đổi bị browser từ chối. HTTP status thành công không đồng nghĩa SRI thành công.

### Bài thử B — CDN CORS

1. Phục vụ script lab trên origin thứ hai.
2. Gắn `integrity` và `crossorigin="anonymous"`.
3. Bỏ `Access-Control-Allow-Origin` ở response CDN lab.
4. Thêm ACAO phù hợp rồi tải lại.

**Kỳ vọng:** CORS failure và integrity mismatch là hai lỗi riêng; sau khi CORS thành công, browser vẫn xác minh digest.

### Bài thử C — Release manifest

Tạo manifest từ hai asset versioned. Viết bước CI nhỏ tính lại digest từ file trong `dist` và so sánh với manifest. Cố ý sửa manifest hoặc artifact để làm test thất bại.

**Kỳ vọng:** CI dừng release khi hash không khớp; không tự cập nhật hash để che mismatch.

### Bài thử D — Cache release cũ/mới

Phát hành release A, sau đó release B với URL asset khác. Giữ HTML A trong một browser tab và tải HTML B ở tab mới.

**Kỳ vọng:** Hai release vẫn tham chiếu asset/hash tương ứng; asset A không bị ghi đè bởi nội dung B.

### Bài thử E — Script tải động

Tạo script element từ manifest, gán `src`, `integrity`, `crossOrigin` trước khi append. Thử thay hash trong manifest hoặc URL ngoài allowlist.

**Kỳ vọng:** Hash sai bị browser chặn; URL không được allowlist bị ứng dụng từ chối trước khi tạo request.

## 25. Checklist review SRI deployment

- [ ] Đã inventory script, stylesheet và tài nguyên được tạo động.
- [ ] Dependency có version rõ ràng và nguồn artifact được xác minh.
- [ ] Hash được tạo từ artifact cuối cùng sau build/minify.
- [ ] Digest dùng SHA-256/384/512 và Base64 chuẩn.
- [ ] URL và hash được quản lý cùng manifest/release.
- [ ] Asset CDN cross-origin dùng CORS mode phù hợp và có ACAO hợp lệ.
- [ ] Asset công khai ưu tiên `crossorigin="anonymous"`; credentialed CORS chỉ dùng khi có lý do.
- [ ] CSP giới hạn host được tải độc lập với SRI.
- [ ] Module/dependency graph được đánh giá; không giả định hash entrypoint pin toàn graph.
- [ ] Dynamic script/link nhận integrity trước khi append.
- [ ] Preload metadata nhất quán với request tiêu thụ.
- [ ] CDN không rewrite asset sau khi hash được tạo.
- [ ] HTML, manifest, asset và service worker cache được version hóa đồng bộ.
- [ ] CI xác minh digest của artifact và nội dung HTML cuối.
- [ ] Có browser integration test cho hash mismatch, CORS và CSP.
- [ ] Không có fallback tự động bỏ integrity.
- [ ] Rollback giữ được cặp HTML/asset/hash đã xác minh.
- [ ] Có owner theo dõi dependency, CDN và lỗi integrity sau release.

## 26. Câu hỏi tự kiểm tra

1. Vì sao SRI deployment cần quy trình tạo hash từ artifact đã review?
2. Những bước build nào có thể làm thay đổi digest?
3. Vì sao URL versioned tốt hơn alias `latest` khi dùng SRI?
4. Tài nguyên cross-origin cần những điều kiện CORS nào?
5. Lockfile integrity khác browser SRI như thế nào?
6. Vì sao hash entrypoint không mặc nhiên pin mọi dependency module?
7. HTML, manifest và CDN cache cần được phát hành đồng bộ ra sao?
8. Service worker có thể ảnh hưởng việc trả asset đúng version như thế nào?
9. Vì sao không nên tự động bỏ `integrity` khi tải resource thất bại?
10. Khi browser trả lỗi integrity, cần so sánh những artifact/response nào?

## 27. Ghi nhớ

SRI deployment không dừng ở việc thêm thuộc tính `integrity` vào HTML. Cần kiểm kê tài nguyên, pin version, xác minh nguồn dependency, tạo digest từ artifact cuối cùng, quản lý manifest, cấu hình CORS cho CDN và phát hành HTML/asset đồng bộ. Lockfile integrity bảo vệ bước cài package; browser SRI bảo vệ tài nguyên được tải lúc runtime.

Hãy tự động kiểm tra hash trong CI, dùng URL bất biến, kiểm thử module/dynamic resource, đồng bộ cache/service worker và chuẩn bị rollback về artifact đã xác minh. Khi integrity mismatch, điều tra CDN, build và release; không bỏ thuộc tính để cho file chưa xác minh chạy. **SRI chỉ đáng tin khi hash, HTML và artifact cùng bắt nguồn từ một quy trình phát hành có kiểm soát.**
