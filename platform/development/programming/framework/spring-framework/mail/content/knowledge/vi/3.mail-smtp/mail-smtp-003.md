# Một message có nhiều người nhận và nhiều lệnh RCPT TO

Khi ứng dụng Spring gửi một thông báo cho ba địa chỉ email, máy chủ SMTP không nhất thiết cần nhận ba lần toàn bộ nội dung thông báo. Trong giao dịch SMTP thông thường, bên gửi có thể khai báo **một người gửi**, lần lượt khai báo **nhiều người nhận bằng nhiều lệnh RCPT TO**, rồi truyền **một lần nội dung thông điệp bằng DATA** cho tập người nhận mà máy chủ đã chấp nhận.

Đây là một đặc điểm nền tảng của SMTP: **số người nhận không đồng nghĩa với số thông điệp cần truyền**, và địa chỉ mà SMTP dùng để chuyển phát không hoàn toàn giống danh sách địa chỉ hiển thị trong các header To, Cc, Bcc.

Bài học giải thích giao dịch nhiều người nhận từ góc nhìn giao thức SMTP, sau đó liên hệ cách Spring Framework Mail và Jakarta Mail gửi email đến một nhóm địa chỉ.

## 1. Tình huống mở đầu: một thông báo cho ba người

Giả sử ứng dụng Spring cần gửi thông báo bảo trì đến:

- Lan: **lan@example.net** — người nhận chính.
- Minh: **minh@example.net** — người nhận được sao chép.
- Bộ phận giám sát: **audit@example.net** — người nhận ẩn.

Cả ba nhận cùng một nội dung:

> Hệ thống sẽ bảo trì lúc 22:00. Vui lòng lưu công việc trước thời điểm này.

Ở cấp giao thức, một giao dịch SMTP có thể có dạng:

~~~text
MAIL FROM:<notify@example.org>

RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>

DATA
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Thông báo bảo trì

Hệ thống sẽ bảo trì lúc 22:00.
Vui lòng lưu công việc trước thời điểm này.
.
~~~

Đoạn trên được rút gọn để nhấn mạnh cấu trúc. Khi trao đổi thực tế, client phải nhận và xử lý mã phản hồi từ server sau các lệnh; thông điệp cũng cần các header và quy tắc định dạng tương ứng. Dòng chỉ chứa dấu chấm kết thúc phần dữ liệu SMTP, **không phải nội dung của email**.

Điểm cần quan sát là:

1. Chỉ có **một MAIL FROM** bắt đầu giao dịch.
2. Có **ba lệnh RCPT TO**, mỗi lệnh chỉ định một địa chỉ nhận.
3. Sau khi các người nhận hợp lệ đã được server chấp nhận, client gửi **một DATA** chứa header và nội dung chung.
4. Địa chỉ **audit@example.net** có trong phong bì gửi thư nhưng không xuất hiện trong To/Cc ở phần nội dung email được trình bày.

Nếu máy chủ chấp nhận ba người nhận, cùng một thông điệp được nhận để xử lý chuyển phát cho cả ba. Máy chủ có thể tạo nhiều bản sao hoặc nhiều lượt chuyển tiếp ở các bước phía sau; cơ chế nội bộ đó độc lập với việc ứng dụng chỉ truyền DATA một lần trong giao dịch đang xét.

## 2. Ba đối tượng cần phân biệt: message, envelope và SMTP transaction

Trong tài liệu hoặc mã nguồn, từ **message** có thể chỉ một đối tượng Java, một email có header và body, hoặc một thư được lưu trong inbox. Để hiểu nhiều RCPT TO, cần tách ba khái niệm.

### 2.1. Nội dung email: Internet message

Một **Internet message** có các header và phần thân, ví dụ:

~~~text
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Thông báo bảo trì
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hệ thống sẽ bảo trì lúc 22:00.
~~~

Các header này mô tả thông tin được hiển thị và cách giải mã nội dung. Chúng thuộc cấu trúc email theo định dạng Internet Message Format và MIME nếu cần.

### 2.2. Phong bì SMTP: envelope

**SMTP envelope** xác định các địa chỉ dùng trong bước vận chuyển:

- **Envelope sender** được cung cấp trong lệnh **MAIL FROM**.
- **Envelope recipients** được cung cấp lần lượt trong những lệnh **RCPT TO**.

Phong bì quyết định SMTP server đang được yêu cầu xử lý thư cho những người nhận nào. Thông tin phong bì **không phải chính các dòng From, To hoặc Cc nằm bên trong DATA**.

Một email có thể hiện To: lan@example.net nhưng phong bì lại chứa nhiều địa chỉ, bao gồm địa chỉ Bcc, địa chỉ danh sách phân phối hoặc một địa chỉ khác theo quy trình chuyển tiếp. SMTP server phải xử lý các lệnh envelope để biết địa chỉ cần chuyển phát; không chỉ dựa vào việc đọc header To.

### 2.3. SMTP transaction: một lần giao thư cho tập người nhận

Một giao dịch gửi thư SMTP thường có cấu trúc:

~~~text
MAIL FROM  -> đặt envelope sender, bắt đầu giao dịch
RCPT TO    -> thêm người nhận thứ nhất
RCPT TO    -> thêm người nhận thứ hai
RCPT TO    -> thêm người nhận thứ ba
DATA       -> bắt đầu truyền thông điệp chung
...        -> header và body
.          -> kết thúc dữ liệu, chờ phản hồi cuối
~~~

Nhiều giao dịch có thể diễn ra nối tiếp trên **cùng một kết nối SMTP**. Vì vậy:

- **Một kết nối SMTP** không nhất thiết bằng **một message**.
- **Một giao dịch SMTP** có thể gồm **nhiều RCPT TO**.
- **Một lệnh RCPT TO** thông thường khai báo **một đường dẫn người nhận**, không phải chuỗi nhiều địa chỉ ngăn cách bằng dấu phẩy.
- **Một lần DATA** truyền nội dung dùng chung cho những envelope recipients đã được nhận vào giao dịch đó.

Nếu muốn gửi cùng nội dung hai lần độc lập, client có thể thực hiện hai giao dịch MAIL FROM/RCPT TO/DATA riêng, dù vẫn tái sử dụng kết nối.

## 3. Luồng SMTP đầy đủ với nhiều RCPT TO

Ví dụ tiếp theo mô phỏng trao đổi giữa client **C** và server **S**. Nó cố ý không hiển thị bước STARTTLS/AUTH để dễ tập trung vào giao dịch; ứng dụng thực tế phải sử dụng kênh bảo mật và xác thực theo yêu cầu của nhà cung cấp.

~~~text
S: 220 smtp.example.org ESMTP ready

C: EHLO app.example.org
S: 250-smtp.example.org
S: 250 SIZE 52428800

C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<minh@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>

C: From: notify@example.org
C: To: lan@example.net
C: Cc: minh@example.net
C: Subject: Thông báo bảo trì
C:
C: Hệ thống sẽ bảo trì lúc 22:00.
C: Vui lòng lưu công việc trước thời điểm này.
C: .

S: 250 2.0.0 Queued as Q12345

C: QUIT
S: 221 Bye
~~~

Trong bản ghi giao thức trên, ký hiệu **C:** và **S:** chỉ dùng để phân biệt hai chiều trao đổi, không phải các byte thực sự gửi trong phiên SMTP.

| Bước | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| EHLO | Client giới thiệu bản thân và nhận danh sách tính năng mà server công bố | STARTTLS, AUTH, PIPELINING, SIZE và các extension phụ thuộc server |
| MAIL FROM | Bắt đầu giao dịch và chỉ định envelope sender | Không đồng nhất với header From hiển thị |
| RCPT TO lần 1 | Đề nghị server nhận thư cho Lan | Server phản hồi riêng cho địa chỉ này |
| RCPT TO lần 2 | Đề nghị nhận thư cho Minh | Không làm phát sinh DATA riêng |
| RCPT TO lần 3 | Đề nghị nhận thư cho bộ phận giám sát | Địa chỉ Bcc vẫn là một recipient của phong bì |
| DATA | Yêu cầu chuyển sang chế độ gửi nội dung thư | Server thường trả mã 354 khi sẵn sàng nhận dữ liệu |
| Header + body + dấu chấm kết thúc | Truyền nội dung message theo quy tắc SMTP | Một DATA phục vụ tập người nhận đã chấp nhận |
| 250 sau DATA | Server báo đã chấp nhận thông điệp để xử lý tiếp | Chưa chứng minh thư đã xuất hiện trong inbox hay được đọc |
| QUIT | Đóng phiên SMTP | Không phải lệnh bắt buộc ngay sau mỗi giao dịch |

### Tại sao cần lặp RCPT TO mà không lặp DATA?

Thông điệp thông thường có phần header và body chung. SMTP cho phép server biết trước các địa chỉ cần nhận qua một tập lệnh **RCPT TO**, rồi chỉ nhận nội dung thư một lần.

Một cách hình dung:

~~~text
                MAIL FROM:<notify@example.org>
                             |
                +------------+------------+
                |            |            |
         RCPT TO Lan   RCPT TO Minh   RCPT TO Audit
                |            |            |
                +------------+------------+
                             |
                         DATA một lần
                             |
                    Thông điệp chung
                             |
                 Server xử lý chuyển phát
                      đến từng địa chỉ
~~~

Cách này giảm số lần client phải truyền lại cùng một nội dung, đặc biệt khi nội dung lớn. Tuy nhiên, server có thể giới hạn số recipient trong một transaction, từ chối một số địa chỉ hoặc tự chia việc xử lý thành nhiều lượt gửi ở hạ tầng bên trong.

### Khi nào DATA được phép bắt đầu?

Client gửi **DATA** sau khi nhận được các phản hồi cho những lệnh RCPT TO theo chế độ làm việc của phiên. Khi có ít nhất một recipient được chấp nhận, client có thể tiếp tục chuyển thông điệp cho các địa chỉ đã được chấp nhận, tùy chính sách client/thư viện. Nếu không có recipient nào được chấp nhận, không thể dựa vào giao dịch đó để chuyển thư; client thường hủy hoặc kết thúc giao dịch phù hợp.

Máy chủ báo **354** để yêu cầu client truyền dữ liệu. Sau khi dữ liệu kết thúc bằng dấu chấm trên một dòng riêng, server mới đưa ra phản hồi tiếp nhận cuối cho thông điệp. **354 không có nghĩa là đã gửi thành công**; nó chỉ báo server sẵn sàng nhận DATA.

### Dấu chấm kết thúc và dot-stuffing

SMTP phân định kết thúc nội dung bằng chuỗi **CRLF . CRLF**. Nếu một dòng nội dung thực sự bắt đầu bằng dấu chấm, client phải thêm một dấu chấm khi truyền trên wire (dot-stuffing), để server không nhầm đó là ký hiệu kết thúc. Thư viện gửi email xử lý chi tiết này; lập trình viên Spring Mail không tự chèn dấu chấm vào phần thân khi tạo **SimpleMailMessage** hoặc **MimeMessage**.

## 4. Một RCPT TO là một người nhận của phong bì

Trong SMTP, cách khai báo nhiều người nhận là lặp lệnh:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>
~~~

Không viết kiểu sau như một lệnh RCPT TO chuẩn chứa hai mailbox:

~~~text
RCPT TO:<lan@example.net>,<minh@example.net>
~~~

Dấu phẩy có thể xuất hiện trong danh sách địa chỉ của **header To** hoặc **Cc** theo cú pháp header, nhưng mỗi lệnh **RCPT TO** nhận một recipient path theo cú pháp giao thức SMTP.

Địa chỉ trong lệnh RCPT TO cũng không đồng nghĩa với số người cuối cùng nhận được thư. Một địa chỉ có thể là:

- Mailbox cá nhân.
- Alias được máy chủ định tuyến đến mailbox khác.
- Địa chỉ nhóm/danh sách phân phối được mở rộng bởi hệ thống email.
- Địa chỉ trung gian được chuyển tiếp theo quy tắc của nhà cung cấp.

Ví dụ, chỉ một lệnh RCPT TO gửi tới nhóm@example.net có thể khiến hạ tầng phía sau phát thư cho nhiều thành viên nhóm. Ngược lại, ba lệnh RCPT TO không bảo đảm có ba người nhận cuối cùng khác nhau, vì quy tắc alias/chuyển tiếp hoặc loại bỏ trùng lặp phụ thuộc hệ thống.

## 5. To, Cc, Bcc là header hoặc khái niệm hiển thị; RCPT TO là hành động vận chuyển

Đây là phần dễ gây nhầm lẫn khi làm việc với JavaMailSender.

| Thành phần | Nằm ở đâu? | Vai trò | Có thể nhìn thấy với người nhận thông thường? |
| --- | --- | --- | --- |
| **MAIL FROM** | SMTP envelope | Địa chỉ gửi phục vụ vận chuyển/báo lỗi chuyển phát | Thường không hiển thị giống header From; có thể phản ánh trong Return-Path sau chuyển phát |
| **RCPT TO** | SMTP envelope | Chỉ định từng người nhận mà server được yêu cầu chuyển thư tới | Không phải một dòng header hiển thị trực tiếp trong message |
| **From** | Header trong DATA | Danh tính người gửi được trình bày với người đọc | Có |
| **To** | Header trong DATA | Người nhận chính được công bố | Thường có |
| **Cc** | Header trong DATA | Người nhận được sao chép và công bố | Thường có |
| **Bcc** | Khái niệm gửi bản sao ẩn | Người nhận vẫn được giao thư qua envelope, nhưng không bị công bố trong header To/Cc | Thường được loại bỏ khỏi header của thư gửi đi |

### 5.1. To và Cc đều trở thành envelope recipients

Nếu Java tạo:

~~~text
To: lan@example.net
Cc: minh@example.net
~~~

thì khi gửi thông thường, cả Lan và Minh đều cần được khai báo để SMTP server xử lý, chẳng hạn:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
~~~

Server **không phân biệt quyền ưu tiên chuyển phát** chỉ dựa trên việc người nhận nằm trong To hay Cc. Việc ai là người nhận chính hoặc được sao chép là ngữ nghĩa của header và ứng dụng.

### 5.2. Bcc vẫn phải được chuyển phát nhưng không lộ trong danh sách công khai

Nếu ứng dụng gửi thêm cho **audit@example.net** dưới dạng Bcc, SMTP client vẫn phải đưa địa chỉ đó vào tập recipient bằng **RCPT TO** hoặc cơ chế tương đương của nhà cung cấp.

Thông điệp gửi đi thông thường sẽ không có dòng Bcc công khai:

~~~text
From: notify@example.org
To: lan@example.net
Cc: minh@example.net
Subject: Thông báo bảo trì
~~~

Người đọc To/Cc không thể kết luận từ các header trên rằng không có recipient nào khác. Việc bảo vệ Bcc phụ thuộc client/library loại bỏ hoặc xử lý header Bcc đúng cách; không nên tự xây dựng chuỗi header thủ công rồi gửi nguyên trường Bcc như nội dung công khai.

**Bcc bảo vệ danh sách recipient ở tầng hiển thị header**, không phải công cụ bảo đảm ẩn danh tuyệt đối trong mọi tình huống. Hệ thống email vẫn có thể ghi thông tin định tuyến trong log hoặc metadata phục vụ vận hành; người nhận Bcc cũng có thể tự tiết lộ mình khi bấm Reply All.

### 5.3. Header To không phải nguồn sự thật về số người nhận

Có thể tạo thông điệp với:

~~~text
To: lan@example.net, minh@example.net
~~~

nhưng phong bì chỉ chứa **RCPT TO:<lan@example.net>**. Nếu không có yêu cầu chuyển phát riêng đến Minh, dòng To không tự khiến SMTP server bắt buộc phải gửi thư cho Minh.

Ngược lại, phong bì có thể có một địa chỉ Bcc hoàn toàn không xuất hiện trong header.

Vì vậy, khi kiểm tra “thư được yêu cầu gửi tới ai”, cần phân biệt:

1. **Danh sách address trong đối tượng thư** mà ứng dụng đưa cho thư viện.
2. **Các lệnh RCPT TO thực sự gửi đi** và phản hồi của SMTP server.
3. **Kết quả chuyển phát cuối cùng** từ hạ tầng email.

Ba tập dữ liệu trên có thể khác nhau.

### 5.4. MAIL FROM cũng không nhất thiết giống From

Một ứng dụng có thể hiển thị:

~~~text
From: notifications@example.org
~~~

trong khi phong bì sử dụng một địa chỉ khác để nhận thông báo lỗi chuyển phát:

~~~text
MAIL FROM:<bounces@example.org>
~~~

Địa chỉ phong bì thường liên quan đến cơ chế trả lỗi/return path. Việc xác thực miền gửi, SPF, DKIM, DMARC và chính sách của nhà cung cấp có thể áp đặt những ràng buộc lên các danh tính này. Không nên tự sửa envelope sender chỉ để che giấu nguồn phát thư hoặc bỏ qua yêu cầu của nhà cung cấp.

## 6. Mỗi RCPT TO có phản hồi riêng: không phải tất cả cùng thành công

Một điểm quan trọng khi gửi nhiều người nhận là **SMTP server có thể chấp nhận địa chỉ này và từ chối địa chỉ khác trong cùng giao dịch**.

Ví dụ:

~~~text
C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<minh@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<audit@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

Cùng một thông điệp nhưng kết quả ở bước RCPT là:

| Người nhận | Phản hồi | Diễn giải trong giao dịch hiện tại |
| --- | --- | --- |
| Lan | **250** | Server chấp nhận địa chỉ này ở bước RCPT |
| Minh | **550** | Server từ chối địa chỉ này, thuộc nhóm lỗi vĩnh viễn |
| Audit | **450** | Server từ chối tạm thời; có thể cần thử lại theo chính sách retry |

Một số mã thường gặp:

- **2xx:** phản hồi thành công ở bước hiện tại.
- **4xx:** thất bại tạm thời; có thể thử lại vào thời điểm phù hợp.
- **5xx:** thất bại lâu dài hoặc từ chối theo chính sách; không nên lặp vô hạn với yêu cầu không thay đổi.
- **354:** server chấp nhận chuyển sang giai đoạn nhận DATA, chưa phải kết quả cuối cùng.
- **250 sau DATA:** server chấp nhận thông điệp để xử lý chuyển phát tiếp theo.

Mã cụ thể và phần mô tả đi kèm phụ thuộc server. Chẳng hạn, 550 có thể phản ánh hộp thư không tồn tại hoặc chính sách từ chối, nên không thể chỉ nhìn mã 550 rồi khẳng định chắc chắn một nguyên nhân duy nhất.

### 6.1. Điều gì xảy ra khi chỉ một số recipient được chấp nhận?

Có hai lớp quyết định:

**Lớp SMTP server:** server đã báo chấp nhận hoặc từ chối từng RCPT. Nếu client tiếp tục gửi DATA thành công, thông điệp được chấp nhận cho những recipient hợp lệ trong giao dịch theo ngữ nghĩa của SMTP.

**Lớp SMTP client/thư viện:** client có thể được cấu hình để:

- **Tiếp tục gửi đến người nhận hợp lệ**, đồng thời báo lỗi với những người bị từ chối.
- **Hủy hoặc không hoàn tất giao dịch** nếu có bất kỳ recipient nào bị từ chối, tùy chính sách gửi và khả năng của thư viện.

Hai hành vi này tạo kết quả khác nhau. Không thể nhìn thấy **250** của một RCPT rồi kết luận email đã gửi đến địa chỉ đó: client vẫn phải gửi DATA và server phải chấp nhận giai đoạn đó.

Một ví dụ nhánh tiếp tục:

~~~text
MAIL FROM -> 250
RCPT Lan  -> 250
RCPT Minh -> 550
RCPT Audit-> 450

Client chọn tiếp tục với Lan:
DATA      -> 354
...nội dung...
.         -> 250 queued

Kết quả: Lan đã được server nhận thư để xử lý tiếp;
          Minh và Audit chưa được nhận vào lần giao dịch này.
~~~

Nếu client quyết định không gửi khi có người bị từ chối, nó có thể hủy giao dịch bằng **RSET** rồi xử lý lỗi hoặc thử lại theo chính sách. Vì vậy, không được suy ra hành vi client cụ thể chỉ từ một chuỗi mã RCPT.

### 6.2. Thành công ở RCPT khác thành công ở DATA và khác chuyển phát cuối

Cần phân biệt ba mốc:

1. **RCPT TO trả 250:** server đồng ý nhận địa chỉ làm recipient của giao dịch.
2. **DATA hoàn tất và trả 250:** server nhận nội dung thông điệp, chịu trách nhiệm xử lý tiếp theo ngữ nghĩa của SMTP.
3. **Thư đến mailbox:** hạ tầng email hoàn tất bước phát thư tương ứng. Có thể có chuyển tiếp, trì hoãn, lỗi trả về hoặc lọc của nhà cung cấp trước khi người nhận thực sự thấy thư.

Các lỗi phát sinh sau bước chấp nhận DATA có thể được báo qua thông báo không phát được (bounce/DSN) hoặc kênh trạng thái của dịch vụ email, chứ không nhất thiết nằm trong phản hồi ngay tại thời điểm gửi.

Với SMTP thông thường, phản hồi cuối cho DATA thường áp dụng cho việc server **tiếp nhận thông điệp của giao dịch**, chứ không là báo cáo phát thư độc lập cho từng recipient ở thời điểm sau đó.

## 7. Thực hành trong Spring Framework Mail: một lần send, nhiều địa chỉ

**Spring Mail** cung cấp các API dựng thông điệp và gửi qua transport. Lập trình viên thường khai báo danh sách người nhận; chính thư viện mail bên dưới đảm nhiệm phiên SMTP và các lệnh RCPT TO.

Trong ứng dụng Spring Boot sử dụng SMTP, có thể bổ sung dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ cấu hình bằng **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Trong môi trường thực tế, cấu hình credentials qua biến môi trường hoặc hệ thống secrets, ví dụ **SPRING_MAIL_USERNAME** và **SPRING_MAIL_PASSWORD**, và đối chiếu lại hướng dẫn TLS/authentication của nhà cung cấp. Các tên miền và địa chỉ trong ví dụ chỉ là dữ liệu minh họa.

### 7.1. SimpleMailMessage: nhiều To, Cc, Bcc

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceMailService {

    private final JavaMailSender mailSender;

    public MaintenanceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void notifyMaintenance() {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("notify@example.org");
        message.setTo("lan@example.net");
        message.setCc("minh@example.net");
        message.setBcc("audit@example.net");
        message.setSubject("Thông báo bảo trì");
        message.setText(
                "Hệ thống sẽ bảo trì lúc 22:00.\n"
              + "Vui lòng lưu công việc trước thời điểm này."
        );

        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

- **setTo** chỉ định người nhận chính.
- **setCc** chỉ định người nhận công khai dạng sao chép.
- **setBcc** chỉ định người nhận ẩn.
- **send(message)** yêu cầu thư viện gửi **một đối tượng thông điệp** đến tập người nhận đã khai báo.

Khi sử dụng SMTP transport theo cách thông thường, thư viện gửi sẽ lấy các recipient phù hợp và khai báo chúng với SMTP server qua nhiều lệnh RCPT TO trong một giao dịch, nếu chính sách và khả năng của server cho phép.

**Không cần lập trình viên tự viết ba lệnh RCPT TO** hoặc gọi **send** ba lần chỉ vì có ba người nhận. Việc gọi **send** ba lần có thể tạo ba giao dịch riêng và làm tăng số lần truyền nội dung, khác với ý định gửi một thông báo chung.

Để có nhiều người nhận cùng vai trò, các API hỗ trợ khai báo mảng hoặc nhiều địa chỉ:

~~~java
message.setTo(
        "lan@example.net",
        "minh@example.net"
);

message.setCc(
        "team-lead@example.net",
        "audit@example.net"
);
~~~

Khi đọc mã này, đừng nhầm **setTo** với số lệnh SMTP. Một lần thiết lập tập To có thể dẫn tới nhiều recipient trong envelope.

### 7.2. MimeMessageHelper: dùng chung nguyên tắc cho HTML và attachment

Khi cần MIME/HTML hoặc tệp đính kèm, Spring Mail có **MimeMessageHelper**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlAnnouncementService {

    private final JavaMailSender mailSender;

    public HtmlAnnouncementService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAnnouncement() throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8"
        );

        helper.setFrom("notify@example.org");
        helper.setTo(new String[] {
                "lan@example.net",
                "minh@example.net"
        });
        helper.setBcc("audit@example.net");
        helper.setSubject("Thông báo bảo trì");
        helper.setText(
                "<p>Hệ thống sẽ bảo trì lúc <b>22:00</b>.</p>",
                true
        );

        mailSender.send(message);
    }
}
~~~

Điểm khác biệt của **MimeMessage** là nội dung có thể có nhiều phần MIME, HTML, attachment hoặc inline resource. **Quy tắc envelope vẫn giữ nguyên:** SMTP cần biết ai là recipient qua RCPT TO, còn nội dung được gửi qua DATA.

Lưu ý khi dùng MIME và Bcc: nên để **Jakarta Mail/Spring Mail** quản lý các trường người nhận và định dạng header. Việc tự nối chuỗi các dòng header có thể làm lộ Bcc hoặc tạo thư sai định dạng.

### 7.3. JavaMailSender có trả về một trạng thái thành công cho từng người không?

Phương thức **send** của Spring Mail không phải API theo dõi chuyển phát cuối cùng cho từng địa chỉ. Nếu thư viện phát hiện lỗi ở phiên gửi, nó có thể ném ngoại lệ thuộc họ **MailException**, chẳng hạn **MailSendException**. Tuy nhiên, chỉ dựa vào việc không có ngoại lệ không đủ để khẳng định mọi recipient đã nhận hoặc đọc thư.

Kết quả khi một số RCPT bị từ chối còn phụ thuộc SMTP provider và các tùy chọn gửi của Jakarta Mail. Ví dụ một số triển khai Jakarta Mail hỗ trợ thuộc tính **mail.smtp.sendpartial** để quyết định có tiếp tục gửi cho người nhận hợp lệ khi người nhận khác lỗi hay không. Cần kiểm tra hành vi của phiên bản thư viện và server cụ thể khi triển khai chính sách gửi từng phần; không nên giả định tự động có một báo cáo hoàn chỉnh per-recipient trong mọi trường hợp.

Nếu nghiệp vụ đòi hỏi biết địa chỉ nào đã chấp nhận, địa chỉ nào bị từ chối và địa chỉ nào bị bounce về sau, ứng dụng cần thiết kế **cơ chế thu thập phản hồi và theo dõi trạng thái** phù hợp, có thể qua lỗi SMTP, event/bounce API của nhà cung cấp hoặc hệ thống gửi chuyên dụng.

## 8. Một message nhiều RCPT TO hay nhiều message riêng?

Hai lựa chọn có cùng nhóm người nhận ban đầu nhưng tác động thực tế khác nhau.

### 8.1. Một message gửi chung cho nhiều recipient

~~~text
Giao dịch 1:
MAIL FROM:<notify@example.org>
RCPT TO:<lan@example.net>
RCPT TO:<minh@example.net>
RCPT TO:<audit@example.net>
DATA
Thông báo chung
.
~~~

Đặc điểm:

- Header/body chung cho nhóm recipient trong giao dịch.
- Giảm việc gửi lặp nội dung từ client sang SMTP server.
- Có thể cùng một subject, attachment và thông điệp.
- Cần xử lý trường hợp chấp nhận một phần hoặc server giới hạn số recipient.
- Dễ lộ danh sách công khai nếu đặt nhiều địa chỉ trong To/Cc khi không muốn người nhận nhìn thấy nhau.

### 8.2. Nhiều message, mỗi message một recipient

~~~text
Giao dịch 1:
MAIL FROM:<notify@example.org>
RCPT TO:<lan@example.net>
DATA
Chào Lan, ...
.

Giao dịch 2:
MAIL FROM:<notify@example.org>
RCPT TO:<minh@example.net>
DATA
Chào Minh, ...
.
~~~

Đặc điểm:

- Có thể cá nhân hóa tên, liên kết, ngôn ngữ hoặc attachment của từng thư.
- Dễ gắn một trạng thái gửi nghiệp vụ riêng cho từng địa chỉ.
- Tốn nhiều giao dịch và lượt truyền nội dung hơn.
- Có thể kiểm soát riêng việc retry và chính sách dữ liệu từng recipient.

Một ứng dụng gửi email hàng loạt thường chọn chiến lược nhóm hoặc cá nhân tùy bài toán, chính sách bảo mật, giới hạn dịch vụ và khả năng theo dõi. Đối với thư chứa thông tin riêng, đường dẫn đăng nhập cá nhân hoặc token xác nhận, **không nên dùng cùng một nội dung chung cho tất cả** chỉ để giảm số lượng giao dịch.

### 8.3. Bảng so sánh

| Tiêu chí | Một message, nhiều RCPT TO | Nhiều message hoặc nhiều transaction |
| --- | --- | --- |
| Số lần truyền DATA | Thường một lần trong giao dịch đang xét | Mỗi transaction có DATA riêng |
| Nội dung cho người nhận | Chung | Có thể khác nhau |
| Thông tin cá nhân hóa | Hạn chế | Linh hoạt |
| Tính riêng tư | Phải thiết kế To/Cc/Bcc cẩn thận | Dễ tránh lộ danh sách recipient qua header |
| Lỗi ở RCPT | Có thể chỉ một phần recipient bị từ chối | Có thể xử lý theo từng transaction |
| Khả năng quan sát nghiệp vụ | Cần theo dõi trạng thái từng recipient | Thường dễ gắn từng yêu cầu gửi với từng recipient |
| Ứng dụng phù hợp | Thông báo chung nội bộ hoặc nhóm được phép thấy nhau | OTP, xác minh, tài liệu cá nhân, thông báo cá nhân hóa |

Cùng một nội dung được gửi nhiều lần không bảo đảm “mỗi người một giao dịch” nếu thư viện hoặc API nhà cung cấp áp dụng cơ chế gom nhóm. Khi cần hành vi chính xác, phải đối chiếu hợp đồng của transport hoặc provider.

## 9. Những giới hạn thực tế khi tăng số recipient

Một message có thể có nhiều RCPT TO, nhưng **không có nghĩa là được khai báo vô hạn người nhận**.

### 9.1. Giới hạn số recipient của server

SMTP server có thể quy định giới hạn người nhận cho mỗi message, mỗi phiên gửi, mỗi tài khoản hoặc mỗi khoảng thời gian. Khi vượt ngưỡng, server có thể tạm thời từ chối một số lệnh RCPT TO, trả mã như **452**, hoặc áp dụng chính sách giới hạn khác.

Ví dụ:

~~~text
C: RCPT TO:<user1@example.net>
S: 250 OK
C: RCPT TO:<user2@example.net>
S: 250 OK
C: RCPT TO:<user3@example.net>
S: 452 Too many recipients
~~~

Trong trường hợp này, không được tự ý suy ra con số giới hạn chung cho mọi SMTP server. Cần đọc tài liệu và phản hồi thực tế của dịch vụ đang sử dụng. Một số server yêu cầu client hoàn tất message cho nhóm đã nhận rồi tạo transaction khác cho phần còn lại.

### 9.2. PIPELINING không thay đổi ý nghĩa của RCPT TO

Nếu server công bố extension **PIPELINING**, client có thể gửi một số lệnh liên tiếp mà không chờ phản hồi riêng sau từng lệnh theo những quy tắc của extension. Điều này giảm độ trễ trao đổi.

Tuy nhiên, ở cấp ngữ nghĩa vẫn có **nhiều RCPT TO riêng biệt** và server vẫn cần đưa ra phản hồi tương ứng. PIPELINING không biến nhiều recipient thành một chuỗi địa chỉ trong một lệnh, và không làm cho các phản hồi của từng recipient mất ý nghĩa.

### 9.3. Một DATA lớn vẫn phải tuân theo giới hạn kích thước

Nếu thư có attachment lớn, một DATA phục vụ nhiều người nhận có thể giúp giảm dữ liệu truyền từ client. Nhưng server vẫn có giới hạn kích thước message, ví dụ công bố qua extension **SIZE**. Nhiều người nhận không làm tăng kích thước DATA theo cấp số nhân ở đầu gửi, nhưng cũng không miễn trừ bất kỳ giới hạn message size, quota hoặc lọc nội dung nào.

### 9.4. Tách lô khi gửi số lượng lớn

Nếu cần gửi cho nhiều địa chỉ, ứng dụng có thể chia thành các nhóm nhỏ phù hợp hạn mức dịch vụ. Khi tách lô, mỗi nhóm thường là một giao dịch SMTP riêng; từng nhóm có thể gặp lỗi hoặc được chấp nhận tại các thời điểm khác nhau.

Thiết kế ứng dụng nên lưu:

- Danh sách recipient dự định gửi.
- Mã thông điệp hoặc mã sự kiện nghiệp vụ.
- Những recipient đã được transport hoặc provider chấp nhận.
- Những recipient bị từ chối tạm thời, vĩnh viễn hoặc chưa rõ kết quả.
- Thông tin retry và phản hồi phát thư về sau nếu có.

Không nên cập nhật tất cả recipient thành trạng thái **Đã gửi** chỉ vì đối tượng message ban đầu có nhiều địa chỉ và phương thức gửi đã được gọi.

## 10. Xử lý retry mà không gửi trùng một cách vô ý

Giả sử server chấp nhận thông điệp cho Lan và Minh, nhưng kết nối bị đứt trước khi client nhận được phản hồi **250 sau DATA**. Phía client có thể không biết chắc server đã nhận thông điệp hay chưa. Nếu tự động gửi lại toàn bộ tập recipient, có thể phát sinh thư trùng.

SMTP không cung cấp cho ứng dụng một bảo đảm tổng quát rằng mỗi thông điệp đến chính xác một lần cho mỗi người nhận.

Các nguyên tắc thiết kế hữu ích:

1. **Phân biệt kết quả đã biết và chưa biết:** phản hồi RCPT/ DATA đã nhận được khác với việc mất kết nối trước khi nhận phản hồi.
2. **Ghi nhận trạng thái theo recipient:** tránh gộp toàn bộ nhóm thành một trạng thái đơn giản.
3. **Retry có chọn lọc:** các recipient bị từ chối tạm thời có thể được thử lại theo backoff; recipient bị từ chối vĩnh viễn cần xem nguyên nhân trước khi thử lại.
4. **Không coi mã 250 là chứng cứ người nhận đã đọc:** vẫn có thể có bounce hoặc lọc ở hạ tầng phía sau.
5. **Có mã liên kết nghiệp vụ:** sử dụng mã sự kiện/đợt gửi để đối chiếu log và phản hồi dịch vụ. Header Message-ID hữu ích để tìm thư nhưng tự nó không tạo ra tính idempotent của SMTP.
6. **Giới hạn việc gửi lại:** áp dụng hàng đợi bền vững, trạng thái xử lý và chính sách retry; nếu provider hỗ trợ cơ chế idempotency riêng thì sử dụng đúng hợp đồng của họ.

Ví dụ với ba recipient:

~~~text
recipient                 trạng thái đã biết tại ứng dụng
--------------------------------------------------------
lan@example.net           DATA accepted (nếu có phản hồi)
minh@example.net          RCPT rejected: 550
audit@example.net         RCPT temp rejected: 450
~~~

Ứng dụng có thể đưa Audit vào danh sách retry, xử lý lý do từ chối của Minh, và không gửi lại Lan chỉ vì Audit lỗi. Nhưng nếu kết quả của Lan thực sự chưa xác định do mất kết nối, thiết kế phải có chính sách giải quyết tình huống không chắc chắn và chấp nhận rằng vẫn có nguy cơ nhận trùng.

## 11. Quan sát thực tế: nên tìm điều gì trong log SMTP?

Trong môi trường phát triển hoặc hệ thống SMTP thử nghiệm, bản ghi hội thoại giao thức có thể giúp hiểu tại sao một message gồm nhiều recipient. Nếu cần xem ở tầng giao thức, hãy nhận diện:

~~~text
MAIL FROM: ...
RCPT TO: ...
RCPT TO: ...
RCPT TO: ...
DATA
354 ...
...
250 ...
~~~

Lưu ý về cách đọc log:

- **Bao nhiêu RCPT TO?** Đây là số lệnh khai báo recipient ở transaction được quan sát, chưa chắc là tổng số người cuối cùng nhận được sau alias/list expansion.
- **Mỗi RCPT nhận phản hồi gì?** 250 ở RCPT khác với 250 sau DATA.
- **Có DATA hay client đã hủy?** Một RCPT trả 250 chưa đủ để kết luận đã có thư được chuyển giao.
- **Có transaction mới không?** Lệnh MAIL FROM tiếp theo có thể bắt đầu một message mới trong cùng kết nối.
- **Bcc có xuất hiện trong header không?** Trong luồng gửi thông thường, địa chỉ Bcc nên xuất hiện qua envelope nhưng không bị công bố trong header của thư nhận.

SMTP debug log có thể chứa địa chỉ, metadata và đôi khi nội dung nhạy cảm hoặc thông tin xác thực nếu cấu hình ghi log thiếu an toàn. Chỉ bật chế độ debug khi cần, bảo vệ log, che dữ liệu nhạy cảm và vô hiệu hóa sau khi chẩn đoán.

### Các hiểu nhầm thường gặp

**Hiểu nhầm 1: “Một email có ba người nhận thì phải gọi send ba lần.”**

Không nhất thiết. Một transaction SMTP có thể khai báo ba RCPT TO và dùng chung một DATA.

**Hiểu nhầm 2: “Thêm ba địa chỉ trong header To nghĩa là server sẽ gửi cho cả ba.”**

Không. Server được yêu cầu chuyển phát thông qua envelope recipients; các header To/Cc có ngữ nghĩa hiển thị riêng.

**Hiểu nhầm 3: “Bcc không có trong header thì không có người nhận Bcc.”**

Không. Recipient Bcc cần được khai báo trong envelope dù danh tính không công khai trong header người nhận thấy.

**Hiểu nhầm 4: “Nếu một RCPT bị lỗi thì mọi recipient đều thất bại.”**

Không thể kết luận như vậy. SMTP phản hồi riêng từng RCPT; client quyết định có hoàn tất gửi cho tập hợp lệ hay hủy giao dịch, tùy cấu hình và chính sách.

**Hiểu nhầm 5: “SMTP server trả 250 nên mọi người nhận đều đọc được thư.”**

Không. 250 là chấp nhận ở một giai đoạn giao thức; chuyển phát cuối và hành vi đọc thư là những kết quả khác.

**Hiểu nhầm 6: “Có thể đặt danh sách địa chỉ phân cách dấu phẩy vào một RCPT TO.”**

Không đúng cú pháp RCPT TO thông thường. Dùng một lệnh cho mỗi recipient path hoặc để thư viện gửi email xử lý danh sách địa chỉ.

## 12. Đặt kiến thức vào đúng ngữ cảnh Spring Framework Mail

Khi viết chức năng gửi một thông báo đến nhiều người trong ứng dụng Spring, quy trình tư duy có thể là:

~~~text
Đầu vào nghiệp vụ
    |
    v
Xác định nhóm người nhận và quyền hiển thị địa chỉ
    |
    +--> To/Cc: có thể công khai trong message header
    |
    +--> Bcc: cần gửi nhưng không công khai trong header
    |
    v
Tạo SimpleMailMessage hoặc MimeMessage
    |
    v
JavaMailSender.send(...)
    |
    v
Jakarta Mail / SMTP transport
    |
    +--> MAIL FROM
    +--> RCPT TO cho recipient 1
    +--> RCPT TO cho recipient 2
    +--> RCPT TO cho recipient N
    +--> DATA chứa nội dung chung
    |
    v
SMTP server chấp nhận/từ chối theo từng bước
    |
    v
Theo dõi kết quả gửi và chuyển phát theo yêu cầu ứng dụng
~~~

Với thông báo chung, một message nhiều recipient là lựa chọn tự nhiên. Với nội dung cá nhân hóa hoặc yêu cầu tách biệt quyền xem thông tin, cần cân nhắc tạo message riêng theo từng người. Trong cả hai trường hợp, Spring Mail giúp dựng và gửi thông điệp, còn việc server nhận, từ chối, trì hoãn hoặc chuyển phát phải được hiểu theo các mốc SMTP tương ứng.

Một message nhiều người nhận chính là ví dụ điển hình cho ranh giới giữa **nội dung thư** và **phong bì vận chuyển**: **một DATA có thể phục vụ nhiều lệnh RCPT TO**, mỗi RCPT được kiểm tra riêng, và kết quả chấp nhận message chỉ là một bước trong quá trình chuyển phát email.
