# Ý nghĩa và giới hạn của timeout, retry và tín hiệu hủy trong Microservices

## Mục tiêu học tập

Khi một dịch vụ gọi dịch vụ khác qua mạng, có ba câu hỏi độc lập nhưng thường bị trộn lẫn: **Ta chờ phản hồi trong bao lâu?**, **khi không nhận được phản hồi, có nên thử lại không?**, và **khi người gọi không còn cần kết quả, làm cách nào yêu cầu tác vụ dừng lại?** Timeout, retry và tín hiệu hủy (cancellation signal) là ba cơ chế trả lời ba câu hỏi đó.

Sau bài học, người học cần:

1. Phân biệt rõ **timeout là giới hạn thời gian chờ** với **thất bại của thao tác nghiệp vụ**; hiểu rằng thiếu phản hồi không chứng minh thao tác chưa thực hiện.
2. Thiết lập deadline chung và phân bổ thời gian cho các lần gọi, retry, xử lý hàng đợi và trả kết quả, thay vì cộng các timeout tùy tiện.
3. Quyết định có retry hay không dựa trên **loại lỗi, tính an toàn khi lặp, ngân sách thời gian và tình trạng tải**.
4. Giải thích vì sao retry cần idempotency, backoff, jitter, số lần thử tối đa, và thường chỉ nên được thực hiện tại một tầng chịu trách nhiệm rõ ràng.
5. Hiểu cancellation là một **tín hiệu yêu cầu ngừng xử lý**, không phải bảo đảm tác vụ đã dừng hoặc hiệu ứng nghiệp vụ đã bị đảo ngược.
6. Thiết kế và quan sát được các tình huống khó: server xử lý thành công sau khi client timeout, retry gây trùng, người dùng hủy trong lúc thanh toán, và lệnh hủy đến sau khi tác vụ hoàn tất.

**Bối cảnh:** Các nguyên tắc dưới đây áp dụng cho HTTP/REST, gRPC, RPC nội bộ, tác vụ bất đồng bộ, message broker, cơ sở dữ liệu và job chạy nền. Ví dụ sử dụng Microservices với Order, Inventory và Payment, nhưng logic không phụ thuộc một framework cụ thể.

## 1. Vì sao ba cơ chế này đi cùng nhau?

Trong chương trình gọi hàm nội bộ, một lỗi thường được quan sát ngay trong cùng tiến trình. Với hệ thống phân tán, client có thể nhìn thấy **không có phản hồi** dù server chưa nhận yêu cầu, đang xử lý, đã commit, hoặc đã trả kết quả nhưng gói tin phản hồi bị thất lạc.

Xét Order gửi yêu cầu **tạo giao dịch thanh toán** tới Payment:

1. Order gửi yêu cầu với mã đơn O-101.
2. Payment nhận yêu cầu, lưu giao dịch và gọi cổng thanh toán.
3. Payment ghi nhận thành công.
4. Phản hồi về Order bị trễ hoặc kết nối bị ngắt.
5. Order hết thời gian chờ.

Ở bước 5, Order chỉ biết mình **không nhận được xác nhận đúng hạn**. Order không biết chắc Payment đã hoàn tất hay chưa. Nếu Order retry với một yêu cầu tạo giao dịch mới không có khóa chống trùng, khách hàng có thể bị tính tiền hai lần.

~~~mermaid
sequenceDiagram
    participant O as Order (client)
    participant N as Network
    participant P as Payment (server)
    O->>N: Request O-101
    N->>P: Request O-101
    P->>P: Ghi nhận thanh toán thành công
    P-->>N: Kết quả thành công
    Note over N: Phản hồi đến muộn hoặc bị mất
    Note over O: Timeout: chưa nhận được kết quả
    O->>N: Retry cùng thao tác?
    Note over O,P: Cần idempotency và khả năng đối soát
~~~

**Nguyên tắc nền tảng:** Timeout nói về **khả năng quan sát kết quả trong một thời hạn**; retry nói về **việc tạo thêm lần thực thi hoặc truyền yêu cầu**; cancellation nói về **ý định ngừng công việc không còn hữu ích**. Không cơ chế nào tự động đảm bảo tính đúng đắn của trạng thái nghiệp vụ.

### Bảng phân biệt

| Khái niệm | Điều nó khẳng định | Điều nó không khẳng định | Rủi ro chính |
|---|---|---|---|
| Timeout | Người chờ đã vượt một mốc thời gian | Server chắc chắn chưa thực hiện, đã rollback hoặc đã ngừng làm việc | Kết quả mơ hồ, công việc vô ích vẫn chạy |
| Retry | Client hoặc hạ tầng gửi/thực hiện lại yêu cầu | Lần đầu chưa được xử lý hoặc lần tiếp theo không tạo tác dụng phụ | Trùng side effect, bão tải, thêm độ trễ |
| Cancellation signal | Một bên phát tín hiệu không còn muốn tác vụ tiếp tục | Bên nhận đã thấy tín hiệu, có thể ngừng hoặc đã hoàn tác | Race condition với commit, tài nguyên chưa được giải phóng |
| Deadline | Mốc kết thúc của ngân sách thời gian dành cho một operation | Mọi tác vụ con đã nhận và tuân thủ deadline | Còn tác vụ chạy sau hạn, truyền budget sai |
| Idempotency | Lặp lại cùng thao tác với cùng định danh không tạo thêm hiệu ứng nghiệp vụ ngoài ý định | Yêu cầu sẽ không được truyền lặp hoặc thực thi code handler lặp | Dùng sai định danh, mất bản ghi khử trùng, trạng thái chạy dở |

Hãy xem đây là một nhóm quyết định phối hợp. Timeout hợp lý nhưng retry vô hạn vẫn làm hệ thống quá tải; retry có backoff nhưng không có idempotency vẫn có thể tạo dữ liệu sai; cancellation nhanh nhưng không có quản lý trạng thái nghiệp vụ vẫn có thể để lại thanh toán hoặc reservation chưa được đối soát.

## 2. Timeout là gì và timeout đang đo đoạn nào?

Một **timeout** là thời gian tối đa dành cho một giai đoạn hoặc một thao tác chờ. Khi giới hạn bị vượt, bên chờ thường trả lỗi hoặc ngừng chờ. Timeout là một **quy tắc ở phía quan sát**, không phải một sự kiện chứng minh phía kia đã thất bại.

Các timeout có phạm vi khác nhau:

| Loại | Giới hạn phần nào | Ví dụ | Nhầm lẫn cần tránh |
|---|---|---|---|
| Connect timeout | Thời gian thiết lập kết nối tới điểm đích | Kết nối TCP tới Inventory | Không giới hạn toàn bộ thời gian xử lý request |
| TLS/handshake timeout | Thời gian thiết lập kênh bảo mật | TLS handshake với Payment | Không thay thế request deadline |
| Response/request timeout | Thời gian chờ phản hồi hoặc hoàn thành request theo hợp đồng thư viện | Order gọi API tồn kho | Không suy ra server đã hủy giao dịch |
| Read/idle timeout | Khoảng chờ dữ liệu tiếp theo trên kết nối | Đọc body hoặc stream | Có thể được làm mới bởi dữ liệu đến từng phần; không phải giới hạn tổng |
| Queue wait timeout | Thời gian nằm trong hàng đợi trước khi được xử lý | Task chờ worker | Không đảm bảo task đã bị loại khỏi queue |
| Server processing timeout | Giới hạn thời gian xử lý trong server | Payment truy vấn database | Có thể không chặn được thao tác I/O không hợp tác |
| Database/query timeout | Thời gian chạy câu lệnh hoặc đợi dữ liệu | Truy vấn tồn kho | Không đồng nghĩa toàn request HTTP đã bị hủy |
| Overall deadline | Ngân sách từ lúc bắt đầu đến kết quả cần thiết | Tạo đơn trong 2 giây | Không tự lan qua mọi service nếu không truyền và thực thi |

**Ví dụ:** Có connect timeout 200 ms và request timeout 800 ms không đồng nghĩa chắc chắn tổng thời gian hệ thống luôn tối đa 1 giây. Cách thư viện tính timeout, queueing, DNS, retry, xử lý phía server, middleware và các bước trước/sau lời gọi có thể làm thời gian thực tế khác đáng kể. Luôn xác định **phạm vi chính xác** theo client/server library và có một ngân sách tổng ở tầng nghiệp vụ.

### Timeout không phải kết luận về trạng thái

Sau timeout, có ít nhất bốn khả năng:

- Request chưa được gửi hoặc chưa đến server.
- Request đã đến nhưng chưa được thực thi.
- Request đang thực thi và có thể hoàn thành sau timeout.
- Request đã hoàn thành, nhưng response không đến client đúng hạn.

Vì không thể phân biệt hoàn toàn các khả năng chỉ bằng một lỗi timeout, thao tác có side effect phải có **định danh truy vấn trạng thái**, cơ chế idempotency hoặc đối soát. Không được tùy tiện chuyển nghiệp vụ sang FAILED vĩnh viễn chỉ vì một lời gọi mạng hết hạn.

### Giá trị timeout nên dựa trên dữ liệu nào?

Bắt đầu từ **ngân sách người dùng chấp nhận**, SLO, độ trễ bình thường và độ trễ ở phần đuôi phân phối (p95/p99). Xem thêm RTT qua mạng, proxy, vùng địa lý, tải đỉnh, hàng đợi và thời gian phụ thuộc. Timeout quá ngắn tạo nhiều lỗi giả và retry; timeout quá dài khiến thread, kết nối, hàng đợi và tài nguyên bị giữ khi hệ thống đã không còn đáp ứng được yêu cầu.

Ví dụ, nếu p99 của Inventory ở mức khoảng 180 ms trong điều kiện bình thường, đặt request timeout 100 ms có thể gây lỗi thường xuyên. Đặt 30 giây cho một API người dùng cần hoàn tất trong 2 giây cũng không hợp lý. Con số phải được thử dưới tải và điều chỉnh dựa trên mục tiêu thực, không sao chép từ cấu hình mặc định.

## 3. Deadline chung và ngân sách thời gian

**Timeout theo từng lần gọi** trả lời: “Một attempt được chờ tối đa bao lâu?”  
**Deadline chung** trả lời: “Operation này còn giá trị đến thời điểm nào?”

Giả sử request từ người dùng có **ngân sách tổng 2.000 ms**, gồm xác thực, xử lý Order, gọi Inventory/Payment, độ trễ mạng và thời gian trả response. Nếu chỉ cấu hình mỗi dependency timeout 2.000 ms rồi thực hiện hai lời gọi nối tiếp, tổng request có thể vượt xa thời gian người dùng mong đợi.

Một cách phân bổ mang tính minh họa:

| Phần việc | Ngân sách dự kiến |
|---|---:|
| Xác thực, kiểm tra đầu vào, xử lý ban đầu | 150 ms |
| Inventory (bao gồm tối đa hai lần thử nếu còn thời gian) | 500 ms |
| Payment (hoặc tạo trạng thái xử lý tiếp bất đồng bộ) | 900 ms |
| Lưu trạng thái Order và chuẩn bị response | 150 ms |
| Dự phòng mạng, hàng đợi và dao động | 300 ms |
| **Tổng** | **2.000 ms** |

Không nên coi bảng này là bộ timeout cố định cho mọi hệ thống. Tác vụ nối tiếp, song song và bất đồng bộ có cách tiêu thụ ngân sách khác nhau; riêng thời gian dự phòng phải được đo từ lưu lượng thật.

### Tính thời gian còn lại

Dùng một mốc thời gian đơn điệu trong tiến trình để đo elapsed time, chẳng hạn **System.nanoTime()** trong Java:

**remaining = totalBudget − elapsed**

Trước mỗi attempt, chỉ cấp **perAttemptTimeout ≤ remaining**; trước mỗi lần ngủ backoff, kiểm tra còn đủ thời gian để retry và xử lý tiếp hay không. Nếu gần deadline, ưu tiên trả trạng thái phù hợp hoặc chuyển sang xử lý nền có chủ đích thay vì tạo một lời gọi chắc chắn vô ích.

Khi đi qua nhiều service, có thể truyền một **deadline hoặc remaining budget** qua metadata/hợp đồng nội bộ (gRPC có hỗ trợ khái niệm deadline; HTTP có thể cần quy ước riêng). Khi truyền thời điểm tuyệt đối giữa các máy, phải xét chênh lệch đồng hồ; không tự động tin budget do client ngoài hệ thống gửi. Tầng nhận nên áp dụng giới hạn cục bộ tối đa và trừ đi chi phí xử lý đã tiêu thụ.

### Quan hệ giữa deadline và cancellation

Khi deadline hết, bên gọi thường phát sinh timeout và có thể gửi tín hiệu hủy xuống tầng phụ thuộc. Nhưng việc một tầng đã hết deadline **không đảm bảo** mọi tác vụ con, database query, message đã phát hoặc giao dịch của bên thứ ba đều dừng. Muốn thật sự giảm công việc vô ích, mỗi tầng cần **nhận, chuyển tiếp và tôn trọng tín hiệu hủy** ở các điểm phù hợp.

## 4. Retry là chính sách có điều kiện, không phải phản xạ với mọi lỗi

Retry hữu ích khi lỗi có khả năng **tạm thời**: mất kết nối thoáng qua, server đang chuyển phiên bản, một instance ngừng đáp ứng, hoặc gateway trả 503 trong đợt sự cố ngắn. Retry có thể giảm lỗi người dùng nếu có instance khác khỏe hoặc sự cố hồi phục nhanh.

Tuy nhiên, retry cũng tạo **thêm lưu lượng và side effect**, khiến hệ thống vốn đang quá tải càng chậm. Mỗi retry còn tiêu thụ deadline; lỗi vĩnh viễn không tự biến mất sau nhiều lần gọi.

### Bốn câu hỏi trước khi retry

1. **Có lý do tin lỗi là tạm thời không?** Validation lỗi, xác thực sai, thiếu quyền hoặc vi phạm nghiệp vụ thường sẽ không được giải quyết bằng retry.
2. **Thao tác lặp có an toàn không?** GET đọc dữ liệu thường ít side effect hơn POST tạo giao dịch, nhưng ý nghĩa thực tế và hợp đồng server mới quyết định. Một phương thức HTTP không thay thế hiểu biết về nghiệp vụ.
3. **Có đủ ngân sách và năng lực xử lý không?** Retry phải có giới hạn attempts, backoff/jitter, deadline và kiểm soát tải.
4. **Tầng nào sở hữu retry?** Nếu client, gateway, service và SDK đều tự retry, số lần thực hiện có thể nhân lên ngoài ý muốn.

### Bảng quyết định minh họa cho HTTP

| Tín hiệu | Chính sách khởi đầu | Giải thích |
|---|---|---|
| 400, 422 do dữ liệu sai | Không retry nguyên yêu cầu | Cần sửa dữ liệu hoặc quy tắc |
| 401, 403 | Không retry mù | Cần xác thực hoặc quyền hợp lệ; quy trình refresh token riêng nếu có |
| 404 | Thường không retry | Có ngoại lệ nếu API có tài nguyên xuất hiện trễ và hợp đồng quy định |
| 409, 412 | Không retry y nguyên theo mặc định | Có thể là xung đột phiên bản/điều kiện; phải đọc lại trạng thái và quyết định |
| 429 | Chỉ retry khi chính sách và deadline cho phép | Tôn trọng Retry-After/rate limit; thêm jitter, không làm tăng bão yêu cầu |
| 500 | Tùy hợp đồng và idempotency | Server lỗi có thể xảy ra sau commit; không coi 500 là chắc chắn chưa có side effect |
| 502, 503, 504 | Có thể retry có giới hạn | Khả năng lỗi tạm thời; cần xét Retry-After, thời gian còn lại và tải |
| Connect failure, reset | Có thể retry nếu thao tác an toàn | Không phải mọi lỗi kết nối chứng minh server chưa thực thi |
| Read/request timeout | Chỉ retry nếu an toàn và còn budget | Kết quả nghiệp vụ có thể đã hoàn thành |
| Client đã hủy / deadline hết | Dừng retry | Không phát thêm công việc khi kết quả không còn giá trị |

Đây là **chính sách khởi đầu để thảo luận**, không phải bảng hành vi mặc định bắt buộc. Một API thanh toán, gửi email hoặc cập nhật tồn kho có điều kiện riêng; client phải theo hợp đồng của dependency và ý nghĩa nghiệp vụ.

### Backoff, jitter, số lần thử và retry budget

Một chính sách phổ biến là **exponential backoff với jitter**:

~~~text
attempt đầu: gửi ngay
sau lỗi lần 1: nghỉ ngẫu nhiên trong [0, min(cap, base × 2^0)]
sau lỗi lần 2: nghỉ ngẫu nhiên trong [0, min(cap, base × 2^1)]
sau lỗi lần 3: nghỉ ngẫu nhiên trong [0, min(cap, base × 2^2)]
...
Dừng khi vượt maxAttempts, deadline, retry budget hoặc gặp lỗi không retry.
~~~

**Jitter** tránh trường hợp hàng nghìn client cùng thất bại rồi cùng retry ở đúng mốc 100 ms, 200 ms, 400 ms. **Backoff** để dịch vụ phụ thuộc có cơ hội phục hồi; **maxAttempts** và **overall deadline** chặn việc kéo dài vô hạn.

Một giới hạn bổ sung là **retry budget**: lượng retry được phép chỉ chiếm một phần nhỏ lưu lượng hoặc tổng chi phí của các request ban đầu trong một cửa sổ thời gian. Mục đích là tránh việc khi error rate tăng, retry biến thành nguyên nhân chính của overload. Khi server trả 429 hoặc Retry-After, ưu tiên tuân thủ chỉ dẫn của server và ngừng retry nếu thời điểm được phép thử lại đã vượt deadline.

**Cảnh báo về nhân lần gọi:** Nếu ba tầng client → API gateway → Order đều “thử tối đa ba lần” cho cùng một thao tác, tình huống xấu có thể dẫn đến **3 × 3 × 3 = 27 attempts ở tầng sâu nhất**. Trong đó có thể chứa nhiều side effect hoặc tạo núi request khi Payment chậm. Cần xác định **một tầng sở hữu retry cho operation cụ thể**, hoặc phối hợp policy giữa các tầng.

### Các kỹ thuật liên quan nhưng khác retry

- **Circuit breaker:** Khi dependency lỗi vượt ngưỡng, ngắt nhanh một thời gian để bảo vệ tài nguyên và tránh tiếp tục gọi vô ích. Không sửa được tính đúng đắn của việc retry giao dịch.
- **Bulkhead/concurrency limit:** Giới hạn số luồng/kết nối/request đồng thời dành cho một dependency để sự cố không nuốt toàn bộ tài nguyên.
- **Rate limiting và load shedding:** Chặn hoặc giảm lưu lượng khi hệ thống quá tải. Retry phải phối hợp với các tín hiệu này.
- **Queue/backpressure:** Dời hoặc giới hạn công việc; không đồng nghĩa xử lý đã xong và cần giám sát tuổi công việc trong queue.

Một policy retry đúng phải nằm trong bức tranh về tải và độ tin cậy toàn hệ thống.

## 5. Retry an toàn: idempotency và kết quả không chắc chắn

**Idempotency** trong ngữ cảnh nghiệp vụ là: nhận lại cùng một **logical request** với cùng định danh không tạo thêm side effect ngoài ý định. Có thể handler nhận message và chạy mã nhiều lần, nhưng tác dụng nghiệp vụ cuối cùng vẫn được kiểm soát.

Với POST tạo payment, client có thể gửi:

~~~http
POST /payments
Idempotency-Key: order-O-101-charge-v1
Content-Type: application/json

{"orderId":"O-101","amount":250000,"currency":"VND"}
~~~

Payment phải triển khai logic server-side, không chỉ tin rằng header xuất hiện sẽ tự chống trùng:

1. Lấy khóa idempotency và xác thực phạm vi sử dụng (tenant, merchant, action).
2. Tạo **request fingerprint** cho dữ liệu quan trọng (ví dụ orderId, amount, currency, người thụ hưởng). Cùng key nhưng payload khác phải bị từ chối hoặc xử lý theo hợp đồng rõ ràng.
3. Sử dụng ràng buộc uniqueness/transaction hoặc cơ chế đồng bộ tương đương để hai request đến cùng lúc không cùng tạo hai payment.
4. Lưu **trạng thái đang xử lý và kết quả cuối** theo key. Khi request lặp đến, trả lại kết quả đã hoàn tất hoặc trạng thái đang xử lý, thay vì kích hoạt lần tính tiền mới.
5. Nếu tương tác với provider bên ngoài, dùng **mã tham chiếu idempotent do provider hỗ trợ**, hoặc đối soát trước khi yêu cầu thu tiền lại; uniqueness ở DB nội bộ không tự bảo đảm provider không thu hai lần.
6. Xác định chính sách thời hạn lưu key, retry sau hết hạn, chuyển trạng thái, lỗi vĩnh viễn và khả năng truy vấn lại.

~~~mermaid
flowchart TD
    R["Nhận request + Idempotency-Key"] --> F{"Key đã tồn tại?"}
    F -- "Chưa" --> U["Đăng ký key atomically / UNIQUE"]
    U --> P["Thực thi và lưu kết quả"]
    P --> E["Trả kết quả"]
    F -- "Có" --> M{"Fingerprint khớp?"}
    M -- "Không" --> C["Từ chối xung đột payload"]
    M -- "Có" --> S{"Trạng thái key?"}
    S -- "Đã hoàn tất" --> O["Trả kết quả đã lưu"]
    S -- "Đang xử lý" --> W["Trả pending / chờ có giới hạn / truy vấn"]
~~~

**Điểm cần phân biệt:** Idempotency bảo vệ logical effect; **deduplication** thường giúp nhận diện message đã xử lý; **exactly-once delivery** là một cam kết của từng hệ thống truyền tải nếu có, không tự mở rộng thành exactly-once side effect xuyên database, broker và cổng thanh toán.

Ví dụ với message broker: consumer nhận **PaymentAuthorized** hai lần. Nếu mỗi lần đều chuyển Order và gửi email độc lập, có thể phát sinh hậu quả lặp. Consumer cần key sự kiện hoặc khóa nghiệp vụ, lưu mốc xử lý, và quy tắc transition trạng thái chỉ được áp dụng hợp lệ một lần.

### Khi timeout xảy ra sau commit

Trình tự có thể là:

~~~text
t = 0 ms      Order gửi create payment, key K
t = 400 ms    Payment thực hiện xong giao dịch và commit
t = 500 ms    Order timeout trước khi thấy response
t = 650 ms    Order retry với cùng key K
t = 680 ms    Payment trả kết quả đã lưu cho K, không tạo charge mới
~~~

Nếu lần đầu đang thực thi, retry phải được xử lý như **cùng một thao tác đang chạy**. Nếu nhà cung cấp thanh toán trả kết quả không xác định, ưu tiên hỏi trạng thái theo transaction reference thay vì tạo payment với key mới.

**Phân biệt retry kỹ thuật và retry nghiệp vụ:** Retry kỹ thuật khôi phục một attempt truyền/nhận lỗi trong cùng logical operation. Một lần người dùng chủ động thanh toán lại sau khi giao dịch trước thất bại xác định là **nghiệp vụ mới**; định danh và điều kiện cho lần mới phải do chính sách sản phẩm quyết định.

## 6. Cancellation signal: yêu cầu ngừng, không phải quyền năng hoàn tác

Cancellation signal là thông tin từ bên gọi hoặc bộ điều phối rằng tác vụ **không còn cần tiếp tục** hoặc **phải ngừng vì chính sách**. Nguồn phát tín hiệu thường là:

- Người dùng bấm Hủy.
- Client đóng kết nối hoặc thoát màn hình.
- Parent request chạm deadline.
- Một nhánh chạy song song đã có kết quả đủ dùng, nhánh còn lại trở nên thừa.
- Dịch vụ đang shutdown, hệ thống vượt tải hoặc có quyết định hủy job.

Một cancellation signal hữu ích phải có **nơi phát**, **đối tượng nhận**, **cách chuyển tiếp**, **điểm kiểm tra**, **trạng thái xác nhận** và **quy tắc nghiệp vụ nếu đã commit**. Nếu không, cancel chỉ là thay đổi trạng thái UI còn backend vẫn chạy.

### Ba mức ý nghĩa cần tách bạch

1. **Ngừng chờ:** Client ngừng đợi và trả quyền điều khiển cho người dùng. Server có thể vẫn đang chạy.
2. **Yêu cầu dừng xử lý:** Client/middleware gửi cancel hoặc đóng stream; server, worker, database driver hoặc SDK có thể nhận tín hiệu và chủ động dừng tại điểm hỗ trợ.
3. **Hủy kết quả nghiệp vụ:** Cần một transition/compensation được định nghĩa riêng. Hủy việc chờ **không** tự động xóa payment, hoàn tiền, khôi phục kho hay rollback một transaction đã commit.

Trong nhiều môi trường, cancellation là **cooperative**: tác vụ kiểm tra token/interrupt/deadline, truyền cho lời gọi con, đóng tài nguyên hỗ trợ và kết thúc sạch. Code đang chạy CPU mà không kiểm tra tín hiệu, I/O không hỗ trợ cancel, remote call đã được chấp nhận hay message đã gửi có thể không dừng ngay.

### Cancellation trong Java

Với task chạy qua ExecutorService, **Future.cancel(true)** có thể yêu cầu interrupt thread đang thực thi; chương trình phải xử lý interrupt đúng cách:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

Future<?> task = executor.submit(() -> {
    try {
        for (int part = 0; part < 100; part++) {
            if (Thread.currentThread().isInterrupted()) {
                return; // Điểm hợp tác để dừng
            }
            processPart(part);
            Thread.sleep(20); // Ví dụ chờ có thể bị interrupt
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Dọn tài nguyên nếu cần; không tiếp tục sinh side effect.
    }
});

// Ở luồng điều phối:
task.cancel(true); // Gửi yêu cầu hủy, không bảo đảm việc từ xa đã rollback.
executor.shutdown();
~~~

Trong ví dụ, **processPart** là một hàm minh họa do ứng dụng tự cài. Nếu nó gọi dịch vụ Payment và bên đó đã commit, interrupt chỉ tác động đến thread cục bộ; Payment không có nghĩa vụ tự rollback. Một số thư viện/driver có hỗ trợ hủy request; cần kiểm tra ngữ nghĩa cụ thể của chúng.

**Lưu ý kỹ thuật:** Không được suy ra rằng mọi Future đều xử lý interrupt giống nhau. Chẳng hạn, cờ **mayInterruptIfRunning** của CompletableFuture.cancel không đảm bảo ngắt thread thực thi công việc. HTTP client, reactive pipeline, stream và driver thường có cơ chế cancel riêng. Muốn tin cancellation đã đến nơi, phải có bằng chứng từ tầng đó.

### Truyền cancellation trong chuỗi gọi

~~~mermaid
flowchart LR
    U["Người dùng / API client"] --> A["Gateway"]
    A --> O["Order"]
    O --> I["Inventory"]
    O --> P["Payment"]
    U -. "Huỷ / deadline" .-> A
    A -. "Truyền cancel / budget" .-> O
    O -. "Truyền khi hỗ trợ" .-> I
    O -. "Truyền khi hỗ trợ" .-> P
~~~

Việc gateway đóng HTTP response không đảm bảo tự động cancel câu query database hay tác vụ background. Các tầng cần có cơ chế rõ ràng để:

- Ngừng mở những lời gọi con **chưa bắt đầu** khi budget đã hết.
- Chuyển tiếp deadline/cancellation qua thư viện có hỗ trợ.
- Gọi phương thức cancel/abort cụ thể nếu còn có thể dừng.
- Đảm bảo lock, thread, connection, subscription và tài nguyên được giải phóng.
- Phân loại kết quả **CANCEL_REQUESTED**, **CANCELLED**, **ALREADY_COMPLETED** hoặc **UNKNOWN**, tùy hợp đồng.
- Không báo đã hủy thành công một thao tác có side effect khi chưa có xác nhận.

### Race condition: hủy đúng lúc commit

Giả sử người dùng bấm **Hủy thanh toán** gần thời điểm Payment hoàn tất:

~~~text
t = 0       Payment bắt đầu tạo giao dịch
t = 200 ms  Người dùng bấm Hủy
t = 210 ms  Order gửi cancellation signal
t = 220 ms  Payment commit charge
t = 230 ms  Payment nhận tín hiệu hủy (đã quá muộn)
~~~

Trong tình huống này, không thể chỉ xem mốc nhấn nút hoặc thứ tự gửi thông điệp để kết luận charge không xảy ra. Thiết kế phải quy định rõ **điểm không thể hủy** (point of no return). Khi đã qua điểm đó, lựa chọn có thể là trả **ALREADY_COMPLETED**, hoặc bắt đầu một nghiệp vụ bù trừ riêng như refund, với trạng thái và xác nhận độc lập.

**Cancellation không đồng nghĩa compensation.** Cancellation cố ngăn công việc tiếp theo; compensation sửa hệ quả của công việc đã hoàn thành. Refund là giao dịch mới có chính sách, idempotency và khả năng thất bại riêng; không được gọi nó là “rollback tự động”.

## 7. Timeout, retry và cancellation tương tác với nhau ra sao?

Có ba quy tắc phối hợp quan trọng:

**Quy tắc 1 — Deadline kết thúc quyền retry.** Khi overall deadline đã hết hoặc người dùng đã hủy, không tiếp tục retry như thể chưa có gì thay đổi. Chỉ có một quy trình nghiệp vụ nền được giao quyền rõ ràng mới có thể tiếp tục sau khi HTTP request kết thúc.

**Quy tắc 2 — Cancellation không thay thế idempotency.** Có thể tín hiệu cancel đến sau khi thao tác đầu tiên đã tạo side effect. Nếu retry của yêu cầu cũ hoặc job phục hồi vẫn còn, hệ thống vẫn cần khóa idempotency và đối soát.

**Quy tắc 3 — Kết quả không chắc chắn cần trạng thái rõ ràng.** Một timeout có thể tạo trạng thái **PENDING/UNKNOWN** tại Order. Sau đó hệ thống truy vấn Payment theo transaction reference hoặc nhận event kết quả. Không gán **FAILED** nghiệp vụ chỉ vì client timeout, trừ khi hợp đồng đảm bảo không thể có side effect sau timeout.

### Ma trận tình huống

| Tình huống | Hành vi phù hợp | Sai lầm dễ gặp |
|---|---|---|
| GET Inventory timeout, còn 700 ms và backend ổn | Retry tối đa theo policy, backoff/jitter trong budget | Retry vô hạn hoặc mỗi tầng tự retry |
| POST Payment timeout, có idempotency key K | Kiểm tra trạng thái hoặc retry cùng K theo hợp đồng | Sinh key mới và tạo charge thứ hai |
| Server trả 429 + Retry-After vượt deadline | Dừng retry và trả tín hiệu quá tải phù hợp | Ngủ qua deadline rồi retry |
| Người dùng đóng trang khi tác vụ đang chờ query | Cancel những nhánh còn có thể hủy, giải phóng tài nguyên | Khẳng định database và remote task đã rollback |
| Người dùng hủy khi Payment đã commit | Trả trạng thái đã hoàn thành hoặc mở quy trình refund | Ghi CANCELLED nhưng giữ nguyên charge không đối soát |
| Message đến trùng sau khôi phục | Dedup/idempotent consumer, trạng thái monotonic | Coi event nào cũng mới và phát side effect lại |
| Một dependency ngừng đáp ứng trên diện rộng | Giới hạn attempts, concurrency và circuit breaker | Tăng retry khiến dependency kiệt sức hơn |

### Ai sở hữu trách nhiệm?

Một lựa chọn thiết kế thường có trách nhiệm theo lớp như sau:

- **Client/UI:** Hiển thị trạng thái đang chờ, cho phép người dùng yêu cầu hủy, không mặc định rằng timeout là thất bại nghiệp vụ.
- **API gateway:** Áp dụng giới hạn request, auth, rate limit và chuyển metadata budget khi phù hợp; tránh retry độc lập các thao tác có side effect.
- **Application service:** Nắm business deadline, quyết định operation có thể retry, định danh idempotency, quản lý trạng thái UNKNOWN/PENDING và phát event đối soát.
- **Dependency client/SDK:** Triển khai connect/request timeout, abort/cancel và số lần thử theo cấu hình được kiểm soát; tránh tự retry ngầm làm vượt policy.
- **Dependency server/worker:** Thực thi idempotency, tôn trọng deadline khi có thể, công bố trạng thái đã commit và cho phép truy vấn/đối soát.

Ranh giới trách nhiệm phải được ghi trong API contract và quyết định kiến trúc để nhóm client, server và hạ tầng không giả định sai về nhau.

## 8. Ví dụ Java: timeout tổng và retry có kiểm soát cho GET

Ví dụ Java 21 dùng **java.net.http.HttpClient** để đọc số lượng hàng từ Inventory. Đây là thao tác GET giả định không tạo side effect nghiệp vụ. Ví dụ chủ động có **connect timeout**, **per-attempt timeout**, **overall budget**, **tối đa ba attempts**, **full jitter** và **không bắt lỗi ngắt để retry**.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class InventoryGateway {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(200))
            .build();

    public String getInventory(URI uri, Duration totalBudget)
            throws IOException, InterruptedException {

        if (totalBudget.isNegative() || totalBudget.isZero()) {
            throw new IllegalArgumentException("totalBudget must be positive");
        }

        final long started = System.nanoTime();
        final long totalNanos = totalBudget.toNanos();
        IOException lastFailure = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            long remaining = totalNanos - (System.nanoTime() - started);
            if (remaining <= 0) {
                throw new HttpTimeoutException("Overall budget exhausted");
            }

            long perAttemptNanos = Math.min(
                    remaining,
                    Duration.ofMillis(450).toNanos()
            );
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofNanos(perAttemptNanos))
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

                int status = response.statusCode();
                if (status == 200) {
                    return response.body();
                }

                // Ví dụ chỉ retry một số lỗi gateway/server tạm thời.
                if (status != 502 && status != 503 && status != 504) {
                    throw new IOException("HTTP " + status + ": no retry");
                }

                // Không phớt lờ chỉ dẫn chờ từ server.
                if (response.headers().firstValue("Retry-After").isPresent()) {
                    throw new IOException(
                            "Retry-After requires a separate scheduling policy"
                    );
                }

                lastFailure = new IOException("Temporary HTTP " + status);
            } catch (HttpTimeoutException | ConnectException ex) {
                // Với GET thuần, có thể thử lại nếu còn budget.
                lastFailure = ex;
            }

            if (attempt == 3) {
                break;
            }

            long left = totalNanos - (System.nanoTime() - started);
            if (left <= 0) {
                break;
            }

            long upperMs = Math.min(200L, 50L * (1L << (attempt - 1)));
            long jitterMs = ThreadLocalRandom.current()
                    .nextLong(upperMs + 1);
            long delayNanos = TimeUnit.MILLISECONDS.toNanos(jitterMs);

            if (left <= delayNanos) {
                break;
            }

            // Có thể bị interrupt; không nuốt tín hiệu hủy.
            TimeUnit.NANOSECONDS.sleep(delayNanos);
        }

        if (lastFailure != null) {
            throw lastFailure;
        }
        throw new HttpTimeoutException("Request did not complete");
    }
}
~~~

**Cách đọc ví dụ:**

- **HttpClient.connectTimeout(200 ms):** Giới hạn thiết lập kết nối theo semantics của Java HttpClient; không thay thế timeout của request.
- **HttpRequest.timeout:** Mỗi attempt tối đa 450 ms hoặc thời gian tổng còn lại nếu nhỏ hơn. Chính xác phạm vi áp dụng theo API của Java HttpClient, không mặc định nó ngừng mọi tác vụ bên server.
- **System.nanoTime():** Đo elapsed time trong tiến trình, tránh phụ thuộc đồng hồ lịch có thể chỉnh. Ngân sách ví dụ phải là Duration nhỏ, hữu hạn; ứng dụng thật cần chuẩn hóa giới hạn đầu vào.
- **Tối đa ba attempts:** Bao gồm lần đầu. Backoff được chọn ngẫu nhiên trong một khoảng tăng dần và có trần.
- **InterruptedException được truyền lên:** Nếu thread bị interrupt trong lời gọi hoặc lúc ngủ, vòng retry không tiếp tục. Caller chịu trách nhiệm xử lý hủy và dọn dẹp.
- **Retry-After:** Ví dụ dừng và giao cho policy tầng trên xử lý thay vì cố retry sớm. Ứng dụng thật có thể parse Retry-After (số giây hoặc HTTP-date), kiểm tra deadline và rate limit trước khi lập lịch.
- **Những lỗi khác:** Bị ném ra ngay; không mặc định mọi IOException hoặc 500 đều transient.

**Giới hạn của mẫu:** Đây là code giảng giải một policy đơn giản, chưa bao gồm circuit breaker, retry budget toàn hệ thống, metrics/tracing, test clock, async cancellation, hay deadline truyền qua các hop. Khi dùng thư viện resilience hoặc HTTP client có retry tự động, phải kiểm tra không vô tình **chồng thêm một lớp retry khác**. Đừng sao chép policy GET này sang POST Payment.

### Phác thảo cho POST có side effect

Với POST tạo payment, trung tâm của thiết kế là cùng một **logical operation ID** đi qua tất cả attempts. Luồng ý tưởng:

~~~text
operationId = tạo một lần cho một yêu cầu nghiệp vụ
idempotencyKey = định danh ổn định gắn với operationId

gửi POST với idempotencyKey
nếu nhận kết quả chắc chắn:
    ghi kết quả và kết thúc
nếu timeout hoặc lỗi kết nối:
    kiểm tra remaining deadline
    truy vấn trạng thái theo operationId nếu API hỗ trợ
    nếu chưa xác định và policy cho phép:
        retry với CHÍNH idempotencyKey cũ
    nếu vẫn không xác định:
        giữ PENDING/UNKNOWN và đưa vào đối soát
nếu người dùng yêu cầu cancel:
    ngừng attempts không cần thiết
    xác định đã qua điểm có thể hủy hay chưa
    nếu đã commit, dùng quy trình bù trừ riêng (nếu nghiệp vụ cho phép)
~~~

Tính đúng đắn phụ thuộc implementation của **Payment server** và provider, không chỉ phía Order. Một key chỉ có tác dụng khi được server xử lý và lưu phù hợp.

## 9. Bối cảnh message broker và tác vụ nền

Một message thường không có người gọi còn ngồi chờ HTTP response. Vì thế cần tách **thời hạn của request người dùng** khỏi **vòng đời nghiệp vụ được xử lý nền**.

Ví dụ Order nhận yêu cầu và trả **202 Accepted + orderId**, sau đó saga tiếp tục:

1. API ghi Order ở trạng thái PENDING cùng bản ghi outbox.
2. Worker phát message yêu cầu giữ hàng.
3. Inventory xử lý và công bố kết quả.
4. Payment xử lý bước tiếp theo.
5. Order cập nhật CONFIRMED hoặc FAILED/CANCELLED theo nghiệp vụ.
6. Người dùng đọc trạng thái qua GET hoặc nhận thông báo.

Một timeout của HTTP ban đầu chỉ giới hạn thời gian **nhận sự xác nhận đã tiếp nhận**; nó không mang nghĩa dừng saga nền. Worker có thể có timeout riêng, retry broker riêng, deadline nghiệp vụ riêng và cơ chế giải quyết trạng thái mắc kẹt.

### Retry message không giống retry HTTP request

Broker thường có cơ chế delivery lại khi consumer không ACK hoặc process chết. Consumer cần:

- Định danh message và thao tác nghiệp vụ để xử lý lặp an toàn.
- Phân biệt lỗi transient với lỗi dữ liệu vĩnh viễn.
- Retry có trì hoãn, số lần thử tối đa và dead-letter queue (DLQ) khi phù hợp.
- Giám sát retry count, tuổi message, số lượng message chờ, thời gian xử lý.
- Cơ chế replay/reconciliation có kiểm soát, tránh tự động tạo side effect lặp.

**Cancellation với job nền** thường cần một command/event mang id của job cùng state machine. Lệnh CancelRequested có thể được xử lý trễ hơn JobCompleted. Worker phải xác định trạng thái hợp lệ; không thể khẳng định hủy chỉ bằng việc phát event.

Một state machine minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: Worker nhận việc
    PENDING --> CANCELLED: Hủy trước khi bắt đầu
    RUNNING --> CANCEL_REQUESTED: Yêu cầu hủy
    RUNNING --> COMPLETED: Xử lý xong
    RUNNING --> FAILED: Lỗi xác định
    CANCEL_REQUESTED --> CANCELLED: Đã dừng an toàn
    CANCEL_REQUESTED --> COMPLETED: Đã qua điểm không thể hủy
    CANCEL_REQUESTED --> FAILED: Lỗi khi xử lý/đối soát
    COMPLETED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
~~~

Sơ đồ chỉ biểu diễn các lựa chọn thường gặp; từng domain phải định nghĩa transaction, transition hợp lệ và phản hồi của lệnh hủy. Với thanh toán, sau **COMPLETED** có thể có luồng **REFUND_REQUESTED/REFUNDED** riêng; không gộp refund vào CANCELLED.

## 10. Quan sát và điều tra: biết đã hết hạn, đã retry và đã hủy thật chưa

Hệ thống cần trả lời ít nhất ba câu: **vì sao phải retry? retry đã gây tác dụng gì? cancellation đã được thực thi đến mức nào?**

Các dấu vết nên mang **correlation/trace ID**, logical operation ID, request attempt number, dependency, deadline/remaining budget, kết quả timeout và trạng thái business. Không ghi secrets, token hoặc dữ liệu thanh toán nhạy cảm vào log.

### Những chỉ số và sự kiện hữu ích

| Tín hiệu | Diễn giải | Cần chú ý |
|---|---|---|
| request latency p50/p95/p99 theo route/dependency | Độ trễ trung bình và đuôi phân phối | p99 tăng có thể báo overload sớm |
| timeout count/rate | Số lần vượt giới hạn chờ | Phân biệt connect, request, queue và overall |
| retry attempts per operation | Mức khuếch đại request | Có đột biến theo dependency không? |
| retry success rate | Retry có thực sự cứu request? | Nếu hầu hết vẫn lỗi, retry có thể đang gây hại |
| retry budget used | Mức chi phí retry so với tải cơ sở | Chặn runaway retry |
| 429/503 và Retry-After | Tín hiệu quá tải của dependency | Có client đang bỏ qua Retry-After không? |
| cancellation requested/observed/acknowledged | Các bước của vòng đời hủy | Requested không bằng hoàn thành |
| pending/unknown business operations | Yêu cầu kết quả chưa xác định | Cần cơ chế đối soát, cảnh báo tồn đọng |
| idempotency replay/conflict | Yêu cầu trùng và xung đột payload | Bảo vệ side effect và phát hiện client lỗi |
| queue age, DLQ count, compensation failures | Tình trạng xử lý nền | Số job mắc kẹt, cần người vận hành xử lý |

Khi thiết kế metric, tránh đặt **orderId, paymentId, customerId** thành label Prometheus vì gây độ phân biệt giá trị rất cao; dùng chúng trong log/trace có kiểm soát. Metric nên tổng hợp theo service, route, error type hoặc dependency, sau đó dùng trace/log để đi vào từng giao dịch.

### Ví dụ chuỗi sự kiện cho một operation

~~~text
operationId=O-101 attempt=1 dependency=payment event=request_started
operationId=O-101 attempt=1 dependency=payment event=client_timeout
operationId=O-101 event=status_unknown action=reconcile
operationId=O-101 event=payment_status_found status=SUCCEEDED
operationId=O-101 event=order_confirmed
~~~

Log này cho thấy client timeout nhưng giao dịch **thành công sau đối soát**. Nếu chỉ nhìn dòng client_timeout rồi tự động hoàn tác Order, hệ thống có thể rơi vào trạng thái sai. Một span trace nên thể hiện parent/child, thời điểm và lỗi; log nghiệp vụ vẫn cần thiết vì trace không thay thế trạng thái lưu trữ.

## 11. Kiểm thử các giới hạn trong thực tế

Dưới đây là những tình huống cần mô phỏng. Mỗi trường hợp phải xác nhận **response**, **trạng thái nghiệp vụ cuối cùng**, **số side effect** và **mức tiêu thụ tài nguyên**.

| Tình huống | Thiết lập | Kỳ vọng |
|---|---|---|
| Connect timeout | Dependency không mở kết nối | Kết thúc theo ngân sách, số retry bị giới hạn |
| Response chậm hơn per-attempt timeout | Server chậm nhưng vẫn chạy | Client timeout; không suy ra server chưa commit |
| Server commit rồi mất response | Chặn response sau khi commit | Retry cùng key không tạo side effect thứ hai |
| 503 tạm thời | Lỗi 1–2 attempts rồi khỏe | Có thể thành công trong deadline với backoff |
| 429 + Retry-After dài | Dependency công bố giới hạn tải | Client không retry dồn dập hoặc vượt overall deadline |
| Lỗi 400/403 | Dữ liệu hoặc quyền sai | Không retry và không che nguyên nhân |
| Retry đồng thời từ nhiều tầng | Client và gateway bật cùng policy | Phát hiện/loại trừ khuếch đại attempts |
| Người dùng cancel trước khi task chạy | Task còn trong queue | Không bắt đầu công việc mới, trạng thái cancel rõ |
| Cancel trong lúc task chạy | Chèn điểm kiểm tra token/interrupt | Task hợp tác dừng, đóng tài nguyên hợp lệ |
| Cancel tới sau khi commit | Delay cancel message | Trả ALREADY_COMPLETED hoặc bắt đầu compensation có chủ đích |
| Lặp event/ACK mất | Broker giao lại message | Consumer không nhân side effect |
| Dependency outage kéo dài | Liên tục timeout/503 | Retry budget, concurrency limit và circuit breaker bảo vệ hệ thống |

### Bài thực hành theo bước

**Bước 1 — Thiết kế hợp đồng.** Xây dựng một endpoint GET /inventory/{sku} và một endpoint POST /payments. Viết rõ các nhóm lỗi, timeout/deadline, điều kiện retry, idempotency key cho POST và API truy vấn trạng thái payment.

**Bước 2 — Thêm lỗi có thể kiểm soát.** Giả lập độ trễ 100/300/700 ms, kết nối thất bại, 503, 429 và response bị mất sau commit. Theo dõi một logical operation ID qua từng attempt.

**Bước 3 — Áp dụng ngân sách.** Cho request người dùng deadline 2 giây. Đảm bảo từng lời gọi và backoff không vượt remaining budget. Đo thời gian thực tế và giải thích sai khác so với cấu hình.

**Bước 4 — Thử tín hiệu hủy.** Cho client cancel khi worker đang chờ hoặc giữa một bước xử lý. So sánh ba trạng thái: client ngừng chờ, worker thực sự ngừng, và trạng thái nghiệp vụ đã commit hay chưa.

**Bước 5 — Đối soát.** Giả lập Payment đã charge nhưng Order nhận timeout. Xác minh logic không charge lại, Order cập nhật đúng sau khi hỏi trạng thái, và có alert nếu giao dịch ở UNKNOWN quá lâu.

**Sản phẩm mong đợi:** sơ đồ sequence thể hiện failure path, bảng timeout và retry policy, code minh họa với ID ổn định, log/trace kết quả, kết quả thử nghiệm cùng một ADR ngắn giải thích các trade-off.

## 12. Những hiểu lầm phổ biến

**Hiểu lầm 1: “Timeout nghĩa là server không làm gì.”**  
Sai. Timeout chủ yếu khẳng định người gọi không có kết quả kịp thời. Server có thể đã commit hoặc tiếp tục chạy.

**Hiểu lầm 2: “Retry sẽ làm request đáng tin cậy hơn trong mọi trường hợp.”**  
Sai. Retry có thể làm trùng side effect và nhân tải khi dependency đang overload. Nó chỉ hữu ích nếu có khả năng phục hồi, thao tác an toàn và policy được giới hạn.

**Hiểu lầm 3: “GET luôn an toàn, POST luôn cấm retry.”**  
Quá đơn giản. GET theo hợp đồng HTTP thường được kỳ vọng an toàn để đọc, nhưng implementation thực tế phải đúng hợp đồng. POST có thể retry an toàn nếu server hỗ trợ idempotency và operation ID ổn định. Phân loại theo **ngữ nghĩa nghiệp vụ**, không theo tên method đơn thuần.

**Hiểu lầm 4: “Có idempotency key ở client là đủ.”**  
Sai. Server phải thực thi uniqueness, xử lý request đang chạy, kiểm tra payload, lưu kết quả và phối hợp với side effect bên ngoài.

**Hiểu lầm 5: “Hủy Future sẽ hủy cả request tới Payment.”**  
Sai. Cancel/interrupt cục bộ không đảm bảo remote request dừng; ngay cả khi remote nhận tín hiệu, commit có thể đã xảy ra.

**Hiểu lầm 6: “Hủy request tương đương rollback.”**  
Sai. Cần biết transaction nào chưa commit, cơ chế rollback của tầng lưu trữ, và những side effect bên ngoài nào cần compensation.

**Hiểu lầm 7: “Mỗi service tự đặt timeout 2 giây là đủ.”**  
Sai. Các lời gọi nối tiếp, queue và backoff có thể khiến thời gian end-to-end vượt xa 2 giây. Cần overall deadline và budget propagation.

**Hiểu lầm 8: “Cứ đặt timeout cực ngắn để fail fast.”**  
Sai. Timeout quá ngắn gây false timeout, tăng retry và có thể khuếch đại tải. Fail fast đúng nghĩa phải dựa trên số đo và chính sách overload.

**Hiểu lầm 9: “Message broker bảo đảm exactly-once payment.”**  
Sai. Cam kết delivery của broker, commit database và side effect của provider là những biên giao dịch khác nhau. Consumer idempotency và đối soát vẫn cần thiết.

**Hiểu lầm 10: “Người dùng bấm Hủy thì UI có thể báo đã hủy thành công ngay.”**  
Không đủ. UI có thể báo **đã tiếp nhận yêu cầu hủy**, rồi cập nhật khi backend xác nhận CANCELLED hoặc trả kết quả TOO_LATE/ALREADY_COMPLETED.

## 13. Câu hỏi ôn tập

1. Tại sao lỗi timeout từ API Payment không chứng minh thanh toán thất bại? Hãy nêu tối thiểu ba trạng thái server có thể đang ở.
2. Connect timeout, response timeout và overall deadline khác nhau ở điểm nào? Cho ví dụ khi một loại timeout không giới hạn được độ trễ end-to-end.
3. Nếu frontend cần kết quả trong 2 giây nhưng Order gọi hai dependency nối tiếp, bạn phân bổ và truyền remaining budget thế nào?
4. Vì sao retry 503 thường có thể cân nhắc, còn retry 400 hoặc 403 y nguyên thường vô ích?
5. Nếu cả client, gateway và Order đều cho phép ba attempts, số attempts xuống dependency sâu nhất có thể tăng như thế nào?
6. Exponential backoff và jitter giải quyết hai vấn đề khác nhau gì? Điều gì xảy ra nếu mọi client retry đúng cùng một nhịp?
7. Khi POST bị timeout sau commit, idempotency key và truy vấn trạng thái có vai trò gì? Điều gì xảy ra khi mỗi retry tạo key mới?
8. Phân biệt **cancel requested**, **cancel acknowledged**, **cancel completed** và **business compensated**.
9. Vì sao gọi Future.cancel(true) không thể dùng làm bằng chứng rằng payment từ xa đã rollback?
10. Một event được giao lại sau khi worker ACK thất bại có thể tạo side effect trùng như thế nào? Consumer phải lưu gì để phát hiện?
11. Khi người dùng hủy ngay sát lúc Payment commit, state machine nào giúp Order tránh báo sai trạng thái?
12. Bạn sẽ xem metrics, trace và trạng thái nghiệp vụ nào để xác định retry đang cứu hệ thống hay đang đẩy hệ thống vào overload?

## 14. Checklist ứng dụng vào một luồng Microservices

Trước khi triển khai timeout/retry/cancellation cho một luồng nghiệp vụ, hãy ghi rõ:

- [ ] **Overall deadline:** Người dùng hoặc nghiệp vụ chấp nhận chờ tổng bao lâu, ai kiểm soát?
- [ ] **Timeout theo tầng:** Connect, request, queue, database và worker timeout đang đo phần nào?
- [ ] **Budget propagation:** Mỗi hop có nhận và tôn trọng remaining budget không?
- [ ] **Retry owner:** Ai được retry, tối đa bao nhiêu attempts, với loại lỗi nào?
- [ ] **Load protection:** Có backoff, jitter, Retry-After, retry budget và giới hạn concurrency không?
- [ ] **Idempotency:** Operation ID ổn định, uniqueness, xử lý trùng đồng thời và dữ liệu trả lại được đảm bảo ra sao?
- [ ] **Unknown outcome:** Timeout sau commit được phát hiện và đối soát thế nào?
- [ ] **Cancellation:** Tín hiệu hủy đi qua những tầng nào, dừng ở đâu, ai xác nhận?
- [ ] **Point of no return:** Khi đã commit, cancellation chuyển thành trạng thái gì hoặc cần compensation nào?
- [ ] **Background tasks:** Request HTTP hết hạn có ảnh hưởng thế nào tới saga/job nền?
- [ ] **Observability:** Có thấy attempts, timeout type, request/deadline ID, cancellation state, side effect và kết quả đối soát không?
- [ ] **Failure testing:** Đã thử timeout sau commit, response mất, 429, 503, cancel sau commit và message trùng chưa?

## 15. Kết nối với các chủ đề Microservices khác

- **Service communication và API contract:** Retry, timeout và cancellation là một phần của hợp đồng giao tiếp; không thể chọn chúng độc lập với REST/gRPC/event.
- **Sở hữu dữ liệu và transaction:** Timeout sau commit tạo trạng thái chưa rõ; idempotency, outbox và transaction boundary giúp bảo vệ bất biến nghiệp vụ.
- **Saga và eventual consistency:** Cancellation giữa các bước saga có thể cần compensation, reconciliation và trạng thái trung gian có thể quan sát.
- **Resilience:** Circuit breaker, bulkhead, rate limit và backpressure giảm tác động của retry khi dependency bất ổn.
- **Observability:** Trace, metric, log và trạng thái nghiệp vụ là bằng chứng để phân biệt lỗi mạng với thành công muộn.
- **Capacity planning và SLO:** Timeout và retry ảnh hưởng trực tiếp đến tail latency, tài nguyên, chi phí và error budget.
- **Security:** Deadline/ID và tín hiệu hủy phải được xác thực và giới hạn; tránh cho khách hàng ngoài hệ thống áp đặt deadline hoặc hủy job của người khác.

**Kết luận:** Timeout giúp **giới hạn chờ**, retry giúp **khôi phục một số lỗi tạm thời**, cancellation giúp **ngừng công việc không còn cần thiết khi hệ thống hỗ trợ**. Cả ba đều có giới hạn trong thế giới phân tán: kết quả có thể không rõ, side effect có thể đã xảy ra, và hủy có thể đến muộn. Kiến trúc đúng là kết hợp **deadline + retry có điều kiện + idempotency + cancellation hợp tác + trạng thái nghiệp vụ + đối soát + quan sát**, rồi kiểm chứng bằng các tình huống lỗi thực tế.