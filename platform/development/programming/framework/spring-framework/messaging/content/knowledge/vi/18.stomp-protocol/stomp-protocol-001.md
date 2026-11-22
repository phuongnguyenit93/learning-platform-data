# Cấu trúc STOMP frame: lệnh, header và body

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả cấu trúc wire-format của một STOMP frame theo STOMP 1.2.
- Phân biệt command, header section, body và byte kết thúc NUL.
- Đọc các frame CONNECT, CONNECTED, SEND, SUBSCRIBE, MESSAGE, ACK, RECEIPT và ERROR.
- Hiểu cách dùng content-length, content-type và cách đếm byte của body.
- Mã hóa và giải mã header value theo quy tắc escape của STOMP 1.2.
- Xử lý header lặp, heartbeat và nhiều frame trên cùng một kết nối stream.
- Phân biệt frame STOMP với WebSocket frame và Spring Message.
- Theo dõi cách Spring WebSocket/STOMP chuyển frame thành message nội bộ.
- Tạo một SEND frame đúng định dạng bằng Java 17 và UTF-8.

## 1. STOMP là gì?

STOMP là viết tắt của Simple Text Oriented Messaging Protocol. Đây là giao thức messaging nhẹ, dùng các frame để trao đổi dữ liệu giữa client và message server/broker. STOMP có thể chạy trên một kết nối hai chiều đáng tin cậy như TCP hoặc WebSocket.

STOMP được thiết kế để dễ triển khai trên nhiều ngôn ngữ và nền tảng. Một client có thể gửi message bằng frame SEND, đăng ký nhận message bằng SUBSCRIBE, rồi nhận dữ liệu từ server qua frame MESSAGE.

STOMP là giao thức ở tầng wire-format. Nó quy định cấu trúc frame và các command phổ biến, nhưng để broker quyết định ý nghĩa của destination, cách lưu trữ, phân phối, retry và độ bền của message. Ví dụ, tên /queue/orders hoặc /topic/orders là quy ước phổ biến, nhưng cú pháp và semantics cụ thể phụ thuộc STOMP server.

Bài này tập trung vào STOMP 1.2. Khi làm việc với broker hoặc client cụ thể, cần kiểm tra phiên bản STOMP mà hai phía thương lượng được và các extension riêng của server.

## 2. Cấu trúc tổng quát của một STOMP frame

Một frame có bốn phần theo thứ tự:

1. Command: tên hành động, ví dụ SEND hoặc SUBSCRIBE.
2. Header section: không hoặc nhiều dòng key:value.
3. Dòng trống: đánh dấu kết thúc header và bắt đầu body.
4. Body: dữ liệu message, theo sau là byte NUL kết thúc frame.

Dạng tổng quát:

~~~text
COMMAND
header1:value1
header2:value2

Body^@
~~~

Trong ví dụ, ký hiệu ^@ biểu diễn một byte NUL có giá trị 0x00. Đây là ký hiệu minh họa trong tài liệu, không phải hai ký tự dấu mũ và chữ @ được gửi lên mạng.

Một frame SEND thực tế:

~~~text
SEND
destination:/queue/orders
content-type:text/plain
content-length:9

Xin chào^@
~~~

Frame trên có:

- Command là SEND.
- Header destination chỉ ra đích nhận.
- Header content-type mô tả định dạng body.
- Header content-length cho biết body dài 9 byte UTF-8.
- Dòng trống phân cách header và body.
- Body là chuỗi Xin chào.
- Byte NUL kết thúc frame.

Frame không phải một dòng text đơn lẻ. Nó là chuỗi byte có cấu trúc. Một kết nối có thể mang nhiều frame nối tiếp nhau.

## 3. Command line và EOL

Command nằm ở dòng đầu tiên của frame. Command được kết thúc bằng EOL (end-of-line).

Trong STOMP 1.2, EOL là:

- LF: byte line feed, giá trị 10.
- CRLF: byte carriage return 13 theo sau bởi line feed 10.

STOMP 1.2 cho phép cả LF và CRLF. LF là dạng thường thấy trong các ví dụ và client đơn giản.

Ví dụ:

~~~text
SEND\n
destination:/queue/orders\n
\n
hello^@
~~~

Ở đây \n biểu diễn byte LF. Trong wire-format thực tế, các dấu backslash và chữ n không xuất hiện; chúng chỉ giúp minh họa xuống dòng.

Command và header name phân biệt chữ hoa/chữ thường. SEND và send không phải cùng một command. destination và Destination cũng là hai header name khác nhau.

Một parser không được tự ý đổi command sang chữ thường hoặc viết hoa, vì điều đó làm thay đổi ý nghĩa frame.

## 4. Header section

Sau command là zero hoặc nhiều header line. Mỗi header có cấu trúc:

~~~text
key:value
~~~

Dấu hai chấm đầu tiên phân tách tên header và giá trị. Mỗi header line kết thúc bằng EOL.

Ví dụ:

~~~text
SEND
destination:/queue/orders
content-type:application/json
content-length:10
receipt:send-186

{"id":186}^@
~~~

Các header có thể mang thông tin điều khiển giao thức hoặc metadata của message.

Header thường gặp:

| Header | Ý nghĩa |
|---|---|
| destination | Destination mà SEND hoặc SUBSCRIBE nhắm tới |
| content-type | MIME type của body |
| content-length | Số byte của body |
| receipt | Yêu cầu server gửi RECEIPT khi xử lý frame |
| id | ID subscription hoặc transaction tùy command |
| ack | Chế độ acknowledgement của subscription |
| transaction | ID transaction STOMP |
| message-id | ID message do server cung cấp trong MESSAGE |
| subscription | ID subscription nhận được MESSAGE |
| ack (trong MESSAGE) | Token dùng cho ACK/NACK khi subscription yêu cầu xác nhận |
| receipt-id | Giá trị receipt tương ứng trong RECEIPT |

Một header có thể là header chuẩn của STOMP hoặc header do ứng dụng/broker định nghĩa. Header tùy chỉnh thường được dùng để truyền correlation ID, event type, tenant hoặc metadata phục vụ lọc message.

### 4.1. Dòng trống kết thúc header

Một dòng EOL trống đánh dấu ranh giới giữa header và body.

Ví dụ:

~~~text
SEND
destination:/queue/a
content-type:text/plain

hello^@
~~~

Dòng trống sau content-type không phải một header rỗng. Nó là dấu phân cách bắt buộc giữa header section và body.

Nếu không có header nào, frame vẫn có command line rồi một EOL trống:

~~~text
DISCONNECT

^@
~~~

Một parser phải nhận ra dòng trống này trước khi đọc body. Nếu nhầm nó là body, parser sẽ lệch vị trí và có thể không giải mã được frame tiếp theo.

### 4.2. Không tự trim header value

Theo STOMP 1.2, client và server không được tự ý trim hoặc thêm khoảng trắng ở đầu/cuối header. Khoảng trắng có thể là một phần giá trị do ứng dụng gửi.

Ví dụ, giá trị:

~~~text
x-label:  urgent  
~~~

có hai dấu cách ở đầu và cuối giá trị. Parser không được tự xóa chúng.

Nếu ứng dụng muốn chuẩn hóa giá trị, hãy làm ở tầng nghiệp vụ sau khi frame đã được giải mã, không thay đổi wire-format.

### 4.3. Header lặp

STOMP 1.2 cho phép frame có nhiều header cùng tên. Khi nhận các header trùng, client/server SHOULD dùng giá trị của header xuất hiện đầu tiên. Các giá trị sau có thể được giữ như lịch sử thay đổi hoặc bị bỏ qua.

Ví dụ:

~~~text
MESSAGE
foo:World
foo:Hello

^@
~~~

Theo quy tắc STOMP 1.2, giá trị foo được dùng là World.

Điểm này quan trọng khi broker thêm header hoặc cập nhật metadata trong topology store-and-forward. Ứng dụng không nên giả định header trùng luôn được gộp thành một danh sách hoặc giá trị cuối cùng sẽ thắng.

Nếu một header cần có nhiều giá trị, hãy dùng quy ước rõ ràng ở tầng ứng dụng hoặc một header có định dạng phù hợp, thay vì dựa vào hành vi riêng của broker.

## 5. Header escaping trong STOMP 1.2

Header value không thể chứa trực tiếp một số ký tự phân cách của frame như CR, LF và dấu hai chấm. STOMP 1.2 dùng escape sequence để biểu diễn chúng.

Với các frame thông thường, quy tắc escape là:

| Ký tự gốc | Dạng trên wire |
|---|---|
| Backslash \ | \\ |
| Carriage return | \r |
| Line feed | \n |
| Colon : | \c |

Ví dụ giá trị header gốc:

~~~text
line1:ok
line2\done
~~~

Khi encode thành header value:

~~~text
note:line1\cok\nline2\\done
~~~

Khi decode, parser đảo ngược các escape sequence để khôi phục giá trị gốc.

Các escape sequence không được định nghĩa, ví dụ \t, là lỗi giao thức trong STOMP 1.2 và phải được xử lý như protocol error.

Có ngoại lệ tương thích: CONNECT và CONNECTED không áp dụng quy tắc escape cho CR, LF và colon theo cách các frame khác áp dụng. Điều này nhằm duy trì tương thích với STOMP 1.0. Khi viết encoder/decoder, hãy xử lý đúng loại frame và phiên bản giao thức.

Quy tắc thực hành:

- Khi encode, escape backslash trước, sau đó mới escape CR, LF và colon.
- Khi decode, chỉ chấp nhận các escape sequence được STOMP 1.2 định nghĩa.
- Không trim khoảng trắng trong header.
- Không tự escape body; quy tắc này áp dụng cho header section.

Nếu escape backslash sau cùng, một backslash vừa được tạo bởi quá trình encode có thể bị escape lần nữa và làm sai giá trị.

## 6. Body section

Body bắt đầu ngay sau dòng EOL trống và kết thúc bằng byte NUL (0x00).

Chỉ ba loại frame trong STOMP 1.2 được phép có body:

- SEND: client gửi nội dung message.
- MESSAGE: server chuyển message tới subscriber.
- ERROR: server có thể gửi nội dung giải thích lỗi.

Các frame khác như CONNECT, CONNECTED, SUBSCRIBE, ACK, RECEIPT và DISCONNECT không được có body theo đặc tả.

Body có thể là text hoặc binary. STOMP có định hướng text, nhưng payload không bắt buộc là văn bản thuần.

Ví dụ body JSON:

~~~text
SEND
destination:/queue/trade
content-type:application/json

{"action":"BUY","ticker":"MMM"}^@
~~~

Ví dụ body nhị phân có thể chứa byte NUL ở giữa. Khi đó parser không thể dùng byte NUL đầu tiên làm dấu kết thúc; phải có content-length để biết chính xác số byte body.

## 7. content-length: đếm byte, không đếm ký tự

content-length là độ dài body tính bằng octet (byte), không phải số ký tự, không phải số code point và cũng không nhất thiết bằng String.length() trong Java.

Với body UTF-8 có ký tự ngoài ASCII, số byte có thể khác số ký tự.

Ví dụ body:

~~~text
Xin chào
~~~

Trong Java:

- String.length() trả về 8 UTF-16 code units.
- UTF-8 encoding tạo ra 9 byte.
- Vì vậy content-length phải là 9.

Ví dụ frame:

~~~text
SEND
destination:/queue/a
content-type:text/plain;charset=UTF-8
content-length:9

Xin chào^@
~~~

Nếu body có byte NUL bên trong, content-length là bắt buộc. Parser phải đọc đúng số byte được khai báo, sau đó vẫn phải đọc byte NUL kết thúc frame.

Nếu content-length không có, parser tìm byte NUL đầu tiên để xác định kết thúc body. Cách này không dùng được khi payload có byte NUL.

### 7.1. content-type

Khi frame có body, SEND, MESSAGE và ERROR SHOULD gửi content-type để receiver biết cách diễn giải payload.

content-type là MIME type, ví dụ:

- text/plain
- application/json
- application/xml
- application/octet-stream

Với nội dung văn bản, UTF-8 được khuyến nghị để tăng khả năng tương thích. Nếu dùng charset khác, khai báo rõ trong MIME type, ví dụ text/plain;charset=UTF-16.

Nếu content-type không có, receiver nên xem body như binary blob theo đặc tả.

### 7.2. Không tính byte NUL vào content-length

content-length chỉ đếm các byte của body. Byte NUL kết thúc frame nằm sau body và không được tính vào giá trị content-length.

Ví dụ:

~~~text
content-length:3

abc^@
~~~

Body dài 3 byte: a, b, c. Byte NUL là byte thứ tư sau dòng trống, dùng để kết thúc frame.

## 8. Kết thúc frame bằng NUL

Byte NUL có giá trị 0x00 là dấu kết thúc frame. Sau NUL, đặc tả cho phép có thêm zero hoặc nhiều EOL.

Ký hiệu ^@ trong tài liệu đại diện byte NUL. Không gửi hai ký tự ^ và @.

Các frame có thể được nối liên tiếp trên cùng một kết nối:

~~~text
SEND
destination:/queue/a

first^@SEND
destination:/queue/a

second^@
~~~

Trong ví dụ, sau byte NUL của frame thứ nhất, frame thứ hai bắt đầu ngay bằng command SEND. Có thể có EOL bổ sung sau NUL, nhưng parser phải bỏ qua đúng số EOL theo grammar.

NUL là byte phân cách quan trọng. Không dùng newline để kết thúc body vì body có thể chứa nhiều dòng hoặc dữ liệu binary.

## 9. Cách parser đọc một frame

STOMP chạy trên stream hai chiều như TCP. Một lần đọc socket không đảm bảo trả về trọn một frame. Frame có thể bị chia qua nhiều lần đọc; một lần đọc cũng có thể chứa nhiều frame.

Một parser streaming thường làm theo các bước:

1. Đọc command tới EOL.
2. Đọc từng header line tới EOL.
3. Gặp EOL trống thì kết thúc header section.
4. Kiểm tra content-length nếu có.
5. Nếu có content-length, đọc đúng số octet body rồi kiểm tra byte NUL kết thúc.
6. Nếu không có content-length, đọc body tới byte NUL đầu tiên.
7. Bỏ qua EOL bổ sung sau NUL nếu có.
8. Tiếp tục parse frame tiếp theo trong buffer.

Khi body có NUL bên trong, content-length cho parser biết NUL nào thuộc body và NUL nào kết thúc frame.

Parser cũng cần giới hạn:

- Số header trên một frame.
- Độ dài mỗi header line.
- Kích thước body.
- Thời gian chờ frame chưa hoàn chỉnh.
- Số byte buffer được giữ cho một connection.

Đặc tả cho phép server đặt giới hạn kích thước để tránh tiêu thụ bộ nhớ quá mức. Nếu vượt giới hạn, server có thể trả ERROR và đóng connection.

Không viết parser production bằng cách gọi readLine() cho toàn bộ frame rồi ghép body thành String. Cách đó làm hỏng binary payload, không tôn trọng content-length theo byte và có thể đọc nhầm frame tiếp theo.

## 10. Các frame kết nối: CONNECT, STOMP và CONNECTED

Client bắt đầu phiên STOMP bằng CONNECT hoặc STOMP. Server trả CONNECTED nếu chấp nhận.

Ví dụ client:

~~~text
CONNECT
accept-version:1.2
host:broker.example
heart-beat:10000,10000

^@
~~~

Ví dụ server:

~~~text
CONNECTED
version:1.2
heart-beat:10000,10000
session:session-186

^@
~~~

Trong STOMP 1.2, client MUST gửi:

- accept-version: các phiên bản giao thức client hỗ trợ.
- host: tên virtual host mà client muốn kết nối.

Server trả version để xác nhận phiên bản được chọn. Hai bên dùng phiên bản cao nhất mà cả hai cùng hỗ trợ.

Các header tùy chọn thường gặp:

- login: user name.
- passcode: mật khẩu hoặc credential theo cấu hình server.
- heart-beat: tham số heartbeat.
- session: session ID do server cung cấp.
- server: thông tin server.

Không ghi passcode thật vào log hoặc ví dụ production. STOMP frame có thể đi qua mạng; dùng TLS và cơ chế xác thực phù hợp.

STOMP command và header name phân biệt chữ hoa/chữ thường. CONNECT và STOMP là hai command kết nối; server STOMP 1.2 MUST xử lý STOMP tương tự CONNECT.

## 11. Các client command thường gặp

| Command | Mục đích | Header quan trọng |
|---|---|---|
| CONNECT / STOMP | Mở phiên STOMP | accept-version, host |
| SEND | Gửi message | destination |
| SUBSCRIBE | Đăng ký nhận message | destination, id, ack |
| UNSUBSCRIBE | Hủy subscription | id |
| ACK | Xác nhận đã xử lý message | id |
| NACK | Báo message chưa được xử lý | id |
| BEGIN | Bắt đầu transaction STOMP | transaction |
| COMMIT | Commit transaction | transaction |
| ABORT | Rollback transaction | transaction |
| DISCONNECT | Đóng phiên | receipt tùy chọn |

### 11.1. SEND

SEND yêu cầu header destination. Body chứa nội dung gửi tới destination.

~~~text
SEND
destination:/queue/orders
content-type:application/json
content-length:10

{"id":186}^@
~~~

Các header ứng dụng tùy chỉnh có thể được thêm vào SEND. Broker có thể chuyển tiếp các header đó tới MESSAGE frame của subscriber.

Destination được STOMP xem như một chuỗi opaque. Giao thức không quy định tên /queue hay /topic phải có semantics cụ thể. Hãy kiểm tra tài liệu broker.

### 11.2. SUBSCRIBE

SUBSCRIBE đăng ký nhận message từ một destination:

~~~text
SUBSCRIBE
id:orders-sub-1
destination:/queue/orders
ack:client-individual

^@
~~~

id là định danh subscription duy nhất trong cùng connection. Server dùng ID này để liên kết MESSAGE và UNSUBSCRIBE.

Header ack quy định chế độ xác nhận:

- auto: client không gửi ACK; server xem message đã được nhận khi gửi tới client.
- client: ACK có tính cumulative, xác nhận message được chỉ định và các message trước đó trong subscription.
- client-individual: ACK/NACK chỉ áp dụng cho message tương ứng.

Nếu không chỉ định ack, mặc định là auto.

### 11.3. UNSUBSCRIBE

UNSUBSCRIBE cần ID của subscription đã tạo:

~~~text
UNSUBSCRIBE
id:orders-sub-1

^@
~~~

Sau khi server xử lý, connection không còn nhận message qua subscription đó.

### 11.4. ACK và NACK

Khi subscription dùng client hoặc client-individual, MESSAGE có header ack. Client gửi ACK hoặc NACK với giá trị đó:

~~~text
ACK
id:ack-token-186

^@
~~~

~~~text
NACK
id:ack-token-187

^@
~~~

Trong STOMP 1.2, header id của ACK/NACK phải khớp giá trị ack trong MESSAGE, không phải message-id. Có thể thêm transaction để gắn acknowledgement vào transaction STOMP.

NACK báo rằng client chưa xử lý message. Broker có thể giao lại, loại bỏ hoặc đưa vào dead-letter queue; hành vi cụ thể phụ thuộc server.

## 12. Các server frame: CONNECTED, MESSAGE, RECEIPT và ERROR

Server gửi CONNECTED sau khi kết nối thành công. Sau đó server có thể gửi MESSAGE, RECEIPT hoặc ERROR.

### 12.1. MESSAGE

MESSAGE chuyển nội dung tới một subscription:

~~~text
MESSAGE
destination:/queue/orders
message-id:msg-186
subscription:orders-sub-1
content-type:application/json
content-length:10

{"id":186}^@
~~~

Các header bắt buộc:

- destination: destination message được gửi tới.
- message-id: ID duy nhất của message.
- subscription: ID subscription đang nhận message.
- ack: có mặt khi subscription dùng acknowledgement explicit.

Header subscription trong MESSAGE phải khớp ID của SUBSCRIBE tương ứng.

### 12.2. RECEIPT

Client có thể yêu cầu receipt bằng header receipt trên frame client, ngoại trừ CONNECT. Server trả RECEIPT với receipt-id có cùng giá trị.

Ví dụ client gửi:

~~~text
SEND
destination:/queue/orders
receipt:send-186

order-186^@
~~~

Server trả:

~~~text
RECEIPT
receipt-id:send-186

^@
~~~

RECEIPT xác nhận server đã xử lý frame tương ứng ở mức giao thức. Vì STOMP chạy trên stream, receipt cũng là xác nhận tích lũy rằng các frame trước đó đã được server nhận. Tuy nhiên, receipt không có nghĩa message đã được consumer xử lý xong hoặc transaction nghiệp vụ đã commit.

Nếu cần xác nhận nghiệp vụ, ứng dụng phải định nghĩa response/event ở tầng nghiệp vụ.

### 12.3. ERROR

Server có thể gửi ERROR khi frame sai cú pháp, thiếu header bắt buộc hoặc không thể xử lý command.

~~~text
ERROR
message:malformed frame
content-type:text/plain

Missing required destination header^@
~~~

ERROR có thể chứa body mô tả lỗi. Theo STOMP 1.2, server gửi ERROR rồi đóng connection. Client nên đọc lỗi, giải phóng tài nguyên và thực hiện reconnect theo chính sách phù hợp.

Không coi ERROR như một response bình thường mà connection vẫn chắc chắn hoạt động.

## 13. Transaction trong STOMP

STOMP định nghĩa các command BEGIN, COMMIT và ABORT. Transaction ID được dùng trong các frame SEND, ACK và NACK để gắn thao tác vào transaction.

Ví dụ:

~~~text
BEGIN
transaction:tx-186

^@SEND
destination:/queue/orders
transaction:tx-186

order-186^@COMMIT
transaction:tx-186

^@
~~~

Luồng:

1. BEGIN mở transaction tx-186.
2. SEND gắn transaction tx-186.
3. COMMIT xác nhận transaction.
4. ABORT có thể được dùng thay COMMIT để hủy transaction.

Transaction ID phải duy nhất trong cùng connection. Transaction chưa commit sẽ bị abort ngầm nếu client DISCONNECT hoặc TCP connection bị mất.

Transaction STOMP là semantics do broker cung cấp cho các thao tác STOMP được gắn transaction. Nó không tự động bao gồm database transaction trong ứng dụng Spring.

## 14. RECEIPT và DISCONNECT có xác nhận graceful shutdown

Client có thể đóng socket trực tiếp, nhưng khi đó không chắc server đã nhận tất cả frame trước đó.

Để đóng kết nối có xác nhận:

~~~text
DISCONNECT
receipt:close-186

^@
~~~

Client chờ:

~~~text
RECEIPT
receipt-id:close-186

^@
~~~

Sau khi nhận receipt, client đóng socket. Client MUST NOT gửi thêm frame sau DISCONNECT.

Trong thực tế, server có thể đóng socket nhanh và client không nhận được receipt cuối cùng. Client cần timeout cho quá trình graceful shutdown.

## 15. Heartbeat: EOL không phải một frame command

STOMP heartbeat kiểm tra kết nối còn hoạt động hay không. Hai phía thương lượng heartbeat bằng header heart-beat trong CONNECT và CONNECTED.

Ví dụ:

~~~text
CONNECT
accept-version:1.2
host:broker.example
heart-beat:10000,5000

^@
~~~

~~~text
CONNECTED
version:1.2
heart-beat:8000,6000

^@
~~~

Header có hai số:

- Số thứ nhất: khoảng tối thiểu phía gửi có thể gửi dữ liệu ra.
- Số thứ hai: khoảng mà phía gửi mong muốn nhận dữ liệu vào.

Gọi giá trị client là cx,cy và server là sx,sy:

- Client gửi heartbeat cho server mỗi MAX(cx, sy) mili giây nếu cả hai giá trị đều khác 0.
- Server gửi heartbeat cho client mỗi MAX(sx, cy) mili giây nếu cả hai giá trị đều khác 0.

Nếu không có frame nào cần gửi trong khoảng heartbeat, bên gửi gửi một EOL đơn lẻ, thường là LF. EOL này không phải một STOMP frame vì nó không có command, header hoặc NUL terminator.

Bất kỳ dữ liệu nào nhận được trên connection cũng có thể chứng minh peer còn hoạt động. Receiver nên có một khoảng dung sai vì scheduler và mạng có thể gây trễ.

Heartbeat STOMP khác WebSocket Ping/Pong. Heartbeat thuộc STOMP protocol; Ping/Pong thuộc WebSocket transport. Hai cơ chế có thể cùng tồn tại.

## 16. Phân biệt STOMP frame với WebSocket frame và Spring Message

Ba khái niệm này nằm ở các tầng khác nhau:

| Thành phần | Vai trò |
|---|---|
| WebSocket frame/message | Đơn vị dữ liệu ở tầng transport WebSocket |
| STOMP frame | Cấu trúc command, headers, body ở tầng messaging |
| Spring Message | Object nội bộ Spring gồm headers và payload |

Khi dùng Spring WebSocket/STOMP, STOMP frame từ client được decode thành Spring Message và đưa vào clientInboundChannel. Message có destination prefix /app có thể được chuyển tới method @MessageMapping; destination /topic hoặc /queue thường được chuyển tới broker theo cấu hình.

Khi server gửi message qua brokerChannel, broker phân phối cho subscriber phù hợp. Message được chuyển qua clientOutboundChannel, encode thành STOMP frame và gửi về WebSocket client.

Ví dụ cấu hình Spring:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Controller nhận SEND frame đã được Spring chuyển thành message:

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greeting")
    public String handle(String greeting) {
        return "Hello " + greeting;
    }
}
~~~

Client gửi:

~~~text
SEND
destination:/app/greeting
content-type:text/plain

Spring^@
~~~

Client subscribe:

~~~text
SUBSCRIBE
id:greeting-sub
destination:/topic/greeting
ack:auto

^@
~~~

Spring nhận SEND, route tới GreetingController.handle, rồi phát kết quả tới /topic/greeting. Broker gửi MESSAGE frame tới subscriber.

Trong cấu hình này, /app, /topic và /queue là prefix do ứng dụng cấu hình. STOMP specification xem destination như chuỗi opaque; broker khác có thể dùng quy ước khác.

## 17. Các API Spring liên quan tới STOMP header và frame

Spring cung cấp một số API để làm việc với STOMP ở tầng messaging:

- StompHeaderAccessor: truy cập và chỉnh sửa STOMP command/header thông qua Spring Message.
- StompHeaders: biểu diễn tập STOMP header trong các API Spring hỗ trợ.
- StompDecoder: decode byte stream thành message STOMP nội bộ.
- StompEncoder: encode Spring Message thành STOMP frame.
- SimpMessagingTemplate: gửi message tới destination trong mô hình messaging của Spring.
- @MessageMapping: ánh xạ message đến method xử lý trong controller.

Các API này giúp ứng dụng thao tác với metadata và payload mà không phải tự nối chuỗi wire-format cho từng request.

Khi cần debug protocol, có thể xem frame thô ở client hoặc broker log. Khi viết business code trong Spring, thường nên dùng MessageMapping, SimpMessagingTemplate và header accessor.

Không nhầm StompHeaderAccessor với JMS Message headers. STOMP và JMS là hai API/protocol khác nhau, dù broker có thể hỗ trợ cả hai.

## 18. Ví dụ Java 17: tạo SEND frame với body UTF-8 và header escaping

Ví dụ này tạo một STOMP 1.2 SEND frame dưới dạng byte array. Nó minh họa ba chi tiết dễ sai:

- Header value phải escape colon, newline và backslash.
- content-length phải đếm byte UTF-8 của body.
- Frame kết thúc bằng byte NUL.

Tạo file StompFrameBuilderDemo.java:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class StompFrameBuilderDemo {

    private static byte[] encodeSend(
            String destination,
            String contentType,
            String note,
            String body) {

        byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream frame = new ByteArrayOutputStream();

        writeLine(frame, "SEND");
        writeLine(frame, "destination:" + escapeHeader(destination));
        writeLine(frame, "content-type:" + escapeHeader(contentType));
        writeLine(frame, "note:" + escapeHeader(note));
        writeLine(frame, "content-length:" + bodyBytes.length);

        // EOL trống kết thúc header section.
        frame.write('\n');

        // Body là byte UTF-8, không phải số ký tự Java.
        frame.writeBytes(bodyBytes);

        // NUL octet kết thúc frame; không tính vào content-length.
        frame.write(0);

        return frame.toByteArray();
    }

    private static void writeLine(
            ByteArrayOutputStream output,
            String line) {

        output.writeBytes(
                (line + "\n").getBytes(StandardCharsets.UTF_8)
        );
    }

    private static String escapeHeader(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace(":", "\\c");
    }

    public static void main(String[] args) {
        String body = "Xin chào";
        String note = "line1:ok\nline2\\done";

        byte[] frame = encodeSend(
                "/queue/orders",
                "text/plain;charset=UTF-8",
                note,
                body
        );

        // Chỉ thay NUL bằng ký hiệu dễ đọc để in ví dụ.
        String printable = new String(
                frame,
                StandardCharsets.UTF_8
        ).replace(String.valueOf((char) 0), "^@");

        System.out.println(printable);
        System.out.println("body.utf8Octets="
                + body.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("body.javaLength=" + body.length());
    }
}
~~~

Biên dịch và chạy bằng Java 17:

~~~bash
javac StompFrameBuilderDemo.java
java StompFrameBuilderDemo
~~~

Stdout:

~~~text
SEND
destination:/queue/orders
content-type:text/plain;charset=UTF-8
note:line1\cok\nline2\\done
content-length:9

Xin chào^@
body.utf8Octets=9
body.javaLength=8
~~~

Trong output, ký hiệu ^@ đại diện byte NUL. Chương trình chỉ thay NUL bằng ký hiệu dễ đọc khi in; byte thực tế trong frame vẫn là 0x00.

Ví dụ cho thấy String.length() bằng 8 trong khi UTF-8 body dài 9 byte. Giá trị content-length đúng là 9.

Hàm escapeHeader áp dụng quy tắc cho header value của frame SEND. Không dùng hàm này cho body. Một encoder production còn phải xử lý command, header name hợp lệ, giới hạn kích thước, phiên bản STOMP và các loại frame khác.

## 19. Lỗi thường gặp khi đọc hoặc tạo frame

1. **Quên dòng trống giữa header và body:** parser không biết body bắt đầu ở đâu.
2. **Dùng newline để kết thúc body:** STOMP frame kết thúc bằng byte NUL, không phải newline.
3. **Gửi hai ký tự ^@ thay cho NUL:** ^@ chỉ là ký hiệu trong tài liệu.
4. **Đếm ký tự thay vì byte:** content-length phải là số octet sau khi encode.
5. **Tính byte NUL vào content-length:** NUL terminator nằm ngoài body length.
6. **Không đặt content-length khi body chứa NUL:** parser có thể kết thúc body quá sớm.
7. **Không escape header value:** colon, CR, LF hoặc backslash có thể làm hỏng cấu trúc header.
8. **Escape sai thứ tự:** backslash phải được escape trước các ký tự khác.
9. **Dùng escape sequence không hợp lệ:** STOMP 1.2 không định nghĩa \t.
10. **Trim header value:** khoảng trắng đầu/cuối có thể là dữ liệu có chủ ý.
11. **Giả định header trùng lấy giá trị cuối:** STOMP 1.2 khuyến nghị dùng giá trị đầu tiên.
12. **Cho rằng mọi frame đều có body:** chỉ SEND, MESSAGE và ERROR được phép có body.
13. **Nhầm heartbeat LF với frame rỗng:** heartbeat là EOL đơn lẻ, không có command và NUL.
14. **Coi RECEIPT là xác nhận nghiệp vụ:** receipt chỉ xác nhận server đã xử lý frame ở mức protocol.
15. **Nhầm ACK id với message-id:** ACK id phải khớp header ack trong MESSAGE.
16. **Giả định /queue và /topic là cú pháp bắt buộc:** semantics destination do server quy định.
17. **Giả định một lần socket read tương ứng một frame:** stream có thể chia hoặc gộp frame tùy thời điểm.
18. **Không giới hạn kích thước frame:** header/body lớn có thể làm cạn bộ nhớ parser.
19. **Nhầm STOMP frame với WebSocket frame:** STOMP là subprotocol chạy trên transport; Spring Message là object nội bộ.
20. **Dùng JMS API để parse STOMP:** JMS Message và STOMP wire frame là hai abstraction khác nhau.

## 20. Checklist kiểm tra một frame

Khi debug frame thô, kiểm tra theo thứ tự:

- Command có đúng tên và đúng chữ hoa/chữ thường không?
- EOL có hợp lệ theo phiên bản STOMP không?
- Header line có dạng key:value không?
- Các header bắt buộc của command đã có chưa?
- Có dòng EOL trống trước body không?
- Header value đã escape đúng chưa?
- Có header trùng cần áp dụng quy tắc first-value không?
- content-type có mô tả đúng body không?
- content-length có bằng số byte body sau encoding không?
- Nếu body chứa NUL, content-length đã có chưa?
- Byte NUL terminator có ở đúng vị trí không?
- Nếu không có frame, EOL đơn lẻ có phải heartbeat không?
- Frame có vượt giới hạn kích thước của client/server không?
- Destination và header extension có đúng với broker đang dùng không?

## 21. Câu hỏi tự kiểm tra

1. Một STOMP frame gồm những phần nào?
2. EOL trong STOMP 1.2 có thể là LF hoặc CRLF như thế nào?
3. Dòng trống có vai trò gì?
4. Byte nào kết thúc frame?
5. Vì sao ^@ trong tài liệu không phải dữ liệu gửi lên wire?
6. content-length đếm byte hay ký tự?
7. Khi nào content-length là bắt buộc?
8. Những frame nào được phép có body?
9. content-type giúp receiver điều gì?
10. STOMP 1.2 escape colon, LF, CR và backslash thành những sequence nào?
11. Vì sao backslash cần được escape trước?
12. Nếu một header xuất hiện nhiều lần, giá trị nào SHOULD được dùng?
13. Heartbeat được biểu diễn bằng gì khi không có frame cần gửi?
14. SEND và SUBSCRIBE khác nhau ở mục đích nào?
15. Header ack trong SUBSCRIBE điều khiển điều gì?
16. ACK id phải khớp header nào của MESSAGE?
17. RECEIPT xác nhận điều gì và không xác nhận điều gì?
18. Vì sao một lần đọc socket không chắc chứa trọn một frame?
19. Spring chuyển STOMP frame thành abstraction nội bộ nào?
20. Vì sao destination /queue/orders không có semantics giống nhau trên mọi broker?

## 22. Kết luận

STOMP frame có cấu trúc rõ ràng: command, header section, dòng trống, body và byte NUL kết thúc. Command xác định thao tác; header mang thông tin định tuyến và điều khiển; body mang payload. content-length đếm byte của body, content-type mô tả định dạng, còn header escaping bảo vệ các ký tự phân cách trong giá trị header.

Khi parse stream, cần xử lý frame chưa hoàn chỉnh, nhiều frame nối tiếp, NUL terminator, heartbeat và giới hạn kích thước. Khi làm việc với Spring, STOMP frame được decode thành Spring Message rồi đi qua message channel, controller hoặc broker. Hiểu đúng ranh giới giữa wire-format, transport và Spring Message giúp debug protocol chính xác và tránh tự xử lý chuỗi theo cách làm hỏng binary payload.

## Tài liệu tham khảo chính thức

- STOMP Protocol Specification, Version 1.2: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework 6.2 — STOMP Overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/overview.html
- Spring Framework 6.2 — STOMP Message Flow: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — STOMP Protocol Support: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html
- Spring Framework 6.2 — STOMP Client: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/client.html
- Spring Framework 6.2 StompHeaderAccessor API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2 StompDecoder API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html
- Spring Framework 6.2 StompEncoder API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html
