# EHLO, HELO, MAIL FROM, RCPT TO và DATA trong SMTP

## 1. Năm lệnh nền tảng của một phiên SMTP

**Simple Mail Transfer Protocol (SMTP)** là giao thức được dùng để nộp và chuyển tiếp email giữa ứng dụng gửi thư và máy chủ mail, hoặc giữa các máy chủ mail với nhau. Trong một ứng dụng sử dụng **Spring Framework Mail**, lập trình viên thường gọi `JavaMailSender.send(...)` thay vì thao tác trực tiếp từng lệnh. Tuy vậy, hiểu các lệnh SMTP là điều quan trọng để phân biệt giai đoạn thiết lập kết nối, khai báo người gửi/người nhận và truyền nội dung; đồng thời giúp đọc chính xác log và phản hồi lỗi từ SMTP server.

Năm lệnh chính:

| Lệnh | Vai trò | Trạng thái thay đổi |
| --- | --- | --- |
| `EHLO` | Chào máy chủ theo Extended SMTP (ESMTP), nhận các extension được hỗ trợ | Bắt đầu cuộc hội thoại ESMTP và nhận danh sách khả năng của server |
| `HELO` | Chào máy chủ theo SMTP cơ bản | Thiết lập cuộc hội thoại SMTP truyền thống |
| `MAIL FROM` | Chỉ định **envelope sender**, còn gọi là reverse-path | Bắt đầu một giao dịch gửi thông điệp |
| `RCPT TO` | Chỉ định **envelope recipient**; có thể gọi nhiều lần | Thêm từng người nhận được máy chủ chấp nhận |
| `DATA` | Truyền **header và body** của email | Sau phản hồi `354`, truyền các dòng nội dung và kết thúc bằng `CRLF . CRLF` |

Điểm cốt lõi là phải phân biệt **phiên SMTP** với **giao dịch gửi một email**. Một kết nối có thể được chào một lần bằng `EHLO`, sau đó thực hiện nhiều giao dịch riêng biệt, mỗi giao dịch thường có dạng:

~~~text
MAIL FROM:<sender@example.com>
RCPT TO:<recipient-1@example.net>
RCPT TO:<recipient-2@example.net>
DATA
[Header, dòng trống, body/MIME]
<CRLF>.<CRLF>
~~~

`EHLO` hoặc `HELO` thường đứng trước giao dịch. Các lệnh `STARTTLS` và `AUTH` có thể xuất hiện sau `EHLO` để nâng cấp kết nối và xác thực theo chính sách của máy chủ. Phiên được kết thúc bằng `QUIT`. Các dòng ở trên là cấu trúc khái quát; khi thực thi, client phải đọc và xử lý **phản hồi của server sau mỗi bước**.

## 2. Vì sao thứ tự lệnh quan trọng?

SMTP là giao thức đối thoại có trạng thái. Không thể gửi `DATA` ngay khi vừa thiết lập TCP rồi hy vọng server tự xác định người gửi và người nhận. Client thường phải:

1. Mở kết nối TCP; chờ máy chủ phát lời chào `220`.
2. Gửi `EHLO` (hoặc `HELO` khi phù hợp); đọc phản hồi.
3. Nếu cần và được hỗ trợ, thực hiện `STARTTLS`, chào lại; sau đó `AUTH`.
4. Gửi `MAIL FROM` để mở một giao dịch mới.
5. Gửi một hay nhiều `RCPT TO`; theo dõi từng địa chỉ được chấp nhận hay từ chối.
6. Khi có người nhận hợp lệ, gửi `DATA`; đợi `354` rồi gửi toàn bộ thông điệp.
7. Kết thúc dữ liệu; chờ phản hồi cuối, thường là `250` khi server nhận thư.
8. Bắt đầu giao dịch tiếp theo hoặc gửi `QUIT` để đóng phiên.

~~~mermaid
sequenceDiagram
    participant App as Spring / Jakarta Mail SMTP client
    participant Server as SMTP submission server
    App->>Server: TCP connection
    Server-->>App: 220 Ready
    App->>Server: EHLO app.example.com
    Server-->>App: 250 + ESMTP extensions
    opt TLS bắt buộc hoặc được chọn
        App->>Server: STARTTLS
        Server-->>App: 220 Start TLS
        Note over App,Server: TLS handshake
        App->>Server: EHLO app.example.com
        Server-->>App: 250 + capabilities mới
    end
    opt Server yêu cầu xác thực
        App->>Server: AUTH theo cơ chế hỗ trợ
        Server-->>App: Kết quả xác thực
    end
    App->>Server: MAIL FROM:<sender@example.com>
    Server-->>App: 250 Sender accepted
    App->>Server: RCPT TO:<lan@example.net>
    Server-->>App: 250 Recipient accepted
    App->>Server: DATA
    Server-->>App: 354 Continue
    App->>Server: Headers + body + CRLF . CRLF
    Server-->>App: 250 Accepted for delivery
    App->>Server: QUIT
    Server-->>App: 221 Closing
~~~

Trong ví dụ, `220`, `250`, `354` và `221` là **mã trả lời SMTP**. Chúng không phải HTTP status code. Mã `503 Bad sequence of commands` có thể xuất hiện khi client gửi lệnh sai giai đoạn của giao dịch.

## 3. EHLO: lời chào và thương lượng khả năng của server

**`EHLO`** là lệnh chào của **Extended SMTP (ESMTP)**. Client truyền tên máy của mình hoặc address literal hợp lệ để tự giới thiệu:

~~~text
C: EHLO app.example.com
S: 250-smtp.example.net Hello app.example.com
S: 250-SIZE 10485760
S: 250-8BITMIME
S: 250-STARTTLS
S: 250-PIPELINING
S: 250 AUTH PLAIN LOGIN
~~~

Ở đây `C:` là dòng client gửi; `S:` là dòng server trả về. Chú ý phản hồi nhiều dòng:

- `250-` với dấu gạch nối cho biết **phản hồi còn dòng tiếp theo**.
- `250 ` với dấu cách cho biết **dòng cuối** của phản hồi đó.
- Client phải đọc đủ phản hồi để biết toàn bộ extension trước khi tiếp tục.

Các khả năng phổ biến:

| Extension | Ý nghĩa |
| --- | --- |
| `SIZE 10485760` | Server công bố giới hạn kích thước message tính theo octet; ví dụ 10.485.760 octet |
| `STARTTLS` | Hỗ trợ nâng cấp kết nối SMTP hiện tại lên TLS |
| `AUTH PLAIN LOGIN` | Công bố các cơ chế xác thực SMTP sẵn có trong bối cảnh hiện tại |
| `PIPELINING` | Cho phép gửi một số lệnh liên tiếp mà chưa cần chờ từng phản hồi, theo quy định extension |
| `8BITMIME` | Hỗ trợ truyền body có octet 8-bit theo điều kiện của extension |
| `SMTPUTF8` | Hỗ trợ SMTP quốc tế hóa theo các ràng buộc của extension |
| `DSN` | Hỗ trợ các tham số thông báo trạng thái chuyển phát |
| `CHUNKING` | Hỗ trợ lệnh `BDAT` thay cách truyền `DATA` thông thường |

Máy chủ có thể công bố một tập khác, và không phải extension nào cũng xuất hiện trong mọi phiên. Client không được coi tất cả extension trên là mặc định. Ví dụ, nếu server không công bố `SMTPUTF8`, client không thể tùy tiện dùng yêu cầu gửi địa chỉ quốc tế cần extension đó.

### 3.1. Tên trong EHLO có phải là người gửi thư?

Không. Trong:

~~~text
EHLO app.example.com
~~~

`app.example.com` là danh tính **máy/client kết nối**, không phải địa chỉ email của người gửi. Nó khác với `MAIL FROM:<bounce@example.com>` và header `From: notifications@example.com` nằm trong nội dung thư.

Thông thường client dùng tên máy đầy đủ (FQDN) thích hợp; khi không thể dùng tên phù hợp, giao thức còn mô tả dạng address literal. Không nên lấy địa chỉ email của người dùng gắn vào trường EHLO như một cách đặt người gửi.

### 3.2. EHLO sau STARTTLS

Một phiên nộp thư qua cổng 587 có thể diễn ra:

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-STARTTLS
S: 250 SIZE 10485760
C: STARTTLS
S: 220 Ready to start TLS
   [TLS handshake hoàn tất]
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
   [Client xác thực; lược bỏ nội dung xác thực]
~~~

Sau STARTTLS thành công, client **phải bỏ các khả năng EHLO trước đó và chào EHLO lại**. Điều này quan trọng vì server có thể quảng bá tập khả năng khác sau khi kết nối được mã hóa. Một số server chỉ công bố `AUTH` sau khi TLS được thiết lập.

`STARTTLS` có nghĩa *nâng cấp* kết nối đang mở. Nó khác với TLS ngay từ đầu khi kết nối (implicit TLS), thường dùng ở cổng 465. Dùng đúng cơ chế theo nhà cung cấp SMTP; không gửi mật khẩu trên kênh không đáp ứng yêu cầu bảo mật.

## 4. HELO: lời chào SMTP truyền thống

**`HELO`** là cách chào cơ bản:

~~~text
S: 220 smtp.example.net SMTP ready
C: HELO app.example.com
S: 250 smtp.example.net Hello app.example.com
~~~

So sánh:

| Khía cạnh | `EHLO` | `HELO` |
| --- | --- | --- |
| Mục đích | Chào theo ESMTP và khám phá extension | Chào theo SMTP cơ bản |
| Phản hồi thành công | Có thể có nhiều dòng `250-...` nêu khả năng | Thường trả một dòng `250` |
| STARTTLS / AUTH / SIZE | Có thể được quảng bá bằng EHLO | HELO không có cơ chế công bố extension |
| Ứng dụng hiện đại | Thường thử trước | Dùng cho tương thích khi thích hợp |

Client có thể dự phòng từ `EHLO` sang `HELO` khi kết nối đến SMTP server cũ không hỗ trợ ESMTP. Nhưng việc fallback không phải lý do để bỏ qua chính sách bắt buộc mã hóa, xác thực hoặc extension cần thiết. Nếu ứng dụng yêu cầu STARTTLS mà server không hỗ trợ, cần báo lỗi phù hợp.

Trong JavaMailSender, bước chào do Jakarta Mail SMTP transport thực hiện theo cấu hình và phản hồi máy chủ; service nghiệp vụ không cần tự gửi chuỗi `EHLO`/`HELO`.

## 5. MAIL FROM: mở giao dịch và xác định envelope sender

Sau khi chào và thực hiện những bước bảo mật cần thiết, client bắt đầu giao dịch:

~~~text
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
~~~

`MAIL FROM` khai báo **reverse-path** hay **envelope sender**. Nó phục vụ việc vận chuyển thư và xử lý thông báo lỗi chuyển phát (bounce). Đây là thông tin của **phong bì SMTP**, không nhất thiết giống địa chỉ From hiển thị trong MUA.

Ví dụ một thư có thể chứa các địa chỉ khác nhau:

~~~text
SMTP envelope:
    MAIL FROM:<bounce@example.com>

Message headers:
    From: "Weekly Reports" <reports@example.com>
    Reply-To: support@example.com
~~~

| Trường | Vai trò |
| --- | --- |
| `MAIL FROM` | Địa chỉ envelope dùng trong quá trình gửi và xử lý lỗi |
| `From:` | Địa chỉ/tên tác giả hoặc người gửi trong thông điệp mà người nhận nhìn thấy |
| `Reply-To:` | Địa chỉ được ưu tiên khi người nhận chọn “Trả lời” |

Hệ thống gửi email số lượng lớn thường dùng địa chỉ bounce chuyên biệt, trong khi header `From:` dùng tên dịch vụ. Khác biệt này tự nó chưa cho biết thư hợp lệ hay giả mạo; xác thực tài khoản, quyền gửi và cơ chế bảo vệ miền như SPF/DKIM/DMARC có những vai trò riêng.

### 5.1. Tham số MAIL FROM mở rộng

Nếu EHLO công bố `SIZE`, client có thể gửi tham số kích thước:

~~~text
C: MAIL FROM:<bounce@example.com> SIZE=4096
S: 250 2.1.0 Sender accepted
~~~

`4096` là ví dụ số **octet** của message theo quy tắc extension, không phải độ dài Java `String`. Các tham số như `BODY=8BITMIME` và `SMTPUTF8` cũng phụ thuộc extension và điều kiện tương ứng.

Cú pháp reverse-path rỗng:

~~~text
C: MAIL FROM:<>
~~~

được dùng cho một số thông báo trạng thái chuyển phát nhằm tránh tạo vòng lặp bounce. Đây không phải cách để một ứng dụng tùy ý gửi thư nặc danh; nó cũng không đồng nghĩa header `From:` bên trong message phải rỗng.

Nếu `MAIL FROM` không được chấp nhận, giao dịch chưa thể tiếp tục theo hướng gửi recipient và dữ liệu như một thư hợp lệ. Ví dụ server có thể từ chối do tài khoản không được phép dùng địa chỉ envelope đó.

## 6. RCPT TO: một lệnh cho mỗi người nhận chuyển phát

Sau `MAIL FROM`, client chỉ định người nhận:

~~~text
C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<team@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<unknown@example.net>
S: 550 5.1.1 Mailbox unavailable
~~~

Mỗi địa chỉ có **phản hồi riêng**. Hai người nhận đầu được chấp nhận, người nhận thứ ba bị từ chối. Một email có thể có nhiều `RCPT TO` vì SMTP envelope phân phối thư cho từng đích.

### 6.1. RCPT TO khác To, Cc và Bcc thế nào?

Giả sử giao diện soạn thư hiển thị:

~~~text
To:  lan@example.net
Cc:  team@example.net
Bcc: quan@example.org
~~~

Envelope có thể mang cả ba đích:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<team@example.net>
RCPT TO:<quan@example.org>
~~~

Trong khi header bên trong `DATA` của bản thư gửi cho Lan và nhóm có thể chỉ chứa:

~~~text
To: lan@example.net
Cc: team@example.net
~~~

Địa chỉ Bcc phải được xử lý sao cho không làm lộ thông tin với những người nhận không có quyền thấy nó; cách tạo và phân phối header Bcc phụ thuộc MUA/hệ thống mail. **Header `To:` không phải danh sách phát thư duy nhất**: server vận chuyển dựa vào các `RCPT TO` được chấp nhận. Việc tự viết dòng `To: ...` vào body cũng không làm SMTP gửi thư tới địa chỉ đó.

### 6.2. Người nhận bị từ chối một phần

| Phản hồi | Diễn giải thường gặp | Ý nghĩa đối với client |
| --- | --- | --- |
| `250` | Recipient được chấp nhận | Có thể thêm recipient hoặc chuyển sang `DATA` |
| `251` | Người dùng không cục bộ; server đồng ý chuyển tiếp | Coi theo quy tắc thành công của server |
| `450` | Hộp thư tạm thời không khả dụng | Có thể cân nhắc retry |
| `451` | Lỗi xử lý tạm thời | Cần chính sách thử lại phù hợp |
| `550` | Từ chối vĩnh viễn: có thể do địa chỉ hoặc chính sách | Xem mã nâng cao và thông báo |
| `553` | Tên/địa chỉ mailbox không được chấp nhận | Kiểm tra cú pháp và quyền gửi |

**Không thể luôn suy ra `550` = “không tồn tại người nhận”**: nhiều máy chủ dùng `550` vì chính sách hoặc từ chối relay. Xem cả enhanced status code (ví dụ `5.1.1`, `5.7.1`) và giải thích mà server trả về.

Nếu vẫn có ít nhất một `RCPT TO` hợp lệ, client có thể tiếp tục gửi `DATA` cho tập recipient đã được chấp nhận. Nếu tất cả bị từ chối, client không nên tiếp tục gửi dữ liệu cho một giao dịch không có đích; thường cần `RSET` hoặc kết thúc phiên. Kết quả từng recipient quan trọng khi thiết kế báo lỗi và retry để tránh gửi trùng cho những người đã được chấp nhận.

## 7. DATA: truyền header và body của thông điệp

Khi đã có người nhận được chấp nhận, client gửi:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
~~~

Mã `354` là phản hồi trung gian yêu cầu client gửi nội dung. Từ đây, server đọc **dữ liệu message** gồm các dòng header, dòng trống phân cách và body. Ví dụ:

~~~text
C: DATA
S: 354 Continue
C: From: Reports <reports@example.com>
C: To: lan@example.net
C: Subject: Weekly report
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=us-ascii
C:
C: The weekly report is ready.
C: .
S: 250 2.0.0 Message accepted for delivery
~~~

Dòng cuối chỉ chứa dấu chấm trong transcript biểu diễn **`CRLF . CRLF`**, tức cách SMTP đánh dấu kết thúc nội dung. SMTP sử dụng cặp ký tự kết thúc dòng CRLF trên đường truyền. Sau terminator, server trả phản hồi cuối xác nhận chấp nhận hoặc từ chối thông điệp.

### 7.1. DATA truyền cả header, không chỉ nội dung người dùng gõ

Một email theo cấu trúc thông điệp bao gồm:

1. **Header**: ví dụ `From:`, `To:`, `Subject:`, `Date:`, `Message-ID:` và các trường MIME.
2. **Dòng trống**: ranh giới giữa headers và body.
3. **Body**: text, HTML hoặc nội dung đa phần MIME, có thể chứa attachment.

Với email HTML và tệp đính kèm, Java/Jakarta Mail dựng các phần `multipart/alternative`, `multipart/mixed`, boundary, content type và mã hóa thích hợp. Lệnh `DATA` chỉ vận chuyển chuỗi thông điệp; nó không tự hiểu ý nghĩa của file PDF hay HTML nếu không có MIME header mô tả.

### 7.2. Dot-stuffing: vì sao một dấu chấm phải thành hai?

Vì dòng chỉ có dấu `.` báo kết thúc `DATA`, một dòng body **thực sự bắt đầu bằng dấu chấm** phải được client thêm một dấu chấm trước khi truyền:

| Dòng body gốc | Dòng truyền qua DATA |
| --- | --- |
| `Hello` | `Hello` |
| `.Warning` | `..Warning` |
| `..Two dots` | `...Two dots` |
| `.` | `..` |

Server nhận loại bỏ dấu chấm bổ sung khi khôi phục dữ liệu. Cơ chế này gọi là **dot-stuffing** hoặc **SMTP transparency**. Đối với Spring Mail, lập trình viên **không** tự thêm dấu chấm vào `helper.setText(...)`; SMTP transport của Jakarta Mail xử lý định dạng đường truyền.

Ví dụ một nội dung hai dòng:

~~~text
Body thực tế:
.Read this first
See the report

Khi truyền trong DATA:
..Read this first
See the report
.
~~~

Dòng `..Read this first` thuộc nội dung; dòng chỉ có `.` cuối cùng mới kết thúc giao dịch. Cần lưu ý rằng chuẩn quy định CRLF và giá trị byte cụ thể; ví dụ hiển thị văn bản đơn giản hóa cách thể hiện các byte này.

### 7.3. Server nhận DATA thành công có nghĩa đã giao tới Inbox?

**Chưa.** Phản hồi:

~~~text
S: 250 2.0.0 Queued as ABC123
~~~

chỉ cho biết server đã **tiếp nhận thông điệp vào trách nhiệm xử lý/chuyển phát**. Đây là kết quả của lần nộp thư vào server, không chứng minh rằng:

- Email đã nằm trong Inbox của người nhận;
- Email không bị lọc vào thư rác;
- Người nhận đã đọc thư;
- Không còn khả năng thất bại ở chặng vận chuyển sau đó.

Thư có thể bị hoãn chuyển phát, bị từ chối ở bước tiếp theo hoặc phát sinh DSN/bounce. Ứng dụng muốn theo dõi kết quả cuối cần nhận tín hiệu phù hợp từ nhà cung cấp (ví dụ webhook/API trạng thái) hoặc xử lý phản hồi lỗi phát sinh sau đó.

### 7.4. Khi nào không thấy DATA?

Nếu server có công bố ESMTP extension **`CHUNKING`**, một client hỗ trợ có thể dùng `BDAT` để truyền body theo khối thay cho `DATA`. Vì vậy khi đọc trace, không nên kết luận ứng dụng không gửi thư chỉ vì thiếu chuỗi `DATA` nếu hai phía đang sử dụng cơ chế mở rộng khác.

## 8. Transcript SMTP hoàn chỉnh để đối chiếu từng bước

Phiên ví dụ dưới đây giả định server hỗ trợ TLS và có cơ chế xác thực sau TLS. Phản hồi bằng chữ và mã bổ sung là minh họa; hệ thống thực tế có thể khác.

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250-STARTTLS
S: 250 8BITMIME

C: STARTTLS
S: 220 Ready to start TLS
   [TLS handshake completed]

C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
   [SMTP authentication completed; credentials omitted]

C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender accepted
C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient accepted
C: RCPT TO:<unknown@example.net>
S: 550 5.1.1 Mailbox unavailable

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: Reports <reports@example.com>
C: To: lan@example.net
C: Subject: Weekly report
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=us-ascii
C:
C: The report is ready.
C: ..Please read section 2.
C: .
S: 250 2.0.0 Queued as ABC123

C: QUIT
S: 221 2.0.0 Goodbye
~~~

Diễn giải:

- `EHLO` đầu tiên nhận extension `STARTTLS`, sau TLS phải `EHLO` lần nữa.
- `MAIL FROM` được chấp nhận, do đó mở giao dịch.
- Recipient `lan@example.net` được chấp nhận; `unknown@example.net` bị từ chối.
- `DATA` truyền message cho những recipient **đã được chấp nhận**, không “sửa” recipient bị từ chối.
- Dòng `..Please read section 2.` là dạng dot-stuffing của nội dung bắt đầu bằng một dấu chấm.
- `250` sau dấu kết thúc `.` nghĩa là server đã nhận để xử lý tiếp; `QUIT` đóng kết nối.

Một phiên có thể gửi giao dịch email khác trên kết nối này trước khi `QUIT`, nhưng phải khai báo `MAIL FROM` và các recipient cho giao dịch mới.

## 9. SMTP envelope khác message header như thế nào?

Đây là ranh giới đặc biệt quan trọng khi debug các trường `From`, `To` và `Bcc` trong Spring Mail.

~~~text
SMTP ENVELOPE (giao tiếp điều khiển)
  MAIL FROM:<bounce@example.com>
  RCPT TO:<lan@example.net>
  RCPT TO:<quan@example.org>

MESSAGE (được truyền trong DATA)
  From: Reports <reports@example.com>
  To: lan@example.net
  Reply-To: support@example.com
  Subject: Weekly report

  Here is your weekly report.
~~~

| Câu hỏi | Căn cứ trả lời |
| --- | --- |
| Hệ thống SMTP đang chuyển thư cho ai? | Các `RCPT TO` được server chấp nhận |
| Địa chỉ envelope để phản hồi lỗi gửi là gì? | `MAIL FROM` |
| Người nhận nhìn thấy tên người gửi nào? | Header `From:` trong `DATA` |
| Khi bấm Reply, email được gửi tới đâu? | Header `Reply-To:` nếu có; nếu không thường dựa vào `From:` |
| Tiêu đề, text, HTML và attachment nằm ở đâu? | Bên trong message header/body/MIME được truyền qua `DATA` |
| Địa chỉ Bcc có cần xuất hiện trong header người nhận nhìn thấy? | Không; envelope có thể chứa recipient Bcc trong khi header được giữ kín phù hợp |

Sự khác nhau này giải thích tại sao một thư có trường `To:` vẫn cần lệnh `RCPT TO`, và tại sao đặt `From:` trong nội dung không đồng nghĩa đã thay đổi reverse-path của SMTP.

## 10. Đọc mã phản hồi và xử lý lỗi theo từng lệnh

SMTP dùng mã phản hồi ba chữ số. Chữ số đầu cho biết nhóm kết quả:

| Nhóm | Ý nghĩa cơ bản | Ví dụ |
| --- | --- | --- |
| `2xx` | Thành công | `220` server sẵn sàng; `250` lệnh được chấp nhận; `221` kết thúc kết nối |
| `3xx` | Server chờ client cung cấp thêm dữ liệu | `354` chờ phần message của `DATA` |
| `4xx` | Lỗi tạm thời | `421` dịch vụ không khả dụng; `450` lỗi hộp thư tạm thời |
| `5xx` | Lỗi vĩnh viễn hoặc yêu cầu không được chấp nhận | `500` lỗi cú pháp; `503` sai thứ tự; `550` từ chối |

Một số tình huống cụ thể:

**EHLO thành công nhưng không có STARTTLS.** Nếu cấu hình bắt buộc TLS, client cần dừng hoặc báo lỗi, không gửi thông tin xác thực qua kết nối không đạt chính sách.

**MAIL FROM nhận `550`/`553`.** Có thể server không cho phép địa chỉ envelope, tài khoản không có quyền gửi hoặc cú pháp sai. Không thể kết luận lỗi recipient vì chưa tới bước `RCPT TO`.

**RCPT TO nhận `450`.** Đây thường là lỗi tạm thời; ứng dụng có thể lên lịch gửi lại phù hợp chính sách, thay vì báo địa chỉ vĩnh viễn sai.

**RCPT TO nhận `550`.** Có thể recipient không tồn tại hoặc server từ chối vì chính sách. Cần đọc enhanced status code và chi tiết phản hồi.

**DATA nhận `354` rồi sau dấu kết thúc trả `552` hoặc `554`.** Server cho phép bắt đầu truyền nhưng **không chấp nhận thông điệp cuối cùng**. Không được chỉ thấy `354` rồi ghi nhận email đã gửi.

**Mất kết nối trước phản hồi cuối DATA.** Client có thể không biết server đã ghi nhận message hay chưa. Retry mù quáng có thể gửi trùng. Với nghiệp vụ quan trọng, cần thiết kế cơ chế định danh yêu cầu và theo dõi trạng thái gửi để xử lý tình huống kết quả không chắc chắn.

### 10.1. RSET và QUIT hỗ trợ điều khiển giao dịch

`RSET` hủy trạng thái của **giao dịch hiện tại** như sender và recipients đã chọn nhưng thông thường vẫn giữ phiên SMTP. Client có thể bắt đầu lại với `MAIL FROM`.

~~~text
C: MAIL FROM:<bounce@example.com>
S: 250 OK
C: RCPT TO:<invalid@example.net>
S: 550 Recipient rejected
C: RSET
S: 250 Reset OK
C: MAIL FROM:<bounce@example.com>
S: 250 OK
~~~

`QUIT` đề nghị đóng phiên và server thường trả `221`. `RSET` không có nghĩa “thu hồi email đã gửi”, vì một message đã được chấp nhận ở giao dịch trước không bị xóa chỉ bởi `RSET` của giao dịch tiếp theo.

## 11. Liên hệ với Spring Framework Mail

Khi dùng **`JavaMailSender`**, ứng dụng làm việc với các đối tượng email; Jakarta Mail SMTP transport lo phiên SMTP bên dưới.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["JavaMailSender + MimeMessage"]
    B --> C["Jakarta Mail SMTP transport"]
    C --> D["EHLO / HELO"]
    D --> E["MAIL FROM"]
    E --> F["RCPT TO từng người nhận"]
    F --> G["DATA với headers + body"]
    G --> H["SMTP server tiếp nhận"]
~~~

| Trong code Spring | Trách nhiệm tương ứng |
| --- | --- |
| Cấu hình `host`, `port`, TLS, auth | Thiết lập kết nối và thương lượng SMTP, gồm `EHLO`, có thể `STARTTLS` và `AUTH` |
| `MimeMessageHelper.setFrom(...)` | Tạo header `From:`; envelope sender có thể lấy theo message hoặc cấu hình transport riêng |
| `setTo(...)`, `setCc(...)`, `setBcc(...)` | Chuẩn bị recipient của message để transport tạo `RCPT TO` khi gửi |
| `setSubject(...)`, `setText(...)`, `addAttachment(...)` | Tạo thông tin/header/body/MIME được truyền trong `DATA` |
| `mailSender.send(message)` | Kích hoạt thao tác kết nối/vận chuyển, tiếp nhận phản hồi server hoặc lỗi |

Không có nghĩa mỗi setter trên `MimeMessageHelper` lập tức gửi một lệnh SMTP: chúng chủ yếu thay đổi đối tượng message trong bộ nhớ; quá trình vận chuyển bắt đầu khi thực sự gửi.

### 11.1. Ví dụ gửi thông điệp qua JavaMailSender

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {

    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, String text) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());
            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Weekly report");
            helper.setText(text, false); // plain text
        } catch (MessagingException ex) {
            throw new IllegalStateException("Cannot prepare email", ex);
        }

        mailSender.send(message);
    }
}
~~~

Với `sendReport("lan@example.net", "Your report is ready")`:

1. Service chuẩn bị `MimeMessage` chứa From, To, Subject và body.
2. `JavaMailSender` dùng Jakarta Mail transport được cấu hình để mở kết nối tới SMTP server.
3. Transport thực hiện chào `EHLO`, thương lượng khả năng, bảo mật/xác thực nếu cần.
4. Transport khai báo `MAIL FROM`, `RCPT TO` và truyền message bằng `DATA` hoặc extension thích hợp.
5. Nếu server từ chối hay kết nối lỗi, Spring Mail có thể ném ngoại lệ runtime thuộc họ `MailException`, ví dụ `MailAuthenticationException` hoặc `MailSendException`.

Đoạn mã chỉ minh họa giao tiếp Spring Mail. Trong ứng dụng thực tế, địa chỉ `From` phải được cấp quyền, các giá trị do client cung cấp phải được kiểm tra và hệ thống cần chính sách chống lạm dụng, giới hạn số lượng thư và retry phù hợp. Lỗi `MessagingException` xảy ra khi tạo message khác với lỗi vận chuyển tại `send(...)`.

### 11.2. Cấu hình SMTP submission với Spring Boot

Trong Spring Boot có `spring-boot-starter-mail`, một cấu hình mẫu:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: smtp-user-from-environment
    password: smtp-secret-from-environment
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Hai trường `username`/`password` ở đây là **giá trị minh họa**, không phải thông tin đăng nhập sử dụng được; triển khai thực tế phải lấy credentials từ biến môi trường hoặc kho secrets, không commit vào repository.

- Cổng **587** thường dùng cho SMTP submission với STARTTLS theo chính sách provider.
- `mail.smtp.starttls.enable` cho phép nâng cấp kết nối khi server hỗ trợ.
- `mail.smtp.starttls.required` yêu cầu STARTTLS thành công mới tiếp tục.
- `mail.smtp.auth` dùng xác thực SMTP khi server yêu cầu và tài khoản được cấu hình.
- Các timeout tính bằng mili-giây, hạn chế việc thao tác mạng bị treo không giới hạn.

Các thuộc tính `spring.mail.*` là tiện ích cấu hình của **Spring Boot**. Với Spring Framework thuần, có thể tự khai báo bean `JavaMailSenderImpl` cùng các thuộc tính Jakarta Mail. Nếu nhà cung cấp yêu cầu implicit TLS qua cổng **465**, phải cấu hình chế độ TLS tương ứng thay vì áp dụng nguyên cách STARTTLS ở cổng 587.

### 11.3. Có cần tự lập trình EHLO, MAIL FROM và DATA không?

Thông thường **không**. Jakarta Mail xử lý:

- Đọc lời chào `220` và phản hồi ESMTP nhiều dòng;
- `EHLO`, `HELO` và các khả năng extension;
- STARTTLS, chào lại, các cơ chế xác thực;
- Tạo envelope sender, các recipient, gọi `DATA` hoặc cơ chế mở rộng;
- CRLF, MIME encoding, dot-stuffing và dòng kết thúc dữ liệu;
- Phản hồi server, trạng thái từ chối và lỗi mạng.

Tầng Spring nên tập trung vào danh tính gửi hợp lệ, nội dung email, quyền của người dùng, thời điểm gửi, giới hạn tải và cách phản hồi tình trạng giao dịch. Khi cần điều tra lỗi gửi, hãy nhìn vào giai đoạn SMTP xảy ra lỗi thay vì tự viết lại giao thức.

## 12. Vận hành an toàn và diễn giải trạng thái gửi

### 12.1. Phân biệt accepted, delivered và read

`250` sau `DATA` thường chỉ là **server accepted/queued**, chưa phải **delivered to mailbox** và càng chưa phải **read by user**. Trạng thái chuyển phát thực tế có thể phụ thuộc chặng relay sau đó, chính sách spam hoặc kết quả riêng của provider. Để hiển thị trạng thái đầy đủ, ứng dụng cần nguồn thông tin tương ứng ngoài phản hồi SMTP ban đầu.

### 12.2. Xử lý lỗi tạm thời và vĩnh viễn

Nhóm `4xx` thường cần cân nhắc thử lại sau một khoảng thời gian hợp lý; nhóm `5xx` thường cần xem lại địa chỉ, nội dung, quyền gửi hoặc cấu hình. Đừng retry vô hạn hoặc gửi lại toàn bộ danh sách người nhận nếu chỉ một người bị từ chối. Một yêu cầu nghiệp vụ nên có định danh, giới hạn retry và ghi nhận kết quả từng đích nếu cần.

### 12.3. Đừng để log SMTP làm lộ dữ liệu

Khi bật debug/protocol trace của Jakarta Mail, dữ liệu quan sát có thể chứa địa chỉ email, header, nội dung thư và thông tin xác thực tùy cơ chế và mức ghi log. Chỉ bật trong phạm vi cần thiết, kiểm soát quyền truy cập, che dữ liệu nhạy cảm và tránh để credentials/tokens trong log hoặc tài liệu.

### 12.4. Unicode trong body và SMTPUTF8 là hai vấn đề khác nhau

Body tiếng Việt có thể được biểu diễn qua MIME với `charset=UTF-8` và encoding thích hợp. Tuy nhiên địa chỉ email quốc tế đòi hỏi `SMTPUTF8` trong một số trường hợp: chỉ khai báo charset cho body **không** có nghĩa đã được phép gửi mọi dạng địa chỉ quốc tế qua SMTP.

### 12.5. Một số câu hỏi kiểm tra sự hiểu biết

**“Tại sao đã có To trong email mà SMTP vẫn cần RCPT TO?”**  
`To:` là header của message, còn `RCPT TO` là địa chỉ chuyển phát trong envelope. Danh sách hai phía không nhất thiết giống nhau, nhất là với Bcc.

**“Nếu server trả 354 thì coi như gửi thành công được chưa?”**  
Chưa. `354` chỉ yêu cầu truyền dữ liệu. Phải hoàn tất message và đọc phản hồi sau terminator.

**“Nếu EHLO bị lỗi thì luôn gửi HELO rồi tiếp tục?”**  
Không. HELO chỉ là phương án tương thích khi phù hợp; các yêu cầu về TLS, authentication và extension vẫn phải được đáp ứng.

**“MAIL FROM có giống From trong email không?”**  
Không nhất thiết. `MAIL FROM` là reverse-path trong SMTP envelope; `From:` là header hiển thị trong message.

**“Spring JavaMailSender có phải SMTP server không?”**  
Không. Nó là API phía ứng dụng gọi Jakarta Mail để **kết nối đến server** và gửi thông điệp. Hạ tầng SMTP server chịu trách nhiệm tiếp nhận và chuyển tiếp.

## 13. Áp dụng trong một tình huống thực tế

Một dịch vụ Spring gửi báo cáo tuần cho ba thành viên. Backend tạo `MimeMessage` với địa chỉ gửi đã được cấp quyền, tiêu đề và tài liệu đính kèm. Khi gọi `send(...)`, SMTP transport chào `EHLO` để biết khả năng server, thực hiện TLS/xác thực theo cấu hình, mở giao dịch `MAIL FROM`, phát từng `RCPT TO` và cuối cùng chuyển thông điệp MIME bằng `DATA`.

Nếu một recipient bị từ chối trong khi hai người còn lại được chấp nhận, ứng dụng cần ghi nhận tình huống gửi một phần theo hành vi thư viện và chính sách gửi của hệ thống. Nếu server trả `250` sau `DATA`, ứng dụng có thể ghi trạng thái “nhà cung cấp đã tiếp nhận yêu cầu gửi”, đồng thời tiếp tục theo dõi kết quả chuyển phát nếu nghiệp vụ đòi hỏi.

**Chuỗi để ghi nhớ:** `EHLO/HELO` thiết lập đối thoại, `MAIL FROM` xác định envelope sender, `RCPT TO` quyết định các đích gửi, và `DATA` truyền chính email. Hiểu đúng từng ranh giới giúp kiểm tra lỗi SMTP, tránh nhầm lẫn giữa email header với SMTP envelope và dùng Spring Framework Mail chính xác.
