# Clickjacking defense

## 1. Clickjacking là làm lệch ý định của thao tác giao diện

Clickjacking là một dạng UI redress: người dùng tưởng mình đang tương tác với nội dung của một trang, nhưng thao tác thực tế lại tác động lên giao diện khác bị đặt trong một ngữ cảnh gây hiểu lầm. Với hình thức dùng frame, một trang không đáng tin có thể nhúng trang hợp lệ rồi bố trí lớp hiển thị khiến người dùng không nhận ra nơi nhận cú nhấp.

Rủi ro không nhất thiết đòi hỏi đọc được DOM của trang mục tiêu hoặc chạy mã trong origin của ứng dụng. Nếu người dùng đã đăng nhập và trang thật xử lý thao tác hợp lệ từ chính giao diện đó, request có thể mang session và CSRF token đúng. Vấn đề là người dùng không hiểu đúng hành động mà mình vừa kích hoạt.

Ví dụ trong nền tảng học tập: một giảng viên có quyền công bố khóa học, đổi người quản lý hoặc thu hồi chứng chỉ. Nếu màn hình nhạy cảm được nhúng tùy ý, một trang khác có thể đặt nó vào trải nghiệm đánh lừa người dùng. Authorization server vẫn có thể trả lời “giảng viên này có quyền”, nhưng chưa chứng minh thao tác thể hiện đúng ý định của họ.

Trong module yêu cầu bảo mật, mục tiêu là xác định những trang nào được phép bị nhúng, bởi origin nào, và hành động nhạy cảm cần thêm điều kiện gì để người dùng nhận biết rõ. Chống clickjacking không thể chỉ đặc tả bằng câu “có token chống CSRF”.

## 2. Phân biệt các lớp bảo vệ liên quan

| Cơ chế | Câu hỏi nó giải quyết | Vì sao chưa đủ một mình? |
| --- | --- | --- |
| Authentication | Người gọi hoặc session là ai? | Người dùng thật vẫn có thể bị dẫn dắt tương tác sai ý định |
| Authorization | Danh tính đó có quyền thực hiện thao tác không? | Một thao tác đúng quyền vẫn có thể do giao diện gây hiểu nhầm kích hoạt |
| CSRF defense | Request có đáp ứng quy tắc chống giả mạo liên trang không? | Clickjacking có thể dùng chính form và token hợp lệ của trang thật |
| Same-origin policy | Các origin có được đọc/tác động dữ liệu của nhau qua các API tương ứng không? | Nhúng và lừa tương tác không nhất thiết cần đọc DOM chéo origin |
| Framing policy | Những ancestor nào được phép chứa tài liệu? | Một ancestor đã được cho phép vẫn cần được đánh giá mức tin cậy |
| Xác nhận hành động có ngữ cảnh | Người dùng có thấy đúng đối tượng và tác động trước khi chấp thuận không? | Một hộp xác nhận generic nằm trong frame vẫn có thể bị đánh lừa |

Same-origin policy giới hạn nhiều tương tác giữa tài liệu khác origin, nhưng không nên suy từ đó rằng mọi cross-origin embedding tự bị cấm. Việc kiểm soát ai được nhúng trang cần policy riêng. [MDN: Same-origin policy](https://developer.mozilla.org/en-US/docs/Glossary/Same-origin_policy).

Các kiểm soát trên bổ sung cho nhau. Đội thiết kế cần giữ authentication, authorization và CSRF, đồng thời thêm yêu cầu về framing và ngữ cảnh xác nhận đối với bề mặt có rủi ro.

## 3. Lập inventory theo trang và hành động

Không phải mọi trang của nền tảng cần cùng một mức nhúng. Một ma trận mẫu có thể như sau:

| Nhóm trang | Nhu cầu nhúng của tình huống | Chính sách đề xuất |
| --- | --- | --- |
| Bảo mật tài khoản, MFA, đổi thông tin xác thực | Không | Không cho nhúng |
| Quản trị tổ chức, cấp role, đổi quyền sở hữu | Không | Không cho nhúng |
| Xác nhận công bố hoặc thu hồi chứng chỉ | Không | Không cho nhúng; xác nhận rõ hành động |
| Trang nội bộ chỉ cần frame cùng origin | Có nhu cầu đã xác minh | Chỉ cùng origin |
| Thẻ giới thiệu khóa học cho LMS đối tác | Có | Route nhúng chuyên biệt, origin được duyệt, quyền tối thiểu |
| Trang lỗi hoặc trạng thái phiên có giao diện | Cần xét theo luồng | Giữ policy của nhóm trang tương ứng |

“Nội bộ” không tự đồng nghĩa “cùng origin”. `https://learn.example.com` và `https://portal.example.com` là hai origin khác nhau. Cần ghi đúng scheme, host và port trong quyết định quyền nhúng.

Inventory cũng cần nêu trạng thái đăng nhập, các redirect, host được dùng, proxy/CDN và những đường hiển thị cùng chức năng qua route cũ hoặc giao diện mobile. Một màn hình được bảo vệ ở URL chính nhưng còn alias không có header vẫn là khoảng trống cần xử lý.

Các policy trong bài là ví dụ thiết kế. Không có thao tác thay đổi server, gateway hay trình duyệt production nào được yêu cầu để đọc bài học này.

## 4. CSP `frame-ancestors`: kiểm soát ai được nhúng tài liệu

Ba policy cơ bản:

```http
Content-Security-Policy: frame-ancestors 'none'
```

```http
Content-Security-Policy: frame-ancestors 'self'
```

```http
Content-Security-Policy: frame-ancestors 'self' https://lms.partner.example
```

`'none'` cấm các ancestor nhúng tài liệu; `'self'` giới hạn cùng origin; danh sách origin cấp quyền cho các nguồn đã chốt. Directive kiểm tra các ancestor trong chuỗi nhúng, không chỉ parent trực tiếp. Nó không fallback về `default-src` và không có hiệu lực nếu chỉ đặt qua CSP meta element. [MDN: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors).

### 4.1. Phải xét toàn bộ chuỗi ancestor

Giả sử route nhúng chỉ cho `https://lms.partner.example` và origin của ứng dụng. Chuỗi sau không được coi là hợp lệ chỉ vì parent gần nhất là đối tác:

```text
https://outside.example       ← không được cho phép
└── https://lms.partner.example
    └── https://learn.example.com/embed/course-card
```

Ancestor ngoài cùng vẫn phải đáp ứng policy của tài liệu con. Đây là một ca nghiệm thu quan trọng khi một đối tác nhúng giao diện bên trong một portal nhiều tầng.

Nếu ứng dụng có thêm một origin wrapper hợp lệ, phải đánh giá và liệt kê origin đó có chủ đích. Không giải quyết lỗi chuỗi nhúng bằng wildcard rộng cho toàn bộ Internet hoặc toàn bộ hệ sinh thái đối tác chưa được quản lý.

### 4.2. `frame-src` là hướng kiểm soát khác

`frame-src` của trang A giới hạn tài liệu con mà A được tải vào frame. `frame-ancestors` trên trang B quyết định ancestor nào được chứa B. Vì vậy một policy như `frame-src 'none'` trên màn hình quản trị không thay yêu cầu `frame-ancestors 'none'` để ngăn website khác nhúng màn hình đó.

Tương tự, `default-src 'none'` không tự cung cấp một anti-framing policy. Cần directive riêng đúng mục tiêu thay vì chỉ tìm thấy một CSP header bất kỳ rồi chốt PASS.

## 5. `X-Frame-Options` và ma trận tương thích

Hai giá trị thường dùng là:

```http
X-Frame-Options: DENY
```

```http
X-Frame-Options: SAMEORIGIN
```

`DENY` cấm nhúng, còn `SAMEORIGIN` giới hạn theo same-origin. Không dùng `ALLOW-FROM` như một allowlist hiện đại: directive này đã lỗi thời và các trình duyệt hiện đại có thể bỏ qua header đó. Đặt X-Frame-Options trong meta element cũng không có tác dụng như response header. [MDN: X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options).

### 5.1. Ghép policy có chủ đích

| Nhu cầu | CSP enforce | X-Frame-Options tương ứng |
| --- | --- | --- |
| Không cho nhúng | `frame-ancestors 'none'` | `DENY` |
| Chỉ cùng origin | `frame-ancestors 'self'` | `SAMEORIGIN` |
| Một số đối tác khác origin | Origin allowlist cụ thể | Không có cách tương đương để biểu diễn danh sách đối tác bằng các giá trị hiện đại trên |

Theo cơ chế CSP, một `frame-ancestors` trong policy enforce được xử lý ưu tiên so với X-Frame-Options. Tuy vậy vẫn phải kiểm tra tập browser/version mà sản phẩm hỗ trợ, đặc biệt khi duy trì fallback. [W3C CSP: frame-ancestors và X-Frame-Options](https://www.w3.org/TR/CSP3/#directive-frame-ancestors).

Với route cho đối tác, không phát một X-Frame-Options không hợp lệ để giả lập allowlist. Nếu giữ `DENY` hay `SAMEORIGIN` như fallback, các client áp dụng fallback đó có thể không nhúng được. Sản phẩm phải chốt rõ browser hỗ trợ và phương án xem top-level cho client không đáp ứng contract; không bỏ toàn bộ framing defense để cố hỗ trợ mọi trường hợp.

### 5.2. Report-Only không phải bằng chứng đã chống nhúng

`Content-Security-Policy-Report-Only` không cung cấp enforcement của policy đó. Nếu mục tiêu yêu cầu ngăn nhúng, cần một cơ chế enforce có hiệu lực. X-Frame-Options đang enforce có thể vẫn là một lớp độc lập, nhưng chỉ có Report-Only không được tính như đã chặn framing.

Các báo cáo trình duyệt giúp quan sát, không bảo đảm được giao đầy đủ. Một lần thử không thấy report hoặc không thấy session trong frame chưa đủ chứng minh header đã thực thi đúng; phải xác minh hành vi và nguyên nhân thực tế.

## 6. Ví dụ Java: chọn header từ phân loại route tin cậy

Ví dụ Java 17 dưới đây tách ba nhu cầu. Phân loại trang phải do router/metadata của server quyết định, không nhận từ query `embed=true`, header tự khai báo hoặc body của client.

```java
import java.util.Objects;
import java.util.Optional;

public final class FramingPolicy {
    public enum PageKind {
        ACCOUNT_SECURITY,
        ORGANIZATION_ADMIN,
        SAME_ORIGIN_WORKSPACE,
        PARTNER_COURSE_CARD
    }

    public record FramingHeaders(
            String contentSecurityPolicy,
            Optional<String> xFrameOptions
    ) {}

    public static FramingHeaders forPage(PageKind pageKind) {
        Objects.requireNonNull(pageKind, "Server page classification required");

        return switch (pageKind) {
            case ACCOUNT_SECURITY, ORGANIZATION_ADMIN ->
                    new FramingHeaders(
                            "frame-ancestors 'none'",
                            Optional.of("DENY")
                    );
            case SAME_ORIGIN_WORKSPACE ->
                    new FramingHeaders(
                            "frame-ancestors 'self'",
                            Optional.of("SAMEORIGIN")
                    );
            case PARTNER_COURSE_CARD ->
                    new FramingHeaders(
                            "frame-ancestors 'self' https://lms.partner.example",
                            Optional.empty()
                    );
        };
    }

    private FramingPolicy() {}
}
```

Một adapter có thể phát policy anti-framing như một CSP enforce bổ sung, để không ghi đè CSP khác bảo vệ script và tài nguyên của tài liệu:

```java
FramingPolicy.FramingHeaders headers = FramingPolicy.forPage(
        FramingPolicy.PageKind.ACCOUNT_SECURITY
);

response.addHeader("Content-Security-Policy", headers.contentSecurityPolicy());
headers.xFrameOptions().ifPresent(
        value -> response.setHeader("X-Frame-Options", value)
);
```

`response` trong đoạn tích hợp là response của adapter web thực tế. Ví dụ không yêu cầu thay đổi cấu hình hay dependency của module học tập.

Các CSP enforce đồng thời đều có hiệu lực; một policy mới không nới policy chặt hơn đã được proxy hoặc ứng dụng phát. Vì vậy route đối tác phải được đối soát để không còn một `frame-ancestors 'none'` xung đột từ tầng khác. Code trên không tự gỡ header của proxy và cũng không chứng minh route đã hoạt động đúng qua đường phân phối thật.

`Optional.empty()` trong policy đối tác có nghĩa lớp policy này không phát X-Frame-Options. Nó không bảo đảm các tầng khác không thêm header đó. Tập header cuối cùng phải được kiểm tra theo route và browser contract đã chốt.

## 7. SameSite là lớp bổ sung, không phải quyền nhúng

Cookie session có `SameSite=Lax` hoặc `SameSite=Strict` có thể không được gửi trong iframe cross-site, qua đó giảm các tình huống cần session. Nhưng thuộc tính này không chặn tài liệu bị nhúng, không bảo vệ mọi hành vi không cần đăng nhập và không chặn cùng cách đối với request same-site. [OWASP: Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html#defending-with-samesite-cookies).

### 7.1. Same-site khác same-origin

Hai trang `https://learn.example.com` và `https://promo.example.com` có thể same-site nhưng khác origin. Một subdomain cùng site bị kiểm soát không mặc định được quyền nhúng màn hình tài khoản chỉ vì cookie policy dùng SameSite. Khái niệm site thường xét scheme cùng registered domain, còn origin xét scheme, host và port. [MDN: Site](https://developer.mozilla.org/en-US/docs/Glossary/Site).

Ca nghiệm thu cần bao phủ cả website khác site và sibling subdomain cùng site. Chỉ thử iframe từ một domain hoàn toàn khác rồi thấy trang chưa đăng nhập có thể bỏ sót trường hợp session vẫn tham gia trong ngữ cảnh same-site.

### 7.2. Không hạ cookie policy toàn hệ thống để một iframe chạy được

`SameSite=None` yêu cầu `Secure` trong cơ chế cookie hiện đại; khả năng gửi cookie còn phụ thuộc browser và policy third-party cookie. [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Nếu tích hợp đối tác cần xác thực trong iframe, cần thiết kế riêng scope dữ liệu, session/quyền và phương án khi cookie bị hạn chế. Không đổi cookie quản trị sang cross-site chỉ vì một thẻ giới thiệu khóa học chưa đăng nhập được.

Việc cho phép origin đối tác nhúng và việc cấp dữ liệu cho người dùng trong iframe là hai quyết định khác nhau. Framing allowlist không phải chứng thư xác nhận actor của request có quyền xem một khóa học riêng tư.

## 8. Ngoại lệ nhúng phải là một bề mặt được thiết kế riêng

### 8.1. Tách route nhúng khỏi màn hình có đặc quyền

Nếu LMS đối tác chỉ cần hiển thị thông tin khóa học, cung cấp một route chuyên biệt với dữ liệu và thao tác tối thiểu, chẳng hạn `/embed/course-card`. Không cho phép nhúng toàn bộ dashboard rồi dùng CSS để giấu các nút quản trị.

Một contract mẫu cho route nhúng có thể quy định:

- Chỉ hiển thị thông tin khóa học mà người xem được phép truy cập.
- Không chứa thao tác đổi role, đổi thông tin xác thực, chuyển quyền sở hữu hoặc công bố nội dung.
- Không nhận origin được phép từ query hoặc body; policy lấy từ registry tích hợp đã duyệt.
- Các hành động nhạy cảm cần mở một màn hình top-level có anti-framing policy của chính nó.
- Mỗi tích hợp có owner, origin chính xác, mục đích dữ liệu và thời hạn xem xét lại.

Route nhúng không được làm thay đổi trạng thái chỉ qua một request GET. Một anti-framing response được trình duyệt kiểm tra không thay việc giữ ngữ nghĩa HTTP và kiểm soát thao tác ở server; request có thể đã tới server trước khi trình duyệt quyết định không hiển thị tài liệu trong frame.

### 8.2. Không phản chiếu origin thành quyền nhúng

Header `Origin`, `Referer` hoặc query `parentOrigin` có thể phục vụ những kiểm tra được thiết kế riêng, nhưng không thay thế việc trình duyệt kiểm tra toàn bộ ancestor chain bằng framing policy. Không ghép trực tiếp một giá trị client khai báo vào `frame-ancestors` để tự động cho phép chính nó.

Nếu tích hợp có registry động, origin phải được chuẩn hóa và kiểm tra theo quy tắc đã chốt trước khi được lưu thành cấu hình tin cậy. Chỉ chấp nhận cấu trúc cần thiết, bảo vệ quyền sửa registry và ghi nhận ai phê duyệt. Không cấp wildcard cho subdomain chưa có kiểm kê quyền sở hữu hoặc vòng đời.

Một đối tác được allowlist là một bên được cấp quyền đặt tài liệu vào giao diện của họ. Nếu họ bị xâm nhập hoặc cố tình gây hiểu lầm, `frame-ancestors` không phát hiện ý định xấu của chính origin đã được cho phép. Vì vậy giới hạn quyền của bề mặt nhúng vẫn có giá trị ngay cả khi allowlist chính xác.

### 8.3. Kênh `postMessage` không được trở thành command tổng quát

Nếu frame và parent cần trao đổi kích thước hoặc trạng thái, gửi message tới target origin cụ thể và kiểm tra origin, nguồn window cùng schema khi nhận. Không dùng `*` cho dữ liệu riêng và không coi mọi message từ một parent bất kỳ là lệnh đáng tin. [MDN: Window.postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage).

Một kênh chỉ cần báo chiều cao không nên nhận các lệnh như `deleteCourse` hoặc `changeOwner`. Ngay cả origin đối tác đúng cũng không thay authentication và authorization của thao tác ở server. Việc bổ sung message có tác dụng ghi là một thay đổi quyền cần được xét lại theo contract tích hợp.

## 9. Hành động nhạy cảm cần ngữ cảnh xác nhận rõ

Anti-framing giúp giảm nguy cơ bị thao túng qua frame không được phép. Với thao tác có tác động lớn, thiết kế cần cho người dùng thấy đúng đối tượng và hậu quả trước khi xác nhận.

Ví dụ chuyển quyền sở hữu khóa học có thể yêu cầu:

```text
Mở màn hình xác nhận top-level
→ hiển thị tên và định danh khóa học
→ hiển thị chủ sở hữu hiện tại và người nhận
→ thực hiện xác thực bổ sung nếu policy yêu cầu
→ server kiểm tra quyền và trạng thái hiện tại
→ xác nhận đúng thao tác đã trình bày
```

Một thông điệp “Bạn có chắc không?” nằm trong cùng iframe có thể vẫn bị đặt dưới lớp giao diện gây hiểu nhầm. Nếu dùng bước xác nhận, nó phải gắn với hành động cụ thể và được đặt trong ngữ cảnh mà sản phẩm đã đánh giá.

Với flow xác thực bổ sung, bằng chứng chấp thuận cần được ràng buộc với actor, tenant, đối tượng và loại thao tác cùng thời hạn theo policy. Không dùng một cờ `confirmed=true` do client tự gửi như bằng chứng đã hiển thị hoặc đã được người dùng hiểu đúng.

User activation, một cú nhấp hay việc nút có focus không tự chứng minh ý định nghiệp vụ. Các thao tác nhạy cảm vẫn cần xác định quyền ở thời điểm ghi và xử lý thay đổi trạng thái giữa lúc xem và lúc xác nhận.

Những biện pháp cho frame-based clickjacking cũng không bao phủ mọi UI redress qua cửa sổ top-level, popup hoặc chuyển focus. Nếu mô hình đe dọa của thao tác bao gồm các hình thức đó, phải đánh giá flow xác nhận riêng thay vì công bố rằng anti-framing header đã ngăn mọi trường hợp đánh lừa tương tác.

## 10. Vì sao frame-busting JavaScript không nên là hàng rào chính?

Đoạn code kiểu sau thường được gọi là frame-buster:

```javascript
// Minh họa một cơ chế không nên dùng làm kiểm soát duy nhất.
if (window.top !== window.self) {
  window.top.location = window.self.location;
}
```

Nó phụ thuộc JavaScript được chạy, quyền điều hướng và điều kiện của môi trường frame. Có thể gặp giới hạn browser, sandbox hoặc lỗi khác trước khi cơ chế hoạt động. Vì vậy không lấy đoạn JavaScript này thay cho CSP/X-Frame-Options có hiệu lực trên response.

Thuộc tính `sandbox` do một trang cha hợp lệ đặt cho iframe có thể giới hạn quyền của nội dung con, nhưng một trang cha không đáng tin không có nghĩa vụ giữ cấu hình sandbox mà ứng dụng mong muốn. Nó không tự giải quyết yêu cầu ai được nhúng tài liệu của server.

Tương tự, yêu cầu parent cung cấp một giá trị nhận diện bằng JavaScript không chứng minh toàn bộ ancestor chain đều được phép. Cơ chế ứng dụng bổ sung phải có contract rõ và không xóa bỏ framing policy để tiện nhận message.

Đối với client cũ trong phạm vi hỗ trợ, cần kiểm tra cơ chế thực sự được browser áp dụng. Nếu không thể giữ mức bảo vệ cần thiết cho một tính năng nhạy cảm ở chế độ nhúng, sản phẩm nên cung cấp đường sử dụng top-level phù hợp thay vì ngầm bỏ kiểm soát.

## 11. Phân phối header, redirect và cache

### 11.1. Kiểm tra response cuối cùng được render

Một URL quản trị có thể redirect tới đăng nhập khi session hết hạn. Kiểm tra chỉ response redirect không đủ; tài liệu cuối cùng trong từng trạng thái cũng cần policy phù hợp. Tương tự, trang lỗi do gateway sinh ra có thể mang các header khác trang thành công.

Nếu một frame chỉ hiển thị được trang đăng nhập chưa có session, điều đó chưa chứng minh trang quản trị sau đăng nhập đã được bảo vệ. Các ca kiểm thử phải bao phủ trạng thái session thực tế của mục tiêu.

### 11.2. Chốt owner của framing policy

Ứng dụng, ingress và CDN có thể cùng thêm header. Cần quy định tầng sở hữu policy theo route và cách đọc lại tập header cuối cùng. Không phát hai giá trị X-Frame-Options trái nhau rồi mong browser tự chọn một kết quả an toàn và nhất quán.

Với CSP nhiều policy, không cố mở ngoại lệ đối tác bằng cách thêm một policy rộng hơn trong khi một policy enforce khác vẫn cấm. Cần thay cấu hình của đúng owner cho route ngoại lệ, giữ các giới hạn khác của trang.

Mọi thay đổi policy anti-framing cần có revision, kiểm tra hồi quy và đường phục hồi. Rollback không được vô tình làm mất header hoặc mở lại ngoại lệ origin đã hết hạn.

### 11.3. Không để cache phát policy của tenant khác

Nếu policy nhúng thay theo tenant hoặc tích hợp, response không được dùng nhầm allowlist từ một bản cache khác. Cần cache key hoặc policy không lưu phù hợp với toàn bộ nội dung và cấu hình được chọn.

Một giá trị `parentOrigin` trong request không được trở thành quyền thay cache policy hoặc quyền sửa header. Phân loại route, tenant context và registry đối tác phải xuất phát từ logic server đã kiểm tra.

Đối với trang quản trị cá nhân hóa, policy cache có thể chọn không cho shared cache lưu response. Đối với thẻ khóa học công khai, vẫn cần đảm bảo policy framing của artifact được phát đúng cùng nội dung. Lựa chọn cụ thể phải nằm trong contract phân phối của sản phẩm.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-CJ-01 | Mọi trang có thao tác nhạy cảm được phân loại về quyền nhúng trước khi phát hành | Inventory route–hành động–owner và policy được duyệt |
| SR-CJ-02 | Trang bảo mật tài khoản và quản trị trong phạm vi không được render trong frame | Header enforce cùng ca browser từ origin khác và cùng origin |
| SR-CJ-03 | Trang chỉ cho cùng origin dùng framing policy đúng origin, không dùng khái niệm same-site thay thế | Ca scheme/host/port và sibling subdomain |
| SR-CJ-04 | Ngoại lệ đối tác chỉ áp dụng cho route nhúng chuyên biệt và origin được duyệt | Registry origin, kiểm tra route và các origin ngoài tập |
| SR-CJ-05 | Toàn bộ ancestor chain phải đáp ứng policy; không chỉ kiểm tra parent gần nhất | Ca nested frame với ancestor ngoài cùng không được phép |
| SR-CJ-06 | Header tới được mọi HTML response liên quan qua proxy/CDN, kể cả flow đăng nhập và lỗi | Readback response cuối của các luồng đã inventory |
| SR-CJ-07 | Browser contract xác định rõ CSP/XFO fallback; không dùng ALLOW-FROM hoặc meta như hàng rào chính | Ma trận client và ca enforcement thực tế |
| SR-CJ-08 | SameSite được đánh giá như lớp bổ sung; chức năng không phụ thuộc cookie vẫn có framing policy | Ca không session, same-site và cross-site |
| SR-CJ-09 | Hành động nhạy cảm có xác nhận đúng đối tượng/tác động và kiểm tra quyền server theo policy | Ca thao tác trong ngữ cảnh nhúng và ca xác nhận top-level |
| SR-CJ-10 | Request GET dùng hiển thị không gây thay đổi trạng thái nhạy cảm | Kiểm tra contract endpoint và trạng thái sau request |
| SR-CJ-11 | Cache hoặc cấu hình theo tenant không làm lan allowlist sang trang/tenant khác | Ca cache hit/miss với hai tenant có policy khác nhau |
| SR-CJ-12 | Mọi ngoại lệ nhúng có owner, mục đích, phạm vi dữ liệu và ngày xem xét lại | Hồ sơ phê duyệt và ca thu hồi ngoại lệ |

SR-CJ-02 trong ví dụ bao gồm cấm nhúng cả từ cùng origin. Nếu sản phẩm thực sự có chức năng cần cùng-origin frame, phải phân loại đúng route đó và kiểm tra SR-CJ-03; không làm rộng policy cho toàn bộ nhóm quản trị chỉ để một trang hoạt động.

SR-CJ-09 cần mức kiểm soát phù hợp tác động nghiệp vụ. Không bắt mọi thao tác đọc phải có reauthentication; cũng không bỏ bước xác nhận có ngữ cảnh cho thay đổi quyền chỉ vì request đã có CSRF token.

## 13. Thiết kế ca nghiệm thu trên trình duyệt

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được thực thi trong bài học.

### 13.1. Môi trường và fixture phải tạo đúng ngữ cảnh

Chuẩn bị các origin kiểm thử do đội được phép kiểm soát: origin ứng dụng, một origin khác site, một sibling subdomain cùng site và origin đối tác được duyệt. Nếu có nhu cầu nested embedding, thêm một wrapper origin ngoài danh sách cho ca âm.

Trang harness đơn giản chỉ cần thử nhúng tài liệu, không cần overlay hay đánh lừa người dùng thật:

```html
<!doctype html>
<meta charset="utf-8">
<title>Framing policy test</title>
<h1>Kiểm tra tài liệu có được render trong frame không</h1>
<iframe
  src="https://learn.example.com/account/security"
  title="Tài liệu mục tiêu trong môi trường kiểm thử"
  width="800"
  height="500"></iframe>
```

URL là minh họa; ca triển khai sử dụng host và tài khoản thử đã được cấp quyền. Harness cần được phục vụ qua origin có chủ đích, không mặc định dùng file local rồi coi opaque origin của nó tương đương đối tác hoặc sibling subdomain.

### 13.2. Ma trận hành vi

| Ca | Ngữ cảnh thử | Kỳ vọng theo policy mẫu |
| --- | --- | --- |
| J1 | Mở trang quản trị top-level | Trang hoạt động bình thường sau auth |
| J2 | Nhúng trang quản trị từ origin khác | Không render tài liệu quản trị trong frame |
| J3 | Nhúng trang quản trị từ cùng origin | Vẫn bị chặn vì policy của nhóm là none/DENY |
| J4 | Nhúng trang bảo mật từ sibling subdomain same-site | Bị chặn dù cookie có thể tham gia request |
| J5 | Nhúng trang same-origin-only từ đúng origin | Hoạt động nếu parent policy và các điều kiện khác cũng cho phép |
| J6 | Nhúng trang same-origin-only từ khác host hoặc port | Không được coi là cùng origin |
| J7 | Đối tác được duyệt nhúng route course-card | Chỉ bề mặt và dữ liệu được cấp hoạt động |
| J8 | Origin không được duyệt nhúng course-card | Bị chặn theo frame-ancestors |
| J9 | Ancestor ngoài cùng trái policy, parent trực tiếp được phép | Vẫn bị chặn |
| J10 | Session hết hạn, redirect sang login | Tài liệu cuối tuân policy; không suy từ response redirect |
| J11 | Hai tenant có allowlist khác nhau qua cache | Không nhận policy của tenant khác |
| J12 | Thu hồi origin đối tác và phát cấu hình mới | Origin cũ không còn nhúng được trong phạm vi hiệu lực đã chốt |

Với J7, cần kiểm tra cả một trường hợp thành công thật sự. Nếu mọi frame đều thất bại vì DNS, TLS hoặc parent có `frame-src 'none'`, chưa chứng minh policy của child đúng và ngoại lệ hợp lệ hoạt động.

### 13.3. Tránh các kết luận PASS sai

Không dùng việc parent không đọc được DOM cross-origin làm bằng chứng tài liệu không được nhúng: đó có thể chỉ là same-origin policy đang hoạt động. Cũng không lấy riêng sự kiện `iframe.onload` làm kết luận, vì hành vi load/error của frame không trực tiếp chứng minh tài liệu nhạy cảm đã render hay bị framing policy chặn.

Cần kết hợp raw headers của tài liệu cuối, diagnostics của browser, kết quả render và trạng thái chức năng. Nếu browser chặn vì X-Frame-Options thì ghi đúng nguyên nhân; nếu ca muốn kiểm chứng CSP, phải xác định CSP enforce có hiệu lực theo browser contract chứ không suy từ một failure chung.

Thử cả có và không có session phù hợp. Một trang trong frame trống vì cookie bị chặn không đồng nghĩa trang đó có anti-framing policy. Ngược lại, header đã chặn render không hứa rằng server hoàn toàn không nhận request, nên trạng thái nghiệp vụ vẫn phải giữ đúng theo contract GET và quyền của endpoint.

### 13.4. Ca cho thao tác nhạy cảm và tích hợp

Với route nhúng chuyên biệt, xác minh không có UI hoặc kênh message dùng để cấp quyền, đổi tài khoản hay thực hiện hành động ngoài phạm vi. Link sang màn hình nhạy cảm phải dẫn tới flow top-level có policy và quyền riêng phù hợp.

Với bước xác nhận, kiểm tra đối tượng và hành động được server xác nhận có khớp nội dung đã trình bày không. Nếu quyền bị thu hồi hoặc trạng thái khóa học thay đổi giữa hai bước, không được ghi chỉ vì một cờ chấp thuận cũ còn tồn tại.

Nếu dùng postMessage, thêm ca origin đúng nhưng source window không đúng, schema sai và loại message ngoài tập được cấp. Một message được chấp nhận về giao tiếp không tự là bằng chứng người gửi được quyền thực hiện mọi command nghiệp vụ.

### 13.5. Quan sát và kiểm tra hồi quy

Có thể dùng reporting của CSP hoặc telemetry browser theo cơ chế sản phẩm hỗ trợ để phát hiện framing bị chặn. Dữ liệu quan sát phải được giới hạn, xử lý như input không tin cậy và không trở thành nguồn tự động thêm origin vào allowlist.

Regression cần chạy khi thay proxy, CDN, header middleware, trang đăng nhập, route nhúng hoặc browser support matrix. Một thay đổi không liên quan logic khóa học vẫn có thể xóa mất header trên error path hoặc phát thêm một policy xung đột.

## 14. Những giả định dễ làm lệch yêu cầu

**“Có CSRF token là đủ.”** Trang thật có thể tự gửi token hợp lệ khi người dùng bị dẫn dắt bấm vào chính giao diện thật. Giữ CSRF defense và bổ sung framing policy.

**“Cùng site thì đều đáng tin.”** Một sibling subdomain có thể nằm dưới quyền kiểm soát khác hoặc bị xâm nhập. Hãy quyết định quyền nhúng theo origin cụ thể và phạm vi chức năng.

**“Iframe không có cookie thì không còn rủi ro.”** Một số thao tác không cần session, same-site có hành vi khác cross-site và browser có thể áp cookie policy khác nhau. Cookie không thay quyết định ai được nhúng.

**“Cho đối tác nhúng dashboard rồi giấu nút.”** Ẩn nút không giảm quyền server và không làm trang thành bề mặt tích hợp tối thiểu. Cần route, dữ liệu và thao tác dành riêng cho nhu cầu đã duyệt.

**“Chỉ cần kiểm tra Referer.”** Nó không biểu diễn đáng tin cậy toàn bộ ancestor chain và có thể thiếu theo policy. Không thay cơ chế browser bằng việc phản chiếu header hoặc query thành allowlist.

**“CSP nào cũng ngăn clickjacking.”** Policy chỉ có script-src hoặc frame-src chưa chắc có frame-ancestors. Phải kiểm tra đúng directive và chế độ enforce.

**“Header bảo vệ mọi kiểu đánh lừa giao diện.”** Frame-based defense có phạm vi cụ thể. Với popup, chuyển focus hoặc flow top-level nhạy cảm, cần đánh giá thiết kế tương tác riêng.

## 15. Bài tập vận dụng

Một nền tảng có màn hình đổi MFA, trang quản trị khóa học và một thẻ khóa học mà hai LMS đối tác muốn nhúng. Đội sản phẩm đề xuất đặt `ALLOW-FROM` theo query `parentOrigin` cho toàn bộ ứng dụng để giảm công cấu hình.

Hãy thiết kế phương án thay thế với các đầu ra sau:

1. Ma trận route, hành động, quyền nhúng và owner cho ba bề mặt.
2. CSP/XFO tương ứng và policy cho browser không đáp ứng contract nhúng đối tác.
3. Registry origin đối tác có quyền sửa, ngày xem xét và cách thu hồi.
4. Một ca nested ancestor, một ca sibling subdomain và một ca cache theo tenant.
5. Flow xác nhận cho hành động đổi MFA hoặc chuyển quyền quản lý, có ngữ cảnh và kiểm tra server phù hợp.
6. Tiêu chí PASS phân biệt framing policy chặn với lỗi cookie, mạng hoặc same-origin DOM access.

Kết quả cần chỉ rõ ai được đặt tài liệu vào giao diện của mình, bề mặt đó được cấp những hành động nào và bằng chứng nào xác nhận browser thực thi đúng. Chống clickjacking là giữ sự nhất quán giữa quyền nhúng, quyền nghiệp vụ và ý định mà giao diện trình bày cho người dùng.
