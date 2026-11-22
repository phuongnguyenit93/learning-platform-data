# Lỗi xác thực hoặc địa chỉ không nên thử lại mù

Trong Spring Framework Mail, cơ chế retry giúp hệ thống phục hồi khi SMTP server tạm thời không sẵn sàng, kết nối mạng gián đoạn hoặc bị giới hạn tốc độ trong một khoảng ngắn. Tuy nhiên, **không phải lỗi gửi email nào cũng nên được thử lại**.

Nếu tài khoản SMTP sai mật khẩu, OAuth token đã bị thu hồi hoặc tính năng SMTP AUTH bị tắt, việc gửi lại cùng yêu cầu mỗi vài giây thường không giúp gì. Nó còn có thể kích hoạt khóa tài khoản, tăng cảnh báo bảo mật hoặc khiến cả hàng đợi email bị nghẽn. Tương tự, nếu địa chỉ người nhận không tồn tại, gửi lại hàng chục lần chỉ tạo lưu lượng vô ích và có thể làm xấu uy tín gửi thư.

Một chính sách an toàn cần phân biệt:

- **Lỗi có thể phục hồi tạm thời:** server bận, giới hạn tốc độ, lỗi mạng nhất thời.
- **Lỗi cần sửa cấu hình hoặc thông tin xác thực:** credentials sai, quyền SMTP bị tắt, cơ chế xác thực không tương thích.
- **Lỗi địa chỉ hoặc người nhận:** cú pháp sai, mailbox không tồn tại, người nhận không được chấp nhận.
- **Lỗi chính sách:** domain, nội dung, sender hoặc tổ chức không được server chấp nhận.
- **Kết quả không xác định:** kết nối đứt sau khi SMTP có thể đã nhận message; retry có nguy cơ gửi trùng.

Nguyên tắc chính: **retry phải dựa trên loại lỗi, giai đoạn xảy ra, phản hồi SMTP và trạng thái thực tế của tác vụ; không dựa đơn thuần vào việc có exception**.

## 1. Tại sao retry mù gây hại?

Giả sử một worker lấy các email đang chờ từ outbox và gọi JavaMailSender:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (Exception ex) {
        Thread.sleep(1000);
    }
}
~~~

Đây là mô hình cần tránh vì:

1. Không biết exception có phải tạm thời hay không.
2. Không có số lần thử tối đa hoặc backoff thích hợp.
3. Lỗi xác thực có thể khiến worker thử đi thử lại bằng credentials không hợp lệ.
4. Địa chỉ không tồn tại vẫn bị thử lại vô hạn.
5. Nếu message đã được SMTP chấp nhận nhưng phản hồi bị mất, lần thử kế tiếp có thể gửi trùng.
6. Worker bị chiếm giữ bởi một tác vụ lỗi thay vì xử lý các tác vụ hợp lệ khác.
7. Hệ thống không lưu trạng thái để người vận hành biết cần sửa cấu hình hay dữ liệu.

Ví dụ chuỗi sự cố:

~~~text
SMTP password bị thay đổi
        |
        v
JavaMailSender.send()
        |
        v
Authentication failed
        |
        v
Retry mỗi giây
        |
        +-- Tăng số lần đăng nhập thất bại
        +-- Có nguy cơ bị khóa tài khoản
        +-- Tăng log và cảnh báo
        +-- Không có email nào được gửi
~~~

Lỗi credentials cần một hành động khác: **tạm dừng nhóm tác vụ sử dụng cấu hình lỗi, cảnh báo và yêu cầu sửa cấu hình**, sau đó mới khôi phục gửi.

## 2. Cách đọc phản hồi SMTP

SMTP dùng mã phản hồi ba chữ số, thường đi kèm thông điệp mô tả. Một số hệ thống còn trả **enhanced status code** theo dạng ba thành phần như 5.1.1 hoặc 4.7.0.

Phân loại cơ bản:

| Nhóm | Ý nghĩa khái quát | Hướng xử lý ban đầu |
| --- | --- | --- |
| **2xx** | Lệnh đã được chấp nhận | Tiếp tục theo giao thức; không có lỗi cần retry ở bước đó |
| **3xx** | Server yêu cầu dữ liệu hoặc bước tiếp theo | Không phải lỗi cuối cùng của message |
| **4xx** | Negative completion tạm thời | Có thể retry có giới hạn, sau khi phân tích nguyên nhân |
| **5xx** | Negative completion không được chấp nhận trong điều kiện hiện tại | Thường cần sửa dữ liệu/cấu hình/chính sách trước khi thử lại |

**4xx không đồng nghĩa chắc chắn retry ngay**, và **5xx không đồng nghĩa mọi địa chỉ đều phải bị xóa vĩnh viễn**. Phải xem phản hồi thuộc giai đoạn nào và server thực sự đang nói về điều gì.

### 2.1. Enhanced status code bổ sung ngữ cảnh

Ví dụ:

~~~text
550 5.1.1 User unknown
~~~

Trong đó:

- **550** là SMTP reply code.
- **5.1.1** là enhanced status code, thường mô tả địa chỉ đích không tồn tại.
- **User unknown** là diagnostic text của server.

Một phản hồi khác:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

Đây là tín hiệu về xác thực, không phải bằng chứng rằng email của người nhận sai.

Mã và thông điệp thực tế phụ thuộc nhà cung cấp. Cần tham khảo tài liệu của SMTP provider để hiểu chính xác các trường hợp đặc thù; không chỉ tìm một từ khóa trong diagnostic text rồi quyết định xóa địa chỉ.

### 2.2. Các mã thường gặp và cách hiểu thận trọng

| Phản hồi minh họa | Giai đoạn thường gặp | Ý nghĩa khả dĩ | Xử lý thường phù hợp |
| --- | --- | --- | --- |
| **535 5.7.8** | AUTH | Thông tin xác thực không hợp lệ | Dừng retry tự động, sửa credentials |
| **534 5.7.x** | AUTH | Cơ chế/điều kiện xác thực không được chấp nhận | Kiểm tra chính sách xác thực, MFA/OAuth |
| **530 5.7.x** | MAIL FROM hoặc lệnh khác | Cần xác thực hoặc TLS trước khi tiếp tục | Kiểm tra cấu hình/session |
| **454 4.7.0** | AUTH | Xác thực tạm thời không khả dụng | Retry có giới hạn, backoff và cảnh báo nếu kéo dài |
| **421 4.x.x** | Kết nối hoặc lệnh SMTP | Service tạm thời không sẵn sàng | Retry có backoff nếu chưa chấp nhận message |
| **450 4.2.x** | RCPT TO | Mailbox tạm thời không khả dụng | Retry theo chính sách |
| **451 4.3.x** | RCPT TO/DATA | Lỗi xử lý tạm thời | Retry có giới hạn |
| **452 4.2.2** | RCPT TO | Mailbox đầy hoặc tài nguyên tạm thời thiếu | Chờ, giới hạn retry |
| **501 5.1.3** | MAIL FROM/RCPT TO | Cú pháp địa chỉ hoặc tham số sai | Sửa dữ liệu, không retry nguyên trạng |
| **550 5.1.1** | RCPT TO | Mailbox không tồn tại | Đánh dấu recipient không hợp lệ khi tín hiệu đáng tin |
| **553 5.1.3** | RCPT TO | Địa chỉ mailbox sai cú pháp | Sửa địa chỉ |
| **550 5.7.1** | RCPT TO hoặc DATA | Không được phép, policy từ chối | Điều tra sender, quyền và chính sách |
| **552 5.2.2** | RCPT TO/DATA | Hộp thư đầy theo phản hồi server | Phân loại theo provider; không tự coi là user unknown |
| **554 5.7.x** | DATA hoặc cuối giao dịch | Bị từ chối theo chính sách/nội dung | Dừng retry nguyên trạng, điều tra chính sách |

Bảng là các ví dụ thường gặp, **không phải ánh xạ tuyệt đối**. Cùng mã SMTP ba chữ số có thể mang ý nghĩa khác nhau theo enhanced code, phase và diagnostic text. Đặc biệt, **550 một mình không chứng minh địa chỉ người nhận không tồn tại**.

## 3. Phân biệt các giai đoạn SMTP

Một exception từ JavaMailSender có thể phát sinh ở nhiều giai đoạn:

~~~text
CONNECT
   |
   v
TLS / STARTTLS
   |
   v
AUTH
   |
   v
MAIL FROM
   |
   v
RCPT TO
   |
   v
DATA
   |
   v
Server accepts or rejects message
~~~

Thông tin về **giai đoạn lỗi** giúp quyết định retry.

### 3.1. CONNECT và TLS

Timeout khi tạo connection có thể là lỗi mạng tạm thời. Nhưng host sai, port sai, certificate không hợp lệ hoặc cấu hình STARTTLS không tương thích thường cần sửa cấu hình.

Nếu chứng chỉ TLS không được tin cậy, retry liên tục thường không làm thay đổi kết quả. Không tắt kiểm tra chứng chỉ để “sửa nhanh” cho một lỗi xác thực hoặc TLS.

### 3.2. AUTH

Lỗi ở AUTH liên quan đến account, phương thức xác thực, token, quyền hoặc dịch vụ xác thực. Phải tách lỗi tạm thời khỏi lỗi cấu hình.

### 3.3. MAIL FROM

Server có thể từ chối envelope sender vì account không có quyền gửi bằng địa chỉ đó, domain chưa được cho phép hoặc policy gửi thư không đạt.

Đây không phải lỗi của email người nhận. Không đưa tất cả recipient vào danh sách địa chỉ không hợp lệ khi lỗi nằm ở MAIL FROM.

### 3.4. RCPT TO

Giai đoạn này thường cung cấp tín hiệu cụ thể về địa chỉ người nhận: mailbox không tồn tại, địa chỉ không hợp lệ, người nhận bị từ chối hoặc tạm thời không khả dụng.

Tuy nhiên, một từ chối ở RCPT TO cũng có thể do policy, rate limit hoặc reputation của sender. Phải xem cả mã và diagnostic.

### 3.5. DATA và phản hồi cuối

Nếu server từ chối nội dung ở DATA, lỗi có thể liên quan policy, kích thước hoặc loại file đính kèm. Nếu kết nối đứt sau khi gửi dữ liệu nhưng trước khi ứng dụng nhận phản hồi cuối, kết quả gửi **có thể không xác định**.

Đây là một trong những tình huống quan trọng nhất đối với idempotency: việc retry có thể tạo một bản email trùng nếu server đã chấp nhận message.

## 4. Lỗi xác thực: không retry bằng cùng credentials mãi mãi

Một số nguyên nhân phổ biến:

- Mật khẩu SMTP đã thay đổi.
- App password bị thu hồi.
- SMTP AUTH bị tắt ở account hoặc tenant.
- Account bắt buộc dùng OAuth2 nhưng ứng dụng vẫn dùng mật khẩu.
- Access token hết hạn và cơ chế refresh bị lỗi.
- Server yêu cầu TLS trước khi AUTH.
- Account bị khóa hoặc bị chính sách bảo mật chặn.
- Sai SMTP host, port hoặc cơ chế TLS.
- Tài khoản không được phép gửi bằng envelope sender hoặc From đang chọn.

Các nguyên nhân này có thể cần quản trị viên hoặc cơ chế cấp credential sửa lại. Không nên coi chúng như lỗi mạng tạm thời.

### 4.1. Phản hồi 535

Ví dụ:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

Nếu credentials cấu hình không đổi, gửi lại cùng lệnh AUTH sau một giây thường vẫn thất bại.

Hướng xử lý:

1. Ghi nhận tài khoản/cấu hình gửi bị ảnh hưởng bằng định danh không nhạy cảm.
2. Chuyển các mail job liên quan sang trạng thái tạm dừng do cấu hình.
3. Không tiếp tục thử cùng credentials theo vòng lặp.
4. Phát cảnh báo cho người vận hành hoặc cơ chế quản lý secrets.
5. Sau khi xác minh cấu hình mới, thực hiện một lần kiểm tra có kiểm soát.
6. Tiếp tục xử lý queue theo tốc độ đã giới hạn.

Không log password, OAuth token hoặc nội dung Authorization.

### 4.2. SMTP AUTH bị tắt

Một provider có thể từ chối dù username và password đúng vì tài khoản, tenant hoặc tổ chức không cho phép SMTP AUTH.

Khi đó cần thay đổi quyền hoặc lựa chọn cơ chế gửi khác theo chính sách provider. Retry không sửa được một quyền bị vô hiệu hóa.

### 4.3. OAuth token hết hạn

Nếu sử dụng OAuth2, token hết hạn là một tình huống có thể phục hồi bằng quy trình refresh hợp lệ.

Một chính sách an toàn có thể là:

- Nhận diện token hết hạn theo phản hồi provider đáng tin cậy.
- Làm mới token bằng refresh flow đã được triển khai.
- Thử lại **có giới hạn**, thường một lần với token mới cho lần xử lý đó.
- Nếu refresh thất bại, token bị thu hồi hoặc account mất quyền, chuyển sang trạng thái cần can thiệp.
- Dùng đồng bộ hóa hoặc single-flight refresh để tránh hàng trăm worker cùng refresh token.

**Không mặc định mọi phản hồi 535 đều là token hết hạn.** Cần xem cơ chế xác thực và tín hiệu của provider.

### 4.4. Lỗi AUTH tạm thời vẫn có thể retry

Ví dụ một số provider trả:

~~~text
454 4.7.0 Temporary authentication failure
~~~

Nếu đây thực sự là lỗi tạm thời của dịch vụ xác thực, có thể thử lại sau một khoảng chờ và giới hạn số lần.

Không retry dồn dập: ngay cả lỗi 4xx lặp đi lặp lại cũng có thể tạo tải hoặc kích hoạt chính sách chống lạm dụng.

### 4.5. Tránh khóa tài khoản

Một hệ thống có 20 worker và mỗi worker retry 5 lần có thể tạo 100 lần AUTH thất bại trong thời gian ngắn.

Với lỗi dùng chung credentials, nên có cơ chế **pause/circuit breaker theo SMTP account hoặc tenant** thay vì để từng message tự thử không giới hạn. Lỗi một account không nên làm dừng mọi tenant hoặc tài khoản gửi khác nếu chúng độc lập.

## 5. Địa chỉ người nhận sai: sửa dữ liệu thay vì retry

Không phải mọi địa chỉ email trông giống nhau đều thực sự tồn tại.

Một số trường hợp:

- Thiếu dấu @ hoặc phần domain.
- Địa chỉ chứa ký tự không hợp lệ theo chính sách hệ thống.
- Domain không tồn tại hoặc không nhận email.
- Mailbox đã bị xóa.
- Người nhận nhập sai tên mailbox.
- Recipient bị server từ chối theo chính sách.
- Hộp thư đang tạm thời không nhận thư.

Các tình huống này cần cách xử lý khác nhau.

### 5.1. Lỗi cú pháp địa chỉ

Ví dụ:

~~~text
501 5.1.3 Bad recipient address syntax
~~~

Nếu địa chỉ được nhập sai, retry nguyên trạng không giúp ích. Ứng dụng nên đánh dấu cần sửa dữ liệu, không thử lại cho đến khi địa chỉ được cập nhật.

Kiểm tra cú pháp trước khi tạo mail:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public void validateRecipient(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException(
                "Địa chỉ email không được để trống"
        );
    }

    try {
        InternetAddress address = new InternetAddress(email, true);
        address.validate();

        if (address.isGroup()) {
            throw new IllegalArgumentException(
                    "Cần một mailbox riêng, không phải nhóm địa chỉ"
            );
        }
    } catch (AddressException ex) {
        throw new IllegalArgumentException(
                "Địa chỉ email không hợp lệ",
                ex
        );
    }
}
~~~

Đây chỉ là một lớp kiểm tra cú pháp theo API Jakarta Mail. Nó **không bảo đảm mailbox tồn tại**, không xác minh chủ sở hữu địa chỉ và không thay thế kiểm tra quyền gửi hoặc quy tắc sản phẩm.

Cần cân nhắc địa chỉ quốc tế hóa, chính sách hỗ trợ SMTPUTF8 và các trường hợp domain đặc biệt nếu hệ thống có yêu cầu tương ứng.

### 5.2. Mailbox không tồn tại

Ví dụ:

~~~text
550 5.1.1 User unknown
~~~

Nếu provider xác nhận mailbox không tồn tại ở RCPT TO, ứng dụng có thể đánh dấu recipient cần sửa hoặc đưa vào danh sách suppression phù hợp với chính sách.

Không nên tiếp tục retry cùng địa chỉ chỉ vì outbox job chưa đạt giới hạn attempts.

Tuy nhiên, không tự động suy ra “unknown user” từ mọi mã 550. Phải xem enhanced status code, phản hồi chi tiết, phase và hành vi provider.

### 5.3. Mailbox đầy không giống mailbox không tồn tại

Ví dụ:

~~~text
452 4.2.2 Mailbox full
~~~

Một mailbox đầy có thể trở lại trạng thái nhận thư sau khi người dùng giải phóng dung lượng. Tùy provider, có thể cân nhắc retry chậm, có giới hạn.

Một phản hồi lớp 5.2.2 có thể mang ý nghĩa từ chối không thể xử lý ở thời điểm đó. Không tự gắn nhãn địa chỉ là “không tồn tại” chỉ vì mailbox đầy.

### 5.4. Domain không nhận thư

Nếu lỗi là domain không tìm thấy hoặc không có tuyến chuyển phát phù hợp, có thể là dữ liệu sai hoặc lỗi DNS tạm thời. Cần phân biệt DNS NXDOMAIN ổn định với DNS timeout.

Không xóa recipient do một timeout DNS ngắn. Ngược lại, không retry vô hạn một domain rõ ràng không tồn tại.

### 5.5. Không dùng SMTP VRFY như bằng chứng chắc chắn

Nhiều hệ thống vô hiệu hóa hoặc hạn chế lệnh VRFY để chống thu thập địa chỉ. Một số server cố tình không xác nhận người dùng tại SMTP transaction.

Không thiết kế chức năng “kiểm tra địa chỉ tồn tại” bằng cách gửi lệnh thăm dò hàng loạt. Cách này không đáng tin cậy và có thể bị coi là hoạt động lạm dụng.

Cách xác minh chủ sở hữu địa chỉ phù hợp hơn trong nhiều sản phẩm là gửi email xác minh có thời hạn và yêu cầu người dùng hoàn tất quy trình xác nhận.

## 6. Lỗi policy không phải lỗi địa chỉ

Một số phản hồi SMTP từ chối gửi thư vì:

- Sender không được cấp quyền.
- Domain gửi chưa được xác thực theo chính sách provider.
- SPF, DKIM hoặc DMARC không được cấu hình phù hợp.
- Danh tiếng IP/domain thấp.
- Nội dung hoặc attachment vi phạm quy tắc.
- Giới hạn gửi của account hoặc tenant.
- Recipient domain áp dụng policy đặc biệt.

Ví dụ:

~~~text
550 5.7.1 Message rejected by policy
~~~

Nếu chỉ thấy 550 rồi đưa recipient vào suppression như “mailbox không tồn tại”, hệ thống có thể làm mất những địa chỉ hợp lệ.

Cách xử lý đúng là phân loại theo **nguồn gốc lỗi**:

- Lỗi sender/domain: kiểm tra cấu hình và danh tiếng gửi.
- Lỗi nội dung: điều tra template, link và attachment.
- Lỗi quyền gửi: kiểm tra account và chính sách provider.
- Lỗi recipient rõ ràng: xử lý dữ liệu recipient.
- Lỗi quota/rate limit: chờ theo chính sách thay vì sửa địa chỉ.

Không có một bảng mã SMTP duy nhất đủ để quyết định mọi trường hợp mà không cần ngữ cảnh provider.

## 7. Lỗi tạm thời: retry có điều kiện và có giới hạn

Một số lỗi phù hợp với retry:

- SMTP server tạm thời không sẵn sàng.
- Connection timeout trước khi message được chấp nhận.
- Rate limiting hoặc throttling được provider báo rõ.
- Lỗi 4xx ở RCPT TO hoặc DATA thể hiện trạng thái tạm thời.
- Dịch vụ xác thực tạm thời gián đoạn, nếu có tín hiệu đáng tin cậy.

Nhưng retry cần:

1. Giới hạn số lần thử.
2. Giãn cách theo exponential backoff.
3. Thêm jitter để tránh đồng loạt gửi lại.
4. Tôn trọng thời gian chờ được provider khuyến nghị nếu có.
5. Giới hạn concurrency theo account/provider.
6. Phân biệt tác vụ lỗi chung do cấu hình với lỗi của từng message.
7. Ghi nhận nguyên nhân và thời điểm thử lại.

Ví dụ một chuỗi backoff minh họa:

~~~text
Attempt 1 -> lỗi tạm thời
  Wait ~30 giây + jitter
Attempt 2 -> lỗi tạm thời
  Wait ~2 phút + jitter
Attempt 3 -> lỗi tạm thời
  Wait ~10 phút + jitter
Attempt 4 -> lỗi tạm thời
  Wait ~30 phút + jitter
Quá ngưỡng -> MANUAL_REVIEW hoặc FAILED
~~~

Các khoảng trên chỉ là ví dụ kiến trúc, không phải mặc định của Spring Mail. Chính sách thực tế phụ thuộc SLA, nhà cung cấp SMTP, loại thông báo và khả năng phục hồi.

### 7.1. Không retry ngay khi provider rate limit

Nếu server phản hồi dạng:

~~~text
421 4.7.0 Too many requests
~~~

thử lại tức thì với nhiều worker có thể làm tình hình tệ hơn. Nên giảm tốc, dùng backoff và giới hạn tổng số kết nối/lệnh gửi.

### 7.2. Circuit breaker cho lỗi toàn cục

Nếu toàn bộ email gửi qua một SMTP account đều nhận cùng lỗi AUTH cố định, thay vì retry từng message, có thể mở circuit breaker cho account đó.

~~~text
SMTP account A
      |
      v
Repeated permanent AUTH errors
      |
      v
PAUSED_CONFIG
      |
      +-- Alert owner
      +-- Update/validate credentials
      +-- Controlled recovery
      |
      v
Resume queued sends
~~~

Các account độc lập khác vẫn có thể hoạt động bình thường.

## 8. Spring Mail biểu diễn lỗi như thế nào?

Spring cung cấp **JavaMailSender** để tạo và gửi MimeMessage. Các lỗi runtime khi gửi thường được chuyển thành các exception thuộc hệ phân cấp **MailException**.

Một số loại thường gặp:

| Exception | Ý nghĩa thường gặp | Lưu ý |
| --- | --- | --- |
| **MailAuthenticationException** | Quá trình xác thực thất bại | Cần xem lỗi cố định hay tạm thời |
| **MailSendException** | Lỗi khi gửi một hoặc nhiều message | Có thể chứa lỗi chi tiết của message |
| **MailParseException** | Không phân tích được thông điệp mail | Thường cần sửa dữ liệu hoặc cách dựng message |
| **MailPreparationException** | Lỗi chuẩn bị message | Không retry SMTP nếu đầu vào/template còn sai |
| **MailException** | Lớp cha cho lỗi mail ở Spring | Không đủ để quyết định retry |

Ví dụ:

~~~java
try {
    mailSender.send(mimeMessage);
} catch (MailAuthenticationException ex) {
    // Thường cần kiểm tra cấu hình AUTH trước khi retry.
} catch (MailSendException ex) {
    // Đọc nguyên nhân, message failures và SMTP response.
} catch (MailException ex) {
    // Phân loại theo nguyên nhân cụ thể; không retry vô điều kiện.
}
~~~

**Tên exception ở lớp Spring chưa đủ để kết luận chính xác.** Một MailSendException có thể chứa lỗi SMTP với các mã khác nhau, thậm chí thông tin kết quả của nhiều recipient.

### 8.1. Jakarta Mail và exception lồng nhau

Khi làm việc với Jakarta Mail, các loại exception có ích gồm:

- **jakarta.mail.MessagingException**
- **jakarta.mail.AuthenticationFailedException**
- **jakarta.mail.SendFailedException**
- **jakarta.mail.internet.AddressException**

Một MessagingException có thể chứa exception liên kết qua **getNextException()**, không chỉ qua Java cause chain. Spring MailSendException cũng có thể cung cấp các exception chi tiết qua **getMessageExceptions()** hoặc mapping message lỗi.

Một hệ thống phân loại lỗi nên quan sát **chuỗi exception thực tế và phản hồi SMTP**, thay vì kiểm tra mỗi tên exception ngoài cùng.

### 8.2. Exception theo SMTP provider

Một số provider Jakarta Mail có exception chuyên biệt cho địa chỉ hoặc lệnh SMTP, chứa SMTP reply code và thông tin recipient. Package/class cụ thể có thể phụ thuộc implementation và phiên bản mail provider được sử dụng.

Không nên hard-code một tên package SMTP provider vào toàn bộ domain logic. Hãy viết một adapter ở tầng infrastructure để chuyển exception của provider thành các tín hiệu chung như:

~~~text
phase
smtpReplyCode
enhancedStatusCode
recipient
providerDiagnostic
outcomeKnown
~~~

Sau đó retry policy chỉ phụ thuộc các tín hiệu đã chuẩn hóa.

### 8.3. Có thể gửi thành công một phần

Một lần gửi tới nhiều recipient có thể có kết quả khác nhau cho từng địa chỉ. Jakarta Mail SendFailedException có thể cung cấp những nhóm địa chỉ như:

- Địa chỉ không hợp lệ.
- Địa chỉ hợp lệ đã được gửi theo kết quả transport.
- Địa chỉ hợp lệ nhưng chưa được gửi.

Hãy xem các nhóm đó cùng provider policy. Không retry toàn bộ danh sách chỉ vì một địa chỉ bị từ chối; điều đó có thể làm người đã nhận thư nhận thêm bản sao.

## 9. Thiết kế bộ phân loại retry rõ ràng

Một tầng infrastructure có thể chuyển lỗi thành thông tin có cấu trúc, sau đó một policy xác định hành động.

Ví dụ model Java:

~~~java
public enum SmtpStage {
    CONNECT,
    TLS,
    AUTH,
    MAIL_FROM,
    RCPT_TO,
    DATA,
    AFTER_DATA,
    UNKNOWN
}

public record FailureSignals(
        SmtpStage stage,
        Integer replyCode,
        String enhancedCode,
        boolean responseLostAfterData,
        boolean malformedRecipient
) {}

public enum RetryDecision {
    RETRY_WITH_BACKOFF,
    STOP_INVALID_RECIPIENT,
    STOP_FIX_AUTH,
    STOP_FIX_POLICY,
    REVIEW_UNKNOWN_OUTCOME
}
~~~

Các trường được lấy từ exception/SMTP diagnostics có thật. **Không đoán replyCode hoặc stage nếu provider không cung cấp.** Có thể để null/UNKNOWN và phân loại bảo thủ.

### 9.1. Ví dụ policy minh họa

~~~java
public final class MailRetryPolicy {

    public RetryDecision decide(FailureSignals f) {
        if (f.responseLostAfterData()) {
            return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
        }

        if (f.malformedRecipient()) {
            return RetryDecision.STOP_INVALID_RECIPIENT;
        }

        Integer code = f.replyCode();
        String enhanced = f.enhancedCode();

        if (f.stage() == SmtpStage.AUTH) {
            if (code != null && code >= 500 && code <= 599) {
                return RetryDecision.STOP_FIX_AUTH;
            }
            if (code != null && code >= 400 && code <= 499) {
                return RetryDecision.RETRY_WITH_BACKOFF;
            }
            return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
        }

        if (f.stage() == SmtpStage.RCPT_TO &&
                ("5.1.1".equals(enhanced) ||
                 "5.1.3".equals(enhanced))) {
            return RetryDecision.STOP_INVALID_RECIPIENT;
        }

        if (code != null && code >= 400 && code <= 499) {
            return RetryDecision.RETRY_WITH_BACKOFF;
        }

        if (code != null && code >= 500 && code <= 599) {
            return RetryDecision.STOP_FIX_POLICY;
        }

        return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
    }
}
~~~

Đây là **policy tối giản để minh họa cấu trúc**, không phải bộ phân loại hoàn chỉnh cho mọi SMTP provider. Trong sản phẩm thật cần xét thêm TLS, chính sách, quota, địa chỉ sender, enhanced status code cụ thể, giai đoạn DATA và các tín hiệu lỗi mạng. **RETRY_WITH_BACKOFF** cũng phải chịu giới hạn attempts/TTL và điều kiện không gửi trùng.

### 9.2. Tách phân loại và hành động

Không nên để bộ phân loại tự gọi SMTP lần nữa. Nó chỉ nên trả về quyết định. Một worker khác sẽ:

- Ghi nhận trạng thái.
- Chọn thời điểm retry.
- Cập nhật attempts.
- Phát cảnh báo nếu cần.
- Chờ thông tin cấu hình được sửa.
- Thực hiện gửi khi tác vụ đủ điều kiện.

Tách trách nhiệm giúp retry policy có thể kiểm thử độc lập mà không cần kết nối SMTP thật.

## 10. Phân loại lỗi xác thực trong Java

Ở mức Spring Mail, có thể chặn riêng lỗi AUTH:

~~~java
public void deliver(MimeMessage message) {
    try {
        mailSender.send(message);
    } catch (MailAuthenticationException ex) {
        throw new SmtpAccountNeedsAttentionException(
                "SMTP authentication failed",
                ex
        );
    }
}
~~~

**SmtpAccountNeedsAttentionException** là exception ứng dụng tự định nghĩa để thông báo cho tầng điều phối rằng account gửi cần được xem xét. Nó không phải class có sẵn của Spring.

Ví dụ:

~~~java
public class SmtpAccountNeedsAttentionException
        extends RuntimeException {

    public SmtpAccountNeedsAttentionException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
~~~

Cách này có ích để phản ánh một nhóm lỗi nghiêm trọng, nhưng **không nên đánh đồng mọi MailAuthenticationException là credentials sai vĩnh viễn**. Nếu provider cho biết AUTH tạm thời không sẵn sàng, policy có thể cho phép retry có giới hạn.

Điểm quan trọng là **không bắt MailAuthenticationException rồi tự retry vô hạn**:

~~~java
catch (MailAuthenticationException ex) {
    // Sai: lập tức send lại liên tục với cùng credentials.
}
~~~

Tầng gửi mail nên báo đúng lỗi; tầng điều phối quyết định dừng, sửa cấu hình hoặc retry.

## 11. Phân biệt lỗi recipient từ exception

Nếu provider trả lỗi ở RCPT TO, thông tin cần xác định gồm:

- Recipient nào bị từ chối?
- SMTP reply code là gì?
- Enhanced status code có đáng tin cậy không?
- Lỗi do recipient không tồn tại hay do policy?
- Có recipient khác đã được chấp nhận không?
- Message đã được chấp nhận sau DATA hay chưa?

Một số implementation cung cấp exception dành riêng cho địa chỉ SMTP. Jakarta Mail SendFailedException cũng có thể cung cấp danh sách địa chỉ hợp lệ, không hợp lệ và chưa gửi.

Ví dụ cách quan sát loại exception:

~~~java
catch (MailSendException ex) {
    for (Exception cause : ex.getMessageExceptions()) {
        if (cause instanceof jakarta.mail.SendFailedException sfe) {
            Address[] invalid = sfe.getInvalidAddresses();
            Address[] validSent = sfe.getValidSentAddresses();
            Address[] validUnsent = sfe.getValidUnsentAddresses();

            // Chuyển thành kết quả có cấu trúc theo recipient.
            // Không gửi lại toàn bộ danh sách một cách mù quáng.
        }
    }
}
~~~

Đây là đoạn minh họa trích xuất thông tin ở tầng infrastructure. Các mảng có thể null, exception có thể lồng sâu hơn và hành vi cụ thể phụ thuộc provider. Cần xử lý các trường hợp đó trong adapter.

Không ghi raw diagnostic, toàn bộ địa chỉ hoặc message content vào log không được bảo vệ. Hãy redaction những dữ liệu không cần thiết khi báo lỗi.

## 12. Một địa chỉ lỗi không có nghĩa cả batch lỗi

Giả sử gửi một message tới ba người:

~~~text
alice@example.net  -> accepted
bob@example.net    -> unknown user
carol@example.net  -> accepted
~~~

Nếu mail sender ném exception do Bob, việc retry lại nguyên message cho cả Alice, Bob và Carol có thể:

- Gửi trùng cho Alice và Carol.
- Tiếp tục thử địa chỉ Bob không tồn tại.
- Làm khó xác định ai thực sự đã nhận.

Một chiến lược đơn giản cho email giao dịch là **mỗi ý định gửi gắn với một recipient**, đặc biệt khi cần theo dõi retry và suppression độc lập. Nếu nghiệp vụ bắt buộc gửi nhiều recipient trong cùng message, phải dùng thông tin kết quả từng recipient từ transport và chính sách provider để quyết định retry.

Không suy ra partial delivery chỉ từ việc API trả exception. Hãy xem các tín hiệu transport thực sự có sẵn.

## 13. Trạng thái outbox phù hợp với lỗi AUTH và recipient

Nếu sử dụng transactional outbox, không nên chỉ có PENDING và SENT. Cần biểu diễn các trạng thái lỗi cần hành động khác nhau.

Một mô hình minh họa:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted ------> ACCEPTED_BY_RELAY
   |
   +-- Temporary error ----> RETRY_WAIT
   |
   +-- AUTH fixed error ---> PAUSED_CONFIG
   |
   +-- Invalid recipient --> INVALID_RECIPIENT
   |
   +-- Policy rejection --> NEEDS_REVIEW
   |
   +-- Ambiguous result ---> UNKNOWN_OUTCOME
   |
   +-- Retry exhausted ---> FAILED
~~~

Tên trạng thái là ví dụ của ứng dụng, không phải enum có sẵn trong Spring.

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **PENDING** | Ý định gửi đã được commit | Chờ worker |
| **PROCESSING** | Worker đã claim | Xử lý trong thời hạn lease |
| **RETRY_WAIT** | Lỗi được đánh giá là tạm thời | Chờ tới nextAttemptAt |
| **PAUSED_CONFIG** | SMTP account cần sửa AUTH/TLS/policy | Không tự retry theo từng message |
| **INVALID_RECIPIENT** | Recipient được xác nhận không hợp lệ | Chờ sửa địa chỉ hoặc suppression |
| **NEEDS_REVIEW** | Từ chối theo policy hoặc nguyên nhân chưa rõ | Điều tra trước khi retry |
| **UNKNOWN_OUTCOME** | Có khả năng message đã được server chấp nhận | Đối soát và retry thận trọng |
| **ACCEPTED_BY_RELAY** | SMTP provider đã chấp nhận message | Theo dõi bounce/delivery nếu có |
| **FAILED** | Hết giới hạn hoặc không thể tiếp tục | Xử lý vận hành |

Không dùng trạng thái ACCEPTED_BY_RELAY để tuyên bố người nhận đã mở thư.

### 13.1. Lỗi AUTH là vấn đề cấp account

Nếu account SMTP A bị lỗi xác thực, hàng nghìn message có thể bị ảnh hưởng. Không cần tăng attempts của từng message thêm hàng chục lần chỉ để chứng minh cùng một credentials vẫn sai.

Có thể đánh dấu account A bị PAUSED_CONFIG, giữ các message PENDING/PAUSED, cảnh báo và khôi phục sau khi cấu hình được xác nhận hợp lệ.

### 13.2. Lỗi recipient là vấn đề cấp địa chỉ

Nếu một recipient cụ thể không hợp lệ, chỉ tác vụ của recipient đó cần được tạm dừng hoặc xử lý. Các message gửi tới địa chỉ hợp lệ khác vẫn tiếp tục.

Tách lỗi theo **account**, **sender domain**, **recipient** và **message** giúp không mở rộng phạm vi sự cố.

## 14. Ghi outbox trong transaction dữ liệu, gửi SMTP sau commit

Một kiến trúc thường dùng:

~~~text
Order service @Transactional
     |
     +-- Commit trạng thái đơn hàng
     +-- Insert mail_outbox(status=PENDING)
     |
     v
   COMMIT
     |
     v
Outbox worker
     |
     +-- Claim event
     +-- Tạo MIME
     +-- Gọi JavaMailSender
     +-- Phân loại AUTH/recipient/policy/network
     +-- Update status hoặc retry schedule
~~~

Nếu transaction nghiệp vụ rollback, outbox row cũng rollback. Nếu commit thành công, worker có thể xử lý tác vụ sau restart.

Quan trọng: **không giữ transaction database đang khóa row trong lúc chờ SMTP**. Worker có thể claim bằng một transaction ngắn, gửi ngoài transaction, rồi cập nhật kết quả trong một transaction ngắn khác.

### 14.1. Ví dụ pseudocode worker

~~~java
public void process(MailOutboxEvent event) {
    if (smtpAccountRegistry.isPaused(event.accountId())) {
        // Không tốn thêm một lần AUTH không hợp lệ.
        outboxService.deferUntilConfigRestored(event.id());
        return;
    }

    try {
        mailDeliveryService.send(event);
        outboxService.markAcceptedByRelay(event.id());
    } catch (Exception ex) {
        FailureSignals signals = failureExtractor.extract(ex);
        RetryDecision decision = retryPolicy.decide(signals);

        outboxService.applyDecision(
                event.id(),
                decision,
                signals
        );
    }
}
~~~

Các service **smtpAccountRegistry**, **outboxService** và **failureExtractor** là các thành phần ứng dụng minh họa, không phải API có sẵn của Spring Mail. Phần áp dụng quyết định phải đặt attempts, nextAttemptAt, lease, account pause và giới hạn retry theo policy.

### 14.2. Retry không được chạy lại toàn bộ nghiệp vụ

Nếu chỉ SMTP lỗi, worker nên retry **ý định gửi email**, không chạy lại transaction tạo đơn hàng, phát hành hóa đơn hoặc cấp mã xác thực.

Có thể tái sử dụng DTO snapshot đã được lưu trong outbox để dựng lại cùng message. Điều này tránh biến một lần gửi lại thành một giao dịch nghiệp vụ mới.

## 15. Idempotency và kết quả SMTP không xác định

Một giới hạn quan trọng:

~~~text
1. Worker gửi DATA.
2. SMTP server chấp nhận message.
3. Kết nối đứt trước khi response tới ứng dụng.
4. Worker ghi nhận timeout.
5. Worker retry.
6. Người nhận có thể nhận hai email.
~~~

Không thể suy ra “message chắc chắn chưa được gửi” chỉ từ một timeout.

### 15.1. Phân biệt retry an toàn hơn và retry có nguy cơ trùng

- Lỗi trước khi có recipient được chấp nhận hoặc trước DATA thường có ít nguy cơ tạo message trùng hơn, nếu có tín hiệu xác định từ transport.
- Lỗi sau khi DATA được truyền và phản hồi cuối không nhận được cần đánh dấu **UNKNOWN_OUTCOME** nếu không xác minh được.
- Một lỗi Java ở tầng cao có thể che mất phase thực tế; khi thiếu thông tin, không tự giả định chưa gửi.

Không thể bảo đảm exactly-once email chỉ bằng retry ở tầng ứng dụng.

### 15.2. Dùng event ID ổn định

Mỗi ý định gửi có event ID không thay đổi giữa các lần retry:

~~~text
mailEventId = ORDER_CONFIRMED:1001:version-3
~~~

Event ID dùng cho log, đối soát và trạng thái outbox. Nó không phải một mã mới tạo ở mỗi lần thử.

### 15.3. Message-ID không phải bảo đảm deduplication

MIME message có header Message-ID. Việc duy trì Message-ID nhất quán có thể giúp một số công cụ đối soát, nhưng không buộc mọi SMTP server hoặc email client loại bỏ bản gửi trùng.

Nếu provider hỗ trợ idempotency key bằng API riêng, có thể sử dụng theo hợp đồng của provider. SMTP thông thường không có exactly-once idempotency key tổng quát.

### 15.4. Nội dung phải chịu được gửi lặp

Với email giao dịch, retry không nên:

- Phát sinh thêm đơn hàng.
- Tạo mã xác thực mới nếu cùng sự kiện.
- Thu tiền lại.
- Thay đổi trạng thái nghiệp vụ không liên quan.
- Khiến một bản email lặp bị hiểu là giao dịch mới.

Hãy dùng ID nghiệp vụ và snapshot ổn định để nội dung không thay đổi ngoài dự kiến giữa các lần thử.

## 16. Xử lý bounce sau khi SMTP đã chấp nhận

Không phải mọi lỗi địa chỉ đều được phát hiện ở RCPT TO. Có trường hợp SMTP relay chấp nhận message, nhưng sau đó hệ thống nhận gửi **delivery status notification (DSN)** hoặc thông báo bounce.

Do đó có thể xảy ra:

~~~text
SMTP send returns success
        |
        v
Provider accepts message
        |
        v
Later delivery attempt fails
        |
        v
Hard bounce or soft bounce
~~~

Một mail job được đánh dấu ACCEPTED_BY_RELAY vẫn có thể có kết quả chuyển phát thất bại sau đó.

### 16.1. Hard bounce và soft bounce

Khái niệm thường dùng:

- **Hard bounce:** lỗi không thể chuyển phát mang tính lâu dài, ví dụ địa chỉ không tồn tại.
- **Soft bounce:** lỗi tạm thời, ví dụ mailbox đầy hoặc server nhận tạm thời không khả dụng.

Tuy nhiên, nhãn hard/soft phụ thuộc provider và không thay thế phân tích SMTP/DSN thực tế.

### 16.2. Không tự suppression chỉ vì có một SMTP 550 mơ hồ

Danh sách suppression cần dựa trên tín hiệu đáng tin cậy. Ví dụ provider xác nhận 5.1.1 user unknown cho một địa chỉ là tín hiệu mạnh hơn một phản hồi 550 chung về policy.

Khi quyết định suppression:

1. Lưu lý do và nguồn dữ liệu.
2. Xác định phạm vi recipient hoặc tenant.
3. Không xóa vĩnh viễn địa chỉ khỏi hồ sơ người dùng nếu chỉ cần ngăn gửi.
4. Cho phép sửa địa chỉ hoặc yêu cầu xác minh lại theo quy trình sản phẩm.
5. Đảm bảo danh sách suppression tuân thủ chính sách privacy/retention.

## 17. Bảo mật khi xử lý lỗi AUTH

Lỗi xác thực thường chứa thông tin có giá trị cho kẻ tấn công. Cần cẩn thận khi log và hiển thị exception.

### 17.1. Không log secrets

Không ghi:

- SMTP password.
- OAuth access token hoặc refresh token.
- Authorization header.
- SMTP AUTH payload.
- Nội dung raw connection transcript chứa dữ liệu nhạy cảm.

Nếu bật debug protocol, phải kiểm soát nghiêm ngặt việc lưu log, môi trường sử dụng và quyền truy cập.

### 17.2. Phân quyền khi sửa credentials

Chỉ người hoặc service được phép mới có thể thay SMTP account credentials. Sau khi sửa, nên kiểm tra kết nối có kiểm soát trước khi mở lại queue.

Không cho phép một yêu cầu từ người dùng cuối tự kích hoạt vô hạn AUTH attempt để “kiểm tra” một tài khoản SMTP chung.

### 17.3. Cảnh báo theo account, không theo từng message

Nếu 500 message cùng thất bại vì một password bị đổi, không cần gửi 500 cảnh báo giống nhau. Có thể gom cảnh báo theo account ID và loại lỗi, trong khi vẫn lưu trạng thái riêng cho các mail job bị ảnh hưởng.

## 18. Quan sát và logging để phân loại lỗi đúng

Một sự kiện lỗi gửi mail có thể lưu những trường sau:

~~~text
eventId
accountId
tenantId
recipientReference
smtpStage
smtpReplyCode
enhancedStatusCode
errorCategory
retryDecision
attemptNumber
nextAttemptAt
provider
timestamp
~~~

Hãy phân quyền và redaction dữ liệu theo quy định. Không cần lưu toàn bộ MIME message, file attachment hoặc credential trong mỗi log.

### 18.1. Metrics hữu ích

Các chỉ số:

- Số email chờ gửi.
- Số email đang retry.
- Số tác vụ bị PAUSED_CONFIG.
- Tỷ lệ lỗi AUTH theo SMTP account.
- Tỷ lệ invalid recipient theo nguồn nhập dữ liệu.
- Tỷ lệ 4xx/5xx theo provider.
- Số trường hợp UNKNOWN_OUTCOME.
- Tuổi tác vụ PENDING cũ nhất.
- Thời gian từ lúc nghiệp vụ commit tới lúc provider accept.
- Số worker đang hoạt động và độ dài queue.

Các metric này giúp phân biệt sự cố cấu hình với một provider outage hoặc một nhóm recipient có dữ liệu sai.

### 18.2. Alert theo hành động cần thực hiện

Ví dụ:

| Alert | Hành động |
| --- | --- |
| SMTP AUTH 535 lặp lại cho account A | Kiểm tra secrets, policy account và OAuth |
| Nhiều 421/4.7.0 trong thời gian ngắn | Giảm concurrency, xem rate limit |
| Nhiều 5.1.1 từ một nguồn đăng ký | Kiểm tra nhập dữ liệu và quy trình xác minh |
| Nhiều 5.7.1 tại MAIL FROM/DATA | Kiểm tra sender, domain authentication và policy |
| UNKNOWN_OUTCOME tăng | Xem network/SMTP response và duplicate risk |
| Outbox backlog tăng liên tục | Xem worker, provider và retry scheduling |

## 19. Kiểm thử chính sách retry

Có thể kiểm thử classifier mà không cần SMTP thật bằng cách tạo các FailureSignals:

~~~java
MailRetryPolicy policy = new MailRetryPolicy();

RetryDecision auth = policy.decide(
        new FailureSignals(
                SmtpStage.AUTH,
                535,
                "5.7.8",
                false,
                false
        )
);

assertEquals(RetryDecision.STOP_FIX_AUTH, auth);

RetryDecision unknownUser = policy.decide(
        new FailureSignals(
                SmtpStage.RCPT_TO,
                550,
                "5.1.1",
                false,
                false
        )
);

assertEquals(
        RetryDecision.STOP_INVALID_RECIPIENT,
        unknownUser
);

RetryDecision temporary = policy.decide(
        new FailureSignals(
                SmtpStage.RCPT_TO,
                450,
                "4.2.0",
                false,
                false
        )
);

assertEquals(
        RetryDecision.RETRY_WITH_BACKOFF,
        temporary
);
~~~

Ví dụ dùng mô hình đã định nghĩa ở phần trước. Các tín hiệu được truyền trực tiếp để test chính sách; test trích xuất exception của provider nên được thực hiện riêng.

### 19.1. Bảng tình huống kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| AUTH 535 với credentials không đổi | Dừng retry tự động và cảnh báo |
| AUTH 454 có tín hiệu tạm thời | Retry có backoff, giới hạn attempts |
| RCPT TO 550 5.1.1 | Đánh dấu recipient không hợp lệ theo policy |
| RCPT TO 450 4.2.x | Retry theo lịch |
| 550 5.7.1 policy rejection | Không gắn nhãn recipient unknown; cần xem policy |
| TLS certificate không hợp lệ | Dừng và sửa cấu hình |
| Rate limit trên account | Giảm tốc, không retry ngay |
| Kết nối mất sau DATA | UNKNOWN_OUTCOME; xem duplicate risk |
| Gửi tới nhiều recipient có partial acceptance | Không gửi lại mù cho người đã được chấp nhận |
| Worker restart sau PAUSED_CONFIG | Không tự mở queue khi chưa sửa và kiểm tra config |
| Worker restart sau RETRY_WAIT | Tiếp tục theo nextAttemptAt |
| Event bị xử lý lại | Không tạo thêm tác vụ nghiệp vụ mới |

### 19.2. SMTP capture server và giả lập lỗi

Một SMTP test server hoặc transport fake có thể tạo phản hồi AUTH/RCPT TO/DATA để kiểm tra worker. Với production provider, cần test riêng các cơ chế xác thực, rate limit và cách họ thể hiện enhanced status code.

Không thử nhiều lần credentials sai trên tài khoản thật chỉ để kiểm tra retry policy. Dùng fake/stub hoặc môi trường test được cho phép.

## 20. Ma trận quyết định vận hành

| Loại lỗi | Retry tự động? | Trạng thái gợi ý | Việc cần làm |
| --- | --- | --- | --- |
| Sai password hoặc SMTP AUTH bị tắt | **Không**, khi cấu hình chưa đổi | PAUSED_CONFIG | Sửa credentials/quyền |
| OAuth access token hết hạn và refresh hợp lệ | Có giới hạn sau refresh | RETRY_WAIT hoặc PROCESSING | Refresh an toàn, không storm |
| Lỗi AUTH tạm thời 4xx | Có giới hạn | RETRY_WAIT | Backoff và theo dõi |
| Recipient sai cú pháp | **Không** | INVALID_RECIPIENT | Sửa địa chỉ |
| Recipient user unknown 5.1.1 rõ ràng | **Không** | INVALID_RECIPIENT | Suppress hoặc xác minh |
| Recipient tạm thời không khả dụng 4xx | Có giới hạn | RETRY_WAIT | Backoff theo provider |
| Mailbox full | Tùy mã/provider | RETRY_WAIT hoặc NEEDS_REVIEW | Tránh gắn nhãn unknown user |
| Sender/policy bị từ chối 5.7.x | Không retry nguyên trạng | NEEDS_REVIEW | Kiểm tra quyền, domain, nội dung |
| Server rate limit 4xx | Có, sau chờ | RETRY_WAIT | Giảm tốc và concurrency |
| TLS config/certificate sai | **Không** | PAUSED_CONFIG | Sửa cấu hình an toàn |
| Timeout trước DATA với phase xác định | Có giới hạn | RETRY_WAIT | Backoff và kiểm tra network |
| Timeout sau DATA với kết quả chưa rõ | Không retry mù | UNKNOWN_OUTCOME | Đối soát, chấp nhận duplicate risk khi quyết định retry |
| MIME/template hỏng | **Không** đến khi sửa | NEEDS_REVIEW | Sửa template/dữ liệu |

Không dùng bảng này như một thay thế hoàn toàn cho tài liệu provider. Nó là khung để xây dựng policy có giải thích được và có hành động tiếp theo.

## 21. Câu hỏi thường gặp

**1. Tại sao lỗi AUTH không nên retry liên tục?**

Nếu mật khẩu sai, account bị khóa hoặc SMTP AUTH bị tắt, credentials không đổi sẽ tiếp tục bị từ chối. Retry dồn dập làm tăng tải và có thể kích hoạt chính sách bảo mật.

**2. Lỗi 535 có phải lỗi địa chỉ người nhận không?**

Không. 535 thường liên quan quá trình AUTH. Cần kiểm tra account, cơ chế đăng nhập và quyền, không đưa recipient vào danh sách địa chỉ không hợp lệ.

**3. Lỗi 454 có thể retry không?**

Có thể, nếu provider xác nhận đây là lỗi AUTH tạm thời. Cần backoff, giới hạn attempts và không gửi dồn dập.

**4. Gặp SMTP 550 có nên xóa email recipient?**

Không tự động. 550 có thể là mailbox không tồn tại, nhưng cũng có thể là policy rejection. Chỉ xử lý recipient theo tín hiệu đủ rõ như enhanced status 5.1.1 trong ngữ cảnh phù hợp.

**5. 501 hoặc 553 với lỗi cú pháp có nên retry?**

Không nên retry cùng địa chỉ chưa sửa. Cần cập nhật dữ liệu và kiểm tra cú pháp trước khi tạo tác vụ gửi mới.

**6. Mailbox full có giống invalid recipient không?**

Không. Một mailbox đầy có thể tiếp tục nhận mail sau khi được giải phóng dung lượng. Xử lý theo mã và chính sách của provider.

**7. Spring MailAuthenticationException có đủ để biết credentials sai không?**

Nó là tín hiệu lỗi xác thực, nhưng cần xem nguyên nhân gốc để phân biệt cấu hình sai, token hết hạn và lỗi tạm thời của dịch vụ xác thực.

**8. Retry lỗi sau DATA có nguy cơ gì?**

Server có thể đã chấp nhận message nhưng ứng dụng không nhận được response. Retry có thể tạo email trùng.

**9. Message-ID có ngăn SMTP gửi trùng không?**

Không bảo đảm. Nó giúp nhận diện và đối soát message, nhưng SMTP không yêu cầu mọi server/client deduplicate theo Message-ID.

**10. Có nên retry toàn bộ mail khi chỉ một recipient lỗi không?**

Không nên nếu một số recipient khác đã được chấp nhận. Cần theo dõi kết quả từng người hoặc tách một ý định gửi cho mỗi recipient.

**11. Làm gì khi tất cả tác vụ đều lỗi AUTH?**

Tạm dừng account SMTP tương ứng, cảnh báo, sửa credentials/cấu hình, kiểm tra có kiểm soát rồi tiếp tục queue. Không tăng attempts vô ích của từng message.

**12. Có thể biết chắc một địa chỉ tồn tại bằng InternetAddress.validate() không?**

Không. API chủ yếu kiểm tra cú pháp. Nó không xác nhận mailbox thật sự tồn tại hoặc người dùng sở hữu địa chỉ đó.

**13. Bounce có thể xảy ra sau khi JavaMailSender trả thành công không?**

Có. SMTP relay có thể chấp nhận message rồi hệ thống chuyển phát sau đó báo bounce. Cần theo dõi DSN/provider event nếu nghiệp vụ yêu cầu.

**14. Outbox có bảo đảm exactly-once email không?**

Không. Outbox lưu bền vững ý định gửi, nhưng worker có thể crash sau SMTP accept và trước khi ghi trạng thái, khiến lần retry gửi thêm một message.

**15. Lỗi 4xx có phải luôn retry không?**

Không. Retry cần dựa trên stage, nội dung phản hồi, provider, giới hạn attempts và duplicate risk. Một lỗi cấu hình tạm thời không nên được thử mãi mà không có người xử lý.

## 22. Ghi nhớ khi xử lý lỗi xác thực hoặc địa chỉ

**Không retry mù mọi MailException.** Hãy phân biệt lỗi xác thực, lỗi recipient, lỗi policy, lỗi tạm thời và kết quả gửi chưa xác định. Phản hồi SMTP gồm mã ba chữ số, enhanced status code và diagnostic text; cần đọc chúng cùng giai đoạn CONNECT, AUTH, MAIL FROM, RCPT TO hoặc DATA. **Một mã 550 chung không đủ để kết luận mailbox không tồn tại**, trong khi AUTH 535 thường là vấn đề của tài khoản gửi chứ không phải địa chỉ người nhận.

Với lỗi xác thực cố định, hãy **tạm dừng SMTP account bị ảnh hưởng, cảnh báo và sửa cấu hình** trước khi thử lại có kiểm soát. Với recipient sai cú pháp hoặc user unknown đã được xác nhận, hãy **sửa dữ liệu hoặc suppression theo chính sách**, không gửi lại nguyên trạng. Với lỗi thực sự tạm thời, dùng **backoff, jitter, giới hạn attempts và concurrency**. Nếu server có thể đã nhận DATA, đánh dấu **UNKNOWN_OUTCOME** và xử lý nguy cơ gửi trùng thay vì giả định send thất bại hoàn toàn.

Trong Spring Framework Mail, hãy đặt logic phân loại ngoài JavaMailSender, trích xuất cause chain và SMTP diagnostics qua tầng infrastructure, lưu quyết định vào outbox/queue và retry chính **tác vụ gửi**, không chạy lại transaction nghiệp vụ. Bảo vệ credentials và dữ liệu người nhận trong log. Mục tiêu của retry không phải “thử cho đến khi hết lỗi”, mà là **phục hồi đúng những lỗi có thể phục hồi, dừng đúng những lỗi cần sửa và tránh tạo tác dụng phụ mới**.
