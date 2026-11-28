# Tùy chỉnh điều kiện tiếp tục bằng ToolExecutionEligibilityChecker

Trong Spring AI 2.x, `ToolCallingAdvisor` điều khiển vòng lặp gọi công cụ: gửi yêu cầu đến model, nhận phản hồi, thực thi các tool call đủ điều kiện, đưa kết quả trở lại hội thoại rồi gọi model tiếp. Mặc định, vòng lặp tiếp tục khi phản hồi có tool call. Khi cần kiểm tra thêm metadata của model hoặc quy tắc riêng của provider, có thể thay đổi điều kiện này bằng `ToolExecutionEligibilityChecker`. Các ví dụ chữ ký interface trong bài nhắm tới Spring AI 2.1.0; nếu dự án dùng 2.0.x, hãy đối chiếu đúng API minor version trước khi triển khai.

Checker là một điểm mở rộng nhỏ nhưng ảnh hưởng trực tiếp đến luồng thực thi. Nếu trả về `true`, advisor cho phép xử lý tool call trong phản hồi và đi tiếp vòng lặp. Nếu trả về `false`, advisor dừng vòng lặp tại phản hồi đó. Vì vậy, điều kiện cần được thiết kế rõ ràng: phải nhận diện đúng phản hồi có tool call, đồng thời chỉ thêm những tiêu chí mà provider thực sự bảo đảm.

## Sau bài học, bạn có thể

- Xác định vị trí của `ToolExecutionEligibilityChecker` trong vòng lặp của `ToolCallingAdvisor`.
- Mô tả điều kiện mặc định và cách checker quyết định có tiếp tục vòng tool calling hay không.
- Tùy chỉnh checker bằng lambda, builder hoặc Spring bean.
- Kết hợp `hasToolCalls()` với finish reason hoặc metadata đặc thù của provider.
- Hiểu tác động khi checker từ chối một phản hồi vẫn chứa tool call.
- Phân biệt điều kiện tiếp tục với phân quyền, xác nhận thao tác và giới hạn số vòng.
- Kiểm thử checker và xử lý khác biệt API khi nâng cấp từ Spring AI 1.x.

## Checker nằm ở đâu trong vòng lặp?

Trong Spring AI 2.x, `ChatClient` sử dụng `ToolCallingAdvisor` để quản lý vòng gọi công cụ. Advisor được tự động đăng ký trong `DefaultChatClient` khi request có tool, trừ khi ứng dụng tắt cơ chế tự đăng ký hoặc đã cung cấp một `ToolAdvisor` phù hợp.

Một vòng gọi cơ bản diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant A as ToolCallingAdvisor
    participant M as Model
    participant E as ToolExecutionEligibilityChecker
    participant T as ToolCallingManager
    participant S as Dịch vụ nghiệp vụ

    U->>C: Câu hỏi và danh sách tool
    C->>A: Bắt đầu vòng gọi
    A->>M: Prompt + ToolDefinition
    M-->>A: ChatResponse
    A->>E: isToolCallResponse(response)
    alt Checker trả về true
        E-->>A: true
        A->>T: Thực thi tool calls
        T->>S: Gọi callback và service
        S-->>T: Kết quả
        T-->>A: ToolExecutionResult
        A->>M: Lịch sử hội thoại + tool result
        M-->>A: ChatResponse tiếp theo
        A->>E: Kiểm tra phản hồi mới
    else Checker trả về false
        E-->>A: false
        A-->>C: Kết thúc vòng lặp
    end
    A-->>C: Kết quả cuối của request
    C-->>U: Câu trả lời
~~~

Checker được gọi sau khi model trả về một `ChatResponse`. Nó quyết định phản hồi đó có kích hoạt lần thực thi tool tiếp theo hay không. Nếu tool được thực thi, `ToolCallingManager` tìm callback, chuyển đối số và `ToolContext` cho callback, nhận kết quả rồi advisor tiếp tục gọi model.

Checker không tự thực thi callback. Nó cũng không tạo hoặc thay đổi `ToolDefinition`. Việc xác định tool nào được cung cấp cho model và việc tìm callback tương ứng vẫn thuộc các thành phần khác của Spring AI.

## Điều kiện mặc định

Trong Spring AI 2.1.0, `ToolExecutionEligibilityChecker` là một functional interface trong package:

~~~java
import org.springframework.ai.model.tool.ToolExecutionEligibilityChecker;
~~~

Chữ ký của interface:

~~~java
import org.springframework.ai.chat.model.ChatResponse;

@FunctionalInterface
public interface ToolExecutionEligibilityChecker {

    boolean isToolCallResponse(@Nullable ChatResponse chatResponse);
}
~~~

Checker mặc định cho phép vòng lặp tiếp tục khi phản hồi khác `null` và có tool call:

~~~java
response -> response != null && response.hasToolCalls()
~~~

Có thể hiểu điều kiện này theo bảng:

| Phản hồi model | Kết quả mặc định | Hành vi |
|---|---:|---|
| `null` | `false` | Không có phản hồi để xử lý |
| Không có tool call | `false` | Kết thúc vòng tool calling |
| Có một tool call | `true` | Cho phép thực thi tool call |
| Có nhiều tool call | `true` | Cho phép xử lý các tool call trong phản hồi |

Điều kiện mặc định phù hợp với phần lớn ứng dụng vì model thường dùng tool call như tín hiệu yêu cầu ứng dụng thực hiện một hành động hoặc truy xuất dữ liệu. Tuy nhiên, một số provider có metadata hoặc finish reason riêng. Khi cần xác nhận thêm rằng model thực sự kết thúc lượt bằng trạng thái gọi công cụ, hãy bổ sung điều kiện đó vào checker.

## Tùy chỉnh bằng lambda

Ví dụ đơn giản nhất là khai báo checker rồi truyền vào builder của `ToolCallingAdvisor`:

~~~java
import org.springframework.ai.chat.client.advisor.ToolCallingAdvisor;
import org.springframework.ai.model.tool.ToolExecutionEligibilityChecker;

ToolExecutionEligibilityChecker checker = response ->
        response != null && response.hasToolCalls();

ToolCallingAdvisor advisor = ToolCallingAdvisor.builder()
        .toolExecutionEligibilityChecker(checker)
        .build();
~~~

Đoạn code trên có cùng hành vi với checker mặc định. Nó hữu ích khi cần cấu hình rõ ràng hoặc chuẩn bị mở rộng điều kiện ở bước tiếp theo.

Nếu muốn kiểm tra thêm finish reason, có thể viết:

~~~java
ToolExecutionEligibilityChecker strictChecker = response ->
        response != null
                && response.hasToolCalls()
                && "tool_calls".equals(response.getMetadata().getFinishReason());

ToolCallingAdvisor advisor = ToolCallingAdvisor.builder()
        .toolExecutionEligibilityChecker(strictChecker)
        .build();
~~~

Điều kiện này yêu cầu đồng thời:

1. Phản hồi tồn tại.
2. Phản hồi chứa ít nhất một tool call.
3. Metadata finish reason có giá trị `tool_calls`.

Chuỗi `tool_calls` trong ví dụ là giá trị minh họa theo cách provider báo kết thúc lượt. Không phải mọi provider đều dùng cùng một chuỗi. Trước khi áp dụng, hãy kiểm tra giá trị metadata thực tế mà model/provider đang trả về. Nếu provider cung cấp enum hoặc finish reason category ổn định hơn, ưu tiên dùng thông tin đó thay vì so sánh chuỗi tùy tiện.

### Vì sao vẫn cần hasToolCalls()?

Finish reason cho biết model kết thúc lượt theo cách nào, nhưng riêng finish reason chưa chứng minh response có một tool call hợp lệ. Kết hợp với `hasToolCalls()` giúp checker chỉ tiếp tục khi response thực sự chứa yêu cầu gọi công cụ.

Ví dụ, điều kiện sau quá rộng:

~~~java
ToolExecutionEligibilityChecker unsafeChecker = response ->
        response != null
                && "tool_calls".equals(response.getMetadata().getFinishReason());
~~~

Nếu provider trả finish reason không nhất quán với nội dung response, điều kiện này có thể cho phép advisor đi tiếp dù không có tool call. Hãy giữ kiểm tra `hasToolCalls()` làm điều kiện nền, rồi mới bổ sung metadata.

## Gắn checker vào ToolCallingAdvisor

Có hai cách cấu hình phổ biến: xây dựng advisor tường minh hoặc cung cấp checker như Spring bean để auto-configuration sử dụng.

### Cấu hình advisor tường minh

Khi cần tự tạo advisor, truyền checker vào `ToolCallingAdvisor.Builder`:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.ToolCallingAdvisor;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.model.tool.ToolExecutionEligibilityChecker;

@Configuration(proxyBeanMethods = false)
public class AssistantConfiguration {

    @Bean
    ChatClient assistantChatClient(ChatModel chatModel) {
        ToolExecutionEligibilityChecker checker = response ->
                response != null
                        && response.hasToolCalls()
                        && "tool_calls".equals(
                                response.getMetadata().getFinishReason()
                        );

        ToolCallingAdvisor toolCallingAdvisor = ToolCallingAdvisor.builder()
                .toolExecutionEligibilityChecker(checker)
                .build();

        return ChatClient.builder(chatModel)
                .defaultAdvisors(toolCallingAdvisor)
                .build();
    }
}
~~~

`ToolCallingAdvisor` là một `ToolAdvisor`, nên `DefaultChatClient` nhận biết advisor đã có trong chain và không tự thêm một tool advisor thứ hai. Spring AI yêu cầu chỉ có một advisor chịu trách nhiệm cho vòng đời tool calling trong một chain.

Nếu cấu hình advisor thủ công, đừng đồng thời thêm một `ToolCallingAdvisor` khác vào cùng chain. Nếu ứng dụng dùng custom advisor khác để điều khiển tool lifecycle, advisor đó cũng cần tuân thủ cơ chế `ToolAdvisor` tương ứng.

### Cung cấp checker bằng Spring bean

Với Spring Boot, có thể khai báo `ToolExecutionEligibilityChecker` thành bean. Builder của `ToolCallingAdvisor` được auto-configure sẽ nhận checker này:

~~~java
@Configuration(proxyBeanMethods = false)
public class ToolEligibilityConfiguration {

    @Bean
    ToolExecutionEligibilityChecker toolExecutionEligibilityChecker() {
        return response ->
                response != null
                        && response.hasToolCalls()
                        && "tool_calls".equals(
                                response.getMetadata().getFinishReason()
                        );
    }
}
~~~

Cách này phù hợp khi muốn dùng cùng một chính sách kiểm tra cho ChatClient được auto-configure. Nếu ứng dụng tự tạo `ToolCallingAdvisor` hoặc tự cấu hình builder, hãy truyền checker trực tiếp để tránh phụ thuộc vào auto-configuration không được sử dụng.

Chỉ đăng ký một checker bean nếu ứng dụng muốn một chính sách mặc định chung. Nếu nhiều module cùng khai báo checker bean, cần xử lý rõ ràng việc chọn bean bằng cấu hình hoặc qualifier theo cơ chế wiring của ứng dụng.

## Điều gì xảy ra khi checker trả về false?

Checker không chỉ là bộ lọc metadata. Kết quả của nó quyết định advisor có tiếp tục vòng tool calling cho response hiện tại hay không.

Giả sử model trả về:

~~~json
{
  "tool_calls": [
    {
      "name": "getOrderStatus",
      "arguments": {
        "orderId": "DH-1024"
      }
    }
  ],
  "finish_reason": "stop"
}
~~~

Với checker yêu cầu finish reason phải là `tool_calls`, kết quả sẽ là `false`. Advisor dừng vòng lặp và tool call trong response đó không được chuyển sang bước thực thi thông thường của vòng lặp. Ứng dụng không nên giả định rằng đơn hàng đã được tra cứu hoặc model đã tạo được câu trả lời cuối cùng.

Đây là hành vi có chủ đích khi provider trả metadata không phù hợp với chính sách. Tuy nhiên, nếu điều kiện quá chặt hoặc so sánh sai giá trị provider, ứng dụng có thể dừng trước một tool call hợp lệ. Khi đó, người dùng có thể nhận một response chưa hoàn chỉnh hoặc không có câu trả lời văn bản hữu ích, tùy response model và cách ứng dụng xử lý kết quả.

Vì vậy:

- Kiểm tra log/metadata khi checker từ chối response có tool call.
- Không dùng giá trị finish reason của provider A để áp dụng nguyên trạng cho provider B.
- Có thông báo hoặc fallback phù hợp nếu response bị dừng mà chưa có câu trả lời cuối.
- Kiểm thử cả trường hợp checker trả `true` và `false`.

## Dùng checker cho các chính sách nào?

Checker phù hợp nhất với những điều kiện có thể xác định từ `ChatResponse`, ví dụ:

| Chính sách | Có phù hợp với checker? | Ghi chú |
|---|---|---|
| Response phải có tool call | Có | Chính là hành vi mặc định |
| Finish reason phải thuộc loại tool call | Có | Kiểm tra metadata của provider |
| Không tiếp tục với response rỗng | Có | Kiểm tra null và cấu trúc response |
| Bỏ qua tool call từ một trạng thái kết thúc bất thường | Có | Phụ thuộc metadata provider |
| Chỉ cho phép user thuộc tenant X | Không nên | Checker không nhận principal hoặc context request |
| Yêu cầu người dùng xác nhận trước khi ghi dữ liệu | Không | Dùng cơ chế Tool Call Confirmation hoặc workflow xác nhận |
| Giới hạn tối đa N vòng cho từng request | Không trực tiếp | Checker không nhận iteration count hoặc request context |
| Kiểm tra quyền truy cập bản ghi | Không | Thực hiện trong callback hoặc service nghiệp vụ |

Checker nhận `ChatResponse`, không nhận trực tiếp `ChatClientRequest`, `ToolContext`, danh tính người dùng hoặc bộ đếm iteration. Vì vậy, không nên dùng nó làm điểm duy nhất để kiểm tra quyền hoặc chính sách phụ thuộc vào request.
Checker trả về một boolean cho toàn bộ response. Nếu một response chứa nhiều tool call, checker không chọn riêng từng call; khi được chấp nhận, danh sách call sẽ được chuyển cho `ToolCallingManager` xử lý theo chính sách của manager.

### Checker không thay thế phân quyền

Một checker trả về `true` chỉ có nghĩa response đủ điều kiện để vòng tool calling tiếp tục. Nó không chứng minh người dùng có quyền thực thi tool hoặc truy cập tài nguyên.

Ví dụ, model yêu cầu gọi `getCustomerInfo` với `customerId=C-1024`. Checker có thể chấp nhận response vì nó có tool call hợp lệ. Nhưng callback vẫn phải lấy tenant/user từ ngữ cảnh đáng tin cậy và yêu cầu service kiểm tra quyền trước khi truy vấn.

Không đưa kiểm tra quyền vào checker rồi bỏ qua ở service. Callback có thể được gọi từ đường khác, và chính sách bảo mật phải được áp dụng tại nơi thực thi nghiệp vụ.

### Checker không phải cơ chế xác nhận thao tác

Nếu tool có tác động như hoàn tiền, xóa dữ liệu hoặc gửi giao dịch, trả về `true` từ checker không đồng nghĩa người dùng đã đồng ý. Checker không có giao diện để hỏi người dùng và không giữ trạng thái phê duyệt.

Với Spring AI 2.1.0, Tool Call Confirmation cho phép `ToolCallingManager` tạm dừng trước khi thực thi tool cần xác nhận, trả các call đang chờ quyết định về ứng dụng, rồi tiếp tục sau khi người dùng cho phép hoặc từ chối. Hãy dùng cơ chế này cho approval; checker chỉ xử lý điều kiện tiếp tục dựa trên response.

## Giới hạn vòng lặp và trạng thái theo request

Một yêu cầu có thể phát sinh nhiều lần gọi model và nhiều tool call iteration. Checker có thể ngăn một response kích hoạt vòng tiếp theo, nhưng bản thân interface chỉ nhận một `ChatResponse`. Nó không nhận số vòng hiện tại hoặc ngân sách của request.

Không nên đặt biến đếm mutable trong checker singleton như sau:

~~~java
@Component
public class CountingChecker implements ToolExecutionEligibilityChecker {

    private int iteration;

    @Override
    public boolean isToolCallResponse(ChatResponse response) {
        iteration++;
        return response != null && response.hasToolCalls() && iteration < 5;
    }
}
~~~

Bean singleton có thể được nhiều request sử dụng đồng thời. Bộ đếm của request A có thể ảnh hưởng request B, dẫn đến dừng sai hoặc tiếp tục quá mức. Nếu cần giới hạn số vòng theo request, hãy chọn một trong các cách sau:

- Dùng vòng lặp do ứng dụng điều khiển với bộ đếm cục bộ cho từng request.
- Tạo advisor tùy chỉnh có trạng thái được khởi tạo và kết thúc theo vòng đời request.
- Dùng hook của `ToolCallingAdvisor` để quan sát từng iteration và quản lý dữ liệu theo request, bảo đảm không chia sẻ mutable state giữa các request.
- Áp dụng giới hạn ở lớp orchestration/service nếu đó là ngân sách nghiệp vụ như số lần gọi model, thời gian hoặc chi phí.

Checker có thể là stateless lambda kiểm tra response metadata. Đây là thiết kế đơn giản, dễ kiểm thử và an toàn hơn trong môi trường nhiều request đồng thời.

## Tương tác với ToolCallingAdvisor và lịch sử hội thoại

Khi checker cho phép tiếp tục, `ToolCallingAdvisor` chuyển tool call đến `ToolCallingManager`, thêm tool result vào lịch sử và gửi lịch sử đó cho model ở iteration tiếp theo. Mặc định, advisor quản lý lịch sử hội thoại nội bộ trong vòng lặp.

Nếu checker trả về false, không có tool result mới được thêm từ response bị từ chối. Vì thế, ứng dụng cần hiểu rằng response đó không tương đương một vòng gọi tool đã hoàn tất.

Checker cũng không thay đổi thứ tự advisor. Nếu cần advisor khác quan sát từng iteration, hãy đặt advisor theo thứ tự phù hợp trong chain hoặc sử dụng hook của `ToolCallingAdvisor`. Nếu muốn quản lý toàn bộ lịch sử và thực thi thủ công, có thể gọi `ChatModel` trực tiếp và tự điều phối bằng `ToolCallingManager`; khi đó ứng dụng tự quyết định điều kiện tiếp tục của vòng lặp.

## Khác biệt API giữa Spring AI 1.x và 2.x

Tên và vị trí mở rộng thay đổi khi Spring AI chuyển vòng lặp tool calling từ từng `ChatModel` sang `ToolCallingAdvisor`.

| Phiên bản | API | Nơi áp dụng | Trạng thái |
|---|---|---|---|
| Spring AI 1.x | `ToolExecutionEligibilityPredicate` | Cơ chế thực thi tool nội bộ của ChatModel | API cũ |
| Spring AI 2.0 | `ToolExecutionEligibilityChecker` | `ToolCallingAdvisor.Builder` | API mới |
| Spring AI 2.1 | `ToolExecutionEligibilityChecker` | `ToolCallingAdvisor.Builder` | Dùng cho advisor-controlled loop |

Trong 1.x, predicate có thể nhận cả `ChatOptions` và `ChatResponse`, thường kiểm tra `internalToolExecutionEnabled` cùng việc response có tool call hay không. Spring AI 2.0 deprecated `ToolExecutionEligibilityPredicate` và loại bỏ cờ `internalToolExecutionEnabled`; Spring AI 2.1 loại bỏ `ToolExecutionEligibilityPredicate` cùng `DefaultToolExecutionEligibilityPredicate`.

Thay vào đó, dùng `ToolExecutionEligibilityChecker` trong `ToolCallingAdvisor`. Checker mới chỉ dựa trên `ChatResponse`, vì vậy những chính sách từng phụ thuộc vào `ChatOptions` cần được chuyển sang lớp advisor hoặc orchestration phù hợp.

Không nhầm `ToolExecutionEligibilityChecker` với `ToolExecutionEligibilityPredicate` cũ. Dù mục đích tương tự, chữ ký và vị trí tích hợp khác nhau.

## Kiểm thử checker

Kiểm thử nên tập trung vào các điều kiện mà checker chịu trách nhiệm. Không cần gọi model thật để kiểm tra một lambda đơn giản.

Các trường hợp cơ bản:

- Response là null: trả false.
- Response không có tool call: trả false.
- Response có tool call và finish reason phù hợp: trả true.
- Response có tool call nhưng finish reason không phù hợp: trả false.
- Metadata thiếu finish reason: xử lý theo chính sách đã chọn, thường là false nếu cần điều kiện nghiêm ngặt.

Ví dụ kiểm thử bằng Mockito (tên getter metadata có thể khác theo loại response/provider và phiên bản đang dùng):

~~~java
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.model.ChatResponse;

@Test
void shouldRejectResponseWithoutToolCalls() {
    ChatResponse response = mock(ChatResponse.class);
    when(response.hasToolCalls()).thenReturn(false);

    assertThat(checker.isToolCallResponse(response)).isFalse();
}

@Test
void shouldAcceptToolCallWithExpectedFinishReason() {
    ChatResponse response = mock(ChatResponse.class);
    ChatResponseMetadata metadata = mock(ChatResponseMetadata.class);

    when(response.hasToolCalls()).thenReturn(true);
    when(response.getMetadata()).thenReturn(metadata);
    when(metadata.getFinishReason()).thenReturn("tool_calls");

    assertThat(checker.isToolCallResponse(response)).isTrue();
}
~~~

Với checker nghiêm ngặt, cần bổ sung test cho finish reason không khớp và metadata null nếu API cho phép. Nếu interface đánh dấu response nullable, test trực tiếp trường hợp null:

~~~java
assertThat(checker.isToolCallResponse(null)).isFalse();
~~~

Ngoài unit test, nên có integration test với model giả hoặc ChatModel stub để xác minh vòng lặp thực tế:

1. Model trả response có tool call và metadata hợp lệ.
2. Checker cho phép tiếp tục.
3. Tool được gọi đúng số lần.
4. Tool result được đưa vào lịch sử.
5. Model nhận lượt tiếp theo và trả câu trả lời cuối.
6. Với metadata không hợp lệ, checker dừng và callback không được thực thi.

Nếu ứng dụng hỗ trợ nhiều provider, chạy bộ test metadata riêng cho từng provider. Một checker dựa trên finish reason của OpenAI có thể từ chối response hợp lệ từ provider khác nếu provider đó dùng giá trị khác.

## Những lỗi thường gặp

- **Bỏ qua hasToolCalls():** chỉ kiểm tra finish reason có thể cho phép response không chứa tool call đi vào vòng thực thi.
- **Dùng finish reason cố định cho mọi provider:** các provider có thể dùng giá trị hoặc metadata khác nhau. Xác minh response thực tế.
- **Nhầm checker với quyền truy cập:** checker chỉ quyết định response có kích hoạt vòng tiếp theo; service vẫn phải kiểm tra quyền.
- **Dùng checker để yêu cầu người dùng xác nhận:** checker không tương tác với người dùng. Dùng Tool Call Confirmation hoặc workflow riêng.
- **Dùng bộ đếm singleton để giới hạn iteration:** request đồng thời có thể chia sẻ trạng thái. Dùng trạng thái theo request hoặc vòng lặp do ứng dụng điều khiển.
- **Cho rằng checker false có nghĩa tool call đã thất bại an toàn:** callback chưa được thực thi theo vòng lặp đó, nhưng response có thể vẫn chứa tool call. Ứng dụng phải xử lý kết quả dừng phù hợp.
- **Dùng API Predicate cũ trong Spring AI 2.x:** chuyển sang checker gắn với ToolCallingAdvisor.
- **Tạo nhiều ToolCallingAdvisor trong cùng chain:** Spring AI yêu cầu một advisor quản lý tool lifecycle. Dùng checker trên advisor hiện có thay vì thêm advisor thứ hai.

## Checklist trước khi tùy chỉnh điều kiện tiếp tục

- [ ] Đã xác định phiên bản Spring AI và API checker tương ứng.
- [ ] Checker luôn xử lý null và kiểm tra `hasToolCalls()`.
- [ ] Finish reason hoặc metadata bổ sung đã được xác minh với provider đang dùng.
- [ ] Checker được gắn vào đúng `ToolCallingAdvisor.Builder` hoặc đăng ký thành bean.
- [ ] Không tạo nhiều tool advisor trong cùng advisor chain.
- [ ] Không dùng checker làm cơ chế phân quyền hoặc xác nhận thao tác.
- [ ] Không lưu bộ đếm request trong singleton checker.
- [ ] Có test cho response hợp lệ, không có tool call và finish reason không khớp.
- [ ] Có integration test xác minh callback chỉ chạy khi checker chấp nhận.
- [ ] Có fallback phù hợp khi vòng lặp dừng trên response chứa tool call.

## Ghi nhớ khi thiết kế

`ToolExecutionEligibilityChecker` là điểm mở rộng để quyết định một `ChatResponse` có kích hoạt iteration tool calling tiếp theo hay không. Mặc định, checker chấp nhận response khác null có chứa tool call. Khi cần, có thể bổ sung điều kiện dựa trên finish reason hoặc metadata của provider thông qua `ToolCallingAdvisor.Builder` hoặc Spring bean.

Hãy giữ `hasToolCalls()` làm điều kiện nền, kiểm tra metadata theo đúng provider và giữ checker stateless. Checker chỉ kiểm soát việc tiếp tục vòng lặp; phân quyền vẫn thuộc callback/service, xác nhận thuộc workflow approval, còn giới hạn ngân sách theo request cần được quản lý ở lớp orchestration có trạng thái riêng cho từng request.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 Upgrade Notes — ToolExecutionEligibilityChecker](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Spring AI 2.1.0 Reference — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

