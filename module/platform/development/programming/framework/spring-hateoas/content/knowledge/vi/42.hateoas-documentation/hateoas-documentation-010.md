# Kiểm tra tài liệu khớp API

Tài liệu API chỉ hữu ích khi mô tả đúng hành vi mà client thực sự nhận được. Một trang OpenAPI có thể ghi đúng URL và schema nhưng bỏ sót link next, relation approve hoặc affordance chỉ xuất hiện khi order ở trạng thái PENDING. Ngược lại, response runtime có thể đã đổi tên field, đổi status code hoặc thay đổi điều kiện công bố link trong khi tài liệu vẫn giữ ví dụ cũ.

Với Spring HATEOAS, việc kiểm tra tài liệu cần bao gồm cả HTTP contract và hypermedia contract. HTTP contract mô tả method, URI, request/response, status, header, media type và security. Hypermedia contract mô tả relation, đích của link, embedded resource, URI template, pagination và các hành động client có thể khám phá từ representation. Cần kiểm tra hai phần này dựa trên response thực tế và hành vi điều hướng của API.

## Tài liệu có thể lệch khỏi API như thế nào?

Contract drift (độ lệch hợp đồng) thường xuất hiện theo nhiều cách:

- Controller đổi path hoặc HTTP method nhưng trang tài liệu chưa cập nhật.
- DTO thêm, bỏ hoặc đổi kiểu field nhưng schema và ví dụ vẫn cũ.
- API đổi status code hoặc media type mà tài liệu chưa phản ánh.
- Assembler thêm relation mới, bỏ relation cũ hoặc thay href.
- Link approve chỉ xuất hiện cho role quản lý nhưng tài liệu ghi nó luôn có.
- Pagination đổi tên query parameter hoặc không giữ filter khi tạo next.
- Error response đổi sang Problem Details nhưng tài liệu vẫn minh họa JSON lỗi cũ.
- Security rule thay đổi nhưng OpenAPI vẫn đánh dấu endpoint là public.
- Một URI template được công bố như URI cố định, khiến client ghép tham số sai.

Không phải mọi khác biệt đều là lỗi. Một relation có thể vắng mặt hợp lệ khi trạng thái hoặc quyền không cho phép hành động. Tài liệu cần giải thích điều kiện xuất hiện của relation và test cần kiểm tra cả trường hợp có lẫn không có relation đó.

## Phân biệt HTTP contract, OpenAPI và hypermedia contract

Ba lớp thông tin có liên quan nhưng không thay thế nhau:

| Lớp | Nội dung chính | Cách kiểm tra |
| --- | --- | --- |
| HTTP contract | Path, method, parameter, header, status, media type, schema, security | OpenAPI và HTTP integration tests. |
| Hypermedia contract | _links, _embedded, relation, href, URI template, pagination, affordance | Spring REST Docs link snippets và runtime traversal tests. |
| Business behavior | Điều kiện nghiệp vụ khiến link/action xuất hiện hoặc biến mất | Tests theo state, principal, tenant và quyền. |

OpenAPI là định dạng mô tả HTTP API. Nó mô tả operation, parameter, request body, response, schema và security. OpenAPI cũng có Link Object để mô tả quan hệ giữa các operation trong tài liệu. Link Object này là liên kết ở cấp hợp đồng OpenAPI; nó không tự động đồng nghĩa với các relation động nằm trong HAL _links của response.

HAL công bố link relation ngay trong representation runtime. Client có thể theo self, next, collection hoặc relation mở rộng để khám phá tài nguyên tiếp theo. Danh sách relation có thể phụ thuộc state và authorization, vì vậy một schema OpenAPI tĩnh thường không đủ để chứng minh mọi link runtime đều đúng.

Với affordance, cần ghi rõ media type và cách serialize. HAL cơ bản định nghĩa cấu trúc link; thông tin mô tả form/action có thể được biểu diễn qua extension như HAL-FORMS hoặc ALPS tùy cấu hình. Không giả định mọi affordance trong mô hình Spring HATEOAS đều tự xuất hiện trong JSON HAL thuần.

## Chọn nguồn sự thật cho tài liệu

Một dự án có thể dùng code-first hoặc contract-first:

- **Code-first:** controller, DTO, annotation và test là nguồn triển khai; OpenAPI được sinh từ code bằng springdoc-openapi hoặc công cụ tương đương.
- **Contract-first:** OpenAPI hoặc schema được quản lý trước; controller và test phải thực hiện đúng contract đã duyệt.
- **Test-generated documentation:** Spring REST Docs tạo snippet từ request/response thật trong test. Test thất bại khi response không còn khớp các descriptor đã khai báo.

Các cách này có thể kết hợp. Ví dụ, OpenAPI mô tả operation và schema tổng quát; Spring REST Docs kiểm chứng response HAL và link relation; integration tests kiểm tra link có xuất hiện theo quyền và state hay không.

Điều quan trọng là xác định rõ file hoặc artifact nào là nguồn chính thức. Không nên để OpenAPI YAML, README, wiki và ví dụ Postman được sửa thủ công độc lập mà không có kiểm tra chéo.

## Dùng OpenAPI để mô tả HTTP contract

Với Spring MVC, springdoc-openapi có thể đọc mapping và annotation để tạo OpenAPI document. Các annotation thường dùng gồm:

- @Operation: mô tả operation và mục đích của endpoint.
- @Parameter: mô tả path/query/header parameter.
- @ApiResponse và @ApiResponses: mô tả status và response content.
- @Schema: mô tả field, kiểu dữ liệu, format và ví dụ.
- @SecurityRequirement: gắn yêu cầu security cho operation hoặc controller.

Ví dụ:

~~~java
import java.util.UUID;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderRepresentationService orderRepresentationService;

    OrderController(OrderRepresentationService orderRepresentationService) {
        this.orderRepresentationService = orderRepresentationService;
    }

    @Operation(
            operationId = "getOrder",
            summary = "Lấy representation của đơn hàng",
            description = "Trả order cùng các hypermedia link khả dụng.")
    @ApiResponses({
            @ApiResponse(
                    responseCode = "200",
                    description = "Tìm thấy đơn hàng",
                    content = @Content(
                            mediaType = "application/hal+json",
                            schema = @Schema(implementation = OrderModel.class))),
            @ApiResponse(
                    responseCode = "404",
                    description = "Không tìm thấy đơn hàng"),
            @ApiResponse(
                    responseCode = "500",
                    description = "Lỗi máy chủ")
    })
    @GetMapping(
            path = "/api/orders/{id}",
            produces = "application/hal+json")
    EntityModel<OrderModel> getOrder(
            @Parameter(description = "Định danh đơn hàng")
            @PathVariable UUID id) {
        return orderRepresentationService.findById(id);
    }
}
~~~

OrderModel và orderRepresentationService là kiểu ứng dụng do dự án định nghĩa. Ví dụ tập trung vào metadata của operation. Với EntityModel, hãy kiểm tra OpenAPI document được sinh ra: tùy phiên bản springdoc và cấu hình Spring HATEOAS, schema suy luận có thể chưa mô tả chính xác _links hoặc _embedded. Khi cần, khai báo schema wrapper riêng hoặc bổ sung schema/examples tường minh.

OpenAPI mặc định của springdoc thường được phục vụ tại /v3/api-docs; giao diện Swagger UI thường có tại /swagger-ui.html hoặc đường dẫn được cấu hình. Các đường dẫn này có thể thay đổi theo cấu hình ứng dụng. Trong CI, hãy tải document từ application test hoặc kiểm tra artifact được sinh ra, không chỉ nhìn giao diện UI.

## Mô tả HAL trong OpenAPI

Một schema HAL có thể mô tả phần data và cấu trúc link. Ví dụ giản lược:

~~~yaml
components:
  schemas:
    OrderHal:
      type: object
      required:
        - id
        - status
        - _links
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [PENDING, APPROVED, SHIPPED, CANCELLED]
        _links:
          type: object
          properties:
            self:
              $ref: '#/components/schemas/HalLink'
            collection:
              $ref: '#/components/schemas/HalLink'
            approve:
              $ref: '#/components/schemas/HalLink'
            cancel:
              $ref: '#/components/schemas/HalLink'
    HalLink:
      type: object
      required:
        - href
      properties:
        href:
          type: string
          format: uri
        templated:
          type: boolean
        type:
          type: string
        title:
          type: string
~~~

Schema trên chỉ minh họa một phần cấu trúc HAL trong components.schemas của OpenAPI document. Relation approve và cancel không nhất thiết có mặt trong mọi response. Không nên khai báo chúng là required nếu API chỉ công bố theo state hoặc quyền.

Nếu dùng CURIE hoặc relation URI mở rộng, tài liệu phải giải thích cách mở rộng relation và URI tài liệu của relation. Với URI template, mô tả templated: true và biến template. Client cần biết link là template để mở rộng đúng cách; không nên coi href có {?page,size} như URI đã hoàn chỉnh.

## Dùng Spring REST Docs để sinh tài liệu từ response thật

Spring REST Docs tạo snippet từ test chạy qua MockMvc, WebTestClient hoặc REST Assured. Khi request hoặc response thay đổi, test có thể thất bại nếu field, link hay parameter không còn khớp descriptor.

Với Spring HATEOAS, HypermediaDocumentation cung cấp link extractor cho HAL. Test có thể mô tả relation self, collection, next và các relation khác từ response thực tế.

Ví dụ cấu hình test:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.mockito.BDDMockito.given;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.halLinks;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

record OrderModel(UUID id, String status) {
}

@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs
class OrderDocumentationTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderRepresentationService orderRepresentationService;

    @Test
    void documentsOrderRepresentation() throws Exception {
        UUID orderId = UUID.fromString(
                "00000000-0000-0000-0000-000000000042");
        OrderModel model = new OrderModel(orderId, "PENDING");
        given(orderRepresentationService.findById(orderId))
                .willReturn(EntityModel.of(
                        model,
                        Link.of("/api/orders/" + orderId).withSelfRel()));

        mockMvc.perform(get("/api/orders/{id}",
                        orderId)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andDo(document("orders-get",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Định danh đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái hiện tại"),
                                subsectionWithPath("_links")
                                        .description("Các link hypermedia")),
                        links(halLinks(),
                                linkWithRel("self")
                                        .description("Representation hiện tại"),
                                linkWithRel("collection").optional()
                                        .description("Collection đơn hàng"))));
    }
}
~~~

Ví dụ giả định controller có test fixture hoặc mock service để trả order hợp lệ. subsectionWithPath("_links") mô tả phần link như một subsection; links(halLinks(), ...) kiểm tra các relation cụ thể và tạo snippet riêng. Nếu collection relation luôn bắt buộc trong endpoint này, bỏ optional() để test phát hiện khi link biến mất.

Trong ví dụ test, OrderModel là DTO có hai field id và status; OrderRepresentationService là bean được mock. Nếu ứng dụng bật Spring Security cho endpoint, thêm principal test phù hợp (ví dụ @WithMockUser) hoặc cấu hình test security theo chính sách của ứng dụng.

Spring REST Docs ghi snippet vào thư mục output đã cấu hình, thường là target/generated-snippets hoặc build/generated-snippets. Có thể dùng Asciidoctor để ghép các snippet thành tài liệu HTML/PDF. File tài liệu cuối cùng nên được tạo trong pipeline build để người đọc không dùng nhầm bản cũ.

## Chọn strict hay relaxed descriptors

Spring REST Docs có các descriptor strict và relaxed:

- responseFields(...) yêu cầu các field trong response được mô tả; field mới chưa có descriptor thường làm test thất bại.
- relaxedResponseFields(...) cho phép response có thêm field chưa được mô tả.
- links(...) kiểm tra tập link theo descriptor đã khai báo.
- relaxedLinks(...) cho phép có thêm relation ngoài danh sách mô tả.

Dùng strict descriptor cho contract mà client cần dựa vào. Dùng relaxed descriptor khi endpoint có nhiều extension relation hợp lệ hoặc khi test chỉ muốn tập trung một phần response. Không nên dùng relaxed ở mọi nơi để tránh test luôn xanh dù API đã thay đổi ngoài ý muốn.

Một cách thực tế là có hai nhóm test:

1. **Contract test strict:** kiểm tra field và relation cốt lõi, status, media type và headers.
2. **Exploration test:** cho phép extension links và kiểm tra một số quan hệ cụ thể mà client cần theo.

Nếu relation là optional theo state, dùng descriptor optional và viết test riêng chứng minh điều kiện xuất hiện/vắng mặt. Optional trong tài liệu không thay thế kiểm tra authorization hoặc business rule.

## Kiểm tra relation theo state và quyền

Một order có thể có representation khác nhau theo state:

| State | Relation có thể có | Relation không nên có |
| --- | --- | --- |
| PENDING, user có quyền duyệt | self, collection, approve, cancel | ship |
| PENDING, user chỉ được xem | self, collection | approve, cancel |
| APPROVED | self, collection, ship | approve |
| SHIPPED | self, collection, delivery | approve, ship |
| CANCELLED | self, collection | approve, cancel, ship |

Các relation trong bảng là ví dụ theo domain. Hợp đồng thực tế cần định nghĩa rõ semantics và điều kiện. Test nên tạo fixture riêng cho từng state và principal:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .with(user("reviewer").roles("ORDER_REVIEWER"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.approve.href").exists());

mockMvc.perform(get("/api/orders/{id}", orderId)
        .with(user("reader").roles("ORDER_READER"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.approve").doesNotExist());
~~~

Ví dụ cần import request post processor user từ SecurityMockMvcRequestPostProcessors và có Spring Security test support. Test data phải đảm bảo hai request đọc cùng order state để chỉ khác biệt về quyền. Cần test trực tiếp endpoint approve trong một test authorization riêng; ẩn link không phải cơ chế bảo vệ endpoint.

Không ghi tài liệu rằng relation luôn có chỉ vì nó xuất hiện trong một response mẫu. Hãy nói rõ relation có điều kiện và đưa ví dụ cho từng vai trò hoặc trạng thái quan trọng.

## Kiểm tra link traversal thực tế

Một response có href đúng cú pháp chưa chắc link hoạt động. Test traversal cần theo link mà server trả về thay vì tự ghép URI dựa trên giả định:

1. Gọi API root.
2. Đọc relation orders.
3. Theo href của relation đó để lấy collection.
4. Đọc một item và theo self link.
5. Theo action link khi điều kiện phù hợp.
6. Theo next và xác nhận filter/sort được giữ.

Ví dụ kiểm tra link self và collection bằng MockMvc:

~~~java
import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.springframework.test.web.servlet.MvcResult;

MvcResult result = mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

String selfHref = JsonPath.read(
        result.getResponse().getContentAsString(),
        "$._links.self.href");

mockMvc.perform(get(URI.create(selfHref).getPath())
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(orderId.toString()));
~~~

Ví dụ rút gọn giả định href cùng origin với MockMvc server. Nếu href là absolute URL, hãy dùng client test phù hợp để gọi URI đầy đủ hoặc tách path/query sau khi xác minh host hợp lệ. Không loại bỏ host một cách mù quáng trong test vì như vậy có thể che lỗi sinh absolute link sai origin.

Với pagination, lấy href từ _links.next rồi gọi lại chính href đó. Kiểm tra trang kế tiếp không lặp item, không bỏ filter và relation prev trỏ đúng trang trước. Không chỉ kiểm tra chuỗi page=1 vì server có thể đổi URI template hoặc query parameter theo hợp đồng.

## Kiểm tra URI template và CURIE

Nếu response có template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

Tài liệu cần nêu tên biến, kiểu dữ liệu, giá trị cho phép và cách encode. Test cần xác nhận templated là true và template chứa đúng biến được công bố. Client nên dùng URI Template library để mở rộng template thay vì nối chuỗi.

Nếu response có CURIE:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "order",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "order:approve": {
      "href": "https://api.example.com/orders/o-42/approval"
    }
  }
}
~~~

Tài liệu phải giải thích cách mở rộng order:approve thành URI relation đầy đủ, trang mô tả semantics và điều kiện sử dụng. Test cần kiểm tra CURIE declaration và relation extension khớp nhau.

## Kiểm tra affordance và form metadata

Nếu API dùng HAL-FORMS hoặc media type có affordance, tài liệu cần mô tả:

- Relation hoặc template đại diện hành động.
- HTTP method được công bố.
- Content type của request body.
- Các property bắt buộc/tùy chọn và kiểu dữ liệu.
- Giá trị mặc định hoặc lựa chọn hợp lệ nếu có.
- Điều kiện state/authorization khiến template xuất hiện.

Test cần gửi request theo metadata thực tế và xác nhận server chấp nhận hoặc từ chối đúng hợp đồng. Không suy ra hành động chỉ từ tên relation; method và schema phải được công bố theo định dạng mà client sử dụng.

HAL thuần không có cấu trúc form tiêu chuẩn như HAL-FORMS. Nếu endpoint chỉ trả application/hal+json, không mô tả affordance như thể client có thể đọc method và input schema từ một template mà response không thực sự chứa.

## Kiểm tra error contract và security documentation

Tài liệu thành công thường được chú ý nhiều hơn error response, nhưng client cũng phụ thuộc vào lỗi:

- Status code 400, 401, 403, 404, 409, 422, 429, 500 hoặc 503 theo hợp đồng.
- Media type application/problem+json khi dùng Problem Details.
- type, title, status, detail, instance và extension members ổn định.
- Retry-After, WWW-Authenticate, request ID hoặc trace correlation header khi có.
- Link help hoặc documentation relation nếu API công bố.

OpenAPI và Spring REST Docs phải mô tả đúng security scheme, authentication requirement và response 401/403. Test nên chạy với cả principal hợp lệ và không hợp lệ. Không ghi stack trace, SQL hoặc internal URL vào ví dụ tài liệu.

Với CORS, nếu client cần đọc response header như ETag, Link hoặc X-Request-Id, tài liệu triển khai phải nêu header nào được expose. CORS configuration không thay thế authorization và không làm link an toàn hơn.

## Kiểm tra schema compatibility

Khi API thay đổi, cần phân loại thay đổi trước khi cập nhật tài liệu:

| Thay đổi | Rủi ro tương thích thường gặp |
| --- | --- |
| Thêm response field tùy chọn | Thường additive nếu client bỏ qua field chưa biết. |
| Xóa hoặc đổi tên response field | Breaking với client đang đọc field cũ. |
| Đổi kiểu field | Có thể breaking ngay cả khi tên không đổi. |
| Thêm required request field | Breaking với client chưa gửi field đó. |
| Thay đổi enum response | Có thể làm client cũ không parse được giá trị mới. |
| Bỏ link relation hoặc đổi semantics | Breaking với client đang traversal relation đó. |
| Thêm relation tùy chọn | Thường additive nếu client bỏ qua relation chưa biết. |
| Đổi href hoặc query semantics | Có thể breaking dù relation name giữ nguyên. |
| Đổi status/media type/security requirement | Có thể thay đổi cách client xử lý response. |

Một thay đổi additive trong JSON vẫn có thể breaking ở hypermedia nếu client phụ thuộc relation đã bị bỏ hoặc href đổi semantics. Ngược lại, thêm relation tùy chọn thường không phá client tuân thủ nguyên tắc bỏ qua relation chưa biết.

Với OpenAPI, có thể dùng công cụ diff/compatibility checker trong CI để phát hiện breaking schema changes. Với HAL, cần bổ sung contract tests cho relation và traversal vì công cụ diff OpenAPI không nhất thiết nhìn thấy mọi hành vi runtime của assembler.

## Tích hợp kiểm tra tài liệu vào CI

Một pipeline có thể thực hiện:

~~~text
Compile
  |
  v
Unit + MVC integration tests
  |
  +--> Verify HTTP status, headers and media types
  |
  +--> Verify JSON fields and HAL relations
  |
  +--> Verify state/role-dependent links
  |
  +--> Generate Spring REST Docs snippets
  |
  v
Generate OpenAPI document
  |
  v
OpenAPI lint + compatibility diff
  |
  v
Assemble HTML documentation
  |
  v
Publish build artifact
~~~

Nên làm pipeline thất bại khi:

- Spring REST Docs thiếu field/link descriptor bắt buộc.
- Test traversal không theo được link được công bố.
- OpenAPI document không hợp lệ hoặc có breaking change chưa được duyệt.
- Ví dụ response không còn khớp JSON runtime.
- Endpoint thay đổi media type, security hoặc error response mà tài liệu chưa cập nhật.

Tài liệu được tạo ở CI phải có version/build identifier để biết nó khớp với artifact ứng dụng nào. Không chỉnh tay file snippet đã sinh; sửa test descriptor hoặc source documentation rồi chạy lại pipeline.

## Ví dụ kiểm tra tài liệu và runtime cùng nhau

Một test cho endpoint collection có thể xác minh content type, các field và pagination relation:

~~~java
mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray());
~~~

Test này xác nhận response có hình dạng cơ bản. Một test tài liệu Spring REST Docs đi kèm sẽ mô tả field và link. Một traversal test khác cần lấy href next từ response rồi gọi nó, kiểm tra filter status=PENDING được giữ. Ba kiểm tra này bổ sung cho nhau:

- Assertion xác nhận điều kiện runtime cụ thể.
- REST Docs ghi lại contract mà test đã quan sát.
- Traversal xác nhận link có thể dùng được từ góc nhìn client.

Đừng chỉ sinh tài liệu từ một fixture duy nhất. Hãy có fixture cho empty collection, collection có nhiều trang, state khác nhau và principal có quyền khác nhau. Một tài liệu có thể ghi relation optional, nhưng test vẫn phải xác minh khi nào relation có mặt và khi nào nó vắng mặt.

## Những lỗi thường gặp

| Cách làm sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dựa vào OpenAPI schema | Bỏ sót relation động và affordance runtime. | Kết hợp Spring REST Docs và traversal tests. |
| Cập nhật tài liệu thủ công sau mỗi release | Dễ quên hoặc mô tả sai response thực tế. | Sinh snippet từ test và kiểm tra OpenAPI trong CI. |
| Dùng relaxed descriptors ở mọi test | Field/link mới hoặc bị xóa không làm test thất bại. | Dùng strict contract tests cho phần cốt lõi. |
| Ghi relation có điều kiện như relation bắt buộc | Client hiểu sai khả năng ở state/quyền khác. | Ghi rõ điều kiện và test theo state/principal. |
| Chỉ kiểm tra href tồn tại | Link có thể trỏ sai route hoặc không giữ query. | Theo href trong traversal test. |
| Mô tả affordance nhưng response chỉ là HAL thuần | Client không tìm thấy method/input metadata. | Tài liệu đúng media type HAL-FORMS hoặc format thực tế. |
| Không kiểm tra error/security responses | Tài liệu thiếu thông tin cần thiết khi request thất bại. | Kiểm tra Problem Details, 401/403 và security scheme. |
| Sửa snippet đã sinh bằng tay | Lần build sau ghi đè và tài liệu không còn traceable. | Sửa test/source rồi sinh lại. |

## Quy trình kiểm tra tài liệu khớp API

1. Xác định nguồn contract chính thức: OpenAPI, annotations, tests hoặc schema được duyệt.
2. Liệt kê operation, status, media type, headers, request/response fields và security.
3. Liệt kê relation, URI template, embedded resource, pagination và affordance theo từng resource.
4. Xác định điều kiện state, principal và tenant làm relation thay đổi.
5. Viết integration tests quan sát response thực tế và Spring REST Docs descriptors.
6. Viết traversal tests theo href do server trả về.
7. Sinh OpenAPI và tài liệu HTML từ cùng build.
8. Chạy lint và compatibility diff để phát hiện breaking changes.
9. Gắn version/build metadata cho tài liệu được phát hành.
10. Chỉ công bố tài liệu sau khi các kiểm tra contract và runtime đều thành công.

## Nguyên tắc thiết kế

- Kiểm tra cả HTTP contract lẫn hypermedia contract.
- Dùng OpenAPI cho operation/schema/security và Spring REST Docs cho response/link quan sát được.
- Không nhầm OpenAPI Link Object với HAL _links runtime.
- Ghi rõ relation chuẩn, extension relation, URI template và điều kiện xuất hiện.
- Kiểm thử link theo state, principal, tenant và collection pagination.
- Theo href do server trả về thay vì tự ghép URI trong client test.
- Dùng strict descriptors cho contract cốt lõi; chỉ dùng relaxed khi có lý do.
- Kiểm tra error media type, status, headers và security scheme.
- Chạy OpenAPI lint/compatibility diff và contract tests trong CI.
- Sinh tài liệu từ đúng build artifact sẽ phát hành.

Kiểm tra tài liệu khớp API là một phần của kiểm thử hợp đồng. OpenAPI mô tả bề mặt HTTP; Spring REST Docs ghi lại request, response và relation được quan sát; traversal tests chứng minh client có thể đi theo link thực tế. Khi kết hợp ba góc nhìn này, tài liệu Spring HATEOAS phản ánh được cả cấu trúc representation lẫn khả năng điều hướng mà API đang cung cấp.
