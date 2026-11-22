# Kiểm thử customizer độc lập với việc giao diện có hiển thị đẹp hay không

Khi tùy biến OpenAPI bằng springdoc-openapi, kết quả cần kiểm tra là tài liệu JSON/YAML mà ứng dụng công bố. Swagger UI chỉ là một giao diện đọc tài liệu đó. Một trang Swagger UI hiển thị đẹp không chứng minh customizer đã thêm đúng metadata, giữ nguyên schema, không làm mất operation hoặc tạo security requirement sai.

Vì vậy, hãy kiểm thử customizer ở hai cấp: kiểm thử đơn vị cho logic biến đổi OpenAPI model và kiểm thử tích hợp cho tài liệu thực tế do endpoint springdoc sinh ra. Cách này phát hiện được cả lỗi trong đoạn code tùy biến lẫn lỗi do cấu hình Spring, group, phạm vi áp dụng customizer hoặc quá trình sinh đặc tả.

## 1. Xác định đầu ra cần kiểm thử

OpenAPI document là hợp đồng máy đọc được. Các phần quan trọng thường gồm:

| Thành phần | Điều cần xác minh |
| --- | --- |
| info | title, version, description, contact, license và terms |
| servers | URL gốc mà client thực sự được phép sử dụng |
| paths | Operation đúng tập endpoint và HTTP method |
| parameters | Tên, vị trí, kiểu và tính bắt buộc |
| requestBody | Media type, schema và ví dụ |
| responses | Status code, content và schema |
| components | Schema, response, parameter và security scheme được tham chiếu |
| security | Scheme và requirement khớp chính sách endpoint |
| tags và externalDocs | Nhóm operation và liên kết tài liệu chính xác |

Customizer có thể tác động đến một hoặc nhiều phần trong danh sách. Trước khi viết test, xác định chính xác field nào customizer được phép thay đổi và field nào phải được giữ nguyên.

Ví dụ, một customizer chỉ bổ sung contact vào info cần được kiểm tra rằng:

- Contact xuất hiện đúng tên và email.
- Title, version và description có sẵn vẫn được giữ nguyên.
- Paths, schemas, responses và security không bị thay đổi ngoài ý muốn.
- Logic được áp dụng cho đúng tài liệu mặc định hoặc đúng group đã chọn.

## 2. Phân biệt các loại customizer trước khi kiểm thử

Springdoc có các cơ chế tùy biến với phạm vi khác nhau. Chọn sai loại customizer có thể khiến unit test riêng lẻ vẫn đạt nhưng tài liệu group thực tế không được cập nhật.

| Cơ chế | Phạm vi | Cách kiểm tra |
| --- | --- | --- |
| OpenApiCustomizer bean độc lập | Tài liệu mặc định | Gọi logic trực tiếp và kiểm tra /v3/api-docs |
| GlobalOpenApiCustomizer | Tài liệu mặc định và các group | Kiểm tra nhiều endpoint tài liệu, gồm từng group |
| GroupedOpenApi.builder().addOpenApiCustomizer(...) | Group được gắn customizer | Kiểm tra group đích và một group không liên quan |
| OperationCustomizer | Operation được xử lý | Kiểm tra từng path/method sau khi sinh tài liệu |
| OpenApiMethodFilter | Lọc method đưa vào tài liệu | Kiểm tra operation có hoặc không xuất hiện |

Đối với springdoc 2.x và 3.x, GroupedOpenApi thường nằm trong package org.springdoc.core.models; các customizer nằm trong package org.springdoc.core.customizers. Dòng springdoc 1.x có một số package khác. Hãy dùng API tương ứng với dependency của dự án.

Không nên chỉ kiểm tra customizer được tạo thành bean. Cần kiểm tra tài liệu cuối cùng để xác nhận springdoc đã áp dụng bean vào đúng document.

## 3. Tách logic biến đổi thành hàm có thể kiểm thử

Một cách đơn giản để unit test là tách logic cập nhật OpenAPI model thành phương thức riêng, sau đó dùng customizer gọi phương thức đó.

Ví dụ bổ sung metadata chung:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    static void applySharedMetadata(OpenAPI openApi) {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        if (info.getContact() == null) {
            info.setContact(new Contact()
                .name("API Platform Team")
                .email("api-support@example.com"));
        }
    }

    @Bean
    GlobalOpenApiCustomizer sharedMetadataCustomizer() {
        return OpenApiConfiguration::applySharedMetadata;
    }
}
~~~

Hàm applySharedMetadata chỉ bổ sung contact nếu chưa có. Nó giữ lại title, version, description và các field khác của Info. Việc tách hàm giúp kiểm tra logic mà không cần khởi động Spring hoặc dựng Swagger UI.

## 4. Unit test cho logic customizer

Có thể dùng JUnit 5 để tạo một OpenAPI model nhỏ, gọi hàm biến đổi và kiểm tra kết quả:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.junit.jupiter.api.Test;

class OpenApiConfigurationTest {

    @Test
    void addsContactAndPreservesExistingInfo() {
        OpenAPI openApi = new OpenAPI()
            .info(new Info()
                .title("Partner API")
                .version("v2")
                .description("Hợp đồng dành cho đối tác."));

        OpenApiConfiguration.applySharedMetadata(openApi);

        assertEquals("Partner API", openApi.getInfo().getTitle());
        assertEquals("v2", openApi.getInfo().getVersion());
        assertEquals(
            "Hợp đồng dành cho đối tác.",
            openApi.getInfo().getDescription());

        Contact contact = openApi.getInfo().getContact();
        assertNotNull(contact);
        assertEquals("API Platform Team", contact.getName());
        assertEquals("api-support@example.com", contact.getEmail());
    }
}
~~~

Test này bảo vệ hành vi quan trọng: customizer thêm metadata nhưng không ghi đè metadata riêng của group. Nếu implementation thay Info hiện có bằng một object mới, các assertion title/version/description sẽ phát hiện lỗi.

Nên bổ sung trường hợp openApi.getInfo() ban đầu là null để xác nhận customizer khởi tạo object an toàn:

~~~java
@Test
void createsInfoWhenDocumentHasNoInfo() {
    OpenAPI openApi = new OpenAPI();

    OpenApiConfiguration.applySharedMetadata(openApi);

    assertNotNull(openApi.getInfo());
    assertNotNull(openApi.getInfo().getContact());
}
~~~

## 5. Kiểm tra tính idempotent và tránh dữ liệu dùng chung bị biến đổi

Customizer có thể được áp dụng khi springdoc tạo nhiều tài liệu hoặc tạo lại document. Logic nên tránh thêm phần tử trùng mỗi lần chạy.

Ví dụ, customizer thêm tag:

~~~java
import java.util.ArrayList;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.tags.Tag;

static void addOrdersTag(OpenAPI openApi) {
    if (openApi.getTags() == null) {
        openApi.setTags(new ArrayList<>());
    }

    boolean exists = openApi.getTags().stream()
        .anyMatch(tag -> "Orders".equals(tag.getName()));

    if (!exists) {
        openApi.addTagsItem(new Tag()
            .name("Orders")
            .description("Các thao tác quản lý đơn hàng"));
    }
}
~~~

Kiểm thử gọi hai lần:

~~~java
@Test
void addingTagTwiceDoesNotCreateDuplicates() {
    OpenAPI openApi = new OpenAPI();

    OpenApiConfiguration.addOrdersTag(openApi);
    OpenApiConfiguration.addOrdersTag(openApi);

    long count = openApi.getTags().stream()
        .filter(tag -> "Orders".equals(tag.getName()))
        .count();

    assertEquals(1, count);
}
~~~

Với servers, security, tags hoặc danh sách response, hãy quyết định rõ customizer thay thế danh sách hay bổ sung phần tử. Không dùng add... vô điều kiện nếu customizer có thể chạy nhiều lần.

Không giữ một OpenAPI, Info, Components hoặc List mutable trong biến static rồi dùng chung giữa nhiều group. Mỗi document nên nhận object phù hợp với phạm vi của nó; dữ liệu dùng chung nên được tạo mới hoặc sao chép có chủ đích để tránh group này làm thay đổi group khác.

## 6. Unit test cho customizer riêng của group

Ví dụ một group partner cần title riêng:

~~~java
static void applyPartnerMetadata(OpenAPI openApi) {
    Info info = openApi.getInfo();
    if (info == null) {
        info = new Info();
        openApi.setInfo(info);
    }
    info.setTitle("Partner API");
    info.setVersion("v2");
}
~~~

Bean cấu hình:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(
            OpenApiConfiguration::applyPartnerMetadata)
        .build();
}
~~~

Unit test có thể gọi applyPartnerMetadata trên một model giả lập để xác minh title và version. Nhưng unit test đó chưa chứng minh group được cấu hình đúng hoặc customizer thực sự được springdoc áp dụng. Phần đó cần integration test gọi endpoint của group.

## 7. Integration test tài liệu JSON bằng MockMvc

Kiểm tra endpoint OpenAPI thực tế bằng @SpringBootTest và MockMvc. Cách này khởi tạo Spring context, để springdoc quét controller, áp dụng customizer và trả về document như ứng dụng đang chạy.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void partnerDocumentContainsExpectedMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs/partner-api"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title")
                .value("Partner API"))
            .andExpect(jsonPath("$.info.version")
                .value("v2"))
            .andExpect(jsonPath("$.info.contact.name")
                .value("API Platform Team"));
    }
}
~~~

Test này không mở trình duyệt, không phụ thuộc CSS hoặc JavaScript của Swagger UI. Nó kiểm tra trực tiếp tài liệu JSON mà client và công cụ contract testing sẽ đọc.

Nếu ứng dụng đã tùy chỉnh springdoc.api-docs.path, hãy dùng endpoint tương ứng thay cho /v3/api-docs. Nếu tài liệu được bảo vệ bằng Spring Security, test cần cung cấp danh tính/quyền phù hợp hoặc cấu hình test security riêng cho endpoint docs. Không tắt bảo mật production chỉ để test trả về 200.

## 8. Kiểm tra operation, schema và tham chiếu

Metadata đúng chưa đủ. Customizer có thể vô tình thay thế paths, components hoặc security. Hãy xác nhận operation quan trọng vẫn còn:

~~~java
@Test
void partnerDocumentContainsOnlyExpectedOperations() throws Exception {
    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/api/partner/orders'].get")
            .exists())
        .andExpect(jsonPath("$.paths['/api/admin/users']")
            .doesNotExist())
        .andExpect(jsonPath(
            "$.paths['/api/partner/orders'].get.responses['200']"
        ).exists());
}
~~~

Nếu response tham chiếu schema:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].get.responses['200']"
            + ".content['application/json'].schema['$ref']"
    ).value("#/components/schemas/PartnerOrder"));
~~~

Hãy xác minh component đích cũng tồn tại:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.PartnerOrder.type"
    ).value("object"));
~~~

Đường dẫn JSONPath cần khớp với path và schema thực tế của dự án. Những assertion này giúp phát hiện customizer vô tình xóa component hoặc tạo $ref không hợp lệ.

## 9. Kiểm tra GlobalOpenApiCustomizer trên nhiều group

Một GlobalOpenApiCustomizer cần được kiểm tra trên tài liệu mặc định và các group. Chỉ gọi /v3/api-docs là chưa đủ.

Ví dụ:

~~~java
@Test
void sharedMetadataIsPresentInEveryGroup() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.contact.name")
            .value("API Platform Team"));

    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.contact.name")
            .value("API Platform Team"));
}
~~~

Ngoài metadata chung, cần xác nhận mỗi group vẫn giữ thông tin riêng:

~~~java
@Test
void groupsKeepTheirOwnTitles() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-api"))
        .andExpect(jsonPath("$.info.title").value("Public API"));

    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(jsonPath("$.info.title").value("Partner API"));
}
~~~

Đây là cách phát hiện lỗi global customizer thay thế toàn bộ Info và xóa title riêng của từng group. Nếu các group được cấu hình động, hãy lấy danh sách group từ cấu hình test và kiểm tra từng endpoint tương ứng.

## 10. Kiểm tra security scheme và security requirement

Customizer có thể thêm security scheme vào components.securitySchemes, nhưng điều đó không đồng nghĩa mọi operation đều bắt buộc dùng scheme đó.

Ví dụ kiểm tra scheme:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.securitySchemes.bearerAuth.type"
    ).value("http"))
    .andExpect(jsonPath(
        "$.components.securitySchemes.bearerAuth.scheme"
    ).value("bearer"));
~~~

Nếu group có cả operation public và protected, kiểm tra requirement ở đúng cấp. Một security requirement ở cấp document có thể áp dụng mặc định cho mọi operation; operation có thể ghi đè hoặc làm rõ yêu cầu theo quy tắc OpenAPI. Hãy xác nhận JSON sinh ra phản ánh chính sách mong muốn.

OpenAPI security metadata không thay thế test authorization runtime. Cần có test riêng gọi endpoint thật với token hợp lệ, token thiếu hoặc không đủ quyền để kiểm tra Spring Security.

## 11. Kiểm tra JSON/YAML thay vì phụ thuộc Swagger UI

Swagger UI có thể thay đổi phiên bản, giao diện, theme, layout hoặc JavaScript. Những thay đổi này không nhất thiết làm thay đổi hợp đồng OpenAPI.

Khi kiểm thử customizer, ưu tiên:

- Gọi endpoint JSON/YAML.
- Parse tài liệu thành cây JSON hoặc OpenAPI model.
- Assert vào các field quan trọng.
- Kiểm tra $ref, media type, operation và security.
- Chạy validator hoặc contract diff khi cần.

Không nên dùng screenshot hoặc kiểm tra CSS selector của Swagger UI làm bằng chứng duy nhất rằng customizer đúng. Giao diện có thể hiển thị một phần metadata hoặc ẩn một số chi tiết; tài liệu JSON/YAML mới là đầu ra có cấu trúc cần xác nhận.

Nếu dự án chỉ cần xuất đặc tả cho CI hoặc developer portal mà không cần giao diện tương tác, starter springdoc-openapi-starter-webmvc-api hoặc springdoc-openapi-starter-webflux-api có thể đáp ứng nhu cầu mà không cần đóng gói Swagger UI. Nếu ứng dụng đã dùng starter *-ui, các test contract vẫn nên gọi endpoint OpenAPI trực tiếp.

## 12. Kiểm tra YAML và nhiều định dạng đầu ra

Nếu hệ thống công bố cả JSON và YAML, cần xác nhận hai biểu diễn mô tả cùng một hợp đồng. Đường dẫn mặc định thường có /v3/api-docs cho JSON và /v3/api-docs.yaml cho YAML; đường dẫn có thể thay đổi theo cấu hình springdoc.

Test endpoint YAML có thể kiểm tra status và content type:

~~~java
mockMvc.perform(get("/v3/api-docs.yaml"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.valueOf("application/vnd.oai.openapi")));
~~~

Content-Type thực tế có thể khác theo phiên bản và cấu hình. Hãy xác nhận response header của ứng dụng trước khi cố định assertion. Để kiểm tra nội dung, parse YAML bằng thư viện parser phù hợp của dự án rồi assert các field tương đương JSON.

Với group, URL YAML có thể phụ thuộc cách cấu hình endpoint và phiên bản springdoc. Không tự giả định một hậu tố; hãy kiểm tra route thực tế được cung cấp trong ứng dụng.

## 13. Kiểm thử customizer theo tình huống lỗi

Ngoài trường hợp thành công, nên kiểm tra những điều kiện có thể làm customizer hỏng:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| openApi.getInfo() là null | Customizer tạo Info hợp lệ trước khi cập nhật |
| components chưa tồn tại | Customizer khởi tạo an toàn nếu cần thêm component |
| Schema mục tiêu không tồn tại | Bỏ qua có kiểm soát hoặc báo lỗi cấu hình rõ ràng |
| Tag đã tồn tại | Không thêm bản sao ngoài ý muốn |
| Customizer được gọi hai lần | Không tạo duplicate server, tag hoặc security requirement |
| Group không có operation phù hợp | Document rỗng hoặc hành vi được xác định rõ theo cấu hình |
| Có nhiều group | Metadata chung được áp dụng, metadata riêng không bị ghi đè |
| Customizer xử lý server URL | Không công bố localhost hoặc host nội bộ trong tài liệu public |
| Security scheme có sẵn | Không thay thế scheme khác hoặc xóa requirement cần thiết |

Nếu customizer dựa vào cấu hình môi trường, test từng profile hoặc inject property test rõ ràng. Không dùng dữ liệu ngẫu nhiên hoặc timestamp hiện tại trong tài liệu nếu không có lý do; giá trị thay đổi liên tục khiến contract diff khó phân tích.

## 14. Contract diff và snapshot

Với API có nhiều group, có thể lưu OpenAPI document đã chuẩn hóa làm artifact CI hoặc so sánh với bản phát hành trước. Mục tiêu là phát hiện thay đổi hợp đồng không chủ ý:

- Operation bị xóa hoặc đổi HTTP method.
- Required field mới được thêm.
- Kiểu dữ liệu hoặc format bị thay đổi.
- Response status hoặc schema bị xóa.
- Security requirement bị mở rộng hoặc thu hẹp.
- Server URL đổi ngoài kế hoạch.
- $ref trỏ tới component không còn tồn tại.

Snapshot test toàn bộ JSON có thể quá nhạy với thứ tự field, version thư viện hoặc metadata không ổn định. Tốt hơn là chuẩn hóa document trước khi so sánh hoặc assert các thuộc tính có ý nghĩa. Nếu dùng snapshot, hãy cập nhật snapshot có review khi thay đổi hợp đồng được chấp nhận.

Contract diff nên chạy trên từng group, không chỉ document mặc định. Một customizer toàn cục có thể làm thay đổi tất cả group cùng lúc.

## 15. Quy trình kiểm thử trong CI

Một pipeline phù hợp có thể thực hiện theo thứ tự:

1. Unit test hàm biến đổi OpenAPI model: kiểm tra field được thêm, field cũ được giữ và logic idempotent.
2. Khởi động Spring test context: xác nhận bean customizer và GroupedOpenApi được đăng ký.
3. Gọi endpoint JSON của từng group: kiểm tra metadata, paths, schema, $ref và security.
4. Gọi endpoint YAML nếu ứng dụng công bố YAML: parse và kiểm tra nội dung tương đương.
5. Chạy OpenAPI validator hoặc contract diff với phiên bản đặc tả được hỗ trợ.
6. Chạy test authorization runtime riêng cho endpoint nghiệp vụ và endpoint tài liệu.
7. Lưu tài liệu đã sinh làm artifact để review hoặc phân phối.

Không cần khởi chạy trình duyệt trong pipeline chỉ để xác nhận customizer. Nếu nhóm phát triển muốn kiểm thử Swagger UI, đó là một lớp smoke test giao diện bổ sung, không thay thế các kiểm tra hợp đồng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Unit test pass nhưng group không có metadata | Test chỉ gọi helper, bean không được gắn vào GroupedOpenApi | Thêm integration test gọi /v3/api-docs/{group} |
| Default document đúng nhưng group sai | Dùng OpenApiCustomizer thay vì GlobalOpenApiCustomizer hoặc group-level customizer | Chọn đúng phạm vi customizer và kiểm tra từng document |
| Contact xuất hiện nhưng title biến mất | Thay toàn bộ Info object | Chỉ cập nhật field cần thay đổi |
| Tag hoặc server bị lặp | Customizer thêm phần tử không kiểm tra tồn tại | Làm logic idempotent |
| $ref bị lỗi sau tùy biến | Component bị xóa hoặc không được thêm vào document của group | Kiểm tra components trong từng document |
| Security scheme đúng nhưng operation sai quyền | Nhầm scheme với security requirement | Kiểm tra cả hai cấp trong OpenAPI và test authorization runtime |
| Swagger UI trông đúng nhưng JSON sai | Chỉ kiểm tra giao diện hoặc giao diện không thể hiện hết metadata | Assert trực tiếp JSON/YAML |
| Snapshot thay đổi liên tục | Document có dữ liệu động hoặc thứ tự không ổn định | Chuẩn hóa và chỉ so sánh field có ý nghĩa |

## 17. Checklist trước khi hoàn tất customizer

- [ ] Xác định đúng loại customizer và phạm vi document.
- [ ] Unit test logic biến đổi OpenAPI model.
- [ ] Giữ nguyên metadata và component không thuộc phạm vi thay đổi.
- [ ] Kiểm tra customizer có thể chạy lặp mà không tạo dữ liệu trùng.
- [ ] Integration test gọi endpoint OpenAPI của document mặc định và từng group liên quan.
- [ ] Kiểm tra paths, request/response schemas và $ref.
- [ ] Kiểm tra servers, security scheme và security requirement.
- [ ] Kiểm tra JSON và YAML nếu cả hai được công bố.
- [ ] Chạy validator hoặc contract diff khi phù hợp.
- [ ] Kiểm tra authorization runtime độc lập với tài liệu.
- [ ] Không dùng trạng thái hiển thị của Swagger UI làm bằng chứng duy nhất.

Một customizer được kiểm thử tốt phải tạo ra tài liệu OpenAPI có cấu trúc đúng, giữ nguyên các phần ngoài phạm vi thay đổi và áp dụng đúng cho từng group. Khi test trực tiếp JSON/YAML và logic biến đổi model, nhóm phát triển có thể xác nhận hợp đồng API mà không phụ thuộc giao diện Swagger UI.

## Tài liệu tham khảo

- [springdoc-openapi – FAQ và customizer](https://springdoc.org/faq.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
