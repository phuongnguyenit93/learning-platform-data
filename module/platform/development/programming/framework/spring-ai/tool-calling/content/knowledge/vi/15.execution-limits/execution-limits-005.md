# Phát hiện vòng lặp lặp lại cùng công cụ hoặc cùng đối số

Trong một vòng tool calling, mô hình có thể yêu cầu ứng dụng gọi công cụ, nhận kết quả rồi tiếp tục yêu cầu gọi công cụ khác. Chu trình này hữu ích khi cần tra cứu nhiều bước hoặc xử lý một quy trình nghiệp vụ. Tuy nhiên, mô hình cũng có thể lặp lại cùng một lời gọi nhiều lần: cùng tên công cụ, cùng đối số, cùng kết quả nhưng vẫn tiếp tục yêu cầu thực thi. Nếu không phát hiện, ứng dụng sẽ tiêu tốn token, thời gian và tài nguyên downstream; với công cụ ghi dữ liệu, việc lặp còn có thể tạo side effect trùng.

Spring AI có giới hạn số lần gọi công cụ trong một lượt, nhưng giới hạn theo số lượng không nhận diện được hai lần gọi có cùng ý nghĩa. Để phát hiện chính xác hơn, ứng dụng cần theo dõi dấu vân tay của lời gọi: tên công cụ kết hợp với đối số đã chuẩn hóa. Guard phải được đặt trước ranh giới thực thi, có phạm vi theo từng lượt người dùng và cho phép các trường hợp lặp hợp lệ như phân trang hoặc polling có giới hạn.

## Vòng lặp lặp lại trông như thế nào?

Một vòng lặp lặp lại thường có các dấu hiệu sau:

- Mô hình gọi `lookupOrder` với cùng `orderId` nhiều lần dù tool result trước đó đã trả đủ trạng thái.
- Mô hình gọi `searchProducts` liên tục với cùng query, cùng filter và cùng page cursor.
- Mô hình gọi một công cụ, nhận lỗi, rồi yêu cầu lại cùng công cụ với cùng đối số mà không sửa điều kiện gây lỗi.
- Mô hình luân phiên giữa hai công cụ theo cùng một chuỗi mà không tạo ra dữ liệu hoặc trạng thái mới.
- Mô hình tạo tool call ID mới ở mỗi vòng nhưng tên công cụ và JSON arguments không đổi.

Ví dụ:

```text
Vòng 1: lookupOrder({"orderId":"ORD-2048"})
        -> trạng thái: PROCESSING
Vòng 2: lookupOrder({"orderId":"ORD-2048"})
        -> trạng thái: PROCESSING
Vòng 3: lookupOrder({"orderId":"ORD-2048"})
        -> trạng thái: PROCESSING
Vòng 4: lookupOrder({"orderId":"ORD-2048"})
        -> trạng thái: PROCESSING
```

Nếu ứng dụng không đặt giới hạn, mô hình có thể tiếp tục yêu cầu cùng thao tác. Trong khi đó, các trường hợp sau chưa chắc là vòng lặp:

```text
searchProducts({"query":"keyboard","cursor":"page-1"})
searchProducts({"query":"keyboard","cursor":"page-2"})
searchProducts({"query":"keyboard","cursor":"page-3"})
```

Tên công cụ giống nhau nhưng cursor thay đổi, nên đây có thể là phân trang hợp lệ. Detector cần phân biệt lời gọi trùng ý nghĩa với những lần gọi cùng công cụ nhưng có tiến triển.

## Phân biệt giới hạn số lần gọi và phát hiện lời gọi trùng

`DefaultToolCallingManager` của Spring AI 2.1.0 có hai giới hạn mặc định trong một lượt:

| Giới hạn | Mặc định | Mục đích |
|---|---:|---|
| Số lần gọi cho mỗi tool | 40 | Ngăn một công cụ bị gọi quá nhiều lần |
| Tổng số tool call | 150 | Ngăn tổng số lần thực thi của tất cả công cụ vượt ngưỡng |

Manager đếm các `ToolResponseMessage` từ `UserMessage` cuối cùng trở đi. Bộ đếm này không so sánh tên công cụ với JSON arguments để xác định hai lần gọi có giống nhau hay không. Vì vậy, 10 lần gọi `lookupOrder` với 10 order ID khác nhau và 10 lần gọi `lookupOrder` với cùng một order ID đều tiêu thụ cùng số lượng trong giới hạn per-tool.

Có thể cấu hình các giới hạn tích hợp bằng properties:

```properties
spring.ai.tools.limits.max-calls-per-tool-default=8
spring.ai.tools.limits.max-calls-per-tool.lookupOrder=4
spring.ai.tools.limits.max-total-tool-calls=25
spring.ai.tools.limits.on-limit-exceeded=THROW
```

`on-limit-exceeded` cũng có thể là `RETURN_ERROR_RESPONSE`, khi đó manager bỏ qua lời gọi vượt giới hạn và tạo tool response lỗi để mô hình biết giới hạn đã đạt. Các giá trị trên chỉ là ví dụ cấu hình; hãy chọn ngưỡng theo đặc điểm nghiệp vụ và ngân sách request.

Hai lớp bảo vệ giải quyết hai vấn đề khác nhau:

| Cơ chế | Phát hiện | Ví dụ |
|---|---|---|
| Giới hạn số lần gọi của Spring AI | Một tool hoặc toàn bộ request bị gọi quá số lần cho phép | `lookupOrder` đã được gọi 8 lần trong lượt |
| Repetition guard của ứng dụng | Cùng một lời gọi có cùng ý nghĩa xuất hiện quá ngưỡng | `lookupOrder` với `orderId=ORD-2048` bị yêu cầu lặp lại lần thứ ba |

Nên dùng cả hai. Giới hạn tổng bảo vệ trước trường hợp mô hình thay đổi đối số liên tục để né detector trùng; repetition guard bắt được vòng lặp chính xác xảy ra ngay cả khi tổng số call vẫn còn thấp.

## Xác định thế nào là cùng một lời gọi?

Một khóa nhận diện cơ bản nên gồm:

```text
fingerprint = toolName + canonicalArguments
```

Ví dụ, hai JSON sau có cùng ý nghĩa nếu thứ tự thuộc tính không ảnh hưởng đến hợp đồng tool:

```json
{"orderId":"ORD-2048","includeItems":true}
```

```json
{
  "includeItems": true,
  "orderId": "ORD-2048"
}
```

Nếu so sánh chuỗi thô, hai đối số này khác nhau do khoảng trắng và thứ tự key. Hãy parse JSON, sắp xếp key của object một cách đệ quy rồi serialize lại trước khi tạo fingerprint.

Khi xây dựng fingerprint, lưu ý:

- Dùng tên tool cùng arguments; không dùng tool call ID vì model có thể tạo ID mới ở mỗi lần lặp.
- Sắp xếp key của JSON object để bỏ khác biệt về thứ tự thuộc tính.
- Giữ nguyên thứ tự phần tử của array vì thứ tự có thể mang ý nghĩa nghiệp vụ.
- Chỉ chuẩn hóa chữ hoa/thường, khoảng trắng bên trong chuỗi, đơn vị hoặc giá trị số khi hợp đồng của tool quy định các dạng đó tương đương.
- Không loại bỏ trường có ảnh hưởng tới kết quả. Ví dụ, `cursor`, `page`, `status` hoặc `includeHistory` có thể làm lời gọi khác về mặt nghiệp vụ.
- Không thêm các giá trị ngẫu nhiên như trace ID vào arguments chỉ để tránh detector. Correlation ID không phải một phần của ý nghĩa nghiệp vụ.
- Nếu guard tồn tại lâu hơn một request hoặc có nhiều tenant, đưa phạm vi bảo mật đã xác thực vào khóa. Với guard chỉ sống trong một request của một user/tenant, phạm vi có thể đã được bảo đảm bởi lifecycle của guard.

Không nên coi hai lời gọi của hai tool khác nhau là trùng chỉ vì chúng nhận cùng một chuỗi đối số. Ví dụ `lookupOrder(orderId)` và `getOrderStatus(orderId)` có thể là hai thao tác khác nhau. Tên tool cần nằm trong fingerprint.

## Chuẩn hóa JSON trước khi so sánh

Một helper có thể parse arguments thành `JsonNode`, sắp xếp key đệ quy và giữ nguyên thứ tự array:

```java
private JsonNode sortObjectKeys(JsonNode node) {
    if (node.isObject()) {
        ObjectNode sorted = objectMapper.createObjectNode();
        List<String> names = new ArrayList<>();
        node.fieldNames().forEachRemaining(names::add);
        Collections.sort(names);

        for (String name : names) {
            sorted.set(name, sortObjectKeys(node.get(name)));
        }
        return sorted;
    }

    if (node.isArray()) {
        ArrayNode sorted = objectMapper.createArrayNode();
        node.forEach(value -> sorted.add(sortObjectKeys(value)));
        return sorted;
    }

    return node.deepCopy();
}

private String canonicalize(String rawArguments) {
    try {
        JsonNode parsed = objectMapper.readTree(rawArguments);
        if (parsed == null || !parsed.isObject()) {
            throw new IllegalArgumentException("Tool arguments phải là JSON object.");
        }
        return objectMapper.writeValueAsString(sortObjectKeys(parsed));
    }
    catch (JsonProcessingException ex) {
        throw new IllegalArgumentException("Không thể chuẩn hóa tool arguments.", ex);
    }
}
```

Đây là canonicalization ở mức cấu trúc object. Nếu hệ thống coi `1`, `1.0` hoặc hai định dạng ngày giờ là tương đương, hãy chuẩn hóa các trường đó theo schema nghiệp vụ trước khi serialize. Không tự động đổi mọi chuỗi thành chữ thường hoặc xóa khoảng trắng, vì có thể làm hai giá trị thực sự khác nhau trở thành một.

## Theo dõi số lần lặp trong phạm vi một lượt

Detector cần lưu trạng thái cho từng lượt người dùng, không lưu một bộ đếm mutable dùng chung cho mọi request. Nếu đặt map đếm vào singleton Spring bean mà không tách key theo conversation/turn, lời gọi của user A có thể ảnh hưởng user B và gây từ chối sai.

Một chính sách đơn giản là cho phép một lời gọi ban đầu và một lần thử lại cùng fingerprint; lần thứ ba bị chặn. Ngưỡng này chỉ là ví dụ, có thể cấu hình riêng theo tool:

```java
public final class RepeatedToolCallGuard {

    private final int maxIdenticalCalls;
    private final byte[] fingerprintKey;
    private final Map<String, Integer> counts = new HashMap<>();

    public RepeatedToolCallGuard(int maxIdenticalCalls, byte[] fingerprintKey) {
        this.maxIdenticalCalls = maxIdenticalCalls;
        this.fingerprintKey = fingerprintKey.clone();
    }

    public synchronized void checkBatch(List<AssistantMessage.ToolCall> calls) {
        Map<String, Integer> pending = new HashMap<>();

        for (AssistantMessage.ToolCall call : calls) {
            String key = fingerprint(call.name(), canonicalize(call.arguments()));
            int countInBatch = pending.merge(key, 1, Integer::sum);
            int total = counts.getOrDefault(key, 0) + countInBatch;

            if (total > maxIdenticalCalls) {
                throw new RepeatedToolCallException(
                        call.name(), maxIdenticalCalls);
            }
        }

        // Chỉ commit bộ đếm khi toàn bộ batch vượt qua preflight.
        pending.forEach((key, delta) -> counts.merge(key, delta, Integer::sum));
    }

}
```

Trong ví dụ, `canonicalize(...)` là helper ở phần trước; `fingerprint(...)` dùng HMAC như phần kế tiếp; `RepeatedToolCallException` là exception do ứng dụng định nghĩa. Map chỉ giữ fingerprint đã băm và số lần xuất hiện, không giữ raw arguments.

`checkBatch(...)` kiểm tra toàn bộ tool call trong một phản hồi trước khi manager thực thi bất kỳ callback nào. Nếu một call vượt ngưỡng, batch bị từ chối ở bước preflight. Bộ đếm chỉ được cập nhật khi tất cả call trong batch vượt qua kiểm tra, tránh ghi nhận một phần batch đã bị chặn.

Guard nên được tạo mới ở đầu lượt người dùng. `fingerprintKey` được lấy từ secret manager hoặc cấu hình bí mật của ứng dụng:

```java
public String ask(String question) {
    RepeatedToolCallGuard guard = new RepeatedToolCallGuard(2, fingerprintKey);

    ToolCallingChatOptions options = ToolCallingChatOptions.builder()
            .toolCallbacks(toolCallbacks)
            .build();

    Prompt prompt = new Prompt(question, options);
    ChatResponse response = chatModel.call(prompt);

    while (response.hasToolCalls()) {
        List<AssistantMessage.ToolCall> calls =
                response.getResult().getOutput().getToolCalls();

        guard.checkBatch(calls); // Chặn trước khi callback chạy.

        ToolExecutionResult result =
                toolCallingManager.executeToolCalls(prompt, response);

        if (result.returnDirect()) {
            return convertDirectResult(result);
        }

        prompt = new Prompt(result.conversationHistory(), options);
        response = chatModel.call(prompt);
    }

    return response.getResult().getOutput().getText();
}
```

Ví dụ dùng vòng lặp `ChatModel` do ứng dụng điều khiển. `guard` là biến cục bộ của một lần `ask`, nên không chia sẻ trạng thái giữa các request. `convertDirectResult(...)` là hàm chuyển kết quả trực tiếp theo response contract của ứng dụng. Nếu `checkBatch(...)` ném `RepeatedToolCallException`, tầng điều phối bắt lỗi và kết thúc lượt với một trạng thái có kiểm soát, chẳng hạn `REPEATED_TOOL_CALL`; không tiếp tục gửi cùng một lời gọi cho manager.

## Tạo fingerprint an toàn khi arguments có dữ liệu nhạy cảm

Arguments có thể chứa email, số hợp đồng, mã khách hàng, nội dung tìm kiếm hoặc dữ liệu cá nhân. Không ghi nguyên JSON arguments vào log chỉ để so sánh. Đặt phương thức HMAC-SHA-256 sau vào class `RepeatedToolCallGuard` để tạo khóa ổn định mà không lưu giá trị đầu vào:

```java
private String fingerprint(String toolName, String canonicalArguments) {
    try {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(fingerprintKey, "HmacSHA256"));

        String value = toolName + "\n" + canonicalArguments;
        byte[] digest = mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest);
    }
    catch (GeneralSecurityException ex) {
        throw new IllegalStateException("Không thể tạo tool-call fingerprint.", ex);
    }
}
```

`fingerprintKey` phải đến từ secret manager hoặc cấu hình bí mật của ứng dụng; không hard-code khóa trong source code và không ghi khóa vào log. Tạo một `Mac` mới cho mỗi lần gọi vì `Mac` không được thiết kế để chia sẻ đồng thời giữa nhiều thread. HMAC hữu ích khi fingerprint có thể được lưu hoặc ghi log; nếu chỉ giữ khóa trong bộ nhớ của một request, vẫn nên tránh lưu raw arguments không cần thiết.

Fingerprint không phải bằng chứng xác thực và không thay thế authorization. Nó chỉ là khóa nhận diện một lời gọi trong chính sách chống lặp.

## Phân biệt lặp chính xác với cùng công cụ nhưng có tiến triển

Detector chỉ dựa vào fingerprint chính xác có thể phát hiện cùng tool + cùng arguments. Nhưng có những vòng lặp không dùng lại đối số hoàn toàn:

| Mẫu gọi | Cách nhận diện | Xử lý gợi ý |
|---|---|---|
| Cùng tool, cùng arguments | Fingerprint giống hệt | Chặn khi vượt ngưỡng lặp |
| Cùng tool, cursor/page thay đổi | Fingerprint khác nhau | Cho phép số trang hữu hạn; phát hiện cursor không tiến triển |
| Cùng tool, arguments thay đổi liên tục | Per-tool count tăng | Dùng giới hạn per-tool và tổng call |
| Hai tool luân phiên A-B-A-B | Chuỗi fingerprint lặp theo pattern | Theo dõi cửa sổ gần nhất và phát hiện chu kỳ |
| Cùng tool, cùng arguments nhưng kết quả thay đổi | Fingerprint giống nhau nhưng có thể có tiến triển thời gian | Áp dụng chính sách riêng cho polling và giới hạn thời gian |

### Phát hiện chu kỳ nhiều công cụ

Ví dụ mô hình lặp lại chuỗi:

```text
getPaymentStatus(paymentId)
retryPayment(paymentId)
getPaymentStatus(paymentId)
retryPayment(paymentId)
getPaymentStatus(paymentId)
retryPayment(paymentId)
```

Hai fingerprint đơn lẻ không lặp liên tiếp, nhưng cặp `[getPaymentStatus, retryPayment]` lặp lại. Với các workflow phức tạp, có thể giữ một cửa sổ N fingerprint gần nhất và kiểm tra chuỗi con lặp lại hai hoặc ba lần. Chỉ kích hoạt cơ chế này cho các luồng cần thiết vì chuỗi thao tác giống nhau đôi khi vẫn hợp lệ trong xử lý batch hoặc retry có chủ đích.

### Kiểm tra tiến triển thay vì chỉ đếm lời gọi

Một vòng lặp có tiến triển khi nó tạo ra thông tin hoặc trạng thái mới. Tùy loại tool, ứng dụng có thể theo dõi:

- Cursor hoặc page token đã thay đổi chưa.
- Số bản ghi mới có được trả về không.
- Trạng thái nghiệp vụ có chuyển từ `PENDING` sang `COMPLETED`/`FAILED` không.
- Kết quả có chứa resource ID hoặc version mới không.
- Một điều kiện trước đó đã được giải quyết chưa.

Nếu cursor không thay đổi hoặc cùng một trạng thái được trả về liên tục, có thể dừng phân trang/polling. Với polling hợp lệ, hãy quy định số lần tối đa, deadline tổng, khoảng thời gian giữa các lần kiểm tra và điều kiện dừng rõ ràng. Không để mô hình tự quyết định polling vô hạn.

## Xử lý polling, retry và pagination hợp lệ

Không phải mọi lời gọi giống nhau đều sai. Ví dụ, tool `getJobStatus(jobId)` có thể cần được gọi nhiều lần vì trạng thái job thay đổi theo thời gian. Một công cụ đọc cũng có thể được gọi lại sau khi hệ thống vừa cập nhật dữ liệu.

Thay vì bỏ detector cho toàn bộ tool, hãy khai báo chính sách theo tool:

| Loại tool | Chính sách gợi ý |
|---|---|
| Tra cứu ổn định, read-only | Ngưỡng lặp thấp; có thể cache kết quả trong cùng lượt nếu freshness cho phép |
| Polling trạng thái job | Cho phép số lần poll giới hạn, có deadline và khoảng cách tối thiểu |
| Pagination | Cho phép cursor khác nhau; chặn nếu cursor lặp hoặc không tiến triển |
| Retry dịch vụ tạm thời | Retry ở service/client với backoff và số lần tối đa; không giao retry không giới hạn cho model |
| Ghi dữ liệu hoặc thanh toán | Dùng idempotency key ở service; guard phát hiện vòng lặp không thay thế cơ chế chống giao dịch trùng |

Đối với thao tác ghi, việc chặn lời gọi lặp ở tầng hội thoại không bảo đảm exactly-once. Một request có thể timeout sau khi hệ thống đã commit. Nếu mô hình hoặc client gửi lại cùng thao tác, service cần idempotency key và lưu kết quả của lần thực thi đầu để trả lại khi nhận retry hợp lệ.

## Tích hợp guard với ChatClient tự động

`ChatClient` mặc định dùng `ToolCallingAdvisor` để chạy vòng tool calling tự động. Caller nhận phản hồi cuối sau khi advisor đã thực hiện các callback, vì vậy kiểm tra fingerprint sau `.call()` là quá muộn để ngăn side effect.

Có hai hướng tích hợp:

1. **Bọc `ToolCallback` theo request:** tạo một decorator quanh từng callback, truyền `RepeatedToolCallGuard` riêng của request vào decorator và kiểm tra tên tool cùng raw JSON trước khi delegate thực thi. Decorator phải chuyển tiếp nguyên `ToolDefinition`, `ToolMetadata`, `call(String)` và `call(String, ToolContext)` tới callback gốc. Không giữ guard mutable dùng chung trong singleton callback.
2. **Tự điều khiển vòng lặp hoặc dùng custom `ToolCallingAdvisor`:** kiểm tra toàn bộ batch tool call trước khi gọi manager. Cách này phù hợp khi chính sách yêu cầu nếu một call trong batch bị lặp thì không call nào trong batch được thực thi.

Callback decorator phát hiện ở ranh giới từng lần gọi; nếu nhiều tool được thực thi trong một batch, các callback khác có thể đã chạy trước khi decorator phát hiện một callback lặp. Nếu cần preflight nguyên batch để tránh partial side effect, hãy kiểm tra danh sách `AssistantMessage.ToolCall` trước `executeToolCalls(...)` hoặc tùy biến manager/advisor ở điểm phù hợp.

Khi dùng `ChatClient`, có thể truyền callback đã bọc qua `.tools(...)` cho từng request. Guard phải được tạo mới cho mỗi user turn và không được chia sẻ giữa hai request đồng thời. Nếu hội thoại tạm dừng để xác nhận rồi tiếp tục ở request HTTP khác, hãy lưu trạng thái guard theo conversation/turn ở server-side store và khôi phục nó khi resume.

## Quyết định khi phát hiện lặp

Khi guard phát hiện vượt ngưỡng, ứng dụng cần chọn hành vi rõ ràng:

- **Dừng lượt:** trả trạng thái `REPEATED_TOOL_CALL` cho caller và ghi nhận lý do. Phù hợp khi cần bảo đảm không tiếp tục side effect.
- **Gửi lỗi có kiểm soát về model một lần:** thông báo rằng lời gọi lặp đã bị chặn và yêu cầu mô hình trả lời từ kết quả hiện có hoặc hỏi người dùng. Nếu model tiếp tục lặp, kết thúc lượt.
- **Dùng lại kết quả đã có:** với tool read-only và dữ liệu còn đủ mới, có thể trả lại kết quả đã cache thay vì gọi downstream lần nữa. Cần kiểm tra quyền và freshness trước khi dùng cache.
- **Yêu cầu người dùng làm rõ:** nếu mô hình lặp do thiếu thông tin, kết thúc chuỗi và hỏi người dùng cung cấp dữ liệu còn thiếu.

Không nên chỉ gửi cùng một thông báo lỗi về mô hình ở mọi vòng mà không có ngưỡng dừng. Mô hình có thể tiếp tục gọi cùng tool, làm lỗi lặp lại thành một vòng lặp mới. Khi phát hiện vượt ngưỡng, trạng thái phải được giữ trong guard để lần gọi tiếp theo không thể thực thi lại.

## Quan sát vòng lặp mà không làm lộ đối số

Spring AI phát Micrometer observation cho tool call với tên `spring.ai.tool`, bao gồm tên tool, metadata định nghĩa, thời gian thực thi và tracing context nếu có. Có thể kết hợp observation này với số liệu của guard:

- Tổng số lần gọi theo tool trong một user turn.
- Số fingerprint trùng và số lần bị chặn.
- Lý do dừng: duplicate invocation, repeated cycle, per-tool limit, total limit hoặc deadline.
- Thời gian từ lần gọi đầu tới lần lặp bị chặn.
- Kết quả cuối cùng của service trước khi vòng lặp dừng.

Không ghi raw arguments hoặc dữ liệu nhạy cảm vào log. Nếu cần liên kết các lần gọi, ghi HMAC fingerprint rút gọn cùng request ID, nhưng không ghi secret dùng tạo HMAC. Không ghi token, thông tin xác thực, dữ liệu khách hàng hoặc toàn bộ prompt chỉ để debug vòng lặp.

## Kiểm thử repetition guard

Nên kiểm thử riêng canonicalization, thuật toán đếm và tích hợp trước khi gọi downstream:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Cùng tool, cùng arguments | Fingerprint giống nhau và bộ đếm tăng |
| JSON có key order/whitespace khác | Sau canonicalization vẫn là cùng fingerprint |
| Array có thứ tự khác | Fingerprint khác nếu thứ tự array có ý nghĩa |
| Cùng tool, cursor khác | Không bị xem là cùng lời gọi; vẫn chịu per-tool/total limit |
| Hai tool khác tên, cùng arguments | Không bị gộp thành một fingerprint |
| Tool call ID thay đổi nhưng arguments không đổi | Vẫn nhận diện là cùng lời gọi |
| Vượt ngưỡng trong cùng batch | Preflight từ chối batch trước khi callback được thực thi |
| Lần gọi thứ ba vượt ngưỡng | Ném `RepeatedToolCallException` hoặc trả trạng thái dừng theo chính sách |
| Lượt người dùng mới | Guard mới bắt đầu với bộ đếm rỗng |
| Hai request đồng thời | Bộ đếm của request A không ảnh hưởng request B |
| Polling được cho phép | Số lần poll không vượt ngân sách và kết thúc theo deadline/trạng thái |
| Thao tác ghi bị gọi lại | Idempotency ở service ngăn side effect trùng |
| Model tiếp tục sau thông báo lỗi | Guard vẫn chặn lần lặp tiếp theo; không tạo vòng lỗi vô hạn |

Ví dụ kiểm thử preflight:

```java
@Test
void blocksThirdIdenticalInvocationBeforeExecution() {
    RepeatedToolCallGuard guard = new RepeatedToolCallGuard(2, testFingerprintKey);
    AssistantMessage.ToolCall call1 = new AssistantMessage.ToolCall(
            "call-1", "function", "lookupOrder", """{"orderId":"ORD-2048"}""");
    AssistantMessage.ToolCall call2 = new AssistantMessage.ToolCall(
            "call-2", "function", "lookupOrder", """{ "orderId" : "ORD-2048" }""");
    AssistantMessage.ToolCall call3 = new AssistantMessage.ToolCall(
            "call-3", "function", "lookupOrder", """{"orderId":"ORD-2048"}""");

    guard.checkBatch(List.of(call1));
    guard.checkBatch(List.of(call2));

    assertThatThrownBy(() -> guard.checkBatch(List.of(call3)))
            .isInstanceOf(RepeatedToolCallException.class);
}
```

`testFingerprintKey` là khóa giả chỉ dùng trong test. Trong integration test, gắn guard vào vòng điều phối và dùng mock service để xác minh lần gọi bị chặn không chạm repository hoặc API downstream. Cũng cần test trường hợp pagination có cursor thay đổi để tránh detector chặn nhầm luồng hợp lệ.

## Checklist triển khai

1. Dùng giới hạn per-tool và tổng tool call tích hợp của Spring AI.
2. Xây dựng fingerprint từ tên tool và JSON arguments đã canonicalize.
3. Bỏ tool call ID khỏi fingerprint vì ID thay đổi qua từng lần model yêu cầu.
4. Giữ thứ tự array và chỉ chuẩn hóa giá trị khi schema nghiệp vụ xác nhận chúng tương đương.
5. Tạo guard theo từng user turn; không chia sẻ bộ đếm mutable giữa các request.
6. Kiểm tra toàn bộ batch trước khi thực thi nếu cần tránh partial side effect.
7. Đặt ngưỡng riêng cho polling, pagination và các tool có thể retry hợp lệ.
8. Dùng idempotency ở service cho thao tác ghi; repetition guard không thay thế exactly-once.
9. Khi vượt ngưỡng, dừng hoặc cho model một cơ hội phục hồi có giới hạn.
10. Không ghi raw arguments hoặc fingerprint key vào log.
11. Kiểm thử key order, duplicate batch, cursor tiến triển, reset theo lượt và request đồng thời.

## Kết luận

Phát hiện vòng lặp lặp lại cần nhận diện ý nghĩa của lời gọi thay vì chỉ đếm số lần gọi công cụ. Hãy tạo fingerprint từ tên tool và JSON arguments đã chuẩn hóa, theo dõi trong phạm vi một lượt người dùng và chặn trước khi callback thực thi. Spring AI 2.1.0 cung cấp giới hạn per-tool và tổng tool call để bảo vệ ngân sách; repetition guard của ứng dụng bổ sung khả năng nhận diện cùng lời gọi. Cần giữ ngoại lệ cho pagination, polling và retry có tiến triển, dùng idempotency cho thao tác ghi và kết thúc vòng lặp bằng một trạng thái rõ ràng khi mô hình không còn tiến triển.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools.html) — vòng lặp tự động, `ToolCallingAdvisor`, tool limits, counting và cấu hình `DefaultToolCallingManager`.
- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools/chatmodel-tool-calling.html) — vòng lặp thủ công, kiểm tra `hasToolCalls()` và thực thi bằng `ToolCallingManager`.
- [Spring AI 2.1.x — DefaultToolCallingManager API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/DefaultToolCallingManager.html) — giới hạn số lần gọi theo tool và tổng số tool call.
- [Spring AI 2.1.x — AssistantMessage.ToolCall API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/AssistantMessage.ToolCall.html) — các trường `id`, `name` và `arguments` của một tool call.
