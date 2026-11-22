# Timeout, deadline và lan truyền hủy yêu cầu

Trong một hệ thống cloud, một API thường không chỉ thực hiện công việc trong một tiến trình. Nó có thể gọi database, cache, dịch vụ thanh toán, API nội bộ, message broker hoặc nhiều dịch vụ khác. Mỗi lời gọi qua mạng đều có thể chậm, mất phản hồi hoặc bị gián đoạn. Nếu mỗi tầng tự chờ theo một thời gian tùy ý, hệ thống dễ giữ request quá lâu, cạn thread/connection, tiếp tục làm việc dù người dùng đã bỏ cuộc và khuếch đại sự cố bằng retry.

Ba cơ chế cần thiết kế cùng nhau là:

- **Timeout:** giới hạn thời gian một thao tác được phép chờ hoặc thực hiện trước khi caller ngừng chờ.
- **Deadline:** thời điểm cuối cùng mà toàn bộ một yêu cầu hoặc hành trình còn giá trị để hoàn tất.
- **Cancellation:** tín hiệu yêu cầu công việc đang chạy dừng lại vì không còn cần thiết hoặc không còn đủ thời gian.

Trong module **CLOUD_ARCHITECTURE**, đây là các nguyên lý quan trọng để thiết kế API có độ trễ dự đoán được, bảo vệ tài nguyên, giảm lỗi dây chuyền và vận hành đáng tin cậy. Mục tiêu không chỉ là trả lỗi nhanh, mà là đảm bảo công việc dừng đúng lúc, dữ liệu giữ đúng trạng thái và các dependency không bị quá tải.

## 1. Vì sao timeout, deadline và cancellation phải đi cùng nhau?

Xét một API đặt lịch:

~~~mermaid
flowchart LR
    Client["Client"] --> Gateway["API Gateway"]
    Gateway --> Booking["Booking API"]
    Booking --> Inventory["Availability service"]
    Booking --> Payment["Payment service"]
    Booking --> DB["Database"]
~~~

Client gửi request và chờ tối đa 2 giây. Gateway có thể chờ Booking 3 giây; Booking lại chờ Inventory 2 giây, Payment 5 giây và database 3 giây. Khi client đã timeout, các tầng phía sau vẫn có thể tiếp tục chờ hoặc thực hiện công việc. Một request duy nhất có thể chiếm tài nguyên nhiều giây sau khi kết quả không còn hữu ích.

Những hậu quả thường gặp:

1. **Thread hoặc connection bị chiếm lâu:** request chậm tích tụ và làm giảm khả năng phục vụ request mới.
2. **Hàng đợi phình to:** server nhận công việc nhanh hơn tốc độ hoàn thành, dẫn đến latency tăng thêm.
3. **Retry storm:** nhiều caller cùng retry sau timeout, làm hệ thống đang yếu nhận thêm tải.
4. **Công việc vô ích tiếp tục chạy:** caller đã hủy hoặc người dùng đóng trang nhưng dependency vẫn xử lý.
5. **Kết quả nghiệp vụ mơ hồ:** caller hết thời gian chờ trong khi thao tác phía server có thể đã commit.
6. **Lỗi lan truyền:** một dependency chậm khiến các tầng phụ thuộc giữ tài nguyên, rồi cả hệ thống suy giảm.

Timeout, deadline và cancellation giải quyết những phần khác nhau của vấn đề. Timeout giới hạn một lần chờ; deadline đặt giới hạn chung cho hành trình; cancellation truyền thông tin rằng công việc không còn cần tiếp tục. Thiếu một trong ba, các tầng có thể không thống nhất về thời gian và mục đích của request.

## 2. Phân biệt các khái niệm và phạm vi thời gian

| Khái niệm | Phạm vi | Câu hỏi được trả lời |
| --- | --- | --- |
| **Connect timeout** | Thiết lập kết nối tới dependency | Bao lâu thì bỏ cuộc nếu không kết nối được? |
| **Read/response timeout** | Chờ dữ liệu/phản hồi sau khi kết nối | Bao lâu không có tiến triển thì caller ngừng chờ? |
| **Request timeout** | Một request tại một tầng | Một request được phép chiếm tài nguyên tối đa bao lâu? |
| **Deadline** | Toàn bộ hành trình từ lúc bắt đầu tới thời điểm hết hạn | Kết quả còn hữu ích đến khi nào? |
| **Cancellation** | Công việc đang chạy ở một hoặc nhiều tầng | Khi caller không cần kết quả nữa, làm sao yêu cầu hệ thống dừng? |
| **Execution limit** | Runtime/job/function hoặc nền tảng thực thi | Một tiến trình được phép chạy tối đa bao lâu? |
| **Idle timeout** | Kết nối hoặc phiên không có hoạt động | Bao lâu thì đóng kết nối nhàn rỗi? |

**Timeout không phải deadline.** Một tầng có thể đặt timeout 1 giây cho từng lần gọi nhưng thực hiện 3 lần retry, tổng thời gian vẫn vượt 3 giây. Deadline là giới hạn tổng; mọi lần gọi và retry phải dùng phần thời gian còn lại.

**Cancellation không phải rollback.** Hủy request có thể dừng công việc chưa thực hiện, nhưng không thể mặc định đảo ngược một giao dịch đã commit hoặc một khoản thanh toán đã được nhà cung cấp xác nhận. Với thao tác có side effect, phải thiết kế idempotency, trạng thái giao dịch và đối soát riêng.

### Ví dụ theo chuỗi thời gian

Giả sử client bắt đầu lúc 10:00:00.000 và yêu cầu phải có phản hồi trong 2 giây:

| Thời điểm | Sự kiện | Ngân sách còn lại |
| --- | --- | ---: |
| 10:00:00.000 | Client tạo request, deadline tại 10:00:02.000 | 2.000 ms |
| 10:00:00.120 | Gateway chuyển tới Booking | 1.880 ms |
| 10:00:00.300 | Booking gọi Inventory | 1.700 ms |
| 10:00:01.050 | Inventory trả kết quả | 950 ms |
| 10:00:01.100 | Booking gọi Payment | 900 ms |
| 10:00:01.850 | Payment chưa phản hồi, phần còn lại 150 ms | 150 ms |
| 10:00:02.000 | Deadline hết hạn | 0 ms |

Ở thời điểm hết hạn, Booking phải dừng chờ hoặc chuyển sang một trạng thái nghiệp vụ được thiết kế trước. Không nên bắt đầu thêm một request phụ có timeout 1 giây vì nó không thể hoàn tất trong deadline ban đầu.

## 3. Thiết kế ngân sách thời gian từ SLO

Không chọn timeout theo cảm giác hoặc chỉ đặt cùng một giá trị cho mọi API. Bắt đầu từ **SLO của hành trình**, phân tích latency p50/p95/p99 và phân bổ ngân sách cho các tầng.

Ví dụ API tìm kiếm cần p99 dưới 1.500 ms:

| Thành phần | Ngân sách minh họa |
| --- | ---: |
| Edge, xác thực và gateway | 100 ms |
| Xử lý tại API | 150 ms |
| Search dependency | 700 ms |
| Database/metadata lookup | 250 ms |
| Serialize, network và dự phòng | 300 ms |
| **Tổng** | **1.500 ms** |

Đây là cách lập budget, không có nghĩa mỗi thành phần được tiêu hết ngân sách độc lập. Nếu search dùng 650 ms thay vì 400 ms, API phải biết phần thời gian còn lại đã giảm. Các lời gọi tuần tự cộng latency; các lời gọi song song có thể hoàn tất theo nhánh chậm nhất nhưng tiêu thụ concurrency lớn hơn.

### Tuần tự và song song

Nếu một request gọi hai dependency tuần tự:

\[
T_{\text{total}}\approx T_A+T_B+T_{\text{overhead}}.
\]

Nếu hai dependency độc lập được gọi song song:

\[
T_{\text{total}}\approx\max(T_A,T_B)+T_{\text{overhead}}.
\]

Gọi song song có thể giảm latency nhưng **không miễn phí**: nó tạo nhiều công việc đồng thời, nhiều connection và có thể gây fan-out. Nếu một nhánh đã thất bại, hệ thống nên hủy nhánh còn lại khi kết quả không còn cần thiết và việc hủy an toàn.

### Timeout cần nhỏ hơn deadline còn lại

Tại thời điểm gọi dependency, hãy tính thời gian còn lại đến deadline, trừ phần cần để xử lý response, commit, serialize và trả kết quả. Timeout của dependency phải nằm trong phần ngân sách đó.

Ví dụ deadline còn 400 ms; cần dự trù 80 ms để xử lý response và hoàn tất request. Timeout cho dependency tối đa khoảng 320 ms, có thể nhỏ hơn nếu còn nhiều nhánh khác. Giá trị thực phải dựa vào latency distribution và SLO, không chỉ lấy p99 của một lần đo riêng lẻ.

### Tránh cộng timeout mặc định ở từng tầng

Một thiết kế lỗi phổ biến:

- API Gateway timeout 30 giây.
- Service A timeout 20 giây.
- Service B timeout 20 giây.
- Database timeout 15 giây.
- Mỗi service lại retry hai lần.

Con số trên không tạo ra một giới hạn hành trình rõ ràng. Mỗi tầng nên nhận deadline hoặc budget từ caller và đặt timeout cục bộ theo phần còn lại. Gateway timeout ngắn hơn downstream cũng cần được phối hợp để tránh client đã nhận 504 trong khi server vẫn thực hiện công việc không cần thiết.

## 4. Tính timeout theo độ trễ thực tế và phân bố tải

Latency có phân bố, không chỉ có một con số trung bình. Hãy phân tích:

- p50, p90, p95, p99 hoặc p99.9 theo endpoint và dependency.
- Thời gian connect, TLS handshake, chờ connection pool, queue wait và thời gian xử lý.
- Tải bình thường, giờ cao điểm, cold start, cache miss và tình huống downstream chậm.
- Lỗi timeout theo vùng, AZ, loại client và phiên bản ứng dụng.
- SLO của caller và SLO của dependency, cùng error budget còn lại.

Timeout quá ngắn làm request hợp lệ bị hủy, retry không cần thiết và tăng tải. Timeout quá dài giữ tài nguyên, làm queue tăng và phát hiện sự cố chậm. Cần chọn ngưỡng để cân bằng **tỉ lệ false timeout** với **thời gian tối đa chấp nhận chờ**.

Một cách bắt đầu là quan sát percentile của dependency dưới tải đại diện, sau đó cộng biên an toàn cho biến động mạng và xử lý. Tuy nhiên, không nên mặc định p99 của dependency là timeout tối ưu: nếu deadline toàn hành trình chỉ còn 300 ms, timeout 1 giây là vô nghĩa; nếu thao tác ghi cần hoàn tất an toàn, timeout quá thấp có thể tạo kết quả không xác định.

### Phân biệt timeout và overload

Timeout có thể đến từ:

1. Dependency thực sự chậm.
2. Connection pool hết chỗ hoặc queue quá dài.
3. Network packet loss, DNS hoặc TLS handshake.
4. CPU, memory, I/O hoặc lock contention.
5. Client đặt timeout quá chặt so với đặc tính workload.

Đừng chỉ tăng timeout khi thấy nhiều timeout. Cần xác định request đã chờ ở đâu và resource nào bị bão hòa. Nếu queue đang tăng, tăng timeout có thể giữ nhiều request hơn và làm sự cố nặng thêm.

## 5. Deadline propagation giữa các tầng

Trong một request phân tán, mỗi tầng phải biết **thời điểm kết thúc chung**. Có hai cách biểu diễn phổ biến:

- **Absolute deadline:** thời điểm hết hạn theo một đồng hồ thời gian, ví dụ Unix timestamp hoặc timestamp có độ chính xác phù hợp.
- **Remaining timeout/budget:** thời lượng còn lại tính từ lúc gửi, ví dụ còn 450 ms.

Deadline tuyệt đối giúp các tầng giữ cùng một mốc kết thúc nếu đồng hồ được đồng bộ đủ tốt. Remaining timeout tránh phụ thuộc trực tiếp đồng hồ giữa các máy nhưng mỗi hop phải trừ thời gian đã tiêu thụ và overhead. Một số giao thức có metadata riêng cho deadline/timeout; cần dùng đúng semantics thay vì tự tạo header không có hợp đồng.

### Nguyên tắc truyền deadline

1. Tầng đầu tiên xác định deadline từ yêu cầu sản phẩm hoặc client, có giới hạn tối đa do server áp đặt.
2. Mỗi tầng nhận deadline, kiểm tra phần thời gian còn lại trước khi bắt đầu công việc.
3. Mọi lời gọi ra dependency sử dụng timeout không vượt phần ngân sách còn lại.
4. Nếu deadline đã hết, từ chối bắt đầu công việc mới và trả lỗi phù hợp.
5. Nếu công việc đang chạy còn khả năng hủy, gửi tín hiệu cancellation xuống tầng dưới.
6. Ghi nhận deadline gốc, thời gian còn lại và nơi request kết thúc để điều tra.

### Không tin deadline từ client vô điều kiện

Client có thể gửi timeout rất dài hoặc giá trị sai. API nên có **maximum request duration** và chuẩn hóa deadline dựa trên policy server. Không cho phép một caller tùy ý giữ tài nguyên backend hàng phút chỉ bằng cách đặt deadline xa. Với caller nội bộ, vẫn cần kiểm tra quyền và giới hạn để tránh cấu hình lỗi lan rộng.

### Ví dụ HTTP header dạng remaining budget

Một hệ thống có thể định nghĩa header nội bộ như X-Request-Timeout-Ms: 450, nhưng đây **không phải chuẩn HTTP phổ quát**. Producer và consumer phải thống nhất:

- Đơn vị chính xác (ms, giây hoặc timestamp).
- Header được trừ như thế nào ở mỗi hop.
- Giới hạn tối đa và hành vi khi header thiếu/sai/âm.
- Có được ghi đè bởi gateway hay không.
- Header có bị client Internet giả mạo không.
- Cách liên kết với request ID và trace context.

Không đặt một header tên giống nhau nhưng ngữ nghĩa khác giữa các team. Nếu nền tảng/giao thức có cơ chế deadline chuẩn, ưu tiên sử dụng contract được tài liệu hóa.

## 6. Cancellation: dừng công việc khi kết quả không còn cần thiết

Cancellation là tín hiệu có thể được truyền từ client tới server, từ gateway tới service và từ service tới các dependency. Nó thường **mang tính hợp tác (cooperative)**: mỗi tầng cần quan sát tín hiệu và tự dừng ở điểm an toàn. Hủy tác vụ không có nghĩa runtime có thể cưỡng bức dừng mọi thread, transaction hoặc thao tác I/O ngay lập tức.

### Những nguyên nhân thường dẫn tới cancellation

- Client đóng kết nối, hủy navigation hoặc người dùng bỏ thao tác.
- API gateway hết timeout hoặc client disconnect.
- Deadline toàn hành trình đã hết.
- Một nhánh song song thất bại, các nhánh còn lại không còn cần thiết.
- Người vận hành dừng job, rollout hoặc shutdown process.
- Hệ thống overload và quyết định load shedding.
- Request bị thay thế bởi một thao tác mới có tính supersede.

### Hành vi cần xác định

| Giai đoạn | Có thể dừng thế nào? | Điều cần bảo toàn |
| --- | --- | --- |
| Chưa bắt đầu xử lý | Không xếp vào queue hoặc reject ngay | Không tiêu tài nguyên cho công việc đã hết hạn |
| Đang chờ pool/queue | Rút khỏi queue hoặc bỏ qua khi consumer nhận | Không làm sai thứ tự hoặc trạng thái queue |
| Đang gọi dependency | Hủy request/stream nếu client và server hỗ trợ | Xử lý kết nối và tài nguyên được giải phóng |
| Đang tính toán | Kiểm tra cancellation giữa các bước/chunk | Không để lại file tạm hoặc state dở dang |
| Đang trong transaction | Rollback nếu transaction còn mở và engine hỗ trợ | Không giả định transaction đã commit có thể rollback |
| Side effect đã xảy ra | Hoàn tất, đối soát hoặc dùng hành động bù | Trạng thái nghiệp vụ chính xác, không lặp thao tác |

### Cancellation không đồng nghĩa ngắt TCP

Client đóng socket không đảm bảo downstream biết ngay. Proxy có thể buffer request, kết nối multiplexing có thể vẫn sống, hoặc server đã đọc hết body và tiếp tục xử lý. Do đó application cần API cancellation riêng hoặc cơ chế context/deadline của framework, đồng thời luôn có timeout ở dependency như một lớp bảo vệ cuối.

### Khi nào không nên hủy?

Một tác vụ nền đã được chấp nhận và có cam kết hoàn thành không nhất thiết phụ thuộc vào kết nối HTTP ban đầu. Ví dụ người dùng gửi lệnh tạo báo cáo dài và API trả 202 Accepted cùng job ID. Sau đó client đóng kết nối, job vẫn cần chạy theo lifecycle đã cam kết. Trong tình huống này, request tạo job kết thúc; **job có deadline, cancellation policy và quyền sở hữu riêng**, không kế thừa cancellation của kết nối client một cách máy móc.

## 7. Truyền deadline/cancellation theo giao thức

### HTTP/1.1 và HTTP/2

HTTP có timeout ở client, proxy, gateway và server framework; nhưng không có một header deadline phổ quát được mọi triển khai tự hiểu. Client có thể đóng kết nối hoặc stream; server cần framework hỗ trợ nhận biết disconnect/cancel và truyền xuống các tác vụ con.

Với HTTP/2, client có thể reset một stream mà không đóng toàn bộ connection; server và thư viện cần xử lý sự kiện reset/cancellation theo semantics của framework. Không nên coi một TCP connection còn mở là mọi request trên connection vẫn còn cần.

### gRPC

gRPC hỗ trợ deadline và cancellation trong mô hình RPC. Client đặt deadline cho call; deadline được truyền trong metadata nội bộ theo cơ chế gRPC; server có thể kiểm tra deadline/cancellation context để dừng xử lý. Hãy dùng API deadline của gRPC thay vì tự đặt header tùy biến rồi kỳ vọng mọi client/server hiểu giống nhau.

Ví dụ Java minh họa tạo call với deadline:

~~~java
import io.grpc.Deadline;
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;

class InventoryCaller {
    static InventoryGrpc.InventoryBlockingStub withDeadline(
            ManagedChannel channel, long remainingMs
    ) {
        InventoryGrpc.InventoryBlockingStub stub =
                InventoryGrpc.newBlockingStub(channel);
        return stub.withDeadline(
                Deadline.after(remainingMs, TimeUnit.MILLISECONDS)
        );
    }
}
~~~

Đoạn mã minh họa cách áp deadline cục bộ cho stub. Trong hệ thống thực, cần truyền **thời gian còn lại của request gốc**, không tạo deadline mới đầy đủ ở mỗi hop; kiểm tra API được sinh từ proto và phiên bản thư viện; xử lý DEADLINE_EXCEEDED/CANCELLED; không nuốt exception rồi tiếp tục xử lý side effect.

### Message broker và queue

Message queue thường có lifecycle khác HTTP:

- Request tạo job có thể có deadline để xác nhận enqueue.
- Message/job có thể mang expiresAt, notAfter hoặc thời hạn nghiệp vụ nếu contract định nghĩa.
- Consumer cần kiểm tra job hết hạn trước khi bắt đầu hoặc trước các side effect quan trọng.
- Cancellation có thể được truyền bằng control message, trạng thái job trong store hoặc API quản lý; việc xóa message khỏi queue không đồng nghĩa consumer đang chạy tự dừng.
- Retry, visibility timeout/ack deadline, lease và job deadline là các cơ chế khác nhau, phải thiết kế nhất quán.

Một job hết hạn có thể được đưa vào dead-letter hoặc trạng thái expired để audit. Không nên âm thầm bỏ job quan trọng nếu sản phẩm cần thông báo hoặc đối soát.

### Event streaming

Với stream dài như WebSocket, server-sent events hoặc stream gRPC, deadline có thể là thời hạn phiên hoặc thời hạn cho từng message. Cancellation/reset cần giải phóng subscriber, cursor và tài nguyên server. Nếu stream gửi event có độ bền, phải phân biệt **hủy việc truyền cho client** với **hủy việc tạo/lưu event**.

## 8. Cài đặt timeout và cancellation trong ứng dụng Java

Java cung cấp nhiều cơ chế khác nhau tùy API blocking, asynchronous hoặc reactive. Chọn đúng cơ chế cho stack ứng dụng và truyền thời hạn xuống các lời gọi con.

### HTTP client với connect timeout và request timeout

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

class CatalogClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(200))
            .build();

    HttpResponse<String> getItem(URI uri, Duration remaining)
            throws Exception {
        if (remaining.isZero() || remaining.isNegative()) {
            throw new IllegalStateException("Request deadline exceeded");
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(remaining)
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }
}
~~~

Trong ví dụ, connect timeout giới hạn thời gian thiết lập kết nối; request timeout giới hạn request theo API HTTP client. Giá trị remaining phải được tính từ **deadline gốc**. Ví dụ rút gọn chưa bao gồm xử lý status code, parse response, cancellation từ caller và phân biệt kết quả nghiệp vụ chưa xác định. Nên dùng client instance được tái sử dụng thay vì tạo client mới cho từng request.

### Cancellation hợp tác trong tác vụ tính toán

Với tác vụ CPU dài, có thể truyền một cờ cancellation hoặc dùng cơ chế interrupt. Worker phải kiểm tra ở những điểm an toàn:

~~~java
import java.util.concurrent.CancellationException;

class ReportBuilder {
    byte[] buildReport(CancellationToken token) {
        ReportAccumulator result = new ReportAccumulator();

        for (int page = 0; page < 10_000; page++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException("Report generation cancelled");
            }

            result.add(renderPage(page));
        }

        return result.toByteArray();
    }
}
~~~

CancellationToken ở đây là interface/pattern minh họa, không phải lớp có sẵn trong Java core. Trong code thực tế cần xác định ai sở hữu token, cách thread-safe để phát tín hiệu, cách cleanup resource và hành vi khi cancel giữa lúc ghi file/database. Không nên xóa file output cuối nếu đã được commit và công bố cho người dùng; có thể ghi file tạm rồi atomically publish khi hoàn tất.

### Future, interrupt và giới hạn của cancel

ExecutorService/Future hỗ trợ request hủy. Tuy nhiên, Future.cancel(true) thường chỉ gửi interrupt tới thread đang chạy nếu tác vụ đã bắt đầu; tác vụ phải hợp tác bằng cách kiểm tra interrupt hoặc gọi hàm blocking có hỗ trợ interrupt. Một số native call, I/O hoặc thư viện không phản ứng nhanh với interrupt. Không thể coi lệnh cancel là bằng chứng công việc đã dừng hoặc side effect đã được hoàn tác.

Một pattern an toàn:

1. Giữ tham chiếu tới task/future theo request hoặc job ID.
2. Khi hết deadline, gửi cancellation một lần và đánh dấu trạng thái hủy đang chờ.
3. Tác vụ kiểm tra interrupt/cancel ở các boundary an toàn và đóng resource.
4. Theo dõi thời gian từ lúc phát cancel tới lúc worker thực sự dừng.
5. Nếu task không thể dừng kịp, cách ly hoặc giới hạn tài nguyên và xử lý kết quả muộn theo quy tắc nghiệp vụ.

### Timeout transaction và connection pool

API có thể đặt timeout cho việc lấy connection, query, transaction và lock wait. Đây là các timeout khác nhau:

- **Connection acquisition timeout:** chờ connection từ pool.
- **Statement/query timeout:** giới hạn thời gian query.
- **Lock timeout:** chờ khóa tối đa bao lâu.
- **Transaction timeout:** giới hạn thời lượng transaction theo framework/engine nếu có.

Nếu chỉ đặt HTTP timeout mà query không bị cancel, database vẫn có thể thực thi query sau khi client đã bỏ cuộc. Cần cấu hình JDBC driver, ORM, database và pool theo khả năng hỗ trợ; kiểm tra bằng cách quan sát query có bị server database dừng thực sự không.

Đừng hủy transaction sau khi đã commit rồi tuyên bố rollback. Nếu response bị mất sau commit, client cần tra cứu bằng request ID/idempotency key để biết kết quả.

## 9. Retry budget, timeout và idempotency

Retry thường được dùng để chịu lỗi mạng nhất thời, nhưng nó cần gắn với deadline và tính an toàn khi lặp.

### Retry chỉ khi còn thời gian

Giả sử deadline còn 500 ms, cần một lần gọi có timeout 300 ms và dự trù 50 ms để xử lý response. Không nên bắt đầu retry thứ hai nếu backoff cộng timeout vượt 150 ms còn lại. Một retry đã chắc chắn không thể trả kết quả trước deadline chỉ làm tăng tải.

Thiết kế retry nên quy định:

- Số lần tối đa và retry budget theo request/service.
- Những loại lỗi được retry (timeout, connection reset, một số status như 503 theo hợp đồng).
- Thao tác nào an toàn để lặp; với thao tác ghi phải dùng idempotency key hoặc cơ chế dedupe.
- Exponential backoff và jitter; tôn trọng Retry-After khi phù hợp.
- Một tầng chịu trách nhiệm retry, tránh nhân số lần gọi ở nhiều tầng.
- Deadline gốc áp dụng cho toàn chuỗi, kể cả thời gian backoff.

### Timeout khi ghi tạo ra kết quả chưa xác định

Ví dụ client gửi POST /payments, payment provider xử lý và thu tiền, nhưng response timeout. Client không thể kết luận giao dịch chưa xảy ra. Nếu gửi lại với idempotency key mới, có thể thu tiền hai lần.

Một quy trình an toàn:

1. Sinh operation ID/idempotency key ổn định cho giao dịch và lưu bền vững.
2. Gửi lệnh với key đó theo contract của provider.
3. Nếu nhận kết quả xác nhận, cập nhật trạng thái nghiệp vụ.
4. Nếu timeout hoặc mất kết nối, ghi trạng thái **UNKNOWN/PENDING_RECONCILIATION**, không suy diễn thành thất bại.
5. Truy vấn trạng thái provider hoặc chờ webhook; nếu retry được, dùng cùng key.
6. Đối soát các giao dịch còn chưa rõ trước khi cho phép thao tác mới.

### Những kết quả timeout không giống nhau

| Tình huống | Ý nghĩa | Phản ứng |
| --- | --- | --- |
| Connect timeout trước khi gửi request | Có thể chưa thiết lập kết nối tới server | Retry có giới hạn nếu thao tác an toàn |
| Timeout khi gửi request | Server có thể đã nhận một phần hoặc toàn bộ request | Xem kết quả là chưa xác định nếu không có bằng chứng |
| Timeout chờ response | Server có thể đã xử lý/commit | Tra cứu bằng request ID/idempotency key |
| Deadline hết trước khi bắt đầu | Không gửi thêm công việc | Từ chối sớm |
| Caller cancel sau khi commit | Kết quả nghiệp vụ đã tồn tại dù caller không nhận response | Tra cứu/đối soát, không rollback giả định |

## 10. Mã lỗi API và cách biểu đạt timeout

Không nên dùng một status code cho mọi trường hợp. Lựa chọn cần phù hợp vai trò của thành phần và contract API:

| Mã | Ý nghĩa phổ biến | Khi nào cân nhắc |
| --- | --- | --- |
| **408 Request Timeout** | Server không nhận đủ request trong thời gian chờ | Client gửi request body quá chậm hoặc không hoàn tất theo giới hạn server |
| **504 Gateway Timeout** | Gateway/proxy không nhận response kịp từ upstream | API gateway chờ service backend vượt timeout |
| **503 Service Unavailable** | Service tạm không thể xử lý | Overload, maintenance hoặc dependency khiến service không thể đáp ứng; có thể kèm Retry-After |
| **429 Too Many Requests** | Caller vượt rate/concurrency limit | Rate limit hoặc quota; client cần backoff theo contract |
| **500 Internal Server Error** | Lỗi server không phân loại rõ hơn | Chỉ dùng khi thực sự là lỗi nội bộ, không thay cho mọi timeout |

Một API server gọi database và query timeout có thể ánh xạ theo contract của sản phẩm; không có quy tắc buộc mọi timeout nội bộ phải trả 504. 504 thường phù hợp với gateway/proxy đang chờ upstream. Nên có error code nghiệp vụ riêng như REQUEST_DEADLINE_EXCEEDED hoặc OPERATION_PENDING khi client cần phân biệt kết quả chưa xác định.

Không gửi stack trace, tên host nội bộ, token hoặc chi tiết hạ tầng trong response. Response nên có request/correlation ID để support có thể tra cứu log an toàn.

### Retry-After và hướng dẫn caller

Nếu server muốn client thử lại, cần nói rõ thời điểm có thể retry và điều kiện. Retry-After có thể biểu diễn thời gian chờ theo HTTP semantics. Tuy nhiên, client vẫn phải tuân theo deadline phía người dùng, backoff và idempotency. Nếu thao tác ghi chưa rõ kết quả, API nên yêu cầu tra cứu operation status trước khi phát sinh một operation mới.

## 11. Cancellation trong các tác vụ bất đồng bộ

Với API trả 202 Accepted và job ID, vòng đời job cần được quản lý độc lập khỏi kết nối HTTP tạo job. Một mô hình trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: Worker nhận job
    QUEUED --> CANCELLED: Hủy trước khi chạy
    RUNNING --> SUCCEEDED: Hoàn tất
    RUNNING --> FAILED: Lỗi không thể retry
    RUNNING --> CANCELLING: Có yêu cầu hủy
    CANCELLING --> CANCELLED: Dừng an toàn
    CANCELLING --> SUCCEEDED: Side effect đã commit
    RUNNING --> EXPIRED: Job hết deadline trước side effect
    FAILED --> QUEUED: Retry theo policy
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Các trạng thái là một ví dụ, phải phù hợp với nghiệp vụ. Chẳng hạn, job gửi báo cáo có thể được hủy khi đang render; job chuyển tiền không thể coi là CANCELLED nếu ngân hàng đã thực hiện lệnh.

### Contract API cho job

Một thiết kế có thể cung cấp:

- POST /reports để tạo job, trả 202 và job ID.
- GET /reports/{jobId} để đọc trạng thái, thời gian tạo, deadline và kết quả.
- DELETE /reports/{jobId} hoặc endpoint cancel riêng để yêu cầu hủy nếu trạng thái cho phép.

DELETE request chỉ **đưa ra yêu cầu hủy**; response nên thể hiện trạng thái đang hủy hoặc đã hủy theo semantics. Nếu job đã hoàn tất, hệ thống không được giả vờ đã xóa side effect. Cần kiểm tra quyền sở hữu job, chống hủy job của tenant khác và audit hành động.

### Job deadline và message expiry

Job có thể được queue giữ lâu hơn thời hạn nghiệp vụ. Hệ thống nên lưu thời điểm hết hạn ở metadata bền vững và kiểm tra khi dequeue. TTL của message broker có thể chỉ xóa message khỏi queue theo semantics broker; nó không thay thế logic kiểm tra ở worker, đặc biệt khi message đã được nhận hoặc đang chạy.

## 12. Quan sát timeout và cancellation

Chỉ đếm số request trả 504 không đủ tìm nguyên nhân. Cần đo ở từng tầng và toàn bộ hành trình.

| Chỉ số | Ý nghĩa |
| --- | --- |
| Request latency p50/p95/p99 | Phân bố thời gian end-to-end và tail latency |
| Deadline exceeded rate | Tỉ lệ request hết deadline tại từng endpoint |
| Timeout by phase | Connect, pool wait, TLS, response/read, database query |
| Cancellation requested/completed | Số tín hiệu hủy và số tác vụ thực sự dừng |
| Cancellation lag | Thời gian từ lúc yêu cầu hủy tới khi worker giải phóng tài nguyên |
| Work after caller gone | Công việc tiếp tục sau client disconnect/deadline |
| Retry attempts per request | Mức khuếch đại tải do retry |
| In-flight requests and queue depth | Tài nguyên đang bị giữ và backlog |
| Late result rate | Tỉ lệ response/kết quả tới sau deadline |
| UNKNOWN operation count | Giao dịch ghi chưa xác định cần đối soát |

### Tracing và log

Mỗi request nên có trace ID/correlation ID, deadline gốc, budget còn lại tại các hop, timeout cấu hình, upstream, status/error category và cancellation reason. Ghi thời gian chờ connection pool riêng với thời gian query để phân biệt nghẽn ở client pool với nghẽn database.

Không tạo metric label có cardinality rất cao như raw request ID, user ID hoặc URL đầy đủ. Những giá trị đó phù hợp với trace/log có kiểm soát truy cập; metric nên dùng endpoint class, dependency, region, error category và trạng thái tổng hợp.

### Cảnh báo

- Tỉ lệ deadline exceeded tăng hoặc vượt error budget.
- p99 tăng trong khi throughput giảm hoặc queue depth tăng.
- Cancellation requested tăng nhưng cancellation completed không tăng tương ứng.
- Số query/call tiếp tục chạy sau khi caller timeout tăng.
- Retry attempts/request tăng đột biến.
- UNKNOWN payment/booking operations tích tụ hoặc quá hạn đối soát.

Đặt alert theo ảnh hưởng người dùng và xu hướng, tránh cảnh báo chỉ dựa vào một timeout đơn lẻ.

## 13. Case study: API đặt lịch có deadline 2 giây

Giả sử nền tảng đặt lịch có một API tạo booking. Mục tiêu minh họa:

- Client nhận phản hồi trong tối đa **2.000 ms**.
- Booking phải tránh tạo bản ghi trùng khi client retry.
- Availability được gọi đồng bộ vì cần xác nhận thời gian còn chỗ.
- Email xác nhận được gửi bất đồng bộ.
- Payment provider có độ trễ biến động và có thể trả response muộn.
- Hệ thống cần phân biệt booking chưa commit, đã commit và đang chờ xác minh thanh toán.

### Bước 1 — Phân bổ deadline

| Thành phần | Budget minh họa |
| --- | ---: |
| Gateway và xác thực | 100 ms |
| Kiểm tra/validate tại Booking | 150 ms |
| Availability | 350 ms |
| Payment provider | 900 ms |
| Commit và cập nhật trạng thái | 250 ms |
| Serialize, network và headroom | 250 ms |
| **Tổng** | **2.000 ms** |

Các budget trên là giả định ban đầu, cần thay bằng latency distribution và benchmark. Payment provider có thể có p99 vượt 900 ms; khi đó API phải quyết định chính sách: trả trạng thái pending, dùng luồng xác minh bất đồng bộ hoặc từ chối trước khi side effect xảy ra theo yêu cầu nghiệp vụ. Không thể chỉ tăng timeout lên 5 giây nếu client SLO vẫn là 2 giây.

### Bước 2 — Định nghĩa cancellation

- Nếu request bị hủy **trước khi bắt đầu**: không làm gì thêm.
- Nếu request đang chờ Availability và chưa có side effect: yêu cầu hủy lời gọi khi deadline hết.
- Nếu đang chờ Payment: chỉ hủy chờ/connection khi protocol hỗ trợ; kết quả thanh toán có thể vẫn chưa xác định.
- Nếu booking transaction chưa commit: rollback transaction nếu còn mở và an toàn.
- Nếu booking đã commit: không giả vờ rollback chỉ vì client disconnect; tra cứu operation theo idempotency key.
- Email được đưa vào outbox sau commit; job email có lifecycle riêng, không bị hủy theo HTTP request ban đầu.

### Bước 3 — Idempotency và trạng thái operation

Client gửi một idempotency key ổn định. Booking API ghi nhận key cùng payload hash và trạng thái xử lý. Nếu cùng key và cùng payload đến lần nữa, API trả kết quả đã lưu hoặc trạng thái đang xử lý. Nếu cùng key nhưng payload khác, trả lỗi theo contract.

Nếu Payment timeout, operation chuyển sang trạng thái PENDING_RECONCILIATION (tên minh họa). Worker riêng truy vấn provider hoặc xử lý webhook, sau đó cập nhật kết quả. Client có thể GET trạng thái operation thay vì khởi tạo khoản thanh toán mới.

### Bước 4 — Phản hồi và xử lý muộn

Nếu toàn bộ giao dịch hoàn tất trước deadline, trả thành công. Nếu deadline hết nhưng transaction chưa commit, trả lỗi timeout phù hợp và dừng các công việc chưa cần thiết. Nếu payment có thể đã thành công nhưng không nhận được xác nhận, trả trạng thái chưa xác định/đang xác minh kèm operation ID; không ánh xạ thành “thanh toán thất bại” nếu chưa có bằng chứng.

### Bước 5 — Đo hiệu quả

Theo dõi latency end-to-end, timeout theo dependency, tỉ lệ payment pending, thời gian đối soát, retry, cancellation lag, booking duplicate và email queue lag. Đánh giá theo SLO của hành trình, không chỉ số lượng API trả 200.

## 14. Kiểm thử timeout, deadline và cancellation

Resilience test nên chứng minh rằng hệ thống không tiêu tài nguyên vô hạn, không xử lý side effect ngoài ý muốn và giữ dữ liệu đúng khi caller bỏ cuộc.

| Bài thử | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Dependency chậm | Availability trả sau 1,5 giây | Booking tuân deadline, không giữ request quá budget |
| Connect timeout | Không thể thiết lập kết nối Payment | Caller dừng trong timeout, retry có kiểm soát |
| Response timeout sau commit | Provider thực hiện payment nhưng response bị mất | Operation thành pending/unknown; không tạo payment mới với key khác |
| Client disconnect | Caller đóng HTTP connection | Cancellation lan truyền tới tác vụ có thể hủy |
| Một nhánh song song lỗi | Search metadata lỗi, nhánh recommendation còn chạy | Hủy nhánh không còn cần thiết nếu an toàn |
| Queue job hết hạn | Worker nhận job sau deadline | Không bắt đầu side effect đã quá hạn; audit trạng thái |
| Retry storm | Nhiều client timeout đồng thời | Backoff/jitter/rate limit giới hạn lượng retry |
| Shutdown khi đang chạy | Pod nhận SIGTERM trong lúc request active | Ngừng nhận request mới, drain hoặc cancel theo grace period |
| Query không phản hồi | Database query vượt timeout | Query thực sự bị cancel/cleanup theo cơ chế engine |

### Fault injection

Có thể mô phỏng latency, packet loss, DNS failure, giới hạn connection pool, database lock, queue backlog hoặc provider 5xx. Bắt đầu ở môi trường kiểm thử và tải đại diện; đặt điều kiện dừng để tránh gây sự cố lan rộng. Sau mỗi thử nghiệm, xác minh cả:

- Caller nhận response trong deadline hay không.
- Backend có tiếp tục xử lý vô ích sau deadline không.
- Connection/thread/queue có được giải phóng không.
- Có side effect nào xảy ra hai lần hoặc bị bỏ dở không.
- Log/trace có chỉ ra tầng làm hết budget không.

### Kiểm thử bằng clock giả lập

Đối với unit test, dùng clock abstraction để kiểm tra deadline còn/hết mà không cần chờ thời gian thực. Test các trường hợp deadline đã hết trước khi gọi dependency, deadline còn rất ít, retry không đủ budget, cancellation giữa các bước và race giữa cancel với commit. Với integration test, vẫn phải kiểm tra framework/client/database thực sự có phản ứng như mong đợi.

## 15. Những sai lầm thường gặp

1. **Timeout riêng lẻ nhưng không có deadline toàn hành trình:** mỗi tầng có thể chờ cộng dồn quá lâu.
2. **Retry làm mới timeout:** mỗi lần retry lại được cả ngân sách mới, kéo dài request và khuếch đại tải.
3. **Đặt timeout cao để giảm lỗi:** che giấu overload và giữ connection/thread lâu hơn.
4. **Timeout quá thấp theo p50:** nhiều request hợp lệ bị cắt ở tail latency.
5. **Không truyền cancellation:** caller hết hạn nhưng các tầng con vẫn chạy.
6. **Giả định client disconnect tự dừng server work:** proxy/framework có thể không truyền tín hiệu tới worker.
7. **Coi Future.cancel là rollback:** task có thể không dừng ngay; side effect đã commit không bị hoàn tác.
8. **Hủy job nền theo HTTP request:** job đã được chấp nhận cần lifecycle riêng.
9. **Retry thao tác ghi với key mới:** có thể tạo thanh toán hoặc booking trùng.
10. **Không phân biệt timeout trước gửi và sau commit:** xử lý sai trạng thái nghiệp vụ.
11. **Không tính pool wait và queue wait:** chỉ nhìn query time nên bỏ sót điểm nghẽn.
12. **Dùng status code không nhất quán:** caller không biết nên retry, tra cứu hay dừng.
13. **Không ghi nhận kết quả muộn:** backend vẫn hoàn thành sau deadline nhưng không ai biết.
14. **Thiếu test dưới tải:** timeout/cancellation hoạt động trong đơn lẻ nhưng thất bại khi nhiều request đồng thời.

## 16. Bài tập thực hành và đáp án định hướng

Một API tổng hợp thông tin sản phẩm có deadline **1.200 ms**. Gateway dùng 100 ms, xử lý nội bộ cần 150 ms, còn lại cho các dependency. API gọi Catalog trong 300 ms, Pricing trong 400 ms và Recommendation trong 350 ms. Ba lời gọi được thực hiện **song song**. Cần thêm 100 ms cho serialize và trả response.

### Câu 1 — Các dependency có fit deadline không?

**Đáp án:** Nhánh chậm nhất 400 ms. Tổng ước lượng \(100+150+400+100=750\) ms, còn headroom khoảng 450 ms. Tuy nhiên, cần tính queue/connection setup, tail latency và độ biến động; timeout từng dependency phải bị giới hạn bởi deadline còn lại.

### Câu 2 — Recommendation lỗi sau 250 ms, Catalog/Pricing vẫn chạy. Làm gì?

**Đáp án định hướng:** Nếu recommendation là chức năng phụ và có fallback hợp lệ, có thể bỏ nhánh recommendation và trả dữ liệu từ Catalog/Pricing; phát tín hiệu cancellation tới nhánh còn lại nếu kết quả của nó không cần nữa. Không nên làm hỏng toàn bộ API vì một tính năng không thiết yếu.

### Câu 3 — Nếu ba dependency được gọi tuần tự thì sao?

**Đáp án:** Tổng dependency là \(300+400+350=1.050\) ms. Cộng gateway, xử lý và serialize: \(100+150+1.050+100=1.400\) ms, vượt deadline 1.200 ms. Cần thay đổi thứ tự/parallelization, giảm work hoặc định nghĩa fallback.

### Câu 4 — Client gọi API tạo thanh toán, nhận timeout. Có thể coi thanh toán thất bại không?

**Đáp án:** Không. Server/provider có thể đã commit. Cần giữ idempotency key, lưu trạng thái chưa xác định và đối soát; retry nếu có phải dùng cùng key theo contract.

### Câu 5 — Client hủy request tải báo cáo, job đã được API trả 202 và nằm trong queue. Có nên hủy job không?

**Đáp án:** Không tự động. Job đã được chấp nhận có lifecycle riêng. Chỉ hủy khi có lệnh cancel rõ ràng và trạng thái cho phép; job kiểm tra cancellation ở điểm an toàn và xử lý file/output tạm phù hợp.

### Câu 6 — Vì sao timeout ở HTTP client chưa đủ bảo vệ database?

**Đáp án:** Driver/query có thể tiếp tục thực thi nếu timeout HTTP chỉ làm caller ngừng chờ. Cần query/statement/transaction timeout, hủy statement theo driver, kiểm tra query thực sự dừng và giải phóng connection đúng cách.

## 17. Checklist review API

- Đã định nghĩa SLO và deadline end-to-end cho từng hành trình quan trọng chưa?
- Timeout connect, pool wait, read, query và execution có được phân biệt không?
- Các tầng nhận deadline gốc/remaining budget và không tự tạo ngân sách mới chưa?
- Có giới hạn maximum request duration phía server không?
- Retry có giới hạn, backoff, jitter, budget và idempotency phù hợp chưa?
- Client disconnect/deadline có truyền cancellation tới các tác vụ có thể hủy không?
- Job bất đồng bộ có lifecycle, expiry và cancellation policy riêng chưa?
- Giao dịch chưa rõ kết quả có trạng thái pending/unknown và cơ chế đối soát không?
- Status code/error contract có hướng dẫn caller retry, tra cứu hoặc dừng không?
- Có metric/tracing cho timeout phase, cancellation lag, late result và retry không?
- Có test dependency chậm, client disconnect, query chạy lâu và mất response sau commit không?
- Có runbook và owner xử lý khi deadline exceeded hoặc unknown operation tích tụ không?

Khi kết thúc review, hãy chứng minh **mỗi tầng còn bao nhiêu thời gian, công việc nào được dừng, side effect nào cần bảo vệ và cách hệ thống xử lý kết quả chưa xác định**. Timeout giúp giới hạn chờ; deadline giữ toàn hành trình trong ngân sách; cancellation giải phóng công việc không còn cần thiết. Ba cơ chế chỉ thật sự hữu ích khi được thiết kế và đo lường như một hợp đồng xuyên suốt các tầng.

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Dependency chậm hoặc mất kết nối có làm cạn tài nguyên và gây lỗi dây chuyền không? | Timeout budget, retry limit, cancellation test, SLO/error budget |
| **Bảo mật** | Deadline/header có bị caller giả mạo để giữ tài nguyên? Log có lộ dữ liệu nhạy cảm? | Giới hạn server-side, authentication, authorization, log policy |
| **Hiệu năng** | Tail latency, connection pool, queue wait và fan-out được kiểm soát ra sao? | p95/p99, in-flight, pool wait, dependency tracing |
| **Tối ưu chi phí** | Công việc vô ích sau caller timeout có tiếp tục tiêu CPU, connection và tiền không? | Late-work rate, cancellation lag, compute/operation |
| **Vận hành xuất sắc** | Đội trực có thể xác định tầng làm hết deadline và xử lý operation chưa rõ kết quả không? | Dashboard, correlation ID, runbook, đối soát |
| **Tính bền vững** | Workload có tiếp tục tiêu tài nguyên sau khi không còn giá trị không? | Cancellation effectiveness, autoscaling và capacity utilization |

Timeout và cancellation là một phần của hợp đồng giữa các thành phần. Chúng cần được thiết kế cùng retry, idempotency, transaction và observability; cấu hình một con số ở API gateway không đủ để chứng minh hệ thống chịu được sự cố.
