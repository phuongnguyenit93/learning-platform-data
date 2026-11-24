# Rò rỉ liên kết khôi phục trong analytics

## 1. Khi một lượt xem trang làm lộ quyền khôi phục

Liên kết khôi phục thường mang một token cho phép tiếp tục một thao tác nhạy cảm: đặt lại mật khẩu, khôi phục MFA hoặc bắt đầu quy trình đăng ký lại passkey sau khi mất thiết bị. Nếu token hoạt động như một **bearer credential**, người sở hữu nó có thể thực hiện quyền mà token cấp trong thời gian còn hiệu lực, trừ khi hệ thống yêu cầu thêm bằng chứng.

Xét liên kết minh họa sau; mọi token trong bài đều là dữ liệu giả:

```text
https://accounts.example.test/recovery/password?token=DEMO_SECRET_NOT_VALID
```

Trang khôi phục dùng chung layout với trang công khai. Layout nạp tag manager và tự động gửi lượt xem:

```json
{
  "event": "page_view",
  "page_location": "https://accounts.example.test/recovery/password?token=DEMO_SECRET_NOT_VALID"
}
```

Ứng dụng chưa hề chủ động gọi một API “gửi token cho bên thứ ba”. Tuy nhiên, SDK đã sao chép URL chứa token vào payload. Dữ liệu có thể tiếp tục đi qua hàng đợi, máy chủ thu thập, kho dữ liệu, dashboard, bản xuất và tài khoản của người phân tích.

Điểm cần bảo vệ là ranh giới giữa **quyền khôi phục tài khoản** và **dữ liệu đo lường**. Người được quyền xem báo cáo chuyển đổi không mặc nhiên được quyền đặt lại mật khẩu hay thay yếu tố xác thực của người dùng.

HTTPS bảo vệ dữ liệu trên đường truyền tới nơi nhận. Nó vẫn chuyển nguyên payload nhạy cảm cho máy chủ analytics nếu ứng dụng gửi payload đó.

## 2. Những đường đi của liên kết vào hệ thống đo lường

| Nguồn thu thập | Dữ liệu có thể bị sao chép | Tình huống thường gặp |
| --- | --- | --- |
| Tự động ghi nhận lượt xem | URL hiện tại, tiêu đề, nguồn giới thiệu | SDK khởi tạo trong layout trước mã xử lý recovery |
| Theo dõi điều hướng SPA | URL cũ, URL mới, trạng thái router | Chuyển sang trang lỗi làm SDK gửi lại URL có token |
| Theo dõi lượt nhấp | `href`, nhãn liên kết, thuộc tính phần tử | Email hoặc trang hỗ trợ chứa liên kết khôi phục |
| Session replay | DOM, thuộc tính, trạng thái biểu mẫu | Token nằm trong input ẩn hoặc thuộc tính HTML |
| Báo lỗi và giám sát hiệu năng | URL, breadcrumb, request body | Handler lỗi đính kèm toàn bộ request để chẩn đoán |
| Thu thập phía máy chủ | Request target, header, tham số | Proxy analytics nhận URL nguyên bản rồi chuyển tiếp |
| Theo dõi click trong email | Địa chỉ đích đầy đủ của liên kết | Nhà cung cấp email bọc recovery URL qua miền theo dõi |

Danh sách này mô tả các điểm cần xem xét theo cách tích hợp thực tế; không phải mọi SDK đều thu thập tất cả các trường trên. Tuy vậy, cấu hình mặc định của một SDK có thể đủ để tạo sự cố. Ví dụ, tài liệu Google Analytics định nghĩa `page_location` là URL đầy đủ của trang, mặc định lấy từ `document.location`; `page_referrer` mặc định lấy từ `document.referrer`. [Nguồn: Google Analytics Configuration](https://developers.google.com/analytics/devguides/collection/ga4/reference/config#page_location).

Một endpoint thu thập nằm trên chính tên miền của ứng dụng vẫn có thể chuyển dữ liệu tới nhà cung cấp khác. Đổi từ third-party endpoint sang first-party proxy chỉ đổi chặng đầu, chưa chứng minh token được loại khỏi payload.

## 3. Phân biệt Referer, payload JavaScript và fragment

### 3.1. Header Referer

Trình duyệt có thể gửi header HTTP `Referer` khi tải tài nguyên hoặc điều hướng. Lượng thông tin phụ thuộc vào referrer policy và quan hệ origin.

Với `strict-origin-when-cross-origin`, một request cùng origin có thể mang đường dẫn và query của trang nguồn; request khác origin qua HTTPS chỉ mang origin. Vì vậy, không nên giả định mọi request analytics khác origin đều tự động nhận toàn bộ token qua header này. Ngược lại, cũng không nên coi một collector cùng origin là an toàn.

`Referrer-Policy: no-referrer` ngăn trình duyệt gửi header nguồn giới thiệu cho các request thuộc phạm vi áp dụng. Chính sách này không lọc các thuộc tính JSON do JavaScript tự tạo. [Nguồn: W3C Referrer Policy, mục 3 và 4](https://www.w3.org/TR/referrer-policy/).

### 3.2. Payload do JavaScript tạo

Đoạn mã sau tự đưa token vào dữ liệu gửi đi:

```javascript
// Ví dụ không an toàn trên trang khôi phục.
navigator.sendBeacon(
  "/telemetry",
  JSON.stringify({
    event: "page_view",
    url: window.location.href
  })
);
```

Header `Referer` có bị loại bỏ hoàn toàn thì thuộc tính `url` trong body vẫn còn. CORS cũng không phải cơ chế che bí mật khỏi một script đang chạy trong trang; script đó đã có thể đọc URL và tạo request theo các khả năng của trình duyệt.

### 3.3. Token trong fragment

Đổi liên kết thành:

```text
https://accounts.example.test/recovery#token=DEMO_SECRET_NOT_VALID
```

có thể giảm một số chỗ xuất hiện của token: fragment không nằm trong request target HTTP gửi tới máy chủ và bị loại khi tạo giá trị header `Referer`. Tuy nhiên, JavaScript trong trang vẫn đọc được `location.hash` hoặc `location.href`. SDK thu thập URL đầy đủ vẫn có thể gửi token. [Nguồn: W3C Referrer Policy, mục 8.4](https://www.w3.org/TR/referrer-policy/#strip-url).

Nếu chọn thiết kế dùng fragment, ứng dụng cần một bước gửi token có kiểm soát tới backend, giữ trang nhận token không có script thu thập và xử lý đầy đủ CSRF, XSS, vòng đời token. Fragment chỉ thay đổi đường truyền dữ liệu; nó không tự tạo một vùng tin cậy cho analytics.

## 4. Vì sao token ngắn hạn vẫn cần được giữ kín

Giả sử token còn hiệu lực trong một khoảng ngắn và chỉ dùng một lần. Analytics nhận token trước khi người dùng hoàn thành khôi phục. Một người hoặc tiến trình có quyền đọc dữ liệu thu thập vẫn có thể giành quyền sử dụng trước.

Ngay cả khi token đã hết hạn tại thời điểm xem báo cáo, dữ liệu đã thu thập có thể:

- Tiết lộ người dùng nào đang khôi phục tài khoản và thời điểm thực hiện.
- Chứa email hoặc định danh nằm kèm token trong URL.
- Bị sao chép sang nhiều kho có thời hạn lưu trữ và quyền truy cập khác nhau.
- Giúp nối các hoạt động nhạy cảm với hồ sơ hành vi hoặc chiến dịch email.

Token một lần, thời hạn hiệu lực và lưu trữ an toàn là các lớp bảo vệ cần có. Chúng không thay thế việc ngăn token đi vào analytics. OWASP khuyến nghị token khôi phục được sinh bằng nguồn ngẫu nhiên an toàn, đủ mạnh, gắn với người dùng và mất hiệu lực sau khi sử dụng. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Trong khôi phục MFA hoặc passkey, cần giữ đúng mục đích của quyền được cấp. Ví dụ, token cho bước xác nhận địa chỉ email không tự động đủ để xóa mọi yếu tố xác thực. Nếu token bị lộ, phạm vi tác động phải bị giới hạn bởi chính sách khôi phục và các bằng chứng bổ sung mà giao dịch yêu cầu.

## 5. Thiết kế trang recovery có ranh giới thu thập riêng

### 5.1. Loại công cụ thu thập khỏi toàn bộ luồng nhạy cảm

Trang nhận liên kết khôi phục nên dùng một shell tối giản riêng, không kế thừa vô điều kiện layout marketing. Loại bỏ tag manager, analytics phía trình duyệt, session replay, quảng cáo và widget không cần thiết khỏi các bước có bí mật hoặc dữ liệu xác minh.

Phạm vi cần bao gồm:

- Trang tiếp nhận liên kết.
- Trang nhập hoặc xác nhận thông tin khôi phục.
- Trang lỗi, hết hạn và liên kết đã dùng.
- Điều hướng nội bộ liên quan, kể cả khi SPA giữ nguyên tài liệu đang chạy.
- Thành phần hỗ trợ và trình báo lỗi được nạp ở cấp ứng dụng.

Việc chỉ bỏ lệnh gửi `page_view` thủ công không dừng được mọi listener hoặc SDK đã khởi tạo. Với một SPA đã nạp công cụ thu thập từ trang trước, chuyển sang một route có nhãn “private” cũng không tự gỡ chúng. Một tài liệu HTML riêng cho recovery giúp ranh giới nạp mã rõ ràng hơn.

### 5.2. Làm sạch URL bằng chuyển trạng thái phía máy chủ

Một phương án kiến trúc là tiếp nhận token ở endpoint chuyên dụng, giữ nó trong trạng thái tạm trên máy chủ rồi chuyển người dùng sang URL sạch:

```mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant R as Dịch vụ recovery
    participant M as Bộ đếm nội bộ
    B->>R: GET /recovery/entry?token=...
    Note over R: Không ghi raw URL/token; không đổi thông tin tài khoản
    R-->>B: Cookie handle tạm + 303 tới /recovery/continue
    B->>R: GET /recovery/continue
    R-->>B: Biểu mẫu tối giản + CSRF token
    B->>R: POST xác nhận tiếp tục
    Note over R: Kiểm tra bằng chứng và chuyển trạng thái nguyên tử
    R->>M: Sự kiện có schema tối giản
```

Cookie ở đây chỉ chứa handle ngẫu nhiên trỏ tới trạng thái tạm, có thời hạn ngắn và thuộc tính `Secure`, `HttpOnly`, `SameSite` phù hợp. Nó chưa phải session đăng nhập đầy đủ. Server không đặt token gốc vào `Location`, HTML, dữ liệu bootstrap hoặc thông báo lỗi.

GET có thể tạo trạng thái tạm được giới hạn tài nguyên, nhưng không nên tự đặt lại mật khẩu, thay MFA hoặc tiêu thụ token chỉ vì liên kết được mở. Trình quét email và công cụ xem trước cũng có thể mở URL. Khi nhận thao tác POST rõ ràng, backend mới áp dụng kiểm tra CSRF, mục đích token, hạn dùng, trạng thái giao dịch và bằng chứng bổ sung; việc tiêu thụ token hoặc đổi sang quyền khôi phục tiếp theo phải được thực hiện nguyên tử.

Phương án này vẫn có điểm cần bảo vệ: request đầu tiên chứa token trong query. CDN, WAF, reverse proxy, tracing và application access log phải có chính sách loại bỏ dữ liệu nhạy cảm trước khi lưu hoặc xuất. Redirect không xóa dữ liệu đã được tầng trước ghi nhận.

### 5.3. Áp dụng header phòng vệ đúng vai trò

Ví dụ phản hồi của một trang recovery không dùng JavaScript:

```http
Cache-Control: no-store
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; script-src 'none'; style-src 'self'; img-src 'self'; connect-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'
```

Đây là ví dụ chính sách cho một trang tối giản, cần điều chỉnh theo tài nguyên thực sự cần thiết. Áp dụng header cho cả phản hồi redirect, trang đích và trang lỗi có liên quan. Backend vẫn cần bảo vệ CSRF cho form.

`no-store` yêu cầu cache không lưu phản hồi; nó không xóa URL khỏi log hoặc lịch sử đã có. CSP giới hạn khả năng nạp và gửi dữ liệu của trang; nếu cho phép một script cùng origin đọc token rồi gửi tới endpoint được phép, CSP không tự phân loại payload đó thành bí mật.

### 5.4. Giới hạn của history.replaceState

```javascript
// Chỉ là biện pháp bổ sung sau khi ứng dụng đã giữ trạng thái hợp lệ.
history.replaceState(null, "", "/recovery/continue");
```

Lệnh này thay địa chỉ hiển thị trong entry lịch sử hiện tại. Nó không thu hồi beacon đã gửi, không sửa bản sao URL SDK đã giữ trong bộ nhớ và không xóa log của request ban đầu.

Nếu script thu thập chạy trước lệnh này, rò rỉ có thể đã xảy ra. Vì vậy, không dùng việc “xóa query thật nhanh khi trang load” làm kiểm soát duy nhất.

## 6. Vẫn đo được hiệu quả recovery mà không gửi liên kết

Thông tin vận hành hữu ích thường là số yêu cầu, thời gian hoàn thành theo nhóm, tỷ lệ hết hạn và kết quả các bước. Có thể tạo các sự kiện này ở backend sau một chuyển trạng thái đã xác định.

Ví dụ payload:

```json
{
  "event": "account_recovery_step",
  "schema_version": 1,
  "step": "proof_verified",
  "method": "email",
  "outcome": "success",
  "duration_bucket": "under_5m"
}
```

Payload này không cần URL đầy đủ, token, email, user ID, nội dung form hay định danh giao dịch recovery. Các giá trị phân loại phải lấy từ tập giá trị cố định do hệ thống định nghĩa.

Một schema allowlist cần giới hạn cả **tên trường** và **giá trị**. Cho phép trường `outcome` nhưng chấp nhận mọi chuỗi vẫn có thể làm lộ bí mật nếu code truyền nguyên thông báo lỗi chứa URL vào trường đó.

Mã giả cho collector chuyên dụng:

```text
receiveRecoveryMetric(input):
    require exact field set:
        event, schema_version, step, method, outcome, duration_bucket

    require event == "account_recovery_step"
    require schema_version == 1
    require step in allowedSteps
    require method in allowedMethods
    require outcome in allowedOutcomes
    require duration_bucket in allowedDurationBuckets

    emit only the validated fields
```

Collector không tự bổ sung raw request URL, cookie, header nguồn, định danh người dùng hoặc body gốc vào bản ghi sự kiện. Nếu từ chối payload, nó ghi mã lỗi theo schema thay vì ghi toàn bộ payload bị từ chối. Tầng thu thập vẫn có thể nhìn thấy metadata mạng như IP, nên cần chính sách giảm thiểu và lưu trữ riêng cho lớp này.

Đối với product analytics, có thể tổng hợp số đếm theo thời gian trước khi xuất. Đối với chống lạm dụng và điều tra bảo mật, dùng kênh audit riêng có kiểm soát truy cập và thời hạn lưu trữ phù hợp. Audit có thể cần định danh nội bộ, nhưng vẫn không cần token hoặc liên kết có khả năng thực thi.

## 7. Cấu hình SDK: cần hiểu phạm vi từng công tắc

Nếu một khu vực ít nhạy cảm hơn của sản phẩm vẫn dùng Google Analytics, `send_page_view: false` kiểm soát lượt xem mặc định của snippet; không nên suy ra rằng mọi loại sự kiện, tag và cơ chế đo lường khác đều ngừng hoạt động. [Nguồn: Google Analytics Configuration, send_page_view](https://developers.google.com/analytics/devguides/collection/ga4/reference/config#send_page_view).

Với recovery, ưu tiên không nạp SDK ở nơi có bí mật. Nếu cần sự kiện từ một trang sạch sau khi hoàn thành, dữ liệu đầu vào phải được tạo từ giá trị đã phê duyệt thay vì sao chép URL hiện tại rồi cố xóa một vài tham số.

Một quy tắc “xóa query của mọi URL” vẫn có thể bỏ sót:

- Token nằm trong path hoặc fragment.
- URL nhạy cảm nằm lồng trong tham số `redirect`, `return_to` hoặc chuỗi JSON.
- Thuộc tính `href` của liên kết và dữ liệu trong DOM.
- Breadcrumb hoặc hàng đợi do SDK khác giữ trước đó.
- Tham số chiến dịch bị gán email hoặc định danh tài khoản.

Không dùng regex xóa riêng `token=` làm lớp bảo vệ cuối cùng. Giảm số nguồn thu thập và phát sinh dữ liệu đo lường từ schema cố định giúp kiểm soát ranh giới rõ hơn.

## 8. Những cách xử lý dễ tạo cảm giác an toàn sai

| Cách xử lý | Giới hạn còn lại |
| --- | --- |
| Chỉ bật HTTPS | Nơi nhận analytics vẫn đọc được payload |
| Chỉ đặt `no-referrer` | JavaScript vẫn có thể gửi URL trong body |
| Chỉ chuyển token sang fragment | Script trong trang vẫn đọc được fragment |
| Chỉ tắt session replay | Lượt xem, theo dõi click và báo lỗi có thể vẫn chạy |
| Chỉ che token trên dashboard | Dữ liệu thô có thể đã vào collector và kho xuất |
| Chỉ xóa token sau khi SDK khởi tạo | SDK có thể đã gửi hoặc xếp hàng dữ liệu |
| Gửi hash token thay cho token | Tạo dấu nối giữa các hệ thống; không cần thiết cho số đếm và có thể nguy hiểm nếu giá trị đó được chấp nhận ở nơi khác |
| Bọc token bằng URL encoding hoặc Base64 | Đây là biểu diễn có thể đảo ngược, không loại bỏ bí mật |
| Dùng tên miền thu thập nội bộ | Collector vẫn có thể lưu hoặc chuyển tiếp payload đầy đủ |

Hash dùng để kiểm tra token trong kho recovery có mục đích khác với một thuộc tính analytics. Không xuất giá trị kiểm tra token hoặc biến thể của nó sang hệ thống báo cáo chỉ để nối các bước trong funnel.

## 9. Email và attribution cũng thuộc ranh giới bảo vệ

Một email giao dịch có thể bị nền tảng gửi thư tự động thay liên kết bằng URL theo dõi lượt nhấp. Khi URL đích chứa recovery token, nền tảng theo dõi có thể nhận quyền truy cập đó trước khi trình duyệt tới ứng dụng.

Với liên kết mang bí mật:

- Tắt click tracking hoặc link rewriting cho đúng loại liên kết theo khả năng của nhà cung cấp.
- Tránh dịch vụ rút gọn liên kết và redirect phục vụ chiến dịch.
- Không nhúng email, token hoặc ID người dùng vào `utm_*`.
- Đo số thư gửi và kết quả recovery từ các sự kiện nghiệp vụ phù hợp, thay vì đưa URL bí mật vào attribution.

Tắt click tracking không loại bỏ vai trò của nhà cung cấp email trong việc chuyển thư, cũng không kiểm soát mọi hệ thống quét thư của người nhận. Thiết kế token và hành vi GET phải chịu được việc liên kết được mở tự động.

## 10. Khi phát hiện token đã đi vào analytics

Xử lý theo cả hai hướng: chặn đường rò rỉ đang hoạt động và giảm khả năng sử dụng các quyền đã lộ.

1. Xác định nguồn gửi và ngừng thu thập ở luồng recovery bị ảnh hưởng, gồm cả tag động và hàng đợi còn giữ dữ liệu.
2. Xác định khoảng thời gian, mục đích token và các đích nhận; tránh sao chép token thật sang ticket, chat hoặc tài liệu điều tra.
3. Vô hiệu hóa token hoặc giao dịch recovery còn hiệu lực trong phạm vi có bằng chứng bị lộ. Không chờ thao tác xóa dữ liệu bên analytics mới thu hồi quyền.
4. Kiểm tra hành vi khôi phục và thay đổi yếu tố xác thực bất thường. Khi xác định có chiếm đoạt tài khoản, áp dụng quy trình ứng phó và thu hồi session phù hợp với tài khoản bị ảnh hưởng.
5. Hạn chế truy cập dữ liệu liên quan, phối hợp xóa hoặc xử lý bản sao tại collector, kho dữ liệu và các đích xuất theo khả năng thực tế.
6. Ghi nhận nguyên nhân, phạm vi và biện pháp khắc phục bằng định danh điều tra nội bộ, không bằng liên kết còn sử dụng được.

Không suy ra rằng mọi tài khoản đều cần đặt lại mật khẩu chỉ từ một cấu hình analytics sai. Quyết định ứng phó cần dựa trên dữ liệu đã đi đâu, token còn quyền gì và có dấu hiệu sử dụng trái phép hay không.

## 11. Ví dụ áp dụng xuyên suốt

Một dịch vụ có ba luồng: đặt lại mật khẩu, yêu cầu khôi phục MFA và đăng ký lại passkey sau khi mất thiết bị. Cả ba từng dùng layout có tag manager.

Thiết kế cải tiến dùng tài liệu recovery riêng, không nạp các công cụ thu thập phía trình duyệt. Endpoint nhận liên kết chuyển sang URL sạch qua trạng thái tạm phía máy chủ; các tầng ingress không lưu bí mật. Backend chỉ phát sự kiện theo schema cố định khi có chuyển trạng thái nghiệp vụ. Mỗi luồng giữ yêu cầu bằng chứng và phạm vi quyền riêng.

Nhờ đó, nhóm sản phẩm vẫn xem được tỷ lệ hoàn thành theo phương thức và các nhóm thời gian, trong khi quyền đọc analytics không kéo theo quyền tiếp tục khôi phục tài khoản. Sự phân tách này cần được duy trì khi thêm công cụ báo lỗi, widget hỗ trợ hoặc cơ chế attribution mới.
