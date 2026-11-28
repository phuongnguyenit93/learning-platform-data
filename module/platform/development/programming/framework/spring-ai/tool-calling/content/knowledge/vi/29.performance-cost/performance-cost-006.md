# Chạy đồng thời công cụ độc lập khi kiến trúc cho phép

Khi tích hợp Spring AI Tool Calling, một yêu cầu người dùng có thể cần nhiều nguồn dữ liệu: xem trạng thái đơn hàng, tra vận đơn, đọc tồn kho hoặc đối chiếu khuyến mại. Nếu các lời gọi **độc lập về dữ liệu, quyền truy cập và side effect**, chạy chúng đồng thời có thể giảm thời gian chờ. Nhưng bật tùy chọn “parallel tool calls” của provider không có nghĩa ứng dụng đã thực thi các `ToolCallback` bằng nhiều luồng. Việc tối ưu phải đặt đúng tầng: **mô hình có thể đề xuất nhiều tool; ứng dụng quyết định lịch chạy, giới hạn đồng thời, kiểm tra quyền và cách ghép kết quả**.

Bài học thuộc chương **Hiệu năng và chi phí** của mô-đun `SPRING_AI_TOOL_CALLING`. Trọng tâm là phối hợp `@Tool`/`ToolCallback`, `ToolContext`, model/tool loop, giới hạn tài nguyên và quan sát để giảm latency mà không tăng quá nhiều chi phí hoặc làm sai kết quả nghiệp vụ. Tất cả ví dụ đều cần được đối chiếu với phiên bản Spring AI và provider thực tế trước khi đưa vào production.

## 1. Phân biệt ba kiểu “đồng thời”

| Khái niệm | Ai quyết định? | Ý nghĩa | Có bảo đảm callback chạy song song? |
| --- | --- | --- | --- |
| **Model trả nhiều tool calls trong một reply** | Mô hình và tùy chọn của provider | Một lần gọi mô hình có thể đề xuất nhiều công cụ | **Không** |
| **Nhiều callback thực thi đồng thời** | Ứng dụng, `ToolCallingManager` hoặc custom scheduler | Nhiều tác vụ I/O chạy chồng thời gian | Chỉ khi executor thực sự triển khai |
| **Nhiều user turns/requests cùng lúc** | Web server và hệ thống thực thi | Nhiều người dùng gọi ChatClient song song | Không đồng nghĩa tool calls của *cùng một reply* song song |

Ví dụ OpenAI provider có option `parallel-tool-calls` (tùy phiên bản thường ánh xạ sang `OpenAiChatOptions.parallelToolCalls(true)`). Tùy chọn này chủ yếu cho phép **mô hình đề xuất nhiều tool call trong một phản hồi**. Nó không phải switch biến vòng Java của `DefaultToolCallingManager` thành một executor song song.

Theo mã triển khai `DefaultToolCallingManager` được đối chiếu ở dòng Spring AI 2.1/main, nhiều tool call trong `AssistantMessage` được duyệt theo vòng `for` và callback được gọi trực tiếp từng cái. Đã có issue đề xuất hỗ trợ chạy song song ở manager; vì vậy **không được hứa Spring AI mặc định chạy song song chỉ vì model trả nhiều call**. Nếu phiên bản tương lai thêm executor/mode thực thi, hãy kiểm tra source/API của đúng dependency và test chứng minh có overlap.

## 2. Khi nào nên cho hai tool chạy cùng lúc?

Hai tác vụ chỉ được xem là độc lập nếu đồng thời đáp ứng:

1. **Không có phụ thuộc dữ liệu**: đầu vào của tool B không lấy từ kết quả của tool A.
2. **Không có quan hệ thứ tự nghiệp vụ**: A không bắt buộc phải commit trước B.
3. **Không tranh chấp tài nguyên gây thay đổi semantics**: không cùng sửa record, inventory hoặc hạn mức không đồng bộ.
4. **Caller có quyền với từng thao tác**: cùng một `ToolContext` không có nghĩa tất cả action đều được phép.
5. **Có budget tổng**: concurrency, timeout, rate limit, token/tool-call quota và chi phí được kiểm soát.
6. **Có cách ghép kết quả và lỗi rõ**: mỗi kết quả gắn đúng lời gọi hoặc tài nguyên đã yêu cầu.

Ví dụ các tác vụ có thể chạy độc lập:

- Tra trạng thái đơn hàng đã được xác thực và tra vận đơn bằng `shipmentId` **đã có sẵn trước fan-out**.
- Tra tồn kho ở ba kho độc lập để tổng hợp khả năng giao hàng.
- Tải ba bản ghi thuộc cùng phạm vi tenant mà backend đã kiểm tra quyền.
- Đọc thông tin khách hàng và quy tắc giá từ hai dịch vụ chỉ đọc mà không phụ thuộc output của nhau.

Ví dụ các tác vụ **không độc lập**:

- `findOrder(orderNumber)` rồi mới lấy `shipmentId` từ kết quả để gọi `findShipment(shipmentId)`.
- Trừ tồn kho rồi tạo đơn hàng: có thứ tự và transaction/saga.
- Cấp quyền rồi xuất dữ liệu dựa trên quyền vừa cấp.
- Hoàn tiền rồi gửi email xác nhận “đã hoàn tiền”.
- Hai yêu cầu cập nhật cùng tài khoản hoặc cùng dòng version mà không có cơ chế concurrency control.
- Tool phải chờ người dùng xác nhận trước khi side effect được thực hiện.

**Độc lập về kỹ thuật không đồng nghĩa độc lập về nghiệp vụ.** Hai HTTP endpoint khác nhau vẫn có thể dùng chung database hoặc quota phía backend.

## 3. Nhìn bài toán như đồ thị phụ thuộc (DAG)

Hãy biểu diễn mỗi tool/service step thành một nút và mỗi quan hệ “phải xong trước” thành một cạnh:

~~~mermaid
flowchart TD
  U["User: Tình trạng đơn và giao hàng?"] --> A["Xác thực caller + tra metadata order"]
  A --> B["Đọc OrderSummary"]
  A --> C["Đọc ShipmentSummary"]
  B --> D["Tổng hợp OrderOverview"]
  C --> D
  D --> M["Model tạo phản hồi"]
~~~

Trong sơ đồ, `B` và `C` có thể chạy đồng thời **sau khi A hoàn thành**. Không nên chạy `C` từ đầu nếu chưa có `shipmentId` hoặc chưa xác thực quyền đối với shipment. Một scheduler chỉ được fan-out các nút cùng cấp phụ thuộc; không chạy toàn bộ DAG cùng lúc.

So sánh:

~~~text
Tuần tự:
A ──▶ B ──▶ C ──▶ D
       250ms 320ms

Có fan-out sau A:
          ┌─ B: 250ms ─┐
A ────────┤             ├──▶ D
          └─ C: 320ms ─┘
~~~

Giả sử overhead khởi tạo/ghép nhỏ, đoạn B+C từ khoảng 570 ms giảm xuống gần 320 ms. **Tổng thời gian người dùng** còn có model round-trip, network, A, D và stream response nên không nhất thiết giảm cùng tỷ lệ.

## 4. Công thức ước tính lợi ích và những giới hạn

Với `n` công việc độc lập có thời gian `T1…Tn`:

\[
T_{\text{serial}} \approx \sum_{i=1}^{n} T_i
\]

\[
T_{\text{parallel}} \approx \max_i(T_i) + T_{\text{scheduler}} + T_{\text{contention}}
\]

Đây là xấp xỉ; phần gọi model trước/sau, transaction, serialization và rate limits cần cộng riêng. Trong thực tế:

- `T_parallel` bị chi phối bởi tool chậm nhất (“straggler”).
- Càng nhiều fan-out, xác suất có ít nhất một dependency chậm/lỗi càng tăng.
- Pool/connection lớn không đồng nghĩa throughput tăng vô hạn; database có thể bão hòa.
- Chạy nhiều tool cùng lúc không tự làm giảm số lần gọi tool hoặc token.
- Chạy nhanh hơn có thể giảm *latency* nhưng không giảm *giá provider* nếu prompt/model calls không đổi.
- Nếu model cần nhiều vòng để phụ thuộc kết quả trước, không thể cắt vòng chỉ bằng Java executor.

Ví dụ ba HTTP requests lần lượt mất 180, 220 và 280 ms: chạy tuần tự tốn khoảng 680 ms; chạy đồng thời lý tưởng gần 280 ms, cộng overhead. Nhưng nếu dịch vụ đích chỉ cho 2 requests đồng thời, request thứ ba phải đợi và thời gian thực có thể lớn hơn.

## 5. Lựa chọn tầng triển khai trước khi viết custom ToolCallingManager

Ưu tiên theo mức độ phức tạp:

| Cách triển khai | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| **Một `@Tool` tổng hợp, fan-out ở service** | Nhiều read-only dependencies biết trước, có cùng mục tiêu nghiệp vụ | Rõ policy, dễ test, ít sửa Spring AI internals |
| **Batch API ở service đích** | Backend hỗ trợ truy vấn nhiều ID trong một request | Giảm overhead mạng, đôi khi tốt hơn concurrency |
| **Application orchestration DAG** | Có nhiều bước phụ thuộc và checkpoint | Chủ động lịch chạy, cần quản lý state/history |
| **Custom concurrent tool-call execution** | Cần giữ nhiều tool call *do model đề xuất trong cùng reply* và thực thi song song | Phải bảo toàn ToolCall IDs, confirmation, limits, errors, traces, order |
| **Giữ mặc định tuần tự** | Side effect, dependencies, traffic ít hoặc chi phí kiểm soát quan trọng hơn latency | Đơn giản và dễ dự đoán nhất |

Nếu nghiệp vụ luôn cần hai nguồn độc lập để dựng một báo cáo, **tạo một tool nghiệp vụ rõ ngữ nghĩa** thường tốt hơn để model phải chọn hai tool kỹ thuật rồi dựa vào custom scheduler. Mô hình nhìn thấy một contract “getOrderOverview”; service quyết định gọi hai dependency song song khi an toàn.

## 6. Ví dụ `@Tool` tổng hợp: fan-out sau bước kiểm tra quyền

Ví dụ ứng dụng có sẵn hai service chỉ đọc: `OrderReadService` và `ShipmentReadService`. Backend tra một metadata record và xác thực quyền đầu tiên, lấy được cả `orderId` và `shipmentId`. Hai bước đọc sau đó không phụ thuộc kết quả lẫn nhau.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class OrderOverviewTools {

    private final OrderAccessService accessService;
    private final OrderReadService orderReadService;
    private final ShipmentReadService shipmentReadService;
    private final Executor toolIoExecutor;

    public OrderOverviewTools(
            OrderAccessService accessService,
            OrderReadService orderReadService,
            ShipmentReadService shipmentReadService,
            Executor toolIoExecutor) {
        this.accessService = accessService;
        this.orderReadService = orderReadService;
        this.shipmentReadService = shipmentReadService;
        this.toolIoExecutor = toolIoExecutor;
    }

    @Tool(description = """
            Xem tổng quan một đơn hàng và tình trạng giao hàng
            trong phạm vi caller hiện tại. Chỉ đọc, không thay đổi dữ liệu.
            """)
    public OrderOverview getOrderOverview(
            @ToolParam(description = "Mã đơn hàng chính xác")
            String orderNumber,
            ToolContext toolContext) {

        CallerContext caller = requireCaller(toolContext);

        // Bước có thứ tự: xác thực caller và lấy IDs đã được cấp quyền.
        AuthorizedOrderRef ref =
                accessService.requireVisibleOrder(caller, orderNumber);

        var orderFuture = CompletableFuture.supplyAsync(
                () -> orderReadService.readAuthorized(
                        caller, ref.orderId()),
                toolIoExecutor);

        var shipmentFuture = CompletableFuture.supplyAsync(
                () -> shipmentReadService.readAuthorized(
                        caller, ref.shipmentId()),
                toolIoExecutor);

        try {
            // Chỉ chờ hai công việc độc lập; giới hạn thời gian ở service.
            CompletableFuture.allOf(orderFuture, shipmentFuture)
                    .orTimeout(2, TimeUnit.SECONDS)
                    .join();
            return new OrderOverview(
                    orderFuture.join(), shipmentFuture.join());
        }
        catch (RuntimeException ex) {
            orderFuture.cancel(true);
            shipmentFuture.cancel(true);
            throw new OrderOverviewUnavailableException(
                    "Không thể tạo tổng quan đơn hàng.", ex);
        }
    }
}
~~~

`CallerContext`, `AuthorizedOrderRef`, `OrderOverview` và các service là kiểu do ứng dụng định nghĩa. `requireCaller` lấy danh tính tin cậy từ `ToolContext`; không lấy `tenantId` hoặc `isAdmin` từ model arguments. Ví dụ trên giả định order và shipment đều tồn tại: nếu đơn chưa có vận đơn, cần xử lý `shipmentId=null` bằng business policy thay vì gọi với `null`.

**Điểm quan trọng về timeout:** `CompletableFuture.orTimeout(...)` chỉ làm future chuyển sang trạng thái lỗi sau deadline; `cancel(true)` với các tác vụ `supplyAsync` **không bảo đảm** cắt được HTTP request hay giải phóng luồng ngay. Phải đặt timeout riêng ở HTTP client/DB và giới hạn deadline của toàn request; cancellation chỉ là tín hiệu best-effort. Nếu service dùng Reactor/non-blocking client, có thể dùng `Mono.zip(...)`/`timeout(...)`, nhưng phải kiểm tra cancellation của client và không gọi `block()` trên Netty event loop.

## 7. Thread pool riêng và backpressure

Dùng `ForkJoinPool.commonPool()` cho blocking HTTP/database calls có thể tranh tài nguyên với công việc khác. Với Spring Boot, nên có executor riêng cho các thao tác I/O này.

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ToolIoConfiguration {

    @Bean("toolIoExecutor")
    ThreadPoolTaskExecutor toolIoExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("tool-io-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Các con số 4/8/32 chỉ là ví dụ. Không dùng `Executors.newFixedThreadPool(8)` với queue không giới hạn rồi coi đó là hệ thống đã có backpressure. Khi pool và queue đã đầy, scheduler nên trả `RESOURCE_BUSY`/429 hoặc fallback theo policy, không chờ vô hạn.

Có **hai giới hạn khác nhau**:

- **Per-request fan-out:** tối đa bao nhiêu tool của một turn chạy đồng thời.
- **Global/per-tenant concurrency:** tổng tải đồng thời trên toàn instance và từng dependency.

Pool trên chỉ giới hạn tác vụ của **một instance**; nếu có nhiều replica, tổng tải có thể tăng gấp số replica. Dùng bulkhead/semaphore ở tầng service, rate limit theo tenant, connection pool và quota của backend. Không đặt semaphore/bộ đếm permission trong biến local rồi giả định nó áp dụng cho cả cluster.

## 8. ToolContext, thread-safety và propagation

Khi gọi hai service trên hai thread:

- `ToolContext` là input của lời gọi, nhưng object trong map có thể mutable. Chỉ truyền DTO ngữ cảnh **bất biến**.
- Không dùng shared `HashMap` hoặc mutable collector giữa tasks mà không đồng bộ.
- `SecurityContextHolder`, MDC và tracing context có thể là thread-local; `CompletableFuture.supplyAsync` **không tự bảo đảm** mang chúng sang worker thread.
- Truyền caller/tenant/request scope trực tiếp vào service methods và xác thực quyền tại service.
- Nếu cần trace liên tục, dùng Micrometer Context Propagation hoặc task decorator được dự án cấu hình, rồi kiểm chứng span parent-child thực tế.
- Không dùng lại `ToolContext` mutable giữa người dùng/tenant; mỗi request cần context riêng.

Ví dụ DTO ngữ cảnh:

~~~java
public record CallerContext(
        String subjectId,
        String tenantId,
        String requestId) {
}

static CallerContext requireCaller(ToolContext context) {
    if (context == null || context.getContext() == null) {
        throw new AccessDeniedException("Thiếu caller context.");
    }
    Object caller = context.getContext().get("caller");
    if (caller instanceof CallerContext trusted) {
        return trusted;
    }
    throw new AccessDeniedException("Thiếu caller context.");
}
~~~

Việc model “biết” orderId không cấp quyền đọc shipmentId. `ShipmentReadService.readAuthorized(...)` phải kiểm tra đúng caller, tenant và ACL, kể cả khi bước `accessService.requireVisibleOrder(...)` đã kiểm tra sơ bộ trước fan-out.

## 9. Lỗi trong một nhánh: fail-fast hay kết quả một phần?

Một cặp HTTP reads độc lập có thể có ba kết quả: cả hai thành công, một nhánh lỗi, hoặc cả hai lỗi. Quy tắc xử lý phải dựa trên nghiệp vụ.

| Hợp đồng | Khi một nhánh lỗi | Ví dụ |
| --- | --- | --- |
| **All-or-nothing** | Toàn bộ tool trả lỗi chuẩn hóa | Tính tổng thanh toán cần đủ mọi khoản |
| **Partial result** | Trả dữ liệu thành công + phần lỗi và cờ `partial=true` | Dashboard tổng hợp có thể chấp nhận thiếu vận đơn |
| **Fallback** | Chuyển sang nguồn thay thế đã được cấp phép | Tra cứu kho phụ khi kho chính tạm unavailable |
| **Queue/retry async** | Trả job ID và tiếp tục xử lý ở background | Đồng bộ nhiều kho lớn |

Ví dụ DTO rõ ràng:

~~~java
public record SourceResult<T>(
        String source,
        boolean available,
        T data,
        String errorCode) {
}

public record OrderOverviewPartial(
        SourceResult<OrderSummary> order,
        SourceResult<ShipmentSummary> shipment,
        boolean partial) {
}
~~~

Không trả “Thành công” nếu chỉ 1/2 nguồn hoàn tất mà nghiệp vụ cần cả hai. Cũng không để mô hình suy đoán shipment status khi shipment service lỗi. Trả `partial=true` và mô tả giới hạn dữ liệu hoặc yêu cầu retry có kiểm soát.

### Vấn đề fail-fast với fan-out

`CompletableFuture.allOf(...)` hoàn thành khi tất cả future kết thúc; exception của một nhánh làm aggregate result thất bại nhưng các nhánh khác có thể đã và vẫn đang thực thi. Timeout ở parent không tự rollback/cancel side effects ở child. Nếu cần fail-fast thật, phải thiết kế cancellation và các client timeout/circuit breaker tương ứng; với thao tác ghi phải xử lý compensation.

Với hai read-only tasks, có thể “collect all” và dùng kết quả một phần. Với side effect không thể hoàn tác, **không song song chỉ vì cần giảm latency**.

## 10. Giữ kết quả đúng theo tool-call ID và thứ tự ban đầu

Nếu mô hình đề xuất nhiều tool calls trong một reply, mỗi call có tên, arguments và thường có `id`. Ví dụ:

~~~json
{
  "tool_calls": [
    {"id": "call_A", "name": "getOrder", "arguments": "{\"orderNumber\":\"ORD-7\"}"},
    {"id": "call_B", "name": "getShipment", "arguments": "{\"shipmentId\":\"SHIP-4\"}"}
  ]
}
~~~

Khi thực thi đồng thời, `getShipment` có thể hoàn thành trước `getOrder`. **Không xây tool responses theo thứ tự hoàn thành** rồi vô tình gán `call_A` cho dữ liệu của `call_B`. Mỗi result phải giữ `toolCallId`, tên tool và vị trí index gốc.

Nguyên tắc tập hợp:

1. Đánh index theo vị trí trong danh sách assistant tool calls ban đầu.
2. Lưu kết quả cùng ID/ tên tool / outcome tương ứng.
3. Chờ/thu thập các tác vụ được phép chạy theo policy.
4. Sắp xếp lại theo index gốc trước khi tạo `ToolResponseMessage`.
5. Giữ nguyên assistant message có tool calls và một message chứa responses khớp ID ở conversation history.
6. Không đưa một raw result từ tool B vào entry của tool A chỉ vì nó đến sớm hơn.

Provider có thể yêu cầu ID hoặc có cơ chế thay thế khi thiếu ID; phải tuân thủ hợp đồng của provider/Spring AI đang dùng. Không sửa ID hoặc tự đổi tên callback trong lúc chạy.

## 11. Tình huống cần tránh: hai tool gọi cùng bản ghi ghi dữ liệu

Ví dụ model đề xuất:

~~~text
1. reserveInventory(orderId=42, item=A, qty=2)
2. reserveInventory(orderId=42, item=A, qty=3)
~~~

Nếu cả hai callback cùng kiểm tra “còn hàng” trước khi trừ kho, có thể oversell. Dù kết quả mô hình mong muốn là “đặt tổng 5”, hai request độc lập về JSON arguments nhưng **không độc lập về tài nguyên**.

Cần chọn một trong các hướng:

- Gộp thành một lệnh nghiệp vụ `reserveInventoryBatch` có transaction/invariant chung.
- Dùng optimistic locking/version hoặc row lock ở database.
- Dùng per-resource serial queue/actor để đảm bảo thứ tự.
- Gửi lệnh đến inventory service hỗ trợ idempotency/atomic reservation.
- Nếu không có cơ chế đảm bảo, giữ chạy tuần tự và vẫn kiểm tra race giữa **nhiều user turns**.

**Đồng thời hóa các side effect không có cơ chế đồng bộ là đổi hiệu năng lấy sai dữ liệu.** Bài tối ưu này ưu tiên truy vấn độc lập/chỉ đọc hoặc thao tác ghi đã được chứng minh an toàn.

## 12. Chính sách chọn chạy song song theo dependency và risk

Một scheduler có thể duy trì registry do ứng dụng quản lý:

| Thuộc tính | Mục đích |
| --- | --- |
| `toolName` | Khóa định danh callback |
| `sideEffect` | READ_ONLY / IDEMPOTENT_WRITE / NON_IDEMPOTENT |
| `resourceKey` | Tài nguyên hoặc lock key có thể bị tác động |
| `requiresApproval` | Có gate xác nhận hay không |
| `dependsOn` | Input cần kết quả từ bước nào |
| `timeout` | Deadline riêng cho tool |
| `bulkheadGroup` | Nhóm backend/connection quota |
| `maxConcurrency` | Mức đồng thời an toàn cho dependency |
| `retryPolicy` | Chỉ retry khi semantics cho phép |
| `authorizationPolicy` | Quyền cần có trên action/resource |

Mô hình có thể đề xuất tool list, nhưng **không được tự ghi `sideEffect=false`, `requiresApproval=false` hoặc `maxConcurrency=100` trong arguments để vượt policy**. Metadata quyết định được lấy từ catalog/server và resource state hiện hành.

Một chính sách khởi đầu bảo thủ:

- Chỉ đưa các **read-only tool** không phụ thuộc dữ liệu vào nhóm concurrent mặc định.
- Với write tool, chỉ cho phép concurrency khi business service công bố rõ cơ chế idempotency/locking.
- Nếu có approval pending, tạm dừng toàn bộ batch theo cơ chế confirmation của phiên bản dùng, không “cho đọc chạy trước” nếu hợp đồng yêu cầu atomic pause.
- Khi dữ liệu không đủ để chứng minh độc lập, fallback tuần tự hoặc hỏi thêm.


## 13. Muốn chạy song song nhiều tool call do model đề xuất thì sao?

Có hai trường hợp cần phân biệt:

**Trường hợp A — một tool nghiệp vụ fan-out bên trong:** `getOrderOverview` là một callback; implementation tự chạy hai HTTP reads đồng thời. `ToolCallingManager` nhìn thấy một tool response bình thường. Đây là cách minh họa ở mục 6, ít can thiệp vào internals Spring AI.

**Trường hợp B — model trả hai hoặc nhiều tool calls trong cùng `AssistantMessage`:** muốn thực thi chúng đồng thời thì phải có **manager/scheduler thực sự hỗ trợ concurrency**. Trong bản triển khai `DefaultToolCallingManager` đã đối chiếu, `executeToolCalls(...)` chạy từng callback theo vòng lặp; gọi API này từ hai thread hoặc bật `parallel-tool-calls` ở provider không tự biến batch thành song song.

Với Spring AI 2.x, để tự điều phối vòng tool call, có thể tắt auto tool loop ở từng request bằng:

~~~java
ChatClientResponse rawResponse = chatClient.prompt()
        .user(question)
        .options(chatOptions)
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .chatClientResponse();
~~~

Khi đó ứng dụng tự kiểm tra `rawResponse.chatResponse().hasToolCalls()`, phân loại call, thực thi và tạo message history cho round kế tiếp. Tài liệu Spring AI có ví dụ user-controlled execution với `ToolCallingManager.executeToolCalls(prompt, response)`; **ví dụ đó vẫn dùng manager mặc định nên không mặc nhiên là concurrent batch**.

Nếu thay bằng custom scheduler, phải tự đảm nhận các chức năng mặc định: tool resolution chỉ trong scope, schema validation, `ToolContext`, logging/tracing, exception processing, call limits, confirmation, `returnDirect`, conversation history và kiểm soát duplicate side effect. Không copy mỗi đoạn `CompletableFuture.allOf(...)` rồi gọi là tương đương với `ToolCallingManager`.

## 14. Thuật toán lập lịch cho một batch độc lập

Pseudocode ở dưới là **thiết kế ứng dụng**, không phải API dựng sẵn của Spring AI:

~~~text
handleToolBatch(prompt, assistantMessage, caller):
    calls = assistantMessage.toolCalls
    checkBatchSizeAndToolCallBudget(calls)
    requireAllConfirmationsResolvedOrPauseWholeBatch(calls)

    planned = []
    for index, call in enumerate(calls):
        callback = requireAttachedAllowedCallback(call.name)
        args = validateSchema(call.arguments)
        authorization.check(caller, call.action, args.resource)
        metadata = policyCatalog.forTool(call.name)
        planned.add(index, call.id, callback, args, metadata)

    groups = dependencyPlanner.buildWaves(planned)
    results = []
    for wave in groups:
        // Chỉ chạy đồng thời các call được chứng minh độc lập.
        futures = submitBounded(wave, deadline, quota)
        waveResults = waitAndCollect(futures)
        results.addAll(waveResults)

        if waveResults contain unsafe failure:
            stop scheduling next waves
            break

    // Sort theo index tool call ban đầu, không theo completion time.
    orderedResponses = sortByOriginalIndex(results)
    return appendAssistantCallAndToolResponses(prompt, orderedResponses)
~~~

Điểm khó không phải tạo futures, mà là chứng minh *wave nào thật sự độc lập*. Nếu mô hình không cung cấp được thông tin dependency hoặc tool catalog không mô tả semantics rõ, scheduler nên giữ tuần tự. Việc chia wave thường cần resource IDs, lock keys, side-effect classification và dữ liệu quyền lấy từ ứng dụng, không từ nội dung tự suy luận của mô hình.

Ở batch có một tool chờ xác nhận, Spring AI 2.1 Tool Call Confirmation **dừng toàn bộ reply trước khi thực thi**; custom scheduler phải giữ nguyên invariant đó. Không chạy các read-only tool trước khi hiển thị confirmation nếu pipeline đã cam kết “chưa tool nào của batch chạy trước quyết định”.

## 15. Trả tool responses đúng format để model hiểu

Spring AI dùng `ToolResponseMessage` để gửi kết quả callback về mô hình. Về nguyên tắc, mỗi `ToolResponseMessage.ToolResponse` phải khớp đúng tool-call ID và tool name.

Ví dụ phác thảo **chỉ cho bước tập hợp** sau khi custom executor đã hoàn tất và kiểm tra quyền:

~~~java
public record IndexedToolResult(
        int index,
        String toolCallId,
        String toolName,
        String content) {
}

List<ToolResponseMessage.ToolResponse> responses =
        indexedResults.stream()
                .sorted(Comparator.comparingInt(IndexedToolResult::index))
                .map(result -> new ToolResponseMessage.ToolResponse(
                        result.toolCallId(),
                        result.toolName(),
                        result.content()))
                .toList();

ToolResponseMessage responseMessage =
        ToolResponseMessage.builder()
                .responses(responses)
                .build();
~~~

`indexedResults` là danh sách đã được custom scheduler tạo ra. Code này **không** thay thế phần thực thi/callback policy của manager. Cần ghép vào lịch sử đầy đủ theo thứ tự:

~~~text
UserMessage
AssistantMessage(toolCalls: [call_A, call_B, ...])
ToolResponseMessage(responses: [result_A, result_B, ...])
AssistantMessage(final response hoặc tool calls tiếp)
~~~

Không tự tạo một lời gọi model mới với tool responses nhưng bỏ qua assistant message chứa tool calls: provider có thể báo lỗi vì kết quả không có lời gọi tương ứng. Trường hợp bị từ chối trước execution cần tool response lỗi/decision theo cơ chế được hỗ trợ, không tạo response “thành công giả”.

## 16. `returnDirect`, confirmation và giới hạn call trong batch

Có ba rule cần giữ khi custom hóa:

**`returnDirect`:** nếu reply chứa nhiều tool calls, Spring AI `ToolCallingAdvisor` chỉ trả trực tiếp tool results mà không gọi lại model khi **mọi tool thực thi trong batch đều yêu cầu return-direct** (và không có call bị từ chối). Một call `returnDirect=true` nằm cạnh call thường không làm cho toàn reply đột ngột kết thúc. Custom scheduler cần giữ semantics này.

**Approval:** `@Tool(requiresConfirmation=true)` từ Spring AI 2.1 là policy về việc **chưa chạy**, không phải policy về concurrency. Nếu một call cần confirmation, manager có thể pause toàn bộ reply. Custom scheduler không được “tối ưu” bằng cách chạy các nhánh khác trước và chỉ chờ nhánh ghi.

**Limits:** giới hạn số tool calls theo tool/tổng trong một turn phải áp dụng **trước khi dispatch wave**, đồng thời đếm cả những call trùng tên trong cùng batch. Với Spring AI 2.1, có thể cấu hình manager:

~~~java
ToolCallingManager manager = ToolCallingManager.builder()
        .maxCallsPerTool(3)
        .maxTotalToolCalls(8)
        .onLimitExceeded(ToolCallLimitBehavior.THROW)
        .build();
~~~

Ví dụ này cấu hình giới hạn cho manager mặc định, **không** tự kích hoạt concurrent execution. Nếu ứng dụng tự viết scheduler, phải tự enforcement tương đương hoặc dùng các thành phần được framework hỗ trợ khi có. Không tăng vô hạn `maxTotalToolCalls` chỉ để loại bỏ lỗi; một batch fan-out lớn có thể vượt quota downstream hoặc chi phí API.

## 17. Deadline: phân bổ thời gian của cả request

Một lỗi thường gặp là đặt `timeout=2s` cho từng tool nhưng cho phép model retry nhiều vòng không hạn định. Nếu caller chỉ chờ tối đa 5 giây, mỗi nhánh cần dùng **deadline còn lại**, không khởi tạo một timeout mới nguyên vẹn ở mỗi bước.

Ví dụ phân bổ:

~~~text
User request deadline: 5.0s
  Model round #1:      1.2s
  Authorization:       0.1s
  Parallel read group: max 1.5s
  Model round #2:      1.3s
  Serialization/margin: 0.9s
  Total:               5.0s
~~~

Đây là một budget minh họa, không phải cấu hình mặc định. Khi mô hình/phía backend đã tiêu nhiều thời gian hơn dự tính, phải kiểm tra `remainingDeadline` trước khi fan-out tiếp; nếu còn quá ít, trả lỗi/partial/queued theo hợp đồng, không bắt đầu tác vụ biết chắc quá hạn.

Phân biệt:

- **Connect timeout:** giới hạn thiết lập kết nối.
- **Read/response timeout:** chặn dependency treo.
- **Batch deadline:** giới hạn toàn bộ nhóm concurrently executing.
- **Model/tool loop deadline:** giới hạn cả lượt hội thoại.
- **Job deadline:** cho tác vụ chạy nền nếu đã chuyển sang asynchronous workflow.

Hủy một `CompletableFuture` không bảo đảm cắt side effect đã commit. Với thao tác ghi, timeout phải dẫn tới trạng thái “chưa rõ” để đối soát, không tự retry ngay.

## 18. Backpressure và bảo vệ từng backend

Giả sử một request fan-out ba service calls và 100 requests được gửi cùng lúc: tối đa có thể xuất hiện 300 calls tới dependencies. Điều đó có thể làm backend sập dù p95 latency đơn lẻ trước đây rất tốt.

Các lớp giới hạn cần phối hợp:

| Lớp | Ví dụ | Tác dụng |
| --- | --- | --- |
| Per-turn fan-out | Tối đa 2–3 tool reads song song | Không để một prompt bùng nổ |
| Executor queue | Bounded thread + queue | Tránh tăng bộ nhớ vô hạn |
| Bulkhead theo dependency | `inventory-read` tối đa 20 inflight | Không làm quá tải một service |
| Tenant/user quota | Max requests/tokens/tool calls | Công bằng và hạn chế lạm dụng |
| DB connection pool | HikariCP max pool size | Khống chế kết nối, nhưng không thay circuit breaker |
| Client retry policy | Backoff + jitter + số lần tối đa | Không nhân tải khi backend lỗi |
| Circuit breaker | Tạm ngừng gọi backend đang suy giảm | Tránh cascading failure |

Khi worker pool từ chối task do đầy, không chuyển sang chạy trực tiếp trên model/event-loop thread trừ khi đó là một quyết định có kiểm soát và an toàn; cách “CallerRuns” có thể làm nghẽn thread cần phục vụ nhiều request. Một policy rõ hơn là trả lỗi tạm thời `RESOURCE_BUSY` hoặc tiếp nhận job trong queue bền vững.

Không dùng một semaphore per-tenant lưu trong `ConcurrentHashMap` mãi mà không có eviction nếu tenant ID có cardinality không giới hạn. Chọn limiter được quản lý vòng đời và có quota theo chính sách hệ thống.

## 19. Không tạo race condition khi cập nhật trạng thái

Fan-out chỉ đọc đã cần tính tới consistency: đọc order lúc 10:00:00.1 và shipment lúc 10:00:00.4 có thể cho snapshot khác thời điểm. Đây không phải bug concurrency trong Java, mà là vấn đề **mức nhất quán dữ liệu**.

Các chiến lược:

- Với dashboard chỉ đọc chấp nhận eventual consistency: trả `retrievedAt`, `sourceVersion` và cảnh báo stale.
- Với báo cáo bắt buộc snapshot chung: truyền `asOf`/snapshot version hoặc dùng transaction/read view phù hợp.
- Với giao dịch tài chính: không ghép các kết quả đọc độc lập rồi coi là một commit nhất quán.
- Với cùng một record ghi: dùng optimistic lock/version, row lock, resource-level serialization hoặc lệnh batch nguyên tử.
- Với cross-service write: dùng saga/outbox/idempotency, không cố bọc mọi HTTP call trong một database transaction local.

Nếu kết quả từ hai nhánh mâu thuẫn, trả trạng thái *không nhất quán* hoặc yêu cầu xác minh lại; không để model tùy ý chọn kết quả “có vẻ đúng” nhất để khẳng định giao dịch đã hoàn tất.

## 20. Reactor/WebFlux: khi bất đồng bộ thật sự có lợi

Trong ứng dụng reactive, có thể chạy hai non-blocking network calls bằng `Mono.zip`:

~~~java
Mono<OrderOverview> overview(
        CallerContext caller, AuthorizedOrderRef ref) {

    Mono<OrderSummary> order =
            orderClient.readAuthorized(caller, ref.orderId());

    Mono<ShipmentSummary> shipment =
            shipmentClient.readAuthorized(caller, ref.shipmentId());

    return Mono.zip(order, shipment)
            .map(tuple -> new OrderOverview(
                    tuple.getT1(), tuple.getT2()))
            .timeout(Duration.ofSeconds(2));
}
~~~

Đây là ví dụ **service reactive**. Việc gọi method `@Tool` qua `ToolCallback` vẫn phụ thuộc hợp đồng callback và cơ chế framework/version; đừng mặc định trả một `Mono` từ mọi `@Tool` sẽ được chờ hoặc serialize như kết quả đã resolve. Nếu tool callback yêu cầu kết quả đồng bộ, cần adapter được framework hỗ trợ hoặc dùng service blocking ở executor phù hợp; **không gọi `block()` trên Netty event loop**.

`Mono.zip` cũng có semantics fail-fast/cancellation theo Reactor. Cần test khi một nguồn lỗi hoặc trả empty, khi subscriber cancel và khi dependency đã có side effect. Reactive không tự thay thế authorization, quota hay idempotency.

## 21. Chạy đồng thời nhiều conversation: bài toán khác

Khi 50 user requests cùng gọi một `ChatClient`, ứng dụng có concurrency ở **cấp request** ngay cả khi callback trong mỗi model reply vẫn tuần tự. Vì vậy:

- Không lưu `conversationId`, `CallerContext`, state advisor hoặc list kết quả vào field mutable singleton.
- Không tái sử dụng `ToolContext` của user A cho user B.
- Chỉ dùng shared `ChatClient`/service khi các dependencies của chúng thread-safe.
- Nếu giữ session memory, phân tách session ID theo user/tenant và kiểm tra quyền.
- Tránh chạy hai turn ghi dữ liệu của cùng conversation song song khi ứng dụng cần thứ tự hội thoại.
- Thực thi qua nhiều replica vẫn phải có quota/lock ở tầng dữ liệu hoặc gateway.

Một bài benchmark báo “100 concurrent requests đạt thông lượng cao” **không chứng minh** các tool call trong từng reply được chạy song song. Hai chiều concurrency cần được đo và test riêng.

## 22. Quan sát hiệu năng và chi phí đúng cách

Spring AI có Micrometer observation `spring.ai.tool` cho callback execution, `gen_ai.client.operation` cho model calls, và `spring.ai.chat.client` cho ChatClient. Có thể bổ sung metric ứng dụng:

| Metric | Ý nghĩa |
| --- | --- |
| `app.ai.batch.tool.count` | Số tool proposals/executions trong batch |
| `app.ai.batch.parallelism.max` | Số tasks đang active tối đa |
| `app.ai.batch.duration` | Thời gian từ dispatch wave đến khi collect |
| `app.ai.tool.wait.duration` | Thời gian chờ trong executor/queue |
| `app.ai.tool.timeout.count` | Nhánh quá deadline |
| `app.ai.tool.business.outcome` | SUCCESS/PARTIAL/DENIED/DEPENDENCY_FAILED |
| `app.ai.turn.model.calls` | Số model rounds trong turn |
| `app.ai.turn.duration` | End-to-end latency người dùng |
| `app.ai.turn.token.usage` | Token từ provider theo loại, nếu có |
| `app.ai.bulkhead.rejected` | Số task bị từ chối do quota |

Các tên `app.ai.*` là **metric đề xuất của ứng dụng**, không phải meter có sẵn của Spring AI. Không dùng `conversationId`, `userId`, raw URL, tool arguments hay `toolCallId` làm Prometheus label; đưa IDs vào trace/audit đã bảo vệ. Nếu có tracing xuyên executor, kiểm chứng context propagation tới child spans và tránh ghi payload nhạy cảm.

Đừng cộng timer của ChatClient + model + tool rồi gọi đó là tổng độ trễ, vì timer có thể lồng nhau. So sánh end-to-end p50/p95/p99, số model calls/turn, tool count/turn, backend load và chi phí token trước/sau tối ưu.

## 23. Phân tích chi phí: song song hóa không luôn rẻ hơn

Một phép so sánh nên có nhiều chỉ số hơn mỗi latency:

| Thay đổi | Có thể tốt hơn | Có thể tệ hơn |
| --- | --- | --- |
| Một model reply gọi nhiều tools | Ít model rounds hơn nếu model chủ động batch | Nhiều tool không cần thiết được gọi cùng lúc |
| Đồng thời ba reads | Giảm thời gian chờ | Tăng peak traffic/connection/quota |
| Tool tổng hợp trả DTO gọn | Model nhận ít metadata, dễ dùng | Backend thực hiện thêm logic aggregation |
| Partial result | UI có dữ liệu sớm | Model có thể suy đoán từ dữ liệu thiếu |
| Retry song song | Tăng khả năng có nhánh thành công nhanh | Retry storm, chi phí và duplicate side effects |
| Cache nguồn đọc | Ít HTTP calls/giảm latency | Stale data/ACL leakage nếu key sai |
| Batch API thay fan-out | Giảm overhead mạng và CPU | API backend có thể là điểm nghẽn tập trung |

**Tối ưu tổng chi phí/giá trị hoàn tất**, không chỉ giảm p50 latency. Nếu ba tool reads song song khiến toàn yêu cầu thất bại khi một nguồn quá tải, hiệu năng nhìn có vẻ nhanh hơn nhưng task completion thấp hơn.

Khi benchmark, giữ cố định model/version, dataset, tool catalog, backend load và quota; đo tối thiểu:

- `turn p50/p95/p99`, `tool p95`, queue wait và throughput.
- `total tool executions`, model rounds, tokens/input-output và ước tính cost.
- Error/timeout/partial-result rate và task completion rate.
- DB connections, downstream RPS, retry count và bulkhead rejections.

Không dùng một lần đo đơn lẻ để tuyên bố “nhanh hơn 2 lần”; chạy warm-up và nhiều lượt ở mức tải phù hợp, báo sample count, confidence và điều kiện đo.

## 24. Test chứng minh hai nhánh thực sự overlap

Test bằng thời gian tổng có thể bị flaky do CI/CPU khác nhau. Có thể dùng `CountDownLatch` để chứng minh cả hai service được gọi trước khi release:

~~~java
@Test
void independentReadsShouldStartBeforeEitherCompletes()
        throws Exception {

    CountDownLatch bothStarted = new CountDownLatch(2);
    CountDownLatch releaseReads = new CountDownLatch(1);

    // Hai fake read services dùng cùng hành vi:
    // bothStarted.countDown();
    // if (!releaseReads.await(2, TimeUnit.SECONDS)) {
    //     throw new AssertionError("Read timed out in fixture");
    // }
    // return DTO tổng hợp giả lập;

    try {
        CompletableFuture<OrderOverview> result =
                CompletableFuture.supplyAsync(
                        () -> overviewTools.getOrderOverview(
                                "ORD-TEST-1", trustedToolContext));

        assertThat(bothStarted.await(1, TimeUnit.SECONDS))
                .as("Hai nhánh phải bắt đầu trước khi bất kỳ nhánh nào xong")
                .isTrue();
        releaseReads.countDown();

        assertThat(result.get(3, TimeUnit.SECONDS))
                .isNotNull();
    }
    finally {
        releaseReads.countDown(); // Tránh treo fixture khi assertion thất bại.
    }
}
~~~

Đây là **test template**, giả định mock/fake `OrderReadService` và `ShipmentReadService` được cấu hình để gọi `bothStarted.countDown()` rồi chờ `releaseReads`. Nếu một service chỉ bắt đầu sau khi service kia kết thúc, điều kiện `bothStarted.await(...)` sẽ fail mà không cần đo sai số millisecond.

Bổ sung kiểm thử kết quả đúng theo ID, tenant scope và timeout, không chỉ overlap.

## 25. Ma trận kiểm thử cần có trước khi bật parallelism

| Kịch bản | Kỳ vọng |
| --- | --- |
| Hai read-only tools độc lập | Có overlap, kết quả đúng |
| Tool B phụ thuộc output tool A | Không chạy B trước khi A xong |
| Hai calls cùng resource ghi | Tuần tự/lock/idempotency, không lost update |
| Một nhánh bị `DENIED` | Không gửi request tới resource bị cấm |
| Một tool cần confirmation | Cả model reply pause trước khi có callback chạy theo contract 2.1 |
| Hai tool calls hoàn thành đảo thứ tự | `ToolResponseMessage` vẫn gắn ID/tên/index đúng |
| Một nhánh timeout | Nhánh khác có kết quả nhưng policy quyết định partial/error; client timeout thật |
| One-of-two failure | All-or-nothing hoặc partial result đúng hợp đồng |
| Executor đầy | Rejection/bulkhead hoạt động, không queue vô hạn |
| Nhiều tenant đồng thời | Không trộn `ToolContext`/SecurityContext/MDC |
| User disconnect | Không nhân đôi side effect; job đã nhận tiếp tục theo lifecycle riêng |
| Provider đưa hai tool calls cùng lượt | Không giả định callback mặc định chạy song song |
| Callback `returnDirect=true` xen callback thường | Batch semantics giữ nguyên |
| Tool call limit bị vượt | Không dispatch vượt quota; partial work được ghi/đối soát đúng |
| Một lời gọi được retry | Kết quả idempotency và metric không double-count |
| Model streaming/tool loop nhiều vòng | History tool-call/tool-response đầy đủ, không mất ID |

Với test integration của `ToolCallingManager` mặc định, xác minh hành vi của phiên bản đang dùng; không dựa vào tên `parallelToolCalls` để suy luận concurrency. Với custom scheduler, test cả error-result serialization, observability context propagation, callback resolution và cancellation.

## 26. Checklist áp dụng trong dự án

- [ ] Vẽ dependency DAG cho các tool/service steps.
- [ ] Chỉ fan-out những nhánh không phụ thuộc dữ liệu và không xung đột side effect.
- [ ] Phân biệt “model đề xuất nhiều tool calls” với “application thực thi cùng lúc”.
- [ ] Xác minh behavior của Spring AI `DefaultToolCallingManager` theo version thực tế.
- [ ] Ưu tiên composite `@Tool` hoặc batch service API trước khi tự viết manager.
- [ ] Giữ `ToolContext`/caller bất biến, check authz cho từng tool và từng resource.
- [ ] Không đưa mutable request state vào singleton/thread-local không được propagate.
- [ ] Dùng executor riêng, bounded queue, per-request fan-out và per-backend quota.
- [ ] Có timeout ở client, batch deadline, total turn deadline và cancellation policy.
- [ ] Nếu custom scheduler, bảo toàn ID, thứ tự, error mapping, `returnDirect`, confirmation, call limits và history.
- [ ] Chỉ retry tác vụ idempotent, có backoff và đối soát nếu kết quả không chắc.
- [ ] Xác định khi nào trả partial, khi nào fail cả batch.
- [ ] Có kiểm soát consistency/snapshot nếu các read song song cần cùng thời điểm dữ liệu.
- [ ] Đo p95/p99, queue wait, backend RPS, tool count, model rounds, token cost và task completion.
- [ ] Có test overlap bằng latch, test đảo completion order, timeout, bulkhead và cross-tenant.
- [ ] Đặt rollout/canary và rollback nếu latency giảm nhưng lỗi hoặc downstream load tăng.

## Tài liệu tham khảo

- [Spring AI 2.1 — Tool Calling và Tool Calling Loop](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1 — ToolCallingAdvisor, user-controlled execution và returnDirect](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI 2.1 — Tool Call Limits](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/reference.html)
- [Spring AI — OpenAI Chat Options: parallel-tool-calls](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html)
- [Spring AI source — DefaultToolCallingManager](https://github.com/spring-projects/spring-ai/blob/main/spring-ai-model/src/main/java/org/springframework/ai/model/tool/DefaultToolCallingManager.java)
- [Spring AI issue #5195 — Thảo luận thực thi nhiều tool call đồng thời](https://github.com/spring-projects/spring-ai/issues/5195)
- [JDK — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Project Reactor — Mono.zip](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)

Chạy nhiều tool đồng thời là một **quyết định kiến trúc của ứng dụng**, không phải hệ quả tự động khi mô hình sinh một batch tool calls. Hãy nhận diện dependency trước, ưu tiên fan-out các phép đọc độc lập trong service, dùng executor và quota có giới hạn, bảo toàn ngữ cảnh người gọi, xử lý deadline/error/partial response minh bạch và kiểm thử tính đúng đắn dưới tải. Nếu phải thay toàn bộ batch execution của Spring AI, hãy giữ đầy đủ quy tắc tool-call IDs, confirmation, quyền thực thi, kết quả và history. **Giảm độ trễ chỉ có giá trị khi chi phí, mức tải và kết quả nghiệp vụ vẫn được kiểm soát.**
