# Content-Security-Policy

## 1. CSP là hợp đồng thực thi của trình duyệt đối với tài liệu

Content Security Policy, thường viết tắt là CSP, cho phép server công bố những giới hạn mà trình duyệt áp dụng khi một tài liệu tải tài nguyên hoặc thực hiện một số hành vi. Một policy có thể giới hạn script, stylesheet, kết nối từ trang, nguồn ảnh, nơi submit form và những trang được phép nhúng tài liệu.

Trong module yêu cầu bảo mật, mục tiêu không phải chỉ có một header tên `Content-Security-Policy`. Cần xác định hành vi nào được phép, hành vi nào phải bị chặn, các trang nào nằm trong phạm vi và bằng chứng nào xác nhận trình duyệt đã thực thi policy mong muốn.

Giả sử trang quản lý khóa học hiển thị tên do giảng viên nhập. Nếu một lỗi output encoding khiến dữ liệu trở thành markup, CSP được thiết kế tốt có thể chặn một số đường thực thi script ngoài dự kiến. Nhưng CSP không sửa lỗi encoding, không thay authorization và không chứng minh mọi thao tác trong trang đều an toàn.

OWASP coi CSP là một lớp bảo vệ bổ sung; ứng dụng vẫn cần các thực hành phòng XSS như encoding theo ngữ cảnh và sanitization khi cho phép nội dung HTML. [OWASP: Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html).

Bài học sử dụng tình huống một trang HTML quản lý khóa học, có JavaScript và CSS do ứng dụng cung cấp, không có iframe, video hoặc worker trong trang đó. Những route có nhu cầu khác phải có policy tương ứng; không sao chép nguyên policy ví dụ cho toàn bộ nền tảng rồi bỏ qua chức năng thực tế.

## 2. Bắt đầu từ rủi ro và inventory tài nguyên

Trước khi chọn directive, cần ghi lại tài nguyên và hành vi của trang:

| Thành phần | Nguồn và nhu cầu của tình huống | Câu hỏi bảo mật |
| --- | --- | --- |
| JavaScript khởi tạo | Một bundle do ứng dụng kiểm soát | Script nào được server chủ động cấp quyền chạy? |
| CSS và font | Tài nguyên cùng origin | Có cần style inline hoặc font bên thứ ba không? |
| Ảnh khóa học | Tài nguyên cùng origin trong ví dụ | Có upload hoặc proxy ảnh làm thay đổi ranh giới tin cậy không? |
| API từ trang | Cùng origin | Có endpoint ngoài origin hoặc WebSocket không? |
| Form | Submit về cùng origin | Có luồng thanh toán hoặc SSO cần đích khác không? |
| Nhúng trang khác | Không có trong trang mẫu | Route khác có iframe video hoặc tích hợp đối tác không? |
| Trang bị nhúng | Không được phép trong tình huống | Có nhu cầu LMS đối tác nhúng tài liệu không? |

Inventory cần xét cả mã ứng dụng, tag manager, widget hỗ trợ, thư viện runtime và tài nguyên tải động. Một bundle ban đầu cùng origin có thể tải thêm script bên ngoài; chỉ nhìn HTML source chưa đủ để hiểu luồng tải.

Đối với trang học viên thật sự có video hoặc iframe, cần xác định nguồn được chấp nhận và quyền dữ liệu của tích hợp. Yêu cầu chức năng hợp lệ được đưa vào policy có chủ đích, thay vì mở rộng `*` mỗi khi xuất hiện một violation.

## 3. Đọc directive theo hành vi, không theo tên header

Một policy là tập directive phân tách bằng dấu chấm phẩy. Những directive sau giải quyết các hướng kiểm soát khác nhau:

| Directive | Hành vi cần đặc tả |
| --- | --- |
| `default-src` | Nguồn dự phòng cho các fetch directive có quy tắc fallback tương ứng |
| `script-src` | Script và những cơ chế thực thi liên quan theo policy |
| `script-src-attr` | JavaScript trong event-handler attribute |
| `style-src` | Stylesheet và style theo policy |
| `img-src`, `font-src`, `media-src` | Nguồn ảnh, font, media |
| `connect-src` | Các kết nối từ API của trang như fetch/XHR theo phạm vi directive |
| `frame-src` | Nguồn tài liệu con mà trang được tải vào frame |
| `worker-src` | Nguồn worker theo cơ chế CSP |
| `object-src` | Nguồn object/embed và nội dung liên quan |
| `base-uri` | Giá trị base URL mà tài liệu được dùng |
| `form-action` | Đích được phép submit form |
| `frame-ancestors` | Các trang cha được phép nhúng tài liệu này |

Các directive có thuật toán và quan hệ fallback riêng trong đặc tả; không thể xem mọi dòng là một danh sách host có cùng ý nghĩa. [W3C: Content Security Policy Level 3](https://www.w3.org/TR/CSP3/).

### 3.1. `default-src` không phải mặc định cho mọi thứ

Khi có `script-src` riêng, source list của nó được dùng theo directive đó, không tự cộng thêm source list của `default-src`. Các fetch directive thiếu cấu hình sẽ áp dụng chuỗi fallback tương ứng. [MDN: default-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/default-src).

Các giới hạn như `base-uri`, `form-action` và `frame-ancestors` phải được xem xét riêng. Không ghi yêu cầu “đã có `default-src 'none'` nên mọi hành vi ngoài danh sách đều bị cấm” mà chưa kiểm tra directive nào thực sự kế thừa.

### 3.2. `frame-src` khác `frame-ancestors`

`frame-src` kiểm soát trang này được tải tài liệu nào vào iframe. `frame-ancestors` kiểm soát ai được nhúng trang này. `frame-ancestors` không fallback về `default-src`, kiểm tra chuỗi ancestor và không được hỗ trợ qua CSP meta element. [MDN: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors).

Trong tình huống quản lý khóa học, có thể chốt cả hai là `'none'`. Nếu cần nhúng vào LMS của đối tác, thay đổi phía ancestor phải được xét theo origin và toàn bộ chuỗi nhúng thực tế; cho phép một iframe video ở trang con không tự cấp cho một website khác quyền nhúng màn hình quản trị.

## 4. Phân biệt nguồn được phép và script được cấp quyền

Một allowlist script chỉ theo host có thể quá rộng nếu host đó đồng thời có tài nguyên do người dùng tải lên hoặc các endpoint phát nội dung không phù hợp. Việc một file nằm cùng origin không tự chứng minh nó là mã ứng dụng đã được duyệt.

Một thiết kế khác là dùng nonce hoặc hash để cấp quyền cho những script cụ thể. Với nonce, server tạo một giá trị không thể dự đoán cho response, đưa nó vào policy và gắn cùng giá trị vào script do template ứng dụng kiểm soát.

```html
<!-- Giá trị dưới đây chỉ minh họa một response, không dùng làm nonce cố định. -->
<script nonce="RnN4XkQxE9k2fBv7sJp3qA=="
        src="/assets/course-app.js" defer></script>
```

Policy của chính response đó có thể chứa:

```text
script-src 'nonce-RnN4XkQxE9k2fBv7sJp3qA=='
```

Trình duyệt đối chiếu nonce theo cơ chế CSP. Nonce cần được tạo khác nhau cho mỗi lần phục vụ tài liệu, bằng bộ sinh ngẫu nhiên mật mã, với ít nhất 128 bit dữ liệu ngẫu nhiên trước encoding theo hướng dẫn. [MDN: nonce](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/nonce).

### 4.1. Không biến nonce thành con dấu cho dữ liệu không tin cậy

Template chỉ gắn nonce cho script mà ứng dụng chủ động viết hoặc tải. Không dùng middleware quét toàn bộ HTML rồi thêm nonce vào mọi thẻ `script`: markup do dữ liệu không tin cậy chèn vào cũng có thể được cấp quyền theo cách đó.

Cũng không đặt dữ liệu người dùng chưa được biểu diễn đúng ngữ cảnh vào một script đã có nonce. Nếu nội dung của script được cấp quyền đã bị dữ liệu làm thay đổi ý nghĩa, CSP không tự phân biệt phần nào của nội dung đó là ý định của lập trình viên.

Nguồn script cũng phải do ứng dụng kiểm soát. Một thẻ có nonce hợp lệ nhưng `src` lấy tùy ý từ input có thể trao quyền chạy cho nguồn không được dự định.

### 4.2. `strict-dynamic` là quyết định ủy quyền tải script

`'strict-dynamic'` cho phép sự tin cậy từ script được cấp quyền bằng nonce/hash truyền tới script mà root script tải theo cơ chế áp dụng. Trên trình duyệt hỗ trợ, các source expression theo host hoặc scheme như `'self'` trong cùng `script-src` không còn được dùng như một allowlist bổ sung theo cách nhiều người tưởng. [MDN: script-src và strict-dynamic](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src#strict-dynamic).

Vì vậy, không thêm `strict-dynamic` chỉ để “policy hiện đại hơn”. Cần biết root loader nào được tin, nó lấy URL script từ đâu và có thể bị dữ liệu điều khiển không. Nếu trang chỉ cần các script đã được template cấp nonce, policy mẫu trong bài không cần directive này.

Khi ứng dụng có runtime loader hợp lệ, đội thiết kế có thể bổ sung `strict-dynamic` sau khi đánh giá luồng tải và ma trận trình duyệt. Không lấy việc thêm một từ khóa làm bằng chứng đã đánh giá chuỗi tin cậy của loader.

## 5. Ví dụ Java: tạo policy và nonce trong cùng một lần render

Ví dụ Java 17 dưới đây tạo 32 byte ngẫu nhiên, tương đương 256 bit trước Base64. Mỗi lần render một tài liệu mới gọi factory đúng một lần; kết quả được dùng chung cho header và các script tin cậy của tài liệu đó.

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class DocumentCsp {
    private static final SecureRandom RANDOM = new SecureRandom();

    public record RenderSecurity(String nonce, String policy) {}

    public static RenderSecurity forNewDocument() {
        byte[] randomBytes = new byte[32];
        RANDOM.nextBytes(randomBytes);
        String nonce = Base64.getEncoder().encodeToString(randomBytes);

        String policy = String.join("; ",
                "default-src 'none'",
                "script-src 'nonce-" + nonce + "'",
                "script-src-attr 'none'",
                "style-src 'self'",
                "img-src 'self'",
                "font-src 'self'",
                "connect-src 'self'",
                "media-src 'none'",
                "frame-src 'none'",
                "worker-src 'none'",
                "object-src 'none'",
                "base-uri 'none'",
                "form-action 'self'",
                "frame-ancestors 'none'",
                "report-to csp"
        );
        return new RenderSecurity(nonce, policy);
    }

    private DocumentCsp() {}
}
```

Ở adapter HTTP và template của trang, sử dụng cùng đối tượng:

```java
DocumentCsp.RenderSecurity security = DocumentCsp.forNewDocument();

// Ví dụ tích hợp với response/template context do ứng dụng kiểm soát.
response.setHeader("Content-Security-Policy", security.policy());
response.setHeader("Reporting-Endpoints",
        "csp=\"https://reports.learning.example/csp\"");
response.setHeader("Cache-Control", "private, no-store");
request.setAttribute("cspNonce", security.nonce());
```

Các đối tượng `response` và `request` ở đoạn tích hợp là đối tượng của adapter web thực tế, không phải API do lớp `DocumentCsp` định nghĩa. Ví dụ không yêu cầu sửa cấu hình hay dependency của module học tập.

Template đưa `cspNonce` vào thuộc tính nonce của những script tin cậy bằng cơ chế thuộc tính của template. Không gọi factory lần thứ hai để lấy nonce cho body, vì header và body sẽ khác giá trị.

Policy mẫu có các giả định cụ thể: CSS là stylesheet ngoài cùng origin, không cần style attribute, không dùng worker/media/frame và các API của trang cùng origin. Nếu mã giao diện còn dựa vào inline style, event-handler attribute hoặc `eval`, cần xử lý phụ thuộc đó theo kế hoạch thay đổi, không mở rộng policy một cách tự động.

### 5.1. Nonce và cache phải được thiết kế cùng nhau

Response động trong ví dụ dùng `private, no-store` để không tái phát hành nguyên một HTML có nonce qua shared cache. Không cache HTML dùng nonce theo một policy chung rồi coi `Vary: Cookie` là đã bảo đảm nonce mới cho mỗi response.

Nếu edge tạo nonce, nó phải tạo và gắn nhất quán cả header lẫn đúng các vị trí template tin cậy trong body. Chỉ thay nonce header nhưng giữ body đã cache làm script hợp lệ bị chặn; tái dùng nonce của bản HTML cũ làm mất contract về tính mới của nonce.

Với HTML tĩnh cần cache rộng, hash-based policy có thể phù hợp hơn. Quyết định này phải được ghi cùng chiến lược build và phân phối tài nguyên, thay vì giải quyết cache bằng cách bỏ kiểm soát script.

## 6. Hash-based policy cho nội dung tĩnh

Hash cấp quyền dựa trên nội dung script theo thuật toán được CSP hỗ trợ. Với inline script, byte nội dung thực sự được đưa vào trang phải khớp digest; thay whitespace hoặc minify khác có thể làm hash không còn khớp.

Ví dụ tính source expression từ một đoạn script cố định trong Java:

```java
String trustedBootstrap =
        "document.documentElement.dataset.courseAppReady = 'true';";
byte[] digest = java.security.MessageDigest.getInstance("SHA-256")
        .digest(trustedBootstrap.getBytes(java.nio.charset.StandardCharsets.UTF_8));
String hashSource = "'sha256-"
        + java.util.Base64.getEncoder().encodeToString(digest) + "'";
String scriptDirective = "script-src " + hashSource;
```

Đoạn này minh họa inline script có nội dung đúng bằng `trustedBootstrap`, không bao gồm thẻ `script`. Việc phát hành phải cập nhật script và header hash như cùng một artifact để tránh lệch phiên bản. Các yêu cầu cho hash của external script và Subresource Integrity cần được thiết kế riêng nếu sử dụng.

Không tính hash từ chuỗi người dùng gửi rồi tự thêm nó vào policy: thao tác đó chỉ đổi cách cấp quyền cho dữ liệu không tin cậy. Tập nội dung được cấp hash phải xuất phát từ artifact ứng dụng đã được duyệt.

Nonce và hash là hai cách xác định mã được tin trong những mô hình phát hành khác nhau. Chúng không thay việc kiểm tra nguồn dữ liệu mà mã đã được cấp quyền sử dụng tiếp theo.

## 7. Report-Only dùng để quan sát, enforce dùng để chặn

Hai header có vai trò khác nhau:

| Header | Vai trò |
| --- | --- |
| `Content-Security-Policy` | Trình duyệt thực thi policy và chặn hành vi vi phạm theo directive |
| `Content-Security-Policy-Report-Only` | Đánh giá policy ở chế độ báo cáo, không biến các vi phạm đó thành chặn theo policy report-only |

Một response có thể đồng thời enforce policy hiện tại và report-only một candidate chặt hơn. Candidate không nới lỏng policy đang enforce; tài nguyên bị policy enforce cấm vẫn bị chặn. [MDN: Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only).

Trong quá trình chuyển đổi, cần ghi rõ policy nào là baseline đang bảo vệ và policy nào là thử nghiệm. Một scanner thấy header Report-Only không được coi đó là bằng chứng script ngoài policy đã bị ngăn chạy.

Không kéo dài vô hạn trạng thái report-only mà vẫn công bố yêu cầu “trình duyệt chặn inline script”. Nếu mục tiêu chỉ đang được quan sát, trạng thái yêu cầu phải phản ánh đúng khoảng trống đó, cùng owner và gate chuyển sang enforce.

Các giới hạn chức năng cần được kiểm tra ở chế độ enforce trên môi trường phù hợp. Report-only giúp phát hiện phụ thuộc, nhưng không thay một ca xác nhận thao tác vi phạm thực sự không có hiệu ứng khi bị chặn.

## 8. Header phải tới đúng tài liệu và không bị các tầng làm lệch

### 8.1. Ưu tiên phân phối qua HTTP response header

CSP của trang phải được phân phối trên response tài liệu cần bảo vệ. Đặt CSP trên một JSON API không tự áp policy đó lên trang HTML đang fetch JSON. Tương tự, một file JavaScript có header không thay cho policy của tài liệu đã tải nó theo cách cần bảo vệ ở đây.

Trong tình huống của bài, cần inventory các HTML response của màn hình quản lý, đăng nhập và trang lỗi có giao diện tương ứng. Không chỉ kiểm tra đường trả `200` thuận lợi rồi bỏ qua error page do proxy hoặc ứng dụng sinh ra.

Meta element chỉ hỗ trợ một phần cơ chế CSP và bị giới hạn về vị trí/thời điểm có hiệu lực; không dùng nó thay hoàn toàn header khi yêu cầu có các directive hoặc chế độ không được hỗ trợ. Với `frame-ancestors`, cần HTTP header như đã nêu ở phần directive. [MDN: Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy).

### 8.2. Nhiều policy enforce là nhiều điều kiện đồng thời

Nếu ứng dụng và reverse proxy cùng phát CSP enforce, tài liệu phải thỏa các policy cùng có hiệu lực. Thêm một header có source list rộng hơn không tự nới header chặt hơn trước đó. [MDN: multiple content security policies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy#multiple_content_security_policies).

Ví dụ app cho `connect-src 'self'` nhưng proxy còn giữ `connect-src 'none'`: fetch cùng origin vẫn có thể bị chặn. Đây là lỗi phối hợp cấu hình, không phải lý do để thêm một policy thứ ba với `connect-src *`.

Cần chốt tầng nào sở hữu policy động có nonce, tầng nào được thêm các header khác và cách đối soát response cuối cùng. Khi edge sửa HTML, minify hoặc cache body, nó phải giữ contract nonce/hash tương ứng.

### 8.3. Policy revision khác nonce của response

Nonce thay theo tài liệu; policy revision biểu diễn cấu hình đã được phát hành. Telemetry nên liên kết được response với revision ổn định mà không dùng toàn bộ nonce làm nhãn metrics.

Một đổi cấu hình ở proxy hoặc CDN cũng là thay đổi policy thực tế, dù code Java không đổi. Gate phát hành cần nhìn header và body sau tất cả các tầng, không chỉ unit test cho chuỗi policy builder.

## 9. Reporting cần endpoint và chính sách dữ liệu riêng

Trong ví dụ, directive `report-to csp` tham chiếu tên endpoint được công bố bằng header:

```http
Reporting-Endpoints: csp="https://reports.learning.example/csp"
```

Reporting API định nghĩa ánh xạ tên tới endpoint và cơ chế chuyển báo cáo ngoài luồng hoạt động của trang. Việc giao báo cáo là best-effort; trình duyệt, kết nối hoặc điều kiện môi trường có thể khiến báo cáo không tới collector. [W3C: Reporting API](https://www.w3.org/TR/reporting/).

Do đó không nhận được report không chứng minh policy không có violation, và không được lấy việc endpoint nhận report làm bằng chứng mọi trang đã enforce đúng.

### 9.1. Phân biệt cơ chế báo cáo được hỗ trợ

Ma trận trình duyệt của sản phẩm phải ghi rõ khả năng hỗ trợ `report-to` và cơ chế báo cáo được chọn. Nếu cần `report-uri` để đáp ứng một tập client đã chốt, thiết kế collector phải nhận đúng format tương ứng và phân biệt với Reporting API. Không mặc định hai cơ chế gửi cùng một JSON schema.

Không mở một fallback làm yếu `script-src` chỉ để hỗ trợ reporting. Khả năng gửi báo cáo và khả năng chặn tài nguyên là hai tiêu chí cần được kiểm tra riêng.

### 9.2. Collector nhận dữ liệu không tin cậy

Một report có thể bị giả mạo hoặc gửi lặp. Collector cần giới hạn kích thước body, số report trong batch, tốc độ nhận, độ dài trường và thời hạn lưu. Không thực thi nội dung report, không dùng URL trong report làm lệnh cho server truy cập và không xem report là audit có thẩm quyền về danh tính người dùng.

Sau chuẩn hóa, hệ thống có thể lưu một sự kiện nội bộ nhỏ:

```json
{
  "event": "CSP_VIOLATION_OBSERVED",
  "policyRevision": "course-management-csp-4",
  "routeGroup": "course-management",
  "effectiveDirective": "script-src-elem",
  "disposition": "enforce",
  "blockedResourceClass": "inline"
}
```

Đây là schema sự kiện nội bộ minh họa, không phải khẳng định mọi trình duyệt gửi nguyên cấu trúc này. Adapter collector phải chuyển từ format nguồn đã hỗ trợ sang schema quan sát của sản phẩm.

### 9.3. Tránh đưa dữ liệu riêng vào kênh report

Report có thể liên quan tới document URL, referrer, original policy hoặc chi tiết tài nguyên bị chặn. URL của ứng dụng không nên mang token hoặc dữ liệu cá nhân; collector vẫn phải kiểm tra, giảm dữ liệu và che thông tin theo policy, thay vì mặc định mọi trường đã được trình duyệt làm sạch đủ.

Việc bật `report-sample`, nếu cần, phải được xét riêng vì sample có thể chứa một phần nội dung thực thi hoặc dữ liệu của trang. Policy mẫu không cần tùy chọn này để đạt mục tiêu chặn script ngoài quyền.

Metrics nên nhóm theo directive, route group, policy revision và disposition có tập giá trị kiểm soát. Không đưa raw URL, nonce hoặc toàn bộ policy từng response vào label không giới hạn. Báo cáo có thể chứa nhiễu từ extension hoặc mã cũ; cần phân loại trước khi mở rộng nguồn được phép.

## 10. Từ mục tiêu rủi ro tới bộ yêu cầu cụ thể

Đối với trang quản lý khóa học trong bài, có thể đặc tả các yêu cầu sau:

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-CSP-01 | Các HTML route trong phạm vi có policy enforce được duyệt và owner rõ ràng | Danh mục route cùng response thực tế qua gateway/CDN |
| SR-CSP-02 | Script chỉ được thực thi theo mô hình nonce hoặc hash đã chọn; không cho phép inline script tùy ý hoặc string-to-code ngoài policy | Ca script hợp lệ, thiếu/sai nonce và cơ chế thực thi cần kiểm tra |
| SR-CSP-03 | Nonce được sinh bằng CSPRNG, tối thiểu 128 bit trước encoding, thay theo response và khớp header/body | Kiểm tra nguồn sinh, nhiều response và phép đối chiếu nonce |
| SR-CSP-04 | Nonce chỉ được template gắn cho script tin cậy, không phát sinh từ input và không thêm hàng loạt vào HTML tùy ý | Kiểm tra template/renderer và fixture markup không tin cậy |
| SR-CSP-05 | Nguồn style, ảnh, font, kết nối và các tài nguyên khác đúng inventory của từng nhóm trang | Ma trận tài nguyên cần thiết và ca nguồn ngoài tập |
| SR-CSP-06 | `base-uri`, `form-action` và `frame-ancestors` có quyết định riêng; không dựa sai vào default-src | Kiểm tra hành vi base, submit và nhúng trang |
| SR-CSP-07 | Report-Only không được tính là đã hoàn thành yêu cầu chặn; candidate có gate chuyển enforce | Hồ sơ rollout và ca trình duyệt phân biệt hai chế độ |
| SR-CSP-08 | Mọi tầng phát header phối hợp để policy cuối cùng không bị mất, lệch nonce hoặc thêm policy xung đột | Readback raw headers và HTML sau đường phân phối thật |
| SR-CSP-09 | CSP report được xử lý như input không tin cậy, có giới hạn tài nguyên và giảm dữ liệu riêng | Ca collector sai schema/quá lớn/lặp và kiểm tra retention |
| SR-CSP-10 | Chính sách cache không tái dùng nonce trái contract và không làm lệch header/body | Ca cache hit/miss, các người dùng và các node theo kiến trúc |
| SR-CSP-11 | Ngoại lệ nguồn hoặc loader có owner, lý do, phạm vi và ngày xem xét lại | Registry ngoại lệ và gate thay đổi policy |
| SR-CSP-12 | XSS encoding/sanitization và authorization tiếp tục được kiểm chứng độc lập với CSP | Bằng chứng các kiểm soát nền và ca không phụ thuộc report |

Các từ như “script tin cậy” và “trang trong phạm vi” phải ánh xạ được tới artifact/route cụ thể. Một yêu cầu chỉ ghi “bật strict CSP” không cho reviewer biết cách cấp quyền cho script, phạm vi chức năng hay tiêu chí từ chối.

Nếu cần tài nguyên bên thứ ba, yêu cầu nguồn phải ghi rõ mục đích và quyền. Một nhà cung cấp analytics được phép tải script có thể chạy trong ngữ cảnh trang với khả năng đáng kể; việc thêm host vào CSP không thay đánh giá dữ liệu mà script đó được tiếp cận.

## 11. Lộ trình triển khai có gate rõ ràng

### 11.1. Khảo sát và sửa các phụ thuộc không cần thiết

Liệt kê inline event handler, inline script/style, runtime loader và các chức năng dùng string-to-code. Chuyển những handler như `onclick` sang listener trong bundle tin cậy; giữ dữ liệu ngoài code khi có thể. Với HTML do người dùng soạn, tiếp tục dùng sanitizer theo contract nội dung.

Không giữ một bộ cấu hình dev rộng rồi mang nguyên sang production. Dev server, hot reload và source map có nhu cầu riêng; policy từng môi trường phải được phân biệt nhưng vẫn có owner và giới hạn dữ liệu tương ứng.

### 11.2. Quan sát candidate mà vẫn biết baseline hiện tại

Phát candidate bằng Report-Only, gắn revision và collector có giới hạn. Chạy các luồng chức năng quan trọng: đăng nhập, mở khóa học, lưu thay đổi, phiên hết hạn và trang lỗi.

Mỗi nhóm violation cần được phân loại thành phụ thuộc hợp lệ, lỗi triển khai, input không tin cậy hoặc nhiễu. Không tự lấy danh sách `blockedURL` rồi thêm tất cả vào allowlist; một tài nguyên bị chặn có thể chính là hành vi policy cần ngăn.

### 11.3. Enforce theo nhóm trang và ma trận trình duyệt

Chọn nhóm trang có inventory rõ để enforce, rồi mở rộng theo kế hoạch. Gate cần có các ca chức năng hợp lệ thành công và các ca vi phạm bị chặn trên tập trình duyệt/version mà sản phẩm cam kết.

Các directive mới có thể không có cùng mức hỗ trợ trên mọi client. Phải đánh giá policy có hiệu lực thực tế, bao gồm fallback, thay vì chỉ kiểm tra cú pháp header trên một browser hiện đại. Không thêm `'unsafe-inline'` hoặc `'unsafe-eval'` toàn cục để dập lỗi tương thích mà chưa có quyết định rủi ro cụ thể.

### 11.4. Giữ đường phục hồi mà không mất baseline

Nếu một candidate làm hỏng chức năng, có thể quay lại policy enforce đã biết trong phạm vi kế hoạch phát hành. Không biến rollback thành việc xóa toàn bộ CSP hoặc mở wildcard vô thời hạn.

Ngoại lệ phải gắn với route/tài nguyên cụ thể và có ngày rà soát. Nếu phải cho thêm một origin, xác minh domain do ai kiểm soát và endpoint nào trên origin có thể cung cấp nội dung thực thi. Một nguồn được phép có upload tùy ý không tương đương kho artifact do đội phát hành quản lý.

## 12. Thiết kế ca nghiệm thu ở trình duyệt

Phần này mô tả bằng chứng cần có khi triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được chạy trong bài học.

### 12.1. Kiểm tra header và nonce trước

Lấy nhiều response mới của cùng route qua đường phân phối thực tế. Với mỗi response, parse policy và HTML để xác nhận nonce của script tin cậy khớp source expression; giữa các response phải có giá trị mới theo contract. Kiểm tra code nguồn sinh nonce, vì một mẫu nhỏ không trùng nhau chưa chứng minh chất lượng ngẫu nhiên.

Không chỉ dùng một biểu thức tìm thấy chữ `nonce-` là PASS. Cần phân biệt header enforce với Report-Only, policy bổ sung từ proxy, những script không cần hoặc không được cấp quyền, và bản HTML đến từ cache.

### 12.2. Ma trận hành vi mẫu

| Ca | Thao tác trong môi trường kiểm thử | Kỳ vọng theo policy mẫu |
| --- | --- | --- |
| C1 | Script `/assets/course-app.js` có nonce của response | Được thực thi và chức năng hợp lệ hoạt động |
| C2 | Inline script không có nonce | Không thực thi khi enforce |
| C3 | Script có nonce khác hoặc nonce từ response trước | Không được cấp quyền bởi response hiện tại |
| C4 | Event-handler attribute như `onclick` được thêm vào fixture | Không thực thi handler theo policy |
| C5 | Script không có nonce dù cùng origin | Không được tự cấp quyền chỉ vì cùng origin |
| C6 | Kết nối từ trang tới origin ngoài inventory | Bị chặn theo connect-src của mẫu |
| C7 | Tài liệu thêm base URL không được phép | Base không được áp dụng theo policy |
| C8 | Form submit tới origin ngoài tập | Bị chặn theo form-action |
| C9 | Một trang khác cố nhúng màn hình quản lý | Bị chặn theo frame-ancestors |
| C10 | Trang mẫu cố tải iframe/video/worker | Bị chặn; route có nhu cầu khác phải có contract riêng |
| C11 | Cùng fixture vi phạm ở Report-Only và enforce | Phân biệt được quan sát với chặn thực tế |
| C12 | Header app và proxy có policy đồng thời | Hiệu lực cuối đúng với tập điều kiện đồng thời, không suy là cộng allowlist |

Với fixture inline script, có thể dùng một marker vô hại, chẳng hạn đoạn chỉ đặt `document.documentElement.dataset.cspProbe = 'executed'`. Khi test mong bị chặn, marker không được xuất hiện do script đó thực thi. Đồng thời quan sát sự kiện/console và trạng thái chức năng để phân biệt bị CSP chặn với một lỗi JavaScript khác.

Fixture phải được tải hoặc chèn qua ngữ cảnh phù hợp để trình duyệt thực sự áp dụng CSP. Việc gõ một lệnh trực tiếp trong công cụ phát triển có đặc quyền không tự tương đương với một script do tài liệu tải, nên không dùng nó làm bằng chứng duy nhất về enforcement.

### 12.3. Kiểm tra không vô tình cấp nonce cho markup không tin cậy

Đưa vào dữ liệu thử một marker markup phù hợp môi trường kiểm thử, rồi xác minh renderer vẫn encode/sanitize theo contract và không gắn nonce cho script phát sinh từ dữ liệu. Ca này kiểm tra hai lớp khác nhau: dữ liệu không được biến thành markup thực thi, và cơ chế cấp nonce không tự hợp thức hóa markup ngoài template.

Nếu ứng dụng cần rich text, kiểm tra HTML sau sanitizer trước khi render và hành vi ở browser. CSP không phải lý do để cho phép sanitizer giữ những thành phần thực thi mà nghiệp vụ không cần.

### 12.4. Kiểm tra report và chức năng cùng lúc

Tạo một violation biết trước để kiểm tra collector nhận đúng cơ chế, nhưng không buộc một bài test chức năng phải chờ report tức thời như một bảo đảm giao hàng. Có thể xác minh event cục bộ và hành vi chặn riêng, kiểm tra đường report riêng theo cửa sổ quan sát phù hợp.

Kiểm tra report-only và enforce được phân loại đúng trong telemetry. Một lượng report bằng zero có thể là policy tốt, browser không gửi được hoặc collector lỗi; cần tín hiệu sức khỏe đường quan sát để phân biệt.

Các luồng hợp lệ phải tiếp tục hoạt động dưới enforce: form được phép submit, API được phép gọi và script tin cậy thực thi. Policy chặn hết mọi thứ nhưng làm trang không sử dụng được không đáp ứng yêu cầu bảo mật gắn với chức năng.

## 13. Giới hạn và những giả định cần tránh

**CSP không thay quyền truy cập server.** Một client không phải trình duyệt có thể gửi HTTP trực tiếp. Endpoint vẫn phải kiểm tra authentication, object/field authorization và các điều kiện nghiệp vụ.

**CSP không biến mọi nguồn cùng origin thành đáng tin.** Upload, endpoint trả nội dung động hoặc một loader lấy URL từ input cần được đánh giá theo cách chúng được dùng. Policy nguồn không thay inventory nội dung thực thi.

**CSP không phải tường lửa dữ liệu toàn diện.** `connect-src` kiểm soát các kết nối trong phạm vi directive, không tự chứng minh mọi kênh đưa dữ liệu khỏi trang đã bị loại bỏ. Quyền của script đã được cấp, các nguồn còn cho phép và các hành vi khác vẫn cần được xét.

**Một report không chứng minh người dùng bị tấn công.** Nó có thể do lỗi, mã cũ, extension hoặc dữ liệu giả mạo gửi tới collector. Điều tra phải dựa trên ngữ cảnh và nhiều bằng chứng.

**Không phải cứ có CSP là đã có script policy chặt.** Wildcard, cho phép inline tùy ý, hoặc một policy chỉ giới hạn ảnh chưa chứng minh mục tiêu ngăn thực thi script ngoài dự kiến đã đạt.

**Không sửa lỗi bằng cách mở toàn bộ origin hoặc scheme.** Mỗi thay đổi source list cần gắn với nhu cầu và owner. Tài nguyên hợp lệ bị chặn là đầu vào để điều chỉnh thiết kế, không phải bằng chứng cần bỏ mọi giới hạn.

**Một lần kiểm tra header không bao phủ toàn bộ phân phối.** Error page, route ít dùng, vùng triển khai, CDN cache và các node proxy có thể khác cấu hình. Phạm vi nghiệm thu phải bám inventory.

## 14. Bài tập vận dụng

Một nền tảng học tập có trang quản lý dùng bundle nội bộ, trang học có iframe video từ nhà cung cấp, và trang đăng nhập có form về cùng origin. Hiện đội vận hành muốn phát một policy duy nhất với `script-src * 'unsafe-inline'` để tránh lỗi tương thích.

Hãy đề xuất thiết kế với các đầu ra sau:

1. Tách inventory và mục tiêu kiểm soát của ba nhóm trang, chỉ ra nhu cầu nguồn nào thực sự khác nhau.
2. Chọn nonce hoặc hash cho script của từng mô hình render; mô tả cách giữ header/body hoặc artifact nhất quán.
3. Quyết định riêng cho base-uri, form-action, frame-src và frame-ancestors.
4. Viết ba yêu cầu có thể nghiệm thu, mỗi yêu cầu gắn với một rủi ro và ít nhất hai ca hành vi trình duyệt.
5. Thiết kế rollout Report-Only sang enforce cùng collector có giới hạn dữ liệu và tài nguyên.
6. Chỉ ra policy baseline được giữ khi rollback và cách kiểm soát ngoại lệ nguồn bên thứ ba.

Kết quả cần chỉ rõ hành vi được cấp quyền, nơi policy được phát và bằng chứng browser thực thi đúng. Content-Security-Policy có giá trị khi trở thành một hợp đồng cụ thể của từng nhóm tài liệu, được duy trì cùng template, tài nguyên, cache và quy trình phát hành.
