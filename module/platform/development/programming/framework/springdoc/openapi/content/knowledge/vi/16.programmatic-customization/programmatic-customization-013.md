# Tính lặp lại an toàn và tránh nhân đôi dữ liệu khi tài liệu được xây lại

Ứng dụng Spring Boot có thể bổ sung metadata OpenAPI bằng annotation, OpenApiCustomizer hoặc GlobalOpenApiCustomizer. Các customizer thường thêm server, tag, security scheme, response mặc định, header hoặc extension vào mô hình OpenAPI mà springdoc tạo từ controller. Khi tài liệu được tạo lại, được sinh cho nhiều document group hoặc được xử lý nhiều lần trong cùng một quy trình, thao tác bổ sung không kiểm soát có thể tạo phần tử trùng lặp hoặc ghi đè metadata đã có.

Vì vậy, logic tùy biến cần có tính **idempotent**: áp dụng cùng một customizer nhiều lần lên cùng một mô hình phải cho kết quả tương đương với việc chỉ áp dụng một lần. Tính chất này giúp tài liệu ổn định khi khởi động lại ứng dụng, làm mới tài liệu, chạy kiểm thử, xuất đặc tả trong CI hoặc bổ sung group mới.

## 1. Idempotency trong quá trình xây dựng OpenAPI

Một thao tác idempotent có thể được lặp lại mà không làm thay đổi kết quả sau lần đầu. Với customizer, có thể biểu diễn:

\[
F(F(D)) = F(D)
\]

Trong đó:

- D là mô hình OpenAPI được springdoc tạo.
- F là hàm tùy biến.
- F(D) là tài liệu sau khi áp dụng customizer một lần.
- F(F(D)) là tài liệu sau khi áp dụng lại customizer trên kết quả trước đó.

Hai kết quả cần tương đương về nội dung hợp đồng: không phát sinh thêm server, tag, parameter, response hoặc operation chỉ vì customizer được chạy lại.

Ví dụ, nếu customizer luôn gọi addServersItem(...), mỗi lần chạy có thể thêm một server giống server cũ. Nếu luôn gọi addParametersItem(...), một operation có thể nhận nhiều bản sao của cùng header. Ngược lại, nếu kiểm tra phần tử đã tồn tại theo một khóa ổn định rồi mới thêm, thao tác có thể lặp lại an toàn.

Tính idempotent cần được thiết kế trong chính logic tùy biến. Không nên dựa vào giả định rằng springdoc chỉ gọi customizer đúng một lần trong toàn bộ vòng đời ứng dụng. Việc tạo tài liệu, cache, document group và kiểm thử có thể khiến cùng logic được thực thi trong nhiều ngữ cảnh.

## 2. Những vị trí dễ phát sinh dữ liệu trùng

Một số thành phần OpenAPI có cấu trúc danh sách, số khác là map hoặc tập hợp. Cách tránh trùng phụ thuộc vào cấu trúc và định danh của thành phần:

| Thành phần | Thao tác dễ gây trùng | Khóa nhận diện nên dùng |
| --- | --- | --- |
| servers | Luôn thêm server mới | URL server |
| tags cấp tài liệu | Luôn thêm tag mới | Tên tag |
| tags của operation | Luôn thêm chuỗi tag | Tên tag |
| parameters | Thêm lại header hoặc query parameter | Cặp in + name |
| responses | Bổ sung response mặc định nhiều lần | Mã trạng thái |
| security | Thêm lại security requirement | Tên scheme và scopes |
| components.schemas | Tạo component cùng tên nhiều lần | Tên schema |
| components.securitySchemes | Đăng ký lại scheme | Tên scheme |
| paths và operation | Tạo lại path/method đã tồn tại | Path + HTTP method |
| Extensions | Ghi nhiều giá trị cho cùng một ý nghĩa | Tên extension |

Các cấu trúc dạng map như responses hoặc components.schemas thường có khóa duy nhất trong model, nhưng vẫn có thể bị ghi đè ngoài ý muốn nếu customizer dùng put không đúng phạm vi. Các cấu trúc danh sách như servers, tags, parameters và security cần được kiểm tra kỹ hơn vì thao tác append có thể tạo phần tử lặp.

## 3. Quy tắc thiết kế customizer có thể chạy lặp

Một customizer ổn định nên tuân theo các nguyên tắc sau:

1. **Xác định khóa tự nhiên của phần tử.** Ví dụ parameter được nhận diện bằng vị trí in và tên name; server được nhận diện bằng URL.
2. **Kiểm tra trước khi thêm.** Nếu phần tử đã tồn tại, không append bản sao.
3. **Cập nhật có chủ đích.** Nếu customizer sở hữu metadata đó, thay giá trị hiện tại bằng giá trị chuẩn; nếu không sở hữu, giữ metadata do annotation hoặc controller khai báo.
4. **Dùng thao tác upsert.** Tạo mới khi chưa có, cập nhật khi đã có, và giữ số lượng phần tử ổn định.
5. **Không lưu trạng thái thay đổi trong biến mutable dùng chung.** Mỗi lần chạy phải dựa trên OpenAPI model và cấu hình hiện tại.
6. **Giữ thứ tự ổn định.** Khi tạo danh sách, dùng thứ tự xác định để tài liệu không thay đổi chỉ vì thứ tự duyệt không ổn định.
7. **Không tạo dữ liệu ngẫu nhiên hoặc phụ thuộc thời điểm.** Tránh timestamp hiện tại, UUID ngẫu nhiên hoặc kết quả gọi dịch vụ ngoài nếu chúng không phải một phần hợp đồng cố định.
8. **Không thay thế operation có sẵn một cách mù quáng.** Chỉ thêm operation mới khi path và HTTP method chưa tồn tại; nếu đã có, cập nhật đúng phần mà customizer chịu trách nhiệm.

Một cách phân biệt hữu ích:

- **ensure:** bảo đảm phần tử có tồn tại, nếu đã có thì giữ hoặc chuẩn hóa nó.
- **upsert:** tạo mới hoặc cập nhật phần tử theo khóa.
- **replace:** thay toàn bộ giá trị do customizer sở hữu.
- **append:** thêm vào cuối danh sách, chỉ dùng khi phần tử thực sự có tính lặp và việc thêm nhiều lần là có chủ đích.

Với metadata OpenAPI, append thường cần điều kiện kiểm tra trước.

## 4. Ví dụ customizer thêm tag, server và response một cách idempotent

Ví dụ dưới đây minh họa ba thao tác thường gặp:

- Bảo đảm tài liệu có tag Orders, chỉ giữ một tag cùng tên.
- Bảo đảm có server https://api.example.com, không thêm bản sao.
- Bổ sung response 429 cho operation thuộc /api/orders, nhưng không ghi đè response đã được controller khai báo.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.Server;
import io.swagger.v3.oas.models.tags.Tag;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StableOpenApiConfiguration {

    @Bean
    OpenApiCustomizer stableOpenApiCustomizer() {
        return StableOpenApiConfiguration::apply;
    }

    static void apply(OpenAPI openApi) {
        ensureTag(openApi, "Orders", "Các API quản lý đơn hàng");
        ensureServer(
            openApi,
            "https://api.example.com",
            "API server chính thức"
        );

        if (openApi.getPaths() == null) {
            return;
        }

        openApi.getPaths().forEach((path, pathItem) -> {
            if (!isOrderPath(path) || pathItem == null) {
                return;
            }

            for (Operation operation : pathItem.readOperations()) {
                ensureOperationTag(operation, "Orders");
                ensureRateLimitResponse(operation);
            }
        });
    }

    private static boolean isOrderPath(String path) {
        return "/api/orders".equals(path)
            || path.startsWith("/api/orders/");
    }

    private static void ensureTag(
            OpenAPI openApi,
            String name,
            String description
    ) {
        List<Tag> existing = openApi.getTags() == null
            ? new ArrayList<>()
            : openApi.getTags();

        Map<String, Tag> unique = new LinkedHashMap<>();
        for (Tag tag : existing) {
            if (tag != null && tag.getName() != null) {
                unique.putIfAbsent(tag.getName(), tag);
            }
        }

        Tag target = unique.get(name);
        if (target == null) {
            unique.put(name, new Tag().name(name).description(description));
        } else {
            // Customizer sở hữu description của tag Orders.
            target.setDescription(description);
        }

        openApi.setTags(new ArrayList<>(unique.values()));
    }

    private static void ensureServer(
            OpenAPI openApi,
            String url,
            String description
    ) {
        List<Server> existing = openApi.getServers() == null
            ? new ArrayList<>()
            : openApi.getServers();

        Map<String, Server> unique = new LinkedHashMap<>();
        for (Server server : existing) {
            if (server != null && server.getUrl() != null) {
                unique.putIfAbsent(server.getUrl(), server);
            }
        }

        Server target = unique.get(url);
        if (target == null) {
            unique.put(url, new Server().url(url).description(description));
        } else {
            // Chuẩn hóa mô tả của server do customizer quản lý.
            target.setDescription(description);
        }

        openApi.setServers(new ArrayList<>(unique.values()));
    }

    private static void ensureOperationTag(
            Operation operation,
            String tag
    ) {
        List<String> existing = operation.getTags() == null
            ? new ArrayList<>()
            : operation.getTags();

        Set<String> unique = new LinkedHashSet<>(existing);
        unique.add(tag);
        operation.setTags(new ArrayList<>(unique));
    }

    private static void ensureRateLimitResponse(Operation operation) {
        ApiResponses responses = operation.getResponses();
        if (responses == null) {
            responses = new ApiResponses();
            operation.setResponses(responses);
        }

        // Giữ response 429 do controller khai báo nếu đã tồn tại.
        responses.putIfAbsent(
            "429",
            new ApiResponse().description("Vượt quá giới hạn request")
        );
    }
}
~~~

Điểm quan trọng của ví dụ:

- Tag và server được gom theo khóa trước khi gán lại danh sách, vì vậy phần tử trùng cũ cũng được loại bỏ.
- Tag của operation được gom bằng LinkedHashSet, vừa giữ thứ tự vừa loại chuỗi trùng.
- Response 429 dùng putIfAbsent, do đó customizer không thay thế response chi tiết đã khai báo ở controller.
- Mỗi object model mới được tạo trong lần chạy, không dùng chung một instance mutable cho nhiều operation.
- Customizer không giữ bộ đếm hoặc danh sách thay đổi trong field static.

Trong ứng dụng thực tế, chỉ nên chuẩn hóa những tag/server mà customizer sở hữu. Ví dụ trên xem URL là khóa nhận diện server. Nếu tài liệu dùng server URL dạng template và các biến server tạo ra những đích khác nhau, khóa cần bao gồm cả URL lẫn định nghĩa variables; không gộp hai server chỉ vì chuỗi URL template giống nhau.

## 5. Upsert parameter theo cặp vị trí và tên

Parameter trong OpenAPI có thể nằm ở path, query, header hoặc cookie. Hai parameter có cùng tên nhưng khác in là hai parameter khác nhau. Vì vậy, khóa nhận diện cần là cặp:

\[
(\text{in}, \text{name})
\]

Ví dụ customizer muốn bảo đảm header X-Request-Id có trong một operation:

~~~java
import java.util.ArrayList;
import java.util.List;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;

static void ensureRequestIdHeader(Operation operation) {
    List<Parameter> parameters = operation.getParameters() == null
        ? new ArrayList<>()
        : new ArrayList<>(operation.getParameters());

    Parameter existing = parameters.stream()
        .filter(parameter -> "header".equals(parameter.getIn()))
        .filter(parameter -> "X-Request-Id".equals(parameter.getName()))
        .findFirst()
        .orElse(null);

    if (existing == null) {
        parameters.add(
            new Parameter()
                .name("X-Request-Id")
                .in("header")
                .required(false)
                .description("Mã tương quan request do client gửi")
                .schema(new io.swagger.v3.oas.models.media.StringSchema())
        );
    }

    // Chỉ gán lại danh sách sau khi xác định parameter còn thiếu.
    operation.setParameters(parameters);
}
~~~

Ví dụ chỉ thêm header nếu chưa có. Nếu cần chuẩn hóa description hoặc schema của parameter đã tồn tại, hãy cập nhật đúng parameter đó thay vì thêm một bản sao. Không xóa hoặc thay thế parameter cùng tên nhưng khác vị trí.

OpenAPI còn cho phép parameter được khai báo ở Path Item và được operation kế thừa. Khi kiểm tra trùng, cần xem cả parameter ở cấp path và operation. Một parameter ở operation có cùng name và in với parameter cấp path có thể ghi đè theo quy tắc OpenAPI; không nên vô tình tạo thêm bản trùng ở cả hai cấp.

## 6. Tránh ghi đè metadata đã có

Customizer thường chạy sau khi springdoc đã đọc controller annotation và xây dựng model. Nếu customizer gán lại toàn bộ danh sách hoặc map, có thể xóa mất thông tin do controller khai báo.

Ví dụ không an toàn:

~~~java
operation.setResponses(new ApiResponses()
    .addApiResponse("200", new ApiResponse().description("OK")));
~~~

Đoạn code trên thay toàn bộ response hiện tại bằng một map mới. Các response 400, 404, 409 hoặc 500 được khai báo trước đó có thể biến mất.

Nếu chỉ muốn bổ sung response mặc định:

~~~java
operation.getResponses().putIfAbsent(
    "429",
    new ApiResponse().description("Vượt quá giới hạn request")
);
~~~

Nếu customizer chịu trách nhiệm hoàn toàn cho một response cụ thể và cần chuẩn hóa nội dung của nó, có thể dùng put cho đúng status code đó. Không thay cả collection khi chỉ cần cập nhật một entry.

Tương tự:

- Dùng putIfAbsent hoặc put theo quyền sở hữu cho schema component.
- Tìm parameter theo (in, name) trước khi thêm.
- Tìm tag theo name trước khi cập nhật.
- Tìm server theo URL trước khi bổ sung.
- Không thay operationId đã ổn định nếu customizer không sở hữu quy tắc định danh operation.

## 7. Components và tham chiếu cần tên ổn định

components.schemas, components.parameters, components.responses, components.examples và components.securitySchemes được định danh bằng key. Khi thêm component từ customizer, dùng tên ổn định và tránh tạo tên phụ thuộc thời gian hoặc thứ tự chạy.

Ví dụ:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.StringSchema;
import java.util.LinkedHashMap;

static void ensureCorrelationIdSchema(OpenAPI openApi) {
    if (openApi.getComponents() == null) {
        openApi.setComponents(new Components());
    }

    if (openApi.getComponents().getSchemas() == null) {
        openApi.getComponents().setSchemas(new LinkedHashMap<>());
    }

    openApi.getComponents().getSchemas().putIfAbsent(
        "CorrelationId",
        new StringSchema()
            .description("Mã tương quan của request")
            .example("req-1001")
    );
}
~~~

Tên component CorrelationId được giữ cố định. Khi customizer chạy lại, putIfAbsent không tạo component khác. Các operation có thể tham chiếu đến cùng component bằng $ref.

Nếu cần cập nhật schema đã tồn tại, chỉ dùng put khi customizer có quyền sở hữu component đó. Nếu component có thể do annotation hoặc một customizer khác tạo, hãy thống nhất tên và trách nhiệm trước khi thay đổi. Hai customizer cùng ghi một key nhưng kỳ vọng khác nhau sẽ tạo ra kết quả phụ thuộc thứ tự thực thi.

## 8. Tránh nhân đôi security requirement và extension

Security requirement được biểu diễn dưới dạng danh sách. Việc gọi addSecurityItem(...) vô điều kiện có thể tạo các requirement lặp. Hãy kiểm tra scheme và scopes trước khi thêm:

~~~java
import java.util.ArrayList;
import java.util.List;

import io.swagger.v3.oas.models.security.SecurityRequirement;

static void ensureBearerRequirement(Operation operation) {
    String scheme = "bearerAuth";

    List<SecurityRequirement> requirements =
        operation.getSecurity() == null
            ? new ArrayList<>()
            : new ArrayList<>(operation.getSecurity());

    boolean exists = requirements.stream()
        .anyMatch(requirement -> requirement.containsKey(scheme));

    if (!exists) {
        requirements.add(new SecurityRequirement().addList(scheme));
    }

    operation.setSecurity(requirements);
}
~~~

Nếu scheme có scopes, khóa so sánh cần bao gồm cả tên scheme và danh sách scopes. Không chỉ so sánh tên scheme nếu hai requirement có ngữ nghĩa khác nhau.

Với extension x-..., mô hình OpenAPI lưu theo key. Dùng cùng một key và cập nhật giá trị có chủ đích:

~~~java
openApi.addExtension("x-build-source", "springdoc-customizer");
~~~

Không tạo key mới ở mỗi lần chạy như x-build-source-1, x-build-source-2. Extension là metadata bổ sung của hợp đồng; tên key nên ổn định và có ý nghĩa.

## 9. Không dùng trạng thái mutable dùng chung giữa các lần gọi

Một lỗi khó phát hiện là customizer giữ danh sách hoặc object model ở field rồi tiếp tục thêm phần tử khi callback chạy lại:

~~~java
// Không nên dùng cách này.
private final List<Tag> generatedTags = new ArrayList<>();

OpenApiCustomizer customizer() {
    return openApi -> {
        generatedTags.add(new Tag().name("Orders"));
        openApi.setTags(generatedTags);
    };
}
~~~

Danh sách generatedTags sống lâu hơn một lần xây dựng tài liệu. Mỗi lần callback chạy lại, nó giữ dữ liệu cũ và tiếp tục tăng kích thước. Nếu nhiều group hoặc thread cùng dùng object này, còn có thể phát sinh chia sẻ trạng thái ngoài ý muốn.

Hãy tạo dữ liệu ngay trong lần áp dụng customizer:

~~~java
OpenApiCustomizer customizer() {
    return openApi -> {
        ensureTag(openApi, "Orders", "Các API quản lý đơn hàng");
    };
}
~~~

Các giá trị cấu hình bất biến như tên tag, URL server hoặc mô tả có thể được giữ ở hằng số. Những object model như Tag, Server, ApiResponse, Parameter nên được tạo hoặc tìm trong từng OpenAPI model, không dùng một instance mutable chung cho nhiều tài liệu.

## 10. Tính xác định khi xây lại tài liệu

Idempotency tập trung vào việc lặp lại cùng một biến đổi trên cùng một trạng thái. Tính xác định còn yêu cầu cùng đầu vào và cùng cấu hình phải tạo ra cùng nội dung đầu ra.

Tránh đưa các giá trị sau vào tài liệu nếu không có lý do hợp đồng:

- Thời gian hiện tại được lấy mỗi lần customizer chạy.
- UUID ngẫu nhiên cho operationId hoặc component name.
- Giá trị tăng dần từ bộ đếm trong bộ nhớ.
- Kết quả của API ngoài có thể thay đổi giữa các lần xây dựng.
- Thứ tự collection phụ thuộc vào HashMap hoặc nguồn dữ liệu không ổn định.

Nếu tài liệu cần thể hiện phiên bản build, lấy giá trị cố định từ cấu hình build hoặc metadata artifact. Không gọi hệ thống bên ngoài trong customizer để tạo nội dung mà lẽ ra có thể xác định từ cấu hình ứng dụng.

Một pipeline sinh tài liệu ổn định thường có dạng:

~~~text
Controller + DTO + annotation
              |
              v
        Springdoc tạo model
              |
              v
       Áp dụng customizer
              |
              v
  Upsert metadata theo khóa ổn định
              |
              v
     Serialize OpenAPI JSON/YAML
              |
              v
      So sánh và kiểm tra hợp đồng
~~~

Khi chạy lại, cùng model và cùng cấu hình phải cho ra cùng metadata, không tăng số lượng phần tử chỉ vì pipeline được thực hiện thêm lần nữa.

## 11. Phạm vi áp dụng cho tài liệu mặc định và document group

Một ứng dụng có thể tạo tài liệu mặc định và nhiều group. Cùng một customizer có thể được áp dụng trong nhiều phạm vi tùy loại bean và cách cấu hình springdoc.

Hãy xác định rõ:

- Metadata nào dùng chung cho mọi group, ví dụ thông tin liên hệ hoặc server nền.
- Metadata nào chỉ thuộc một group, ví dụ tag hoặc response riêng cho API quản trị.
- Customizer nào áp dụng cho tài liệu mặc định.
- Customizer nào cần áp dụng cho mọi group.

Nếu một tag hoặc server được thêm vào từng group, mỗi tài liệu cần độc lập và không chứa bản sao. Không dùng một OpenAPI model dùng chung rồi sửa nối tiếp cho nhiều group nếu không có cơ chế tạo bản sao và cô lập rõ ràng.

Khi group có customizer riêng, kiểm tra cùng logic trên từng endpoint tài liệu như /v3/api-docs, /v3/api-docs/customer-api và /v3/api-docs/admin-api. Một group có thể có controller và metadata khác group còn lại; không giả định kết quả của tài liệu mặc định đại diện cho tất cả.

## 12. Kiểm thử customizer chạy nhiều lần

Một kiểm thử trực tiếp có thể áp dụng cùng hàm tùy biến hai lần lên cùng một OpenAPI model và so sánh kết quả:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.Paths;
import io.swagger.v3.oas.models.responses.ApiResponses;
import org.junit.jupiter.api.Test;

class StableOpenApiConfigurationTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void applyingCustomizerTwiceProducesSameDocument() throws Exception {
        OpenAPI openApi = new OpenAPI();

        Paths paths = new Paths();
        paths.addPathItem(
            "/api/orders",
            new PathItem().get(
                new Operation()
                    .operationId("listOrders")
                    .responses(new ApiResponses())
            )
        );
        openApi.setPaths(paths);

        StableOpenApiConfiguration.apply(openApi);
        String afterFirstRun = objectMapper.writeValueAsString(openApi);

        StableOpenApiConfiguration.apply(openApi);
        String afterSecondRun = objectMapper.writeValueAsString(openApi);

        assertThat(afterSecondRun).isEqualTo(afterFirstRun);
        assertThat(openApi.getTags())
            .extracting("name")
            .containsExactly("Orders");
        assertThat(openApi.getServers())
            .extracting("url")
            .containsExactly("https://api.example.com");
        assertThat(openApi.getPaths()
            .get("/api/orders")
            .getGet()
            .getResponses()).containsKey("429");
    }
}
~~~

Kiểm thử này xác nhận:

- Nội dung JSON sau lần chạy thứ hai bằng lần chạy thứ nhất.
- Danh sách tag chỉ có một tag Orders.
- Danh sách server chỉ có một URL server đã định nghĩa.
- Response 429 đã tồn tại và không được thêm nhiều lần.

Nếu tài liệu chứa collection mà thứ tự không mang ý nghĩa, có thể chuẩn hóa thứ tự trước khi so sánh. Tuy nhiên, giữ thứ tự ổn định ngay từ customizer giúp diff dễ đọc và phát hiện thay đổi hợp đồng thực sự.

### Kiểm tra endpoint tài liệu sau nhiều request

Ngoài kiểm thử hàm, có thể gọi endpoint OpenAPI nhiều lần trong kiểm thử tích hợp. Đoạn dưới đây là một phương thức trong test class đã inject MockMvc và ObjectMapper:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentRepeatRequestTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void repeatedApiDocsRequestsDoNotDuplicateTags() throws Exception {
        String first = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        String second = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode firstDocument = objectMapper.readTree(first);
        JsonNode secondDocument = objectMapper.readTree(second);

        assertThat(secondDocument.path("tags").size())
            .isEqualTo(firstDocument.path("tags").size());
    }
}
~~~

Đây là kiểm tra bổ sung ở HTTP layer. Nếu springdoc cache tài liệu, hai request có thể trả cùng kết quả đã cache mà không thực thi customizer lần nữa. Vì vậy, kiểm thử gọi endpoint nhiều lần không thay thế kiểm thử trực tiếp áp dụng customizer hai lần trên cùng model.

## 13. So sánh đặc tả sau khi xây dựng

Trong CI, có thể lưu OpenAPI JSON/YAML làm artifact rồi so sánh với phiên bản đã phát hành. Khi tài liệu được xây lại, diff cần giúp phân biệt:

- Thay đổi hợp đồng có chủ đích: thêm response, thay schema, thêm operation.
- Thay đổi metadata: description, tag, server hoặc security.
- Thay đổi ngoài ý muốn: tag lặp, server lặp, parameter lặp, operationId thay đổi hoặc component trùng.

Nên chuẩn hóa các phần không có ý nghĩa thứ tự trước khi so sánh nếu công cụ diff coi thứ tự danh sách là khác biệt. Tuy nhiên, không xóa mọi khác biệt bằng bước chuẩn hóa quá mạnh; việc đó có thể che thay đổi hợp đồng thực sự.

Một số kiểm tra tự động hữu ích:

1. Tên tag không bị lặp.
2. URL server không bị lặp.
3. Mỗi operation không có hai parameter trùng cặp in + name.
4. Mỗi operationId duy nhất trong một tài liệu.
5. Security requirement không bị nhân đôi.
6. Tên schema và security scheme ổn định.
7. Hai lần sinh tài liệu với cùng commit và cấu hình cho nội dung tương đương.

## 14. Lỗi thường gặp

**Mỗi lần gọi /v3/api-docs lại có thêm server.** Customizer đang append server không kiểm tra. Dùng upsert theo URL và loại bản sao đã tồn tại.

**Header xuất hiện nhiều lần trong Swagger UI.** Kiểm tra addParametersItem(...) và dùng khóa (in, name) để chỉ có một parameter trong đúng phạm vi.

**Response mặc định làm mất response controller đã khai báo.** Kiểm tra customizer có gọi setResponses(new ApiResponses()) hay không. Bổ sung một status bằng putIfAbsent hoặc cập nhật riêng entry do customizer sở hữu.

**Tag toàn cục bị lặp.** Gom danh sách theo Tag.name, giữ thứ tự ổn định và cập nhật mô tả trên tag hiện có.

**Một group có metadata của group khác.** Kiểm tra customizer đang áp dụng ở phạm vi mặc định hay global, và tránh dùng chung mutable OpenAPI model giữa các group.

**Kết quả thay đổi sau mỗi lần khởi động.** Tìm timestamp, UUID ngẫu nhiên, bộ đếm hoặc dữ liệu ngoài trong customizer. Chuyển sang cấu hình cố định và hàm biến đổi xác định.

**Kiểm thử endpoint nhiều lần vẫn không phát hiện lỗi.** Tài liệu có thể được cache. Bổ sung unit test gọi trực tiếp logic customizer nhiều lần trên cùng OpenAPI model.

**Hai customizer ghi cùng một component.** Thống nhất quyền sở hữu component và thứ tự áp dụng. Dùng tên ổn định, tránh hai customizer cùng cập nhật một key với nội dung khác nhau.

## 15. Checklist cho customizer idempotent

- [ ] Xác định thành phần nào customizer được quyền tạo hoặc cập nhật.
- [ ] Chọn khóa nhận diện ổn định cho tag, server, parameter, response và component.
- [ ] Kiểm tra trước khi append vào collection.
- [ ] Dùng upsert hoặc replace có phạm vi rõ ràng.
- [ ] Giữ metadata được khai báo bởi controller nếu customizer không sở hữu nó.
- [ ] Không dùng object mutable hoặc collection dùng chung giữa các lần chạy.
- [ ] Không sinh timestamp, UUID hoặc giá trị ngẫu nhiên trong tài liệu nếu không cần thiết.
- [ ] Giữ thứ tự ổn định để diff dễ đọc.
- [ ] Kiểm tra riêng tài liệu mặc định và từng document group.
- [ ] Áp dụng customizer hai lần lên cùng model và so sánh kết quả.
- [ ] So sánh artifact OpenAPI trong CI để phát hiện thay đổi ngoài ý muốn.

## 16. Kết luận

Tùy biến OpenAPI bằng code cần có tính lặp lại an toàn vì tài liệu có thể được xây dựng trong nhiều ngữ cảnh và nhiều lần. Hãy nhận diện từng thành phần bằng khóa ổn định, kiểm tra trước khi thêm, cập nhật đúng phần mình sở hữu và giữ metadata do controller khai báo. Tránh trạng thái mutable dùng chung và dữ liệu ngẫu nhiên. Quan trọng nhất, kiểm thử customizer bằng cách áp dụng hai lần lên cùng một OpenAPI model; nếu kết quả không đổi, logic đã đáp ứng yêu cầu idempotency ở cấp biến đổi.

## 17. Nguồn tham khảo

- [Springdoc OpenAPI — FAQ](https://springdoc.org/faq.html): tùy biến OpenAPI bằng OpenApiCustomizer và GlobalOpenApiCustomizer.
- [Swagger Core — OpenAPI Model](https://github.com/swagger-api/swagger-core): cấu trúc model OpenAPI, operation, parameters, responses, components và servers.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): ý nghĩa và cấu trúc của OpenAPI Object, Operation Object, Parameter Object, Response Object và Components Object.
