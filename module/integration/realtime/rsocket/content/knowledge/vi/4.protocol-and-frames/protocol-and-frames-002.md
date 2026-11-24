# Stream ID bằng 0 và quy tắc định danh luồng do hai phía khởi tạo

RSocket cho phép nhiều tương tác reactive chạy đồng thời trên cùng một kết nối TCP hoặc WebSocket. Để ghép từng frame vào đúng tương tác, giao thức gắn một **stream ID** vào header của frame. Stream ID bằng `0` được dành riêng cho frame cấp kết nối; các tương tác request-response, fire-and-forget, request-stream và request-channel dùng ID khác `0`.

Điểm cần nhớ là cả hai endpoint đều có thể khởi tạo tương tác sau khi kết nối RSocket được thiết lập. Endpoint gửi `SETUP` giữ vai trò client của kết nối và cấp stream ID lẻ cho các stream do mình mở. Endpoint nhận `SETUP` giữ vai trò server và cấp stream ID chẵn cho các stream do mình mở. Khi một stream đã được mở, cả hai phía dùng cùng ID đó cho các frame thuộc stream, kể cả khi frame đi theo chiều ngược lại.

## 1. Stream ID nằm ở đâu và dùng để làm gì?

Mỗi RSocket frame có header chứa stream ID cùng thông tin về loại frame và các cờ điều khiển. Stream ID giúp bên nhận xác định frame thuộc tương tác nào trên kết nối đang dùng. Ví dụ, `REQUEST_STREAM` mở một stream mới; những frame `PAYLOAD`, `REQUEST_N`, `CANCEL` hoặc `ERROR` liên quan đến tương tác đó tiếp tục mang cùng stream ID.

Stream ID có các đặc điểm sau:

- Là số nguyên dương 31-bit đối với stream cấp tương tác, nằm trong khoảng `1` đến `2^31 - 1`.
- `0` là giá trị đặc biệt dành cho frame cấp kết nối, không đại diện cho một request hay một stream dữ liệu.
- Được cấp bởi endpoint khởi tạo stream. Mỗi endpoint quản lý dãy ID của chính mình.
- Có phạm vi trong một kết nối RSocket; không phải ID người dùng, ID route, ID phiên nghiệp vụ hay mã tương quan toàn hệ thống.

Nhờ stream ID, một kết nối có thể ghép xen kẽ frame của nhiều tương tác. Bên nhận không cần tạo một kết nối TCP/WebSocket riêng cho từng request để biết frame nào thuộc luồng nào.

## 2. Stream ID bằng 0: frame cấp kết nối

Stream ID `0` biểu thị frame tác động đến toàn bộ kết nối RSocket hoặc mang thông tin điều khiển ở cấp kết nối. Nó không mở một request stream và cũng không phải ID mặc định cho request đầu tiên.

Một số frame cấp kết nối thường gặp:

| Frame | Mục đích | Stream ID |
|---|---|---:|
| `SETUP` | Khởi tạo phiên RSocket, thương lượng phiên bản, MIME type và thông tin thiết lập ban đầu. | `0` |
| `LEASE` | Thông báo hoặc cập nhật quyền được phép khởi tạo request theo cơ chế lease. | `0` |
| `KEEPALIVE` | Duy trì kết nối và trao đổi thông tin vị trí khi dùng cơ chế tương ứng. | `0` |
| `METADATA_PUSH` | Đẩy metadata ở phạm vi kết nối, không gắn với một request stream cụ thể. | `0` |
| `RESUME` | Yêu cầu tiếp tục một phiên RSocket có hỗ trợ resumption. | `0` |
| `RESUME_OK` | Xác nhận việc tiếp tục phiên. | `0` |
| `ERROR` | Báo lỗi khiến toàn bộ kết nối không thể tiếp tục hoạt động bình thường. | `0` |

`ERROR` là trường hợp cần chú ý: frame này có thể mang ID `0` để báo lỗi cấp kết nối, hoặc mang ID khác `0` để báo lỗi của một stream cụ thể. Vì vậy, không thể chỉ nhìn loại frame `ERROR` để kết luận phạm vi ảnh hưởng; cần đọc cả stream ID.

Ví dụ về các frame cấp kết nối:

```text
Client                                  Server
  |                                       |
  |----------- SETUP (streamId=0) ------->|
  |                                       |
  |<--------- KEEPALIVE (streamId=0) -----|
  |----------- KEEPALIVE (streamId=0) --->|
  |                                       |
  |----------- METADATA_PUSH (id=0) ----->|
```

Một frame `SETUP` không nhận stream ID `1`, vì nó thiết lập kết nối chứ không mở một tương tác nghiệp vụ. Tương tự, `KEEPALIVE` dùng ID `0` dù có thể được gửi nhiều lần trong suốt vòng đời kết nối.

## 3. Quy tắc cấp ID lẻ và chẵn

Trong một kết nối RSocket thông thường, endpoint gửi `SETUP` là client và endpoint nhận `SETUP` là server. Hai phía có không gian ID riêng để có thể mở stream độc lập mà không đụng nhau:

| Endpoint khởi tạo stream | Dãy ID | Ví dụ |
|---|---|---|
| Client (phía gửi `SETUP`) | Số lẻ, bắt đầu từ `1`, tăng dần mỗi lần `2` | `1`, `3`, `5`, `7`, ... |
| Server (phía nhận `SETUP`) | Số chẵn, bắt đầu từ `2`, tăng dần mỗi lần `2` | `2`, `4`, `6`, `8`, ... |

Ví dụ, client mở ba stream đầu tiên thì có thể cấp ID `1`, `3`, `5`. Trong lúc đó server độc lập mở hai stream và cấp ID `2`, `4`. Việc hai phía sử dụng hai dãy khác parity giúp ID không xung đột trong cùng kết nối.

Các quy tắc quan trọng:

1. Client phải cấp ID lẻ cho stream do client khởi tạo; server phải cấp ID chẵn cho stream do server khởi tạo.
2. Mỗi phía cấp ID tăng dần theo dãy của mình. Không quay lại ID cũ khi một stream đã hoàn tất hoặc bị hủy.
3. ID của một stream không được tái sử dụng trong cùng kết nối, kể cả khi stream đó kết thúc sớm do lỗi hoặc cancellation.
4. Stream ID `0` không được dùng để mở một tương tác request.
5. Hai phía không dùng chung một bộ đếm. Client quản lý dãy lẻ, server quản lý dãy chẵn.

Vì stream ID là số hữu hạn và không được tái sử dụng trong một kết nối, endpoint không được quay vòng về `1` hoặc `2` khi đã dùng hết dãy ID của mình. Khi không còn ID hợp lệ để mở stream mới, kết nối không thể tiếp tục tạo thêm stream theo cách cấp ID đó.

## 4. Parity cho biết ai khởi tạo stream, không cho biết ai gửi frame

Đây là quy tắc dễ bị hiểu nhầm nhất. ID lẻ không có nghĩa mọi frame mang ID lẻ đều do client gửi. ID chẵn cũng không có nghĩa mọi frame mang ID chẵn đều do server gửi. **Parity cho biết endpoint nào đã mở stream ban đầu.** Sau khi stream được mở, cả hai phía có thể gửi frame trên cùng stream ID.

Ví dụ client mở request-stream với ID `1`:

```text
Client                                  Server
  |                                       |
  |---- REQUEST_STREAM (streamId=1) ----->|
  |                                       |
  |<--------- PAYLOAD (streamId=1) -------|
  |<--------- PAYLOAD (streamId=1) -------|
  |                                       |
  |<--------- ERROR (streamId=1) ----------|  (nếu stream gặp lỗi)
```

Server gửi các `PAYLOAD` mang ID `1`, vì đây vẫn là stream do client khởi tạo. Server không cấp ID mới cho từng phần tử trả về. Nếu client hủy stream, frame `CANCEL` mà client gửi cũng mang ID `1`.

Tương tự, khi server mở một request-response với ID `2`, client gửi kết quả trả về trên chính ID `2`:

```text
Client                                  Server
  |                                       |
  |<--- REQUEST_RESPONSE (streamId=2) ----|
  |                                       |
  |------- PAYLOAD (streamId=2) --------->|
```

Do đó, khi đọc packet capture hoặc log frame, hãy tách hai câu hỏi: **ai khởi tạo stream?** và **endpoint nào đang gửi frame hiện tại?** Stream ID trả lời câu hỏi thứ nhất; hướng truyền trên transport trả lời câu hỏi thứ hai.

## 5. Một stream giữ nguyên ID trong suốt tương tác

Một tương tác RSocket thường bắt đầu bằng một trong các frame `REQUEST_RESPONSE`, `REQUEST_FNF`, `REQUEST_STREAM` hoặc `REQUEST_CHANNEL`. Frame mở đầu được gửi với ID mới do bên khởi tạo cấp. Các frame tiếp theo liên quan đến tương tác đó giữ nguyên ID.

| Kiểu tương tác | Frame mở đầu | Frame tiếp theo thường gặp | Quy tắc ID |
|---|---|---|---|
| Request-response | `REQUEST_RESPONSE` | `PAYLOAD` hoặc `ERROR` | Dùng cùng ID từ request đến response. |
| Fire-and-forget | `REQUEST_FNF` | Thường không có response payload; có thể có `ERROR` theo quy tắc giao thức. | ID do bên gửi request cấp. |
| Request-stream | `REQUEST_STREAM` | `REQUEST_N`, `PAYLOAD`, `CANCEL`, `ERROR` | Tất cả frame thuộc stream giữ cùng ID. |
| Request-channel | `REQUEST_CHANNEL` | `REQUEST_N`, `PAYLOAD`, `CANCEL`, `ERROR` | Cả dữ liệu hai chiều thuộc cùng stream ID. |

Các frame `REQUEST_N` và `CANCEL` là frame điều khiển một stream cụ thể nên cần ID khác `0`. `PAYLOAD` cũng mang ID của stream mà nó đang truyền dữ liệu. Khi stream kết thúc, ID đó vẫn được xem là đã dùng trong kết nối và không được cấp lại cho tương tác mới.

Với request-channel, hai phía có thể gửi dữ liệu trên cùng stream. Điều đó không tạo ra hai stream riêng: cả dữ liệu client gửi lên và dữ liệu server gửi xuống đều thuộc một tương tác channel, được nhận diện bằng một ID duy nhất.

## 6. Hai phía có thể mở stream độc lập trên cùng kết nối

RSocket là giao thức hai chiều. Vai trò client/server xác định cách cấp ID, nhưng không giới hạn việc chỉ client mới được gửi request. Sau khi kết nối được thiết lập, server có thể mở request mới hướng đến client nếu ứng dụng và peer hỗ trợ tương tác đó.

Ví dụ sau cho thấy hai phía mở stream đồng thời:

```text
Client (gửi SETUP)                    Server (nhận SETUP)
        |                                      |
        |---- REQUEST_STREAM (id=1) ---------->|
        |                                      |
        |<--- REQUEST_RESPONSE (id=2) ---------|  Server tự mở stream
        |                                      |
        |<--------- PAYLOAD (id=1) ------------|  Response của stream 1
        |                                      |
        |---- PAYLOAD (id=2) ----------------->|  Response của stream 2
        |                                      |
        |---- REQUEST_CHANNEL (id=3) --------->|
        |                                      |
        |<--- REQUEST_STREAM (id=4) ------------|  Server mở stream khác
```

Trong ví dụ:

- `id=1` do client mở, nên là số lẻ. Server trả dữ liệu cho stream này trên ID `1`.
- `id=2` do server mở, nên là số chẵn. Client trả kết quả cho server trên ID `2`.
- `id=3` tiếp tục thuộc dãy client; `id=4` thuộc dãy server.
- Các frame có thể xen kẽ nhau trên cùng kết nối. Mỗi frame vẫn được ghép vào stream tương ứng bằng ID.

Điều này giúp ứng dụng xây dựng giao tiếp hai chiều mà không phải mở một kết nối mới cho mỗi lần server chủ động gửi yêu cầu tới client.

## 7. Ví dụ với Spring RSocket

Trong Spring, ứng dụng thường làm việc với `Mono`, `Flux` và `RSocketRequester`; không cần tự tăng hoặc gán stream ID trong code nghiệp vụ. RSocket runtime quản lý việc cấp ID, ghép frame và xử lý các frame phản hồi.

Ví dụ client tạo request-response:

```java
Mono<Quote> quote = requester
    .route("quotes.latest")
    .data("ACME")
    .retrieveMono(Quote.class);

return quote;
```

Khi publisher được subscribe, RSocket runtime mở một stream mới và cấp một ID lẻ vì client là phía khởi tạo tương tác. Giá trị cụ thể như `1` hay `3` phụ thuộc những stream client đã mở trước đó trên cùng kết nối. Phản hồi từ server thuộc cùng ID này.

Ví dụ client tạo request-stream:

```java
Flux<Quote> quotes = requester
    .route("quotes.stream")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class);

return quotes.take(20);
```

`take(20)` giới hạn số phần tử mà ứng dụng quan tâm. Khi upstream bị hủy, runtime gửi frame điều khiển `CANCEL` trên stream ID của request-stream đó. `CANCEL` không mở stream mới và không dùng ID `0`.

Ở phía server, handler nhận request và trả publisher:

```java
@MessageMapping("quotes.stream")
public Flux<Quote> stream(QuoteRequest request) {
    return quoteService.stream(request.symbol());
}
```

Framework gắn publisher phản hồi vào stream ID của request đến. Vì vậy, server trả `PAYLOAD` trên ID do client đã cấp, không lấy một ID chẵn mới cho phần response. Nếu server muốn khởi tạo một tương tác độc lập hướng đến client, đó mới là lúc server cấp ID chẵn của mình.

## 8. Phân biệt lỗi cấp kết nối và lỗi cấp stream

Stream ID giúp xác định phạm vi của frame `ERROR`:

| Dạng lỗi | Stream ID | Phạm vi ảnh hưởng |
|---|---:|---|
| Connection error | `0` | Kết nối RSocket bị lỗi; nhiều hoặc toàn bộ stream trên kết nối có thể bị ảnh hưởng. |
| Stream error | ID khác `0` | Tương tác mang ID đó kết thúc do lỗi; các stream độc lập khác có thể tiếp tục. |

Khi xử lý lỗi, không nên mặc định mọi `ERROR` đều đóng kết nối. Nếu `ERROR` mang ID của một stream, ứng dụng cần xử lý lỗi trong phạm vi tương tác đó. Nếu ID bằng `0`, cần xem đây là tín hiệu ở phạm vi kết nối và xử lý vòng đời connection tương ứng.

Ví dụ:

```text
ERROR (streamId=0)  -> lỗi cấp kết nối
ERROR (streamId=5)  -> lỗi của stream do client mở với ID 5
ERROR (streamId=4)  -> lỗi của stream do server mở với ID 4
```

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| Xem `streamId=0` là stream đầu tiên. | `0` được dành riêng cho frame cấp kết nối. | Stream tương tác đầu tiên thường có ID `1` từ client hoặc `2` từ server. |
| Nghĩ mọi frame có ID lẻ đều do client gửi. | Server có thể gửi `PAYLOAD`, `ERROR` hoặc frame điều khiển trên stream lẻ do client mở. | Parity nhận diện bên khởi tạo stream, không nhận diện bên gửi frame hiện tại. |
| Nghĩ server chỉ được phản hồi, không được mở request. | RSocket hỗ trợ hai phía khởi tạo tương tác. | Server dùng dãy ID chẵn khi tự mở stream. |
| Cấp ID mới cho response của request-response. | Response là một phần của stream đã được mở. | Response dùng lại stream ID của request. |
| Tái sử dụng ID sau khi stream hoàn tất. | ID phải duy nhất trong phạm vi kết nối và không được tái sử dụng. | Tiếp tục cấp ID mới theo dãy tăng dần của endpoint. |
| Dùng ID `0` cho `REQUEST_N`, `CANCEL` hoặc `PAYLOAD`. | Đây là các frame thuộc một stream cụ thể. | Dùng ID khác `0` của stream tương ứng. |
| Xem ID là mã request toàn cục. | ID chỉ có ý nghĩa trong một kết nối RSocket. | Nếu cần correlation xuyên nhiều kết nối hoặc lưu vết nghiệp vụ, dùng correlation ID ở tầng ứng dụng. |

## 10. Cách đọc log và chẩn đoán lỗi stream ID

Khi đọc log frame hoặc packet capture, hãy thực hiện theo trình tự:

1. Xác định kết nối và endpoint nào đã gửi `SETUP`. Đây là cơ sở để biết phía nào dùng dãy lẻ và phía nào dùng dãy chẵn.
2. Đọc stream ID trước khi diễn giải frame. ID `0` cho biết phạm vi kết nối; ID khác `0` cho biết frame thuộc một stream cụ thể.
3. Nếu gặp frame mở đầu `REQUEST_*`, xác định endpoint gửi frame đó. ID phải thuộc dãy của endpoint khởi tạo.
4. Ghép các frame tiếp theo có cùng ID, kể cả khi hướng truyền đổi chiều. Không tạo một stream mới chỉ vì frame được gửi từ endpoint còn lại.
5. Khi gặp `ERROR`, kiểm tra ID để xác định lỗi ở phạm vi connection hay stream.
6. Kiểm tra ID có tăng đúng dãy và có bị tái sử dụng trong cùng kết nối không.

Ví dụ log giả lập:

```text
C -> S  SETUP              stream=0
C -> S  REQUEST_STREAM     stream=1
S -> C  REQUEST_RESPONSE   stream=2
S -> C  PAYLOAD            stream=1
C -> S  PAYLOAD            stream=2
C -> S  REQUEST_CHANNEL    stream=3
S -> C  REQUEST_STREAM     stream=4
S -> C  KEEPALIVE          stream=0
```

Log này hợp lệ về nguyên tắc cấp ID: client mở các stream `1` và `3`; server mở các stream `2` và `4`; `SETUP` và `KEEPALIVE` thuộc cấp kết nối nên dùng ID `0`. Hướng truyền của `PAYLOAD` trên ID `1` và `2` cho thấy response có thể đi ngược chiều với frame mở đầu mà vẫn giữ nguyên ID.

Nếu thấy `REQUEST_*` dùng ID `0`, ID sai parity so với endpoint khởi tạo, hoặc một ID đã được cấp lại trong cùng kết nối, hãy kiểm tra cách triển khai protocol hoặc thư viện RSocket. Nếu thấy `PAYLOAD` đi theo hướng ngược với request ban đầu, đó có thể là hành vi hoàn toàn bình thường; hãy kiểm tra stream ID trước khi kết luận có lỗi định tuyến.

## Kết luận

Stream ID `0` dành cho điều khiển và thông tin ở phạm vi kết nối. Các stream tương tác dùng ID khác `0`; client mở stream bằng dãy số lẻ, server mở stream bằng dãy số chẵn. ID được cấp bởi bên khởi tạo, tăng dần và không tái sử dụng trong cùng kết nối. Sau khi stream được mở, cả hai phía dùng chung ID đó cho mọi frame của tương tác, bất kể hướng truyền. Hiểu rõ ba quy tắc này giúp đọc frame RSocket chính xác, xây dựng giao tiếp hai chiều và chẩn đoán lỗi multiplexing trên TCP hoặc WebSocket.
