# Return direct không có hiệu lực như mong đợi

Một lập trình viên đánh dấu một công cụ bằng @Tool(returnDirect = true), nhưng khi chạy vẫn thấy mô hình gọi thêm một lượt, diễn giải lại dữ liệu hoặc trả lời bằng một định dạng khác kết quả gốc. Đôi khi tool method đã chạy và trả về String chính xác nhưng ChatClient không dừng; đôi khi hệ thống trả ra tool call chưa được thực thi; có trường hợp chương trình tự gọi tiếp ChatModel dù ToolCallingManager đã báo returnDirect là true.

Muốn chẩn đoán đúng, cần xác định sự cố xảy ra **ở tầng khai báo metadata, tầng chọn và thực thi tool, tầng điều phối vòng lặp hay tầng chuyển kết quả đến caller**. Return direct không phải một lệnh yêu cầu model ngừng suy luận trong prompt. Đó là một flag của ToolMetadata được application/framework kiểm tra **sau khi tool đã được thực thi**.

Bài này thuộc chương *Chẩn đoán sự cố* trong module Spring AI Tool Calling. Nó dùng Spring AI 2.1.0 làm mốc chính và lưu ý sự khác biệt với kiến trúc Spring AI 1.x. Các ví dụ tập trung vào @Tool, ToolCallback, ToolCallingManager, ToolCallingAdvisor, ToolExecutionResult, ChatClient, ChatModel và việc xử lý nhiều tool calls.

## 1. Hiểu đúng hợp đồng return direct

Spring AI hỗ trợ hai cách dùng kết quả một tool call:

1. **Mặc định (returnDirect = false):** công cụ chạy; application thêm tool response vào conversation; model có thể dùng response đó để suy luận và tạo câu trả lời tiếp.
2. **Return direct (returnDirect = true):** công cụ chạy; application bỏ qua lần gửi kết quả ấy lại model và trả nội dung tool result trực tiếp cho caller.

Với ChatClient tự động điều phối, ToolCallingAdvisor nhận ToolExecutionResult từ ToolCallingManager, kiểm tra returnDirect và quyết định kết thúc vòng lặp hay tiếp tục gọi mô hình.

~~~mermaid
flowchart TD
    A[Người dùng gọi ChatClient] --> B[ToolCallingAdvisor gọi model]
    B --> C{Model có tool calls?}
    C -- Không --> D[Trả câu trả lời của model]
    C -- Có --> E[ToolCallingManager thực thi các callback]
    E --> F{Toàn bộ tool call của lượt đều returnDirect?}
    F -- Không --> G[Đưa tool responses lại model]
    G --> B
    F -- Có --> H[Chuyển tool results thành ChatResponse]
    H --> I[Trả về caller, không gọi model thêm]
~~~

Lưu ý: nhánh return direct chỉ xảy ra khi **model thật sự yêu cầu tool** và lời gọi đã được manager thực thi. Nếu model tự trả lời mà không yêu cầu tool, flag trên một tool chưa được gọi đương nhiên không có tác dụng.

### Return direct không có nghĩa là gì?

- Không có nghĩa @Tool method sẽ tự động được gọi mỗi khi người dùng nhắc đến nó.
- Không đồng nghĩa controller REST sẽ bỏ qua toàn bộ mapping/serialization riêng của ứng dụng.
- Không tự xác nhận input hợp lệ, kiểm tra quyền hoặc cấp phép side effect.
- Không bảo đảm result được model diễn giải, dịch, rút gọn hoặc làm đẹp; mục đích của flag chính là bỏ qua bước ấy.
- Không dừng được một vòng lặp thủ công nếu người viết vòng lặp không đọc ToolExecutionResult.returnDirect().
- Không phải cờ bắt buộc model phát một tool call duy nhất thay vì nhiều tool calls.
- Không áp dụng cho một phương thức Java được ứng dụng gọi trực tiếp ngoài framework tool-calling loop.

## 2. Triệu chứng, nguyên nhân và điểm kiểm tra

| Triệu chứng quan sát | Nguyên nhân thường gặp | Điểm kiểm tra trước tiên |
|---|---|---|
| Tool chạy nhưng model vẫn trả lời lại | ToolMetadata.returnDirect false, hoặc batch có một tool non-direct | Metadata của callback thực tế và toàn bộ tool calls trong response |
| Tool không chạy, chỉ thấy yêu cầu function/tool call | Dùng ChatModel trực tiếp trong 2.x hoặc tắt ToolCallingAdvisor | Đường gọi ChatModel/ChatClient và advisor registration |
| Chỉ chạy một vòng nhưng output không phải String kỳ vọng | ToolCallResultConverter đã serialize DTO; REST/UI map tiếp | Raw callback result, ChatResponse generation và response layer |
| returnDirect=true trên annotation nhưng callback báo false | Factory programmatic tạo metadata khác, wrapper làm mất metadata, đăng ký nhầm callback | callback.getToolMetadata().returnDirect() của đúng callback được dispatch |
| Một tool direct nhưng không dừng khi model gọi hai tool | Tool còn lại returnDirect=false | Danh sách tool calls trong cùng assistant response |
| Luồng stream không hiện kết quả như mong muốn | Đọc chunk không phù hợp, client hủy subscription, filter/projection khác | ChatClient streaming response và final aggregation |
| Đã bật returnDirect nhưng tool đòi người dùng xác nhận | requiresConfirmation làm manager tạm dừng trước execution | Metadata và ToolCallDecisions, approval flow |
| Model gọi một tool khác có cùng tên | Catalog/resolver khác hoặc callback không đúng phiên bản | ToolDefinition.name, registry và metadata cuối cùng |
| Một custom advisor vẫn làm thay đổi kết quả direct | Advisor sau tool loop transform ChatResponse hoặc code UI post-process | Advisor ordering và final response mapping |
| Chỉ một số provider/model gặp lỗi | Provider không trả tool-call structure như kỳ vọng | ChatResponse.hasToolCalls và tool call name/arguments |

Trình tự điều tra hiệu quả là: **xác nhận tool call có xảy ra → callback thực tế có metadata gì → tool execution result có returnDirect gì → advisor/manual loop có tôn trọng flag không → caller đọc dữ liệu ở đâu**.

## 3. Kiểm tra đầu tiên: model có gọi đúng tool không?

Đừng kết luận return direct bị hỏng chỉ dựa vào câu trả lời cuối. Trong nhiều yêu cầu, model có thể không gọi tool:

~~~java
@Component
class ReportTools {

    @Tool(
            description = "Lấy nội dung báo cáo đã được tạo theo mã",
            returnDirect = true)
    public String fetchReport(
            @ToolParam(description = "Mã báo cáo") String reportId) {
        return "REPORT:" + reportId;
    }
}
~~~

Gọi bằng ChatClient:

~~~java
String answer = ChatClient.create(chatModel)
        .prompt()
        .user("Lấy nội dung báo cáo R-100 bằng công cụ fetchReport")
        .tools(new ReportTools())
        .call()
        .content();
~~~

Ví dụ trên khai báo đúng flag, nhưng **model vẫn là bên quyết định có phát tool call hay không**. Một prompt nhắc tên công cụ không phải bằng chứng model thực sự dùng nó. Khi debug, thu thập các tín hiệu:

- ChatResponse.hasToolCalls ở model iteration đầu.
- Tool call name và số lượng tool calls model tạo ra.
- Callback nào được ToolCallingManager dispatch.
- Kết quả và metadata của callback sau khi thực thi.
- Số lượt gọi model trước và sau callback.

Không nên log raw arguments, prompt chứa thông tin cá nhân hoặc tool result nhạy cảm. Chỉ log tên tool, tool-call ID, kết quả thành công/thất bại và các cờ metadata đã lọc.

### Phân biệt ChatClient với ChatModel trong 2.x

Với Spring AI 2.x:

- ChatClient mặc định tự đăng ký ToolCallingAdvisor và quản lý vòng gọi công cụ.
- ChatModel trực tiếp chỉ gửi definitions cho model và nhận tool call request; **nó không tự thực thi công cụ**.

Vì vậy, đoạn code này chỉ lấy phản hồi thô của model:

~~~java
ToolCallback[] callbacks = ToolCallbacks.from(new ReportTools());

ChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(callbacks)
        .build();

ChatResponse response = chatModel.call(
        new Prompt("Lấy báo cáo R-100", options));

// response có thể chứa tool calls, nhưng callbacks chưa tự chạy.
~~~

Nếu đã chọn ChatModel trực tiếp thì phải tự thực thi qua ToolCallingManager và quyết định returnDirect trong vòng lặp thủ công; xem mục 8. Không dùng kết quả từ ChatModel trực tiếp để kết luận annotation returnDirect bị bỏ qua.

### ChatClient có thể bị tắt tự điều phối

Trong Spring AI 2.1.0, auto-registration của ToolCallingAdvisor có thể bị tắt:

~~~properties
spring.ai.chat.client.tool-calling.enabled=false
~~~

Hoặc tắt cho riêng request:

~~~java
ChatClientResponse response = chatClient.prompt()
        .user("Lấy báo cáo R-100")
        .tools(new ReportTools())
        .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
        .call()
        .chatClientResponse();
~~~

Trong chế độ đó, tools vẫn có thể được gửi cho model, nhưng callback không được ChatClient tự động thực thi. Nếu ứng dụng chủ động dùng custom ToolAdvisor khác, hãy kiểm tra logic của nó; không giả định mọi custom advisor xử lý returnDirect như ToolCallingAdvisor gốc.

## 4. Kiểm tra metadata trên ToolCallback thực tế

Return direct nằm trong ToolMetadata, không nằm trong JSON arguments, Prompt, ToolContext hoặc ToolDefinition.inputSchema.

~~~java
ToolCallback[] callbacks = ToolCallbacks.from(new ReportTools());

for (ToolCallback callback : callbacks) {
    System.out.printf(
            "tool=%s, direct=%s%n",
            callback.getToolDefinition().name(),
            callback.getToolMetadata().returnDirect()
    );
}
~~~

Với ReportTools.fetchReport trong ví dụ, callback tương ứng phải có returnDirect=true. Nếu kết quả false, trước tiên kiểm tra:

1. Annotation @Tool đang nằm trên đúng method được factory quét.
2. Tool được truyền tới ChatClient chính là object/ToolCallback đã kiểm tra.
3. Có ToolCallback bean, resolver hoặc registry khác khai báo cùng tên không.
4. Wrapper/adapter có ủy quyền getToolMetadata() hay tự dựng metadata mặc định.
5. Programmatic callback có thực sự được gắn ToolMetadata.returnDirect(true) không.
6. Phiên bản dependency và import @Tool có khớp Spring AI hiện chạy không.

**Đừng chỉ kiểm tra @Tool trong source rồi cho rằng callback runtime chắc chắn mang flag đó.** Một function callback hoặc remote callback có thể được tạo từ nguồn khác mà không có annotation ấy.

### Phân biệt ToolDefinition và ToolMetadata

~~~text
ToolDefinition:
  name, description, inputSchema  -> model chọn tool và tạo arguments

ToolMetadata:
  returnDirect, requiresConfirmation, ... -> Spring AI điều phối tool

ToolContext:
  tenantId, actorId, correlation ID       -> dữ liệu nội bộ tới callback
~~~

Nếu custom ToolCallback trả đúng name/schema nhưng getToolMetadata() bỏ qua cấu hình gốc, model vẫn chọn được tool và method vẫn chạy, nhưng ToolCallingAdvisor thấy returnDirect=false.

## 5. Khai báo returnDirect theo từng loại tool

### @Tool method

~~~java
class ExportTools {

    @Tool(
            name = "downloadReport",
            description = "Trả nội dung báo cáo sẵn có theo mã, không sửa dữ liệu",
            returnDirect = true)
    String downloadReport(String reportId) {
        return "REPORT:" + reportId;
    }
}
~~~

Kiểm tra callback tạo từ chính object này bằng ToolCallbacks.from(...). Không dùng annotation returnDirect trên DTO hoặc service không được đăng ký như tool.

### MethodToolCallback khai báo programmatic

~~~java
Method method = ReflectionUtils.findMethod(
        ExportTools.class, "downloadReport", String.class);

ToolCallback callback = MethodToolCallback.builder()
        .toolDefinition(ToolDefinitions.builder(method)
                .description("Trả nội dung báo cáo theo mã")
                .build())
        .toolMethod(method)
        .toolObject(new ExportTools())
        .toolMetadata(ToolMetadata.builder()
                .returnDirect(true)
                .build())
        .build();
~~~

Đối với callback tạo thủ công, phải đặt returnDirect vào ToolMetadata gắn trên builder. Chỉ tự dựng ToolDefinition với description có câu "trả thẳng" không làm cờ kỹ thuật bật lên.

### FunctionToolCallback khai báo programmatic

~~~java
public record ReportRequest(String reportId) {
}

ToolCallback callback = FunctionToolCallback
        .builder("downloadReport", (ReportRequest r) -> "REPORT:" + r.reportId())
        .description("Lấy nội dung báo cáo theo mã")
        .inputType(ReportRequest.class)
        .toolMetadata(ToolMetadata.builder()
                .returnDirect(true)
                .build())
        .build();
~~~

Các lớp ReportRequest, ExportTools là fixture minh họa. Khi chạy, nên kiểm tra callback.getToolMetadata().returnDirect() ngay sau khi tạo và trước khi đăng ký vào ChatClient. Đừng nhầm constructor FunctionToolCallback với method @Tool mà bạn từng đánh dấu trong source: hai callback là hai đối tượng khác nhau, metadata có thể khác.

## 6. Bẫy quan trọng nhất: nhiều tool calls trong cùng một model response

Spring AI xét returnDirect **trên cả nhóm tool calls được model yêu cầu trong cùng một lượt**, không quyết định độc lập theo từng tool call rồi kết thúc ngay khi gặp một tool direct.

Ví dụ model yêu cầu hai công cụ cùng lúc:

| Tool call | returnDirect | Kết luận cho toàn nhóm |
|---|---|---|
| downloadReport | true | Chưa đủ để return direct |
| getReportMetadata | false | Toàn nhóm không direct |

Kết quả: hai tool calls được thực thi theo quy tắc của manager, các tool results được đưa lại mô hình và vòng lặp tiếp tục. Đây là hành vi **đúng thiết kế**, không phải annotation bị vô hiệu hóa.

### Quy tắc tổng hợp

~~~text
Nếu model trả 1 tool call:
    returnDirect của nhóm = returnDirect của tool đó

Nếu model trả N tool calls cùng một iteration:
    returnDirect của nhóm = AND(returnDirect của mọi tool được gọi)

Chỉ cần một tool có returnDirect = false:
    returnDirect của nhóm = false
    => tool results được đưa lại model
~~~

Đừng nhầm hai lượt model liên tiếp với một nhóm nhiều tool calls. Khi lượt đầu chứa một tool direct duy nhất và được thực thi, advisor dừng vòng. Ngược lại, nếu model trả ba tool trong **cùng một response**, toàn bộ ba metadata được xét chung.

### Cách khắc phục khi muốn một công cụ dừng vòng

1. Nếu tất cả kết quả có thể trả nguyên vẹn cho caller, cân nhắc đặt returnDirect=true cho mọi tool của nhóm, sau khi xác định format của nhiều kết quả.
2. Nếu một tool phụ chỉ phục vụ chuẩn bị dữ liệu, thiết kế một tool cấp use case thực hiện phần đọc/ghép cần thiết trong service và trả một result duy nhất.
3. Nếu cần mô hình diễn giải kết quả tổng hợp, dùng returnDirect=false và để model tiếp tục; không ép returnDirect để đạt mục tiêu trái ngược.
4. Nếu cần quy tắc dừng riêng (ví dụ dừng khi một tool cụ thể chạy thành công bất kể tool khác), đó là một **chính sách điều phối tùy chỉnh**, không phải hành vi mặc định của returnDirect. Khi thiết kế lại, phải xem xét side effect, giới hạn gọi và thứ tự thực thi.

Không nên sửa mô tả của tool thành "hãy chỉ gọi một công cụ" rồi coi đó là bảo đảm. Model có thể vẫn phát nhiều tool calls; quy tắc an toàn phải nằm ở ứng dụng và được test với dữ liệu response thực tế.

### Trường hợp batch có tool bị từ chối hoặc chờ xác nhận

Trong Spring AI 2.1.0, requiresConfirmation là cơ chế riêng. Nếu một tool call trong nhóm cần người phê duyệt, ToolCallingManager sẽ tạm dừng cả nhóm trước khi thực thi. Sau khi resume, nếu có một tool bị từ chối thì kết quả không được return direct như nhóm đã được chấp thuận đầy đủ.

Vì vậy:

- **Chưa chạy tool:** đừng dùng returnDirect để giải thích tại sao vòng lặp tạm dừng.
- **Sau phê duyệt:** kiểm tra kết quả ToolExecutionResult.returnDirect() của lần thực thi sau resume.
- **Sau từ chối:** xử lý thông điệp từ chối theo policy; không ép trả direct một kết quả chưa thực thi.

## 7. Kiểm tra ToolCallingAdvisor và chế độ execution

Một tool có metadata đúng chỉ là điều kiện cần. Chương trình vẫn phải đi qua thành phần điều phối thực thi và kiểm tra flag.

### ChatClient mặc định

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(new ReportTools())
        .build();

String result = chatClient.prompt()
        .user("Lấy báo cáo R-100")
        .call()
        .content();
~~~

Theo thiết kế Spring AI 2.1.0, ChatClient mặc định tự đăng ký một ToolCallingAdvisor nếu không bị tắt hoặc thay thế. Khi callback có returnDirect=true và model gọi duy nhất callback đó trong lượt, ToolCallingAdvisor thực thi, kiểm tra ToolExecutionResult.returnDirect(), dừng vòng và trả kết quả tool làm nội dung generation của ChatResponse.

Điều này **không** có nghĩa String result được đưa thẳng qua network đến browser. Controller, SSE adapter, DTO mapper hoặc frontend có thể vẫn sửa, encode, trim hoặc bỏ qua field. Khi debug, phân biệt kết quả ở ChatClient với kết quả người dùng nhìn thấy.

### Kiểm tra có ToolAdvisor tùy chỉnh không

Spring AI 2.x có quy tắc mỗi advisor chain chỉ chứa một ToolAdvisor. Nếu ứng dụng dùng custom ToolAdvisor, ToolSearchToolCallingAdvisor hoặc subclass ToolCallingAdvisor, hãy kiểm tra chính implementation đang chạy:

- Nó có gọi ToolCallingManager.executeToolCalls hay không?
- Nó có kiểm tra ToolExecutionResult.returnDirect() trước lượt model tiếp theo không?
- Có hook doBeforeCall/doAfterCall hoặc doFinalizeLoop biến đổi response không?
- Có advisor ngoài vòng loop sửa final ChatClientResponse không?
- Có một cấu hình đang tắt auto-registration hoặc thay bằng vòng điều phối khác không?

Khi custom loop cố tình bỏ qua returnDirect, đổi annotation ở method không thể sửa lỗi. Phải chỉnh policy tại nơi tiêu thụ ToolExecutionResult.

### Một lời gọi Java trực tiếp không kích hoạt returnDirect

~~~java
String raw = reportTools.fetchReport("R-100");
~~~

Dòng này chỉ là lời gọi Java. Annotation @Tool không can thiệp vào control flow của Java. Tương tự:

~~~java
String raw = callback.call("{\"reportId\":\"R-100\"}");
~~~

Đây là thực thi ToolCallback trực tiếp, trả một String. Nó không có vòng lặp model để dừng. Test loại này rất tốt để xác minh result conversion, nhưng không chứng minh ToolCallingAdvisor xử lý returnDirect đúng.

## 8. Khi tự điều phối bằng ChatModel, phải kiểm tra ToolExecutionResult

Trong Spring AI 2.1.0, ChatModel.call(prompt) không tự thực thi tool. Ứng dụng có thể tự xây vòng lặp; chính vòng lặp này phải tôn trọng returnDirect:

~~~java
ChatModel model = ...;
ToolCallingManager manager = ToolCallingManager.builder().build();

ToolCallback[] callbacks = ToolCallbacks.from(new ReportTools());
ChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(callbacks)
        .build();

Prompt prompt = new Prompt("Lấy báo cáo R-100", options);
ChatResponse response = model.call(prompt);

while (response != null && response.hasToolCalls()) {
    ToolExecutionResult execution =
            manager.executeToolCalls(prompt, response);

    if (execution.returnDirect()) {
        // Không gọi model lần nữa. Chuyển các result sang caller.
        List<Generation> directGenerations =
                ToolExecutionResult.buildGenerations(execution);
        return new ChatResponse(directGenerations);
    }

    prompt = new Prompt(execution.conversationHistory(), options);
    response = model.call(prompt);
}

return response;
~~~

Các biến model, manager và return được viết như phần thân của một service method trả ChatResponse. Điểm mấu chốt là **kiểm tra execution.returnDirect() ngay sau executeToolCalls và trước khi tạo request model mới**.

### Ví dụ sai: luôn gọi model sau tool

~~~java
while (response.hasToolCalls()) {
    ToolExecutionResult execution =
            manager.executeToolCalls(prompt, response);

    // Sai: bỏ qua execution.returnDirect()
    prompt = new Prompt(execution.conversationHistory(), options);
    response = model.call(prompt);
}
~~~

Ở đây mọi tool result, kể cả direct, đều quay lại model vì code ứng dụng tự làm thế. Thêm @Tool(returnDirect=true) không thay đổi vòng while này.

### Đừng chỉ return conversationHistory rồi tưởng đã trả final text

ToolExecutionResult.conversationHistory() là danh sách messages gồm hội thoại và tool responses. Nó không tự là HTTP response body hoặc String dành cho người dùng. Khi muốn trả dạng ChatResponse, Spring AI có ToolExecutionResult.buildGenerations(execution) giúp chuyển tool results thành generations.

Nếu API ngoài cần DTO riêng, hãy định nghĩa rõ cách lấy nội dung cần trả từ các tool results đã được xác thực và được phép. Đừng chỉ lấy message cuối rồi ép thành String khi một batch có thể chứa nhiều kết quả, hoặc khi response còn metadata quan trọng như tool-call ID.

### Với ChatClient đã tắt auto ToolAdvisor

Nếu dùng ChatClient nhưng tự quản lý tool execution bằng AdvisorParams.toolCallingAdvisorAutoRegister(false), áp dụng cùng nguyên tắc:

1. Lấy ChatClientResponse hoặc ChatResponse đầy đủ để kiểm tra hasToolCalls.
2. Truyền Prompt tương ứng và response đó cho ToolCallingManager.
3. Nếu ToolExecutionResult.returnDirect() true thì kết thúc và trả trực tiếp.
4. Chỉ khi false mới ghép conversationHistory vào prompt lượt tiếp theo.

Không gọi lại một prompt mới thiếu lịch sử tool calls hoặc không mang tool callbacks cần thiết, vì provider có thể từ chối hoặc model không nhìn thấy kết quả đã thực thi.

## 9. Return direct và định dạng kết quả

Kết quả tool luôn được ToolCallResultConverter chuyển thành String cho giao thức tool calling. Converter mặc định dựa vào Jackson để serialize Java result. Điều này có hai hệ quả:

- Nếu tool trả DTO, caller có thể nhìn thấy JSON result thay vì một câu trả lời văn xuôi.
- Nếu tool trả String hoặc một format tùy chỉnh, cần kiểm tra output thực tế ở callback boundary; đừng đoán dấu ngoặc kép, escape sequence hay whitespace từ kiểu Java trả về.

Ví dụ:

~~~java
public record ReportPayload(
        String reportId,
        String status,
        List<String> sections) {
}

@Tool(
        description = "Trả dữ liệu báo cáo để client hiển thị",
        returnDirect = true)
ReportPayload getReport(String reportId) {
    return reportService.readAuthorized(reportId);
}
~~~

Đặt returnDirect không tự biến ReportPayload thành Markdown hay một summary bằng tiếng Việt. Nó trả tool result đã serialize, theo converter đang cấu hình. Nếu UI cần JSON có schema ổn định, hãy thiết kế DTO và kiểm thử converter; nếu UI cần văn bản đọc được, trả String đã format hoặc đặt custom ToolCallResultConverter phù hợp.

### Đừng sửa returnDirect để giải quyết lỗi serialization

Nếu tool result "trông như" sai định dạng, kiểm tra:

1. Return type của method/Function callback.
2. ToolCallResultConverter hiện được dùng.
3. Giá trị callback.call(json) thực tế.
4. ChatResponse generation content sau ToolCallingAdvisor.
5. API/controller có serialize hoặc wrap kết quả thêm lần nữa không.

Ví dụ controller có thể trả:

~~~java
return Map.of("answer", chatClient.prompt().user(question)
        .call().content());
~~~

HTTP response khi ấy là JSON có field answer, dù ChatClient đã return direct. Đây là định dạng response của ứng dụng, không phải lỗi của Spring AI.

### Return direct không đồng nghĩa "không còn token"

Model vẫn phải được gọi **ít nhất một lượt** để quyết định tool nào cần dùng và tạo arguments. ReturnDirect tránh lần model continuation **sau** tool execution khi đủ điều kiện, chứ không tránh model call đầu tiên. Nếu thấy vẫn có một model request trước tool, đó là hành vi bình thường.

## 10. Streaming: kiểm tra đúng kết quả cuối, không chỉ các chunk

Trong ChatClient streaming, ToolCallingAdvisor cũng hỗ trợ returnDirect. Nhưng kết quả stream gồm nhiều ChatResponse chunks, còn provider có thể stream từng phần arguments trước khi tool call hoàn chỉnh xuất hiện.

Một số lỗi quan sát thường gặp:

| Hiện tượng | Giải thích |
|---|---|
| UI không thấy tool-call chunk trung gian | ToolCallingAdvisor có thể lọc chunk tool call khỏi stream trả về caller; advisor bên trong loop mới quan sát từng iteration |
| UI thấy arguments từng mảnh rồi hiểu nhầm đã thực thi | Partial ToolCallPart không phải tool call hoàn chỉnh; manager chỉ xử lý call đã hoàn thiện |
| Stream bị hủy trước kết quả tool | Cancellation có thể ngăn subscriber nhận final generation |
| Tool chạy nhưng frontend không hiển thị trực tiếp | SSE mapper chỉ forward text hoặc bỏ qua loại chunk mang kết quả |
| Model call count khó xác định | Một user turn có thể có nhiều model iterations; phải ghi theo iteration và theo tool call |

Khi debug, thử trước bằng blocking path:

~~~java
ChatResponse response = chatClient.prompt()
        .user("Lấy báo cáo R-100")
        .tools(new ReportTools())
        .call()
        .chatResponse();

System.out.println(response.getResult().getOutput().getText());
~~~

Nếu blocking path trả kết quả tool đúng và không có model continuation nhưng stream/UI sai, vấn đề có thể thuộc tầng streaming aggregator, subscriber hoặc response transformation, không phải @Tool metadata.

Với streaming:

~~~java
Flux<ChatResponse> chunks = chatClient.prompt()
        .user("Lấy báo cáo R-100")
        .tools(new ReportTools())
        .stream()
        .chatResponse();

return chunks;
~~~

Đây là đoạn bên trong một controller/service trả Flux. Khi UI chỉ cần text có thể dùng stream().content(), nhưng khi chẩn đoán hãy kiểm tra ChatResponse đầy đủ để không bỏ mất finish reason, tool-call parts hoặc metadata liên quan.

### Streaming thủ công cần tổng hợp trước khi kiểm tra returnDirect

Nếu tự điều phối ChatModel.stream hoặc ChatClient.stream đã tắt ToolAdvisor, không kiểm tra hasToolCalls trên từng chunk rời rạc. Trong Spring AI 2.1.0, ChatClientMessageAggregator / MessageAggregator giúp tổng hợp response một iteration rồi mới gọi ToolCallingManager. Sau manager.executeToolCalls, phải kiểm tra returnDirect như blocking path trước khi tạo stream model tiếp.

Không gọi callback dựa trên fragment JSON arguments chưa đầy đủ. Một ToolCallPart partial có thể thiếu id, name hoặc phần cuối của JSON; thực thi sớm có thể tạo side effect sai hoặc trùng.

### Return direct không đảm bảo client vẫn kết nối

Một tool có thể bắt đầu trước khi SSE subscriber bị hủy. Do đó:

- Hủy subscription không đồng nghĩa tool đã rollback.
- Direct result không tự hủy transaction hoặc gọi compensation.
- Nếu tool tạo side effect, application service cần idempotency, operation state và khả năng truy vấn lại.
- Với thao tác cần chạy sau khi client disconnect, dùng durable job/workflow rồi trả operation ID thay vì giữ tool execution gắn chặt với SSE connection.

## 11. Những khác biệt giữa các phiên bản Spring AI

Spring AI 1.x và 2.x không dùng cùng cơ chế điều phối. Đọc nhầm tài liệu có thể dẫn đến cấu hình "đúng" nhưng không có tác dụng.

| Phiên bản | Ai quản lý tool loop mặc định? | Điểm kiểm tra returnDirect |
|---|---|---|
| Spring AI 1.x | Vòng tool execution nội bộ ChatModel theo options của phiên bản | ToolCallback metadata và manager/model internal execution behavior |
| Spring AI 2.0/2.1 | ToolCallingAdvisor trong ChatClient | ToolMetadata → ToolExecutionResult.returnDirect → ToolCallingAdvisor |
| Spring AI 2.x dùng ChatModel trực tiếp | Ứng dụng phải tự điều phối | Chính vòng lặp tự viết phải kiểm tra execution.returnDirect |

Trong 1.x, có thể gặp ví dụ dùng internalToolExecutionEnabled(false) để tắt auto tool execution. Trong 2.x, per-ChatModel internal execution loop đã bị loại bỏ; không lấy flag cũ làm giải pháp cho lỗi returnDirect của ToolCallingAdvisor.

Kiểm tra phiên bản thực sự qua dependency management của dự án và tài liệu tương ứng. Với Spring AI 2.1.0, xem cả API returnDirect, requiresConfirmation và hỗ trợ batch. Nếu cần so sánh giữa bản 1.0, 1.1, 2.0 và 2.1, hãy dùng test thực tế theo từng bản thay vì giả định một property hoạt động giống nhau.

## 12. Chẩn đoán nhanh theo chuỗi bằng chứng

Thay vì thay đổi nhiều thứ cùng lúc, thu thập bằng chứng theo thứ tự:

~~~mermaid
flowchart TD
    A[Tool không return direct như mong đợi] --> B{Tool callback có thực sự chạy?}
    B -- Không --> C[Kiểm tra model tool call, ChatModel vs ChatClient, ToolAdvisor]
    B -- Có --> D{Callback runtime returnDirect = true?}
    D -- Không --> E[Kiểm tra annotation, factory, Function callback, wrapper]
    D -- Có --> F{Batch có hơn một tool call?}
    F -- Có --> G{Tất cả tool có returnDirect=true?}
    G -- Không --> H[Đúng hành vi: gửi cả batch cho model]
    G -- Có --> I[Kiểm tra ToolExecutionResult.returnDirect]
    F -- Không --> I
    I --> J{execution.returnDirect true?}
    J -- Không --> K[Kiểm tra confirmation, error, custom manager, policy]
    J -- Có --> L{Có gọi model thêm?}
    L -- Có --> M[Manual loop/custom advisor bỏ qua flag]
    L -- Không --> N[Kiểm tra result converter, ChatResponse, stream/UI mapping]
~~~

Checklist bằng chứng tối thiểu của một lần lỗi:

1. Spring AI version chính xác.
2. Đường vào ChatClient.call(), ChatClient.stream() hay ChatModel.call()/stream().
3. Có hay không ToolCallingAdvisor/ToolSearchToolCallingAdvisor/custom ToolAdvisor.
4. Tool names được offer cho model trong request.
5. Model trả bao nhiêu tool calls trong cùng response.
6. getToolMetadata().returnDirect() của từng callback thực tế.
7. ToolCallingManager có thực thi từng call thành công không.
8. ToolExecutionResult.returnDirect() ở manager boundary.
9. Số lượt model call trước và sau execution.
10. Raw tool result String, ChatResponse generation text và HTTP/SSE payload cuối.

Chỉ cần một dấu vết bị thiếu ở bước nào, hãy thu hẹp tìm kiếm ở bước đó trước. Ví dụ callback metadata=false thì chưa cần điều tra streaming. Nếu execution.returnDirect=true nhưng code tự gọi model tiếp, không cần sửa annotation.

## 13. Kiểm thử trực tiếp để loại trừ lỗi metadata

Test đầu tiên không cần mô hình thật. Tạo ToolCallback từ fixture có @Tool và kiểm tra metadata:

~~~java
class ReturnDirectToolTest {

    @Test
    void annotationIsReflectedInToolMetadata() {
        ToolCallback[] callbacks = ToolCallbacks.from(new ReportTools());

        ToolCallback callback = Arrays.stream(callbacks)
                .filter(c -> "fetchReport".equals(
                        c.getToolDefinition().name()))
                .findFirst()
                .orElseThrow();

        assertThat(callback.getToolMetadata().returnDirect()).isTrue();

        String output = callback.call("{\"reportId\":\"R-100\"}");
        assertThat(output).contains("REPORT:R-100");
    }
}
~~~

Ví dụ dùng JUnit Jupiter và AssertJ; các import tương ứng phải được thêm vào file test thực tế. Assertion về callback.call chỉ chứng minh method/result converter hoạt động, **không tự chứng minh model loop đã dừng**.

### Kiểm thử toàn nhóm tool calls bằng manager

Một test deterministic có thể tạo ChatResponse giả với hai tool calls. Dùng ToolCallingManager thật với callbacks của fixture, không cần ChatModel:

~~~java
class BatchTools {

    @Tool(returnDirect = true)
    public String getReport() {
        return "REPORT";
    }

    @Tool
    public String getMetadata() {
        return "METADATA";
    }
}

@Test
void mixedBatchMustContinueToModel() {
    ToolCallback[] tools = ToolCallbacks.from(new BatchTools());

    ChatOptions options = ToolCallingChatOptions.builder()
            .toolCallbacks(tools)
            .build();

    Prompt prompt = new Prompt("Lấy báo cáo và metadata", options);

    AssistantMessage toolCalls = AssistantMessage.builder()
            .toolCalls(List.of(
                    new AssistantMessage.ToolCall(
                            "c1", "function", "getReport", "{}"),
                    new AssistantMessage.ToolCall(
                            "c2", "function", "getMetadata", "{}")))
            .build();

    ChatResponse requested = new ChatResponse(
            List.of(new Generation(toolCalls)));

    ToolCallingManager manager = ToolCallingManager.builder().build();
    ToolExecutionResult executed =
            manager.executeToolCalls(prompt, requested);

    assertThat(executed.returnDirect()).isFalse();
}
~~~

Ở đây getReport có returnDirect=true nhưng getMetadata mặc định false. Vì vậy manager phải trả returnDirect=false cho toàn nhóm. Một test khác đặt @Tool(returnDirect=true) cho cả hai method và kiểm tra executed.returnDirect() là true.

Để test thực tế không phụ thuộc vào provider, tạo các assistant tool call messages bằng constructor của đúng version đang dùng. Bản 2.1.0 sử dụng AssistantMessage.ToolCall(id, type, name, arguments), với type thường là function.

### Kiểm thử trường hợp một tool direct duy nhất

~~~java
@Test
void aSingleDirectToolReturnsDirect() {
    ToolCallback[] tools = ToolCallbacks.from(new ReportTools());

    ChatOptions options = ToolCallingChatOptions.builder()
            .toolCallbacks(tools)
            .build();
    Prompt prompt = new Prompt("Lấy báo cáo R-100", options);

    AssistantMessage oneCall = AssistantMessage.builder()
            .toolCalls(List.of(new AssistantMessage.ToolCall(
                    "c1", "function", "fetchReport",
                    "{\"reportId\":\"R-100\"}")))
            .build();

    ChatResponse requested = new ChatResponse(
            List.of(new Generation(oneCall)));

    ToolExecutionResult executed = ToolCallingManager.builder()
            .build()
            .executeToolCalls(prompt, requested);

    assertThat(executed.returnDirect()).isTrue();
    assertThat(ToolExecutionResult.buildGenerations(executed))
            .isNotEmpty();
}
~~~

Test này chứng minh manager thực thi callback và tính đúng direct flag. Nó vẫn chưa chứng minh ChatClient/Advisor dừng gọi model; để có bằng chứng cuối, thêm integration test dùng scripted/fake ChatModel và đếm số lượt gọi.

## 14. Integration test: đếm lượt model call

Đặt một fake ChatModel có kịch bản:

- **Call thứ nhất:** trả AssistantMessage chứa một tool call fetchReport.
- **Call thứ hai (nếu xảy ra):** trả một câu "MODEL CONTINUED".

Chạy ChatClient với ToolCallingAdvisor và ReportTools:

~~~java
String answer = ChatClient.create(scriptedChatModel)
        .prompt("Lấy báo cáo R-100")
        .tools(new ReportTools())
        .call()
        .content();

assertThat(scriptedChatModel.callCount()).isEqualTo(1);
assertThat(answer).contains("REPORT:R-100");
~~~

Ở đây scriptedChatModel là fake do test tự triển khai, trả lời theo thứ tự đã định, không phải một class mặc định có sẵn với tên này trong Spring AI. Để test đáng tin:

1. Fake luôn phát tool call ở lượt đầu, không để model thực tự quyết định.
2. Ghi nhận mỗi lần phương thức ChatModel.call được gọi.
3. Nếu returnDirect=true và chỉ có một tool call, call count phải là 1.
4. Đổi tool flag thành false rồi chạy lại: model continuation có thể khiến call count thành 2 và câu trả lời cuối là MODEL CONTINUED.
5. Thêm một tool non-direct vào batch: cũng phải chạy lượt model thứ hai.
6. Test cả ChatClient.call và ChatClient.stream nếu ứng dụng hỗ trợ streaming.

Nếu không dùng fake ChatModel, có thể dùng Mockito với Answer trả ChatResponse lần một/lần hai, nhưng cần stub đúng API của ChatModel trên phiên bản dự án. Không dùng model provider thật cho test đếm vòng vì provider có thể chọn không gọi tool và làm kết quả không ổn định.

## 15. Lỗi, confirmation và side effect có thể che triệu chứng

### Tool exception không tương đương với tool result hợp lệ

ToolCallback có thể ném ToolExecutionException hoặc lỗi parse JSON. ToolExecutionExceptionProcessor ở ToolCallingManager quyết định ném lỗi ra caller hay đưa thông báo lỗi vào tool response để model xử lý. Vì vậy việc có thêm model call sau lỗi chưa chắc là returnDirect bị bỏ qua; trước hết xác minh callback có thực sự trả kết quả thành công hay không.

Không bật returnDirect để che lỗi nghiệp vụ; không trả câu "SUCCESS" chỉ vì framework mong một String. Với tool có side effect, cần lưu operation state và idempotency để chống chạy lại sau timeout.

### requiresConfirmation chạy trước callback

Khi một tool yêu cầu confirmation, ToolCallingManager có thể tạm dừng cả batch để người dùng phê duyệt. Trong trạng thái đang chờ, không có tool result để return direct. Nếu ứng dụng chỉ dùng .call().content(), phản hồi tạm dừng có thể rỗng hoặc không đủ dữ liệu. Dùng .call().chatResponse() và ToolCallDecisions.awaitingDecision(response) để xác định trạng thái chờ phê duyệt.

Sau khi resume với đủ quyết định hợp lệ, chính ToolExecutionResult của batch đã được phê duyệt mới quyết định có return direct hay không. Một tool bị từ chối làm nhóm không return direct theo quy tắc của Spring AI 2.1.0.

### Return direct không bỏ qua security

ReturnDirect không là shortcut cho authorization, confirmation, validation, quota hoặc audit. Tương tự, bypass model continuation có thể khiến kết quả thô được đưa thẳng đến API caller; hãy giới hạn dữ liệu nhạy cảm và kiểm tra quyền trước khi tool chạy.

Nếu tool trả HTML, Markdown hoặc URL do bên thứ ba cung cấp, client phải xử lý nội dung theo loại tin cậy và chống injection/XSS. Không vì không đưa dữ liệu trở lại model mà mặc định result an toàn để render trực tiếp.

## 16. Ghi log chẩn đoán nhưng không làm rò rỉ thông tin

ReturnDirect có thể giảm một vòng model call nhưng sẽ khó điều tra nếu không biết callback nào thực sự chạy. Hãy ghi nhận dữ liệu tối thiểu theo từng user turn:

| Trường quan sát | Ví dụ | Mục đích |
|---|---|---|
| runId / trace ID | opaque identifier | Ghép model invocation với callback |
| framework version | 2.1.0 | Phân biệt hành vi 1.x/2.x |
| entry point | ChatClient.call / stream / ChatModel.call | Biết ai sở hữu loop |
| modelIteration | 1, 2, ... | Thấy có continuation không |
| toolCallId + toolName | c1 / fetchReport | Phân biệt các lời gọi cùng tên |
| toolCountInResponse | 1 hoặc 2 | Phát hiện nhóm mixed direct |
| callbackDirect | true/false | Cờ trên đúng ToolCallback runtime |
| executionDirect | true/false | Quyết định của ToolCallingManager |
| executionOutcome | success / denied / failed | Phân biệt lỗi với kết quả hợp lệ |
| finalSource | model / direct tool result | Xác minh output đến từ đâu |

Với metrics, không đưa raw JSON arguments, tool result, JWT, tenant secret hoặc user ID vào low-cardinality tags. Nếu cần điều tra một request cụ thể, dùng trace/log đã phân quyền với retention hợp lý.

Khi benchmark độ trễ, hãy đo số model calls và tổng latency từ đầu request đến response cuối. Một lần direct thành công có thể vẫn tốn thời gian thực thi công cụ, serialization hoặc network của controller. Không kết luận returnDirect không chạy chỉ vì latency không giảm đáng kể.

### Mẫu thông điệp log an toàn

~~~text
tool_iteration runId=... iter=1 toolCalls=2
tool_dispatch   runId=... tool=getReport       direct=true  outcome=success
tool_dispatch   runId=... tool=getMetadata     direct=false outcome=success
tool_execution  runId=... groupDirect=false
model_iteration runId=... iter=2
~~~

Trong tình huống này, lượt model thứ hai là **đúng** vì nhóm mixed direct. Nếu chỉ log getReport.direct=true rồi báo lỗi framework, kết luận sẽ sai.

## 17. Bộ test hồi quy cần có

| Trường hợp | Kết quả kỳ vọng |
|---|---|
| Một @Tool(returnDirect=true) được gọi duy nhất | Tool chạy; manager direct=true; không có model continuation |
| @Tool mặc định false | Tool chạy; manager direct=false; model có thể tiếp tục |
| Một nhóm gồm hai tool đều direct=true | Manager direct=true cho toàn nhóm |
| Nhóm một true, một false | Manager direct=false; toàn nhóm gửi lại model |
| Model không gọi tool | Trả model answer; returnDirect không có tác dụng |
| ChatModel trực tiếp chưa chạy manager | Chỉ có tool-call request; callback không chạy |
| Manual loop đọc result.returnDirect() | Dừng đúng sau direct result |
| Manual loop quên kiểm tra flag | Test bắt được model call ngoài ý muốn |
| Programmatic FunctionToolCallback không có metadata | getToolMetadata().returnDirect() không true |
| Wrapper callback không delegate metadata | Test contract phát hiện cờ bị mất |
| Callback bị lỗi parse arguments | Không coi error path là direct success |
| Tool cần confirmation | Tạm dừng trước execution; xử lý riêng |
| Batch có một tool bị từ chối khi resume | Không return direct như nhóm được duyệt hết |
| Stream hoàn tất | Tool result hiển thị phù hợp sau khi aggregation |
| Stream bị hủy giữa chừng | Không giả định tool đã rollback hoặc client đã nhận final |
| Controller wrap ChatResponse | Phân biệt result conversion và response DTO |
| Tool trả DTO | Kiểm tra JSON string và client parser |
| Tool có side effect | Permission/idempotency vẫn có hiệu lực |
| Thay phiên bản Spring AI | Chạy lại contract test metadata, manager và advisor |

### Kiểm thử custom wrapper làm mất metadata

Một wrapper giám sát tool dễ vô tình làm sai returnDirect khi không ủy quyền ToolMetadata:

~~~java
public final class LoggedToolCallback implements ToolCallback {

    private final ToolCallback delegate;

    public LoggedToolCallback(ToolCallback delegate) {
        this.delegate = delegate;
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return delegate.getToolDefinition();
    }

    @Override
    public ToolMetadata getToolMetadata() {
        return delegate.getToolMetadata();
    }

    @Override
    public String call(String input) {
        return delegate.call(input);
    }

    @Override
    public String call(String input, ToolContext context) {
        return delegate.call(input, context);
    }
}
~~~

Nếu wrapper bỏ getToolMetadata hoặc luôn trả ToolMetadata mặc định, tool vẫn có tên/schema đúng nhưng returnDirect có thể chuyển từ true sang false. Assertion quan trọng:

~~~java
ToolCallback original = ToolCallbacks.from(new ReportTools())[0];
ToolCallback wrapped = new LoggedToolCallback(original);

assertThat(wrapped.getToolDefinition())
        .isEqualTo(original.getToolDefinition());
assertThat(wrapped.getToolMetadata().returnDirect())
        .isEqualTo(original.getToolMetadata().returnDirect());
~~~

Test thêm returnDirect của wrapper trong một nhóm mixed tool calls, vì lỗi metadata có thể chỉ xuất hiện khi manager xét cả batch.

## 18. Bài tập thực hành: tái hiện và xử lý bốn sự cố

Tạo ba công cụ:

1. fetchReport(reportId), returnDirect=true, chỉ đọc báo cáo đã có.
2. getReportMetadata(reportId), returnDirect=false, trả tác giả và ngày tạo.
3. exportReport(reportId), returnDirect=true, có service bảo vệ quyền truy cập.

Thực hiện các bước:

1. Tạo ToolCallbacks.from(...) và assert metadata của từng tool.
2. Dùng fake ChatModel trả đúng một tool call fetchReport, xác minh ChatClient chỉ gọi model một lần.
3. Dùng fake trả hai tool calls fetchReport + getReportMetadata cùng lượt, xác minh vẫn có model continuation.
4. Đổi getReportMetadata thành direct=true, xác minh manager direct=true cho nhóm.
5. Dùng ChatModel.call trực tiếp, quan sát chỉ có tool-call request; thêm vòng manager và điều kiện result.returnDirect().
6. Bỏ cố ý nhánh if(result.returnDirect()) rồi chạy lại để test phát hiện gọi model dư.
7. Bọc exportReport bằng wrapper sai không delegate ToolMetadata; test fail. Sửa wrapper để test pass.
8. Thử một response DTO chứa JSON và kiểm tra controller không double-serialize gây sai format.
9. Chuyển sang stream, xác minh result sau khi aggregation và xử lý subscriber cancellation.
10. Thêm requiresConfirmation cho exportReport và kiểm tra paused reply riêng với direct result.

Ghi lại cho mỗi testcase: model call count, số tool calls trong batch, metadata của callback, ToolExecutionResult.returnDirect, raw tool result, final ChatResponse và lỗi nếu có. Chỉ coi lỗi đã được xử lý khi các chỉ số cho thấy lý do vòng lặp dừng/tiếp tục là xác định được.

## 19. Checklist trước khi kết luận return direct bị lỗi

- [ ] Đã xác định đúng phiên bản Spring AI (1.x hay 2.0/2.1).
- [ ] Model thật sự trả tool call có tên trùng callback cần dùng.
- [ ] Callback runtime đúng là callback được đăng ký vào request, không phải bản khác cùng tên.
- [ ] Đã kiểm tra getToolMetadata().returnDirect() trên callback thực tế.
- [ ] @Tool hoặc programmatic builder thực sự đặt returnDirect=true.
- [ ] Wrapper/adapter ủy quyền ToolDefinition, ToolMetadata và overload call.
- [ ] Nếu có nhiều tool calls trong cùng response, tất cả có direct=true.
- [ ] Không nhầm ChatModel trực tiếp với ChatClient tự động điều phối.
- [ ] ToolCallingAdvisor đang hoạt động, không bị cấu hình tắt hoặc thay thế ngoài ý muốn.
- [ ] Custom ToolAdvisor/manual loop kiểm tra ToolExecutionResult.returnDirect().
- [ ] Confirmation và error path đã được phân biệt với execution thành công.
- [ ] Nếu đã paused để phê duyệt, kết quả resume được xử lý theo quy tắc riêng.
- [ ] Với stream, tool calls được tổng hợp đủ trước dispatch và final result không bị subscriber bỏ mất.
- [ ] ToolCallResultConverter, ChatResponse, controller và UI không bị nhầm với nhau.
- [ ] Đã đếm model calls thay vì suy đoán chỉ từ response text.
- [ ] Có direct callback tests, manager tests và advisor integration tests có fake model.
- [ ] Return direct không làm mất authorization, confirmation, audit hoặc idempotency.
- [ ] Logs/metrics đã lọc thông tin nhạy cảm và không ghi raw tool arguments.

**Kết luận:** Khi returnDirect không có hiệu lực như mong đợi, bốn câu hỏi có giá trị nhất là: **(1)** có tool call thật không, **(2)** ToolCallback được thực thi có metadata direct=true không, **(3)** toàn bộ tool calls trong cùng lượt có direct=true không, và **(4)** thành phần đang sở hữu vòng lặp có tôn trọng ToolExecutionResult.returnDirect không. Nếu bốn điều kiện đã đúng mà output vẫn lạ, hãy chuyển sang kiểm tra result conversion, streaming và lớp API/client hiển thị kết quả. Chẩn đoán đúng ranh giới sẽ giúp sửa lỗi mà không thay đổi tool contract hoặc vô tình tạo side effect mới.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling: Return Direct, ToolMetadata, Result Conversion](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor: Return Direct, Ordering và Auto-Registration](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatModel Tool Calling: ToolExecutionResult trong vòng lặp thủ công](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.0 — Tool Call Confirmation: Pause, Resume và Return Direct](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI 2.1.x API — ToolMetadata và returnDirect()](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/metadata/ToolMetadata.html)
- [Spring AI 2.1.x API — ToolExecutionResult và buildGenerations()](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/ToolExecutionResult.html)
- [Spring AI 2.1.x API — @Tool annotation](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/annotation/Tool.html)
