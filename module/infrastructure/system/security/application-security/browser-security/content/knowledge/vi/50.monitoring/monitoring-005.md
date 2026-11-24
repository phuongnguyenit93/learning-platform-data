# XSS signal

XSS signal là những dấu hiệu quan sát được cho thấy ứng dụng có thể đang bị thử khai thác Cross-Site Scripting (XSS), đã thực thi nội dung không mong muốn hoặc đang có một đường xử lý dữ liệu không an toàn. Các tín hiệu có thể đến từ trình duyệt, CSP, Trusted Types, lỗi JavaScript, máy chủ ứng dụng, reverse proxy, WAF và hệ thống hỗ trợ khách hàng.

Một tín hiệu riêng lẻ thường chưa đủ để kết luận đã xảy ra XSS. Ví dụ, CSP report cho biết browser đã gặp một hành vi vi phạm policy; nó có thể đến từ payload tấn công, một script hợp lệ cấu hình sai hoặc extension của người dùng. Một request chứa chuỗi giống payload XSS có thể chỉ là nội dung được người dùng nhập vào trình soạn thảo. Giám sát tốt cần kết hợp nhiều nguồn, xác định ngữ cảnh và giữ bằng chứng đủ để điều tra.

Trong module bảo mật trình duyệt, XSS signal giúp nhóm vận hành phát hiện sớm hoạt động đáng ngờ, tìm route hoặc component có nguy cơ, đánh giá tác động và xác minh hiệu quả của biện pháp phòng vệ như output encoding, sanitizer, CSP và Trusted Types. Signal hỗ trợ phát hiện và phản ứng; nó không thay thế các biện pháp ngăn XSS trong thiết kế ứng dụng.

## Phân biệt tín hiệu, sự kiện và sự cố

Ba khái niệm này cần được tách rõ:

- **Signal:** dữ liệu quan sát có thể liên quan đến XSS, ví dụ CSP violation, Trusted Types violation hoặc request khớp quy tắc WAF.
- **Sự kiện bảo mật:** một hành vi cụ thể đã được xác nhận, chẳng hạn browser chặn inline script không có nonce trên một route.
- **Sự cố XSS:** có bằng chứng cho thấy mã không được phép đã thực thi hoặc kẻ tấn công đã khai thác được một đường XSS để tác động đến người dùng hay dữ liệu.

Không nên nâng mọi signal thành incident. Ngược lại, cũng không nên bỏ qua một signal chỉ vì nó chưa chứng minh được việc thực thi mã. Cần đánh giá nguồn phát, ngữ cảnh, khả năng tái hiện, mức độ nhạy cảm của route và bằng chứng bổ sung.

XSS thường được chia thành ba dạng:

| Dạng | Đường đi dữ liệu | Tín hiệu có thể quan sát |
|---|---|---|
| Reflected XSS | Request chứa dữ liệu được phản hồi vào HTML của response | Request bất thường, CSP report ngay sau request, lỗi parser hoặc hành vi đáng ngờ trên route nhận tham số |
| Stored XSS | Dữ liệu độc hại được lưu rồi hiển thị cho người dùng khác | CSP/Trusted Types signal trên nhiều phiên, nhiều người dùng hoặc cùng nội dung; báo cáo hỗ trợ về một bản ghi cụ thể |
| DOM-based XSS | JavaScript phía client đưa dữ liệu không tin cậy vào DOM sink | Trusted Types violation, lỗi runtime, CSP violation hoặc telemetry từ component xử lý dữ liệu |

Các dạng có thể kết hợp. Một payload có thể được lưu ở server, sau đó JavaScript phía client đọc dữ liệu và đưa vào sink nguy hiểm. Do đó, khi điều tra cần lần theo cả request, nơi lưu dữ liệu, response và thao tác DOM.

## Nguồn tín hiệu XSS

Không có một nguồn telemetry duy nhất phát hiện được mọi XSS. Mỗi nguồn quan sát một phần khác nhau của chuỗi tấn công.

| Nguồn | Điều có thể cho biết | Giới hạn |
|---|---|---|
| CSP violation report | Browser đã chặn hoặc báo cáo một hành vi vi phạm policy | Không phải mọi XSS đều vi phạm CSP; report có thể do cấu hình sai hoặc extension |
| `securitypolicyviolation` event | Document nhận được sự kiện CSP violation ở runtime | Chỉ tồn tại trong document còn hoạt động; không bảo đảm gửi được về server |
| Trusted Types enforcement | Dữ liệu không đúng loại Trusted Type đi vào sink được bảo vệ | Có thể là lỗi ứng dụng hợp lệ; chỉ hỗ trợ trên browser có enforcement tương ứng |
| JavaScript error và unhandled rejection | Lỗi runtime có thể phát sinh khi policy chặn thao tác hoặc code xử lý payload | Thông báo lỗi không chứng minh có tấn công và có thể chứa dữ liệu nhạy cảm |
| WAF hoặc reverse proxy | Request có mẫu đáng ngờ, nguồn hoặc tần suất bất thường | Có false positive; payload có thể được mã hóa, chia nhỏ hoặc không khớp rule |
| Application log | Route, thao tác, object ID và kết quả xử lý ở server | Chỉ hữu ích nếu log được thiết kế; không quan sát trực tiếp việc thực thi trong browser |
| SAST/DAST và kiểm thử chủ động | Sink nguy hiểm, source không tin cậy hoặc payload thử nghiệm có thể khai thác | Là bằng chứng theo thời điểm kiểm thử, không phải telemetry liên tục |
| Phản ánh người dùng và hỗ trợ | Nội dung hiển thị bất thường, redirect hoặc thao tác ngoài ý muốn | Cần tái hiện và xác minh; ảnh chụp màn hình không luôn cho thấy nguồn thực thi |

Kết hợp tín hiệu từ client và server giúp điều tra tốt hơn. Ví dụ, một CSP report về `script-src` trên trang hồ sơ có thể được đối chiếu với request vừa lưu nội dung hồ sơ, phiên bản frontend và release vừa triển khai.

## CSP làm nguồn phát hiện XSS

Content Security Policy có thể chặn một số đường thực thi script không được phép và gửi báo cáo về vi phạm. CSP hiệu quả cần được thiết kế để cho phép đúng script hợp lệ, thường bằng nonce hoặc hash, và tránh các nguồn quá rộng.

Ví dụ response headers cho một ứng dụng dùng nonce:

~~~http
Reporting-Endpoints: csp="https://reports.example.com/csp"
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; report-to csp; report-uri https://reports.example.com/csp
~~~

`RANDOM_PER_RESPONSE` là chỗ giữ chỗ trong ví dụ; hệ thống phải sinh nonce ngẫu nhiên cho từng response HTML và gắn cùng giá trị vào các script được cấp phép. Không dùng chuỗi cố định này trong production. `report-to` tham chiếu nhóm endpoint trong `Reporting-Endpoints`; `report-uri` có thể được giữ làm đường tương thích cho browser cũ trong giai đoạn chuyển đổi. Hỗ trợ báo cáo khác nhau theo browser nên phải kiểm thử trên ma trận client thực tế.

Để quan sát một policy mới trước khi chặn, có thể dùng `Content-Security-Policy-Report-Only` với cùng mục tiêu policy. Report-Only giúp phát hiện script hợp lệ còn thiếu trong allowlist. Khi đã phân loại các report và xác minh policy, chuyển sang CSP enforce. Không coi Report-Only là biện pháp ngăn XSS vì nó không chặn theo policy đó.

### Những trường report cần chú ý

Report CSP có thể chứa các trường như:

- Loại report và `effectiveDirective`, ví dụ `script-src` hoặc `script-src-elem`.
- `blockedURL` hoặc `blocked-uri`: URL hay loại tài nguyên bị chặn; giá trị có thể là `inline`, `eval`, `data` hoặc một URL.
- URL document, referrer, file nguồn, dòng và cột phát sinh vi phạm.
- `disposition`: policy đang enforce hay report-only.
- `originalPolicy`: nội dung policy được áp dụng.
- `sample`: một phần mẫu nội dung nếu policy cho phép thu thập bằng `report-sample` và browser hỗ trợ.

Tên trường và định dạng khác nhau giữa báo cáo CSP cũ và Reporting API mới. Hệ thống tiếp nhận cần nhận diện content type và schema tương ứng thay vì giả định mọi browser gửi một cấu trúc duy nhất.

Không lưu nguyên report thô vô thời hạn. URL có thể chứa token, email, mã hồ sơ hoặc tham số tìm kiếm; `originalPolicy` có thể chứa nonce; `sample` có thể chứa nội dung người dùng. Chỉ giữ các trường cần thiết, rút gọn URL và áp dụng retention phù hợp.

## Thu thập CSP violation trong trang

Browser phát sự kiện `securitypolicyviolation` trên document khi có vi phạm CSP. Ứng dụng có thể dùng sự kiện này để ghi nhận một số trường tối thiểu ở client.

~~~javascript
function safeOrigin(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:'
      ? url.origin
      : null;
  } catch {
    return null;
  }
}

document.addEventListener('securitypolicyviolation', (event) => {
  const signal = {
    type: 'csp-violation',
    directive: String(event.effectiveDirective || '').slice(0, 80),
    disposition: String(event.disposition || '').slice(0, 20),
    blockedOrigin: safeOrigin(event.blockedURI),
    sourceOrigin: safeOrigin(event.sourceFile),
    line: Number.isInteger(event.lineNumber) ? event.lineNumber : null,
    appVersion: window.APP_VERSION || 'unknown'
  };

  const body = JSON.stringify(signal);
  const blob = new Blob([body], { type: 'application/json' });
  if (typeof navigator.sendBeacon === 'function') {
    navigator.sendBeacon('/telemetry/security-signal', blob);
  }
});
~~~

Đây là ví dụ minh họa cho telemetry phía client. `safeOrigin()` cố ý chỉ giữ origin, bỏ path, query và fragment. Trong sản phẩm, cần cân nhắc `connect-src` vì `sendBeacon()` vẫn chịu chính sách kết nối của browser; endpoint phải được cho phép trong `connect-src`. Không gửi `event.sample`, `event.originalPolicy` hoặc URL đầy đủ nếu chưa có mục đích và kiểm soát dữ liệu rõ ràng.

Client telemetry có thể mất khi trang đóng, offline, browser chặn request hoặc endpoint lỗi. Nếu đã cấu hình CSP report endpoint, sự kiện client có thể trùng với report browser gửi trực tiếp. Dùng khóa khử trùng lặp và nguồn sự kiện để không đếm hai lần. Không phụ thuộc vào listener JavaScript để phát hiện mọi XSS.

## Trusted Types và DOM XSS signal

Trusted Types giúp bảo vệ một số DOM sink bằng cách yêu cầu giá trị thuộc loại tin cậy như `TrustedHTML`, `TrustedScript` hoặc `TrustedScriptURL`. Khi policy `require-trusted-types-for 'script'` được enforce, thao tác đưa chuỗi thông thường vào sink được bảo vệ có thể bị browser từ chối.

Ví dụ CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-sanitizer; object-src 'none'; base-uri 'self'
~~~

Nếu ứng dụng cố gắng gán một chuỗi không phải `TrustedHTML` vào `innerHTML`, browser có thể ném `TypeError` và tạo tín hiệu vi phạm liên quan đến Trusted Types/CSP. Tín hiệu này thường hữu ích để tìm một đường code đang truyền dữ liệu không đúng loại vào sink.

Tuy nhiên, không phải mọi lỗi `TypeError` đều là tấn công. Có thể đó là code cũ chưa được chuyển đổi, test fixture hoặc một thư viện bên thứ ba. Cần ghi nhận sink/component, release, route và directive liên quan, sau đó kiểm tra nguồn dữ liệu đi vào sink.

Không nên tạo default policy trả lại nguyên chuỗi đầu vào chỉ để ứng dụng cũ không lỗi. Cách làm đó có thể vô hiệu hóa mục tiêu của Trusted Types. Policy phải gọi sanitizer đã được đánh giá, có test cho các ngữ cảnh HTML phù hợp và không tin dữ liệu chỉ vì nó đến từ cùng origin.

Khi browser không hỗ trợ Trusted Types enforcement, cần duy trì các kiểm soát khác: dùng `textContent` cho văn bản, sanitizer phù hợp khi cần HTML, encode theo ngữ cảnh, kiểm soát template và review các sink như `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` và script URL. Polyfill không thể thay thế enforcement gốc của browser.

## Lỗi JavaScript và tín hiệu phía client

Một số XSS bị CSP hoặc Trusted Types chặn có thể đi kèm lỗi JavaScript. Ứng dụng có thể ghi nhận lỗi toàn cục để hỗ trợ chẩn đoán:

~~~javascript
window.addEventListener('error', (event) => {
  const signal = {
    type: 'client-error',
    name: String(event.error?.name || 'Error').slice(0, 80),
    appVersion: window.APP_VERSION || 'unknown',
    route: location.pathname
  };

  queueSecurityTelemetry(signal);
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason;
  const signal = {
    type: 'unhandled-rejection',
    name: String(reason?.name || typeof reason).slice(0, 80),
    appVersion: window.APP_VERSION || 'unknown',
    route: location.pathname
  };

  queueSecurityTelemetry(signal);
});
~~~

`queueSecurityTelemetry` là hàm của ứng dụng cần được triển khai có giới hạn tốc độ và xử lý lỗi. Ví dụ cố ý không gửi `event.message`, stack trace, nội dung rejection hoặc query string vì các trường đó có thể chứa dữ liệu người dùng và bí mật. Nếu cần stack trace để điều tra, phải lọc dữ liệu, giới hạn quyền truy cập và thời gian lưu.

Lỗi JavaScript thông thường có độ đặc hiệu thấp với XSS. Hãy phân loại riêng lỗi do Trusted Types, lỗi CSP, lỗi parser và lỗi ứng dụng chung. Không tự động kết luận một người dùng bị tấn công chỉ vì trình duyệt ghi nhận một `TypeError`.

## Tín hiệu từ server, WAF và ứng dụng

Server quan sát được request trước hoặc sau khi dữ liệu được xử lý. Đây là nguồn quan trọng để liên kết hoạt động đáng ngờ với route và object cụ thể.

Các dấu hiệu có thể theo dõi:

- Request có chuỗi hoặc cấu trúc thường gặp trong payload XSS, sau khi giải mã ở mức an toàn theo đúng encoding của từng lớp.
- Nhiều request thử các biến thể HTML, thuộc tính sự kiện, scheme URL hoặc cú pháp script trên cùng một tham số.
- Một request bị WAF đánh dấu rồi ngay sau đó xuất hiện CSP violation trên route nhận dữ liệu.
- Một bản ghi do người dùng tạo chứa markup bất thường và được render trên nhiều tài khoản hoặc nhiều phiên.
- Thay đổi đột ngột về lỗi template, lỗi sanitizer hoặc lỗi encode ở một route sau release.
- Một user action dẫn đến response có nội dung không mong muốn, redirect bất thường hoặc thao tác DOM không nằm trong luồng sản phẩm.

WAF có thể cung cấp rule ID, tham số, vị trí phát hiện và hành động (allow, block, log). Dùng các trường này để tìm mẫu tấn công, nhưng đừng dựa vào WAF như bộ lọc XSS hoàn chỉnh. Mã hóa nhiều lớp, Unicode, parser khác nhau và payload chia nhỏ có thể làm tín hiệu khó nhận biết; nội dung hợp lệ trong editor cũng có thể khớp rule.

Application log nên ghi thông tin có cấu trúc: route template, action, loại object, kết quả validation, phiên bản ứng dụng, request ID và rule ID nếu có. Không ghi toàn bộ HTML, cookie, token hoặc payload thô vào log thông thường. Nếu cần giữ mẫu để điều tra, lưu trong kho giới hạn truy cập, mã hóa và đặt thời hạn xóa ngắn.

## Chuẩn hóa tín hiệu

Các nguồn telemetry thường có schema khác nhau. Nên chuyển chúng về một cấu trúc nội bộ để có thể lọc, so sánh và khử trùng lặp.

Một schema tối thiểu có thể gồm:

| Trường | Mục đích |
|---|---|
| `event_type` | `csp_violation`, `trusted_types_violation`, `client_error`, `waf_match` hoặc `app_validation` |
| `observed_at` | Thời điểm nhận tín hiệu ở hệ thống, không mặc định là thời điểm browser tạo report |
| `app_version` | Phiên bản release để liên kết với thay đổi gần đây |
| `route_template` | Route đã chuẩn hóa, không chứa query hoặc ID nhạy cảm |
| `browser_family` và `browser_version_major` | Phân tích tương thích ở mức cần thiết |
| `directive` hoặc `rule_id` | CSP directive, Trusted Types sink hoặc WAF rule liên quan |
| `blocked_origin` | Origin tài nguyên bị chặn nếu có thể chuẩn hóa an toàn |
| `disposition` | Enforce hay report-only đối với CSP |
| `request_id` | Liên kết với log server nếu có, không dùng làm bí mật xác thực |
| `source` | Nguồn thu thập: browser report, client event, WAF hoặc application |

Không đưa session cookie, access token, nội dung biểu mẫu, URL có query hoặc payload nguyên gốc vào schema mặc định. Nếu cần correlation với người dùng, ưu tiên mã sự kiện hoặc định danh giả danh có thời hạn và chỉ khi có cơ sở quyền riêng tư phù hợp.

## Khử trùng lặp và phân loại mức độ

Một hành vi có thể tạo nhiều report: browser gửi report trực tiếp, listener client gửi telemetry và WAF ghi nhận request. Một script bị chặn trên nhiều page cũng có thể tạo nhiều report giống nhau. Nếu đếm mỗi report thành một incident, dashboard sẽ phóng đại mức độ.

Có thể tạo fingerprint từ các trường ít nhạy cảm:

~~~text
fingerprint = hash(
  event_type + route_template + directive_or_rule + blocked_origin + app_version
)
~~~

Kết hợp fingerprint với cửa sổ thời gian để gom các report gần nhau. Không đưa raw payload hoặc full URL vào fingerprint nếu không cần; giá trị có thể chứa bí mật và làm tăng số lượng nhóm không kiểm soát.

Phân loại ban đầu có thể theo mức độ và độ tin cậy:

| Mức | Ví dụ | Hành động |
|---|---|---|
| Thông tin | Một deprecation hoặc lỗi client không liên quan trực tiếp đến sink XSS | Ghi nhận và theo dõi xu hướng |
| Thấp | CSP report đơn lẻ trên tài nguyên thử nghiệm hoặc extension, chưa có dấu hiệu khai thác | Kiểm tra nguồn và cấu hình; không tự động khóa người dùng |
| Trung bình | Nhiều CSP/Trusted Types signal trên cùng route, có request đáng ngờ tương ứng | Tạo cảnh báo cho đội ứng dụng, tái hiện trong staging và kiểm tra dữ liệu nguồn |
| Cao | Có bằng chứng code không được phép thực thi, stored payload hiển thị cho nhiều người hoặc hành vi trái phép sau khi render | Mở incident, cô lập đường dữ liệu, vá lỗi và đánh giá phiên bị ảnh hưởng |

Độ nghiêm trọng phụ thuộc vào nơi bị ảnh hưởng, quyền của người dùng, dữ liệu truy cập được và khả năng khai thác. Một vi phạm ở trang quản trị có thể có tác động cao hơn cùng loại signal ở một trang marketing tĩnh.

## Correlate và triage một XSS signal

Khi một cảnh báo xuất hiện, điều tra theo trình tự:

1. **Xác định nguồn:** signal đến từ CSP endpoint, browser event, Trusted Types, WAF, application log hay phản ánh người dùng? Kiểm tra schema và độ tin cậy của nguồn.
2. **Xác định route và release:** route template, phiên bản ứng dụng, browser/version và thời điểm triển khai có liên quan.
3. **Xác định directive hoặc sink:** ví dụ `script-src`, `script-src-elem`, `require-trusted-types-for` hoặc một WAF rule.
4. **Kiểm tra request liên quan:** có tham số hoặc object vừa được tạo/cập nhật không? Có request cùng request ID hoặc thời điểm gần đó không?
5. **Lần theo dữ liệu:** dữ liệu bắt đầu từ đâu, được lưu ở đâu, được encode/sanitize như thế nào và đi đến DOM sink nào?
6. **Tái hiện an toàn:** dùng dữ liệu giả và browser test trong staging; không mở payload nghi ngờ trong profile chứa tài khoản thật.
7. **Đánh giá tác động:** xác định người dùng, route, loại dữ liệu và quyền có thể bị ảnh hưởng.
8. **Ghi kết luận:** phân biệt false positive, lỗi cấu hình, hành vi bị chặn và XSS đã thực thi; ghi bằng chứng còn thiếu.

Ví dụ: WAF ghi nhận request chứa markup ở trường `displayName`; vài giây sau CSP endpoint nhận report `script-src-elem` trên `/profile`. Điều tra cần kiểm tra liệu trường đó có được lưu, trang profile có render trường bằng `innerHTML` hay không, report có cùng browser/session test hay chỉ trùng thời gian, và browser có chặn script thật không. Nếu payload chỉ được hiển thị như text, có thể đó là một lần thử bị phòng vệ chặn; nếu script thực thi, đây là sự cố XSS.

## Bảo vệ endpoint nhận report

CSP report endpoint thường phải nhận request không có cookie đăng nhập ứng dụng. Bất kỳ client nào có thể gửi HTTP request cũng có thể giả mạo một JSON giống report. Vì vậy, report là telemetry không tin cậy, không phải bằng chứng xác thực danh tính.

Endpoint cần:

- Chấp nhận đúng content type và schema được hỗ trợ; kiểm tra report cũ và mới theo nhánh riêng.
- Giới hạn kích thước body, số report mỗi batch, tốc độ request và thời gian xử lý.
- Giới hạn độ dài chuỗi, số lượng trường và cấu trúc lồng; từ chối payload quá lớn hoặc sai định dạng.
- Không fetch `blockedURL`, `sourceFile`, `documentURL` hay URL nào do report cung cấp; làm vậy có thể tạo SSRF.
- Encode dữ liệu khi hiển thị trên dashboard; không render report như HTML.
- Không dùng `Origin`, `Referer` hoặc `User-Agent` làm cơ chế xác thực.
- Trả phản hồi gọn, thường là `204 No Content`, và xử lý bất đồng bộ nếu phân tích tốn tài nguyên.
- Áp dụng quota, deduplication và retention để report giả mạo không làm cạn tài nguyên.

Report endpoint cần có giám sát riêng: tỷ lệ request lỗi, batch bị từ chối, kích thước trung bình, nguồn report theo browser và tình trạng hàng đợi. Không để endpoint thu thập report trở thành đường DoS hoặc kho lưu dữ liệu cá nhân không kiểm soát.

## Bảo vệ quyền riêng tư khi thu thập XSS signal

Telemetry bảo mật có thể vô tình thu thập nhiều dữ liệu hơn cần thiết. URL, referrer, source sample, nội dung lỗi và stack trace có thể chứa dữ liệu cá nhân hoặc bí mật.

Áp dụng nguyên tắc giảm thiểu:

- Lưu route template thay vì URL đầy đủ; loại bỏ query string và fragment.
- Chỉ giữ origin của tài nguyên bị chặn khi mục tiêu điều tra không cần path.
- Không bật `report-sample` mặc định; chỉ bật trong phạm vi hẹp, có thời hạn và kiểm soát truy cập.
- Không ghi cookie, token, authorization header, nội dung biểu mẫu hoặc HTML đầy đủ.
- Hạn chế quyền xem report thô; dashboard tổng hợp có thể phục vụ nhóm rộng hơn.
- Đặt thời hạn lưu cho raw report, dữ liệu chuẩn hóa và incident evidence riêng biệt.
- Ghi lại mục đích thu thập, người chịu trách nhiệm và cách xử lý yêu cầu xóa dữ liệu.

Không dùng XSS telemetry để tạo fingerprint người dùng chi tiết. Nếu cần liên kết sự kiện trong một phiên điều tra, dùng mã tương quan ngẫu nhiên, thời hạn ngắn và chỉ cấp cho nhóm ứng phó.

## Kiểm thử pipeline XSS signal

Một pipeline giám sát cần được kiểm thử chủ động để biết tín hiệu có đi qua toàn bộ đường thu thập hay không. Dùng origin, tài khoản và payload vô hại do nhóm kiểm soát.

Các test case cơ bản:

1. **CSP enforce:** tạo fixture có script inline không được cấp nonce/hash. Xác nhận browser chặn thực thi, phát `securitypolicyviolation` và gửi report nếu browser hỗ trợ endpoint đã cấu hình.
2. **CSP Report-Only:** tạo cùng vi phạm với policy Report-Only. Xác nhận report được ghi nhận nhưng tài nguyên không bị chặn chỉ bởi policy Report-Only.
3. **Trusted Types:** trong browser hỗ trợ, thử đưa chuỗi thường vào sink được bảo vệ. Xác nhận thao tác bị từ chối và tín hiệu được phân loại đúng.
4. **Request/WAF:** gửi một chuỗi test vô hại vào fixture đã chỉ định để xác nhận rule được ghi nhận. Không dùng payload thực thi trên hệ thống production.
5. **Khử trùng lặp:** tạo cùng một sự kiện qua nhiều nguồn để xác nhận dashboard không đếm thành nhiều incident độc lập.
6. **Dữ liệu riêng tư:** đưa query giả lập chứa dữ liệu nhạy cảm vào fixture và xác nhận pipeline loại bỏ query, sample và trường không cần thiết.
7. **Endpoint lỗi:** gửi JSON sai định dạng, batch quá lớn và tốc độ cao trên môi trường test. Xác nhận endpoint giới hạn tài nguyên và không lộ stack trace.
8. **Browser không hỗ trợ:** xác nhận ứng dụng vẫn hoạt động an toàn khi Reporting API hoặc Trusted Types không có; dashboard thể hiện rõ thiếu telemetry.

Ví dụ kiểm thử browser event bằng Playwright có thể dùng một route fixture chỉ tồn tại trong môi trường test:

~~~javascript
import { test, expect } from '@playwright/test';

test('records a blocked inline script as a CSP signal', async ({ page }) => {
  const signals = [];
  await page.exposeFunction('recordSignalForTest', (signal) => {
    signals.push(signal);
  });

  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      window.recordSignalForTest({
        directive: event.effectiveDirective,
        disposition: event.disposition
      });
    });
  });

  await page.goto('/__test/xss-signal');

  await expect.poll(() => signals.length).toBeGreaterThan(0);
  expect(signals.some((signal) =>
    signal.directive === 'script-src' || signal.directive === 'script-src-elem'
  )).toBe(true);
});
~~~

Fixture `/__test/xss-signal` phải trả CSP enforce và chứa inline script vô hại không được cấp phép. `recordSignalForTest` chỉ là kênh quan sát trong test; không dùng nó làm telemetry production. Test phải xác nhận thêm script không được thực thi, ví dụ bằng một cờ kiểm thử không được thiết lập. Không dùng `page.evaluate()` để chèn script rồi suy ra CSP đã chặn payload trong parser của document, vì lệnh automation có thể có quyền thực thi khác với script inline trong HTML.

## Xử lý khi xác nhận XSS

Khi có bằng chứng XSS đã thực thi hoặc dữ liệu bị truy cập trái phép, xử lý như incident bảo mật:

1. Ghi nhận route, release, browser, thời điểm, signal nguồn và bằng chứng đã được lọc dữ liệu nhạy cảm.
2. Xác định source và sink; tìm mọi nơi cùng component hoặc template được dùng.
3. Tạm thời vô hiệu hóa hoặc giới hạn chức năng bị ảnh hưởng nếu cần để ngăn thêm dữ liệu đi qua đường lỗi.
4. Sửa nguyên nhân gốc bằng output encoding theo ngữ cảnh, sanitizer phù hợp, API DOM an toàn và kiểm soát URL/script loader.
5. Dùng CSP và Trusted Types làm lớp phòng vệ bổ sung; không chỉ thêm rule chặn một payload cụ thể.
6. Kiểm tra các bản ghi đã lưu để xác định stored payload có còn được render ở nơi khác không.
7. Đánh giá khả năng cookie/session hoặc dữ liệu tài khoản bị truy cập. Nếu có căn cứ session bị lộ, thu hồi phiên và token theo quy trình ứng phó.
8. Triển khai bản vá, chạy regression test và theo dõi signal sau phát hành để xác nhận lỗi đã được xử lý.
9. Ghi lại phạm vi ảnh hưởng, quyết định thông báo và biện pháp phòng ngừa tái diễn.

Không xóa report hoặc log gốc trước khi bảo toàn bằng chứng cần thiết. Đồng thời, không sao chép payload hay dữ liệu cá nhân vào ticket rộng quyền truy cập; dùng bản đã làm sạch và tham chiếu đến kho bằng chứng được kiểm soát.

## Chỉ số vận hành và cảnh báo

Dashboard XSS signal nên cho phép xem xu hướng và drill-down theo route, release, browser, directive và nguồn telemetry. Các chỉ số hữu ích gồm:

- Số CSP violation theo directive và disposition (enforce/report-only).
- Số Trusted Types violation theo route và phiên bản ứng dụng.
- Số WAF match theo rule ID, action và endpoint.
- Tỷ lệ signal lặp lại sau khi đã deduplicate.
- Số route có nhiều nguồn signal cùng xuất hiện trong một cửa sổ thời gian.
- Tỷ lệ report hợp lệ, report bị từ chối và độ trễ từ lúc nhận đến lúc xử lý.
- Thời gian từ cảnh báo đến triage, xác nhận và khắc phục.

Không đặt cảnh báo chỉ dựa trên tổng số report toàn hệ thống. Một đợt rollout CSP có thể làm report tăng mạnh mà không có cuộc tấn công. Nên so sánh với baseline theo route, release và browser; cảnh báo khi có thay đổi bất thường hoặc nhiều nguồn độc lập cùng xác nhận.

Một quy tắc cảnh báo minh họa: tạo cảnh báo ưu tiên khi một route nhạy cảm có CSP `script-src` violation tăng đột ngột, đồng thời WAF phát hiện request có dấu hiệu XSS trên cùng route và phiên bản ứng dụng vừa thay đổi. Cần cho phép người trực xác nhận correlation thay vì tự động khóa tài khoản chỉ dựa trên mẫu này.

## Lỗi thường gặp khi vận hành XSS signal

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Coi mọi CSP report là XSS thành công | Tạo nhiều incident giả và mất niềm tin vào cảnh báo | Phân biệt hành vi bị chặn, cấu hình sai và thực thi đã xác nhận |
| Coi không có report là không có XSS | Bỏ sót XSS không vi phạm CSP hoặc browser không gửi report | Kết hợp kiểm thử, SAST/DAST, log ứng dụng và phản ánh người dùng |
| Lưu nguyên URL và sample | Rò rỉ token, PII hoặc nội dung người dùng | Chuẩn hóa route, rút gọn URL và hạn chế sample |
| Tin `Origin` hoặc `User-Agent` trong report | Client giả mạo có thể làm sai phân tích | Coi payload là telemetry không tin cậy, xác minh bằng nguồn khác |
| Không khử trùng lặp | Một hành vi tạo nhiều cảnh báo | Dùng fingerprint từ trường đã làm sạch và cửa sổ thời gian |
| Chặn người dùng tự động theo một WAF rule | Chặn nhầm nội dung hợp lệ và dễ bị lạm dụng gây từ chối dịch vụ | Triage theo ngữ cảnh và dùng nhiều tín hiệu |
| Dùng regex để kết luận payload đã thực thi | Bỏ sót biến thể và nhầm nội dung hợp lệ | Xác minh source-to-sink và hành vi runtime |
| Chỉ thu thập lỗi JavaScript | Không thấy các XSS chạy thành công mà không phát sinh lỗi | Kết hợp CSP, Trusted Types, server và test chủ động |

## Checklist XSS signal

- [ ] Có danh sách nguồn tín hiệu: CSP, Trusted Types, client error, WAF và application log.
- [ ] Phân biệt signal, sự kiện bị chặn và incident XSS đã xác nhận.
- [ ] CSP enforce và Report-Only được cấu hình, kiểm thử theo browser mục tiêu.
- [ ] `securitypolicyviolation` event chỉ gửi trường cần thiết và không gửi nonce/sample thô.
- [ ] Trusted Types violation được phân loại riêng với lỗi JavaScript chung.
- [ ] Endpoint report kiểm tra schema, giới hạn kích thước/tốc độ và coi payload là không tin cậy.
- [ ] URL, query, referrer, source sample, cookie và token được giảm thiểu hoặc loại bỏ.
- [ ] Signal được chuẩn hóa, deduplicate và liên kết với route/release phù hợp.
- [ ] Dashboard có baseline và phân tích theo directive, browser, route và disposition.
- [ ] Có quy trình triage, tái hiện an toàn, bảo toàn bằng chứng và ứng phó incident.
- [ ] Có test chủ động xác nhận pipeline hoạt động và có thể nhận biết browser thiếu telemetry.
- [ ] Biện pháp sửa tập trung vào source/sink và nguyên nhân gốc, không chỉ chặn payload cụ thể.

## Câu hỏi tự kiểm tra

1. Vì sao CSP violation không đồng nghĩa với XSS đã thực thi?
2. Những trường nào trong CSP report có thể chứa dữ liệu nhạy cảm?
3. Trusted Types violation giúp tìm lỗi DOM XSS như thế nào, và vì sao vẫn có thể là lỗi ứng dụng thông thường?
4. Vì sao WAF match hoặc request chứa chuỗi giống payload không đủ để kết luận XSS?
5. Làm thế nào liên kết CSP report với request server mà không lưu cookie hoặc URL đầy đủ?
6. Vì sao cần kiểm thử pipeline trên browser không hỗ trợ Reporting API hoặc Trusted Types?
7. Khi nào một XSS signal cần được nâng thành incident và cần bảo toàn bằng chứng nào?

XSS signal có giá trị khi được thu thập có chọn lọc, đặt đúng ngữ cảnh và đối chiếu với bằng chứng khác. Hãy dùng CSP và Trusted Types để quan sát hành vi browser, log server để lần theo dữ liệu và kiểm thử chủ động để xác minh pipeline. Khi phát hiện bất thường, ưu tiên tìm source và sink gây ra vấn đề, đánh giá tác động và sửa nguyên nhân gốc.
