# Kiểm thử pagination link

Một endpoint trả danh sách đơn hàng có thể chia kết quả thành nhiều trang. Khi client đang xem trang đầu, response cần cho biết trang kế tiếp ở đâu; khi ở trang cuối, client cần biết trang trước và trang đầu. Nếu chỉ kiểm tra HTTP status `200` hoặc số item trong response, test chưa chứng minh các link điều hướng được tạo đúng. Kiểm thử pagination link phải xác nhận cả metadata trang, relation, URI đích và khả năng theo link sang trang tiếp theo.

Spring HATEOAS kết hợp Spring Data hỗ trợ biểu diễn kết quả phân trang bằng `PagedModel` và tạo các link `first`, `prev`, `self`, `next`, `last` thông qua `PagedResourcesAssembler`. Với HAL, các link nằm trong `_links`, còn thông tin phân trang nằm trong `page`. MockMvc có thể kiểm tra response sau khi Spring MVC đã serialize model thành HAL.

## Hợp đồng phân trang trong HAL

Một response phân trang có hai phần độc lập nhưng bổ trợ nhau:

- **Page metadata:** cho biết số trang hiện tại, kích thước trang, tổng số phần tử và tổng số trang.
- **Pagination links:** cung cấp URI để client đi đến trang đầu, trước, hiện tại, kế tiếp hoặc cuối.

Ví dụ trang đầu của collection có năm đơn hàng, mỗi trang hai đơn hàng:

```json
{
  "_embedded": {
    "orders": [
      { "id": "ord-1042", "status": "PENDING" },
      { "id": "ord-1043", "status": "PAID" }
    ]
  },
  "_links": {
    "self": { "href": "https://api.example.com/api/orders?page=0&size=2" },
    "first": { "href": "https://api.example.com/api/orders?page=0&size=2" },
    "next": { "href": "https://api.example.com/api/orders?page=1&size=2" },
    "last": { "href": "https://api.example.com/api/orders?page=2&size=2" }
  },
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 0
  }
}
```

Trong ví dụ:

| Thành phần | Ý nghĩa |
| --- | --- |
| `_embedded.orders` | Các item của trang hiện tại. |
| `_links.self` | URI của trang đang xem, bao gồm query hiện tại. |
| `_links.first` | URI của trang đầu. |
| `_links.prev` | URI của trang trước, nếu có. |
| `_links.next` | URI của trang kế tiếp, nếu có. |
| `_links.last` | URI của trang cuối. |
| `page.number` | Chỉ số trang hiện tại, thường zero-based với Spring Data. |
| `page.size` | Kích thước trang được áp dụng. |
| `page.totalElements` | Tổng số phần tử phù hợp với truy vấn. |
| `page.totalPages` | Tổng số trang theo kích thước trang. |

Tên relation `prev` là relation điều hướng về trang trước. Không nhầm `next` với item kế tiếp trong collection: các relation này điều hướng giữa các page, còn self link của embedded item trỏ đến một item cụ thể.

## Tạo pagination links bằng Spring HATEOAS

Với controller Spring MVC dùng Spring Data, `Pageable` nhận query parameter `page`, `size` và `sort`. `PagedResourcesAssembler` chuyển `Page<T>` thành `PagedModel<R>` và tạo metadata cùng các page links.

Ví dụ assembler cho item:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        return EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

Controller dùng `PagedResourcesAssembler`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    OrderController(OrderService orderService,
                    OrderModelAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(path = "/api/orders", produces = MediaTypes.HAL_JSON_VALUE)
    PagedModel<EntityModel<OrderView>> findOrders(
            @RequestParam(name = "status", required = false) OrderStatus status,
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.search(status, pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
```

Ví dụ giả định ứng dụng đã cấu hình Spring Data web support, có `OrderService.search(...)`, `OrderModelAssembler` và DTO `OrderView`. Trong Spring Boot, Spring Data web support thường được auto-configure khi dependency phù hợp có trên classpath. Ở ứng dụng MVC thuần, cần đăng ký các argument resolver tương ứng.

`PagedResourcesAssembler` lấy request hiện tại làm cơ sở để tạo link phân trang. Các filter như `status` và tiêu chí sort cần được giữ lại khi client theo `next` hoặc `prev`. Vì vậy, test phải xác nhận query context trong `href`, không chỉ kiểm tra relation có tồn tại.

## Những gì cần kiểm thử

Một bộ test pagination link tốt xác minh ít nhất bốn khía cạnh:

1. **Representation:** response có `Content-Type` HAL, `_embedded` và `page` metadata đúng.
2. **Relations:** các link `first`, `prev`, `self`, `next`, `last` xuất hiện hoặc vắng mặt đúng với vị trí trang.
3. **Target URI:** query `page`, `size`, `sort` và filter được giữ đúng trong `href`.
4. **Traversal:** client có thể lấy `next.href`, gửi request đến URI đó và nhận đúng trang kế tiếp.

Không chỉ kiểm tra chuỗi URL nguyên vẹn. Host, thứ tự query parameter hoặc cách encode có thể thay đổi theo môi trường. Hãy phân tích URI rồi kiểm tra từng thành phần có ý nghĩa.

## Chuẩn bị dữ liệu test xác định được

Giả sử test fixture có năm đơn hàng phù hợp filter `status=PENDING`, và request dùng `size=2`. Khi đó:

- Trang `0` có hai item, `totalElements=5`, `totalPages=3`.
- Trang `1` có hai item.
- Trang `2` có một item.

Dữ liệu phải ổn định giữa các lần chạy. Nếu nhiều đơn hàng có cùng `createdAt`, nên thêm sort key phụ duy nhất như `id` để thứ tự không đổi giữa các page:

```http
GET /api/orders?status=PENDING&page=0&size=2&sort=createdAt,desc&sort=id,asc
```

Sort ổn định giúp tránh trường hợp item bị lặp hoặc bị bỏ qua khi client chuyển page trong lúc dữ liệu không đổi. Nếu không cố định thứ tự, test pagination có thể thất bại ngẫu nhiên dù link vẫn đúng.

## Kiểm thử trang đầu

Trang đầu phải có link đến trang hiện tại, trang đầu, trang kế tiếp và trang cuối nếu collection có nhiều trang. Không có trang trước, nên relation `prev` không nên xuất hiện theo hợp đồng phổ biến.

Ví dụ MockMvc:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .param("sort", "id,asc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(5))
    .andExpect(jsonPath("$.page.totalPages").value(3))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$._links.prev").doesNotExist());
```

Test giả định endpoint trả HAL và fixture có đúng năm kết quả sau filter. Nếu API chọn quy ước khác cho first/last link hoặc relation không khả dụng, hãy kiểm tra theo hợp đồng mà API công bố.

## Kiểm thử trang giữa

Trang giữa phải cho phép đi cả về trước và tiếp về sau. Với ba trang, page `1` là trang giữa:

```java
mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "1")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists());
```

Test này tập trung vào topology của link. Nếu API có nhiều hơn ba trang, trang giữa vẫn phải có `prev` và `next`; không nên hard-code `last` bằng một page number cụ thể trừ khi fixture và hợp đồng test yêu cầu.

## Kiểm thử trang cuối

Trang cuối có link quay về trước và link đến trang đầu, nhưng không có trang kế tiếp:

```java
mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "2")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.number").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(5))
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$._links.next").doesNotExist());
```

Trang cuối có thể chứa ít item hơn `page.size`. Trong ví dụ này, `page.size` vẫn là `2` trong khi `_embedded.orders` chỉ có một item. Không dùng số item của trang cuối để suy ra page size đã yêu cầu.

## Kiểm tra query parameters trong href

Một pagination link chỉ hữu ích nếu nó giữ ngữ cảnh truy vấn. Khi request có filter và sort, link `next` phải mang các điều kiện đó cùng page number mới.

Thay vì so sánh toàn bộ URL dưới dạng chuỗi, lấy `href` rồi phân tích query:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static com.jayway.jsonpath.JsonPath.read;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.util.MultiValueMap;
import org.springframework.web.util.UriComponentsBuilder;

MvcResult result = mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String body = result.getResponse().getContentAsString();
String nextHref = read(body, "$._links.next.href");

MultiValueMap<String, String> query = UriComponentsBuilder
    .fromUri(URI.create(nextHref))
    .build()
    .getQueryParams();

assertThat(query.getFirst("page")).isEqualTo("1");
assertThat(query.getFirst("size")).isEqualTo("2");
assertThat(query.getFirst("status")).isEqualTo("PENDING");
assertThat(query.get("sort")).contains("createdAt,desc");
```

Đoạn test giả định API dùng tên parameter mặc định của Spring Data (`page`, `size`, `sort`) và filter `status`. Nếu ứng dụng đổi tên parameter bằng resolver tùy chỉnh, hãy kiểm tra tên công khai đã cấu hình.

Query parameter có thể được encode trong URI. `UriComponentsBuilder` giúp đọc query đã parse; không so sánh raw string như `?page=1&size=2&sort=createdAt,desc` vì thứ tự parameter hoặc cách encode dấu phẩy có thể khác mà URI vẫn tương đương.

Có thể dùng một helper nhỏ để kiểm tra page number của từng relation:

```java
private static int pageNumber(String href) {
    String value = UriComponentsBuilder.fromUriString(href)
        .build()
        .getQueryParams()
        .getFirst("page");
    return Integer.parseInt(value);
}
```

Sau khi đọc response body thành JSON, xác nhận target của các link:

```java
String firstHref = read(body, "$._links.first.href");
String selfHref = read(body, "$._links.self.href");
String nextHref = read(body, "$._links.next.href");
String lastHref = read(body, "$._links.last.href");

assertThat(pageNumber(firstHref)).isZero();
assertThat(pageNumber(selfHref)).isZero();
assertThat(pageNumber(nextHref)).isEqualTo(1);
assertThat(pageNumber(lastHref)).isEqualTo(2);
```

Ví dụ này dùng fixture ba trang và response của trang đầu. Với trang giữa, kiểm tra `prev` là page `0` và `next` là page `2`; với trang cuối, kiểm tra `prev` là page `1` và `last` là page `2`.

## Theo next link sang trang kế tiếp

Kiểm thử mạnh hơn là lấy `next.href` từ response đầu, gửi request đến URI đó rồi kiểm tra page metadata của response mới. Cách này chứng minh link thực sự điều hướng đến trang kế tiếp.

```java
import static com.jayway.jsonpath.JsonPath.read;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

MvcResult firstPage = mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String nextHref = read(
    firstPage.getResponse().getContentAsString(), "$._links.next.href");

mockMvc.perform(get(URI.create(nextHref)).accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$._links.prev.href").exists());
```

MockMvc nhận URI đích lấy trực tiếp từ response. Nếu môi trường test dùng host khác hoặc absolute URI không phù hợp với mock servlet context, có thể parse `URI` rồi dùng `get(uri.getRawPath()).queryParams(...)`; điều quan trọng là các query value được lấy từ chính link đã công bố, không dựng lại page number theo giả định riêng của test.

## Kiểm tra self link giữ đúng truy vấn hiện tại

`self.href` phải đại diện cho page hiện tại với filter, sort và page size đang áp dụng. Ví dụ request `status=PENDING&page=1&size=2` thì self link cần giữ các điều kiện tương ứng.

Kiểm tra `self` riêng giúp phát hiện lỗi khi server tạo `next` đúng nhưng `self` bị mất filter, hoặc ngược lại. Có thể tái sử dụng cách phân tích query bằng `UriComponentsBuilder` cho cả hai relation.

## Kiểm thử collection một trang và collection rỗng

Khi tổng số phần tử nhỏ hơn hoặc bằng page size, không có trang trước hoặc trang kế tiếp. Ví dụ một trang có ba item với `size=5`:

- `page.number` bằng `0`.
- `page.totalElements` bằng `3`.
- `page.totalPages` bằng `1`.
- `self` trỏ đến page hiện tại.
- `next` và `prev` không xuất hiện nếu đó là quy ước của API.

Với kết quả rỗng, test cần xác nhận `_embedded` rỗng hoặc không chứa relation collection theo serializer đã chọn, metadata phản ánh tổng số phần tử bằng `0`, và link được tạo theo chính sách API. Đừng giả định mọi phiên bản Spring Data/Spring HATEOAS đều tạo first/last link giống nhau cho zero pages; hãy chốt hành vi mong muốn trong hợp đồng rồi kiểm tra đúng hành vi đó.

## Kiểm thử page index ngoài phạm vi

Request có thể yêu cầu `page` lớn hơn trang cuối. Spring Data thường trả page rỗng cho index ngoài phạm vi, nhưng API có thể chọn chuẩn hóa về trang cuối hoặc trả lỗi theo chính sách riêng.

Hãy quyết định và kiểm thử một hành vi rõ ràng:

- Trả page rỗng cùng metadata phản ánh request, hoặc
- Điều hướng/chuẩn hóa đến page cuối, hoặc
- Từ chối request bằng status code và error representation đã công bố.

Nếu trả page rỗng, cần xác nhận link `self`, `last` và metadata không dẫn client vào vòng lặp. Nếu chuẩn hóa page, response và `self.href` phải thống nhất page number thực tế. Không để body báo page `8` nhưng self link lại trỏ page `2` mà không có quy tắc giải thích.

## Kiểm thử sort ổn định và nhiều sort values

Spring Data cho phép lặp `sort` parameter:

```http
GET /api/orders?page=0&size=2&sort=createdAt,desc&sort=id,asc
```

Pagination links cần giữ đầy đủ thứ tự sort. Test nên parse query và xác nhận danh sách sort values, không chỉ kiểm tra một chuỗi chứa `sort=`.

Đồng thời, server phải allowlist sort properties được hỗ trợ. Không cho phép client truyền tên cột tùy ý để tạo SQL hoặc JPQL động. Kiểm thử sort link cần kết hợp kiểm thử validation với field không hợp lệ.

## Kiểm thử filter được giữ qua các page

Nếu collection được lọc theo trạng thái, khách hàng hoặc ngày, page link phải tiếp tục truy vấn trên cùng tập kết quả. Ví dụ:

```http
GET /api/orders?status=PENDING&customerId=cus-73&page=0&size=2
```

Link `next` phải giữ `status=PENDING` và `customerId=cus-73`. Nếu filter bị mất, trang kế tiếp có thể hiển thị đơn hàng không thuộc tập kết quả ban đầu dù page number đúng.

Nên kiểm tra ít nhất một filter đơn, nhiều filter kết hợp và filter có ký tự cần encoding. Nếu API hỗ trợ parameter lặp, xác nhận tất cả giá trị được giữ trong `href`.

## Pagination links với tham số tùy chỉnh

Ứng dụng có thể cấu hình tên page parameter khác `page`, tên size khác `size`, hoặc dùng một resolver tùy chỉnh. Khi đó test phải xác nhận đúng tên parameter trong link công khai.

Ví dụ nếu API công bố `offset` và `limit`, đừng chỉ kiểm tra `page` và `size`. Contract test nên phản ánh chính xác quy ước mà client nhìn thấy, không phụ thuộc vào tên Java variable hoặc default của framework.

Nếu controller dùng `@PageableDefault`, kiểm thử cả trường hợp client bỏ qua page/size để xác nhận default được áp dụng và `self.href` thể hiện đúng page size thực tế.

## Kiểm tra relation và URI theo cách bền vững

Các relation `first`, `prev`, `self`, `next`, `last` mô tả vị trí page. Không nên khẳng định host luôn là `localhost` hoặc query parameter luôn xuất hiện theo một thứ tự. Những chi tiết đó có thể thay đổi giữa local, staging, reverse proxy và production.

Nên kiểm tra:

- Relation có mặt hoặc vắng mặt theo vị trí page.
- Path trỏ đúng collection endpoint.
- Query `page` trỏ đến page number mong đợi.
- `size`, `sort` và filter được giữ nguyên.
- Link có thể được follow và trả đúng page metadata.

Nếu ứng dụng dùng CURIE cho relation riêng, kiểm tra CURIE declaration và relation key theo cấu hình HAL; pagination relations chuẩn thường được serialize trực tiếp.

## Bảo mật và dữ liệu trong pagination links

Pagination link có thể giữ lại query parameter của request hiện tại. Vì vậy, không đưa access token, password, secret hoặc dữ liệu nhạy cảm vào query string. URI thường xuất hiện trong access log, proxy log, tracing và browser history.

Kiểm thử cần bảo đảm:

- Link không làm lộ token hoặc secret.
- Filter không vượt qua tenant scope hoặc authorization.
- Sort field bị giới hạn trong danh sách cho phép.
- `size` có giới hạn tối đa để tránh tải dữ liệu quá lớn.
- Cache key tính đến filter, sort, page và phạm vi người dùng khi response phụ thuộc quyền.
- Endpoint kiểm tra authorization trên mỗi page request, không dựa vào việc client đã nhận được link trước đó.

Link không phải cơ chế phân quyền. Client có thể sửa page, size hoặc filter thủ công; server phải validate và authorize request mới.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra status `200` | Không phát hiện thiếu hoặc sai pagination links. | Kiểm tra page metadata và từng relation. |
| Chỉ kiểm tra `next` tồn tại | Không phát hiện link mang page/filter/sort sai. | Parse `href` và xác nhận query values. |
| So sánh toàn bộ URL dạng chuỗi | Test dễ hỏng do host, encoding hoặc thứ tự query thay đổi. | Phân tích URI rồi kiểm tra path và query. |
| Không kiểm thử first/middle/last page | Bỏ sót lỗi biên như `prev` ở trang đầu hoặc `next` ở trang cuối. | Tạo test cho từng vị trí page. |
| Dữ liệu test không có sort ổn định | Item có thể lặp hoặc mất giữa các page. | Dùng sort key phụ duy nhất và fixture xác định. |
| Filter biến mất ở page tiếp theo | Kết quả bị trộn với tập dữ liệu khác. | Kiểm tra filter được giữ trong `next` và `prev` href. |
| Giả định trang cuối luôn đầy đủ | Test sai khi số item còn lại ít hơn page size. | Phân biệt page size với số item thực tế. |
| Không định nghĩa hành vi empty/out-of-range | Client không biết dừng hoặc điều hướng thế nào. | Công bố chính sách và viết test tương ứng. |
| Đưa secret vào query string | Secret có thể xuất hiện trong log và history. | Dùng header xác thực và không đưa secret vào href. |
| Tin link thay cho authorization | Request trực tiếp có thể vượt qua kỳ vọng bảo mật. | Validate và authorize từng page request ở server. |

## Ghi nhớ

- Pagination response gồm page metadata và navigation links.
- HAL thường đặt metadata trong `page`, links trong `_links` và item trong `_embedded`.
- Dùng `PagedModel` và `PagedResourcesAssembler` để tạo response phân trang với Spring HATEOAS/Spring Data.
- Kiểm thử `first`, `prev`, `self`, `next`, `last` ở trang đầu, giữa và cuối.
- Xác nhận `page.number`, `page.size`, `page.totalElements` và `page.totalPages`.
- Parse `href` để kiểm tra page, size, sort và filter; tránh so sánh raw URL.
- Follow `next.href` trong integration test để xác nhận link điều hướng đến đúng page.
- Kiểm thử collection một trang, rỗng và page index ngoài phạm vi theo hợp đồng đã chọn.
- Dùng sort ổn định để tránh item lặp hoặc bị bỏ qua giữa các page.
- Bảo vệ endpoint, giới hạn page size/sort field và không đưa secret vào query string.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paging)
- [Spring HATEOAS API – PagedModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [Spring Data Commons API – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring Data Web Support – Pageable and Sort](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Framework Reference – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
