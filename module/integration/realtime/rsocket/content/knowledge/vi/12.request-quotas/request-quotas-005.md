# Hành vi khi hết hạn ngạch hoặc lease hết hiệu lực

RSocket có cơ chế **leasing** để giới hạn số request mà một peer được phép khởi tạo trong một khoảng thời gian. Responder gửi frame `LEASE` để cấp cho requester một số lượt request cùng thời hạn sử dụng. Khi đã dùng hết lượt hoặc lease hết hạn, requester không được mở request mới cho đến khi nhận được lease tiếp theo.

Lease là cơ chế kiểm soát quyền **bắt đầu tương tác** ở cấp kết nối. Nó khác với backpressure của request-stream: lease giới hạn số request mới, còn `REQUEST_N` giới hạn số payload mà responder được phép phát trên một stream đã mở. Phân biệt hai loại hạn ngạch này giúp tránh nhầm lẫn khi xử lý request bị từ chối, stream đang chạy và việc cấp thêm demand.

## 1. Lease là gì?

Một lease do Responder gửi cho Requester qua frame `LEASE`. Nó có hai thông tin chính:

| Trường | Ý nghĩa | Đơn vị |
|---|---|---|
| `Time-To-Live` (TTL) | Thời gian lease còn hiệu lực, tính từ lúc requester nhận frame. | Millisecond |
| `Number of Requests` | Số request mới tối đa mà requester được phép gửi trong thời hạn đó. | Lượt request |

Frame `LEASE` luôn có `streamId = 0` vì nó áp dụng cho toàn bộ kết nối, không thuộc một request stream riêng. Metadata có thể đi kèm nếu ứng dụng cần truyền thêm thông tin về lease; giao thức không quy định nội dung metadata tùy chỉnh đó.

Ví dụ, responder cấp:

```text
LEASE
  streamId        = 0
  timeToLive      = 5000 ms
  numberOfRequests = 100
```

Requester có tối đa 100 lượt mở request trong vòng 5 giây kể từ khi nhận lease. Nếu dùng hết 100 lượt sau 2 giây, requester phải đợi lease tiếp theo dù TTL cũ vẫn còn. Nếu chỉ dùng 20 lượt rồi TTL kết thúc, 80 lượt còn lại cũng hết hiệu lực.

## 2. Lease được thương lượng khi thiết lập kết nối

Lease chỉ được áp dụng khi hai phía bật cơ chế leasing. Trong frame `SETUP`, cờ `L` cho biết requester ở phía gửi `SETUP` cam kết tôn trọng lease mà peer cấp.

Với kết nối client-server thông thường:

1. Client gửi `SETUP` với cờ `L` nếu muốn giới hạn các request mà client gửi lên server.
2. Nếu server chấp nhận `SETUP` có cờ `L`, server phải gửi một frame `LEASE` trước khi client được gửi request.
3. Client chỉ bắt đầu request sau khi nhận lease hợp lệ.
4. Nếu client không bật cờ `L`, client requester có thể gửi request ngay sau khi kết nối được thiết lập mà không cần chờ lease từ server.

RSocket hỗ trợ khởi tạo request theo cả hai chiều. Nếu server cũng muốn gửi request đến client, server-side requester phải tuân theo lease do client-side responder cấp. Khi client bật `L`, client-side responder cũng phải gửi lease để cho phép server khởi tạo request theo chiều ngược lại.

```text
Client (Requester)                         Server (Responder)
       |                                           |
       | SETUP, L=1, streamId=0                    |
       |------------------------------------------>|
       |                                           |
       | LEASE, streamId=0, TTL=5000, N=100        |
       |<------------------------------------------|
       |                                           |
       | REQUEST_RESPONSE, streamId=1              |
       |------------------------------------------>|
       |                                           |
       |<---------------- PAYLOAD -----------------|
```

Nếu `SETUP` có cờ `L` nhưng peer không hỗ trợ hoặc không chấp nhận cấu hình, kết nối có thể bị từ chối trong giai đoạn thiết lập. Ứng dụng cần cấu hình leasing đồng bộ ở hai phía thay vì chỉ giả định rằng server tự động giới hạn request.

## 3. Những request nào tiêu thụ quota?

Lease đếm **từng request mới thuộc mọi kiểu tương tác**. Mỗi frame mở đầu một tương tác tiêu thụ một lượt:

| Frame mở đầu | Có tiêu thụ một lượt lease? | Giải thích |
|---|---:|---|
| `REQUEST_RESPONSE` | Có | Mở một request-response. |
| `REQUEST_FNF` | Có | Mở một fire-and-forget. |
| `REQUEST_STREAM` | Có | Mở một request-stream, dù sau đó stream phát nhiều payload. |
| `REQUEST_CHANNEL` | Có | Mở một request-channel hai chiều. |

Các frame tiếp tục một tương tác đã mở không tiêu thụ thêm quota lease:

- `PAYLOAD` gửi response hoặc dữ liệu tiếp theo trên stream hiện tại.
- `REQUEST_N` cấp thêm demand cho stream hiện tại.
- `CANCEL`, `COMPLETE` và `ERROR` kết thúc hoặc điều khiển vòng đời stream.
- Một request bị phân mảnh thành nhiều frame vẫn chỉ tính là một request.

Ví dụ, một `REQUEST_STREAM` tiêu thụ một lượt lease dù responder trả về 10 hay 10.000 `PAYLOAD`. Tương tự, một `REQUEST_CHANNEL` tiêu thụ một lượt khi được mở; các `PAYLOAD` tiếp theo của channel không phải request mới.

## 4. Hai cách một lease hết quyền sử dụng

Quota của lease có thể hết trước TTL hoặc TTL có thể hết trước khi dùng hết quota.

### Hết số lượt trước khi hết TTL

Giả sử lease cho phép 3 request trong 10 giây:

```text
Thời điểm nhận lease:  t=0s
TTL:                  10s
Number of Requests:   3

t=1s  REQUEST_RESPONSE  -> còn 2 lượt
t=2s  REQUEST_STREAM    -> còn 1 lượt
t=3s  REQUEST_FNF       -> còn 0 lượt
t=4s  request mới       -> phải chờ lease mới
t=10s lease cũ hết TTL
```

Khi quota đã về 0, requester không được mở request thứ tư. Việc TTL còn 7 giây không tạo thêm lượt. Requester phải chờ responder gửi lease mới hoặc áp dụng chính sách chờ/từ chối ở tầng ứng dụng.

### Hết TTL trước khi dùng hết số lượt

Giả sử lease cho phép 10 request trong 2 giây nhưng requester mới dùng 4 lượt:

```text
Thời điểm nhận lease:  t=0s
TTL:                  2s
Number of Requests:   10

t=0.5s REQUEST_RESPONSE -> còn 9 lượt
t=0.8s REQUEST_STREAM   -> còn 8 lượt
t=1.2s REQUEST_FNF      -> còn 7 lượt
t=1.8s REQUEST_CHANNEL  -> còn 6 lượt
t=2.0s TTL hết hạn      -> quota hiệu lực = 0
t=2.1s request mới      -> phải chờ lease mới
```

Khi lease hết TTL, số lượt còn lại tự động trở thành 0. Requester không được giữ lại phần quota chưa dùng để cộng sang lease tiếp theo.

## 5. Hành vi khi hết quota hoặc lease hết hạn

Requester phải tự tuân thủ lease. Khi số lượt còn lại bằng 0 hoặc TTL đã hết, requester không được gửi thêm frame mở request mới. Các hành vi ở tầng ứng dụng thường gồm:

- Tạm giữ request trong hàng đợi chờ lease mới.
- Trả lỗi giới hạn tạm thời cho caller nếu không thể chờ.
- Áp dụng timeout cho thời gian chờ lease để tránh giữ request vô hạn.
- Điều chỉnh tốc độ tạo request hoặc giảm tải ở upstream.

Giao thức không tự động tạo lease mới và cũng không bắt buộc đóng kết nối khi lease hết. Việc cấp lease mới thuộc trách nhiệm của responder/application. Nếu responder ngừng gửi lease, requester sẽ không có quyền mở request mới trong hướng được kiểm soát; xử lý tình trạng chờ hoặc báo lỗi là chính sách của ứng dụng.

Lease chỉ kiểm soát request mới. Các stream đã được mở hợp lệ trước thời điểm quota cạn hoặc TTL hết vẫn có thể tiếp tục trả `PAYLOAD`, hoàn tất hoặc lỗi theo vòng đời riêng. Hết lease không tự động hủy các request đang chạy và cũng không thu hồi demand `REQUEST_N` đã cấp cho stream.

## 6. Nếu requester gửi request vượt lease: ERROR[REJECTED]

Một requester tuân thủ giao thức không được cố tình gửi request khi lease không còn quyền. Tuy nhiên, nếu responder nhận được một request mà nó không thể chấp nhận do hạn chế lease, responder phải trả frame `ERROR` với mã `REJECTED` trên stream ID của request đó.

```text
Requester                                  Responder
    |                                          |
    | LEASE (streamId=0, TTL=3000, N=1)       |
    |<-----------------------------------------|
    |                                          |
    | REQUEST_RESPONSE (streamId=1)            |
    |----------------------------------------->|
    |                                          |
    | REQUEST_STREAM (streamId=3)              |
    |----------------------------------------->|  vượt quota
    |                                          |
    | ERROR (streamId=3, code=REJECTED)        |
    |<-----------------------------------------|
```

`REJECTED` có ý nghĩa quan trọng: responder bảo đảm request bị từ chối chưa được xử lý. Caller có thể đợi lease mới rồi cân nhắc gửi lại request. Điều này khác với timeout hoặc lỗi kết nối, khi client có thể không biết server đã thực hiện side effect hay chưa.

Không nên xem `REJECTED` là lỗi làm hỏng toàn bộ kết nối. Đây là lỗi ở phạm vi stream; các request khác đang chạy trên kết nối có thể tiếp tục bình thường. Khi xử lý ở Reactor, requester nhận lỗi tương ứng trên publisher của request bị từ chối.

## 7. Lease mới thay thế lease cũ

Khi requester nhận một frame `LEASE` mới, giá trị mới nhất **ghi đè** các giá trị lease trước đó. Quota mới không cộng dồn với số lượt còn lại của lease cũ.

Ví dụ:

| Sự kiện | TTL | Quota mới | Diễn giải |
|---|---:|---:|---|
| Nhận lease A | 10 giây | 100 | Bắt đầu có 100 lượt trong 10 giây. |
| Đã dùng 30 lượt | Còn 7 giây | Còn 70 | Lease A còn 70 lượt. |
| Nhận lease B | 5 giây | 20 | Lease B thay lease A; quota hiện tại là 20 trong 5 giây. |
| Dùng 20 lượt | Còn 3 giây | 0 | Hết quota; chờ lease tiếp theo. |

Responder có thể gửi lease mới định kỳ để gia hạn hoặc thay đổi hạn ngạch theo tải hệ thống. Vì lease mới thay thế lease cũ, bộ phát lease cần chọn TTL và quota theo chính sách rõ ràng. Nếu muốn duy trì cửa sổ request liên tục, thời điểm phát lease kế tiếp cần được tính đến độ trễ truyền và xử lý.

Giao thức cũng cho phép responder ngăn các request mới bằng một lease có `Number of Requests = 0` hoặc `TTL = 0`. Đây là trường hợp đặc biệt để báo dừng cấp quyền. Với lease thông thường, cả TTL và Number of Requests đều phải lớn hơn `0`; giá trị `0` không phải một lease rỗng có thể chờ rồi tự có thêm quota.

## 8. Phân biệt lease quota với REQUEST_N

Hai cơ chế đều có số đếm nhưng kiểm soát hai việc khác nhau:

| Tiêu chí | LEASE | REQUEST_N |
|---|---|---|
| Phạm vi | Toàn bộ kết nối theo một hướng requester → responder. | Một stream cụ thể. |
| Điều gì được đếm? | Số request mới được mở. | Số payload response được phép phát. |
| Frame cấp quyền | `LEASE`, do responder gửi, `streamId=0`. | `REQUEST_STREAM` initial N hoặc `REQUEST_N`, do requester gửi trên stream ID. |
| Hết hạn | Có TTL; quota còn lại mất khi TTL hết. | Không có TTL trong cơ chế request-N; demand giảm khi payload được phát. |
| Khi hết số lượng | Không mở request mới cho đến lease tiếp theo. | Responder phải chờ requester cấp thêm demand trước khi phát thêm payload. |
| Ảnh hưởng stream đang chạy | Không tự hủy stream đã mở. | Điều tiết số payload tiếp theo của stream. |

Ví dụ, một client có lease 5 request có thể mở 5 request-stream. Mỗi request-stream sau đó vẫn cần demand riêng qua initial N và `REQUEST_N`. Có đủ quota lease không có nghĩa responder được phép phát vô hạn payload trên mỗi stream.

## 9. Cấu hình leasing trong RSocket Java

Trong RSocket Java, leasing không được bật mặc định. Client cần cấu hình `RSocketConnector.lease(...)` để báo rằng nó sẽ tuân thủ lease từ peer. Server cấu hình `RSocketServer.lease(...)` và cung cấp một luồng lease để cấp quyền cho requester.

### Bật lease ở phía client

```java
Mono<RSocket> connection = RSocketConnector.create()
    .lease(spec -> spec.maxPendingRequests(128))
    .connect(transport);
```

`maxPendingRequests(128)` giới hạn số request đang chờ lease được cấp. Trong RSocket Java 1.1.x, giá trị mặc định của hàng đợi này là 256; đặt bằng `0` khiến request được kết thúc ngay khi không có lease khả dụng thay vì chờ trong hàng đợi. Đây là chính sách của implementation, không phải một trường trong frame `LEASE`.

### Cấp lease ở phía server

```java
RSocketServer server = RSocketServer.create(socketAcceptor)
    .lease(spec -> spec.sender(() ->
        Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
            .map(tick -> Lease.create(Duration.ofSeconds(2), 100))
    ));

server.bind(transport).subscribe();
```

Ví dụ tạo một lease mới mỗi giây, mỗi lease cho tối đa 100 request trong 2 giây. Vì lease mới thay thế lease cũ, quota không cộng dồn. Trong hệ thống thực tế, nguồn lease nên dựa trên tải, số worker khả dụng, giới hạn downstream hoặc chính sách admission control của ứng dụng.

Hai phía cần bật leasing tương ứng. Nếu client không yêu cầu hoặc không cam kết tôn trọng lease trong `SETUP`, server không thể giả định rằng client sẽ chờ lease trước khi mở request. API cụ thể có thể khác giữa các phiên bản RSocket Java; kiểm tra Javadoc đúng phiên bản đang dùng khi cấu hình `LeaseSpec` và `LeaseSender`.

## 10. Xử lý request đang chờ lease

Khi quota cạn, request mới có thể được giữ lại ở requester cho đến khi có lease mới, tùy implementation và cấu hình. Hàng đợi này cần giới hạn để tránh việc request tích tụ không kiểm soát khi responder ngừng cấp lease.

Một chính sách ứng dụng nên xác định rõ:

1. **Giới hạn hàng đợi:** số request tối đa được phép chờ lease.
2. **Thời gian chờ:** mỗi request có timeout riêng hoặc deadline chung.
3. **Khi hàng đợi đầy:** từ chối sớm bằng lỗi overload/throttling ở tầng ứng dụng.
4. **Khi lease mới đến:** cho phép requester phát các request đang chờ theo thứ tự hoặc theo mức ưu tiên của ứng dụng.
5. **Khi kết nối đóng:** kết thúc request đang chờ và giải phóng tài nguyên.

Không nên để hàng đợi vô hạn. Nếu upstream tạo request nhanh hơn tốc độ responder cấp lease trong thời gian dài, bộ nhớ có thể tăng liên tục và độ trễ của các request cũ trở nên không còn hữu ích.

Ví dụ, với một API realtime, caller có thể chờ lease tối đa 500 ms. Nếu không có lease mới trong thời gian đó, ứng dụng trả lỗi tạm thời như `ServiceBusyException` để caller quyết định thử lại sau. Thời gian chờ này là chính sách ứng dụng, không phải TTL của lease.

## 11. Kết nối bị resume hoặc reconnect

Lease gắn với kết nối và không được mặc định kế thừa nguyên trạng khi resumption tạo lại kết nối transport. Theo giao thức, leasing phải được khởi động lại trên kết nối mới bằng frame `LEASE` từ responder. Requester không nên dùng số lượt còn lại hoặc thời hạn của lease thuộc kết nối cũ để mở request trên kết nối mới.

Khi dùng resume, ứng dụng cần:

- Chờ quá trình resume hoàn tất và nhận lease mới nếu kết nối sử dụng leasing.
- Cập nhật quota theo frame `LEASE` mới nhất.
- Không cộng số lượt còn lại của lease cũ vào quota mới.
- Xử lý request đang chờ theo trạng thái kết nối và chính sách retry của ứng dụng.

Reconnect tạo một kết nối mới cũng cần thương lượng và cấp lease lại. Việc khôi phục transport không đồng nghĩa quota cũ được khôi phục.

## 12. Chẩn đoán khi request bị treo hoặc REJECTED

Khi client không gửi được request mới hoặc nhận `REJECTED`, hãy kiểm tra theo thứ tự:

1. Trong `SETUP`, requester có bật cờ `L` hay không? Hai phía đã cấu hình leasing tương ứng chưa?
2. Sau `SETUP`, requester đã nhận frame `LEASE` nào chưa? Ghi lại TTL, quota và thời điểm nhận.
3. Frame `LEASE` gần nhất có thay thế lease trước đó không? Chỉ sử dụng quota của lease mới nhất.
4. Số request đã mở kể từ lease gần nhất là bao nhiêu? Đếm `REQUEST_RESPONSE`, `REQUEST_FNF`, `REQUEST_STREAM` và `REQUEST_CHANNEL`.
5. TTL còn hiệu lực không? Tính từ thời điểm nhận lease, không phải thời điểm server tạo hoặc gửi frame.
6. Request đang chờ lease ở hàng đợi hay đã được gửi lên wire? Kiểm tra giới hạn `maxPendingRequests` nếu dùng RSocket Java.
7. Nếu nhận `ERROR[REJECTED]`, kiểm tra stream ID và error data để xác định request bị từ chối do quota hoặc chính sách responder.
8. Nếu kết nối vừa resume/reconnect, kiểm tra đã nhận lease mới trên kết nối hiện tại chưa.

Ví dụ log:

```text
S -> C  LEASE            stream=0 ttl=5000ms requests=2
C -> S  REQUEST_RESPONSE stream=1 route=quotes.latest
C -> S  REQUEST_STREAM   stream=3 route=quotes.stream
C -> S  REQUEST_FNF      stream=5 route=audit.record
S -> C  ERROR            stream=5 code=REJECTED
S -> C  LEASE            stream=0 ttl=5000ms requests=10
C -> S  REQUEST_FNF      stream=7 route=audit.record
```

Client chỉ được cấp hai lượt nhưng đã mở hai request đầu tiên. Request thứ ba vượt quota và bị từ chối. Sau khi nhận lease mới, client có thể tiếp tục mở request theo quota mới.

## 13. Những lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Coi lease là số payload được phép nhận. | Giới hạn sai loại lưu lượng. | Lease đếm request mới; `REQUEST_N` mới đếm payload response. |
| Cộng quota của lease mới với lease cũ. | Requester có thể gửi vượt số lượt được cấp. | Frame `LEASE` mới nhất thay thế toàn bộ giá trị cũ. |
| Chỉ kiểm tra số lượt mà quên TTL. | Request được gửi sau khi lease đã hết hạn. | Kiểm tra cả quota còn lại và thời hạn tính từ lúc nhận frame. |
| Nghĩ TTL hết sẽ tự đóng kết nối. | Ứng dụng xử lý nhầm lỗi quota thành lỗi transport. | Lease hết chỉ ngăn request mới; vòng đời kết nối do chính sách riêng quản lý. |
| Nghĩ stream đang chạy bị hủy khi lease hết. | Làm mất kết quả của request đã được mở hợp lệ. | Lease không tự hủy stream đang tồn tại. |
| Nghĩ `REJECTED` đồng nghĩa server đã xử lý request. | Retry có thể bị bỏ qua không cần thiết hoặc xử lý sai. | Theo ngữ nghĩa giao thức, responder bảo đảm request bị `REJECTED` chưa được xử lý. |
| Bật lease ở client nhưng quên cấp lease ở server. | Requester chờ mãi vì không có quyền mở request. | Cấu hình nguồn cấp lease và lịch phát lease ở responder. |
| Để hàng đợi request chờ lease không giới hạn. | Tăng bộ nhớ và độ trễ khi downstream quá tải. | Giới hạn hàng đợi, timeout và từ chối sớm khi đầy. |
| Dùng quota cũ sau reconnect/resume. | Requester gửi request khi kết nối mới chưa được cấp quyền. | Chờ lease mới trên kết nối mới. |

## Tài liệu tham khảo

- [RSocket Protocol — LEASE frame và Lease Semantics](https://rsocket.io/about/protocol/#lease-frame-0x02) — cấu trúc TTL, Number of Requests, quy tắc thay thế lease và `ERROR[REJECTED]`.
- [RSocket Protocol — Connection Establishment](https://rsocket.io/about/protocol/#connection-establishment) — cờ `L` trong `SETUP` và trình tự kết nối có lease.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — tổng quan request throttling bằng leasing và tích hợp Spring.
- [RSocket Java 1.1.5 — RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html) — bật leasing ở requester.
- [RSocket Java 1.1.5 — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html) — cấp lease từ responder.
- [RSocket Java 1.1.5 — LeaseSpec](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/LeaseSpec.html) — cấu hình hàng đợi và nguồn cấp lease.

## Kết luận

Lease giới hạn số request mới mà requester được phép mở trong một khoảng thời gian. Mỗi `LEASE` cấp một quota và TTL; quota cạn hoặc TTL hết đều khiến quyền mở request mới trở về 0. Lease mới nhất thay thế lease cũ, còn request vượt giới hạn phải bị responder từ chối bằng `ERROR[REJECTED]`. Các stream đã mở vẫn có vòng đời riêng. Khi triển khai, hãy bật leasing đồng bộ qua `SETUP`, cấp lease theo tải hệ thống, giới hạn hàng đợi chờ lease và phân biệt lease quota với `REQUEST_N` để điều tiết payload trên từng stream.
