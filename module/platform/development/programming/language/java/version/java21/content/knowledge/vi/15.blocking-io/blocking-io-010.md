# Phân tích bottleneck ở dịch vụ phụ thuộc khi tăng mức đồng thời

Khi tăng số tác vụ đồng thời trong ứng dụng Java 21, throughput không nhất thiết tăng theo. Một ứng dụng có thể tạo rất nhiều virtual thread nhưng vẫn bị giới hạn bởi database, HTTP service, message broker, connection pool hoặc quota của hệ thống bên ngoài. Khi dịch vụ phụ thuộc đạt giới hạn, số tác vụ đang chờ và thời gian phản hồi thường tăng nhanh trong khi throughput gần như đứng yên.

Phân tích bottleneck cần đo cả ứng dụng gọi và dịch vụ được gọi. Chỉ nhìn CPU của ứng dụng hoặc số virtual thread đang chạy sẽ không đủ để xác định nguyên nhân. Cần tìm xem thời gian bị tiêu tốn ở bước chờ connection, chờ permit, truyền dữ liệu, xử lý tại dịch vụ đích hay chờ kết quả trả về.

## 1. Hiểu quan hệ giữa concurrency, latency và throughput

Ba đại lượng cần theo dõi:

- **Concurrency**: số tác vụ hoặc lời gọi đang được xử lý đồng thời.
- **Latency**: thời gian từ lúc bắt đầu đến lúc hoàn tất một thao tác.
- **Throughput**: số thao tác hoàn tất trong một đơn vị thời gian, ví dụ request/giây.

Trong một hệ thống ổn định, định luật Little mô tả quan hệ:

**L = λ × W**

Trong đó:

- **L** là số yêu cầu trung bình đang ở trong hệ thống, bao gồm cả yêu cầu chờ.
- **λ** là throughput trung bình, tính bằng yêu cầu mỗi giây.
- **W** là thời gian trung bình một yêu cầu ở trong hệ thống, tính bằng giây.

Ví dụ, nếu trung bình có 80 yêu cầu đang chờ hoặc được xử lý và thời gian trung bình trong hệ thống là 0,4 giây, throughput tương ứng ở trạng thái ổn định là khoảng 200 yêu cầu/giây. Công thức này mô tả một hệ thống ổn định; nó không có nghĩa tăng L vô hạn sẽ làm throughput tăng vô hạn.

Khi dịch vụ phụ thuộc đã đạt công suất, tăng concurrency thường làm tăng số yêu cầu xếp hàng. Throughput bị giới hạn bởi năng lực xử lý của dịch vụ đích, còn W tăng do thời gian chờ. Đây là lý do một bài kiểm thử có thể cho thấy số virtual thread tăng mạnh nhưng số request hoàn tất mỗi giây gần như không đổi.

## 2. Nhận diện đường cong bão hòa

Khi tăng tải theo từng bước, hệ thống thường có ba vùng:

| Vùng tải | Throughput | Latency và hàng đợi |
|---|---|---|
| Dưới điểm bão hòa | Tăng theo tải | Latency tương đối ổn định, hàng đợi nhỏ |
| Gần điểm bão hòa | Tăng chậm dần | p95/p99 bắt đầu tăng, tài nguyên gần chạm giới hạn |
| Vượt điểm bão hòa | Gần như đi ngang hoặc giảm | Hàng đợi, timeout và lỗi tăng nhanh |

Điểm bắt đầu mà latency tăng mạnh trong khi throughput không còn tăng tương ứng thường được gọi là saturation knee. Mục tiêu vận hành là giữ tải trong vùng có độ trễ và tỷ lệ lỗi chấp nhận được, đồng thời có đủ khoảng trống cho đợt tăng tải ngắn.

Không chỉ xem latency trung bình. Hãy theo dõi **p50, p95 và p99**. Trung bình có thể vẫn đẹp trong khi một nhóm request phải chờ connection hoặc bị retry nhiều lần.

## 3. Đo ở từng ranh giới của lời gọi phụ thuộc

Một request có thể đi qua nhiều bước: nhận request, lấy connection, gửi dữ liệu, chờ dịch vụ đích, đọc response và giải phóng tài nguyên. Gắn thời gian và bộ đếm cho từng bước sẽ giúp xác định chính xác nơi chờ.

| Chỉ số | Ý nghĩa khi tăng concurrency |
|---|---|
| Request rate và throughput hoàn tất | Tải vào và năng lực xử lý thực tế |
| In-flight requests | Số request đang chạy hoặc chờ |
| p50/p95/p99 latency | Mức độ trễ và phần đuôi phân phối |
| Thời gian chờ semaphore và số lần từ chối | Caller có đang bị giới hạn bởi bulkhead hay không |
| Thời gian chờ connection pool | Nút thắt ở pool trước khi request tới dịch vụ đích |
| Active connections và pending borrowers | Pool có chạm giới hạn hay không |
| Thời gian gọi downstream | Dịch vụ đích, mạng và xử lý response |
| Timeout, HTTP 429, HTTP 5xx và lỗi kết nối | Quá tải, giới hạn tốc độ hoặc lỗi phụ thuộc |
| Retry attempts trên mỗi request | Mức độ khuếch đại tải do retry |
| CPU, heap, GC và thread pinning ở ứng dụng | Nút thắt nội bộ của caller |
| Queue depth, CPU và latency ở dịch vụ đích | Năng lực và hàng đợi phía downstream |

Đặt timer quanh từng ranh giới thay vì chỉ đo toàn bộ request. Ví dụ, với JDBC, tách thời gian chờ lấy connection khỏi thời gian thực thi query. Với HTTP, tách thời gian chờ giới hạn concurrency nội bộ khỏi thời gian gửi và nhận response.

Các metric nên có nhãn với số lượng giá trị hữu hạn như tên dịch vụ, operation hoặc kết quả. Tránh dùng request ID, user ID hay URL chứa ID làm metric label vì cardinality lớn làm tăng chi phí lưu trữ và truy vấn metrics. Dùng trace hoặc log có cấu trúc để theo dõi từng request.

## 4. Phân biệt bottleneck ở caller, pool và dịch vụ đích

Một số dấu hiệu thường gặp:

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| CPU caller cao, CPU downstream thấp | Caller đang tốn CPU ở serialize, validate, mã hóa hoặc xử lý dữ liệu |
| CPU caller thấp, nhiều virtual thread chờ, pool hết connection | Pool hoặc giới hạn connection đang làm hàng đợi tích tụ |
| Thời gian lấy connection cao nhưng query sau khi lấy connection nhanh | Pool quá nhỏ, connection bị giữ quá lâu hoặc có transaction dài |
| Thời gian query tăng cùng CPU/queue ở database | Database gần giới hạn xử lý, query hoặc lock contention cần kiểm tra |
| HTTP 429 tăng | Dịch vụ đích đang áp dụng rate limit hoặc quota |
| HTTP 5xx và timeout tăng cùng latency downstream | Dịch vụ đích hoặc một dependency phía sau đang quá tải |
| Latency tăng nhưng downstream vẫn khỏe, có nhiều thời gian chờ ở caller | Queue, semaphore hoặc scheduler phía ứng dụng có thể là giới hạn |
| CPU caller thấp nhưng JFR có nhiều virtual thread pinned trên JDK 21 | Blocking trong synchronized monitor hoặc native call có thể giữ carrier |

Một metric riêng lẻ không chứng minh nguyên nhân. Hãy đối chiếu thời điểm tăng tải ở caller với metrics và trace của downstream, rồi kiểm tra xem bottleneck có di chuyển khi thay đổi một giới hạn cụ thể hay không.

## 5. Virtual thread không làm tăng công suất của dependency

Virtual thread giúp ứng dụng duy trì nhiều tác vụ đang chờ I/O mà không cần giữ một platform thread cho mỗi tác vụ. Khi một thao tác blocking được JDK hỗ trợ, virtual thread có thể nhường carrier trong lúc chờ và tiếp tục sau đó.

Tuy nhiên, virtual thread không tăng:

- Số connection mà database cho phép.
- Throughput hoặc quota mà HTTP service cấp.
- Băng thông mạng hoặc số file descriptor của hệ điều hành.
- Năng lực CPU và bộ nhớ của dịch vụ phụ thuộc.

**Executors.newVirtualThreadPerTaskExecutor()** tạo một virtual thread mới cho mỗi task; nó không phải một pool giới hạn số task đang chờ. Vì vậy, nếu gửi mọi request tới một dịch vụ đang quá tải, ứng dụng có thể tạo ra rất nhiều virtual thread cùng chờ. Chi phí thread thấp hơn không đồng nghĩa chi phí hàng đợi bằng không.

Hãy giới hạn số lời gọi đang đi vào dependency bằng connection pool, semaphore hoặc cơ chế admission control phù hợp. Giới hạn này phải dựa trên năng lực đo được của dependency và thời gian giữ tài nguyên, không dựa đơn thuần vào số carrier hoặc số CPU.

Lưu ý rằng semaphore giới hạn số lời gọi đã lấy permit, nhưng không tự giới hạn số virtual thread đang chờ permit. Nếu lượng request đến cao hơn khả năng xử lý trong thời gian dài, hãy kết hợp timeout chờ permit với admission control ở đầu vào hoặc một hàng đợi có giới hạn. Tránh nhận vô hạn công việc rồi để tất cả virtual thread chờ trong bộ nhớ.

## 6. Giới hạn số lời gọi đồng thời bằng Semaphore

**Semaphore** có thể tạo một bulkhead đơn giản cho dịch vụ phụ thuộc. Mỗi lời gọi phải lấy một permit trước khi gọi; permit được trả lại trong finally. Khi hết permit, caller chờ trong một khoảng thời gian giới hạn hoặc từ chối request.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class DownstreamClient {
    private static final Semaphore SLOTS = new Semaphore(40);

    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    static HttpResponse<String> get(URI uri)
            throws IOException, InterruptedException, TimeoutException {
        if (!SLOTS.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new TimeoutException("Dịch vụ phụ thuộc đang bận");
        }

        try {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            return CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );
        } finally {
            SLOTS.release();
        }
    }
}
~~~

Trong ví dụ:

- Semaphore cho phép tối đa 40 lời gọi giữ permit cùng lúc.
- **tryAcquire(100, MILLISECONDS)** giới hạn thời gian chờ permit; nếu không lấy được, caller nhận TimeoutException.
- **connectTimeout** giới hạn thời gian thiết lập kết nối mới.
- **HttpRequest.timeout** giới hạn thời gian chờ response của request.
- finally bảo đảm permit được trả lại cả khi lời gọi lỗi hoặc bị interrupt.

Con số 40 chỉ là ví dụ. Hãy chọn giới hạn từ thử nghiệm tải và giới hạn được thống nhất với dịch vụ đích. Nếu giới hạn quá thấp, caller tự tạo bottleneck; nếu quá cao, downstream vẫn có thể quá tải.

Semaphore giới hạn số lời gọi đang đồng thời ở trong vùng được bảo vệ, không giới hạn tổng số virtual thread đã được tạo và cũng không giới hạn số request mỗi giây. Muốn giới hạn tốc độ đến, cần thêm rate limiter hoặc quota phù hợp.

## 7. Phân biệt concurrency limit, rate limit và connection pool

Ba cơ chế này giải quyết các giới hạn khác nhau:

| Cơ chế | Giới hạn | Ví dụ |
|---|---|---|
| Concurrency limit | Số thao tác đang in-flight cùng lúc | Semaphore cho tối đa 40 lời gọi |
| Rate limit | Số thao tác bắt đầu trong một khoảng thời gian | Tối đa 200 request/giây |
| Connection pool | Số kết nối vật lý được giữ hoặc cho mượn | JDBC pool có tối đa 30 connection |

Một dịch vụ có thể chịu được 100 request đồng thời nhưng chỉ cho phép 200 request mỗi giây. Một database có thể xử lý nhiều query nhưng chỉ cho phép một số lượng connection nhỏ. Chỉ tăng connection pool có thể làm database chịu thêm context switching, lock contention và bộ nhớ mà không tăng throughput.

Đặt giới hạn ở đúng tài nguyên cần bảo vệ. Nếu database là bottleneck, hãy xem thời gian giữ connection, query latency và pool wait trước khi tăng max pool size. Nếu dịch vụ HTTP áp quota theo giây, semaphore một mình không thay thế rate limiter.

## 8. Đặt timeout theo ngân sách của request

Timeout ngăn một request chiếm tài nguyên quá lâu. Nên xác định ngân sách thời gian ở cấp request, rồi phân bổ cho các bước phụ thuộc sao cho tổng thời gian vẫn nằm trong deadline.

Với HTTP Client trong Java 21:

- **HttpClient.Builder.connectTimeout(Duration)** áp dụng cho thời gian thiết lập kết nối.
- **HttpRequest.Builder.timeout(Duration)** áp dụng cho thời gian chờ response của request.
- **HttpClient.send()** là API đồng bộ; có thể gọi theo luồng mã tuần tự trong virtual thread mà không phải chuyển logic sang callback. Khi thao tác blocking được runtime hỗ trợ, virtual thread có thể nhường carrier trong lúc chờ.

Timeout không phải cơ chế tăng năng lực downstream. Nó giúp caller ngừng chờ vô hạn và giải phóng permit/tài nguyên khi request không thể hoàn tất trong ngân sách. Cần chọn timeout theo latency phân vị của dịch vụ, mạng và yêu cầu trải nghiệm người dùng; timeout quá ngắn sẽ tạo lỗi giả khi hệ thống có dao động bình thường.

Nếu một request gọi nhiều dependency tuần tự, không cấp cho từng dependency một timeout đầy đủ bằng toàn bộ deadline. Hãy trừ thời gian đã tiêu tốn và dành phần ngân sách còn lại cho các bước tiếp theo cùng việc trả response.

## 9. Retry có thể khuếch đại bottleneck

Khi downstream chậm hoặc trả lỗi, retry làm tăng số lần gọi cho cùng một request nghiệp vụ. Nếu nhiều caller cùng retry ngay lập tức, tải tăng đúng lúc dependency đang yếu nhất.

Chỉ retry khi lỗi có khả năng tạm thời và thao tác có thể lặp an toàn. Với thao tác ghi, cần bảo đảm idempotency hoặc dùng idempotency key để tránh tạo tác động lặp. Một timeout không chứng minh dịch vụ đích chưa thực hiện request; server có thể đã hoàn tất nhưng response bị mất trên đường về.

Chính sách retry nên có:

- Số lần thử tối đa hữu hạn.
- Exponential backoff và jitter để tránh nhiều client retry cùng thời điểm.
- Deadline tổng thể cho request, không để mỗi lần retry khởi động lại toàn bộ ngân sách.
- Phân loại lỗi có thể retry, ví dụ một số lỗi kết nối hoặc phản hồi tạm thời; không retry lỗi validation hay authorization.
- Giới hạn retry toàn hệ thống để tránh khuếch đại lưu lượng.

Đo **retry attempts/request** và tổng số request thực tế gửi tới dependency. Nếu một request nghiệp vụ tạo ra nhiều lần thử, throughput ở tầng HTTP có thể cao hơn số request nghiệp vụ hoàn tất.

## 10. Thiết kế thử tải để tìm điểm bão hòa

Một phép thử hữu ích phải giữ ổn định các yếu tố khác trong khi tăng concurrency:

1. Chọn một workload đại diện: tỷ lệ đọc/ghi, kích thước payload, số dependency và phân bố dữ liệu.
2. Warm up JVM, JIT, connection pool và cache trước khi lấy số liệu chính.
3. Tăng concurrency theo từng bước, giữ mỗi bước đủ lâu để quan sát trạng thái ổn định.
4. Ghi throughput, p50/p95/p99, error rate, timeout, pool wait và metrics phía downstream.
5. Kiểm tra load generator không trở thành bottleneck về CPU, mạng hoặc số connection.
6. Lặp lại khi thay đổi một giới hạn, chẳng hạn semaphore hoặc pool size, để xem bottleneck có dịch chuyển không.

Nên dùng cả hai kiểu tải khi phù hợp:

- **Closed-loop**: client gửi request mới sau khi request trước hoàn tất. Cách này phản ánh một số mô hình người dùng nhưng có thể che khuất mức tải đến khi latency tăng.
- **Open-loop**: client phát request theo tốc độ đến đã định trước, độc lập với thời gian hoàn tất của request trước. Cách này giúp kiểm tra hệ thống có chịu được arrival rate mục tiêu và bộc lộ hàng đợi tăng.

Không chỉ ghi lại mức concurrency tối đa. Cần tìm mức tải mà p95/p99, error rate và queue vẫn đáp ứng SLO. Tải tối đa trước khi sụp đổ thường không phải mức vận hành an toàn.

## 11. Quan sát virtual thread và pinning trên JDK 21

Khi caller dùng virtual thread nhưng throughput vẫn thấp, hãy phân biệt thời gian virtual thread chờ dependency với thời gian carrier không thể chạy task khác.

Trên JDK 21, virtual thread có thể bị pin khi blocking trong synchronized monitor hoặc trong native/foreign call. Pinning kéo dài có thể làm giảm số carrier sẵn sàng cho công việc khác. JDK Flight Recorder có event **jdk.VirtualThreadPinned** để hỗ trợ tìm các trường hợp này.

Nếu event pinning xuất hiện nhiều, kiểm tra stack trace và vùng mã đang giữ monitor hoặc gọi native. Không thay mọi synchronized bằng lock khác một cách máy móc; hãy xác định vùng blocking kéo dài và đo ảnh hưởng trước khi thay đổi. Hành vi monitor pinning đã được cải thiện từ JDK 24 bởi JEP 491, nên khi phân tích cần ghi rõ runtime thực tế đang chạy.

## 12. Checklist phân tích bottleneck

- [ ] Đo throughput và p50/p95/p99 ở caller lẫn dependency.
- [ ] Đo thời gian chờ connection/permit tách khỏi thời gian xử lý downstream.
- [ ] Theo dõi active connection, pending wait, queue depth, timeout và HTTP 429/5xx.
- [ ] Dùng định luật Little để hiểu quan hệ giữa in-flight, latency và throughput trong trạng thái ổn định.
- [ ] Tìm saturation knee thay vì chỉ tăng concurrency đến mức cao nhất.
- [ ] Không nhầm số virtual thread lớn với năng lực xử lý lớn của dependency.
- [ ] Dùng semaphore/bulkhead để giới hạn in-flight và rate limiter cho giới hạn request/giây.
- [ ] Đặt timeout theo deadline và trả permit/tài nguyên trong finally.
- [ ] Giới hạn retry, dùng backoff/jitter và bảo đảm thao tác retry an toàn.
- [ ] Thử cả closed-loop và open-loop nếu phù hợp với traffic thực tế.
- [ ] Kiểm tra JFR và virtual thread pinning khi caller bị nghẽn dù CPU thấp.
- [ ] Chọn mức concurrency theo SLO và năng lực dependency đã đo được.

## Tài liệu tham khảo

- [Java SE 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 API: Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API: HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API: HttpRequest.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 21 API: ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
