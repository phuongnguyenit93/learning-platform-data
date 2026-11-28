# Phân biệt lịch sử nội bộ của vòng lặp với bộ nhớ giữa nhiều lượt

Khi mô hình gọi nhiều tool trong cùng một yêu cầu, Spring AI phải giữ các message đã trao đổi để gửi kết quả tool trở lại mô hình ở vòng tiếp theo. Đó là **lịch sử nội bộ của vòng tool calling**. Khi người dùng gửi một yêu cầu mới sau khi lượt trước đã kết thúc, ứng dụng cần tải lại ngữ cảnh của cuộc trò chuyện. Đó là **bộ nhớ giữa nhiều lượt**.

Hai cơ chế cùng làm việc với message, nhưng có phạm vi và trách nhiệm khác nhau:

- `ToolCallingAdvisor` giữ lịch sử cần thiết để hoàn tất một lượt gọi, gồm các tool call và tool response trong lượt đó.
- Session Memory lưu các sự kiện của cuộc trò chuyện qua nhiều lượt, khôi phục phần lịch sử phù hợp cho request tiếp theo và quản lý việc thu gọn ngữ cảnh.

`ToolExecutionResult.conversationHistory()` là dữ liệu để tiếp tục vòng hiện tại. Bản thân nó không phải kho lưu trữ và không làm cho request kế tiếp tự nhớ được cuộc trò chuyện trước đó.

## 1. Phân biệt round, turn và session

Ba khái niệm giúp xác định message đang được giữ ở phạm vi nào:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Model round | Một lần gửi prompt đến mô hình và nhận response | Mô hình yêu cầu gọi `lookup_order` |
| Turn | Một message của người dùng và mọi hoạt động cho đến message người dùng tiếp theo | Câu hỏi, các tool call, tool result và câu trả lời cuối |
| Session | Danh tính của một cuộc trò chuyện liên tục qua nhiều turn | Cuộc trò chuyện hỗ trợ đơn hàng của một người dùng |

Một turn có thể gồm nhiều model round. Ví dụ:

1. Người dùng hỏi tổng tiền đơn hàng.
2. Mô hình yêu cầu gọi `lookup_order`.
3. Ứng dụng thực thi tool và trả kết quả.
4. Mô hình yêu cầu gọi `calculate_total`.
5. Ứng dụng thực thi tool và trả kết quả.
6. Mô hình tổng hợp câu trả lời cuối.

Toàn bộ sáu bước thuộc một turn, dù mô hình đã được gọi nhiều lần. Khi người dùng hỏi tiếp ở turn sau, session memory cung cấp ngữ cảnh của các turn trước.

~~~mermaid
flowchart TD
    S[Session: cuộc trò chuyện] --> T1[Turn 1: câu hỏi đầu tiên]
    T1 --> R1[Round 1: model yêu cầu tool A]
    R1 --> X1[Tool A chạy và trả kết quả]
    X1 --> R2[Round 2: model yêu cầu tool B]
    R2 --> X2[Tool B chạy và trả kết quả]
    X2 --> R3[Round 3: model trả lời cuối]
    R3 --> T2[Turn 2: người dùng hỏi tiếp]
    T2 --> M[Session memory tải active view]
    M --> R4[Round đầu của turn 2]
~~~

## 2. Lịch sử nội bộ của ToolCallingAdvisor

Trong Spring AI 2.x, `ChatClient` tự đăng ký `ToolCallingAdvisor` để điều phối vòng gọi tool. Khi response của mô hình chứa tool call, advisor giao các call cho `ToolCallingManager`, nhận kết quả, thêm tool response vào conversation history rồi gửi lịch sử mới cho mô hình.

Luồng mặc định:

1. Gửi prompt cùng tool definitions đến mô hình.
2. Nhận `ChatResponse`.
3. Nếu response có tool call, thực thi các callback tương ứng.
4. Nối assistant message chứa tool call và tool response vào lịch sử của vòng.
5. Gửi lịch sử đã cập nhật về mô hình.
6. Lặp lại cho đến khi mô hình trả response không còn tool call.

Lịch sử này bảo đảm mô hình nhìn thấy những gì đã xảy ra trong lượt hiện tại. Nếu mô hình vừa gọi `lookup_order`, nó cần thấy tool result của `lookup_order` trước khi quyết định gọi tool khác hoặc trả lời.

### ToolExecutionResult.conversationHistory()

Khi tự gọi `ToolCallingManager`, kết quả thực thi được biểu diễn bằng `ToolExecutionResult`:

~~~java
ToolExecutionResult execution =
    toolCallingManager.executeToolCalls(prompt, chatResponse);

List<Message> history = execution.conversationHistory();

// Dùng lịch sử mới để tạo prompt của model round kế tiếp.
Prompt nextPrompt = new Prompt(history, chatOptions);
ChatResponse nextResponse = chatModel.call(nextPrompt);
~~~

`conversationHistory()` trả về danh sách message đã trao đổi trong conversation được đưa vào lần thực thi, bao gồm kết quả tool. Ứng dụng dùng danh sách này để tiếp tục cùng vòng. Nếu ứng dụng gọi `ChatModel` trực tiếp và bỏ danh sách này, mô hình ở round sau có thể không còn thấy tool call hoặc tool result vừa xảy ra.

`ToolCallingAdvisor` duy trì lịch sử nội bộ cho vòng hiện tại theo mặc định. Khi vòng kết thúc, lịch sử nội bộ không tự trở thành bộ nhớ lâu dài. Một request `ChatClient` mới không tự có lịch sử của request trước nếu ứng dụng không cấu hình memory/session.

## 3. Bộ nhớ giữa nhiều lượt giải quyết việc gì?

LLM không tự lưu trạng thái giữa các request. Khi một turn đã hoàn tất, request tiếp theo cần một thành phần:

- Xác định cuộc trò chuyện thuộc session nào.
- Đọc lịch sử đã lưu.
- Chọn phần lịch sử phù hợp với context window.
- Đưa phần đó vào prompt mới.
- Ghi lại user message, assistant reply và những tool message cần giữ.
- Quản lý lịch sử dài bằng window hoặc compaction.

Trong Spring AI 2.1.0, **Session Memory** là cơ chế được khuyến nghị cho việc này. Session giữ một append-only event log; các advisor đọc active view của log để tạo prompt và ghi các message phát sinh trong lượt.

`ChatMemory`, `MessageWindowChatMemory`, `ChatMemoryRepository` và `MessageChatMemoryAdvisor` đã deprecated từ Spring AI 2.1.0, dự kiến bị loại bỏ ở 3.0.0 để chuyển sang Session Memory. Các dự án cũ vẫn có thể gặp những API này; phần sau sẽ giải thích cách chúng hoạt động và điểm khác biệt.

## 4. SessionAdvisors trong ChatClient

`SessionAdvisors` kết hợp hai advisor có phạm vi khác nhau:

| Advisor | Vị trí | Trách nhiệm |
| --- | --- | --- |
| `SessionMemoryAdvisor` | Bên trong tool-calling loop, chạy ở mỗi model round | Đọc active view, thêm context vào prompt và ghi message của round |
| `SessionTurnAdvisor` | Bên ngoài tool-calling loop, chạy một lần cho mỗi `ChatClient` call | Quản lý turn, xử lý kết quả khi loop kết thúc không có model round và chạy compaction |

Order mặc định của hai advisor lần lượt là `HIGHEST_PRECEDENCE + 1000` và `HIGHEST_PRECEDENCE + 200`. `ToolCallingAdvisor` mặc định ở `HIGHEST_PRECEDENCE + 300`. Vì vậy memory advisor chạy bên trong loop, còn turn advisor bao quanh toàn bộ loop.

### Cấu hình Session Memory

Với Spring Boot và JDBC, thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-model-session-jdbc</artifactId>
</dependency>
~~~

Khi có `DataSource`, auto-configuration tạo `JdbcSessionRepository` và `SessionService`. Có thể cấu hình `ChatClient`:

~~~java
@Bean
ChatClient chatClient(
        ChatModel chatModel,
        SessionService sessionService) {

    return ChatClient.builder(chatModel)
        .defaultAdvisors(
            SessionAdvisors.builder(sessionService)
                .compaction(
                    new TurnCountTrigger(20),
                    WindowCompactionStrategy.builder()
                        .lastTurns(10)
                        .build()
                )
                .build()
        )
        .build();
}
~~~

Mỗi request phải chỉ rõ session:

~~~java
String answer = chatClient.prompt()
    .user("Đơn hàng ORD-100 của tôi đang ở trạng thái nào?")
    .advisors(SessionAdvisors.session(sessionId))
    .call()
    .content();
~~~

Session chưa tồn tại sẽ được tạo ở lần sử dụng đầu tiên. Không có session mặc định. Việc bắt buộc truyền ID giúp tránh vô tình gộp lịch sử của nhiều người dùng vào cùng một cuộc trò chuyện.

### Điều gì xảy ra trong từng round?

`SessionMemoryAdvisor` thực hiện các bước:

1. Lấy session ID từ advisor context.
2. Đọc active view của session.
3. Kết hợp lịch sử còn thiếu vào prompt hiện tại, tránh thêm trùng những message mà tool loop đã mang theo.
4. Ghi trailing user message hoặc tool result của request.
5. Sau response của mô hình, ghi assistant message. Assistant message có tool call luôn được lưu để giữ cấu trúc hội thoại.

`SessionTurnAdvisor` chạy một lần quanh `ChatClient` call. Sau khi loop kết thúc, nó ghi các tool result của trường hợp loop không gọi mô hình thêm, ví dụ tool có `returnDirect` hoặc lượt bị dừng do giới hạn tool call; sau đó chạy compaction nếu trigger đã đạt.

Do `SessionMemoryAdvisor` nằm trong loop, `DefaultChatClient` tự tắt internal conversation history của `ToolCallingAdvisor` để tránh ghi cùng một message hai lần. Nếu tự tạo `ToolCallingAdvisor` và `SessionMemoryAdvisor`, phải gọi `disableInternalConversationHistory()` trên builder của tool advisor.

## 5. Một turn được lưu trong session như thế nào?

Một turn có thể có nhiều message:

~~~text
USER
  "Tổng tiền đơn hàng ORD-100 là bao nhiêu?"

ASSISTANT
  tool call: lookup_order(orderId="ORD-100")

TOOL
  lookup_order -> {subtotal: 1000000, discount: 100000}

ASSISTANT
  tool call: calculate_total(subtotal=1000000, discount=100000)

TOOL
  calculate_total -> {total: 900000}

ASSISTANT
  "Tổng tiền đơn hàng là 900.000 đồng."
~~~

Các message này thuộc cùng một turn. Khi người dùng hỏi tiếp:

~~~text
USER
  "Nếu áp dụng thêm voucher 50.000 đồng thì sao?"
~~~

Session memory đọc active view, gồm những turn trước còn trong phạm vi, để mô hình hiểu "thêm voucher" đang nói về đơn hàng nào. Tool loop của turn mới lại có lịch sử riêng cho các round của turn mới.

Session event log cũng có thể chứa event nghiệp vụ do ứng dụng định nghĩa. Chỉ event loại `MESSAGE` tham gia vào việc tạo prompt và compaction; event tiến độ hoặc trạng thái khác vẫn nằm trong log nhưng không tự trở thành nội dung hội thoại.

## 6. Quản lý session ID và quyền truy cập

Session ID là khóa phân vùng lịch sử. Ai có thể chỉ định hoặc đọc một ID thì có thể ảnh hưởng đến cuộc trò chuyện được gắn với ID đó. Hãy tạo hoặc phân giải ID ở server từ danh tính đã xác thực:

~~~java
String sessionId = conversationRegistry.requireOwnedSession(
    authenticatedPrincipal,
    requestedConversationId
);

String answer = chatClient.prompt()
    .user(question)
    .advisors(SessionAdvisors.session(sessionId))
    .call()
    .content();
~~~

`conversationRegistry` là thành phần ứng dụng kiểm tra quyền sở hữu. Không lấy tenant ID, user ID hoặc quyền truy cập từ lời nhắc hay tool arguments do mô hình sinh ra.

Các nguyên tắc cần giữ:

- Mỗi người dùng và mỗi cuộc trò chuyện độc lập có session ID riêng.
- Xác minh quyền sở hữu session trước khi đọc, ghi, liệt kê hoặc xóa.
- Không dùng một ID cố định như `default` cho mọi request.
- Không xem session ID khó đoán là cơ chế authorization.
- Đặt thời hạn lưu trữ và quy trình xóa theo chính sách dữ liệu của ứng dụng.

Session có metadata để lưu thuộc tính như principal, tên agent hoặc phiên bản agent. Metadata hỗ trợ tra cứu và quản lý session; nó không thay thế kiểm tra quyền trong endpoint/service.

## 7. Event log, active view và compaction

Session Memory không chỉ lưu một danh sách message phẳng. Nó lưu các `SessionEvent` theo thứ tự append:

- `MESSAGE`: một message của Spring AI như `UserMessage`, `AssistantMessage`, `ToolResponseMessage`.
- `COMPACTION`: ranh giới xác định active view sau khi lịch sử được thu gọn.
- Event tùy chỉnh: dữ liệu tiến độ hoặc trạng thái do ứng dụng ghi, không tham gia prompt nếu không được chuyển thành message.

Có hai cách đọc khác nhau:

~~~java
// Các message trong active view mà mô hình được phép thấy.
List<Message> promptHistory =
    sessionService.getActiveMessages(sessionId);

// Toàn bộ event log, kể cả event đã được compaction che khỏi active view.
List<SessionEvent> auditLog =
    sessionService.getEvents(sessionId, EventFilter.all());
~~~

`EventFilter.active()` đọc active view. `EventFilter.all()` đọc toàn bộ log. Compaction không xóa hoặc sửa event cũ; nó thêm boundary để xác định phần lịch sử nào còn được đưa vào prompt. Vì vậy có thể giữ lịch sử kiểm toán trong log nhưng chỉ đưa một cửa sổ ngắn hơn cho mô hình.

### Window phải giữ trọn turn

Không nên cắt lịch sử giữa assistant tool call và tool result. Một provider có thể từ chối prompt nếu assistant message chứa tool call không được theo sau bởi các tool response tương ứng.

Session event filtering mở rộng cửa sổ `lastN` về đầu turn nếu điểm cắt rơi vào giữa turn. Nhờ vậy cửa sổ không bắt đầu bằng một tool result thiếu tool call hoặc một assistant reply thiếu câu hỏi mở đầu.

Ví dụ:

~~~text
Log:
  U1 A1 U2 A2[tool call] T2[result] A2-final

Yêu cầu lastN(2):
  T2[result] A2-final

Active view sau khi mở rộng:
  U2 A2[tool call] T2[result] A2-final
~~~

### Compaction theo turn hoặc token

Ví dụ cấu hình đã dùng ở trên:

~~~java
.compaction(
    new TurnCountTrigger(20),
    WindowCompactionStrategy.builder()
        .lastTurns(10)
        .build()
)
~~~

Nghĩa là khi active view đạt ngưỡng 20 turn, chiến lược giữ 10 turn gần nhất. Có thể dùng `TokenCountTrigger` và `tokenBudget(...)` nếu muốn giới hạn theo số token ước tính thay vì số lượt.

Khi có summarizer, các turn cũ được tóm tắt thành một summary turn. Summary được thêm vào active view thông qua compaction boundary; log gốc vẫn giữ nguyên. Turn mới nhất luôn được giữ nguyên, kể cả khi riêng turn đó vượt cửa sổ, để không cắt một tool loop đang chạy.

## 8. EventFilter và MessageFilter

Hai filter có tác dụng ở hai thời điểm khác nhau:

| Filter | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| `EventFilter` | Khi đọc session | Chọn event nào được đưa vào active prompt view |
| `MessageFilter` | Khi ghi message | Quyết định message mới có được lưu hay không |

Ví dụ chỉ tải một cửa sổ nhỏ hơn cho một request:

~~~java
String answer = chatClient.prompt()
    .user("Tóm tắt ngắn gọn cuộc trò chuyện.")
    .advisors(a -> a
        .param(
            SessionMemoryAdvisor.SESSION_ID_CONTEXT_KEY,
            sessionId
        )
        .param(
            SessionMemoryAdvisor.EVENT_FILTER_CONTEXT_KEY,
            EventFilter.lastN(5)
        ))
    .call()
    .content();
~~~

`EventFilter` chỉ ẩn event khỏi lần đọc đó; event vẫn còn trong log. `MessageFilter` từ chối message thì message không được ghi.

Tool call và tool result luôn được lưu bởi `SessionMemoryAdvisor`, vì chỉ lưu một nửa cặp sẽ tạo history không hợp lệ. Nếu một `EventFilter` loại bỏ tool response nhưng vẫn giữ assistant tool call, advisor sẽ phát hiện cặp không đầy đủ và bỏ cặp đó khỏi prompt. Khi cần mô hình hiểu tool transcript, hãy giữ cả `TOOL` message type trong active view.

## 9. Xử lý returnDirect và tool loop kết thúc sớm

Khi một tool có `returnDirect = true`, `ToolCallingAdvisor` có thể kết thúc vòng mà không gọi mô hình thêm. Khi đó `SessionMemoryAdvisor` một mình không ghi được tool result cuối cùng vào session vì nó chạy ở từng model round; không có round tiếp theo để nó quan sát.

Đó là lý do nên cấu hình cả `SessionMemoryAdvisor` và `SessionTurnAdvisor` thông qua `SessionAdvisors`. `SessionTurnAdvisor` nhìn thấy kết quả cuối của toàn `ChatClient` call và ghi tool result của loop kết thúc sớm. Nó cũng xử lý kết quả khi tool-call limit bị vượt.

Điều này quan trọng khi turn tiếp theo cần biết tool trước đó đã trả dữ liệu gì. Nếu chỉ có loop history, kết quả direct chỉ phục vụ caller hiện tại và không tự xuất hiện trong session của request sau.

## 10. Dùng ChatMemory API cũ trong dự án hiện hữu

Trong các phiên bản trước, ứng dụng thường dùng `ChatMemory`, `MessageWindowChatMemory` và `MessageChatMemoryAdvisor`. Các API này đã deprecated từ Spring AI 2.1.0 để chuyển sang Session Memory.

Nếu đang duy trì ứng dụng cũ, vị trí của `MessageChatMemoryAdvisor` so với `ToolCallingAdvisor` quyết định những message nào được lưu:

| Vị trí | Hành vi |
| --- | --- |
| Ngoài loop, order mặc định `HIGHEST_PRECEDENCE + 200` | Đọc history một lần trước loop; ghi user message và assistant final sau loop; không thấy tool call/result trung gian |
| Trong loop, order lớn hơn `ToolCallingAdvisor` (ví dụ `+400`) | Chạy mỗi model round; có thể lưu tool call/result để dùng ở lượt sau |

Ví dụ advisor cũ ở ngoài loop:

~~~java
ChatClient client = ChatClient.builder(chatModel)
    .defaultAdvisors(
        MessageChatMemoryAdvisor.builder(chatMemory).build()
    )
    .build();
~~~

Đây là hành vi an toàn với repository chỉ lưu user/assistant message, nhưng tool transcript không được giữ trong memory.

Nếu đặt advisor cũ bên trong loop, repository phải serialize được `ToolResponseMessage` và assistant tool-call message. Khi đó internal history của `ToolCallingAdvisor` phải được tắt để tránh ghi trùng. `DefaultChatClient` tự phát hiện memory advisor bên trong loop và tắt internal history; nếu tự tạo `ToolCallingAdvisor`, hãy gọi `disableInternalConversationHistory()` trên builder.

Các repository cũ hỗ trợ đầy đủ tool message gồm `InMemoryChatMemoryRepository`, `RedisChatMemoryRepository` và `Neo4jChatMemoryRepository`. Không nên giả định mọi repository đều lưu được tool call và tool result. Với persistence JDBC và lịch sử tool đầy đủ, Session Memory cùng `JdbcSessionRepository` là hướng phù hợp.

Với dự án mới trên Spring AI 2.1.0, ưu tiên Session Memory. Nó lưu tool message dưới dạng event, giữ nguyên turn và có cơ chế compaction phù hợp cho hội thoại dài.

## 11. Khi tự điều phối bằng ChatModel

`SessionAdvisors` là tích hợp cho `ChatClient`. Nếu gọi `ChatModel` và `ToolCallingManager` trực tiếp, ứng dụng phải tự kết hợp hai phạm vi history:

1. Đọc active view của session khi bắt đầu turn mới.
2. Thêm `UserMessage` hiện tại vào prompt.
3. Giữ `ToolExecutionResult.conversationHistory()` làm lịch sử nội bộ để gọi mô hình ở round kế tiếp.
4. Ghi các message mới phát sinh trong turn vào session đúng một lần: assistant tool-call message, tool response và assistant final.
5. Ở turn sau, đọc lại active view từ session thay vì dựa vào một biến list còn nằm trong memory của process.

Ví dụ phần điều phối nội bộ:

~~~java
List<Message> history =
    new ArrayList<>(sessionService.getActiveMessages(sessionId));

history.add(new UserMessage(question));
Prompt prompt = new Prompt(history, chatOptions);
ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    ToolExecutionResult result =
        toolCallingManager.executeToolCalls(prompt, response);

    // Đây là lịch sử cho round kế tiếp của cùng turn.
    history = new ArrayList<>(result.conversationHistory());
    prompt = new Prompt(history, chatOptions);
    response = chatModel.call(prompt);
}
~~~

Đoạn mã minh họa vòng lặp; lớp điều phối phải ghi các message mới vào `SessionService` khi chúng phát sinh. Không ghi lặp toàn bộ `history` ở mỗi vòng. Cần giữ cặp assistant tool call và `ToolResponseMessage` tương ứng, rồi ghi assistant final khi mô hình kết thúc. Nếu `returnDirect` kết thúc loop, ứng dụng cũng phải lưu tool result được trả trực tiếp.

Ở mức API, `SessionService.appendMessage(sessionId, message)` thêm một message vào event log. Khi tự điều phối, gọi nó đúng một lần cho từng message mới: user message, assistant message có tool call, tool response và assistant final. Không append lại những message đã có trong active view từ trước khi turn bắt đầu.

`ToolCallingManager` không tự biết session ID, không tự tải lịch sử từ repository và không tự ghi message sang turn tiếp theo. Những trách nhiệm đó thuộc lớp điều phối của ứng dụng khi không dùng `ChatClient` cùng SessionAdvisors.

## 12. ToolContext không phải conversation memory

`ToolContext` truyền dữ liệu ứng dụng cho một lần gọi tool, ví dụ tenant ID, user ID hoặc request metadata. Nó không phải nơi lưu lịch sử hội thoại và không tự được mô hình nhìn thấy.

| Dữ liệu | Nơi phù hợp |
| --- | --- |
| Câu hỏi và câu trả lời của các turn trước | Session Memory |
| Assistant tool call và tool result của round hiện tại | Tool loop history và Session Memory nếu cần lưu qua turn |
| Tenant ID, user ID đã xác thực | `ToolContext` hoặc security context do ứng dụng tạo |
| Quyền được phép gọi tool | Authorization/service layer |
| Kết quả cần nhớ lâu dài như sở thích hoặc hồ sơ | Kho nghiệp vụ hoặc memory/retrieval phù hợp |

Không nhét toàn bộ conversation history vào `ToolContext` với kỳ vọng tool sẽ tự hiểu các turn trước. Tool nhận các tham số của chính nó và context do ứng dụng truyền rõ ràng; việc xây dựng prompt history thuộc advisor/orchestrator.

## 13. Persistence và triển khai nhiều instance

`InMemorySessionRepository` phù hợp cho test và demo. Dữ liệu mất khi process restart và không được chia sẻ giữa các instance.

`JdbcSessionRepository` lưu session metadata và event log trong database quan hệ. Spring AI 2.1.0 hỗ trợ PostgreSQL, MySQL, MariaDB, Microsoft SQL Server và H2. Có thể dùng starter `spring-ai-starter-model-session-jdbc` để Spring Boot cấu hình `SessionService` và repository.

Với nhiều instance ứng dụng:

- Dùng repository dùng chung thay vì in-memory store.
- Tạo session ID ổn định và kiểm tra quyền sở hữu trên mọi instance.
- Dùng TTL và job dọn session hết hạn theo yêu cầu lưu trữ.
- Không giữ history duy nhất trong field của singleton `ChatClient` hoặc service.
- Nếu cần kiểm toán, đọc toàn bộ event log; nếu cần prompt, đọc active view.

Session log có append idempotency theo event ID và hỗ trợ optimistic concurrency cho batch append/compaction. Tuy vậy, không nên chạy hai turn đồng thời trên cùng một session. Session memory yêu cầu ứng dụng serialize các call của một session; nếu hai call cùng session chạy song song, message có thể xen kẽ và làm sai thứ tự hội thoại.

## 14. Kiểm thử sự khác nhau giữa hai loại history

Thiết kế test theo từng phạm vi:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Một turn có hai tool round | Model round thứ hai nhận assistant tool call và tool result của round trước |
| Kết thúc turn | Internal loop history không được xem là persistence tự động |
| Turn mới cùng session ID | Prompt nhận được active history của turn trước |
| Turn mới với session ID khác | Không có message của session khác |
| Hai người dùng cùng lúc | Session ID và lịch sử không bị trộn |
| Tool `returnDirect` | Tool result cuối được `SessionTurnAdvisor` ghi vào session |
| Tool-call limit kết thúc loop | Kết quả một phần và thông tin giới hạn được lưu đúng theo session advisor |
| Compaction | Active view giữ trọn turn, không tách tool call khỏi tool response |
| Event filter loại tool messages | Advisor không gửi cặp tool message không đầy đủ cho model |
| Manual ChatModel loop | Ứng dụng ghi từng message mới đúng một lần và tải lại session ở turn sau |
| Repository restart | JDBC repository vẫn đọc được session và active view |
| Hai request đồng thời cùng session | Ứng dụng xếp hàng hoặc từ chối request thứ hai theo policy |

Nên mock `ChatModel` để trả response có tool call cố định, dùng fake `ToolCallback` để tạo tool result xác định và kiểm tra message history gửi vào từng round. Với Session Memory, kiểm tra cả `getEvents(sessionId, EventFilter.all())` và `getActiveMessages(sessionId)` để thấy sự khác biệt giữa log gốc và prompt view.

## 15. Lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mô hình quên kết quả tool ở round sau | Không đưa `ToolExecutionResult.conversationHistory()` vào prompt kế tiếp | Tiếp tục loop bằng history do manager trả về |
| Mô hình quên turn trước | Chỉ dùng internal tool loop, chưa cấu hình session memory | Dùng `SessionAdvisors` hoặc tự tải/lưu session |
| Tool result bị lặp trong prompt | Vừa bật internal loop history vừa ghi cùng message qua memory advisor | Dùng SessionAdvisors hoặc tắt internal history khi memory advisor nằm trong loop |
| Không thấy tool result ở turn tiếp theo | Chỉ dùng `SessionMemoryAdvisor` nhưng tool loop kết thúc bằng `returnDirect` | Đăng ký cả `SessionTurnAdvisor` thông qua `SessionAdvisors` |
| Provider từ chối prompt history | Assistant tool call không có tool response tương ứng | Giữ trọn cặp tool call/result; không cắt giữa turn |
| Lịch sử người dùng bị gộp | Dùng session ID cố định hoặc không kiểm tra quyền | Tạo session riêng theo user và conversation |
| Lịch sử mất khi deploy lại | Chỉ dùng `InMemorySessionRepository` | Dùng repository bền vững như JDBC |
| Token tăng liên tục | Không có event filter/window hoặc compaction | Đặt cửa sổ theo turn hoặc token budget |
| Message xen kẽ giữa hai request | Cho phép hai turn chạy đồng thời trên cùng session | Serialize request theo session ID |
| Manual loop có message trùng | Persist toàn bộ history ở mỗi iteration | Chỉ append phần message mới đúng một lần |

## Bài thực hành

Xây dựng assistant hỗ trợ đơn hàng với hai turn:

**Turn 1:** Người dùng hỏi trạng thái và tổng tiền đơn hàng `ORD-100`. Mô hình gọi `lookup_order`, sau đó gọi `calculate_total`, rồi trả lời.

**Turn 2:** Người dùng hỏi "Nếu dùng voucher 50.000 đồng thì tổng mới là bao nhiêu?". Mô hình cần hiểu câu hỏi đang nói về đơn hàng vừa tra cứu.

Hãy thực hiện:

1. Dùng `ToolCallingAdvisor` để giữ tool call và tool result trong các round của turn 1.
2. Dùng `SessionAdvisors` để lưu turn 1 vào session.
3. Gửi turn 2 với cùng session ID và xác minh active history được tải vào prompt.
4. Gửi một request khác với session ID riêng và xác minh không thấy dữ liệu của `ORD-100`.
5. Thêm một tool `returnDirect = true`; xác minh tool result vẫn được lưu sau khi loop kết thúc sớm.
6. Bật compaction theo số turn và xác minh active view không cắt giữa tool call và tool result.
7. Chạy hai request đồng thời trên cùng session; thiết kế cơ chế serialize và kiểm thử thứ tự.

Sau khi hoàn thành, hãy giải thích vì sao `ToolExecutionResult.conversationHistory()` không thay thế Session Memory, và vì sao một tool result cần được lưu vào session nếu turn sau còn phụ thuộc vào nó.

## Ghi nhớ

Lịch sử nội bộ của tool loop phục vụ các model round trong cùng một turn: nó giữ assistant tool call và tool response để mô hình tiếp tục đúng trình tự. Bộ nhớ giữa nhiều lượt phục vụ toàn bộ cuộc trò chuyện: nó lưu turn, khôi phục active view, quản lý session ID và thu gọn lịch sử khi cần. Trong Spring AI 2.1.0, nên dùng `SessionAdvisors` để kết hợp `SessionMemoryAdvisor` bên trong loop với `SessionTurnAdvisor` bên ngoài loop. Khi tự điều phối bằng `ChatModel`, ứng dụng phải tự tải, nối và lưu các message mới vào session.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — Session Memory](https://docs.spring.io/spring-ai/reference/api/session.html)
- [Spring AI 2.1.0 — ChatClient Integration](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)
- [Spring AI 2.1.0 — Session Concepts](https://docs.spring.io/spring-ai/reference/api/session/concepts.html)
- [Spring AI 2.1.0 — Event Filtering](https://docs.spring.io/spring-ai/reference/api/session/event-filter.html)
- [Spring AI 2.1.0 — Compaction](https://docs.spring.io/spring-ai/reference/api/session/compaction.html)
- [Spring AI 2.1.0 — JDBC Repository](https://docs.spring.io/spring-ai/reference/api/session/jdbc.html)
- [Spring AI 2.1.0 — Upgrading to 2.1.0](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
