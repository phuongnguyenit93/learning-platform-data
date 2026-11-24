# Tránh thử lại qua nhiều tầng và khuếch đại lưu lượng khi có sự cố

Retry giúp một request vượt qua lỗi tạm thời, nhưng retry ở nhiều tầng cùng lúc có thể biến một sự cố nhỏ thành quá tải diện rộng. Browser retry, gateway retry, service retry và database client retry có thể nhân số lần gọi lên nhiều lần. Khi hệ thống đang chậm vì thiếu tài nguyên, các lần thử lại tiếp tục chiếm connection, thread, CPU và queue, khiến request mới càng khó hoàn tất.

Trong module `INTEGRATION_REALTIME_RSOCKET`, một logical request có thể đi qua browser/WebSocket, RSocket edge, service downstream và database hoặc broker. Vì vậy, cần thiết kế retry như một ngân sách xuyên suốt request, xác định rõ tầng chịu trách nhiệm thử lại, truyền deadline xuống các tầng và kết hợp circuit breaker, bulkhead cùng load shedding. Mục tiêu là phục hồi lỗi tạm thời mà không khuếch đại tải khi dependency đang suy giảm.

## 1. Vì sao retry nhiều tầng gây khuếch đại?

Giả sử một request đi qua bốn tầng: client, gateway, service và database client. Mỗi tầng cho phép tối đa ba attempt tổng cộng, bao gồm lần đầu. Nếu mọi lần gọi ở tầng trên đều kích hoạt toàn bộ chuỗi bên dưới, số attempt tới database trong trường hợp xấu nhất là:

\[
A_{total} = A_{client} \times A_{gateway} \times A_{service} \times A_{database}
\]

Với ba attempt ở mỗi tầng:

\[
A_{total} = 3 \times 3 \times 3 \times 3 = 81
\]

Một thao tác logic có thể tạo tới 81 lần thử ở database. Trong thực tế, số lần phụ thuộc tầng nào phát hiện lỗi và request có đi tiếp xuống tầng dưới hay không; phép nhân thể hiện giới hạn khuếch đại khi mọi tầng đều retry cùng một lỗi.

```text
Client: 3 attempts
   |
   +-- Gateway: 3 attempts cho mỗi lần client gọi
          |
          +-- Service: 3 attempts cho mỗi lần gateway gọi
                 |
                 +-- DB client: 3 attempts cho mỗi lần service gọi
                        |
                        +-- Tối đa 81 DB attempts
```

Nếu request còn fan-out tới nhiều dependency, tổng tải còn tăng theo số nhánh. Một service gọi đồng thời bốn dependency và retry mỗi nhánh ba lần có thể tạo nhiều công việc hơn đáng kể so với một request đơn.

## 2. Retry storm và vòng phản hồi quá tải

Retry storm thường diễn ra theo vòng lặp:

1. Một dependency chậm hoặc bắt đầu trả lỗi do thiếu connection, thread hoặc CPU.
2. Client/gateway/service timeout và gửi lại request.
3. Request cũ có thể vẫn đang chạy; request mới tạo thêm công việc trùng.
4. Queue, connection pool và thread pool đầy nhanh hơn.
5. Latency tăng khiến nhiều tầng timeout cùng lúc.
6. Các tầng tiếp tục retry, làm tải tăng dù năng lực xử lý không tăng.

Retry không tạo thêm năng lực xử lý. Khi nguyên nhân là quá tải, retry đồng bộ thường làm tình hình tệ hơn. Hệ thống cần giảm số request được chấp nhận, giới hạn concurrency và cho dependency thời gian phục hồi.

Các dấu hiệu thường gặp:

- Số request/attempt tăng nhanh trong khi số request nghiệp vụ thành công giảm.
- Latency p95/p99 tăng và timeout xuất hiện ở nhiều tầng.
- Connection pool, event-loop queue hoặc worker queue gần chạm giới hạn.
- Nhiều request có cùng correlation ID nhưng attempt khác nhau.
- Số kết nối mới/reconnect tăng đột biến.
- CPU và số lần serialize/deserialize tăng dù lưu lượng người dùng không đổi.

## 3. Chỉ định một tầng sở hữu retry

Với mỗi thao tác nghiệp vụ, hãy chọn một tầng có đủ ngữ cảnh để quyết định retry. Tầng đó phải biết loại lỗi, tính idempotent, deadline còn lại và trạng thái dependency. Các tầng khác nên trả lỗi lên thay vì tự retry thêm một vòng.

Ví dụ phân công:

| Tầng | Trách nhiệm khuyến nghị |
|---|---|
| Browser/mobile client | Chỉ retry thao tác được phép, theo policy sản phẩm; dùng command ID nếu có side effect. |
| API gateway / edge | Áp dụng deadline, giới hạn request, circuit/load shedding; tránh retry nghiệp vụ nếu service đã có retry owner. |
| Service điều phối | Retry một dependency cụ thể khi có thể xác định lỗi tạm thời, deadline và idempotency. |
| HTTP/RSocket client dùng chung | Mặc định trả lỗi; chỉ retry nếu được cấu hình rõ là retry owner của thao tác. |
| Database driver/client | Dùng retry nội bộ cho lỗi kết nối an toàn theo hợp đồng driver; tránh lặp transaction hoặc câu lệnh ghi không idempotent. |
| Service mesh / proxy | Chỉ retry khi hiểu giao thức và request có thể replay an toàn; tránh chồng với retry ở ứng dụng. |

Không có một tầng bắt buộc phải sở hữu mọi retry. Điều quan trọng là một logical operation có một policy retry chính, được ghi rõ trong hợp đồng. Nếu cần retry ở tầng thấp cho lỗi kết nối rất hẹp, policy đó phải nằm trong ngân sách chung và không tạo một vòng retry độc lập không giới hạn.

### 3.1. Phân biệt retry kết nối với retry tương tác

Với RSocket, kết nối là một logical session có thể phục vụ nhiều stream. Retry tạo kết nối ban đầu (`connectTcp` hoặc `connectWebSocket`) khác với retry một Request-Response sau khi requester đã kết nối.

- **Connect retry:** thử thiết lập transport/SETUP khi server chưa sẵn sàng hoặc mạng tạm thời lỗi.
- **Interaction retry:** tạo lại một request/stream/channel cụ thể trên một requester đang hoạt động hoặc requester mới.
- **Reconnect/Resume:** khôi phục transport/session sau disconnect; Resume có thể phát lại frame chưa xác nhận nếu state còn tồn tại.
- **Business retry:** gửi lại command vì chưa có kết quả nghiệp vụ chắc chắn; cần idempotency và đối soát.

Không dùng một `retryWhen` chung để giải quyết cả bốn trường hợp. Nếu client retry toàn bộ `Mono<RSocketRequester>` rồi mỗi service cũng retry interaction, số lần kết nối và request có thể tăng đồng thời.

Một TCP load balancer thông thường phân phối kết nối, không hiểu semantics của từng RSocket stream. Chỉ proxy/gateway có hiểu giao thức mới có thể quyết định retry ở cấp tương tác; không giả định mọi service mesh hoặc L4 load balancer có thể retry an toàn một frame RSocket.

## 4. Đặt deadline xuyên suốt request

Deadline là thời điểm cuối cùng mà kết quả còn hữu ích. Thay vì mỗi tầng tự đặt timeout mới từ đầu, tầng trên nên truyền thời gian còn lại xuống tầng dưới.

Ví dụ:

```text
Client deadline: 2.0 giây
   |
   +-- Gateway còn 1.8 giây
          |
          +-- Service còn 1.4 giây
                 |
                 +-- Database còn 0.9 giây
```

Các tầng cần dành một phần thời gian cho xử lý và trả response. Không để database tiêu hết deadline khiến service không còn thời gian serialize và gửi kết quả.

Nguyên tắc:

- Tạo deadline ở ranh giới tin cậy của request.
- Truyền `remaining timeout` hoặc deadline metadata theo một hợp đồng nội bộ đã xác định.
- Trước mỗi lần retry, tính lại thời gian còn lại; không reset timeout đầy đủ cho attempt mới.
- Không bắt đầu attempt nếu thời gian còn lại không đủ để thực hiện và trả kết quả.
- Timeout ở client không chứng minh server đã dừng xử lý; server vẫn phải truyền cancellation và quản lý tác vụ.
- Đồng bộ deadline với timeout database, HTTP client và proxy để tránh tầng dưới chạy lâu hơn request tổng thể.

Ví dụ ở một service reactive:

```java
Mono<DeviceStatus> loadStatus(String deviceId, Duration remaining) {
    if (remaining.isZero() || remaining.isNegative()) {
        return Mono.error(new DeadlineExceededException());
    }

    return requester
        .route("devices.{deviceId}.status.get", deviceId)
        .data(new StatusQuery())
        .retrieveMono(DeviceStatus.class)
        .timeout(remaining);
}
```

Đây là ví dụ minh họa. Trong hệ thống thực tế, `remaining` phải được tính từ deadline gốc hoặc context đã được xác thực, không được nhận một timeout tùy ý từ client rồi cho phép nó vượt quá giới hạn server. RSocket metadata có thể mang deadline/timeout theo quy ước ứng dụng; RSocket không tự áp đặt một deadline nghiệp vụ chung cho mọi interaction.

## 5. Exponential backoff và jitter

Nếu retry là phù hợp, đừng gửi lại ngay lập tức. Exponential backoff tăng khoảng chờ sau mỗi lần thất bại:

\[
T_n = \min(T_{max}, T_{base} \times 2^n)
\]

Nếu mọi client dùng cùng một lịch backoff, chúng có thể thức dậy và retry cùng thời điểm. Jitter thêm độ ngẫu nhiên để phân tán các attempt:

\[
T_{wait} \sim U(0, T_n)
\]

Đây là full jitter: thời gian chờ được chọn ngẫu nhiên trong khoảng từ 0 tới backoff tối đa của attempt. Có thể dùng equal jitter hoặc decorrelated jitter tùy thư viện và chính sách.

Ví dụ Reactor:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.5)
        .filter(this::isTransientFailure));
```

Trong Reactor, `Retry.backoff(2, ...)` cho phép tối đa hai lần retry sau attempt ban đầu, tức tối đa ba attempt tổng cộng. `.jitter(0.5)` thêm biến thiên quanh lịch backoff do Reactor tạo ra; không nên mô tả nó là full jitter chính xác nếu chưa xác minh semantics của phiên bản Reactor đang dùng. Ví dụ này chỉ dành cho truy vấn đọc có thể lặp an toàn và lỗi tạm thời.

### 5.1. Giới hạn cả số lần lẫn tổng thời gian

Chỉ giới hạn số lần retry chưa đủ. Ba attempt có thể kéo dài quá lâu nếu mỗi attempt gần hết timeout. Policy cần giới hạn:

- Số attempt tổng cộng.
- Thời gian tối đa cho một attempt.
- Tổng deadline của logical request.
- Khoảng backoff tối đa.
- Số request được retry đồng thời.

Nếu dependency trả `Retry-After` hoặc thông tin thời gian phục hồi, có thể cân nhắc tôn trọng giá trị đó trong giới hạn deadline và policy của client. Không retry trước thời điểm server yêu cầu nếu việc đó tiếp tục tạo tải.

## 6. Retry budget: giới hạn tổng lượng retry

Retry budget giới hạn tỷ lệ hoặc số lượng attempt bổ sung so với request gốc. Ví dụ, một service cho phép retry tối đa 5% số request trong một cửa sổ thời gian. Khi budget cạn, request mới đi qua một lần hoặc thất bại sớm thay vì tiếp tục retry.

Một cách triển khai là token bucket:

- Request gốc không cần lấy retry token.
- Mỗi attempt retry phải lấy một token.
- Token được bổ sung theo tốc độ cố định hoặc theo tỷ lệ request thành công.
- Khi không còn token, trả lỗi hoặc fallback theo policy.

Budget nên được đo theo service/dependency và có thể chia theo tenant hoặc mức ưu tiên. Không dùng một budget vô hạn cho toàn hệ thống. Nếu nhiều replica có budget cục bộ, tổng retry budget toàn cluster bằng tổng budget từng replica; cần tính điều này khi cấu hình.

Các metric hữu ích:

- `requests_total` và `retry_attempts_total`.
- Tỷ lệ retry trên request gốc.
- Retry budget còn lại và số attempt bị từ chối do hết budget.
- Số logical request cuối cùng thành công sau retry.
- Số request thất bại sau khi budget/deadline cạn.

Không đưa request ID hoặc token vào metric label; dùng nhãn có cardinality thấp như service, route template, dependency và error class.

## 7. Chỉ retry lỗi tạm thời và có thể phục hồi

Không phải mọi lỗi đều đáng retry. Phân loại lỗi theo nguyên nhân và khả năng thành công nếu thử lại:

| Lỗi | Retry? | Ghi chú |
|---|---|---|
| DNS/connection reset tạm thời | Có thể | Giới hạn attempt và deadline; xác định request đã tới server chưa. |
| HTTP 503 / service unavailable | Có thể | Tôn trọng `Retry-After`, backoff và retry budget. |
| HTTP 429 / rate limit | Có điều kiện | Giảm tải và chờ theo policy; không retry ngay. |
| Timeout | Có điều kiện | Outcome có thể không xác định; chỉ retry thao tác idempotent hoặc có dedup. |
| Validation error | Không | Sửa dữ liệu đầu vào. |
| Authentication/authorization error | Không | Làm mới credential hoặc xử lý quyền theo luồng riêng; không lặp vô hạn. |
| Route không tồn tại / protocol mismatch | Không | Đây là lỗi cấu hình/hợp đồng. |
| Business rejection | Thường không | Chỉ retry nếu trạng thái nghiệp vụ thay đổi và policy cho phép. |
| Database deadlock/serialization conflict | Có thể | Chỉ retry toàn bộ transaction theo giới hạn; không retry riêng một câu lệnh giữa transaction. |
| Circuit breaker đang open | Không retry ngay | Fail fast hoặc fallback cho tới khi probe phục hồi. |

Hàm `isTransientFailure` phải kiểm tra loại exception/status cụ thể. Không dùng `filter(error -> true)` hoặc retry mọi `RuntimeException`.

## 8. Idempotency là điều kiện của retry an toàn

Timeout hoặc disconnect không cho biết server đã thực hiện side effect hay chưa. Nếu client retry lệnh thanh toán, tạo đơn hoặc điều khiển thiết bị, server có thể thực hiện hai lần.

Với command có side effect:

1. Client tạo `commandId`/idempotency key trước lần gửi đầu tiên.
2. Mọi lần retry dùng lại cùng key và cùng payload nghiệp vụ.
3. Server lưu key với phạm vi tenant/operation và payload hash.
4. Unique constraint ngăn hai request đồng thời cùng tạo command mới.
5. Server trả lại receipt/kết quả đã lưu khi nhận key trùng với payload giống nhau.
6. Nếu cùng key nhưng payload khác, trả conflict và ghi nhận sự kiện bất thường.

Ví dụ DTO:

```java
public record DeviceCommand(
    String commandId,
    String deviceId,
    String action
) {}
```

Đối với side effect trong cùng database, lưu idempotency record và cập nhật nghiệp vụ trong cùng transaction. Với dịch vụ ngoài database, dùng Transactional Outbox và downstream idempotency hoặc quy trình đối soát. Không coi RSocket `CANCEL` là rollback; server có thể đã thực hiện side effect trước khi nhận cancellation.

### 8.1. Không retry Fire-and-Forget một cách mù quáng

`RSocketRequester.send()` hoàn tất không phải xác nhận server đã xử lý command. Nếu timeout hoặc kết nối đứt, client càng không biết server đã nhận hay chưa.

- Với telemetry best-effort, có thể chấp nhận mất mẫu và không retry.
- Với event quan trọng, lưu event vào outbox/queue và gửi lại cùng event ID.
- Nếu cần server xác nhận đã chấp nhận command, dùng Request-Response để trả receipt hoặc một status query riêng.
- Server phải deduplicate event/command ID trước khi thực hiện side effect.

## 9. Retry cho Stream và Channel cần cursor/sequence

Retry một `Mono` đọc trạng thái thường đơn giản hơn retry một `Flux` kéo dài. Khi retry Request-Stream, publisher có thể mở subscription mới và phát lại dữ liệu từ đầu. Khi retry Request-Channel, client có thể gửi lại các command đã phát trước khi disconnect.

Với stream/channel:

- Dùng sequence number, event ID hoặc cursor để xác định phần dữ liệu đã nhận/đã xử lý.
- Khi reconnect, gửi cursor cuối đã xác nhận để server tiếp tục từ vị trí phù hợp.
- Server deduplicate command theo ID và sequence.
- Định nghĩa rõ semantics cho phần tử đang xử lý khi cancel hoặc disconnect.
- Nếu cần replay sau thời gian dài, lấy dữ liệu từ event store/broker; không dựa vào in-memory publisher hoặc Resume buffer như kho lịch sử.

RSocket Resume có thể khôi phục frame của logical session khi session và buffer còn hiệu lực. Nó không thay thế retry budget, idempotency hoặc cursor nghiệp vụ. Tránh vừa bật Resume vừa retry toàn bộ stream ngay khi có disconnect mà không hiểu trạng thái session, vì có thể tạo subscription mới và phát lại công việc trùng.

## 10. Circuit breaker, bulkhead và load shedding

Retry là một công cụ phục hồi; cần các cơ chế khác để bảo vệ hệ thống khi dependency suy giảm.

### 10.1. Circuit breaker

Circuit breaker theo dõi tỷ lệ lỗi/timeout. Khi vượt ngưỡng, breaker chuyển sang `OPEN` và từ chối lời gọi mới trong một khoảng thời gian. Sau đó nó chuyển sang `HALF_OPEN`, cho một số ít probe thử dependency. Nếu probe thành công, breaker đóng lại; nếu thất bại, breaker tiếp tục mở.

Circuit breaker ngăn request tiếp tục dồn vào dependency đang lỗi. Khi breaker open, không retry liên tục bên trong breaker; hãy fail fast hoặc trả fallback có ý nghĩa.

### 10.2. Bulkhead và giới hạn concurrency

Bulkhead giới hạn số công việc đồng thời tới một dependency để lỗi của dependency đó không chiếm hết tài nguyên của service. Có thể dùng semaphore, bounded scheduler, connection pool giới hạn hoặc concurrency limit ở client.

Đặt giới hạn theo năng lực thực tế của dependency. Queue chờ cũng phải hữu hạn; queue quá dài chỉ biến quá tải tức thời thành latency lớn và timeout dây chuyền.

### 10.3. Load shedding

Khi hệ thống đã quá tải, từ chối sớm request có mức ưu tiên thấp có thể giúp bảo vệ các request quan trọng. Có thể trả status tương ứng như `503`/`429` ở HTTP boundary hoặc application error đã chuẩn hóa ở RSocket.

Không nhận thêm công việc rồi giữ vô hạn trong memory. Dùng bounded queue, giới hạn payload, concurrency và deadline. Client cần hiểu tín hiệu quá tải và chờ theo backoff thay vì retry ngay.

## 11. Hedged request và retry song song

Hedged request gửi cùng một request tới nhiều replica để giảm tail latency khi một replica chậm. Kết quả đầu tiên thắng, các attempt còn lại bị hủy.

Hedging có thể hữu ích cho truy vấn đọc idempotent khi có nhiều replica độc lập, nhưng nó chủ động nhân tải ngay cả khi chưa có lỗi. Khi hệ thống đã bận, hedging có thể làm tăng tail latency thay vì giảm.

Chỉ cân nhắc hedging khi:

- Đã đo được tail latency và biết một phần request chậm do replica bất thường.
- Chỉ áp dụng cho thao tác đọc/idempotent hoặc có dedup mạnh.
- Có tỷ lệ hedge nhỏ, độ trễ khởi phát và concurrency limit.
- Hủy các attempt thua và chấp nhận rằng cancellation không đảm bảo server đã dừng side effect.
- Có metric riêng cho hedge rate và tài nguyên tăng thêm.

Không dùng hedging cho command thanh toán, ghi dữ liệu hoặc Fire-and-Forget không có idempotency. Với RSocket, không giả định mọi load balancer có thể hedge một interaction trên cùng session; thường cần logic ở application client và một kết nối/stream tới replica khác.

## 12. Ví dụ phối hợp policy trong một service

Một service có thể áp dụng deadline, giới hạn concurrency, circuit breaker và retry ở đúng một dependency call:

```java
Mono<DeviceStatus> getStatus(String deviceId, Duration remaining) {
    if (remaining.compareTo(Duration.ofMillis(100)) < 0) {
        return Mono.error(new DeadlineExceededException());
    }

    return Mono.defer(() ->
        bulkhead.executeSupplier(() ->
            circuitBreaker.executeSupplier(() ->
                requester
                    .route("devices.{deviceId}.status.get", deviceId)
                    .data(new StatusQuery())
                    .retrieveMono(DeviceStatus.class)
                    .timeout(remaining)
                    .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
                        .maxBackoff(Duration.ofMillis(300))
                        .jitter(0.5)
                        .filter(this::isTransientFailure))
            )
        )
    );
}
```

Đây là pseudocode gần với API của các thư viện resilience; chữ ký `bulkhead`/`circuitBreaker` phụ thuộc thư viện và cách tích hợp Reactor. Điểm thiết kế là chỉ một policy retry nằm cạnh dependency call, có deadline, retry ít lần và phân loại lỗi. Trong triển khai thật, cần kiểm tra thứ tự decorator và semantics timeout của thư viện để tránh breaker đo nhầm lỗi do caller cancel hoặc timeout của tầng ngoài.

Không copy đoạn code này mà chưa cấu hình retry budget toàn service. Nếu gateway đã retry cùng thao tác, hãy tắt retry ở service hoặc điều chỉnh để tổng số attempt vẫn nằm trong ngân sách đã định.

## 13. Quy tắc phối hợp giữa các tầng

Một hợp đồng retry xuyên suốt có thể được ghi rõ như sau:

| Tầng | Timeout/deadline | Retry | Hành động khi lỗi |
|---|---|---|---|
| Browser | Deadline trải nghiệm người dùng | Không retry command không idempotent; dùng command ID | Hiển thị trạng thái chưa xác định và cho phép đối soát. |
| Gateway | Deadline còn lại từ client, có giới hạn server | Mặc định không retry nghiệp vụ nếu service là owner | Rate limit, load shed, trả lỗi có correlation ID. |
| RSocket service | Dùng remaining deadline | Retry dependency call được chỉ định, có budget | Circuit breaker, bulkhead và fallback. |
| Database client | Timeout ngắn hơn deadline còn lại | Chỉ retry lỗi transaction an toàn theo driver/policy | Rollback transaction và trả lỗi phân loại. |
| Broker consumer | Visibility/ack deadline theo broker | Redelivery theo broker, consumer idempotent | Dead-letter hoặc retry topic/queue có giới hạn. |

Hợp đồng cũng cần nói rõ tầng nào là retry owner cho từng route/operation. Một route đọc trạng thái có thể retry ở service; một command điều khiển có thể yêu cầu client giữ command ID và chỉ retry sau khi status query; một event nền có thể để broker redelivery và consumer dedup.

## 14. Kiểm thử retry amplification và sự cố

Không chỉ kiểm thử rằng một request thành công sau một lần retry. Cần chứng minh tổng số attempt được giới hạn khi nhiều tầng cùng gặp lỗi.

Các kịch bản nên có:

1. Làm dependency trả lỗi tạm thời; xác nhận đúng một tầng thực hiện retry.
2. Cấu hình client/gateway/service/database có retry; đo tổng attempt và xác nhận không vượt ngân sách đã định.
3. Mô phỏng 503/429; xác nhận backoff, jitter và `Retry-After` được xử lý.
4. Mô phỏng timeout sau khi server đã commit; xác nhận command ID ngăn side effect lặp.
5. Làm dependency chậm; xác nhận deadline được truyền xuống và request không tiếp tục chạy sau deadline.
6. Mở circuit breaker; xác nhận request fail fast và số probe ở HALF_OPEN bị giới hạn.
7. Làm đầy bulkhead/queue; xác nhận load shedding thay vì queue tăng vô hạn.
8. Hủy RSocket stream/channel; xác nhận cancellation được truyền xuống nguồn và không kích hoạt retry ngoài ý muốn.
9. Làm nhiều client reconnect đồng thời; xác nhận backoff/jitter và connection rate nằm trong giới hạn.
10. Kiểm thử Fire-and-Forget, Request-Stream và Request-Channel với duplicate event/command, cursor và sequence.
11. Kiểm tra metric cho request gốc, attempt, retry budget, circuit state và dependency latency.

Trong load test, so sánh hai tình huống: retry ở mọi tầng và retry ở một tầng có budget. Quan sát request throughput thành công, attempt count, p99 latency, queue depth, CPU, connection pool và thời gian phục hồi. Chỉ nhìn tỷ lệ lỗi cuối cùng có thể bỏ qua việc hệ thống đang tạo quá nhiều công việc trùng.

## 15. Những sai lầm thường gặp

- **Mỗi tầng tự retry ba lần:** attempt nhân lên theo chiều sâu chuỗi gọi.
- **Reset timeout ở mỗi lần retry:** tổng thời gian vượt deadline của người dùng.
- **Retry mọi exception:** lặp cả validation, authorization và business rejection.
- **Retry ngay lập tức:** các client đồng bộ tạo burst cùng thời điểm.
- **Retry command không idempotent:** side effect có thể chạy nhiều lần sau timeout.
- **Dùng Fire-and-Forget như có acknowledgement:** client không biết server đã xử lý hay chưa.
- **Coi CANCEL là rollback:** cancellation không hoàn tác side effect đã commit.
- **Dùng circuit breaker nhưng vẫn retry khi OPEN:** tiếp tục dồn tải vào dependency đang lỗi.
- **Hedging mọi request:** tăng tải ngay cả khi hệ thống chưa có lỗi.
- **Queue không giới hạn:** giữ quá nhiều công việc và làm latency tăng dây chuyền.
- **Không đo attempt riêng:** chỉ thấy một logical request nhưng không biết nó tạo bao nhiêu lần gọi downstream.

## 16. Checklist trước khi bật retry

- Đã xác định retry owner cho từng operation/route.
- Các tầng khác không có retry policy trùng lặp ngoài ngân sách đã thống nhất.
- Có deadline tổng và truyền thời gian còn lại xuống dependency.
- Có giới hạn attempt, tổng thời gian và retry budget.
- Có exponential backoff, jitter và xử lý `Retry-After` khi phù hợp.
- Chỉ retry lỗi tạm thời đã phân loại.
- Side effect có idempotency key, dedup hoặc cơ chế đối soát.
- Request-Stream/Channel có cursor/sequence khi cần replay.
- Circuit breaker, bulkhead, bounded queue và load shedding được cấu hình.
- Hedging chỉ dùng cho thao tác an toàn và có giới hạn tải.
- Có metric phân biệt logical request với attempt.
- Đã kiểm thử outage, timeout sau commit, reconnect storm và retry storm.

## 17. Kết luận

Retry ở nhiều tầng có thể nhân số attempt theo chiều sâu chuỗi gọi và làm quá tải trở nên nghiêm trọng hơn. Hãy chỉ định một retry owner cho mỗi logical operation, truyền deadline xuyên suốt, giới hạn attempt bằng retry budget, dùng exponential backoff cùng jitter và chỉ retry lỗi tạm thời. Với side effect, bắt buộc có idempotency hoặc cơ chế đối soát; với stream/channel, cần cursor và sequence. Kết hợp circuit breaker, bulkhead, bounded queue và load shedding để hệ thống có thể từ chối sớm khi cần. Cuối cùng, đo cả logical request lẫn số attempt thực tế để phát hiện khuếch đại trước khi nó trở thành retry storm.
