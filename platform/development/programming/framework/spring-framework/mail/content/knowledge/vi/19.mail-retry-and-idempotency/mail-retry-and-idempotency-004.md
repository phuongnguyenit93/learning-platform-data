# Phân loại exception cho chính sách retry

## 1. Vì sao phải phân loại lỗi trước khi gửi lại email?

Trong một ứng dụng sử dụng **Spring Framework Mail**, việc gọi **JavaMailSender.send(...)** có thể thất bại vì nhiều nguyên nhân rất khác nhau: thiếu trường bắt buộc khi dựng email, sai tài khoản SMTP, recipient không hợp lệ, server tạm thời quá tải, kết nối bị ngắt hoặc ứng dụng không nhận được phản hồi cuối cùng từ SMTP server.

Nếu mọi exception đều được xử lý bằng cách thử gửi lại ngay, ứng dụng có thể:

- Gửi lặp đi lặp lại một email không bao giờ hợp lệ.
- Làm tăng tải trên SMTP server đang quá tải.
- Khóa hàng đợi bởi lỗi cấu hình không thể tự hồi phục.
- Gửi trùng email sau một timeout dù server đã nhận thông điệp.
- Gửi lại cho những recipient đã nhận thành công trong một batch có kết quả một phần.
- Báo “đã gửi thất bại” hoặc “đã giao thành công” khi thực tế chưa đủ thông tin để kết luận.

Do đó, trước khi retry cần **phân loại lỗi dựa trên loại exception, nguyên nhân gốc, phản hồi SMTP, giai đoạn lỗi xảy ra và trạng thái đã biết của lần gửi**.

Mục tiêu của bài này là thiết kế chính sách retry dựa trên bằng chứng, thay vì dùng quy tắc đơn giản “bắt tất cả exception rồi gửi lại”.

Luồng xử lý nên có dạng:

~~~text
Tạo nội dung + MimeMessage
            |
            v
     JavaMailSender.send(...)
            |
      +-----+------+
      |            |
      v            v
   Thành công     Exception
      |            |
      v            v
  SUBMITTED    Thu thập ngữ cảnh
                   |
                   v
             Phân loại lỗi
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
  Retry được    Không retry   Chưa rõ kết quả
       |           |           |
       v           v           v
  RETRY_WAIT   FAILED/ALERT   UNKNOWN/RECONCILE
~~~

**Retry chỉ là một trong các hành động có thể chọn.** Một hệ thống tốt cũng biết khi nào phải dừng, khi nào cần sửa dữ liệu/cấu hình và khi nào phải đối soát trước khi quyết định gửi lại.

## 2. Phân biệt lỗi gửi với trạng thái giao hàng đến người nhận

Trước khi phân loại exception, cần hiểu lời gọi gửi email đại diện cho bước nào trong hành trình email:

~~~text
Ứng dụng
  |
  v
Tạo MIME
  |
  v
SMTP submission
  |
  v
SMTP server / Email provider chấp nhận
  |
  v
Relay / Queue / MX phía nhận
  |
  v
Mailbox / Spam / Quarantine / Bounce
~~~

Lời gọi **JavaMailSender.send(...)** thành công thường có nghĩa email đã được nộp thành công cho mail transport hoặc SMTP server ở chặng đầu. Nó **không bảo đảm email đã vào Inbox, đã đến tất cả recipient hoặc đã được mở**.

Ngược lại, một exception từ send không phải lúc nào cũng chứng minh SMTP server chưa nhận thông điệp. Ví dụ, kết nối có thể bị ngắt sau khi server đã chấp nhận DATA nhưng trước khi ứng dụng nhận được phản hồi cuối.

Vì vậy, nên tách hai nhóm trạng thái:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Submission status** | PENDING, SUBMITTED, RETRY_WAIT, UNKNOWN, FAILED | Ứng dụng biết gì về việc nộp email |
| **Delivery status** | DELIVERED, BOUNCED, DEFERRED, COMPLAINED | Kết quả chuyển phát được provider hoặc hệ thống nhận báo lại |

Không đặt trạng thái **DELIVERED** chỉ vì không có exception. Nếu có webhook bounce hoặc delivery event từ nhà cung cấp, xử lý nó như một luồng kết quả riêng.

## 3. Ba nhóm lỗi cốt lõi

Một cách phân loại dễ áp dụng là chia thành ba nhóm:

| Nhóm | Bản chất | Hành động mặc định |
|---|---|---|
| **Transient / Retryable** | Lỗi có khả năng tự hồi phục theo thời gian | Retry với backoff, jitter và giới hạn |
| **Permanent / Non-retryable** | Cùng input/cấu hình sẽ tiếp tục thất bại | Dừng, sửa nguyên nhân, cảnh báo khi cần |
| **Ambiguous / Unknown outcome** | Không biết server đã nhận email hay chưa | Đối soát hoặc xử lý theo chính sách chống trùng |

Ví dụ:

**Transient:**

- SMTP trả **421**, **450**, **451** hoặc **452** theo ngữ cảnh thích hợp.
- Server tạm thời quá tải hoặc áp dụng giới hạn tốc độ.
- Không thể kết nối tới SMTP server trong một khoảng thời gian ngắn và xác nhận chưa bắt đầu nộp thư.
- DNS gặp lỗi tạm thời, nếu xác định được là tạm thời.

**Permanent hoặc cần can thiệp:**

- Địa chỉ email không hợp lệ về cú pháp.
- SMTP authentication thất bại do credential hoặc quyền không đúng.
- MIME/template không thể dựng do dữ liệu hoặc cấu hình sai.
- SMTP từ chối recipient vĩnh viễn bằng mã 5xx.
- Thông điệp vượt giới hạn kích thước không thể khắc phục bằng chờ đợi.

**Ambiguous:**

- Timeout khi chờ phản hồi cuối sau lệnh SMTP DATA.
- Kết nối bị cắt sau khi ứng dụng đã truyền message nhưng chưa biết kết quả.
- Nhà cung cấp chấp nhận yêu cầu nhưng ứng dụng mất phản hồi xác nhận.

Phân loại còn phụ thuộc vào **pha xảy ra lỗi**. Cùng một SocketTimeoutException có thể là retryable nếu xảy ra trước khi nộp thư, nhưng có thể là ambiguous nếu xảy ra sau khi đã truyền nội dung.

## 4. Các giai đoạn trong một lần gửi SMTP

Để phân loại đúng, nên hình dung tiến trình gửi theo từng pha:

~~~text
1. PREPARE
   Tạo subject, recipient, HTML/MIME, attachment
             |
             v
2. CONNECT
   TCP connection, DNS, timeout, proxy
             |
             v
3. SECURE / AUTHENTICATE
   TLS, STARTTLS, credential
             |
             v
4. ENVELOPE
   MAIL FROM, RCPT TO
             |
             v
5. DATA
   Gửi nội dung MIME
             |
             v
6. WAIT FINAL REPLY
   Chờ SMTP server xác nhận nhận hoặc từ chối DATA
             |
             v
7. SUBMITTED
   Server đã trả lời chấp nhận ở chặng này
~~~

| Pha | Lỗi điển hình | Nhận định ban đầu |
|---|---|---|
| PREPARE | Template thiếu dữ liệu, invalid address syntax, attachment không đọc được | Thường không retry mù |
| CONNECT | Connection refused, connect timeout | Thường retry được nếu chưa gửi DATA |
| TLS/AUTH | Authentication failed, certificate lỗi | Thường cần sửa cấu hình; lỗi kết nối thoáng qua phải xét riêng |
| MAIL FROM / RCPT TO | SMTP 4xx hoặc 5xx | Xem phản hồi của server, từng recipient |
| DATA trước phản hồi rõ ràng | Kết nối lỗi giữa chừng | Có thể chưa rõ, tùy bằng chứng truyền/nhận |
| WAIT FINAL REPLY | Read timeout, connection reset | Kết quả có thể chưa rõ |
| Sau khi nhận phản hồi thành công | Lỗi lưu trạng thái ứng dụng | Không gửi lại chỉ vì ghi DB thất bại |

Không phải implementation SMTP nào cũng cung cấp thông tin chi tiết về từng pha qua Spring MailException. Khi không đủ bằng chứng, cần giữ trạng thái **UNKNOWN** thay vì suy diễn rằng lỗi chắc chắn xảy ra trước khi server nhận thư.

## 5. Hệ thống exception của Spring Framework Mail

Spring Mail có abstraction **MailException** và những exception thường gặp sau:

| Exception | Ý nghĩa khái quát | Chính sách gợi ý |
|---|---|---|
| **MailAuthenticationException** | SMTP authentication thất bại | Không retry cùng credential liên tục; cảnh báo và điều tra |
| **MailParseException** | Lỗi phân tích hoặc chuẩn bị nội dung mail | Dừng, sửa input/template/MIME |
| **MailPreparationException** | Lỗi khi chuẩn bị thông điệp, ví dụ callback preparator | Dừng hoặc phân loại nguyên nhân bên trong |
| **MailSendException** | Có lỗi trong quá trình gửi một hoặc nhiều message | Phải xem nguyên nhân, SMTP reply và kết quả từng message |
| **MailException** (chung) | Ngoại lệ nền của tầng Spring Mail | Không đủ thông tin để mặc định retry |

Tên exception cho biết **tầng phát hiện lỗi**, nhưng không đủ để kết luận mức độ tạm thời của tất cả trường hợp.

### MailAuthenticationException

Ví dụ server từ chối thông tin xác thực:

~~~text
SMTP authentication failed
  -> MailAuthenticationException
  -> credential sai / tài khoản bị khóa / cơ chế auth không được hỗ trợ
~~~

Với cùng username/password và cấu hình, retry sau vài giây thường không giải quyết được. Hãy:

- Kiểm tra credential và cơ chế authentication được provider yêu cầu.
- Kiểm tra quyền gửi, tài khoản và chính sách ứng dụng.
- Cảnh báo vận hành hoặc chuyển notification sang trạng thái chờ sửa cấu hình.
- Chỉ replay sau khi nguyên nhân được khắc phục hoặc có bằng chứng đây là lỗi tạm thời của provider.

### MailParseException và MailPreparationException

Các lỗi này thường liên quan đến dữ liệu hoặc quá trình tạo thông điệp:

- Địa chỉ không hợp lệ.
- Header hoặc dữ liệu MIME không đúng.
- Template render thất bại.
- Một **MimeMessagePreparator** ném MessagingException.

Nếu dữ liệu không đổi, retry thường sẽ tạo lại cùng lỗi. Tuy nhiên cần xem cause: nếu lỗi chuẩn bị là do nguồn attachment remote tạm thời không truy cập được, chính sách có thể khác với lỗi template thiếu biến.

### MailSendException

Đây là trường hợp **không thể phân loại chỉ bằng class**. Nó có thể chứa lỗi kết nối, phản hồi SMTP, lỗi gửi từng message hoặc tình huống kết quả không chắc chắn.

Một MailSendException có thể chứa thông tin nhiều message trong một batch. Không nên tự động retry cả batch mà không xác định phần nào thất bại.

## 6. Exception bên dưới Jakarta Mail và mạng

Spring Mail sử dụng Jakarta Mail để thao tác với SMTP. Các nguyên nhân gốc có thể thuộc nhiều tầng:

| Tầng | Ví dụ | Ý nghĩa khi xét retry |
|---|---|---|
| Jakarta Mail | **AuthenticationFailedException** | Thường không retry cùng cấu hình |
| Jakarta Mail | **SendFailedException** | Có thể có recipient bị từ chối hoặc giao một phần |
| Jakarta Mail | **MessagingException** | Lỗi tổng quát; cần xem nguyên nhân chi tiết |
| Java networking | **ConnectException** | Có thể retry nếu không có dấu hiệu đã gửi message |
| Java networking | **SocketTimeoutException** | Phải biết xảy ra ở pha nào |
| Java networking | **UnknownHostException** | Xem DNS/tên host; không kết luận tạm thời chỉ từ class |
| TLS/security | **SSLHandshakeException** | Có thể do chứng chỉ/cấu hình sai hoặc sự cố tạm thời; thường cần điều tra |
| Nguồn dữ liệu | **IOException** | Có thể là file mất, quyền đọc sai hoặc remote timeout |

**MessagingException** có thể lưu một chuỗi exception liên quan qua **getNextException()** bên cạnh chuỗi cause thông thường. Nếu cần chẩn đoán đầy đủ, bộ thu thập nguyên nhân nên biết cả hai cơ chế và tránh vòng lặp.

Khi dùng SMTP provider cụ thể, có thể có exception bổ sung chứa mã SMTP response và địa chỉ recipient, chẳng hạn các lớp SMTP của Jakarta Mail implementation. Đây là chi tiết phụ thuộc provider; không nên giả định mọi implementation đều có cùng class hoặc getter.

### Đừng phân loại bằng chuỗi trong exception message

Ví dụ không nên làm:

~~~java
if (ex.getMessage().contains("timeout")) {
    retry();
}
~~~

Vấn đề:

- Message có thể khác nhau giữa các phiên bản thư viện.
- Message có thể bị localization hoặc chứa chi tiết từ server.
- Chuỗi “timeout” không chỉ ra nó xảy ra trước hay sau DATA.
- Message có thể chứa dữ liệu nhạy cảm; không nên dùng để quyết định nghiệp vụ hoặc ghi nguyên văn vào log.

Ưu tiên **loại exception, SMTP reply code được xác thực và ngữ cảnh gửi**.

## 7. Mã SMTP 4xx và 5xx

SMTP server dùng mã phản hồi để mô tả kết quả của một lệnh. Quy tắc tổng quát:

- **4xx:** lỗi tạm thời; client có thể thử lại sau khi chờ, tùy chính sách.
- **5xx:** lỗi thường mang tính vĩnh viễn cho lệnh/yêu cầu hiện tại; cần sửa nguyên nhân thay vì retry mù.
- **2xx:** lệnh tương ứng được chấp nhận; riêng phản hồi chấp nhận DATA là dấu hiệu submission đã thành công ở chặng đó.

Một số ví dụ:

| SMTP code | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| **421** | Dịch vụ tạm thời không khả dụng, đóng kết nối | Retry với backoff nếu chưa được chấp nhận |
| **450** | Mailbox hoặc tác vụ tạm thời không khả dụng | Retry có giới hạn |
| **451** | Lỗi xử lý tạm thời | Retry và theo dõi |
| **452** | Thiếu tài nguyên hoặc giới hạn tạm thời | Retry với delay phù hợp |
| **550** | Mailbox không khả dụng hoặc bị từ chối | Thường dừng; kiểm tra recipient/chính sách |
| **551** | User không có ở máy chủ này, có thể có chuyển tiếp | Không retry y nguyên nếu không có cơ chế sửa route |
| **552** | Vượt hạn mức lưu trữ hoặc kích thước tùy server | Xem chi tiết; thường cần can thiệp |
| **553** | Tên mailbox không hợp lệ | Sửa địa chỉ |
| **554** | Giao dịch bị từ chối | Phân tích chính sách, content hoặc server response |

**Không nên quyết định chỉ theo một số code mà bỏ qua lệnh đang thực thi.** Ví dụ mã 5xx trong RCPT TO không giống lỗi 5xx trong AUTH. Với mail gateway, text của mã phản hồi và SMTP enhanced status code giúp giải thích thêm lý do.

### Enhanced status code

Một số SMTP server trả mã mở rộng như:

~~~text
550 5.1.1 User unknown
451 4.7.1 Try again later
552 5.3.4 Message size exceeds fixed maximum message size
~~~

Ba chữ số đầu thể hiện nhóm 4xx/5xx. Mã dạng **x.y.z** bổ sung thông tin. Chẳng hạn lỗi kích thước cố định cần giảm attachment; chờ vài giây không giúp ích. Cách phân tích enhanced status cần bám theo hợp đồng của provider.

## 8. Kết nối và DNS: không phải lỗi mạng nào cũng giống nhau

Một số lỗi có thể được retry sau khi xác nhận chưa bắt đầu nộp email:

- Kết nối TCP bị từ chối khi SMTP server đang khởi động lại.
- Connect timeout vì mạng tạm nghẽn.
- Lỗi DNS tạm thời từ resolver.
- Kết nối bị ngắt trước khi SMTP session gửi lệnh MAIL FROM.

Tuy nhiên, retry liên tục có thể phản tác dụng khi:

- Hostname cấu hình sai, không tồn tại lâu dài.
- Port sai hoặc firewall chặn vĩnh viễn.
- DNS record bị cấu hình nhầm.
- SMTP server chỉ cho phép IP khác trong allowlist.
- TLS certificate không đáng tin cậy do truststore sai.

Ví dụ:

~~~text
ConnectException tại CONNECT:
    -> Có thể retry với backoff

UnknownHostException cho smtp.invalid:
    -> Kiểm tra hostname/DNS trước khi retry dài hạn

SocketTimeoutException khi chờ final DATA reply:
    -> Không biết server đã chấp nhận hay chưa
~~~

Vì vậy hệ thống nên ghi lại **pha xảy ra lỗi** hoặc mức độ tin cậy của thông tin đó. Nếu tầng mail client không cung cấp pha chính xác, đừng suy đoán từ class IOException.

## 9. Authentication và TLS: khi nào không nên retry?

Ví dụ lỗi xác thực:

~~~java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Không gửi lại liên tục bằng cùng credential.
    // Chuyển sang trạng thái cần kiểm tra cấu hình/quyền.
    throw ex;
}
~~~

Nếu SMTP server trả lỗi authentication rõ ràng, cần kiểm tra credential, quyền tài khoản, cơ chế AUTH và chính sách nhà cung cấp. Retry nhanh với cùng secret có thể kích hoạt khóa tài khoản hoặc tăng lượng lỗi.

Với TLS, không nên tắt kiểm tra certificate hoặc giảm bảo mật chỉ để làm lần gửi sau thành công. Thay vào đó:

- Kiểm tra hostname và chứng chỉ.
- Kiểm tra truststore và chuỗi CA.
- Xác minh yêu cầu STARTTLS/SMTPS theo provider.
- Kiểm tra đồng hồ hệ thống.
- Phân biệt lỗi cấu hình ổn định với sự cố hạ tầng tạm thời.

Không có một câu trả lời tuyệt đối cho mọi SSLHandshakeException. Nhưng mặc định **không retry mù và không bỏ qua xác thực TLS** là hướng vận hành an toàn.

## 10. Lỗi chuẩn bị MIME, template và attachment

Những lỗi xảy ra trước khi nộp thư thường cần sửa input hoặc nội dung:

| Lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Template | Thiếu template key hoặc biến bắt buộc | Dừng, sửa renderer/data |
| Địa chỉ | AddressException, recipient sai cú pháp | Sửa địa chỉ, không retry y nguyên |
| Header | Subject hoặc địa chỉ không hợp lệ | Kiểm tra và chuẩn hóa dữ liệu |
| Charset | Nội dung encode không đúng | Sửa cách tạo MIME |
| Attachment | File local không tồn tại | Kiểm tra vòng đời file, không retry mù |
| Remote attachment | Object storage tạm thời timeout | Retry tải file có giới hạn nếu nguồn còn tồn tại |
| Kích thước | File vượt giới hạn provider | Giảm file hoặc gửi liên kết an toàn |

**Lỗi chuẩn bị có thể có nguyên nhân bên ngoài tạm thời**, nhưng điều đó không biến mọi MailPreparationException thành retryable.

Ví dụ cùng là IOException:

~~~text
NoSuchFileException:
    file tạm đã bị xóa
    -> cần sửa vòng đời tài nguyên

SocketTimeoutException từ object storage:
    nguồn còn tồn tại, mạng tạm lỗi
    -> có thể retry bước tải file
~~~

Không nên retry nguyên việc gửi SMTP nếu nguồn attachment chưa đọc được. Hãy kiểm tra và chuẩn bị lại nội dung trước khi đưa email trở lại hàng gửi.

## 11. Timeout: phải biết lỗi xảy ra trước hay sau DATA

Một timeout là ví dụ rõ ràng cho việc **exception class chưa đủ để quyết định retry**.

### Timeout tại CONNECT

~~~text
Ứng dụng --X--> SMTP server
           connect timeout

Chưa có SMTP session hoặc chưa gửi thông điệp.
~~~

Nếu có bằng chứng kết nối chưa được thiết lập và dữ liệu email chưa được nộp, retry với backoff có thể phù hợp.

### Timeout khi gửi dữ liệu

~~~text
Ứng dụng ---- DATA bytes ----> SMTP server
                    |
                    X connection reset
~~~

Tùy thời điểm kết nối bị cắt, server có thể đã nhận một phần hoặc toàn bộ dữ liệu. Nếu không có phản hồi cuối của lệnh DATA, ứng dụng có thể không biết message đã được chấp nhận hay chưa.

### Timeout khi chờ phản hồi cuối của DATA

~~~text
Ứng dụng                        SMTP server
    |                                |
    | ------ DATA / body ---------> |
    | ------ kết thúc DATA ------> |
    |                                | xử lý, có thể enqueue
    | <------- phản hồi 250 -------- X
    |             mất kết nối        |
    v
SocketTimeoutException / I/O error
~~~

Nếu server đã chấp nhận và đưa thư vào queue, gửi lại có thể tạo bản thứ hai. Vì thế **lỗi khi chờ phản hồi cuối sau DATA cần được coi là kết quả không rõ nếu không có bằng chứng server từ chối**.

### Nhận phản hồi từ chối rõ ràng thì sao?

Nếu SMTP server đã trả một phản hồi 4xx hoặc 5xx xác định rằng nó từ chối giao dịch, tình huống khác với mất phản hồi. Với một phản hồi 4xx rõ ràng, có thể retry theo chính sách; với 5xx rõ ràng, thường cần sửa nguyên nhân.

Điểm mấu chốt:

| Bằng chứng | Nhận định |
|---|---|
| Chưa mở kết nối/chưa nộp message | Có thể retry sau lỗi tạm thời |
| Đã nhận phản hồi 4xx cho bước quyết định | Retryable theo điều kiện |
| Đã nhận phản hồi 5xx cho bước quyết định | Thường non-retryable |
| Đã nhận xác nhận chấp nhận DATA | Đã submitted; không gửi lại |
| Đã truyền dữ liệu, mất phản hồi cuối | UNKNOWN; cần đối soát |

Nếu không nắm được pha hoặc phản hồi, không nên tự tạo một nhãn giả như “chắc chắn chưa gửi”.

## 12. Một MailSendException có thể chứa nhiều lỗi

**JavaMailSender** hỗ trợ gửi nhiều message. Nếu một lệnh gửi một batch có lỗi, Spring có thể tạo **MailSendException** và cung cấp thông tin lỗi của các message thông qua những API như:

~~~java
MailSendException exception = ...;

Map<Object, Exception> failedMessages = exception.getFailedMessages();
Exception[] messageExceptions = exception.getMessageExceptions();
~~~

Đây là các phương thức để xem thông tin lỗi, không phải lời gọi gửi. Trong thực tế, ứng dụng nhận exception qua catch:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    Map<Object, Exception> failed = ex.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object message = entry.getKey();
        Exception error = entry.getValue();

        // Dùng định danh message của ứng dụng để đối chiếu record.
        // Phân loại error riêng cho từng message thất bại.
    }
}
~~~

Ví dụ trên giả định biến **messages** là mảng MimeMessage đã được chuẩn bị. Thông tin map cần được đối chiếu với notification ID do ứng dụng quản lý; không dùng Object.toString() làm định danh ổn định hoặc ghi nội dung MIME vào log.

### Vì sao không retry cả batch?

Giả sử gửi ba thư:

~~~text
Email A: được server chấp nhận
Email B: lỗi recipient
Email C: lỗi mạng
~~~

Nếu catch MailSendException rồi gửi lại nguyên batch A+B+C, Email A có thể bị gửi trùng. Email B tiếp tục thất bại vì dữ liệu không hợp lệ. Email C cần phân loại theo pha xảy ra lỗi.

Thay vì gửi lại cả batch:

1. Gắn notification ID ổn định cho từng message.
2. Ghi nhận kết quả cho từng message khi có đủ bằng chứng.
3. Phân loại nguyên nhân của từng message thất bại.
4. Chỉ retry những message chắc chắn chưa được chấp nhận và có lỗi retryable.
5. Đánh dấu UNKNOWN nếu không xác định được kết quả của một message.

**Danh sách lỗi không luôn chứng minh mọi message không có trong map đều đã được chuyển phát cuối cùng.** Nó phải được diễn giải theo hợp đồng của API và điểm lỗi thực tế.

## 13. Một thông điệp có nhiều recipient: partial success

Ngay cả khi chỉ gửi một **MimeMessage**, email đó có thể có nhiều người nhận ở To, Cc và Bcc. Một số mail transport có thể thành công với một tập recipient và thất bại với tập khác, tùy cách cấu hình và hành vi SMTP.

Jakarta Mail có **SendFailedException** với các phương thức giúp tìm hiểu tập địa chỉ:

~~~java
SendFailedException ex = ...;

Address[] invalid = ex.getInvalidAddresses();
Address[] validSent = ex.getValidSentAddresses();
Address[] validUnsent = ex.getValidUnsentAddresses();
~~~

Ý nghĩa tổng quát:

- **invalidAddresses:** địa chỉ không hợp lệ theo lỗi được báo.
- **validSentAddresses:** địa chỉ hợp lệ đã được coi là gửi thành công ở phạm vi mà transport xác định.
- **validUnsentAddresses:** địa chỉ hợp lệ chưa gửi được.

Tập dữ liệu có thể rỗng hoặc không đầy đủ trong một số đường lỗi; đây không phải bằng chứng tuyệt đối về delivery cuối cùng. Cần xem cách Jakarta Mail provider và SMTP server triển khai hành vi gửi một phần.

### Rủi ro khi retry nguyên MimeMessage

~~~text
Recipient A  -> accepted
Recipient B  -> rejected
Recipient C  -> accepted
~~~

Nếu gửi lại cả message cho A, B, C, A và C có thể nhận trùng. Phương án thực tế là:

- Lưu notification state theo từng recipient khi hệ thống thật sự cần gửi một message nhiều người nhận.
- Chỉ xây dựng lần gửi lại cho tập recipient phù hợp, khi có bằng chứng trạng thái rõ ràng.
- Với thông báo giao dịch có dữ liệu riêng, thường đơn giản và an toàn hơn khi tạo **một notification cho một recipient**.

Không suy ra rằng mọi lỗi SendFailedException đều khiến tất cả recipient thất bại. Ngược lại, cũng không suy ra những recipient được ghi nhận là validSent đã chắc chắn thấy email trong Inbox.

## 14. Phân loại theo lỗi cuối cùng và hành động vận hành

Một policy có thể dùng các hành động sau:

| Hành động | Khi chọn | Kết quả |
|---|---|---|
| **RETRY** | Có bằng chứng lỗi tạm thời và chưa nhận acceptance | Đặt next_attempt_at với backoff |
| **STOP** | Lỗi dữ liệu, cấu hình hoặc từ chối vĩnh viễn | Đánh dấu FAILED hoặc cần can thiệp |
| **RECONCILE** | Kết quả không rõ, có khả năng đã accepted | Đánh dấu UNKNOWN; đối soát trước retry |
| **SUBMITTED** | Có bằng chứng server đã nhận message ở chặng submission | Ghi nhận đã nộp, theo dõi delivery riêng |

**SUBMITTED không phải một loại exception**, mà là một kết quả gửi cần giữ riêng để tránh retry do lỗi xảy ra sau khi SMTP đã chấp nhận thư.

### Ma trận quyết định minh họa

| Exception / bằng chứng | Pha | Hành động |
|---|---|---|
| MailParseException do địa chỉ sai cú pháp | PREPARE | STOP |
| MailPreparationException do template thiếu biến | PREPARE | STOP |
| MailAuthenticationException với credential sai | AUTH | STOP + ALERT |
| ConnectException trước SMTP session | CONNECT | RETRY có giới hạn |
| SMTP 421 | CONNECT hoặc command bị từ chối rõ ràng | RETRY |
| SMTP 451 tại RCPT TO | ENVELOPE | RETRY recipient tương ứng |
| SMTP 550 với user unknown | ENVELOPE | STOP recipient tương ứng |
| SMTP 552 vì message quá lớn | DATA hoặc chặng policy | STOP, giảm kích thước |
| SocketTimeoutException khi chờ final DATA reply | WAIT_FINAL_REPLY | RECONCILE |
| SMTP acceptance được xác nhận, DB update lỗi | AFTER_ACK | SUBMITTED về mặt gửi; khôi phục trạng thái record |
| UnknownHostException do host cấu hình sai | CONNECT | STOP/ALERT |
| SSLHandshakeException do truststore sai | TLS | STOP/ALERT |

Ma trận chỉ là định hướng. Nếu có thông tin bổ sung cho thấy provider thực sự gặp lỗi tạm thời hoặc permanent, policy nên sử dụng thông tin đáng tin cậy đó.

## 15. Chuẩn hóa bằng chứng lỗi trước khi quyết định

Thay vì để mọi nơi tự bắt exception rồi tự quyết định, có thể đưa lỗi vào một cấu trúc chung.

Ví dụ:

~~~java
public enum SendPhase {
    PREPARE,
    CONNECT,
    TLS,
    AUTH,
    ENVELOPE,
    DATA,
    WAIT_FINAL_REPLY,
    AFTER_ACCEPTANCE,
    UNKNOWN
}

public enum RetryAction {
    RETRY,
    STOP,
    RECONCILE,
    SUBMITTED
}

public record FailureEvidence(
        SendPhase phase,
        Integer definitiveSmtpReplyCode,
        boolean acceptanceConfirmed,
        boolean acceptanceMayHaveHappened
) {
}

public record RetryDecision(
        RetryAction action,
        String reason
) {
}
~~~

Trong đó:

- **phase:** pha xử lý đã được quan sát hoặc suy ra bằng chứng đáng tin cậy.
- **definitiveSmtpReplyCode:** phản hồi SMTP rõ ràng của thao tác liên quan, không phải mã được đoán từ văn bản exception.
- **acceptanceConfirmed:** đã nhận phản hồi chấp nhận submission.
- **acceptanceMayHaveHappened:** thư có thể đã được chấp nhận nhưng chưa có xác nhận chắc chắn.
- **action:** hành động mà hệ thống sẽ thực hiện.
- **reason:** mã/lý do ngắn để log và metric, không chứa dữ liệu nhạy cảm.

Các giá trị này không phải trường mặc định của Spring Mail. **FailureEvidence** là model do ứng dụng thiết kế, phải được điền từ thông tin mà mail transport/provider thật sự cung cấp. Nếu không có thông tin, giữ **UNKNOWN**; không điền một mã SMTP giả để làm policy trông chắc chắn hơn.

## 16. Ví dụ Java: bộ phân loại lỗi có ngữ cảnh

Một implementation cơ bản:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;

public final class MailRetryClassifier {

    public RetryDecision classify(
            Throwable failure,
            FailureEvidence evidence
    ) {
        if (evidence.acceptanceConfirmed()) {
            return new RetryDecision(
                    RetryAction.SUBMITTED,
                    "SMTP_ACCEPTANCE_CONFIRMED"
            );
        }

        Integer reply = evidence.definitiveSmtpReplyCode();
        if (reply != null) {
            if (reply >= 400 && reply <= 499) {
                return new RetryDecision(
                        RetryAction.RETRY,
                        "SMTP_TRANSIENT_REJECTION"
                );
            }
            if (reply >= 500 && reply <= 599) {
                return new RetryDecision(
                        RetryAction.STOP,
                        "SMTP_PERMANENT_REJECTION"
                );
            }
        }

        if (evidence.acceptanceMayHaveHappened()
                || evidence.phase() == SendPhase.WAIT_FINAL_REPLY
                || evidence.phase() == SendPhase.AFTER_ACCEPTANCE) {
            return new RetryDecision(
                    RetryAction.RECONCILE,
                    "SUBMISSION_OUTCOME_UNKNOWN"
            );
        }

        if (hasCause(failure, MailAuthenticationException.class)) {
            return new RetryDecision(
                    RetryAction.STOP,
                    "MAIL_AUTHENTICATION_FAILED"
            );
        }

        if (hasCause(failure, MailParseException.class)
                || hasCause(failure, MailPreparationException.class)) {
            return new RetryDecision(
                    RetryAction.STOP,
                    "MAIL_PREPARATION_FAILED"
            );
        }

        if (evidence.phase() == SendPhase.CONNECT
                && (hasCause(failure, ConnectException.class)
                    || hasCause(failure, SocketTimeoutException.class))) {
            return new RetryDecision(
                    RetryAction.RETRY,
                    "SMTP_CONNECT_TRANSIENT"
            );
        }

        return new RetryDecision(
                RetryAction.RECONCILE,
                "INSUFFICIENT_FAILURE_EVIDENCE"
        );
    }

    private boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType
    ) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<>()
        );

        Throwable current = failure;
        while (current != null && seen.add(current)) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

### Cách hiểu ví dụ

Implementation trên diễn giải **bằng chứng acceptance** trước, sau đó mới đọc SMTP reply, nhận diện kết quả chưa rõ và cuối cùng xét exception type. Bởi vậy, dù có lỗi cập nhật dữ liệu sau khi SMTP acceptance được xác nhận, policy không tự phát lại email.

**Đây là ví dụ minh họa một lõi quyết định, chưa phải một bộ classifier production hoàn chỉnh.** Cần bổ sung:

- Xác thực bằng chứng SMTP reply là phản hồi của bước nào, đặc biệt khi có nhiều RCPT TO.
- Phân tích chuỗi **MessagingException.getNextException()** ngoài chuỗi getCause.
- Đọc lỗi từng message từ MailSendException và từng recipient từ SendFailedException khi cần.
- Phân biệt lỗi cấu hình TLS, sai hostname, thiếu file, thiếu template, lỗi provider API.
- Xử lý 2xx, 3xx và mã không hợp lệ theo pha thực tế, không mặc định đó là bằng chứng submission.
- Xử lý lỗi kết nối khi không biết pha bằng trạng thái chưa rõ thay vì retry mù.

Trong Spring, mail exception thường được ném sau khi API gửi có kết quả hoặc thất bại. Để điền **FailureEvidence** chính xác, có thể cần adapter ở tầng transport, event provider, SMTP diagnostics hoặc cơ chế lưu trạng thái chặng gửi. Không nên tự gán phase bằng cách đoán từ tên exception.

## 17. Thận trọng với thứ tự ưu tiên của các quy tắc

Một rule engine dễ mắc lỗi khi điều kiện được xét sai thứ tự.

Ví dụ thứ tự sai:

~~~java
if (hasCause(ex, SocketTimeoutException.class)) {
    return RetryAction.RETRY;
}

if (acceptanceMayHaveHappened) {
    return RetryAction.RECONCILE;
}
~~~

Nếu timeout xuất hiện khi chờ phản hồi sau DATA, nhánh đầu tiên sẽ retry ngay và có thể gửi trùng.

Thứ tự nên dựa trên bằng chứng mạnh nhất:

1. Đã xác nhận SMTP chấp nhận hay chưa?
2. Có phản hồi từ chối 4xx/5xx rõ ràng của lần gửi tương ứng không?
3. Có khả năng thư đã được chấp nhận nhưng mất phản hồi không?
4. Nếu chắc chắn chưa gửi, exception và pha có cho thấy lỗi tạm thời hay vĩnh viễn không?
5. Nếu vẫn thiếu bằng chứng, đưa vào trạng thái cần đối soát/điều tra.

Không nhất thiết mọi hệ thống phải dùng cùng bộ enum hay cùng thứ tự code, nhưng policy phải bảo đảm **không có một rule retry quá rộng lấn át bằng chứng cho thấy email có thể đã được chấp nhận**.

## 18. Khi nào nên chỉ retry một recipient?

Nếu một notification chứa nhiều địa chỉ, exception hoặc SMTP server có thể báo những kết quả khác nhau.

Ví dụ:

~~~text
Recipient A: 250 accepted
Recipient B: 450 temporary failure
Recipient C: 550 permanent rejection
~~~

Ở pha RCPT TO, tập recipient được chấp nhận và bị từ chối còn phụ thuộc vào cách client/server tiếp tục giao dịch. Không thể chỉ nhìn ba mã rồi suy ra message đã được truyền DATA cho A và được nhận cuối cùng.

Một mô hình an toàn hơn với email giao dịch:

~~~text
Business event
    |
    +--> Notification A -> recipient A -> trạng thái riêng
    +--> Notification B -> recipient B -> trạng thái riêng
    +--> Notification C -> recipient C -> trạng thái riêng
~~~

Mỗi notification có:

- Recipient riêng.
- Event ID hoặc notification key riêng.
- Attempt riêng.
- Retry status riêng.
- Kết quả gửi và đối soát riêng.

Với thông điệp có nhiều người nhận, cần chính sách xử lý partial success và tách được kết quả từng recipient nếu transport hỗ trợ. Không tự động đổi trạng thái của tất cả recipient bằng trạng thái của một người.

## 19. Chính sách retry không được tách rời idempotency

Ngay cả khi classifier quyết định đúng rằng một lỗi có thể retry, hệ thống vẫn cần tránh xử lý lặp sự kiện nghiệp vụ.

Ví dụ webhook thanh toán được gửi lại hai lần:

~~~text
PaymentSucceeded event E1
         |
         +--> HTTP delivery #1
         |
         +--> HTTP delivery #2
~~~

Nếu mỗi HTTP delivery tạo một notification email mới, người mua có thể nhận hai biên nhận dù không có lỗi SMTP.

Vì thế nên có một notification identity ổn định:

~~~text
notification key =
  businessEventId + notificationType + recipientId
~~~

Hoặc nếu hệ thống có event version:

~~~text
aggregateId + transitionVersion + notificationType + recipientId
~~~

Thiết lập unique constraint trong database giúp ngăn nhiều request đồng thời tạo bản ghi notification trùng nhau. Chỉ kiểm tra tồn tại bằng một SELECT rồi INSERT mà không có constraint sẽ có race condition.

Nhưng idempotency key ở database **không bảo đảm SMTP gửi đúng một lần**:

1. Worker gửi message và SMTP đã nhận.
2. Worker dừng trước khi đánh dấu SUBMITTED.
3. Lease hết hạn, worker khác xử lý lại record.
4. Email có thể được gửi lần hai.

Do đó, **idempotent event handling** và **idempotent email delivery** là hai vấn đề riêng. Nhiều SMTP server không cung cấp một API deduplication end-to-end.

## 20. Message-ID không thay thế idempotency key

Header **Message-ID** hỗ trợ nhận diện một email trong các hệ thống mail. Tuy nhiên, không có cam kết chung rằng gửi lại một message với cùng Message-ID sẽ khiến mọi SMTP server hoặc mailbox tự bỏ qua bản trùng.

Vì vậy:

- Có thể gắn correlation ID hoặc Message-ID ổn định để hỗ trợ truy vết theo chính sách.
- Không lấy Message-ID làm bằng chứng rằng retry sẽ không gửi trùng.
- Khi provider hỗ trợ idempotency key qua API, cần đọc rõ phạm vi và thời hạn hiệu lực.
- Với SMTP thuần, cần xem việc gửi trùng là rủi ro phải giảm và theo dõi, không phải điều có thể loại bỏ hoàn toàn chỉ bằng database transaction.

Trong một tình huống **UNKNOWN**, nếu không thể đối soát qua provider, quyết định gửi lại hay chờ xử lý thủ công là trade-off giữa nguy cơ **mất thông báo** và nguy cơ **gửi trùng**. Quyết định này nên được xác lập theo loại email.

## 21. Retry với exponential backoff và jitter

Khi đã xác định lỗi **retryable**, không nên gửi lại ngay liên tục. Một policy thường gồm:

- **Initial delay:** thời gian chờ trước lần retry đầu tiên.
- **Backoff multiplier:** hệ số tăng thời gian chờ giữa các lần thử.
- **Maximum delay:** giới hạn thời gian chờ mỗi lần.
- **Jitter:** độ lệch ngẫu nhiên để nhiều worker không cùng thử lại đúng một thời điểm.
- **Maximum attempts:** số lần thử tối đa.
- **Maximum age:** thời gian tối đa một notification được phép chờ, nếu nghiệp vụ có hạn xử lý.

Một công thức minh họa:

~~~text
baseDelay(attempt) =
    min(maxDelay, initialDelay * 2^(attempt - 1))

actualDelay = baseDelay + jitter
~~~

Giả sử initialDelay = 30 giây và maxDelay = 30 phút:

| Lần retry | Thời gian cơ sở trước jitter |
|---:|---:|
| 1 | 30 giây |
| 2 | 60 giây |
| 3 | 120 giây |
| 4 | 240 giây |
| 5 | 480 giây |
| 6 | 960 giây |
| 7 | 1.800 giây, đã chạm trần |

Đây là một chính sách ví dụ, không phải giá trị mặc định của Spring Mail. Cần điều chỉnh theo quota SMTP, loại email và SLA.

### Hàm tính delay bằng Java

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelayPolicy {

    private static final long INITIAL_SECONDS = 30L;
    private static final long MAX_SECONDS = 1_800L;

    public Duration delayForRetry(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                    "retryNumber phải lớn hơn hoặc bằng 1"
            );
        }

        long seconds = INITIAL_SECONDS;
        for (int i = 1; i < retryNumber; i++) {
            seconds = Math.min(MAX_SECONDS, seconds * 2);
        }

        long jitter = ThreadLocalRandom.current()
                .nextLong(0, Math.max(1, seconds / 4) + 1);

        return Duration.ofSeconds(seconds + jitter);
    }
}
~~~

Đây là ví dụ tính delay có giới hạn. Với hệ thống thật, nên tránh nhân số có nguy cơ overflow nếu mở rộng công thức, dùng clock thống nhất và lưu **nextAttemptAt** để retry bền vững qua restart.

Nếu SMTP server trả một thời gian thử lại được chuẩn hóa và đáng tin cậy, có thể dùng thông tin đó để điều chỉnh lịch retry. Không giả định mọi SMTP response đều chứa trường **Retry-After** giống HTTP.

## 22. Không lặp lại nguyên phương thức nghiệp vụ để retry email

Giả sử một endpoint thanh toán vừa cập nhật dữ liệu vừa gửi email:

~~~java
public void completePayment(PaymentRequest request) {
    paymentService.capture(request);
    mailService.sendReceipt(request);
}
~~~

Nếu gửi mail thất bại, **không nên retry toàn bộ completePayment** chỉ để gửi lại biên nhận. Điều đó có thể dẫn tới xử lý thanh toán lặp nếu tầng nghiệp vụ không có idempotency phù hợp.

Thay vào đó:

1. Xử lý sự kiện thanh toán idempotent.
2. Tạo một notification/outbox record trong transaction có liên quan.
3. Worker lấy record đó.
4. Worker chỉ retry **bước gửi notification** sau khi classifier đánh giá lại lỗi.

~~~text
Payment transaction
    |
    +--> Ghi payment state
    |
    +--> Ghi notification outbox
    |
   COMMIT
    |
    v
Outbox worker
    |
    v
Render email + JavaMailSender
    |
    +--> SUBMITTED
    +--> RETRY_WAIT
    +--> FAILED
    +--> UNKNOWN
~~~

Nhờ vậy, lỗi SMTP không làm endpoint lặp lại những hành động nghiệp vụ có hậu quả tài chính hoặc trạng thái.

### Spring Retry có tự giải quyết vấn đề này không?

Một công cụ retry ở mức method có thể giúp thực hiện lại một operation tạm thời thất bại. Nhưng chỉ bọc **mailSender.send(...)** trong vòng retry:

- Không tự lưu trạng thái bền vững khi process restart.
- Không tự hiểu giai đoạn SMTP DATA đã được chấp nhận hay chưa.
- Không tự giải quyết partial recipients.
- Không tự chống trùng email ở phía mailbox.
- Có thể giữ request thread quá lâu nếu sleep/backoff trong lời gọi đồng bộ.

Với notification quan trọng, thường nên để worker/outbox quản lý lịch retry bền vững và dùng classifier làm quyết định. Một thư viện retry chỉ là công cụ thực hiện chính sách, không thay thế thiết kế idempotency.

## 23. Lưu kết quả phân loại vào notification record

Một record thông báo có thể có các trường:

| Trường | Mục đích |
|---|---|
| **notification_id** | Định danh notification |
| **event_id** | Sự kiện nghiệp vụ nguồn |
| **recipient_ref** | Tham chiếu người nhận |
| **attempt_count** | Số lần đã thử gửi |
| **status** | PENDING, RETRY_WAIT, SUBMITTED, FAILED, UNKNOWN |
| **last_failure_code** | Mã lỗi chuẩn hóa, ví dụ SMTP_TRANSIENT_REJECTION |
| **last_smtp_reply** | Mã SMTP nếu xác định và được phép lưu |
| **last_send_phase** | Pha gửi nếu biết |
| **next_attempt_at** | Thời điểm retry tiếp theo |
| **provider_message_id** | ID provider nếu có |
| **updated_at** | Thời điểm thay đổi |

### State machine

~~~text
       PENDING
          |
          v
       SENDING
          |
          +------ accepted ----------> SUBMITTED
          |
          +------ transient ---------> RETRY_WAIT
          |                               |
          |                               v
          |                            SENDING
          |
          +------ permanent ---------> FAILED
          |
          +------ ambiguous ---------> UNKNOWN
                                          |
                             +------------+------------+
                             |                         |
                             v                         v
                        SUBMITTED                 MANUAL_REVIEW
                       (đối soát)                hoặc retry có
                                                 kiểm soát
~~~

Không tự động biến UNKNOWN thành RETRY_WAIT chỉ vì đã đến thời gian polling tiếp theo. Nếu đã chọn cơ chế đối soát, cần có worker hoặc quy trình riêng để giải quyết trạng thái không chắc chắn.

### Cập nhật trạng thái với quyền sở hữu

Trong hệ thống nhiều worker, nên update có điều kiện theo claim token:

~~~sql
UPDATE notification_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :nextAttemptAt,
    last_failure_code = :reasonCode,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :notificationId
  AND status = 'SENDING'
  AND claim_token = :claimToken;
~~~

Nếu update tác động 0 dòng, worker có thể đã mất quyền xử lý. Không tiếp tục ghi đè trạng thái bằng một update thiếu điều kiện.

## 24. Cách dùng classifier trong worker

Ví dụ khung điều phối:

~~~java
public void process(ClaimedNotification notification) {
    try {
        RenderedEmail rendered = renderer.render(notification);
        MimeMessage message = buildMimeMessage(
                notification.recipient(),
                rendered
        );

        mailSender.send(message);

        resultService.markSubmitted(
                notification.id(),
                notification.claimToken()
        );
    } catch (MailException exception) {
        FailureEvidence evidence =
                failureEvidenceExtractor.from(
                        notification,
                        exception
                );

        RetryDecision decision = classifier.classify(
                exception,
                evidence
        );

        resultService.apply(
                notification.id(),
                notification.claimToken(),
                decision
        );
    }
}
~~~

**failureEvidenceExtractor**, **buildMimeMessage**, **resultService.apply** và các kiểu nghiệp vụ là thành phần minh họa cần triển khai. Để chương trình hoàn chỉnh, phải xử lý cả MessagingException khi dựng MIME và những lỗi dữ liệu/rendering phát sinh ngoài MailException.

Ví dụ trên cho thấy nơi classifier có thể được gọi, không phải triển khai production copy-paste:

- Khi dùng **MailSendException**, extractor phải xử lý lỗi từng message.
- Khi không có mã SMTP/pha đáng tin cậy, extractor phải ghi nhận thiếu bằng chứng.
- Với lỗi đã biết là sau acceptance, không được dùng retry chung.
- Khi ghi trạng thái thất bại, cần một transaction database ngắn riêng với việc gửi SMTP.
- Nếu resultService không lưu được trạng thái sau send, cần cơ chế khôi phục không gửi lại mù quáng.

Trong thực tế, có thể tách pipeline thành các bước **prepare -> submit -> finalize** để phân biệt exception chuẩn bị với exception vận chuyển, tránh bắt cùng một exception cho mọi pha.

## 25. Nên tách lỗi prepare và lỗi transport trong code

Một cách giúp classifier có nhiều bằng chứng hơn là có ranh giới rõ:

~~~java
RenderedEmail content;
MimeMessage message;

try {
    content = renderer.render(notification);
    message = mimeFactory.create(notification, content);
} catch (TemplateException | InvalidNotificationException ex) {
    resultService.markFailed(notification.id(), "INVALID_CONTENT");
    return;
} catch (MessagingException ex) {
    resultService.markFailed(notification.id(), "MIME_PREPARATION_ERROR");
    return;
}

try {
    mailSender.send(message);
    resultService.markSubmitted(notification.id());
} catch (MailException ex) {
    // Thu thập phản hồi và pha đã biết, sau đó phân loại.
    classifyAndRecord(notification, ex);
}
~~~

Các class **TemplateException**, **InvalidNotificationException**, **mimeFactory** và phương thức resultService là ví dụ ứng dụng tự định nghĩa. Khi triển khai production, cần dùng claim token, transaction result và xử lý phù hợp cho nguồn attachment có lỗi tạm thời.

Tách try/catch theo pha giúp tránh một câu catch chung gộp cả lỗi template, lỗi database và lỗi SMTP thành “mail send error”.

Tuy nhiên, **send(message)** có thể tự làm một số công việc serialize/read MIME khi truyền dữ liệu. Vì vậy lỗi đọc attachment hoặc encode content vẫn có thể xuất hiện trong pha transport. Ranh giới code giúp dễ chẩn đoán hơn nhưng không loại bỏ việc phải xem nguyên nhân thực tế.

## 26. Một số kịch bản phân loại thực tế

### Kịch bản A: Recipient sai cú pháp

~~~text
Input: user@@example..com
Exception: lỗi parse địa chỉ
SMTP DATA: chưa gửi
~~~

Hành động: **STOP**, yêu cầu sửa địa chỉ. Retry cùng chuỗi sẽ thất bại lặp lại.

### Kịch bản B: SMTP server tạm thời quá tải

~~~text
SMTP: 421 Service not available
Server đã từ chối rõ ràng ở chặng tương ứng
~~~

Hành động: **RETRY** có backoff và jitter. Theo dõi số lần retry để tránh gây thêm áp lực lên server.

### Kịch bản C: Mật khẩu SMTP sai

~~~text
Exception: MailAuthenticationException
Credential/config không thay đổi
~~~

Hành động: **STOP hoặc tạm dừng queue và ALERT**. Sau khi sửa credential, có thể replay có kiểm soát theo chính sách.

### Kịch bản D: Mailbox không tồn tại

~~~text
SMTP: 550 5.1.1 User unknown
Recipient: customer@example.invalid
~~~

Hành động: **STOP** cho recipient đó. Không retry liên tục. Cần xác thực và sửa recipient.

### Kịch bản E: Timeout sau DATA

~~~text
Ứng dụng đã gửi nội dung MIME
Chưa nhận được phản hồi cuối
SocketTimeoutException
~~~

Hành động: **RECONCILE**. Nếu provider có tracking API, tra cứu kết quả bằng correlation ID. Nếu không có khả năng đối soát, chọn chính sách thủ công hoặc retry có chấp nhận nguy cơ trùng, tùy mức độ quan trọng của thông báo.

### Kịch bản F: Ba message có hai message đã được chấp nhận

~~~text
Batch: A, B, C
A: success
B: failed due to invalid recipient
C: connection error
~~~

Hành động: **không retry cả batch**. Ghi nhận kết quả từng message; B dừng, C được phân loại theo pha và phản hồi, A không gửi lại.

### Kịch bản G: SMTP đã chấp nhận nhưng ghi database kết quả lỗi

~~~text
JavaMailSender.send(...) returned normally
resultRepository.markSubmitted(...) failed
~~~

Hành động: **không coi là SMTP send failure**. Khôi phục trạng thái bằng cơ chế retry cập nhật DB/đối soát; không tái gửi chỉ vì database cập nhật kết quả bị lỗi.

## 27. Kiểm thử bộ phân loại exception

Một classifier nên được kiểm tra bằng dữ liệu có chủ ý, không cần SMTP thật cho từng nhánh.

### Các case tối thiểu

| Case | Bằng chứng | Quyết định kỳ vọng |
|---|---|---|
| Auth failed | MailAuthenticationException | STOP |
| Parse failed | MailParseException | STOP |
| Connect refused | Pha CONNECT, ConnectException | RETRY |
| SMTP 451 | Phản hồi từ chối rõ ràng | RETRY |
| SMTP 550 | Phản hồi từ chối rõ ràng | STOP |
| Lost final reply | Pha WAIT_FINAL_REPLY | RECONCILE |
| Confirmed accepted | acceptanceConfirmed = true | SUBMITTED |
| Unknown cause and phase | Không đủ bằng chứng | RECONCILE |
| Timeout after DATA | MayHaveAccepted = true | RECONCILE |
| Batch partial success | Kết quả từng message khác nhau | Xử lý từng message |

Ví dụ JUnit 5 với classifier ở trên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import org.junit.jupiter.api.Test;

class MailRetryClassifierTest {

    private final MailRetryClassifier classifier =
            new MailRetryClassifier();

    @Test
    void retriesConnectionFailureBeforeSubmission() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.CONNECT,
                null,
                false,
                false
        );

        RetryDecision result = classifier.classify(
                new ConnectException("Connection refused"),
                evidence
        );

        assertEquals(RetryAction.RETRY, result.action());
    }

    @Test
    void doesNotBlindlyRetryLostFinalReply() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.WAIT_FINAL_REPLY,
                null,
                false,
                true
        );

        RetryDecision result = classifier.classify(
                new SocketTimeoutException("Read timed out"),
                evidence
        );

        assertEquals(RetryAction.RECONCILE, result.action());
    }

    @Test
    void stopsOnPermanentSmtpRejection() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.ENVELOPE,
                550,
                false,
                false
        );

        RetryDecision result = classifier.classify(
                new RuntimeException("recipient rejected"),
                evidence
        );

        assertEquals(RetryAction.STOP, result.action());
    }
}
~~~

Các test trên kiểm tra rule của classifier chứ không xác nhận rằng thư viện SMTP thực tế sẽ luôn sinh chính xác những bằng chứng này. Cần có integration test với server SMTP thử nghiệm để kiểm tra adapter thu thập mã phản hồi, chuỗi nguyên nhân và hành vi từng message.

### Test lỗi mạng có kết quả không rõ

Một SMTP test server có thể được cấu hình nhận DATA rồi cố tình cắt kết nối trước khi trả phản hồi cuối. Tình huống này giúp xác nhận rằng pipeline không đánh dấu FAILED chắc chắn và không tự retry ngay.

Không thử tạo lỗi bằng cách gửi email thật cho khách hàng production.

## 28. Quan sát và cảnh báo trong vận hành

Khi phân loại lỗi, nên ghi metric theo **error category** và **action**, không chỉ tổng số lần exception.

Ví dụ:

| Metric | Mục đích |
|---|---|
| mail_attempt_total | Số lần thử gửi |
| mail_submission_success_total | Số lần submission được xác nhận |
| mail_retry_scheduled_total | Số lần được phân loại retryable |
| mail_permanent_failure_total | Số lỗi dừng vĩnh viễn |
| mail_unknown_outcome_total | Số trường hợp chưa rõ kết quả |
| mail_auth_failure_total | Lỗi xác thực/cấu hình |
| mail_smtp_reply_total | Phân bố SMTP reply code |
| mail_retry_queue_age | Thời gian tồn đọng của notification retry |
| mail_attempt_duration | Độ trễ gửi ở tầng transport |

Một log sự kiện có thể chứa:

~~~text
notificationId=... eventId=...
phase=CONNECT
errorCategory=TRANSIENT
decision=RETRY
attempt=3
smtpCode=421
nextAttemptAt=...
~~~

Thông tin trên chỉ là các trường minh họa. Không nên ghi credential, body MIME, attachment, OTP, token hoặc địa chỉ đầy đủ vào log không được bảo vệ.

### Cảnh báo gợi ý

- MailAuthenticationException tăng đột biến: nghi vấn credential hoặc chính sách provider thay đổi.
- SMTP 4xx tăng: có thể provider quá tải hoặc rate limit.
- SMTP 5xx tăng: có thể dữ liệu recipient hoặc chính sách nội dung có vấn đề.
- UNKNOWN tăng: có thể network timeout ở pha cuối hoặc lỗi adapter.
- RETRY_WAIT tồn đọng quá lâu: worker hoặc SMTP bị gián đoạn.
- FAILED tăng: cần sửa dữ liệu/template/config, không chỉ tăng số lần retry.

## 29. Bảo mật dữ liệu khi phân tích exception

Một exception mail có thể chứa:

- Địa chỉ email người gửi hoặc người nhận.
- SMTP response với nội dung do server ngoài cung cấp.
- Hostname, chi tiết TLS hoặc authentication.
- Đường dẫn attachment.
- Dữ liệu MIME trong một số stack trace hoặc log debug.

Vì vậy:

1. Ghi **error code chuẩn hóa** như SMTP_TRANSIENT_REJECTION thay vì copy nguyên response vào log công khai.
2. Bảo vệ log và giới hạn quyền truy cập.
3. Không log toàn bộ MimeMessage chỉ để chẩn đoán retry.
4. Không dùng exception message để xây nội dung gửi trực tiếp cho khách hàng.
5. Không đưa token hoặc link xác thực vào thông báo lỗi vận hành.
6. Giới hạn thời gian lưu failure details và lịch sử attempt.
7. Nếu cần lưu SMTP reply raw để điều tra, áp dụng kiểm soát dữ liệu phù hợp.

Việc phân loại lỗi chính xác không đòi hỏi thu thập mọi byte của email. Thường chỉ cần phase, normalized reason, SMTP code và correlation ID.

## 30. Bảng quyết định tổng hợp

| Bằng chứng đáng tin cậy | Category | Action | Điều kiện bổ sung |
|---|---|---|---|
| Template/địa chỉ sai cú pháp | Permanent | STOP | Cập nhật input/template rồi replay nếu cần |
| Credential bị từ chối | Permanent/configuration | STOP + ALERT | Chỉ replay khi credential/quyền được sửa |
| TLS certificate không hợp lệ | Configuration/security | STOP + ALERT | Không bỏ qua xác thực TLS |
| TCP connect timeout trước submission | Transient | RETRY | Backoff, max attempts |
| SMTP từ chối rõ bằng 4xx | Transient | RETRY | Tôn trọng delay/quota |
| SMTP từ chối rõ bằng 5xx | Permanent | STOP | Xem recipient, size, content và policy |
| Attachment local đã mất | Preparation | STOP | Sửa vòng đời file |
| Remote attachment timeout | Transient preparation | RETRY nguồn | Đảm bảo dữ liệu vẫn đúng snapshot |
| Đã truyền DATA, mất final reply | Ambiguous | RECONCILE | Không retry mù |
| Acceptance đã xác nhận, ghi DB lỗi | Post-submission | SUBMITTED | Khôi phục trạng thái DB |
| Batch có thành công một phần | Mixed outcomes | Per-message action | Không gửi lại cả batch |
| Không biết pha/mã SMTP | Unknown | RECONCILE | Bổ sung bằng chứng, không tự đoán |

Chính sách cuối cần phản ánh yêu cầu thực tế. Email OTP có thời hạn ngắn có thể hết giá trị sau khi retry chậm; email hóa đơn quan trọng có thể cần điều tra kỹ trước khi bỏ qua; email marketing có thể có quota và chính sách suppression riêng. Một bảng classification dùng chung nên cho phép **cấu hình theo notification type** mà không phá vỡ các nguyên tắc an toàn về duplicate và trạng thái chưa rõ.

## 31. Ghi nhớ

**Phân loại exception cho retry trong Spring Framework Mail không phải phép ánh xạ một class exception thành một số lần thử lại.** MailAuthenticationException, MailParseException và MailPreparationException thường dẫn tới kiểm tra dữ liệu/cấu hình; MailSendException cần xem lỗi lồng nhau và có thể chứa kết quả nhiều message. Jakarta Mail, lỗi mạng và SMTP reply code cung cấp thêm bằng chứng về nguyên nhân.

Hãy luôn hỏi: **Lỗi xảy ra ở pha nào? Server có phản hồi từ chối 4xx/5xx rõ ràng không? Thư có thể đã được chấp nhận chưa? Có recipient hoặc message nào đã thành công không?** Nếu lỗi tạm thời và chắc chắn chưa accepted, retry với backoff, jitter, giới hạn attempts và trạng thái bền vững. Nếu lỗi vĩnh viễn, dừng và sửa nguyên nhân. Nếu kết quả không rõ, đối soát trước khi gửi lại.

Classifier cần đi cùng **event identity, notification-level idempotency, xử lý partial success, outbox/queue, observability và chính sách UNKNOWN**. Những cơ chế này giảm nguy cơ mất thông báo hoặc gửi trùng, nhưng không biến SMTP thành exactly-once delivery.

**Quy tắc quan trọng nhất: chỉ retry khi có bằng chứng đủ mạnh để tin rằng retry là hợp lý; không biến một exception chưa rõ thành một lần gửi lại vô điều kiện.**


