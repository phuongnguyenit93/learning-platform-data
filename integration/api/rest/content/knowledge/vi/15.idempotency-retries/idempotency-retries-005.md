# Backoff, jitter, giới hạn số lần và ngân sách thời gian

> **Phạm vi:** Bài học thuộc **INTEGRATION_API_REST**, chương **Lũy đẳng và thử lại**. Trọng tâm là thiết kế chính sách retry cho client REST API: **khi nào được thử lại, chờ bao lâu, cách phân tán thời điểm thử bằng jitter, khi nào phải dừng theo giới hạn lượt và ngân sách thời gian**. Bài kết nối với ngữ nghĩa phương thức HTTP, mã trạng thái, `Retry-After`, idempotency, OpenAPI, Java/Spring, bảo mật, kiểm thử và vận hành.

## 1. Tình huống mở đầu: retry có thể làm sự cố nặng hơn

Ứng dụng bán hàng gọi `POST /v1/orders` để tạo đơn. Trong giờ cao điểm, dịch vụ đặt hàng tạm thời trả `503 Service Unavailable` vì connection pool cạn. Nếu 5.000 client lập tức gửi lại request ở cùng thời điểm, server đang quá tải phải xử lý **thêm 5.000 request**, gây thêm timeout. Những client đó lại đồng loạt retry, biến sự cố ngắn thành **retry storm**.

Ngược lại, nếu client hoàn toàn không retry, một lỗi mạng tạm thời có thể khiến người dùng phải bấm lại, hoặc một tác vụ hợp lệ không bao giờ hoàn tất. Bài toán không phải lựa chọn “retry hay không retry”, mà là **retry có điều kiện, có giới hạn và có trách nhiệm với hệ thống đích**.

Trong một API có side effect, còn có tình huống khó hơn:

~~~text
Client gửi POST tạo đơn
  -> Server đã ghi đơn thành công
  -> Kết nối bị ngắt trước khi response 201 đến client
  -> Client không biết đơn đã được tạo chưa
  -> Nếu POST lại không có idempotency, có thể tạo hai đơn
~~~

Một chính sách retry tốt phải giải quyết đồng thời hai mục tiêu:

1. **Khôi phục các thất bại tạm thời** mà không gây bão request hoặc kéo dài thời gian vô hạn.
2. **Không tạo tác động nghiệp vụ trùng** khi response bị mất, worker nhận lại message hoặc một yêu cầu được xử lý nhiều lần.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt lỗi **có thể retry**, lỗi cần sửa request và kết quả **chưa biết** sau timeout.
- Chọn chính sách retry dựa trên phương thức HTTP và **khả năng lặp an toàn của tác động nghiệp vụ**.
- Tính exponential backoff có trần, phân biệt **full**, **equal** và **decorrelated jitter**.
- Định nghĩa `maxAttempts`, `perAttemptTimeout`, **deadline/total time budget** và điều kiện dừng.
- Hiểu và xử lý `Retry-After` khi gặp `429`/`503`, kể cả giá trị dạng giây và HTTP-date.
- Tránh khuếch đại request qua nhiều tầng retry; kết hợp rate limiting, circuit breaker và giới hạn đồng thời.
- Thiết kế HTTP contract với idempotency key, OpenAPI, Java/Spring và bộ kiểm thử xác định.

## 2. Retry không phải tính chất của riêng HTTP status

Quyết định thử lại phụ thuộc **cả bốn yếu tố**:

1. **Loại yêu cầu:** GET, PUT, PATCH, POST, DELETE; có tác động phụ hay không?
2. **Loại lỗi:** chưa kết nối được, timeout sau khi gửi, nhận `429`/`503` hay request bị từ chối vì dữ liệu?
3. **Hợp đồng nghiệp vụ:** thao tác có idempotency key, unique constraint, precondition hoặc cơ chế đối soát không?
4. **Ngân sách còn lại:** còn đủ thời gian, lượt retry, quota và tín hiệu cho phép từ server không?

Không thể rút gọn thành “cứ `5xx` thì thử lại ba lần” hoặc “cứ POST là không được retry”. Ví dụ GET thường có thể thử lại khi lỗi tạm, nhưng một GET tốn tài nguyên cũng phải tuân thủ giới hạn. POST có thể được retry an toàn **khi server có hợp đồng idempotency bảo đảm** hoặc khi tác động vốn được thiết kế để lặp.

### 2.1. Safe, idempotent và retry-safe là ba khái niệm cần phân biệt

| Thuộc tính | Ý nghĩa | Điều nó **không** bảo đảm |
|---|---|---|
| **Safe** | Theo ngữ nghĩa HTTP, phương thức không yêu cầu thay đổi trạng thái nghiệp vụ (`GET`, `HEAD`) | Không bảo đảm backend không tốn chi phí hoặc server không có log/metric |
| **Idempotent** | Một yêu cầu giống hệt được thực hiện nhiều lần có **hiệu ứng dự định** giống thực hiện một lần | Không yêu cầu mọi response giống nhau; không tự chống mọi race, timeout hoặc side effect ngoài hợp đồng |
| **Retry-safe trong bối cảnh này** | Có thể gửi lại sau kết quả không chắc chắn mà không gây tác động nghiệp vụ trùng hoặc xung đột không được kiểm soát | Không có nghĩa retry sẽ chắc chắn thành công hoặc rẻ |

Theo ngữ nghĩa HTTP, `GET`, `HEAD`, `PUT`, `DELETE` có tính idempotent; `POST` và `PATCH` **không được bảo đảm idempotent theo mặc định**. Tuy nhiên:

- Một `PUT` cập nhật tài nguyên có thể ghi đè thay đổi vừa được client khác thực hiện. Khi cần chống lost update, dùng `If-Match`/ETag và cập nhật nguyên tử.
- Một `DELETE` lần hai có thể nhận `404` dù lần đầu đã thành công; điều này không làm mất tính idempotent của hiệu ứng dự định.
- Một `POST` kèm `Idempotency-Key` có thể được retry nếu backend thực thi hợp đồng chống trùng một cách bền vững.
- Một `PATCH` chỉ thực hiện “đặt field thành X” có thể idempotent về nghiệp vụ, nhưng một `PATCH` “cộng thêm 1” có thể không; phải xét patch document và side effect cụ thể.

**Retry-safe là quyết định của hợp đồng và hệ thống thực tế**, không thể suy diễn chỉ từ tên HTTP method.

## 3. Phân loại lỗi trước khi retry

| Tình huống | Hành động thường phù hợp | Vì sao |
|---|---|---|
| `200`/`201`/`202`/`204` thành công theo hợp đồng | **Dừng retry**, xử lý kết quả | `202` là đã nhận việc, không phải thất bại; theo dõi operation nếu cần |
| `400 Bad Request`, `422 Unprocessable Content` | Không tự retry request y nguyên | Client cần sửa dữ liệu |
| `401 Unauthorized` | Thực hiện quy trình xác thực/refresh có giới hạn rồi quyết định gửi lại | Refresh token không phải retry mù; không lặp vô hạn với token sai |
| `403 Forbidden` | Không retry y nguyên | Thiếu quyền; cần hành động khác hoặc thay đổi quyền |
| `404 Not Found` | Thông thường không retry | Chỉ poll/retry có giới hạn nếu API **công bố** eventual consistency hoặc quá trình provisioning |
| `409 Conflict` | Không retry mù | Thường cần đọc state hoặc giải quyết xung đột; chỉ retry nếu loại xung đột cụ thể được tài liệu hóa là tạm thời |
| `412 Precondition Failed`, `428 Precondition Required` | Không gửi lại y nguyên | Phải lấy validator mới hoặc thêm precondition và xử lý xung đột |
| `408 Request Timeout` | Có thể retry nếu thao tác retry-safe | Server timeout không chứng minh tác động chưa xảy ra |
| `425 Too Early` | Theo chính sách giao thức/early data và yêu cầu lặp an toàn | Không dùng làm tín hiệu chung cho mọi lỗi |
| `429 Too Many Requests` | Chờ theo `Retry-After` nếu có; giảm nhịp, giới hạn tổng | Retry ngay sẽ tăng tải |
| `500 Internal Server Error` | Chỉ retry có giới hạn nếu lỗi được xác định là tạm và request retry-safe | 500 có thể do bug cố định, retry chỉ làm nặng thêm |
| `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout` | Thường là **ứng viên retry** nếu request retry-safe | Cần backoff, jitter, time budget; 502/504 vẫn có kết quả backend không chắc chắn |
| DNS/connect failure | Có thể retry có giới hạn theo loại lỗi | Chưa chắc backend đã nhận request, nhưng không phải mọi lỗi TLS/DNS đều tạm |
| Socket reset/response read timeout | Chỉ retry khi có bảo đảm tác động lặp an toàn | Server có thể đã xử lý trước khi response bị mất |
| Lỗi TLS certificate/hostname, cấu hình URI, schema response không tương thích | Thường **không retry** | Lỗi cấu hình hoặc hợp đồng không tự hết sau vài trăm mili giây |
| Client chủ động hủy thao tác | Dừng và truyền tín hiệu hủy | Retry không được làm sống lại thao tác người dùng đã hủy |

Các dòng trên là **chính sách khởi đầu**, không phải một bảng bắt buộc cho mọi API. Hợp đồng sản phẩm có thể định nghĩa `409` hoặc `404` tạm thời trong một quy trình cụ thể, nhưng phải có dấu hiệu nhận diện rõ và điều kiện dừng.

### 3.1. Phân biệt “server không xử lý” với “client không nhận response”

Khi gặp timeout sau khi gửi request, client **thường không thể suy ra** server đã commit hay chưa. Điều này đặc biệt quan trọng với tạo đơn, thanh toán, gửi email và job nền:

~~~mermaid
flowchart TD
    A["Client gửi yêu cầu"] --> B{"Nhận phản hồi hợp lệ?"}
    B -- "2xx" --> C["Dừng retry; xử lý kết quả"]
    B -- "4xx không có retry contract" --> D["Dừng; sửa request hoặc quyền"]
    B -- "429/5xx ứng viên retry" --> E["Kiểm tra retry-safe + ngân sách"]
    B -- "Mất response / timeout" --> F{"Side effect có thể đã xảy ra?"}
    F -- "Có hoặc không biết" --> G["Cần idempotency/đối soát trước khi retry"]
    F -- "Chắc chắn chưa gửi theo khả năng quan sát" --> E
    G --> E
    E --> H{"Còn lượt, deadline, quota và server cho phép?"}
    H -- "Không" --> I["Dừng; trả lỗi hoặc trạng thái chưa biết"]
    H -- "Có" --> J["Backoff + jitter + Retry-After khi có"]
    J --> A
~~~

Không thể chỉ dựa vào thông báo “client timeout” để khẳng định request chưa tới server. Một HTTP client khác hoặc proxy có thể tự retry; cần hiểu cả tầng transport lẫn nghiệp vụ.

## 4. Vì sao phải chờ: backoff và hiệu ứng bầy đàn

**Backoff** là cách tăng khoảng chờ trước mỗi lần thử lại sau thất bại. Nó giúp dịch vụ đích có thời gian phục hồi và giảm tốc độ gửi request khi đang lỗi. **Jitter** thêm yếu tố ngẫu nhiên để các client không cùng thức dậy ở một thời điểm.

Ví dụ 1.000 client cùng gặp `503` lúc 09:00:00:

~~~text
Không backoff:
09:00:00  1.000 retry
09:00:00  1.000 retry
09:00:00  1.000 retry ... (bùng nổ)

Backoff cố định 1 giây, không jitter:
09:00:01  1.000 retry
09:00:02  1.000 retry
09:00:03  1.000 retry ... (đỉnh tải đồng bộ)

Backoff có jitter:
09:00:00.2  một phần client
09:00:00.6  một phần client
09:00:00.9  một phần client
...
Các retry phân tán theo thời gian.
~~~

Vấn đề **thundering herd** xảy ra cả khi tất cả client dùng exponential backoff **không jitter**: nếu cùng bắt đầu và cùng nhận lỗi, họ vẫn tăng lịch chờ theo cùng chuỗi.

### 4.1. Exponential backoff có trần

Đặt:

- `baseDelay`: thời gian chờ đầu tiên, ví dụ **200 ms**.
- `maxDelay`: trần của thời gian chờ từng lần, ví dụ **3.000 ms**.
- `k`: số lần thất bại dẫn tới việc sắp lịch retry, bắt đầu từ 1.

Lịch chờ tối đa trước khi thêm jitter:

\[
C_k = \min(D_{\max}, D_{\text{base}} \times 2^{k-1})
\]

Ví dụ:

| Đã thất bại lần thứ `k` | `base × 2^(k-1)` | `C_k` khi max 3.000 ms |
|---:|---:|---:|
| 1 | 200 ms | 200 ms |
| 2 | 400 ms | 400 ms |
| 3 | 800 ms | 800 ms |
| 4 | 1.600 ms | 1.600 ms |
| 5 | 3.200 ms | 3.000 ms |
| 6 | 6.400 ms | 3.000 ms |

Trần `maxDelay` giúp tránh khoảng chờ tăng theo cấp số nhân vô hạn. Khi lập trình, **không tính thẳng `base × 2^k` với số mũ không giới hạn** vì có thể overflow; dùng cách nhân tăng dần có chặn, hoặc công thức đã bảo vệ số học.

Chỉ backoff chưa đủ. Nếu sau lần thử thứ ba mà deadline đã hết, **không** nên chờ thêm chỉ vì công thức yêu cầu 800 ms.

## 5. Ba kiểu jitter thông dụng

Với `C_k` là delay có trần ở lần thất bại thứ `k`, các chiến lược có thể là:

### 5.1. Full jitter

\[
W_k \sim U(0, C_k)
\]

Chọn ngẫu nhiên một thời gian từ 0 đến `C_k`. Với `C_k=800` ms, delay có thể là 76 ms, 315 ms hoặc 734 ms. Giá trị trung bình lý thuyết là khoảng `C_k/2` nếu phân phối đều.

**Ưu điểm:** phân tán mạnh, dễ triển khai, thường giảm đỉnh tải tốt. **Đánh đổi:** một số retry có thể xảy ra rất sớm; cần cân nhắc giới hạn tối thiểu hoặc chính sách server khi quá tải.

### 5.2. Equal jitter

\[
W_k = \frac{C_k}{2} + U(0, \frac{C_k}{2})
\]

Giữ tối thiểu nửa khoảng delay có trần và ngẫu nhiên hóa nửa còn lại. Với `C_k=800` ms, khoảng chờ nằm từ 400 đến 800 ms; kỳ vọng lý thuyết khoảng 600 ms.

**Ưu điểm:** tránh các khoảng chờ quá ngắn so với full jitter. **Đánh đổi:** mức phân tán thường ít hơn và có thể tạo tổng thời gian chờ lớn hơn.

### 5.3. Decorrelated jitter

Một biến thể có trạng thái:

\[
W_k = \min(D_{\max}, U(D_{\text{base}}, 3W_{k-1}))
\]

Với `W_0 = D_base` và `U(a,b)` là lấy ngẫu nhiên trong khoảng từ `a` đến `b`. Khoảng chờ mới phụ thuộc khoảng chờ trước, thay vì chỉ phụ thuộc thứ tự lần thử. Đây là **một công thức thường dùng**, không phải chuẩn duy nhất của decorrelated jitter.

**Ưu điểm:** phân tán tốt và ít có tính chu kỳ đồng bộ; **đánh đổi:** khó lý luận trực tiếp về tổng thời gian và cần lưu trạng thái delay trước.

### 5.4. So sánh và cách chọn

| Chiến lược | Công thức hoặc khoảng | Đặc điểm | Khi cân nhắc |
|---|---|---|---|
| Không jitter | `W_k=C_k` | Dễ đoán nhưng có thể retry đồng loạt | Ít phù hợp với nhiều client đồng thời |
| Full jitter | `U(0,C_k)` | Phân tán mạnh, delay trung bình ngắn hơn mức trần | Mặc định thực dụng cho nhiều HTTP client |
| Equal jitter | `C_k/2+U(0,C_k/2)` | Không retry quá sát sau lỗi | Muốn thời gian nghỉ tối thiểu |
| Decorrelated jitter | Phụ thuộc `W_{k-1}`, có trần | Phân tán phụ thuộc lịch sử | Môi trường nhiều retry và cần phân tán tốt |

Các giá trị ngẫu nhiên **không phải** cam kết latency hay bảo đảm server phục hồi. Chọn chiến lược dựa trên kết quả load test, SLA, giới hạn đích và hành vi của client khác. Nếu dùng nhiều instance, mỗi instance/request nên có nguồn ngẫu nhiên phù hợp để không sinh chuỗi delay giống nhau; trong test nên **tiêm random source có thể kiểm soát**.

### 5.5. Minh họa lịch retry có jitter

~~~mermaid
sequenceDiagram
    participant C as REST Client
    participant A as API Gateway
    participant S as Order Service
    C->>A: Attempt 1: POST + Idempotency-Key
    A->>S: Chuyển tiếp request
    S-->>A: 503 tạm quá tải
    A-->>C: 503 + Retry-After: 2
    Note over C: Jitter cục bộ 130ms nhưng server yêu cầu chờ 2s
    Note over C: Chỉ retry nếu 2s còn nằm trong deadline
    C->>A: Attempt 2: cùng key, cùng payload
    A->>S: Chuyển tiếp request
    S-->>A: 201 Created + Location
    A-->>C: 201 Created
    Note over C: Dừng, không retry thêm
~~~

Trong ví dụ, `Retry-After` là **thời gian chờ tối thiểu do server đề nghị cho lần thử lại**. Nếu delay random tính được 130 ms nhưng server yêu cầu 2 giây, client không nên retry ở mốc 130 ms.

## 6. Định nghĩa giới hạn lượt thử đúng: attempts khác retries

Hai biến cấu hình dễ gây nhầm:

- **`maxAttempts=4`**: tối đa **4 lần gửi tổng cộng**, gồm lần đầu và tối đa 3 lần retry.
- **`maxRetries=4`**: tối đa **4 lần thử lại sau lần đầu**, tức tối đa 5 lần gửi.

Trong bài này chọn cách đếm **`maxAttempts` bao gồm lần đầu** để tránh đếm lệch. Luôn ghi rõ điều này trong configuration và metric.

### 6.1. Ví dụ tính cận trên thời gian

Giả sử:

- `maxAttempts=5` (1 lần đầu + tối đa 4 lần retry).
- `perAttemptTimeout=2 giây`.
- `baseDelay=200 ms` và `maxDelay=3 giây`.
- Không có `Retry-After`; không có jitter, delay lần lượt 200, 400, 800, 1.600 ms.

Nếu mỗi lần gửi đều chờ trọn timeout, thời gian tối đa theo lịch này là:

\[
5 \times 2s + (0.2+0.4+0.8+1.6)s = 13s
\]

Với **full jitter**, tổng delay có thể nhỏ hơn cận trên của từng khoảng, nhưng **không được dựa vào giá trị trung bình** để hứa mọi request kết thúc trước deadline. Nếu business SLA chỉ cho phép 6 giây, chính sách trên **không phù hợp**, dù maxAttempts hữu hạn.

### 6.2. Một request có nhiều loại timeout

| Timeout | Khống chế | Lưu ý |
|---|---|---|
| Connect timeout | Thời gian thiết lập kết nối tới đích | Không bao gồm toàn bộ thời gian xử lý |
| Per-attempt/request timeout | Tổng thời gian một attempt được cho phép theo client/library | Phải hiểu thư viện đo khoảng nào, gồm DNS/TLS/body hay không |
| Read/response timeout | Khoảng chờ dữ liệu phản hồi hoặc giữa các lần đọc, tùy thư viện | Không mặc định tương đương end-to-end timeout |
| **Total retry budget / deadline** | Toàn bộ hành trình: attempt đầu, các attempt sau, backoff, parse, overhead | **Giới hạn trên cùng** cần được truyền qua workflow |
| Server processing timeout | Thời gian server cho phép xử lý | Client timeout có thể xảy ra trước khi server dừng |
| Upstream deadline | Ngân sách còn lại do tầng gọi tới truyền xuống | Không được kéo dài quá deadline của người dùng |

Không cho mọi tầng tự bắt đầu “30 giây mới” khi request tới từng microservice. Nếu request từ người dùng chỉ có 8 giây, downstream phải nhận phần **ngân sách còn lại** sau khi đã tiêu thời gian xử lý trước đó.

## 7. Ngân sách thời gian tổng: deadline quan trọng hơn số lượt tối đa

**Time budget** là lượng thời gian client sẵn sàng dành cho toàn bộ thao tác. Có thể thiết kế theo thời lượng `totalBudget=8s` kể từ lúc bắt đầu, sau đó chuyển thành **deadline cố định**.

~~~text
start = monotonicNow()
deadline = start + totalBudget

Mỗi lần trước attempt:
  remaining = deadline - monotonicNow()
  nếu remaining <= 0: dừng
  attemptTimeout = min(configuredPerAttemptTimeout, remaining)

Sau attempt thất bại:
  nếu hết maxAttempts: dừng
  nếu không retry-safe: dừng
  delay = chọn backoff/jitter và tôn trọng Retry-After
  nếu delay >= remaining: dừng, không ngủ vô ích
  ngủ tối đa delay (có thể bị hủy)
  kiểm tra lại remaining trước lần gửi tiếp theo
~~~

Sử dụng **đồng hồ đơn điệu (monotonic elapsed time)** cho ngân sách cục bộ để tránh thay đổi đồng hồ hệ thống làm kéo dài hoặc rút ngắn lịch retry. Khi parse `Retry-After` dưới dạng HTTP-date, cần thời gian lịch thực (wall clock) để tính khoảng đợi và lưu ý clock skew.

### 7.1. Ví dụ deadline 8 giây

| Mốc | Việc xảy ra | Thời gian đã dùng | Còn lại |
|---|---|---:|---:|
| Bắt đầu | Attempt 1, deadline +8s | 0,0s | 8,0s |
| Lỗi timeout | Attempt 1 dùng 2s | 2,0s | 6,0s |
| Backoff | Chờ 0,3s | 2,3s | 5,7s |
| Lỗi `503` | Attempt 2 mất 1s | 3,3s | 4,7s |
| Server yêu cầu chờ | `Retry-After: 5` | 3,3s | 4,7s |
| Quyết định | Không còn đủ 5s trong budget | 3,3s | 4,7s |
| Kết thúc | Trả lỗi/báo trạng thái chưa biết cho caller | 3,3s | 4,7s |

**Không nên chờ 5 giây rồi vẫn gửi thêm một request sau deadline**. Nếu hợp đồng server yêu cầu chờ lâu hơn ngân sách còn lại, client có thể dừng và truyền tín hiệu thích hợp cho tầng gọi. Deadline không phải lời đảm bảo mọi thư viện sẽ dừng đúng từng mili giây: còn scheduling, cleanup và các thành phần không hỗ trợ hủy. Phải đo thực tế và dành khoảng an toàn.

### 7.2. Tránh khởi chạy attempt khi không đủ thời gian hữu ích

Giả sử còn 15 ms, trong khi kết nối và một request hữu ích thường cần ít nhất 100 ms. Dù `remaining > 0`, việc gửi thêm có thể chỉ làm tăng tải. Có thể đặt **minimum useful attempt budget** (ví dụ 100–200 ms tùy môi trường) để dừng trước khi attempt gần như chắc chắn timeout. Ngưỡng này cần được đo, không chọn tùy tiện cho mọi dịch vụ.

### 7.3. Tín hiệu hủy và quy tắc cleanup

Khi người dùng bấm Cancel, request cha hết deadline hoặc thread bị interrupt, client phải ngừng lên lịch retry mới. Nếu thư viện cho phép cancel attempt đang chạy, nên truyền cancellation; nhưng **hủy request phía client không bảo đảm server đã rollback tác động**. Với nghiệp vụ tạo đơn/thanh toán, idempotency và endpoint tra cứu trạng thái vẫn cần thiết.

## 8. `Retry-After`: tôn trọng tín hiệu của server

Server có thể gửi `Retry-After`, đặc biệt khi đang rate limit hoặc tạm không đáp ứng:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 4
Content-Type: application/problem+json

{"type":"about:blank","title":"Rate limit exceeded","status":429}
~~~

Hoặc:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: Wed, 18 Nov 2026 09:00:20 GMT
Content-Type: application/problem+json

{"type":"about:blank","title":"Service temporarily unavailable","status":503}
~~~

### 8.1. Hai dạng giá trị

- **Delay-seconds:** số nguyên không âm, ví dụ `Retry-After: 4` nghĩa là chờ khoảng 4 giây trước khi thử lại.
- **HTTP-date:** ngày giờ theo cú pháp HTTP, ví dụ `Wed, 18 Nov 2026 09:00:20 GMT`; client tính thời gian còn lại đến mốc đó theo đồng hồ lịch.

Parser cần xử lý đúng cả hai dạng và chống overflow, giá trị âm, chuỗi sai format hoặc date quá xa. Nếu date nằm trong quá khứ, khoảng chờ suy ra có thể xem là 0, nhưng client vẫn áp dụng backoff/jitter và quota cục bộ.

### 8.2. Kết hợp backoff cục bộ với server hint

Với một lỗi được phép retry, chính sách minh họa:

\[
W_{\text{effective}} = \max(W_{\text{local-jitter}}, W_{\text{Retry-After}})
\]

Nếu không có header hoặc giá trị không hợp lệ, dùng local jitter và ghi metric. Nếu server yêu cầu 10 giây nhưng `totalBudget` chỉ còn 3 giây, **dừng retry**; không tự cắt thành 3 giây rồi gửi sớm hơn chỉ thị.

`maxDelay` thường dùng để chặn **backoff do client tự sinh**. Không nên áp trần này lên `Retry-After` theo cách biến yêu cầu “đợi ít nhất 30 giây” thành retry sau 3 giây. Nếu server hint vượt giới hạn của caller, hãy kết thúc và để quy trình tầng trên quyết định lần thử mới sau đó.

### 8.3. `Retry-After` không đồng nghĩa mọi response được retry

Không retry một `403` chỉ vì response có `Retry-After` lạ. Trước tiên phải kiểm tra **status, ngữ nghĩa lỗi và retry-safe**, sau đó mới tính delay. Header này cũng xuất hiện trong một số bối cảnh redirect; không trộn chiến lược retry với việc theo redirect.

Với `202 Accepted` trong API tác vụ nền, đôi khi server dùng `Retry-After` như **gợi ý polling**; đó là quy ước API cần được tài liệu hóa, không phải tín hiệu yêu cầu gửi lại `POST` đã được nhận. Client nên **GET operation monitor**, không POST lại chỉ vì kết quả nghiệp vụ còn đang chạy.

## 9. Idempotency là điều kiện tiên quyết cho retry có side effect

### 9.1. Tạo đơn với Idempotency-Key

Client gửi:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 2fc34b36-7517-4d7c-b3e6-5f6123d27c87
Content-Type: application/json

{
  "customerId": "cus_82",
  "items": [{"sku":"BOOK-123","quantity":2}]
}
~~~

Server tạo đơn và phát response, nhưng response bị mất:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/ord_916
Content-Type: application/json

{"id":"ord_916","status":"PENDING_PAYMENT"}
~~~

Client retry **cùng key và cùng nội dung request**. Server cần nhận ra yêu cầu logic đã được xử lý, trả lại cùng kết quả hoặc kết quả tương đương theo hợp đồng, **không tạo ord_917 chỉ vì request đến lần hai**.

### 9.2. Hợp đồng idempotency tối thiểu

| Khía cạnh | Quyết định cần công bố |
|---|---|
| Phạm vi khóa | Gắn với principal/tenant và loại thao tác, không cho user khác đoán key để đọc kết quả |
| Fingerprint request | Cùng key nhưng payload khác phải báo lỗi theo contract, ví dụ `409 Conflict` |
| Trạng thái đang xử lý | Khi request trùng tới lúc lần đầu còn chạy, trả same operation/response hoặc conflict tạm theo contract rõ |
| Atomicity | Đặt chỗ key và commit tác động nghiệp vụ không tạo race khi retry đồng thời |
| Retention | Khóa được giữ bao lâu; retry sau khi hết hạn có thể tạo tác động mới |
| Response replay | Có trả nguyên status/body/Location cũ hay response hiện hành; ghi rõ để SDK xử lý |
| Lỗi hậu xử lý | Có operation resource để đối soát nếu kết quả bất đồng bộ |

`Idempotency-Key` phải được giữ **nguyên** qua các attempt của **cùng một thao tác logic**. Nếu client tạo UUID mới mỗi lần retry, server sẽ coi đó là những thao tác khác nhau và cơ chế chống trùng không còn hiệu quả. **Không dùng lại cùng key cho một thao tác nghiệp vụ mới.**

### 9.3. Retry transport không giải quyết exactly-once business effect

Ngay cả khi HTTP chỉ tạo một operation, worker có thể nhận message hai lần do broker redelivery hoặc timeout khi gọi nhà cung cấp ngoài. Cần:

- Unique constraint/transaction hoặc dedupe cho thao tác logic.
- Idempotency ở worker và khi gọi hệ thống ngoài nếu có thể.
- Outbox hoặc cơ chế tiếp nhận bền vững để tránh đã `202` nhưng mất công việc.
- Đối soát khi trạng thái thực của thanh toán/đơn hàng không rõ.

**Không tuyên bố exactly-once chỉ vì client dùng jitter, idempotency key hoặc queue có ack.** Hãy chứng minh tính duy nhất của tác động nghiệp vụ ở điểm ghi cuối cùng.

### 9.4. `If-Match` không thay thế idempotency key

`If-Match`/ETag bảo vệ cập nhật khi representation đã đổi: khi stale, server trả `412 Precondition Failed`. `Idempotency-Key` giúp nhận diện **cùng request nghiệp vụ được gửi lại**. Một endpoint có thể cần cả hai:

~~~http
PATCH /v1/order-drafts/ord_916 HTTP/1.1
If-Match: "draft-916-v7"
Idempotency-Key: 0d2528e3-f278-4fad-8361-a3185912ade2
Content-Type: application/merge-patch+json

{"deliveryNote":"Để trước cửa"}
~~~

Khi response thất lạc sau commit, retry với ETag cũ có thể nhận `412` nếu server không có replay/dedupe contract. Nếu muốn nhận lại kết quả của cùng lệnh, thiết kế idempotency replay theo policy tương thích với precondition, tránh để client hiểu nhầm rằng request lần đầu chắc chắn thất bại. Client không được tự bỏ `If-Match` để ép ghi.

## 10. Retry ở nhiều tầng: vì sao “mỗi tầng 3 lần” nguy hiểm?

Một request đi qua:

~~~text
Mobile client
  -> API Gateway
    -> Order API
      -> Inventory API
        -> Database
~~~

Nếu **ba tầng** liên tiếp đều cho phép tối đa **3 attempts**, một request có thể gây tới:

\[
3 \times 3 \times 3 = 27
\]

lần gọi đến tầng cuối trong tình huống xấu, **chưa tính** những tầng khác, job queue hoặc side effect. Với bốn tầng cùng nhân ba, tối đa có thể lên tới 81 lần gọi. Đây là **request amplification** do retry lồng nhau.

### 10.1. Chỉ định chủ sở hữu retry

Một thiết kế tốt cần quyết định:

- Tầng nào **được phép retry** thao tác này? Ví dụ API client retry GET khi transport lỗi, còn Order API chịu trách nhiệm retry một read-only call tới Inventory.
- Tầng nào **không retry** để tránh nhân số request? Ví dụ gateway không tự retry POST có side effect nếu không có hợp đồng idempotency.
- Có truyền **deadline từ upstream** xuống từng call không? Downstream chỉ dùng ngân sách còn lại, không reset timer.
- Có **phân biệt idempotency scope** giữa lệnh nghiệp vụ và từng bước con không?
- Log/trace có thể ghép các attempt cùng logical operation không?

Đừng bật retry mặc định trong SDK, gateway, service mesh, HTTP client và application code mà không kiểm tra tổng số attempts trên toàn tuyến.

### 10.2. Retry trong queue và worker là một tầng khác

Một công việc nền được tiếp nhận bằng `202 Accepted` có thể có:

1. Client retry `POST` khi response ban đầu thất lạc.
2. Publisher retry ghi message vào broker.
3. Broker redeliver cùng message sau timeout.
4. Worker retry gọi hệ thống thanh toán hoặc dịch vụ ngoài.

Mỗi lớp phải có **danh tính công việc và idempotency** phù hợp. Backoff giữa các attempt của worker thường lâu hơn HTTP request tương tác. Nếu tác vụ kéo dài phút, không nên để HTTP client giữ kết nối và retry POST trong nhiều phút; dùng **operation monitor** với polling/backoff riêng hoặc webhook theo hợp đồng.

### 10.3. Vì sao “retry ở tầng gần lỗi nhất” thường hữu ích?

Khi tầng gọi Inventory gặp một transient 503 trong 100 ms, retry nội bộ trong **ngân sách được cấp** có thể tránh lặp toàn bộ workflow của mobile. Nhưng nếu tất cả request của Order API đã bị quá tải, retry ở tầng dưới có thể khiến sự cố nặng hơn. Chọn vị trí retry dựa trên:

- Có đủ ngữ cảnh để phân loại lỗi và biết thao tác có retry-safe không.
- Có thể ngăn tạo side effect trùng hay không.
- Có thể quan sát và giới hạn tổng budget cùng concurrency không.
- Có cách **trả lỗi sớm/load shed** khi đích không có khả năng phục hồi ngay không.

Không có quy tắc “chỉ retry tại một tầng” tuyệt đối; có thể có nhiều tầng **với ngân sách phối hợp và giới hạn khuếch đại**, nhưng phải chứng minh được tác động.

## 11. Kết hợp retry với bảo vệ hệ thống

### 11.1. Rate limiting và token bucket

Khi nhận `429`, client cần tôn trọng `Retry-After` và giảm tần suất. Một **retry budget** theo số lượng cũng hữu ích: ví dụ số request retry chỉ được chiếm một tỷ lệ nhỏ so với request gốc trong một cửa sổ thời gian, hoặc tiêu token từ bucket riêng. Khi hết token, không retry dù `maxAttempts` chưa đạt.

Hai loại ngân sách khác nhau:

- **Time budget:** còn bao nhiêu thời gian cho một logical operation.
- **Retry capacity budget:** hệ thống còn cho phép gửi bao nhiêu request retry trên tổng tải.

Nếu người dùng có 8 giây nhưng retry bucket rỗng, **không** dùng hết 8 giây để spam; dừng hoặc chờ theo chính sách chung mà không vượt deadline.

### 11.2. Circuit breaker

Circuit breaker có thể **ngừng thử gửi** tới dependency đang lỗi nặng trong một khoảng thời gian, sau đó thử một số request probe để đánh giá phục hồi. Kết hợp với backoff giúp tránh mỗi client tiếp tục tạo request khi hệ thống không thể phục vụ.

**Phân biệt:** circuit breaker không phải điều kiện idempotency. Nó bảo vệ tài nguyên và điều chỉnh lưu lượng, không kiểm tra việc một thanh toán đã được ghi hay chưa. Khi circuit mở, response có thể là lỗi tạm thời hoặc fallback theo contract; không tự biến lỗi thành thành công giả.

### 11.3. Bulkhead và giới hạn đồng thời

Ngay cả khi mỗi request retry tối đa ba lần, một ứng dụng có hàng chục nghìn request đồng thời vẫn có thể tạo tải lớn. Giới hạn số tác vụ đang chờ, số kết nối, số request đang gọi dependency và queue size giúp tránh cạn tài nguyên. Không nên gom tất cả retry vào một queue không giới hạn trong bộ nhớ.

### 11.4. Khi nào nên dừng sớm?

Ngay cả trước khi hết maxAttempts, một client nên dừng khi:

- Deadline hoặc minimum useful attempt budget không còn.
- Có cancellation từ người dùng hoặc caller.
- `Retry-After` nằm ngoài deadline.
- Lỗi không retryable hoặc request không đủ bảo đảm retry-safe.
- Circuit breaker đang mở, quota retry đã hết hoặc dependency bị load shedding.
- Mục tiêu nghiệp vụ đã được xác nhận thành công qua response hoặc endpoint đối soát.

Không coi “chỉ mới thử hai lần” là lý do bắt buộc phải dùng hết lượt thứ ba.

### 11.5. Hedged requests không giống retries

Một số hệ thống gửi **request thứ hai trước khi request đầu tiên báo lỗi** để giảm tail latency. Đó là **hedging**, có thể làm tăng tải khi backend chậm. Không áp dụng đại trà cho POST có side effect; với GET vẫn cần giới hạn concurrency, quota, cancellation và đo lợi ích. Hedging cần đánh giá riêng, không nên tự thêm chỉ vì đã có thư viện retry.

## 12. Một chính sách retry ví dụ có thể công bố

Giả sử SDK gọi `POST /v1/report-jobs` để tạo job xuất báo cáo. Server hỗ trợ `Idempotency-Key` và trả `202 Accepted` với `Location` đến monitor.

| Thành phần | Quy tắc minh họa |
|---|---|
| **Retry-safe** | Chỉ retry cùng logical POST khi có Idempotency-Key đã được server hỗ trợ; body có thể replay nguyên vẹn |
| **Lỗi HTTP có thể retry** | `408`, `429`, `502`, `503`, `504`; `500` chỉ khi có xác nhận lỗi tạm trong contract |
| **Transport** | Chỉ retry nhóm timeout/connect/reset đã nhận diện; lỗi cấu hình TLS/chứng chỉ không retry |
| **maxAttempts** | 4, **bao gồm attempt đầu** |
| **baseDelay** | 250 ms |
| **maxDelay** | 2 giây với backoff cục bộ |
| **Jitter** | Full jitter |
| **perAttemptTimeout** | 1,5 giây, còn phải bị giới hạn bởi remaining budget |
| **totalBudget** | 6 giây kể từ khi bắt đầu thao tác |
| **minimum useful attempt** | 100 ms trong ví dụ |
| **Retry-After** | Xem là ngưỡng chờ tối thiểu trên 429/503; không vượt deadline |
| **Response thành công** | Bất kỳ 2xx hợp lệ theo hợp đồng, đặc biệt `202`: **dừng retry POST**, bắt đầu theo dõi operation |
| **Cancellation** | Dừng lên lịch retry và truyền hủy nếu thư viện hỗ trợ |
| **Truy vết** | Một logical request ID, attempt count, lỗi gốc và thời gian đã dùng |

**Đây là policy minh họa**, không phải khuyến nghị dùng chung các số 250 ms/6 s cho mọi môi trường. Chọn tham số từ SLO, latency quan sát được, quota dependency, tỷ lệ lỗi tạm, chi phí và số lượng client. Cần thử tải để biết sau retry hệ thống có phục hồi tốt hơn hay bị khuếch đại.

### 12.1. Sơ đồ quyết định cho một attempt

~~~mermaid
flowchart TD
    Start["Bắt đầu logical operation"] --> Budget{"Còn time budget và retry capacity?"}
    Budget -- "Không" --> Stop["Dừng và trả kết quả chưa biết / lỗi đã quan sát"]
    Budget -- "Có" --> Send["Gửi attempt với timeout <= remaining"]
    Send --> Outcome{"Kết quả?"}
    Outcome -- "2xx" --> Success["Thành công HTTP; dừng retry"]
    Outcome -- "Lỗi vĩnh viễn / 4xx không cho retry" --> Fail["Dừng; báo lỗi hợp đồng"]
    Outcome -- "Timeout hoặc transient failure" --> Safe{"Request retry-safe?"}
    Safe -- "Không" --> Reconcile["Đối soát; không retry mù"]
    Safe -- "Có" --> Attempts{"Đã đạt maxAttempts?"}
    Attempts -- "Có" --> Stop
    Attempts -- "Chưa" --> Wait["Delay = max(jitter, Retry-After)"]
    Wait --> Fits{"Delay + lượt tiếp theo còn trong deadline?"}
    Fits -- "Không" --> Stop
    Fits -- "Có" --> Budget
~~~

Đối với lỗi HTTP `500` có thể do lỗi lập trình cố định, classifier phải dựa trên hợp đồng, không biến mọi 500 thành transient. Với lỗi network, classifier phải phân biệt điều kiện có thể khôi phục và lỗi có khả năng lặp lại vô ích; không bắt các exception tùy ý rồi retry.

## 13. Java 17+: vòng retry có deadline, jitter và Retry-After

Đoạn mã minh họa sau dùng Java `HttpClient` và một request POST **đã được bảo vệ bằng Idempotency-Key ở server**. Nó giữ nguyên body/key giữa các attempt, không tự theo redirect tới host khác và kiểm soát **time budget xuyên suốt cả backoff**.

### 13.1. Chính sách và helper tách biệt

~~~java
import java.time.Duration;

public record RetryPolicy(
    int maxAttempts,
    Duration totalBudget,
    Duration perAttemptTimeout,
    Duration baseDelay,
    Duration maxDelay,
    Duration minUsefulAttempt
) {
    public RetryPolicy {
        if (maxAttempts < 1 || maxAttempts > 10
                || totalBudget.isNegative() || totalBudget.isZero()
                || perAttemptTimeout.isNegative()
                || perAttemptTimeout.isZero()
                || baseDelay.isNegative() || baseDelay.isZero()
                || maxDelay.compareTo(baseDelay) < 0
                || minUsefulAttempt.isNegative()
                || minUsefulAttempt.isZero()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
    }
}
~~~

Có thể giới hạn `maxAttempts` dưới 10, `maxDelay` theo số giây và các cấu hình khác qua validator hệ thống. Không cho cấu hình tùy ý cực lớn đến mức phép tính `toNanos` hoặc `toMillis` overflow.

### 13.2. Tính jitter không bị tràn số khi tăng mũ

~~~java
import java.time.Duration;
import java.util.random.RandomGenerator;

public final class Backoff {
    private Backoff() {}

    public static Duration fullJitter(
            Duration base, Duration max,
            int failedAttempt, RandomGenerator random) {
        long maxMillis = max.toMillis();
        long capMillis = Math.min(base.toMillis(), maxMillis);
        if (capMillis <= 0 || maxMillis <= 0) {
            throw new IllegalArgumentException("Delay must be >= 1ms");
        }

        // failedAttempt=1 => base; attempt=2 => 2*base, v.v.
        for (int n = 1; n < failedAttempt; n++) {
            capMillis = capMillis > maxMillis / 2
                ? maxMillis
                : Math.min(maxMillis, capMillis * 2);
        }
        // Các policy dùng delay thực tế nhỏ, nên cap+1 không overflow.
        return Duration.ofMillis(random.nextLong(capMillis + 1));
    }
}
~~~

Với `maxDelay` ở cấp mili giây đến vài giây, công thức tránh phép tính `2^k` có thể overflow. Điều kiện `capMillis > maxMillis/2` là kỹ thuật chặn nhân hai; cấu hình vẫn cần hạn chế `maxMillis` để phép `capMillis + 1` an toàn. Có thể thêm một khoảng chờ tối thiểu nếu hệ thống không muốn full jitter cho ra 0 ms, nhưng phải thống nhất với yêu cầu `Retry-After` và deadline.

### 13.3. Parse hai dạng Retry-After

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public final class RetryAfter {
    private RetryAfter() {}

    public static Duration parseOrZero(String header, Instant now) {
        if (header == null) return Duration.ZERO;
        String value = header.trim();

        if (value.matches("[0-9]{1,10}")) {
            try {
                long seconds = Long.parseLong(value);
                // Giá trị rất lớn vẫn lớn hơn mọi budget tương tác.
                return Duration.ofSeconds(Math.min(
                    seconds, 366L * 24 * 3600));
            } catch (NumberFormatException e) {
                return Duration.ZERO;
            }
        }

        try {
            Instant target = ZonedDateTime.parse(
                value, DateTimeFormatter.RFC_1123_DATE_TIME
            ).toInstant();
            Duration wait = Duration.between(now, target);
            return wait.isNegative() ? Duration.ZERO : wait;
        } catch (DateTimeParseException e) {
            return Duration.ZERO;
        }
    }
}
~~~

Hàm `parseOrZero` trả 0 khi header sai để policy fallback sang jitter; hệ thống thật nên **ghi metric/log an toàn** về invalid header. Hàm dùng `Instant.now()` bên ngoài nên có thể tiêm `Clock` trong test. `HTTP-date` phụ thuộc đồng hồ hệ thống; nếu cần bù clock skew, có thể xem xét header `Date` của server và ràng buộc chặt chẽ hơn, tránh biến thành chờ âm hoặc retry quá sớm.

### 13.4. HTTP client với tổng ngân sách

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class ReportJobClient {
    private final HttpClient http;
    private final RetryPolicy policy;

    public ReportJobClient(HttpClient http, RetryPolicy policy) {
        this.http = http;
        this.policy = policy;
    }

    public HttpResponse<String> startReport(
            URI endpoint,
            String accessToken,
            String idempotencyKey,
            String stableJsonBody)
            throws IOException, InterruptedException {

        // System.nanoTime dùng để đo elapsed time, không dùng để
        // suy ra ngày giờ lịch thực của Retry-After HTTP-date.
        long started = System.nanoTime();
        long budgetNanos = policy.totalBudget().toNanos();
        HttpResponse<String> lastResponse = null;
        IOException lastTransportFailure = null;

        for (int attempt = 1;
                attempt <= policy.maxAttempts(); attempt++) {
            long elapsed = Math.max(0, System.nanoTime() - started);
            long remainingNanos = budgetNanos - elapsed;
            if (remainingNanos
                    < policy.minUsefulAttempt().toNanos()) {
                break;
            }

            Duration currentTimeout = Duration.ofNanos(Math.min(
                remainingNanos,
                policy.perAttemptTimeout().toNanos()));

            // Request body publisher này có thể tạo lại cho mỗi attempt.
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(currentTimeout)
                .header("Authorization", "Bearer " + accessToken)
                .header("Content-Type", "application/json")
                .header("Idempotency-Key", idempotencyKey)
                .POST(HttpRequest.BodyPublishers.ofString(
                    stableJsonBody, StandardCharsets.UTF_8))
                .build();

            HttpResponse<String> response = null;
            try {
                response = http.send(
                    request, HttpResponse.BodyHandlers.ofString());
                lastResponse = response;
                lastTransportFailure = null;

                // Trả 2xx và mọi lỗi không được retry cho caller.
                if (!retryableStatus(response.statusCode())) {
                    return response;
                }
            } catch (IOException ex) {
                // Timeout sau khi gửi có kết quả chưa rõ,
                // nên chỉ retry bởi POST này có idempotency contract.
                if (!retryableTransport(ex)) throw ex;
                lastTransportFailure = ex;
                lastResponse = null;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }

            if (attempt == policy.maxAttempts()) break;

            Duration local = Backoff.fullJitter(
                policy.baseDelay(), policy.maxDelay(),
                attempt, ThreadLocalRandom.current());
            Duration serverHint = response == null
                ? Duration.ZERO
                : RetryAfter.parseOrZero(
                    response.headers()
                        .firstValue("Retry-After").orElse(null),
                    Instant.now());

            Duration delay = local.compareTo(serverHint) >= 0
                ? local : serverHint;
            elapsed = Math.max(0, System.nanoTime() - started);
            remainingNanos = budgetNanos - elapsed;
            Duration remaining = remainingNanos <= 0
                ? Duration.ZERO
                : Duration.ofNanos(remainingNanos);

            // Không ngủ nếu sau đó không còn đủ thời gian
            // hữu ích để gửi một attempt tiếp theo.
            if (delay.compareTo(
                    remaining.minus(policy.minUsefulAttempt())) >= 0) {
                break;
            }

            try {
                Thread.sleep(delay.toMillis());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }
        }

        // Giữ HTTP response cuối cùng nếu đã nhận được, để tầng
        // gọi nhìn thấy 429/503 và header gốc thay vì đổi thành 500.
        if (lastResponse != null) return lastResponse;
        throw new IOException(
            "Retry attempts or time budget exhausted",
            lastTransportFailure);
    }

    private static boolean retryableStatus(int code) {
        return code == 408 || code == 429
            || code == 502 || code == 503 || code == 504;
    }

    private static boolean retryableTransport(IOException ex) {
        return ex instanceof HttpTimeoutException
            || ex instanceof ConnectException
            || ex instanceof SocketException;
    }
}
~~~

**Giới hạn rõ ràng của ví dụ:** đây là **mẫu minh họa policy** cho một request có body nhỏ, có thể replay và server đã bảo đảm idempotency. Không sử dụng nguyên xi mà bỏ qua kiểm thử. Các điểm cần cải thiện trong production:

- **Constructor `HttpClient`** cần dùng `followRedirects(HttpClient.Redirect.NEVER)` hoặc chính sách redirect an toàn, `connectTimeout` phù hợp và kiểm soát proxy; code nhận một HttpClient được tiêm nên cấu hình do caller chịu trách nhiệm.
- **Body publisher** phải có thể replay. `ofString` tạo lại body là phù hợp cho ví dụ; stream đọc một lần hoặc multipart upload lớn cần cơ chế riêng.
- **Hạn chế budget:** `Duration.toNanos()` có thể overflow với cấu hình cực lớn; bắt buộc validate giới hạn hợp lý ở nơi tạo `RetryPolicy`.
- **Timeout thực tế:** `HttpRequest.timeout` giới hạn thời gian theo khả năng hỗ trợ của Java HTTP client, nhưng vẫn phải xem DNS, connection pool, thread scheduling, parse body và cleanup; đo latency end-to-end thật.
- **Không retry mọi IOException:** ví dụ chỉ nhận một số loại timeout/connect/reset; TLS certificate lỗi, URI sai, lỗi parse response hoặc request không thể replay cần dừng. Classification production cần thêm test theo thư viện và stack mạng thực tế.
- **HTTP 500:** mặc định không retry trong code vì có thể là lỗi cố định; nếu API xác định một dạng 500 tạm thời, thêm có chủ đích và theo dõi hiệu quả.
- **Ngân sách/cancel:** mã đồng bộ `Thread.sleep` giúp giải thích; ứng dụng reactive/async nên dùng scheduler non-blocking và truyền cancellation/deadline.
- **Idempotency:** caller phải tạo **một key cho mỗi logical operation**, giữ key qua mọi retry và không thay body. Tầng server cần thực sự chống trùng.
- **Quyền và bí mật:** không log bearer token, payload nhạy cảm hoặc idempotency key đầy đủ; không forward token qua redirect/host không tin cậy.

### 13.5. Cách khởi tạo minh họa

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

RetryPolicy retryPolicy = new RetryPolicy(
    4,
    Duration.ofSeconds(6),
    Duration.ofMillis(1500),
    Duration.ofMillis(250),
    Duration.ofSeconds(2),
    Duration.ofMillis(100)
);

HttpClient http = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

ReportJobClient client = new ReportJobClient(http, retryPolicy);
// Caller tạo key mới một lần cho logical operation rồi giữ nguyên
// trong mọi attempt của client.startReport(...).
~~~

Trong mô hình tải cao, không tạo mới một HttpClient và connection pool cho từng request; tái sử dụng client đã cấu hình. Lớp gọi nên kiểm tra response: nếu `202` thì lấy `Location` và theo dõi operation, nếu `429/503` cuối cùng thì truyền thông tin backoff thích hợp, nếu transport không rõ kết quả thì có thể đối soát bằng idempotency key/operation resource.

## 14. Tích hợp vào ứng dụng Spring

Spring cung cấp nhiều cách gọi HTTP và các thư viện resilience thường được tích hợp vào ứng dụng Java, nhưng **chọn thư viện không thay thế thiết kế policy**. Quy tắc phải được áp dụng tại đúng ranh giới logical operation, nơi ứng dụng biết request có retry-safe hay không.

### 14.1. Ranh giới ứng dụng và client adapter

~~~mermaid
flowchart LR
    Web["Controller / use case"] --> Cmd["Logical command\nID + Idempotency-Key"]
    Cmd --> Retry["HTTP client adapter\nretry classifier + budget"]
    Retry --> Dep["Downstream REST API"]
    Dep --> Retry
    Retry --> Result["Result / error / uncertain outcome"]
    Result --> Web
    Metrics["Tracing + metrics"] -.-> Retry
~~~

Controller không cần tự viết vòng `while (retry)` cho mọi request. Một adapter có thể nhận `RetryContext` gồm deadline, principal/tenant và logical operation ID rồi thực hiện các attempt với policy tương ứng. Service nghiệp vụ quyết định khi nào **không** retry (ví dụ trạng thái đã xác nhận) và cách đối soát kết quả sau timeout.

Ví dụ cấu hình giả định trong ứng dụng:

~~~yaml
integration:
  report-service:
    retry:
      max-attempts: 4
      total-budget: 6s
      per-attempt-timeout: 1500ms
      base-delay: 250ms
      max-delay: 2s
      jitter: full
      retryable-statuses: [408, 429, 502, 503, 504]
~~~

Đây là **YAML cấu hình minh họa**, không phải thuộc tính Spring Boot tự nhận diện. Muốn dùng thật phải tạo `@ConfigurationProperties`, validation và mã kết nối configuration vào HTTP client/retry component. Cấu hình cần một nguồn nhất quán; tránh để gateway có policy riêng âm thầm nhân thêm attempts.

### 14.2. Khi dùng Spring Retry hoặc Resilience4j

Những thư viện như **Spring Retry** hoặc **Resilience4j** có thể giúp thực thi retry, backoff, circuit breaker và metric, nhưng cần kiểm tra:

- `maxAttempts` hoặc `maxRetryAttempts` của thư viện có **tính lần đầu** không? Mỗi thư viện/phiên bản có quy ước riêng.
- Có hỗ trợ **jitter thực sự** hay chỉ exponential backoff cố định?
- `Retry-After` có được parse và tôn trọng không, hay cần custom interval function?
- Lỗi HTTP được biểu diễn là response hay exception? Classifier có nhận ra `429/503` không?
- Có **per-attempt timeout** và **total deadline** riêng không?
- Retry của thư viện có nằm **bên ngoài hay bên trong `@Transactional`**? Không lặp cả transaction với side effect chưa có idempotency.
- Có retry nào đã được bật ở HTTP transport, Spring Cloud Gateway hoặc service mesh không?
- Async/reactive retry có dùng scheduler không-blocking và hỗ trợ cancellation không?

Ví dụ một annotation `@Retryable` có thể tự retry khi method ném exception, nhưng nếu method thực hiện `POST` không idempotent, annotation **không thể tự biến side effect thành an toàn**. Đừng annotate toàn bộ service rồi coi mọi lỗi runtime là transient. Cần predicate/exception policy cụ thể và giới hạn thời gian chung với caller.

### 14.3. Transaction và retry phải được đặt đúng chỗ

Nếu một transaction DB nội bộ thất bại vì optimistic conflict, retry cả transaction có thể phù hợp khi logic được thiết kế để đọc lại state và tránh tác động ngoài; nhưng đó là quyết định **khác** với retry một HTTP POST đã phát hành đến dịch vụ ngoài.

Ví dụ nguy hiểm:

~~~text
@Transactional placeOrder():
    insert order vào DB
    gọi chargePayment() bên ngoài
    một lỗi SQL khiến transaction rollback
    retry toàn bộ placeOrder()

Nếu chargePayment() đã thành công, lần retry có thể thu tiền lần hai.
~~~

Giải pháp có thể gồm transactional outbox, saga, key idempotency cho payment provider, đối soát trạng thái và ranh giới transaction phù hợp. **Backoff không sửa được thiết kế transaction/side effect sai.**

## 15. API server cần hỗ trợ client retry văn minh

Không chỉ client phải có trách nhiệm. Server có thể giảm retry storm bằng cách:

- Trả `429 Too Many Requests` khi vượt quota thay vì cố nhận vô hạn.
- Trả `503 Service Unavailable` và `Retry-After` khi có thời gian phục hồi hợp lý.
- Công bố idempotency contract cho POST có side effect quan trọng.
- Tạo resource monitor cho tác vụ nền, giúp client không cần retry POST để hỏi tiến độ.
- Công bố mã lỗi ổn định giúp classifier biết lỗi nào không thể tự hết.
- Có quota/concurrency limit và cơ chế backpressure ở server/gateway.
- Trả `201`/`202`/`200` đúng nghĩa, không dùng `200 {"success":false}` cho lỗi cần phân nhánh theo HTTP.

### 15.1. Ví dụ 429 bằng Spring MVC

~~~java
import java.time.Duration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RateLimitAdvice {
    @ExceptionHandler(QuotaExceededException.class)
    public ResponseEntity<ProblemDetail> rateLimited(
            QuotaExceededException exception) {
        // Hệ thống quota xác định số giây chờ hợp lệ.
        Duration wait = exception.retryAfter();
        long seconds = wait.isNegative() || wait.isZero()
            ? 1L
            : Math.max(1L,
                wait.getSeconds() + (wait.getNano() > 0 ? 1L : 0L));

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.TOO_MANY_REQUESTS);
        problem.setTitle("Too many requests");
        problem.setDetail(
            "Giảm tần suất yêu cầu và thử lại sau thời gian được chỉ định.");
        problem.setProperty("code", "RATE_LIMITED");

        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
            .header(HttpHeaders.RETRY_AFTER, Long.toString(seconds))
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }
}

// Exception nghiệp vụ minh họa, cần được phát bởi quota layer.
class QuotaExceededException extends RuntimeException {
    private final Duration retryAfter;

    QuotaExceededException(Duration retryAfter) {
        this.retryAfter = retryAfter;
    }

    Duration retryAfter() {
        return retryAfter;
    }
}
~~~

Code là minh họa cấu trúc HTTP. Trong production, quota layer phải tính `retryAfter` từ giới hạn thực tế, bảo vệ khỏi giá trị cực lớn và áp dụng kiểm soát theo tenant/user/IP hoặc operation tùy chính sách. Ví dụ làm **tròn lên** số giây để không đề nghị client retry sớm hơn khi duration có phần lẻ. Một chính sách production cần kiểm tra overflow, giới hạn số giây tối đa và hành vi khi không thể dự đoán lúc quota sẽ mở lại.

### 15.2. `202 Accepted` là chuyển sang polling, không phải tiếp tục retry tạo job

Ví dụ:

~~~http
POST /v1/report-jobs HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: report-2026-11-cus82
Content-Type: application/json

{"type":"monthly-orders","month":"2026-10"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_419
Content-Type: application/json
Retry-After: 3

{
  "id": "op_419",
  "status": "QUEUED",
  "links": {"self": "/v1/operations/op_419"}
}
~~~

Một client đúng sẽ:

1. **Dừng retry POST** vì server đã nhận công việc.
2. Lưu URI operation theo hợp đồng.
3. `GET /v1/operations/op_419` theo **polling policy riêng**, có backoff/`Retry-After` nếu API quy định.
4. Dừng polling khi `SUCCEEDED`, `FAILED` hoặc `CANCELLED`; không tự tạo job khác chỉ vì thất bại.

`Retry-After` trên `202` trong ví dụ là **gợi ý polling theo hợp đồng cụ thể**, không có nghĩa phải gửi lại POST sau 3 giây. Đây là lỗi client phổ biến khi dùng chung một bộ retry cho tất cả response không phải `200`.

### 15.3. Trường hợp lỗi khiến client cần đối soát, không retry ngay

Nếu `POST /payments` bị read timeout, có thể thanh toán đã được thực hiện. Khi có API tra cứu trạng thái theo idempotency key hoặc payment operation ID, client nên đối soát theo chính sách trước khi tạo yêu cầu khác. Với giao dịch tài chính, hành vi retry cần đáp ứng quy định nghiệp vụ và cơ chế chống trùng của nhà cung cấp; không áp dụng mã mẫu retry tùy tiện.

## 16. Tài liệu OpenAPI: mô tả giới hạn và Retry-After

OpenAPI nên mô tả các status và header để client sinh ra có đủ thông tin:

~~~yaml
openapi: 3.1.0
info:
  title: Report Job API
  version: 1.0.0
paths:
  /v1/report-jobs:
    post:
      summary: Tiếp nhận yêu cầu xuất báo cáo
      description: |
        Khi request được chấp nhận, trả 202 với Location
        đến operation monitor. Client không POST lại để hỏi tiến độ.
        Cùng Idempotency-Key và cùng payload trong thời gian giữ khóa
        phải tham chiếu cùng logical operation theo hợp đồng.
        429/503 có thể kèm Retry-After; client chỉ retry khi còn
        deadline, cùng key/body và nằm trong số attempt được phép.
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 8
            maxLength: 128
          description: Khóa chống trùng trong phạm vi caller và thao tác
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [type, month]
              additionalProperties: false
              properties:
                type: {type: string, enum: [monthly-orders]}
                month:
                  type: string
                  pattern: '^[0-9]{4}-[0-9]{2}$'
      responses:
        '202':
          description: Công việc đã được tiếp nhận, chưa hoàn tất
          headers:
            Location:
              required: true
              description: Operation monitor, không phải file kết quả
              schema: {type: string, format: uri}
            Retry-After:
              description: |
                Gợi ý thời gian chờ trước khi GET operation,
                theo quy ước polling của API này.
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '400':
          description: Request không hợp lệ
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '409':
          description: Idempotency key dùng lại với payload khác
        '422':
          description: Dữ liệu hợp cú pháp nhưng không xử lý được
        '429':
          description: Quá giới hạn; xem Retry-After nếu có
          headers:
            Retry-After:
              description: Số giây hoặc HTTP-date
              schema: {type: string}
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '503':
          description: Dịch vụ tạm không thể nhận thêm công việc
          headers:
            Retry-After:
              description: Số giây hoặc HTTP-date nếu có
              schema: {type: string}
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    Operation:
      type: object
      required: [id, status]
      properties:
        id: {type: string}
        status:
          type: string
          enum: [QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED]
        links:
          type: object
          additionalProperties: {type: string}
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

OpenAPI **không có một trường chuẩn duy nhất tự buộc mọi SDK thực thi maxAttempts, jitter và deadline đúng như thiết kế**. Các quy tắc retry thường nằm trong `description`, profile SDK, hướng dẫn tích hợp hoặc extension có tên riêng của tổ chức. Nếu dùng vendor extension như `x-retry-policy`, phải nói rõ nó **không phải** ngữ nghĩa HTTP/OpenAPI bắt buộc, và tooling chỉ hiểu nếu được cài đặt để đọc extension đó.

Tài liệu nên ghi cụ thể: phương thức nào được retry, lỗi nào tạm thời, retention của Idempotency-Key, thời gian/giới hạn retry khuyến nghị, ý nghĩa `Retry-After` và cách đối soát sau timeout. Việc chỉ định nghĩa `429` trong OpenAPI không tạo ra rate limiter hoặc retry client.

## 17. Quan sát: đo thành công của logical operation, không chỉ attempt

Nếu chỉ đo “số response 200 sau retry”, có thể kết luận sai rằng retry cải thiện hệ thống, trong khi tổng request tăng gấp ba và latency p99 xấu đi.

### 17.1. Các metric nên có

| Metric | Ý nghĩa | Cảnh báo cần quan sát |
|---|---|---|
| `logical_operations_total` | Số yêu cầu người dùng/tác vụ logic, **không** tính các attempt retry | Lưu lượng nghiệp vụ gốc |
| `http_attempts_total` | Tổng lượt gửi HTTP tới dependency | Tăng nhanh hơn logical operations |
| `retry_attempts_total` | Số lượt gửi lại sau attempt đầu | Retry storm hoặc lỗi tạm |
| `retry_attempts_per_operation` | Phân bố số lần retry một operation | MaxAttempts thường xuyên bị chạm |
| `retry_success_after_failure` | Tỷ lệ thao tác phục hồi được sau lỗi tạm | Xem chi phí so với lợi ích |
| `retry_exhausted_total` | Số lần dừng vì hết lượt | Lỗi kéo dài hoặc cấu hình không phù hợp |
| `retry_budget_exhausted_total` | Số lần dừng vì hết deadline | Latency tail, ngân sách thiếu |
| `retry_suppressed_total{reason}` | Dừng vì non-retryable, quota, breaker, cancellation... | Thay đổi loại lỗi |
| `retry_after_wait_seconds` | Delay do server yêu cầu | Dependency đang rate-limit hoặc quá tải |
| `logical_operation_latency` | Thời gian **end-to-end** gồm attempt và chờ | p95/p99 cao dù từng attempt nhanh |
| `downstream_429_503_rate` | Tỷ lệ throttling/unavailable | Kế hoạch capacity/load shedding |
| `idempotency_replay_total` | Số lần server nhận lại cùng logical request | Số lần network hoặc client retry |

Theo dõi **retry amplification**:

\[
A = \frac{\text{tổng số attempt}}{\text{số logical operation}}
\]

Nếu có 1.000 logical operations nhưng 2.700 attempts, `A=2,7`. Đây không tự chứng minh sai: có thể do dependency tạm lỗi. Tuy nhiên cần so với latency, error rate, tải hệ thống và số retry giúp phục hồi thành công.

### 17.2. Tracing và logging

Một trace có thể có:

~~~text
logical_operation_id = op_419
idempotency_key_fingerprint = hash_or_redacted_id
attempt = 1    status = 503    elapsed = 120ms
retry_delay = 2s    source = Retry-After
attempt = 2    status = 202    elapsed = 210ms
logical_duration = 2.33s
outcome = ACCEPTED
~~~

Chỉ dùng giá trị đã redacted hoặc fingerprint không thể đảo ngược khi ghi idempotency key và định danh nhạy cảm; không đưa bearer token, thẻ thanh toán hay nguyên request body vào log. Nếu trace qua nhiều tầng, cần một logical ID để phân biệt những attempt thuộc cùng hoạt động với các hoạt động mới.

**Không gắn raw URL, user ID hoặc idempotency key làm nhãn metric có cardinality cao.** Nhóm theo endpoint template, status class, dependency và nguyên nhân retry; dùng trace/log có kiểm soát để điều tra từng trường hợp.

## 18. Kiểm thử một retry policy không phụ thuộc thời gian thật

Một test dùng `Thread.sleep(1000)` nhiều lần vừa chậm vừa dễ flake khi CI bị tải. Nên thiết kế retry engine với những thành phần có thể tiêm:

~~~text
RetryEngine
  - Clock/Ticker: đo thời gian và deadline
  - Sleeper/Scheduler: ghi nhận khoảng chờ, không ngủ thật
  - RandomSource: trả số giả ngẫu nhiên cố định trong test
  - HttpTransport: trả status hoặc ném lỗi theo kịch bản
  - RetryPolicy: maxAttempts, delay, timeouts, budget, classifier
~~~

Java `ReportJobClient` ở mục 13 giúp minh họa thuật toán nhưng dùng trực tiếp `System.nanoTime()`, `ThreadLocalRandom` và `Thread.sleep`, nên **muốn unit test xác định** cần tách các phần đó thành dependency như trên. Integration tests có thể dùng HTTP mock server và DB/operation store thật để kiểm tra ngữ nghĩa idempotency.

### 18.1. Ma trận kiểm thử classifier

| Trường hợp | Kỳ vọng |
|---|---|
| Attempt đầu trả `201 Created` | Trả ngay, 1 attempt, không sleep |
| Attempt đầu trả `202 Accepted` | Dừng retry POST; theo dõi monitor bằng luồng riêng |
| `400`, `401`, `403`, `422` | Không retry request y nguyên |
| `409` không có hợp đồng transient | Không retry mù |
| `412`/`428` | Không bỏ precondition để retry |
| `408`/`429`/`502`/`503`/`504` | Retry khi policy và budget cho phép |
| `500` không được đánh dấu transient | Không retry theo ví dụ |
| Read timeout sau POST có key | Có thể retry cùng key/body theo hợp đồng |
| Read timeout sau POST **không** có key/guarantee | Không retry tự động; đối soát |
| SSL certificate/hostname error | Không retry |
| Cancellation trước lượt thứ hai | Không ngủ/không gửi thêm |
| `429` có `Retry-After` lớn hơn budget | Không retry |
| `429` có invalid Retry-After | Dùng jitter fallback, có metric lỗi header |
| Retry bucket rỗng hoặc breaker mở | Không gửi attempt mới |

### 18.2. Ma trận kiểm thử backoff/jitter

| Input | Kết quả cần kiểm |
|---|---|
| Base 200 ms, cap 3.000 ms, failureIndex 1..6 | `C_k` lần lượt 200, 400, 800, 1600, 3000, 3000 ms |
| Full jitter, random trả 0 | Delay bằng 0, nhưng phải không vi phạm `Retry-After` |
| Full jitter, random trả giá trị lớn nhất cho phép | Delay không vượt `C_k` |
| Equal jitter với cap 800 ms | Delay nằm trong khoảng 400–800 ms |
| Decorrelated jitter | Delay phụ thuộc previous delay, vẫn không vượt max |
| Base gần max hoặc nhiều attempts | Không bị overflow hoặc số âm |
| Config base/max/attempts không hợp lệ | Từ chối ngay khi khởi tạo |
| Các client dùng nguồn random khác nhau | Lịch retry có phân tán; kiểm thử tải thống kê |

**Kiểm thử ngẫu nhiên:** unit test không nên mong chính xác một số jitter thật. Tiêm random giả để kiểm cận trên/dưới và công thức; dùng test thống kê riêng khi muốn quan sát phân phối.

### 18.3. Ma trận kiểm thử ngân sách thời gian

| Kịch bản | Kỳ vọng |
|---|---|
| `maxAttempts=1` | Không retry, bất kể lỗi tạm |
| `maxAttempts=4` và mọi attempt đều lỗi nhanh | Tối đa 4 lượt gửi |
| Per-attempt timeout 1,5s, remaining 0,4s | Attempt timeout không vượt 0,4s nếu vẫn đủ ngưỡng hữu ích |
| Remaining chỉ còn 30 ms, minUseful 100 ms | Không gửi attempt mới |
| Backoff dự kiến 0,8s, remaining 0,5s | Không ngủ rồi gửi sau deadline |
| Retry-After 5s, remaining 2s | Dừng sớm, không tự rút ngắn hint thành 2s |
| Time budget 6s, client liên tục gặp 503 | Tổng thời gian bị giới hạn, cho phép overhead nhỏ đã đo |
| Đồng hồ lịch bị chỉnh lùi | Deadline vẫn dựa trên monotonic elapsed time |
| Interrupt/cancel lúc đang chờ | Dừng retry, giữ/tuyên truyền cancellation |
| Caller truyền deadline đã gần hết | Downstream không cấp lại full budget |

Với đồng hồ giả, cần mô phỏng cả thời gian **attempt** và thời gian **sleep**; chỉ tăng thời gian khi sleep sẽ bỏ sót các attempt tiêu hết ngân sách.

### 18.4. Kiểm thử Retry-After

~~~text
Header: Retry-After: 3
Now:    bất kỳ
Expect: serverWait = 3s

Header: Retry-After: Wed, 18 Nov 2026 09:00:20 GMT
Now:    2026-11-18T09:00:15Z
Expect: serverWait ~ 5s

Header: Retry-After: Wed, 18 Nov 2026 09:00:10 GMT
Now:    2026-11-18T09:00:15Z
Expect: serverWait = 0s rồi áp dụng local backoff

Header: Retry-After: negative-or-garbage
Expect: fallback jitter + ghi metric invalid header
~~~

Khi API hoặc proxy bổ sung `Date` header, có thể test lệch đồng hồ server/client. Không để header có ngày rất xa khiến thread ngủ trong nhiều ngày; với interactive request, policy phải dừng theo deadline.

### 18.5. Test end-to-end về idempotency và retry lặp

1. Server nhận `POST /orders` với key K và lưu đơn; mock network **đánh rơi response 201**.
2. Client retry đúng K và payload, trong budget.
3. Server trả cùng đơn/Location hoặc response tương đương theo contract.
4. Assert có đúng **một đơn** trong database và một logical business effect.
5. Gửi K với payload khác: phải nhận lỗi xung đột theo policy, không tạo đơn mới.
6. Chạy hai request K đồng thời: kiểm chứng unique constraint/transaction chống race.
7. Cho worker nhận lại message: không phát sinh hai tác động nghiệp vụ.
8. Kiểm tra retention: sau khi key hết hạn, client hiểu nguy cơ tạo hành động mới.

Đừng chỉ test client gửi đúng ba lần. Một retry loop có thể “đúng số lượt” nhưng vẫn tạo ba đơn nếu server không có idempotency bền vững.

## 19. Bài thực hành: phục hồi lỗi khi tạo báo cáo

### 19.1. Đề bài

Ứng dụng Java/Spring gọi một REST API ngoài để khởi tạo báo cáo. Hợp đồng:

- `POST /v1/report-jobs` nhận JSON, yêu cầu `Idempotency-Key`.
- Thành công trả `202 Accepted` với `Location: /v1/operations/{id}`.
- Server đôi khi trả `429` hoặc `503` có `Retry-After`.
- Đôi khi kết nối bị reset sau khi server đã tiếp nhận job.
- Mobile app chỉ chờ tối đa **7 giây** cho bước tiếp nhận công việc; tạo báo cáo thực tế kéo dài nhiều phút và được theo dõi riêng.
- Có hàng nghìn client cùng dùng API trong giờ cao điểm.

**Yêu cầu của người học:**

1. Chọn chính sách retry: `maxAttempts`, `baseDelay`, `maxDelay`, jitter, `perAttemptTimeout`, `totalBudget=7s` và ngưỡng minimum useful attempt; giải thích đánh đổi.
2. Phân loại `202`, `400`, `409`, `429`, `500`, `502`, `503`, `504` và reset/timeout thành retry hoặc không retry.
3. Viết mã giả vòng retry dùng deadline và một key **không đổi** qua attempts.
4. Cho ví dụ lỗi `503 Retry-After: 5` khi chỉ còn 4 giây budget: client phải làm gì, vì sao không rút delay xuống 4 giây?
5. Thiết kế cách dừng retry POST khi nhận `202` và bắt đầu GET operation monitor với **ngân sách polling riêng**.
6. Giải thích cách chống retry storm khi 3.000 client cùng bị `503`.
7. Viết một `RetryPolicy` có thể cấu hình và unit tests với fake clock/sleeper/random.
8. Đề xuất service-side idempotency store và cách xử lý cùng key/payload đồng thời.
9. Viết OpenAPI rút gọn cho `202`, `429`, `503`, `Retry-After` và header idempotency.
10. Vẽ sơ đồ sequence của một lần tạo báo cáo thành công sau retry, và một lần dừng do budget hết.
11. Đề xuất metric/phép đo để biết retry có giúp giảm lỗi người dùng hay tạo thêm tải.

### 19.2. Một phương án chính sách tham khảo

| Giá trị | Đề xuất minh họa | Lý do |
|---|---:|---|
| `maxAttempts` | 4 | Một lượt đầu, tối đa ba retry |
| `totalBudget` | 7 giây | Ràng buộc bởi trải nghiệm người dùng |
| `perAttemptTimeout` | 2 giây | Giới hạn attempt, co lại theo remaining |
| `baseDelay` | 200 ms | Không retry ngay cùng thời điểm |
| `maxDelay` | 1,6 giây | Có trần để không kéo dài quá mức |
| Jitter | Full | Phân tán 3.000 client |
| `minUsefulAttempt` | 100 ms | Tránh attempt vô ích sát deadline |
| Retry statuses | 408, 429, 502, 503, 504 | Chỉ khi retry-safe |
| Idempotency | Key mới mỗi job, cố định mọi attempt | Không tạo hai job do mất response |

Giá trị trên phải được **đo lại**: nếu latency thông thường của API là 2,5 giây, timeout 2 giây có thể gây timeout giả và tăng tải. Nếu quota nghiêm ngặt hoặc server thường trả Retry-After 10 giây, client nên dừng sớm và chuyển sang trạng thái chờ/tra cứu, không ép gọi lại trong 7 giây.

### 19.3. Bài tính thời gian

**Tình huống A:** `totalBudget=4s`, `maxAttempts=5`. Attempt 1 tiêu 0,9s, jitter 0,2s, attempt 2 tiêu 0,9s. Khi attempt 2 trả `429 Retry-After: 3`, tổng đã dùng:

\[
0.9 + 0.2 + 0.9 = 2.0\;s
\]

Còn **2,0s**, nhưng server yêu cầu chờ **3,0s**. **Đáp án:** không retry lần ba trong logical operation hiện tại; phản hồi lỗi/giới hạn cho tầng gọi và không gửi trước mốc server đề nghị.

**Tình huống B:** `maxAttempts=5`, `perAttemptTimeout=2s`, exponential delay không jitter với base 200ms, cap 3s. Nếu năm attempt đều timeout, thời gian tối đa theo lịch là:

\[
5 \times 2s + (0.2+0.4+0.8+1.6)s=13s
\]

Nếu business chỉ cho 6s, **maxAttempts=5 chưa đủ** để bảo đảm thời gian; cần total deadline, attempt timeout co lại và dừng trước khi lên lịch retry vượt budget.

**Tình huống C:** 3.000 client dùng backoff cố định 1s rồi cùng retry. Họ vẫn tạo đỉnh khoảng **3.000 request** tại thời điểm +1s. Dùng full jitter trải lịch trong một khoảng, kết hợp quota/circuit breaker. **Không được** cho rằng chỉ thêm jitter đã bảo đảm backend không quá tải; phải đo số request, concurrency và SLO.

### 19.4. Kỳ vọng bài giải

Một bài đạt yêu cầu không chỉ ghi công thức `2^n`. Bài cần:

- Chứng minh **không gửi POST mới khi đã 202**.
- Nêu rõ idempotency key và payload không thay đổi khi retry.
- Kiểm tra cả maxAttempts và deadline, kể cả thời gian chờ.
- Tôn trọng `Retry-After` thay vì chỉ dùng delay cục bộ.
- Chặn retry 4xx không phù hợp và lỗi TLS/config.
- Có xử lý cancellation, concurrency và tải nhiều client.
- Có test server-side dedupe để chứng minh không có tác động trùng.

## 20. Những phản mẫu thường gặp

| Phản mẫu | Hệ quả | Thiết kế thay thế |
|---|---|---|
| Retry ngay lập tức khi nhận 503 | Làm quá tải nặng hơn | Exponential backoff + jitter + quota |
| Chỉ exponential, không jitter | Client thức dậy đồng loạt | Full/equal/decorrelated jitter |
| Dùng `while(true)` cho retry | Không có điều kiện dừng, treo vô hạn | MaxAttempts và total deadline |
| Đếm maxRetries như maxAttempts | Lệch số request thật | Ghi rõ attempts gồm lượt đầu |
| Có maxAttempts nhưng không giới hạn mỗi attempt | Một lần gọi có thể treo quá lâu | Per-attempt timeout |
| Có timeout từng attempt nhưng không có total budget | Tổng thời gian có thể vượt SLO nhiều lần | Deadline chung gồm cả backoff |
| Sleep hết Retry-After dù deadline đã hết | Làm request người dùng treo vô ích | Dừng khi hint vượt remaining budget |
| Cắt Retry-After từ 30s xuống maxDelay 2s | Gửi lại sớm hơn server yêu cầu | Tôn trọng hint hoặc dừng |
| Retry mọi 500/4xx và mọi IOException | Retry lỗi vĩnh viễn/cấu hình, tăng tải | Classifier có mục tiêu |
| Retry POST với key mới mỗi lượt | Có thể tạo đơn/thu tiền lặp | Giữ key và payload cùng logical operation |
| Retry POST khi đã nhận 202 | Tạo tác vụ trùng hoặc lãng phí request | GET operation monitor |
| Gateway, SDK và service đều retry ngầm | Request amplification | Phối hợp vị trí retry và deadline |
| Retry cả transaction chứa side effect bên ngoài | Có thể gọi thanh toán lặp | Outbox, saga và idempotency |
| Dùng If-Match như idempotency key | Không phân biệt request lặp với stale state | Dùng cơ chế đúng cho từng vấn đề |
| Dùng Thread.sleep trong reactive event loop | Block luồng và giảm throughput | Scheduler non-blocking/cancellation |
| Test dùng sleep thật và không đo thời gian attempt | Test chậm, flaky, bỏ sót over-budget | Fake clock/sleeper, test tổng elapsed |
| Ghi token/idempotency key đầy đủ vào metric | Rủi ro bí mật và cardinality | Redaction, low-cardinality metrics |
| Chỉ đo success rate từng attempt | Có thể che retry storm và latency cao | Đo logical operations + amplification |

## 21. Bộ câu hỏi tự kiểm tra

**1. `maxAttempts=4` nghĩa là 4 hay 5 lần gửi?** Trong hợp đồng bài này là **4 lần tổng cộng**, gồm lần đầu và tối đa ba retry. Không suy ra điều tương tự cho mọi thư viện mà chưa đọc quy ước của thư viện.

**2. Tại sao cần jitter nếu đã dùng exponential backoff?** Vì các client gặp lỗi cùng lúc có thể cùng dùng lịch backoff giống nhau; jitter giúp phân tán thời điểm gửi lại và giảm đỉnh tải đồng bộ.

**3. Full jitter có phải luôn tốt nhất không?** Không. Nó phân tán mạnh nhưng có thể chọn delay gần 0. Chọn theo SLO, tín hiệu server, tải và kết quả thử nghiệm; equal/decorrelated jitter là những lựa chọn có đánh đổi khác.

**4. Khi `Retry-After=8s` mà deadline còn 3s, nên ngủ 3s rồi thử lại?** Không. Không còn đủ ngân sách để chờ đúng hint và gửi request sau đó; dừng logical retry thay vì gửi sớm hơn yêu cầu server.

**5. Một request POST bị timeout có nghĩa là server chưa xử lý?** Không. Server có thể đã commit và chỉ mất response. Cần idempotency hoặc cơ chế đối soát, không retry mù.

**6. `202 Accepted` có nên đưa vào danh sách status retry?** Không đối với **POST khởi tạo công việc** đã được tiếp nhận; client chuyển sang theo dõi resource monitor. Nếu API dùng `Retry-After` trên 202 làm gợi ý poll, đó là hợp đồng polling riêng.

**7. Có thể retry `409 Conflict` không?** Không mặc định. Phải xem mã lỗi và trạng thái nghiệp vụ; chỉ retry khi contract nói rõ loại conflict nào là tạm và cách xử lý.

**8. PUT có tính idempotent, vậy có cần `If-Match` không?** Khi cần bảo vệ thay đổi của các client khác, **có thể cần**. Tính idempotent không ngăn stale PUT ghi đè giá trị mới của người khác.

**9. Vì sao timeout mỗi attempt chưa đủ?** Vì tổng số attempt và các khoảng sleep có thể khiến logical operation vượt thời gian cho phép. Cần deadline chung và chỉ cấp thời gian còn lại cho attempt tiếp theo.

**10. Nếu ba tầng cùng tối đa ba attempts, có thể có bao nhiêu lượt tới tầng cuối?** Trong trường hợp xấu là **27**, nếu mỗi attempt của tầng trên gây đủ ba attempts ở tầng dưới. Thực tế còn phụ thuộc lỗi và các điều kiện dừng.

**11. Đo “retry thành công” thế nào cho đúng?** Đo trên logical operation, gồm toàn bộ latency, số attempts, chi phí và tác động nghiệp vụ; không chỉ đo status của request cuối cùng.

**12. Nếu user đã hủy, client có nên tiếp tục retry trong background?** Không tự động. Phải truyền cancellation tới retry scheduler và dừng gửi mới; nếu server có thể đã nhận công việc, cần cơ chế đối soát/hủy nghiệp vụ theo hợp đồng.

## 22. Checklist trước khi đưa retry policy vào production

### Khả năng retry an toàn

- [ ] Xác định endpoint/method và **tác động nghiệp vụ** thực sự retry-safe.
- [ ] POST/PATCH có side effect được bảo vệ bằng idempotency hoặc cơ chế tương đương khi retry.
- [ ] Key và request body không thay đổi giữa các attempts của cùng logical operation.
- [ ] Lỗi timeout sau khi gửi có hướng đối soát kết quả, không giả định request chưa chạy.
- [ ] `202` dừng retry tạo job và chuyển sang monitor.

### Thời gian và số lượt

- [ ] `maxAttempts` được định nghĩa rõ **có tính lần đầu**.
- [ ] Có `perAttemptTimeout`, `totalBudget`/deadline và minimum useful attempt.
- [ ] Tính budget bao gồm cả attempt, backoff và overhead; dùng monotonic elapsed time.
- [ ] Không ngủ/gửi khi delay vượt remaining budget.
- [ ] Có cancellation từ request cha hoặc người dùng và không retry vô hạn.
- [ ] Có backoff có trần, jitter và số học chống overflow.

### HTTP, server hints và tải

- [ ] Có classifier cho status/lỗi transport; không retry 4xx/5xx tùy tiện.
- [ ] Parse cả delay-seconds và HTTP-date của `Retry-After`.
- [ ] Không cắt ngắn Retry-After để gửi sớm hơn server đề nghị.
- [ ] Có giới hạn retry capacity/rate/quota, circuit breaker/bulkhead khi phù hợp.
- [ ] Đã kiểm tra retry đang bật trong SDK, proxy, mesh, gateway và worker.
- [ ] Hạn chế request amplification, không reset deadline ở từng tầng.

### Contract, kiểm thử và vận hành

- [ ] OpenAPI mô tả status, header, idempotency, Retry-After và cách theo dõi operation.
- [ ] Unit test có fake clock/sleeper/random, assert số lượt và tổng thời gian.
- [ ] Integration test mất response sau commit, key trùng đồng thời và worker redelivery.
- [ ] Load test nhiều client cùng nhận 429/503 để quan sát thundering herd và tải thực.
- [ ] Metric tách logical operation, attempt, retry, deadline exhausted và amplification.
- [ ] Log/trace có correlation ID an toàn, không lộ credential hoặc key nhạy cảm.

## 23. Ghi nhớ

Một chính sách retry đáng tin cậy không chỉ là **“thử lại ba lần”**. Nó phải trả lời **có được retry không**, **nên chờ bao lâu**, **lần gửi tiếp theo có còn trong ngân sách không** và **side effect có bị lặp không**.

Hãy bắt đầu từ ngữ nghĩa HTTP và hợp đồng **idempotency**, phân loại rõ transient failure, dùng **exponential backoff có trần và jitter** để tránh đồng bộ tải, tôn trọng `Retry-After`, giới hạn **maxAttempts và total deadline** cùng nhau, rồi đo hiệu quả trên **logical operations**. Với Java/Spring, thư viện chỉ là công cụ thực thi; sự an toàn đến từ ranh giới retry đúng, bảo đảm nghiệp vụ ở server và các phép thử mô phỏng timeout, cạnh tranh và quá tải.
