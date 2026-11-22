# Ngăn bão retry và khuếch đại tải qua nhiều tầng

## 1. Bối cảnh và mục tiêu

Trong kiến trúc microservices, một yêu cầu của người dùng thường đi qua nhiều dịch vụ đồng bộ trước khi trả kết quả. Khi một dịch vụ chậm hoặc tạm thời không khả dụng, gọi lại (retry) đôi khi giúp vượt qua lỗi ngắn hạn. Nhưng nếu API Gateway, service A, service B, HTTP client và proxy đều tự retry, mỗi lỗi có thể tạo thêm hàng chục lời gọi. Chính lưu lượng bổ sung này khiến dịch vụ đang gặp sự cố càng khó hồi phục.

**Retry storm (bão retry)** là hiện tượng nhiều client đồng loạt lặp lại yêu cầu, thường cùng thời điểm, tạo một vòng phản hồi khiến hệ thống quá tải. **Retry amplification (khuếch đại bởi retry)** là số lần gọi được nhân lên khi nhiều tầng lặp lại cùng một chuỗi tác vụ.

Mục tiêu của bài là thiết kế retry như một phần của ngân sách tài nguyên và thời gian của toàn bộ luồng, thay vì bật tính năng retry độc lập ở từng thư viện.

Sau bài học, người đọc có thể:
- Giải thích vì sao retry lồng nhau tạo tải nhân theo cấp số nhân.
- Phân biệt lỗi có thể retry, lỗi không nên retry và thao tác chưa chắc an toàn để lặp lại.
- Thiết kế retry có giới hạn bằng deadline, timeout, retry budget, exponential backoff và jitter.
- Kết hợp retry với circuit breaker, bulkhead, giới hạn đồng thời và cơ chế giảm tải.
- Đo mức khuếch đại thực tế, thử nghiệm sự cố và ứng phó khi bão retry xảy ra.

## 2. Tại sao một lời gọi có thể biến thành 27 lời gọi?

Giả sử luồng xử lý đồng bộ như sau:

```text
Người dùng
    |
API Gateway --(gọi Order Service)--> Order Service
                                         |
                                         +--(gọi Inventory Service)--> Inventory Service
                                                                             |
                                                                             +--(gọi DB)--> Database
```

Mỗi trong ba tầng Gateway → Order, Order → Inventory, Inventory → DB đều cấu hình `maxAttempts = 3`, nghĩa là **tối đa 3 lần thử tổng cộng, kể cả lần đầu**, không phải 3 lần retry cộng với lần đầu.

Nếu Database gặp lỗi và mọi tầng đều thất bại theo cách kích hoạt retry:

| Tầng | Số lần thử tối đa cho mỗi lời gọi từ tầng trên |
| --- | ---: |
| Gateway gọi Order | 3 |
| Order gọi Inventory | 3 |
| Inventory gọi DB | 3 |
| **Số lời gọi DB tối đa trên một yêu cầu đầu vào** | **3 × 3 × 3 = 27** |

Khi 1.000 yêu cầu đầu vào mỗi giây gặp cùng kiểu lỗi, về lý thuyết có thể sinh tới 27.000 lần gọi DB mỗi giây. Đây là **cận trên của kịch bản mọi retry đều được thực hiện**, không phải dự báo cố định: deadline, circuit breaker, lỗi bị chặn sớm hoặc trạng thái thực tế có thể làm con số thấp hơn.

Với `L` tầng độc lập, mỗi tầng cho phép `Aᵢ` lần thử, cận trên của số lời gọi ở tầng cuối trong một nhánh là:

```text
MaxLeafCallsPerRequest = A1 × A2 × ... × AL

Ví dụ: 4 tầng, mỗi tầng 3 lần thử → 3^4 = 81 lần gọi tầng cuối.
```

Nếu nghiệp vụ vốn cần gọi song song nhiều dịch vụ (fan-out), lưu lượng cơ sở đã lớn hơn một. Cần tách **fan-out hợp lệ của nghiệp vụ** khỏi số lời gọi bổ sung bởi retry. Không được gán mọi lời gọi xuống tầng dưới là retry.

Một nguyên nhân gây hiểu nhầm khác là cấu hình `maxRetries = 3` thường có nghĩa **1 lần đầu + 3 lần retry = 4 lần thử**. Khi đọc cấu hình thư viện, luôn xác minh tên tham số và cách tính số lần thử.

## 3. Vòng xoáy quá tải hình thành như thế nào?

Diễn biến thường gặp:

1. Dịch vụ phụ thuộc bắt đầu chậm vì CPU, kết nối, pool, đĩa hoặc một sự cố mạng.
2. Thời gian chờ tăng; client timeout và gửi lại yêu cầu trong khi lời gọi trước có thể vẫn đang xử lý.
3. Retry làm tăng số request, số kết nối và số tác vụ xếp hàng, khiến dịch vụ phụ thuộc chậm hơn.
4. Nhiều client timeout hơn, dẫn tới nhiều retry hơn. Nếu mọi client có lịch retry giống nhau, chúng tạo các đợt tải đồng bộ.
5. Hàng đợi, thread pool, connection pool hoặc các service phía trên cũng cạn tài nguyên; lỗi lan qua nhiều tầng.

```text
Dịch vụ chậm
    ↓
Timeout / 503 tăng
    ↓
Client retry thêm
    ↓
Lưu lượng và số yêu cầu đang xử lý tăng
    ↓
Hàng đợi lâu hơn, hệ thống càng chậm
    └─────────────────── quay về Timeout / 503 tăng
```

Retry thành công đối với lỗi thoáng qua khi hệ thống còn dư công suất. Khi hệ thống đã bão hòa, retry có thể biến một suy giảm cục bộ thành **cascading failure** (lỗi dây chuyền).

Lỗi timeout đặc biệt khó: client không nhận được câu trả lời **không chứng minh** server chưa hoàn thành thao tác. Retry một lệnh thanh toán, tạo đơn hàng hoặc gửi thông báo có thể lặp tác dụng phụ nếu thiếu cơ chế chống trùng.

## 4. Nguyên tắc thiết kế: một chủ sở hữu retry cho một chuỗi đồng bộ

Với một đường gọi đồng bộ, chỉ định rõ **tầng nào được quyết định retry** và các tầng còn lại trả lỗi đủ thông tin cho tầng đó. Chủ sở hữu có thể là client gần nơi phát sinh lỗi, một lớp adapter tích hợp dịch vụ hoặc tầng điều phối có đầy đủ ngữ cảnh nghiệp vụ. Không có một vị trí cố định đúng cho mọi hệ thống.

Ví dụ một chính sách:

```text
API Gateway → Order Service → Inventory Service → Database
  không retry      retry tối đa 2 lần      không retry ở tầng DB client
                   cho lời gọi Inventory
```

Trong ví dụ này, tầng Order là chủ sở hữu retry của lời gọi Inventory. Các proxy, SDK và client bên trong không được lén thực hiện thêm retry cho cùng thao tác. Nếu Database có retry riêng cho lỗi giao dịch đặc thù, phải tính nó vào giới hạn chung hoặc tách rõ thành một thao tác khác với lý do được kiểm soát.

Đừng hiểu nguyên tắc “một chủ sở hữu” là cấm mọi retry trong toàn hệ thống. Mục tiêu là **tránh các vòng retry lồng nhau không có ngân sách chung**. Mỗi nhánh và loại thao tác có thể cần chiến lược khác nhau, nhưng phải biết số lần gọi tối đa ở cuối chuỗi.

Một bản thiết kế retry cần ghi rõ:

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Vị trí | Thành phần nào chịu trách nhiệm retry? |
| Điều kiện | Lỗi nào thật sự tạm thời, thao tác nào an toàn để gọi lại? |
| Giới hạn | Tối đa bao nhiêu lần thử và bao nhiêu retry bổ sung trong hệ thống? |
| Thời gian | Deadline tổng và timeout từng lần thử là bao nhiêu? |
| Nhịp độ | Backoff, jitter và `Retry-After` được xử lý ra sao? |
| Bảo vệ | Circuit breaker, concurrency limit, load shedding hoạt động ở đâu? |
| Quan sát | Ai đo retry count, retry ratio và tải khuếch đại? |

## 5. Chỉ retry khi đồng thời thỏa điều kiện kỹ thuật và nghiệp vụ

Quyết định retry phải xét **lỗi + loại thao tác + trạng thái hệ thống + thời gian còn lại**, không chỉ một mã HTTP.

| Tình huống | Hướng xử lý |
| --- | --- |
| Lỗi kết nối thoáng qua, DNS/transport tạm thời, kết nối bị reset | Có thể retry với giới hạn nếu thao tác an toàn và còn deadline. |
| HTTP 502/503/504 | Có thể retry có kiểm soát; nếu lỗi phổ biến hoặc upstream quá tải, phải giảm retry và mở breaker khi cần. |
| HTTP 429 | Tôn trọng `Retry-After` nếu có, đồng thời kiểm tra deadline và budget; không tự tạo đợt gọi dồn. |
| HTTP 500 | Không tự động coi mọi 500 là lỗi tạm thời; cần hợp đồng API và hiểu biết về tác dụng phụ. |
| HTTP 400/401/403/422 | Thường là lỗi đầu vào, xác thực, quyền hoặc nghiệp vụ; lặp nguyên yêu cầu sẽ không giải quyết. |
| HTTP 404 | Thường không retry; ngoại lệ eventual consistency phải được mô tả rõ ở API cụ thể. |
| HTTP 409 | Cần phân tích xung đột phiên bản/trạng thái; không retry mù cùng một lệnh. |
| Client timeout / mất phản hồi | Kết quả thực thi phía server là **không xác định**; chỉ retry nếu đã có an toàn idempotency. |
| Hệ thống phụ thuộc đã quá tải kéo dài | Ưu tiên fail fast, circuit breaker, admission control hoặc hàng đợi có giới hạn. |

**Idempotency** là khả năng lặp lại cùng một thao tác mà không làm thay đổi kết quả nghiệp vụ nhiều lần. `GET` đọc dữ liệu thường an toàn để retry; `PUT` hoặc `DELETE` có thể idempotent theo hợp đồng API; `POST` tạo tác dụng phụ chỉ nên retry khi ứng dụng thiết kế cơ chế chống trùng tương ứng. Đừng dựa vào phương thức HTTP mà bỏ qua triển khai thực tế.

Ví dụ thanh toán:

```http
POST /payments
Idempotency-Key: order-8472-payment-v1
Content-Type: application/json

{"orderId":"8472","amount":250000,"currency":"VND"}
```

Client giữ **cùng** `Idempotency-Key` cho các lần thử của **cùng một thao tác logic**, không phát sinh key mới mỗi lần retry. Server lưu trạng thái và kết quả theo key một cách bền vững, xử lý đồng thời an toàn; nếu yêu cầu đã thành công, lần lặp phải trả lại kết quả phù hợp thay vì thu tiền lần nữa. Phạm vi key, TTL và trường hợp cùng key nhưng payload khác cần được định nghĩa rõ. Chỉ thêm header ở client mà server không hỗ trợ thì chưa tạo ra idempotency.

## 6. Deadline và timeout: không cho phép mỗi tầng bắt đầu lại đồng hồ

**Timeout** giới hạn thời gian chờ của một lần gọi. **Deadline end-to-end** là thời điểm muộn nhất mà yêu cầu toàn luồng còn giá trị. Một luồng đã quá deadline không nên tạo retry mới dù số lần thử chưa hết.

Giả sử tổng ngân sách phản hồi là 800 ms. Nếu Gateway đã tiêu 200 ms, Order còn tối đa khoảng 600 ms cho công việc còn lại, không phải một hạn mức 800 ms mới. Khi Order gọi Inventory, nó phải chừa thời gian xử lý và trả kết quả về phía trên.

```text
Ngân sách tổng:                 800 ms
Đã tiêu ở các bước trước:      200 ms
Còn lại tại Order:             600 ms
Timeout gọi Inventory:         min(timeout cấu hình, thời gian còn lại)
Sau lần gọi + backoff:         tính lại thời gian còn lại trước khi retry
```

Thiết kế đúng cần:

- Ghi nhận deadline hoặc ngân sách còn lại tại ingress; truyền xuống các dịch vụ con bằng cơ chế được thống nhất. gRPC có khái niệm deadline; với HTTP thường cần header ứng dụng hoặc propagation được framework hỗ trợ.
- Dùng đồng hồ đơn điệu (monotonic clock) cho phép đo khoảng thời gian trong một tiến trình. Nếu truyền thời điểm tuyệt đối qua các máy, lưu ý lệch đồng hồ và giới hạn giá trị do client gửi.
- Đặt timeout kết nối, đọc, tổng lời gọi và thời gian xếp hàng phù hợp từng tầng. Timeout không nhất thiết hủy được tác vụ đã chạy ở server.
- Trước mỗi retry, xét thời gian còn lại, độ trễ chờ và thời gian hữu ích tối thiểu cho một lần thử. Nếu không đủ thì dừng.
- Không tạo các lời gọi “mồ côi” tiếp tục tốn tài nguyên sau khi phía gọi đã bỏ cuộc, nếu giao thức và thư viện cho phép hủy.

**Ví dụ sai:** 4 tầng, mỗi tầng tự chờ 2 giây và retry 3 lần, trong khi HTTP request của người dùng chỉ được phép hoàn thành trong 1 giây. Các lần thử sau không còn giá trị cho người dùng nhưng vẫn gây tải.

## 7. Exponential backoff và jitter: phân tán các lần thử

**Exponential backoff** tăng thời gian chờ giữa những lần retry, chẳng hạn cơ sở 100 ms rồi 200 ms, 400 ms…, có trần 800 ms. Nó giúp hệ thống phụ thuộc có thời gian hồi phục. Nhưng nếu hàng nghìn client gặp lỗi cùng lúc và tất cả chờ chính xác 100 ms, rồi 200 ms, chúng vẫn thức dậy đồng loạt (thundering herd).

**Jitter** thêm ngẫu nhiên để phân tán những lần thử. Với *full jitter*:

```text
retryIndex = 0 cho lần retry đầu tiên
cap = min(maxBackoff, baseBackoff × 2^retryIndex)
delay = random(0, cap)
```

Ví dụ Java 21 minh họa phép tính khoảng chờ, với `retryIndex` không âm:

```java
import java.util.concurrent.ThreadLocalRandom;

public final class BackoffPolicy {
    private BackoffPolicy() {}

    public static long fullJitterMillis(int retryIndex) {
        long baseMillis = 100L;
        long maxMillis = 800L;
        long exponential = baseMillis << Math.min(retryIndex, 20);
        long cap = Math.min(maxMillis, exponential);
        return ThreadLocalRandom.current().nextLong(cap + 1);
    }
}
```

Đây là hàm tính thời gian chờ, **không phải** toàn bộ chính sách retry. Trong ứng dụng reactive/non-blocking, hãy lên lịch delay bất đồng bộ thay vì `Thread.sleep` trên event loop. Đặt trần retry và deadline độc lập với backoff; ngẫu nhiên hóa không có nghĩa là cho phép retry vô hạn.

Khi server trả `Retry-After` (giá trị số giây hoặc thời điểm HTTP hợp lệ), client nên tôn trọng chỉ dẫn đó trong giới hạn deadline, retry budget và chính sách an toàn. Nếu đợi theo header sẽ quá deadline, hãy dừng sớm và trả lỗi phù hợp.

## 8. Retry budget: kiểm soát tổng lưu lượng bổ sung

Giới hạn “tối đa 3 lần thử cho mỗi request” là cần thiết nhưng chưa đủ. Nếu một triệu yêu cầu đồng loạt lỗi, mỗi yêu cầu được retry hai lần vẫn có thể tạo thêm hai triệu lời gọi.

**Retry budget** giới hạn *tổng số lần thử bổ sung* theo cửa sổ thời gian hoặc token bucket. Ví dụ, nếu chính sách cho phép tối đa 10% lưu lượng bổ sung và có 1.000 yêu cầu gốc đi vào một downstream trong một cửa sổ, chỉ có khoảng 100 lần retry bổ sung được cấp phép cho cửa sổ đó (theo cách tính budget đã chọn). Các lần thử ban đầu vẫn đi qua kiểm soát tải riêng. Không lấy 10% như một bảo đảm tuyệt đối trong mọi giây nếu thuật toán token bucket có burst allowance.

```text
Yêu cầu gốc đến downstream trong cửa sổ:  1.000
Tỷ lệ retry bổ sung mục tiêu:               10%
Budget retry tương ứng:                     100
Tổng attempts theo budget:                1.100
```

Cách triển khai:

1. Có bộ đếm/token cho retry, giới hạn theo downstream hoặc operation class; không chia một budget lớn cho mọi endpoint có độ quan trọng khác nhau.
2. Chỉ tiêu thụ token khi chuẩn bị **thử lại**, không tính lần đầu là retry.
3. Nếu hết token, trả lỗi có kiểm soát hoặc fallback đã được thiết kế, không “vay” retry qua SDK khác.
4. Kết hợp giới hạn số attempt mỗi yêu cầu, thời gian còn lại và số lời gọi đang chạy. Budget tỷ lệ không tự bảo vệ được hệ thống khỏi tải gốc quá lớn.
5. Phân tán bộ đếm/budget phù hợp môi trường nhiều instance; nếu mỗi instance giữ budget riêng, cần hiểu tổng burst có thể lớn hơn dự tính.

Budget không nên duy trì tỷ lệ retry lớn khi backend đã chết hoàn toàn. Khi breaker mở, hệ thống có thể chỉ cho ít probe ở trạng thái half-open, thay vì dùng hết budget để tiếp tục đập vào backend.

## 9. Mô hình quyết định retry an toàn

Luồng kiểm tra đề xuất:

```text
Gọi lần đầu
    |
    +-- Thành công? -------------------------> Trả kết quả
    |
    +-- Lỗi
          |
          +-- Operation có an toàn lặp? ----- Không --> Dừng
          |
          +-- Lỗi có thể phục hồi tạm thời? - Không --> Dừng
          |
          +-- Circuit breaker cho phép? ---- Không --> Dừng
          |
          +-- Chưa vượt maxAttempts? -------- Không --> Dừng
          |
          +-- Retry budget còn token? ------ Không --> Dừng
          |
          +-- Deadline đủ cho delay + call? - Không --> Dừng
          |
          +-- Tính backoff + jitter, xét Retry-After
          |
          +-- Chờ không chặn luồng và gọi lại
```

Mã giả theo ngôn ngữ độc lập, nhấn mạnh thứ tự quyết định:

```text
deadline = monotonicNow() + endToEndBudget
maxAttempts = 3

for attempt from 1 to maxAttempts:
    remaining = deadline - monotonicNow()
    if remaining < minimumUsefulCallTime:
        return DEADLINE_EXCEEDED

    perAttemptTimeout = min(configuredAttemptTimeout, remaining)
    result = callDownstream(timeout = perAttemptTimeout)

    if result.success:
        return result

    if not isSafeToRepeat(operation, idempotencyKey):
        return result

    if not isTransient(result) or not breakerAllowsRequest():
        return result

    if attempt == maxAttempts:
        return result

    delay = chooseBackoffWithJitter(attempt - 1, result.retryAfter)
    remaining = deadline - monotonicNow()

    if delay + minimumUsefulCallTime >= remaining:
        return DEADLINE_EXCEEDED

    if not retryBudget.tryAcquireToken():
        return result

    awaitNonBlocking(delay)

return LAST_FAILURE
```

Trong triển khai thật, phải xét race giữa kiểm tra budget, deadline và việc bắt đầu lần thử; có thể hoàn trả token nếu retry chưa xảy ra theo hợp đồng bộ đếm. Circuit breaker cần bao bọc đúng lời gọi và thống kê lỗi theo chính sách; cách sắp thứ tự lớp decorator (retry/breaker/timeout) ảnh hưởng đến số request thực sự được gửi. Ghi nhận attempt ở lớp gần transport để không bỏ sót lần thử ẩn.

## 10. Retry phải đi cùng cơ chế bảo vệ quá tải

| Cơ chế | Vai trò | Khi nào đặc biệt hữu ích |
| --- | --- | --- |
| Circuit breaker | Tạm dừng lời gọi tới phụ thuộc đang lỗi nặng; cho probe giới hạn khi hồi phục. | Lỗi kéo dài, mở kết nối vô ích, 503 hàng loạt. |
| Bulkhead / concurrency limit | Giới hạn tác vụ đồng thời, thread hoặc kết nối mà một phụ thuộc có thể chiếm. | Một downstream chậm làm nghẽn tài nguyên của service khác. |
| Rate limiting / admission control | Chặn hoặc trì hoãn lưu lượng ngay tại cửa vào, ưu tiên công việc quan trọng. | Tải gốc hoặc burst vượt năng lực phục vụ. |
| Load shedding | Từ chối sớm request khi quá tải thay vì xếp hàng không giới hạn. | Queue tăng và độ trễ leo thang. |
| Bounded queue | Giới hạn kích thước, thời gian nằm trong hàng đợi và cách xử lý khi đầy. | Công việc có thể chờ nhưng phải được chặn tràn. |
| Fallback có chủ đích | Trả dữ liệu cache, trạng thái tạm thời hoặc luồng suy giảm được chấp nhận. | Khi nghiệp vụ cho phép giảm chất lượng thay vì retry thêm. |

Thứ tự quan trọng: không phải mọi request đều được phép vào queue rồi retry. Khi backend quá tải, phản hồi nhanh bằng `429` hoặc `503` kèm thông tin thích hợp có thể hữu ích hơn việc giữ kết nối rất lâu. Client vẫn phải tuân thủ budget; `Retry-After` không phải giấy phép bỏ qua giới hạn.

**Circuit breaker không thay thế idempotency.** Breaker giảm áp lực lên dịch vụ lỗi; khi một lệnh có tác dụng phụ được gọi lại, việc không thực thi trùng vẫn là trách nhiệm của giao thức nghiệp vụ.

## 11. Tình huống thực tế: checkout gọi Payment và Inventory

Giả sử luồng:

```text
Client → Checkout API → Payment Service
                    └→ Inventory Service
```

Một chính sách có thể chấp nhận:

- Checkout đặt deadline chung, ví dụ 900 ms cho yêu cầu đồng bộ; từng cuộc gọi downstream được cấp phần thời gian còn lại.
- Checkout chỉ retry lời gọi **đọc tồn kho** khi lỗi thoáng qua và trong giới hạn tổng, ví dụ tối đa 2 attempts; HTTP client mặc định, proxy và service con không lặp lại cùng lời gọi.
- Với thao tác **ghi thanh toán**, Checkout không retry chỉ vì timeout nếu chưa có hợp đồng idempotency; khi đã có key bền vững và trạng thái tra cứu, mới áp dụng chính sách retry giới hạn hoặc truy vấn kết quả.
- Payment Service kiểm tra `Idempotency-Key` khi nhận lệnh và đồng bộ hóa xử lý trùng để tránh thu tiền hai lần.
- Inventory và Payment có giới hạn đồng thời riêng; Payment có breaker và phương án báo trạng thái “đang xác minh” nếu kết quả thanh toán chưa rõ.
- Retry budget phân theo dependency để sự cố Inventory không tiêu hết tài nguyên dành cho Payment.

Điểm tinh tế: sau timeout khi gọi Payment, một response “thất bại” từ Checkout có thể sai nếu Payment đã ghi nhận thành công. Cần biểu diễn trạng thái **unknown/pending reconciliation** hoặc truy vấn trạng thái dựa trên operation ID; không tự động chuyển thành “chưa thanh toán” rồi phát lệnh mới.

Đối với xử lý bất đồng bộ bằng queue, broker cũng có thể redeliver và worker có thể retry. Hãy đặt giới hạn requeue, backoff, dead-letter queue và consumer idempotent; không kết hợp retry HTTP vô hạn với redelivery vô hạn. Queue chỉ dời tải trong thời gian, không xóa được nhu cầu kiểm soát tải.

## 12. Quan sát để phát hiện khuếch đại trước khi thành sự cố

Theo dõi tối thiểu theo downstream và operation class:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `incoming_requests_total` | Số yêu cầu gốc/luồng vào; làm mẫu số theo phạm vi đo rõ ràng. |
| `outbound_attempts_total` | Tổng lời gọi thực gửi tới downstream, kể cả attempt đầu. |
| `retries_total` | Số attempt bổ sung; nên phân loại theo lý do và kết quả. |
| `retry_budget_denied_total` | Số lần muốn retry nhưng bị budget từ chối. |
| `downstream_inflight`, `queue_depth` | Tải đang chờ và yêu cầu đang chạy, phát hiện tích tụ tài nguyên. |
| `timeout_total`, `http_429_total`, `http_503_total` | Dấu hiệu lỗi/giảm tải; nhìn cùng latency và saturation. |
| `circuit_breaker_state` | Mức bảo vệ đang hoạt động: closed/open/half-open. |
| `request_duration` (p95/p99) | Độ trễ cuối luồng; retry “cứu” thành công nhưng có thể phá SLO. |

Trong luồng một lời gọi cơ sở cho mỗi request, có thể định nghĩa:

```text
retry_ratio = retries_total / original_outbound_calls_total

amplification_ratio = outbound_attempts_total / original_outbound_calls_total
                    = 1 + retry_ratio
```

Đây là các chỉ số trong **cùng một phạm vi đo và cửa sổ**; nếu có fan-out, batching hoặc request sinh thêm công việc hợp lệ, phải xác định “original outbound calls” theo baseline nghiệp vụ, không đơn thuần chia mọi cuộc gọi DB cho số request vào Gateway.

Trace phân tán nên có một span cho mỗi lượt gọi thực và ghi số attempt, reason, deadline remaining, backoff, retry owner, retry budget decision. Dùng trace ID hoặc operation ID để nối request qua các tầng. Hạn chế tag có cardinality cao (user ID, order ID, raw URL, token) trong metrics; cũng không đưa bí mật hoặc toàn bộ body vào log.

Một dấu hiệu cảnh báo thực tế là **outbound attempts tăng nhanh hơn incoming requests**, đồng thời p99 latency và số in-flight tăng; lúc này tăng retry thường làm tình hình tệ hơn.

## 13. Kịch bản kiểm thử lỗi và tải

Đừng chỉ thử một request riêng lẻ thành công sau lần gọi lại. Hãy kiểm tra hệ thống dưới tải đồng thời và cố ý gây lỗi:

1. **Lỗi thoáng qua:** downstream trả một `503` rồi thành công. Kiểm tra số attempts, delay và tỷ lệ phục hồi.
2. **Lỗi kéo dài:** downstream luôn trả `503`. Kiểm tra mọi request dừng trong deadline, breaker và retry budget chặn được lưu lượng bổ sung.
3. **Đồng loạt lỗi:** nhiều client nhận timeout cùng lúc. Kiểm tra jitter làm phân tán thời điểm retry và concurrency không tăng vô hạn.
4. **429 kèm Retry-After:** client tôn trọng chỉ dẫn nhưng dừng nếu thời gian chờ vượt deadline.
5. **Timeout sau khi ghi dữ liệu:** server hoàn tất Payment rồi mất phản hồi. Gửi lại với cùng idempotency key và xác nhận không có thanh toán trùng.
6. **Nhiều tầng retry:** bật mô phỏng retry ở proxy, SDK và service để xác nhận cấu hình cuối cùng chỉ có chủ sở hữu dự kiến; đếm attempts thực tới tầng cuối.
7. **Hồi phục sau lỗi:** backend trở lại bình thường. Kiểm tra probe half-open không gây làn sóng đồng bộ và throughput tăng có kiểm soát.

Tại mỗi kịch bản, đo tổng lời gọi thực, tỷ lệ thành công, p95/p99, số request bị từ chối, queue/in-flight và số tác dụng phụ được ghi nhận. Kết quả “tất cả request cuối cùng thành công” chưa đủ nếu hệ thống đánh đổi bằng độ trễ quá deadline hoặc tải tăng hàng chục lần.

## 14. Ứng phó khi bão retry đang xảy ra

Khi monitoring cho thấy retry khuếch đại tải:

1. **Xác định nguồn khuếch đại:** tách incoming traffic, attempts từ gateway, service, SDK và proxy bằng metrics/traces.
2. **Giảm các retry không thiết yếu:** hạ `maxAttempts`, giảm retry budget hoặc tắt retry với nhóm thao tác không an toàn; áp dụng thay đổi theo cấu hình có kiểm soát.
3. **Chặn tải ở vị trí thích hợp:** circuit breaker, load shedding, giới hạn đồng thời, giới hạn queue và ưu tiên traffic quan trọng.
4. **Bảo vệ dữ liệu nghiệp vụ:** giữ idempotency keys và không phát lại lệnh thanh toán/ghi dữ liệu khi trạng thái kết quả chưa rõ.
5. **Khôi phục có điều tiết:** cho phép probe ít, tăng lưu lượng từ từ, theo dõi saturation và p99 trước khi mở hoàn toàn.
6. **Điều tra hậu sự cố:** thống kê amplification factor, vị trí retry lồng nhau, timeout sai, thiếu deadline/budget và cập nhật hợp đồng retry giữa nhóm sở hữu các service.

Tăng số replica có thể cần thiết nếu thiếu công suất thật, nhưng không thay thế việc chặn vòng retry tự khuếch đại. Việc scale chậm hơn tốc độ bão retry hoặc làm nghẽn phụ thuộc chung thậm chí có thể không cải thiện kết quả.

## 15. Bài tập áp dụng

**Bài tập 1 — Tính tải xấu nhất.** Một request đi qua 3 tầng đồng bộ. Mỗi tầng có `maxAttempts = 4`, kể cả lần đầu. Không có deadline, breaker hay budget. Tính số lần tầng cuối có thể bị gọi nếu mọi attempt đều thất bại. Nếu lưu lượng đầu vào 200 request/s, xác định cận trên của số lần gọi tầng cuối mỗi giây. Gợi ý: nhân số attempts của các tầng; đây là cận trên trong kịch bản giả định.

**Bài tập 2 — Sửa cấu hình.** Hệ thống A → B → C có retry 3 attempts tại A và B; SDK từ B đến C cũng có retry 3 attempts. Đề xuất một chủ sở hữu retry, deadline 700 ms, một ngưỡng retry budget, backoff có jitter và tiêu chí bật breaker. Chỉ ra cách ngăn proxy/SDK thêm retry ngoài dự kiến.

**Bài tập 3 — An toàn nghiệp vụ.** Checkout gọi Payment và bị timeout ngay sau khi Payment commit. Viết hợp đồng idempotency key, lưu trữ kết quả, tra cứu trạng thái và xử lý hai request đồng thời cùng key. Giải thích vì sao đổi key mới ở mỗi retry có thể tạo giao dịch trùng.

**Bài tập 4 — Đo lường.** Với một operation có 10.000 lời gọi gốc và 800 attempts bổ sung trong cùng cửa sổ, tính retry ratio và amplification ratio. Nếu kiến trúc còn có fan-out hợp lệ 2 downstream calls trên một lời gọi gốc, hãy đề xuất mẫu số phù hợp để không nhầm fan-out với retry.

## 16. Ghi nhớ

- **Retry là tải bổ sung**, nên phải được quản lý như tài nguyên hữu hạn.
- **Số attempts lồng nhau nhân nhau**; xác định một chủ sở hữu retry và loại bỏ retry ẩn.
- **Giới hạn đủ cả bốn chiều:** điều kiện lỗi/nghiệp vụ, số attempts, retry budget và deadline.
- **Backoff có jitter** phân tán lần thử; **circuit breaker và load shedding** bảo vệ backend khi lỗi kéo dài.
- **Timeout không chứng minh thao tác chưa xảy ra**; lệnh có tác dụng phụ cần idempotency hoặc cơ chế xác minh trạng thái.
- **Đo attempts thực ở downstream**, đối chiếu baseline nghiệp vụ và thử lỗi dưới tải trước khi tin rằng cấu hình an toàn.

Một chiến lược retry tốt tăng xác suất hoàn tất các lỗi thoáng qua mà vẫn giữ được giới hạn tải, thời gian và tính đúng đắn nghiệp vụ khi hệ thống đang ở trạng thái xấu nhất.
