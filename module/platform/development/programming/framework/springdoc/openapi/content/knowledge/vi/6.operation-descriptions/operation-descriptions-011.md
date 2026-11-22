# Đặt siêu dữ liệu trên interface, lớp cơ sở và phương thức ghi đè

Trong một ứng dụng Spring Boot, controller có thể được tổ chức theo interface, lớp cơ sở trừu tượng và các lớp triển khai cụ thể. Cách tổ chức này giúp chia sẻ hợp đồng HTTP giữa nhiều controller hoặc tách phần khai báo API khỏi logic nghiệp vụ. Với **springdoc-openapi**, siêu dữ liệu như summary, description, tag, operationId, parameter và response có thể được khai báo tại những vị trí khác nhau trong hệ phân cấp kiểu.

Vấn đề cần quan tâm là cách Java và Spring tìm annotation không hoàn toàn giống nhau. Annotation trên phương thức ghi đè không tự động được kế thừa theo quy tắc Java thông thường. Spring và springdoc có cơ chế tìm kiếm annotation trên interface hoặc phương thức cha trong một số trường hợp, nhưng kết quả phụ thuộc loại annotation, vị trí khai báo và phiên bản thư viện. Vì vậy, cần đặt metadata có chủ đích và xác minh đặc tả OpenAPI sau khi ứng dụng khởi động.

## 1. Những loại siêu dữ liệu có thể đặt trên controller

Một operation OpenAPI thường cần các nhóm thông tin sau:

| Siêu dữ liệu | Annotation thường dùng | Phạm vi |
| --- | --- | --- |
| Tên và mô tả nhóm API | **@Tag** | Controller, interface hoặc operation |
| Tóm tắt và mô tả operation | **@Operation** | Phương thức endpoint |
| Định danh operation | **operationId** trong **@Operation** | Từng operation, cần duy nhất trong tài liệu |
| Tham số | **@Parameter**, **@Parameters** | Tham số phương thức |
| Request body | **@RequestBody** của OpenAPI, **@Content** | Operation |
| Response | **@ApiResponse**, **@ApiResponses** | Operation hoặc nhóm response dùng chung |
| Schema | **@Schema** | DTO, field, parameter hoặc kiểu trả về |
| Ẩn endpoint hoặc thành phần | **@Hidden** | Controller, phương thức hoặc thành phần được hỗ trợ |

Springdoc đọc các annotation này cùng mapping của Spring MVC hoặc WebFlux để tạo operation. Các mapping như **@GetMapping**, **@PostMapping**, **@RequestMapping** xác định đường dẫn và HTTP method; annotation OpenAPI bổ sung ý nghĩa và chi tiết hợp đồng.

Có thể tổ chức theo nguyên tắc:

- Interface mô tả hợp đồng dùng chung mà controller triển khai.
- Lớp cơ sở chứa hành vi hoặc metadata thực sự dùng chung cho các controller con.
- Phương thức ghi đè mô tả chi tiết riêng khi một controller cần thay đổi nội dung hoặc ngữ nghĩa operation.
- Lớp controller cụ thể xác định bean Spring, tag và mapping ở phạm vi phù hợp với thiết kế.

Không cần lặp lại toàn bộ annotation ở mọi lớp. Việc lặp lại làm tăng nguy cơ summary, response hoặc parameter giữa các vị trí khai báo bị lệch nhau.

## 2. Phân biệt kế thừa annotation trong Java và khả năng quét của Springdoc

### Quy tắc Java cần nhớ

Annotation Java có retention và target xác định nơi có thể khai báo và thời gian có thể đọc được. Annotation muốn được đọc lúc chạy thường cần **@Retention(RetentionPolicy.RUNTIME)**.

Annotation **@Inherited** chỉ ảnh hưởng đến annotation ở cấp lớp khi lớp con kế thừa từ lớp cha. Nó không làm annotation trên interface tự động xuất hiện trên lớp triển khai, và cũng không làm annotation trên phương thức cha tự động xuất hiện trên phương thức ghi đè.

Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ApiArea {
    String value();
}

@ApiArea("Orders")
class BaseController {}

class OrderController extends BaseController {}
~~~

Trong ví dụ, Java reflection có thể tìm thấy **@ApiArea** trên lớp con vì annotation được đánh dấu **@Inherited** và quan hệ là kế thừa lớp. Nếu đặt **@ApiArea** trên một interface rồi cho **OrderController implements OrderApi**, quy tắc **@Inherited** không áp dụng.

Tương tự, annotation trên một phương thức trong lớp cha không được Java tự động sao chép vào phương thức override:

~~~java
class BaseController {
    @Operation(summary = "Đọc tài nguyên")
    public ResourceView findById(UUID id) {
        throw new UnsupportedOperationException();
    }
}

class ResourceController extends BaseController {
    @Override
    public ResourceView findById(UUID id) {
        return service.findById(id);
    }
}
~~~

Phương thức **ResourceController.findById** không tự nhận annotation **@Operation** chỉ nhờ có **@Override**. Đây là quy tắc Java; khả năng springdoc tìm metadata ở phương thức cha là một bước xử lý riêng.

### Springdoc có thể tìm metadata ở đâu?

Springdoc hỗ trợ đọc nhiều annotation OpenAPI trên interface controller và phương thức được khai báo ở interface. Điều này hữu ích khi interface đại diện cho hợp đồng API, còn lớp triển khai chỉ chứa logic nghiệp vụ. Spring Framework cũng có cơ chế tìm annotation hợp nhất trên một số kiểu và phương thức trong hệ phân cấp.

Tuy nhiên, không nên suy luận rằng mọi annotation đều tự động hợp nhất từ mọi vị trí. Ví dụ:

- **@Operation** trên interface method có thể được springdoc đọc cho endpoint triển khai interface trong các phiên bản hỗ trợ.
- **@Parameter** và các annotation OpenAPI khác trên tham số interface cần được kiểm tra trong đặc tả sinh ra.
- Metadata trên phương thức lớp cha hoặc phương thức abstract có thể được tìm thấy khi springdoc phân giải phương thức kế thừa; phương thức override có annotation riêng có thể làm thay đổi kết quả.
- **@Tag** ở interface, superclass và controller cụ thể có thể tạo ra các tag khác nhau trong operation. Không mặc định rằng các tag sẽ được nối hoặc ghi đè theo cách mong muốn.
- Mapping Spring và metadata OpenAPI là hai lớp thông tin khác nhau. Endpoint có thể được Spring ánh xạ đúng nhưng annotation mô tả vẫn thiếu trong OpenAPI.

Khi sử dụng cấu trúc kế thừa, hãy xem JSON được sinh tại **/v3/api-docs** là kết quả cuối cùng cần kiểm tra. Đừng chỉ dựa vào việc mã nguồn biên dịch hoặc endpoint chạy được.

## 3. Đặt hợp đồng trên interface controller

Đặt metadata trên interface phù hợp khi nhiều lớp triển khai cùng một hợp đồng hoặc muốn giữ khai báo API tách khỏi logic nghiệp vụ. Spring MVC hỗ trợ khai báo mapping trên interface controller; lớp triển khai là bean có **@RestController**.

Ví dụ interface mô tả API đơn hàng:

~~~java
import java.util.UUID;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@Tag(
    name = "Orders",
    description = "Tra cứu và quản lý đơn hàng"
)
@RequestMapping("/api/orders")
public interface OrderApi {

    @Operation(
        operationId = "getOrderById",
        summary = "Lấy thông tin đơn hàng",
        description = "Trả về chi tiết của một đơn hàng theo mã định danh."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy đơn hàng",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy đơn hàng"
        )
    })
    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    OrderView getById(
        @Parameter(
            name = "id",
            description = "Mã định danh đơn hàng",
            required = true,
            in = ParameterIn.PATH,
            example = "2f3c8e5d-8e7b-4a90-ae11-4a1c1f0d2b33"
        )
        @PathVariable("id") UUID id
    );
}
~~~

Lớp triển khai cung cấp logic:

~~~java
@RestController
@RequiredArgsConstructor
public class OrderController implements OrderApi {

    private final OrderService orderService;

    @Override
    public OrderView getById(UUID id) {
        return orderService.findById(id);
    }
}
~~~

Ở ví dụ này:

- **@RequestMapping** trên interface đặt prefix URL cho hợp đồng.
- **@GetMapping** trên interface method khai báo method, path và media type.
- **@Tag** nhóm operation vào Orders.
- **@Operation** cung cấp operationId, summary và description.
- **@ApiResponses** mô tả các response có ý nghĩa.
- **@Parameter** mô tả path parameter.
- Lớp triển khai không lặp lại mapping hoặc metadata OpenAPI.

Trong các phiên bản Springdoc hỗ trợ annotation trên interface, tài liệu sinh ra sẽ lấy các thông tin này cho endpoint được triển khai. Hãy xác minh operation **GET /api/orders/{id}** có đúng tag, summary, parameter và response.

Nếu annotation trên interface không được nhận diện trong cấu hình hoặc phiên bản dự án, có thể chuyển metadata cần thiết sang phương thức controller cụ thể. Trước khi làm vậy, kiểm tra xem endpoint có thực sự được Spring nhận mapping từ interface hay không; hai vấn đề mapping và OpenAPI metadata cần được chẩn đoán riêng.

### Không khai báo mapping trùng ở hai nơi

Khi chọn interface làm hợp đồng, nên giữ các mapping liên quan ở interface và để lớp triển khai tập trung vào logic. Tránh khai báo một **@GetMapping** trên interface rồi khai báo thêm một mapping khác trên implementation với ý định bổ sung đường dẫn. Mapping ở nhiều vị trí có thể tạo ra kết quả không mong muốn hoặc khiến Spring không xác định được mapping duy nhất.

Nếu dự án cần mapping nằm trên implementation, có thể chuyển cả mapping và metadata OpenAPI về phương thức đó. Quan trọng là giữ một nguồn khai báo rõ ràng và xác minh path/method cuối cùng.

## 4. Dùng lớp cơ sở để chia sẻ operation

Lớp cơ sở phù hợp khi nhiều controller con thật sự chia sẻ một hành vi hoặc endpoint chung. Ví dụ, nhiều nhóm tài nguyên có thể cung cấp endpoint đọc trạng thái hoặc thông tin phiên bản. Một phương thức public có mapping trên lớp cơ sở có thể được Spring MVC phát hiện như phương thức kế thừa của controller con.

Ví dụ:

~~~java
public abstract class BaseStatusController {

    @Operation(
        operationId = "getServiceStatus",
        summary = "Lấy trạng thái dịch vụ",
        description = "Trả về trạng thái hoạt động của thành phần."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Trạng thái dịch vụ",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = StatusView.class)
        )
    )
    @GetMapping(
        value = "/status",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public StatusView status() {
        return currentStatus();
    }

    protected abstract StatusView currentStatus();
}
~~~

Controller cụ thể kế thừa endpoint:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
public class OrderController extends BaseStatusController {

    @Override
    protected StatusView currentStatus() {
        return new StatusView("UP", "orders");
    }
}
~~~

Spring MVC có thể nhận phương thức public kế thừa như một handler method của controller cụ thể. Springdoc có thể đọc **@Operation** và **@ApiResponse** được đặt trên phương thức kế thừa đó. Kết quả mong đợi là operation **GET /api/orders/status** được mô tả trong OpenAPI.

Lớp cơ sở không nên trở thành nơi chứa mọi annotation chỉ vì có thể tái sử dụng. Chỉ đưa metadata lên lớp cha khi nội dung đó đúng với tất cả lớp con. Nếu mỗi controller có response hoặc ý nghĩa khác nhau, hãy khai báo ở controller hoặc interface tương ứng.

### Chú ý operationId khi tái sử dụng phương thức

**operationId** cần duy nhất trong một tài liệu OpenAPI. Nếu cùng một phương thức lớp cơ sở được kế thừa bởi nhiều controller, springdoc có thể tạo nhiều operation từ cùng metadata. Một operationId tĩnh đặt ở lớp cơ sở có thể bị lặp.

Có thể xử lý bằng cách:

- Không đặt operationId dùng chung ở lớp cơ sở nếu nhiều controller sẽ kế thừa endpoint.
- Đặt operationId riêng trên từng phương thức hoặc interface cụ thể khi cần.
- Tách các nhóm tài liệu nếu các API thực sự thuộc các hợp đồng riêng biệt và không được phát hành chung.
- Kiểm tra toàn bộ **paths** và operationId sau khi sinh OpenAPI để phát hiện trùng lặp.

Không nên dựa vào tên phương thức Java được sinh tự động làm operationId ổn định khi đổi tên hoặc tái cấu trúc mã nguồn.

## 5. Metadata trên phương thức ghi đè

Khi lớp con override một phương thức của lớp cơ sở hoặc triển khai phương thức interface, có thể cần cập nhật summary, description, response hoặc tag cho endpoint cụ thể.

Ví dụ lớp cơ sở cung cấp hành vi và metadata mặc định:

~~~java
public abstract class BaseResourceController {

    @Operation(
        summary = "Lấy tài nguyên",
        description = "Trả về tài nguyên theo mã định danh."
    )
    public abstract ResourceView findById(UUID id);
}
~~~

Controller đơn hàng ghi đè phương thức và bổ sung mapping riêng:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
public class OrderController extends BaseResourceController {

    @Override
    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã",
        description = "Chỉ trả về đơn hàng thuộc phạm vi người dùng hiện tại."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Đã tìm thấy đơn hàng",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Đơn hàng không tồn tại hoặc không thể truy cập"
        )
    })
    public OrderView findById(@PathVariable UUID id) {
        return orderService.findVisibleById(id);
    }
}
~~~

Trong ví dụ này, **@Operation** trên phương thức override là metadata cụ thể của endpoint đơn hàng. Khi phương thức override có annotation riêng, hãy xem metadata trên phương thức triển khai là nguồn mô tả chủ đích. Không nên giả định springdoc sẽ hợp nhất từng thuộc tính từ **@Operation** trên lớp cha với **@Operation** trên lớp con thành một annotation hoàn chỉnh.

Nếu muốn dùng metadata mặc định từ phương thức cha, có thể để phương thức override không khai báo lại annotation OpenAPI và kiểm tra xem phiên bản springdoc hiện tại có tìm được annotation trên phương thức bị ghi đè hay không. Nếu kết quả không ổn định hoặc khó hiểu với người bảo trì, khai báo metadata đầy đủ tại phương thức cụ thể sẽ rõ ràng hơn.

### Khi nào nên ghi đè metadata?

| Thành phần | Giữ metadata dùng chung khi | Ghi đè ở phương thức cụ thể khi |
| --- | --- | --- |
| Summary | Tên hành động giống nhau giữa các endpoint | Endpoint có mục đích riêng |
| Description | Quy tắc nghiệp vụ giống nhau | Phạm vi, điều kiện hoặc quyền truy cập khác nhau |
| Response | Cùng status và cùng schema | Schema hoặc nhánh lỗi khác nhau |
| Parameter | Cùng ý nghĩa và ràng buộc | Tên, kiểu hoặc điều kiện khác nhau |
| Tag | Cùng nhóm API | Endpoint thuộc nhóm tài liệu khác |
| OperationId | Chỉ có một operation sử dụng | Có nhiều operation kế thừa hoặc triển khai riêng |

Khi ghi đè, hãy kiểm tra toàn bộ operation sau khi sinh tài liệu. Một annotation ở phương thức con có thể thay đổi cả summary, tag hoặc response mà không tự động giữ các giá trị đã khai báo ở nơi khác.

## 6. Kết hợp interface và lớp cơ sở

Một thiết kế có thể sử dụng interface cho hợp đồng API và lớp cơ sở cho phần triển khai dùng chung. Ví dụ interface định nghĩa endpoint, lớp cơ sở cung cấp logic chung, còn controller cụ thể hoàn thiện hành vi:

~~~java
@Tag(name = "Documents", description = "Quản lý tài liệu")
@RequestMapping("/api/documents")
public interface DocumentApi {

    @Operation(
        operationId = "getDocument",
        summary = "Lấy thông tin tài liệu"
    )
    @GetMapping("/{id}")
    DocumentView getDocument(
        @Parameter(description = "Mã tài liệu", required = true)
        @PathVariable("id") UUID id
    );
}
~~~

Lớp cơ sở triển khai hành vi truy vấn:

~~~java
public abstract class AbstractDocumentController implements DocumentApi {

    protected abstract DocumentService documentService();

    @Override
    public DocumentView getDocument(UUID id) {
        return documentService().findById(id);
    }
}
~~~

Controller cụ thể đăng ký bean:

~~~java
@RestController
public class InternalDocumentController extends AbstractDocumentController {

    private final DocumentService service;

    public InternalDocumentController(DocumentService service) {
        this.service = service;
    }

    @Override
    protected DocumentService documentService() {
        return service;
    }
}
~~~

Thiết kế này có thể hoạt động khi Spring MVC nhận mapping từ interface và phương thức triển khai được phân giải đúng. Tuy nhiên, nếu có nhiều lớp cùng triển khai **DocumentApi**, mỗi lớp có thể tạo ra operation giống nhau hoặc mapping trùng. Cần quyết định rõ lớp nào là controller được đăng ký và API nào được công bố.

Không nên tạo nhiều lớp triển khai cùng một interface controller trong cùng ứng dụng chỉ để tái sử dụng metadata nếu các endpoint có cùng method và path. Thay vào đó, cân nhắc dùng interface làm hợp đồng cho một controller duy nhất, hoặc tách các API có URL và document group rõ ràng.

## 7. Metadata trên tham số và DTO kế thừa

Annotation trên tham số cũng cần được xử lý có chủ đích. Java không tự kế thừa parameter annotation từ interface hoặc phương thức cha sang phương thức override. Nếu mô tả tham số ở interface, kiểm tra OpenAPI có nhận được tên, vị trí, required, description và example hay không.

Ví dụ:

~~~java
@Operation(summary = "Tìm kiếm đơn hàng")
@GetMapping
List<OrderView> search(
    @Parameter(
        name = "status",
        description = "Trạng thái đơn hàng",
        example = "PENDING"
    )
    @RequestParam(required = false) String status
);
~~~

Nếu phương thức triển khai override và cần thay đổi ý nghĩa parameter, đặt annotation trên tham số của phương thức triển khai hoặc định nghĩa hợp đồng riêng. Sau đó kiểm tra mục **parameters** trong operation được sinh ra.

Với DTO có kế thừa, **@Schema** mô tả kiểu dữ liệu và thuộc tính. Ví dụ:

~~~java
@Schema(description = "Thông tin tài nguyên cơ bản")
public abstract class BaseResourceView {

    @Schema(description = "Mã định danh", example = "RES-100")
    private String id;
}

@Schema(description = "Thông tin đơn hàng")
public class OrderView extends BaseResourceView {

    @Schema(description = "Trạng thái đơn hàng", example = "CREATED")
    private String status;
}
~~~

Springdoc thường có thể mô tả thuộc tính kế thừa trong schema của kiểu con. Nếu cấu hình Jackson hoặc schema composition thay đổi cách serialize, kiểm tra **components.schemas** để bảo đảm các field thực tế được mô tả. Metadata của DTO và metadata của operation là hai phạm vi khác nhau; annotation trên interface controller không thay thế mô tả schema của DTO.

## 8. Tránh xung đột và trùng lặp annotation

Một số tình huống dễ tạo ra tài liệu khó hiểu:

**Cùng khai báo @Operation trên interface và implementation.** Nếu hai nơi có summary hoặc response khác nhau, kết quả có thể phụ thuộc thứ tự phân giải annotation của thư viện. Chọn một vị trí làm nguồn chính hoặc khai báo đầy đủ ở nơi cần ghi đè.

**Khai báo @Tag trên cả interface và controller.** Kiểm tra operation có một tag hay nhiều tag và tag có được tạo trong phần **tags** cấp tài liệu. Nếu muốn một endpoint nằm trong nhiều nhóm, khai báo danh sách tag một cách rõ ràng tại operation.

**Khai báo @ApiResponse ở lớp cha và lớp con.** Không mặc định các response được nối tự động. Đối chiếu mục **responses** và bảo đảm mọi mã trạng thái thực tế cần công bố đều có schema phù hợp.

**Dùng operationId giống nhau trong nhiều controller.** Đặt operationId riêng hoặc bỏ khai báo tĩnh tại lớp dùng chung. Một operationId duy nhất giúp công cụ sinh client tạo tên phương thức ổn định.

**Đặt mapping ở cả interface và phương thức override.** Tránh tạo mapping chồng lấn. Chọn vị trí khai báo mapping nhất quán và kiểm tra endpoint bằng Spring MVC cũng như OpenAPI.

**Dùng @Hidden ở vị trí không phù hợp.** Nếu một phương thức kế thừa bị ẩn hoặc được ghi đè, kiểm tra operation có thực sự bị ẩn theo mong muốn. Không dùng ẩn endpoint để che một lỗi metadata hoặc mapping.

## 9. Kiểm tra metadata đã được kế thừa trong OpenAPI

Sau khi khởi động ứng dụng, lấy đặc tả JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem operation cần kiểm tra:

~~~bash
jq '.paths["/api/orders/{id}"].get | {
  operationId,
  tags,
  summary,
  description,
  parameters,
  responses
}' openapi.json
~~~

Kiểm tra schema được tham chiếu:

~~~bash
jq '.components.schemas.OrderView' openapi.json
~~~

Nếu dự án sử dụng document group, hãy gọi đúng endpoint tài liệu của nhóm đó. Nếu ứng dụng đổi đường dẫn API docs hoặc dùng context path, điều chỉnh URL theo cấu hình thực tế.

Một checklist kiểm tra hữu ích:

1. Operation có xuất hiện đúng path và HTTP method không?
2. Summary, description và operationId có đến từ vị trí khai báo dự kiến không?
3. Tag có đúng tên và mô tả không?
4. Parameter có đúng tên, vị trí, required, schema và example không?
5. Response có đủ mã trạng thái và schema không?
6. Schema DTO có bao gồm thuộc tính kế thừa và đúng tên JSON sau serialization không?
7. Không có operationId trùng hoặc operation bị nhân đôi do nhiều controller triển khai cùng hợp đồng.
8. Swagger UI hiển thị đúng operation và không báo lỗi khi tải đặc tả.

Có thể bổ sung kiểm thử tự động để đọc **/v3/api-docs** bằng Jackson và assert các field như **operationId**, **summary**, **tags** và **responses**. Cách này giúp phát hiện khi nâng cấp Springdoc hoặc thay đổi cấu trúc controller làm metadata không còn được nhận diện.

## 10. Gợi ý chọn vị trí khai báo

| Trường hợp | Vị trí nên ưu tiên | Lý do |
| --- | --- | --- |
| Nhiều implementation cùng một API contract | Interface | Metadata đi cùng hợp đồng mà các lớp triển khai thực hiện |
| Nhiều controller có cùng hành vi thực sự | Lớp cơ sở | Có thể chia sẻ mapping và metadata của endpoint chung |
| Endpoint có ý nghĩa hoặc response riêng | Phương thức controller cụ thể | Metadata gần với hành vi thực tế nhất |
| Tag của một controller | Lớp controller hoặc interface API | Xác định nhóm tài liệu ở phạm vi phù hợp |
| Mô tả field và cấu trúc dữ liệu | DTO và thuộc tính của DTO | Schema gắn với kiểu dữ liệu được serialize |
| Tham số chỉ có ý nghĩa ở một endpoint | Tham số phương thức endpoint | Giữ mô tả sát với cách endpoint nhận dữ liệu |

Không có một vị trí duy nhất phù hợp với mọi dự án. Hãy chọn vị trí theo quyền sở hữu hợp đồng và khả năng tái sử dụng thực tế, sau đó kiểm tra kết quả OpenAPI để bảo đảm metadata không bị thiếu hoặc nhân đôi.

## 11. Kết luận

Interface, lớp cơ sở và phương thức ghi đè đều có thể tham gia vào việc mô tả API trong Springdoc, nhưng cơ chế tìm annotation của Springdoc cần được phân biệt với quy tắc kế thừa của Java. Đặt metadata dùng chung ở nơi sở hữu hợp đồng, ghi đè rõ ràng khi endpoint có ngữ nghĩa riêng, tránh mapping và operationId trùng nhau. Cuối cùng, đọc đặc tả OpenAPI được sinh ra để xác minh summary, tag, parameter, response và schema đúng với controller mà client thực sự gọi.
