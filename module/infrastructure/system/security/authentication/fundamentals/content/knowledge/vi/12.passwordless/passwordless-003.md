# Magic link — Đăng nhập không mật khẩu bằng liên kết dùng một lần

> **Chương:** Passwordless  
> **Chủ đề:** Magic link  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào liên kết đăng nhập gửi qua email, ranh giới tin cậy của hộp thư, bảo vệ token, chống phát lại và quản lý phiên an toàn.

## 1. Magic link là gì?

**Magic link** là một liên kết chứa hoặc tham chiếu đến một token có thể được dùng để hoàn tất một hành động xác thực mà không yêu cầu người dùng nhập mật khẩu. Ứng dụng thường gửi liên kết đến địa chỉ email người dùng đã khai báo; khi người dùng mở và xác nhận liên kết, server kiểm tra token rồi tạo phiên đăng nhập hoặc hoàn thành một tác vụ đã định nghĩa.

Ví dụ, người dùng nhập `mai@example.org` ở màn hình đăng nhập. Server tạo yêu cầu đăng nhập ngắn hạn và gửi email có nút “Đăng nhập”. Người dùng mở email trên thiết bị của mình, nhấn liên kết và hoàn tất bước xác nhận. Nếu token hợp lệ, chưa hết hạn, đúng mục đích và chưa được dùng, server có thể xác định account tương ứng và tạo session.

Magic link thường được gọi là **passwordless sign-in**, nhưng cần hiểu chính xác bằng chứng được kiểm tra: server đang dựa vào khả năng kiểm soát hộp thư hoặc kênh nhận liên kết tại thời điểm sử dụng. Nó **không tự chứng minh danh tính pháp lý**, không chứng minh người bấm link là một cá nhân cụ thể, và không tự động là MFA.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích magic link chứng minh điều gì và giới hạn của bằng chứng đó.
2. Phân biệt liên kết đăng nhập, xác minh email, khôi phục tài khoản và liên kết danh tính.
3. Thiết kế token ngẫu nhiên, thời hạn, mục đích, account binding và cơ chế sử dụng một lần.
4. Xử lý email scanner/link preview mà không vô tình tiêu thụ token khi chỉ tải trang.
5. Ngăn replay, enumeration, open redirect, rò rỉ token và lạm dụng gửi email.
6. Tạo phiên sau xác thực và tích hợp magic link với MFA, passkey, tenant và chính sách rủi ro.

## 2. Magic link chứng minh điều gì?

Một liên kết đăng nhập thường là một **bearer credential**: bên nào nắm được token hợp lệ đều có khả năng sử dụng token trong phạm vi và thời hạn được cấp. Khi server chấp nhận liên kết gửi qua email, kết luận hợp lý là:

> Bên đang hoàn tất giao dịch đã kiểm soát được token được gửi tới hộp thư gắn với yêu cầu đăng nhập, theo các kiểm soát của hệ thống.

Kết luận này phụ thuộc vào nhiều giả định: email được gửi tới đúng địa chỉ, hộp thư chưa bị chiếm, token chưa bị chuyển tiếp hoặc đánh cắp, URL không bị rò rỉ và server kiểm tra đúng giao dịch. Nếu hộp thư bị chiếm, kẻ tấn công có thể lấy liên kết và đăng nhập mà không cần biết mật khẩu của tài khoản ứng dụng.

| Điều được kiểm tra | Điều không thể tự suy ra |
| --- | --- |
| Token đúng với yêu cầu server đã tạo | Người bấm link là chủ thể pháp lý có tên trong hồ sơ. |
| Token được dùng trong thời hạn cho phép | Hộp thư sẽ luôn do cùng một người kiểm soát. |
| Token gắn với một account hoặc yêu cầu cụ thể | Người dùng đã chứng minh yếu tố độc lập thứ hai. |
| Token chưa bị sử dụng và chưa bị thu hồi | Thiết bị hiện tại không có mã độc hoặc không bị chia sẻ. |
| Người dùng có thể truy cập email nhận liên kết tại thời điểm đó | Phiên sau đăng nhập sẽ an toàn mãi mãi. |

**Magic link thường là một phương thức xác thực dựa trên quyền truy cập email**, không phải một cơ chế MFA độc lập theo mặc định. Nếu hộp thư được bảo vệ bằng mật khẩu và MFA, điều đó có thể làm tăng bảo vệ của kênh email, nhưng ứng dụng RP không nên tự khẳng định đã xác minh các yếu tố đó nếu không có bằng chứng và quan hệ tin cậy tương ứng.

## 3. Phân biệt các loại liên kết có thể gửi qua email

Một URL có thể trông giống nhau nhưng phục vụ mục đích bảo mật khác nhau. Server phải lưu rõ **purpose** và không cho token của mục đích này sử dụng ở mục đích khác.

| Loại liên kết | Mục đích | Kết quả khi hoàn tất |
| --- | --- | --- |
| **Magic link sign-in** | Chứng minh khả năng truy cập hộp thư gắn với yêu cầu đăng nhập | Tạo phiên đăng nhập hoặc hoàn thành xác thực theo policy. |
| **Email verification** | Xác nhận địa chỉ email có thể nhận liên kết | Đánh dấu địa chỉ đã xác minh; không nhất thiết đăng nhập. |
| **Password reset** | Cho phép thay credential mật khẩu đã quên | Đổi/reset mật khẩu; có thể thu hồi phiên và yêu cầu đăng nhập lại. |
| **Account recovery** | Phục hồi quyền kiểm soát tài khoản khi mất authenticator | Chạy quy trình phục hồi với mức bằng chứng riêng. |
| **Identity linking** | Gắn email/IdP/credential mới vào account đang tồn tại | Tạo quan hệ danh tính sau khi xác thực các phía cần thiết. |
| **Invitation** | Mời một người tham gia tenant hoặc workspace | Tạo membership theo lời mời, vai trò và policy đã được duyệt. |

Không nên tạo một loại token chung kiểu `valid=true` rồi để endpoint quyết định diễn giải tùy ý. Một token xác minh email không được phép trở thành token reset mật khẩu; token đăng nhập không được dùng để thêm IdP; invitation không được cấp quyền ngoài tenant hoặc vai trò trong lời mời.

**Purpose binding** cần được thực thi ở server. URL hoặc tham số `purpose=login` do client gửi không thể thay thế mục đích đã lưu trong bản ghi token.

## 4. Luồng magic link từ yêu cầu đến phiên đăng nhập

Một luồng điển hình có hai giai đoạn: **yêu cầu liên kết** và **hoàn tất liên kết**.

~~~mermaid
flowchart TD
    A["Người dùng nhập email"] --> B["Server chuẩn hóa theo policy và giới hạn lạm dụng"]
    B --> C["Tạo giao dịch token ngẫu nhiên, ngắn hạn"]
    C --> D["Gửi email qua kênh đã cấu hình"]
    D --> E["Người dùng mở liên kết"]
    E --> F["GET hiển thị trang xác nhận, chưa tiêu thụ token"]
    F --> G["Người dùng chủ động nhấn Continue"]
    G --> H["POST token + giao dịch xác nhận"]
    H --> I{"Token đúng, còn hạn, đúng purpose/account, chưa dùng?"}
    I -- "Không" --> J["Từ chối an toàn"]
    I -- "Có" --> K["Tiêu thụ nguyên tử token"]
    K --> L["Tạo principal và session mới"]
    L --> M["Chuyển tới trang đích đã cho phép"]
~~~

### Giai đoạn 1: yêu cầu gửi liên kết

1. Người dùng cung cấp identifier, thường là email.
2. Server kiểm tra cú pháp và áp dụng quy tắc chuẩn hóa email nhất quán.
3. Server áp dụng rate limit và kiểm soát gửi thư theo account, địa chỉ, IP, thiết bị và tổng lưu lượng.
4. Nếu account đủ điều kiện, server tạo token mới, lưu thông tin xác minh và gửi email qua một origin đáng tin cậy.
5. Client nhận phản hồi chung, không tiết lộ account có tồn tại hay không.

### Giai đoạn 2: hoàn tất liên kết

1. Trình duyệt tải trang đích qua HTTPS.
2. Server kiểm tra sơ bộ và hiển thị trang xác nhận; request GET không tự tiêu thụ token.
3. Người dùng chủ động xác nhận hành động.
4. Server nhận POST, xác minh token và giao dịch theo account, purpose, expiry và trạng thái đã dùng.
5. Server tiêu thụ token theo thao tác nguyên tử, tạo principal từ account ID nội bộ và cấp session mới.
6. Server chuyển hướng tới trang nội bộ đã được cho phép, không dựa vào URL tùy ý từ query string.

### Vì sao GET không nên tự đăng nhập?

Các hệ thống email thường dùng **link scanner, safe-link rewriting, preview bot hoặc proxy** để kiểm tra URL trước khi người dùng mở. Một số trình duyệt và ứng dụng cũng tải trước liên kết. Nếu chỉ một GET đã tiêu thụ token, scanner có thể sử dụng liên kết trước người dùng, khiến liên kết hết hiệu lực hoặc thậm chí tạo phiên ở môi trường không mong muốn.

Thiết kế nên dùng GET để hiển thị trang xác nhận, sau đó cần một thao tác POST có chủ đích để hoàn tất. Điều này giảm rủi ro do prefetch/scanner, nhưng không phải bảo đảm tuyệt đối trước mọi bot có khả năng mô phỏng tương tác. Hệ thống có rủi ro cao có thể cần thêm bước xác nhận, mã phụ hoặc ràng buộc giao dịch phù hợp.

## 5. Thiết kế token: ngẫu nhiên, ngắn hạn, một lần và đúng mục đích

Magic link an toàn bắt đầu từ token có entropy đủ lớn và cách lưu trữ đúng.

### 5.1. Sinh token bằng bộ sinh số ngẫu nhiên mật mã

Token cần được tạo bằng CSPRNG (cryptographically secure pseudorandom number generator), không dùng timestamp, số tăng dần, username, UUID phiên bản không phù hợp hoặc `Math.random()`.

Ví dụ khái niệm: tạo 32 byte ngẫu nhiên (256 bit), mã hóa Base64URL không padding để đưa vào URL. Độ dài token cần đủ để chống đoán trực tuyến; hệ thống vẫn phải rate limit và kiểm tra token ở server.

~~~java
byte[] randomBytes = new byte[32];
secureRandom.nextBytes(randomBytes);

String token = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(randomBytes);
~~~

Đây là ví dụ Java minh họa. Trong ứng dụng thực, dùng CSPRNG được cung cấp bởi nền tảng hoặc thư viện đã được kiểm chứng.

### 5.2. Không lưu token thô trong database

Vì token có thể dùng trực tiếp như bearer credential, database không nên lưu bản rõ nếu không cần. Có thể lưu digest của token rồi so sánh digest khi người dùng gửi lại. Với token ngẫu nhiên có entropy cao, SHA-256 phù hợp để tra cứu/so khớp digest; có thể cân nhắc HMAC với khóa server khi kiến trúc yêu cầu thêm lớp bảo vệ.

~~~text
Raw token:    chỉ được tạo để đưa vào email và nhận từ client
Stored value: SHA-256(raw token) hoặc HMAC(server_key, raw token)

Không log:
  raw token
  full magic-link URL
  email body chứa token
  session cookie / bearer token sau đăng nhập
~~~

Không nhầm token magic link với mật khẩu người dùng: mật khẩu có entropy khó dự đoán hơn nhiều trong thực tế và cần password hashing có salt/chi phí như Argon2id; token ngẫu nhiên có entropy cao có thể được lưu bằng digest nhanh để tra cứu.

### 5.3. Token phải gắn với account và purpose

Một bản ghi token nên có các trường tương đương:

~~~json
{
  "tokenDigest": "digest-value",
  "accountId": "account-1742",
  "purpose": "MAGIC_LINK_SIGN_IN",
  "issuedAt": "2026-11-22T10:00:00Z",
  "expiresAt": "2026-11-22T10:10:00Z",
  "consumedAt": null,
  "revokedAt": null,
  "emailVersion": 4,
  "tenantId": "tenant-alpha",
  "redirectKey": "account-home"
}
~~~

Đây là schema minh họa; không bắt buộc mọi hệ thống phải có tất cả trường. Các nguyên tắc cần giữ:

- **accountId:** token gắn với account đã được server xác định khi phát hành.
- **purpose:** chỉ cho phép đúng một loại hành động.
- **issuedAt / expiresAt:** có thời hạn rõ ràng và được kiểm tra theo đồng hồ server.
- **consumedAt:** ngăn dùng lại.
- **revokedAt:** cho phép vô hiệu hóa khi account, email hoặc policy thay đổi.
- **emailVersion:** tùy thiết kế, có thể làm token cũ mất hiệu lực khi địa chỉ liên hệ thay đổi.
- **tenantId:** nếu luồng login đã chọn tenant hoặc token chỉ có ý nghĩa trong tenant cụ thể, phải ràng buộc và kiểm tra lại.
- **redirectKey:** tham chiếu tới route nội bộ đã cho phép thay vì lưu URL tùy ý.

Không lấy account ID hoặc purpose từ body POST để ghi đè thông tin token đã lưu. Server phải tìm token digest và dùng bản ghi tin cậy để xác định account, mục đích và phạm vi.

### 5.4. Thời hạn và số token đang hoạt động

Liên kết đăng nhập thường có thời hạn ngắn, ví dụ vài phút đến khoảng mười lăm phút tùy rủi ro và trải nghiệm. Đây là lựa chọn chính sách, không phải một con số chuẩn cho mọi hệ thống. Thời hạn quá dài làm tăng cửa sổ sử dụng nếu email hoặc URL bị lộ; quá ngắn gây khó khăn khi email đến trễ hoặc người dùng chuyển thiết bị.

Khi gửi liên kết mới, có thể thu hồi các token cũ cùng account và purpose hoặc giữ một số lượng nhỏ theo chính sách. Nếu cho nhiều token cùng tồn tại, phải xác định rõ token nào được chấp nhận và cách thu hồi. Không để một liên kết cũ tiếp tục đăng nhập sau khi người dùng đã yêu cầu liên kết mới nếu policy quy định chỉ giữ token mới nhất.

## 6. Tiêu thụ token đúng một lần và chống replay

Một token hết hạn hoặc đã được sử dụng phải bị từ chối. Quan trọng hơn, thao tác tiêu thụ phải **nguyên tử**: hai request đến gần như đồng thời không được cùng hoàn tất một token.

Một cách triển khai SQL khái niệm:

~~~sql
UPDATE magic_link_tokens
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_digest = :digest
  AND purpose = 'MAGIC_LINK_SIGN_IN'
  AND expires_at > CURRENT_TIMESTAMP
  AND consumed_at IS NULL
  AND revoked_at IS NULL
RETURNING account_id, tenant_id, redirect_key;
~~~

Nếu câu lệnh trả về đúng một hàng, request đã giành quyền tiêu thụ token. Nếu không có hàng, token sai, hết hạn, đã dùng hoặc bị thu hồi. Cần thực hiện các bước liên quan trong transaction phù hợp và đảm bảo chỉ một request thành công.

Không làm theo kiểu:

1. SELECT token thấy `consumed_at IS NULL`.
2. Tạo session.
3. UPDATE token thành consumed.

Hai request song song có thể cùng đọc trạng thái chưa dùng và tạo hai session. Hãy dùng atomic update/row lock/transaction hoặc primitive tương đương được database bảo đảm.

### Các điều kiện phải kiểm tra

- Token tồn tại và digest khớp.
- Purpose đúng với endpoint hiện tại.
- Chưa hết hạn theo thời gian server.
- Chưa bị consume hoặc revoke.
- Account vẫn hoạt động và được phép đăng nhập.
- Email/account binding vẫn còn hợp lệ theo policy.
- Tenant, nếu có, vẫn active và account còn membership.
- Giao dịch hoàn tất đúng flow và không bị thay đổi giữa các bước.

**Replay** có thể xảy ra khi token bị copy từ email, log, browser history, proxy hoặc thiết bị dùng chung. One-time use và atomic consumption làm giảm khả năng sử dụng lại sau lần thành công đầu tiên, nhưng không ngăn kẻ tấn công sử dụng token bị đánh cắp **trước** người dùng hợp lệ. Cần bảo vệ toàn bộ đường truyền và nơi token xuất hiện.

## 7. Link scanner, preview và trình duyệt: xử lý an toàn

Magic link thường bị quét trước khi người dùng mở. Thiết kế sai có thể biến công cụ bảo vệ email thành tác nhân tiêu thụ token.

### 7.1. GET chỉ hiển thị trang xác nhận

Một pattern an toàn hơn:

~~~text
GET /auth/magic/confirm?token=<opaque-token>
  - Không tạo session
  - Không consume token
  - Không thay đổi email/account/credential
  - Hiển thị nút xác nhận hoặc thông tin hướng dẫn
  - Không tải analytics/third-party script có thể nhận URL

POST /auth/magic/complete
  - Nhận token từ form hoặc request body
  - Xác minh CSRF/origin và giao dịch
  - Consume token nguyên tử
  - Tạo session mới
  - Redirect sang route nội bộ đã cho phép
~~~

Không đặt token trong request log, analytics event, exception message, tracing span hoặc thông báo lỗi. Cần cấu hình reverse proxy/CDN để loại bỏ query parameter nhạy cảm khỏi access log. Nếu framework tự ghi URL đầy đủ, phải điều chỉnh middleware hoặc dùng thiết kế truyền token tránh log.

### 7.2. Bảo vệ trang xác nhận

- Chỉ dùng HTTPS và origin cố định đã cấu hình.
- Thiết lập `Referrer-Policy: no-referrer` cho trang chứa token; hạn chế nội dung bên thứ ba, pixel tracking và script không cần thiết.
- Áp dụng Content Security Policy phù hợp và tránh nhúng widget/analytics nhận URL.
- Sau khi lấy token vào giao dịch xác nhận, có thể chuyển sang URL sạch để giảm token nằm trong thanh địa chỉ/lịch sử; cần đảm bảo không làm lộ token qua log hoặc redirect.
- Không tự động submit form chỉ vì trang vừa tải.
- Kiểm tra CSRF/origin theo mô hình ứng dụng; token magic link là bearer secret, nên endpoint hoàn tất cần được thiết kế cẩn thận để website khác không thể ép trình duyệt dùng giao dịch không mong muốn.
- Không phản chiếu token vào HTML, error page hoặc nội dung trả về.

GET không consume giúp chống scanner phổ biến nhưng **không đủ để chống mọi bot**. Có scanner thực hiện tương tác nâng cao; nếu rủi ro yêu cầu, có thể dùng mã xác nhận bổ sung, user interaction rõ ràng hoặc phương thức chống phishing mạnh hơn.

### 7.3. Link rewriting và URL bị biến đổi

Một số hệ thống email bọc URL qua dịch vụ kiểm tra an toàn. Ứng dụng nên kiểm thử liên kết trong các môi trường email mục tiêu, đảm bảo token không bị cắt, giải mã sai hoặc biến đổi encoding. Token Base64URL tránh một số ký tự gây vấn đề trong query string, nhưng vẫn cần encode đúng theo URL và kiểm tra giới hạn độ dài.

## 8. Bảo vệ email và kênh gửi liên kết

Email là một phần của ranh giới tin cậy. Server có thể bảo vệ token tốt nhưng vẫn gửi đến sai địa chỉ, bị lộ qua dịch vụ email hoặc cho phép gửi hàng loạt.

Các kiểm soát:

- Gửi từ domain và địa chỉ được cấu hình, có SPF, DKIM và DMARC phù hợp để giảm giả mạo domain gửi.
- Dùng template rõ ràng: tên dịch vụ, yêu cầu đăng nhập vừa được tạo, thời hạn, nút/link chính thức và cách báo cáo nếu không phải người yêu cầu.
- Hiển thị domain đích dễ nhận biết; không dùng URL rút gọn hoặc redirect qua domain không liên quan.
- Không đưa password, OTP, token phụ hoặc thông tin cá nhân không cần thiết vào email.
- Có rate limit và quota cho mỗi email, account, IP, tenant và toàn hệ thống; ngăn attacker gửi hàng trăm link làm phiền nạn nhân.
- Gửi thông báo khi có yêu cầu đăng nhập bất thường theo policy, nhưng tránh tiết lộ account tồn tại cho người yêu cầu chưa xác thực.
- Xử lý bounce, email sai, email bị thay đổi và sự kiện deliverability; không coi “đã gửi thành công” là “người dùng đã nhận”.
- Có cơ chế chống gửi lại liên tục và cooldown hợp lý, nhưng tránh để attacker khóa vĩnh viễn người dùng hợp lệ bằng cách spam request.

SPF/DKIM/DMARC giúp xác thực domain gửi theo các cơ chế email, nhưng không bảo vệ khi hộp thư thật bị chiếm, token bị forward hoặc người dùng bị lừa nhấn link giả. Chúng là lớp bảo vệ kênh gửi, không thay thế token security.

## 9. Phishing và giới hạn chống phishing của magic link

Magic link thường dễ dùng nhưng **không mặc định phishing-resistant**. Kẻ tấn công có thể:

1. Gửi email giả với nút đăng nhập trỏ đến website giả.
2. Thuyết phục người dùng mở một link đăng nhập giả hoặc chuyển tiếp email thật.
3. Thu token hoặc URL chứa token mà người dùng copy/paste.
4. Sử dụng token trước khi hết hạn nếu nó chưa được consume.

Một link thật có domain đúng giúp người dùng nhận biết, nhưng không ngăn mọi kỹ thuật social engineering. Token là bearer credential; người có token có thể sử dụng trong phạm vi nó cho phép.

| Rủi ro | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Email giả mạo | Email trông như từ dịch vụ thật | SPF/DKIM/DMARC, template rõ ràng, domain dễ nhận biết, cảnh báo. |
| Link giả | Nút trỏ tới domain gần giống | Hiển thị domain chính thức, không dùng URL rút gọn, giáo dục người dùng. |
| Token bị forward | Người dùng gửi email đăng nhập cho người khác | Cảnh báo không chia sẻ; token ngắn hạn, một lần; đánh giá thêm ràng buộc theo rủi ro. |
| Mailbox takeover | Kẻ tấn công kiểm soát email | Bảo vệ account email, recovery mạnh, hỗ trợ passkey hoặc MFA trong ứng dụng. |
| Token theft | URL bị lộ trong log/history/analytics | Redact log, no-referrer, HTTPS, không script bên thứ ba, consume một lần. |
| AiTM | Proxy thu token và chuyển tiếp | Magic link không tự chống AiTM; ưu tiên WebAuthn/passkey cho yêu cầu phishing resistance. |

Nếu nghiệp vụ đòi hỏi chống phishing mạnh, **passkey/WebAuthn** thường phù hợp hơn vì chữ ký được ràng buộc với RP ID/origin. Có thể giữ magic link làm phương án truy cập dự phòng cho nhóm rủi ro thấp, nhưng phải định nghĩa rõ phương thức dự phòng không được dùng để vượt chính sách bắt buộc cho tài khoản nhạy cảm.

## 10. Cùng thiết bị và khác thiết bị

Người dùng có thể mở email trên cùng thiết bị đang đăng nhập hoặc trên thiết bị khác.

### Cùng thiết bị

Browser nhận token, hiển thị trang xác nhận và hoàn tất trong cùng môi trường. Trải nghiệm thuận tiện, có thể kết hợp với giao dịch pending trong cookie ngắn hạn. Tuy nhiên cookie không phải bằng chứng độc lập nếu thiết bị đã bị chiếm.

### Khác thiết bị

Người dùng yêu cầu link trên laptop nhưng mở email trên điện thoại. Nếu token là bearer, điện thoại có thể hoàn tất đăng nhập cho browser hoặc thiết bị đã yêu cầu, tùy thiết kế. Không nên giả định IP hoặc thiết bị mở link giống thiết bị khởi tạo.

Một số thiết kế ràng buộc yêu cầu đăng nhập với browser ban đầu bằng cookie giao dịch hoặc mã phụ hiển thị trên màn hình. Cách này có thể giảm nguy cơ token bị forward, nhưng làm mất trải nghiệm cross-device và không phải lúc nào cũng phù hợp. Nếu sử dụng, phải mô tả rõ cho người dùng và có phương án dự phòng an toàn.

**Không nên ràng buộc token bằng IP đơn thuần**: mạng di động, VPN và NAT khiến IP có thể thay đổi hợp lệ; IP không phải bằng chứng sở hữu account.

### Lựa chọn theo rủi ro

- Ứng dụng nội dung ít nhạy cảm: có thể chấp nhận cross-device với token ngắn hạn, một lần, kiểm soát email và session.
- Ứng dụng chứa dữ liệu cá nhân: cân nhắc xác thực bổ sung khi thiết bị/ngữ cảnh mới hoặc hành động nhạy cảm.
- Quản trị viên hoặc tác vụ tài chính: không dựa vào magic link đơn lẻ nếu policy đòi hỏi phương thức chống phishing; yêu cầu passkey, security key hoặc quy trình xác thực mạnh hơn.

## 11. Enumeration, rate limiting và chống lạm dụng

Khi người dùng nhập email, phản hồi khác nhau theo việc account có tồn tại có thể giúp attacker dò danh sách người dùng.

**Không nên trả:**

- “Email này chưa có tài khoản” khi không tồn tại.
- “Đã gửi link” khi tồn tại.
- “Tài khoản bị khóa” trước khi người yêu cầu xác thực.

Có thể dùng thông điệp chung như:

> Nếu địa chỉ này đủ điều kiện đăng nhập, hướng dẫn sẽ được gửi tới hộp thư.

Thông điệp chung cần đi cùng xử lý thời gian phản hồi hợp lý, rate limit và giám sát; nó không phải biện pháp duy nhất.

### Các chiều rate limit

| Phạm vi | Mục đích |
| --- | --- |
| Email đã chuẩn hóa | Ngăn spam một người nhận và enumeration qua gửi thư. |
| Account ID | Giới hạn tạo nhiều token cho cùng tài khoản. |
| IP/ASN hoặc nguồn mạng | Giảm tự động hóa từ một nguồn, có cân nhắc NAT/VPN. |
| Device/session/request | Hạn chế lặp yêu cầu từ một client. |
| Tenant | Ngăn một tenant tiêu thụ hết quota gửi email chung. |
| Toàn hệ thống | Bảo vệ nhà cung cấp email, chi phí và khả năng gửi thư. |

Cần giới hạn cả **yêu cầu gửi link**, **gửi lại email**, **hoàn tất token sai** và **đổi trạng thái account**. Đặt quota quá chặt có thể bị lợi dụng để khóa người dùng; nên có progressive throttling, cooldown và hỗ trợ hợp lệ.

## 12. Account binding, email change và liên kết danh tính

Magic link phải được gắn với một account đã được server xác định. Không nhận account ID từ client sau khi token được tạo rồi dùng nó làm chủ thể đăng nhập.

### Địa chỉ email thay đổi

Giả sử token được tạo cho `mai@old.example`, sau đó account đổi email sang `mai@new.example`. Token cũ không nên đăng nhập một cách vô điều kiện. Có thể lưu email version hoặc identifier snapshot để vô hiệu hóa token đang chờ khi địa chỉ thay đổi. Nếu token gắn với account ID và policy cho phép tiếp tục, phải quyết định rõ và audit; không để một email cũ vừa được chuyển cho người khác trở thành đường vào account.

### Email trùng ở nhiều tenant

Trong ứng dụng multi-tenant, cùng email có thể thuộc hai tenant hoặc hai account theo policy. Khi tạo magic link cần biết tenant context nếu flow yêu cầu tenant cụ thể. Token có thể gắn với tenant ID và phải kiểm tra membership còn hiệu lực khi hoàn tất. Không chọn tenant bằng một query parameter chưa xác minh rồi cấp phiên có quyền trong tenant đó.

### Tự động liên kết account là nguy hiểm

Một người đăng nhập bằng magic link tới email trùng với một account đã có thể chưa đủ để tự động gộp danh tính ngoài, đặc biệt khi account được tạo qua SSO hoặc có dữ liệu nhạy cảm. Dùng internal account ID ổn định; nếu thêm IdP hoặc credential mới, yêu cầu phiên account hiện tại và xác thực danh tính mới theo policy. Với OIDC, mapping nên dựa trên cặp issuer + subject đã xác minh, không chỉ email.

## 13. Tạo session sau khi magic link thành công

Magic link chỉ hoàn tất **một sự kiện xác thực**. Ứng dụng cần tạo session riêng với chính sách bảo vệ phù hợp.

Các bước nên có:

1. Kiểm tra account active, không bị khóa hoặc bị suspend.
2. Kiểm tra tenant và membership nếu luồng có tenant scope.
3. Xác định authentication context: phương thức magic link, thời điểm xác thực, purpose và mức bảo đảm theo policy.
4. Tiêu thụ token một cách nguyên tử.
5. Tạo session ID mới, ngẫu nhiên và khó đoán; không tái sử dụng session ID do client chọn trước đăng nhập.
6. Gắn session với account ID, tenant context (nếu có), thời điểm xác thực và trạng thái thu hồi.
7. Thiết lập cookie Secure, HttpOnly và SameSite phù hợp; bảo vệ CSRF cho thao tác thay đổi trạng thái.
8. Chuyển hướng tới route nội bộ được allowlist.
9. Ghi audit không chứa token hoặc cookie bí mật.

Nếu dùng access token, API phải xác minh chữ ký/introspection, issuer, audience, expiry, scope và trạng thái cần thiết. Token mới được phát hành không tự chứng minh người dùng đã thực hiện thêm yếu tố xác thực.

### Không giữ phiên cũ qua ranh giới xác thực

Sau khi magic link thành công, cần rotate session ID để chống session fixation. Nếu người dùng đã có phiên chưa xác thực hoặc pending MFA, server không nên nâng quyền một session ID có thể đã bị attacker biết. Có thể tạo session mới rồi thu hồi session tạm.

### Magic link có thể không đủ cho step-up

Nếu user đã đăng nhập rồi muốn đổi mật khẩu, gỡ MFA hoặc cấp quyền quản trị, việc gửi magic link tới email không nhất thiết đáp ứng yêu cầu step-up. Chính sách có thể yêu cầu passkey hoặc authenticator đã đăng ký; không dùng cùng email làm con đường mặc định để bỏ qua một yếu tố mạnh hơn.

## 14. Tích hợp MFA và passwordless

Magic link có thể là một trong nhiều phương thức đăng nhập của sản phẩm. Cần xác định rõ cách nó kết hợp với các phương thức khác.

| Thiết kế | Ý nghĩa | Điều cần chú ý |
| --- | --- | --- |
| Magic link là phương thức đăng nhập duy nhất | Người dùng đăng nhập bằng quyền truy cập email | Hộp thư là điểm lỗi trọng yếu; bảo vệ email/recovery và token. |
| Magic link thay mật khẩu, passkey là phương thức mạnh hơn | Người dùng có lựa chọn tiện lợi hoặc phishing-resistant | Policy phải ngăn fallback yếu cho tác vụ bắt buộc chống phishing. |
| Magic link + yếu tố thứ hai | Email link hoàn thành bước đầu, authenticator khác xác minh bước sau | Hai yếu tố phải thực sự độc lập theo mô hình và giao dịch. |
| Magic link chỉ xác minh email | Xác nhận địa chỉ, chưa cấp session | Không tự biến email verification thành login hoặc recovery. |
| Magic link phục hồi tài khoản | Cho phép bắt đầu recovery | Phải có assurance policy riêng; không tự coi recovery là login bình thường. |

Không gọi email magic link cộng email OTP gửi cùng một hộp thư là hai yếu tố độc lập. Cả hai dựa trên cùng quyền kiểm soát mailbox và có thể bị chiếm cùng lúc.

**Passwordless không đồng nghĩa phishing-resistant.** Passkey/WebAuthn cung cấp ràng buộc theo RP ID/origin; magic link là bearer URL và có thể bị chuyển tiếp. Chọn phương thức theo threat model, không theo tên gọi marketing.

## 15. Redirect, URL và các lỗi triển khai thường gặp

Magic link thường kết thúc bằng redirect. Tham số đích không được trở thành open redirect.

Ví dụ nguy hiểm:

~~~text
https://app.example/auth/magic?token=...&next=https://attacker.example
~~~

Nếu server chấp nhận `next` tùy ý, attacker có thể dùng domain thật để tạo link đáng tin rồi chuyển người dùng tới domain giả sau khi xác thực. Hãy dùng route key nội bộ hoặc allowlist origin/path; từ chối scheme lạ, protocol-relative URL, hostname không thuộc danh sách và các dạng encoding gây bypass.

Các lỗi khác:

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Token đoán được | Brute force đăng nhập | CSPRNG, entropy cao, rate limit. |
| Token lưu bản rõ | Database/log bị lộ kéo theo khả năng đăng nhập | Lưu digest/HMAC, redaction. |
| Token dùng nhiều lần | Replay | Atomic one-time consumption. |
| GET tự consume | Scanner/prefetch làm hỏng link | GET chỉ hiển thị, POST xác nhận. |
| Token không có purpose | Token xác minh email dùng để login/reset | Purpose binding server-side. |
| Token không gắn account | Dùng token với account do client chọn | Account binding ở record server. |
| Host header quyết định link | Host poisoning, email link trỏ domain attacker | Dùng origin cấu hình cố định. |
| Redirect tùy ý | Open redirect/phishing | Allowlist route nội bộ. |
| URL bị log hoặc gửi qua Referer | Rò bearer token | Redact, no-referrer, không third-party script. |
| Không giới hạn gửi link | Email bombing, chi phí và từ chối dịch vụ | Quota/rate limit/cooldown. |
| Phản hồi khác nhau theo account tồn tại | Enumeration | Response chung và giám sát. |
| Không rotate session sau login | Session fixation | Cấp session ID mới và thu hồi session tạm. |

## 16. Vòng đời token và trạng thái giao dịch

Một mô hình trạng thái đơn giản:

~~~text
CREATED
   |
   | email queued / sent
   v
PENDING
   |    |   expiry / revoke / email change / account lock
   |   v
   |  EXPIRED or REVOKED
   |
   | valid confirmation, atomic consume
   v
CONSUMED
   |
   | session creation succeeds
   v
COMPLETED
~~~

Nếu token đã consume nhưng việc tạo session thất bại do lỗi hạ tầng, người dùng có thể phải yêu cầu link mới. Điều này có thể gây bất tiện nhưng tránh việc token đã dùng lại. Nếu muốn retry an toàn, thiết kế idempotency phải gắn với đúng giao dịch và không cho phép một token tạo nhiều session ngoài ý muốn.

Không để trạng thái `PENDING` tồn tại vô hạn. Cần job dọn bản ghi hết hạn theo policy, nhưng vẫn giữ audit tối thiểu phù hợp. Không log raw token trong quá trình dọn hoặc điều tra.

### Hủy token khi có sự kiện bảo mật

Có thể thu hồi token pending khi:

- Người dùng yêu cầu link mới theo policy.
- Email liên hệ thay đổi.
- Account bị khóa, suspend hoặc đóng.
- Tenant bị suspend hoặc membership bị thu hồi nếu link gắn tenant.
- Phát hiện yêu cầu đăng nhập đáng ngờ hoặc user báo không phải mình.
- Chính sách bảo mật thay đổi làm token cũ không còn đủ điều kiện.

## 17. Ví dụ thiết kế endpoint và giả mã

Ví dụ API khái niệm:

~~~http
POST /auth/magic/request
Content-Type: application/json

{"email":"mai@example.org"}
~~~

Server trả phản hồi chung, ví dụ:

~~~http
202 Accepted
{"message":"Nếu địa chỉ đủ điều kiện, hướng dẫn đăng nhập sẽ được gửi."}
~~~

Khi người dùng mở link, trang xác nhận gửi:

~~~http
POST /auth/magic/complete
Content-Type: application/json

{"token":"<opaque-token>"}
~~~

Giả mã Java:

~~~java
MagicResult completeMagicLink(String rawToken, RequestContext request) {
    String digest = tokenHasher.sha256(rawToken);

    // Atomic consume: trả về record chỉ khi đúng purpose,
    // chưa hết hạn, chưa dùng và chưa bị revoke.
    MagicTokenRecord record =
        tokenRepository.consumeOnce(digest, "MAGIC_LINK_SIGN_IN", clock.now())
            .orElseThrow(GenericInvalidLinkException::new);

    Account account = accountRepository.requireActive(record.accountId());

    if (record.tenantId() != null) {
        tenantService.requireActive(record.tenantId());
        membershipService.requireActive(record.tenantId(), account.id());
    }

    accountPolicy.requireMagicLinkAllowed(account, request);

    AuthenticationContext auth = AuthenticationContext.builder()
        .accountId(account.id())
        .method("EMAIL_MAGIC_LINK")
        .authenticatedAt(clock.now())
        .purpose("MAGIC_LINK_SIGN_IN")
        .build();

    // Tạo session ID mới; không nâng session chưa xác thực.
    Session session = sessionService.createFreshSession(auth);

    return new MagicResult(session, redirectPolicy.resolve(record.redirectKey()));
}
~~~

Đây là giả mã minh họa, chưa phải code production. Thứ tự transaction giữa consume token, kiểm tra trạng thái account và tạo session cần được thiết kế cẩn thận: nếu token bị consume nhưng account đã bị khóa thì không được cấp session; nếu session creation thất bại thì phải có chính sách retry an toàn. Có thể dùng transaction/outbox/idempotency theo kiến trúc, nhưng không được làm mất tính một lần của token.

Một cách tiếp cận khác là khóa/đọc record trong transaction, xác minh account và membership, sau đó consume và tạo session trong một transaction hoặc workflow có trạng thái rõ ràng. Không để hai request song song cùng hoàn tất.

## 18. Quan sát và kiểm thử bảo mật

Magic link cần được kiểm thử cả luồng bình thường và các trường hợp scanner, replay, enumeration, redirect và lạm dụng.

| Ca thử | Kết quả mong đợi |
| --- | --- |
| Email hợp lệ, account active, token mới | Có thể hoàn tất sau xác nhận chủ động. |
| Email không tồn tại | Phản hồi công khai không tiết lộ account tồn tại. |
| Token sai hoặc bị sửa một ký tự | Từ chối chung; không tạo session. |
| Token hết hạn | Từ chối và yêu cầu link mới. |
| Token đã consume | Từ chối; không tạo session thứ hai. |
| Hai POST cùng token đồng thời | Chỉ một request tiêu thụ thành công. |
| GET từ email scanner | Không consume token, không tạo session, không đổi trạng thái. |
| Người dùng chủ động POST xác nhận | Consume token một lần và tạo session mới nếu policy cho phép. |
| Token purpose là EMAIL_VERIFICATION gửi tới endpoint login | Từ chối. |
| Account bị khóa sau khi link được gửi | Không tạo session. |
| Email đổi sau khi link được gửi | Token cũ bị vô hiệu theo policy/version. |
| Tenant bị suspend hoặc membership bị thu hồi | Không cấp tenant-scoped session. |
| Client sửa accountId hoặc tenantId trong POST | Không thay đổi account/tenant gắn với token. |
| next redirect trỏ domain ngoài | Từ chối hoặc dùng route mặc định. |
| Host header giả | Email link vẫn dùng origin cấu hình tin cậy. |
| URL chứa token xuất hiện trong access log | Kiểm thử logging xác nhận token được redacted. |
| Trang xác nhận tải analytics bên thứ ba | CSP/no-referrer và kiểm tra network đảm bảo không rò URL/token. |
| Gửi link liên tục | Rate limit/cooldown hoạt động, không gây email bombing. |
| Token bị dùng từ thiết bị khác | Xử lý theo policy cross-device; không suy IP là danh tính. |
| Session cũ được tạo trước login | Session ID được rotate hoặc session cũ bị thu hồi. |
| Người dùng yêu cầu link mới | Token cũ bị revoke hoặc xử lý theo quy tắc số token đang hoạt động. |

### Log và chỉ số vận hành

Có thể ghi: request ID, account ID nội bộ sau khi xác định được, tenant ID đã xác minh, thời điểm yêu cầu, trạng thái gửi, reason code chung, kết quả consume, loại client và kết quả session creation. Tránh ghi email đầy đủ nếu không cần; có thể dùng giá trị đã mask hoặc định danh phục vụ điều tra theo policy.

Không log raw token, URL có token, cookie, session ID bí mật, nội dung email đầy đủ hoặc recovery secret. Các chỉ số hữu ích gồm tỷ lệ yêu cầu/hoàn tất, token hết hạn, token bị replay, scanner GET, resend, bounce, rate-limit, session creation failure và báo cáo phishing. Theo dõi false positive và thời gian người dùng hoàn tất để cân bằng bảo mật với khả năng sử dụng.

## 19. Bài tập tình huống

Một nền tảng đào tạo cho phép đăng nhập bằng magic link. Người học nhập email trên laptop, email được gửi đến hộp thư công ty. Gateway bảo mật của công ty tự động mở mọi URL để kiểm tra trước khi giao email. Hệ thống hiện tại tiêu thụ token ngay khi nhận GET. Một số người dùng báo link đã hết hiệu lực trước khi họ nhấn vào.

Một ngày khác, kẻ tấn công gửi email giả với nút “Đăng nhập lại”, dụ người dùng copy link magic thật vào một cuộc trò chuyện. Kẻ tấn công sử dụng token trước người dùng. Một số link còn chứa tham số `next` do client cung cấp và redirect tới bất kỳ domain nào.

**Yêu cầu:**

1. Giải thích vì sao email scanner làm token bị consume trước người dùng.
2. Đề xuất flow GET/POST để tránh prefetch phổ biến.
3. Chỉ ra vì sao one-time token không ngăn được attacker sử dụng trước người dùng.
4. Thiết kế token record có account, purpose, expiry, consumed/revoked và tenant binding nếu cần.
5. Đề xuất cách xử lý redirect và logging để không làm lộ token.
6. Quyết định khi nào magic link không đủ và cần passkey hoặc step-up.

**Hướng phân tích:** GET chỉ hiển thị trang xác nhận, POST có chủ đích mới consume token. Token phải ngẫu nhiên, ngắn hạn, digest trong database, gắn account/purpose và consume nguyên tử. One-time chỉ ngăn dùng lại sau lần thành công đầu tiên; nó không ngăn kẻ đánh cắp dùng token trước chủ tài khoản. Không chấp nhận redirect tùy ý; dùng route key/allowlist. Redact URL ở proxy/log, đặt no-referrer và loại script bên thứ ba. Với tài khoản nhạy cảm hoặc yêu cầu chống phishing, ưu tiên passkey/WebAuthn và dùng magic link chỉ trong phạm vi policy cho phép.

## 20. Checklist review

- [ ] Magic link được mô tả đúng là bằng chứng kiểm soát kênh email tại thời điểm sử dụng, không phải danh tính pháp lý.
- [ ] Token được tạo bằng CSPRNG, có entropy cao, thời hạn và purpose rõ ràng.
- [ ] Database chỉ lưu digest/HMAC phù hợp, không lưu token thô.
- [ ] Token gắn với account ID và tenant/purpose nếu cần; không tin account ID do client gửi.
- [ ] Token chỉ dùng một lần, consume nguyên tử và có kiểm soát replay.
- [ ] GET không tự consume hoặc tạo session; có bước xác nhận chủ động.
- [ ] Trang chứa token dùng HTTPS, no-referrer, CSP và không gửi URL đến analytics bên thứ ba.
- [ ] Reverse proxy, CDN, application log và tracing redacts token/URL.
- [ ] Origin email dùng cấu hình cố định; không dựa Host header không tin cậy.
- [ ] Redirect được giới hạn vào route/origin đã cho phép.
- [ ] Phản hồi request link không làm lộ account enumeration.
- [ ] Rate limit và quota bảo vệ email, account, IP, tenant và toàn hệ thống.
- [ ] Account, email version, tenant và membership được kiểm tra lại trước khi cấp phiên.
- [ ] Session ID được tạo mới sau xác thực; cookie/token được bảo vệ và có khả năng thu hồi.
- [ ] Recovery và step-up không dùng magic link yếu để bỏ qua yêu cầu bảo đảm mạnh hơn.
- [ ] Có kiểm thử scanner GET, replay đồng thời, redirect, log redaction và token purpose.

## 21. Ghi nhớ

**Magic link là một cách passwordless tiện lợi dựa trên token bearer gửi qua một kênh như email.** Thiết kế an toàn cần token ngẫu nhiên, ngắn hạn, gắn account và purpose, lưu digest, xác nhận có chủ đích, consume nguyên tử, chống enumeration, bảo vệ URL và tạo session mới. Hệ thống phải xem hộp thư là một ranh giới tin cậy có thể bị chiếm, và không nhầm magic link với MFA hay xác thực chống phishing.

Khi review một luồng, hãy hỏi: **Token chứng minh quyền kiểm soát điều gì? Nó được gắn với account và mục đích nào? Scanner có thể dùng nó trước người dùng không? Kẻ khác có thể đánh cắp hoặc phát lại token không? URL có rò qua log/redirect không? Phiên được cấp có đủ bảo đảm cho hành động tiếp theo không?**
