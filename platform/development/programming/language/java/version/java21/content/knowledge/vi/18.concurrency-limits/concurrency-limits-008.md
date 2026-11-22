# Xử lý overload và phục hồi khi dependency chậm

Trong ứng dụng Java 21, một dependency chậm có thể khiến request tích tụ, thread chờ lâu, connection pool cạn và thời gian phản hồi của toàn hệ thống tăng theo. Khi dependency phục hồi, lượng công việc dồn lại còn có thể tạo thêm một đợt tải đột biến. Vì vậy, xử lý overload cần kết hợp giới hạn lượng công việc được nhận, giới hạn số thao tác đồng thời, timeout, hủy tác vụ, retry có kiểm soát và cơ chế phục hồi.

Virtual thread giúp xử lý nhiều tác vụ blocking với chi phí thread thấp, nhưng không tự tạo backpressure hoặc giới hạn tải lên database, HTTP service, message broker hay hệ thống bên ngoài. Ứng dụng phải đặt giới hạn ở ranh giới tài nguyên và quyết định rõ điều gì xảy ra khi hệ thống không còn capacity.

## 1. Overload và dependency chậm hình thành như thế nào?

Giả sử một API nhận request và mỗi request cần gọi một dịch vụ thanh toán. Khi dịch vụ thanh toán phản hồi chậm hơn bình thường, mỗi request giữ tài nguyên lâu hơn. Trong cùng một khoảng thời gian, số request đang chờ tăng lên.

Một chuỗi sự kiện thường gặp:

1. Dependency xử lý chậm hoặc bắt đầu timeout.
2. Request của ứng dụng giữ virtual thread, connection, buffer và trạng thái xử lý lâu hơn.
3. Request mới tiếp tục được nhận và tạo thêm task.
4. Số task đang chờ vượt khả năng phục vụ của dependency hoặc connection pool.
5. Độ trễ tăng, timeout lan sang các tầng khác và retry có thể làm tải tăng thêm.
6. Khi dependency phục hồi, hàng đợi công việc tích tụ có thể tiếp tục gây overload.

Có thể hình dung:

~~~text
Request đến
    |
    v
Ứng dụng nhận task
    |
    v
Giới hạn admission / concurrency
    |
    v
Dependency chậm
    |
    +---- còn capacity ----> xử lý và trả kết quả
    |
    +---- hết capacity ----> chờ có giới hạn hoặc từ chối sớm
    |
    v
Timeout / circuit breaker / fallback
    |
    v
Trả kết quả có kiểm soát và giải phóng tài nguyên
~~~

Mục tiêu không phải làm cho dependency chậm trở nên nhanh hơn. Mục tiêu là giữ cho tải mà ứng dụng đưa tới dependency nằm trong giới hạn chịu đựng, ngăn lỗi lan rộng và cho hệ thống cơ hội phục hồi.

## 2. Phân biệt concurrency limit, rate limit và backpressure

Ba cơ chế này giải quyết các vấn đề liên quan nhưng khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Concurrency limit | Số thao tác đang diễn ra đồng thời | Tối đa 30 request đang chờ phản hồi từ payment service |
| Rate limit | Số thao tác được phép bắt đầu trong một khoảng thời gian | Tối đa 100 request mỗi giây |
| Backpressure / admission control | Tốc độ hoặc số lượng công việc được nhận vào hệ thống khi downstream không theo kịp | Tạm dừng nhận, giảm tốc độ phát hoặc từ chối request mới |

Một semaphore thường được dùng để giới hạn concurrency. Nó không giới hạn số request mỗi giây. Một rate limiter có thể kiểm soát tốc độ bắt đầu request, nhưng không nhất thiết giới hạn số request đang đồng thời chờ phản hồi. Một hàng đợi có giới hạn giúp kiểm soát lượng công việc chờ, nhưng vẫn cần giới hạn số worker xử lý.

Hệ thống thực tế thường cần phối hợp các cơ chế này. Ví dụ, rate limit bảo vệ quota của dịch vụ bên ngoài; semaphore giới hạn số request đồng thời; admission control từ chối công việc mới khi hàng đợi hoặc hệ thống đã quá tải.

## 3. Đặt timeout ở từng ranh giới I/O

Không có timeout, một task có thể chờ dependency vô thời hạn, giữ tài nguyên và làm giảm capacity cho request khác. Hãy đặt timeout rõ ràng cho từng thao tác có thể chờ:

- Timeout thiết lập kết nối.
- Timeout chờ phản hồi hoặc đọc dữ liệu.
- Timeout lấy connection từ connection pool.
- Query timeout hoặc transaction timeout với database.
- Timeout tổng thể của request hoặc workflow.

Java 21 HttpClient hỗ trợ timeout khi thiết lập client và timeout cho từng HttpRequest:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://payments.example/api/status"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

connectTimeout giới hạn thời gian thiết lập kết nối; HttpRequest.timeout đặt thời hạn cho request. Ứng dụng vẫn cần xác định cách xử lý IOException, HttpTimeoutException và các lỗi HTTP từ dependency.

Với JDBC, có thể dùng các cơ chế timeout phù hợp của driver và pool, chẳng hạn query timeout của Statement, network timeout của Connection hoặc thời hạn chờ lấy connection. Hành vi cụ thể còn phụ thuộc driver và database; cần xác minh trong tài liệu của implementation đang triển khai.

Timeout phải dựa trên mục tiêu độ trễ và thời gian còn lại của request. Đặt timeout quá dài làm tài nguyên bị giữ lâu; đặt quá ngắn gây hủy các request hợp lệ và tăng retry không cần thiết.

## 4. Dùng deadline tổng thể để tránh cộng dồn timeout

Nếu một request gọi nhiều dependency tuần tự, mỗi tầng đặt timeout riêng mà không xét thời gian đã dùng có thể khiến tổng thời gian vượt quá SLA của request.

Ví dụ, request có deadline 2 giây. Tầng A chờ tối đa 2 giây rồi tầng B lại chờ thêm 2 giây thì tổng thời gian có thể vượt 4 giây, chưa kể xử lý nội bộ.

Thay vào đó, tạo một deadline tổng thể và tính thời gian còn lại trước mỗi thao tác:

~~~java
import java.time.Duration;
import java.time.Instant;

Instant deadline = Instant.now().plusSeconds(2);

Duration remainingTime(Instant deadline) {
    Duration remaining = Duration.between(Instant.now(), deadline);
    if (remaining.isNegative() || remaining.isZero()) {
        throw new java.util.concurrent.CancellationException(
                "Request deadline exceeded");
    }
    return remaining;
}
~~~

Khi gọi dependency tiếp theo, dùng thời gian còn lại làm timeout cho lời gọi đó. Không đặt lại toàn bộ ngân sách thời gian ở mỗi tầng.

Trong hệ thống phân tán, deadline nên được truyền qua các tầng theo một định dạng và hợp đồng nhất quán. Khi nhận request đã gần hết deadline, ứng dụng có thể bỏ qua công việc không còn khả năng hoàn tất đúng hạn thay vì tiếp tục tiêu tốn tài nguyên.

Đồng hồ monotonic như System.nanoTime() phù hợp để đo thời lượng trong cùng tiến trình vì không bị điều chỉnh theo thời gian hệ thống. Instant hữu ích khi biểu diễn thời điểm deadline có thể truyền hoặc ghi log. Khi chỉ cần timeout cục bộ, nên tính elapsed time bằng nanoTime().

## 5. Giới hạn concurrency bằng Semaphore

Semaphore cho phép giới hạn số task cùng lúc đi vào một vùng tài nguyên. Ví dụ, chỉ cho tối đa 20 request đồng thời gọi một dependency:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

Semaphore dependencySlots = new Semaphore(20);

String callDependency() throws Exception {
    if (!dependencySlots.tryAcquire(100, TimeUnit.MILLISECONDS)) {
        throw new DependencyOverloadedException(
                "Dependency concurrency limit reached");
    }

    try {
        return invokeRemoteService();
    } finally {
        dependencySlots.release();
    }
}
~~~

tryAcquire(timeout, unit) chờ permit trong thời gian có giới hạn. Nếu không lấy được permit đúng hạn, ứng dụng có thể từ chối sớm, trả lỗi có thể retry hoặc dùng fallback phù hợp. finally bảo đảm permit được trả lại khi thao tác kết thúc hoặc ném exception.

Không dùng release() nếu task chưa lấy được permit. Đặt tryAcquire trước khối try-finally như ví dụ để chỉ trả permit mà task thực sự sở hữu.

### Semaphore và virtual thread

Khi dùng virtual-thread-per-task executor, có thể có nhiều virtual thread được tạo trong khi chỉ một số task được phép gọi dependency đồng thời. Các task còn lại có thể chờ permit:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (Request request : requests) {
        executor.submit(() -> {
            if (!dependencySlots.tryAcquire()) {
                recordRejectedRequest(request);
                return;
            }

            try {
                processWithDependency(request);
            } finally {
                dependencySlots.release();
            }
        });
    }
}
~~~

Ví dụ dùng tryAcquire() không chờ: task không lấy được permit được xử lý theo chính sách từ chối. Điều này tránh tạo một hàng dài virtual thread chỉ để chờ cùng một dependency.

Nếu dùng acquire() hoặc tryAcquire(timeout) trong từng virtual thread, thread chờ thường có chi phí thấp hơn platform thread đang bị block, nhưng số virtual thread và trạng thái request vẫn có thể tăng rất lớn. Vì vậy, giới hạn concurrency ở dependency chưa đủ nếu ứng dụng vẫn nhận và lưu một lượng task chờ không giới hạn. Cần thêm admission control ở đầu vào.

## 6. Admission control và load shedding

Admission control quyết định có nhận thêm công việc hay không trước khi tạo hoặc xếp hàng quá nhiều task. Khi hệ thống gần hết capacity, ứng dụng có thể:

- Từ chối request mới bằng phản hồi quá tải phù hợp.
- Giới hạn số request đang chờ bằng hàng đợi có capacity rõ ràng.
- Dừng nhận message mới hoặc giảm tốc độ consumer.
- Ưu tiên request quan trọng và bỏ công việc ít ưu tiên.
- Trả kết quả cache hoặc fallback nếu nghiệp vụ cho phép.

Load shedding là chủ động loại bỏ một phần tải khi không thể xử lý an toàn toàn bộ yêu cầu. Từ chối sớm thường tốt hơn nhận mọi request rồi để chúng chờ đến khi hết timeout, bởi request chờ vẫn chiếm bộ nhớ và có thể giữ các tài nguyên khác.

Ví dụ, có thể dùng semaphore ở ranh giới nhận công việc để giới hạn số request được đưa vào xử lý:

~~~java
Semaphore requestSlots = new Semaphore(200);

Response handle(Request request) {
    if (!requestSlots.tryAcquire()) {
        return Response.overloaded();
    }

    try {
        return process(request);
    } finally {
        requestSlots.release();
    }
}
~~~

Ở ví dụ này, tối đa 200 request cùng giữ slot trong phạm vi xử lý. Trong ứng dụng web thực tế, cần đặt semaphore tại đúng tầng có vòng đời request và bảo đảm permit được giải phóng sau khi xử lý hoàn tất, kể cả khi request bị hủy hoặc ném lỗi.

Một semaphore đơn lẻ không thay thế giới hạn kích thước hàng đợi, giới hạn body/request size hoặc rate limit. Cần chọn điểm admission phù hợp để từ chối trước khi tạo quá nhiều công việc phụ.

## 7. Bulkhead: cô lập các dependency và nhóm công việc

Bulkhead là nguyên tắc chia tài nguyên thành các vùng độc lập để sự cố của một dependency không chiếm hết capacity của toàn ứng dụng.

Ví dụ, payment service chậm không nên sử dụng hết tất cả permit dành cho inventory service. Có thể dùng semaphore riêng cho từng dependency:

~~~java
Semaphore paymentSlots = new Semaphore(20);
Semaphore inventorySlots = new Semaphore(50);
Semaphore profileSlots = new Semaphore(100);
~~~

Mỗi lời gọi chỉ sử dụng slot của dependency tương ứng. Khi payment chậm, các request thanh toán có thể bị giới hạn hoặc từ chối mà không lấy mất toàn bộ slot của inventory và profile.

Cần tránh dùng một semaphore toàn cục cho tất cả dependency nếu thời gian xử lý và capacity của chúng khác nhau. Giới hạn nên dựa trên quota, connection pool, throughput và SLA của từng hệ thống.

Bulkhead có thể được triển khai bằng semaphore, executor riêng, connection pool riêng hoặc các cơ chế cô lập tương ứng. Với virtual thread, thường không cần tạo một platform thread pool lớn chỉ để có một thread cho mỗi request; hãy cô lập tài nguyên thực sự có giới hạn.

## 8. Circuit breaker ngăn gọi dependency liên tục khi đang lỗi

Circuit breaker theo dõi kết quả gọi dependency và tạm ngừng gửi request khi tỷ lệ lỗi hoặc timeout vượt ngưỡng. Mô hình phổ biến có ba trạng thái:

| Trạng thái | Hành vi |
|---|---|
| Closed | Cho phép request đi qua và ghi nhận kết quả |
| Open | Từ chối nhanh hoặc dùng fallback, không gọi dependency |
| Half-open | Cho phép một số ít request thử lại để đánh giá dependency đã phục hồi chưa |

Luồng trạng thái:

~~~text
        lỗi/timeout vượt ngưỡng
Closed --------------------------> Open
  ^                                  |
  |                                  | hết thời gian chờ
  |                                  v
  +--------- thành công -------- Half-open
                 |
                 +-- tiếp tục lỗi --> Open
~~~

Circuit breaker khác timeout. Timeout dừng chờ một lời gọi quá lâu; circuit breaker ngăn ứng dụng tiếp tục gửi nhiều lời gọi khi dependency đã có dấu hiệu hỏng.

Java 21 không cung cấp một CircuitBreaker API chuẩn trong JDK. Có thể triển khai state machine phù hợp với nhu cầu hoặc sử dụng thư viện resilience đang được dự án hỗ trợ. Khi dùng thư viện, hãy kiểm tra phiên bản, cách đo failure rate, cửa sổ thống kê, số probe half-open và cách tích hợp timeout.

Không nên mở circuit chỉ vì một lỗi đơn lẻ không liên quan đến dependency, chẳng hạn lỗi validation của request. Cần phân loại lỗi: timeout, connection failure và một số mã phản hồi server có thể là lỗi dependency; lỗi đầu vào hoặc lỗi nghiệp vụ thường không nên tính vào failure rate của circuit breaker.

## 9. Retry có kiểm soát, backoff và jitter

Retry có thể giúp vượt qua lỗi tạm thời, nhưng retry quá nhanh hoặc quá nhiều có thể làm dependency đang chậm càng quá tải. Nếu mỗi request được thử lại nhiều lần, tổng số lời gọi có thể tăng theo cấp số nhân qua nhiều tầng.

Một chính sách retry an toàn cần:

- Chỉ retry lỗi có khả năng tạm thời, chẳng hạn một số lỗi kết nối hoặc phản hồi server.
- Chỉ retry thao tác có thể thực hiện lại an toàn; với thao tác ghi, cần idempotency key hoặc cơ chế chống ghi trùng.
- Giới hạn số lần thử và tổng thời gian retry.
- Dùng exponential backoff để tăng dần khoảng nghỉ.
- Thêm jitter để các client không đồng loạt retry cùng thời điểm.
- Tôn trọng deadline tổng thể và hướng dẫn retry từ dependency nếu có.

Ví dụ tính thời gian chờ có exponential backoff và jitter:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

Duration retryDelay(int attempt) {
    long baseMillis = 100;
    long maxMillis = 2_000;

    int exponent = Math.max(0, Math.min(attempt, 5));
    long cap = Math.min(maxMillis, baseMillis << exponent);

    long delay = ThreadLocalRandom.current()
            .nextLong(cap / 2 + 1, cap + 1);

    return Duration.ofMillis(delay);
}
~~~

Đây là cách tính delay minh họa; vòng retry vẫn phải kiểm tra deadline, số lần thử, loại exception và trạng thái circuit breaker. Không retry lỗi xác thực, lỗi validation hoặc thao tác không idempotent nếu không có bảo vệ phù hợp.

Nếu dependency trả Retry-After, ứng dụng cần cân nhắc giá trị đó trong chính sách retry. Không để từng tầng tự retry độc lập mà không có ngân sách chung, vì một request có thể tạo nhiều lần thử ở nhiều tầng.

## 10. Fallback và graceful degradation

Khi dependency chậm hoặc không khả dụng, một số chức năng có thể trả kết quả thay thế để giữ phần còn lại của ứng dụng hoạt động.

Ví dụ:

- Trả dữ liệu cache còn hiệu lực theo chính sách nghiệp vụ.
- Ẩn phần thông tin không bắt buộc thay vì làm hỏng toàn bộ trang.
- Trả trạng thái đang xử lý hoặc kết quả gần đúng nếu sản phẩm cho phép.
- Đưa tác vụ không khẩn cấp vào hàng đợi bền vững để xử lý sau.
- Từ chối chức năng phụ thuộc trực tiếp vào dependency nếu không có fallback an toàn.

Fallback phải rõ ràng về độ mới và tính chính xác của dữ liệu. Không trả dữ liệu cũ như dữ liệu mới nhất nếu điều đó có thể gây sai lệch nghiệp vụ. Với giao dịch thanh toán, tồn kho hoặc quyền truy cập, fallback tùy tiện có thể gây rủi ro lớn hơn việc trả lỗi.

Graceful degradation có nghĩa là giảm chức năng có kiểm soát khi một thành phần gặp sự cố, trong khi vẫn giữ các chức năng độc lập hoạt động.

## 11. Kết hợp timeout, bulkhead, circuit breaker và retry

Các cơ chế nên được sắp xếp thành một chính sách nhất quán. Một luồng tham khảo:

1. Admission control quyết định request có được nhận hay không.
2. Deadline tổng thể xác định thời gian tối đa còn lại.
3. Circuit breaker kiểm tra có nên gọi dependency hay từ chối nhanh.
4. Bulkhead/semaphore giới hạn số lời gọi đồng thời.
5. Timeout giới hạn thời gian chờ của từng lời gọi.
6. Retry chỉ thực hiện nếu lỗi tạm thời, thao tác an toàn và còn ngân sách deadline.
7. Fallback hoặc lỗi có kiểm soát được trả về khi không thể tiếp tục.

Một điểm thiết kế cần chú ý là thời gian chờ permit cũng tiêu thụ deadline. Không nên đợi semaphore quá lâu rồi mới bắt đầu request dependency với timeout đầy đủ như thể request vừa bắt đầu. Hãy trừ thời gian đã dùng khỏi deadline còn lại.

Không có thứ tự duy nhất đúng cho mọi hệ thống. Ví dụ, circuit breaker thường được kiểm tra trước khi chờ permit để tránh giữ slot trong lúc circuit đang mở; một số kiến trúc cần kiểm tra lại trạng thái trước khi thực sự gọi dependency. Hãy đặt các bước theo ranh giới tài nguyên và mục tiêu độ trễ của ứng dụng.

## 12. Ví dụ phối hợp giới hạn concurrency và timeout

Ví dụ sau minh họa một dependency được giới hạn số lời gọi đồng thời, có thời gian chờ permit ngắn và timeout cho HTTP request:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

class DependencyClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(1))
            .build();

    private final Semaphore slots = new Semaphore(20);

    String fetchStatus() throws Exception {
        if (!slots.tryAcquire(50, TimeUnit.MILLISECONDS)) {
            throw new DependencyOverloadedException();
        }

        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://service.example/status"))
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            if (response.statusCode() >= 500) {
                throw new IOException("Dependency server error");
            }

            return response.body();
        } finally {
            slots.release();
        }
    }
}
~~~

Ví dụ này có các giới hạn:

- Tối đa 20 lời gọi đang giữ permit.
- Task chỉ chờ permit tối đa 50 ms.
- Kết nối có timeout 1 giây.
- Request có timeout 2 giây.
- Permit luôn được trả lại khi lời gọi kết thúc hoặc ném lỗi.

DependencyOverloadedException trong ví dụ là exception nghiệp vụ do ứng dụng tự định nghĩa để biểu thị không lấy được slot đúng hạn. Trong ứng dụng thực tế, cần bổ sung phân loại status code, xử lý timeout, deadline tổng thể, circuit breaker và fallback theo hợp đồng API. Cũng cần cân nhắc giới hạn admission ở tầng nhận request để tránh tạo quá nhiều virtual thread chỉ để chờ permit.

## 13. Quan sát và xác định điểm nghẽn

Không thể điều chỉnh concurrency limit chỉ bằng cảm tính. Cần theo dõi cả ứng dụng và dependency.

Các chỉ số hữu ích:

| Chỉ số | Điều cần quan sát |
|---|---|
| Request rate | Số request đến và số request được chấp nhận mỗi giây |
| In-flight requests | Số request đang xử lý đồng thời |
| Permit utilization | Số permit đang dùng và thời gian chờ lấy permit |
| Queue depth | Số task đang chờ nếu hệ thống có hàng đợi |
| Latency percentile | p50, p95, p99 và timeout rate |
| Error rate | Lỗi kết nối, timeout, HTTP 5xx và lỗi nghiệp vụ |
| Retry count | Số lần retry trên mỗi request và tổng retry rate |
| Circuit state | Thời gian circuit ở closed/open/half-open |
| Dependency capacity | Connection pool, quota, CPU và throughput của dependency |
| Resource usage | Heap, allocation, socket, file descriptor và số virtual thread |

Khi dependency chậm, cần xác định bottleneck nằm ở mạng, connection pool, database, lock, CPU hay chính dịch vụ từ xa. Tăng số virtual thread hoặc tăng semaphore limit mà không xác định bottleneck có thể làm tình hình xấu hơn.

## 14. Quy trình phục hồi sau overload

Khi dependency bắt đầu phục hồi, không nên lập tức đưa toàn bộ tải đang chờ trở lại. Hãy khôi phục theo từng bước:

1. Từ chối hoặc giảm admission trong giai đoạn lỗi.
2. Cho circuit breaker chuyển sang half-open và chỉ gửi một số probe nhỏ.
3. Xác nhận dependency trả kết quả ổn định và latency nằm trong giới hạn.
4. Tăng dần concurrency hoặc tốc độ nhận tải nếu hệ thống hỗ trợ điều chỉnh.
5. Giữ retry budget thấp trong giai đoạn đầu để tránh tạo đợt tải thứ hai.
6. Theo dõi queue depth, error rate, latency và connection pool.
7. Chỉ khôi phục đầy đủ khi các chỉ số ổn định trong một khoảng thời gian phù hợp.

Nếu dùng message broker, cần điều chỉnh consumer concurrency hoặc tốc độ poll theo khả năng xử lý và dung lượng backlog. Nếu hàng đợi đã quá lớn, cần chính sách ưu tiên, hết hạn message hoặc loại bỏ công việc đã lỗi thời thay vì cố xử lý toàn bộ bất kể deadline.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ tăng số virtual thread khi dependency chậm | Tăng số task chờ và áp lực bộ nhớ | Giới hạn admission và concurrency |
| Không đặt timeout | Task giữ tài nguyên quá lâu | Đặt timeout cho từng thao tác I/O và deadline tổng thể |
| Dùng semaphore nhưng cho phép chờ vô hạn | Hình thành hàng đợi virtual thread không giới hạn | Dùng tryAcquire hoặc timeout và từ chối sớm |
| Retry ngay lập tức | Tạo retry storm và làm dependency quá tải hơn | Backoff, jitter, retry budget |
| Retry mọi loại lỗi | Lặp lại lỗi nghiệp vụ hoặc thao tác không an toàn | Phân loại lỗi và bảo đảm idempotency |
| Không cô lập dependency | Một dependency chậm chiếm capacity của các dependency khác | Bulkhead riêng theo dependency |
| Fallback không kiểm tra độ mới dữ liệu | Trả kết quả sai hoặc gây sai lệch nghiệp vụ | Đặt freshness policy và chỉ fallback khi an toàn |
| Mở circuit nhưng không có probe phục hồi | Dependency đã khỏe nhưng ứng dụng tiếp tục từ chối | Half-open với số probe giới hạn |
| Khôi phục toàn bộ tải cùng lúc | Dependency lại bị quá tải | Tăng tải dần và theo dõi chỉ số |

## Kết luận

Xử lý overload và phục hồi khi dependency chậm cần nhiều lớp bảo vệ. Java 21 cung cấp virtual thread và các API đồng thời hữu ích, nhưng ứng dụng vẫn phải chủ động kiểm soát admission, concurrency, timeout, cancellation và vòng đời task. Semaphore/bulkhead giới hạn tài nguyên dùng chung; circuit breaker ngăn gọi liên tục khi dependency lỗi; retry có backoff và jitter chỉ áp dụng cho lỗi tạm thời, thao tác an toàn; fallback giúp giảm chức năng có kiểm soát. Theo dõi latency, error rate, queue depth và dependency capacity để điều chỉnh tải và phục hồi từng bước.

## Tài liệu tham khảo

- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API — HttpRequest](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
