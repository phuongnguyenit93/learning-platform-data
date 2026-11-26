# Báo cáo vi phạm và lộ trình chuyển từ quan sát sang chặn

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bối cảnh: một CSP chặt có thể làm ứng dụng ngừng hoạt động

Một ứng dụng Spring Boot đang vận hành có giao diện dashboard, thư viện UI, API bên ngoài, hệ thống thanh toán và trình soạn thảo văn bản. Nhóm phát triển muốn chuyển từ việc chưa dùng CSP sang:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Đây là điểm khởi đầu tốt để thảo luận, nhưng nếu bật chặn ngay lập tức, một số chức năng hợp lệ có thể hỏng:

- Trang còn dùng một khối `<script>...</script>` inline để khởi tạo dữ liệu.
- Thư viện UI tạo `<style>` động, không có nonce/hash phù hợp.
- Ảnh sản phẩm tải từ CDN không nằm trong `img-src`.
- Frontend gọi API ở origin khác hoặc mở WebSocket không nằm trong `connect-src`.
- Biểu mẫu SSO hoặc thanh toán POST sang một origin ngoài `'self'`.

Giải pháp triển khai thực tế không phải mặc định thêm `'unsafe-inline'`, `'unsafe-eval'`, `*` hoặc `https:` để hết lỗi. Thay vào đó, dùng **violation reporting** để quan sát chính sách đề xuất (*candidate policy*), xử lý các vi phạm hợp lệ, rồi chuyển từng bước sang **enforcement**.

**Mục tiêu bài học:** phân biệt header thực thi và header quan sát; hiểu cấu trúc báo cáo vi phạm qua các cơ chế reporting; xây collector nhận dữ liệu không đáng tin; thiết kế quy trình phân loại, thử nghiệm, canary và rollback; cấu hình và kiểm thử trên Spring Security Servlet lẫn Reactive/WebFlux.

## 2. Enforcement và Report-Only: hai mục đích khác nhau

Trình duyệt có hai cách nhận chính sách CSP thông qua HTTP response header của tài liệu:

~~~http
Content-Security-Policy: script-src 'self'; object-src 'none'; base-uri 'self'
~~~

và:

~~~http
Content-Security-Policy-Report-Only: script-src 'self'; object-src 'none'; base-uri 'self'
~~~

| Đặc điểm | `Content-Security-Policy` | `Content-Security-Policy-Report-Only` |
|---|---|---|
| Mục đích | **Thực thi** giới hạn của policy | **Quan sát** candidate policy |
| Khi một hành vi vi phạm | Browser có thể **chặn** hành vi | Browser không chặn **chỉ vì** policy Report-Only |
| Console/violation event | Có thể xuất hiện | Có thể xuất hiện với disposition tương ứng |
| Gửi report qua endpoint | Có, nếu cấu hình và browser hỗ trợ | Có, nếu cấu hình và browser hỗ trợ |
| Thích hợp cho | Bảo vệ đang áp dụng cho người dùng | Đánh giá ảnh hưởng trước khi siết chính sách |
| Có bảo đảm không làm hỏng giao diện? | Không | Vẫn có thể có lỗi từ cơ chế khác hoặc CSP thực thi khác |

Quan trọng: **Report-Only không “bật bảo vệ ở mức nhẹ”**. Nó không ngăn script hoặc kết nối thuộc candidate policy mà chỉ tạo tín hiệu quan sát trong phạm vi browser hỗ trợ. Nếu ứng dụng hoàn toàn không có CSP thực thi, một script vi phạm candidate policy vẫn có thể chạy.

### Hai header có thể cùng tồn tại

Một cách chuyển đổi thường dùng là giữ policy thực thi đang ổn định và đồng thời thử candidate chặt hơn:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; object-src 'none'
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Policy thứ nhất vẫn thực thi. Policy thứ hai báo các hành vi **sẽ không phù hợp** nếu nó được bật theo mô hình hỗ trợ của browser. Ví dụ một script inline có thể vẫn chạy vì policy thực thi cho `'unsafe-inline'`, đồng thời tạo báo cáo vi phạm đối với candidate `script-src 'self'`.

Ngược lại, nếu đã có một CSP thực thi khác chặn script, việc thêm Report-Only không thể làm script được chạy trở lại. **Từng CSP thực thi cùng áp dụng; Report-Only chỉ quan sát.**

### Report-Only không phải phép thử hoàn hảo cho mọi directive

Một số directive không có hiệu lực hoặc không được đánh giá như một policy thực thi khi đặt trong Report-Only. Ví dụ, `frame-ancestors` là directive cần được kiểm chứng bằng CSP thực thi; không được coi việc không có report trong chế độ quan sát là bằng chứng chống clickjacking đã hoạt động. Các cơ chế hỗ trợ và reporting cũng khác nhau giữa phiên bản trình duyệt.

Vì vậy Report-Only dùng để **thu thập dấu hiệu**, không phải thay toàn bộ thử nghiệm enforcement trong browser.

## 3. Ba chặng trong quá trình nâng cấp CSP

Một lộ trình an toàn nên có ba chặng tách biệt:

~~~mermaid
flowchart TD
    A[Kiểm kê trang, tài nguyên và đường thực thi] --> B[Thiết kế candidate CSP chặt]
    B --> C[Phát Content-Security-Policy-Report-Only]
    C --> D[Nhận và phân loại violation]
    D --> E{Có hành vi hợp lệ bị ảnh hưởng?}
    E -- Có --> F[Sửa frontend hoặc cấp phép đúng nguồn]
    F --> C
    E -- Không hoặc đã xử lý --> G[Thử enforced CSP trên staging]
    G --> H{Luồng nghiệp vụ đạt kiểm thử?}
    H -- Chưa --> F
    H -- Đạt --> I[Canary/rollout theo đợt]
    I --> J[Giám sát lỗi, vi phạm và chức năng]
    J --> K{Có hồi quy nghiêm trọng?}
    K -- Có --> L[Rollback chính sách, điều tra và sửa]
    L --> C
    K -- Không --> M[Mở rộng enforcement và duy trì]
~~~

| Chặng | Kết quả cần có | Điều không nên làm |
|---|---|---|
| **Quan sát** | Bản đồ nguồn hợp lệ, lỗi frontend còn tồn tại, vi phạm được phân loại | Cho rằng không có report nghĩa là an toàn |
| **Xác minh chặn** | Browser thực sự từ chối hành vi không được phép, chức năng hợp lệ vẫn chạy | Chỉ kiểm tra header hoặc chỉ dựa vào Report-Only |
| **Rollout** | Chính sách có phiên bản, được giám sát và có cách quay lui | Mở wildcard/unsafe cho toàn bộ ứng dụng chỉ để tránh một lỗi đơn lẻ |

Mọi số liệu về tỷ lệ vi phạm, ngưỡng rollback hoặc thời gian quan sát phải do đội dự án đặt trên **số liệu thực tế**. Không có một ngưỡng cố định phù hợp cho mọi ứng dụng.

## 4. CSP gửi báo cáo vi phạm bằng cách nào?

Có hai họ cơ chế mà bạn thường gặp trong hệ sinh thái browser:

1. **`report-uri`:** cơ chế CSP lâu đời, yêu cầu browser gửi JSON report đến URL khai báo.
2. **`report-to` cùng Reporting API:** policy tham chiếu một nhóm endpoint; endpoint được khai báo bằng header reporting tương ứng, thường gặp ở các triển khai mới.

Mức hỗ trợ thay đổi theo browser và phiên bản; ứng dụng thực tế cần kiểm thử cả những trình duyệt người dùng đang sử dụng.

### 4.1. report-uri: lựa chọn tương thích phổ biến

Ví dụ candidate CSP:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; report-uri /_csp/legacy-report
~~~

`/_csp/legacy-report` là endpoint cùng origin của ứng dụng. Khi browser hỗ trợ và quyết định gửi report, nó thường dùng:

~~~http
POST /_csp/legacy-report HTTP/1.1
Content-Type: application/csp-report
~~~

Body là JSON chứa đối tượng `csp-report` với các trường mô tả vi phạm. Browser có thể không gửi ngay hoặc không gửi mọi vi phạm; endpoint không nên kỳ vọng một request cho mỗi lần người dùng gặp lỗi.

`report-uri` là cơ chế cũ nhưng vẫn hữu ích cho khả năng tương thích. Đừng đồng nhất nó với `report-to`: kiểu payload và cách chỉ định endpoint có thể khác.

### 4.2. report-to và Reporting-Endpoints

Một ví dụ cấu hình dùng Reporting API:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/_csp/reports"
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'; report-to csp-endpoint
~~~

Ở đây:

- `Reporting-Endpoints` định nghĩa tên endpoint `csp-endpoint` trỏ tới URL thu thập report.
- `report-to csp-endpoint` trong CSP tham chiếu **tên endpoint**, không phải URL trực tiếp.
- Browser hỗ trợ Reporting API sẽ dùng định dạng reporting phù hợp; payload và cách gửi không nhất thiết giống `application/csp-report`.

Trong môi trường có browser khác nhau, có thể khai báo cả hai cơ chế:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/_csp/reports"
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'; report-uri /_csp/legacy-report; report-to csp-endpoint
~~~

Trong trình duyệt hỗ trợ `report-to`, cơ chế mới có thể được ưu tiên và `report-uri` bị bỏ qua đối với policy đó; browser không hỗ trợ có thể dùng `report-uri`. Đừng dựa vào giả định browser sẽ gửi **hai** bản report cho mỗi sự kiện. Cần thử trên browser mục tiêu.

Một số hệ thống còn dùng header `Report-To` kiểu khai báo nhóm trước đây. Cú pháp và hỗ trợ của nó không hoàn toàn đồng nhất với `Reporting-Endpoints`; không tự trộn các ví dụ của hai cơ chế nếu chưa kiểm chứng.

### 4.3. Vì sao nên ưu tiên endpoint cùng origin?

Trong giai đoạn đầu, endpoint báo cáo cùng origin với trang thường giúp giảm cấu hình phụ về đường truyền và chính sách báo cáo cross-origin. Nếu sử dụng collector ở một origin độc lập, cần đánh giá các yêu cầu của Reporting API, quyền riêng tư, TLS, hạn chế cross-origin và chính sách của browser tương ứng.

Điều quan trọng hơn vị trí endpoint là: nó **thực sự nhận được report ở browser mục tiêu**, xử lý dữ liệu không đáng tin và không trở thành nguyên nhân làm hỏng ứng dụng khi collector gặp sự cố.

## 5. Đọc payload báo cáo: report-uri và Reporting API

Hai cơ chế có thể khác tên trường, cấu trúc và content type. Không viết parser chỉ chấp nhận một định dạng mà lại cấu hình cả hai endpoint cùng một đường dẫn không phân biệt.

### 5.1. Ví dụ payload từ report-uri

Đây là **mẫu minh họa** của định dạng thường thấy, không phải cam kết mọi browser luôn gửi đủ tất cả trường:

~~~json
{
  "csp-report": {
    "document-uri": "https://app.example.com/dashboard",
    "violated-directive": "script-src-elem",
    "effective-directive": "script-src-elem",
    "original-policy": "default-src 'none'; script-src 'self'; report-uri /_csp/legacy-report",
    "blocked-uri": "inline",
    "disposition": "report",
    "source-file": "https://app.example.com/dashboard",
    "line-number": 27,
    "column-number": 5,
    "status-code": 200
  }
}
~~~

Ý nghĩa một số trường:

| Trường | Dùng để hiểu gì? | Giới hạn |
|---|---|---|
| `document-uri` | Tài liệu HTML chứa CSP | Có thể bị rút gọn hoặc không có một số thành phần URL |
| `effective-directive` | Directive thực sự quyết định lần kiểm tra | Quan trọng khi có fallback từ `default-src` |
| `violated-directive` | Tên directive trong báo cáo | Có browser dùng giá trị tương đồng hoặc cũ |
| `original-policy` | Chính sách gây ra report | Dài; nên chuẩn hóa thành version policy để tổng hợp |
| `blocked-uri` | Nguồn/hành vi bị từ chối, ví dụ `inline` hoặc host | Browser có thể rút gọn URL ngoài origin vì quyền riêng tư |
| `disposition` | `report` (Report-Only) hoặc `enforce` (thực thi) | Dùng để phân biệt tín hiệu quan sát và chặn thật |
| `source-file`, `line-number`, `column-number` | Vị trí liên quan đến vi phạm | Không phải report nào cũng có hoặc đủ chính xác |
| `status-code` | HTTP status có liên quan trong báo cáo | Có thể bằng 0/không được cung cấp trong vài tình huống |

Ví dụ trên cho thấy một script inline bị candidate policy đánh dấu. Vì `disposition: "report"`, nó không chứng minh script đã bị chặn: cần xem có CSP thực thi khác hoặc lỗi JavaScript hay không.

### 5.2. Ví dụ báo cáo dạng Reporting API

Một số browser dùng Reporting API có thể gửi mảng report với `type` và `body` dạng camelCase:

~~~json
[
  {
    "type": "csp-violation",
    "url": "https://app.example.com/dashboard",
    "user_agent": "Browser report metadata",
    "body": {
      "documentURL": "https://app.example.com/dashboard",
      "effectiveDirective": "connect-src",
      "blockedURL": "https://unknown.example",
      "originalPolicy": "default-src 'none'; connect-src 'self'; report-to csp-endpoint",
      "disposition": "report",
      "statusCode": 200
    }
  }
]
~~~

Đây cũng chỉ là **ví dụ cấu trúc**: những trường cụ thể, cách viết tên và dữ liệu được gửi có thể phụ thuộc browser/phiên bản. Dữ liệu `url`, `blockedURL` hoặc source có thể bị giới hạn để không tiết lộ chi tiết cross-origin.

Một endpoint phục vụ Reporting API thường cần chấp nhận `Content-Type: application/reports+json`. Endpoint cho `report-uri` kiểu cũ thường cần `application/csp-report`. Khi thiết kế collector, nên **lưu nhận diện định dạng**, sau đó chuẩn hóa về một mô hình nội bộ thay vì giả định hai payload có cùng khóa.

### 5.3. report-sample có thể chứa một phần mã

Nếu thêm từ khóa `'report-sample'` vào directive tương ứng, browser hỗ trợ có thể đưa **mẫu ngắn của đoạn inline bị từ chối** vào report:

~~~http
Content-Security-Policy-Report-Only: script-src 'self' 'report-sample'; style-src 'self' 'report-sample'; report-uri /_csp/legacy-report
~~~

Điều này giúp biết đoạn script/style nào bị ảnh hưởng, nhưng có rủi ro **thu thập dữ liệu nhạy cảm hoặc code nội bộ**. Chỉ bật khi đã đánh giá nhu cầu, chính sách lưu dữ liệu và giới hạn quyền truy cập log. Không nên thu toàn bộ request/DOM hoặc gửi nguyên thông tin người dùng chỉ để “debug CSP”.

## 6. Không nhận được báo cáo không có nghĩa policy đúng

Violation reporting có tính chất quan sát, **không phải cơ chế ghi log tuyệt đối**:

- Browser có thể không hỗ trợ một directive, kiểu báo cáo hoặc endpoint reporting.
- Report có thể được gửi bất đồng bộ, bị gộp, bị giới hạn số lượng hoặc bị mất khi tab đóng, browser offline hay endpoint lỗi.
- Cài đặt riêng tư, extension, proxy và hạn chế mạng có thể ảnh hưởng việc gửi.
- Một chức năng chưa được người dùng mở trong giai đoạn quan sát sẽ không tạo tín hiệu.
- Chưa có report không đảm bảo policy không chặn hoặc không làm hỏng một luồng hiếm gặp.
- Header CSP trên API JSON không tự bảo vệ tài liệu HTML do CDN/origin khác trả.
- Report-Only có giới hạn đối với một số directive, đặc biệt các cơ chế liên quan navigation/embedding.

Vì vậy phải kết hợp **CSP reports + Network/Console + kiểm thử trình duyệt + chỉ số chức năng + log server**. Một báo cáo tự nó cũng chưa đủ chứng minh có tấn công: font mới, CDN đổi hostname hoặc extension cũng có thể làm phát sinh vi phạm.

### Quan sát trong chính trình duyệt

Trong ứng dụng hoặc trang demo do đội phát triển kiểm soát:

1. Mở DevTools → Network; chọn response **document HTML** và xem các header CSP thực nhận.
2. Phân biệt `Content-Security-Policy` với `Content-Security-Policy-Report-Only`.
3. Mở Console/Issues để xem thông báo vi phạm, directive hiệu lực và nguồn liên quan.
4. Trong Network, lọc request tới `/_csp/legacy-report` hoặc `/_csp/reports` nếu browser đã quyết định gửi report.
5. Kiểm tra request collector trong server log/metrics để chắc chắn nó nhận được loại payload mong đợi.
6. Thực hiện cùng phép thử trên các browser mục tiêu và qua hệ thống proxy/CDN thực tế.

Không dùng duy nhất việc chạy JavaScript trực tiếp trong **DevTools Console** để kết luận CSP của tài liệu, vì code do người dùng nhập vào Console có thể chịu xử lý khác mã được parser hoặc script ứng dụng thực thi.

## 7. Thiết kế endpoint nhận báo cáo an toàn

Một collector CSP thường là HTTP endpoint mà browser có thể gửi report **không kèm phiên đăng nhập hoặc CSRF token của ứng dụng**. Điều đó có nghĩa endpoint có thể nhận dữ liệu từ client không đáng tin và thậm chí bị gửi payload giả.

Những yêu cầu tối thiểu:

1. **Chỉ chấp nhận phương thức và content type cần thiết:** thường POST với `application/csp-report` hoặc `application/reports+json` tại hai route có trách nhiệm rõ ràng.
2. **Giới hạn kích thước body:** đặt giới hạn ở proxy/gateway và application, tránh bị gửi report lớn gây tiêu tốn bộ nhớ.
3. **Rate limit và kiểm soát tải:** bảo vệ endpoint khỏi flood, không thực hiện phép xử lý nặng trên request path.
4. **Không tin nội dung report:** mọi URL, directive, user-agent, line number hoặc `original-policy` đều là dữ liệu do client gửi; không coi đó là bằng chứng tuyệt đối.
5. **Không log nguyên payload theo mặc định:** chuẩn hóa và giảm nhạy cảm các trường, tránh ghi token, query string, inline sample hay mã nguồn vào log chung.
6. **Trả response ngắn:** ví dụ HTTP 204; không yêu cầu browser chờ xử lý phân tích dài.
7. **Không đặt collector ngoài khả năng chịu lỗi của app:** sự cố hệ thống báo cáo không được làm gián đoạn người dùng truy cập trang chính.
8. **Chính sách lưu giữ và truy cập:** hạn chế quyền xem, thời gian lưu, mục đích phân tích; báo cáo có thể chứa metadata về hành vi duyệt web.

### CSRF và authorization cho reporting endpoint

Browser gửi CSP report không phải HTML form hợp lệ có CSRF token của ứng dụng. Nếu endpoint đi qua Spring Security với CSRF protection, POST có thể nhận 403 trước khi controller được gọi. Cần thiết kế **ngoại lệ CSRF đúng route báo cáo**, không tắt CSRF cho toàn bộ ứng dụng chỉ để nhận report.

Tương tự, nếu collector buộc đăng nhập, browser có thể không gửi hoặc không truy cập được trong các trường hợp cần báo cáo. Có thể cho phép POST vào endpoint báo cáo không cần authentication, nhưng phải kết hợp giới hạn kích thước, rate limit, validation và không tin payload. Một report **không** phải yêu cầu thay đổi dữ liệu nghiệp vụ của người dùng.

Không nên đưa các giá trị nhận được từ report vào cấu hình CSP để tự động mở nguồn: kẻ xấu có thể cố tình tạo report dẫn tới mở allowlist.

## 8. Ví dụ collector Servlet/Spring MVC

Đây là controller tối giản minh họa đường đi của hai loại payload. Nó chỉ trả HTTP 204, không ghi log raw payload:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CspReportController {

    @PostMapping(
        path = "/_csp/legacy-report",
        consumes = "application/csp-report"
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void receiveLegacy(@RequestBody String reportJson) {
        // Minh họa: xác thực kích thước, phân tích JSON theo schema,
        // bỏ dữ liệu nhạy cảm, rồi đưa sự kiện đã chuẩn hóa vào pipeline.
        // Không tin URL hoặc nội dung từ reportJson.
    }

    @PostMapping(
        path = "/_csp/reports",
        consumes = "application/reports+json"
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void receiveReportingApi(@RequestBody String reportsJson) {
        // Reporting API có thể gửi danh sách report dạng JSON.
        // Không ghi log nguyên reportsJson, không tự động cấp phép nguồn.
    }
}
~~~

**Đây không phải collector production hoàn chỉnh.** Việc dùng `@RequestBody String` yêu cầu hệ thống áp đặt giới hạn body **trước khi** nạp toàn bộ payload vào bộ nhớ. Ứng dụng thật cần validation schema, quy trình chuẩn hóa, rate limit và telemetry nội bộ. Nếu muốn nhận nhiều MIME variation, cần cập nhật mapping sau khi có bằng chứng từ browser mục tiêu; không mở `*/*` theo thói quen.

### Cấu hình Spring Security chỉ cho phép route collector

Ví dụ Servlet minh họa một phần cấu hình cho ứng dụng cần collector công khai:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// Đưa vào cấu hình HttpSecurity của chain áp dụng cho các route này.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        HttpMethod.POST,
        "/_csp/legacy-report",
        "/_csp/reports"
    ).permitAll()
    .anyRequest().authenticated()
);

http.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        new AntPathRequestMatcher("/_csp/legacy-report", "POST"),
        new AntPathRequestMatcher("/_csp/reports", "POST")
    )
);
~~~

Ở đây chỉ hai route POST thu báo cáo được miễn CSRF. **Mọi form hay API thay đổi trạng thái khác vẫn cần bảo vệ CSRF đúng thiết kế.** Cấu hình authorization ví dụ phải được hợp nhất với quy tắc security chain, static resources và login thực tế của dự án; không sao chép `anyRequest().authenticated()` nếu nó làm hỏng luồng công khai hợp lệ. API matcher có thể khác theo phiên bản Spring Security, cần kiểm tra đúng version dự án khi đưa vào build.

## 9. Ví dụ collector Reactive/WebFlux

Với WebFlux, controller có thể nhận report bất đồng bộ qua `Mono`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCspReportController {

    @PostMapping(
        path = "/_csp/legacy-report",
        consumes = "application/csp-report"
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> receiveLegacy(@RequestBody Mono<String> body) {
        return body.then(); // Minh họa nhận và bỏ payload.
    }

    @PostMapping(
        path = "/_csp/reports",
        consumes = "application/reports+json"
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> receiveModern(@RequestBody Mono<String> body) {
        return body.then(); // Pipeline thật phải parse/validate/rate-limit.
    }
}
~~~

Với reactive stack, cũng phải giới hạn kích thước body ở lớp HTTP/message codec hoặc gateway phù hợp; `Mono<String>` không tự bảo vệ khỏi payload lớn. Collector thực tế có thể chuyển **sự kiện đã làm sạch** vào hàng đợi hoặc hệ thống xử lý sau request, nhưng không được lưu vô hạn hoặc thực hiện tác vụ block trong event loop.

Việc miễn CSRF chỉ cho **đúng reporting endpoint** phải được cấu hình trong `ServerHttpSecurity` theo request matcher thích hợp. Đừng chuyển nguyên `HttpServletRequest` hoặc Servlet filter sang WebFlux; hai stack dùng API khác nhau. Nếu frontend và API ở các origin riêng, xác định server nào thực sự phục vụ HTML và nơi nhận report.

## 10. Cấu hình Report-Only trong Spring Security Servlet

Spring Security có DSL cho CSP. Trong ứng dụng Servlet, ví dụ dưới đây dùng candidate policy với `report-uri`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletCspReportOnlyConfig {

    private static final String CANDIDATE_POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "img-src 'self' https://images.example.net; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.example.net; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'; " +
        "report-uri /_csp/legacy-report";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CANDIDATE_POLICY)
                .reportOnly()
            )
        );
        return http.build();
    }
}
~~~

`reportOnly()` yêu cầu cấu hình CSP xuất header `Content-Security-Policy-Report-Only` thay vì enforced CSP của **cấu hình này**. Cấu hình đó không có nghĩa mọi CSP khác trong ứng dụng bị tắt. Nếu reverse proxy hoặc security chain khác vẫn trả `Content-Security-Policy`, browser tiếp tục chặn theo policy thực thi đó.

Với `report-to`, ứng dụng phải bổ sung header khai báo reporting endpoint tương ứng (ví dụ `Reporting-Endpoints`) ở tầng phục vụ HTML; phương thức `policyDirectives(...)` chỉ đưa chuỗi policy vào CSP, không tự tạo hệ thống collector hay endpoint.

### Chuyển sang enforcement

Sau khi candidate policy đạt các bước xác minh:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(ENFORCED_POLICY)
        // Không gọi reportOnly() để xuất CSP thực thi.
    )
);
~~~

`ENFORCED_POLICY` đại diện cho chuỗi directive đã được kiểm thử và review. Có thể giữ `report-uri`/`report-to` trong **CSP thực thi** để tiếp tục thu violation có `disposition` tương ứng. Không tự động loại bỏ endpoint báo cáo khi chuyển sang enforcement nếu hệ thống vẫn cần giám sát.

Trong một số triển khai, đội phát triển muốn giữ **enforced baseline** và **Report-Only candidate** cùng lúc. Cần cấu hình hai header một cách có chủ đích bằng thành phần header phù hợp (Spring, filter hoặc proxy), kiểm thử response thực tế và tránh writer ghi đè hoặc tạo policy trùng không mong muốn. Không gọi lặp cấu hình CSP DSL với giả định sẽ tự tạo hai header độc lập.

## 11. Cấu hình Report-Only trong Spring Security Reactive/WebFlux

WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveCspReportOnlyConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String candidatePolicy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self' https://images.example.net; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.net; " +
            "object-src 'none'; " +
            "base-uri 'none'; " +
            "form-action 'self'; " +
            "report-uri /_csp/legacy-report";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(candidatePolicy)
                .reportOnly()
            )
        );
        return http.build();
    }
}
~~~

Ý nghĩa của Report-Only do browser quyết định, **không đổi giữa Servlet và WebFlux**. Khác biệt chỉ là API cấu hình server và đường phục vụ HTML.

Khi muốn enforcement ở WebFlux, bỏ `reportOnly()` trong cấu hình tương ứng sau khi xác minh policy. Lưu ý tên và khả năng của DSL có thể khác giữa các phiên bản Spring Security; cần đối chiếu dependency đang dùng khi chạy kiểm thử thực tế.

### Frontend tách khỏi backend

Nếu Spring WebFlux chỉ trả JSON hoặc SSE tại `https://api.example.net` nhưng HTML được CDN trả từ `https://app.example.com`, việc gắn Report-Only trên response JSON **không quan sát CSP của tài liệu HTML**. Để thu vi phạm của frontend, header Report-Only phải xuất cùng **response HTML** từ hệ thống phục vụ frontend, còn endpoint collector có thể nằm ở backend được thiết kế riêng.

## 12. Phân loại vi phạm: lỗi hợp lệ hay tín hiệu bất thường?

Để tránh phản ứng sai, mỗi report nên được phân loại theo **hành vi + trang + policy version + browser + môi trường**:

| Dấu hiệu vi phạm | Nguyên nhân có thể hợp lệ | Hướng xử lý |
|---|---|---|
| `script-src-elem` chặn inline script | Template cần script bootstrap | Chuyển ra file hoặc cấp nonce/hash đúng cách |
| `script-src-attr` chặn `onclick`/`onerror` | Legacy inline handler | Chuyển sang `addEventListener` |
| `style-src-elem` chặn style block | CSS-in-JS hoặc template inline CSS | Chuyển CSS ra file hoặc tích hợp nonce/hash |
| `style-src-attr` chặn style attribute | UI dùng `style="..."` | Dùng CSS class hoặc giải pháp tương thích |
| `img-src` chặn CDN ảnh | Host ảnh chưa được kiểm kê | Xác minh nguồn, chỉ mở đúng CDN |
| `font-src` chặn webfont | Tệp font nằm ở host khác stylesheet | Sửa `font-src`; kiểm tra CORS font riêng |
| `connect-src` chặn API | API/WebSocket/SSE ngoài allowlist | Xác minh protocol, port, host, nhu cầu nghiệp vụ |
| `form-action` chặn submit | Form SSO/payment khác origin | Cho đúng đích đã được phê duyệt; kiểm tra server |
| `base-uri` chặn thẻ `<base>` | Frontend dùng base tag để định tuyến | Kiểm tra URL; ưu tiên bỏ base nếu không cần |
| `script-src` chặn `eval` | Development build hoặc thư viện cũ | Dùng production build, loại bỏ nhu cầu eval |
| Nhiều URL lạ từ extension | Extension hoặc nội dung bị chèn | Không tự cho phép; phân tích theo browser/ngữ cảnh |

### Những câu hỏi trước khi thêm một nguồn

1. URL hoặc code bị chặn **thuộc tính năng nào**?
2. Ai sở hữu và vận hành nguồn đó? Có người dùng upload hoặc tenant không?
3. Vi phạm xuất hiện ở những route, phiên bản, trình duyệt nào?
4. Có thể **sửa frontend** thay vì thêm `'unsafe-inline'`, `'unsafe-eval'`, `*` hoặc `https:` không?
5. Nguồn được thêm sẽ mở thêm những hành vi nào ngoài tính năng đang lỗi?
6. Liệu CSP là nguyên nhân chính hay còn CORS, authentication, CSRF, 404/500, cookie, WSS hoặc proxy?

Một report đơn lẻ không tự chứng minh host bên ngoài cần được đưa vào CSP. Việc tự động thêm source expression từ `blocked-uri` là đặc biệt nguy hiểm: báo cáo do client gửi có thể bị giả mạo để thúc đẩy mở allowlist.

## 13. Chuẩn hóa và tổng hợp dữ liệu vi phạm

Không nên tạo hàng triệu log riêng rẽ rồi đọc thủ công. Một pipeline reporting đơn giản:

~~~mermaid
flowchart LR
    A[Browser CSP violation] --> B[POST report-uri hoặc Reporting API]
    B --> C[Collector giới hạn kích thước và rate]
    C --> D[Parse, validate, giảm dữ liệu nhạy cảm]
    D --> E[Chuẩn hóa directive, policy version, document route]
    E --> F[Gom nhóm và thống kê]
    F --> G[Dashboard và cảnh báo vận hành]
    G --> H[Review: sửa mã hay cập nhật policy]
~~~

Các trường có thể dùng để **nhóm**:

- **Policy version:** ví dụ theo release hoặc hash policy để so sánh trước/sau deploy.
- **Disposition:** `report` hoặc `enforce`.
- **Directive hiệu lực:** `script-src-elem`, `connect-src`, `img-src`...
- **Route mẫu:** `/dashboard`, `/checkout`; bỏ query string nếu có dữ liệu nhạy cảm.
- **Origin tài nguyên bị chặn:** khi có thể suy ra an toàn; không giả định toàn URL luôn được trả.
- **Browser / môi trường:** nếu được phép thu thập và có độ tin cậy phù hợp.
- **Thời điểm và bản build:** giúp liên hệ với deploy/feature flag.

### Vì sao cần loại bỏ dữ liệu nhạy cảm?

Một report có thể đưa theo URL tài liệu, URL tài nguyên, chính sách đầy đủ hoặc một đoạn code inline khi bật `'report-sample'`. Những thông tin này có khả năng chứa token trong query string, địa chỉ định danh, tham số tìm kiếm hoặc code nội bộ.

Do đó:

- Không lưu nguyên URL nếu không cần; giữ origin và path đã xử lý.
- Loại token/query/fragment có nguy cơ nhạy cảm; hạn chế số ký tự của trường.
- Không xem `source-file` hoặc `blocked-uri` là URL đáng tin để server tự gọi đến (tránh SSRF).
- Không đưa raw CSP report ra trang HTML hoặc log viewer mà không escape.
- Chỉ cấp quyền đọc dashboard báo cáo cho người có trách nhiệm.

### Không đồng nhất “số report” với “số người dùng bị ảnh hưởng”

Một trang có nhiều vi phạm cùng loại trong một lần tải; một browser có thể gộp hoặc bỏ bớt report; người dùng chưa truy cập feature sẽ không tạo dữ liệu. Vì vậy **số lượng report thô không phải tỷ lệ lỗi chức năng**.

Đội phát triển nên ghép dữ liệu report với test E2E, frontend error rate, dữ liệu chức năng và những tín hiệu vận hành khác. Nếu có chỉ số “tỷ lệ trang tải với CSP violation”, cần xác định mẫu số và độ phủ browser trước khi dùng để quyết định rollout.

## 14. Thiết kế chính sách theo giai đoạn

Giả sử ứng dụng ban đầu có:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' https:; connect-src 'self' https:
~~~

Đội phát triển muốn giảm nguy cơ nhưng chưa thể sửa hết frontend trong một lần phát hành. Có thể tách các thay đổi:

| Giai đoạn | Thay đổi chính | Kiểm chứng |
|---|---|---|
| 0. Baseline | Ghi nhận CSP hiện tại, chức năng, nguồn tải | Browser + asset/network inventory |
| 1. Candidate | Report-Only với source list hẹp và không có unsafe | Violation theo từng directive, route và browser |
| 2. Refactor | Chuyển inline handler/script, loại eval, đóng CDN không dùng | Unit/integration/E2E tests |
| 3. Staging enforcement | Bật candidate làm CSP thực thi trên môi trường test | Kiểm tra hành vi bị chặn và chức năng hợp lệ |
| 4. Canary | Bật enforced CSP cho tập nhỏ response/nhóm người dùng có kiểm soát | Lỗi JS/UI/API, conversion/checkout, báo cáo CSP |
| 5. Mở rộng | Tăng phạm vi rồi chuẩn hóa thành baseline mới | Không phát sinh hồi quy chưa xử lý |
| 6. Duy trì | Version policy, review nguồn và reporting | QA sau thay đổi frontend/CDN |

Đối với policy chứa nonce, phải tạo nonce **mới cho từng response HTML**, đồng bộ CSP header với thẻ script/style tin cậy. Đối với hash, cần tính digest đúng nội dung inline cuối cùng và cập nhật khi build thay đổi. Không duy trì mã inline không an toàn bằng cách giữ `'unsafe-inline'` vô thời hạn mà không có quyết định rủi ro rõ ràng.

### Canary theo response hoặc nhóm tuyến tính năng

Có thể bật enforced CSP trước trên một route ít phức tạp hoặc một tập người dùng thử nghiệm, sau đó mở rộng. Nếu triển khai phân nhánh response, cần đảm bảo:

- Đúng HTML response nhận đúng policy; không gắn candidate enforcement nhầm lên API JSON.
- Reverse proxy/CDN không trộn policy giữa những bản cache có nội dung khác nhau.
- Nếu có nonce động, header và HTML của từng response phải khớp.
- Có cơ chế quay lui **được kiểm thử trước** và có owner chịu trách nhiệm.
- Không làm phương án rollback vô tình tắt các security header khác như HSTS.

Một cấu hình được “bật 1%” nhưng bị cache ở CDN rồi phát cho người dùng khác có thể tạo phạm vi ngoài dự định. Hãy xác định nơi quyết định policy và cách cache hoạt động trước khi thử canary.

## 15. Chất lượng rollout: khi nào có thể bật chặn?

Không có công thức chỉ dựa vào “0 report”. Một policy có thể được xem là đủ điều kiện thử enforcement khi:

1. **Phạm vi đã rõ:** biết các route HTML chính, các trình duyệt hỗ trợ và nguồn asset/API thực sự cần thiết.
2. **Các vi phạm hợp lệ trọng yếu đã xử lý:** đăng nhập, điều hướng, form/checkout, upload, in ấn, dashboard real-time, thư viện UI không bị hỏng trong thử nghiệm.
3. **Source list được review:** nguồn mới có chủ sở hữu và lý do; tránh wildcard/unsafe không cần thiết.
4. **Cơ chế reporting hoạt động đủ để quan sát:** collector nhận được report demo trên browser mục tiêu, có dashboard/nhóm chịu trách nhiệm.
5. **Kiểm thử enforced trên staging đạt yêu cầu:** có phép thử cho script/ảnh/API bị chặn có chủ đích và phép thử nghiệp vụ hợp lệ.
6. **Có rollback:** biết thay đổi/feature flag/config nào đưa policy về baseline ổn định mà không làm hỏng các header bảo vệ khác.

Trong canary, phải theo dõi thêm tình trạng JavaScript, UX, tỷ lệ thành công của tác vụ nghiệp vụ, sự cố CSRF/CORS, WebSocket reconnect và HTTP 4xx/5xx. Một tăng đột biến của report có thể do chính sách chặt hoạt động đúng trước nguồn không đáng tin, hoặc do chức năng hợp lệ vừa bị chặn — cần phân loại, không tự động rollback tất cả.

## 16. Kiểm thử server: Servlet với MockMvc

Test phía server giúp xác minh Spring Security trả **đúng tên header**. Giả sử ứng dụng có route HTML `/dashboard` và MockMvc sử dụng Spring Security filters:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy-Report-Only",
        containsString("script-src 'self'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy-Report-Only",
        containsString("report-uri /_csp/legacy-report")
    ));
~~~

Khi chuyển sang enforcement, test kỳ vọng header:

~~~java
mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ));
~~~

### Kiểm thử collector legacy

Nếu đã cấu hình `CspReportController` và ngoại lệ CSRF chính xác cho endpoint:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

String reportJson =
    "{\"csp-report\":{\"document-uri\":\"https://app.example.com/dashboard\"," +
    "\"effective-directive\":\"script-src-elem\",\"blocked-uri\":\"inline\"}}";

mockMvc.perform(post("/_csp/legacy-report")
    .contentType("application/csp-report")
    .content(reportJson))
    .andExpect(status().isNoContent());
~~~

Test 204 này chỉ chứng minh request đã đến endpoint. Muốn xác minh hệ thống reporting thật, cần thêm test parse/schema, giới hạn kích thước, rate limit, dữ liệu nhạy cảm và việc sự kiện được đưa vào pipeline xử lý theo thiết kế. Không dùng test thành công để kết luận browser chắc chắn gửi report.

## 17. Kiểm thử server: Reactive với WebTestClient

Với ứng dụng WebFlux, test response HTML:

~~~java
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy-Report-Only",
        ".*script-src 'self'.*"
    );
~~~

Test endpoint nhận report, giả định có route và security configuration phù hợp:

~~~java
webTestClient.post()
    .uri("/_csp/legacy-report")
    .header("Content-Type", "application/csp-report")
    .bodyValue("""
        {"csp-report":{"effective-directive":"connect-src",
                       "blocked-uri":"https://unknown.example"}}
        """)
    .exchange()
    .expectStatus().isNoContent();
~~~

Ví dụ `"""` yêu cầu phiên bản Java hỗ trợ text block; nếu dự án dùng Java cũ hơn, thay bằng chuỗi JSON bình thường. Trong test browser thật, hãy xác nhận `Content-Security-Policy-Report-Only` trên **response HTML**, không chỉ response báo cáo 204 hoặc API JSON.

## 18. Kiểm thử browser: so sánh báo cáo với hành vi chặn thật

Một demo tối thiểu có thể dùng HTML:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>CSP rollout demo</title></head>
<body>
  <p>Đánh giá chính sách CSP</p>

  <!-- Script inline để quan sát vi phạm; nội dung vô hại -->
  <script>console.log("CSP inline test");</script>

  <img src="https://untrusted.example/demo.png" alt="Ảnh thử nghiệm">
  <button id="reload" type="button">Tải thử API</button>

  <!-- File JS cùng origin tự đăng ký click handler -->
  <script src="/js/csp-demo.js" defer></script>
</body>
</html>
~~~

Trong `/js/csp-demo.js`:

~~~javascript
document.getElementById("reload").addEventListener("click", async () => {
  try {
    await fetch("https://untrusted.example/demo-api");
  } catch (error) {
    console.warn("Request failed or blocked:", error);
  }
});
~~~

Thử candidate:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; report-uri /_csp/legacy-report
~~~

**Kỳ vọng:** browser hỗ trợ có thể hiển thị vi phạm cho script inline, ảnh ngoài allowlist và fetch ngoài allowlist; nhưng những hành vi đó **không bị chặn chỉ bởi Report-Only**. Ảnh hoặc fetch vẫn có thể thất bại vì mạng, DNS, CORS hoặc nguyên nhân khác, nên không sử dụng việc chúng “thành công/thất bại” đơn lẻ để đo hiệu lực Report-Only.

Sau đó thử enforcement:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; report-uri /_csp/legacy-report
~~~

Ở chế độ này, browser sẽ chặn những hành vi thuộc phạm vi policy mà không được cấp phép. Script `/js/csp-demo.js` vẫn có thể chạy do `script-src 'self'`; script inline không có nonce/hash sẽ bị từ chối. Quan sát DevTools để phân biệt `disposition: "enforce"` với `disposition: "report"` nếu có report.

### Ma trận xác minh

| Ca kiểm thử | Report-Only | Enforcement |
|---|---|---|
| Script inline không nonce/hash | Có thể tạo vi phạm; không bị policy này chặn | Bị chặn nếu policy không cho inline |
| JS file cùng origin | Không vi phạm ở `script-src 'self'` | Được phép theo CSP |
| Ảnh từ host ngoài `img-src` | Có thể báo vi phạm; không bị policy này chặn | Bị chặn bởi CSP |
| `fetch` tới host ngoài `connect-src` | Có thể báo vi phạm; không bị policy này chặn | Bị chặn bởi CSP |
| Collector trả 404/403 | Report có thể không được lưu | Chính sách vẫn có thể chặn; reporting bị lỗi |
| Route HTML có CSP thực thi khác | Policy thực thi khác có thể chặn | Phải thỏa tất cả CSP thực thi |

**Đừng kiểm tra bằng một URL bên ngoài không tồn tại rồi suy đoán kết quả**: kết nối thất bại vì DNS không chứng minh CSP đã chặn. Trong môi trường học tập, nên sử dụng các origin thử nghiệm có kiểm soát và quan sát thông báo chính sách trong browser.

## 19. Chẩn đoán lỗi: không có report, report sai, policy chặn không như mong đợi

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không có report nào | Browser không hỗ trợ, endpoint sai, chưa tạo violation, mạng/extension hoặc rate limit | Kiểm tra header HTML, Console, Network, browser mục tiêu |
| Console có violation nhưng collector không nhận | `report-uri`/`report-to` sai, endpoint 403/404, cấu hình Reporting-Endpoints thiếu | Thử payload mẫu, kiểm tra collector và request |
| POST report nhận 403 trong Spring | CSRF protection hoặc authorization chặn endpoint | Chỉ miễn CSRF và permit đúng route POST collector |
| Collector trả 415 | Content type mapping không khớp | Phân biệt `application/csp-report` và `application/reports+json` |
| Collector bị ngập dữ liệu | Nhiều violation, flood hoặc thiếu giới hạn | Size limit, rate limit, sampling/dedup và queue phù hợp |
| Có report nhưng nội dung không giống ví dụ | Khác browser, mechanism hoặc trường bị rút gọn | Parse mềm dẻo nhưng validate schema, dùng effective directive |
| Script đang chạy nhưng Report-Only báo vi phạm | Report-Only không thực thi | Kiểm tra CSP enforcement riêng |
| Script vẫn bị chặn dù đã bỏ CSP thực thi trong code | Proxy/CDN hoặc chain khác vẫn phát CSP | Kiểm tra tất cả response headers |
| Nhiều report cùng một vi phạm | Nhiều policy, nhiều lần tạo sự kiện, browser gửi lặp | Gom nhóm theo policy, directive, route |
| Sau rollout mới có báo cáo `enforce` | Enforced CSP giờ chặn những trường hợp thực | Phân loại và so với chỉ số chức năng |
| Host API đã nằm trong candidate nhưng `fetch` thất bại | CORS/auth/mạng; không chỉ CSP | Kiểm tra Network, preflight, status và logs |
| WebSocket không chạy dù `connect-src` cho phép | WSS/proxy/Origin/auth server | Kiểm tra handshake và log backend |
| Browser không báo `frame-ancestors` trong Report-Only | Directive có giới hạn trong Report-Only | Thử enforced policy trên môi trường kiểm soát |
| CSP của HTML không thay đổi sau deploy | HTML được CDN/cache trả với header cũ | Kiểm tra response cuối cùng và cơ chế cache |
| Nonce khớp ở server nhưng lệch HTML | Filter/template/cache phát giá trị khác nhau | Đồng bộ nonce từng response; không dùng cache sai |

### Một ví dụ có nhiều CSP thực thi

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://static.example.net
Content-Security-Policy: default-src 'self'; script-src 'self'
~~~

Script từ `https://static.example.net` có thể bị policy thứ hai chặn, dù policy thứ nhất đã cho phép. Browser không chọn “header mới nhất” để ghi đè toàn bộ policy cũ; **tất cả CSP thực thi đều có hiệu lực**. Nếu có thêm Report-Only, những tín hiệu từ nó cần được phân biệt qua disposition/policy version.

## 20. Một tình huống rollout hoàn chỉnh

**Bối cảnh:** hệ thống đặt hàng Spring MVC có dashboard, trang checkout, SSO dạng POST form, thư viện CSS, ảnh CDN và API cross-origin. Đội phát triển muốn loại `'unsafe-inline'` khỏi script policy và thu hẹp allowlist.

### Giai đoạn A — Kiểm kê và đo hiện trạng

Nhóm thu thập danh sách:

| Chức năng | Nguồn/hành vi đang sử dụng | Directive cần đánh giá |
|---|---|---|
| Dashboard bootstrap | Inline script cố định | `script-src` + nonce/hash hoặc file ngoài |
| Nút thao tác | `onclick` nội tuyến | `script-src-attr`; nên refactor |
| CSS UI | Stylesheet CDN | `style-src` |
| Font | CDN font khác host stylesheet | `font-src` và CORS font |
| Ảnh sản phẩm | Ảnh CDN | `img-src` |
| Gọi API | HTTPS API | `connect-src` và CORS |
| Form checkout | Form POST cùng origin | `form-action 'self'` |
| SSO redirect/form POST | IdP origin khác | Kiểm tra luồng thực; có thể cần `form-action` |

### Giai đoạn B — Candidate Report-Only

Nhóm thử policy không có `'unsafe-inline'`:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self' https://styles.example.net; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self' https://idp.example.net; report-uri /_csp/legacy-report
~~~

Sau khi quan sát, nhóm **không** thêm `'unsafe-inline'` chỉ vì dashboard báo vi phạm. Họ chuyển inline handler vào JavaScript dùng `addEventListener`; script bootstrap cố định được đưa ra file hoặc cấp hash hợp lệ. Họ xác minh `https://idp.example.net` thật sự là đích của form SSO, không mở `form-action https:`.

### Giai đoạn C — Enforced trên staging

Nhóm bật policy đã sửa thành `Content-Security-Policy` trên staging, thử:

1. Đăng nhập/đăng xuất, SSO, dashboard và checkout.
2. CSS, font, ảnh, responsive image và trình soạn thảo.
3. API, WebSocket hoặc SSE nếu có, kiểm tra thêm CORS và Origin validation.
4. Script inline không được cấp phép: browser phải từ chối.
5. Trang lỗi, redirect và route được phục vụ bởi chain/proxy khác.

Khi có vấn đề, nhóm xem **directive hiệu lực** trong Console, phân tích nguyên nhân, sửa code hoặc allowlist đã được review rồi thử lại. Không tắt CSP/CSRF/CORS toàn hệ thống chỉ để cho một luồng chạy.

### Giai đoạn D — Canary, theo dõi và rollback

Nhóm phát enforcement đến một tập route hoặc nhóm người dùng được chọn, có cơ chế tránh CDN cache trộn policy. Trong thời gian canary, họ theo dõi:

- Violation `enforce` theo directive và route.
- JavaScript errors và các chức năng không hoàn thành.
- Tỷ lệ thành công của đăng nhập, thanh toán và thao tác quan trọng.
- Tình trạng collector, tỷ lệ báo cáo bị lỗi, các vấn đề response 4xx/5xx.
- Những report mới sau deploy CDN/script/font.

Nếu gặp hồi quy nghiêm trọng, nhóm quay lại policy phiên bản trước đã biết hoạt động, tiếp tục giữ các bảo vệ khác, rồi sửa nguyên nhân. Rollback không đồng nghĩa loại bỏ toàn bộ CSP; mục tiêu là quay về **baseline an toàn nhất còn tương thích**, sau đó tiến hành chặt lại.

## 21. Bài thực hành

**Yêu cầu:** triển khai giám sát CSP và một lần chuyển thử từ quan sát sang chặn trên ứng dụng Spring Security do bạn kiểm soát.

1. Tạo route HTML `/csp-lab` có một script inline nhỏ, một tệp script cùng origin và một ảnh từ host thử nghiệm ngoài allowlist.
2. Cấu hình Spring Security Servlet phát `Content-Security-Policy-Report-Only` với `script-src 'self'` và `img-src 'self'`; thêm `report-uri /_csp/legacy-report`.
3. Tạo endpoint POST nhận `application/csp-report`, trả HTTP 204. Chỉ miễn CSRF cho route báo cáo, không tắt CSRF cho toàn ứng dụng. Đặt giới hạn kích thước/rate ở cấu hình test thích hợp.
4. Trong DevTools, thử tạo violation và xác nhận Console/Network; kiểm tra collector có nhận report demo hay không.
5. Đọc `effective-directive`, `blocked-uri` và `disposition` trong report, so sánh với hành vi quan sát được trên trang.
6. Thử Reporting API với `Reporting-Endpoints` và `report-to` trên browser hỗ trợ; so sánh content type, hình dạng payload và độ phủ với `report-uri`.
7. Sửa script inline bằng cách chuyển sang file ngoài hoặc dùng hash/nonce đúng cách. Không thêm `'unsafe-inline'` chỉ để loại bỏ report.
8. Chuyển candidate thành CSP thực thi trên môi trường test; xác minh phần tử không được cho phép bị browser chặn còn chức năng hợp lệ vẫn hoạt động.
9. Tạo test MockMvc/WebTestClient kiểm tra header ở hai giai đoạn và response 204 của collector.
10. Lập kế hoạch canary: scope, chỉ số nghiệp vụ, ai review report, điều kiện rollback, cách tránh cache sai và phiên bản policy cần phục hồi.

### Câu hỏi tự đánh giá

1. `Content-Security-Policy-Report-Only` có chặn script bị vi phạm không? Điều gì xảy ra nếu cùng response có một CSP thực thi khác?
2. Vì sao không thể xem việc không nhận được CSP report là bằng chứng trang đã an toàn?
3. Khác biệt giữa `report-uri` và `report-to` là gì? Vì sao đôi khi cần hỗ trợ cả hai?
4. Endpoint nào thường nhận `application/csp-report`, endpoint nào nhận `application/reports+json`?
5. `disposition: "report"` và `disposition: "enforce"` giúp phân biệt điều gì?
6. Vì sao một CSP collector không nên yêu cầu CSRF token như form nghiệp vụ thông thường? Làm sao giới hạn ngoại lệ đúng phạm vi?
7. Vì sao phải loại bỏ dữ liệu nhạy cảm trước khi lưu report, đặc biệt khi bật `'report-sample'`?
8. Nếu một report có `blocked-uri` trỏ đến domain lạ, có nên tự thêm domain đó vào allowlist không?
9. Vì sao một chính sách Report-Only đạt yêu cầu vẫn phải được kiểm thử enforcement trên browser?
10. Khi Spring Boot chỉ phục vụ JSON còn CDN trả HTML, header Report-Only nên xuất ở đâu?
11. Một response có hai CSP thực thi, một cho phép CDN và một chặn CDN. Browser xử lý thế nào?
12. Khi nào nhóm nên rollback, và vì sao rollback nên giữ lại baseline bảo vệ ổn định thay vì xóa toàn bộ security headers?

## 22. Ghi nhớ

**Lộ trình CSP hiệu quả không dừng ở việc thêm một header.** Trước tiên cần kiểm kê nguồn và chức năng, dùng `Content-Security-Policy-Report-Only` để quan sát candidate, thu và phân loại báo cáo vi phạm, sửa frontend hoặc mở nguồn có chủ đích, rồi kiểm thử `Content-Security-Policy` thực thi trước khi canary/rollout. `report-uri` và `report-to`/Reporting API có độ phủ và payload khác nhau; collector phải coi mọi report là dữ liệu không đáng tin, giới hạn tài nguyên, bảo vệ quyền riêng tư và không tạo lỗ hổng mới.

Với Spring Security **Servlet** hoặc **Reactive/WebFlux**, phải đặt CSP trên **response HTML mà browser thực sự render**, xác minh đúng tên header và đường đi đến collector. Report-Only không thay thế kiểm thử chặn thật; số report thô không phản ánh đầy đủ mức ảnh hưởng. CSP cần được vận hành cùng escape/sanitize, CORS, CSRF, HSTS, HTTP firewall, authentication/authorization và bảo vệ session của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`.
