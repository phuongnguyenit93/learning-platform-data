# Kiểm thử href

Trong Spring HATEOAS, một link gồm hai thành phần cốt lõi: **relation** mô tả ý nghĩa của liên kết và **href** cho biết URI đích. Một response có thể chứa đúng relation `self`, `next`, `customer` hoặc `approve-order`, nhưng href vẫn sai do mapping thay đổi, thiếu context path, sai host công khai, mã hóa path variable không đúng hoặc query parameter bị mất.

Kiểm thử href cần xác nhận client thực sự nhận được URI có thể sử dụng theo hợp đồng API. Hãy kiểm tra relation và href cùng nhau, đồng thời phân biệt URI tuyệt đối, URI tương đối và URI template. Với Spring MVC, có thể dùng MockMvc và JsonPath; với Spring HATEOAS client API, `LinkDiscoverer` giúp tìm link theo relation mà không phụ thuộc trực tiếp vào cấu trúc JSONPath.

## Vì sao cần kiểm thử href?

Link được tạo từ controller mapping, request hiện tại, context path và đôi khi từ forwarded headers của reverse proxy. Những yếu tố này có thể làm URI thay đổi dù code assembler không đổi.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/v1/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/v1/customers/7"
    },
    "cancel": {
      "href": "https://api.example.com/v1/orders/42/cancellation"
    }
  }
}
~~~

Một bài kiểm thử link tốt nên xác nhận:

- Relation cần thiết có xuất hiện hay không.
- Href trỏ tới đúng resource hoặc action.
- Path variable được thay bằng giá trị đúng.
- Query parameter cần thiết được giữ lại và encode đúng.
- Host, scheme, port và context path đúng với hợp đồng triển khai nếu API yêu cầu URI tuyệt đối.
- URI template được đánh dấu templated và chứa đúng biến nếu link chưa được mở rộng.
- Link chỉ xuất hiện khi hành động khả dụng, nếu link phụ thuộc trạng thái hoặc quyền.

Không nên chỉ kiểm tra response có chuỗi href. Một href sai vẫn có thể là chuỗi hợp lệ và làm test kiểm tra sự tồn tại vượt qua.

## Kiểm tra Link trực tiếp khi unit test

Nếu mục tiêu là kiểm tra logic tạo link của assembler hoặc component riêng, có thể kiểm thử đối tượng `Link` trước khi serialize thành HAL. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.net.URI;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class OrderLinkFactoryTests {

    @Test
    void buildsSelfLinkForTheSelectedOrder() {
        UUID orderId = UUID.fromString(
            "f1d3a2c4-5b6e-4d7f-8a9b-0c1d2e3f4a5b");

        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setScheme("https");
        request.setServerName("api.example.test");
        request.setServerPort(443);
        request.setRequestURI("/");
        request.setServletPath("");
        RequestContextHolder.setRequestAttributes(
            new ServletRequestAttributes(request));

        try {
            Link self = linkTo(
                methodOn(OrderController.class).one(orderId)
            ).withSelfRel();

            assertThat(self.getRel()).isEqualTo(IanaLinkRelations.SELF);
            assertThat(URI.create(self.getHref()).getPath())
                .endsWith("/orders/" + orderId);
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }
}
~~~

Ví dụ giả định `OrderController.one(UUID)` được ánh xạ tới `/orders/{id}`. `methodOn(...)` giúp link builder đọc mapping và thay path variable theo phương thức controller. Test kiểm tra relation `self` riêng với path để lỗi ở một phần không bị che khuất bởi phần còn lại.

`WebMvcLinkBuilder` đọc base URI từ request hiện tại, nên unit test thuần cần thiết lập request context trước khi gọi builder. Trong ứng dụng thật, MockMvc integration test ở phần sau sẽ cung cấp request context tự nhiên.

Unit test phù hợp để xác minh quy tắc xây link độc lập. Nó không thay thế kiểm thử HTTP vì chưa xác nhận serializer, content negotiation, servlet context hoặc forwarded header handling.

## Kiểm tra href trong HAL response bằng MockMvc

Với endpoint Spring MVC trả `EntityModel`, kiểm tra trực tiếp response đã serialize. Ví dụ controller:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

record OrderRepresentation(UUID id, String status) {}

interface OrderService {
    OrderRepresentation findRepresentation(UUID id);
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        OrderRepresentation body = orderService.findRepresentation(id);

        return EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
~~~

Test xác nhận media type, relation và phần cuối của href:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHrefTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsSelfHrefForRequestedOrder() throws Exception {
        UUID orderId = UUID.fromString(
            "f1d3a2c4-5b6e-4d7f-8a9b-0c1d2e3f4a5b");

        mockMvc.perform(get("/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/" + orderId)));
    }
}
~~~

`EXISTING_ORDER_ID` hoặc UUID trong ví dụ cần được chuẩn bị trong test fixture nếu endpoint đọc dữ liệu từ repository. Dùng `endsWith` khi host, scheme và port được quyết định bởi môi trường test nhưng path là phần hợp đồng cần xác nhận. Nếu ứng dụng có base path cố định, hãy kiểm tra cả prefix đó.

HAL đặt link trong `_links`, mỗi relation thường là một key. Vì vậy, JsonPath của HAL dùng `$._links.self.href`. Không dùng biểu thức `$.links[?(@.rel == 'self')].href` của một representation JSON khác cho response HAL.

## Kiểm tra href tuyệt đối đầy đủ

Nếu hợp đồng yêu cầu server công bố URI tuyệt đối, chỉ kiểm tra path là chưa đủ. Hãy phân tích href thành `URI` và xác nhận từng phần:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

@Test
void publishesTheConfiguredPublicBaseUri() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
            .with(request -> {
                request.setScheme("https");
                request.setServerName("api.example.test");
                request.setServerPort(443);
                return request;
            })
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

    String body = result.getResponse().getContentAsString();
    String href = JsonPath.read(body, "$._links.self.href");
    URI uri = URI.create(href);

    assertThat(uri.isAbsolute()).isTrue();
    assertThat(uri.getScheme()).isEqualTo("https");
    assertThat(uri.getHost()).isEqualTo("api.example.test");
    assertThat(uri.getPath()).endsWith("/orders/" + EXISTING_ORDER_ID);
}
~~~

Ví dụ giả định ứng dụng tạo absolute link từ scheme/host của request và không bật cấu hình ép HTTPS. Nếu ứng dụng luôn chạy sau proxy HTTPS, test cần cấu hình forwarded headers đúng với hạ tầng và xác nhận public scheme/host mà proxy gửi. Không dùng một header do client tùy ý cung cấp làm nguồn tin cậy trong production; forwarded headers chỉ nên được xử lý khi request đến từ proxy đáng tin cậy.

Nếu test không cần xác minh host, đừng khóa cứng `localhost`, port ngẫu nhiên hoặc scheme của môi trường test. Ngược lại, nếu public base URI là hợp đồng triển khai quan trọng, hãy kiểm tra nó trong một integration test có cấu hình tương ứng.

## Dùng LinkDiscoverer để tìm href theo relation

Spring HATEOAS cung cấp `LinkDiscoverer` để tìm link theo relation trong một representation. Với HAL, dùng `HalLinkDiscoverer`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

class HalLinkDiscovererTests {

    @Test
    void discoversSelfHrefFromHalDocument() {
        String document = """
            {
              "_links": {
                "self": {
                  "href": "https://api.example.test/orders/42"
                },
                "customer": {
                  "href": "https://api.example.test/customers/7"
                }
              }
            }
            """;

        LinkDiscoverer discoverer = new HalLinkDiscoverer();
        Link self = discoverer.findLinkWithRel("self", document);

        assertThat(self.getHref())
            .isEqualTo("https://api.example.test/orders/42");
    }
}
~~~

`LinkDiscoverer` tách việc tìm link khỏi cấu trúc JSONPath cụ thể. Cách này hữu ích khi muốn kiểm tra relation và href bằng Spring HATEOAS API. Nếu ứng dụng dùng nhiều hypermedia media type, chọn `LinkDiscoverer` tương ứng với media type đang kiểm thử.

Trong ứng dụng đã bật `@EnableHypermediaSupport`, Spring HATEOAS có thể tự đăng ký `LinkDiscoverer` bean nếu JSONPath có trên classpath. Có thể inject `LinkDiscoverers` rồi lấy implementation theo media type thay vì tạo `HalLinkDiscoverer` trực tiếp.

## Kiểm tra link theo relation tùy chỉnh

Với relation nghiệp vụ, test cần xác nhận đúng relation và đúng endpoint:

~~~java
@Test
void exposesApproveLinkWithExpectedHref() throws Exception {
    mockMvc.perform(get("/orders/{id}", PENDING_ORDER_ID)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/approve-order'].href")
            .value(endsWith("/orders/" + PENDING_ORDER_ID + "/approval")));
}
~~~

Trong HAL, custom relation dạng URI đầy đủ thường là key của `_links`; vì key có dấu `:` và `/`, dùng cú pháp bracket trong JsonPath. Nếu server compact relation bằng CURIE, key có thể là `acme:approve-order`; khi đó test phải kiểm tra cả link `curies` và relation đã compact.

Link action có thể phụ thuộc trạng thái:

~~~java
@Test
void doesNotExposeApproveLinkForCompletedOrder() throws Exception {
    mockMvc.perform(get("/orders/{id}", COMPLETED_ORDER_ID)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/approve-order']")
            .doesNotExist());
}
~~~

Test này xác nhận server không công bố affordance khi hành động không khả dụng. Nó không thay thế test authorization của endpoint: client vẫn có thể tự gửi request trực tiếp, nên controller/service phải kiểm tra quyền và trạng thái.

## Kiểm tra path variable và URI encoding

Href thường được tạo từ controller mapping và các giá trị `@PathVariable`. Kiểm tra ID thực tế được chèn vào đúng vị trí:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();

assertThat(URI.create(self.getHref()).getPath())
    .endsWith("/orders/" + orderId);
~~~

Nếu path variable có ký tự đặc biệt, không tự nối chuỗi để tạo href. URI builder phải mã hóa giá trị đúng cách. Test nên dùng một giá trị có khoảng trắng, dấu `?` hoặc ký tự Unicode nếu domain cho phép các giá trị đó trong path, sau đó xác nhận href không làm thay đổi cấu trúc path. Dấu `/` có ý nghĩa phân tách path segment; encoded slash còn có thể bị servlet container hoặc reverse proxy từ chối, nên chỉ dùng nó nếu API và hạ tầng hỗ trợ rõ ràng.

Ví dụ, nếu API cho phép dấu `/` trong một path segment, phải xác nhận cả quy tắc encode/decode của server, proxy và client. Dùng `URI.getRawPath()` để kiểm tra dạng encoded trên wire; `URI.getPath()` trả về path đã decode.

## Kiểm tra query parameter

Link tới collection/search có thể chứa query parameter. Test nên xác nhận những tham số thuộc hợp đồng có mặt và giữ nguyên giá trị:

~~~java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

@Test
void keepsSearchParametersInSelfHref() throws Exception {
    mockMvc.perform(get("/orders")
            .param("status", "PENDING")
            .param("sort", "createdAt,desc")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
            .value(allOf(
                containsString("status=PENDING"),
                containsString("sort="))));
}
~~~

Ví dụ giả định controller tạo self link từ request hiện tại và response là collection HAL. Nếu thứ tự query parameter không phải một phần của hợp đồng, đừng so sánh toàn bộ href bằng một chuỗi có thứ tự cố định. Hãy parse query string và kiểm tra tên/giá trị từng parameter.

~~~java
URI selfUri = URI.create(selfHref);
MultiValueMap<String, String> query =
    UriComponentsBuilder.fromUri(selfUri).build().getQueryParams();

assertThat(query.getFirst("status")).isEqualTo("PENDING");
assertThat(query.getFirst("sort")).isEqualTo("createdAt,desc");
~~~

Các import liên quan:

~~~java
import org.springframework.util.MultiValueMap;
import org.springframework.web.util.UriComponentsBuilder;
~~~

Nếu link chứa URI template thay vì giá trị đã mở rộng, kiểm tra template variable trước. Đừng mong đợi một query parameter cụ thể đã có mặt khi server chủ ý công bố biến mẫu.

## Kiểm tra URI template

Spring HATEOAS `Link` có thể chứa URI template theo RFC 6570. Ví dụ link search:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link search = Link.of(
    "/orders{?status,page,size}",
    LinkRelation.of("search")
);
~~~

Kiểm tra link là template và chứa đúng biến:

~~~java
assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
    .containsExactlyInAnyOrder("status", "page", "size");

Link expanded = search.expand(Map.of(
    "status", "PENDING",
    "page", 0,
    "size", 20
));

assertThat(expanded.getHref())
    .isEqualTo("/orders?status=PENDING&page=0&size=20");
~~~

Trong HAL, URI template thường được serialize với thuộc tính `templated: true`:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

Với MockMvc, có thể kiểm tra cả href và cờ templated:

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value("/orders{?status,page,size}"));
~~~

Chỉ kiểm tra biến mà client được phép cung cấp. URI template có thể được mở rộng theo các quy tắc encoding của RFC 6570; không tự thay placeholder bằng cách nối chuỗi.

## Kiểm tra collection self và item self riêng biệt

Một response collection có thể chứa self link ở hai cấp:

- `_links.self` bên ngoài xác định collection hoặc view hiện tại.
- `_embedded.orders[n]._links.self` xác định từng item.

Ví dụ:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "_links": {
          "self": {
            "href": "https://api.example.test/orders/ORD-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/orders?page=0"
    }
  }
}
~~~

Test nên kiểm tra đúng cấp:

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(endsWith("/orders?page=0")))
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
        .value(endsWith("/orders/" + FIRST_ORDER_ID)));
~~~

Đừng dùng link self của collection để thay cho link item. Client cần biết URI nào tải lại toàn bộ view và URI nào truy cập một entity cụ thể.

## Kiểm tra thuộc tính khác của Link

Ngoài href và rel, Spring HATEOAS `Link` có thể mang thuộc tính theo RFC 8288 như `type`, `hreflang`, `title`, `name`, `profile` hoặc `deprecation`. Nếu client dựa vào những thuộc tính này, hãy kiểm tra chúng:

~~~java
Link link = Link.of("/orders/42")
    .withRel("order")
    .withTitle("Chi tiết đơn hàng")
    .withType("application/hal+json");

assertThat(link.getTitle()).contains("Chi tiết đơn hàng");
assertThat(link.getType()).contains("application/hal+json");
~~~

Với response HAL, các thuộc tính có thể được serialize cùng href:

~~~json
{
  "_links": {
    "order": {
      "href": "/orders/42",
      "title": "Chi tiết đơn hàng",
      "type": "application/hal+json"
    }
  }
}
~~~

Không cần kiểm tra mọi thuộc tính trên mọi link. Chỉ kiểm tra metadata mà client hoặc hợp đồng API thực sự sử dụng; test không nên trở nên mong manh vì một thuộc tính trình bày không ảnh hưởng điều hướng.

## Kiểm tra href trong WebFlux bằng WebTestClient

Với ứng dụng reactive, `WebTestClient` có thể deserialize response thành Spring HATEOAS model. Cần áp dụng `HypermediaWebTestClientConfigurer` để client test hiểu media type hypermedia:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.server.core.TypeReferences;
import org.springframework.hateoas.config.HypermediaWebTestClientConfigurer;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveOrderHrefTests {

    @Autowired
    WebTestClient.Builder builder;

    @Autowired
    HypermediaWebTestClientConfigurer configurer;

    @Test
    void deserializesAndVerifiesSelfLink() {
        WebTestClient client = builder.apply(configurer).build();

        client.get()
            .uri("/orders/{id}", EXISTING_ORDER_ID)
            .accept(MediaTypes.HAL_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody(new TypeReferences.EntityModelType<OrderRepresentation>() {})
            .consumeWith(result -> {
                EntityModel<OrderRepresentation> model =
                    result.getResponseBody();

                assertThat(model).isNotNull();
                assertThat(model.getRequiredLink("self").getHref())
                    .endsWith("/orders/" + EXISTING_ORDER_ID);
            });
    }
}
~~~

Ví dụ giả định ứng dụng dùng Spring WebFlux và endpoint trả một `EntityModel<OrderRepresentation>`. `WebTestClient` là immutable; lấy instance được trả về từ `builder.apply(configurer).build()` để thực hiện request. Nếu dùng Spring MVC, ưu tiên MockMvc để kiểm thử đúng stack đang chạy.

## Kiểm tra forwarded headers và public base URI

Khi ứng dụng chạy sau reverse proxy, href tuyệt đối có thể được tạo từ scheme, host và port công khai được proxy chuyển tiếp. Nếu cấu hình filter/transformer sai, link có thể chứa `http` thay vì `https`, host nội bộ hoặc port của container.

Nếu ứng dụng bật `ForwardedHeaderFilter`, hãy có integration test với header `Forwarded` hoặc `X-Forwarded-*` đúng theo cấu hình proxy tin cậy. Kiểm tra `scheme`, `host`, `port` và context path của href. Không bật xử lý forwarded header trong production nếu ứng dụng nhận trực tiếp traffic từ client không đáng tin cậy mà không có lớp proxy kiểm soát các header này.

Test chỉ gửi `Host` header không chứng minh forwarded-header configuration hoạt động. Hãy kiểm thử đúng filter/transformer và đúng header mà proxy của môi trường thực tế sử dụng.

## Các lỗi thường gặp khi kiểm thử href

- **Chỉ kiểm tra link tồn tại:** href có thể sai path, host hoặc query.
- **Khóa cứng host và port không ổn định:** test thất bại giữa local, CI và môi trường triển khai dù route đúng.
- **Bỏ qua relation:** một href đúng nhưng được gắn nhầm relation có thể khiến client không tìm thấy.
- **So sánh query string theo thứ tự:** hai URI tương đương có thể sắp xếp parameter khác nhau.
- **Nhầm self collection và self item:** kiểm tra đúng URI nhưng ở sai cấp trong HAL.
- **Không kiểm tra templated:** client tưởng href đã hoàn chỉnh trong khi server yêu cầu mở rộng biến.
- **Tự nối chuỗi để dựng expected URL:** test lặp lại cùng giả định mong manh với code sản xuất.
- **Chỉ unit test link builder:** chưa xác nhận serializer và request context thực tế.
- **Dùng JSONPath sai media type:** HAL dùng `_links`, không dùng cấu trúc link của representation khác.
- **Kiểm tra forwarded header không đúng môi trường:** gửi Host header nhưng không đi qua filter xử lý forwarded header.

## Checklist kiểm thử href

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Relation | Link có đúng relation mà client tìm kiếm không? |
| Path | Href có đúng resource và path variable không? |
| Query | Filter, sort và parameter cần thiết có được giữ lại không? |
| Encoding | Ký tự đặc biệt có được encode thành URI hợp lệ không? |
| Base URI | Scheme, host, port và context path có đúng khi hợp đồng yêu cầu không? |
| Template | `templated` và danh sách biến có chính xác không? |
| Cardinality | Relation có một hay nhiều link theo đúng hợp đồng không? |
| Trạng thái | Link action chỉ xuất hiện khi hành động khả dụng không? |
| Media type | Test có gửi Accept đúng và kiểm tra Content-Type không? |
| Collection | Self của collection và self của item có được kiểm tra riêng không? |

Kiểm thử href trong Spring HATEOAS cần xác nhận cả relation lẫn URI đích. Dùng unit test cho quy tắc xây `Link`, MockMvc hoặc WebTestClient để kiểm tra representation thực tế, và `LinkDiscoverer` khi muốn tìm link theo relation mà không phụ thuộc cấu trúc JSONPath. Chỉ kiểm tra host tuyệt đối khi đó là một phần hợp đồng triển khai; với phần còn lại, tập trung vào path, query, encoding và template để test bền vững qua thay đổi môi trường.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – LinkDiscoverer](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverer.html)
- [Spring HATEOAS API – HalLinkDiscoverer](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalLinkDiscoverer.html)
- [Spring Framework – MockMvc testing](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 6570 – URI Template](https://www.rfc-editor.org/rfc/rfc6570.html)
