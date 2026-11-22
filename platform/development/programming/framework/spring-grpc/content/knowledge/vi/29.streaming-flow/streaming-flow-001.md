# Flow control trong HTTP/2

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao HTTP/2 cần flow control khi nhiều luồng truyền dữ liệu đồng thời.
- Phân biệt **stream-level window** và **connection-level window**.
- Mô tả vai trò của **DATA**, **WINDOW_UPDATE** và **SETTINGS_INITIAL_WINDOW_SIZE**.
- Tính lượng dữ liệu có thể gửi dựa trên cửa sổ truyền và hiểu cách cửa sổ được bổ sung.
- Phân biệt flow control của HTTP/2 với congestion control của TCP và manual flow control ở API gRPC.
- Áp dụng backpressure để tránh làm đầy bộ nhớ khi xử lý streaming trong Spring gRPC.

## 1. Flow control giải quyết vấn đề gì?

Trong gRPC, dữ liệu RPC được truyền trên HTTP/2. Một kết nối HTTP/2 có thể mang nhiều stream đồng thời; mỗi stream có thể gửi nhiều frame dữ liệu. Nếu bên gửi liên tục truyền nhanh hơn khả năng đọc hoặc xử lý của bên nhận, dữ liệu chờ sẽ tích tụ trong bộ đệm, làm tăng bộ nhớ và độ trễ.

**Flow control** giới hạn lượng dữ liệu mà một bên có thể gửi trước khi bên nhận cho phép gửi tiếp. Bên nhận điều chỉnh giới hạn bằng cách cập nhật cửa sổ truyền. Cơ chế này giúp bảo vệ khả năng tiếp nhận dữ liệu của peer và cho phép nhiều stream chia sẻ một kết nối.

Trong **SPRING_GRPC**, điều này đặc biệt quan trọng với client-streaming, server-streaming và bidirectional streaming. Một producer nhanh có thể tạo dữ liệu nhanh hơn service hoặc client xử lý; flow control tạo backpressure ở tầng truyền tải, còn ứng dụng cần phối hợp để không tích lũy thêm hàng đợi vô hạn ở tầng của mình.

## 2. Hai cấp cửa sổ của HTTP/2

HTTP/2 dùng hai cửa sổ độc lập cho mỗi hướng truyền:

1. **Stream-level flow-control window**: giới hạn DATA được gửi trên một stream cụ thể.
2. **Connection-level flow-control window**: giới hạn tổng DATA được gửi trên toàn bộ kết nối.

Mỗi DATA frame tiêu thụ dung lượng của cả hai cửa sổ. Bên gửi chỉ có thể gửi thêm DATA khi cả cửa sổ của stream và cửa sổ của connection đều còn đủ dung lượng.

~~~mermaid
flowchart TD
  S["Sender"] --> D["DATA frame trên stream A"]
  D --> SW["Trừ stream window A"]
  D --> CW["Trừ connection window"]
  SW --> G{"Cả hai window còn đủ?"}
  CW --> G
  G -->|Có| R["Tiếp tục gửi DATA"]
  G -->|Không| W["Chờ WINDOW_UPDATE"]
  W --> U["Receiver tăng window"]
  U --> R
~~~

Ví dụ, connection window còn 20 KiB nhưng stream A chỉ còn 2 KiB. Stream A chỉ có thể gửi tối đa 2 KiB DATA trước khi cần window update cho stream A. Ngược lại, nếu stream A còn 20 KiB nhưng connection window chỉ còn 1 KiB, tổng dữ liệu gửi trên connection bị giới hạn còn 1 KiB.

Hai cửa sổ này ngăn hai tình huống khác nhau: một stream làm tràn bộ đệm dành cho chính nó, và nhiều stream cộng lại làm tràn khả năng tiếp nhận của toàn connection.

## 3. Window được tính bằng byte DATA

Flow control của HTTP/2 áp dụng cho **DATA frame**, không áp dụng cho mọi loại frame. Các frame như HEADERS, SETTINGS, PING và WINDOW_UPDATE không tiêu thụ flow-control window.

Đơn vị cửa sổ là octet (byte) của payload DATA được tính theo quy tắc HTTP/2:

- Payload dữ liệu của DATA frame bị trừ khỏi window.
- Nếu frame có padding, phần Pad Length và padding cũng thuộc độ dài bị tính flow control.
- 9 byte frame header không bị tính vào cửa sổ.

Vì vậy, flow control không đếm số frame, số RPC hay số message Protobuf. Nó giới hạn lượng byte DATA có thể đang được gửi mà chưa được bù lại bằng window update.

## 4. Kích thước cửa sổ mặc định

Theo HTTP/2, giá trị cửa sổ ban đầu mặc định là **65.535 octet** cho mỗi stream và cho connection. Cửa sổ không phải giới hạn tổng kích thước của một RPC hoặc tổng số byte stream được phép truyền trong suốt vòng đời; đó là lượng DATA có thể gửi trước khi cần cập nhật cửa sổ.

Một peer có thể điều chỉnh cửa sổ stream bằng setting **SETTINGS_INITIAL_WINDOW_SIZE**. Setting này áp dụng cho các stream và stream được tạo sau đó. Nó không thay đổi connection-level window. Connection window được điều chỉnh riêng bằng frame **WINDOW_UPDATE**.

Khi SETTINGS_INITIAL_WINDOW_SIZE giảm, giá trị cửa sổ stream hiện tại có thể trở thành âm. Khi đó sender phải dừng gửi DATA trên stream cho đến khi window trở lại dương đủ để gửi tiếp. Điều này không phải lỗi nếu kết quả nằm trong quy tắc HTTP/2.

Không nhầm:

- **SETTINGS_MAX_FRAME_SIZE** giới hạn kích thước frame DATA có thể gửi.
- **SETTINGS_INITIAL_WINDOW_SIZE** điều chỉnh cửa sổ flow control của stream.
- **WINDOW_UPDATE** bổ sung dung lượng flow control cho stream hoặc connection.

## 5. WINDOW_UPDATE bổ sung cửa sổ như thế nào?

Receiver gửi frame **WINDOW_UPDATE** để cho phép sender gửi thêm DATA. Frame mang một số nguyên dương 31-bit, gọi là window size increment.

- WINDOW_UPDATE có stream ID bằng 0: cập nhật **connection window**.
- WINDOW_UPDATE có stream ID khác 0: cập nhật cửa sổ của stream đó.
- Increment phải lớn hơn 0.
- Giá trị cửa sổ không được vượt quá \(2^{31}-1\); nếu vượt, kết nối hoặc stream gặp lỗi flow control theo quy tắc HTTP/2.

Ví dụ, nếu stream window còn 4.096 byte và receiver gửi WINDOW_UPDATE tăng 8.192 byte, sender có thêm 8.192 byte quyền gửi trên stream đó. Dung lượng connection window vẫn phải đủ riêng.

Receiver thường bổ sung cửa sổ khi dữ liệu đã được tiêu thụ đủ để có thể tiếp nhận thêm. Ứng dụng không nên giả định mỗi lần đọc một message gRPC sẽ tạo đúng một WINDOW_UPDATE; thời điểm và kích thước update do HTTP/2 implementation quản lý.

## 6. Flow control là độc lập theo từng hướng

Hai peer đều có thể gửi dữ liệu và điều khiển lượng dữ liệu mà mình sẵn sàng nhận. Cửa sổ cho hướng client → server và server → client là độc lập:

- Client quảng bá giới hạn nhận dữ liệu của client để server điều tiết DATA gửi xuống.
- Server quảng bá giới hạn nhận dữ liệu của server để client điều tiết DATA gửi lên.

Vì vậy, một server-streaming RPC có thể bị giới hạn bởi cửa sổ nhận ở client; một client-streaming RPC có thể bị giới hạn bởi cửa sổ nhận ở server. Trong bidirectional streaming, hai hướng có thể tiến triển với tốc độ khác nhau.

Flow control là **hop-by-hop** giữa hai endpoint HTTP/2 trực tiếp. Nếu có proxy hoặc gateway, mỗi chặng có cơ chế cửa sổ riêng; window update của một chặng không tự động là window update của chặng khác.

## 7. gRPC message không đồng nhất với HTTP/2 DATA frame

Một message gRPC có framing riêng gồm:

1. Một byte compression flag.
2. Bốn byte độ dài message theo big-endian.
3. Nội dung message Protobuf đã serialize.

HTTP/2 vận chuyển các byte framing và payload đó bên trong DATA frame. Một message gRPC có thể bị chia qua nhiều DATA frame; một DATA frame cũng có thể chứa phần cuối của message trước và phần đầu của message sau.

Do đó:

- Flow control HTTP/2 tính byte của DATA payload, gồm cả framing gRPC.
- Nó không cấp một cửa sổ riêng cho từng message Protobuf.
- Gọi **request(1)** ở API gRPC có nghĩa cho phép nhận thêm một message ở tầng gRPC; nó không có nghĩa tăng HTTP/2 window thêm một byte hoặc một frame.

Sự phân lớp này quan trọng khi chẩn đoán: một RPC có thể chưa nhận message tiếp theo vì ứng dụng chưa request thêm, hoặc vì transport chưa có đủ HTTP/2 window. Hai nguyên nhân nằm ở hai tầng khác nhau.

## 8. Flow control khác congestion control

**HTTP/2 flow control** và **TCP congestion control** cùng giới hạn truyền dữ liệu nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Bảo vệ điều gì? | Được điều khiển bởi |
| --- | --- | --- |
| HTTP/2 flow control | Khả năng tiếp nhận dữ liệu của peer và stream | Receiver qua window update/settings |
| TCP congestion control | Khả năng chịu tải của mạng trên đường truyền | TCP stack dựa trên tín hiệu mạng |
| Application backpressure | Khả năng xử lý, hàng đợi và tài nguyên nghiệp vụ | Logic ứng dụng và API gRPC |

Một HTTP/2 window lớn không có nghĩa mạng có thể truyền nhanh hơn mà không gây tắc nghẽn. Ngược lại, TCP congestion window lớn không có nghĩa receiver ứng dụng sẵn sàng nhận vô hạn dữ liệu.

Flow control cũng không thay thế giới hạn kích thước message, deadline, quota hoặc giới hạn bộ nhớ. Các cơ chế này cần được cấu hình và kiểm tra riêng.

## 9. Ảnh hưởng của một stream đến các stream khác

Các stream trên cùng một HTTP/2 connection chia sẻ connection-level window. Nếu một stream gửi lượng DATA lớn và nhanh, nó có thể tiêu thụ phần lớn connection window, làm các stream khác tạm thời không gửi được DATA dù stream window riêng của chúng còn dung lượng.

Đây là lý do cần xem xét:

- Kích thước message và tốc độ producer.
- Số lượng stream đồng thời trên một connection.
- Tốc độ đọc/tiêu thụ ở receiver.
- Cách HTTP/2 implementation phân bổ window update giữa stream và connection.
- Khả năng tách tải lớn sang connection hoặc RPC phù hợp khi có yêu cầu cô lập.

Không nên mặc định một stream chậm sẽ chỉ ảnh hưởng chính nó. Ở tầng connection, nhiều stream có chung ngân sách flow control.

## 10. Backpressure ở API gRPC Java

HTTP/2 flow control được quản lý ở tầng transport. Ứng dụng Spring gRPC thường tương tác với backpressure qua API gRPC Java:

- **Outbound readiness**: **isReady()** cho biết observer hiện có thể nhận thêm dữ liệu mà không tích lũy quá nhiều dữ liệu chờ trong lớp gửi.
- **On-ready callback**: **setOnReadyHandler(...)** thông báo khi khả năng gửi thay đổi để producer tiếp tục phát dữ liệu.
- **Inbound manual flow control**: ứng dụng có thể tắt auto request và gọi **request(n)** khi đã xử lý xong số message tương ứng.

Ví dụ server phát response theo readiness:

~~~java
ServerCallStreamObserver<Update> out =
    (ServerCallStreamObserver<Update>) responseObserver;

out.setOnReadyHandler(() -> {
    while (out.isReady() && hasNextUpdate()) {
        out.onNext(nextUpdate());
    }

    if (!hasNextUpdate() && !out.isCancelled()) {
        out.onCompleted();
    }
});
~~~

Đây là khung minh họa: producer thực tế cần quản lý trạng thái hoàn tất, hủy call và đồng bộ truy cập dữ liệu nếu callback có thể chạy trên executor khác. Không tạo vòng lặp bận để chờ isReady() trở thành true.

Với inbound manual flow control ở client, **ClientResponseObserver.beforeStart(...)** có thể gọi **disableAutoRequestWithInitial(1)**, rồi gọi **request(1)** sau khi xử lý xong mỗi response. Nhờ vậy ứng dụng chỉ yêu cầu thêm message khi sẵn sàng tiếp nhận.

**isReady()** và **request(n)** là API ở tầng gRPC, không phải API chỉnh trực tiếp HTTP/2 stream window. Transport vẫn quản lý DATA frame, connection window và WINDOW_UPDATE bên dưới.

## 11. Áp dụng cho các kiểu streaming RPC

| Kiểu RPC | Hướng dữ liệu chính | Nơi cần chú ý flow control |
| --- | --- | --- |
| Unary | Một request, một response | Message lớn vẫn tiêu thụ window; tránh giả định unary không cần backpressure. |
| Server streaming | Server gửi nhiều response | Server theo dõi outbound readiness; client điều tiết inbound message nếu cần. |
| Client streaming | Client gửi nhiều request | Client theo dõi outbound readiness; server xử lý inbound có giới hạn. |
| Bidirectional streaming | Hai hướng cùng gửi nhiều message | Quản lý backpressure độc lập cho inbound và outbound ở cả hai phía. |

Với bidirectional streaming, không nên để một callback xử lý message chặn việc đọc hoặc gửi ở hướng còn lại nếu hai hướng cần tiến triển độc lập. Dùng hàng đợi có giới hạn, xử lý bất đồng bộ có kiểm soát và phối hợp cancellation/deadline.

## 12. Cách chẩn đoán khi stream bị chậm

Khi thấy streaming RPC chậm hoặc ngừng phát message, kiểm tra theo từng tầng:

1. **Ứng dụng gửi**: producer có tạo dữ liệu liên tục, có bị chặn bởi isReady() hoặc hàng đợi nội bộ không?
2. **gRPC inbound demand**: ứng dụng nhận đã gọi request(n) đủ chưa, hay auto flow control đã bị tắt?
3. **HTTP/2 stream window**: stream cụ thể còn đủ window để gửi DATA không?
4. **HTTP/2 connection window**: stream khác có đang tiêu thụ phần lớn cửa sổ connection không?
5. **Receiver**: ứng dụng có đọc và xử lý message đủ nhanh để transport tiếp tục nhận không?
6. **TCP/network**: có retransmission, congestion hoặc giới hạn băng thông không?

Quan sát metric của ứng dụng cùng metric transport nếu thư viện cung cấp. Đừng kết luận “HTTP/2 window bằng 0” chỉ từ việc không thấy callback onNext; nguyên nhân có thể nằm ở demand của ứng dụng, producer hoặc network.

## 13. Thực hành thiết kế backpressure an toàn

Với một upload client-streaming, nên:

- Chia dữ liệu thành chunk có kích thước hợp lý, không gom toàn bộ tệp vào một message lớn.
- Chỉ phát chunk tiếp khi outbound observer sẵn sàng.
- Ở server, xử lý chunk theo thứ tự và giới hạn số chunk đang chờ.
- Nếu dùng manual inbound flow control, chỉ request thêm sau khi chunk hiện tại đã được xử lý hoặc đã có chỗ chứa an toàn.
- Dừng producer khi call bị cancel hoặc deadline hết hạn.
- Xác định cách xử lý chunk lặp, thiếu, sai offset và retry ở tầng nghiệp vụ.

~~~mermaid
sequenceDiagram
  participant C as Client producer
  participant T as HTTP/2 transport
  participant S as Server consumer
  C->>T: DATA chunk 1
  T->>S: Chuyển chunk 1
  S->>S: Validate và persist
  S-->>C: Demand / readiness cho chunk tiếp
  C->>T: DATA chunk 2
  T->>S: Chuyển chunk 2
  S->>S: Validate và persist
  S-->>C: Demand / readiness cho chunk tiếp
~~~

Flow control không thay thế xác thực dữ liệu, giới hạn tổng kích thước upload hoặc kiểm tra quyền. Một client vẫn có thể gửi một message đơn rất lớn nếu giới hạn message cho phép; cần giới hạn kích thước riêng.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ quan tâm stream window | Bỏ qua giới hạn connection window dùng chung | Theo dõi cả hai cấp cửa sổ. |
| Nghĩ WINDOW_UPDATE được gửi sau mỗi message | Giả định sai về thời điểm truyền tiếp | Xem đây là cơ chế byte-level do transport quản lý. |
| Nhầm request(1) với tăng HTTP/2 window | Chẩn đoán sai tầng gây nghẽn | Phân biệt gRPC message demand và HTTP/2 byte window. |
| Gửi liên tục dù isReady() là false | Làm tăng buffer, độ trễ và áp lực bộ nhớ | Dừng producer, tiếp tục qua on-ready callback. |
| Dùng hàng đợi vô hạn ở ứng dụng | Flow control transport không ngăn heap tăng vô hạn | Dùng bounded queue và backpressure. |
| Cho rằng flow control là congestion control | Bỏ qua tình trạng nghẽn mạng | Theo dõi cả HTTP/2 và TCP/network. |
| Coi flow control là giới hạn kích thước message | Một message lớn vẫn có thể gây áp lực bộ nhớ | Cấu hình message-size limit và streaming chunk. |
| Không dừng xử lý khi RPC bị cancel | Tiếp tục tiêu tốn tài nguyên sau khi client rời đi | Theo dõi cancellation và giải phóng tài nguyên. |

## 15. Bài tập thực hành

Một dịch vụ Spring gRPC nhận tệp qua client-streaming RPC và trả về tổng số byte đã lưu:

1. Giải thích vì sao HTTP/2 cần cả stream window và connection window khi nhiều upload cùng chạy trên một connection.
2. Với cửa sổ mặc định 65.535 byte, giải thích sender cần làm gì khi stream window cạn nhưng connection window vẫn còn.
3. Mô tả frame WINDOW_UPDATE với stream ID 0 khác gì frame có stream ID của upload.
4. Giải thích vì sao 5 byte gRPC message prefix cũng tiêu thụ HTTP/2 DATA window.
5. Thiết kế producer chỉ gửi chunk tiếp theo khi outbound observer sẵn sàng.
6. Đề xuất cách giới hạn số chunk đang chờ ở server khi dùng inbound manual flow control.
7. Phân biệt tình huống bị chặn bởi request(n), HTTP/2 window và TCP congestion.

**Tiêu chí hoàn thành:** mô tả đúng hai cấp cửa sổ, tính được lượng DATA được phép gửi, phân biệt flow control với các tầng backpressure khác và thiết kế streaming không tích lũy dữ liệu vô hạn.

## 16. Ghi nhớ

- HTTP/2 flow control áp dụng cho **DATA frame** và được tính bằng byte payload chịu flow control.
- Mỗi hướng truyền có **stream window** và **connection window**; gửi DATA phải có đủ dung lượng ở cả hai.
- **WINDOW_UPDATE** bổ sung cửa sổ; **SETTINGS_INITIAL_WINDOW_SIZE** điều chỉnh cửa sổ stream, không điều chỉnh connection window.
- gRPC message có framing riêng nhưng được vận chuyển trong DATA frame; flow control không đếm message.
- Flow control HTTP/2 khác TCP congestion control và khác application backpressure.
- Trong gRPC Java, phối hợp **isReady()**, on-ready callback và **request(n)** để điều tiết producer/consumer.
- Dùng hàng đợi có giới hạn, giới hạn message, cancellation và deadline để bảo vệ toàn bộ pipeline streaming.

Hiểu flow control trong HTTP/2 giúp dịch vụ Spring gRPC điều tiết luồng dữ liệu giữa nhiều stream, hạn chế bộ đệm tăng mất kiểm soát và duy trì độ ổn định khi client/server xử lý streaming với tốc độ khác nhau.
