# List-Unsubscribe cho email đăng ký

## 1. Tại sao email đăng ký cần List-Unsubscribe?

Trong ứng dụng **Spring Framework Mail**, một hệ thống thường gửi cả email giao dịch (xác nhận đơn hàng, OTP, thông báo bảo mật) và email **subscription**: bản tin, marketing, nội dung cập nhật sản phẩm hoặc những danh sách mà người nhận chủ động đăng ký theo dõi. Đối với email subscription, người nhận phải có cách đơn giản để **ngừng nhận đúng loại email họ không muốn**.

`List-Unsubscribe` là một header chuẩn của email. Nó cung cấp cho mail client các URI phục vụ yêu cầu hủy đăng ký, giúp client có thể hiển thị tùy chọn unsubscribe ngay trong giao diện thư. Đặc biệt, chuẩn **RFC 8058** định nghĩa cách báo hiệu **one-click unsubscribe** bằng hai header để mail receiver có thể thực hiện một yêu cầu HTTPS POST theo sự đồng ý của người dùng.

~~~text
Người nhận đã đăng ký bản tin
             |
             v
Spring app tạo email subscription
             |
             +-- Nội dung HTML / text
             +-- List-Unsubscribe header
             +-- List-Unsubscribe-Post header
             |
             v
SMTP / email provider (DKIM signing)
             |
             v
Inbox: client có thể hiển thị "Unsubscribe"
             |
             v
HTTPS POST one-click đến endpoint của người gửi
             |
             v
Lưu suppression / ngừng gửi list tương ứng
~~~

Lợi ích:

- Người nhận không phải tìm đường dẫn hủy ở cuối một email dài.
- Các mail client có đủ tín hiệu để hỗ trợ tính năng hủy đăng ký một chạm, tùy chính sách của client.
- Giảm khả năng người nhận bấm “Report spam” khi thực ra chỉ muốn rời danh sách.
- Hệ thống có thể thống nhất trạng thái consent/suppression và ngừng gửi đúng danh sách.
- Hỗ trợ đáp ứng yêu cầu của các nhà cung cấp hộp thư đối với email marketing/subscription, góp phần bảo vệ **deliverability**.

**List-Unsubscribe không phải cách đảm bảo email chắc chắn vào Inbox.** Nó là một phần của thực hành gửi email lành mạnh, bên cạnh consent, SPF/DKIM/DMARC, uy tín domain/IP, tỷ lệ spam complaint, bounce handling và quản lý danh sách người nhận.

## 2. Phân biệt email subscription và email transactional

Không phải email nào gửi từ `JavaMailSender` cũng phải được coi là một bản tin có thể unsubscribe.

| Loại email | Ví dụ | Hành vi hủy đăng ký |
|---|---|---|
| Newsletter / marketing | Bản tin tuần, mã khuyến mại, nội dung tiếp thị | Cần cơ chế unsubscribe rõ ràng, thường hỗ trợ one-click |
| Product updates tùy chọn | Thông tin tính năng mới mà người dùng đăng ký | Có thể tắt theo danh sách/chủ đề |
| Digest tùy chọn | Tổng hợp thông báo mỗi ngày/tuần | Có thể dừng digest mà không ảnh hưởng email khác |
| OTP / password reset | Mã xác thực, link đặt lại mật khẩu | Thường là transactional, không nên cho unsubscribe làm mất luồng bảo mật |
| Purchase receipt | Biên nhận mua hàng, chứng từ theo giao dịch | Thường là transactional, chính sách gửi riêng |
| Security alert | Đăng nhập lạ, thay đổi phương thức xác thực | Không nên bị suppression marketing chặn |

Google phân biệt **subscription messages** và **non-subscription/transactional messages** theo mục đích gửi, không chỉ theo tên template hay địa chỉ From. Một loại “thông báo” vẫn có thể là subscription nếu nó được gửi cho danh sách người đăng ký nhận nội dung tùy chọn.

Vì vậy hãy **phân loại email trước khi compose**:

~~~java
public enum MailCategory {
    SUBSCRIPTION,
    TRANSACTIONAL
}

public record NotificationPolicy(
        MailCategory category,
        String listId,
        boolean supportsOneClick) {
}
~~~

Đây là model do ứng dụng tự định nghĩa. Với bản tin, `listId` phải xác định đúng danh sách người nhận đăng ký; với email transactional, thường không đưa vào suppression marketing và không tùy tiện gắn header List-Unsubscribe giả.

## 3. Ba tiêu chuẩn và tài liệu cần biết

| Nguồn | Vai trò |
|---|---|
| **RFC 2369** | Định nghĩa nhóm header `List-*`, trong đó có `List-Unsubscribe` với URI trong dấu ngoặc nhọn |
| **RFC 8058** | Cách báo hiệu one-click unsubscribe: `List-Unsubscribe-Post`, HTTPS POST và DKIM |
| **Email sender guidelines của provider** | Quy tắc bổ sung về one-click, authentication, thời hạn xử lý và khả năng hiển thị tùy chọn unsubscribe |

Nguồn tham khảo chính thức:

- [RFC 2369 — The Use of URLs as Meta-Syntax for Core Mail List Commands](https://www.rfc-editor.org/rfc/rfc2369.html)
- [RFC 8058 — Signaling One-Click Functionality for List Email Headers](https://www.rfc-editor.org/rfc/rfc8058.html)
- [Google — Email sender guidelines](https://support.google.com/mail/answer/81126?hl=en)
- [Google — Email subscription guidelines](https://support.google.com/mail/answer/15263077?hl=en)

Các yêu cầu của provider có thể thay đổi theo thời gian, loại email và quy mô người gửi. Khi triển khai production cần kiểm tra lại hướng dẫn hiện hành của các mailbox provider mục tiêu.

## 4. Cú pháp List-Unsubscribe theo RFC 2369

Header `List-Unsubscribe` chứa một hoặc nhiều URI, mỗi URI đặt trong dấu `<` và `>`. Nhiều phương án được phân tách bằng dấu phẩy:

~~~mime
List-Unsubscribe: <mailto:unsubscribe@example.com?subject=unsubscribe>
~~~

Hoặc:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/opaque-token>
~~~

Hoặc có nhiều phương án:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/opaque-token>, <mailto:unsubscribe@example.com?subject=unsubscribe>
~~~

Theo RFC 2369, các URI có thứ tự ưu tiên từ trái sang phải; client có thể dùng phương án nó hỗ trợ. Nên dùng **HTTPS URL** cho one-click và có thể cung cấp `mailto:` như phương án khác nếu hệ thống thực sự xử lý được email yêu cầu hủy đăng ký.

**Không chỉ viết một dòng `List-Unsubscribe: unsubscribe@example.com`:** URI trong header phải có cú pháp thích hợp, bao gồm scheme và dấu ngoặc nhọn. Mỗi message nên có một header `List-Unsubscribe`; không tạo các bản sao cùng tên từ nhiều lớp ứng dụng/gateway.

### Hạn chế của mailto

Phương án `mailto:` đòi hỏi hệ thống xử lý yêu cầu qua email. Một số client có thể mở một email mới để gửi yêu cầu; việc này không tương đương one-click HTTPS POST theo RFC 8058. Do đó, **chỉ có mailto không đáp ứng yêu cầu one-click** của các nhà cung cấp yêu cầu RFC 8058.

## 5. One-click theo RFC 8058: hai header đi cùng nhau

Để báo hiệu one-click, thư cần **đồng thời** có:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/f4TzYf4u6K8...>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

`List-Unsubscribe` chứa một HTTPS URI có thể xác định **đúng subscriber và đúng mailing list**. `List-Unsubscribe-Post` có giá trị **chính xác** là `List-Unsubscribe=One-Click`; đây không phải JSON hoặc một URL khác.

Khi người nhận chọn unsubscribe qua giao diện mail client và client thực hiện one-click, phía nhận có thể gọi:

~~~http
POST /u/f4TzYf4u6K8... HTTP/1.1
Host: mail.example.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 26

List-Unsubscribe=One-Click
~~~

RFC 8058 cho phép `application/x-www-form-urlencoded` hoặc `multipart/form-data`; ví dụ trên dùng form-urlencoded. Server cần hiểu đúng request và xử lý unsubscribe **mà không yêu cầu đăng nhập, cookie, CAPTCHA hay bước xác nhận thứ hai**.

Các điều kiện trọng tâm của RFC 8058:

1. Header `List-Unsubscribe` phải chứa một URI **HTTPS**.
2. Header `List-Unsubscribe-Post` phải có đúng cặp khóa/giá trị `List-Unsubscribe=One-Click`.
3. URL phải tự chứa đủ thông tin (thường là opaque token) để xác định list + recipient, không dựa vào session của browser.
4. Email phải có chữ ký **DKIM hợp lệ bao phủ cả hai header**.
5. Endpoint one-click xử lý **POST**, không phải một GET tự động gây thay đổi subscription.
6. Không trả HTTP redirect cho hành động POST one-click.
7. Không yêu cầu thêm thông tin tương tác từ người nhận.

**Chỉ thêm hai header vào message chưa đủ.** Nếu endpoint không xử lý POST, link bị redirect hoặc DKIM không ký đúng, client có thể không hiện nút one-click hoặc unsubscribe không hoạt động.

## 6. One-click POST không được giống GET hủy đăng ký

Một số hệ thống cũ triển khai đường dẫn:

~~~text
GET https://mail.example.com/unsubscribe?email=user@example.com
    -> lập tức xóa user khỏi danh sách
~~~

Cách này dễ gây **unsubscribe ngoài ý muốn**. Các hệ thống bảo mật email có thể tự động truy cập URL trong message để quét liên kết, kiểm tra phishing hoặc tạo preview. Một GET được bot gọi không có nghĩa người nhận thực sự muốn hủy đăng ký.

RFC 8058 giải quyết vấn đề bằng cách tách hành vi:

| Phương thức | Ý nghĩa nên triển khai |
|---|---|
| `GET /u/{token}` | Hiển thị trang thông tin hoặc preference center; **không tự đổi trạng thái** |
| `POST /u/{token}` kèm `List-Unsubscribe=One-Click` | Hủy đúng subscription theo yêu cầu one-click |
| `POST` từ form trên trang quản lý | Xử lý theo workflow tùy chỉnh, kiểm tra hành động rõ ràng |

Ví dụ:

~~~text
Mail security scanner
       |
       v
GET /u/token123
       |
       v
Trang xác nhận / preferences
       |
       +-- KHÔNG thay đổi subscription

Mail client (người nhận đã bấm unsubscribe)
       |
       v
POST /u/token123
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
       |
       v
Ghi trạng thái UNSUBSCRIBED
~~~

Server phải chấp nhận one-click **không có cookie, HTTP Authorization, session hoặc CSRF token do browser tạo**. Nhưng không được bỏ xác thực token trong URL: URL là một **bearer capability** có phạm vi nhỏ, chỉ dùng để thực hiện hành động unsubscribe cho đúng list/recipient. Token đủ khó đoán, được ràng buộc và kiểm tra trên server là lớp bảo vệ chính.

### Có thể dùng cùng URL cho GET và POST không?

Có. Đây là cách phổ biến: GET dẫn tới trang hủy/điều chỉnh tùy chọn, POST với marker one-click thực hiện hành động. Điều cốt lõi là **GET không có side effect** và one-click POST không cần một round-trip/confirmation khác.

### One-click là một hành động hoàn tất, không phải mở trang

Nếu POST chỉ trả về một trang `"Nhấn vào nút Xác nhận để hủy"` mà chưa cập nhật suppression, đó không phải trải nghiệm one-click theo RFC 8058. Trái lại, response `204 No Content` sau khi cập nhật thành công là một lựa chọn phù hợp để client biết request đã được xử lý mà không cần render HTML.

## 7. DKIM phải ký hai header List-Unsubscribe

RFC 8058 yêu cầu email có **ít nhất một chữ ký DKIM hợp lệ**, trong đó danh sách các header được ký (tham số `h=` của `DKIM-Signature`) phải chứa cả:

- `List-Unsubscribe`
- `List-Unsubscribe-Post`

Ví dụ raw header minh họa:

~~~mime
From: newsletter@example.com
To: subscriber@example.net
Subject: Bản tin tháng 11
List-Id: Product Updates <updates.example.com>
List-Unsubscribe: <https://mail.example.com/u/opaque123>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=mail;
 h=from:to:subject:list-id:list-unsubscribe:list-unsubscribe-post;
 bh=...; b=...
~~~

**Đây chỉ là ví dụ cấu trúc**: giá trị `bh=...` và `b=...` không phải chữ ký hợp lệ. Trong production, DKIM được tạo và xác minh bằng hệ thống gửi/provider hoặc thư viện ký chuyên dụng với khóa phù hợp.

### Thứ tự tạo và ký có ý nghĩa

~~~text
Spring tạo MimeMessage
       |
       +-- From/To/Subject
       +-- List-Id
       +-- List-Unsubscribe
       +-- List-Unsubscribe-Post
       +-- Body HTML/text
       |
       v
DKIM signer (mail gateway / provider)
       |
       v
SMTP relay / mailbox provider
~~~

Nếu thêm hai header **sau khi ký DKIM**, chữ ký trước đó không bao phủ chúng hoặc có thể bị vô hiệu hóa. Vì vậy phải bảo đảm chúng được đặt trước bước ký. Nếu gửi qua SMTP provider tự ký DKIM khi nhận message, cần kiểm tra provider thực sự ký hai header này và không xóa/viết lại chúng.

Spring Mail và `MimeMessageHelper` **không tự động cấp DKIM cho domain** chỉ bằng việc gọi `setHeader`. Quyền ký và selector/record DNS thường do email provider hoặc mail gateway cấu hình.

### Kiểm tra raw message ở phía nhận

Khi một mail client không hiện lựa chọn one-click, hãy kiểm tra:

1. Có đúng một header `List-Unsubscribe` và `List-Unsubscribe-Post`.
2. Header List-Unsubscribe có HTTPS URI hoạt động.
3. Header List-Unsubscribe-Post có giá trị chính xác.
4. Có chữ ký DKIM hợp lệ và `h=` bao phủ cả hai header.
5. Provider/gateway có làm mất header trong quá trình relay không.
6. Những điều kiện về uy tín người gửi và chính sách hiển thị của client.

**Có DKIM pass không có nghĩa chắc chắn header đã được ký.** Phải kiểm tra `h=` của chữ ký hợp lệ: nếu DKIM pass nhưng chỉ ký From/Subject mà không ký hai header unsubscribe, điều kiện của RFC 8058 vẫn chưa được đáp ứng.

## 8. Unsubscribe đúng danh sách, không chặn mọi email

Một ứng dụng có thể có nhiều danh sách:

~~~text
Subscriber: user@example.net
    |
    +-- WEEKLY_NEWSLETTER      subscribed
    +-- PRODUCT_UPDATES        subscribed
    +-- PROMOTIONAL_OFFERS     subscribed
    +-- TRANSACTIONAL_RECEIPTS (luồng giao dịch, không thuộc list marketing)
~~~

Khi người nhận dùng one-click từ bản tin tuần, việc đúng thường là:

~~~text
WEEKLY_NEWSLETTER  -> unsubscribed
PRODUCT_UPDATES    -> giữ nguyên
PROMOTIONAL_OFFERS -> giữ nguyên
TRANSACTIONAL_RECEIPTS -> không bị chặn
~~~

RFC 8058 yêu cầu URI có đủ thông tin xác định recipient và list; không có bước hỏi thêm “muốn hủy danh sách nào?”. Do đó **không dùng cùng một unsubscribe URL chung cho mọi list nếu endpoint không phân biệt được danh sách**.

### Dùng List-Id khi có nhiều mailing lists

Header `List-Id` giúp nhận diện danh sách theo định danh ổn định:

~~~mime
List-Id: Weekly Newsletter <weekly.example.com>
List-Unsubscribe: <https://mail.example.com/u/opaque-weekly-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

`List-Id` không thay thế token trong URL. Nó hỗ trợ client/phân loại; endpoint vẫn phải xác định chính xác subscriber và list bằng dữ liệu đáng tin cậy trên server.

Không đặt vào List-Id thông tin cá nhân hoặc token bí mật. ID nên đại diện một **mailing list**, không phải một recipient.

### Preference center và global unsubscribe khác nhau

Một trang preference center có thể cung cấp:

- Tắt riêng bản tin tuần.
- Tắt thông báo cập nhật sản phẩm.
- Tắt toàn bộ email marketing/tùy chọn.
- Chọn tần suất gửi.

Tuy nhiên **one-click từ một email phải tự xử lý được việc rời list liên quan tới email đó**, không bắt người nhận chọn lại trên trang preferences. Nếu tổ chức có tùy chọn global unsubscribe, hãy cung cấp như một lựa chọn riêng có chủ đích và giải thích tác động cho người nhận.

## 9. Vẫn cần liên kết unsubscribe trong nội dung email

Header List-Unsubscribe phục vụ email client, nhưng không phải client nào cũng hiển thị nút unsubscribe trong giao diện. Vì vậy email subscription vẫn nên có **liên kết hủy đăng ký rõ ràng trong body**, cùng thông tin về tên danh sách và cách thay đổi tùy chọn.

Ví dụ HTML:

~~~html
<html lang="vi">
  <body>
    <h1>Bản tin tuần</h1>
    <p>Nội dung mới nhất dành cho người đăng ký.</p>

    <hr>
    <p>
      Bạn nhận email này vì đã đăng ký Bản tin tuần.
      <a href="https://mail.example.com/preferences/opaque-token">
        Quản lý tùy chọn nhận thư
      </a>
      hoặc
      <a href="https://mail.example.com/u/opaque-token">
        Hủy đăng ký bản tin
      </a>.
    </p>
  </body>
</html>
~~~

Ví dụ bản plain text:

~~~text
Bạn nhận email vì đã đăng ký Bản tin tuần.
Hủy đăng ký hoặc điều chỉnh tùy chọn:
https://mail.example.com/u/opaque-token
~~~

Trong trường hợp GET chỉ mở trang và cần người dùng bấm xác nhận, đường dẫn ở body vẫn có thể sử dụng được; nhưng **header one-click sử dụng HTTPS POST** tới endpoint tương ứng và không được yêu cầu bấm thêm. Có thể dùng hai URL khác nhau nếu muốn tách đường dẫn preference center và endpoint POST, miễn tuân thủ semantics và bảo mật.

**Chỉ có một link trong body không đủ thay thế header one-click** đối với những luồng mà nhà cung cấp yêu cầu RFC 8058. Ngược lại, chỉ có header mà không có phương án hủy dễ tìm trong body có thể tạo trải nghiệm kém trên client không hỗ trợ.

## 10. Gmail và yêu cầu đối với subscription senders

Theo hướng dẫn hiện hành của Google, người gửi **hơn 5.000 email/ngày tới tài khoản Gmail cá nhân** thuộc nhóm bulk senders và các email marketing/subscribed cần hỗ trợ one-click unsubscribe. Google mô tả cách triển khai bằng cả `List-Unsubscribe` và `List-Unsubscribe-Post`, đồng thời có các yêu cầu về email authentication và spam rate.

Google cũng hướng dẫn:

- Xử lý và tôn trọng yêu cầu unsubscribe **trong vòng 48 giờ**.
- Xác nhận người dùng thực sự muốn đăng ký nhận nội dung (consent phù hợp).
- Tách địa chỉ gửi các email subscription và non-subscription, khi hợp lý.
- Nhận diện mailing list bằng `List-Id` dễ hiểu hoặc địa chỉ From riêng cho từng subscription list.
- Không gửi tiếp một loại subscription message khi người nhận đã rút lại đăng ký danh sách đó.

Hãy coi 48 giờ là **giới hạn ngoài**, không phải mục tiêu cho hệ thống: quy trình hợp lý là cập nhật suppression ngay khi xử lý POST thành công và áp policy ở thời điểm dispatch. Nếu hệ thống có job đã xếp hàng, phải ngăn chúng tiếp tục gửi sau khi unsubscribe.

Tính năng unsubscribe xuất hiện ở vị trí nào trong giao diện Gmail hoặc provider khác **không hoàn toàn do người gửi quyết định**. Mailbox provider có thể xét xác thực, danh tiếng, lịch sử gửi, loại email và các chính sách của họ trước khi hiển thị tùy chọn.

Đối với các mailbox provider khác, cần kiểm tra chính sách tương ứng thay vì suy luận rằng mọi nơi áp chính xác cùng ngưỡng bulk sender hoặc cùng UI.

## 11. Thiết kế subscription và suppression trong database

Một hệ thống đáng tin cậy không nên coi unsubscribe là “đã nhận POST” rồi chỉ ghi log. Cần có một **trạng thái có thể kiểm tra trước mỗi lần gửi**, được lưu bền vững trong database hoặc nguồn dữ liệu chuyên trách.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mailing_subscription (
    id UUID PRIMARY KEY,
    subscriber_id UUID NOT NULL,
    list_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('SUBSCRIBED', 'UNSUBSCRIBED')),
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    unsubscribed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscriber_id, list_key)
);

CREATE TABLE unsubscribe_token (
    token_hash BYTEA PRIMARY KEY,
    subscription_id UUID NOT NULL
        REFERENCES mailing_subscription(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX unsubscribe_token_subscription_idx
    ON unsubscribe_token(subscription_id);
~~~

Ở đây:

- `subscriber_id` là định danh nội bộ của người nhận.
- `list_key` xác định mailing list, ví dụ `WEEKLY_NEWSLETTER`.
- `status` là trạng thái consent cho **đúng list**.
- `token_hash` dùng để xác định quyền unsubscribe mà không lưu raw token cần gửi trong URL.
- `unsubscribed_at` giúp audit thời điểm xử lý.

Schema chỉ minh họa. Thực tế có thể cần consent source, locale, tenant ID, consent version, double opt-in confirmation, suppression reason và retention. Với tenant-scoped lists, unique constraint phải xét tenant để tránh trộn subscriber của các tổ chức khác nhau.

### Một bảng unsubscribe chưa chắc đủ

Ứng dụng có thể có:

1. Subscription preferences: user muốn nhận loại nội dung nào.
2. Global suppression: email bị bounce nặng, complaint hoặc được yêu cầu chặn toàn bộ quảng cáo.
3. Legal/consent evidence: nguồn và thời điểm người dùng đồng ý.
4. Delivery state: email đã được lên lịch, đã submit, thất bại hay bị bỏ qua.

Chúng không nhất thiết trùng nhau. Ví dụ người dùng rời bản tin tuần không có nghĩa phải chặn email hóa đơn; nhưng một địa chỉ bị đánh dấu không còn hợp lệ có thể cần chặn nhiều loại email để bảo vệ uy tín sender.

### Idempotency khi nhận unsubscribe

One-click POST có thể tới nhiều lần do người dùng bấm lại, hệ thống retry hoặc nhiều client xử lý cùng một message. Lệnh unsubscribe phải **idempotent**:

~~~sql
UPDATE mailing_subscription
SET status = 'UNSUBSCRIBED',
    unsubscribed_at = COALESCE(
        unsubscribed_at, CURRENT_TIMESTAMP),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :subscription_id
  AND status = 'SUBSCRIBED';
~~~

Nếu row đã là UNSUBSCRIBED, thao tác không cần đổi gì thêm. Server vẫn có thể trả phản hồi thành công để tránh người dùng bị mắc kẹt vì một request lặp.

Nếu ứng dụng dùng hệ thống distributed cache, cần đảm bảo cập nhật suppression bền vững xảy ra **trước** khi phản hồi hoàn tất; cache invalidation và các bản sao đọc ở worker phải được thiết kế để tránh tiếp tục gửi do dữ liệu cũ.

## 12. Token one-click: phải xác định đúng người và list, khó đoán

URL trong header `List-Unsubscribe` không nên đơn giản là:

~~~text
https://mail.example.com/u?email=user@example.net&list=NEWS
~~~

Lý do:

- Địa chỉ email nằm trong URL có thể xuất hiện trong request logs, proxy logs hoặc công cụ analytics.
- Người khác có thể sửa email/list để hủy đăng ký thay người khác nếu endpoint không xác thực.
- Một GET scanner hoặc hệ thống tự động có thể vô tình kích hoạt thao tác nếu thiết kế sai.

Một cách phù hợp hơn là tạo **opaque token ngẫu nhiên đủ entropy**. Server lưu ánh xạ token tới đúng `subscription_id`; bên ngoài không thể suy luận email/list từ token:

~~~text
https://mail.example.com/u/ScuNwUewX1kKM8aQ...
                             |
                             v
                         token hash
                             |
                             v
                    subscription_id
                             |
                   +---------+---------+
                   | subscriber_id     |
                   | list_key          |
                   | status            |
                   +-------------------+
~~~

Ví dụ Java tạo token từ 32 byte ngẫu nhiên:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class UnsubscribeTokenGenerator {
    private final SecureRandom random = new SecureRandom();

    public String newToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 byte tạo khoảng 256 bit entropy trước khi encode, phù hợp để chống việc đoán token khi dùng nguồn ngẫu nhiên mật mã. Không sử dụng `java.util.Random` hoặc một mã subscriber tuần tự làm token công khai.

### Chỉ lưu hash của token khi có thể

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public static byte[] hashToken(String token) {
    try {
        return MessageDigest.getInstance("SHA-256").digest(
                token.getBytes(StandardCharsets.US_ASCII));
    } catch (java.security.NoSuchAlgorithmException ex) {
        throw new IllegalStateException(
                "SHA-256 is required by the Java runtime", ex);
    }
}
~~~

Với token ngẫu nhiên mạnh, SHA-256 giúp database không chứa trực tiếp bearer token. Server nhận raw token, tính hash và lookup bằng `token_hash`. **Không log token, kể cả token trong path URL.** Cấu hình access log/reverse proxy cần tránh ghi raw unsubscribe path nếu có thể.

### Một token gắn với phạm vi gì?

Token nên ràng buộc với:

- Một subscriber hoặc địa chỉ đích đã xác minh.
- Một mailing list cụ thể.
- Tenant/campaign policy nếu hệ thống đa tenant.
- Một phiên consent/subscription nếu hệ thống cho phép đăng ký lại sau khi đã hủy.

Token không nên có quyền đổi địa chỉ email, cập nhật profile, truy cập account hoặc hủy các list khác. Nó chỉ có tác dụng **ngừng gửi list được nêu trong email**.

### Token hết hạn và việc đăng ký lại

Không đặt TTL quá ngắn khiến email gửi chậm hoặc thư được mở lại sau nhiều tuần không còn hủy được. Một link unsubscribe trong email cũ vẫn nên có hành vi an toàn và dễ hiểu:

- Nếu subscription đã hủy, trả thành công idempotent.
- Nếu người dùng đã đăng ký lại với **một lần consent mới**, phải quyết định có thu hồi token của đợt cũ để tránh link cũ hủy đăng ký mới.
- Nếu token bị thu hồi, cung cấp lựa chọn điều chỉnh subscription qua workflow an toàn khác nếu thích hợp.

Không nên tự động tái đăng ký user chỉ vì họ mở trang GET. Việc opt-in lại phải có một hành động consent rõ ràng.

## 13. Tạo hai header từ Spring Framework Mail

`MimeMessageHelper` hỗ trợ dựng body và header thông dụng, nhưng các header list như `List-Unsubscribe` và `List-Unsubscribe-Post` có thể được đặt trực tiếp trên `MimeMessage` bằng API Jakarta Mail.

Ví dụ một composer sử dụng sender cố định:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NewsletterMailComposer {
    private final JavaMailSender mailSender;
    private final UnsubscribeLinkService linkService;

    public NewsletterMailComposer(
            JavaMailSender mailSender,
            UnsubscribeLinkService linkService) {
        this.mailSender = mailSender;
        this.linkService = linkService;
    }

    public MimeMessage compose(
            NewsletterRecipient recipient,
            String plainBody,
            String htmlBody) throws MessagingException {

        // recipient là dữ liệu đã được kiểm tra consent/list.
        String unsubscribeUrl =
                linkService.httpsOneClickUrl(recipient.subscriptionId());

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("newsletter@example.com");
        helper.setTo(recipient.email());
        helper.setSubject("Bản tin sản phẩm");
        helper.setText(plainBody, htmlBody);

        // Ghi đúng một giá trị cho mỗi header.
        message.setHeader(
                "List-Id",
                "Product Newsletter <newsletter.example.com>");
        message.setHeader(
                "List-Unsubscribe",
                "<" + unsubscribeUrl + ">");
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click");

        // Chưa gửi; gateway/provider ký DKIM sau khi header đã có.
        return message;
    }
}
~~~

`NewsletterRecipient` và `UnsubscribeLinkService` là các abstraction do ứng dụng xây dựng; `httpsOneClickUrl` phải tạo URL từ base URL **được cấu hình tin cậy**, token hợp lệ và HTTPS, không nhận một URL tùy ý do request truyền vào.

Sau khi compose:

~~~java
MimeMessage message =
        newsletterMailComposer.compose(recipient, plain, html);
mailSender.send(message);
~~~

**Chỉ tạo message cho recipient còn được phép nhận.** Với campaign batch, không xây một MimeMessage rồi thay `To` và unsubscribe URL nhiều lần; mỗi người nhận nên có message và token đúng của họ.

### Vì sao setHeader thay vì addHeader?

`setHeader(name, value)` thay thế giá trị header hiện có cùng tên; `addHeader(name, value)` có thể tạo thêm header trùng. Theo cấu trúc list headers, mỗi mail message nên chỉ có **một** `List-Unsubscribe`. Nếu nhiều lớp trong pipeline cùng thêm header, có thể gây kết quả khó dự đoán và chữ ký DKIM không phù hợp.

Đừng nối tên header vào body HTML:

~~~java
// Không có tác dụng tạo List-Unsubscribe header MIME.
helper.setText(
        "List-Unsubscribe: <https://mail.example.com/u/token>", false);
~~~

Header phải nằm trong MIME headers, không phải trong text/plain hoặc HTML body.

### Cấu hình mailto thêm vào header

Nếu hệ thống có xử lý email gửi tới `unsubscribe@example.com`, có thể cung cấp phương án:

~~~java
message.setHeader(
        "List-Unsubscribe",
        "<" + unsubscribeUrl + ">, "
            + "<mailto:unsubscribe@example.com?subject=unsubscribe>");
~~~

Nếu backend không có listener xử lý `mailto:` thì **đừng công bố URI giả** chỉ để “đầy đủ cú pháp”. Luồng HTTPS one-click vẫn phải hoạt động độc lập.

## 14. Triển khai endpoint one-click với Spring MVC

Endpoint server nhận request `POST` do mail client phát sinh sau khi người nhận chọn unsubscribe. Nó cần trả kết quả mà **không cần đăng nhập hay xác nhận thêm** và phải xử lý đúng token/list.

Ví dụ:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/u")
public class OneClickUnsubscribeController {
    private final UnsubscribeService unsubscribeService;

    public OneClickUnsubscribeController(
            UnsubscribeService unsubscribeService) {
        this.unsubscribeService = unsubscribeService;
    }

    @PostMapping(
            path = "/{token}",
            consumes = {
                MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                MediaType.MULTIPART_FORM_DATA_VALUE
            })
    public ResponseEntity<Void> oneClick(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String marker) {

        if (!"One-Click".equals(marker)) {
            return ResponseEntity.badRequest().build();
        }

        // Chỉ hủy list được token xác thực.
        unsubscribeService.unsubscribeByToken(token);

        // Không redirect sang URL khác và không cần xác nhận.
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{token}")
    public ResponseEntity<String> viewPreferences(
            @PathVariable String token) {
        // Mẫu đơn giản: GET chỉ mô tả hành động.
        // App thực tế có thể render trang preferences.
        return ResponseEntity.ok(
                "Trang hủy đăng ký. GET không thay đổi trạng thái.");
    }
}
~~~

Đây là khung minh họa; `UnsubscribeService` do ứng dụng xây dựng. Trong hệ thống thật, `GET` có thể hiển thị trang có nút xác nhận bằng form, hoặc dẫn vào preference center, nhưng tuyệt đối không làm thay đổi consent khi chỉ được fetch.

### Cần chấp nhận request không có session/cookie

Theo RFC 8058, request one-click không kèm cookie hay HTTP authorization. Vì vậy:

- Route `POST /u/{token}` phải có thể gọi công khai, chỉ dựa vào token có giới hạn quyền.
- Không yêu cầu login, CAPTCHA hay form CSRF token từ một browser session.
- Nếu dùng Spring Security và CSRF protection mặc định, cần **miễn CSRF có mục tiêu** cho đúng endpoint one-click; không tắt CSRF toàn ứng dụng.
- Không đặt endpoint sau một reverse proxy bắt đăng nhập SSO.
- Không yêu cầu redirect HTTP-to-HTTPS từ URL đã công bố. URL trong header phải là HTTPS hợp lệ ngay từ đầu.

Một cấu hình Spring Security 6 minh họa cách chỉ miễn CSRF cho **POST one-click**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Bean
SecurityFilterChain mailSecurityFilterChain(
        HttpSecurity http) throws Exception {

    RequestMatcher oneClickPost = request ->
            "POST".equals(request.getMethod())
            && request.getServletPath()
                    .matches("^/u/[A-Za-z0-9_-]{43}$");

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(oneClickPost).permitAll()
                    .requestMatchers(
                            org.springframework.http.HttpMethod.GET,
                            "/u/**").permitAll()
                    .anyRequest().authenticated())
            .csrf(csrf ->
                    csrf.ignoringRequestMatchers(oneClickPost))
            .build();
}
~~~

Regex trên giả định token được tạo bằng 32 byte Base64URL không padding, dài **43 ký tự**. Nếu token format khác, hãy đổi matcher. Đây là **ví dụ cấu hình**, không phải file security config hoàn chỉnh cho mọi hệ thống; nếu ứng dụng đã có nhiều `SecurityFilterChain`, phải ghép rule vào chain đúng mà không thay thế nhầm các endpoint còn lại. Các API Spring Security có thể thay đổi giữa các phiên bản, cần khớp version dự án.

**Ngoại lệ CSRF được chấp nhận có mục tiêu vì endpoint dùng token khó đoán, phạm vi hẹp và hành động idempotent**. Không mở quyền cho một API thay đổi email, mật khẩu hoặc profile chỉ vì cùng có route chứa token.

## 15. UnsubscribeService: xác thực token và cập nhật suppression bền vững

Controller chỉ nhận request. Logic xác định subscriber/list và đổi trạng thái nằm trong service transaction.

~~~java
import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UnsubscribeService {
    private static final Pattern TOKEN_FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private final UnsubscribeTokenRepository tokens;
    private final MailingSubscriptionRepository subscriptions;

    public UnsubscribeService(
            UnsubscribeTokenRepository tokens,
            MailingSubscriptionRepository subscriptions) {
        this.tokens = tokens;
        this.subscriptions = subscriptions;
    }

    @Transactional
    public void unsubscribeByToken(String token) {
        if (token == null
                || !TOKEN_FORMAT.matcher(token).matches()) {
            return;
        }

        byte[] digest = hashToken(token);
        Optional<UnsubscribeTokenRecord> record =
                tokens.findActiveByHash(digest);

        if (record.isEmpty()) {
            return;
        }

        subscriptions.markUnsubscribed(
                record.get().subscriptionId());
    }

    private static byte[] hashToken(String token) {
        try {
            return java.security.MessageDigest
                    .getInstance("SHA-256")
                    .digest(token.getBytes(
                            java.nio.charset.StandardCharsets.US_ASCII));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", ex);
        }
    }
}
~~~

`UnsubscribeTokenRepository`, `MailingSubscriptionRepository` và `UnsubscribeTokenRecord` là abstraction minh họa. `findActiveByHash` phải lookup token theo hash, kiểm tra trạng thái hiệu lực/tenant/list nếu schema yêu cầu. `markUnsubscribed` thực hiện một `UPDATE` idempotent trong cùng transaction.

Trong ví dụ, token không hợp lệ/không tồn tại vẫn trả `204` thông qua controller. Đây là một lựa chọn để không tạo oracle tiết lộ tài khoản/list qua status code; hệ thống có thể thiết kế phản hồi khác phù hợp nhưng không được xác nhận một thao tác chưa thực hiện là xóa thành công ở các báo cáo vận hành. Log/metrics nội bộ nên phân biệt token invalid và trạng thái đã unsubscribe mà không tiết lộ địa chỉ email.

### Không xác định subscriber bằng HTTP request headers

Không dùng địa chỉ IP, `User-Agent`, cookie, địa chỉ `From` do request tự khai, hoặc một tham số email ngoài body như bằng chứng danh tính subscriber. Với one-click, **toàn bộ ngữ cảnh unsubscribe phải nằm trong URI/token đã được tạo lúc gửi thư**. IP của mail receiver có thể là proxy/shared infrastructure và không đại diện người nhận.

### Idempotency và giao dịch đồng thời

Hai POST đồng thời cho cùng token phải kết thúc ở cùng trạng thái:

~~~text
POST A ---+
          +--> UPDATE subscription SET UNSUBSCRIBED
POST B ---+
          |
          v
Trạng thái cuối: UNSUBSCRIBED
~~~

Unique constraints, transaction và update có điều kiện là công cụ chính; không cần tạo một job unsubscribe trùng cho mỗi POST. Nếu suppression phải đồng bộ sang bên thứ ba, dùng outbox/event để đồng bộ **sau khi cập nhật trạng thái nguồn bền vững**, đồng thời đảm bảo lần gửi tiếp theo vẫn tôn trọng trạng thái nguồn.

## 16. Chặn gửi sau unsubscribe, kể cả email đã được lên lịch

Giả sử ứng dụng tạo sẵn 50.000 job newsletter lúc 08:00; người dùng hủy lúc 08:10; worker vẫn đang gửi job đã được lên lịch lúc 08:30. Nếu chỉ lọc người nhận khi tạo campaign, có thể tiếp tục gửi dù trạng thái subscription đã thay đổi.

~~~text
08:00  Tạo 50.000 mail outbox jobs
08:10  Subscriber X one-click unsubscribe
08:30  Worker xử lý job cũ của X
        |
        +-- Sai: gửi theo snapshot recipient từ 08:00
        |
        +-- Đúng: kiểm tra suppression trước khi submit
                 -> SKIP cho list mà X đã hủy
~~~

Luồng được khuyến nghị:

~~~mermaid
flowchart TD
    A[Campaign / mail outbox job] --> B[Claim job]
    B --> C[Load subscriber + list + suppression]
    C --> D{Vẫn được phép nhận?}
    D -- Không --> E[Mark SKIPPED_UNSUBSCRIBED]
    D -- Có --> F[Render message + List-Unsubscribe]
    F --> G[Rate limit / JavaMailSender.send]
    G --> H[Mark SMTP submission outcome]
~~~

**Kiểm tra tại dispatch time** quan trọng vì consent có thể thay đổi giữa lúc lập lịch và lúc gửi. Nếu hệ thống có nhiều replica và cache, cần chiến lược đồng bộ trạng thái suppression phù hợp để không dựa quá lâu vào bản cache cũ.

### Vẫn tồn tại một khoảng race không thể loại bỏ hoàn toàn

Worker có thể kiểm tra subscription còn active, sau đó người nhận hủy đăng ký ngay khi SMTP call đang được thực hiện:

~~~text
Worker: kiểm tra SUBSCRIBED
             |
             +---- Người nhận POST unsubscribe
             |
Worker: SMTP call đã bắt đầu
~~~

Không có cơ chế nào chỉ dựa vào header có thể thu hồi email đã được SMTP server chấp nhận. Hãy giảm khoảng race bằng việc kiểm tra sát thời điểm submit, xử lý suppression nhanh và không giữ các batch snapshot quá cũ. Tránh khóa một row subscription suốt thời gian SMTP network call chỉ để đạt “atomic send”, vì SMTP không tham gia database transaction.

### Không dùng suppression marketing để chặn email bảo mật

Nếu subscriber rời danh sách quảng cáo, email OTP hay thông báo giao dịch vẫn phải tuân theo quy tắc riêng. Hãy phân biệt:

~~~text
mailCategory=SUBSCRIPTION, list=WEEKLY_NEWSLETTER
  -> kiểm tra status của đúng list

mailCategory=TRANSACTIONAL, kind=PASSWORD_RESET
  -> kiểm tra quyền và nhu cầu giao dịch, không dùng status newsletter
~~~

Không có nghĩa email transactional được gửi vô điều kiện: vẫn cần kiểm soát lạm dụng, recipient verification, security policy và các nghĩa vụ liên quan. Chỉ không nên gộp “unsubscribe newsletter” thành “tắt mọi email”.

## 17. Consent và chất lượng danh sách gửi

Một hệ thống có List-Unsubscribe đúng chuẩn vẫn có thể gặp vấn đề deliverability nếu gửi cho người chưa từng đồng ý nhận subscription email.

Quy trình danh sách lành mạnh:

1. Người dùng lựa chọn đăng ký một mailing list cụ thể.
2. Ghi lại thời điểm, nguồn và phiên bản nội dung consent theo chính sách.
3. Với loại đăng ký yêu cầu xác nhận, gửi email xác minh và chỉ kích hoạt khi người dùng xác nhận (**double opt-in**).
4. Chỉ gửi nội dung phù hợp với loại subscription đã đồng ý.
5. Mỗi email chứa thông tin danh sách và cơ chế unsubscribe rõ ràng.
6. Khi nhận one-click POST, cập nhật trạng thái nhanh, ngừng các lần gửi sau.
7. Khi người dùng đăng ký lại, lưu **consent mới**, không tự hồi phục chỉ vì họ mở một email cũ.
8. Xử lý bounce/complaints/suppression theo chính sách riêng.

### Một subscriber có thể có nhiều kênh consent

Ví dụ:

| Kênh | Preference | Kết quả unsubscribe email |
|---|---|---|
| Email newsletter | SUBSCRIBED | Chuyển UNSUBSCRIBED |
| Email promotions | SUBSCRIBED | Không đổi nếu là list khác |
| Push notification | ENABLED | Không đổi |
| SMS marketing | ENABLED | Không đổi |
| Transactional email | Theo hoạt động nghiệp vụ | Không bị newsletter one-click chặn |

Nếu sản phẩm muốn có lệnh “unsubscribe tất cả marketing”, hãy thể hiện rõ phạm vi và cung cấp hành động riêng. One-click từ một list không nên lặng lẽ thay đổi nhiều kênh liên lạc không liên quan.

## 18. Test MIME headers mà không gửi SMTP thật

Trước khi gửi, có thể kiểm tra message do Spring tạo ra có đúng hai header không. Một bài kiểm thử round-trip với Jakarta Mail:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class ListUnsubscribeHeaderTest {
    @Test
    void hasOneClickHeadersAfterMimeRoundTrip() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("newsletter@example.com");
        helper.setTo("subscriber@example.net");
        helper.setSubject("Bản tin tuần");
        helper.setText("Nội dung bản tin", false);

        message.setHeader(
                "List-Unsubscribe",
                "<https://mail.example.com/u/opaque123>");
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click");

        message.saveChanges();
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        message.writeTo(stream);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(stream.toByteArray()));

        assertThat(parsed.getHeader("List-Unsubscribe"))
                .containsExactly(
                        "<https://mail.example.com/u/opaque123>");
        assertThat(parsed.getHeader("List-Unsubscribe-Post"))
                .containsExactly("List-Unsubscribe=One-Click");
    }
}
~~~

Test dùng URL giả để kiểm tra **MIME serialization**, không kiểm tra token có thật hay endpoint HTTP đã triển khai. Việc dùng `MimeMessage.saveChanges()/writeTo` giúp xác nhận header còn tồn tại sau khi tạo raw message.

**Test này không xác minh DKIM**. Chữ ký thường được tạo tại gateway/provider sau khi Spring đã gửi. Để kiểm tra RFC 8058 end-to-end, cần capture raw message **sau khi DKIM được ký** rồi xác minh chữ ký hợp lệ và `h=` có đủ hai header.

### Không assert giá trị token cố định trong production

Trong test unit có thể dùng token cố định giả. Trong code thực tế, URL được tạo theo recipient/list và token ngẫu nhiên. Nên assert cấu trúc URL, danh sách đã chọn và mapping token bằng test repository/service; không làm snapshot test nguyên secret.

## 19. Test endpoint one-click bằng Spring MockMvc

Spring MockMvc có thể kiểm tra hành vi POST/GET mà không cần gửi email thật.

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class OneClickControllerTest {
    @Test
    void postUnsubscribesButGetDoesNot() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service))
                .build();

        String token = "a".repeat(43);

        mvc.perform(get("/u/" + token))
                .andExpect(status().isOk());
        verifyNoInteractions(service);

        mvc.perform(post("/u/" + token)
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("List-Unsubscribe", "One-Click"))
                .andExpect(status().isNoContent());

        verify(service).unsubscribeByToken(token);
    }
}
~~~

Đoạn test này dựa trên controller và service abstraction đã mô tả; nó kiểm tra luồng gọi ở controller, chưa kiểm tra repository hoặc Spring Security filter chain.

Các test khác nên có:

- `POST` với marker thiếu/sai trả `400` và không thay đổi subscription.
- `POST` multipart/form-data với marker hợp lệ được xử lý.
- Token lạ/không hợp lệ không cho phép thay đổi subscriber khác.
- Hai POST giống nhau chỉ giữ trạng thái UNSUBSCRIBED; không tạo hiệu ứng phụ lặp.
- GET và HEAD, nếu được hỗ trợ, **không cập nhật subscription**.
- POST từ client không có cookie/Auth/CSRF token vẫn hợp lệ khi token đúng.
- Endpoint HTTPS không bị redirect trước khi xử lý POST.
- DB write thất bại không được báo thành công rồi lặng lẽ tiếp tục gửi.
- Worker dispatch bỏ qua subscriber đã unsubscribe.
- Token của list A không được dùng để hủy list B.

**Test standalone MockMvc không chạy toàn bộ Spring Security chain.** Cần thêm integration test với security config thật để phát hiện trường hợp one-click POST bị `403 CSRF` hoặc `302 redirect sang login`.

## 20. Chẩn đoán: vì sao nút Unsubscribe không xuất hiện?

Ngay cả khi hệ thống gửi có hai header, người nhận không phải lúc nào cũng thấy nút “Unsubscribe” cạnh tên người gửi. Mail client quyết định việc hiển thị theo chính sách và mức tin cậy của người gửi.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có nút unsubscribe | Thiếu một trong hai header, DKIM hoặc điều kiện phía client | Kiểm tra raw source phía nhận, xác thực và uy tín người gửi |
| Có List-Unsubscribe nhưng không có one-click | Thiếu `List-Unsubscribe-Post` hoặc chỉ có mailto | Đưa HTTPS URI và marker đúng RFC 8058 |
| Header có HTTPS nhưng client không one-click | DKIM không ký hai header | Kiểm tra `h=` và kết quả DKIM verification |
| Bấm unsubscribe trả lỗi 403 | Spring Security CSRF hoặc bắt đăng nhập | Scope ngoại lệ CSRF đúng route, cho public POST có token |
| Bấm unsubscribe trả 404 | URL sai hoặc token không được lưu | Kiểm tra base URL, route, token mapping |
| Bấm unsubscribe trả 405 | Endpoint chỉ có GET | Triển khai POST thực sự |
| Bấm unsubscribe redirect 301/302/307 | Trailing slash, HTTP→HTTPS, SSO hoặc reverse proxy | Công bố HTTPS URL cuối cùng, không redirect one-click POST |
| POST trả 415 | Server không nhận form-urlencoded/multipart | Kiểm tra `consumes`/content type |
| POST trả 400 | Không parse được `List-Unsubscribe=One-Click` | Kiểm tra marker và binding của form |
| HTTP 204 nhưng vẫn nhận bản tin | Chỉ log POST, suppression không được dùng ở dispatch | Kiểm tra DB, cache, outbox và logic send |
| Một list đã hủy làm mất email khác | Global suppression vô tình áp cho mọi category | Tách list-level consent và transactional policy |
| Token của email cũ hủy đăng ký mới | Token scope không gắn phiên subscription | Thiết kế revoke/lifecycle khi subscribe lại |
| Link trong footer hoạt động nhưng one-click không | GET flow hoạt động, POST flow không | Kiểm tra endpoint bằng request POST, không chỉ mở browser |

### Quy trình chẩn đoán từ đầu đến cuối

~~~mermaid
flowchart TD
    A[Không thấy hoặc không dùng được Unsubscribe] --> B[Inspect raw email đã nhận]
    B --> C{Có đúng hai header?}
    C -- Không --> D[Sửa composer/provider header handling]
    C -- Có --> E{HTTPS URL và marker đúng?}
    E -- Không --> F[Sửa URL/cú pháp RFC 8058]
    E -- Có --> G{DKIM hợp lệ và ký cả hai?}
    G -- Không --> H[Sửa thứ tự ký hoặc cấu hình DKIM]
    G -- Có --> I[Thử POST form-urlencoded không có cookie]
    I --> J{POST được xử lý?}
    J -- Không --> K[Kiểm tra Security, route, proxy, Content-Type]
    J -- Có --> L{Subscription đã đổi và worker bỏ qua?}
    L -- Không --> M[Sửa suppression/dispatch/cache]
    L -- Có --> N[Kiểm tra chính sách hiển thị và reputation của client]
~~~

### Header có thể bị nhà cung cấp viết lại

Một email có thể đi qua nhiều lớp:

~~~text
Spring MimeMessage
    |
    v
SMTP submission provider
    |
    v
DKIM signer / outbound gateway
    |
    v
Mail transfer / security gateway
    |
    v
Recipient mailbox provider
~~~

Đừng chỉ xem message trước `JavaMailSender.send` rồi kết luận header ở Inbox là như vậy. Một gateway có thể bổ sung, chuẩn hóa, xóa hoặc viết lại List-Unsubscribe, làm thay đổi DKIM và hành vi của client. Khi điều tra, so sánh **raw MIME trước gửi** và **raw MIME người nhận thực sự thấy**.

## 21. Bảo mật endpoint unsubscribe và dữ liệu cá nhân

### Token là một quyền có phạm vi hẹp

Ai có URL hợp lệ có thể yêu cầu hủy đăng ký list tương ứng. Đây là tính chất có chủ đích của one-click, vì mail receiver không gửi login cookie hoặc HTTP authorization. Do đó phải thiết kế token như một bearer capability:

- Sinh bằng CSPRNG đủ entropy.
- Không dùng email/ID tuần tự làm token dự đoán được.
- Scope tới một subscriber/list và tenant đúng.
- Không trao cho token quyền đọc/đổi thông tin tài khoản.
- Lưu hash hoặc cơ chế xác minh mật mã phù hợp.
- Thu hồi/rebind token khi consent lifecycle yêu cầu.
- Không xuất token ra logs, analytics hoặc exception traces không cần thiết.

### Không làm lộ token khi GET mở trang

Nếu footer link cho phép mở trang GET, browser có thể làm rò URL qua Referer nếu trang tải tài nguyên bên thứ ba. Nên:

- Phục vụ bằng HTTPS với chứng chỉ hợp lệ.
- Đặt header `Referrer-Policy: no-referrer` cho trang quản lý subscription.
- Tránh script/pixel/asset từ bên thứ ba trên trang mang token nhạy cảm.
- Không đưa token vào URL analytics hoặc external navigation.
- Không phản chiếu token lên HTML/JavaScript theo cách tạo XSS.
- Cấu hình access log để loại bỏ/hạn chế URL chứa token.

### Giới hạn yêu cầu để giảm lạm dụng

Endpoint one-click công khai có thể bị quét hoặc gửi nhiều POST. Có thể áp:

- Rate limit ở reverse proxy theo nguồn và hành vi, có ngưỡng phù hợp với các mail receiver hợp lệ.
- Giới hạn độ dài và bộ ký tự của token.
- Một số lượng tối đa các request và kích thước body hợp lý.
- Timeout HTTP/DB để không chiếm tài nguyên vô hạn.
- Monitoring cho tỷ lệ token không hợp lệ và lỗi DB.

**Không dùng CAPTCHA hoặc yêu cầu xác nhận tương tác cho POST one-click.** Chúng mâu thuẫn với mục đích của RFC 8058. Rate limiting cần tránh chặn nhầm các mail client/receiver có thể gửi nhiều yêu cầu từ một IP hoặc vùng IP chung.

### Không dùng unsubscribe như công cụ xác minh email tồn tại

Một endpoint trả:

~~~json
{ "email": "customer@example.net", "subscribed": true }
~~~

cho một URL không được xác thực có thể làm lộ dữ liệu. One-click chỉ cần phản hồi xử lý, không trả email hoặc chi tiết hồ sơ. Với token không tồn tại, phản hồi không nên tiết lộ danh sách hoặc tình trạng người dùng.

### HTTPS và redirect

URL trong header phải là HTTPS thực sự, không phải HTTP rồi chuyển hướng. RFC 8058 yêu cầu sender **không trả redirect cho POST one-click**. Đặc biệt, cấu hình reverse proxy có thể redirect do:

- Thiếu trailing slash hoặc thêm trailing slash.
- Chuyển từ domain cũ sang mới.
- Bắt chuyển qua login/SSO.
- Chuyển HTTP sang HTTPS.
- WAF tạo challenge hoặc bot protection page.

Hãy công bố đúng origin/path cuối cùng và cấu hình proxy để POST chạy trực tiếp, không phải theo redirect.

## 22. Metrics, audit và SLA xử lý unsubscribe

Tính năng hủy đăng ký là một **luồng nghiệp vụ vận hành liên tục**. Không thể chỉ test endpoint một lần rồi bỏ qua. Khi service bị lỗi, người nhận vẫn nhận email, tăng spam complaints và giảm uy tín sender.

Metric đề xuất:

| Metric | Ý nghĩa |
|---|---|
| `unsubscribe_post_total` | Số POST hợp lệ vào endpoint |
| `unsubscribe_success_total` | Số request xử lý thành công |
| `unsubscribe_invalid_token_total` | Số token không xác minh được |
| `unsubscribe_failure_total` | Số lỗi service/DB |
| `unsubscribe_processing_duration` | Thời gian xử lý POST |
| `unsubscribe_to_suppression_lag` | Độ trễ từ request đến trạng thái suppression hiệu lực |
| `subscription_mail_skipped_total` | Số job bị bỏ qua vì đã unsubscribe |
| `subscription_mail_sent_after_optout_total` | Tín hiệu nghi ngờ gửi sau opt-out |
| `subscription_backlog_age` | Tuổi job subscription mail còn chờ |

Các metric label nên là loại danh sách, mã kết quả, môi trường hoặc provider ở mức cardinality thấp. Không dùng email, token hoặc subscriber ID làm metric label.

### Audit event tối thiểu

~~~text
event=subscription_unsubscribed
subscriptionId=8f2b...
listKey=WEEKLY_NEWSLETTER
source=RFC8058_ONE_CLICK
processedAt=2026-11-12T10:00:00Z
result=ALREADY_UNSUBSCRIBED_OR_UPDATED
~~~

Các giá trị là ví dụ. Một sự kiện audit nên có nguồn, thời gian, list và kết quả, nhưng tránh lưu raw unsubscribe token. Khi cần lưu bằng chứng consent theo pháp lý hoặc chính sách, dùng kho dữ liệu được kiểm soát riêng.

### Thời hạn 48 giờ và mục tiêu thực tế

Google yêu cầu/hướng dẫn xử lý unsubscribe của subscription messages trong 48 giờ theo các trang sender/subscription guidelines. Về mặt kỹ thuật, one-click POST có thể cập nhật DB **ngay lập tức**, nên mục tiêu vận hành hợp lý thường là tính bằng giây hoặc phút, không đợi gần hết 48 giờ.

Nếu đồng bộ suppression sang email service provider ngoài, cần theo dõi độ trễ đồng bộ và retry; nhưng hệ thống gửi nội bộ vẫn phải chặn những job đã thấy opt-out, không đợi một batch chạy hằng đêm mới ngừng gửi.

### Cảnh báo hữu ích

- Tỷ lệ HTTP 5xx của endpoint unsubscribe tăng.
- Endpoint chỉ nhận GET, không có POST thành công trong khi vẫn gửi subscription mail.
- Xác thực DKIM của one-click header thất bại sau thay đổi gateway.
- Suppression DB cập nhật nhưng worker vẫn gửi cho list đã hủy.
- Token invalid tăng đột biến sau một deploy tạo URL.
- Email gửi nhầm sau unsubscribe vượt ngưỡng được phép trong chính sách.

## 23. Những anti-pattern thường gặp

### 23.1. Chỉ thêm link trong body và coi như đã có one-click

~~~html
<a href="https://example.com/preferences">Unsubscribe</a>
~~~

Liên kết trong HTML là cần thiết cho trải nghiệm người nhận, nhưng **không thay thế** hai header `List-Unsubscribe` và `List-Unsubscribe-Post` khi provider yêu cầu one-click theo RFC 8058.

### 23.2. Chỉ dùng mailto trong List-Unsubscribe

~~~mime
List-Unsubscribe: <mailto:unsubscribe@example.com>
~~~

Header kiểu RFC 2369 này có thể hữu ích, nhưng không có HTTPS endpoint để mail receiver thực hiện POST. Không đáp ứng one-click theo RFC 8058.

### 23.3. Dùng GET làm hành động unsubscribe ngay

~~~java
@GetMapping("/unsubscribe")
public void unsubscribe(@RequestParam String email) {
    repository.unsubscribe(email);
}
~~~

Mail scanner/prefetch có thể gây hủy ngoài ý muốn. GET chỉ nên hiển thị trang hoặc nội dung không thay đổi trạng thái; one-click thay đổi qua POST có marker.

### 23.4. Một token dùng chung cho tất cả người nhận

Nếu mọi bản tin đều dùng `https://mail.example.com/u/newsletter`, endpoint không có cách nhận biết ai đang hủy mà không hỏi thêm thông tin. Hãy tạo token riêng theo subscription và ánh xạ tới đúng list/recipient.

### 23.5. Bỏ địa chỉ email trực tiếp vào URL mà không bảo vệ

~~~text
https://mail.example.com/u?email=user@example.net&list=NEWS
~~~

URL dễ bị sửa và có thể lộ PII qua logs/proxies. Dùng opaque token đủ entropy hoặc cơ chế ký khó giả mạo, không cho request tự quyết định danh tính subscriber.

### 23.6. One-click POST trả về trang yêu cầu xác nhận lần nữa

Thao tác một chạm phải hoàn tất mà không cần thêm click. Preference center có thể tồn tại riêng, nhưng không được là điều kiện bắt buộc cho RFC 8058 POST.

### 23.7. Chỉ hỗ trợ JSON POST

Một endpoint chỉ nhận:

~~~http
Content-Type: application/json

{"unsubscribe": true}
~~~

không tương thích với request one-click chuẩn sử dụng form encoding. Cần xử lý `List-Unsubscribe=One-Click` với `application/x-www-form-urlencoded` và/hoặc `multipart/form-data` như RFC 8058 nêu.

### 23.8. Thêm header sau khi đã ký DKIM

Lúc đó chữ ký không bao phủ header mới hoặc bị ảnh hưởng; RFC 8058 yêu cầu chữ ký hợp lệ bao phủ hai header. Thêm header **trước khi provider ký**, xác minh raw MIME phía nhận.

### 23.9. Chỉ kiểm tra DKIM pass mà bỏ qua h=

Một chữ ký DKIM pass chưa chắc ký `List-Unsubscribe` và `List-Unsubscribe-Post`. Cần đọc `h=` của chữ ký hợp lệ để xác nhận cả hai.

### 23.10. Chặn mọi email khi hủy một mailing list

Người nhận rời newsletter không đồng nghĩa từ chối hóa đơn, OTP hoặc các list khác. Áp list-scoped consent và chính sách transactional riêng.

### 23.11. Chỉ lọc subscriber lúc tạo campaign

Người dùng hủy sau khi đã enqueue nhưng trước khi gửi sẽ tiếp tục nhận thư. Kiểm tra suppression **sát thời điểm dispatch** và áp chính sách cho job đang chờ.

### 23.12. Ghi nhận POST trong log nhưng không lưu trạng thái

HTTP 204 mà database không đổi sẽ gây gửi tiếp. Endpoint cần cập nhật suppression bền vững, có transaction, error handling và metrics.

### 23.13. Yêu cầu cookie, SSO hoặc CSRF token cho one-click

Mail client không có browser session của người nhận. URL/token là dữ liệu xác thực phục vụ hành động hẹp; công khai đúng endpoint POST và miễn CSRF đúng phạm vi, không mở toàn hệ thống.

### 23.14. Dùng HTTP rồi redirect sang HTTPS

RFC 8058 yêu cầu HTTPS URI và không redirect POST. Hãy công bố URL cuối cùng bằng HTTPS và cấu hình proxy để nhận trực tiếp.

### 23.15. Tự động subscribe lại sau một hoạt động không phải consent

Mở trang quản lý, đăng nhập, mua hàng mới hoặc nhận email transactional không tự đồng nghĩa với đồng ý nhận marketing trở lại. Cần quyết định opt-in rõ ràng và lưu consent mới.

### 23.16. Cho một service nhiều tenant dùng một token scope sai

Token của tenant A không được phép thay đổi subscription của tenant B. Ánh xạ token phải tới một subscription record có tenant/list/subscriber rõ ràng; repository query không được lấy ID do request tự cung cấp làm tiêu chí duy nhất.

## 24. Lộ trình triển khai trong Spring Framework Mail

Nếu hệ thống đã gửi bản tin nhưng chưa có one-click, có thể triển khai theo thứ tự:

1. **Phân loại email:** xác định marketing/subscription khác transactional.
2. **Lập danh sách:** định nghĩa `list_key` và `List-Id` cho từng subscription list.
3. **Đánh giá consent:** subscriber nào thực sự đang đăng ký, nguồn consent và trường hợp cần double opt-in.
4. **Xây nguồn suppression:** lưu SUBSCRIBED/UNSUBSCRIBED bền vững theo subscriber/list.
5. **Tạo token:** CSPRNG, opaque, scope hẹp, lưu ánh xạ/hash và quyết định lifecycle.
6. **Xây HTTPS endpoint:** GET không thay đổi trạng thái; POST nhận marker one-click và xử lý idempotent.
7. **Cấu hình bảo mật:** HTTPS, không session/Auth requirement cho POST, CSRF exemption đúng route, log redaction.
8. **Thêm header khi compose:** List-Unsubscribe, List-Unsubscribe-Post và List-Id trước DKIM signing.
9. **Giữ body link:** footer hủy và preference center rõ ràng trong HTML lẫn text.
10. **Kiểm tra DKIM/provider:** raw MIME phía nhận, `h=` ký đủ hai header.
11. **Kiểm tra dispatch:** suppression áp cả với job đã enqueue và nhiều replica.
12. **Chạy negative tests:** GET, invalid token, wrong marker, duplicate POST, multiple lists, expired consent.
13. **Theo dõi SLA:** POST success, suppression lag, job skipped và gửi sau opt-out.
14. **Triển khai có kiểm soát:** một danh sách thử nghiệm trước, mở rộng sang các danh sách còn lại.

### Bộ tình huống nghiệm thu

| Tình huống | Kết quả mong đợi |
|---|---|
| Người nhận chưa đăng ký list | Không gửi subscription email |
| Email marketing đã compose | Có một cặp header đúng cú pháp |
| Email đã nhận | DKIM hợp lệ ký hai header |
| Người nhận click unsubscribe từ client | POST đúng token/marker, không login hay redirect |
| Bot chỉ GET URL | Không thay đổi subscription |
| POST lặp hai lần | Vẫn một trạng thái UNSUBSCRIBED |
| Token của list A | Chỉ hủy A, không hủy B |
| Email transactional sau hủy newsletter | Vẫn theo policy transactional riêng |
| Campaign job đã enqueue trước unsubscribe | Bị bỏ qua tại dispatch nếu chưa submit |
| Cùng người nhận đăng ký lại hợp lệ | Consent mới và token lifecycle rõ ràng |
| Proxy/WAF được bật | Không chặn POST hoặc ép chuyển hướng ngoài ý muốn |
| User mở email trên client không hỗ trợ nút | Footer link vẫn dùng được |

## 25. Câu hỏi thường gặp

**List-Unsubscribe là gì?** Một MIME header cho mail client biết cách thực hiện hành động hủy đăng ký khỏi mailing list, được định nghĩa trong RFC 2369.

**List-Unsubscribe-Post dùng để làm gì?** Nó báo hiệu one-click theo RFC 8058 khi có giá trị `List-Unsubscribe=One-Click` và được dùng cùng HTTPS URI trong List-Unsubscribe.

**Có bắt buộc gắn cả hai header cho email marketing không?** Với sender/loại email thuộc yêu cầu one-click của các mailbox provider như Gmail, có. Ngoài các yêu cầu cụ thể, triển khai RFC 8058 đầy đủ là thực hành tốt cho subscription mail.

**Chỉ một mailto link có đủ không?** Không cho RFC 8058 one-click. Cần HTTPS URI nhận POST.

**Có cần để người dùng đăng nhập khi hủy không?** One-click POST không được yêu cầu đăng nhập hoặc tương tác thêm. Token trong URL phải được giới hạn phạm vi và đủ khó đoán.

**Có thể dùng cùng URL cho GET footer và POST one-click không?** Có, nếu GET không đổi trạng thái và POST đúng marker thực hiện unsubscribe. Không redirect POST.

**Tại sao một GET không nên tự hủy?** Mail security scanners có thể tự fetch URL, làm người nhận bị unsubscribe ngoài ý muốn.

**Có thể trả `302` sau POST để chuyển về trang cảm ơn không?** Không nên. RFC 8058 yêu cầu không trả HTTPS redirect cho hành động one-click POST. Trả `204` hoặc `200` trực tiếp sau khi xử lý.

**DKIM pass là đủ chưa?** Chưa. Chữ ký DKIM hợp lệ cần bao phủ cả hai header unsubscribe trong `h=`.

**Spring Mail có API riêng cho List-Unsubscribe không?** Có thể dùng `MimeMessage.setHeader(...)` của Jakarta Mail cùng `MimeMessageHelper`. Không đưa hai dòng header vào body.

**Có nên dùng token chứa địa chỉ email không?** Không nên đưa email plaintext vào URL. Opaque token khó đoán làm giảm rủi ro giả mạo và rò dữ liệu; vẫn phải bảo vệ token vì nó có khả năng hủy đăng ký.

**Một token có thể hủy nhiều list?** One-click nên hủy đúng list liên quan tới email. Nếu có tùy chọn global unsubscribe, thiết kế hành động riêng, có phạm vi rõ.

**Hủy newsletter có chặn OTP/receipt không?** Không nên. Email transactional và subscription phải có chính sách khác nhau.

**Có cần xử lý ngay không?** Nên cập nhật suppression ngay khi POST hợp lệ thành công; Google hướng dẫn xử lý unsubscribe trong vòng 48 giờ. Đợi đủ 48 giờ mới xử lý là trải nghiệm kém và tăng rủi ro gửi tiếp.

**Nếu đã gửi thành công nhưng người nhận bấm hủy cùng lúc thì sao?** Không thu hồi được SMTP submission đã accepted. Kiểm tra trạng thái sát thời điểm gửi giúp giảm race cho những email chưa submit.

**Đã có List-Unsubscribe, tại sao Gmail không hiện nút?** Client xét thêm authentication, reputation và các chính sách giao diện. Kiểm tra raw MIME phía nhận, DKIM `h=`, URL/endpoint và các tiêu chí provider.

**Có cần cả List-Id không?** List-Id giúp nhận diện mailing list và thường hữu ích cho subscription messages, nhưng không thay thế hai header RFC 8058.

**Có nên hủy bản tin nếu mail client gửi POST hai lần?** Lệnh unsubscribe cần idempotent. POST lặp phải giữ trạng thái UNSUBSCRIBED, không trả lỗi khiến receiver thử vô hạn.

## 26. Tổng kết

**List-Unsubscribe cho email đăng ký** là sự kết hợp giữa **header MIME chuẩn**, **HTTPS endpoint one-click**, **consent/suppression bền vững** và **chính sách gửi tại thời điểm dispatch**.

Đối với Spring Framework Mail, mô hình cốt lõi:

~~~text
Subscriber đồng ý nhận list
            |
            v
Lưu consent theo subscriber + list
            |
            v
Tạo opaque unsubscribe token
            |
            v
Spring MimeMessage:
  List-Unsubscribe: <https://.../u/token>
  List-Unsubscribe-Post: List-Unsubscribe=One-Click
  List-Id: ...
            |
            v
DKIM signer ký cả hai unsubscribe headers
            |
            v
SMTP / mailbox provider
            |
            v
Mail client POST khi người nhận chọn hủy
            |
            v
Spring endpoint xác thực token
            |
            v
Update UNSUBSCRIBED theo đúng list
            |
            v
Dispatcher không gửi subscription mail tiếp
~~~

Hãy nhớ bốn nguyên tắc:

1. **Header phải đúng RFC 8058:** HTTPS List-Unsubscribe + List-Unsubscribe-Post và DKIM ký cả hai.
2. **POST hoàn tất một chạm:** không login/cookie/confirmation/redirect; GET không tự hủy.
3. **Unsubscribe đúng phạm vi:** subscriber + mailing list, không chặn nhầm email giao dịch.
4. **Suppression phải thực sự ngăn gửi:** cập nhật bền vững và kiểm tra tại dispatch, kể cả job đã được lên lịch.

Khi các lớp này hoạt động thống nhất, unsubscribe trở thành một phần đáng tin cậy của hệ thống gửi email đăng ký, giúp tôn trọng lựa chọn người nhận và duy trì deliverability lâu dài.
