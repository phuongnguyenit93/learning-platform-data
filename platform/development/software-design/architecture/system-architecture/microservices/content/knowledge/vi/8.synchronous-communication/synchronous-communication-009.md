# Tổng hợp yêu cầu và thực hiện song song có giới hạn

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Giao tiếp đồng bộ

## 1. Bài toán: một phản hồi cần dữ liệu từ nhiều dịch vụ

Trong hệ thống microservices, mỗi dịch vụ thường sở hữu một phần dữ liệu và quy tắc nghiệp vụ. Giao diện sản phẩm, trang chi tiết đơn hàng hoặc dashboard quản trị lại cần **một góc nhìn tổng hợp** để hiển thị. Nếu client tự gọi hàng loạt dịch vụ, client phải biết nhiều endpoint, cách xác thực, xử lý lỗi và quan hệ giữa các miền nghiệp vụ.

Một cách thiết kế là có **API Composition / Aggregator** hoặc lớp **Backend for Frontend (BFF)** nhận một yêu cầu, gọi những dịch vụ cần thiết và ghép kết quả trả về:

    Client
      |
      | GET /orders/8042/summary
      v
    OrderSummaryAggregator
      |----> OrderService       (thông tin đơn)
      |----> PaymentService     (trạng thái thanh toán)
      |----> ShippingService    (trạng thái vận chuyển)
      '----> CustomerService    (thông tin khách)
      |
      '---> SummaryResponse

Các lời gọi tới service khác thường có chi phí mạng, thời gian xử lý và xác suất lỗi riêng. Nếu aggregator thực hiện mọi lời gọi **nối tiếp** dù chúng độc lập, tổng độ trễ có thể lớn. Nếu phát tất cả **song song không giới hạn**, một đợt tăng tải có thể tạo hàng nghìn request nội bộ, làm cạn connection pool và khiến nhiều dịch vụ quá tải.

Vì vậy bài toán có hai phần cần giải cùng nhau:

1. **Chỉ thực hiện song song những tác vụ thật sự độc lập**, để giảm thời gian chờ trên đường phản hồi.
2. **Giới hạn mức đồng thời và tài nguyên**, để một request hoặc một lượng request tăng đột biến không làm hỏng hệ thống.

Mục tiêu không phải tạo càng nhiều thread hoặc future càng tốt. Mục tiêu là đạt độ trễ phù hợp với cam kết trải nghiệm người dùng, giữ tính đúng đắn của dữ liệu, đồng thời bảo vệ các dịch vụ phụ thuộc.

## 2. Ba kiểu quan hệ giữa các lời gọi

Trước khi chọn thực hiện song song, cần hiểu quan hệ dữ liệu và nghiệp vụ giữa các bước.

### 2.1. Độc lập, có thể chạy song song

Ví dụ OrderSummary đã nhận một mã đơn và có đủ quyền truy cập để hỏi OrderService, PaymentService và ShippingService về các thông tin chỉ đọc theo mã đó. Nếu các lời gọi không phụ thuộc kết quả của nhau, chúng có thể cùng khởi chạy và được ghép khi hoàn tất.

    Bắt đầu
       |--------- OrderService ---------|
       |------------ PaymentService ------------|
       |------ ShippingService ------|
       '--------------------------------------> Ghép phản hồi

Tổng thời gian của nhóm gọi song song trong tình huống lý tưởng thường gần **nhánh hoàn tất muộn nhất**, cộng chi phí điều phối và ghép dữ liệu.

### 2.2. Có phụ thuộc đầu ra, phải đi theo thứ tự

Giả sử phải gọi OrderService để lấy danh sách sản phẩm trước khi biết ID cần hỏi Pricing. Khi đó Pricing phải chờ dữ liệu từ OrderService. Không nên ép cả hai khởi chạy đồng thời bằng cách phỏng đoán đầu vào.

    OrderService.getOrder(orderId)
              |
              v
    PricingService.quote(order.items, context)

Tuy nhiên, sau khi đã có danh sách sản phẩm, những lời gọi khác độc lập có thể chạy cùng nhau hoặc được gom batch.

### 2.3. Một phần độc lập, một phần phụ thuộc

Thực tế nhiều workflow là **đồ thị phụ thuộc (DAG)**:

    [Order] ---------------------> [Summary]
       |
       +----> [PriceQuote] ------> [Summary]

    [Shipping] ------------------> [Summary]
    [Payment] -------------------> [Summary]

Order phải có trước PriceQuote, còn Shipping và Payment có thể chạy ngay. Một cách triển khai hợp lý là chia thành các giai đoạn và chỉ đợi những kết quả mà bước sau thực sự cần.

**Lưu ý:** Nếu hai bước cùng ghi hoặc thay đổi trạng thái nhạy cảm như giữ hàng, thu tiền và xác nhận đơn, khả năng song song không chỉ là chuyện thread. Phải xác định các bất biến nghiệp vụ, cơ chế nhất quán và kế hoạch xử lý khi một nhánh thành công còn nhánh khác thất bại.

## 3. Nối tiếp và song song khác nhau thế nào?

Giả sử một lần tải màn hình cần ba lời gọi độc lập, với thời gian thực tế của riêng lần đó là:

| Dịch vụ | Thời gian quan sát |
| --- | ---: |
| OrderService | 80 ms |
| PaymentService | 140 ms |
| ShippingService | 110 ms |

Nếu gọi nối tiếp, tổng thời gian chờ cho ba lời gọi xấp xỉ:

    80 + 140 + 110 = 330 ms

Nếu bắt đầu đồng thời, không giới hạn tài nguyên và không có phụ thuộc:

    max(80, 140, 110) = 140 ms

Thời gian end-to-end vẫn cần cộng overhead xác thực, xử lý, scheduling, serialization, network và ghép phản hồi. Hai phép tính chỉ minh họa quan hệ của các bước trong một request cụ thể, **không phải cam kết rằng p95 end-to-end bằng max hoặc tổng p95 của từng downstream**. Phân vị phải đo trên phân bố thực tế, có xét tương quan giữa các nhánh.

Song song hóa cũng không làm biến mất chi phí. Cùng một request vẫn tiêu thụ ba remote calls và có thể giữ ba kết nối đồng thời thay vì từng kết nối. Đây là đánh đổi giữa **latency** và **mức sử dụng tài nguyên đồng thời**.

## 4. Tại sao song song không giới hạn rất nguy hiểm?

Một mô hình fan-out thường có dạng:

    Số request từ người dùng × Số downstream calls/request
      = Lượng gọi nội bộ được tạo ra

Ví dụ 300 request/giây tới aggregator, mỗi request gọi 8 downstream:

    300 × 8 = 2.400 remote calls/giây

Con số này là tổng số lần gọi được phát nếu mỗi request tạo đủ tám lời gọi; tải phân phối thực tế còn tùy các endpoint đích. Nếu retry diễn ra ở nhiều tầng, số lần gọi có thể tăng hơn mức này.

Nếu mỗi lời gọi giữ tài nguyên lâu hơn vì downstream chậm, số thao tác đang bay (in flight) cũng tăng. Theo trực giác từ Little's Law, khi tốc độ đến gần ổn định, lượng công việc đang tồn tại xấp xỉ **tốc độ đến × thời gian lưu lại hệ thống**. Ví dụ một downstream nhận 500 request/giây và mỗi request mất 0,2 giây, số request đồng thời trung bình có thể quanh 100 trong điều kiện ổn định phù hợp với giả định.

Khi thời gian tăng lên 1 giây mà lưu lượng vẫn 500 request/giây, nhu cầu đồng thời có thể tăng khoảng năm lần. Nếu không có giới hạn, thread, connection, bộ nhớ và queue phình ra; từ đó timeout tăng và sinh retry tiếp, khiến quá tải lan rộng.

### 4.1. Các loại giới hạn cần phân biệt

- **Giới hạn song song trong một request:** một request người dùng tối đa được phát bao nhiêu tác vụ cùng lúc.
- **Giới hạn toàn cục của aggregator:** tổng số tác vụ hoặc kết nối đang hoạt động trên một instance.
- **Giới hạn theo downstream:** tổng số lời gọi đồng thời tới PaymentService, CatalogService hoặc đối tác thứ ba.
- **Giới hạn hàng đợi:** có bao nhiêu công việc được phép chờ trước khi bị từ chối.
- **Rate limit:** số yêu cầu được phép bắt đầu trong mỗi khoảng thời gian; khác với số request đồng thời.
- **Connection pool:** số kết nối có thể dùng và số request chờ kết nối; cần phù hợp với cơ chế multiplexing và loại client.

Một semaphore 20 permits giới hạn số **tác vụ đang giữ permit**, không trực tiếp giới hạn 20 request/giây. Ngược lại, rate limit 200 request/giây không bảo đảm concurrency thấp nếu mỗi request kéo dài nhiều giây.

### 4.2. Giới hạn theo dịch vụ giúp cô lập lỗi

Giả sử Dashboard gọi cả Catalog và Payment. Nếu Payment chậm, các task chờ Payment không nên chiếm toàn bộ tài nguyên khiến Catalog cũng ngừng phục vụ. Dùng **bulkhead** theo dependency (semaphore, thread pool hoặc connection pool có giới hạn) để tránh một phía chiếm hết năng lực xử lý.

Trong hệ thống nhiều replica, giới hạn 20 permits trên từng instance không có nghĩa toàn cụm chỉ được 20 lời gọi đồng thời. Với 6 replica, về lý thuyết có thể có tới 120 lời gọi. Cần tính quy mô cụm và quota thực tế của downstream khi chọn ngưỡng.

## 5. Thiết kế aggregator theo trách nhiệm

Một aggregator phục vụ chủ yếu việc **truy vấn và tổng hợp**. Trước khi triển khai, cần quyết định:

1. Endpoint này phục vụ use case nào: tổng quan đơn, giỏ hàng, danh sách người dùng, dashboard?
2. Trường dữ liệu nào thuộc về service nào? Aggregator có tự tính lại quy tắc nghiệp vụ của service khác không?
3. Thành phần nào bắt buộc để phản hồi hợp lệ, thành phần nào có thể vắng mặt?
4. Khi dữ liệu giữa các service được chụp ở thời điểm hơi khác nhau, người dùng có chấp nhận không?
5. Có dữ liệu nào chứa thông tin nhạy cảm cần xác thực và kiểm soát quyền truy cập riêng?
6. Có thể giảm số remote calls bằng batch hoặc read projection trước khi tăng fan-out không?

**Không biến aggregator thành “siêu service” sở hữu mọi quy tắc nghiệp vụ.** Nếu PaymentService chịu trách nhiệm xác định một giao dịch có được hoàn tiền hay không, aggregator nên lấy kết quả quyết định từ PaymentService hoặc sử dụng contract được công bố, chứ không sao chép logic tính tiền và tự quyết định.

### 5.1. Cấu trúc phản hồi cần thể hiện ý nghĩa dữ liệu

Ví dụ một phản hồi cho màn hình đơn hàng:

    {
      "order": {"id": "8042", "status": "CONFIRMED"},
      "payment": {"status": "PAID"},
      "shipping": {
        "status": "UNAVAILABLE",
        "detailAvailable": false
      },
      "partial": true
    }

Nếu ShippingService timeout và trạng thái vận chuyển là thành phần **tùy chọn** cho màn hình xem đơn, phản hồi có thể thể hiện không tải được thông tin vận chuyển, thay vì âm thầm bịa trạng thái “chưa giao”. Nếu Payment bắt buộc phải có để xác nhận một thao tác quan trọng, không được trả mặc định “PAID” hoặc “UNPAID” khi chưa biết.

Trường "partial" chỉ có nghĩa khi API công bố rõ loại dữ liệu nào có thể thiếu. Một client có thể dùng nó để hiển thị “Chưa tải được thông tin vận chuyển, thử lại”, nhưng không thay đổi quyết định thanh toán từ một phản hồi chưa đủ.

## 6. Required và optional: cách chọn chính sách lỗi

Đối với từng nhánh, phân loại theo nhu cầu nghiệp vụ.

| Loại | Ví dụ | Chính sách có thể áp dụng |
| --- | --- | --- |
| Required | Dữ liệu đơn khi hiển thị chi tiết đơn theo ID | Nếu thất bại, endpoint có thể trả lỗi hoặc trạng thái chưa xác định |
| Required cho quyết định | Trạng thái Payment trước khi cho phép hoàn tiền | Không đưa ra quyết định dựa trên dữ liệu thiếu |
| Optional | Ảnh đại diện, gợi ý sản phẩm, lịch sử xem | Có thể trả partial và báo phần chưa sẵn sàng |
| Có thể dùng cache | Tên/ảnh sản phẩm trong màn hình đọc, khi business cho phép | Dùng cache với độ mới được công bố |
| Có thể tải sau | Timeline vận chuyển chi tiết trong màn hình tổng quan | Trả phần cốt lõi, client yêu cầu bổ sung khi cần |

### 6.1. Fail-fast không luôn là lựa chọn tốt

Nếu không có OrderService thì response không còn nghĩa, việc dừng sớm có thể tiết kiệm tài nguyên. Nhưng nếu một nhánh Optional mất kết nối, hủy toàn bộ các nhánh đang có kết quả hữu ích sẽ làm trải nghiệm tệ không cần thiết.

### 6.2. Partial response phải có hợp đồng rõ

Có thể trả HTTP 200 với body cho biết một số phần không sẵn sàng khi **bản thân endpoint có nghĩa là “lấy thông tin tổng quan có thể không đầy đủ”**. Với endpoint đòi hỏi đầy đủ như “xác nhận thanh toán đủ điều kiện”, trả 200 và một phần dữ liệu giả là sai.

Ngoài schema, cần định nghĩa mã lỗi ổn định cho từng thành phần, khả năng cache, retry từ client và xử lý quyền truy cập. Không dùng dữ liệu cũ hoặc null theo cách khiến client hiểu sai thành trạng thái nghiệp vụ thực sự.

## 7. Deadline tổng và timeout từng nhánh

Tách nhiều lời gọi song song có thể rút ngắn thời gian, nhưng **mỗi request vẫn phải có ngân sách thời gian hữu hạn**.

Ví dụ endpoint summary có mục tiêu hoàn tất trong 700 ms:

    Client request
       |
       |  60 ms: xác thực, kiểm tra input
       | 450 ms: chạy các nhánh cần thiết đồng thời
       | 120 ms: ghép dữ liệu, serialization, trả về
       |  70 ms: phần dự phòng
       v
    Tổng ngân sách: 700 ms

Các con số chỉ để minh họa. Trong thiết kế thật phải dùng SLO, số đo thực tế, tải, độ lớn payload và thời gian p95/p99 của các dependency.

Một sai lầm là cấp 700 ms **cho từng nhánh ở mỗi tầng**, khiến cuộc gọi con vẫn tiếp tục sau khi toàn bộ request đã hết deadline. Nên truyền deadline hoặc thời gian còn lại qua các service, và cắt ngắn ngân sách theo giới hạn riêng từng downstream.

### 7.1. Timeout của future không đồng nghĩa đã dừng HTTP call

Ví dụ một CompletableFuture bị đánh dấu timeout sau 300 ms, nhưng lệnh HTTP chạy trong thread bên dưới có thể vẫn tiếp tục. Hoàn thành future với lỗi không bảo đảm socket hoặc thao tác ở service đích đã bị hủy.

Cần cấu hình timeout tại **HTTP client** hoặc cơ chế transport thực sự, giới hạn tổng deadline và kiểm soát tài nguyên đang giữ. Với thao tác có tác dụng phụ, ngay cả khi client đã hủy, service đích có thể đã thực hiện thành công; không được mặc định có thể gửi lại như một lệnh mới.

### 7.2. Deadline và retry dùng chung một ngân sách

Nếu còn 100 ms trước deadline, một retry dự kiến mất 400 ms không còn hợp lý. Retry nên chỉ được thực hiện khi lỗi có khả năng tạm thời, thao tác an toàn với việc lặp, có backoff và vẫn còn đủ thời gian trong deadline. Tránh retry nhiều tầng cùng lúc làm phình fan-out.

## 8. Ba tầng kiểm soát song song quan trọng

### 8.1. Tầng thứ nhất: giới hạn fan-out theo request

Không cho một request mở vô hạn lời gọi. Ví dụ một search aggregator có 25 nguồn dữ liệu nhưng chỉ cho phép tối đa 4 nguồn xử lý đồng thời; các nguồn còn lại đợi theo thứ tự ưu tiên hoặc bị bỏ qua khi hết deadline.

Cần xác định vì sao gọi tới 25 nguồn. Nếu thực tế đều là query tương tự, hãy cân nhắc batch, projection hoặc cache để giảm nhu cầu fan-out.

### 8.2. Tầng thứ hai: giới hạn tài nguyên thực thi

Executor hoặc scheduler cần có giới hạn concurrency và queue. Một ThreadPoolExecutor dùng **hàng đợi không giới hạn** có thể tránh lỗi reject lúc đầu nhưng giữ công việc quá lâu khi downstream chậm, dẫn tới cạn bộ nhớ hoặc queue latency tăng đột biến.

Một lựa chọn là thread pool có giới hạn, queue hữu hạn và chính sách từ chối rõ. Rejection có thể được ánh xạ sang lỗi quá tải có thể quan sát; không nên âm thầm giữ request không giới hạn.

### 8.3. Tầng thứ ba: giới hạn riêng từng dependency

Một thread pool chung chỉ giới hạn tổng số tác vụ của aggregator. Nếu một downstream chậm chiếm hết số worker, những dependency khỏe vẫn bị ảnh hưởng. Có thể dùng semaphore hoặc pool chuyên biệt cho một vài dependency quan trọng.

Ví dụ:

    Aggregator: tối đa 64 nhiệm vụ outbound đồng thời / instance
       |
       +--> Catalog: tối đa 32 in-flight
       +--> Payment: tối đa 12 in-flight
       '--> Shipping: tối đa 20 in-flight

Đây chỉ là số ví dụ. Các con số cần được chọn theo năng lực downstream, giới hạn kết nối, số replica và số đo thực tế. Không nên đặt tổng giới hạn chỉ bằng phép cộng máy móc nếu mô hình dùng nhiều loại tác vụ và tài nguyên khác nhau.

## 9. Pseudocode của một phép tổng hợp có giới hạn

Ví dụ luồng đọc dữ liệu của một đơn hàng:

    function getSummary(orderId, deadline):
        validateAccess(orderId)

        orderTask    = submitBounded(() => orderClient.get(orderId))
        paymentTask  = submitBounded(() => paymentClient.getByOrder(orderId))
        shipmentTask = submitBounded(() => shippingClient.getByOrder(orderId))

        order   = awaitRequired(orderTask, deadline)
        payment = awaitRequired(paymentTask, deadline)
        ship    = awaitOptional(shipmentTask, deadline)

        return combine(order, payment, ship)

Trong pseudocode này, "submitBounded" phải là cơ chế thực sự giới hạn số tác vụ và hàng đợi, không chỉ tạo mới một thread cho mỗi request. "awaitRequired" và "awaitOptional" dùng **cùng deadline**, đồng thời có quy tắc xử lý lỗi rõ ràng. Nếu một nhánh required thất bại sớm, hệ thống cần cân nhắc hủy/chặn phần công việc không còn ích lợi, nhưng phải hiểu khả năng hủy thực tế của transport.

### 9.1. Ví dụ Java với executor và semaphore

Đoạn mã sau minh họa kỹ thuật giới hạn concurrency. Nó là **khối xây dựng**, không phải một aggregator hoàn chỉnh với Spring wiring, HTTP client, tracing và hợp đồng lỗi:

    import java.util.concurrent.*;
    import java.util.function.Supplier;

    public final class BoundedCalls implements AutoCloseable {
        private final ThreadPoolExecutor workers =
            new ThreadPoolExecutor(
                16, 16, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(64),
                new ThreadPoolExecutor.AbortPolicy()
            );

        private final Semaphore paymentSlots = new Semaphore(12);

        public <T> CompletableFuture<T> paymentCall(Supplier<T> action) {
            // RejectedExecutionException được ném nếu pool và queue đầy.
            return CompletableFuture.supplyAsync(
                () -> withPermit(paymentSlots, action), workers
            );
        }

        private <T> T withPermit(
            Semaphore permits, Supplier<T> action
        ) {
            boolean acquired = false;
            try {
                acquired = permits.tryAcquire(
                    80, TimeUnit.MILLISECONDS
                );
                if (!acquired) {
                    throw new RejectedExecutionException(
                        "Payment bulkhead is full"
                    );
                }
                return action.get();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new CompletionException(e);
            } finally {
                if (acquired) {
                    permits.release();
                }
            }
        }

        @Override
        public void close() {
            workers.shutdown();
        }
    }

Phần đáng chú ý:

- Pool có 16 worker và queue tối đa 64 tác vụ, nên khi bão hòa có thể từ chối thêm việc thay vì tích tụ vô hạn.
- Semaphore cho Payment giới hạn tối đa 12 tác vụ đang giữ permit **trên instance**. Đây không phải giới hạn 12 request/giây.
- "tryAcquire" chờ tối đa 80 ms là ví dụ; thời gian chờ permit phải nằm trong deadline tổng.
- Nếu HTTP client vẫn đang chờ mà một future bên ngoài đã timeout, permit có thể vẫn bị giữ tới khi lời gọi thực sự kết thúc. Vì vậy cần timeout ở HTTP client.
- ThreadPoolExecutor ở ví dụ dùng chung; trong hệ thống thật có thể cần tách pool, dùng bulkhead khác hoặc API bất đồng bộ phù hợp để tránh worker bị giữ lâu khi một downstream chậm.
- Việc đóng executor phải gắn với lifecycle ứng dụng, chẳng hạn bean được hủy khi ứng dụng dừng. Mỗi request **không được tự tạo một thread pool mới**.

Nếu dùng Spring Boot, có thể đóng gói các giới hạn trong những bean sống theo ứng dụng, cấu hình theo môi trường và quan sát metrics của executor/queue/semaphore. Nếu sử dụng reactive non-blocking client, việc giới hạn in-flight request và backpressure vẫn cần thiết; reactive không mặc nhiên giải quyết quá tải.

### 9.2. Điều code minh họa chưa thay thế

Code trên không tự mang lại network timeout, rate limiting, deadline propagation, circuit breaker, retries, xác thực, idempotency hay xử lý partial response. Những cơ chế này thuộc hợp đồng API/client và thiết kế nghiệp vụ cụ thể.

Không sao chép kích thước pool, queue hoặc semaphore từ ví dụ vào production mà không đo workload. Đặc biệt không gọi một phương thức có tác dụng phụ nhiều lần chỉ vì CompletableFuture báo lỗi hoặc timeout.

## 10. Bẫy thường gặp khi dùng CompletableFuture và fan-out

### 10.1. Khởi chạy xong lại chờ ngay từng task

Cách viết sau **trông có CompletableFuture nhưng vẫn tạo chờ nối tiếp** nếu mỗi task mới chỉ được tạo sau khi đợi task trước:

    order = asyncGetOrder().join();
    payment = asyncGetPayment().join();
    shipment = asyncGetShipment().join();

Muốn có song song, các tác vụ độc lập phải được **khởi chạy trước** rồi mới đợi kết quả:

    orderFuture = asyncGetOrder();
    paymentFuture = asyncGetPayment();
    shipmentFuture = asyncGetShipment();

    // Sau khi cả ba đã bắt đầu:
    order = await(orderFuture);
    payment = await(paymentFuture);
    shipment = await(shipmentFuture);

Nhưng cách viết đó vẫn cần deadline và chính sách lỗi để không đợi vô thời hạn.

### 10.2. Gọi allOf rồi coi mọi nhánh là bắt buộc

"CompletableFuture.allOf" cho phép chờ nhiều future, nhưng nếu dùng một chính sách lỗi duy nhất cho mọi nhánh sẽ dễ khiến một widget phụ làm toàn bộ response thất bại. Hãy xác định required và optional trước, xử lý lỗi theo hợp đồng của từng nhánh.

### 10.3. Dùng common pool cho các HTTP call blocking

CompletableFuture.supplyAsync không truyền executor sẽ dùng cơ chế thực thi mặc định. Với nhiều lời gọi I/O đồng bộ có thời gian chờ dài, điều này có thể gây cạnh tranh tài nguyên với những tác vụ không liên quan. Nên kiểm soát executor, concurrency và queue; nếu phù hợp, dùng HTTP client hỗ trợ non-blocking I/O với giới hạn in-flight rõ.

### 10.4. Tạo thread mới cho mọi lời gọi

Mỗi request mở 10 thread, 1.000 request đồng thời thành hàng nghìn thread. Tạo thread hoặc executor tùy tiện gây tăng overhead và làm khó kiểm soát tài nguyên. Thread ảo có thể giảm chi phí thread nền tảng trong một số trường hợp Java hiện đại, nhưng **không làm tăng khả năng chịu tải của downstream** và vẫn phải giới hạn số lời gọi mạng, pool kết nối và hàng đợi.

### 10.5. Giữ permit trong khi chờ một tác vụ không liên quan

Nếu một task chiếm permit rồi chờ một future khác vốn cũng cần permit của cùng nhóm, hệ thống có thể tự khóa hoặc bỏ phí concurrency. Hãy thu hẹp phạm vi giữ permit đúng vào phần công việc sử dụng tài nguyên cần bảo vệ.

### 10.6. Tăng retry khi downstream đang quá tải

Aggregator có thể gọi 5 dependency và retry cả 5 ở nhiều tầng. Nếu downstream đang nghẽn, retry đồng loạt khiến tình trạng tồi tệ hơn. Nên giới hạn retry, backoff với jitter, tôn trọng Retry-After khi phù hợp và ưu tiên giảm tải khi cần.

## 11. Không phải mọi tổng hợp nên giải quyết bằng song song HTTP calls

Trước khi tối ưu số worker, hãy hỏi có cần số lượng remote calls hiện tại không.

### 11.1. Bulk/batch API

Nếu aggregator lấy thông tin 50 sản phẩm, thay vì gọi Catalog 50 lần có thể dùng một bulk endpoint nhận danh sách ID. Phải định nghĩa giới hạn batch, xử lý item không tìm thấy, quyền truy cập và độ mới dữ liệu.

### 11.2. Read model và CQRS projection

Một màn hình dashboard chủ yếu đọc dữ liệu đã kết hợp từ nhiều domain có thể dùng read projection được cập nhật bất đồng bộ. Điều này giảm fan-out trên đường request nhưng tạo yêu cầu quản lý độ trễ đồng bộ, event schema, rebuild, reconciliation và mức chấp nhận dữ liệu cũ.

### 11.3. Cache và snapshot

Tên sản phẩm hoặc thông tin hiển thị ít thay đổi có thể được cache theo chính sách phù hợp. Đơn hàng đã xác nhận có thể lưu snapshot đơn giá tại thời điểm mua, tránh dùng “giá hiện tại” trong Catalog cho lịch sử giao dịch.

Cache không thay thế kiểm tra tính đúng đắn cho các thao tác tiền, giữ hàng hay chuyển trạng thái khi dữ liệu cũ không được phép dùng.

### 11.4. Chuyển việc không cần kết quả ngay ra khỏi đường đồng bộ

Nếu sau khi tạo đơn cần gửi email, cập nhật analytics hoặc chỉ mục tìm kiếm, không nhất thiết giữ response chờ hoàn tất các bước đó. Có thể phát event hoặc tạo job nền khi hợp đồng nghiệp vụ cho phép. Tuy nhiên asynchronous messaging yêu cầu xử lý trùng, retry, ordering, backlog và cơ chế theo dõi riêng.

### 11.5. Điều chỉnh ranh giới service

Nếu hai service luôn gọi nhau để bảo vệ cùng một business invariant, luôn phải đổi và deploy cùng nhau, vấn đề có thể nằm ở ranh giới sở hữu. Gộp hoặc chuyển trách nhiệm đôi khi giảm coupling tốt hơn việc tăng concurrency. Không nên gộp chỉ vì một trace có nhiều lời gọi; cần xét domain và tần suất thay đổi.

## 12. Quan sát, đo lường và kiểm thử

Một aggregator chạy được trên môi trường ít tải chưa chứng minh nó an toàn khi nhiều client gọi đồng thời. Cần quan sát cả trải nghiệm end-to-end và áp lực lên từng dependency.

### 12.1. Metrics nên có

| Nhóm chỉ số | Ví dụ |
| --- | --- |
| Trải nghiệm request | request rate, p50/p95/p99 latency, tỉ lệ lỗi, tỉ lệ partial response |
| Fan-out | số downstream calls/request, số nhánh song song, độ sâu dependency |
| Tài nguyên thực thi | active worker, queue length, queue wait time, rejected tasks |
| Bulkhead | permits đang dùng, thời gian chờ permit, tỉ lệ từ chối |
| HTTP client | active connections, connection wait, connect/read timeout |
| Dependency | latency và error rate theo từng service, retry count |
| Deadline | số request hết deadline, nhánh tiếp tục sau khi caller hết hạn |
| Chất lượng dữ liệu | dữ liệu thiếu, dữ liệu stale, cảnh báo mismatch giữa nguồn |

Distributed tracing cần thể hiện quan hệ giữa các span song song, thời điểm bắt đầu/kết thúc và kết quả của từng dependency. Một trace có thể giúp xác định nhánh chậm nhất, nhưng để điều chỉnh giới hạn cần quan sát nhiều request ở tải thực tế và thời điểm lỗi.

### 12.2. Kịch bản kiểm thử

1. **Tải bình thường:** so sánh latency và số lời gọi của chế độ nối tiếp với giới hạn song song đã chọn.
2. **Tăng tải đột biến:** kiểm tra queue không lớn vô hạn, giới hạn permits hoạt động và có phản hồi từ chối rõ.
3. **Một downstream chậm:** tăng delay Payment nhưng giữ các nhánh khác bình thường; kiểm tra bulkhead ngăn nghẽn lan rộng.
4. **Một downstream không phản hồi:** kiểm tra deadline end-to-end, timeout thực ở client và giải phóng tài nguyên.
5. **Optional branch lỗi:** xem response partial có đúng contract và không biến thiếu dữ liệu thành giá trị nghiệp vụ giả.
6. **Required branch lỗi:** bảo đảm endpoint không trả thành công như thể tất cả dữ liệu quan trọng đã có.
7. **Retry storm:** tiêm lỗi tạm thời để đo request amplification và đảm bảo retry có giới hạn.
8. **Khôi phục:** sau khi downstream trở lại, quan sát queue, latency, tỉ lệ từ chối và trạng thái data có hồi phục không.

Các bài thử nên ghi nhận cấu hình pool, queue, permits, số replica, tải đầu vào và SLO trước khi chạy. Nếu kết quả cải thiện ở một số load profile nhưng tệ hơn ở tải cao, cần thể hiện đánh đổi thay vì chỉ báo một con số trung bình.

## 13. Ví dụ lựa chọn mức đồng thời theo workload

Giả sử một instance aggregator nhận khoảng 100 request/giây. Mỗi request đọc ba nguồn độc lập, mỗi nguồn mất trung bình 100 ms ở tải hiện tại. Một phép ước lượng rất thô:

    Tổng số downstream calls/giây = 100 × 3 = 300
    In-flight trung bình ≈ 300 × 0,1 = 30

Con số 30 chỉ là giá trị trung bình trong điều kiện ổn định và giả định các lời gọi phân phối như ví dụ. Nó không phải kích thước thread pool nên đặt. Ở p99, khi connection pool chờ, hay khi một service có sự cố, số in-flight có thể tăng mạnh.

Khi chọn giới hạn cần cân nhắc:

- Tần suất request đỉnh thay vì chỉ trung bình.
- Độ trễ của từng downstream, nhất là phần đuôi phân bố.
- Tỷ lệ request thực sự cần từng nhánh.
- Số replica của aggregator và downstream.
- Tài nguyên CPU, memory, network, connection pool.
- Mức độ ưu tiên giữa endpoint quan trọng và endpoint ít quan trọng.
- Ngưỡng downstream bắt đầu bị saturation.
- Thời gian chờ tối đa trước khi phản hồi từ chối hoặc partial.

Một quá trình điều chỉnh thực tế có thể bắt đầu bằng giới hạn bảo thủ, đo load test, tăng dần trong vùng an toàn, quan sát tail latency và lỗi rồi lựa chọn mức giới hạn có thể vận hành. **Không tối ưu riêng throughput nếu p99 và khả năng phục hồi xấu đi.**

## 14. Bài tập thực hành

Một endpoint "GET /dashboard" cần kết quả từ năm nguồn:

| Nguồn | Thời gian ở lần đo ví dụ | Có bắt buộc cho màn hình? |
| --- | ---: | --- |
| Account | 70 ms | Có |
| Orders | 160 ms | Có |
| Shipping | 210 ms | Không |
| Recommendation | 350 ms | Không |
| Alerts | 90 ms | Có |

Giả sử các lời gọi độc lập, caller có deadline tổng 500 ms và được phép tối đa **hai remote calls cùng lúc**.

Hãy giải thích:

1. Nếu gọi nối tiếp theo thứ tự bảng, tổng thời gian chờ lý tưởng là bao nhiêu, chưa tính overhead?
2. Với giới hạn hai nhánh song song, bạn sẽ xếp lịch gọi thế nào để các phần bắt buộc nhận được kết quả trước?
3. Nếu Recommendation bị chậm đến 2 giây, nên chờ, trả partial hay bỏ nhánh đó? Cần định nghĩa response thế nào để client nhận biết?
4. Vì sao đặt timeout 500 ms riêng cho cả năm downstream có thể làm request vượt deadline?
5. Nếu 500 request/giây cùng vào endpoint, mỗi request fan-out năm nhánh, cần quan sát giới hạn nào để bảo vệ các downstream?
6. Nếu dashboard cần 50 sản phẩm từ Recommendation, batch API hoặc projection có thể giảm số lời gọi như thế nào?
7. Khi một nhánh required lỗi, những nhánh nào nên tiếp tục chạy và có thể dừng ra sao? Hãy xét khả năng cancellation thực tế của HTTP client.
8. Bạn sẽ ghi lại những metrics và trace nào để so sánh trước/sau?

**Gợi ý:** Tổng thời gian nếu nối tiếp theo các số đo ví dụ là 880 ms. Nhưng khi chỉ có hai slot đồng thời, tổng thời gian không còn đơn giản bằng max của năm nhánh: phải xét lịch cấp slot, thời gian chờ, ưu tiên các nhánh required và deadline. Không nên để nhánh tùy chọn có thời gian dài chiếm hết slot làm chậm thông tin cốt lõi.

## 15. Các lỗi tư duy cần tránh

- **“Cứ song song là nhanh hơn và tốt hơn.”** Có thể tăng concurrency và mức sử dụng tài nguyên tới mức làm downstream quá tải.
- **“Một request không nhiều lời gọi nên an toàn.”** Hàng nghìn request đồng thời có thể khuếch đại lượng outbound rất lớn.
- **“CompletableFuture hoặc async nghĩa là non-blocking.”** Một tác vụ blocking chạy trong thread pool vẫn giữ worker khi chờ I/O.
- **“Đặt timeout cho future là đã hủy HTTP request.”** Underlying task có thể còn chạy; cần timeout/cancellation ở transport.
- **“Semaphores giải quyết hết overload.”** Còn phải giới hạn queue, connection pool, rate, replica, retry và resource toàn hệ thống.
- **“Mọi nhánh lỗi thì trả dữ liệu mặc định.”** Với những trạng thái như thanh toán hoặc tồn kho, dữ liệu giả có thể gây hành động sai.
- **“Mọi dữ liệu luôn phải lấy đồng bộ.”** Batch, cache, projection và async có thể phù hợp hơn khi nghiệp vụ chấp nhận.
- **“Gọi nhiều endpoint thì tăng thread pool.”** Đôi khi gốc rễ là N+1 hoặc service boundary sai.
- **“Mỗi request có deadline riêng cho từng tầng.”** Cần quản lý một ngân sách end-to-end và truyền thời gian còn lại.
- **“Giảm p50 là đủ.”** Tail latency, error rate, saturation và khả năng khôi phục mới cho thấy tác động dưới tải.

## 16. Ghi nhớ

**Tổng hợp yêu cầu** giúp tạo một phản hồi phục vụ đúng use case mà client không phải tự điều phối nhiều dịch vụ. **Thực hiện song song** giảm thời gian chờ khi các bước độc lập; **thực hiện song song có giới hạn** giữ lưu lượng, tài nguyên và mức ảnh hưởng sự cố trong ngưỡng có thể vận hành.

Một thiết kế tốt phải có: ranh giới dữ liệu và trách nhiệm rõ, đồ thị phụ thuộc đúng, deadline end-to-end, phân loại required/optional, giới hạn theo request và downstream, executor/queue/connection pool hữu hạn, chính sách xử lý lỗi minh bạch, quan sát bằng metrics/tracing và kiểm thử ở tải cao. Khi số lời gọi quá nhiều, cần xem lại batch, cache, projection hoặc ranh giới service trước khi tăng thêm concurrency.
