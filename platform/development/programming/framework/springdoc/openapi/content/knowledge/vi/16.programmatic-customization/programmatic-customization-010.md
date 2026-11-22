# Thứ tự thực thi và nguy cơ ghi đè giữa các customizer

springdoc-openapi cho phép tùy biến đặc tả sau khi quét controller và tạo mô hình OpenAPI. Một ứng dụng có thể đăng ký nhiều customizer để bổ sung metadata, chuẩn hóa response, thêm security requirement, chỉnh sửa schema hoặc thay đổi server URL. Khi các customizer cùng sửa một phần của tài liệu, thứ tự chạy quyết định kết quả cuối cùng.

Ví dụ, customizer thứ nhất đặt tiêu đề API, customizer thứ hai thay toàn bộ đối tượng `Info`, rồi customizer thứ ba bổ sung version. Nếu customizer thứ hai chạy sau cùng, tiêu đề do customizer thứ nhất đặt có thể biến mất. Một trường hợp khác là hai customizer cùng thêm response `429`; customizer chạy sau có thể thay response đã được thêm trước nếu cả hai ghi vào cùng một status code.

Bài học này giải thích vòng đời tạo tài liệu, các loại customizer thường dùng, cách Spring sắp xếp bean, sự khác biệt giữa thao tác thay thế và bổ sung, và cách thiết kế chuỗi tùy biến có kết quả xác định.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định các giai đoạn springdoc xây dựng và tùy biến OpenAPI.
- Phân biệt customizer ở cấp operation, toàn tài liệu và nhóm tài liệu.
- Dùng `@Order` hoặc `Ordered` để khai báo thứ tự thực thi.
- Hiểu vì sao `@DependsOn`, `@Primary` và thứ tự khởi tạo bean không thay thế thứ tự customizer.
- Nhận diện các thao tác có thể thay thế dữ liệu trước đó như `setInfo`, `setServers`, `setResponses`.
- Thiết kế thao tác bổ sung có kiểm tra trùng lặp và bảo toàn cấu hình hiện hữu.
- Tránh xung đột giữa customizer khi cùng sửa path, operation, response, tag, security hoặc component.
- Kiểm thử thứ tự, tính idempotent và tài liệu OpenAPI cuối cùng.

## 1. Vì sao thứ tự customizer quan trọng?

OpenAPI là một cấu trúc dữ liệu có nhiều cấp:

- Root document chứa `info`, `servers`, `tags`, `paths`, `components` và `security`.
- Mỗi path chứa các operation như GET, POST, PUT và DELETE.
- Mỗi operation có parameters, request body, responses, tags, security và extensions.
- Components chứa schemas, responses, parameters, security schemes và các thành phần có thể tái sử dụng.

Nhiều customizer có thể cùng sửa một node trong cấu trúc này. Ví dụ:

| Customizer | Thay đổi |
|---|---|
| MetadataCustomizer | Đặt title, description và version trong `info` |
| ServerCustomizer | Thêm server URL cho môi trường triển khai |
| SecurityCustomizer | Bổ sung security scheme và security requirement |
| ErrorResponseCustomizer | Bổ sung response lỗi dùng chung cho operation |
| TagCustomizer | Chuẩn hóa tag và thứ tự tag |

Nếu các customizer hoạt động trên những phần độc lập, thứ tự có thể không ảnh hưởng. Nhưng khi hai customizer cùng ghi vào một property hoặc cùng thay một collection, kết quả phụ thuộc thứ tự. Điều này tạo ra các lỗi khó nhận biết: title biến mất, server bị mất, response lỗi bị thay thế, tag bị lặp hoặc security requirement không còn như mong muốn.

Hãy coi các customizer như một chuỗi biến đổi tuần tự trên cùng một mô hình OpenAPI. Với mỗi biến đổi, cần biết nó đọc dữ liệu nào, ghi vào đâu, có thay thế dữ liệu hiện tại hay chỉ bổ sung dữ liệu.

## 2. Vòng đời tạo tài liệu OpenAPI

Ở mức khái niệm, quá trình tạo tài liệu có thể được nhìn theo các giai đoạn:

1. Spring Boot khởi tạo application context và đăng ký các bean liên quan đến springdoc.
2. springdoc phát hiện controller, request mapping, functional route và metadata annotation.
3. springdoc xây dựng path, operation, parameter, request body, response và schema.
4. Các operation customizer được gọi khi operation được tạo hoặc hoàn thiện.
5. Các OpenAPI customizer nhận tài liệu đã được tập hợp và sửa đổi mô hình tổng thể.
6. Tài liệu được chuyển thành JSON hoặc YAML để trả về qua endpoint tài liệu.

Đây là sơ đồ khái quát. Vị trí chính xác của từng hook có thể thay đổi theo phiên bản springdoc, loại ứng dụng MVC/WebFlux và cách dùng grouped API. Không nên suy ra thứ tự của mọi extension point chỉ từ thứ tự khởi tạo bean.

Ví dụ endpoint mặc định thường là:

~~~text
GET /v3/api-docs
~~~

Nếu ứng dụng định nghĩa group, mỗi group có thể có endpoint tài liệu riêng, thường theo dạng:

~~~text
GET /v3/api-docs/{group}
~~~

Các customizer có thể được áp dụng ở phạm vi khác nhau. Vì vậy, khi xác minh kết quả, hãy gọi đúng endpoint tài liệu mà client hoặc cổng API thực sự sử dụng.

### OperationCustomizer và OpenApiCustomizer chạy ở cấp nào?

`OperationCustomizer` tác động lên một operation cùng `HandlerMethod` tương ứng. Nó phù hợp để thêm metadata dựa trên controller method, ví dụ extension chứa tên chức năng, response mặc định hoặc mô tả dựa trên annotation nội bộ.

`OpenApiCustomizer` nhận toàn bộ đối tượng `OpenAPI`. Nó phù hợp với thay đổi cấp tài liệu như `info`, `servers`, root tags, security schemes hoặc thao tác quét qua nhiều path/operation.

Một customizer cấp operation thường chạy trong lúc operation được tạo; customizer cấp tài liệu có thể nhìn thấy cấu trúc tổng thể sau khi các operation đã được tập hợp. Tuy nhiên, không nên dùng giả định về thứ tự này để thay thế tài liệu API của phiên bản springdoc đang dùng. Hãy kiểm thử hook cụ thể nếu logic phụ thuộc vào thời điểm.

## 3. Các loại customizer và phạm vi áp dụng

springdoc cung cấp nhiều extension point. Chọn loại có phạm vi nhỏ nhất đủ để giải quyết nhu cầu:

| Extension point | Phạm vi | Ví dụ sử dụng |
|---|---|---|
| `OperationCustomizer` | Một operation gắn với handler method | Thêm extension hoặc response theo annotation của method |
| `GlobalOperationCustomizer` | Operation trong các tài liệu, bao gồm group theo hỗ trợ của phiên bản | Áp dụng chính sách chung cho operation |
| `OpenApiCustomizer` | Toàn bộ tài liệu OpenAPI mặc định | Chỉnh `info`, `servers`, root tags hoặc components |
| `GlobalOpenApiCustomizer` | Toàn bộ tài liệu, bao gồm grouped OpenAPI theo hỗ trợ của phiên bản | Chính sách chung cho mọi group |
| `RouterOperationCustomizer` | Operation phát hiện từ functional route | Bổ sung metadata cho route không dùng controller annotation |

Tên interface, package và phạm vi group có thể thay đổi giữa các major version. Với springdoc 2.x, các customizer thường nằm trong package `org.springdoc.core.customizers`; `ParameterObject` nằm trong `org.springdoc.core.annotations`. Hãy dùng API được cung cấp bởi dependency thực tế của dự án.

### Chọn đúng phạm vi

Nếu chỉ cần sửa một operation dựa trên method annotation, hãy dùng OperationCustomizer. Không cần quét toàn bộ `openApi.getPaths()` để tìm lại method đó.

Nếu cần bổ sung server URL hoặc `Info` cho toàn bộ tài liệu mặc định, OpenApiCustomizer phù hợp hơn.

Nếu ứng dụng có nhiều `GroupedOpenApi` và chính sách phải áp dụng cho mọi group, hãy xem xét GlobalOpenApiCustomizer hoặc GlobalOperationCustomizer. Một OpenApiCustomizer thông thường có thể chỉ được áp dụng cho tài liệu mặc định, tùy phiên bản và cách đăng ký. Đừng cho rằng mọi group tự động nhận cùng customizer.

### Ví dụ OperationCustomizer

~~~java
import io.swagger.v3.oas.models.Operation;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
class OperationCustomizationConfiguration {

    @Bean
    @Order(100)
    OperationCustomizer addOperationSourceExtension() {
        return (operation, handlerMethod) -> {
            operation.addExtension(
                "x-source-method",
                handlerMethod.getMethod().getName()
            );
            return operation;
        };
    }
}
~~~

Ví dụ thêm extension cho từng operation dựa trên tên method. Extension được thêm bằng `addExtension`, không thay toàn bộ map extensions hiện có.

### Ví dụ OpenApiCustomizer

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
class DocumentCustomizationConfiguration {

    @Bean
    @Order(100)
    OpenApiCustomizer addDefaultInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }

            Info info = openApi.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Product API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };
    }
}
~~~

Customizer chỉ điền các trường còn thiếu. Cách làm này giữ lại giá trị `title` hoặc `version` đã được khai báo từ nguồn khác. Nếu mục tiêu là bắt buộc dùng một giá trị cụ thể, có thể chủ động ghi đè, nhưng cần thể hiện rõ quyền sở hữu của customizer đó.

## 4. Thứ tự thực thi với @Order và Ordered

Spring hỗ trợ sắp xếp các bean khi chúng được thu thập thành một danh sách hoặc được xử lý bởi một cơ chế có sử dụng order comparator. Có thể khai báo thứ tự bằng annotation `@Order` trên bean hoặc bằng cách triển khai interface `Ordered`.

Quy tắc giá trị:

- Số nhỏ hơn có độ ưu tiên cao hơn và được xử lý trước.
- `Ordered.HIGHEST_PRECEDENCE` biểu thị ưu tiên cao nhất.
- `Ordered.LOWEST_PRECEDENCE` biểu thị ưu tiên thấp nhất.
- Nếu nhiều bean có cùng giá trị order, không nên dựa vào thứ tự đăng ký ngẫu nhiên hoặc chi tiết triển khai để quyết định kết quả.

Ví dụ:

~~~java
@Bean
@Order(10)
OpenApiCustomizer addBaseMetadata() {
    return openApi -> {
        // Bước 1: thiết lập metadata nền.
    };
}

@Bean
@Order(20)
OpenApiCustomizer addEnvironmentServer() {
    return openApi -> {
        // Bước 2: bổ sung server theo môi trường.
    };
}

@Bean
@Order(30)
OpenApiCustomizer addSharedResponses() {
    return openApi -> {
        // Bước 3: bổ sung response dùng chung.
    };
}
~~~

Khi springdoc thu thập các bean cùng loại theo thứ tự Spring, customizer có order 10 được xử lý trước order 20, rồi đến order 30. Hãy xác nhận hành vi với phiên bản springdoc đang dùng nếu logic phụ thuộc vào thứ tự này.

### Triển khai Ordered

Nếu cần tạo customizer thành class riêng:

~~~java
public class MetadataOpenApiCustomizer
        implements OpenApiCustomizer, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void customise(OpenAPI openApi) {
        // Bổ sung metadata nền.
    }
}
~~~

Tùy phiên bản interface, tên phương thức callback có thể là `customise` hoặc `customize`. Ví dụ trên minh họa kiểu API dùng `customise`; hãy dùng đúng chữ ký mà dependency springdoc của dự án cung cấp. Annotation `@Order` thường ngắn gọn hơn khi chỉ cần đặt thứ tự cho bean.

### Order chỉ có ý nghĩa trong đúng pipeline

`@Order` không tạo ra một chuỗi tổng hợp duy nhất cho mọi extension point. Một OperationCustomizer và một OpenApiCustomizer thuộc hai giai đoạn khác nhau; không nên kỳ vọng đặt `@Order(10)` cho OpenApiCustomizer sẽ khiến nó chạy trước OperationCustomizer có `@Order(20)`.

Tương tự, thứ tự giữa `OpenApiCustomizer` và `GlobalOpenApiCustomizer`, hoặc giữa customizer mặc định và customizer của group, phụ thuộc cách springdoc tổ chức từng pipeline. Hãy đặt order rõ ràng trong cùng loại collection và kiểm thử phạm vi áp dụng riêng.

### @Order không phải thứ tự khởi tạo bean

`@Order` thường điều khiển thứ tự trong collection hoặc cơ chế có hỗ trợ order. Nó không phải cam kết bean được khởi tạo theo đúng thứ tự số. Spring có thể khởi tạo bean theo dependency và lifecycle của application context.

Ba annotation/cơ chế dễ bị nhầm:

| Cơ chế | Vai trò | Có sắp xếp thứ tự callback customizer không? |
|---|---|---|
| `@Order` / `Ordered` | Sắp xếp bean trong collection có hỗ trợ order | Có, nếu springdoc dùng comparator cho collection đó |
| `@DependsOn` | Ép khởi tạo bean phụ thuộc trước bean hiện tại | Không tự sắp xếp thứ tự gọi customizer |
| `@Primary` | Chọn bean ưu tiên khi cần resolve một dependency đơn | Không sắp xếp toàn bộ các customizer |

Nếu cần một customizer chạy sau một customizer khác, hãy dùng order trong đúng pipeline hoặc hợp nhất logic có quan hệ phụ thuộc vào một customizer duy nhất. Không dùng `@DependsOn` để cố điều khiển thứ tự biến đổi OpenAPI.

## 5. Phân biệt thao tác thay thế và bổ sung

Các model của swagger-core có nhiều setter và helper method. Chúng không có cùng semantics:

- Setter như `setInfo`, `setServers`, `setResponses` thường thay tham chiếu hoặc collection hiện tại bằng giá trị mới.
- Method `add...` thường thêm phần tử, nhưng với map có khóa như responses hoặc schemas, thêm cùng khóa có thể thay giá trị cũ.
- Sửa object con thông qua getter thường chỉ thay property được chọn, giữ lại các property khác của object đó.

Không nên gọi một thao tác là “merge” nếu nó chỉ thay cả object hoặc map. Hãy đọc đúng semantics của model method và kiểm tra giá trị trước khi ghi.

| Thành phần | Thao tác có nguy cơ thay thế | Cách cập nhật ít phá hủy hơn |
|---|---|---|
| Info | `openApi.setInfo(new Info())` | Lấy `getInfo()` rồi cập nhật riêng title/description/version |
| Servers | `openApi.setServers(newServers)` | Duyệt danh sách hiện tại, thêm hoặc cập nhật server theo URL |
| Root tags | `openApi.setTags(tags)` | Thêm tag nếu chưa có tên tương ứng |
| Responses | `operation.setResponses(newResponses)` | Lấy map hiện tại, chỉ thêm status code chưa có |
| Security | `operation.setSecurity(requirements)` | Kiểm tra requirement hiện tại rồi bổ sung scheme cần thiết |
| Extensions | `operation.setExtensions(map)` | Dùng `addExtension` cho từng key |
| Paths | `openApi.setPaths(paths)` | Thêm hoặc cập nhật một path cụ thể, kiểm tra path đã tồn tại |
| Schemas | `components.setSchemas(schemas)` | Thêm schema theo tên duy nhất, xử lý rõ khi tên đã tồn tại |

### setInfo có thể xóa metadata trước đó

Đoạn mã sau thay toàn bộ Info hiện tại:

~~~java
openApi.setInfo(new Info()
    .title("Internal API")
    .version("2.0"));
~~~

Nếu một customizer trước đó đã đặt description, terms of service, contact hoặc license, các giá trị đó có thể mất vì Info mới không chứa chúng.

Nếu chỉ cần cập nhật title, hãy sửa đúng property:

~~~java
if (openApi.getInfo() == null) {
    openApi.setInfo(new Info());
}

openApi.getInfo().setTitle("Internal API");
~~~

Cách thứ hai giữ các property Info khác. Nếu muốn thay toàn bộ Info, hãy làm điều đó có chủ đích và để một customizer duy nhất sở hữu toàn bộ metadata.

### setServers và addServersItem

`setServers` thay danh sách server hiện tại. Nếu một customizer đặt server URL từ cấu hình deployment, customizer khác gọi `setServers` với một danh sách chỉ có URL local có thể xóa server deployment.

`addServersItem` bổ sung server vào danh sách. Tuy nhiên, gọi lặp lại có thể tạo server trùng. Hãy kiểm tra URL trước khi thêm:

~~~java
String serverUrl = "https://api.example.com";

if (openApi.getServers() == null) {
    openApi.setServers(new ArrayList<>());
}

boolean exists = openApi.getServers().stream()
    .anyMatch(server -> serverUrl.equals(server.getUrl()));

if (!exists) {
    openApi.addServersItem(
        new Server().url(serverUrl).description("Production")
    );
}
~~~

Ví dụ dùng URL làm khóa nhận diện. Nếu cùng URL nhưng description khác nhau, cần quyết định rõ nên giữ description hiện tại hay cập nhật nó.

## 6. Xung đột ở responses, security, tags và components

### Responses được định danh bằng status code

`ApiResponses` là map có khóa là mã response như `200`, `400`, `429` hoặc `default`. Khi hai customizer cùng ghi response `429`, customizer chạy sau có thể thay response cùng khóa.

Ví dụ dễ ghi đè:

~~~java
operation.getResponses().addApiResponse(
    "429",
    new ApiResponse().description("Rate limit exceeded")
);
~~~

Nếu một customizer khác cũng thêm `429` với nội dung khác, giá trị sau có thể thay giá trị trước. Hãy chọn chính sách:

- Nếu response `429` đã có, giữ nguyên.
- Nếu chưa có, thêm response mặc định.
- Nếu cần chuẩn hóa response hiện có, sửa description/content có chủ đích thay vì thay cả ApiResponse.

Ví dụ chỉ thêm khi chưa tồn tại:

~~~java
ApiResponses responses = operation.getResponses();
if (responses == null) {
    responses = new ApiResponses();
    operation.setResponses(responses);
}

if (!responses.containsKey("429")) {
    responses.addApiResponse(
        "429",
        new ApiResponse().description("Rate limit exceeded")
    );
}
~~~

Nếu response lỗi dùng chung cần được chuẩn hóa trên mọi operation, hãy đặt logic ở một customizer có quyền sở hữu rõ ràng và tránh để nhiều bean cùng định nghĩa status code đó.

### Security requirement có thể bị thay thế

Root security (`openApi.security`) và operation security (`operation.security`) là hai cấp khác nhau. `setSecurity(...)` ở một cấp có thể thay danh sách hiện tại tại chính cấp đó. Nếu một operation đã có security riêng, thêm security ở root không nhất thiết có nghĩa operation sẽ dùng thêm requirement như bạn mong đợi; semantics OpenAPI cho phép operation-level security ghi đè root-level security.

Trước khi thay security, hãy kiểm tra:

- Security scheme đã tồn tại trong `components.securitySchemes` chưa.
- Root security đang áp dụng requirement nào.
- Operation có khai báo security riêng hay không.
- `security: []` có được dùng để đánh dấu operation không cần xác thực hay không.

Trong OpenAPI, mỗi Security Requirement Object trong danh sách `security` là một lựa chọn thay thế (OR). Bên trong một object, nhiều scheme phải được đáp ứng đồng thời (AND). Vì vậy, thêm một object mới vào danh sách có thể tạo thêm cách xác thực thay thế; thêm nhiều scheme vào cùng object lại yêu cầu client đáp ứng tất cả scheme đó.

Ví dụ hai lựa chọn xác thực thay thế:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Client có thể dùng bearer token hoặc API key. Nếu đặt cả hai scheme trong cùng một Security Requirement Object, client phải cung cấp cả hai:

~~~yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
~~~

Không xóa security requirement hiện có chỉ để thêm scheme mới. Hãy gộp requirement theo semantics OR/AND của OpenAPI và xác nhận bằng tài liệu được sinh.

### Tags và extensions

Root tags và operation tags là hai phần riêng. Thêm tag vào operation không tự tạo mô tả tag ở root. Nếu customizer thêm root tag nhiều lần, tài liệu có thể chứa tên trùng. Hãy kiểm tra theo `tag.getName()` trước khi thêm.

Với extension, ưu tiên `addExtension("x-key", value)` thay cho `setExtensions(...)` nếu chỉ muốn thêm một key. Nếu key đã tồn tại, cần quy định customizer nào có quyền cập nhật giá trị.

### Components và tên schema

`components.schemas` là map theo tên component. Hai customizer cùng thêm schema tên `ErrorResponse` không tạo hai schema độc lập; thao tác ghi cùng khóa có thể thay giá trị đã có. Điều này đặc biệt nguy hiểm khi hai nhóm dùng cùng tên nhưng cấu trúc khác nhau.

Đặt tên component có phạm vi rõ, ví dụ `PublicErrorResponse` và `AdminErrorResponse`, hoặc dùng một schema dùng chung được sở hữu bởi một cấu hình trung tâm. Trước khi thêm schema, kiểm tra tên đã tồn tại và xác minh `$ref` từ operation vẫn trỏ đến schema đúng.

## 7. Thiết kế chuỗi customizer có quyền sở hữu rõ ràng

Thứ tự chỉ giải quyết một phần vấn đề. Nếu nhiều customizer cùng có quyền sửa một property, việc sắp xếp chúng chỉ quyết định ai ghi cuối cùng; cấu hình vẫn mong manh khi có bean mới hoặc thay đổi order.

Một thiết kế dễ bảo trì nên xác định rõ:

1. Customizer nào sở hữu một phần của tài liệu.
2. Customizer nào chỉ được bổ sung dữ liệu khi chưa có.
3. Customizer nào được phép thay thế giá trị hiện tại.
4. Các customizer có phụ thuộc vào kết quả của nhau hay không.
5. Phạm vi áp dụng là tài liệu mặc định, mọi group hay một group cụ thể.

Ví dụ quy ước:

| Dữ liệu | Chủ sở hữu đề xuất | Quy tắc |
|---|---|---|
| `info.title`, `info.version` | Metadata customizer | Một nơi quyết định giá trị cuối |
| `info.description`, contact, license | Metadata customizer | Cập nhật property riêng, giữ phần không sở hữu |
| `servers` | Server customizer | Upsert theo URL, tránh xóa server khác |
| Security schemes | Security customizer | Tên scheme duy nhất, không thay map nếu không cần |
| Response `429` | Rate-limit customizer | Chỉ thêm nếu chưa có hoặc cập nhật theo chính sách đã thống nhất |
| Error schema | Error-contract customizer | Tên component có quy ước, không ghi trùng schema khác cấu trúc |
| Operation extension | Operation customizer | Dùng key riêng theo namespace `x-...` |

### Ví dụ chia trách nhiệm theo order

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    @Order(10)
    OpenApiCustomizer ensureDocumentInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }

            Info info = openApi.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Catalog API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };
    }

    @Bean
    @Order(20)
    OpenApiCustomizer ensureProductionServer() {
        return openApi -> {
            String url = "https://api.example.com";
            if (openApi.getServers() == null) {
                openApi.setServers(new ArrayList<>());
            }

            boolean exists = openApi.getServers().stream()
                .anyMatch(server -> url.equals(server.getUrl()));

            if (!exists) {
                openApi.addServersItem(
                    new Server().url(url).description("Production")
                );
            }
        };
    }

    @Bean
    @Order(30)
    OpenApiCustomizer ensureRateLimitResponse() {
        return openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }

            openApi.getPaths().values().forEach(pathItem ->
                pathItem.readOperations().forEach(operation -> {
                    ApiResponses responses = operation.getResponses();
                    if (responses == null) {
                        responses = new ApiResponses();
                        operation.setResponses(responses);
                    }
                    if (!responses.containsKey("429")) {
                        responses.addApiResponse(
                            "429",
                            new ApiResponse().description("Rate limit exceeded")
                        );
                    }
                })
            );
        };
    }
}
~~~

Ba customizer có order khác nhau và mỗi bean phụ trách một phần. `ensureDocumentInfo` chỉ điền trường còn thiếu; `ensureProductionServer` thêm server theo URL nếu chưa có; `ensureRateLimitResponse` chỉ thêm status code chưa tồn tại. Nhờ đó, nếu tài liệu đã có description, server hoặc response `429`, các customizer không xóa chúng một cách vô tình.

Ví dụ cần các import tương ứng từ swagger-models và Spring. Hãy điều chỉnh server URL theo cấu hình ứng dụng thay vì hardcode môi trường production trong code nếu ứng dụng chạy ở nhiều môi trường.

Trong ví dụ, `ensureRateLimitResponse` thêm `429` cho mọi operation được duyệt. Ứng dụng thực tế nên lọc operation theo annotation, policy hoặc nhóm endpoint thật sự có rate limit; không công bố response mà server không thể trả.

Các kiểu được dùng trong ví dụ gồm `OpenAPI`, `Info`, `Server`, `ApiResponses`, `ApiResponse`, `OpenApiCustomizer`, `@Bean`, `@Configuration` và `@Order`. Hãy import từ `io.swagger.v3.oas.models`, `org.springdoc.core.customizers` và các package Spring tương ứng.

### Khi nên gộp nhiều customizer thành một?

Nếu hai thay đổi luôn phải xảy ra cùng nhau hoặc bước sau cần dữ liệu vừa được bước trước tạo, một customizer duy nhất thường rõ ràng hơn:

~~~java
@Bean
OpenApiCustomizer applySharedApiPolicy() {
    return openApi -> {
        ensureDocumentInfo(openApi);
        ensureServers(openApi);
        ensureCommonResponses(openApi);
    };
}
~~~

Việc gộp logic giảm phụ thuộc vào cơ chế sắp xếp bean và làm rõ một nơi chịu trách nhiệm cho chính sách chung. Không nên tạo một customizer tổng hợp quá lớn cho mọi thay đổi không liên quan; hãy gộp những bước có cùng vòng đời và quyền sở hữu.

Các method `ensureDocumentInfo`, `ensureServers` và `ensureCommonResponses` trong ví dụ là helper do ứng dụng định nghĩa; phần thân được lược bỏ để tập trung vào cách tổ chức chuỗi.

## 8. Tính idempotent và tránh trạng thái dùng chung

Một customizer idempotent là customizer có thể chạy nhiều lần mà không làm tài liệu thay đổi ngoài ý muốn sau lần đầu. Với đầu vào như nhau, chạy một lần hay nhiều lần sẽ cho cùng kết quả.

Ví dụ không idempotent:

~~~java
openApi.addServersItem(
    new Server().url("https://api.example.com")
);
~~~

Nếu customizer được gọi lặp, danh sách server có thể chứa URL trùng. Tương tự, mỗi lần thêm tag, parameter hoặc response vào collection có thể tạo bản sao hoặc thay giá trị cùng khóa.

Phiên bản có kiểm tra trước:

~~~java
boolean hasServer = openApi.getServers() != null
    && openApi.getServers().stream()
        .anyMatch(server ->
            "https://api.example.com".equals(server.getUrl())
        );

if (!hasServer) {
    openApi.addServersItem(
        new Server().url("https://api.example.com")
    );
}
~~~

Các thao tác thường cần upsert hoặc kiểm tra trùng:

- Server: nhận diện theo URL.
- Tag: nhận diện theo tên.
- Parameter: nhận diện theo `name` và `in`.
- Response: nhận diện theo status code.
- Schema: nhận diện theo tên component.
- Security scheme: nhận diện theo scheme name.
- Extension: nhận diện theo key.

### Không lưu OpenAPI model mutable trong field dùng chung

Customizer thường là singleton bean. Không lưu đối tượng `OpenAPI`, `Operation`, `ApiResponses` hoặc collection mutable từ lần chạy này sang lần chạy khác trong field static hay field instance để tái sử dụng. Tài liệu cho group khác hoặc lần build khác có thể bị ảnh hưởng bởi trạng thái cũ.

Không nên:

~~~java
@Component
class UnsafeCustomizer implements OpenApiCustomizer {
    private final List<String> seenPaths = new ArrayList<>();

    @Override
    public void customise(OpenAPI openApi) {
        // seenPaths giữ trạng thái qua nhiều lần tạo tài liệu.
    }
}
~~~

Nên tạo collection tạm trong lần gọi và thao tác trên chính OpenAPI được truyền vào:

~~~java
@Component
class SafeCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        Set<String> currentPaths =
            new LinkedHashSet<>(openApi.getPaths().keySet());

        // Xử lý currentPaths trong phạm vi lần gọi này.
    }
}
~~~

Ngoài ra:

- Không sinh giá trị ngẫu nhiên hoặc timestamp mới mỗi lần customizer chạy nếu chúng không thuộc hợp đồng.
- Không gọi dịch vụ mạng hoặc cơ sở dữ liệu từ customizer để tạo tài liệu nếu có thể đưa cấu hình cần thiết vào application properties.
- Không phụ thuộc thứ tự duyệt của collection không có thứ tự xác định nếu output cần ổn định.
- Không sửa trực tiếp annotation hoặc controller metadata từ customizer.

### Idempotent không có nghĩa là không được ghi đè

Một customizer có thể chủ động đặt `info.version` thành một giá trị cấu hình và vẫn idempotent vì chạy nhiều lần cho cùng kết quả. Điều quan trọng là hành vi ghi đè phải có chủ ý, có quyền sở hữu rõ và không phụ thuộc dữ liệu tạm từ lần chạy trước.

## 9. Customizer với GroupedOpenApi

Một ứng dụng có thể tạo nhiều tài liệu, ví dụ public, admin và partner. Mỗi group có path, operation và metadata riêng:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .addOpenApiCustomizer(openApi ->
            openApi.getInfo().setTitle("Public API")
        )
        .build();
}
~~~

Customizer gắn trực tiếp với builder của group phù hợp khi thay đổi chỉ dành cho group đó. Ví dụ public group có title riêng, admin group có server hoặc tag riêng. `GroupedOpenApi` thuộc package `org.springdoc.core.models` trong springdoc 2.x.

Với chính sách dùng chung cho mọi group, hãy cân nhắc `GlobalOpenApiCustomizer` hoặc `GlobalOperationCustomizer` theo phiên bản springdoc. Cần phân biệt:

- `OpenApiCustomizer`: customizer cấp tài liệu mặc định; phạm vi group cần xác minh theo phiên bản.
- `GlobalOpenApiCustomizer`: dành cho thay đổi toàn tài liệu cần áp dụng cả các group theo hỗ trợ của springdoc.
- `GroupedOpenApi.builder().addOpenApiCustomizer(...)`: gắn customizer riêng vào một group cụ thể.

Không đăng ký cùng một thay đổi ở cả global customizer và group customizer nếu không có kiểm tra idempotent. Nếu cả hai cùng thêm server hoặc response, kết quả có thể bị trùng hoặc bị ghi đè.

### Tránh group customizer xóa kết quả global

Giả sử global customizer thêm hai server, còn customizer của public group gọi `setServers(List.of(publicServer))`. Kết quả của group có thể chỉ còn một server. Nếu mục tiêu chỉ là thêm server public, hãy upsert theo URL; nếu mục tiêu là thay toàn bộ danh sách, ghi rõ đó là chính sách sở hữu server của group.

Thứ tự giữa customizer toàn cục và customizer gắn group phụ thuộc pipeline của phiên bản springdoc. Nếu kết quả group cần một thứ tự cụ thể, hãy kiểm tra endpoint `/v3/api-docs/{group}` bằng integration test thay vì dựa vào giả định.

## 10. Kiểm thử thứ tự và kết quả cuối cùng

Nên kiểm thử ở hai mức:

1. Unit test cho logic biến đổi một đối tượng OpenAPI nhỏ.
2. Integration test gọi endpoint `/v3/api-docs` để xác minh springdoc đã áp dụng customizer đúng trong application context thật.

### Unit test cho customizer

~~~java
class DocumentCustomizerTest {

    @Test
    void fillsMissingInfoWithoutReplacingExistingDescription() {
        OpenAPI openApi = new OpenAPI()
            .info(new Info().description("Mô tả hiện có"));

        OpenApiCustomizer customizer = openApiDocument -> {
            if (openApiDocument.getInfo() == null) {
                openApiDocument.setInfo(new Info());
            }
            Info info = openApiDocument.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Catalog API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };

        customizer.customise(openApi);
        customizer.customise(openApi);

        assertEquals("Catalog API", openApi.getInfo().getTitle());
        assertEquals("1.0", openApi.getInfo().getVersion());
        assertEquals("Mô tả hiện có", openApi.getInfo().getDescription());
    }
}
~~~

Test gọi customizer hai lần để xác minh tính idempotent và đồng thời bảo đảm description cũ được giữ lại. Ví dụ giả định có các import JUnit, `assertEquals`, `OpenAPI`, `Info` và `OpenApiCustomizer`. Nếu dự án dùng phiên bản interface có callback tên khác, thay lời gọi theo đúng API dependency.

### Integration test cho OpenAPI cuối cùng

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiCustomizationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void appliesDocumentCustomizersInExpectedOrder() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Catalog API"))
            .andExpect(jsonPath("$.info.version").value("1.0"))
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com"));
    }
}
~~~

Các giá trị trong assertion phải khớp cấu hình test của ứng dụng. Ví dụ giả định có import `SpringBootTest`, `AutoConfigureMockMvc`, `Autowired`, `MockMvc`, `Test`, các request/result matcher và `get`. Nếu server URL được lấy từ profile hoặc property, hãy đặt giá trị test rõ ràng để kết quả không phụ thuộc môi trường chạy.

### Kiểm tra response không bị ghi đè

Nếu một customizer bổ sung response `429`, hãy kiểm tra:

- Response `200` ban đầu vẫn còn.
- Response `400` do controller khai báo vẫn còn.
- Response `429` có description/content mong muốn.
- Nếu response `429` đã được khai báo riêng, chính sách giữ nguyên hay thay thế hoạt động đúng.

Không chỉ kiểm tra rằng key `429` tồn tại; hãy kiểm tra cả schema, media type, header và description nếu các trường đó thuộc hợp đồng.

### Kiểm tra mọi group

Nếu ứng dụng có group, test endpoint riêng:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Public API"));

mockMvc.perform(get("/v3/api-docs/admin"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Admin API"));
~~~

Đảm bảo customizer chung áp dụng đúng cho cả hai group và customizer riêng không làm mất metadata chung.

## 11. Chẩn đoán khi thứ tự hoặc kết quả không đúng

Khi OpenAPI JSON không như mong đợi, hãy lần theo dữ liệu từ nguồn đến kết quả:

1. Kiểm tra annotation trên controller và kiểu trả về có tạo ra operation/response ban đầu đúng không.
2. Xác nhận customizer bean có được đăng ký trong application context và điều kiện profile/property có thỏa mãn không.
3. Xác định customizer thuộc pipeline nào: operation, document mặc định, global hay group cụ thể.
4. Tìm tất cả nơi gọi setter hoặc ghi cùng key vào map/list đang bị mất dữ liệu.
5. Kiểm tra `@Order` có được áp dụng trong đúng collection và có giá trị khác nhau không.
6. Gọi đúng endpoint tài liệu mặc định hoặc endpoint group.
7. Kiểm tra kết quả sau khi khởi động lại hoặc sau khi làm mới cache tài liệu.

### Triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Title hoặc version biến mất | Customizer khác gọi `setInfo(new Info())` sau đó | Tìm mọi chỗ gọi `setInfo` và kiểm tra thứ tự |
| Server URL không còn | Customizer sau gọi `setServers` | Tìm nơi thay toàn bộ danh sách server |
| Response lỗi bị mất | Customizer thay `ApiResponses` hoặc ghi cùng status code | Kiểm tra map responses trước và sau mỗi bước |
| Có tag/server/parameter trùng | Customizer append mà không kiểm tra trước | Kiểm tra idempotency và khóa nhận diện |
| Security scheme có nhưng operation không yêu cầu | Scheme chỉ được thêm vào components, chưa có security requirement phù hợp | Kiểm tra root và operation security |
| Customizer chạy với tài liệu mặc định nhưng không chạy ở group | Dùng customizer không có phạm vi group | Dùng global hoặc gắn customizer vào GroupedOpenApi |
| `@Order` không tạo thứ tự mong muốn | Các bean thuộc pipeline khác nhau hoặc order trùng | Kiểm tra loại customizer và đặt order riêng biệt |
| Thay đổi code nhưng JSON vẫn cũ | Tài liệu đang được cache hoặc gọi nhầm group/instance | Khởi động lại, kiểm tra cache và endpoint |
| Schema hoặc `$ref` không đúng | Hai customizer dùng cùng component name | Kiểm tra `components.schemas` và mọi `$ref` |

### Kiểm tra cache tài liệu

springdoc có thể cache tài liệu được sinh để tránh phân tích controller lặp lại. Khi đang chẩn đoán thay đổi customizer, hãy khởi động lại ứng dụng và gọi lại endpoint tài liệu. Có thể tạm tắt cache bằng cấu hình:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Chỉ dùng cấu hình này khi cần chẩn đoán hoặc khi có lý do vận hành rõ ràng. Cache bị tắt có thể làm tăng chi phí tạo tài liệu; không nên đưa cấu hình debug vào production mà chưa đánh giá tác động.

### Tìm mọi nơi ghi cùng property

Khi một property bị ghi đè, tìm kiếm toàn bộ mã nguồn theo các setter liên quan, ví dụ:

~~~text
setInfo(
setServers(
setResponses(
setSecurity(
setTags(
setSchemas(
setExtensions(
~~~

Sau đó lập bảng thứ tự và nguồn ghi. Với customizer có điều kiện, kiểm tra cả profile, property và group để biết nhánh nào thực sự được thực thi. Đừng chỉ nhìn vào thứ tự khai báo các method `@Bean`; thứ tự callback phải được xác minh trong pipeline.

## 12. Những quy tắc an toàn khi sửa OpenAPI model

Trước khi thay đổi model, áp dụng các quy tắc sau:

- Kiểm tra null trước khi truy cập object con như `info`, `servers`, `paths`, `responses` hoặc `components`.
- Với list, kiểm tra phần tử trùng theo khóa nghiệp vụ thay vì chỉ so sánh object identity.
- Với map, nhớ rằng ghi cùng key sẽ thay giá trị cũ.
- Khi cần thay một property, sửa property đó thay vì tạo lại toàn bộ object cha.
- Khi cần thay cả collection, xác định rõ customizer sở hữu collection và dữ liệu nào được phép bị loại.
- Không chia sẻ cùng một mutable model giữa các group.
- Không sửa response hoặc schema đã có mà không kiểm tra annotation của controller và các customizer khác.
- Dùng tên extension bắt đầu bằng `x-` và có namespace riêng để tránh đụng key.

### Bảo toàn dữ liệu hiện hữu

Ví dụ helper thêm tag nếu chưa có:

~~~java
private void addTagIfMissing(OpenAPI openApi, String name, String description) {
    if (openApi.getTags() == null) {
        openApi.setTags(new ArrayList<>());
    }

    boolean exists = openApi.getTags().stream()
        .anyMatch(tag -> name.equals(tag.getName()));

    if (!exists) {
        openApi.addTagsItem(
            new Tag().name(name).description(description)
        );
    }
}
~~~

Helper này dùng tên tag làm khóa. Nếu tag đã tồn tại nhưng description cần được cập nhật, hãy viết chính sách riêng thay vì thêm tag thứ hai cùng tên.

Ví dụ thêm parameter nếu chưa có:

~~~java
private void addHeaderIfMissing(Operation operation, Parameter header) {
    if (operation.getParameters() == null) {
        operation.setParameters(new ArrayList<>());
    }

    boolean exists = operation.getParameters().stream()
        .anyMatch(existing ->
            Objects.equals(header.getName(), existing.getName())
                && Objects.equals(header.getIn(), existing.getIn())
        );

    if (!exists) {
        operation.addParametersItem(header);
    }
}
~~~

Parameter được nhận diện bằng cặp `name` và `in`, vì cùng một tên có thể xuất hiện ở query, header, path hoặc cookie. Ví dụ dùng `Objects.equals` để so sánh an toàn khi một giá trị chưa được gán; cần import `java.util.Objects`. Nếu parameter đã tồn tại ở path level, cần cân nhắc cả path-level parameter trước khi thêm operation-level parameter.

## 13. Bài thực hành tổng hợp

Xây dựng một ứng dụng Spring Boot có tài liệu mặc định và hai group `public` cùng `admin`. Tạo các customizer sau:

1. Metadata customizer điền title và version nếu còn thiếu.
2. Server customizer thêm URL theo cấu hình môi trường và không tạo bản sao.
3. Security customizer bổ sung security scheme dùng chung, giữ nguyên scheme hiện có.
4. Response customizer thêm response `429` nếu operation chưa có.
5. Operation customizer thêm extension `x-owner` từ metadata của handler method.
6. Group customizer đặt title riêng cho public và admin.
7. Đặt order khác nhau cho các customizer cùng pipeline và ghi lại lý do thứ tự.
8. Tạo một customizer thử nghiệm gọi `setInfo(new Info())` để quan sát metadata bị mất, sau đó sửa bằng cách cập nhật property riêng.
9. Gọi `/v3/api-docs`, `/v3/api-docs/public` và `/v3/api-docs/admin` để so sánh phạm vi.
10. Gọi customizer nhiều lần trong unit test để kiểm tra không sinh server/tag/response trùng.
11. Viết integration test xác nhận title, server, security, response và extension cuối cùng.
12. Tạm tắt cache nếu cần chẩn đoán và xác nhận lại output sau khi bật cache.

### Tiêu chí hoàn thành

- [ ] Phân biệt được operation customizer và document customizer.
- [ ] Biết customizer nào áp dụng cho tài liệu mặc định, global và từng group.
- [ ] Dùng `@Order`/`Ordered` trong đúng pipeline và không nhầm với thứ tự khởi tạo bean.
- [ ] Chứng minh được setter thay thế dữ liệu hiện có và helper `add` có thể gây trùng hoặc ghi cùng key.
- [ ] Bảo toàn metadata bằng cách cập nhật property cụ thể.
- [ ] Response, security, tag, server và schema không bị ghi đè ngoài ý muốn.
- [ ] Customizer có tính idempotent và không giữ mutable state giữa các lần gọi.
- [ ] OpenAPI JSON của mọi group có nội dung đúng.
- [ ] Integration test phát hiện được thay đổi thứ tự hoặc xung đột customizer.

## Tiếp tục học

Sau bài này, hãy kết hợp customizer với schema converter, operation filter, grouped documentation và kiểm thử hợp đồng. Khi thêm customizer mới, hãy ghi rõ extension point, phạm vi group, thứ tự, dữ liệu được sở hữu và quy tắc khi key đã tồn tại. Điều đó giúp tài liệu OpenAPI có kết quả dự đoán được khi ứng dụng phát triển.
