# Độ trễ, mất gói và giới hạn độ tin cậy của mạng

## 1. Tại sao mạng làm thay đổi cách thiết kế microservices?

Trong ứng dụng đơn khối, nhiều thành phần trao đổi bằng lời gọi hàm trong cùng một tiến trình. Khi tách thành microservices, một lời gọi nghiệp vụ trở thành trao đổi qua mạng: tìm địa chỉ dịch vụ, thiết lập kết nối, xác thực, truyền dữ liệu, đợi phía nhận xử lý và nhận phản hồi. Mỗi bước có thể chậm, lỗi hoặc bị quá tải.

**Mạng có độ trễ, có thể mất gói, có thể đứt kết nối và không cho ứng dụng một bảo đảm tuyệt đối rằng yêu cầu đã được xử lý đúng một lần.** Đây là thuộc tính cần dự tính từ lúc thiết kế, không phải một ngoại lệ hiếm chỉ cần xử lý sau khi triển khai.

Ví dụ Order Service gọi Inventory Service để giữ hai sản phẩm cho đơn hàng. Inventory đã ghi nhận giữ hàng nhưng gói phản hồi bị thất lạc, khiến Order bị timeout. Nếu Order tự động gửi lại bằng một mã giữ hàng mới, Inventory có thể giữ hàng hai lần. Nếu Order đánh dấu đơn thất bại ngay, hai dịch vụ có thể không thống nhất trạng thái. Điều cần giải quyết bao gồm cả vấn đề mạng lẫn **tính đúng đắn của nghiệp vụ sau lỗi**.

Bài học này giải thích:

- **Latency (độ trễ)** hình thành và cộng dồn qua các dịch vụ như thế nào.
- **Packet loss (mất gói)** ảnh hưởng tới TCP, HTTP, gRPC và thời gian phản hồi ra sao.
- Vì sao **timeout không chứng minh server chưa xử lý** yêu cầu.
- Cách sử dụng **deadline, retry, backoff, idempotency, circuit breaker, bulkhead** và phương án khôi phục.
- Cách đo và kiểm chứng độ tin cậy bằng metrics, tracing, load test và fault injection.

## 2. Phân biệt độ trễ, băng thông và thông lượng

**Độ trễ (latency)** là thời gian cần để hoàn thành một hoạt động từ điểm đo bắt đầu đến điểm đo kết thúc. Ở API, thường là thời gian từ lúc client phát yêu cầu tới lúc nhận đủ phản hồi hoặc nhận kết quả theo quy ước đo.

**Băng thông (bandwidth)** là năng lực truyền dữ liệu của một liên kết trong một đơn vị thời gian, thường biểu diễn bằng bit/giây. **Thông lượng (throughput)** là lượng dữ liệu hoặc số thao tác hoàn thành thực tế trong thời gian đó. Băng thông lý thuyết cao không tự động tạo ra độ trễ thấp.

Ví dụ: gửi một request có payload nhỏ qua đường mạng liên vùng có thể tốn nhiều thời gian do khoảng cách và các lượt bắt tay dù băng thông dư thừa. Ngược lại, một endpoint nằm gần client vẫn chậm nếu thread pool hoặc connection pool bị bão hòa.

Ba thành phần độ trễ mạng thường được nhắc tới:

| Thành phần | Bản chất | Điều làm tăng |
| --- | --- | --- |
| Propagation delay | Thời gian tín hiệu di chuyển qua khoảng cách | Tuyến dài, khác vùng địa lý |
| Transmission delay | Thời gian đẩy các bit của một gói lên liên kết | Gói lớn, tốc độ liên kết thấp |
| Queueing delay | Thời gian gói/request chờ tài nguyên được phục vụ | Tắc nghẽn, burst, pool đầy |

Ngoài ra còn có xử lý tại thiết bị mạng, serialization/deserialization, encryption, database và logic nghiệp vụ. Để đánh giá một request đầu-cuối cần nhìn toàn bộ đường đi, không chỉ chỉ số ping.

### 2.1. Round-trip time (RTT)

**RTT** là thời gian đi và về của một lượt trao đổi giữa hai điểm, tùy cách đo và giao thức. Các giao thức cần xác nhận hoặc bắt tay có thể chịu thêm chi phí RTT. Khi hai dịch vụ ở xa nhau, một chuỗi nhiều lần gọi đồng bộ có thể có độ trễ đáng kể dù mỗi endpoint xử lý rất nhanh.

Không dùng một giá trị RTT cố định cho mọi cloud, mọi khu vực hoặc môi trường. Hãy đo từ **đúng nơi gọi**, qua **đúng tuyến kết nối**, trong các điều kiện tải có ý nghĩa.

### 2.2. Mô hình thời gian phản hồi của một API

Có thể hình dung:

~~~text
API end-to-end latency =
    queue/wait at client
  + DNS resolution (nếu cần)
  + connection/TLS setup (nếu không tái sử dụng)
  + request transfer
  + proxy/gateway waiting
  + server queueing and processing
  + downstream dependency latency
  + response transfer
  + client-side processing
~~~

Đây là sơ đồ khái niệm. Trên thực tế một số giai đoạn chạy song song, một số được cache, và mỗi công cụ đo có thể đặt ranh giới khác nhau. Không nên lấy số liệu từ nhiều công cụ rồi cộng cơ học khi chúng có phần chồng lấn.

## 3. Độ trễ trong chuỗi gọi microservices

Giả sử luồng đặt hàng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    C->>O: Tạo đơn
    O->>I: Giữ hàng
    I-->>O: Mã giữ hàng
    O->>P: Xử lý thanh toán
    P-->>O: Kết quả
    O-->>C: Trạng thái đơn
~~~

Nếu Order phải đợi Inventory rồi mới gọi Payment, thời gian chờ của hai dependency thường tham gia vào thời gian toàn request. Thêm lần gọi network có thể làm tăng latency và thêm điểm có thể hỏng. Nếu Payment sử dụng nhà cung cấp thanh toán ngoài, độ trễ bên ngoài cũng ảnh hưởng đến response của Order.

**Hai kiểu phụ thuộc:**

- **Sequential calls:** B phải hoàn tất trước C. Thời gian phản hồi chịu ảnh hưởng của cả chuỗi.
- **Parallel fan-out:** B và C có thể được gọi đồng thời. Thời gian chờ toàn bộ thường phụ thuộc nhánh chậm nhất; nếu phải đợi tất cả thành công, rủi ro cũng phụ thuộc tất cả các nhánh.

Một ví dụ xác suất minh họa: nếu mỗi lời gọi độc lập có 1% xác suất chậm hơn một ngưỡng và request phải đợi 20 lời gọi, xác suất có ít nhất một lời gọi chậm xấp xỉ 1 − 0,99^20 = 18,2%. Các lỗi thực tế có thể tương quan do chung database, proxy hoặc mạng; không được dùng phép tính giả định này thay cho đo đạc.

### 3.1. Tail latency

Độ trễ trung bình (average) có thể che khuất những request rất chậm. Hệ thống thường đo các percentile:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50 | 50% quan sát có độ trễ không vượt ngưỡng này |
| p95 | 95% quan sát không vượt ngưỡng này |
| p99 | 99% quan sát không vượt ngưỡng này |
| p99.9 | Dùng để theo dõi phần đuôi rất xa khi đủ mẫu đo |

Ví dụ một API có p50 là 40 ms nhưng p99 là 1.800 ms: phần lớn request có vẻ nhanh, một nhóm người dùng vẫn phải chờ lâu. Cần tìm nguyên nhân qua trace, pool wait, database lock, pause của runtime, tắc nghẽn hoặc dependency chậm.

**Không thể cộng p99 của từng service rồi coi đó là p99 của toàn bộ request.** Percentile của tổng phụ thuộc vào phân phối chung, tương quan giữa các bước và cách phối hợp. Hãy đo end-to-end latency song song với span của từng dependency.

### 3.2. Giảm số vòng qua mạng

Một số cách giảm latency phù hợp với nghiệp vụ:

1. Tránh chia dịch vụ quá nhỏ khiến một use case phải gọi nhiều service chỉ để đọc một aggregate.
2. Hạn chế các lời gọi đồng bộ nối tiếp không cần thiết; gọi song song các phụ thuộc thực sự độc lập.
3. Gộp các truy vấn thích hợp vào một API ở service sở hữu dữ liệu thay vì nhiều request nhỏ.
4. Dùng read model hoặc cache có giới hạn và chính sách làm mới khi phù hợp.
5. Tái sử dụng connection, tránh lặp DNS/handshake không cần thiết.
6. Dùng message/background processing khi công việc không cần hoàn tất trước lúc trả phản hồi.

Tuy nhiên, bất đồng bộ làm thay đổi semantics: phản hồi **“đã tiếp nhận xử lý”** khác với **“nghiệp vụ hoàn tất thành công”**. Không được cải thiện số đo latency bằng cách báo hoàn tất sớm khi hệ thống chưa thật sự hoàn tất.

## 4. Packet loss là gì?

**Packet loss** xảy ra khi một gói dữ liệu không đến được đích hoặc bị loại bỏ trên một liên kết hay tại thiết bị xử lý. Một số nguyên nhân:

- Router/switch hoặc kernel buffer bị đầy trong giai đoạn tắc nghẽn.
- Mạng không dây bị nhiễu, tín hiệu yếu, di chuyển giữa các điểm phát.
- Đường truyền vật lý có lỗi hoặc thiết bị mạng hoạt động không ổn định.
- Firewall, load balancer, NAT hoặc cấu hình đường đi tác động tới lưu lượng.
- MTU không phù hợp hoặc hành vi phân mảnh/đường đi phát sinh lỗi.
- Bên nhận hoặc thiết bị trung gian quá tải.
- Thay đổi tuyến mạng hoặc ngắt kết nối trong thời gian ngắn.

**Mất gói ở tầng mạng không đồng nghĩa với một HTTP request bị mất hoàn toàn.** Nhiều giao thức truyền tải có cơ chế truyền lại. Kết quả mà ứng dụng quan sát có thể là latency tăng, timeout, reset kết nối, stream bị gián đoạn hoặc response không đầy đủ.

Ngược lại, một HTTP 504 cũng không đủ để kết luận packet loss: server có thể đang chờ database, thread pool, queue hoặc API của bên thứ ba.

### 4.1. TCP xử lý mất gói ra sao?

TCP cung cấp luồng byte **có thứ tự** và sử dụng sequence number, acknowledgment, retransmission, flow/congestion control để phục hồi một số mất mát trong khi kết nối còn hoạt động. Khi một segment bị mất, bên gửi có thể truyền lại. Ứng dụng thường nhìn thấy **chậm** thay vì nhìn thấy từng gói bị mất.

TCP vẫn có giới hạn:

- Kết nối có thể bị reset, đóng hoặc bị gián đoạn vĩnh viễn.
- Truyền dữ liệu vào socket không chứng minh ứng dụng phía nhận đã xử lý hay commit.
- Một đoạn byte còn thiếu có thể khiến dữ liệu đến sau phải chờ để giữ thứ tự.
- Congestion control có thể giảm tốc độ gửi khi phát hiện nghẽn.

HTTP/2 multiplex nhiều stream trên một kết nối TCP, nhưng khi TCP còn thiếu dữ liệu, một mất mát ở tầng TCP có thể ảnh hưởng đồng thời đến các stream đang chia sẻ kết nối. HTTP/3 sử dụng QUIC trên UDP với cách multiplex stream khác để giảm một số dạng blocking giữa stream; điều này **không làm HTTP/3 miễn nhiễm mất gói hoặc lỗi mạng**.

### 4.2. UDP và QUIC

UDP là giao thức datagram, tự nó không cung cấp bảo đảm truyền lại và thứ tự như TCP. Ứng dụng có thể xây cơ chế khôi phục ở tầng cao hơn hoặc chấp nhận mất một số gói cho use case realtime.

QUIC chạy trên UDP nhưng tự cung cấp nhiều cơ chế về tin cậy, bảo mật, điều khiển luồng và congestion control. Vì vậy “dùng UDP” không tự cho biết đầy đủ mức độ tin cậy của một ứng dụng.

Với microservices, điều quan trọng là phân biệt **tin cậy của transport** với **tính đúng đắn của nghiệp vụ**: TCP/QUIC không thể thay cho cơ chế bảo đảm một lệnh tạo đơn, giữ hàng hoặc thanh toán không bị thực hiện trùng do retry.

## 5. Partial failure: lỗi chỉ xảy ra ở một phần hệ thống

Trong hệ thống phân tán, một service có thể vẫn khỏe trong khi service khác không truy cập được. Một số dạng lỗi:

| Tình huống | Điều client quan sát | Điều còn chưa biết |
| --- | --- | --- |
| DNS không trả kết quả | Không tìm được địa chỉ service | Service gốc có đang chạy không |
| Connect timeout | Không thiết lập kết nối đúng hạn | Đích chết, tuyến chặn hay quá tải |
| Connection refused | Kết nối bị từ chối | Nguyên nhân ở app, port, proxy hay policy |
| TLS handshake lỗi | Không thiết lập được phiên mã hóa | Chứng chỉ, identity hoặc giao thức có vấn đề gì |
| Read/request timeout | Chưa có kết quả trong thời hạn | Request có được server xử lý chưa |
| Connection reset | Một phần kết nối bị đóng bất thường | Server đã commit dữ liệu trước đó chưa |
| HTTP 503 | Endpoint tạm không phục vụ | Retry nào an toàn theo contract |
| HTTP 429 | Hết hạn mức hoặc đang throttle | Thời điểm và tốc độ gửi lại phù hợp |
| Message đến trễ/trùng | Consumer nhận event khác thời điểm dự kiến | Event đã tạo side effect chưa |

**Timeout là trạng thái người gọi chưa biết kết quả trong thời hạn, không phải bằng chứng phía nhận không thực hiện.** Đây là sự khác biệt đặc biệt quan trọng với thao tác có tác dụng phụ.

### 5.1. Ví dụ trạng thái chưa xác định

~~~text
T0: Order gửi POST /payments với paymentId=P-8421
T1: Payment nhận request và kiểm tra idempotency
T2: Payment ghi bền vững kết quả hoặc gọi nhà cung cấp
T3: Kết nối bị mất trước khi response về Order
T4: Order bị timeout
~~~

Lúc T4, Order không có cơ sở kết luận tiền chưa được xử lý. Nếu gửi một yêu cầu mới với paymentId khác, có nguy cơ tạo hai giao dịch. Nếu coi timeout là thất bại cuối, màn hình đơn hàng có thể không khớp với kết quả thanh toán.

Thiết kế tốt có **operationId/paymentId ổn định**, lưu trạng thái bền vững, xử lý yêu cầu lặp, cung cấp API tra cứu trạng thái, callback có xác thực hoặc cơ chế reconciliation để tìm kết quả cuối.

## 6. Timeout: đừng chờ vô hạn

**Timeout** đặt giới hạn chờ một thao tác hoặc một pha giao tiếp. Nó tránh để thread, socket, connection hoặc hàng đợi bị chiếm vô hạn khi dependency chậm.

Một số timeout phổ biến:

- **Connect timeout:** thời gian chờ thiết lập kết nối.
- **TLS handshake timeout:** thời gian chờ thỏa thuận phiên mã hóa.
- **Read/socket timeout:** thời gian chờ đọc dữ liệu, semantics phụ thuộc thư viện.
- **Request/response timeout:** thời gian chờ kết quả của request.
- **Connection pool acquisition timeout:** thời gian chờ lấy một kết nối có sẵn từ pool.
- **Overall deadline:** thời điểm cuối cho toàn bộ thao tác, kể cả các dependency và retry.

Tên cấu hình thay đổi tùy HTTP client, gRPC, reverse proxy và framework. Cần đọc contract thực tế: một số read timeout đếm thời gian giữa các lần đọc, không nhất thiết là tổng thời gian của request.

### 6.1. Timeout quá dài gây lỗi dây chuyền

Giả sử Order Service có 100 worker thread. Khi Payment chậm, toàn bộ thread có thể bị giữ trong 20 giây để chờ phản hồi. Request mới bắt đầu queue, connection pool cạn, các endpoint khác cũng chậm. Dù CPU chưa đầy, ứng dụng có thể gần như ngừng phục vụ.

Timeout giúp giải phóng tài nguyên hoặc trả trạng thái phù hợp. Tuy nhiên timeout quá ngắn lại từ chối cả request hợp lệ và có thể kích hoạt nhiều retry làm tình hình tệ hơn. Cần chọn bằng **số liệu độ trễ, deadline nghiệp vụ và rủi ro của thao tác**.

### 6.2. Đặt latency budget

Giả sử target response của một API tạo đơn là 1.100 ms trong điều kiện đã xác định. Ngân sách minh họa:

| Bước | Budget |
| --- | ---: |
| Gateway + xác thực | 80 ms |
| Logic và dữ liệu tại Order | 130 ms |
| Inventory | 250 ms |
| Payment | 450 ms |
| Biến động network/serialization và dự phòng | 190 ms |
| **Tổng** | **1.100 ms** |

Các con số chỉ minh họa; phải xác minh qua tải thực và SLO của sản phẩm. Nếu ba dependency nối tiếp và mỗi bên được đặt timeout 1.100 ms, tổng thời gian có thể vượt xa hạn của client. Nên dùng **deadline chung**, phân bổ budget hợp lý và truyền remaining deadline khi giao thức hỗ trợ.

### 6.3. Deadline và cancellation

Deadline là thời điểm cuối mà kết quả còn hữu ích. Một service gọi tiếp dependency nên tính thời gian **còn lại**, thay vì bắt đầu một timeout đầy đủ mới. Nếu thời hạn tổng sắp hết, có thể từ chối gửi một tác vụ không thể hoàn thành đúng hạn.

Cancellation có thể giúp giảm việc vô ích nhưng **không phải transaction rollback**. Server có thể đã commit trước khi biết client ngừng chờ, hoặc đã gọi hệ thống bên ngoài. Tính đúng đắn sau cancellation vẫn cần trạng thái nghiệp vụ, idempotency và reconciliation.

## 7. Retry: dùng có điều kiện, không gửi lại vô hạn

**Retry** có thể vượt qua lỗi tạm thời như mất kết nối ngắn, 503 hoặc một số lỗi đọc. Nhưng retry cũng làm tăng tải, tạo request trùng và kéo dài outage.

Một chính sách retry cần trả lời:

1. Lỗi nào được coi là tạm thời và **được phép thử lại**?
2. Thao tác có tác dụng phụ hay không? Có **idempotency** thật sự?
3. Số attempt tối đa là bao nhiêu?
4. Chờ giữa các attempt bao lâu, có backoff và jitter không?
5. Tổng thời gian thử lại có vượt overall deadline không?
6. Proxy/SDK/gateway đã retry chưa, tránh nhiều tầng cùng retry?
7. Khi bị 429 hoặc nhận Retry-After thì giới hạn tốc độ thế nào?
8. Khi kết quả vẫn mơ hồ, truy vấn trạng thái hay báo pending ra sao?

### 7.1. Retry storm và retry amplification

Nếu một upstream gọi downstream thất bại rồi 1.000 client cùng retry ngay, downstream vừa phục hồi sẽ nhận một đợt truy cập dồn dập, dễ tiếp tục quá tải.

Nếu Gateway có tối đa 3 attempt và Order Service cũng cho tối đa 3 attempt tới Inventory, một yêu cầu có thể dẫn tới **9 lần gọi Inventory** trong tình huống xấu, chưa tính SDK. Một thành phần hỏng có thể khiến tổng traffic tăng nhiều lần. Cần phân công retry ở tầng phù hợp và áp dụng retry budget chung.

### 7.2. Exponential backoff và jitter

~~~text
delay(attempt) = min(maxDelay, baseDelay × 2^(attempt - 1))
wait = random(0, delay(attempt))   // ví dụ full jitter
~~~

Backoff tăng thời gian giữa những lần thử; jitter tránh nhiều client chạy đồng nhịp. Công thức là minh họa nguyên lý, không có nghĩa luôn retry sau mọi loại lỗi. Giới hạn tổng attempt, deadline và chi phí là bắt buộc khi triển khai thực tế.

### 7.3. Bảng xử lý lỗi theo ý nghĩa

| Kết quả | Hướng xử lý |
| --- | --- |
| Lỗi kết nối ngắn trước khi request được gửi | Có thể thử lại theo policy và budget |
| Timeout sau khi gửi POST thanh toán | Trạng thái mơ hồ: tra cứu operation; chỉ replay an toàn theo idempotency contract |
| HTTP 503 | Có thể retry có giới hạn nếu dependency cho phép |
| HTTP 429 | Giảm tải, xét Retry-After, không tăng retry đồng loạt |
| HTTP 400 do request không hợp lệ | Sửa dữ liệu, không retry cùng payload |
| HTTP 401/403 | Xử lý xác thực/phân quyền, tránh vòng lặp retry |
| HTTP 409 do xung đột nghiệp vụ | Xử lý conflict theo contract |
| DNS cấu hình sai | Sửa cấu hình, retry dồn dập không giải quyết |
| Broker gửi lại cùng event | Consumer cần deduplication/idempotency |

Không suy ra chính sách retry chỉ từ HTTP status; cần biết server đã xử lý side effect hay chưa và ngữ nghĩa của endpoint.

## 8. Idempotency: giải quyết tác dụng trùng do mạng không chắc chắn

**Idempotency** ở tầng nghiệp vụ nghĩa là nhiều lần xử lý cùng một yêu cầu được định danh không nhân đôi tác dụng không mong muốn. Một lệnh thanh toán được retry không được tạo thêm lần thu tiền.

Ví dụ API:

~~~http
POST /v1/payments
Content-Type: application/json
Idempotency-Key: order-8421-payment-1

{
  "paymentId": "P-8421",
  "orderId": "8421",
  "amount": 250000,
  "currency": "VND"
}
~~~

Idempotency key không tự phát huy tác dụng nếu server chỉ nhận header rồi bỏ qua. Phía Payment cần có cơ chế:

- Định danh operation bền vững, phạm vi khóa rõ ràng.
- Kiểm tra và khóa tránh hai request trùng chạy đồng thời thành hai transaction.
- Lưu status và kết quả có thể trả lại cho request lặp.
- Phát hiện cùng khóa nhưng payload khác; trả conflict theo contract.
- Quy định thời hạn giữ key, hành vi khi operation vẫn đang xử lý.
- Bảo vệ transaction nội bộ, cập nhật với bên thứ ba và đối soát khi lỗi.

Một trạng thái phù hợp sau network timeout có thể là **PENDING_CONFIRMATION**. Hệ thống tiếp tục tra cứu, xử lý callback đã xác thực hoặc chạy reconciliation, không đoán request đã thất bại.

### 8.1. Khác biệt giữa transport guarantee và business guarantee

TCP truyền byte tin cậy trong giới hạn kết nối, nhưng không chứng minh server đã commit đơn hàng. HTTP trả 200 có thể xác nhận theo contract, nhưng chưa chắc công việc nền đã hoàn tất. Broker có cơ chế delivery riêng nhưng side effect ở database hoặc API ngoài có thể bị lặp khi consumer retry.

Cụm “exactly once” phải nói rõ **phạm vi bảo đảm**. Để đạt một tác dụng nghiệp vụ không trùng, thường cần operation ID, transaction/ràng buộc dữ liệu, deduplication và cơ chế khôi phục trạng thái; không thể chỉ chọn một giao thức truyền tải.

## 9. Reliability patterns: hạn chế lỗi lan truyền

Các cơ chế dưới đây giải quyết những vấn đề khác nhau:

| Cơ chế | Vai trò | Giới hạn |
| --- | --- | --- |
| Timeout | Chặn chờ vô hạn | Không xác định tác dụng nghiệp vụ sau lỗi |
| Deadline propagation | Không cấp lại thời gian khi gọi qua nhiều tầng | Không tự rollback việc đã commit |
| Retry budget | Giới hạn số lần và chi phí thử lại | Không sửa lỗi cấu hình vĩnh viễn |
| Circuit breaker | Tạm ngừng gọi dependency đang thất bại nhiều | Không thay thế timeout hoặc idempotency |
| Bulkhead | Cô lập thread/connection/concurrency cho các nhóm | Cần sizing phù hợp |
| Bounded queue | Không cho lượng việc chờ tăng vô hạn | Phải có cách reject/backpressure |
| Rate limiting | Giới hạn số request theo capacity/quota | Cần quy tắc ưu tiên, công bằng |
| Load shedding | Bỏ việc ít ưu tiên khi quá tải | Không được loại bỏ tác vụ quan trọng thiếu kiểm soát |
| Graceful degradation | Tiếp tục chức năng quan trọng khi phần phụ lỗi | Không được làm sai tính nhất quán nghiệp vụ |
| Cache/read model | Giảm một số lời gọi đồng bộ | Phải quản lý stale data và invalidation |

### 9.1. Circuit breaker

Một circuit breaker thường quan sát lỗi/latency trong một khoảng, tạm ngưng gửi request khi dependency liên tục thất bại và sau đó cho một lượng nhỏ request kiểm tra phục hồi. Điều này giúp upstream không phí tài nguyên và giảm tải cho downstream đang lỗi.

Circuit breaker không quyết định được đơn hàng đã tạo hay thanh toán đã thành công chưa. Với thao tác có side effect, sau lỗi vẫn cần trạng thái trung gian và đối soát.

### 9.2. Bulkhead và giới hạn concurrency

Nếu Order dùng chung một pool cho Catalog, Inventory và Payment, khi Payment chậm nó có thể chiếm hết connection khiến các thao tác khác bị ảnh hưởng. Pool/limiter tách biệt theo dependency có thể cô lập sự cố.

Số giới hạn phải đo theo capacity, thời gian chờ và burst. Theo Little's law, trong hệ thống ổn định, số yêu cầu đồng thời trung bình xấp xỉ **tốc độ xử lý mỗi giây nhân thời gian lưu trong hệ thống**. Ví dụ 100 request/giây và 0,2 giây tương ứng khoảng 20 request đang xử lý trung bình, nhưng không đủ để chọn pool dưới tải đỉnh hoặc tail latency cao.

### 9.3. Graceful degradation

Recommendation Service chậm không nhất thiết phải làm checkout thất bại; giao diện có thể ẩn gợi ý sản phẩm hoặc dùng danh sách thay thế đã được chấp thuận. Nhưng một lời gọi xác nhận thanh toán không thể được thay bằng kết quả “thành công giả” chỉ để giữ UI mượt.

**Phân loại chức năng bắt buộc và chức năng có thể suy giảm** theo nghiệp vụ trước khi chọn fallback.

## 10. Giao tiếp đồng bộ và bất đồng bộ dưới điều kiện mạng lỗi

Giao tiếp đồng bộ (REST/gRPC request-response) phù hợp khi cần kết quả trực tiếp, thao tác ngắn và có thể xử lý failure trong deadline. Giao tiếp bất đồng bộ (message/event) phù hợp khi công việc có thể kéo dài, cần tách thời điểm, hấp thụ burst hoặc phục vụ nhiều consumer độc lập.

Ví dụ gửi email xác nhận không cần nằm trong critical path của request thanh toán. Khi đơn đã được xác nhận, hệ thống có thể ghi event và để Notification xử lý sau. Tuy nhiên message có thể chậm, thất lạc trong một số kiểu cấu hình, redeliver hoặc bị kẹt; bất đồng bộ không xóa bỏ nhu cầu vận hành và khôi phục.

### 10.1. Transactional Outbox

Nếu database đã commit đơn hàng nhưng tiến trình chết trước khi phát event, hệ thống có thể không gửi thông báo hoặc không cập nhật downstream. **Transactional Outbox** ghi dữ liệu nghiệp vụ và bản ghi chờ phát event **trong cùng transaction nội bộ**, sau đó publisher xử lý gửi lại theo cơ chế bền vững.

~~~text
Transaction của Order:
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO outbox(event_id, event_type, payload)
  COMMIT

Publisher:
  đọc outbox -> gửi broker -> ghi trạng thái publish

Consumer:
  nhận event -> deduplicate event_id -> xử lý idempotent
~~~

Publisher có thể phát lại khi mất acknowledgment, nên consumer vẫn cần tránh xử lý trùng. Outbox xử lý một phần bài toán **dual write**, không tạo bảo đảm toàn bộ nghiệp vụ xuyên nhiều dịch vụ là một transaction nguyên tử.

### 10.2. Saga cho quy trình nhiều dịch vụ

Nếu Order giữ hàng thành công nhưng Payment thất bại, cần action bù trừ như giải phóng giữ hàng. **Saga** tổ chức nhiều giao dịch cục bộ với logic tiếp tục/bù trừ. Có thể dùng coordinator (orchestration) hoặc sự kiện giữa các thành phần (choreography).

Mỗi bước cần operation ID, timeout, retry an toàn, idempotency và theo dõi trạng thái. Bù trừ không đồng nghĩa rollback vật lý được mọi tác dụng bên ngoài, ví dụ hoàn tiền hoặc email đã gửi.

## 11. Quan sát độ trễ, loss và lỗi trong production

Cần đo **từ phía người gọi và phía nhận**, trên đúng đường đi và môi trường. Một vài chỉ số tối thiểu:

| Nhóm | Ví dụ metrics | Ý nghĩa |
| --- | --- | --- |
| Request | RPS, p50/p95/p99, error rate, status | Mức tải và trải nghiệm API |
| Client dependency | Connect timeout, read timeout, pool wait, retry attempt | Service đang chờ ở đâu |
| Network | RTT, retransmission, packet drop, connection reset | Dấu hiệu đường truyền hoặc tắc nghẽn |
| Gateway/proxy | Upstream latency, queue time, 502/503/504 | Vấn đề tại ranh giới điều hướng |
| Runtime | CPU, memory, GC pause, thread/connection pool | Nghẽn bên trong ứng dụng |
| Database | Slow queries, lock wait, connection saturation | Nút thắt dữ liệu |
| Broker | Queue lag, consumer backlog, redelivery | Công việc bất đồng bộ có bị tồn đọng |
| Business | Payment pending quá hạn, đơn chưa đối soát, giữ kho hết hạn | Lỗi có ảnh hưởng nghiệp vụ không |

**TCP retransmission không tự chứng minh nguyên nhân duy nhất là packet loss trên một đường cụ thể.** Cần kết hợp thông tin từ NIC, kernel, mạng, proxy và trace. Ping/ICMP cũng không đủ để kết luận một HTTP API khỏe vì ICMP và TCP/TLS có thể đi qua chính sách hoặc đường xử lý khác.

### 11.1. Distributed tracing

Một trace giúp nối request qua service và các dependency:

~~~text
traceId=abc123
POST /orders                  845 ms
  Order validation             20 ms
  Inventory reserve           120 ms
    Inventory DB               38 ms
  Payment authorize           650 ms
    External payment provider 610 ms
  Order persist                30 ms
~~~

Ví dụ này cho thấy Payment provider chiếm phần lớn thời gian. Tăng số instance của Order chưa chắc cải thiện latency. Nếu client-side span lớn hơn server-side span nhiều, cần kiểm tra proxy, network, queue hoặc phần chưa được instrument; không kết luận chỉ từ một trace.

Trace nên đi cùng **correlation ID**, logs có cấu trúc và metrics. Không ghi thẻ thanh toán, token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào spans/logs.

### 11.2. Phân tách dữ liệu đo

Độ trễ trung bình toàn bộ có thể che khuất lỗi chỉ xuất hiện ở một vùng hoặc endpoint. Nên phân tích theo đường API, phiên bản release, region, tải cao điểm, loại request, kích thước payload, retry attempts và dependency.

Đồng thời đo trải nghiệm đầu-cuối của người dùng, vì metrics trong data center không phản ánh đầy đủ mạng di động, DNS, CDN hoặc thiết bị của client.

## 12. Phân biệt network bottleneck và ứng dụng bottleneck

| Hiện tượng | Giả thuyết cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| p99 cao, CPU thấp | Pool wait, database lock, API bên ngoài | Tracing, query logs, pool metrics |
| Request mới chậm, request trên connection cũ nhanh | DNS, TCP/TLS handshake | Timing từng pha, connection reuse |
| Chỉ một khu vực bị chậm | Vị trí, routing hoặc dịch vụ vùng đó | So kết quả từ nhiều region |
| Timeout tăng khi burst | Queue, saturation, retry storm | RPS, pool wait, queue depth |
| Nhiều reset kết nối | Proxy idle timeout, network, process restart | Log load balancer, TCP metrics |
| Lỗi sau deploy | Cấu hình, DNS, TLS, thay đổi retry/pool | So version, timeline thay đổi |
| Client timeout nhưng server ghi success | Response bị mất/chậm hoặc deadline không đồng bộ | TraceId + operationId + commit status |
| Broker lag tăng | Consumer chậm, poison message, throughput không đủ | Consumer lag, processing time |

Một HTTP 504 có thể bắt nguồn từ backend bị chậm khi chờ DB chứ không phải packet loss. Ngược lại, một service “healthy” ở endpoint health check chưa chắc trả được request nghiệp vụ đúng hạn. Phải kết hợp nhiều nguồn dữ liệu.

### 12.1. Liveness, readiness và business health

- **Liveness:** tiến trình còn hoạt động theo tiêu chí kiểm tra.
- **Readiness:** instance có thể nhận loại traffic mà hệ thống sẽ điều hướng tới không.
- **Dependency health:** các hệ thống phụ thuộc có sẵn từ góc nhìn service không.
- **Business health:** các workflow quan trọng có hoàn tất và đối soát không.

Không nên làm readiness phụ thuộc cứng vào mọi dependency ngoài, vì một dịch vụ phụ lỗi có thể khiến tất cả instance bị loại khỏi routing, làm sự cố lan rộng. Phải xác định các dependency nào thật sự bắt buộc với loại traffic đang phục vụ.

## 13. Lập SLI, SLO và error budget

**SLI** là chỉ số đo chất lượng, ví dụ tỷ lệ request thành công hoặc p95 latency. **SLO** là mục tiêu cho chỉ số đó trong một khoảng thời gian và theo cách tính đã định. **SLA** là cam kết ở cấp thỏa thuận, có thể kèm điều khoản riêng.

Một mục tiêu minh họa:

~~~text
Trong cửa sổ 30 ngày:
- 99,9% request GET /products hợp lệ được phục vụ thành công.
- 95% request hợp lệ hoàn tất trong 300 ms,
  đo tại điểm ingress được thống nhất.
~~~

Đây là **số giả định để học**, không phải chỉ tiêu áp dụng mặc định. Dự án phải xác định rõ request nào tính vào mẫu, lỗi client có loại trừ không, nơi đo, mức tải, nhóm khách hàng, cách xử lý maintenance và cửa sổ thống kê.

**Error budget** là khoảng sai lệch SLO cho phép trong kỳ; khi ngân sách gần cạn, nhóm có thể ưu tiên giảm rủi ro vận hành. Một SLO tốt giúp các quyết định về kiến trúc, timeout, cache và redundancy dựa trên yêu cầu đo được.

Đối với thanh toán, cần thêm chỉ số nghiệp vụ: số giao dịch pending quá hạn, tỷ lệ phải đối soát, tỷ lệ xử lý trùng ngăn được. Chỉ HTTP status hoặc CPU không thể đại diện cho tính đúng đắn nghiệp vụ.

## 14. Ví dụ timeout trong Java

Ví dụ sử dụng HTTP client của JDK trong một ứng dụng Java. Mục đích là minh họa connection timeout và request timeout; đây không phải toàn bộ production client.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class InventoryClient {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .build();

    public String getAvailability(URI endpoint)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofMillis(800))
            .GET()
            .build();

        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString()
            );
            if (response.statusCode() == 200) {
                return response.body();
            }
            throw new IOException(
                "Inventory status: " + response.statusCode()
            );
        } catch (HttpTimeoutException ex) {
            // Client chưa nhận kết quả trong thời hạn.
            // Không khẳng định service chưa xử lý.
            throw new IOException("Inventory timed out", ex);
        }
    }
}
~~~

**Lưu ý sử dụng:**

- URI phải được lấy từ cấu hình tin cậy; không cho untrusted input điều khiển endpoint gọi ra.
- Chương trình thực cần authentication, tracing, retry policy rõ ràng và quản lý response schema.
- Với POST có side effect cần thêm định danh idempotency do service nhận thực hiện.
- Không retry mọi lỗi HTTP tự động.
- Connection client nên được reuse với lifecycle rõ ràng thay vì tạo mới cho từng request.
- Phía gọi phải xử lý InterruptedException đúng hợp đồng, không nuốt interrupt.
- Timeout của API gọi ngoài phải phù hợp với deadline tổng, và cancellation không bảo đảm rollback.

### 14.1. Mô hình pseudocode cho retry có deadline

~~~text
function callWithPolicy(operationId, overallDeadline):
    for attempt in 1..MAX_ATTEMPTS:
        remaining = overallDeadline - now()
        if remaining <= 0:
            return UNKNOWN_OR_TIMED_OUT

        result = send(
            operationId = operationId,
            timeout = min(PER_ATTEMPT_TIMEOUT, remaining)
        )

        if result is SUCCESS:
            return SUCCESS

        if result is FINAL_BUSINESS_ERROR:
            return result

        if result is AMBIGUOUS_SIDE_EFFECT:
            return QUERY_STATUS_OR_MARK_PENDING

        if result is NOT_RETRYABLE:
            return result

        if attempt == MAX_ATTEMPTS:
            return RETRY_EXHAUSTED

        wait = backoffWithJitter(attempt)
        if wait >= overallDeadline - now():
            return RETRY_EXHAUSTED
        sleep(wait)

    return RETRY_EXHAUSTED
~~~

Pseudocode chỉ mô tả nguyên tắc. Tùy thư viện và hợp đồng, cần quản lý retry budget toàn hệ thống, connection pool, cancellation, logging, bảo mật và các trạng thái nghiệp vụ cụ thể.

## 15. Thử nghiệm hệ thống khi mạng không hoàn hảo

Một hệ thống chỉ chạy đúng khi mọi dependency phản hồi ngay chưa đủ tin cậy. Cần thử nghiệm có kiểm soát trong môi trường cho phép.

### 15.1. Load test về latency

1. Xác định SLO và workload đại diện: tỷ lệ đọc/ghi, kích thước payload, trạng thái cache, lượng dữ liệu.
2. Tăng tải theo các mức, không chỉ kiểm tra một request đơn lẻ.
3. Thu p50, p95, p99, throughput, error rate, concurrency, queue time.
4. Gắn metrics thread pool, connection pool, database, broker và downstream.
5. Tìm bottleneck cụ thể rồi thử tối ưu, sau đó đo lại cùng điều kiện.
6. Thử burst và giai đoạn hồi phục, không chỉ trạng thái ổn định.

Một p95 không đạt không tự chứng minh cần microservices. Vấn đề có thể là truy vấn database, khóa giao dịch, cache, network round trips hoặc cấu hình pool.

### 15.2. Fault injection có mục tiêu

Các tình huống nên kiểm tra:

- Thêm độ trễ và jitter vào Inventory Service.
- Giả lập packet loss và kết nối bị cắt trong một giai đoạn.
- Làm Payment xử lý xong nhưng response không về client.
- Cho một dependency trả 429/503 trong thời gian ngắn.
- Tạo DNS/connect/TLS failure ở đúng tuyến thử nghiệm.
- Làm message đến trễ, lặp hoặc sai thứ tự.
- Giới hạn băng thông hoặc tăng queueing ở một liên kết.
- Khởi động lại consumer khi đang xử lý event và đo khả năng phục hồi.

Mỗi phép thử cần phạm vi môi trường, dữ liệu thử, điều kiện dừng và người chịu trách nhiệm rõ. Không gây gián đoạn production hoặc luồng tiền thật ngoài quy trình được phê duyệt.

### 15.3. Điều kiện thành công

Ngoài việc API trả kết quả, cần kiểm tra:

- Không có request chiếm tài nguyên vượt giới hạn cho phép.
- Lỗi Inventory không kéo sập chức năng không phụ thuộc Inventory.
- Không giữ kho hoặc trừ tiền trùng vì retry.
- Workflow pending cuối cùng được xử lý hoặc đưa vào đối soát.
- Hàng đợi hồi phục mà không tạo retry storm.
- Metrics và trace đủ để truy tìm nguyên nhân.
- Client nhận trạng thái nghiệp vụ trung thực, không bị báo thành công giả.

## 16. Ví dụ thực tế: Order gọi Inventory khi mạng không ổn định

Giả định Order Service cần giữ một SKU cho đơn hàng 8421. Chọn một contract có định danh operation:

~~~http
POST /v1/reservations
Content-Type: application/json
Idempotency-Key: reserve-order-8421

{
  "orderId": "8421",
  "items": [{"sku": "BK-01", "quantity": 2}]
}
~~~

Inventory Service xử lý một lần trên cùng operation ID, lưu trạng thái và mã reservation. Nó trả thành công, hết hàng, conflict hoặc trạng thái đang xử lý theo API contract.

Nếu Order nhận response thành công, tiếp tục workflow. Nếu Inventory báo hết hàng, xử lý lỗi nghiệp vụ. Nếu connection timeout sau khi gửi request, Order **không tạo reservation mới ngay**. Nó có thể truy vấn theo orderId hoặc retry cùng key khi hợp đồng idempotency cho phép, trong deadline và retry budget. Nếu vẫn chưa biết, giữ trạng thái **RESERVATION_PENDING_CONFIRMATION**, để worker đối soát.

Nếu Payment sau đó thất bại, hệ thống gửi thao tác giải phóng giữ hàng theo cùng nguyên tắc: định danh ổn định, idempotency, retry có giới hạn và cơ chế khôi phục. Một network failure không được làm mất bất biến về số lượng đã giữ.

## 17. Khi nào xử lý bất đồng bộ để tránh chặn người dùng?

Nếu việc xác nhận đơn yêu cầu kết quả thanh toán thật, không thể chỉ nhận request rồi nói thanh toán thành công. Nhưng các công việc như gửi email, tạo hóa đơn PDF, đồng bộ analytics hoặc cập nhật search index có thể được tách khỏi critical path nếu nghiệp vụ cho phép.

Ví dụ:

~~~mermaid
flowchart LR
    U["Người dùng"] --> O["Order API"]
    O --> DB[("Order DB")]
    O --> OB[("Outbox")]
    OB --> B[("Broker")]
    B --> N["Notification"]
    B --> A["Analytics"]
~~~

Order trả phản hồi đúng semantics theo trạng thái đã commit. Notification và Analytics xử lý sau. Cần theo dõi message lag, dead-letter, redelivery và xử lý trùng. Việc có broker không thay thế giám sát tình trạng nghiệp vụ.

## 18. Quy trình điều tra khi microservices đột nhiên chậm

**Bước 1 — Xác nhận triệu chứng:** Đường API nào chậm, p95 hay p99 tăng, ảnh hưởng region nào, bắt đầu khi nào?

**Bước 2 — Xác định phạm vi:** Các endpoint độc lập có lỗi theo không? Có thay đổi release, traffic hoặc hạ tầng gần thời điểm đó không?

**Bước 3 — Đọc trace:** Thời gian nằm ở client connect, gateway, queue, service processing, database hay external API?

**Bước 4 — Đối chiếu mạng:** RTT, reset, retransmission, packet drop, lỗi DNS/TLS có tương quan không? Không kết luận từ một chỉ số.

**Bước 5 — Kiểm tra tài nguyên:** Thread pool, connection pool, CPU, memory, DB locks, queue lag và retry rate có bão hòa không?

**Bước 6 — Bảo vệ hệ thống:** Giới hạn concurrent calls, giữ timeout phù hợp, tắt retry quá mức, shed traffic ít ưu tiên và giữ đúng trạng thái nghiệp vụ.

**Bước 7 — Khôi phục nghiệp vụ:** Đối soát các đơn/payment đang pending, giải phóng reservation hợp lệ, xử lý event trễ hoặc trùng.

**Bước 8 — Ghi bài học:** Cập nhật runbook, dashboard, fault test và hợp đồng API nếu cần.

Không nên giải quyết mọi latency spike bằng cách tăng timeout hoặc tăng số container. Hai thay đổi đó có thể giúp hoặc có thể làm vấn đề nặng hơn, tùy bottleneck thực tế.

## 19. Các sai lầm phổ biến

1. **Cho rằng mạng nội bộ luôn nhanh và không bao giờ lỗi.** Mọi đường giao tiếp vẫn có queue, thay đổi tuyến, restart và cạn tài nguyên.
2. **Đặt timeout rất lớn để che giấu request chậm.** Điều này giữ tài nguyên lâu và có thể gây cascading failure.
3. **Chỉ đo average latency.** Tail latency thường tác động đáng kể đến một nhóm người dùng.
4. **Retry không giới hạn hoặc ở nhiều tầng.** Traffic nhân lên đúng lúc dependency đang yếu.
5. **Retry POST có side effect nhưng không có idempotency.** Timeout có thể xảy ra sau khi server đã commit.
6. **Tin rằng TCP loại bỏ mọi duplicate operation.** TCP bảo vệ một luồng byte trong giới hạn kết nối, không quyết định semantics của API.
7. **Xem timeout là thất bại nghiệp vụ cuối.** Timeout đôi khi là trạng thái chưa biết, cần tra cứu và đối soát.
8. **Dùng circuit breaker như giải pháp cho mọi lỗi.** Nó không sửa dữ liệu hoặc rollback việc đã commit.
9. **Tách quá nhiều service vì muốn scale.** Nhiều round trip và dependency mới có thể tăng latency, availability risk.
10. **Cho rằng event-driven luôn đáng tin hơn.** Broker có queue lag, redelivery, ordering và failure modes riêng.
11. **Không kiểm thử lỗi mất phản hồi sau commit.** Đây là tình huống nguy hiểm với tiền và tồn kho.
12. **Dùng HTTP 200 làm thước đo duy nhất.** Workflow có thể trả 200 nhưng bị kẹt ở pending, mất event hoặc sai trạng thái.

## 20. Checklist thiết kế API giữa các microservice

Trước khi đưa một lời gọi network vào luồng quan trọng, hãy trả lời:

- [ ] Có cần lời gọi đồng bộ không, hay có thể dùng xử lý bất đồng bộ?
- [ ] Endpoint có **deadline** và timeout hữu hạn ở những pha cần thiết?
- [ ] Tổng timeout các dependency có hợp với deadline của client?
- [ ] Client có giới hạn concurrency, pool wait và queue length?
- [ ] Lỗi nghiệp vụ khác lỗi network và trạng thái chưa xác định như thế nào?
- [ ] Retry chỉ áp dụng cho trường hợp được phép, có attempt/budget/backoff/jitter?
- [ ] Có nguy cơ nhiều tầng cùng retry và nhân tải không?
- [ ] POST có side effect dùng operation ID và idempotency được server bảo đảm?
- [ ] Khi response mất, có cách query/reconcile trạng thái không?
- [ ] Dependency lỗi có thể được cô lập bằng bulkhead, circuit breaker hoặc degrade không?
- [ ] API có metrics, trace context và correlation ID, không lộ secret?
- [ ] Có đo p95/p99 từ đúng điểm và trong các điều kiện tải phù hợp?
- [ ] Có test packet loss, connect/reset, timeout sau commit, redelivery và phục hồi?
- [ ] Có thể khôi phục trạng thái tiền, đơn, tồn kho đúng sau partial failure?

Checklist giúp tìm rủi ro; không nhất thiết phải thêm tất cả cơ chế cho mọi endpoint. Chọn biện pháp tương xứng với yêu cầu chất lượng và chi phí.

## 21. Bài tập thực hành

### Bài tập 1 — Timeout khi giữ hàng

Order gửi reserve tới Inventory. Inventory ghi DB thành công, nhưng response bị mất và Order timeout sau 500 ms.

Hãy giải thích những trạng thái có thể xảy ra, cách tránh giữ hàng hai lần, cách thiết kế query status và khi nào chuyển sang trạng thái cần đối soát.

### Bài tập 2 — Lập latency budget

API tổng hợp trang chủ cần dữ liệu Profile, Order và Recommendation. Mục tiêu p95 từ người dùng là 600 ms trong tải đã thống nhất. Hãy so sánh gọi tuần tự với gọi song song, cấp budget cho các service và quyết định Recommendation có thể bị bỏ qua khi lỗi hay không.

### Bài tập 3 — Retry amplification

Gateway retry Order tối đa ba lần. Order retry Payment tối đa ba lần. Hãy tính số attempt Payment tối đa có thể xuất hiện từ một request, giải thích vì sao cấu hình này nguy hiểm khi Payment quá tải và đề xuất retry budget.

### Bài tập 4 — Phân biệt mất gói và nghẽn DB

Hệ thống thấy p99 tăng từ 200 ms lên 2.000 ms. Network RTT gần như không đổi nhưng DB lock wait và connection pool wait tăng mạnh. Hãy đề xuất trình tự điều tra, xác định bằng chứng nào bác bỏ giả thuyết packet loss là nguyên nhân chính.

### Bài tập 5 — Thiết kế thử nghiệm lỗi mạng

Hãy phác thảo một fault-injection test cho tình huống Payment commit thành công rồi client mất kết nối. Định nghĩa dữ liệu thử, cách mô phỏng, metrics, kết quả nghiệp vụ mong đợi và điều kiện dừng. Không dùng giao dịch tài chính thật.

## 22. Tự kiểm tra kiến thức

1. Propagation delay, transmission delay và queueing delay khác nhau như thế nào?
2. Vì sao tăng băng thông không chắc làm giảm RTT?
3. Khi fan-out gọi nhiều dịch vụ song song, tail latency có thể bị khuếch đại như thế nào?
4. Packet loss trên TCP thường dẫn tới phản ứng nào của tầng truyền tải?
5. Vì sao timeout không chứng minh request chưa được server xử lý?
6. Connect timeout khác read timeout và deadline tổng ở điểm nào?
7. Vì sao cộng p95 của nhiều service không cho ra p95 của toàn request?
8. Retry storm hình thành thế nào và backoff có jitter giúp ích ra sao?
9. Idempotency key do client gửi và logic deduplication ở server có quan hệ gì?
10. Một retry HTTP có thể nhân đôi tác dụng nghiệp vụ dù TCP có retransmission không?
11. Circuit breaker khác bulkhead và load shedding như thế nào?
12. Khi nào nên cho một dependency degrade thay vì trả lỗi toàn bộ request?
13. Transactional Outbox xử lý loại lỗi nào và còn giới hạn gì?
14. Những số đo nào giúp phân biệt lỗi network, proxy, thread pool và database?
15. Tại sao phải kiểm tra số đơn/payment pending bên cạnh HTTP error rate?

## 23. Kết luận

**Độ trễ, mất gói và partial failure là những điều kiện bình thường của hệ thống phân tán.** Khi chia phần mềm thành microservices, ta đổi một phần lời gọi nội bộ thành giao tiếp mạng, vì vậy phải tính thời gian chờ, giới hạn tài nguyên, khả năng hỏng và cách khôi phục trạng thái ngay trong thiết kế.

Một hệ thống đáng tin không chỉ giảm p95/p99 bằng tối ưu network. Nó còn phải biết **điều gì đã xảy ra với nghiệp vụ khi mất phản hồi**, có cơ chế retry an toàn, idempotency, đối soát, quan sát và phục hồi sau lỗi. Lựa chọn timeout, retry, circuit breaker, async messaging và phân chia ranh giới dịch vụ cần dựa trên đo đạc cùng yêu cầu chất lượng cụ thể, thay vì kỳ vọng mạng luôn hoạt động hoàn hảo.
