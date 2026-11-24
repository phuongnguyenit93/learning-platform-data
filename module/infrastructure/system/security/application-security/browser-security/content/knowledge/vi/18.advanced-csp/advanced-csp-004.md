# Report-only mode: thử nghiệm CSP trước khi áp dụng enforcement

**Chương:** CSP nâng cao  
**Mô-đun:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Content-Security-Policy-Report-Only** là chế độ triển khai CSP để trình duyệt đánh giá một policy và gửi báo cáo khi trang vi phạm policy đó, nhưng **không chặn tài nguyên hoặc hành vi vi phạm**. Đây là bước thử nghiệm hữu ích trước khi chuyển policy sang `Content-Security-Policy` để enforcement, đặc biệt với ứng dụng lớn có nhiều route, script bên thứ ba, inline code, iframe và dependency khó kiểm kê.

Report-only giúp nhóm phát triển nhìn thấy những gì policy dự kiến sẽ chặn trong môi trường người dùng thật. Tuy nhiên, báo cáo chỉ là tín hiệu để điều tra: một violation có thể là chức năng hợp lệ chưa được đưa vào allowlist, một dependency cũ, cấu hình sai, hoặc hành vi tấn công. Ngược lại, không có report không chứng minh ứng dụng không có XSS hay policy đã bao phủ đầy đủ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa CSP enforcement và Report-only mode.
2. Cấu hình header `Content-Security-Policy-Report-Only` đúng cách trên HTTP response.
3. Thiết lập endpoint nhận báo cáo bằng `report-uri` và `report-to`/`Reporting-Endpoints`.
4. Đọc các trường quan trọng trong violation report và phân loại false positive, cấu hình thiếu hoặc hành vi đáng ngờ.
5. Triển khai policy theo từng giai đoạn, từ quan sát đến enforcement.
6. Bảo vệ endpoint báo cáo khỏi spam, dữ liệu nhạy cảm và chi phí lưu trữ không cần thiết.
7. Viết kiểm thử để chứng minh Report-only không làm hỏng chức năng và policy được đề xuất sẽ phát hiện các hành vi ngoài dự kiến.

## 2. CSP enforcement và Report-only khác nhau thế nào?

CSP có hai header chính:

| Header | Hành vi của browser | Mục đích |
| --- | --- | --- |
| `Content-Security-Policy` | Áp dụng policy và chặn hành vi vi phạm theo directive | Bảo vệ người dùng bằng enforcement |
| `Content-Security-Policy-Report-Only` | Đánh giá policy và gửi report, nhưng vẫn cho hành vi vi phạm tiếp tục | Quan sát tác động trước khi enforce |

Ví dụ response:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /csp-report
```

Nếu trang có inline script, policy trên có thể tạo violation report vì `script-src 'self'` không cho phép inline script. Nhưng trong Report-only mode, script đó **vẫn chạy**. Khi cùng policy được gửi bằng header `Content-Security-Policy`, browser sẽ chặn inline script không được phép.

Đừng nhầm Report-only với một policy “enforce nhẹ”. Nó không chặn một phần directive và cũng không làm request an toàn hơn. Nó chỉ cung cấp dữ liệu quan sát về kết quả nếu policy được thực thi.

### 2.1. Những giới hạn cần nhớ

- Report-only phải được gửi bằng **HTTP response header**. Không thể bật chế độ này bằng thẻ `<meta http-equiv>`.
- Report-only không thay thế header CSP enforcement đang có. Nếu response có cả hai header, policy enforcement hiện tại vẫn chặn theo quy tắc của nó; policy Report-only được đánh giá độc lập và tạo report riêng.
- Nếu có nhiều policy CSP, browser áp dụng từng policy; các policy enforced đồng thời đều phải được đáp ứng. Một policy Report-only bổ sung không nới lỏng policy đang enforce.
- Report-only không phải cơ chế kiểm thử tự động hoàn chỉnh: một số hành vi chỉ xuất hiện ở route, browser, trạng thái đăng nhập hoặc thiết bị cụ thể.
- Việc không nhận report có thể do browser không hỗ trợ reporting, endpoint lỗi, mạng chặn report, report bị gom batch hoặc policy chưa tạo violation.

### 2.2. Vì sao không bật enforcement ngay?

Một policy quá chặt có thể chặn:

- script inline được framework hoặc server render;
- script bundle từ CDN;
- style inline hoặc style attribute;
- font, ảnh, media từ host chưa được kiểm kê;
- API, WebSocket, worker hoặc iframe hợp lệ;
- luồng thanh toán, đăng nhập liên kết hoặc widget bên thứ ba.

Nếu enforce trước khi hiểu dependency, ứng dụng có thể lỗi ở một số route hoặc chỉ lỗi trong một nhóm người dùng. Report-only cho phép thu thập dữ liệu thực tế, xác định nguồn hợp lệ, loại bỏ dependency thừa và chuẩn bị nonce/hash/allowlist trước khi chuyển chế độ.

## 3. Đặt Report-only trên response header

Ví dụ policy ban đầu:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; report-uri /csp-report
```

Policy này là ví dụ để quan sát, không phải policy phù hợp cho mọi ứng dụng. Nếu trang đang dùng inline script, inline style hoặc tài nguyên bên ngoài, browser sẽ báo violation tương ứng. Trong Report-only, tài nguyên đó vẫn được tải và code vẫn chạy.

### 3.1. Dùng cùng lúc policy enforced và report-only

Có thể giữ một CSP hiện đang enforce, đồng thời gửi một policy mới ở chế độ Report-only:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-{RANDOM_NONCE}'; style-src 'self'; object-src 'none'; base-uri 'self'; report-uri /csp-report
```

Trong ví dụ:

- Policy thứ nhất tiếp tục bảo vệ theo các directive đang được enforce.
- Policy thứ hai chỉ báo cáo những gì sẽ vi phạm policy mới.
- Violation do policy enforced và violation do report-only có thể tạo các report khác nhau; hãy xem trường `disposition` để phân biệt.

Không thêm một header CSP yếu hơn với ý định nới lỏng policy hiện có. Nhiều policy được kết hợp theo hướng hạn chế hơn; policy mới không ghi đè policy cũ.

### 3.2. Nonce và hash trong giai đoạn thử nghiệm

Với script inline hợp lệ, policy hiện đại thường dùng nonce ngẫu nhiên riêng cho từng response hoặc hash của nội dung script ổn định:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-{RANDOM_NONCE_PER_RESPONSE}' 'sha256-{BASE64_HASH}'; object-src 'none'; base-uri 'self'; report-uri /csp-report
```

`{RANDOM_NONCE_PER_RESPONSE}` và `{BASE64_HASH}` chỉ là placeholder. Nonce phải khó đoán, được tạo bằng bộ sinh số ngẫu nhiên mật mã và không tái sử dụng giữa các response. Cùng nonce phải được gắn vào đúng thẻ script được server cho phép.

Hash phải tính từ nội dung script chính xác theo thuật toán CSP; thay đổi khoảng trắng hoặc nội dung script sẽ làm hash không khớp. Với inline event handler, cách xử lý tốt hơn thường là bỏ handler và dùng `addEventListener` thay vì cố đưa tất cả handler vào allowlist.

## 4. Gửi violation report về đâu?

Một policy Report-only cần một endpoint nhận report nếu muốn tập hợp dữ liệu từ browser. Có hai cơ chế cần biết:

- `report-uri` là directive CSP đời cũ, vẫn được nhiều browser hỗ trợ nhưng đã được đánh dấu deprecated trong đặc tả.
- `report-to` trỏ tới một reporting endpoint group được khai báo bằng header `Reporting-Endpoints` theo Reporting API hiện đại.

Trong giai đoạn chuyển tiếp, nhiều hệ thống cấu hình cả hai để có độ tương thích tốt hơn. Browser hỗ trợ cơ chế mới có thể dùng `report-to`; browser chỉ hỗ trợ `report-uri` có thể dùng endpoint legacy.

### 4.1. Cấu hình endpoint hiện đại và fallback

Ví dụ response:

```http
Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri https://reports.example.test/csp
```

Giải thích:

- `Reporting-Endpoints` khai báo tên group `csp-endpoint` và URL nhận report.
- Directive `report-to csp-endpoint` liên kết CSP policy với group đã khai báo.
- `report-uri` là fallback cho browser chưa hỗ trợ cơ chế Reporting API mới.
- Endpoint nên dùng HTTPS, có giới hạn request body và chỉ nhận dữ liệu báo cáo theo schema dự kiến.

Không nhầm `Reporting-Endpoints` với header `Report-To` cũ. Với triển khai mới, ưu tiên header `Reporting-Endpoints`; chỉ giữ cấu hình cũ nếu cần tương thích với browser/version đã xác định.

### 4.2. Cấu hình trên server Node.js

Ví dụ handler khái niệm:

```javascript
import { createServer } from "node:http";

const app = createServer((req, res) => {
  if (req.method === "POST" && req.url === "/csp") {
    const chunks = [];
    let size = 0;
    let tooLarge = false;
    req.on("data", chunk => {
      size += chunk.length;
      if (size > 64 * 1024) {
        tooLarge = true;
        return;
      }
      if (!tooLarge) chunks.push(chunk);
    });

    req.on("end", () => {
      if (tooLarge) {
        res.writeHead(413);
        res.end();
        return;
      }
      const body = Buffer.concat(chunks).toString("utf8");
      // Parse JSON như dữ liệu không tin cậy.
      try {
        const report = JSON.parse(body);
        storeCspReport(report);
      } catch {
        // Không phản chiếu payload lỗi về response.
      }

      res.writeHead(204, { "Cache-Control": "no-store" });
      res.end();
    });
    return;
  }

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Reporting-Endpoints": 'csp-endpoint="http://localhost:3000/csp"',
    "Content-Security-Policy-Report-Only":
      "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri http://localhost:3000/csp"
  });
  res.end("<!doctype html><title>Report-only</title><h1>Policy preview</h1>");
});

app.listen(3000);
```

Đây là khung minh họa, không phải collector production hoàn chỉnh. Trong server thật, cần xử lý stream giới hạn dung lượng an toàn, timeout, content type, rate limit, chống log injection, lưu trữ có TTL và giám sát lỗi. Không để một request body quá lớn làm tăng bộ nhớ vô hạn.

### 4.3. Đừng giả định mỗi violation chỉ gửi đúng một request

Reporting API có thể gom nhóm/batch report và gửi bất đồng bộ. Browser có thể trì hoãn, giới hạn, bỏ report hoặc gửi lại theo chính sách nội bộ. Vì vậy:

- Không dùng số report làm số lần tấn công chính xác.
- Không giả định report đến ngay sau khi trang render.
- Không dùng report collector làm hệ thống đo lường giao dịch hoặc audit log.
- Xây dựng pipeline có thể nhận report trùng, thiếu hoặc đến muộn.

## 5. Đọc cấu trúc của CSP violation report

Hai cơ chế báo cáo có format khác nhau. Legacy `report-uri` thường gửi JSON với object `csp-report`; Reporting API thường gửi một mảng report với `type` như `csp-violation` và object `body`.

### 5.1. Ví dụ legacy report

```json
{
  "csp-report": {
    "document-uri": "https://app.example.test/profile",
    "referrer": "https://app.example.test/",
    "blocked-uri": "inline",
    "violated-directive": "script-src-elem",
    "effective-directive": "script-src-elem",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /csp",
    "disposition": "report",
    "status-code": 200,
    "script-sample": ""
  }
}
```

### 5.2. Ví dụ Reporting API report

```json
[
  {
    "type": "csp-violation",
    "url": "https://app.example.test/profile",
    "body": {
      "documentURL": "https://app.example.test/profile",
      "blockedURL": "inline",
      "effectiveDirective": "script-src-elem",
      "disposition": "report",
      "originalPolicy": "default-src 'self'; script-src 'self'",
      "statusCode": 200
    }
  }
]
```

Tên field và mức chi tiết có thể khác theo format/browser. Collector nên lưu raw report đã giới hạn kích thước cùng các trường đã chuẩn hóa, đồng thời giữ thông tin format/version để phân tích về sau.

Với report legacy, browser thường gửi media type `application/csp-report`; Reporting API dùng `application/reports+json`. Không giả định mọi browser gửi cùng một content type hoặc cùng một cấu trúc JSON. Hãy kiểm tra media type, giới hạn body, parse theo schema phù hợp và từ chối dữ liệu sai định dạng một cách an toàn.

### 5.3. Những trường hữu ích

| Trường | Ý nghĩa khi phân tích |
| --- | --- |
| `document-uri` / `documentURL` | Trang phát sinh violation |
| `blocked-uri` / `blockedURL` | Nguồn hoặc nội dung bị policy đánh dấu |
| `effective-directive` / `effectiveDirective` | Directive thực sự gây violation |
| `violated-directive` | Directive vi phạm theo report legacy |
| `original-policy` / `originalPolicy` | Policy browser đang đánh giá |
| `disposition` | `report` hoặc `enforce` tùy loại report |
| `source-file` / `sourceFile` | File nguồn liên quan, nếu browser cung cấp |
| `line-number` / `lineNumber` | Dòng nguồn liên quan, nếu có |
| `script-sample` / `sample` | Mẫu code nếu policy yêu cầu report sample và browser hỗ trợ |

`disposition` đặc biệt quan trọng khi response có cả policy enforced và policy Report-only. Report có disposition `report` biểu thị violation được báo cáo mà không bị policy đó chặn; `enforce` biểu thị violation thuộc policy đang enforce.

### 5.4. `securitypolicyviolation` event trong trang

Ngoài gửi report về endpoint, browser có thể phát event `securitypolicyviolation` trong document:

```javascript
document.addEventListener("securitypolicyviolation", event => {
  console.log({
    directive: event.effectiveDirective,
    blockedURI: event.blockedURI,
    disposition: event.disposition,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber
  });
});
```

Event hữu ích cho debug trong môi trường phát triển. Không dựa vào JavaScript event listener để thay thế server collector: script có thể không chạy, trang có thể đóng và client có thể bị sửa. Không hiển thị nội dung report thô cho người dùng.

## 6. Phân loại report và xử lý false positive

Một violation report là đầu mối điều tra, không phải phán quyết rằng đã có cuộc tấn công. Phân loại từng report theo route, directive, browser, release, người sở hữu dependency và khả năng tái hiện.

| Nhóm | Dấu hiệu | Hành động |
| --- | --- | --- |
| Chức năng hợp lệ chưa khai báo | Script/style/image từ CDN hoặc service được sản phẩm sử dụng | Xác minh chủ sở hữu, tính cần thiết và integrity; cập nhật policy tối thiểu |
| Inline code còn sót | Violation ở `script-src-elem`, `script-src-attr` hoặc `style-src-attr` | Chuyển sang external file, nonce/hash hoặc DOM API phù hợp |
| Dependency bên thứ ba | Nguồn mới xuất hiện sau khi nâng cấp SDK/widget | Kiểm tra phiên bản, tài liệu, chain tải và rủi ro supply chain |
| Cấu hình deploy sai | Policy khác nhau giữa route, CDN, staging và production | Chuẩn hóa header ở ingress/app; kiểm tra response thực tế |
| Hành vi có dấu hiệu tấn công | Nguồn lạ, scheme bất thường, inline code không thuộc release | Điều tra theo request ID, route, thời điểm và telemetry liên quan |
| Browser extension hoặc môi trường người dùng | Violation không tái hiện trên profile sạch | Ghi nhận browser/context; không tự động allowlist nguồn lạ |

### 6.1. Không allowlist theo từng report một cách máy móc

Một report từ host lạ không phải lý do để thêm host đó vào `script-src`. Trước khi thay policy, cần xác minh:

1. Tài nguyên có thuộc chức năng đã được phê duyệt không?
2. Host có được kiểm soát bởi tổ chức hoặc nhà cung cấp đáng tin không?
3. Có thể tự host hoặc loại bỏ dependency không?
4. Có thể dùng nonce/hash thay vì cho phép inline hoặc cả host không?
5. Host có thể phục vụ nội dung do người dùng kiểm soát hay redirect sang nguồn khác không?
6. Việc thêm nguồn có làm policy rộng hơn mức cần thiết không?

Cho phép một host CDN có thể cho phép mọi script mà host đó phục vụ, tùy directive và cách tải. Ưu tiên nonce/hash cho script inline được kiểm soát và nguồn script hẹp. Tránh wildcard, `https:` hoặc `'unsafe-inline'` chỉ để làm report biến mất.

### 6.2. Report-only không chứng minh policy đã bao phủ hết

Browser chỉ báo những hành vi nó quan sát được khi người dùng truy cập. Route ít dùng, trạng thái lỗi, luồng thanh toán, người dùng có extension, thiết bị di động hoặc feature flag có thể chưa được chạy. Hãy kết hợp report thực tế với test automation, kiểm thử thủ công theo luồng quan trọng và inventory dependency.

## 7. Quyền riêng tư và an toàn của report collector

Violation report có thể chứa URL trang, URL tài nguyên bị chặn, referrer, file nguồn, dòng code hoặc thông tin policy. Những giá trị này đôi khi để lộ ID tài khoản, mã định danh, query string hoặc cấu trúc nội bộ.

Các nguyên tắc xử lý:

- Chỉ thu thập trường cần thiết cho điều tra CSP.
- Loại bỏ hoặc redact query parameter nhạy cảm trước khi lưu và hiển thị.
- Không bật `report-sample` trừ khi thật sự cần; sample có thể chứa đoạn code hoặc dữ liệu nhạy cảm.
- Đặt thời hạn lưu trữ ngắn, phân quyền truy cập và audit việc đọc report.
- Không ghi cookie, Authorization header, CSRF token hoặc body request người dùng vào report log.
- Escape dữ liệu khi hiển thị trong dashboard để tránh log/report injection.
- Giới hạn kích thước body, số report, tốc độ request và dung lượng lưu trữ.
- Chấp nhận report trùng và report lỗi; collector không nên làm gián đoạn ứng dụng chính.
- Giám sát tỷ lệ report theo release, route, directive và browser; không coi một spike đơn lẻ là bằng chứng tấn công.

Endpoint report thường được browser gọi tự động và không nên phụ thuộc vào session đăng nhập người dùng. Hãy coi request và JSON report là dữ liệu không tin cậy; không cho report endpoint thực hiện thao tác nghiệp vụ hoặc phản chiếu nội dung report vào trang.
## 8. Quy trình rollout từ Report-only sang enforcement

Không chuyển policy sang enforcement chỉ vì report giảm xuống thấp. Cần xác định phạm vi quan sát, xử lý report theo chủ sở hữu và kiểm tra các luồng quan trọng.

### 8.1. Giai đoạn 1 — kiểm kê và tạo policy ban đầu

1. Liệt kê script, style, image, font, media, API, worker và frame mà ứng dụng thực sự sử dụng.
2. Xác định nguồn first-party, third-party, inline code và tài nguyên do người dùng kiểm soát.
3. Tạo policy tối thiểu có thể triển khai, bắt đầu từ directive có ý nghĩa như `default-src`, `script-src`, `object-src` và `base-uri`.
4. Đưa policy lên staging và gửi Report-only header.
5. Xác nhận response thực tế có header đúng trên mọi route, redirect, lỗi và response HTML được CDN cache.

### 8.2. Giai đoạn 2 — thu thập và phân loại

1. Thu report từ browser mục tiêu trong một khoảng thời gian đủ bao phủ các chu kỳ sử dụng.
2. Gom theo `effective-directive`, route, blocked URI, browser/version và release.
3. Gắn owner cho từng nguồn tài nguyên hợp lệ.
4. Tái hiện report trong môi trường sạch để phân biệt dependency thật với extension hoặc môi trường cục bộ.
5. Không thêm nguồn mới vào allowlist nếu chưa xác minh chủ sở hữu và lý do cần thiết.

### 8.3. Giai đoạn 3 — sửa ứng dụng và policy

- Chuyển inline script sang file ngoài, hoặc dùng nonce/hash cho inline block thực sự cần.
- Thay inline event handler bằng `addEventListener`.
- Thay DOM sink không an toàn bằng API text/DOM phù hợp.
- Loại bỏ dependency không dùng; tự host asset nếu có thể.
- Thu hẹp nguồn theo host cụ thể; không dùng wildcard để giải quyết nhanh.
- Thêm directive chuyên biệt như `connect-src`, `img-src`, `font-src`, `frame-src` và `worker-src` theo inventory.
- Bổ sung Trusted Types nếu kiến trúc hỗ trợ và đã xử lý các sink cần thiết.

### 8.4. Giai đoạn 4 — kiểm chứng trước khi enforce

Chạy lại unit, integration và browser test trên các luồng chính:

- đăng nhập, đăng xuất, reset mật khẩu và MFA;
- thanh toán, upload, download và thao tác thay đổi dữ liệu;
- dashboard, editor, rich text và nội dung do người dùng tạo;
- analytics, chat, video, widget và SDK bên thứ ba;
- route lỗi, trang mở trực tiếp, redirect và trang render phía server.

Nếu report còn lại chỉ là violation đã hiểu rõ, hãy ghi nhận lý do chấp nhận và owner. Nếu report không giải thích được, tiếp tục điều tra. Không đặt mục tiêu “zero report” bằng cách nới policy cho mọi nguồn.

### 8.5. Giai đoạn 5 — enforce có kiểm soát

1. Chuyển policy đã được phê duyệt sang `Content-Security-Policy`.
2. Có thể giữ một policy chặt hơn ở Report-only để đánh giá bước hardening tiếp theo.
3. Theo dõi CSP violation, lỗi frontend, tỷ lệ hoàn tất luồng nghiệp vụ và ticket hỗ trợ.
4. Chuẩn bị rollback có kiểm soát nếu phát hiện chức năng quan trọng bị chặn.
5. Sau rollout, tiếp tục xử lý report của policy enforced và policy Report-only riêng biệt.

Report-only có thể được giữ lâu dài cho một policy mục tiêu kế tiếp. Nó không nhất thiết chỉ dùng một lần trước khi bật CSP.

## 9. Test matrix cho Report-only mode

| ID | Thử nghiệm | Kết quả mong đợi |
| --- | --- | --- |
| RO-01 | Response có header Report-only hợp lệ | DevTools hiển thị policy và browser đánh giá policy |
| RO-02 | Inline script vi phạm `script-src 'self'` | Có report; script vẫn chạy |
| RO-03 | Inline style vi phạm `style-src 'self'` | Có report; style vẫn được áp dụng |
| RO-04 | External script không thuộc allowlist | Có report; script vẫn được tải trong Report-only |
| RO-05 | Cùng policy chuyển sang header enforced | Hành vi vi phạm bị chặn theo directive |
| RO-06 | Header CSP enforced cũ và Report-only mới cùng tồn tại | Policy enforced cũ vẫn hoạt động; policy mới chỉ report |
| RO-07 | Dùng `<meta http-equiv>` cho Report-only | Không bật được chế độ Report-only |
| RO-08 | Endpoint nhận legacy report | Collector parse được object `csp-report` |
| RO-09 | Endpoint nhận Reporting API report | Collector parse được mảng report và trường `body` |
| RO-10 | Report có `disposition: report` | Dashboard phân loại là Report-only |
| RO-11 | Browser không hỗ trợ report-to | Fallback `report-uri` được dùng nếu browser hỗ trợ directive này |
| RO-12 | Endpoint trả lỗi hoặc mạng offline | Ứng dụng chính vẫn hoạt động; report có thể thất lạc |
| RO-13 | Report trùng hoặc gửi muộn | Collector xử lý idempotent và không làm sai thống kê |
| RO-14 | Query string chứa dữ liệu nhạy cảm | Collector redact trước khi lưu/hiển thị theo policy riêng tư |
| RO-15 | CSP policy thay đổi giữa release | Dashboard giữ được policy/release context để so sánh |

### 9.1. Kiểm tra chức năng không bị chặn

Trong Report-only, hành vi vi phạm vẫn phải tiếp tục. Test này xác nhận đúng semantics của chế độ:

- script inline test marker vẫn thực thi;
- style inline vẫn được áp dụng;
- tài nguyên vi phạm vẫn được browser tải nếu không bị một policy enforced khác chặn;
- report vẫn xuất hiện nếu browser và endpoint hỗ trợ.

Nếu tài nguyên bị chặn trong giai đoạn này, hãy kiểm tra xem response có CSP enforced khác, extension, mixed-content policy, CORS, network error hoặc cơ chế browser khác đang tác động hay không.

## 10. Lab: quan sát Report-only bằng Node.js

Lab tạo một HTTP server local có hai trang:

- `/` có inline script và inline style vi phạm policy thử nghiệm.
- `/clean` không có inline code, dùng làm positive control cho trang không phát sinh violation từ hai directive đó.

Server gửi `Content-Security-Policy-Report-Only`, nhận report tại `/csp-report` và in report ra terminal. Vì đang ở Report-only, inline script và style trên trang `/` vẫn hoạt động.

### 10.1. Tạo server

Tạo file `csp-report-only-lab.mjs`:

```javascript
import { createServer } from "node:http";

const reportPath = "/csp-report";
const reportLimit = 64 * 1024;

const noisyPage = [
  "<!doctype html>",
  '<html lang="vi">',
  "<meta charset=\"utf-8\">",
  "<title>CSP Report-only lab</title>",
  "<style>body { color: teal; }</style>",
  '<h1 id="status">Loading...</h1>',
  "<script>",
  'document.querySelector("#status").textContent = "Inline script still ran";',
  'document.addEventListener("securitypolicyviolation", event => {',
  '  console.log("CSP violation", {',
  "    directive: event.effectiveDirective,",
  "    disposition: event.disposition,",
  "    blockedURI: event.blockedURI",
  "  });",
  "});",
  "</script>",
  "</html>"
].join("\n");

const cleanPage = [
  "<!doctype html>",
  '<html lang="vi">',
  "<meta charset=\"utf-8\">",
  "<title>Clean control</title>",
  "<h1>Trang không có inline script hoặc style</h1>",
  "</html>"
].join("\n");

function sendPage(res, html) {
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Reporting-Endpoints": 'csp-endpoint="http://localhost:3000/csp-report"',
    "Content-Security-Policy-Report-Only":
      "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri http://localhost:3000/csp-report"
  });
  res.end(html);
}

const server = createServer((req, res) => {
  if (req.method === "POST" && req.url === reportPath) {
    const chunks = [];
    let size = 0;
    let tooLarge = false;

    req.on("data", chunk => {
      size += chunk.length;
      if (size > reportLimit) {
        tooLarge = true;
        return;
      }
      if (!tooLarge) chunks.push(chunk);
    });

    req.on("end", () => {
      if (tooLarge) {
        res.writeHead(413);
        res.end();
        return;
      }
      const raw = Buffer.concat(chunks).toString("utf8");
      try {
        const report = JSON.parse(raw);
        console.log("CSP report received:");
        console.log(JSON.stringify(report, null, 2));
      } catch {
        console.log("Invalid JSON report received");
      }

      res.writeHead(204, { "Cache-Control": "no-store" });
      res.end();
    });
    return;
  }

  if (req.method === "GET" && req.url === "/") {
    return sendPage(res, noisyPage);
  }

  if (req.method === "GET" && req.url === "/clean") {
    return sendPage(res, cleanPage);
  }

  res.writeHead(404);
  res.end("Not found");
});

server.listen(3000, () => {
  console.log("Open http://localhost:3000/");
  console.log("Clean control: http://localhost:3000/clean");
});
```

Chạy:

```bash
node csp-report-only-lab.mjs
```

Mở `http://localhost:3000/` trong browser. Nếu browser không gửi report qua HTTP localhost theo cấu hình Reporting API, kiểm tra console/Network và có thể chạy lab trên HTTPS local với chứng chỉ dev được tin cậy. Không bỏ qua cảnh báo chứng chỉ cho website thật.

### 10.2. Quan sát trang có violation

Trên `http://localhost:3000/`:

1. Tiêu đề chuyển thành **Inline script still ran**. Điều này chứng minh Report-only không chặn script.
2. Nội dung được tô màu teal. Inline style vẫn được áp dụng.
3. DevTools → Console có thể hiển thị event `securitypolicyviolation`.
4. DevTools → Network có thể thấy POST tới `/csp-report`. Reporting API có thể gửi trễ hoặc gom report.
5. Terminal hiển thị JSON report nhận được, thường có directive liên quan `script-src-elem` hoặc `style-src-elem` và disposition `report`.

### 10.3. So sánh với trang clean

Mở `http://localhost:3000/clean`. Trang không có inline script hoặc style, nên hai directive `script-src` và `style-src` không nên phát violation từ nội dung đó. Browser vẫn có thể phát report cho những tài nguyên khác nếu chúng vi phạm policy.

Trang clean là positive control giúp xác nhận collector không chỉ nhận report do lỗi cấu hình endpoint hoặc một nguồn vi phạm chung.

### 10.4. Thử chuyển sang enforcement

Trong môi trường lab, đổi tên header trong hàm `sendPage` từ `Content-Security-Policy-Report-Only` thành `Content-Security-Policy` rồi tải lại `/`.

Kết quả mong đợi:

- inline script bị chặn và tiêu đề vẫn là `Loading...`;
- inline style bị chặn;
- browser ghi violation với disposition `enforce`;
- report có thể tiếp tục được gửi nếu endpoint reporting vẫn được cấu hình trong policy enforced.

Hoàn nguyên header về Report-only để tiếp tục bài học. Dừng server bằng Ctrl+C. Đây là lab local, không triển khai collector demo ra Internet.

## 11. Những ngộ nhận thường gặp

**“Report-only chặn tài nguyên để xem ứng dụng có lỗi không.”** Sai. Nó báo cáo violation nhưng vẫn cho hành vi vi phạm tiếp tục, trừ khi một policy enforced khác chặn.

**“Không có report nghĩa là policy đã an toàn.”** Sai. Browser có thể chưa đi qua route, không hỗ trợ reporting, gửi report muộn hoặc bị mạng/extension chặn.

**“Chỉ cần đặt `Content-Security-Policy-Report-Only` trong thẻ meta.”** Sai. Report-only phải được gửi bằng HTTP response header.

**“CORS kiểm soát CSP report.”** Sai. CORS và CSP là cơ chế khác nhau; endpoint reporting cần được cấu hình theo Reporting API/CSP và có xử lý request riêng.

**“`report-uri` và `report-to` là hai directive có thể thay thế hoàn toàn cho nhau ở mọi browser.”** Sai. Mức hỗ trợ khác nhau; thường cấu hình cả hai trong giai đoạn chuyển tiếp.

**“Report là bằng chứng chắc chắn có tấn công.”** Sai. Có thể là dependency hợp lệ, extension, policy chưa hoàn chỉnh hoặc lỗi deploy. Cần điều tra trước khi thay policy.

**“Thêm host gây violation vào `script-src` là cách xử lý chuẩn.”** Sai. Phải xác minh nguồn và quyền kiểm soát trước; allowlist rộng có thể làm CSP yếu đi.

**“Report-only thay thế kiểm thử browser.”** Sai. Report chỉ phản ánh hành vi được quan sát; vẫn cần automation và test thủ công cho luồng ít dùng.

**“Endpoint report là dữ liệu đáng tin vì browser gửi.”** Sai. Request có thể bị giả mạo hoặc spam; report và field bên trong phải được xử lý như input không tin cậy.

**“Report collector có thể dùng làm audit log bảo mật.”** Sai. Report có thể thiếu, trùng, đến muộn hoặc bị browser bỏ; audit log nghiệp vụ cần nguồn sự thật phía server.

## 12. Checklist triển khai Report-only

Trước khi rollout, xác nhận:

1. **Header:** CSP Report-only được gửi qua HTTP response header trên mọi route HTML cần quan sát.
2. **Policy:** directive phù hợp inventory thực tế; không dùng wildcard hoặc unsafe directive chỉ để giảm report.
3. **Enforcement hiện có:** policy đang enforce vẫn được giữ và kiểm tra độc lập.
4. **Nonce/hash:** nonce riêng từng response; hash khớp nội dung chính xác; không tái sử dụng nonce.
5. **Reporting endpoint:** khai báo `Reporting-Endpoints` và `report-to`; giữ `report-uri` fallback khi cần tương thích.
6. **Collector:** giới hạn body, rate limit, timeout, parse JSON an toàn, trả response nhanh và không làm ảnh hưởng app.
7. **Privacy:** redact URL/query nhạy cảm; hạn chế `report-sample`; đặt retention và quyền truy cập.
8. **Classification:** phân loại report theo directive, route, browser, release và owner; không allowlist tự động.
9. **Coverage:** test login, payment, editor, upload, widget, route lỗi, browser mục tiêu và feature flag.
10. **Semantics:** xác nhận violation trong Report-only vẫn chạy; test enforcement riêng trong môi trường kiểm soát.
11. **Monitoring:** theo dõi report theo release và browser; phân biệt `report` với `enforce`.
12. **Promotion:** chỉ chuyển sang enforcement sau khi report đã được điều tra và các luồng nghiệp vụ đã được kiểm thử.
13. **Rollback:** có cách phục hồi có kiểm soát và người chịu trách nhiệm khi policy enforce chặn chức năng.
14. **Continuous hardening:** sau khi enforce, tiếp tục giữ Report-only cho policy mục tiêu chặt hơn nếu có ích.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trang có inline script vi phạm `script-src 'self'` trong Report-only. Browser có chạy script không?  
**Đáp án:** Có, nếu không có policy enforced khác chặn. Report-only chỉ phát violation report.

**Câu 2.** Có thể khai báo Report-only bằng `<meta http-equiv>` không?  
**Đáp án:** Không. Header Report-only phải được gửi trong HTTP response.

**Câu 3.** Khi response có cả CSP enforced và CSP Report-only, policy enforced có bị thay thế không?  
**Đáp án:** Không. Policy enforced tiếp tục áp dụng; policy Report-only được đánh giá độc lập.

**Câu 4.** Vì sao nên cấu hình cả `report-to` và `report-uri`?  
**Đáp án:** `report-to` dùng Reporting API với endpoint group; `report-uri` là fallback cho browser chưa hỗ trợ cơ chế mới.

**Câu 5.** `disposition: report` có ý nghĩa gì?  
**Đáp án:** Violation được báo cáo ở chế độ Report-only; policy đó không chặn hành vi.

**Câu 6.** Có nên tự động thêm mọi blocked host vào `script-src`?  
**Đáp án:** Không. Xác minh owner, mục đích, chain tải và rủi ro trước; ưu tiên policy hẹp.

**Câu 7.** Vì sao report endpoint cần rate limit và retention?  
**Đáp án:** Report có thể bị spam, trùng hoặc chứa URL và source information nhạy cảm; cần kiểm soát chi phí và quyền riêng tư.

**Câu 8.** Không nhận report trong một ngày có chứng minh không có CSP violation?  
**Đáp án:** Không. Browser có thể chưa quan sát hành vi vi phạm, không hỗ trợ reporting hoặc report bị trì hoãn/thất lạc.

## 14. Ghi nhớ cốt lõi

`Content-Security-Policy-Report-Only` cho phép browser đánh giá một CSP policy và gửi violation report mà không chặn hành vi vi phạm. Nó hữu ích để kiểm kê dependency, phát hiện inline code, thử nonce/hash và chuẩn bị policy trước khi enforcement. Header phải được gửi qua HTTP response; không thể bật Report-only bằng meta tag.

Dùng `Reporting-Endpoints` cùng `report-to` cho Reporting API hiện đại và cân nhắc `report-uri` làm fallback tương thích. Phân loại report theo directive, route, browser và release; bảo vệ collector khỏi spam và rò rỉ dữ liệu; không allowlist nguồn một cách máy móc. **Report-only là công cụ quan sát và giảm rủi ro rollout, không phải cơ chế chặn XSS và cũng không chứng minh policy đã hoàn chỉnh.**

### Tài liệu tham khảo

- [MDN — Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only).
- [MDN — Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP).
- [MDN — Reporting API](https://developer.mozilla.org/en-US/docs/Web/API/Reporting_API).
- [MDN — Reporting-Endpoints header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Reporting-Endpoints).
- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/).
- [W3C — Reporting API](https://www.w3.org/TR/reporting-1/).
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html).
