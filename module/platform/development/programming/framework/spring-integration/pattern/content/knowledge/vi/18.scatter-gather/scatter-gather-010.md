# Giới hạn số nhánh và tài nguyên

## 1. Tại sao Scatter-Gather cần giới hạn?

Một hệ thống định giá đơn hàng nhận `QuoteRequest` và đồng thời hỏi ba nguồn:

1. **Inventory**: còn hàng hay không?
2. **Pricing**: giá hiện hành và mức chiết khấu.
3. **Shipping**: phí và thời gian giao hàng.

Sau đó hệ thống **gather** ba kết quả thành `QuoteResult`. Nếu mỗi yêu cầu tạo ba nhánh thì 200 yêu cầu/giây có thể tạo **600 tác vụ nhánh/giây**. Khi Pricing chậm từ 100 ms lên 2 giây, số tác vụ đang chờ tăng mạnh; nếu hệ thống dùng queue không giới hạn và giữ message group chờ vô hạn, memory, thread pool và response time có thể suy giảm dù logic định tuyến vẫn đúng.

~~~mermaid
flowchart LR
    Q["QuoteRequest"] --> SC{"Scatter"}
    SC --> A["Inventory"]
    SC --> B["Pricing"]
    SC --> C["Shipping"]
    A --> G{"Gather"}
    B --> G
    C --> G
    G --> R["QuoteResult / Gateway reply"]
~~~

**Giới hạn số nhánh và tài nguyên** là thiết kế **fan-out có kiểm soát**: mỗi yêu cầu chỉ được phát tới những nhánh hợp lệ, số công việc đang thực thi và chờ đợi được giới hạn, và Gather có deadline/cleanup rõ ràng. Mục đích không chỉ là tránh lỗi `OutOfMemoryError` mà còn bảo đảm một nhánh chậm hoặc một tenant gửi nhiều request **không làm nghẽn toàn bộ hệ thống**.

Bài thuộc chương **Scatter gather** của module **SPRING_INTEGRATION_PATTERN**, phục vụ mục tiêu học triển khai **Enterprise Integration Patterns** với Spring Integration: xây dựng các luồng message ít phụ thuộc, dễ mở rộng; thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát các nhánh xử lý.

Sau bài học, bạn có thể phân biệt số nhánh và độ song song, lập kế hoạch tài nguyên cho Scatter-Gather, cấu hình luồng theo hướng bounded, đưa lỗi/thời hạn vào hợp đồng Gather, hạn chế retry và duplicate, và kiểm thử các trường hợp quá tải, thiếu nhánh hoặc trả kết quả trễ.

## 2. Scatter-Gather có hai phần và hai loại chi phí

**Scatter** phát một yêu cầu tới nhiều người nhận. **Gather** ghép các phản hồi liên quan theo correlation và release strategy. Trong Spring Integration, pattern này có thành phần `ScatterGatherHandler` với một nhánh phát tán (thường dựa trên `RecipientListRouter` hoặc `PublishSubscribeChannel`) và một nhánh thu thập (Aggregator).

| Pha | Đang tiêu thụ gì? | Rủi ro khi không giới hạn |
|---|---|---|
| Lập danh sách recipients | Cấu hình route, logic lựa chọn | Fan-out bị đẩy lên quá nhiều hoặc bị thao túng |
| Scatter | Dispatch, serialization, kết nối, thread | Một request tạo bão message hoặc quá nhiều tác vụ |
| Branch execution | CPU, DB pool, HTTP connection, broker consumer | Chậm, timeout, rate limit, tranh chấp tài nguyên |
| Gather | Message group, correlation metadata, memory/store | Giữ nhiều group chưa hoàn tất, rò tài nguyên |
| Reply | Gateway thread, deadline, output queue | Caller timeout, kết quả đến muộn, phát hai lần |
| Retry/recovery | Scheduler, queue, DLQ, state store | Khuếch đại tải và tạo duplicate |

**Giới hạn một phía không đủ**: cho phép tối đa bốn recipient trên mỗi request vẫn có thể tạo hàng chục nghìn tác vụ nếu ingress mở vô hạn; giới hạn thread pool vẫn có thể gây `OutOfMemoryError` nếu queue/gather store không giới hạn; đặt Gateway timeout vẫn có thể để các worker tiếp tục gọi mạng và tạo side effect.

## 3. Phân biệt fan-out, concurrency, queue và group đang chờ

Bốn đại lượng thường bị dùng lẫn:

| Đại lượng | Ký hiệu | Ý nghĩa |
|---|---:|---|
| **Fan-out** | `F` | Số nhánh được chọn cho *một* yêu cầu |
| **Concurrency** | `C` | Số tác vụ nhánh đang chạy cùng lúc |
| **Queued work** | `Q` | Số tác vụ đã chấp nhận nhưng chưa chạy |
| **Pending groups** | `G` | Số lần Gather còn chờ kết quả |

Ví dụ:

~~~text
1 request → F = 3 nhánh
10 requests đồng thời → tối đa 30 công việc nhánh đang chạy hoặc xếp hàng
Thread pool có 8 workers → C thực tế bị giới hạn khoảng 8 tác vụ
Queue 100 tasks → Q tối đa 100 nếu đã thiết kế bounded
10 requests chưa đủ replies → G = 10 pending groups
~~~

Thêm thread không làm tăng giới hạn kết nối database. Giảm số nhánh có thể giảm tác vụ nhưng không thay thế timeout. Còn giới hạn `G` cần được đặt riêng nếu một số nhánh không bao giờ gửi reply.

**Tách “đã nhận request” và “đã hoàn tất request”**: request được chấp nhận vào channel không chứng minh đã chạy xong ba nhánh; mỗi completion phải được đo theo logic của Gather, không theo giá trị Boolean của `send()`.

## 4. Ba kiến trúc khác nhau: đồng bộ, song song và qua broker

| Kiểu triển khai | Đặc điểm | Giới hạn cần ưu tiên |
|---|---|---|
| **Scatter đồng bộ trong JVM** | Nhánh có thể được gọi nối tiếp trên cùng thread | Tổng thời gian blocking, deadline Gateway, branch timeout |
| **Scatter với Executor/Queue** | Nhánh chạy trên worker threads | Bounded executor, queue, admission control, error path |
| **Scatter qua broker/các service** | Mỗi nhánh đi qua transport độc lập | Broker quotas, consumer concurrency, in-flight request, reply correlation, durable state |

Đừng hiểu chữ **scatter** là “tự động chạy song song”. `PublishSubscribeChannel` không có executor có thể gọi subscriber đồng bộ. `RecipientListRouter` cũng không tự biến mọi handler thành job song song. Muốn concurrency phải cấu hình ranh giới thực thi (executor, queue hoặc các consumer/service độc lập).

Ngược lại, **đặt executor không giải quyết mọi vấn đề**: nếu chọn 20 recipients, executor có 8 threads và queue 1.000, request vẫn có thể gửi 20 task vào backlog. Hệ thống phải quyết định nhận thêm hay từ chối yêu cầu mới khi không đủ capacity.

## 5. Nguyên tắc giới hạn fan-out trước khi gửi

**Không nhận một danh sách channel tùy ý từ payload hoặc header bên ngoài**. Ứng dụng nên chọn recipient từ một tập đã cấu hình, có version và được kiểm thử:

~~~text
Nhánh được phép:
  INVENTORY → quote.inventory
  PRICING   → quote.pricing
  SHIPPING  → quote.shipping
  FRAUD     → quote.fraud (chỉ đơn rủi ro cao)

Đơn bình thường: 3 nhánh
Đơn rủi ro cao:  4 nhánh
Giới hạn cứng:   không quá 4 nhánh
~~~

**Tập nhánh bắt buộc** không được tùy ý loại để đáp ứng giới hạn tải nếu điều đó bỏ qua kiểm tra an toàn. Ví dụ, nếu đánh giá gian lận bắt buộc cho đơn rủi ro cao, không được âm thầm bỏ nhánh `FRAUD` vì queue của nó đầy rồi báo thành công.

Một kế hoạch phân tán (*scatter plan*) nên được tạo **một lần cho request**, mang `requestId`, tenant scope, danh sách nhánh dự kiến và deadline. Gather phải biết **tập nhánh này** để xác định kết quả nào là đủ; không được mặc định số recipients là một hằng số khi nhánh được bật/tắt có điều kiện.

## 6. Java: tạo branch plan có giới hạn và không nhận tên channel tự do

Mô hình dữ liệu tối giản (Java 17+):

~~~java
enum QuoteBranch {
    INVENTORY, PRICING, SHIPPING, FRAUD
}

record QuoteRequest(
    String requestId,
    String tenantId,
    boolean highRisk,
    int lineCount
) {}

record ScatterPlan(
    String requestId,
    String tenantId,
    Set<QuoteBranch> required,
    Instant deadline
) {
    ScatterPlan {
        required = Set.copyOf(required);
    }
}
~~~

Tạo kế hoạch từ quy tắc domain:

~~~java
final class ScatterPlanner {
    static final int MAX_BRANCHES = 4;

    ScatterPlan plan(QuoteRequest request,
                     Instant now,
                     Duration totalBudget) {
        if (request.requestId() == null
                || request.requestId().isBlank()
                || request.tenantId() == null
                || request.tenantId().isBlank()) {
            throw new IllegalArgumentException("MISSING_IDENTITY");
        }
        if (request.lineCount() <= 0
                || request.lineCount() > 500) {
            throw new IllegalArgumentException("INVALID_LINE_COUNT");
        }
        if (totalBudget.isZero() || totalBudget.isNegative()) {
            throw new IllegalArgumentException("INVALID_BUDGET");
        }

        EnumSet<QuoteBranch> branches = EnumSet.of(
            QuoteBranch.INVENTORY,
            QuoteBranch.PRICING,
            QuoteBranch.SHIPPING);
        if (request.highRisk()) {
            branches.add(QuoteBranch.FRAUD);
        }
        if (branches.size() > MAX_BRANCHES) {
            throw new IllegalStateException("TOO_MANY_BRANCHES");
        }
        return new ScatterPlan(
            request.requestId(),
            request.tenantId(),
            branches,
            now.plus(totalBudget));
    }
}
~~~

Điểm cần chú ý:

- `EnumSet` và `MAX_BRANCHES` bảo đảm không có hơn bốn nhánh trong **một plan**.
- `Set.copyOf` tạo snapshot, ngăn caller chỉnh lại danh sách sau khi đã phát request.
- `requestId` phải được cấp ổn định ở boundary đáng tin và có thể kết hợp với attempt/revision khi cần.
- `tenantId` chỉ có ý nghĩa phân quyền nếu đã được xác thực; đừng tin tenant do client tự khai.
- `highRisk` là kết quả của một bước đánh giá tin cậy. Nếu client tự được đặt `highRisk=false`, quy tắc bỏ nhánh FRAUD sẽ không an toàn.
- `lineCount` có limit để chặn một request phình to về kích thước độc lập với fan-out.

**Đây là code lập kế hoạch ứng dụng**, không phải API do Spring Integration tự cung cấp. Bước tiếp theo cần ánh xạ mỗi enum tới đúng channel đã được tạo trong cấu hình, không xây tên bean từ raw string do client gửi.

## 7. Fan-out dựa trên nội dung nhưng không được nổ theo số item

Một lỗi phổ biến là đặt Scatter-Gather **bên trong Splitter** mà không tính số phần tử:

~~~mermaid
flowchart TD
    IN["Order: 500 lines"] --> S["Splitter: 500 line messages"]
    S --> SC["Scatter mỗi line tới 4 services"]
    SC --> OUT["Tối đa 2.000 branch tasks"]
~~~

Một request bên ngoài có thể tạo:

\[
F_{\mathrm{effective}}
= N_{\mathrm{items}}\times F_{\mathrm{perItem}}
\]

Với 500 item và 4 nhánh trên mỗi item, tải nội bộ **2.000 tác vụ** dù fan-out “mỗi message” vẫn không quá bốn.

Để tránh khuếch đại ngoài ý muốn:

1. Đặt giới hạn **số item** và **độ sâu fan-out**.
2. Nếu API hỗ trợ bulk query, gom `N` item thành chunk và tra cứu cả chunk một lần.
3. Dùng shared cache hoặc batch lookup, có TTL/version và tenant scope.
4. Tính **tổng số tác vụ dự kiến của request**, không chỉ số recipients trực tiếp.
5. Chặn recursion hoặc loop routing không có điều kiện dừng.

**Một limit cục bộ không chứng minh toàn bộ flow bounded** khi còn Splitter, Nested Router, retry và fan-out nhiều tầng.

## 8. Ước tính concurrency bằng throughput và latency

Một mô hình định hướng dung lượng theo Little's Law:

\[
C_{\mathrm{inflight}}
\approx \lambda_{\mathrm{requests}}
\times F_{\mathrm{average}}
\times W_{\mathrm{branch}}
\]

Trong đó `λ_requests` là số request/giây, `F_average` là số nhánh bình quân/request, `W_branch` là thời gian lưu trú trung bình của một tác vụ nhánh (giây), và `C_inflight` là số tác vụ đang xử lý/chờ phản hồi trung bình.

Ví dụ **100 request/giây**, mỗi request có **4 nhánh**, thời gian nhánh trung bình **0,25 giây**:

\[
C_{\mathrm{inflight}}\approx100\times4\times0.25=100
\]

Đó là **ước tính trung bình**, không phải đề xuất cấp chính xác 100 threads. Hệ thống phải xét p95/p99, burst, contention, loại tài nguyên và queue delay. Các nhánh I/O-bound có thể chờ rất lâu dù ít CPU; nhánh CPU-bound cần giới hạn phù hợp số cores.

Nếu latency nhánh tăng gấp tám lần mà traffic giữ nguyên, số tác vụ pending có thể tăng gần tương ứng trước khi backpressure hoặc timeout phát huy tác dụng. Vì vậy **timeout và admission control là một phần của capacity planning**, không phải tính năng phụ.

## 9. Đặt giới hạn đồng thời tại đúng tài nguyên

Một hệ thống có thể cần nhiều **bulkhead**:

| Tài nguyên | Giới hạn mẫu | Rủi ro khi dùng chung không phân loại |
|---|---|---|
| Inventory HTTP client | 40 in-flight calls | Pricing chậm làm hết connection pool |
| Pricing service | 20 in-flight calls | Request giá dồn backlog và timeout |
| Shipping provider | 12 in-flight calls | Bị rate limit từ nhà cung cấp |
| Fraud service | 8 in-flight calls | Nhánh rủi ro cao đói tài nguyên |
| Per-tenant requests | 10 active scatter plans | Một tenant chiếm hết capacity của toàn hệ |
| Global scatter operations | 100 pending plans | Memory/store tăng do group chờ |

Các con số là **minh họa**, không phải khuyến nghị áp dụng mọi hệ thống. Chọn limit theo phép đo thật và SLO.

**Không chỉ có một Semaphore toàn cục** nếu các nhánh có mức ưu tiên khác nhau. Một bulkhead riêng cho Pricing làm Pricing chậm không nhất thiết phải ăn hết slot của Inventory. Tuy vậy cũng cần một **trần toàn cục**, tránh số lượng bulkhead độc lập cộng lại lớn hơn sức chứa thực tế của JVM/DB/network.

Nếu dùng shared thread pool cho tất cả branches, một nhánh blocking chậm có thể chiếm đa số workers. Hãy cân nhắc tách executor hoặc dùng I/O client bất đồng bộ với giới hạn kết nối và in-flight phù hợp.

## 10. Executor và queue: chỉ tăng threads không phải giải pháp

Một `ExecutorChannel` hoặc `PublishSubscribeChannel` có executor có thể đưa dispatch ra worker threads. Nhưng **giới hạn threads không đồng nghĩa giới hạn backlog**:

~~~text
Producer: tạo 500 tasks/giây
Workers: hoàn tất 300 tasks/giây
Queue không giới hạn:
  backlog tăng khoảng 200 tasks/giây
  sau 60 giây: khoảng 12.000 tasks chưa chạy
~~~

Trong thời gian backlog tăng, các task có thể chứa payload lớn, headers và reference tới object khác. Cùng lúc Gather giữ nhiều group chờ reply: tiêu thụ bộ nhớ tăng từ **cả queue lẫn group store**.

Một executor bounded mẫu:

~~~java
@Bean(destroyMethod = "shutdown")
ThreadPoolExecutor branchExecutor() {
    return new ThreadPoolExecutor(
        8,                        // core threads
        8,                        // maximum threads
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(128),
        new ThreadPoolExecutor.AbortPolicy());
}
~~~

Khi đủ 8 workers và 128 slots queue, executor có thể **từ chối task mới** bằng `RejectedExecutionException`. Đây là **tín hiệu capacity**, không nên bắt exception rồi tự âm thầm chạy không giới hạn trên thread khác.

**Cần phân biệt:** trần executor ở ví dụ giới hạn **tác vụ do executor này nhận**, không giới hạn toàn bộ tác vụ trong Kafka consumers, HTTP client async hoặc scheduler khác. Khi dùng các adapter riêng, mỗi ranh giới cần chính sách capacity nhất quán.

## 11. Java: admission control phải giữ permit đến khi task thật sự kết thúc

Một Semaphore giúp giới hạn tổng số branch operations được chấp nhận tại một thời điểm. Ví dụ đặt permit **trước khi submit** và trả lại khi worker hoàn tất:

~~~java
record BranchOutcome(
    String requestId,
    QuoteBranch branch,
    boolean success,
    String value,
    String reasonCode
) {
    static BranchOutcome unavailable(
            String id, QuoteBranch branch, String reason) {
        return new BranchOutcome(
            id, branch, false, null, reason);
    }
}

final class BoundedBranchDispatcher {
    private final Semaphore permits = new Semaphore(64);
    private final Executor executor;

    BoundedBranchDispatcher(Executor executor) {
        this.executor = executor;
    }

    CompletableFuture<BranchOutcome> dispatch(
            QuoteRequest request,
            QuoteBranch branch,
            Function<QuoteRequest, BranchOutcome> operation) {
        CompletableFuture<BranchOutcome> result =
            new CompletableFuture<>();

        if (!permits.tryAcquire()) {
            result.complete(BranchOutcome.unavailable(
                request.requestId(), branch, "CAPACITY_EXCEEDED"));
            return result;
        }

        try {
            executor.execute(() -> {
                try {
                    result.complete(operation.apply(request));
                } catch (Exception failure) {
                    result.completeExceptionally(failure);
                } finally {
                    permits.release();
                }
            });
        } catch (RejectedExecutionException rejected) {
            permits.release();
            result.complete(BranchOutcome.unavailable(
                request.requestId(), branch, "EXECUTOR_REJECTED"));
        }
        return result;
    }
}
~~~

**Điều mã này minh họa:** khi không có permit hoặc queue executor đầy, coordinator vẫn nhận một **outcome có cấu trúc** để đưa vào Gather hoặc quyết định fail toàn request. Nếu không có outcome, Gather có thể đợi một branch chưa từng được submit.

**Các ranh giới cần hoàn thiện khi đưa vào production:**

- Đoạn code dùng một semaphore minh họa; nên có limit **per-service/per-tenant/global** tùy hệ thống.
- `CompletableFuture` ở đây là **ứng dụng thuần Java**, không phải API `ScatterGatherHandler`. Cần bridge đúng sang message reply và correlation contract.
- Permit được nhả trong worker `finally`, **không nhả chỉ vì caller cancel future** khi task nền vẫn chạy.
- Cần quy tắc xử lý lỗi nghiêm trọng ở thread executor và không dùng result `CAPACITY_EXCEEDED` như một giá trị nghiệp vụ thành công.
- Nếu một operation có thể block vô hạn, semaphore vẫn bị giữ vô hạn: **timeout ở HTTP/DB client** và watchdog vận hành là bắt buộc.
- Cần xác minh executor reject không chạy task trước khi từ chối; hành vi này đúng với mẫu `ThreadPoolExecutor.AbortPolicy` đang minh họa.

Không dùng `Thread.sleep` cố định như một biện pháp backpressure. Nó giữ thread nhưng không đảm bảo giảm lượng công việc đã được chấp nhận hay giải phóng memory.

## 12. Admission control ở cấp **cả request** để tránh phát nửa chừng

Giả sử một quote cần đúng ba nhánh bắt buộc. Nếu coordinator gửi thành công Inventory và Pricing, sau đó mới phát hiện không còn capacity cho Shipping, nó phải xử lý **một kế hoạch đã được thực thi một phần**.

Có hai chiến lược:

| Chiến lược | Ưu điểm | Chi phí |
|---|---|---|
| **Reserve budget cho cả plan** trước khi Scatter | Tránh gửi một phần rồi mới từ chối vì quota | Có thể giữ capacity cho một branch chưa chạy |
| **Admit từng branch** và trả failure outcome nếu không còn chỗ | Tận dụng capacity linh hoạt | Gather phải hiểu partial dispatch và kết quả thất bại |

Nếu yêu cầu *all-or-nothing*, nên **kiểm tra capacity trước khi phát** và duy trì trạng thái plan. Nếu nhận một phần là hợp lệ, mỗi nhánh không được gửi phải có trạng thái `SKIPPED_CAPACITY` hoặc `FAILED_CAPACITY` chính thức, không bị “mất tích”.

Ví dụ pseudo workflow:

~~~text
Plan = [INVENTORY, PRICING, SHIPPING]

admit plan? NO
  → reject/429/503 theo API contract hoặc queue có giới hạn
  → không tạo pending gather group vô thời hạn

admit plan? YES
  → persist/record expected branches + deadline
  → scatter
  → gather mỗi branch outcome
  → release theo chính sách
~~~

**Không được đồng nhất 429 với 503 trong mọi trường hợp:** mã HTTP phụ thuộc lý do và hợp đồng công khai. Với message broker, overload có thể dẫn tới nack/requeue/DLQ và cần policy khác; cùng một `RejectedExecutionException` trong Java không tự quyết định cách broker ack.

## 13. Chọn recipient theo policy, không theo quyền tùy ý của producer

Một input nguy hiểm:

~~~json
{
  "requestId": "Q-101",
  "recipients": [
    "quote.inventory",
    "quote.pricing",
    "admin.internalChannel"
  ]
}
~~~

Không cho client điều khiển danh sách tên bean/channel nội bộ trực tiếp. Một API có thể cho phép **chọn tính năng** như “có cần tính shipping không”, nhưng quyết định cuối cùng nên dựa trên:

- Quyền của caller và tenant, đã xác thực.
- Business invariant: những nhánh bắt buộc không thể bị tắt tùy ý.
- Allowlists: channel/recipient cố định hoặc được đăng ký qua control plane có phê duyệt.
- Max fan-out và độ sâu fan-out theo một request.
- Giới hạn per-tenant và rate limit.
- Version của plan để khi retry không tự gửi sang tập nhánh khác.

**Scatter plan là một phần của hợp đồng correlation.** Khi thay nhánh động, Gather phải dùng **tập expected recipients thực tế tại thời điểm phát**, thay vì lấy tập recipients mới nhất ở một phiên bản cấu hình đã thay đổi.

## 14. Spring Integration: cấu hình Scatter-Gather theo giới hạn có kiểm soát

Trong Spring Integration, scatterer có thể dựa trên **Recipient List Router** hoặc **Publish-Subscribe Channel**; gatherer dùng cơ chế **Aggregator**. Cấu hình cụ thể phụ thuộc Java DSL/API của phiên bản dự án, nhưng kiến trúc nên cố định các điểm kiểm soát:

~~~mermaid
flowchart TD
    IN["quotes.in"] --> V["Filter / validate QuoteRequest"]
    V --> P["ScatterPlanner: 3 hoặc 4 recipients"]
    P --> ADM{"Admission control"}
    ADM -->|"Không đủ capacity"| REJ["Overload outcome / reject"]
    ADM -->|"Được nhận"| SC["ScatterGatherHandler"]
    SC --> I["inventory requests"]
    SC --> PR["pricing requests"]
    SC --> SH["shipping requests"]
    SC --> FR["fraud nếu bắt buộc"]
    I --> GA["Gather: expected branches, deadline"]
    PR --> GA
    SH --> GA
    FR --> GA
    GA --> OUT["quotes.result"]
~~~

Ví dụ một **flow vỏ** cho ingress và admission trước Scatter-Gather:

~~~java
@Configuration
@EnableIntegration
class QuoteIngressFlow {

    @Bean
    IntegrationFlow validateAndAdmitQuotes(
            QuoteAdmissionService admissionService) {
        return IntegrationFlow.from("quotes.in")
            .filter(QuoteRequest.class,
                request -> request.requestId() != null
                    && !request.requestId().isBlank(),
                f -> f.throwExceptionOnRejection(true))
            .handle(QuoteRequest.class,
                (request, headers) ->
                    admissionService.prepareAndReserve(request))
            .channel("quotes.scatter.ready")
            .get();
    }
}
~~~

`QuoteAdmissionService` là **service ứng dụng do bạn định nghĩa**; `prepareAndReserve()` phải trả một payload/message phù hợp (không null) chứa plan, deadline và lease/correlation metadata để flow kế tiếp xử lý. Nó phải bảo đảm resource lease được trả lại **sau khi Gather có outcome terminal**, kể cả timeout/lỗi; đoạn code trên chưa triển khai lease lifecycle.

Phần `ScatterGatherHandler` tiếp theo phải được cấu hình với recipient list đã giới hạn, error handling, reply channel và gather timeout theo **API thật của phiên bản Spring Integration đang dùng**. Không chấp nhận raw target bean names hoặc expression từ payload công khai. Không cần tự tạo nhiều subscription riêng cho một channel chỉ vì có nhiều tenant nếu có thể giải quyết bằng policy ở layer quản trị.

**Điểm thực hành:** khi dùng scatterer kiểu pub/sub, nhớ kiểm tra cách đánh dấu sequence headers; khi dùng recipient list, kiểm tra cách cấu hình số recipients và việc subscriber có trả reply. Không giả định cả hai tạo metadata và release strategy giống hệt nhau mà chưa kiểm thử.

## 15. Một request phải có **expected reply set** rõ ràng

Gather chỉ có thể kết luận “đã đủ” nếu biết các nhánh nào thực sự được yêu cầu.

~~~text
Plan Q-101:
  expected = {INVENTORY, PRICING, SHIPPING}

Reply đến:
  INVENTORY: OK
  PRICING:   OK
  SHIPPING:  TIMEOUT/FAILED
~~~

Nếu `FRAUD` là nhánh tùy điều kiện, không được dùng một con số release cứng áp dụng mọi plan; nếu `SHIPPING` chưa từng được gửi vì capacity, cũng không được giả làm “reply bị mất” mà phải ghi nhận lý do không dispatch.

Một cấu trúc kết quả:

~~~java
record BranchReply(
    String requestId,
    QuoteBranch branch,
    boolean success,
    String value,
    String reasonCode
) {}

record QuoteGatherResult(
    String requestId,
    Set<QuoteBranch> expected,
    Map<QuoteBranch, BranchReply> received,
    boolean complete,
    String overallStatus
) {}
~~~

**Mỗi branch chỉ đóng góp tối đa một kết quả hợp lệ** vào cùng logical request (trừ khi contract hỗ trợ nhiều phiên bản kết quả). `BranchReply` phải được validate `requestId`, tenant scope, branch membership và schema; message từ nhánh lạ không được tính để làm “đủ số lượng”.

Khi mỗi nhánh có thể retry, nên bổ sung `attemptId` và quy tắc chọn **outcome cuối hợp lệ** của branch thay vì cộng tất cả replies vào group size.

## 16. Release theo tập nhánh, không đơn thuần theo số message

Một implementation release quá yếu:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

Giả sử Inventory reply hai lần vì broker redelivery, Pricing reply một lần còn Shipping chưa xong:

~~~text
Group Q-101:
  INVENTORY - attempt 1
  INVENTORY - duplicate attempt 1
  PRICING   - attempt 1

group.size() = 3, nhưng SHIPPING chưa có
~~~

**Không release thành công** chỉ dựa vào ba message. Một mô hình application-level:

~~~java
final class ExpectedBranchRelease {

    boolean ready(Set<QuoteBranch> expected,
                  Collection<BranchReply> replies) {
        if (expected == null || expected.isEmpty()) {
            throw new IllegalArgumentException("INVALID_EXPECTED_SET");
        }
        for (BranchReply reply : replies) {
            if (!expected.contains(reply.branch())) {
                throw new IllegalArgumentException("UNEXPECTED_BRANCH");
            }
        }
        Set<QuoteBranch> received = replies.stream()
            .map(BranchReply::branch)
            .collect(Collectors.toSet());
        return received.equals(expected);
    }
}
~~~

Ví dụ này cho thấy **đếm unique branches** nhưng chưa xử lý đầy đủ duplicate khác nội dung hoặc kết quả thuộc nhầm `requestId`. Trong production, phải so với một **manifest/plan đã chốt**, xác minh request/tenant, kiểm tra duplicate conflict và chính sách timeout/partial result.

Nếu một branch trả `FAILURE_RESULT` có cấu trúc, nó vẫn có thể được tính là **đã có outcome** của branch ấy; nhưng **overallStatus** phải là `FAILED` hoặc `PARTIAL` theo hợp đồng, không là `SUCCESS`.

## 17. Correlation phải phân biệt request, tenant và phiên bản plan

Một tenant có thể tạo nhiều quote cho cùng order; hai tenant có thể dùng chung `orderId`. Nếu Gather chỉ dùng orderId hoặc customerId, các replies từ request khác nhau có thể bị ghép nhầm.

| Identity | Vai trò | Có phải group key độc lập an toàn? |
|---|---|---|
| `MessageHeaders.ID` | ID của Spring message tại một thời điểm | Không ổn định xuyên rebuild/replay |
| `orderId` | ID đơn hàng nghiệp vụ | Có thể có nhiều quote/revision |
| `requestId` | Một logical quote evaluation | Tốt nếu duy nhất và được cấp đúng |
| `tenantId` | Phạm vi phân quyền/khách hàng | Cần kèm request/group ID |
| `planVersion` | Phiên bản tập nhánh/quy tắc | Cần khi cùng request có kế hoạch khác nhau |
| `traceId` | Quan sát toàn chuỗi call | Không thay business correlation |
| `sequenceNumber/size` | Metadata scatter/gather | Không thay membership hay idempotency |

Một khóa ví dụ:

~~~text
tenant-A | quote-Q101 | plan-v3
tenant-A | quote-Q101 | plan-v4
tenant-B | quote-Q101 | plan-v3
~~~

**Không biến `correlationId` thành UUID mới ở từng branch handler**. Stable group ID phải được tạo và ghi nhận **trước khi scatter**. Khi retry cùng logical evaluation, policy có thể giữ group ID và attempt ID riêng; khi thay đổi plan một cách có chủ đích, phải xác định versioning/migration và không trộn replies từ hai plan.

Qua Kafka/AMQP, header mapper có thể loại hoặc chuyển kiểu một số headers. Nên công bố business correlation trong wire contract, nhưng vẫn phải xác minh tenant và nguồn gửi reply; một string trùng ID không phải bằng chứng authorization.

## 18. Deadline tổng và timeout từng nhánh là hai loại khác nhau

Giả sử API có deadline **1 giây**:

~~~text
T0 = request được nhận
Deadline tổng = T0 + 1.000 ms

Inventory: timeout 300 ms
Pricing:   timeout 700 ms
Shipping:  timeout 600 ms
Gather:    không được chờ quá deadline tổng
~~~

Không cấu hình mỗi nhánh timeout 1 giây rồi để Gather đợi thêm một giây nữa, vì tổng thời gian có thể vượt SLO của Gateway. Có thể tính ngân sách còn lại:

\[
T_{\mathrm{remaining}}
= \max(0,\ T_{\mathrm{deadline}}-T_{\mathrm{now}})
\]

Một quyết định downstream nên tuân theo **deadline tổng**, đồng thời dùng timeout HTTP client/DB call ngắn hơn hoặc bằng phần ngân sách còn lại. Nếu queue wait đã ăn 800 ms, không nên cấp mới một timeout 700 ms chỉ vì Pricing bình thường có ngân sách đó.

**Quan trọng:** `gatherTimeout` hoặc `groupTimeout` không thay thế timeout của nhánh remote. Khi caller ngừng chờ, task nền có thể vẫn chạy; cancellation, abort/timeout ở client và cleanup group phải được thiết kế riêng.

## 19. Một nhánh chậm ảnh hưởng toàn bộ quote như thế nào?

Với Gather kiểu *all responses required*, thời gian trả kết quả gần bằng **nhánh chậm nhất** (và overhead scatter/gather), không phải tổng độ trễ mọi nhánh nếu chúng thực sự chạy song song:

\[
T_{\mathrm{all}}\approx
\max(T_{\mathrm{inventory}},T_{\mathrm{pricing}},T_{\mathrm{shipping}})
+T_{\mathrm{overhead}}
\]

Nếu ba nhánh **chạy nối tiếp**, thời gian lại gần tổng các branch durations. Do đó phải xác minh topology và executor thực tế trước khi kỳ vọng tối ưu latency.

Một nhánh chậm gây ba loại áp lực:

1. **Branch capacity:** số HTTP connections, threads hoặc permits bị giữ lâu.
2. **Gather state:** message group, correlation/pending metadata còn tồn tại.
3. **Caller:** Gateway thread hoặc request future chờ kết quả.

Thêm semaphore vào branch không giải quyết group retention nếu những request đã được nhận vẫn chưa thể kết luận. Cần deadline, timeout handling, release strategy và overload outcome nhất quán với hợp đồng business.

## 20. Trạng thái PARTIAL, FAILED và TIMEOUT phải tách biệt

Không phải use case nào cũng đòi cả ba nhánh thành công.

| Chính sách | Ý nghĩa | Ví dụ |
|---|---|---|
| **All required** | Tất cả nhánh bắt buộc phải có kết quả hợp lệ | Không báo giá nếu chưa biết phí shipping |
| **Partial allowed** | Có thể phát kết quả với một số nhánh thiếu | Hiển thị giá tạm, shipping pending |
| **Quorum** | Đủ một số nguồn hợp lệ để quyết định | Đối chiếu nhiều nguồn dữ liệu độc lập |
| **First-success** | Dùng kết quả thành công đầu tiên | Lookup từ nhiều mirror tương đương |
| **Fail-fast** | Một lỗi nhất định làm toàn request không còn ý nghĩa | Fraud kết luận block |

**Không được âm thầm thay đổi release policy khi quá tải**. Nếu Shipping là bắt buộc, việc bỏ Shipping rồi trả `SUCCESS` không phải “graceful degradation”.

Một result tổng hợp cần biểu diễn điều kiện đã hoàn tất:

~~~json
{
  "requestId": "Q-101",
  "status": "PARTIAL",
  "expectedBranches": ["INVENTORY", "PRICING", "SHIPPING"],
  "receivedBranches": ["INVENTORY", "PRICING"],
  "missingBranches": ["SHIPPING"],
  "reasonCode": "SHIPPING_TIMEOUT"
}
~~~

Với `QUORUM`, phải chứng minh những reply được đếm thực sự đến từ **các nguồn độc lập được cho phép**; ba duplicate từ một nguồn không được xem là ba phiếu.

## 21. Nhánh bị từ chối capacity không phải nhánh đã hoàn tất thành công

Khi worker pool đầy, có ít nhất ba cách xử lý:

1. **Từ chối toàn quote trước scatter:** caller nhận overload/too-busy theo contract.
2. **Phát failure outcome cho branch không được nhận:** Gather có thể kết luận `FAILED/PARTIAL`.
3. **Xếp hàng có giới hạn:** request được chấp nhận nhưng deadline phải bao gồm cả thời gian chờ.

Hành vi không nên làm:

~~~text
Shipping không còn permit
  → bỏ qua send
  → vẫn gắn expected=3
  → Gather chờ vô hạn vì không bao giờ có Shipping reply
~~~

Hoặc:

~~~text
Shipping không còn permit
  → tự giảm expected từ 3 xuống 2
  → báo SUCCESS dù Shipping bắt buộc
~~~

Cách đúng là một **outcome có mã lỗi** và quy tắc rõ: `CAPACITY_EXCEEDED` có thể không retry, retry ngắn khi còn deadline, hoặc được chuyển sang fallback nếu nghiệp vụ cho phép. Tất cả phải được đo riêng khỏi lỗi dữ liệu và lỗi mạng.

## 22. Kích thước message và byte budget cũng cần giới hạn

Số nhánh chỉ là một trục của tiêu thụ tài nguyên:

~~~text
1 QuoteRequest payload = 10 MiB
4 branches copy/serialize cùng payload
→ có thể tạo nhiều lần copy, encode, queueing và GC
~~~

Với payload lớn, fan-out nhỏ vẫn có thể gây memory pressure. Nên:

- Giới hạn kích thước request tại adapter và số line items trong payload.
- Gửi **projection** phù hợp cho mỗi branch, không sao chép mọi field/PII.
- Với dữ liệu lớn, truyền object reference/storage key có quyền truy cập thay vì nạp lại nhiều bản.
- Giới hạn số bytes đang chờ trong broker/executor chứ không chỉ task count.
- Kiểm tra native header mapper; không serialize `replyChannel`, `errorChannel` hoặc object Spring nội bộ tùy tiện.
- Đo payload bytes **sau serialize**, vì encoding và headers làm kích thước wire khác Java object trong RAM.

Nếu Scatter dùng `PublishSubscribeChannel` trong cùng JVM, các subscriber có thể cùng tham chiếu tới payload **mutable**. Một branch sửa object tại chỗ có thể ảnh hưởng branch khác. Nên dùng message/payload bất biến, hoặc clone có chủ đích, đặc biệt khi chạy đồng thời.

## 23. Giới hạn theo tenant: tránh một khách hàng chiếm hết pool

Một hệ thống đa tenant phải xác định **fairness**:

~~~text
Global concurrent budget = 100 branch calls
Tenant A traffic tăng đột biến
Tenant B vẫn cần xử lý quote bình thường
~~~

Nếu chỉ có global semaphore, tenant A có thể lấy hết permits. Một thiết kế tốt hơn có thể kết hợp:

- **Global admission limit** để bảo vệ JVM/cluster.
- **Per-tenant concurrency/rate quota** để cô lập tải.
- **Per-branch bulkhead** cho Pricing, Shipping, Inventory.
- **Priority classes** cho traffic quan trọng, nhưng tránh starvation cho traffic thường.
- **Queueing có giới hạn** và timeout phù hợp từng lớp dịch vụ.

Đừng dùng `tenantId` trong raw header của client làm khóa tính quota nếu nó chưa được xác thực. Quota theo tenant phải gắn với principal/credential đã được hệ thống xác minh.

Tránh mở một thread pool riêng cho mỗi tenant không giới hạn: khi có hàng nghìn tenant, overhead threads, queues và monitoring có thể còn tệ hơn bài toán ban đầu. Có thể dùng shared bounded pool với accounting/fair scheduling theo tenant.

## 24. Retry làm khuếch đại fan-out như thế nào?

Giả sử quote có 4 nhánh, mỗi branch được retry tối đa 3 attempts:

~~~text
1 quote
  → 4 logical branches
  → tối đa 12 branch attempts (nếu mỗi nhánh chạy đủ 3 lần)
~~~

Nếu **toàn bộ Scatter-Gather** cũng được retry 3 lần từ đầu, số attempts tối đa có thể đạt **36** trong ví dụ, trừ khi các bước đã thành công được reuse/dedupe. Đây là mức tải gấp nhiều lần 4 nhánh ban đầu.

\[
A_{\mathrm{worst}}
\le F\times R_{\mathrm{branch}}\times R_{\mathrm{wholeFlow}}
\]

Trong đó `R` là **tổng số attempts**, không phải “số lần retry thêm”. Đây là **upper bound minh họa** khi các cấp retry lồng nhau; hành vi thật phụ thuộc vị trí advice và chính sách cancel/dedupe.

Để tránh retry storm:

1. Định nghĩa retry ở **một ranh giới sở hữu rõ ràng**.
2. Chỉ retry transient errors và còn deadline.
3. Giới hạn số attempts, dùng backoff + jitter.
4. Đặt **retry budget toàn cục/per-tenant**.
5. Không gửi lại các nhánh đã có outcome hợp lệ nếu contract cho phép reuse.
6. Bảo vệ side effects bằng idempotency key theo `requestId + branch + operation`.
7. Có circuit breaker/bulkhead cho phụ thuộc liên tục lỗi.

Một `Gateway timeout` không chứng minh các nhánh chưa tạo side effect. Retry toàn quote mà không có idempotency có thể làm nhiều branch hành động lặp.

## 25. Late replies, duplicate replies và group cleanup

Một quote có deadline 1 giây, Pricing hoàn tất sau 1,3 giây:

~~~text
T+000 ms  Scatter plan Q-101, expected={I,P,S}
T+250 ms  Inventory reply
T+400 ms  Shipping reply
T+1000 ms Gather timeout → QuoteResult(TIMEOUT)
T+1300 ms Pricing reply trễ
~~~

**Không được coi reply muộn là yêu cầu mới và tạo summary thứ hai** nếu nghiệp vụ chỉ cho một final result. Với MessageGroupStore/Gather:

- Có thể giữ một **completed/expired group marker** trong TTL thích hợp.
- Có thể dùng durable state với chuyển trạng thái `WAITING → COMPLETED/EXPIRED` có điều kiện.
- Với reply trễ, định nghĩa **ignore/quarantine/correction event** có audit.
- Với duplicate, chỉ chấp nhận một outcome cuối được phép cho mỗi branch; conflict phải được phát hiện.
- Xóa/expire các group chờ đã hết hạn; group chờ vô hạn có thể làm đầy memory/store.

Các cấu hình Spring Integration liên quan `groupTimeout`, `expireGroupsUponCompletion`, partial release và message group store có semantics phụ thuộc version và topology. **Không suy đoán rằng chỉ set timeout là framework tự cắt mọi remote call, xóa mọi pending state hoặc ngăn mọi reply muộn**.

## 26. MessageGroupStore: giới hạn pending groups và dung lượng lưu

Gather có thể giữ dữ liệu của nhiều request cùng lúc:

| Loại state | Kích thước tăng theo | Cần chính sách |
|---|---|---|
| Pending group metadata | Số quote chưa hoàn tất | Max pending, timeout, cleanup |
| Collected replies | Số nhánh đã trả kết quả | Payload size, store/retention |
| Duplicate detection | Số branch outcome IDs | TTL/window, uniqueness |
| Completed group markers | Số quote đã hoàn thành còn cần nhớ | Retention hữu hạn |
| Error/quarantine | Số request thất bại | Quota, paging, ownership |

**In-memory MessageGroupStore** không tự sống qua restart; **persistent store** có thể hỗ trợ khôi phục nhưng cần transaction, cleanup và locking phù hợp khi nhiều instance cùng aggregate. Dùng DB chung không tự ngăn double release nếu cập nhật group không được phối hợp đúng.

Một trần hữu ích là **maximum pending groups per flow/tenant**, kết hợp time budget. Khi chạm trần, ứng dụng phải **từ chối hoặc làm chậm ingress** có chủ đích. Nếu chỉ để store lớn dần, vấn đề có thể xuất hiện muộn và khó gắn với nhánh lỗi ban đầu.

**Không xóa nhóm tùy tiện để giải phóng RAM** khi chưa phát outcome cho caller/coordinator. Xóa state của một quote đang hoạt động có thể khiến reply đến sau trở thành orphan và không bao giờ có kết quả.

## 27. Chuỗi lỗi: từ branch tới error channel và Gateway

Một nhánh thất bại có thể diễn ra trước hoặc sau ranh giới async:

| Tình huống | Caller có thể thấy gì? | Ai xử lý? |
|---|---|---|
| Scatter đồng bộ, handler ném exception | Exception lan ngược qua channel/caller | Synchronous error boundary |
| Executor branch ném exception | Publisher đã gửi xong; lỗi ở worker | Error handler/error channel |
| Broker branch bị redelivery | Caller có thể đã timeout | Listener/container + recovery |
| Quá capacity trước scatter | Overload/rejection outcome | Admission service |
| Quá capacity ở một branch | Failure outcome hoặc branch-level error | Bulkhead/branch coordinator |
| Gather chờ quá deadline | Timeout/partial/fail theo policy | Gather/coordinator |
| Lỗi khi publish summary | Kết quả tính đúng nhưng chưa đến downstream | Output retry/outbox/idempotency |

**Error channel không tự có nghĩa là “một branch reply thất bại” cho Aggregator.** Nếu một branch handler ném exception trước khi trả reply, Gather có thể **không nhận được message nào từ nhánh đó**. Muốn group kết thúc có chủ đích, phải chuyển lỗi thành `BranchReply(success=false, reasonCode=...)` với đúng correlation, hoặc để timeout/fail-fast coordinator đánh dấu terminal state.

**Không log mọi exception thành “scattered successfully”.** Phân biệt lỗi do ingress validation, capacity, branch execution, correlation mismatch, gather timeout và output publication.

## 28. Unit test cho planner và release

JUnit 5 kiểm thử giới hạn nhánh:

~~~java
@Test
void normalQuoteHasThreeBranches() {
    QuoteRequest request = new QuoteRequest(
        "Q-101", "tenant-a", false, 10);
    ScatterPlan plan = new ScatterPlanner().plan(
        request, Instant.parse("2026-11-21T03:00:00Z"),
        Duration.ofSeconds(1));

    assertEquals(3, plan.required().size());
    assertFalse(plan.required().contains(QuoteBranch.FRAUD));
}

@Test
void highRiskQuoteRequiresFraudAndIsStillBounded() {
    QuoteRequest request = new QuoteRequest(
        "Q-102", "tenant-a", true, 20);
    ScatterPlan plan = new ScatterPlanner().plan(
        request, Instant.parse("2026-11-21T03:00:00Z"),
        Duration.ofSeconds(1));

    assertEquals(4, plan.required().size());
    assertTrue(plan.required().contains(QuoteBranch.FRAUD));
    assertTrue(plan.required().size()
        <= ScatterPlanner.MAX_BRANCHES);
}

@Test
void rejectsUnboundedInputSize() {
    QuoteRequest request = new QuoteRequest(
        "Q-103", "tenant-a", false, 100_000);
    assertThrows(IllegalArgumentException.class,
        () -> new ScatterPlanner().plan(
            request, Instant.now(), Duration.ofSeconds(1)));
}
~~~

Kiểm thử Gather không được đánh đồng duplicate với đủ reply:

~~~java
@Test
void duplicateInventoryDoesNotReplaceMissingShipping() {
    Set<QuoteBranch> expected = Set.of(
        QuoteBranch.INVENTORY,
        QuoteBranch.PRICING,
        QuoteBranch.SHIPPING);
    List<BranchReply> replies = List.of(
        new BranchReply("Q-101", QuoteBranch.INVENTORY,
            true, "YES", null),
        new BranchReply("Q-101", QuoteBranch.INVENTORY,
            true, "YES", null),
        new BranchReply("Q-101", QuoteBranch.PRICING,
            true, "100", null));

    assertFalse(new ExpectedBranchRelease().ready(
        expected, replies));
}
~~~

Đoạn code kiểm tra membership cơ bản; production cần thêm validation `requestId/tenantId/planVersion`, duplicate conflicting values và manifest do nguồn đáng tin cấp. Test không cần Spring context khi kiểm thử planner/release thuần Java.

## 29. Test bounded executor và resource leak

Một test tài nguyên nên có chủ đích, không dựa vào độ trễ ngẫu nhiên:

1. Dùng `CountDownLatch` để giữ một số worker trong nhánh giả lập.
2. Gửi đủ requests để sử dụng hết permits.
3. Thử gửi thêm, xác minh outcome `CAPACITY_EXCEEDED` hoặc `EXECUTOR_REJECTED` theo policy.
4. Thả latch, xác minh task hoàn tất và permits được nhả.
5. Đảm bảo cancellation/timeout **không làm nhả permit sớm** khi task còn chạy.
6. Xác minh không có group đang chờ không thời hạn do một branch bị từ chối.
7. Lặp với exception từ branch handler, kiểm tra nhả permit trong `finally`.

Ví dụ định hướng:

~~~java
CountDownLatch entered = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Function<QuoteRequest, BranchOutcome> slowBranch = request -> {
    entered.countDown();
    try {
        if (!release.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("TEST_WAIT_TIMEOUT");
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(interrupted);
    }
    return new BranchOutcome(
        request.requestId(), QuoteBranch.PRICING,
        true, "OK", null);
};
~~~

Đây là **test fixture**, không phải một bài test đầy đủ. Khi nối vào `BoundedBranchDispatcher`, tạo đủ task để chạm trần của dispatcher/executor, sau đó giải phóng latch trong `finally` của test để không làm treo test runner khi assertion lỗi.

**Đo cả active threads, queued tasks, memory và pending Gather groups.** Một test chỉ xác nhận `RejectedExecutionException` xảy ra chưa chứng minh request đã nhận rejection outcome hoặc không còn pending state bị bỏ quên.

## 30. Integration test: nhiều quote đồng thời, reply đảo thứ tự

Kiểm thử Scatter-Gather trong Spring context nên có test channels/handlers để đếm thực tế số lần gọi và correlation. Mô phỏng:

~~~text
Q-101: INVENTORY nhanh, PRICING chậm, SHIPPING vừa
Q-102: INVENTORY chậm, PRICING nhanh, SHIPPING vừa

Reply xen kẽ:
  Q-101/INVENTORY
  Q-102/PRICING
  Q-102/SHIPPING
  Q-101/SHIPPING
  Q-101/PRICING
  Q-102/INVENTORY
~~~

Kỳ vọng:

- Mỗi `QuoteResult` chứa **đúng requestId/tenant/planVersion** và tập các nhánh của riêng nó.
- Không dùng reply đầu tiên của Q-102 để hoàn thành Q-101.
- Không release đủ chỉ vì nhận đủ số message nhưng thiếu một branch.
- Nếu nhánh bị timeout, result chứa trạng thái/nhánh thiếu theo policy.
- Broker redelivery hoặc duplicate reply không tạo `QuoteResult` thứ hai trái hợp đồng.

### Ma trận kiểm thử cần có

| Case | Mô phỏng | Điều phải chứng minh |
|---|---|---|
| Normal quote | 3 recipients | Chính xác 3 branch requests, đủ 3 outcomes |
| High-risk quote | 4 recipients | Fraud không bị loại, Gather chờ đúng tập |
| Dynamic recipients | Plan v2 khác v1 | Không lấy expected set mới cho request cũ |
| One branch slow | Pricing vượt deadline | Overall TIMEOUT/PARTIAL/FAILED theo policy |
| Executor saturated | Queue và workers đầy | Không tạo queue vô hạn, có rejection result |
| Admission rejected | Không có global permit | Không phát scatter rồi giữ group chờ |
| Branch exception | Shipping ném lỗi | Error path/outcome có correlation |
| Duplicate reply | Inventory gửi hai bản | Không xem duplicate là hai nhánh |
| Late reply | Pricing về sau terminal state | Không phát kết quả cuối lần hai |
| Concurrent requests | Q-101/Q-102 xen kẽ | Không ghép chéo request |
| Cross-tenant | Cùng request ID ở tenant A/B | Không trộn tenant |
| Mixed protocol | Qua broker/header mapper | Correlation và deadline giữ đúng |
| Nested Splitter | 500 lines × 4 branches | Total work budget được thực thi |
| Restart | Pending groups ở durable store | Recovery theo contract |
| Retry storm | Whole flow + branch retry | Bounded attempts, không double side effects |
| Empty recipient plan | Plan không có nhánh hợp lệ | Reject/terminal result, không chờ mãi |

Các test nên dùng `CountDownLatch`/barrier/test queue, timeout hữu hạn và Spring context thực. Không dựa vào `Thread.sleep` để “hy vọng” branch về đúng thứ tự. Khi test broker, cần kiểm tra ack/redelivery, error handler, header mapper và transaction thực; unit test mock không chứng minh các semantics đó.

## 31. Observability: nhìn được fan-out và mức tiêu thụ tài nguyên

Một dashboard Scatter-Gather nên có các nhóm metric:

| Tín hiệu đề xuất | Cần phát hiện |
|---|---|
| `scatter.requests.count` | Lưu lượng ingress |
| `scatter.branch.count` | Số nhánh/request; thay đổi bất thường |
| `scatter.tasks.created.count` | Tổng công việc nội bộ |
| `scatter.admission.rejected.count` | Request bị từ chối trước Scatter |
| `scatter.branch.capacity.rejected.count` | Nhánh không được nhận do đầy |
| `branch.active.count` theo service | In-flight load |
| `branch.queue.depth` và queue age | Backlog/latency |
| `branch.duration` p95/p99 | Nhánh chậm |
| `gather.pending.groups` | Nhóm chờ hoàn tất |
| `gather.group.age` | Nhóm có nguy cơ timeout |
| `gather.timeout.count` | Timeout theo flow/branch |
| `gather.partial.count` | Kết quả thiếu nhánh |
| `gather.duplicate.reply.count` | Redelivery/dedupe |
| `gather.late.reply.count` | Replies đến sau terminal state |
| `retry.attempts.count` | Retry amplification |
| `message.store.size.bytes` | Group store/broker pressure |

Đây là **tên metric đề xuất**, không khẳng định là meter mặc định của Spring Integration. Với Micrometer/observation, chọn tag có cardinality thấp như `branchType`, `outcome`, `flowName`, `reasonCode`; **không dùng request ID hoặc customer ID làm metric tag**.

Trong tracing/log có kiểm soát, giữ `requestId`, `tenantId` đã xác thực, `planVersion`, branch identity, attempt ID và deadline. Không log nguyên payload/headers nhạy cảm. Khi một quote timeout, cần biết nó **chưa được admit**, **đang queue**, **đang chạy branch**, **đã có reply nhưng bị mismatch**, hay **Gather chưa release**.

## 32. Runbook khi Scatter-Gather quá tải

Khi p99 quote latency tăng và pending groups nhiều:

1. **Đo fan-out thực tế:** Có bật nhánh mới hoặc nested Splitter khiến số tasks/request tăng không?
2. **Xem nhánh chậm:** Pricing, Shipping hay Inventory đang giữ nhiều connections/threads?
3. **Kiểm tra queue:** Có queue không giới hạn hoặc queue age vượt deadline không?
4. **Đối chiếu admission:** Quota global/per-tenant/per-branch có bị vượt hay không?
5. **Kiểm tra Gather:** Nhánh đã reply chưa, correlation có đúng, group có expired chưa?
6. **Kiểm tra retry:** Có retry storm hoặc cả whole-flow và branch-level retry đang chạy đồng thời không?
7. **Giảm tải có chủ đích:** Rate limit, circuit breaker, queue bound, giảm traffic canary hoặc fallback chỉ khi hợp đồng cho phép.
8. **Bảo vệ dữ liệu:** Không drop branch bắt buộc để có “success”; phải phát overload/failure/partial outcome phù hợp.
9. **Phục hồi:** Reconcile pending groups, late replies và side effects trước khi replay.
10. **Ngăn tái diễn:** Thử lại load test với burst, dependency chậm, broker redelivery và các limit đã đo.

**Không giải quyết mọi sự cố chỉ bằng cách tăng thread pool**. Nếu downstream chỉ chịu được 20 concurrent calls, nâng pool từ 20 lên 200 có thể khiến service lỗi nặng hơn, làm retry tăng và kéo theo cả hệ thống.

## 33. Bài thực hành: thiết kế quote fan-out có giới hạn

Xây flow **BoundedQuoteScatterGather** theo các bước:

1. **Contract:** định nghĩa `QuoteRequest`, `ScatterPlan`, `BranchReply`, `QuoteGatherResult` và deadline.
2. **Rule:** ba nhánh bắt buộc, nhánh Fraud khi high-risk; `MAX_BRANCHES=4`.
3. **Admission:** đặt trần toàn request và trần từng branch; không gửi nửa plan mà không có outcome.
4. **Executor:** dùng bounded thread pool/queue; cho một branch giả lập chậm để quan sát saturation.
5. **Gather:** release theo **tập expected branches**, không chỉ đếm messages.
6. **Correlation:** giữ request/tenant/plan identity xuyên Splitter, Router, Transformer và broker.
7. **Deadline:** 1 giây tổng, timeout riêng theo nhánh; xây policy `TIMEOUT/PARTIAL/FAILED`.
8. **Retry:** giới hạn attempts, có backoff/jitter và idempotency cho branch có side effect.
9. **Late/duplicate:** gửi replay/reply đến muộn sau terminal state, kiểm tra không double publish.
10. **Multi-tenant:** tạo burst từ tenant A, xác minh tenant B vẫn có capacity theo policy.
11. **Load test:** so 3/4/8 recipients, 50/100/200 request/s; quan sát active tasks, queue depth và pending groups.
12. **Runbook:** viết cách xác định request đang chờ ở đâu và khi nào được rollback/cancel/retry.

**Tiêu chí hoàn thành:** số nhánh được chặn đúng theo policy; không có queue/group chờ vô hạn; mỗi branch có outcome hoặc deadline; overload là trạng thái có thể quan sát; duplicate/late reply không làm sai Gather; tổng mức đồng thời bám limit đã chọn; test chứng minh không có resource leak sau timeout hoặc exception.

## 34. Sai lầm thường gặp

**“Scatter-Gather tự chạy song song.”** Không nhất thiết. Concurrency tùy executor/channel/transport, và nhánh đồng bộ có thể được gọi nối tiếp.

**“Giới hạn bốn nhánh/request là đủ để không quá tải.”** Sai. Ingress, nested Splitter, retry và số request đang chạy vẫn có thể làm tổng tasks rất lớn.

**“Thread pool 8 workers bảo đảm bộ nhớ hữu hạn.”** Sai nếu queue, payload hoặc pending MessageGroupStore không có giới hạn.

**“Không dispatch Shipping thì Gather tự hiểu còn hai nhánh.”** Sai. Expected set phải được chốt; branch không gửi cần failure/cancel outcome rõ ràng.

**“Tăng timeout có thể sửa mọi group thiếu result.”** Sai. Nhánh `void`/Filter drop hoặc correlation mismatch có thể không bao giờ tạo reply.

**“Cứ đủ ba messages là xong.”** Sai khi duplicate branch reply hoặc message từ nhánh lạ được tính vào nhóm.

**“Gateway timeout nghĩa là mọi branch đã dừng.”** Sai. Tác vụ remote có thể còn chạy và tạo side effect.

**“Bắt RejectedExecutionException rồi tiếp tục như success.”** Sai. Quá capacity phải được phản ánh trong request/group status.

**“Retry giúp hệ thống mau hồi phục khi dependency đã quá tải.”** Không luôn. Retry không giới hạn tạo bão request, làm sự cố kéo dài.

**“Dùng lại replyChannel làm business requestId xuyên broker.”** Sai. Return address nội bộ và correlation identity có nhiệm vụ khác nhau.

**“MessageGroupStore persistent là đủ để exactly-once.”** Sai. Cần idempotency, transaction/locking và kiểm soát late replies/double release.

**“Tenant ID từ request body đủ để đặt quota và quyền.”** Sai. Quota và tenant scope cần gắn với identity đã được xác minh.

## 35. Ghi nhớ

**Scatter-Gather an toàn không chỉ là phát nhanh rồi đợi đủ reply.** Cần giới hạn **số nhánh trên từng request, số công việc đồng thời, queue backlog, pending Gather groups, payload bytes, retry attempts và tài nguyên theo tenant**. Một cấu hình limit đơn lẻ không thể thay thế các giới hạn còn lại.

Trong **Spring Integration**, hãy lập **scatter plan** từ allowlist trước khi gửi, dùng executor/channel/adapter có backpressure, giữ **correlation và expected recipient set** ổn định, dùng Gather release theo các branch identity thực sự, đặt **deadline tổng + timeout từng nhánh**, và định nghĩa outcome cho overload, partial failure, late/duplicate replies. Kết hợp **Gateway, Filter, Router, Transformer, Splitter, Aggregator, error channel và retry** với test concurrency/overload/cleanup sẽ giúp flow có thể mở rộng mà không đánh đổi tính đúng đắn.

### Tài liệu tham khảo

- Spring Integration Reference, **Scatter-Gather**: https://docs.spring.io/spring-integration/reference/scatter-gather.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Messaging Endpoints**: https://docs.spring.io/spring-integration/reference/endpoint.html
- Enterprise Integration Patterns, **Scatter-Gather**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
