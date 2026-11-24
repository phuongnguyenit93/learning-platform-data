# Đọc log io.rsocket.FrameLogger và dựng lại trình tự trao đổi

Khi một request RSocket bị treo, nhận lỗi hoặc kết thúc sớm, log ứng dụng thường chỉ cho biết handler đã ném exception hoặc publisher đã kết thúc. Để biết chuyện gì xảy ra trên connection, cần quan sát các frame mà hai peer gửi và nhận. RSocket Java cung cấp logger category `io.rsocket.FrameLogger`; đặt logger này ở mức `DEBUG` sẽ in frame theo hướng gửi/nhận cùng stream ID, frame type, flags, độ dài và phần metadata/data.

`FrameLogger` giúp dựng lại trình tự trao đổi ở tầng protocol: client đã gửi `SETUP` chưa, server có trả `ERROR` trên connection hay không, request thuộc stream nào, consumer đã cấp `REQUEST_N` chưa, peer có gửi `CANCEL` hay `KEEPALIVE` không. Khi đọc log, cần ghép theo connection, hướng truyền và stream ID. Stream ID chỉ có ý nghĩa trong một connection; ID giống nhau ở hai connection khác nhau không đại diện cho cùng request.

Bài này hướng dẫn bật `FrameLogger`, hiểu cấu trúc log, đọc các frame quan trọng, dựng timeline cho request-response/stream/channel và phân biệt lỗi setup, lỗi stream, backpressure với lỗi transport. Bài cũng nêu cách dùng log an toàn vì phần dump có thể chứa dữ liệu payload và metadata nhạy cảm.

## 1. `io.rsocket.FrameLogger` là gì?

Trong RSocket Java, `io.rsocket.FrameLogger` là tên logger category được implementation dùng để ghi frame. Bạn bật mức `DEBUG` cho category này; không cần tự tạo instance `FrameLogger` hoặc thêm một handler Java chỉ để bật log.

Frame log thường có hai phần:

- Dòng logger cho biết timestamp, level, thread, category và hướng `sending` hoặc `receiving`.
- Phần mô tả frame có `Stream ID`, `Type`, `Flags`, `Length`, sau đó có thể là dump `Metadata` và `Data` dưới dạng hex/ASCII.

Ví dụ dạng log thường gặp:

```text
2026-11-22 10:15:01.120 DEBUG ... io.rsocket.FrameLogger : sending ->
Frame => Stream ID: 0 Type: SETUP Flags: 0b0 Length: 75
Data:

2026-11-22 10:15:01.125 DEBUG ... io.rsocket.FrameLogger : receiving ->
Frame => Stream ID: 0 Type: ERROR Flags: 0b0 Length: 24
Data:
...
```

Định dạng chi tiết, cách hiển thị flags và dump payload có thể thay đổi theo phiên bản RSocket Java và logger backend. Hãy đọc `Type`, `Stream ID` và nội dung frame theo semantics protocol, không phụ thuộc tuyệt đối vào một chuỗi log cụ thể.

### 1.1. Bật log trong Spring Boot

Trong `application.properties`:

```properties
logging.level.io.rsocket.FrameLogger=DEBUG
```

Hoặc `application.yml`:

```yaml
logging:
  level:
    io.rsocket.FrameLogger: DEBUG
```

Nếu cấu hình trực tiếp bằng Logback:

```xml
<configuration>
    <logger name="io.rsocket.FrameLogger" level="DEBUG"/>
</configuration>
```

Hãy xác minh log appender đang nhận mức `DEBUG`; chỉ đặt level ở logger nhưng appender lọc `INFO` thì frame vẫn không xuất hiện. Nếu ứng dụng chạy nhiều instance, bật log trên cả hai phía hoặc ít nhất trên peer cần điều tra.

### 1.2. Phân biệt FrameLogger, Reactor log và Netty wiretap

| Công cụ | Tầng quan sát | Thông tin chính |
|---|---|---|
| `io.rsocket.FrameLogger` | Frame protocol RSocket | Stream ID, frame type, flags, metadata/data |
| Reactor `log()` | Reactive Streams publisher/subscriber | `onSubscribe`, `request(n)`, `onNext`, `onError`, `onComplete`, cancel |
| Netty wiretap | I/O và transport | Sự kiện/byte ở tầng Netty, tùy cấu hình và transport |
| Application log | Nghiệp vụ | Route, command ID, kết quả handler, exception đã xử lý |

`FrameLogger` trả lời câu hỏi “frame nào đã đi qua connection?”. Reactor `log()` trả lời “publisher/subscriber đã phát signal và demand ra sao?”. Hai log có thể bổ sung cho nhau nhưng không thay thế nhau. Một lần `request(n)` ở Reactor cũng không nên được mặc định coi là đúng một frame `REQUEST_N` trên wire vì runtime/operator có thể tổng hợp demand.

## 2. Đọc các trường trong frame log

Một dòng frame thường có các trường sau:

| Trường | Ý nghĩa | Cách dùng khi chẩn đoán |
|---|---|---|
| `sending` / `receiving` | Hướng tương đối với process đang ghi log | Xác định local peer đang gửi hay nhận frame |
| `Stream ID` | ID của interaction hoặc `0` cho connection | Ghép các frame của cùng stream |
| `Type` | Loại frame như `SETUP`, `REQUEST_RESPONSE`, `PAYLOAD`, `ERROR` | Nhận diện bước trong protocol |
| `Flags` | Các bit có ý nghĩa phụ thuộc frame type | Đọc metadata, next, complete, follows, respond... |
| `Length` | Độ dài frame được logger hiển thị | Phát hiện frame bất thường hoặc payload lớn |
| `Metadata` | Metadata của frame nếu có | Kiểm tra route, MIME extension, authentication/context |
| `Data` | Data payload hoặc setup/error data | Kiểm tra schema, nội dung lỗi và payload |

### 2.1. Hướng gửi và nhận là tương đối với process

Trong log client:

- `sending ->` là client gửi frame ra server.
- `receiving ->` là client nhận frame từ server.

Trong log server, cùng frame đó sẽ có hướng ngược lại:

- `receiving ->` là server nhận frame từ client.
- `sending ->` là server gửi frame về client.

Vì vậy, một frame có thể xuất hiện hai lần trong log tập trung: một lần là `sending` ở client, một lần là `receiving` ở server. Đây không phải hai request khác nhau. Khi ghép log hai phía, dùng timestamp, connection identity và hướng để tránh đếm trùng.

### 2.2. Stream ID và phạm vi duy nhất

Stream ID `0` dành cho hoạt động ở cấp connection như `SETUP`, `KEEPALIVE`, `LEASE`, `METADATA_PUSH`, `RESUME` và lỗi connection. Stream ID lớn hơn `0` thuộc một interaction cụ thể.

Theo quy tắc cấp ID của protocol:

- Client khởi tạo stream bằng ID lẻ: `1`, `3`, `5`, ...
- Server khởi tạo stream bằng ID chẵn: `2`, `4`, `6`, ...
- ID phải duy nhất cho requester tương ứng trong phạm vi connection.

Do đó, ID `1` trong connection A không liên quan ID `1` trong connection B. Nếu logger không đưa connection ID vào prefix, hãy bổ sung correlation/connection identity ở application log hoặc log lifecycle để biết frame thuộc socket nào.

RSocket là giao thức hai chiều: sau khi connection được thiết lập, cả client và server đều có thể khởi tạo request. Vì thế, stream ID chẵn trong log server có thể là request do server khởi tạo đến client; không mặc định server chỉ trả lời stream ID lẻ.

### 2.3. Flags phụ thuộc frame type

Không diễn giải một bit flag theo cùng một nghĩa cho mọi frame. Một số flag thường gặp:

| Flag | Ý nghĩa ở frame tương ứng |
|---|---|
| `M` | Frame có metadata |
| `F` | Fragment hiện tại còn fragment theo sau |
| `N` | `PAYLOAD` chứa một phần tử `onNext` |
| `C` | `PAYLOAD` báo hoàn tất stream |
| `R` | `KEEPALIVE` yêu cầu peer phản hồi |
| `I` | Ignore flag cho extension/frame không được hiểu |

`PAYLOAD` có thể mang `N`, `C` hoặc cả hai. Logger có thể hiển thị dạng `NEXT`, `COMPLETE` hoặc `NEXT_COMPLETE`; đây là cách diễn giải flag của frame payload, không nhất thiết là các frame type độc lập trên wire. Một payload data rỗng vẫn có thể là một `NEXT` hợp lệ.

## 3. Những frame cần nhận diện

| Frame | Stream ID | Vai trò |
|---|---:|---|
| `SETUP` | 0 | Client bắt đầu protocol processing và gửi tham số connection |
| `LEASE` | 0 | Responder cấp quota request và thời gian hiệu lực |
| `KEEPALIVE` | 0 | Kiểm tra peer/connection còn hoạt động |
| `REQUEST_RESPONSE` | > 0 | Mở interaction một request, một response |
| `REQUEST_FNF` | > 0 | Gửi một chiều, không chờ response |
| `REQUEST_STREAM` | > 0 | Mở stream response và gửi initial request N |
| `REQUEST_CHANNEL` | > 0 | Mở interaction hai chiều với stream ở cả hai hướng |
| `REQUEST_N` | > 0 | Consumer yêu cầu thêm N payload |
| `CANCEL` | > 0 | Hủy một interaction đang chạy |
| `PAYLOAD` | > 0 | Gửi payload hoặc tín hiệu complete trên stream |
| `ERROR` | 0 hoặc > 0 | Lỗi connection hoặc lỗi một stream |
| `METADATA_PUSH` | 0 | Gửi metadata bất đồng bộ ở cấp connection |
| `RESUME` / `RESUME_OK` | 0 | Bắt đầu và chấp nhận khôi phục session nếu được hỗ trợ |

### 3.1. SETUP mang thông tin gì?

`SETUP` được client gửi với Stream ID `0`. Frame chứa các tham số quan trọng:

- Major/minor protocol version.
- Khoảng thời gian gửi `KEEPALIVE` và `Max Lifetime`.
- Resume token nếu client yêu cầu resumption.
- Data MIME type và Metadata MIME type.
- Setup metadata và setup data nếu được gửi.
- Flag liên quan metadata, resume và lease.

MIME type của data và metadata được khai báo riêng. Protocol truyền các giá trị này nhưng không tự diễn giải schema hoặc ý nghĩa nghiệp vụ của MIME type; ứng dụng và codec hai phía phải thống nhất định dạng.

Không có frame `SETUP_ACK` bắt buộc để báo setup thành công. Nếu server chấp nhận setup, connection tiếp tục hoạt động và các request có thể được gửi. Nếu server từ chối, thường sẽ thấy `ERROR` với Stream ID `0` và connection bị kết thúc.

### 3.2. ERROR: phân biệt lỗi connection và lỗi stream

Đây là quy tắc rất quan trọng khi đọc log:

- `ERROR` có Stream ID `0`: lỗi ở cấp connection, bao gồm lỗi trong quá trình setup hoặc resume.
- `ERROR` có Stream ID lớn hơn `0`: lỗi thuộc interaction/stream cụ thể; connection có thể vẫn hoạt động.

Một số mã lỗi chuẩn:

| Error code | Giá trị | Ý nghĩa |
|---|---:|---|
| `INVALID_SETUP` | `0x00000001` | SETUP không hợp lệ đối với server |
| `UNSUPPORTED_SETUP` | `0x00000002` | Một hoặc nhiều tham số SETUP không được hỗ trợ |
| `REJECTED_SETUP` | `0x00000003` | Server chủ động từ chối setup; error data có thể nêu lý do |
| `REJECTED_RESUME` | `0x00000004` | Server từ chối khôi phục session |
| `CONNECTION_ERROR` | `0x00000101` | Connection đang bị kết thúc; có thể đóng ngay |
| `CONNECTION_CLOSE` | `0x00000102` | Kết thúc connection sau khi các stream đang chạy kết thúc theo semantics |
| `APPLICATION_ERROR` | `0x00000201` | Handler/application phát lỗi trên stream |
| `REJECTED` | `0x00000202` | Responder từ chối request hợp lệ và bảo đảm chưa xử lý request |
| `CANCELED` | `0x00000203` | Responder hủy request; có thể đã bắt đầu có side effect |
| `INVALID` | `0x00000204` | Request không hợp lệ |

Error data thường là chuỗi UTF-8, nhưng frame dump có thể hiển thị bytes dạng hex. Hãy giải mã nội dung theo encoding của implementation trước khi kết luận.

## 4. Bật log và giới hạn phạm vi thu thập

Trong Spring Boot, có thể bật logger tạm thời bằng cấu hình:

```properties
logging.level.io.rsocket.FrameLogger=DEBUG
```

Khi điều tra xong, hạ level về `INFO` hoặc mức mặc định. Với hệ thống có nhiều connection, không nên giữ frame logging toàn cục ở `DEBUG` trong thời gian dài vì lượng log có thể tăng nhanh theo số stream và payload.

FrameLogger có thể dump metadata và data payload. Những vùng này có thể chứa:

- Access token hoặc authentication metadata.
- User ID, device ID, tenant ID.
- Nội dung command, event, dữ liệu cá nhân hoặc thông tin nghiệp vụ.
- Setup data và error message có thông tin nội bộ.

Chỉ bật trong môi trường test/staging hoặc một cửa sổ điều tra ngắn có kiểm soát. Dùng quyền truy cập log phù hợp, giới hạn retention, tránh gửi log thô ra hệ thống bên ngoài và tuân thủ chính sách masking/redaction. Không giả định rằng logger tự động che token hoặc dữ liệu nhạy cảm.

## 5. Quy trình dựng lại trình tự trao đổi

Một quy trình thực tế giúp tránh nhầm frame giữa nhiều connection:

1. **Chọn khoảng thời gian:** bắt đầu trước khi client kết nối và kết thúc sau lỗi/timeout/disconnect.
2. **Xác định peer:** phân biệt log client, server, gateway và transport proxy.
3. **Xác định connection:** dùng connection key, remote endpoint hoặc correlation context nếu có. Không dùng stream ID một mình làm khóa toàn cục.
4. **Tách hướng:** đánh dấu `sending` và `receiving` theo từng process.
5. **Tách connection-level frame:** đọc các frame Stream ID `0` trước để biết setup, keepalive, lease, resume và lỗi connection.
6. **Nhóm theo stream ID:** ghép request frame, payload, request N, cancel, complete và error của cùng stream.
7. **Đọc metadata/data:** xác định route, MIME type, setup metadata và nội dung error nếu có thể giải mã an toàn.
8. **Đánh dấu terminal event:** `PAYLOAD` có `C`, `ERROR` hoặc `CANCEL` cho biết stream kết thúc theo cách nào.
9. **Đối chiếu application log:** ghép route, command ID, trace ID, handler start/end và downstream latency.
10. **Viết timeline:** ghi thời điểm, peer, hướng, stream ID, frame và diễn giải; đánh dấu rõ sự kiện quan sát được với giả thuyết.

Các frame từ cùng một sender được transport bảo toàn thứ tự. Khi ghép log từ client và server, timestamp có thể lệch do clock; cần đồng bộ thời gian và không suy ra quan hệ nhân quả chỉ từ vài mili giây chênh lệch. Trong trường hợp khó, chọn log một phía làm timeline chính rồi dùng log peer để xác nhận.

## 6. Ví dụ timeline: request-response thành công

Giả sử client mở connection rồi gửi một request `device.status`:

```text
Client sending:   SETUP              stream=0
Server receiving: SETUP              stream=0
Client sending:   REQUEST_RESPONSE   stream=1
Server receiving: REQUEST_RESPONSE   stream=1
Server sending:   NEXT_COMPLETE      stream=1
Client receiving: NEXT_COMPLETE      stream=1
```

Diễn giải:

1. Client gửi `SETUP` ở cấp connection.
2. Server nhận setup; không có `SETUP_ACK` riêng trong trình tự thông thường.
3. Client khởi tạo request-response với Stream ID lẻ `1`.
4. Server xử lý request và trả một payload có cả `NEXT` và `COMPLETE`.
5. Client nhận response; stream kết thúc nhưng connection vẫn có thể tiếp tục phục vụ request khác.

Trong log thực tế, metadata của `REQUEST_RESPONSE` có thể là composite metadata chứa routing extension. FrameLogger có thể chỉ dump bytes, không hiển thị sẵn chuỗi route. Hãy giải mã metadata bằng MIME type/codec tương ứng hoặc đối chiếu application log.

## 7. Ví dụ timeline: SETUP bị từ chối

Một trình tự setup bị từ chối có thể trông như sau:

```text
Client sending:   SETUP   stream=0  version=major.minor  dataMime=... metadataMime=...
Server receiving: SETUP   stream=0
Server sending:   ERROR   stream=0  code=UNSUPPORTED_SETUP
Client receiving: ERROR   stream=0  code=UNSUPPORTED_SETUP
Transport:        closed
```

Đây là lỗi ở cấp connection, không phải lỗi của một route request. Kiểm tra:

- Protocol major/minor mà client gửi và phiên bản server hỗ trợ.
- Data MIME type và Metadata MIME type có được server hỗ trợ không.
- Các tham số setup như keepalive/lifetime, lease hoặc resume có tương thích không.
- Setup metadata có đúng encoding/extension và có được policy chấp nhận không.
- Authentication/authorization ở thời điểm setup có bị từ chối không.

`UNSUPPORTED_SETUP` cho biết một hoặc nhiều tham số setup không được hỗ trợ. `INVALID_SETUP` cho biết frame/parameters không hợp lệ. `REJECTED_SETUP` thường phản ánh quyết định từ chối của server; error data có thể chứa lý do như policy hoặc authentication. Mã lỗi thực tế phụ thuộc cách server phân loại và implementation.

Nếu log client có `SETUP` nhưng không thấy server nhận, chưa thể kết luận MIME type sai: lỗi có thể xảy ra trước khi frame tới RSocket, ví dụ DNS, TCP connect, TLS handshake, WebSocket upgrade, proxy hoặc firewall. FrameLogger chỉ quan sát frame sau khi transport đã chuyển dữ liệu đến RSocket layer.

## 8. MIME type và metadata: đọc đúng tầng

SETUP mang hai MIME type riêng:

- **Data MIME type:** định dạng của payload data, ví dụ JSON hoặc CBOR.
- **Metadata MIME type:** định dạng của metadata, có thể là composite metadata chứa routing/authentication extension.

Một số tình huống:

| Dấu hiệu log | Khả năng cần kiểm tra |
|---|---|
| `ERROR` stream 0 + `UNSUPPORTED_SETUP` | Server không hỗ trợ một tham số setup, có thể là MIME type hoặc tính năng |
| `ERROR` stream 0 + `REJECTED_SETUP` | Server từ chối setup theo policy; đọc error data và auth log |
| Setup được chấp nhận nhưng request có `ERROR` stream > 0 | Codec, route, metadata extension hoặc handler có thể lỗi ở cấp stream |
| Request có metadata flag nhưng không giải mã được bytes | MIME type/metadata codec hoặc composite metadata format không khớp |
| Route không xuất hiện trong dump | FrameLogger có thể đang in bytes; cần decode metadata thay vì kết luận route rỗng |

Protocol truyền MIME type nhưng không tự kiểm tra schema ứng dụng. Một MIME type hợp lệ về mặt protocol vẫn có thể không có decoder tương ứng trong Spring/codec của service. Khi setup được chấp nhận nhưng codec thất bại ở request đầu tiên, lỗi có thể xuất hiện dưới dạng stream-level `ERROR`, không phải `UNSUPPORTED_SETUP`.

## 9. Dựng lại request-stream và flow control

Ví dụ client mở request-stream với initial demand bằng `2`:

```text
Client sending:   REQUEST_STREAM  stream=3  initialRequestN=2
Server receiving: REQUEST_STREAM  stream=3
Server sending:   PAYLOAD         stream=3  NEXT
Server sending:   PAYLOAD         stream=3  NEXT
Client receiving: PAYLOAD         stream=3  NEXT
Client receiving: PAYLOAD         stream=3  NEXT
Client sending:   REQUEST_N       stream=3  n=2
Server receiving: REQUEST_N       stream=3  n=2
Server sending:   PAYLOAD         stream=3  NEXT
Server sending:   PAYLOAD         stream=3  COMPLETE
```

Diễn giải:

- `REQUEST_STREAM` mở stream và cấp initial request N.
- Server chỉ được phát trong phạm vi demand đã cấp.
- Khi client tiêu thụ và cần thêm dữ liệu, client gửi `REQUEST_N`.
- `PAYLOAD` có `NEXT` chuyển một phần tử; `COMPLETE` kết thúc stream.

Nếu producer ngừng phát sau khi dùng hết initial demand và log chưa có `REQUEST_N` mới, đó có thể là backpressure hoạt động bình thường. Hãy kiểm tra subscriber có đang xử lý chậm, đang buffer hoặc đã dừng yêu cầu thêm không. Không coi việc thiếu `PAYLOAD` là lỗi nếu chưa đối chiếu demand và nguồn dữ liệu.

`REQUEST_N` đếm số payload, không phải byte. Một request N nhỏ vẫn có thể cho phép payload lớn; muốn chẩn đoán memory pressure cần xem thêm payload length và queue/buffer metrics.

## 10. Dựng lại request-channel hai chiều

`REQUEST_CHANNEL` mở interaction có dữ liệu ở cả hai hướng. Sau frame mở channel, các payload tiếp theo của mỗi hướng được gửi bằng `PAYLOAD`. Mỗi consumer cấp demand cho producer ở hướng tương ứng bằng `REQUEST_N`.

| Hướng | Producer | Consumer | Dấu hiệu trong log |
|---|---|---|---|
| Client → Server | Client | Server | Client gửi `PAYLOAD`; server gửi `REQUEST_N` để cấp credit |
| Server → Client | Server | Client | Server gửi `PAYLOAD`; client gửi `REQUEST_N` để cấp credit |

Khi dựng timeline channel, không gộp hai chiều thành một chuỗi “request/response” đơn giản. Hãy nhóm theo cùng stream ID nhưng vẫn ghi rõ peer và hướng. Một bên có thể tiếp tục gửi trong khi bên kia tạm dừng vì chưa được cấp demand.

## 11. CANCEL, FNF và các frame connection-level

### 11.1. CANCEL

`CANCEL` có Stream ID lớn hơn `0` và yêu cầu hủy một interaction đang chạy. Nó có thể xuất hiện khi:

- Client dùng `take(n)` hoặc người dùng rời màn hình.
- Timeout hủy upstream.
- Một service không còn cần kết quả.
- Connection lifecycle hủy các stream phụ thuộc.

Nếu thấy `CANCEL`, hãy kiểm tra application log để xác định ai khởi tạo cancel và server có dừng công việc/cleanup resource không. `CANCEL` là tín hiệu điều khiển bình thường trong reactive flow, không tự động có nghĩa request lỗi.

### 11.2. FIRE-AND-FORGET

`REQUEST_FNF` là request một chiều. Không chờ response payload trên stream đó. Vì vậy, không thấy `PAYLOAD` trả về sau `REQUEST_FNF` là hành vi bình thường. Nếu nghiệp vụ cần xác nhận command đã được xử lý, phải có acknowledgement ở tầng ứng dụng hoặc dùng request-response.

### 11.3. KEEPALIVE

`KEEPALIVE` luôn dùng Stream ID `0`. Client thường gửi định kỳ với flag `R` yêu cầu phản hồi; peer trả `KEEPALIVE` với flag respond tắt và echo data theo protocol. Nếu thấy keepalive gửi đi nhưng không có phản hồi trong lifetime đã cấu hình, hãy đối chiếu:

- Keepalive interval và max lifetime trong SETUP.
- Log ở peer nhận và network/proxy giữa hai bên.
- Event-loop delay hoặc CPU starvation.
- Connection close/error ngay sau khoảng timeout.

Keepalive chỉ cho biết connection peer còn trao đổi frame theo cơ chế protocol; nó không chứng minh handler nghiệp vụ hoặc database đang khỏe.

### 11.4. LEASE, METADATA_PUSH và RESUME

- `LEASE` dùng Stream ID `0`, cấp số request được phép gửi trong một khoảng TTL. Nếu lease hết hạn hoặc quota bằng 0, requester có thể không được phép mở request mới cho đến lease tiếp theo.
- `METADATA_PUSH` dùng Stream ID `0`, gửi metadata bất đồng bộ ở cấp connection.
- `RESUME` và `RESUME_OK` dùng Stream ID `0`. Nếu server trả `ERROR[REJECTED_RESUME]`, session không thể tiếp tục bằng resumption; client cần xử lý full reconnect/sync theo thiết kế ứng dụng.

## 12. Phân biệt lỗi SETUP, lỗi stream và lỗi transport

| Dấu hiệu | Phạm vi | Hướng điều tra |
|---|---|---|
| Không có frame `SETUP` ở client | Trước hoặc trong lúc tạo RSocket connection | Kiểm tra client lifecycle, logger level và transport connect |
| Client gửi `SETUP`, server không nhận | Có thể lỗi trước RSocket layer | DNS, TCP, TLS, WebSocket upgrade, proxy/firewall |
| Server nhận `SETUP`, gửi `ERROR` stream 0 | Connection establishment | Version, MIME type, setup metadata, auth/policy, resume/lease support |
| SETUP không bị từ chối, request sau đó lỗi stream > 0 | Interaction cụ thể | Route, codec, metadata decode, handler và downstream |
| `REQUEST_STREAM` rồi không có payload sau khi hết demand | Flow control | Có `REQUEST_N` mới chưa, producer có dữ liệu không, consumer có đang xử lý không |
| `REQUEST_FNF` không có response | Bình thường theo interaction type | Xác minh side effect bằng application log/ack riêng |
| `CANCEL` trước khi response hoàn tất | Stream bị hủy | Tìm timeout, `take`, client disconnect hoặc logic cancel |
| `KEEPALIVE` không được echo và connection đóng | Connection liveness | Timeout, event loop, network, proxy idle timeout |
| `ERROR` stream 0 sau khi đã hoạt động | Connection bị kết thúc | Close reason, protocol/transport error và shutdown |

Một `ERROR` stream ID `0` là dấu hiệu quan trọng cho lỗi cấp connection. Một `ERROR` trên stream ID `1`, `3`, `2`... thường chỉ kết thúc interaction tương ứng; các stream khác trên connection có thể tiếp tục.

## 13. Mẫu timeline điều tra thực tế

Khi báo cáo một lỗi, hãy tạo bảng timeline thay vì chỉ đính kèm hàng trăm dòng log:

| Thời điểm | Peer | Hướng | Stream ID | Frame | Diễn giải |
|---|---|---|---:|---|---|
| 10:15:01.120 | Client | sending | 0 | SETUP | Bắt đầu connection |
| 10:15:01.123 | Server | receiving | 0 | SETUP | Server nhận tham số setup |
| 10:15:01.130 | Client | sending | 1 | REQUEST_RESPONSE | Mở request route `device.status` |
| 10:15:01.132 | Server | receiving | 1 | REQUEST_RESPONSE | Server nhận request |
| 10:15:03.131 | Server | sending | 1 | ERROR | Handler/downstream lỗi hoặc request bị từ chối |
| 10:15:03.134 | Client | receiving | 1 | ERROR | Caller nhận lỗi stream |

Đây là dữ liệu minh họa. Trong sự cố thật, thay route/ID/thời điểm bằng giá trị đã xác minh từ log. Ghi rõ điều nào là quan sát trực tiếp và điều nào là giả thuyết.

Một timeline tốt nên có:

- Environment, service version, transport và endpoint đã che thông tin nhạy cảm.
- Connection key hoặc correlation ID để phân biệt nhiều connection.
- Timestamp và timezone.
- Peer và hướng `sending`/`receiving`.
- Stream ID, frame type, flags và error code.
- Route/metadata đã decode nếu có.
- Application handler start/end và downstream error.
- Kết luận ngắn cùng bằng chứng frame hỗ trợ kết luận.

## 14. Những sai lầm thường gặp khi đọc FrameLogger

| Sai lầm | Vì sao sai | Cách đọc đúng |
|---|---|---|
| Coi `io.rsocket.FrameLogger` là class cần khởi tạo | Đây là logger category được bật bằng log level | Đặt `io.rsocket.FrameLogger=DEBUG` |
| Ghép stream ID mà không phân biệt connection | ID chỉ duy nhất trong phạm vi connection/requester | Nhóm theo connection rồi mới theo stream ID |
| Coi `sending` luôn là client gửi | Hướng là tương đối với process ghi log | Xác định log đến từ client hay server |
| Coi mọi `ERROR` là connection chết | Error trên stream > 0 chỉ thuộc interaction đó | Kiểm tra Stream ID của ERROR |
| Coi thiếu response sau FNF là lỗi | FNF không có response | Dùng application acknowledgement nếu cần |
| Coi không có PAYLOAD là producer lỗi | Có thể consumer chưa cấp demand | Kiểm tra initial request N và REQUEST_N |
| Đọc flags không theo frame type | Bit có ý nghĩa khác nhau theo frame | Diễn giải flags theo loại frame |
| Coi metadata hex là route rỗng | Composite metadata có thể chưa được decode | Giải mã bằng metadata MIME/extension phù hợp |
| Coi SETUP thành công phải có SETUP_ACK | Protocol không yêu cầu frame ack riêng | Xác nhận connection tiếp tục và request được xử lý |
| Bật DEBUG lâu dài trong production | Payload/metadata có thể nhạy cảm và log rất lớn | Bật ngắn hạn, giới hạn phạm vi và bảo vệ log |

## 15. Runbook nhanh khi gặp lỗi

1. Bật `io.rsocket.FrameLogger` ở `DEBUG` trong thời gian điều tra có kiểm soát.
2. Thu log client và server cùng khoảng thời gian; ghi rõ timezone và instance.
3. Xác định connection và tìm `SETUP`/`ERROR` stream `0` trước.
4. Nếu setup bị từ chối, đọc error code/data rồi đối chiếu version, data/metadata MIME type, setup metadata và auth policy.
5. Nếu setup thành công, chọn stream ID của request lỗi và dựng trình tự request → payload/request N → complete/error/cancel.
6. Kiểm tra `REQUEST_N` để xác định consumer có cấp demand; không kết luận producer lỗi khi hết credit.
7. Giải mã metadata bằng đúng MIME type nếu cần tìm route hoặc authentication extension.
8. Đối chiếu application log/trace để xác định handler và downstream gây lỗi.
9. Mask dữ liệu nhạy cảm, lưu phần timeline tối thiểu đủ bằng chứng.
10. Tắt DEBUG sau khi thu thập và ghi lại kết luận/runbook.

Nếu không có frame log ở server dù client đã ghi `sending`, hãy điều tra transport/TLS/proxy trước khi sửa route. Nếu có `ERROR` stream ID `0`, tập trung vào connection/setup. Nếu `ERROR` chỉ xuất hiện trên stream cụ thể, giữ connection và các stream khác trong phạm vi kiểm tra trước khi quyết định reconnect toàn bộ.

## 16. Tài liệu tham khảo

- [RSocket Java – Debugging](https://github.com/rsocket/rsocket-java#debugging): hướng dẫn bật logger `io.rsocket.FrameLogger` ở mức debug.
- [RSocket Protocol](https://rsocket.io/about/protocol/): frame header, stream ID, SETUP, ERROR, request/stream/channel, flow control và resumption.
- [RSocket Java 1.1.5 – FrameType Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/frame/FrameType.html): tên frame và mô tả các loại frame trong API Java.
- [RSocket Client CLI – FrameLogger examples](https://github.com/making/rsc#log-options): ví dụ output `sending`/`receiving`, frame header và dump metadata/data.
