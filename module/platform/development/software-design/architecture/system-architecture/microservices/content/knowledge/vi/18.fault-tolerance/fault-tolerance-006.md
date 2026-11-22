# Bulkhead và tách tài nguyên giữa các phụ thuộc

> **Phạm vi:** Software Design Architecture → System Architecture → Microservices → Khả năng chịu lỗi.  
> **Trọng tâm:** giới hạn mức độ tiêu thụ tài nguyên của từng phụ thuộc để một dịch vụ chậm hoặc lỗi không làm cạn kiệt năng lực phục vụ các luồng nghiệp vụ khác.

## 1. Vấn đề: một phụ thuộc chậm có thể làm cả dịch vụ ngừng phục vụ

Xét **Order Service** nhận yêu cầu tạo đơn hàng. Trong một request, dịch vụ lần lượt hoặc song song gọi **Inventory Service** để kiểm tra hàng, **Payment Service** để thanh toán và **Recommendation Service** để lấy sản phẩm gợi ý. Recommendation chỉ là chức năng bổ sung, nhưng cả ba lời gọi dùng chung một nhóm thread, connection hoặc executor.

Ở trạng thái bình thường, Recommendation trả lời sau 100 ms. Khi Recommendation suy giảm và mỗi lời gọi giữ tài nguyên trong 5 giây, các request đang chờ nó tăng nhanh. Nếu tất cả dùng một pool 200 thread, các lời gọi Recommendation có thể chiếm gần hết pool. Khi đó Inventory và Payment vẫn khỏe nhưng không lấy được thread để chạy. Kết quả là phần tạo đơn hàng thất bại cùng với tính năng gợi ý.

Đây là **resource exhaustion** dẫn tới **cascading failure**: vấn đề bắt đầu từ một dependency nhưng lan sang các chức năng không liên quan thông qua tài nguyên dùng chung.

Các tài nguyên thường bị cạnh tranh gồm:

- Thread xử lý HTTP, worker thread của executor, event-loop nếu bị chặn bằng I/O đồng bộ.
- Connection trong pool HTTP hoặc database; socket, file descriptor và bộ nhớ.
- Hàng đợi đang chờ xử lý; bộ nhớ lưu task hoặc request chưa hoàn thành.
- CPU, heap, container quota và giới hạn số request đồng thời tại downstream.

**Timeout** chỉ giới hạn thời gian chờ của từng lời gọi. Nếu rất nhiều lời gọi cùng chờ đến lúc timeout, hệ thống vẫn có thể hết thread hoặc connection. Cần thêm cơ chế giới hạn số lời gọi đồng thời và cách phân bổ tài nguyên giữa các phụ thuộc.

## 2. Bulkhead là gì?

**Bulkhead pattern** lấy ý tưởng từ các khoang kín trên tàu: khi một khoang gặp sự cố, nước không tràn sang toàn bộ con tàu. Trong microservices, mỗi dependency hoặc nhóm công việc được cấp một **giới hạn tài nguyên độc lập**. Dependency quá tải sẽ làm đầy phần tài nguyên của chính nó; phần còn lại vẫn phục vụ được.

Một bulkhead thường có:

1. **Ranh giới cô lập:** theo dependency, endpoint, nhóm nghiệp vụ hoặc loại workload.
2. **Giới hạn:** số request đồng thời, số thread, số connection hoặc kích thước queue.
3. **Chính sách khi đầy:** từ chối sớm, chờ tối đa một khoảng ngắn, chuyển sang fallback hoặc báo lỗi rõ ràng.
4. **Đo lường:** số slot đang dùng, thời gian chờ, lượt bị từ chối và ảnh hưởng đến độ trễ nghiệp vụ.

~~~mermaid
flowchart LR
    C[Client] --> O[Order Service]
    O --> P["Payment bulkhead<br/>30 concurrent calls"]
    O --> I["Inventory bulkhead<br/>25 concurrent calls"]
    O --> R["Recommendation bulkhead<br/>12 concurrent calls"]
    R -->|Hết slot / timeout| F["Fallback: không hiển thị gợi ý"]
    P --> PD[Payment Service]
    I --> ID[Inventory Service]
    R --> RD[Recommendation Service]
~~~

Sơ đồ minh họa **giới hạn độc lập**. Các con số chỉ là ví dụ, không phải mặc định nên sao chép vào mọi hệ thống.

Bulkhead không làm downstream nhanh hơn và không tự chữa lỗi downstream. Nó bảo vệ những phần còn khỏe bằng cách **giữ sự cố trong phạm vi tài nguyên đã định**.

## 3. Chọn ranh giới cô lập đúng

Nên xác định ranh giới theo **failure domain**: nhóm lời gọi nào có thể chậm, lỗi hoặc tăng tải cùng nhau và nhóm nào phải giữ khả năng hoạt động độc lập.

| Ranh giới | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Theo dependency | Payment, Inventory, Recommendation có giới hạn riêng | Một downstream có thể suy giảm độc lập |
| Theo chức năng | Checkout tách khỏi báo cáo và gợi ý | Chức năng quan trọng không bị tác vụ phụ chiếm tài nguyên |
| Theo workload | Request tương tác tách batch/export | Batch chạy lâu, có nguy cơ chiếm thread và connection |
| Theo tenant/priority | Khách hàng thông thường tách khỏi luồng quản trị quan trọng | Cần công bằng hoặc ưu tiên theo chính sách |
| Theo cấp hạ tầng | Pool kết nối, executor, pod hoặc process riêng | Cần cô lập sâu hơn giới hạn đồng thời ở tầng ứng dụng |

Không nhất thiết tạo một bulkhead cho mọi endpoint. Nếu hàng chục endpoint cùng gọi một dịch vụ có cùng hồ sơ rủi ro, có thể dùng chung nhóm giới hạn. Ngược lại, nếu checkout và báo cáo cùng truy cập database nhưng có yêu cầu độ trễ khác nhau, cần xem xét pool hoặc workload riêng dù cùng một database.

**Cẩn thận với tài nguyên vẫn dùng chung bên dưới.** Hai semaphore độc lập không bảo đảm cô lập nếu các lời gọi vẫn tranh nhau một HTTP connection pool chỉ có 20 connection, cùng một executor toàn cục hoặc một database chỉ nhận được 50 connection. Phải lần theo đường đi của request đến tài nguyên hữu hạn thực sự.

## 4. Các cách triển khai bulkhead

### 4.1. Semaphore bulkhead: giới hạn số lời gọi đồng thời

Semaphore cấp tối đa **N permit** cho một dependency. Lời gọi phải lấy được permit trước khi thực hiện và trả permit sau khi hoàn tất. Khi hết permit, request có thể bị từ chối ngay hoặc chờ một khoảng rất ngắn.

**Ưu điểm:** ít chi phí thread, cấu hình đơn giản, phù hợp lời gọi đồng bộ hoặc luồng đã có executor được kiểm soát. **Giới hạn:** semaphore không tạo thread riêng, không kiểm soát timeout I/O và không bảo vệ khỏi shared executor bị chặn trước khi lời gọi tới bulkhead. Nó chỉ cô lập **số tác vụ đang chạy trong đoạn mã được bảo vệ**.

Ví dụ: cho Recommendation tối đa 12 lời gọi đồng thời; request thứ 13 không lấy được permit trong 10 ms thì trả fallback. Payment dùng một giới hạn riêng, nên việc Recommendation đầy slot không chiếm permit của Payment.

### 4.2. Thread-pool bulkhead: executor và queue riêng

Mỗi nhóm công việc có executor riêng, với số thread và queue **được chặn trên**. Ví dụ Recommendation có 8 worker và queue 16 task; Payment có executor khác. Khi queue Recommendation đầy, hệ thống từ chối thêm tác vụ cho nhóm này.

**Ưu điểm:** cô lập rõ ràng khi dùng I/O chặn hoặc thư viện đồng bộ; dễ giới hạn thread và độ dài queue theo dependency. **Đánh đổi:** thêm context switch, bộ nhớ cho thread, queue và chi phí quản lý; queue dài có thể tạo độ trễ cao dù downstream đã phục hồi. Pool riêng cũng không tránh được cạn CPU, RAM hay connection chung của cả process.

Trong ứng dụng **Spring MVC** với HTTP client blocking, thread-pool bulkhead có thể hữu ích. Trong **Spring WebFlux / Reactor**, không được dùng cách này để che giấu việc chặn event-loop: ưu tiên client non-blocking, giới hạn concurrency bằng toán tử phù hợp và chỉ offload tác vụ blocking sang scheduler riêng có giới hạn.

### 4.3. Cô lập connection pool, queue và tài nguyên hạ tầng

Bulkhead hiệu quả thường phải đi qua nhiều lớp:

- **HTTP:** cấu hình max connection tổng, max connection theo host, thời gian chờ lấy connection và timeout cho từng dependency.
- **Database:** giới hạn kết nối cho từng nhóm truy cập hoặc tách pool khi thực sự cần; tránh cấp tổng số connection vượt khả năng database.
- **Async worker:** tách queue cho tác vụ thời gian thực và batch; giới hạn đồng thời từng consumer.
- **Container/deployment:** cân nhắc autoscaling, CPU/memory quotas, deployment riêng cho workload có mức tiêu thụ tài nguyên rất khác.
- **Downstream:** tổng lưu lượng từ nhiều pod vẫn có thể vượt giới hạn dịch vụ đích; bulkhead trong một pod không thay thế giới hạn toàn cụm.

Chọn mức cô lập nhỏ nhất giải quyết được failure domain thực tế. Tách mọi thứ thành process riêng khi chưa có nhu cầu có thể làm tăng độ phức tạp vận hành mà không tạo thêm giá trị.

## 5. Luồng xử lý khi bulkhead đầy

Một lời gọi qua bulkhead nên có đường đi rõ ràng:

1. Xác định dependency và ngân sách thời gian còn lại của request.
2. Thử lấy slot hoặc đưa task vào queue đã giới hạn.
3. Nếu không nhận được slot trong thời gian cho phép, trả **bulkhead rejection** ngay.
4. Nếu nhận được, thực hiện lời gọi với connect timeout và request/read timeout phù hợp.
5. Dù thành công, lỗi hay bị ngắt, trả slot và ghi metrics.
6. Controller hoặc service áp dụng fallback hay trả lỗi theo **mức độ quan trọng của nghiệp vụ**.

| Loại dependency | Khi đầy slot | Nguyên tắc |
| --- | --- | --- |
| Gợi ý, analytics, enrichment phụ | Bỏ qua kết quả, dùng dữ liệu cache hoặc danh sách rỗng | Ưu tiên duy trì chức năng cốt lõi |
| Inventory/check tồn kho | Trả lỗi có kiểm soát hoặc trạng thái “chưa xác nhận” | Không giả định còn hàng khi không kiểm chứng được |
| Thanh toán | Trả trạng thái rõ ràng, giữ idempotency, có cơ chế kiểm tra/đối soát | Không giả lập thanh toán thành công và không retry tạo giao dịch trùng |
| Công việc nền có thể trì hoãn | Đưa vào hàng đợi bền vững đã giới hạn hoặc từ chối có thể retry | Không giữ vô hạn trong queue bộ nhớ |

**Fast fail** có ích khi downstream đang chậm và việc chờ tiếp không mang lại kết quả có giá trị. Lỗi HTTP có thể là 503 kèm Retry-After khi dịch vụ thiếu năng lực tạm thời; 429 thường phù hợp khi phía ứng dụng chủ động áp quota/rate limit cho client. Mã phản hồi cần nhất quán với API contract, không mặc định mọi lần bulkhead đầy đều là 429.

## 6. Ví dụ Java: bảo vệ Recommendation bằng Semaphore

Ví dụ sau minh họa đường gọi **đồng bộ**. Recommendation là thông tin tùy chọn nên khi không còn permit hoặc dependency không sẵn sàng, gateway trả danh sách rỗng. Interface client là một adapter của ứng dụng; adapter phải tự đặt timeout cho I/O.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class RecommendationGateway {
    private static final int MAX_IN_FLIGHT = 12;
    private static final long MAX_WAIT_MILLIS = 10;

    private final Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
    private final RecommendationClient client;

    public RecommendationGateway(RecommendationClient client) {
        this.client = client;
    }

    public List<String> getSuggestions(String customerId) {
        boolean acquired = false;

        try {
            acquired = permits.tryAcquire(
                MAX_WAIT_MILLIS, TimeUnit.MILLISECONDS
            );

            if (!acquired) {
                // Ghi metric bulkhead_rejected; chức năng này cho phép degrade.
                return List.of();
            }

            // Adapter phải thực thi timeout này ở network client thật.
            return client.fetch(customerId, Duration.ofMillis(250));

        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return List.of();

        } catch (RecommendationUnavailableException unavailable) {
            // Ghi metric dependency_failed; fallback chỉ dành cho gợi ý.
            return List.of();

        } finally {
            if (acquired) {
                permits.release();
            }
        }
    }

    public interface RecommendationClient {
        List<String> fetch(String customerId, Duration timeout);
    }

    public static final class RecommendationUnavailableException
            extends RuntimeException {
        public RecommendationUnavailableException(Throwable cause) {
            super(cause);
        }
    }
}
~~~

**Ý nghĩa của ví dụ:**

- Semaphore là **field dùng chung cho tất cả lời gọi qua cùng gateway instance**; tạo semaphore trong method sẽ vô hiệu hóa giới hạn.
- **tryAcquire** chỉ đợi tối đa 10 ms để xin permit. Nó không có quyền hủy lời gọi mạng sau 250 ms; adapter chịu trách nhiệm thực thi timeout.
- **finally** đảm bảo trả permit kể cả khi client ném exception. Chỉ được release khi đã acquire thành công.
- Nếu thread bị interrupt, khôi phục cờ interrupt để tầng trên nhận biết việc hủy.
- Mỗi instance ứng dụng có 12 permit riêng. Với 5 replica, tổng số lời gọi đồng thời có thể tới 60; cần tính cả năng lực downstream.
- Fallback danh sách rỗng là đúng với gợi ý nhưng **không được sao chép** sang thanh toán, chuyển tiền hoặc ghi dữ liệu quan trọng.

Trong ứng dụng thực tế, cần ghi logs/metrics theo loại kết quả, dùng dependency-specific exception, bảo đảm các cách gọi khác không đi vòng qua gateway, và thống nhất các timeout trong toàn chuỗi request.

## 7. Cấu hình theo tên dependency với Resilience4j

Thay vì tự quản lý semaphore, ứng dụng Spring Boot có thể dùng **Resilience4j Bulkhead**. Hai biến thể thường dùng là semaphore bulkhead và thread-pool bulkhead. Dưới đây là ví dụ cấu hình minh họa; thuộc tính và cách gắn annotation cần phù hợp phiên bản Resilience4j/Spring đang sử dụng.

~~~yaml
resilience4j:
  bulkhead:
    instances:
      recommendations:
        maxConcurrentCalls: 12
        maxWaitDuration: 10ms
      payments:
        maxConcurrentCalls: 30
        maxWaitDuration: 0ms

  thread-pool-bulkhead:
    instances:
      reporting:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
~~~

Khi tích hợp:

- Đặt tên instance theo dependency hoặc workload để số liệu vận hành có ý nghĩa.
- Gắn bulkhead tại **ranh giới outbound call**, không chỉ ở controller; những caller khác của cùng dependency cũng phải đi qua giới hạn tương ứng.
- Xử lý **BulkheadFullException** (hoặc tín hiệu rejection tương đương) theo hợp đồng nghiệp vụ.
- Với thread-pool bulkhead, kiểm tra kiểu trả về bất đồng bộ tương thích với cơ chế decorator/annotation của phiên bản thư viện.
- Nếu dùng Spring AOP annotation, chú ý self-invocation trong cùng bean có thể không đi qua proxy. Test bằng tải thực tế để xác nhận giới hạn có hiệu lực.
- Dùng metrics tích hợp Micrometer/Actuator nếu có, rồi liên kết chúng với dashboard và cảnh báo.

Một cấu hình hoàn toàn đúng cú pháp vẫn có thể tạo điểm nghẽn mới khi giới hạn quá nhỏ. Giá trị cần xuất phát từ tải, thời gian phục vụ, SLO và năng lực downstream.

## 8. Ước tính sức chứa và độ chờ

Để có điểm bắt đầu, dùng định luật Little cho hệ ổn định:

**L ≈ λ × W**

Trong đó:

- **L:** số lời gọi đang xử lý đồng thời trung bình.
- **λ:** tốc độ lời gọi đến dependency (request/giây).
- **W:** thời gian mỗi lời gọi chiếm slot (giây).

Ví dụ Recommendation nhận 60 request/giây, thời gian gọi trung bình 150 ms:

**L ≈ 60 × 0,15 = 9 lời gọi đồng thời.**

Giới hạn 12–16 permit có thể là giả thuyết khởi đầu để load test, vì tải có burst và phân phối latency có đuôi dài. Đây không phải công thức đảm bảo hiệu năng; phải xem p95/p99, concurrency thực tế, retry và traffic theo từng replica.

Khi dependency chậm đến 3 giây nhưng vẫn nhận 60 request/giây, nhu cầu giữ slot sẽ tăng lên khoảng **180** nếu không có hạn chế. Bulkhead 12 slot sẽ **không** tự tăng lên 180; nó bảo vệ Order Service bằng cách bắt đầu từ chối hoặc degrade bớt yêu cầu.

Khi thiết kế giới hạn, cần cân nhắc:

1. **Ngân sách của request:** nếu toàn bộ API chỉ có 800 ms, không nên để một queue chờ 700 ms rồi mới bắt đầu gọi downstream.
2. **Giới hạn downstream:** với N replica, mức concurrency tối đa có thể gần N × maxConcurrentCalls; cộng thêm traffic từ các hệ thống khác.
3. **Số lượng queue:** queue dài biến overload thành độ trễ. Một queue 100 task, tốc độ xử lý 20 task/giây có thể tạo nhiều giây chờ cho task cuối.
4. **Chi phí mỗi request:** request nặng CPU và request chờ I/O đòi hỏi cách tính khác nhau; không dùng chung một con số permit cho mọi loại.
5. **Burst và công bằng:** khi có nhiều tenant hoặc priority, một nhóm traffic có thể độc chiếm permit nếu không bổ sung phân loại.

Bắt đầu với giới hạn nhỏ có thể đo được; dùng canary, load test và số liệu sản xuất để điều chỉnh theo từng dependency.

## 9. Kết hợp Bulkhead với các cơ chế chịu lỗi khác

| Cơ chế | Câu hỏi nó giải quyết | Quan hệ với Bulkhead |
| --- | --- | --- |
| **Timeout** | Chờ một lời gọi tối đa bao lâu? | Hạn chế thời gian chiếm permit; timeout không giới hạn concurrency |
| **Circuit Breaker** | Dependency đang lỗi nhiều, có nên tiếp tục gọi? | Ngắt sớm lời gọi đến dependency bất ổn, còn bulkhead bảo vệ tài nguyên khi có nhiều lời gọi đồng thời |
| **Rate Limiter** | Nhận bao nhiêu request trong một khoảng thời gian? | Giới hạn tốc độ, khác với số lời gọi in-flight; có thể cần cả hai |
| **Retry** | Lỗi tạm thời có nên thử lại? | Có thể khuếch đại tải; mỗi lần retry phải tôn trọng bulkhead và tổng deadline |
| **Load Shedding** | Khi quá tải, nên chủ động từ chối phần nào? | Bulkhead là một ranh giới cho quyết định từ chối có kiểm soát |
| **Fallback/Cache** | Khi dependency không dùng được, còn trả kết quả nào an toàn? | Cho phép dịch vụ tiếp tục cung cấp phần giá trị còn lại |

Không có một thứ tự decorator phù hợp cho mọi ứng dụng. Ví dụ có thể kiểm tra trạng thái Circuit Breaker trước khi giành permit để tránh chiếm slot cho một lời gọi chắc chắn bị chặn; nhưng còn tùy thư viện và cách compose. Quy tắc quan trọng là mỗi lần retry đều phải có **deadline tổng**, không vượt chính sách concurrency, và không biến một request thành hàng chục request gây thêm quá tải.

Với giao dịch có side effect, retry phải dựa trên **idempotency key**, phân biệt lỗi tạm thời với trạng thái kết quả chưa biết, và tuyệt đối không giả định timeout đồng nghĩa downstream chưa thực hiện nghiệp vụ.

## 10. Quan sát hệ thống: làm sao biết bulkhead đang phát huy tác dụng?

Ít nhất nên đo **theo tên bulkhead/dependency**, có phân biệt instance, môi trường và kết quả:

| Nhóm tín hiệu | Ví dụ cần theo dõi | Ý nghĩa |
| --- | --- | --- |
| Sức chứa | Available/used permits, active threads, active connections | Bulkhead có gần đầy liên tục không? |
| Từ chối | Rejected calls, tỷ lệ rejection theo phút | Đang chủ động chặn overload ở đâu? |
| Thời gian | Wait-to-acquire, queue wait, downstream p50/p95/p99 | Chậm do chờ slot hay do chính dependency? |
| Lỗi | Timeout, connection error, Circuit Breaker open, cancellation | Nhận diện nguyên nhân thay vì gộp tất cả thành 5xx |
| Nghiệp vụ | Tỷ lệ checkout thành công, payment pending, fallback recommendation | Hạn chế lỗi kỹ thuật có giữ được mục tiêu nghiệp vụ? |
| Hạ tầng | Thread pool saturation, HTTP/DB pool usage, CPU, heap | Có điểm nghẽn dùng chung nằm ngoài bulkhead không? |

Nếu Recommendation rejection tăng nhưng checkout latency và tỷ lệ thành công vẫn ổn, đó có thể là dấu hiệu **cô lập thành công** trong một sự cố downstream. Tuy nhiên, rejection kéo dài cũng có thể nghĩa là giới hạn đặt quá thấp hoặc upstream tăng tải; cần xem đồng thời throughput, error budget và năng lực downstream.

Tránh gắn customer ID, request ID hoặc URL động làm nhãn metrics có cardinality cao. Dùng distributed tracing để lần theo request cụ thể khi cần điều tra.

## 11. Kiểm thử bằng kịch bản suy giảm

Tạo môi trường kiểm thử có Order Service gọi hai dependency quan trọng và một dependency tùy chọn:

1. **Baseline:** đo throughput, tỷ lệ lỗi, p95 latency, số slot và queue khi mọi dependency khỏe.
2. **Làm chậm Recommendation:** tăng latency từ 100 ms lên 3–5 giây, giữ traffic vào Order Service. Kỳ vọng Recommendation chạm giới hạn rồi bắt đầu fallback; Payment và Inventory vẫn có tài nguyên.
3. **Làm lỗi Recommendation:** trả timeout/503. Kỳ vọng các lỗi được ghi đúng loại, slot được release và hệ thống hồi phục khi dependency khỏe trở lại.
4. **Burst traffic:** tăng đột ngột concurrency. Kỳ vọng queue bị chặn trên, thời gian chờ không tăng vô hạn và API thể hiện chính sách từ chối rõ ràng.
5. **Làm chậm Payment:** kiểm tra luồng quan trọng báo trạng thái phù hợp, không trả thành công giả, không tạo giao dịch trùng do retry.
6. **Chạy nhiều replica:** đo tổng số outbound call và mức tải phía downstream; xác nhận giới hạn cục bộ không vượt năng lực toàn cụm.

**Tiêu chí quan sát:** dependency chậm bị giới hạn tại nhóm của nó; các request khác không bị kẹt theo; không có hàng đợi phình vô hạn; permit/connection được trả sau mọi nhánh kết thúc; tỷ lệ thành công của nghiệp vụ cốt lõi tốt hơn cấu hình dùng chung tài nguyên.

Nên chạy load test cùng fault injection hoặc network impairment. Unit test một lời gọi bị từ chối chỉ chứng minh nhánh xử lý exception, chưa chứng minh sự cô lập dưới contention.

## 12. Những sai lầm thường gặp

- **Có semaphore nhưng vẫn dùng shared executor đã cạn trước đó:** giới hạn ở quá muộn trong call path. Cần cô lập hoặc giới hạn tài nguyên dùng chung thật sự.
- **Tạo pool riêng nhưng queue vô hạn:** tránh hết thread trước mắt, đổi lại backlog, memory pressure và request lỗi thời.
- **Không đặt timeout I/O:** một permit có thể bị giữ rất lâu; toàn bộ bulkhead kẹt vĩnh viễn.
- **Đặt permit quá lớn:** từng dependency lại có khả năng chiếm hầu hết connection hoặc CPU của process, làm mất tác dụng cô lập.
- **Đặt permit quá nhỏ và fallback âm thầm:** chức năng bị degrade thường xuyên nhưng dashboard tổng thể vẫn “xanh”.
- **Mỗi request tạo semaphore mới:** không có giới hạn chung giữa các request.
- **Release permit sai nhánh:** leak permit nếu thiếu finally, hoặc vượt giới hạn nếu release dù acquire không thành công.
- **Chỉ giới hạn tại một replica:** autoscaling làm tổng concurrency vượt sức downstream.
- **Retry ngay khi bị rejection:** tạo retry storm, cần backoff có jitter và giới hạn tổng số thử lại khi chính sách nghiệp vụ cho phép.
- **Giữ permit quá rộng:** chiếm slot trong lúc serialize response, xử lý dữ liệu cục bộ hoặc chờ công việc không liên quan.
- **Tách thread pool nhưng vẫn dùng chung connection pool quá nhỏ:** nghẽn chuyển xuống tầng connection.
- **Áp fallback sai cho nghiệp vụ cốt lõi:** recommendation có thể bỏ qua; thanh toán và thay đổi trạng thái đơn hàng cần trạng thái đúng và cơ chế phục hồi rõ ràng.

## 13. Hướng dẫn áp dụng từng bước

Với một hệ microservices hiện hữu, cách triển khai thực dụng là:

1. Vẽ call graph từ 1–2 API quan trọng, ghi các downstream và tài nguyên thực sự dùng chung.
2. Xác định dependency tùy chọn và dependency bắt buộc; viết rõ chính sách rejection/fallback cho từng cái.
3. Chọn một failure domain có nguy cơ cao và đặt giới hạn đồng thời có thể quan sát được.
4. Cấu hình timeout, max wait, connection pool và queue nhất quán với deadline của request.
5. Công bố metrics và thử tải với dependency chậm trước khi mở rộng pattern.
6. Điều chỉnh số permit dựa trên traffic, latency, capacity downstream, số replica và SLO, rồi mới nhân rộng sang dependency khác.

**Ví dụ quyết định thiết kế:** Nếu Order Service phải duy trì checkout khi Recommendation chậm, hãy đặt bulkhead riêng cho Recommendation, không chờ slot lâu, trả fallback an toàn và bảo đảm nó không chiếm pool được Payment sử dụng. Nếu Payment chậm, ưu tiên trạng thái thanh toán rõ ràng, timeout, idempotency và cơ chế đối soát; không tái sử dụng fallback “thành công” của Recommendation.

## 14. Câu hỏi tự kiểm tra

**1. Tại sao có timeout 2 giây vẫn có thể hết thread?**  
Vì trong 2 giây đó hàng trăm request vẫn giữ thread/connection đồng thời. Timeout giới hạn thời gian một request chiếm tài nguyên, còn bulkhead giới hạn số request cùng chiếm tài nguyên.

**2. Rate limit 100 request/giây có thay thế bulkhead 20 permit không?**  
Không. Nếu mỗi lời gọi mất 5 giây, 100 request/giây vẫn có thể tạo hàng trăm lời gọi in-flight. Tốc độ và concurrency là hai chiều khác nhau.

**3. Nếu có 10 replica, mỗi replica tối đa 20 lời gọi Payment, downstream cần chuẩn bị bao nhiêu concurrency?**  
Chỉ riêng ứng dụng này có thể mở tới khoảng 200 lời gọi đồng thời, chưa tính ứng dụng khác. Phải kiểm tra giới hạn thực của downstream và dùng thêm cơ chế phối hợp khi cần.

**4. Khi một dependency bắt buộc đã đầy slot, có nên trả dữ liệu giả để đáp ứng SLA?**  
Không. Cần trả trạng thái lỗi hoặc pending đúng với nghiệp vụ, kèm idempotency/khôi phục nếu là giao dịch có side effect.

**5. Khi nào cần thread-pool bulkhead thay vì semaphore?**  
Khi phải cô lập các tác vụ blocking vào executor riêng có giới hạn thread/queue; semaphore phù hợp hơn khi chỉ cần chặn concurrency và đã có mô hình thực thi được kiểm soát.

## Tài liệu tham khảo

- Resilience4j — Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- Java SE 21 — Semaphore: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html
- AWS Builders' Library — Using load shedding to avoid overload: https://aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/

**Ghi nhớ:** Bulkhead là một quyết định **phân bổ năng lực và phạm vi chịu lỗi**. Hệ thống chịu lỗi tốt khi sự cố ở một dependency có giới hạn, quan sát được, được xử lý đúng nghiệp vụ và không khiến tài nguyên của các luồng khác cạn theo.
