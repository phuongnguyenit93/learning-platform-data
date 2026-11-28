# Kiểm thử lại hợp đồng trước khi đổi mô hình hoặc nhà cung cấp

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xác định **hợp đồng tool calling** mà ứng dụng Spring AI phải giữ ổn định khi thay model, phiên bản model hoặc nhà cung cấp.
- Tách kiểm thử callback/schema và nghiệp vụ có thể chạy ngoại tuyến khỏi kiểm thử hành vi thực tế của model cần gọi API.
- Thiết kế bộ ca kiểm thử cho chọn công cụ, đối số JSON, vòng gọi nhiều lượt, lỗi, giới hạn, xác thực quyền và thao tác có tác dụng phụ.
- Đặt tiêu chí so sánh baseline–candidate, lưu bằng chứng và quyết định có đủ điều kiện chuyển model/provider hay không.

**Bối cảnh phiên bản:** Bài sử dụng Spring AI **2.1.0** (phát hành GA ngày 20/11/2026) và API tool calling tương ứng. Việc gọi model ở môi trường thật còn phụ thuộc phiên bản model, endpoint và chính sách của từng provider. Không coi việc hai provider cùng triển khai `ChatModel` là bằng chứng chúng có hành vi tool calling giống nhau.

## 1. Vì sao đổi model lại phải kiểm thử hợp đồng?

Giả sử trợ lý chăm sóc khách hàng có hai công cụ:

- `order_status`: tra cứu trạng thái đơn hàng trong tenant hiện tại.
- `cancel_order`: hủy đơn hàng, yêu cầu xác thực và xác nhận trước khi thực thi.

Bản đang chạy dùng model A. Khi đổi sang model B, code Java vẫn biên dịch, tên `@Tool` vẫn giữ nguyên và API `ChatClient` không đổi. Tuy nhiên, model B có thể chọn sai công cụ, bỏ sót đối số, tự tạo `orderId` khi người dùng chưa cung cấp, yêu cầu nhiều tool call trong một phản hồi hoặc trả câu trả lời sau khi nhận lỗi theo cách khác. Provider cũng có thể khác nhau ở cách biểu diễn tool call, streaming, giới hạn số tool, schema được hỗ trợ và cấu hình lựa chọn tool.

Vì vậy, **hợp đồng cần giữ là hành vi quan sát được của toàn hệ thống**, gồm cả quyết định của model **và** ràng buộc bắt buộc do ứng dụng thực thi. Kiểm thử «gọi được API và nhận về câu trả lời» chưa đủ để kết luận có thể thay thế model.

Một cách phân tách hữu ích:

| Lớp hợp đồng | Điều cần giữ ổn định | Chủ thể chịu trách nhiệm |
|---|---|---|
| Khai báo công cụ | Tên duy nhất, mô tả, JSON Schema đầu vào, kiểu kết quả, công cụ nào được cấp | Ứng dụng / Spring AI |
| Quyết định của model | Có gọi tool khi cần, chọn đúng tool, tạo đối số phù hợp, không gọi khi thiếu thông tin | Model, prompt và cấu hình provider |
| Thực thi nghiệp vụ | Xác thực tenant, kiểm tra quyền theo tài nguyên, validation, idempotency, timeout, xử lý lỗi | Ứng dụng / dịch vụ nghiệp vụ |
| Vòng điều phối | Ghép phản hồi tool vào hội thoại, gọi tiếp khi cần, dừng khi hoàn tất hoặc vượt hạn mức | `ToolCallingAdvisor` / `ToolCallingManager` hoặc bộ điều phối riêng |
| Đầu ra & vận hành | Trả kết quả có căn cứ, không lộ dữ liệu, đo được độ trễ/chi phí/lỗi và phục hồi an toàn | Toàn hệ thống |

Một test thất bại phải chỉ ra **lớp nào vi phạm**. Ví dụ, nếu model sinh `{"orderId":""}` thì đó có thể là lỗi chọn đối số; nếu callback cho phép đọc đơn của tenant khác thì đó là lỗi phân quyền dù model đã chọn đúng tool.

## 2. Những điểm phải xác minh theo Spring AI 2.1

### 2.1. Phân biệt `ChatClient` và `ChatModel`

Với `ChatClient` trong Spring AI 2.1, `ToolCallingAdvisor` được tự đăng ký theo cấu hình mặc định. Advisor gửi định nghĩa tool tới model, nhận yêu cầu gọi tool, dùng `ToolCallingManager` thực thi callback, đưa kết quả vào lịch sử trao đổi và lặp đến khi model không yêu cầu gọi tool tiếp. Cả đường `call()` và `stream()` được hỗ trợ.

Ngược lại, gọi trực tiếp `ChatModel.call(prompt)` hoặc `ChatModel.stream(prompt)` **chỉ** gửi định nghĩa tool và nhận phản hồi thô; `ChatModel` không tự thực thi tool call. Nếu hệ thống đang tự viết loop hoặc chuyển từ cách làm của Spring AI 1.x, phải kiểm thử lại việc thu thập tool call, ghép `ToolResponseMessage`, kiểm soát vòng lặp và điều kiện dừng. Trong Spring AI 1.x, vòng tool execution từng nằm ở các `ChatModel`; từ 2.0 trở đi, vòng này thuộc lớp advisor của `ChatClient`.

Có thể tắt tự đăng ký `ToolCallingAdvisor` bằng cấu hình `spring.ai.chat.client.tool-calling.enabled=false` hoặc theo từng request bằng `AdvisorParams.toolCallingAdvisorAutoRegister(false)`. Khi tắt, trách nhiệm điều phối thuộc về code ứng dụng. Một bài kiểm thử dùng `ChatModel` không thể mặc nhiên đại diện cho hành vi của `ChatClient`.

### 2.2. Danh sách tool và schema gửi tới provider

Spring AI 2.1 hỗ trợ `@Tool`, `MethodToolCallback` và `FunctionToolCallback`; cả ba cung cấp `ToolCallback` với `ToolDefinition` gồm `name()`, `description()` và `inputSchema()`. Tên tool phải duy nhất trong tập được cấp. Mô tả giúp model chọn đúng tool; JSON Schema quy định tên, kiểu và tính bắt buộc của đối số.

- Với `@Tool`, các tham số mặc định là bắt buộc; có thể dùng `@ToolParam(required = false)` hoặc `@Nullable` cho tham số tùy chọn.
- `ChatClient.defaultTools(…)` và `ChatClient.prompt().tools(…)` được **gộp**; thêm `.tools(…)` theo request không tự xóa các tool mặc định.
- Với `ChatModel` và `ToolCallingChatOptions`, danh sách tool trong options của request **thay thế** danh sách tool mặc định của model khi cả hai cùng được đặt.
- `ToolContext` chuyển dữ liệu do ứng dụng cấp (ví dụ tenant hoặc danh tính người gọi) tới callback mà không gửi giá trị đó cho model. Context không thay thế kiểm tra quyền tại service.

Hai code path có quy tắc kết hợp tool khác nhau; test migration phải xác minh **danh sách thực tế được gửi**. Nếu đồng thời dùng tool nội bộ và MCP, cũng phải kiểm tra va chạm tên. `ChatClient` kiểm tra trùng tên trên tập kết hợp; đường `ChatModel` trực tiếp hoặc loop tự viết cần tự kiểm tra danh sách này.

### 2.3. Chức năng 2.1 ảnh hưởng đến kỳ vọng kiểm thử

Spring AI 2.1 bổ sung/củng cố các khả năng cần đưa vào ma trận hồi quy:

- **Xác nhận công cụ**: `@Tool(requiresConfirmation = true)` có thể khiến vòng gọi tạm dừng để ứng dụng xin quyết định của người dùng. Nếu một phản hồi yêu cầu cả tool đọc và tool cần xác nhận, manager tạm dừng **toàn bộ nhóm call trong phản hồi đó** trước khi thực thi. Test không được giả định một phần của nhóm đã chạy.
- **Giới hạn lời gọi**: `ToolCallingManager` có giới hạn số lần mỗi tool và tổng số tool call trong một turn (mặc định lần lượt là `40` và `150` trong tài liệu 2.1). Cần test chính sách khi vượt giới hạn: dừng hoặc trả lỗi cho model, và không lặp vô hạn.
- **Streaming tool arguments**: với các provider/endpoint có hỗ trợ, stream có thể đưa ra những mảnh `ToolCallPart` đánh dấu *partial*. Mảnh này thường chưa phải JSON hoàn chỉnh và **không được thực thi** như tool call; manager chỉ xử lý tool call hoàn chỉnh.
- **Lịch sử hội thoại**: Spring AI 2.1 có mô hình `MessagePart` theo thứ tự, bao gồm text, reasoning, tool call và tool result. Khi chuyển provider, cần test round-trip lịch sử, nhất là khi provider có dữ liệu riêng. `ChatMemory` truyền thống đã bị deprecated trong 2.1 để nhường chỗ cho Session API; nếu ứng dụng lưu lịch sử tool trong memory, cần kiểm tra cách advisor đặt trong/ngoài loop.

Các tính năng này không có nghĩa mọi model hoặc endpoint hỗ trợ giống nhau. Xem ma trận tính năng của model, tài liệu provider và kết quả test thật cho **đúng mã model** sẽ triển khai.

## 3. Ví dụ hợp đồng nghiệp vụ: tra cứu đơn theo tenant

Đây là ví dụ rút gọn của một tool đọc; `OrderService` là giao diện nghiệp vụ do ứng dụng định nghĩa. Các import được lược bỏ để tập trung vào hợp đồng:

```java
record OrderSnapshot(String orderId, String state) {}

interface OrderService {
    OrderSnapshot findForTenant(String tenantId, String orderId);
}

final class OrderTools {
    private final OrderService orders;

    OrderTools(OrderService orders) {
        this.orders = orders;
    }

    @Tool(
        name = "order_status",
        description = "Đọc trạng thái một đơn hàng đã biết mã; không tạo, sửa hoặc hủy đơn"
    )
    public OrderSnapshot status(
            @ToolParam(description = "Mã đơn hàng do người dùng cung cấp") String orderId,
            ToolContext toolContext) {

        String tenantId = (String) toolContext.getContext().get("tenantId");
        if (tenantId == null || tenantId.isBlank()) {
            throw new SecurityException("Thiếu tenant đã xác thực");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Thiếu mã đơn hàng");
        }

        // Service phải xác thực quyền truy cập trên chính đơn hàng này.
        return orders.findForTenant(tenantId, orderId);
    }
}

// Trong request đã xác thực của ứng dụng:
ChatClient client = ChatClient.builder(chatModel).build();

String answer = client.prompt()
    .user("Cho tôi biết trạng thái đơn ORD-17.")
    .tools(new OrderTools(orderService))
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
```

Hợp đồng này có bốn bất biến:

1. Chỉ expose `order_status` với input `orderId` kiểu chuỗi, bắt buộc; không để model tự quyết định `tenantId`.
2. `tenantId` phải đến từ request đã xác thực thông qua `ToolContext`; callback từ chối context thiếu và service kiểm tra quyền trên tài nguyên thật.
3. Mã đơn thiếu hoặc không hợp lệ không được suy đoán để gọi hệ thống; trợ lý phải xin mã hoặc báo không đủ thông tin.
4. Phản hồi cuối phải dựa trên `OrderSnapshot` thật; nếu không đọc được đơn, không tự bịa trạng thái.

**Quyết định quan trọng:** Ở ví dụ này, model lựa chọn gọi tool và chuẩn bị `orderId`; ứng dụng mới là bên thực thi `orders.findForTenant`. Khi thay model, bất biến 2 không được phụ thuộc vào khả năng tuân thủ prompt của model.

## 4. Đóng băng baseline trước khi thử provider mới

Tạo một **contract fixture** có thể chạy lại với cùng dữ liệu nghiệp vụ. Mỗi ca test nên lưu:

| Thành phần | Giá trị cần chốt |
|---|---|
| Model/provider | Provider, model ID chính xác, endpoint/API mode, phiên bản SDK/starter, ngày chạy |
| Cấu hình sinh | Temperature/top-p nếu được hỗ trợ, giới hạn token, tool-choice/parallel tool-call options theo provider |
| Lời nhắc | System/developer instruction, câu người dùng, ngôn ngữ và lịch sử hội thoại cần thiết |
| Tập công cụ | Tên, mô tả, JSON Schema, `returnDirect`, `requiresConfirmation`, allowlist theo vai trò |
| Ngữ cảnh ứng dụng | Tenant/role test, quyền trên tài nguyên, clock cố định, dữ liệu stub và lỗi giả lập |
| Kỳ vọng | Tool được/không được gọi, đối số hợp lệ, số lần thực thi, phản hồi, giới hạn, side effect |
| Bằng chứng | Kết quả pass/fail theo case, trace an toàn, thời gian, token/chi phí nếu provider cung cấp |

Lấy kết quả từ model đang chạy làm **baseline tham khảo**, nhưng viết expected behavior từ **yêu cầu nghiệp vụ**, không sao chép nguyên câu trả lời của baseline thành chuẩn. Baseline cũng có thể sai. Không so khớp từng chữ của phần diễn đạt tự nhiên; thay vào đó so khớp dữ kiện, hành động và các thuộc tính có thể xác minh.

Nếu dùng model ngẫu nhiên, chạy lặp nhiều lần trên tập đánh giá cố định, giữ cùng cấu hình và báo cả số lần chạy lẫn tỷ lệ đạt. Các yêu cầu an toàn/ủy quyền phải đạt **100%**; với chất lượng chọn tool có thể định ngưỡng riêng cho ứng dụng, ví dụ ≥ 95% trên tập test đại diện. Đây là ngưỡng minh họa do dự án tự chọn, không phải cam kết của Spring AI hay provider.

## 5. Thiết kế bộ kiểm thử ba lớp

### Lớp A — Contract và callback, không gọi model

Kiểm thử thuần Java/JUnit với service giả lập để phát hiện sai lệch định nghĩa tool hoặc lỗi nghiệp vụ trước khi tốn chi phí gọi model:

- Lấy `ToolCallbacks.from(new OrderTools(...))`, kiểm tra `ToolDefinition.name()`, mô tả và `inputSchema()`. Parse JSON Schema; xác minh `orderId` nằm trong `required` và có kiểu `string`.
- Gọi trực tiếp `ToolCallback.call(jsonArguments, toolContext)` với input hợp lệ; kiểm tra callback gọi đúng service với đúng tenant, trả kết quả được serialize và không ghi dữ liệu.
- Gọi với `tenantId` thiếu, mã đơn trống, mã đơn ngoài quyền, dữ liệu không tồn tại, timeout; kiểm tra service từ chối và lỗi được ánh xạ theo chính sách.
- Với tool thay đổi trạng thái, kiểm tra phân quyền, idempotency key, audit và `requiresConfirmation` theo policy; không dựa vào prompt để bảo vệ thao tác nguy hiểm.
- Kiểm tra tập tool cuối cùng không có tên trùng, không vô tình expose tool quản trị, và không chứa tool ngoài allowlist của vai trò.

Ví dụ kiểm thử hợp đồng schema và chuyển ngữ cảnh. Những class `OrderTools`, `OrderService`, `OrderSnapshot` lấy từ ví dụ trên; phần import AssertJ, JUnit, Jackson và Mockito được lược bỏ:

```java
@Test
void orderStatusContractAndTenantArePreserved() throws Exception {
    OrderService orders = mock(OrderService.class);
    when(orders.findForTenant("tenant-A", "ORD-17"))
        .thenReturn(new OrderSnapshot("ORD-17", "DELIVERED"));

    ToolCallback tool = ToolCallbacks.from(new OrderTools(orders))[0];
    assertThat(tool.getToolDefinition().name()).isEqualTo("order_status");

    JsonNode schema = new ObjectMapper().readTree(
        tool.getToolDefinition().inputSchema());
    assertThat(schema.path("properties").path("orderId").path("type").asText())
        .isEqualTo("string");
    assertThat(schema.path("required").toString()).contains("orderId");

    String result = tool.call(
        "{\"orderId\":\"ORD-17\"}",
        new ToolContext(Map.of("tenantId", "tenant-A"))
    );

    verify(orders).findForTenant("tenant-A", "ORD-17");
    assertThat(result).contains("DELIVERED");
}

@Test
void tenantMustComeFromTrustedContext() {
    OrderService orders = mock(OrderService.class);
    ToolCallback tool = ToolCallbacks.from(new OrderTools(orders))[0];

    assertThatThrownBy(() -> tool.call(
        "{\"orderId\":\"ORD-17\"}",
        new ToolContext(Map.of())
    )).isInstanceOf(RuntimeException.class);

    verifyNoInteractions(orders);
}
```

Lưu ý: `ToolCallback` có thể bọc lỗi phương thức thành ngoại lệ của lớp tool, vì vậy assertion về **loại ngoại lệ cụ thể** phải căn cứ cơ chế xử lý ngoại lệ đang cấu hình; ví dụ ở trên chỉ kiểm tra lời gọi bị chặn trước khi chạm service. Đối với test tích hợp, cần cấu hình `ToolExecutionExceptionProcessor` và khẳng định thông điệp lỗi có thể gửi về model không chứa dữ liệu nhạy cảm.

### Lớp B — Kiểm thử tích hợp với **model/provider thật**

Chạy cùng bộ tình huống trên baseline và candidate qua `ChatClient`. Dùng fake service có bộ đếm/lịch sử lời gọi để kiểm tra **hành động thực tế**; phân tích final answer theo tiêu chí dữ kiện, tránh phụ thuộc văn phong. Trường hợp cần quan sát nguyên bản yêu cầu tool, có thể kiểm thử riêng bằng `ChatModel` cùng `ToolCallingChatOptions`, nhưng nhớ đường này không tự chạy callback.

Ví dụ một ca tích hợp (lược bỏ khởi tạo provider và import):

```java
@Test
void candidateCanReadAnExistingOrder() {
    OrderService orders = mock(OrderService.class);
    when(orders.findForTenant("tenant-A", "ORD-17"))
        .thenReturn(new OrderSnapshot("ORD-17", "DELIVERED"));

    String answer = ChatClient.builder(candidateChatModel).build()
        .prompt()
        .user("Tra cứu đơn ORD-17 và cho biết tình trạng thực tế.")
        .tools(new OrderTools(orders))
        .toolContext(Map.of("tenantId", "tenant-A"))
        .call()
        .content();

    verify(orders, times(1)).findForTenant("tenant-A", "ORD-17");
    assertThat(answer).isNotBlank();
    // Đánh giá trạng thái DELIVERED qua chuẩn hóa dữ kiện/structured evaluator.
}
```

Ca trên có thể thất bại vì model không chọn tool, sinh sai tham số hoặc không hoàn tất loop; ba lỗi này cần ghi riêng trong kết quả. Không đặt `verify(times(1))` vào một bài kiểm thử yêu cầu retry hợp lệ: khi đó expected call count phải được định nghĩa riêng kèm tính idempotent.

### Lớp C — Kiểm thử chuỗi, lỗi và khả năng phục hồi

Tạo hội thoại nhiều lượt có stub dịch vụ và sai hỏng có chủ đích:

- **Nhiều lượt:** người dùng hỏi trạng thái nhưng chưa có mã đơn; trợ lý xin mã, sau đó chỉ gọi tool với mã vừa được cung cấp.
- **Nhiều tool call:** câu hỏi về hai đơn. Kiểm tra từng mã được ánh xạ đúng, không lẫn kết quả hoặc tenant; không mặc định provider nào cũng tạo nhiều call đồng thời.
- **Tool lỗi:** service trả 404/403/429/5xx/timeout; xác minh phản hồi cuối đúng loại lỗi, không dựng dữ kiện và không tiết lộ stack trace/token.
- **Retry:** nếu cần retry ở HTTP/client hoặc tool layer, kiểm tra số lần gọi thực, backoff và idempotency; tuyệt đối không lặp hành động ghi dữ liệu chỉ vì model gọi lại.
- **Dừng vòng:** mô phỏng model liên tục gọi cùng tool; kiểm tra giới hạn `max-calls-per-tool`/`max-total-tool-calls` và chính sách xử lý khi vượt hạn mức.
- **Streaming:** so với blocking về hiệu ứng nghiệp vụ; fragment `ToolCallPart` chưa hoàn chỉnh không bao giờ được chạy trước khi có tool call hoàn chỉnh.
- **Xác nhận:** một response vừa yêu cầu đọc vừa yêu cầu hủy; xác minh chưa tool nào chạy khi cần duyệt, sau đó chỉ tool được cho phép mới thực thi.
- **Chuyển lịch sử:** thử cùng lịch sử sau một vòng tool, cả khi thay model trong một phiên; kiểm tra thông tin provider-specific được xử lý hợp lệ và không làm mất các cặp tool call/tool result.

## 6. Ma trận hồi quy tối thiểu trước khi chuyển provider

| Mã ca | Tình huống | Kỳ vọng bắt buộc |
|---|---|---|
| TC-01 | Có mã đơn hợp lệ, được quyền | Chọn `order_status`, đúng `orderId`, đúng tenant, trả dữ kiện thật |
| TC-02 | Người dùng chưa cho mã đơn | Xin mã; không tự tạo mã để gọi service |
| TC-03 | Yêu cầu ngoài phạm vi tool | Không bịa tool hay gọi công cụ không được cấp |
| TC-04 | Cố yêu cầu tenant khác bằng lời nhắc | Tenant lấy từ `ToolContext`; service từ chối truy cập chéo |
| TC-05 | Mã đơn không tồn tại | Nói không tìm thấy; không tự khẳng định trạng thái |
| TC-06 | Mã JSON sai/thiếu/khác kiểu | Validation từ chối; hệ thống phục hồi có giới hạn |
| TC-07 | Hai đơn trong một câu | Không nhầm đối số/kết quả; số call phù hợp chính sách |
| TC-08 | Kết quả tool mâu thuẫn suy đoán ban đầu | Dựa vào kết quả nguồn nghiệp vụ |
| TC-09 | Tool trả 429/timeout | Lỗi được xử lý, retry có giới hạn, không lộ chi tiết nội bộ |
| TC-10 | Model yêu cầu hủy đơn | Kiểm tra quyền và xác nhận; không tự hủy khi chưa được phép |
| TC-11 | Model lặp gọi tool quá hạn mức | Dừng/hoàn trả lỗi theo cấu hình; không tạo vòng vô hạn |
| TC-12 | Blocking so với streaming | Cùng bất biến nghiệp vụ; không thực thi fragment chưa hoàn chỉnh |
| TC-13 | Trùng tên tool nội bộ/MCP | Từ chối hoặc đổi tên rõ ràng trước khi dispatch |
| TC-14 | Chuyển provider giữa hội thoại có tool | Không mất cặp request/result, không gán sai lời gọi |
| TC-15 | `returnDirect=true`, một hay nhiều tool | Kết quả đi đúng đường; chỉ return direct nếu mọi tool trong lượt đáp ứng điều kiện |
| TC-16 | Vai trò không được cấp tool nhạy cảm | Tool không nằm trong tập expose; callback vẫn kiểm quyền nếu bị gọi ngoài luồng |

Chia test theo mức độ: `TC-01`–`TC-06`, `TC-10` và `TC-16` thường là **điều kiện chặn release**; những ca còn lại đánh giá theo chức năng thực tế của ứng dụng. Nếu hệ thống không có tool ghi dữ liệu hay MCP, có thể đánh dấu `N/A` với giải thích, không ghi `PASS` giả.

## 7. So sánh hai model một cách có thể giải thích

Thực hiện mỗi ca trên cùng fixture, với cùng dữ liệu giả, cùng quyền và cùng kỳ vọng. Ghi ít nhất các trường sau cho từng lần chạy:

```json
{
  "caseId": "TC-01",
  "variant": "candidate",
  "provider": "provider-B",
  "modelId": "model-version-pinned",
  "iteration": 3,
  "selectedTools": ["order_status"],
  "normalizedArguments": {"orderId": "ORD-17"},
  "executedCalls": 1,
  "authorizationPassed": true,
  "businessOutcome": "DELIVERED",
  "finalAnswerGrounded": true,
  "latencyMs": 850,
  "status": "PASS"
}
```

Các giá trị JSON chỉ là **ví dụ dữ liệu đo**, không phải kết quả đo thật. Tập trung vào:

1. **Đúng chức năng:** tỷ lệ chọn đúng tool; tỷ lệ input schema hợp lệ; tỷ lệ đáp án có căn cứ; tỷ lệ hoàn tất workflow nhiều bước.
2. **Đúng quyền và an toàn:** số lần gọi sai tenant, gọi tool ngoài allowlist, vượt bước xác nhận, ghi dữ liệu trùng hoặc lộ bí mật. Với các bất biến này, chỉ chấp nhận **0 vi phạm**.
3. **Độ ổn định:** phân phối số tool call, tỷ lệ lỗi/timeout, stop reason, tỷ lệ retry và kết quả ở các lần chạy lặp.
4. **Hiệu năng/chi phí:** p50/p95 latency, token vào/ra nếu có, số round-trip, chi phí theo bảng giá hiện hành và ngân sách của hệ thống.

Không so chi phí chỉ dựa trên giá/token: một model giá/token thấp có thể tạo thêm nhiều lượt tool và tăng tổng thời gian/chi phí. Cũng không khẳng định tính năng `tool_choice`, chế độ JSON nghiêm ngặt, parallel tool calls hay stream delta có nghĩa giống nhau giữa tất cả provider; kiểm tra tài liệu và đường truyền thực tế.

### Phân loại lỗi để biết cần sửa gì

| Hiện tượng | Nơi điều tra trước |
|---|---|
| Tool không được gọi dù cần | Capability của model, tên/mô tả, prompt, lựa chọn tool phía provider |
| Tool đúng nhưng sai JSON | `inputSchema()`, cách provider diễn giải schema, tham số required, output tool call thô |
| Tool gọi đúng nhưng đọc sai tenant | `ToolContext` và kiểm quyền tại service; đây là lỗi ứng dụng |
| Lặp lại sau lỗi 429 | Chính sách retry, lỗi trả về model, giới hạn loop |
| Tool đã chạy nhưng final answer sai | Nội dung `ToolResponseMessage`, lịch sử loop, grounding/evaluator |
| Chỉ hỏng khi streaming | Kết hợp fragments, aggregation, sự khác biệt endpoint streaming |
| Chỉ hỏng khi đổi phiên bản Spring AI | Migration loop `ChatModel`/`ChatClient`, advisor/memory và cấu hình callback |

## 8. Quy trình đổi model/provider có cổng kiểm soát

1. **Chốt contract:** danh sách tool, schema, quy tắc quyền, error mapping, xác nhận, chính sách retry/limit và các case chặn release. Version hóa bộ fixture cùng ứng dụng.
2. **Kiểm tra năng lực ứng viên:** xác nhận model ID/endpoint thật hỗ trợ tool calling, kiểu input JSON mong đợi, streaming, tính năng cần dùng; lập danh sách khác biệt provider-specific.
3. **Chạy kiểm thử ngoại tuyến:** schema/callback, allowlist, auth, idempotency, lỗi và giới hạn với fake service. Bất kỳ lỗi quyền nào cũng phải sửa trước khi gọi model thật.
4. **Chạy suite tích hợp A/B:** baseline và candidate dùng cùng bộ dữ liệu. Phân tách ca blocking/streaming và luồng `ChatClient`/`ChatModel` khi ứng dụng dùng cả hai.
5. **Phân tích sai lệch:** phân loại theo tool selection, arguments, execution, loop, final answer; sửa mô tả/schema/prompt hoặc thích ứng provider theo bằng chứng. Không vá lỗi quyền chỉ bằng cách viết prompt chặt hơn.
6. **Kiểm thử giới hạn và rollout:** xác định ngân sách tool call, timeout, canary theo tỷ lệ traffic, quan sát số tool call và lỗi nghiệp vụ, chuẩn bị rollback model/config. Nếu mất hợp đồng chặn release, không chuyển toàn bộ traffic.

**Định nghĩa hoàn tất:** chỉ chuyển khi các bất biến bảo mật và side effect đạt 100%, các ca chức năng đạt ngưỡng đã thống nhất, hiệu năng/chi phí nằm trong ngân sách và có khả năng rollback. Nếu một provider thiếu khả năng thiết yếu, kết quả phải là `BLOCKED/UNSUPPORTED` kèm nguyên nhân, không cố ép mọi model vào cùng một kỳ vọng.

## 9. Các nhầm lẫn cần tránh

- **“Đổi `ChatModel` thì tự động thay được tool.”** API chung chỉ thống nhất cách gọi ở phía Java; chính sách chọn tool và biểu diễn tool call của model vẫn khác nhau.
- **“Schema hợp lệ nghĩa là model luôn sinh đúng JSON.”** Schema định nghĩa giao diện đầu vào; ứng dụng vẫn cần kiểm tra, xử lý thiếu/sai kiểu và từ chối yêu cầu không hợp lệ.
- **“Tool đã được mô tả là chỉ đọc nên an toàn.”** Quyền, tenant và side effect phải được enforce trong callback/service; model không phải ranh giới tin cậy.
- **“Chạy JUnit với mock model là đủ.”** Mock chứng minh contract nội bộ; chỉ thử endpoint/provider thật mới đo được khả năng chọn tool và hoàn thành workflow của model ứng viên.
- **“Thành công một lần là tương đương.”** Cần ca phủ lỗi và thử lặp cho hành vi xác suất, dùng tiêu chí chấp nhận công khai.
- **“Stream hiện JSON fragment là có thể thực thi.”** Chỉ tool call đã hoàn chỉnh mới được dispatch.

## 10. Tự kiểm tra kiến thức

1. Vì sao `ToolCallbacks.from(…)` với schema đúng vẫn chưa chứng minh model mới phù hợp để triển khai?
2. Hãy chỉ ra khác biệt giữa `ChatClient.prompt().tools(…)` và `ToolCallingChatOptions` trên `ChatModel` khi có default tools.
3. Trong test đổi provider, nếu model chọn đúng `order_status` nhưng trả dữ liệu của tenant khác, lỗi thuộc lớp nào và cần sửa ở đâu?
4. Tại sao ca “hủy đơn + tra cứu đơn” phải xác minh trạng thái tạm dừng của **toàn nhóm tool call** khi có yêu cầu xác nhận?
5. Bạn sẽ dùng những bằng chứng nào để quyết định rollback sau rollout canary?

## Tài liệu tham khảo

- [Spring AI 2.1.0 GA — thông báo phát hành](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/).
- [Spring AI 2.1 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `@Tool`, `ToolCallback`, JSON Schema, `ToolContext`, vòng gọi, giới hạn và streaming.
- [Spring AI 2.1 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html): tool options, override, điều phối thủ công.
- [Spring AI 2.1 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html): yêu cầu xác nhận và cơ chế resume.
- [Spring AI 2.1 — Chat Models Comparison](https://docs.spring.io/spring-ai/reference/api/chat/comparison.html): kiểm tra khả năng theo model/provider.
- [Spring AI 2.1 — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html): API chung, `MessagePart` và metadata phản hồi.
