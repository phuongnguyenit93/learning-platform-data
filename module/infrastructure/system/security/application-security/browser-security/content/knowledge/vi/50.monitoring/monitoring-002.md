# CSP violation

Content Security Policy (CSP) giúp trình duyệt giới hạn những tài nguyên và hành động mà một trang web được phép thực hiện. Khi nội dung vi phạm chính sách, trình duyệt có thể chặn hành động đó và phát sinh một báo cáo vi phạm. CSP violation monitoring thu thập, phân tích và theo dõi các báo cáo này để phát hiện cấu hình sai, thay đổi ngoài dự kiến, tích hợp bên thứ ba không phù hợp hoặc dấu hiệu khai thác.

Một báo cáo CSP là tín hiệu kỹ thuật, không tự động chứng minh có tấn công. Nó có thể xuất hiện khi ứng dụng triển khai một script mới, khi extension chèn mã, khi trình duyệt chặn một tài nguyên hợp lệ theo chính sách hiện tại hoặc khi có nội dung không đáng tin cậy cố thực thi. Cần kết hợp báo cáo với chính sách đang áp dụng, URL, browser, phiên bản phát hành và hành vi thực tế để xác định nguyên nhân.

Bài học thuộc module <code>SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY</code>, tập trung vào ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web. Nội dung trình bày cách giám sát vi phạm CSP để hỗ trợ phòng vệ XSS, CSRF và clickjacking; cách tiếp nhận báo cáo an toàn; cách phân loại nhiễu; và cách dùng dữ liệu quan sát để cải thiện chính sách bảo mật.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích khi nào trình duyệt phát sinh CSP violation và phân biệt chính sách enforce với Report-Only.
- Cấu hình endpoint nhận báo cáo bằng cơ chế tương thích cũ và Reporting API.
- Đọc các trường quan trọng trong báo cáo legacy, báo cáo Reporting API và sự kiện <code>securitypolicyviolation</code>.
- Xây dựng endpoint tiếp nhận dữ liệu không đáng tin cậy, giới hạn kích thước, chuẩn hóa và giảm thiểu dữ liệu nhạy cảm.
- Phân loại vi phạm thành lỗi cấu hình, thay đổi ứng dụng, tích hợp bên thứ ba, hành vi extension hoặc dấu hiệu tấn công.
- Theo dõi xu hướng, phát hiện hồi quy và dùng báo cáo để triển khai CSP an toàn.

## 1. CSP violation là gì?

CSP là một chính sách do máy chủ ứng dụng gửi tới trình duyệt, thường qua HTTP response header <code>Content-Security-Policy</code>. Chính sách có thể giới hạn nguồn script, style, image, font, kết nối mạng, frame, object, worker và nhiều hành vi khác. Khi một hành động không đáp ứng chính sách, trình duyệt xử lý theo chế độ của policy và có thể phát sinh vi phạm.

Ví dụ, trang chỉ cho phép script từ origin của chính nó:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Nếu trang cố tải script từ một origin không được cho phép, trình duyệt có thể chặn request và tạo báo cáo. Nếu trang cố thực thi một khối script inline trong khi policy không cho phép inline script, trình duyệt có thể chặn việc thực thi và tạo báo cáo tương ứng.

Một vi phạm có thể liên quan tới:

- Script hoặc style inline không được cho phép.
- JavaScript sử dụng <code>eval()</code> hoặc cơ chế tương đương khi policy không cho phép.
- Script, stylesheet, image, font hoặc media tải từ nguồn không nằm trong allowlist.
- Request <code>fetch()</code>, XHR, WebSocket hoặc kết nối khác bị <code>connect-src</code> giới hạn.
- Iframe hoặc cửa sổ nhúng không đáp ứng <code>frame-src</code>, <code>child-src</code> hoặc <code>frame-ancestors</code>.
- Form gửi dữ liệu tới đích không được <code>form-action</code> cho phép.
- Tài liệu có <code>base</code> URL không phù hợp với <code>base-uri</code>.
- Worker hoặc plugin bị giới hạn bởi directive tương ứng.

CSP violation không chỉ xuất hiện khi có payload XSS. Một lần triển khai frontend đổi domain CDN, thêm analytics, thay đổi bundler hoặc đưa inline style mới cũng có thể làm phát sinh báo cáo.

### Vi phạm ở chế độ enforce và Report-Only

Có hai chế độ cần phân biệt:

| Chế độ | Header | Hành vi | Mục đích |
|---|---|---|---|
| Enforce | <code>Content-Security-Policy</code> | Trình duyệt áp dụng chính sách và chặn hành động vi phạm | Bảo vệ người dùng |
| Report-Only | <code>Content-Security-Policy-Report-Only</code> | Trình duyệt ghi nhận vi phạm nhưng không chặn theo policy này | Quan sát chính sách trước khi enforce |

Khi một policy ở chế độ Report-Only ghi nhận script inline, script đó vẫn có thể chạy nếu không bị một policy enforce khác chặn. Vì vậy, không diễn giải một báo cáo có <code>disposition</code> là <code>report</code> thành bằng chứng rằng trình duyệt đã chặn nội dung.

Một response có thể chứa nhiều CSP policy. Các policy enforce được áp dụng độc lập; thêm một policy chặt hơn không làm policy cũ yếu đi. Policy Report-Only cũng có thể tạo thêm báo cáo cho cùng một hành động. Khi phân tích, cần biết chính xác policy nào tạo ra từng báo cáo.

<code>Content-Security-Policy-Report-Only</code> phải được gửi qua HTTP response header; không dùng thẻ <code>meta</code> để thay thế cơ chế này. Một số directive chỉ có ý nghĩa trong header và khả năng báo cáo cũng phụ thuộc browser.

## 2. Luồng giám sát CSP

Một hệ thống giám sát cơ bản có các bước:

1. Ứng dụng trả CSP policy cùng thông tin endpoint báo cáo.
2. Trình duyệt tải trang và đánh giá các hành động theo policy.
3. Khi phát hiện vi phạm, trình duyệt áp dụng hành vi enforce hoặc Report-Only.
4. Trình duyệt có thể gửi báo cáo tới endpoint theo cơ chế được hỗ trợ.
5. Endpoint kiểm tra định dạng, giới hạn kích thước và chuẩn hóa trường dữ liệu.
6. Hệ thống lưu sự kiện đã giảm thiểu dữ liệu, gom nhóm và phát hiện xu hướng.
7. Nhóm phát triển xác minh nguyên nhân, điều chỉnh ứng dụng hoặc policy, rồi theo dõi lại.

~~~mermaid
flowchart TD
    A["HTTP response chứa CSP"] --> B["Browser đánh giá hành động"]
    B --> C{"Có vi phạm policy?"}
    C -->|Không| D["Tiếp tục theo policy"]
    C -->|Có| E["Enforce hoặc Report-Only"]
    E --> F["Tạo violation event/report"]
    F --> G["Endpoint nhận báo cáo"]
    G --> H["Validate, giới hạn và chuẩn hóa"]
    H --> I["Lưu sự kiện đã giảm thiểu"]
    I --> J["Gom nhóm và phân tích"]
    J --> K["Điều tra, sửa ứng dụng hoặc policy"]
~~~

Báo cáo được gửi không đồng bộ và có thể được trình duyệt gom nhóm hoặc trì hoãn. Không xem endpoint nhận báo cáo là một cơ chế chặn request. Việc thực thi CSP diễn ra trong trình duyệt theo policy; endpoint chỉ nhận tín hiệu để quan sát.

Báo cáo có thể không tới máy chủ vì browser không hỗ trợ cơ chế đã cấu hình, endpoint không truy cập được, mạng bị gián đoạn, người dùng đóng tab, chính sách quyền riêng tư hoặc cơ chế giảm tần suất báo cáo. Vì vậy, không dùng số lượng báo cáo làm thước đo duy nhất để kết luận rằng CSP đang hoạt động.

## 3. Cấu hình endpoint báo cáo

CSP có hai cơ chế báo cáo thường gặp: <code>report-uri</code> và <code>report-to</code> kết hợp với Reporting API. <code>report-uri</code> là cơ chế cũ, vẫn hữu ích cho khả năng tương thích. <code>report-to</code> sử dụng một nhóm endpoint được khai báo bằng header <code>Reporting-Endpoints</code> trên các browser hỗ trợ.

Để hỗ trợ nhiều phiên bản browser, có thể cấu hình cả hai trong giai đoạn chuyển tiếp và xác minh hành vi thực tế trên ma trận trình duyệt của sản phẩm.

### Cấu hình Reporting API

Ví dụ response header:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.test/csp-reports"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri /csp-reports
~~~

Trong ví dụ:

- <code>Reporting-Endpoints</code> ánh xạ tên nhóm <code>csp-endpoint</code> tới URL nhận báo cáo.
- <code>report-to csp-endpoint</code> yêu cầu browser dùng nhóm endpoint đã khai báo khi hỗ trợ cơ chế này.
- <code>report-uri /csp-reports</code> cung cấp đường tương thích cho browser còn dùng cơ chế cũ.
- Header đang dùng là <code>Content-Security-Policy-Report-Only</code>, nên policy này chỉ báo cáo và không chặn nội dung.

Khi đã xác minh policy, ứng dụng có thể chuyển sang header enforce:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri /csp-reports
~~~

Endpoint nên dùng HTTPS và thuộc hạ tầng do tổ chức kiểm soát. Ví dụ dùng cùng origin giúp đơn giản hóa cấu hình và vận hành. Không đưa token, email, session ID hoặc thông tin cá nhân vào URL endpoint hay query string.

### Cấu hình legacy report-uri

Cấu hình tối thiểu cho cơ chế cũ:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-reports
~~~

Browser hỗ trợ <code>report-uri</code> có thể gửi request POST với Content-Type thường là <code>application/csp-report</code>. Body JSON thường có wrapper <code>csp-report</code>:

~~~json
{
  "csp-report": {
    "document-uri": "https://app.example.test/account",
    "referrer": "https://app.example.test/",
    "violated-directive": "script-src-elem",
    "effective-directive": "script-src-elem",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /csp-reports",
    "blocked-uri": "https://cdn.example.invalid/widget.js",
    "status-code": 200,
    "source-file": "https://app.example.test/account",
    "line-number": 42,
    "column-number": 3
  }
}
~~~

Tên trường trong định dạng legacy thường dùng dấu gạch nối. Không giả định tất cả trường đều xuất hiện; browser có thể bỏ một số giá trị hoặc rút gọn URL vì lý do riêng tư.

### Cấu hình và kiểm tra header

Dùng Network panel trong DevTools để xác nhận response thực tế chứa đúng header. Kiểm tra cả trang HTML chính và các route quan trọng vì CSP thường được cấu hình ở reverse proxy, CDN hoặc application server theo từng route.

Các lỗi cấu hình thường gặp:

- Header <code>Reporting-Endpoints</code> thiếu hoặc tên endpoint không khớp với tên trong <code>report-to</code>.
- Endpoint dùng HTTP trong khi môi trường yêu cầu HTTPS.
- Policy Report-Only được đặt trong meta tag thay vì HTTP header.
- Header CSP bị ghi đè hoặc lặp lại ngoài dự kiến ở proxy/CDN.
- Endpoint trả redirect hoặc lỗi 4xx/5xx.
- Chỉ cấu hình một cơ chế báo cáo trong khi sản phẩm cần hỗ trợ browser cũ.
- Đưa URL endpoint chứa dữ liệu nhạy cảm.

Không xóa policy enforce hiện có chỉ để thử endpoint báo cáo. Có thể thêm policy Report-Only song song trong môi trường kiểm thử để quan sát thay đổi mà không làm giảm bảo vệ đang hoạt động.

## 4. Đọc cấu trúc báo cáo

### Các trường quan trọng

Một CSP violation report có thể chứa những trường sau. Tên trường thay đổi giữa định dạng legacy và Reporting API:

| Ý nghĩa | Legacy report-uri | Reporting API |
|---|---|---|
| URL tài liệu | <code>document-uri</code> | <code>body.documentURL</code> |
| Directive hiệu lực | <code>effective-directive</code> | <code>body.effectiveDirective</code> |
| Directive vi phạm | <code>violated-directive</code> | Thường dùng <code>body.effectiveDirective</code> |
| Policy gốc | <code>original-policy</code> | <code>body.originalPolicy</code> |
| Tài nguyên bị chặn | <code>blocked-uri</code> | <code>body.blockedURL</code> |
| Referrer | <code>referrer</code> | <code>body.referrer</code> |
| Nguồn phát sinh | <code>source-file</code> | <code>body.sourceFile</code> |
| Dòng và cột | <code>line-number</code>, <code>column-number</code> | <code>body.lineNumber</code>, <code>body.columnNumber</code> |
| HTTP status | <code>status-code</code> | <code>body.statusCode</code> |
| Chế độ | Thường suy ra từ policy | <code>body.disposition</code> |
| Loại report | Không có wrapper type riêng | <code>type</code> ở phần tử report |

Trong Reporting API, payload thường là một mảng report. Mỗi phần tử có thể có <code>type</code>, <code>url</code>, <code>user_agent</code> và object <code>body</code>. Với CSP, type thường là <code>csp-violation</code>. Một request có thể chứa nhiều report.

### effective-directive và violated-directive

<code>effective-directive</code> cho biết directive thực tế áp dụng để đánh giá hành động. Đây là trường quan trọng để phân tích vì CSP có quy tắc fallback. Ví dụ, nếu policy không khai báo <code>script-src-elem</code>, browser có thể dùng <code>script-src</code> hoặc <code>default-src</code> làm fallback cho phần tử script. Báo cáo có thể cho biết directive hiệu lực thay vì directive mà người viết policy nghĩ rằng đang được áp dụng.

Dùng directive hiệu lực để nhóm sự kiện, sau đó đối chiếu với toàn bộ policy. Không suy luận directive gây lỗi chỉ từ tên tài nguyên bị chặn.

### blocked-uri

<code>blocked-uri</code> hoặc <code>blockedURL</code> mô tả nguồn bị policy từ chối. Giá trị có thể là URL đầy đủ, origin, đường dẫn rút gọn hoặc nhãn như <code>inline</code>, <code>eval</code>, <code>data</code> hay <code>blob</code>.

Browser có thể loại bỏ path, query hoặc fragment để hạn chế rò rỉ dữ liệu. Vì vậy:

- Không yêu cầu trường này luôn là URL tuyệt đối.
- Không dùng nó làm URL để máy chủ tự động truy cập hoặc tải tài nguyên.
- Không xem mọi hostname lạ là tấn công; đó có thể là CDN, extension hoặc tích hợp hợp lệ.
- Chuẩn hóa và giới hạn độ dài trước khi lưu.

### disposition

<code>disposition</code> thường phân biệt <code>enforce</code> với <code>report</code>. Khi disposition là <code>report</code>, policy tương ứng đang ở chế độ Report-Only. Khi là <code>enforce</code>, policy được áp dụng để chặn hành động vi phạm.

Nếu định dạng cũ không có trường này, hãy đối chiếu với header policy đang được triển khai tại thời điểm xảy ra sự kiện. Đừng suy ra chế độ chỉ từ việc endpoint nhận được báo cáo.

### source-file, line-number và column-number

Các trường vị trí giúp tìm nơi phát sinh hành động, nhưng không phải lúc nào cũng chỉ đúng file source ban đầu. Bundle, minification, inline script, source map và extension có thể làm vị trí khác với mã nguồn mà nhóm đang đọc.

Dùng các trường này như manh mối. Đối chiếu với release, source map nội bộ và trace trong môi trường phát triển. Không công khai source map hoặc log chứa đường dẫn nội bộ chỉ để làm cho báo cáo dễ đọc hơn.

### original-policy và sample

<code>original-policy</code> giúp biết policy mà browser đánh giá. Nó hữu ích khi nhiều route hoặc phiên bản triển khai policy khác nhau. Tuy nhiên, không cần lưu lặp toàn bộ chuỗi policy trong mọi bản ghi nếu có thể ánh xạ sang policy ID hoặc hash đã được quản lý.

Một số policy có thể dùng biểu thức <code>report-sample</code> để yêu cầu browser đưa một đoạn ngắn của inline script hoặc style vi phạm vào báo cáo. Sample có thể chứa dữ liệu nhạy cảm hoặc nội dung do người dùng kiểm soát. Chỉ bật khi có nhu cầu điều tra rõ ràng, giới hạn nơi truy cập và thời gian lưu, đồng thời tránh đưa sample thô vào log phổ thông.

## 5. Thu thập sự kiện trong trang

Ngoài report endpoint, trang có thể lắng nghe sự kiện <code>securitypolicyviolation</code>. Cách này hữu ích khi phát triển, kiểm thử hoặc hiển thị chẩn đoán nội bộ. Sự kiện không thay thế việc cấu hình endpoint vì nó chỉ quan sát trong tài liệu hiện tại và có thể mất khi trang đóng hoặc điều hướng.

~~~js
document.addEventListener("securitypolicyviolation", (event) => {
  const detail = {
    effectiveDirective: event.effectiveDirective,
    violatedDirective: event.violatedDirective,
    disposition: event.disposition,
    blockedURI: event.blockedURI,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber,
    columnNumber: event.columnNumber,
    statusCode: event.statusCode
  };

  console.info("CSP violation", detail);
});
~~~

Các thuộc tính của <code>SecurityPolicyViolationEvent</code> có thể gồm:

- <code>documentURI</code>: URL tài liệu có vi phạm.
- <code>blockedURI</code>: nguồn bị chặn hoặc giá trị rút gọn.
- <code>effectiveDirective</code> và <code>violatedDirective</code>: directive liên quan.
- <code>originalPolicy</code>: policy gốc.
- <code>disposition</code>: enforce hoặc report.
- <code>sourceFile</code>, <code>lineNumber</code>, <code>columnNumber</code>: vị trí có thể xác định.
- <code>statusCode</code>: HTTP status của tài liệu.
- <code>sample</code>: đoạn nội dung ngắn nếu browser cung cấp và policy yêu cầu.

Không gửi nguyên object event lên một dịch vụ telemetry công khai. Hãy chọn trường cần thiết, loại bỏ query/fragment khỏi URL, giới hạn độ dài và tránh thu thập sample nếu không có nhu cầu. Nếu endpoint đã nhận report từ browser, việc tự gửi thêm cùng sự kiện từ JavaScript có thể tạo bản ghi trùng lặp.

Sự kiện trong trang cũng có thể hữu ích để xác nhận một ca kiểm thử cụ thể. Trong test tự động, đăng ký listener trước khi kích hoạt hành động có khả năng vi phạm:

~~~js
const violationPromise = new Promise((resolve) => {
  document.addEventListener("securitypolicyviolation", resolve, {
    once: true
  });
});

const script = document.createElement("script");
script.textContent = "window.__cspTestMarker = true";
document.body.append(script);

const event = await violationPromise;
console.log(event.effectiveDirective, event.disposition);
~~~

Ví dụ trên chỉ minh họa cách quan sát một sự kiện trong fixture có policy phù hợp. Khi viết test thật, đặt timeout cho promise, xác nhận marker không thay đổi trong chế độ enforce và chạy ca tương ứng ở Report-Only để xác nhận script vẫn được phép thực thi theo policy đó. Không dùng đoạn script inline này trên trang production.

## 6. Xây dựng endpoint tiếp nhận báo cáo an toàn

CSP report endpoint là endpoint công khai nhận dữ liệu do browser gửi. Nội dung report có thể phản ánh URL, directive, source file, user agent và một số thông tin về nội dung trang. Dữ liệu này phải được xem là đầu vào không đáng tin cậy.

Một endpoint an toàn nên:

- Chỉ nhận method và Content-Type dự kiến.
- Giới hạn kích thước request và độ dài từng trường.
- Hỗ trợ payload legacy và Reporting API theo nhu cầu tương thích.
- Kiểm tra cấu trúc JSON trước khi xử lý.
- Chuẩn hóa tên trường, kiểu dữ liệu và URL.
- Không thực thi, render HTML hoặc tự truy cập URL trong report.
- Không lưu cookie, token, query nhạy cảm hoặc sample thô nếu không cần.
- Giới hạn tần suất và đưa xử lý lưu trữ vào hàng đợi khi lưu lượng lớn.
- Trả response nhỏ, không redirect và không echo payload về client.

### Ví dụ endpoint Node.js với Express

Ví dụ dưới đây minh họa endpoint nhận cả JSON legacy và mảng report Reporting API. Cần điều chỉnh middleware, logger và hàng đợi theo ứng dụng thực tế:

~~~js
import express from "express";

const app = express();

const acceptedTypes = [
  "application/csp-report",
  "application/reports+json",
  "application/json"
];

function readText(value, maxLength = 512) {
  if (typeof value !== "string") return undefined;
  return value.slice(0, maxLength);
}

function readNumber(value) {
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

function safeBlockedValue(value) {
  const text = readText(value, 1024);
  if (!text) return undefined;

  const specialValues = [
    "inline",
    "eval",
    "wasm-eval",
    "data",
    "blob",
    "self"
  ];

  if (specialValues.includes(text)) return text;

  try {
    const url = new URL(text);
    return (url.origin + url.pathname).slice(0, 1024);
  } catch {
    return text.slice(0, 128);
  }
}

function normalizeReport(item) {
  const body = item?.body ?? item?.["csp-report"] ?? item;

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }

  return {
    type: readText(item?.type, 64) ?? "legacy-csp-report",
    disposition: readText(body.disposition, 32),
    effectiveDirective: readText(
      body.effectiveDirective ?? body["effective-directive"],
      128
    ),
    violatedDirective: readText(body["violated-directive"], 128),
    blockedURI: safeBlockedValue(
      body.blockedURL ?? body["blocked-uri"]
    ),
    documentURL: safeBlockedValue(
      body.documentURL ?? body["document-uri"]
    ),
    sourceFile: safeBlockedValue(
      body.sourceFile ?? body["source-file"]
    ),
    statusCode: readNumber(
      body.statusCode ?? body["status-code"]
    ),
    lineNumber: readNumber(
      body.lineNumber ?? body["line-number"]
    ),
    columnNumber: readNumber(
      body.columnNumber ?? body["column-number"]
    )
  };
}

app.post(
  "/csp-reports",
  express.raw({ type: acceptedTypes, limit: "32kb" }),
  (req, res) => {
    if (!Buffer.isBuffer(req.body)) {
      return res.sendStatus(415);
    }

    let payload;

    try {
      payload = JSON.parse(req.body.toString("utf8"));
    } catch {
      return res.sendStatus(400);
    }

    const items = Array.isArray(payload) ? payload : [payload];

    if (items.length > 50) {
      return res.sendStatus(413);
    }

    for (const item of items) {
      const normalized = normalizeReport(item);
      if (!normalized) continue;

      // Đưa bản ghi đã chuẩn hóa vào hàng đợi hoặc structured logger.
      logger.info({
        event: "csp_violation",
        ...normalized
      });
    }

    return res.status(204).end();
  }
);
~~~

Ví dụ tập trung vào cách tiếp nhận và chuẩn hóa. Trong hệ thống thực tế, cần khởi tạo logger và hàng đợi trước khi dùng; bổ sung rate limit ở reverse proxy hoặc middleware; theo dõi lỗi parse và request bị loại bỏ bằng metric tổng hợp. Không log raw request body.

Hàm chuẩn hóa trong ví dụ cắt ngắn các trường chuỗi và bỏ query/fragment của URL. Cần kiểm tra lại yêu cầu lưu trữ của tổ chức trước khi giữ lại bất kỳ URL, source file hay user agent nào. Có thể thay URL đầy đủ bằng origin và route đã chuẩn hóa nếu thông tin chi tiết không cần thiết cho điều tra.

### Xử lý payload không hợp lệ

Endpoint phải xử lý các tình huống sau một cách có kiểm soát:

| Đầu vào | Xử lý đề xuất |
|---|---|
| Content-Type không được hỗ trợ | Trả 415 |
| JSON sai cú pháp | Trả 400, tăng metric tổng hợp |
| Body vượt giới hạn | Từ chối bằng 413 |
| Mảng report quá lớn | Từ chối hoặc cắt theo giới hạn đã định |
| Trường sai kiểu | Bỏ trường đó hoặc bỏ report |
| Chuỗi quá dài | Cắt ngắn trước khi lưu |
| Report thiếu directive | Ghi nhận là dữ liệu thiếu hoặc loại bỏ theo schema |
| URL không parse được | Lưu nhãn rút gọn an toàn hoặc bỏ trường |
| Lưu trữ tạm thời lỗi | Ghi metric và xử lý qua hàng đợi/dự phòng |

Không để một report bất thường làm sập endpoint. Không phản hồi bằng HTML có chứa dữ liệu gửi lên. Không dùng nội dung <code>blocked-uri</code> để tạo request từ máy chủ; thao tác đó có thể biến endpoint thành điểm phát sinh SSRF.

### Giới hạn lưu lượng và chống lạm dụng

Một trang công khai có thể tạo nhiều report do lỗi cấu hình hoặc do nội dung bị khai thác. Kẻ tấn công cũng có thể cố tình tạo lưu lượng lớn tới endpoint. Nên:

- Giới hạn kích thước body, số report trong một request và tốc độ request.
- Đặt timeout ngắn cho bước nhận request.
- Xử lý ghi log và phân tích ở hàng đợi bất đồng bộ.
- Có ngưỡng cảnh báo khi lưu lượng tăng đột biến.
- Gom nhóm report lặp lại để giảm chi phí.
- Giữ endpoint độc lập với luồng phục vụ trang; endpoint lỗi không được làm ứng dụng chính ngừng hoạt động.
- Theo dõi tỷ lệ report hợp lệ, report bị loại và lỗi lưu trữ.

Không yêu cầu người dùng đăng nhập để browser có thể gửi report. Không dựa vào header Origin, Referer hoặc User-Agent như bằng chứng xác thực vì chúng có thể thiếu, bị rút gọn hoặc không đáng tin cậy. Endpoint cần được thiết kế như một cổng tiếp nhận dữ liệu công khai.

## 7. Bảo vệ quyền riêng tư của báo cáo

CSP report có thể tiết lộ nhiều hơn một metric thông thường. Ví dụ, URL tài liệu có thể chứa mã đơn hàng, email hoặc token nếu ứng dụng thiết kế URL không an toàn. Source file và sample cũng có thể làm lộ cấu trúc nội bộ.

Áp dụng nguyên tắc thu thập tối thiểu:

- Loại query string và fragment khỏi URL trước khi lưu.
- Chỉ giữ path khi cần điều tra route cụ thể; cân nhắc thay ID động bằng mẫu route.
- Không lưu cookie, Authorization header hoặc body của request.
- Hạn chế quyền đọc report và ghi lại truy cập dữ liệu.
- Đặt thời hạn lưu cho report chi tiết và metric tổng hợp.
- Che hoặc loại sample; chỉ bật <code>report-sample</code> trong phạm vi cần thiết.
- Tránh gửi report sang hệ thống analytics bên thứ ba nếu chưa đánh giá dữ liệu có thể bị lộ.
- Không đưa raw report vào dashboard HTML mà chưa encode đầu ra.

Không giả định browser luôn xóa dữ liệu nhạy cảm. Cần kiểm tra URL và nội dung do ứng dụng tạo ra để bảo đảm không đưa bí mật vào vị trí mà report có thể ghi nhận.

Nếu cần phân tích theo người dùng, ưu tiên correlation ID ngẫu nhiên có thời hạn và không chứa thông tin định danh. Thông thường, phân tích theo route, release, browser và directive đã đủ để tìm nguyên nhân mà không cần gắn report với tài khoản cụ thể.

## 8. Phân loại và điều tra CSP violation

Không xử lý mọi report như một incident. Trước hết, xác định policy, chế độ, directive và hành động bị ảnh hưởng.

### Nhóm nguyên nhân phổ biến

| Nhóm | Dấu hiệu | Cách kiểm tra |
|---|---|---|
| Cấu hình ứng dụng | Tài nguyên hợp lệ bị chặn sau release | So sánh policy, route và release trước/sau |
| Tích hợp bên thứ ba | Host analytics, payment hoặc CDN mới | Xác minh nhà cung cấp và danh sách nguồn đã duyệt |
| Inline script/style | <code>blocked-uri</code> là <code>inline</code> | Kiểm tra template, framework, nonce/hash |
| Eval hoặc dynamic code | Directive liên quan <code>script-src</code>, giá trị <code>eval</code> | Tìm API hoặc thư viện tạo mã động |
| Extension | URL có scheme extension hoặc source không thuộc app | Tái hiện trên profile sạch |
| XSS hoặc injection | Nguồn lạ, route nhạy cảm, hành vi không giải thích được | Tái hiện an toàn, kiểm tra input/output và log liên quan |
| Policy không đồng nhất | Cùng route nhận nhiều original policy | Kiểm tra CDN, proxy và nhiều response header |
| Browser hoặc công cụ | Chỉ xuất hiện trong một browser/profile | Kiểm tra phiên bản, extension, WebView và fixture |

### Quy trình điều tra

1. Xác định report đến từ policy enforce hay Report-Only.
2. Lấy <code>effective-directive</code> và <code>original-policy</code> để biết quy tắc được áp dụng.
3. Chuẩn hóa URL tài liệu, URL nguồn và release để xác định route bị ảnh hưởng.
4. Kiểm tra tài nguyên có phải tích hợp hợp lệ đã được phê duyệt không.
5. Tái hiện trên profile sạch và browser/version được báo cáo.
6. Kiểm tra Network, Console, source map nội bộ và log máy chủ có liên quan.
7. Xác định tác động: nội dung bị chặn, tính năng bị gián đoạn hay hành vi không mong muốn được ngăn lại.
8. Ghi nhận kết luận, thay đổi cần thực hiện và cách xác minh sau sửa.

Nếu report có <code>blocked-uri</code> là <code>inline</code>, không tự động thêm <code>'unsafe-inline'</code>. Xác định inline script/style đó có cần thiết không; ưu tiên nonce hoặc hash theo thiết kế CSP. Nếu một domain CDN mới xuất hiện, xác minh chủ sở hữu và phạm vi tài nguyên cần tải trước khi thêm nguồn vào allowlist.

### Phân biệt extension và hành vi của ứng dụng

Extension có thể chèn script hoặc style vào trang và tạo CSP violation. Một số report có thể nhắc tới scheme hoặc source không thuộc ứng dụng. Để xác minh:

- Mở profile sạch không cài extension.
- Tắt extension trong môi trường thử nghiệm được kiểm soát.
- So sánh browser, route và thời điểm phát sinh.
- Kiểm tra request initiator và source file trong DevTools.
- Không đưa extension origin vào CSP allowlist chỉ để loại bỏ báo cáo.

Nếu vi phạm chỉ xuất hiện khi có extension cụ thể, ghi nhận đây là điều kiện môi trường. Nếu vẫn tái hiện trên profile sạch, tiếp tục điều tra ứng dụng hoặc nội dung bên thứ ba.

## 9. Giảm nhiễu và gom nhóm báo cáo

Một release có thể tạo hàng nghìn report giống nhau. Dashboard nên gom nhóm theo các trường đủ ổn định:

- Policy ID hoặc hash của policy.
- Directive hiệu lực.
- Disposition.
- Origin và route đã chuẩn hóa của tài liệu.
- Giá trị blocked URI đã rút gọn.
- Browser family/version nếu dữ liệu đủ tin cậy.
- Release hoặc build.
- Khoảng thời gian.

Không dùng toàn bộ URL với query string làm khóa nhóm vì có thể tạo cardinality rất cao và lưu dữ liệu nhạy cảm. Không dùng sample hoặc raw report làm nhãn metric.

Có thể tính số report, số route bị ảnh hưởng, số browser khác nhau và thời điểm đầu tiên/cuối cùng quan sát được. Tách metric tổng hợp khỏi kho report chi tiết để dashboard không cần quyền truy cập dữ liệu thô.

### Dedupe và phân loại

Một khóa dedupe có thể dựa trên policy ID, disposition, effective directive, route chuẩn hóa và blocked URI rút gọn trong một cửa sổ thời gian. Không gộp các report enforce và report-only thành một nhóm vì mức tác động khác nhau.

Các report giống nhau trong một khoảng ngắn có thể được gom thành một nhóm có bộ đếm. Tuy nhiên, giữ một mẫu đại diện đã giảm thiểu để phục vụ điều tra và cho phép xem lại thay đổi theo release.

### Mức độ ưu tiên

| Mức | Ví dụ | Hành động |
|---|---|---|
| Khẩn cấp | Dấu hiệu script không mong muốn ở route nhạy cảm, có khả năng thực thi hoặc truy cập dữ liệu | Điều tra ngay, phối hợp nhóm ứng dụng và bảo mật |
| Cao | Policy enforce chặn tính năng xác thực, thanh toán hoặc thao tác quan trọng | Xác định phạm vi người dùng và khôi phục chức năng an toàn |
| Trung bình | Tích hợp hợp lệ bị chặn sau release hoặc policy Report-Only phát hiện nguồn chưa được duyệt | Xác minh chủ sở hữu, cập nhật cấu hình có kiểm soát |
| Thấp | Report lặp lại từ extension hoặc môi trường thử nghiệm đã biết | Ghi nhận, lọc theo quy tắc và tiếp tục theo dõi |

Không dùng số lượng report đơn lẻ để xác định mức độ nghiêm trọng. Một report có thể phản ánh một hành động bị chặn rất quan trọng; hàng nghìn report có thể chỉ là một extension hoặc lỗi cấu hình lặp lại.

## 10. Dùng Report-Only để triển khai CSP

Report-Only giúp đánh giá policy trước khi enforce. Một quy trình an toàn có thể gồm:

1. Xác định threat model và các loại tài nguyên ứng dụng thực sự cần.
2. Tạo policy ban đầu dựa trên nguồn hợp lệ, ưu tiên nonce/hash cho script.
3. Gửi policy bằng header Report-Only ở môi trường thử nghiệm hoặc nhóm triển khai phù hợp.
4. Thu thập report qua nhiều luồng người dùng, browser và route.
5. Phân loại từng nhóm vi phạm, xác minh nguồn và nhu cầu nghiệp vụ.
6. Sửa ứng dụng hoặc tích hợp để loại bỏ nguồn không cần thiết.
7. Chỉ thêm nguồn đã xác minh vào policy.
8. Enforce policy ở phạm vi phù hợp và theo dõi report sau triển khai.

Không chuyển tất cả host xuất hiện trong report vào allowlist. Report có thể đến từ extension, input độc hại, script bị chặn hoặc nguồn chưa được kiểm chứng. Mỗi nguồn cần có chủ sở hữu, lý do nghiệp vụ và phạm vi directive rõ ràng.

### Không biến report thành allowlist tự động

Một hệ thống tự động thêm <code>blocked-uri</code> vào <code>script-src</code> sẽ biến đầu vào không đáng tin cậy thành quyền thực thi. Kẻ tấn công có thể cố tình tạo report để đưa domain của họ vào policy. Việc cập nhật policy cần được review, kiểm tra chủ sở hữu domain, kiểm tra nội dung và xác minh nhu cầu thực tế.

### Chuyển dần sang enforce

Có thể triển khai theo route hoặc nhóm người dùng để giảm rủi ro. Trước mỗi bước:

- Xác nhận policy version và endpoint báo cáo hoạt động.
- Chạy smoke test các luồng đăng nhập, thanh toán, upload, download và nội dung nhúng.
- Xác minh browser mục tiêu.
- Chuẩn bị cách rollback policy nếu tính năng quan trọng bị chặn.
- Theo dõi lỗi ứng dụng và report enforce sau rollout.

Rollback nên khôi phục policy đã được kiểm duyệt trước đó. Không xóa CSP hoàn toàn khi một directive gây lỗi; điều chỉnh phạm vi cần thiết và duy trì các bảo vệ còn lại.

## 11. Kiểm thử endpoint và hành vi trình duyệt

Một bộ test giám sát CSP nên kiểm tra cả policy, trình duyệt và endpoint:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| CSPV-01 | Report-Only chặn theo policy mô phỏng | Report được tạo, hành động vẫn được phép theo policy đó |
| CSPV-02 | Enforce chặn script inline không được phép | Script không chạy và có violation |
| CSPV-03 | Script từ host không được allowlist | Request/thực thi bị chặn theo directive |
| CSPV-04 | Reporting-Endpoints và report-to khớp tên nhóm | Browser hỗ trợ gửi report tới endpoint |
| CSPV-05 | report-uri fallback | Browser hỗ trợ cơ chế cũ gửi report legacy |
| CSPV-06 | Endpoint nhận JSON legacy | Parse và chuẩn hóa thành công |
| CSPV-07 | Endpoint nhận mảng Reporting API | Parse từng phần tử hợp lệ |
| CSPV-08 | JSON sai cú pháp | Endpoint trả 400, không ghi raw body |
| CSPV-09 | Body vượt giới hạn | Endpoint từ chối bằng 413 |
| CSPV-10 | Content-Type không hỗ trợ | Endpoint trả 415 |
| CSPV-11 | Trường sai kiểu hoặc quá dài | Dữ liệu được bỏ hoặc cắt an toàn |
| CSPV-12 | URL có query/fragment nhạy cảm | Bản ghi lưu trữ đã được loại bỏ phần nhạy cảm |
| CSPV-13 | Endpoint tạm thời không khả dụng | CSP enforce vẫn được browser áp dụng |
| CSPV-14 | Extension tạo violation | Có thể phân loại bằng profile sạch và nguồn phát sinh |
| CSPV-15 | Nhiều report trùng lặp | Dashboard gom nhóm, không làm mất số lượng |
| CSPV-16 | Nhiều policy cùng áp dụng | Report được liên hệ đúng policy và disposition |

### Kiểm tra trong DevTools

Trong môi trường thử nghiệm:

1. Mở Network và bật Preserve log nếu cần.
2. Tải trang có header CSP.
3. Thực hiện hành động tạo vi phạm có chủ đích.
4. Xem Console để nhận biết directive và tài nguyên bị ảnh hưởng.
5. Kiểm tra request POST tới endpoint nếu browser hỗ trợ cơ chế báo cáo đó.
6. Mở payload và xác định định dạng legacy hay Reporting API.
7. So sánh với sự kiện <code>securitypolicyviolation</code> trong trang.
8. Xác minh hành vi thực tế: tài nguyên có bị chặn hay chỉ được báo cáo.

Console message không đảm bảo có report POST. Ngược lại, report có thể được gửi trễ hoặc gom nhóm. Hãy xác nhận endpoint và hành vi browser riêng biệt.

### Kiểm tra sự kiện trong trang

Đăng ký listener trước khi kích hoạt nội dung vi phạm. Ghi nhận <code>effectiveDirective</code>, <code>disposition</code> và <code>blockedURI</code>. Trong chế độ enforce, xác nhận marker không thay đổi; trong Report-Only, xác nhận marker thay đổi nếu không có policy enforce khác chặn.

### Kiểm tra endpoint độc lập

Có thể gửi payload mẫu bằng công cụ HTTP để xác nhận parser và giới hạn dữ liệu:

~~~bash
curl -i https://app.example.test/csp-reports \
  -H "Content-Type: application/csp-report" \
  --data '{"csp-report":{"effective-directive":"script-src","blocked-uri":"inline","document-uri":"https://app.example.test/lab"}}'
~~~

Đây là kiểm tra endpoint với dữ liệu giả lập, không chứng minh browser đã gửi report. Cần chạy riêng một test trong browser để xác minh header, hành vi CSP và việc gửi báo cáo.

## 12. Quan sát vận hành và cảnh báo

Một dashboard hữu ích nên thể hiện:

- Số report theo thời gian và disposition.
- Top effective directive và blocked URI đã chuẩn hóa.
- Route và release bị ảnh hưởng.
- Browser family/version nếu có dữ liệu phù hợp.
- Tỷ lệ report được parse, bị loại, bị giới hạn hoặc lỗi lưu trữ.
- Nhóm report mới xuất hiện sau release.
- Sự khác nhau giữa report-only và enforce.

Cảnh báo nên dựa trên thay đổi có ý nghĩa: một nhóm violation mới trên route nhạy cảm, tỷ lệ enforce tăng đột biến, một nguồn script không được duyệt hoặc endpoint nhận report thất bại kéo dài. Dùng baseline theo release và giờ hoạt động để giảm cảnh báo nhiễu.

Theo dõi sức khỏe của pipeline độc lập với CSP:

- Request nhận được và status response.
- Tỷ lệ parse thành công.
- Kích thước payload và số report trong mỗi request.
- Thời gian chờ hàng đợi và lỗi lưu trữ.
- Rate limit, request bị từ chối và nguồn lưu lượng bất thường.
- Độ trễ từ lúc nhận report tới khi hiển thị trên dashboard.

Không cảnh báo chỉ vì không có report. Một ứng dụng không có vi phạm, browser không gửi báo cáo hoặc endpoint bị lỗi đều có thể dẫn đến số liệu bằng không. Cần một health check riêng cho endpoint và test tổng hợp trong môi trường kiểm soát.

## 13. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ xem Console | Không có dữ liệu tập trung và lịch sử | Cấu hình endpoint, metric và dashboard |
| Chỉ dùng report-uri | Một số browser mới có thể dùng cơ chế khác | Kết hợp cơ chế phù hợp và kiểm tra tương thích |
| Dùng report-only rồi tưởng đã chặn | Nội dung vẫn có thể thực thi | Phân biệt disposition và policy enforce |
| Tự động thêm blocked-uri vào allowlist | Kẻ tấn công có thể mở rộng quyền | Review thủ công nguồn và nhu cầu |
| Lưu raw report vô thời hạn | Tăng rủi ro lộ URL và sample | Chuẩn hóa, giảm thiểu và đặt retention |
| Endpoint parse JSON không giới hạn | Có thể bị gửi payload lớn hoặc gây quá tải | Giới hạn body, số phần tử và rate |
| Render report như HTML | Có thể tạo XSS trong dashboard | Encode đầu ra và dùng text node |
| Fetch blocked-uri từ server | Có thể tạo SSRF | Không truy cập URL trong report |
| Coi mọi report là tấn công | Tạo nhiều false positive | Phân loại theo policy, profile, release và hành vi |
| Endpoint lỗi làm gián đoạn ứng dụng | Monitoring ảnh hưởng availability | Tách pipeline báo cáo khỏi luồng phục vụ trang |

## 14. Thực hành

Tạo một trang lab do bạn kiểm soát tại <code>https://app.example.test/csp-lab</code> và endpoint <code>/csp-reports</code>. Dùng dữ liệu giả lập, không sử dụng trang production hoặc dữ liệu người dùng thật.

### Phần A: Report-Only

Trả header sau cho trang lab:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.test/csp-reports"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri /csp-reports
~~~

Tạo một script inline thay đổi marker trên trang. Quan sát Console, sự kiện <code>securitypolicyviolation</code> và request báo cáo nếu browser hỗ trợ. Xác nhận script vẫn chạy theo policy Report-Only.

### Phần B: Enforce

Chuyển policy lab sang header <code>Content-Security-Policy</code>. Tải lại trang và kích hoạt cùng hành động. Xác nhận script không chạy, browser phát sinh violation và endpoint nhận report nếu cơ chế được hỗ trợ.

So sánh <code>disposition</code> và hành vi giữa hai chế độ. Không chỉ so sánh câu chữ trong Console.

### Phần C: Chuẩn hóa và bảo vệ endpoint

Gửi payload legacy và payload mảng Reporting API tới endpoint. Kiểm tra parser xử lý đúng wrapper và trường camelCase/hyphenated. Thử JSON sai cú pháp, body quá lớn, trường sai kiểu và URL có query giả lập chứa dữ liệu nhạy cảm.

Xác nhận endpoint giới hạn dữ liệu, loại query/fragment theo chính sách, không log raw body và trả status phù hợp. Kiểm tra dashboard chỉ hiển thị dữ liệu đã encode.

### Phần D: Phân tích nhiễu

Tạo một report từ nguồn script không hợp lệ trong lab. Sau đó chạy lại bằng profile có extension thử nghiệm và profile sạch. So sánh nguồn phát sinh, directive, URL và release. Ghi kết luận vào bảng:

| Trường | Giá trị |
|---|---|
| Browser/engine/version | |
| Policy ID và disposition | |
| Effective directive | |
| Document route đã chuẩn hóa | |
| Blocked URI đã rút gọn | |
| Profile và extension | |
| Hành vi thực tế | |
| Nguyên nhân dự kiến | |
| Bằng chứng | |
| Hành động tiếp theo | |

Cuối cùng, xóa dữ liệu lab và xác nhận endpoint không còn giữ report thô ngoài thời hạn kiểm thử.

## 15. Ghi nhớ

- CSP violation là tín hiệu cho biết một hành động không đáp ứng policy; nó không tự động chứng minh có tấn công.
- Enforce chặn hành động vi phạm; Report-Only chỉ quan sát theo policy đó.
- <code>report-uri</code> là cơ chế cũ; <code>Reporting-Endpoints</code> kết hợp <code>report-to</code> hỗ trợ Reporting API trên browser tương ứng.
- Payload legacy và Reporting API có cấu trúc khác nhau; endpoint cần chuẩn hóa định dạng mà sản phẩm hỗ trợ.
- <code>effective-directive</code>, <code>disposition</code>, <code>blocked-uri</code> và <code>original-policy</code> là các trường quan trọng khi điều tra.
- Browser có thể rút gọn URL, trì hoãn, gom nhóm hoặc không gửi report; không xem số report là phép đo đầy đủ.
- Endpoint phải giới hạn kích thước, xác thực cấu trúc, giảm thiểu dữ liệu, rate limit và không truy cập URL do report cung cấp.
- Không tự động đưa nguồn vi phạm vào allowlist; mỗi nguồn cần được xác minh và review.
- Dashboard phải encode dữ liệu và tách metric tổng hợp khỏi report chi tiết.
- Theo dõi sức khỏe endpoint riêng với trạng thái thực thi CSP trong browser.
