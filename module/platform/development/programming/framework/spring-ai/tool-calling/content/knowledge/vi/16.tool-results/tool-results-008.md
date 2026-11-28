# Phân biệt kết quả công cụ với structured output của câu trả lời cuối

Trong Spring AI, tool calling và structured output đều có thể tạo ra dữ liệu JSON hoặc dữ liệu ánh xạ vào Java object. Tuy nhiên, chúng giải quyết hai bước khác nhau trong một cuộc hội thoại.

- **Tool arguments** là dữ liệu đầu vào do mô hình tạo để yêu cầu ứng dụng thực thi một công cụ.
- **Tool result** là dữ liệu do callback/service trả về sau khi công cụ chạy. Spring AI chuyển kết quả này thành String để đưa vào tool response message; mặc định, message được gửi lại mô hình.
- **Structured final output** là câu trả lời cuối do mô hình tạo theo cấu trúc mà ứng dụng yêu cầu, sau đó Spring AI chuyển nội dung đó thành Java type như record hoặc DTO.

Điểm dễ nhầm là tool result có thể được serialize thành JSON, nhưng điều đó không biến nó thành structured output của câu trả lời cuối. Một JSON tool result là dữ liệu từ bước thực thi; một structured final output là kết quả sinh ra ở bước hoàn tất của mô hình. Hai loại dữ liệu có nguồn, mục đích, converter và quy tắc kiểm tra khác nhau.

Bài này sử dụng Spring AI 2.1.0 làm mốc API và giải thích cách kết hợp tool result với ChatClient.entity(...), StructuredOutputConverter, BeanOutputConverter, cách xử lý returnDirect và cách kiểm tra kết quả trước khi đưa vào nghiệp vụ.

## Ba loại dữ liệu trong một lượt tool calling

Một lượt có tool calling thường đi qua ba loại dữ liệu:

~~~mermaid
flowchart TD
    A["Ứng dụng gửi prompt và ToolDefinition"] --> B["Mô hình chọn công cụ"]
    B --> C["Tool arguments: JSON"]
    C --> D["Spring AI gọi ToolCallback"]
    D --> E["Ứng dụng thực thi service"]
    E --> F["Tool result: Object hoặc giá trị Java"]
    F --> G["ToolCallResultConverter"]
    G --> H["Tool response message: String"]
    H --> I["Mô hình đọc tool result"]
    I --> J["Mô hình tạo câu trả lời cuối"]
    J --> K["StructuredOutputConverter / entity()"]
    K --> L["Java object của câu trả lời cuối"]
~~~

| Thành phần | Ai tạo? | Vai trò | Cơ chế Spring AI |
|---|---|---|---|
| Tool arguments | Mô hình | Cung cấp dữ liệu để ứng dụng gọi công cụ. | Tool definition, input schema và bộ chuyển đổi arguments. |
| Tool result | Callback hoặc service của ứng dụng | Cung cấp dữ liệu thực tế cho mô hình tiếp tục suy luận. | ToolCallResultConverter chuyển kết quả thành String. |
| Structured final output | Mô hình | Cung cấp câu trả lời cuối theo cấu trúc ứng dụng cần. | StructuredOutputConverter<T>, BeanOutputConverter<T>, entity(...). |

Tool definition mô tả tên, chức năng và schema của **đầu vào công cụ**. Schema đó không tự động trở thành schema cho object mà phương thức công cụ trả về. Kết quả công cụ được chuyển thành nội dung tool response riêng, sau đó mô hình đọc kết quả và có thể tạo câu trả lời tiếp theo.

## Tool arguments: dữ liệu đầu vào của công cụ

Khi mô hình yêu cầu gọi một tool, nó tạo tên công cụ và arguments theo input schema đã công bố. Ví dụ, công cụ tra cứu khách hàng nhận customerId:

~~~java
class CustomerTools {

    private final CustomerQueryService customerQueryService;

    CustomerTools(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @Tool(description = "Tra cứu thông tin cơ bản của khách hàng theo mã khách hàng")
    public CustomerSnapshot lookupCustomer(
            @ToolParam(description = "Mã khách hàng do hệ thống cấp") String customerId) {
        // Gọi service nghiệp vụ
        return customerQueryService.findSnapshot(customerId);
    }
}
~~~

Schema đầu vào mô tả customerId. Nó không mô tả CustomerSnapshot trả về. Mô hình quyết định có gọi tool hay không và đề xuất arguments; ứng dụng vẫn phải parse, validation, xác thực và kiểm tra quyền trước khi thực thi.

Tool arguments là dữ liệu chưa đáng tin cậy. Không coi việc mô hình tạo đúng JSON Schema là bằng chứng rằng customerId tồn tại hoặc người dùng có quyền xem khách hàng đó.

## Tool result: dữ liệu trả về sau khi thực thi

Sau khi callback chạy, phương thức Java có thể trả về String, record, DTO, collection hoặc kiểu dữ liệu serializable khác. Spring AI dùng ToolCallResultConverter để chuyển giá trị trả về thành String tương thích với tool response.

Hợp đồng của converter:

~~~java
@FunctionalInterface
public interface ToolCallResultConverter {
    String convert(Object result, Type returnType);
}
~~~

Trong Spring AI 2.1.0:

- DefaultToolCallResultConverter là converter mặc định.
- Converter mặc định dùng Jackson để serialize kết quả.
- Có thể cấu hình converter riêng qua thuộc tính resultConverter của @Tool hoặc qua ToolMetadata đối với callback được tạo theo chương trình.

Ví dụ một tool trả về record:

~~~java
public record CustomerSnapshot(
        String displayName,
        String accountStatus,
        String supportReference) {
}

@Component
class CustomerTools {

    private final CustomerQueryService customerQueryService;

    CustomerTools(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @Tool(description = "Tra cứu tên hiển thị và trạng thái tài khoản khách hàng")
    public CustomerSnapshot lookupCustomer(String customerId) {
        Customer customer = customerQueryService.findById(customerId);

        return new CustomerSnapshot(
                customer.getDisplayName(),
                customer.getAccountStatus().name(),
                customer.getSupportReference()
        );
    }
}
~~~

Converter mặc định có thể serialize kết quả thành JSON tương tự:

~~~json
{
  "displayName": "Nguyen An",
  "accountStatus": "ACTIVE",
  "supportReference": "SUP-2048"
}
~~~

JSON này được đặt vào tool response message để mô hình đọc. Nó không phải câu trả lời cuối cho người dùng. Mô hình có thể diễn giải, kết hợp với các kết quả khác hoặc tiếp tục gọi công cụ.

### Chọn kết quả công cụ có cấu trúc nhỏ và ổn định

Nên trả về DTO/projection riêng thay vì trả nguyên JPA entity hoặc object domain lớn. Tool result có thể được gửi đến model provider và tiêu thụ token ở các vòng tiếp theo.

Hãy chỉ đưa vào result những trường mô hình cần để hoàn thành tác vụ. Tránh trả:

- Toàn bộ entity có quan hệ lồng nhau hoặc lazy-loaded collection.
- Access token, API key, session, internal credential hoặc secret.
- Thông tin nội bộ như tenantId, internal note, audit fields nếu mô hình không cần.
- Dữ liệu cá nhân hoặc tài chính ngoài phạm vi yêu cầu.
- Danh sách không giới hạn hoặc payload lớn.

Schema đầu vào giúp mô hình biết cách gọi tool; DTO kết quả giúp ứng dụng kiểm soát dữ liệu mà tool trả về. Hai hợp đồng này nên được thiết kế và kiểm thử độc lập.

## ToolCallResultConverter không phải StructuredOutputConverter

Hai converter có tên gần giống nhưng hướng chuyển đổi và thời điểm sử dụng khác nhau:

| Đặc điểm | ToolCallResultConverter | StructuredOutputConverter<T> |
|---|---|---|
| Hướng chuyển đổi | Object → String | String → T |
| Dữ liệu nguồn | Giá trị trả về của callback/tool | Nội dung văn bản do mô hình tạo |
| Mục đích | Tạo tool result để mô hình nhận được | Parse câu trả lời mô hình thành kiểu Java |
| Thời điểm | Sau khi tool thực thi | Sau khi mô hình tạo câu trả lời |
| Hướng dẫn format cho mô hình | Không có trách nhiệm sinh format cuối | Cung cấp format/schema hướng dẫn mô hình |
| API thường gặp | @Tool(resultConverter = ...), ToolMetadata | ChatClient.entity(...), BeanOutputConverter |

StructuredOutputConverter<T> kết hợp hai vai trò:

- FormatProvider cung cấp hướng dẫn định dạng để mô hình tạo output theo cấu trúc mong muốn.
- Converter<String, T> chuyển văn bản mô hình thành Java object.

Converter này hoạt động quanh text completion. Spring AI ghi rõ StructuredOutputConverter không được dùng cho LLM Tool Calling, vì tool calling vốn đã có cấu trúc riêng cho tool name và arguments. Nó phù hợp với câu trả lời có cấu trúc mà ứng dụng muốn nhận sau khi mô hình hoàn tất.

## Structured output cho câu trả lời cuối bằng ChatClient.entity()

Khi downstream cần một object có kiểu cụ thể, dùng entity(...) thay vì chỉ lấy content().

Ví dụ kiểu dữ liệu cho câu trả lời hỗ trợ khách hàng:

~~~java
public record SupportAnswer(
        String summary,
        String suggestedAction,
        boolean needsHumanReview) {
}
~~~

Gọi ChatClient:

~~~java
SupportAnswer answer = chatClient.prompt()
        .user("Tóm tắt tình trạng khách hàng và đề xuất bước xử lý tiếp theo.")
        .tools(customerTools)
        .call()
        .entity(SupportAnswer.class);
~~~

Trong luồng này:

1. Mô hình có thể gọi lookupCustomer.
2. Ứng dụng thực thi tool và trả kết quả đã serialize.
3. Mô hình đọc tool result và tạo câu trả lời cuối.
4. entity(SupportAnswer.class) chuyển nội dung câu trả lời cuối thành SupportAnswer.

entity(...) trả về object đã parse, không trả toàn bộ ChatResponse. Nếu cần cả object lẫn metadata như token usage, generation hoặc response metadata, dùng responseEntity(...):

entity(...) là API đồng bộ sau call(); không dùng được với stream() vì structured parsing cần toàn bộ nội dung phản hồi.

~~~java
ResponseEntity<ChatResponse, SupportAnswer> result = chatClient.prompt()
        .user("Tóm tắt tình trạng khách hàng và đề xuất bước xử lý tiếp theo.")
        .tools(customerTools)
        .call()
        .responseEntity(SupportAnswer.class);

SupportAnswer answer = result.entity();
ChatResponse rawResponse = result.response();
~~~

Với kiểu generic như List<SupportAnswer> hoặc Map<String, SupportAnswer>, dùng ParameterizedTypeReference để giữ thông tin generic:

~~~java
List<SupportAnswer> answers = chatClient.prompt()
        .user("Tạo các đề xuất xử lý cho những trường hợp sau...")
        .call()
        .entity(new ParameterizedTypeReference<List<SupportAnswer>>() {});
~~~

## BeanOutputConverter và StructuredOutputConverter ở mức thấp

ChatClient.entity(...) là API thuận tiện ở mức cao và được xây dựng trên StructuredOutputConverter. Khi gọi ChatModel trực tiếp hoặc cần tùy chỉnh converter, có thể dùng BeanOutputConverter:

~~~java
BeanOutputConverter<SupportAnswer> converter =
        new BeanOutputConverter<>(SupportAnswer.class);

String formatInstructions = converter.getFormat();

Prompt prompt = new Prompt(
        "Phân tích kết quả và trả lời theo cấu trúc sau:\n" + formatInstructions
);

ChatResponse response = chatModel.call(prompt);
String modelText = response.getResult().getOutput().getText();

SupportAnswer answer = converter.convert(modelText);
~~~

BeanOutputConverter sinh JSON Schema từ Java type, đưa hướng dẫn format vào prompt và parse văn bản trả về thành object. Nếu cần YAML, CSV hoặc định dạng riêng, có thể triển khai StructuredOutputConverter<T> phù hợp.

Không dùng BeanOutputConverter để serialize kết quả tool. Việc đó thuộc ToolCallResultConverter.

## Structured output là best effort nếu chỉ hướng dẫn bằng prompt

Mặc định, entity(SupportAnswer.class) yêu cầu mô hình trả về JSON theo schema suy ra từ class. Mô hình có thể không tuân thủ hoàn toàn: thiếu trường, thêm trường, sai kiểu hoặc bọc JSON trong phần giải thích. Khi parse không thành công, ứng dụng có thể nhận exception.

Spring AI 2.1.0 có hai tùy chọn tăng độ tin cậy qua EntityParamSpec:

### validateSchema()

validateSchema() bật vòng tự sửa khi response không hợp lệ. Spring AI kiểm tra output theo schema; nếu validation thất bại, lỗi cụ thể được bổ sung vào prompt và request được gửi lại. Mặc định tối đa 3 lần thử.

~~~java
SupportAnswer answer = chatClient.prompt()
        .user("Tóm tắt và đề xuất bước xử lý.")
        .call()
        .entity(SupportAnswer.class, spec -> spec.validateSchema());
~~~

Việc retry có thể tăng model call, token và chi phí. Hãy tính nó vào ngân sách của request.

### useProviderStructuredOutput()

useProviderStructuredOutput() gửi schema tới provider như một ràng buộc ở cấp API. Cách này cần model/provider hỗ trợ native structured output.

~~~java
SupportAnswer answer = chatClient.prompt()
        .user("Tóm tắt và đề xuất bước xử lý.")
        .call()
        .entity(SupportAnswer.class, spec -> spec.useProviderStructuredOutput());
~~~

Có thể kết hợp cả hai:

~~~java
SupportAnswer answer = chatClient.prompt()
        .user("Tóm tắt và đề xuất bước xử lý.")
        .call()
        .entity(SupportAnswer.class, spec -> spec
                .useProviderStructuredOutput()
                .validateSchema());
~~~

Provider-native constraint giảm khả năng sai định dạng; validation và retry bắt các trường hợp còn lại. Dù vậy, cấu trúc đúng không đồng nghĩa nội dung đúng về nghiệp vụ hoặc sự thật.

## Kết hợp tool calling và structured final output

Trong ứng dụng hỗ trợ khách hàng, tool có thể trả về dữ liệu có cấu trúc, sau đó mô hình dùng dữ liệu đó để tạo một object khác theo hợp đồng của API.

~~~java
public record CustomerSnapshot(
        String displayName,
        String accountStatus,
        String supportReference) {
}

public record SupportAnswer(
        String summary,
        String suggestedAction,
        boolean needsHumanReview) {
}

@Component
class CustomerTools {

    private final CustomerQueryService customerQueryService;

    CustomerTools(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @Tool(description = "Tra cứu tên hiển thị và trạng thái tài khoản khách hàng")
    public CustomerSnapshot lookupCustomer(String customerId) {
        Customer customer = customerQueryService.findById(customerId);
        return new CustomerSnapshot(
                customer.getDisplayName(),
                customer.getAccountStatus().name(),
                customer.getSupportReference()
        );
    }
}
~~~

Ở service orchestration:

~~~java
SupportAnswer answer = chatClient.prompt()
        .user("Tra cứu khách hàng CUS-100, tóm tắt trạng thái và đề xuất bước tiếp theo.")
        .tools(customerTools)
        .call()
        .entity(SupportAnswer.class, spec -> spec.validateSchema());
~~~

Hai Java type phục vụ hai hợp đồng riêng:

- CustomerSnapshot giới hạn dữ liệu tool trả về cho mô hình.
- SupportAnswer xác định cấu trúc câu trả lời cuối mà ứng dụng nhận.

Không tái sử dụng một DTO lớn cho cả hai mục đích nếu hai bên có yêu cầu trường khác nhau. Tool result nên chứa dữ liệu nguồn tối thiểu; final output nên chứa kết luận và hành động phù hợp với client/API.

Việc kết hợp native structured output và tool calling trong cùng một request phụ thuộc khả năng của provider/model. Nếu provider không hỗ trợ đồng thời các tính năng đó, hãy dùng prompt-based structured output nếu phù hợp hoặc tách thành một model call tổng hợp sau khi tool loop kết thúc. Tách bước sẽ tăng độ trễ và chi phí, nhưng giúp phân định rõ hai giai đoạn.

## returnDirect: tool result trở thành đầu ra gửi cho caller

Mặc định, tool result được gửi lại mô hình để mô hình tiếp tục hội thoại. Với returnDirect = true, kết quả tool bỏ qua model và được trả trực tiếp cho caller:

~~~java
@Tool(
        description = "Trả về báo cáo đã tạo sẵn cho người dùng",
        returnDirect = true
)
public ReportResult generateReport(String reportId) {
    return reportService.getCompletedReport(reportId);
}
~~~

returnDirect hữu ích khi tool result đã là đầu ra cuối và không cần mô hình diễn giải thêm. Tuy nhiên:

- Không có lượt model cuối để biến tool result thành SupportAnswer.
- Caller nhận kết quả của công cụ theo đường trả trực tiếp.
- Nếu cần kiểu trả về ổn định, hãy định nghĩa DTO cho tool result và ánh xạ ở lớp ứng dụng.
- Nếu một lượt có nhiều tool call, returnDirect chỉ được áp dụng khi tất cả công cụ trong lượt đó đều có returnDirect = true; nếu không, kết quả được gửi lại mô hình.

Vì vậy, cần quyết định rõ API muốn nhận tool result trực tiếp hay câu trả lời cuối do mô hình tạo. Đừng mặc định rằng returnDirect vẫn chạy bước structured final output.

## Validation sau khi chuyển thành Java object

Việc deserialize thành record hoặc DTO chỉ xác nhận dữ liệu có thể ánh xạ vào kiểu Java. Nó không chứng minh:

- Mã khách hàng hoặc đơn hàng tồn tại.
- Người dùng có quyền xem hoặc thay đổi tài nguyên.
- Trạng thái nghiệp vụ hợp lệ.
- Giá trị số nằm trong giới hạn nghiệp vụ.
- Kết luận của mô hình đúng với dữ liệu nguồn.
- suggestedAction được phép thực thi.

Sau khi nhận structured output, hãy kiểm tra nullability, enum, độ dài, miền giá trị, quan hệ giữa các trường và các invariant nghiệp vụ. Nếu object dẫn đến thao tác ghi, service phải xác minh lại quyền và trạng thái trước khi thực thi.

Tương tự, tool result cần được validation trước khi đưa vào conversation. Nếu service trả dữ liệu lỗi hoặc không đầy đủ, hãy trả một result có trạng thái rõ ràng hoặc phát lỗi theo policy; không để mô hình diễn giải dữ liệu thiếu thành kết luận chắc chắn.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Tool result là câu trả lời cuối. | Mặc định tool result được gửi lại mô hình; mô hình còn có thể tiếp tục gọi tool hoặc tạo final answer. |
| Tool input schema cũng mô tả output của tool. | Input schema mô tả arguments mô hình gửi; tool result được chuyển đổi riêng. |
| JSON tool result là structured output. | JSON chỉ là định dạng serialization của kết quả callback; structured output là nội dung cuối do mô hình tạo và parse thành type. |
| ToolCallResultConverter parse JSON thành DTO. | Converter này chuyển Object trả về thành String. StructuredOutputConverter mới chuyển String của model thành Java type. |
| BeanOutputConverter dùng để serialize kết quả tool. | Nó hướng dẫn và parse structured output của mô hình. |
| entity() bảo đảm nội dung đúng. | Nó tạo Java object theo schema; vẫn cần validation định dạng và nghiệp vụ. |
| returnDirect vẫn chạy model để tạo structured output. | returnDirect bỏ qua lượt model tiếp theo và trả tool result trực tiếp. |
| returnDirect luôn được áp dụng khi một tool trong batch bật nó. | Với nhiều tool call trong một lượt, tất cả tool được gọi phải bật returnDirect. |
| Structured output converter được dùng cho tool arguments. | Tool calling có cơ chế structured arguments riêng; StructuredOutputConverter phục vụ text output. |

## Kiểm thử hai hợp đồng độc lập

Nên kiểm thử tool result và final structured output riêng trước khi kiểm thử toàn bộ hội thoại.

| Kiểm thử | Điều cần xác minh |
|---|---|
| Tool arguments | JSON đúng schema, trường bắt buộc và kiểu dữ liệu được kiểm tra. |
| Tool execution | Callback gọi đúng service và kiểm tra quyền trên tài nguyên. |
| Tool result converter | DTO được serialize thành String đúng định dạng; không lộ trường nội bộ. |
| Tool result message | Nội dung được gắn với đúng tool call và gửi lại mô hình khi không dùng returnDirect. |
| Final entity() | Văn bản cuối được parse thành đúng Java type. |
| Generic structured output | ParameterizedTypeReference giữ đúng kiểu phần tử. |
| Schema validation | Output sai schema bị phát hiện; retry diễn ra theo cấu hình. |
| Provider-native output | Provider hỗ trợ schema constraint và trả đúng định dạng. |
| responseEntity() | Có cả entity và ChatResponse metadata. |
| returnDirect | Model không được gọi thêm; caller nhận đúng tool result. |
| Nhiều tool call | returnDirect chỉ được áp dụng nếu tất cả tool trong batch bật thuộc tính. |
| Business validation | Java object sai miền giá trị hoặc quyền bị từ chối trước khi dùng. |
| Provider không hỗ trợ kết hợp | Ứng dụng có fallback phù hợp hoặc tách bước tổng hợp. |

Với test tích hợp, dùng model giả lập để tạo tool call và final JSON xác định. Kiểm tra số lần model được gọi, số lần callback chạy, nội dung tool response, object cuối và metadata. Dùng model/provider thật trong tập kiểm tra riêng để xác nhận khả năng hỗ trợ structured output và tool calling đồng thời.

## Bài tập thực hành

Xây dựng luồng tra cứu đơn hàng:

1. Tạo tool getOrderSnapshot(orderId) trả về OrderSnapshot gồm mã đơn, trạng thái và ngày giao dự kiến.
2. Kiểm tra rằng tool input schema chỉ mô tả orderId.
3. Dùng ToolCallResultConverter mặc định để chuyển OrderSnapshot thành tool result JSON.
4. Cho mô hình đọc kết quả và tạo OrderAnswer gồm summary, deliveryStatus và needsSupport.
5. Dùng entity(OrderAnswer.class, spec -> spec.validateSchema()) để parse câu trả lời cuối.
6. Thử responseEntity(OrderAnswer.class) để lấy cả usage metadata.
7. Bật returnDirect cho một tool báo cáo và quan sát việc bỏ qua final model response.
8. Thử tool result thiếu trường, final JSON sai schema và object có giá trị nghiệp vụ không hợp lệ.
9. Thử provider hỗ trợ và không hỗ trợ native structured output cùng tool calling trong một request.

Bạn hoàn thành khi có thể chỉ ra dữ liệu nào do mô hình tạo để gọi tool, dữ liệu nào do service trả về, dữ liệu nào do mô hình tạo làm câu trả lời cuối và converter nào chịu trách nhiệm ở từng ranh giới.

## Danh sách kiểm tra trước khi triển khai

- [ ] Tool input schema chỉ mô tả arguments mô hình được phép tạo.
- [ ] Tool result có DTO/projection riêng và chỉ chứa trường cần cho mô hình.
- [ ] ToolCallResultConverter được hiểu là Object → String.
- [ ] StructuredOutputConverter<T> được hiểu là String → T và cung cấp format hướng dẫn mô hình.
- [ ] Không dùng StructuredOutputConverter thay cho cơ chế tool calling.
- [ ] Câu trả lời cuối dùng entity(...) hoặc responseEntity(...) khi downstream cần Java type.
- [ ] Dùng ParameterizedTypeReference cho generic output.
- [ ] Đã chọn validateSchema(), useProviderStructuredOutput() hoặc kết hợp theo khả năng provider.
- [ ] Đã tính chi phí retry khi bật schema validation.
- [ ] Đã kiểm tra provider có hỗ trợ structured output cùng tool calling trong cùng request hay không.
- [ ] Đã quyết định có dùng returnDirect hay cần mô hình tạo câu trả lời cuối.
- [ ] Không coi parse thành Java object là validation nghiệp vụ hoặc kiểm tra quyền.
- [ ] Có unit test riêng cho tool result converter và final structured output.
- [ ] Có integration test cho tool loop, result message và final typed response.

Tool result và structured final output là hai hợp đồng liên tiếp trong một lượt tool calling. Tool result mang dữ liệu thực thi trở lại mô hình; structured output chuyển câu trả lời cuối của mô hình thành kiểu Java cho ứng dụng. Khi tách rõ hai hợp đồng, ứng dụng dễ kiểm soát schema, quyền, dữ liệu trả về, validation và chi phí hơn.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling, Result Conversion và returnDirect](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – Structured Output](https://docs.spring.io/spring-ai/reference/api/structured-output.html)
- [Spring AI 2.1.0 – Output Converters](https://docs.spring.io/spring-ai/reference/api/structured-output/converters.html)
- [Spring AI 2.1.0 – ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
