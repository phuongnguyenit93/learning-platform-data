# Truyền thời hạn xử lý xuyên chuỗi lời gọi

## 1. Vấn đề trong giao tiếp đồng bộ

Trong kiến trúc microservices, một request thường đi qua nhiều thành phần trước khi có kết quả:

~~~text
Client
   |
API Gateway
   |
Checkout Service
   |
   +--> Pricing Service
   |
   +--> Inventory Service
   |
   +--> Payment Service
~~~

Mỗi lời gọi mạng tiêu tốn thời gian truyền, chờ connection, đợi thread, đọc/ghi database và xử lý nghiệp vụ. Nếu mỗi dịch vụ đặt timeout riêng, các timeout đó không tự tạo thành giới hạn thời gian đầu cuối. Gateway có thể đã trả lỗi cho người dùng trong khi Checkout và Payment vẫn tiếp tục xử lý, chiếm tài nguyên hoặc thậm chí hoàn tất thao tác có hiệu ứng phụ.

**Truyền thời hạn xử lý** (*deadline propagation*) nghĩa là đưa giới hạn thời gian của một yêu cầu logic xuyên qua các lời gọi con. Mỗi hop tính thời gian còn lại rồi đặt timeout phù hợp cho công việc tiếp theo. Một hop không được tự ý cấp thêm thời gian vượt khỏi giới hạn đã nhận.

Mục tiêu của bài học:

- Phân biệt timeout, deadline, time budget, cancellation và SLO.
- Thiết kế deadline xuyên các lời gọi HTTP và gRPC.
- Tính thời gian còn lại cho chuỗi tuần tự, fan-out song song và retry.
- Tránh tiếp tục việc vô ích khi deadline đã hết.
- Xử lý an toàn thao tác đã commit nhưng caller bị timeout.
- Quan sát và kiểm thử việc truyền deadline thực tế.

**Nguyên tắc quan trọng:** deadline cho biết **caller không còn thời gian chờ**; nó không chứng minh công việc ở server chắc chắn đã thất bại hay được rollback.

## 2. Phân biệt timeout, deadline và các khái niệm liên quan

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Timeout** | Khoảng thời gian chờ tối đa của một thao tác cụ thể, tính từ khi thao tác bắt đầu | Chờ Inventory response tối đa 500 ms |
| **Deadline** | Thời điểm chót mà request cần hoàn tất theo hợp đồng | Request phải xong trước 10:00:01.500 UTC |
| **Remaining time / time budget** | Thời gian còn lại của deadline tại thời điểm hiện tại | Còn 270 ms để gọi Payment |
| **Cancellation** | Tín hiệu nỗ lực dừng thao tác không còn cần thiết | Caller đóng kết nối, hủy lời gọi con |
| **SLO latency** | Mục tiêu thống kê độ trễ dịch vụ trong cửa sổ đo | p95 dưới 600 ms trong 30 ngày |

Timeout là tương đối với **lần chờ đó**. Deadline là giới hạn được chia sẻ bởi **toàn bộ yêu cầu logic**. Một hệ thống có thể dùng cả hai: deadline bảo vệ thời gian đầu cuối, trong khi timeout mỗi dependency chặn lời gọi đơn lẻ quá chậm.

**SLO không phải deadline của từng request.** Ví dụ, mục tiêu p95 dưới 500 ms không có nghĩa mọi request phải bị hủy ở 500 ms. Deadline phải được chọn theo hành vi sản phẩm, trải nghiệm người dùng, chi phí tài nguyên, phân bố độ trễ và chính sách tải.

### 2.1. Vì sao timeout tại mỗi hop gây cộng dồn?

Giả sử Checkout gọi ba service tuần tự; mỗi lời gọi có timeout 1.000 ms:

~~~text
Checkout xử lý ban đầu:      200 ms
Pricing gần timeout:        950 ms
Inventory gần timeout:      950 ms
Payment gần timeout:        950 ms
Tổng hợp response:          100 ms
----------------------------------
Tổng thời gian:           3.150 ms
~~~

Không lời gọi nào vi phạm timeout riêng 1 giây, nhưng request mất hơn 3 giây. Nếu Gateway chỉ chờ 1.500 ms, Gateway đã trả lỗi trước khi Checkout hoàn thành.

Trong thực tế, tình huống này có thể dẫn đến hàng đợi dài, thread/connection pool bị giữ, tăng số retry, phát sinh lỗi dây chuyền và thực hiện các thao tác mà caller không còn đợi nữa.

### 2.2. Deadline dùng một thời điểm chung

~~~text
Request bắt đầu:   10:00:00.000 UTC
Deadline:          10:00:01.200 UTC

Gateway gọi A:     10:00:00.200 UTC   => còn 1.000 ms
A chuẩn bị gọi B:  10:00:00.720 UTC   => còn   480 ms
B chuẩn bị gọi C:  10:00:01.020 UTC   => còn   180 ms
~~~

Khi B gọi C, C không thể được cấp thêm một timeout 1 giây cho cùng request. Nếu cần dành 50 ms để B/A hoàn tất phản hồi, C chỉ có tối đa khoảng 130 ms. Nếu công việc C không thể hoàn tất hữu ích trong ngân sách đó, nên bỏ hoặc trả lỗi theo chính sách đã định.

## 3. Công thức ngân sách thời gian

Ký hiệu:

- **D**: thời điểm deadline hiệu lực.
- **now**: thời điểm hiện tại, được so sánh trên cơ sở đồng hồ phù hợp.
- **R**: thời gian còn lại.
- **M**: thời gian dự phòng (*safety margin*) để tổng hợp kết quả, giải phóng tài nguyên và phản hồi.
- **H**: timeout tối đa được cấu hình cho dependency.
- **T_child**: timeout áp dụng cho lời gọi con.

~~~text
R = max(0, D - now)

T_child = min(H, max(0, R - M))
~~~

Nếu **R <= M**, không nên khởi động công việc downstream mới. Cần phân biệt “budget bằng 0” với tham số timeout bằng 0: trong một số thư viện, **0 có thể có nghĩa là không giới hạn**, dẫn đến lỗi ngược mong muốn. Thực thi nên từ chối trước khi gọi client.

Phần dự phòng M không phải con số ngẫu nhiên. Nó có thể bao gồm ghi response, serialization, network response, commit ngắn, quan sát/tracing và dọn dẹp. Đặt quá nhỏ khiến request hết hạn ngay khi xử lý xong nghiệp vụ; đặt quá lớn có thể cắt công việc hữu ích sớm không cần thiết.

### 3.1. Ví dụ chia ngân sách theo thời gian thực

Giả sử Gateway nhận deadline đầu cuối 1.500 ms:

| Thời điểm | Đã tiêu | Ngân sách còn |
|---|---:|---:|
| Gateway nhận request | 0 ms | 1.500 ms |
| Xác thực tại Gateway | 100 ms | 1.400 ms |
| Checkout kiểm tra đầu vào | 160 ms | 1.240 ms |
| Checkout chuẩn bị gọi Inventory | 40 ms | 1.200 ms |
| Dự phòng phản hồi | 150 ms | Có thể cấp tối đa 1.050 ms |
| Inventory kết thúc | 600 ms | Còn 600 ms kể từ lúc gọi |
| Checkout hoàn tất | 200 ms | Còn khoảng 400 ms |

Nếu chính sách của Inventory client cho phép tối đa 800 ms thì gọi với **min(800, 1.050) = 800 ms**. Nếu lúc gọi chỉ còn 250 ms và cần reserve 70 ms, timeout tối đa là 180 ms.

Không nên định nghĩa một budget cứng cho từng bước rồi bỏ qua thời gian thực tế. Bước trước kết thúc sớm thì bước sau có thể dùng thời gian còn lại trong giới hạn của mình; bước trước chậm thì bước sau phải có deadline ngắn hơn hoặc bị bỏ qua.

## 4. Chọn điểm đặt deadline gốc

Deadline thường được quyết định ở một ranh giới đáng tin cậy: API Gateway, ingress hoặc service mở đầu workflow. Nó phải phù hợp mục tiêu kinh doanh và loại operation.

Ví dụ:

- API truy vấn thông tin cho giao diện có thể cần deadline ngắn.
- Tác vụ tải báo cáo có thể chuyển sang xử lý bất đồng bộ, trả trạng thái nhận lệnh sớm.
- Một lệnh thanh toán cần deadline chờ HTTP rõ, nhưng kết quả nghiệp vụ phải có cách truy vấn lại khi timeout.
- Job xử lý dài trong nền nên có thời hạn workflow riêng, không đơn giản kế thừa deadline 500 ms từ HTTP request đã nhận việc.

Người dùng bên ngoài có thể muốn rút ngắn deadline, nhưng không nên được tùy ý tăng nó vô hạn. Tại ingress, chặn bằng chính sách server:

~~~text
effectiveDeadline = min(
    deadline do upstream cung cấp,
    deadline tối đa do server chấp nhận
)
~~~

Nếu thiếu deadline, dùng giới hạn mặc định theo loại operation. Nếu deadline sai định dạng, trong quá khứ hoặc xa bất thường, hành vi từ chối hay clamp phải được quy định trong contract. **Không dùng giá trị header không đáng tin để cấp tài nguyên quá mức.**

## 5. Truyền deadline qua HTTP

HTTP không có một header deadline end-to-end phổ quát được tất cả framework và reverse proxy tự động hiểu. Nhóm phát triển có thể thiết lập hợp đồng nội bộ bằng header riêng.

### 5.1. Truyền thời điểm tuyệt đối

Ví dụ minh họa:

~~~http
GET /internal/inventory/SKU-42 HTTP/1.1
X-Request-Deadline: 2026-11-11T10:00:01.500Z
X-Correlation-Id: req_74ac
Authorization: Bearer <token>
~~~

**X-Request-Deadline là header minh họa do hệ thống tự định nghĩa**, không phải chuẩn mà mọi HTTP client biết cách xử lý. Tài liệu contract phải nêu:

- Định dạng UTC RFC 3339/ISO 8601; múi giờ và độ chính xác.
- Ai được quyền cung cấp header.
- Cách xử lý header thiếu, hỏng hoặc nằm ngoài giới hạn.
- Deadline nào có hiệu lực khi ingress, proxy và service có các cap khác nhau.
- Cách giảm deadline qua các hop và đo thời gian khi request chờ queue.
- Cách xử lý sai lệch đồng hồ giữa máy (*clock skew*).

Ở mỗi hop, đọc deadline có hiệu lực, tính remaining và truyền cùng deadline hoặc deadline **sớm hơn** theo policy. Không thay bằng “giờ hiện tại cộng timeout mặc định 1 giây” vì hành động đó có thể gia hạn request.

### 5.2. Truyền duration còn lại

Có hệ thống dùng một trường tương đối, ví dụ:

~~~http
X-Remaining-Budget-Ms: 420
~~~

Đây cũng là header tự định nghĩa. Ưu điểm là không phải trực tiếp so sánh wall clock giữa các máy. Nhược điểm: nếu bên nhận bắt đầu đếm lại từ lúc đọc header, thời gian transit, queue, proxy hoặc load balancer có thể không được trừ. Một chuỗi nhiều hop có thể chạy lâu hơn deadline của caller.

Nếu chọn duration, cần quy tắc rõ để trừ phần đã tiêu, tránh reset budget ở mỗi hop và tính đến chi phí truyền/queue. Với hợp đồng yêu cầu thời điểm chót chặt chẽ giữa nhiều máy, cần chiến lược đồng bộ thời gian hoặc hỗ trợ deadline của giao thức đủ rõ; không thể giả định duration tự bảo đảm chính xác tuyệt đối.

### 5.3. Không nhầm trace context với deadline

Header **traceparent** trong W3C Trace Context truyền thông tin nhận dạng trace/span, không tự chứa deadline. **Correlation ID**, **trace ID**, **deadline** và **idempotency key** là các khái niệm có vai trò khác nhau. Hãy truyền, kiểm tra và quan sát chúng theo đúng hợp đồng; tránh nhét các giá trị riêng vào trường không được thiết kế cho mục đích ấy.

## 6. gRPC hỗ trợ deadline như thế nào?

gRPC có cơ chế deadline được sử dụng qua API client và trạng thái **DEADLINE_EXCEEDED**. Tùy ngôn ngữ, phiên bản và cấu hình, propagation đến lời gọi con có thể được hỗ trợ bởi context/interceptor. Không mặc định tất cả các runtime tự động giữ deadline ở mọi đường bất đồng bộ hoặc thread mới.

Ví dụ Java khi gọi stub:

~~~java
import java.util.concurrent.TimeUnit;

// remainingMillis phải đến từ deadline đã được chấp nhận.
if (remainingMillis <= 0L) {
    throw new IllegalStateException("Request deadline exceeded");
}

InventoryReply result = inventoryStub
    .withDeadlineAfter(remainingMillis, TimeUnit.MILLISECONDS)
    .checkInventory(request);
~~~

Khi có hạn thời gian toàn chuỗi, mỗi lời gọi gRPC con phải được ràng buộc bởi remaining budget tại thời điểm gọi. Nên dùng cơ chế **io.grpc.Context** và Deadline khi phù hợp với ứng dụng, đồng thời thử nghiệm việc context được truyền qua executor, callback và lời gọi nested.

Deadline ở client có thể hết trước khi server nhận được tín hiệu cancellation. **DEADLINE_EXCEEDED không chứng minh tác vụ server chưa thực hiện side effect.**

## 7. Dùng đồng hồ đơn điệu bên trong một tiến trình

Có hai mục đích khác nhau:

1. **Thời điểm tuyệt đối trên dây và trong log:** thường biểu diễn bằng UTC timestamp, có thể dùng **Instant**.
2. **Thời gian đã trôi và remaining cục bộ:** nên dùng đồng hồ đơn điệu như **System.nanoTime()**, tránh việc đồng hồ hệ thống bị chỉnh tiến/lùi.

Khi nhận absolute deadline, server so sánh với thời gian hiện tại, áp giới hạn cấu hình và quy đổi thành budget cục bộ. Sau đó dùng monotonic clock để tính elapsed. Cách này không xóa được clock skew giữa hai máy, nhưng tránh sai lệch do wall clock thay đổi trong suốt quá trình xử lý trên cùng máy.

### 7.1. Ví dụ Java: đối tượng RequestBudget

~~~java
import java.time.Duration;

public final class RequestBudget {
    private final long startNanos;
    private final long allowedNanos;

    public RequestBudget(Duration allowed) {
        if (allowed.isZero() || allowed.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        // Trước khi gọi, clamp Duration để toNanos() không overflow.
        this.allowedNanos = allowed.toNanos();
        this.startNanos = System.nanoTime();
    }

    public Duration remaining() {
        long elapsed = Math.max(0L, System.nanoTime() - startNanos);
        long left = Math.max(0L, allowedNanos - elapsed);
        return Duration.ofNanos(left);
    }

    public Duration childTimeout(Duration cap, Duration reserve) {
        long available = remaining().toNanos() - reserve.toNanos();
        long bounded = Math.min(cap.toNanos(), available);

        if (bounded <= 0L) {
            throw new DeadlineExceededException("No time left for child");
        }
        return Duration.ofNanos(bounded);
    }

    public static final class DeadlineExceededException
            extends RuntimeException {
        public DeadlineExceededException(String message) {
            super(message);
        }
    }
}
~~~

Đoạn code minh họa cơ chế cục bộ; caller phải kiểm tra duration dương, giới hạn giá trị để tránh overflow và thiết lập cơ chế cancellation/response error riêng. Nó **không tự** đưa deadline qua mạng.

### 7.2. Chuyển deadline từ HTTP vào RequestBudget

~~~java
import java.time.Duration;
import java.time.Instant;

Instant requested = Instant.parse(deadlineHeader);
Instant receivedAt = Instant.now();

Duration remaining = Duration.between(receivedAt, requested);
Duration serverMaximum = Duration.ofSeconds(2);

if (remaining.isZero() || remaining.isNegative()) {
    throw new RequestBudget.DeadlineExceededException(
        "Request already expired"
    );
}

Duration accepted = remaining.compareTo(serverMaximum) < 0
    ? remaining
    : serverMaximum;

RequestBudget budget = new RequestBudget(accepted);
~~~

Khi muốn truyền tiếp absolute deadline, hãy sử dụng **deadline hiệu lực** đã chấp nhận, tính toán sao cho không muộn hơn deadline upstream. Không gửi một absolute deadline mới được tạo từ timeout mặc định mà vô tình kéo dài thời hạn.

## 8. HTTP client Java phải áp timeout cho lời gọi con

Ví dụ dùng **java.net.http.HttpClient** trong Java 21:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;

public final class InventoryClient {
    private final HttpClient client;

    public InventoryClient(HttpClient client) {
        this.client = client;
    }

    public String fetch(
            String sku,
            RequestBudget budget,
            Instant effectiveDeadline
    ) throws Exception {
        Duration timeout = budget.childTimeout(
            Duration.ofMillis(800),  // Dependency cap
            Duration.ofMillis(50)    // Reserve for caller response
        );

        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create("https://inventory.internal/v1/stock/" + sku))
            .header("X-Request-Deadline", effectiveDeadline.toString())
            .timeout(timeout)
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req,
            HttpResponse.BodyHandlers.ofString()
        );

        if (res.statusCode() != 200) {
            throw new IllegalStateException(
                "Inventory returned " + res.statusCode()
            );
        }
        return res.body();
    }
}
~~~

Chú thích thực thi:

- Địa chỉ, bảo mật, encoding URL và kiểu lỗi ở đây được đơn giản hóa để tập trung vào deadline.
- **timeout** áp cho lời gọi Inventory, nhưng **effectiveDeadline** tiếp tục được chuyển qua header nội bộ.
- Trước mỗi lời gọi khác hoặc retry, phải tính lại **remaining**.
- Nếu thời gian quá ít, từ chối trước khi dựng request.
- Timeout ở client không bắt server từ xa rollback tự động.

Với Spring Boot, cùng nguyên tắc có thể được áp dụng qua **RestClient**, **WebClient**, OpenFeign hay gRPC với timeout/interceptor phù hợp. Phải kiểm tra từng lớp: connect timeout, response timeout, read timeout, acquisition timeout của connection pool và deadline toàn operation không nhất thiết có phạm vi giống nhau.

## 9. Truyền deadline qua các bước bên trong service

Một request có thể chờ đáng kể trước khi gọi network:

- Queue của executor hoặc thread pool.
- Connection pool của HTTP client.
- Connection pool của JDBC/ORM.
- Lock database, transaction hoặc truy vấn SQL.
- Rate limiter, semaphore, bulkhead.
- Xử lý CPU nặng và serialization.

Nếu chỉ đặt timeout cho RPC mà không tính **pool wait** hoặc **queue wait**, request vẫn có thể vượt deadline. Trước khi bắt đầu bước đắt đỏ, kiểm tra budget; nếu đã hết thì dừng sớm. Cần cấu hình timeout tương ứng ở tầng DB, HTTP client và bộ giới hạn concurrency.

~~~java
Duration remaining = budget.remaining();

if (remaining.isZero() || remaining.isNegative()) {
    throw new RequestBudget.DeadlineExceededException(
        "Deadline elapsed before database call"
    );
}

// Cấu hình query/lock timeout theo remaining và khả năng của JDBC driver.
// Sau khi truy vấn xong, kiểm tra lại trước lời gọi downstream kế tiếp.
~~~

Không phải mọi JDBC driver đều hủy ngay truy vấn khi timeout và không phải mọi cancellation đều giải phóng lock tức thì. Cần kiểm thử bằng DB/driver/transaction manager thực tế.

### 9.1. Mất context sau khi đổi thread

Nếu một service lưu deadline trong **ThreadLocal**, việc chuyển sang executor, CompletableFuture hoặc luồng reactive có thể làm mất nó. Lời gọi mới sau đó có thể dùng default timeout dài, kéo dài request quá mức.

Giải pháp:

- Truyền **RequestBudget** tường minh khi hợp lý.
- Dùng context chính thức của framework, ví dụ Reactor Context hoặc gRPC Context.
- Đặt filter/interceptor cho outbound clients để lấy remaining.
- Kiểm thử việc truyền context qua callback, async handoff và fan-out.
- Ghi metric phát hiện deadline bị thiếu bất thường ở các hop nội bộ.

## 10. Fan-out: các lời gọi đồng thời dùng cùng deadline

Checkout có thể gọi Pricing và Inventory **song song**:

~~~text
               +---> Pricing ------+
Checkout ------|                   +---> Tổng hợp response
               +---> Inventory ---+
~~~

Mỗi nhánh có thể được cấp thời gian tối đa theo **cùng deadline chung**, trừ dự phòng và cap riêng của dependency. Thời gian đầu cuối của fan-out thường chịu ảnh hưởng của nhánh chậm nhất, chưa kể chi phí tổng hợp; không lấy tổng các timeout để ước lượng thời gian thực tế của nhánh chạy song song.

Ví dụ:

~~~text
Remaining tại lúc fan-out: 700 ms
Reserve để tổng hợp và phản hồi: 80 ms

Pricing cap:   300 ms => timeout <= 300 ms
Inventory cap: 600 ms => timeout <= 600 ms
~~~

Nếu Inventory mất hơn 600 ms, Checkout không nên tiếp tục chờ theo một timeout mới chỉ vì Pricing đã trả về. Quy định rõ điều kiện thành công:

1. **All-or-nothing:** thiếu bất kỳ kết quả bắt buộc nào thì request không thể hoàn thành.
2. **Fallback:** chỉ dùng cache hoặc mặc định khi nghiệp vụ cho phép; công bố độ mới và giới hạn sai số.
3. **Partial response:** chỉ dùng nếu API hỗ trợ trạng thái kết quả một phần.
4. **Quorum:** áp dụng khi nghiệp vụ có semantics quorum thật, không dùng tùy tiện cho thanh toán hoặc bất biến tồn kho.

Khi không còn cần các nhánh chậm, hủy chúng nếu thư viện hỗ trợ. Cancellation là best effort; nhánh remote có thể đã hoàn tất hoặc tạo side effect.

## 11. Retry luôn tiêu cùng ngân sách

Nếu lời gọi đầu tiên timeout sau 500 ms, không được cho attempt tiếp theo lại nhận 500 ms chỉ vì cấu hình mặc định của dependency như vậy. Trước **mỗi attempt**, tính remaining, trừ dự phòng và backoff có thể có.

| Mốc | Remaining | Xử lý |
|---|---:|---|
| Trước attempt 1 | 900 ms | Có thể cho tối đa 550 ms |
| Attempt 1 timeout | 350 ms | Cân nhắc lỗi có thể retry không |
| Backoff có jitter | 100 ms | Còn 250 ms |
| Reserve phản hồi | 100 ms | Còn tối đa 150 ms |
| Attempt 2 cần ít nhất 300 ms để hữu ích | 150 ms | Không retry; kết thúc có kiểm soát |

Dữ liệu chỉ minh họa. Không có nghĩa thời lượng cần thiết của một dependency luôn xác định trước. Quyết định retry cần dựa trên kết quả thực tế, failure mode, idempotency, ngân sách còn lại và retry policy.

### 11.1. Retry khuếch đại ở nhiều tầng

Nếu Gateway retry 3 lần, Checkout retry 3 lần và Inventory retry 3 lần, dependency cuối có thể nhận nhiều attempt tăng theo cấp số nhân. Chọn tầng chịu trách nhiệm retry, đặt giới hạn số attempt toàn chuỗi và quan sát retry amplification.

Deadline giúp giới hạn thời gian retry nhưng **không thay thế** retry budget, rate limiting, circuit breaker hoặc load shedding.

### 11.2. Hedging phải có policy

Hedged requests chạy nhiều attempt chồng lấn để giảm tail latency. Điều này tăng tải và có thể lặp side effect. Chỉ dùng với operation an toàn hoặc có idempotency đầy đủ, giới hạn concurrency và tất cả attempt vẫn phải cùng chia sẻ deadline gốc.

## 12. Hết deadline và side effect: nguy cơ lớn nhất

Xét ví dụ thanh toán:

~~~text
t =   0 ms: Checkout gửi lệnh tạo authorization
t = 480 ms: Payment đã commit authorization
t = 500 ms: Checkout timeout, chưa nhận response
t = 520 ms: Payment cố gửi response nhưng kết nối đã đóng
~~~

Checkout **không thể kết luận authorization thất bại**. Timeout chỉ cho biết caller hết thời gian chờ; kết quả nghiệp vụ hiện chưa xác định với caller.

Hợp đồng của operation có hiệu ứng phụ phải bao gồm:

- **Idempotency key:** nhận diện cùng một thao tác logic khi retry.
- **Phạm vi và thời hạn key:** theo caller, operation và thời gian lưu giữ.
- **Trạng thái có thể truy vấn:** payment/command ID, operation status hoặc reconciliation endpoint.
- **Trạng thái tạm:** PENDING/UNKNOWN khi chưa xác minh kết quả.
- **Chính sách đối soát:** khi nào poll, retry an toàn hoặc escalte.
- **Bù trừ:** nếu cần hủy một thao tác đã thành công, phải có workflow nghiệp vụ rõ.

Không dùng cancellation để suy ra rollback. Một số thao tác đã vượt điểm commit hoặc gửi lệnh tới bên thứ ba nên vẫn tiếp tục ngay cả khi caller rời đi. Nếu cần hoàn thành điều đó, hãy chuyển trách nhiệm cho workflow có hạn riêng và cơ chế quan sát riêng.

### 12.1. Cancellation là nỗ lực dừng

**Deadline** là giới hạn thời gian. **Cancellation** là tín hiệu cố dừng công việc. Có thể xảy ra đồng thời nhưng không tương đương.

Khi caller mất kết nối, framework có thể hủy stream/call. Server cần kiểm tra cancellation token/context tại điểm phù hợp, ngừng công việc chưa bắt đầu và giải phóng tài nguyên. Tuy nhiên, nếu transaction hoặc side effect đã commit, cần hoàn tất trạng thái nhất quán, không hứa “hủy đồng nghĩa chưa thay đổi dữ liệu”.

### 12.2. Đồng bộ và bất đồng bộ là hai vòng đời khác nhau

API nhận một export job có thể trả HTTP **202 Accepted** trong 300 ms và job chạy 10 phút. Deadline của HTTP request chi phối giai đoạn **nhận việc**, trong khi job có lifecycle, timeout, retry, dead-letter và SLO riêng.

~~~http
POST /exports
HTTP/1.1

-> 202 Accepted
Location: /exports/jobs/job-123
~~~

Không copy deadline 300 ms sang job 10 phút rồi làm nó hết hạn trước khi bắt đầu. Với message async, phải xác định rõ deadline/TTL dành cho **thời điểm nhận**, **bắt đầu xử lý**, **hoàn tất xử lý** hay **độ mới dữ liệu**.

## 13. Trả lỗi như thế nào?

Không có một HTTP status chuẩn duy nhất biểu diễn mọi trường hợp “deadline đã hết” trong một ứng dụng. Phân biệt timeout phía client, gateway và service nghiệp vụ.

| Giao thức / tầng | Tình huống | Biểu diễn thường gặp |
|---|---|---|
| gRPC | Request vượt deadline | DEADLINE_EXCEEDED |
| gRPC | Caller hủy request | CANCELLED |
| HTTP gateway | Gateway timeout khi chờ upstream | 504 Gateway Timeout |
| HTTP service | Không khả dụng/quá tải tạm thời | 503 Service Unavailable khi phù hợp |
| HTTP client | Timeout chờ request | Exception/timeout cục bộ, có thể không có response HTTP |
| Proxy log | Client đóng kết nối | Một số proxy ghi 499, không phải HTTP status chuẩn |

Mọi operation cần công bố mã lỗi, điều kiện retry, cách truy vấn trạng thái và liệu timeout có thể đi kèm side effect đã thành công. Nếu server từ chối **ngay tại ingress** vì deadline quá ngắn, hãy chọn và thống nhất error code nội bộ phù hợp thay vì gán 504 cho mọi tình huống.

## 14. Clock skew và deadline xuyên nhiều máy

Khi truyền absolute timestamp, các máy cần đồng bộ giờ đủ tốt. Máy nhanh hơn 200 ms có thể cắt request sớm; máy chậm hơn có thể cho xử lý quá deadline.

Cần:

1. Đồng bộ thời gian bằng hạ tầng của tổ chức và theo dõi sai lệch.
2. Xác định sai số chấp nhận được với deadline gần sát thời điểm hiện tại.
3. Dùng monotonic clock để đo elapsed trong một tiến trình.
4. Đặt guard band hợp lý cho network/queue và độ trễ phản hồi.
5. Kiểm tra deadline quá xa, sai timezone hoặc không parse được.
6. Không giả định mô hình duration tương đối giải quyết hoàn toàn transit latency.

Cả clock skew và việc mạng chậm đều ảnh hưởng đến thời hạn thực tế. Mô hình truyền deadline cần được kiểm tra end-to-end, không chỉ trong unit test của một hàm chuyển timestamp.

## 15. Proxy, pool và các timeout khác

Một chuỗi có thể có nhiều giới hạn:

~~~text
Client request timeout
     |
Gateway / load balancer timeout
     |
Ingress / service mesh timeout
     |
Service request deadline
     |
Connection pool acquire timeout
     |
HTTP client connect / response timeout
     |
Database lock / query timeout
~~~

Cấu hình phải nhất quán về mục đích. Nếu Gateway ngắt sau 800 ms nhưng service cho downstream chạy 2 giây, việc truyền deadline không đạt hiệu quả. Nếu HTTP client chỉ bắt đầu đo response timeout **sau khi lấy được connection**, 500 ms đợi pool cộng 700 ms xử lý có thể vượt deadline 1 giây.

Không nhất thiết mọi timeout phải có cùng giá trị. Cần biết chúng bao phủ **giai đoạn nào**, và bảo đảm mọi thời gian chờ được tính trong request budget chung.

Không đặt vô hạn thread/connection queue chỉ vì downstream timeout đã được cấu hình. Khi tải vượt khả năng xử lý, load shedding sớm thường tốt hơn việc giữ công việc đến sau deadline.

## 16. Quan sát deadline trong tracing và metrics

Distributed tracing cho thấy toàn bộ chuỗi lời gọi:

~~~text
Trace: request đặt hàng

Gateway       [ 100 ms ]
Checkout      [           280 ms            ]
  Pricing     [  110 ms  ]
  Inventory   [       250 ms      ]
  Payment     [          timeout 300 ms      ]
~~~

Có thể ghi thêm thuộc tính nội bộ trên span:

- **request.deadline.utc:** deadline hiệu lực tại ingress.
- **request.remaining_ms_at_start:** ngân sách khi bắt đầu span.
- **rpc.effective_timeout_ms:** timeout thật đã cấp cho attempt.
- **rpc.retry_attempt:** lần retry.
- **rpc.queue_wait_ms:** thời gian đợi queue/pool.
- **request.deadline_exceeded:** kết thúc vì vượt deadline.
- **request.cancel_requested:** nhận yêu cầu hủy hay chưa.

Đây là **ví dụ tên thuộc tính do hệ thống thiết kế**, không khẳng định tất cả là semantic convention chuẩn của OpenTelemetry. Không ghi bearer token, dữ liệu thanh toán hoặc PII vào trace.

Các metric đáng theo dõi:

| Chỉ số | Giá trị chẩn đoán |
|---|---|
| End-to-end latency p50/p95/p99 | Mức trễ người dùng thực sự thấy |
| Deadline exceeded rate | Phần request vượt thời hạn |
| Remaining budget theo hop | Hop nào tiêu phần lớn thời gian |
| Timeout và retry count | Dependency chậm, retry storm |
| Queue/pool wait | Thời gian mất trước khi thực thi |
| Cancellation handling | Có ngừng công việc không cần thiết hay không |
| Work chạy sau caller timeout | Phát hiện orphaned work |
| Unknown side-effect outcomes | Số giao dịch cần đối soát |
| SLO/error budget burn | Ảnh hưởng chất lượng vận hành |

Đặt cảnh báo khi timeout tăng cùng queue depth hoặc retry rate. Chỉ đếm timeout mà không đo side effect sau timeout có thể che mất lỗi nghiêm trọng trong hệ thống giao dịch.

## 17. Một số sai lầm thường gặp

**Sai lầm 1: Mỗi service tự đặt timeout 1 giây.** Kết quả: deadline bị reset, tổng trễ cộng dồn. Cách khắc phục: truyền deadline và tính remaining trước mỗi hop.

**Sai lầm 2: Chỉ truyền deadline ở HTTP header.** Code bên trong vẫn đợi connection pool, lock hoặc DB vô hạn. Cách khắc phục: dùng remaining cho queue, pool, DB và các lời gọi con.

**Sai lầm 3: Dùng đồng hồ wall clock cho elapsed.** Hệ điều hành chỉnh giờ có thể làm budget tăng/giảm không hợp lý. Cách khắc phục: chuyển thành budget local đo bằng monotonic clock.

**Sai lầm 4: Cho mỗi retry một timeout đầy đủ.** Có thể kéo request dài gấp nhiều lần. Cách khắc phục: retry chỉ dùng phần ngân sách còn lại và bị giới hạn bởi số attempt.

**Sai lầm 5: Gộp cancellation với rollback.** Caller timeout nhưng Payment đã thành công. Cách khắc phục: idempotency, trạng thái UNKNOWN/PENDING và reconciliation.

**Sai lầm 6: Mất context khi đổi thread.** Deadline ở HTTP filter không đi theo CompletableFuture/queue. Cách khắc phục: context propagation rõ ràng và kiểm thử async handoff.

**Sai lầm 7: Copy deadline HTTP cho background job.** Job dài bị hủy sai, hoặc job âm thầm kéo dài request. Cách khắc phục: tách deadline cho API nhận lệnh và lifecycle workflow.

**Sai lầm 8: Dùng thời gian tuyệt đối nhưng bỏ qua clock skew.** Service khác host có thể tự đánh giá deadline sai. Cách khắc phục: hạ tầng đồng bộ giờ và chính sách guard band.

**Sai lầm 9: Truyền duration không tính network transit.** Nhiều hop bắt đầu lại countdown và làm tổng thời gian vượt giới hạn. Cách khắc phục: thiết kế semantics, giảm budget đúng và kiểm thử xuyên mạng.

**Sai lầm 10: Chọn deadline quá ngắn chỉ để có p95 đẹp.** Request bị cắt trước khi có thể hoàn thành, tỷ lệ lỗi tăng. Cách khắc phục: đo phân bố, đặt target theo yêu cầu sản phẩm, theo dõi đồng thời latency và success rate.

## 18. Thiết kế kiểm thử deadline propagation

| Kịch bản | Dàn dựng | Kết quả cần quan sát |
|---|---|---|
| Deadline đủ rộng | Downstream trả nhanh | Thành công; deadline không được tăng ở hop sau |
| Deadline hết tại ingress | Gửi thời điểm quá khứ | Từ chối sớm, không gọi dependency |
| Chỉ còn ít thời gian | Thêm chờ queue | Không mở RPC mới khi không đủ budget |
| Gọi tuần tự | Hop A tiêu 300 ms rồi gọi B | B nhận ít budget hơn A |
| Fan-out | Một nhánh rất chậm | Fan-in dừng theo deadline và cancel nhánh thừa khi hỗ trợ |
| Retry | Attempt 1 tốn phần lớn budget | Attempt 2 không reset timeout |
| Async handoff | Chuyển executor/thread | Deadline vẫn nằm trong context |
| Chờ connection pool | Làm pool cạn | Thời gian chờ pool có tính vào budget |
| Clock skew | Giả lập lệch đồng hồ host | Hệ thống xử lý hoặc phát hiện sai lệch theo policy |
| Client ngắt | Đóng kết nối giữa chừng | Không sinh công việc vô ích mới |
| Commit rồi mất response | Payment commit trước timeout | Retry an toàn, không tạo side effect kép |
| Job nhận qua 202 | Client timeout sau khi đã nhận việc | Job theo lifecycle và hạn riêng |

### 18.1. Test không reset deadline

Ingress đặt deadline sau 1.000 ms. Hop A chờ 350 ms rồi gọi B. B phải nhận tối đa khoảng 650 ms (còn trừ reserve nếu có), không nhận một timeout mới đầy đủ 1.000 ms. Có thể dùng fake clock hoặc controllable server để test deterministically.

### 18.2. Test timeout sau commit

Server ghi reservation thành công rồi giả lập mất response. Client retry cùng idempotency key trong thời hạn hiệu lực. Kỳ vọng chỉ có **một** reservation và client truy vấn lại được trạng thái. Đây là test nghiệp vụ, không chỉ là test timeout exception.

### 18.3. Test quá tải và pool

Giới hạn connection/thread pool rồi tạo đủ request để queue xuất hiện. Đo số request bị loại sớm, độ dài queue, thời gian giữ tài nguyên, p99 latency và số retry. Mục tiêu là tránh tích tụ những request đã quá thời hạn, không chỉ thấy timeout ở phía client.

## 19. Mẫu tài liệu deadline contract

~~~markdown
# Deadline Contract: <Caller> -> <Callee>

Nghiệp vụ và loại operation:
- Đọc / ghi, idempotent hay không:
- Side effect có thể tồn tại sau timeout không:
- Ai là chủ kết quả và cơ chế truy vấn trạng thái:

Ingress:
- Deadline/timeout mặc định:
- Deadline tối đa được server chấp nhận:
- Ai được phép cung cấp thời hạn:
- Xử lý thiếu/sai/quá hạn:

Propagation:
- Giao thức HTTP/gRPC:
- Header/metadata và format, đơn vị, timezone:
- Clock skew và guard band:
- Cách tính remaining:
- Reserve để tổng hợp/trả kết quả:

Tầng thực thi:
- Connection pool / queue / DB budget:
- Timeout tối đa theo dependency:
- Retry, backoff, số attempt:
- Fan-out, partial result và fallback:
- Cancellation và giới hạn thực thi:

Khi hết hạn:
- Error/status:
- Idempotency key và thời gian giữ:
- Lookup/reconciliation sau unknown outcome:
- Background workflow nếu có:

Vận hành:
- SLI/SLO và error budget:
- Metrics/traces/alerts:
- Test multi-hop, retry, timeout sau commit:
- Người phụ trách, ngày xem lại:
~~~

Nên cập nhật tài liệu này cùng cấu hình ở Gateway, service mesh, HTTP client, DB driver và service. Một tài liệu đúng trên giấy nhưng timeout tại proxy ngắn hơn cam kết sẽ làm deadline propagation không có tác dụng như dự kiến.

## 20. Bài tập thực hành

Giả sử một hệ thống đặt vé có deadline **1.800 ms** từ Gateway. Gateway đã tiêu 120 ms; Booking Service xử lý validation và nghiệp vụ nội bộ mất 230 ms; cần dành dự phòng 150 ms để phản hồi. Booking gọi **SeatAvailability** rồi **PaymentAuthorization** tuần tự. SeatAvailability có timeout cấu hình tối đa 700 ms, PaymentAuthorization tối đa 900 ms.

1. Tính remaining ngay trước khi Booking gọi SeatAvailability.
2. Tính timeout lớn nhất dành cho SeatAvailability sau khi trừ reserve.
3. Nếu SeatAvailability thực tế tốn 520 ms, còn bao nhiêu budget trước PaymentAuthorization? Timeout Payment tối đa là bao nhiêu?
4. Nếu Payment đã commit authorization nhưng Booking timeout, có thể kết luận thanh toán thất bại không? Thiết kế idempotency và status lookup.
5. Nếu đổi SeatAvailability và PaymentAuthorization sang chạy song song, điều kiện nghiệp vụ nào phải được chứng minh trước? Cách fan-in và cancellation thay đổi ra sao?
6. Nêu hai test xác minh deadline không bị reset sau hop và retry.

**Gợi ý phép tính** (bỏ qua network overhead khác để đơn giản):

~~~text
Ban đầu:                              1.800 ms
Sau Gateway 120 ms:                    1.680 ms
Sau Booking 230 ms:                    1.450 ms

Timeout SeatAvailability
  = min(700, 1450 - 150)               = 700 ms

SeatAvailability thực tế 520 ms:
Remaining trước Payment               = 930 ms

Timeout PaymentAuthorization
  = min(900, 930 - 150)                = 780 ms
~~~

Tất cả con số trong bài tập là giả định để thực hành, không phải timeout mặc định cho hệ thống production.

## 21. Checklist trước khi áp dụng

- [ ] Deadline gốc được xác định tại ingress từ chính sách đáng tin cậy.
- [ ] Phân biệt rõ deadline toàn chuỗi, timeout từng hop, connect/read timeout và SLO.
- [ ] Mỗi hop truyền thời hạn bằng hoặc sớm hơn thời hạn kế thừa.
- [ ] HTTP header/gRPC metadata có định dạng, đơn vị và policy rõ.
- [ ] Thiếu, sai, quá hạn hoặc quá xa được xử lý nhất quán.
- [ ] Clock skew được kiểm soát; elapsed local dùng monotonic clock.
- [ ] Queue, pool, DB, RPC và retry đều kiểm tra remaining.
- [ ] Retry không reset ngân sách; số attempt toàn chuỗi được giới hạn.
- [ ] Fan-out có budget, fan-in và cancellation rõ.
- [ ] Các thao tác side effect có idempotency, trạng thái và reconciliation.
- [ ] Workflow async có deadline và SLO riêng.
- [ ] Proxy/gateway timeout phù hợp với hợp đồng service.
- [ ] Metrics/traces cho thấy timeout, remaining, retry, queue và orphaned work.
- [ ] Có test multi-hop, clock skew, timeout sau commit và quá tải.

## 22. Ghi nhớ

**Deadline propagation giúp một request duy trì cùng giới hạn thời gian khi đi qua nhiều microservice.** Mỗi hop chỉ được dùng ngân sách còn lại và phải tính thời gian đã mất trong network, queue, pool, DB, retry và xử lý nội bộ. Hết deadline không đồng nghĩa side effect đã rollback; muốn vận hành an toàn cần idempotency, trạng thái có thể truy vấn và cancellation có giới hạn. Một thiết kế tốt kết hợp deadline rõ ràng với metrics, tracing, kiểm thử lỗi và chính sách load shedding để bảo vệ cả trải nghiệm người dùng lẫn tài nguyên hệ thống.
