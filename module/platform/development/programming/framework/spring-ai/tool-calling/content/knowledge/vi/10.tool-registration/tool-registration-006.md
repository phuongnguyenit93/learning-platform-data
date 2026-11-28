# Quy tắc kết hợp hoặc ghi đè giữa mặc định và cấu hình lúc gọi

Spring AI cho phép đăng ký công cụ ở nhiều cấp: cấu hình mặc định của `ChatClient`, cấu hình riêng cho một request và tùy chọn trực tiếp trên `ChatModel`. Các cấp này không có cùng quy tắc kết hợp. Nếu không phân biệt rõ, bạn có thể vô tình gửi thiếu công cụ cần thiết, làm một công cụ nhạy cảm xuất hiện ở quá nhiều request hoặc nghĩ rằng một công cụ cùng tên sẽ tự động thay thế công cụ khác.

Trong tài liệu Spring AI 2.1.0, các quy tắc chính là:

- Với `ChatClient`, `.tools(...)` ở thời điểm gọi được nối thêm vào `.defaultTools(...)` của client.
- Với `ChatModel` gọi trực tiếp, danh sách tool callback ở request options thay thế danh sách trong default options của model.
- Với `ToolContext`, context mặc định và context ở request được gộp; giá trị runtime thắng khi trùng khóa.

Một chi tiết phụ thuộc release line: tài liệu Spring AI 2.1.1-SNAPSHOT mô tả `.tools(...)` thay callback list nằm trong `.options(...)` khi cùng request cấu hình cả hai. Phần dưới ghi rõ phạm vi phiên bản này; hãy kiểm tra lại trước khi áp dụng cho một release khác.

Đây là quy tắc kết hợp danh sách và map. Nó không có nghĩa một tool cùng tên sẽ được thay thế theo kiểu ghi đè từng phần tử. Tên công cụ vẫn phải duy nhất trong tập công cụ cuối cùng.

## Phân biệt các tầng cấu hình

Trước khi chọn cách đăng ký, hãy xác định bạn đang dùng API nào và cấu hình được đặt ở đâu.

| Tầng | API thường gặp | Phạm vi |
|---|---|---|
| Mặc định của `ChatClient` | `ChatClient.builder(chatModel).defaultTools(...)` | Công cụ mặc định của các request tạo từ client đó. |
| Theo từng request `ChatClient` | `chatClient.prompt().tools(...)` | Bổ sung công cụ cho request hiện tại. |
| Options của request `ChatClient` | `chatClient.prompt().options(...)` với `ToolCallingChatOptions` | Tùy chọn tool callback nằm trong options của request; có quy tắc ưu tiên riêng khi đồng thời gọi `.tools(...)`. |
| Mặc định của `ChatModel` | `ToolCallingChatOptions` được đặt khi tạo model | Công cụ trong default options của instance model. |
| Theo từng request `ChatModel` | `Prompt` chứa `ToolCallingChatOptions` | Danh sách tool callback cho request trực tiếp tới model. |
| Context mặc định và runtime | `defaultToolContext(...)`, `toolContext(...)` | Dữ liệu phụ trợ chuyển vào tool khi thực thi, không phải danh sách công cụ. |

Đừng gộp các tầng này thành một khái niệm “default tools”. `ChatClient` còn có advisor điều phối vòng gọi công cụ; `ChatModel` là API thấp hơn và không tự thực thi tool call trong Spring AI 2.x.

## Quy tắc của ChatClient: runtime tools được nối thêm

Với `ChatClient`, `.defaultTools(...)` đăng ký tập công cụ dùng chung cho request được tạo từ client. `.tools(...)` bổ sung các công cụ chỉ cần trong một lần gọi.

```java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(accountTools, orderQueryTools)
        .build();

String answer = chatClient.prompt()
        .user("Tra cứu đơn hàng DH-100 và thông tin tài khoản của tôi")
        .tools(shippingTools)
        .call()
        .content();
```

Trong ví dụ, request có tập công cụ gồm:

- `accountTools` và `orderQueryTools` từ cấu hình mặc định.
- `shippingTools` được thêm riêng cho request hiện tại.

Request tiếp theo dùng cùng `chatClient` vẫn có hai nhóm mặc định, nhưng không tự động giữ `shippingTools` của lần gọi trước. Đây là cách tổ chức phù hợp khi một số công cụ luôn cần thiết còn các công cụ chuyên biệt chỉ phù hợp với một luồng nghiệp vụ.

`defaultTools(...)` và `tools(...)` nhận được nhiều loại đối tượng: instance có phương thức `@Tool`, `ToolCallback`, `ToolCallbackProvider`, hoặc mảng/collection của các loại này. Có thể kết hợp nhiều cách khai báo trong cùng một tập.

Một nguồn mặc định khác có thể nằm ở `ChatModel` bên dưới: model có thể đã được cấu hình `ToolCallingChatOptions.toolCallbacks(...)`. Khi `ChatClient` gửi danh sách tool ở cấp request, danh sách request-level này ghi đè callback list trong default options của `ChatModel`. Vì vậy, đừng giả định `ChatClient.defaultTools(...)` sẽ tự động hợp nhất thêm danh sách đã đặt trong `ChatModel` options. Hãy chọn một nơi quản lý danh mục tool hoặc tự hợp nhất danh sách mà request cần.

### Có thể dùng runtime tools để loại bỏ default tools không?

Không. Với `ChatClient` 2.1.0, `.tools(...)` là phép bổ sung, không phải phép thay thế `.defaultTools(...)`. Nếu client mặc định có `accountTools` và `orderQueryTools`, việc gọi `.tools(reportTool)` vẫn giữ hai nhóm mặc định và thêm `reportTool`.

Nếu một request phải có tập công cụ giới hạn, hãy thiết kế client hoặc luồng đăng ký phù hợp với tập đó. Các cách thường dùng:

- Tạo các `ChatClient` riêng theo nhóm quyền hoặc theo loại tác vụ, mỗi client có default tools phù hợp.
- Không đăng ký các công cụ cần lọc làm mặc định; chọn và truyền danh sách theo từng request.
- Tạo `ToolCallbackProvider` hoặc lớp chọn công cụ theo quyền đã xác thực trước khi gửi request.

Không cố “xóa” một công cụ mặc định bằng cách truyền một tool khác cùng tên. Trùng tên được xử lý như xung đột, không phải cơ chế thay thế an toàn.

## Lưu ý khi kết hợp options(...) và tools(...)

Một request có thể nhận `ChatOptions` qua `.options(...)`. Nếu options đó chứa `ToolCallingChatOptions.toolCallbacks(...)` và cùng request cũng gọi `.tools(...)`, không được mặc định rằng hai danh sách sẽ được nối lại. Tài liệu Spring AI 2.1.1-SNAPSHOT mô tả `.tools(...)` thay thế callback list nằm trong `.options(...)`. Vì chi tiết này gắn với release line cụ thể, hãy kiểm tra tài liệu/Javadoc đúng phiên bản đang khóa trước khi dựa vào nó.

Ví dụ cần tránh:

```java
ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(defaultCallbacks)
        .build();

chatClient.prompt()
        .user("Tìm thông tin đơn hàng")
        .options(options)
        .tools(shippingTool)
        .call()
        .content();
```

Trong trường hợp được mô tả ở tài liệu 2.1.1-SNAPSHOT, không nên giả định request có cả `defaultCallbacks` lẫn `shippingTool`. `.tools(shippingTool)` thay callback list trong options của request. Nếu muốn tự kiểm soát tập callback ở request này, hãy tạo một danh sách đầy đủ rồi truyền nó qua một đường cấu hình rõ ràng.

Ví dụ tạo danh sách hợp nhất tường minh:

```java
List<ToolCallback> requestTools = new ArrayList<>(defaultCallbacks);
requestTools.add(shippingTool);

ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(requestTools)
        .build();

chatClient.prompt()
        .user("Tìm thông tin đơn hàng và vận chuyển")
        .options(options)
        .call()
        .content();
```

Ở đây, code của ứng dụng tự quyết định tập công cụ cuối cùng. Tránh vừa truyền danh sách qua `.options(...)` vừa truyền một danh sách khác qua `.tools(...)` nếu không có lý do rõ ràng.

## Quy tắc của ChatModel: runtime options thay thế default options

Khi gọi `ChatModel` trực tiếp, công cụ được đặt trong `ToolCallingChatOptions.toolCallbacks(...)`. Nếu instance model đã có danh sách mặc định và request cũng cung cấp một danh sách, danh sách ở request thay thế danh sách mặc định hoàn toàn.

```java
ToolCallback[] defaultTools = {
        accountTool,
        orderQueryTool,
        shippingTool
};

ChatModel chatModel = OllamaChatModel.builder()
        .ollamaApi(ollamaApi)
        .options(ToolCallingChatOptions.builder()
                .toolCallbacks(defaultTools)
                .build())
        .build();

ToolCallingChatOptions runtimeOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(reportTool)
        .build();

ChatResponse response = chatModel.call(
        new Prompt("Tạo báo cáo đơn hàng", runtimeOptions)
);
```

Trong ví dụ, model nhận `reportTool`; ba công cụ mặc định không được nối thêm tự động. Nếu muốn giữ các công cụ mặc định và bổ sung một công cụ, ứng dụng phải hợp nhất danh sách trước khi tạo runtime options.

```java
List<ToolCallback> combined = new ArrayList<>(Arrays.asList(defaultTools));
combined.add(reportTool);

ToolCallingChatOptions runtimeOptions = ToolCallingChatOptions.builder()
        .toolCallbacks(combined)
        .build();
```

Quy tắc này áp dụng cho đường gọi `ChatModel` trực tiếp. Không lấy quy tắc append của `ChatClient` để suy luận rằng `ChatModel` cũng tự hợp nhất hai danh sách.

### ChatModel trực tiếp không tự chạy vòng tool calling

Trong Spring AI 2.x, `ChatModel.call(prompt)` và `ChatModel.stream(prompt)` gửi định nghĩa công cụ cho mô hình và trả về response chứa tool call nếu mô hình yêu cầu. Chúng không tự thực thi callback rồi gọi lại mô hình. Caller phải tự điều phối vòng lặp, hoặc dùng `ChatClient` với `ToolCallingAdvisor` nếu muốn framework quản lý chu trình đó.

Vì vậy, khi dùng `ChatModel` trực tiếp, trách nhiệm của ứng dụng bao gồm:

1. Tạo danh sách callback hoàn chỉnh cho request.
2. Gửi `Prompt` cùng tool options.
3. Kiểm tra response có tool call hay không.
4. Gọi `ToolCallingManager` để thực thi callback và tạo conversation history mới.
5. Gửi history cùng danh sách options cần thiết cho lượt tiếp theo.
6. Dừng khi mô hình trả câu trả lời cuối hoặc khi đạt giới hạn vòng lặp.

Không nhầm việc “đã gửi tool definition cho model” với việc “callback đã được thực thi”.

## ToolContext: map mặc định được gộp với map runtime

`ToolContext` là dữ liệu phụ trợ đi vào callback khi thực thi. Nó không phải danh sách công cụ và cũng không được gửi cho mô hình như JSON arguments.

`ChatClient.Builder` có `defaultToolContext(...)`; request có `toolContext(...)`. Nếu cùng một khóa xuất hiện ở cả hai map, giá trị runtime được ưu tiên.

```java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultToolContext(Map.of(
                "application", "support-portal",
                "locale", "vi-VN"
        ))
        .defaultTools(orderQueryTool)
        .build();

String answer = chatClient.prompt()
        .user("Tra cứu đơn DH-100")
        .toolContext(Map.of(
                "requestId", requestId,
                "locale", "en-US"
        ))
        .call()
        .content();
```

Context cuối cùng có `application=support-portal`, `requestId` của request hiện tại và `locale=en-US` vì giá trị runtime ghi đè `vi-VN`.

Không đặt `userId`, `tenantId` hoặc quyền của người dùng vào context mặc định của một client dùng chung cho nhiều người. Hãy tạo các giá trị định danh từ security context đã xác thực ở từng request và truyền chúng qua `toolContext(...)`. Nếu quên truyền runtime key, một giá trị mặc định cũ có thể bị dùng nhầm trong phạm vi không mong muốn.

## Trùng tên không phải là ghi đè

Tên công cụ là khóa mà mô hình dùng để yêu cầu thực thi. Trong tập công cụ cuối cùng của một request, mỗi tên phải duy nhất.

Với `ChatClient`, danh sách từ default và runtime được hợp nhất rồi kiểm tra. Nếu hai callback có cùng tên, request thất bại với `IllegalStateException`. Spring AI không tự chọn callback runtime để thay callback mặc định cùng tên.

Với đường `ChatModel` trực tiếp hoặc vòng lặp tự viết bằng danh sách callback ghép thủ công, bước kiểm tra danh sách hợp nhất của `ChatClient` không tự chạy. Bộ phân giải theo tên có thể chọn callback đầu tiên trong danh sách mà không báo lỗi. Điều này đặc biệt nguy hiểm khi trộn callback nội bộ với công cụ từ MCP hoặc nguồn từ xa.

Hãy xử lý xung đột bằng cách:

- Đặt tên riêng theo miền nghiệp vụ, ví dụ `orders_getStatus` và `shipping_getTracking`.
- Dùng prefix cho các công cụ đến từ server hoặc provider khác nhau.
- Lọc bỏ callback không cần thiết trước khi đăng ký.
- Kiểm tra tên duy nhất trên danh sách cuối cùng trước khi gửi tới `ChatModel` hoặc custom loop.

Không dựa vào thứ tự đăng ký để thay thế callback cùng tên. Thứ tự không phải một chính sách override đáng tin cậy.

## ToolCallbackResolver và resolution fallback

Spring AI có `ToolCallbackResolver` để tìm callback theo tên. Trong cấu hình mặc định, `StaticToolCallbackResolver` được tạo từ các bean `ToolCallback` và các `ToolCallbackProvider` phù hợp trong application context. Việc một callback tồn tại trong resolver không đồng nghĩa nó luôn được gửi cho mô hình trong mọi request.

Mặc định, `spring.ai.tools.resolution.fallback.enabled=false`: chỉ callback gắn với request mới được thực thi. Nếu bật fallback, một tool call có tên không nằm trong callback list của request vẫn có thể được tìm trong resolver và thực thi.

```properties
# Mặc định: chỉ thực thi các callback được gắn vào request
spring.ai.tools.resolution.fallback.enabled=false
```

Không bật fallback chỉ để tiện tra cứu công cụ theo tên. Khi bật, mọi callback mà resolver có thể tìm thấy có thể trở thành khả năng thực thi dù request không chủ động đính kèm chúng, bao gồm cả công cụ ghi hoặc công cụ có mức rủi ro cao. Nếu cần cơ chế này, hãy kiểm soát resolver, giới hạn danh mục callback mà nó trả về và tiếp tục kiểm tra quyền trong từng callback/service.

## Chọn công cụ mặc định theo quyền và mức rủi ro

Default tools tiện lợi nhưng làm tăng phạm vi công cụ luôn có sẵn cho các request của client. Hãy phân loại công cụ trước khi đăng ký:

| Nhóm | Cách đăng ký thường phù hợp | Lý do |
|---|---|---|
| Công cụ đọc ít rủi ro, dùng thường xuyên | Có thể đặt làm default nếu quyền vẫn được kiểm tra lúc chạy | Giảm lặp cấu hình ở các request phổ biến. |
| Công cụ chuyên biệt theo luồng nghiệp vụ | Thêm bằng `.tools(...)` ở request | Chỉ xuất hiện khi tác vụ cần đến. |
| Công cụ ghi dữ liệu hoặc có tác động lớn | Chỉ cung cấp sau khi kiểm tra quyền và điều kiện ở request | Tránh làm công cụ nhạy cảm luôn có mặt trong mọi cuộc hội thoại. |
| Công cụ từ MCP hoặc nguồn bên ngoài | Lọc, namespace và đăng ký có chủ đích | Tránh xung đột tên và giảm phạm vi của nguồn chưa hoàn toàn do ứng dụng kiểm soát. |

Việc không cung cấp công cụ ở request là một lớp giảm bề mặt tấn công, nhưng không thay thế authorization bên trong callback/service. Mỗi lần thực thi vẫn phải kiểm tra quyền trên tài nguyên cụ thể.

## Ví dụ chọn cách cấu hình theo tình huống

| Tình huống | Cách cấu hình |
|---|---|
| Mọi request hỗ trợ tra cứu đơn hàng | Đăng ký `orderQueryTool` bằng `defaultTools(...)`. |
| Chỉ request tạo báo cáo cần `reportTool` | Thêm `reportTool` bằng `.tools(...)` ở request. |
| Request cần danh sách tool chính xác, không dùng default | Dùng client có default set phù hợp hoặc tạo tập callback được lọc trước khi gọi. |
| Gọi `ChatModel` trực tiếp và cần default cộng thêm tool | Hợp nhất default callbacks với runtime callback bằng code trước khi tạo `ToolCallingChatOptions`. |
| Cùng request cần truyền `requestId` mới | Truyền qua `.toolContext(...)`; giá trị runtime thắng context default cùng khóa. |
| Tích hợp local tools và MCP tools | Đảm bảo tên duy nhất, namespace nguồn ngoài và kiểm tra danh sách cuối cùng. |

## Kiểm thử quy tắc kết hợp và ghi đè

Đừng chỉ kiểm tra câu trả lời cuối của mô hình. Hãy xác minh chính xác tập định nghĩa công cụ và context mà request nhận được.

| Trường hợp kiểm thử | Kết quả mong đợi |
|---|---|
| `ChatClient` có default A, B và runtime C | Model nhận A, B, C. |
| `ChatClient` có default A, B và request không gọi `.tools(...)` | Model nhận A, B. |
| `ChatClient` có default A, B; request thêm callback trùng tên A | Validation báo lỗi trùng tên; không tự thay thế A. |
| Request có `.options(...)` chứa A, B và `.tools(C)` | Callback list từ `.tools(C)` được dùng thay callback list trong options request. |
| `ChatModel` default A, B và runtime C | Model chỉ nhận C. |
| `ChatModel` default A, B và runtime list A, B, C do ứng dụng hợp nhất | Model nhận A, B, C. |
| Default context có `locale=vi-VN`, runtime có `locale=en-US` | Callback nhận `locale=en-US`. |
| Hai request đồng thời có `userId` khác nhau | Mỗi callback nhận context của đúng request; không rò dữ liệu giữa request. |
| Local tool và MCP tool trùng tên qua `ChatClient` | Request bị từ chối do tên trùng; cần đổi tên hoặc lọc nguồn. |
| Custom ChatModel loop có tên trùng | Kiểm tra thủ công danh sách; không dựa vào validation tự động của ChatClient. |

Nên tách phần tạo danh sách callback thành một hàm có thể unit test. Hàm đó nhận quyền/tác vụ đã xác định và trả về danh sách tool đã lọc, không lấy tên tool tùy ý từ đầu vào người dùng rồi đăng ký trực tiếp.

## Lưu ý về phiên bản Spring AI

Quy tắc kết hợp đã thay đổi giữa các dòng phiên bản. Tài liệu Spring AI 1.0 mô tả trường hợp default tools và runtime tools của `ChatClient` là runtime tools thay thế hoàn toàn default tools. Tài liệu Spring AI 2.1.0 hiện hành mô tả `.tools(...)` của `ChatClient` nối thêm vào `.defaultTools(...)`. Không sao chép ví dụ từ tài liệu 1.x mà không kiểm tra release line của dự án.

Ngoài ra, API cấu hình cũng thay đổi giữa các phiên bản. Trong Spring AI 2.x, `ChatClient` dùng `.tools(...)` và `.defaultTools(...)` cho callback, provider hoặc object có `@Tool`; context được cấu hình riêng bằng `.toolContext(...)` và `.defaultToolContext(...)`. Hãy kiểm tra Javadoc/tài liệu đúng phiên bản được khóa trong dependency.

Tài liệu tham khảo chính thức:

- [Spring AI 2.1.0 – Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 – ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 1.0 – Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 2.1.1-SNAPSHOT – Tool Specification Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/reference.html) (đang phát triển; dùng để đối chiếu chi tiết `options(...)`/`.tools(...)` và kiểm tra lại khi nâng cấp)

## Bài tập thực hành

Tạo một `ChatClient` cho ứng dụng hỗ trợ khách hàng:

1. Đăng ký `customerLookupTool` và `orderQueryTool` làm default tools.
2. Chỉ thêm `shipmentTrackingTool` ở request hỏi về giao hàng.
3. Thử thêm một callback cùng tên với `orderQueryTool` và quan sát lỗi trùng tên.
4. Tạo một request có `ToolCallingChatOptions` riêng; kiểm tra sự khác nhau khi đồng thời dùng `.options(...)` và `.tools(...)`.
5. Dùng `defaultToolContext` cho `application` và `locale`, sau đó truyền `locale` mới cùng `requestId` ở request.
6. Tạo một ví dụ gọi `ChatModel` trực tiếp với default callbacks và runtime callbacks; chứng minh runtime list thay thế defaults.
7. Tạo danh sách hợp nhất tường minh để giữ cả defaults và tool bổ sung.
8. Kiểm tra quyền trên từng tool trong service, kể cả khi tool đã được đăng ký làm mặc định.

Bạn hoàn thành khi có thể dự đoán chính xác tập tool và context của mỗi request, giải thích vì sao `ChatClient` và `ChatModel` khác nhau, và phát hiện được xung đột tên trước khi công cụ được thực thi.

## Danh sách kiểm tra

- [ ] Đã xác định đang dùng `ChatClient` hay gọi `ChatModel` trực tiếp.
- [ ] Đã phân biệt `defaultTools(...)`, `.tools(...)` và callback trong `ToolCallingChatOptions`.
- [ ] Với `ChatClient`, đã tính runtime tools là phần bổ sung vào defaults.
- [ ] Với `ChatModel`, đã tính runtime callback list là phần thay thế defaults.
- [ ] Không cấu hình cùng callback list ở `.options(...)` và `.tools(...)` nếu chưa chủ động quyết định thứ tự ưu tiên.
- [ ] Đã kiểm tra tên duy nhất trên tập công cụ cuối cùng.
- [ ] Không dùng trùng tên như một cách ghi đè callback.
- [ ] Đã kiểm tra `ToolCallbackResolver` và giữ resolution fallback tắt trừ khi có chính sách rõ ràng.
- [ ] Context runtime được tạo từ nguồn tin cậy và ghi đè default context khi trùng khóa.
- [ ] Không đặt user/tenant identity vào context mặc định dùng chung cho nhiều người.
- [ ] Công cụ nhạy cảm chỉ được cung cấp khi cần và luôn kiểm tra quyền lúc thực thi.
- [ ] Đã kiểm thử danh sách cuối cùng, context và khác biệt giữa các API trên phiên bản Spring AI của dự án.

Hãy coi việc đăng ký công cụ là quyết định về phạm vi quyền mà mô hình được phép yêu cầu trong một request. Hiểu đúng quy tắc kết hợp giúp ứng dụng cung cấp đúng tập công cụ, tránh xung đột tên và giữ dữ liệu theo request trong đúng ngữ cảnh thực thi.
