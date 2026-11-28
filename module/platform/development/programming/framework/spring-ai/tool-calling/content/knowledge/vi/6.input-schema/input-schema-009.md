# Phân biệt ràng buộc schema với kiểm tra dữ liệu lúc thực thi

Trong Spring AI tool calling, input schema mô tả dữ liệu mà mô hình cần gửi khi yêu cầu gọi một công cụ. Schema giúp mô hình hiểu tên trường, kiểu dữ liệu, trường bắt buộc và một số giới hạn về định dạng hoặc giá trị. Tuy nhiên, một đối số phù hợp với schema vẫn có thể sai nghiệp vụ, không tồn tại hoặc vượt quá quyền của người dùng.

Vì vậy, cần phân biệt hai trách nhiệm:

- **Ràng buộc schema** mô tả hợp đồng đầu vào để mô hình tạo yêu cầu gọi có cấu trúc phù hợp.
- **Kiểm tra lúc thực thi** xác minh dữ liệu thực tế, quy tắc nghiệp vụ và quyền truy cập trước khi ứng dụng thực hiện thao tác.

Schema là lớp hướng dẫn và ràng buộc hình dạng dữ liệu. Ứng dụng vẫn phải kiểm tra dữ liệu tại ranh giới thực thi trước khi gọi dịch vụ nghiệp vụ.

## 1. Hai lớp kiểm soát khác nhau

Giả sử ứng dụng có tool tra cứu tồn kho theo mã SKU. Schema yêu cầu mô hình gửi một chuỗi có dạng mã SKU. Mô hình gửi **SKU-100**; dữ liệu này có thể đúng kiểu và đúng định dạng, nhưng sản phẩm có thể không tồn tại, không thuộc tenant hiện tại hoặc người dùng không được phép xem.

| Câu hỏi | Schema đầu vào | Kiểm tra lúc thực thi |
| --- | --- | --- |
| Trường nào cần gửi? | Mô tả bằng **required** | Kiểm tra dữ liệu thực nhận có thiếu không |
| Giá trị có đúng kiểu? | Khai báo **type** | Kiểm tra sau khi parse/bind |
| Chuỗi có đúng định dạng? | Có thể mô tả bằng **pattern** | Kiểm tra theo quy tắc thực tế |
| Số lượng có nằm trong giới hạn? | Có thể mô tả **minimum**, **maximum** | Kiểm tra giới hạn nghiệp vụ hiện hành |
| SKU có tồn tại? | Schema không thể xác minh dữ liệu lưu trữ | Service tra cứu nguồn dữ liệu |
| Người dùng có quyền xem SKU? | Schema không xác định danh tính đáng tin cậy | Ứng dụng xác thực và phân quyền |
| Kết quả có còn hợp lệ tại thời điểm xử lý? | Schema không biết trạng thái hệ thống | Service kiểm tra trạng thái hiện tại |

Ví dụ, **SKU-100** có thể hợp lệ về cú pháp nhưng không tồn tại trong kho. **SKU-101** có thể tồn tại nhưng thuộc một tenant khác. Cả hai trường hợp đều cần được xử lý ở phía ứng dụng.

## 2. Schema đầu vào mô tả điều gì?

Schema thường được biểu diễn bằng JSON Schema. Một schema cho tool tra cứu tồn kho có thể trông như sau:

~~~json
{
  "type": "object",
  "properties": {
    "sku": {
      "type": "string",
      "description": "Mã SKU, ví dụ SKU-100",
      "minLength": 7,
      "maxLength": 16,
      "pattern": "^SKU-[A-Z0-9]+$"
    },
    "includeWarehouse": {
      "type": "boolean",
      "description": "Có bao gồm tên kho trong kết quả hay không"
    }
  },
  "required": ["sku"],
  "additionalProperties": false
}
~~~

Các thành phần có ý nghĩa:

- **type** xác định kiểu dữ liệu của object hoặc thuộc tính.
- **properties** liệt kê các trường hợp lệ của object.
- **description** giải thích ý nghĩa của trường để mô hình tạo giá trị phù hợp.
- **required** liệt kê tên những trường bắt buộc phải có trong object.
- **minLength**, **maxLength**, **minimum**, **maximum**, **minItems** và **maxItems** mô tả một số giới hạn cơ bản.
- **pattern** mô tả mẫu chuỗi bằng biểu thức chính quy.
- **enum** giới hạn giá trị vào một tập lựa chọn đã biết.
- **additionalProperties: false** yêu cầu object không có thuộc tính ngoài danh sách được khai báo, nếu bộ xử lý schema hỗ trợ ràng buộc này.

Schema trên giúp mô hình hiểu rằng **sku** là chuỗi bắt buộc, có định dạng bắt đầu bằng **SKU-**, còn **includeWarehouse** là boolean tùy chọn. Nó không xác minh SKU có trong cơ sở dữ liệu hay người dùng có quyền xem kho tương ứng.

### required không có nghĩa là không được null

Trong JSON Schema, **required** yêu cầu thuộc tính phải xuất hiện trong object. Điều đó khác với việc thuộc tính phải có giá trị khác null. Ví dụ, một trường có thể xuất hiện với giá trị null nếu schema cho phép kiểu null.

~~~json
{
  "type": "object",
  "properties": {
    "note": {
      "type": ["string", "null"]
    }
  },
  "required": ["note"]
}
~~~

Trong ví dụ này, **note** bắt buộc phải xuất hiện nhưng giá trị null vẫn được chấp nhận. Nếu trường tùy chọn và không xuất hiện, ứng dụng cần quy định giá trị mặc định. Nếu trường xuất hiện với null, ứng dụng cần xử lý riêng theo hợp đồng dữ liệu. Không nên mặc định xem thiếu trường và null là cùng một tình huống.

### enum, pattern và format

**enum** hữu ích khi trường chỉ nhận một số lựa chọn đã biết, chẳng hạn:

~~~json
{
  "type": "string",
  "enum": ["AVAILABLE", "OUT_OF_STOCK", "DISCONTINUED"]
}
~~~

**pattern** phù hợp với chuỗi có quy ước hình dạng như SKU, mã bưu chính hoặc mã tham chiếu. **format** có thể mô tả ngữ nghĩa của giá trị như **date**, **date-time** hoặc **email**. Tuy nhiên, mức độ thực thi format phụ thuộc vào bộ kiểm tra JSON Schema và cấu hình của nó; nhiều hệ thống xem format là annotation hoặc hint. Không dùng format như bằng chứng duy nhất rằng một giá trị đã được xác thực.

## 3. Spring AI đưa schema vào tool definition như thế nào?

Với tool khai báo bằng phương thức, Spring AI có thể tạo input schema từ kiểu tham số, chữ ký phương thức và metadata annotation. Ví dụ:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class InventoryTools {

    private final InventoryQueryService inventoryQueryService;

    public InventoryTools(InventoryQueryService inventoryQueryService) {
        this.inventoryQueryService = inventoryQueryService;
    }

    @Tool(
        name = "lookup_inventory",
        description = "Tra cứu tồn kho theo mã SKU. Công cụ chỉ đọc dữ liệu."
    )
    public String lookupInventory(
            @ToolParam(
                description = "Mã SKU cần tra cứu, ví dụ SKU-100"
            ) String sku,
            @ToolParam(
                description = "Có bao gồm tên kho hay không",
                required = false
            ) Boolean includeWarehouse) {

        return inventoryQueryService.lookup(sku, includeWarehouse);
    }
}
~~~

Trong ví dụ:

- Kiểu **String** của **sku** được dùng để mô tả một giá trị chuỗi.
- Kiểu **Boolean** của **includeWarehouse** được dùng để mô tả giá trị boolean.
- **@ToolParam** cung cấp mô tả và cho phép đánh dấu tham số không bắt buộc.
- **@Tool** cung cấp tên và mô tả mục đích của công cụ.

**@ToolParam** không phải một bộ kiểm tra nghiệp vụ tổng quát. Các thuộc tính của annotation này phục vụ metadata tham số mà Spring AI dùng để tạo tool definition. Không nên suy ra rằng mọi annotation Bean Validation trên tham số sẽ tự động được chuyển thành JSON Schema hoặc tự động được thực thi khi callback chạy.

Nếu cần kiểm soát chi tiết hơn đối với schema, ứng dụng có thể cung cấp schema tường minh trong **ToolDefinition**, hoặc cấu hình kiểu đầu vào/schema cho callback tương ứng. API cụ thể và khả năng sinh schema phụ thuộc phiên bản Spring AI. Dù schema được sinh tự động hay khai báo thủ công, ứng dụng vẫn cần xác thực dữ liệu ở runtime.

## 4. Vì sao schema không đủ để bảo vệ ứng dụng?

Có một số giới hạn cơ bản:

1. **Mô hình có thể tạo dữ liệu không đúng.** Schema giúp định hướng nhưng không phải mọi provider hoặc chế độ gọi tool đều thực thi mọi keyword theo cùng một cách.
2. **Schema không truy vấn được trạng thái nghiệp vụ.** Nó không biết SKU có tồn tại, số lượng hiện tại là bao nhiêu hoặc đơn hàng đã bị hủy chưa.
3. **Schema không xác thực danh tính.** Một trường **userId** hoặc **tenantId** do mô hình gửi vẫn là dữ liệu đầu vào không đáng tin cậy.
4. **Schema không thay thế kiểm tra quyền.** Giá trị có cấu trúc hợp lệ vẫn có thể trỏ đến tài nguyên người dùng không được phép truy cập.
5. **Trạng thái có thể thay đổi sau khi tạo tool call.** Một mặt hàng còn hàng khi mô hình tạo yêu cầu nhưng đã hết hàng khi service thực thi.
6. **Schema không thay thế kiểm soát tác động phụ.** Một yêu cầu hợp lệ về kiểu dữ liệu vẫn có thể là hành động không được phép trong luồng hiện tại.

Ngay cả khi provider hỗ trợ chế độ strict hoặc constrained tool schema, ứng dụng vẫn phải xác minh đầu vào, quyền và trạng thái nghiệp vụ trước khi thực hiện. Cơ chế strict có thể giảm lỗi về cấu trúc, nhưng không thể xác nhận một sự kiện trong database hoặc quyết định người dùng có quyền trên tài nguyên.

## 5. Quy trình kiểm tra tại runtime

Một quy trình thực thi an toàn có thể chia thành các bước:

~~~mermaid
flowchart TD
    A[Nhận tool call] --> B[Parse và bind đối số]
    B --> C{Dữ liệu đúng cấu trúc?}
    C -->|Không| X[Trả lỗi đầu vào an toàn]
    C -->|Có| D[Kiểm tra định dạng và giới hạn]
    D --> E{Đầu vào hợp lệ?}
    E -->|Không| X
    E -->|Có| F[Lấy danh tính và context tin cậy]
    F --> G{Có quyền trên tài nguyên?}
    G -->|Không| Y[Từ chối truy cập]
    G -->|Có| H[Kiểm tra quy tắc nghiệp vụ]
    H --> I{Nghiệp vụ cho phép?}
    I -->|Không| Z[Trả kết quả nghiệp vụ phù hợp]
    I -->|Có| J[Thực thi service]
    J --> K[Giới hạn và chuẩn hóa kết quả]
    K --> L[Trả tool result]
~~~

### Bước 1: Parse và bind

Đối số JSON cần được parse thành kiểu dữ liệu mà callback hoặc phương thức tool mong đợi. JSON sai cú pháp, kiểu không thể chuyển đổi hoặc trường bắt buộc bị thiếu có thể làm thất bại ngay ở bước này.

Ứng dụng cần xử lý các lỗi binding một cách có kiểm soát. Không nên giả định mọi chuỗi đều chuyển được thành số, ngày hoặc enum. Nếu một giá trị không parse được, không gọi dịch vụ nghiệp vụ với giá trị mặc định tùy tiện.

### Bước 2: Kiểm tra cấu trúc và định dạng

Kiểm tra null, chuỗi rỗng, độ dài, biểu thức chính quy, giới hạn số và các quan hệ giữa trường. Một số ràng buộc có thể lặp lại từ schema bằng Bean Validation hoặc validator riêng. Việc lặp lại là có chủ đích: schema giúp mô hình tạo đầu vào; validator ở server xác nhận dữ liệu thực nhận.

### Bước 3: Xác thực và phân quyền

Lấy danh tính người dùng từ cơ chế xác thực của ứng dụng. Kiểm tra quyền trên tài nguyên cụ thể và phạm vi tenant trước khi truy vấn hoặc thay đổi dữ liệu. Không lấy quyền từ mô tả tool hoặc trường do mô hình tự chọn.

### Bước 4: Kiểm tra quy tắc nghiệp vụ

Xác minh các điều kiện phụ thuộc dữ liệu và trạng thái hiện tại, ví dụ sản phẩm còn tồn tại, ngày kết thúc không trước ngày bắt đầu, số lượng có thể bán đủ đáp ứng yêu cầu hoặc bản ghi vẫn ở trạng thái cho phép xử lý.

### Bước 5: Thực thi và chuẩn hóa kết quả

Chỉ sau các bước kiểm tra mới gọi service nghiệp vụ. Kết quả gửi lại mô hình cần ngắn gọn, đúng dữ kiện và không chứa dữ liệu nhạy cảm hoặc chi tiết nội bộ không cần thiết.

## 6. Ví dụ kiểm tra dữ liệu bằng Bean Validation

Giả sử SKU phải có dạng **SKU-** theo sau bởi 3 đến 12 ký tự chữ in hoa hoặc chữ số. Có thể mô tả quy tắc bằng một record đầu vào:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record SkuQuery(
    @NotBlank
    @Size(min = 7, max = 16)
    @Pattern(regexp = "^SKU-[A-Z0-9]{3,12}$")
    String sku
) {}
~~~

Sau đó dùng **jakarta.validation.Validator** một cách tường minh trong lớp tool hoặc service:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class InventoryTools {

    private final InventoryQueryService inventoryQueryService;
    private final Validator validator;

    public InventoryTools(
            InventoryQueryService inventoryQueryService,
            Validator validator) {
        this.inventoryQueryService = inventoryQueryService;
        this.validator = validator;
    }

    @Tool(description = "Tra cứu tồn kho theo mã SKU.")
    public String lookupInventory(
            @ToolParam(description = "Mã SKU, ví dụ SKU-100") String sku) {

        Set<ConstraintViolation<SkuQuery>> violations =
            validator.validate(new SkuQuery(sku));

        if (!violations.isEmpty()) {
            return "Mã SKU không hợp lệ. Hãy cung cấp mã theo dạng SKU-100.";
        }

        return inventoryQueryService.lookup(sku);
    }
}
~~~

Ở đây, validator được gọi rõ ràng. Ứng dụng cần có một Bean Validation provider trên classpath để Spring cung cấp bean **Validator**; với Spring Boot, có thể dùng starter validation phù hợp với phiên bản dự án. Việc đặt annotation **@NotBlank**, **@Size** hoặc **@Pattern** trên một record không có nghĩa Spring AI tự động chạy Bean Validation khi gọi tool. Nếu muốn dùng method validation của Spring, cần cấu hình đúng bean, proxy và cơ chế validation; với luồng tool, hãy kiểm tra rõ rằng bước validation thực sự được thực thi. Không nên dựa vào giả định.

Thông báo trả về được giới hạn ở thông tin cần để người dùng sửa đầu vào. Không trả toàn bộ **ConstraintViolation**, tên lớp nội bộ hoặc stack trace cho mô hình nếu những chi tiết đó không cần thiết.

## 7. Kiểm tra quy tắc nghiệp vụ và quyền truy cập

Đầu vào hợp lệ về cú pháp chưa đảm bảo nghiệp vụ cho phép. Ví dụ, **SKU-100** có thể hợp lệ theo regex nhưng không có trong kho. Service cần truy vấn trạng thái thực tế và trả kết quả tương ứng.

Với dữ liệu nhiều tenant, tenant ID cần đến từ context đáng tin cậy do ứng dụng cung cấp:

~~~java
import org.springframework.ai.chat.model.ToolContext;

@Tool(
    description = "Tra cứu tồn kho của một SKU trong tenant hiện tại."
)
public String lookupInventory(
        @ToolParam(description = "Mã SKU cần tra cứu") String sku,
        ToolContext toolContext) {

    String tenantId =
        (String) toolContext.getContext().get("tenantId");

    return inventoryQueryService.lookupForTenant(sku, tenantId);
}
~~~

Ứng dụng cung cấp context từ phiên đăng nhập đã xác thực:

~~~java
import java.util.Map;

return chatClient.prompt()
    .user(question)
    .tools(inventoryTools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

**tenantId** trong ví dụ không phải một trường trong schema đầu vào của mô hình. Ứng dụng lấy nó từ danh tính đã xác thực và truyền vào lần thực thi. Service vẫn phải kiểm tra quyền trên SKU và tenant theo chính sách thực tế. Không dùng **ToolContext** như bằng chứng tự thân rằng dữ liệu đã được xác thực; độ tin cậy phụ thuộc vào nơi ứng dụng lấy và cách ứng dụng tạo context.

**ToolContext** là tham số ngữ cảnh đặc biệt do Spring AI chuyển cho phương thức tool; nó không phải một trường nghiệp vụ để mô hình tạo trong JSON arguments. Schema của ví dụ này vẫn chỉ cần mô tả **sku**.

## 8. Thiếu trường, null và giá trị mặc định

Đối với trường tùy chọn, cần quy định rõ hành vi khi:

- Trường không xuất hiện trong JSON.
- Trường xuất hiện với giá trị null.
- Trường xuất hiện với chuỗi rỗng hoặc giá trị mặc định.
- Trường có kiểu sai hoặc giá trị ngoài tập cho phép.

Ví dụ, **includeWarehouse** không bắt buộc có thể được mặc định là **false** khi bị bỏ qua. Nếu trường xuất hiện với **null**, ứng dụng cần quyết định có chấp nhận null hay từ chối. Đừng vô tình chuyển null thành false nếu điều đó làm mất ý nghĩa của dữ liệu.

Với trường bắt buộc, schema nên đánh dấu **required** và runtime vẫn kiểm tra null/blank theo quy tắc của ứng dụng. Khi một trường được tạo từ dữ liệu nội bộ như tenant ID, user ID hoặc role, không nên đưa nó thành trường do mô hình cung cấp.

## 9. Xử lý lỗi validation

Không phải lỗi nào cũng nên được xử lý giống nhau. Nên phân biệt:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Parse/binding | JSON sai, chuỗi không chuyển được sang số | Từ chối đối số, không gọi service |
| Cấu trúc/định dạng | SKU rỗng, sai pattern, số âm | Trả hướng dẫn sửa đầu vào |
| Nghiệp vụ | SKU không tồn tại, kho không có hàng | Trả kết quả nghiệp vụ rõ ràng |
| Phân quyền | Người dùng không có quyền xem tenant hoặc sản phẩm | Từ chối truy cập, không tiết lộ dữ liệu |
| Hạ tầng | Database hoặc API kho bị lỗi | Ghi nhận lỗi kỹ thuật và xử lý theo chính sách retry/fallback |

Không biến lỗi database thành thông báo “SKU không tồn tại”. Điều đó làm mô hình và người dùng hiểu sai trạng thái thực tế. Cũng không gửi exception thô, stack trace, câu SQL hoặc thông tin cấu hình nội bộ vào tool result. Hãy dùng lớp xử lý lỗi của ứng dụng hoặc cơ chế xử lý lỗi tool đã cấu hình trong Spring AI để chuyển lỗi thành thông tin an toàn và phù hợp.

## 10. Khác biệt giữa schema provider và validator của ứng dụng

Tool definition được gửi đến provider/model dưới dạng hợp đồng. Provider có thể hỗ trợ một tập con JSON Schema, có cách diễn giải riêng cho một số keyword hoặc cung cấp chế độ strict riêng. Vì thế:

- Không giả định mọi provider hỗ trợ toàn bộ JSON Schema.
- Kiểm tra schema thực tế được gửi đi khi đổi model/provider.
- Giữ schema đơn giản, dễ sinh và dễ hiểu nếu không cần ràng buộc phức tạp.
- Kiểm tra hành vi với phiên bản Spring AI và model đang triển khai.
- Duy trì validation ở server kể cả khi provider báo đã tuân thủ schema.

JSON Schema validator và Bean Validation cũng có mục tiêu khác nhau. JSON Schema mô tả cấu trúc tài liệu JSON; Bean Validation kiểm tra object Java sau khi bind. Chúng có thể diễn đạt một số quy tắc giống nhau, nhưng không thay thế nhau hoàn toàn. Quy tắc nghiệp vụ và phân quyền thường cần service hoặc policy riêng.

## 11. Ma trận kiểm thử

Nên kiểm tra schema, validation và quyền theo các nhóm độc lập:

| Trường hợp | Kiểm tra schema/binding | Kiểm tra runtime | Kết quả mong đợi |
| --- | --- | --- | --- |
| SKU đúng định dạng và tồn tại | Đối số có trường **sku** dạng string | Service tìm thấy bản ghi và xác minh quyền | Trả thông tin tồn kho |
| SKU sai pattern | Schema mô tả pattern | Validator từ chối giá trị thực nhận | Không gọi service |
| SKU rỗng | Mô tả chuỗi bắt buộc | **@NotBlank** hoặc validator từ chối | Trả hướng dẫn sửa đầu vào |
| SKU đúng dạng nhưng không tồn tại | Schema vẫn hợp lệ | Service tra cứu không thấy | Trả kết quả không tìm thấy |
| SKU thuộc tenant khác | Schema vẫn hợp lệ | Policy từ chối truy cập | Không tiết lộ dữ liệu |
| Trường tùy chọn bị bỏ qua | Binding nhận giá trị vắng mặt | Áp dụng default đã quy định | Hành vi nhất quán |
| Dịch vụ kho bị lỗi | Schema vẫn hợp lệ | Service phát sinh lỗi hạ tầng | Xử lý lỗi kỹ thuật, không giả thành dữ liệu không tồn tại |

Unit test nên kiểm tra validator và service được gọi đúng hoặc không được gọi. Integration test nên kiểm tra callback nhận đối số, context được truyền, quyền được xác minh và kết quả được đưa về hội thoại. Contract test có thể kiểm tra schema đã công bố để phát hiện thay đổi ngoài ý muốn khi refactor chữ ký phương thức.

## 12. Checklist khi thiết kế tool input

- Schema có tên trường rõ ràng và kiểu dữ liệu phù hợp.
- Trường bắt buộc, tùy chọn và null được phân biệt.
- Mô tả có định dạng, đơn vị và ví dụ khi cần.
- Enum, pattern và giới hạn chỉ được dùng khi phản ánh quy tắc thực tế.
- Không đưa user ID, tenant ID, role hoặc bí mật thành dữ liệu mô hình tự quyết định.
- Runtime validation chạy trước khi gọi service.
- Service kiểm tra sự tồn tại, trạng thái và quy tắc nghiệp vụ hiện hành.
- Authorization kiểm tra quyền trên tài nguyên cụ thể.
- Lỗi được phân loại và chuyển thành thông tin an toàn.
- Tool result chỉ chứa dữ liệu cần thiết.
- Có kiểm thử cho cả đầu vào hợp lệ, sai cấu trúc, sai nghiệp vụ, thiếu quyền và lỗi hạ tầng.

## Ghi nhớ

Schema đầu vào giúp mô hình hiểu hình dạng dữ liệu cần gửi và giảm các lỗi về cấu trúc. Nó không thể xác minh dữ liệu có tồn tại, còn hợp lệ theo trạng thái hiện tại hoặc thuộc phạm vi người dùng được phép truy cập. Trong Spring AI, hãy xem input schema là hợp đồng giữa mô hình và ứng dụng; parse, validate, kiểm tra quyền và quy tắc nghiệp vụ tại runtime trước khi gọi service. Đây là ranh giới bảo vệ thực tế của hệ thống.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [JSON Schema — Understanding JSON Schema](https://json-schema.org/understanding-json-schema/)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
