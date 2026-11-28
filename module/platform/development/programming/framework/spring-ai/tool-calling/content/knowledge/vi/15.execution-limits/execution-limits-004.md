# Đặt thời hạn cho công cụ và cho toàn bộ yêu cầu

Một tool có thể gọi database, HTTP API, hệ thống tìm kiếm hoặc một dịch vụ nội bộ. Nếu dịch vụ phụ thuộc phản hồi chậm, một lần gọi tool có thể chiếm tài nguyên lâu hơn dự kiến. Một hội thoại còn có thể gọi model nhiều lần: model đề xuất tool, ứng dụng thực thi, gửi kết quả về model rồi tiếp tục vòng lặp. Vì vậy, timeout cho một tool và deadline cho toàn bộ yêu cầu là hai giới hạn khác nhau.

Timeout của tool giới hạn thời gian một thao tác cụ thể được phép chờ. Deadline toàn request giới hạn tổng thời gian từ lúc ứng dụng nhận yêu cầu đến khi hoàn tất câu trả lời, bao gồm các lần gọi model, tool, retry và thời gian chờ giữa các bước. Muốn hệ thống phản hồi đúng hạn, ứng dụng cần kết hợp cả hai, truyền phần thời gian còn lại đến từng bước và xử lý việc hủy công việc khi hết hạn.

## Sau bài học, bạn có thể

- Phân biệt connect timeout, response timeout, timeout của tool, timeout của một lần gọi model và deadline toàn request.
- Đặt timeout tại HTTP client hoặc dịch vụ mà tool sử dụng.
- Truyền deadline theo từng request qua `ToolContext`.
- Tính timeout hiệu lực bằng giá trị nhỏ hơn giữa giới hạn riêng của tool và thời gian còn lại của request.
- Kiểm tra deadline trước mỗi vòng model và trước khi thực thi tool.
- Hiểu giới hạn của cancellation, retry và timeout ở tầng HTTP.
- Kiểm thử timeout của tool, deadline toàn request và hành vi khi request đồng thời.

## Phân biệt các loại thời hạn

Các thuật ngữ timeout thường bị dùng thay thế cho nhau, nhưng chúng giới hạn các giai đoạn khác nhau.

| Loại giới hạn | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Connection timeout | Thời gian thiết lập kết nối tới máy chủ | Kết nối HTTP phải hoàn tất trong 1 giây |
| Connection-pool acquire timeout | Thời gian chờ lấy connection từ pool | Không chờ quá 500 ms để lấy connection |
| Response/read timeout | Thời gian chờ phản hồi hoặc dữ liệu theo chính sách của client | API đối tác phải bắt đầu/tiếp tục phản hồi trong giới hạn |
| Tool timeout | Thời gian tối đa cho một lần thực thi callback | Tool tra cứu đơn hàng tối đa 3 giây |
| Model request timeout | Thời gian tối đa cho một HTTP request tới model provider | Một lần gọi chat model tối đa 8 giây |
| Request deadline | Tổng thời gian cho toàn bộ yêu cầu của người dùng | Từ lúc nhận request đến lúc trả lời tối đa 20 giây |

Connection timeout không giới hạn thời gian đọc response. Response timeout cũng không nhất thiết là deadline tổng của toàn bộ nghiệp vụ. Tùy HTTP client, response timeout có thể giới hạn thời gian chờ phản hồi hoặc khoảng im lặng giữa các lần đọc dữ liệu.

Một tool gọi nhiều dịch vụ nối tiếp có thể tiêu thụ nhiều timeout nhỏ. Nếu mỗi dịch vụ có timeout 3 giây và tool gọi ba dịch vụ tuần tự, tổng thời gian có thể gần 9 giây. Do đó, ngoài timeout cho từng dependency, cần có một giới hạn cho toàn bộ callback.

## Timeout của tool nằm ở đâu?

Spring AI gọi logic của tool thông qua `ToolCallback`. Với method `@Tool`, callback gọi method đã được đánh dấu. Với `FunctionToolCallback`, callback gọi function hoặc method reference đã đăng ký.

Annotation `@Tool` không tự đặt một timeout phổ quát cho mọi thao tác bên trong method. Thời hạn thực thi cần được đặt ở nơi thực hiện I/O hoặc ở wrapper điều phối callback:

- HTTP client đặt connect, pool-acquire và response/request timeout.
- Database driver hoặc transaction layer đặt query/statement timeout.
- Dịch vụ nghiệp vụ kiểm tra deadline trước khi bắt đầu công việc và trước các bước tiếp theo.
- Wrapper có thể giới hạn một tác vụ blocking cũ bằng executor, nhưng phải hiểu cách cancellation của tác vụ đó hoạt động.

Ví dụ, một tool tra cứu thông tin vận chuyển gọi HTTP API. Nếu dùng JDK `HttpClient`, có thể đặt connect timeout ở client và request timeout cho từng request:

~~~java
@Bean
HttpClient shippingHttpClient() {
    return HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(1))
            .build();
}
~~~

Khi gửi request:

~~~java
HttpRequest request = HttpRequest.newBuilder(shippingUri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response = shippingHttpClient.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

Trong ví dụ này, connect timeout giới hạn thời gian thiết lập kết nối; `HttpRequest.timeout` giới hạn thời gian của request HTTP. Đây là timeout ở tầng transport. Nếu tool còn thực hiện xử lý dữ liệu sau khi nhận response, cần tính phần xử lý đó trong timeout của callback hoặc deadline toàn request.

Nếu dùng Reactor Netty, có thể cấu hình các timeout ở tầng HTTP client, ví dụ:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(3));
~~~

Các timeout của connection pool, kết nối, TLS và response có mục đích riêng. Hãy chọn theo loại dịch vụ và client đang sử dụng. Không dùng một giá trị response timeout để thay thế mọi giới hạn khác.

## Đặt timeout cho một lần gọi model

Mỗi lần model phản hồi trong tool-calling loop là một request riêng tới provider. Trong Spring AI, timeout và retry thường được cấu hình theo model provider vì mỗi integration có HTTP client và property riêng.

Ví dụ với OpenAI chat model:

~~~yaml
spring:
  ai:
    openai:
      timeout: 8s
      max-retries: 1
~~~

Tên property và khả năng cấu hình có thể khác giữa provider hoặc phiên bản starter. Hãy kiểm tra trang cấu hình của model provider đang dùng. Không giả định rằng `spring.ai.openai.timeout` áp dụng cho Anthropic, Azure OpenAI hoặc mọi `ChatModel`.

Timeout này giới hạn một request của model provider. Nếu tool-calling loop gọi model ba lần, mỗi lần có thể tiêu thụ gần hết timeout riêng. Vì vậy, timeout 8 giây cho một lần gọi model không có nghĩa toàn bộ hội thoại sẽ hoàn thành trong 8 giây.

Retry ở client model cũng tiêu thụ thời gian. Nếu một lần thử có timeout 8 giây và client được phép retry, tổng thời gian chờ có thể dài hơn đáng kể. Hãy tính cả số lần retry và backoff trong deadline toàn request.

## Deadline toàn request

Deadline toàn request là mốc thời gian tuyệt đối mà mọi bước của yêu cầu phải tôn trọng. Nó nên được tạo ở ranh giới nhận request, trước khi gọi model hoặc dịch vụ nghiệp vụ.

Một yêu cầu có thể gồm:

1. Xác thực và chuẩn bị ngữ cảnh.
2. Lần gọi model đầu tiên.
3. Một hoặc nhiều lần thực thi tool.
4. Các lần gọi model tiếp theo để diễn giải kết quả.
5. Retry có giới hạn và backoff.
6. Chuyển đổi kết quả và trả response.

Nếu chỉ đặt timeout cho từng bước mà không chia sẻ deadline, mỗi bước có thể dùng hết timeout riêng và làm tổng thời gian vượt xa SLA.

Ví dụ ngân sách tổng là 20 giây:

| Giai đoạn | Giới hạn riêng | Thời gian đã dùng minh họa |
|---|---:|---:|
| Model lần đầu | Tối đa 8 giây | 4 giây |
| Tool tra cứu | Tối đa 4 giây | 2 giây |
| Model sau tool | Tối đa 8 giây | 5 giây |
| Dự phòng xử lý và trả response | Phần còn lại | 9 giây còn lại trước khi tính bước cuối |

Các con số trên chỉ minh họa. Trong thực tế, không cấp sẵn toàn bộ 8 giây cho mỗi bước nếu request chỉ còn 3 giây. Mỗi bước phải dùng thời gian còn lại làm giới hạn trên.

## Biểu diễn deadline trong Java

Trong một process, dùng `System.nanoTime()` để đo thời gian trôi qua. Đây là đồng hồ đơn điệu, phù hợp để tính deadline và không bị thay đổi khi đồng hồ hệ thống được chỉnh lại.

Có thể tạo một object nhỏ để giữ deadline:

~~~java
public record RequestBudget(long deadlineNanos) {

    public static RequestBudget start(Duration totalBudget) {
        if (totalBudget.isZero() || totalBudget.isNegative()) {
            throw new IllegalArgumentException("totalBudget phải lớn hơn 0");
        }

        return new RequestBudget(
                System.nanoTime() + totalBudget.toNanos()
        );
    }

    public Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();

        if (nanos <= 0) {
            throw new RequestDeadlineExceededException();
        }

        return Duration.ofNanos(nanos);
    }

    public Duration timeoutFor(Duration operationLimit) {
        Duration left = remaining();

        return left.compareTo(operationLimit) < 0
                ? left
                : operationLimit;
    }

    public void requireRemaining() {
        remaining();
    }
}
~~~

`RequestDeadlineExceededException` là exception của ứng dụng, dùng để báo request đã hết ngân sách thời gian. Có thể bổ sung constructor và mã lỗi phù hợp với quy ước của dự án.

Phương thức `timeoutFor` luôn trả về giá trị nhỏ hơn giữa giới hạn của thao tác và thời gian còn lại của request. Ví dụ tool được phép chạy tối đa 4 giây nhưng request chỉ còn 900 ms, tool chỉ được cấp 900 ms.

Không truyền trực tiếp giá trị `deadlineNanos` sang process khác. `System.nanoTime()` chỉ có ý nghĩa trong JVM/process hiện tại. Khi gọi dịch vụ khác, hãy truyền thời gian còn lại dưới dạng duration hoặc deadline theo giao thức đã thống nhất, ví dụ header timeout nội bộ hoặc metadata gRPC.

## Truyền deadline vào ToolContext

Khi tạo request, ứng dụng tạo một `RequestBudget` mới và truyền nó vào context. Có thể dùng cùng object cho advisor context và tool context:

~~~java
RequestBudget budget = RequestBudget.start(Duration.ofSeconds(20));

String answer = chatClient.prompt()
        .user(question)
        .tools(orderTools)
        .toolContext(Map.of(
                "requestBudget", budget,
                "requestId", requestId
        ))
        .advisors(advisors -> advisors.param("requestBudget", budget))
        .call()
        .content();
~~~

Trong ví dụ này:

- `toolContext(...)` truyền budget đến callback khi tool được thực thi.
- `advisors(...)` đặt budget vào context của advisor chain để advisor tùy chỉnh có thể kiểm tra trước mỗi lần gọi model.
- Mỗi request tạo một `RequestBudget` riêng, không dùng một biến deadline mutable dùng chung cho tất cả người dùng.

Context này là dữ liệu nội bộ của ứng dụng. Không đưa deadline, user ID hoặc tenant ID vào JSON Schema để yêu cầu model tạo. Model không cần biết deadline nội bộ; callback và advisor đọc nó từ context.

## Áp dụng deadline bên trong tool

Method `@Tool` nhận `ToolContext`, lấy budget và tính timeout hiệu lực trước khi gọi dịch vụ:

~~~java
@Component
public class ShippingTools {

    private final ShippingService shippingService;

    public ShippingTools(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    @Tool(description = "Tra cứu trạng thái vận chuyển theo mã đơn hàng")
    public ShippingStatus getShippingStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        RequestBudget budget = (RequestBudget) toolContext
                .getContext()
                .get("requestBudget");

        Duration timeout = budget.timeoutFor(Duration.ofSeconds(4));

        return shippingService.getStatus(orderId, timeout);
    }
}
~~~

Dịch vụ phải sử dụng timeout được truyền vào khi gọi dependency:

~~~java
public ShippingStatus getStatus(String orderId, Duration timeout) {
    HttpRequest request = HttpRequest.newBuilder(
                    URI.create(baseUrl + "/orders/" + orderId + "/shipping"))
            .timeout(timeout)
            .GET()
            .build();

    try {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        return parseStatus(response.body());
    }
    catch (HttpTimeoutException ex) {
        throw new ToolExecutionTimeoutException("Shipping service timed out", ex);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new ToolExecutionInterruptedException(ex);
    }
    catch (IOException ex) {
        throw new ShippingServiceException(ex);
    }
}
~~~

Đây là ví dụ rút gọn; ứng dụng cần kiểm tra HTTP status, xác thực response và ánh xạ lỗi theo hợp đồng dịch vụ. Điểm quan trọng là timeout hiệu lực được truyền đến HTTP request, thay vì chỉ kiểm tra thời gian trước khi bắt đầu rồi để I/O chờ vô hạn.

Với tool dùng nhiều dependency nối tiếp, hãy tính lại `budget.timeoutFor(...)` trước từng dependency. Không tái sử dụng timeout đã tính ở đầu method vì thời gian còn lại giảm trong khi tool đang chạy.

## Kiểm tra deadline trước mỗi vòng model

Trong Spring AI 2.x, `ToolCallingAdvisor` quản lý vòng gọi model và thực thi tool. Advisor cung cấp hook `doBeforeCall` trước mỗi lần gọi model và `doBeforeStream` cho luồng streaming. Có thể dùng custom subclass để kiểm tra request budget trước khi bắt đầu iteration mới. Builder của advisor không thay thế deadline end-to-end; ngân sách tổng vẫn do ứng dụng quản lý và phối hợp với timeout của từng client.

Ví dụ phần hook cho đường blocking:

~~~java
@Override
protected ChatClientRequest doBeforeCall(
        ChatClientRequest request,
        CallAdvisorChain chain) {

    RequestBudget budget = (RequestBudget) request.context()
            .get("requestBudget");

    if (budget != null) {
        budget.requireRemaining();
    }

    return request;
}
~~~

Với streaming, cần triển khai hook tương ứng:

~~~java
@Override
protected ChatClientRequest doBeforeStream(
        ChatClientRequest request,
        StreamAdvisorChain chain) {

    RequestBudget budget = (RequestBudget) request.context()
            .get("requestBudget");

    if (budget != null) {
        budget.requireRemaining();
    }

    return request;
}
~~~

Đây là các hook của custom `ToolCallingAdvisor`; phần khởi tạo subclass và đăng ký advisor cần theo đúng cấu hình advisor của ứng dụng. `DefaultChatClient` chỉ nên có một `ToolAdvisor` chịu trách nhiệm cho tool lifecycle. Nếu dùng custom subclass, nó thay thế advisor mặc định trong chain.

Kiểm tra ở `doBeforeCall` ngăn bắt đầu một model iteration mới khi deadline đã hết. Nó không tự hủy một model request hoặc tool đang chạy. Vì vậy vẫn phải cấu hình timeout tại HTTP client của model và client của tool.

## Kết hợp giới hạn từng tool và deadline tổng

Một request có thể gọi nhiều tool trong cùng một vòng hoặc qua nhiều vòng. Mỗi callback cần giới hạn riêng, nhưng tất cả callback phải dùng chung budget của request.

Ví dụ:

| Công cụ | Giới hạn riêng | Thời gian request còn lại khi bắt đầu | Timeout hiệu lực |
|---|---:|---:|---:|
| Tra cứu khách hàng | 3 giây | 12 giây | 3 giây |
| Tra cứu vận chuyển | 4 giây | 6 giây | 4 giây |
| Tính phí hoàn tiền | 5 giây | 1 giây | 1 giây |

Tool thứ ba chỉ còn 1 giây vì các bước trước đã tiêu thụ ngân sách. Nếu deadline hết trước khi tool bắt đầu, callback phải dừng ngay thay vì tạo một request mới với timeout đầy đủ.

Nếu một response có nhiều tool call, deadline tổng vẫn bao trùm toàn bộ nhóm call. Khi thực thi tuần tự, thời gian của từng call cộng dồn; khi thực thi song song, request chỉ hoàn tất khi các call cần thiết đã kết thúc hoặc bị hủy. Hãy đo hành vi của cấu hình thực tế và không giả định tổng thời gian bằng timeout của một tool.

## Timeout, cancellation và công việc vẫn tiếp tục

Timeout và cancellation liên quan nhưng không đồng nghĩa:

- **Timeout** xác định rằng thời gian chờ đã vượt giới hạn và ứng dụng không tiếp tục chờ kết quả theo chính sách.
- **Cancellation** gửi tín hiệu yêu cầu dừng công việc đang chạy.
- **Ngắt luồng (interrupt)** là một tín hiệu trong Java; tác vụ phải hợp tác kiểm tra hoặc thư viện I/O phải phản ứng với nó.

Một timeout ở tầng controller hoặc gateway có thể trả lỗi cho người dùng trong khi thread phía sau vẫn đang gọi model hoặc tool. Tương tự, hoàn tất một `CompletableFuture` bằng `orTimeout(...)` không bảo đảm tác vụ I/O gốc đã dừng. `CompletableFuture.cancel(...)` cũng không dùng interrupt để điều khiển công việc bên dưới.

Nếu cần bọc một tác vụ blocking bằng `Future`, `cancel(true)` chỉ yêu cầu interrupt; code và thư viện được gọi phải hỗ trợ cancellation. Không tạo một thread mới cho mỗi tool call. Dùng executor có giới hạn số thread và queue, theo dõi tác vụ bị timeout nhưng chưa dừng, và ưu tiên timeout gốc của HTTP/database client.

Với reactive client, cancellation khi dispose subscription có thể hủy thao tác I/O ở client nếu transport hỗ trợ. Tuy nhiên, server từ xa có thể vẫn tiếp tục xử lý sau khi client đóng kết nối. Không xem việc client ngừng chờ là bằng chứng nghiệp vụ phía server chưa thực hiện hành động.

## Timeout khi tool thực hiện thao tác ghi

Nếu tool tạo đơn hàng, hoàn tiền, gửi email hoặc thay đổi dữ liệu, timeout có thể xảy ra sau khi server đã commit thay đổi nhưng trước khi client nhận response. Ứng dụng không biết chắc thao tác đã thành công hay chưa.

Trong trường hợp đó:

- Dùng idempotency key hoặc mã yêu cầu duy nhất để tránh thực hiện trùng khi retry.
- Trước khi gửi lại, kiểm tra trạng thái thao tác bằng mã yêu cầu nếu dịch vụ hỗ trợ.
- Phân biệt timeout trước khi gửi request với timeout sau khi gửi request.
- Ghi nhận trạng thái `UNKNOWN` hoặc `PENDING_RECONCILIATION` nếu chưa xác định được kết quả.
- Yêu cầu xác nhận hoặc đối soát trước khi lặp lại một hành động không thể đảo ngược.

Timeout không phải rollback. Nếu cần bảo đảm tính nguyên tử giữa nhiều dịch vụ, hãy dùng workflow, saga hoặc cơ chế bù trừ phù hợp thay vì kỳ vọng timeout tự hoàn tác mọi tác động.

## Retry phải dùng chung ngân sách

Retry có thể khắc phục lỗi mạng tạm thời, nhưng mỗi lần thử và khoảng backoff đều tiêu thụ deadline. Một retry policy không biết thời gian còn lại có thể tiếp tục thử sau khi người dùng đã hết thời gian chờ.

Quy tắc nên áp dụng:

1. Chỉ retry lỗi có khả năng tạm thời, chẳng hạn một số lỗi kết nối hoặc phản hồi 5xx.
2. Không retry lỗi validation, lỗi phân quyền hoặc yêu cầu không hợp lệ.
3. Chỉ retry thao tác ghi khi có idempotency hoặc cơ chế xác định trạng thái trước đó.
4. Trước mỗi lần thử, tính lại thời gian còn lại.
5. Chỉ retry nếu còn đủ thời gian cho backoff và một lần thực thi có ý nghĩa.
6. Giới hạn số lần thử và dùng exponential backoff có jitter.
7. Tính cả retry của provider model và retry của ứng dụng vào cùng ngân sách.

Không nên cấu hình nhiều lớp retry độc lập mà không tính tổng số lần thử. Ví dụ, ba lần retry ở HTTP client bên trong hai lần retry của service có thể tạo ra nhiều request hơn dự kiến.

## Deadline tổng trong ChatClient và streaming

`ToolCallingAdvisor` tự động lặp cho đến khi model trả response không còn tool call. Timeout của một lần gọi model không giới hạn toàn bộ vòng lặp. Một request có thể gọi model nhiều lần, do đó cần deadline dùng chung và kiểm tra ở từng iteration.

Với `ChatClient.call()`, ứng dụng thường chạy theo đường blocking. Timeout ở HTTP server hoặc proxy có thể ngừng chờ từ phía client, nhưng không tự bảo đảm các thao tác blocking bên trong đã dừng. Hãy kết hợp deadline trong advisor, timeout của provider và timeout của từng tool.

Với `ChatClient.stream()`, cần phân biệt:

- **Idle timeout:** không có chunk mới trong một khoảng thời gian.
- **Absolute deadline:** tổng thời gian kể từ lúc request bắt đầu, kể cả khi stream liên tục phát chunk.

Một toán tử timeout trên `Flux` có thể được dùng để phát hiện khoảng im lặng giữa các tín hiệu; nó không thay thế deadline tuyệt đối nếu stream vẫn liên tục phát dữ liệu. Dùng deadline timer/cancellation ở tầng request để kết thúc toàn bộ stream khi hết ngân sách.

Nếu ứng dụng tự điều khiển vòng lặp bằng `ChatModel` và `ToolCallingManager`, có thể kiểm tra deadline trước từng lần gọi model và từng lần thực thi callback. Cách này cho quyền kiểm soát rõ ràng nhưng ứng dụng phải tự quản lý lịch sử hội thoại, lỗi, observability và cancellation.

## Xử lý lỗi timeout

Nên phân loại timeout theo nơi xảy ra để trả lỗi và quan sát đúng:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Hết thời gian kết nối | Không kết nối được host | Có thể retry giới hạn nếu lỗi tạm thời |
| Hết thời gian response của tool | API đối tác phản hồi chậm | Dừng tool, ghi nhận dependency và thời gian |
| Tool vượt deadline request | Request chỉ còn ít thời gian | Không bắt đầu hoặc không tiếp tục dependency mới |
| Model request timeout | Provider không trả lời kịp | Áp dụng retry theo provider và phần budget còn lại |
| Request deadline exceeded | Tổng thời gian đã hết | Dừng vòng lặp và trả lỗi timeout ở tầng API |
| Cancellation | Người dùng đóng kết nối hoặc hủy request | Truyền tín hiệu hủy xuống các tác vụ có hỗ trợ |

Không trả stack trace, URL nội bộ, token hoặc thông tin cấu hình cho model/người dùng. Có thể trả mã lỗi ổn định như `TOOL_TIMEOUT` hoặc `REQUEST_DEADLINE_EXCEEDED` cùng thông báo an toàn. Nếu muốn model giải thích lỗi tool, chỉ đưa thông điệp đã làm sạch và tránh yêu cầu model retry vô hạn.

## Quan sát thời gian thực thi

Để tìm ra bước nào làm request chậm, ghi nhận thời gian theo từng giai đoạn:

- Tổng thời gian request và deadline còn lại.
- Thời gian từng lần gọi model.
- Thời gian từng tool callback theo tên tool.
- Thời gian connect, chờ connection pool và chờ response của dependency.
- Số lần retry, thời gian backoff và nguyên nhân retry.
- Số vòng tool calling và số tool call trong mỗi vòng.
- Số tác vụ đã timeout nhưng vẫn còn chạy nếu có thể quan sát.

Dùng request ID hoặc trace ID để liên kết các span. Không ghi toàn bộ tool arguments, dữ liệu khách hàng hoặc context nhạy cảm chỉ để đo thời gian. Các metric như `tool.execution.duration`, `tool.timeout.count` và `request.deadline.remaining` giúp so sánh theo tool/provider mà không cần lưu payload.

## Kiểm thử timeout và deadline

Không cần gọi model thật để kiểm tra logic tính deadline. Hãy kiểm thử riêng budget object, tool service, advisor hook và toàn bộ request.

Các trường hợp quan trọng:

- Tool hoàn tất trước timeout riêng.
- Tool chậm hơn timeout riêng và bị client timeout.
- Request chỉ còn ít thời gian hơn giới hạn riêng của tool.
- Deadline đã hết trước khi tool bắt đầu.
- Nhiều tool hoặc nhiều vòng model tiêu thụ chung một deadline, không reset ngân sách.
- Retry chỉ xảy ra khi còn đủ thời gian.
- Người dùng hủy request và cancellation được truyền đến thao tác có hỗ trợ.
- Hai request đồng thời có budget riêng, không ảnh hưởng lẫn nhau.
- Thao tác ghi timeout sau khi server có thể đã commit được xử lý bằng idempotency/đối soát.

Ví dụ kiểm thử phép tính timeout hiệu lực:

~~~java
@Test
void toolTimeoutMustNotExceedRemainingRequestBudget() {
    RequestBudget budget = RequestBudget.start(Duration.ofMillis(500));

    Duration effective = budget.timeoutFor(Duration.ofSeconds(3));

    assertThat(effective).isLessThanOrEqualTo(Duration.ofMillis(500));
}
~~~

Với test timeout I/O, dùng mock server có thể trì hoãn response hoặc ngắt kết nối có kiểm soát. Xác minh exception đúng loại, thời gian hoàn tất nằm trong biên cho phép và không có retry vượt ngân sách.

Với integration test tool loop, dùng model giả trả về một hoặc nhiều tool call. Kiểm tra advisor không bắt đầu iteration mới sau deadline, tool không bắt đầu khi ngân sách đã hết và kết quả cuối phản ánh timeout đúng cách.

## Những lỗi thường gặp

- **Chỉ đặt timeout cho HTTP client của tool:** một tool loop nhiều vòng vẫn có thể kéo dài hơn thời hạn người dùng mong đợi. Dùng deadline tổng.
- **Dùng timeout mỗi bước như deadline tổng:** mỗi bước có thể tiêu thụ hết timeout riêng và làm tổng thời gian tăng theo số bước.
- **Reset deadline sau mỗi tool:** ngân sách sẽ kéo dài vô hạn theo số iteration. Tạo budget một lần ở ranh giới request.
- **Chỉ timeout ở controller hoặc gateway:** caller nhận lỗi nhưng công việc bên trong có thể tiếp tục. Kết hợp cancellation và timeout ở transport.
- **Tin `CompletableFuture.orTimeout()` sẽ dừng I/O:** nó giới hạn việc chờ future, không bảo đảm tác vụ gốc đã dừng.
- **Dùng `Future.cancel(true)` như rollback:** interrupt là yêu cầu hợp tác, không hoàn tác tác động đã commit.
- **Retry mọi timeout:** thao tác ghi có thể đã thành công ở server. Dùng idempotency và kiểm tra trạng thái.
- **Truyền `System.nanoTime()` sang dịch vụ khác:** giá trị này chỉ có ý nghĩa trong process hiện tại. Truyền remaining duration hoặc deadline theo giao thức.
- **Dùng idle timeout cho streaming như deadline tổng:** stream phát chunk liên tục có thể chạy lâu hơn giới hạn mong muốn. Đặt absolute deadline riêng.
- **Dùng một deadline mutable singleton:** request đồng thời có thể ghi đè thời hạn của nhau. Tạo budget riêng cho từng request.

## Checklist trước khi phát hành

- [ ] Có connection timeout và response/request timeout phù hợp cho từng dependency.
- [ ] Có timeout riêng cho mỗi loại tool.
- [ ] Model provider có timeout và retry được cấu hình theo đúng integration.
- [ ] Deadline tổng được tạo ở đầu request và không bị reset giữa các iteration.
- [ ] Thời gian còn lại được truyền đến tool qua context.
- [ ] Custom advisor hoặc orchestrator kiểm tra deadline trước mỗi model iteration.
- [ ] Mỗi tool tính timeout hiệu lực từ giới hạn riêng và thời gian còn lại.
- [ ] Retry có giới hạn và dùng chung deadline.
- [ ] Thao tác ghi có idempotency hoặc cơ chế đối soát.
- [ ] Cancellation và tác vụ blocking được kiểm tra trong môi trường thật.
- [ ] Có metric cho thời gian tool, model, retry và tổng request.
- [ ] Có test cho timeout, deadline, retry, cancellation và request đồng thời.

## Ghi nhớ khi thiết kế

Timeout của tool giới hạn một lần thực thi callback hoặc một dependency. Timeout của model giới hạn một request tới provider. Deadline toàn request bao trùm tất cả lần gọi model, tool, retry và xử lý còn lại. Mỗi bước phải dùng thời gian còn lại của cùng một deadline, thay vì bắt đầu một đồng hồ mới.

Hãy đặt timeout ở tầng HTTP/database thực hiện I/O, truyền một budget riêng theo request qua advisor context và `ToolContext`, kiểm tra trước mỗi iteration và mỗi tool, rồi kết hợp cancellation phù hợp. Timeout chỉ dừng việc chờ theo giới hạn; nó không tự rollback thao tác đã commit. Với thao tác ghi, luôn có idempotency hoặc đối soát trước khi retry.

## Tài liệu tham khảo

- [Spring AI — Tool Calling Loop](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — ToolCallingAdvisor và hook methods](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI — OpenAI Chat Configuration](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Java SE — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE — Future.cancel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

