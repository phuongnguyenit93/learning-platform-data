# Timeout kết nối, timeout phản hồi và giới hạn hủy phía nhận

## 1. Bối cảnh: một lời gọi đồng bộ có nhiều loại thời gian chờ

Trong kiến trúc microservices, một yêu cầu có thể đi theo chuỗi:

    Người dùng -> Gateway -> Order -> Inventory
                                  -> Payment -> Nhà cung cấp thanh toán

Mỗi chặng đều có thể bị chậm khi chờ kết nối, chờ tài nguyên, chờ service xử lý hoặc chờ dữ liệu được gửi về. Nếu các lời gọi không có thời hạn chờ, một service chậm có thể giữ thread, connection và bộ nhớ ở các service phía trước, dẫn đến lỗi dây chuyền. Nếu timeout quá ngắn, hệ thống có thể tạo thất bại giả và những lần thử lại không an toàn.

**Timeout là giới hạn thời gian chờ của bên quan sát, không phải bằng chứng rằng nghiệp vụ phía nhận đã bị hủy hay đã thất bại.** Khi một lệnh thu tiền hết thời gian chờ, nhà cung cấp thanh toán có thể đã thu thành công nhưng phản hồi chưa về tới caller.

Bài này tập trung vào ba loại quyết định:

- **Timeout kết nối:** Khi nào client ngừng cố thiết lập kết nối mới?
- **Timeout phản hồi:** Client chờ kết quả từ service nhận trong bao lâu, tính từ mốc nào và có bao gồm body không?
- **Giới hạn hủy phía nhận:** Khi caller ngừng chờ hoặc gửi tín hiệu cancel, phần việc nào ở receiver thực sự ngừng được, phần nào có thể vẫn tiếp tục hoặc đã commit?

Sau bài, bạn có thể lập bản đồ thời gian của một request, dùng deadline từ đầu đến cuối, cấu hình các timeout riêng theo từng giai đoạn, xử lý retry và kết quả chưa xác định, và thiết kế cơ chế hủy có trách nhiệm ở phía service nhận.

## 2. Một request HTTP đi qua những giai đoạn nào?

Một request đồng bộ thông thường có thể có các giai đoạn sau:

    (A) Chờ lấy connection từ pool
           |
    (B) Phân giải DNS / chọn địa chỉ
           |
    (C) Thiết lập TCP connection
           |
    (D) TLS handshake nếu HTTPS
           |
    (E) Gửi HTTP headers và request body
           |
    (F) Server xếp hàng / điều phối / xử lý
           |
    (G) Client nhận response headers
           |
    (H) Client đọc response body
           |
    (I) Client giải mã và xử lý kết quả

Đây là mô hình tư duy, không phải một chuỗi bất biến ở mọi giao thức. HTTP/2 có thể ghép nhiều stream trên một connection; DNS có cache; client có thể tái sử dụng connection cũ; HTTP proxy hoặc service mesh bổ sung giai đoạn riêng.

Nhầm lẫn phổ biến là coi timeout cho giai đoạn C cũng bao phủ A, B, D, E, F, G và H. Nó thường không làm được điều đó.

### 2.1. Thời gian chờ lấy connection từ pool

Khi tất cả connection trong pool đang được dùng, request có thể nằm trong hàng đợi trước khi tạo kết nối mới hoặc sử dụng kết nối sẵn có.

Một số thư viện dùng tên connection request timeout, pending acquire timeout hoặc pool acquisition timeout. Nó khác **connect timeout**. Nếu chỉ giới hạn TCP connect, caller vẫn có thể kẹt lâu ở pool.

Các chỉ số nên theo dõi: active connections, idle connections, pending requests, acquire latency và số lần acquire timeout.

### 2.2. DNS timeout

Client cần phân giải hostname thành địa chỉ. Hành vi này có thể do hệ điều hành, resolver riêng hoặc thư viện mạng thực hiện. Không nên mặc định connect timeout đã bao gồm toàn bộ DNS lookup. Để quản trị thời gian chờ toàn lời gọi, cần thêm ngân sách tổng thể phù hợp và hiểu cách resolver của stack đang dùng hoạt động.

### 2.3. TCP connection timeout

Giới hạn thời gian thiết lập một TCP connection mới tới endpoint hoặc proxy. Với kết nối đã được tái sử dụng, request mới có thể không phải trải qua TCP connect. Vì vậy connect timeout không phải tổng thời gian chờ request.

Nếu có proxy, load balancer hoặc nhiều địa chỉ IP, một kết nối thất bại cũng không đủ để suy ra hệ ứng dụng cuối cùng đã xử lý hay chưa; cần xem cơ chế tự thử địa chỉ và gửi lại của client.

### 2.4. TLS handshake timeout

HTTPS thường cần bắt tay TLS sau khi TCP kết nối thành công. Thư viện có thể có giới hạn handshake riêng. Connect timeout 300 ms không nhất thiết buộc toàn bộ quá trình TLS hoàn thành trong 300 ms.

### 2.5. Timeout ghi request

Gửi request body lớn, tải file lên hoặc kết nối mạng chậm có thể khiến client bị treo ở bước ghi. Một write timeout hoặc tổng deadline có thể cần thiết. Nếu upload bị ngắt giữa chừng, receiver có thể đã nhận một phần dữ liệu; hợp đồng phải nêu cách xử lý nội dung chưa đầy đủ và yêu cầu có thể gửi lại.

### 2.6. Timeout phản hồi hoặc đọc dữ liệu

Tên gọi này **khác nhau theo thư viện**:
- Có API đếm thời gian từ lúc request đã gửi đến khi response đầu tiên xuất hiện.
- Có API xem read timeout là thời gian tối đa không có byte mới giữa hai lần đọc.
- Có API tính thời gian nhận hết body.
- Có API đặt một request timeout ở cấp lời gọi; điều này cũng không tự bảo đảm phía nhận dừng mọi công việc.

Một server gửi một phần response mỗi 500 ms có thể không vi phạm idle read timeout 1 giây, dù tổng body kéo dài rất lâu. Nếu sản phẩm đòi caller không chờ quá 3 giây, cần xem xét **overall deadline** riêng.

Trong tài liệu thiết kế, hãy ghi timeout bắt đầu từ lúc nào, dừng ở sự kiện nào, thư viện/phiên bản nào thực thi và trường hợp response streaming được xử lý ra sao.

## 3. Phân biệt timeout với deadline

**Timeout** thường là khoảng thời gian được phép chờ một giai đoạn hoặc một lần gọi. **Deadline** là mốc kết thúc hoặc ngân sách tối đa cho toàn bộ yêu cầu từ góc nhìn caller.

Giả sử Gateway có ngân sách 2.000 ms cho một request Checkout:

    Gateway: còn 2000 ms
        |
        v
    Order: còn 1850 ms
        |
        +--> Inventory: còn 1200 ms
        |
        +--> Payment: còn 700 ms
                  |
                  +--> Provider: còn 400 ms

Các con số chỉ minh họa. Mỗi hop phải tính **ngân sách còn lại**, không tự cấp thêm 2 giây từ đầu.

Nếu Order gọi Inventory tối đa 2 giây, sau đó gọi Payment tối đa 2 giây, rồi Notification tối đa 2 giây, tổng có thể vượt 6 giây dù Gateway đã ngừng chờ ở giây thứ ba. Các service phía sau vẫn có thể tiêu thụ CPU và connection.

### 3.1. Truyền deadline qua service

Một cách triển khai:
1. Entry point xác định deadline theo giới hạn đáng tin cậy của hệ thống.
2. Mỗi service xác định thời gian đã trôi bằng đồng hồ đơn điệu tại tiến trình.
3. Khi gọi downstream, truyền ngân sách còn lại hoặc một deadline theo giao thức đã thống nhất.
4. Receiver lấy giá trị nhỏ hơn giữa giới hạn do caller cung cấp và **giới hạn của chính receiver**.
5. Trước khi bắt đầu việc tốn nhiều tài nguyên, service kiểm tra còn đủ ngân sách để thực hiện một bước có ý nghĩa không.
6. Nếu hết thời hạn, service ngừng phần việc có thể ngừng an toàn hoặc chuyển sang trạng thái bất đồng bộ có hợp đồng.

Một timestamp deadline tuyệt đối truyền giữa nhiều máy phải xem xét độ lệch đồng hồ. Không dùng riêng đồng hồ hệ thống có thể bị điều chỉnh để đo chính xác thời gian đã trôi; ưu tiên nguồn thời gian đơn điệu trong cùng tiến trình. Với giao thức có hỗ trợ deadline propagation như gRPC, vẫn phải xác minh cách framework và từng service phản ứng khi deadline vượt ngưỡng.

### 3.2. Deadline của HTTP không phải tuổi thọ của nghiệp vụ

Một request HTTP có thể chỉ đáng chờ tối đa một giây, nhưng nghiệp vụ thu tiền hoặc xuất báo cáo có thể tiếp tục lâu hơn. Khi như vậy, giải pháp thường phù hợp là **ghi nhận intent bền vững, trả operationId và xử lý bất đồng bộ**, thay vì giữ HTTP connection trong nhiều phút.

Nếu hệ thống vẫn chọn đồng bộ, cần quy định trạng thái khi deadline hết nhưng side effect chưa biết kết quả.

## 4. Timeline: timeout không đồng nghĩa thất bại

Giả sử Order gọi Payment với timeout 800 ms:

    T=0 ms       Order gửi ChargePayment
    T=150 ms     Payment nhận request, ghi paymentAttempt
    T=300 ms     Payment yêu cầu provider thu tiền
    T=800 ms     Order timeout và ngừng chờ
    T=1000 ms    Provider thu tiền thành công
    T=1080 ms    Payment ghi CAPTURED vào DB
    T=1150 ms    Payment trả response, nhưng kết nối không còn

Khi nhận timeout, Order **không thể kết luận** khoản thu chưa xảy ra. Nếu Order tạo một ChargePayment mới với idempotency key khác, người dùng có thể bị thu tiền hai lần.

Các trường hợp phải phân biệt:
- Request chắc chắn chưa được gửi tới một nơi có thể gây tác động.
- Request có thể đã gửi, nhưng không biết receiver đã bắt đầu chưa.
- Receiver đã ghi intent, đang chờ kết quả cuối.
- Receiver đã commit nhưng response bị mất.
- Receiver đã gọi một hệ thống ngoài và chưa biết kết quả.
- Receiver hoàn thành một phần workflow nhưng còn bước bù trừ.

Chỉ một số trường hợp có bằng chứng đủ mạnh rằng việc gửi lại một yêu cầu hoàn toàn mới là an toàn. Cách chung là dùng **idempotency key ổn định** và khả năng tra cứu trạng thái.

## 5. Giới hạn của hủy phía nhận

Đóng HTTP connection, hủy một Future hoặc kết thúc một reactive subscription thường chỉ đảm bảo **bên gọi ngừng chờ** trong phạm vi API cụ thể. Không có cam kết chung rằng:
- Thread ở receiver bị dừng ngay.
- Transaction database đã rollback.
- Lời gọi provider bên ngoài được thu hồi.
- Message đã phát lên broker bị xóa.
- Tác động đã commit bị hoàn tác.

### 5.1. Vì sao server có thể vẫn chạy?

Một servlet controller có thể đang thực hiện đoạn tính toán CPU và chưa động vào socket, nên chưa nhận ra client đã đóng kết nối. HTTP/2 có tín hiệu hủy stream, nhưng ứng dụng phải có đường xử lý tín hiệu đó. Một subscriber Reactor có thể cancel upstream; phần công việc nằm ở thư viện blocking, native driver hoặc hệ thống ngoài vẫn có thể chạy tiếp.

Việc HTTP response không gửi được không có nghĩa phương thức xử lý request chưa ghi dữ liệu.

### 5.2. Các giai đoạn và hướng xử lý hủy

| Giai đoạn | Hướng xử lý |
|---|---|
| Chưa bắt đầu công việc | Kiểm tra deadline/cancel token rồi từ chối bắt đầu |
| Đang tính toán không có tác dụng phụ | Kiểm tra hủy định kỳ, dừng tại điểm an toàn |
| Đang chờ downstream | Hủy subscription/lời gọi nếu driver hỗ trợ, giải phóng tài nguyên |
| Đang truy vấn chỉ đọc | Có thể gửi yêu cầu cancel statement nếu database hỗ trợ |
| Đang trong transaction ghi chưa commit | Quyết định rollback hoặc hoàn tất theo quy tắc toàn vẹn |
| Đã commit dữ liệu | Ghi nhận kết quả có hiệu lực; phục vụ tra cứu, phát sự kiện cần thiết |
| Đã gửi lệnh đến provider | Không giả định có thể hủy; truy vấn trạng thái hoặc đối soát |
| Đã phát job/message | Không coi hủy HTTP là hủy job/message đã giao |

**Hủy là một yêu cầu hợp tác tại những điểm an toàn, không phải rollback phân tán.**

### 5.3. Cooperative cancellation

Với tác vụ tính toán dài, ứng dụng có thể chủ động kiểm tra:

~~~java
// Giả mã: RequestContext do ứng dụng định nghĩa.
Report generate(RequestContext context, List<Item> items) {
    context.throwIfDeadlineExceeded();

    Report result = new Report();
    for (Item item : items) {
        context.throwIfDeadlineExceeded();
        result.add(calculate(item));
    }

    return result;
}
~~~

Nếu một bước đã tạo tác động có hiệu lực, đừng ném lỗi ở vị trí tùy ý rồi coi như chưa có gì xảy ra. Hệ thống cần state machine và cơ chế hoàn tất hoặc bù trừ theo nghiệp vụ.

## 6. Hủy trong Java có ý nghĩa đến đâu?

### 6.1. Thread interrupt

Java hỗ trợ cờ interrupt, nhưng một thread không bị kết thúc cưỡng bức chỉ vì có cờ này. Nhiều thao tác blocking phản ứng với interrupt; vòng lặp CPU hoặc thư viện không hợp tác có thể tiếp tục.

~~~java
try {
    performInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException("Interrupted", ex);
}
~~~

Khôi phục cờ interrupt thường hữu ích khi tầng hiện tại không xử lý đầy đủ việc ngắt. Tuy nhiên interrupt không phải giao thức hoàn tác transaction hoặc API bên ngoài.

### 6.2. CompletableFuture.cancel

CompletableFuture.cancel(true) không đảm bảo thread thực thi computation được interrupt. Future có thể có trạng thái cancelled trong khi tác vụ hoặc lời gọi remote vẫn tiếp tục. Cần hiểu executor và tác vụ bên dưới, truyền cancellation token khi phù hợp và không xem cancelled đồng nghĩa không có side effect.

### 6.3. Reactor và WebFlux

Reactor timeout có thể phát lỗi timeout rồi cancel subscription upstream. Nhưng cancellation của subscription có phạm vi riêng; đoạn blocking code, I/O driver hoặc thao tác đã commit có thể không bị dừng.

Khi dùng WebFlux, cần xác định:
- Cancellation signal có thực sự được đưa đến phần gọi HTTP khác không?
- Driver có dừng I/O hay chỉ dừng quan sát kết quả?
- Tác vụ nền được tạo riêng có nhận tín hiệu không?
- Một lần ghi database đã commit có còn cần hoàn tất phát event không?

### 6.4. Spring MVC và Servlet async

Timeout của async request có thể kích hoạt một sự kiện ở vòng đời Servlet, nhưng công việc tự chạy trên thread pool vẫn cần cơ chế hủy. Với MVC controller đồng bộ, timeout từ Gateway thường không tự động dừng toàn bộ Java method.

Không được dùng tên cấu hình server timeout để suy rằng mỗi controller có giới hạn thời gian thực thi cứng, trừ khi framework và cấu hình cụ thể thực sự thực thi như vậy.

## 7. Ví dụ client timeout với Java 21

Java HttpClient có cấu hình cho kết nối và request:

~~~java
HttpClient httpClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(300))
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://inventory.example/reservations"))
    .timeout(Duration.ofMillis(900))
    .header("Content-Type", "application/json")
    .header("Idempotency-Key", "order-123-reserve-1")
    .POST(HttpRequest.BodyPublishers.ofString(
        "{\"orderId\":\"ord-123\",\"sku\":\"SKU-7\",\"quantity\":1}"))
    .build();

try {
    HttpResponse<String> response = httpClient.send(
        request,
        HttpResponse.BodyHandlers.ofString()
    );
    handleResponse(response);
} catch (HttpConnectTimeoutException ex) {
    // Không tạo được kết nối trong thời hạn được cấu hình.
} catch (HttpTimeoutException ex) {
    // Lời gọi vượt thời hạn chờ theo API client.
    // Cần xử lý trạng thái chưa biết nếu command có side effect.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Caller ngừng chờ; receiver có thể vẫn xử lý.
}
~~~

Mã ví dụ cần import các lớp và xử lý IO exception theo ứng dụng thực tế. Kết nối có thể được tái sử dụng; connectTimeout không thay thế toàn bộ deadline. Phạm vi thực tế của request.timeout đối với response và body cần đối chiếu tài liệu phiên bản JDK, proxy và kiểu BodyHandler đang dùng. Nó cũng không chứng minh receiver đã dừng làm việc.

### 7.1. Ví dụ Spring WebClient và Reactor Netty

~~~java
HttpClient netty = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
    .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(netty))
    .baseUrl("https://inventory.example")
    .build();

Mono<ReservationResult> result = webClient.post()
    .uri("/reservations")
    .header("Idempotency-Key", requestKey)
    .bodyValue(command)
    .retrieve()
    .bodyToMono(ReservationResult.class)
    .timeout(Duration.ofMillis(900));
~~~

Ở đây:
- CONNECT_TIMEOUT_MILLIS điều khiển TCP connect theo Netty.
- responseTimeout điều khiển một dạng timeout phản hồi của Reactor Netty.
- Mono.timeout đặt giới hạn chờ ở mức publisher/subscription.

Ba cấu hình không có nghĩa tổng thời gian lời gọi luôn bằng phép cộng của ba con số. Còn phải xem DNS, pool, TLS, payload, response streaming và ngữ nghĩa thư viện đúng phiên bản. Khi subscription timeout, remote side effect vẫn có thể tiếp tục.

### 7.2. Không chọn một timeout cho mọi dependency

Một dịch vụ gợi ý sản phẩm có thể được gọi trong ngân sách ngắn và dùng fallback. Một lệnh thu tiền có thể cần flow theo operation ID vì kết quả chưa xác định. Một báo cáo dài nên được chuyển thành job. Một upload cần phân biệt write timeout, idle read timeout và thời gian tổng.

Cấu hình nên theo **loại nghiệp vụ và SLO**, dựa trên độ trễ thực tế p95/p99, khả năng chịu lỗi, tài nguyên và chi phí của kết quả thiếu chắc chắn.

## 8. Timeout ở receiver và database

Các cấu hình được gọi “server timeout” có thể là:
- Thời gian chờ nhận request headers/body.
- Keep-alive hoặc idle connection timeout.
- Servlet async request timeout.
- Transaction timeout.
- Query/statement timeout.
- Lock wait timeout.
- Giới hạn chạy một business operation do ứng dụng tự thực thi.

Đây là các giới hạn khác nhau. Keep-alive timeout 5 giây không có nghĩa mọi phương thức xử lý HTTP sẽ dừng sau 5 giây.

### 8.1. JDBC và database query cancellation

Một số driver/datastore cho phép đặt query timeout hoặc gửi yêu cầu cancel statement. Điều này có thể giải phóng tài nguyên, nhưng phải xác định:
- Driver có hỗ trợ và thực thi đúng không?
- Timeout áp dụng cho statement hay toàn transaction?
- Khi cancel trong lúc COMMIT, trạng thái cuối được xác nhận thế nào?
- Có connection hay lock bị giữ lại sau lỗi không?
- Retry transaction có thể chạy lại side effect không?

Không suy rằng query timeout luôn đồng nghĩa transaction đã rollback. Đặc biệt gần mốc COMMIT, caller có thể chưa biết trạng thái thực tế.

### 8.2. Transaction cục bộ và outbox

Ví dụ Order chuyển sang CONFIRMED:

~~~text
BEGIN
  kiểm tra trạng thái và bằng chứng nghiệp vụ
  UPDATE orders SET status = CONFIRMED, version = version + 1
  INSERT INTO outbox (eventId, type, payload)
COMMIT
~~~

Nếu HTTP client đã timeout, transaction vẫn có thể commit. Khi đã commit, một publisher vẫn cần phát event đã ghi trong outbox; không được tự xóa vì caller ngừng chờ. Đối với một lỗi chưa rõ commit thành công hay chưa, dùng cơ chế truy vấn/đối soát trạng thái nguồn.

### 8.3. Tránh giữ khóa DB khi đợi service ngoài

Một mẫu nguy hiểm:

~~~text
BEGIN transaction
  SELECT order FOR UPDATE
  call payment provider (có thể chờ 10 giây)
  UPDATE order
COMMIT
~~~

Thread giữ lock trong lúc chờ mạng. Điều này tạo lock contention, deadlock và tăng tail latency. Có thể tách thành transaction ghi PENDING, lời gọi provider bằng idempotency, rồi transaction cập nhật kết quả. Khi tách, cần state machine và cách đối soát, thay vì giả định giao dịch ACID trải qua HTTP.

## 9. Retry sau timeout phải được thiết kế theo ngữ nghĩa

Retry có thể cải thiện khả năng chịu lỗi tạm thời, nhưng cũng có thể nhân tải và tạo side effect trùng.

Nếu Gateway retry tối đa 3 lần, Order cũng retry 3 lần và Payment retry provider 3 lần, một request ban đầu có thể dẫn tới **27 lần thử ở tầng sâu** trong kịch bản xấu nhất. Đây là minh họa sự khuếch đại, không phải dự báo cho một hệ thống cụ thể.

### 9.1. Retry theo loại thao tác

| Thao tác | Cách tiếp cận |
|---|---|
| GET dữ liệu an toàn | Có thể retry giới hạn trong deadline |
| Tra cứu operation ID | Có thể polling/backoff theo hợp đồng |
| Ghi idempotent với key ổn định | Có thể retry khi owner bảo vệ chống trùng |
| POST tạo effect không có key | Không retry mù sau timeout |
| Charge/Refund | Chỉ retry theo hợp đồng Payment/provider, kèm tra trạng thái |
| Streaming/upload | Cần biết có resume hay phải bắt đầu lại |
| Tác vụ dài | Dùng operation ID và điều khiển riêng, tránh giữ HTTP |

### 9.2. Backoff và jitter

Khi retry phù hợp, cần:
- Giới hạn số lần thử.
- Exponential backoff hoặc chính sách tương đương kèm jitter.
- Không reset overall deadline ở mỗi lần retry.
- Dùng cùng idempotency key cho cùng intent.
- Chỉ retry các lỗi được phân loại là tạm thời.
- Có retry budget hoặc cơ chế chặn khi dependency đang quá tải.
- Log attempt number và kết quả cuối của một operation logic.

Nếu một lần thử cần tối thiểu 500 ms nhưng deadline chỉ còn 50 ms, không nên bắt đầu lại chỉ để nhận thêm một timeout. Dù vậy nếu intent đã được nhận bền vững, workflow phía server có thể vẫn cần tiếp tục hoàn tất hoặc đối soát.

## 10. Circuit breaker, bulkhead và overload

Timeout giới hạn **một lần chờ**. Circuit breaker có thể tránh tiếp tục gọi một dependency đang thất bại; bulkhead giới hạn số công việc đồng thời; rate limiting giới hạn tốc độ vào hệ thống.

Chúng hỗ trợ nhau:

    Caller
      |
      +-- Check deadline
      +-- Rate / concurrency limit
      +-- Circuit breaker
      +-- Transport timeout
      +-- Downstream

Nếu Payment chậm 30 giây, 200 thread của Order có thể bị giữ hết dù Payment cuối cùng trả lời. Khi tải 20 yêu cầu/giây, trực giác tải × thời gian cho thấy số yêu cầu đồng thời có thể lớn hơn 200 rất nhanh. Một timeout phù hợp và giới hạn đồng thời giúp bảo vệ hệ thống; nhưng cũng cần giải quyết nguyên nhân Payment chậm.

**Fallback chỉ phù hợp khi kết quả thay thế có ý nghĩa nghiệp vụ.** Recommendation timeout có thể bỏ gợi ý; dashboard timeout có thể hiển thị snapshot cũ và dấu thời gian. Payment timeout không được tự báo “đã thanh toán” hoặc “chưa thu tiền”; Inventory timeout không được giả định “đã giữ hàng”.

## 11. Idempotency và trạng thái UNKNOWN

Với một command có side effect, định danh **ý định nghiệp vụ** phải tách khỏi một lần gọi mạng.

Ví dụ:

    Intent: Charge order ord-123, amount 500000 VND
    Idempotency-Key: charge-ord-123-attempt-1

Nếu caller timeout, retry cùng intent dùng **cùng key** và cùng payload theo quy tắc Payment công bố.

Service sở hữu cần quy định:
- Phạm vi khóa theo tenant, caller, command type và resource.
- Cùng key/cùng payload được trả lại kết quả nào.
- Cùng key/khác payload bị từ chối ra sao.
- Thời hạn lưu khóa và trạng thái sau thời hạn.
- Hai request đồng thời cùng key được chống trùng bằng constraint/transaction thế nào.
- Provider bên ngoài có hỗ trợ idempotency hay phải dùng đối soát.

### 11.1. Một contract có operation ID

~~~http
POST /payments/operations
Idempotency-Key: charge-ord-123-attempt-1
Content-Type: application/json

{
  "orderId": "ord-123",
  "amountMinor": 500000,
  "currency": "VND"
}
~~~

Server có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /payments/operations/pay-op-77
Content-Type: application/json

{
  "operationId": "pay-op-77",
  "status": "PROCESSING"
}
~~~

Trạng thái có thể đi qua:

    ACCEPTED -> PROCESSING -> CAPTURED
                    |
                    +-------> FAILED
                    |
                    +-------> NEEDS_RECONCILIATION

Nếu POST ban đầu timeout, caller có thể tra status bằng operationId hoặc idempotency key theo hợp đồng. Không nên tạo một charge mới với key khác chỉ vì chưa thấy phản hồi.

### 11.2. Hủy Payment khác hoàn tiền

Một request cancel HTTP hoặc cancel Future không có nghĩa một khoản thu đã được hoàn. Nếu provider đã capture thành công, hệ thống có thể cần nghiệp vụ Refund theo quy tắc Payment, với authorization, amount và idempotency riêng.

## 12. Hủy công việc dài như một nghiệp vụ

Một job xuất báo cáo có thể chạy vài phút. Thay vì để HTTP chờ liên tục:

1. POST /exports ghi nhận công việc và trả operationId.
2. Worker thực hiện từng phần với giới hạn tài nguyên riêng.
3. GET /exports/{id} trả trạng thái.
4. POST /exports/{id}/cancel yêu cầu hủy.
5. Worker kiểm tra cờ hủy ở điểm an toàn.
6. Server ghi CANCELLED khi thực sự dừng được; nếu đã hoàn tất thì trả COMPLETED.

Phân biệt:
- **CANCEL_REQUESTED:** Yêu cầu đã đến.
- **CANCELLING:** Đang thực hiện bước dừng và cleanup.
- **CANCELLED:** Đã dừng theo hợp đồng.
- **COMPLETED:** Đã có kết quả hiệu lực, có thể không còn hủy được.
- **FAILED:** Công việc lỗi; trạng thái tác động phụ cần được xác nhận riêng.

Hủy job có thể phải dọn file tạm, giải phóng reservation hoặc bù trừ. Không được chỉ xóa record job và giả định mọi tác động biến mất.

## 13. Proxy, gateway và HTTP status

Một request có thể bị giới hạn bởi nhiều tầng:

    Browser
       |
    CDN / Load balancer
       |
    API Gateway
       |
    Service A / HTTP client
       |
    Service B / Database

Nếu Gateway timeout trước Service A, người dùng có thể nhận **504 Gateway Timeout** trong khi A vẫn đang xử lý. Nếu A giới hạn thời gian chờ ngắn hơn, nó có cơ hội trả lỗi có kiểm soát trước khi Gateway ngắt, nhưng vẫn phải xử lý trạng thái nghiệp vụ chưa biết.

Các mã thường thấy:
- **408 Request Timeout:** Thường liên quan server không nhận đủ request kịp thời; không phải mã chung cho mọi downstream timeout.
- **504 Gateway Timeout:** Gateway/proxy không nhận upstream response đúng thời hạn.
- **503 Service Unavailable:** Service tạm không phục vụ, ví dụ quá tải hoặc bảo trì.
- **502 Bad Gateway:** Gateway nhận upstream response không hợp lệ hoặc gặp lỗi giao tiếp.
- **499:** Mã log không chuẩn mà một số proxy dùng khi client đóng connection; không phải HTTP status chuẩn cho ứng dụng gửi đi.

Mapping thực tế tùy proxy/framework. HTTP status không đủ để kết luận trạng thái giao dịch phía receiver.

### 13.1. Idle timeout trong streaming

SSE, HTTP streaming hoặc tải file lớn cần xem thời gian chờ giữa các lần truyền dữ liệu và giới hạn tổng thời gian. Heartbeat có thể giữ connection không bị coi là idle tại một số tầng nhưng không tự hoàn tất công việc nghiệp vụ. Với API stream, cần chính sách cho consumer chậm, backpressure và đóng stream.

## 14. Khi nào nên đồng bộ, khi nào nên chuyển bất đồng bộ?

Giữ lời gọi đồng bộ khi:
- Caller thực sự cần kết quả trước khi tiếp tục.
- Thời gian xử lý đủ ngắn và có phân phối latency phù hợp ngân sách.
- Khi timeout, kết quả có thể được xử lý an toàn.
- Không tạo chuỗi phụ thuộc đồng bộ quá dài.

Chuyển thành operation bất đồng bộ khi:
- Công việc thường dài hơn deadline người dùng chấp nhận.
- Có tác động ngoài hệ thống không thể hủy bằng HTTP.
- Phải thử lại, đối soát hoặc bù trừ qua nhiều bước.
- Người dùng có thể nhận ID rồi theo dõi trạng thái.
- Giữ connection liên tục làm tăng đáng kể áp lực lên thread và pool.

**Chuyển sang async không tự làm nghiệp vụ chính xác.** Vẫn cần state machine, idempotency, message ordering, outbox, retries và monitoring. Lợi ích là tách thời gian chờ HTTP khỏi vòng đời công việc.

## 15. Observability: đo từng chặng thay vì một metric “timeout”

Các chỉ số hữu ích:

| Metric / trace event | Điều cần biết |
|---|---|
| Pool acquire wait và pending count | Có thiếu connection không? |
| DNS lookup latency | Tên miền có được phân giải nhanh không? |
| TCP connect attempts/timeouts | Kết nối mới có thất bại không? |
| TLS handshake failures/latency | Lỗi nằm ở bảo mật/chứng chỉ/mạng? |
| Request write duration | Có bị nghẽn khi upload không? |
| Time to response headers | Server xử lý/định tuyến chậm đến đâu? |
| Response body read/idle time | Stream có bị treo hoặc đọc chậm không? |
| End-to-end request duration | Có đạt deadline/SLO không? |
| Deadline remaining by hop | Tầng nào dùng phần lớn ngân sách? |
| Server queue time/processing time | Có chờ thread hay tài nguyên không? |
| Caller timeout và server observed cancel | Có nhận tín hiệu hủy không? |
| Work completed after caller left | Side effect có tiếp tục sau timeout không? |
| Retry attempts/amplification | Retry có gây thêm tải không? |
| Idempotency hits/conflicts | Chống trùng có đang hoạt động không? |
| Unknown outcomes và reconciliation backlog | Có bao nhiêu tác vụ chưa biết kết quả? |
| DB lock wait/query timeout | Có nghẽn trong datastore không? |

### 15.1. Phân biệt trace ID và idempotency key

Trace ID dùng để liên kết các span trong một chuỗi gọi; các lần thử mạng có thể có span riêng. Idempotency key nhận diện **cùng ý định nghiệp vụ**, phải ổn định qua retry tương ứng. Nếu dùng trace ID mới làm idempotency key mới ở mỗi lần retry, hệ thống sẽ mất khả năng chống trùng.

### 15.2. Một trace mẫu

    Trace checkout-42
      Gateway                     0..1000ms
        Order                    10..980ms
          Inventory              50..260ms
          Payment               300..960ms
            Provider            400..>1000ms
        Order client timeout    960ms

Payment có thể hoàn tất sau khi trace gọi ban đầu ở Order kết thúc. Dùng operationId/correlation ID để liên hệ kết quả đến sau và audit.

### 15.3. Không đặt tên metric gây hiểu nhầm

Tên “cancelled_requests_total” có thể chỉ đếm **caller stopped waiting**. Nên tách:
- Cancellation requested.
- Receiver observed cancellation.
- Work stopped before effect.
- Operation completed after cancellation.
- Compensation requested/completed.

Không gộp tất cả thành “đã hủy thành công”.

## 16. Kiểm thử timeout, cancellation và kết quả nghiệp vụ

Không chỉ kiểm tra có ném HttpTimeoutException; cần biết trạng thái của receiver.

| Tình huống | Điều phải xác minh |
|---|---|
| Pool đầy, không lấy được connection | Acquire timeout và resource được giải phóng |
| DNS chậm | Deadline tổng thể được tôn trọng theo phạm vi thiết kế |
| TCP không kết nối được | Phân biệt connect timeout và HTTP error |
| TLS handshake chậm | Có giới hạn phù hợp cho handshake |
| Server trả headers chậm | Client hết hạn đúng theo semantics cấu hình |
| Body gửi nhỏ giọt | Idle timeout khác overall deadline |
| Gateway hết hạn trước service | Server có thể tiếp tục; trạng thái vẫn truy vấn được |
| Client đóng socket khi server tính toán | Tác vụ nhận cancel ở điểm hợp tác và dừng an toàn |
| Timeout ngay trước COMMIT | Không tự khẳng định rollback; xác minh dữ liệu |
| Timeout ngay sau COMMIT | Idempotent retry không tạo hiệu ứng mới |
| Provider thu tiền nhưng phản hồi trễ | Caller dùng UNKNOWN/PENDING, tra lại thay vì thu thêm |
| Hai retry cùng key đến đồng thời | Chỉ một effect nghiệp vụ |
| Consumer nhận event trùng | Không nhân đôi side effect tại consumer |
| Tác vụ bị hủy giữa chừng | Cleanup/bù trừ theo trạng thái chính xác |
| Nhiều request timeout liên tục | Thread, pool, memory, subscription không rò rỉ |

Có thể dùng mock HTTP server để cố ý trì hoãn headers/body, proxy gây lỗi mạng và datastore thực tế để thử transaction. Với Payment, dùng sandbox hoặc provider giả lập. Kiểm thử cạnh tranh phải dùng cơ chế concurrency thật; một unit test gọi tuần tự không chứng minh chống trùng.

### 16.1. Một kịch bản kiểm thử có giá trị

1. Gửi ChargePayment với key K.
2. Làm client timeout sau khi provider đã commit charge nhưng trước khi response tới Order.
3. Kiểm tra Order ghi nhận kết quả chưa xác định.
4. Gửi lại cùng key K.
5. Xác nhận Payment không tạo thêm khoản thu.
6. Tra operation ID; trạng thái cuối cùng là CAPTURED đúng một lần.
7. Xác nhận event/outbox và hệ thống kế toán nhận kết quả theo hợp đồng.

Đây là bài kiểm thử **độ đúng nghiệp vụ dưới timeout**, không chỉ kiểm thử cấu hình HTTP.

## 17. Ví dụ thiết kế Checkout an toàn hơn

Một thiết kế dễ gặp:

    POST /checkout
      -> Order tạo đơn
      -> Inventory giữ hàng
      -> Payment gọi provider (chờ tối đa 30s)
      -> Notification gửi email
      -> Trả "Success"

Nếu Gateway timeout ở giây thứ ba, Order có thể vẫn gọi Payment và gửi email. Khi người dùng bấm lại, có thể xuất hiện hai đơn hoặc hai khoản thu.

Một thiết kế theo trạng thái:

    Client -- POST /checkout, idempotencyKey --> Order
                                    |
                                    +-- Commit order=PENDING
                                    +-- Outbox / khởi chạy workflow
    Client <-- 202 + orderId + status=PENDING

    Workflow:
      Order -> Inventory: ReserveStock(orderId, stable key)
      Inventory -> Order: Reserved / Rejected / Pending

      Order -> Payment: Charge(orderId, stable key)
      Payment -> Order: Captured / Failed / Pending

      Order: xác nhận trạng thái cuối theo state machine
      Notification: nhận OrderConfirmed, gửi email

Đây là một lựa chọn phù hợp khi các phụ thuộc có latency dài hoặc kết quả không chắc chắn. Nếu nghiệp vụ và SLO cho phép trả kết quả đồng bộ nhanh, vẫn có thể giữ synchronous path nhưng cần cùng các nguyên tắc idempotency, deadline và trạng thái.

### 17.1. Inventory timeout

Order không được kết luận Inventory chưa giữ hàng. Nó truy vấn reservation theo key, chờ event hoặc chuyển sang trạng thái xác minh. Nếu đơn đã bị hủy nhưng reservation tồn tại, Order yêu cầu ReleaseReservation; Inventory phải xử lý lệnh release một cách idempotent, không cộng số lượng hai lần.

### 17.2. Payment timeout

Order chuyển PENDING_PAYMENT_VERIFICATION hoặc trạng thái tương đương, tiếp tục tra kết quả từ Payment. Payment phải kiểm soát idempotency với provider, không dùng retry key mới bừa bãi.

### 17.3. Người dùng yêu cầu hủy

Nếu workflow chưa bắt đầu payment, Order có thể hủy theo chính sách. Nếu provider đã thu tiền, yêu cầu hủy có thể dẫn đến refund thay vì rollback. UI cần phân biệt CANCEL_REQUESTED, CANCELLING, CANCELLED và REFUND_PENDING khi nghiệp vụ yêu cầu.

## 18. Các ngộ nhận phổ biến

**“Connect timeout 1 giây nghĩa là toàn bộ HTTP call tối đa 1 giây.”** Sai; còn pool, DNS, TLS, gửi request, nhận response và xử lý.

**“Read timeout 2 giây nghĩa là response body luôn hoàn tất trong 2 giây.”** Không chắc; một số read timeout đo khoảng im lặng giữa các lần đọc.

**“Caller timeout thì server đã dừng.”** Sai; server có thể đang tiếp tục CPU, transaction hoặc provider call.

**“Future.cancel(true) sẽ interrupt và rollback mọi việc.”** Sai; cancellation ở Java phụ thuộc tác vụ và không tự hoàn tác I/O ngoài.

**“Reactive timeout đồng nghĩa mọi side effect bị cancel.”** Sai; chỉ subscription và các nguồn hỗ trợ cancel có thể phản ứng.

**“Gateway trả 504 nghĩa là Payment đã thất bại.”** Sai; 504 phản ánh thời hạn chờ của gateway.

**“Bỏ kết nối tức là hủy giao dịch đã commit.”** Sai; giao dịch đã commit có hiệu lực và cần được xử lý đúng.

**“Retry càng nhiều càng an toàn.”** Sai; có thể gây retry storm và giao dịch lặp.

**“Cứ tăng timeout lên 60 giây sẽ giảm sự cố.”** Có thể giữ tài nguyên lâu và làm quá tải nghiêm trọng hơn.

**“Có circuit breaker nên không cần timeout.”** Sai; cơ chế ngăn lời gọi mới không tự giới hạn mọi lời gọi đang treo.

**“Timeout phía server là một thông số chung.”** Sai; request receive, async execution, DB query, transaction và keep-alive có các ngữ nghĩa khác nhau.

**“Một response đã có headers là đã tải xong.”** Sai; body streaming có thể chậm hoặc kẹt độc lập.

## 19. Quy trình thiết kế cho một đường gọi đồng bộ

### Bước 1 — Xác định tác động của operation

Đây là GET an toàn, command idempotent, tạo side effect hay quy trình dài? Nếu có side effect, kết quả có được tra cứu bằng ID không?

### Bước 2 — Vẽ bản đồ các hop

Liệt kê Client, Gateway, service, proxy, connection pool, database và provider. Đánh dấu nơi request bắt đầu, nơi commit và nơi caller có thể nhận phản hồi.

### Bước 3 — Chọn overall deadline

Dựa vào mục tiêu sản phẩm và dữ liệu latency thực tế. Để phần ngân sách cho serialize/response và tránh cấp thêm toàn bộ deadline ở mỗi hop.

### Bước 4 — Cấu hình timeout từng giai đoạn

Phân biệt pool acquire, DNS, TCP connect, TLS, write, response/read và body. Ghi rõ semantics của client library/phiên bản.

### Bước 5 — Định nghĩa hành vi khi timeout

Nếu GET không quan trọng, có thể fallback. Nếu command có side effect, dùng trạng thái UNKNOWN/PENDING, idempotency key và status query. Không giả định timeout là rollback.

### Bước 6 — Xác định phạm vi cancel

Nêu phần việc có thể dừng hợp tác, phần phải hoàn tất sau commit và phần cần bù trừ. Nếu cần hủy nghiệp vụ dài, thiết kế API cancel riêng.

### Bước 7 — Retry và chống quá tải

Một tầng sở hữu retry, số lần giới hạn, backoff/jitter, cùng key cho cùng ý định, kiểm tra deadline còn lại, circuit breaker và bulkhead khi phù hợp.

### Bước 8 — Kiểm chứng

Thử lỗi trước và sau commit, response headers/body chậm, cancellation, provider kết quả trễ, retry đồng thời và resource cleanup. Đo tại cả caller lẫn receiver.

## 20. Mẫu ghi quyết định kiến trúc (ADR)

~~~text
ADR: Timeout, Deadline và Cancellation cho <operation>

Mục tiêu nghiệp vụ / SLO:
Caller và receiver:
Các hop: Gateway, proxy, service, DB, provider:
Loại thao tác và side effect:
Operation ID / idempotency key:
Điểm ra quyết định và điểm commit:
Pool acquire timeout:
DNS / TCP connect / TLS handshake timeout:
Request write / response headers / body read timeout:
Overall deadline và cách truyền qua hop:
Deadline còn lại trước từng bước:
Chính sách concurrency limit / bulkhead / circuit breaker:
Retry owner, số lần, backoff, lỗi cho phép retry:
Fallback nào hợp lệ theo nghiệp vụ:
Hành vi khi chưa gửi request:
Hành vi khi đã gửi nhưng chưa biết kết quả:
Hành vi khi receiver đã commit:
Server-side cancellation signal và điểm hủy an toàn:
Phần không thể hủy, quy trình bù trừ:
Status query / đối soát:
Metric, tracing, alert và cleanup:
Các phép thử lỗi đã định nghĩa:
Rủi ro và thời điểm đánh giá lại:
~~~

## 21. Bài thực hành: một lần thu tiền bị timeout

Một cửa hàng có Gateway → Order → Payment → Provider. Giả định:
- Gateway đặt overall timeout 2.000 ms.
- Order gọi Payment với response timeout 1.500 ms.
- Payment xử lý cục bộ 200 ms và gọi Provider có thể mất 2.500 ms.
- Provider có thể thu tiền thành công nhưng trả kết quả trễ.
- Order hiện retry cùng một khoản thu hai lần với **key mới** ở mỗi lần thử.
- HTTP client của Payment đặt TCP connect timeout 500 ms nhưng không giới hạn pool acquire.
- Nhóm vận hành chỉ có metric payment_error_total.

**Yêu cầu:**
1. Vẽ timeline khi provider commit khoản thu ở 1.800 ms và response về ở 2.300 ms. Order và Gateway có thể thấy gì?
2. Phân biệt connect timeout 500 ms, pool acquire và response timeout 1.500 ms.
3. Giải thích vì sao retry với key mới có thể thu hai lần. Đề xuất operation ID và key ổn định.
4. Đề xuất deadline tổng cùng cơ chế truyền remaining budget qua các service.
5. Khi Order đóng socket sau 1.500 ms, Payment Spring MVC có chắc dừng không? Vì sao?
6. Nếu provider đã thu tiền, một yêu cầu cancel HTTP có tương đương hoàn tiền không?
7. Thiết kế các trạng thái PROCESSING, CAPTURED, FAILED, NEEDS_RECONCILIATION.
8. Bổ sung metric pool wait, connect, response, timeout, cancellation observed và kết quả hoàn tất sau caller timeout.
9. Viết ba test: timeout trước commit, timeout sau provider commit, hai retry đồng thời cùng key.
10. Đề xuất khi nào nên trả 202 + operationId thay cho việc giữ HTTP mở đến khi provider xong.

**Hướng tiếp cận:** Nếu kết quả thu tiền chưa chắc chắn, Order nên giữ PENDING_PAYMENT hoặc NEEDS_VERIFICATION và truy vấn Payment. Payment dùng một paymentAttemptId/idempotency key ổn định với provider; timeout chỉ dừng thời gian chờ trong phạm vi caller. Khi operation có thể kéo dài ngoài deadline, xử lý bất đồng bộ giúp giữ trạng thái có thể khôi phục và tránh giữ connection quá lâu.

## 22. Ghi nhớ

1. Timeout kết nối, chờ pool, DNS, TLS, timeout phản hồi và tổng deadline là những cơ chế khác nhau.
2. Phải mô tả chính xác thời điểm bắt đầu/kết thúc của mỗi timeout trong thư viện đang dùng.
3. Deadline từ đầu đến cuối giới hạn ngân sách chờ, tránh mỗi hop tự kéo dài request.
4. Caller hết thời hạn chờ không chứng minh receiver đã ngừng hoặc rollback.
5. Hủy phía nhận có giới hạn; thread, Future, reactive stream, database và provider có khả năng hủy khác nhau.
6. Side effect đã commit cần được ghi nhận, tra cứu và đối soát, kể cả khi caller đã bỏ cuộc.
7. Retry chỉ an toàn khi theo hợp đồng nghiệp vụ, cùng identity và cơ chế idempotency.
8. Circuit breaker, bulkhead và kiểm soát retry hỗ trợ timeout trong phòng ngừa lỗi dây chuyền.
9. Công việc kéo dài nên cân nhắc operation bất đồng bộ với trạng thái và yêu cầu hủy rõ ràng.
10. Kiểm thử phải quan sát đúng dữ liệu và tác động thực tế ở receiver, không chỉ exception của client.
