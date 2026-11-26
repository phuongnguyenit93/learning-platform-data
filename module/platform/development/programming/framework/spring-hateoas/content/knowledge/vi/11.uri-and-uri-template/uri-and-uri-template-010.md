# Kiểm thử URI

Trong Spring HATEOAS, URI được tạo từ mapping controller và được đưa vào Link để client điều hướng giữa các tài nguyên. Khi mapping, path variable, query parameter, context path hoặc cấu hình reverse proxy thay đổi, link trong response cũng có thể thay đổi. Vì vậy, kiểm thử URI là một phần quan trọng để bảo vệ hợp đồng hypermedia.

Một bài kiểm thử tốt cần xác nhận URI trỏ đúng tài nguyên, relation được gắn đúng, URI template có đúng biến và khi mở rộng template thì các giá trị được mã hóa hợp lệ. Với link được tạo từ controller mapping, kiểm thử còn cần phát hiện việc đổi route làm sai link hoặc làm mất query parameter. Bài học này trình bày cách kiểm thử Link, UriTemplate, WebMvcLinkBuilder, response HAL và các trường hợp triển khai có context path hoặc reverse proxy.

## 1. Mục tiêu của kiểm thử URI

URI trong API hypermedia có thể được tạo thủ công, sinh từ controller mapping hoặc chứa biến template. Mỗi trường hợp cần kiểm tra một nhóm đặc tính khác nhau.

| Đối tượng cần kiểm thử | Điều cần xác nhận |
|---|---|
| Link thông thường | href hợp lệ và relation đúng |
| Link self | URI trỏ đến chính tài nguyên hiện tại |
| Link đến tài nguyên liên quan | Đường dẫn và relation phản ánh đúng quan hệ nghiệp vụ |
| URI có path variable | Giá trị định danh được đưa vào đúng vị trí và mã hóa đúng |
| URI template | Có đúng tên biến, loại biến và có thể mở rộng |
| Query parameter | Tên, giá trị và cách biểu diễn nhiều giá trị đúng hợp đồng |
| Link từ controller mapping | URI theo mapping hiện tại, không bị hard-code sai |
| URI trong response HAL | Client nhận đúng href, rel và metadata |
| URI sau proxy/context path | Scheme, host, port và base path phản ánh địa chỉ công khai |

Không nên chỉ kiểm tra một chuỗi URI tuyệt đối trong mọi trường hợp. Host, scheme, port và context path có thể khác nhau giữa môi trường test, staging và production. Hãy xác định phần nào là hợp đồng cố định, phần nào phụ thuộc môi trường rồi viết assertion tương ứng.

## 2. Kiểm thử Link trực tiếp

Spring HATEOAS cung cấp Link như một value object. Có thể kiểm tra href, relation và trạng thái templated mà không cần khởi động web server.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

import static org.assertj.core.api.Assertions.assertThat;

class LinkTest {

    @Test
    void createsSelfLink() {
        Link link = Link.of(
            "/orders/ORD-42",
            IanaLinkRelations.SELF
        );

        assertThat(link.getHref()).isEqualTo("/orders/ORD-42");
        assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
        assertThat(link.isTemplated()).isFalse();
    }
}
~~~

Test này kiểm tra ba đặc tính cơ bản:

- href trỏ đến URI dự kiến.
- rel là relation self.
- Link không chứa URI template.

Với relation tùy chỉnh, có thể kiểm tra bằng LinkRelation:

~~~java
Link link = Link.of(
    "/customers/CUS-7",
    "customer"
);

assertThat(link.getRel().value()).isEqualTo("customer");
assertThat(link.getHref()).isEqualTo("/customers/CUS-7");
~~~

Khi test relation, nên xác nhận cả relation lẫn href. Một URI đúng nhưng gắn nhầm relation vẫn có thể làm client điều hướng sai về mặt ngữ nghĩa.

## 3. Kiểm thử URI template

URI template là một mẫu URI có các biến cần được thay thế trước khi gửi request. Spring HATEOAS cung cấp UriTemplate để tạo, đọc và mở rộng mẫu URI.

Ví dụ mẫu có path variable và query variable:

~~~java
import org.springframework.hateoas.UriTemplate;

UriTemplate template =
    UriTemplate.of("/orders/{id}{?projection,page}");

assertThat(template.getVariableNames())
    .containsExactly("id", "projection", "page");
~~~

getVariableNames() cho biết các biến được phát hiện trong template. Kiểm thử danh sách này giúp phát hiện trường hợp đổi tên biến hoặc vô tình bỏ một biến khỏi URI.

Có thể kiểm tra một chuỗi có phải URI template hay không bằng UriTemplate.isTemplate(...):

~~~java
assertThat(UriTemplate.isTemplate("/orders/{id}")).isTrue();
assertThat(UriTemplate.isTemplate("/orders/ORD-42")).isFalse();
~~~

Nếu API dùng Link thay vì thao tác trực tiếp trên UriTemplate, có thể kiểm tra các thuộc tính tương ứng trên Link:

~~~java
Link search = Link.of("/orders{?status,page}", "search");

assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
    .containsExactly("status", "page");
~~~

Nên kiểm thử biến template theo tên và ý nghĩa. Tránh chỉ so sánh chuỗi template trong mọi test nếu thứ tự biến không phải một phần hợp đồng API.

## 4. Kiểm thử mở rộng URI template

Template chỉ hữu ích khi client có thể thay thế biến để tạo URI cuối cùng. UriTemplate.expand(...) nhận giá trị theo thứ tự biến hoặc nhận Map theo tên biến.

~~~java
import java.net.URI;
import java.util.Map;

UriTemplate template =
    UriTemplate.of("/orders/{id}{?projection,page}");

URI expanded = template.expand(Map.of(
    "id", "ORD-42",
    "projection", "summary",
    "page", 2
));

assertThat(expanded.getPath()).isEqualTo("/orders/ORD-42");
assertThat(expanded.getQuery())
    .contains("projection=summary")
    .contains("page=2");
~~~

Map giúp test không phụ thuộc thứ tự tham số trong lời gọi. Khi template có nhiều biến, cách này dễ đọc và giảm rủi ro gán nhầm giá trị.

Cũng có thể kiểm tra Link.expand(...):

~~~java
Link templateLink = Link.of(
    "/orders{?status,page}",
    "search"
);

Link expandedLink = templateLink.expand(Map.of(
    "status", "PROCESSING",
    "page", 2
));

assertThat(expandedLink.isTemplated()).isFalse();
assertThat(expandedLink.getHref())
    .contains("status=PROCESSING")
    .contains("page=2");
assertThat(expandedLink.getRel()).isEqualTo(templateLink.getRel());
~~~

Sau khi mở rộng đủ biến cần thiết, link kết quả không còn là template chưa mở rộng. Relation vẫn cần được giữ nguyên vì việc thay giá trị URI không làm thay đổi ngữ nghĩa của link.

Nếu một biến query là tùy chọn và không được truyền, template có thể bỏ biến đó khỏi URI kết quả. Hãy viết test cho cả trường hợp có và không có biến tùy chọn để xác nhận hành vi mà client mong đợi.

## 5. Kiểm thử mã hóa path variable và query parameter

Giá trị đưa vào URI có thể chứa khoảng trắng, dấu tiếng Việt, dấu cộng, dấu gạch chéo hoặc ký tự dành riêng. Việc ghép chuỗi thủ công dễ tạo URI sai hoặc thay đổi ý nghĩa của giá trị.

Dùng UriTemplate để kiểm tra mã hóa path variable:

~~~java
URI uri = UriTemplate.of("/orders/{id}")
    .expand(Map.of("id", "ORD 42"));

assertThat(uri.getRawPath()).contains("ORD%2042");
~~~

getRawPath() trả về path ở dạng mã hóa. Nếu test dùng getPath(), URI có thể trả về giá trị đã giải mã; hãy chọn getter phù hợp với điều cần xác nhận.

Với query parameter, kiểm tra giá trị sau khi phân tích query hoặc kiểm tra raw query khi muốn xác nhận encoding:

~~~java
URI uri = UriTemplate.of("/orders{?keyword}")
    .expand(Map.of("keyword", "đơn hàng mới"));

assertThat(uri.getRawQuery()).isNotBlank();
assertThat(uri.getRawQuery()).contains("keyword=");
~~~

Không nên tự giả định mọi ký tự được mã hóa theo cùng một cách trong path và query. Hãy kiểm tra theo chuẩn URI và contract của ứng dụng. Đặc biệt, dấu cộng có thể mang ý nghĩa khác nhau tùy cách giải mã query; test nên xác nhận giá trị cuối cùng mà controller nhận được nếu encoding là phần quan trọng của use case.

Với collection-valued query parameter, Spring MVC có thể biểu diễn nhiều giá trị theo dạng lặp lại tên parameter hoặc dạng phân tách bằng dấu phẩy. Cách render phụ thuộc cấu hình và annotation như @NonComposite. Nếu endpoint hỗ trợ danh sách giá trị, hãy kiểm thử cả cách tạo link lẫn cách server parse query.

## 6. Kiểm thử URI sinh từ WebMvcLinkBuilder

WebMvcLinkBuilder tạo link dựa trên mapping controller. Đây là cách giảm phụ thuộc vào URL viết thủ công, nhưng vẫn cần test để bảo đảm link trỏ đúng mapping.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // Trả biểu diễn đơn hàng
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> search(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Integer page) {
        // Trả tập hợp theo bộ lọc
    }
}
~~~

Test tạo link self từ method mapping:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

class OrderLinkTest {

    @Test
    void createsLinkFromControllerMapping() {
        UUID id = UUID.fromString(
            "7f2d8a6e-3f16-4f41-9a73-1f0b4e6c9a20"
        );

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/orders");
        request.setScheme("https");
        request.setServerName("api.example.test");
        request.setServerPort(443);
        RequestContextHolder.setRequestAttributes(
            new ServletRequestAttributes(request)
        );

        try {
            Link link = linkTo(
                methodOn(OrderController.class).one(id)
            ).withSelfRel();

            assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
            assertThat(link.getHref()).endsWith("/orders/" + id);
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }
}
~~~

methodOn(...) tạo proxy ghi nhận lời gọi controller để Spring HATEOAS đọc mapping và tham số URI. Nó không thực thi logic nghiệp vụ của method. LinkBuilder sử dụng mapping để tạo href.

Test dùng endsWith(...) để không khóa cứng scheme, host và port do request context có thể thay đổi. Nếu base URI là một phần bắt buộc của hợp đồng trong môi trường triển khai, hãy có test tích hợp riêng để xác nhận đầy đủ URI.

Lưu ý: khi dùng methodOn(...), các tham số thường được bỏ qua ngoại trừ những tham số được dùng làm path variable. Request parameter được xử lý theo metadata mapping để tạo URI template. Vì vậy, test template cần kiểm tra tên biến được sinh ra, không chỉ truyền giá trị vào methodOn rồi kỳ vọng mọi tham số đều trở thành giá trị cố định trong href.

## 7. Kiểm thử query template được sinh từ controller

Một endpoint tìm kiếm thường có các query parameter tùy chọn. Link đến endpoint này có thể công bố template để client tự điền giá trị.

Ví dụ tạo search link:

~~~java
Link search = linkTo(
    methodOn(OrderController.class).search(null, null)
).withRel("search");

assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
    .contains("status", "page");
~~~

Đoạn tạo link bằng WebMvcLinkBuilder cần được chạy trong request context, giống môi trường controller đang xử lý request. Trong unit test, thiết lập MockHttpServletRequest và RequestContextHolder như ví dụ ở mục trước; trong integration test, thực hiện request qua MockMvc để Spring tự thiết lập ngữ cảnh.

Test nên xác nhận:

1. Link có trạng thái templated.
2. Các tên biến đúng với query parameter mà API công bố.
3. Không có biến thừa do thay đổi mapping.
4. Mở rộng template tạo query string có thể được endpoint nhận.
5. Giá trị tùy chọn được bỏ qua hoặc giữ lại đúng quy tắc.

Có thể mở rộng và kiểm tra:

~~~java
Link expanded = search.expand(Map.of(
    "status", "PROCESSING",
    "page", 2
));

URI uri = URI.create(expanded.getHref());

assertThat(uri.getQuery())
    .contains("status=PROCESSING")
    .contains("page=2");
~~~

Nếu test muốn xác nhận server thực sự nhận được query, hãy gửi URI đã mở rộng qua MockMvc và kiểm tra kết quả lọc hoặc tham số service. Đây là test tích hợp bổ sung cho test tạo template.

## 8. Kiểm thử URI trong response HAL bằng MockMvc

Test Link object xác nhận logic tạo link ở mức Java. MockMvc kiểm tra response HTTP sau khi controller, assembler, serializer và content negotiation phối hợp.

Ví dụ:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href",
        endsWith("/orders/" + orderId)))
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Đối với link template, có thể kiểm tra metadata templated và href:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href").exists());
~~~

Nếu serializer và relation provider có cấu hình cụ thể, test có thể kiểm tra chính xác tên relation trong JSON. Hãy coi tên relation, sự hiện diện của link và cấu trúc URI là một phần hợp đồng API.

Không nên chỉ kiểm tra response có thuộc tính _links. Một response có _links nhưng thiếu self hoặc dùng sai relation vẫn không đáp ứng mục tiêu điều hướng hypermedia.

## 9. Kiểm thử base URI, context path và reverse proxy

WebMvcLinkBuilder lấy thông tin URI cơ sở từ request hiện tại. Vì thế link có thể bao gồm scheme, host, port và context path của request. Trong production, ứng dụng có thể chạy sau reverse proxy hoặc API gateway; địa chỉ nội bộ có thể khác địa chỉ client truy cập.

Các trường hợp cần kiểm thử:

- HTTP và HTTPS: link có scheme phù hợp với request hoặc cấu hình proxy.
- Host: href sử dụng host công khai khi hệ thống được triển khai sau gateway.
- Port: port mặc định và port không mặc định được xử lý đúng.
- Context path: ứng dụng chạy dưới prefix như /shop hoặc /api.
- Forwarded headers: X-Forwarded-Host, X-Forwarded-Proto hoặc Forwarded được xử lý theo cấu hình tin cậy.
- Mapping lồng nhau: path variable được nối đúng sau context path.

Với MockMvc, có thể kiểm thử link trong request context của ứng dụng. Ví dụ:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").value(
        org.hamcrest.Matchers.endsWith("/orders/" + orderId)
    ));
~~~

Nếu ứng dụng có context path hoặc proxy header, hãy cấu hình chúng trong test setup và kiểm tra phần URI tương ứng. Không nên thêm forwarded header vào mọi test một cách tùy tiện; test cần mô phỏng đúng cấu hình proxy của môi trường triển khai.

Spring WebFlux dùng request context reactive và WebFluxLinkBuilder. Nếu endpoint chạy trên WebFlux, hãy dùng WebTestClient và WebFluxLinkBuilder để kiểm thử link; không dùng WebMvcLinkBuilder chỉ để tái sử dụng một test MVC.

## 10. Kiểm thử URI trong Spring WebFlux

Với WebFlux, controller trả về Mono hoặc Flux và link có thể được tạo bằng WebFluxLinkBuilder. WebTestClient kiểm tra response HTTP và HAL JSON.

Ví dụ:

~~~java
webTestClient.get()
    .uri("/orders/{id}", orderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
    .expectBody()
    .jsonPath("$._links.self.href").exists()
    .jsonPath("$._links.orders.href").exists();
~~~

Nếu cần kiểm tra body thành representation model thay vì JSONPath, có thể áp dụng HypermediaWebTestClientConfigurer cho WebTestClient. Sau đó dùng TypeReferences.EntityModelType hoặc CollectionModelType để giải mã response theo kiểu Spring HATEOAS.

Ví dụ cấu hình:

~~~java
WebTestClient client = builder
    .apply(hypermediaConfigurer)
    .build();

client.get()
    .uri("/orders/{id}", orderId)
    .exchange()
    .expectStatus().isOk()
    .expectBody(new TypeReferences.EntityModelType<OrderRepresentation>() {})
    .consumeWith(result -> {
        EntityModel<OrderRepresentation> model = result.getResponseBody();

        assertThat(model).isNotNull();
        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
    });
~~~

WebTestClient là immutable value type. apply(...) trên builder tạo cấu hình client; nếu sử dụng một client đã tạo, cần giữ client đã được mutate thay vì giả định cấu hình tự thay đổi trên instance cũ.

Với WebFlux, việc tạo link nên nằm trong reactive pipeline hoặc dùng ServerWebExchange tường minh khi cần. Kiểm thử tích hợp cần xác nhận link được tạo với request context đúng, đặc biệt khi ứng dụng chạy sau proxy.

## 11. Kiểm thử regression khi mapping thay đổi

Một lợi ích của việc tạo link từ controller mapping là URI không bị sao chép thủ công ở nhiều nơi. Tuy nhiên, khi mapping thay đổi, test cần phát hiện thay đổi đó có ảnh hưởng đến hợp đồng client hay không.

Ví dụ, route cũ:

~~~java
@GetMapping("/orders/{id}")
~~~

được thay thành:

~~~java
@GetMapping("/sales/orders/{id}")
~~~

Nếu hợp đồng cho phép thay đổi URI và client theo self link, test nên xác nhận self trỏ đến route mới. Nếu một client cụ thể vẫn phụ thuộc route cũ, thay đổi đó có thể là breaking change và cần versioning hoặc chuyển tiếp.

Nên tổ chức test thành hai nhóm:

- **Test cấu trúc link**: relation self, customer, orders, cancel có tồn tại đúng điều kiện.
- **Test URI mapping**: href kết thúc bằng hoặc khớp path mà mapping hiện tại công bố.

Khi thay mapping, cập nhật test dựa trên quyết định hợp đồng API. Không nên sửa assertion một cách máy móc chỉ để làm test xanh; trước tiên cần xác định URI mới có tương thích với client hay không.

## 12. Các lỗi thường gặp khi kiểm thử URI

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| So sánh tuyệt đối host và port trong mọi unit test | Test phụ thuộc môi trường | Kiểm tra path hoặc tách test base URI |
| Chỉ kiểm tra href mà bỏ qua rel | Link có thể trỏ đúng URI nhưng sai ngữ nghĩa | Kiểm tra cả href và relation |
| Không kiểm tra tên biến template | Client không thể mở rộng template theo hợp đồng | Kiểm tra getVariableNames() |
| Dùng URI.create() trực tiếp với template còn dấu ngoặc nhọn | URI parser có thể từ chối ký tự template chưa mở rộng | Mở rộng template trước rồi mới parse URI |
| Tự nối chuỗi để kiểm tra URI | Test lặp lại logic tạo URI và có thể che lỗi | Dùng UriTemplate hoặc link builder |
| Bỏ qua encoding | Giá trị chứa ký tự đặc biệt làm URI sai | Kiểm tra raw path/query và giá trị server nhận |
| Chỉ test Link object | Không phát hiện lỗi serializer hoặc content negotiation | Bổ sung test HTTP với MockMvc/WebTestClient |
| Không kiểm thử context path/proxy | Link production có thể chứa địa chỉ nội bộ | Tạo test tích hợp theo cấu hình triển khai |
| Dùng sai builder giữa MVC và WebFlux | Link không lấy đúng request context | Chọn builder theo web stack |

## 13. Checklist cho một bộ kiểm thử URI

Trước khi hoàn thành endpoint hypermedia, hãy xác nhận:

1. Link self có relation self và href trỏ đúng tài nguyên.
2. Link đến tài nguyên liên quan có relation và path đúng.
3. Path variable được đưa vào đúng vị trí và mã hóa hợp lệ.
4. Query template có đủ tên biến cần công bố.
5. Mở rộng template tạo URI hợp lệ và giữ đúng relation.
6. Query parameter tùy chọn và nhiều giá trị được xử lý đúng.
7. Response HAL công bố href và relation như hợp đồng.
8. Context path, scheme, host và proxy header được kiểm thử khi có sử dụng.
9. Mapping thay đổi được phát hiện bởi regression test.
10. MVC dùng MockMvc/WebMvcLinkBuilder; WebFlux dùng WebTestClient/WebFluxLinkBuilder.

Kiểm thử URI giúp bảo vệ phần điều hướng của REST API, nơi client phụ thuộc vào link mà server công bố để khám phá tài nguyên. Kết hợp unit test cho Link và UriTemplate với integration test cho controller và response HAL sẽ phát hiện cả lỗi tạo URI lẫn lỗi tuần tự hóa. Khi test tập trung vào relation, path, biến template và ngữ cảnh request, hợp đồng hypermedia có thể tiến hóa có kiểm soát mà không buộc client phải tự đoán cấu trúc URL.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [UriTemplate API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html)
- [Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [WebFluxLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [URI Template – RFC 6570](https://www.rfc-editor.org/rfc/rfc6570)

