# Thực nghiệm ngắt mạng, resume thành công và chuyển sang phiên mới

RSocket có thể khôi phục một phiên đang hoạt động sau khi transport connection bị gián đoạn, nếu cả hai peer đã bật resume và vẫn giữ đủ trạng thái cần thiết. Quá trình này dùng frame `RESUME` và `RESUME_OK` để nối lại phiên cũ, đồng thời phát lại các frame chưa được peer xác nhận. Nếu phiên đã hết hạn, resume buffer không còn đủ dữ liệu hoặc peer không còn trạng thái phiên, ứng dụng phải tạo một RSocket session mới bằng `SETUP`.

Bài học này hướng dẫn một thí nghiệm có thể lặp lại để quan sát cả hai nhánh: resume thành công và fallback sang phiên mới. Điểm quan trọng là giữ nguyên tiến trình ứng dụng trong lần thử resume, ngắt đường truyền ở giữa để tạo lỗi transport, sau đó so sánh frame, stream ID và chuỗi dữ liệu trước/sau khi kết nối lại.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt reconnect transport, resume phiên RSocket và tạo session mới.
- Giải thích vai trò của resume token, resume buffer, vị trí frame và thời hạn phiên.
- Thiết kế thí nghiệm ngắt mạng mà vẫn giữ trạng thái phiên ở hai peer.
- Nhận diện `RESUME`, `RESUME_OK` và lỗi `REJECTED_RESUME`.
- Xác minh stream đang chạy tiếp tục sau resume và hiểu giới hạn khi resume thất bại.
- Thiết kế fallback bằng `SETUP`, khôi phục subscription và tránh xử lý nghiệp vụ trùng lặp.
- Đọc log, metric và kết quả thử nghiệm để chẩn đoán sự cố.

## 1. Ba kết quả khác nhau sau khi mất mạng

Khi TCP hoặc WebSocket bị ngắt, ứng dụng không nên gọi mọi lần kết nối lại là “resume”. Có ba kết quả khác nhau:

| Kết quả | Điều xảy ra | Trạng thái stream |
|---|---|---|
| Reconnect transport để resume | Mở transport mới rồi gửi `RESUME` với token của phiên cũ | Phiên logic cũ và các stream có thể tiếp tục nếu server chấp nhận |
| Resume thất bại | Server không còn phiên hoặc không thể phát lại đủ frame | Phiên cũ không thể tiếp tục; các stream cũ không được phục hồi bằng cách tự động |
| Tạo session mới | Mở transport mới và gửi `SETUP` | Bắt đầu phiên mới; ứng dụng phải khởi tạo lại các tương tác cần thiết |

Resume không chỉ là mở socket mới. Client và server phải nhận diện đúng phiên cũ, còn giữ trạng thái protocol và có đủ frame chưa được xác nhận để đồng bộ lại hai phía.

## 2. Điều kiện cần để resume hoạt động

Resume phải được bật ngay từ lúc thiết lập phiên. Trong frame `SETUP`, client đặt cờ resume (`R`) và gửi resume identification token. Server phải hỗ trợ resume và chấp nhận yêu cầu đó. Cả hai phía cần giữ trạng thái phiên cùng các frame cần thiết cho việc phát lại.

Các điều kiện thực tế gồm:

1. Client và server đều sử dụng implementation hỗ trợ RSocket resumption.
2. Client bật resume trong cấu hình trước khi gửi `SETUP`.
3. Phiên đã được thiết lập với resume token hợp lệ, duy nhất và được bảo vệ.
4. Cả hai peer còn giữ trạng thái của phiên cũ khi transport bị ngắt.
5. Các frame cần phát lại vẫn còn trong resume buffer ở hai phía.
6. Thời gian gián đoạn nằm trong cửa sổ phiên còn hiệu lực.
7. Client reconnect tới đúng peer hoặc cụm có thể tìm lại trạng thái phiên tương ứng.

Nếu client không bật cờ resume trong `SETUP`, connection đó không tự nhiên có khả năng resume sau này. Việc chỉ thêm một token khi reconnect không thể biến một phiên thường thành phiên có resume.

### Resume token và vị trí frame

Resume token là định danh để server tìm phiên cũ. Token không phải access token nghiệp vụ và không thay thế xác thực. Nên tạo token đủ ngẫu nhiên, gắn với đúng phiên và không ghi nguyên giá trị vào log.

Để đồng bộ dữ liệu, giao thức theo dõi vị trí frame đã được nhận ở mỗi hướng. Khi gửi `RESUME`, client cung cấp resume token và thông tin vị trí cần thiết để hai bên xác định frame nào đã được nhận, frame nào còn phải phát lại. Server trả `RESUME_OK` khi chấp nhận việc nối lại và cung cấp thông tin vị trí tương ứng. Sau đó, các frame còn thiếu được phát lại theo thứ tự giao thức.

Các vị trí này thuộc cơ chế resumption của connection; chúng không phải sequence number nghiệp vụ trong payload. Ứng dụng vẫn nên có event ID hoặc sequence number riêng nếu cần đối soát nghiệp vụ.

## 3. Những frame cần quan sát

Các frame resumption hoạt động ở phạm vi connection, do đó dùng stream ID bằng 0.

| Frame | Frame type | Vai trò |
|---|---:|---|
| `SETUP` | `0x01` | Thiết lập phiên mới; có thể bật resume bằng cờ `R` và token |
| `RESUME` | `0x0D` | Yêu cầu nối lại một phiên đã tồn tại bằng resume token và thông tin vị trí frame |
| `RESUME_OK` | `0x0E` | Server chấp nhận resume và xác nhận thông tin đồng bộ |
| `ERROR[REJECTED_RESUME]` | Error code `0x00000004` | Báo không thể chấp nhận yêu cầu resume |
| `REQUEST_STREAM` / `PAYLOAD` | Stream-level | Mở tương tác hoặc mang dữ liệu trên stream sau khi phiên hoạt động |

Không có `SETUP` mới trong nhánh resume thành công. Client gửi `RESUME` trên transport mới để khôi phục session đã tồn tại. Ngược lại, khi chuyển sang session mới, client phải thực hiện `SETUP` và không thể tiếp tục dùng stream ID cùng trạng thái của phiên cũ như thể chưa có gián đoạn.

## 4. Chuẩn bị môi trường thí nghiệm

Dùng ba thành phần để có thể ngắt đường truyền mà không dừng hai peer:

- **RSocket server:** cung cấp một request-stream phát dữ liệu có sequence tăng dần.
- **RSocket client:** đăng ký stream và ghi lại các sequence đã nhận.
- **TCP proxy có khả năng fault injection:** chuyển tiếp kết nối client-server và cho phép cắt hoặc làm gián đoạn đường truyền theo thời gian.

Có thể dùng Toxiproxy hoặc một proxy thử nghiệm tương đương. Cấu hình client kết nối qua proxy thay vì kết nối trực tiếp tới server. Khi cần tạo sự cố, thay đổi trạng thái proxy để cắt luồng TCP trong khi vẫn giữ client process, server process và trạng thái RSocket trong bộ nhớ.

Không dùng thao tác graceful dispose của RSocket session để mô phỏng mất mạng. Đóng session một cách chủ động có thể giải phóng trạng thái mà resume cần. Mục tiêu của thí nghiệm là làm hỏng transport path trong khi hai peer vẫn còn giữ session state.

### Dữ liệu thử nghiệm

Server phát một phần tử có số thứ tự tăng dần, ví dụ:

~~~java
Flux<Reading> readings(String deviceId) {
    return Flux.interval(Duration.ofMillis(100))
            .map(sequence -> new Reading(deviceId, sequence));
}
~~~

Client ghi lại từng sequence đã nhận. Có thể dùng một request-stream duy nhất và để stream chạy liên tục trong suốt thời gian thí nghiệm.

Với request-channel, có thể mở rộng bài thử bằng cách gửi các lệnh có sequence từ client lên server, đồng thời server phát acknowledgement theo một stream output. Như vậy có thể quan sát dữ liệu ở cả hai hướng của cùng một channel.

## 5. Cấu hình resume trước khi kết nối

Ở tầng RSocket Java, resume được cấu hình trên connector trước khi mở connection. Tên builder method và cách cấp token có thể khác theo phiên bản rsocket-java; cần dùng API của dependency thực tế trong dự án.

Ví dụ minh họa ý tưởng cấu hình:

~~~java
Resume resume = new Resume()
        .sessionDuration(Duration.ofMinutes(2))
        .streamTimeout(Duration.ofMinutes(2));

RSocketConnector connector = RSocketConnector.create()
        .resume(resume);
~~~

Cấu hình này minh họa thời gian giữ phiên và stream. Trong ứng dụng thực tế, cần kiểm tra thêm cách implementation tạo hoặc cấp resume token, cách cấu hình resume store/buffer và cách connector tìm lại transport khi cần reconnect.

Hai khoảng thời gian có ý nghĩa khác nhau:

- **Session duration:** thời gian implementation giữ phiên có thể resume sau khi connection bị gián đoạn.
- **Stream timeout:** giới hạn thời gian stream có thể tiếp tục tồn tại trong quá trình resumption, tùy implementation.

Không đặt các khoảng thời gian quá ngắn nếu mạng thường xuyên chập chờn. Ngược lại, giữ phiên quá lâu làm tăng số session và lượng buffer trong bộ nhớ. Cần đo tải thực tế để chọn giới hạn.

## 6. Thí nghiệm A: ngắt mạng và resume thành công

Mục tiêu là chứng minh stream cũ tiếp tục trên cùng session logic sau khi transport được mở lại.

### Bước 1: Mở phiên có resume

Khởi động server và client với resume được bật ở cả hai phía. Client kết nối qua proxy, hoàn tất `SETUP` và bắt đầu request-stream. Ghi nhận:

- Thời điểm kết nối và trạng thái session.
- Resume token dưới dạng hash hoặc mã rút gọn; không log token nguyên bản.
- Stream ID của request-stream.
- Sequence đầu tiên và cuối cùng đã nhận.
- Frame setup và thông tin keepalive.

Để stream chạy đủ lâu nhằm có dữ liệu trước thời điểm ngắt.

### Bước 2: Cắt transport đột ngột

Dùng proxy cắt kết nối TCP hoặc tạo một khoảng blackhole ngắn. Không dừng client hay server. Hai process cần còn sống để giữ resume state.

Trong thời gian mất mạng, server tiếp tục tạo dữ liệu. Các frame chưa được xác nhận phải được giữ trong resume buffer nếu còn dung lượng. Client cũng giữ trạng thái cần thiết để gửi thông tin resume.

Ghi lại thời điểm mất kết nối, thời gian gián đoạn và số lượng dữ liệu server tiếp tục phát.

### Bước 3: Khôi phục đường truyền

Sau một khoảng ngắn hơn session duration, khôi phục proxy. Client mở transport mới và gửi `RESUME` với token của phiên cũ.

Nếu server còn giữ session và buffer đủ dữ liệu, server trả `RESUME_OK`. Hai phía đồng bộ vị trí frame và phát lại phần frame còn thiếu.

### Bước 4: Xác minh stream tiếp tục

Quan sát các dấu hiệu sau:

- Có `RESUME` rồi `RESUME_OK`, không có `SETUP` mới.
- Stream ID của request-stream được giữ nguyên.
- Client nhận lại dữ liệu bị gián đoạn theo thứ tự protocol.
- Stream tiếp tục phát dữ liệu mới sau phần replay.
- Không cần tạo subscription mới chỉ để tiếp tục stream đã resume.

Sơ đồ luồng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Fault proxy
    participant S as RSocket server
    C->>P: Transport connection
    P->>S: Chuyển tiếp kết nối
    C->>S: SETUP (cờ R, resume token)
    C->>S: REQUEST_STREAM (stream ID 1)
    S-->>C: PAYLOAD 1, 2, 3
    Note over P: Cắt đường truyền, giữ hai process
    S-xP: Các frame tiếp theo được giữ trong resume buffer
    Note over C,S: Transport bị gián đoạn
    C->>P: Mở transport mới
    P->>S: Chuyển tiếp kết nối mới
    C->>S: RESUME (token và vị trí frame)
    S-->>C: RESUME_OK
    S-->>C: Replay các frame còn thiếu
    S-->>C: PAYLOAD tiếp theo trên stream 1
~~~

### Kết quả mong đợi

Phiên logic không bị thay thế. Transport vật lý đã đổi, nhưng các stream còn hiệu lực được tiếp tục từ trạng thái phiên đã lưu. Dữ liệu replay và dữ liệu mới được xử lý theo thứ tự frame của giao thức.

## 7. Thí nghiệm B: resume bị từ chối và tạo session mới

Mục tiêu là xác minh nhánh phục hồi khi phiên cũ không còn khả năng resume.

Có nhiều cách tạo điều kiện thất bại có kiểm soát:

- Giữ mạng gián đoạn lâu hơn session duration đã cấu hình.
- Làm resume buffer không còn giữ đủ frame cần phát lại.
- Khởi động lại server nếu resume state chỉ nằm trong bộ nhớ của process.
- Dùng token không khớp hoặc token của một phiên khác trong môi trường thử nghiệm.
- Tắt resume ở server hoặc dùng server implementation không hỗ trợ.

### Bước 1: Tạo phiên và stream như thí nghiệm A

Thiết lập session có resume, mở request-stream và ghi nhận token, stream ID, sequence cuối cùng đã nhận.

### Bước 2: Làm phiên cũ không còn khả năng resume

Cắt mạng và chờ quá session duration, hoặc làm server mất resume state trong một môi trường thử nghiệm riêng. Không thực hiện việc này trên môi trường production.

### Bước 3: Gửi RESUME và quan sát từ chối

Khi client thử nối lại, server không tìm thấy phiên phù hợp hoặc không thể đáp ứng yêu cầu replay. Server có thể trả `ERROR[REJECTED_RESUME]` (mã `0x00000004`) và đóng connection.

Các implementation có thể biểu diễn lỗi chi tiết khác nhau trong log, nhưng kết quả protocol là phiên cũ không được tiếp tục.

### Bước 4: Tạo session mới bằng SETUP

Ứng dụng mở một transport connection mới và thực hiện `SETUP` như một phiên mới. Sau khi setup thành công, ứng dụng phải:

1. Đánh dấu các stream thuộc session cũ là đã mất hoặc đã kết thúc bất thường.
2. Đọc checkpoint nghiệp vụ cuối cùng đã xử lý chắc chắn.
3. Tạo request-stream hoặc request-channel mới.
4. Truyền offset, sequence hoặc cursor để server tiếp tục từ điểm phù hợp.
5. Dùng event ID và idempotency key để tránh side effect trùng lặp nếu cần gửi lại lệnh.
6. Ghi nhận session generation mới để phân biệt trace của phiên mới với phiên cũ.

Không thể tiếp tục tương tác cũ chỉ bằng cách giữ lại stream ID. Session mới có phạm vi stream ID riêng và phải mở các tương tác mới; một ID số như `1` có thể được dùng lại trong session mới mà không phải là stream cũ được resume.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Fault proxy
    participant S as Server
    C->>S: SETUP (resume enabled)
    C->>S: REQUEST_STREAM (stream ID 1)
    S-->>C: PAYLOAD đến sequence 20
    Note over P: Ngắt mạng quá thời hạn phiên
    C->>S: RESUME (token cũ)
    S-->>C: ERROR[REJECTED_RESUME]
    Note over C,S: Session cũ không thể khôi phục
    C->>S: Mở transport connection mới
    C->>S: SETUP (session mới)
    C->>S: REQUEST_STREAM mới (stream ID thuộc session mới)
    S-->>C: PAYLOAD từ checkpoint nghiệp vụ
~~~

## 8. Phân biệt replay của protocol với phát lại nghiệp vụ

Resume replay những frame còn thiếu dựa trên vị trí protocol mà hai peer đã trao đổi. Cơ chế này giúp tiếp tục các stream trong cùng phiên mà không yêu cầu ứng dụng tự tạo lại mọi request.

Tuy nhiên, resume không thay thế transaction hoặc cơ chế xác nhận nghiệp vụ. Vị trí frame phản ánh trạng thái nhận frame của protocol, không chứng minh một thao tác đã commit trong cơ sở dữ liệu hay side effect bên ngoài đã hoàn tất.

Khi resume thành công, implementation xử lý frame replay theo trạng thái phiên và tránh phát lại những frame đã được xác nhận ở tầng protocol. Nhưng nếu ứng dụng chuyển sang session mới, không còn resume state để đối chiếu. Khi đó, phát lại từ checkpoint có thể gửi lại thao tác đã được thực hiện trước lúc mất mạng.

Với nghiệp vụ có side effect, hãy áp dụng:

- Event ID duy nhất để nhận diện một thao tác.
- Idempotency key ở API hoặc consumer.
- Checkpoint được cập nhật sau khi xử lý nghiệp vụ thành công.
- Deduplication ở nơi thực hiện side effect.
- Quy tắc xác định điểm tiếp tục sau khi tạo session mới.

## 9. Resume buffer và thời gian gián đoạn

Resume cần giữ các frame chưa được peer xác nhận. Vì vậy, bộ nhớ cần thiết phụ thuộc vào thông lượng gửi, thời gian mất kết nối và kích thước frame.

Một ước lượng ban đầu cho mỗi hướng truyền:

~~~text
required buffer bytes
    >= peak outbound bytes per second
       * tolerated interruption seconds
       + burst margin
~~~

Ví dụ, một hướng có thể phát đỉnh 256 KB/giây và muốn chịu được gián đoạn 10 giây. Riêng phần dữ liệu trong thời gian gián đoạn đã cần khoảng 2,56 MB buffer, chưa tính burst và overhead. Cả client lẫn server đều cần được xem xét vì mỗi bên có thể phải giữ frame đã gửi nhưng chưa được xác nhận.

Nếu buffer bị tràn hoặc session hết hạn, resume có thể bị từ chối. Tăng buffer và session duration giúp chịu được gián đoạn dài hơn nhưng làm tăng bộ nhớ và số phiên phải giữ. Cần đặt giới hạn theo tải, số connection đồng thời và mức gián đoạn mục tiêu.

## 10. Những trường hợp resume thường thất bại

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Resume không được bật trong SETUP | Không có resume token/session state | Bật resume ở cả hai phía trước khi thiết lập phiên |
| Token không hợp lệ hoặc không tìm thấy | Server từ chối RESUME | Kiểm tra token mapping và vòng đời phiên |
| Session hết hạn | Resume bị rejected sau thời gian dài | Điều chỉnh session duration hoặc chuyển sang session mới |
| Resume buffer thiếu frame cần thiết | Không thể đồng bộ vị trí frame | Tăng buffer có giới hạn hoặc giảm thông lượng/burst |
| Server process khởi động lại | Resume state trong bộ nhớ bị mất | Dùng lưu trữ hỗ trợ nếu implementation có; nếu không, tạo session mới |
| Client reconnect tới node không có session state | Node đích không nhận diện token | Dùng sticky routing hoặc chia sẻ resume state theo khả năng triển khai |
| Một peer không hỗ trợ resume | SETUP hoặc RESUME bị từ chối | Đồng bộ implementation/cấu hình hai phía |
| Phiên bản protocol hoặc tham số setup không tương thích | Lỗi thiết lập connection | Kiểm tra version, MIME type và capability |

Resume state thường gắn với implementation và cách triển khai cụ thể. Không nên giả định rằng load balancer có thể gửi reconnect tới bất kỳ node nào mà node đó vẫn tìm được session. Nếu state chỉ ở bộ nhớ của một process, reconnect cần tới đúng node đó trong thời gian phiên còn hiệu lực.

## 11. Quan sát và log trong thí nghiệm

Để phân biệt hai nhánh thành công và thất bại, ghi log có cấu trúc với các trường sau:

| Trường log | Mục đích |
|---|---|
| `connection_id` | Nhận diện transport connection; giá trị mới sau reconnect |
| `session_id_hash` | Nhận diện phiên mà không tiết lộ resume token |
| `session_generation` | Phân biệt phiên cũ và session mới |
| `frame_type` | Quan sát SETUP, RESUME, RESUME_OK, ERROR và PAYLOAD |
| `stream_id` | Xác định stream được tiếp tục hay stream mới |
| `frame_position` | Theo dõi vị trí protocol nếu implementation cung cấp |
| `event_sequence` | Đối chiếu dữ liệu ở tầng ứng dụng |
| `disconnect_duration_ms` | So sánh với session duration |
| `resume_result` | success, rejected hoặc fallback-new-session |

Một lần resume thành công thường có chuỗi log tương tự:

~~~text
transport.disconnected session=abc
transport.connected connection=conn-2
rsocket.resume.sent session=abc
rsocket.resume.accepted session=abc
stream.resumed streamId=1
payload.received sequence=24
~~~

Một lần resume thất bại và fallback có thể có chuỗi:

~~~text
transport.disconnected session=abc
transport.connected connection=conn-3
rsocket.resume.rejected reason=session_expired
rsocket.setup.sent session=new
rsocket.setup.accepted session=new
stream.opened streamId=1 sessionGeneration=2
~~~

Đây là log minh họa, không phải chuỗi thông điệp bắt buộc của mọi implementation. Không ghi resume token nguyên bản, credential hay payload nhạy cảm.

## 12. Ma trận thử nghiệm nên chạy

| Ca thử | Cách tạo điều kiện | Kết quả mong đợi |
|---|---|---|
| Mất mạng ngắn | Cắt transport ngắn hơn session duration, buffer còn đủ | RESUME/RESUME_OK, stream cũ tiếp tục |
| Mất mạng sát giới hạn | Ngắt gần thời điểm session hết hạn | Xác định ranh giới timeout và tính ổn định |
| Mất mạng dài | Ngắt lâu hơn session duration | Resume bị từ chối; ứng dụng tạo session mới |
| Buffer thiếu | Tạo lưu lượng cao trong thời gian ngắt | Resume có thể bị từ chối vì không còn đủ frame |
| Server restart | Khởi động lại server khi client vẫn giữ token cũ | Kiểm tra resume state có bền vững hay không |
| Token sai | Dùng token không thuộc phiên thử nghiệm | Resume bị từ chối |
| Resume tắt | Thiết lập phiên không có cờ R | Không thể resume phiên đó |
| Session mới | Sau rejected resume, gửi SETUP mới và mở stream mới | Stream mới chạy từ checkpoint nghiệp vụ |

Với mỗi ca, lưu thời gian gián đoạn, số frame hoặc byte đã phát, số byte buffer, stream ID, event sequence và kết quả cuối. Không chỉ kiểm tra rằng socket đã mở lại; cần chứng minh đúng loại frame được trao đổi và đúng hành vi dữ liệu.

## 13. Quy trình quyết định sau khi mất kết nối

Có thể tổ chức logic phục hồi ở tầng ứng dụng theo trình tự:

1. Phát hiện transport mất kết nối và dừng việc gửi request mới trên transport cũ.
2. Kiểm tra session có bật resume và vẫn nằm trong thời hạn cấu hình.
3. Thử mở transport mới và gửi RESUME bằng token của phiên cũ.
4. Nếu nhận RESUME_OK, tiếp tục sử dụng các stream đã được khôi phục.
5. Nếu nhận REJECTED_RESUME hoặc không thể resume trong thời hạn, đánh dấu session cũ không còn dùng được.
6. Tạo transport/session mới bằng SETUP.
7. Khôi phục các subscription và command từ checkpoint nghiệp vụ, dùng idempotency/deduplication khi cần.
8. Ghi metric cho số lần resume thành công, resume bị từ chối và fallback.

Không nên lặp vô hạn việc gửi RESUME với cùng token khi server đã từ chối rõ ràng. Sau khi session cũ không còn khả năng khôi phục, cần chuyển sang quy trình session mới.

## Kết luận

Thí nghiệm resumption cần ngắt transport path trong khi giữ nguyên hai process và trạng thái phiên. Khi resume thành công, client gửi RESUME, server trả RESUME_OK, frame còn thiếu được phát lại và stream cũ tiếp tục mà không có SETUP mới. Khi session hết hạn, buffer không đủ, token sai hoặc server mất trạng thái, resume bị từ chối; ứng dụng phải mở session mới bằng SETUP và khôi phục tương tác từ checkpoint nghiệp vụ. Resume giúp phục hồi trạng thái protocol, còn tính đúng đắn của side effect vẫn cần event ID, idempotency và đối soát ở tầng ứng dụng.

## Tài liệu tham khảo

- [RSocket Protocol – Resumption](https://rsocket.io/about/protocol/)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
