# PAYLOAD và các cờ NEXT, COMPLETE, FOLLOWS

RSocket sử dụng các frame để trao đổi dữ liệu trên một phiên giao tiếp. Trong số đó, **PAYLOAD** là frame mang một payload của stream: payload có thể chứa data, metadata hoặc cả hai. Ba cờ **NEXT**, **COMPLETE** và **FOLLOWS** quyết định cách bên nhận diễn giải frame này: có một phần tử mới hay không, hướng stream có kết thúc hay không, và payload hiện tại còn fragment tiếp theo hay không.

Nắm rõ ba cờ giúp đọc trace giao thức, xử lý stream đúng vòng đời và tránh nhầm lẫn giữa việc kết thúc một payload, kết thúc một hướng stream và hoàn tất quá trình truyền một payload đã phân mảnh. Nội dung nằm trong phạm vi giao thức RSocket dùng cho giao tiếp bất đồng bộ, hai chiều và reactive qua các transport như TCP hoặc WebSocket.

## 1. PAYLOAD frame nằm ở đâu trong giao thức?

Mỗi frame RSocket có header chung gồm **Stream ID**, **Frame Type** và **Flags**. Stream ID xác định tương tác mà frame thuộc về; Frame Type cho biết loại thao tác; Flags bổ sung thông tin điều khiển riêng cho loại frame đó.

PAYLOAD có Frame Type là **0x0A**. Sau phần header là nội dung payload, gồm metadata tùy chọn và data. Một PAYLOAD frame thuộc về một stream cụ thể, vì vậy Stream ID của nó phải xác định được tương tác đang diễn ra.

Cần phân biệt hai khái niệm:

- **Payload** là đối tượng nội dung mà ứng dụng gửi hoặc nhận, thường gồm data và metadata.
- **PAYLOAD frame** là đơn vị frame của giao thức dùng để chuyển payload hoặc báo hiệu trạng thái stream.

Các frame khởi tạo tương tác như REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL hoặc REQUEST_FNF mang request ban đầu. Sau khi tương tác được thiết lập, PAYLOAD frame thường được dùng để gửi các phần tử tiếp theo của stream hoặc phản hồi. Ví dụ, requester khởi tạo REQUEST_STREAM; responder sau đó gửi các PAYLOAD frame chứa từng kết quả.

### Cấu trúc khái quát

~~~text
+-------------------------------+
| Stream ID                     |
+-------------------------------+
| Frame Type = PAYLOAD (0x0A)   |
| Flags: M | F | C | N          |
+-------------------------------+
| Metadata (nếu có)             |
+-------------------------------+
| Data                          |
+-------------------------------+
~~~

Các bit flag được định nghĩa trong trường Flags 10 bit của header. Những bit không được định nghĩa cho loại frame đang xét phải được gửi bằng 0 và không được diễn giải như một cờ PAYLOAD.

## 2. Data và metadata trong PAYLOAD

PAYLOAD có thể chứa hai phần nội dung:

- **Data:** dữ liệu nghiệp vụ, ví dụ JSON, chuỗi, byte array hoặc dữ liệu đã được codec mã hóa.
- **Metadata:** thông tin mô tả hoặc điều khiển đi kèm, ví dụ route, MIME type, thông tin tracing hoặc dữ liệu xác thực theo quy ước của ứng dụng.

Cờ **M (Metadata)** có giá trị mask **0x100**. Khi M được bật, frame có phần metadata và phần metadata được mã hóa với trường độ dài theo định dạng của giao thức. Data nằm sau phần metadata. Khi M không được bật, frame không có phần metadata; phần nội dung còn lại là data.

Metadata không thay thế data và cũng không tự mang ý nghĩa xác thực. Hai peer phải thống nhất cách mã hóa, MIME type và cách diễn giải metadata. Phía nhận vẫn phải kiểm tra dữ liệu nhận được trước khi sử dụng.

Một điểm quan trọng: payload có thể có data rỗng mà vẫn là một phần tử hợp lệ. Vì vậy, không thể xác định có sự kiện mới chỉ bằng cách kiểm tra độ dài data. Cờ NEXT cho biết có một payload cần chuyển đến tầng ứng dụng.

## 3. Ý nghĩa của ba cờ chính

Ba cờ NEXT, COMPLETE và FOLLOWS có trách nhiệm riêng. NEXT và COMPLETE mô tả ngữ nghĩa Reactive Streams của payload/stream; FOLLOWS mô tả việc phân mảnh ở tầng frame.

| Cờ | Bit mask | Ý nghĩa |
|---|---:|---|
| NEXT (N) | 0x20 | Có payload mới; bên nhận phát sự kiện tương đương onNext(payload) |
| COMPLETE (C) | 0x40 | Hướng stream này hoàn tất; bên nhận phát sự kiện tương đương onComplete() |
| FOLLOWS (F) | 0x80 | Còn fragment tiếp theo của cùng một payload đang được truyền |

Cách ghi nhớ:

- **NEXT:** có một phần tử mới để giao cho ứng dụng.
- **COMPLETE:** bên gửi đã hoàn tất việc phát dữ liệu trên hướng stream của nó.
- **FOLLOWS:** payload hiện tại chưa được truyền xong ở tầng frame; còn fragment theo sau.

FOLLOWS không có nghĩa là stream sẽ có thêm phần tử nghiệp vụ. Nó chỉ báo rằng phần payload hiện tại còn phần tiếp theo. Ngược lại, COMPLETE nói về vòng đời của hướng stream, không phải trạng thái hoàn tất của riêng một fragment.

## 4. Các tổ hợp NEXT và COMPLETE

Trong PAYLOAD frame, NEXT và COMPLETE tạo ra ba tổ hợp có ý nghĩa. Tổ hợp cả hai đều tắt không hợp lệ đối với PAYLOAD.

| NEXT | COMPLETE | Ý nghĩa ở tầng ứng dụng |
|---:|---:|---|
| 1 | 0 | Giao một payload mới; stream tiếp tục mở |
| 1 | 1 | Giao payload cuối cùng rồi hoàn tất stream |
| 0 | 1 | Hoàn tất stream mà không giao payload mới |
| 0 | 0 | Không hợp lệ đối với PAYLOAD frame |

### NEXT bật, COMPLETE tắt

Đây là trường hợp thường gặp khi stream còn dữ liệu:

~~~text
PAYLOAD
  NEXT = 1
  COMPLETE = 0
  FOLLOWS = 0
  Data = "event-001"
~~~

Bên nhận chuyển payload cho subscriber như một phần tử mới. Stream vẫn mở và có thể tiếp tục nhận PAYLOAD frame khác.

Ví dụ, một dịch vụ theo dõi giá gửi nhiều cập nhật. Mỗi cập nhật là một phần tử; các frame NEXT liên tiếp không có COMPLETE cho biết stream vẫn đang hoạt động.

### NEXT và COMPLETE cùng bật

Tổ hợp này có nghĩa là frame mang payload cuối cùng và đồng thời kết thúc hướng stream:

~~~text
PAYLOAD
  NEXT = 1
  COMPLETE = 1
  FOLLOWS = 0
  Data = "final-result"
~~~

Bên nhận xử lý phần tử cuối cùng trước, sau đó nhận tín hiệu hoàn tất. Thứ tự này quan trọng: ứng dụng phải xử lý payload cuối trước khi kết thúc pipeline.

### Chỉ COMPLETE bật

Tổ hợp này dùng để báo hoàn tất mà không có phần tử mới:

~~~text
PAYLOAD
  NEXT = 0
  COMPLETE = 1
  FOLLOWS = 0
  Data = empty
~~~

Ví dụ, producer đã phát hết dữ liệu nhưng không có phần tử cuối cần gửi. Consumer nhận tín hiệu hoàn tất và kết thúc subscription bình thường.

### Vì sao NEXT không được suy ra từ độ dài data?

Một payload có thể chứa data rỗng nhưng vẫn là một sự kiện hợp lệ. Ví dụ, ứng dụng dùng sự kiện rỗng để biểu diễn một tín hiệu hoặc metadata-only message. Nếu chỉ kiểm tra data length lớn hơn 0, receiver sẽ bỏ qua payload hợp lệ đó.

NEXT là tín hiệu rõ ràng cho biết receiver phải chuyển payload tới tầng ứng dụng. Nó tách ngữ nghĩa “có phần tử mới” khỏi chi tiết payload có bao nhiêu byte data.

## 5. FOLLOWS và phân mảnh payload

Một payload có thể lớn hơn kích thước frame mà transport hoặc cấu hình ứng dụng cho phép. RSocket hỗ trợ **fragmentation** để chia payload thành nhiều frame nhỏ hơn. FOLLOWS cho biết fragment hiện tại có fragment tiếp theo hay không.

Ví dụ, một payload lớn được chia thành ba PAYLOAD frame:

~~~text
Fragment 1: PAYLOAD (FOLLOWS = 1) -- còn fragment sau
Fragment 2: PAYLOAD (FOLLOWS = 1) -- vẫn còn fragment sau
Fragment 3: PAYLOAD (FOLLOWS = 0) -- fragment cuối
~~~

Bên nhận thu thập các fragment theo đúng thứ tự và reassemble thành một payload logic trước khi chuyển payload đó lên tầng ứng dụng. Ba fragment không phải ba sự kiện NEXT độc lập. Chúng tạo thành một payload duy nhất.

### Quy tắc truyền metadata và data

Khi một PAYLOAD bị phân mảnh, metadata phải được truyền đầy đủ trước data. Nếu metadata lớn hơn phần dung lượng có thể đặt trong một frame, các fragment đầu có thể mang những phần metadata tiếp theo; chỉ sau khi metadata đã được truyền hết mới đến phần data. Cờ M cho biết fragment có metadata trong frame đó.

Điều này giúp receiver ghép đúng cấu trúc payload. Không được giả định mỗi fragment đều chứa cả metadata và data.

### FOLLOWS không phải NEXT

Hai cờ giải quyết hai vấn đề khác nhau:

- NEXT nói rằng payload logic được chuyển tới ứng dụng như một phần tử.
- FOLLOWS nói rằng quá trình truyền payload logic này còn fragment tiếp theo.

Một chuỗi fragment không được tính thành nhiều phần tử stream. Fragmentation cũng không làm tăng số demand credit mà payload tiêu thụ: một payload đã phân mảnh vẫn tương ứng với một phần tử theo request(n).

### FOLLOWS và COMPLETE

FOLLOWS và COMPLETE không nên được hiểu là hai trạng thái đối lập. FOLLOWS điều khiển reassembly; COMPLETE điều khiển vòng đời stream. Tuy nhiên, theo quy tắc PAYLOAD của giao thức, nếu một PAYLOAD có cả FOLLOWS và COMPLETE bật thì FOLLOWS bị bỏ qua. Vì vậy, không thiết kế chuỗi fragment dựa trên giả định rằng một frame vừa báo còn fragment tiếp theo vừa báo hoàn tất theo cách thông thường.

## 6. Đọc PAYLOAD trong các kiểu tương tác RSocket

PAYLOAD xuất hiện trong các kiểu tương tác có stream response hoặc dữ liệu tiếp diễn. Cần đọc nó trong ngữ cảnh stream ID và request frame đã khởi tạo.

### Request-response

Requester gửi REQUEST_RESPONSE. Responder trả về một PAYLOAD chứa kết quả. Với request-response, tương tác chỉ có một response; nếu PAYLOAD response không bật COMPLETE, receiver vẫn phải coi response đó là hoàn tất theo quy tắc riêng của giao thức.

Ví dụ luồng logic:

~~~text
Requester -> Responder: REQUEST_RESPONSE
Responder -> Requester: PAYLOAD (NEXT = 1, COMPLETE = 1)
~~~

### Request-stream

Requester gửi REQUEST_STREAM kèm initial request N. Responder gửi các PAYLOAD frame theo nhu cầu đã cấp. Khi hết dữ liệu, responder có thể gửi payload cuối với NEXT và COMPLETE cùng bật, hoặc gửi COMPLETE mà không có NEXT nếu không còn phần tử nào cần giao.

~~~text
Requester -> Responder: REQUEST_STREAM (Initial Request N = 2)
Responder -> Requester: PAYLOAD (NEXT = 1, COMPLETE = 0)
Responder -> Requester: PAYLOAD (NEXT = 1, COMPLETE = 0)
Responder -> Requester: PAYLOAD (NEXT = 0, COMPLETE = 1)
~~~

### Request-channel

Request-channel cho phép hai phía trao đổi stream dữ liệu. Mỗi phía có thể gửi PAYLOAD trên cùng stream ID để truyền phần tử theo hướng của mình. COMPLETE từ một phía báo rằng phía đó đã kết thúc việc gửi dữ liệu; phía còn lại vẫn có thể tiếp tục gửi cho đến khi hướng của nó hoàn tất hoặc stream bị hủy/lỗi.

Điều này quan trọng khi triển khai client/server Java: kết thúc luồng request do client phát không nhất thiết có nghĩa luồng response do server phát cũng đã kết thúc.

### Fire-and-forget

Fire-and-forget khởi tạo bằng REQUEST_FNF và không có response stream cho requester đăng ký. Vì vậy, không nên mong đợi chuỗi PAYLOAD response để xác nhận xử lý. Nếu ứng dụng cần xác nhận nghiệp vụ, cần chọn kiểu tương tác có response hoặc thiết kế cơ chế xác nhận riêng.

## 7. Ví dụ đọc một chuỗi frame

Giả sử một client đăng ký stream cập nhật trạng thái. Các frame sau được ghi nhận cho cùng Stream ID 17:

| Thứ tự | Frame | FOLLOWS | Diễn giải |
|---:|---|---:|---|
| 1 | PAYLOAD (NEXT) | 0 | Có cập nhật thứ nhất |
| 2 | PAYLOAD (NEXT) | 0 | Có cập nhật thứ hai |
| 3 | PAYLOAD fragment 1 | 1 | Fragment đầu của một payload lớn |
| 4 | PAYLOAD fragment 2 | 1 | Fragment tiếp theo của payload lớn |
| 5 | PAYLOAD fragment 3 | 0 | Fragment cuối; ghép với fragment 1 và 2 thành một payload logic |
| 6 | PAYLOAD (COMPLETE) | 0 | Stream hoàn tất, không có phần tử mới |

Dòng fragment chỉ thể hiện cờ FOLLOWS để làm rõ ranh giới reassembly; không diễn giải từng fragment như một NEXT event độc lập. Khi reassembly xong, ứng dụng nhận một payload logic duy nhất. NEXT và COMPLETE được hiểu theo ngữ nghĩa của payload/stream hoàn chỉnh, không dùng để đếm số fragment.

## 8. Ví dụ với Java và Spring Boot

Ở tầng ứng dụng, lập trình viên thường không tự dựng bit NEXT, COMPLETE hoặc FOLLOWS. Spring Boot và thư viện RSocket chuyển các tín hiệu reactive thành frame giao thức tương ứng.

Một endpoint trả về stream:

~~~java
@Controller
public class StatusController {

    @MessageMapping("status.stream")
    public Flux<StatusUpdate> stream() {
        return statusService.updates();
    }
}
~~~

Client đăng ký và nhận các phần tử:

~~~java
Flux<StatusUpdate> updates = requester
    .route("status.stream")
    .retrieveFlux(StatusUpdate.class);
~~~

Khi server phát một phần tử, tầng RSocket gửi PAYLOAD có NEXT. Khi publisher hoàn tất, giao thức biểu đạt COMPLETE; nếu phần tử cuối cùng và hoàn tất được gửi cùng nhau, NEXT và COMPLETE cùng bật. Nếu payload vượt giới hạn fragment, tầng giao thức chia thành các frame có FOLLOWS rồi reassemble ở bên nhận.

Trong code reactive, các tín hiệu thường tương ứng như sau:

| Reactor / Reactive Streams | Ý nghĩa giao thức ở mức khái quát |
|---|---|
| onNext(value) | PAYLOAD có NEXT |
| onComplete() | PAYLOAD có COMPLETE |
| onNext(value) rồi onComplete() | PAYLOAD cuối có NEXT và COMPLETE, hoặc các frame tương ứng theo cách truyền |
| Một payload lớn | Có thể được chia thành fragment với FOLLOWS |

Đây là ánh xạ khái niệm để đọc hành vi. Việc tạo frame cụ thể do thư viện và phiên RSocket đảm nhiệm; ứng dụng không cần tự bật các bit flag khi sử dụng API Spring thông thường.

## 9. Các lỗi thường gặp khi đọc frame

- **Coi COMPLETE là đóng kết nối:** COMPLETE chỉ báo kết thúc hướng stream của tương tác. Phiên RSocket có thể tiếp tục phục vụ các stream khác.
- **Coi FOLLOWS là còn phần tử tiếp theo:** FOLLOWS chỉ báo còn fragment của payload hiện tại, không báo thêm một sự kiện nghiệp vụ.
- **Đếm mỗi fragment thành một phần tử:** một payload bị phân mảnh vẫn là một payload logic và chỉ tiêu thụ một demand credit.
- **Suy NEXT từ data length:** payload data rỗng vẫn có thể hợp lệ; phải dựa vào NEXT.
- **Bỏ qua metadata:** payload có thể mang metadata, data hoặc cả hai; M cho biết metadata có mặt trong frame.
- **Nghĩ COMPLETE luôn phải đi kèm NEXT:** COMPLETE có thể được gửi riêng để kết thúc stream mà không có payload cuối.
- **Nhầm hướng hoàn tất trong request-channel:** mỗi phía có thể kết thúc hướng gửi của mình độc lập.
- **Xử lý fragment như dữ liệu hoàn chỉnh:** receiver cần reassemble đúng thứ tự trước khi chuyển payload lên ứng dụng.

Khi phân tích lỗi, hãy đọc cùng lúc Stream ID, Frame Type, các flag, metadata, data và thứ tự frame. Chỉ nhìn một bit riêng lẻ có thể dẫn đến kết luận sai về trạng thái stream.

## 10. Kiểm thử và quan sát

Các bài kiểm thử nên bao phủ cả ngữ nghĩa stream và trường hợp payload lớn:

1. Gửi một PAYLOAD có NEXT nhưng không COMPLETE; xác nhận consumer nhận một phần tử và stream vẫn mở.
2. Gửi PAYLOAD có NEXT và COMPLETE; xác nhận consumer nhận phần tử cuối rồi hoàn tất.
3. Gửi PAYLOAD chỉ có COMPLETE; xác nhận không phát thêm phần tử nhưng stream hoàn tất.
4. Kiểm tra payload data rỗng nhưng NEXT bật; xác nhận consumer vẫn nhận payload.
5. Gửi payload vượt giới hạn frame; xác nhận fragment được reassemble thành một payload duy nhất.
6. Kiểm tra payload có metadata lớn; xác nhận metadata được truyền đầy đủ trước data.
7. Với request-channel, kết thúc một hướng gửi và xác nhận hướng còn lại vẫn hoạt động nếu chưa hoàn tất.

Ở mức ứng dụng, Reactor Test có thể kiểm tra tín hiệu onNext, onComplete và cancellation. Ở mức tích hợp, cần quan sát frame thực tế hoặc kiểm thử qua RSocket client/server để xác nhận việc ánh xạ đúng qua transport.

Các chỉ số hữu ích gồm số PAYLOAD frame, số payload logic sau reassembly, số fragment trên mỗi payload, kích thước metadata/data, số lần lỗi reassembly, độ trễ giao payload và số stream hoàn tất/hủy. Nếu số frame tăng đột biến do fragmentation, cần xem lại kích thước payload, giới hạn frame và cấu hình transport.

## 11. Kết luận

PAYLOAD là frame mang nội dung của một stream RSocket. NEXT báo có payload mới để chuyển đến tầng ứng dụng; COMPLETE báo hướng stream hoàn tất; FOLLOWS báo còn fragment của payload hiện tại. Metadata có thể đi kèm data và được đánh dấu bằng cờ M.

Khi đọc hoặc thiết kế luồng realtime, hãy phân biệt ba tầng ngữ nghĩa: phần tử dữ liệu, vòng đời hướng stream và quá trình phân mảnh frame. Sự phân biệt này giúp xử lý đúng request-stream, request-channel, phản hồi request-response, payload rỗng và dữ liệu lớn trong các ứng dụng Java/Spring Boot.

Tài liệu tham khảo: [RSocket Protocol](https://rsocket.io/about/protocol/).

