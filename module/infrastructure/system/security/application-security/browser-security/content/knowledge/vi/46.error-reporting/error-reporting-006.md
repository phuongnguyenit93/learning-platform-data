# Báo cáo vi phạm CSP: thu thập, phân tích và vận hành an toàn

Content Security Policy (CSP) giúp browser giới hạn những tài nguyên và hành vi mà một trang web được phép sử dụng. Khi một hành động vi phạm policy, browser có thể chặn hành động đó và tạo một báo cáo để hệ thống biết directive nào đã bị vi phạm, tài nguyên nào bị chặn và trang nào phát sinh sự kiện.

Báo cáo vi phạm CSP giúp đội phát triển quan sát tác động của policy trước và sau khi bật enforcement. Chúng cũng giúp phát hiện cấu hình sai, dependency ngoài dự kiến và một số dấu hiệu tấn công. Tuy nhiên, báo cáo là dữ liệu đầu vào không đáng tin cậy: browser có thể gửi thiếu, gửi trễ hoặc không gửi; endpoint có thể nhận dữ liệu giả mạo; một vi phạm có thể xuất phát từ code hợp lệ, extension hoặc môi trường kiểm thử.

Bài học này giải thích cách CSP tạo báo cáo, phân biệt chế độ report-only với enforcement, cấu hình Reporting API và cơ chế report-uri tương thích cũ, đọc các trường báo cáo, xây dựng endpoint nhận báo cáo an toàn và biến dữ liệu thành quy trình xử lý có thể vận hành.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích khi nào browser tạo CSP violation report.
- Phân biệt `Content-Security-Policy` với `Content-Security-Policy-Report-Only`.
- Cấu hình `Reporting-Endpoints` và directive `report-to`.
- Nhận diện cơ chế `report-uri` cũ và định dạng JSON tương ứng.
- Phân biệt `Reporting-Endpoints` với HTTP header `Report-To` đã lỗi thời.
- Đọc các trường như `effectiveDirective`, `blockedURL`, `documentURL`, `disposition` và `originalPolicy`.
- Hiểu giới hạn về độ tin cậy, tính đầy đủ và quyền riêng tư của báo cáo.
- Xây dựng endpoint nhận báo cáo có giới hạn kích thước, xác thực cấu trúc và chống lạm dụng.
- Phân loại báo cáo thành lỗi cấu hình, vi phạm dự kiến và tín hiệu cần điều tra.
- Triển khai CSP theo giai đoạn từ report-only tới enforcement.
- Kiểm thử báo cáo bằng DevTools, Reporting API và sự kiện `securitypolicyviolation`.

## 1. CSP violation report là gì?

CSP violation report là dữ liệu browser tạo ra khi một hành động bị policy ngăn chặn hoặc không đáp ứng một quy tắc CSP có liên quan. Ví dụ:

- Trang chỉ cho phép script từ origin của chính nó nhưng lại yêu cầu script từ một CDN chưa được cho phép.
- Một đoạn inline script không có nonce hoặc hash hợp lệ.
- Code gọi `eval()` trong khi policy không cho phép `unsafe-eval`.
- Trang cố tải hình ảnh, font, stylesheet hoặc frame từ một nguồn bị chặn.
- Một document vi phạm quy tắc `frame-ancestors` hoặc các directive khác có cơ chế báo cáo.

Báo cáo mô tả sự kiện ở góc nhìn của browser. Nó có thể cho biết directive hiệu lực, URL bị chặn, URL document, vị trí source và policy gốc. Dữ liệu này giúp developer tìm ra nguyên nhân và đánh giá tác động của CSP.

### 1.1 Báo cáo không phải bằng chứng chắc chắn về một cuộc tấn công

Một báo cáo có thể phát sinh từ:

- Mã ứng dụng hợp lệ nhưng policy chưa cập nhật.
- Một dependency mới được thêm vào.
- Một cấu hình CDN hoặc asset host bị thiếu.
- Một trang thử nghiệm hoặc staging có policy khác production.
- Browser extension hoặc phần mềm can thiệp nội dung trang.
- Một request do người dùng hoặc script tạo ra.
- Hành vi đáng ngờ hoặc nỗ lực injection thực sự.

Vì vậy, không được xem mỗi báo cáo là một incident bảo mật. Cần đối chiếu route, release, directive, blocked URL, browser, thời điểm và thay đổi gần nhất trước khi kết luận.

### 1.2 Báo cáo khác với việc browser thực thi policy

CSP có hai vai trò liên quan nhưng khác nhau:

- Enforcement: browser áp dụng policy và chặn hành động vi phạm.
- Reporting: browser gửi thông tin về hành động vi phạm tới nơi nhận báo cáo.

Một policy report-only có thể ghi nhận vi phạm mà không chặn hành động. Một policy enforcement có thể vừa chặn vừa tạo báo cáo nếu đã cấu hình đích báo cáo.

Báo cáo giúp quan sát policy. Nó không làm policy mạnh hơn và cũng không thay thế việc thiết kế directive đúng.

## 2. Report-only và enforcement

Hai response header quan trọng:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Policy trong `Content-Security-Policy` được thực thi. Policy trong `Content-Security-Policy-Report-Only` chỉ tạo báo cáo khi có vi phạm và không chặn hành động theo policy report-only đó.

### 2.1 Khi nào dùng report-only?

Report-only hữu ích khi:

- Chuẩn bị triển khai một policy mới.
- Chuyển từ allowlist rộng sang nonce/hash.
- Đánh giá dependency bên thứ ba.
- Phát hiện inline script hoặc inline style còn tồn tại.
- Xác định ảnh hưởng của directive mới trước khi bật enforcement.
- Kiểm tra policy cho một release hoặc route cụ thể.

Ví dụ, ứng dụng hiện đang cho phép script từ nhiều nguồn. Đội phát triển muốn giới hạn `script-src` về `'self'` nhưng chưa chắc tất cả trang đã tương thích. Có thể phát hành policy mới bằng report-only, thu thập dữ liệu qua nhiều luồng người dùng rồi điều chỉnh.

### 2.2 Có thể gửi đồng thời policy enforcement và report-only

Một response có thể có cả hai header. Browser xử lý từng policy theo vai trò riêng:

- Policy enforcement tiếp tục chặn hành động không được phép.
- Policy report-only ghi nhận những hành động vi phạm policy thử nghiệm.
- Một hành động có thể tạo báo cáo từ nhiều policy khác nhau.
- Nếu có nhiều policy enforcement, hành động phải tuân thủ tất cả policy áp dụng.

Khi phân tích, cần nhận diện policy nào đã tạo báo cáo. Trường `disposition` thường giúp phân biệt `enforce` và `report`, còn `originalPolicy` cho biết policy liên quan.

### 2.3 Report-only không được khai báo bằng meta element

`Content-Security-Policy-Report-Only` phải được gửi bằng HTTP response header. Không thể dùng `<meta http-equiv>` để triển khai report-only policy.

Các reporting directive như `report-to` và `report-uri` cũng cần được cấu hình trong HTTP header theo cơ chế CSP tương ứng. Với CSP reporting, hãy kiểm tra response header thực tế trong Network panel.

## 3. Các cơ chế gửi báo cáo

Có hai cơ chế cần hiểu khi vận hành CSP reporting:

1. Reporting API với `Reporting-Endpoints` và directive CSP `report-to`.
2. Directive `report-uri` theo cơ chế cũ, vẫn cần cân nhắc để tương thích với browser chưa hỗ trợ đầy đủ cơ chế mới.

Không nhầm directive CSP `report-to` với HTTP response header `Report-To` cũ. Header `Report-To` thuộc phiên bản trước của Reporting API và đã được thay thế bởi `Reporting-Endpoints`.

### 3.1 Reporting API: Reporting-Endpoints và report-to

Server khai báo tên endpoint và URL nhận báo cáo bằng HTTP response header:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"
~~~

Sau đó policy tham chiếu endpoint bằng directive `report-to`:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint
~~~

Tên `csp-endpoint` trong policy phải khớp tên endpoint đã khai báo trong `Reporting-Endpoints`.

Khi có vi phạm, browser tạo report thuộc loại `csp-violation` và gửi tới endpoint theo cơ chế Reporting API. Request thường dùng:

~~~http
POST /csp HTTP/1.1
Host: reports.example.test
Content-Type: application/reports+json
~~~

Body của Reporting API có dạng một mảng report. Ví dụ rút gọn:

~~~json
[
  {
    "age": 12,
    "type": "csp-violation",
    "url": "https://app.example.test/profile",
    "user_agent": "Example Browser",
    "body": {
      "documentURL": "https://app.example.test/profile",
      "referrer": "https://app.example.test/",
      "blockedURL": "https://cdn.example.test/widget.js",
      "effectiveDirective": "script-src-elem",
      "originalPolicy": "default-src 'self'; script-src 'self'; report-to csp-endpoint",
      "disposition": "report",
      "statusCode": 200,
      "sourceFile": "https://app.example.test/profile",
      "lineNumber": 42,
      "columnNumber": 9,
      "sample": ""
    }
  }
]
~~~

Các trường có thể khác nhau tùy loại report, browser và ngữ cảnh. Một số giá trị có thể vắng mặt hoặc được browser rút gọn vì lý do quyền riêng tư.

### 3.2 report-uri: cơ chế tương thích cũ

`report-uri` là reporting directive cũ trong CSP. Ví dụ:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri /csp-report
~~~

Browser hỗ trợ cơ chế cũ gửi HTTP POST tới URI đã khai báo. Content-Type thường là:

~~~http
Content-Type: application/csp-report
~~~

Body có cấu trúc object với key `csp-report`:

~~~json
{
  "csp-report": {
    "document-uri": "https://app.example.test/profile",
    "referrer": "https://app.example.test/",
    "blocked-uri": "https://cdn.example.test/widget.js",
    "effective-directive": "script-src-elem",
    "violated-directive": "script-src-elem",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /csp-report",
    "disposition": "report",
    "status-code": 200,
    "source-file": "https://app.example.test/profile",
    "line-number": 42,
    "column-number": 9
  }
}
~~~

Định dạng legacy khác với định dạng của Reporting API. Backend phải nhận diện Content-Type và parse theo schema tương ứng. Không giả định mọi POST đến endpoint đều là một JSON array hoặc mọi report đều có key `csp-report`.

### 3.3 Khai báo cả report-to và report-uri trong giai đoạn tương thích

`report-uri` đã bị deprecated và được thay thế bởi `report-to`. Tuy nhiên, hỗ trợ browser có thể khác nhau theo phiên bản. Trong giai đoạn chuyển tiếp, có thể khai báo cả hai:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri https://reports.example.test/csp-legacy; report-to csp-endpoint
~~~

Trong browser hỗ trợ `report-to`, directive này được ưu tiên và `report-uri` có thể bị bỏ qua. Browser cũ hơn có thể dùng `report-uri`.

Nếu hai endpoint khác nhau, cần vận hành và giám sát cả hai. Nếu cùng dùng một endpoint, backend phải hỗ trợ cả hai định dạng request. Kiểm tra browser mục tiêu và ma trận tương thích thực tế trước khi bỏ cơ chế cũ.

### 3.4 Không dùng Report-To cho cấu hình mới

HTTP header `Report-To` là cơ chế khai báo endpoint cũ của Reporting API. Header này đã được thay thế bởi `Reporting-Endpoints`.

Phân biệt ba tên sau:

| Tên | Vai trò | Trạng thái sử dụng |
|---|---|---|
| `Reporting-Endpoints` | HTTP response header ánh xạ tên endpoint tới URL | Cơ chế hiện hành nên ưu tiên |
| `report-to` | CSP directive chọn tên endpoint | Dùng cùng `Reporting-Endpoints` |
| `report-uri` | CSP directive gửi báo cáo theo định dạng cũ | Deprecated, giữ khi cần tương thích |
| `Report-To` | HTTP response header cũ khai báo nhóm endpoint | Đã bị thay thế |

## 4. Những trường quan trọng trong báo cáo

Khi phân tích báo cáo, cần hiểu ý nghĩa từng trường và giới hạn của nó. Tên trường có thể dùng kiểu kebab-case trong định dạng legacy và camelCase trong Reporting API.

| Trường | Ý nghĩa |
|---|---|
| `documentURL` / `document-uri` | URL document phát sinh vi phạm |
| `referrer` | Referrer của document nếu có |
| `blockedURL` / `blocked-uri` | URL hoặc loại tài nguyên bị chặn |
| `effectiveDirective` / `effective-directive` | Directive thực tế áp dụng cho hành động |
| `violated-directive` | Tên directive theo định dạng legacy |
| `originalPolicy` / `original-policy` | Policy liên quan đến vi phạm |
| `disposition` | `enforce` hoặc `report` |
| `statusCode` / `status-code` | HTTP status code của document |
| `sourceFile` / `source-file` | Tệp nguồn được browser xác định là vị trí liên quan |
| `lineNumber` / `line-number` | Số dòng nếu browser xác định được |
| `columnNumber` / `column-number` | Số cột nếu browser xác định được |
| `sample` / `script-sample` | Mẫu code ngắn nếu policy và browser cung cấp |

### 4.1 effectiveDirective

`effectiveDirective` cho biết directive thực sự được dùng để kiểm tra hành động. Ví dụ:

- `script-src-elem`: kiểm soát script được tải bằng phần tử script.
- `script-src-attr`: kiểm soát event handler attribute như `onclick`.
- `script-src`: directive kiểm soát script trong trường hợp không có directive chuyên biệt phù hợp.
- `style-src-elem`: kiểm soát stylesheet hoặc style element.
- `img-src`: kiểm soát nguồn hình ảnh.
- `connect-src`: kiểm soát kết nối từ các API như Fetch, XHR, WebSocket và EventSource.
- `frame-src`: kiểm soát nguồn nội dung được nhúng trong frame.
- `frame-ancestors`: kiểm soát origin nào được phép nhúng document trong frame.

Đừng chỉ nhìn `violated-directive` mà bỏ qua `effectiveDirective`. Khi directive chuyên biệt có mặt, giá trị effective giúp tìm đúng nhánh policy cần sửa.

### 4.2 blockedURL

`blockedURL` có thể chứa URL, origin hoặc giá trị đặc biệt như `inline`, `eval`, `data` hoặc `blob`, tùy loại vi phạm và browser.

Không phải lúc nào browser cũng cung cấp toàn bộ path của tài nguyên cross-origin. Một số thông tin có thể được rút gọn để tránh tiết lộ dữ liệu. Do đó, không được dựa vào blockedURL để khẳng định chính xác mọi URL gốc.

### 4.3 originalPolicy

`originalPolicy` chứa policy liên quan đến báo cáo. Trường này hữu ích khi một ứng dụng có nhiều policy hoặc khi policy thay đổi giữa các release.

Tuy nhiên, policy có thể chứa nonce, hash hoặc thông tin triển khai. Không nên đưa nguyên văn trường này vào dashboard public hoặc log không kiểm soát quyền truy cập. Có thể lưu policy hash, release identifier và phiên bản cấu hình thay vì hiển thị toàn bộ giá trị.

### 4.4 disposition

Giá trị thường gặp:

- `enforce`: hành động bị ngăn theo policy đang thực thi.
- `report`: hành động vi phạm policy report-only, nhưng không bị policy report-only chặn.

Trường này giúp phân biệt một lỗi đã ảnh hưởng hành vi người dùng với một vi phạm đang được quan sát trước khi enforcement.

Nếu ứng dụng có cả policy enforced và report-only, một hành động có thể tạo nhiều report. Cần gắn mỗi report với đúng policy và disposition.

### 4.5 sample, sourceFile, lineNumber và columnNumber

Một số browser có thể cung cấp mẫu code ngắn khi policy có token `report-sample` ở directive phù hợp. Ví dụ:

~~~http
Content-Security-Policy-Report-Only: script-src 'self' 'report-sample'; report-to csp-endpoint
~~~

Sample hỗ trợ tìm inline script hoặc đoạn code gây vi phạm. Nhưng nó cũng có thể chứa một phần dữ liệu nhạy cảm nếu nội dung được tạo động.

sourceFile, lineNumber và columnNumber hỗ trợ định vị lỗi. Các trường này không phải lúc nào cũng có mặt, đặc biệt khi browser không xác định được source hoặc khi vi phạm phát sinh từ inline code.

## 5. Sự kiện và API quan sát ở phía client

Ngoài HTTP report gửi tới server, browser cung cấp một số cách để quan sát CSP violation trong DevTools hoặc code chẩn đoán.

### 5.1 SecurityPolicyViolationEvent

Document có thể lắng nghe sự kiện `securitypolicyviolation`:

~~~javascript
document.addEventListener("securitypolicyviolation", (event) => {
  console.log({
    documentURI: event.documentURI,
    blockedURI: event.blockedURI,
    effectiveDirective: event.effectiveDirective,
    violatedDirective: event.violatedDirective,
    disposition: event.disposition,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber,
    columnNumber: event.columnNumber
  });
});
~~~

Sự kiện cung cấp thông tin hữu ích để debug trong browser. Không phải mọi trình duyệt hoặc mọi tình huống đều cung cấp đầy đủ trường. Sự kiện cũng không tự gửi dữ liệu lên server.

Không nên thêm một luồng telemetry client-side trùng lặp với HTTP reporting nếu chưa có lý do rõ ràng. Nếu cần thu thập từ client, hãy giới hạn trường, kiểm soát quyền riêng tư và chống gửi lặp.

### 5.2 ReportingObserver

Reporting API có `ReportingObserver` để quan sát các report được browser tạo trong browsing context:

~~~javascript
if ("ReportingObserver" in window) {
  const observer = new ReportingObserver(
    (reports) => {
      for (const report of reports) {
        if (report.type === "csp-violation") {
          console.log(report.body);
        }
      }
    },
    {
      types: ["csp-violation"],
      buffered: true
    }
  );

  observer.observe();
}
~~~

`buffered: true` yêu cầu observer nhận cả report phù hợp đã được tạo trước khi observer bắt đầu theo dõi, nếu browser còn lưu chúng.

ReportingObserver hữu ích cho chẩn đoán tại client và công cụ nội bộ. Nó không thay thế endpoint nhận báo cáo ở server, không bảo đảm report được gửi tới backend và không phải cơ chế giám sát duy nhất cho production.

### 5.3 Không dùng client event làm bằng chứng đáng tin cậy

JavaScript trong trang có thể bị thay đổi bởi người dùng, extension hoặc môi trường kiểm thử. Dữ liệu do client tự gửi có thể bị giả mạo. Khi cần thống kê production, hãy phân biệt báo cáo do browser gửi qua Reporting API với dữ liệu telemetry do ứng dụng tự tạo.

Cả hai loại vẫn cần được xem là input không đáng tin cậy ở server.

## 6. Xây dựng endpoint nhận báo cáo an toàn

CSP report endpoint thường là endpoint public vì browser của người dùng cần gửi report tới đó. Nó không thể mặc định chỉ nhận request từ người dùng đã đăng nhập.

Thiết kế endpoint cần tính đến:

- Request có thể đến từ nhiều browser và origin.
- Report có thể bị giả mạo bằng HTTP client.
- Một trang có thể tạo rất nhiều report.
- Body có thể lớn hoặc chứa dữ liệu bất thường.
- URL và sample có thể chứa thông tin nhạy cảm.
- Định dạng request có thể khác giữa Reporting API và report-uri.
- Report có thể đến trễ hoặc trùng lặp.

### 6.1 Chấp nhận đúng method và content type

Endpoint thường nhận POST. Cần hỗ trợ các định dạng mà hệ thống thực sự triển khai:

- `application/reports+json` cho Reporting API.
- `application/csp-report` cho report-uri legacy.

Ví dụ logic xử lý:

~~~javascript
function classifyReportRequest(contentType) {
  const normalized = (contentType || "")
    .split(";")[0]
    .trim()
    .toLowerCase();

  if (normalized === "application/reports+json") {
    return "reporting-api";
  }

  if (normalized === "application/csp-report") {
    return "legacy-csp";
  }

  return null;
}
~~~

Không parse mọi body như JSON bất kể Content-Type. Cần giới hạn method, content type và kích thước trước khi parse.

Một số hệ thống reverse proxy hoặc browser có thể tạo khác biệt nhỏ về header. Hãy quan sát request thực tế trong môi trường mục tiêu và cấu hình parser theo contract đã chọn.

### 6.2 Giới hạn kích thước và số lượng report

Đặt giới hạn body size, số report trong một batch, độ dài chuỗi và độ sâu object. Không để endpoint nhận một mảng không giới hạn hoặc object lồng nhau quá sâu.

Ví dụ các giới hạn cần cân nhắc:

- Request body tối đa.
- Số report tối đa trong một batch.
- Độ dài tối đa của URL, policy và sample.
- Số trường được lưu.
- Thời gian xử lý tối đa.
- Tốc độ request theo IP hoặc các tín hiệu phù hợp.

Giới hạn phải phù hợp với dữ liệu thật. Khi vượt giới hạn, trả lỗi phù hợp hoặc loại bỏ phần dư theo chính sách đã công bố, đồng thời ghi nhận số liệu tổng hợp để theo dõi.

### 6.3 Validate schema và chuẩn hóa dữ liệu

Không tin cậy giá trị do browser gửi. Một endpoint có thể nhận report từ client không phải browser, từ script tự viết hoặc từ attacker.

Cần:

1. Parse JSON bằng parser chuẩn.
2. Xác nhận top-level object hoặc array đúng loại.
3. Kiểm tra `type` nếu dùng Reporting API.
4. Xác nhận body có cấu trúc phù hợp.
5. Kiểm tra kiểu dữ liệu và độ dài từng trường.
6. Chỉ giữ các trường cần cho điều tra.
7. Chuẩn hóa URL và loại bỏ query/fragment khi không cần.
8. Loại hoặc redact dữ liệu nhạy cảm trước khi ghi log.
9. Gắn server receive time và release identifier từ cấu hình server.
10. Đưa report vào hàng đợi nếu xử lý tiếp theo tốn thời gian.

Không dùng giá trị `documentURL` do client gửi làm căn cứ phân quyền hoặc định tuyến tới hệ thống nội bộ.

### 6.4 Không thực thi hoặc render dữ liệu báo cáo

Các trường `sample`, `blockedURL`, `documentURL`, `originalPolicy` và `user_agent` đều là dữ liệu không tin cậy.

Không:

- Ghép trực tiếp chúng vào HTML dashboard.
- Dùng `innerHTML` để hiển thị report.
- Dùng URL trong report làm URL fetch server-side.
- Thực thi sample như JavaScript.
- Dùng nội dung report để tạo câu lệnh shell hoặc SQL không tham số.
- Dùng chuỗi trong report làm template hoặc biểu thức regex không giới hạn.

Khi hiển thị, dùng text node hoặc output encoding theo đúng context. Khi lưu database, dùng parameterized query và schema có giới hạn.

### 6.5 Chống spam và report giả mạo

Endpoint có thể bị lạm dụng để tạo tải hoặc làm nhiễu dashboard. Các biện pháp vận hành gồm:

- Rate limit theo IP hoặc tín hiệu phù hợp, có cân nhắc NAT và mạng doanh nghiệp.
- Giới hạn kích thước request và batch.
- Dùng WAF hoặc reverse proxy để lọc request bất thường.
- Tách ingest khỏi xử lý phân tích nặng.
- Dedupe theo fingerprint và khoảng thời gian.
- Giới hạn retention và chi phí lưu trữ.
- Theo dõi tỷ lệ report bất thường.
- Không tự động chặn IP, user hoặc domain chỉ dựa trên một report.

Không thể xác thực một CSP report chỉ bằng cách kiểm tra Origin hoặc User-Agent. Các header này có thể bị giả mạo ngoài browser. Report là tín hiệu quan sát, không phải bằng chứng xác thực.

### 6.6 Endpoint không cần cookie đăng nhập của người dùng

Browser gửi báo cáo trong bối cảnh reporting riêng. Không thiết kế endpoint phụ thuộc vào session cookie của ứng dụng như điều kiện để nhận report. Endpoint cần có thể nhận request từ browser mà không làm lộ cookie hoặc token của người dùng.

Nếu endpoint nằm ở origin khác, hãy kiểm tra hành vi request thực tế và yêu cầu hạ tầng. Đừng bật credentialed CORS hoặc chia sẻ cookie rộng chỉ để nhận report. Cấu hình endpoint theo hướng nhận dữ liệu tối thiểu, không cấp quyền đọc dữ liệu nhạy cảm cho client.

### 6.7 Phản hồi nhanh và xử lý bất đồng bộ

Report không phải request nghiệp vụ cần trả dữ liệu cho người dùng. Endpoint nên:

- Xác thực cấu trúc tối thiểu.
- Ghi nhận hoặc enqueue report.
- Trả response nhanh với status phù hợp.
- Không chạy truy vấn nặng hoặc gửi cảnh báo đồng bộ.
- Có cơ chế retry nội bộ nếu queue hoặc storage tạm thời lỗi.

Reporting API không bảo đảm browser sẽ retry vô hạn. Hệ thống phải chịu được report bị mất và không dùng nó như nguồn audit duy nhất.

## 7. Quyền riêng tư và dữ liệu nhạy cảm trong báo cáo

CSP report có thể chứa URL, referrer, tên tệp, đường dẫn nội bộ, policy và sample. Những trường này có thể tiết lộ thông tin về người dùng hoặc ứng dụng.

### 7.1 URL có thể chứa dữ liệu cá nhân

Một số ứng dụng đưa dữ liệu vào query string hoặc path. Ví dụ:

~~~text
https://app.example.test/search?email=lan@example.test
https://app.example.test/reset/one-time-token
~~~

Nếu URL được ghi nguyên vẹn vào report hoặc log, endpoint có thể lưu email, token hoặc dữ liệu nhạy cảm.

Nên:

- Loại query string và fragment khi không cần phân tích.
- Không dùng token hoặc dữ liệu cá nhân trong URL.
- Redact các route chứa reset token hoặc identifier nhạy cảm.
- Giới hạn người có quyền xem raw report.
- Đặt thời hạn lưu trữ và quy trình xóa dữ liệu.

Browser có thể rút gọn một số URL cross-origin, nhưng không nên dựa vào việc browser luôn xóa mọi thông tin nhạy cảm.

### 7.2 originalPolicy và sample cũng cần được bảo vệ

Policy có thể chứa nonce hoặc thông tin cấu hình. Sample có thể chứa đoạn code nội tuyến được tạo từ dữ liệu động. Không bật `report-sample` trên toàn bộ hệ thống nếu chưa đánh giá rủi ro và nhu cầu.

Nếu cần sample trong giai đoạn điều tra:

1. Chỉ bật ở policy hoặc route cần chẩn đoán.
2. Giới hạn người truy cập dashboard.
3. Redact dữ liệu nhạy cảm trước khi lưu.
4. Giới hạn retention.
5. Tắt hoặc thu hẹp sau khi tìm được nguyên nhân.

### 7.3 Tránh lưu User-Agent và IP quá mức cần thiết

Reporting API report có thể chứa `user_agent`; hạ tầng ingest cũng có thể ghi IP nguồn. Các dữ liệu này hữu ích để phân nhóm browser và điều tra nhưng có thể là dữ liệu cá nhân theo chính sách tổ chức.

Chỉ lưu mức chi tiết cần thiết, áp dụng retention và quyền truy cập phù hợp. Nếu chỉ cần phân tích browser family, có thể chuẩn hóa User-Agent thành nhóm thay vì lưu chuỗi đầy đủ.

## 8. Phân tích và phân loại báo cáo

Số lượng report lớn không đồng nghĩa với số lượng lỗ hổng lớn. Mục tiêu là biến các report thành tín hiệu có thể xử lý.

### 8.1 Nhóm theo effectiveDirective

Một dashboard có thể nhóm report theo:

- `effectiveDirective`.
- `blockedURL` hoặc origin của blocked URL.
- `documentURL` đã chuẩn hóa route.
- `disposition`.
- Release identifier.
- Browser family.
- Thời gian phát sinh.
- Policy hash.

Ví dụ, nhiều report `script-src-elem` từ cùng một CDN ngay sau release mới có thể cho thấy dependency hoặc asset host bị thiếu trong policy.

### 8.2 Phân loại nguyên nhân

| Nhóm | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Lỗi cấu hình | Tài nguyên hợp lệ của ứng dụng bị chặn | Sửa policy hoặc cấu hình resource |
| Dependency mới | Vi phạm bắt đầu sau khi thêm package/CDN | Review dependency và nguồn tải |
| Inline code | `blockedURL` là `inline` hoặc directive script/style | Chuyển sang nonce/hash hoặc refactor |
| Eval | Vi phạm liên quan `eval` hoặc `unsafe-eval` | Loại bỏ eval hoặc thay thư viện |
| Browser extension | URL có scheme extension hoặc chỉ xảy ra trên một số máy | Phân biệt môi trường và xác minh |
| Tấn công tiềm năng | Nguồn lạ, route nhạy cảm, mẫu hành vi bất thường | Điều tra cùng log và telemetry khác |
| Policy sai release | `originalPolicy` hoặc policy hash không khớp bản triển khai | Kiểm tra cache và pipeline phát hành |

Đây là nhóm phân loại ban đầu. Một report có thể thuộc nhiều nhóm hoặc cần điều tra thêm.

### 8.3 Fingerprint để deduplicate

Có thể tạo fingerprint từ một số trường đã chuẩn hóa, chẳng hạn:

- `effectiveDirective`.
- Origin của `blockedURL`.
- Route đã bỏ query.
- Policy hash.
- Release identifier.
- Loại `disposition`.

Không nên dùng toàn bộ URL hoặc sample làm fingerprint nếu chúng chứa dữ liệu thay đổi theo từng người dùng. Fingerprint cần ổn định vừa đủ để nhóm sự kiện, nhưng vẫn giữ khả năng phân biệt release hoặc policy khác nhau.

### 8.4 Không tự động thêm nguồn vào allowlist

Một lỗi phổ biến là thấy report từ một domain lạ rồi thêm domain đó vào `script-src` để hết cảnh báo.

Trước khi sửa policy, phải xác minh:

- Domain đó có thuộc dependency hợp lệ không?
- Có phải URL bị chặn do redirect hoặc tracking không?
- Có phải browser extension hoặc môi trường cá nhân không?
- Resource có cần thiết cho trang không?
- Có thể self-host hoặc thay dependency không?
- Có cách dùng nonce/hash an toàn hơn không?

CSP là cơ chế giới hạn nguồn và hành vi. Mở rộng allowlist chỉ để giảm số report có thể làm policy yếu đi.

## 9. Quy trình triển khai CSP reporting theo giai đoạn

Một quy trình thực tế nên tách việc thu thập, phân tích, sửa policy và enforcement.

~~~mermaid
flowchart TD
    A["Xác định policy mục tiêu"] --> B["Triển khai Report-Only"]
    B --> C["Cấu hình endpoint và ingest"]
    C --> D["Thu thập report theo release"]
    D --> E["Chuẩn hóa, dedupe và phân loại"]
    E --> F{"Có vi phạm hợp lệ?"}
    F -->|Có| G["Sửa code hoặc policy"]
    G --> B
    F -->|Không / đã giải thích| H["Kiểm thử luồng chính"]
    H --> I["Bật CSP enforcement"]
    I --> J["Tiếp tục giám sát report"]
    J --> K["Điều chỉnh policy có kiểm soát"]
~~~

### 9.1 Bước 1: Xác định policy mục tiêu

Xác định các directive cần có dựa trên kiến trúc ứng dụng. Ví dụ:

- `default-src`.
- `script-src`.
- `style-src`.
- `img-src`.
- `font-src`.
- `connect-src`.
- `frame-src`.
- `frame-ancestors`.
- `object-src`.
- `base-uri`.
- `form-action`.

Không copy một policy mẫu mà không kiểm tra ứng dụng thực tế. Cần biết route nào dùng inline code, script nonce, worker, WebSocket, iframe hoặc third-party integration.

### 9.2 Bước 2: Phát hành report-only

Thêm `Content-Security-Policy-Report-Only` với policy mục tiêu và endpoint reporting. Giữ policy enforced hiện tại trong thời gian đánh giá.

Đảm bảo report có release identifier hoặc cách liên kết với release. Không so sánh dữ liệu từ nhiều policy khác nhau như thể chúng cùng một cấu hình.

### 9.3 Bước 3: Thu thập đủ luồng người dùng

Chạy qua các luồng chính:

- Đăng nhập và đăng xuất.
- Điều hướng giữa các route.
- Tải ảnh, font và stylesheet.
- Gửi form.
- Gọi API.
- Mở dialog, popup và iframe hợp lệ.
- Tải worker nếu ứng dụng dùng.
- Tích hợp thanh toán hoặc dịch vụ ngoài nếu có.

Report-only chỉ ghi nhận hành vi đã xảy ra. Nếu một route hoặc tính năng không được sử dụng trong thời gian quan sát, report-only không chứng minh route đó tương thích.

### 9.4 Bước 4: Sửa nguyên nhân

Ưu tiên sửa code hoặc cấu hình resource để policy có thể chặt chẽ hơn:

- Thay inline script bằng file riêng hoặc nonce/hash.
- Loại bỏ `eval()` và dependency yêu cầu `unsafe-eval`.
- Self-host asset nếu phù hợp.
- Thu hẹp nguồn bên thứ ba.
- Bổ sung nonce theo từng response nếu kiến trúc dùng nonce.
- Loại bỏ script hoặc resource không còn cần thiết.

Không đưa nonce cố định vào cấu hình. Nonce phải được sinh ngẫu nhiên đủ mạnh cho mỗi response và gắn nhất quán với header cùng script hợp lệ.

### 9.5 Bước 5: Bật enforcement theo phạm vi

Khi report-only không còn các vi phạm hợp lệ chưa xử lý, bật policy bằng `Content-Security-Policy`.

Có thể rollout theo route, nhóm người dùng hoặc tỷ lệ traffic nếu hạ tầng hỗ trợ. Cần có cách rollback khi policy chặn chức năng quan trọng.

### 9.6 Bước 6: Duy trì giám sát

Sau khi bật enforcement, tiếp tục thu thập report. Report mới có thể xuất hiện do release, dependency, nội dung người dùng hoặc môi trường browser thay đổi.

Đặt cảnh báo theo mức tăng bất thường và route quan trọng. Không tạo alert cho mọi report đơn lẻ vì có thể gây nhiễu và làm đội vận hành bỏ qua cảnh báo.

## 10. Kiểm thử CSP violation report

Thực hiện trong local lab hoặc ứng dụng do bạn kiểm soát. Không tạo payload tấn công lên website bên thứ ba.

### 10.1 Kiểm tra response header

Dùng DevTools Network hoặc curl để kiểm tra response:

~~~bash
curl -I https://app.example.test/
~~~

Xác nhận:

- Có `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only` đúng môi trường.
- `Reporting-Endpoints` khai báo đúng tên và URL.
- `report-to` tham chiếu đúng tên endpoint.
- `report-uri` chỉ còn nếu cần tương thích.
- Endpoint sử dụng HTTPS.
- Không có header trùng lặp hoặc policy cũ từ proxy/CDN.

### 10.2 Tạo một vi phạm có kiểm soát

Trong trang lab có policy:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-report; report-to csp-endpoint
~~~

và endpoint được khai báo:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.test/csp-report"
~~~

Thử thêm một script từ origin lab khác không có trong `script-src`. Vì policy đang ở report-only, browser ghi nhận vi phạm nhưng vẫn cho phép hành động theo policy report-only đó.

Quan sát:

- Console có thông báo CSP violation.
- Network có request báo cáo nếu browser hỗ trợ cơ chế tương ứng và report được gửi.
- Endpoint nhận đúng Content-Type.
- Backend parse đúng schema.
- `disposition` là `report`.

Không dùng script có hành vi nguy hiểm. Chỉ dùng một file script thử nghiệm không có tác động ngoài việc ghi một thông điệp vào console.

### 10.3 Kiểm tra enforcement

Đổi policy thử nghiệm thành `Content-Security-Policy` trong lab. Lặp lại hành động.

Xác nhận:

- Browser chặn tài nguyên vi phạm.
- Console ghi nhận lý do.
- Report có thể được gửi với `disposition` là `enforce`.
- Các tài nguyên hợp lệ vẫn hoạt động.

Không dựa vào việc endpoint có nhận report hay không để kết luận enforcement đã hoạt động. Kiểm tra trực tiếp hành vi tải tài nguyên và console.

### 10.4 Kiểm tra định dạng legacy và Reporting API

Nếu hỗ trợ cả hai cơ chế:

- Gửi một request `application/csp-report` fixture vào parser legacy trong môi trường test.
- Gửi một mảng `application/reports+json` fixture vào parser Reporting API.
- Xác nhận cả hai được chuẩn hóa thành cùng schema nội bộ.
- Kiểm tra request sai Content-Type hoặc JSON sai cấu trúc bị xử lý an toàn.
- Xác nhận không có parser fallback làm nhận nhầm dữ liệu.

### 10.5 Kiểm tra report bị giả mạo

Gửi report fixture bằng HTTP client tới endpoint lab. Endpoint vẫn có thể nhận request vì không thể chứng minh request đó đến từ browser thật.

Xác nhận hệ thống:

- Không coi report là xác thực người dùng.
- Không tự động khóa tài khoản hoặc chặn IP.
- Có rate limit và giới hạn body.
- Ghi nhận nguồn tiếp nhận theo cách phù hợp.
- Không render sample hoặc URL như HTML.

### 10.6 Kiểm tra dữ liệu nhạy cảm

Tạo URL lab có query giả lập, ví dụ `?test-id=demo-value`, và kiểm tra pipeline lưu report.

Xác nhận query và fragment được loại bỏ hoặc redact theo policy. Không dùng email, token, session ID hay dữ liệu thật trong bài kiểm thử.

## 11. Lỗi vận hành thường gặp

### 11.1 Không nhận được report

Nguyên nhân có thể gồm:

- Header `Reporting-Endpoints` không được gửi.
- Tên trong `report-to` không khớp endpoint name.
- Endpoint URL không hợp lệ hoặc không dùng HTTPS.
- Browser không hỗ trợ cơ chế đang dùng.
- Policy không có reporting directive.
- Không có vi phạm nào xảy ra.
- Browser trì hoãn, gộp hoặc bỏ report.
- Request bị proxy, firewall hoặc server từ chối.

Cách xử lý: kiểm tra response header, browser compatibility, Network, endpoint log và tạo một vi phạm lab có kiểm soát.

### 11.2 Endpoint nhận report nhưng parser lỗi

Có thể backend chỉ hỗ trợ `csp-report` trong khi browser gửi `application/reports+json`, hoặc ngược lại.

Kiểm tra Content-Type trước khi parse và viết test cho cả hai định dạng nếu cần tương thích.

### 11.3 Report trùng lặp

Một hành động có thể vi phạm nhiều policy hoặc được report nhiều lần. Reporting API cũng có thể batch nhiều report trong một request.

Dùng fingerprint và deduplication theo khoảng thời gian. Không loại bỏ dữ liệu gốc đến mức mất khả năng truy vết release và disposition.

### 11.4 Report từ extension gây nhiễu

Một số extension hoặc phần mềm phía client có thể thêm script, thay đổi DOM hoặc yêu cầu tài nguyên. Những hành động này có thể vi phạm CSP.

Không thêm scheme extension hoặc domain không rõ vào allowlist chỉ để hết report. So sánh nhiều browser và profile sạch để phân biệt nguyên nhân.

### 11.5 Dùng report-only quá lâu mà không có kế hoạch

Report-only có thể tạo rất nhiều dữ liệu nhưng policy không bao giờ được enforcement. Đặt thời hạn quan sát, tiêu chí hoàn thành và người chịu trách nhiệm xử lý từng nhóm vi phạm.

### 11.6 Chuyển sang enforcement quá sớm

Nếu chưa kiểm tra các luồng chính, CSP có thể chặn script, API hoặc asset hợp lệ và làm hỏng chức năng.

Dùng rollout có kiểm soát, theo dõi lỗi ứng dụng và có khả năng rollback.

### 11.7 Tự động mở rộng allowlist từ report

Một domain trong `blockedURL` có thể do attacker kiểm soát hoặc do extension. Không tự động thêm vào policy. Mọi thay đổi nguồn phải qua review dependency và chủ sở hữu ứng dụng.

### 11.8 Lưu raw report vô thời hạn

Raw report có thể chứa URL và sample nhạy cảm. Áp dụng retention, redaction, access control và xóa dữ liệu theo chính sách.

### 11.9 Coi report là audit log đầy đủ

Browser có thể không gửi report. Report có thể bị drop, batch, trùng lặp hoặc giả mạo. Không dùng CSP report làm nguồn duy nhất để chứng minh mọi hành vi đã xảy ra.

### 11.10 Không liên kết report với release

Không có release identifier, đội vận hành khó biết policy nào đã tạo report. Gắn policy hash hoặc release metadata từ phía server và lưu cùng report đã chuẩn hóa.

## 12. Checklist review CSP reporting

- [ ] Đã phân biệt policy enforcement và report-only.
- [ ] Report-only được gửi bằng HTTP response header.
- [ ] Đã xác định directive cần báo cáo.
- [ ] `Reporting-Endpoints` khai báo đúng endpoint name và HTTPS URL.
- [ ] `report-to` tham chiếu đúng endpoint name.
- [ ] Đã quyết định có cần `report-uri` cho browser cũ hay không.
- [ ] Không dùng HTTP header `Report-To` cũ cho cấu hình mới.
- [ ] Endpoint nhận được `application/reports+json` nếu dùng Reporting API.
- [ ] Endpoint nhận được `application/csp-report` nếu hỗ trợ report-uri.
- [ ] Parser xử lý đúng cả batch report và legacy object.
- [ ] Có giới hạn method, body size, batch size và độ dài trường.
- [ ] Có schema validation và xử lý JSON sai định dạng.
- [ ] Dữ liệu report được coi là không đáng tin cậy.
- [ ] Có rate limit, deduplication và xử lý bất đồng bộ.
- [ ] Không render report bằng innerHTML hoặc thực thi sample.
- [ ] URL, originalPolicy, sample, User-Agent và IP được redacted theo nhu cầu.
- [ ] Retention và quyền truy cập raw report được xác định.
- [ ] Không tự động thêm nguồn vào CSP allowlist.
- [ ] Report được gắn với route, release hoặc policy hash.
- [ ] Đã kiểm tra các luồng ứng dụng quan trọng trước enforcement.
- [ ] Có kế hoạch rollout, giám sát và rollback.
- [ ] Không dùng CSP report làm audit log hoặc bằng chứng xác thực duy nhất.

## 13. Câu hỏi tự kiểm tra

**1. CSP violation report được tạo khi nào?**

Khi browser phát hiện một hành động vi phạm policy có cơ chế báo cáo và policy đã cấu hình reporting endpoint phù hợp.

**2. Report-only khác enforcement như thế nào?**

Report-only ghi nhận vi phạm nhưng không chặn hành động theo policy đó. Enforcement áp dụng policy và chặn hành động vi phạm.

**3. Reporting-Endpoints và report-to có vai trò gì?**

`Reporting-Endpoints` ánh xạ tên endpoint tới URL. Directive CSP `report-to` chọn tên endpoint mà browser dùng để gửi CSP report.

**4. report-uri có còn nên dùng không?**

Đây là cơ chế legacy đã deprecated. Có thể giữ trong giai đoạn tương thích với browser chưa hỗ trợ đầy đủ `report-to`, tùy ma trận browser của ứng dụng.

**5. HTTP header Report-To khác report-to thế nào?**

`Report-To` là HTTP response header cũ để khai báo nhóm endpoint. `report-to` là directive CSP chọn endpoint name. Cấu hình mới nên dùng `Reporting-Endpoints`.

**6. Hai định dạng báo cáo phổ biến khác nhau thế nào?**

Reporting API gửi JSON dạng mảng với `type: "csp-violation"` và `body`; report-uri legacy gửi object có key `csp-report`.

**7. disposition có ý nghĩa gì?**

Nó phân biệt báo cáo từ policy enforcement (`enforce`) và policy report-only (`report`).

**8. Vì sao không thể tin cậy mọi report?**

Request có thể bị giả mạo, dữ liệu có thể bị thiếu hoặc trễ, browser có thể bỏ report và nhiều vi phạm có nguyên nhân hợp lệ như cấu hình sai hoặc extension.

**9. Vì sao endpoint cần rate limit và giới hạn kích thước?**

Đây là endpoint nhận dữ liệu từ client không xác thực. Attacker có thể gửi report giả, body lớn hoặc số lượng request cao để gây nhiễu và tăng chi phí.

**10. Vì sao không tự động thêm blockedURL vào allowlist?**

Nguồn bị chặn có thể không đáng tin hoặc không cần thiết. Thêm tự động có thể mở rộng quyền tải script và làm policy yếu đi.

## Ghi nhớ

CSP reporting giúp quan sát những hành động vi phạm policy và hỗ trợ triển khai CSP an toàn theo từng giai đoạn. Dùng `Reporting-Endpoints` cùng directive `report-to` cho cơ chế Reporting API; giữ `report-uri` khi cần tương thích với browser cũ. Phân biệt report-only với enforcement, parse đúng từng định dạng và xem mọi report là dữ liệu không đáng tin cậy. Endpoint cần giới hạn tài nguyên, chống spam, redaction và retention phù hợp. Phân tích report theo directive, route, release và nguyên nhân; không tự động mở allowlist hoặc coi report là bằng chứng xác thực. Chỉ bật enforcement khi các luồng hợp lệ đã được kiểm tra và có phương án vận hành.

## Tài liệu tham khảo

- [W3C: Content Security Policy Level 3 — Reporting Directives](https://www.w3.org/TR/CSP3/#reporting)
- [MDN: Content-Security-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy)
- [MDN: Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only)
- [MDN: Content-Security-Policy report-to directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-to)
- [MDN: Reporting-Endpoints header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Reporting-Endpoints)
- [MDN: Content-Security-Policy report-uri directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/report-uri)
- [MDN: Reporting API](https://developer.mozilla.org/en-US/docs/Web/API/Reporting_API)
- [MDN: SecurityPolicyViolationEvent](https://developer.mozilla.org/en-US/docs/Web/API/SecurityPolicyViolationEvent)
- [MDN: ReportingObserver](https://developer.mozilla.org/en-US/docs/Web/API/ReportingObserver)
- [OWASP: Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
