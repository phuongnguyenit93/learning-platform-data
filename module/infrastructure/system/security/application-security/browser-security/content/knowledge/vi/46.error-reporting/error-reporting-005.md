# Reporting API

Reporting API là cơ chế của trình duyệt để ghi nhận và gửi các báo cáo về một số sự kiện liên quan đến trang web. Ví dụ, trình duyệt có thể tạo báo cáo khi một tài nguyên bị Content Security Policy (CSP) chặn, khi trang sử dụng một tính năng sắp bị loại bỏ hoặc khi trình duyệt áp dụng một intervention. Ứng dụng có thể nhận các báo cáo này ở máy chủ để theo dõi lỗi tương thích, phát hiện cấu hình bảo mật chưa đúng và ưu tiên sửa lỗi dựa trên hành vi thực tế.

Reporting API đặc biệt hữu ích khi triển khai CSP, Permissions Policy hoặc các chính sách cách ly theo từng giai đoạn. Trong môi trường production, nhóm phát triển khó tái hiện mọi trang, thiết bị và luồng người dùng. Báo cáo từ trình duyệt bổ sung bằng chứng về những gì đã xảy ra ở client.

Reporting API không phải hệ thống ghi nhận mọi lỗi JavaScript, cũng không phải cơ chế chặn tấn công. Nó cung cấp một kênh thu thập report cho những loại sự kiện mà trình duyệt hỗ trợ. Chính sách như CSP vẫn quyết định tài nguyên nào được phép tải; Reporting API chỉ giúp quan sát và phân tích một số quyết định hoặc sự kiện đó.

## Thành phần và luồng hoạt động

Một hệ thống báo cáo thường có bốn thành phần:

1. **Nguồn tạo report:** trình duyệt phát hiện một sự kiện có thể báo cáo, chẳng hạn vi phạm CSP hoặc deprecation.
2. **Bộ đệm của trình duyệt:** browser tạo report, xếp hàng và có thể gộp nhiều report trước khi gửi.
3. **Endpoint nhận report:** ứng dụng khai báo một hoặc nhiều URL để browser gửi dữ liệu đến.
4. **Pipeline xử lý:** máy chủ kiểm tra định dạng, loại bỏ dữ liệu nhạy cảm, lưu trữ, tổng hợp và hiển thị số liệu cho nhóm vận hành.

~~~mermaid
flowchart TD
    E[Sự kiện trong trình duyệt] --> R[Browser tạo report]
    R --> Q[Hàng đợi report của browser]
    Q -->|HTTP POST theo lô| EP[Reporting endpoint]
    EP --> V[Kiểm tra schema và giới hạn]
    V --> S[Chuẩn hóa và giảm dữ liệu nhạy cảm]
    S --> D[Kho dữ liệu / hệ thống quan sát]
    D --> A[Phân tích xu hướng và cảnh báo]
    R --> O[ReportingObserver trong trang]
    O --> L[Telemetry phía client nếu cần]
~~~

Trình duyệt quyết định thời điểm gửi report. Việc gửi có thể bị trì hoãn, gộp lô hoặc không xảy ra nếu browser đóng, thiết bị ngoại tuyến, report hết hạn hoặc chính sách của trình duyệt không cho phép gửi. Vì vậy, hệ thống không nên giả định mỗi sự kiện đều tạo ra đúng một request ngay lập tức. Báo cáo là tín hiệu quan sát có ích, không phải nhật ký kiểm toán bảo đảm đầy đủ.

## Những loại report thường gặp

Các loại report phụ thuộc vào browser, phiên bản và tính năng đang được sử dụng. Một số loại thường được gặp trong hệ sinh thái Chromium:

| Loại report | Sự kiện có thể tạo report | Cách sử dụng |
|---|---|---|
| `csp-violation` | Tài nguyên hoặc hành vi vi phạm chính sách CSP | Phát hiện policy quá chặt, cấu hình sai hoặc hoạt động đáng ngờ |
| `deprecation` | Trang sử dụng API hoặc hành vi đã bị đánh dấu deprecated | Tìm vị trí cần cập nhật trước khi API bị loại bỏ |
| `intervention` | Trình duyệt can thiệp vào một hành vi vì lý do hiệu năng, an toàn hoặc trải nghiệm | Phát hiện tính năng bị browser hạn chế |
| `permissions-policy-violation` | Một tính năng bị chặn bởi Permissions Policy trong browser có hỗ trợ report tương ứng | Kiểm tra chính sách quyền của document và iframe |
| Report về COOP/COEP hoặc network error | Một số cơ chế cách ly hoặc Network Error Logging tạo report theo cấu hình và hỗ trợ của browser | Điều tra vấn đề tương thích, tải tài nguyên và cách ly browsing context |

Không phải mọi browser đều hỗ trợ cùng loại report hoặc cùng trường dữ liệu. Trước khi thiết kế dashboard hay cảnh báo, cần kiểm tra danh sách loại report thực tế trên các browser mục tiêu và thử với phiên bản đang triển khai.

Reporting API cũng không tự động thu mọi lỗi JavaScript như exception không được bắt, promise rejection hoặc lỗi logic nghiệp vụ. Những lỗi này thường cần `window.onerror`, `unhandledrejection` hoặc SDK theo dõi lỗi riêng. Không nên gộp tất cả tín hiệu vào một nhãn “Reporting API” nếu nguồn và độ tin cậy của chúng khác nhau.

## Khai báo endpoint bằng Reporting-Endpoints

Website khai báo endpoint bằng response header `Reporting-Endpoints`. Mỗi mục ánh xạ một tên nhóm endpoint với một URL nhận report. Ví dụ:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp", default="https://reports.example.com/browser"
~~~

Sau đó, một chính sách hỗ trợ Reporting API có thể tham chiếu tên endpoint. Với CSP, directive `report-to` dùng tên nhóm đã khai báo:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint
~~~

Ở đây, `csp-endpoint` là tên nhóm được ánh xạ trong `Reporting-Endpoints`. Browser có thể gửi báo cáo vi phạm CSP đến URL tương ứng. Nếu trang cần tương thích với browser cũ chưa hỗ trợ `report-to` hoặc `Reporting-Endpoints`, có thể duy trì `report-uri` như phương án dự phòng trong giai đoạn chuyển đổi:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri https://reports.example.com/csp
~~~

`report-uri` là cơ chế cũ và không thay thế được toàn bộ khả năng của Reporting API mới. Hỗ trợ và hành vi dự phòng khác nhau giữa browser; cần kiểm thử trên ma trận trình duyệt thực tế. Header `Report-To` đời cũ đã được thay bằng `Reporting-Endpoints` trong thiết kế mới, vì vậy không nên bắt đầu một triển khai mới bằng cách chỉ cấu hình `Report-To`.

### Dùng Report-Only để quan sát trước khi chặn

Khi triển khai CSP mới, thay đổi policy ngay có thể làm hỏng tính năng hợp lệ. Có thể dùng `Content-Security-Policy-Report-Only` để browser tạo report về các vi phạm giả định mà không chặn tài nguyên theo policy đó:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp-endpoint; report-uri https://reports.example.com/csp
~~~

Trong giai đoạn này, nhóm phát triển quan sát report, xác định script hoặc host hợp lệ còn thiếu, sửa policy và thử lại. Khi đã hiểu các vi phạm và xác nhận policy phù hợp, chuyển dần sang `Content-Security-Policy` để browser thực sự thực thi. Report-Only không chặn tài nguyên; do đó nó không thể thay thế policy đang enforce và không phải biện pháp phòng vệ độc lập.

## Quan sát report trong JavaScript bằng ReportingObserver

`ReportingObserver` cho phép mã JavaScript trong document nhận những report mà browser cung cấp cho observer. Cách này phù hợp để bổ sung telemetry tại client, kiểm tra trong môi trường phát triển hoặc ghi nhận một số loại report ngay trong ứng dụng.

~~~javascript
if ('ReportingObserver' in window) {
  const observer = new ReportingObserver((reports) => {
    for (const report of reports) {
      // Chỉ lấy trường cần thiết cho mục đích chẩn đoán.
      const item = {
        type: report.type,
        url: report.url,
        body: report.body
      };

      console.info('Browser report', item);
    }
  }, {
    types: ['deprecation', 'intervention', 'csp-violation'],
    buffered: true
  });

  observer.observe();
}
~~~

`types` giới hạn những loại report mà observer quan tâm. `buffered: true` yêu cầu observer nhận cả những report phù hợp đã được browser lưu trong bộ đệm trước thời điểm `observe()`. Khi không bật tùy chọn này, observer chủ yếu nhận report mới phát sinh sau khi bắt đầu quan sát.

Một số phương thức hữu ích:

- `observe()` bắt đầu nhận report.
- `takeRecords()` lấy các report đang chờ trong hàng đợi của observer.
- `disconnect()` dừng observer và giải phóng việc quan sát.
- `report.type`, `report.url` và `report.body` cung cấp loại report, URL liên quan và dữ liệu chi tiết do browser cung cấp.

Không phải mọi report mà browser gửi đến endpoint đều nhất thiết được cung cấp cho observer trong document, và ngược lại. ReportingObserver và việc gửi report đến endpoint là hai đường thu thập khác nhau. Cần kiểm tra hỗ trợ browser trước khi phụ thuộc vào API này:

~~~javascript
const reportingObserverSupported = 'ReportingObserver' in window;
~~~

Không gửi nguyên `report.body` đến một dịch vụ thứ ba nếu chưa đánh giá quyền riêng tư. Body có thể chứa URL, vị trí mã nguồn, directive, tên tài nguyên hoặc mẫu nội dung liên quan đến trang. Hãy chọn trường tối thiểu cần dùng và áp dụng cùng chính sách giảm dữ liệu như ở endpoint máy chủ.

## Định dạng và tiếp nhận report ở máy chủ

Browser thường gửi report đến endpoint bằng HTTP POST. Với định dạng Reporting API mới, request có thể sử dụng media type `application/reports+json` và chứa một mảng report. Mỗi phần tử thường có các trường như `age`, `type`, `url`, `user_agent` và `body`; cấu trúc `body` thay đổi theo loại report.

Ví dụ rút gọn về một report CSP:

~~~json
[
  {
    "age": 120,
    "type": "csp-violation",
    "url": "https://app.example.com/account",
    "user_agent": "Browser information",
    "body": {
      "blockedURL": "https://cdn.example.net/widget.js",
      "effectiveDirective": "script-src-elem",
      "disposition": "report",
      "statusCode": 200
    }
  }
]
~~~

Đây là ví dụ minh họa; trường thực tế có thể khác theo loại report và browser. Endpoint phải chấp nhận batch có nhiều phần tử, kiểm tra schema theo `type` và chịu được report trùng lặp hoặc đến trễ.

Ví dụ dưới đây minh họa cách tiếp nhận bằng Express. Phần chuẩn hóa chỉ lưu một số trường đã chọn; các hàm lưu trữ và định tuyến thực tế cần được triển khai theo hệ thống của ứng dụng:

~~~javascript
import express from 'express';

const app = express();
const allowedOrigins = new Set(['https://app.example.com']);

app.post(
  '/csp',
  express.json({
    type: ['application/reports+json', 'application/json'],
    limit: '64kb'
  }),
  async (req, res) => {
    if (!Array.isArray(req.body) || req.body.length > 50) {
      return res.sendStatus(400);
    }

    const accepted = [];

    for (const report of req.body) {
      if (!report || typeof report !== 'object') continue;
      if (typeof report.type !== 'string' || typeof report.url !== 'string') continue;

      let pageUrl;
      try {
        pageUrl = new URL(report.url);
      } catch {
        continue;
      }

      if (pageUrl.protocol !== 'https:' || !allowedOrigins.has(pageUrl.origin)) {
        continue;
      }

      if (report.type === 'csp-violation') {
        const body = report.body && typeof report.body === 'object'
          ? report.body
          : {};

        accepted.push({
          type: 'csp-violation',
          pageOrigin: pageUrl.origin,
          effectiveDirective: typeof body.effectiveDirective === 'string'
            ? body.effectiveDirective.slice(0, 100)
            : null,
          disposition: typeof body.disposition === 'string'
            ? body.disposition.slice(0, 20)
            : null
        });
      }
    }

    await storeReports(accepted);
    return res.sendStatus(204);
  }
);
~~~

`storeReports` là hàm lưu trữ minh họa cần được cung cấp trong ứng dụng. Ví dụ chỉ giữ origin và hai trường CSP để tránh lưu URL đầy đủ hoặc toàn bộ body. Trong triển khai thực tế, cần bổ sung schema riêng cho từng loại report, giới hạn batch, xử lý JSON sai định dạng, giới hạn tốc độ và cơ chế chống quá tải. Không dùng trực tiếp dữ liệu report để tạo câu lệnh SQL, HTML hoặc lệnh hệ thống.

## Bảo vệ endpoint và dữ liệu report

Report được tạo ở phía client và gửi qua mạng công cộng. Một request đến endpoint không chứng minh nó thực sự do browser đáng tin cậy tạo ra. Bất kỳ client nào có thể gửi HTTP request cũng có thể giả mạo JSON có hình thức giống report. Vì vậy, report chỉ nên được coi là telemetry, không phải bằng chứng xác thực danh tính hoặc bằng chứng duy nhất để kết luận một cuộc tấn công đã xảy ra.

Endpoint nhận report cần được thiết kế như một API công khai có thể bị lạm dụng:

- **Kiểm tra đầu vào:** xác nhận content type, JSON hợp lệ, kiểu dữ liệu, độ dài chuỗi, số lượng report trong batch và schema theo từng loại.
- **Giới hạn tài nguyên:** giới hạn kích thước body, tốc độ request, số report mỗi batch và dung lượng hàng đợi. Có thể dùng quota theo endpoint, origin hoặc tín hiệu mạng; không dựa duy nhất vào IP vì nhiều người dùng có thể dùng chung NAT.
- **Không tin dữ liệu nhận dạng:** `user_agent`, URL, timestamp và mọi trường trong body đều có thể thiếu, cũ hoặc bị giả mạo. Không dùng chúng làm thông tin xác thực.
- **Chống injection:** encode dữ liệu khi hiển thị, dùng truy vấn có tham số khi lưu, loại bỏ ký tự điều khiển trong log và không render report như HTML.
- **Tránh SSRF:** không tự động truy cập URL xuất hiện trong `blockedURL`, `sourceFile`, `documentURL` hoặc trường khác. Các URL đó là dữ liệu báo cáo, không phải chỉ thị để máy chủ fetch.
- **Phản hồi gọn:** sau khi chấp nhận hoặc loại bỏ report theo chính sách, trả phản hồi thành công phù hợp, thường là `204 No Content`; không trả lại dữ liệu nội bộ hoặc stack trace.
- **Cô lập xử lý:** đưa report vào hàng đợi hoặc pipeline bất đồng bộ để việc phân tích nặng không làm endpoint nhận bị treo.

Endpoint thu thập report thường cần nhận request không kèm phiên đăng nhập của ứng dụng. Không nên phụ thuộc vào cookie phiên người dùng để xác thực report. CORS, header `Origin` hoặc `Referer` có thể hỗ trợ phân tích nguồn trong một số luồng, nhưng không thay thế xác thực và giới hạn tài nguyên vì client tùy ý có thể giả mạo request.

### Giảm thiểu dữ liệu nhạy cảm

Một report CSP có thể chứa URL của document, URL tài nguyên bị chặn, vị trí file nguồn, dòng và cột, directive, referrer hoặc mẫu mã nguồn nếu policy yêu cầu gửi sample. URL có thể chứa mã định danh, email, token hoặc tham số tìm kiếm. Vì vậy:

1. Tránh đặt bí mật trong query string hoặc path có thể xuất hiện trong URL.
2. Chỉ lưu origin, route đã chuẩn hóa hoặc route template nếu mục tiêu phân tích không cần URL đầy đủ.
3. Không bật `report-sample` trừ khi thật sự cần mẫu mã nguồn để điều tra và đã đánh giá nguy cơ lộ dữ liệu.
4. Lọc hoặc rút gọn `blockedURL`, `sourceFile`, `referrer` và các trường tự do trước khi lưu.
5. Đặt thời hạn lưu trữ, quyền truy cập và quy trình xóa report; tránh cho toàn bộ nhóm vận hành xem được dữ liệu thô nếu không cần.
6. Không ghi toàn bộ report vào log ứng dụng mặc định, vì log thường được sao chép sang nhiều hệ thống và có thời hạn lưu dài.

Nếu endpoint phục vụ nhiều website, cần xác định rõ origin nào được phép gửi và cách tách dữ liệu giữa các tenant. Danh sách origin cho phép giúp giảm report rác nhưng không biến report thành dữ liệu đã xác thực. Hệ thống vẫn phải xử lý trường hợp client giả mạo origin hoặc gửi payload không hợp lệ.

## Phân tích report và tránh cảnh báo sai

Một lượng lớn report không nhất thiết đồng nghĩa có cuộc tấn công. CSP Report-Only có thể tạo nhiều report vì policy đang thử nghiệm. Một tiện ích trình duyệt, extension hoặc script bên thứ ba có thể tạo hành vi không giống luồng người dùng phổ biến. Một số browser cũng gửi lại report khi mạng phục hồi hoặc gộp nhiều sự kiện.

Khi phân tích, nên nhóm theo các chiều có ích:

- `type` và directive, ví dụ `csp-violation` với `script-src-elem`.
- Origin hoặc route đã chuẩn hóa của document.
- Origin tài nguyên bị chặn, sau khi đã loại bỏ phần path/query nhạy cảm.
- Phiên bản ứng dụng, phiên bản policy và giai đoạn triển khai.
- Browser family hoặc phiên bản ở mức đủ dùng cho phân tích tương thích.
- Khoảng thời gian, tần suất và số lượng client ước lượng.

Không đếm mọi report thành một sự cố độc lập. Có thể khử trùng lặp theo tổ hợp type, directive, origin, route template và khoảng thời gian. Khi cảnh báo, kết hợp report với log server, thay đổi triển khai và bằng chứng khác. Một report bị giả mạo có thể làm nhiễu dashboard hoặc tạo cảnh báo giả, do đó không tự động khóa tài khoản hoặc chặn người dùng chỉ dựa vào một report chưa được xác minh.

## Quy trình triển khai Reporting API

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Chọn tín hiệu:** xác định loại report cần theo dõi, ví dụ CSP violation và deprecation; tránh thu thập tất cả dữ liệu nếu chưa có mục đích.
2. **Thiết kế endpoint:** xác định URL, nhóm endpoint, giới hạn request, schema, nơi lưu, quyền truy cập và thời hạn lưu trữ.
3. **Bật chế độ quan sát:** cấu hình `Reporting-Endpoints` và policy Report-Only trên một nhóm người dùng hoặc môi trường staging.
4. **Kiểm tra dữ liệu:** xác nhận report đến đúng endpoint, batch được parse, trường nhạy cảm được rút gọn và report sai định dạng bị loại bỏ.
5. **Phân tích:** phân loại vi phạm hợp lệ, lỗi cấu hình, extension hoặc script bên thứ ba và dấu hiệu cần điều tra.
6. **Điều chỉnh policy:** sửa allowlist hoặc mã ứng dụng có căn cứ; không thêm nguồn rộng chỉ để làm dashboard hết report.
7. **Enforce theo giai đoạn:** chuyển policy đã kiểm chứng sang CSP enforce, theo dõi report tiếp tục và chuẩn bị phương án rollback.
8. **Vận hành:** theo dõi chất lượng endpoint, tỷ lệ report bị loại, dung lượng lưu, thời hạn lưu và thay đổi hỗ trợ của browser.

## Kiểm thử trong môi trường phát triển

Để xác minh luồng report, dùng một trang thử nghiệm và endpoint do nhóm kiểm soát. Không tạo policy lỏng trên website production chỉ để thử nghiệm.

**Kiểm tra header:** mở DevTools, chọn request tài liệu HTML và xem response headers. Xác nhận `Reporting-Endpoints` và CSP có đúng tên nhóm, URL và directive `report-to`.

**Tạo vi phạm có kiểm soát:** trong môi trường thử nghiệm, cấu hình CSP Report-Only chỉ cho phép script từ origin thử nghiệm. Sau đó tham chiếu một script test trên origin khác do nhóm quản lý. Vì policy ở chế độ Report-Only, browser không chặn script theo policy đó nhưng có thể tạo report. Khi kiểm tra chính sách enforce, dùng tài nguyên thử nghiệm vô hại và xác nhận browser chặn đúng tài nguyên ngoài allowlist.

**Kiểm tra ReportingObserver:** tạo observer với `buffered: true`, ghi lại `report.type` và những trường đã chọn. Xác nhận mã có feature detection và không làm ứng dụng lỗi khi browser không hỗ trợ API.

**Kiểm tra endpoint:** quan sát request POST, content type, batch và status response. Gửi thêm payload JSON sai định dạng, batch quá lớn, trường sai kiểu và URL ngoài origin cho phép để xác nhận endpoint từ chối hoặc loại bỏ an toàn. Thực hiện các phép thử này trên endpoint thử nghiệm.

**Kiểm tra quyền riêng tư:** tạo URL thử nghiệm có query string giả lập dữ liệu nhạy cảm, rồi xác nhận pipeline lưu trữ đã loại bỏ query và fragment. Không sử dụng token hoặc thông tin cá nhân thật để kiểm tra.

**Kiểm tra độ tin cậy:** ngắt mạng hoặc đóng browser sau khi phát sinh sự kiện, sau đó quan sát rằng report có thể không đến ngay hoặc không đến. Đây là cách kiểm tra dashboard không giả định tính đầy đủ tuyệt đối của kênh báo cáo.

## Checklist review

- [ ] Đã xác định loại report cần thu thập và browser hỗ trợ tương ứng.
- [ ] `Reporting-Endpoints` khai báo đúng tên nhóm và URL nhận report.
- [ ] CSP dùng đúng `report-to`; có phương án tương thích cho browser mục tiêu khi cần.
- [ ] Report-Only được dùng để quan sát trước khi chuyển policy sang enforce.
- [ ] ReportingObserver có feature detection và chỉ theo dõi loại report cần thiết.
- [ ] Endpoint xử lý batch, content type, schema, body size và rate limit.
- [ ] Dữ liệu report được coi là đầu vào không tin cậy và có thể bị giả mạo.
- [ ] URL, query string, source sample và thông tin người dùng được giảm thiểu trước khi lưu.
- [ ] Pipeline không fetch URL từ report và không render dữ liệu thô như HTML.
- [ ] Có chính sách retention, phân quyền truy cập và xử lý dữ liệu theo tenant.
- [ ] Dashboard phân biệt tín hiệu quan sát với bằng chứng bảo mật đã xác minh.
- [ ] Đã kiểm thử trên browser mục tiêu, cả khi endpoint lỗi hoặc browser không hỗ trợ API.

## Câu hỏi tự kiểm tra

1. Reporting API khác `window.onerror` và `unhandledrejection` ở mục đích và nguồn tạo report như thế nào?
2. `Reporting-Endpoints` liên kết với CSP bằng directive nào? `report-uri` còn vai trò gì trong giai đoạn tương thích?
3. Vì sao CSP Report-Only hữu ích trước khi chuyển sang policy enforce?
4. Tại sao endpoint nhận report phải coi payload là dữ liệu không tin cậy dù request được gửi bởi browser?
5. Những trường nào trong CSP report có thể làm lộ dữ liệu nhạy cảm, và có thể giảm thiểu bằng cách nào?
6. Vì sao không nên coi việc không nhận report là bằng chứng chắc chắn rằng không có vi phạm?

Reporting API giúp nhóm phát triển quan sát cách browser thực thi chính sách và xử lý các tính năng web trong môi trường thực. Giá trị của nó phụ thuộc vào cấu hình đúng, endpoint có khả năng chống lạm dụng, dữ liệu được giảm thiểu và cách diễn giải report có xét đến giới hạn của browser. Hãy dùng report để tìm vấn đề và xác định nơi cần điều tra; việc thực thi bảo mật vẫn phải đến từ CSP, Permissions Policy, cơ chế cách ly và thiết kế ứng dụng phù hợp.
