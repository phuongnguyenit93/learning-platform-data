# Thiết kế ngân sách timeout theo đường đi của yêu cầu

Trong kiến trúc microservices, một yêu cầu HTTP có thể đi qua API Gateway, nhiều service, cơ sở dữ liệu và hệ thống bên ngoài. Nếu mỗi thành phần tự chọn timeout mà không xét thời gian còn lại của toàn bộ yêu cầu, hệ thống có thể tiếp tục xử lý sau khi người dùng đã bỏ cuộc, retry quá nhiều lần hoặc giữ tài nguyên cho những kết quả không còn giá trị.

**Ngân sách timeout (timeout budget)** là khoảng thời gian hữu hạn dành cho toàn bộ đường đi của một yêu cầu, được phân bổ và cập nhật khi yêu cầu đi qua từng bước. Thiết kế tốt bắt đầu từ **deadline đầu cuối**, rồi giới hạn mỗi thao tác theo **thời gian thực sự còn lại**.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Phân biệt latency SLO, timeout, deadline, budget, cancellation và retry budget.
- Vẽ đường đi thực tế của một request, xác định nhánh tuần tự, song song và đường găng (critical path).
- Tính ngân sách cho từng hop, bao gồm cả queueing, connection, retry và thời gian dự phòng.
- Truyền thời hạn qua ranh giới service và buộc downstream dừng khi kết quả không còn hữu ích.
- Thiết kế timeout hợp lý cho HTTP/gRPC, database, gateway và tác vụ bất đồng bộ.
- Đọc trace, metric và kết quả thử nghiệm để phát hiện timeout chồng chéo hoặc cạn ngân sách.

## 2. Bắt đầu bằng yêu cầu đầu cuối

Giả sử API `POST /orders` có đường đi:

~~~text
Ứng dụng khách
    |
    v
API Gateway
    |
    v
Order Service -- xác thực/kiểm tra đơn
    |
    +------> Inventory Service -----+
    |                              |
    +------> Pricing Service -------+  (hai lời gọi song song)
    |
    v
Payment Service -> nhà cung cấp thanh toán
    |
    v
Order Database
    |
    v
Trả response
~~~

Người dùng quan tâm thời gian **từ khi gửi yêu cầu đến khi nhận phản hồi**. Việc Inventory trả về sau 200 ms hay Payment trả về sau 350 ms chỉ có ý nghĩa trong giới hạn tổng thể đó. Timeout của từng component phải phục vụ giới hạn đầu cuối, đồng thời bảo vệ tài nguyên riêng của component.

Cần đo và ghi rõ:

1. **Điểm bắt đầu:** ví dụ lúc gateway nhận request; nếu tính SLO từ phía client thì cộng cả thời gian mạng giữa client và gateway.
2. **Điểm kết thúc:** response hoàn tất hoặc yêu cầu hết hạn/bị hủy.
3. **Mức cam kết:** ví dụ 99% request hợp lệ hoàn tất trong 1.000 ms, theo cửa sổ đo đã định.
4. **Giới hạn thực thi:** ví dụ client chờ tối đa 1.000 ms, gateway cho tối đa 900 ms, Order Service thực thi tối đa 800 ms.

**SLO độ trễ không phải timeout.** SLO mô tả phân phối kết quả mà hệ thống hướng tới; timeout là điểm dừng để tránh chờ quá lâu. Đặt timeout 900 ms không tự động khiến p99 latency đạt 900 ms, và một phản hồi nhanh nhưng lỗi vẫn không đáp ứng mục tiêu thành công.

## 3. Nắm chắc các khái niệm

| Khái niệm | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Timeout** | Thời lượng tối đa một thao tác được chờ, thường tính từ khi thao tác bắt đầu. | `connectTimeout = 100 ms`, `requestTimeout = 220 ms`. |
| **Deadline** | Thời điểm cuối cùng mà kết quả còn được chấp nhận. | Yêu cầu phải hoàn tất trước deadline nhận từ upstream. |
| **Remaining budget** | Khoảng thời gian còn lại tới deadline ngay tại thời điểm ra quyết định. | Mỗi lời gọi downstream phải tính lại, không dùng số liệu lúc đầu request. |
| **Reserve / safety margin** | Thời gian giữ lại cho serialize, response, cleanup, jitter và sai lệch. | Không cấp 100% thời gian còn lại cho một lời gọi duy nhất. |
| **Cancellation** | Tín hiệu ngừng công việc khi client hủy hoặc deadline hết. | Hủy lời gọi đang chờ, giải phóng connection/worker và hạn chế ghi kết quả muộn. |
| **Retry budget** | Phần thời gian và số lần thử còn được phép dùng để thử lại. | Một retry chỉ được thực hiện nếu còn đủ thời gian cho backoff, lần thử mới và response. |

Có hai lớp giới hạn khác nhau:

- **Deadline của request** bảo đảm công việc không kéo dài vô hạn theo đường đi nghiệp vụ.
- **Timeout cục bộ** bảo vệ từng phụ thuộc khỏi chờ bất thường: lấy connection trong pool, DNS/TCP/TLS, đọc dữ liệu, lock database, gọi dịch vụ ngoài, v.v.

Một lời gọi HTTP có timeout tổng 200 ms vẫn có thể cần connect timeout ngắn hơn và giới hạn chờ pool riêng. Tên và phạm vi từng loại timeout tùy HTTP client, driver và proxy; phải xác nhận chúng đo từ thời điểm nào và bao gồm giai đoạn nào.

## 4. Vẽ đường đi và tìm critical path

Trước khi phân bổ thời gian, tách request thành các bước:

- **Tuần tự:** bước sau chỉ bắt đầu khi bước trước hoàn tất; thời gian của chúng cộng lại.
- **Song song:** các nhánh chạy đồng thời và phải đợi tất cả; thời gian xấp xỉ nhánh chậm nhất, cộng chi phí phối hợp.
- **Có điều kiện:** một số nhánh chỉ xuất hiện ở loại request hoặc trạng thái nhất định; cần ngân sách theo kịch bản.
- **Không nằm trên đường trả lời:** event, log hoặc job có thể chạy nền; không nên vô tình làm response phụ thuộc chúng.

Với hai lời gọi song song `Inventory` và `Pricing`:

~~~text
T_path ≈ T_gateway + T_validate
       + max(T_inventory, T_pricing) + T_join
       + T_payment + T_database + T_response
~~~

Nếu Inventory có budget 210 ms, Pricing có 160 ms, hai lời gọi thực sự khởi chạy đồng thời thì không cộng thành 370 ms trên critical path. Tuy nhiên, chúng vẫn cùng tiêu thụ thread, socket, connection pool, CPU và tải downstream. Nếu một nhánh phải đợi pool hoặc chạy sau nhánh kia, giả định song song không còn đúng.

**Chú ý xác suất:** cộng p99 của từng hop không suy ra p99 đầu cuối. Độ trễ giữa các hop có thể tương quan, và fan-out làm tăng xác suất gặp một nhánh chậm. Dùng trace thực tế, histogram và kiểm thử tải để đánh giá phân phối end-to-end; bảng ngân sách là công cụ thiết kế giới hạn, không phải phép chứng minh SLO.

## 5. Ví dụ phân bổ một ngân sách 900 ms

Giả sử gateway dành tối đa **900 ms** cho phần xử lý phía sau, với các công đoạn dưới đây. Các giá trị là giả định thiết kế cần hiệu chỉnh bằng đo đạc:

| Công đoạn | Budget trần | Quan hệ |
|---|---:|---|
| Gateway: xác thực, định tuyến, chuẩn bị request | 50 ms | Tuần tự |
| Order Service: kiểm tra nghiệp vụ | 60 ms | Tuần tự |
| Inventory Service | 210 ms | Song song với Pricing |
| Pricing Service | 160 ms | Song song với Inventory |
| Payment Service, gồm chờ network/provider | 260 ms | Sau fan-out |
| Lưu Order Database, gồm chờ pool/query/commit | 130 ms | Sau Payment |
| Chuẩn bị và gửi response | 40 ms | Tuần tự |
| Reserve cho dao động, chuyển tiếp và hủy | 100 ms | Dành riêng |

Đường găng trong trường hợp hai nhánh chạy song song:

~~~text
50 + 60 + max(210, 160) + 260 + 130 + 40 + 100
= 850 ms

Budget gateway: 900 ms
Khoảng chưa cấp: 50 ms
~~~

Điều này cho thấy **có khả năng** thiết kế vừa trong 900 ms về mặt giới hạn lý thuyết; không có nghĩa mọi request sẽ chạy đúng các thời lượng này. Khi thời gian thực tế ở bước đầu lớn hơn dự kiến, downstream nhận ít thời gian hơn. Không được tiếp tục cấp cố định 210 ms hoặc 260 ms nếu thời hạn tổng thể sắp hết.

Nếu một công đoạn chiếm nhiều thời gian hơn ngân sách đã đặt, lựa chọn thường là tối ưu hóa, điều chỉnh giới hạn có chủ đích hoặc cung cấp kết quả degrade/fallback được nghiệp vụ chấp nhận. Không tự ý tăng tất cả timeout vì việc đó dễ làm nghẽn tài nguyên và chỉ chuyển timeout sang lớp bên ngoài.

### Cấu trúc timeout lồng nhau

Một cấu hình thường có quan hệ:

~~~text
Client tổng:          1.000 ms
  Gateway upstream:     900 ms
    Order request:      800 ms
      Downstream call: min(hop cap, remaining - reserve)
~~~

Đây là những **trần riêng theo vị trí quan sát**, không phải phép cộng các tầng. Cần tính cả overhead từ client đến gateway và chừa chỗ cho gateway tạo response lỗi trước khi client tự timeout. Nếu load balancer hoặc service mesh có giới hạn nhỏ hơn, nó sẽ trở thành giới hạn thực tế và cần được đưa vào sơ đồ.

## 6. Dùng một deadline và cấp phát động tại mỗi hop

Hãy tạo deadline ở điểm ingress mà bạn kiểm soát. Trước mỗi thao tác, tính lại thời gian còn lại. Quy tắc cơ bản:

~~~text
remaining = request_deadline - now

usable = remaining - reserve_for_return_and_cleanup

hop_timeout = min(hop_policy_cap, usable)

if usable <= 0 or hop_timeout < minimum_useful_time:
    fail fast / trả fallback hợp lệ / hủy request
else:
    thực hiện lời gọi với hop_timeout
~~~

Trong đó:

- `hop_policy_cap` là giới hạn được cấu hình theo đặc điểm phụ thuộc; ví dụ Inventory tối đa 220 ms, Payment tối đa 300 ms.
- `reserve_for_return_and_cleanup` là phần giữ lại để xử lý kết quả hoặc lỗi, chuẩn bị response và giải phóng tài nguyên.
- `minimum_useful_time` tránh khởi động những thao tác chắc chắn không thể hoàn tất trong vài mili giây còn sót lại.
- `remaining` **không bao giờ được reset** về budget ban đầu ở mỗi service.

Ví dụ, Payment Service có giới hạn cục bộ 300 ms, nhưng request chỉ còn 170 ms và phải giữ 40 ms cho ghi kết quả/response. Timeout thực sự của lời gọi Payment tối đa **130 ms**, dù cấu hình Payment cho phép 300 ms.

Nếu downstream có chính sách timeout thấp hơn, downstream được phép dừng sớm. Ngược lại, downstream không nên tự kéo dài deadline đã nhận từ upstream.

### Deadline tương đối và tuyệt đối qua mạng

Trong **cùng một tiến trình**, hãy đo elapsed time bằng đồng hồ đơn điệu như `System.nanoTime()` ở Java; không dùng `System.currentTimeMillis()` để tính thời gian đã trôi vì đồng hồ hệ thống có thể được điều chỉnh.

Qua **hai máy khác nhau**, không truyền trực tiếp giá trị `nanoTime` vì chúng không chia sẻ mốc thời gian. Có thể dùng:

- **gRPC:** deadline/call timeout do thư viện quản lý; gRPC hỗ trợ truyền deadline theo lời gọi và biểu diễn timeout trên wire. Kiểm tra cấu hình propagation và cancellation của framework đang dùng.
- **HTTP nội bộ:** định nghĩa hợp đồng header rõ ràng, chẳng hạn `X-Request-Deadline-Epoch-Ms` và giới hạn độ tin cậy/sai lệch clock, hoặc truyền remaining budget có tính đến thời gian truyền. Header tự đặt **không phải chuẩn HTTP chung**.
- **Ở ingress:** đặt một mức trần cục bộ ngay cả khi client gửi deadline quá xa hoặc giá trị không hợp lệ; chỉ tin tưởng header nhận từ gateway hoặc service đã xác thực.

Deadline tuyệt đối dễ tránh việc reset qua nhiều hop nhưng nhạy với clock skew giữa máy. Remaining duration không cần đồng bộ mốc giờ nhưng nếu các hop cứ cấp lại trọn TTL nhận được thì có thể tích lũy độ trễ vận chuyển. Phải có hợp đồng propagation thống nhất, dùng tracing để kiểm chứng, và dự phòng sai lệch đồng hồ khi áp dụng deadline tuyệt đối.

## 7. Ví dụ Java: đối tượng TimeBudget dùng trong một service

Đoạn mã sau minh họa **ngân sách cục bộ** với Java 21. Mỗi instance được tạo khi nhận request; không serialize `deadlineNanos` để truyền sang máy khác.

~~~java
import java.time.Duration;

public final class TimeBudget {
    private final long deadlineNanos;

    private TimeBudget(Duration total) {
        if (total.isZero() || total.isNegative()) {
            throw new IllegalArgumentException("total must be positive");
        }
        // Các budget thực tế được giới hạn trong vài giây.
        this.deadlineNanos = System.nanoTime() + total.toNanos();
    }

    public static TimeBudget start(Duration total) {
        return new TimeBudget(total);
    }

    public Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanos));
    }

    public Duration forCall(Duration hopCap, Duration reserve) {
        if (hopCap.isZero() || hopCap.isNegative() || reserve.isNegative()) {
            throw new IllegalArgumentException("invalid budget parameters");
        }

        long usableNanos = remaining().toNanos() - reserve.toNanos();
        if (usableNanos <= 0) {
            throw new IllegalStateException("request deadline exceeded");
        }
        return Duration.ofNanos(Math.min(usableNanos, hopCap.toNanos()));
    }
}
~~~

Cách sử dụng khi gọi downstream bằng Java HTTP Client:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

TimeBudget budget = TimeBudget.start(Duration.ofMillis(800));

HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(100))
    .build();

Duration inventoryTimeout = budget.forCall(
    Duration.ofMillis(220),  // trần theo chính sách Inventory
    Duration.ofMillis(80)    // giữ cho phần còn lại
);

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://inventory.internal/items/42"))
    .timeout(inventoryTimeout)
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString()
);

// Trước lời gọi tiếp theo, phải gọi budget.forCall(...) một lần nữa.
~~~

Đây là ví dụ một luồng xử lý, không phải framework hoàn chỉnh: thực tế cần định nghĩa kiểu lỗi deadline, ánh xạ response, truyền context, chống retry không an toàn và hủy tác vụ khi client đã ngắt. `HttpRequest.timeout` giới hạn thời gian của request HTTP ở phía client; connection timeout và các ràng buộc pool phải được xem xét riêng theo thư viện cụ thể.

**Không dùng một `Duration` được tính sẵn cho mọi lời gọi.** Nếu Inventory đã mất 190 ms, phần thời gian đó phải bị trừ khỏi ngân sách khi bắt đầu gọi Payment hay database.

## 8. Truyền deadline qua microservices

Ở mỗi service, thực hiện chu trình:

1. **Nhận:** đọc deadline từ context đáng tin cậy; xác thực giá trị, giới hạn bởi trần của service.
2. **Khởi tạo local budget:** chuyển deadline nhận được thành thời gian còn lại theo đồng hồ đơn điệu của tiến trình.
3. **Kiểm tra trước công việc:** nếu hết hạn, từ chối sớm và tránh gọi dependency.
4. **Gọi tiếp:** gửi giới hạn thích hợp cho downstream, thiết lập client timeout hữu hiệu theo remaining.
5. **Chờ song song:** dùng một deadline chung cho nhóm fan-out; nhánh chậm không được khiến nhánh khác hết thời gian vô ích.
6. **Kết thúc:** hoàn thành response trước deadline; khi lỗi, timeout hoặc client hủy, phát tín hiệu cancellation xuống các tác vụ còn chạy.

**Ví dụ fan-out:** Inventory và Pricing được gọi cùng lúc. Nếu Inventory lỗi sau 90 ms khiến đơn hàng không thể xử lý, nên hủy Pricing nếu kết quả của nó không còn cần thiết. Nếu kết quả Pricing có cache/fallback được nghiệp vụ cho phép, có thể trả giá dự phòng; phải ghi nhận rõ đó là degraded response chứ không âm thầm giả định dữ liệu luôn mới.

Với Spring WebFlux/Reactor, toán tử `timeout(Duration)` có thể đặt thời hạn cho publisher, và cancellation được lan truyền theo subscription. Tuy nhiên, cần kiểm tra HTTP client/driver thực sự ngừng I/O khi bị cancel. Với `CompletableFuture`, `orTimeout` hoặc `cancel` không mặc nhiên bảo đảm socket hay truy vấn ở phía server ngừng chạy. Phải kiểm chứng hành vi cancellation ở từng tầng.

## 9. Phối hợp timeout với retry, backoff và circuit breaker

Retry tiêu tốn thêm ngân sách và làm tăng tải đúng lúc downstream có thể đang chậm. Chỉ retry khi **còn thời gian**, lỗi **có khả năng tạm thời**, và thao tác **an toàn để lặp lại**.

Điều kiện tối thiểu:

~~~text
remaining > reserve
          + estimated_backoff
          + minimum_useful_next_attempt
~~~

Nếu còn 420 ms, giữ 80 ms cho response, thì chỉ có 340 ms để thử lại. Hai lần thử 150 ms với backoff 20 ms chiếm tối đa 320 ms; hai lần 180 ms cộng backoff 25 ms thành 385 ms, vượt phần usable. Khi thực hiện thật, tính lại remaining ngay trước từng attempt vì các chi phí khác cũng trôi qua.

Gợi ý thiết kế:

- **Giới hạn số lần retry** và tổng thời gian; tránh mỗi tầng Gateway → Order → Payment đều retry độc lập gây bùng nổ số request.
- **Backoff kèm jitter** nhằm giảm các đợt retry đồng thời; nhưng backoff cũng phải nằm trong deadline.
- **Không retry mù các lệnh có side effect.** Với thanh toán, timeout có thể xảy ra sau khi provider đã ghi nhận giao dịch. Dùng idempotency key, truy vấn trạng thái hoặc reconciliation theo hợp đồng provider trước khi quyết định thử lại.
- **Circuit breaker** cắt nhanh khi dependency liên tục thất bại; **bulkhead** hạn chế số request đang chờ; **rate limit** giảm tải đầu vào. Chúng bổ trợ cho deadline chứ không thay thế deadline.
- **Hedging** (gửi thêm yêu cầu song song) có thể giảm tail latency ở một số read-only workload, nhưng tăng tải đáng kể; cần giới hạn chặt và chỉ dùng với operation idempotent, có khả năng hủy nhánh thua.

Timeout được chọn quá thấp gây false timeout và retry không cần thiết; timeout quá cao tạo queue backlog, pool exhaustion và dây chuyền lỗi. Chọn giá trị từ latency histogram, chi phí lỗi, công suất và mục tiêu của API, rồi điều chỉnh dựa trên đo đạc.

## 10. Đồng bộ với Gateway, service mesh và HTTP client

Một request có thể chịu nhiều lớp timeout độc lập:

~~~text
Mobile/Web client
    -> CDN / Edge / Load Balancer
    -> API Gateway / Service Mesh
    -> Service HTTP client
    -> Downstream server
    -> Database client
~~~

Lập bảng cấu hình theo **tên timeout và phạm vi đo**, không chỉ theo giá trị mili giây. Các biến thường cần xem xét:

| Vị trí | Loại giới hạn | Điều cần kiểm tra |
|---|---|---|
| Client | Tổng thời gian chờ response | Có timeout trước khi gateway kịp báo lỗi không? Có hỗ trợ hủy request không? |
| Gateway/proxy | Upstream response timeout, idle timeout, route timeout | Giới hạn là toàn request hay thời gian không có byte nào được truyền? Có retry mặc định không? |
| HTTP client | Chờ connection/pool, connect, TLS, request/response/read timeout | Giới hạn nào bao gồm chờ pool? Có bao gồm thời gian đọc body không? |
| Service execution | Deadline nghiệp vụ, async task timeout | Deadline có được truyền qua thread/context và kiểm tra trước side effect không? |
| Database | Chờ pool, query/statement timeout, lock timeout, transaction timeout | Transaction/lock có dừng thật khi client timeout không? |
| External provider | Hợp đồng timeout, idempotency và trạng thái giao dịch | Khi timeout, kết quả có thể đã thành công ở phía provider không? |

Ví dụ với proxy, một **idle timeout** có thể được reset mỗi lần có dữ liệu truyền qua, nên không bảo đảm toàn request dừng sau một khoảng tuyệt đối. Khi cần deadline cứng, phải có giới hạn tổng thích hợp thay vì chỉ phụ thuộc idle/read timeout.

Tránh nhầm ý nghĩa mã lỗi: HTTP 504 thường cho biết gateway/proxy timeout khi chờ upstream; 408 nói về timeout nhận request ở server; client chủ động hủy có thể không có response HTTP hoàn chỉnh. Nội bộ có thể map thành mã nghiệp vụ riêng. Với gRPC, phân biệt `DEADLINE_EXCEEDED` và `CANCELLED` khi ghi nhận nguyên nhân; phía server có thể đã làm side effect trước khi deadline được quan sát.

## 11. Budget cho database và hàng đợi

Thời gian database không chỉ là lúc thực thi SQL:

~~~text
T_db = chờ connection pool + chờ lock + query execution
     + truyền dữ liệu + commit/rollback/cleanup
~~~

Nếu budget gọi DB là 130 ms mà pool có thể chờ 500 ms, timeout thực tế bị phá vỡ ngay cả trước khi SQL bắt đầu. Cần ràng buộc hợp lý cho chờ pool, thời gian truy vấn, lock và transaction; mức giới hạn cấp dưới không được lớn hơn thời gian thực sự còn lại mà request có thể chấp nhận.

Khi ứng dụng timeout hoặc hủy request, không mặc định rằng database đã rollback hoặc query đã ngừng. Kiểm tra transaction semantics, khả năng cancel statement và trạng thái commit trước khi thực hiện retry.

**Synchronous queue:** thời gian nằm trong queue phải được trừ vào deadline. Worker lấy một job đã quá hạn nên loại bỏ hoặc xử lý theo hợp đồng lỗi, không tiếp tục xử lý chỉ vì job vừa được dequeue.

**Durable asynchronous workflow:** job nền được người dùng chấp nhận có thể cần SLA và deadline riêng (phút/giờ), không nên kế thừa nguyên timeout HTTP ngắn của request đã kết thúc. Trả mã tiếp nhận kèm job ID, rồi áp dụng ngân sách/TTL và chính sách retry riêng cho workflow đó. Việc tách request-response khỏi xử lý nền phải là quyết định nghiệp vụ minh bạch.

## 12. Hết ngân sách thì hệ thống phải làm gì?

Không có một hành động duy nhất phù hợp cho mọi API. Xác định trước theo loại nghiệp vụ:

- **Fail fast:** không khởi chạy công việc mới khi remaining quá nhỏ; trả lỗi chuẩn và ghi lý do hết deadline.
- **Fallback/degrade:** dùng cache, dữ liệu cũ hoặc bỏ phần gợi ý không thiết yếu nếu hợp đồng API cho phép; đánh dấu degraded, kiểm soát độ mới và không che giấu sai số quan trọng.
- **Cancel propagation:** gửi tín hiệu hủy xuống HTTP call, coroutine/reactive stream, task và DB query có hỗ trợ; giải phóng pool/semaphore.
- **Unknown outcome:** với thao tác ghi hoặc thanh toán, timeout không chứng minh thất bại. Dùng idempotency key, trạng thái giao dịch và reconciliation.
- **Đừng tiếp tục làm việc vô ích:** việc gửi response đã bất khả thi hoặc client disconnect phải được quan sát và xử lý, trừ phần cleanup/compensation bắt buộc.

Một server cố gắng trả response sau khi client đã timeout có thể vừa lãng phí tài nguyên vừa gây kết quả khó hiểu khi client retry. Thiết kế cần quan sát được những request có kết quả muộn và tác động side effect của chúng.

## 13. Quan sát bằng metric, trace và log

Một sơ đồ budget chỉ có giá trị khi đối chiếu với hệ thống đang chạy. Với mỗi request, thu thập:

- **Độ trễ đầu cuối:** histogram theo API, kết quả thành công/lỗi và phân vị p50/p95/p99; tính từ cùng một điểm quan sát.
- **Remaining budget:** ở ingress, trước/ sau các hop chính, thời gian còn lại khi quyết định fallback hoặc retry.
- **Timeout theo tầng:** gateway, connect, pool wait, dependency, DB statement, deadline exceeded, client cancellation.
- **Retry:** attempt count, backoff, lý do retry, số request bị từ chối vì thiếu ngân sách.
- **Tài nguyên:** active requests, thread/connection pool saturation, queue wait, error rate, CPU, số task tiếp tục chạy sau client cancel.
- **Tính đúng nghiệp vụ:** unknown payment outcome, duplicate request, số lần reconciliation, degraded response.

Trong distributed tracing, một trace có thể biểu diễn:

~~~text
POST /orders      [0 ....................................... 900 ms]
  auth            [0 .. 42]
  validate        [43 .. 95]
  inventory       [96 ............... 286]
  pricing         [96 ........ 205]
  payment         [287 ..................... 535]
  database        [536 ............ 650]
  response        [651 ... 681]
  unused budget   [682 ................................. 900]
~~~

Timeline cần lấy từ timestamp thực, không tái tạo bằng cách cộng riêng latency các span. Đặt thuộc tính tùy biến như `request.deadline_remaining_ms` và `dependency.timeout_ms` nhất quán trong hệ thống; đây là tên minh họa, không mặc định là semantic convention chuẩn của OpenTelemetry. Đừng đưa request ID hoặc user ID vào **metric labels** có cardinality cao; dùng trace/log để liên kết từng request cụ thể.

Khi trace cho thấy Gateway timeout ở 900 ms nhưng Order vẫn chạy đến 1.800 ms, vấn đề không nằm ở thiếu timeout trên Gateway; cần kiểm tra propagation, cancellation và việc áp deadline ở downstream.

## 14. Kiểm thử thiết kế trước khi đưa vào production

Các kiểm thử có ý nghĩa cần bao phủ **thời gian còn lại** và cách hệ thống hành xử khi giới hạn bị chạm:

| Tình huống | Kỳ vọng |
|---|---|
| Request đơn giản, downstream nhanh | Hoàn tất bình thường, không chờ đủ timeout mới trả kết quả. |
| Inventory chậm vượt cap, Pricing nhanh | Inventory bị giới hạn; Pricing không làm deadline tổng bị reset. |
| Đầu request mất nhiều thời gian | Payment/DB nhận timeout nhỏ hơn tương ứng, hoặc bị bỏ qua khi không đủ usable budget. |
| Client hủy giữa chừng | Tác vụ hỗ trợ cancellation dừng; tài nguyên được giải phóng. |
| Retry với remaining thấp | Không bắt đầu attempt mới nếu không còn đủ backoff, thời gian thử và reserve. |
| Pool DB bị nghẽn hoặc lock lâu | Thời gian chờ được tính trong budget; không kẹt vô hạn ngoài deadline. |
| Gateway timeout trước service | Service phát hiện deadline/cancellation và không tiếp tục công việc vô ích. |
| Payment timeout khi outcome không rõ | Không ghi nhận giao dịch thất bại chắc chắn hay retry tạo thu tiền trùng. |
| Fan-out lớn hoặc dependency đồng loạt chậm | Hạn chế tải, không tạo retry storm, tail latency và lỗi được quan sát rõ. |

Dùng fake clock hoặc clock abstraction cho thuật toán ngân sách có tính quyết định; dùng integration/load test với latency injection để kiểm tra I/O, pool và cancellation ngoài đời thực. So sánh kết quả ở tải bình thường và tải cao; p99 sẽ thay đổi đáng kể khi queueing tăng.

## 15. Những lỗi thiết kế thường gặp

1. **Mỗi hop cùng timeout 1 giây:** một request qua nhiều hop tuần tự có thể mất nhiều giây. Sửa bằng deadline chung và remaining budget.
2. **Cộng mọi nhánh song song:** dẫn tới phân bổ không cần thiết. Sửa bằng mô hình critical path, đồng thời kiểm tra contention thực tế.
3. **Chỉ đặt timeout ở gateway:** service vẫn làm việc sau khi client đã rời đi. Sửa bằng propagation và cancellation.
4. **Không tính thời gian đợi pool/queue:** tổng request vượt dự kiến dù query hoặc HTTP call ngắn. Sửa bằng tính thời gian từ lúc bắt đầu đợi tài nguyên.
5. **Retry sau timeout mà không xét deadline:** gây tăng tải và có thể lặp side effect. Sửa bằng retry budget, idempotency và tình trạng outcome.
6. **Tăng timeout để che p99 xấu:** request treo lâu hơn, tích tụ công việc. Sửa bằng xem xét nguyên nhân chậm, saturation, giới hạn đồng thời và khả năng degrade.
7. **Dùng đồng hồ tường để đo elapsed trong process:** sai khi clock điều chỉnh. Sửa bằng monotonic clock, chỉ dùng deadline truyền qua máy theo hợp đồng có kiểm soát clock skew.
8. **Cho rằng cancel Future là hủy mọi công việc:** I/O hoặc database có thể còn chạy. Sửa bằng kiểm chứng hành vi driver/client và quan sát wasted work.
9. **Coi timeout của lệnh ghi là thất bại chắc chắn:** dễ tạo kết quả trùng. Sửa bằng idempotency, status lookup và reconciliation.
10. **Dùng một deadline HTTP cho job nền kéo dài:** job bị hết hạn sai ngữ cảnh. Sửa bằng SLA và deadline riêng cho xử lý bất đồng bộ.

## 16. Quy trình áp dụng cho một API thực tế

**Bước 1 — Chọn mục tiêu:** xác định SLO end-to-end theo nhóm request và client timeout hiện có.

**Bước 2 — Lập bản đồ phụ thuộc:** vẽ đường request với các nhánh tuần tự/song song, proxy, pool, DB và external API. Đánh dấu bước bắt buộc so với bước có fallback.

**Bước 3 — Đo baseline:** lấy latency histogram, error rate, queue wait, saturation và trace ở tải điển hình lẫn tải cao. Không chọn timeout chỉ từ giá trị trung bình.

**Bước 4 — Đặt deadline đầu cuối:** thống nhất nơi khởi tạo, cách propagate, độ tin cậy header, giới hạn clock skew và cách response khi hết hạn.

**Bước 5 — Phân bổ theo critical path:** dành reserve, xác định hop cap, connect/pool/query/lock timeout, số retry tối đa và mức minimum useful budget.

**Bước 6 — Thực thi tại mỗi hop:** kiểm tra remaining trước khi gọi, giới hạn thao tác theo min(cap, remaining − reserve), hủy downstream khi request kết thúc.

**Bước 7 — Kiểm thử failure mode:** injected latency, lost response, slow DB lock, connection exhaustion, retry và client cancellation; đo cả request bị bỏ và side effect chưa chắc chắn.

**Bước 8 — Vận hành và cải tiến:** phân tích deadline-exceeded theo nguyên nhân, điều chỉnh budget khi có dữ liệu mới, theo dõi lỗi mới xuất hiện sau mỗi thay đổi.

## 17. Bài tập tình huống

Một request có deadline còn **620 ms** tại Order Service. Cần giữ **70 ms** cho việc ghi dữ liệu và gửi response. Order gọi đồng thời Inventory (cap 260 ms) và Pricing (cap 180 ms), sau đó gọi Payment (cap 300 ms). Giả sử overhead phối hợp là 20 ms.

**Câu hỏi:**

1. Nếu hai nhánh chạy song song, thời gian tối đa theo cap của nhóm fan-out là bao nhiêu?
2. Nếu Inventory hoàn tất sau 220 ms và Pricing sau 150 ms, sau overhead 20 ms còn bao nhiêu thời gian usable trước Payment?
3. Có nên mặc định cấp đủ 300 ms cho Payment? Nếu không, cần tính theo công thức nào?
4. Nếu Payment là thao tác tạo giao dịch và bị timeout không rõ kết quả, có nên retry ngay với idempotency key mới không?

**Gợi ý tự đối chiếu:** nhóm song song lấy `max(260, 180) = 260 ms` theo cap; với số đo thực tế, đã dùng `max(220, 150) + 20 = 240 ms`, còn 380 ms trước reserve và **310 ms usable** sau khi giữ 70 ms. Payment vẫn phải giới hạn bởi thời gian còn lại tại thời điểm thật sự bắt đầu: `min(300 ms, remaining − 70 ms)`. Không dùng idempotency key mới cho retry mù của cùng một giao dịch; cần cùng khóa theo hợp đồng và/hoặc xác minh trạng thái.

## 18. Kết luận

Thiết kế timeout trong microservices là bài toán **kiểm soát thời gian theo toàn bộ đường đi request**. Bắt đầu từ deadline đầu cuối, phân tích critical path, chừa reserve, và tính lại remaining budget trước mỗi thao tác. Đặt giới hạn rõ cho network, pool, DB và retry; truyền tín hiệu hủy để dừng công việc không còn giá trị; đo trace/metric để xác nhận hành vi thực tế. Một hệ thống chịu lỗi tốt biết **khi nào nên dừng**, **khi nào được fallback**, và **khi nào kết quả của thao tác có side effect vẫn chưa xác định**.
