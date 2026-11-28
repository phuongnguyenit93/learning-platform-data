# Phân biệt số token, chi phí mô hình và chi phí hệ thống được gọi

Trong một ứng dụng **Spring AI Tool Calling**, một câu hỏi của người dùng có thể kích hoạt nhiều lần gọi mô hình, nhiều lời gọi `@Tool` hoặc `ToolCallback`, và những request REST/SDK đến các dịch vụ nghiệp vụ khác nhau. Nếu chỉ xem chỉ số “total tokens” từ một response, chúng ta chưa biết yêu cầu đó thực sự tốn bao nhiêu tiền; nếu chỉ xem hóa đơn API của mô hình, chúng ta vẫn chưa thấy chi phí hệ thống mà tool đã gọi.

Cần phân biệt rõ **ba đại lượng**:

1. **Số token sử dụng**: đơn vị đo đầu vào/đầu ra của những lần gọi mô hình, được model provider báo qua usage metadata.
2. **Chi phí mô hình**: số tiền ước tính hoặc thực tế phải trả cho model provider, phụ thuộc bảng giá theo model, loại token, cache, modality và điều kiện tính phí.
3. **Chi phí hệ thống được gọi**: tiền, tài nguyên và độ trễ phát sinh khi `ToolCallback` gọi REST API, SDK, database, vector store, dịch vụ thanh toán hoặc hạ tầng nội bộ.

Ba đại lượng có quan hệ nhưng **không thể thay thế lẫn nhau**. Một tool call không nhất thiết tiêu thụ thêm token tại thời điểm thực thi, nhưng kết quả của nó có thể làm tăng token đầu vào của lượt model kế tiếp. Ngược lại, một SDK có thể tính tiền cho mỗi request dù không có LLM nào tham gia.

Bài viết giải thích cách ghi nhận chính xác theo từng lần gọi model, từng lần gọi tool và từng lượt yêu cầu của người dùng trong **Spring AI 2.1.0**, sau đó dùng những số liệu này để xây dựng ngân sách, cảnh báo và kiểm thử.

## 1. Một lượt người dùng có thể tạo nhiều lần gọi

Xét câu hỏi:

> “Kiểm tra tồn kho SKU-100, tính phí giao tới Hà Nội và cho tôi biết có thể giao ngay không.”

Ứng dụng có hai công cụ:

- `lookupInventory(sku)` gọi dịch vụ tồn kho.
- `estimateShipping(sku, destination)` gọi dịch vụ vận chuyển.

Trong chế độ `ChatClient` có `ToolCallingAdvisor`, một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant M as ChatModel
    participant T as ToolCallingManager
    participant I as Inventory REST
    participant S as Shipping SDK

    U->>C: Hỏi tồn kho và phí giao
    C->>M: Model call #1 (prompt + tool definitions)
    M-->>C: Tool call: lookupInventory
    C->>T: Thực thi tool
    T->>I: GET tồn kho
    I-->>T: Số lượng khả dụng
    T-->>C: Tool result
    C->>M: Model call #2 (history + kết quả tồn kho)
    M-->>C: Tool call: estimateShipping
    C->>T: Thực thi tool
    T->>S: Tính phí vận chuyển
    S-->>T: Phí giao dự kiến
    T-->>C: Tool result
    C->>M: Model call #3 (history + hai tool results)
    M-->>C: Câu trả lời cuối
    C-->>U: Tồn kho, phí giao, thời gian dự kiến
~~~

Trong ví dụ có:

- **Một lượt yêu cầu của người dùng** (`user turn`).
- **Ba lần gọi ChatModel** (`model calls`).
- **Hai tool calls** do mô hình yêu cầu.
- **Hai thao tác hệ thống bên ngoài** tại REST API và SDK, chưa kể retry hoặc những call nội bộ khác.

Nếu muốn lập ngân sách cho “một lượt”, cần cộng **đúng tất cả các đơn vị phát sinh** chứ không chỉ phản hồi cuối.

## 2. Định nghĩa các lớp số đo

| Đại lượng | Đơn vị | Nguồn dữ liệu | Ý nghĩa |
|---|---|---|---|
| Input/prompt tokens | token | Model provider qua `Usage` | Token đầu vào của một lần gọi model |
| Output/completion tokens | token | Model provider qua `Usage` | Token mô hình tạo ở lần gọi đó |
| Total tokens | token | `Usage.getTotalTokens()` | Tổng token được định nghĩa theo usage của provider/framework |
| Cached input tokens | token | `Usage` cache metrics hoặc native usage | Phần input được đọc/ghi qua prompt cache |
| Model cost | tiền | Bảng giá + usage hoặc hóa đơn provider | Chi phí dùng mô hình |
| Tool invocation count | lần | `ToolCallingManager` hoặc tool service | Số lần công cụ được gọi |
| External request count | lần | HTTP client/SDK adapter | Số request thật đến dịch vụ |
| External provider cost | tiền | Bảng giá/hóa đơn API bên ngoài | Phí dịch vụ được tool gọi |
| Internal execution cost | tiền hoặc tài nguyên | Hệ thống hạ tầng/FinOps | CPU, RAM, network, storage, database, vận hành |
| End-to-end latency | thời gian | Trace từ request đến response | Thời gian người dùng chờ; không phải chi phí tiền |

**Không có công thức chung “1 token = một số tiền cố định”.** Token chỉ là đơn vị sử dụng. Giá phụ thuộc vào model cụ thể và loại token; nhiều dịch vụ không định giá theo token.

### Phân biệt ba loại giới hạn

- **Context window**: số token mà model có thể nhận/xử lý trong một lần gọi, theo giới hạn model.
- **Rate limit/quota**: hạn mức request hoặc token trong một khoảng thời gian do provider áp dụng.
- **Ngân sách chi tiêu**: mức tiền/tài nguyên ứng dụng tự đặt cho người dùng, tenant, tác vụ hoặc tháng.

Một request có thể hợp lệ về context window, chưa chạm rate limit, nhưng vẫn vượt ngân sách tiền mà ứng dụng cho phép.

## 3. Đọc token usage từ ChatResponse trong Spring AI

Spring AI cung cấp `ChatResponseMetadata` và `Usage`. Với `ChatClient.call()`, cần lấy `chatResponse()` thay vì chỉ `content()` nếu muốn có metadata.

~~~java
ChatResponse response = chatClient.prompt()
    .user("Tra cứu tồn kho SKU-100 tại Hà Nội.")
    .tools(inventoryTools)
    .call()
    .chatResponse();

if (response == null || response.getMetadata() == null) {
    throw new IllegalStateException(
        "Không có metadata để ghi nhận usage"
    );
}

Usage usage = response.getMetadata().getUsage();

if (usage != null) {
    Integer input = usage.getPromptTokens();
    Integer output = usage.getCompletionTokens();
    Integer total = usage.getTotalTokens();

    usageRecorder.record(
        response.getMetadata().getId(),
        response.getMetadata().getModel(),
        input,
        output,
        total
    );
}
~~~

`usageRecorder` là service ghi sổ đo do ứng dụng tự triển khai. Trong ứng dụng thực tế, hãy xử lý `null` và trường hợp provider không trả usage theo chính sách: đánh dấu `UNKNOWN`/`UNREPORTED` thay vì lặng lẽ xem là 0.

Các thuộc tính quan trọng:

~~~java
Usage usage = response.getMetadata().getUsage();

Integer promptTokens = usage.getPromptTokens();
Integer completionTokens = usage.getCompletionTokens();
Integer totalTokens = usage.getTotalTokens();

Long cacheRead = usage.getCacheReadInputTokens();
Long cacheWrite = usage.getCacheWriteInputTokens();

Object providerSpecific = usage.getNativeUsage();
~~~

`getNativeUsage()` chứa đối tượng riêng của provider nếu có. Vì các provider có cấu trúc báo cáo khác nhau, không nên cast nó sang một lớp vendor cố định trong code dùng chung cho nhiều model.

**Lưu ý phiên bản:** `getCacheReadInputTokens()` và `getCacheWriteInputTokens()` có trong Spring AI 2.x; khả năng trả số liệu phụ thuộc provider. Giá trị `null` là “không có số liệu”, không nhất thiết là “không sử dụng cache”.

## 4. Usage của một model call khác usage của toàn tool loop

Đây là điểm rất dễ dẫn đến tính sai:

**Trong Spring AI 2.1.0, `ChatResponse.getMetadata().getUsage()` nhận được sau một vòng `ChatClient` có tool calling đã bao gồm usage cộng dồn của các model calls trong vòng đó.** Nó không chỉ là số token của model call cuối cùng.

Ví dụ minh họa:

| Model call | Tác vụ | Input tokens | Output tokens | Total tokens |
|---|---|---:|---:|---:|
| #1 | Model chọn `lookupInventory` | 1.800 | 200 | 2.000 |
| #2 | Model chọn `estimateShipping` | 2.600 | 300 | 2.900 |
| #3 | Model trả lời cuối | 3.100 | 500 | 3.600 |
| **Tổng một vòng ChatClient** | | **7.500** | **1.000** | **8.500** |

Khi dùng `ChatClient.call().chatResponse()` với `ToolCallingAdvisor`, `Usage` của response cuối có thể cho số tổng `7.500 / 1.000 / 8.500`.

Trong khi đó, metric của `ChatModel` đo từng lần gọi: #1, #2 và #3.

### Quy tắc tránh đếm trùng

Chọn **một nguồn chuẩn** cho mỗi mục đích:

- **Báo cáo tổng một exchange**: lấy cumulative usage ở response cuối của `ChatClient`.
- **Phân tích từng model call**: lấy usage ở lớp `ChatModel` hoặc advisor **bên trong** vòng tool calling.
- **Đối soát billing**: lưu từng request ID và usage cấp provider; tính tổng từ ledger một lần.

**Sai:** cộng cumulative `8.500` ở response cuối với ba metric per-call `2.000 + 2.900 + 3.600`. Kết quả `17.000` là đếm hai lần cùng một mức sử dụng.

**Đúng:** `8.500` là tổng đã bao gồm ba model calls.

Spring AI dùng `UsageCalculator` để tổng hợp usage trong các vòng nhiều bước, bao gồm số liệu cache chuẩn hóa. `getNativeUsage()` có thể là `null` sau khi usage từ nhiều model calls được gộp, vì không thể hợp nhất tùy ý các kiểu native usage của từng provider.

### “Một exchange” chưa chắc bằng “một lượt người dùng” của sản phẩm

Một HTTP request của ứng dụng có thể gọi nhiều `ChatClient` độc lập, ví dụ model A phân loại ý định, model B xử lý tool loop rồi model C kiểm tra định dạng. Cumulative usage của riêng model B không gồm các lần gọi A và C.

Hãy định nghĩa `turnId` ở application boundary, gắn tất cả hoạt động trong cùng tác vụ vào đó và tính tổng theo ledger. Không phụ thuộc vào việc API cuối cùng chỉ trả một `ChatResponse`.

## 5. Token usage không phải hóa đơn tiền

Chi phí mô hình thường được tính theo giá riêng cho input/output hoặc nhiều nhóm input khác nhau. Một công thức khái quát:

~~~text
ModelCost =
    UncachedInputTokens × InputPrice
  + CachedReadTokens   × CachedReadPrice
  + CacheWriteTokens   × CacheWritePrice/Adjustment
  + OutputTokens       × OutputPrice
  + OtherBillableUnits × CorrespondingPrice
~~~

Các giá ở công thức phải quy về **cùng đơn vị** (ví dụ USD/token). Nếu bảng giá niêm yết theo một triệu token, chia cho `1.000.000` để có đơn giá/token.

**Không dùng công thức trên như quy tắc tính phí chung cho mọi provider.** Các nhà cung cấp khác nhau có thể tính cached input, cache creation, reasoning tokens, audio, ảnh hoặc batch processing theo cách khác. Một số loại token được **bao gồm** trong prompt/completion tổng, không được cộng thêm như một loại token mới. Hãy tạo price adapter theo provider/model/phiên bản bảng giá.

### Ví dụ giả định: token giống nhau, giá khác nhau

Giả sử cùng một model call sử dụng:

- Input: 2.000 token.
- Output: 500 token.
- Total: 2.500 token.

| Giá giả định | Đơn giá input/1M | Đơn giá output/1M | Chi phí model call |
|---|---:|---:|---:|
| Model A | $1 | $4 | $0,004 |
| Model B | $3 | $12 | $0,012 |
| Model C | $0,50 | $2 | $0,002 |

Vì cùng lượng token vẫn có thể tạo ra các mức chi phí khác nhau, **không thể đo chi phí chỉ bằng `getTotalTokens()`**. Bảng chỉ là phép minh họa, không đại diện cho giá hiện hành của bất kỳ nhà cung cấp nào.

### Mã Java ước tính cơ bản

Dùng `BigDecimal` để tránh lỗi làm tròn khi tính tiền:

~~~java
record TextModelRate(
    BigDecimal inputUsdPerMillion,
    BigDecimal outputUsdPerMillion
) {}

static BigDecimal estimateBasicModelUsd(
        long promptTokens,
        long completionTokens,
        TextModelRate rate) {

    BigDecimal inputUsd = BigDecimal.valueOf(promptTokens)
        .multiply(rate.inputUsdPerMillion());

    BigDecimal outputUsd = BigDecimal.valueOf(completionTokens)
        .multiply(rate.outputUsdPerMillion());

    return inputUsd.add(outputUsd)
        .divide(
            BigDecimal.valueOf(1_000_000L),
            8,
            RoundingMode.HALF_UP
        );
}
~~~

Đây là bộ tính **chi phí text cơ bản**, chỉ dùng khi giá input/output thông thường là đủ. Nó chưa xử lý cached tokens, audio, reasoning-specific pricing, thuế, minimum charge hoặc các điều khoản thanh toán của nhà cung cấp.

Bảng giá cần lưu `provider`, `model`, `effectiveFrom`, `currency` và `priceVersion`. Khi nhà cung cấp đổi giá, vẫn phải có khả năng tính lại bản ghi cũ theo đúng giá tại thời điểm sử dụng.

## 6. Prompt cache, reasoning và các loại token chuyên biệt

Một usage tổng có thể che đi nhiều loại token được tính phí khác nhau.

| Nhóm | Ý nghĩa | Cách dùng khi tính phí |
|---|---|---|
| Input tokens thông thường | Nội dung prompt, history, tool schemas, tool results | Dùng đơn giá input theo provider/model |
| Cached read input tokens | Phần prompt được đọc từ cache | Áp dụng giá cache-read nếu có |
| Cache write input tokens | Phần prompt mới được ghi vào cache | Áp dụng quy tắc cache-write riêng của provider |
| Output/completion tokens | Nội dung mà model tạo ra | Dùng đơn giá output theo provider/model |
| Reasoning tokens | Token suy luận nội bộ mà một số provider có báo cáo | Xác định có nằm trong output tokens hoặc được tính riêng không |
| Audio/image/video units | Đơn vị cho modality khác text | Theo hợp đồng/bảng giá tương ứng |

Không lấy `getPromptTokens() + getCacheReadInputTokens()` làm tổng input nếu cached tokens **đã nằm trong** prompt tokens: phép cộng đó đếm trùng. Tương tự, reasoning tokens thường là một thành phần trong usage output chứ không phải lúc nào cũng là một khoản cộng độc lập.

Ví dụ giả định khi provider xác nhận `cachedRead` là tập con của `promptTokens`:

~~~text
Input tokens = 5.000
  - cached read = 1.000
  - non-cached = 4.000
Output tokens = 1.000

Giá giả định:
  - input thường: $1 / 1M
  - cache read:  $0,25 / 1M
  - output:      $4 / 1M

Model cost = (4.000 × 1 + 1.000 × 0,25 + 1.000 × 4)
             / 1.000.000
           = $0,00825
~~~

Đây là phép tính áp dụng **chỉ khi** cấu trúc usage của provider và bảng giá xác nhận sự phân loại trên. Với provider khác, phải điều chỉnh price adapter.

Trong Spring AI 2.1.0, `Usage.getCacheReadInputTokens()` và `getCacheWriteInputTokens()` là API thống nhất; số liệu native có thể bổ sung breakdown theo modality hoặc reasoning. Khi cumulative usage gộp nhiều model calls, hãy giữ các bản ghi mỗi lần gọi nếu cần native breakdown để tính tiền thật sát hóa đơn.

## 7. Tool gọi REST/SDK có chi phí riêng, không nằm trong token usage

Một `@Tool` có thể tra cứu database, gọi API trả phí hoặc chạy thuật toán nhiều CPU:

~~~java
public class InventoryTools {

    private final InventoryService service;

    @Tool(
        description = "Tra cứu số lượng tồn kho theo SKU"
    )
    public StockBalance lookupInventory(
            @ToolParam(description = "Mã SKU") String sku,
            ToolContext context) {

        Actor actor = requireAuthenticatedActor(context);
        return service.getBalance(actor, sku);
    }
}
~~~

Lời gọi `service.getBalance(...)` có thể thực hiện một hoặc nhiều database queries, cache lookups và HTTP requests. Các hoạt động đó **không tự động tạo token** chỉ vì chúng được gọi từ tool. Nhưng chúng có thể có phí dịch vụ hoặc chi phí hạ tầng.

Đặc biệt, nếu tool tự gọi một mô hình phụ (ví dụ embeddings hoặc phân loại văn bản), lần gọi đó **cũng có model usage riêng** và phải được ghi trong phần model cost của tác vụ, thay vì xếp toàn bộ vào phí API thông thường.

### Ba loại chi phí thường nằm phía sau tool

| Loại | Ví dụ | Cách đo |
|---|---|---|
| Phí API của bên thứ ba | Phí mỗi lần geocoding, search hoặc dịch vụ vận chuyển | Từ response/hóa đơn/rate card của vendor |
| Tài nguyên nội bộ | Database CPU, Redis, egress, hàng đợi, storage | Infra metrics, cloud billing, unit-cost allocation |
| LLM phụ do tool gọi | Tool dùng embedding model hoặc một ChatModel khác | Usage/provider cost của chính model call đó |

Không tự suy ra “mỗi tool call = một số token”. Một tool trả JSON lớn có thể làm **tăng token đầu vào của model call kế tiếp**, nhưng đó là chi phí token của model call kế tiếp, không phải token “đã dùng trong REST call”.

### Retry và fan-out

Một tool call có thể thực hiện ba lần request HTTP do retry:

~~~text
ToolCall ID: call_inventory_123
  HTTP attempt 1 -> timeout
  HTTP attempt 2 -> 503
  HTTP attempt 3 -> 200
~~~

Ở cấp Spring AI: **một tool call**. Ở cấp REST gateway: **ba attempts**. Nếu vendor tính phí theo mỗi attempt, tổng chi phí có thể gồm cả các request thất bại. Vì vậy cần ghi các `attemptId`/`providerRequestId` riêng thay vì dựa duy nhất vào tool call ID.

## 8. Ví dụ tổng hợp chi phí của một lượt

Trở lại tác vụ tồn kho và phí giao ở đầu bài. Số liệu dưới đây đều **giả định**, phục vụ cách tính:

| Thành phần | Lượng sử dụng | Đơn giá giả định | Thành tiền |
|---|---|---|---:|
| Model input | 7.500 tokens | $2 / 1M tokens | $0,015 |
| Model output | 1.000 tokens | $8 / 1M tokens | $0,008 |
| Inventory API | 1 request | $0,004 / request | $0,004 |
| Shipping SDK | 1 request | $0,001 / request | $0,001 |
| Infra phân bổ | 1 lượt | $0,0015 / lượt | $0,0015 |
| **Tổng chi phí ước tính** | | | **$0,0295** |

Các phép tính:

~~~text
ModelCost = 7.500 × (2 / 1.000.000)
          + 1.000 × (8 / 1.000.000)
          = $0,023

ExternalCost = $0,004 + $0,001 = $0,005

InfrastructureCost = $0,0015

EstimatedTurnCost = $0,023 + $0,005 + $0,0015
                  = $0,0295
~~~

Nếu chỉ nhìn `8.500 tokens`, không thể biết tổng là `$0,0295`. Nếu chỉ nhìn hóa đơn model `$0,023`, lại thiếu phí hệ thống bên ngoài và infra.

Ngược lại, những chi phí như nhân sự, vận hành nền tảng, hỗ trợ khách hàng hoặc cam kết năng lực có thể là **chi phí phân bổ** chứ không tính chính xác theo từng request. Trong báo cáo, nên tách `direct cost` và `allocated cost`, tránh trình bày ước lượng như số tiền đã được provider thu thực tế.

## 9. Thiết kế cost ledger theo model call, tool attempt và turn

Để có thể audit và đối soát, ứng dụng nên lưu một số bản ghi đo độc lập.

### 9.1. Bản ghi model usage

~~~text
ModelUsageEvent
  turnId
  conversationId
  modelCallId
  providerRequestId (nếu có)
  provider
  model
  startedAt, finishedAt
  promptTokens, completionTokens, totalTokens
  cacheReadTokens, cacheWriteTokens
  usageSource = PROVIDER_REPORTED | ESTIMATED | UNKNOWN
  priceVersion
  estimatedModelCost
  status = COMPLETED | FAILED | CANCELLED | UNKNOWN
~~~

Giữ `modelCallId` hoặc `providerRequestId` để tránh ghi trùng khi nhận lại event từ queue, trace exporter hoặc retry. Khi response bị lỗi trước lúc nhận usage, không tự gán `0 tokens` vì provider có thể đã xử lý và tính phí.

### 9.2. Bản ghi tool execution

~~~text
ToolExecutionEvent
  turnId
  toolCallId
  toolName
  attemptId
  remoteRequestId (nếu có)
  targetSystem
  startedAt, finishedAt
  outcome
  meteredUnits
  vendorFee
  infrastructureEstimate
  priceVersion
~~~

Phân biệt `toolCallId` với `attemptId`. Một tool có thể tạo nhiều remote requests; một remote request được retry có thể xuất hiện nhiều lần trong HTTP metrics nhưng chỉ được vendor tính một lần hoặc nhiều lần tùy hợp đồng.

### 9.3. Bản ghi lượt người dùng

~~~text
TurnCostSummary
  turnId
  userScopeKey / tenantScopeKey (giới hạn quyền truy cập)
  modelCallCount
  toolCallCount
  externalAttemptCount
  promptTokensTotal
  completionTokensTotal
  modelCostEstimated
  externalCostObserved
  infrastructureCostAllocated
  totalCostEstimated
  budgetLimit
  budgetRemaining
  currency
  reconciliationStatus
~~~

**Một nguồn sự thật:** lưu event chi tiết và aggregate theo `turnId`. Nếu đồng thời lưu cumulative usage ở `ChatClient` và từng `ModelUsageEvent`, cần phân loại bản ghi tổng là **summary**, không coi nó là event mới để cộng thêm tiền.

## 10. Quan sát bằng Micrometer trong Spring AI 2.1.0

Spring AI có tích hợp observability trên nền Spring/Micrometer cho `ChatClient`, advisors, `ChatModel` và tool calling.

| Observation / metric | Đối tượng | Dùng để |
|---|---|---|
| `spring.ai.chat.client` | Một lời gọi ChatClient `call()` hoặc `stream()` | Đo end-to-end invocation |
| `spring.ai.advisor` | Advisor trong chain | Theo dõi thời gian xử lý advisor |
| `gen_ai.client.operation` | Một model execution | Model latency, provider/model, status |
| `gen_ai.client.token.usage` | Token usage của một model call | Theo dõi input/output/total tokens |
| `spring.ai.tool` | Một lần thực thi tool | Thời gian thực thi, tool name, error |
| HTTP client, DB, VectorStore observations | Dịch vụ phía sau tool | Đo attempt, latency, lỗi, tài nguyên |

Các chỉ số trên **không tự cộng thành hóa đơn tiền**. Spring AI cho số đo kỹ thuật; ứng dụng cần bổ sung rate card và hệ thống billing của từng dịch vụ.

Trong Prometheus, metric token usage có thể được xuất theo tên:

~~~text
gen_ai_client_token_usage_total
~~~

với nhãn `gen_ai_token_type` gồm `input`, `output`, `total`. Để tránh đếm trùng, khi tính tổng hãy dùng **chỉ `total`** hoặc cộng **`input + output`**, không cộng cả ba.

Ví dụ truy vấn PromQL theo model:

~~~promql
sum by (gen_ai_request_model) (
  rate(
    gen_ai_client_token_usage_total{
      gen_ai_token_type="total"
    }[5m]
  )
)
~~~

Kết quả biểu diễn **token/giây** trên cửa sổ 5 phút; nhân với `60` nếu muốn token/phút. Nhãn exporter phụ thuộc convention/phiên bản Micrometer và backend quan sát; hãy xác minh tên metric thật của ứng dụng trước khi cấu hình dashboard.

### Dùng Spring Boot Actuator

Một cấu hình cơ bản:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.tags.application=order-assistant
~~~

Cấu hình chỉ là nền tảng metrics; cần bảo vệ endpoint `/actuator/prometheus` ở tầng mạng/xác thực theo chính sách production. Tracing qua OpenTelemetry/Zipkin/collector yêu cầu dependencies và cấu hình tracing riêng.

### Đừng đưa ID cá nhân vào metric tags

Không đặt `userId`, `turnId`, `conversationId`, `orderNumber`, raw prompt, tool arguments hoặc API token vào nhãn của Prometheus counter. Chúng có cardinality lớn và có thể chứa dữ liệu nhạy cảm.

Sử dụng những nhãn có tập giá trị hữu hạn như `provider`, `model`, `toolName`, `outcome`, `environment`. Nếu cần tra cứu theo lượt, lưu thông tin đã kiểm soát vào ledger/traces với retention và quyền truy cập riêng.

## 11. Quan sát từng model call mà không đếm trùng usage

Có hai điểm quan sát phù hợp:

**Bên ngoài tool loop**: nhận `ChatResponse` cuối từ `ChatClient` và ghi một dòng **cumulative usage** cho exchange.

~~~java
ChatResponse response = chatClient.prompt()
    .user(question)
    .tools(authorizedTools)
    .call()
    .chatResponse();

Usage totalUsage = response.getMetadata().getUsage();

// Record one exchange-level summary, không cộng tiếp với
// các ModelUsageEvent nếu chúng đã đại diện cùng usage.
turnSummaries.recordExchangeUsage(turnId, totalUsage);
~~~

**Bên trong tool loop**: quan sát mỗi lần `ToolCallingAdvisor` gọi xuống model; có thể thêm advisor có order lớn hơn `ToolCallingAdvisor.DEFAULT_ORDER` (mặc định `Ordered.HIGHEST_PRECEDENCE + 300`).

~~~java
public class PerModelUsageAdvisor
        implements CallAdvisor, StreamAdvisor {

    private final ModelUsageRecorder recorder;

    public PerModelUsageAdvisor(ModelUsageRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public String getName() {
        return "per-model-usage";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        ChatClientResponse response = chain.nextCall(request);
        if (response.chatResponse() != null) {
            recorder.recordOnce(response.chatResponse());
        }
        return response;
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {

        return new ChatClientMessageAggregator()
            .aggregateChatClientResponse(
                chain.nextStream(request),
                complete -> {
                    if (complete.chatResponse() != null) {
                        recorder.recordOnce(complete.chatResponse());
                    }
                }
            );
    }
}
~~~

Ví dụ mô tả nguyên tắc tích hợp. `ModelUsageRecorder` là service tự triển khai, có trách nhiệm lấy `turnId` từ context đáng tin cậy, xác định model/provider, chuẩn hóa usage, và **deduplicate** theo request ID. `ChatClientMessageAggregator` tổng hợp chunks để thu phản hồi hoàn chỉnh nhưng vẫn trả `Flux<ChatClientResponse>` cho subscriber; không dùng `collectList().block()` để mất streaming.

Advisor ở **bên trong** loop có thể ghi nhiều event trong một `ChatClient` exchange; advisor **bên ngoài** loop chỉ quan sát kết quả cuối. Trong trường hợp model trả nhiều chunk metadata hoặc dùng streaming retry, `recordOnce` cần xử lý identity chính xác thay vì ghi vào ledger mỗi `doOnNext`.

**Lưu ý:** không nên xây dựng billing chính xác duy nhất dựa trên một callback ở advisor. Hãy đối soát với provider request IDs và hóa đơn provider. Với những model call thất bại/cancel trước khi usage được phát, số liệu có thể chưa đầy đủ.

## 12. Không cộng token cho từng streaming chunk

Với `ChatClient.stream()`, model có thể phát text theo từng chunk. Không được xem mỗi chunk là một model call hoặc cộng `Usage.getTotalTokens()` của từng chunk một cách mù quáng.

Có provider chỉ phát usage ở cuối; có provider không phát usage trong một số chế độ streaming; một số metadata có thể là giá trị lũy kế hoặc snapshot. Nếu cộng mọi snapshot, tổng sẽ bị phóng đại.

**Quy tắc an toàn:**

- Gom kết quả của một model iteration nếu cần usage hoàn chỉnh.
- Chỉ ghi usage đã được xác định là cuối cùng cho iteration.
- Không ước lượng token bằng số ký tự để thay thế usage do provider báo; ước lượng chỉ dùng cho admission control và phải gắn nhãn `ESTIMATED`.
- Khi stream bị hủy, bị timeout hoặc lỗi giữa chừng, đánh dấu usage là `PARTIAL` hoặc `UNKNOWN` theo dữ liệu thực nhận.
- Đối soát sau với provider billing/export nếu cần độ chính xác tài chính.

Thao tác `retry()` trên `Flux` có thể đăng ký lại publisher và dẫn đến một lần gọi model mới. Với tool có side effect, retry toàn chuỗi còn có thể thực thi tool lần nữa. Vì vậy, identity và ledger phải phân biệt **model call mới**, **replayed event**, **vendor request retry** và **cùng response bị quan sát hai lần**.

## 13. Tạo ngân sách theo từng lượt: ước lượng, dự phòng, đối soát

Một ngân sách hữu ích không nên chỉ là biến `spentUsd` tăng sau khi mọi việc kết thúc. Ứng dụng cần quyết định **trước mỗi lần gọi** liệu còn đủ ngân sách hay không.

Ví dụ cấu hình chính sách:

~~~text
PerTurnPolicy
  maxModelCalls: 5
  maxToolCalls: 8
  maxEstimatedModelUsd: 0.04
  maxEstimatedExternalUsd: 0.02
  maxElapsedSeconds: 30
  maxOutputTokensPerCall: 800
~~~

Các con số là ví dụ, không phải mặc định Spring AI. Chúng có thể khác theo tier người dùng, mục đích và mức rủi ro.

### Luồng thực thi

~~~mermaid
flowchart TD
    A[Nhận một turn đã xác thực] --> B[Định danh tenant và policy]
    B --> C[Ước lượng prompt + max output + tool cost]
    C --> D{Còn ngân sách để đặt trước?}
    D -- Không --> E[Từ chối hoặc chuyển workflow rẻ hơn]
    D -- Có --> F[Reserve budget]
    F --> G[Gọi model / thực thi tool]
    G --> H[Đọc usage, tool attempts, thời gian]
    H --> I[Commit chi phí đã biết; release chênh lệch]
    I --> J{Cần thêm lượt model/tool?}
    J -- Có --> C
    J -- Không --> K[Ghi summary và trả kết quả]
~~~

Một API ngân sách của ứng dụng có thể thiết kế như sau:

~~~java
public interface TurnBudgetService {

    Reservation reserve(
        String turnId,
        String operationId,
        BigDecimal estimatedWorstCaseUsd
    );

    void settle(
        Reservation reservation,
        BigDecimal observedOrEstimatedUsd,
        UsageQuality quality
    );

    void markUncertain(
        Reservation reservation,
        String reason
    );
}
~~~

`reserve(...)` phải dùng thao tác **atomic** trong database/Redis/transaction thích hợp, không chỉ:

~~~java
// Sai khi có nhiều request cùng dùng một ngân sách.
if (spent.add(estimated).compareTo(limit) <= 0) {
    // thread khác có thể cũng thấy đủ tiền rồi cùng chạy
}
~~~

Thay bằng `spent + reserved + newReservation <= limit` được kiểm tra và ghi atomically. Khi có kết quả, settle theo actual/estimated usage và giải phóng phần reserve dư. Nếu response bị timeout trước khi nhận usage, không tự release toàn bộ như thể provider không hề tính tiền; đánh dấu khoản chờ đối soát.

### Giới hạn “hard cap” không tuyệt đối

Vì usage thật thường chỉ có **sau** khi model call hoàn thành, ứng dụng không thể biết chính xác chi phí cuối cùng trước khi request được xử lý. `maxOutputTokens`, giới hạn số vòng model, max tool calls, deadline và reserve đủ biên giúp hạn chế vượt ngân sách, nhưng vẫn có rủi ro do provider behavior, cache billing, retry hoặc phí ngoài dự kiến.

Phân biệt:

- **Soft budget**: cho phép hoàn thành và cảnh báo khi gần/vượt ngưỡng.
- **Admission budget**: từ chối bắt đầu thao tác khi ước tính không còn đủ.
- **Operational hard stop**: không bắt đầu vòng mới và dừng các thao tác chưa chạy khi đạt giới hạn.
- **Financial invoice cap**: chỉ có thể cam kết nếu tích hợp giới hạn/hợp đồng chính thức của provider và xử lý tất cả chi phí in-flight.

Không tuyên bố ngân sách app là cap thanh toán tuyệt đối khi vẫn có request đang xử lý.

## 14. Đặt budget checkpoint trước model call và trước tool

Nếu yêu cầu cần hai tool, checkpoint có thể nằm ở nhiều vị trí:

1. Trước model call đầu tiên: kiểm tra token context ước lượng, max output, dự phòng model.
2. Sau response có tool calls: kiểm tra tool được phép, dự phòng phí external API và side effects.
3. Trước model call tiếp theo: tính lại prompt đã lớn thêm vì history và tool results.
4. Sau từng remote attempt: ghi số units/thành tiền thật nếu API trả thông tin.
5. Khi task kết thúc: tổng hợp và đối soát.

Spring AI 2.1.0 `ToolCallingAdvisor` có hook `doBeforeCall` và `doBeforeStream` trước mỗi model iteration. Có thể mở rộng advisor để dùng ngân sách trước mỗi vòng. `ToolCallingManager` cũng có giới hạn tổng tool calls và số lần một tool được gọi trong mỗi turn:

~~~properties
spring.ai.tools.limits.max-total-tool-calls=8
spring.ai.tools.limits.max-calls-per-tool-default=4
spring.ai.tools.limits.on-limit-exceeded=THROW
~~~

Các property trên hạn chế **số lượt gọi tool**, không giới hạn trực tiếp token hoặc USD. Theo chính sách sản phẩm, cần cấu hình thêm ngân sách model và ngân sách vendor API ở application layer.

Nếu dùng `returnDirect = true`, tool result có thể được trả thẳng ra caller và bỏ qua model call cuối. Điều này có thể giảm token model, nhưng không làm mất phí đã phát sinh khi tool thực thi.

### Không chặn dựa trên dữ liệu do model cung cấp

Nguồn `turnId`, tenant ID, vai trò, số dư và ngân sách phải do server xác định. `ToolContext` có thể truyền ngữ cảnh tin cậy đến callback mà không đưa nó vào tool arguments. Không nhận `budgetUsd` hoặc `authorizedTenant` từ prompt/model rồi dùng làm điều kiện cấp quyền.

## 15. Chi phí mô hình và dịch vụ có thể lệch nhau theo thời gian

Bảng giá và usage không luôn sẵn có cùng lúc:

- Usage token có thể xuất hiện ngay khi response hoàn tất.
- Giá của provider được quản lý theo bảng giá có hiệu lực.
- Phí REST/SDK có thể chỉ có trên hóa đơn cuối ngày hoặc cuối tháng.
- Infra cost thường là khoản phân bổ sau theo CPU/GB/hour hoặc cloud invoice.
- Refund, discount, rate-limit credit và hợp đồng doanh nghiệp có thể làm giá billed khác estimate.

Vì vậy nên dùng trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `PENDING` | Đã chạy nhưng chưa có đủ usage/cost |
| `ESTIMATED` | Tính từ usage và price table nội bộ |
| `OBSERVED` | Có quantity/cost do provider trả ở response |
| `RECONCILED` | Đã đối chiếu với hóa đơn/export chính thức |
| `DISPUTED` | Có chênh lệch, cần kiểm tra |

Không ghi số tiền ước tính vào trường “final billed amount” nếu chưa đối soát. Báo cáo có thể đồng thời hiển thị **ước tính theo lượt** và **thanh toán thực tế theo kỳ**.

### Tại sao độ trễ không quy đổi thành tiền đơn giản?

Một tool gọi database trong 200 ms có thể không có phí biên đo được theo từng request; một API trả lời trong 20 ms có thể tính $0,01. Ngược lại, query nặng có thể tốn nhiều CPU nhưng không thu phí theo request.

Theo dõi latency để tối ưu trải nghiệm và tài nguyên, nhưng không dùng công thức “mỗi giây = X USD” trừ khi hệ thống đã có mô hình phân bổ được kiểm chứng.

## 16. Ví dụ xây dựng bảng điều khiển

Một dashboard có thể chia thành ba khu vực.

### A. Token/model consumption

| Metric | Công dụng |
|---|---|
| Token input/output/total theo model | Phát hiện model tốn context |
| Tokens per turn (p50, p95) | Phát hiện các lượt đột biến |
| Model calls per turn | Phát hiện vòng tool calling kéo dài |
| Cached-read token ratio | Ước lượng hiệu quả prompt cache khi provider báo |
| Estimated model cost/turn | Kiểm soát budget trực tiếp |
| Unknown-usage rate | Phát hiện thiếu dữ liệu billing |

### B. Tool/external consumption

| Metric | Công dụng |
|---|---|
| Tool calls/turn và theo tool | Phát hiện tool bị gọi dư |
| Remote HTTP attempts/tool call | Phát hiện retry, fan-out |
| Vendor fees theo hệ thống | Phân biệt phí model và phí đối tác |
| Tool latency và error rate | Phát hiện hệ thống chậm/lỗi |
| Database/storage/egress allocation | Ước lượng chi phí nội bộ |

### C. Ngân sách và đối soát

| Metric | Công dụng |
|---|---|
| Remaining budget theo nhóm chính sách | Quyết định có cho chạy thêm |
| Reservation amount | Nhìn các lượt còn in-flight |
| Budget rejection count | Phát hiện chính sách quá thấp |
| Reconciliation difference | Phát hiện ước tính lệch hóa đơn |
| Unknown/partial usage | Xác định độ tin cậy của báo cáo |
| Unauthorized tool execution rate | Mục tiêu bằng 0 |

Các dashboard mức tổng hợp nên giữ cardinality thấp. Khi cần điều tra một lượt cụ thể, dùng `turnId` để truy vấn ledger có kiểm soát quyền, không gắn ID đó vào mọi Prometheus timeseries.

## 17. Kiểm thử tính đúng đắn của số liệu và ngân sách

Kiểm thử không nhất thiết cần gọi provider thật. Có thể tạo `ChatResponse` giả lập với usage cố định, fake tool adapter và bộ ghi ledger trong memory để xác minh logic.

| Test case | Điều cần xác minh |
|---|---|
| Một model call | Input/output/total được ghi đúng một lần |
| Một tool loop gồm ba model calls | Cumulative usage bằng tổng ba call; không nhân đôi |
| Tool gọi 3 HTTP attempts | Một toolCallId nhưng 3 attempt records |
| Provider không trả usage | Báo `UNKNOWN`, không xem là 0 |
| Cached tokens | Không cộng trùng phần cached nằm trong input |
| Hai model có giá khác nhau | Cùng token nhưng chi phí khác nhau |
| Giá đổi theo ngày | Sử dụng đúng `priceVersion` khi tính lại |
| Retry sau lỗi | Deduplicate replay; phân biệt request mới và cùng event |
| Stream kết thúc bình thường | Ghi usage khi đã có metadata cuối |
| Stream bị cancel | `PARTIAL`/`UNKNOWN` và reconciliation |
| Hai lượt song song cùng budget | Reservation atomic, không vượt phần ngân sách có thể cấp |
| Tool bị từ chối quyền | Không có remote API call và không ghi phí giả |
| Tool chứa LLM phụ | Model phụ được ghi usage riêng, không mất trong tổng |
| Budget cạn giữa vòng | Không bắt đầu model/tool call tiếp theo |
| Return-direct tool | Không giả tạo model call cuối |
| Mất sự kiện telemetry | Ledger/idempotency giúp đối soát hoặc đánh dấu chênh lệch |

Một assert đơn giản cho phép cộng:

~~~java
@Test
void cumulativeTokensMustNotBeCountedTwice() {
    long[] perModelCallTokens = {2_000, 2_900, 3_600};

    long sum = LongStream.of(perModelCallTokens).sum();

    assertThat(sum).isEqualTo(8_500);

    long chatClientCumulativeUsage = 8_500;

    // Ghi cumulative như summary, không cộng như event lần thứ tư.
    assertThat(chatClientCumulativeUsage).isEqualTo(sum);
}
~~~

Với budget đồng thời, cần integration test có hai transaction cố reserve trên cùng tenant: chỉ một hoặc phần phù hợp được cấp, không có race gây overspend. Với tool retry, dùng HTTP stub để điều khiển attempts và chỉ ghi vendor fee theo điều khoản tính phí thực tế.

## 18. Các hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách nhìn đúng |
|---|---|---|
| “Total tokens = tiền phải trả” | Giá khác nhau theo model/loại token | Dùng rate card + usage + provider billing |
| “Một ChatClient request chỉ gọi model một lần” | Tool loop có thể gọi model nhiều vòng | Xem cumulative usage và từng call |
| “Cộng cumulative với per-call để có tổng” | Đếm trùng cùng usage | Chọn một nguồn ledger chuẩn |
| “Mỗi tool call đều tiêu thụ token” | Tool backend có thể không dùng LLM | Tách tool execution cost và model cost |
| “Tool không có phí nếu response nhỏ” | API có thể tính theo request/attempt | Ghi fee ở gateway/SDK |
| “Cached tokens phải cộng thêm vào input” | Cached token thường đã nằm trong prompt usage | Dùng mapping của provider để tránh double count |
| “Không có usage nghĩa là 0 token” | Response có thể lỗi, stream hủy hoặc provider không báo | Ghi `UNKNOWN` và đối soát |
| “RateLimit là ngân sách USD” | Đây là hạn mức provider về request/tokens | Dùng ngân sách riêng của ứng dụng |
| “HTTP tool gọi một lần nên vendor chỉ tính một lần” | Adapter có thể retry/fan-out | Đếm remote attempts và hóa đơn |
| “Token metrics tự tính được cost” | Chúng không có giá/discount/fee external | Tích hợp price table và cost ledger |
| “Retry toàn bộ stream luôn an toàn” | Có thể tạo model/tool attempts mới | Kiểm soát idempotency, retry theo boundary |
| “Giới hạn maxOutputTokens bảo đảm hóa đơn không vượt ngân sách” | Còn prompt, retry, tool, cache và in-flight | Dùng reserve, checkpoints và đối soát |
| “Cứ log toàn bộ prompt để điều tra” | Có thể lộ PII, secret và nội dung tool | Ghi metadata tối thiểu, redaction và RBAC |

## 19. Checklist triển khai production

- [ ] Phân biệt **token usage**, **model billing**, **external/vendor cost** và **infra allocation**.
- [ ] Có định nghĩa rõ `turnId`, `modelCallId`, `toolCallId`, `attemptId` và `providerRequestId`.
- [ ] Đọc `Usage` từ `ChatResponseMetadata` ở đúng vị trí trong Spring AI 2.1.0.
- [ ] Hiểu response cuối của `ChatClient` có tool loop chứa cumulative usage.
- [ ] Không cộng lại cumulative usage với metric per-model-call.
- [ ] Phân biệt cache read/write, reasoning/modality và provider pricing.
- [ ] Có versioned rate card theo provider/model/currency và ngày hiệu lực.
- [ ] Có ledger cho phí API/SDK và remote HTTP attempts của tool.
- [ ] Có phương án đo và phân bổ chi phí nội bộ nếu sản phẩm cần báo cáo toàn bộ.
- [ ] Có trạng thái `ESTIMATED`, `UNKNOWN`, `RECONCILED`; không coi thiếu số liệu là 0.
- [ ] Có ngân sách theo user/tenant/turn và atomic reservation cho concurrency.
- [ ] Có checkpoint trước model iterations và tool có phí/side effect.
- [ ] Có giới hạn số model calls, số tool calls, timeout, output tokens và retry.
- [ ] Hạn mức provider `RateLimit` không bị nhầm với hạn mức tài chính của ứng dụng.
- [ ] Streaming được xử lý theo lifecycle, không cộng usage mỗi chunk một cách mù quáng.
- [ ] Micrometer metrics không chứa user IDs, prompt, credentials hay tool arguments.
- [ ] Có đối soát với provider invoice/export khi cần độ chính xác thanh toán.
- [ ] Có test cho multi-call loop, cache, lỗi, hủy stream, retry và budget concurrency.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): `ChatResponseMetadata`, `Usage`, `RateLimit`, cached input metrics và cumulative usage qua nhiều model calls.
- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): `spring.ai.chat.client`, `gen_ai.client.operation`, `gen_ai.client.token.usage`, `spring.ai.tool` và các nhãn observation.
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `ToolCallingAdvisor`, `ToolCallingManager`, vòng tool call, `ToolContext`, giới hạn tool calls và bảo mật.
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): quan sát từng iteration và hook để kiểm soát ngân sách.
- [Spring AI 2.1.0 — Structured Output](https://docs.spring.io/spring-ai/reference/api/structured-output.html): `responseEntity(...)` để lấy dữ liệu có cấu trúc cùng response metadata.
- [Micrometer — Documentation](https://docs.micrometer.io/): meter registry, counters, timers, tracing và thực hành giới hạn cardinality.

**Điểm cần nhớ:** một token không phải một đơn vị tiền; chi phí model không bao gồm chi phí API/SDK do tool gọi; và usage của response cuối sau tool calling có thể đã là tổng nhiều model calls. Hãy ghi đúng từng lớp, tránh cộng trùng, có rate card và ledger rõ nguồn, rồi kiểm soát ngân sách trước khi bắt đầu vòng xử lý mới. Khi dữ liệu còn thiếu hoặc mới ước tính, hãy thể hiện đúng mức độ chắc chắn thay vì báo một con số thanh toán giả chính xác.

