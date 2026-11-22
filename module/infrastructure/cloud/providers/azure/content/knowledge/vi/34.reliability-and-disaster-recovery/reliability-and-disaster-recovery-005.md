# Retry, circuit breaker, timeout và bulkhead trong ứng dụng

Một ứng dụng có thể vẫn chạy bình thường trong khi dịch vụ mà nó gọi gặp lỗi: mạng chập chờn, API phản hồi chậm, cơ sở dữ liệu quá tải hoặc một vùng hạ tầng bị gián đoạn. Nếu mọi request đều chờ vô hạn hoặc liên tục gọi lại dịch vụ đang hỏng, sự cố nhỏ ở một dependency có thể lan thành sự cố toàn hệ thống.

Trong chương **Độ tin cậy và khôi phục thảm họa** của lộ trình **CLOUD_PROVIDERS_AZURE**, chúng ta tập trung vào bốn mẫu thiết kế bảo vệ ứng dụng: **timeout**, **retry**, **circuit breaker** và **bulkhead**. Chúng áp dụng cho ứng dụng Java, .NET, Node.js hoặc các workload khác triển khai trên Azure App Service, Azure Kubernetes Service (AKS), Azure Container Apps và Azure Functions. Kiến thức này bổ sung cho kiến trúc Azure tổng thể, gồm mạng, dịch vụ tính toán, lưu trữ, dữ liệu, giám sát, bảo mật và kiểm soát chi phí.

Mục tiêu không phải làm mọi request luôn thành công bằng mọi giá. Mục tiêu là **đặt giới hạn cho thời gian chờ và tài nguyên sử dụng, phục hồi có kiểm soát khi lỗi tạm thời, đồng thời ngăn sự cố lan rộng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện lỗi tạm thời, lỗi lâu dài, quá tải và lỗi nghiệp vụ trước khi chọn cơ chế xử lý.
2. Thiết kế deadline tổng thể, timeout cho từng lần gọi và retry có backoff, jitter, giới hạn số lần.
3. Giải thích trạng thái **closed → open → half-open** của circuit breaker và cách xác định thời điểm thử phục hồi.
4. Tính và áp dụng giới hạn đồng thời bằng **bulkhead**, tránh một dependency dùng hết thread, connection hoặc bộ nhớ của ứng dụng.
5. Kết hợp bốn cơ chế với nhau và với cơ chế retry có sẵn trong Azure SDK, HTTP gateway hoặc hàng đợi.
6. Cấu hình một ví dụ ứng dụng Java gọi dịch vụ qua HTTP, giám sát bằng Azure Monitor/Application Insights và thiết kế thử nghiệm lỗi.

## 2. Bối cảnh thực tế: một lỗi nhỏ dẫn đến sự cố dây chuyền

Giả sử một API **orders-api** chạy trên Azure Container Apps hoặc AKS. Khi người dùng tạo đơn hàng, API gọi **inventory-api** để kiểm tra tồn kho, **pricing-api** để lấy giá và **payment-api** để xác nhận thanh toán. Inventory API tạm thời chậm từ 100 ms lên 8 giây do pool kết nối cơ sở dữ liệu bị nghẽn.

Nếu orders-api xử lý mỗi request bằng một thread và không đặt timeout:

1. Các request mới tiếp tục gọi inventory-api.
2. Thread bị giữ để chờ; pool HTTP và connection bắt đầu đầy.
3. Những request không liên quan tới inventory cũng không còn tài nguyên để thực hiện.
4. Load balancer có thể vẫn gửi thêm request vì một số health check còn trả về thành công.
5. Autoscale bổ sung instance nhưng các instance mới cũng tiếp tục gây tải lên inventory-api.

Nếu thêm retry không giới hạn, sự cố có thể nặng hơn: 100 request ban đầu, mỗi request gọi lại nhiều lần, có thể tạo thêm hàng trăm yêu cầu lên dependency vốn đã quá tải.

~~~mermaid
flowchart LR
    U["Client"] --> O["orders-api trên Azure"]
    O --> I["inventory-api đang chậm"]
    O --> P["pricing-api"]
    O --> M["payment-api"]
    I --> D["Database connection pool quá tải"]
    D -. "Tăng thời gian phản hồi" .-> I
    I -. "Giữ thread / connection" .-> O
    O -. "Cạn tài nguyên" .-> P
    O -. "Cạn tài nguyên" .-> M
~~~

Bốn mẫu thiết kế giải quyết những điểm khác nhau:

| Mẫu | Câu hỏi cần trả lời | Hành động chính | Rủi ro nếu dùng sai |
| --- | --- | --- | --- |
| **Timeout** | Tôi sẵn sàng đợi dependency bao lâu? | Giới hạn thời gian, trả lỗi hoặc fallback khi quá hạn | Timeout quá ngắn gây lỗi giả; timeout không chắc hủy thao tác phía server |
| **Retry** | Lỗi này có khả năng tự hết nếu thử lại? | Thử lại có giới hạn, chờ giữa các lần thử | Khuếch đại lưu lượng, nhân đôi thao tác có tác dụng phụ |
| **Circuit breaker** | Dependency có đang hỏng đến mức nên tạm ngừng gọi? | Mở mạch khi lỗi vượt ngưỡng; cho phép thử phục hồi có kiểm soát | Ngưỡng kém làm từ chối quá sớm hoặc hồi phục quá chậm |
| **Bulkhead** | Một dependency được phép chiếm tối đa bao nhiêu tài nguyên? | Giới hạn đồng thời hoặc hàng đợi theo nhóm | Giới hạn quá thấp làm nghẽn ngay cả khi dependency khỏe |

Không mẫu nào thay thế được redundancy giữa Availability Zone/region, backup, khôi phục dữ liệu hay chiến lược disaster recovery. Đây là **resilience ở cấp lời gọi và tài nguyên ứng dụng**, hỗ trợ hệ thống ổn định hơn trước lỗi từng phần.

## 3. Phân loại lỗi trước khi quyết định retry

Thử lại chỉ có ích khi xác suất thành công ở lần tiếp theo đủ lớn và chi phí thử lại được kiểm soát.

| Tín hiệu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Timeout / network reset** | Kết nối bị ngắt, phản hồi không đến kịp | Có thể retry với deadline, nhưng phải xét thao tác có tác dụng phụ đã hoàn thành phía server hay chưa |
| **HTTP 429** | Dịch vụ giới hạn tốc độ | Tôn trọng **Retry-After** nếu có, giảm tốc độ gửi và retry trong ngân sách; cần điều chỉnh concurrency/rate limit |
| **HTTP 503 / 502 / 504** | Dịch vụ tạm không sẵn sàng, proxy lỗi, gateway hết hạn | Có thể retry có giới hạn nếu request an toàn |
| **HTTP 500** | Lỗi server, nguyên nhân chưa rõ | Chỉ retry khi đã biết tính chất lỗi và tính an toàn của thao tác; tránh mặc định retry mọi 500 |
| **HTTP 400 / 401 / 403 / 404 / 422** | Dữ liệu sai, chưa đăng nhập, không có quyền, không tìm thấy, lỗi xác thực đầu vào | Thường **không retry** khi request và trạng thái không thay đổi |
| **HTTP 409 / 412** | Xung đột trạng thái, điều kiện phiên bản không đạt | Phân tích logic nghiệp vụ và concurrency; không retry mù |
| **Circuit breaker đang open** | Đã xác định dependency không khỏe | Fail fast hoặc fallback; không tiếp tục retry vào cùng dependency |
| **Bulkhead đã đầy** | Đã chạm mức đồng thời cho phép | Từ chối nhanh, backpressure, hàng đợi hữu hạn hoặc degradation |
| **Lỗi nghiệp vụ vĩnh viễn** | Hết hàng, thẻ bị từ chối, mã sản phẩm không hợp lệ | Trả kết quả nghiệp vụ; không thử lại tự động |

Phân loại trên là **điểm khởi đầu**, không phải quy tắc tuyệt đối cho mọi HTTP API. Hợp đồng của dependency phải xác định mã lỗi nào thực sự có thể phục hồi, mã nào được retry và liệu yêu cầu đã sinh tác dụng phụ hay chưa.

### 3.1. Idempotency quyết định retry có an toàn không

Một thao tác là **idempotent** nếu thực hiện nhiều lần với cùng thông tin không làm thay đổi kết quả nghiệp vụ vượt quá lần đầu. HTTP GET thường được thiết kế an toàn để đọc lại. HTTP PUT có thể idempotent khi cùng cập nhật một trạng thái đích; DELETE thường có tính idempotent về tác dụng cuối dù phản hồi từng lần có thể khác.

Với **POST tạo đơn hàng hoặc thu tiền**, lỗi timeout không chứng minh thao tác đã thất bại. Server có thể đã ghi thành công đơn hàng rồi mất kết nối trước khi gửi phản hồi.

Ví dụ bảo vệ thao tác tạo thanh toán:

~~~http
POST /payments
Idempotency-Key: payment-order-78125-v1
Content-Type: application/json

{"orderId":"78125","amount":250000,"currency":"VND"}
~~~

Server thanh toán phải định nghĩa cách lưu và kiểm tra khóa idempotency, giới hạn thời gian giữ khóa, xử lý request trùng nhưng payload khác, tính nguyên tử khi ghi trạng thái và chính sách hoàn trả kết quả. **Header Idempotency-Key không tự làm cho mọi API idempotent**. Chỉ retry POST khi API đích hỗ trợ rõ ràng hoặc ứng dụng có cơ chế deduplication được kiểm chứng.

## 4. Timeout: giới hạn thời gian chờ, không chỉ chặn request treo

### 4.1. Các loại timeout cần phân biệt

| Lớp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Connection timeout** | Đợi thiết lập kết nối đến host/port | Không thiết lập TCP trong 200 ms |
| **TLS/handshake timeout** | Đợi bắt tay TLS ở client/proxy có hỗ trợ | Kết nối bảo mật không hoàn thành đúng hạn |
| **Read/response timeout** | Đợi dữ liệu từ server hoặc khoảng không nhận dữ liệu, tùy HTTP client | Không có dữ liệu phản hồi trong 450 ms |
| **Per-attempt timeout** | Thời gian tối đa dành cho một lần gọi cụ thể | Một HTTP attempt 500 ms |
| **Overall deadline** | Thời điểm cuối cùng cả request nghiệp vụ phải xong, kể cả retry và fallback | Tổng xử lý tạo đơn hàng 2 giây |
| **Gateway/ingress timeout** | Giới hạn tại Azure Front Door, Application Gateway, API Management hoặc proxy | Gateway có thể đóng kết nối trước backend |

**Read timeout không phải lúc nào cũng là tổng thời gian request.** Có HTTP client áp dụng timeout cho từng lần đọc hoặc thời gian không có dữ liệu, nên server gửi dữ liệu lắt nhắt vẫn có thể kéo dài toàn bộ request. Nếu ứng dụng cần hạn mức tuyệt đối, hãy dùng **deadline tổng thể** hoặc cơ chế request timeout thực sự bao trùm toàn bộ operation.

Lớp ngoài thường quyết định ngân sách tối đa mà lớp trong phải tôn trọng. Nếu client chờ tối đa 2 giây nhưng orders-api mất 3 giây chỉ để gọi inventory, kết quả đó không thể phục vụ client đúng hạn. Timeout của ứng dụng, proxy, load balancer và dependency nên được xem xét cùng nhau; không tự giả định giá trị mặc định của một dịch vụ Azure cố định giữa mọi cấu hình.

### 4.2. Tính ngân sách thời gian từ đầu đến cuối

Ví dụ request cần trả kết quả trong tối đa **2.000 ms**. Dành:

- 250 ms cho kiểm tra dữ liệu, xác thực và serialization.
- 200 ms dự phòng cho scheduling, network và fallback.
- Tối đa 1.550 ms cho các lần gọi inventory và khoảng chờ retry.

Nếu gọi inventory tối đa **3 attempt**, mỗi attempt tối đa **400 ms** và hai lần backoff lần lượt 100 ms, 200 ms, thì tổng lý thuyết là:

\[
3 \times 400 + 100 + 200 = 1.500 \text{ ms}
\]

Chỉ còn khoảng 50 ms trong ngân sách inventory, nên thực tế phải tính cả thời gian kết nối, xử lý nội bộ, biến thiên mạng và overhead. Các số trên **chỉ là ví dụ để học cách lập ngân sách**, không phải cấu hình chuẩn cho mọi workload.

Tốt hơn nữa, ứng dụng nên dùng **deadline thực tế còn lại** ở từng attempt thay vì cấp mới toàn bộ 400 ms mỗi lần:

~~~text
deadline = monotonic_now() + 2_000_ms
...
remaining = deadline - monotonic_now()
attempt_timeout = min(400_ms, remaining - safety_margin)
if attempt_timeout <= 0:
    stop_with_timeout
~~~

Dùng đồng hồ monotonic cho phép tính khoảng thời gian, vì đồng hồ hệ thống có thể được điều chỉnh. Với chuỗi nhiều service, có thể truyền thông tin deadline/budget qua metadata phù hợp, nhưng server nhận phải kiểm tra giới hạn tin cậy và tránh để client bên ngoài yêu cầu thời gian chờ vô hạn.

### 4.3. Timeout không đồng nghĩa tác vụ đã bị hủy

Khi client timeout, thao tác database hoặc request HTTP phía downstream **có thể vẫn đang chạy**. Cancellation signal cũng không bảo đảm server đã rollback giao dịch hoặc ngừng xử lý. Vì thế:

1. Cấu hình timeout/cancel phù hợp ở HTTP client, database driver và upstream.
2. Giữ idempotency cho tác vụ ghi.
3. Dùng correlation ID để theo dõi kết quả cuối cùng.
4. Với thao tác dài, cân nhắc nhận việc bất đồng bộ qua hàng đợi rồi trả **202 Accepted** cùng mã tra cứu thay vì giữ kết nối HTTP.

## 5. Retry: phục hồi lỗi tạm thời mà không gây bão request

### 5.1. Retry có giới hạn

Một policy retry cần khai báo tối thiểu:

- **Max attempts:** tổng số lần gồm attempt đầu tiên, ví dụ 3 attempts = 1 lần gốc + tối đa 2 lần retry.
- **Retryable conditions:** những exception hoặc mã lỗi nào được retry.
- **Backoff:** cách tính thời gian giữa các lần thử.
- **Jitter:** thành phần ngẫu nhiên làm các client không retry đồng loạt.
- **Deadline:** không retry nếu không đủ thời gian hoàn thành hữu ích.
- **Idempotency:** yêu cầu ghi phải an toàn khi thực hiện nhiều lần.
- **Retry budget:** giới hạn tổng lưu lượng retry cho toàn dịch vụ để tránh khuếch đại.

Ví dụ exponential backoff có giới hạn:

\[
d_k = \min(d_{max}, d_0 \times 2^{k-1})
\]

Trong đó \(d_0\) là khoảng chờ ban đầu, \(d_{max}\) là trần, \(k\) là số lần retry. Với **full jitter**, thời gian chờ được chọn ngẫu nhiên trong khoảng từ 0 đến \(d_k\), giúp nhiều instance không đồng loạt gọi lại sau một khoảng cố định.

Giả sử \(d_0 = 100\) ms, \(d_{max} = 2.000\) ms:

| Retry thứ | Backoff trần trước jitter |
| --- | --- |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |

Số lần retry thực tế phải được giới hạn độc lập; **bảng không hàm ý ứng dụng cần retry tới 5 lần**. Nhiều API tương tác yêu cầu deadline thấp chỉ có thể chấp nhận 0–2 lần retry.

### 5.2. HTTP 429, Retry-After và backpressure

Khi nhận **429 Too Many Requests**, server có thể gửi **Retry-After** dưới dạng số giây hoặc ngày HTTP. Client cần phân tích chính xác, tôn trọng ngân sách request và áp dụng ngưỡng chờ tối đa. Nếu thời gian server yêu cầu chờ lớn hơn deadline của người dùng, hãy trả tín hiệu quá tải hoặc xử lý bất đồng bộ; không giữ request tới khi hết hạn một cách vô ích.

Retry **không thay thế rate limiting**. Nếu lưu lượng nền liên tục vượt capacity, cần giảm tốc độ phát request, giới hạn concurrency, scale phù hợp, tối ưu truy vấn hoặc cải thiện capacity downstream.

~~~mermaid
flowchart TD
    A["Gọi dependency"] --> B{"Kết quả?"}
    B -->|"Thành công"| C["Trả kết quả"]
    B -->|"Lỗi không retryable"| D["Trả lỗi / fallback"]
    B -->|"429, 503, timeout có thể retry"| E{"Idempotent và còn deadline/budget?"}
    E -->|"Không"| D
    E -->|"Có"| F["Backoff + jitter; xét Retry-After"]
    F --> G{"Đủ ngân sách thử tiếp?"}
    G -->|"Không"| D
    G -->|"Có"| A
~~~

### 5.3. Tránh retry lồng nhiều tầng

Một hệ thống có thể có retry ở:

- Mobile/web client.
- Azure API Management hoặc gateway.
- Ứng dụng orders-api.
- Azure SDK / HTTP client.
- Database driver hoặc message consumer.

Nếu ba lớp độc lập đều gọi tối đa ba lần, một yêu cầu gốc có thể sinh tới **3 × 3 × 3 = 27** attempt ở dependency xa nhất trong trường hợp xấu. Cần xác định **tầng sở hữu retry**, dùng tổng deadline và quan sát số attempt thật. Đừng thêm policy retry chỉ vì SDK hoặc thư viện hỗ trợ.

## 6. Circuit breaker: ngắt sớm những lời gọi có xác suất lỗi cao

### 6.1. Ba trạng thái cơ bản

**CLOSED:** cho phép request đi qua và ghi nhận kết quả. Nếu tỷ lệ lỗi hoặc tỷ lệ gọi chậm vượt ngưỡng đã cấu hình sau khi đủ số mẫu, breaker chuyển sang OPEN.

**OPEN:** từ chối lời gọi ngay để bảo vệ cả caller và dependency. Ứng dụng trả fallback hoặc lỗi có kiểm soát. Hết khoảng chờ cấu hình, breaker được phép chuyển sang HALF_OPEN.

**HALF_OPEN:** chỉ cho một số lời gọi thăm dò. Nếu kết quả cho thấy dependency hồi phục, chuyển CLOSED; nếu vẫn vượt ngưỡng lỗi, quay OPEN.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Tỷ lệ lỗi/chậm vượt ngưỡng sau đủ mẫu
    OPEN --> HALF_OPEN: Hết thời gian mở mạch
    HALF_OPEN --> CLOSED: Thăm dò đạt điều kiện phục hồi
    HALF_OPEN --> OPEN: Thăm dò thất bại
~~~

Một số thư viện còn có trạng thái bổ sung như **DISABLED**, **FORCED_OPEN** hoặc **METRICS_ONLY** phục vụ vận hành và kiểm thử. Không nên xem việc breaker OPEN đồng nghĩa service đã sập hoàn toàn; đôi khi nó phản ánh latency tăng vượt chính sách hoặc ngưỡng được đặt quá nhạy.

### 6.2. Chọn ngưỡng có ý nghĩa

Ví dụ cấu hình ban đầu cho inventory-api:

| Tham số | Giá trị minh họa | Mục đích |
| --- | --- | --- |
| Sliding window | 20 cuộc gọi gần nhất | Theo dõi tình trạng gần đây |
| Minimum number of calls | 10 | Tránh quyết định dựa trên quá ít mẫu |
| Failure rate threshold | 50% | Mở mạch khi nhiều lời gọi thất bại |
| Slow-call duration | 400 ms | Định nghĩa một lời gọi chậm |
| Slow-call rate threshold | 70% | Có thể mở mạch dù chưa có nhiều lỗi HTTP |
| Wait duration in open state | 30 giây | Giảm tải trước khi kiểm tra lại |
| Permitted half-open calls | 3 | Giới hạn thăm dò |

Những con số này phải được điều chỉnh theo **SLO, lưu lượng, loại dependency, cửa sổ quan sát và khả năng phục hồi**. Một service chỉ có 2 request/phút không phù hợp với cấu hình phải đợi 10 sample rồi mới ra quyết định. Một service 10.000 request/giây có thể cần cửa sổ theo thời gian và cách phân nhóm khác.

**Phân loại exception rất quan trọng.** HTTP 400 do client gửi sai dữ liệu không nên làm breaker đánh giá dependency hỏng. Ngược lại, timeout, network error và 503 thường là tín hiệu có giá trị. Với 429, cần cân nhắc đây là quá tải/rate limit có chính sách riêng, không tự động xem tất cả 429 như sự cố hệ thống.

### 6.3. Fallback khi circuit breaker mở

Một fallback hợp lý phụ thuộc nghiệp vụ:

| Lời gọi | Fallback có thể chấp nhận | Fallback nguy hiểm |
| --- | --- | --- |
| Lấy gợi ý sản phẩm | Trả danh sách cache và gắn dữ liệu có thể cũ | Báo chắc chắn giá/tồn kho mới nhất |
| Lấy thông tin ít quan trọng | Bỏ phần phụ hoặc trả placeholder | Giả định thành công toàn bộ nghiệp vụ |
| Kiểm tra tồn kho trước đặt hàng | Tạm dừng nhận đơn hoặc đặt đơn ở trạng thái chờ xác minh | Khẳng định còn hàng khi chưa có bằng chứng |
| Thu tiền | Trả trạng thái đang xử lý và đối soát theo idempotency key | Tự coi thanh toán thành công hoặc gọi thêm không kiểm soát |

Fallback **không được làm sai tính đúng đắn nghiệp vụ**. Một API bán hàng có thể degrade phần gợi ý, nhưng quyết định đã trừ tiền hoặc đã giữ hàng thường đòi hỏi xác nhận thật.

## 7. Bulkhead: cô lập sức chứa của các dependency

Thuật ngữ **bulkhead** lấy từ các khoang kín trên tàu: một khoang bị nước tràn không làm chìm cả tàu. Trong ứng dụng, mỗi nhóm lời gọi quan trọng có một **phần tài nguyên được giới hạn**.

Hai cách phổ biến:

1. **Semaphore bulkhead:** chỉ cho tối đa N lời gọi đồng thời. Khi đủ N, từ chối hoặc chờ rất ngắn. Phù hợp I/O bất đồng bộ hoặc HTTP call mà không cần tạo thread pool riêng.
2. **Thread-pool bulkhead:** có thread pool và hàng đợi hữu hạn dành cho một nhóm tác vụ đồng bộ. Tăng khả năng cô lập nhưng thêm chi phí thread, queue, scheduling và nguy cơ queue quá dài.

Ví dụ orders-api có 80 worker thread. Nếu 80 thread đều chờ inventory, pricing và endpoint health không còn thread xử lý. Giới hạn **inventory tối đa 20 lời gọi đồng thời trên mỗi instance** có thể chừa tài nguyên cho các endpoint khác, miễn sao thiết kế thread pool/HTTP pool thực sự tương thích.

~~~mermaid
flowchart LR
    R["Requests vào orders-api"] --> B{"Inventory bulkhead còn slot?"}
    B -->|"Có"| I["Tối đa N lời gọi inventory"]
    B -->|"Hết slot"| F["Từ chối nhanh / backpressure"]
    R --> P["Pricing dùng bulkhead riêng"]
    R --> H["Endpoint quan trọng dùng tài nguyên riêng"]
~~~

### 7.1. Ước lượng mức đồng thời bằng Little's Law

Với lưu lượng ổn định, quan hệ gần đúng:

\[
L = \lambda \times W
\]

Trong đó \(L\) là số tác vụ đồng thời trung bình, \(\lambda\) là số request/giây và \(W\) là thời gian xử lý trung bình tính bằng giây.

Nếu một instance gửi **50 request/giây** tới inventory và mỗi cuộc gọi mất trung bình **0,2 giây**, mức đồng thời trung bình khoảng:

\[
50 \times 0{,}2 = 10
\]

Có thể thử giới hạn ban đầu khoảng 15–20 concurrent calls, sau đó đo p95/p99, queue và tỷ lệ bị từ chối. Đây chỉ là ví dụ tính toán: lưu lượng burst, tail latency, CPU, số connection và tải giữa các replica có thể làm mức giới hạn cần thay đổi. Nếu có 5 replica, mỗi replica cho 20 concurrent calls thì tổng tiềm năng lên tới **100 lời gọi đồng thời**, nên phải xét capacity thực của dependency.

### 7.2. Hàng đợi cũng là tài nguyên

Queue dài có thể biến lỗi quá tải thành chờ lâu rồi timeout. Hãy đặt:

- Số concurrent calls tối đa.
- Queue capacity tối đa nếu dùng thread pool/queue.
- Thời gian chờ lấy slot rất ngắn hoặc bằng 0 cho API yêu cầu phản hồi nhanh.
- Phản hồi khi từ chối, ví dụ HTTP 503/429 theo hợp đồng API, cùng dấu hiệu backpressure.
- Cảnh báo khi tỷ lệ từ chối slot tăng.

Một bulkhead cho từng dependency sẽ có ích hơn một giới hạn chung nếu inventory và pricing có đặc tính khác nhau. Tuy nhiên bulkhead không cứu được ứng dụng nếu tất cả lời gọi vẫn dùng chung thread pool nhỏ và có những thao tác chặn không kiểm soát ở ngoài vùng cô lập.

## 8. Phối hợp timeout, retry, circuit breaker và bulkhead

Thứ tự kiểm soát có ảnh hưởng đến số lần thử, thời gian chờ và cách thống kê lỗi. Một mô hình khái niệm dễ suy luận:

1. Khi request tới, tạo **overall deadline**.
2. Kiểm tra giới hạn **bulkhead** cho toàn bộ hoạt động gọi dependency.
3. Với mỗi attempt, hỏi **circuit breaker** có cho phép gọi không.
4. Nếu được phép, gửi lời gọi với **per-attempt timeout** nhỏ hơn thời gian còn lại.
5. Ghi kết quả attempt vào circuit breaker theo chính sách phân loại lỗi.
6. Nếu lỗi retryable, còn ngân sách và breaker vẫn cho phép, thực hiện **backoff + jitter** rồi thử lại.
7. Trả kết quả hoặc fallback; **nhả bulkhead trong mọi trường hợp**.

~~~mermaid
flowchart TD
    A["Request + overall deadline"] --> B{"Bulkhead còn slot?"}
    B -->|"Không"| X["Trả overload / fallback an toàn"]
    B -->|"Có"| C{"Còn deadline và retry budget?"}
    C -->|"Không"| Z["Trả lỗi / fallback"]
    C -->|"Có"| D{"Circuit breaker cho phép?"}
    D -->|"Không, OPEN"| Z
    D -->|"Có"| E["Gọi dependency với attempt timeout"]
    E -->|"Thành công"| S["Trả kết quả"]
    E -->|"Lỗi"| F{"Lỗi retryable và idempotent?"}
    F -->|"Không"| Z
    F -->|"Có"| G["Backoff + jitter, giới hạn bởi deadline"]
    G --> C
    S --> H["Nhả bulkhead"]
    Z --> H
~~~

Trong mô hình này, bulkhead **có thể giữ slot cả khi chờ backoff** vì slot bao quanh cả hoạt động logic. Cách đó đơn giản để giới hạn số request đang chờ hoàn tất nhưng có thể lãng phí slot trong thời gian ngủ. Một thiết kế khác chỉ giữ slot trong từng attempt, nhả slot trước backoff và lấy lại slot trước attempt tiếp theo. Lựa chọn cần dựa vào yêu cầu về bảo vệ concurrency và đo lường, không được quên giới hạn số request logic đang chờ.

**Điểm dễ nhầm với framework:** thứ tự thực tế của các decorator hoặc annotation như **@Retry**, **@CircuitBreaker**, **@Bulkhead**, **@TimeLimiter** phụ thuộc cấu hình AOP/decorator. Nếu circuit breaker nằm ngoài retry, nó có thể ghi nhận **một operation cuối cùng**; nếu ở trong retry, nó có thể ghi nhận **từng attempt**. Điều này thay đổi failure rate, time spent và ngưỡng mở mạch. Cần kiểm tra thứ tự đã cấu hình và chạy thử lỗi có kiểm soát.

### 8.1. Các tỷ lệ cần suy nghĩ

- **Retry amplification:** số attempt downstream / số yêu cầu logic upstream.
- **Failure rate:** lỗi được policy đánh giá / số cuộc gọi được đo.
- **Slow-call rate:** số cuộc gọi vượt ngưỡng chậm / số cuộc gọi được đo.
- **Bulkhead utilization:** slot đang dùng / tổng slot.
- **Time budget exhaustion:** tỷ lệ request kết thúc vì không còn deadline.

Một hệ thống có success rate cao sau retry vẫn có thể không ổn định nếu p99 tăng mạnh, dependency bị quá tải và retry amplification quá lớn.

## 9. Ví dụ Java: HTTP timeout + Resilience4j

Phần này minh họa trên **Spring Boot có Spring Framework 6.1+** (ví dụ Spring Boot 3.2+) với thư viện **Resilience4j** tương thích. Các API/phiên bản thực tế cần đối chiếu theo bộ dependency của dự án. Mục tiêu là hiểu điểm đặt chính sách và giới hạn, không yêu cầu có sẵn project hay service Azure trong bài học.

### 9.1. Dependencies

Một ứng dụng Spring MVC có thể khai báo dependencies tương ứng:

~~~text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-aop
org.springframework.boot:spring-boot-starter-actuator
io.github.resilience4j:resilience4j-spring-boot3:<compatible-version>
io.github.resilience4j:resilience4j-micrometer:<compatible-version>
~~~

Đây là **tọa độ thư viện minh họa**, không phải file Gradle/POM hoàn chỉnh. Phải chọn phiên bản Resilience4j tương thích Spring Boot/JDK được sử dụng. Đối với ứng dụng WebFlux và CompletionStage, cần cấu hình tích hợp reactive/async phù hợp; **@TimeLimiter** không tự áp đặt hard deadline cho mọi phương thức trả về đồng bộ.

### 9.2. HTTP client có connection và read timeout

~~~java
package example.orders;

import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.HttpClientErrorException;
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;

@Component
public class InventoryGateway {
    private final RestClient http;

    public InventoryGateway(RestClient.Builder builder) {
        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(200); // milliseconds
        requestFactory.setReadTimeout(450);    // milliseconds
        this.http = builder
            .baseUrl("https://inventory.internal.example")
            .requestFactory(requestFactory)
            .build();
    }

    @Bulkhead(name = "inventory", type = Bulkhead.Type.SEMAPHORE)
    @CircuitBreaker(name = "inventory")
    @Retry(name = "inventory")
    public InventoryResult checkStock(String sku) {
        return http.get()
            .uri("/v1/stock/{sku}", sku)
            .retrieve()
            .body(InventoryResult.class);
    }
}
~~~

Trong ví dụ, **InventoryResult** là DTO của ứng dụng, chẳng hạn:

~~~java
package example.orders;

public record InventoryResult(String sku, boolean available, int quantity) {}
~~~

Địa chỉ **inventory.internal.example** chỉ là placeholder và phải thay bằng endpoint thực, có TLS/chứng thực phù hợp. Mặc dù có kết nối tối đa 200 ms và thời gian chờ đọc 450 ms, hai giá trị này **không đảm bảo hard end-to-end timeout 650 ms**. Đặc biệt, hãy bổ sung deadline ở service orchestration/API gateway và kiểm tra hành vi của HTTP client khi nhận response theo nhiều chunk.

Các annotation Resilience4j thường được áp dụng qua Spring AOP proxy. **Gọi checkStock từ phương thức khác trong cùng đối tượng (self-invocation) có thể bỏ qua proxy và làm policy không chạy**. Gọi qua bean được Spring quản lý và kiểm tra hành vi bằng test thực tế.

### 9.3. Cấu hình retry, circuit breaker, bulkhead

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 150ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 400ms
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 3
        recordExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
~~~

**Giới hạn của cấu hình minh họa:**

- **maxAttempts: 3** bao gồm lần đầu và tối đa hai retry. **waitDuration + exponential backoff** trong đoạn này chưa có jitter; ở production cần bổ sung cơ chế randomization đúng API của thư viện hoặc retry policy tự xây dựng/được hỗ trợ.
- Các exception phía **4xx** bị loại khỏi retry và circuit breaker. **HTTP 429** thường cũng bị RestClient ánh xạ thành lỗi 4xx; muốn retry 429 theo Retry-After, cần handler/predicate riêng. Không cấu hình mặc định retry toàn bộ 4xx.
- Các exception khác, bao gồm lỗi từ bulkhead/circuit breaker, cần được phân loại rõ để **không retry khi mạch đã mở hoặc bulkhead đã đầy**.
- **ResourceAccessException** có thể bao gồm lỗi kết nối/đọc; không tự suy luận mọi lỗi I/O đều luôn retryable cho thao tác ghi.
- **@TimeLimiter** dành cho phương thức async/CompletionStage hoặc reactive theo tích hợp tương ứng. Ví dụ đồng bộ trên chỉ cấu hình timeout HTTP client, và cần có **overall deadline** ở orchestration.
- Chỉ số lỗi của circuit breaker phụ thuộc thứ tự AOP thực tế; kiểm tra trong môi trường chạy trước khi chọn threshold.

### 9.4. Fallback tách khỏi giao tiếp downstream

Service nghiệp vụ quyết định cách degrade khi InventoryGateway không trả kết quả. Thay vì tự cho rằng còn hàng, có thể trả trạng thái cần xác minh:

~~~java
package example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderAvailabilityService {
    private final InventoryGateway inventoryGateway;

    public OrderAvailabilityService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    public AvailabilityStatus lookup(String sku) {
        try {
            var result = inventoryGateway.checkStock(sku);
            return result.available()
                ? AvailabilityStatus.AVAILABLE
                : AvailabilityStatus.OUT_OF_STOCK;
        } catch (RuntimeException failure) {
            // Log lỗi ở nơi tập trung, không ghi thông tin nhạy cảm.
            // Phân loại lỗi cụ thể để quyết định HTTP response phù hợp.
            return AvailabilityStatus.UNKNOWN_TEMPORARILY;
        }
    }

    public enum AvailabilityStatus {
        AVAILABLE, OUT_OF_STOCK, UNKNOWN_TEMPORARILY
    }
}
~~~

Đoạn code minh họa **fallback an toàn về nghiệp vụ**, chưa phải endpoint production hoàn chỉnh. Thực tế nên bắt những nhóm exception đã phân loại thay vì mọi RuntimeException, bảo đảm lỗi lập trình không bị che giấu. Nếu không xác minh được tồn kho, luồng đặt đơn cần ở trạng thái chờ kiểm tra hoặc trả lỗi có kiểm soát; không tự chuyển **UNKNOWN_TEMPORARILY** thành **AVAILABLE**.

### 9.5. Kết hợp timeout cứng hơn cho async

Với API bất đồng bộ, có thể dùng **CompletionStage + TimeLimiter** hoặc Reactor **timeout(Duration)** theo kiểu trả về của framework. Timeout chủ động ở async layer giúp kết thúc chờ từ phía caller, nhưng cần xác nhận việc cancellation có thực sự dừng tác vụ I/O hay không. Với Spring WebFlux, ví dụ ý tưởng:

~~~java
Mono<InventoryResult> result = inventoryWebClient.get()
    .uri("/v1/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(InventoryResult.class)
    .timeout(Duration.ofMillis(450));
~~~

Đoạn trên cần **inventoryWebClient** được cấu hình riêng và import Reactor/WebClient tương ứng. Nó minh họa timeout của một reactive publisher; nếu thêm **retryWhen**, cần kiểm tra vị trí toán tử **timeout** so với **retryWhen** để biết timeout áp dụng cho từng attempt hay toàn bộ chuỗi. Deadline tổng thể vẫn là giới hạn độc lập.

## 10. Trên Azure: policy nào đã có sẵn, policy nào phải tự thêm?

Mỗi lớp hạ tầng có thể đã tự xử lý một phần lỗi tạm thời. Trước khi thêm retry ở ứng dụng, cần kiểm tra cơ chế sẵn có:

| Thành phần Azure | Cơ chế liên quan | Việc ứng dụng vẫn phải làm |
| --- | --- | --- |
| **Azure Storage SDK** | Thường có retry policy cho lỗi tạm thời theo cấu hình SDK | Chọn deadline, idempotency, retry budget; tránh retry lồng |
| **Azure Cosmos DB SDK** | Xử lý throttling, mã 429 và thông tin chờ theo SDK | Đo RU/s, độ trễ, request charge; tối ưu partition và capacity |
| **Azure Service Bus SDK** | Có retry cho thao tác dịch vụ; message processing có cơ chế giao lại | Thiết kế consumer idempotent, lock duration, max delivery count, dead-letter |
| **Azure Functions** | Một số trigger có khả năng retry theo host/trigger và cách xử lý lỗi | Xác minh trigger cụ thể, số lần retry, hành vi message/poison handling |
| **Azure API Management** | Có các policy như retry, timeout/forward-request theo cấu hình | Xác định tầng sở hữu retry, giới hạn toàn hệ thống, tránh gọi lại thao tác ghi |
| **Azure Front Door / Application Gateway** | Có timeout, routing, health probe tùy cấu hình | Bảo đảm application deadline phù hợp và có kế hoạch degrade |
| **AKS / Container Apps / App Service** | Có scale và kiểm tra sức khỏe theo cách triển khai | Không coi scale hoặc health probe là thay thế cho retry/breaker/bulkhead |

Đây là **bức tranh nguyên tắc**, không khẳng định mọi phiên bản SDK hay gói dịch vụ có cùng retry count, timeout mặc định hoặc policy. Khi thực hành, kiểm tra phiên bản SDK, cấu hình instance/namespace và tài liệu của chính dịch vụ đang dùng.

### 10.1. Azure Cosmos DB: retry phải đi cùng capacity

Nếu Cosmos DB trả 429 vì request units (RU/s) không đủ, SDK có thể chờ và thử lại. Nếu caller lại có một policy retry bên ngoài, tổng thời gian có thể tăng vượt SLA của người dùng. Cách cải thiện không chỉ là tăng số retry, mà còn xem:

- Partition key và phân bổ RU theo partition.
- Query quá đắt hoặc truy cập hot partition.
- Autoscale throughput, RU/s provisioned và chi phí.
- Retry-after, độ trễ tổng và khả năng từ chối nhanh khi hết deadline.

Thử lại một thao tác đọc thường khác thử lại thao tác ghi có điều kiện (ETag) hoặc stored procedure; phải xét semantics nghiệp vụ và SDK.

### 10.2. Azure Service Bus: at-least-once và dead-letter

Một consumer nhận message ở chế độ **Peek-Lock** có thể xử lý thành công tác vụ nhưng bị gián đoạn trước khi hoàn tất **Complete**. Khi lock hết hạn hoặc message bị abandon, message có thể được giao lại. Đây là hành vi **at-least-once**, nên consumer phải idempotent và lưu dấu đã xử lý nếu nghiệp vụ yêu cầu.

Quy trình tham khảo:

~~~mermaid
flowchart TD
    A["Service Bus nhận message"] --> B["Consumer kiểm tra deduplication"]
    B --> C{"Đã xử lý thành công?"}
    C -->|"Có"| D["Complete message, không thực hiện lại tác vụ"]
    C -->|"Chưa"| E["Xử lý với deadline và giới hạn concurrency"]
    E -->|"Thành công"| F["Lưu kết quả bền vững + Complete"]
    E -->|"Lỗi tạm thời"| G["Thử lại có kiểm soát / chờ giao lại"]
    E -->|"Poison message"| H["Dead-letter + cảnh báo"]
~~~

Xử lý trạng thái nghiệp vụ và complete message thường không nằm trong một transaction xuyên mọi hệ thống, vì vậy phải thiết kế deduplication và recovery rõ ràng. **MaxDeliveryCount**, dead-letter queue (DLQ), lock duration và auto lock renewal là cơ chế vận hành quan trọng; một vòng retry trong process không được kéo dài vô hạn và làm lock hết hạn. Nếu message luôn không xử lý được, hãy đưa vào DLQ cùng lý do phù hợp để điều tra và phát lại sau khi sửa lỗi.

### 10.3. Circuit breaker theo replica

Với AKS/Container Apps có nhiều replica, Resilience4j circuit breaker và semaphore bulkhead **thường lưu trạng thái cục bộ trong từng process**. Khi một replica mở mạch, replica khác có thể vẫn gửi request. Đây là đặc tính cần tính tới khi:

- Đánh giá tổng concurrency xuống dependency.
- Tính tỷ lệ request được phép thăm dò trong half-open.
- Scale số replica và số request đồng thời thực tế.
- Phân tích vì sao một phần request thành công còn phần khác bị từ chối.

Không tự xem breaker cục bộ như công tắc đóng/ngắt toàn vùng. Nếu cần giới hạn toàn hệ thống, cân nhắc rate limiter/distributed admission control phù hợp, đồng thời bảo đảm hệ thống điều phối đó không tạo điểm lỗi mới.

## 11. Thiết kế SLO và quan sát bằng Azure Monitor

Các mẫu resilience là cơ chế vận hành có thể đo được, không chỉ là annotation trong code. Tối thiểu cần giám sát:

| Nhóm chỉ số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Latency** | p50, p95, p99 end-to-end và theo dependency | Phân biệt cải thiện trung bình với tail latency xấu đi |
| **Success/error** | Tỷ lệ 2xx, 4xx, 5xx; timeout; lỗi mạng | Biết loại thất bại và xu hướng |
| **Retry** | Total attempts, retry count, retry amplification | Phát hiện retry storm |
| **Circuit breaker** | State transitions, open duration, calls not permitted | Đánh giá dependency có thực sự đang hỏng |
| **Bulkhead** | Available slots, rejected calls, queued/active tasks | Phát hiện nghẽn và nguy cơ cạn tài nguyên |
| **Dependency health** | Connection pool, database latency, RU/throttling | Xử lý nguyên nhân gốc |
| **Business** | Tỷ lệ tạo đơn thành công, đơn pending, duplicate payment | Tránh fallback làm sai số liệu nghiệp vụ |

Với **Azure Monitor/Application Insights**, có thể kết hợp trace, dependency telemetry và custom metrics từ ứng dụng. OpenTelemetry hỗ trợ truyền trace context qua các service, giúp nhận diện một user request đã tạo bao nhiêu HTTP attempts. Bảo đảm không đưa token, mật khẩu, payload nhạy cảm hoặc toàn bộ URL chứa thông tin riêng tư vào telemetry.

Ví dụ truy vấn **Kusto Query Language (KQL)** trên các bảng Application Insights kiểu cổ điển:

~~~kusto
dependencies
| where timestamp >= ago(30m)
| summarize
    calls = count(),
    failures = countif(success == false),
    p95Ms = percentile(duration / 1ms, 95)
  by target, type
| order by failures desc
~~~

Một số hệ thống Application Insights dạng workspace-based sử dụng tên bảng/cột khác, ví dụ **AppDependencies**, **TimeGenerated**, **DurationMs**. Khi triển khai, hãy chỉnh tên bảng và cột theo Log Analytics workspace thực tế; query trên là mẫu về cách phân tích **failure và p95 dependency latency**, không bảo đảm chạy nguyên trạng trên mọi workspace.

### 11.1. SLI, SLO và alert hợp lý

Giả sử SLO của **orders-api** là **99,9% request hợp lệ trả kết quả trong 2 giây** trong khoảng thời gian đo đã định nghĩa. Khi service dùng retry để tăng success rate, vẫn phải đo yêu cầu kết thúc quá 2 giây là vi phạm latency SLO.

Không nên alert production chỉ vì breaker chuyển OPEN một lần trong vài giây: có thể đó chính là hành vi bảo vệ mong muốn. Thay vào đó, xem **tỷ lệ lỗi cuối cùng, thời gian OPEN kéo dài, lượng request bị từ chối, retry amplification, dependency latency và error budget burn**.

Các dashboard nên phân biệt **lỗi trước retry** và **kết quả sau retry**. Nếu chỉ báo cuối cùng thành công, tổ chức có thể bỏ qua dấu hiệu dependency đang suy giảm nghiêm trọng.

## 12. Điều chỉnh policy bằng số liệu, không đoán mò

Một cách thẩm định cấu hình:

1. **Đo baseline:** RPS, concurrency, p50/p95/p99, timeout, 429/503, connection pool và CPU/memory.
2. **Đặt business deadline:** phù hợp với thời gian phản hồi người dùng và gateway.
3. **Chia ngân sách:** latency của các bước nối tiếp hoặc song song, thời gian chờ retry, fallback.
4. **Chọn retry conditions:** chỉ những lỗi transient và thao tác an toàn; xác minh tầng SDK đã retry.
5. **Chọn bulkhead:** dựa trên throughput, latency và capacity của downstream; tính cả số replica.
6. **Chọn breaker:** đủ mẫu quan sát, ngưỡng lỗi/chậm và thời gian thăm dò phù hợp.
7. **Thử lỗi:** mô phỏng chậm, 503, 429, network reset, overload; kiểm tra tác động đến service khác.
8. **Theo dõi sau rollout:** kiểm tra mục tiêu latency, tỷ lệ từ chối, chi phí và điều chỉnh từng tham số.

Ví dụ một workload có **200 request/giây** ở 4 replica. Mỗi replica nhận trung bình 50 request/giây. Nếu gọi inventory trung bình 200 ms và chỉ 70% request cần inventory, mức concurrency bình quân riêng inventory mỗi replica xấp xỉ:

\[
50 \times 0{,}7 \times 0{,}2 = 7
\]

Con số 7 chưa phản ánh burst và tail latency. Bulkhead ban đầu 12–16 slot/replica có thể là một giả thuyết cần load test, không phải công thức lấy số luôn đúng. Với 4 replica, đỉnh đồng thời có thể 48–64 calls. Nếu capacity inventory chỉ chịu 30 concurrent calls, cấu hình này cần hạ giới hạn, thêm admission control hoặc tăng capacity trước khi mở rộng caller.

**Không tăng retry count để che việc capacity thiếu lâu dài.** Một kế hoạch đúng có thể bao gồm rate limiting, queue async, cache có TTL hợp lý, giảm fan-out, tối ưu truy vấn hoặc mở rộng dependency.

## 13. Thực hành: thiết kế và kiểm thử khả năng chống lỗi

**Bối cảnh:** orders-api trên Azure App Service/AKS/Container Apps gọi inventory-api qua HTTP GET. Bình thường inventory mất 120 ms. Khi sự cố, 30% request gặp HTTP 503, 20% request kéo dài hơn 2 giây. Nhu cầu: phản hồi người dùng trong 2 giây, không làm ngập inventory, vẫn phục vụ phần chức năng không phụ thuộc tồn kho.

### Bước 1 — Xác định hợp đồng nghiệp vụ

Viết rõ:

- GET tồn kho có an toàn để retry hay không; dữ liệu cache được phép cũ bao lâu.
- Nếu inventory không xác nhận được, đơn hàng phải bị chặn, chuyển trạng thái pending hay được xử lý async.
- Những request nào có thể trả HTTP 503/429 cho client và những request nào cần 202 Accepted.
- Tỷ lệ và thời gian chờ tối đa chấp nhận được cho người dùng.

**Kết quả cần có:** bảng quy tắc phân loại lỗi và fallback, không chỉ một danh sách mã HTTP.

### Bước 2 — Đặt cấu hình thử nghiệm

Tham số mẫu để bắt đầu đo, có thể thay đổi theo hệ thống:

| Cơ chế | Giá trị ban đầu |
| --- | --- |
| Overall deadline | 2.000 ms |
| Connection timeout | 200 ms |
| Per-attempt response timeout | 450 ms |
| Retry | Max 3 attempts, exponential backoff 150/300 ms và jitter |
| Circuit breaker | Window 20, min 10 calls, failure threshold 50%, open 30 giây |
| Bulkhead | 20 concurrent calls/replica, không queue |
| Fallback | UNKNOWN_TEMPORARILY, không coi hàng có sẵn |

**Lưu ý:** timeout HTTP client ở ví dụ Java không tự tạo hard deadline 450 ms; cần thêm cơ chế timeout theo request thực và overall deadline ở service.

### Bước 3 — Mô phỏng lỗi có kiểm soát

Thực hiện trong môi trường test được phép, với dữ liệu không nhạy cảm:

1. **Baseline:** inventory khỏe, đo p95/p99, RPS, CPU, active concurrency và success rate.
2. **Delay:** thêm độ trễ lớn hơn per-attempt timeout, kiểm tra request không treo vô hạn.
3. **503:** tạo lỗi tạm thời, xác minh retry count bị giới hạn và có backoff/jitter.
4. **429:** trả Retry-After, xem client có tôn trọng và không vượt overall deadline hay không.
5. **Burst:** tăng đột ngột concurrency, xác minh bulkhead từ chối có kiểm soát và các endpoint khác vẫn trả lời.
6. **Sustained failure:** tạo lỗi kéo dài, xác minh breaker OPEN và giảm số attempt downstream.
7. **Recovery:** phục hồi inventory, kiểm tra HALF_OPEN, các probe và thời điểm quay CLOSED.
8. **Duplicate operation:** thử trên API ghi có idempotency key để bảo đảm retry không tạo đơn/thanh toán trùng.

Có thể dùng công cụ giả lập HTTP failure, network proxy test, hoặc cơ chế fault injection phù hợp với môi trường của nhóm. **Không thử nghiệm chaos trên production** khi chưa có phạm vi, guardrail, thời điểm và quy trình vận hành được phê duyệt.

### Bước 4 — Tiêu chí nghiệm thu

Một kết quả tốt phải có bằng chứng:

- Số attempts/request có trần xác định và không tăng vô hạn.
- Các request quá hạn kết thúc trong ngân sách thiết kế, sau khi tính overhead.
- Downstream không bị tăng traffic đột biến do retry; retry amplification được ghi nhận.
- Khi inventory lỗi, endpoint độc lập vẫn có tài nguyên phục vụ.
- Circuit breaker chuyển trạng thái hợp lý, số probe phục hồi bị giới hạn.
- Các thao tác ghi không tạo tác dụng phụ trùng; fallback không báo sai kết quả nghiệp vụ.
- Dashboard phân biệt lỗi trước và sau retry; cảnh báo đo ảnh hưởng thực tế lên người dùng.

**Báo cáo thực hành** nên gồm sơ đồ lời gọi, bảng cấu hình thực tế, kết quả các kịch bản lỗi, graph latency/error, số lần retry, trạng thái breaker, số rejected bulkhead và đề xuất điều chỉnh. Không cần ghi secret, access token hoặc dữ liệu khách hàng thật.

## 14. Lỗi triển khai thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| Request vẫn kéo dài nhiều giây dù read timeout ngắn | Chỉ timeout từng thao tác đọc; không có overall deadline | Phân biệt connect/read/request/deadline, đo tổng thời gian thực |
| Lỗi tăng sau khi bật retry | Retry storm, lỗi không transient, quá nhiều tầng cùng retry | Giảm max attempts, thêm jitter/budget, kiểm tra SDK retry |
| Có thanh toán hoặc đơn hàng trùng | Retry POST khi không có idempotency | Thêm key và cơ chế deduplication tại server |
| Breaker không OPEN dù dependency chậm | Chỉ đếm exception, không đo slow call; không đủ minimum calls | Kiểm tra loại lỗi, slow threshold, window và metric thực |
| Breaker luôn OPEN | Ngưỡng quá nhạy, half-open probe không phục hồi, downstream vẫn lỗi | Kiểm tra số sample, probe, latency và nguyên nhân gốc |
| Thêm annotation nhưng policy không chạy | Spring AOP self-invocation, thiếu starter/AOP, sai bean | Xác minh dependency, proxy, call path và actuator metrics |
| Bulkhead có 20 slot nhưng app vẫn nghẽn | Thread/connection pool dùng chung, blocking chỗ khác | Đo thread dump, connection pool, queue, event loop |
| 429 tiếp tục tăng | Retry không tôn trọng Retry-After, vượt quota RU/s/API | Giảm tốc và điều chỉnh capacity/rate limit |
| Service Bus xử lý trùng | Lock hết hạn hoặc Complete thất bại, message được giao lại | Idempotent consumer, gia hạn lock và DLQ |
| Autoscale làm downstream sập nhanh hơn | Mỗi replica có bulkhead cục bộ và tổng concurrency tăng | Tính tổng slot, đặt giới hạn theo capacity downstream |
| Fallback che lỗi hệ thống | Bắt mọi exception và trả kết quả nghiệp vụ giả | Trả degraded status có nghĩa, phân loại lỗi và alert |
| Có timeout nhưng tài nguyên downstream vẫn bị chiếm | Cancellation không truyền đến server hoặc truy vấn chưa ngừng | Kiểm tra cancellation, DB timeout và server-side cleanup |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một API GET gặp HTTP 503 trong 200 ms và deadline còn 1 giây. Có thể thử lại không?  
**Gợi ý trả lời:** Có thể, nếu API an toàn để gọi lại, còn retry budget, có backoff/jitter và không có tầng dưới đã retry vượt ngân sách.

**Câu 2.** Tại sao tăng max attempts từ 3 lên 10 có thể làm hệ thống kém tin cậy hơn?  
**Gợi ý trả lời:** Tăng tải lên dependency đang lỗi, chiếm nhiều thời gian và tài nguyên hơn, làm tail latency xấu đi và có thể tạo retry storm.

**Câu 3.** Circuit breaker OPEN có nên tự động gửi request liên tục đến dependency để xem đã khỏe chưa?  
**Gợi ý trả lời:** Không. Breaker nên fail fast khi OPEN và chỉ cho số lượng probe hữu hạn khi chuyển HALF_OPEN sau khoảng chờ theo policy.

**Câu 4.** Bulkhead 20 slot/replica trên 6 replica có giới hạn toàn cụm là 20 request không?  
**Gợi ý trả lời:** Không. Có thể lên đến khoảng 120 lời gọi đồng thời nếu tất cả replica đều đầy; cần tính tổng capacity và các tầng giới hạn khác.

**Câu 5.** Timeout ở client có chứng minh một request thanh toán chưa được xử lý không?  
**Gợi ý trả lời:** Không. Server có thể đã hoàn tất trước khi mất phản hồi; phải dùng idempotency và đối soát trạng thái.

**Câu 6.** Vì sao chỉ số success rate sau retry có thể gây hiểu nhầm?  
**Gợi ý trả lời:** Người dùng vẫn có thể chịu latency cao, request ban đầu lỗi nhiều, downstream nhận nhiều attempt, tốn thêm tài nguyên và chi phí. Cần theo dõi cả attempts và latency.

**Câu 7.** Có nên bật Resilience4j retry cho mọi lỗi do RestClient ném ra?  
**Gợi ý trả lời:** Không. Phải phân loại lỗi, xác định các mã 4xx/5xx thích hợp, xem idempotency, deadline và retry của SDK/gateway.

**Câu 8.** Đâu là khác biệt giữa timeout và circuit breaker?  
**Gợi ý trả lời:** Timeout giới hạn một lần chờ; circuit breaker quan sát lỗi/chậm trong nhiều lần gọi rồi chủ động chặn request mới trong một thời gian để tránh khuếch đại lỗi.

## 16. Checklist áp dụng vào dự án Azure

- [ ] Mỗi dependency có bản mô tả loại lỗi và điều kiện được retry.
- [ ] Thao tác ghi đã được bảo vệ bằng idempotency/deduplication phù hợp.
- [ ] Có overall deadline và per-attempt timeout phù hợp với gateway, SDK, ứng dụng.
- [ ] Retry có max attempts, backoff/jitter, retry budget và xét Retry-After.
- [ ] Đã kiểm tra retry tự có của Azure SDK, gateway, Functions và message consumer.
- [ ] Circuit breaker đếm đúng lỗi/chậm, có cửa sổ mẫu và HALF_OPEN probe hợp lý.
- [ ] Bulkhead giới hạn concurrency/queue, tính cả tổng số replica và connection pool.
- [ ] Fallback không làm sai quyết định nghiệp vụ hoặc dữ liệu giao dịch.
- [ ] Application Insights/Azure Monitor ghi nhận latency, retry, breaker, bulkhead, dependency health và business metrics.
- [ ] Đã thử nghiệm delay, 429, 503, network failure, overload và phục hồi trong môi trường kiểm soát.
- [ ] Có cảnh báo về SLO/error budget và hướng dẫn vận hành khi dependency suy giảm.

**Ghi nhớ:** Timeout giới hạn thời gian chờ; retry xử lý lỗi tạm thời; circuit breaker ngăn tiếp tục gọi khi dependency có dấu hiệu hỏng; bulkhead giữ cho sự cố của một dependency không chiếm hết tài nguyên ứng dụng. Chúng phát huy hiệu quả khi cùng tuân theo **deadline, giới hạn tải, idempotency, khả năng quan sát và tính đúng đắn nghiệp vụ**. Đây là nền tảng quan trọng để xây dựng ứng dụng Azure chịu lỗi từng phần mà vẫn có thể bảo vệ trải nghiệm người dùng và khôi phục có kiểm soát.
