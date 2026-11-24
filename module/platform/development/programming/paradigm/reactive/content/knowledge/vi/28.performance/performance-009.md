# So sánh mô hình phản ứng, luồng nền tảng và luồng ảo có cùng tải

Khi một dịch vụ phải xử lý nhiều thao tác đồng thời, ba cách tổ chức thực thi thường được đem ra so sánh: mô hình reactive dựa trên Publisher và luồng sự kiện, mô hình blocking dùng platform thread, và mô hình blocking dùng virtual thread. Cả ba có thể phục vụ cùng một API và nghiệp vụ, nhưng cách chúng sử dụng thread, bộ nhớ, hàng đợi và tài nguyên I/O khác nhau. Muốn chọn đúng, cần so sánh chúng dưới cùng một tải và đo cả độ trễ lẫn chi phí tài nguyên.

Bài học thuộc chương **Hiệu năng** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này đặt mô hình reactive cạnh platform thread và virtual thread, chỉ ra điều kiện để benchmark công bằng và cách diễn giải kết quả theo loại tải.

## Ba cách tổ chức thực thi

Trước khi so sánh, cần phân biệt mô hình lập trình với loại thread. Reactive là cách mô hình hóa dữ liệu, sự kiện, demand và kết quả bất đồng bộ. Nó không phải một loại thread. Một ứng dụng Reactor có thể dùng event loop chạy trên platform thread, dùng Scheduler với pool platform thread, hoặc tích hợp một số tác vụ trên virtual thread. Ngược lại, virtual thread là một loại `Thread` trong JVM và thường được dùng để viết mã blocking theo phong cách tuần tự.

| Mô hình | Cách xử lý một thao tác I/O | Đơn vị thực thi thường thấy | Điểm cần quản lý |
|---|---|---|---|
| Blocking với platform thread | Thread gọi bị giữ trong lúc chờ I/O | Một platform thread cho mỗi request đang xử lý, thường qua pool có giới hạn | Kích thước pool, hàng đợi, thời gian chờ và context switch |
| Blocking với virtual thread | Virtual thread có thể nhường carrier khi chờ ở API hỗ trợ | Một virtual thread cho mỗi tác vụ hoặc request | Giới hạn tài nguyên downstream, pinning, số tác vụ và vòng đời |
| Reactive với I/O non-blocking | Pipeline đăng ký I/O rồi tiếp tục khi có tín hiệu, không giữ thread chỉ để chờ | Event loop hoặc Scheduler dùng ít thread hơn số thao tác đang chờ | Backpressure, demand, queue, scheduler boundary và cancellation |

Platform thread là thread do hệ điều hành lập lịch. Nó có stack và chi phí quản lý lớn hơn virtual thread. Trong mô hình thread-per-request, một request đang chờ database hoặc HTTP thường giữ một platform thread trong suốt thời gian chờ.

Virtual thread là thread nhẹ do JVM quản lý và được ánh xạ lên các platform thread gọi là carrier. Với các thao tác blocking được JDK hỗ trợ, virtual thread có thể tạm nhường carrier trong lúc chờ; carrier đó có thể chạy virtual thread khác. Nhờ vậy, mã blocking tuần tự có thể phục vụ nhiều tác vụ chờ I/O mà không cần tạo một platform thread cho mỗi tác vụ.

Reactive pipeline thường đăng ký thao tác I/O non-blocking và xử lý tín hiệu khi kết quả sẵn sàng. Một event loop có thể phục vụ nhiều connection vì nó không bị giữ trong lúc chờ socket. Publisher và Subscriber phối hợp demand qua Reactive Streams khi nguồn hỗ trợ giao thức này.

## Không so sánh sai khái niệm

Ba cách tổ chức không phải ba lựa chọn loại trừ tuyệt đối:

- Reactive mô tả cách biểu diễn và kết hợp luồng dữ liệu bất đồng bộ.
- Platform thread và virtual thread mô tả đơn vị thực thi trong JVM.
- Một ứng dụng reactive vẫn có thể gọi thư viện blocking trên pool platform thread hoặc trên virtual thread.
- Một ứng dụng dùng virtual thread vẫn có thể phát sự kiện, dùng `CompletionStage` hoặc tích hợp Publisher.

Do đó, benchmark cần mô tả chính xác cấu hình. Ví dụ, WebFlux không tự động có nghĩa toàn bộ stack non-blocking: nếu controller gọi JDBC trực tiếp, event loop vẫn có thể bị chặn. Tương tự, virtual thread không làm JDBC trở thành non-blocking; nó chỉ giúp việc chờ blocking ít chiếm carrier hơn nếu driver và JVM có thể unmount virtual thread trong tình huống đó.

Khi so sánh kiến trúc đầu cuối, hãy ghi rõ:

1. Server framework và cách dispatch request.
2. Client HTTP, driver database và các API thực sự blocking hay non-blocking.
3. Scheduler, executor và giới hạn concurrency.
4. Kích thước connection pool, giới hạn database và các dependency dùng chung.
5. Phiên bản JDK, framework, driver và cấu hình JVM.

## Platform thread: pool có giới hạn và hàng đợi

Mô hình blocking truyền thống thường dùng thread pool. Một request chiếm một platform thread trong lúc chạy controller, gọi dịch vụ và chờ I/O. Pool có giới hạn giúp kiểm soát số thread hoạt động, nhưng nếu mọi thread đều đang chờ I/O, request mới phải đợi trong hàng đợi hoặc bị từ chối.

Ví dụ một executor với số worker và hàng đợi có giới hạn:

~~~java
ThreadPoolExecutor requestExecutor = new ThreadPoolExecutor(
    32,
    32,
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(500),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Pool có 32 worker và hàng đợi tối đa 500 tác vụ. Khi cả worker lẫn hàng đợi đều đầy, `AbortPolicy` từ chối tác vụ. Đây là một dạng admission control ở tầng executor. Ứng dụng cần chuyển việc từ chối thành phản hồi phù hợp, chẳng hạn HTTP 503, thay vì để hàng đợi tăng vô hạn.

Ưu điểm của mô hình này là dễ hiểu, dễ tích hợp với thư viện blocking và có thể đặt giới hạn tài nguyên rõ ràng. Nhược điểm là mỗi thao tác đang chờ vẫn giữ một platform thread. Tăng pool quá mức có thể làm tăng stack memory, context switch và cạnh tranh CPU. Giảm pool quá mức có thể làm request chờ lâu dù database vẫn còn năng lực.

## Virtual thread: giữ phong cách blocking với chi phí thread thấp hơn

Java 21 chuẩn hóa virtual thread. Có thể tạo một virtual thread cho mỗi tác vụ bằng:

~~~java
try (ExecutorService executor =
         Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Customer> customer = executor.submit(
        () -> blockingCustomerClient.findById(customerId)
    );

    Customer result = customer.get();
}
~~~

Mỗi tác vụ được chạy trên một virtual thread. Khi `findById` chờ ở API blocking tương thích, JVM có thể unmount virtual thread khỏi carrier để carrier thực hiện công việc khác. Mã ứng dụng vẫn tuần tự và có thể dùng `try/catch`, `try-with-resources` cùng thư viện blocking quen thuộc.

Không nên tạo pool để tái sử dụng virtual thread như cách làm với platform thread. Mô hình thường dùng là tạo virtual thread cho từng tác vụ; JVM quản lý và tái sử dụng carrier. Khi cần giới hạn số thao tác truy cập một dependency, dùng semaphore, bulkhead, connection pool hoặc giới hạn concurrency ở tầng nghiệp vụ.

Ví dụ, nếu dịch vụ chỉ cho phép tối đa 40 lời gọi blocking đồng thời, có thể dùng semaphore làm bulkhead:

~~~java
private final Semaphore permits = new Semaphore(40);

Customer findCustomer(String id) throws InterruptedException {
    permits.acquire();
    try {
        return blockingClient.findCustomer(id);
    } finally {
        permits.release();
    }
}
~~~

Virtual thread có thể chờ ở `acquire()` mà không cần giữ carrier như một platform thread bị chặn trong mọi tình huống tương thích. Semaphore giới hạn số lời gọi đang đi vào dependency; nó không giới hạn số virtual thread đã được tạo. Nếu không muốn tạo quá nhiều tác vụ chờ permit, cần thêm admission control ở tầng nhận request.

Virtual thread làm giảm chi phí chờ thread, nhưng không tạo thêm năng lực cho database, dịch vụ HTTP hoặc CPU. Nếu 10.000 virtual thread cùng đợi một connection pool chỉ có 50 connection, phần lớn vẫn phải chờ connection. Nếu chúng cùng chạy phép tính CPU nặng, số virtual thread lớn không làm CPU xử lý nhanh hơn số core.

Một số điểm cần chú ý:

- Không giữ monitor hoặc thực hiện native/foreign call theo cách khiến virtual thread bị pin carrier trong lúc chờ. Hành vi pinning phụ thuộc phiên bản JDK; trên JDK 21–23, blocking khi đang giữ monitor `synchronized` có thể pin carrier. JDK 24 cải thiện đáng kể tình huống pinning do monitor theo JEP 491, nhưng native/foreign call và các trường hợp khác vẫn cần kiểm tra theo phiên bản.
- ThreadLocal hoạt động với virtual thread, nhưng tạo nhiều virtual thread cùng các giá trị ThreadLocal lớn có thể tăng bộ nhớ. Với dữ liệu ngữ cảnh theo tác vụ, hãy cân nhắc vòng đời và kích thước dữ liệu.
- Không dùng số lượng virtual thread như giới hạn concurrency cho dependency. Dùng giới hạn tài nguyên tường minh.
- Hủy tác vụ hoặc interrupt không đảm bảo mọi thư viện blocking dừng ngay. Khả năng hủy vẫn phụ thuộc API và driver.

## Reactive: nhiều thao tác đang chờ trên ít thread

Trong mô hình reactive, một request có thể được biểu diễn thành `Mono` hoặc `Flux`. Với client và driver non-blocking, pipeline đăng ký I/O rồi tiếp tục khi có tín hiệu. Thread event loop không phải ngồi chờ response cho từng request.

Ví dụ với WebClient:

~~~java
Mono<CustomerView> customer =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .map(CustomerView::from);
~~~

Publisher mô tả thao tác; I/O được thực thi khi có subscription. Nếu client thực sự non-blocking, thread không bị giữ chỉ để chờ response. Nếu downstream gọi thêm một API blocking, phần đó cần được cô lập:

~~~java
Mono<CustomerView> customer =
    Mono.fromCallable(() -> legacyClient.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .map(CustomerView::from);
~~~

Ví dụ thứ hai vẫn là thao tác blocking. `boundedElastic` cô lập nó khỏi event loop nhưng worker vẫn bị giữ trong lúc thư viện chờ. Vì vậy, benchmark reactive cần phân biệt stack non-blocking hoàn toàn với reactive pipeline có adapter blocking.

Reactive Streams bổ sung cơ chế demand cho Publisher và Subscriber. Với nguồn tuân thủ backpressure, downstream có thể yêu cầu từng lô phần tử và giảm tốc độ phát. Điều này hữu ích với luồng dữ liệu, nhưng không thay thế giới hạn concurrency, giới hạn buffer hoặc admission control ở những nguồn không thể điều tiết.

## Dự đoán hiệu năng theo loại tải

Không có mô hình thắng trong mọi tình huống. Kết quả phụ thuộc tỷ lệ thời gian chờ I/O so với thời gian CPU, số thao tác đồng thời, driver và cách giới hạn tài nguyên.

| Loại tải | Platform thread | Virtual thread | Reactive |
|---|---|---|---|
| I/O blocking, concurrency vừa phải | Đơn giản, nhưng thread bị giữ khi chờ | Thường phục vụ nhiều tác vụ chờ với ít carrier hơn | Có thể hiệu quả nếu I/O non-blocking; adapter blocking vẫn giữ worker |
| I/O blocking, concurrency rất cao | Có thể cần nhiều thread và bộ nhớ | Thường phù hợp với mã blocking có nhiều lần chờ | Phù hợp nếu toàn bộ đường I/O hỗ trợ non-blocking và backpressure |
| CPU-bound | Cần pool gần số core hữu ích | Không tăng năng lực CPU; nhiều virtual thread có thể tranh CPU | Scheduler CPU-bound cũng cần giới hạn theo số core |
| Luồng dữ liệu lớn | Cần queue và xử lý batch | Có thể dùng blocking iterator, nhưng vẫn phải giới hạn buffer | Demand/backpressure giúp điều tiết nếu nguồn hỗ trợ |
| Thư viện cũ chỉ có API blocking | Tích hợp tự nhiên | Tích hợp tự nhiên, giảm chi phí thread chờ | Cần cô lập trên Scheduler blocking |
| Cần composition, cancellation và stream processing | Có thể cần tự quản lý callback hoặc queue | Có thể dùng API blocking/structured concurrency | Có sẵn operator cho ghép luồng, lỗi, demand và cancellation |

Với workload chủ yếu chờ I/O, virtual thread có thể mang lại mô hình đơn giản với khả năng đồng thời cao. Reactive có thể đạt hiệu quả tốt khi stack I/O thực sự non-blocking, có luồng dữ liệu cần backpressure hoặc cần kết hợp nhiều nguồn bất đồng bộ. Với CPU-bound, cả ba mô hình đều bị giới hạn bởi số core và hiệu quả thuật toán; thay thread model không thay thế tối ưu hóa phép tính.

## Thiết kế benchmark công bằng

Một benchmark có ích phải giữ nguyên nghiệp vụ và các điều kiện bên ngoài. Nếu một phiên bản dùng connection pool 200 còn phiên bản khác dùng pool 20, kết quả không còn phản ánh riêng mô hình thực thi. Tương tự, nếu một bên trả kết quả đã cache còn bên kia truy vấn database, throughput không thể so sánh trực tiếp.

Hãy thiết lập cùng một workload:

1. Cùng endpoint, dữ liệu đầu vào, payload và logic nghiệp vụ.
2. Cùng database, dịch vụ phụ thuộc, mạng và connection pool.
3. Cùng timeout, retry, deadline, giới hạn request và chính sách lỗi.
4. Cùng tài nguyên máy: CPU, RAM, container limit và JVM heap.
5. Cùng phiên bản JDK hoặc ghi rõ khác biệt phiên bản khi benchmark tính năng phụ thuộc JDK.
6. Cùng thời gian warm-up, thời gian đo và số lần lặp.
7. Cùng công cụ tạo tải và vị trí chạy load generator.

Tách ít nhất hai loại thử nghiệm:

- **I/O-bound:** mỗi request chờ một hoặc nhiều dịch vụ bên ngoài, với thời gian phản hồi và tỷ lệ lỗi được kiểm soát. Dùng để đánh giá khả năng giữ nhiều thao tác chờ.
- **CPU-bound:** mỗi request thực hiện lượng tính toán xác định, không phụ thuộc network. Dùng để thấy giới hạn CPU, scheduler và chi phí phối hợp.

Nên thử cả tải ổn định lẫn burst. Một hệ thống có throughput tốt ở tải ổn định vẫn có thể thất bại khi request đến dồn dập. Hãy quan sát thời gian hàng đợi tăng, hành vi từ chối và tốc độ hồi phục sau burst.

### Closed-loop và open-loop load

Load generator closed-loop chỉ gửi request mới khi request trước hoàn tất hoặc khi slot client được giải phóng. Cách này phù hợp để đo throughput tại mức concurrency cố định, nhưng khi server chậm, tốc độ gửi cũng tự giảm.

Load generator open-loop phát request theo tốc độ đến đã định trước, độc lập với thời gian hoàn tất của request trước. Cách này hữu ích để kiểm tra SLA dưới một arrival rate cụ thể và phát hiện queue growth khi hệ thống không theo kịp. Công cụ phải ghi nhận latency đúng cách để tránh coordinated omission, tức bỏ qua khoảng thời gian mà client không gửi request mới chỉ vì đang chờ request cũ.

Ghi rõ loại load model trong báo cáo. Không so sánh throughput closed-loop của một mô hình với latency open-loop của mô hình khác.

## Chỉ số cần đo

Requests per second là một chỉ số, không phải toàn bộ kết luận. Cần đo đồng thời:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Thông lượng | Throughput, số tác vụ hoàn tất/giây | Năng lực xử lý ở mức tải đã thử |
| Độ trễ | p50, p95, p99, max | Trải nghiệm điển hình và tail latency |
| Lỗi | Error rate, timeout, reject, retry | Chất lượng xử lý khi tải tăng |
| Thread | Platform thread count, virtual thread count, carrier utilization | Chi phí và mức sử dụng môi trường thực thi |
| CPU | CPU utilization, thời gian CPU mỗi request | Khả năng tận dụng core và chi phí điều phối |
| Bộ nhớ | Heap, live set, allocation rate, GC pause | Chi phí giữ request, queue và object |
| Hàng đợi | Queue depth, queue age, pending task | Tình trạng backlog và độ trễ chờ |
| I/O | Connection pool active/pending, socket, database latency | Nút thắt ở dependency |

Đặc biệt chú ý p99. Một hệ thống có p50 tốt nhưng p99 tăng mạnh có thể đang gặp queueing, pool exhaustion, GC hoặc một số request chờ dependency quá lâu. Throughput cao trong khi error rate tăng không phải là cải thiện.

## Ví dụ tổ chức cùng một tác vụ I/O

Giả sử một thao tác đọc hồ sơ từ client đồng bộ. Có thể viết phiên bản platform thread dùng executor giới hạn:

~~~java
ExecutorService platformPool =
    Executors.newFixedThreadPool(32);

Future<Customer> platformResult =
    platformPool.submit(() ->
        blockingClient.findCustomer(customerId));
~~~

Phiên bản virtual thread:

~~~java
ExecutorService virtualExecutor =
    Executors.newVirtualThreadPerTaskExecutor();

Future<Customer> virtualResult =
    virtualExecutor.submit(() ->
        blockingClient.findCustomer(customerId));
~~~

Phiên bản reactive cần client non-blocking:

~~~java
Mono<Customer> reactiveResult =
    reactiveClient.findCustomer(customerId);
~~~

Ba đoạn mã chỉ minh họa cách dispatch cùng một thao tác; chúng chưa phải benchmark hoàn chỉnh. Khi đo, phải submit cùng số request, dùng cùng server và dữ liệu, áp dụng cùng giới hạn dependency, chờ kết quả và thu thập metric. Nếu dùng blocking client trong phiên bản reactive:

~~~java
Mono<Customer> reactiveAdapter =
    Mono.fromCallable(() ->
            blockingClient.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Hãy báo cáo nó là reactive adapter trên blocking I/O. Không gộp kết quả này với phiên bản dùng reactive client native.

Đoạn mã platform pool và virtual executor chỉ minh họa cách dispatch. Trong ứng dụng thật, cần quản lý vòng đời executor, xử lý rejection hoặc interruption và bảo đảm mọi phiên bản áp dụng cùng giới hạn số thao tác đồng thời vào dependency. Không so sánh một phiên bản có queue/reject với một phiên bản nhận vô hạn tác vụ mà không ghi rõ chính sách admission khác nhau.

Trong cả ba phiên bản, nếu database chỉ cho phép 40 connection đồng thời, hãy giới hạn concurrency hoặc cấu hình pool theo cùng một giá trị. Virtual thread có thể tạo nhiều tác vụ chờ connection; reactive pipeline cũng có thể tạo nhiều subscription chờ connection. Không có mô hình nào làm giới hạn database biến mất.

## Diễn giải kết quả và chọn mô hình

Một báo cáo benchmark tốt cần trả lời câu hỏi “mô hình nào phù hợp với workload và giới hạn này?” thay vì chỉ xếp hạng một con số.

- Nếu platform thread đạt throughput mục tiêu và p99 ổn định với pool nhỏ, sự đơn giản của nó có thể là đủ.
- Nếu workload chủ yếu blocking I/O và cần nhiều tác vụ đồng thời, virtual thread có thể giảm chi phí quản lý thread mà không buộc phải chuyển toàn bộ code sang reactive.
- Nếu pipeline cần stream processing, demand, composition nhiều nguồn, cancellation và driver non-blocking, reactive có thể đem lại lợi ích về khả năng điều tiết và sử dụng thread.
- Nếu reactive stack chứa JDBC hoặc SDK blocking, cần đo riêng phần worker bị giữ và giới hạn `boundedElastic`; đừng suy luận rằng API trả `Mono` đã loại bỏ blocking.
- Nếu CPU là nút thắt, hãy tối ưu thuật toán, batch, dữ liệu và số core trước khi thay thread model.

Ngoài hiệu năng, hãy cân nhắc độ phức tạp vận hành, khả năng debug, thư viện hiện có, kỹ năng nhóm, transaction model và yêu cầu tương thích. Một lựa chọn tốt là lựa chọn đáp ứng SLA và giới hạn tài nguyên với chi phí vận hành chấp nhận được.

## Những lỗi thường gặp khi benchmark

| Cách làm | Vì sao kết quả sai lệch | Cách khắc phục |
|---|---|---|
| Dùng dữ liệu hoặc dependency khác nhau | Đo cả khác biệt của database/cache/network | Dùng cùng dependency và trạng thái dữ liệu |
| So sánh reactive dùng JDBC với reactive driver non-blocking mà không ghi rõ | Hai cấu hình có hành vi I/O khác nhau | Gắn nhãn native non-blocking và blocking adapter |
| Tăng virtual thread vô hạn rồi kết luận hệ thống mở rộng vô hạn | Database, pool, CPU và bộ nhớ vẫn hữu hạn | Đặt concurrency cap và đo queue/pool |
| Chỉ báo cáo requests/second | Bỏ qua p99, lỗi và độ trễ hàng đợi | Báo cáo throughput, latency percentiles và error rate |
| Chỉ chạy tải ổn định | Không thấy phản ứng khi burst hoặc overload | Thử steady-state, ramp-up và burst |
| So sánh open-loop với closed-loop | Arrival rate và latency measurement không tương đương | Dùng cùng load model và ghi rõ cấu hình |
| Bỏ qua warm-up và JIT | Đo một phiên bản ở trạng thái chưa ổn định | Warm-up đủ và lặp nhiều lần |
| Dùng `Thread.sleep` làm đại diện duy nhất cho I/O | Không mô phỏng connection pool, socket, driver và cancellation | Dùng dependency thử nghiệm gần với hành vi thật |
| Không theo dõi queue và pool | Không biết nút thắt nằm ở executor hay dependency | Thu thập queue depth, pool pending và worker utilization |

## Nguyên tắc lựa chọn

Trước khi quyết định giữa reactive, platform thread và virtual thread, hãy xác định:

1. Workload chủ yếu chờ I/O hay tiêu thụ CPU?
2. Driver và thư viện có API non-blocking thực sự không?
3. Số thao tác đồng thời và giới hạn connection pool là bao nhiêu?
4. Có cần backpressure và stream processing xuyên suốt các tầng không?
5. Hàng đợi, concurrency, timeout và cancellation được kiểm soát ở đâu?
6. Benchmark có cùng tải, dependency, tài nguyên, load model và thời gian warm-up không?
7. Kết quả có bao gồm p95/p99, lỗi, CPU, bộ nhớ, thread và queue không?
8. Độ phức tạp triển khai và vận hành của từng phương án có phù hợp với nhóm không?

Reactive, platform thread và virtual thread giải quyết các khía cạnh khác nhau của bài toán đồng thời. Platform thread phù hợp với mô hình blocking có pool được kiểm soát; virtual thread giúp giữ phong cách blocking khi có nhiều thao tác chờ; reactive phối hợp luồng sự kiện và demand hiệu quả khi các nguồn I/O hỗ trợ non-blocking. Chỉ benchmark cùng tải, cùng giới hạn tài nguyên và đo cả tail latency lẫn chi phí vận hành mới cho thấy lựa chọn nào phù hợp với dịch vụ thực tế.
