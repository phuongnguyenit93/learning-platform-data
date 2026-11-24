# Triển khai CSP theo giai đoạn: từ quan sát đến enforce

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Lập inventory script, style, frame, worker, API endpoint và tài nguyên mà ứng dụng tải.
2. Thiết kế Content Security Policy (CSP) theo kiến trúc và threat model.
3. Triển khai Content-Security-Policy-Report-Only để quan sát mà chưa chặn chức năng.
4. Thu thập, phân loại và xử lý violation report mà không làm lộ dữ liệu nhạy cảm.
5. Chuyển dần từ allowlist rộng sang nonce/hash và policy chặt hơn.
6. Kiểm soát third-party script, CDN, analytics, tag manager và nội dung inline.
7. Rollout CSP theo môi trường, route, nhóm người dùng và tỷ lệ traffic.
8. Xác định tiêu chí chuyển từ Report-Only sang enforcement.
9. Giám sát lỗi sau triển khai, rollback an toàn và duy trì policy theo release.
10. Kiểm thử regression bằng DevTools, automated tests và CSP reports.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. CSP là lớp phòng thủ theo hướng allowlist: browser chỉ tải hoặc thực thi những tài nguyên phù hợp policy. Triển khai production cần có inventory, quan sát, xử lý tương thích và rollout có kiểm soát để policy chặt hơn mà không phá chức năng hợp lệ.

## 1. Vì sao cần triển khai CSP theo giai đoạn?

Content Security Policy (CSP) cho phép server khai báo nguồn tài nguyên và một số hành vi mà browser được phép thực hiện trong document. CSP có thể giảm tác động của XSS bằng cách hạn chế script inline, script từ nguồn ngoài, object/plugin, frame và kết nối mạng.

Một policy quá rộng như:

    Content-Security-Policy: default-src * 'unsafe-inline' 'unsafe-eval' data: blob:

gần như làm mất nhiều lợi ích của CSP. Ngược lại, một policy chặt được bật đột ngột trên ứng dụng có nhiều dependency có thể chặn:

- Inline script hoặc style hợp lệ.
- Script do framework hoặc server render.
- API endpoint của backend.
- Font, image, media và worker.
- iframe thanh toán, đăng nhập hoặc hỗ trợ khách hàng.
- Tài nguyên CDN và tag manager.
- Luồng upload, download hoặc preview.

Vì vậy, triển khai CSP là một thay đổi vận hành. Cần biết ứng dụng đang tải gì, policy sẽ ảnh hưởng route nào, report được thu thập ra sao, ai xử lý violation và tiêu chí nào cho phép chuyển sang enforcement.

### Hai chế độ chính

| Chế độ | Header | Hành vi |
| --- | --- | --- |
| Report-Only | Content-Security-Policy-Report-Only | Browser báo cáo vi phạm nhưng không chặn tài nguyên vì policy này |
| Enforce | Content-Security-Policy | Browser áp dụng policy và chặn hành vi vi phạm |

Có thể triển khai cả hai header cùng lúc: policy enforce đang bảo vệ ứng dụng, policy Report-Only quan sát policy nghiêm ngặt hơn cho giai đoạn tiếp theo.

Report-Only không phải biện pháp bảo vệ thay thế enforcement. Nó chỉ giúp quan sát trước khi bật policy thật.

## 2. Lộ trình triển khai

Một rollout điển hình gồm các giai đoạn:

    Inventory
       |
       v
    Baseline và threat model
       |
       v
    Report-Only trên staging
       |
       v
    Triage violation và sửa nguồn hợp lệ
       |
       v
    Canary Report-Only trên production
       |
       v
    Enforce policy nền tảng trên canary
       |
       v
    Mở rộng theo route/traffic
       |
       v
    Giám sát, regression và siết policy định kỳ

Không chuyển giai đoạn chỉ vì đã hết một khoảng thời gian. Chỉ chuyển khi có bằng chứng rằng policy phản ánh dependency hợp lệ, report đủ chất lượng và các luồng quan trọng đã được kiểm thử.

### Vai trò cần tham gia

| Vai trò | Trách nhiệm |
| --- | --- |
| Application developer | Inventory source, sửa inline code và dependency |
| Platform/DevOps | Cấu hình response header tại app, reverse proxy hoặc CDN |
| Security engineer | Thiết kế policy, threat model và review exception |
| QA | Kiểm tra luồng nghiệp vụ và browser compatibility |
| SRE/Operations | Theo dõi error rate, report volume và rollback |
| Privacy/Data protection | Review dữ liệu trong violation report và retention |

## 3. Giai đoạn 0 — Xác định phạm vi và baseline

Trước khi viết policy, xác định ứng dụng, origin và luồng cần bảo vệ.

### Inventory theo route

Lập danh sách:

- Trang đăng nhập, đăng xuất và callback.
- Trang dashboard và các route SPA.
- Trang quản trị.
- Trang có form, upload, download hoặc preview.
- Trang nhúng iframe hoặc được nhúng bởi website khác.
- Trang thanh toán, identity provider hoặc third-party widget.
- Trang lỗi, maintenance và static content.

Một origin có thể phục vụ nhiều ứng dụng hoặc nhiều loại document. Không áp một policy duy nhất nếu các route có trust boundary khác nhau.

### Inventory tài nguyên

Với mỗi route, ghi lại:

| Nhóm | Ví dụ cần tìm |
| --- | --- |
| Script | External script, inline script, module, dynamic import |
| Style | Stylesheet, inline style, style attribute, CSS-in-JS |
| Image | CDN, data URL, blob URL, avatar |
| Font | Font CDN và font tự host |
| Connect | Fetch, XHR, WebSocket, EventSource, beacon |
| Frame | Identity provider, payment, support widget |
| Worker | Dedicated worker, shared worker, service worker |
| Media | Audio, video và MediaSource |
| Object | PDF/object/embed nếu ứng dụng còn dùng |
| Form | Form action và redirect |
| Base URL | Thẻ base và URL resolution |

### Thu thập baseline từ browser

1. Mở từng route trên staging.
2. Mở DevTools → Network.
3. Bật Preserve log.
4. Thực hiện đầy đủ các thao tác nghiệp vụ.
5. Lọc theo loại tài nguyên và host.
6. Ghi nhận redirect, dynamic request và tài nguyên chỉ xuất hiện sau tương tác.
7. Kiểm tra Console để tìm lỗi CSP hiện có.

Network log chỉ phản ánh những luồng đã chạy trong phiên kiểm thử. Nó không thay thế inventory code hoặc kiểm thử các tính năng ít dùng.

### Đo baseline lỗi chức năng

Ghi nhận trước triển khai:

- Tỷ lệ lỗi JavaScript.
- Tỷ lệ lỗi API.
- Tỷ lệ đăng nhập/callback thành công.
- Lỗi thanh toán, upload và download.
- Lỗi iframe/widget.
- Tỷ lệ lỗi frontend theo browser.
- Error rate và latency ở backend.

Baseline giúp phân biệt lỗi đã tồn tại với lỗi xuất hiện sau khi CSP được bật.

## 4. Giai đoạn 1 — Thiết kế policy nền tảng

Policy cần bắt đầu từ yêu cầu thật của ứng dụng, không sao chép một header mẫu rồi bật production.

### Các directive thường dùng

| Directive | Kiểm soát | Ví dụ |
| --- | --- | --- |
| default-src | Fallback cho nhiều loại tài nguyên | default-src 'self' |
| script-src | Script và nguồn thực thi script | script-src 'self' |
| style-src | Stylesheet và một số style source | style-src 'self' |
| img-src | Ảnh | img-src 'self' data: |
| font-src | Font | font-src 'self' |
| connect-src | Fetch, XHR, WebSocket, EventSource và beacon | connect-src 'self' |
| frame-src | Nguồn document được nhúng | frame-src 'self' |
| frame-ancestors | Ai được phép nhúng document hiện tại | frame-ancestors 'none' |
| object-src | object, embed và plugin content | object-src 'none' |
| base-uri | URL base hợp lệ | base-uri 'self' |
| form-action | Nơi form được submit | form-action 'self' |
| worker-src | Worker source | worker-src 'self' |
| media-src | Audio và video | media-src 'self' |
| manifest-src | Web app manifest | manifest-src 'self' |
| upgrade-insecure-requests | Nâng request HTTP lên HTTPS trong phạm vi hỗ trợ | upgrade-insecure-requests |

### Directive không có fallback từ default-src

Không giả định default-src 'self' tự kiểm soát mọi hành vi. Một số directive như base-uri, form-action và frame-ancestors không fallback từ default-src. Khai báo riêng các directive quan trọng này.

### Policy nền tảng tham khảo

Với ứng dụng server-rendered đơn giản, policy khởi đầu có thể gần như:

    Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; worker-src 'self'

Đây chỉ là ví dụ để bắt đầu inventory. Ứng dụng thật có thể cần nonce/hash, CDN cụ thể, API host, iframe provider, blob: hoặc policy khác theo từng route.

### Không mở rộng wildcard để làm biến mất report

Không xử lý violation bằng cách thêm:

- * vào mọi directive.
- unsafe-inline cho script.
- unsafe-eval mà không có đánh giá.
- data: hoặc blob: vào default-src.
- Domain CDN rộng hơn nhu cầu.

Mỗi exception phải có owner, lý do, phạm vi, ngày review và kế hoạch loại bỏ nếu có thể.

## 5. Giai đoạn 2 — Bật Report-Only trên staging

Report-Only cho phép quan sát những hành vi mà policy dự kiến sẽ chặn.

Ví dụ:

    Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; report-to csp-endpoint; report-uri /csp-report

report-to dùng Reporting API và tên group được khai báo qua response header Reporting-Endpoints. report-uri là cơ chế cũ hơn nhưng vẫn hữu ích làm fallback trên browser còn hỗ trợ. Kiểm tra browser mục tiêu và định dạng report thực tế.

### Khai báo reporting endpoint

Ví dụ response header:

    Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"

Endpoint nhận report phải:

- Chỉ nhận phương thức và content type cần thiết.
- Giới hạn kích thước body và tốc độ request.
- Không yêu cầu session cookie người dùng để nhận report.
- Không phản chiếu report vào HTML hoặc thực thi nội dung report.
- Redact query/token và dữ liệu nhạy cảm trước khi lưu.
- Có retention và access control rõ ràng.

### CSP report có thể chứa dữ liệu nhạy cảm

Report có thể chứa document-uri, blocked-uri, source-file, line number, directive và sample code tùy browser/policy. URL có thể mang query parameter chứa email, token hoặc mã định danh. Nếu thêm keyword report-sample vào script-src hoặc style-src, browser hỗ trợ có thể đưa một đoạn code inline vào report.

Không bật report-sample rộng rãi nếu chưa đánh giá privacy. Redact URL query/fragment, không lưu raw report lâu hơn cần thiết và giới hạn người được xem.

### Kiểm tra endpoint trước khi rollout

1. Gửi report test từ staging.
2. Xác nhận endpoint nhận được payload.
3. Kiểm tra parser hỗ trợ định dạng report browser thực gửi.
4. Xác nhận report không bị lưu như HTML có thể thực thi.
5. Kiểm tra rate limit và chống spam.
6. Kiểm tra dữ liệu nhạy cảm đã được redaction.

## 6. Giai đoạn 3 — Phân loại violation report

Không phải mọi violation đều là XSS hoặc tấn công. Report-Only thường phát hiện cả dependency hợp lệ chưa được đưa vào policy.

### Nhóm nguyên nhân

| Nhóm | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Dependency hợp lệ | Script/style từ CDN hoặc provider đã phê duyệt | Xác minh owner và scope; ưu tiên self-host hoặc nonce/hash |
| Inline code hợp lệ | Script do template/framework sinh | Chuyển sang external file, nonce hoặc hash |
| Dynamic code | eval, Function hoặc string timer | Loại bỏ hoặc thay bằng code/data API |
| Third-party widget | iframe/script từ nhà cung cấp | Xác minh hợp đồng, origin và nhu cầu; sandbox khi phù hợp |
| Tài nguyên không dùng | Request từ tính năng cũ hoặc dependency thừa | Xóa dependency và code path |
| Extension/browser injection | Source từ extension hoặc browser tool | Xác minh môi trường và không thêm extension vào allowlist production |
| Scanner/test | Request do QA hoặc security scanner tạo | Gắn nhãn test và tách khỏi traffic người dùng |
| Attack/noise | Host lạ, scheme lạ hoặc payload bất thường | Điều tra; không allowlist chỉ để dập report |
| Browser compatibility | Hành vi khác giữa browser/version | Tái hiện và xác định directive/API liên quan |

### Triage theo từng report

Với mỗi nhóm violation:

1. Xác định route và browser.
2. Xác định directive bị vi phạm.
3. Xác định resource hoặc inline code bị chặn/được báo cáo.
4. Xác định initiator và tính năng tương ứng.
5. Xác minh owner và nguồn tài nguyên.
6. Phân loại hợp lệ, không cần thiết, test noise hay đáng ngờ.
7. Ghi quyết định: sửa code, thêm exception có giới hạn hoặc điều tra.
8. Thêm regression test.

### Không allowlist theo blocked-uri một cách tự động

Attacker có thể khiến trang yêu cầu URL độc hại. Nếu pipeline tự thêm mọi blocked-uri vào script-src hoặc connect-src, report trở thành kênh mở rộng policy cho attacker.

Mọi nguồn mới phải được xác minh độc lập, có owner và lý do nghiệp vụ.

### Nhóm report thay vì xử lý từng event

Một trang có thể phát hàng nghìn report giống nhau. Gom nhóm theo:

- document-uri đã chuẩn hóa.
- effective-directive.
- blocked-uri đã redaction.
- source-file và line number khi hữu ích.
- browser family/version.
- release/build.
- user cohort hoặc route group.

Không dùng full URL có token làm group key.

## 7. Giai đoạn 4 — Sửa ứng dụng để giảm exception

Trước khi enforce, giảm dependency vào inline code và nguồn rộng.

### Chuyển inline script thành file ngoài

Trước:

    <script>
      initializeApplication();
    </script>

Sau:

    <script src="/assets/app.js" defer></script>

Nếu script cần dữ liệu server, truyền qua JSON serialization an toàn hoặc data structure đã encode phù hợp. Không nối dữ liệu người dùng vào JavaScript source.

### Dùng nonce cho script inline cần thiết

Server sinh nonce ngẫu nhiên, khó đoán cho từng response và gắn vào CSP header cùng các script hợp lệ:

    Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'

HTML:

    <script nonce="RANDOM_PER_RESPONSE">
      initializeApplication();
    </script>

Nonce phải:

- Được sinh bằng bộ sinh số ngẫu nhiên mật mã.
- Khác nhau giữa các response document.
- Không tái sử dụng cố định trong template hoặc config.
- Được gắn vào đúng script được tin cậy.
- Không bị lộ qua log hoặc telemetry không cần thiết.

### Cache và nonce

Nếu HTML chứa nonce nhưng CDN cache HTML lâu, nonce có thể bị tái sử dụng giữa người dùng hoặc response. Thiết kế cache phải bảo đảm nonce được sinh và phân phối đúng. Có thể dùng dynamic HTML, edge substitution được thiết kế an toàn hoặc hash cho script tĩnh.

Không tạo nonce ở client sau khi trang đã tải; browser cần nonce trong response policy và markup ngay từ đầu.

### Dùng hash cho inline script tĩnh

Hash phù hợp khi nội dung inline ổn định:

    Content-Security-Policy: script-src 'self' 'sha256-BASE64_HASH'; object-src 'none'; base-uri 'self'

Hash phải khớp chính xác bytes nội dung script theo quy tắc CSP. Chỉ một thay đổi khoảng trắng hoặc ký tự có thể làm hash không còn khớp.

Hash phù hợp với snippet tĩnh; nonce thường thuận tiện hơn cho script inline động do server sinh.

### Hạn chế unsafe-inline và unsafe-eval

unsafe-inline cho phép nhiều dạng inline script/style tùy directive và browser behavior, làm giảm khả năng CSP ngăn XSS. unsafe-eval cho phép một số cơ chế tạo code từ chuỗi như eval/Function.

Không giữ các keyword này như giải pháp lâu dài chỉ vì framework cũ cần chúng. Tìm cách cập nhật framework, thay dynamic code hoặc cô lập legacy route.

## 8. Giai đoạn 5 — Thiết kế script-src hiện đại

### Nonce-based policy

Ví dụ:

    Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'

Browser cho phép script có nonce khớp với policy. Script ngoài cùng origin nhưng không có nonce vẫn chịu quy tắc script-src; nonce không phải cơ chế cấp quyền cho mọi tài nguyên.

Lưu ý: thêm self vào script-src cũng cho phép các script cùng origin đáp ứng nguồn đó. Nếu ứng dụng có endpoint cùng origin có thể trả JavaScript không tin cậy, file upload được render như script hoặc JSONP cũ, self có thể làm policy yếu đi. Chỉ giữ self sau khi review toàn bộ script path; với kiến trúc phù hợp, cân nhắc policy nonce/hash kết hợp strict-dynamic mà không cần host source rộng.

### Hash-based policy

Hash cho phép script có nội dung đúng hash. Phù hợp với script inline cố định hoặc một số mô hình static build.

### strict-dynamic

strict-dynamic cho phép trust được truyền từ script có nonce/hash sang script mà script đó tải động trong browser hỗ trợ CSP Level 3.

Ví dụ:

    Content-Security-Policy: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic'; object-src 'none'; base-uri 'none'

Khi dùng strict-dynamic, cần hiểu cách browser hiện đại xử lý host allowlist và fallback ở browser cũ. Không thêm strict-dynamic chỉ để làm biến mất report; kiểm tra loader script, dependency chain và nguồn dữ liệu điều khiển URL script.

### Script loader có thể trở thành trust boundary

Nếu script có nonce tải script URL do dữ liệu người dùng kiểm soát, attacker có thể lợi dụng loader đáng tin để tải mã ngoài ý muốn. Validate URL, dùng manifest/allowlist cho dependency và tránh biến dữ liệu page thành script source.

### Không dùng nonce như secret ứng dụng

Nonce CSP chỉ chứng minh script được server cho phép trong response. Nó không phải token đăng nhập, CSRF token hoặc credential để gọi API.

## 9. Style, image, font, media và worker

Không tập trung script-src mà bỏ qua các directive khác.

### style-src

Inventory stylesheet, style attribute, CSS-in-JS và framework runtime. Ưu tiên external stylesheet, nonce hoặc hash theo hỗ trợ browser. Tránh unsafe-inline nếu không cần.

### img-src

Chỉ thêm CDN, data: hoặc blob: nếu ứng dụng thật sự cần. Avatar URL do người dùng cung cấp cần được kiểm tra và có thể proxy/rasterize theo threat model.

### font-src

Liệt kê nguồn font thực tế. Không thêm wildcard chỉ vì font CDN đổi host theo môi trường; dùng domain ổn định hoặc self-host.

### media-src

Kiểm tra audio/video, MediaSource và Blob URL. Nếu cần blob:, chỉ thêm vào media-src.

### worker-src

Kiểm tra Worker, SharedWorker và Service Worker. Nếu ứng dụng tạo Worker từ Blob URL, policy có thể cần blob: trong worker-src. Không mở blob: trong script-src một cách rộng rãi chỉ để sửa lỗi Worker.

Service Worker có yêu cầu script URL cùng origin và không được khởi tạo từ Blob URL hoặc data URL. Ví dụ blob: trong worker-src áp dụng cho loại Worker phù hợp như Dedicated Worker; không dùng nó để thiết kế Service Worker từ mã Blob.

### connect-src

Inventory:

- API origin.
- WebSocket endpoint.
- EventSource.
- beacon/telemetry.
- GraphQL endpoint.
- Web worker fetch nếu áp dụng.

Dùng scheme và host chính xác. WebSocket có thể dùng wss:; không dùng wildcard scheme nếu không cần.

## 10. Third-party script, CDN và tag manager

Third-party script chạy trong context trang thường có thể đọc DOM và thao tác theo quyền origin của document. Việc đưa một host vào script-src là quyết định trust, không chỉ là thao tác tương thích.

### Inventory dependency

Với mỗi provider, ghi:

- Tên nhà cung cấp và owner nội bộ.
- Script URL và redirect chain.
- Tính năng sử dụng.
- Dữ liệu script có thể đọc.
- Có dynamic script loader hay không.
- Có SRI hoặc cơ chế integrity phù hợp không.
- Cách cập nhật và kiểm soát phiên bản.
- Kế hoạch khi provider gặp sự cố.

### Ưu tiên self-host khi phù hợp

Self-host có thể giúp kiểm soát phiên bản và nguồn tải, nhưng cần quy trình cập nhật dependency và scan. Không tự động copy script bên thứ ba về rồi bỏ qua update/security advisory.

### Subresource Integrity

SRI có thể xác minh bytes của một số tài nguyên script/style external:

    <script src="https://cdn.example.test/library.min.js"
            integrity="sha384-BASE64_HASH"
            crossorigin="anonymous"></script>

SRI không thay CSP. CSP giới hạn nguồn; SRI xác minh nội dung của tài nguyên theo hash đã khai báo. Với tài nguyên thay đổi thường xuyên, cần quy trình cập nhật hash.

### Tag manager

Tag manager có thể tải thêm script động và thay đổi dependency mà không cần release ứng dụng. Hạn chế quyền publish, yêu cầu review, tách môi trường và audit thay đổi. Không cho phép tag manager trở thành đường tải script tùy ý mà không có kiểm soát.

## 11. Frame, form và navigation

### frame-src

Kiểm soát nguồn iframe mà trang có thể nhúng. Liệt kê provider cụ thể cho identity, payment, support hoặc video.

### frame-ancestors

Kiểm soát website nào được phép nhúng document hiện tại. Nếu không cần embed:

    Content-Security-Policy: frame-ancestors 'none'

Nếu cần nhúng từ parent cụ thể:

    Content-Security-Policy: frame-ancestors 'self' https://portal.example.test

frame-ancestors không được cấu hình qua meta element; cần gửi qua HTTP response header.

Có thể đưa frame-ancestors vào Content-Security-Policy-Report-Only để quan sát parent không phù hợp mà chưa chặn việc nhúng. Khi đã xác minh danh sách parent hợp lệ, chuyển directive sang Content-Security-Policy enforce để browser thực sự chặn embedding ngoài allowlist.

### form-action

Giới hạn nơi form được submit:

    Content-Security-Policy: form-action 'self'

Nếu có payment/identity provider, chỉ cho phép endpoint cần thiết và kiểm tra redirect flow.

### base-uri

Giới hạn URL base:

    Content-Security-Policy: base-uri 'self'

Hoặc 'none' nếu ứng dụng không dùng base element. Directive này giúp giảm rủi ro base tag injection thay đổi URL tương đối.

## 12. Reporting API và xử lý dữ liệu report

### Hai cơ chế report

report-uri là directive CSP đời cũ, hiện được xem là deprecated trong CSP mới nhưng vẫn có thể được browser hỗ trợ. report-to sử dụng Reporting API và endpoint group được khai báo qua Reporting-Endpoints.

Ví dụ:

    Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"

    Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-to csp-endpoint; report-uri /csp-report

Hỗ trợ thực tế và định dạng payload khác nhau theo browser/version. Duy trì parser tương thích với các dạng report cần hỗ trợ và kiểm thử từ browser mục tiêu.

### Endpoint phải chống abuse

- Giới hạn body size.
- Rate limit theo nguồn và route phù hợp.
- Xử lý JSON và content type an toàn.
- Không render report body trực tiếp vào dashboard HTML.
- Không follow URL trong report.
- Không fetch blocked-uri thay người gửi.
- Không ghi raw body vào log ứng dụng không redaction.
- Tách quyền xem report khỏi quyền vận hành ứng dụng.

### Chuẩn hóa và redaction

Trước khi lưu hoặc hiển thị:

1. Loại query/fragment có thể chứa token.
2. Che username/password nếu URL có userinfo.
3. Chuẩn hóa URL theo policy privacy.
4. Giới hạn độ dài các field.
5. Escape nội dung khi hiển thị dashboard.
6. Giữ build ID và directive để điều tra.

### Báo cáo có thể bị giả mạo

Endpoint public có thể nhận request do client hoặc attacker tạo. Không coi report là bằng chứng tuyệt đối rằng browser thật đã chặn một hành vi. Dùng report như tín hiệu để điều tra, đối chiếu telemetry, build và reproduction.

### Tránh report storm

Một lỗi có thể phát report trên mọi page view. Dùng sampling, aggregation, deduplication và alert threshold. Không drop toàn bộ report mà không giữ số liệu tổng hợp; cần biết mức độ phổ biến và trend.

## 13. Giai đoạn 6 — Canary Report-Only trên production

Sau khi staging đã được kiểm thử, bật Report-Only trên một phạm vi nhỏ của production.

Có thể rollout theo:

- Một route ít rủi ro trước.
- Một nhóm người dùng nội bộ.
- Một tỷ lệ traffic nhỏ.
- Một browser/version cụ thể nếu cần chẩn đoán compatibility.
- Một tenant test được kiểm soát.

### Cách triển khai

1. Gắn policy Report-Only vào response của nhóm canary.
2. Gắn release/build ID vào telemetry phù hợp.
3. Theo dõi report theo route, directive và browser.
4. Đối chiếu error rate với baseline.
5. Triage nguồn hợp lệ và bất thường.
6. Sửa code/dependency.
7. Lặp lại cho đến khi không còn violation hợp lệ chưa xử lý.

### Tiêu chí rời Report-Only

- Các route trọng yếu đã được inventory.
- Luồng đăng nhập, callback và logout hoạt động.
- Các luồng thanh toán, upload, download và iframe được kiểm tra.
- Report endpoint nhận và redaction đúng.
- Không còn nguồn script không rõ owner.
- Violation hợp lệ đã có cách xử lý hoặc exception được phê duyệt.
- Error rate không tăng bất thường.
- Rollback đã được thử trên staging.

Không yêu cầu số report bằng zero trong mọi trường hợp. Extension, browser tool, scanner hoặc tài nguyên không liên quan có thể tạo noise. Cần phân loại và hiểu nguồn noise thay vì thêm allowlist rộng.

## 14. Giai đoạn 7 — Enforce trên staging

Khi policy đã ổn định, chuyển từ Report-Only sang Content-Security-Policy trên staging.

### Thực hiện

1. Giữ report endpoint để quan sát violation khi enforce.
2. Bật header enforce với policy đã review.
3. Chạy toàn bộ test suite.
4. Mở các route và thao tác thủ công.
5. Kiểm tra Console, Network và CSP reports.
6. Thử browser được hỗ trợ.
7. Kiểm tra fallback và error handling.

### Enforce và Report-Only có thể chạy cùng lúc

Ví dụ:

    Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'

    Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; report-to csp-endpoint

Header thứ nhất bảo vệ hiện tại. Header thứ hai quan sát policy thử nghiệm nghiêm ngặt hơn. Khi đọc report, xác định report thuộc policy nào và route/build nào.

### Nhiều CSP policy

Nếu response có nhiều Content-Security-Policy header hoặc nhiều policy được khai báo, browser áp dụng đồng thời theo quy tắc CSP; policy bổ sung thường làm giới hạn chặt hơn. Không kỳ vọng header thứ hai ghi đè header thứ nhất.

Kiểm tra header tại response cuối cùng sau reverse proxy/CDN. Một lớp hạ tầng có thể thêm header ngoài ý muốn khiến ứng dụng bị chặn dù cấu hình tại app đúng.

### Meta CSP có giới hạn

CSP qua meta element không hỗ trợ mọi directive và chỉ có hiệu lực sau khi browser parse meta. Các directive như frame-ancestors, report-uri và một số tính năng không thể thay thế HTTP response header. Production nên dùng response header.

## 15. Giai đoạn 8 — Canary enforcement trên production

Không bật policy mới cho toàn bộ traffic trong một lần nếu ứng dụng có nhiều route hoặc dependency.

### Kế hoạch canary

Ví dụ rollout:

| Đợt | Phạm vi minh họa | Mục tiêu |
| --- | --- | --- |
| 1 | Internal users | Phát hiện lỗi chức năng sớm |
| 2 | 1–5% traffic | Kiểm tra hành vi thực tế |
| 3 | 10–25% traffic | Đánh giá độ ổn định và browser mix |
| 4 | 50% traffic | Xác nhận không có lỗi hệ thống |
| 5 | 100% traffic | Hoàn tất rollout |

Tỷ lệ thực tế tùy kiến trúc, năng lực routing và mức độ rủi ro. Có thể rollout theo route hoặc tenant thay vì random traffic.

### Theo dõi trong từng đợt

- CSP violation rate theo directive.
- JavaScript error rate.
- API failure rate.
- Login/callback success rate.
- Payment/upload/download success.
- Iframe/widget load success.
- Frontend performance.
- Support ticket và user feedback.

### Tiêu chí dừng rollout

Tạm dừng hoặc rollback nếu:

- Luồng đăng nhập hoặc callback thất bại tăng.
- Trang trắng do script hợp lệ bị chặn.
- API hoặc WebSocket thiết yếu bị chặn.
- Thanh toán, upload hoặc download bị lỗi.
- Third-party identity/widget không hoạt động.
- CSP report tăng đột biến chưa giải thích được.
- Error rate vượt ngưỡng vận hành đã định.

Không tắt CSP toàn hệ thống chỉ vì một report đơn lẻ. Xác định route, directive và tài nguyên bị ảnh hưởng trước.

## 16. Rollback và xử lý sự cố

Rollback cần được chuẩn bị trước khi enforce.

### Thiết kế rollback

- Lưu policy version trong source/config.
- Biết header được phát ở app, gateway hay CDN.
- Có thể revert về policy enforce trước đó.
- Có người sở hữu thay đổi và người phê duyệt.
- Kiểm thử rollback ở staging.
- Có dashboard và alert cho error rate.

### Khi phát hiện lỗi sau rollout

1. Xác định cohort/route/build bị ảnh hưởng.
2. Kiểm tra response header thực tế từ browser.
3. Xem Console CSP violation.
4. Xem Network request bị blocked.
5. Xác định directive và resource.
6. Đối chiếu với dependency inventory.
7. Nếu lỗi nghiêm trọng, rollback về policy đã biết là hoạt động được.
8. Tạo regression test và sửa policy/code.
9. Rollout lại qua canary.

### Không rollback bằng cách mở mọi nguồn

Không sửa nhanh bằng:

    script-src *

hoặc:

    script-src 'unsafe-inline' 'unsafe-eval' *

Cách này có thể làm mất mục tiêu bảo vệ. Nếu cần khôi phục dịch vụ, dùng policy trước đó đã được phê duyệt, sau đó điều tra và sửa nguồn gây lỗi.

### Incident response khi nghi có XSS

Nếu CSP report hoặc telemetry cho thấy script lạ:

- Giữ nguyên bằng chứng đã redaction.
- Xác định nguồn và route.
- Kiểm tra script loader và dependency.
- Kiểm tra thay đổi tag manager/CDN.
- Kiểm tra server response và template injection.
- Thu hồi hoặc cập nhật dependency bị compromise.
- Không allowlist nguồn chỉ để giảm alert.
- Đánh giá dữ liệu và session có thể bị ảnh hưởng.

## 17. Vận hành policy qua CDN, proxy và nhiều ứng dụng

Header có thể được tạo tại nhiều lớp:

    Application
       |
       v
    Reverse proxy / API gateway
       |
       v
    CDN / edge
       |
       v
    Browser

Nếu mỗi lớp thêm hoặc sửa CSP, policy cuối có thể khác cấu hình trong code.

### Xác định nguồn sở hữu header

Quyết định một nguồn authoritative hoặc quy trình merge rõ ràng. Tránh app và CDN cùng thêm policy không được phối hợp.

### Cache variation

Nếu policy có nonce theo response, cache phải giữ đúng quan hệ giữa header và HTML. Không cache header nonce khác với nonce trong markup. Không phục vụ một HTML chứa nonce cho nhiều người dùng nếu kiến trúc yêu cầu nonce riêng mỗi response.

### Nhiều ứng dụng cùng host

Nếu nhiều app dùng chung origin, CSP của document vẫn áp dụng cho document hiện tại nhưng cấu hình ở gateway có thể vô tình tác động tất cả route. Tách policy theo route/app hoặc origin khi trust boundary khác nhau.

### Error page và redirect

Kiểm tra CSP trên:

- Response HTML thành công.
- Error page.
- Login redirect/callback.
- Trang maintenance.
- Trang download/preview nếu là document.

Không phải mọi response đều cần cùng CSP, nhưng cần policy rõ cho document có thể render HTML.

## 18. Browser compatibility và fallback

CSP có mức hỗ trợ khác nhau theo browser/version. Một số directive mới hoặc cách report có thể khác.

### Ma trận browser

Ghi nhận:

- Chrome/Chromium version.
- Firefox version.
- Safari/WebKit version.
- Edge version.
- Embedded webview nếu sản phẩm hỗ trợ.
- Browser enterprise policy nếu có.

### Progressive policy

Thiết kế policy sao cho browser hiện đại nhận được cơ chế mạnh hơn như nonce/hash/strict-dynamic, còn browser cũ có fallback hợp lý nếu cần. Không để fallback cũ vô tình mở rộng policy trong browser mới.

### Report endpoint khác nhau

Một browser có thể gửi report theo Reporting API, browser khác hỗ trợ report-uri hoặc định dạng khác. Parser cần tolerant nhưng không được tin payload. Kiểm thử endpoint bằng browser thực tế, không chỉ gửi JSON tự tạo.

### Feature không hỗ trợ

Nếu một browser không hỗ trợ directive, browser có thể bỏ qua directive đó. Xác định browser tối thiểu và không coi directive chưa được hỗ trợ là lớp bảo vệ đã hoạt động.

## 19. CSP và các cơ chế bảo vệ liên quan

CSP là một lớp trong defense-in-depth.

| Cơ chế | Vai trò | CSP có thay thế không? |
| --- | --- | --- |
| Output encoding | Ngăn dữ liệu bị parse thành markup/code sai context | Không |
| HTML sanitization | Cho phép tập HTML an toàn có kiểm soát | Không |
| Trusted Types | Kiểm soát DOM injection sink | Không |
| HttpOnly cookie | Ngăn page JavaScript đọc cookie value | Không |
| SameSite/CSRF token | Giảm request giả mạo dùng cookie | Không |
| SRI | Kiểm tra integrity của tài nguyên external hỗ trợ | Không |
| X-Content-Type-Options | Giảm MIME sniffing trong ngữ cảnh hỗ trợ | Không |
| frame-ancestors | Chống document bị nhúng trái phép | Là một phần CSP |

### CSP không phải bộ lọc HTML

Nếu ứng dụng chèn dữ liệu không tin cậy bằng innerHTML, sink vẫn nguy hiểm. CSP có thể chặn một số cách thực thi nhưng không bảo đảm mọi injection đều vô hại.

### Kết hợp Trusted Types

Ứng dụng hỗ trợ có thể dùng:

    Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html

Policy Trusted Types phải dùng sanitizer thật và được review. Không tạo default policy trả input nguyên trạng chỉ để tránh lỗi.

### Kết hợp SRI

Với script/style external tĩnh từ CDN, SRI giúp xác minh bytes. CSP vẫn giới hạn nguồn; SRI bổ sung integrity. Cả hai cần quy trình cập nhật dependency.

## 20. Dashboard và chỉ số vận hành

Không đánh giá rollout chỉ bằng số lượng report thô.

### Chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| Violation count | Số report nhận được |
| Unique violation groups | Số nhóm lỗi sau deduplication |
| Violation rate per page view | Tỷ lệ vi phạm theo traffic |
| Enforced blocked count | Hành vi thực sự bị chặn bởi enforce policy nếu đo được |
| Unknown source count | Nguồn chưa xác định owner |
| Critical route failure | Lỗi trên login/payment/core workflow |
| JS error rate | Lỗi JavaScript sau rollout |
| API error rate | Request thiết yếu thất bại |
| Browser coverage | Tỷ lệ traffic đã quan sát theo browser |
| Remediation age | Thời gian xử lý violation |

### Alert

Tạo alert khi:

- Violation mới từ script source không được phê duyệt.
- Tỷ lệ blocked resource trên route trọng yếu tăng.
- Login hoặc payment success giảm.
- Một release tạo ra spike report bất thường.
- Report endpoint bị flood hoặc tăng payload lỗi.

Alert cần có owner, severity và runbook. Không gửi raw report có query/token vào kênh chat rộng.

### Review định kỳ

Mỗi release hoặc chu kỳ vận hành:

1. So sánh CSP header trước/sau.
2. Review permission/exception mới.
3. Xác định host không còn dùng.
4. Kiểm tra dependency update.
5. Xem violation trend.
6. Xóa exception đã hết nhu cầu.
7. Chạy regression test.

## 21. Runbook triển khai CSP

### Trước triển khai

- [ ] Xác định owner và route scope.
- [ ] Hoàn tất inventory script/style/connect/frame/worker/media.
- [ ] Xác định third-party provider và owner.
- [ ] Chụp baseline error rate và workflow success.
- [ ] Thiết kế policy version và report endpoint.
- [ ] Review privacy, redaction, retention và access control.
- [ ] Kiểm thử report parser và rate limit.
- [ ] Chuẩn bị rollback.

### Trong Report-Only

- [ ] Bật policy trên staging.
- [ ] Chạy luồng nghiệp vụ đầy đủ.
- [ ] Bật canary Report-Only production.
- [ ] Deduplicate và phân loại report.
- [ ] Sửa inline code và dependency không cần thiết.
- [ ] Không tự động allowlist blocked-uri.
- [ ] Kiểm tra browser compatibility.

### Trước enforcement

- [ ] Policy đã được review bởi security và application owner.
- [ ] Nonce/hash được tạo đúng và không bị cache sai.
- [ ] Không còn exception không có owner.
- [ ] Critical workflow pass trên browser hỗ trợ.
- [ ] Report endpoint và dashboard hoạt động.
- [ ] Rollback đã thử thành công.

### Sau enforcement

- [ ] Canary trước khi mở rộng.
- [ ] Theo dõi JS/API/core workflow error.
- [ ] Triage violation mới.
- [ ] Dừng rollout khi vượt ngưỡng.
- [ ] Ghi policy version và thời điểm thay đổi.
- [ ] Chạy regression và review định kỳ.

## 22. Ma trận kiểm thử

| Ca kiểm thử | Cấu hình/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Report-Only cơ bản | Tài nguyên ngoài policy được yêu cầu | Report được gửi; tài nguyên không bị chặn bởi Report-Only |
| Enforce cơ bản | Tài nguyên ngoài policy được yêu cầu | Browser chặn tài nguyên theo directive |
| Enforce + Report-Only | Hai policy cùng response | Enforce policy chặn; Report-Only chỉ quan sát policy thử nghiệm |
| Script same-origin | script-src 'self' | Script cùng origin được tải theo policy |
| Inline script không nonce/hash | Enforce nonce/hash policy | Script bị chặn |
| Inline script có nonce | Nonce khớp response | Script được phép theo policy |
| Nonce tái sử dụng | Kiểm tra nhiều response | Không tái sử dụng nonce cố định |
| Hash mismatch | Thay đổi một byte script | Script không khớp hash bị chặn |
| unsafe-eval | Code gọi eval trong policy không cho phép | Browser chặn hành vi theo CSP |
| strict-dynamic | Nonce script tải child script | Hành vi đúng theo CSP3 và browser mục tiêu |
| connect-src | Fetch/WebSocket tới host ngoài allowlist | Request bị chặn |
| frame-src | Nhúng provider được phép/không được phép | Chỉ nguồn được cho phép được nhúng |
| frame-ancestors | Report-Only rồi enforce trên staging; thử parent hợp lệ và ngoài allowlist | Report-Only ghi nhận vi phạm mà không chặn; enforce chặn parent ngoài allowlist |
| form-action | Form submit tới origin ngoài allowlist | Submit bị chặn |
| base-uri | Base tag không được phép | Browser chặn thay đổi base URL |
| worker-src | Worker từ blob: khi chưa cho phép | Worker bị chặn; khi policy cho phép thì hoạt động theo hỗ trợ |
| Report endpoint | Report hợp lệ và malformed | Nhận, validate và rate limit đúng |
| Report privacy | URL chứa query test giả | Query nhạy cảm được redacted |
| Report flood | Nhiều report trùng | Aggregation/sampling ngăn dashboard bị quá tải |
| CDN header | Header app và edge khác nhau | Xác định response header cuối cùng và policy hợp nhất |
| Cache nonce | HTML cache qua nhiều response | Nonce header và markup luôn khớp; không tái sử dụng ngoài thiết kế |
| Browser matrix | Chrome/Firefox/Safari/Edge | Ghi nhận directive/report khác biệt |
| Rollback | Revert policy version | Core workflow phục hồi theo policy đã biết |
| Regression | Login, callback, upload, download, payment | Không có lỗi ngoài ngưỡng đã định |

## 23. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Bật enforce ngay trên toàn production | Chặn script/API hợp lệ và gây outage | Report-Only, staging, canary và rollout |
| Nghĩ Report-Only đã bảo vệ ứng dụng | XSS vẫn có thể thực thi | Chuyển sang enforce sau khi policy được xác minh |
| Thêm mọi blocked-uri vào allowlist | Attacker có thể mở rộng policy | Review owner và nguồn độc lập |
| Dùng wildcard để dập report | CSP quá rộng, giảm hiệu quả | Allowlist host chính xác và loại dependency |
| Giữ unsafe-inline lâu dài | Inline XSS dễ thực thi hơn | Nonce/hash và sửa template |
| Dùng nonce cố định | Attacker có thể dự đoán hoặc tái sử dụng | Nonce ngẫu nhiên mỗi response |
| Cache HTML sai với nonce | Header và markup lệch hoặc nonce bị tái sử dụng | Thiết kế cache-aware và kiểm tra response |
| Nghĩ default-src kiểm soát mọi directive | Bỏ sót frame-ancestors, form-action, base-uri | Khai báo riêng directive quan trọng |
| Chỉ kiểm tra staging một route | Bỏ sót admin/payment/iframe | Inventory và test route đầy đủ |
| Bỏ qua report privacy | URL/token/PII xuất hiện trong telemetry | Redaction, retention và access control |
| Cho tag manager tải script tùy ý | Mở trust boundary rộng | Governance, review và audit publish |
| Thêm blob: vào script-src vì Worker lỗi | Mở rộng quyền script không cần thiết | Sửa worker-src đúng nhu cầu |
| Chỉ nhìn app config | CDN/proxy thêm policy khác | Kiểm tra response header cuối cùng |
| Xóa CSP toàn bộ khi có lỗi | Mất lớp phòng thủ | Rollback policy version đã biết |
| Không kiểm tra browser cũ | Directive có thể bị bỏ qua | Ma trận browser/version và fallback |
| Tin report là bằng chứng tuyệt đối | Report có thể giả hoặc noise | Correlate telemetry và tái hiện |

## 24. Câu hỏi củng cố

**Câu 1.** Khác biệt giữa Content-Security-Policy và Content-Security-Policy-Report-Only là gì?

**Giải đáp:** Header enforce áp dụng policy và chặn hành vi vi phạm; Report-Only chỉ gửi báo cáo theo policy mà không chặn vì policy đó.

**Câu 2.** Vì sao cần Report-Only trước khi enforce?

**Giải đáp:** Để inventory dependency thực tế, phát hiện nguồn hợp lệ bị thiếu và sửa ứng dụng trước khi policy làm gián đoạn người dùng.

**Câu 3.** Report-Only có ngăn XSS không?

**Giải đáp:** Không. Nó chỉ quan sát và báo cáo; cần enforce policy để browser chặn hành vi vi phạm.

**Câu 4.** Vì sao không allowlist mọi blocked-uri?

**Giải đáp:** Report có thể do attacker kích hoạt. Tự động tin blocked-uri sẽ biến report thành kênh mở rộng nguồn được phép.

**Câu 5.** Nonce phải được tạo như thế nào?

**Giải đáp:** Dùng bộ sinh số ngẫu nhiên mật mã, khó đoán, khác nhau theo response và khớp giữa header với script được tin cậy.

**Câu 6.** Hash phù hợp với trường hợp nào?

**Giải đáp:** Inline script/style tĩnh có nội dung ổn định; hash phải khớp chính xác bytes của nội dung.

**Câu 7.** frame-src khác frame-ancestors thế nào?

**Giải đáp:** frame-src giới hạn nguồn iframe mà trang hiện tại nhúng; frame-ancestors giới hạn website nào được phép nhúng trang hiện tại.

**Câu 8.** Vì sao report endpoint cần redaction?

**Giải đáp:** Violation report có thể chứa URL, query, source file và sample code có token hoặc PII.

**Câu 9.** Vì sao phải kiểm tra CSP ở CDN/proxy?

**Giải đáp:** Header cuối cùng có thể được tạo hoặc sửa ở nhiều lớp; browser chỉ áp dụng response thực nhận.

**Câu 10.** Khi CSP làm hỏng chức năng production, xử lý thế nào?

**Giải đáp:** Xác định route, directive và resource bị chặn; nếu ảnh hưởng nghiêm trọng thì rollback về policy đã biết hoạt động, sửa nguyên nhân và rollout lại qua canary.

## 25. Tổng kết

Triển khai CSP là quy trình vận hành nhiều giai đoạn. Bắt đầu bằng inventory route và dependency, đo baseline, thiết kế policy theo threat model rồi bật Report-Only để quan sát. Phân loại report theo nguồn hợp lệ, dependency thừa, noise và hành vi đáng ngờ; không tự động thêm blocked-uri vào allowlist.

Trước enforcement, ưu tiên loại inline code không cần thiết, dùng nonce hoặc hash, giới hạn host và directive theo nhu cầu. Kiểm tra third-party script, tag manager, iframe, form, worker, CDN và cache nonce. Report endpoint phải được bảo vệ, giới hạn tải, redaction URL và có retention/access control.

Enforce trước trên staging, sau đó canary production và mở rộng theo route hoặc traffic. Theo dõi cả CSP violation lẫn chỉ số chức năng như login, API, payment, upload và download. Chuẩn bị rollback policy version đã biết; không mở wildcard hoặc tắt CSP toàn hệ thống để chữa cháy. Duy trì review theo release, regression test và loại bỏ exception không còn cần.

## Tài liệu tham khảo

1. [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/): thuật toán xử lý policy, directive, nonce, hash và reporting.
2. [MDN — Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): hướng dẫn triển khai CSP và Report-Only.
3. [MDN — Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only): chế độ quan sát policy.
4. [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): response header enforce.
5. [MDN — Reporting API](https://developer.mozilla.org/en-US/docs/Web/API/Reporting_API): cấu hình endpoint và nhận report từ browser.
6. [Chrome Developers — CSP](https://developer.chrome.com/docs/privacy-security/csp): triển khai và kiểm tra CSP trên Chromium.
7. [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): chiến lược CSP, nonce/hash và vận hành.
8. [OWASP — CSP Evaluator](https://github.com/google/csp-evaluator): công cụ hỗ trợ review điểm yếu trong policy; kết quả cần được con người đánh giá.
9. [W3C — Subresource Integrity](https://www.w3.org/TR/SRI/): kiểm tra integrity của tài nguyên external.
