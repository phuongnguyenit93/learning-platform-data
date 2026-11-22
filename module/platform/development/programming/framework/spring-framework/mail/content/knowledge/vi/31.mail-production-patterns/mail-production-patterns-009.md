# Policy xử lý địa chỉ bounce và unsubscribe

## 1. Vì sao hệ thống gửi email production cần một policy riêng?

Trong ứng dụng **Spring Framework Mail**, gửi thư thường bắt đầu bằng **JavaMailSender**, **MimeMessageHelper** và một SMTP provider. Tuy nhiên, một lệnh gửi thành công không chứng minh email đã đến inbox của người nhận, và việc một địa chỉ từng nhận được thư không có nghĩa địa chỉ đó vẫn đồng ý nhận mọi loại thư trong tương lai.

Một hệ thống thực tế cần xử lý hai nhóm tín hiệu khác nhau:

- **Bounce:** phản hồi về việc email không thể chuyển phát hoặc bị trì hoãn. Tín hiệu có thể đến từ SMTP response, Delivery Status Notification (DSN), webhook của Email Service Provider (ESP) hoặc API đối soát.
- **Unsubscribe:** yêu cầu của người nhận muốn ngừng một hoặc nhiều loại email. Yêu cầu có thể đến từ trang tùy chọn, đường dẫn trong nội dung thư, header **List-Unsubscribe**, cơ chế **one-click unsubscribe** hoặc một yêu cầu hỗ trợ được xác minh.

Một policy thiếu chặt chẽ có thể gây ra:

1. Tiếp tục gửi vào địa chỉ chắc chắn không còn hợp lệ, làm xấu chất lượng danh sách và reputation.
2. Gửi email marketing sau khi người nhận đã unsubscribe.
3. Chặn nhầm toàn bộ email quan trọng chỉ vì một lỗi SMTP tạm thời.
4. Tự động suppress người nhận dựa trên một bounce giả mạo.
5. Gửi sai **MAIL FROM/Return-Path** nên không đối chiếu được thông báo bounce.
6. Nhân đôi trạng thái khi ESP gửi lại cùng webhook.
7. Cho phép một request GET do link scanner tạo ra thực hiện unsubscribe ngoài ý muốn.
8. Không kiểm tra suppression ngay trước lúc gửi, khiến email đã lên lịch vẫn được gửi sau khi người nhận đổi lựa chọn.
9. Trộn bounce, spam complaint, unsubscribe và lỗi cấu hình SMTP thành một trạng thái duy nhất, dẫn đến retry sai.

Mục tiêu của bài là xây dựng **policy đủ rõ để thực thi, kiểm thử và vận hành**: mỗi sự kiện có nguồn tin cậy, phạm vi tác động, trạng thái, quyền thay đổi, điều kiện gửi lại và dấu vết audit.

## 2. Bounce và unsubscribe là hai khái niệm khác nhau

| Khía cạnh | Bounce | Unsubscribe |
|---|---|---|
| Nguồn gốc | Hệ thống chuyển phát/ESP/server nhận | Người nhận hoặc thao tác được xác thực thay mặt người nhận |
| Câu hỏi trả lời | Thư có chuyển phát được không? | Người nhận có muốn tiếp tục nhận loại thư này không? |
| Phạm vi | Có thể thuộc một attempt, message hoặc recipient | Thường theo tenant, brand, danh sách hoặc chủ đề |
| Tính thời gian | Có thể đến muộn sau SMTP acceptance | Có hiệu lực theo policy từ khi yêu cầu được ghi nhận |
| Hành động phổ biến | Retry, tạm hoãn hoặc suppress địa chỉ không khả dụng | Ngừng những email thuộc phạm vi đã chọn |
| Có thể tự phục hồi? | Soft bounce có thể hết; hard bounce cần xác minh | Không tự động subscribe lại nếu chưa có ý định hợp lệ |
| Bằng chứng cần lưu | Provider event ID, recipient, mã lỗi, thời gian | Phạm vi, thời gian, phương thức, bằng chứng lựa chọn |

**Một hard bounce không phải một unsubscribe.** Người nhận có thể vẫn mong muốn nhận thư nhưng mailbox bị xóa hoặc sai chính tả.

**Một unsubscribe không phải một hard bounce.** Địa chỉ vẫn tồn tại và có thể nhận email, nhưng người nhận không muốn nhận một loại thư nhất định.

Hai sự kiện có thể cùng áp dụng cho một recipient, vì vậy thiết kế nên giữ **contact deliverability state** và **subscription preference** độc lập, rồi tính quyền gửi bằng một policy tổng hợp.

## 3. Phân biệt ba địa chỉ dễ nhầm trong email

Giả sử một thông điệp:

~~~text
Header From:    news@brand.example
Header Reply-To: support@brand.example
SMTP MAIL FROM: bounce+N100@returns.brand.example
SMTP RCPT TO:   customer@example.net
~~~

Mỗi địa chỉ có chức năng:

| Địa chỉ | Vai trò |
|---|---|
| **Header From** | Danh tính người gửi hiển thị trong email |
| **Reply-To** | Địa chỉ nhận phản hồi thông thường của người đọc |
| **SMTP MAIL FROM** | Envelope sender/reverse-path, nơi hệ thống mail thường gửi thông báo không chuyển phát |
| **RCPT TO** | Địa chỉ nhận ở SMTP envelope; có thể gồm To, Cc, Bcc |
| **Return-Path** | Header thường được thêm khi thư được giao cuối cùng, phản ánh reverse-path đã sử dụng |

Một lỗi thường gặp là thấy từ “bounce address” rồi không biết đang nói đến:

1. **Địa chỉ recipient bị bounce**, ví dụ customer@example.net; hoặc
2. **Địa chỉ nhận báo cáo bounce**, ví dụ bounce+N100@returns.brand.example.

Hai đối tượng hoàn toàn khác nhau. **Suppression policy** thường tác động vào địa chỉ **recipient bị bounce**, không phải vô hiệu hóa toàn bộ mailbox nhận bounce của tổ chức.

### Không tự gắn Return-Path header để thay SMTP envelope

~~~text
message.setHeader("Return-Path", "bounces@example.com")
~~~

không phải cách portable để kiểm soát **SMTP MAIL FROM**. Mail server thường thiết lập hoặc viết lại Return-Path khi giao thư; ESP có thể quản lý custom MAIL FROM theo cấu hình account/domain.

Với Jakarta Mail SMTP transport, có thể dùng **mail.smtp.from** ở cấu hình transport khi implementation hỗ trợ. Khi nhiều tenant dùng chung bean **JavaMailSenderImpl**, không sửa property đó theo từng request trong lúc các thread khác đang gửi: rất dễ đưa nhầm bounce address hoặc credential giữa tenant. Dùng sender profile được cấp quyền riêng theo account/tenant hoặc API provider chính thức để thiết lập envelope sender.

## 4. Dòng thời gian SMTP submission và bounce

Một vòng đời điển hình:

~~~text
09:00:00 Spring JavaMailSender.send(...)
           |
           v
09:00:01 ESP SMTP endpoint trả 250 Accepted
           |
           v
09:00:02 Ứng dụng ghi SUBMITTED
           |
           v
09:02:00 ESP thử chuyển thư tới mail server đích
           |
           +-- Server đích tạm trả 451 -> deferred/retry
           |
           v
09:20:00 Server đích trả 550 -> failure
           |
           v
09:20:05 ESP phát bounce webhook hoặc DSN
           |
           v
09:20:06 Inbound event handler ghi recipient BOUNCED
           |
           v
09:20:07 Policy cập nhật suppression theo mức độ tin cậy
~~~

Lệnh **send(...)** đã thành công lúc 09:00:01, nhưng delivery thất bại sau đó. Đây không phải mâu thuẫn:

- **SUBMITTED/ACCEPTED** mô tả chặng SMTP đang quan sát.
- **DELIVERED** theo provider cho biết provider ghi nhận delivery event, không nhất thiết người nhận đã đọc hoặc thư đã vào primary inbox.
- **BOUNCED** là kết quả không chuyển phát được ở một chặng sau.
- **DEFERRED** là trạng thái chưa kết thúc, chưa chắc là bounce vĩnh viễn.
- **OPEN/CLICK** nếu ESP cung cấp cũng không phải bằng chứng chuyển phát có độ tin cậy tuyệt đối do nhiều yếu tố bảo vệ quyền riêng tư và tự động quét link.

Vì bounce thường **bất đồng bộ**, chỉ catch **MailSendException** trong Java là chưa đủ để xây suppression list chính xác.

## 5. Phân loại bounce trước khi ra quyết định

| Nhóm | Ví dụ | Cách xử lý tham khảo |
|---|---|---|
| **Hard bounce / invalid mailbox** | Recipient không tồn tại được provider xác nhận | Dừng gửi vào recipient; yêu cầu sửa/xác minh địa chỉ |
| **Soft bounce / temporary** | Mailbox đầy, server tạm unavailable, trả 4xx | Để provider retry/backoff; có thể tạm hoãn |
| **Policy rejection** | Sender domain/reputation/SPF/DKIM/DMARC bị từ chối | Điều tra sender/provider; không tự kết luận recipient sai |
| **Content/size rejection** | Message vượt giới hạn hoặc content bị chặn | Sửa nội dung/attachment/config |
| **Provider throttling** | Quota/tốc độ gửi vượt giới hạn | Backoff và giảm throughput, không suppress recipient |
| **Unknown/ambiguous** | Thiếu đủ thông tin hoặc kết quả mâu thuẫn | Giữ sự kiện và đối soát |
| **Spam complaint** | Người nhận báo thư là spam qua feedback loop | Ngừng email thuộc phạm vi policy, thường ưu tiên ngăn gửi marketing |

Không áp dụng công thức:

~~~text
SMTP 5xx = xóa recipient
SMTP 4xx = luôn retry ngay
~~~

Lý do:

- SMTP 5xx có thể phản ánh **sender policy**, authentication, size hoặc reputation, không phải mailbox của recipient đã biến mất.
- SMTP 4xx thường là lỗi tạm thời nhưng retry liên tục có thể làm tình hình xấu hơn hoặc vượt quota.
- Các ESP có taxonomy riêng: **hard**, **soft**, **suppressed**, **blocked**, **deferred**, **complaint**. Nên chuẩn hóa nhưng vẫn giữ raw provider code để điều tra.

Trong policy production, phân loại **mã lỗi + nguồn sự kiện + ngữ cảnh** trước khi suppress.

## 6. Đọc SMTP enhanced status code có ngữ cảnh

Một số mã có thể gặp:

~~~text
550 5.1.1 User unknown
451 4.2.2 Mailbox temporarily full
550 5.7.1 Message rejected by policy
421 4.7.0 Rate limit / temporary deferral
~~~

Ý nghĩa vận hành:

- **5.1.1** thường liên quan địa chỉ recipient/mailbox không tồn tại.
- **4.2.2** thường là vấn đề mailbox/giới hạn tạm thời.
- **5.7.1** có thể liên quan policy hoặc bảo mật, không đủ chứng minh email recipient sai.
- **4.7.x** thường liên quan security/policy/throttling tạm thời.

Đây chỉ là ví dụ cách diễn giải: wording, enhanced code, mã phụ và chi tiết provider có thể khác nhau.

Một schema event nên giữ:

~~~json
{
  "provider": "primary-esp",
  "providerEventId": "evt-901",
  "notificationId": "N100",
  "recipientRef": "R12",
  "eventType": "bounce",
  "classification": "invalid_recipient",
  "smtpCode": "550",
  "enhancedStatus": "5.1.1",
  "occurredAt": "2026-11-12T09:20:00Z"
}
~~~

Object này là **schema chuẩn hóa của ứng dụng**, không phải định dạng webhook bắt buộc của mọi ESP.

## 7. Khi nào suppress ngay, khi nào cần quan sát thêm?

Không có một ngưỡng tuyệt đối áp dụng cho mọi nhà cung cấp và loại email. Một policy có thể bắt đầu bằng:

| Sự kiện | Hành động sơ bộ |
|---|---|
| Hard bounce có bằng chứng mạnh rằng recipient không tồn tại | Suppress recipient cho những luồng gửi liên quan |
| Soft bounce đơn lẻ | Ghi nhận, dùng backoff/ESP retry, chưa suppress vĩnh viễn |
| Soft bounce lặp lại nhiều lần trong một cửa sổ | Tạm hoãn recipient và đánh giá lại theo policy |
| Throttling toàn provider | Điều tiết sender/account thay vì suppress người nhận |
| Policy rejection trên nhiều domain | Kiểm tra sender reputation và DNS/authentication |
| Spam complaint đáng tin | Chặn luồng marketing liên quan ngay theo chính sách |
| Unsubscribe hợp lệ | Áp dụng lựa chọn người nhận cho phạm vi được chỉ rõ |
| Bounce giả mạo hoặc không đối chiếu được notification | Quarantine/ignore policy mutation, ghi audit |

**Không xóa một địa chỉ khỏi tất cả danh sách của mọi tenant chỉ vì nó hard bounce ở một tenant.** Mức cô lập phụ thuộc vào mô hình tài khoản, pháp lý, consent và tính tin cậy của nguồn.

Ngược lại, nếu hệ thống dùng một provider account chung và nhà cung cấp đã đưa địa chỉ vào **account-level suppression**, ứng dụng cần hiểu giới hạn chung đó để không liên tục gọi gửi rồi nhận lỗi.

## 8. Unsubscribe là một lựa chọn có phạm vi

Một người có thể muốn:

- Ngừng **weekly newsletter**, nhưng vẫn nhận hóa đơn.
- Ngừng mọi email **marketing** của một thương hiệu.
- Ngừng mọi email không bắt buộc từ một tenant.
- Giảm tần suất digest thay vì unsubscribe toàn bộ.
- Không nhận reminder về một loại sự kiện cụ thể.

Vì vậy không nên chỉ lưu:

~~~text
email_unsubscribed = true
~~~

cho mọi hoàn cảnh.

Một model rõ nghĩa:

~~~text
tenant_id = tenant-A
recipient_key = R12
scope_type = LIST
scope_key = weekly-newsletter
decision = UNSUBSCRIBED
effective_at = 2026-11-12T09:00:00Z
source = ONE_CLICK_POST
~~~

Hoặc:

~~~text
scope_type = STREAM
scope_key = MARKETING
decision = UNSUBSCRIBED
~~~

**Cần giải thích phạm vi trên giao diện và trong email.** Người dùng nhấn “Hủy nhận bản tin hàng tuần” không nên vô tình mất thông báo hóa đơn, đồng thời hệ thống cũng không nên diễn giải “Ngừng mọi email marketing” thành chỉ hủy một campaign nhỏ.

## 9. Nhóm email và quy tắc ưu tiên

Một taxonomy hữu ích:

| Stream | Ví dụ | Preference policy |
|---|---|---|
| **Marketing/promotional** | Khuyến mại, newsletter, chương trình ưu đãi | Phải tôn trọng consent/unsubscribe áp dụng |
| **Product updates** | Thông tin sản phẩm hoặc nội dung định kỳ | Xem chính sách lựa chọn tương ứng |
| **Transactional** | Xác nhận đơn, hóa đơn, cập nhật giao dịch | Chỉ gửi khi thực sự cần cho nghiệp vụ và đúng quyền |
| **Security/account** | OTP, cảnh báo đăng nhập, thay đổi mật khẩu | Policy riêng với hạn sử dụng/nguy cơ bảo mật |
| **Operational/legal notice** | Thông báo bắt buộc theo hợp đồng/quy định áp dụng | Cần xác định cơ sở pháp lý và nội dung thực tế |

Không thể dựa vào nhãn do code gán **TRANSACTIONAL** để tự miễn tất cả quy tắc. Một email quảng cáo không trở thành transactional chỉ vì được gửi sau khi khách hàng mua hàng.

Với email thật sự bắt buộc, cần quy tắc riêng được xác nhận bởi sản phẩm/pháp lý. **Một địa chỉ hard bounce được xác minh vẫn không thể được làm cho nhận thư chỉ bằng cách gán type=SECURITY**. Khi đó cần kênh dự phòng hoặc yêu cầu người dùng cập nhật địa chỉ.

## 10. Thứ tự đánh giá quyền gửi trước SMTP

Một **send eligibility service** nên tổng hợp nhiều rào chắn, không chỉ xem người nhận có trong suppression list hay không:

~~~text
Notification intent
        |
        v
Authenticated tenant and sender profile
        |
        v
Business event still relevant?
        |
        v
Recipient address valid and verified as required?
        |
        v
Consent and unsubscribe for this stream/list?
        |
        v
Bounce suppression or temporary hold?
        |
        v
Spam complaint / abuse policy?
        |
        v
Deadline + campaign window + quota?
        |
        v
Final admission before JavaMailSender.send(...)
~~~

Một **deny** có thể đến từ nhiều nguồn. Ví dụ recipient đã unsubscribe marketing và cũng hard bounce; nên lưu được **cả hai lý do**, dù API chỉ trả một reason code chính.

Chính sách precedence có thể là:

1. Không đúng tenant/quyền sender: từ chối ngay.
2. Có request unsubscribe hợp lệ trong phạm vi hiện tại: không gửi luồng đó.
3. Có complaint/suppression áp dụng: không gửi theo policy.
4. Business event đã lỗi thời hoặc notification quá hạn: skip/expire.
5. Quota hoặc provider chưa sẵn sàng: defer nếu còn hạn.
6. Chỉ khi đủ điều kiện mới tạo SMTP attempt.

**Thứ tự cụ thể là quyết định sản phẩm**, nhưng không nên để lỗi ưu tiên khiến unsubscribe bị bỏ qua vì quota hoặc vì email đã xếp hàng từ trước.

## 11. List-Unsubscribe header dùng để làm gì?

**List-Unsubscribe** là một header của email dành cho cơ chế rời danh sách nhận thư. Một số mail client/provider có thể hiển thị thao tác hủy nhận thư gần phần thông tin người gửi dựa trên các header này và những tín hiệu khác.

Ví dụ:

~~~text
List-ID: Weekly Offers <offers.brand.example>
List-Unsubscribe: <mailto:unsubscribe+abc@brand.example>,
 <https://mail.brand.example/u/opaque-token>
~~~

Ý nghĩa:

- **mailto:** cho phép người nhận hoặc mail client gửi email tới địa chỉ xử lý unsubscribe.
- **HTTPS URL:** cung cấp endpoint hoặc trang quản lý unsubscribe.
- **List-ID:** giúp nhận diện danh sách; không phải khóa bảo mật.

Không phải mọi provider/mail client sẽ hiện cùng một nút unsubscribe. Việc có header **không bảo đảm** giao diện hộp thư hiển thị một tính năng cụ thể; provider còn có chính sách riêng về reputation, signing và loại traffic.

### Header không thay thế đường dẫn trong nội dung

Với email quảng bá, vẫn nên có một đường dẫn **unsubscribe hoặc preference center** rõ ràng trong nội dung thư theo chính sách và quy định áp dụng. Header phục vụ mail client, còn footer cho phép người đọc chủ động thao tác ngay cả khi client không hỗ trợ List-Unsubscribe.

## 12. One-click unsubscribe và RFC 8058

**One-click unsubscribe** là cơ chế cho phép mail provider gửi **HTTP POST** đến một endpoint HTTPS đã định sẵn để hủy nhận email thuộc danh sách tương ứng, không cần mở một trang yêu cầu thao tác xác nhận bổ sung.

Hai header tiêu biểu:

~~~text
List-Unsubscribe: <https://mail.brand.example/u/TOKEN>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

Khi client/provider hỗ trợ cơ chế này, request có dạng:

~~~http
POST /u/TOKEN HTTP/1.1
Host: mail.brand.example
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
~~~

**TOKEN** đại diện cho một opaque capability có phạm vi và quyền hạn phù hợp; nó không phải email thô của recipient.

Các nguyên tắc:

- **HTTPS** để bảo vệ token trên đường truyền.
- **POST** thực hiện thay đổi trạng thái unsubscribe.
- **GET không được tự unsubscribe**, vì các hệ thống quét liên kết bảo mật có thể truy cập URL bằng GET.
- Endpoint xử lý nhanh, idempotent và không yêu cầu người dùng đăng nhập hoặc hoàn thành form xác nhận.
- Không yêu cầu CAPTCHA hoặc login để hoàn tất cơ chế one-click đã được provider kích hoạt đúng.
- Không dùng HTTP redirect làm bước bắt buộc của one-click POST; xử lý trực tiếp.
- Header one-click phải được triển khai cùng chính sách **DKIM signing** phù hợp. Theo RFC 8058, một chữ ký DKIM hợp lệ phải bao phủ các header List-Unsubscribe và List-Unsubscribe-Post.

**JavaMailSender chỉ giúp tạo/gửi MIME; nó không tự bảo đảm chữ ký DKIM đúng.** Signing thường được thực hiện bởi ESP/gateway hoặc một thành phần ký đã được triển khai và kiểm tra.

## 13. Vì sao GET không được thay đổi trạng thái?

Một số mail client, antivirus gateway hoặc hệ thống chống phishing tự động truy cập liên kết trước khi người dùng click.

Nếu endpoint có hành vi:

~~~text
GET /unsubscribe?email=customer@example.net
   -> set subscribed=false
~~~

thì chỉ cần một link scanner đọc URL là người nhận có thể bị unsubscribed dù họ không hề yêu cầu.

Một thiết kế an toàn hơn:

~~~text
GET /preferences/TOKEN
    -> hiển thị trang lựa chọn
    -> không thay đổi trạng thái

POST /u/TOKEN
    -> one-click unsubscribe
    -> cập nhật list/stream đã được token cấp quyền
~~~

Đường dẫn trong footer có thể mở trang tùy chọn bằng GET và yêu cầu một hành động rõ ràng của người dùng. Nhưng **one-click POST từ mail provider phải hoàn thành unsubscribe mà không cần tương tác thứ hai**.

Không sử dụng cùng một URL GET có side effect cho cả email footer và List-Unsubscribe.

## 14. Token unsubscribe phải là capability có phạm vi hẹp

Một URL không nên là:

~~~text
https://mail.example.com/u?email=person@example.net
~~~

Vì địa chỉ dễ bị đoán, có thể xuất hiện trong logs và không chứng minh request được phép hủy danh sách của người nhận.

Thay vào đó dùng một **opaque random token**:

~~~text
https://mail.example.com/u/6xf...opaque...n2
~~~

Token ánh xạ trong backend tới:

~~~text
tenant_id       = tenant-A
recipient_key   = R1001
list_id         = weekly-offers
scope_type      = LIST
purpose         = ONE_CLICK_UNSUBSCRIBE
issued_at       = ...
revoked_at      = null
~~~

Nguyên tắc thiết kế:

1. Token được tạo bằng **cryptographically secure random generator** với đủ entropy, không dùng số tăng dần.
2. Scope rõ ràng: chỉ được hủy danh sách/stream đã chỉ định, không tự ý thay đổi lựa chọn không liên quan.
3. Không chứa email, tenant ID nhạy cảm hoặc dữ liệu cá nhân ở dạng đọc được trong URL.
4. Lưu **hash/HMAC của token** thay vì lưu token plaintext khi có thể, nhằm giảm hậu quả khi database bị lộ.
5. Đặt thời hạn và chính sách vô hiệu hóa phù hợp với trải nghiệm unsubscribe: một email cũ vẫn có thể được người dùng mở sau nhiều tuần/tháng.
6. Hạn chế quyền của token: dùng cho unsubscribe, không dùng để truy cập tài khoản hoặc xem dữ liệu recipient.
7. Tránh log full URL/token vào access logs và analytics bên thứ ba.
8. Hỗ trợ **idempotency**: nhấn nhiều lần hoặc provider retry không tạo nhiều side effect.

Token unsubscribe là một **bearer capability**: ai có URL có thể gửi yêu cầu hủy trong scope của token. Điều đó phù hợp với nhiều luồng one-click, nhưng phải giới hạn phạm vi và không dùng token này cho các thao tác tăng quyền.

## 15. Ví dụ schema token và subscription preference

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_unsubscribe_token (
    id               UUID PRIMARY KEY,
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    token_hash       BYTEA NOT NULL UNIQUE,
    issued_at        TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    CHECK (scope_type IN ('LIST', 'STREAM', 'BRAND'))
);

CREATE TABLE mail_subscription_preference (
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    decision         VARCHAR(30) NOT NULL,
    decision_at      TIMESTAMPTZ NOT NULL,
    decision_source  VARCHAR(50) NOT NULL,
    version          BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (
        tenant_id, recipient_key, scope_type, scope_key
    ),
    CHECK (
        decision IN ('SUBSCRIBED', 'UNSUBSCRIBED')
    )
);
~~~

Đây là schema ứng dụng minh họa; không phải bảng mặc định của Spring Mail. **token_hash** có thể là HMAC-SHA-256 của token dùng key riêng được bảo vệ. Với token ngẫu nhiên đủ entropy, hash thông thường cũng có thể phù hợp, nhưng cần đánh giá mô hình đe dọa và quy trình rotation.

**Không dùng một row preference duy nhất để làm mất lịch sử consent.** Có thể có bảng **mail_subscription_audit** ghi các chuyển trạng thái, nguồn và thời điểm để đối soát.

### Vì sao có scope type và scope key?

Cùng một recipient có thể:

~~~text
LIST  weekly-offers -> UNSUBSCRIBED
LIST  product-news  -> SUBSCRIBED
STREAM MARKETING    -> UNSUBSCRIBED
~~~

Policy tổng hợp cần áp dụng **cấm ở scope rộng** khi một scope rộng phủ lên scope hẹp. Trong ví dụ, quyết định MARKETING=UNSUBSCRIBED vẫn ngăn gửi weekly-offers và product-news, dù row product-news ghi SUBSCRIBED.

## 16. Ví dụ Spring MVC xử lý one-click POST

Một controller minh họa:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mail/unsubscribe")
public class OneClickUnsubscribeController {

    private final UnsubscribeService service;

    public OneClickUnsubscribeController(
            UnsubscribeService service
    ) {
        this.service = service;
    }

    @PostMapping(
        path = "/{token}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Void> unsubscribe(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String action
    ) {
        if (!"One-Click".equals(action)) {
            return ResponseEntity.badRequest().build();
        }

        // Service xử lý idempotent, chỉ trong scope của token,
        // không nhận recipientId/listId do caller tự khai.
        service.unsubscribeByOneClickToken(token);
        return ResponseEntity.ok().build();
    }
}
~~~

**UnsubscribeService** là service do ứng dụng định nghĩa. Nó cần:

- Tính hash token và tìm record chưa revoked/hết hạn theo policy.
- Chỉ xác định tenant/recipient/scope từ record token.
- Ghi preference **UNSUBSCRIBED** và audit qua transaction.
- Cho phép POST lặp lại mà không thay đổi kết quả hoặc tạo vô hạn audit entries.
- Xử lý token không hợp lệ/hết hạn theo API contract có kiểm soát.
- Không đưa token vào log lỗi, URL tracing hay analytics.

**Không yêu cầu Session cookie/login** trên endpoint one-click dành cho mailbox provider. Token là capability scoped; bảo vệ bằng entropy, HTTPS, validation, throttling và audit.

### Spring Security và CSRF

Nếu ứng dụng sử dụng Spring Security với CSRF mặc định, POST không có CSRF token có thể bị từ chối. Đường one-click cần được cấu hình **ngoại lệ CSRF giới hạn đúng endpoint**, không tắt CSRF trên toàn bộ ứng dụng. Điều này chỉ hợp lý khi endpoint **không xác thực bằng cookie/session của trình duyệt**, không phụ thuộc user session và token URL là căn cứ được cấp quyền.

Các endpoint quản lý preference thông thường có đăng nhập/cookie vẫn phải giữ bảo vệ CSRF và authorization đúng chuẩn.

## 17. Gắn header unsubscribe khi tạo MimeMessage

Ví dụ Spring Mail:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MarketingMailComposer {

    private final JavaMailSender sender;

    public MarketingMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String approvedFrom,
            String recipient,
            String subject,
            String htmlBody,
            String oneClickUrl,
            String mailtoAddress
    ) throws Exception {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setFrom(approvedFrom);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(htmlBody, true);

        message.setHeader(
                "List-Unsubscribe",
                "<" + oneClickUrl + ">, <mailto:"
                        + mailtoAddress + ">"
        );
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click"
        );

        return message;
    }
}
~~~

Giá trị **approvedFrom**, **oneClickUrl** và **mailtoAddress** phải được sinh từ **sender/list profile đã được xác minh**, không nhận chuỗi tùy ý của người dùng để chèn vào header. URI cần HTTPS, token được escape/path-encode đúng cách, domain trong allowlist.

Ở điểm gửi, hệ thống còn phải:

- Kiểm tra consent/unsubscribe trước SMTP.
- Chọn đúng tenant SMTP profile và MAIL FROM.
- Tạo nội dung unsubscribe link trong footer nếu là loại thư yêu cầu.
- Bảo đảm ESP/gateway ký **DKIM** cho các header cần thiết và không làm mất/chỉnh sửa chúng sau khi ký.
- Xác minh mail provider có giữ header và tính năng one-click hoạt động trên email thực tế.

**MimeMessageHelper không tự sinh List-Unsubscribe, không tự quản lý preference, cũng không bảo đảm provider cung cấp one-click UI.**

## 18. Body unsubscribe link và preference center

Một email marketing có thể chứa:

~~~text
Bạn nhận email này vì đã đăng ký thông tin sản phẩm.

Ngừng bản tin này: https://brand.example/preferences/TOKEN
Quản lý các loại thông báo: https://brand.example/preferences/TOKEN
~~~

Trang preference center có thể cho người dùng:

1. Hủy danh sách hiện tại.
2. Hủy toàn bộ marketing.
3. Chọn chủ đề quan tâm.
4. Giảm tần suất nhận digest.
5. Xem lựa chọn đã lưu và thời điểm có hiệu lực.

Không nên dùng cách thiết kế gây cản trở như giấu link, bắt nhập lại địa chỉ đã biết hoặc yêu cầu người dùng đi qua nhiều trang không cần thiết để hủy.

Trang GET chỉ hiển thị trạng thái/form; thao tác thay đổi nên là POST/PUT có xác thực phù hợp. **Trang preference có thể yêu cầu một bước người dùng xác nhận**, nhưng endpoint **one-click HTTP POST** cho mail provider không được phụ thuộc bước xác nhận đó.

## 19. Unsubscribe qua email mailto

Một số hệ thống hỗ trợ:

~~~text
List-Unsubscribe:
 <mailto:unsubscribe+opaque-token@lists.brand.example>
~~~

Khi nhận email tại địa chỉ đó, inbound service:

1. Đọc mailbox/route phù hợp.
2. Trích xuất **opaque token** từ địa chỉ đích theo parser đã kiểm soát.
3. Đối chiếu token với recipient/list/scope.
4. Ghi unsubscribe idempotent.
5. Gửi phản hồi xác nhận nếu policy yêu cầu, tránh tạo mail loop.

**Không tin trường From của email unsubscribe như bằng chứng duy nhất**, vì From có thể giả mạo. Dùng token có phạm vi hẹp và chống abuse; cân nhắc mức xác minh tùy loại thao tác.

Không xử lý một email trả lời bình thường với Subject “unsubscribe” như quyền hủy mọi danh sách của một địa chỉ khác mà không có kiểm tra.

## 20. Webhook preference center và email events cần cùng policy

Một người có thể unsubscribe qua nhiều đường:

~~~text
Email one-click POST ----------+
Preference center ------------+---> SubscriptionPolicyService
Inbound mailto unsubscribe ---+             |
Customer support verified ----+             v
                                Durable preference + audit
                                              |
                                              v
                                  Eligibility before send
~~~

Không nên để **HTTP endpoint** ghi vào một bảng, **support CRM** ghi vào bảng khác còn **scheduler** chỉ đọc một trong hai.

Tất cả nguồn phải được chuẩn hóa thành cùng một quyết định quyền gửi, với:

- Scope.
- Thời gian có hiệu lực.
- Nguồn và mức tin cậy.
- Idempotency key.
- Actor/automation source phù hợp.
- Audit và phiên bản policy.

Nếu nhiều hệ thống lưu preference, cần xác định **source of truth**, cơ chế đồng bộ và cách xử lý conflict. Không mặc định dữ liệu bị cache ở worker đã cập nhật ngay khi người nhận vừa unsubscribe.

## 21. Nhận bounce qua ESP webhook

Nhiều hệ thống production sử dụng webhook của ESP để nhận:

~~~text
SMTP accepted
      |
      v
ESP delivery pipeline
      |
      +-- delivered
      +-- deferred
      +-- bounced
      +-- complained
      |
      v
Webhook endpoint của ứng dụng
      |
      v
Verify -> dedup -> persist -> normalize -> policy
~~~

Một pipeline nên:

1. Xác minh **chữ ký hoặc phương thức xác thực webhook** đúng contract provider.
2. Xác minh timestamp/replay protection khi provider hỗ trợ.
3. Giới hạn request size và validate schema/field types.
4. Chỉ tin **providerEventId** và **message mapping** sau khi xác thực.
5. Lưu raw event/normalized event an toàn theo retention.
6. Deduplicate bằng event ID ổn định hoặc cơ chế thay thế được thiết kế.
7. Đối chiếu provider message ID và recipient với notification attempt đã gửi.
8. Áp dụng state transition và suppression policy theo kết quả.
9. Trả HTTP response nhất quán để provider retry khi cần.

Không nhận header:

~~~text
X-Provider-Event: hard_bounce
~~~

như bằng chứng tin cậy nếu caller ngoài Internet có thể tự tạo header đó.

### Xác minh chữ ký trên raw HTTP body

Nếu provider dùng HMAC trên **raw bytes** của request, phải giữ raw body nguyên vẹn để verify. Parse thành JSON rồi serialize lại trước khi tính chữ ký có thể làm thay đổi whitespace/field order và gây mismatch. Quy trình verify cần dùng API và secret rotation theo contract provider.

Nếu webhook xác thực thất bại, không được dùng dữ liệu đó để thay đổi suppression hoặc unsubscribe.

## 22. Nhận DSN qua mailbox bounce

Nếu ESP không cung cấp webhook hoặc cần đối soát, có thể đọc **Delivery Status Notification** từ mailbox chuyên nhận bounce bằng **IMAP/POP3**.

Một DSN chuẩn có thể có cấu trúc:

~~~text
multipart/report; report-type=delivery-status
  |
  +-- text/plain
  |
  +-- message/delivery-status
  |
  +-- message/rfc822-headers (optional)
~~~

Phần delivery-status có thể chứa:

~~~text
Final-Recipient: rfc822; customer@example.net
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Đừng parse DSN chỉ bằng:

~~~text
Subject contains "Undelivered Mail"
~~~

vì Subject là dữ liệu có thể bị giả mạo. Nên nhận diện **MIME report structure**, các trường DSN và correlation với notification đã gửi. Nhiều DSN có thể thiếu trường hoặc chứa nội dung khác nhau tùy server.

Một pipeline:

~~~text
Bounce mailbox
     |
     v
IMAP/POP3 receiver
     |
     v
MIME/DSN parser with size limits
     |
     v
Correlation token / recipient matching
     |
     v
Event dedup + durable store
     |
     v
Bounce classification + suppression policy
~~~

Không tự chuyển tất cả mail gửi vào mailbox bounce thành hard bounce. Địa chỉ bounce có thể bị spam hoặc nhận backscatter; một email nhìn giống DSN nhưng không khớp notification outbound phải được quarantine/ignore theo policy.

### VERP và correlation

**Variable Envelope Return Path (VERP)** là kỹ thuật mã hóa một định danh vào địa chỉ MAIL FROM:

~~~text
bounce+tenantA.N100.R12@returns.brand.example
~~~

Khi DSN đến, hệ thống có thể ánh xạ token tới **notification-recipient**. Token nên opaque/ký bảo vệ để hạn chế giả mạo và không chứa dữ liệu cá nhân đọc được. Không kết luận DSN hợp lệ chỉ vì nó có một chuỗi giống token; phải kết hợp nguồn, cấu trúc và mapping.

Khi dùng ESP, provider có thể tự quản lý MAIL FROM/VERP, nên không giả định ứng dụng có thể tùy ý quyết định Return-Path trong mỗi thư.

## 23. Idempotency khi webhook hoặc DSN gửi lại

Một provider có thể gửi lại cùng webhook nếu:

~~~text
T0   Provider POST event E100
T1   Ứng dụng verify và commit database
T2   HTTP response bị timeout trên đường mạng
T3   Provider retry POST event E100
~~~

Nếu mỗi HTTP request tăng số bounce hoặc ghi một suppression mới, hệ thống sẽ đếm trùng. Cần phân biệt:

- **Webhook request count:** mọi lần HTTP request đến.
- **Unique verified provider events:** chỉ những event ID mới và hợp lệ.
- **Unique bounced notification-recipient:** chỉ những notification-recipient được kết luận bounced theo policy.
- **Active suppressed recipients:** số recipient hiện đang bị cấm gửi theo scope.

Các chỉ số không thể thay nhau.

Ví dụ unique key:

~~~sql
CREATE TABLE mail_provider_event (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id          VARCHAR(100) NOT NULL,
    provider_account_id  VARCHAR(120) NOT NULL,
    provider_event_id    VARCHAR(300) NOT NULL,
    provider_message_ref VARCHAR(500),
    recipient_key        VARCHAR(240),
    event_type           VARCHAR(80) NOT NULL,
    event_at             TIMESTAMPTZ,
    ingested_at          TIMESTAMPTZ NOT NULL,
    normalized_category  VARCHAR(100),
    raw_event_ref        TEXT,
    UNIQUE (
        provider_id, provider_account_id, provider_event_id
    )
);
~~~

Không phải provider nào cũng cung cấp event ID bền vững. Nếu thiếu, cần xây **dedup fingerprint** theo hợp đồng event của provider, có giới hạn thời gian và đánh giá false positive/false negative. Đừng coi hai email cùng timestamp hoặc cùng diagnostic string là một event.

### Xử lý duplicate event

Khi insert gặp unique conflict:

1. Xác nhận đó là event đã nhận trước đó.
2. Không lặp lại side effects của policy nếu chúng đã commit.
3. Trả response phù hợp để provider không tiếp tục retry vô hạn.
4. Nếu lần trước chỉ persist nhưng chưa apply policy, worker từ **durable event inbox** tiếp tục xử lý thay vì phụ thuộc webhook phải tới lại.

## 24. Lưu event và cập nhật policy trong transaction phù hợp

Mô hình an toàn:

~~~text
Verified webhook
     |
     v
BEGIN DB TRANSACTION
  INSERT provider event (unique ID)
  INSERT processing_work_item
COMMIT
     |
     v
Policy worker
     |
     v
BEGIN DB TRANSACTION
  Check event not applied
  Update recipient delivery state
  Apply suppression if warranted
  Mark event applied
COMMIT
~~~

Cách này cho phép:

- Webhook phản hồi nhanh để tránh provider timeout.
- Retry ứng dụng sau khi process crash.
- Phân loại provider errors ngoài HTTP request path.
- Giữ audit khi chính sách suppression thay đổi.

Nếu webhook nhận và business update cùng database transaction, vẫn phải tránh gọi API ngoài trong transaction lâu. Nếu event lưu ở một database còn suppression lưu ở dịch vụ khác, cần **idempotent command + reconciliation** thay vì giả định có ACID xuyên dịch vụ.

**Không trả success trước khi event quan trọng được chấp nhận bền vững**, trừ khi provider contract và cơ chế queue đã bảo đảm lưu trữ theo kiến trúc.

## 25. Data model cho suppression tách khỏi preference

Để tránh trộn “recipient muốn nhận gì” với “recipient có nhận được không”, có thể dùng hai nguồn:

~~~text
mail_subscription_preference
    tenant, recipient, scope, subscribed/unsubscribed

mail_suppression
    tenant, recipient, scope, reason,
    active, started_at, expires_at
~~~

Một schema ví dụ:

~~~sql
CREATE TABLE mail_suppression (
    tenant_id        VARCHAR(120) NOT NULL,
    recipient_key    VARCHAR(240) NOT NULL,
    scope_type       VARCHAR(30) NOT NULL,
    scope_key        VARCHAR(160) NOT NULL,
    reason           VARCHAR(60) NOT NULL,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    started_at       TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    source_event_id  BIGINT,
    version          BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (
        tenant_id,
        recipient_key,
        scope_type,
        scope_key,
        reason
    )
);
~~~

Ví dụ:

~~~text
Tenant A / recipient R12:

Preference:
  MARKETING -> UNSUBSCRIBED

Suppression:
  RECIPIENT / HARD_BOUNCE -> active
  MARKETING / SPAM_COMPLAINT -> active
~~~

Một recipient có thể vừa unsubscribed vừa suppressed. Khi giải quyết hard bounce bằng địa chỉ mới, không được tự động xóa unsubscribe marketing trước đó.

### Chính sách scope

**scope_type** có thể là RECIPIENT, LIST, STREAM, BRAND, PROVIDER_ACCOUNT hoặc TENANT tùy model. Nhưng các scope phải được kiểm soát:

- Suppression do recipient invalid có thể áp dụng rộng tới mọi mail stream dùng cùng địa chỉ.
- Unsubscribe newsletter thường chỉ tác động list hoặc marketing stream.
- Spam complaint có thể cần phạm vi rộng hơn và phụ thuộc chính sách ESP.
- Provider account-level suppression có thể ảnh hưởng nhiều tenant cùng account.

Không có quy tắc mặc định của Spring Mail cho mức scope này; nó phải là domain policy được kiểm thử.

## 26. Một bảng trạng thái tổng hợp chưa đủ cho audit

Nếu chỉ có:

~~~text
recipient R12 -> SUSPRESSED
~~~

sẽ khó giải thích:

- Vì sao bị suppress?
- Do bounce, complaint hay admin?
- Có phải chỉ một soft bounce?
- Provider nào và attempt nào tạo sự kiện?
- Suppression có thời hạn hay vĩnh viễn tới khi verify?
- Người dùng đã unsubscribe từ trước hay chưa?
- Ai được phép gỡ trạng thái?

Nên giữ:

1. **Event ledger bất biến**: sự kiện inbound/outbound và chứng cứ.
2. **Current effective state**: trạng thái nhanh để worker kiểm tra trước gửi.
3. **Policy version**: phiên bản quy tắc quyết định chuyển trạng thái.
4. **Actor/source**: webhook provider, consent endpoint, support action.
5. **Audit transition**: giá trị trước/sau và lý do.

Đây là lý do một suppression service không chỉ là một HashSet địa chỉ email.

## 27. Gắn event chính xác vào notification-recipient

Một message có thể có nhiều người nhận:

~~~text
MimeMessage M100:
  To: a@example.net
  Cc: b@example.net
  Bcc: c@example.net
~~~

Nhà cung cấp có thể phát bounce riêng cho **b@example.net**, trong khi a/c đã được chấp nhận.

Không nên:

~~~text
if any recipient bounced:
    mark entire message as undeliverable
    suppress all recipients
~~~

Một mô hình đúng hơn:

~~~text
Notification N100
    |
    +-- Recipient R1 -> DELIVERED
    +-- Recipient R2 -> BOUNCED
    +-- Recipient R3 -> UNKNOWN/DEFERRED
~~~

Sự kiện từ provider cần đối chiếu:

- Provider account và message ID.
- Notification/attempt tương ứng.
- Recipient key được chuẩn hóa.
- Tenant/stream/list mà message đã gửi.
- Event type và thời gian.

Nếu không thể đối chiếu chắc chắn, **quarantine event**, không tự cập nhật suppression theo tên địa chỉ lấy từ payload chưa đủ tin cậy.

### Bcc vẫn có delivery outcome riêng

Bcc không xuất hiện trong header hiển thị cho những người nhận khác, nhưng **RCPT TO** vẫn được SMTP server sử dụng. Do đó hệ thống theo dõi deliverability cần giữ danh sách envelope recipients một cách bảo mật và không lộ địa chỉ Bcc cho những recipient khác.

## 28. Event có thể đến sai thứ tự

Ví dụ:

~~~text
09:00  ESP accepted message
09:01  Event "deferred" xảy ra
09:02  Event "delivered" xảy ra
09:03  Webhook "delivered" tới application
09:05  Webhook "deferred" tới application (bị trễ)
~~~

Nếu application xử lý:

~~~text
delivery_status = newest_HTTP_request.eventType
~~~

thì sau 09:05 trạng thái sẽ bị lùi từ DELIVERED về DEFERRED, dù sự kiện deferred xảy ra trước.

Giải pháp:

- Lưu **provider event time**, ingestion time và event ID.
- Xác định **state transition rules** cho từng provider/event type.
- Không dùng đơn thuần thứ tự HTTP arrival.
- Không overwrite terminal outcome bởi transient event cũ.
- Đánh dấu trạng thái có xung đột để reconciliation khi provider báo kết quả khác thường.

Đặc biệt, **một trạng thái giao hàng** và **một quyết định suppression** là hai thứ riêng. Có thể một message được báo delivered, sau đó recipient complaint; việc complaint chặn marketing mới không đòi sửa sự thật rằng message cũ đã được provider báo delivered.

## 29. State machine cho mỗi recipient

Một mô hình gợi ý:

~~~text
SCHEDULED
     |
     v
SUBMITTED
     |
     +-- DEFERRED -> still pending provider outcome
     |
     +-- DELIVERED
     |
     +-- BOUNCED
     |
     +-- DELIVERY_UNKNOWN

Independent contact policy:
     |
     +-- CONTACT_OK
     +-- TEMPORARY_HOLD
     +-- SUPPRESSED_HARD_BOUNCE
     +-- SUPPRESSED_COMPLAINT
     +-- UNSUBSCRIBED_LIST
     +-- UNSUBSCRIBED_MARKETING
~~~

Đối với một provider, event DELIVERY có thể đến sau DEFERRED; nhưng **spam complaint** không nhất thiết là một nhánh giao hàng thay thế của message đó.

Không thiết kế một enum duy nhất:

~~~text
SENT | BOUNCED | UNSUBSCRIBED
~~~

để biểu diễn cả lịch sử message và lựa chọn người nhận. Một email đã DELIVERED có thể bị người nhận unsubscribe sau đó, và cả hai thông tin đều cần tồn tại.

## 30. Soft bounce: tạm hoãn thay vì xóa vĩnh viễn

Ví dụ:

~~~text
Recipient R12:
  2026-11-01 -> temporary mailbox full
  2026-11-03 -> temporary mailbox full
  2026-11-04 -> delivered
~~~

Một lần soft bounce không chứng minh địa chỉ vô hiệu. Có thể dùng policy:

1. Ghi nhận soft bounce theo recipient/provider và khoảng thời gian.
2. Để ESP retry theo cơ chế của họ hoặc điều tiết retry ở application, tránh retry chồng nhau.
3. Nếu vượt ngưỡng được định nghĩa, đặt **TEMPORARY_HOLD**.
4. Đặt **hold_until**, không cần suppress vĩnh viễn.
5. Sau thời gian hold, gửi thử theo rate hạn chế khi còn consent và business intent hợp lệ.
6. Nếu có delivery thành công, đánh giá lại trạng thái deliverability.

Ví dụ policy minh họa:

~~~text
3 temporary delivery failures trong 7 ngày
  -> HOLD 24 giờ

Sau HOLD:
  -> Cho một số email hợp lệ gửi thử có kiểm soát

Không còn soft bounce:
  -> Gỡ hold theo rule
~~~

Các con số chỉ để diễn giải, không phải chuẩn bắt buộc. Ngưỡng phải dựa trên ESP behavior, stream, recipient domain và chất lượng danh sách thực tế.

### Không retry một message đã hết giá trị

OTP hết hạn trong 5 phút không nên được gửi lại sau một temporary hold 24 giờ. **Provider retry policy** và **business deadline** phải được phối hợp để không phát ra nội dung lỗi thời.

## 31. Hard bounce: xác minh và phục hồi địa chỉ

Một recipient hard bounce được xác minh, ví dụ mailbox không tồn tại, thường cần dừng gửi tới **địa chỉ hiện tại**.

Quy trình:

~~~text
Verified invalid-recipient bounce
      |
      v
Set suppression for recipient address
      |
      v
Cancel/defer applicable pending messages
      |
      v
Notify account owner through approved channel
      |
      v
User updates/validates contact address
      |
      v
Create a new verified contact identity
      |
      v
Re-evaluate consent/eligibility
~~~

Không tự động gỡ hard suppression chỉ vì đã trôi qua N ngày nếu không có bằng chứng địa chỉ đã được sửa/xác minh.

Nếu người dùng đổi email từ **old@example.net** sang **new@example.net**, nên quản lý phiên bản/contact identity phù hợp. Không làm như địa chỉ cũ chưa từng bounce; lịch sử vẫn hữu ích cho audit.

### Khi mã 5xx chưa đủ tin cậy

Nếu nhiều domain cùng báo policy 5.7.1 sau khi DKIM bị cấu hình sai, việc suppress hàng nghìn người nhận sẽ là kết luận sai. Trước khi áp dụng bulk hard suppression, cần phân biệt **recipient-invalid** với **sender-policy**.

## 32. Spam complaint là một tín hiệu riêng

Một người nhận có thể đánh dấu một email là spam, và provider gửi complaint event qua feedback loop hoặc webhook.

Nên:

- Xác minh complaint event đến từ nguồn đáng tin.
- Liên kết tới recipient và message/list/brand phù hợp.
- Dừng gửi marketing thuộc phạm vi chính sách.
- Ghi reason **SPAM_COMPLAINT** riêng với **HARD_BOUNCE** và **UNSUBSCRIBE**.
- Kiểm tra danh sách nguồn, consent và tần suất gửi.
- Không gửi lại email marketing để “xin xác nhận complaint” nếu điều đó trái với lựa chọn người dùng.

Không phải mọi spam report trong một mailbox sẽ có thể liên kết chính xác tới recipient, vì một số feedback loop ẩn thông tin định danh. Cần policy cho **aggregated complaint signals** thay vì tự bịa một recipient khi thiếu dữ liệu.

### Vì sao complaint không đồng nghĩa bounce?

Thư có thể đã được giao, người dùng nhìn thấy rồi đánh dấu spam. Địa chỉ vẫn có thể nhận email. Suppression xuất phát từ **phản đối của người nhận/chính sách chống lạm dụng**, không từ khả năng kỹ thuật của mailbox.

## 33. Chuẩn hóa địa chỉ email mà không gộp nhầm người nhận

Một policy phải định danh recipient nhất quán giữa:

- Outbound SMTP envelope.
- Provider webhook.
- DSN Final-Recipient.
- Unsubscribe token.
- Subscription database.
- CRM/contact record.

Nhưng việc **normalize email address** có các bẫy:

- Phần **domain** của địa chỉ không phân biệt chữ hoa/chữ thường trong DNS; cần canonicalize tên miền theo quy tắc và IDN khi phù hợp.
- Phần **local-part** về mặt giao thức không thể mặc định chuyển hết thành lowercase cho mọi mail server.
- Không tự động bỏ dấu chấm hoặc hậu tố **+tag** chỉ vì một số nhà cung cấp có alias convention như vậy. Các domain khác có thể coi đó là địa chỉ khác.
- Không sử dụng display name để định danh contact.
- Email có Unicode/IDN cần thư viện và chính sách SMTPUTF8 phù hợp nếu provider hỗ trợ.
- Một user có thể thay đổi địa chỉ, vì vậy contact identity và address version không nên là một chuỗi duy nhất không có lịch sử.

Ví dụ:

~~~text
Contact ID: C100
  Address version 1: user.old@example.net
  Address version 2: user.new@example.net

Suppression:
  Address version 1 -> HARD_BOUNCE

Preference:
  Marketing topic -> UNSUBSCRIBED
~~~

Khi user thay địa chỉ, suppression do hard bounce trên địa chỉ cũ không nhất thiết áp dụng cho địa chỉ mới. Nhưng **unsubscribe marketing ở cấp contact** có thể vẫn phải áp dụng, tùy phạm vi đồng ý đã ghi nhận.

Một model tốt tách:

1. **Contact/person key**.
2. **Deliverable address identity/version**.
3. **Subscription preference scope**.
4. **Suppression reason scope**.

## 34. Thứ tự kết hợp subscription, bounce và complaint

Giả sử recipient R12 có:

~~~text
Subscription:
  LIST weekly-newsletter = SUBSCRIBED
  STREAM MARKETING       = UNSUBSCRIBED

Deliverability:
  ADDRESS = TEMPORARY_HOLD until tomorrow

Complaint:
  LIST weekly-newsletter = SUPPRESSED_COMPLAINT
~~~

Khi muốn gửi weekly newsletter, kết quả phải là **DENY**, dù có một row LIST=SUBSCRIBED. Scope lớn STREAM MARKETING đã unsubscribe, và còn suppression khác.

Một phép tính đơn giản:

~~~text
allow =
    senderAuthorized
    AND messageStillRelevant
    AND consentPolicyAllows(tenant, recipient, stream, list)
    AND NOT applicableUnsubscribe
    AND NOT applicableComplaint
    AND NOT applicableHardBounce
    AND NOT applicableTemporaryHold
    AND recipientAddressUsable
    AND scheduleDeadlineAllows
~~~

Đây là công thức về mặt ý tưởng. Một luồng **email bắt buộc hợp lệ** có thể không dựa trên cùng opt-in marketing, nhưng vẫn cần đánh giá deliverability, policy, quyền gửi và tính phù hợp. Không nên cho một stream được miễn mọi gate chỉ vì tên của nó là TRANSACTIONAL.

### Quyết định DENY nên có reason

Ví dụ:

~~~text
DENY_UNSUBSCRIBED_MARKETING
DENY_LIST_UNSUBSCRIBED
DENY_SPAM_COMPLAINT
DENY_HARD_BOUNCE
DEFER_TEMPORARY_BOUNCE_HOLD
DEFER_PROVIDER_THROTTLE
DENY_BUSINESS_OBSOLETE
DENY_EXPIRED
ALLOW_SEND
~~~

Các reason phải thuộc tập hữu hạn. Không dùng raw exception text làm policy result, vì có thể chứa PII và gây khó tổng hợp.

## 35. Ví dụ service quyết định gửi trong Spring

Một abstraction:

~~~java
public record SendRequest(
        String tenantId,
        String recipientKey,
        String notificationType,
        String stream,
        String listId
) {
}

public enum DecisionCode {
    ALLOW,
    UNSUBSCRIBED,
    COMPLAINT_SUPPRESSED,
    HARD_BOUNCE_SUPPRESSED,
    TEMPORARY_HOLD,
    NOT_AUTHORIZED,
    NOT_ELIGIBLE
}

public record SendDecision(
        boolean allowed,
        DecisionCode code
) {
    public static SendDecision allow() {
        return new SendDecision(true, DecisionCode.ALLOW);
    }

    public static SendDecision deny(DecisionCode code) {
        return new SendDecision(false, code);
    }
}
~~~

Policy service minh họa:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RecipientEligibilityService {

    private final SenderAuthorization senderAuthorization;
    private final SubscriptionRepository subscriptions;
    private final SuppressionRepository suppressions;
    private final NotificationBusinessPolicy businessPolicy;

    public RecipientEligibilityService(
            SenderAuthorization senderAuthorization,
            SubscriptionRepository subscriptions,
            SuppressionRepository suppressions,
            NotificationBusinessPolicy businessPolicy
    ) {
        this.senderAuthorization = senderAuthorization;
        this.subscriptions = subscriptions;
        this.suppressions = suppressions;
        this.businessPolicy = businessPolicy;
    }

    public SendDecision evaluate(SendRequest request) {

        if (!senderAuthorization.maySend(request)) {
            return SendDecision.deny(DecisionCode.NOT_AUTHORIZED);
        }

        if (!businessPolicy.isRelevant(request)) {
            return SendDecision.deny(DecisionCode.NOT_ELIGIBLE);
        }

        if (subscriptions.isUnsubscribedFor(request)) {
            return SendDecision.deny(DecisionCode.UNSUBSCRIBED);
        }

        if (suppressions.hasSpamComplaint(request)) {
            return SendDecision.deny(
                    DecisionCode.COMPLAINT_SUPPRESSED
            );
        }

        if (suppressions.hasHardBounce(request)) {
            return SendDecision.deny(
                    DecisionCode.HARD_BOUNCE_SUPPRESSED
            );
        }

        if (suppressions.hasTemporaryHold(request)) {
            return SendDecision.deny(
                    DecisionCode.TEMPORARY_HOLD
            );
        }

        return SendDecision.allow();
    }
}
~~~

**SenderAuthorization, SubscriptionRepository, SuppressionRepository, NotificationBusinessPolicy** là interface do ứng dụng định nghĩa. Đoạn mã trình bày một pipeline quyết định, chưa gồm business deadline/quota/lease, caching, transaction và concurrent updates.

Nên phân biệt **DENY** với **DEFER** trong implementation thực:

- UNSUBSCRIBED hoặc HARD_BOUNCE thường là quyết định không nên tiếp tục một notification mới.
- TEMPORARY_HOLD có thể xếp lịch lại nếu message còn hạn và policy cho phép.
- Sender authorization failure không nên biến thành retry SMTP vô hạn.

Không chỉ dùng một boolean rồi bỏ mất reason; reason là đầu vào quan trọng cho audit và vận hành.

## 36. Scheduled outbox phải kiểm tra suppression ngay trước gửi

Ví dụ:

~~~text
08:00  Campaign tạo email N100 cho recipient R12
09:00  N100 scheduled
08:45  R12 one-click unsubscribe
09:00  Worker lấy N100
~~~

Nếu worker chỉ đọc cờ consent được lưu trong payload lúc 08:00, N100 vẫn có thể được gửi trái với lựa chọn mới.

Luồng nên là:

~~~text
Outbox PENDING
      |
      v
Claim by worker with token
      |
      v
Load current subscription + suppression
      |
      +-- UNSUBSCRIBED -> SKIPPED with reason
      +-- HARD_BOUNCE -> SKIPPED with reason
      +-- TEMP_HOLD   -> DEFER if deadline allows
      |
      v
Check tenant, business relevance, deadline
      |
      v
Transition to SENDING with claim token
      |
      v
JavaMailSender.send(...)
~~~

**Một outbox entry có thể được tạo hợp lệ trước khi unsubscribe, nhưng không còn được phép gửi khi đến lượt.** Quyền gửi cần được đánh giá tại thời điểm thực hiện, không chỉ thời điểm lên lịch.

### Business skip khác SMTP failure

Một notification bị suppress trước send không nên tạo một SMTP attempt giả:

~~~text
status = SKIPPED
reason = RECIPIENT_UNSUBSCRIBED
attempt_count = 0
~~~

Nếu ghi FAILED/SMTP_ERROR, alert transport error sẽ không phản ánh đúng sự cố và scheduler có thể retry sai.

## 37. Race giữa unsubscribe và một SMTP send đang chạy

Một trường hợp khó:

~~~text
09:00:00.000  Worker kiểm tra subscription: vẫn opted in
09:00:00.050  Worker chuyển trạng thái SENDING
09:00:00.100  One-click POST ghi UNSUBSCRIBED
09:00:00.120  Worker truyền SMTP DATA
~~~

**Không có transaction ACID chung giữa preference database và SMTP server.** Vì vậy một check trước send không tạo bảo đảm tuyệt đối rằng unsubscribe có thể ngăn một attempt đã bước vào vùng gửi.

Những biện pháp giảm race:

- Chỉ gửi sau **final eligibility check** gần network call.
- Dùng snapshot version hoặc optimistic locking cho policy và outbox state transition.
- Nếu một stream yêu cầu nghiêm ngặt, thiết kế một **admission coordinator** hoặc transaction ngắn khóa những record cần thiết trước khi đánh dấu SENDING.
- Khi one-click unsubscribe thành công, dừng/chặn các job PENDING/RETRY_WAIT liên quan.
- Không tự khẳng định có thể thu hồi thư đã SUBMITTED.
- Lưu **unsubscribe effective_at**, **attempt_started_at** và **submitted_at** để điều tra ranh giới.

Ngay cả khi DB bảo vệ trạng thái SENDING, **SMTP submission có thể tiếp tục sau khi DB transaction commit**. Muốn có đặc tính mạnh hơn cần kiểm soát ở tầng dispatch/provider và thừa nhận giới hạn side effect đã xảy ra.

### Không khóa preference trong suốt gửi SMTP

Giữ một row lock của subscription trong nhiều giây khi gọi SMTP có thể làm yêu cầu unsubscribe bị chậm hoặc deadlock với workflow khác. Nên giữ transaction ngắn và có ranh giới rõ; không dùng lock dài như một cách bảo đảm tuyệt đối rằng email chưa ra khỏi hệ thống.

## 38. Update notification có điều kiện theo quyết định policy

Giả sử worker đang sở hữu claim của N100. Nếu recipient đã unsubscribe, có thể cập nhật:

~~~sql
UPDATE email_outbox
SET
    status = 'SKIPPED',
    outcome_reason = 'RECIPIENT_UNSUBSCRIBED',
    finished_at = statement_timestamp(),
    claim_token = NULL,
    lease_until = NULL,
    version = version + 1
WHERE id = :notificationId
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
RETURNING id;
~~~

Điều kiện status/token ngăn một worker cũ ghi đè kết quả của worker mới hoặc trạng thái đã SUBMITTED. Nếu update không trả row, cần đọc lại state rồi xử lý theo state machine, không bỏ WHERE để “ghi cho được”.

Trong nhiều tenant, **tenant_id** cũng nên xuất hiện trong WHERE hoặc được ràng buộc bởi authorization và nguồn job đã xác thực. Không chỉ dùng notificationId nhận từ client mà không kiểm tra ownership.

Với temporary hold:

~~~text
if hold_until < notification_expires_at:
    RETRY_WAIT until hold_until
else:
    SKIP_OR_EXPIRE under business policy
~~~

Không cố retry ngay mỗi lần worker quét queue khi hold vẫn còn hiệu lực.

## 39. Cập nhật preference idempotent trong một transaction

Một service unsubscribe nên thực hiện:

~~~text
BEGIN TRANSACTION
    |
    +-- Lookup token hash and validate scope
    |
    +-- Lock/update preference for tenant+recipient+scope
    |
    +-- If already UNSUBSCRIBED: no-op
    |
    +-- Else record UNSUBSCRIBED and audit
    |
    +-- Insert internal preference-changed event
    |
COMMIT
~~~

Để nhiều POST đồng thời không tạo duplicate side effects, có thể dùng:

- Unique key trên **tenant + recipient + scope**.
- Atomic **INSERT ... ON CONFLICT DO UPDATE** hoặc conditional update phù hợp database.
- Một event ledger có idempotency key.
- Outbox event để thông báo worker/cache một cách bền vững.

Ví dụ ý tưởng PostgreSQL:

~~~sql
INSERT INTO mail_subscription_preference (
    tenant_id, recipient_key,
    scope_type, scope_key,
    decision, decision_at, decision_source, version
)
VALUES (
    :tenantId, :recipientKey,
    :scopeType, :scopeKey,
    'UNSUBSCRIBED',
    statement_timestamp(),
    'ONE_CLICK_POST',
    1
)
ON CONFLICT (
    tenant_id, recipient_key, scope_type, scope_key
)
DO UPDATE SET
    decision = 'UNSUBSCRIBED',
    decision_at = statement_timestamp(),
    decision_source = 'ONE_CLICK_POST',
    version = mail_subscription_preference.version + 1
WHERE mail_subscription_preference.decision
      IS DISTINCT FROM 'UNSUBSCRIBED'
RETURNING tenant_id, recipient_key;
~~~

Nếu không trả row vì preference đã UNSUBSCRIBED, có thể coi HTTP POST là thành công idempotent. Nếu trả row, transaction có thể ghi một audit transition/outbox event duy nhất theo policy.

**Không dùng lệnh trên cho resubscribe**. Subscribe lại đòi một luồng có bằng chứng đồng ý mới, không được do webhook hoặc caller bên ngoài tùy ý đổi.

## 40. Đồng bộ cache và ESP suppression list

Một kiến trúc có thể có nhiều lớp:

~~~text
Preference DB (source of truth)
           |
           +-- Application cache
           |
           +-- Sending workers
           |
           +-- ESP provider suppression list
~~~

Thách thức:

- Database đã UNSUBSCRIBED nhưng cache còn giá trị SUBSCRIBED cũ.
- Một provider suppression event đến nhưng app chưa đồng bộ.
- App đã gỡ một temporary hold nhưng provider vẫn giữ account-level suppression.
- ESP API đồng bộ thất bại, ứng dụng và provider nhìn trạng thái khác nhau.

Các nguyên tắc:

1. Xác định **source of truth** cho consent và suppression do ứng dụng quản lý.
2. Dùng **policy-change event/outbox** để invalidate cache và đồng bộ provider.
3. Không cho cache TTL dài làm thất hiệu lực một unsubscribe vừa commit.
4. Nếu policy service không khả dụng, xác định **fail-closed** cho marketing thay vì gửi không kiểm soát.
5. Có job **reconciliation** với provider suppression state khi API hỗ trợ.
6. Không tự động gỡ suppression phía provider nếu không hiểu vì sao provider đặt nó.

**Đồng bộ không có nghĩa provider sẽ cho gửi ngay**: ESP có thể từ chối recipient ở account-level dù application đã cho phép. Cần giữ thông tin từ chối đó trong logs/metrics và xử lý theo chính sách.

## 41. Subscribe lại sau khi đã unsubscribe

Một người đã unsubscribe có thể đổi ý. Nhưng **subscribe lại phải là một quyết định mới có bằng chứng thích hợp**, không phải một side effect khi:

- Đồng bộ lại CRM.
- ESP thông báo delivered.
- Soft bounce tự hết hold.
- Admin chạy import danh sách recipient.
- Thay email address.
- Một user nhấn mở lại trang preferences.

Một workflow:

~~~text
Recipient previously UNSUBSCRIBED
        |
        v
User explicitly opts in again
        |
        v
Validate scope and identity
        |
        v
Optional double opt-in verification
        |
        v
Record new consent evidence and timestamp
        |
        v
Re-evaluate hard-bounce/complaint suppressions
        |
        v
Eligible for applicable future email
~~~

Nếu contact còn **SUPPRESSED_HARD_BOUNCE**, chỉ đổi preference thành SUBSCRIBED không đủ để tiếp tục gửi tới một địa chỉ chưa chứng minh còn hoạt động.

### Double opt-in có thể hữu ích ở đâu?

Với đăng ký newsletter hoặc thay địa chỉ liên hệ, ứng dụng có thể:

1. Nhận yêu cầu đăng ký.
2. Gửi email xác minh đến địa chỉ mới theo chính sách được phép.
3. Người nhận xác nhận qua token an toàn.
4. Lưu timestamp, scope và bằng chứng.
5. Mới cho phép gửi nội dung tương ứng.

Một luồng xác minh cũng phải chống abuse, không cho phép liên tục gửi email “xác minh” tới người đã từ chối nhận mail. Cần có rate limit, TTL và bảo vệ dữ liệu riêng.

## 42. Hard bounce được gỡ như thế nào?

Một rule phục hồi có thể yêu cầu:

| Trạng thái | Điều kiện gỡ |
|---|---|
| **TEMPORARY_HOLD** | Hết hold, có tín hiệu phù hợp và đáp ứng quota/policy |
| **HARD_BOUNCE** | Người dùng sửa địa chỉ hoặc xác minh lại tính khả dụng |
| **SPAM_COMPLAINT** | Chỉ theo quy trình re-permission được xác nhận và phù hợp chính sách ESP |
| **UNSUBSCRIBED** | Người dùng opt-in lại một cách rõ ràng |
| **PROVIDER_ACCOUNT_SUPPRESSED** | Provider cho phép gỡ và nguyên nhân gốc đã được giải quyết |

Không áp dụng một lệnh:

~~~sql
DELETE FROM mail_suppression
WHERE started_at < statement_timestamp() - INTERVAL '30 days';
~~~

để gỡ mọi suppression sau 30 ngày. Temporary hold, invalid mailbox và spam complaint có ý nghĩa khác nhau; không thể đặt cùng expiry tự động.

Nên **đánh dấu inactive với audit** thay vì xóa lịch sử làm mất khả năng điều tra. Khi recipient được gỡ, cần đảm bảo consent và những suppression scope khác vẫn được kiểm tra.

## 43. Đăng ký và unsubscribe trong hệ thống nhiều tenant

Một địa chỉ email có thể dùng cùng lúc trên nhiều workspace:

~~~text
customer@example.net
   |
   +-- Tenant A: subscribed to product-news
   |
   +-- Tenant B: unsubscribed from marketing
   |
   +-- Tenant C: bounced due to provider policy
~~~

Hệ thống không được tự suy rằng:

~~~text
Tenant B unsubscribe -> tất cả tenant phải unsubscribe
~~~

Nếu sản phẩm có thương hiệu/tổ chức gửi hoàn toàn tách biệt, consent có thể theo tenant hoặc brand. Tuy nhiên, nếu cùng **provider account** có suppression thực ở cấp account, một sự kiện provider vẫn có thể ảnh hưởng kỹ thuật đến nhiều tenant.

Điều cần xác định:

1. **Consent owner:** một tenant, brand hay nền tảng?
2. **List owner:** ai được thêm/xóa người nhận?
3. **Provider account scope:** quota/suppression có chung không?
4. **Data locality:** event và PII được lưu vùng nào?
5. **Authorization:** user tenant A không đọc/chỉnh preference tenant B.
6. **Audit:** ai được gỡ hard bounce hoặc complaint?

Không lấy tenantId từ raw MIME header/webhook field chưa được verify để sửa suppression của tenant. Tenant identity phải được xác định qua account/provider mapping và notification correlation đáng tin cậy.

## 44. Pháp lý và trải nghiệm hủy nhận thư

Các nghĩa vụ về consent, marketing, unsubscribe, thời hạn xử lý, xác minh nguồn gửi và lưu trữ bằng chứng **khác nhau theo khu vực pháp lý, loại thư và vai trò tổ chức**.

Vì vậy policy production nên:

- Phân loại **marketing** và **transactional/service** theo nội dung/thực chất, không chỉ tên enum.
- Có cơ chế opt-out rõ ràng cho luồng áp dụng.
- Thực thi unsubscribe với độ trễ phù hợp, ưu tiên cập nhật ngay khi có yêu cầu hợp lệ.
- Không yêu cầu thông tin không cần thiết hoặc ép người nhận đăng nhập để hoàn tất one-click.
- Có audit tối thiểu về phạm vi và thời gian lựa chọn.
- Xử lý các quyền về dữ liệu cá nhân và retention theo chính sách hợp lệ.
- Kiểm tra các yêu cầu mới nhất của mail provider trước khi triển khai bulk-sending.

**Không coi ví dụ trong bài là tư vấn pháp lý hoặc tuyên bố một thời hạn tuân thủ cụ thể.** Việc lựa chọn scope, thời hạn và consent flow cần phối hợp với nhóm pháp lý/compliance theo nơi doanh nghiệp hoạt động.

### Email xác nhận unsubscribe có cần gửi?

Không nhất thiết. Nếu tự động gửi một loạt email “Bạn đã unsubscribed” hoặc đòi người dùng click xác nhận, có thể đi ngược mục tiêu của one-click hoặc tạo thêm traffic không mong muốn.

Nếu sản phẩm cần hiển thị xác nhận, HTTP response và preference page thường đã đủ. Chỉ gửi thêm email xác nhận nếu có lý do nghiệp vụ/chính sách hợp lệ, tránh mail loop và tôn trọng suppression/deliverability.

## 45. Deliverability: SPF, DKIM, DMARC và bounce alignment

Một số bounce tăng đột biến không do recipient:

~~~text
Deploy cấu hình From mới
        |
        v
DKIM signing domain sai hoặc thiếu
        |
        v
Receiving domains từ chối theo policy
        |
        v
Bounce/policy rejection tăng trên nhiều domain
~~~

Để điều tra:

- **SPF:** sender/provider được phép gửi cho envelope domain theo cấu hình DNS?
- **DKIM:** thông điệp có chữ ký hợp lệ, signing domain đúng?
- **DMARC:** Header From alignment với domain xác thực như thế nào?
- **MAIL FROM/Return-Path:** ESP có dùng domain đã cấu hình và xác minh?
- **Reputation:** một nguồn gửi/campaign có làm tăng complaints không?
- **Sender profile:** có nhầm giữa tenant, account và domain khi scale nhiều worker?

Đừng sửa một lỗi DMARC alignment bằng cách suppress toàn bộ recipient bị trả 5.7.x. Cần điều tra tuyến gửi/ESP và xác định mức độ lan rộng.

### Vấn đề DKIM với one-click

Nếu ứng dụng thêm **List-Unsubscribe-Post** nhưng ESP ký DKIM trước khi một gateway sửa header, chữ ký có thể không còn hợp lệ. Cần kiểm tra **message cuối cùng sau khi provider xử lý**, không chỉ object MimeMessage ở JVM.

Ngược lại, chỉ có DKIM hợp lệ cũng không thay thế việc endpoint one-click phải thực sự xử lý POST an toàn và đúng scope.

## 46. Ranh giới trách nhiệm của các thành phần Spring

Trong một ứng dụng Spring điển hình:

| Thành phần | Nhiệm vụ |
|---|---|
| **JavaMailSender** | Tạo/gửi SMTP messages |
| **MimeMessageHelper** | Gán From/To/Subject/body/attachment |
| **Jakarta Mail** | MIME/header/envelope transport tùy provider |
| **Spring MVC** | Nhận one-click HTTP POST và preference requests |
| **Spring Security** | Bảo vệ admin/user APIs và cấu hình endpoint công khai có kiểm soát |
| **Spring JDBC/JPA** | Lưu preferences, suppressions, events, outbox và audit |
| **Spring Scheduling** | Quét outbox, retry, soft hold expiry, reconciliation |
| **Spring Integration Mail** | Nhận DSN/mailto unsubscribe qua mailbox nếu cần |
| **Micrometer/Actuator** | Đo metrics và xuất dữ liệu giám sát |

Không có một phương thức của **JavaMailSender** tự:

- Tạo một one-click endpoint.
- Quyết định consent theo tenant/list.
- Đọc webhook bounce.
- Chuyển một hard bounce thành suppression policy.
- Ngăn worker gửi email đã lên lịch sau unsubscribe.
- Cập nhật provider suppression list.
- Đảm bảo exactly-once khi SMTP final reply bị mất.

Vì vậy kiến trúc nên có **domain service** cho preferences và deliverability, dùng Spring Mail ở **transport boundary**.

Một sơ đồ triển khai:

~~~text
                   Recipient actions
            +-------------+-------------+
            |                           |
        Preference UI             One-click endpoint
            |                           |
            +-------------+-------------+
                          |
                          v
                 Subscription Service
                          |
                          v
              Preference/Audit database
                          |
                     Policy events
                          |
                          v
Outbox jobs ------> Eligibility gate -----> JavaMailSender
                          ^                       |
                          |                       v
                    Suppression DB           SMTP Provider
                          ^                       |
                          |                       v
                  Bounce policy worker <---- Webhook/DSN
~~~

## 47. Metrics: đo số message, recipient và policy outcome riêng

Các metric logic hữu ích:

| Metric | Ý nghĩa |
|---|---|
| **mail_submitted_total** | Unique notification-recipient được SMTP/ESP accepted |
| **mail_attempts_total** | Số attempts, bao gồm retry |
| **mail_provider_bounce_events_total** | Số verified provider events báo bounce |
| **mail_bounced_recipients_total** | Unique recipient-notification được xác định bounced |
| **mail_deferred_events_total** | Số event trì hoãn delivery |
| **mail_complaints_total** | Verified spam complaint events |
| **mail_unsubscribe_requests_total** | Requests one-click/UI/mailto đã nhận |
| **mail_unsubscribe_applied_total** | Unique subscription transitions thành công |
| **mail_policy_blocked_total** | Outbox attempts bị chặn bởi policy trước SMTP |
| **mail_suppression_active** | Số active suppression records theo loại/scope |
| **mail_webhook_signature_failures_total** | Webhooks bị từ chối do xác thực |
| **mail_webhook_unmatched_total** | Events chưa correlate được notification |
| **mail_policy_sync_lag_seconds** | Độ trễ đồng bộ preference đến sender/provider |
| **mail_policy_reconciliation_failures_total** | Lỗi đối soát đồng bộ trạng thái |

Không gộp **webhook requests** với **unique bounce**: provider có thể retry cùng event nhiều lần.

Không lấy số **email unsubscribe requests** làm số người đã unsubscribed mới: một người có thể nhấn lại nhiều lần hoặc có nhiều loại subscription.

### Cần định nghĩa denominator

Ví dụ:

~~~text
Trong một ngày:
  1.000 unique submitted recipients
     20 confirmed bounced
     50 deferred events
     15 spam complaint events
     30 unsubscribe requests
~~~

Các số này có thể đại diện cho những thế hệ message khác nhau vì delivery feedback đến muộn. Không nên mặc định tính “20/1000 = 2% bounce rate của ngày hôm nay” nếu 20 bounce thuộc những thư gửi hôm trước.

**Operational arrival rate** dùng để phát hiện tăng đột biến tức thời; **cohort ratio** theo thời điểm submission và độ chín dữ liệu phù hợp hơn để đánh giá deliverability.

## 48. Bounce rate theo cohort và sự kiện đến muộn

Ví dụ:

~~~text
Cohort A:
  2026-11-10: 5.000 recipient submissions accepted
  2026-11-11: 100 bounce reports tới
  2026-11-12: thêm 25 bounce reports tới
~~~

Nếu chỉ chia bounce event nhận ngày 12/11 cho submissions ngày 12/11, kết quả có thể sai rất xa.

Một phép đo:

~~~text
Mature-cohort bounce ratio =
    unique bounced recipient-submissions in cohort
    /
    unique accepted recipient-submissions in cohort
~~~

Cần định nghĩa:

- **Cohort time** là submitted_at/accepted_at.
- **Observation window** đủ dài cho provider feedback.
- **Outcome** theo recipient và attempt, không đếm webhook retries.
- **Hard/soft/policy bounce** riêng nếu muốn chẩn đoán nguyên nhân.
- **UNKNOWN** và feedback chưa có được báo cáo như dữ liệu chưa trưởng thành.
- **Provider-specific delay** để không so sánh cohort mới với cohort đã hoàn tất.

### Alert theo arrival event chỉ là proxy

Một cảnh báo “unique hard-bounce events tăng trong 15 phút” phù hợp để điều tra đột biến, nhưng không thay thế ratio theo cohort. Nếu chiến dịch vừa gửi một batch lớn, số bounce tuyệt đối tăng có thể do volume tăng, không phải chất lượng xấu hơn.

Với số lượng nhỏ, cần **minimum sample**. Một bounce trên một submission có thể là 100%, nhưng không đủ thông tin để kết luận hạ tầng bị sự cố diện rộng.

## 49. Giám sát unsubscribe và chất lượng trải nghiệm

Một one-click endpoint có thể trả HTTP 200 nhưng backend không thực sự chặn email mới nếu:

- Preference chỉ được ghi ở cache, chưa commit database.
- Worker dùng dữ liệu cũ.
- Tenant/list scope được ánh xạ sai.
- Provider API đồng bộ thất bại.
- Campaign đã chuẩn bị sẵn recipient list snapshot.

Do đó cần giám sát:

1. **POST success rate** của endpoint one-click.
2. **Time-to-effective-unsubscribe** từ commit preference đến khi send eligibility thấy giá trị mới.
3. Số **mail_policy_blocked_total{reason=UNSUBSCRIBED}**.
4. Số notification được submit **sau effective_at của unsubscribe** trong scope áp dụng, có phân biệt in-flight race.
5. Tỷ lệ one-click token invalid/expired.
6. Mailto unsubscribe backlog.
7. Tỷ lệ đồng bộ provider suppression API.
8. Các request lặp lại/idempotency outcomes.

Một chỉ số quan trọng:

~~~text
POST processed at 10:00
Preference committed at 10:00:01
Worker attempts marketing send at 10:01
~~~

Khi worker bắt đầu attempt sau thời điểm preference đã có hiệu lực và thuộc scope bị chặn, việc nó vẫn gửi là **policy enforcement defect** cần điều tra. Nhưng nếu SMTP đã bắt đầu trước commit và accepted sau đó, phải phân tích race thay vì kết luận chỉ từ submitted_at.

## 50. Cảnh báo và phân biệt nguyên nhân bounce spike

Khi bounce tăng:

| Hiện tượng | Giả thuyết ban đầu | Không nên làm ngay |
|---|---|---|
| 5.1.1 tăng ở danh sách vừa import | List quality/address validation | Retry dồn hoặc tăng SMTP timeout |
| 5.7.1 tăng ở nhiều domain | DKIM/DMARC/reputation/policy | Suppress toàn bộ recipient |
| 4xx/deferred tăng trên một domain | Receiving domain tạm throttle | Hard-suppress tất cả |
| Bounce có cùng provider event ID lặp lại | Webhook retry/dedup lỗi | Đếm mỗi HTTP POST là bounce mới |
| Hard bounce spike sau config rotation | Sender profile sai, provider changed policy | Coi mọi email invalid |
| Complaint rate tăng trong campaign | Consent/content/frequency vấn đề | Tự đổi provider để né reputation policy |
| Event webhook giảm về 0 đột ngột | Receiver/signature parser/backlog bị lỗi | Kết luận không còn bounce |

Không chỉ kiểm tra SMTP success rate; một vấn đề deliverability có thể xuất hiện **sau** khi SMTP đã accepted hàng nghìn message.

### Alert ví dụ theo nhóm

- **PolicyRejectSurge:** tỷ lệ rejection có mã nhóm policy tăng trên nhiều receiver domains.
- **InvalidRecipientBounceHigh:** confirmed invalid recipient tăng trong một cohort đủ volume.
- **ComplaintRateHigh:** verified complaints tăng so với sent cohorts.
- **UnsubscribeEndpointErrors:** one-click POST 5xx/timeout.
- **UnsubscribePropagationLag:** preference đã commit nhưng worker/provider chưa đồng bộ.
- **BounceWebhookOutage:** provider vẫn phát event nhưng ứng dụng ingest fail/backlog lớn.
- **BounceCorrelationFailures:** verified events không map được notification.

Nên gắn **runbook** và owner cụ thể. Không dùng SMTP provider đang có sự cố làm **kênh cảnh báo duy nhất** về chính sự cố đó.

## 51. Unit test policy: một hành động, một quyết định rõ ràng

Vì phần cốt lõi của bài toán là **policy**, nên thiết kế những test case độc lập với SMTP:

| Dữ liệu đầu vào | Loại email | Kết quả mong đợi |
|---|---|---|
| Recipient unsubscribed LIST=news | Newsletter cùng list | DENY_UNSUBSCRIBED |
| Recipient unsubscribed LIST=news | Email khác list, vẫn có consent | Đánh giá tiếp, không chặn chỉ vì list news |
| Recipient unsubscribed STREAM=MARKETING | Mọi list marketing trong stream | DENY_UNSUBSCRIBED |
| Recipient unsubscribed marketing | Hóa đơn hợp lệ | Đánh giá theo transactional policy, không tự mặc định deny/allow |
| Hard bounce xác minh recipient invalid | Notification tới cùng address | DENY_HARD_BOUNCE |
| Soft bounce đơn lẻ | Notification còn hợp lệ | Retry/defer theo policy, không hard suppress |
| Temporary hold còn hiệu lực | Newsletter | DEFER hoặc SKIP nếu hết deadline |
| Temporary hold đã hết nhưng consent bị rút | Newsletter | DENY_UNSUBSCRIBED |
| Complaint verified | Marketing cùng scope | DENY_COMPLAINT |
| Bounce 5.7.1 do sender auth | Recipient address | Không tự hard-suppress |
| Event webhook không có chữ ký hợp lệ | Bất kỳ | Không thay đổi suppression |
| Event duplicate providerEventId | Bất kỳ | Không tăng unique event/outcome lần hai |
| User opt-in lại list A | List A | Chỉ cho phép nếu không còn scope rộng cấm và deliverability hợp lệ |
| Provider account suppression | Tất cả tenant dùng account đó | Policy vận hành phản ánh account-level limit |
| Tenant A unsubscribe | Tenant B khác phạm vi | Không đổi tenant B |
| Scheduled job sau unsubscribe | Marketing job còn PENDING | SKIPPED trước SMTP |
| Unsubscribe đến sau SMTP accepted | Message cũ | Giữ lịch sử accepted, chặn future sends |
| Recipient đổi địa chỉ | Email mới đã verify | Đánh giá contact preference và suppression theo address mới |

### Nên test precedence của nhiều lý do đồng thời

Ví dụ recipient:

~~~text
UNSUBSCRIBED_MARKETING = true
TEMPORARY_BOUNCE_HOLD = true
~~~

Policy có thể chọn primary reason **UNSUBSCRIBED_MARKETING**, nhưng audit vẫn phải giữ temporary hold để sau này không tự cho phép gửi khi hold hết hạn.

Test không nên chỉ assert boolean false; nên assert **decision code** và side effect kỳ vọng (không tạo attempt, không tự đổi consent).

## 52. Kiểm thử one-click HTTP endpoint

Những ca cần kiểm tra:

1. POST hợp lệ với Content-Type **application/x-www-form-urlencoded** và body **List-Unsubscribe=One-Click**.
2. POST lần đầu tạo preference UNSUBSCRIBED đúng tenant/list.
3. POST lần hai **idempotent**, không tạo duplicate audit side effect.
4. GET cùng URL **không thay đổi preference**.
5. POST thiếu marker hoặc marker sai không được silently áp dụng.
6. Token không hợp lệ/hết hạn/revoked xử lý theo contract mà không lộ contact existence.
7. Token của tenant A không thay đổi row tenant B.
8. Token LIST A không hủy LIST B hoặc toàn bộ account.
9. Endpoint không yêu cầu cookie/login/CSRF token của một browser session.
10. Endpoint có thể bị rate limited mà không ảnh hưởng người nhận hợp lệ bất thường.
11. Link scanner chỉ thực hiện GET, preference vẫn giữ nguyên.
12. Domain HTTPS, certificate và redirect behavior phù hợp one-click.
13. Token không xuất hiện trong logs/traces hoặc Referrer không được kiểm soát.
14. DKIM signature trên email cuối bao phủ hai unsubscribe headers cần thiết.

Ví dụ ý tưởng với **Spring MockMvc**:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OneClickUnsubscribeWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void postSupportsOneClickPayload() throws Exception {
        String token = createValidTestToken();

        mvc.perform(post("/mail/unsubscribe/{token}", token)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .content("List-Unsubscribe=One-Click"))
                .andExpect(status().isOk());

        // Assertion bổ sung: scope đúng đã UNSUBSCRIBED;
        // message khác scope không bị ảnh hưởng.
    }

    @Test
    void getMustNotUnsubscribe() throws Exception {
        String token = createValidTestToken();

        mvc.perform(get("/mail/unsubscribe/{token}", token))
                .andExpect(status().isMethodNotAllowed());

        // Assertion bổ sung: preference trong DB không đổi.
    }

    private String createValidTestToken() {
        // Test fixture: sinh token và row thuộc tenant/list thử nghiệm.
        throw new UnsupportedOperationException("Fixture required");
    }
}
~~~

Đây là **skeleton minh họa**, phương thức fixture cần được triển khai trong test project và cấu hình Spring Security phải cho phép POST public hợp lệ theo đúng giới hạn endpoint. Không dùng test này để kết luận DKIM đã được ký; phần đó cần test email thực tế sau khi đi qua ESP/gateway.

### Test endpoint riêng chưa đủ

Nếu chỉ assert HTTP 200 mà không xem database và worker, có thể bỏ sót lỗi:

~~~text
POST -> HTTP 200
DB -> UNSUBSCRIBED
Worker cache -> vẫn SUBSCRIBED
SMTP -> vẫn gửi marketing
~~~

Một integration test nên kích hoạt một job đã lên lịch trước POST, thực hiện unsubscribe, sau đó cho worker chạy và xác nhận **không có SMTP attempt mới**.

## 53. Kiểm thử bounce và feedback ingestion

Có thể dùng webhook fixture giả lập, DSN MIME fixture, database thử nghiệm và SMTP capture server.

### Webhook integration tests

| Trường hợp | Kết quả |
|---|---|
| Chữ ký hợp lệ, event ID mới | Lưu event và apply policy phù hợp |
| Chữ ký sai | Reject; không đổi suppression |
| Cùng event ID gửi hai lần | Một unique event/transition |
| Event của provider account khác | Không map nhầm tenant |
| Hard bounce 5.1.1 có correlation | Suppress recipient theo rule |
| Policy reject 5.7.1 | Điều tra sender; không hard-suppress nếu chưa xác minh recipient-invalid |
| Soft bounce 4.2.2 | Ghi transient/hold, không tự permanent |
| Delivered tới trước deferred cũ | Không đảo ngược trạng thái bởi stale event |
| Complaint có recipient mapping | Áp dụng complaint policy |
| Complaint không có recipient identity | Ghi tín hiệu aggregate, không bịa recipient |
| Missing provider event ID | Dùng contract/fingerprint fallback hoặc quarantine |
| Webhook handler crash sau DB commit | Provider retry được dedup; worker tiếp tục |
| Event mới nhưng provider API unavailable | Persist để retry; không drop |
| Một message nhiều recipients | Chỉ cập nhật recipient liên quan |
| Unmatched event | Quarantine/reconciliation, không ghi suppression bừa |

### DSN integration tests

Một DSN có:

~~~text
multipart/report; report-type=delivery-status
Final-Recipient: rfc822; user@example.net
Action: failed
Status: 5.1.1
~~~

phải được parse thành event có cấu trúc và **đối chiếu notification-recipient**. Khi một mail thường giả Subject “Mail delivery failed”, không được đi thẳng vào hard suppression.

Test khác:

- DSN có nhiều Final-Recipient sections.
- DSN thiếu Message-ID nhưng có VERP token.
- DSN có MIME malformed hoặc vượt size limit.
- DSN lặp sau IMAP reconnect.
- DSN có account/tenant không khớp.
- DSN chứa một phần email gốc nhạy cảm, không bị ghi raw vào log.

### SMTP tests

Với test SMTP server như GreenMail/Mailpit:

- Khi recipient đã unsubscribe thì **JavaMailSender.send(...) không được gọi**.
- Khi temporary hold còn hiệu lực, không được gửi lại trước next allowed time.
- Header **List-Unsubscribe** và **List-Unsubscribe-Post** được sinh cho những thư phù hợp.
- Message transactional theo policy không vô tình chứa token hoặc header từ tenant khác.
- Không sửa JavaMailSenderImpl singleton theo account giữa các thread, gây sai MAIL FROM.

Các test chỉ kiểm chứng MIME do app tạo. DKIM, Return-Path cuối, provider suppression behavior và webhook end-to-end phải được kiểm tra qua sandbox/provider theo khả năng thực tế.

## 54. Runbook khi hard bounce tăng bất thường

Một alert **HardBounceSurge** phải dẫn tới điều tra nguyên nhân thay vì tự động gỡ/xóa một loạt recipient.

### Bước 1 — Kiểm tra số liệu có thật không

- Webhook requests có tăng vì provider retry cùng event không?
- Unique provider event IDs và unique bounced notifications có tăng tương ứng không?
- Có thay đổi schema/parser/webhook source không?
- Có dữ liệu delivery đến muộn từ campaign cũ không?
- Đang dùng bounce arrival rate hay mature-cohort bounce ratio?

### Bước 2 — Xác định phạm vi

- Một ESP account hay mọi provider?
- Một tenant/list/campaign hay toàn bộ hệ thống?
- Một recipient domain hay nhiều domain?
- Một sender domain/MAIL FROM profile hay mọi profile?
- Có thay đổi SPF/DKIM/DMARC gần đây không?
- Có import danh sách mới hoặc thay consent acquisition flow không?

### Bước 3 — Phân loại lỗi

| Nhóm tăng | Hướng điều tra |
|---|---|
| **invalid_recipient** | Chất lượng dữ liệu/địa chỉ, validation, stale contacts |
| **policy_rejection** | SPF/DKIM/DMARC, reputation, content, sender policy |
| **mailbox_full** | Temporary hold, provider retry, recipient domain |
| **provider_throttle** | Rate/quota/backpressure, không hard suppress |
| **unknown/malformed** | Parser, correlation, webhook version |
| **complaint** | Consent, frequency, content, list hygiene |

### Bước 4 — Giảm tác động

- Nếu nhiều recipients được xác nhận invalid, ngăn tiếp tục gửi vào những địa chỉ đó.
- Nếu sender auth bị lỗi, sửa cấu hình domain/account hoặc tạm dừng tuyến gửi có vấn đề; không hard suppress hàng loạt recipient.
- Nếu provider throttle, điều tiết rate, backoff và bảo vệ stream quan trọng.
- Nếu complaint tăng, rà soát campaign và cân nhắc tạm dừng marketing theo quy trình.
- Nếu webhook giả mạo hoặc signature sai, ngăn cập nhật policy từ nguồn đó và kiểm tra secret/config.
- Không dùng provider khác để né lệnh chặn do chính sách chống spam.

### Bước 5 — Đối soát và phục hồi

- So sánh provider exports/API với event ledger.
- Xem những notification đã được accepted trước khi phát sinh bounce.
- Xem suppression mới có đúng scope/recipient không.
- Nếu phân loại nhầm, sử dụng một **controlled correction workflow** có audit, không xóa dấu vết lỗi.
- Theo dõi cohort tiếp theo sau khi khắc phục để xác nhận deliverability cải thiện.

## 55. Runbook khi người dùng nói đã unsubscribe nhưng vẫn nhận email

Trường hợp này cần ưu tiên vì nó có thể phản ánh lỗi chính sách và ảnh hưởng niềm tin.

### Bước 1 — Xác nhận sự kiện unsubscribe

- Người dùng nhấn **one-click**, trang preference hay mailto?
- Có HTTP POST vào đúng endpoint không?
- Request trả mã gì? Có gặp CSRF/security filter không?
- Token ánh xạ tới tenant, recipient và list nào?
- Preference đã được commit lúc nào?
- User đã chọn hủy list hiện tại hay toàn bộ marketing?

Không yêu cầu người dùng cung cấp full token qua kênh hỗ trợ công khai. Nhân viên hỗ trợ nên tra cứu thông qua ID nội bộ có quyền, tránh làm lộ bearer capability.

### Bước 2 — Kiểm tra email nhận sau đó

- Đây có phải **email marketing thuộc scope đã hủy** không?
- Notification được tạo, claim, bắt đầu SMTP và accepted lúc nào?
- Email có được provider nhận trước khi user unsubscribe nhưng giao tới inbox sau đó không?
- Có một email khác thuộc loại transactional/security thực sự không?
- Email có được gửi từ tenant/brand khác không?

Một email đến inbox sau unsubscribe không tự động chứng minh application đã **bắt đầu submission sau effective_at**. Có thể nó nằm trong hàng chuyển phát của provider trước đó. Tuy nhiên, vẫn cần đối soát và giải thích trung thực.

### Bước 3 — Kiểm tra policy propagation

~~~text
Unsubscribe endpoint
      |
      +-- DB decision?
      +-- Audit event?
      +-- Cache invalidation?
      +-- Outbox pending jobs?
      +-- Eligibility final gate?
      +-- ESP provider suppression sync?
~~~

Nếu worker dùng cache stale, cần sửa invalidation/consistency chứ không chỉ tăng TTL hoặc hủy thủ công một job duy nhất.

### Bước 4 — Ngăn gửi thêm và xử lý sự cố

1. Xác nhận preference UNSUBSCRIBED đúng scope được lưu bền vững.
2. Chặn những notification PENDING/RETRY_WAIT áp dụng.
3. Nếu cần, tạm dừng campaign/tuyến đang vi phạm để không tiếp tục gửi.
4. Không đổi trạng thái SUBMITTED thành CANCELLED như thể mail đã được thu hồi.
5. Xem lịch sử provider, application attempts và điểm thời gian.
6. Ghi nhận incident, root cause và biện pháp chống tái diễn.

### Bước 5 — Kiểm tra lại

Tạo một notification thử trong môi trường kiểm thử cùng policy/scope. Xác nhận **eligibility gate trả DENY**, **không gọi SMTP** và không có side effect trái với lựa chọn người dùng.

Không gửi thêm một email marketing “để thử unsubscribe đã hoạt động” tới chính người đã yêu cầu ngừng nhận.

## 56. Các anti-pattern thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp hơn |
|---|---|---|
| Coi JavaMailSender.send thành công là delivered | Không xử lý bounce bất đồng bộ | Tách submission và delivery feedback |
| Coi mọi MailSendException là hard bounce | Suppress nhầm khi DNS/TLS/auth lỗi | Phân loại transport vs delivery |
| Coi mọi SMTP 5xx là mailbox không tồn tại | Xóa nhầm danh sách do sender policy | Parse enhanced code và ngữ cảnh |
| Coi mọi 4xx là hard bounce sau một lần | Chặn recipient tạm thời lỗi | Retry/backoff/temporary hold |
| Dùng địa chỉ nhận bounce làm recipient suppression key | Chặn sai đối tượng | Phân biệt MAIL FROM và RCPT TO |
| Set Return-Path header để điều khiển envelope | DSN đi sai tuyến hoặc bị provider rewrite | Cấu hình MAIL FROM/provider đúng cách |
| Sửa JavaMailSenderImpl singleton theo tenant | Gửi nhầm credential/MAIL FROM | Sender profile bất biến và routing |
| Tin bounce email chỉ qua Subject | DSN giả mạo tạo suppression | Parse DSN cấu trúc và correlation |
| Tin webhook không verify chữ ký | Kẻ ngoài sửa trạng thái người nhận | Raw-body signature verification |
| Đếm mỗi webhook request là một bounce | Tăng giả khi provider retry | Unique event ledger |
| Dùng HTTP arrival time để ghi đè delivery state | Stale deferred event lùi trạng thái | Event-time/transition rules |
| Một enum SENT/BOUNCED/UNSUBSCRIBED chung | Mất thông tin delivery và consent | State tách message/contact/preference |
| Suppress toàn bộ domain vì một 5.1.1 | Ảnh hưởng người nhận hợp lệ khác | Recipient-scoped evidence |
| Xóa suppression tự động sau 30 ngày | Gửi lại địa chỉ invalid/complaint | Policy gỡ theo reason |
| Subscribe lại vì ESP báo delivered | Bỏ qua lựa chọn người nhận | Explicit new consent |
| GET link thực hiện unsubscribe | Link scanner gây hủy ngoài ý muốn | One-click HTTPS POST |
| One-click cần login/confirmation | Không hoàn tất cơ chế one-click | Scoped token + idempotent POST |
| URL chứa địa chỉ email rõ ràng | PII leak và enumeration | Opaque token |
| Token cho phép hủy mọi tenant/list | Vượt phạm vi quyền | Token scoped theo recipient/list/tenant |
| Unsubscribe endpoint phụ thuộc CSRF session | Provider POST bị 403 | CSRF exception hẹp, token-based authorization |
| Tắt CSRF toàn app để sửa one-click | Rủi ro cho user sessions | Chỉ miễn endpoint phù hợp |
| Gửi marketing theo consent snapshot lúc enqueue | Gửi sau unsubscribe | Final eligibility trước SMTP |
| Cache preference không invalidate | Worker gửi theo dữ liệu cũ | Durable source + propagation |
| Bỏ qua suppression khi gắn nhãn TRANSACTIONAL | Tiếp tục gửi vào invalid address | Policy riêng nhưng vẫn kiểm tra deliverability |
| Gộp recipient ở các tenant vì cùng địa chỉ | Cross-tenant suppression leak | Scope tenant/brand/provider rõ |
| Dùng email thô làm metrics label | PII leak, cardinality cao | Dimension hữu hạn và trace có quyền |
| Dùng unsubscribe count làm unique recipients | Double-count request retries | Distinct transitions |
| Retry lại toàn batch khi một recipient bounce | Gửi trùng người đã thành công | Per-recipient result/policy |
| Gỡ provider suppression bừa bãi | Vi phạm account policy, tăng complaint | Reconcile và xác minh nguyên nhân |

## 57. Checklist triển khai production

**Thiết kế domain**

1. Có phân biệt **recipient bị bounce** và **MAIL FROM/bounce mailbox** chưa?
2. Đã có taxonomy hard/soft/policy/complaint/unknown chưa?
3. Có tách **subscription preference** khỏi **deliverability suppression** không?
4. Có chính sách scope theo tenant, brand, stream và list không?
5. Email transactional và marketing được phân loại dựa trên nội dung thực tế chưa?
6. Có rule phục hồi soft hold/hard bounce/complaint riêng không?

**Sending path**

7. Worker có kiểm tra consent/suppression gần lúc gửi không?
8. Có chặn job PENDING sau unsubscribe hoặc hard bounce không?
9. Có idempotency cho notification-recipient và retry không?
10. Có phân biệt SMTP accepted với delivered và UNKNOWN không?
11. Có kết quả per-recipient khi message nhiều To/Cc/Bcc không?
12. Sender profile, From, MAIL FROM, DKIM và tenant ownership có đúng không?

**One-click unsubscribe**

13. Email phù hợp có **List-Unsubscribe** và **List-Unsubscribe-Post** không?
14. HTTPS one-click endpoint chấp nhận form POST đúng contract không?
15. GET có tuyệt đối không tự cập nhật preference không?
16. Endpoint có idempotent, không yêu cầu login/confirmation không?
17. Token có entropy đủ, scope hẹp, không chứa PII không?
18. Có chính sách token lifetime/revocation cho email cũ không?
19. CSRF exception có chỉ áp dụng cho endpoint token-based không?
20. Header one-click có được DKIM ký và còn nguyên khi qua ESP không?
21. Có link hủy/điều chỉnh nhận thư rõ ràng trong body theo policy không?

**Bounce/DSN feedback**

22. Webhook có verify chữ ký trên raw body không?
23. Có dedup provider event ID và lưu event bền vững không?
24. Có mapping event về provider account, tenant, notification-recipient không?
25. Có xử lý event out of order không?
26. DSN parser có kiểm tra multipart/report và status fields không?
27. Có chống DSN giả/backscatter và unmatched events không?
28. Có giữ provider taxonomy/raw code để điều tra không?

**State và dữ liệu**

29. Có atomic preference transitions và audit không?
30. Re-opt-in có cần bằng chứng mới và không tự gỡ suppression khác không?
31. Cache và provider suppression được đồng bộ có theo dõi lag không?
32. Có reconciliation khi webhook/API thất bại không?
33. Có giới hạn PII, token, raw DSN và retention không?
34. Tenant A có được ngăn xem/chỉnh dữ liệu tenant B không?

**Kiểm thử và vận hành**

35. Đã kiểm thử one-click POST lặp, GET không side effect và token sai scope chưa?
36. Đã kiểm thử webhook invalid signature, duplicate và out-of-order chưa?
37. Đã kiểm thử hard vs soft bounce và sender policy 5.7.x chưa?
38. Đã kiểm thử unsubscribe xảy ra khi job đã được enqueue chưa?
39. Đã kiểm thử cache stale và provider sync failure chưa?
40. Đã có metric mature-cohort bounce ratio và unique unsubscribe transitions chưa?
41. Đã có alert cho policy-rejection surge và one-click endpoint outage chưa?
42. Có runbook cho bounce spike và complaint/unsubscribe incident chưa?

Checklist này không có nghĩa chỉ cần thêm một vài header vào MIME là hệ thống đã tuân thủ mọi yêu cầu deliverability hoặc pháp lý. Các cấu hình provider, quy trình xác minh, dữ liệu consent và quy định hiện hành đều phải được làm rõ trước khi vận hành.

## 58. Ghi nhớ

**Policy xử lý địa chỉ bounce và unsubscribe** trong Spring Framework Mail cần giải quyết song song **khả năng chuyển phát** và **quyền/lựa chọn của người nhận**, không được gộp chúng thành một cờ “sendAllowed” không có nguồn gốc.

Những nguyên tắc quan trọng nhất:

1. **Bounce và unsubscribe khác nhau:** bounce nói về delivery, unsubscribe nói về preference; spam complaint là tín hiệu riêng.
2. **MAIL FROM/Return-Path không phải recipient bị bounce.** Cần cấu hình bounce routing và correlation chính xác.
3. **Hard bounce chỉ nên suppress khi có bằng chứng recipient không khả dụng; soft bounce thường cần retry/hold; policy rejection cần điều tra sender.**
4. **List-Unsubscribe và RFC 8058 one-click** yêu cầu endpoint HTTPS POST thực sự xử lý opt-out, GET không có side effect, token được giới hạn phạm vi và header được ký phù hợp.
5. **Subscription và suppression là hai nguồn dữ liệu độc lập**: gỡ bounce không tự subscribe lại, và opt-in mới không tự bỏ qua một địa chỉ invalid.
6. **Webhook/DSN là nguồn dữ liệu bên ngoài**: phải xác minh, deduplicate, correlate theo notification-recipient và xử lý out-of-order.
7. **Outbox worker phải kiểm tra policy ngay trước SMTP**; một email đã lên lịch trước khi unsubscribe vẫn có thể phải SKIPPED.
8. **SMTP không có rollback chung với database**; khi email đã gửi hoặc kết quả UNKNOWN, không thể khẳng định unsubscribe/cancellation thu hồi được thư cũ.
9. **Cô lập tenant, token và dữ liệu cá nhân**, đồng thời lưu audit, đồng bộ provider/cache và quan sát những chính sách có hiệu lực.
10. **Đo đúng đơn vị và điều tra theo cohort/reason**, không đếm webhook retries hoặc tất cả SMTP 5xx như hard bounce.

**Mục tiêu của policy tốt không chỉ là giảm bounce rate hay có nút hủy đăng ký, mà là bảo đảm mỗi quyết định gửi hoặc ngừng gửi đều có đúng nguồn bằng chứng, đúng phạm vi, đúng thời điểm và có thể giải thích, kiểm thử cũng như khôi phục an toàn.**










