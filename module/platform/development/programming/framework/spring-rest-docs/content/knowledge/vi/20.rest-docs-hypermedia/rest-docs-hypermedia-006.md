# Document embedded resources và liên kết lồng nhau

## 1. Embedded resource và link lồng nhau trong HAL

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Với API hypermedia, response có thể chứa dữ liệu của tài nguyên hiện tại, các tài nguyên được nhúng và những liên kết cho phép client điều hướng giữa chúng. Snippet giúp mô tả cả payload lẫn cấu trúc liên kết; sau đó được ghép thành Asciidoctor/Markdown và đưa vào build, CI.

Trong HAL, hai vùng dữ liệu quan trọng là:

- _embedded: chứa các resource được nhúng trực tiếp trong representation hiện tại.
- _links: chứa các link điều hướng ở cấp representation đó.

Ví dụ response danh sách cửa hàng:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Cửa hàng trung tâm",
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      },
      {
        "id": 12,
        "name": "Cửa hàng phía Đông",
        "_links": {
          "self": {"href": "/api/stores/12"},
          "products": {"href": "/api/stores/12/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"},
    "next": {"href": "/api/stores?page=1"}
  }
}
~~~

Response có nhiều cấp:

| Vị trí | Nội dung | Ví dụ relation/link |
| --- | --- | --- |
| Root representation | Collection cửa hàng | self, next |
| Mỗi embedded store | Dữ liệu một cửa hàng | id, name |
| _links của từng store | Điều hướng từ cửa hàng đó | self, products |

Nếu chỉ document root links, tài liệu bỏ qua các relation nằm trong từng phần tử _embedded.stores. Nếu chỉ mô tả link lồng nhau, client không thấy link phân trang của collection. Cần xác định đúng cấp dữ liệu muốn tài liệu hóa.

## 2. Mô tả payload và links riêng theo từng cấp

Với response HAL lồng nhau, nên chia công việc thành hai phần:

1. Dùng payload descriptors để mô tả embedded resource: các field, kiểu dữ liệu và subsection.
2. Dùng link descriptors để mô tả quan hệ ở root và ở từng embedded resource.

Các API thường sử dụng:

| API | Mục đích |
| --- | --- |
| subsectionWithPath("_embedded.stores") | Mô tả cả vùng embedded như một subsection trong bảng field. |
| beneathPath("_embedded.stores[]") | Chuyển ngữ cảnh mô tả vào từng phần tử store trong mảng. |
| fieldWithPath("id") | Mô tả field bên trong subsection hiện tại. |
| links(...) | Mô tả link tại root của operation. |
| links(beneathPath(...), ...) | Mô tả link nằm bên trong một subsection của payload. |
| linkWithRel("products") | Chọn relation theo tên rel ở cấp đang được trích xuất. |

Điểm quan trọng: beneathPath(...) không tạo embedded resource và cũng không thay đổi response. Nó chỉ tạo ngữ cảnh trích xuất con để snippet mô tả phần payload cần quan tâm. Tương tự, link descriptor chỉ đọc các link đã xuất hiện trong response.

## 3. Chuẩn bị Spring HATEOAS representation

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring MVC, Spring HATEOAS, JUnit Jupiter và Spring REST Docs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management nên quản lý phiên bản Spring HATEOAS và Spring REST Docs tương thích. Dự án không dùng BOM cần chọn phiên bản theo Spring Framework đang sử dụng.

Một collection representation có thể được tạo bằng CollectionModel chứa các EntityModel:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class StoreController {

    @GetMapping(value = "/api/stores", produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<EntityModel<Store>> listStores() {
        EntityModel<Store> first = EntityModel.of(
                new Store(11L, "Cửa hàng trung tâm"),
                linkTo(methodOn(StoreController.class).getStore(11L)).withSelfRel(),
                linkTo(methodOn(ProductController.class).listByStore(11L))
                        .withRel("products"));

        EntityModel<Store> second = EntityModel.of(
                new Store(12L, "Cửa hàng phía Đông"),
                linkTo(methodOn(StoreController.class).getStore(12L)).withSelfRel(),
                linkTo(methodOn(ProductController.class).listByStore(12L))
                        .withRel("products"));

        return CollectionModel.of(List.of(first, second),
                linkTo(methodOn(StoreController.class).listStores()).withSelfRel());
    }
}
~~~

Đây là ví dụ biểu diễn ý tưởng; Store, getStore(...) và ProductController.listByStore(...) cần được định nghĩa trong ứng dụng. Có thể thêm link phân trang ở root bằng withRel("next") khi trang kế tiếp tồn tại. Mỗi EntityModel giữ link của chính embedded store; CollectionModel giữ link của collection.

Để serializer trả HAL, endpoint cần media type HAL và cấu hình Spring HATEOAS tương ứng. Trong bài kiểm thử, xác nhận Content-Type thực tế trước khi khai báo descriptor.

## 4. Document embedded fields bằng beneathPath(...)

Giả sử response có cấu trúc:

~~~json
{
  "_embedded": {
    "stores": [
      {"id": 11, "name": "Cửa hàng trung tâm"},
      {"id": 12, "name": "Cửa hàng phía Đông"}
    ]
  }
}
~~~

Có thể mô tả từng phần tử trong mảng bằng payload subsection extractor:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
        beneathPath("_embedded.stores[]"),
        fieldWithPath("id").description("Mã cửa hàng"),
        fieldWithPath("name").description("Tên cửa hàng"))
~~~

beneathPath("_embedded.stores[]") làm cho các descriptor id và name được hiểu tương đối với từng phần tử store. Nhờ vậy snippet fields tập trung vào cấu trúc embedded item thay vì phải lặp đường dẫn đầy đủ ở mọi descriptor.

### Mô tả subsection như một khối

Nếu chỉ muốn thông báo response có một vùng embedded mà không liệt kê mọi field:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
        subsectionWithPath("_embedded.stores")
                .description("Danh sách cửa hàng được nhúng trong response"))
~~~

Ví dụ minh họa mô tả subsection ở root; các descriptor khác cần được bổ sung theo toàn bộ cấu trúc response thực tế nếu đang dùng chế độ strict. subsectionWithPath(...) mô tả một vùng như một đơn vị. Nó không thay thế ví dụ chi tiết khi người đọc cần biết các field bên trong từng store.

### Chọn cách mô tả phù hợp

| Mục tiêu tài liệu | Cách dùng |
| --- | --- |
| Chỉ cho biết có embedded collection | subsectionWithPath("_embedded.stores") |
| Liệt kê field của từng phần tử | beneathPath("_embedded.stores[]") cùng fieldWithPath(...) |
| Mô tả field sâu trong item | Dùng descriptor tương đối như address.city sau khi chọn đúng subsection |
| Mô tả root response đầy đủ | Kết hợp descriptor root và subsection/field theo cấu trúc JSON thực tế |

## 5. Mô tả link ở cấp root và embedded resource

Trong response ví dụ, root có self và next; từng store có self và products. Bảng links ở root có thể được khai báo riêng:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;

links(
        linkWithRel("self").description("Collection cửa hàng"),
        linkWithRel("next").optional()
                .description("Trang kế tiếp nếu còn dữ liệu"))
~~~

Đối với link nằm trong từng embedded item, cần chọn subsection chứa các item trước khi mô tả relation. Spring REST Docs cung cấp overload của links(...) nhận PayloadSubsectionExtractor:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Cửa hàng hiện tại"),
        linkWithRel("products").description("Sản phẩm của cửa hàng"))
~~~

Khi gọi dạng này, linkWithRel("self") và linkWithRel("products") được tìm trong link map của từng phần tử bên dưới _embedded.stores[], thay vì link map tại root. Nhờ đó, relation cùng tên có thể được mô tả độc lập ở hai cấp nếu response thật sự có relation đó ở cả hai nơi.

### Không nhầm root link với embedded link

Ví dụ root có relation next:

~~~json
{
  "_links": {
    "self": {"href": "/api/stores?page=0"},
    "next": {"href": "/api/stores?page=1"}
  },
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  }
}
~~~

Nếu dùng links(linkWithRel("next")...) ở root, descriptor nói về phân trang collection. Nếu dùng links(beneathPath("_embedded.stores[]"), ...), descriptor nói về link trên mỗi store. Chọn sai cấp sẽ dẫn đến lỗi không tìm thấy relation hoặc tài liệu mô tả nhầm ý nghĩa.

## 6. Ví dụ MockMvc cho embedded resources và nested links

Ví dụ test sau giả định endpoint /api/stores trả HAL với root relation self, next, và mỗi store có self, products. Test mô tả payload và links ở cả hai cấp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class StoreDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentStoreCollection() throws Exception {
        mockMvc.perform(get("/api/stores")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.stores[0].id").value(11))
                .andExpect(jsonPath("$._embedded.stores[0]._links.products.href").exists())
                .andDo(document("stores-list",
                        links(
                                linkWithRel("self").description("Collection cửa hàng"),
                                linkWithRel("next").optional().description("Trang kế tiếp")),
        links(
                beneathPath("_embedded.stores[]").withSubsectionId("stores"),
                                linkWithRel("self").description("Cửa hàng hiện tại"),
                                linkWithRel("products").description("Sản phẩm của cửa hàng")),
                        responseFields(
                beneathPath("_embedded.stores[]").withSubsectionId("stores"),
                                fieldWithPath("id").description("Mã cửa hàng"),
                                fieldWithPath("name").description("Tên cửa hàng"))));
    }
}
~~~

Test dùng ba nhóm mô tả:

1. links(...) đầu tiên trích xuất relation ở root response, tức collection stores.
2. links(beneathPath("_embedded.stores[]"), ...) trích xuất relation trong từng embedded store.
3. responseFields(beneathPath("_embedded.stores[]"), ...) mô tả field của mỗi store.

Ví dụ tập trung vào snippet subsection. Nếu cần tài liệu hóa đầy đủ root fields và _embedded trong một bảng responseFields strict, hãy khai báo thêm field root hoặc mô tả subsection thích hợp theo đúng JSON thực tế. Không giả định một bộ descriptor con tự động bao phủ mọi field ở root.

## 7. Subsection lồng nhiều tầng

Embedded resource có thể chứa object con hoặc collection khác. Ví dụ một store chứa địa chỉ:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Cửa hàng trung tâm",
        "address": {
          "city": "Hồ Chí Minh",
          "district": "Quận 1"
        },
        "_links": {
          "self": {"href": "/api/stores/11"}
        }
      }
    ]
  }
}
~~~

Để mô tả field trong address của từng store:

~~~java
responseFields(
        beneathPath("_embedded.stores[]"),
        fieldWithPath("id").description("Mã cửa hàng"),
        fieldWithPath("name").description("Tên cửa hàng"),
        fieldWithPath("address.city").description("Thành phố"),
        fieldWithPath("address.district").description("Quận/huyện"))
~~~

Trong ví dụ này, đường dẫn field được tính tương đối từ từng phần tử store. Nếu muốn tài liệu chỉ riêng address, có thể chọn sâu hơn bằng extractor tương ứng:

~~~java
responseFields(
        beneathPath("_embedded.stores[].address"),
        fieldWithPath("city").description("Thành phố"),
        fieldWithPath("district").description("Quận/huyện"))
~~~

Đối với mảng lồng nhau, chẳng hạn mỗi store có embedded departments, cần xác định rõ path và collection boundary:

~~~text
_embedded
  └── stores[]
       └── _embedded
            └── departments[]
                 ├── id
                 └── name
~~~

Mỗi cấp có thể được mô tả bằng snippet riêng, dùng subsection extractor đến đúng vùng cần trình bày. Cách này giúp bảng fields không trở thành một danh sách đường dẫn rất dài khó đọc.

## 8. Phân biệt embedded resource, association link và collection link

| Loại | Cấu trúc HAL | Ý nghĩa |
| --- | --- | --- |
| Embedded resource | _embedded.stores[] | Dữ liệu resource được đưa trực tiếp vào response hiện tại. |
| Association link | _links.products bên trong một store | Điều hướng từ store tới collection products liên quan. |
| Collection navigation link | _links.next tại root | Điều hướng giữa các trang của collection stores. |

Một resource có thể vừa được nhúng, vừa có link riêng. Embedded data giúp client có một phần thông tin ngay trong response; link cho phép client truy cập representation đầy đủ hoặc các quan hệ khác. Không suy luận rằng embedded object làm cho link self của object không còn cần thiết.

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "name": "Cửa hàng trung tâm",
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"}
  }
}
~~~

Client có thể đọc tên store từ embedded resource, dùng link self để lấy tài nguyên store độc lập, hoặc dùng products để khám phá sản phẩm của store. Tài liệu nên mô tả ba khả năng này theo đúng thiết kế API.

## 9. Optional, ignored và strict/relaxed ở link lồng nhau

Nguyên tắc required/optional/ignored vẫn áp dụng cho descriptor của link lồng nhau; khác biệt là extractor phải trỏ đúng cấp:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Cửa hàng hiện tại"),
        linkWithRel("products").optional()
                .description("Sản phẩm nếu cửa hàng hỗ trợ"))
~~~

Ở đây self là bắt buộc với từng store; products có thể vắng mặt. Nếu một relation nội bộ nằm trong từng embedded store nhưng không đưa vào tài liệu:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Cửa hàng hiện tại"),
        linkWithRel("internal-audit").ignored())
~~~

Nếu mỗi store có nhiều link khác chưa được mô tả, cân nhắc relaxed links cho subsection đó. Cần kiểm tra API phiên bản dự án có overload tương ứng cho relaxedLinks(PayloadSubsectionExtractor, ...); nếu không có, tổ chức test bằng snippet phù hợp thay vì giả định mọi overload giống nhau.

Không dùng optional để che một relation bắt buộc ở một số item. Nếu hợp đồng quy định mọi store đều có products, descriptor bắt buộc và test phải phát hiện item thiếu relation.

## 10. Ghép snippet embedded fields và links vào Asciidoctor

Một operation có thể tạo nhiều snippet theo các khía cạnh khác nhau. Tùy descriptor và cấu hình, thư mục stores-list có thể chứa:

~~~text
build/generated-snippets/
└── stores-list/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── links.adoc
    ├── response-fields-stores.adoc
    └── links-stores.adoc
~~~

Tên snippet cho subsection phụ thuộc ID/subsection configuration mà dự án khai báo; cây trên chỉ minh họa. Hãy kiểm tra file thực tế được sinh trước khi viết include.

Một trang Asciidoctor có thể trình bày theo cấp:

~~~adoc
= Stores API

== Danh sách cửa hàng

include::{snippets}/stores-list/http-request.adoc[]
include::{snippets}/stores-list/http-response.adoc[]

=== Liên kết của collection

include::{snippets}/stores-list/links.adoc[]

=== Embedded store

include::{snippets}/stores-list/response-fields-stores.adoc[]
include::{snippets}/stores-list/links-stores.adoc[]
~~~

Với subsection ID stores đặt trong ví dụ, tên response-fields-stores.adoc và links-stores.adoc được tạo theo identifier subsection. Tên file cuối cùng còn phụ thuộc snippet type và phiên bản; kiểm tra thư mục output thực tế trước khi dùng include.

Với Markdown, snippet mặc định thường là AsciiDoc. Cần cơ chế chuyển đổi/nhúng phù hợp trước khi xuất bản; không giả định Markdown renderer xử lý trực tiếp include::.

## 11. Lỗi thường gặp khi document embedded resources

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy subsection | Path trong beneathPath(...) sai hoặc khác JSON thực tế | Kiểm tra response body, đặc biệt _embedded và tên relation collection. |
| Descriptor id không khớp | Descriptor đang ở root thay vì subsection item | Chuyển extractor vào _embedded.stores[] hoặc dùng đường dẫn đầy đủ đúng ngữ cảnh. |
| Không tìm thấy link products | Link nằm trong mỗi store nhưng descriptor đọc ở root | Dùng links(beneathPath("_embedded.stores[]"), ...). |
| Root next không xuất hiện trong snippet | Nhầm extractor root với subsection item | Mô tả root links bằng links(...) riêng. |
| Field trong embedded item chưa được mô tả | Strict response fields còn field chưa khai báo | Bổ sung field descriptor hoặc mô tả subsection phù hợp. |
| Một item thiếu relation bắt buộc | Hợp đồng thực tế không bảo đảm relation ở mọi item | Chỉ dùng optional khi API cho phép; nếu không, sửa response. |
| Subsection snippet có tên file khác include | Subsection ID hoặc cấu hình snippet khác giả định | Đọc output directory rồi điều chỉnh include theo tên thật. |
| Body có embedded data nhưng thiếu _links | Representation chưa tạo association links hoặc serializer chưa xuất HAL links | Kiểm tra EntityModel, CollectionModel và HATEOAS configuration. |
| Media type là JSON thường | Endpoint không trả HAL hoặc negotiation không đúng | Kiểm tra Accept, produces và Content-Type. |

Khi lỗi xảy ra, in response thực tế và xác định subsection/link nằm ở cấp nào trước khi thay descriptor. Không chuyển toàn bộ snippet sang relaxed chỉ để tránh lỗi path hoặc relation.

## 12. Bài thực hành

1. Tạo response HAL collection gồm hai embedded store, mỗi store có self và products; mô tả fields qua beneathPath("_embedded.stores[]").
2. Tạo root link next cho pagination và mô tả bằng links(...) ở root.
3. Mô tả nested products link bên trong từng store bằng link subsection extractor.
4. Thêm object address trong embedded store; document các field address.city và address.district.
5. Cho products link trở thành tùy chọn ở một số store; viết test cho cả item có và không có link.
6. Ghép HTTP response, root links, embedded fields và nested links vào Asciidoctor; kiểm tra task tài liệu trong CI.

**Tiêu chí hoàn thành:** phân biệt root representation với embedded item; chọn đúng path extractor cho payload và link; mô tả association link ở từng item; không trộn link phân trang với link lồng nhau; snippet và include khớp output thực tế.

## 13. Checklist trước khi công bố embedded resources

- [ ] Xác nhận response thực tế dùng hypermedia format và media type đã công bố.
- [ ] Xác định collection được nhúng ở path nào trong _embedded.
- [ ] Dùng beneathPath(...) cho field descriptors tương đối với embedded item.
- [ ] Dùng subsectionWithPath(...) khi cần mô tả một vùng như một khối.
- [ ] Document root _links riêng với _links trong embedded resource.
- [ ] Dùng link subsection extractor khi mô tả relation nằm trong từng item.
- [ ] Required/optional/ignored phản ánh đúng hợp đồng của từng relation.
- [ ] Đặt subsection ID và kiểm tra tên snippet thực tế trước khi viết include.
- [ ] Asciidoctor/Markdown biên soạn sau khi test tạo snippet thành công.

**Ghi nhớ:** Embedded resource là dữ liệu được đưa vào _embedded; nested links là các quan hệ trong _links của chính resource đó. Dùng payload subsection extractor và link subsection extractor ở đúng cấp giúp Spring REST Docs tạo tài liệu rõ ràng về cả cấu trúc dữ liệu lẫn cách client điều hướng giữa những tài nguyên lồng nhau.
