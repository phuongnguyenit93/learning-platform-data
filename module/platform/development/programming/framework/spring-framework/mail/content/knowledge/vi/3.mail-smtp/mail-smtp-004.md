# Mã phản hồi 2xx, 4xx và 5xx trong SMTP

Khi ứng dụng dùng **Spring Framework Mail** để gửi email, nó thường kết nối tới một máy chủ **SMTP (Simple Mail Transfer Protocol)**. Trong cuộc hội thoại này, ứng dụng gửi các lệnh như `EHLO`, `MAIL FROM`, `RCPT TO` và `DATA`; máy chủ trả về **mã phản hồi gồm ba chữ số** để thông báo lệnh vừa được xử lý ra sao.

Ba nhóm mã cần phân biệt khi triển khai chức năng gửi mail là:

| Nhóm mã | Ý nghĩa trong SMTP | Hướng xử lý thường gặp |
| --- | --- | --- |
| **2xx** | Positive completion: yêu cầu ở **bước hiện tại** được xử lý thành công | Tiếp tục bước SMTP tiếp theo hoặc ghi nhận thư đã được máy chủ chấp nhận sau khi kết thúc `DATA` |
| **4xx** | Transient negative completion: máy chủ **tạm thời không hoàn tất** yêu cầu | Xem xét thử lại sau một khoảng chờ, có giới hạn và theo đúng trạng thái của giao dịch |
| **5xx** | Permanent negative completion: yêu cầu **không được chấp nhận ở điều kiện hiện tại** | Tìm nguyên nhân, sửa địa chỉ/cấu hình/nội dung/chính sách trước khi gửi lại |

Đây là **quy ước của giao thức SMTP**, không phải mã trạng thái HTTP. Đặc biệt, `4xx` của SMTP biểu thị lỗi mang tính tạm thời; `5xx` thường đòi hỏi thay đổi điều kiện trước khi thử lại. Không nên áp dụng cách hiểu “4xx = lỗi của client, 5xx = lỗi của server” trong HTTP cho SMTP.

> Còn một nhóm rất quan trọng: **3xx**, chẳng hạn `354 Start mail input`. Đây là phản hồi *positive intermediate*, nghĩa là máy chủ đã sẵn sàng nhận dữ liệu tiếp theo. Bài này tập trung vào 2xx, 4xx và 5xx nhưng sẽ dùng 354 để hiểu đầy đủ luồng gửi.

## 1. Phản hồi SMTP có cấu trúc như thế nào?

Một dòng phản hồi thường có dạng:

~~~text
<mã-ba-chữ-số><dấu-phân-cách><nội-dung-diễn-giải>

250 2.0.0 Message accepted for delivery
451 4.3.0 Temporary processing error
550 5.1.1 User unknown
~~~

Trong đó:

- **Mã ba chữ số** đầu dòng, như `250`, `451` hay `550`, là mã phản hồi SMTP cơ bản.
- **Chuỗi như `2.0.0`, `4.3.0`, `5.1.1`** có thể xuất hiện sau mã chính là *enhanced status code*, cung cấp thông tin chi tiết hơn. Không phải mọi máy chủ hay mọi phản hồi đều kèm mã này.
- **Phần văn bản** do máy chủ cung cấp giúp chẩn đoán, nhưng cách diễn đạt phụ thuộc nhà cung cấp, không ổn định như một API có cấu trúc.

### 1.1. Ý nghĩa của chữ số đầu tiên

| Chữ số đầu | Tên nhóm | Ý nghĩa |
| --- | --- | --- |
| `2` | Positive completion | Lệnh đã hoàn tất thành công ở công đoạn hiện tại |
| `3` | Positive intermediate | Lệnh được chấp nhận bước đầu, máy chủ yêu cầu thêm dữ liệu |
| `4` | Transient negative completion | Lệnh chưa thể hoàn tất vì điều kiện được xem là tạm thời |
| `5` | Permanent negative completion | Lệnh bị từ chối; gửi lại nguyên trạng thường không giải quyết được |

Hai chữ số còn lại giúp xác định loại tình huống cụ thể. Chẳng hạn `250`, `251` đều thuộc nhóm thành công nhưng không có cùng ngữ nghĩa. Không được suy luận mọi mã có cùng chữ số đầu là có thể xử lý hoàn toàn giống nhau.

### 1.2. Phản hồi nhiều dòng

SMTP cho phép máy chủ trả lời nhiều dòng, thường thấy sau `EHLO`:

~~~text
S: 250-smtp.example.net Hello app.example.org
S: 250-PIPELINING
S: 250-SIZE 10485760
S: 250 STARTTLS
~~~

Dấu **gạch nối** ngay sau mã (`250-`) biểu thị còn dòng tiếp theo của cùng phản hồi; dấu **cách** (`250 `) đánh dấu dòng cuối. Client phải đọc hết phản hồi liên quan thay vì xem mỗi dòng là kết quả của một lệnh khác.

## 2. Nhóm 2xx: máy chủ chấp nhận bước xử lý hiện tại

**2xx không có nghĩa email chắc chắn đã tới hộp thư của người nhận.** Mức thành công phụ thuộc lệnh đang được phản hồi:

| Mã | Ý nghĩa thường gặp | Thời điểm có thể gặp |
| --- | --- | --- |
| **220** | Service ready: máy chủ SMTP sẵn sàng | Khi bắt đầu kết nối; cũng dùng cho phản hồi sẵn sàng bắt đầu TLS sau lệnh `STARTTLS` |
| **221** | Service closing transmission channel | Khi kết thúc phiên bằng `QUIT` |
| **235** | Authentication successful | Sau khi xác thực SMTP AUTH thành công, nếu server hỗ trợ extension này |
| **250** | Requested mail action okay, completed | Sau `EHLO`, `MAIL FROM`, `RCPT TO`, hoặc sau khi server chấp nhận toàn bộ nội dung `DATA` |
| **251** | User not local; will forward | Máy chủ chấp nhận việc chuyển tiếp cho một địa chỉ khác; ít gặp hơn |
| **252** | Cannot verify user, but will accept message and attempt delivery | Một phản hồi có thể gặp trong ngữ cảnh `VRFY`; không chứng minh người nhận tồn tại |

### 2.1. Mã `250` ở những công đoạn khác nhau

Đây là mã xuất hiện rất nhiều trong log SMTP, nhưng phải **đọc kèm lệnh ngay trước nó**:

- `250` sau `MAIL FROM`: máy chủ đã chấp nhận **địa chỉ envelope sender** cho giao dịch hiện tại.
- `250` sau `RCPT TO`: máy chủ đã chấp nhận **người nhận envelope** tương ứng ở bước này.
- `250` sau dấu chấm kết thúc dữ liệu của `DATA`: máy chủ đã **nhận trách nhiệm xử lý/chuyển tiếp** thông điệp được gửi trong giao dịch.

Ngay cả trường hợp cuối, thư vẫn có thể bị trì hoãn, trả lại (*bounce*), bị từ chối ở máy chủ phía sau hoặc bị lọc vào thư rác. Để biết các trạng thái đó, thường phải theo dõi phản hồi bất đồng bộ như bounce, DSN (*Delivery Status Notification*) hoặc webhook của nhà cung cấp.

### 2.2. Ví dụ một phiên gửi thành công

Ký hiệu `C` là client (ứng dụng/thư viện mail), `S` là server SMTP:

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.org
S: 250-smtp.example.net
S: 250-PIPELINING
S: 250 SIZE 10485760

C: MAIL FROM:<no-reply@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<reader@example.net>
S: 250 2.1.5 Recipient OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.org
C: To: reader@example.net
C: Subject: Welcome
C:
C: Hello, this is a test message.
C: .
S: 250 2.0.0 Message queued as Q12345

C: QUIT
S: 221 2.0.0 Bye
~~~

Diễn biến cần chú ý:

1. **220:** server sẵn sàng giao tiếp.
2. **250 sau `EHLO`:** server phản hồi lời chào và có thể liệt kê các extension.
3. **250 sau `MAIL FROM` và `RCPT TO`:** envelope sender và recipient được chấp nhận.
4. **354:** server yêu cầu client truyền nội dung email; nó **chưa xác nhận nhận toàn bộ thư**.
5. **250 sau dấu chấm `.`:** server chấp nhận thư để xử lý/chuyển tiếp.
6. **221:** phiên SMTP kết thúc bình thường.

Ví dụ lược bỏ xác thực và TLS để tập trung vào mã phản hồi. Trên hệ thống thật, client có thể phải thực hiện `STARTTLS`, `EHLO` lại sau khi nâng cấp TLS, rồi `AUTH` theo chính sách của nhà cung cấp.

## 3. Nhóm 4xx: lỗi tạm thời, có thể cần thử lại

**4xx** cho biết máy chủ chưa thể thực hiện yêu cầu **ở thời điểm hiện tại**. Thông thường có thể thử lại về sau, nhưng cần đánh giá tình huống và không retry vô hạn.

| Mã | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| **421** | Dịch vụ tạm thời không khả dụng; kênh truyền đang/chuẩn bị đóng | Dừng phiên, tạo kết nối mới sau khoảng chờ |
| **450** | Mailbox tạm thời không khả dụng, ví dụ bị khóa/bận | Giữ yêu cầu và thử lại sau |
| **451** | Lỗi cục bộ khi máy chủ xử lý yêu cầu | Thử lại có giới hạn, ghi nhận nguyên nhân/pha xảy ra lỗi |
| **452** | Hệ thống thiếu tài nguyên/lưu trữ để xử lý | Giảm tải, chờ trước khi thử lại |
| **454** | Xác thực SMTP tạm thời không khả dụng | Kiểm tra trạng thái auth/provider, thử lại khi phù hợp |

Phần mô tả từ server thường giải thích thêm, ví dụ:

~~~text
421 4.7.0 Too many connections, try later
450 4.2.0 Mailbox temporarily unavailable
451 4.7.1 Greylisted, please try again later
452 4.3.1 Insufficient system storage
454 4.7.0 Temporary authentication failure
~~~

Đây là **ví dụ minh họa**; thông điệp và enhanced status code thực tế do từng server quyết định. Không nên xây quy tắc retry chỉ bằng cách tìm những từ như “greylisted” hay “temporary” trong chuỗi mô tả.

### 3.1. Ví dụ: máy chủ tạm từ chối một người nhận

~~~text
C: RCPT TO:<recipient@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

Máy chủ chưa chấp nhận người nhận này trong giao dịch hiện tại. Hệ thống gửi thư cần lưu trạng thái phù hợp rồi thử lại theo chính sách, thay vì đánh dấu “đã gửi thành công”.

### 3.2. Ví dụ: lỗi tạm thời sau khi gửi nội dung

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: Subject: Monthly report
C:
C: Report body...
C: .
S: 451 4.3.0 Temporary local processing error
~~~

Trường hợp trên **không có `250` sau nội dung thư** nên không thể kết luận máy chủ đã chấp nhận thư. Client có thể thử lại sau theo chính sách gửi. Nhưng cần phân biệt một tình huống khác: nếu client bị **mất kết nối trước khi nhận phản hồi cuối**, không thể chắc chắn máy chủ đã nhận hay chưa, vì vậy retry có nguy cơ gửi trùng.

### 3.3. Retry như thế nào?

Một chiến lược hợp lý với 4xx:

1. Lưu yêu cầu gửi và lý do thất bại (mã SMTP, pha xử lý, thời điểm).
2. Đặt lịch thử lại sau khoảng chờ tăng dần, chẳng hạn **exponential backoff** có **jitter** để tránh nhiều worker cùng retry một lúc.
3. Giới hạn số lần thử hoặc tổng thời gian chờ; sau khi vượt ngưỡng, chuyển tác vụ sang trạng thái cần theo dõi/xử lý.
4. Tôn trọng giới hạn tốc độ và hướng dẫn cụ thể của nhà cung cấp.
5. Theo dõi tỷ lệ 4xx tăng đột biến để phát hiện sự cố hệ thống hoặc chính sách gửi.

Thời gian chờ cụ thể nên lấy từ yêu cầu nghiệp vụ và khuyến cáo của nhà cung cấp, không áp một con số cứng cho mọi trường hợp. Đặc biệt, `454` thường liên quan hạ tầng xác thực và có thể cần cảnh báo vận hành song song với retry.

## 4. Nhóm 5xx: yêu cầu bị từ chối ở điều kiện hiện tại

**5xx** nghĩa là máy chủ coi yêu cầu **không thể hoàn tất bằng cách gửi lại y nguyên**. Nhiều nguyên nhân không phải sự cố máy chủ: cú pháp lệnh sai, địa chỉ người nhận không tồn tại, thiếu xác thực, chính sách gửi bị từ chối hoặc loại nội dung không được chấp nhận.

| Mã | Ý nghĩa thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| **500** | Lệnh không hợp lệ về cú pháp hoặc không được nhận diện | Tên lệnh/giao thức client |
| **501** | Cú pháp tham số hoặc đối số của lệnh sai | Cách định dạng địa chỉ/đối số |
| **502** | Lệnh không được triển khai/hỗ trợ | Khả năng tương thích với SMTP server |
| **503** | Thứ tự lệnh không hợp lệ | Trình tự `EHLO`, `MAIL FROM`, `RCPT TO`, `DATA` |
| **504** | Tham số lệnh chưa được hỗ trợ | Extension, cơ chế AUTH hoặc tùy chọn |
| **530** | Cần xác thực trước khi thực hiện thao tác | Cấu hình SMTP AUTH và chính sách relay |
| **535** | Xác thực không thành công | Credentials, tài khoản, phương thức AUTH, chính sách provider |
| **550** | Mailbox không khả dụng, địa chỉ không tồn tại hoặc bị từ chối vì chính sách | Địa chỉ recipient, domain, quyền relay, chặn spam |
| **551** | Người dùng không ở máy chủ này; cần địa chỉ chuyển tiếp được chỉ định | Đường đi/địa chỉ nhận phù hợp |
| **552** | Vượt giới hạn dung lượng/lưu trữ | Kích thước thư, quota mailbox |
| **553** | Tên mailbox không được phép | Định dạng/địa chỉ người gửi hoặc người nhận |
| **554** | Giao dịch không hoàn tất hoặc bị từ chối | Quy tắc lọc/chính sách/server và lý do cụ thể |

Ví dụ thường gặp:

~~~text
535 5.7.8 Authentication credentials invalid
550 5.1.1 Recipient address rejected: User unknown
550 5.7.1 Relay access denied
552 5.2.2 Mailbox full
554 5.7.1 Message rejected by policy
~~~

Mã `550` xuất hiện trong **nhiều loại lỗi khác nhau**. Không thể nhìn mỗi `550` rồi kết luận chắc chắn “email không tồn tại”. Phải kết hợp enhanced status code, câu trả lời của nhà cung cấp, lệnh đang gửi và chính sách tương ứng.

### 4.1. Ví dụ: địa chỉ nhận không tồn tại

~~~text
C: RCPT TO:<typo@example.net>
S: 550 5.1.1 User unknown
~~~

Ứng dụng nên đánh dấu địa chỉ này cần sửa hoặc ngừng thử gửi tới địa chỉ đó. Retry liên tục với cùng địa chỉ không giúp giải quyết lỗi được server khai báo là vĩnh viễn.

### 4.2. Ví dụ: xác thực không thành công

~~~text
C: AUTH ...
S: 535 5.7.8 Authentication credentials invalid
~~~

Đây thường là dấu hiệu phải kiểm tra tên người dùng, thông tin xác thực, tài khoản, phương thức AUTH hoặc thiết lập của nhà cung cấp. Không nên in dữ liệu AUTH hoặc mật khẩu ra log. Cũng không nên tự retry liên tục vì có thể gây khóa tài khoản hoặc vượt giới hạn.

### 4.3. Ví dụ: bị từ chối do chính sách

~~~text
C: RCPT TO:<recipient@external.example>
S: 550 5.7.1 Relay access denied
~~~

Thông điệp này thường gợi ý client đang cố chuyển tiếp mail qua server không cho phép: chưa được xác thực, sử dụng sai SMTP host, tài khoản thiếu quyền, hoặc địa chỉ gửi/domain không được cấp phép. Cần sửa cấu hình hoặc quyền gửi, thay vì tự động lặp lại yêu cầu.

## 5. Enhanced status code: vì sao `550 5.1.1` và `550 5.7.1` khác nhau?

Ngoài mã ba chữ số, server có thể gửi **enhanced status code** theo mẫu:

~~~text
X.Y.Z

550 5.1.1 User unknown
550 5.7.1 Message rejected by policy
451 4.7.1 Temporary policy deferral
~~~

Ý nghĩa ở mức khái quát:

- **X (class):** `2` là thành công, `4` là lỗi tạm thời, `5` là lỗi vĩnh viễn.
- **Y (subject):** nhóm vấn đề, chẳng hạn addressing, mailbox, mail system, network/routing, protocol hoặc security/policy.
- **Z (detail):** tình huống chi tiết trong nhóm đó.

Một số ví dụ dễ phân biệt:

| Phản hồi | Cách hiểu hữu ích |
| --- | --- |
| `550 5.1.1` | Địa chỉ người nhận không hợp lệ/không tồn tại theo phản hồi máy chủ |
| `550 5.7.1` | Từ chối vì chính sách, quyền relay hoặc vấn đề bảo mật |
| `535 5.7.8` | Thông tin xác thực không được chấp nhận |
| `451 4.7.1` | Tạm hoãn theo chính sách; có thể là greylisting hoặc giới hạn tạm thời |
| `452 4.3.1` | Máy chủ đang thiếu tài nguyên/lưu trữ |
| `250 2.0.0` | Bước gửi hiện tại hoàn tất; sau `DATA` thường nghĩa là thư được nhận để xử lý |

**Không phải máy chủ nào cũng phát cùng một chuỗi enhanced status hoặc cách diễn giải.** Để chẩn đoán chính xác, ưu tiên mã tiêu chuẩn và tài liệu provider, đồng thời lưu phản hồi thô có giới hạn và đã loại bỏ dữ liệu nhạy cảm.

## 6. Mã lỗi xuất hiện ở bước nào trong phiên SMTP?

Một mã giống nhau có thể được trả về ở những giai đoạn khác nhau; mỗi giai đoạn dẫn đến cách khắc phục khác nhau.

~~~mermaid
flowchart TD
    A["Kết nối SMTP"] --> B{"Banner"}
    B -->|"220"| C["EHLO / STARTTLS / AUTH"]
    B -->|"421"| X["Tạm dừng và thử kết nối sau"]
    C --> D{"Kết quả chuẩn bị phiên"}
    D -->|"2xx"| E["MAIL FROM"]
    D -->|"4xx"| R["Lên lịch retry phù hợp"]
    D -->|"5xx"| F["Sửa cấu hình / xác thực"]
    E --> G["RCPT TO từng người nhận"]
    G --> H{"Người nhận được chấp nhận?"}
    H -->|"250"| I["DATA"]
    H -->|"4xx"| R
    H -->|"5xx"| J["Sửa địa chỉ / quyền / chính sách"]
    I --> K{"354 rồi gửi nội dung, dấu chấm kết thúc"}
    K -->|"250 sau nội dung"| L["SMTP đã nhận thư để xử lý"]
    K -->|"4xx"| R
    K -->|"5xx"| J
~~~

| Vị trí xảy ra lỗi | Câu hỏi chẩn đoán |
| --- | --- |
| **Kết nối / banner** | Server đang khả dụng? Có quá tải, giới hạn kết nối hay vấn đề mạng không? |
| **`EHLO` / `STARTTLS`** | Server có hỗ trợ extension và chế độ TLS mà client yêu cầu không? |
| **`AUTH`** | Thông tin xác thực đúng? Cơ chế AUTH được hỗ trợ? Quyền gửi hợp lệ? |
| **`MAIL FROM`** | Địa chỉ envelope sender có được server cho phép không? |
| **`RCPT TO`** | Địa chỉ người nhận hợp lệ? Server có cho phép gửi tới domain này? |
| **`DATA` và sau dấu chấm kết thúc** | Kích thước, nội dung, giới hạn tài nguyên hoặc chính sách lọc có khiến thư bị từ chối không? |

### 6.1. Một thư có nhiều người nhận

SMTP có thể gọi `RCPT TO` nhiều lần trong một giao dịch:

~~~text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<bob@example.net>
S: 550 5.1.1 User unknown
C: RCPT TO:<carol@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

Trong ví dụ này, các địa chỉ có **kết quả khác nhau**. Cách thư viện tiếp tục gửi, bỏ qua người nhận lỗi hoặc báo ngoại lệ phụ thuộc cấu hình và quy tắc xử lý của SMTP client/provider. Phần mềm quản lý gửi thư nên theo dõi kết quả **theo từng người nhận** nếu nghiệp vụ cần độ chính xác, tránh đánh dấu cả danh sách “thành công” hoặc “thất bại” khi chỉ một số địa chỉ bị từ chối.

### 6.2. Timeout không đồng nghĩa với 4xx

Nếu client gặp `SocketTimeoutException`, mất kết nối hoặc lỗi TLS trước khi nhận phản hồi, **có thể hoàn toàn không có mã SMTP** để phân loại 2xx/4xx/5xx. Đặc biệt, mất kết nối sau khi đã gửi dấu chấm kết thúc `DATA` tạo tình huống không rõ server đã chấp nhận thư hay chưa. Hệ thống retry cần cân nhắc nguy cơ phát sinh thư trùng và nên gắn ID nghiệp vụ/idempotency key cho tác vụ gửi ở phía ứng dụng.

## 7. Diễn giải mã SMTP trong Spring Framework Mail

Trong Java, Spring cung cấp `JavaMailSender` để gửi thư. Khi sử dụng Spring Boot với `spring-boot-starter-mail`, ứng dụng thường inject interface này vào service; việc kết nối SMTP do implementation và thư viện Jakarta Mail phía dưới thực hiện.

Ví dụ đơn giản:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailSubmissionService {
    private final JavaMailSender sender;

    public MailSubmissionService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        try {
            sender.send(message);
            // Lời gọi gửi trả về bình thường:
            // quá trình nộp thư qua transport đã hoàn tất.
            // Chưa thể khẳng định thư đã đến Inbox.
        } catch (MailException failure) {
            // Lưu thông tin lỗi ở lớp điều phối/job phù hợp.
            // Cần xem nguyên nhân lồng bên dưới để biết mã SMTP,
            // nếu máy chủ thực sự đã trả về mã.
            throw failure;
        }
    }
}
~~~

Đây là ví dụ về **ranh giới API**, không phải một cơ chế retry hoàn chỉnh. Một số ngoại lệ cần biết:

- `MailAuthenticationException`: Spring báo lỗi xác thực mail; nên kiểm tra nguyên nhân gốc và phản hồi SMTP nếu có (ví dụ `454` tạm thời hoặc `535` không chấp nhận credentials).
- `MailSendException`: lỗi trong quá trình gửi; có thể chứa chi tiết thất bại theo thông điệp, thông qua các phương thức như `getFailedMessages()`, cùng ngoại lệ nguồn.
- `MailException`: lớp cha của các ngoại lệ mail phía Spring. Chỉ dựa vào tên lớp ngoại lệ thường **không đủ** để kết luận đây là 4xx hay 5xx.
- Các ngoại lệ từ Jakarta Mail/SMTP provider bên dưới có thể chứa mã phản hồi gốc. Cách lấy mã cụ thể tùy implementation và loại lỗi; cần kiểm tra chuỗi exception liên quan, bao gồm cả các exception lồng và liên kết của Jakarta Mail.

Không nên viết kiểu:

~~~java
// Cách suy luận dễ sai:
// catch (MailSendException e) { retryForever(); }
// catch (MailAuthenticationException e) { neverRetry(); }
~~~

Vì `MailSendException` có thể bao gồm lỗi vĩnh viễn, còn sự cố xác thực đôi khi là tạm thời. Phân loại theo **mã phản hồi SMTP thực tế + pha xử lý + tình trạng kết nối + chính sách provider**, rồi mới quyết định lịch retry hoặc cảnh báo.

### 7.1. Luồng xử lý kết quả ở lớp ứng dụng

Trong một hệ thống có lưu trạng thái công việc, có thể dùng cách phân loại ở mức ý tưởng:

~~~text
Gọi JavaMailSender.send(...)
  |
  +-- Trả về bình thường
  |      -> SUBMITTED_TO_SMTP
  |         (chưa phải DELIVERED_TO_RECIPIENT)
  |
  +-- Có SMTP reply 4xx
  |      -> TEMPORARY_FAILURE
  |         (retry theo backoff/giới hạn)
  |
  +-- Có SMTP reply 5xx
  |      -> PERMANENT_FAILURE
  |         (sửa dữ liệu/cấu hình/chính sách trước khi gửi lại)
  |
  +-- Timeout / mất kết nối / không có SMTP reply
         -> UNKNOWN_OUTCOME hoặc TRANSPORT_FAILURE
            (đánh giá pha thất bại và khả năng gửi trùng)
~~~

Tên trạng thái trên là **ví dụ thiết kế của ứng dụng**, không phải enum do Spring Mail cung cấp sẵn. Nếu provider hỗ trợ webhook, trạng thái `SUBMITTED_TO_SMTP` có thể được bổ sung bằng `DELIVERED`, `BOUNCED` hoặc các sự kiện hậu gửi khác.

## 8. Chiến lược xử lý thực tế theo nhóm mã

| Tình huống | Phân loại | Việc ứng dụng nên làm | Việc cần tránh |
| --- | --- | --- | --- |
| `250` sau khi kết thúc `DATA` | SMTP đã chấp nhận thông điệp | Lưu thời gian, ID giao dịch/provider nếu có; tiếp tục theo dõi delivery khi cần | Báo chắc chắn người dùng đã nhận/đọc thư |
| `421`, `450`, `451`, `452` | Thất bại tạm thời | Retry có khoảng chờ, giới hạn và log phục vụ điều tra | Gửi lặp ngay lập tức không giới hạn |
| `454` | Lỗi xác thực tạm thời | Kiểm tra tình trạng provider, cảnh báo khi kéo dài | Xem là credentials sai vĩnh viễn ngay lập tức |
| `535` | Xác thực bị từ chối | Kiểm tra credentials, quyền và cơ chế AUTH | Liên tục thử sai làm khóa tài khoản |
| `550 5.1.1` | Người nhận không hợp lệ theo server | Ghi nhận địa chỉ lỗi, yêu cầu sửa | Retry với cùng địa chỉ không thay đổi |
| `550 5.7.1` | Bị từ chối do quyền/chính sách | Kiểm tra SPF/DKIM/DMARC nếu liên quan, From, relay và cấu hình provider | Mặc định kết luận mailbox không tồn tại |
| `552` hoặc từ chối do kích thước | Thư/quota vượt giới hạn | Giảm kích thước/tách đính kèm hoặc xử lý quota | Tăng số lần retry khi dữ liệu không đổi |
| Mất kết nối sau `DATA`, chưa nhận phản hồi cuối | Kết quả chưa xác định | Kiểm tra trạng thái provider nếu có, áp dụng chống trùng và quy tắc retry thận trọng | Khẳng định chắc chắn thư chưa được gửi |

### 8.1. Những thông tin nên lưu để điều tra

Với mỗi lần gửi, có thể lưu:

- ID tác vụ/ID nghiệp vụ và loại email;
- SMTP host hoặc provider đã dùng (không ghi credentials);
- pha SMTP xảy ra lỗi, mã ba chữ số và enhanced status nếu lấy được;
- mã lỗi nội bộ, số lần thử, thời điểm thất bại và lịch retry tiếp theo;
- ID message/provider (nếu có) và trạng thái delivery được cập nhật sau này.

Không nên log mật khẩu, token xác thực, toàn bộ nội dung email, mã đặt lại mật khẩu hay dữ liệu nhạy cảm của người dùng. Nếu cần lưu địa chỉ email để hỗ trợ vận hành, áp dụng quy tắc quyền truy cập và che/mã hóa theo chính sách của hệ thống.

### 8.2. Phân biệt lỗi giao thức với khả năng gửi thư thực tế

Có bốn tình huống hay bị đánh đồng:

1. **Client nhận `250` sau `RCPT TO`:** địa chỉ người nhận được chấp nhận ở bước envelope, nhưng nội dung thư chưa gửi.
2. **Client nhận `250` sau dấu chấm kết thúc `DATA`:** máy chủ đã nhận thông điệp để xử lý/chuyển tiếp.
3. **Provider báo “delivered”:** thường là thông điệp đã được máy chủ nhận phía đích tiếp nhận, theo định nghĩa provider; chưa chứng minh thư nằm trong Inbox.
4. **Người dùng đã đọc thư:** không thể khẳng định chỉ từ kết quả SMTP; những cơ chế theo dõi mở thư cũng có giới hạn về độ tin cậy và quyền riêng tư.

## 9. Tự diễn giải một số phản hồi

Hãy đọc mỗi dòng cùng với tình huống:

| Phản hồi quan sát được | Cách diễn giải |
| --- | --- |
| `220 smtp.example.net ready` khi mở kết nối | Kết nối SMTP đã tới một server sẵn sàng; chưa có email nào được gửi |
| `235 2.7.0 Authentication successful` sau AUTH | Xác thực thành công; các bước gửi thư vẫn phải diễn ra |
| `250 2.0.0 Queued as ABC` sau kết thúc DATA | Máy chủ chấp nhận thư để chuyển tiếp; lưu mã ABC để tra cứu nếu provider hỗ trợ |
| `451 4.7.1 Try again later` tại RCPT TO | Địa chỉ đang bị tạm hoãn; cân nhắc retry theo chính sách |
| `550 5.1.1 User unknown` tại RCPT TO | Server từ chối người nhận; kiểm tra/sửa địa chỉ |
| `550 5.7.1 Relay denied` tại RCPT TO | Server từ chối chuyển tiếp; kiểm tra cấu hình/quyền gửi |
| `535 5.7.8 Invalid credentials` tại AUTH | Kiểm tra tài khoản, secrets và cơ chế xác thực |
| Không có mã vì kết nối bị timeout sau dấu chấm của DATA | Kết quả giao dịch chưa rõ; xử lý nguy cơ duplicate khi retry |

Khi đọc log SMTP của một module Spring Mail, hãy xác định lần lượt **lệnh đang được phản hồi**, **mã ba chữ số**, **enhanced status code nếu có** và **kết quả mà hệ thống có thể khẳng định**. Từ đó, nhóm 2xx cho biết công đoạn nào đã thành công; nhóm 4xx hướng tới việc thử lại có kiểm soát; nhóm 5xx hướng tới sửa lỗi dữ liệu, cấu hình hoặc chính sách. Cách đọc này giúp tránh cả hai sai lầm lớn: thông báo “đã giao thư” quá sớm và retry vô hạn những yêu cầu SMTP vốn đang bị từ chối vĩnh viễn.
