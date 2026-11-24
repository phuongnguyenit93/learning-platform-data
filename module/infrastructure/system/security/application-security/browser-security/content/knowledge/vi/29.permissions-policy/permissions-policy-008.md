# Policy audit: chẩn đoán, báo cáo vi phạm và kiểm thử tương thích Permissions Policy

> **Chương:** Permissions Policy  
> **Phạm vi module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.  
> **Trọng tâm bài:** chẩn đoán và xử lý lỗi cấu hình, báo cáo vi phạm và ma trận tương thích.

**Permissions Policy** cho phép website giới hạn những tính năng trình duyệt mà document và nội dung nhúng được sử dụng, ví dụ geolocation, camera, microphone, fullscreen, clipboard hoặc screen capture. Policy được thiết lập chủ yếu bằng response header **Permissions-Policy** và có thể thu hẹp riêng từng iframe bằng thuộc tính **allow**.

Một policy có thể đúng cú pháp nhưng vẫn không có tác dụng như mong đợi vì header không xuất hiện trên response HTML cuối cùng, directive sai tên, origin không khớp, iframe thiếu allow, ancestor đã tắt feature, browser chưa hỗ trợ hoặc người dùng chưa cấp permission. Vì thế, audit phải theo dõi toàn bộ đường đi từ response header đến API thực tế.

Bài này xây dựng quy trình điều tra theo lớp, cách đọc lỗi Console/Network, sử dụng **Permissions-Policy-Report-Only** và Reporting API khi browser hỗ trợ, thu thập báo cáo trong trang bằng ReportingObserver, xử lý khác biệt định dạng báo cáo, cùng ma trận tương thích để quyết định phần nào có thể dựa vào browser và phần nào cần fallback.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Kiểm tra policy thực tế mà browser nhận từ response thay vì chỉ đọc cấu hình server.
2. Phân biệt lỗi cú pháp header, lỗi feature identifier, allowlist, inheritance và iframe delegation.
3. Chẩn đoán feature bị chặn bởi Permissions Policy hay bởi user permission, secure context, user activation hoặc thiết bị.
4. Đọc thông báo Console, Network và trạng thái frame trong DevTools.
5. Thiết lập Reporting-Endpoints cùng report-to cho policy vi phạm.
6. Dùng Permissions-Policy-Report-Only để quan sát policy dự kiến mà chưa enforcement.
7. Thu thập report bằng ReportingObserver và xử lý khác biệt payload giữa browser.
8. Xây dựng ma trận kiểm thử theo browser, phiên bản, directive và ngữ cảnh iframe.
9. Lập kế hoạch rollout, theo dõi, rollback và kiểm tra hồi quy cho policy.
10. Thực hành audit trên hai origin localhost bằng Node.js.

## 1. Mô hình audit: policy được đánh giá ở nhiều lớp

### 1.1 Ba lớp cần kiểm tra

Khi một API không hoạt động, đừng bắt đầu bằng việc sửa JavaScript. Hãy lần theo ba lớp:

| Lớp | Câu hỏi | Nơi kiểm tra |
|---|---|---|
| Policy của document | Response có gửi Permissions-Policy đúng không? | Network → document response headers |
| Policy kế thừa/container | Parent, ancestor và iframe allow có cho phép origin hiện tại không? | DOM iframe, response của từng frame, DevTools frame policy |
| Điều kiện của API | Browser, người dùng, secure context và user activation có cho phép không? | Console, Permissions API, API error và thiết bị |

Một feature chỉ dùng được khi policy cho phép và các điều kiện riêng của API cũng thỏa mãn. Permissions Policy không cấp camera hoặc geolocation thay cho người dùng; nó chỉ cho phép hoặc ngăn document yêu cầu sử dụng feature.

### 1.2 Quy trình điều tra chuẩn

~~~text
API không hoạt động
       |
       v
1. Browser có hỗ trợ API và directive?
       |
       v
2. Document có secure context / đúng user activation?
       |
       v
3. Response HTML có Permissions-Policy?
       |
       v
4. Feature identifier và allowlist có hợp lệ?
       |
       v
5. Tất cả ancestor có cho phép feature?
       |
       v
6. Iframe có allow đúng origin và redirect?
       |
       v
7. User permission / OS permission có cho phép?
       |
       v
8. Đối chiếu Console, Network và violation reports
~~~

Ghi lại browser/version, URL document, frame URL, feature identifier, response header, kết quả API và thời điểm thử. Nếu không giữ đủ dữ liệu này, một lỗi chỉ tái hiện được trên một thiết bị sẽ rất khó phân loại.

### 1.3 Phân biệt các cơ chế gần nhau

| Cơ chế | Kiểm soát |
|---|---|
| Permissions Policy | Document/origin nào được sử dụng một browser feature |
| Permissions API | Trạng thái permission mà browser báo cho website |
| CSP frame-src | Trang cha được tải iframe từ nguồn nào |
| CSP frame-ancestors | Những trang nào được phép nhúng document |
| iframe sandbox | Những khả năng của document nhúng bị hạn chế |
| Same-Origin Policy | Script có thể truy cập DOM/dữ liệu của origin khác hay không |
| CORS | Script có được đọc response cross-origin hay không |

Ví dụ, iframe có thể được phép dùng geolocation theo Permissions Policy nhưng vẫn không được trang cha đọc DOM do Same-Origin Policy. Ngược lại, CORS thành công không tự cấp camera hoặc microphone.

## 2. Kiểm tra response header thực tế

### 2.1 Xác minh trên document response

Mở DevTools → Network, bật Preserve log nếu trang điều hướng hoặc có redirect, tải lại trang và chọn request loại Document. Kiểm tra Response Headers của response HTML cuối cùng.

Ví dụ policy:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net"), camera=(), microphone=(), fullscreen=(self "https://video.example.net")
~~~

Kiểm tra:

- Header có thực sự xuất hiện trên response document không?
- Header có bị reverse proxy, CDN, load balancer hoặc framework xóa/ghi đè không?
- Có response HTML khác cho route, locale, login hoặc error page không?
- Service worker hoặc cache có đang trả HTML cũ không?
- Có header trùng hoặc cấu hình khác nhau giữa staging và production không?
- Tên directive và origin có đúng chính tả không?

Đừng chỉ xem cấu hình Nginx, Node.js hoặc manifest. Browser chỉ xử lý header trên response mà nó thực sự nhận.

### 2.2 Header phải nằm trên response HTML cần áp dụng

Đặt header trên file JavaScript, ảnh hoặc response API không tạo policy cho document đang sử dụng chúng. Header phải được gửi cùng response của document cần áp dụng policy. Mỗi iframe document có thể nhận policy riêng để giới hạn chính nó và các descendant.

Nếu một route trả HTML qua nhiều tầng proxy, hãy kiểm tra response sau tất cả redirect và middleware. Một header chỉ được cấu hình ở một virtual host có thể không xuất hiện trên subdomain hoặc route khác.

### 2.3 Cú pháp Structured Headers

Permissions-Policy dùng cú pháp structured header:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net"), camera=(), microphone=()
~~~

Các quy tắc quan trọng:

- Nhiều directive được phân tách bằng dấu phẩy.
- Allowlist nằm trong ngoặc đơn.
- Origin được đặt trong dấu nháy kép.
- self là token, không đặt trong dấu nháy.
- () có nghĩa là không cho origin nào sử dụng feature.
- * cho phép mọi origin và chỉ dùng một mình trong allowlist.
- report-to là tham số của từng directive, không phải một directive độc lập.

Ví dụ sai do dùng cú pháp Feature Policy cũ:

~~~http
Permissions-Policy: geolocation 'self'; camera 'none'
~~~

Cú pháp mới:

~~~http
Permissions-Policy: geolocation=(self), camera=()
~~~

Header cũ Feature-Policy dùng cú pháp khác và đã được thay bằng Permissions-Policy. Không trộn hai cú pháp trong cùng cấu hình. Nếu cần hỗ trợ browser cũ, hãy kiểm tra hành vi thực tế và giữ fallback ở cấp ứng dụng; không giả định browser mới sẽ diễn giải header cũ.

### 2.4 Kiểm tra allowlist và origin

Origin gồm scheme, host và port. Các giá trị sau là các origin khác nhau:

- https://app.example.com
- http://app.example.com
- https://app.example.com:8443
- https://maps.example.com

Path không thuộc origin. Không ghi URL có path vào allowlist nếu directive yêu cầu origin.

Ví dụ:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net")
~~~

Origin trong iframe allow attribute có cú pháp khác:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'src'">
</iframe>
~~~

Trong HTML, origin cụ thể không đặt trong dấu nháy; các keyword đặc biệt như 'self', 'src' và 'none' có dấu nháy đơn. Không sao chép nguyên cú pháp header vào thuộc tính allow.

### 2.5 Default allowlist không giống nhau cho mọi feature

Nếu directive không xuất hiện trong header, browser áp dụng default allowlist được định nghĩa cho feature đó. Giá trị mặc định có thể là self hoặc * tùy directive. Không kết luận rằng bỏ một feature khỏi header đồng nghĩa tắt feature đó.

Khi audit các feature nhạy cảm, hãy khai báo rõ trạng thái mong muốn, ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=(), display-capture=()
~~~

Đối với feature cần dùng, liệt kê origin cụ thể. Kiểm tra trang tham chiếu của từng directive để biết default allowlist và browser support.

## 3. Chẩn đoán lỗi theo triệu chứng

### 3.1 Header không có tác dụng

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Feature vẫn hoạt động trên mọi iframe | Header không có trên document response hoặc browser không hỗ trợ header | Kiểm tra Network và ma trận tương thích |
| Chỉ một số route bị giới hạn | Header chỉ áp dụng trên một nhóm route | Chuẩn hóa middleware/server config cho mọi response HTML |
| Staging đúng, production sai | CDN/proxy xóa hoặc ghi đè header | So sánh response tại browser và origin server |
| Header xuất hiện hai lần | Nhiều middleware/proxy cùng thêm policy | Chọn một nơi quản lý header, kiểm tra giá trị cuối |
| Console không có violation | Browser không hỗ trợ báo cáo, API chưa được gọi hoặc feature không phát sinh report | Kiểm tra API thật, browser support và DevTools |

### 3.2 Directive không được nhận diện

Tên feature phải đúng identifier mà browser và specification hỗ trợ. Một API JavaScript và directive tương ứng không nhất thiết có tên giống nhau.

Ví dụ:

| API | Directive thường dùng |
|---|---|
| navigator.geolocation | geolocation |
| navigator.mediaDevices.getUserMedia() với video | camera |
| navigator.mediaDevices.getUserMedia() với audio | microphone |
| Element.requestFullscreen() | fullscreen |
| Clipboard read | clipboard-read |
| Clipboard write | clipboard-write |
| Screen Capture API | display-capture |

Không tự đặt directive như getUserMedia, screen-capture-api hoặc tên thư viện. Kiểm tra danh sách policy-controlled feature chính thức và support theo browser.

### 3.3 Header cho phép origin nhưng iframe vẫn bị chặn

Header là tập quyền tối đa có thể delegate. Iframe allow attribute thu hẹp quyền cho frame cụ thể. Cả hai cần cho phép origin.

Ví dụ header:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net")
~~~

Iframe:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation">
</iframe>
~~~

Nếu thiếu allow attribute trên iframe cross-origin, feature có thể không được delegate dù origin đã có trong header. Nếu header chỉ cho self, allow attribute của iframe không thể mở quyền cho một origin khác.

### 3.4 Child frame không thể bật lại feature đã bị ancestor tắt

Ví dụ:

~~~http
Permissions-Policy: camera=()
~~~

~~~html
<iframe
  src="https://widget.example.net"
  allow="camera *">
</iframe>
~~~

Camera vẫn bị chặn. Policy bị tắt ở ancestor là giới hạn một chiều; child không thể nới lỏng policy đó.

Khi có nhiều tầng iframe, kiểm tra từng ancestor từ top-level document đến frame trực tiếp chứa API. Một ancestor bất kỳ có thể là nơi feature bị tắt.

### 3.5 Redirect làm origin không khớp

Nếu iframe ban đầu tải từ https://widget.example.net rồi redirect sang https://login.partner.example, policy có thể không được áp dụng cho origin đích nếu origin đó không được liệt kê.

Kiểm tra redirect chain trong Network. Nếu luồng điều hướng là hợp lệ và cần feature, thêm origin đích một cách có chủ đích vào allowlist. Không dùng wildcard để che một redirect không rõ nguồn.

### 3.6 Feature được policy cho phép nhưng API vẫn lỗi

Permissions Policy chỉ trả lời feature có được phép trong document hay không. Browser vẫn có thể từ chối vì:

- Người dùng đã từ chối permission.
- Hệ điều hành chưa cấp quyền cho browser.
- Document không ở secure context.
- API hoặc thiết bị không được hỗ trợ.
- Thiếu user activation.
- Thiết bị đang được ứng dụng khác sử dụng.
- Quy tắc riêng của API hoặc browser đang áp dụng.

Ví dụ NotAllowedError từ camera không chứng minh Permissions Policy là nguyên nhân. Hãy kiểm tra Console, permission state, secure context và thông báo API.

### 3.7 Không nhầm Permissions API với Permissions Policy

navigator.permissions.query() báo trạng thái permission mà browser quản lý, ví dụ granted, prompt hoặc denied khi descriptor được hỗ trợ. Nó không phải API chuẩn hóa để đọc toàn bộ allowlist của Permissions Policy.

Ví dụ:

~~~js
async function inspectGeolocationPermission() {
  if (!navigator.permissions?.query) {
    return 'Permissions API không khả dụng';
  }

  try {
    const result = await navigator.permissions.query({
      name: 'geolocation'
    });
    return result.state;
  } catch (error) {
    return 'Không query được permission: ' + error.name;
  }
}
~~~

Nếu trạng thái là granted, policy vẫn có thể chặn feature. Nếu trạng thái là denied, nguyên nhân có thể là user permission hoặc browser policy. Luôn phân biệt hai lớp.

## 4. Kiểm tra policy bằng DevTools và JavaScript

### 4.1 Console và Network

Trong Console, tìm thông báo có cụm:

- Permissions policy violation
- Tên feature như geolocation, camera, microphone
- Thông tin frame hoặc nguồn script nếu browser cung cấp
- Lỗi API như NotAllowedError, SecurityError

Trong Network, kiểm tra response HTML của top-level document và response của từng iframe. Kiểm tra Permissions-Policy, Permissions-Policy-Report-Only, Reporting-Endpoints và URL sau redirect.

### 4.2 Application panel trong Chromium

Trên Chrome/Edge, mở DevTools → Application → Frames. Chọn frame cần audit và xem danh sách feature được phép hoặc bị chặn nếu phiên bản DevTools cung cấp bảng này.

Đối chiếu frame URL với allowlist. Một iframe có thể bị chặn bởi policy của parent ngay cả khi response của chính iframe không gửi header hạn chế.

### 4.3 JavaScript introspection có giới hạn

Specification mới mô tả document.permissionsPolicy và policy object với các method như allowsFeature(), features(), allowedFeatures() và getAllowlistForFeature(). Tuy nhiên, hỗ trợ browser chưa đồng đều.

API cũ document.featurePolicy/FeaturePolicy là non-standard và deprecated. Không dùng nó làm cơ chế enforcement hoặc kiểm tra tương thích bắt buộc.

Nếu dùng để hỗ trợ chẩn đoán trên browser đã xác minh:

~~~js
const policy = document.permissionsPolicy ?? document.featurePolicy;

if (policy?.allowsFeature) {
  console.log('Geolocation policy:', policy.allowsFeature('geolocation'));
} else {
  console.log('Không có API introspection policy trên browser này.');
}
~~~

Kết quả chỉ phản ánh policy trong context mà API hỗ trợ. Nó không xác nhận user permission, thiết bị, secure context hoặc user activation. Luôn kiểm tra hành vi API thật.

### 4.4 Feature detection không thay thế policy audit

~~~js
const capabilities = {
  geolocation: 'geolocation' in navigator,
  camera: Boolean(navigator.mediaDevices?.getUserMedia),
  clipboard: Boolean(navigator.clipboard),
  fullscreen: Boolean(document.documentElement.requestFullscreen)
};

console.table(capabilities);
~~~

Feature detection chỉ cho biết API có được expose hay không. Nó không chứng minh API sẽ thành công. Một API có thể tồn tại nhưng bị policy hoặc user permission chặn khi gọi.

## 5. Báo cáo vi phạm bằng Reporting API

### 5.1 Hai cách nhận báo cáo

Permissions Policy violation có thể được quan sát theo hai cách:

1. **Trong trang:** dùng ReportingObserver để nhận report mà browser đã tạo cho document.
2. **Trên server:** cấu hình Reporting-Endpoints và tham số report-to để browser gửi report về endpoint.

Reporting API không phải cơ chế bảo đảm mọi browser đều gửi report. Khả năng tạo report, gửi endpoint và nhận trong trang có thể khác nhau theo browser/version. DevTools vẫn là công cụ kiểm tra chính khi reporting không được hỗ trợ.

### 5.2 Khai báo endpoint

Ví dụ cấu hình endpoint tên pp:

~~~http
Reporting-Endpoints: pp="https://app.example.com/reports/permissions-policy"
~~~

Tên pp là endpoint identifier. URL là endpoint HTTPS nhận report. Endpoint nên có xác thực ở tầng mạng nếu phù hợp, rate limit, giới hạn body size và giám sát lỗi.

### 5.3 Gắn endpoint vào directive

Để nhận report cho các violation của policy enforcement:

~~~http
Reporting-Endpoints: pp="https://app.example.com/reports/permissions-policy"
Permissions-Policy: geolocation=();report-to=pp, camera=();report-to=pp, microphone=();report-to=pp
~~~

report-to là tham số của directive. Mỗi directive cần được gắn endpoint nếu muốn route report riêng. Có thể khai báo endpoint default để dùng làm nơi nhận mặc định khi browser hỗ trợ và không có endpoint riêng.

### 5.4 Report-Only để thử policy dự kiến

Ví dụ policy hiện tại cho phép geolocation trên same-origin, nhưng policy dự kiến muốn tắt:

~~~http
Reporting-Endpoints: pp="https://app.example.com/reports/permissions-policy"
Permissions-Policy: geolocation=(self), camera=(), microphone=()
Permissions-Policy-Report-Only: geolocation=();report-to=pp
~~~

Trong browser hỗ trợ, policy Report-Only không chặn feature chỉ vì policy thử nghiệm. Nếu hành vi vi phạm xảy ra, browser có thể tạo report với disposition là report. Policy enforcement hiện tại vẫn có hiệu lực; nếu enforcement đã chặn feature, report sẽ phản ánh disposition enforce.

Dùng Report-Only để phát hiện luồng nào sẽ bị ảnh hưởng trước khi thay đổi policy thật. Nó không đảm bảo mọi browser gửi report và không thay thế kiểm thử trên các luồng nghiệp vụ.

### 5.5 Report-Only không phải một cách bật feature

Nếu policy enforcement đặt camera=(), việc thêm Report-Only cho phép camera không thể bật lại camera. Report-Only chỉ quan sát policy thử nghiệm; policy enforcement và các ancestor vẫn là giới hạn thực tế.

Tương tự, nếu enforcement cho phép feature nhưng Report-Only cấm feature, browser có thể cho API tiếp tục hoạt động đồng thời gửi report về policy dự kiến. Đây là tình huống phù hợp để đánh giá migration.

### 5.6 Dạng report và trường dữ liệu

Report type của Permissions Policy là permissions-policy-violation. Body có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| featureId | Identifier của feature bị vi phạm |
| sourceFile | URL nguồn script nếu browser xác định được |
| lineNumber | Dòng nguồn nếu có |
| columnNumber | Cột nguồn nếu có |
| disposition | enforce hoặc report |
| allowAttribute | Giá trị allow của iframe trong potential violation report nếu có |
| srcAttribute | Giá trị src của iframe trong potential violation report nếu có |

Specification cũng định nghĩa potential-permissions-policy-violation cho tình huống có thể xác định iframe không được kế thừa quyền ngay khi container được xử lý. Hỗ trợ và thời điểm phát report có thể khác nhau; không giả định mọi browser gửi cả hai loại.

Có một khác biệt serialization cần xử lý: MDN ghi nhận Chrome server-side report có thể dùng policyId thay cho featureId; report đọc qua ReportingObserver theo spec dùng featureId. Backend nên chấp nhận cả hai.

### 5.7 Quan sát report trong trang

~~~js
if ('ReportingObserver' in window) {
  const observer = new ReportingObserver((reports) => {
    for (const report of reports) {
      if (
        report.type !== 'permissions-policy-violation' &&
        report.type !== 'potential-permissions-policy-violation'
      ) {
        continue;
      }

      const body = report.body || {};
      const feature = body.featureId || body.policyId || 'unknown';

      console.warn('Permissions Policy report', {
        type: report.type,
        feature,
        disposition: body.disposition,
        sourceFile: body.sourceFile,
        lineNumber: body.lineNumber,
        allowAttribute: body.allowAttribute,
        srcAttribute: body.srcAttribute
      });
    }
  }, {
    types: [
      'permissions-policy-violation',
      'potential-permissions-policy-violation'
    ],
    buffered: true
  });

  observer.observe();
}
~~~

Đăng ký observer sớm trước khi code gọi feature. Observer chỉ quan sát report mà browser hỗ trợ và tạo ra; không dùng nó làm điều kiện duy nhất để cho phép hoặc từ chối API.

### 5.8 Xử lý report ở server

Endpoint cần:

- Chỉ nhận POST.
- Giới hạn kích thước request body.
- Chấp nhận batch JSON thay vì giả định một object đơn.
- Chuẩn hóa featureId và policyId.
- Ghi nhận disposition, URL document, sourceFile và browser/version khi có.
- Giới hạn tần suất và chống spam.
- Không render URL hoặc dữ liệu report bằng HTML sink.
- Xóa query string hoặc thông tin nhạy cảm trước khi lưu nếu không cần.
- Không coi report là bằng chứng chắc chắn về hành vi độc hại.

Ví dụ chuẩn hóa payload ở Node.js:

~~~js
function normalizePolicyReport(report) {
  const body = report?.body || {};

  return {
    type: report?.type || 'unknown',
    documentUrl: report?.url || null,
    feature: body.featureId || body.policyId || 'unknown',
    disposition: body.disposition || 'unknown',
    sourceFile: body.sourceFile || null,
    lineNumber: body.lineNumber ?? null,
    columnNumber: body.columnNumber ?? null
  };
}
~~~

Dữ liệu report do client gửi về không đáng tin cậy. Validate schema và độ dài từng field trước khi đưa vào log hoặc dashboard.

## 6. Ma trận tương thích browser

### 6.1 Đọc ma trận đúng cách

Permissions Policy không phải một tính năng đơn nhất có cùng mức hỗ trợ ở mọi nơi. Cần tách:

- Header Permissions-Policy có được browser xử lý không?
- iframe allow có được parse và áp dụng không?
- Directive cụ thể có được triển khai không?
- Reporting-Only/ReportingObserver có được hỗ trợ không?
- API được kiểm soát có hoạt động trên thiết bị và phiên bản đó không?

Bảng dưới đây là ảnh chụp tương thích theo tài liệu MDN và Can I Use được kiểm tra tháng 11-2026. Đây là ma trận định hướng cho các browser desktop/mobile phổ biến; trước release hãy kiểm tra lại đúng phiên bản runtime và feature directive của ứng dụng.

### 6.2 Ma trận tổng quan

| Browser family | Permissions-Policy header | iframe allow | Permissions-Policy-Report-Only / violation reporting |
|---|---|---|---|
| Chrome / Chromium desktop | Có; Can I Use ghi nhận từ Chrome 85 | Thuộc tính iframe rộng rãi; directive cụ thể vẫn cần test | Có theo bảng tương thích từ Chrome 120 |
| Edge desktop (Chromium) | Có; từ Edge 85 | Thuộc tính iframe rộng rãi; directive cụ thể vẫn cần test | Có theo bảng tương thích từ Edge 120 |
| Opera desktop (Chromium) | Có; từ Opera 71 | Thuộc tính iframe rộng rãi; directive cụ thể vẫn cần test | Có theo bảng tương thích từ Opera 106 |
| Samsung Internet | Có; từ phiên bản 14 | Cần kiểm tra từng feature trên runtime thiết bị | Có theo bảng tương thích từ phiên bản 25 |
| Firefox desktop | Header không được hỗ trợ trong bảng tương thích hiện tại | Đừng suy ra enforcement đầy đủ chỉ từ việc attribute tồn tại | Report-Only và Permissions Policy violation reporting chưa được hỗ trợ trong bảng hiện tại |
| Firefox Android | Header/reporting chưa được hỗ trợ trong bảng tương thích hiện tại | Kiểm thử API và frame thực tế | Report-Only/reporting chưa được hỗ trợ |
| Safari macOS | Header không được hỗ trợ trong bảng tương thích hiện tại | Không dựa vào allow để enforcement nếu runtime không hỗ trợ policy | Report-Only/reporting chưa được hỗ trợ |
| Safari iOS / WebView iOS | Header/reporting chưa được hỗ trợ trong bảng tương thích hiện tại | Phụ thuộc WebKit runtime; kiểm thử trên thiết bị thật | Report-Only/reporting chưa được hỗ trợ |

HTMLIFrameElement.allow là thuộc tính HTML đã được hỗ trợ rộng rãi trên nhiều browser từ lâu. Điều đó không đồng nghĩa mọi browser triển khai toàn bộ Permissions Policy header hoặc tất cả feature được đặt trong allow. Cần tách hỗ trợ cú pháp DOM với enforcement thực tế.

### 6.3 Các mốc tương thích cần nhớ

Theo bảng Can I Use được kiểm tra trong tháng 11-2026:

- Permissions-Policy header: Chrome 85+, Edge 85+, Opera 71+ và Samsung Internet 14+; Firefox và Safari chưa hỗ trợ trong dữ liệu hiện tại.
- Permissions-Policy-Report-Only: Chrome 120+, Edge 120+, Opera 106+ và Samsung Internet 25+; Firefox/Safari chưa hỗ trợ trong dữ liệu hiện tại.
- permissions-policy-violation report: hỗ trợ theo nhóm Chromium từ khoảng Chrome 120; Firefox/Safari chưa hỗ trợ trong bảng tương thích report.
- document.featurePolicy: API cũ, non-standard/deprecated; không lấy nó làm tiêu chí hỗ trợ Permissions Policy chuẩn.

Các mốc phiên bản có thể thay đổi khi browser phát hành mới hoặc dữ liệu tương thích được cập nhật. Kiểm tra MDN/Can I Use tại thời điểm release và thử trên browser thực tế của người dùng.

### 6.4 Ma trận theo capability

| Capability | Dùng để | Khi thiếu hỗ trợ |
|---|---|---|
| Header enforcement | Giới hạn feature cho document và descendant | Không dựa vào header để bảo vệ browser không hỗ trợ; hạn chế tích hợp ở cấp ứng dụng và kiểm thử quyền mặc định |
| iframe allow | Thu hẹp quyền cho từng frame | Không nhúng nội dung không tin cậy cần feature nhạy cảm nếu không thể kiểm soát bằng runtime |
| Report-Only | Quan sát policy dự kiến trước enforcement | Dùng staging, DevTools, log API và test matrix thủ công |
| Reporting-Endpoints | Gửi violation tới server | Dùng Console/ReportingObserver nếu có; không giả định endpoint nhận đủ report |
| ReportingObserver | Thu thập report trong document | Dùng DevTools và server reporting; feature detection trước khi tạo observer |
| Policy introspection | Đọc trạng thái policy qua JS | Không phụ thuộc API non-standard; kiểm tra header, frame chain và hành vi API |
| Feature API | Camera/geolocation/fullscreen/... | Kiểm tra secure context, user permission, thiết bị, user activation và fallback |

### 6.5 Không suy rộng hỗ trợ từ Chromium sang mọi browser

Edge, Opera và Samsung Internet dựa trên Chromium nhưng có thể dùng phiên bản engine khác nhau hoặc có cấu hình riêng. WebView còn phụ thuộc phiên bản Android System WebView và ứng dụng host. Safari iOS phụ thuộc WebKit runtime của hệ điều hành.

Kiểm thử ma trận theo engine/version thực tế, không chỉ theo tên browser. Đặc biệt, nếu ứng dụng chạy trong WebView hoặc trình duyệt nhúng, hãy kiểm tra chính runtime mà người dùng đang sử dụng.

## 7. Ma trận kiểm thử policy

### 7.1 Các tình huống tối thiểu

| ID | Header parent | iframe allow | User permission | Kết quả mong đợi trong browser hỗ trợ |
|---|---|---|---|---|
| P01 | geolocation=(self) | Không có iframe | Granted | Parent được phép gọi geolocation |
| P02 | geolocation=(self "https://maps.example") | geolocation | Granted | Origin maps được delegate |
| P03 | geolocation=(self) | geolocation trên iframe cross-origin | Granted | Child vẫn bị chặn vì origin không nằm trong superset |
| P04 | geolocation=() | geolocation * | Granted | Child và parent đều bị chặn |
| P05 | Cho phép origin widget | Thiếu allow | Granted | Cross-origin iframe không nhận quyền qua container policy |
| P06 | Cho phép origin ban đầu | allow không liệt kê redirect target | Granted | Origin sau redirect không tự động nhận quyền |
| P07 | Cho phép feature | Đúng | Denied | Policy cho phép nhưng user permission vẫn từ chối |
| P08 | Cho phép feature | Đúng | Prompt | Browser có thể hỏi người dùng theo API |
| P09 | Report-Only cấm, enforcement cho phép | Đúng | Granted | Feature tiếp tục hoạt động; report có disposition report nếu hỗ trợ |
| P10 | Browser không hỗ trợ header | Bất kỳ | Granted | Không dựa vào header để enforcement; xác minh fallback |
| P11 | Feature API không được browser hỗ trợ | Đúng | N/A | Feature detection báo không có API |
| P12 | Ancestor tắt feature | Child cố bật lại | Granted | Child không thể bật lại feature |

### 7.2 Kiểm thử cả đường đi thành công và thất bại

Với mỗi feature, cần ít nhất các trường hợp:

- Feature được policy cho phép và user permission được cấp.
- Feature bị policy chặn.
- Feature được policy cho phép nhưng user permission bị từ chối.
- API không tồn tại trên browser mục tiêu.
- Iframe cùng origin và iframe cross-origin.
- Redirect sang origin khác.
- Report-Only và enforcement.
- Trang tải trực tiếp và trang được nhúng nhiều tầng.

Không dùng một lần thử camera thành công trên Chrome desktop để kết luận policy đúng trên Safari iOS hoặc Android WebView.

## 8. Quy trình rollout và xử lý hồi quy

### 8.1 Lập inventory trước khi thay đổi

Ghi lại:

- Feature identifier.
- Document/route cần feature.
- Origin nào cần quyền.
- Iframe nào sử dụng feature.
- Header hiện tại và allow attribute.
- Browser/runtime cần hỗ trợ.
- User permission và secure-context requirement.
- Owner của tích hợp bên thứ ba.

Tìm mọi iframe và feature API trong source. Kết hợp tìm kiếm code với quan sát Network/Console vì script bên thứ ba có thể tạo iframe hoặc gọi API động.

### 8.2 Bắt đầu từ policy mong muốn, không từ danh sách lỗi

Xác định feature nào phải tắt mặc định và origin nào thực sự cần dùng. Ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=(self "https://maps.example.net"), fullscreen=(self "https://video.example.net"), clipboard-read=(self), clipboard-write=(self)
~~~

Đây là policy minh họa. Kiểm tra feature identifier và browser support trước khi áp dụng. Không đưa một origin vào allowlist chỉ vì report cho thấy nó từng gọi API.

### 8.3 Chạy Report-Only ở staging

~~~http
Reporting-Endpoints: pp="https://app.example.com/reports/permissions-policy"
Permissions-Policy: camera=(), microphone=(), geolocation=(self "https://maps.example.net")
Permissions-Policy-Report-Only: geolocation=();report-to=pp, camera=();report-to=pp, microphone=();report-to=pp
~~~

Chạy các luồng login, thanh toán, upload, bản đồ, hội nghị, fullscreen và widget. Phân loại report theo feature, route, frame, origin và browser. Sửa policy hoặc ứng dụng theo nhu cầu thực tế.

### 8.4 Chuyển enforcement theo từng nhóm route

Không bật policy mới đồng loạt nếu ứng dụng có nhiều legacy route và tích hợp bên thứ ba. Chuyển từng nhóm route hoặc cohort người dùng, theo dõi lỗi API và tỷ lệ hoàn tất tác vụ. Nếu browser không hỗ trợ Report-Only, dùng staging và kiểm thử thủ công trước khi bật enforcement.

### 8.5 Chuẩn bị rollback

Trước khi phát hành, xác định:

- Header cũ có thể khôi phục nhanh ở đâu?
- Route nào cần rollback riêng?
- Làm sao nhận biết feature bị chặn làm hỏng luồng nghiệp vụ?
- Có thể tắt tích hợp bên thứ ba bị lỗi không?
- Có fallback UI khi browser không cho phép feature không?

Rollback policy không thay thế sửa lỗi. Sau khi khôi phục chức năng, ghi lại nguyên nhân và lên lịch siết lại policy.

## 9. Lab: audit Permissions Policy trên hai origin localhost

Lab tạo parent ở port 3000 và iframe child ở port 3001. Hai port khác nhau tạo hai origin. Có ba chế độ:

- allow: policy cho phép geolocation trên parent và child.
- report: enforcement cho phép, Report-Only thử tắt geolocation.
- enforce: enforcement tắt geolocation cho tất cả.

Lab dùng geolocation; browser có thể yêu cầu user permission. Chỉ cấp quyền nếu muốn thử. Không có dữ liệu vị trí được gửi tới server.

### 9.1 Tạo file permissions-policy-lab.mjs

~~~js
import { createServer } from 'node:http';

const mode = process.env.PP_MODE || 'report';
if (!['allow', 'report', 'enforce'].includes(mode)) {
  throw new Error('PP_MODE must be allow, report or enforce');
}

const parentHtml = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head><meta charset="utf-8"><title>Permissions Policy audit</title></head>',
  '<body>',
  '<h1>Parent: localhost:3000</h1>',
  '<p>Mode: ' + mode + '</p>',
  '<button id="geo" type="button">Thử geolocation ở parent</button>',
  '<pre id="result">Chưa thử.</pre>',
  '<iframe src="http://localhost:3001/child" title="Cross-origin child" ',
  'allow="geolocation" width="650" height="260"></iframe>',
  '<script>',
  'const result = document.querySelector("#result");',
  'if ("ReportingObserver" in window) {',
  '  const observer = new ReportingObserver((reports) => {',
  '    for (const report of reports) {',
  '      const body = report.body || {};',
  '      console.log("Policy report", {',
  '        type: report.type,',
  '        feature: body.featureId || body.policyId,',
  '        disposition: body.disposition,',
  '        sourceFile: body.sourceFile',
  '      });',
  '    }',
  '  }, {',
  '    types: ["permissions-policy-violation", "potential-permissions-policy-violation"],',
  '    buffered: true',
  '  });',
  '  observer.observe();',
  '} else {',
  '  console.log("ReportingObserver không được hỗ trợ.");',
  '}',
  'document.querySelector("#geo").addEventListener("click", () => {',
  '  if (!navigator.geolocation) {',
  '    result.textContent = "Geolocation API không khả dụng.";',
  '    return;',
  '  }',
  '  navigator.geolocation.getCurrentPosition(',
  '    () => { result.textContent = "Geolocation thành công; lab không hiển thị tọa độ."; },',
  '    error => { result.textContent = error.name + ": " + error.message; }',
  '  );',
  '});',
  '</script>',
  '</body></html>'
].join('\n');

const childHtml = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head><meta charset="utf-8"><title>Child frame</title></head>',
  '<body>',
  '<h2>Child: localhost:3001</h2>',
  '<button id="geo" type="button">Thử geolocation trong iframe</button>',
  '<pre id="result">Chưa thử.</pre>',
  '<script>',
  'const result = document.querySelector("#result");',
  'if ("ReportingObserver" in window) {',
  '  const observer = new ReportingObserver((reports) => {',
  '    for (const report of reports) {',
  '      console.log("Child policy report", report.type, report.body);',
  '    }',
  '  }, { types: ["permissions-policy-violation"], buffered: true });',
  '  observer.observe();',
  '}',
  'document.querySelector("#geo").addEventListener("click", () => {',
  '  navigator.geolocation.getCurrentPosition(',
  '    () => { result.textContent = "Geolocation thành công; không hiển thị tọa độ."; },',
  '    error => { result.textContent = error.name + ": " + error.message; }',
  '  );',
  '});',
  '</script>',
  '</body></html>'
].join('\n');

const parent = createServer((req, res) => {
  if (req.url === '/reports/pp' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString('utf8');
      if (body.length > 65536) {
        req.destroy();
      }
    });
    req.on('end', () => {
      console.log('Reporting API payload:', body.slice(0, 65536));
      res.writeHead(204);
      res.end();
    });
    return;
  }

  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Reporting-Endpoints': 'pp="http://localhost:3000/reports/pp"'
  };

  if (mode === 'allow' || mode === 'report') {
    headers['Permissions-Policy'] =
      'geolocation=(self "http://localhost:3001"), camera=(), microphone=()';
  } else {
    headers['Permissions-Policy'] =
      'geolocation=(), camera=(), microphone=()';
  }

  if (mode === 'report') {
    headers['Permissions-Policy-Report-Only'] =
      'geolocation=();report-to=pp';
  }

  res.writeHead(200, headers);
  res.end(parentHtml);
});

const child = createServer((req, res) => {
  if (req.url !== '/child') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(childHtml);
});

parent.listen(3000, 'localhost', () => {
  console.log('Parent: http://localhost:3000');
  console.log('Mode:', mode);
});

child.listen(3001, 'localhost', () => {
  console.log('Child:  http://localhost:3001/child');
});
~~~

### 9.2 Chạy chế độ allow

~~~bash
node permissions-policy-lab.mjs
~~~

Mặc định là report; để chạy allow trên PowerShell:

~~~powershell
$env:PP_MODE = "allow"
node permissions-policy-lab.mjs
~~~

Mở http://localhost:3000. Header cho phép geolocation trên parent và origin child; iframe có allow="geolocation". Nhấn từng nút và xử lý prompt nếu browser hỏi.

### 9.3 Chạy chế độ report

Dừng server rồi chạy:

~~~powershell
$env:PP_MODE = "report"
node permissions-policy-lab.mjs
~~~

Enforcement vẫn cho geolocation, còn Report-Only thử cấm feature. Trong browser hỗ trợ, khi gọi API, quan sát report có disposition report trong Console và thử nhận payload ở terminal server.

Nếu endpoint report không được browser hỗ trợ hoặc bị chặn trên HTTP localhost, dùng Console/ReportingObserver và chạy lab trên HTTPS staging để kiểm tra Reporting-Endpoints. Không kết luận policy không hoạt động chỉ vì server chưa nhận report.

### 9.4 Chạy chế độ enforce

~~~powershell
$env:PP_MODE = "enforce"
node permissions-policy-lab.mjs
~~~

Header đặt geolocation=(). Dù iframe vẫn có allow="geolocation", cả parent và child đều không thể bật lại feature. Quan sát Console, API error và report có disposition enforce nếu browser hỗ trợ.

### 9.5 Ma trận kết quả lab

| Mode | Parent | Child iframe | Report |
|---|---|---|---|
| allow | Policy cho phép; còn cần user permission | Được delegate qua header và allow | Không có report do policy này |
| report | Enforcement cho phép; Report-Only thử cấm | Inherited policy có thể phát report khi gọi API | disposition=report nếu browser hỗ trợ |
| enforce | Bị policy chặn | Bị ancestor policy chặn; allow không thể mở lại | disposition=enforce nếu browser hỗ trợ |

Sau lab, dừng cả hai server. Có thể thu hồi quyền geolocation của localhost trong cài đặt browser nếu muốn kiểm thử lại prompt.

## 10. Lỗi thường gặp khi triển khai reporting

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Không nhận report ở server | Browser không hỗ trợ Reporting API hoặc endpoint không reachable | Kiểm tra compatibility, HTTPS, Reporting-Endpoints và Network |
| ReportingObserver không tồn tại | Browser/runtime chưa hỗ trợ | Feature-detect và dùng DevTools |
| Report không có featureId | Khác biệt serialization hoặc payload không đúng loại | Chấp nhận policyId như fallback |
| Report-Only không chặn API | Hành vi đúng của chế độ report-only | Dùng enforcement header khi đã sẵn sàng |
| Có report nhưng không biết iframe nào | Report body thiếu allow/src hoặc browser không cung cấp potential report | Gắn log theo frame URL, kiểm tra DOM và Network |
| Endpoint bị quá tải | Lặp API call hoặc nhiều client gửi report | Rate limit, sampling và nhóm report theo feature |
| Report chứa URL nhạy cảm | sourceFile/document URL có query hoặc identifier | Redact query string và giới hạn thời gian lưu |
| Report không xuất hiện dù Console báo lỗi | Reporting API và Console là hai kênh riêng | Dùng cả Console và server reporting; không dựa vào một kênh |

## 11. Checklist Policy audit trước phát hành

### Response và syntax

- [ ] Kiểm tra response HTML cuối cùng trong Network.
- [ ] Xác nhận header không bị CDN/proxy xóa hoặc ghi đè.
- [ ] Dùng cú pháp Permissions-Policy structured header, không dùng Feature-Policy cũ.
- [ ] Kiểm tra directive identifier và default allowlist của từng feature.
- [ ] Không gửi allowlist wildcard nếu không có lý do.

### Iframe và inheritance

- [ ] Kiểm tra policy của mọi ancestor.
- [ ] Header chứa superset origin được phép.
- [ ] Iframe cross-origin có allow attribute đúng feature.
- [ ] Kiểm tra origin chính xác gồm scheme/host/port.
- [ ] Kiểm tra redirect và origin đích.
- [ ] Xác minh sandbox, CSP frame-src và frame-ancestors độc lập.

### API và permission

- [ ] Kiểm tra secure context.
- [ ] Feature detection API.
- [ ] Kiểm tra user activation và document focus nếu API yêu cầu.
- [ ] Phân biệt Permissions Policy với user permission/OS permission.
- [ ] Xử lý NotAllowedError và fallback UX.

### Reporting và compatibility

- [ ] Kiểm tra Reporting-Endpoints và report-to nếu browser hỗ trợ.
- [ ] Chạy Report-Only trước enforcement.
- [ ] Đăng ký ReportingObserver bằng feature detection.
- [ ] Chuẩn hóa featureId/policyId và disposition.
- [ ] Kiểm thử Chrome, Edge, Firefox, Safari và mobile/WebView mục tiêu.
- [ ] Có test riêng cho từng feature directive, không suy rộng từ header parser.
- [ ] Chuẩn bị fallback và rollback.

**Ghi nhớ:** Một policy chỉ được audit đầy đủ khi response header, inheritance, iframe allow, browser support và user permission đều được kiểm tra. Dùng DevTools để xác minh hành vi thật, Report-Only để quan sát trước enforcement khi có hỗ trợ, và ma trận browser để tránh dựa vào một implementation Chromium cho toàn bộ người dùng.

## Tài liệu tham khảo

- [W3C — Permissions Policy (Working Draft, 26 October 2026)](https://www.w3.org/TR/permissions-policy/)
- [MDN — Permissions Policy guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
- [MDN — Permissions-Policy-Report-Only header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy-Report-Only)
- [MDN — PermissionsPolicyViolationReport](https://developer.mozilla.org/en-US/docs/Web/API/PermissionsPolicyViolationReport)
- [MDN — ReportingObserver](https://developer.mozilla.org/en-US/docs/Web/API/ReportingObserver)
- [MDN — HTMLIFrameElement.allow](https://developer.mozilla.org/en-US/docs/Web/API/HTMLIFrameElement/allow)
- [Can I Use — Permissions-Policy header](https://caniuse.com/mdn-http_headers_permissions-policy)
- [Can I Use — Permissions-Policy-Report-Only](https://caniuse.com/mdn-http_headers_permissions-policy-report-only)
- [Chrome for Developers — Control browser features with Permissions Policy](https://developer.chrome.com/docs/privacy-security/permissions-policy)

