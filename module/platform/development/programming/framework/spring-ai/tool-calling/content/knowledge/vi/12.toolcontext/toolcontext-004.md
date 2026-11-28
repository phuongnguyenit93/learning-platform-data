# Quy tắc kết hợp ngữ cảnh mặc định và ngữ cảnh từng lần gọi

Trong một ứng dụng Spring AI, nhiều tool cần dùng chung một số thông tin như mã ứng dụng, vùng triển khai hoặc nguồn yêu cầu. Mỗi lần gọi hội thoại lại có thêm dữ liệu riêng như người dùng đã xác thực, tenant, mã tương quan và locale hiện tại. `ToolContext` cho phép truyền những dữ liệu này đến tool mà không đưa chúng vào nội dung mà mô hình ngôn ngữ nhìn thấy.

Spring AI hỗ trợ khai báo context mặc định ở cấp `ChatClient.Builder` và context riêng ở cấp request. Khi cả hai cùng được thiết lập, framework hợp nhất hai map: các key chỉ có trong map mặc định được giữ lại, các key chỉ có trong map runtime được thêm vào, và giá trị runtime ghi đè giá trị mặc định nếu trùng key. Đây là quy tắc quan trọng để tái sử dụng context chung mà vẫn giữ đúng dữ liệu của từng request.

## Sau bài học, bạn có thể

- Phân biệt context mặc định của ChatClient với context của một request.
- Dùng `defaultToolContext(...)` và `toolContext(...)` để truyền dữ liệu cho tool.
- Giải thích cách hợp nhất map và thứ tự ưu tiên khi trùng key.
- Nhận context trong method `@Tool` hoặc function callback.
- Hiểu context không được gửi cho model và không phải dữ liệu đầu vào trong JSON Schema.
- Thiết kế context an toàn khi ChatClient được dùng đồng thời bởi nhiều người dùng.
- Kiểm thử quy tắc merge, giá trị ghi đè và ranh giới quyền truy cập.

## ToolContext dùng để làm gì?

`ToolContext` chứa dữ liệu phụ trợ do ứng dụng cung cấp khi thực thi tool. Ví dụ:

- `tenantId`: tenant được xác định từ danh tính đã xác thực.
- `userId`: người dùng đang thực hiện yêu cầu.
- `requestId` hoặc `correlationId`: mã liên kết log và trace.
- `locale`: ngôn ngữ hoặc vùng định dạng cần dùng khi trả kết quả.
- `applicationId` hoặc `sourceSystem`: nguồn ứng dụng tạo ra yêu cầu.
- `authorizationScope`: phạm vi đã được ứng dụng tính toán để tool sử dụng.

Những dữ liệu này khác với tham số mà model tạo ra. Ví dụ, model có thể gửi `customerId` trong JSON để chỉ rõ hồ sơ cần tra cứu; ứng dụng truyền `tenantId` và `userId` qua `ToolContext` để dịch vụ xác định người dùng đó có quyền xem hồ sơ hay không.

~~~mermaid
flowchart TD
    A[ChatClient.Builder] --> B[Default ToolContext]
    C[Người dùng đã xác thực] --> D[Context của request]
    B --> E[Hợp nhất context]
    D --> E
    E --> F[ToolContext]
    G[Model] --> H[Tool call: tên và JSON arguments]
    H --> I[ToolCallback]
    F --> I
    I --> J[Dịch vụ nghiệp vụ]
    J --> K[Kết quả tool]
    K --> G
~~~

Spring AI gửi tool definition cho model để model biết tên, mô tả và schema đầu vào. Map context được chuyển trực tiếp đến tool lúc thực thi; dữ liệu trong context không được gửi cho model. Đây là cách truyền dữ liệu nội bộ mà không phải chèn chúng vào system prompt hoặc yêu cầu model tự tạo.

## Context mặc định và context từng lần gọi

Hai cấp context có mục đích khác nhau.

| Cấp cấu hình | API | Phạm vi | Dữ liệu phù hợp |
|---|---|---|---|
| Mặc định | `ChatClient.Builder.defaultToolContext(...)` | Các request được tạo từ ChatClient tương ứng | Mã ứng dụng, nguồn hệ thống, vùng triển khai hoặc giá trị chung ổn định |
| Từng lần gọi | `ChatClientRequestSpec.toolContext(...)` | Một request cụ thể | User ID, tenant ID, request ID, locale hoặc phạm vi quyền của request |

Ví dụ khai báo context mặc định:

~~~java
@Configuration(proxyBeanMethods = false)
public class AssistantConfiguration {

    @Bean
    ChatClient assistantChatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel)
                .defaultToolContext(Map.of(
                        "applicationId", "customer-assistant",
                        "sourceSystem", "web-portal",
                        "deploymentRegion", "ap-southeast-1"
                ))
                .build();
    }
}
~~~

Context này chứa dữ liệu chung cho các request đi qua ChatClient được tạo từ builder. Không đưa dữ liệu riêng của một người dùng vào đây nếu ChatClient được dùng chung cho nhiều người.

Ở nơi xử lý request, ứng dụng bổ sung dữ liệu theo người dùng hiện tại:

~~~java
String answer = assistantChatClient.prompt()
        .user("Cho tôi biết trạng thái khách hàng C-1024")
        .tools(customerTools)
        .toolContext(Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "userId", authenticatedUser.userId(),
                "requestId", requestId,
                "locale", authenticatedUser.locale()
        ))
        .call()
        .content();
~~~

`authenticatedUser` phải được lấy từ principal hoặc cơ chế xác thực đáng tin cậy của backend. Không lấy `tenantId` hay `userId` từ JSON do model tạo ra rồi đưa thẳng vào context.

## Quy tắc hợp nhất hai map

Khi context mặc định và context runtime cùng được thiết lập, Spring AI hợp nhất chúng thành một map. Giá trị runtime được ưu tiên khi hai map có cùng key.

Giả sử context mặc định là:

~~~java
Map<String, Object> defaultContext = Map.of(
        "applicationId", "customer-assistant",
        "sourceSystem", "web-portal",
        "locale", "vi-VN",
        "region", "ap-southeast-1"
);
~~~

Context của request hiện tại là:

~~~java
Map<String, Object> runtimeContext = Map.of(
        "tenantId", "tenant-42",
        "userId", "user-1008",
        "locale", "en-US",
        "requestId", "req-7f21"
);
~~~

Context cuối cùng được truyền cho tool tương đương:

~~~java
{
    "applicationId": "customer-assistant",
    "sourceSystem": "web-portal",
    "region": "ap-southeast-1",
    "tenantId": "tenant-42",
    "userId": "user-1008",
    "locale": "en-US",
    "requestId": "req-7f21"
}
~~~

Trong ví dụ này, `locale` của request là `en-US`, nên nó thay thế `vi-VN` mặc định. Các key khác của hai map được giữ lại.

| Key | Giá trị mặc định | Giá trị runtime | Giá trị tool nhận |
|---|---|---|---|
| `applicationId` | `customer-assistant` | Không có | `customer-assistant` |
| `sourceSystem` | `web-portal` | Không có | `web-portal` |
| `region` | `ap-southeast-1` | Không có | `ap-southeast-1` |
| `tenantId` | Không có | `tenant-42` | `tenant-42` |
| `userId` | Không có | `user-1008` | `user-1008` |
| `locale` | `vi-VN` | `en-US` | `en-US` |
| `requestId` | Không có | `req-7f21` | `req-7f21` |

Có thể mô tả quy tắc bằng phép hợp nhất map đơn giản:

~~~java
Map<String, Object> merged = new HashMap<>(defaultContext);
merged.putAll(runtimeContext);
~~~

Đây là mô tả tương đương về kết quả. Trong ứng dụng Spring AI, framework thực hiện việc hợp nhất; không cần tự merge rồi truyền lại trừ khi có logic riêng.

### Bốn trường hợp cần nhớ

1. **Chỉ có context mặc định:** tool nhận các key mặc định.
2. **Chỉ có context runtime:** tool nhận các key của request.
3. **Có cả hai và không trùng key:** tool nhận hợp của hai map.
4. **Có cả hai và trùng key:** giá trị runtime thay thế giá trị mặc định cho key đó.

Nếu context runtime rỗng hoặc không được cung cấp, context mặc định vẫn được sử dụng. Nếu một key runtime có giá trị mới, giá trị đó thay thế giá trị cũ trong map kết quả.

### Hợp nhất là nông, không phải hợp nhất đệ quy

Việc merge diễn ra ở cấp key của map ngoài cùng. Nếu hai map cùng có key `preferences` và giá trị của key đó là một map lồng nhau, giá trị runtime thay thế toàn bộ giá trị mặc định tại key `preferences`; framework không tự ghép từng key con.

Ví dụ:

~~~java
Map<String, Object> defaults = Map.of(
        "preferences", Map.of(
                "locale", "vi-VN",
                "dateFormat", "yyyy-MM-dd"
        )
);

Map<String, Object> runtime = Map.of(
        "preferences", Map.of(
                "locale", "en-US"
        )
);
~~~

Sau khi merge, `preferences` chỉ còn map runtime chứa `locale=en-US`; key `dateFormat` không tự được giữ lại. Nếu cần giữ các thuộc tính lồng nhau, hãy tự hợp nhất map con trước khi truyền context runtime hoặc thiết kế các key phẳng như `locale`, `dateFormat`.

## Nhận ToolContext trong method @Tool

Với method-based tool, thêm tham số `ToolContext` vào chữ ký method. Đây là tham số đặc biệt do Spring AI cung cấp khi gọi tool; nó không trở thành trường JSON mà model phải tạo.

Trong Spring AI 1.0.x, lớp này nằm trong package `org.springframework.ai.chat.model`:

~~~java
import org.springframework.ai.chat.model.ToolContext;
~~~

~~~java
@Component
public class CustomerTools {

    private final CustomerQueryService customerQueryService;
    private final CustomerAccessPolicy customerAccessPolicy;

    public CustomerTools(
            CustomerQueryService customerQueryService,
            CustomerAccessPolicy customerAccessPolicy) {
        this.customerQueryService = customerQueryService;
        this.customerAccessPolicy = customerAccessPolicy;
    }

    @Tool(description = "Tra cứu thông tin khách hàng trong tenant hiện tại")
    public CustomerSummary getCustomerInfo(
            @ToolParam(description = "Mã khách hàng cần tra cứu") String customerId,
            ToolContext toolContext) {

        Map<String, Object> context = toolContext.getContext();

        String tenantId = (String) context.get("tenantId");
        String userId = (String) context.get("userId");

        customerAccessPolicy.requireCanRead(
                userId,
                tenantId,
                customerId
        );

        return customerQueryService.getSummary(tenantId, customerId);
    }
}
~~~

Method nhận hai loại dữ liệu:

- `customerId` đến từ đối số JSON do model tạo theo schema.
- `tenantId` và `userId` đến từ context do ứng dụng cung cấp.

Dịch vụ vẫn kiểm tra quyền sở hữu hoặc phạm vi truy cập trước khi đọc dữ liệu. Có `tenantId` trong context không tự động chứng minh người dùng được phép xem mọi khách hàng thuộc tenant đó.

## Nhận ToolContext trong FunctionToolCallback

Với function-based tool, dùng `BiFunction<I, ToolContext, O>` khi function cần cả DTO đầu vào và context. `Function<I, O>` thông thường chỉ nhận DTO nên không có tham số context riêng.

~~~java
public record CustomerLookupRequest(String customerId) {
}

public record CustomerSummary(
        String customerId,
        String displayName,
        String status) {
}

BiFunction<CustomerLookupRequest, ToolContext, CustomerSummary> lookupCustomer =
        (request, toolContext) -> {
            Map<String, Object> context = toolContext.getContext();

            String tenantId = (String) context.get("tenantId");
            String userId = (String) context.get("userId");

            customerAccessPolicy.requireCanRead(
                    userId,
                    tenantId,
                    request.customerId()
            );

            return customerQueryService.getSummary(
                    tenantId,
                    request.customerId()
            );
        };

ToolCallback customerLookupTool = FunctionToolCallback
        .builder("lookupCustomer", lookupCustomer)
        .description("Tra cứu khách hàng mà người dùng hiện tại được phép xem")
        .inputType(CustomerLookupRequest.class)
        .build();
~~~

Khi đăng ký callback vào ChatClient, truyền context ở cấp request như với method-based tool:

~~~java
String answer = chatClient.prompt()
        .user("Tra cứu khách hàng C-1024")
        .toolCallbacks(customerLookupTool)
        .toolContext(Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "userId", authenticatedUser.userId(),
                "requestId", requestId
        ))
        .call()
        .content();
~~~

Cả method `@Tool` và `BiFunction` đều nhận context ở thời điểm callback được thực thi. Không cần đưa các trường context vào `inputType` hoặc JSON Schema.

## Dùng ToolContext khi gọi ChatModel trực tiếp

Nếu ứng dụng gọi `ChatModel` thay vì `ChatClient`, có thể cấu hình context qua `ToolCallingChatOptions`:

~~~java
import org.springframework.ai.model.tool.ToolCallingChatOptions;

ToolCallingChatOptions options = ToolCallingChatOptions.builder()
        .toolCallbacks(customerToolCallbacks)
        .toolContext(Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "userId", authenticatedUser.userId()
        ))
        .build();

Prompt prompt = new Prompt(
        "Tra cứu khách hàng C-1024",
        options
);

ChatResponse response = chatModel.call(prompt);
~~~

Nếu model có context mặc định trong options khi khởi tạo và request cũng có context runtime, Spring AI áp dụng cùng quy tắc merge: key runtime ghi đè key mặc định. Khi dùng `ChatModel` trực tiếp, cần hiểu rõ cách quản lý tool execution của phiên bản và model đang dùng; ở các phiên bản mới, `ChatModel.call(...)` có thể chỉ trả tool call request và ứng dụng phải tự điều phối vòng thực thi hoặc dùng `ChatClient` với `ToolCallingAdvisor`.

## Context không phải dữ liệu gửi cho model

`ToolContext` được thiết kế cho dữ liệu nội bộ của tool. Spring AI không đưa map context vào request nội dung gửi cho model. Model chỉ thấy:

- Tên tool.
- Mô tả tool.
- JSON Schema của đầu vào.
- Các tham số mà model tạo trong tool call.
- Kết quả tool được ứng dụng gửi lại theo luồng hội thoại.

Ví dụ, model có thể thấy schema có trường `customerId`, nhưng không thấy `tenantId`, `userId` hay `requestId trong ToolContext. Khi tool được thực thi, callback mới nhận được context đã hợp nhất.

Điều này không có nghĩa dữ liệu trong context tự động an toàn. Callback, service, log, tracing và exception handler vẫn có thể tiếp cận dữ liệu đó. Chỉ truyền những giá trị cần thiết cho tool và không ghi toàn bộ context vào log nếu map có dữ liệu nhạy cảm.

## Quy tắc an toàn khi thiết kế context

### Chỉ đưa dữ liệu dùng chung vào context mặc định

Context mặc định được tái sử dụng cho nhiều request của ChatClient. Hãy dùng nó cho dữ liệu ổn định như:

- Mã ứng dụng.
- Nguồn hệ thống.
- Vùng triển khai.
- Phiên bản chính sách hoặc cấu hình công khai nội bộ.

Không đặt `userId`, `tenantId`, quyền của người dùng hoặc mã phiên cụ thể vào context mặc định của ChatClient dùng chung. Nếu làm vậy, request của người khác có thể kế thừa dữ liệu của người dùng đầu tiên hoặc giá trị cũ.

### Đưa dữ liệu định danh vào context runtime

Tạo map runtime cho từng request từ security principal hoặc application context đáng tin cậy:

~~~java
Map<String, Object> requestToolContext = Map.of(
        "tenantId", principal.tenantId(),
        "userId", principal.userId(),
        "requestId", requestId
);

return chatClient.prompt()
        .user(question)
        .tools(customerTools)
        .toolContext(requestToolContext)
        .call()
        .content();
~~~

Không dùng dữ liệu do model tạo ra làm nguồn cho tenant hoặc user ID. Nếu người dùng nhập một mã khách hàng, mã đó có thể đi qua schema như tham số nghiệp vụ; dịch vụ phải xác nhận mã đó thuộc phạm vi người dùng được phép truy cập.

### Không dùng context thay cho phân quyền

Context cung cấp thông tin để tool thực hiện kiểm tra. Nó không tự thực hiện authorization. Mỗi dịch vụ nghiệp vụ phải xác minh quyền trước khi đọc hoặc thay đổi tài nguyên, kể cả khi callback chỉ được cung cấp cho một nhóm người dùng.

### Không lưu context request vào field mutable của singleton

`ChatClient` và tool bean thường được chia sẻ giữa nhiều request. Không gán `userId`, `tenantId` hoặc `requestId` hiện tại vào field mutable của một bean singleton rồi đọc lại khi tool chạy. Hãy truyền context qua API request để mỗi lần gọi có map riêng.

### Không sửa map context trong tool

`ToolContext.getContext()` cung cấp map không thể sửa đổi. Hãy đọc các giá trị cần thiết; nếu cần bổ sung dữ liệu nội bộ, tạo một map mới trong phạm vi xử lý của request. Không cố thay đổi map được trả về từ `getContext()`.

## Những nhầm lẫn thường gặp

- **Nghĩ runtime context thay thế toàn bộ default context:** context được merge theo key; runtime chỉ ghi đè các key trùng.
- **Nghĩ merge là đệ quy:** map lồng nhau ở key trùng bị thay thế như một giá trị, không tự merge các key con.
- **Đưa tenant/user vào default context:** context mặc định dùng chung có thể gây lẫn dữ liệu giữa request. Đưa định danh vào context runtime.
- **Cho rằng ToolContext được gửi đến model:** map này chỉ được chuyển đến tool khi thực thi; model không nhìn thấy các giá trị trong đó.
- **Đưa context fields vào JSON Schema:** context là dữ liệu do ứng dụng cung cấp, không phải tham số mà model cần tạo.
- **Dùng context thay cho kiểm tra quyền:** tool vẫn phải xác minh user, tenant và tài nguyên trong service.
- **Lưu context trong field singleton:** request đồng thời có thể ghi đè dữ liệu của nhau. Truyền map theo từng lần gọi.
- **Coi context mặc định và default tools là một:** `defaultToolContext` cung cấp dữ liệu phụ trợ; `defaultTools` hoặc `defaultToolCallbacks` cung cấp khả năng gọi công cụ. Hai cấu hình độc lập.

## Kiểm thử quy tắc kết hợp

Nên kiểm tra merge ở mức options và kiểm tra việc tool thực sự nhận được context đã hợp nhất.

| Trường hợp | Context mặc định | Context runtime | Kết quả mong đợi |
|---|---|---|---|
| Chỉ mặc định | Có key A | Không có | Giữ A |
| Chỉ runtime | Không có | Có key B | Nhận B |
| Key không trùng | A=1 | B=2 | Nhận cả A=1 và B=2 |
| Key trùng | locale=vi | locale=en | Nhận locale=en |
| Key lồng nhau trùng | preferences={locale, format} | preferences={locale} | Nhận nguyên map runtime ở key preferences |
| Request kế tiếp | A=1 | B=2 ở request trước | Request mới không được kế thừa B nếu không truyền B |

Có thể viết unit test cho quy tắc merge mà không cần gọi model:

~~~java
@Test
void runtimeContextShouldOverrideDefaultsAndKeepOtherKeys() {
    Map<String, Object> defaults = Map.of(
            "applicationId", "customer-assistant",
            "locale", "vi-VN"
    );

    Map<String, Object> runtime = Map.of(
            "tenantId", "tenant-42",
            "locale", "en-US"
    );

    Map<String, Object> merged =
            ToolCallingChatOptions.mergeToolContext(runtime, defaults);

    assertThat(merged)
            .containsEntry("applicationId", "customer-assistant")
            .containsEntry("tenantId", "tenant-42")
            .containsEntry("locale", "en-US");
}
~~~

Đây là kiểm thử trực tiếp hàm merge có trong API Spring AI 1.0.x. Ngoài ra, nên có test tích hợp với một tool giả để xác nhận `ToolContext.getContext()` nhận đúng map ở thời điểm thực thi. Test riêng hai request liên tiếp với hai tenant khác nhau giúp phát hiện lỗi vô tình lưu context vào trạng thái dùng chung.

Một test bảo mật nên xác minh rằng tool từ chối truy cập khi `tenantId` trong context không khớp tenant sở hữu tài nguyên. Không chỉ kiểm tra map có chứa tenant ID; cần kiểm tra kết quả phân quyền của service.

## Khác biệt API giữa Spring AI 1.x và 2.x

Các API cốt lõi `defaultToolContext(Map)` và `toolContext(Map)` vẫn được dùng để khai báo context mặc định và context runtime. Spring AI 2.0 tách cấu hình context khỏi API consumer `ToolSpec` cũ.

Mẫu cũ:

~~~java
chatClient.prompt()
        .tools(spec -> spec
                .callbacks(customerTool)
                .context("tenantId", tenantId))
        .call()
        .content();
~~~

Mẫu mới:

~~~java
chatClient.prompt()
        .tools(customerTool)
        .toolContext(Map.of("tenantId", tenantId))
        .call()
        .content();
~~~

Với context mặc định, dùng `defaultToolContext(...)` trên builder. Khi nâng cấp, hãy kiểm tra API của đúng phiên bản Spring AI và tách phần đăng ký tool khỏi phần truyền context để cấu hình dễ đọc và dễ kiểm thử.

## Checklist trước khi phát hành

- [ ] Context mặc định chỉ chứa dữ liệu ổn định, dùng chung.
- [ ] Context runtime được tạo mới cho từng request.
- [ ] User ID và tenant ID lấy từ nguồn xác thực đáng tin cậy.
- [ ] Đã kiểm tra runtime ghi đè đúng key trùng.
- [ ] Đã hiểu merge là nông đối với map lồng nhau.
- [ ] Tool đọc context qua `ToolContext.getContext()` hoặc `BiFunction`.
- [ ] Không đưa context nội bộ vào JSON Schema hay prompt.
- [ ] Không lưu context request trong field mutable của singleton.
- [ ] Service vẫn xác thực quyền trên từng tài nguyên.
- [ ] Có test cho merge, request kế tiếp và quyền truy cập.

## Ghi nhớ khi thiết kế

Context mặc định chứa dữ liệu ổn định dùng chung cho các request của một ChatClient. Context từng lần gọi chứa dữ liệu riêng của request, được tạo từ principal và ngữ cảnh server. Spring AI hợp nhất hai map theo key; giá trị runtime ghi đè giá trị mặc định khi trùng, còn các key không trùng được giữ lại. Việc merge là nông, không tự ghép map lồng nhau.

Tool nhận context qua tham số `ToolContext` hoặc `BiFunction`, trong khi model chỉ nhận tool definition và đối số JSON. Hãy giữ user và tenant trong context runtime, không lưu trạng thái request vào bean dùng chung, và luôn kiểm tra quyền trong dịch vụ nghiệp vụ.

## Tài liệu tham khảo

- [Spring AI 1.0.9 Reference — Tool Context](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html#_tool_context)
- [Spring AI 1.0.9 API — ToolCallingChatOptions.mergeToolContext](https://docs.spring.io/spring-ai/docs/1.0.x/api/org/springframework/ai/model/tool/ToolCallingChatOptions.html)
- [Spring AI Current Reference — Tool Context](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI Upgrade Notes — ToolContext và ChatClient API](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

