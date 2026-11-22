# Scatter-gather và giới hạn phối hợp nhiều hệ thống

Trong **SPRING_BOOT_INTEGRATION**, một luồng Spring Boot có thể phải phối hợp nhiều HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Một trường hợp điển hình: ứng dụng nhận **một yêu cầu** nhưng phải lấy dữ liệu từ **nhiều hệ thống** trước khi tạo **một câu trả lời**. Mẫu **scatter-gather** tổ chức luồng này thành hai bước: **scatter** phân phối yêu cầu đến các nhánh, **gather** gom những câu trả lời liên quan rồi quyết định khi nào có thể trả kết quả.

Scatter-gather đơn giản về mặt sơ đồ, nhưng không đơn giản về mặt vận hành. Khi một nguồn chậm, trả lỗi, phản hồi trùng hoặc phản hồi muộn, ứng dụng phải quyết định có chờ tiếp, trả dữ liệu một phần, báo lỗi hay chuyển sang xử lý bất đồng bộ. Nếu các nhánh **thay đổi dữ liệu** thay vì chỉ đọc, việc gom kết quả còn liên quan đến ranh giới giao dịch và khả năng phục hồi khi một phần hệ thống đã commit.

Mục tiêu của bài học là sử dụng scatter-gather đúng ngữ nghĩa trong Spring Integration và nhận diện các giới hạn **thời gian, tính nhất quán, lỗi, bộ nhớ trạng thái, thông điệp lặp và khả năng quan sát** của một luồng tích hợp thực tế.

## 1. Tình huống xuyên suốt: hỏi giá ba đối tác

Giả sử dịch vụ **Báo giá** nhận yêu cầu từ HTTP API và cần tham khảo giá tại các đối tác A, B, C. Mỗi đối tác có endpoint, giới hạn truy cập, độ trễ và hợp đồng dữ liệu riêng. Ứng dụng muốn chuẩn hóa về VND, kiểm tra hạn hiệu lực và chọn báo giá thấp nhất trong số các câu trả lời hợp lệ.

~~~mermaid
flowchart TD
  IN["HTTP request: báo giá SKU-001"] --> SG["Scatter: fan-out theo danh sách đối tác"]
  SG --> A["HTTP Client A"]
  SG --> B["HTTP Client B"]
  SG --> C["HTTP Client C"]
  A --> GA["Gather: correlation + group"]
  B --> GA
  C --> GA
  GA --> REL{"Đủ điều kiện release?"}
  REL -->|Đủ| MAP["Chuẩn hóa, chọn giá và tạo response"]
  REL -->|Chưa đủ| WAIT["Chờ reply hoặc hết hạn nhóm"]
  WAIT --> GA
  MAP --> OUT["HTTP response"]
~~~

Ví dụ số liệu **giả định**, không phải SLA thật:

| Đối tác | Kết quả | Thời gian |
| --- | --- | --- |
| A | 400.000 VND | 120 ms |
| B | 390.000 VND | 700 ms |
| C | Timeout | Sau 1.000 ms vẫn chưa có reply |

Nếu quy tắc là **all-of-3**, chưa thể tổng hợp đầy đủ khi C không phản hồi. Nếu quy tắc là **ít nhất 2/3 báo giá hợp lệ**, có thể trả giá của B kèm trạng thái **PARTIAL**. Nếu nghiệp vụ bắt buộc phải có C thì A và B đều hoàn tất cũng chưa đủ. Quy tắc hoàn tất là **hợp đồng nghiệp vụ**, không phải việc framework có thể tự suy ra.

Cần chốt trước khi triển khai:

1. Nhánh nào được gọi với mỗi yêu cầu; danh sách cố định hay định tuyến động theo SKU, vùng địa lý, quyền hoặc loại khách hàng?
2. Cần mọi reply, K reply hợp lệ hay chỉ reply đầu tiên thỏa một tiêu chí?
3. Một nhánh lỗi có làm toàn bộ request lỗi không? Có được dùng dữ liệu từ cache hay trả kết quả từng phần?
4. Khi đã trả response, dữ liệu đến muộn phải bị bỏ qua hay được xử lý qua một quy trình khác?

## 2. Phân biệt scatter-gather với các Enterprise Integration Patterns khác

| Mẫu | Đơn vị được phân phối | Mục đích |
| --- | --- | --- |
| **Splitter** | Các phần khác nhau của một payload | Tách đơn hàng thành dòng hàng |
| **Content-Based Router** | Một message được chọn nhánh dựa trên điều kiện | Đưa đơn hàng quốc tế sang adapter riêng |
| **Publish-Subscribe** | Một message tới nhiều subscriber | Thông báo cùng một sự kiện tới nhiều bộ phận |
| **Recipient List Router** | Một message tới tập recipient được chọn | Gửi yêu cầu báo giá tới A và C theo sản phẩm |
| **Aggregator** | Nhiều message thuộc cùng một nhóm | Gom các reply thành danh sách hoặc kết quả tính toán |
| **Scatter-Gather** | Một yêu cầu được gửi tới nhiều recipient và gom reply | Hỏi nhiều nguồn rồi trả một kết quả |

Trong Spring Integration, **ScatterGatherHandler** kết hợp một bộ phân phối với **AggregatingMessageHandler**. Bộ phân phối có hai dạng chính:

- **Auction:** dựa trên **PublishSubscribeChannel**, thuận tiện khi mỗi yêu cầu đến cùng tập subscriber.
- **Distribution:** dựa trên **RecipientListRouter**, có thể chọn recipient theo điều kiện động. Đây là lựa chọn thường gặp nếu mỗi SKU chỉ phù hợp với một số nhà cung cấp.

Hai dạng này là các lựa chọn scatter khác nhau của cùng endpoint. Phần gather đều cần correlation, điều kiện release, bộ nhớ nhóm và xử lý đầu ra. Spring Integration cung cấp nhiều thành phần EIP riêng lẻ; có thể tổ hợp chúng thay vì sử dụng scatter-gather nếu yêu cầu vượt quá luồng request-reply thông thường.

## 3. Correlation, sequence và đường phản hồi

### 3.1. Vì sao không được gom theo thời điểm nhận?

Giả sử hai HTTP request **R-101** và **R-102** được xử lý đồng thời. Reply của A cho R-102 có thể về trước reply của A cho R-101. Nếu aggregator chỉ cộng dồn ba message tiếp theo, kết quả của hai khách hàng sẽ trộn vào nhau. Cần có định danh nhóm ổn định và duy nhất cho **mỗi lượt fan-out**.

Spring Integration dùng các message header quan trọng:

| Header | Vai trò |
| --- | --- |
| **correlationId** | Xác định các message thuộc cùng một nhóm gather |
| **sequenceNumber** | Chỉ số message trong nhóm, hữu ích để theo dõi nguồn và sequence |
| **sequenceSize** | Số reply dự kiến khi dùng chính sách đủ toàn bộ sequence |
| **replyChannel** | Đường nhận reply từ các recipient rồi chuyển tới gatherer |
| **errorChannel** | Đường xử lý lỗi message, đặc biệt khi nhánh chạy bất đồng bộ |

**applySequence=true** đặt correlation và sequence metadata cho message được phân phối. Từ Spring Integration **6.0**, cấu hình XML và Java DSL cho scatter-gather tự thiết lập apply-sequence trong kịch bản chuẩn. Khi xây dựng trực tiếp **ScatterGatherHandler** và scatterer bằng Java, cần bảo đảm cấu hình này hoặc tự cung cấp correlation strategy phù hợp.

Với **RecipientListRouter** có lọc động, sequenceSize phải tương ứng **số recipient đã được chọn thực sự**, không phải số đối tác được đăng ký trong ứng dụng. Nếu chỉ gọi A và B mà group chờ ba reply, việc gather có thể treo cho đến timeout dù cả hai nguồn đều thành công.

~~~mermaid
sequenceDiagram
  participant API as API Gateway
  participant SG as ScatterGatherHandler
  participant A as Supplier A
  participant B as Supplier B
  participant C as Supplier C
  participant G as Aggregator
  API->>SG: request R-101
  SG->>A: correlation=g-1; seq=1/3
  SG->>B: correlation=g-1; seq=2/3
  SG->>C: correlation=g-1; seq=3/3
  A-->>G: quote A; correlation=g-1
  C-->>G: quote C; correlation=g-1
  B-->>G: quote B; correlation=g-1
  G->>G: ReleaseStrategy + MessageGroupProcessor
  G-->>SG: aggregate reply
  SG-->>API: một response
~~~

Nên giữ thêm **requestId** do ứng dụng tạo trong payload hoặc một header có hợp đồng vận chuyển rõ ràng để truy vết xuyên HTTP, DB, broker. Không đồng nhất requestId nghiệp vụ với correlationId nội bộ nếu ứng dụng có thể scatter nhiều lần cho cùng một request.

### 3.2. Gatherer làm những gì?

**AggregatingMessageHandler** có các thành phần chính:

1. **CorrelationStrategy:** gán mỗi reply vào đúng message group.
2. **MessageStore:** giữ các reply và metadata của group cho tới khi có quyết định release.
3. **ReleaseStrategy:** trả lời câu hỏi nhóm đã sẵn sàng chưa.
4. **MessageGroupProcessor:** biến tập reply thành một output; có thể là danh sách, báo giá tốt nhất hoặc object thể hiện kết quả từng phần.

Mặc định, release thường dựa trên **đủ sequenceSize**; output thường là danh sách payload. Nhưng một thông điệp lỗi được đưa vào group cũng có thể làm tăng số reply đã nhận. Vì vậy, **đủ số lượng reply** và **đủ số reply hợp lệ** là hai khái niệm khác nhau.

## 4. Cấu hình minh họa bằng Java DSL

Ví dụ sau chạy trên Spring Boot với Spring Integration Java DSL hiện đại. Các HTTP adapter được che sau interface **QuoteClients** nhằm tách phần gọi hệ thống ngoài khỏi phần điều phối.

~~~java
// Các kiểu nghiệp vụ; có thể tách thành file riêng khi triển khai.
public record QuoteRequest(
        UUID requestId, String sku, int quantity) {}

public record SupplierQuote(
        String supplier, BigDecimal totalVnd, Instant validUntil) {}

public interface QuoteClients {
    SupplierQuote quoteA(QuoteRequest request);
    SupplierQuote quoteB(QuoteRequest request);
    SupplierQuote quoteC(QuoteRequest request);
}
~~~

~~~java
@Configuration
public class QuoteIntegrationConfig {

    @Bean
    IntegrationFlow bestQuoteFlow(QuoteClients clients) {
        return IntegrationFlow.from("quoteRequests")
            .scatterGather(
                scatter -> scatter
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteA(request)))
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteB(request)))
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteC(request))),
                gather -> gather
                    .outputProcessor(group -> group.getMessages().stream()
                        .map(message -> (SupplierQuote) message.getPayload())
                        .filter(q -> q.validUntil().isAfter(Instant.now()))
                        .min(Comparator.comparing(SupplierQuote::totalVnd))
                        .orElseThrow(() ->
                            new IllegalStateException("No valid quote"))),
                scatterGather -> scatterGather
                    .gatherTimeout(1_500)
                    .requiresReply(true))
            .channel("quoteResults")
            .get();
    }
}
~~~

~~~java
// Gateway ở phía gọi luồng, không phụ thuộc trực tiếp vào message channels.
@MessagingGateway
public interface BestQuoteGateway {
    @Gateway(requestChannel = "quoteRequests", replyTimeout = 2_000)
    SupplierQuote bestQuote(QuoteRequest request);
}
~~~

**Ý nghĩa của ví dụ:**

- Scatterer tạo ba recipient flow; mỗi flow gọi một adapter và **trả reply**, không kết thúc bằng thao tác chỉ có side effect.
- Gatherer chuyển payload của các reply thành **SupplierQuote**, loại bỏ báo giá hết hạn và chọn giá VND thấp nhất. Đây là ví dụ **happy path** giả định mọi nhánh trả object hợp lệ, cùng đơn vị và cùng điều kiện giá.
- **gatherTimeout(1_500)** là thời gian chờ reply từ aggregator tính theo **millisecond**. Nó không tự cấu hình timeout cho HTTP client và không tự động tạo partial result.
- **requiresReply(true)** đòi một kết quả trả về; không có kết quả khi hết hạn có thể dẫn tới exception thay vì một response bình thường.
- Cần import các API tương ứng từ Spring Integration, Spring Framework và Java standard library. Interface **QuoteClients** phải có implementation Spring bean với connect/read/response timeout phù hợp.

Đặc biệt, các channel đồng bộ như **DirectChannel** thường chạy handler trong thread hiện tại. Ba recipient flow ở ví dụ **không được bảo đảm thực thi song song** chỉ vì dùng tên scatter-gather. Nếu adapter đầu tiên block, việc gửi sang adapter sau có thể bị trì hoãn; gather timeout không thay thế một **deadline từ đầu tới cuối request**.

### 4.1. Song song bằng ExecutorChannel có giới hạn

Nếu muốn gọi nhà cung cấp song song, có thể đặt **ExecutorChannel** trong mỗi recipient subflow trước khi gọi adapter:

~~~java
// Minh họa MỘT nhánh; các nhánh khác dùng cùng nguyên tắc.
.recipientFlow(f -> f
    .channel(c -> c.executor(providerExecutor))
    .handle((QuoteRequest request, Map<String, Object> headers) ->
        clients.quoteA(request)))
~~~

**providerExecutor** nên là executor có giới hạn thread, queue và chính sách từ chối rõ ràng. Nếu một nhánh chạy bất đồng bộ và phát sinh exception, lỗi thường đi vào **errorChannel** thay vì tự chuyển thành reply; phải chủ động xử lý để aggregator không chờ mãi một kết quả sẽ không đến. Khi dựng response mới từ async error, cần giữ các header trả lời và correlation cần thiết.

Nếu sử dụng kiểu xử lý **async/reactive** của phiên bản Spring Integration mới hơn, hành vi chờ kết quả có thể khác. Luôn kiểm tra version thư viện mà dự án thực sự dùng, nhất là khi dựa vào hành vi không chặn thread.

## 5. Kết quả từng phần: mô hình hóa lỗi thành dữ liệu

Một chiến lược thực dụng cho bài toán báo giá là để **mỗi nhánh luôn cố gắng tạo một reply có trạng thái**, kể cả khi đối tác bị lỗi mạng. Nhờ đó gatherer biết nguồn nào thành công, thất bại hoặc trả dữ liệu không hợp lệ, thay vì chỉ nhìn thấy một nhóm không đủ message.

~~~java
public enum SupplierStatus {
    OK, TIMEOUT, UNAVAILABLE, INVALID_RESPONSE
}

public record SupplierResult(
        String supplier,
        SupplierStatus status,
        BigDecimal totalVnd,       // chỉ có khi OK
        Instant validUntil,        // chỉ có khi OK
        String errorCode) {}
~~~

~~~java
SupplierResult callSupplierA(QuoteRequest request) {
    try {
        SupplierQuote quote = clients.quoteA(request);
        return new SupplierResult(
            "A", SupplierStatus.OK,
            quote.totalVnd(), quote.validUntil(), null);
    } catch (ResourceAccessException e) {
        return new SupplierResult(
            "A", SupplierStatus.UNAVAILABLE,
            null, null, "NETWORK_ERROR");
    } catch (HttpServerErrorException e) {
        return new SupplierResult(
            "A", SupplierStatus.UNAVAILABLE,
            null, null, "UPSTREAM_5XX");
    }
}
~~~

Trong triển khai thực tế, cần **phân loại riêng** connect timeout, read timeout, HTTP 429, 4xx vĩnh viễn, 5xx tạm thời và JSON sai schema. Không nuốt mọi **RuntimeException** thành dữ liệu hợp lệ vì làm vậy che giấu bug trong code. Không trả nguyên exception, token hay response body nhạy cảm về API công khai.

Khi gom **SupplierResult**, một object đầu ra tốt hơn chỉ trả báo giá:

~~~json
{
  "requestId": "d0e3e4d3-4bc8-4c52-bd08-6b3a18ab32c1",
  "status": "PARTIAL",
  "expected": 3,
  "received": 2,
  "bestQuote": {
    "supplier": "B",
    "totalVnd": 390000
  },
  "failures": [
    {
      "supplier": "C",
      "code": "NETWORK_ERROR"
    }
  ]
}
~~~

Ở đây **PARTIAL** có nghĩa rõ ràng: kết quả chỉ so sánh những đối tác có dữ liệu hợp lệ trong thời hạn. Nếu quyết định kinh doanh bắt buộc có C, không được dùng cùng response này để âm thầm coi quy trình đã hoàn tất.

## 6. Chọn release strategy theo cam kết nghiệp vụ

| Chính sách | Điều kiện release | Giới hạn |
| --- | --- | --- |
| **All-of-N** | Đủ N reply tương ứng sequence | Chịu tác động lớn bởi một nguồn chậm hoặc không trả lời |
| **K-of-N** | Có ít nhất K reply hợp lệ | Có thể bỏ lỡ kết quả tốt hơn từ nguồn đến muộn |
| **First-valid** | Đã có reply đầu tiên thỏa điều kiện | Kết quả phụ thuộc tốc độ, không bảo đảm tốt nhất toàn cục |
| **Priority sources** | Đủ những nguồn bắt buộc và đạt ngưỡng tối thiểu | Phải đánh dấu chính xác source đã hoàn tất |
| **Deadline partial** | Hết thời hạn nhóm, đã có ít nhất một kết quả dùng được | Cần cấu hình expiry/release partial và báo rõ thiếu nguồn |

Ví dụ **K=2** với một tập **SupplierResult**:

~~~java
// Pseudocode diễn tả tiêu chí nghiệp vụ, không phải flow đầy đủ.
boolean canRelease(MessageGroup group) {
    long usable = group.getMessages().stream()
        .map(m -> (SupplierResult) m.getPayload())
        .filter(r -> r.status() == SupplierStatus.OK)
        .count();
    return usable >= 2;
}
~~~

Trong một cấu hình **K-of-N**, phải xác định xử lý các tình huống:

- A và B thành công rất nhanh, C trả giá thấp hơn sau khi response đã được gửi.
- Chỉ A thành công, B và C lỗi; K=2 sẽ **không bao giờ đạt**, dù ba nhánh đều đã kết thúc.
- C gửi lại cùng một reply hai lần; đếm số message có thể tạo ảo giác đã đủ K.
- Recipient list động chỉ chọn A và C; K=2 là toàn bộ nguồn đã chọn, khác với 2/3 nguồn đăng ký.

Release strategy thường được kiểm tra khi reply mới đến. Nếu không có thêm reply, điều kiện K=2 không tự chuyển thành partial; cần một **timeout/expiry policy riêng**, có scheduler và cơ chế tạo kết quả hoặc báo lỗi phù hợp.

## 7. Những loại timeout khác nhau

| Timeout/giới hạn | Ví dụ | Tác động |
| --- | --- | --- |
| **Connect/read timeout của HTTP client** | 200 ms connect, 800 ms response | Ngăn từng adapter block không hạn |
| **Retry policy, circuit breaker, bulkhead** | Tối đa 2 lần gọi có backoff, 20 concurrent calls/nguồn | Giới hạn số lần và tài nguyên dành cho nguồn ngoài |
| **Gather timeout** | 1.500 ms | Giới hạn chờ output của aggregator tại ScatterGatherHandler |
| **Group timeout** | Expire group sau 1.200 ms | Quyết định khi nào dọn nhóm hoặc xử lý nhóm thiếu reply |
| **Gateway/HTTP deadline** | 2.000 ms | Giới hạn thời gian khách hàng chấp nhận chờ |

**Gather timeout KHÔNG đồng nghĩa group timeout.** Request có thể hết hạn chờ output trong ScatterGatherHandler nhưng **message group vẫn tồn tại** trong store, tiếp tục chờ nhánh cuối cùng. Tùy chính sách, có thể cấu hình **groupTimeout**, **sendPartialResultOnExpiry**, task scheduler, discard channel và dọn trạng thái nhóm. Không được chỉ đặt gatherTimeout rồi kỳ vọng framework tự trả danh sách partial và thu hồi mọi message còn lưu.

Với Spring Integration 6.5/7.x, tài liệu hiện hành mô tả giá trị mặc định của gather timeout là **30 giây**; nên chủ động cấu hình theo SLA thay vì phụ thuộc default hoặc hành vi của phiên bản cũ.

Ví dụ ngân sách thời gian **giả định** cho HTTP API 2.000 ms:

~~~text
HTTP request -------------------------------------------------- response
  0 ms                      1.500 ms                       2.000 ms
  |---- dispatch + group wait ---|---- serialize / mạng trả ---|
        HTTP calls có timeout             chừa 500 ms dự phòng
        và rate limit riêng
~~~

Ngân sách thực tế còn phải trừ thời gian vào queue, xác thực, tạo request, lấy cache/DB, serialization và thời gian network. Với nhánh đồng bộ, gather timeout có thể **không giới hạn toàn bộ thời gian fan-out**, bởi quá trình gửi tới recipient cũng tiêu tốn thời gian. Cần đo end-to-end deadline và cân nhắc dừng hoặc bỏ qua công việc sau khi caller đã hết hạn.

Chính sách **all-of-N** thường chịu độ trễ gần bằng **nhánh chậm nhất** (nếu thật sự gọi song song). Càng nhiều hệ thống, xác suất có một nhánh ở đuôi độ trễ càng cao. Song song giảm thời gian so với gọi tuần tự trong trường hợp phù hợp, nhưng không làm các upstream trở nên nhanh hoặc đáng tin cậy hơn.

## 8. MessageStore, late reply, duplicate và restart

**Aggregator là thành phần có trạng thái**, khác với filter/router thông thường. Nó phải ghi nhớ các reply chưa đủ điều kiện release. **SimpleMessageStore** trong bộ nhớ thích hợp cho flow nhỏ, ngắn hạn; khi process restart, state nhóm in-memory sẽ biến mất.

Trong luồng yêu cầu phục hồi sau sự cố, có thể xem xét **MessageGroupStore bền vững**, cơ chế locking giữa nhiều instance và metadata group expiry. Tuy nhiên, lưu nhóm vào database **không khiến HTTP request thread đã chết tự sống lại**. Với công việc dài hoặc cần replay, nên lưu job state và dùng callback/polling.

Những quyết định quan trọng:

- **Late reply:** sau khi release hoặc caller timeout, reply tới muộn sẽ bị discard, đưa vào audit hay tạo bản kết quả mới? Một HTTP response đã gửi không thể bị thay thế lặng lẽ.
- **Duplicate reply:** cần khóa nhận diện ít nhất theo requestId + supplierId (và attemptId nếu retry được xem là một phiên bản riêng). Đừng xem **sequenceNumber** đơn thuần là cơ chế idempotency nghiệp vụ.
- **Completed group metadata:** xóa quá sớm có thể cho phép reply trễ hình thành nhóm mới; giữ mãi gây tăng RAM/dung lượng. Phải có retention và cleanup.
- **Incomplete group:** nếu không có expiration và message cuối cùng không bao giờ đến, nhóm có thể tồn tại rất lâu, nhất là ở nguồn message rate lớn.
- **Horizontal scaling:** reply của cùng correlationId đến các instance khác nhau không tự tập hợp trong các store in-memory riêng biệt. Cần routing cùng key về một instance hoặc store/locking phù hợp.
- **Message contract:** nếu chuyển đổi kiểu payload, nên giữ correlation, sequence, reply headers. Tạo message mới và làm mất các header này có thể khiến gatherer không thể hoàn tất.

Cần hiểu hành vi **expireGroupsUponCompletion**, **sendPartialResultOnExpiry**, **discardChannel** và chính sách dọn group trước khi chỉnh; chúng không chỉ ảnh hưởng bộ nhớ mà còn quyết định một reply trễ hoặc reply trùng sẽ được xử lý ra sao.

## 9. Phân loại lỗi và cách phối hợp

| Tình huống | Hệ quả có thể xảy ra | Chính sách gợi ý |
| --- | --- | --- |
| A trả HTTP 503 | Một nhánh không có báo giá | Convert thành **UNAVAILABLE** nếu cho phép partial; circuit breaker |
| B trả 429 | Retry đồng loạt gây quá tải | Tôn trọng quota/Retry-After, backoff có jitter |
| C read timeout | Thiếu reply, all-of-N không release | Timeout theo nhánh, deadline và group expiry |
| Nhánh đồng bộ ném exception | Exception có thể lan tới caller, khiến nhánh khác xử lý vô ích | Catch đúng loại lỗi hoặc dùng advice ở nhánh |
| Nhánh bất đồng bộ ném exception | Error vào error channel; aggregator vẫn thiếu reply | Cấu hình **errorChannel** và tạo reply lỗi có cùng correlation/reply headers |
| Một nguồn trả sai schema | Cast/transform lỗi hoặc tính giá sai | Validate DTO trước khi đưa vào gather |
| Giá khác currency/tax | So sánh không cùng điều kiện | Chuẩn hóa và kiểm tra hợp đồng trước khi chọn min |
| Nhánh gửi reply trùng | Có thể đếm sai số reply hợp lệ | Dedupe theo source/request và kiểm thử concurrency |
| Kết quả đến sau khi caller timeout | Reply không còn người nhận, group bị giữ | Late-reply policy, discard và cleanup có metric |

Trong trường hợp nhánh chạy qua **ExecutorChannel**, lỗi thường được gửi đến error channel qua cơ chế xử lý thông điệp bất đồng bộ. Nếu muốn đổi lỗi thành reply cho gatherer, phản hồi phải **bảo toàn các header cần thiết** (replyChannel, correlation/sequence và các header nội bộ liên quan) từ failed message. Nếu không, request dễ bị treo và chỉ biểu hiện như timeout. Không nên log toàn bộ payload hoặc exception chứa token, PII và response body từ đối tác.

## 10. Giới hạn quan trọng nhất: không có giao dịch phân tán

Scatter-gather **phối hợp thông điệp**; nó không tự biến nhiều HTTP call, nhiều database và broker thành **một giao dịch ACID**. Xét bài toán khác: gửi lệnh **giữ hàng** đến ba kho thay vì chỉ lấy báo giá.

~~~mermaid
sequenceDiagram
  participant API as Booking API
  participant A as Warehouse A
  participant B as Warehouse B
  participant C as Warehouse C
  API->>A: Reserve(order-1)
  A-->>API: COMMITTED
  API->>B: Reserve(order-1)
  B-->>API: COMMITTED
  API->>C: Reserve(order-1)
  Note over C: Có thể đã commit
  C--xAPI: Timeout / lost reply
  Note over API,C: Gather chưa đủ kết quả, A và B vẫn đã giữ hàng
~~~

Một lời gọi **@Transactional** ở Spring Boot chỉ bảo vệ các tài nguyên do transaction manager tương ứng quản lý, ví dụ một database địa phương. Nó không rollback các đơn giữ hàng đã commit trên A/B khi C timeout. Hơn nữa, **timeout không chứng minh tác vụ thất bại**: C có thể đã commit, nhưng phản hồi bị mất trên đường về. Retry bừa có thể giữ hàng hai lần.

Với các lệnh có side effect, nên ưu tiên:

1. **Idempotency key** xuyên suốt từng lệnh và API tra cứu trạng thái khi kết quả không chắc chắn.
2. **Saga/compensation** cho các bước đã commit: ví dụ hủy phần giữ hàng A/B nếu luồng quyết định thất bại.
3. **Bền vững trạng thái quy trình** bằng DB/workflow engine cho việc kéo dài nhiều giây, phút hoặc cần retry sau restart.
4. **Transactional Outbox** khi cập nhật DB rồi cần phát message broker; **Inbox/idempotent consumer** khi message có thể giao lại.
5. **Reconciliation** để đối chiếu trạng thái của bên gọi và các hệ thống đích.

Một phép gather trả **FAILED** không đảo ngược mọi tác dụng ở các hệ thống đã xử lý. Nên phân biệt ba bài toán: **đọc từ nhiều nguồn để tổng hợp**, **gửi nhiều lệnh cập nhật**, và **điều phối quy trình dài**. Scatter-gather đặc biệt phù hợp bài toán đầu tiên; hai bài toán còn lại cần trạng thái và hợp đồng phục hồi riêng.

### Khi đi qua HTTP, broker hoặc process khác

Khi dùng Spring Integration với RabbitMQ, Kafka hoặc một adapter HTTP bên ngoài, đường reply không còn đơn thuần là message channel trong một JVM. **replyChannel** nội bộ có thể là một object không thể tùy tiện tuần tự hóa rồi gửi qua network. Phải thiết kế:

- Correlation ID/request ID được chuyển qua header mà transport hỗ trợ hoặc trong payload đã version hóa.
- Reply routing theo gateway của transport hoặc reply queue/topic và handler riêng.
- Deadline, TTL, dedup, retry và xử lý **orphan reply** sau khi caller kết thúc.
- Chính sách ack/commit và idempotency khi broker có thể giao lại message.
- Với tác vụ kéo dài, trả **HTTP 202 Accepted + jobId**, lưu state và dùng polling hoặc webhook, thay vì giữ HTTP request chờ vô hạn.

Không nên giả định một **AMQP outbound adapter** tự động trở thành request-reply gateway. Phải chọn đúng gateway/adapter và xác minh hợp đồng reply theo loại tích hợp thực tế.

## 11. Tải hệ thống và tác động của fan-out

Nếu hệ thống nhận **R** request/giây và mỗi yêu cầu gọi **N** nguồn, tải phía ngoài xấp xỉ:

\[
\text{Outbound requests per second} \approx R \times N
\]

Ví dụ **100 request/giây × 4 supplier = khoảng 400 HTTP calls/giây**, chưa kể retry. Bốn supplier đều chậm có thể tiêu thụ nhiều thread hơn một luồng gọi tuần tự, dù độ trễ khách hàng thấp hơn trong trường hợp nguồn phản hồi tốt.

Để không khuếch đại lỗi:

- **Bounded concurrency:** thread pool, HTTP connection pool, semaphore và queue có giới hạn; có cơ chế từ chối khi quá tải.
- **Bulkhead/circuit breaker:** cô lập từng đối tác, ngăn một nguồn chậm làm nghẽn toàn bộ dịch vụ.
- **Rate limit và retry có backoff:** tôn trọng quota, giới hạn số lần thử, không retry mọi HTTP 4xx.
- **Deadline propagation:** không tạo lời gọi mới khi ngân sách của request gần cạn.
- **Caching có chính sách freshness:** giảm tải các tra cứu tương đối tĩnh, nhưng không dùng giá cũ nếu nghiệp vụ cần giá thời gian thực.
- **Giới hạn recipient động:** một lỗi cấu hình router không được biến một yêu cầu thành hàng trăm lời gọi ngoài dự kiến.

Việc chạy song song làm tổng thời gian all-of-N tiến gần **nhánh chậm nhất**; thêm nhiều nguồn làm tăng xác suất gặp tail latency. Cần đo **p95/p99 end-to-end**, thay vì chỉ nhìn độ trễ trung bình của từng HTTP client.

## 12. Quan sát và kiểm thử những bất biến quan trọng

### 12.1. Logging, tracing và metrics

| Cấp độ | Dữ liệu cần đo |
| --- | --- |
| Gateway | requestId, traceId, deadline, status cuối, tổng thời gian |
| Scatter | correlationId, số recipient thực tế, thứ tự, kết quả dispatch |
| HTTP client | tên nguồn, latency, HTTP status, retry count, circuit state |
| Gather | group size, expected size, số OK, lý do release, age, timeout count |
| Vận hành | group chưa hoàn tất, dung lượng MessageStore, late/discarded replies, executor saturation |

Log/trace dùng requestId và correlationId để nối các bước. Metric nên gắn nhãn theo tên supplier và loại lỗi; **không** dùng requestId làm label Prometheus vì cardinality sẽ tăng không giới hạn. Cảnh báo khi tỷ lệ partial tăng, số group timeout tăng, backlog group không giảm hoặc thread pool đến ngưỡng.

### 12.2. Ma trận kiểm thử

| Ca | Kết quả mong muốn |
| --- | --- |
| A/B/C đều thành công | Đúng một response, so sánh đúng đơn vị và hạn hiệu lực |
| Một supplier bị 503 | Chính sách partial/error rõ ràng, không treo group |
| K=2, chỉ A/B thành công | Có thể release sớm nếu business cho phép |
| K=2, chỉ A thành công | Sau deadline có partial/error, không giữ state vô hạn |
| Một source trả reply trùng | Không tính trùng thành đủ quorum hoặc side effect hai lần |
| Hai request chạy đồng thời | Không trộn reply khác correlationId |
| Recipient router chỉ chọn hai nguồn | sequenceSize và release dựa trên hai nguồn thực tế |
| Async handler ném exception | errorChannel/fallback hoạt động, caller không treo |
| Reply đến muộn | Discard/audit đúng chính sách, không trả response HTTP thứ hai |
| Restart giữa lúc gather | Hành vi mất/khôi phục group được kiểm soát và quan sát |
| Tăng tải, supplier chậm | Giới hạn pool, backpressure và deadline có hiệu lực |

Có thể dùng **Spring Integration Test** để kiểm thử message flow, **MockWebServer/WireMock** cho HTTP partner, và **Testcontainers** nếu quy trình liên quan database, Redis hoặc RabbitMQ. Với timing, dùng công cụ kiểm soát đồng bộ thay vì nhiều lời gọi sleep ngẫu nhiên làm bài test không ổn định.

Ví dụ tiêu chí chấp nhận của một tính năng: **với ba đối tác, có ít nhất hai giá hợp lệ trong 1.500 ms thì trả PARTIAL hoặc COMPLETE theo trạng thái nguồn; reply muộn không thay đổi response đã gửi; group hết hạn được dọn theo chính sách; không trộn reply của hai request khác nhau**. Đây là yêu cầu cần được hiện thực bằng release/expiry và output contract rõ ràng, **không phải hành vi mặc định** của ví dụ all-of-N ở mục 4.

## 13. Checklist trước khi triển khai production

- [ ] Xác định **N/K**, nguồn bắt buộc, quy tắc release và phản hồi khi không đủ dữ liệu.
- [ ] Có contract request/reply thống nhất: requestId, supplierId, schemaVersion, đơn vị và hạn hiệu lực.
- [ ] Kiểm tra **correlationId**, sequenceSize, replyChannel và errorChannel xuyên mọi nhánh.
- [ ] Có timeout riêng từng adapter, gather timeout, group expiry/cleanup và deadline của API.
- [ ] Có giới hạn executor/connection pool, rate limit, circuit breaker và retry có backoff.
- [ ] Xử lý partial, late reply, duplicate, restart và trạng thái MessageStore có quan sát.
- [ ] Nếu nhánh gây side effect, có idempotency và cơ chế bù trừ/đối soát.
- [ ] Kiểm thử concurrent requests, partial failure, timeout, quá tải và đường phục hồi.

**Nguyên tắc nhớ:** **Scatter-gather là cơ chế điều phối câu hỏi và tổng hợp câu trả lời.** Nó không bảo đảm các hệ thống ngoài cùng commit, không có exactly-once end-to-end và không tự quyết định thế nào là đủ kết quả. Thiết kế đáng tin cậy bắt đầu từ **hợp đồng dữ liệu, correlation, release policy, deadline, failure policy và chiến lược phục hồi**.

### Tài liệu đối chiếu

- [Spring Integration Reference — Scatter-Gather](https://docs.spring.io/spring-integration/reference/scatter-gather.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
