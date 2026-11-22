# Điều tra API chậm do cold start và downstream latency

Một API chạy trên nền tảng serverless có thể phản hồi chậm vì hai nhóm nguyên nhân lớn: môi trường thực thi Java cần thời gian khởi tạo trước khi xử lý request (*cold start*), hoặc function phải chờ hệ thống phía sau như cơ sở dữ liệu, dịch vụ HTTP, cache hay hàng đợi (*downstream latency*). Hai nguyên nhân có thể xuất hiện cùng lúc, nhưng cách xử lý khác nhau. Tăng bộ nhớ hay giữ function luôn nóng sẽ không giải quyết được một truy vấn cơ sở dữ liệu chậm; tối ưu truy vấn cũng không loại bỏ thời gian khởi tạo JVM.

Bài học này trình bày cách đo độ trễ từ đầu đến cuối, phân loại request chậm, đọc log và trace, thêm phép đo trong Java, kiểm tra các phụ thuộc phía sau, rồi chọn biện pháp giảm độ trễ phù hợp. Mục tiêu vận hành là giữ API trong giới hạn SLO với chi phí hợp lý, đồng thời bảo đảm retry, mở rộng và xử lý lỗi vẫn an toàn.

Sau bài học, người học có thể:

- Phân rã thời gian phản hồi của một request serverless thành các chặng có thể đo được.
- Phân biệt cold start với độ trễ của downstream bằng dữ liệu theo từng request và theo percentile.
- Dùng log có cấu trúc, metric và distributed trace để xác định chặng đang chiếm thời gian.
- Đo thời gian xử lý trong Java bằng đồng hồ đơn điệu và đặt timeout cho lời gọi phụ thuộc.
- Chọn cách tối ưu cold start, kết nối HTTP, connection pool, truy vấn dữ liệu và retry.
- Đánh giá ảnh hưởng của concurrency, idempotency, chi phí và SLO trước khi thay đổi kiến trúc.

## 1. Phân rã độ trễ trước khi sửa lỗi

Độ trễ mà client nhìn thấy là tổng thời gian đi qua nhiều lớp. Một mô hình thực dụng cho API serverless là:

\[
T_{client} = T_{edge} + T_{queue} + T_{init} + T_{handler} + T_{downstream} + T_{response}
\]

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ dấu hiệu cần đo |
|---|---|---|
| `T_edge` | Thời gian tại DNS, CDN, load balancer hoặc API gateway | Gateway latency, integration latency, TLS handshake |
| `T_queue` | Thời gian request chờ được cấp tài nguyên hoặc chờ worker | Queue age, event age, thời gian chờ concurrency |
| `T_init` | Thời gian tạo môi trường và khởi tạo runtime/function | Init duration, cold-start marker, class loading |
| `T_handler` | Thời gian chạy logic trong function | Validation, mapping, serialization, CPU và GC |
| `T_downstream` | Thời gian chờ dịch vụ mà function gọi | Pool wait, DNS, connect, TLS, query, remote processing |
| `T_response` | Thời gian đóng gói và truyền response về client | Kích thước payload, serialization, gateway egress |

Đây là mô hình để định hướng đo đạc, không phải lúc nào cũng là phép cộng trực tiếp của các span. Nếu function gọi ba dịch vụ song song, thời gian của nhánh chậm nhất thường quyết định thời gian chờ; nếu các lời gọi chạy tuần tự, thời gian của chúng cộng dồn. Trace sẽ cho thấy quan hệ cha-con và phần việc chạy song song.

Không gộp tất cả thành một con số `Duration`. Ví dụ, function chạy 900 ms có thể gồm 40 ms xử lý Java, 30 ms chờ lấy kết nối và 830 ms chờ database. Nếu chỉ nhìn duration, nhóm vận hành dễ tối ưu nhầm JVM trong khi truy vấn mới là nút thắt.

### 1.1. Đọc percentile thay vì chỉ nhìn trung bình

- **p50** mô tả request điển hình: một nửa request hoàn tất trong khoảng thời gian này hoặc nhanh hơn.
- **p95** cho thấy trải nghiệm của nhóm request chậm hơn phần lớn người dùng.
- **p99** làm lộ các đuôi chậm do cold start, pool cạn, retry, GC hoặc downstream quá tải.
- **Tỷ lệ vượt SLO** cho biết bao nhiêu request vượt ngưỡng đã cam kết, ví dụ hơn 800 ms.

Trung bình có thể trông tốt dù một nhóm nhỏ request rất chậm. Vì vậy hãy so sánh p50, p95, p99 và tỷ lệ lỗi theo cùng route, region, phiên bản function, kích thước request và khoảng thời gian. Không so sánh p99 của một nhóm rất ít request với p99 của một nhóm có lưu lượng lớn mà không xem số mẫu.

Ví dụ, p50 ở mức 120 ms nhưng p99 lên 2,5 giây thường gợi ý một vấn đề chỉ tác động đến một phần request: môi trường mới khởi tạo, pool hết kết nối, DNS/TLS phải thiết lập lại, hoặc một số truy vấn dữ liệu có kế hoạch thực thi kém. p50 và p95 cùng tăng thường cho thấy tải hoặc downstream đang chậm trên diện rộng.

### 1.2. Cold start là gì?

Với mô hình FaaS, nền tảng tạo một execution environment để chạy function. Lần gọi đầu tiên trong môi trường mới có thể phải thực hiện các công việc như:

1. Cấp phát môi trường thực thi và chuẩn bị runtime.
2. Khởi chạy JVM và nạp các thư viện cần thiết.
3. Nạp class, chạy static initializer, tạo dependency injection container hoặc framework context.
4. Đọc cấu hình, khởi tạo serializer, client HTTP, SDK, connection pool hoặc các thành phần dùng chung.
5. Sau đó mới chạy handler cho request đầu tiên.

Các lần gọi tiếp theo có thể dùng lại cùng môi trường và bỏ qua phần lớn chi phí khởi tạo. Tuy nhiên, nền tảng có quyền tạo hoặc thu hồi môi trường theo tải và chính sách nội bộ. Không được giả định một request tiếp theo sẽ luôn chạy trên cùng instance, cũng không được dùng biến static để lưu trạng thái nghiệp vụ giữa các request.

Java có thể chịu chi phí khởi tạo đáng kể khi ứng dụng kéo theo nhiều dependency, framework quét classpath, reflection, cấu hình logging phức tạp hoặc static initializer thực hiện I/O. Việc khởi tạo client và pool cũng có thể nằm trong giai đoạn init hoặc bị dồn vào request đầu tiên, tùy thời điểm class được nạp.

### 1.3. Downstream latency là gì?

Downstream là bất kỳ hệ thống nào function cần gọi để hoàn thành request: REST/gRPC service, database, cache, object storage, message broker, identity provider hoặc API bên thứ ba. Thời gian của một lời gọi thường gồm nhiều phần:

- Chờ lấy connection từ pool hoặc semaphore.
- Tra cứu DNS và thiết lập TCP connection.
- Thực hiện TLS handshake và xác thực.
- Chờ dịch vụ phía sau xếp lịch xử lý.
- Thực thi truy vấn, transaction hoặc logic từ xa.
- Truyền và đọc response, giải mã payload.
- Chờ các lần retry nếu có lỗi tạm thời.

Một downstream chậm có thể làm function chiếm concurrency lâu hơn. Khi nhiều invocation cùng chờ database, số execution environment tăng lên có thể kéo theo nhiều connection hơn, làm database quá tải và khiến request tiếp tục chậm. Đây là vòng lặp khuếch đại thường gặp trong hệ thống serverless.

## 2. Phân biệt cold start và downstream latency

Hãy phân nhóm request trước khi kết luận. Một request chậm đơn lẻ không đủ để chứng minh cold start hay lỗi database.

| Quan sát | Khả năng cao | Cách xác minh |
|---|---|---|
| Request đầu tiên của môi trường mới chậm; các request sau nhanh | Cold start hoặc khởi tạo lazy | Đối chiếu init duration của nền tảng với marker first invocation và trace |
| Request warm vẫn chậm; span database/HTTP chiếm phần lớn tổng thời gian | Downstream latency | Xem query duration, remote span, pool wait và thời gian kết nối |
| p99 tăng khi tải tăng, kèm throttling hoặc queue age tăng | Thiếu concurrency, giới hạn downstream hoặc queue backlog | So sánh concurrency, throttle, queue age, connection count và error rate |
| Function duration thấp nhưng client/gateway latency cao | Edge, gateway, network hoặc queue | So sánh client timing, gateway timing và function timing |
| Chỉ một số request có nhiều lần gọi lại | Retry hoặc lỗi tạm thời | Ghi số attempt, nguyên nhân retry và tổng thời gian đã tiêu thụ |
| Chậm sau một thời gian idle | Kết nối hết hạn, DNS/TLS hoặc môi trường mới | Đo pool wait, connect/TLS, connection reset và init duration |
| p50 tốt nhưng p99 xấu, không có init duration | Tail latency ở downstream, GC, lock hoặc pool | Dùng trace và metric theo từng chặng; không mặc định đó là cold start |

Một dấu hiệu cold start đáng tin cậy cần liên hệ được request với môi trường mới hoặc chỉ số init do nền tảng cung cấp. Biến static đánh dấu lần gọi đầu chỉ là tín hiệu chẩn đoán ở cấp process; nó không thay thế metric chính thức của nền tảng. Ngược lại, nếu request chậm có span database kéo dài dù môi trường đã warm, tối ưu cold start sẽ không xử lý được nguyên nhân đó.

### 2.1. Xác định phạm vi ảnh hưởng

Trước khi đào sâu, ghi rõ:

- Route, method, region, stage và phiên bản/alias của function.
- Khoảng thời gian xảy ra lỗi, mức tải, số request và thay đổi vừa triển khai.
- p50/p95/p99, tỷ lệ vượt SLO, timeout, 4xx/5xx và retry.
- Request có kích thước, loại dữ liệu hoặc nhánh nghiệp vụ nào đặc biệt.
- Sự cố xảy ra trên mọi region hay chỉ một vùng, mọi downstream hay một phụ thuộc.

Nếu chỉ một route chậm, bắt đầu từ các dependency và nhánh xử lý riêng của route đó. Nếu nhiều route cùng chậm và cùng gọi một database, cache hoặc identity provider, ưu tiên kiểm tra phụ thuộc dùng chung.

## 3. Dữ liệu cần có để điều tra

Một quy trình điều tra hiệu quả kết hợp ba loại tín hiệu: metric cho xu hướng, log cho sự kiện cụ thể và trace cho quan hệ thời gian giữa các thành phần.

### 3.1. Metric ở từng lớp

| Lớp | Metric nên theo dõi | Câu hỏi cần trả lời |
|---|---|---|
| Client/API gateway | Request count, p50/p95/p99, integration latency, 4xx/5xx, timeout | Client chờ ở gateway hay function? |
| FaaS platform | Invocation, duration, init duration, error, throttle, concurrency, queue/event age | Có môi trường mới, thiếu concurrency hay backlog? |
| JVM/function | Thời gian init, CPU, heap, GC pause, memory used, serialization time | Function đang tính toán, GC hay chờ I/O? |
| HTTP client | Pool wait, DNS/connect/TLS, response time, timeout, status, retry count | Kết nối hay dịch vụ từ xa chậm? |
| Database | Connection count, pool pending, query latency, lock wait, CPU, I/O, transaction time | Pool cạn hay truy vấn/DB quá tải? |
| Cache/broker | Hit ratio, command latency, queue depth, oldest message age, redelivery | Cache miss hoặc backlog có làm tăng thời gian? |

Tên metric khác nhau giữa AWS Lambda, Azure Functions, Google Cloud Functions/Cloud Run Functions và các nền tảng khác. Hãy dùng metric tương đương mà provider cung cấp. Với AWS Lambda, log `REPORT` có thể chứa `Init Duration` khi có cold start; các metric như `Duration`, `Errors`, `Throttles` và `ConcurrentExecutions` giúp đặt duration vào bối cảnh tải. Đừng suy ra một metric không có trong provider chỉ vì tên gọi trong ví dụ này.

Theo dõi metric dưới dạng histogram hoặc distribution để tính percentile. Trung bình của các giá trị đã được gom nhóm không thể thay thế chính xác p95/p99 của request. Gắn metric với dimension có cardinality thấp như route, region, function version và downstream service. Không dùng user ID, request ID hoặc URL có query string làm dimension metric vì chúng tạo quá nhiều chuỗi thời gian và có thể làm lộ dữ liệu.

### 3.2. Log có cấu trúc

Mỗi invocation nên có một bản ghi hoặc một nhóm bản ghi có thể liên kết bằng `request_id` và `trace_id`. Trường hữu ích gồm:

- `request_id`, `trace_id`, `route`, `method`, `region`, `function_version`.
- `cold_start_candidate`, `init_duration_ms` nếu nền tảng cung cấp.
- `total_ms`, `validation_ms`, `business_ms`, `serialization_ms`.
- `downstream_service`, `downstream_ms`, `pool_wait_ms`, `attempt`, `status_code`.
- `outcome`, `error_type`, `timeout_stage` và `concurrency` nếu có sẵn.

Không ghi access token, cookie, secret, toàn bộ payload hoặc thông tin cá nhân chỉ để điều tra latency. Nếu cần định danh một loại request, dùng route template hoặc loại nghiệp vụ đã chuẩn hóa. Không ghi URL chứa query string nhạy cảm.

Log phải cho phép phân biệt thời gian tổng với thời gian từng downstream. Một log `request completed in 2400 ms` không cho biết 2,3 giây nằm ở đâu. Một log có `total_ms=2400`, `db_ms=1900`, `http_ms=120`, `handler_ms=300` đã thu hẹp đáng kể phạm vi.

### 3.3. Distributed trace

Trace mô tả đường đi của một request qua gateway, function và các dịch vụ được gọi. Mỗi lời gọi từ xa nên có span riêng, ví dụ `inventory.lookup`, `orders.query` hoặc `payment.authorize`. Dùng OpenTelemetry hoặc khả năng tracing của provider để truyền trace context qua HTTP header và message metadata.

Khi đọc trace:

1. Tìm span gốc tương ứng với request API.
2. Xem span con nào nằm trên critical path và chiếm nhiều thời gian nhất.
3. Tách thời gian chờ pool/kết nối khỏi thời gian xử lý thực tế nếu thư viện hỗ trợ.
4. Xem các span song song có chờ nhau hay không.
5. Đối chiếu attempt và exception để phát hiện retry ẩn trong SDK.

Không phải trace nào cũng ghi nhận giai đoạn khởi tạo trước handler. Hãy kết hợp trace với init duration và log của nền tảng. Sampling cũng có thể bỏ qua request chậm nếu chỉ lấy mẫu ngẫu nhiên; cân nhắc tail-based sampling để giữ lại trace có latency cao hoặc có lỗi, đồng thời kiểm soát chi phí và dữ liệu nhạy cảm.

## 4. Quy trình điều tra theo từng bước

### Bước 1: Chốt triệu chứng và ngưỡng cần đạt

Chọn một route và một khoảng thời gian cụ thể. Ghi lại p50, p95, p99, tỷ lệ vượt SLO, error rate và lưu lượng. So sánh với giai đoạn bình thường, cùng giờ trong ngày hoặc cùng mức tải. Xác nhận sự cố bắt đầu từ lúc deploy, thay đổi cấu hình, tăng lưu lượng hay thay đổi ở downstream.

Không bắt đầu bằng việc tăng memory, timeout hoặc concurrency. Những thay đổi này có thể che dấu triệu chứng, tăng chi phí hoặc làm downstream chịu tải lớn hơn mà không xác định được nguyên nhân.

### Bước 2: So sánh thời gian giữa client, gateway và function

- Nếu client thấy chậm nhưng gateway không thấy chậm, kiểm tra DNS, kết nối client, CDN hoặc mạng phía người dùng.
- Nếu gateway integration latency cao và function duration cũng cao, đi tiếp vào function.
- Nếu gateway chậm nhưng function duration thấp, kiểm tra gateway, queue, kết nối mạng, serialization hoặc thời gian chờ trước khi function bắt đầu.
- Nếu function timeout trong khi downstream vẫn xử lý, kiểm tra deadline và khả năng hủy lời gọi từ xa.

Đảm bảo các con số dùng cùng một đơn vị và cùng request. Không trừ hai percentile độc lập để suy ra thời gian của một chặng; hãy dùng trace hoặc dữ liệu request-level để tính phần chênh lệch.

### Bước 3: Chia request thành nhóm cold và warm

Đối chiếu init duration, first-invocation marker và thời điểm tạo environment nếu provider có cung cấp. So sánh phân phối latency của nhóm có init với nhóm không có init. Nếu chỉ nhóm cold vượt SLO, đo riêng phần khởi tạo và phần handler của request đầu. Nếu nhóm warm vẫn chậm, chuyển trọng tâm sang handler và downstream.

Marker tự ghi trong Java cần được hiểu đúng: biến static chỉ sống trong một runtime environment, có thể reset khi môi trường mới được tạo, và không cho biết chính xác toàn bộ thời gian cấp phát của nền tảng. Dùng nó để phân nhóm sơ bộ; dùng log/metric của provider để xác nhận.

### Bước 4: Tìm downstream chiếm critical path

Với request warm, mở trace chậm và sắp xếp span theo thời gian. Kiểm tra:

- Thời gian chờ connection pool có tăng không?
- DNS, TCP hoặc TLS có xuất hiện ở mọi request hay chỉ sau thời gian idle?
- Database đang chờ lock, scan nhiều dòng hay chạy truy vấn N+1?
- Dịch vụ HTTP có trả 429/5xx, queue nội bộ hoặc response lớn không?
- SDK có retry tự động mà log ứng dụng không thể hiện không?
- Các lời gọi có thể chạy song song hay đang tuần tự không cần thiết?

Đối chiếu trace với metric phía downstream. Nếu function ghi nhận lời gọi mất 1,8 giây và database cũng ghi nhận query mất 1,8 giây, bằng chứng khá rõ. Nếu function chờ 1,8 giây nhưng server chỉ xử lý 80 ms, phần chênh lệch có thể nằm ở pool, mạng, proxy hoặc hàng đợi.

### Bước 5: Tạo giả thuyết có thể kiểm chứng

Một giả thuyết tốt nêu được nguyên nhân, dấu hiệu dự đoán và phép thử. Ví dụ: “p99 tăng vì pool database chỉ có hai connection trong mỗi environment; khi concurrency tăng, invocation chờ pool hơn 500 ms”. Dự đoán là `pool_wait_ms` tăng cùng `pending` trong khi query execution time tương đối ổn định. Thử tăng giới hạn pool có kiểm soát hoặc dùng proxy phù hợp, rồi theo dõi connection count và p99.

Tránh thay đồng thời nhiều biến. Nếu thay memory, pool size, timeout và retry cùng một lần, kết quả tốt hoặc xấu đều khó giải thích.

### Bước 6: Thử nghiệm và xác nhận

Chạy thử trong môi trường có cấu hình mạng, database và giới hạn concurrency gần production. Kiểm tra cả cold path, warm path, tải ổn định và burst. So sánh cùng loại request và cùng kích thước payload trước/sau thay đổi. Theo dõi latency, error rate, throttling, downstream saturation và chi phí trong suốt thử nghiệm.

Một lần gọi thành công sau deploy không chứng minh cold start đã hết: request có thể tình cờ chạy trên môi trường đã warm. Cần quan sát đủ số invocation và số môi trường mới để đánh giá.

## 5. Đo thời gian trong Java

### 5.1. Dùng đồng hồ đơn điệu

Đo khoảng thời gian bằng `System.nanoTime()`. Không dùng `System.currentTimeMillis()` để tính elapsed time vì đồng hồ lịch có thể bị điều chỉnh. Chỉ đổi sang mili giây khi ghi log hoặc xuất metric.

Ví dụ sau minh họa cách ghi nhận request đầu tiên trong một runtime environment và đo riêng một lời gọi repository. Các kiểu `ApiRequest`, `ApiResponse`, `InvocationContext`, `repository` và `logger` đại diện cho thành phần của ứng dụng; thay bằng kiểu thực tế của dự án.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class ApiHandler {
    private static final AtomicBoolean FIRST_INVOCATION =
            new AtomicBoolean(true);

    private final OrderRepository repository;
    private final Logger logger;

    public ApiHandler(OrderRepository repository, Logger logger) {
        this.repository = repository;
        this.logger = logger;
    }

    public ApiResponse handle(ApiRequest request, InvocationContext context) {
        long requestStarted = System.nanoTime();
        boolean firstInvocation = FIRST_INVOCATION.compareAndSet(true, false);
        long repositoryMs = -1;
        String outcome = "success";

        try {
            long repositoryStarted = System.nanoTime();
            Order order = repository.findById(request.orderId());
            repositoryMs = elapsedMillis(repositoryStarted);

            return ApiResponse.from(order);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            long totalMs = elapsedMillis(requestStarted);
            logger.info(
                    "request_id={} first_invocation_candidate={} "
                            + "repository_ms={} total_ms={} outcome={}",
                    context.requestId(), firstInvocation,
                    repositoryMs, totalMs, outcome);
        }
    }

    private static long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000;
    }
}
```

`FIRST_INVOCATION` chỉ là marker ở cấp process. Nó đánh dấu lần handler đầu tiên mà class này quan sát được trong environment hiện tại; nó không đo thời gian cấp phát runtime và không thay thế `Init Duration` của provider. Nếu class được nạp muộn, phần khởi tạo trước lúc nạp class cũng không được tính trong marker này.

Trong ứng dụng thật, nên tạo span cho từng chặng và ghi thời gian cả khi lời gọi thất bại hoặc timeout. Đừng chỉ ghi `repository_ms` khi thành công: nếu exception xảy ra trước khi gán biến, cần có một trường trạng thái như `repository_outcome=timeout` để phân biệt “không gọi” với “gọi nhưng thất bại”.

### 5.2. Đo và giới hạn lời gọi HTTP

Ứng dụng Java nên tái sử dụng HTTP client thread-safe trong phạm vi runtime environment thay vì tạo client mới cho từng request. Ví dụ với `java.net.http.HttpClient` (Java 11 trở lên):

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class CatalogClient {
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(250))
            .version(HttpClient.Version.HTTP_2)
            .build();

    public String getItem(URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(900))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = HTTP.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new DownstreamException(
                    "Catalog returned HTTP " + response.statusCode());
        }
        return response.body();
    }
}
```

`connectTimeout` giới hạn thời gian thiết lập kết nối; `HttpRequest.timeout` giới hạn thời gian của request. Cả hai đều cần được chọn theo deadline còn lại của invocation. Ví dụ 250 ms và 900 ms ở trên chỉ là số minh họa, không phải cấu hình mặc định cho mọi hệ thống.

Tái sử dụng client giúp tận dụng kết nối keep-alive và giảm việc tạo socket/TLS lặp lại. Tuy nhiên, kết nối có thể bị server hoặc proxy đóng khi idle. Cần xử lý lỗi kết nối đã hết hạn và để client thiết lập lại một cách có kiểm soát. Không lưu response hay dữ liệu riêng của người dùng trong static field chỉ vì client được dùng chung.

Với HTTP client hoặc SDK khác, kiểm tra rõ timeout cho từng pha: connection acquisition, connect, TLS, response/read và tổng request. Một timeout chỉ áp dụng cho connect không giới hạn thời gian chờ response. Đặt timeout hữu hạn cho mọi lời gọi từ xa.

### 5.3. Đo connection pool và truy vấn database

Nếu dùng JDBC pool, cần tách ít nhất ba số liệu: thời gian chờ lấy connection, thời gian thực thi query và thời gian giữ connection trong transaction. Pool wait cao có thể xuất hiện dù query nhanh. Query duration cao có thể do thiếu index, scan nhiều dòng, lock contention hoặc database quá tải.

Không đặt pool size lớn theo cảm tính. Trong serverless, nhiều environment có thể tồn tại song song. Nếu concurrency của function là 80 và mỗi environment có pool tối đa 10 connection, hệ thống có thể tạo ra tới khoảng 800 connection ở mức lý thuyết. Con số thực tế còn tùy số environment, số thread và cách pool mở kết nối, nhưng phép nhân này cho thấy vì sao pool nhỏ theo instance vẫn có thể gây áp lực lớn lên database.

Với database có giới hạn connection, cân nhắc proxy/pooler được quản lý, giới hạn concurrency của function, giảm pool size mỗi environment, rút ngắn transaction và chỉ mở connection khi cần. Cấu hình idle timeout và validation phù hợp với chính sách đóng kết nối của database/proxy. Không giữ transaction trong lúc gọi một dịch vụ HTTP không liên quan.

## 6. Giảm cold start cho Java function

Chỉ tối ưu cold start sau khi đo được tỷ lệ cold invocation và phần thời gian init đóng góp vào SLO. Nếu cold start chỉ chiếm một phần rất nhỏ lưu lượng và p99 chủ yếu do database, chi phí đầu tư vào startup có thể không đem lại cải thiện đáng kể.

### 6.1. Giảm công việc trong giai đoạn khởi tạo

- Loại bỏ dependency không dùng, thư viện trùng và phần framework không cần thiết.
- Hạn chế quét classpath, reflection và khởi tạo container lớn nếu function chỉ dùng một vài thành phần.
- Tránh gọi API mạng, truy vấn database hoặc tải cấu hình từ xa trong static initializer nếu không cần thiết.
- Tạo serializer, client và cấu hình dùng chung một lần cho mỗi environment khi chúng an toàn để tái sử dụng.
- Đo riêng thời gian class loading, dependency injection, cấu hình và tạo client để biết phần nào thực sự tốn thời gian.
- Giữ artifact gọn, kiểm tra dependency tree và cách đóng gói JAR/container image.

Lazy initialization có thể chuyển chi phí từ init sang request đầu tiên. Cách này hữu ích khi thành phần hiếm khi được dùng, nhưng sẽ làm chậm request đầu tiên đi qua nhánh đó. Đo cả init duration lẫn latency của request đầu, không chỉ một trong hai.

### 6.2. Chọn runtime và kỹ thuật khởi động

Tùy nền tảng, có thể cân nhắc:

- **Tăng memory/CPU được cấp:** một số nền tảng gắn CPU với cấu hình memory. Tăng memory có thể rút ngắn class loading, xử lý và nén/giải mã, nhưng cũng làm tăng chi phí mỗi đơn vị thời gian. Benchmark các mức cấu hình thay vì mặc định mức cao nhất.
- **AOT hoặc GraalVM Native Image:** có thể giảm thời gian startup và memory footprint trong một số workload. Đổi lại, build phức tạp hơn, cần cấu hình reflection/resource và kiểm tra tương thích thư viện, instrumentation, TLS và runtime behavior.
- **Snapshot/restore runtime:** một số provider hỗ trợ chụp trạng thái đã khởi tạo để khôi phục nhanh. Phải kiểm tra hook sau restore, thời gian, entropy, ID duy nhất, credential và connection mạng. Không nên giả định socket hoặc credential trong snapshot vẫn hợp lệ sau khi restore.
- **Provisioned/warm capacity:** giữ sẵn một lượng môi trường đã khởi tạo để giảm cold start trong phạm vi capacity được cấu hình. Giải pháp này phát sinh chi phí khi capacity nhàn rỗi và không bảo đảm mọi burst đều nằm trong mức đã chuẩn bị.
- **Giảm framework hoặc dùng runtime nhẹ hơn:** có thể có lợi, nhưng cần cân bằng với khả năng bảo trì, thư viện quan sát và tốc độ phát triển.

Tên gọi, giới hạn và cách tính phí của snapshot, provisioned concurrency hoặc warm capacity tùy provider và runtime. Kiểm tra tài liệu hiện hành của nền tảng trước khi đưa vào production.

### 6.3. Đừng phụ thuộc vào warm-up giả

Gửi request định kỳ để “giữ nóng” function không bảo đảm request thật sẽ dùng cùng environment. Nền tảng có thể thu hồi environment hoặc tạo thêm environment khi tải tăng. Warm-up còn tạo invocation và chi phí, làm nhiễu metric, có thể gọi nhầm downstream và che khuất hành vi thực tế khi scale từ zero.

Nếu SLO yêu cầu latency khởi đầu thấp, dùng cơ chế capacity được nền tảng hỗ trợ và đo chi phí. Nếu workload có lưu lượng ổn định, dự đoán được và yêu cầu latency nghiêm ngặt, so sánh FaaS với dịch vụ container/worker luôn chạy. Quyết định dựa trên latency end-to-end, mức sử dụng, khả năng vận hành và tổng chi phí.

## 7. Giảm downstream latency

### 7.1. Giảm số lần gọi và rút ngắn critical path

- Loại bỏ N+1 query và lời gọi HTTP trùng lặp.
- Lấy đủ dữ liệu cần thiết trong một truy vấn có index phù hợp thay vì gọi tuần tự nhiều lần.
- Chỉ chạy song song khi các nhánh độc lập và downstream có đủ capacity.
- Giới hạn số lời gọi đồng thời; không tạo một thread hoặc future không giới hạn cho mỗi phần tử trong payload.
- Phân trang dữ liệu lớn và giới hạn response size.
- Cache dữ liệu đọc nhiều, ít thay đổi khi yêu cầu nhất quán cho phép.

Song song hóa có thể giảm latency của một request nhưng tăng tải đỉnh lên downstream. Trước khi dùng `CompletableFuture` hoặc fan-out, đặt giới hạn concurrency, timeout và quy tắc hủy nhánh còn lại khi request hết deadline. Một thread pool riêng cần có kích thước hữu hạn và được tái sử dụng an toàn trong environment.

Cache trong bộ nhớ của một environment chỉ là cache cục bộ, có thể biến mất khi môi trường bị thu hồi và không được chia sẻ với environment khác. Nếu cần chia sẻ giữa nhiều instance, dùng cache bên ngoài. Cả hai loại cache đều cần TTL, quy tắc invalidation và cách tránh cache stampede khi nhiều environment cùng miss.

### 7.2. Tối ưu database

Khi trace cho thấy database chiếm thời gian, kiểm tra query plan và số dòng thực sự đọc. Tập trung vào:

- Index khớp với điều kiện lọc, thứ tự sắp xếp và join thường dùng.
- Tránh `SELECT *` nếu response chỉ cần một số cột.
- Tránh N+1 query và truy vấn lặp trong vòng lặp.
- Giữ transaction ngắn; không chờ API ngoài trong khi đang giữ lock.
- Dùng pagination có giới hạn và thứ tự ổn định.
- Xem lock wait, I/O, CPU, replication lag và giới hạn connection của database.

Một truy vấn nhanh trong môi trường dev có thể chậm ở production do kích thước dữ liệu, phân bố giá trị, index, concurrency và lock. Thử nghiệm trên dữ liệu gần thực tế và dùng kế hoạch thực thi trước khi thay đổi index.

### 7.3. Tối ưu kết nối mạng và dịch vụ HTTP

Tách thời gian pool wait, DNS, connect, TLS và remote processing. Nếu request đầu sau idle chậm nhưng request kế tiếp nhanh, kiểm tra keep-alive, DNS cache, connection lifetime và TLS handshake. Nếu mọi request đều chậm, xem latency phía server, region, route mạng và kích thước response.

Trong môi trường có VPC hoặc private network, kiểm tra route table, security group/firewall, NAT/egress gateway, DNS resolver và private endpoint. Đừng mặc định mọi chậm trễ trong VPC đều do cold start. Với AWS Lambda hoặc nền tảng tương tự, cơ chế network attachment và cách provider cấp phát interface đã thay đổi theo thời gian; hãy đo đường mạng thực tế và dùng tài liệu provider hiện hành.

Ưu tiên gọi dịch vụ ở region gần nhau khi yêu cầu dữ liệu và khả năng dự phòng cho phép. Kiểm tra việc đi vòng qua public endpoint khi có private endpoint phù hợp. Không bỏ TLS hoặc nới quyền mạng để đổi lấy vài mili giây; hãy tối ưu reuse connection, endpoint và cấu hình DNS an toàn.

### 7.4. Kiểm soát pool và concurrency

Concurrency của function và capacity của downstream phải được thiết kế cùng nhau. Nếu database chỉ chịu được 300 connection và mỗi environment có thể mở 5 connection, số environment hoạt động đồng thời phải được tính đến cùng các service khác dùng chung database.

Các biện pháp thường dùng:

- Giới hạn concurrency của function theo capacity downstream.
- Giữ pool size nhỏ, đặt acquisition timeout rõ ràng và đo số connection đang dùng/chờ.
- Dùng database proxy hoặc pooler khi phù hợp với loại database.
- Giảm thời gian giữ connection và transaction.
- Dùng queue để hấp thụ burst cho công việc có thể xử lý bất đồng bộ.
- Dùng bulkhead hoặc semaphore để giới hạn tải đến từng dependency.

Circuit breaker đặt trong một execution environment chỉ có trạng thái cục bộ. Khi nền tảng tạo nhiều environment, mỗi environment có thể có trạng thái breaker khác nhau. Vì vậy circuit breaker cục bộ hữu ích để ngăn một instance tiếp tục gọi dependency đang lỗi, nhưng không thay thế rate limit hoặc kiểm soát tải ở cấp hệ thống.

## 8. Timeout, retry và idempotency

### 8.1. Thiết kế timeout theo một deadline chung

Một request thường đi qua client, gateway, function và nhiều downstream. Timeout của từng lớp cần phù hợp với deadline còn lại. Ví dụ minh họa:

| Lớp | Ngân sách ví dụ |
|---|---:|
| Client timeout | 3.0 giây |
| Gateway integration timeout | 2.5 giây |
| Function timeout mục tiêu | 2.2 giây |
| Một downstream call quan trọng | tối đa 1.2 giây |
| Phần còn lại | validation, logic, response và dự phòng |

Các số trên chỉ minh họa cách phân bổ. Giới hạn thực tế của gateway và function phụ thuộc provider. Với API đồng bộ, function cần hoàn tất trước khi gateway ngắt kết nối, và client cần chờ lâu hơn gateway một khoảng hợp lý để nhận response lỗi có kiểm soát. Nếu function timeout dài hơn gateway, gateway có thể trả lỗi cho client trong khi function vẫn chạy và tiếp tục tiêu tốn tài nguyên.

Truyền deadline hoặc thời gian còn lại xuống downstream thay vì để mỗi service tự bắt đầu một timeout đầy đủ. Nếu invocation chỉ còn 400 ms, không nên bắt đầu một request downstream có timeout 1 giây. Khi gần hết deadline, dừng công việc không cần thiết và trả lỗi có phân loại.

### 8.2. Retry có giới hạn

Retry chỉ phù hợp với lỗi tạm thời có khả năng thành công khi thử lại, chẳng hạn connection reset, một số 5xx hoặc 429 theo chính sách của dịch vụ. Không retry lỗi validation, authorization hoặc request sai định dạng. Tôn trọng `Retry-After` nếu dịch vụ cung cấp.

Một chính sách retry cần có:

- Số attempt tối đa nhỏ và tổng thời gian nằm trong deadline.
- Exponential backoff có jitter để nhiều invocation không retry đồng loạt.
- Phân loại lỗi có thể retry và lỗi không thể retry.
- Giới hạn retry ở một tầng phù hợp; tránh client, gateway, function và SDK cùng retry độc lập.
- Metric/log ghi rõ attempt, loại lỗi và thời gian đã tiêu thụ.

Retry có thể khuếch đại sự cố. Ví dụ 100 request/giây, mỗi request retry thêm hai lần, có thể tạo đến 300 lần gọi downstream/giây trong tình huống xấu. Khi downstream quá tải, retry dồn dập làm hàng đợi dài hơn và kéo dài sự cố.

### 8.3. Bảo đảm idempotency khi request có thể được gửi lại

HTTP client có thể timeout dù server đã thực hiện xong thao tác; message broker có thể giao lại message; nền tảng có thể retry invocation theo cấu hình. Vì vậy, một request được xử lý nhiều lần không được tạo nhiều giao dịch nghiệp vụ ngoài ý muốn.

- Với thao tác ghi, nhận idempotency key hoặc business key ổn định từ caller.
- Lưu trạng thái xử lý và kết quả bằng kho bền vững có ràng buộc unique/conditional write.
- Cập nhật trạng thái và hiệu ứng nghiệp vụ trong cùng transaction khi có thể.
- Dùng outbox/inbox hoặc cơ chế deduplication khi cần phối hợp database và message broker.
- Đặt TTL và chính sách lưu key phù hợp với thời gian retry/redelivery tối đa.
- Không dùng `static Map` trong Java làm kho idempotency; map đó không chia sẻ giữa environment và mất khi instance bị thu hồi.

Nếu một thao tác không thể làm idempotent, cần xác định rõ trạng thái không chắc chắn sau timeout và có quy trình đối soát. Không tự động retry một thao tác thanh toán hoặc tạo đơn hàng chỉ vì client không nhận được response.

## 9. Cold start, mở rộng và chi phí

Serverless tạo thêm environment khi concurrency tăng. Một đợt burst có thể đồng thời tạo nhiều cold start và nhiều kết nối mới đến downstream. Vì vậy, giảm cold start riêng lẻ nhưng bỏ qua giới hạn database có thể làm p99 tệ hơn khi tải tăng.

Đánh giá các lựa chọn bằng dữ liệu:

| Lựa chọn | Tác động kỳ vọng | Chi phí/rủi ro cần cân nhắc |
|---|---|---|
| Giảm dependency và init work | Giảm thời gian khởi tạo cho environment mới | Công sức refactor, tương thích thư viện |
| Tăng memory/CPU | Có thể giảm init và compute time | Chi phí mỗi invocation tăng; cần benchmark |
| Snapshot/AOT/native image | Có thể giảm startup | Build, debug, reflection, restore semantics và tương thích |
| Provisioned/warm capacity | Giảm cold start trong mức capacity chuẩn bị | Trả phí cho capacity nhàn rỗi; burst vượt mức vẫn có thể cold |
| Giới hạn concurrency | Bảo vệ downstream, giảm connection storm | Có thể tăng queue age hoặc throttling |
| Queue và worker bất đồng bộ | Hấp thụ burst, tách API khỏi công việc dài | Tăng độ phức tạp, độ trễ hoàn tất và yêu cầu idempotency |
| Chuyển sang service luôn chạy | Giữ runtime và connection ổn định hơn | Cần quản lý capacity, scaling, patching và chi phí nhàn rỗi |

Tổng chi phí không chỉ là thời gian chạy function. Cần tính cả invocation, memory/CPU, provisioned capacity, gateway, logging/tracing, NAT/egress, database connection/proxy, cache và retry. Một function nhanh hơn nhưng tạo nhiều connection hoặc retry có thể làm tổng chi phí hệ thống tăng.

Khi quyết định tiếp tục dùng FaaS, cân nhắc: request có đủ ngắn và độc lập không; downstream có chịu được concurrency biến động không; cold-start latency có nằm trong SLO sau khi tối ưu không; và cơ chế retry có an toàn không. Nếu latency yêu cầu nghiêm ngặt trong khi tải ổn định, provisioned capacity hoặc service luôn chạy có thể hợp lý hơn. Nếu phần lớn thời gian là truy vấn database, chuyển khỏi FaaS không tự động làm truy vấn nhanh hơn.

## 10. Runbook xử lý API chậm

Bảng dưới đây có thể dùng làm trình tự xử lý sự cố ban đầu.

| Triệu chứng | Kiểm tra trước | Hành động có cơ sở |
|---|---|---|
| p99 tăng, init duration tăng cùng thời điểm | Nhóm cold/warm, số environment mới, thay đổi package/runtime | Đo thành phần init; giảm dependency hoặc cân nhắc capacity/snapshot phù hợp |
| Warm request chậm và span DB dài | Query plan, lock wait, pool wait, connection count | Tối ưu query/index, transaction, pooler và concurrency |
| Warm request chậm và span HTTP dài | DNS/connect/TLS, remote span, response size, retry | Reuse client/connection, kiểm tra region và xử lý bottleneck phía service |
| Pool wait tăng khi concurrency tăng | Pool pending, số environment, giới hạn database | Giới hạn concurrency, điều chỉnh pool hoặc dùng proxy |
| Gateway timeout nhưng function vẫn chạy | Gateway/function timeout và downstream deadline | Đồng bộ timeout, truyền deadline, hủy công việc không còn cần thiết |
| 429/5xx và attempt tăng nhanh | Retry ở client, SDK, function và gateway | Giới hạn retry, backoff+jitter, rate limit và idempotency |
| Function nhanh nhưng client chậm | Gateway, queue, DNS, TLS và mạng client | Tách metric từng lớp; điều tra edge/network |
| Chậm sau idle, request kế tiếp nhanh | Connection reset, DNS/TLS, init duration | Kiểm tra connection lifetime và tái kết nối an toàn |

Khi sự cố đang diễn ra:

1. Xác nhận route, region, version, thời điểm bắt đầu và SLO bị ảnh hưởng.
2. Kiểm tra error rate, p95/p99, throttling, concurrency và queue age.
3. Lấy một số trace chậm đại diện, bao gồm cả request có init và request warm.
4. Xác định chặng chiếm critical path; kiểm tra capacity của downstream trước khi tăng concurrency.
5. Nếu cần giảm tác động tức thời, cân nhắc rate limit, giảm fan-out, tạm tắt nhánh không thiết yếu hoặc chuyển công việc dài sang queue theo runbook của dịch vụ.
6. Sau khi ổn định, xác nhận nguyên nhân bằng thay đổi nhỏ có thể đo, ghi lại kết quả và cập nhật cảnh báo.

Không tăng timeout vô hạn để làm biến mất lỗi hiển thị. Timeout dài có thể giữ invocation và connection lâu hơn, làm tăng concurrency và chi phí. Nếu cần tạm thời tăng timeout, phải kiểm tra giới hạn của các lớp còn lại và theo dõi thời gian giữ tài nguyên.

## 11. Ví dụ điều tra

Giả sử API `GET /orders/{id}` có p50 là 130 ms, p95 là 420 ms và p99 là 2,8 giây. Tỷ lệ request vượt SLO 800 ms tăng sau một đợt traffic burst.

**Quan sát đầu tiên:** function duration của nhóm p99 cao, nhưng không phải mọi request chậm đều có init duration. Nhóm có init duration thường chậm khoảng 1,6–2,0 giây; nhóm warm vẫn có một số request gần 2 giây.

**Đọc trace warm:** một số request mất 1,7 giây ở `orders-db.query`; span còn lại dưới 100 ms. Metric database cho thấy query time ổn định nhưng pool pending tăng mạnh khi concurrency tăng. Điều này cho thấy có ít nhất hai vấn đề: cold start làm chậm request đầu của environment mới, còn pool wait làm chậm cả request warm trong burst.

**Giả thuyết và phép thử:**

1. Đo riêng pool acquisition và query execution để xác nhận thời gian chờ pool.
2. Giảm pool size mỗi environment và đặt giới hạn concurrency phù hợp với capacity database; theo dõi queue age và p99.
3. Kiểm tra khả năng dùng database proxy/pooler để chia sẻ kết nối hiệu quả hơn.
4. Đo init breakdown và loại bỏ dependency không cần thiết trong Java handler.
5. Chỉ sau khi đo cold-start contribution mới thử tăng memory hoặc provisioned capacity trong một giai đoạn có kiểm soát.

**Kết quả cần chứng minh:** pool wait giảm, database connection không vượt ngưỡng, warm p99 cải thiện, cold p99 giảm trong phạm vi capacity đã chuẩn bị, error/throttle không tăng và tổng chi phí nằm trong ngân sách. Nếu chỉ cold p99 cải thiện nhưng warm p99 vẫn cao, phần downstream vẫn chưa được xử lý.

Ví dụ này cho thấy một API có thể có nhiều nguyên nhân latency cùng lúc. Phải chia nhóm và đo từng chặng để tránh coi mọi request chậm là cold start.

## 12. Kiểm thử và phòng ngừa tái diễn

### 12.1. Kiểm thử cold và warm path

- Deploy phiên bản mới trong môi trường staging có cấu hình gần production.
- Ghi nhận init duration của các environment mới và latency request đầu.
- Gửi nhiều request tiếp theo để quan sát warm path, nhưng không giả định nền tảng giữ nguyên một environment.
- Tạo burst có kiểm soát để quan sát số environment mới, concurrency, pool wait và downstream saturation.
- Lặp lại ở region và cấu hình mạng có liên quan.

Không thể chứng minh cold start bằng unit test chạy trong JVM local. Unit test hữu ích cho logic và instrumentation; cold start cần đo trên runtime serverless thực tế. Load test phải có giới hạn và dữ liệu thử nghiệm được kiểm soát để không gây quá tải hệ thống dùng chung.

### 12.2. Kiểm thử downstream và retry

- Dùng stub/fault injection để mô phỏng timeout, connection reset, 429 và 5xx.
- Kiểm tra request dừng khi hết deadline và không tạo retry vô hạn.
- Gửi lặp cùng idempotency key để xác minh hiệu ứng nghiệp vụ chỉ xảy ra một lần.
- Mô phỏng database chậm, pool cạn và lock contention trong môi trường an toàn.
- Kiểm tra response lớn, pagination và fan-out để đo ảnh hưởng đến memory và concurrency.

### 12.3. Cảnh báo nên có

- p95/p99 hoặc tỷ lệ vượt SLO theo route.
- Error rate, timeout, throttle và queue/event age.
- Init duration hoặc tỷ lệ cold invocation nếu provider hỗ trợ.
- Pool wait, connection count và query latency cho database quan trọng.
- Downstream HTTP latency, retry rate, 429/5xx và circuit-breaker state.
- Concurrency và chi phí theo function/service.

Alert cần có ngưỡng, thời gian duy trì và liên kết đến dashboard/trace. Một spike ngắn có thể không cần paging, trong khi tỷ lệ vượt SLO kéo dài cần cảnh báo. Không tạo cảnh báo cho từng request hoặc từng user ID.

## 13. Checklist trước khi kết thúc điều tra

- [ ] Đã xác định route, region, version, khoảng thời gian và SLO bị ảnh hưởng.
- [ ] Đã xem p50, p95, p99 và tỷ lệ vượt SLO thay vì chỉ xem trung bình.
- [ ] Đã tách request có cold start và request warm bằng tín hiệu có thể kiểm chứng.
- [ ] Đã so sánh client, gateway, function và downstream trên cùng request.
- [ ] Đã xác định span hoặc chặng chiếm critical path.
- [ ] Đã đo riêng pool wait, connect/TLS, remote processing và retry khi có liên quan.
- [ ] Đã kiểm tra concurrency của function so với capacity database/dịch vụ phía sau.
- [ ] Đã đặt timeout hữu hạn và retry có giới hạn theo deadline.
- [ ] Đã xác minh idempotency cho thao tác có thể được gửi lại.
- [ ] Đã thử nghiệm cold, warm, steady load và burst trên môi trường phù hợp.
- [ ] Đã so sánh latency, error rate, throttling, downstream health và tổng chi phí sau thay đổi.
- [ ] Đã lưu trace/log đại diện, nguyên nhân, thay đổi và kết quả vào hồ sơ sự cố.

## Kết luận

Điều tra API serverless chậm cần bắt đầu từ dữ liệu end-to-end. Cold start thể hiện ở chi phí khởi tạo môi trường Java và thường tác động mạnh đến request đầu; downstream latency thể hiện ở thời gian chờ kết nối hoặc xử lý của dịch vụ phía sau và có thể ảnh hưởng cả request warm. Metric cho biết xu hướng, log liên kết sự kiện, còn trace xác định chặng đang chiếm critical path.

Sau khi xác định nguyên nhân, hãy tối ưu đúng lớp: giảm công việc init hoặc chuẩn bị capacity cho cold start; tái sử dụng client, cải thiện pool/query, giới hạn concurrency và kiểm soát retry cho downstream. Mọi thay đổi phải được xác nhận bằng percentile, SLO, sức khỏe dependency và tổng chi phí. Đây là cơ sở để quyết định tiếp tục dùng FaaS, bổ sung capacity luôn sẵn sàng hay chuyển một phần workload sang mô hình chạy liên tục.
