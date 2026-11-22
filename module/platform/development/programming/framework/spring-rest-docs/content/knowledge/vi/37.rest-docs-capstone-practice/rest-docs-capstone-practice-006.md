# Document HATEOAS links và embedded resources

## 1. HATEOAS thay đổi cách mô tả response API

Với REST API thông thường, response chứa dữ liệu và client phải tự biết URL của các thao tác tiếp theo. Với HATEOAS, response còn cung cấp **links** để client khám phá hành động hoặc tài nguyên liên quan. Media type HAL JSON còn có thể gom tài nguyên liên quan vào vùng **embedded resources**.

Ví dụ response HAL:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {"href": "https://api.example.test/orders/42"},
    "cancel": {"href": "https://api.example.test/orders/42/cancel"},
    "customer": {"href": "https://api.example.test/customers/7"}
  },
  "_embedded": {
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2,
        "_links": {
          "product": {"href": "https://api.example.test/products/BOOK-01"}
        }
      }
    ]
  }
}
~~~

Response có ba nhóm thông tin cần mô tả:

- Field nghiệp vụ ở cấp tài nguyên: id, status.
- Các liên kết trong _links: self, cancel, customer.
- Tài nguyên nhúng trong _embedded: danh sách items, mỗi item có field và link riêng.

Spring REST Docs có API chuyên biệt cho links. Dùng links(...) để document quan hệ link; dùng payload field descriptors để mô tả embedded resources và các field dữ liệu còn lại. Không mô tả link chỉ như một chuỗi JSON tùy ý nếu mục tiêu là giúp client hiểu ý nghĩa quan hệ.

Trong module **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo snippet có thể kiểm chứng. Khi API dùng HATEOAS, tài liệu cần giải thích cả quan hệ link lẫn cấu trúc embedded data để người dùng biết cách điều hướng và đọc tài nguyên.

## 2. Links snippet trong Spring REST Docs

### 2.1. Dùng links(...) và linkWithRel(...)

Spring REST Docs cung cấp linkWithRel(...) để mô tả một link theo relation name. Ví dụ MockMvc:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        links(
            linkWithRel("self").description("Liên kết tới chính đơn hàng"),
            linkWithRel("cancel").description("Hủy đơn hàng nếu trạng thái cho phép"),
            linkWithRel("customer").description("Tài nguyên khách hàng của đơn hàng")
        )
    ));
~~~

Operation này tạo snippet links.adoc, mô tả relation, đích liên kết và phần mô tả do test cung cấp. Snippet giúp người đọc biết cancel là quan hệ gì thay vì phải suy đoán từ URL.

Với HAL, REST Docs nhận biết link trong cấu trúc _links. Bảo đảm response có content type phù hợp, ví dụ application/hal+json, để REST Docs dùng parser hypermedia tương ứng.

### 2.2. Mô tả link bắt buộc và tùy chọn

Mặc định descriptor link là bắt buộc. Nếu một relation chỉ xuất hiện trong một số trạng thái tài nguyên, đánh dấu optional:

~~~java
links(
    linkWithRel("self").description("Liên kết tới đơn hàng"),
    linkWithRel("cancel").optional()
        .description("Chỉ xuất hiện khi đơn hàng còn có thể hủy")
)
~~~

Nếu response có link không cần mô tả trong snippet hiện tại, có thể ignore link đó:

~~~java
links(
    linkWithRel("self").description("Liên kết tới đơn hàng"),
    linkWithRel("cancel").description("Hủy đơn hàng"),
    linkWithRel("customer").ignored()
)
~~~

| Descriptor | Ý nghĩa |
| --- | --- |
| Không gọi optional() | Link phải tồn tại trong response |
| optional() | Link có thể không xuất hiện |
| ignored() | Link không thuộc phạm vi snippet này; REST Docs không yêu cầu mô tả nó |

Không dùng ignored() để che giấu một relation quan trọng bị quên document. Với API công khai, nên mô tả rõ các relation mà client được kỳ vọng sử dụng.

### 2.3. relaxedLinks(...) khi cần tài liệu hóa một phần

links(...) kiểm tra các link trong response đã được mô tả, giúp phát hiện khi API thêm relation mà tài liệu chưa cập nhật. Trong giai đoạn khảo sát hoặc khi chỉ muốn document một phần, có thể dùng relaxedLinks(...):

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get",
        relaxedLinks(
            linkWithRel("self").description("Liên kết tới đơn hàng")
        )
    ));
~~~

relaxedLinks(...) không yêu cầu mọi link trong response phải có descriptor. Điều này thuận tiện khi tài liệu hóa một phần, nhưng giảm mức kiểm chứng thay đổi của link contract. Với tài liệu hợp đồng đầy đủ, ưu tiên links(...) và khai báo rõ các relation cần thiết.

## 3. Embedded resources nằm trong payload

HAL thường dùng _embedded để chứa tài nguyên liên quan:

~~~json
{
  "_embedded": {
    "items": [
      {
        "sku": "BOOK-01",
        "quantity": 2
      }
    ]
  }
}
~~~

_embedded.items là một mảng tài nguyên nhúng. Nó không phải link relation trong _links; do đó links(...) không mô tả field sku hoặc quantity.

Dùng responseFields(...) để mô tả cấu trúc JSON:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    fieldWithPath("_embedded.items").description("Danh sách sản phẩm được nhúng"),
    fieldWithPath("_embedded.items[].sku").description("Mã SKU sản phẩm"),
    fieldWithPath("_embedded.items[].quantity").description("Số lượng")
)
~~~

Descriptor cho mảng dùng [] trong path để chỉ phần tử. Nếu API có nhiều field bên trong mỗi phần tử, document chúng như các path con tương ứng.

## 4. Dùng subsectionWithPath(...) cho embedded subtree

Khi muốn mô tả một vùng JSON như một khối, không liệt kê từng field ngay tại snippet cấp response, dùng subsectionWithPath(...):

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    subsectionWithPath("_embedded.items")
        .description("Danh sách tài nguyên sản phẩm được nhúng")
)
~~~

Subsection descriptor cho biết cả cây con _embedded.items thuộc một vùng payload được document. Cách này phù hợp khi chỉ cần giới thiệu embedded collection ở cấp cao, hoặc muốn tách phần mô tả chi tiết thành snippet riêng.

Nếu dùng subsectionWithPath("_embedded.items"), không đồng thời khai báo các field con của cùng subtree trong cùng descriptor set theo cách gây chồng lấp. Chọn một cấp mô tả: hoặc mô tả subtree như một khối, hoặc liệt kê các field con.

### 4.1. Tách field documentation bằng beneathPath(...)

Khi muốn document chi tiết field bên trong embedded resource, có thể dùng beneathPath(...) để giới hạn payload snippet vào một phần của response:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    beneathPath("_embedded.items[]")
        .withSubsectionId("order-items")
        .and()
        .description("Các field của một sản phẩm trong đơn hàng"),
    fieldWithPath("sku").description("Mã SKU"),
    fieldWithPath("quantity").description("Số lượng")
)
~~~

beneathPath(...) tạo payload snippet từ phần được chọn thay vì toàn bộ response. Với embedded collection, xác minh payload được cắt đúng theo cấu trúc thực tế và đường dẫn được hỗ trợ bởi phiên bản REST Docs đang dùng. Nếu descriptor áp dụng cho từng phần tử mảng, snippet field nên mô tả một item mẫu, không nhầm path tương đối với path cấp response.

Một lựa chọn khác là giữ field path đầy đủ trong responseFields(...):

~~~java
responseFields(
    fieldWithPath("_embedded.items[].sku").description("Mã SKU"),
    fieldWithPath("_embedded.items[].quantity").description("Số lượng")
)
~~~

Cách này trực tiếp và dễ đối chiếu với JSON gốc; beneathPath(...) hữu ích khi tài liệu muốn tách subtree thành bảng field độc lập.

## 5. Kết hợp links và response fields trong một operation

Trong một response HAL, links và payload fields là hai phần bổ sung. Có thể tạo cả hai snippet trong cùng operation:

~~~java
mockMvc.perform(get("/orders/42")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        links(
            linkWithRel("self").description("Liên kết tới đơn hàng"),
            linkWithRel("cancel").optional()
                .description("Hủy đơn nếu trạng thái cho phép"),
            linkWithRel("customer").description("Khách hàng của đơn hàng")
        ),
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái"),
            subsectionWithPath("_embedded.items")
                .description("Các sản phẩm trong đơn hàng")
        )
    ));
~~~

Kết quả thường có các snippet riêng:

~~~text
orders/get/
├── http-request.adoc
├── http-response.adoc
├── links.adoc
└── response-fields.adoc
~~~

Tên snippet có thể thay đổi nếu dùng custom snippet template. Hãy kiểm tra thư mục generated thực tế sau khi test chạy và include đúng tên file.

## 6. Ví dụ controller HATEOAS

Một API Spring HATEOAS có thể trả về EntityModel hoặc CollectionModel. Ví dụ rút gọn:

~~~java
@GetMapping(value = "/orders/{id}", produces = "application/hal+json")
EntityModel<Order> getOrder(@PathVariable long id) {
    Order order = orderService.getById(id);
    return EntityModel.of(order,
        linkTo(methodOn(OrderController.class).getOrder(id)).withSelfRel(),
        linkTo(methodOn(OrderController.class).cancelOrder(id)).withRel("cancel"),
        linkTo(methodOn(CustomerController.class).getCustomer(order.customerId()))
            .withRel("customer")
    );
}
~~~

Ví dụ dùng Spring HATEOAS để tạo relation self, cancel và customer. Trong ứng dụng thực tế, endpoint hủy có thể chỉ được thêm khi người dùng có quyền và đơn hàng đang ở trạng thái cho phép. Khi đó test nên có ít nhất hai trường hợp:

- Đơn có thể hủy: relation cancel xuất hiện.
- Đơn không thể hủy: relation cancel không xuất hiện.

REST Docs có thể kiểm tra hai contract bằng descriptor bắt buộc và optional tùy test. Nếu muốn đảm bảo link biến mất đúng trạng thái, hãy có test riêng cho response không có link đó; không chỉ đánh dấu optional rồi bỏ qua hành vi.

## 7. MockMvc test cho HAL response

Ví dụ test minh họa:

~~~java
@WebMvcTest(OrderController.class)
@ExtendWith(RestDocumentationExtension.class)
class OrderHateoasDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void documentsOrderLinksAndEmbeddedItems() throws Exception {
        given(orderService.getById(42L)).willReturn(sampleOrder());

        mockMvc.perform(get("/orders/42")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andDo(document("orders/get-hateoas",
                links(
                    linkWithRel("self").description("Liên kết tới đơn hàng"),
                    linkWithRel("cancel").description("Hủy đơn hàng"),
                    linkWithRel("customer").description("Khách hàng")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đơn hàng"),
                    fieldWithPath("status").description("Trạng thái đơn hàng"),
                    subsectionWithPath("_embedded.items")
                        .description("Danh sách sản phẩm được nhúng")
                )
            ));
    }
}
~~~

Đây là ví dụ khung: sampleOrder(), OrderService, controller và cấu hình Spring HATEOAS cần được cung cấp trong project. Tên relation và JSON path phải khớp response thật mà test nhận được. Nếu response dùng relation orders thay cho items, thay descriptor và AsciiDoc theo hợp đồng thực tế.

## 8. Document collection embedded resources

Với collection HAL, response có thể chứa nhiều resource cùng loại:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {"href": "/orders/42"}
        }
      },
      {
        "id": 43,
        "status": "PENDING",
        "_links": {
          "self": {"href": "/orders/43"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/orders"},
    "profile": {"href": "/profile/orders"}
  }
}
~~~

Document links ở cấp collection:

~~~java
links(
    linkWithRel("self").description("Danh sách đơn hàng"),
    linkWithRel("profile").description("Mô tả profile của collection")
)
~~~

Document embedded collection:

~~~java
responseFields(
    subsectionWithPath("_embedded.orders")
        .description("Danh sách đơn hàng được nhúng")
)
~~~

Hoặc mô tả chi tiết các field:

~~~java
responseFields(
    fieldWithPath("_embedded.orders[].id").description("Mã đơn hàng"),
    fieldWithPath("_embedded.orders[].status").description("Trạng thái đơn hàng")
)
~~~

Các link self nằm bên trong từng phần tử collection có thể cần được mô tả riêng theo cấu trúc hypermedia của response. Kiểm tra output links snippet của test và cấu hình descriptor đúng relation được REST Docs nhận diện ở cấp embedded resource; không giả định link của từng phần tử luôn tương đương link ở root.

## 9. Asciidoctor: include links và embedded fields

Sau khi test sinh snippet:

~~~text
build/generated-snippets/
└── orders/
    └── get-hateoas/
        ├── http-response.adoc
        ├── links.adoc
        └── response-fields.adoc
~~~

Include vào tài liệu:

~~~adoc
== Lấy chi tiết đơn hàng

=== HTTP response
include::{snippets}/orders/get-hateoas/http-response.adoc[]

=== Hypermedia links
include::{snippets}/orders/get-hateoas/links.adoc[]

=== Response fields
include::{snippets}/orders/get-hateoas/response-fields.adoc[]
~~~

Phần links giải thích cách client điều hướng qua relation. Phần response fields giải thích dữ liệu nghiệp vụ và embedded subtree. Người đọc có thể kết hợp cả hai để xây dựng client mà không cần hard-code mọi URL.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không sinh links.adoc | Chưa gọi links(...) hoặc response không được nhận diện hypermedia | Kiểm tra content type, HAL payload và REST Docs configuration |
| Link mới xuất hiện làm test fail | Dùng links(...) nhưng chưa document relation mới | Thêm descriptor hoặc ignore có chủ đích |
| Link tùy chọn làm test fail | Descriptor chưa gọi optional() | Đánh dấu optional và viết test cho cả hai trạng thái |
| Link không được kiểm tra | Dùng relaxedLinks(...) | Dùng links(...) khi cần contract đầy đủ |
| _embedded không có trong fields snippet | Chưa khai báo field/subsection | Dùng subsectionWithPath hoặc field path đầy đủ |
| Field con bị trùng descriptor | Vừa mô tả subtree vừa mô tả field con cùng cấp | Chọn subtree hoặc liệt kê field con |
| Không hiểu path trong embedded array | Nhầm path cấp response và path tương đối | Dùng [] và kiểm tra payload mẫu |
| Link trong embedded item thiếu mô tả | Chỉ document root links | Kiểm tra links trong từng resource và document đúng cấp |
| Asciidoctor không tìm thấy links snippet | Include sai identifier hoặc tên file | Đối chiếu generated-snippets sau test |

## 11. Bài tập thực hành

Xây dựng endpoint GET /orders/{id} trả về HAL:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {"href": "/orders/42"},
    "customer": {"href": "/customers/7"}
  },
  "_embedded": {
    "items": [
      {"sku": "BOOK-01", "quantity": 2}
    ]
  }
}
~~~

Thực hiện:

1. Tạo response bằng Spring HATEOAS EntityModel hoặc cấu trúc HAL tương ứng.
2. Viết MockMvc test nhận application/hal+json.
3. Dùng links(...) và linkWithRel(...) mô tả self và customer.
4. Dùng responseFields(...) với subsectionWithPath("_embedded.items") để mô tả embedded collection.
5. Viết thêm một test mô tả chi tiết sku và quantity bằng field path đầy đủ hoặc beneathPath(...).
6. Nếu có relation chỉ xuất hiện trong một số trạng thái, dùng optional() và kiểm tra cả response có/không có relation.
7. Include http-response.adoc, links.adoc và response-fields.adoc vào Asciidoctor.
8. Chạy test và render tài liệu; đối chiếu snippet với JSON thực tế.

**Tiêu chí hoàn thành:** Relation links được mô tả bằng links snippet; embedded resources được mô tả bằng payload fields/subsection; test phát hiện thay đổi contract ngoài dự kiến; tài liệu cho phép người đọc hiểu cả cách điều hướng và cấu trúc dữ liệu.

## Tài liệu tham khảo

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring HATEOAS — Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring REST Docs — MockMvc](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
