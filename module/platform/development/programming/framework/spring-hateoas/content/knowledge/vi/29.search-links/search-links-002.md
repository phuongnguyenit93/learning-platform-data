# Link đến tìm kiếm

Một API thường cung cấp nhiều cách tìm một tập tài nguyên: lọc theo trạng thái, khách hàng, khoảng thời gian, từ khóa hoặc kết hợp nhiều điều kiện. Nếu client phải tự biết endpoint và tự ghép query string, nó bị phụ thuộc vào cấu trúc URL của server. **Search link** giải quyết vấn đề này bằng cách công bố một liên kết dẫn đến khả năng tìm kiếm, kèm thông tin về các tham số mà client có thể dùng.

Trong Spring HATEOAS, có thể dùng relation chuẩn `search` (`IanaLinkRelations.SEARCH`) để chỉ ra liên kết tìm kiếm. URI template mô tả các query parameter có thể thay đổi, còn `Affordances` và `QueryParameter` có thể mô tả thao tác GET cùng các tham số đầu vào. Client đọc link từ representation, mở rộng template bằng giá trị tìm kiếm và theo link đó để nhận kết quả.

## 1. Search link là gì?

Search link là hypermedia link trỏ đến một endpoint có khả năng tìm kiếm resource hoặc collection liên quan. Link có hai thành phần quan trọng:

- `href`: URI hoặc URI template của endpoint tìm kiếm.
- `rel`: relation mô tả ý nghĩa của link. Với tìm kiếm, dùng relation chuẩn `search` khi ngữ nghĩa phù hợp.

Ví dụ, API gốc có thể công bố link tìm đơn hàng:

```json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/orders{?status,customerId,page,size,sort}",
      "templated": true
    }
  }
}
```

Client biết rằng có thể tìm kiếm qua link `search` và các biến template được liệt kê. Nó không cần tự đoán endpoint `/orders`, cũng không cần hard-code thứ tự query parameter.

Relation `search` mô tả mối quan hệ giữa resource hiện tại với một resource có thể dùng để tìm kiếm trong ngữ cảnh đó. Nó không phải tên của một HTTP method và cũng không quy định cụ thể thuật toán tìm kiếm.

## 2. Search endpoint và query parameter

Một search endpoint thường dùng HTTP `GET` khi thao tác chỉ đọc và các điều kiện tìm kiếm được biểu diễn bằng query parameter. Ví dụ:

```http
GET /orders?status=PAID&customerId=7c180000-0000-0000-0000-000000000001&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

| Parameter | Ý nghĩa |
| --- | --- |
| `status` | Lọc theo trạng thái đơn hàng |
| `customerId` | Lọc theo khách hàng |
| `page` | Trang cần lấy |
| `size` | Số phần tử tối đa trong một trang |
| `sort` | Tiêu chí sắp xếp |

Các query parameter là một phần của hợp đồng search endpoint. Server cần công bố tên, kiểu dữ liệu, giá trị được chấp nhận và cách xử lý khi tham số bị thiếu hoặc không hợp lệ.

Với điều kiện tìm kiếm phức tạp hoặc payload lớn, API có thể dùng một thiết kế khác, chẳng hạn `POST` đến search resource với body chứa điều kiện. Khi đó, link vẫn mô tả khả năng tìm kiếm nhưng affordance phải phản ánh đúng HTTP method và kiểu payload. Không nên dùng GET với request body vì hành vi của client, proxy và cache đối với GET body không nhất quán.

## 3. Khai báo search handler trong Spring MVC

Ví dụ controller tìm kiếm đơn hàng theo trạng thái và khách hàng:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderSearchService searchService;
    private final OrderModelAssembler orderAssembler;

    OrderController(
            OrderSearchService searchService,
            OrderModelAssembler orderAssembler) {
        this.searchService = searchService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    PagedModel<EntityModel<OrderRepresentation>> search(
            @RequestParam(name = "status", required = false) OrderStatus status,
            @RequestParam(name = "customerId", required = false) UUID customerId,
            @PageableDefault(size = 20, sort = "createdAt",
                    direction = Sort.Direction.DESC) Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> result = searchService.search(status, customerId, pageable);
        return pagedAssembler.toModel(result, orderAssembler);
    }
}
```

`OrderRepresentation` là DTO response, có thể khai báo gọn như sau:

```java
import java.util.UUID;

public record OrderRepresentation(UUID id, OrderStatus status) {
}
```

Ví dụ giả định `Order`, `OrderStatus`, `OrderSearchService` và `OrderModelAssembler` là các kiểu miền và thành phần ứng dụng đã được triển khai. Interface service có thể có chữ ký:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

interface OrderSearchService {
    Page<Order> search(OrderStatus status, UUID customerId, Pageable pageable);
}
```

`OrderSearchService` chịu trách nhiệm áp dụng điều kiện tìm kiếm; `OrderModelAssembler` chuyển từng đơn hàng thành representation có link. `Pageable` nhận `page`, `size` và `sort` từ Spring Data Web. `PagedResourcesAssembler` chuyển `Page<Order>` thành `PagedModel` với metadata và link điều hướng.

Ở đây `status` và `customerId` là tham số tùy chọn. Nếu client bỏ qua chúng, service trả về collection theo các điều kiện mặc định của API. Hãy xác định rõ ý nghĩa của việc không truyền filter: tìm trong toàn bộ collection, dùng một mặc định nghiệp vụ hay từ chối request. Đừng để hành vi này phụ thuộc vào một giả định không được công bố.

## 4. Dùng relation chuẩn search

Spring HATEOAS cung cấp `IanaLinkRelations.SEARCH` cho relation chuẩn `search`. Có thể dùng nó khi tạo link đến endpoint tìm kiếm:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

Link searchLink = linkTo(OrderController.class)
        .withRel(IanaLinkRelations.SEARCH);
```

`linkTo(OrderController.class)` đọc mapping cấp lớp của controller để tạo URI collection, nên không cần lặp chuỗi `"/orders"` trong assembler. `withRel(IanaLinkRelations.SEARCH)` gắn ngữ nghĩa tìm kiếm vào link.

Đoạn code này tạo link đến collection endpoint. Nó chưa mô tả những query parameter mà client có thể truyền. Để client khám phá các điều kiện tìm kiếm, hãy bổ sung URI template hoặc affordance như các phần tiếp theo.

## 5. Thêm query parameter bằng URI template

URI template theo RFC 6570 cho phép một link chứa các biến mà client có thể mở rộng. Spring HATEOAS cung cấp `UriTemplate`, `TemplateVariable` và `TemplateVariable.VariableType.REQUEST_PARAM` để khai báo query parameter.

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.TemplateVariable.VariableType.REQUEST_PARAM;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

@Component
class OrderSearchLinkProvider {

    Link searchLink() {
        String collectionUri = linkTo(OrderController.class).toUri().toString();

        UriTemplate template = UriTemplate.of(collectionUri)
                .with(new TemplateVariable("status", REQUEST_PARAM))
                .with(new TemplateVariable("customerId", REQUEST_PARAM))
                .with(new TemplateVariable("page", REQUEST_PARAM))
                .with(new TemplateVariable("size", REQUEST_PARAM))
                .with(new TemplateVariable("sort", REQUEST_PARAM));

        return Link.of(template.toString(), IanaLinkRelations.SEARCH);
    }
}
```

Mỗi `TemplateVariable` khai báo một query parameter. Spring HATEOAS tạo base URI từ mapping controller; phần template bổ sung các biến có thể thay đổi. Kết quả là một link `search` có dạng:

```text
https://api.example.test/orders{?status,customerId,page,size,sort}
```

Các biến trong template không bắt buộc phải có giá trị ngay khi server tạo link. Client có thể chỉ truyền những điều kiện cần thiết; các biến còn lại được bỏ qua khi mở rộng URI.

## 6. Mở rộng URI template ở client

Một `Link` có thể kiểm tra xem URI có phải template không, lấy tên biến và mở rộng bằng map giá trị:

```java
// apiRoot là representation client đã đọc từ response HAL.
import java.util.Map;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

EntityModel<ApiRootRepresentation> apiRoot = readApiRoot();
Link searchLink = apiRoot.getRequiredLink(IanaLinkRelations.SEARCH);

Map<String, Object> parameters = Map.of(
        "status", "PAID",
        "customerId", "7c180000-0000-0000-0000-000000000001",
        "page", 0,
        "size", 20,
        "sort", "createdAt,desc");

Link concreteLink = searchLink.expand(parameters);
String requestUri = concreteLink.getHref();
```

`expand(...)` thay các biến đã cung cấp bằng giá trị tương ứng và trả về link với URI cụ thể. Client không cần tự nối `?`, `&` hoặc tự mã hóa từng giá trị query.

`readApiRoot()` trong ví dụ là lời gọi HTTP của client và bước deserialize response thành `EntityModel<ApiRootRepresentation>`; cách thực hiện phụ thuộc client đang dùng `RestClient`, `WebClient` hay `Traverson`.

Có thể xem tên biến mà server công bố:

```java
if (searchLink.isTemplated()) {
    System.out.println(searchLink.getVariableNames());
}
```

Ứng dụng client có thể dùng danh sách biến để tạo form tìm kiếm hoặc kiểm tra xem điều kiện nào được hỗ trợ. Cách hiển thị label, kiểu input và ràng buộc dữ liệu cần metadata bổ sung nếu client không thể suy ra từ tên biến.

## 7. Mô tả tham số tìm kiếm bằng Affordances

URI template cho biết tên biến có thể mở rộng. Nếu cần mô tả thêm HTTP method, output model và tính bắt buộc của từng tham số, Spring HATEOAS cung cấp `Affordances` và `QueryParameter`.

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

Link searchWithAffordance() {
    Link search = linkTo(OrderController.class)
            .withRel(IanaLinkRelations.SEARCH);

    return Affordances.of(search)
            .afford(HttpMethod.GET)
            .withOutput(OrderRepresentation.class)
            .addParameters(
                    QueryParameter.optional("status"),
                    QueryParameter.optional("customerId"),
                    QueryParameter.optional("page"),
                    QueryParameter.optional("size"),
                    QueryParameter.optional("sort"))
            .withName("searchOrders")
            .toLink();
}
```

`Affordances.of(search)` bắt đầu mô tả thao tác trên link đã có. `afford(HttpMethod.GET)` khai báo phương thức HTTP; `withOutput(...)` mô tả kiểu dữ liệu đầu ra; `addParameters(...)` bổ sung các query parameter. `QueryParameter.optional(...)` biểu thị tham số không bắt buộc. Nếu có điều kiện phải cung cấp, dùng `QueryParameter.required(...)`.

Đoạn code là method fragment có thể đặt trong `OrderSearchLinkProvider`; nó dùng cùng base mapping `/orders` nhưng mô tả thêm tham số của thao tác GET.

Tên `searchOrders` định danh affordance. Media type cụ thể quyết định metadata affordance được serialize ra response như thế nào. HAL-FORMS hoặc một media type có hỗ trợ affordance có thể biểu diễn thêm template cho thao tác; HAL cơ bản vẫn chủ yếu biểu diễn link và URI template.

## 8. Kết hợp URI template và affordance

Hai cơ chế phục vụ hai nhu cầu khác nhau:

| Cơ chế | Thông tin client nhận được |
| --- | --- |
| URI template | Các biến URI có thể mở rộng, ví dụ `status`, `page`, `sort` |
| Affordance | HTTP method, kiểu output và metadata query parameter |
| Search relation | Ý nghĩa của link: đây là khả năng tìm kiếm |

Trong ứng dụng thực tế, có thể tạo URI template từ controller mapping, sau đó gắn affordance vào cùng link:

Đây là method fragment bên trong `OrderSearchLinkProvider`, sử dụng `searchLink()` đã khai báo ở phần trước.

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

Link searchLinkWithAffordance() {
    Link templateLink = searchLink();

    return Affordances.of(templateLink)
            .afford(HttpMethod.GET)
            .withOutput(OrderRepresentation.class)
            .addParameters(
                    QueryParameter.optional("status"),
                    QueryParameter.optional("customerId"),
                    QueryParameter.optional("page"),
                    QueryParameter.optional("size"),
                    QueryParameter.optional("sort"))
            .withName("searchOrders")
            .toLink();
}
```

Khi đó link giữ relation `search` và URI template, đồng thời mang affordance mô tả thao tác GET. Client có thể dùng URI template để mở rộng địa chỉ; client hiểu media type affordance có thể dùng thêm metadata để dựng giao diện tìm kiếm.

Không phải mọi media type đều serialize affordance. Nếu client chỉ nhận `application/hal+json`, hãy dựa vào link và URI template. Nếu cần form metadata, hãy thương lượng media type hỗ trợ affordance, chẳng hạn HAL-FORMS.

## 9. Gắn search link vào representation

Search link thường được công bố ở API root hoặc một resource collection có ngữ cảnh tìm kiếm. Ví dụ root representation:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiRootController {

    private final OrderSearchLinkProvider orderSearchLinks;

    ApiRootController(OrderSearchLinkProvider orderSearchLinks) {
        this.orderSearchLinks = orderSearchLinks;
    }

    @GetMapping("/api")
    EntityModel<ApiRootRepresentation> root() {
        return EntityModel.of(
                new ApiRootRepresentation("Order service"),
                orderSearchLinks.searchLink());
    }
}
```

DTO root có thể là:

```java
public record ApiRootRepresentation(String name) {
}
```

`ApiRootRepresentation` là DTO mô tả API root. `OrderSearchLinkProvider` là component đóng gói cách tạo search link bằng URI template hoặc affordance. Root response có thể được serialize thành:

```json
{
  "name": "Order service",
  "_links": {
    "search": {
      "href": "https://api.example.test/orders{?status,customerId,page,size,sort}",
      "templated": true
    }
  }
}
```

Client bắt đầu từ `/api`, đọc relation `search`, rồi mở rộng link để tìm đơn hàng. Nếu endpoint có nhiều loại tìm kiếm, API có thể công bố nhiều relation hoặc nhiều link cùng relation theo một quy ước rõ ràng.

## 10. Tìm kiếm với nhiều điều kiện và sort

Một search endpoint có thể kết hợp filter, pagination và sorting. Các điều kiện lọc xác định tập kết quả; `page` và `size` xác định phần dữ liệu cần lấy; `sort` xác định thứ tự.

Ví dụ client tìm đơn hàng đã thanh toán của một khách hàng:

```text
GET /orders?status=PAID&customerId=7c180000-0000-0000-0000-000000000001&page=0&size=20&sort=createdAt,desc
```

Nếu `sort` hỗ trợ nhiều tiêu chí, API có thể nhận tham số lặp:

```text
GET /orders?status=PAID&sort=createdAt,desc&sort=id,asc
```

Khi công bố search link, cần liệt kê các biến mà endpoint thật sự hỗ trợ. Không thêm biến `sort`, `page` hoặc filter vào template nếu handler không nhận hoặc không xử lý chúng. Ngược lại, nếu handler có filter nhưng link không công bố, client sẽ không thể khám phá đầy đủ khả năng tìm kiếm.

Với filter dạng collection, cần thống nhất cách truyền nhiều giá trị. Spring MVC hỗ trợ cách lặp tên query parameter và cách phân tách bằng dấu phẩy; `@NonComposite` có thể điều khiển cách Spring HATEOAS render collection-valued request parameter khi tạo link từ method invocation.

## 11. Phân trang kết quả tìm kiếm

Khi search handler trả `Page<T>`, `PagedResourcesAssembler` chuyển kết quả thành `PagedModel`. Các link `self`, `first`, `prev`, `next` và `last` giúp client điều hướng trong tập kết quả.

Các link phân trang cần giữ nguyên điều kiện tìm kiếm. Ví dụ, khi client đang lọc `status=PAID`, link `next` phải giữ filter này cùng sort hiện tại; nếu mất filter, client sẽ chuyển sang một tập dữ liệu khác.

Client nên theo link `next` do server cung cấp thay vì tự tạo URL bằng cách tăng `page`. Điều này giữ client độc lập với tên query parameter, quy tắc pagination và cấu trúc route của server.

Với dữ liệu thay đổi thường xuyên, pagination theo offset có thể làm phần tử dịch chuyển giữa các trang. Hãy cân nhắc cursor/keyset pagination khi yêu cầu tìm kiếm cần điều hướng ổn định trên tập dữ liệu lớn hoặc biến động liên tục.

## 12. Client sử dụng search link như thế nào?

Một client hypermedia có thể thực hiện quy trình sau:

1. Gọi API root và đọc `_links.search`.
2. Kiểm tra link có phải URI template không và lấy danh sách biến.
3. Dựa vào affordance hoặc metadata của media type để dựng các trường tìm kiếm.
4. Thu thập giá trị từ người dùng và mở rộng URI template.
5. Gửi GET đến URI đã mở rộng với `Accept` phù hợp.
6. Đọc response, hiển thị kết quả và theo các link phân trang nếu cần.

Client không nên tự ghép URL từ chuỗi `/orders` hoặc giả định query parameter luôn có tên như hiện tại. Khi server đổi route nhưng giữ relation và metadata hợp đồng, client vẫn có thể khám phá khả năng tìm kiếm.

Nếu client không hiểu relation `search` hoặc media type của affordance, nó cần fallback theo khả năng hỗ trợ đã định nghĩa. Không nên gửi request đến link chỉ vì thấy một chuỗi `href`; client phải hiểu relation và định dạng representation mà server công bố.

## 13. Kiểm tra dữ liệu và bảo mật tìm kiếm

Search link công bố khả năng tìm kiếm, không cấp quyền truy cập dữ liệu. Server vẫn phải:

- Kiểm tra kiểu dữ liệu và định dạng query parameter.
- Giới hạn page size và số lượng điều kiện lọc.
- Chỉ cho phép các field sort/filter được công khai.
- Áp dụng authorization để chỉ trả dữ liệu người dùng được phép xem.
- Tránh xây dựng truy vấn động từ tên field hoặc biểu thức tùy ý do client gửi.
- Kiểm soát chi phí truy vấn và thời gian xử lý.

Không nên đưa thông tin nhạy cảm vào URI template hoặc query parameter. URL thường xuất hiện trong log, lịch sử trình duyệt, cache và telemetry. Với dữ liệu tìm kiếm nhạy cảm hoặc payload lớn, cân nhắc một thao tác POST search có body và affordance tương ứng.

## 14. Kiểm thử search link

Kiểm thử nên xác nhận relation, URI template và các biến được công bố đúng. Với Spring MVC, `MockMvc` tạo request context thật cho `WebMvcLinkBuilder` và cho phép kiểm tra response sau serialize:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiRootSearchLinkTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesTemplatedSearchLink() throws Exception {
        mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.search.href").exists())
                .andExpect(jsonPath("$._links.search.href")
                        .value(containsString("status")))
                .andExpect(jsonPath("$._links.search.href")
                        .value(containsString("customerId")))
                .andExpect(jsonPath("$._links.search.templated").value(true));
    }
}
```

Ngoài ra, nên kiểm tra:

- Từng biến template khớp với query parameter mà controller nhận.
- URI mở rộng có mã hóa ký tự đặc biệt đúng cách.
- Filter được giữ nguyên trong link phân trang.
- Search trả kết quả đúng khi chỉ có một filter hoặc nhiều filter.
- Tham số không hợp lệ trả status code và lỗi theo hợp đồng API.
- Client không thể tìm thấy dữ liệu ngoài phạm vi authorization.
- Media type HAL-FORMS hiển thị affordance khi endpoint cần mô tả form.

## 15. Lỗi thường gặp

**Chỉ công bố URL collection mà không có relation:** client không biết link đó có ý nghĩa tìm kiếm. Dùng relation `search` khi phù hợp.

**Dùng link thường cho endpoint có nhiều query parameter:** client phải tự biết tên filter và tự ghép URL. Dùng URI template để công bố các biến.

**Nhầm URI template với form metadata:** template cho biết biến URI; affordance có thể mô tả method, output và tham số. Dùng đúng mức metadata client cần.

**Giả định HAL cơ bản serialize mọi affordance:** affordance được chuyển thành representation theo media type. Chọn media type hỗ trợ nếu cần template thao tác.

**Công bố biến không được endpoint hỗ trợ:** client tạo request không hợp lệ. Đồng bộ template với chữ ký handler và kiểm thử.

**Làm mất filter trong link phân trang:** client rời khỏi tập kết quả đang tìm. Giữ filter, sort và ngữ cảnh tìm kiếm trong các link tiếp theo.

**Coi search link là quyền truy cập:** client vẫn có thể sửa URL hoặc gửi request trực tiếp. Server phải xác thực và phân quyền mỗi request.

**Đưa dữ liệu nhạy cảm vào query string:** URL có thể bị ghi log hoặc lưu trong lịch sử. Dùng phương thức phù hợp hơn khi dữ liệu tìm kiếm cần bảo vệ.

## 16. Checklist triển khai

- Khai báo một search endpoint có ngữ nghĩa và HTTP method rõ ràng.
- Dùng `IanaLinkRelations.SEARCH` để công bố quan hệ tìm kiếm.
- Dùng `WebMvcLinkBuilder` để tạo base URI từ mapping controller.
- Dùng `UriTemplate` và `TemplateVariable` cho query parameter có thể thay đổi.
- Dùng `Affordances` và `QueryParameter` nếu cần mô tả thao tác và tham số chi tiết.
- Chỉ công bố những filter, page, size và sort mà handler thực sự hỗ trợ.
- Đồng bộ query parameter với `@RequestParam` và `Pageable`.
- Giữ filter/sort trong link phân trang.
- Chọn media type hỗ trợ affordance nếu client cần metadata form.
- Xác thực dữ liệu, giới hạn truy vấn và phân quyền ở server.
- Kiểm thử relation, URI template, biến và link điều hướng bằng `MockMvc`.
- Hướng dẫn client khám phá link thay vì hard-code endpoint.

Search link giúp REST API công bố khả năng tìm kiếm ngay trong hypermedia. Khi relation `search` mô tả đúng ý nghĩa, URI template liệt kê query parameter và affordance bổ sung metadata khi cần, client có thể khám phá, dựng giao diện và gửi request mà không phụ thuộc vào cấu trúc URL nội bộ của server.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates)
- [Spring HATEOAS Reference – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc)
- [Spring HATEOAS Reference – Building affordances manually](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS API – QueryParameter](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
