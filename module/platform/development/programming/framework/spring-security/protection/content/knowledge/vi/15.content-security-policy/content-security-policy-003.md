# Content-Security-Policy và chế độ Report-Only

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cả Servlet lẫn Reactive, kiểm thử tình huống tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Hai chế độ của CSP giải quyết hai giai đoạn khác nhau

**Content Security Policy (CSP)** là tập các quy tắc mà server công bố để trình duyệt hạn chế nguồn tài nguyên và một số hành vi của tài liệu web. Ví dụ, chính sách có thể cấm JavaScript nội tuyến, chỉ cho phép script cùng origin, giới hạn endpoint gọi API hoặc ngăn trang bị nhúng trong iframe.

Một ứng dụng vừa muốn **ngăn hành vi nguy hiểm ngay** vừa muốn **quan sát ảnh hưởng của chính sách mới trước khi triển khai**. Hai HTTP response header phục vụ các mục tiêu đó:

| Header | Vai trò | Nếu script vi phạm chính sách này |
|---|---|---|
| `Content-Security-Policy` | **Enforcement** — chính sách thực thi | Trình duyệt chặn thực thi/tải theo directive vi phạm và có thể phát sinh thông báo, báo cáo |
| `Content-Security-Policy-Report-Only` | **Report-Only** — chính sách thử nghiệm, quan sát | Trình duyệt ghi nhận vi phạm, nhưng **không chặn chỉ vì policy Report-Only đó** |

Ví dụ hai response **riêng biệt**:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Giá trị directive trông giống nhau, nhưng tên header quyết định hậu quả: **chặn** hoặc **chỉ quan sát**. Chính sách Report-Only rất hữu ích cho việc thử nghiệm trên hệ thống thực tế mà chưa làm gián đoạn giao diện. Tuy nhiên, nó không phải hàng rào bảo vệ thay cho policy thực thi.

Sau bài học, bạn có thể:

1. Giải thích chính xác sự khác nhau giữa enforcement và Report-Only khi chỉ có một hoặc đồng thời có cả hai chính sách.
2. Xây dựng chuỗi directive phù hợp với tài nguyên của một ứng dụng Spring Security.
3. Cấu hình và kiểm tra hai chế độ trên Servlet và Reactive/WebFlux.
4. Thu thập, đọc và đánh giá báo cáo vi phạm với hiểu biết về giới hạn và quyền riêng tư.
5. Lập quy trình chuyển từ quan sát sang chặn, tránh làm hỏng frontend hoặc vô tình nới rộng chính sách.

## 2. Trình duyệt áp dụng từng loại header ra sao?

Giả sử trang có đoạn HTML không đáng tin cậy:

~~~html
<img src="/missing-image" onerror="alert('XSS demo')">
~~~

Nếu trình duyệt coi đoạn này là HTML và xử lý thuộc tính `onerror`, nó có thể cố chạy JavaScript nội tuyến. Với `script-src 'self'` không kèm cơ chế cho phép inline thích hợp:

- **Chỉ có `Content-Security-Policy`:** handler nội tuyến thường bị chặn; Console có thông báo vi phạm.
- **Chỉ có `Content-Security-Policy-Report-Only`:** handler không bị chặn bởi policy đó, dù trình duyệt có thể báo vi phạm. Các lớp bảo vệ khác hoặc một policy thực thi khác vẫn có thể ngăn nó chạy.
- **Có cả hai:** trình duyệt đánh giá **mỗi policy**. Policy thực thi quyết định hành vi có bị chặn không; policy Report-Only cung cấp thêm tín hiệu về chính sách đang thử nghiệm.

~~~mermaid
flowchart TD
    A[Trang nhận HTTP response] --> B[Trình duyệt đọc các header CSP]
    B --> C[Trang yêu cầu tải hoặc thực thi nội dung]
    C --> D[Đánh giá mọi chính sách thực thi]
    C --> E[Đánh giá chính sách Report-Only]
    D --> F{Có vi phạm CSP thực thi?}
    F -- Có --> G[Chặn hành vi theo CSP]
    F -- Không --> H[Tiếp tục xử lý thông thường]
    E --> I[Nếu vi phạm: ghi nhận / gửi report khi hỗ trợ và đã cấu hình]
    G --> I
~~~

Report-Only **không cho phép bỏ qua** policy đang thực thi. Nếu response có:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' https://cdn.example.net; object-src 'none'
~~~

thì một script ở `https://cdn.example.net` **vẫn bị chặn** bởi policy thực thi, mặc dù policy Report-Only xem nguồn đó là hợp lệ. Không thể dùng Report-Only để “mở lại” tài nguyên bị policy thực thi từ chối.

### Một response có thể chứa nhiều chính sách

Nếu server, Spring Security và reverse proxy cùng trả nhiều header `Content-Security-Policy`, trình duyệt áp dụng **tất cả chính sách thực thi**; một chính sách không nới lỏng chính sách khác. Đây là nguyên nhân phổ biến khiến frontend bị chặn dù một header đang đọc có vẻ đã cho phép nguồn.

Tương tự, có thể có nhiều policy Report-Only để quan sát. Khi phân tích vi phạm, phải xác định thông báo thuộc policy nào. Không nên cố giải quyết sự cố bằng cách đoán rằng policy xuất hiện cuối sẽ ghi đè policy xuất hiện trước.

## 3. Viết directive cho chính sách thực thi và thử nghiệm

Giá trị của hai header đều dùng cú pháp CSP: các directive ngăn cách bởi dấu `;`, mỗi directive định nghĩa một nhóm nguồn hoặc hành vi.

| Directive | Giới hạn gì? | Lưu ý khi triển khai |
|---|---|---|
| `default-src` | Nguồn dự phòng cho các fetch directive có cơ chế fallback | Không bao phủ mọi directive |
| `script-src` | Nguồn và cách thực thi JavaScript | `'self'` không tự cho phép inline script hoặc handler |
| `style-src` | Nguồn CSS và cách dùng style nội tuyến | CSS-in-JS hoặc inline style có thể bị chặn |
| `img-src` / `font-src` | Nguồn ảnh/font | Xem xét CDN, font ngoài và data URL theo nhu cầu |
| `connect-src` | Kết nối từ script, ví dụ `fetch`, XHR và WebSocket | Cần kiểm tra đúng API origin hoặc `wss://...` |
| `object-src` | Nội dung `object`/`embed` | Thường ưu tiên `'none'` |
| `base-uri` | Giá trị của thẻ `<base>` | Khai báo riêng, không kế thừa `default-src` |
| `form-action` | Đích gửi form | Khai báo riêng, kiểm tra luồng thanh toán/SSO |
| `frame-ancestors` | Những trang được phép nhúng **trang hiện tại** | Khác với `frame-src`; không kế thừa `default-src` |
| `report-to` / `report-uri` | Nơi gửi báo cáo vi phạm | Không phải chỉ thị cấp quyền tải tài nguyên |

Ví dụ chính sách thực thi cho ứng dụng chỉ dùng tài nguyên cùng origin, gọi API cùng origin và không cho trang khác nhúng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Chính sách này **không tự cho phép** inline JavaScript, `onerror`, `onclick` hoặc một script từ CDN ngoài. Nhưng script ở chính origin được cho phép vẫn có thể nguy hiểm nếu ứng dụng phân phối tệp không đáng tin. CSP luôn cần đi cùng mã hóa đầu ra đúng ngữ cảnh, tránh DOM API không an toàn và quản lý nguồn script.

### Những sai sót có ảnh hưởng lớn

- Thêm `'unsafe-inline'` vào `script-src` có thể làm mất rào chắn với nhiều dạng nội dung script bị chèn. Đừng dùng nó làm cách sửa nhanh giao diện.
- Dùng `script-src *` hoặc nguồn quá rộng khiến một số script độc hại dễ thỏa chính sách hơn.
- Quên `form-action`, `base-uri` hoặc `frame-ancestors` vì tưởng `default-src` đã bao phủ.
- Đặt CSP trên response JSON từ backend API nhưng **không** đặt trên response HTML do frontend server/CDN trả. Chính sách tài liệu phải được trình duyệt nhận cùng tài liệu đó.
- Dùng thẻ `<meta http-equiv="Content-Security-Policy">` thay cho header HTTP khi cần Report-Only. **Report-Only chỉ được cung cấp qua HTTP header**; cách đặt bằng meta không hỗ trợ chế độ này. Meta cũng có các giới hạn khác, ví dụ không hỗ trợ `frame-ancestors`.

## 4. Dùng Report-Only trước khi bật chặn

Một trang SPA đang dùng script từ `https://static.example.net`. Đội phát triển muốn dần chuyển mọi script về `'self'`. Bật ngay `script-src 'self'` ở chế độ thực thi có thể làm ứng dụng ngừng hoạt động.

Thay vào đó, duy trì chính sách thực thi đang dùng và thử chính sách mới:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://static.example.net; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /_csp/report
~~~

Khi trang nạp script từ `https://static.example.net`:

1. Chính sách **thực thi** cho phép nguồn đó về mặt CSP; trình duyệt có thể tiếp tục tải script.
2. Chính sách **Report-Only** phát hiện nguồn không phù hợp với `script-src 'self'` và tạo vi phạm.
3. Nhóm phát triển kiểm tra có thể chuyển script đó sang cùng origin hay cần một ngoại lệ thực sự.
4. Khi đã xử lý các vi phạm hợp lệ, nhóm thay chính sách thực thi bằng bản nghiêm ngặt hơn.

Điểm quan trọng: **vi phạm trong Report-Only không luôn là một cuộc tấn công**. Vi phạm có thể do script do đội phát triển viết, thư viện bên thứ ba, CSS nội tuyến, công cụ giám sát, extension trình duyệt hoặc cấu hình CDN sai.

### Hai chế độ trong cùng một đợt triển khai

Một cách có kiểm soát là dùng:

- **Enforced baseline:** chính sách mà ứng dụng đã xác nhận hoạt động ổn định và đang chặn.
- **Report-Only candidate:** chính sách chặt hơn, cần đo lường trước khi thay thế baseline.

Không dùng chính sách Report-Only làm căn cứ kết luận rằng website hiện đã được bảo vệ khỏi mọi payload vi phạm nó. Chỉ chính sách thực thi mới tạo hiệu lực chặn.

## 5. Cấu hình enforcement và Report-Only với Spring Security Servlet

Spring Security cho Servlet cung cấp cấu hình CSP bằng `HttpSecurity.headers(...).contentSecurityPolicy(...)`. Hai ví dụ sau là **hai lựa chọn cho cùng một security chain**, không đặt cả hai nối tiếp lên một DSL như thể lựa chọn sau sẽ tự tạo thêm một header độc lập.

### 5.1. Chỉ bật CSP thực thi

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "style-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self'; " +
                    "frame-ancestors 'none'"
                )
            )
        );
        return http.build();
    }
}
~~~

Response của tài liệu được chain xử lý có header `Content-Security-Policy`.

### 5.2. Chỉ bật CSP Report-Only

Với cùng cấu trúc nhưng đang thử nghiệm chính sách, thêm `reportOnly()`:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; " +
                "script-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "report-uri /_csp/report"
            )
            .reportOnly()
        )
    );
    return http.build();
}
~~~

Ví dụ này thuộc cấu hình **Report-Only**: một vi phạm `script-src` sẽ được ghi nhận, nhưng chính header vừa cấu hình sẽ không làm trình duyệt chặn script. Muốn endpoint `/_csp/report` nhận báo cáo, ứng dụng phải triển khai handler và chính sách server phù hợp; Spring Security không tự tạo collector.

### 5.3. Cùng lúc trả hai header để thử chính sách mới

Khi cần enforcement baseline và Report-Only candidate đồng thời, có thể đăng ký hai `ContentSecurityPolicyHeaderWriter` với chế độ khác nhau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        ContentSecurityPolicyHeaderWriter enforced =
            new ContentSecurityPolicyHeaderWriter(
                "default-src 'self'; " +
                "script-src 'self' https://static.example.net; " +
                "object-src 'none'; base-uri 'self'"
            );

        ContentSecurityPolicyHeaderWriter candidate =
            new ContentSecurityPolicyHeaderWriter(
                "default-src 'self'; " +
                "script-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "report-uri /_csp/report"
            );
        candidate.setReportOnly(true);

        http.headers(headers -> headers
            .addHeaderWriter(enforced)
            .addHeaderWriter(candidate)
        );
        return http.build();
    }
}
~~~

Kết quả kỳ vọng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://static.example.net; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /_csp/report
~~~

Đây là ví dụ **một nguồn cấu hình chủ động tạo hai header với hai mục đích**. Nếu ứng dụng còn có CSP mặc định từ một lớp khác hoặc proxy, phải xem toàn bộ response thực tế vì chính sách bổ sung có thể siết chặt hành vi ngoài dự tính.

### Khi có nhiều SecurityFilterChain

Một ứng dụng Servlet có thể phân chain theo URL. Chỉ các response đi qua chain có cấu hình CSP tương ứng mới nhận header từ chain đó. Cần xác nhận trang đăng nhập, trang dashboard, trang lỗi và các route HTML có nằm trong phạm vi mong muốn. Nếu HTML do máy chủ frontend khác trả, hãy cấu hình ở máy chủ đó thay vì chỉ đặt CSP trên API của Spring.

## 6. Cấu hình tương ứng với Reactive/WebFlux

Trong Spring Security Reactive, sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`. Ví dụ policy thực thi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self'"
                )
            )
        );
        return http.build();
    }
}
~~~

Để chạy **Report-Only**, cấu hình policy tương ứng với tùy chọn `reportOnly()` của API CSP trên Reactive:

~~~java
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; script-src 'self'; " +
                "object-src 'none'; report-uri /_csp/report"
            )
            .reportOnly()
        )
    );
    return http.build();
}
~~~

Ví dụ tương ứng dùng trên **một ứng dụng WebFlux riêng**, với các `import` và `@Configuration` như cấu hình đầu tiên. Không dùng `ContentSecurityPolicyHeaderWriter` của Servlet làm writer trực tiếp trong reactive chain: đó là API làm việc với Servlet request/response.

Trong cả hai stack, Spring Security chỉ phát header; **trình duyệt** mới đánh giá nội dung, nguồn script và quyết định chặn hoặc báo cáo. Endpoint API cho phép CORS cũng không tự thiết lập CSP cho trang HTML được phát từ origin frontend khác.

## 7. Báo cáo vi phạm đến đâu? Console, report-uri và Reporting API

Một lỗi thường gặp khi thử Report-Only là kỳ vọng chỉ cần bật header thì backend sẽ tự có danh sách các vi phạm. Thực tế có **hai kênh quan sát**:

1. **DevTools:** trình duyệt thường ghi thông báo vi phạm vào Console/Issues. Cách hiển thị có thể khác nhau theo trình duyệt và phiên bản.
2. **Báo cáo gửi qua HTTP:** trình duyệt chỉ gửi về nơi được khai báo thông qua cơ chế reporting được hỗ trợ; ứng dụng cần có endpoint thu thập, xử lý và bảo vệ dữ liệu.

### 7.1. Cách cũ: report-uri

Ví dụ:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri /_csp/report
~~~

Với cơ chế `report-uri`, trình duyệt hỗ trợ có thể POST báo cáo vi phạm đến `/_csp/report`. Dạng dữ liệu legacy thường là JSON với content type `application/csp-report`, ví dụ rút gọn:

~~~http
POST /_csp/report HTTP/1.1
Content-Type: application/csp-report

{
  "csp-report": {
    "document-uri": "https://app.example.com/dashboard",
    "effective-directive": "script-src-elem",
    "blocked-uri": "https://unexpected.example.net/widget.js",
    "disposition": "report",
    "original-policy": "default-src 'self'; script-src 'self'; object-src 'none'; report-uri /_csp/report"
  }
}
~~~

Mẫu trên minh họa định dạng. Trường thực tế, URL bị lược bỏ và mức chi tiết có thể khác theo trình duyệt và ngữ cảnh quyền riêng tư. Một report cũng không tự chứng minh trang đã bị tấn công: nó có thể xuất phát từ tính năng hợp lệ.

### 7.2. Cách mới: Reporting API và report-to

Cơ chế Reporting API hiện đại có thể dùng header `Reporting-Endpoints` khai báo tên endpoint và directive `report-to` tham chiếu tới tên đó:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/_csp/reports"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-to csp-endpoint
~~~

Trong các trình duyệt hỗ trợ, CSP report có thể được gửi theo định dạng Reporting API (chẳng hạn `application/reports+json`, một mảng report), với các trường được tổ chức khác dạng `report-uri`. Hãy triển khai collector đọc theo **content type và schema thực nhận**; không giả định mọi browser cùng gửi một dạng payload.

Do mức hỗ trợ Reporting API, `Reporting-Endpoints` và `report-to` khác nhau giữa các trình duyệt, một chính sách có thể ghi cả `report-to` lẫn `report-uri` để tương thích:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/_csp/reports"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-to csp-endpoint; report-uri /_csp/report
~~~

Các trình duyệt hỗ trợ `report-to` có thể ưu tiên cơ chế đó và bỏ qua `report-uri`, còn trình duyệt khác có thể chỉ dùng `report-uri`. **Không nên dựa vào một cơ chế reporting chưa được kiểm thử trên những trình duyệt mà sản phẩm hỗ trợ.**

### 7.3. Thiết kế endpoint nhận báo cáo

Nếu dùng Spring MVC hoặc WebFlux để thu thập CSP report, endpoint là một HTTP POST do bạn triển khai. Nó không được tạo ra chỉ bằng việc bật CSP header. Các điểm cần xử lý:

- Chấp nhận content type phù hợp với những cơ chế/report mà sản phẩm hỗ trợ; các schema legacy và Reporting API khác nhau.
- Giới hạn kích thước request, tốc độ gửi, phương thức và thời gian lưu để tránh quá tải hoặc lạm dụng.
- Xem body report là **dữ liệu không đáng tin**: validate, parse, không render lại dưới dạng HTML, không tin mọi URL hoặc trường do client gửi.
- Tránh log nguyên vẹn URL, query string, sample script hoặc thông tin trang chứa dữ liệu nhạy cảm; phân quyền truy cập kho báo cáo và áp dụng chính sách lưu giữ.
- Một số report sẽ thiếu trường, được rút gọn hoặc không bao giờ được gửi. Dữ liệu báo cáo hữu ích cho việc phát hiện vấn đề, nhưng không phải bản ghi đầy đủ của mọi lần vi phạm.
- Kiểm tra chính sách CSRF đối với endpoint nhận POST từ browser: nếu cần ngoại lệ vì report không mang CSRF token, hãy giới hạn ngoại lệ ở **đúng endpoint**, tuyệt đối không tắt CSRF toàn ứng dụng chỉ vì collector.

Một collector tốt thường chuẩn hóa các trường cần phân tích như: thời gian, phiên bản frontend, trang, effective directive, nguồn bị chặn, disposition, user agent đã được giảm định danh và số lượng báo cáo. Phân loại và thống kê theo phiên bản triển khai hữu ích hơn việc lưu vô hạn toàn bộ JSON.

### Report-Only có cần endpoint mới hoạt động?

**Không cần collector để thử nghiệm thủ công qua DevTools**, nhưng cần endpoint được cấu hình và browser hỗ trợ nếu mục tiêu là nhận báo cáo tập trung qua HTTP. Một cấu hình chỉ có `Content-Security-Policy-Report-Only` mà không có `report-uri`/`report-to` không tạo ra hệ thống thu thập tự động cho server.

## 8. Từ cảnh báo đến quyết định thực thi

Giả sử đội frontend muốn loại bỏ mọi JavaScript nội tuyến nhưng đang có một số widget cũ. Chính sách thử nghiệm:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /_csp/report
~~~

Quy trình triển khai có thể chia làm các bước:

| Bước | Thực hiện | Tiêu chí xem xét |
|---|---|---|
| 1. Kiểm kê | Liệt kê HTML origin, script, CSS, CDN, API, WebSocket, frame và các trang lỗi/đăng nhập | Có tài liệu về những nguồn đang sử dụng |
| 2. Quan sát | Bật Report-Only trên response HTML thật; thu thập Console/report theo trình duyệt mục tiêu | Nhận diện được các vi phạm do tính năng hợp lệ |
| 3. Phân loại | Gắn vi phạm với frontend phiên bản nào, directive nào, tài nguyên nào | Phân biệt false positive, extension, lỗi cấu hình và dấu hiệu tấn công |
| 4. Khắc phục | Đưa script ra file, bỏ inline handler, cấu hình nonce/hash đúng cách hoặc cho phép chính xác host cần thiết | Tính năng hoạt động với candidate CSP |
| 5. Thực thi từng phần | Đưa candidate vào `Content-Security-Policy` trên phạm vi kiểm soát được | Kiểm thử trình duyệt, luồng chính và lỗi thực tế đều đạt |
| 6. Theo dõi | Xem vi phạm, tình trạng giao diện và thông báo người dùng sau triển khai | Điều chỉnh có kiểm soát; không mở wildcard tùy tiện |

Không cần **mọi báo cáo** phải biến mất mới được triển khai: các extension, crawler hoặc hành vi không đáng tin có thể tiếp tục sinh ra vi phạm, và việc chặn các vi phạm đó chính là một mục tiêu của CSP. Cần xác nhận không có **vi phạm hợp lệ gây hỏng chức năng** và những cảnh báo còn lại được giải thích.

### Quan hệ giữa nonce/hash và Report-Only

Khi ứng dụng có inline script hợp lệ, có thể tạo policy thử nghiệm dùng nonce/hash:

~~~http
Content-Security-Policy-Report-Only: script-src 'self' 'nonce-EXAMPLE_PER_RESPONSE'; object-src 'none'; base-uri 'none'; report-uri /_csp/report
~~~

Nonce phải được tạo mới và không thể đoán trước **cho mỗi response HTML**, rồi được gắn đồng nhất vào CSP header và những thẻ script đáng tin cậy của response đó. Ví dụ `EXAMPLE_PER_RESPONSE` chỉ minh họa cú pháp, không phải giá trị dùng trong sản xuất. Cấu hình một nonce cố định có thể làm suy yếu phòng vệ.

Với script nội tuyến ổn định, có thể dùng hash của nội dung script theo cú pháp CSP. Khi nội dung script thay đổi, hash phải cập nhật. Không thêm `'unsafe-inline'` vào `script-src` chỉ để bỏ các cảnh báo; nó có thể cho phép cả đoạn script bị chèn mà chính sách định chặn.

## 9. Kiểm thử ở server và ở trình duyệt

Một kiểm thử đầy đủ phân biệt ba câu hỏi:

1. Server đã gửi **đúng tên header** và **đúng chuỗi directive** chưa?
2. Browser có **chặn** hay chỉ **báo cáo** khi một hành vi thực sự vi phạm không?
3. Hệ thống báo cáo có **nhận được dữ liệu hợp lệ** từ những trình duyệt được hỗ trợ không?

### 9.1. Unit/integration test cho Servlet

Nếu cấu hình Servlet trả cả enforced và candidate Report-Only như mục 5.3, có thể xác nhận response HTML bằng MockMvc:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

// Trong một lớp test đã có MockMvc với Spring Security filters
mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self' https://static.example.net")
    ))
    .andExpect(header().string(
        "Content-Security-Policy-Report-Only",
        containsString("script-src 'self'")
    ));
~~~

Route `/dashboard` trong ví dụ phải tồn tại trong ứng dụng thử nghiệm. Test kiểm tra header chứ không chứng minh trình duyệt đã chặn XSS.

### 9.2. Header của WebFlux

Nếu đang cấu hình **Report-Only** trên WebFlux:

~~~java
// Trong một lớp test đã cấu hình WebTestClient và route "/dashboard"
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy-Report-Only",
        ".*script-src 'self'.*"
    );
~~~

Với chế độ thực thi, thay header cần kiểm thành `Content-Security-Policy`. Nếu endpoint trả redirect hoặc trang HTML đến từ CDN/front end khác, hãy kiểm tra response cuối cùng mà trình duyệt render.

### 9.3. Thử sự khác biệt trong browser

Trong một môi trường học tập do bạn kiểm soát:

1. Tạo trang thử nghiệm có file script hợp lệ cùng origin và một khu vực nhập HTML minh họa lỗi injection.
2. Phục vụ trang với CSP **Report-Only** có `script-src 'self'`. Tạo một handler như `<img src="missing" onerror="alert('demo')">` trong điểm chèn thử nghiệm; ghi nhận vi phạm ở Console và xem hành vi có diễn ra không.
3. Đổi sang CSP **thực thi** cùng chuỗi directive, tải lại trang và thử cùng hành vi. Handler nội tuyến thông thường phải bị chặn do CSP thực thi.
4. Thử tải script từ origin ngoài danh sách; xem network request, Console và lý do browser báo.
5. Bật endpoint nhận report; thử các trình duyệt mục tiêu, đối chiếu kiểu payload, directive và disposition.
6. Lặp lại trên trang đăng nhập, trang dashboard, trang lỗi và sau reverse proxy/CDN nếu triển khai thực tế có các lớp đó.

Chú ý rằng hành vi chạy mã trong **DevTools Console** có thể khác việc trình duyệt phân tích script trong trang. Để kiểm chứng CSP, dùng tình huống HTML/DOM được tạo đúng cách trong môi trường test, không kết luận chỉ từ một lệnh chạy thủ công ở Console.

### Bảng đối chiếu kỳ vọng

Với `script-src 'self'` và không có cấp phép inline:

| Thử nghiệm | Chỉ CSP thực thi | Chỉ Report-Only |
|---|---|---|
| Script từ origin khác không được khai báo | Bị chặn bởi CSP | Có thể tải/chạy; báo vi phạm nếu browser hỗ trợ |
| Handler nội tuyến do HTML injection | Bị chặn bởi CSP | Không bị chặn bởi chính policy này; báo vi phạm |
| File `/js/app.js` cùng origin | Được phép về mặt CSP | Được phép về mặt CSP |
| Có báo cáo trong DevTools | Thường có khi vi phạm | Thường có khi vi phạm |
| Server tự nhận báo cáo mà chưa có endpoint | Không | Không |

“Được phép” chỉ có nghĩa **không bị chính policy CSP này từ chối**; các chính sách thực thi khác, cơ chế trình duyệt và lỗi mạng vẫn có thể ngăn tài nguyên.

## 10. Chẩn đoán xung đột triển khai

| Triệu chứng | Cách xác định nguyên nhân | Hướng xử lý |
|---|---|---|
| Bật CSP rồi giao diện mất chức năng | Console báo `Refused to execute inline script` hoặc script từ host ngoài | Sửa script/handler, cân nhắc nonce/hash hoặc nguồn cụ thể |
| Report-Only báo vi phạm nhưng tính năng vẫn chạy | Kiểm tra tên header, `disposition` và các policy thực thi khác | Đây là mục đích của Report-Only; phân tích trước khi bật chặn |
| Script bị chặn dù Report-Only cho phép | Response còn CSP thực thi nghiêm ngặt hơn | Đọc **tất cả** header CSP từ browser; tìm policy đang chặn |
| DevTools có vi phạm, server không nhận report | Không khai báo endpoint, sai đường dẫn, trình duyệt không hỗ trợ reporting hoặc endpoint từ chối POST | Kiểm tra `report-uri`/`report-to`, Network, status HTTP và collector |
| Collector nhận 403 | Endpoint POST bị CSRF/security chain chặn hoặc không đủ quyền | Sửa riêng security của endpoint nhận báo cáo, không tắt CSRF toàn ứng dụng |
| Staging hoạt động nhưng production lỗi | Origin, port, CDN hoặc proxy khác giữa môi trường | Kiểm kê nguồn thực tế theo môi trường, kiểm tra header cuối cùng |
| CORS báo lỗi khi frontend gọi API | CSP `connect-src` hoặc CORS ở API có thể chặn ở những bước khác nhau | Xác định lỗi thuộc bước CSP hay CORS; sửa đúng cơ chế |
| Browser A gửi report, browser B không | Mức hỗ trợ Reporting API/`report-to`/`report-uri` khác nhau | Thử browser matrix và fallback phù hợp |
| Báo cáo quá nhiều hoặc có URL nhạy cảm | Extension, crawler, lặp lỗi hợp lệ hoặc payload không được kiểm soát | Phân loại, tổng hợp, giới hạn lưu lượng và giảm dữ liệu |

**Không đồng nhất CSP với các lớp bảo vệ khác.** CSP kiểm soát hành vi tài nguyên trong tài liệu web; CORS quy định việc JavaScript đọc response cross-origin; CSRF protection bảo vệ các thao tác trạng thái trước yêu cầu giả mạo; HSTS yêu cầu trình duyệt dùng HTTPS cho host. Session, cookie và HTTP firewall cũng xử lý những bề mặt khác. Các lớp này phối hợp, nhưng không thay thế được nhau.

## 11. Bài thực hành tổng hợp

Một ứng dụng dashboard dùng:

- Script nội bộ: `https://app.example.com/js/app.js`.
- Một script cũ từ CDN: `https://static.example.net/widget.js`.
- API: `https://api.example.com`.
- WebSocket: `wss://events.example.com`.

Mục tiêu là chuyển script CDN về cùng origin mà không làm hỏng bản đang dùng.

**Yêu cầu thực hành:**

1. Thiết lập CSP thực thi cho script cùng origin và CDN hiện tại, đồng thời khai báo `connect-src` phù hợp API/WebSocket.
2. Thiết lập thêm policy Report-Only chỉ cho phép script cùng origin và cấu hình endpoint nhận report. Kiểm tra cả hai header có mặt trên response HTML.
3. Thử widget CDN, ghi lại vi phạm Report-Only và xác nhận tính năng vẫn hoạt động khi policy thực thi cho phép CDN.
4. Chuyển widget sang file do ứng dụng phục vụ. Kiểm tra lại Console, Network và báo cáo; chứng minh tài nguyên hợp lệ không còn vi phạm candidate.
5. Chuyển candidate thành CSP thực thi. Thử một script từ origin ngoài và một handler nội tuyến trong môi trường test để kiểm chứng chặn.
6. Kiểm tra `fetch` tới API: nếu CSP cho phép mà browser vẫn báo CORS, tìm cấu hình API thay vì nới `script-src`.
7. Nếu ứng dụng có Servlet và WebFlux riêng, lập bảng response HTML được phục vụ ở đâu và thành phần nào có trách nhiệm gắn CSP.

**Câu hỏi tự đánh giá:**

1. Tại sao một script có thể tải thành công dù browser báo vi phạm `Content-Security-Policy-Report-Only`?
2. Nếu response cùng lúc có CSP thực thi và Report-Only, policy nào có quyền chặn hành vi?
3. Vì sao thêm `report-uri` không đồng nghĩa server đã có endpoint nhận report?
4. Sự khác nhau giữa báo cáo legacy `report-uri` và Reporting API `report-to` là gì?
5. Vì sao số lượng báo cáo CSP không thể xem là số lượng cuộc tấn công thực tế?
6. Khi nào nên chuyển candidate từ Report-Only sang thực thi? Có cần tất cả cảnh báo biến mất không?
7. Vì sao CSP trên response API không thay thế được CSP trên tài liệu HTML được phục vụ từ CDN?

## 12. Ghi nhớ

`Content-Security-Policy` là **chính sách thực thi**: khi trình duyệt phát hiện một hành vi vi phạm directive có hiệu lực, nó có thể **chặn** hành vi đó. `Content-Security-Policy-Report-Only` dùng để **thử và quan sát** các vi phạm của một chính sách mà chưa chặn hành vi chỉ vì policy thử nghiệm. Hai chính sách có thể cùng xuất hiện trên một response để duy trì bảo vệ hiện có và đánh giá quy tắc mới.

Với Spring Security, cấu hình đúng header ở **nơi phát trang HTML**, dùng DSL Servlet/WebFlux tương ứng, thiết kế reporting endpoint nếu cần thu thập tập trung, phân biệt báo cáo hợp lệ với tín hiệu tấn công và kiểm chứng trên trình duyệt thực tế. CSP là một lớp phòng vệ bổ sung trong mô-đun bảo vệ HTTP; chất lượng của nó phụ thuộc vào việc ứng dụng lựa chọn directive, kiểm thử và quản lý thay đổi có chủ đích.
