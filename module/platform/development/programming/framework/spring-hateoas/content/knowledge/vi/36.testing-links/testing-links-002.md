# Kiểm thử relation

Trong API HATEOAS, relation là hợp đồng ngữ nghĩa giữa server và client. Client tìm link theo relation như `self`, `next`, `customer` hoặc `cancel`, sau đó dùng `href` do server công bố để điều hướng. Vì vậy, kiểm thử link không nên chỉ xác nhận JSON có một chuỗi URL; cần xác nhận relation đúng ý nghĩa, xuất hiện đúng trạng thái, trỏ tới đích phù hợp và được biểu diễn theo media type mà API công bố.

Spring HATEOAS cung cấp `LinkDiscoverer` để tìm link theo relation trong representation, `Links` để kiểm tra tập link đã tìm được, còn Spring MVC Test và Spring REST Docs giúp kiểm thử response HTTP thực tế. Kết hợp các công cụ này giúp phát hiện lỗi khi relation bị đổi tên, link bị thiếu, link xuất hiện sai điều kiện hoặc serializer tạo cấu trúc HAL không đúng.

Bài học này thuộc chương **Testing links** trong module **SPRING_HATEOAS**, tập trung vào kiểm thử relation trong HAL response: xác nhận relation tồn tại, kiểm tra `href` và metadata, xử lý link có điều kiện, nhiều link cùng relation, CURIE, URI template, state transition, và tạo tài liệu link từ test.

Sau bài học, bạn có thể:

- Kiểm thử relation và href bằng MockMvc/JSONPath.
- Dùng `LinkDiscoverers` và `LinkDiscoverer` để tìm link theo media type.
- Phân biệt kiểm tra link bắt buộc và link tùy chọn.
- Kiểm thử nhiều link cùng relation mà không phụ thuộc object/array serialization.
- Kiểm tra CURIE, URI template và metadata của link.
- Kiểm thử relation theo trạng thái nghiệp vụ và quyền truy cập.
- Phân biệt link của resource gốc với link nằm trong embedded resource.
- Dùng Spring REST Docs để phát hiện relation chưa được tài liệu hóa.
- Thiết kế test bền vững khi href thay đổi nhưng semantics vẫn giữ nguyên.

## 1. Kiểm thử relation thay vì kiểm thử URL hard-code

Giả sử response đơn hàng có các link:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "https://api.example.com/orders/42" },
    "customer": { "href": "https://api.example.com/customers/7" },
    "cancel": { "href": "https://api.example.com/orders/42/cancellation" }
  }
}
```

Test quan trọng cần xác nhận:

- Có relation `self` để định danh resource hiện tại.
- Có relation `customer` khi đơn hàng liên kết với khách hàng.
- Có relation `cancel` khi đơn hàng đang ở trạng thái cho phép hủy.
- `cancel.href` dẫn tới endpoint hủy được công bố.
- Representation được trả về đúng media type, ví dụ `application/hal+json`.

Không nên buộc test luôn phải thấy một host hoặc port cụ thể như `http://localhost:8080`. Giá trị đó có thể thay đổi giữa local, test, staging và production. Nếu hợp đồng chỉ yêu cầu URI kết thúc bằng `/orders/42`, hãy kiểm tra phần path hoặc semantics tương ứng. Nếu base URI là một phần hợp đồng, kiểm thử nó trong test cấu hình riêng.

## 2. Chọn công cụ kiểm thử phù hợp

Các công cụ phục vụ những mức kiểm tra khác nhau:

| Công cụ | Kiểm tra phù hợp | Khi nên dùng |
|---|---|---|
| `MockMvc` | HTTP status, header, media type và body do controller/converter tạo | Kiểm thử tích hợp Spring MVC. |
| `jsonPath(...)` | Relation key, href, metadata và cấu trúc `_links` | Assertion cụ thể trên JSON HAL. |
| `LinkDiscoverer` | Tìm link theo relation mà không phụ thuộc cách HAL biểu diễn object/array | Kiểm tra semantics và tái sử dụng logic phía client. |
| `LinkDiscoverers` | Chọn discoverer tương ứng với media type | Ứng dụng hỗ trợ nhiều hypermedia format. |
| `WebTestClient` | Gửi request và xác nhận response theo API reactive hoặc MVC | Kiểm thử HTTP theo fluent API. |
| Spring REST Docs | Kiểm tra link đã được mô tả trong tài liệu và sinh snippet | Duy trì tài liệu khớp response thực tế. |

Một test tốt thường kiểm tra HTTP contract bằng MockMvc/WebTestClient, sau đó dùng JSONPath hoặc `LinkDiscoverer` để xác nhận relation. Không cần dùng mọi công cụ trong cùng một test; chọn abstraction phù hợp với điều cần bảo vệ.

Với Spring Boot, `spring-boot-starter-hateoas` cung cấp tích hợp Spring HATEOAS cho ứng dụng MVC; `spring-boot-starter-test` cung cấp JUnit, AssertJ, MockMvc và các thư viện test phổ biến. Nếu dùng `LinkDiscoverer`, bảo đảm JSONPath có trên classpath vì Spring HATEOAS đăng ký các discoverer JSONPath khi thư viện này hiện diện. Nếu tạo tài liệu bằng REST Docs, thêm `spring-restdocs-mockmvc` với phiên bản được quản lý đồng bộ cùng Spring REST Docs của dự án.

## 3. Kiểm thử relation bằng JSONPath

Với Spring MVC, `MockMvc` có thể xác nhận trực tiếp cấu trúc HAL:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLinksJsonPathTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesExpectedOrderRelations() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").value(endsWith("/orders/42")))
                .andExpect(jsonPath("$._links.customer.href").value(endsWith("/customers/7")))
                .andExpect(jsonPath("$._links.cancel.href")
                        .value(endsWith("/orders/42/cancellation")));
    }
}
```

Ví dụ giả định test fixture có đơn hàng `42`, khách hàng `7` và đơn hàng đang ở trạng thái có thể hủy. `contentTypeCompatibleWith` cho phép kiểm tra media type tương thích mà không phụ thuộc tham số charset.

JSONPath rất trực quan khi test cấu trúc HAL cụ thể. Tuy nhiên, nếu một relation có thể được serialize thành object hoặc array, expression như `$._links.alternate.href` sẽ không xử lý được cả hai dạng. Khi cần kiểm tra ngữ nghĩa relation độc lập với cấu trúc, hãy dùng `LinkDiscoverer`.

## 4. Dùng LinkDiscoverer để tìm link theo relation

`LinkDiscoverer` là abstraction phía client của Spring HATEOAS. Nó nhận representation dạng chuỗi hoặc `InputStream`, tìm link theo relation và trả về `Optional<Link>` hoặc `Links`.

Với Spring Boot auto-configuration, có thể inject `LinkDiscoverers`:

```java
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.client.LinkDiscoverers;

class RelationAssertions {

    private final LinkDiscoverers linkDiscoverers;

    RelationAssertions(LinkDiscoverers linkDiscoverers) {
        this.linkDiscoverers = linkDiscoverers;
    }

    Link findCancel(String responseJson) {
        LinkDiscoverer halDiscoverer = linkDiscoverers
                .getRequiredLinkDiscovererFor(MediaTypes.HAL_JSON);

        return halDiscoverer.findRequiredLinkWithRel(
                LinkRelation.of("cancel"), responseJson);
    }
}
```

`getRequiredLinkDiscovererFor(...)` chọn implementation phù hợp với media type và ném exception nếu không có discoverer tương ứng. `findRequiredLinkWithRel(...)` yêu cầu relation phải tồn tại; nếu không tìm thấy, nó ném `IllegalArgumentException`. Khi link có thể vắng mặt hợp lệ, dùng `findLinkWithRel(...)` để nhận `Optional<Link>`.

Ví dụ assertion:

```java
assertThat(cancel.getHref()).endsWith("/orders/42/cancellation");
assertThat(cancel.getRel()).isEqualTo(LinkRelation.of("cancel"));
```

Nếu ứng dụng không dùng Spring Boot auto-configuration, hãy bảo đảm Spring HATEOAS đã đăng ký `LinkDiscoverer` cho media type cần kiểm thử. Khi dùng `@EnableHypermediaSupport`, Spring HATEOAS có thể tự đăng ký discoverer JSONPath nếu thư viện JSONPath có trên classpath.

## 5. Kiểm thử response HTTP rồi mới phân tích link

Một cách kết hợp MockMvc và `LinkDiscoverer` là lấy body response thực tế, sau đó phân tích theo media type:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.client.LinkDiscoverers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLinkDiscovererTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    LinkDiscoverers linkDiscoverers;

    @Test
    void discoversCancelRelationFromHalResponse() throws Exception {
        MvcResult result = mockMvc.perform(get("/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andReturn();

        String json = result.getResponse().getContentAsString();
        LinkDiscoverer discoverer = linkDiscoverers
                .getRequiredLinkDiscovererFor(MediaTypes.HAL_JSON);

        Link cancel = discoverer.findRequiredLinkWithRel(
                LinkRelation.of("cancel"), json);

        assertThat(cancel.getHref()).endsWith("/orders/42/cancellation");
    }
}
```

Test này xác nhận đường đi từ request HTTP tới representation HAL và sau đó tìm relation theo đúng media type. Nó ít phụ thuộc cấu trúc JSON hơn assertion JSONPath trực tiếp.

## 6. Kiểm thử relation tùy chọn bằng Optional

Một số relation chỉ xuất hiện khi resource ở trạng thái nhất định. Ví dụ `cancel` chỉ có khi đơn hàng `PENDING`. Khi đơn hàng đã `SHIPPED`, việc không có link `cancel` là hành vi đúng.

```java
import java.util.Optional;

LinkDiscoverer discoverer = linkDiscoverers
        .getRequiredLinkDiscovererFor(MediaTypes.HAL_JSON);

Optional<Link> cancel = discoverer.findLinkWithRel(
        LinkRelation.of("cancel"), shippedOrderJson);

assertThat(cancel).isEmpty();
```

Với JSONPath:

```java
mockMvc.perform(get("/orders/42")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Test phải thiết lập trạng thái nghiệp vụ cụ thể, ví dụ đơn hàng đã giao. Không nên chỉ bỏ qua assertion vì test fixture không tạo được link; nếu link vắng mặt ngoài dự kiến, test cần thất bại.

Phân biệt hai loại assertion:

- Relation bắt buộc: dùng `findRequiredLinkWithRel(...)` hoặc assertion JSONPath `.exists()`.
- Relation tùy chọn: dùng `findLinkWithRel(...)` và kiểm tra `Optional`, hoặc `.doesNotExist()` cho scenario không có link.

## 7. Kiểm thử nhiều link cùng relation

HAL cho phép một relation chứa một link object hoặc một mảng link object. Khi có nhiều link cùng relation, nên dùng `findLinksWithRel(...)`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.Links;

Links alternates = discoverer.findLinksWithRel(
        LinkRelation.of("alternate"), orderWithAlternateLinksJson);

assertThat(alternates.toList()).hasSize(2);
assertThat(alternates.toList())
        .extracting(Link::getHref)
        .contains("/orders/42", "/orders/42.pdf");
```

`Links` là container iterable, có các API như `hasSize(...)`, `getLink(...)`, `getRequiredLink(...)`, `stream()` và `toList()`. `findLinksWithRel(...)` luôn trả về `Links`, kể cả khi không tìm thấy link.

Nếu chỉ cần một link, `findLinkWithRel(...)` trả link đầu tiên. Đừng dùng API tìm một link để khẳng định relation chỉ có một link; hãy kiểm tra số lượng bằng `findLinksWithRel(...)` khi cardinality là một phần hợp đồng.

## 8. Không phụ thuộc HAL single-link object hay array

HAL cho phép relation có một link được biểu diễn dưới dạng object hoặc array một phần tử. Spring HATEOAS mặc định serialize một link thành object; khi có nhiều link cùng relation, giá trị là array. Ứng dụng cũng có thể cấu hình chính sách luôn render link đơn thành array.

Vì vậy, test client hoặc contract nên tránh giả định một relation luôn có một JSON shape. Ví dụ:

```java
Links links = discoverer.findLinksWithRel(
        LinkRelation.of("alternate"), responseJson);

assertThat(links.toList()).hasSize(1);
assertThat(links.getRequiredLink("alternate").getHref())
        .endsWith("/orders/42.pdf");
```

Test trên vẫn hoạt động nếu serializer thay đổi từ object sang array mà semantics relation không đổi. Nếu API có cam kết rõ ràng về cấu trúc JSON, có thể kiểm tra JSONPath cụ thể; nhưng hãy xem đó là kiểm thử serialization policy, không phải kiểm thử semantics relation.

## 9. Kiểm thử relation chuẩn và extension relation

Relation chuẩn nên dùng hằng số `IanaLinkRelations` để giảm lỗi chính tả:

```java
import org.springframework.hateoas.IanaLinkRelations;

Link self = discoverer.findRequiredLinkWithRel(
        IanaLinkRelations.SELF, responseJson);

Link next = discoverer.findRequiredLinkWithRel(
        IanaLinkRelations.NEXT, collectionJson);
```

Extension relation có thể dùng `LinkRelation.of(...)`:

```java
Link refund = discoverer.findRequiredLinkWithRel(
        LinkRelation.of("https://api.example.com/rels/refund"), responseJson);
```

Nếu HAL sử dụng CURIE, relation key có thể xuất hiện dưới dạng `acme:refund`. Test cần xác nhận cả khai báo CURIE và relation rút gọn được công bố theo hợp đồng:

```java
assertThat(discoverer.findRequiredLinkWithRel(
        LinkRelation.of("curies"), responseJson).getHref())
        .contains("/rels/{rel}");

Link refund = discoverer.findRequiredLinkWithRel(
        LinkRelation.of("acme:refund"), responseJson);
assertThat(refund.getHref()).endsWith("/orders/42/refund");
```

Không thay relation URI bằng một URL endpoint trong test. Extension relation định danh semantics; href là đích link. Khi server đổi route nhưng giữ relation, test nên tiếp tục thành công nếu href mới vẫn thỏa hợp đồng.

## 10. Kiểm thử URI template và metadata của link

Nếu link chứa URI template, kiểm thử cả href và cờ `templated`:

```java
Link search = discoverer.findRequiredLinkWithRel(
        LinkRelation.of("search"), collectionJson);

assertThat(search.isTemplated()).isTrue();
assertThat(search.getHref()).contains("{?status,page,size}");
```

Với link có metadata, kiểm tra đúng thuộc tính được công bố:

```java
Link help = discoverer.findRequiredLinkWithRel(
        LinkRelation.of("help"), responseJson);

assertThat(help.getType()).contains("text/html");
assertThat(help.getTitle()).contains("Hướng dẫn đơn hàng");
assertThat(help.getHreflang()).contains("vi");
```

Các getter metadata như `getType()`, `getTitle()` và `getHreflang()` trả về chuỗi có thể là `null`, không phải `Optional`; dùng assertion tương ứng, ví dụ `isEqualTo("text/html")` hoặc `isNull()`. `findLinkWithRel(...)` mới là API trả về `Optional<Link>`. Không kiểm tra `templated: false` nếu hợp đồng không yêu cầu property đó, vì serializer có thể bỏ qua thuộc tính mặc định.

## 11. Kiểm thử link trong embedded resource

Một HAL document có thể chứa link ở cấp resource gốc và link bên trong `_embedded`. Ví dụ collection có các item, mỗi item lại có link `self` hoặc `customer`.

Mặc định, HAL link discoverer tìm link trong document theo cấu trúc gốc. Nếu cần tìm link đệ quy trong embedded resource, `HalLinkDiscoverer` cung cấp `inspectEmbeddeds()`:

```java
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

LinkDiscoverer embeddedDiscoverer = new HalLinkDiscoverer().inspectEmbeddeds();

Link customer = embeddedDiscoverer.findRequiredLinkWithRel(
        LinkRelation.of("customer"), collectionJson);
```

Hãy dùng chế độ đệ quy khi mục tiêu test thực sự là link nằm trong embedded representation. Nếu collection có nhiều item cùng relation `self`, hãy kiểm tra tất cả link bằng `findLinksWithRel(...)` hoặc parse từng embedded item riêng để tránh nhầm link của item này với item khác.

## 12. Kiểm thử relation theo state transition

Relation có thể thay đổi theo trạng thái nghiệp vụ. Ví dụ:

| Trạng thái đơn hàng | Relation dự kiến |
|---|---|
| `PENDING` | `self`, `customer`, `cancel`, `payment` |
| `PAID` | `self`, `customer`, `receipt` |
| `SHIPPED` | `self`, `customer`, `tracking` |
| `CANCELLED` | `self`, `customer` |

Test nên kiểm tra ma trận trạng thái thay vì chỉ test một response:

```java
@Test
void pendingOrderExposesCancelAndPayment() throws Exception {
    String json = getOrderJson("PENDING");

    assertThat(discoverer.findLinkWithRel("cancel", json)).isPresent();
    assertThat(discoverer.findLinkWithRel("payment", json)).isPresent();
    assertThat(discoverer.findLinkWithRel("receipt", json)).isEmpty();
}

@Test
void paidOrderExposesReceiptInsteadOfPayment() throws Exception {
    String json = getOrderJson("PAID");

    assertThat(discoverer.findLinkWithRel("receipt", json)).isPresent();
    assertThat(discoverer.findLinkWithRel("payment", json)).isEmpty();
    assertThat(discoverer.findLinkWithRel("cancel", json)).isEmpty();
}
```

`getOrderJson(...)` là helper test gọi endpoint sau khi fixture đặt đơn hàng vào trạng thái tương ứng. Trong test tích hợp, nên thay trạng thái qua service/repository fixture hợp lệ thay vì chỉnh trực tiếp JSON response.

Các test này bảo vệ hợp đồng state transition: client biết thao tác nào được công bố tại từng thời điểm. Endpoint vẫn phải kiểm tra trạng thái khi nhận request, vì trạng thái có thể thay đổi giữa lúc client đọc link và lúc gửi request.

## 13. Kiểm thử relation và authorization

Nếu API chỉ công bố link `approve` cho người dùng có quyền phê duyệt, hãy test cả hai ngữ cảnh:

- Người dùng có quyền: link `approve` xuất hiện khi trạng thái cho phép.
- Người dùng không có quyền: link `approve` không xuất hiện nếu đó là chính sách công bố của API.

Ví dụ test với Spring Security có thể dùng `@WithMockUser`:

```java
@Test
@WithMockUser(authorities = "ORDER_APPROVE")
void approverSeesApproveLink() throws Exception {
    mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.approve.href").exists());
}

@Test
@WithMockUser(authorities = "ORDER_READ")
void readerDoesNotSeeApproveLink() throws Exception {
    mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.approve").doesNotExist());
}
```

Các ví dụ giả định method security và fixture được cấu hình để link được thêm theo authority. Không xem việc ẩn link là biện pháp bảo mật duy nhất; endpoint `approve` vẫn phải xác thực và phân quyền khi được gọi trực tiếp.

## 14. Kiểm thử media type và content negotiation

Một relation được serialize đúng cấu trúc nhưng trả sai media type vẫn có thể khiến client chọn nhầm parser. Vì vậy, kiểm thử cả `Accept` và `Content-Type`:

```java
mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu API hỗ trợ nhiều media type, tạo test riêng cho từng loại và dùng `LinkDiscoverers.getRequiredLinkDiscovererFor(mediaType)` để chọn đúng parser. Không dùng HAL discoverer để phân tích representation UBER hoặc Collection+JSON.

Khi client gửi `Accept: application/json`, Spring Boot có thể cấu hình HAL làm JSON mặc định. Hành vi này phụ thuộc cấu hình `spring.hateoas.use-hal-as-default-json-media-type`; test nên dùng media type tường minh nếu hợp đồng yêu cầu HAL.

## 15. Kiểm thử link documentation bằng Spring REST Docs

Spring REST Docs có thể kiểm tra link trong response và sinh snippet `links.adoc`. Mặc định, `links(...)` hoạt động theo chế độ strict:

- Response có relation chưa được mô tả: test thất bại.
- Descriptor bắt buộc nhưng response không có relation: test thất bại.
- Descriptor `.optional()` cho phép relation vắng mặt.
- Descriptor `.ignored()` bỏ qua relation khỏi snippet mà không làm test thất bại vì link đó.
- `relaxedLinks(...)` cho phép response có thêm relation không được mô tả.

Ví dụ:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andDo(document("orders/get-order",
                links(
                        linkWithRel("self").description("Đơn hàng hiện tại"),
                        linkWithRel("customer").description("Khách hàng liên quan"),
                        linkWithRel("cancel").description("Yêu cầu hủy").optional()
                )));
```

Nếu link có `title`, REST Docs có thể dùng title làm description khi descriptor không khai báo description. Nếu cả hai đều không có, snippet không thể tạo mô tả hợp lệ.

Chế độ strict rất hữu ích để phát hiện relation mới chưa được cập nhật tài liệu. Dùng `relaxedLinks(...)` khi một test chỉ tài liệu hóa một phần link có chủ đích; không dùng relaxed mode cho tất cả endpoint nếu muốn tài liệu đóng vai trò kiểm soát hợp đồng.

## 16. Kiểm thử LinkDiscoverer cho nhiều hypermedia format

`LinkDiscoverers` là registry chọn `LinkDiscoverer` dựa trên media type. API có thể hỗ trợ HAL, HAL-FORMS hoặc format khác; test nên chọn parser tương ứng:

```java
LinkDiscoverer hal = linkDiscoverers
        .getRequiredLinkDiscovererFor(MediaTypes.HAL_JSON);

LinkDiscoverer halForms = linkDiscoverers
        .getRequiredLinkDiscovererFor(MediaTypes.HAL_FORMS_JSON);

Link self = hal.findRequiredLinkWithRel("self", halJson);
Link cancel = halForms.findRequiredLinkWithRel("self", halFormsJson);
```

HAL-FORMS mở rộng HAL và có thể được nhận diện bằng media type riêng. Nếu test chỉ cần `_links`, HAL discoverer có thể đủ; nếu cần kiểm tra template hoặc link trong một representation HAL-FORMS, chọn discoverer hỗ trợ media type đó.

Nếu media type không có discoverer được đăng ký, `getRequiredLinkDiscovererFor(...)` sẽ báo lỗi. Hãy kiểm tra cấu hình và dependency thay vì âm thầm dùng parser của format khác.

## 17. Tổ chức test để tránh phụ thuộc implementation

Một test relation bền vững nên xác nhận điều mà client được phép dựa vào:

- Relation có đúng semantics và tên ổn định.
- Link xuất hiện trong đúng trạng thái và ngữ cảnh quyền.
- `href` là URI hợp lệ và trỏ tới tài nguyên/hành động đúng.
- Metadata quan trọng như `type`, `title`, `hreflang`, `templated` có giá trị đúng nếu hợp đồng yêu cầu.
- Media type của response phù hợp với parser.

Tránh kiểm tra những chi tiết không thuộc hợp đồng:

- Host/port local cụ thể nếu không phải yêu cầu công khai.
- Thứ tự các property trong JSON.
- Thứ tự link trong `_links` nếu client không phụ thuộc thứ tự.
- Object hay array cho một relation đơn nếu API không cố định chính sách serialization.
- Tên method/controller nội bộ.

Nếu route thay đổi nhưng relation vẫn giữ semantics, test nên chỉ cần kiểm tra href mới đáp ứng điều kiện. Nếu route là một phần hợp đồng canonical, hãy tạo test riêng cho canonical URL thay vì ràng buộc mọi test relation vào một host cụ thể.

## 18. Ma trận kiểm thử relation đề xuất

Với một resource nghiệp vụ có nhiều trạng thái, có thể lập ma trận:

| Nhóm | Scenario | Assertion chính |
|---|---|---|
| Cấu trúc | Response HAL hợp lệ | Có `_links`, đúng `Content-Type`. |
| Relation bắt buộc | `self`, `customer` | Relation tồn tại và href đúng. |
| Relation có điều kiện | `cancel` khi `PENDING` | Có ở trạng thái cho phép, vắng ở trạng thái khác. |
| Cardinality | Nhiều `alternate` | `findLinksWithRel` trả đúng số link. |
| CURIE | `acme:refund` | CURIE và relation rút gọn được công bố. |
| URI template | `search` | `templated=true`, href chứa template variables. |
| Metadata | `help` | `type`, `title`, `hreflang` đúng. |
| Authorization | Người có/không có quyền | Link phản ánh policy công bố. |
| Embedded | Link nằm trong item nhúng | Discoverer đệ quy hoặc parse từng item. |
| Documentation | Relation mới xuất hiện | REST Docs strict test yêu cầu mô tả. |
| Content negotiation | HAL/HAL-FORMS | Parser và media type tương ứng. |

Không nhất thiết tạo một test cho mỗi dòng nếu các scenario có thể được nhóm bằng parameterized test. Quan trọng là ma trận thể hiện rõ những trạng thái và relation mà client cần dựa vào.

## 19. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra href mà không kiểm tra relation | URL đúng nhưng semantics có thể sai. | Tìm link theo relation và xác nhận href. |
| Hard-code host/port trong mọi test | Test dễ hỏng giữa môi trường. | Kiểm tra path hoặc URI contract cần thiết. |
| Dùng `findRequiredLinkWithRel` cho link tùy chọn | Test thất bại trong trạng thái hợp lệ không có link. | Dùng `findLinkWithRel` và kiểm tra Optional. |
| Dùng `findLinkWithRel` để kiểm tra cardinality | Bỏ sót link trùng relation. | Dùng `findLinksWithRel` và kiểm tra số lượng. |
| Giả định link đơn luôn là object | Test lỗi khi serializer dùng array. | Dùng `LinkDiscoverer` hoặc test serialization policy riêng. |
| Không kiểm tra state transition | Link cũ có thể xuất hiện sau khi trạng thái đổi. | Test ma trận trạng thái. |
| Dùng sai LinkDiscoverer | Không tìm thấy link dù response hợp lệ. | Chọn discoverer theo Content-Type. |
| Bỏ qua link trong embedded resource | Test nhầm link gốc với link của item. | Dùng `inspectEmbeddeds()` hoặc phân tích từng item. |
| Dùng REST Docs relaxed cho mọi test | Relation mới có thể không được tài liệu hóa. | Dùng strict `links()` cho hợp đồng chính. |
| Coi link ẩn là cơ chế phân quyền | Endpoint vẫn có thể bị gọi trực tiếp. | Kiểm tra authorization tại endpoint. |

## 20. Quy trình kiểm thử relation

1. Xác định media type và lấy response HTTP thực tế bằng MockMvc hoặc WebTestClient.
2. Xác nhận status code và `Content-Type`.
3. Chọn `LinkDiscoverer` tương ứng với media type.
4. Tìm relation bắt buộc bằng `findRequiredLinkWithRel(...)`.
5. Tìm relation tùy chọn bằng `findLinkWithRel(...)` và kiểm tra `Optional`.
6. Dùng `findLinksWithRel(...)` khi relation có thể có nhiều link.
7. Kiểm tra href, URI template và metadata theo hợp đồng.
8. Lặp lại test với các trạng thái nghiệp vụ và quyền truy cập khác nhau.
9. Kiểm tra link trong embedded resource nếu response có `_embedded`.
10. Dùng Spring REST Docs strict snippets để phát hiện relation chưa được mô tả.
11. Tránh ràng buộc test vào host, thứ tự JSON hoặc implementation nội bộ không thuộc hợp đồng.

Kiểm thử relation xác nhận API công bố đúng khả năng điều hướng tại đúng thời điểm. Khi test kiểm tra semantics, trạng thái, href và media type thay vì chỉ so sánh chuỗi URL, hợp đồng hypermedia có thể thay đổi route hoặc cách serialize mà vẫn giữ client tương thích.

## Tài liệu tham khảo

- [Spring HATEOAS – LinkDiscoverer API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverer.html)
- [Spring HATEOAS – LinkDiscoverers API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverers.html)
- [Spring HATEOAS – HalLinkDiscoverer API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalLinkDiscoverer.html)
- [Spring HATEOAS – Links API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Links.html)
- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring REST Docs – Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
