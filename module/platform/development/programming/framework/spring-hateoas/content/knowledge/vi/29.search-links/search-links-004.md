# Keyword parameter

Một search link cho phép client khám phá cách tìm kiếm tài nguyên bằng một hoặc nhiều từ khóa. Trong Spring HATEOAS, link này thường dùng relation **search** và URI template có query parameter, ví dụ **/products/search{?keyword}**. Client đọc tên biến keyword từ template, điền cụm từ tìm kiếm và mở URI đã mở rộng.

Tham số từ khóa là một phần của hợp đồng API. Server quyết định tên parameter, cách chuẩn hóa từ khóa, quy tắc tìm kiếm và các filter được hỗ trợ. Client không nên tự đoán route hoặc tự ghép chuỗi query; nó nên theo search link và mở rộng template mà server công bố.

## Search relation và keyword parameter

Một link có hai thành phần cơ bản:

- **Relation** cho biết link dùng để làm gì. Relation search chỉ ra điểm vào tìm kiếm.
- **Href** cho biết URI hoặc URI template mà client có thể truy cập.

Ví dụ HAL:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/products"
    },
    "search": {
      "href": "https://api.example.com/products/search{?keyword}",
      "templated": true
    }
  }
}
~~~

Phần **{?keyword}** là biểu thức URI template theo RFC 6570. Nó cho biết client có thể mở rộng URI bằng query parameter keyword. Khi client cung cấp giá trị **wireless keyboard**, URI được mở rộng thành một request có query tương ứng; ký tự đặc biệt và khoảng trắng phải được encode đúng cách.

Search link không phải là kết quả tìm kiếm. Nó là điểm vào mô tả cách client yêu cầu kết quả. Sau khi theo link, server trả collection kết quả và có thể cung cấp các link liên quan như self, next, filter hoặc item resource.

## Khai báo endpoint nhận keyword

Giả sử API quản lý sản phẩm có endpoint tìm kiếm theo từ khóa:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductSearchService searchService;
    private final ProductModelAssembler assembler;
    private final ProductCollectionAssembler collectionAssembler;

    ProductController(
            ProductSearchService searchService,
            ProductModelAssembler assembler,
            ProductCollectionAssembler collectionAssembler) {
        this.searchService = searchService;
        this.assembler = assembler;
        this.collectionAssembler = collectionAssembler;
    }

    @GetMapping
    CollectionModel<EntityModel<ProductRepresentation>> all() {
        return collectionAssembler.toModel(searchService.findAll());
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<ProductRepresentation>> search(
            @RequestParam("keyword") String keyword) {

        List<EntityModel<ProductRepresentation>> items =
            searchService.search(keyword).stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(items);
    }
}
~~~

**Product**, **ProductSearchService**, **ProductModelAssembler**, **ProductCollectionAssembler** và **ProductRepresentation** là các kiểu thuộc ứng dụng minh họa. Ví dụ giả định searchService.findAll() và searchService.search(keyword) trả về danh sách Product. Annotation **@RequestParam("keyword")** ánh xạ query parameter keyword vào đối số phương thức. Vì không đặt required=false, Spring MVC yêu cầu client gửi parameter này; nếu thiếu, request không hợp lệ và server thường trả 400 Bad Request.

Nếu muốn endpoint hỗ trợ cả truy vấn không có keyword, có thể khai báo **@RequestParam(name = "keyword", required = false)** và định nghĩa rõ hành vi khi giá trị null hoặc rỗng. Không đổi required chỉ để template trông linh hoạt hơn; quy tắc của controller, service và hypermedia metadata cần nhất quán.

## Tạo search link từ controller mapping

Spring HATEOAS cung cấp **WebMvcLinkBuilder** để tạo link từ mapping của controller. Cách này giúp URI tự cập nhật khi route hoặc context path thay đổi:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link search = linkTo(
    methodOn(ProductController.class).search("wireless keyboard")
).withRel(IanaLinkRelations.SEARCH);
~~~

Ví dụ trên tạo link cụ thể cho một cụm từ đã biết. Khi đối số method được đánh dấu bằng **@RequestParam**, Spring HATEOAS có thể đưa giá trị vào query string. Cách này phù hợp khi server đã có sẵn từ khóa, chẳng hạn khi tạo link quay lại kết quả tìm kiếm hiện tại.

Một search link dùng cho mọi từ khóa cần URI template thay vì giá trị cụ thể. Có thể lấy URI cơ sở từ mapping controller rồi thêm một request parameter template variable:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

Link search = Link.of(
    UriTemplate.of(
        linkTo(methodOn(ProductController.class).search(null))
            .toUri()
            .toString()
    ).with(TemplateVariable.requestParameter("keyword")),
    IanaLinkRelations.SEARCH
);
~~~

Lời gọi methodOn ở đây chỉ để Spring HATEOAS xác định mapping của phương thức search. Đối số null làm cho query value chưa được điền; TemplateVariable.requestParameter("keyword") bổ sung biến query để client cung cấp sau. Kết quả là link có relation search và href dạng URI template.

Nếu endpoint yêu cầu keyword, client phải cung cấp giá trị khi mở rộng template. Cú pháp URI template mô tả biến có thể được thay thế; nó không phải cơ chế validation và không tự công bố rằng query parameter bắt buộc. Khi cần mô tả rõ required cho giao diện, hãy dùng affordance metadata như phần HAL-FORMS bên dưới.

## Gắn search link vào collection representation

Search link thường được công bố trên collection resource để client có thể bắt đầu truy vấn:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
import org.springframework.stereotype.Component;

@Component
class ProductCollectionAssembler {

    private final ProductModelAssembler itemAssembler;

    ProductCollectionAssembler(ProductModelAssembler itemAssembler) {
        this.itemAssembler = itemAssembler;
    }

    CollectionModel<EntityModel<ProductRepresentation>> toModel(
            List<Product> products) {

        List<EntityModel<ProductRepresentation>> items = products.stream()
            .map(itemAssembler::toModel)
            .toList();

        Link self = linkTo(methodOn(ProductController.class).all())
            .withSelfRel();

        Link search = Link.of(
            UriTemplate.of(
                linkTo(methodOn(ProductController.class).search(null))
                    .toUri()
                    .toString()
            ).with(TemplateVariable.requestParameter("keyword")),
            IanaLinkRelations.SEARCH
        );

        return CollectionModel.of(items, self, search);
    }
}
~~~

Ví dụ giả định controller có phương thức **all()** trả collection sản phẩm và **search(String keyword)** nhận query parameter keyword. ProductCollectionAssembler chuyển từng Product thành EntityModel qua ProductModelAssembler, thêm self link cho collection và search link cho thao tác tìm kiếm.

Search link có thể được thêm bởi assembler, controller hoặc RepresentationModelProcessor. Hãy chọn một nơi chịu trách nhiệm rõ ràng để tránh thêm relation search nhiều lần. Với collection rỗng, search link vẫn hữu ích: client có thể tìm sản phẩm ngay cả khi collection hiện tại không có phần tử.

## Mở rộng URI template ở client

Client đọc link relation search và mở rộng biến keyword bằng giá trị người dùng nhập. Spring HATEOAS cung cấp phương thức **Link.expand(...)**:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link searchLink = collection.getRequiredLink(IanaLinkRelations.SEARCH);

URI target = searchLink.expand(
    Map.of("keyword", "wireless keyboard")
).toUri();
~~~

Client không cần biết đường dẫn là /products/search hay một route khác. Nó chỉ cần biết relation search và tên biến keyword trong template. Việc mở rộng URI template chịu trách nhiệm encode giá trị theo quy tắc URI; không nối chuỗi query bằng phép cộng để tránh lỗi với dấu cách, dấu &, dấu +, dấu tiếng Việt hoặc ký tự Unicode.

Sau khi mở rộng, client gửi GET tới URI kết quả với Accept phù hợp, chẳng hạn application/hal+json. Response là collection kết quả và có thể có pagination links để tiếp tục duyệt.

Nếu client dùng một HTTP client không tích hợp Spring HATEOAS, có thể dùng thư viện URI Template tương thích RFC 6570. Điều quan trọng là giữ nguyên template semantics và encode giá trị theo chuẩn.

## Tìm kiếm với nhiều query parameter

API thực tế thường cần keyword cùng các filter khác như category, status hoặc sort. Có thể thêm nhiều template variable:

Ở biến thể này, controller mở rộng phương thức search để nhận thêm category tùy chọn:

~~~java
import java.util.List;

@GetMapping("/search")
CollectionModel<EntityModel<ProductRepresentation>> search(
        @RequestParam("keyword") String keyword,
        @RequestParam(name = "category", required = false) String category) {
    List<EntityModel<ProductRepresentation>> items =
        searchService.search(keyword, category).stream()
            .map(assembler::toModel)
            .toList();

    return CollectionModel.of(items);
}
~~~

Khi tạo link, gọi methodOn với đúng chữ ký hai tham số để lấy mapping:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of(
    linkTo(methodOn(ProductController.class).search(null, null)).toUri().toString()
)
    .with(TemplateVariable.requestParameter("keyword"))
    .with(TemplateVariable.requestParameter("category"));

Link search = Link.of(template.toString(), IanaLinkRelations.SEARCH);
~~~

Client có thể cung cấp một hoặc nhiều biến:

~~~java
import java.net.URI;
import java.util.Map;

URI target = search.expand(Map.of(
    "keyword", "wireless keyboard",
    "category", "electronics"
)).toUri();
~~~

Nếu một biến không được cung cấp, cách mở rộng phụ thuộc loại template variable và URI template expression. Với request parameter template, biến không được cung cấp có thể bị bỏ khỏi query string. Tuy nhiên, endpoint có thể vẫn yêu cầu một tham số cụ thể; hãy bảo đảm metadata và hành vi server thống nhất.

Đối với tham số phân trang và sắp xếp, Spring HATEOAS hoặc PagedResourcesAssembler thường có thể tạo các link page/size/sort dựa trên request hiện tại. Không cần đưa tất cả tham số vào một search template thủ công nếu endpoint đã công bố pagination links riêng.

## Keyword trong affordance và HAL-FORMS

URI template cho biết client có thể thay thế keyword trong href. Nếu cần mô tả thêm phương thức HTTP, input property và tính bắt buộc của tham số, Spring HATEOAS có thể gắn affordance vào search link. API **Affordances** cho phép khai báo query parameter bằng **QueryParameter.required(...)** hoặc **QueryParameter.optional(...)**:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

var searchInvocation =
    methodOn(ProductController.class).search(null, null);

Link search = Affordances.of(
        linkTo(searchInvocation).withRel(IanaLinkRelations.SEARCH)
    )
    .afford(HttpMethod.GET)
    .withOutput(ProductRepresentation.class)
    .addParameters(
        QueryParameter.required("keyword"),
        QueryParameter.optional("category")
    )
    .withName("search")
    .toLink();
~~~

Ví dụ này mô tả một affordance GET có keyword bắt buộc và category tùy chọn. Để metadata phù hợp với endpoint, phương thức search cần khai báo keyword bắt buộc và category có thể bỏ qua, ví dụ:

~~~java
import java.util.List;

@GetMapping("/search")
CollectionModel<EntityModel<ProductRepresentation>> search(
        @RequestParam("keyword") String keyword,
        @RequestParam(name = "category", required = false) String category) {
    List<EntityModel<ProductRepresentation>> items =
        searchService.search(keyword, category).stream()
            .map(assembler::toModel)
            .toList();

    return CollectionModel.of(items);
}
~~~

Khi dùng media type HAL-FORMS, affordance có thể được serialize thành template với method GET và danh sách properties. Property keyword có metadata required; category là optional. Nếu chỉ dùng HAL JSON, client vẫn có thể theo search link và mở rộng URI template, nhưng không nhận đầy đủ form metadata như HAL-FORMS.

QueryParameter mô tả affordance cho client. Nó không thay thế việc khai báo @RequestParam hoặc kiểm tra input ở controller/service. Endpoint vẫn phải xác thực, chuẩn hóa và kiểm tra từ khóa khi nhận request.

## Xử lý keyword an toàn và nhất quán

Một keyword parameter cần có quy tắc rõ ràng để client khác nhau nhận kết quả nhất quán:

- **Tên parameter:** dùng một tên ổn định, ví dụ keyword hoặc q, và giữ nguyên trong URI template.
- **Giá trị trống:** quy định keyword rỗng có bị từ chối, bỏ qua hay trả collection rỗng.
- **Khoảng trắng:** xác định có trim khoảng trắng đầu/cuối trước khi tìm kiếm hay không.
- **Unicode:** hỗ trợ tiếng Việt và ký tự Unicode; không tự encode thủ công trước khi URI template mở rộng.
- **Phân biệt hoa thường:** nêu rõ tìm kiếm có phân biệt chữ hoa/thường hay không.
- **Độ dài tối đa:** giới hạn kích thước query để tránh request quá lớn.
- **Ngữ nghĩa tìm kiếm:** xác định tìm theo prefix, exact match, full-text hay nhiều trường.

Không đưa trực tiếp keyword vào câu SQL bằng cách nối chuỗi. Dùng parameter binding hoặc API truy vấn an toàn của repository để tránh SQL injection. Encoding URI chỉ bảo vệ cú pháp truyền tải; nó không làm cho truy vấn phía server an toàn nếu server xây SQL bằng nối chuỗi.

Nếu keyword có thể chứa nhiều từ, dấu &, dấu + hoặc ký tự tiếng Việt, hãy để URI template/client HTTP encode giá trị. Ví dụ, chuỗi "bàn phím cơ" cần được truyền như một giá trị query duy nhất; không tự thay dấu cách bằng dấu cộng hoặc encode hai lần.

## Search link và link collection có filter

Search relation thường trỏ tới endpoint nhận keyword, trong khi self link của kết quả trỏ tới view đã được thực hiện. Hai link có mục đích khác nhau:

| Relation | Ví dụ href | Ý nghĩa |
| --- | --- | --- |
| self | /products/search?keyword=keyboard | Kết quả tìm kiếm hiện tại |
| search | /products/search{?keyword} | Điểm vào để thực hiện tìm kiếm khác |
| next | /products/search?keyword=keyboard&page=1 | Trang kế tiếp của cùng kết quả |
| item self | /products/P-101 | Một sản phẩm cụ thể |

Không dùng relation self của kết quả hiện tại thay cho search link. Client cần search để bắt đầu truy vấn mới; self để tải lại view hiện tại; next để tiếp tục duyệt kết quả.

Nếu search trả về PagedModel, các link phân trang cần giữ keyword và filter hiện tại. Client nên theo next href do server tạo thay vì tự ghép keyword với page=1. Điều này giữ nguyên encoding, thứ tự tham số và mọi điều kiện truy vấn.

## Kiểm thử search link bằng MockMvc

Integration test nên xác nhận collection có relation search, href là template và tên biến đúng. Ví dụ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProductSearchLinkTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesKeywordSearchTemplate() throws Exception {
        mockMvc.perform(get("/products").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.search.templated").value(true))
            .andExpect(jsonPath("$._links.search.href")
                .value(org.hamcrest.Matchers.endsWith("/products/search{?keyword}")));
    }
}
~~~

Test giả định collection endpoint /products trả CollectionModel có search link được tạo như phần trước. Nếu ứng dụng dùng base path hoặc reverse proxy, kiểm tra suffix hoặc cấu hình URI công khai tương ứng thay vì hardcode host.

Kiểm thử endpoint với keyword có ký tự đặc biệt:

~~~java
mockMvc.perform(get("/products/search")
        .queryParam("keyword", "bàn phím cơ"))
    .andExpect(status().isOk());
~~~

Đoạn test giả định controller nhận keyword và service có thể xử lý fixture tương ứng. MockMvc queryParam giúp test truyền giá trị dưới dạng query parameter; không tự nối chuỗi URL trong test.

Nếu dùng HAL-FORMS affordance, thêm test xác nhận template search có method GET, property keyword được đánh dấu required và category là optional. Đồng thời test request thiếu keyword phải bị từ chối nếu controller khai báo @RequestParam bắt buộc.

## Những lỗi thường gặp

- **Tự ghép query string:** nối keyword vào URL bằng chuỗi làm sai encoding khi có ký tự đặc biệt.
- **Thiếu templated=true:** href chứa biến nhưng link không được đánh dấu là URI template.
- **Dùng sai relation:** đặt link tìm kiếm dưới self hoặc relation tùy ý khiến client không khám phá được search.
- **Không đồng bộ tên biến:** link dùng keyword nhưng controller nhận q hoặc name.
- **Nhầm template variable với required metadata:** URI template không tự cho client biết parameter bắt buộc; dùng affordance QueryParameter khi cần mô tả rõ.
- **Dùng giá trị null như một truy vấn thật:** methodOn với null chỉ dùng để xác định mapping, không phải gửi request tìm kiếm.
- **Mất filter khi phân trang:** client tự tạo next URL và bỏ keyword hoặc category.
- **Không chuẩn hóa input:** các client gửi khoảng trắng hoặc chuỗi rỗng dẫn tới kết quả khó dự đoán.
- **Nối keyword vào SQL:** encoding URI không ngăn SQL injection; luôn dùng parameter binding.
- **Công bố link nhưng endpoint không hỗ trợ:** search link phải trỏ tới mapping thực sự nhận đúng parameter.

Keyword parameter là cách client truyền tiêu chí tìm kiếm qua query string. Trong Spring HATEOAS, hãy tạo relation search từ mapping controller, biểu diễn keyword bằng URI template variable, và dùng QueryParameter.required/optional trong affordance khi cần metadata form chi tiết. Khi tên parameter, encoding, validation và pagination links được giữ nhất quán, client có thể khám phá và thực hiện tìm kiếm mà không phụ thuộc vào cấu trúc URL nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS – URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates)
- [Spring HATEOAS – Building links in Spring MVC và request parameters](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.mvc)
- [Spring HATEOAS – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS API – Affordances](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API – TemplateVariable](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/TemplateVariable.html)
- [Spring HATEOAS API – QueryParameter](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html)
- [RFC 6570 – URI Template](https://www.rfc-editor.org/rfc/rfc6570.html)
