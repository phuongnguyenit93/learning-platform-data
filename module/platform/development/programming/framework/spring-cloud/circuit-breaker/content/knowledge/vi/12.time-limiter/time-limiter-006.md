# Giới hạn interrupt và tác vụ HTTP tiếp tục chạy sau timeout

Timeout giới hạn thời gian caller chờ một thao tác hoàn tất. Tuy nhiên, khi TimeLimiter hết thời gian, điều đó không tự động chứng minh công việc đang chạy đã dừng. Một Future có thể nhận yêu cầu hủy, thread có thể nhận tín hiệu interrupt, HTTP client có thể hủy exchange, nhưng dịch vụ từ xa vẫn có thể tiếp tục xử lý request đã nhận.

Trong Spring Cloud CircuitBreaker với Resilience4j, cần phân biệt ba sự kiện: caller nhận timeout, tác vụ ở phía ứng dụng được yêu cầu hủy và xử lý ở phía server thực sự dừng. Ba sự kiện này có quan hệ với nhau nhưng không đồng nghĩa. Nếu chỉ xử lý timeout ở lớp Circuit Breaker mà không hiểu cơ chế hủy của HTTP client và tác vụ nền, ứng dụng có thể tiếp tục tiêu tốn thread, connection và tài nguyên sau khi đã trả lỗi cho caller.

## 1. Timeout giới hạn thời gian chờ, không phải cam kết dừng công việc

Giả sử dịch vụ đơn hàng gọi dịch vụ tồn kho. Caller đặt timeout hai giây. Dịch vụ tồn kho phản hồi sau tám giây.

Sau hai giây, caller có thể nhận timeout và chuyển sang fallback. Nhưng request đã gửi đi có thể vẫn đang được xử lý ở dịch vụ tồn kho. Nếu phía client đang chạy một tác vụ blocking trên thread pool, tác vụ đó cũng có thể tiếp tục chạy nếu không nhận hoặc không phản hồi tín hiệu hủy.

Có ba lớp cần phân biệt:

| Lớp | Điều xảy ra khi hết timeout | Điều chưa được bảo đảm |
|---|---|---|
| Caller | Ngừng chờ và nhận lỗi timeout hoặc fallback | Công việc phía dưới đã dừng |
| Tác vụ trong ứng dụng | Có thể nhận yêu cầu cancel hoặc interrupt | Code đã phản hồi interrupt và kết thúc |
| HTTP client/server | Client có thể hủy exchange hoặc đóng request | Server đã nhận được tín hiệu hủy và dừng xử lý |

Timeout là giới hạn thời gian ở phía quan sát kết quả. Muốn giải phóng tài nguyên thật sự, cần thiết kế cả tác vụ, HTTP client và server để hỗ trợ hủy.

## 2. TimeLimiter và thuộc tính cancelRunningFuture

Resilience4j TimeLimiter giới hạn thời gian chờ một Future hoặc CompletionStage hoàn thành. Thuộc tính cancelRunningFuture điều khiển việc TimeLimiter có yêu cầu hủy Future đang chạy khi timeout hay không.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Ý nghĩa:

- timeoutDuration đặt giới hạn thời gian chờ là hai giây.
- cancelRunningFuture: true yêu cầu hủy Future khi timeout.
- Nếu đặt false, TimeLimiter không yêu cầu hủy Future đang chạy khi timeout; tác vụ có thể tiếp tục cho đến khi tự hoàn tất hoặc bị hủy ở nơi khác.

Khi dùng Spring Cloud CircuitBreaker với Resilience4j, cấu hình TimeLimiter thường được gắn với ID instance tương ứng. Hãy bảo đảm tên inventory trong code khớp với inventory trong application.yml và xác nhận adapter, kiểu API đang dùng thực sự áp dụng TimeLimiter.

Cấu hình hủy là một yêu cầu gửi đến cơ chế Future, không phải cam kết rằng mọi công việc phía sau sẽ dừng. Kết quả phụ thuộc loại Future, executor, thư viện HTTP và cách tác vụ phản hồi cancellation.

## 3. Future.cancel(true) và ý nghĩa của interrupt

Với một Future thông thường do ExecutorService tạo ra, gọi cancel(true) có thể yêu cầu thread đang thực thi tác vụ nhận tín hiệu interrupt. Nếu tác vụ chưa bắt đầu, nó có thể bị ngăn không cho chạy. Nếu tác vụ đang chạy, việc dừng phụ thuộc vào code và API mà tác vụ đang sử dụng.

Ví dụ một tác vụ có thể phản hồi interrupt:

~~~java
Future<Inventory> future = executor.submit(() -> {
    try {
        return inventoryClient.fetchBlocking("SKU-001");
    } catch (InterruptedException error) {
        Thread.currentThread().interrupt();
        throw error;
    }
});
~~~

Nếu thread thực thi đang chờ trong một thao tác ném InterruptedException, tác vụ có thể dừng và chuyển lỗi lên caller. Việc khôi phục interrupt flag bằng Thread.currentThread().interrupt() giúp giữ lại tín hiệu để các tầng xử lý phía trên nhận biết.

Interrupt trong Java là cơ chế báo hiệu hợp tác. Nó không cưỡng chế JVM kết thúc bất kỳ đoạn code nào. Một tác vụ chỉ dừng đúng lúc khi code chủ động kiểm tra hoặc phản hồi tín hiệu interrupt.

Một số cách code phản hồi interrupt:

- Gọi các API blocking có hợp đồng ném InterruptedException.
- Kiểm tra Thread.currentThread().isInterrupted() tại các điểm an toàn.
- Dừng vòng lặp hoặc công việc tính toán khi phát hiện interrupt.
- Giải phóng tài nguyên trong finally hoặc try-with-resources.
- Không nuốt InterruptedException rồi tiếp tục chạy như bình thường.

Nếu code bắt InterruptedException nhưng không dừng và cũng không khôi phục interrupt flag, yêu cầu hủy có thể bị bỏ qua.

## 4. Vì sao CompletableFuture.cancel(true) không bảo đảm interrupt thread?

Không phải mọi Future đều có cùng hành vi hủy. CompletableFuture có ngữ nghĩa cancellation khác với FutureTask hoặc Future do ExecutorService.submit tạo ra.

Theo hợp đồng của Java CompletableFuture, tham số mayInterruptIfRunning của cancel không được dùng để điều khiển quá trình tính toán. CompletableFuture không nhất thiết sở hữu thread đang thực thi tác vụ, vì vậy cancel(true) chủ yếu hoàn tất CompletableFuture theo trạng thái cancelled và không bảo đảm interrupt thread thực hiện computation.

Ví dụ:

~~~java
CompletableFuture<Inventory> future =
        CompletableFuture.supplyAsync(
                () -> inventoryClient.fetchBlocking("SKU-001"),
                executor
        );

future.cancel(true);
~~~

Lệnh cancel có thể khiến CompletableFuture chuyển sang trạng thái cancelled. Tuy nhiên, tác vụ do supplyAsync đang chạy có thể vẫn tiếp tục trong executor. Không nên xem cancel(true) trên CompletableFuture là cách chắc chắn để ngắt một lời gọi HTTP blocking.

Sự khác biệt:

| Loại tác vụ | Hành vi khi cancel(true) |
|---|---|
| FutureTask đang chạy | Có thể interrupt thread thực thi |
| Future từ ExecutorService | Thường yêu cầu hủy tác vụ và interrupt nếu tác vụ đang chạy |
| CompletableFuture.supplyAsync | Không bảo đảm interrupt computation đang chạy |
| CompletionStage do HTTP client trả về | Phụ thuộc implementation và khả năng truyền cancellation của client |
| Mono/Flux của Reactor | Gửi tín hiệu cancel upstream; tác dụng thực tế phụ thuộc publisher và transport |

Do đó, khi dùng TimeLimiter với CompletionStage, cần xác định CompletionStage đó được tạo bởi thư viện nào và cancellation có truyền đến tác vụ nền hay không. Chỉ nhìn thấy cancelRunningFuture: true trong YAML chưa đủ để kết luận thread HTTP đã dừng.

## 5. Ví dụ dùng TimeLimiter với Future có khả năng interrupt

Với tác vụ blocking được thực thi bằng ExecutorService, có thể dùng TimeLimiter để giới hạn thời gian chờ Future:

~~~java
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

public class InventoryService {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(10);

    private final TimeLimiter timeLimiter = TimeLimiter.of(
            TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .cancelRunningFuture(true)
                    .build()
    );

    private final BlockingInventoryClient inventoryClient;

    public InventoryService(BlockingInventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public Inventory fetch(String sku) throws Exception {
        return timeLimiter.executeFutureSupplier(() ->
                executor.submit(() -> inventoryClient.fetch(sku))
        );
    }
}
~~~

Ví dụ giả định fetch có thể phản hồi interrupt hoặc client có cơ chế hủy phù hợp. Executor nên được quản lý theo vòng đời ứng dụng, chẳng hạn khai báo thành bean và đóng khi ứng dụng shutdown; không tạo một thread pool mới cho từng request.

Nếu fetch đang chờ trong thư viện HTTP không phản hồi interrupt, Future có thể chuyển sang cancelled nhưng thread hoặc hoạt động I/O vẫn chưa kết thúc ngay. Vì vậy, hãy cấu hình timeout ở chính HTTP client và xác nhận hành vi cancellation của thư viện đang dùng.

## 6. Tác vụ HTTP có thể tiếp tục chạy sau timeout như thế nào?

Một HTTP request đi qua nhiều giai đoạn:

~~~mermaid
sequenceDiagram
    participant Caller
    participant TimeLimiter
    participant HttpClient
    participant Server
    Caller->>TimeLimiter: Bắt đầu lời gọi
    TimeLimiter->>HttpClient: Gửi HTTP request
    HttpClient->>Server: Request đến server
    Note over Server: Server bắt đầu xử lý
    TimeLimiter-->>Caller: Timeout sau 2 giây
    Note over Caller: Caller chạy fallback hoặc trả lỗi
    Note over HttpClient,Server: Request có thể vẫn đang được xử lý
    Server-->>HttpClient: Response đến muộn
~~~

Timeout ở caller không nhất thiết thu hồi được request đã gửi qua mạng. Khi server đã nhận request, server có thể tiếp tục:

- Chạy truy vấn cơ sở dữ liệu.
- Gọi thêm dịch vụ phụ thuộc.
- Ghi dữ liệu hoặc cập nhật trạng thái giao dịch.
- Hoàn tất một thao tác nghiệp vụ dù client đã đóng kết nối.

Ngay cả khi HTTP client hủy request hoặc đóng connection, server cũng không bắt buộc phải dừng công việc ngay lập tức. Server có thể chưa phát hiện client disconnect, hoặc logic nghiệp vụ không kiểm tra trạng thái kết nối trong quá trình xử lý.

Vì vậy, một timeout không phải là cơ chế rollback. Nếu request tạo đơn hàng hoặc thực hiện thanh toán đã được server tiếp nhận, caller nhận timeout không có nghĩa thao tác đã thất bại. Retry ngay có thể tạo giao dịch trùng lặp nếu lần đầu đã được xử lý.

## 7. Hủy ở HTTP client và giới hạn của việc ngắt kết nối

Khả năng hủy phụ thuộc HTTP client:

- Một client bất đồng bộ có thể cung cấp handle hoặc Future đại diện cho request và cho phép cancel exchange.
- Một client reactive có thể phản hồi tín hiệu cancel bằng cách giải phóng subscription, hủy exchange hoặc đóng tài nguyên transport.
- Một client blocking có thể không dừng ngay khi thread bị interrupt, tùy API I/O và cấu hình socket.
- Một HTTP request đã đến server có thể vẫn tiếp tục được xử lý dù phía client không còn chờ response.

Với WebClient và Reactor Netty, tín hiệu cancel từ subscriber có thể được truyền xuống publisher của HTTP exchange để hủy hoặc giải phóng hoạt động client. Tuy nhiên, cần kiểm thử với phiên bản Reactor Netty và cấu hình connection pool thực tế. Không nên suy ra rằng server chắc chắn dừng xử lý chỉ vì Mono đã bị cancel.

Có thể đặt timeout ở HTTP client để giới hạn từng giai đoạn:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Trong ví dụ:

- Connect timeout giới hạn thời gian thiết lập kết nối.
- Response timeout của Reactor Netty giới hạn khoảng chờ response theo chính sách của client.
- Timeout tổng thể của request có thể được đặt thêm bằng toán tử timeout trong pipeline.

Các timeout này giải quyết các giai đoạn khác nhau. Hãy kiểm tra tài liệu phiên bản HTTP client để biết chính xác response timeout được đo từ thời điểm nào và có bao gồm thời gian đọc toàn bộ body hay không. Nếu cần giới hạn thời gian đọc body, có thể cần thêm read timeout hoặc deadline ở tầng publisher.

## 8. Kết hợp TimeLimiter, Circuit Breaker và HTTP timeout

Ba cơ chế có vai trò riêng:

- HTTP client timeout giới hạn thời gian chờ ở tầng kết nối hoặc response.
- TimeLimiter giới hạn thời gian caller chờ Future hoặc CompletionStage.
- Circuit Breaker quan sát kết quả và ngăn lời gọi mới khi dependency có dấu hiệu mất ổn định.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
~~~

Ở đây, TimeLimiter giới hạn lời gọi tổng thể ở ba giây. HTTP client có thể có connect timeout một giây và response timeout hai giây. Circuit Breaker ghi nhận timeout hoặc lỗi tương ứng nếu chúng đi qua publisher/Future được bảo vệ và không bị cấu hình bỏ qua.

Cần thiết kế deadline theo thứ tự hợp lý. Nếu HTTP client có thể chờ lâu hơn TimeLimiter, TimeLimiter có thể kết thúc trước trong khi I/O vẫn còn chạy. Nếu HTTP timeout ngắn hơn TimeLimiter, client có cơ hội tự kết thúc hoạt động và giải phóng connection trước khi caller hết deadline tổng thể.

Một ví dụ với Spring Cloud CircuitBreaker và CompletionStage:

~~~java
import java.util.concurrent.CompletionStage;

import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

public class InventoryClient {

    private final CircuitBreaker inventoryBreaker;
    private final AsyncInventoryHttpClient httpClient;

    public InventoryClient(
            CircuitBreakerFactory<?, ?> factory,
            AsyncInventoryHttpClient httpClient) {
        this.inventoryBreaker = factory.create("inventory");
        this.httpClient = httpClient;
    }

    public CompletionStage<Inventory> find(String sku) {
        return inventoryBreaker.run(
                () -> httpClient.fetch(sku),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

Cấu hình TimeLimiter cho instance inventory có thể được áp dụng bởi Resilience4j adapter theo phiên bản và cách tạo breaker. Cần xác nhận adapter có bọc CompletionStage bằng TimeLimiter và việc cancel được truyền đến HTTP client hay không. Nếu HTTP client trả CompletableFuture, cancel Future không mặc nhiên interrupt thread hoặc hủy exchange; hãy kiểm tra API cancellation của chính client.

## 9. Deadline tổng thể và tránh retry làm nhân đôi công việc

Timeout từng lần gọi không đồng nghĩa deadline tổng thể của nghiệp vụ. Giả sử:

- Mỗi lần gọi HTTP có timeout hai giây.
- Retry cho phép thêm một lần thử.
- Khoảng chờ giữa hai lần thử là 200 mili giây.
- Fallback cần thêm 100 mili giây.

Tổng thời gian có thể vượt bốn giây. Nếu request phía trên chỉ cho phép ba giây, caller có thể timeout trước khi chuỗi retry hoàn tất.

Ngoài thời gian, retry còn có thể làm server tiếp tục thực hiện nhiều request cũ. Ví dụ lần đầu client timeout nhưng server vẫn tạo đơn hàng; retry gửi cùng yêu cầu lần hai có thể tạo thêm một đơn hàng khác.

Với thao tác có side effect, nên:

- Dùng idempotency key ổn định cho cùng một nghiệp vụ.
- Lưu trạng thái request hoặc transaction để caller có thể tra cứu kết quả sau timeout.
- Thiết kế API server hỗ trợ nhận biết yêu cầu trùng lặp.
- Giới hạn số lần retry và deadline tổng thể.
- Không retry mù quáng khi chưa biết request trước đã được server xử lý hay chưa.

Timeout chỉ nói rằng caller không nhận được kết quả trong thời hạn. Nó không chứng minh server chưa thực hiện nghiệp vụ.

## 10. Cách thiết kế tác vụ để phản hồi interrupt

Nếu ứng dụng tự quản lý tác vụ blocking, code nên phản hồi interrupt một cách có chủ đích.

Ví dụ vòng lặp kiểm tra tín hiệu:

~~~java
public Inventory fetchWithPolling(String sku) throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Inventory inventory = tryFetch(sku);

        if (inventory != null) {
            return inventory;
        }

        Thread.sleep(100);
    }

    throw new InterruptedException("Inventory lookup interrupted");
}
~~~

Khi thread nhận interrupt trong Thread.sleep, phương thức ném InterruptedException. Tác vụ có thể kết thúc và giải phóng tài nguyên. Nếu phương thức bắt exception ở một tầng rồi không thể ném tiếp, nên khôi phục interrupt flag:

~~~java
try {
    performBlockingOperation();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    cleanup();
    return;
}
~~~

Không nên dùng vòng lặp bận để liên tục kiểm tra interrupt. Hãy dùng API blocking có khả năng interrupt hoặc cơ chế chờ phù hợp. Với thao tác HTTP, ưu tiên API client có cancellation rõ ràng và timeout ở transport thay vì chỉ dựa vào interrupt của thread.

## 11. Quan sát công việc còn chạy sau timeout

Để biết timeout có thật sự giải phóng tài nguyên, cần theo dõi cả caller lẫn tác vụ nền:

- Số timeout được trả về cho caller.
- Số Future được yêu cầu cancel.
- Số tác vụ thực sự kết thúc sau khi nhận cancellation.
- Số thread đang hoạt động trong executor và hàng đợi chờ.
- Số connection đang được sử dụng và số connection bị pending.
- Thời gian từ lúc timeout đến lúc tác vụ nền kết thúc.
- Số request server tiếp tục xử lý sau khi client đã ngắt kết nối.
- Tỷ lệ request bị retry và tỷ lệ thao tác trùng lặp được phát hiện.

Có thể thêm log theo correlation ID và operation ID ở cả client và server. Khi caller timeout, ghi nhận thời điểm và ID. Khi server kết thúc xử lý, ghi cùng ID. Hai mốc thời gian giúp xác định công việc có tiếp tục chạy sau timeout hay không.

Không nên chỉ nhìn metric timeout của TimeLimiter rồi kết luận tài nguyên đã được giải phóng. Cần so sánh với active task, thread pool, connection pool và log phía server.

## 12. Kiểm thử hành vi cancellation

Một bài kiểm thử tốt nên tạo một endpoint giả lập xử lý lâu hơn timeout. Ví dụ, endpoint chờ năm giây trong khi client timeout sau hai giây.

Kiểm tra các điểm sau:

1. Caller nhận timeout hoặc fallback sau khoảng thời gian đã cấu hình.
2. Future có nhận yêu cầu cancel hay không.
3. Thread thực thi có nhận interrupt hay không.
4. Tác vụ blocking có kết thúc sớm hay vẫn chạy đến hết.
5. HTTP client có đóng hoặc hủy exchange không.
6. Server có nhận biết client disconnect và dừng xử lý không.
7. Executor và connection pool có trở về trạng thái bình thường sau tải thử nghiệm không.
8. Retry có gây ra request trùng lặp hoặc side effect trùng lặp không.

Nên chạy thử với cả FutureTask và CompletableFuture để thấy sự khác biệt của cancellation. Với HTTP client, kiểm thử trên đúng implementation và phiên bản production đang sử dụng; hành vi của mock hoặc client khác có thể không đại diện cho transport thực tế.

## 13. Những lỗi thường gặp

- **Cho rằng timeout đồng nghĩa tác vụ đã dừng**: timeout chỉ kết thúc thời gian chờ của caller.
- **Cho rằng cancel(true) luôn interrupt thread**: CompletableFuture không bảo đảm interrupt computation.
- **Nuốt InterruptedException**: tác vụ có thể tiếp tục chạy dù đã nhận tín hiệu hủy.
- **Chỉ đặt TimeLimiter mà không đặt timeout HTTP**: thao tác I/O có thể tiếp tục chiếm tài nguyên sau khi caller đã timeout.
- **Cho rằng đóng kết nối làm server rollback**: server có thể đã thực hiện side effect trước khi client ngắt kết nối.
- **Retry ngay sau timeout mà không có idempotency**: có thể tạo giao dịch trùng lặp.
- **Tạo executor mới cho từng request**: thread pool tăng không kiểm soát và khó giải phóng.
- **Không theo dõi tác vụ nền**: dashboard chỉ hiển thị caller timeout nhưng không cho biết worker còn hoạt động.
- **Dùng một timeout cho mọi tầng**: connect, response, read và deadline tổng thể có mục tiêu khác nhau.
- **Tin rằng mọi HTTP client hỗ trợ cancellation giống nhau**: phải kiểm tra hợp đồng và hành vi của client thực tế.

## 14. Quy trình cấu hình và triển khai

Khi dùng TimeLimiter để bảo vệ lời gọi HTTP trong Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự:

1. Xác định deadline tổng thể mà caller có thể chấp nhận.
2. Đặt connect timeout, response timeout và read timeout phù hợp cho HTTP client.
3. Cấu hình timeoutDuration cho TimeLimiter theo deadline còn lại của lời gọi.
4. Đặt cancelRunningFuture: true nếu muốn yêu cầu hủy Future khi timeout.
5. Xác định loại Future hoặc CompletionStage mà HTTP client trả về và kiểm tra cancellation có được truyền xuống transport hay không.
6. Nếu dùng blocking task, bảo đảm code phản hồi interrupt và giải phóng tài nguyên.
7. Với reactive publisher, kiểm tra tín hiệu cancel có được truyền đến HTTP exchange và giới hạn của server khi client disconnect.
8. Thiết kế idempotency và trạng thái tra cứu cho các thao tác có side effect.
9. Theo dõi số tác vụ còn chạy sau timeout, active thread, connection pool và thời gian kết thúc thực tế.
10. Kiểm thử timeout, cancellation, fallback và retry trong điều kiện dependency phản hồi chậm.

TimeLimiter giúp giới hạn thời gian caller chờ kết quả và có thể yêu cầu hủy Future thông qua cancelRunningFuture. Interrupt là tín hiệu hợp tác; CompletableFuture không bảo đảm interrupt computation; HTTP client có thể hủy exchange nhưng server vẫn có thể tiếp tục xử lý request đã nhận. Khi phối hợp timeout ở TimeLimiter, timeout ở HTTP client, cancellation có thể kiểm chứng và idempotency ở server, ứng dụng giảm được công việc tồn đọng và hạn chế tác động của dependency chậm sau khi caller đã hết thời gian chờ.
