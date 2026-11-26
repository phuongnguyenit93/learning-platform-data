# Tài liệu tham số

API tìm kiếm thường nhận các tham số query để lọc, sắp xếp và phân trang dữ liệu. Ví dụ, client có thể tìm đơn hàng theo trạng thái, khách hàng, khoảng thời gian; chọn thứ tự sắp xếp; rồi yêu cầu trang tiếp theo. Nếu tên, kiểu và quy tắc của các tham số không được công bố rõ, client phải đoán query string hoặc phụ thuộc vào tài liệu ngoài API.

Trong REST API có hypermedia, server có thể công bố một link tìm kiếm dưới dạng URI template. Template cho client biết những biến query nào có thể được cung cấp. Spring MVC bind các biến đó bằng `@RequestParam` và `Pageable`; Spring HATEOAS đưa template vào `_links` để client khám phá trực tiếp từ representation. Tài liệu API tĩnh như OpenAPI hoặc Spring REST Docs bổ sung kiểu dữ liệu, ý nghĩa, giá trị mặc định và ràng buộc chi tiết.

## Tham số query là một phần hợp đồng API

Giả sử endpoint tìm kiếm đơn hàng hỗ trợ:

```http
GET /api/orders?status=PAID&customerId=3fa85f64-5717-4562-b3fc-2c963f66afa6&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

Các tham số này không phải chi tiết nội bộ của controller. Chúng là đầu vào mà client phải hiểu để gọi endpoint đúng cách. Hợp đồng cần mô tả tối thiểu:

- Tên tham số chính xác và mục đích lọc/sắp xếp/phân trang.
- Kiểu dữ liệu và định dạng truyền trên URL.
- Tham số bắt buộc hay tùy chọn.
- Giá trị mặc định khi client bỏ qua.
- Miền giá trị hợp lệ, giới hạn và các giá trị được hỗ trợ.
- Cách truyền nhiều giá trị hoặc nhiều tiêu chí sắp xếp.
- Hành vi khi tham số sai định dạng hoặc không được hỗ trợ.

Ví dụ bảng tham số cho endpoint trên:

| Tham số | Kiểu/định dạng | Bắt buộc | Mặc định và quy tắc |
| --- | --- | --- | --- |
| `status` | Enum: `PENDING`, `PAID`, `SHIPPED`, `CANCELLED` | Không | Bỏ qua filter trạng thái nếu không truyền. |
| `customerId` | UUID | Không | Chỉ trả đơn hàng thuộc khách hàng có ID này. |
| `createdAfter` | ISO-8601 date-time | Không | Chỉ lấy đơn hàng tạo tại hoặc sau thời điểm này. |
| `createdBefore` | ISO-8601 date-time | Không | Chỉ lấy đơn hàng tạo tại hoặc trước thời điểm này. |
| `page` | Số nguyên không âm | Không | `0`, trang đầu tiên. |
| `size` | Số nguyên dương | Không | `20`, giới hạn tối đa `100`. |
| `sort` | Tên trường và hướng, dạng `field,direction` | Không | `createdAt,desc`; chỉ cho phép trường được whitelist. |

Nếu API dùng tên hoặc quy tắc khác, hãy mô tả đúng hợp đồng thực tế. Không nên tài liệu hóa một tham số mà endpoint chưa hỗ trợ.

## Phân biệt tham số query với property của request body

Tham số query thường điều khiển việc chọn tập tài nguyên: filter, sort, page, size. Property của request body thường mang dữ liệu để tạo hoặc cập nhật một tài nguyên. Hai nhóm này có thể dùng kiểu dữ liệu giống nhau nhưng được truyền và xử lý khác nhau.

| Loại đầu vào | Vị trí | Ví dụ | Cách mô tả |
| --- | --- | --- | --- |
| Query parameter | URL sau dấu `?` | `?status=PAID&page=0` | `@RequestParam`, `Pageable`, URI template. |
| Path variable | Một phần đường dẫn | `/orders/{orderId}` | `@PathVariable` và path template. |
| Request body property | Body của POST/PUT/PATCH | `{ "note": "Giao buổi sáng" }` | Request DTO, schema và affordance/HAL-FORMS template. |

Trong Spring HATEOAS, link URI template là cách phù hợp để công bố các biến query của một thao tác tìm kiếm GET. HAL-FORMS `_templates` thường mô tả thao tác có input body; không nên nhầm nó với danh sách query parameter của một link tìm kiếm.

## Công bố URI template trong hypermedia

Một link thông thường trỏ đến một URI cụ thể. URI template công bố URI có các biến mà client có thể điền. Với RFC 6570, biểu thức `{?status,customerId,page,size,sort}` cho biết các biến query có thể được mở rộng thành query string.

Ví dụ HAL:

```json
{
  "_links": {
    "search": {
      "href": "https://shop.example/api/orders{?status,customerId,createdAfter,createdBefore,page,size,sort}",
      "templated": true
    }
  }
}
```

Client đọc relation `search`, nhận biết link là template qua `templated: true`, rồi mở rộng những biến cần dùng. Ví dụ, nếu client chỉ muốn tìm đơn hàng đã thanh toán của một khách hàng cụ thể, nó có thể mở rộng template thành:

```text
/api/orders?status=PAID&customerId=3fa85f64-5717-4562-b3fc-2c963f66afa6
```

Nếu client muốn trang thứ hai với 20 item mỗi trang, nó có thể mở rộng thành:

```text
/api/orders?page=1&size=20
```

Client không cần tự đoán endpoint `/api/orders` từ tên class hay tự ghép các URL theo quy ước không được công bố. Server vẫn kiểm soát URI gốc và tên biến được hỗ trợ.

## Tạo search link bằng Spring HATEOAS

Spring HATEOAS có kiểu `Link` để biểu diễn link và hỗ trợ URI template. Có thể tạo link tìm kiếm bằng relation `search`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class ApiRootController {

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    ApiRoot root() {
        ApiRoot model = new ApiRoot();
        model.add(Link.of(
                "/api/orders{?status,customerId,createdAfter,createdBefore,page,size,sort}",
                "search"));
        return model;
    }
}

class ApiRoot extends RepresentationModel<ApiRoot> {
}
```

`Link.of(...)` tạo link với URI template; khi serialize HAL, link có biến được đánh dấu `templated: true`. Relation `search` cho client biết đây là điểm bắt đầu của thao tác tìm kiếm. Trong ứng dụng thực tế, hãy dùng một nguồn cấu hình URI hoặc link builder nhất quán nếu base path thay đổi theo môi trường; không để các client tự xây URI từ cấu trúc nội bộ.

Một response root có thể trông như sau:

```json
{
  "_links": {
    "search": {
      "href": "https://shop.example/api/orders{?status,customerId,createdAfter,createdBefore,page,size,sort}",
      "templated": true
    }
  }
}
```

Template chỉ công bố tên biến. Nó không tự mô tả đầy đủ kiểu dữ liệu, danh sách enum, giá trị mặc định hay giới hạn `size`; những thông tin đó cần được mô tả trong tài liệu API hoặc profile phù hợp.

## Bind tham số bằng @RequestParam

Controller khai báo query parameter bằng `@RequestParam`. Spring MVC chuyển giá trị chuỗi trong URL sang kiểu Java tương ứng:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderSearchController {

    @GetMapping("/api/orders")
    Object search(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) UUID customerId,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant createdAfter,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant createdBefore) {

        return searchService.search(
                status, customerId, createdAfter, createdBefore);
    }
}
```

Ví dụ dùng `Object` và `searchService` để tập trung vào binding; endpoint thực tế nên trả resource model hoặc `PagedModel` theo hợp đồng hypermedia. Các kiểu `OrderStatus` và `searchService` thuộc ứng dụng.

Một số điểm cần nhớ:

- `required = false` cho phép client bỏ qua filter.
- `UUID` giúp Spring chuyển chuỗi sang UUID; giá trị sai định dạng thường dẫn đến lỗi binding.
- `@DateTimeFormat` quy định định dạng ngày giờ được chấp nhận.
- Enum giới hạn tập giá trị hợp lệ theo kiểu Java, nhưng tài liệu vẫn cần liệt kê các giá trị mà client được dùng.
- Nếu có giá trị mặc định, dùng `defaultValue` hoặc xử lý mặc định ở tầng phân trang/service và ghi rõ trong hợp đồng.

Không dùng `@RequestParam` mà không nêu ý nghĩa của tham số. Tên Java có thể thay đổi trong refactor; tên query parameter công khai cần được cố định rõ bằng `name` khi cần:

```java
@RequestParam(name = "customerId", required = false) UUID customerId
```

## Bind page, size và sort bằng Pageable

Spring Data Web có thể bind các tham số `page`, `size` và `sort` thành `Pageable`. Nhờ vậy, controller không phải tự khai báo và chuyển đổi từng tham số phân trang:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping(value = "/api/orders", produces = MediaTypes.HAL_JSON_VALUE)
PagedModel<OrderResource> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId,
        @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(status, customerId, pageable);
    return pagedAssembler.toModel(page, orderResourceAssembler);
}
```

Với cấu hình trên, query parameter `page` mặc định là `0`, `size` mặc định là `20`, sort mặc định theo `createdAt` giảm dần. Có thể đặt giới hạn page size tối đa trong cấu hình `PageableHandlerMethodArgumentResolver`; tài liệu cần nêu giới hạn đó để client không gửi request vượt quá khả năng API.

Spring Data hỗ trợ nhiều tiêu chí sort bằng cách lặp tham số `sort`, ví dụ:

```http
GET /api/orders?sort=status,asc&sort=createdAt,desc
```

Hãy kiểm tra resolver và cấu hình thực tế để xác nhận cách parse sort trong phiên bản Spring Data đang dùng. Nếu API hỗ trợ cú pháp khác, mô tả đúng cú pháp đó thay vì mặc định client phải biết quy ước Spring.

## Tài liệu hóa tên, kiểu và ràng buộc

URI template chỉ cho biết tên biến. Bảng tài liệu tham số cần mô tả semantics và constraint mà client không thể suy ra từ tên biến:

| Tham số | Mô tả | Ví dụ | Ràng buộc |
| --- | --- | --- | --- |
| `status` | Chỉ lấy đơn hàng theo trạng thái. | `PAID` | Một trong các enum đã công bố. |
| `customerId` | Chỉ lấy đơn hàng của khách hàng. | `3fa85f64-5717-4562-b3fc-2c963f66afa6` | UUID hợp lệ. |
| `createdAfter` | Mốc thời gian bắt đầu. | `2026-01-01T00:00:00Z` | ISO-8601 date-time; inclusive nếu hợp đồng quy định. |
| `createdBefore` | Mốc thời gian kết thúc. | `2026-01-31T23:59:59Z` | ISO-8601 date-time; cần lớn hơn hoặc bằng `createdAfter`. |
| `page` | Chỉ số trang. | `0` | Số nguyên không âm. |
| `size` | Số item tối đa trong một trang. | `20` | Từ `1` đến `100`. |
| `sort` | Trường và hướng sắp xếp. | `createdAt,desc` | Chỉ trường được whitelist; hướng `asc` hoặc `desc`. |

Ghi rõ cách kết hợp filter. Ví dụ, nếu `status` và `customerId` cùng xuất hiện, API có thể áp dụng điều kiện AND. Với khoảng thời gian, cần nói rõ hai đầu mút inclusive hay exclusive và cách xử lý khi `createdAfter` lớn hơn `createdBefore`.

Ghi rõ tham số lặp được hay chỉ nhận một giá trị. Ví dụ `sort` có thể lặp nhiều lần; `status` có thể chỉ nhận một trạng thái. Nếu API hỗ trợ nhiều trạng thái, hãy quy định cú pháp cụ thể như `status=PAID&status=SHIPPED` hoặc `status=PAID,SHIPPED`.

## Whitelist sort và công bố giới hạn

Không nên cho client sắp xếp theo mọi thuộc tính của entity. Một số thuộc tính nội bộ có thể gây truy vấn tốn kém, không được index hoặc không nên trở thành một phần hợp đồng. Hãy ánh xạ tên sort công khai sang thuộc tính được phép ở tầng query:

```java
import java.util.Map;

import org.springframework.data.domain.Sort;

class OrderSortPolicy {

    private static final Map<String, String> ALLOWED = Map.of(
            "createdAt", "createdAt",
            "status", "status",
            "totalAmount", "totalAmount");

    Sort validateAndBuild(String property, Sort.Direction direction) {
        String mappedProperty = ALLOWED.get(property);
        if (mappedProperty == null) {
            throw new IllegalArgumentException("Unsupported sort field: " + property);
        }
        return Sort.by(direction, mappedProperty);
    }
}
```

Đây là policy minh họa cho trường hợp controller nhận sort riêng; nếu dùng `Pageable` trực tiếp, hãy áp dụng whitelist tương đương trước khi đưa `Sort` vào repository. Không nên nối trực tiếp chuỗi sort của client vào SQL. Server phải kiểm tra tên trường và hướng sắp xếp trước khi truy vấn.

Tài liệu cần nêu:

- Các trường được sort và tên public tương ứng.
- Hướng mặc định và cú pháp truyền hướng.
- Có hỗ trợ nhiều tiêu chí sort không.
- Giới hạn page size và giá trị mặc định.
- Hành vi với tên trường không hợp lệ: trả lỗi rõ ràng hay bỏ qua theo chính sách đã công bố.

## Bảo toàn tham số khi điều hướng trang

Khi client theo link `next`, các filter và sort hiện tại cần được giữ lại, chỉ thay đổi page. Ví dụ:

```text
Trang hiện tại:
/api/orders?status=PAID&customerId=3fa85f64-5717-4562-b3fc-2c963f66afa6&page=0&size=20&sort=createdAt,desc

Link next:
/api/orders?status=PAID&customerId=3fa85f64-5717-4562-b3fc-2c963f66afa6&page=1&size=20&sort=createdAt,desc
```

`PagedResourcesAssembler` tạo các link phân trang dựa trên `Page` và request hiện tại. Khi controller nhận filter riêng, hãy kiểm tra các tham số đó còn xuất hiện trong link `next`/`prev` ở response thực tế. Nếu tự tạo link, cần bảo toàn mọi filter/sort có ảnh hưởng đến tập kết quả.

Một link phân trang là URI cụ thể cho trang hiện tại/tiếp theo; search link ở resource gốc có thể là URI template để client bắt đầu một truy vấn mới. Hai loại link phục vụ hai bước khác nhau trong quá trình khám phá API.

## Bổ sung tài liệu bằng OpenAPI

URI template giúp client khám phá tên biến trong runtime. OpenAPI bổ sung tài liệu có cấu trúc cho công cụ sinh client, Swagger UI và quy trình review hợp đồng. Với springdoc-openapi, có thể dùng `@Parameter` để mô tả từng query parameter:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.RequestParam;

@Parameter(
        name = "status",
        description = "Chỉ lấy đơn hàng theo trạng thái",
        schema = @Schema(implementation = OrderStatus.class),
        example = "PAID")
@RequestParam(name = "status", required = false) OrderStatus status
```

Đoạn annotation được đặt cùng tham số method trong controller. Các annotation OpenAPI thuộc dependency springdoc/OpenAPI, không phải Spring HATEOAS core. Với `Pageable`, springdoc có hỗ trợ `@ParameterObject` để biểu diễn các query parameter phân trang; hãy kiểm tra phiên bản springdoc đang dùng và tùy chỉnh mô tả cho `page`, `size`, `sort` nếu cần.

Không để OpenAPI và runtime link template lệch nhau. Nếu OpenAPI nói `size` tối đa 100 nhưng server cho phép 500, hoặc URI template thiếu biến `createdAfter`, client sẽ nhận hai hợp đồng mâu thuẫn. Nên kiểm thử và review cả hai nguồn tài liệu khi thay đổi endpoint.

## Bổ sung tài liệu bằng Spring REST Docs

Spring REST Docs tạo snippet từ request/response đã được kiểm thử. Với query parameter, `requestParameters(...)` ghi lại tên, mô tả, bắt buộc/tùy chọn và ví dụ:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders")
        .param("status", "PAID")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andDo(document("orders-search",
        requestParameters(
            parameterWithName("status")
                .optional()
                .description("Lọc theo trạng thái đơn hàng"),
            parameterWithName("page")
                .optional()
                .description("Chỉ số trang, bắt đầu từ 0"),
            parameterWithName("size")
                .optional()
                .description("Số item mỗi trang, tối đa 100"))));
```

Snippet chỉ được tạo khi test thực thi thành công. Cách này giúp tài liệu phản ánh request thực tế mà ứng dụng xử lý. Spring REST Docs là công cụ bổ trợ; nó không tự công bố metadata trong HAL response và không thay thế URI template trong hypermedia.

## Xử lý tham số sai và bảo mật

Tài liệu cần mô tả hành vi khi client gửi giá trị không hợp lệ. Ví dụ:

- `customerId=abc` không phải UUID hợp lệ.
- `status=UNKNOWN` không nằm trong enum được hỗ trợ.
- `createdAfter` có định dạng ngày giờ sai.
- `createdAfter` muộn hơn `createdBefore`.
- `size=1000` vượt giới hạn tối đa.
- `sort=internalSecret,desc` dùng trường không được công bố.

Chọn status code và cấu trúc lỗi nhất quán, thường là `400 Bad Request` cho tham số sai định dạng hoặc ngoài miền giá trị. Không tiết lộ tên thuộc tính nội bộ, câu SQL hoặc chi tiết persistence trong lỗi trả về.

Các filter cũng phải tuân theo quyền truy cập. Việc client biết tên tham số hoặc mở rộng URI template không cấp quyền đọc dữ liệu. Service/repository phải áp dụng tenant scope, authorization và row-level policy phù hợp trước khi trả kết quả.

## Kiểm thử tài liệu tham số và URI template

Kiểm thử nên xác nhận ba lớp:

1. Search link công bố đúng các biến query và được đánh dấu `templated`.
2. Controller bind đúng kiểu và áp dụng đúng filter/sort/page.
3. Link phân trang giữ nguyên filter và sort trong khi thay đổi page.

Ví dụ kiểm tra HAL search link:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.search.templated").value(true))
        .andExpect(jsonPath("$._links.search.href")
                .value(org.hamcrest.Matchers.containsString(
                        "{?status,customerId,createdAfter,createdBefore,page,size,sort}")));
```

Ví dụ kiểm tra tham số tìm kiếm và link phân trang:

```java
mockMvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("customerId", "3fa85f64-5717-4562-b3fc-2c963f66afa6")
                .param("page", "0")
                .param("size", "2")
                .param("sort", "createdAt,desc")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.next.href")
                .value(org.hamcrest.Matchers.allOf(
                        org.hamcrest.Matchers.containsString("status=PAID"),
                        org.hamcrest.Matchers.containsString(
                                "customerId=3fa85f64-5717-4562-b3fc-2c963f66afa6"),
                        org.hamcrest.Matchers.containsString("page=1"),
                        org.hamcrest.Matchers.containsString("sort=createdAt"))));
```

Đoạn test minh họa assertion; test đầy đủ cần import MockMvc, `MediaTypes`, `jsonPath` và chuẩn bị fixture có nhiều hơn một trang kết quả. Nên có test cho giá trị enum sai, UUID sai, page size vượt giới hạn và sort field không được phép.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ ghi `@RequestParam` trong code mà không công bố hợp đồng | Client không biết tên và cách dùng tham số. | Công bố URI template và tài liệu chi tiết. |
| URI template không có biến query | Client phải đoán tham số được hỗ trợ. | Thêm biến RFC 6570 vào link `search`. |
| Nghĩ URI template mô tả luôn kiểu và giới hạn | Client có thể gửi giá trị sai. | Bổ sung bảng tham số, OpenAPI hoặc REST Docs. |
| Tài liệu và runtime binding khác nhau | Client sinh request không hợp lệ. | Kiểm thử và đồng bộ hai hợp đồng. |
| Cho sort theo mọi thuộc tính entity | Lộ cấu trúc nội bộ hoặc gây truy vấn kém an toàn. | Whitelist sort property. |
| Link next làm mất filter | Client chuyển sang một tập kết quả khác khi phân trang. | Kiểm tra href và giữ filter/sort hiện tại. |
| Dùng HAL-FORMS cho mọi query parameter | Lẫn lộn query của search với input body của action. | Dùng URI template cho GET query; dùng HAL-FORMS khi cần mô tả template thao tác có input. |

## Nguyên tắc thiết kế

- Xem tên, kiểu và ràng buộc query parameter là một phần hợp đồng API.
- Dùng relation `search` cùng URI template để client khám phá các biến query.
- Dùng `@RequestParam` cho filter và `Pageable` cho page/size/sort.
- Mô tả rõ kiểu, required, default, enum, định dạng, giới hạn và khả năng lặp.
- Whitelist trường sort và xác thực mọi tham số ở server.
- Giữ filter/sort trong các link phân trang.
- Dùng OpenAPI hoặc Spring REST Docs để cung cấp tài liệu chi tiết cho người phát triển và công cụ.
- Kiểm thử search template, binding, lỗi tham số và href phân trang.

Tài liệu tham số tốt kết hợp khả năng khám phá runtime với mô tả hợp đồng rõ ràng. URI template trong Spring HATEOAS chỉ ra những biến mà client có thể dùng; `@RequestParam` và `Pageable` xác định cách server tiếp nhận chúng; OpenAPI hoặc Spring REST Docs giải thích kiểu, mặc định và ràng buộc. Khi ba phần thống nhất, client có thể tìm kiếm và phân trang theo các link do server công bố mà không phải đoán cấu trúc endpoint.
