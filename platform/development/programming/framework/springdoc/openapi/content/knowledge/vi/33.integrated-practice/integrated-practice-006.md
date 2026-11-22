# Bổ sung metadata dùng chung bằng customizer có kiểm thử

Trong một ứng dụng Spring Boot, nhiều controller và nhiều nhóm API thường cần dùng chung thông tin tài liệu: contact của đội sở hữu API, license, liên kết hướng dẫn, tag nền tảng hoặc header tương quan request. Nếu lặp lại các thông tin này ở từng controller, chúng dễ bị lệch nhau khi đổi địa chỉ hỗ trợ, tên đội hoặc quy ước tích hợp.

springdoc-openapi cho phép bổ sung metadata bằng `OpenAPI` bean và các customizer. Chọn đúng phạm vi là điều quan trọng: metadata nền tảng có thể áp dụng cho mọi document; metadata của một group chỉ nên xuất hiện trong group đó; metadata của từng operation cần được gắn ở operation tương ứng. Sau khi cấu hình, kiểm thử JSON được sinh ra để xác nhận metadata thực sự xuất hiện trong document mặc định và các group.

## 1. Phân biệt các điểm mở rộng

Không phải mọi customizer đều có cùng phạm vi:

| Cơ chế | Phạm vi sử dụng | Ví dụ phù hợp |
| --- | --- | --- |
| `OpenAPI` bean | Định nghĩa nền tảng dùng chung cho các OpenAPI document | `info`, `components`, security scheme, parameter hoặc header dùng chung. |
| `GlobalOpenApiCustomizer` | Chỉnh sửa document mặc định và các document của `GroupedOpenApi` | Bổ sung contact, external docs, tag hoặc common parameter cho mọi group. |
| `OpenApiCustomizer` gắn vào `GroupedOpenApi` | Chỉ document của group được cấu hình | Description, extension hoặc metadata riêng của nhóm đối tác. |
| `OpenApiCustomizer` bean thông thường | Document mặc định | Điều chỉnh document mặc định mà không áp dụng cho các group. |
| Annotation như `@Operation`, `@Tag`, `@Schema` | Controller, operation hoặc model tương ứng | Mô tả hành vi và schema tại nguồn khai báo API. |

Theo FAQ của springdoc, bean `OpenApiCustomizer` thông thường chỉ áp dụng cho document mặc định. Nếu cần customizer chạy cả với các group, dùng `GlobalOpenApiCustomizer`. Một `OpenAPI` bean có thể cung cấp định nghĩa nền tảng xuất hiện trong các group, kể cả khi group có bộ lọc controller/path riêng.

`OperationCustomizer` là điểm mở rộng ở cấp operation và thường nhận cả operation cùng handler method. Hãy dùng nó khi metadata phụ thuộc method/controller cụ thể. Với metadata dùng chung cho toàn bộ document, `GlobalOpenApiCustomizer` thường diễn đạt đúng phạm vi hơn.

## 2. Xác định metadata nào thật sự dùng chung

Trước khi viết code, phân loại metadata:

| Metadata | Ví dụ | Phạm vi đề xuất |
| --- | --- | --- |
| Tiêu đề và phiên bản tài liệu | Store API, 1.4.0 | Từng API/group nếu các nhóm có vòng đời riêng; dùng cấu hình nền tảng khi giống nhau. |
| Contact | API Platform Team, email hỗ trợ | Toàn bộ document nếu cùng một đội sở hữu. |
| License | Apache 2.0 hoặc điều khoản nội bộ | Toàn bộ document nếu chính sách giống nhau. |
| Terms of service | URL điều khoản sử dụng | Toàn bộ document nếu cùng chính sách. |
| External documentation | Hướng dẫn xác thực, quy ước lỗi | Toàn bộ document hoặc theo group nếu đối tượng đọc khác nhau. |
| Tag dùng chung | Platform, Common | Toàn bộ document nếu operation ở nhiều group cùng dùng. |
| Header tương quan | `X-Correlation-Id` | Chỉ gắn cho operation thực sự chấp nhận header này. |
| Extension riêng | `x-audience`, `x-owner` | Theo thỏa thuận với consumer đọc extension. |

Không đưa mọi metadata vào mọi document chỉ vì có thể làm được. Ví dụ tài liệu public không nên chứa link runbook nội bộ; group đối tác không nên nhận contact của đội vận hành nếu địa chỉ đó không dành cho đối tác. Hãy xác định audience và phạm vi trước khi thêm customizer.

## 3. Tạo OpenAPI bean cho metadata nền tảng

Với springdoc v2 dành cho Spring Boot 3, có thể định nghĩa `OpenAPI` bean để khai báo phần nền tảng. Ví dụ sau đặt title và version chung, đồng thời giữ thông tin này tách khỏi controller:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiBaseConfiguration {

    @Bean
    OpenAPI baseOpenApi(
        @Value("${service.api.version:1.0.0}") String apiVersion
    ) {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version(apiVersion)
                .description("API của nền tảng cửa hàng."));
    }
}
~~~

`OpenAPI` bean phù hợp với thông tin nền tảng mà các document đều cần. Nếu từng group có title hoặc version khác nhau, đừng ép một giá trị chung lên tất cả; đặt metadata riêng ở group customizer hoặc cấu hình theo audience.

Không nên tạo nhiều `OpenAPI` bean cạnh tranh trong cùng application context nếu không có chủ đích rõ ràng. Hãy có một nguồn cấu hình nền tảng và dùng customizer cho phần bổ sung có điều kiện.

## 4. Bổ sung metadata và parameter dùng chung bằng GlobalOpenApiCustomizer

Ví dụ dưới đây bổ sung contact, license, external documentation, tag `Platform` và một header `X-Correlation-Id` dùng chung. Customizer kiểm tra trước khi thêm parameter để tránh tạo bản sao nếu operation đã khai báo header này.

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.tags.Tag;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;
import java.util.Objects;

@Configuration
class SharedOpenApiMetadataConfiguration {

    private static final String CORRELATION_ID_NAME = "X-Correlation-Id";
    private static final String CORRELATION_ID_REF =
        "#/components/parameters/CorrelationId";

    @Bean
    GlobalOpenApiCustomizer sharedMetadataCustomizer() {
        return openApi -> {
            addSharedInfo(openApi);
            addExternalDocumentation(openApi);
            addSharedTag(openApi);
            addCorrelationIdComponent(openApi);
            addCorrelationIdToOperations(openApi);
        };
    }

    private static void addSharedInfo(OpenAPI openApi) {
        if (openApi.getInfo() == null) {
            openApi.setInfo(new Info());
        }

        Info info = openApi.getInfo();
        if (info.getContact() == null) {
            info.setContact(new Contact());
        }
        Contact contact = info.getContact();
        if (contact.getName() == null) {
            contact.setName("API Platform Team");
        }
        if (contact.getEmail() == null) {
            contact.setEmail("api-support@example.com");
        }
        if (contact.getUrl() == null) {
            contact.setUrl("https://developer.example.com/support");
        }

        if (info.getLicense() == null) {
            info.setLicense(new License()
                .name("Internal API Terms")
                .url("https://developer.example.com/terms"));
        }
    }

    private static void addExternalDocumentation(OpenAPI openApi) {
        if (openApi.getExternalDocs() == null) {
            openApi.setExternalDocs(new ExternalDocumentation()
                .description("Hướng dẫn tích hợp API")
                .url("https://developer.example.com/guides"));
        }
    }

    private static void addSharedTag(OpenAPI openApi) {
        boolean exists = openApi.getTags() != null
            && openApi.getTags().stream()
                .anyMatch(tag -> "Platform".equals(tag.getName()));

        if (!exists) {
            openApi.addTagsItem(new Tag()
                .name("Platform")
                .description("Thông tin và quy ước chung của nền tảng."));
        }
    }

    private static void addCorrelationIdComponent(OpenAPI openApi) {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        Components components = openApi.getComponents();
        Parameter existing = components.getParameters() == null
            ? null
            : components.getParameters().get("CorrelationId");

        if (existing == null) {
            components.addParameters("CorrelationId", new Parameter()
                .name(CORRELATION_ID_NAME)
                .in("header")
                .description("Mã tương quan để theo dõi một request qua các dịch vụ.")
                .required(false)
                .schema(new StringSchema()));
        } else if (!CORRELATION_ID_NAME.equals(existing.getName())
            || !"header".equals(existing.getIn())) {
            throw new IllegalStateException(
                "components.parameters.CorrelationId is reserved for X-Correlation-Id");
        }
    }

    private static void addCorrelationIdToOperations(OpenAPI openApi) {
        if (openApi.getPaths() == null) {
            return;
        }

        openApi.getPaths().values().stream()
            .flatMap(pathItem -> pathItem.readOperations().stream())
            .forEach(SharedOpenApiMetadataConfiguration::addCorrelationId);
    }

    static void addCorrelationId(Operation operation) {
        List<Parameter> parameters = operation.getParameters();
        boolean alreadyDeclared = parameters != null
            && parameters.stream().anyMatch(parameter ->
                Objects.equals(CORRELATION_ID_REF, parameter.get$ref())
                    || (Objects.equals("header", parameter.getIn())
                        && CORRELATION_ID_NAME.equalsIgnoreCase(parameter.getName()))
            );

        if (!alreadyDeclared) {
            operation.addParametersItem(new Parameter()
                .$ref(CORRELATION_ID_REF));
        }
    }
}
~~~

`GlobalOpenApiCustomizer` được dùng vì thay đổi cần xuất hiện trong document mặc định và các document nhóm. Component parameter được khai báo một lần trong `components.parameters`; từng operation tham chiếu đến nó bằng `$ref`. Cách này giúp mô tả header thống nhất và tránh lặp nguyên mô tả ở từng controller.

Customizer cũng kiểm tra component key đã tồn tại có đúng là header `X-Correlation-Id` hay không. Nếu key `CorrelationId` đã được dùng cho một parameter khác, cấu hình fail-fast để tránh âm thầm tham chiếu nhầm component. Tag `Platform` được khai báo ở cấp document; việc khai báo này không tự gắn tag vào mọi operation. Chỉ thêm tag vào operation nếu đó thật sự là nhóm phân loại phù hợp.

Ví dụ dùng domain `example.com` dành cho minh họa. Thay contact, license và URL bằng thông tin được tổ chức phê duyệt trước khi phát hành. Không đưa token, email cá nhân hoặc URL runbook riêng tư vào document public.

Header chỉ nên được thêm nếu toàn bộ operation trong phạm vi thực sự chấp nhận header đó. Nếu một số API không hỗ trợ correlation ID, hãy giới hạn customizer theo path/group hoặc dùng metadata riêng cho nhóm endpoint tương ứng. OpenAPI mô tả khả năng của server; thêm header vào document không tự làm Spring MVC đọc hoặc ghi log header đó.

## 5. Tùy biến metadata riêng cho một group

Giả sử đối tác chỉ được xem các endpoint dưới `/api/partner/**`. Group này cần mô tả audience riêng, trong khi contact và correlation header vẫn dùng chung:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PartnerOpenApiConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        OpenApiCustomizer partnerMetadata = openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }
            openApi.getInfo()
                .description("Tài liệu tích hợp dành cho đối tác.")
                .addExtension("x-audience", "partner");
        };

        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(partnerMetadata)
            .build();
    }
}
~~~

Để group có operation thực tế cho integration test, ứng dụng cần một controller khớp path filter. Ví dụ tối giản:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
class PartnerOrderController {

    @GetMapping("/api/partner/orders")
    @Operation(operationId = "listPartnerOrders")
    List<PartnerOrderSummary> listOrders() {
        return List.of();
    }
}

record PartnerOrderSummary(String orderId, String status) {}
~~~

Controller này chỉ minh họa mapping và operation được đưa vào group. Trong ứng dụng thật, method gọi service và trả dữ liệu theo hợp đồng đã định nghĩa.

`OpenApiCustomizer` ở đây được gắn trực tiếp vào `GroupedOpenApi`, nên nó chỉ bổ sung description và extension cho `partner-v1`. `GlobalOpenApiCustomizer` ở mục trước vẫn chịu trách nhiệm metadata chung.

Không đăng ký cùng một group id bằng hai `GroupedOpenApi` bean khác nhau. Nếu cần nhiều customizer cho một group, kết hợp chúng trong cùng builder hoặc tách logic thành các hàm được gọi từ một customizer.

Extension `x-audience` là metadata tùy chọn. Consumer chỉ hiểu nó nếu hai bên thống nhất tên, kiểu dữ liệu và ý nghĩa. Nếu không có consumer cụ thể, description chuẩn trong `info` thường đã đủ.

## 6. Khi nào nên dùng OperationCustomizer?

Metadata cấp document khác metadata cấp operation:

- `GlobalOpenApiCustomizer`: thay đổi `info`, `externalDocs`, `tags`, `components` hoặc duyệt tất cả operation trong document.
- `OpenApiCustomizer`: thay đổi một OpenAPI document, thường được gắn riêng cho group hoặc dùng ở document mặc định.
- `OperationCustomizer`: thay đổi operation dựa trên `HandlerMethod`, ví dụ thêm extension cho các method thuộc một annotation hoặc package nhất định.

Nếu mọi operation đều cần một header chung, có thể duyệt `paths` trong `GlobalOpenApiCustomizer` như ví dụ trên. Nếu chỉ những method có `@InternalApi` mới cần metadata đặc biệt, hãy dùng customizer cấp operation và kiểm tra annotation của handler method. Tránh đặt logic phân loại endpoint phức tạp trong một customizer document lớn nếu nó có thể được biểu đạt bằng group filter hoặc annotation rõ ràng.

## 7. Giữ customizer an toàn khi chạy nhiều lần

Customizer nên có tính lặp an toàn: chạy lại không làm document tích lũy bản sao hoặc thay đổi ngoài dự kiến. Điều này đặc biệt quan trọng khi document có nhiều group, nhiều locale hoặc được tính toán lại.

Một số nguyên tắc:

1. Kiểm tra `null` trước khi truy cập `info`, `components`, `tags` hoặc `paths`.
2. Kiểm tra component key trước khi thêm component dùng chung.
3. Kiểm tra parameter đã tồn tại trước khi thêm `$ref`.
4. Không thêm cùng một tag nhiều lần.
5. Không ghi đè title, version hoặc description do group khai báo nếu customizer không sở hữu các trường đó.
6. Không lưu `OpenAPI` model của một request vào field static hoặc singleton để dùng lại cho request khác.
7. Không thay đổi dữ liệu đầu vào bên ngoài như danh sách cấu hình dùng chung trong lúc customizer đang chạy.

Đoạn customizer mẫu chỉ bổ sung contact/license khi chưa có, chỉ thêm external docs khi chưa có và kiểm tra parameter/tag trước khi thêm. Nếu ứng dụng cần buộc một giá trị chuẩn ghi đè mọi group, hãy viết rõ quy tắc ưu tiên và kiểm thử giá trị cuối cùng thay vì vô tình phụ thuộc thứ tự customizer.

## 8. Không dùng customizer để thay thế cấu hình nghiệp vụ

Customizer thay đổi OpenAPI document được sinh ra. Nó không tự thay đổi:

- Request mapping hoặc HTTP method của controller.
- Spring Security authorization hoặc OAuth2 scope runtime.
- Bean Validation và kiểm tra dữ liệu trong service.
- Cách Jackson serialize/deserialize JSON.
- CORS, rate limit, audit hoặc xử lý correlation ID thực tế.

Ví dụ thêm `X-Correlation-Id` vào document không khiến request tự có header đó. Ứng dụng vẫn cần đọc/generate correlation ID bằng filter/interceptor, truyền qua log và downstream service theo quy ước vận hành.

Tương tự, khai báo `security` trong OpenAPI không tự bật Spring Security. Hãy cấu hình resource server, authorization rule và test request thật riêng biệt.

## 9. Kiểm thử metadata dùng chung ở document mặc định và group

Kiểm thử qua HTTP giúp xác nhận springdoc đã áp dụng customizer vào document cuối cùng. Ví dụ dùng Spring MVC, MockMvc và Jackson:

Ví dụ giả định dự án đã có `spring-boot-starter-test` trong test scope; dependency này cung cấp JUnit Jupiter, AssertJ và MockMvc test support theo dependency management của Spring Boot.

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
class SharedOpenApiMetadataTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void sharedMetadataExistsInDefaultAndPartnerDocuments() throws Exception {
        JsonNode defaultDocument = loadDocument("/v3/api-docs");
        JsonNode partnerDocument = loadDocument("/v3/api-docs/partner-v1");

        assertSharedMetadata(defaultDocument);
        assertSharedMetadata(partnerDocument);

        assertThat(defaultDocument.at("/info/x-audience").isMissingNode()).isTrue();
        assertThat(partnerDocument.at("/info/x-audience").asText())
            .isEqualTo("partner");
        assertThat(partnerDocument.at("/info/description").asText())
            .isEqualTo("Tài liệu tích hợp dành cho đối tác.");
    }

    private JsonNode loadDocument(String path) throws Exception {
        String body = mockMvc.perform(get(path))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
        return objectMapper.readTree(body);
    }

    private static void assertSharedMetadata(JsonNode document) {
        assertThat(document.at("/info/contact/name").asText())
            .isEqualTo("API Platform Team");
        assertThat(document.at("/info/contact/email").asText())
            .isEqualTo("api-support@example.com");
        assertThat(document.at("/info/license/name").asText())
            .isEqualTo("Internal API Terms");
        assertThat(document.at("/externalDocs/url").asText())
            .isEqualTo("https://developer.example.com/guides");
        assertThat(document.at(
            "/components/parameters/CorrelationId/name").asText())
            .isEqualTo("X-Correlation-Id");
        assertThat(document.path("tags").findValuesAsText("name"))
            .contains("Platform");
    }
}
~~~

Test xác nhận metadata chung xuất hiện trong cả document mặc định và group `partner-v1`, còn extension `x-audience` chỉ xuất hiện trong group. Trong OpenAPI model, extension gắn vào `Info` được serialize bên trong object `info`, do đó JSON Pointer tương ứng là `/info/x-audience`. Nếu ứng dụng có security bảo vệ endpoint docs, cấu hình test authentication phù hợp; không vô hiệu hóa security production chỉ để test.

Để kiểm tra header được tham chiếu ở operation, thêm assertion theo path thực tế:

~~~java
JsonNode parameters = partnerDocument.at(
    "/paths/~1api~1partner~1orders/get/parameters"
);
assertThat(parameters.toString())
    .contains("#/components/parameters/CorrelationId");
~~~

Trong JSON Pointer, dấu `/` trong path được escape thành `~1`. Hãy dùng đúng path và HTTP method của controller trong ứng dụng. Nếu một operation đã tự khai báo `X-Correlation-Id`, kiểm tra document chỉ có một parameter hiệu lực, không có bản sao cùng tên.

## 10. Kiểm thử customizer độc lập và tính lặp an toàn

Ngoài integration test, có thể kiểm tra logic customizer trên OpenAPI model tối giản. Ví dụ kiểm tra hàm thêm correlation parameter:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationParameterTest {

    @Test
    void doesNotAddDuplicateCorrelationParameter() {
        Operation operation = new Operation()
            .addParametersItem(new Parameter()
                .$ref("#/components/parameters/CorrelationId"));

        SharedOpenApiMetadataConfiguration.addCorrelationId(operation);
        SharedOpenApiMetadataConfiguration.addCorrelationId(operation);

        assertThat(operation.getParameters()).hasSize(1);
    }
}
~~~

Helper `addCorrelationId` trong ví dụ customizer được để ở phạm vi package-private để test cùng package gọi trực tiếp. Không cần mở helper thành public API của ứng dụng chỉ để test. Nếu muốn giữ helper private, hãy kiểm tra tính lặp an toàn qua integration test của customizer bean thay vì dùng reflection.

## 11. Kiểm tra nhiều group và YAML

Nếu ứng dụng có nhiều group, kiểm tra tất cả group có yêu cầu metadata chung. Đừng chỉ kiểm tra group đầu tiên rồi suy luận mọi group đều được áp dụng:

| Document | Metadata chung | Metadata riêng |
| --- | --- | --- |
| `/v3/api-docs` | Contact, license, external docs, tag, correlation parameter | Không có `x-audience=partner`. |
| `/v3/api-docs/partner-v1` | Cùng metadata chung | `x-audience=partner`, description đối tác. |
| `/v3/api-docs/internal-v1` | Cùng metadata chung nếu chính sách yêu cầu | Có thể có description và owner nội bộ riêng. |

JSON và YAML phải biểu diễn cùng một metadata. Nếu pipeline phát hành YAML, thêm test cho URL `.yaml`, parse YAML thành object rồi xác nhận các trường giống JSON. Test JSON không chứng minh route YAML, security matcher hoặc gateway route đang hoạt động.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Metadata có ở document mặc định nhưng mất trong group | Dùng bean `OpenApiCustomizer` thông thường | Dùng `GlobalOpenApiCustomizer` hoặc gắn customizer vào group. |
| Metadata của đối tác xuất hiện trong mọi group | Dùng global customizer cho dữ liệu riêng group | Chuyển sang `OpenApiCustomizer` gắn riêng `GroupedOpenApi`. |
| Tag hoặc parameter bị lặp | Customizer không kiểm tra phần tử đã tồn tại | Làm customizer idempotent trước khi thêm. |
| `$ref` không resolve được | Có operation tham chiếu nhưng thiếu component parameter | Đăng ký component trong `components.parameters` của cùng document. |
| Header xuất hiện trong OpenAPI nhưng server không xử lý | Chỉ sửa document, chưa triển khai filter/interceptor | Thực hiện xử lý header ở runtime và kiểm thử riêng. |
| Title/version bị ghi đè | Nhiều nơi cùng sở hữu một trường metadata | Xác định nguồn ưu tiên và chỉ để một nơi ghi trường đó. |
| Contact hoặc license khác nhau giữa group | Group có metadata riêng hoặc customizer không chạy toàn cục | Kiểm tra `OpenAPI` bean và `GlobalOpenApiCustomizer` trong từng document. |
| Test không thấy group | `GroupedOpenApi` không được đăng ký hoặc path filter không khớp | Kiểm tra group id, bean và endpoint controller. |
| JSON đúng nhưng YAML sai | YAML endpoint hoặc customizer/security routing chưa được kiểm tra | Test và parse riêng document YAML. |
| Extension bị consumer bỏ qua | Consumer không hiểu quy ước `x-*` | Thống nhất schema extension và kiểm tra consumer trước khi phụ thuộc vào nó. |

## 13. Checklist triển khai

Trước khi phát hành metadata dùng chung, xác nhận:

1. Đã phân loại metadata nền tảng, metadata theo group và metadata theo operation.
2. `OpenAPI` bean chỉ giữ thông tin nền tảng có cùng ý nghĩa giữa các document.
3. `GlobalOpenApiCustomizer` được dùng cho thay đổi cần xuất hiện trong default document và mọi group.
4. `OpenApiCustomizer` riêng được gắn vào đúng `GroupedOpenApi`.
5. Component dùng chung được đăng ký trong `components` trước khi operation tham chiếu `$ref`.
6. Customizer kiểm tra `null`, component/tag/parameter trùng và không ghi đè metadata ngoài quyền sở hữu.
7. Contact, license, external docs và extension không tiết lộ thông tin nội bộ.
8. Header được mô tả trong OpenAPI cũng được hỗ trợ ở runtime.
9. Integration test xác nhận document mặc định và từng group.
10. Test xác nhận metadata riêng không rò sang group khác.
11. JSON/YAML và endpoint tải tài liệu đều được kiểm tra.
12. Security và authorization runtime được kiểm thử độc lập với nội dung document.

## 14. Nguyên tắc áp dụng

- Dùng `OpenAPI` bean cho định nghĩa nền tảng cần có trong mọi document.
- Dùng `GlobalOpenApiCustomizer` cho metadata hoặc thành phần cần được bổ sung vào document mặc định và tất cả group.
- Dùng `OpenApiCustomizer` gắn với `GroupedOpenApi` cho metadata chỉ thuộc một group.
- Dùng customizer cấp operation khi metadata phụ thuộc handler method.
- Đăng ký component dùng chung một lần rồi tham chiếu bằng `$ref`.
- Làm customizer idempotent để tránh duplicate tag, parameter hoặc extension.
- Chỉ thêm metadata phản ánh đúng hành vi runtime.
- Kiểm thử document đã serialize, không chỉ kiểm tra bean được tạo.
- Kiểm tra cả default document, các group, JSON và YAML trước khi publish.

Metadata dùng chung cần có một nguồn cấu hình rõ ràng và một phạm vi áp dụng đúng. `OpenAPI` bean cung cấp định nghĩa nền tảng; `GlobalOpenApiCustomizer` bổ sung thay đổi cần có trong mọi document; customizer gắn với group giữ metadata riêng đúng audience. Khi component được tham chiếu bằng `$ref`, customizer có tính lặp an toàn và integration test xác nhận kết quả ở default document cùng từng group, hợp đồng OpenAPI sẽ nhất quán hơn khi ứng dụng mở rộng hoặc thay đổi controller.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ – Customize the OpenAPI object](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ – GlobalOpenApiCustomizer và GroupedOpenApi](https://springdoc.org/v2/faq.html)
- [Springdoc OpenAPI v2 – Getting Started](https://springdoc.org/v2/getting-started.html)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
